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

// Ajuda SEMPRE VISÍVEL abaixo do campo (prop `ajuda`), alternativa ao `hint`.
//
// Por que existe: o `hint` é um popover `absolute` que abre para CIMA
// (Hint.tsx). Dentro de um Modal — cujo corpo tem `overflow-y-auto` — ele é
// clipado pelo contêiner de scroll e simplesmente não aparece nos campos do
// topo. Clipping por overflow ignora z-index, então subir o z não resolve.
// Em formulário dentro de modal, use `ajuda`; o `hint` continua válido em
// tela cheia, onde não há contêiner de scroll cortando.
function FieldHelp({ ajuda, id }: { ajuda?: string; id?: string }) {
  if (!ajuda) return null
  return <span id={id} className="text-[11px] leading-snug text-dim">{ajuda}</span>
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  ajuda?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ label, error, hint, ajuda, className = '', id, ...rest }, ref) {
    const autoId = useId()
    const fieldId = id ?? (label ? autoId : undefined)
    const ajudaId = ajuda && fieldId ? `${fieldId}-ajuda` : undefined
    return (
      <div className="flex flex-col gap-1">
        <FieldLabel label={label} hint={hint} htmlFor={fieldId} />
        <input
          ref={ref}
          id={fieldId}
          aria-describedby={ajudaId}
          {...rest}
          className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
        />
        <FieldHelp ajuda={ajuda} id={ajudaId} />
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>
    )
  }
)

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  ajuda?: string
}

export function Select({ label, error, hint, ajuda, className = '', id, children, ...rest }: SelectProps) {
  const autoId = useId()
  const fieldId = id ?? (label ? autoId : undefined)
  const ajudaId = ajuda && fieldId ? `${fieldId}-ajuda` : undefined
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} hint={hint} htmlFor={fieldId} />
      <select
        id={fieldId}
        aria-describedby={ajudaId}
        {...rest}
        className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
      >
        {children}
      </select>
      <FieldHelp ajuda={ajuda} id={ajudaId} />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
    label?: string; error?: string; hint?: string; ajuda?: string
  }
>(function Textarea({ label, error, hint, ajuda, className = '', id, ...rest }, ref) {
  const autoId = useId()
  const fieldId = id ?? (label ? autoId : undefined)
  const ajudaId = ajuda && fieldId ? `${fieldId}-ajuda` : undefined
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} hint={hint} htmlFor={fieldId} />
      <textarea
        ref={ref}
        id={fieldId}
        aria-describedby={ajudaId}
        {...rest}
        className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y ${className}`}
      />
      <FieldHelp ajuda={ajuda} id={ajudaId} />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
})
