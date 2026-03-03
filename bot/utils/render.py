from typing import Any, Dict, List

def _fmt_num(x: Any) -> str:
    try:
        n = float(x)
        if n.is_integer():
            return str(int(n))
        return f"{n:.2f}".rstrip("0").rstrip(".")
    except Exception:
        return str(x)

def render_plan_first(payload: Dict[str, Any], ticker: str) -> str:
    p = payload.get("payload") or payload
    # structure payload might be nested in {"payload": {...}} already
    pp = p.get("payload") or p

    tf = pp.get("tf", "4H")
    regime = pp.get("regime", "UNKNOWN")
    r = pp.get("range") or {}
    lv = pp.get("levels") or {}
    long = (lv.get("long") or {})
    short = (lv.get("short") or {})
    vp = pp.get("vp") or {}
    buf = pp.get("buffers") or {}

    lines: List[str] = []
    lines.append(f"📌 {ticker} • TF={tf} • Regime={regime}")
    if r.get("low") is not None and r.get("high") is not None:
        lines.append(f"Range: {_fmt_num(r['low'])} .. {_fmt_num(r['high'])}")
    lines.append(f"LONG: trig>{_fmt_num(long.get('trigger'))} • inv<{_fmt_num(long.get('invalid'))}")
    lines.append(f"SHORT: trig<{_fmt_num(short.get('trigger'))} • inv>{_fmt_num(short.get('invalid'))}")

    trig = (buf.get("trig") or {})
    inv = (buf.get("inv") or {})
    lines.append(f"Buffers: trig={_fmt_num(trig.get('value'))} (x{_fmt_num(trig.get('atr_mult'))}) • inv={_fmt_num(inv.get('value'))} (x{_fmt_num(inv.get('atr_mult'))})")
    lines.append(f"VP: POC={_fmt_num(vp.get('poc'))} • LVN={(vp.get('lvn') or [])[:6]}")

    return "\n".join(lines)

def render_ai_block(raw: Dict[str, Any]) -> str:
    analysis = (raw.get("raw") or {}).get("analysis") or raw.get("analysis") or {}
    ai = analysis.get("ai") or {}
    on = ai.get("on", False)
    if on:
        header = f"🤖 AI: ON • {ai.get('provider','?')} • {ai.get('model','?')}"
    else:
        header = f"🤖 AI: OFF • {ai.get('reason','unknown')}"

    val = analysis.get("value") or analysis  # depending on your final shape
    kp = val.get("key_points") or []
    interp = val.get("interpretation") or []
    align = val.get("alignment") or []
    sc = val.get("scenarios") or []
    conf = val.get("confidence") or {}

    lines: List[str] = [header]
    if kp:
        lines.append("— Key points —")
        for x in kp[:4]:
            lines.append(f"• {x}")
    if interp:
        lines.append("— Interpretation —")
        for x in interp[:3]:
            lines.append(f"• {x}")
    if align:
        lines.append("— Alignment —")
        for x in align[:4]:
            lines.append(f"• {x}")
    if sc:
        lines.append("— Scenarios —")
        for s in sc[:3]:
            lines.append(f"{s.get('name','?')}")
            lines.append(f"IF: {s.get('if','')}")
            for t in (s.get('then') or [])[:3]:
                lines.append(f"• {t}")
            lines.append(f"INV: {s.get('invalidation','')}")
    if conf:
        lines.append(f"Confidence: {conf.get('level','?')} • {conf.get('reason','')}")
    return "\n".join(lines)

def chunk_text(text: str, max_len: int = 3500) -> List[str]:
    # Telegram safe chunks (plain text)
    text = (text or "").strip()
    if len(text) <= max_len:
        return [text]
    out: List[str] = []
    buf: List[str] = []
    cur = 0
    for line in text.splitlines(True):
        if cur + len(line) > max_len and buf:
            out.append("".join(buf).rstrip())
            buf = []
            cur = 0
        buf.append(line)
        cur += len(line)
    if buf:
        out.append("".join(buf).rstrip())
    return out
