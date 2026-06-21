from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DATASET_NAME = "Indian_Investment_Intelligence_100000_Prompts.jsonl"


@dataclass(frozen=True)
class PromptDatasetRecord:
    id: str
    asset_class: str
    domain: str
    market: str
    time_horizon: str
    risk_level: str
    primary_event_or_driver: str
    recommended_agents: tuple[str, ...]
    required_indicators: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    prompt: str
    response_schema: dict[str, Any]
    safety_note: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptDatasetRecord":
        return cls(
            id=str(data.get("id", "")),
            asset_class=str(data.get("asset_class", "")),
            domain=str(data.get("domain", "")),
            market=str(data.get("market", "")),
            time_horizon=str(data.get("time_horizon", "")),
            risk_level=str(data.get("risk_level", "")),
            primary_event_or_driver=str(data.get("primary_event_or_driver", "")),
            recommended_agents=tuple(str(item) for item in data.get("recommended_agents", ()) or ()),
            required_indicators=tuple(str(item) for item in data.get("required_indicators", ()) or ()),
            expected_outputs=tuple(str(item) for item in data.get("expected_outputs", ()) or ()),
            prompt=str(data.get("prompt", "")),
            response_schema=dict(data.get("response_schema", {}) or {}),
            safety_note=str(data.get("safety_note", "")),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asset_class": self.asset_class,
            "domain": self.domain,
            "market": self.market,
            "time_horizon": self.time_horizon,
            "risk_level": self.risk_level,
            "primary_event_or_driver": self.primary_event_or_driver,
            "recommended_agents": list(self.recommended_agents),
            "required_indicators": list(self.required_indicators),
            "expected_outputs": list(self.expected_outputs),
            "prompt": self.prompt,
            "response_schema": self.response_schema,
            "safety_note": self.safety_note,
        }


def default_dataset_path() -> Path | None:
    env_path = os.environ.get("INDIAN_INVESTMENT_PROMPTS_JSONL")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    downloads_path = Path.home() / "Downloads" / DEFAULT_DATASET_NAME
    if downloads_path.exists():
        return downloads_path
    resource_path = Path(__file__).resolve().parents[1] / "resources" / DEFAULT_DATASET_NAME
    if resource_path.exists():
        return resource_path
    return None


def resolve_dataset_path(path: str | Path | None = None) -> Path:
    resolved = Path(path) if path else default_dataset_path()
    if resolved is None or not resolved.exists():
        raise FileNotFoundError(
            "Prompt dataset not found. Pass --prompt-dataset or set INDIAN_INVESTMENT_PROMPTS_JSONL."
        )
    return resolved


def iter_prompt_records(path: str | Path | None = None, limit: int | None = None) -> Iterable[PromptDatasetRecord]:
    dataset_path = resolve_dataset_path(path)
    with dataset_path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle, start=1):
            if limit is not None and index > limit:
                break
            if not line.strip():
                continue
            try:
                yield PromptDatasetRecord.from_dict(json.loads(line))
            except json.JSONDecodeError:
                continue


def summarize_prompt_dataset(path: str | Path | None = None, limit: int | None = None) -> dict[str, Any]:
    counters = {
        "asset_class": Counter(),
        "domain": Counter(),
        "market": Counter(),
        "time_horizon": Counter(),
        "risk_level": Counter(),
        "primary_event_or_driver": Counter(),
        "recommended_agents": Counter(),
        "required_indicators": Counter(),
        "expected_outputs": Counter(),
    }
    record_count = 0
    for record in iter_prompt_records(path, limit):
        record_count += 1
        counters["asset_class"][record.asset_class] += 1
        counters["domain"][record.domain] += 1
        counters["market"][record.market] += 1
        counters["time_horizon"][record.time_horizon] += 1
        counters["risk_level"][record.risk_level] += 1
        counters["primary_event_or_driver"][record.primary_event_or_driver] += 1
        counters["recommended_agents"].update(record.recommended_agents)
        counters["required_indicators"].update(record.required_indicators)
        counters["expected_outputs"].update(record.expected_outputs)
    return {
        "dataset_path": str(resolve_dataset_path(path)),
        "record_count": record_count,
        "top_asset_classes": _top(counters["asset_class"], 12),
        "top_domains": _top(counters["domain"], 12),
        "top_markets": _top(counters["market"], 12),
        "top_time_horizons": _top(counters["time_horizon"], 12),
        "top_risk_levels": _top(counters["risk_level"], 12),
        "top_events_or_drivers": _top(counters["primary_event_or_driver"], 12),
        "top_agents": _top(counters["recommended_agents"], 12),
        "top_required_indicators": _top(counters["required_indicators"], 16),
        "top_expected_outputs": _top(counters["expected_outputs"], 16),
    }


