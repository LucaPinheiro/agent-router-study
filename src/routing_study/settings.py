"""Experiment settings: `.env` secrets + per-experiment YAML + `__`-nested env overrides.

Precedence (highest first): init kwargs > environment > `.env` > experiment YAML.
Model slugs live only in the YAML; code never hardcodes a model.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

StrategyName = Literal["regex", "bm25", "embedding", "llm", "jev", "hybrid"]


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


class RegexStrategy(_Config):
    rules_path: str = "config/regex_rules.yaml"


class BM25Strategy(_Config):
    k1: float = 1.5
    b: float = 0.75


class EmbeddingStrategy(_Config):
    model: str
    similarity: Literal["max_example", "centroid"] = "max_example"
    confidence: Literal["margin", "softmax"] = "softmax"
    softmax_temperature: float = Field(default=0.05, gt=0.0)
    margin_scale: float = Field(default=0.1, gt=0.0)
    provider: ProviderPrefs | None = None
    cache: bool = True


class LLMStrategy(_Config):
    model: str
    temperature: float | None = 0.0
    seed: int | None = None
    confidence: Literal["self_reported"] = "self_reported"
    allow_abstain: bool = False
    history_turns: int = 4
    max_tokens: int = Field(default=512, ge=16)
    reasoning: ReasoningPrefs = Field(default_factory=ReasoningPrefs)
    provider: ProviderPrefs | None = None
    cache: bool = True

    @model_validator(mode="after")
    def _reasoning_ok(self) -> LLMStrategy:
        _check_reasoning(self.model, self.temperature, self.max_tokens, self.reasoning)
        return self


class JevStrategy(_Config):
    model: str
    parse_retries: int = Field(default=1, ge=0)
    # Output cap: without it OpenRouter reserves the model's max (65536) against credits.
    max_tokens: int = Field(default=512, ge=16)
    allow_abstain: bool = False
    history_turns: int = 4
    provider: ProviderPrefs | None = None
    # jev-router is non-deterministic: caching is off by default (3 repetitions required).
    cache: bool = False


class HybridStrategy(_Config):
    rrf_k: int = Field(default=60, ge=1)


class StrategiesConfig(_Config):
    regex: RegexStrategy | None = None
    bm25: BM25Strategy | None = None
    embedding: EmbeddingStrategy | None = None
    llm: LLMStrategy | None = None
    jev: JevStrategy | None = None
    hybrid: HybridStrategy | None = None


class ExecutorConfig(_Config):
    model: str
    temperature: float | None = 0.0
    seed: int | None = None
    max_tool_iterations: int = 3
    max_tokens: int = Field(default=1024, ge=16)
    reasoning: ReasoningPrefs = Field(default_factory=ReasoningPrefs)
    provider: ProviderPrefs | None = None

    @model_validator(mode="after")
    def _reasoning_ok(self) -> ExecutorConfig:
        _check_reasoning(self.model, self.temperature, self.max_tokens, self.reasoning)
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_ignore_empty=True,  # a blank `KEY=` line means unset, not ""
        extra="ignore",
    )

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
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
    # Client-side requests-per-minute caps per model slug (OpenRouter new-account limits).
    rpm_limits: dict[str, int] = Field(
        default_factory=lambda: {"anthropic/claude-sonnet-5": 18, "anthropic/claude-sonnet-5.5": 18}
    )
    max_rate_limit_wait_s: float = 65.0
    request_timeout_s: float = 60.0

    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    strategies: StrategiesConfig = Field(default_factory=StrategiesConfig)
    executor: ExecutorConfig | None = None

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


def load_settings(experiment: str | Path | None = None, **overrides: Any) -> Settings:
    """Build settings for one experiment YAML (or env/.env only when `experiment` is None)."""
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
    if env_patches:
        # Patch env values (incl. list indexes) into the YAML base and pass as init kwargs.
        data = _yaml_data(path)
        for key_path, value in env_patches:
            _set_path(data, key_path, value)
        for top in {p[0] for p, _ in env_patches}:
            overrides.setdefault(top, data.get(top))
    overrides.setdefault("experiment_id", path.stem)
    return _ExperimentSettings(**overrides)
