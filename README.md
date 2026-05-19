# AI Chat

AI 聊天程序，前端使用 Vue 3 + Vite，后端使用 FastAPI 调用 Qwen 大模型。

## 前置条件

- Node.js >= 18
- Conda (Miniconda/Anaconda)
- DashScope API Key

## 快速启动

### 1. 后端

```bash
# 创建并激活 conda 环境
conda activate ai-chat
# 如果环境不存在，先创建：
# conda create -y -n ai-chat python=3.11 && conda activate ai-chat

# 安装依赖
cd backend
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 DASHSCOPE_API_KEY

# 启动服务
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173` 即可使用。

## 项目结构

```text
ai-chat/
├── backend/
│   ├── main.py              # FastAPI 服务器
│   ├── requirements.txt     # Python 依赖
│   └── .env.example         # 环境变量模板
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js       # Vite 配置，前端开发服务器端口 5173
    └── src/
        ├── App.vue          # 聊天界面 + 打字机效果
        ├── main.js
        └── style.css
```

## API

| 方法   | 路径           | 描述         |
| ------ | -------------- | ------------ |
| GET    | `/health`      | 健康检查     |
| POST   | `/api/chat`    | 发送聊天消息 |

请求体：

```json
{
  "message": "你好"
}
```

响应体：

```json
{
  "reply": "你好！有什么可以帮你的吗？"
}
```

## 环境变量

| 变量              | 默认值                                              | 说明              |
| ----------------- | --------------------------------------------------- | ----------------- |
| DASHSCOPE_API_KEY | (空)                                                | 通义千问 API Key  |
| QWEN_BASE_URL     | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Qwen API 基础 URL |
| QWEN_MODEL        | `qwen-plus`                                         | 使用的模型名称    |
