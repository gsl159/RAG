<template>
  <div class="page chat-page">
    <!-- Topbar -->
    <div class="chat-topbar">
      <div class="topbar-left">
        <button class="btn btn-ghost btn-sm" @click="showHistory=!showHistory" title="历史记录">🕘 历史</button>
        <span class="page-title">智能问答</span>
        <span class="intent-badge" :class="lastIntent ? `i-${lastIntent.toLowerCase()}` : ''">
          {{ lastIntent || '就绪' }}
        </span>
      </div>
      <div class="topbar-right">
        <button v-if="messages.length" class="btn btn-ghost btn-sm" @click="exportMd" title="导出 Markdown">📥 导出</button>
        <span class="session-pill" title="当前会话">{{ messages.length ? `${messages.length} 条消息` : '新会话' }}</span>
        <span v-if="lastTrace" class="trace-pill">{{ lastTrace }}</span>
        <span class="status-dot" :class="healthy ? 'ok' : 'err'" :title="healthy ? '服务正常' : '服务异常'"></span>
      </div>
    </div>

    <div class="chat-body">
      <!-- History sidebar -->
      <div v-if="showHistory" class="history-panel">
        <div class="history-hd">
          <span>历史记录</span>
          <button class="modal-close" @click="showHistory=false">&times;</button>
        </div>
        <ConversationManager
          :current-session-id="sessionId"
          @load-session="loadHistoryItem"
          @new-session="newSession"
        />
      </div>

    <!-- Messages -->
    <div class="messages" ref="msgBox">
      <div v-if="!messages.length" class="empty-state">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="23" stroke="var(--border-md)" stroke-width="1.5"/><path d="M16 24h16M16 18h10M16 30h8" stroke="var(--text-3)" stroke-width="1.5" stroke-linecap="round"/></svg>
        </div>
        <p class="empty-title">开始提问</p>
        <p class="empty-sub">知识库模式：上传文档后自动检索回答。如无匹配文档，自动切换模型直答。</p>
        <div class="quick-questions">
          <button v-for="q in suggestions" :key="q" class="quick-btn" @click="sendQuick(q)">{{ q }}</button>
        </div>
      </div>

      <template v-for="(msg, i) in messages" :key="i">
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="msg-row msg-user">
          <div class="bubble bubble-user">{{ msg.content }}</div>
          <div class="msg-avatar user-av">我</div>
        </div>

        <!-- AI消息 -->
        <div v-else class="msg-row msg-ai">
          <div class="msg-avatar ai-av">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <div class="bubble-wrap">
            <div class="bubble bubble-ai">
              <MarkdownRenderer :content="msg.content" @cite-click="onCiteClick(msg, $event)" />
            </div>

            <!-- Meta bar -->
            <div class="meta-bar" v-if="msg.done">
              <span class="intent-tag" :class="`i-${(msg.intent||'c2').toLowerCase()}`">
                {{ {C0:'FAQ缓存',C1:'轻量',C2:'完整'}[msg.intent] || msg.intent }}
              </span>
              <span v-if="msg.degrade_level && msg.degrade_level !== 'C2'" class="degrade-tag">
                降级{{ msg.degrade_level }}
                <span v-if="msg.degrade_reason" class="degrade-reason">·{{ msg.degrade_reason }}</span>
              </span>
              <span v-if="msg.latency_ms" class="meta-item">{{ msg.latency_ms }}ms</span>
              <span v-if="msg.cache_hit" class="cache-tag">缓存命中</span>
              <div v-if="msg.confidence != null" class="conf-wrap">
                <div class="conf-bar"><div class="conf-fill" :style="{width: (msg.confidence*100)+'%', background: confColor(msg.confidence)}"></div></div>
                <span class="conf-val">{{ (msg.confidence*100).toFixed(0) }}%</span>
              </div>
              <div class="spacer"/>
              <button v-if="msg.log_id && !msg.confirmed" class="fb-btn confirm-btn" @click="confirmAnswer(msg)" title="确认答案正确（缓存此结果）">✅ 确认正确</button>
              <span v-if="msg.confirmed" class="confirmed-tag">✅ 已确认</span>
              <button v-if="msg.log_id" class="fb-btn" @click="shareMsg(msg)" title="分享">🔗</button>
              <button class="fb-btn" @click="doFeedback(msg,'like')" :class="{active: msg.fb==='like'}">👍</button>
              <button class="fb-btn" @click="openFbModal(msg)" :class="{active: msg.fb==='dislike'}">👎</button>
            </div>

            <!-- Sources -->
            <div v-if="msg.sources && msg.sources.length" class="sources-block">
              <div class="sources-title">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7z"/><path d="M14 2v5h5"/></svg>
                参考来源（{{ msg.sources.length }}）
              </div>
              <div v-for="(s,si) in msg.sources" :key="si"
                   class="source-item" :class="{expanded: s._expanded}"
                   :id="`src-${msg.sources===expandedSources ? 'active' : ''}-${si}`"
                   @click="s._expanded = !s._expanded">
                <div class="source-header">
                  <span class="source-idx">来源{{ s.idx || si+1 }}</span>
                  <span class="score-pill">{{ ((s.score||0)*100).toFixed(0) }}</span>
                  <span class="source-filename" :title="s.filename">📄 {{ s.filename || '未知文档' }}</span>
                  <span class="source-expand-icon">{{ s._expanded ? '▾' : '▸' }}</span>
                </div>
                <div v-if="s._expanded" class="source-content">
                  {{ s.text || '无内容' }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Typing -->
      <div v-if="loading" class="msg-row msg-ai">
        <div class="msg-avatar ai-av"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg></div>
        <div class="bubble bubble-ai dots"><span/><span/><span/></div>
      </div>
    </div>
    </div><!-- end chat-body -->

    <!-- Input -->
    <div class="input-area">
      <div class="input-options">
        <div class="mode-switch">

        </div>
        <label class="opt-label">
          <input type="checkbox" v-model="streamMode"> 流式
        </label>
        <label class="opt-label">
          意图
          <select v-model="forceIntent" class="intent-sel">
            <option value="">自动</option>
            <option value="C0">C0 FAQ</option>
            <option value="C1">C1 轻量</option>
            <option value="C2">C2 完整</option>
          </select>
        </label>
        <label v-if="allTags.length" class="opt-label">
          知识库
          <select v-model="selectedTags" multiple class="tag-sel" title="按住 Ctrl 多选标签">
            <option v-for="t in allTags" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </label>
        <button v-if="selectedTags.length" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:11px" @click="selectedTags=[]">清除标签</button>
        <button v-if="messages.length" class="btn btn-ghost btn-sm clear-btn" @click="newSession">新会话</button>
      </div>
      <div class="input-row">
        <div class="textarea-wrap">
          <textarea
            v-model="input"
            class="chat-textarea"
            placeholder="输入问题… Ctrl+Enter 发送 | Ctrl+K 聚焦 | Alt+N 新会话"
            @keydown.ctrl.enter.prevent="send"
            @keydown.escape="$event.target.blur()"
            rows="3"
            :disabled="loading"
          />
        </div>
        <button class="send-btn" @click="send" :disabled="loading || !input.trim()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
    </div>

    <!-- 引用溯源弹窗 -->
    <SourceViewer
      :visible="sourceViewerVisible"
      :source="viewingSource"
      :query="viewingQuery"
      :all-sources="viewingAllSources"
      @close="sourceViewerVisible = false"
      @open-doc="onOpenDoc"
    />

    <!-- 差评反馈弹窗 -->
    <div v-if="fbModal" class="modal-overlay" @click.self="fbModal=false">
      <div class="fb-modal">
        <div class="fb-modal-hd">
          <span>反馈详情</span>
          <button class="modal-close" @click="fbModal=false">&times;</button>
        </div>
        <div class="fb-modal-body">
          <label class="fb-field-label">原因</label>
          <div class="fb-reason-tags">
            <button v-for="r in reasonOptions" :key="r" class="reason-tag"
              :class="{selected: fbForm.reason===r}" @click="fbForm.reason=r">{{ r }}</button>
          </div>
          <label class="fb-field-label" style="margin-top:10px">评分</label>
          <div class="fb-ratings">
            <div v-for="dim in ['相关性','准确性','完整性']" :key="dim" class="rating-row">
              <span class="rating-label">{{ dim }}</span>
              <div class="stars">
                <span v-for="n in 5" :key="n" class="star" :class="{on: fbForm.ratings[dim]>=n}" @click="fbForm.ratings[dim]=n">★</span>
              </div>
            </div>
          </div>
          <label class="fb-field-label" style="margin-top:10px">纠正内容（可选）</label>
          <textarea v-model="fbForm.correction" class="fb-textarea" rows="2" placeholder="正确答案应该是…"/>
          <label class="fb-field-label" style="margin-top:10px">备注（可选）</label>
          <textarea v-model="fbForm.comment" class="fb-textarea" rows="2" placeholder="其他反馈…"/>
        </div>
        <div class="fb-modal-ft">
          <button class="btn btn-ghost btn-sm" @click="fbModal=false">取消</button>
          <button class="btn btn-accent btn-sm" @click="submitFbModal">提交差评</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted } from 'vue'
