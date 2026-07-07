// ── Hint: ajuda contextual por campo ─────────────────────────────────────────
// "?" discreto ao lado do label de um campo; no hover/focus abre um popover
// leve (div absolute) com a explicação — descrição/default/exemplo. Sem lib
// externa: wrapper relative + div absolute acima do ícone. `texto` aceita \n
// (vira quebra de linha via whitespace-pre-line). Acessível: focável por
// teclado (tabIndex) com aria-label; Escape fecha.
import { useState } from 'react'
import { HelpCircle } from 'lucide-react'

export interface HintProps {
  texto: string
}

export function Hint({ texto }: HintProps) {
  const [open, setOpen] = useState(false)
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span
        tabIndex={0}
        role="note"
        aria-label={texto}
        className="inline-flex cursor-help text-dim/70 hover:text-ink focus:text-ink focus:outline-none"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}
      >
        <HelpCircle size={12} strokeWidth={2} aria-hidden />
      </span>
      {open && (
        <div
          role="tooltip"
          className="absolute bottom-full left-0 z-50 mb-1.5 w-max max-w-64 whitespace-pre-line rounded-md border border-edge bg-panel px-2.5 py-1.5 text-left text-[11px] font-normal leading-relaxed text-ink shadow-lg"
        >
          {texto}
        </div>
      )}
    </span>
  )
}
