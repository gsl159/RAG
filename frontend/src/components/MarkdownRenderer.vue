<template>
  <div class="md-render" ref="container" v-html="rendered" @click="onContainerClick"></div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
// 按需注册常用语言
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import java from 'highlight.js/lib/languages/java'
import go from 'highlight.js/lib/languages/go'
import yaml from 'highlight.js/lib/languages/yaml'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('java', java)
hljs.registerLanguage('go', go)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)

const props = defineProps({
  content: { type: String, default: '' },
})

const emit = defineEmits(['cite-click'])
const container = ref(null)

// ── markdown-it 实例 ──
const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        return `<pre class="code-block hljs"><div class="code-lang">${lang}</div><code>${highlighted}</code></pre>`
      } catch (e) { console.error(e) }
    }
    const escaped = md.utils.escapeHtml(str)
    return `<pre class="code-block"><code>${escaped}</code></pre>`
  },
})

// ── KaTeX 内联与块级公式 ──
function renderKatex(text) {
  let result = text
  // 块级 $$ ... $$
  result = result.replace(/\$\$([\s\S]+?)\$\$/g, (_, math) => {
    try {
      const katex = window.__katex
      if (katex) return `<div class="katex-block">${katex.renderToString(math.trim(), { displayMode: true, throwOnError: false })}</div>`
    } catch (e) { console.error(e) }
    return `<div class="katex-block katex-error">$$${math}$$</div>`
  })
  // 内联 $...$（排除 $$）
  result = result.replace(/(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)/g, (_, math) => {
    try {
      const katex = window.__katex
      if (katex) return katex.renderToString(math.trim(), { displayMode: false, throwOnError: false })
    } catch (e) { console.error(e) }
    return `<code class="katex-error">${math}</code>`
  })
  return result
}

// ── Mermaid 图表检测 ──
function processMermaid(html) {
  // 将 ```mermaid 代码块的 <pre> 替换为可渲染的 div
  return html.replace(
    /<pre class="code-block[^"]*"><div class="code-lang">mermaid<\/div><code>([\s\S]*?)<\/code><\/pre>/g,
    (_, code) => {
      const decoded = code.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
      return `<div class="mermaid-block" data-mermaid="${encodeURIComponent(decoded)}">${decoded}</div>`
    }
  )
}

// ── 来源引用 [来源N] ──
function processCitations(html) {
  let result = html
  // 【来源：[来源1]、[来源2]...】
  result = result.replace(/【来源：(.*?)】/g, (_, inner) => {
    return inner.replace(/\[来源(\d+)\]/g, '<span class="cite-link" data-src="$1">来源$1</span>')
  })
  // 单独的 [来源N]
  result = result.replace(/\[来源(\d+)\]/g, '<span class="cite-link" data-src="$1">来源$1</span>')
  return result
}

const rendered = computed(() => {
  if (!props.content) return ''
  let html = md.render(props.content)
  html = processMermaid(html)
  html = renderKatex(html)
  html = processCitations(html)
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['mark'],
    ADD_ATTR: ['data-src', 'data-mermaid', 'class'],
    ALLOW_ARIA_ATTR: true,
  })
})

// ── 动态加载 KaTeX CSS + JS ──
let katexLoaded = false
function ensureKatex() {
  if (katexLoaded) return
  katexLoaded = true
  // CSS
  if (!document.querySelector('link[href*="katex"]')) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css'
    document.head.appendChild(link)
  }
  // JS
  if (!window.__katex) {
    import('katex').then(m => {
      window.__katex = m.default || m
    }).catch(() => {})
  }
}

// ── Mermaid 渲染 ──
async function renderMermaidBlocks() {
  await nextTick()
  if (!container.value) return
  const blocks = container.value.querySelectorAll('.mermaid-block[data-mermaid]')
  if (!blocks.length) return
  try {
    const mermaid = (await import('mermaid')).default
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      themeVariables: {
        primaryColor: '#00f3ff',
        primaryTextColor: '#e0e6ff',
        lineColor: '#555c85',
        secondaryColor: '#b967ff',
        tertiaryColor: '#0a0e27',
      },
    })
    for (const block of blocks) {
      const code = decodeURIComponent(block.dataset.mermaid)
      const id = 'mermaid-' + Math.random().toString(36).slice(2, 8)
      try {
        const { svg } = await mermaid.render(id, code)
        block.innerHTML = svg
        block.classList.add('mermaid-rendered')
      } catch {
        block.classList.add('mermaid-error')
      }
    }
  } catch (e) { console.error(e) }
}

onMounted(ensureKatex)

watch(() => props.content, async () => {
  await nextTick()
  renderMermaidBlocks()
})

onMounted(() => renderMermaidBlocks())

function onContainerClick(event) {
  const cite = event.target.closest('.cite-link')
  if (cite) {
    emit('cite-click', parseInt(cite.dataset.src, 10))
  }
}
</script>

