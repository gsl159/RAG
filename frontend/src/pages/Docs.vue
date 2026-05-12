<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title">文档管理</div>
      <div class="page-sub">上传 PDF / Word / HTML / TXT，自动解析入库</div>
    </div>
    <div class="page-body">

      <!-- Upload zone -->
      <div class="upload-zone card" :class="{dragging}" @click="$refs.fileInput.click()"
        @dragover.prevent="dragging=true" @dragleave.prevent="dragging=false" @drop.prevent="onDrop">
        <input ref="fileInput" type="file" style="display:none" multiple
          accept=".pdf,.docx,.doc,.html,.htm,.txt,.md,.csv,.xlsx,.xls,.pptx,.ppt" @change="onFileChange"/>
        <div class="upload-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        </div>
        <p class="upload-title">拖拽或点击上传文件</p>
        <p class="upload-hint">支持 .pdf .docx .pptx .xlsx .csv .html .txt .md &#183; 单文件 &#8804; 50MB</p>
        <label class="overwrite-opt" @click.stop>
          <input type="checkbox" v-model="overwriteMode"> 覆盖已有同文件（MD5 相同时替换旧版本）
        </label>
      </div>

      <!-- Batch upload row -->
      <div class="batch-row" style="margin-top:10px;display:flex;gap:8px;">
        <button class="btn btn-ghost btn-sm" @click="$refs.zipInput.click()">&#128230; 批量上传 ZIP</button>
        <input ref="zipInput" type="file" accept=".zip" style="display:none" @change="onZipUpload"/>
        <button class="btn btn-ghost btn-sm" @click="urlModal=true">&#128279; URL 导入</button>
      </div>

      <!-- Upload queue -->
      <div v-if="queue.length" class="card" style="margin-top:14px">
        <div class="section-hd">上传队列</div>
        <div v-for="(item,i) in queue" :key="i" class="queue-row">
          <div class="q-icon" :class="item.status">
            <span v-if="item.status==='uploading'" class="dots"><span/><span/><span/></span>
            <svg v-else-if="item.status==='ok'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </div>
          <span class="q-name">{{ item.name }}</span>
          <span class="badge" :class="{'badge-blue':item.status==='uploading','badge-green':item.status==='ok','badge-red':item.status==='error'}">
            {{ {uploading:'上传中',ok:'已提交',error:'失败'}[item.status] }}
          </span>
          <span v-if="item.error" class="q-err">{{ item.error }}</span>
        </div>
      </div>

      <!-- Tags management card -->
      <div class="card" style="margin-top:14px">
        <div class="list-header">
          <span class="section-hd" style="margin:0">标签管理</span>
          <div style="display:flex;gap:6px;align-items:center">
            <input v-model="newTagName" class="tag-input" placeholder="新标签名" @keydown.enter="createTag"/>
            <input v-model="newTagColor" type="color" class="tag-color-input" title="标签颜色"/>
            <button class="btn btn-primary btn-sm" @click="createTag" :disabled="!newTagName.trim()">添加</button>
          </div>
        </div>
        <div class="tag-list">
          <span v-for="t in allTags" :key="t.id" class="tag-chip" :style="{background: t.color+'20', color: t.color, borderColor: t.color+'40'}">
            {{ t.name }} <span class="tag-count">{{ t.doc_count || 0 }}</span>
            <button class="tag-del" @click="deleteTag(t.id)">&times;</button>
          </span>
          <span v-if="!allTags.length" style="font-size:12px;color:var(--text-3)">暂无标签</span>
        </div>
      </div>

      <!-- Docs list -->
      <div class="card" style="margin-top:14px">
        <div class="list-header">
          <span class="section-hd" style="margin:0">文档列表 <span class="count-badge">{{ docs.length }}</span></span>
          <div style="display:flex;gap:6px;align-items:center">
            <select v-model="filterTag" class="tag-filter" @change="loadDocs">
              <option value="">全部标签</option>
              <option v-for="t in allTags" :key="t.id" :value="t.name">{{ t.name }}</option>
            </select>
            <button class="btn btn-ghost btn-sm" @click="loadDocs">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
              刷新
            </button>
            <button v-if="selectedIds.length" class="btn btn-danger btn-sm" @click="batchDelete">
              &#128465; 删除选中 ({{ selectedIds.length }})
            </button>
          </div>
        </div>

        <div v-if="docsLoading" class="empty-row"><span class="dots"><span/><span/><span/></span></div>
        <div v-else-if="!docs.length" class="empty-row" style="color:var(--text-3)">暂无文档，请上传</div>

        <table v-else class="data-table" style="margin-top:12px">
          <thead>
            <tr><th style="width:32px"><input type="checkbox" @change="selectAll" :checked="selectedIds.length===docs.length&&docs.length>0"></th><th>文件名</th><th>类型</th><th>标签</th><th>版本</th><th>状态</th><th>质量分</th><th>分块数</th><th>大小</th><th>时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="doc in docs" :key="doc.id" :class="{ 'row-selected': selectedIds.includes(doc.id) }">
              <td><input type="checkbox" :checked="selectedIds.includes(doc.id)" @change="toggleSelect(doc.id)"></td>
              <td class="doc-name" :title="doc.filename">{{ doc.filename }}</td>
              <td><span class="badge badge-gray">{{ doc.file_type }}</span></td>
              <td>
                <div class="doc-tags">
                  <span v-for="t in (docTagsMap[doc.id]||[])" :key="t.id" class="tag-mini" :style="{background:t.color+'20',color:t.color}">
                    {{ t.name }}
                    <button class="tag-mini-del" @click="unbindTag(doc.id, t.id)">&times;</button>
                  </span>
                  <button class="tag-add-btn" @click="openTagBind(doc)" title="添加标签">+</button>
                </div>
              </td>
              <td><span class="badge badge-gray">v{{ doc.doc_version || 1 }}</span></td>
              <td>
                <span class="badge" :class="statusBadge(doc.status)">{{ statusLabel(doc.status) }}</span>
                <span v-if="doc.status==='processing'" class="proc-dot"></span>
              </td>
              <td>
                <div class="score-wrap">
                  <div class="score-bar"><div class="score-fill" :style="{width:(doc.parse_score*100)+'%',background:scoreColor(doc.parse_score)}"/></div>
                  <span class="score-num">{{ (doc.parse_score*100).toFixed(0) }}%</span>
                </div>
              </td>
              <td>{{ doc.chunk_count }}</td>
              <td>{{ fmtSize(doc.file_size) }}</td>
              <td class="time-cell">{{ fmtDate(doc.created_at) }}</td>
              <td>
                <div class="action-btns">
                  <button v-if="doc.status==='done' && doc.chunk_count" class="btn btn-ghost btn-sm" @click="openChunks(doc)">查看分块</button>
                  <button v-if="isAdmin" class="btn btn-ghost btn-sm" @click="openPerms(doc)" title="权限管理">&#128274; 权限</button>
                  <button v-if="['failed','processing','pending'].includes(doc.status)" class="btn btn-accent btn-sm" @click="retryDoc(doc.id)">重试</button>
                  <button class="btn btn-danger btn-sm" @click="remove(doc.id)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 失败详情 -->
      <div v-if="docs.some(d=>d.error_msg)" class="card err-card" style="margin-top:14px">
        <div class="section-hd" style="color:var(--red)">处理失败详情</div>
        <div v-for="doc in docs.filter(d=>d.error_msg)" :key="doc.id" class="err-row">
          <span class="err-name">{{ doc.filename }}</span>
          <span class="err-msg">{{ doc.error_msg }}</span>
          <button v-if="['failed','processing','pending'].includes(doc.status)" class="btn btn-accent btn-sm" style="margin-left:auto;flex-shrink:0" @click="retryDoc(doc.id)">重试</button>
        </div>
      </div>

      <!-- ── Chunk 浏览弹窗（升级版） ── -->
      <div v-if="chunkModal" class="modal-overlay" @click.self="chunkModal=false">
        <div class="modal-box" style="width:920px">
          <div class="modal-header">
            <span class="modal-title">分块浏览 &#183; {{ chunkDocName }}</span>
            <span class="chunk-count">共 {{ chunkTotal }} 块</span>
            <button class="modal-close" @click="chunkModal=false">&times;</button>
          </div>

          <!-- Filter bar -->
          <div class="chunk-filter-bar">
            <div class="filter-type-btns">
              <button v-for="t in chunkTypeOptions" :key="t.value"
                :class="['filter-btn', { active: chunkFilterType === t.value }]"
                @click="chunkFilterType = t.value">{{ t.label }}</button>
            </div>
            <div class="filter-search">
              <input v-model="chunkSearchQuery" placeholder="搜索分块内容..." class="search-input" />
            </div>
          </div>

          <!-- Filter rate warning -->
          <div v-if="chunkFilterRate > 0.3" class="filter-warning">
            当前过滤比例 {{ (chunkFilterRate * 100).toFixed(0) }}%，建议调整分块策略或文档内容
          </div>

          <div class="modal-body chunk-layout">
            <!-- Left: Chunk list -->
            <div class="chunk-list-panel">
              <div v-if="chunkLoading" class="empty-row"><span class="dots"><span/><span/><span/></span></div>
              <div v-else-if="!chunkList.length" class="empty-row" style="color:var(--text-3)">暂无分块数据</div>
              <div v-else class="chunk-list">
                <div v-for="c in filteredChunks" :key="c.id"
                  :class="['chunk-item', { 'chunk-selected': selectedChunk?.id === c.id }]"
                  @click="selectChunk(c)">
                  <div class="chunk-head">
                    <span class="chunk-idx">#{{ c.chunk_idx }}</span>
                    <span class="chunk-chars">{{ c.char_count }} 字</span>
                    <span v-if="c.structure_type" class="chunk-type-badge">{{ structureTypeLabel(c.structure_type) }}</span>
                    <span v-if="c.quality_score != null" :class="['chunk-quality', qualityClass(c.quality_score)]">{{ (c.quality_score * 100).toFixed(0) }}</span>
                  </div>
                  <div class="chunk-text">{{ c.content }}</div>
                </div>
              </div>
            </div>

            <!-- Right: Detail panel -->
            <div class="chunk-detail-panel">
              <div v-if="!selectedChunk" class="empty-row" style="color:var(--text-3);padding-top:60px">点击左侧分块查看详情</div>
              <template v-else>
                <div class="detail-tabs">
                  <button :class="['tab-btn', { active: chunkDetailTab === 'content' }]" @click="chunkDetailTab = 'content'">内容</button>
                  <button :class="['tab-btn', { active: chunkDetailTab === 'metadata' }]" @click="chunkDetailTab = 'metadata'">元数据</button>
                  <button :class="['tab-btn', { active: chunkDetailTab === 'graph' }]" @click="chunkDetailTab = 'graph'">引用关系</button>
                </div>
                <div class="detail-content">
                  <!-- Tab: Content -->
                  <div v-if="chunkDetailTab === 'content'" class="detail-content-pane">
                    <div class="detail-content-text">{{ selectedChunk.content }}</div>
                  </div>
                  <!-- Tab: Metadata -->
                  <div v-if="chunkDetailTab === 'metadata'" class="detail-meta-pane">
                    <div class="meta-row"><span class="meta-key">chunk_id</span><span class="meta-val">{{ selectedChunk.id }}</span></div>
                    <div class="meta-row"><span class="meta-key">chunk_index</span><span class="meta-val">{{ selectedChunk.chunk_index }}</span></div>
                    <div class="meta-row"><span class="meta-key">char_count</span><span class="meta-val">{{ selectedChunk.char_count }}</span></div>
                    <div class="meta-row"><span class="meta-key">structure_type</span><span class="meta-val">{{ selectedChunk.structure_type || '-' }}</span></div>
                    <div class="meta-row"><span class="meta-key">quality_score</span><span class="meta-val">{{ selectedChunk.quality_score }}</span></div>
                    <div class="meta-row"><span class="meta-key">language</span><span class="meta-val">{{ selectedChunk.language || '-' }}</span></div>
                    <div class="meta-row"><span class="meta-key">parent_chunk_id</span><span class="meta-val">{{ selectedChunk.parent_chunk_id || '-' }}</span></div>
                    <div class="meta-row"><span class="meta-key">token_count</span><span class="meta-val">{{ selectedChunk.token_count }}</span></div>
                    <div class="meta-row"><span class="meta-key">embedding_model</span><span class="meta-val">{{ selectedChunk.embedding_model || '-' }}</span></div>
                  </div>
                  <!-- Tab: Graph -->
                  <div v-if="chunkDetailTab === 'graph'" class="detail-graph-pane">
                    <ChunkGraph
                      v-if="selectedChunk"
                      :currentChunk="selectedChunk"
                      :parentChunk="selectedChunk.parent_chunk"
                      :prevChunk="selectedChunk.prev_chunk"
                      :nextChunk="selectedChunk.next_chunk"
                      @navigate="navigateToChunk" />
                  </div>
                </div>
              </template>
            </div>
          </div>

          <div class="modal-footer">
            <button class="btn btn-ghost btn-sm" :disabled="chunkPage===0" @click="chunkPrev">上一页</button>
            <span class="page-info">第 {{ chunkPage+1 }} / {{ Math.max(1, Math.ceil(chunkTotal/CHUNK_LIMIT)) }} 页</span>
            <button class="btn btn-ghost btn-sm" :disabled="(chunkPage+1)*CHUNK_LIMIT>=chunkTotal" @click="chunkNext">下一页</button>
          </div>
        </div>
      </div>

      <!-- URL 导入弹窗 -->
      <div v-if="urlModal" class="modal-overlay" @click.self="urlModal=false">
        <div class="modal-box" style="width:500px">
          <div class="modal-header">
            <span class="modal-title">URL 导入</span>
            <button class="modal-close" @click="urlModal=false">&times;</button>
          </div>
          <div class="modal-body">
            <p style="font-size:12px;color:var(--text-3);margin-bottom:8px">每行一个 URL，最多 20 个</p>
            <textarea v-model="urlText" class="url-textarea" rows="6" placeholder="https://example.com/page1&#10;https://example.com/page2"/>
          </div>
          <div class="modal-footer" style="justify-content:flex-end;gap:8px">
            <button class="btn btn-ghost btn-sm" @click="urlModal=false">取消</button>
            <button class="btn btn-primary btn-sm" @click="doUrlImport" :disabled="urlImporting">
              {{ urlImporting ? '导入中…' : '开始导入' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 标签绑定弹窗 -->
      <div v-if="tagBindModal" class="modal-overlay" @click.self="tagBindModal=false">
        <div class="modal-box" style="width:360px">
          <div class="modal-header">
            <span class="modal-title">为文档添加标签</span>
            <button class="modal-close" @click="tagBindModal=false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="tag-bind-list">
              <label v-for="t in allTags" :key="t.id" class="tag-bind-item">
                <input type="checkbox" :checked="isTagBound(t.id)" @change="toggleTagBind(t.id, $event)"/>
                <span class="tag-chip-sm" :style="{background:t.color+'20',color:t.color}">{{ t.name }}</span>
              </label>
              <span v-if="!allTags.length" style="font-size:12px;color:var(--text-3)">请先创建标签</span>
            </div>
          </div>
          <div class="modal-footer" style="justify-content:flex-end">
            <button class="btn btn-ghost btn-sm" @click="tagBindModal=false">关闭</button>
          </div>
        </div>
      </div>

      <!-- 权限管理弹窗（仅管理员可见） -->
      <div v-if="permModal" class="modal-overlay" @click.self="permModal=false">
        <div class="modal-box" style="width:480px">
          <div class="modal-header">
            <span class="modal-title">&#128274; 权限管理 &#183; {{ permDocName }}</span>
            <button class="modal-close" @click="permModal=false">&times;</button>
          </div>
          <div class="modal-body">
            <p style="font-size:12px;color:var(--text-3);margin-bottom:10px">
              控制哪些部门 / 用户可以访问此文档。未设置时文档对所有人可见。
            </p>
            <!-- 已有权限列表 -->
            <div v-if="permLoading" class="empty-row"><span class="dots"><span/><span/><span/></span></div>
            <table v-else-if="permList.length" class="data-table" style="margin-bottom:12px">
              <thead><tr><th>类型</th><th>作用域值</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="p in permList" :key="p.id">
                  <td><span class="badge badge-blue">{{ p.scope_type }}</span></td>
                  <td>{{ p.scope_value }}</td>
                  <td><button class="btn btn-danger btn-sm" @click="removePerm(p.id)">移除</button></td>
                </tr>
              </tbody>
            </table>
            <p v-else style="font-size:12px;color:var(--text-3);margin-bottom:10px">暂无权限记录</p>
            <!-- 添加新权限 -->
            <div class="perm-add-row">
              <select v-model="newPermType" class="input-base" style="width:120px">
                <option value="public">public（全员）</option>
                <option value="tenant">tenant（同租户）</option>
                <option value="dept">dept（部门）</option>
                <option value="user">user（指定用户）</option>
              </select>
              <input v-model="newPermValue" class="input-base" style="flex:1"
                :placeholder="newPermType==='public'?'值填 *':newPermType==='dept'?'部门ID':'用户ID / 租户ID'"/>
              <button class="btn btn-primary btn-sm" @click="addPerm" :disabled="!newPermValue.trim()">添加</button>
            </div>
          </div>
          <div class="modal-footer" style="justify-content:flex-end">
            <button class="btn btn-ghost btn-sm" @click="permModal=false">关闭</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { apiUpload, apiListDocs, apiDeleteDoc, apiRetryDoc, apiDocChunks, apiBatchUpload, apiUrlImport, apiListTags, apiCreateTag, apiDeleteTag, apiBindDocTag, apiUnbindDocTag, apiDocTags, apiGetDocPermissions, apiAddDocPermission, apiRemoveDocPermission, getChunkDetail, getChunkingProgress, getChunkingReport } from '@/api/index.js'
import ChunkGraph from '@/components/ChunkGraph.vue'
import ChunkingPipeline from '@/components/ChunkingPipeline.vue'

const docs        = ref([])
const queue       = ref([])
const dragging    = ref(false)
const docsLoading = ref(false)
const selectedIds   = ref([])
let refreshTimer    = null
const overwriteMode = ref(false)
const filterTag   = ref('')

// Current user role (from session)
const isAdmin = computed(() => {
  try { return JSON.parse(sessionStorage.getItem('rag_user') || '{}').role === 'admin' || JSON.parse(sessionStorage.getItem('rag_user') || '{}').role === 'super_admin' } catch { return false }
})

// Tags
const allTags     = ref([])
const newTagName  = ref('')
const newTagColor = ref('#4f7ef8')
const docTagsMap  = ref({})  // { doc_id: [tag, ...] }

// Tag bind modal
const tagBindModal  = ref(false)
const tagBindDocId  = ref('')

// Permission modal
const permModal    = ref(false)
const permDocId    = ref('')
const permDocName  = ref('')
const permList     = ref([])
const permLoading  = ref(false)
const newPermType  = ref('dept')
const newPermValue = ref('')

// URL import modal
const urlModal     = ref(false)
const urlText      = ref('')
const urlImporting = ref(false)

// Chunk 浏览（升级版）
const chunkModal    = ref(false)
const chunkDocName  = ref('')
const chunkDocId    = ref('')
const chunkList     = ref([])
const chunkTotal    = ref(0)
const chunkLoading  = ref(false)
const chunkPage     = ref(0)
const CHUNK_LIMIT   = 20
// Chunk filter & detail
const chunkFilterType  = ref('')
const chunkSearchQuery = ref('')
const selectedChunk    = ref(null)
const chunkDetailTab   = ref('content')
const chunkTypeOptions = [
  { value: '', label: '全部' },
  { value: 'narrative', label: '叙事' },
  { value: 'procedure', label: '步骤' },
  { value: 'api', label: 'API' },
  { value: 'table', label: '表格' },
  { value: 'code', label: '代码' },
]

onMounted(() => {
  loadDocs()
  loadTags()
  connectWS()
  // Auto-refresh document list every 30s
  refreshTimer = setInterval(loadDocs, 30000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
  wsStopRetry = true
  if (ws) { try { ws.close() } catch (e) { console.error(e) } ; ws = null }
})

let ws = null
let wsRetries = 0
let wsStopRetry = false
function connectWS() {
  // token 不存在时不发起连接
  const token = sessionStorage.getItem('rag_token') || ''
  if (!token) return
  if (ws) { try { ws.close() } catch (e) { console.error(e) } }
  wsStopRetry = false
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/ws/progress`)
  ws.onopen = () => {
    wsRetries = 0
    // 通过消息发送 token，避免 URL 泄露凭证
    ws.send(JSON.stringify({ type: 'auth', token }))
  }
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'doc_status') {
        // 收到文档状态变更，刷新列表
        loadDocs()
        if (msg.status === 'done') {
          notify(`文档处理完成`); $toast.success('文档处理完成')
        } else if (msg.status === 'failed') {
          notify(`文档处理失败`); $toast.error(`文档处理失败: ${msg.error || '未知错误'}`)
        }
      }
    } catch (e) { console.error(e) }
  }
  ws.onclose = (e) => {
    // 认证拒绝（1008）或组件已卸载时不再重试
    if (wsStopRetry || e.code === 1008 || e.code === 1003) return
    if (wsRetries < 5) {
      const delay = Math.min(5000 * Math.pow(2, wsRetries), 30000)
      wsRetries++
      setTimeout(connectWS, delay)
    }
  }
  ws.onerror = () => ws.close()
}

function notify(text) {
  if (Notification.permission === 'granted') {
    new Notification('RAG 知识库', { body: text })
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission()
  }
}

async function loadDocs() {
  docsLoading.value = true
  try {
    const result = await apiListDocs(0, 100, filterTag.value)
    docs.value = result.docs || result || []
    // load tags for each doc
    await loadDocTags()
  }
  catch (e) { console.error(e) }
  finally { docsLoading.value = false }
}

// ── Tags ──
async function loadTags() {
  try { allTags.value = await apiListTags() || [] } catch (e) { console.error(e) }
}

async function loadDocTags() {
  const map = {}
  await Promise.all(docs.value.map(async d => {
    try { map[d.id] = await apiDocTags(d.id) || [] } catch { map[d.id] = [] }
  }))
  docTagsMap.value = map
}

async function createTag() {
  if (!newTagName.value.trim()) return
  try {
    await apiCreateTag(newTagName.value.trim(), newTagColor.value)
    newTagName.value = ''
    await loadTags()
  } catch (e) { $toast.error('创建标签失败: ' + e) }
}

async function deleteTag(id) {
  if (!confirm('确认删除此标签？')) return
  try { await apiDeleteTag(id); await loadTags(); await loadDocTags() }
  catch (e) { $toast.error('删除失败: ' + e) }
}

function openTagBind(doc) {
  tagBindDocId.value = doc.id
  tagBindModal.value = true
}

function isTagBound(tagId) {
  return (docTagsMap.value[tagBindDocId.value] || []).some(t => t.id === tagId)
}

async function toggleTagBind(tagId, event) {
  const bind = event.target.checked
  try {
    if (bind) {
      await apiBindDocTag(tagBindDocId.value, tagId)
    } else {
      await apiUnbindDocTag(tagBindDocId.value, tagId)
    }
    await loadDocTags()
    await loadTags()
  } catch (e) { $toast.error('操作失败: ' + e) }
}

async function unbindTag(docId, tagId) {
  try { await apiUnbindDocTag(docId, tagId); await loadDocTags(); await loadTags() }
  catch (e) { $toast.error('操作失败: ' + e) }
}

// ── ZIP batch upload ──
async function onZipUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  e.target.value = ''
  const item = reactive({ name: file.name, status: 'uploading', error: '' })
  queue.value.push(item)
  try {
    const fd = new FormData()
    fd.append('file', file)
    await apiBatchUpload(fd)
    item.status = 'ok'
    setTimeout(loadDocs, 2000)
  } catch (err) {
    item.status = 'error'
    item.error = typeof err === 'string' ? err : 'ZIP 上传失败'
  }
}

// ── URL import ──
async function doUrlImport() {
  const urls = urlText.value.split('\n').map(u => u.trim()).filter(Boolean)
  if (!urls.length) { $toast.warning('请输入至少一个 URL'); return }
  if (urls.length > 20) { $toast.warning('最多 20 个 URL'); return }
  urlImporting.value = true
  try {
    await apiUrlImport(urls)
    urlModal.value = false
    urlText.value = ''
    setTimeout(loadDocs, 2000)
  } catch (e) {
    $toast.error('导入失败: ' + e)
  } finally { urlImporting.value = false }
}

function onFileChange(e) { processFiles([...e.target.files]); e.target.value = '' }
function onDrop(e) { dragging.value = false; processFiles([...e.dataTransfer.files]) }

function processFiles(files) {
  files.forEach(file => {
    const item = reactive({ name: file.name, status: 'uploading', error: '' })
    queue.value.push(item)
    doUpload(file, item)
  })
}

async function doUpload(file, item) {
  const fd = new FormData(); fd.append('file', file)
  try {
    await apiUpload(fd, overwriteMode.value)
    item.status = 'ok'
    setTimeout(loadDocs, 2000)
  } catch (e) {
    item.status = 'error'; item.error = typeof e === 'string' ? e : '上传失败'
  }
}

function toggleSelect(id) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}
function selectAll(e) {
  selectedIds.value = e.target.checked ? docs.value.map(d => d.id) : []
}
async function batchDelete() {
  if (!confirm(`确定删除选中的 ${selectedIds.value.length} 个文档？此操作不可撤销。`)) return
  let ok = 0, fail = 0
  for (const id of [...selectedIds.value]) {
    try { await apiDeleteDoc(id); ok++; selectedIds.value = selectedIds.value.filter(x => x !== id) }
    catch (e) { fail++; $toast.error('删除失败: ' + e) }
  }
  if (ok) $toast.success(`成功删除 ${ok} 个文档` + (fail ? `，${fail} 个失败` : ''))
  loadDocs()
}
async function remove(id) {
  if (!confirm('确认删除该文档及所有相关向量数据？')) return
  try { await apiDeleteDoc(id); await loadDocs() }
  catch (e) { $toast.error('删除失败: ' + e) }
}

async function retryDoc(id) {
  try {
    await apiRetryDoc(id)
    await loadDocs()
  } catch (e) {
    $toast.error('重试失败: ' + e)
  }
}

async function openChunks(doc) {
  chunkDocId.value = doc.id
  chunkDocName.value = doc.filename
  chunkPage.value = 0
  chunkList.value = []
  chunkTotal.value = doc.chunk_count || 0
  chunkFilterType.value = ''
  chunkSearchQuery.value = ''
  selectedChunk.value = null
  chunkDetailTab.value = 'content'
  chunkModal.value = true
  await loadChunks()
}

async function loadChunks() {
  chunkLoading.value = true
  try {
    const data = await apiDocChunks(chunkDocId.value, chunkPage.value * CHUNK_LIMIT, CHUNK_LIMIT)
    chunkList.value = data.chunks || []
    chunkTotal.value = data.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    chunkLoading.value = false
  }
}

async function chunkPrev() {
  if (chunkPage.value > 0) { chunkPage.value--; await loadChunks() }
}
async function chunkNext() {
  if ((chunkPage.value + 1) * CHUNK_LIMIT < chunkTotal.value) { chunkPage.value++; await loadChunks() }
}

// ── Chunk filter & detail ──
const filteredChunks = computed(() => {
  let list = chunkList.value
  if (chunkFilterType.value) {
    list = list.filter(c => c.structure_type === chunkFilterType.value)
  }
  if (chunkSearchQuery.value) {
    const q = chunkSearchQuery.value.toLowerCase()
    list = list.filter(c => (c.content || '').toLowerCase().includes(q))
  }
  return list
})

const chunkFilterRate = computed(() => {
  if (!chunkList.value.length) return 0
  return 1 - (filteredChunks.value.length / chunkList.value.length)
})

function selectChunk(chunk) {
  selectedChunk.value = chunk
  chunkDetailTab.value = 'content'
  if (!chunk.parent_chunk && !chunk.parent_chunk_id) {
    loadChunkDetail(chunk.id)
  }
}

async function loadChunkDetail(chunkId) {
  try {
    const detail = await getChunkDetail(chunkDocId.value, chunkId)
    if (detail && selectedChunk.value?.id === chunkId) {
      selectedChunk.value = { ...selectedChunk.value, ...detail }
    }
  } catch (e) {
    console.error(e)
  }
}

function navigateToChunk(chunkId) {
  const found = chunkList.value.find(c => c.id === chunkId)
  if (found) {
    selectChunk(found)
  }
}

function structureTypeLabel(type) {
  const labels = { narrative: '叙事', procedure: '步骤', api: 'API', table: '表格', code: '代码' }
  return labels[type] || type
}

function qualityClass(score) {
  if (score >= 0.8) return 'quality-high'
  if (score >= 0.5) return 'quality-mid'
  return 'quality-low'
}

// ── Permissions ──
async function openPerms(doc) {
  permDocId.value = doc.id
  permDocName.value = doc.filename
  permList.value = []
  newPermType.value = 'dept'
  newPermValue.value = ''
  permModal.value = true
  await loadPerms()
}
async function loadPerms() {
  permLoading.value = true
  try { permList.value = await apiGetDocPermissions(permDocId.value) || [] }
  catch (e) { console.error(e) }
  finally { permLoading.value = false }
}
async function addPerm() {
  const val = newPermType.value === 'public' ? '*' : newPermValue.value.trim()
  if (!val) return
  try {
    await apiAddDocPermission(permDocId.value, newPermType.value, val)
    newPermValue.value = ''
    await loadPerms()
  } catch (e) { $toast.error('添加权限失败: ' + e) }
}
async function removePerm(permId) {
  try { await apiRemoveDocPermission(permDocId.value, permId); await loadPerms() }
  catch (e) { $toast.error('移除失败: ' + e) }
}

const statusLabel = s => ({ pending:'等待中', processing:'处理中', done:'完成', failed:'失败' }[s] || s)
const statusBadge = s => ({ pending:'badge-gray', processing:'badge-blue', done:'badge-green', failed:'badge-red' }[s] || 'badge-gray')

function scoreColor(v) {
  if (v >= 0.8) return 'var(--green)'
  if (v >= 0.6) return 'var(--yellow)'
  return 'var(--red)'
}
function fmtSize(b) {
  if (!b) return '-'
  if (b < 1024) return b + 'B'
  if (b < 1048576) return (b/1024).toFixed(1) + 'KB'
  return (b/1048576).toFixed(1) + 'MB'
}
function fmtDate(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false })
}
</script>

<style scoped>
.upload-zone {
  border:2px dashed rgba(0,243,255,0.25); text-align:center;
  padding:40px 20px; cursor:pointer; transition:all .3s;
  display:flex; flex-direction:column; align-items:center; gap:8px;
  background:rgba(0,243,255,0.02);
}
.upload-zone:hover, .upload-zone.dragging {
  border-color:#00f3ff;
  background:rgba(0,243,255,0.05);
  box-shadow:0 0 20px rgba(0,243,255,0.08);
}
.upload-icon { color:var(--text-3); margin-bottom:4px; }
.upload-zone:hover .upload-icon, .upload-zone.dragging .upload-icon { color:#00f3ff; filter:drop-shadow(0 0 4px rgba(0,243,255,0.4)); }
.upload-title { font-size:14px; font-weight:600; color:var(--text-2); }
.upload-zone:hover .upload-title { color:#00f3ff; }
.upload-hint  { font-size:12px; color:var(--text-3); }

.section-hd {
  font-family:"Orbitron",sans-serif;
  font-size:11px; font-weight:600; color:#00f3ff;
  margin-bottom:10px; letter-spacing:0.5px;
}
.count-badge {
  display:inline-block; padding:0 6px; border-radius:99px;
  background:rgba(0,243,255,0.08); color:#00f3ff; font-size:11px; margin-left:6px;
  font-family:"JetBrains Mono",monospace;
}
.list-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }

.queue-row { display:flex; align-items:center; gap:8px; padding:7px 0; border-bottom:1px solid rgba(0,243,255,0.05); font-size:12px; }
.queue-row:last-child { border-bottom:none; }
.q-icon { width:18px; display:flex; align-items:center; justify-content:center; }
.q-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-2); }
.q-err  { color:#ff006e; font-size:11px; }

.doc-name { max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-1); }
.score-wrap { display:flex; align-items:center; gap:5px; }
.score-bar  { width:48px; height:4px; background:rgba(0,243,255,0.08); border-radius:2px; overflow:hidden; }
.score-fill { height:100%; border-radius:2px; transition:width .3s; }
.score-num  { font-size:11px; color:var(--text-3); font-family:"JetBrains Mono",monospace; }
.time-cell  { font-size:11px; color:var(--text-3); white-space:nowrap; font-family:"JetBrains Mono",monospace; }
.proc-dot   {
  display:inline-block; width:6px; height:6px; border-radius:50%;
  background:#00f3ff; animation:pulse 1s infinite; margin-left:4px;
  box-shadow:0 0 6px rgba(0,243,255,0.5);
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

.empty-row { padding:30px; text-align:center; font-size:13px; }
.err-card  { border-color:rgba(255,0,110,0.2); }
.err-row   { display:flex; gap:10px; padding:6px 0; font-size:12px; border-bottom:1px solid rgba(0,243,255,0.05); }
.err-row:last-child { border-bottom:none; }
.err-name  { font-weight:500; color:var(--text-2); min-width:120px; }
.err-msg   { color:#ff006e; flex:1; }

.action-btns { display:flex; gap:4px; }

/* ── Modal ── */
.modal-overlay {
  position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:1000;
  display:flex; align-items:center; justify-content:center;
  backdrop-filter:blur(5px);
}
.modal-box {
  background:rgba(21,25,50,0.95); border:1px solid rgba(0,243,255,0.2);
  border-radius:14px; width:680px; max-width:90vw; max-height:80vh;
  display:flex; flex-direction:column;
  box-shadow:0 0 40px rgba(0,243,255,0.05);
  backdrop-filter:blur(20px);
}
.modal-header {
  display:flex; align-items:center; gap:10px;
  padding:14px 18px; border-bottom:1px solid rgba(0,243,255,0.1);
}
.modal-title {
  font-family:"Orbitron",sans-serif;
  font-size:12px; font-weight:600; color:#00f3ff; letter-spacing:1px;
}
.chunk-count {
  font-size:11px; color:var(--text-3); padding:2px 7px;
  background:rgba(0,243,255,0.05); border-radius:99px;
  font-family:"JetBrains Mono",monospace;
}
.modal-close {
  margin-left:auto; background:none; border:none; cursor:pointer;
  font-size:20px; color:var(--text-3); padding:0 4px; line-height:1;
  transition:color .2s;
}
.modal-close:hover { color:#ff006e; }
.modal-body { flex:1; overflow-y:auto; padding:14px 18px; }
.modal-footer {
  display:flex; align-items:center; justify-content:center; gap:12px;
  padding:10px 18px; border-top:1px solid rgba(0,243,255,0.1);
}
.page-info { font-size:12px; color:var(--text-3); font-family:"JetBrains Mono",monospace; }

/* ── Chunk Filter Bar ── */
.chunk-filter-bar {
  display:flex; align-items:center; gap:10px;
  padding:10px 18px; border-bottom:1px solid rgba(0,243,255,0.08);
}
.filter-type-btns { display:flex; gap:4px; flex-shrink:0; }
.filter-btn {
  padding:3px 10px; font-size:11px; border-radius:99px; border:1px solid rgba(0,243,255,0.15);
  background:transparent; color:var(--text-3); cursor:pointer; transition:all .2s;
}
.filter-btn:hover { border-color:#00f3ff; color:#00f3ff; }
.filter-btn.active { background:rgba(0,243,255,0.12); border-color:#00f3ff; color:#00f3ff; }
.filter-search { flex:1; }
.search-input {
  width:100%; padding:4px 10px; border:1px solid rgba(0,243,255,0.12); border-radius:99px;
  background:rgba(10,14,39,0.5); color:var(--text-1); font-size:12px; outline:none;
  transition:all .2s;
}
.search-input:focus { border-color:#00f3ff; box-shadow:0 0 8px rgba(0,243,255,0.08); }

/* ── Filter Warning Banner ── */
.filter-warning {
  margin:0 18px; padding:6px 12px; background:rgba(255,183,0,0.1);
  border:1px solid rgba(255,183,0,0.25); border-radius:6px;
  font-size:11px; color:var(--yellow); display:flex; align-items:center; gap:6px;
}

/* ── Chunk Layout (left list + right detail) ── */
.chunk-layout { display:flex; gap:14px; padding:14px 18px; overflow:hidden; }
.chunk-list-panel { flex:1; overflow-y:auto; max-height:55vh; }
.chunk-detail-panel { width:340px; flex-shrink:0; overflow-y:auto; max-height:55vh; border-left:1px solid rgba(0,243,255,0.08); padding-left:14px; }

/* ── Chunk Items (upgraded) ── */
.chunk-list { display:flex; flex-direction:column; gap:6px; }
.chunk-item {
  border:1px solid rgba(0,243,255,0.1); border-radius:8px; overflow:hidden;
  transition:border-color .2s; cursor:pointer;
}
.chunk-item:hover { border-color:rgba(0,243,255,0.25); }
.chunk-item.chunk-selected { border-color:#00f3ff; border-width:2px; }
.chunk-head {
  display:flex; align-items:center; gap:6px;
  padding:5px 10px; background:rgba(0,243,255,0.03); font-size:11px;
}
.chunk-idx { font-weight:700; color:#00f3ff; font-family:"Orbitron",sans-serif; font-size:10px; }
.chunk-chars { color:var(--text-4); font-family:"JetBrains Mono",monospace; font-size:10px; }
.chunk-type-badge {
  padding:1px 5px; border-radius:4px; font-size:9px;
  background:rgba(0,243,255,0.08); color:#00f3ff; margin-left:auto;
}
.chunk-quality {
  font-family:"JetBrains Mono",monospace; font-size:9px; padding:1px 4px; border-radius:4px;
}
.chunk-quality.quality-high { background:rgba(0,200,83,0.15); color:var(--green); }
.chunk-quality.quality-mid { background:rgba(255,183,0,0.15); color:var(--yellow); }
.chunk-quality.quality-low { background:rgba(255,0,110,0.15); color:var(--red); }
.chunk-text {
  padding:8px 10px; font-size:12px; line-height:1.6;
  color:var(--text-2); white-space:pre-wrap; word-break:break-all;
  max-height:80px; overflow:hidden;
}

/* ── Detail Panel ── */
.detail-tabs { display:flex; gap:2px; border-bottom:1px solid rgba(0,243,255,0.08); margin-bottom:10px; }
.tab-btn {
  padding:6px 12px; font-size:11px; border:none; background:transparent;
  color:var(--text-3); cursor:pointer; border-bottom:2px solid transparent;
  transition:all .2s;
}
.tab-btn:hover { color:var(--text-1); }
.tab-btn.active { color:#00f3ff; border-bottom-color:#00f3ff; }
.detail-content { font-size:12px; }
.detail-content-text {
  font-size:12px; line-height:1.7; color:var(--text-2);
  white-space:pre-wrap; word-break:break-all;
  max-height:400px; overflow-y:auto;
}
.detail-meta-pane { display:flex; flex-direction:column; gap:4px; }
.meta-row {
  display:flex; justify-content:space-between; align-items:center;
  padding:4px 0; border-bottom:1px solid rgba(0,243,255,0.04);
}
.meta-key {
  font-size:10px; color:var(--text-4); font-family:"JetBrains Mono",monospace;
  text-transform:uppercase;
}
.meta-val {
  font-size:11px; color:var(--text-2); font-family:"JetBrains Mono",monospace;
  max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  text-align:right;
}
.detail-graph-pane { min-height:120px; }

/* ── Overwrite opt ── */
.overwrite-opt {
  display:flex; align-items:center; gap:6px; margin-top:8px;
  font-size:11px; color:var(--text-3); cursor:pointer;
}
.overwrite-opt input { cursor:pointer; accent-color:#00f3ff; }

/* ── Tags ── */
.tag-input {
  padding:4px 8px; border:1px solid rgba(0,243,255,0.15); border-radius:var(--r-sm);
  background:rgba(10,14,39,0.6); color:var(--text-1); font-size:12px; width:120px; outline:none;
  transition:all .2s;
}
.tag-input:focus { border-color:#00f3ff; box-shadow:0 0 8px rgba(0,243,255,0.1); }
.tag-color-input { width:28px; height:28px; border:none; cursor:pointer; border-radius:4px; background:transparent; }
.tag-list { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.tag-chip {
  display:inline-flex; align-items:center; gap:4px;
  padding:3px 10px; border-radius:99px; font-size:11px; font-weight:500;
  border:1px solid;
  backdrop-filter:blur(5px);
}
.tag-count { font-size:10px; opacity:.7; font-family:"JetBrains Mono",monospace; }
.tag-del { background:none; border:none; cursor:pointer; color:inherit; font-size:13px; opacity:.6; line-height:1; padding:0 0 0 2px; }
.tag-del:hover { opacity:1; }

.tag-filter {
  padding:4px 8px; border:1px solid rgba(0,243,255,0.15); border-radius:var(--r-sm);
  background:rgba(10,14,39,0.6); color:var(--text-1); font-size:12px; outline:none;
}

.doc-tags { display:flex; flex-wrap:wrap; gap:3px; align-items:center; }
.tag-mini {
  display:inline-flex; align-items:center; gap:2px;
  padding:1px 6px; border-radius:99px; font-size:10px;
}
.tag-mini-del { background:none; border:none; cursor:pointer; color:inherit; font-size:11px; opacity:.5; padding:0; line-height:1; }
.tag-mini-del:hover { opacity:1; }
.tag-add-btn {
  width:18px; height:18px; border-radius:50%; border:1px dashed rgba(0,243,255,0.2);
  background:transparent; color:var(--text-3); cursor:pointer; font-size:12px;
  display:flex; align-items:center; justify-content:center;
  transition:all .2s;
}
.tag-add-btn:hover { border-color:#00f3ff; color:#00f3ff; }

.tag-bind-list { display:flex; flex-direction:column; gap:6px; }
.tag-bind-item { display:flex; align-items:center; gap:8px; cursor:pointer; font-size:13px; }
.tag-bind-item input { accent-color:#00f3ff; }
.tag-chip-sm {
  display:inline-flex; padding:2px 8px; border-radius:99px; font-size:11px; font-weight:500;
}

/* ── URL Modal ── */
.url-textarea {
  width:100%; padding:8px 10px; border:1px solid rgba(0,243,255,0.15); border-radius:var(--r-sm);
  background:rgba(10,14,39,0.6); color:var(--text-1); font-size:12px; resize:vertical; outline:none;
  font-family:"JetBrains Mono",monospace; line-height:1.6;
  transition:all .2s;
}
.url-textarea:focus { border-color:#00f3ff; box-shadow:0 0 8px rgba(0,243,255,0.1); }
.perm-add-row { display:flex; gap:8px; align-items:center; margin-top:12px; }
</style>
