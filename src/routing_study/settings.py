"""Experiment settings: `.env` secrets + per-experiment YAML + `__`-nested env overrides.

Precedence (highest first): init kwargs > environment > `.env` > experiment YAML.
Model slugs live only in the YAML; code never hardcodes a model.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from routing_study.routers.calibration import Calibration, LogisticModel

FIXED_STRATEGIES: tuple[str, ...] = (
    "regex",
    "bm25",
    "embedding",
    "llm",
    "jev",
    "hybrid",
    "classifier",
)
# Extra LLM routers: any `strategies.llm_<suffix>` block (e.g. llm_local) is
# one more LLMRouter with its own model/provider; the name is the strategy name everywhere.
_EXTRA_LLM = re.compile(r"^llm(_[a-z0-9]+)+$")


def is_llm_strategy(name: str) -> bool:
    return name == "llm" or bool(_EXTRA_LLM.match(name))


def _strategy_name(name: str) -> str:
    if name in FIXED_STRATEGIES or _EXTRA_LLM.match(name):
        return name
    raise ValueError(f"unknown strategy {name!r}: {FIXED_STRATEGIES} or llm_<suffix>")


StrategyName = Annotated[str, AfterValidator(_strategy_name)]
Provider = Literal["openrouter", "bedrock", "ollama"]


class _Config(BaseModel):
    """Experiment config block: a misspelled key is an error, never silently dropped."""

    model_config = ConfigDict(extra="forbid")


class ProviderPrefs(_Config):
    """OpenRouter provider routing (`extra_body.provider`)."""

    order: list[str] | None = None
    allow_fallbacks: bool = True


class ReasoningPrefs(_Config):
    """OpenRouter `extra_body.reasoning`. Explicit on purpose: with structured output some models
    (e.g. anthropic/claude-sonnet-5) think by default, which silently changes cost, latency and
    the output budget of a router."""

    enabled: bool = False
    effort: Literal["low", "medium", "high"] | None = None
    max_tokens: int | None = Field(default=None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _effort_or_budget_enables(cls, data: Any) -> Any:
        """`effort` or `max_tokens` means reasoning ON (finding 5): never send
        {"enabled": false, "effort": ...}; and only one of the two."""
        if not isinstance(data, dict) or not (data.get("effort") or data.get("max_tokens")):
            return data
        if data.get("effort") and data.get("max_tokens"):
            raise ValueError("reasoning: set only one of effort / max_tokens")
        if data.get("enabled") is False:
            raise ValueError("reasoning: effort/max_tokens given with enabled=false")
        return {**data, "enabled": True}


class ModelEndpoint(_Config):
    """Where a model runs. `provider` picks the client (OpenRouter, AWS Bedrock Converse,
    local Ollama); `region` (Bedrock) and `base_url` (Ollama/OpenRouter) override the
    top-level defaults. `openrouter` = OpenRouter provider routing prefs.

    Legacy configs wrote the OpenRouter prefs as `provider: {order: [...]}`: still accepted."""

    model: str
    provider: Provider = "openrouter"
    region: str | None = None
    base_url: str | None = None
    openrouter: ProviderPrefs | None = None
    # Ollama context window. Its /v1 API ignores per-request options, so the model is served
    # as a derived tag `<model>-ctx<num_ctx>` (same weights, PARAMETER num_ctx), created on
    # preload. Bounds the KV cache: the default 32768 doubled resident memory.
    num_ctx: int | None = Field(default=None, ge=512)
    # Client-side requests-per-minute cap for THIS model id (Bedrock inference profile,
    # OpenRouter slug or Ollama name), shared by every role calling the same id. Operational,
    # not decision-shaping: excluded from dumps so it never changes a run's config hash.
    rpm_limit: int | None = Field(default=None, ge=1, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _legacy_provider_prefs(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("provider"), dict):
            if data.get("openrouter") is not None:
                raise ValueError("give OpenRouter prefs once: `openrouter:` (not `provider:`)")
            data = {**data, "openrouter": data["provider"], "provider": "openrouter"}
        return data

    @model_validator(mode="after")
    def _prefs_only_on_openrouter(self) -> ModelEndpoint:
        if self.openrouter is not None and self.provider != "openrouter":
            raise ValueError(f"`openrouter` prefs given for provider {self.provider!r}")
        if self.num_ctx is not None and self.provider != "ollama":
            raise ValueError(f"`num_ctx` is an Ollama setting (provider {self.provider!r})")
        return self

    @property
    def served_name(self) -> str:
        """The name requests use: the derived `-ctx<n>` tag when `num_ctx` is set."""
        return f"{self.model}-ctx{self.num_ctx}" if self.num_ctx else self.model


def _check_reasoning(
    model: str, temperature: float | None, max_tokens: int, reasoning: ReasoningPrefs
) -> None:
    """Finding 5: the thinking budget must leave room for the answer; finding 8: Anthropic
    models only accept temperature 1 (or unset) with thinking on."""
    if reasoning.max_tokens is not None and reasoning.max_tokens >= max_tokens:
        raise ValueError(
            f"reasoning budget {reasoning.max_tokens} must be < max_tokens {max_tokens}"
        )
    if reasoning.enabled and model.startswith("anthropic/") and temperature not in (None, 1):
        raise ValueError(
            f"{model}: temperature must be 1 or null with reasoning enabled (got {temperature})"
        )


class PipelineStep(_Config):
    strategy: StrategyName
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class StageConfig(_Config):
    pipeline: list[PipelineStep] = Field(default_factory=list)
    on_abstain: Literal["escalate", "native_agent"] = "escalate"
    expose_top_k: int = Field(default=2, ge=1)


class RoutingConfig(_Config):
    mode: Literal["native", "single", "cascade", "shadow"] = "cascade"
    skill: StageConfig = Field(default_factory=StageConfig)
    tool: StageConfig = Field(default_factory=StageConfig)
    # Extra strategies run (and only logged) in shadow mode, beyond the pipeline ones.
    shadow_strategies: list[StrategyName] = Field(default_factory=list)


Level = Literal["skill", "tool"]


class RegexStrategy(_Config):
    rules_path: str = "config/regex_rules.yaml"
    # extra rule files merged over `rules_path` (defs appended, rules appended per option id):
    # RQ5 leave-tools-out conditions (docs/rq5-design.md). Dumped only when set, so configs
    # without overlays keep their config hash.
    overlay_paths: list[str] = Field(default_factory=list, exclude_if=lambda v: not v)
    # score(message) + history_weight * score(last `history_turns` messages)
    history_turns: int = Field(default=0, ge=0)
    history_weight: float = Field(default=0.5, ge=0.0)
    # raw confidence -> P(correct) per level, fitted on dev folds (scripts/analysis/tune_router.py)
    calibration: dict[Level, Calibration] = Field(default_factory=dict)


class BM25FieldRepeats(_Config):
    """Times each catalog field's tokens appear in the option document (term-frequency
    weight; 0 drops the field)."""

    description: int = Field(default=1, ge=0)
    examples: int = Field(default=1, ge=0)
    keywords: int = Field(default=1, ge=0)


class BM25Strategy(_Config):
    k1: float = Field(default=1.5, ge=0.0)
    b: float = Field(default=0.75, ge=0.0, le=1.0)
    variant: Literal["okapi", "l"] = "okapi"  # l = rank_bm25's BM25L (IDF > 0 on tiny corpora)
    delta: float = Field(default=0.5, ge=0.0)  # BM25L only
    stemmer: Literal["none", "light", "prefix"] = "none"
    prefix_len: int = Field(default=5, ge=2)
    stopwords: Literal["basic", "extended"] = "basic"
    field_repeats: BM25FieldRepeats = Field(default_factory=BM25FieldRepeats)
    history_turns: int = Field(default=0, ge=0)
    history_weight: float = Field(default=0.5, ge=0.0)
    # utterance-level indexing (one document per catalog utterance; option score = max or
    # sum of its best `agg_k`), char n-gram analyzer, accent folding, deterministic
    # catalog-only expansion (shots = catalog examples resolved to the option; quotes = the
    # description's WHEN TO USE quotes)
    index: Literal["option", "utterance"] = "option"
    aggregate: Literal["max", "topk_sum"] = "max"
    agg_k: int = Field(default=2, ge=1)
    analyzer: Literal["word", "char"] = "word"
    ngram_min: int = Field(default=3, ge=1)
    ngram_max: int = Field(default=5, ge=1)
    fold_accents: bool = True
    shots: bool = False
    quotes: bool = False
    calibration: dict[Level, Calibration] = Field(default_factory=dict)


class EmbeddingStrategy(ModelEndpoint):
    similarity: Literal["max_example", "centroid", "topk_vote"] = "max_example"
    top_k: int = Field(default=5, ge=1)  # topk_vote only
    confidence: Literal["margin", "softmax"] = "softmax"
    softmax_temperature: float = Field(default=0.05, gt=0.0)
    margin_scale: float = Field(default=0.1, gt=0.0)
    # query = last `history_turns` messages + the message, concatenated
    history_turns: int = Field(default=0, ge=0)
    # option utterances also include the catalog examples resolved to the option
    shots: bool = False
    calibration: dict[Level, Calibration] = Field(default_factory=dict)
    # Instruction-aware embedders (e.g. Qwen3-Embedding) want the QUERY prefixed with the
    # task instruction and documents (option texts) embedded as-is. `{instruction}` is not
    # templated: the whole prefix is given, e.g. "Instruct: ...\nQuery:".
    query_instruction: str | None = None
    cache: bool = True


PromptTrack = Literal["canonical", "tuned"]


def _prompt_variant(name: str) -> str:
    from routing_study.prompts.routers import parse_variant

    parse_variant(name)  # unknown token -> ValueError
    return name


PromptVariant = Annotated[str, AfterValidator(_prompt_variant)]


class _RouterPrompt(_Config):
    """Router prompt (LLM and Jev): `prompt_variant` = `+`-joined tokens of
    src/routing_study/prompts/routers/variants.yaml. `prompt_track` labels where the variant
    comes from (docs/prompt-apex.md): canonical = one prompt for every LLM router, tuned =
    this model's own best variant on dev. `calibration`: raw confidence -> P(correct) per
    level, fitted on dev folds (scripts/analysis/tune_router.py --calibrate)."""

    prompt_track: PromptTrack = "canonical"
    prompt_variant: PromptVariant = "P0"
    calibration: dict[Level, Calibration] = Field(default_factory=dict)


class LLMStrategy(ModelEndpoint, _RouterPrompt):
    temperature: float | None = 0.0
    seed: int | None = None
    # self_reported: the model's `confidence` field; logprob: P(choice tokens) from the
    # token logprobs of the structured reply (providers that return logprobs: ollama)
    confidence: Literal["self_reported", "logprob"] = "self_reported"
    allow_abstain: bool = False
    history_turns: int = 4
    max_tokens: int = Field(default=512, ge=16)
    reasoning: ReasoningPrefs = Field(default_factory=ReasoningPrefs)
    cache: bool = True

    @model_validator(mode="after")
    def _reasoning_ok(self) -> LLMStrategy:
        _check_reasoning(self.model, self.temperature, self.max_tokens, self.reasoning)
        if self.confidence == "logprob" and self.provider != "ollama":
            raise ValueError("confidence: logprob needs a provider that returns logprobs (ollama)")
        return self


class JevStrategy(ModelEndpoint, _RouterPrompt):
    parse_retries: int = Field(default=1, ge=0)
    # Output cap: without it OpenRouter reserves the model's max (65536) against credits.
    max_tokens: int = Field(default=512, ge=16)
    allow_abstain: bool = False
    history_turns: int = 4
    # jev-router is non-deterministic: caching is off by default (3 repetitions required).
    cache: bool = False


class HybridStrategy(_Config):
    """Fusion of cheap routers (routers/hybrid.py). `convex`: weighted mean of calibrated
    per-option distributions (`alpha` = weight of members[0] with two members, or `weights`);
    `stacker`: per-level logistic model fitted on dev folds; `rrf`: rank fusion baseline."""

    fusion: Literal["rrf", "convex", "stacker"] = "convex"
    members: list[Literal["regex", "bm25", "embedding", "classifier"]] = Field(
        default_factory=lambda: ["bm25", "embedding"], min_length=1
    )
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    weights: dict[str, float] = Field(default_factory=dict)
    rrf_k: int = Field(default=60, ge=1)
    stacker: dict[Level, LogisticModel] = Field(default_factory=dict)
    calibration: dict[Level, Calibration] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _stacker_fitted(self) -> HybridStrategy:
        if self.fusion == "stacker" and not self.stacker:
            raise ValueError("hybrid fusion 'stacker' needs `stacker` models (fit_hybrid.py)")
        return self


class ClassifierStrategy(_Config):
    """Learned classifier on catalog text (routers/classifier.py): TF-IDF + LR, or a linear
    probe on the `embedding` strategy's frozen vectors."""

    model: Literal["tfidf_lr", "probe"] = "tfidf_lr"
    features: Literal["word", "char", "word+char"] = "word+char"
    word_ngrams: int = Field(default=2, ge=1)
    char_min: int = Field(default=2, ge=1)
    char_max: int = Field(default=5, ge=1)
    c: float = Field(default=10.0, gt=0.0)
    shots: bool = True
    quotes: bool = True
    description: bool = True
    history_turns: int = Field(default=0, ge=0)
    history_weight: float = Field(default=0.5, ge=0.0)
    probe_instruction: bool = False
    calibration: dict[Level, Calibration] = Field(default_factory=dict)


