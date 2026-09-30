"""MCP catalog and tool calls: the server is the single source of truth about tools and skills.

- `fetch_catalog`: server/discover instructions + tools/list (with `_meta`/annotations) + the
  `skill://<id>/SKILL.md` resources (frontmatter `allowed-tools` must match the `_meta` skills).
- `CatalogProvider`: Redis cache (TTL = server `ttlMs`, fallback 300 s) under
  `mcp:catalog:<url>:<protocol_version>`, plus an in-process copy until the same TTL.
- `Catalog`: skill RouteOptions (3 skills + `__global__`), per-skill tool RouteOptions
  (5 skill tools + 3 globals) and OpenAI-format tool schemas, verbatim from the server.
- `McpTools`: `tools/call` with `X-Customer-Id` and the current `traceparent` in `_meta`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import mcp.types as mt
import yaml
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import MCPError

from routing_study.routers.base import GLOBAL_OPTION, RouteOption
from routing_study.settings import Settings
from routing_study.tracing.langfuse import traceparent

log = logging.getLogger(__name__)

PROTOCOL_VERSION = mt.LATEST_PROTOCOL_VERSION
RDNS = "br.routingstudy"
SERVER_GLOBAL = "global"  # `_meta.br.routingstudy/skill` value of the always-exposed tools
DEFAULT_TTL_S = 300
# Description sections kept out of tool-stage RouteOptions: DON'T USE FOR names the sibling
# tools (their vocabulary would pull BM25/embeddings towards the wrong tool); CONFIRMATION and
# RESULT say nothing about when to use the tool. The executor still gets the full description.
ROUTING_EXCLUDED_SECTIONS = ("DON'T USE FOR:", "CONFIRMATION:", "RESULT:")
_AVOID = "DON'T USE FOR:"
_USE = re.compile(r"\(use ([^)]*)\)")
# A DON'T USE FOR clause opening with "se" is a precondition of the tool's own action
# ("se o pedido já foi enviado"): true between tools, false as a skill-level rule.
_CONDITION = re.compile(r"se\b", re.IGNORECASE)


@dataclass(frozen=True)
class Skill:
    id: str
    description: str
    examples: list[str]
    markdown: str


@dataclass
class Catalog:
    url: str
    protocol_version: str
    instructions: str
    tools: list[dict[str, Any]]  # tools/list entries (by alias), server order
    skills: dict[str, Skill]
    ttl_s: int = DEFAULT_TTL_S
    _by_name: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_name = {t["name"]: t for t in self.tools}

    # ------------------------------------------------------------ identity / cache

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()[:12]

    def to_json(self) -> str:
        """Server order kept (skills, schema properties): it shapes the prompt bytes, and the
        hash covers it. No `sort_keys`: a Redis round-trip must not reorder anything."""
        data = asdict(self)
        data.pop("_by_name")
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | bytes) -> Catalog:
        data = json.loads(raw)
        data["skills"] = {k: Skill(**v) for k, v in data["skills"].items()}
        return cls(**data)

    # ------------------------------------------------------------ lookups

    def tool(self, name: str) -> dict[str, Any]:
        return self._by_name[name]

    def has_tool(self, name: str) -> bool:
        return name in self._by_name

    def meta(self, name: str, key: str, default: Any = None) -> Any:
        return (self._by_name[name].get("_meta") or {}).get(f"{RDNS}/{key}", default)

    def skill_of(self, tool: str) -> str:
        skill = self.meta(tool, "skill")
        return GLOBAL_OPTION if skill == SERVER_GLOBAL else skill

    def tools_for(self, skill_id: str) -> list[str]:
        return [t["name"] for t in self.tools if self.skill_of(t["name"]) == skill_id]

    @property
    def global_tools(self) -> list[str]:
        return self.tools_for(GLOBAL_OPTION)

    def ordered(self, names: set[str] | list[str]) -> list[str]:
        """Tool names in server order (stable tool blocks keep the prompt cache warm)."""
        wanted = set(names)
        return [t["name"] for t in self.tools if t["name"] in wanted]

    # ------------------------------------------------------------ route options

    def avoid_clauses(self, name: str) -> list[tuple[str, list[str]]]:
        """DON'T USE FOR of a tool as [(clause, [tools to use instead])], verbatim, one per
        `;`-separated clause; clauses that name no known tool are dropped."""
        out: list[tuple[str, list[str]]] = []
        for line in self.tool(name)["description"].split("\n"):
            if not line.lstrip().startswith(_AVOID):
                continue
            for clause in line.split(_AVOID, 1)[1].split(";"):
                targets = [
                    t
                    for m in _USE.finditer(clause)
                    for t in re.findall(r"[a-z_]+", m.group(1))
                    if self.has_tool(t)
                ]
                if targets:
                    out.append((clause.strip(" .;"), list(dict.fromkeys(targets))))
        return out

    def _skill_avoid(self, skill_id: str) -> list[tuple[str, list[str]]]:
        """The skill's tools' DON'T USE FOR clauses whose subject is skill-level, with each
        `(use tool)` rewritten as `(use skill)`. Kept only when EVERY target is in another
        skill (a mixed clause is also served by this skill) and the clause names an intent,
        not a precondition of the source tool's own action ("se o pedido já foi enviado":
        that intent still belongs to this skill, only this tool refuses it)."""
        tools = self.tools_for(skill_id) if skill_id != GLOBAL_OPTION else self.global_tools
        out: list[tuple[str, list[str]]] = []
        for name in tools:
            for clause, targets in self.avoid_clauses(name):
                if _CONDITION.match(clause):
                    continue
                skills = list(dict.fromkeys(map(self.skill_of, targets)))
                if skill_id in skills:
                    continue

                def to_skill(m: re.Match[str], home: str = skill_id) -> str:
                    ids = [
                        self.skill_of(t)
                        for t in re.findall(r"[a-z_]+", m.group(1))
                        if self.has_tool(t)
                    ]
                    ids = [i for i in dict.fromkeys(ids) if i and i != home]
                    return f"(use {' / '.join(ids)})" if ids else ""

                text = re.sub(r"\s+", " ", _USE.sub(to_skill, clause)).strip()
                if (text, skills) not in out:
                    out.append((text, skills))
        return out

    def _skill_shots(self, skill_id: str) -> list[str]:
        """The skill's tool examples, round-robin over its tools (tool order)."""
        tools = self.tools_for(skill_id) if skill_id != GLOBAL_OPTION else self.global_tools
        pools = [list(self.meta(n, "examples", [])) for n in tools]
        return [p[i] for i in range(max(map(len, pools), default=0)) for p in pools if i < len(p)]

    def skill_options(self) -> list[RouteOption]:
        opts = [
            RouteOption(
                id=s.id,
                description=s.description,
                examples=s.examples,
                avoid=self._skill_avoid(s.id),
                shots=self._skill_shots(s.id),
            )
            for s in self.skills.values()
        ]
        globals_ = self.global_tools
        opts.append(
            RouteOption(
                id=GLOBAL_OPTION,
                description="Assuntos transversais, sem skill específica: "
                + " ".join(self.tool(n)["description"].split("\n", 1)[0] for n in globals_),
                examples=[e for n in globals_ for e in self.meta(n, "examples", [])],
                keywords=[k for n in globals_ for k in self.meta(n, "keywords", [])],
                avoid=self._skill_avoid(GLOBAL_OPTION),
                shots=self._skill_shots(GLOBAL_OPTION),
            )
        )
        return opts

    def tool_option(self, name: str) -> RouteOption:
        lines = self.tool(name)["description"].split("\n")
        description = "\n".join(
            ln for ln in lines if not ln.lstrip().startswith(ROUTING_EXCLUDED_SECTIONS)
        )
        return RouteOption(
            id=name,
            description=description,
            examples=list(self.meta(name, "examples", [])),
            keywords=list(self.meta(name, "keywords", [])),
            avoid=self.avoid_clauses(name),
            shots=list(self.meta(name, "examples", [])),
        )

    def tool_options(self, skill_id: str) -> list[RouteOption]:
        names = self.tools_for(skill_id) if skill_id != GLOBAL_OPTION else []
        return [self.tool_option(n) for n in [*names, *self.global_tools]]

    def openai_tool(self, name: str) -> dict[str, Any]:
        """Server description and inputSchema verbatim (no host rewrite)."""
        t = self.tool(name)
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }


