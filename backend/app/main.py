import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import field_validator, BaseModel, Field
from sqlalchemy.orm import Session

import threading

from . import audit, chat_cache, config, copilot, evidence, feedback, guardrails
from .ratelimit import chat_rate_limit
from .db import Base, engine, get_session
from .readers import ClientNotFound, ClientReader, PortfolioReader


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    threading.Thread(target=guardrails.warm_up, name="guardrails-warmup", daemon=True).start()   # build the rails off the request path
    threading.Thread(target=chat_cache.chat_cache.warm_up, name="chat-cache-warmup", daemon=True).start()
    yield


app = FastAPI(title="RM Co-pilot API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|bot|assistant)$")
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _clip(cls, v: str) -> str:
        return v[:8000]  # long earlier replies in the history are clipped, not rejected


class FeedbackRequest(BaseModel):
    verdict: Literal["useful", "not_useful"]
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _clip(cls, v: str | None) -> str | None:
        return v[:feedback.MAX_REASON] if v else v


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


def _need_data(r: PortfolioReader):
    if not r.status().get("loaded"):
        raise HTTPException(503, detail={"code": "no_data", "message": "No client data loaded. Run: python -m app.ingest"})


@app.get("/api/data/status")
def data_status(s: Session = Depends(get_session)):
    return PortfolioReader(s).status()


@app.get("/api/dashboard/act-now")
def dashboard_act_now(s: Session = Depends(get_session)):
    """The merchants to act on now (step 1: the five highest-value churn risks), with the data behind each."""
    r = PortfolioReader(s)
    _need_data(r)
    return r.act_now()


@app.get("/api/dashboard/dormant")
def dashboard_dormant(s: Session = Depends(get_session)):
    """Step 4: merchants whose terminals are inactive now, ranked by their earlier monthly card volume."""
    r = PortfolioReader(s)
    _need_data(r)
    return r.dormant_reactivation()


@app.get("/api/dashboard/top-performers")
def dashboard_top_performers(s: Session = Depends(get_session)):
    """Step 3: the merchants driving the bulk of the portfolio's card volume, with their share of it and the step to take."""
    r = PortfolioReader(s)
    _need_data(r)
    return r.top_performers()


@app.get("/api/dashboard/cross-sell")
def dashboard_cross_sell(s: Session = Depends(get_session)):
    """Step 2: the growth-ready merchants with a lending or cross-sell product to offer, with the data behind each."""
    r = PortfolioReader(s)
    _need_data(r)
    return r.cross_sell_targets()


@app.get("/api/dashboard")
def dashboard(filter: str = Query("all", pattern="^(all|opp|high|churn|top|dormant)$"), q: str = "", s: Session = Depends(get_session)):
    r = PortfolioReader(s)
    _need_data(r)
    return r.dashboard(filter, q.strip())


@app.get("/api/clients")
def clients(q: str = "", balance_min: float | None = None, balance_max: float | None = None, segment: str | None = None,
            card_type: str | None = None, product: str | None = None, s: Session = Depends(get_session)):
    r = PortfolioReader(s)
    _need_data(r)
    return r.client_directory(q.strip(), balance_min, balance_max, segment, card_type, product)


@app.get("/api/clients/filter-options")
def client_filter_options(s: Session = Depends(get_session)):
    r = PortfolioReader(s)
    _need_data(r)
    return r.client_filter_options()


@app.get("/api/clients/{merchant_id}")
def client_detail(merchant_id: str, s: Session = Depends(get_session)):
    try:
        return ClientReader(s, merchant_id).detail()
    except ClientNotFound:
        raise HTTPException(404, detail={"code": "client_not_found", "message": f"No client {merchant_id}"})


def _client_reader(s: Session, merchant_id: str) -> ClientReader:
    try:
        return ClientReader(s, merchant_id)
    except ClientNotFound:
        raise HTTPException(404, detail={"code": "client_not_found", "message": f"No client {merchant_id}"})