class StrategiesConfig(_Config):
    """Strategy name -> config. Fixed strategies are fields; extra LLM routers are
    `llm_<suffix>` keys, each validated as an `LLMStrategy` (any other extra key is an
    error, like everywhere else)."""

    model_config = ConfigDict(extra="allow")

    regex: RegexStrategy | None = None
    bm25: BM25Strategy | None = None
    embedding: EmbeddingStrategy | None = None
    llm: LLMStrategy | None = None
    jev: JevStrategy | None = None
    hybrid: HybridStrategy | None = None
    classifier: ClassifierStrategy | None = None

    @model_validator(mode="after")
    def _extra_llm_strategies(self) -> StrategiesConfig:
        extra = self.__pydantic_extra__ or {}
        for name, raw in extra.items():
            if not _EXTRA_LLM.match(name):
                raise ValueError(f"unknown strategy block {name!r} (extra LLMs: llm_<suffix>)")
            if raw is not None and not isinstance(raw, LLMStrategy):
                extra[name] = LLMStrategy.model_validate(raw)
        return self

    def llm_strategies(self) -> dict[str, LLMStrategy]:
        """Every configured LLM router: `llm` + the `llm_<suffix>` blocks."""
        out = {"llm": self.llm} if self.llm is not None else {}
        out.update({k: v for k, v in (self.__pydantic_extra__ or {}).items() if v is not None})
        return out

    def configured(self) -> list[str]:
        """Names of every configured strategy (fixed order, then extra LLMs)."""
        fixed = [n for n in FIXED_STRATEGIES if getattr(self, n) is not None]
        return fixed + [n for n in self.llm_strategies() if n != "llm"]

    def get(self, name: str) -> Any:
        return getattr(self, name, None)