def search_prompt_dataset(
    query: str,
    path: str | Path | None = None,
    *,
    asset_class: str | None = None,
    domain: str | None = None,
    risk_level: str | None = None,
    limit: int = 10,
    scan_limit: int | None = None,
) -> list[dict[str, Any]]:
    query_terms = _terms(query)
    scored: list[tuple[int, PromptDatasetRecord]] = []
    for record in iter_prompt_records(path, scan_limit):
        if asset_class and not _matches_asset_filter(asset_class, record.asset_class):
            continue
        if domain and domain.lower() not in record.domain.lower():
            continue
        if risk_level and risk_level.lower() not in record.risk_level.lower():
            continue
        searchable = " ".join(
            [
                record.asset_class,
                record.domain,
                record.market,
                record.time_horizon,
                record.risk_level,
                record.primary_event_or_driver,
                " ".join(record.recommended_agents),
                " ".join(record.required_indicators),
                " ".join(record.expected_outputs),
                record.prompt,
            ]
        )
        score = _score(query_terms, searchable) + _field_boost(query_terms, record)
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"score": score, **record.to_public_dict()}
        for score, record in scored[: max(1, limit)]
    ]


def enhance_prompt_from_dataset(
    user_prompt: str,
    path: str | Path | None = None,
    *,
    limit: int = 5,
    scan_limit: int | None = None,
) -> dict[str, Any]:
    inferred_asset = _infer_asset_class(user_prompt)
    matches = search_prompt_dataset(
        user_prompt,
        path,
        asset_class=inferred_asset,
        limit=limit,
        scan_limit=scan_limit,
    )
    indicators = _unique_from_matches(matches, "required_indicators")
    outputs = _unique_from_matches(matches, "expected_outputs")
    agents = _unique_from_matches(matches, "recommended_agents")
    response_schema = matches[0].get("response_schema", {}) if matches else {}
    enhanced_prompt = _build_enhanced_prompt(user_prompt, agents, indicators, outputs)
    return {
        "original_prompt": user_prompt,
        "enhanced_prompt": enhanced_prompt,
        "recommended_agents": agents,
        "required_indicators": indicators,
        "expected_outputs": outputs,
        "response_schema": response_schema,
        "matched_training_prompts": matches,
        "safety_note": (
            "Training prompts improve structure only. Live decisions must still use realtime market data, "
            "official sources, and risk controls."
        ),
    }


def export_training_sample(
    output_path: str | Path,
    path: str | Path | None = None,
    *,
    sample_size: int = 1000,
    scan_limit: int | None = None,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for record in iter_prompt_records(path, scan_limit):
            item = {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an Indian Investment Intelligence research assistant. "
                            "Use official/realtime data, distinguish actual data from forecasts, "
                            "return structured risk-aware output, and never guarantee future prices."
                        ),
                    },
                    {"role": "user", "content": record.prompt},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "summary": "Use realtime and official data before answering this investment research query.",
                                "data_sources_to_check": _data_sources_for_record(record),
                                "bullish_factors": [],
                                "bearish_factors": [],
                                "risk_factors": list(record.required_indicators[:5]),
                                "decision": "WATCHLIST",
                                "confidence_score_0_100": 0,
                                "risk_score_0_100": 0,
                                "time_horizon": record.time_horizon,
                                "disclaimer": record.safety_note,
                            },
                            ensure_ascii=True,
                        ),
                    },
                ],
                "metadata": {
                    "id": record.id,
                    "asset_class": record.asset_class,
                    "domain": record.domain,
                    "risk_level": record.risk_level,
                    "recommended_agents": list(record.recommended_agents),
                },
            }
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")
            count += 1
            if count >= sample_size:
                break
    return destination.resolve()


