// ── RadioGroup/RadioItem: seleção única nativa do DS ─────────────────────────
// Contexto distribui name/value/onValueChange aos itens (shape análogo ao
// shadcn radio-group, facilitando o porte da seção Caixa Seguro). Cada item é
// um input radio real sr-only + círculo visual via peer, como o Checkbox.
import React from 'react'

interface RadioCtxValue {
  name: string
  value?: string
  onValueChange?: (value: string) => void
  disabled?: boolean
}

const RadioCtx = React.createContext<RadioCtxValue | null>(null)

export interface RadioGroupProps {
  /** name compartilhado dos inputs; gerado automaticamente se omitido. */
  name?: string
  value?: string
  onValueChange?: (value: string) => void
  disabled?: boolean
  /** aria-label do grupo. */
  label?: string
  className?: string
  children: React.ReactNode
}

export function RadioGroup({ name, value, onValueChange, disabled, label, className = '', children }: RadioGroupProps) {
  const autoName = React.useId()
  return (
    <div role="radiogroup" aria-label={label} className={`flex flex-col gap-2 ${className}`}>
      <RadioCtx.Provider value={{ name: name ?? autoName, value, onValueChange, disabled }}>
        {children}
      </RadioCtx.Provider>
    </div>
  )
}

export interface RadioItemProps {
  value: string
  label?: React.ReactNode
  disabled?: boolean
  className?: string
}

export function RadioItem({ value, label, disabled, className = '' }: RadioItemProps) {
  const ctx = React.useContext(RadioCtx)
  if (!ctx) throw new Error('RadioItem deve ser usado dentro de RadioGroup')
  const isDisabled = disabled || ctx.disabled
  return (
    <label className={`inline-flex items-center gap-2 select-none ${isDisabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'} ${className}`}>
      <input
        type="radio"
        name={ctx.name}
        value={value}
        checked={ctx.value === value}
        onChange={() => ctx.onValueChange?.(value)}
        disabled={isDisabled}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className="relative h-4 w-4 shrink-0 rounded-full border border-edge bg-panel transition-colors peer-checked:border-blue-600 after:absolute after:left-1/2 after:top-1/2 after:h-2 after:w-2 after:-translate-x-1/2 after:-translate-y-1/2 after:rounded-full after:bg-blue-600 after:opacity-0 after:transition-opacity peer-checked:after:opacity-100 peer-focus-visible:ring-1 peer-focus-visible:ring-blue-500"
      />
      {label && <span className="text-sm text-ink">{label}</span>}
    </label>
  )
}