class ExecutorConfig(ModelEndpoint):
    temperature: float | None = 0.0
    seed: int | None = None
    max_tool_iterations: int = 3
    max_tokens: int = Field(default=1024, ge=16)
    reasoning: ReasoningPrefs = Field(default_factory=ReasoningPrefs)

    @model_validator(mode="after")
    def _reasoning_ok(self) -> ExecutorConfig:
        _check_reasoning(self.model, self.temperature, self.max_tokens, self.reasoning)
        return self


class CatalogConfig(_Config):
    """Host-side view of the MCP catalog. `exclude_tools` drops tools after the server fetch
    (RQ5 leave-tools-out, docs/rq5-design.md); the MCP server itself is never changed."""

    exclude_tools: list[str] = Field(default_factory=list)


class BudgetConfig(_Config):
    """Hard spend caps per billing account, enforced from a persistent append-only ledger
    (`study budget` prints it). `prices_path`: per-token prices of providers that do not
    report a cost (Bedrock); local models cost 0 but are still recorded."""

    aws_usd_cap: float = Field(default=90.0, ge=0.0)
    openrouter_usd_cap: float = Field(default=9.0, ge=0.0)
    ledger_path: str = "results/spend_ledger.jsonl"
    prices_path: str = "config/prices.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_ignore_empty=True,  # a blank `KEY=` line means unset, not ""
        extra="ignore",
    )

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    bedrock_region: str = "sa-east-1"  # AWS credentials: the default boto3 chain, never here
    ollama_base_url: str = "http://localhost:11434/v1"
    # Local models Ollama keeps loaded at once (run the server with the same
    # OLLAMA_MAX_LOADED_MODELS). Shadow runs only add local LLM routers when all local models
    # of the pass fit; otherwise those routers get their own routing-only runs (e6b).
    ollama_max_loaded_models: int = Field(default=1, ge=1)
    # Requests the local server runs at once (OLLAMA_NUM_PARALLEL): callers queue client-side
    # beyond it, so the wait is reported as queue_ms and not as model latency.
    ollama_num_parallel: int = Field(default=1, ge=1)
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None
    mcp_url: str = "http://localhost:8765/mcp"
    mcp_token: SecretStr | None = None
    redis_url: str | None = None  # app Redis: MCP catalog cache + LangGraph checkpointer

    experiment_id: str = "adhoc"
    cache_dir: str = ".cache"
    max_concurrency_per_provider: int = Field(default=8, ge=1)
    http_retries: int = Field(default=3, ge=0)
    # Client-side requests-per-minute caps per model id (any provider: OpenRouter slug,
    # Bedrock id, Ollama name). A model block's own `rpm_limit` is merged in (min wins).
    rpm_limits: dict[str, int] = Field(
        default_factory=lambda: {"anthropic/claude-sonnet-5": 18, "anthropic/claude-sonnet-5.5": 18}
    )
    max_rate_limit_wait_s: float = 65.0
    # Throttling / capacity errors (Bedrock ThrottlingException, ServiceUnavailable,
    # ModelNotReady, ModelTimeout; HTTP 429/503) are retried with jittered exponential backoff
    # until this many seconds have passed since the first attempt (`http_retries` bounds the
    # other transient errors only).
    throttle_retry_budget_s: float = Field(default=180.0, ge=0.0)
    throttle_backoff_initial_s: float = Field(default=1.0, gt=0.0)
    throttle_backoff_max_s: float = Field(default=30.0, gt=0.0)
    request_timeout_s: float = 60.0

    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    strategies: StrategiesConfig = Field(default_factory=StrategiesConfig)
    executor: ExecutorConfig | None = None
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources = [init_settings, env_settings, dotenv_settings]
        if settings_cls.model_config.get("yaml_file"):
            sources.append(YamlConfigSettingsSource(settings_cls))
        return tuple(sources)


