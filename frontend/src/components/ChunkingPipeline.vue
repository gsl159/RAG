<template>
  <div class="chunking-pipeline">
    <div class="pipeline-header">
      <span class="pipeline-title">文档处理流水线</span>
      <span class="pipeline-doc">{{ docName }}</span>
    </div>
    <div class="pipeline-stages">
      <div v-for="(s, idx) in stages" :key="s.stage"
           :class="['pipeline-stage', 'stage-' + s.status]"
           :style="{ animationDelay: (idx * 0.05) + 's' }">
        <div class="stage-number">{{ s.stage }}</div>
        <div class="stage-info">
          <div class="stage-name">{{ stageNames[s.name] || s.name }}</div>
          <div v-if="s.status==='completed' && s.duration_ms" class="stage-time">{{ s.duration_ms }}ms</div>
          <div v-if="s.status==='failed'" class="stage-error">
            {{ s.error?.error_message }}
            <button v-if="s.error?.recoverable" class="btn btn-xs btn-accent" @click="$emit('retry', s.stage)">重试</button>
          </div>
        </div>
        <div class="stage-status">
          <span v-if="s.status==='completed'" class="status-icon ok">&#10003;</span>
          <span v-else-if="s.status==='processing'" class="status-icon spin">&#8635;</span>
          <span v-else-if="s.status==='failed'" class="status-icon err">&#10007;</span>
          <span v-else-if="s.status==='skipped'" class="status-icon skip">&#8212;</span>
          <span v-else class="status-icon pending">&#9679;</span>
        </div>
        <div v-if="idx < stages.length-1" :class="['stage-connector', 'conn-' + s.status]"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  docId: String,
  docName: { type: String, default: '' },
  stages: { type: Array, default: () => [] },
  currentStage: { type: Number, default: 1 }
})

defineEmits(['retry'])

const stageNames = {
  DocumentParser: '解析文档格式',
  TextCleaner: '清洗文本内容',
  LanguageDetector: '检测文档语言',
  StrategyResolver: '选择分块策略',
  Chunker: '执行文档分块',
  OverlapFixer: '修正重叠边界',
  QualityFilter: '过滤低质量块',
  MetadataInjector: '注入元数据',
  GraphBuilder: '构建引用关系',
  IncrementalUpdater: '增量更新判断'
}
</script>

<style scoped>
.chunking-pipeline { padding: 12px 0; }
.pipeline-header { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 13px; }
.pipeline-title { font-weight: 600; color: var(--text-1); }
.pipeline-doc { color: var(--text-3); }
.pipeline-stages { position: relative; }
.pipeline-stage { display: flex; align-items: center; padding: 6px 0; position: relative; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
.stage-number { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; background: var(--bg-3); color: var(--text-3); }
.stage-completed .stage-number { background: var(--green); color: #fff; }
.stage-processing .stage-number { background: var(--blue); color: #fff; }
.stage-failed .stage-number { background: var(--red); color: #fff; }
.stage-skipped .stage-number { background: var(--bg-3); color: var(--text-4); }
.stage-info { flex: 1; margin-left: 12px; }
.stage-name { font-size: 12px; color: var(--text-2); }
.stage-time { font-size: 10px; color: var(--text-4); }
.stage-error { font-size: 11px; color: var(--red); margin-top: 2px; }
.stage-status { flex-shrink: 0; width: 20px; text-align: center; }
.status-icon.ok { color: var(--green); font-size: 14px; }
.status-icon.err { color: var(--red); font-size: 14px; }
.status-icon.spin { color: var(--blue); font-size: 14px; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.status-icon.pending { color: var(--text-4); font-size: 8px; }
.stage-connector { position: absolute; left: 11px; top: 30px; width: 2px; height: calc(100% - 6px); background: var(--bg-3); }
.conn-completed { background: var(--green); }
.conn-processing { background: var(--blue); }
.btn-xs { padding: 2px 8px; font-size: 10px; border-radius: 4px; border: none; cursor: pointer; }
.btn-accent { background: var(--orange); color: #fff; }
</style>