# ---------------------------------------------------------------- MCP client


def mcp_client(settings: Settings, customer_id: str | None = None) -> Client:
    headers: dict[str, str] = {}
    if settings.mcp_token:
        headers["Authorization"] = f"Bearer {settings.mcp_token.get_secret_value()}"
    if customer_id:
        headers["X-Customer-Id"] = customer_id
    transport = StreamableHttpTransport(settings.mcp_url, headers=headers)
    return Client(transport, timeout=settings.request_timeout_s)


def parse_skill(skill_id: str, markdown: str) -> tuple[Skill, set[str]]:
    """(skill, frontmatter `allowed-tools`)."""
    front: dict[str, Any] = {}
    if markdown.startswith("---"):
        _, raw, _ = markdown.split("---", 2)
        front = yaml.safe_load(raw) or {}
    skill = Skill(
        id=front.get("name", skill_id),
        description=front.get("description", ""),
        examples=list(front.get("examples") or []),
        markdown=markdown,
    )
    return skill, set(front.get("allowed-tools") or [])


def _text(result: list[Any]) -> str:
    return "\n".join(getattr(c, "text", "") for c in result)


async def fetch_catalog(settings: Settings, client: Client | None = None) -> Catalog:
    """`client`: an unopened client to use instead of `mcp_client(settings)` (e.g. an
    in-process `Client(mcp_server.server.mcp)` for offline tuning)."""
    async with client or mcp_client(settings) as client:
        tools: list[mt.Tool] = []
        cursor: str | None = None
        ttl_ms: int | None = None
        while True:
            page = await client.list_tools_mcp(cursor=cursor)
            dumped = page.model_dump(by_alias=True)
            ttl_ms = ttl_ms or dumped.get("ttlMs")
            tools.extend(page.tools)
            cursor = dumped.get("nextCursor")
            if not cursor:
                break
        skills: dict[str, Skill] = {}
        allowed: dict[str, set[str]] = {}
        for res in await client.list_resources():
            uri = str(res.uri)
            if uri.startswith("skill://") and uri.endswith("/SKILL.md"):
                skill_id = uri.removeprefix("skill://").split("/", 1)[0]
                skill, allowed[skill_id] = parse_skill(
                    skill_id, _text(await client.read_resource(uri))
                )
                skills[skill_id] = skill
        catalog = Catalog(
            url=settings.mcp_url,
            protocol_version=client.protocol_version or PROTOCOL_VERSION,
            instructions=client.instructions or "",
            tools=[t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools],
            skills=skills,
            ttl_s=int(ttl_ms / 1000) if ttl_ms else DEFAULT_TTL_S,
        )
    for skill_id, names in allowed.items():  # SKILL.md frontmatter vs tools/list `_meta`
        if names != set(catalog.tools_for(skill_id)):
            raise ValueError(
                f"skill {skill_id}: allowed-tools {sorted(names)} != _meta "
                f"{sorted(catalog.tools_for(skill_id))}"
            )
    return catalog