import { apiChat, apiFeedback, apiConfirmAnswer, fetchStream, apiHealth, apiSuggestions } from '@/api/index.js'
import { apiListTags } from '@/api/index.js'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import SourceViewer from '@/components/SourceViewer.vue'
import ConversationManager from '@/components/ConversationManager.vue'

const messages     = ref([])
const input        = ref('')
const loading      = ref(false)
const msgBox       = ref(null)
const streamMode   = ref(true)
const chatMode     = ref('rag')  // Always rag, backend auto-detects KB availability

const forceIntent  = ref('')
const lastTrace    = ref('')
const lastIntent   = ref('')
const healthy      = ref(true)
const sessionId    = ref(generateSessionId())
const suggestions  = ref(['公司报销流程是什么？', '年假政策如何申请？', '如何提交绩效评估？'])
const allTags      = ref([])
const selectedTags = ref([])  // tag_ids for scoped queries
const showHistory    = ref(false)

// Source viewer state
const sourceViewerVisible = ref(false)
const viewingSource       = ref({})
const viewingQuery        = ref('')
const viewingAllSources   = ref([])

function generateSessionId() {
  return 'sess_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function newSession() {
  messages.value = []
  sessionId.value = generateSessionId()
  lastTrace.value = ''
  lastIntent.value = ''
}

