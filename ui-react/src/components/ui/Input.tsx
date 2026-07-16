import React, { useId } from 'react'
import { Hint } from './Hint'

// Label do campo com "?" de ajuda contextual opcional (prop `hint`).
// Sem hint renderiza o <label> puro — layout idêntico ao original.
// htmlFor liga o label ao campo (a11y/getByLabel — F10 da migração Caixa):
// clique no rótulo foca o campo e leitores de tela anunciam o nome.
function FieldLabel({ label, hint, htmlFor }: { label?: string; hint?: string; htmlFor?: string }) {
  if (!label) return null
  if (!hint) return <label htmlFor={htmlFor} className="text-xs text-dim font-medium">{label}</label>
  return (
    <span className="flex items-center gap-1">
      <label htmlFor={htmlFor} className="text-xs text-dim font-medium">{label}</label>
      <Hint texto={hint} />
    </span>
  )
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ label, error, hint, className = '', id, ...rest }, ref) {
    const autoId = useId()
    const fieldId = id ?? (label ? autoId : undefined)
    return (
      <div className="flex flex-col gap-1">
        <FieldLabel label={label} hint={hint} htmlFor={fieldId} />
        <input
          ref={ref}
          id={fieldId}
          {...rest}
          className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
        />
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>
    )
  }
)

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
}

export function Select({ label, error, hint, className = '', id, children, ...rest }: SelectProps) {
  const autoId = useId()
  const fieldId = id ?? (label ? autoId : undefined)
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} hint={hint} htmlFor={fieldId} />
      <select
        id={fieldId}
        {...rest}
        className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
      >
        {children}
      </select>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; error?: string; hint?: string }
>(function Textarea({ label, error, hint, className = '', id, ...rest }, ref) {
  const autoId = useId()
  const fieldId = id ?? (label ? autoId : undefined)
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} hint={hint} htmlFor={fieldId} />
      <textarea
        ref={ref}
        id={fieldId}
        {...rest}
        className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y ${className}`}
      />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
})
