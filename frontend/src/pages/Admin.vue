<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title">{{ isAdmin ? '用户管理' : '账户设置' }}</div>
      <div class="page-sub">{{ isAdmin ? '用户注册、角色分配、API Key 管理' : '密码修改、API Key 管理' }}</div>
    </div>
    <div class="page-body">
      <!-- Tabs -->
      <div class="tab-bar">
        <button v-for="t in tabs" :key="t.key" class="tab-btn" :class="{active: tab===t.key}" @click="tab=t.key">{{ t.label }}</button>
      </div>

      <!-- ═══ 用户列表 ═══ -->
      <div v-if="tab==='users'" class="card" style="margin-top:14px">
        <div class="list-header">
          <span class="section-hd" style="margin:0">用户列表 <span class="count-badge">{{ userTotal }}</span></span>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" :disabled="usersLoading" @click="loadUsers">刷新</button>
            <button class="btn btn-primary btn-sm" @click="openCreateUser">+ 新建用户</button>
          </div>
        </div>
        <table class="data-table" style="margin-top:10px">
          <thead><tr><th>用户名</th><th>角色</th><th>租户</th><th>部门</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td style="color:var(--text-1);font-weight:500">{{ u.username }}</td>
              <td><span class="badge" :class="roleBadge(u.role)">{{ roleLabel(u.role) }}</span></td>
              <td>{{ u.tenant_id || '-' }}</td>
              <td>{{ u.dept_id || '-' }}</td>
              <td><span class="badge" :class="u.is_active?'badge-green':'badge-red'">{{ u.is_active?'启用':'禁用' }}</span></td>
              <td class="time-cell">{{ fmtDate(u.created_at) }}</td>
              <td>
                <div class="action-btns">
                  <button class="btn btn-ghost btn-sm" @click="openEditUser(u)">编辑</button>
                  <button class="btn btn-sm" :class="u.is_active?'btn-danger':'btn-primary'" @click="toggleActive(u)">
                    {{ u.is_active?'禁用':'启用' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="hasMoreUsers" style="margin-top:14px;text-align:center">
          <button
            class="btn btn-ghost btn-sm"
            :disabled="usersLoading || !nextCursor"
            @click="loadMoreUsers"
          >
            {{ usersLoading ? '加载中…' : '加载更多' }}
          </button>
        </div>
      </div>

      <!-- ═══ 修改密码 ═══ -->
      <div v-if="tab==='password'" class="card" style="margin-top:14px;max-width:420px">
        <div class="section-hd">修改当前用户密码</div>
        <div class="form-group">
          <label>旧密码</label>
          <input type="password" v-model="pwForm.old_password" class="form-input" autocomplete="current-password"/>
        </div>
        <div class="form-group">
          <label>新密码</label>
          <input type="password" v-model="pwForm.new_password" class="form-input" autocomplete="new-password"/>
        </div>
        <div class="form-group">
          <label>确认新密码</label>
          <input type="password" v-model="pwForm.confirm" class="form-input" autocomplete="new-password"/>
        </div>
        <button class="btn btn-primary" style="margin-top:10px" @click="changePw" :disabled="pwLoading">确认修改</button>
        <div v-if="pwMsg" class="form-msg" :class="pwOk?'msg-ok':'msg-err'">{{ pwMsg }}</div>
      </div>

      <!-- ═══ API Key ═══ -->
      <div v-if="tab==='apikeys'" class="card" style="margin-top:14px">
        <div class="list-header">
          <span class="section-hd" style="margin:0">我的 API Key</span>
          <button class="btn btn-primary btn-sm" @click="openCreateKey">+ 新建 Key</button>
        </div>
        <div v-if="newKeyRaw" class="new-key-banner">
          <span>请妥善保存（仅显示一次）：</span>
          <code class="key-code">{{ newKeyRaw }}</code>
          <button class="btn btn-ghost btn-sm" @click="copyKey(newKeyRaw)">复制</button>
        </div>
        <table v-if="apiKeys.length" class="data-table" style="margin-top:10px">
          <thead><tr><th>名称</th><th>前缀</th><th>创建时间</th><th>过期时间</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="k in apiKeys" :key="k.id">
              <td style="color:var(--text-1)">{{ k.name }}</td>
              <td><code style="font-size:12px;color:var(--text-3)">{{ k.prefix }}</code></td>
              <td class="time-cell">{{ fmtDate(k.created_at) }}</td>
              <td class="time-cell">{{ k.expires_at ? fmtDate(k.expires_at) : '永不' }}</td>
              <td><span class="badge" :class="k.is_active?'badge-green':'badge-red'">{{ k.is_active?'有效':'已撤销' }}</span></td>
              <td>
                <button v-if="k.is_active" class="btn btn-danger btn-sm" @click="revokeKey(k.id)">撤销</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-row" style="color:var(--text-3);padding:20px;text-align:center">暂无 API Key</div>
      </div>

      <!-- 新建用户弹窗 -->
      <div v-if="userModal" class="modal-overlay" @click.self="userModal=false">
        <div class="modal-box" style="width:400px">
          <div class="modal-header">
            <span class="modal-title">{{ editingUser ? '编辑用户' : '新建用户' }}</span>
            <button class="modal-close" @click="userModal=false">&times;</button>
          </div>
          <div class="modal-body" style="display:flex;flex-direction:column;gap:10px">
            <div class="form-group" v-if="!editingUser">
              <label>用户名</label>
              <input v-model="userForm.username" class="form-input" placeholder="必填"/>
            </div>
            <div class="form-group" v-if="!editingUser">
              <label>密码</label>
              <input type="password" v-model="userForm.password" class="form-input" placeholder="至尐10位，含大小写字母、数字和特殊字符" autocomplete="new-password"/>
            </div>
            <div class="form-group">
              <label>角色</label>
              <select v-model="userForm.role" class="form-input">
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
                <option value="super_admin">超级管理员</option>
              </select>
            </div>
            <div class="form-group">
              <label>租户ID</label>
              <input v-model="userForm.tenant_id" class="form-input" placeholder="可选"/>
            </div>
            <div class="form-group">
              <label>部门</label>
              <input v-model="userForm.dept_id" class="form-input" placeholder="可选"/>
            </div>
          </div>
          <div class="modal-footer" style="justify-content:flex-end;gap:8px">
            <button class="btn btn-ghost btn-sm" @click="userModal=false">取消</button>
            <button class="btn btn-primary btn-sm" @click="submitUser">确定</button>
          </div>
        </div>
      </div>

      <!-- 新建 API Key 弹窗 -->
      <div v-if="keyModal" class="modal-overlay" @click.self="keyModal=false">
        <div class="modal-box" style="width:360px">
          <div class="modal-header">
            <span class="modal-title">新建 API Key</span>
            <button class="modal-close" @click="keyModal=false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Key 名称</label>
              <input v-model="keyName" class="form-input" placeholder="eg: 自动化脚本"/>
            </div>
          </div>
          <div class="modal-footer" style="justify-content:flex-end;gap:8px">
            <button class="btn btn-ghost btn-sm" @click="keyModal=false">取消</button>
            <button class="btn btn-primary btn-sm" @click="createKey">创建</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { apiListUsers, apiCreateUser, apiUpdateUser, apiChangePassword, apiCreateApiKey, apiListApiKeys, apiRevokeApiKey } from '@/api/index.js'

const isAdmin = computed(() => {
  try {
    const user = JSON.parse(sessionStorage.getItem('rag_user') || '{}')
    return ['admin', 'super_admin'].includes(user.role)
  } catch { return false }
})

const tab = ref(isAdmin.value ? 'users' : 'password')
const tabs = computed(() => {
  const all = [
    { key: 'users',    label: '用户列表' },
    { key: 'password', label: '修改密码' },
    { key: 'apikeys',  label: 'API Key' },
  ]
  return isAdmin.value ? all : all.filter(t => t.key !== 'users')
})

// ── Users ──
const users     = ref([])
const userTotal = ref(0)
const nextCursor = ref(null)
const hasMoreUsers = ref(false)
const usersLoading = ref(false)
const userModal = ref(false)
const editingUser = ref(null)
const userForm  = reactive({ username: '', password: '', role: 'user', tenant_id: '', dept_id: '' })

onMounted(() => { if (isAdmin.value) loadUsers(); loadKeys() })

async function loadUsers() {
  usersLoading.value = true
  nextCursor.value = null
  try {
    const data = await apiListUsers({ limit: 30 })
    users.value = data.users || data || []
    userTotal.value = data.total != null ? data.total : users.value.length
    nextCursor.value = data.next_cursor || null
    hasMoreUsers.value = !!data.has_more
  } catch (e) { console.error(e) }
  finally { usersLoading.value = false }
}

async function loadMoreUsers() {
  if (!nextCursor.value || !hasMoreUsers.value) return
  usersLoading.value = true
  try {
    const data = await apiListUsers({ limit: 30, cursor: nextCursor.value })
    const list = data.users || []
    users.value = [...users.value, ...list]
    nextCursor.value = data.next_cursor || null
    hasMoreUsers.value = !!data.has_more
  } catch (e) { console.error(e) }
  finally { usersLoading.value = false }
}

function openCreateUser() {
  editingUser.value = null
  Object.assign(userForm, { username: '', password: '', role: 'user', tenant_id: '', dept_id: '' })
  userModal.value = true
}

function openEditUser(u) {
  editingUser.value = u
  Object.assign(userForm, { role: u.role, tenant_id: u.tenant_id || '', dept_id: u.dept_id || '' })
  userModal.value = true
}

async function submitUser() {
  try {
    if (editingUser.value) {
      await apiUpdateUser(editingUser.value.id, {
        role: userForm.role,
        tenant_id: userForm.tenant_id || undefined,
        dept_id: userForm.dept_id || undefined,
      })
    } else {
      if (!userForm.username || !userForm.password) { $toast.warning('用户名和密码必填'); return }
      await apiCreateUser({
        username: userForm.username,
        password: userForm.password,
        role: userForm.role,
        tenant_id: userForm.tenant_id || undefined,
        dept_id: userForm.dept_id || undefined,
      })
    }
    userModal.value = false
    await loadUsers()
  } catch (e) { $toast.error('操作失败: ' + e) }
}

async function toggleActive(u) {
  const action = u.is_active ? '禁用' : '启用'
  if (!confirm(`确认${action}用户 ${u.username}？`)) return
  try {
    await apiUpdateUser(u.id, { is_active: !u.is_active })
    await loadUsers()
  } catch (e) { $toast.error('操作失败: ' + e) }
}

// ── Password ──
const pwForm   = reactive({ old_password: '', new_password: '', confirm: '' })
const pwLoading = ref(false)
const pwMsg     = ref('')
const pwOk      = ref(false)

async function changePw() {
  if (!pwForm.old_password || !pwForm.new_password) { pwMsg.value = '请填写完整'; pwOk.value = false; return }
  if (pwForm.new_password.length < 10 || !/[A-Z]/.test(pwForm.new_password) || !/[a-z]/.test(pwForm.new_password) || !/\d/.test(pwForm.new_password) || !/[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/`~]/.test(pwForm.new_password)) {
    pwMsg.value = '新密码至尐10位且需同时包含大写字母、小写字母、数字和特殊字符'; pwOk.value = false; return
  }
  if (pwForm.new_password !== pwForm.confirm) { pwMsg.value = '两次密码不一致'; pwOk.value = false; return }
  pwLoading.value = true; pwMsg.value = ''
  try {
    await apiChangePassword({ old_password: pwForm.old_password, new_password: pwForm.new_password })
    pwMsg.value = '修改成功'; pwOk.value = true
    pwForm.old_password = ''; pwForm.new_password = ''; pwForm.confirm = ''
  } catch (e) { pwMsg.value = typeof e === 'string' ? e : '修改失败'; pwOk.value = false }
  finally { pwLoading.value = false }
}

// ── API Keys ──
const apiKeys   = ref([])
const keyModal  = ref(false)
const keyName   = ref('')
const newKeyRaw = ref('')

async function loadKeys() {
  try { apiKeys.value = await apiListApiKeys() || [] } catch (e) { console.error(e) }
}

function openCreateKey() { keyName.value = ''; keyModal.value = true; newKeyRaw.value = '' }

async function createKey() {
  if (!keyName.value.trim()) { $toast.warning('请输入名称'); return }
  try {
    const data = await apiCreateApiKey(keyName.value.trim())
    newKeyRaw.value = data.raw_key || data.key || ''
    keyModal.value = false
    await loadKeys()
  } catch (e) { $toast.error('创建失败: ' + e) }
}

async function revokeKey(id) {
  if (!confirm('确认撤销此 Key？撤销后不可恢复')) return
  try { await apiRevokeApiKey(id); await loadKeys() }
  catch (e) { $toast.error('撤销失败: ' + e) }
}

function copyKey(key) {
  navigator.clipboard.writeText(key).then(() => $toast.success('已复制到剪贴板')).catch(() => $toast.info('Key: ' + key))
}

// ── Helpers ──
const roleLabel = r => ({ super_admin: '超级管理员', admin: '管理员', user: '普通用户' }[r] || r)
const roleBadge = r => ({ super_admin: 'badge-red', admin: 'badge-yellow', user: 'badge-blue' }[r] || 'badge-gray')

function fmtDate(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false })
}
</script>

<style scoped>
.tab-bar { display:flex; gap:2px; background:rgba(0,243,255,0.03); border:1px solid rgba(0,243,255,0.1); border-radius:var(--r-sm); padding:2px; width:fit-content; }
.tab-btn {
  padding:6px 16px; border:none; background:transparent; color:var(--text-2);
  font-size:13px; cursor:pointer; border-radius:var(--r-sm); transition:all .2s;
  font-family:"Rajdhani",sans-serif; font-weight:500; letter-spacing:0.5px;
}
.tab-btn.active {
  background:rgba(0,243,255,0.1); color:#00f3ff; font-weight:600;
  box-shadow:0 0 10px rgba(0,243,255,0.1);
  text-shadow:0 0 6px rgba(0,243,255,0.3);
}
.tab-btn:hover:not(.active) { color:var(--text-1); background:rgba(0,243,255,0.03); }

.section-hd {
  font-family:"Orbitron",sans-serif;
  font-size:11px; font-weight:600; color:#00f3ff; margin-bottom:10px; letter-spacing:0.5px;
}
.count-badge { display:inline-block; padding:0 6px; border-radius:99px; background:rgba(0,243,255,0.08); color:#00f3ff; font-size:11px; margin-left:6px; font-family:"JetBrains Mono",monospace; }
.list-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
.time-cell { font-size:11px; color:var(--text-3); white-space:nowrap; font-family:"JetBrains Mono",monospace; }
.action-btns { display:flex; gap:4px; }
.empty-row { padding:20px; text-align:center; font-size:13px; color:var(--text-3); }

.form-group { display:flex; flex-direction:column; gap:4px; }
.form-group label { font-family:"Orbitron",sans-serif; font-size:10px; color:#00f3ff; font-weight:600; letter-spacing:0.5px; text-transform:uppercase; }
.form-input {
  padding:7px 10px; border:1px solid rgba(0,243,255,0.15); border-radius:var(--r-sm);
  background:rgba(10,14,39,0.6); color:var(--text-1); font-size:13px; outline:none;
  transition:all .2s;
}
.form-input:focus { border-color:#00f3ff; box-shadow:0 0 10px rgba(0,243,255,0.1); }

.form-msg { margin-top:8px; font-size:12px; padding:6px 10px; border-radius:var(--r-sm); }
.msg-ok  { background:rgba(5,255,161,0.1); color:#05ffa1; border:1px solid rgba(5,255,161,0.2); }
.msg-err { background:rgba(255,0,110,0.08); color:#ff006e; border:1px solid rgba(255,0,110,0.2); }

.new-key-banner {
  margin-top:10px; padding:10px 14px;
  background:rgba(5,255,161,0.08); border:1px solid rgba(5,255,161,0.2);
  border-radius:var(--r-sm); display:flex; align-items:center; gap:8px; font-size:12px; color:#05ffa1;
}
.key-code {
  font-family:"JetBrains Mono",monospace;
  font-size:11px; color:#00f3ff; background:rgba(10,14,39,0.6);
  padding:3px 8px; border-radius:4px; word-break:break-all; flex:1;
  border:1px solid rgba(0,243,255,0.1);
}

/* ── Modal (reuse global pattern) ── */
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:1000; display:flex; align-items:center; justify-content:center; backdrop-filter:blur(5px); }
.modal-box { background:rgba(21,25,50,0.95); border:1px solid rgba(0,243,255,0.2); border-radius:14px; max-width:90vw; max-height:80vh; display:flex; flex-direction:column; box-shadow:0 0 40px rgba(0,243,255,0.05); backdrop-filter:blur(20px); }
.modal-header { display:flex; align-items:center; gap:10px; padding:14px 18px; border-bottom:1px solid rgba(0,243,255,0.1); }
.modal-title { font-family:"Orbitron",sans-serif; font-size:12px; font-weight:600; color:#00f3ff; letter-spacing:1px; }
.modal-close { margin-left:auto; background:none; border:none; cursor:pointer; font-size:20px; color:var(--text-3); padding:0 4px; line-height:1; transition:color .2s; }
.modal-close:hover { color:#ff006e; }
.modal-body { flex:1; overflow-y:auto; padding:14px 18px; }
.modal-footer { display:flex; align-items:center; padding:10px 18px; border-top:1px solid rgba(0,243,255,0.1); }
</style>