// 差评反馈弹窗
const fbModal = ref(false)
const fbTargetMsg = ref(null)
const reasonOptions = ['答非所问', '信息过时', '不完整', '有错误', '其他']
const fbForm = reactive({ reason: '', correction: '', comment: '', ratings: { '相关性': 0, '准确性': 0, '完整性': 0 } })

function resetFbForm() {
  fbForm.reason = ''; fbForm.correction = ''; fbForm.comment = ''
  fbForm.ratings = { '相关性': 0, '准确性': 0, '完整性': 0 }
}

onMounted(async () => {
  try { await apiHealth(); healthy.value = true }
  catch (e) { healthy.value = false; console.warn('健康检查失败:', e) }
  // 加载动态建议，失败则保留默认
  try {
    const data = await apiSuggestions()
    if (data && data.length) suggestions.value = data.map(d => d.question)
  } catch (e) { console.warn('加载建议失败:', e) }
  // 加载标签
  try { allTags.value = await apiListTags() || [] } catch (e) { console.warn('加载标签失败:', e) }
  // Listen for global keyboard shortcuts
  window.addEventListener('rag:new-session', newSession)
})

import { onUnmounted } from 'vue'
onUnmounted(() => {
  window.removeEventListener('rag:new-session', newSession)
})

function loadHistoryItem(item) {
  // Load a historical Q&A into the current messages
  messages.value = [
    { role: 'user', content: item.question },
    {
      role: 'assistant', content: item.answer || '', done: true,
      sources: (item.sources || []).map(s => ({ ...s, _expanded: false })),
      latency_ms: item.latency_ms,
      cache_hit: item.cache_hit, intent: item.intent,
      confidence: item.confidence, degrade_level: item.degrade_level,
      degrade_reason: item.degrade_reason, log_id: item.id, query: item.question,
    },
  ]
  lastIntent.value = item.intent || ''
  showHistory.value = false
}

function confColor(v) {
  if (v >= 0.75) return 'var(--green)'
  if (v >= 0.5)  return 'var(--yellow)'
  return 'var(--red)'
}