_LIST_FIELDS = {"pipeline", "shadow_strategies", "order"}
_NESTED_ENV = re.compile(r"^(ROUTING|STRATEGIES|EXECUTOR)__(.+)$", re.IGNORECASE)


def _nested_env_overrides(env_file: str | None) -> list[tuple[list[str], Any]]:
    """Collect `ROUTING__…`/`STRATEGIES__…`/`EXECUTOR__…` vars from `.env` then the environment.

    pydantic-settings' native `__` nesting cannot address list items by index
    (ROUTING__SKILL__PIPELINE__0__MIN_CONFIDENCE=0.95), so these are patched into the YAML.
    """
    from dotenv import dotenv_values

    merged: dict[str, Any] = {}
    if env_file and Path(env_file).exists():
        merged.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    merged.update(os.environ)
    out: list[tuple[list[str], Any]] = []
    for key, raw in merged.items():
        m = _NESTED_ENV.match(key)
        if not m:
            continue
        if raw is None or raw == "":  # blank = unset (and "" would crash json.loads)
            continue
        value: Any = raw
        if isinstance(raw, str) and raw[0] in "[{":
            value = json.loads(raw)
        out.append(([m.group(1).lower(), *m.group(2).lower().split("__")], value))
    return out


def _set_path(root: Any, path: list[str], value: Any) -> None:
    node = root
    for i, part in enumerate(path):
        last = i == len(path) - 1
        if isinstance(node, list):
            idx = int(part)
            while len(node) <= idx:
                node.append({})
            if last:
                node[idx] = value
            else:
                if not isinstance(node[idx], dict | list):
                    node[idx] = {}
                node = node[idx]
        else:
            if last:
                node[part] = value
            else:
                nxt = path[i + 1]
                if part not in node or not isinstance(node[part], dict | list):
                    node[part] = [] if nxt.isdigit() or part in _LIST_FIELDS else {}
                node = node[part]


