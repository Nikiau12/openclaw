from typing import Any


def _fmt_num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except Exception:
        return "N/A"


def _direction_from_change(change_pct: Any) -> str:
    try:
        x = float(change_pct)
    except Exception:
        return "Mixed"
    if x > 0:
        return "Up"
    if x < 0:
        return "Down"
    return "Mixed"


def _range_note(change_pct: Any) -> str:
    try:
        x = abs(float(change_pct))
    except Exception:
        return "Normal"
    if x >= 8:
        return "Sharp expansion"
    if x >= 4:
        return "Expanded"
    if x >= 2:
        return "Moderate expansion"
    return "Normal"


def _volume_note(spike: Any) -> str:
    try:
        x = float(spike)
    except Exception:
        return "N/A"
    if x >= 4:
        return "Very strong"
    if x >= 3:
        return "Strong"
    if x >= 2:
        return "Above average"
    return "Moderate"


def _comment(item: dict[str, Any]) -> str:
    direction = _direction_from_change(item.get("change_pct_24h"))
    spike = float(item.get("volume_spike", 0) or 0)
    if direction == "Up" and spike >= 3:
        return "breakout candidate with active participation"
    if direction == "Down" and spike >= 3:
        return "sell-off pressure is active, watch for continuation"
    if direction == "Up":
        return "momentum is improving, watch for continuation"
    if direction == "Down":
        return "weak structure, watch for retest failure"
    return "active but less directional structurally"


def format_scan_message(data: dict[str, Any]) -> str:
    tf = str(data.get("tf") or "15m")
    mode = str(data.get("mode") or "scan")
    items = data.get("items") or []

    if not items:
        return (
            f"⚡ OpenClaw Scan — {tf}\n\n"
            f"Scan Mode:\n"
            f"Market is quiet or below current scan thresholds.\n\n"
            f"Final Summary:\n"
            f"No strong volatility candidates passed the current filters."
        )

    if mode == "volume_spike":
        scan_mode = "Market is active with selective volume-driven moves."
    else:
        scan_mode = "Market snapshot based on filtered tickers."

    lines: list[str] = [
        f"⚡ OpenClaw Scan — {tf}",
        "",
        "Scan Mode:",
        scan_mode,
        "",
    ]

    for idx, item in enumerate(items[:5], start=1):
        symbol = str(item.get("symbol") or "UNKNOWN")
        direction = _direction_from_change(item.get("change_pct_24h"))
        range_note = _range_note(item.get("change_pct_24h"))
        vol_note = _volume_note(item.get("volume_spike"))
        comment = _comment(item)

        lines.extend(
            [
                f"{idx}. {symbol}",
                f"- Direction: {direction}",
                f"- Range: {range_note}",
                f"- Volume: {vol_note}",
                f"- Comment: {comment}",
                "",
            ]
        )

    lines.extend(
        [
            "Final Summary:",
            "The scan highlights the most active symbols by current filters. Best opportunities are usually in names with both expansion and volume confirmation.",
        ]
    )

    return "\n".join(lines).strip()
