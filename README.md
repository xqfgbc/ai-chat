# AI Chat

AI 聊天程序，前端使用 Vue 3 + Vite，后端使用 FastAPI 调用 Qwen 大模型。

## 前置条件

- Node.js >= 18
- Conda (Miniconda/Anaconda)
- DashScope API Key

## 快速启动

### 1. 后端

进入项目根目录，创建并激活 conda 环境：

```bash
cd /Users/bo.gong/Documents/accenture/workspace/ai-chat

# 首次运行需要创建环境（创建一次即可）
conda create -y -n ai-chat python=3.11

# 激活环境
conda activate ai-chat
```

进入 `backend` 目录，安装依赖：

```bash
cd backend
pip install -r requirements.txt
```

配置 API Key（首次运行需要）：

```bash
cp .env.example .env
# 编辑 .env 文件，将 DASHSCOPE_API_KEY= 后的值替换为你的真实 Key
```

启动后端服务（默认监听 `0.0.0.0:8000`）：

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后终端会显示：

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

**注意：** 此命令会阻塞终端，保持运行状态。关闭终端或按 `Ctrl+C` 即可停止后端。

### 2. 前端

打开**新的终端窗口**，进入项目根目录：

```bash
cd /Users/bo.gong/Documents/accenture/workspace/ai-chat
cd frontend
```

首次运行需要安装依赖：

```bash
npm install
```

启动前端开发服务器（默认监听 `localhost:5173`）：

```bash
npm run dev
```

启动成功后终端会显示：

```
  VITE v6.4.2  ready in xxx ms

  ➜  Local:   http://localhost:5173/
```

打开浏览器访问 `http://localhost:5173` 即可使用。

**注意：** 此命令同样会阻塞终端。关闭终端或按 `Ctrl+C` 即可停止前端。

### 完整启动顺序（两个终端窗口）

| 窗口 | 操作 | 结果 |
|------|------|------|
| 窗口 1 | `conda activate ai-chat` → `cd backend` → `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload` | 后端运行在 8000 端口 |
| 窗口 2 | `cd frontend` → `npm run dev` | 前端运行在 5173 端口 |
| 浏览器 | 访问 `http://localhost:5173` | 打开聊天界面 |

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