async function scrollBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

function sendQuick(q) { input.value = q; send() }

async function send() {
  const q = input.value.trim()
  if (!q || loading.value) return
  loading.value = true
  messages.value.push({ role: 'user', content: q })
  input.value = ''
  await scrollBottom()
  streamMode.value ? await sendStream(q) : await sendSync(q)
}

async function sendSync(q) {
  try {
    const data = await apiChat(q, sessionId.value, selectedTags.value, chatMode.value)
    lastTrace.value  = data.trace_id || ''
    lastIntent.value = data.intent || 'C2'
    messages.value.push({
      role: 'assistant', content: data.answer,
      sources: (data.sources || []).map(s => ({ ...s, _expanded: false })),
      latency_ms: data.latency_ms,
      cache_hit: data.cache_hit, intent: data.intent,
      confidence: data.confidence, degrade_level: data.degrade_level,
      degrade_reason: data.degrade_reason,
      log_id: data.log_id, query: q, done: true,
    })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: `请求失败：${e}`, done: true })
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

async function sendStream(q) {
  const idx = messages.value.length
  messages.value.push({ role: 'assistant', content: '', done: false, query: q, sources: [] })
  await fetchStream(q, sessionId.value, {
    tagIds: selectedTags.value.length ? selectedTags.value : undefined,
    mode: chatMode.value,
    onMessage: async (data) => {
      messages.value[idx].content += data
      await scrollBottom()
    },
    onSources: (sources) => {
      // 初始化 _expanded 属性以保证 Vue 响应式追踪
      messages.value[idx].sources = (sources || []).map(s => ({ ...s, _expanded: false }))
    },
    onError: (err) => {
      messages.value[idx].content = `错误：${err}`
      messages.value[idx].done = true; loading.value = false
    },
    onDone: () => {
      // 清理回答文本中的 [SOURCES] 残留
      const content = messages.value[idx].content
      const srcIdx = content.indexOf('\n[SOURCES]')
      if (srcIdx !== -1) messages.value[idx].content = content.slice(0, srcIdx)
      messages.value[idx].done = true; loading.value = false
    },
  })
  await scrollBottom()
}

async function doFeedback(msg, type) {
  if (msg.fb) return
  msg.fb = type
  try {
    await apiFeedback({ query: msg.query||'', answer: msg.content, feedback: type, log_id: msg.log_id })
  } catch (e) { console.warn('反馈提交失败:', e) }
}

async function confirmAnswer(msg) {
  if (!msg.log_id || msg.confirmed) return
  try {
    await apiConfirmAnswer(msg.log_id)
    msg.confirmed = true
  } catch (e) { console.warn('确认答案失败:', e); alert('确认失败：' + e) }
}

function openFbModal(msg) {
  if (msg.fb) return
  fbTargetMsg.value = msg
  resetFbForm()
  fbModal.value = true
}

async function submitFbModal() {
  const msg = fbTargetMsg.value
  if (!msg) return
  msg.fb = 'dislike'
  fbModal.value = false
  try {
    await apiFeedback({
      query: msg.query || '', answer: msg.content, feedback: 'dislike',
      reason: fbForm.reason || null,
      correction: fbForm.correction || null,
      ratings: { relevance: fbForm.ratings['相关性'], accuracy: fbForm.ratings['准确性'], completeness: fbForm.ratings['完整性'] },
      comment: fbForm.comment || null, log_id: msg.log_id,
    })
  } catch (e) { console.warn('详细反馈提交失败:', e) }
}

