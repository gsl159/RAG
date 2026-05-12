<template>
  <div class="chunk-graph">
    <div class="graph-node parent" v-if="parentChunk" @click="$emit('navigate', parentChunk.chunk_id)">
      <div class="node-label">父块</div>
      <div class="node-text">{{ (parentChunk.content || '').slice(0, 50) }}...</div>
    </div>
    <div class="graph-arrow up" v-if="parentChunk">&#8593;</div>
    <div class="graph-row">
      <div class="graph-node sibling" v-if="prevChunk" @click="$emit('navigate', prevChunk.chunk_id)">
        <div class="node-label">&#8592; 前一块</div>
        <div class="node-text">{{ (prevChunk.content || '').slice(0, 30) }}...</div>
      </div>
      <div class="graph-node current">
        <div class="node-label">当前块 #{{ currentChunk.chunk_index }}</div>
        <div class="node-text">{{ (currentChunk.content || '').slice(0, 50) }}...</div>
      </div>
      <div class="graph-node sibling" v-if="nextChunk" @click="$emit('navigate', nextChunk.chunk_id)">
        <div class="node-label">后一块 &#8594;</div>
        <div class="node-text">{{ (nextChunk.content || '').slice(0, 30) }}...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  currentChunk: { type: Object, required: true },
  parentChunk: { type: Object, default: null },
  prevChunk: { type: Object, default: null },
  nextChunk: { type: Object, default: null },
})
defineEmits(['navigate'])
</script>

<style scoped>
.chunk-graph { padding: 12px; }
.graph-node { background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; cursor: pointer; transition: all 0.2s; }
.graph-node:hover { border-color: var(--blue); }
.graph-node.parent { margin-bottom: 4px; }
.graph-node.current { border-color: var(--blue); border-width: 2px; flex: 2; }
.graph-node.sibling { flex: 1; opacity: 0.8; }
.node-label { font-size: 10px; color: var(--text-4); margin-bottom: 4px; text-transform: uppercase; }
.node-text { font-size: 12px; color: var(--text-2); line-height: 1.4; }
.graph-arrow { text-align: center; color: var(--text-4); font-size: 18px; margin: 2px 0; }
.graph-arrow.up { margin-bottom: 0; }
.graph-row { display: flex; gap: 8px; }
</style>
