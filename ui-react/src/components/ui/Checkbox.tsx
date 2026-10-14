// ── Checkbox: caixa de seleção nativa do DS ──────────────────────────────────
// Input real (foco, teclado e leitor de tela de graça) escondido com sr-only;
// o visual é um span irmão dirigido por peer-checked/peer-focus-visible — sem
// Radix. O Hint fica FORA do <label> para o clique no "?" não togglar o campo.
import React from 'react'
import { Check } from 'lucide-react'
import { Hint } from './Hint'

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: React.ReactNode
  hint?: string
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox({ label, hint, className = '', disabled, ...rest }, ref) {
    return (
      <span className={`inline-flex items-center gap-1.5 ${className}`}>
        {/* `relative`: o input sr-only é `position: absolute`; sem ancestral posicionado ele
            se ancora no documento e, abaixo da dobra, estica a área rolável da página inteira
            (a tela "ia para baixo" na aba Utilitários do Admin — captura de 2026-09-07). */}
        <label className={`ui-choice relative inline-flex items-center gap-2 select-none min-w-0 ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}>
          <input ref={ref} type="checkbox" disabled={disabled} {...rest} className="peer sr-only" />
          <span
            aria-hidden="true"
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded border border-control-border bg-panel text-transparent transition-colors peer-checked:border-blue-600 peer-checked:bg-blue-600 peer-checked:text-white peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus"
          >
            <Check size={12} strokeWidth={3} />
          </span>
          {label && <span className="min-w-0 break-words text-sm text-ink">{label}</span>}
        </label>
        {hint && <Hint texto={hint} />}
      </span>
    )
  }
)
