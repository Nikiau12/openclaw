from typing import Any


def _as_text(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _format_targets(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
        return " / ".join(items) if items else "N/A"
    return _as_text(value)


def _format_why(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "- No strong reasons available."
    clean_items = [str(item).strip() for item in items if str(item).strip()]
    if not clean_items:
        return "- No strong reasons available."
    return "\n".join(f"- {item}" for item in clean_items)


def format_analyze_message(data: dict[str, Any]) -> str:
    symbol = _as_text(data.get("symbol"), "UNKNOWN")
    summary = _as_text(data.get("summary"), "No summary available.")
    bias = _as_text(data.get("bias"), "Neutral")
    why = _format_why(data.get("why"))

    levels = data.get("key_levels") or {}
    bullish = data.get("bullish_scenario") or {}
    bearish = data.get("bearish_scenario") or {}

    support = _as_text(levels.get("support"))
    resistance = _as_text(levels.get("resistance"))
    breakout = _as_text(levels.get("breakout_trigger"))
    breakdown = _as_text(levels.get("breakdown_trigger"))

    bullish_entry = _as_text(bullish.get("entry_logic"))
    bullish_invalidation = _as_text(bullish.get("invalidation"))
    bullish_targets = _format_targets(bullish.get("targets"))

    bearish_entry = _as_text(bearish.get("entry_logic"))
    bearish_invalidation = _as_text(bearish.get("invalidation"))
    bearish_targets = _format_targets(bearish.get("targets"))

    news_context = _as_text(data.get("news_context"), "No relevant news context.")
    risk_note = _as_text(data.get("risk_note"), "No major risk note.")

    return f"""🧠 OpenClaw Analysis — {symbol}

Summary:
{summary}

Bias:
{bias}

Why:
{why}

Key Levels:
- Support: {support}
- Resistance: {resistance}
- Breakout trigger: {breakout}
- Breakdown trigger: {breakdown}

Bullish Scenario:
- Entry logic: {bullish_entry}
- Invalidation: {bullish_invalidation}
- Targets: {bullish_targets}

Bearish Scenario:
- Entry logic: {bearish_entry}
- Invalidation: {bearish_invalidation}
- Targets: {bearish_targets}

News Context:
{news_context}

Risk Note:
{risk_note}
""".strip()