<style>
/* ── highlight.js 暗色主题 ── */
.md-render .hljs { background: transparent; }
.hljs-keyword   { color: #b967ff; }
.hljs-string    { color: #05ffa1; }
.hljs-number    { color: #ffbe0b; }
.hljs-comment   { color: #555c85; font-style: italic; }
.hljs-function   { color: #00f3ff; }
.hljs-title      { color: #00f3ff; }
.hljs-params     { color: #e0e6ff; }
.hljs-built_in   { color: #ff6b9d; }
.hljs-literal    { color: #ffbe0b; }
.hljs-attr       { color: #b967ff; }
.hljs-type       { color: #00f3ff; }
.hljs-meta       { color: #8b91c8; }
.hljs-selector-tag { color: #ff6b9d; }
.hljs-selector-class { color: #00f3ff; }
.hljs-selector-id  { color: #b967ff; }
.hljs-name       { color: #ff6b9d; }
.hljs-tag        { color: #8b91c8; }
.hljs-attribute  { color: #b967ff; }
.hljs-variable   { color: #e0e6ff; }
.hljs-symbol     { color: #05ffa1; }

/* ── Markdown 内容样式 ── */
.md-render { line-height: 1.75; word-break: break-word; }

.md-render h1, .md-render h2, .md-render h3, .md-render h4 {
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-weight: 600; color: #00f3ff; margin: 14px 0 6px;
  letter-spacing: 0.3px;
}
.md-render h1 { font-size: 17px; }
.md-render h2 { font-size: 15px; }
.md-render h3 { font-size: 14px; }
.md-render h4 { font-size: 13px; }

.md-render p { margin: 6px 0; }

.md-render ul, .md-render ol { padding-left: 20px; margin: 6px 0; }
.md-render li { margin: 3px 0; }
.md-render li::marker { color: #00f3ff; }

.md-render blockquote {
  border-left: 3px solid #b967ff;
  padding: 6px 14px;
  margin: 8px 0;
  background: rgba(185, 103, 255, 0.05);
  color: var(--text-2);
}

.md-render strong { color: #e8eeff; font-weight: 600; }
.md-render em { color: #b0b8e0; }

.md-render a {
  color: #00f3ff;
  text-decoration: underline;
  text-decoration-color: rgba(0, 243, 255, 0.3);
}
.md-render a:hover { text-decoration-color: #00f3ff; }

.md-render hr {
  border: none;
  border-top: 1px solid rgba(0, 243, 255, 0.15);
  margin: 12px 0;
}

.md-render table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 12px;
}
.md-render th, .md-render td {
  border: 1px solid rgba(0, 243, 255, 0.15);
  padding: 6px 10px;
  text-align: left;
}
.md-render th {
  background: rgba(0, 243, 255, 0.06);
  color: #00f3ff;
  font-weight: 600;
  font-family: "Orbitron", sans-serif;
  font-size: 10px;
  letter-spacing: 0.5px;
}

/* ── Code blocks ── */
.md-render .code-block {
  background: rgba(0, 243, 255, 0.04);
  border: 1px solid rgba(0, 243, 255, 0.1);
  border-radius: 8px;
  padding: 10px 14px;
  margin: 8px 0;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  color: #e0e6ff;
  position: relative;
}
.md-render .code-lang {
  position: absolute;
  top: 4px; right: 8px;
  font-size: 9px;
  color: var(--text-3);
  font-family: "Orbitron", sans-serif;
  letter-spacing: 0.5px;
  opacity: 0.6;
}
.md-render code:not(.code-block code) {
  background: rgba(0, 243, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  color: #00f3ff;
}

/* ── KaTeX ── */
.md-render .katex-block {
  margin: 10px 0;
  text-align: center;
  overflow-x: auto;
}
.md-render .katex-error {
  color: var(--red);
  font-size: 12px;
}

/* ── Mermaid ── */
.md-render .mermaid-block {
  background: rgba(0, 243, 255, 0.03);
  border: 1px solid rgba(0, 243, 255, 0.1);
  border-radius: 8px;
  padding: 14px;
  margin: 10px 0;
  text-align: center;
  overflow-x: auto;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  white-space: pre-wrap;
  color: var(--text-2);
}
.md-render .mermaid-rendered {
  white-space: normal;
  font-family: inherit;
  font-size: inherit;
}
.md-render .mermaid-error {
  border-color: rgba(255, 0, 110, 0.3);
}

/* ── Citations ── */
.md-render .cite-link {
  color: #00f3ff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 5px;
  margin: 0 1px;
  border-radius: 3px;
  background: rgba(0, 243, 255, 0.1);
  transition: all 0.2s;
  display: inline-block;
  font-family: "JetBrains Mono", monospace;
}
.md-render .cite-link:hover {
  background: rgba(0, 243, 255, 0.25);
  box-shadow: 0 0 8px rgba(0, 243, 255, 0.3);
}

/* ── Light theme overrides ── */
[data-theme="light"] .md-render h1,
[data-theme="light"] .md-render h2,
[data-theme="light"] .md-render h3,
[data-theme="light"] .md-render h4 { color: #0066cc; }
[data-theme="light"] .md-render .code-block {
  background: rgba(0, 0, 0, 0.04);
  border-color: rgba(0, 0, 0, 0.1);
}
[data-theme="light"] .md-render code:not(.code-block code) {
  background: rgba(0, 102, 204, 0.08);
  color: #0066cc;
}
[data-theme="light"] .md-render .cite-link {
  background: rgba(0, 102, 204, 0.1);
  color: #0066cc;
}
</style>
