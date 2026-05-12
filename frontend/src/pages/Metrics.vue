<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title">监控大盘</div>
      <div class="page-sub">实时指标 · RAG质量 · 缓存命中 · QPS</div>
    </div>
    <div class="page-body">
      <div v-if="loadError" class="card" style="padding:30px;text-align:center;color:var(--red);font-size:13px">
        加载指标失败，请检查服务状态
        <button class="btn btn-ghost btn-sm" style="margin-left:10px" @click="reload">重试</button>
      </div>

      <!-- 概览卡片 -->
      <div class="stat-grid">
        <div class="stat-card" v-for="s in statCards" :key="s.label">
          <div class="stat-icon">{{ s.icon }}</div>
          <div class="stat-val" :style="{color: s.color || 'var(--text-1)'}">{{ s.val }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </div>

      <!-- 图表行1 -->
      <div class="chart-row">
        <div class="card chart-card">
          <div class="chart-hd">每日查询量 & 平均延迟</div>
          <div ref="queryChart" class="echart"/>
          <div v-if="!ragData.daily?.length" class="chart-empty">暂无查询数据</div>
        </div>
        <div class="card chart-card">
          <div class="chart-hd">RAG 评分趋势（近7天）</div>
          <div ref="scoreChart" class="echart"/>
          <div v-if="!ragData.daily?.some(d => d.avg_score != null)" class="chart-empty">暂无评分数据</div>
        </div>
      </div>

      <!-- 图表行2 -->
      <div class="chart-row">
        <div class="card chart-card">
          <div class="chart-hd">五层缓存命中率</div>
          <div ref="cacheChart" class="echart"/>
        </div>
        <div class="card chart-card">
          <div class="chart-hd">文档质量分布</div>
          <div ref="docChart" class="echart"/>
          <div v-if="!docData.score_dist?.length" class="chart-empty">暂无质量评分</div>
        </div>
      </div>

      <!-- 图表行3 -->
      <div class="chart-row">
        <div class="card chart-card">
          <div class="chart-hd">近1小时 QPS</div>
          <div ref="qpsChart" class="echart"/>
          <div v-if="!qpsData.length" class="chart-empty">近1小时无查询请求</div>
        </div>
        <div class="card chart-card">
          <div class="chart-hd">文档状态分布</div>
          <div ref="docPieChart" class="echart"/>
          <div v-if="!Object.keys(docData.status_counts||{}).length" class="chart-empty">暂无文档数据</div>
        </div>
      </div>

      <!-- LLM 提供商状态 -->
      <div v-if="llmStatus" class="card" style="margin-top:16px;padding:14px 16px">
        <div class="list-header" style="margin-bottom:10px">
          <span class="chart-hd" style="margin:0">LLM 提供商链</span>
          <span style="font-size:11px;color:var(--text-3)">
            当前激活：<strong :style="{color:'var(--green)'}">{{ llmStatus.active_provider }}</strong>
            &nbsp;·&nbsp;{{ llmStatus.failover_enabled ? '故障转移 ✓' : '单一提供商' }}
          </span>
        </div>
        <div class="llm-chain">
          <div v-for="p in llmStatus.providers" :key="p.name" class="llm-card" :class="{active: p.name===llmStatus.active_provider}">
            <div class="llm-dot" :class="{on: p.configured}"></div>
            <div>
              <div class="llm-name">{{ p.name }}</div>
              <div class="llm-ep">{{ p.endpoint }}</div>
            </div>
            <div class="llm-badge">
              <span v-if="p.configured" style="color:var(--green)">已配置</span>
              <span v-else style="color:var(--text-3)">未配置</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Benchmark 评估集管理 -->
      <div class="card" style="margin-top:16px">
        <div class="list-header">
          <div>
            <span class="section-hd" style="margin:0">Ground Truth 评估集</span>
            <span style="font-size:11px;color:var(--text-3);margin-left:8px">人工标注的标准问答对，用于衡量 RAG 质量</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn btn-ghost btn-sm" @click="showBmAdd=!showBmAdd">
              {{ showBmAdd ? '收起' : '+ 新增标准问答' }}
            </button>
            <button class="btn btn-primary btn-sm" @click="runBenchmark" :disabled="bmRunning || !benchmarks.length">
              {{ bmRunning ? '评估中…' : '▶ 批量评估' }}
            </button>
          </div>
        </div>

        <!-- 新增表单 -->
        <div v-if="showBmAdd" class="bm-add-form">
          <input v-model="bmQuestion" class="input-base bm-input" placeholder="标准问题（question）"/>
          <textarea v-model="bmExpected" class="input-base bm-textarea" rows="2" placeholder="期望答案（expected_answer）"/>
          <div style="display:flex;gap:8px;align-items:center">
            <input v-model="bmCategory" class="input-base" style="width:140px;flex-shrink:0" placeholder="分类（如 general）"/>
            <select v-model="bmDifficulty" class="input-base" style="width:100px;flex-shrink:0">
              <option value="easy">easy</option>
              <option value="medium">medium</option>
              <option value="hard">hard</option>
            </select>
            <button class="btn btn-accent btn-sm" @click="addBenchmark" :disabled="!bmQuestion.trim() || !bmExpected.trim()">保存</button>
            <button class="btn btn-ghost btn-sm" @click="showBmAdd=false">取消</button>
          </div>
        </div>

        <!-- 评估结果摘要 -->
        <div v-if="bmResult" class="bm-result">
          <span class="bm-result-item">
            <span class="bm-key">总数</span>
            <span class="bm-val" style="color:var(--accent)">{{ bmResult.total }}</span>
          </span>
          <span class="bm-result-item" v-for="(v,k) in bmResult.avg_scores" :key="k">
            <span class="bm-key">{{ k }}</span>
            <span class="bm-val" :style="{color: scoreColor(v/5)}">{{ v.toFixed(2) }}</span>
          </span>
        </div>

        <!-- 评估集列表 -->
        <div v-if="bmLoading" class="empty-row"><span class="dots"><span/><span/><span/></span></div>
        <div v-else-if="!benchmarks.length" class="empty-row" style="color:var(--text-3);margin-top:10px">
          暂无评估集，点击「新增标准问答」录入 Ground Truth
        </div>
        <table v-else class="data-table" style="margin-top:12px">
          <thead><tr><th>问题</th><th>期望答案</th><th>分类</th><th>难度</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="bm in benchmarks" :key="bm.id">
              <td class="bm-q">{{ bm.question }}</td>
              <td class="bm-a">{{ bm.expected_answer }}</td>
              <td><span class="badge badge-blue">{{ bm.category }}</span></td>
              <td><span class="badge" :class="{'badge-green':bm.difficulty==='easy','badge-yellow':bm.difficulty==='medium','badge-red':bm.difficulty==='hard'}">{{ bm.difficulty }}</span></td>
              <td><button class="btn btn-danger btn-sm" @click="deleteBenchmark(bm.id)">删除</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { apiOverview, apiRagMetrics, apiCacheMetrics, apiDocMetrics, apiQPS,
         apiListBenchmarks, apiAddBenchmark, apiRunBenchmark, apiDeleteBenchmark,
         apiLlmStatus } from '@/api/index.js'

const overview  = ref({})
const ragData   = ref({})
const cacheData = ref({})
const docData   = ref({})
const qpsData   = ref([])
const loadError = ref(false)

// ── Benchmark state ────────────────────────────────────────────────────────
const benchmarks  = ref([])
const bmLoading   = ref(false)
const bmRunning   = ref(false)
const bmResult    = ref(null)
const showBmAdd   = ref(false)
const bmQuestion  = ref('')
const bmExpected  = ref('')
const bmCategory  = ref('general')
const bmDifficulty = ref('medium')

async function loadBenchmarks() {
  bmLoading.value = true
  try { benchmarks.value = await apiListBenchmarks() || [] } catch (e) { console.error("Metrics load failed:", e) }
  finally { bmLoading.value = false }
}
async function addBenchmark() {
  if (!bmQuestion.value.trim() || !bmExpected.value.trim()) return
  await apiAddBenchmark({
    question: bmQuestion.value.trim(),
    expected_answer: bmExpected.value.trim(),
    category: bmCategory.value || 'general',
    difficulty: bmDifficulty.value,
  })
  bmQuestion.value = ''; bmExpected.value = ''
  showBmAdd.value = false
  await loadBenchmarks()
}
async function deleteBenchmark(id) {
  await apiDeleteBenchmark(id)
  await loadBenchmarks()
}
async function runBenchmark() {
  bmRunning.value = true; bmResult.value = null
  try { bmResult.value = await apiRunBenchmark(bmCategory.value) } catch (e) { console.error("Metrics load failed:", e) }
  finally { bmRunning.value = false }
}

// ── LLM 提供商状态 ──────────────────────────────────────────────────────────────
const llmStatus = ref(null)
async function loadLlmStatus() {
  try { llmStatus.value = await apiLlmStatus() } catch (e) { console.error("Metrics load failed:", e) }
}

const statCards = computed(() => [
  { icon:'📄', label:'文档总数',   val: overview.value.doc_count    ?? '-' },
  { icon:'💬', label:'累计查询',   val: overview.value.query_count  ?? '-' },
  { icon:'⭐', label:'平均评分',   val: fmt2(overview.value.avg_score), color: scoreColor(overview.value.avg_score) },
  { icon:'⏱', label:'平均延迟',   val: overview.value.avg_latency_ms ? overview.value.avg_latency_ms+'ms' : '-' },
  { icon:'⚡', label:'缓存命中率', val: pct(overview.value.cache_hit_rate), color:'var(--yellow)' },
  { icon:'🔢', label:'向量总数',   val: overview.value.vector_count ?? '-' },
])

const fmt2 = v => v != null ? Number(v).toFixed(2) : '-'
const pct  = v => v != null ? (v*100).toFixed(1)+'%' : '-'
function scoreColor(v) {
  if (!v) return 'var(--text-1)'
  if (v >= 4) return 'var(--green)'
  if (v >= 3) return 'var(--yellow)'
  return 'var(--red)'
}

const T = {
  bg:'transparent', text:'#8b91c8', grid:'rgba(0,243,255,0.07)',
  accent:'#00f3ff', green:'#05ffa1', yellow:'#ffbe0b', red:'#ff006e', blue:'#b967ff',
}
const axisBase = {
  axisLine:  { lineStyle:{ color:T.grid } },
  axisTick:  { show:false },
  axisLabel: { color:T.text, fontSize:11 },
  splitLine: { lineStyle:{ color:T.grid, type:'dashed' } },
}

const queryChart = ref(null); const scoreChart  = ref(null)
const cacheChart = ref(null); const docChart    = ref(null)
const qpsChart   = ref(null); const docPieChart = ref(null)

const charts = []
function disposeCharts() {
  charts.forEach(c => c.dispose())
  charts.length = 0
}
function initC(el) {
  const c = echarts.init(el, null, { renderer:'canvas' })
  charts.push(c)
  return c
}
function resizeAll() { charts.forEach(c => c.resize()) }
onUnmounted(() => { disposeCharts(); window.removeEventListener('resize', resizeAll) })
const tt = { trigger:'axis', backgroundColor:'rgba(21,25,50,0.95)', borderColor:'rgba(0,243,255,0.2)', textStyle:{ color:'#e0e6ff', fontSize:12 } }

function drawQueryChart() {
  const d = ragData.value.daily || []
  if (!d.length || !queryChart.value) return
  const c = initC(queryChart.value)
  c.setOption({
    backgroundColor:T.bg, tooltip:tt,
    legend:{ data:['查询量','延迟ms'], textStyle:{ color:T.text, fontSize:11 } },
    grid:{ left:46, right:46, top:36, bottom:28 },
    xAxis:{ type:'category', data:d.map(x=>x.day), ...axisBase },
    yAxis:[
      { type:'value', name:'查询量', nameTextStyle:{ color:T.text, fontSize:10 }, ...axisBase },
      { type:'value', name:'延迟ms', nameTextStyle:{ color:T.text, fontSize:10 }, splitLine:{show:false}, axisLabel:{color:T.text,fontSize:11} },
    ],
    series:[
      { name:'查询量', type:'bar', data:d.map(x=>x.queries), itemStyle:{ color:T.accent, borderRadius:[3,3,0,0] }, yAxisIndex:0 },
      { name:'延迟ms', type:'line', data:d.map(x=>x.avg_latency), itemStyle:{ color:T.yellow }, lineStyle:{ color:T.yellow }, yAxisIndex:1, smooth:true },
    ]
  })
}
function drawScoreChart() {
  const d = ragData.value.daily || []
  if (!d.length || !scoreChart.value) return
  const scores = d.map(x => x.avg_score != null ? x.avg_score : null)
  const c = initC(scoreChart.value)
  c.setOption({
    backgroundColor:T.bg, tooltip:tt,
    grid:{ left:40, right:16, top:16, bottom:28 },
    xAxis:{ type:'category', data:d.map(x=>x.day), ...axisBase },
    yAxis:{ type:'value', min:0, max:5, ...axisBase },
    series:[{ type:'line', data:scores, smooth:true, itemStyle:{ color:T.green }, lineStyle:{ color:T.green },
      areaStyle:{ color:{ type:'linear',x:0,y:0,x2:0,y2:1, colorStops:[{offset:0,color:'rgba(5,255,161,.25)'},{offset:1,color:'rgba(5,255,161,0)'}] } },
      markLine:{ data:[{type:'average'}], lineStyle:{ color:T.yellow }, label:{ color:T.yellow } }
    }]
  })
}
function drawCacheChart() {
  if (!cacheChart.value) return
  const cd = cacheData.value
  const layers = [
    { name:'Query',     rate:(cd.layer_query?.hit_rate||0)*100 },
    { name:'Embed',     rate:(cd.layer_embed?.hit_rate||0)*100 },
    { name:'RAG',       rate:(cd.layer_rag?.hit_rate||0)*100 },
    { name:'Retrieval', rate:(cd.layer_retrieval?.hit_rate||0)*100 },
    { name:'Answer',    rate:(cd.layer_answer?.hit_rate||0)*100 },
  ]
  const c = initC(cacheChart.value)
  c.setOption({
    backgroundColor:T.bg, tooltip:{ formatter:'{b}: {c}%' },
    radar:{
      indicator:layers.map(l=>({ name:l.name, max:100 })),
      axisLine:{ lineStyle:{ color:T.grid } },
      splitLine:{ lineStyle:{ color:T.grid } },
      name:{ textStyle:{ color:T.text } },
    },
    series:[{ type:'radar', data:[{
      value:layers.map(l=>l.rate.toFixed(1)), name:'命中率%',
      areaStyle:{ opacity:.2, color:T.accent },
      itemStyle:{ color:T.accent }, lineStyle:{ color:T.accent },
    }] }]
  })
}
function drawDocChart() {
  const dist = docData.value.score_dist || []
  if (!dist.length || !docChart.value) return
  const c = initC(docChart.value)
  c.setOption({
    backgroundColor:T.bg, tooltip:{},
    grid:{ left:40, right:16, top:16, bottom:28 },
    xAxis:{ type:'category', data:dist.map(d=>d.score), ...axisBase },
    yAxis:{ type:'value', ...axisBase },
    series:[{ type:'bar', data:dist.map(d=>({ value:d.count, itemStyle:{ color: parseFloat(d.score)>=0.8?T.green:parseFloat(d.score)>=0.6?T.yellow:T.red, borderRadius:[3,3,0,0] } })) }]
  })
}
function drawQPS() {
  const d = qpsData.value
  if (!d.length || !qpsChart.value) return
  const c = initC(qpsChart.value)
  c.setOption({
    backgroundColor:T.bg, tooltip:tt,
    grid:{ left:40, right:16, top:16, bottom:28 },
    xAxis:{ type:'category', data:d.map(x=>x.minute?.slice(11,16)||''), ...axisBase },
    yAxis:{ type:'value', ...axisBase },
    series:[{ type:'line', data:d.map(x=>x.count), smooth:true, itemStyle:{ color:T.blue }, lineStyle:{ color:T.blue },
      areaStyle:{ color:{ type:'linear',x:0,y:0,x2:0,y2:1, colorStops:[{offset:0,color:'rgba(185,103,255,.25)'},{offset:1,color:'rgba(185,103,255,0)'}] } }
    }]
  })
}
function drawDocPie() {
  const sc = docData.value.status_counts || {}
  if (!Object.keys(sc).length || !docPieChart.value) return
  const colorMap = { done:T.green, processing:T.blue, pending:T.yellow, failed:T.red }
  const c = initC(docPieChart.value)
  c.setOption({
    backgroundColor:T.bg, tooltip:{ trigger:'item', formatter:'{b}: {c} ({d}%)' },
    legend:{ orient:'vertical', left:'left', textStyle:{ color:T.text, fontSize:11 } },
    series:[{ type:'pie', radius:['38%','68%'],
      data:Object.entries(sc).map(([k,v])=>({ name:{done:'完成',processing:'处理中',pending:'等待',failed:'失败'}[k]||k, value:v, itemStyle:{ color:colorMap[k]||T.accent } })),
      label:{ color:T.text, fontSize:11 }, emphasis:{ itemStyle:{ shadowBlur:8, shadowColor:'rgba(0,0,0,.4)' } }
    }]
  })
}

async function reload() {
  loadError.value = false
  try {
    const [ov,rd,cd,dd,qd] = await Promise.allSettled([
      apiOverview(), apiRagMetrics(7), apiCacheMetrics(), apiDocMetrics(), apiQPS()
    ])
    let anyOk = false
    if (ov.status==='fulfilled') { overview.value  = ov.value||{}; anyOk = true }
    if (rd.status==='fulfilled') { ragData.value   = rd.value||{}; anyOk = true }
    if (cd.status==='fulfilled') { cacheData.value = cd.value||{}; anyOk = true }
    if (dd.status==='fulfilled') { docData.value   = dd.value||{}; anyOk = true }
    if (qd.status==='fulfilled') { qpsData.value   = qd.value||[]; anyOk = true }
    if (!anyOk) loadError.value = true
    // 绘图需在 DOM 就绪后执行
    disposeCharts()
    window.removeEventListener('resize', resizeAll)
    setTimeout(() => {
      drawQueryChart(); drawScoreChart(); drawCacheChart()
      drawDocChart();   drawQPS();        drawDocPie()
      window.addEventListener('resize', resizeAll)
    }, 100)
  } catch { loadError.value = true }
}

onMounted(() => { reload(); loadBenchmarks(); loadLlmStatus() })
</script>

<style scoped>
.stat-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:16px; }
.stat-card {
  background:var(--glass);
  backdrop-filter:blur(20px);
  border:1px solid rgba(0,243,255,0.1);
  border-radius:var(--r-lg); padding:16px 12px; text-align:center;
  transition:all .3s;
  position:relative;
  overflow:hidden;
}
.stat-card::before {
  content:'';
  position:absolute;
  top:0; left:0; right:0;
  height:2px;
  background:linear-gradient(90deg, #00f3ff, #b967ff);
  opacity:0;
  transition:opacity .3s;
}
.stat-card:hover { border-color:rgba(0,243,255,0.25); box-shadow:0 0 20px rgba(0,243,255,0.05); }
.stat-card:hover::before { opacity:1; }
.stat-icon  { font-size:22px; margin-bottom:6px; }
.stat-val   {
  font-family:"Orbitron",sans-serif;
  font-size:22px; font-weight:700; line-height:1.2;
  background:linear-gradient(135deg,#00f3ff,#b967ff);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  background-clip:text;
}
.stat-label {
  font-size:11px; color:var(--text-3); margin-top:4px;
  font-family:"Orbitron",sans-serif; letter-spacing:0.3px;
}

.chart-row  { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.chart-card { padding:14px 16px; position:relative; }
.chart-hd   {
  font-family:"Orbitron",sans-serif;
  font-size:10px; font-weight:600; color:#00f3ff;
  margin-bottom:10px; letter-spacing:0.5px; text-transform:uppercase;
}
.echart     { width:100%; height:200px; }
.chart-empty {
  position:absolute;
  top:50%; left:50%; transform:translate(-50%,-50%);
  font-size:12px; color:var(--text-3);
  pointer-events:none;
}

@media (max-width:900px) {
  .chart-row  { grid-template-columns:1fr; }
}

/* ── Benchmark section ─────────────────────────────────────────────────── */
.list-header {
  display:flex; justify-content:space-between; align-items:flex-start;
  margin-bottom:12px; flex-wrap:wrap; gap:8px;
}
.bm-add-form {
  display:flex; flex-direction:column; gap:8px;
  background:var(--glass); border:1px solid rgba(0,243,255,0.12);
  border-radius:var(--r); padding:12px; margin-bottom:12px;
}
.bm-input   { width:100%; }
.bm-textarea { width:100%; resize:vertical; font-family:inherit; }
.bm-result {
  display:flex; flex-wrap:wrap; gap:8px;
  background:rgba(5,255,161,0.06);
  border:1px solid rgba(5,255,161,0.18);
  border-radius:var(--r); padding:10px 14px; margin-bottom:12px;
}
.bm-result-item { display:flex; flex-direction:column; align-items:center; min-width:80px; }
.bm-key { font-size:10px; color:var(--text-3); text-transform:uppercase; letter-spacing:0.4px; }
.bm-val { font-size:18px; font-weight:700; font-family:"Orbitron",sans-serif; }
.bm-table { width:100%; border-collapse:collapse; font-size:13px; }
.bm-table th { color:var(--text-3); font-weight:500; padding:6px 8px;
  border-bottom:1px solid rgba(0,243,255,0.08); text-align:left; }
.bm-table td { padding:7px 8px; border-bottom:1px solid rgba(0,243,255,0.05);
  vertical-align:top; color:var(--text-1); }
.bm-cell-q  { max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bm-cell-a  { max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  color:var(--text-2); }
.bm-empty   { text-align:center; color:var(--text-3); font-size:13px; padding:24px 0; }
.bm-del-btn { background:none; border:none; cursor:pointer; color:var(--red);
  padding:2px 6px; border-radius:4px; transition:background .2s; }
.bm-del-btn:hover { background:rgba(255,0,110,0.12); }

/* ── LLM provider chain ─────────────────────────────────────────────────────── */
.llm-chain { display:flex; gap:8px; flex-wrap:wrap; }
.llm-card {
  display:flex; align-items:center; gap:10px;
  background:rgba(0,243,255,0.04); border:1px solid rgba(0,243,255,0.1);
  border-radius:var(--r); padding:8px 14px; flex:1; min-width:180px;
  transition:border-color .2s;
}
.llm-card.active { border-color:rgba(5,255,161,0.4); background:rgba(5,255,161,0.06); }
.llm-dot {
  width:8px; height:8px; border-radius:50%; flex-shrink:0;
  background:var(--text-3);
}
.llm-dot.on { background:var(--green); box-shadow:0 0 6px var(--green); }
.llm-name { font-size:13px; font-weight:600; color:var(--text-1); }
.llm-ep   { font-size:10px; color:var(--text-3); word-break:break-all; }
.llm-badge { margin-left:auto; font-size:11px; white-space:nowrap; }
</style>
