"""FastAPI backend for AI chat with Qwen model."""
import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not QWEN_API_KEY:
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


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Forward user message to Qwen and return the reply."""
    if not QWEN_API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": QWEN_MODEL,
        "messages": [{"role": "user", "content": req.message}],
        "stream": False,
    }
    url = f"{QWEN_BASE_URL}/chat/completions"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Qwen API error: {resp.text}",
        )

    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    return ChatResponse(reply=reply)


@app.get("/health")
async def health():
    return {"status": "ok"}
