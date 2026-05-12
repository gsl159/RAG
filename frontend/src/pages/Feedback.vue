<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title">用户反馈</div>
      <div class="page-sub">满意度统计 · 差评分析 · 持续优化</div>
    </div>
    <div class="page-body">
      <div v-if="!stats" class="loading-row"><span class="dots"><span/><span/><span/></span></div>
      <template v-else>
        <!-- 统计卡 -->
        <div class="stats-row">
          <div class="stat-mini card" v-for="s in statCards" :key="s.label">
            <div class="sm-icon">{{ s.icon }}</div>
            <div>
              <div class="sm-val" :style="{color:s.color}">{{ s.val }}</div>
              <div class="sm-lbl">{{ s.label }}</div>
            </div>
            <div v-if="s.sub" class="sm-sub">{{ s.sub }}</div>
          </div>
        </div>

        <!-- 图表 -->
        <div class="chart-row">
          <div class="card chart-card">
            <div class="chart-hd">好评 vs 差评</div>
            <div v-if="!stats.total" class="chart-empty">暂无反馈数据</div>
            <div v-else ref="pieChart" class="echart"/>
          </div>
          <div class="card chart-card">
            <div class="chart-hd">用户满意度</div>
            <div ref="gaugeChart" class="echart"/>
          </div>
        </div>

        <!-- 差评原因分布 -->
        <div class="card" style="margin-top:14px" v-if="stats.reason_dist?.length">
          <div class="section-hd">差评原因分布</div>
          <div class="reason-bars">
            <div v-for="r in stats.reason_dist" :key="r.reason" class="reason-bar-row">
              <span class="reason-name">{{ r.reason }}</span>
              <div class="reason-bar"><div class="reason-fill" :style="{width: reasonPct(r.count)+'%'}"/></div>
              <span class="reason-cnt">{{ r.count }}</span>
            </div>
          </div>
        </div>

        <!-- 差评Top -->
        <div class="card" style="margin-top:14px" v-if="stats.top_bad_queries?.length">
          <div class="section-hd" style="color:var(--red)">差评 Top 问题</div>
          <table class="data-table">
            <thead><tr><th>#</th><th>问题</th><th>原因</th><th>备注</th></tr></thead>
            <tbody>
              <tr v-for="(item,i) in stats.top_bad_queries" :key="i">
                <td style="width:36px;color:var(--text-3)">{{ i+1 }}</td>
                <td>{{ item.query }}</td>
                <td><span v-if="item.reason" class="badge badge-red" style="font-size:10px">{{ item.reason }}</span><span v-else style="color:var(--text-3)">-</span></td>
                <td style="color:var(--text-3)">{{ item.comment || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 最近反馈 -->
        <div class="card" style="margin-top:14px">
          <div class="section-hd">最近反馈</div>
          <div v-if="!stats.recent?.length" class="empty-row">暂无反馈数据</div>
          <table v-else class="data-table">
            <thead><tr><th>问题</th><th>评价</th><th>原因</th><th>评分</th><th>备注</th><th>时间</th></tr></thead>
            <tbody>
              <tr v-for="(item,i) in stats.recent" :key="i" class="fb-row" @click="openDetail(item)">
                <td class="q-cell">{{ item.query }}</td>
                <td><span class="badge" :class="item.feedback==='like'?'badge-green':'badge-red'">{{ item.feedback==='like'?'👍':'👎' }}</span></td>
                <td><span v-if="item.reason" class="reason-pill">{{ item.reason }}</span><span v-else style="color:var(--text-3)">-</span></td>
                <td>
                  <div v-if="item.ratings" class="rating-mini">
                    <span v-if="item.ratings.relevance" title="相关性">R:{{ item.ratings.relevance }}</span>
                    <span v-if="item.ratings.accuracy" title="准确性">A:{{ item.ratings.accuracy }}</span>
                    <span v-if="item.ratings.completeness" title="完整性">C:{{ item.ratings.completeness }}</span>
                  </div>
                  <span v-else style="color:var(--text-3)">-</span>
                </td>
                <td class="comment-cell">{{ item.comment||'-' }}</td>
                <td class="time-cell">{{ fmtDate(item.time) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 反馈详情弹窗 -->
        <div v-if="detailItem" class="modal-overlay" @click.self="detailItem=null">
          <div class="fb-detail-modal">
            <div class="detail-hd">
              <span>反馈详情</span>
              <button class="modal-close" @click="detailItem=null">&times;</button>
            </div>
            <div class="detail-body">
              <div class="detail-field">
                <span class="detail-label">问题</span>
                <div class="detail-content">{{ detailItem.query }}</div>
              </div>
              <div class="detail-field">
                <span class="detail-label">评价</span>
                <span class="badge" :class="detailItem.feedback==='like'?'badge-green':'badge-red'">
                  {{ detailItem.feedback==='like'?'👍 好评':'👎 差评' }}
                </span>
              </div>
              <div v-if="detailItem.reason" class="detail-field">
                <span class="detail-label">原因</span>
                <span class="reason-pill">{{ detailItem.reason }}</span>
              </div>
              <div v-if="detailItem.ratings" class="detail-field">
                <span class="detail-label">评分</span>
                <div class="detail-ratings">
                  <div v-for="(v,k) in detailItem.ratings" :key="k" class="dr-item">
                    <span class="dr-name">{{ {relevance:'相关性',accuracy:'准确性',completeness:'完整性'}[k]||k }}</span>
                    <div class="dr-stars">
                      <span v-for="n in 5" :key="n" class="star" :class="{on:v>=n}">★</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="detailItem.comment" class="detail-field">
                <span class="detail-label">备注</span>
                <div class="detail-content">{{ detailItem.comment }}</div>
              </div>
              <div class="detail-field">
                <span class="detail-label">时间</span>
                <span class="detail-time">{{ fmtDateFull(detailItem.time) }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { apiFeedbackStats } from '@/api/index.js'

const stats = ref(null)
const pieChart = ref(null); const gaugeChart = ref(null)
const detailItem = ref(null)

const statCards = computed(() => {
  if (!stats.value) return []
  const s = stats.value
  const sat = s.satisfaction != null ? s.satisfaction.toFixed(1) + '%' : '0%'
  const fmtN = v => (v != null && v > 0) ? v : '0'
  return [
    { icon:'👍', label:'好评', val:fmtN(s.like), color:'var(--green)', sub:s.total ? ((s.like/s.total*100).toFixed(0)+'%') : '' },
    { icon:'👎', label:'差评', val:fmtN(s.dislike), color:'var(--red)', sub:s.total ? ((s.dislike/s.total*100).toFixed(0)+'%') : '' },
    { icon:'📊', label:'总反馈', val:fmtN(s.total), color:'var(--accent)' },
    { icon:'⭐', label:'满意度', val:sat, color:'var(--yellow)' },
  ]
})

function openDetail(item) { detailItem.value = item }
function fmtDateFull(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false })
}

const T = { bg:'transparent', text:'#8b91c8', green:'#05ffa1', red:'#ff006e', yellow:'#ffbe0b' }
let _pieInstance = null, _gaugeInstance = null

function drawPie(s) {
  if (_pieInstance) _pieInstance.dispose()
  const c = echarts.init(pieChart.value)
  _pieInstance = c
  c.setOption({
    backgroundColor:T.bg,
    tooltip:{ trigger:'item', formatter:'{b}: {c} ({d}%)' },
    legend:{ orient:'vertical', left:'left', textStyle:{ color:T.text, fontSize:11 } },
    series:[{ type:'pie', radius:['38%','68%'],
      data:[
        { value:s.like, name:'好评', itemStyle:{ color:T.green } },
        { value:s.dislike, name:'差评', itemStyle:{ color:T.red } },
      ],
      label:{ color:T.text, fontSize:11 },
    }]
  })
}
function drawGauge(s) {
  const val = parseFloat((s.satisfaction||0).toFixed(1))
  if (_gaugeInstance) _gaugeInstance.dispose()
  const c = echarts.init(gaugeChart.value)
  _gaugeInstance = c
  c.setOption({
    backgroundColor:T.bg,
    series:[{
      type:'gauge', startAngle:200, endAngle:-20, min:0, max:100,
      progress:{ show:true, width:18, itemStyle:{ color:val>=70?T.green:val>=50?T.yellow:T.red } },
      axisLine:{ lineStyle:{ width:18, color:[[1,'rgba(255,255,255,0.07)']] } },
      axisTick:{ show:false }, splitLine:{ show:false },
      axisLabel:{ color:T.text, distance:24, fontSize:10 },
      pointer:{ show:false },
      detail:{ valueAnimation:true, formatter:'{value}%', color:'#e0e6ff', fontSize:28, offsetCenter:[0,'20%'] },
      title:{ offsetCenter:[0,'52%'], color:T.text, fontSize:12 },
      data:[{ value:val, name:'满意度' }]
    }]
  })
}

function fmtDate(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false })
}

function reasonPct(count) {
  const max = Math.max(...(stats.value.reason_dist || []).map(r => r.count), 1)
  return Math.round(count / max * 100)
}

let _pollTimer = null

async function loadStats() {
  try {
    stats.value = await apiFeedbackStats()
    await nextTick()
    if (pieChart.value && stats.value.total) drawPie(stats.value)
    if (gaugeChart.value) drawGauge(stats.value)
  } catch (e) {
    console.warn('加载反馈统计失败:', e)
    if (!stats.value) {
      stats.value = { like:0, dislike:0, total:0, satisfaction:0, recent:[], top_bad_queries:[], reason_dist:[] }
    }
  }
}

onMounted(() => {
  loadStats()
  // 每15秒自动轮询刷新反馈数据
  _pollTimer = setInterval(loadStats, 15000)
})

onUnmounted(() => {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
  if (_pieInstance) _pieInstance.dispose()
  if (_gaugeInstance) _gaugeInstance.dispose()
})
</script>

<style scoped>
.loading-row { padding:60px; text-align:center; }
.stats-row   { display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin-bottom:14px; }
.stat-mini   {
  display:flex; align-items:center; gap:12px; padding:18px 20px; position:relative;
  backdrop-filter:blur(20px);
}
.sm-icon     { font-size:28px; flex-shrink:0; }
.sm-val      {
  font-family:"JetBrains Mono","Orbitron",sans-serif;
  font-size:26px; font-weight:700; line-height:1.1;
}
.sm-lbl      { font-size:12px; color:var(--text-3); margin-top:2px; }
.sm-sub      { position:absolute; top:10px; right:14px; font-size:10px; color:var(--text-3); background:rgba(0,243,255,0.05); border-radius:8px; padding:1px 7px; font-family:"JetBrains Mono",monospace; }
.chart-row   { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.chart-card  { padding:14px 16px; }
.chart-hd    { font-family:"Orbitron",sans-serif; font-size:10px; font-weight:600; color:#00f3ff; margin-bottom:10px; letter-spacing:0.5px; text-transform:uppercase; }
.chart-empty { padding:40px; text-align:center; color:var(--text-3); font-size:13px; }
.echart      { width:100%; height:220px; }
.section-hd  { font-family:"Orbitron",sans-serif; font-size:11px; font-weight:600; color:#00f3ff; margin-bottom:10px; letter-spacing:0.5px; }
.empty-row   { padding:24px; text-align:center; color:var(--text-3); font-size:13px; }

.reason-bars { display:flex; flex-direction:column; gap:8px; }
.reason-bar-row { display:flex; align-items:center; gap:8px; }
.reason-name { font-size:12px; color:var(--text-2); width:80px; flex-shrink:0; }
.reason-bar { flex:1; height:10px; background:rgba(0,243,255,0.06); border-radius:5px; overflow:hidden; }
.reason-fill { height:100%; background:linear-gradient(90deg, #ff006e, #b967ff); border-radius:5px; transition:width .4s ease; box-shadow:0 0 8px rgba(255,0,110,0.2); }
.reason-cnt { font-size:11px; color:var(--text-3); width:30px; text-align:right; font-family:"JetBrains Mono",monospace; }
.reason-pill { font-size:10px; background:rgba(255,0,110,0.1); color:#ff006e; padding:2px 8px; border-radius:10px; }

/* 最近反馈表 */
.fb-row { cursor:pointer; transition:all .2s; }
.fb-row:hover { background:rgba(0,243,255,0.03); }
.q-cell { max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.comment-cell { max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-3); }
.time-cell { font-size:11px; color:var(--text-3); white-space:nowrap; font-family:"JetBrains Mono",monospace; }
.rating-mini { display:flex; gap:6px; font-size:10px; color:var(--text-3); font-family:"JetBrains Mono",monospace; }
.rating-mini span { background:rgba(0,243,255,0.05); padding:1px 4px; border-radius:3px; }

/* 详情弹窗 */
.modal-overlay { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,.6); display:flex; align-items:center; justify-content:center; z-index:999; backdrop-filter:blur(5px); }
.fb-detail-modal { background:rgba(21,25,50,0.95); border:1px solid rgba(0,243,255,0.2); border-radius:14px; width:460px; max-width:92vw; max-height:80vh; overflow:auto; box-shadow:0 0 40px rgba(0,243,255,0.05); backdrop-filter:blur(20px); }
.detail-hd { display:flex; justify-content:space-between; align-items:center; padding:16px 20px; border-bottom:1px solid rgba(0,243,255,0.1); font-family:"Orbitron",sans-serif; font-weight:600; font-size:12px; color:#00f3ff; letter-spacing:1px; }
.modal-close { background:none; border:none; font-size:22px; color:var(--text-3); cursor:pointer; line-height:1; transition:color .2s; }
.modal-close:hover { color:#ff006e; }
.detail-body { padding:16px 20px; display:flex; flex-direction:column; gap:14px; }
.detail-field {}
.detail-label { font-family:"Orbitron",sans-serif; font-size:9px; color:#00f3ff; display:block; margin-bottom:4px; text-transform:uppercase; letter-spacing:1px; }
.detail-content { font-size:13px; color:var(--text-1); line-height:1.6; white-space:pre-wrap; word-break:break-all; background:rgba(10,14,39,0.6); padding:10px 12px; border-radius:8px; border:1px solid rgba(0,243,255,0.08); }
.detail-time { font-size:13px; color:var(--text-2); font-family:"JetBrains Mono",monospace; }
.detail-ratings { display:flex; flex-direction:column; gap:6px; }
.dr-item { display:flex; align-items:center; gap:10px; }
.dr-name { font-size:12px; color:var(--text-2); width:56px; }
.dr-stars { display:flex; gap:2px; }
.star { font-size:16px; color:rgba(0,243,255,0.1); transition:all .15s; }
.star.on { color:#ffbe0b; text-shadow:0 0 6px rgba(255,190,11,0.4); }

@media (max-width: 640px) {
  .stats-row { flex-direction:column; }
  .chart-row { grid-template-columns:1fr; }
}
</style>
