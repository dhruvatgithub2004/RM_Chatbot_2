import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import field_validator, BaseModel, Field
from sqlalchemy.orm import Session

import threading

from . import audit, config, copilot, guardrails
from .ratelimit import chat_rate_limit
from .db import Base, engine, get_session
from .readers import ClientNotFound, ClientReader, PortfolioReader


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    threading.Thread(target=guardrails.warm_up, name="guardrails-warmup", daemon=True).start()   # build the rails off the request path
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


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


def _need_data(r: PortfolioReader):
    if not r.status().get("loaded"):
        raise HTTPException(503, detail={"code": "no_data", "message": "No client data loaded. Run: python -m app.ingest"})


@app.get("/api/data/status")
def data_status(s: Session = Depends(get_session)):
    return PortfolioReader(s).status()


@app.get("/api/dashboard")
def dashboard(filter: str = Query("all", pattern="^(all|opp|high)$"), q: str = "", s: Session = Depends(get_session)):
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
    audit.record("chat", request_id=rid, scope=scope, merchant_id=merchant_id, client=request.client.host if request.client else None,
                 mode=out["mode"], model=config.LLM_MODEL if out["mode"] == "llm" else None, question=req.messages[-1].text,
                 reply=out["reply"], llm_error=out.get("llm_error"), guardrail=out.get("guardrail"), latency_ms=round((time.perf_counter() - t0) * 1000))
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
