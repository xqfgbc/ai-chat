<script setup>
import { ref, nextTick, onBeforeUnmount } from 'vue'

const API_URL = 'http://localhost:8000/api/chat'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const chatContainer = ref(null)
let typewriterTimer = null

async function sendMessage() {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true

  const assistantMsg = { role: 'assistant', content: '' }
  messages.value.push(assistantMsg)

  await nextTick()
  scrollToBottom()

  try {
    const resp = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Request failed' }))
      assistantMsg.content = `Error: ${err.detail || 'Unknown error'}`
      return
    }

    const data = await resp.json()
    typewriterEffect(assistantMsg, data.reply)
  } catch (e) {
    assistantMsg.content = `Network error: ${e.message}`
  }
}

function typewriterEffect(msgObj, fullText) {
  let index = 0
  const delay = 30

  typewriterTimer = setInterval(() => {
    if (index < fullText.length) {
      msgObj.content += fullText[index]
      index++
      nextTick(scrollToBottom)
    } else {
      clearInterval(typewriterTimer)
      loading.value = false
    }
  }, delay)
}

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

onBeforeUnmount(() => {
  if (typewriterTimer) clearInterval(typewriterTimer)
})
</script>

<template>
  <div class="chat-layout">
    <h1 class="title">AI Chat</h1>

    <div ref="chatContainer" class="messages">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['message', msg.role]"
      >
        <div class="bubble">{{ msg.content || 'Thinking...' }}</div>
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="input"
        @keydown="handleKeydown"
        placeholder="Type your message... (Enter to send)"
        :disabled="loading"
        rows="1"
      ></textarea>
      <button @click="sendMessage" :disabled="loading || !input.trim()">
        {{ loading ? 'Sending...' : 'Send' }}
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
  max-width: 75%;
  padding: 10px 16px;
  border-radius: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
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
