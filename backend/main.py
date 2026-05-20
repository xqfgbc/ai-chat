"""FastAPI backend for AI chat with Bailian app."""

import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import TOOLS, RouterAgent, SlowSQLAgent, _stream_bailian_text, _stream_qwen_text

# Agent class lookup for route → agent mapping.
# Add new agents here when extending RouterAgent.AGENTS.
AGENT_MAP = {
    "slow_sql": SlowSQLAgent,
}

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
BAILIAN_APP_ID = os.getenv("BAILIAN_APP_ID", "1eedcc662da24784a2e73d4771aec350")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DASHSCOPE_API_KEY:
        print("WARNING: DASHSCOPE_API_KEY not set. Chat API will fail.")
    yield


app = FastAPI(title="AI Chat Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Mock MCP Tool Endpoints ──────────────────────────────────────────

class ToolResponse(BaseModel):
    name: str
    value: str


@app.get("/api/tools/{tool_name}", response_model=ToolResponse)
async def get_tool(tool_name: str):
    """Return mock MCP tool data with simulated delay."""
    if tool_name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")
    await asyncio.sleep(1.5)
    return ToolResponse(name=tool_name, value=TOOLS[tool_name]["value"])


# ── Qwen Chat ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Forward user message to Qwen API and return the reply."""
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": QWEN_MODEL,
        "messages": [{"role": "user", "content": req.message}],
        "stream": False,
    }
    url = f"{QWEN_BASE_URL}/chat/completions"

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Qwen API error: {resp.text}",
        )

    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    return ChatResponse(reply=reply)


# ── Bailian App Chat (backward compat) ────────────────────────────────

class BailianRequest(BaseModel):
    message: str
    params: dict = {}


@app.post("/api/bailian")
async def bailian_chat(req: BailianRequest):
    """Call Bailian app with SSE streaming and auto-continuation."""
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    async def generate():
        session_id = str(os.urandom(16).hex())
        try:
            async for text in _stream_bailian_text(
                DASHSCOPE_API_KEY, BAILIAN_APP_ID,
                req.message, req.params, session_id,
            ):
                yield f"data: {json.dumps({'text': text})}\n\n"
        except RuntimeError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Agent Router Endpoint ─────────────────────────────────────────────

class AgentRequest(BaseModel):
    message: str


@app.post("/api/chat/agent")
async def agent_chat(req: AgentRequest):
    """Unified agent endpoint with routing and SSE streaming."""
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    route = RouterAgent.classify(req.message)

    async def generate():
        # Route event
        yield f"data: {json.dumps({'type': 'route', 'action': route})}\n\n"

        if route in AGENT_MAP:
            agent_cls = AGENT_MAP[route]
            agent = agent_cls(DASHSCOPE_API_KEY, BAILIAN_APP_ID)
            async for event in agent.execute(req.message):
                yield f"data: {json.dumps(event)}\n\n"
        else:
            # general_chat: streaming Qwen direct chat
            yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

            try:
                async for text in _stream_qwen_text(
                    QWEN_BASE_URL, DASHSCOPE_API_KEY, QWEN_MODEL, req.message,
                ):
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
            except RuntimeError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