@app.get("/api/clients/{merchant_id}/evidence")
def client_evidence(merchant_id: str, s: Session = Depends(get_session)):
    """The data behind this client's current suggestion, with the checks re-run on current data."""
    return evidence.build(_client_reader(s, merchant_id).detail(), s)


@app.post("/api/clients/{merchant_id}/feedback")
def rate_suggestion(merchant_id: str, req: FeedbackRequest, s: Session = Depends(get_session)):
    """Rate this client's current suggestion useful or not useful. Rating again replaces the earlier rating."""
    decision = feedback.current_decision(_client_reader(s, merchant_id).detail())
    if decision is None:
        raise HTTPException(422, detail={"code": "nothing_to_rate", "message": "This client has no suggested action to rate."})
    return feedback.record(s, merchant_id, decision, req.verdict, req.reason)


@app.delete("/api/clients/{merchant_id}/feedback")
def clear_rating(merchant_id: str, s: Session = Depends(get_session)):
    decision = feedback.current_decision(_client_reader(s, merchant_id).detail())
    return {"cleared": bool(decision and feedback.clear(s, merchant_id, decision))}


@app.get("/api/feedback/summary")
def feedback_summary(s: Session = Depends(get_session)):
    """How useful RMs have found suggestions: overall, by who decided (AI or rules), by product, and the reasons given."""
    return feedback.summary(s)


@app.get("/api/suggestions")
def suggestions(product: str | None = None, s: Session = Depends(get_session)):
    r = PortfolioReader(s)
    _need_data(r)
    return r.suggestions(10, product)


@app.get("/api/suggestions/products")
def suggestion_products(s: Session = Depends(get_session)):
    r = PortfolioReader(s)
    _need_data(r)
    return r.suggestion_products()


def _audited_reply(request: Request, scope: str, merchant_id: str | None, req: ChatRequest, answer) -> dict:
    """Run a co-pilot answer, write one audit line for it and return it with a request id the RM can quote."""
    rid, t0 = uuid.uuid4().hex[:12], time.perf_counter()
    out = answer()
    usage = out.pop("usage", None)     # token counts and a blocked answer's text are audited, not sent to the browser
    blocked_reply = out.pop("blocked_reply", None)
    audit.record("chat", request_id=rid, scope=scope, merchant_id=merchant_id, client=request.client.host if request.client else None,
                 mode=out["mode"], model=config.LLM_MODEL if out["mode"] == "llm" else None, question=req.messages[-1].text,
                 reply=out["reply"], llm_error=out.get("llm_error"), guardrail=out.get("guardrail"), cache_hit=out.get("cache_hit"),
                 latency_ms=round((time.perf_counter() - t0) * 1000), usage=usage, blocked_reply=blocked_reply)
    return {**out, "request_id": rid}


@app.post("/api/copilot/portfolio", dependencies=[Depends(chat_rate_limit)])
def copilot_portfolio(request: Request, req: ChatRequest, s: Session = Depends(get_session)):
    r = PortfolioReader(s)
    _need_data(r)
    if req.messages[-1].role != "user":
        raise HTTPException(422, detail="last message must be from the user")
    return _audited_reply(request, "portfolio", None, req, lambda: copilot.portfolio_reply(r, [m.model_dump() for m in req.messages]))


@app.post("/api/copilot/clients/{merchant_id}", dependencies=[Depends(chat_rate_limit)])
def copilot_client(request: Request, merchant_id: str, req: ChatRequest, s: Session = Depends(get_session)):
    if req.messages[-1].role != "user":
        raise HTTPException(422, detail="last message must be from the user")
    try:
        reader = ClientReader(s, merchant_id)
    except ClientNotFound:
        raise HTTPException(404, detail={"code": "client_not_found", "message": f"No client {merchant_id}"})
    return _audited_reply(request, "client", merchant_id, req,
                          lambda: copilot.merchant_reply(reader, PortfolioReader(s).directory_names(), [m.model_dump() for m in req.messages]))
