import React from 'react'

interface PlaceholderPickerProps {
  placeholders: string[]
  // React 19: useRef<T>(null) infere RefObject<T | null>; aceitamos o null para
  // bater com as três telas que criam useRef<HTMLTextAreaElement>(null).
  targetRef: React.RefObject<HTMLTextAreaElement | null>
  value: string
  onChange: (next: string) => void
  label?: string
}

// Chips clicáveis que inserem o token {placeholder} na posição do cursor da
// textarea apontada por targetRef (preserva a seleção mesmo após o textarea
// perder o foco para o botão — selectionStart/End continuam válidos). Aditivo:
// não altera o contrato da textarea, só escreve em value via onChange.
export function PlaceholderPicker({ placeholders, targetRef, value, onChange, label }: PlaceholderPickerProps) {
  function insert(ph: string) {
    const token = `{${ph}}`
    const el = targetRef.current
    const start = el?.selectionStart ?? value.length
    const end = el?.selectionEnd ?? value.length
    const next = value.slice(0, start) + token + value.slice(end)
    onChange(next)
    requestAnimationFrame(() => {
      if (!el) return
      el.focus()
      const pos = start + token.length
      el.setSelectionRange(pos, pos)
    })
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {label && <span className="text-[10px] text-dim">{label}</span>}
      {placeholders.map(ph => (
        <button
          key={ph}
          type="button"
          onClick={() => insert(ph)}
          title={`Inserir {${ph}} no texto`}
          aria-label={`Inserir placeholder ${ph}`}
          className="font-mono text-[10px] leading-none px-1.5 py-1 rounded border border-edge text-dim hover:bg-edge/40 hover:text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {`{${ph}}`}
        </button>
      ))}
    </div>
  )
}
