// ── Switch: liga/desliga nativo do DS ────────────────────────────────────────
// Mesmo padrão do Checkbox: input real sr-only + trilho visual via peer; o
// polegar é um after: que translada no checked. Thumb branco fixo funciona
// sobre o trilho nos dois temas (edge desligado, blue-600 ligado).
import React from 'react'
import { Hint } from './Hint'

export interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'role'> {
  label?: React.ReactNode
  hint?: string
}

export const Switch = React.forwardRef<HTMLInputElement, SwitchProps>(
  function Switch({ label, hint, className = '', disabled, ...rest }, ref) {
    return (
      <span className={`inline-flex items-center gap-1.5 ${className}`}>
        <label className={`inline-flex items-center gap-2 select-none ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}>
          <input ref={ref} type="checkbox" role="switch" disabled={disabled} {...rest} className="peer sr-only" />
          <span
            aria-hidden="true"
            className="relative h-5 w-9 shrink-0 rounded-full bg-edge transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:border after:border-black/10 after:bg-white after:shadow after:transition-transform peer-checked:bg-blue-600 peer-checked:after:translate-x-4 peer-focus-visible:ring-1 peer-focus-visible:ring-blue-500"
          />
          {label && <span className="text-sm text-ink">{label}</span>}
        </label>
        {hint && <Hint texto={hint} />}
      </span>
    )
  }
)
