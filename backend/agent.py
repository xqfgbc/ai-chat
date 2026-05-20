"""SlowSQL agent and router agent for AI chat."""

import asyncio
import json
import uuid
from http import HTTPStatus

from dashscope import Application

# ── Tool definitions ──────────────────────────────────────────────────


TOOLS = {
    "sql": {
        "label": "获取慢查询 SQL 语句",
        "value": "SELECT m.id, m.name, COUNT(DISTINCT o.id) as order_count, COUNT(DISTINCT o.user_id) as user_count, SUM(o.amount) as total_amount, AVG(o.amount) as avg_amount, SUM(oi.quantity) as total_items FROM merchants m LEFT JOIN orders o ON m.id = o.merchant_id LEFT JOIN order_items oi ON o.id = oi.order_id WHERE m.city = '北京' AND m.level = 3 AND o.status = 1 AND o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY m.id, m.name ORDER BY total_amount DESC LIMIT 100;",
    },
    "table_structures": {
        "label": "获取表结构信息",
        "value": "-- 订单表（500万条记录）\nCREATE TABLE orders (\n    id BIGINT PRIMARY KEY AUTO_INCREMENT,\n    order_no VARCHAR(32),\n    merchant_id INT,\n    user_id INT,\n    amount DECIMAL(10,2),\n    status TINYINT,\n    created_at DATETIME,\n    updated_at DATETIME\n) ENGINE=InnoDB;\n\n-- 订单明细表（2000万条记录）\nCREATE TABLE order_items (\n    id BIGINT PRIMARY KEY AUTO_INCREMENT,\n    order_id BIGINT,\n    product_id INT,\n    quantity INT,\n    price DECIMAL(10,2),\n    created_at DATETIME\n) ENGINE=InnoDB;\n\n-- 商户表（10万条记录）\nCREATE TABLE merchants (\n    id INT PRIMARY KEY AUTO_INCREMENT,\n    name VARCHAR(100),\n    category VARCHAR(50),\n    city VARCHAR(50),\n    level TINYINT\n) ENGINE=InnoDB;",
    },
    "slow_log": {
        "label": "获取慢查询日志",
        "value": "# Time: 2024-03-15T03:25:41.123456Z\n# Query_time: 20.342387  Lock_time: 0.000123  Rows_sent: 100  Rows_examined: 25438921\n# Rows_affected: 0  Bytes_sent: 15234",
    },
    "explain_result": {
        "label": "获取 EXPLAIN 分析结果",
        "value": "+----+-------------+-------+------+---------------+------+---------+------+----------+----------------------------------------------+\n| id | select_type | table | type | possible_keys | key  | key_len | ref  | rows     | Extra                                        |\n+----+-------------+-------+------+---------------+------+---------+------+----------+----------------------------------------------+\n|  1 | SIMPLE      | m     | ALL  | NULL          | NULL | NULL    | NULL |   100000 | Using where; Using temporary; Using filesort |\n|  1 | SIMPLE      | o     | ALL  | NULL          | NULL | NULL    | NULL |  5000000 | Using where; Using join buffer              |\n|  1 | SIMPLE      | oi    | ALL  | NULL          | NULL | NULL    | NULL | 20000000 | Using where; Using join buffer              |\n+----+-------------+-------+------+---------------+------+---------+------+----------+----------------------------------------------+",
    },
    "tables_info": {
        "label": "获取表信息描述",
        "value": "订单表（500万条记录），订单明细表（2000万条记录），商户表（10万条记录）",
    },
}


# ── Router Agent ──────────────────────────────────────────────────────


class RouterAgent:
    """Classify user messages and route to the appropriate agent.

    To add a new agent, register it in AGENTS with keywords and agent class.
    """

    # Agent registry: {route_name: {keywords, agent_class}}
    # Route name 'general_chat' is the fallback — no keywords needed.
    AGENTS = {
        "slow_sql": {
            "keywords": [
                "sql", "慢查询", "慢sql", "slow query", "slow sql",
                "优化", "性能", "诊断", "数据库", "database",
                "explain", "索引", "index", "查询", "调优",
                "执行计划", "sql优化", "query optimization",
                "全表扫描", "filesort", "temporary", "慢查",
                "explain analyze", "执行效率", "查询慢",
            ],
        },
        # Add new agents here, e.g.:
        # "data_analysis": {
        #     "keywords": ["分析", "统计", "报表", "图表"],
        # },
    }

    @classmethod
    def classify(cls, message: str) -> str:
        """Return the route name for the message, or 'general_chat'."""
        lower = message.lower()
        for route_name, config in cls.AGENTS.items():
            for kw in config["keywords"]:
                if kw in lower:
                    return route_name
        return "general_chat"


