/**
 * A deliberately small Markdown renderer.
 *
 * FORGE stores dossier prose as Markdown and must display it without pulling in
 * a parser + sanitiser pair. This renderer emits React elements directly - there
 * is no HTML string anywhere in the path - so untrusted content cannot inject
 * markup. It covers what the app actually writes: headings, lists, blockquotes,
 * horizontal rules, bold/italic/code and bare links.
 */

import type { ReactNode } from 'react'

const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`]+`|https?:\/\/\S+)/g

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let index = 0
  for (const part of text.split(INLINE)) {
    if (!part) continue
    const key = `${keyPrefix}-${index++}`
    if ((part.startsWith('**') && part.endsWith('**')) || (part.startsWith('__') && part.endsWith('__'))) {
      nodes.push(<strong key={key}>{part.slice(2, -2)}</strong>)
    } else if (
      (part.startsWith('*') && part.endsWith('*') && part.length > 2) ||
      (part.startsWith('_') && part.endsWith('_') && part.length > 2)
    ) {
      nodes.push(<em key={key}>{part.slice(1, -1)}</em>)
    } else if (part.startsWith('`') && part.endsWith('`') && part.length > 1) {
      nodes.push(<code key={key}>{part.slice(1, -1)}</code>)
    } else if (/^https?:\/\//.test(part)) {
      nodes.push(
        <a key={key} href={part} target="_blank" rel="noreferrer noopener">
          {part}
        </a>,
      )
    } else {
      nodes.push(<span key={key}>{part}</span>)
    }
  }
  return nodes
}

interface Block {
  type: 'heading' | 'paragraph' | 'ul' | 'ol' | 'quote' | 'rule'
  level?: number
  lines: string[]
}

export function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = []
  const lines = (markdown ?? '').replace(/\r\n/g, '\n').split('\n')
  let current: Block | null = null

  const flush = () => {
    if (current && (current.lines.length > 0 || current.type === 'rule')) blocks.push(current)
    current = null
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()

    if (!line.trim()) {
      flush()
      continue
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      flush()
      blocks.push({ type: 'heading', level: heading[1].length, lines: [heading[2]] })
      continue
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      flush()
      blocks.push({ type: 'rule', lines: [] })
      continue
    }
    const unordered = /^\s*[-*+]\s+(.*)$/.exec(line)
    if (unordered) {
      if (!current || current.type !== 'ul') {
        flush()
        current = { type: 'ul', lines: [] }
      }
      current.lines.push(unordered[1])
      continue
    }
    const ordered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (ordered) {
      if (!current || current.type !== 'ol') {
        flush()
        current = { type: 'ol', lines: [] }
      }
      current.lines.push(ordered[1])
      continue
    }
    const quote = /^>\s?(.*)$/.exec(line)
    if (quote) {
      if (!current || current.type !== 'quote') {
        flush()
        current = { type: 'quote', lines: [] }
      }
      current.lines.push(quote[1])
      continue
    }
    if (!current || current.type !== 'paragraph') {
      flush()
      current = { type: 'paragraph', lines: [] }
    }
    current.lines.push(line)
  }
  flush()
  return blocks
}

export function Markdown({ text, className = 'md' }: { text: string; className?: string }) {
  const blocks = parseBlocks(text)
  if (blocks.length === 0) return null

  return (
    <div className={className}>
      {blocks.map((block, index) => {
        const key = `block-${index}`
        switch (block.type) {
          case 'heading': {
            const Tag = (`h${Math.min(block.level ?? 2, 4)}` as unknown) as 'h2'
            return <Tag key={key}>{renderInline(block.lines[0] ?? '', key)}</Tag>
          }
          case 'ul':
            return (
              <ul key={key}>
                {block.lines.map((line, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{renderInline(line, `${key}-${itemIndex}`)}</li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={key}>
                {block.lines.map((line, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{renderInline(line, `${key}-${itemIndex}`)}</li>
                ))}
              </ol>
            )
          case 'quote':
            return <blockquote key={key}>{renderInline(block.lines.join(' '), key)}</blockquote>
          case 'rule':
            return <hr key={key} />
          default:
            return <p key={key}>{renderInline(block.lines.join(' '), key)}</p>
        }
      })}
    </div>
  )
}
