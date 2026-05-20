<script setup>

import { ref, nextTick, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import ThinkingPanel from './components/ThinkingPanel.vue'

marked.use({ gfm: true, breaks: false })

const AGENT_URL = 'http://localhost:8000/api/chat/agent'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const chatContainer = ref(null)
const thinkingPanel = ref(null)
const collectingParams = ref(false)

let abortController = null

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function createThinkingSummary() {
  const snapshot = thinkingPanel.value.getSnapshot()
  const doneCount = snapshot.filter((t) => t.status === 'done').length
  messages.value.push({
    role: 'thinking',
    doneCount,
    total: snapshot.length,
    tools: snapshot,
    expanded: false,
  })
}

function createAssistantPlaceholder() {
  messages.value.push({ role: 'assistant', content: '', rendered: '' })
  return messages.value.length - 1
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true

  await nextTick()
  scrollToBottom()

  try {
    abortController = new AbortController()
    const resp = await fetch(AGENT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: abortController.signal,
    })

    if (!resp.ok) {
      messages.value.push({ role: 'assistant', content: `Error: ${resp.status}`, rendered: '' })
      loading.value = false
      return
    }

    let fullText = ''
    let streamDone = false
    let streamError = null
    let assistantMsgIdx = -1

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8', { stream: true })

    // ── SSE reader (runs in parallel with typewriter) ──
    async function readSSE() {
      let sseBuf = ''
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) { streamDone = true; return }

          sseBuf += decoder.decode(value, { stream: true })
          const lines = sseBuf.split('\n')
          sseBuf = ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const dataStr = line.slice(6)
            if (dataStr === '[DONE]') { streamDone = true; return }

            let event
            try {
              event = JSON.parse(dataStr)
            } catch {
              sseBuf = line + '\n'
              continue
            }

            if (event.error) {
              streamError = event.error
              streamDone = true
              return
            }

            switch (event.type) {
              case 'route':
                if (event.action === 'slow_sql') {
                  collectingParams.value = true
                  await nextTick()
                  scrollToBottom()
                }
                break

              case 'tool_start':
                thinkingPanel.value.init()
                await nextTick()
                scrollToBottom()
                break

              case 'tool_progress':
                if (event.status === 'loading') {
                  thinkingPanel.value.addTool(event.name, event.label, event.status)
                } else {
                  thinkingPanel.value.updateTool(event.name, event.status, event.error)
                }
                break

              case 'tool_done':
                thinkingPanel.value.finish()
                collectingParams.value = false
                createThinkingSummary()
                assistantMsgIdx = createAssistantPlaceholder()
                await nextTick()
                scrollToBottom()
                break

              case 'thinking_start':
                if (assistantMsgIdx >= 0) {
                  messages.value[assistantMsgIdx].rendered =
                    '<span class="thinking-indicator">正在分析<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></span>'
                }
                break

              case 'text':
                if (assistantMsgIdx < 0) {
                  assistantMsgIdx = createAssistantPlaceholder()
                  await nextTick()
                  scrollToBottom()
                }
                fullText += event.content
                break

              case 'done':
                streamDone = true
                return

              case 'error':
                streamError = event.message
                streamDone = true
                return
            }
          }
        }
      } catch (e) {
        streamError = e.message
        streamDone = true
      }
    }

    const readTask = readSSE()

    // ── Typewriter (runs in parallel with SSE reader) ──
    const BATCH = 5
    let pos = 0
    await new Promise((resolve, reject) => {
      const timer = setInterval(() => {
        const remaining = fullText.length - pos
        const take = Math.min(BATCH, remaining)

        if (take > 0 && assistantMsgIdx >= 0) {
          pos += take
          const part = fullText.slice(0, pos)
          const lastNL = part.lastIndexOf('\n')
          const safe = lastNL > 0 ? part.slice(0, lastNL) : part
          messages.value[assistantMsgIdx].rendered = marked.parse(safe)
          messages.value[assistantMsgIdx].content = part
          scrollToBottom()
        }

        if (streamDone && pos >= fullText.length) {
          clearInterval(timer)
          resolve()
        }
        if (streamError) {
          clearInterval(timer)
          reject(new Error(streamError))
        }
      }, 25)
    })

    await readTask

    if (streamError) {
      if (assistantMsgIdx >= 0) {
        messages.value[assistantMsgIdx].content = `Error: ${streamError}`
      } else {
        messages.value.push({ role: 'assistant', content: `Error: ${streamError}`, rendered: '' })
      }
      loading.value = false
      return
    }

    if (assistantMsgIdx >= 0 && fullText) {
      messages.value[assistantMsgIdx].rendered = marked.parse(fullText)
      messages.value[assistantMsgIdx].content = fullText
    }
    loading.value = false
  } catch (e) {
    if (e.name === 'AbortError') return
    console.error('Agent error:', e)
    messages.value.push({ role: 'assistant', content: `Network error: ${e.message}`, rendered: '' })
    loading.value = false
  }
}