def _yaml_data(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_settings(
    experiment: str | Path | None = None,
    *,
    patches: dict[str, Any] | None = None,
    **overrides: Any,
) -> Settings:
    """Build settings for one experiment YAML (or env/.env only when `experiment` is None).

    `patches`: `{"dotted.key.path": value}` applied over the YAML after the env patches (a
    manifest entry's `overrides`, e.g. `catalog.exclude_tools` for the RQ5 conditions)."""
    if experiment is None:
        return Settings(**overrides)
    path = Path(experiment)
    if not path.exists():
        raise FileNotFoundError(f"experiment config not found: {path}")

    class _ExperimentSettings(Settings):
        model_config = SettingsConfigDict(**{**Settings.model_config, "yaml_file": str(path)})

    # B11: the top level ignores unknown ENV keys (the process env is full of them) but a
    # misspelled YAML key (`strategys:`) must fail, like every nested block does
    unknown = sorted(set(_yaml_data(path)) - set(Settings.model_fields))
    if unknown:
        raise ValueError(f"{path}: unknown top-level key(s) {unknown}")
    env_file = Settings.model_config.get("env_file")
    env_patches = _nested_env_overrides(env_file if isinstance(env_file, str) else None)
    bad = sorted(k for k in patches or {} if k.split(".")[0] not in Settings.model_fields)
    if bad:  # the top level ignores unknown keys: a misspelled patch must not be dropped
        raise ValueError(f"unknown settings patch key(s) {bad}")
    env_patches += [(k.split("."), v) for k, v in (patches or {}).items()]
    if env_patches:
        # Patch env values (incl. list indexes) into the YAML base and pass as init kwargs.
        data = _yaml_data(path)
        for key_path, value in env_patches:
            _set_path(data, key_path, value)
        for top in {p[0] for p, _ in env_patches}:
            overrides.setdefault(top, data.get(top))
    overrides.setdefault("experiment_id", path.stem)
    return _ExperimentSettings(**overrides)
