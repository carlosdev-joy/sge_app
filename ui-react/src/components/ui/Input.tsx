import React from 'react'
import { Hint } from './Hint'

// Label do campo com "?" de ajuda contextual opcional (prop `hint`).
// Sem hint renderiza o <label> puro — layout idêntico ao original.
function FieldLabel({ label, hint }: { label?: string; hint?: string }) {
  if (!label) return null
  if (!hint) return <label className="text-xs text-dim font-medium">{label}</label>
  return (
    <span className="flex items-center gap-1">
      <label className="text-xs text-dim font-medium">{label}</label>
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
  function Input({ label, error, hint, className = '', ...rest }, ref) {
    return (
      <div className="flex flex-col gap-1">
        <FieldLabel label={label} hint={hint} />
        <input
          ref={ref}
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

export function Select({ label, error, hint, className = '', children, ...rest }: SelectProps) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} hint={hint} />
      <select
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
>(function Textarea({ label, error, hint, className = '', ...rest }, ref) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} hint={hint} />
      <textarea
        ref={ref}
        {...rest}
        className={`bg-panel border ${error ? 'border-red-500' : 'border-edge'} text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y ${className}`}
      />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
})
