"""FastAPI backend for AI chat with Bailian app."""
import asyncio
import json
import os
import uuid
from http import HTTPStatus
from contextlib import asynccontextmanager

import httpx
from dashscope import Application
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
MOCK_TOOLS = {
    "sql": {
        "value": "SELECT m.id, m.name, COUNT(DISTINCT o.id) as order_count, COUNT(DISTINCT o.user_id) as user_count, SUM(o.amount) as total_amount, AVG(o.amount) as avg_amount, SUM(oi.quantity) as total_items FROM merchants m LEFT JOIN orders o ON m.id = o.merchant_id LEFT JOIN order_items oi ON o.id = oi.order_id WHERE m.city = '北京' AND m.level = 3 AND o.status = 1 AND o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY m.id, m.name ORDER BY total_amount DESC LIMIT 100;"
    },
    "table_structures": {
        "value": "-- 订单表（500万条记录）\nCREATE TABLE orders (\n    id BIGINT PRIMARY KEY AUTO_INCREMENT,\n    order_no VARCHAR(32),\n    merchant_id INT,\n    user_id INT,\n    amount DECIMAL(10,2),\n    status TINYINT,\n    created_at DATETIME,\n    updated_at DATETIME\n) ENGINE=InnoDB;\n\n-- 订单明细表（2000万条记录）\nCREATE TABLE order_items (\n    id BIGINT PRIMARY KEY AUTO_INCREMENT,\n    order_id BIGINT,\n    product_id INT,\n    quantity INT,\n    price DECIMAL(10,2),\n    created_at DATETIME\n) ENGINE=InnoDB;\n\n-- 商户表（10万条记录）\nCREATE TABLE merchants (\n    id INT PRIMARY KEY AUTO_INCREMENT,\n    name VARCHAR(100),\n    category VARCHAR(50),\n    city VARCHAR(50),\n    level TINYINT\n) ENGINE=InnoDB;"
    },
    "slow_log": {
        "value": "# Time: 2024-03-15T03:25:41.123456Z\n# Query_time: 20.342387  Lock_time: 0.000123  Rows_sent: 100  Rows_examined: 25438921\n# Rows_affected: 0  Bytes_sent: 15234"
    },
    "explain_result": {
        "value": """+----+-------------+-------+------+---------------+------+---------+------+----------+----------------------------------------------+\n| id | select_type | table | type | possible_keys | key  | key_len | ref  | rows     | Extra                                        |\n+----+-------------+-------+------+---------------+------+---------+------+----------+----------------------------------------------+\n|  1 | SIMPLE      | m     | ALL  | NULL          | NULL | NULL    | NULL |   100000 | Using where; Using temporary; Using filesort |\n|  1 | SIMPLE      | o     | ALL  | NULL          | NULL | NULL    | NULL |  5000000 | Using where; Using join buffer              |\n|  1 | SIMPLE      | oi    | ALL  | NULL          | NULL | NULL    | NULL | 20000000 | Using where; Using join buffer              |\n+----+-------------+-------+------+---------------+------+---------+------+----------+----------------------------------------------+"""
    },
    "tables_info": {
        "value": "订单表（500万条记录），订单明细表（2000万条记录），商户表（10万条记录）"
    },
}


class ToolResponse(BaseModel):
    name: str
    value: str


@app.get("/api/tools/{tool_name}", response_model=ToolResponse)
async def get_tool(tool_name: str):
    """Return mock MCP tool data with simulated delay."""
    if tool_name not in MOCK_TOOLS:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")
    await asyncio.sleep(1.5)
    return ToolResponse(name=tool_name, value=MOCK_TOOLS[tool_name]["value"])


# ── Bailian App Chat ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Forward user message to Bailian app and return the reply."""
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


class BailianRequest(BaseModel):
    message: str
    params: dict = {}


def _is_truncated(text: str) -> bool:
    """Check if text appears to be cut off mid-sentence."""
    if not text:
        return False
    stripped = text.rstrip()
    if not stripped:
        return False
    if len(stripped) < 50:
        return False

    last_char = stripped[-1]

    # Strong sentence endings: definitely complete
    if last_char in {'。', '！', '？', '…'}:
        return False

    # Ends with paragraph break after strong ending
    if last_char == '\n' and len(stripped) > 50:
        prev_line = stripped.rstrip('\n').split('\n')[-1].strip()
        if prev_line and prev_line[-1] in {'。', '！', '？', '…', '：'}:
            return False

    # Check last 5 non-space chars for a strong ending
    last_chars = stripped[-15:].replace(' ', '')
    if any(c in {'。', '！', '？', '…'} for c in last_chars):
        return False

    # Unbalanced code fence
    if stripped.count('```') % 2 != 0:
        return True

    # Likely truncated
    return True


@app.post("/api/bailian")
async def bailian_chat(req: BailianRequest):
    """Call Bailian app with SSE streaming and auto-continuation."""
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    def generate():
        session_id = str(uuid.uuid4())
        prompt = req.message
        max_rounds = 5
        round_num = 0

        try:
            while round_num < max_rounds:
                round_num += 1
                responses = Application.call(
                    api_key=DASHSCOPE_API_KEY,
                    app_id=BAILIAN_APP_ID,
                    prompt=prompt,
                    biz_params={"user_prompt_params": req.params},
                    stream=True,
                    incremental_output=True,
                    session_id=session_id,
                )
                round_text = ""
                for response in responses:
                    if response.status_code != HTTPStatus.OK:
                        yield f"data: {json.dumps({'error': response.message})}\n\n"
                        return
                    text = response.output.text if response.output else ''
                    if text:
                        round_text += text
                        yield f"data: {json.dumps({'text': text})}\n\n"

                if not _is_truncated(round_text):
                    break
                prompt = "继续"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