def _build_enhanced_prompt(
    user_prompt: str,
    agents: list[str],
    indicators: list[str],
    outputs: list[str],
) -> str:
    return "\n".join(
        [
            user_prompt.strip(),
            "",
            "Institutional research instructions:",
            f"- Use these specialist agents: {', '.join(agents[:6]) or 'Macro Agent, News Agent, Risk Agent'}.",
            f"- Validate with these indicators: {', '.join(indicators[:10]) or 'price trend, volume, volatility, news sentiment, official data'}.",
            f"- Return these outputs: {', '.join(outputs[:10]) or 'Buy/Hold/Sell, confidence score, risk score, target range, reasons, sources'}.",
            "- Separate current/historical facts from future forecast estimates.",
            "- Include bull, base, and bear cases with probability, risk controls, source URLs, and a clear safety note.",
        ]
    )


def _data_sources_for_record(record: PromptDatasetRecord) -> list[str]:
    sources = ["NSE", "BSE", "SEBI", "RBI", "MOSPI", "Ministry of Finance"]
    if any(term.lower() in record.asset_class.lower() for term in ("gold", "silver", "crude", "petrol", "diesel")):
        sources.extend(["MCX", "PPAC", "OPEC", "World Bank", "IMF"])
    return sources


def _unique_from_matches(matches: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for match in matches:
        for value in match.get(key, []) or []:
            normalized = " ".join(str(value).split())
            if normalized and normalized.lower() not in seen:
                seen.add(normalized.lower())
                values.append(normalized)
    return values


def _score(query_terms: set[str], text: str) -> int:
    text_terms = _terms(text)
    overlap = len(query_terms & text_terms)
    phrase_bonus = sum(3 for term in query_terms if len(term) > 4 and term in text.lower())
    return overlap * 4 + phrase_bonus


def _field_boost(query_terms: set[str], record: PromptDatasetRecord) -> int:
    boost = 0
    if "intraday" in query_terms and record.time_horizon.lower() == "intraday":
        boost += 35
    if "intraday" in query_terms and "intraday" in record.domain.lower():
        boost += 20
    weighted_fields = (
        (record.asset_class, 6),
        (record.domain, 8),
        (record.time_horizon, 8),
        (record.risk_level, 4),
        (record.primary_event_or_driver, 4),
    )
    for value, weight in weighted_fields:
        if query_terms & _terms(value):
            boost += weight
    for output in record.expected_outputs:
        if query_terms & _terms(output):
            boost += 3
    for indicator in record.required_indicators:
        if query_terms & _terms(indicator):
            boost += 2
    return boost


def _matches_asset_filter(filter_value: str, asset_class: str) -> bool:
    normalized_filter = _normalize_asset(filter_value)
    normalized_asset = _normalize_asset(asset_class)
    if normalized_filter in normalized_asset or normalized_asset in normalized_filter:
        return True
    synonyms = {
        "stock": {"stock", "nse stock", "bse stock", "equity", "share"},
        "stocks": {"stock", "nse stock", "bse stock", "equity", "share"},
        "mutual fund": {"mutual fund", "mutual funds", "sip"},
        "mutual funds": {"mutual fund", "mutual funds", "sip"},
        "gold": {"gold"},
        "silver": {"silver"},
        "crude oil": {"crude oil", "oil", "petrol", "diesel"},
        "oil": {"crude oil", "oil", "petrol", "diesel"},
        "real estate": {"real estate", "reit", "property"},
    }
    return normalized_asset in synonyms.get(normalized_filter, set())


def _infer_asset_class(prompt: str) -> str | None:
    normalized = prompt.lower()
    ordered = (
        ("gold", "Gold"),
        ("silver", "Silver"),
        ("mutual fund", "Mutual Fund"),
        ("sip", "Mutual Fund"),
        ("intraday", "Stocks"),
        ("stock", "Stocks"),
        ("share", "Stocks"),
        ("nse", "Stocks"),
        ("bse", "Stocks"),
        ("crude", "Crude Oil"),
        ("oil", "Crude Oil"),
        ("petrol", "Petrol"),
        ("diesel", "Diesel"),
        ("reit", "REIT"),
        ("real estate", "Real Estate"),
    )
    for needle, asset in ordered:
        if needle in normalized:
            return asset
    return None


def _normalize_asset(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    if value.endswith("s") and value not in {"bse", "nse"}:
        value = value[:-1]
    return value


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", value.lower())
        if len(token) > 2 and token not in {"the", "and", "for", "with", "from", "this", "that"}
    }


def _top(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in counter.most_common(limit)
        if name
    ]
