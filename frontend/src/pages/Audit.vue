<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title">审计日志</div>
      <div class="page-sub">操作记录 · 登录追踪 · 安全审计</div>
    </div>
    <div class="page-body">
      <div class="card">
        <!-- 过滤栏 -->
        <div class="filter-row">
          <select v-model="filterAction" class="input-base filter-sel" @change="load">
            <option value="">全部操作</option>
            <option value="login">登录</option>
            <option value="login_fail">登录失败</option>
            <option value="query">查询</option>
            <option value="upload">上传</option>
            <option value="batch_upload">批量上传</option>
            <option value="overwrite_upload">覆盖上传</option>
            <option value="url_import">URL导入</option>
            <option value="delete_doc">删除文档</option>
            <option value="retry_doc">重试解析</option>
            <option value="create_user">创建用户</option>
            <option value="update_user">更新用户</option>
          </select>
          <button class="btn btn-ghost btn-sm" @click="load">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
            刷新
          </button>
          <span class="total-info" v-if="total">共 {{ total }} 条</span>
        </div>

        <div v-if="loading" class="empty-row"><span class="dots"><span/><span/><span/></span></div>
        <div v-else-if="!items.length" class="empty-row">暂无日志</div>
        <table v-else class="data-table" style="margin-top:12px">
          <thead>
            <tr><th>时间</th><th>用户</th><th>操作</th><th>资源</th><th>IP</th><th>Trace ID</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.id" class="clickable-row" @click="openDetail(item)">
              <td class="time-col">{{ fmtDate(item.created_at) }}</td>
              <td>{{ item.username || item.user_id || '-' }}</td>
              <td><span class="action-tag" :class="actionClass(item.action)">{{ actionLabel(item.action) }}</span></td>
              <td class="resource-col" :title="item.resource">{{ (item.resource||'-').slice(0,30) }}</td>
              <td class="mono-col">{{ item.ip || '-' }}</td>
              <td class="trace-col">{{ (item.trace_id||'-').slice(0,12) }}…</td>
            </tr>
          </tbody>
        </table>

        <!-- 分页 -->
        <div class="pager" v-if="total > limit">
          <button class="btn btn-ghost btn-sm" :disabled="page<=1" @click="page--;load()">上一页</button>
          <span class="page-info">第 {{ page }} / {{ Math.ceil(total/limit) }} 页</span>
          <button class="btn btn-ghost btn-sm" :disabled="page>=Math.ceil(total/limit)" @click="page++;load()">下一页</button>
        </div>
      </div>

      <!-- 详情弹窗 -->
      <div v-if="detailItem" class="modal-overlay" @click.self="detailItem=null">
        <div class="detail-modal">
          <div class="detail-hd">
            <span>审计日志详情</span>
            <button class="modal-close" @click="detailItem=null">&times;</button>
          </div>
          <div class="detail-body">
            <div class="detail-row">
              <span class="detail-label">ID</span>
              <span class="detail-val">{{ detailItem.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">时间</span>
              <span class="detail-val">{{ fmtDateFull(detailItem.created_at) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">用户</span>
              <span class="detail-val">{{ detailItem.username || detailItem.user_id || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">操作</span>
              <span class="detail-val"><span class="action-tag" :class="actionClass(detailItem.action)">{{ actionLabel(detailItem.action) }}</span></span>
            </div>
            <div class="detail-row">
              <span class="detail-label">IP 地址</span>
              <span class="detail-val mono-val">{{ detailItem.ip || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Trace ID</span>
              <span class="detail-val mono-val">{{ detailItem.trace_id || '-' }}</span>
            </div>
            <div class="detail-row full">
              <span class="detail-label">资源 / 内容</span>
              <div class="detail-resource">{{ detailItem.resource || '-' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiAuditLogs } from '@/api/index.js'

const items        = ref([])
const total        = ref(0)
const loading      = ref(false)
const page         = ref(1)
const limit        = ref(20)
const filterAction = ref('')
const detailItem   = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await apiAuditLogs(page.value, limit.value, filterAction.value)
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e) { console.error(e) } finally { loading.value = false }
}

function openDetail(item) { detailItem.value = item }

onMounted(load)

const actionLabel = a => ({ login:'登录', login_fail:'登录失败', query:'查询', upload:'上传', batch_upload:'批量上传', overwrite_upload:'覆盖上传', url_import:'URL导入', delete_doc:'删除文档', retry_doc:'重试解析', create_user:'创建用户', update_user:'更新用户' }[a] || a)
const actionClass = a => ({ login:'tag-green', login_fail:'tag-red', query:'tag-blue', upload:'tag-yellow', batch_upload:'tag-yellow', overwrite_upload:'tag-yellow', url_import:'tag-yellow', delete_doc:'tag-red', retry_doc:'tag-blue', create_user:'tag-green', update_user:'tag-green' }[a] || 'tag-gray')

function fmtDate(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false })
}

function fmtDateFull(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false })
}
</script>

<style scoped>
.filter-row { display:flex; align-items:center; gap:10px; margin-bottom:4px; }
.filter-sel { width:140px; }
.total-info { margin-left:auto; font-size:12px; color:var(--text-3); font-family:"JetBrains Mono",monospace; }
.empty-row  { padding:40px; text-align:center; color:var(--text-3); font-size:13px; }
.time-col     { font-size:11px; color:var(--text-3); white-space:nowrap; font-family:"JetBrains Mono",monospace; }
.resource-col { max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mono-col   { font-family:"JetBrains Mono",monospace; font-size:11px; color:var(--text-3); }
.trace-col  { font-family:"JetBrains Mono",monospace; font-size:11px; color:var(--text-3); }
.action-tag { display:inline-flex; align-items:center; padding:2px 7px; border-radius:4px; font-size:11px; font-weight:600; letter-spacing:0.3px; }
.tag-green  { background:rgba(5,255,161,0.1); color:#05ffa1; text-shadow:0 0 6px rgba(5,255,161,0.3); }
.tag-red    { background:rgba(255,0,110,0.08); color:#ff006e; text-shadow:0 0 6px rgba(255,0,110,0.3); }
.tag-blue   { background:rgba(0,243,255,0.08); color:#00f3ff; text-shadow:0 0 6px rgba(0,243,255,0.3); }
.tag-yellow { background:rgba(255,190,11,0.1); color:#ffbe0b; text-shadow:0 0 6px rgba(255,190,11,0.3); }
.tag-gray   { background:rgba(85,92,133,0.15); color:var(--text-2); }
.pager { display:flex; align-items:center; gap:10px; justify-content:center; padding-top:16px; border-top:1px solid rgba(0,243,255,0.08); margin-top:12px; }
.page-info { font-size:12px; color:var(--text-3); font-family:"JetBrains Mono",monospace; }

.clickable-row { cursor:pointer; transition:all .2s; }
.clickable-row:hover td { background:rgba(0,243,255,0.03) !important; }

/* ── Detail Modal ── */
.modal-overlay {
  position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:1000;
  display:flex; align-items:center; justify-content:center;
  backdrop-filter:blur(5px);
}
.detail-modal {
  background:rgba(21,25,50,0.95); border:1px solid rgba(0,243,255,0.2);
  border-radius:14px; width:560px; max-width:90vw; max-height:80vh;
  display:flex; flex-direction:column;
  box-shadow:0 0 40px rgba(0,243,255,0.05);
  backdrop-filter:blur(20px);
}
.detail-hd {
  display:flex; justify-content:space-between; align-items:center;
  padding:14px 18px; border-bottom:1px solid rgba(0,243,255,0.1);
  font-family:"Orbitron",sans-serif;
  font-size:12px; font-weight:600; color:#00f3ff; letter-spacing:1px;
}
.modal-close {
  background:none; border:none; cursor:pointer;
  font-size:20px; color:var(--text-3); line-height:1;
  transition:color .2s;
}
.modal-close:hover { color:#ff006e; }
.detail-body { padding:16px 18px; overflow-y:auto; display:flex; flex-direction:column; gap:12px; }
.detail-row { display:flex; align-items:flex-start; gap:12px; }
.detail-row.full { flex-direction:column; gap:6px; }
.detail-label { font-family:"Orbitron",sans-serif; font-size:9px; font-weight:600; color:#00f3ff; width:80px; flex-shrink:0; letter-spacing:0.5px; text-transform:uppercase; }
.detail-val { font-size:13px; color:var(--text-1); word-break:break-all; }
.mono-val { font-family:"JetBrains Mono",monospace; font-size:12px; color:#00f3ff; }
.detail-resource {
  background:rgba(10,14,39,0.6); border:1px solid rgba(0,243,255,0.1);
  border-radius:var(--r-sm); padding:10px 12px;
  font-family:"JetBrains Mono",monospace;
  font-size:12px; line-height:1.7; color:var(--text-2);
  white-space:pre-wrap; word-break:break-all;
  max-height:200px; overflow-y:auto;
}
</style>