# ── Shared helpers ────────────────────────────────────────────────────

import httpx


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

    if last_char in {'。', '！', '？', '…'}:
        return False

    if last_char == '\n' and len(stripped) > 50:
        prev_line = stripped.rstrip('\n').split('\n')[-1].strip()
        if prev_line and prev_line[-1] in {'。', '！', '？', '…', '：'}:
            return False

    last_chars = stripped[-15:].replace(' ', '')
    if any(c in {'。', '！', '？', '…'} for c in last_chars):
        return False

    if stripped.count('```') % 2 != 0:
        return True

    return True


async def _stream_qwen_text(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
):
    """Stream Qwen chat completions, yielding text chunks."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    url = f"{base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"Qwen API error ({resp.status_code}): {body.decode()}")
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass


async def _stream_bailian_text(
    api_key: str,
    app_id: str,
    prompt: str,
    biz_params: dict,
    session_id: str,
):
    """Stream Bailian app response as text chunks, with auto-continuation."""
    current_prompt = prompt
    max_rounds = 5

    for _ in range(max_rounds):
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _run():
            try:
                responses = Application.call(
                    api_key=api_key,
                    app_id=app_id,
                    prompt=current_prompt,
                    biz_params={"user_prompt_params": biz_params},
                    stream=True,
                    incremental_output=True,
                    session_id=session_id,
                )
                round_text = ""
                for response in responses:
                    if response.status_code != HTTPStatus.OK:
                        loop.call_soon_threadsafe(
                            queue.put_nowait, ('error', response.message)
                        )
                        return
                    text = response.output.text if response.output else ''
                    if text:
                        round_text += text
                        loop.call_soon_threadsafe(queue.put_nowait, ('text', text))
                loop.call_soon_threadsafe(queue.put_nowait, ('round_done', round_text))
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ('error', str(e)))

        loop.run_in_executor(None, _run)

        round_text = ""
        while True:
            kind, data = await queue.get()
            if kind == 'error':
                yield data
                return
            if kind == 'round_done':
                round_text = data
                break
            if kind == 'text':
                yield data

        if not _is_truncated(round_text):
            break
        current_prompt = "继续"


# ── SlowSQL Agent ─────────────────────────────────────────────────────


class SlowSQLAgent:
    """Encapsulates the slow SQL diagnosis workflow.

    Collects MCP tool data then calls Bailian app for analysis.
    """

    def __init__(self, api_key: str, app_id: str):
        self.api_key = api_key
        self.app_id = app_id

    async def execute(self, message: str):
        """Run the slow SQL diagnosis workflow, yielding SSE event dicts.

        Yields:
            {"type": "tool_start", "count": int}
            {"type": "tool_progress", "name": str, "label": str, "status": str, "error": str|None}
            {"type": "tool_done", "params": dict}
            {"type": "thinking_start"}
            {"type": "text", "content": str}
            {"type": "done"}
            {"type": "error", "message": str}
        """
        # Phase 1: Collect tools sequentially (for progressive UI display)
        yield {"type": "tool_start", "count": len(TOOLS)}

        params = {}
        for name, info in TOOLS.items():
            label = info["label"]
            yield {"type": "tool_progress", "name": name, "label": label, "status": "loading", "error": None}
            try:
                value = await self._fetch_tool(name)
                params[name] = value
                yield {"type": "tool_progress", "name": name, "label": label, "status": "done", "error": None}
            except Exception as e:
                yield {"type": "tool_progress", "name": name, "label": label, "status": "error", "error": str(e)}

        yield {"type": "tool_done", "params": params}

        # Phase 2: Call Bailian app with streaming
        yield {"type": "thinking_start"}

        session_id = str(uuid.uuid4())

        try:
            async for text in _stream_bailian_text(
                self.api_key, self.app_id, message, params, session_id
            ):
                yield {"type": "text", "content": text}
        except RuntimeError as e:
            yield {"type": "error", "message": str(e)}
            return

        yield {"type": "done"}

    async def _fetch_tool(self, name: str) -> str:
        """Simulate MCP tool call with 1.5s delay."""
        await asyncio.sleep(1.5)
        return TOOLS[name]["value"]