class CatalogProvider:
    """Catalog with a Redis cache shared across processes and an in-process copy."""

    def __init__(self, settings: Settings, redis: Any | None = None) -> None:
        self.settings = settings
        self.redis = redis
        self.key = f"mcp:catalog:{settings.mcp_url}:{PROTOCOL_VERSION}"
        self._memo: tuple[Catalog, float] | None = None

    async def get(self) -> tuple[Catalog, str]:
        """(catalog, source) with source in memory | redis | server."""
        now = time.monotonic()
        if self._memo and now < self._memo[1]:
            return self._memo[0], "memory"
        catalog, source, ttl_s = None, "server", None
        if self.redis is not None:
            try:
                raw = await self.redis.get(self.key)
                if raw:
                    catalog, source = Catalog.from_json(raw), "redis"
                    ttl_s = await self.redis.ttl(self.key)  # memo ends with the Redis key
            except Exception:  # cache is an optimization; the server is authoritative
                log.warning("redis catalog read failed", exc_info=True)
        if catalog is None:
            catalog = await fetch_catalog(self.settings)
            if self.redis is not None:
                try:
                    await self.redis.set(self.key, catalog.to_json(), ex=catalog.ttl_s)
                except Exception:
                    log.warning("redis catalog write failed", exc_info=True)
        remaining = ttl_s if ttl_s is not None and 0 <= ttl_s <= catalog.ttl_s else catalog.ttl_s
        self._memo = (catalog, now + remaining)
        return catalog, source


# ---------------------------------------------------------------- tools/call


@dataclass
class ToolOutcome:
    text: str
    structured: dict[str, Any] | None
    is_error: bool

    @property
    def status(self) -> str:
        return (self.structured or {}).get("status") or ("error" if self.is_error else "completed")


class McpTools:
    """`tools/call` for one customer. Use as `async with McpTools(settings, customer_id)`."""

    def __init__(self, settings: Settings, customer_id: str | None) -> None:
        self._client = mcp_client(settings, customer_id)

    async def __aenter__(self) -> McpTools:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.__aexit__(*exc)

    async def call(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        try:
            r = await self._client.call_tool_mcp(name, args, meta=traceparent() or None)
        except MCPError as exc:
            # Only -32602 (the model's arguments) is tool-visible. Transport/session failures
            # (closed, timeout, HTTP 5xx, session terminated) raise: a top-level case error.
            if exc.code != mt.INVALID_PARAMS:
                raise
            return ToolOutcome(
                text=f"{type(exc).__name__}: {exc.message}"[:500],
                is_error=True,
                structured={"status": "error", "code": "PROTOCOL_ERROR"},
            )
        return ToolOutcome(
            text=_text(r.content), structured=r.structured_content, is_error=bool(r.is_error)
        )
