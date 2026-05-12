<template>
  <div v-if="visible" class="source-viewer-overlay" @click.self="close">
    <div class="source-viewer">
      <div class="sv-header">
        <span class="sv-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M15 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7z"/><path d="M14 2v5h5"/>
          </svg>
          引用溯源
        </span>
        <div class="sv-actions">
          <button v-if="source.doc_id" class="btn btn-ghost btn-sm" @click="openOriginal" title="查看原文档">
            📄 原文档
          </button>
          <button class="sv-close" @click="close">&times;</button>
        </div>
      </div>

      <div class="sv-meta">
        <span class="sv-badge">来源{{ source.idx }}</span>
        <span v-if="source.score" class="sv-score">匹配度 {{ ((source.score||0)*100).toFixed(0) }}%</span>
        <span v-if="source.filename" class="sv-filename">{{ source.filename }}</span>
        <span v-if="source.chunk_idx != null" class="sv-chunk">分块 #{{ source.chunk_idx }}</span>
      </div>

      <div class="sv-body">
        <!-- 高亮匹配文本 -->
        <div class="sv-content" v-html="highlightedText"></div>
      </div>

      <!-- 上下文 chunks 浏览 -->
      <div v-if="contextChunks.length > 1" class="sv-context">
        <div class="sv-ctx-title">相邻分块上下文</div>
        <div v-for="(chunk, ci) in contextChunks" :key="ci"
             class="sv-ctx-item" :class="{active: chunk.isCurrent}">
          <span class="sv-ctx-idx">#{{ chunk.chunk_idx }}</span>
          <span class="sv-ctx-text">{{ chunk.text }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps({
  visible:    { type: Boolean, default: false },
  source:     { type: Object, default: () => ({}) },
  query:      { type: String, default: '' },
  allSources: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'open-doc'])
const contextChunks = ref([])

// 提取关键词用于高亮
function extractKeywords(query) {
  if (!query) return []
  // 简单分词：中文2字以上连续，英文2字母以上
  const matches = query.match(/[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9]{2,}/g)
  return matches ? [...new Set(matches)] : []
}

const highlightedText = computed(() => {
  const text = props.source.text || '无内容'
  const keywords = extractKeywords(props.query)
  if (!keywords.length) return escapeHtml(text)

  let result = escapeHtml(text)
  for (const kw of keywords) {
    const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const re = new RegExp(`(${escaped})`, 'gi')
    result = result.replace(re, '<mark class="sv-highlight">$1</mark>')
  }
  return DOMPurify.sanitize(result, { ALLOWED_TAGS: ['mark'], ALLOWED_ATTR: ['class'] })
})

function escapeHtml(text) {
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// 构建上下文 chunks（当前 + 前后相邻）
watch(() => [props.source, props.allSources], () => {
  if (!props.source || !props.allSources.length) {
    contextChunks.value = []
    return
  }
  const currentIdx = props.source.chunk_idx
  if (currentIdx == null) { contextChunks.value = []; return }

  const sameDoc = props.allSources
    .filter(s => s.doc_id === props.source.doc_id)
    .sort((a, b) => (a.chunk_idx || 0) - (b.chunk_idx || 0))

  contextChunks.value = sameDoc.map(s => ({
    chunk_idx: s.chunk_idx,
    text: (s.text || '').slice(0, 150) + ((s.text||'').length > 150 ? '...' : ''),
    isCurrent: s.chunk_idx === currentIdx,
  }))
}, { immediate: true })

function close() { emit('close') }

function openOriginal() {
  if (props.source.doc_id) {
    emit('open-doc', props.source.doc_id)
  }
}
</script>

<style scoped>
.source-viewer-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
  backdrop-filter: blur(5px);
}
.source-viewer {
  background: rgba(21, 25, 50, 0.97);
  border: 1px solid rgba(0, 243, 255, 0.2);
  border-radius: 14px;
  width: 640px; max-width: 95vw; max-height: 85vh;
  display: flex; flex-direction: column;
  backdrop-filter: blur(20px);
  box-shadow: 0 0 40px rgba(0, 243, 255, 0.08);
}

.sv-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(0, 243, 255, 0.1);
}
.sv-title {
  font-family: "Orbitron", sans-serif;
  font-size: 12px; font-weight: 600;
  color: #00f3ff; letter-spacing: 1px;
  display: flex; align-items: center; gap: 6px;
}
.sv-actions { display: flex; align-items: center; gap: 8px; }
.sv-close {
  background: none; border: none;
  font-size: 20px; color: var(--text-3);
  cursor: pointer; transition: color 0.2s;
}
.sv-close:hover { color: #ff006e; }

.sv-meta {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 18px;
  border-bottom: 1px solid rgba(0, 243, 255, 0.06);
  flex-wrap: wrap;
}
.sv-badge {
  background: rgba(0, 243, 255, 0.1);
  color: #00f3ff;
  padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 700;
  font-family: "JetBrains Mono", monospace;
}
.sv-score {
  font-size: 11px; color: #05ffa1;
  font-family: "JetBrains Mono", monospace;
}
.sv-filename {
  font-size: 11px; color: var(--text-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sv-chunk {
  font-size: 10px; color: var(--text-3);
  font-family: "JetBrains Mono", monospace;
}

.sv-body {
  flex: 1; overflow-y: auto;
  padding: 16px 18px;
}
.sv-content {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-1);
  white-space: pre-wrap;
  word-break: break-word;
}

.sv-context {
  border-top: 1px solid rgba(0, 243, 255, 0.1);
  padding: 10px 18px;
  max-height: 180px;
  overflow-y: auto;
}
.sv-ctx-title {
  font-family: "Orbitron", sans-serif;
  font-size: 9px; font-weight: 600;
  color: #b967ff; letter-spacing: 1px;
  margin-bottom: 6px;
}
.sv-ctx-item {
  display: flex; gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-3);
  transition: background 0.2s;
  line-height: 1.5;
}
.sv-ctx-item.active {
  background: rgba(0, 243, 255, 0.08);
  color: var(--text-1);
  border-left: 2px solid #00f3ff;
}
.sv-ctx-idx {
  flex-shrink: 0;
  font-family: "JetBrains Mono", monospace;
  color: var(--text-3);
  font-size: 10px;
  min-width: 24px;
}
.sv-ctx-text {
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

:deep(.sv-highlight) {
  background: rgba(255, 190, 11, 0.25);
  color: #ffbe0b;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}

/* light theme */
[data-theme="light"] .source-viewer {
  background: rgba(255, 255, 255, 0.97);
  border-color: rgba(0, 102, 204, 0.2);
}
[data-theme="light"] .sv-content { color: #1a1a2e; }
</style>
