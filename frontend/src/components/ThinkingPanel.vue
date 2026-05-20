<script setup>

import { ref, computed } from 'vue'

const tools = ref([])
const done = ref(false)
const collapsed = ref(false)

const doneCount = computed(
  () => tools.value.filter((t) => t.status === 'done').length
)

function init(count) {
  tools.value = []
  done.value = false
  collapsed.value = false
  for (let i = 0; i < count; i++) {
    tools.value.push({ name: '', label: '', status: 'pending' })
  }
}

function update(name, label, status, error) {
  // Find first pending slot and fill it
  const idx = tools.value.findIndex((t) => t.status === 'pending')
  if (idx !== -1) {
    tools.value[idx] = { name, label, status, error: error || null }
  }
}

function finish() {
  done.value = true
  collapsed.value = true
}

function getSnapshot() {
  return tools.value.map((t) => ({
    name: t.name,
    label: t.label,
    status: t.status,
  }))
}

defineExpose({ init, update, finish, getSnapshot })
</script>

<template>
  <div class="thinking" :class="{ collapsed }">
    <!-- Collapsed bar -->
    <div v-if="done && collapsed" class="collapse-bar" @click="collapsed = false">
      <span class="summary">
        ✓ 参数收集完成 ({{ doneCount }}/{{ tools.length }})
      </span>
      <span class="hint">展开 ▸</span>
    </div>

    <!-- Expanded content -->
    <template v-else>
      <div class="thinking-header" @click="done ? (collapsed = true) : null">
        <span class="icon">{{ done ? '📋' : '🔍' }}</span>
        {{ done ? '参数收集结果' : '正在收集参数...' }}
        <span v-if="done" class="collapse-hint">点击折叠 ▾</span>
      </div>
      <div v-for="(t, idx) in tools" :key="idx" class="tool-item">
        <div class="tool-label">
          <span v-if="t.status === 'pending'" class="spinner">⏳</span>
          <span v-else-if="t.status === 'done'" class="check">✓</span>
          <span v-else class="error-icon">✗</span>
          {{ t.label || '等待中...' }}
        </div>
        <div v-if="t.status === 'done'" class="tool-status success">成功</div>
        <div v-else-if="t.status === 'error'" class="tool-status error">
          失败: {{ t.error }}
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.thinking {
  background: #f8f9fa;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 8px;
  transition: all 0.2s;
}

.thinking.collapsed {
  padding: 10px 16px;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #64748b;
  margin-bottom: 12px;
}

.collapse-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  font-size: 13px;
  color: #22c55e;
  user-select: none;
}

.collapse-bar .hint {
  color: #94a3b8;
  font-size: 12px;
}

.thinking-header .collapse-hint {
  margin-left: auto;
  font-size: 11px;
  color: #94a3b8;
  cursor: pointer;
}

.tool-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
}

.tool-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #475569;
}

.spinner {
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
}

.check {
  color: #22c55e;
  font-weight: bold;
}

.error-icon {
  color: #ef4444;
}

.tool-status {
  font-size: 12px;
  font-weight: 500;
}

.tool-status.success {
  color: #22c55e;
}

.tool-status.error {
  color: #ef4444;
}
</style>
