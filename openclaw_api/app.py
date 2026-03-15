from fastapi import FastAPI
from pydantic import BaseModel
import os

from openclaw_api import mexc
from typing import Optional, Dict, Any

from openclaw_api.routes.mexc_spot import router as mexc_spot_router
from openclaw_api.routes.dexter_proxy import router as dexter_router
from openclaw_api.routes.plan import router as plan_router
from openclaw_api.routes.plan_v2 import router as plan_v2_router
from openclaw_api.routes.bias_v1 import router as bias_router
from openclaw_api.routes.plan_v3 import router as plan_v3_router
from openclaw_api.routes.market_top import router as market_router
from openclaw_api.routes.market_scan import router as market_scan_router
from openclaw_api.routes.insight import router as insight_router
app = FastAPI(title="OpenClaw API")
app.include_router(market_scan_router)
app.include_router(market_router)
app.include_router(plan_v3_router)
app.include_router(bias_router)
app.include_router(plan_v2_router)
app.include_router(plan_router)
app.include_router(mexc_spot_router)
app.include_router(dexter_router)
app.include_router(insight_router)

@app.get("/health")
def health():
    return {"ok": True, "build": (os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_SHA") or "unknown")}
@app.get("/")
def root():
    return {"ok": True, "service": "openclaw_api"}

class ChatReq(BaseModel):
    text: str
    user_id: Optional[int] = None
    symbol: str = "BTC_USDT"

class PlanReq(BaseModel):
    symbol: str = "BTC_USDT"
    deposit: float = 3000
    risk: float = 1.0
    lev: float = 20
    margin: str = "cross"
    intent: str = "plan"

@app.post("/chat")
def chat(req: ChatReq) -> Dict[str, Any]:
    return {
        "ok": True,
        "answer_html": (
            "🧠 <b>Контекст</b>\n"
            f"Ты спросил: <b>{req.text}</b>\n\n"
            "Пока это заглушка. Дальше подключим MEXC + анализ."
        )
    }

@app.post("/plan")
def plan(req: PlanReq) -> Dict[str, Any]:
    msg = (
        f"📌 <b>{req.symbol}</b>\n"
        f"🧠 Контекст: депо {req.deposit}, риск {req.risk}%, плечо {req.lev}x, {req.margin}\n\n"
        "🟥 <b>SHORT</b>: (заглушка)\n"
        "🟩 <b>LONG</b>: (заглушка)\n\n"
        "🎯 <b>Вердикт</b>: позже будет реальный\n"
        "🚨 <b>Риск-правило</b>: стоп обязателен.\n"
    )
    return {"ok": True, "message_html": msg}


@app.get("/mexc/symbols")
def mexc_symbols(limit: int = 2000):
    symbols, _raw = mexc.load_symbols(force=False)
    arr = sorted(list(symbols))
    return {"ok": True, "count": len(arr), "symbols": arr[: int(limit)]}

@app.get("/mexc/resolve")
def mexc_resolve(input: str):
    sym = mexc.resolve_symbol(input)
    return {"ok": True, "input": input, "symbol": sym}

