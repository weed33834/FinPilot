import { useCallback, useMemo } from 'react'
import DOMPurify from 'dompurify'

/**
 * MarkdownRenderer
 * ----------------
 * 轻量级 Markdown 渲染器，专为金融 Agent 返回的表格 / 代码 / 结构化内容设计。
 *
 * 实现策略：自包含的轻量 Markdown 解析器（正则 + 行扫描）+ DOMPurify XSS 清洗，
 * 不依赖 react-markdown / remark / rehype（项目未安装，且安装存在 React 19 peer 风险）。
 *
 * 支持：
 *  - 标题 / 段落 / 列表（有序、无序）/ 引用 / 分割线
 *  - 表格（GFM 管道表格，含对齐）
 *  - 代码块（围栏 ```）、行内代码
 *  - 代码块复制按钮（事件委托）
 *  - 轻量语法高亮（CSS 类，支持 python / sql / json / js / bash）
 *  - 粗体 / 斜体 / 删除线 / 链接（新标签页打开，rel=noopener noreferrer）/ 图片
 *  - XSS 防护：所有原始 HTML 转义 + DOMPurify 二次清洗
 */

interface MarkdownRendererProps {
  content: string
  className?: string
}

/* ------------------------------------------------------------------ */
/*  XSS 安全：HTML 转义                                                 */
/* ------------------------------------------------------------------ */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/* ------------------------------------------------------------------ */
/*  轻量语法高亮                                                        */
/* ------------------------------------------------------------------ */

const KEYWORDS: Record<string, string[]> = {
  python: [
    'def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'not',
    'and', 'or', 'is', 'None', 'True', 'False', 'import', 'from', 'as', 'try',
    'except', 'finally', 'with', 'raise', 'lambda', 'yield', 'global', 'pass',
    'break', 'continue', 'assert', 'del', 'async', 'await', 'self',
  ],
  sql: [
    'SELECT', 'FROM', 'WHERE', 'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET',
    'DELETE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'ON', 'GROUP', 'BY',
    'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'AS', 'AND', 'OR', 'NOT', 'NULL',
    'CREATE', 'TABLE', 'DROP', 'ALTER', 'INDEX', 'DISTINCT', 'UNION', 'ALL',
    'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
  ],
  json: ['true', 'false', 'null'],
  javascript: [
    'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while',
    'do', 'switch', 'case', 'break', 'continue', 'new', 'try', 'catch',
    'finally', 'throw', 'typeof', 'instanceof', 'in', 'of', 'class', 'extends',
    'super', 'this', 'import', 'from', 'export', 'default', 'async', 'await',
    'yield', 'true', 'false', 'null', 'undefined',
  ],
  js: [
    'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while',
    'do', 'switch', 'case', 'break', 'continue', 'new', 'try', 'catch',
    'finally', 'throw', 'typeof', 'instanceof', 'in', 'of', 'class', 'extends',
    'super', 'this', 'import', 'from', 'export', 'default', 'async', 'await',
    'yield', 'true', 'false', 'null', 'undefined',
  ],
  bash: [
    'if', 'then', 'else', 'fi', 'for', 'in', 'do', 'done', 'while', 'case',
    'esac', 'echo', 'export', 'cd', 'ls', 'cat', 'grep', 'awk', 'sed', 'return',
    'function', 'local', 'exit',
  ],
}