onBeforeUnmount(() => {
  if (abortController) abortController.abort()
})
</script>

<template>
  <div class="chat-layout">
    <h1 class="title">SQL 智能诊断</h1>

    <div ref="chatContainer" class="messages">
      <template v-for="(msg, i) in messages" :key="i">
        <div
          v-if="msg.role === 'thinking'"
          class="message thinking-msg"
        >
          <div class="thinking-inline" @click="msg.expanded = !msg.expanded">
            <span class="thinking-summary-icon">✓</span>
            参数收集完成 ({{ msg.doneCount }}/{{ msg.total }})
            <span class="thinking-toggle">{{ msg.expanded ? '折叠 ▾' : '展开 ▸' }}</span>
          </div>
          <div v-if="msg.expanded" class="thinking-detail">
            <div v-for="t in msg.tools" :key="t.name" class="thinking-tool-line">
              <span v-if="t.status === 'done'" class="check">✓</span>
              <span v-else class="error-icon">✗</span>
              {{ t.label }}
            </div>
          </div>
        </div>
        <div v-else :class="['message', msg.role]">
          <div class="bubble" v-html="msg.rendered || msg.content"></div>
        </div>
      </template>

      <div v-if="collectingParams" class="message assistant">
        <div class="bubble collecting">
          <ThinkingPanel ref="thinkingPanel" />
        </div>
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="input"
        @keydown="handleKeydown"
        placeholder="输入消息... (Enter 发送)"
        :disabled="loading"
        rows="1"
      ></textarea>
      <button @click="sendMessage" :disabled="loading || !input.trim()">
        {{ loading ? '处理中...' : '发送' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.title {
  text-align: center;
  padding: 16px 0;
  font-size: 1.4rem;
  color: #1a1a2e;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  display: flex;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 85%;
  padding: 12px 18px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.message.user .bubble {
  background: #4f46e5;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .bubble {
  background: #fff;
  color: #333;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.message.assistant .bubble.collecting {
  max-width: 100%;
  background: transparent;
  box-shadow: none;
  padding: 0;
}

/* ── Inline thinking summary ── */
.thinking-msg {
  justify-content: flex-start;
}

.thinking-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #64748b;
  cursor: pointer;
  user-select: none;
  padding: 4px 0;
}

.thinking-summary-icon {
  color: #22c55e;
  font-weight: bold;
  font-size: 12px;
}

.thinking-toggle {
  color: #94a3b8;
  font-size: 12px;
}

.thinking-detail {
  padding: 4px 0 4px 8px;
  border-left: 2px solid #e2e8f0;
  margin: 4px 0 4px 8px;
}

.thinking-tool-line {
  font-size: 12px;
  color: #94a3b8;
  padding: 2px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.thinking-tool-line .check {
  color: #22c55e;
  font-weight: bold;
}

.thinking-tool-line .error-icon {
  color: #ef4444;
}

/* ── Thinking indicator animation ── */
.thinking-indicator {
  color: #94a3b8;
  font-size: 14px;
}
.thinking-indicator .dot {
  animation: dotFade 1.4s infinite;
}
.thinking-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-indicator .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotFade {
  0%, 60%, 100% { opacity: 0.2; }
  30% { opacity: 1; }
}

.bubble :deep(code) {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 13px;
}

.bubble :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.bubble :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.bubble :deep(h1), .bubble :deep(h2), .bubble :deep(h3) {
  margin: 12px 0 6px;
}

.bubble :deep(p) {
  margin: 6px 0;
}

.bubble :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}

.bubble :deep(th), .bubble :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 6px 10px;
  text-align: left;
  font-size: 13px;
}

.bubble :deep(th) {
  background: #f8fafc;
  font-weight: 600;
}

.bubble :deep(ul), .bubble :deep(ol) {
  padding-left: 20px;
}
.bubble :deep(blockquote) {
  border-left: 3px solid #e2e8f0;
  padding-left: 12px;
  margin: 8px 0;
  color: #64748b;
}
.bubble :deep(hr) {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 12px 0;
}
.bubble :deep(a) {
  color: #4f46e5;
  text-decoration: underline;
}
.bubble :deep(strong) {
  font-weight: 600;
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 0;
  border-top: 1px solid #e0e0e0;
}

textarea {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #ccc;
  border-radius: 8px;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  outline: none;
}

textarea:focus {
  border-color: #4f46e5;
}

textarea:disabled {
  background: #f0f0f0;
}

button {
  padding: 10px 20px;
  background: #4f46e5;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}

button:hover:not(:disabled) {
  background: #4338ca;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