function exportMd() {
  const lines = messages.value.map(m =>
    m.role === 'user' ? `**Q:** ${m.content}` : `**A:** ${m.content}`
  )
  const md = `# RAG 问答记录\n\n${lines.join('\n\n---\n\n')}\n`
  const blob = new Blob([md], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `chat_${new Date().toISOString().slice(0,10)}.md`
  a.click(); URL.revokeObjectURL(a.href)
}

function shareMsg(msg) {
  if (!msg.log_id) return
  const url = `${location.origin}/api/chat/share/${msg.log_id || msg.id}`
  navigator.clipboard.writeText(url).then(() => alert('分享链接已复制')).catch(() => {
    prompt('复制分享链接：', url)
  })
}

const expandedSources = ref(null)   // currently tracked sources array (for scroll-to)

function onCiteClick(msg, srcIdx) {
  if (!msg.sources || !msg.sources.length) return
  const source = msg.sources.find(s => (s.idx || 0) === srcIdx) ||
                 msg.sources[srcIdx - 1]
  if (!source) return
  // Open source viewer modal
  viewingSource.value = { ...source, idx: source.idx || srcIdx }
  viewingQuery.value = msg.query || ''
  viewingAllSources.value = msg.sources
  sourceViewerVisible.value = true
}

function onOpenDoc(docId) {
  // Navigate to docs page with document filter
  if (docId) {
    window.open(`/docs?doc_id=${encodeURIComponent(docId)}`, '_blank')
  }
}
</script>

<style scoped>
.chat-page { display:flex; flex-direction:column; height:100%; }

.chat-body { display:flex; flex:1; overflow:hidden; }

/* ── History Panel ── */
.history-panel {
  width:260px; min-width:260px; border-right:1px solid rgba(0,243,255,0.1);
  background:rgba(10,14,39,0.9); display:flex; flex-direction:column; overflow:hidden;
  backdrop-filter:blur(15px);
}
.history-hd {
  display:flex; justify-content:space-between; align-items:center;
  padding:12px 14px; border-bottom:1px solid rgba(0,243,255,0.1);
  font-family:"Orbitron",sans-serif;
  font-size:11px; font-weight:600; color:#00f3ff; letter-spacing:1px;
}

.chat-topbar {
  height:48px; border-bottom:1px solid rgba(0,243,255,0.1);
  display:flex; align-items:center; padding:0 20px; gap:10px; flex-shrink:0;
  background:rgba(10,14,39,0.5);
  backdrop-filter:blur(10px);
}
.topbar-left { display:flex; align-items:center; gap:8px; }
.topbar-right { margin-left:auto; display:flex; align-items:center; gap:8px; }
.trace-pill {
  font-size:11px; color:var(--text-3);
  font-family:"JetBrains Mono",monospace;
  padding:2px 7px; border:1px solid rgba(0,243,255,0.15); border-radius:4px;
}
.session-pill {
  font-size:11px; color:var(--text-3);
  padding:2px 7px; border:1px solid rgba(0,243,255,0.15); border-radius:4px;
}
.status-dot { width:8px; height:8px; border-radius:50%; }
.status-dot.ok  { background:#05ffa1; box-shadow:0 0 8px rgba(5,255,161,0.6); }
.status-dot.err { background:#ff006e; box-shadow:0 0 8px rgba(255,0,110,0.6); }

.intent-badge {
  font-family:"Orbitron",sans-serif;
  font-size:10px; font-weight:600; padding:2px 7px; border-radius:4px; letter-spacing:0.5px;
}
.i-c0 { background:rgba(5,255,161,0.1); color:#05ffa1; text-shadow:0 0 6px rgba(5,255,161,0.3); }
.i-c1 { background:rgba(255,190,11,0.1); color:#ffbe0b; text-shadow:0 0 6px rgba(255,190,11,0.3); }
.i-c2 { background:rgba(0,243,255,0.08); color:#00f3ff; text-shadow:0 0 6px rgba(0,243,255,0.3); }

.messages {
  flex:1; overflow-y:auto; padding:20px;
  display:flex; flex-direction:column; gap:18px;
  min-width:0;
}
.empty-state { margin:auto; text-align:center; padding:40px 20px; }
.empty-icon  { margin:0 auto 14px; opacity:.4; }
.empty-title {
  font-family:"Orbitron",sans-serif;
  font-size:15px; font-weight:600; color:#00f3ff;
  text-shadow:0 0 10px rgba(0,243,255,0.3); margin-bottom:6px;
}
.empty-sub   { font-size:13px; color:var(--text-3); margin-bottom:18px; }
.quick-questions { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
.quick-btn {
  padding:6px 14px; border-radius:99px;
  border:1px solid rgba(0,243,255,0.2);
  background:rgba(0,243,255,0.05); color:var(--text-2); font-size:12px; cursor:pointer;
  transition:all .2s;
}
.quick-btn:hover {
  border-color:#00f3ff; color:#00f3ff;
  box-shadow:0 0 10px rgba(0,243,255,0.15);
}

.msg-row { display:flex; gap:10px; align-items:flex-start; animation:msgIn .3s ease; min-width:0; }
.msg-user { flex-direction:row-reverse; }
@keyframes msgIn {
  from { opacity:0; transform:translateY(10px); }
  to { opacity:1; transform:translateY(0); }
}
.msg-avatar { width:30px; height:30px; border-radius:50%; flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:600; }
.user-av { background:rgba(185,103,255,0.15); color:#b967ff; border:1px solid rgba(185,103,255,0.3); }
.ai-av   { background:linear-gradient(135deg,#00f3ff,#b967ff); color:#0a0e27; box-shadow:0 0 10px rgba(0,243,255,0.2); }

.bubble-wrap {
  display:flex; flex-direction:column; gap:8px;
  min-width:0; max-width:min(78%, 720px); flex:1;
}

.bubble {
  padding:14px 18px; border-radius:14px; font-size:13.5px; line-height:1.75;
  word-break:break-word; overflow-wrap:break-word;
  backdrop-filter:blur(10px);
}
.bubble-user {
  max-width:min(70%, 600px);
  background:rgba(185,103,255,0.1);
  border:1px solid rgba(185,103,255,0.25);
  color:var(--text-1);
}
.bubble-ai {
  background:rgba(21,25,50,0.8);
  border:1px solid rgba(0,243,255,0.15);
  color:var(--text-1);
}

/* ── Markdown styling delegated to MarkdownRenderer ── */

.meta-bar {
  display:flex; align-items:center; gap:6px; flex-wrap:wrap;
  font-size:11px; color:var(--text-3); padding:0 4px;
  font-family:"JetBrains Mono",monospace;
}
.intent-tag { padding:1px 6px; border-radius:3px; font-weight:600; }
.degrade-tag { padding:1px 6px; border-radius:3px; background:rgba(255,190,11,0.1); color:#ffbe0b; font-size:10px; }
.degrade-reason { opacity:.7; }
.cache-tag { padding:1px 6px; border-radius:3px; background:rgba(5,255,161,0.1); color:#05ffa1; font-weight:600; }
.conf-wrap { display:flex; align-items:center; gap:4px; }
.conf-bar  { width:40px; height:3px; background:rgba(0,243,255,0.1); border-radius:2px; overflow:hidden; }
.conf-fill { height:100%; border-radius:2px; transition:width .3s; }
.conf-val  { font-size:11px; }
.spacer { flex:1; }
.fb-btn {
  background:none; border:none; cursor:pointer; padding:3px 6px; border-radius:4px;
  font-size:14px; transition:all .2s; opacity:0.6;
}
.fb-btn:hover { background:rgba(0,243,255,0.08); opacity:1; }
.fb-btn.active { opacity:1; }
.confirm-btn { font-size:12px; color:var(--text-2); }
.confirm-btn:hover { color:#05ffa1; }
.confirmed-tag { font-size:12px; color:#05ffa1; padding:3px 6px; }

.sources-block {
  border:1px solid rgba(0,243,255,0.1); border-radius:10px; overflow:hidden;
  backdrop-filter:blur(10px); margin-top:6px;
}
.sources-title {
  padding:7px 12px;
  font-family:"Orbitron",sans-serif;
  font-size:9px; font-weight:600; color:#00f3ff;
  letter-spacing:1px;
  background:rgba(0,243,255,0.05); display:flex; align-items:center; gap:5px;
}
.source-item {
  display:flex; flex-direction:column; gap:4px; padding:8px 12px;
  border-top:1px solid rgba(0,243,255,0.05); font-size:11px;
  transition:background .15s; cursor:pointer;
}
.source-item:hover { background:rgba(0,243,255,0.03); }
.source-item.expanded { background:rgba(0,243,255,0.05); }
.source-header {
  display:flex; align-items:center; gap:8px; width:100%;
}
.source-idx {
  color:#00f3ff; font-weight:700; font-size:10px;
  font-family:"JetBrains Mono",monospace; flex-shrink:0;
}
.score-pill {
  padding:1px 5px; border-radius:3px;
  background:rgba(0,243,255,0.1); color:#00f3ff;
  font-weight:700; flex-shrink:0;
  font-family:"JetBrains Mono",monospace;
}
.source-filename {
  color:var(--text-2); font-size:11px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  flex:1; min-width:0;
}
.source-expand-icon {
  color:var(--text-3); font-size:10px; flex-shrink:0; margin-left:auto;
}
.source-content {
  color:var(--text-2); font-size:11px; line-height:1.6;
  padding:6px 0 2px 0; white-space:pre-wrap; word-break:break-all;
  border-top:1px dashed rgba(0,243,255,0.08); margin-top:4px;
  max-height:200px; overflow-y:auto;
}
.source-text { color:var(--text-2); line-height:1.5; }

.input-area {
  border-top:1px solid rgba(0,243,255,0.1); padding:12px 16px; flex-shrink:0;
  background:rgba(10,14,39,0.8);
  backdrop-filter:blur(15px);
}
.input-options { display:flex; align-items:center; gap:12px; margin-bottom:8px; font-size:12px; color:var(--text-3); }
.mode-switch { display:flex; gap:2px; background:rgba(10,14,39,0.6); border:1px solid rgba(0,243,255,0.15); border-radius:6px; padding:2px; }
.mode-btn {
  display:flex; align-items:center; gap:4px; padding:4px 10px; border:none; border-radius:4px;
  background:transparent; color:var(--text-3); font-size:12px; cursor:pointer; transition:all 0.2s;
  white-space:nowrap;
}
.mode-btn:hover { color:var(--text-1); background:rgba(0,243,255,0.06); }
.mode-btn.active { background:rgba(0,243,255,0.15); color:var(--accent); box-shadow:0 0 8px rgba(0,243,255,0.1); }
.opt-label { display:flex; align-items:center; gap:4px; cursor:pointer; }
.intent-sel {
  background:rgba(10,14,39,0.6); border:1px solid rgba(0,243,255,0.15);
  color:var(--text-2); border-radius:4px; padding:2px 6px; font-size:11px; outline:none;
}
.tag-sel {
  background:rgba(10,14,39,0.6); border:1px solid rgba(0,243,255,0.15);
  color:var(--text-2); border-radius:4px; padding:2px 6px; font-size:11px; outline:none;
  min-width:80px; max-height:60px;
}
.clear-btn  { margin-left:auto; }
.input-row  { display:flex; gap:8px; align-items:flex-end; }
.textarea-wrap { flex:1; min-width:0; }
.chat-textarea {
  width:100%; background:rgba(10,14,39,0.6);
  border:1px solid rgba(0,243,255,0.2);
  border-radius:10px; color:var(--text-1); padding:10px 14px;
  font-size:13px; resize:none; font-family:inherit; outline:none;
  line-height:1.5; transition:all .2s;
}
.chat-textarea:focus { border-color:#00f3ff; box-shadow:0 0 15px rgba(0,243,255,0.1); }
.chat-textarea:disabled { opacity:.5; }
.chat-textarea::placeholder { color:var(--text-3); }
.send-btn {
  width:42px; height:42px; border-radius:10px;
  background:linear-gradient(135deg,#00f3ff,#b967ff);
  border:none; cursor:pointer; display:flex; align-items:center; justify-content:center;
  flex-shrink:0; color:#0a0e27; transition:all .2s;
  box-shadow:0 0 15px rgba(0,243,255,0.2);
}
.send-btn:hover:not(:disabled) {
  box-shadow:0 0 25px rgba(0,243,255,0.4);
  transform:translateY(-1px);
}
.send-btn:disabled { opacity:.4; cursor:not-allowed; }

/* 差评反馈弹窗 */
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.6); display:flex; align-items:center; justify-content:center; z-index:100; backdrop-filter:blur(5px); }
.fb-modal {
  background:rgba(21,25,50,0.95); border:1px solid rgba(0,243,255,0.2);
  border-radius:14px; width:400px; max-width:92vw;
  backdrop-filter:blur(20px);
  box-shadow:0 0 30px rgba(0,243,255,0.05);
}
.fb-modal-hd {
  display:flex; justify-content:space-between; align-items:center;
  padding:14px 16px; border-bottom:1px solid rgba(0,243,255,0.1);
  font-family:"Orbitron",sans-serif; font-weight:600; font-size:12px;
  color:#00f3ff; letter-spacing:1px;
}
.fb-modal-body { padding:14px 16px; }
.fb-modal-ft { display:flex; justify-content:flex-end; gap:8px; padding:10px 16px; border-top:1px solid rgba(0,243,255,0.1); }
.modal-close { background:none; border:none; font-size:20px; color:var(--text-3); cursor:pointer; transition:color .2s; }
.modal-close:hover { color:#ff006e; }
.fb-field-label {
  display:block; font-family:"Orbitron",sans-serif;
  font-size:10px; font-weight:600; color:#00f3ff;
  margin-bottom:6px; letter-spacing:0.5px;
}
.fb-reason-tags { display:flex; flex-wrap:wrap; gap:6px; }
.reason-tag {
  padding:4px 12px; border-radius:99px;
  border:1px solid rgba(0,243,255,0.15);
  background:rgba(0,243,255,0.03); color:var(--text-2); font-size:12px; cursor:pointer;
  transition:all .2s;
}
.reason-tag.selected { border-color:#00f3ff; background:rgba(0,243,255,0.1); color:#00f3ff; box-shadow:0 0 8px rgba(0,243,255,0.15); }
.fb-ratings { display:flex; flex-direction:column; gap:6px; }
.rating-row { display:flex; align-items:center; gap:8px; }
.rating-label { font-size:12px; color:var(--text-3); width:50px; }
.stars { display:flex; gap:2px; }
.star { font-size:18px; color:rgba(0,243,255,0.15); cursor:pointer; transition:all .2s; user-select:none; }
.star.on { color:#ffbe0b; text-shadow:0 0 6px rgba(255,190,11,0.4); }
.fb-textarea {
  width:100%; background:rgba(10,14,39,0.6);
  border:1px solid rgba(0,243,255,0.15); border-radius:6px;
  color:var(--text-1); padding:6px 10px; font-size:12px;
  resize:none; font-family:inherit; outline:none;
  transition:all .2s;
}
.fb-textarea:focus { border-color:#00f3ff; box-shadow:0 0 8px rgba(0,243,255,0.1); }

/* ── Light theme overrides ── */
:root[data-theme="light"] .chat-topbar { background:rgba(255,255,255,0.7); border-bottom-color:rgba(0,102,204,0.1); }
:root[data-theme="light"] .history-panel { background:rgba(248,250,255,0.95); border-right-color:rgba(0,102,204,0.1); }
:root[data-theme="light"] .history-hd { border-bottom-color:rgba(0,102,204,0.1); color:#0066cc; }
:root[data-theme="light"] .bubble-user { background:rgba(124,58,237,0.08); border-color:rgba(124,58,237,0.15); }
:root[data-theme="light"] .bubble-ai { background:rgba(255,255,255,0.9); border-color:rgba(0,102,204,0.12); }
:root[data-theme="light"] .input-area { background:rgba(255,255,255,0.85); border-top-color:rgba(0,102,204,0.1); }
:root[data-theme="light"] .chat-textarea { background:rgba(248,250,255,0.8); border-color:rgba(0,102,204,0.15); }
:root[data-theme="light"] .chat-textarea:focus { border-color:#0066cc; box-shadow:0 0 10px rgba(0,102,204,0.08); }
:root[data-theme="light"] .send-btn { background:linear-gradient(135deg,#0066cc,#7c3aed); box-shadow:0 0 10px rgba(0,102,204,0.15); }
:root[data-theme="light"] .fb-modal { background:rgba(255,255,255,0.97); border-color:rgba(0,102,204,0.15); }
:root[data-theme="light"] .fb-modal-hd { border-bottom-color:rgba(0,102,204,0.1); color:#0066cc; }

/* ── Mobile responsive ── */
@media (max-width: 768px) {
  .history-panel { position:fixed; left:0; top:0; bottom:0; z-index:50; width:280px; box-shadow:4px 0 24px rgba(0,0,0,0.3); }
  .bubble-wrap { max-width:90% !important; }
  .input-area { padding:8px 10px; }
  .input-options { flex-wrap:wrap; gap:6px; }
  .chat-topbar { padding:0 10px; }
}
</style>