function highlightCode(raw: string, lang: string): string {
  const kw = KEYWORDS[lang.toLowerCase()]
  const kwAlt = kw && kw.length ? `(${kw.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})` : ''

  const parts: string[] = [
    "'''(?:[\\s\\S]*?)'''",
    '"""(?:[\\s\\S]*?)"""',
    "'(?:[^'\\\\\\n]|\\\\.)*'",
    '"(?:[^"\\\\\\n]|\\\\.)*"',
    '`(?:[^`\\\\\\n]|\\\\.)*`',
    '#[^\\n]*',
    '\\/\\/[^\\n]*',
    '--[^\\n]*',
    '\\/\\*[\\s\\S]*?\\*\\/',
    '\\b\\d+(?:\\.\\d+)?\\b',
    kwAlt || 'a^',
  ]
  const re = new RegExp(parts.join('|'), 'g')

  let out = ''
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(raw)) !== null) {
    out += escapeHtml(raw.slice(last, m.index))
    const text = m[0]
    let cls = 'tok-kw'
    if (/^(?:'''|"""|'|"|`)/.test(text)) cls = 'tok-str'
    else if (/^(?:#|\/\/|--|\/\*)/.test(text)) cls = 'tok-com'
    else if (/^\d/.test(text)) cls = 'tok-num'
    out += `<span class="${cls}">${escapeHtml(text)}</span>`
    last = m.index + text.length
    if (re.lastIndex === m.index) re.lastIndex++ // 防止零宽匹配死循环
  }
  out += escapeHtml(raw.slice(last))
  return out
}

/* ------------------------------------------------------------------ */
/*  行内格式                                                            */
/* ------------------------------------------------------------------ */

function inlineFormat(text: string): string {
  let s = escapeHtml(text)

  // 行内代码先抽取占位，避免内部 * / _ 被处理
  const codes: string[] = []
  s = s.replace(/`([^`]+)`/g, (_m, c: string) => {
    codes.push(c)
    return `\u0000CODE${codes.length - 1}\u0000`
  })

  // 图片
  s = s.replace(
    /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    (_m, alt: string, url: string, title?: string) =>
      `<img src="${url}" alt="${alt}"${title ? ` title="${title}"` : ''} loading="lazy" />`,
  )

  // 链接（新标签页打开）
  s = s.replace(
    /\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    (_m, t: string, url: string, title?: string) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer"${title ? ` title="${title}"` : ''}>${t}</a>`,
  )

  // 粗体
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  // 删除线
  s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>')
  // 斜体
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  s = s.replace(/(?<![A-Za-z0-9])_([^_]+)_(?![A-Za-z0-9])/g, '<em>$1</em>')

  // 还原行内代码
  s = s.replace(/\u0000CODE(\d+)\u0000/g, (_m, n: string) => `<code class="md-inline">${codes[+n]}</code>`)

  return s
}

/* ------------------------------------------------------------------ */
/*  代码块渲染                                                          */
/* ------------------------------------------------------------------ */

function renderCodeBlock(code: string, lang: string): string {
  const safeLang = /^[a-zA-Z0-9+-]+$/.test(lang) ? lang : ''
  const highlighted = safeLang ? highlightCode(code, safeLang) : escapeHtml(code)
  const langLabel = safeLang || 'text'
  return (
    `<div class="md-code-block">` +
    `<div class="md-code-head"><span class="md-code-lang">${escapeHtml(langLabel)}</span>` +
    `<button type="button" class="md-code-copy">复制</button></div>` +
    `<pre><code class="md-code-content${safeLang ? ` language-${escapeHtml(safeLang)}` : ''}">${highlighted}</code></pre>` +
    `</div>`
  )
}

/* ------------------------------------------------------------------ */
/*  表格渲染                                                            */
/* ------------------------------------------------------------------ */

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((c) => c.trim())
}

function isTableSeparator(line: string): boolean {
  const t = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return /^\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*$/.test(t)
}

function renderTable(headerLine: string, _sepLine: string, rows: string[]): string {
  const headers = splitTableRow(headerLine)
  const head = headers
    .map((h) => `<th>${inlineFormat(h)}</th>`)
    .join('')
  const body = rows
    .map((r) => {
      const cells = splitTableRow(r)
      return `<tr>${cells.map((c) => `<td>${inlineFormat(c)}</td>`).join('')}</tr>`
    })
    .join('')
  return `<div class="md-table-wrap"><table class="md-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
}

/* ------------------------------------------------------------------ */
/*  块级解析                                                            */
/* ------------------------------------------------------------------ */

function markdownToHtml(md: string): string {
  const src = md.replace(/\r\n?/g, '\n')
  const lines = src.split('\n')
  const blocks: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // 空行
    if (line.trim() === '') {
      i++
      continue
    }

    // 围栏代码块
    const fence = line.match(/^(`{3,}|~{3,})\s*([\w+-]*)\s*$/)
    if (fence) {
      const marker = fence[1][0]
      const minLen = fence[1].length
      const lang = fence[2] || ''
      const codeLines: string[] = []
      i++
      while (i < lines.length) {
        const cl = lines[i]
        const closeRe = new RegExp(`^${marker === '`' ? '`' : '~'}{${minLen},}\\s*$`)
        if (closeRe.test(cl.trim())) break
        codeLines.push(cl)
        i++
      }
      i++ // 跳过结束围栏
      blocks.push(renderCodeBlock(codeLines.join('\n'), lang))
      continue
    }

    // 表格
    if (
      line.includes('|') &&
      /^\s*\|?.*\|/.test(line) &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      const headerLine = line
      const sepLine = lines[i + 1]
      i += 2
      const rows: string[] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(lines[i])
        i++
      }
      blocks.push(renderTable(headerLine, sepLine, rows))
      continue
    }

    // 标题
    const h = line.match(/^(#{1,6})\s+(.*)\s*#*\s*$/)
    if (h) {
      const level = h[1].length
      blocks.push(`<h${level}>${inlineFormat(h[2])}</h${level}>`)
      i++
      continue
    }

    // 分割线
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push('<hr />')
      i++
      continue
    }

    // 引用
    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = []
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s?/, ''))
        i++
      }
      blocks.push(`<blockquote>${inlineFormat(quoteLines.join('\n').replace(/\n/g, '<br />'))}</blockquote>`)
      continue
    }

    // 无序列表
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ''))
        i++
      }
      blocks.push(`<ul>${items.map((it) => `<li>${inlineFormat(it)}</li>`).join('')}</ul>`)
      continue
    }

    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''))
        i++
      }
      blocks.push(`<ol>${items.map((it) => `<li>${inlineFormat(it)}</li>`).join('')}</ol>`)
      continue
    }

    // 段落：收集连续非块级行
    const paraLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(`{3,}|~{3,})/.test(lines[i]) &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      !/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(lines[i]) &&
      !/^>\s?/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      // 停在表格起始
      if (
        paraLines.length > 0 &&
        lines[i].includes('|') &&
        i + 1 < lines.length &&
        isTableSeparator(lines[i + 1])
      ) {
        break
      }
      paraLines.push(lines[i])
      i++
    }
    if (paraLines.length > 0) {
      blocks.push(`<p>${inlineFormat(paraLines.join('\n').replace(/\n/g, '<br />'))}</p>`)
    }
  }

  return blocks.join('\n')
}

/* ------------------------------------------------------------------ */
/*  注入一次样式                                                        */
/* ------------------------------------------------------------------ */

let styleInjected = false
function ensureStyle(): void {
  if (styleInjected || typeof document === 'undefined') return
  styleInjected = true
  const css = `
.md-body { font-size: 0.875rem; line-height: 1.65; word-break: break-word; }
.md-body > :first-child { margin-top: 0; }
.md-body > :last-child { margin-bottom: 0; }
.md-body h1 { font-size: 1.5rem; font-weight: 700; margin: 0.8em 0 0.4em; }
.md-body h2 { font-size: 1.3rem; font-weight: 700; margin: 0.8em 0 0.4em; }
.md-body h3 { font-size: 1.12rem; font-weight: 600; margin: 0.7em 0 0.35em; }
.md-body h4 { font-size: 1rem; font-weight: 600; margin: 0.6em 0 0.3em; }
.md-body h5,.md-body h6 { font-size: 0.9rem; font-weight: 600; margin: 0.5em 0 0.3em; }
.md-body p { margin: 0.5em 0; }
.md-body ul,.md-body ol { margin: 0.5em 0; padding-left: 1.5em; }
.md-body li { margin: 0.2em 0; }
.md-body blockquote { margin: 0.5em 0; padding: 0.3em 0.9em; border-left: 3px solid var(--color-border,#444); color: var(--color-text-muted,#9aa); background: rgba(127,127,127,0.06); }
.md-body hr { border: none; border-top: 1px solid var(--color-border,#444); margin: 0.9em 0; }
.md-body a { color: var(--color-primary,#3b82f6); text-decoration: underline; }
.md-body a:hover { opacity: 0.85; }
.md-body img { max-width: 100%; border-radius: 6px; }
.md-body .md-inline { background: rgba(127,127,127,0.18); padding: 1px 5px; border-radius: 4px; font-family: var(--font-mono,monospace); font-size: 0.85em; }
.md-body .md-table-wrap { overflow-x: auto; margin: 0.6em 0; }
.md-body .md-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.md-body .md-table th,.md-body .md-table td { border: 1px solid var(--color-border,#3a3f4b); padding: 6px 10px; text-align: left; vertical-align: top; }
.md-body .md-table th { background: rgba(127,127,127,0.12); font-weight: 600; }
.md-body .md-table tbody tr:nth-child(even) { background: rgba(127,127,127,0.04); }
.md-body .md-code-block { margin: 0.6em 0; border: 1px solid var(--color-border,#3a3f4b); border-radius: 8px; overflow: hidden; background: rgba(0,0,0,0.28); }
.md-body .md-code-head { display: flex; justify-content: space-between; align-items: center; padding: 4px 10px; font-size: 0.7rem; color: #9aa4b2; border-bottom: 1px solid var(--color-border,#3a3f4b); background: rgba(127,127,127,0.08); }
.md-body .md-code-lang { font-family: var(--font-mono,monospace); text-transform: lowercase; }
.md-body .md-code-copy { background: transparent; border: 1px solid #4a505c; color: #9aa4b2; border-radius: 4px; padding: 1px 9px; font-size: 0.7rem; cursor: pointer; transition: all .15s ease; }
.md-body .md-code-copy:hover { background: rgba(255,255,255,0.1); color: #fff; border-color: #6a707c; }
.md-body .md-code-block pre { margin: 0; padding: 10px 12px; overflow-x: auto; }
.md-body .md-code-content { font-family: var(--font-mono,monospace); font-size: 0.8rem; line-height: 1.55; white-space: pre; color: #e6edf3; }
.md-body .tok-kw { color: #ff7b72; }
.md-body .tok-str { color: #a5d6ff; }
.md-body .tok-num { color: #79c0ff; }
.md-body .tok-com { color: #8b949e; font-style: italic; }
.md-body strong { font-weight: 700; }
.md-body em { font-style: italic; }
.md-body del { text-decoration: line-through; opacity: 0.8; }
`
  const style = document.createElement('style')
  style.setAttribute('data-md-renderer', 'true')
  style.textContent = css
  document.head.appendChild(style)
}
ensureStyle()

/* ------------------------------------------------------------------ */
/*  组件                                                                */
/* ------------------------------------------------------------------ */

export default function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const html = useMemo(() => {
    const raw = markdownToHtml(content ?? '')
    return DOMPurify.sanitize(raw, {
      ADD_ATTR: ['target', 'rel', 'loading', 'title'],
      ADD_TAGS: ['button'],
    })
  }, [content])

  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    const btn = target.closest('.md-code-copy') as HTMLButtonElement | null
    if (!btn) return
    const block = btn.closest('.md-code-block')
    const codeEl = block?.querySelector('.md-code-content')
    if (!codeEl) return
    const text = codeEl.textContent || ''
    const clipboard = navigator.clipboard
    const flash = () => {
      const original = btn.textContent
      btn.textContent = '已复制'
      window.setTimeout(() => {
        btn.textContent = original
      }, 1500)
    }
    if (clipboard && typeof clipboard.writeText === 'function') {
      void clipboard.writeText(text).then(flash).catch(() => {
        /* ignore */
      })
    } else {
      // 回退：使用临时 textarea 执行复制
      try {
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
        flash()
      } catch {
        /* ignore */
      }
    }
  }, [])

  return (
    <div
      className={`md-body${className ? ` ${className}` : ''}`}
      onClick={handleClick}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
