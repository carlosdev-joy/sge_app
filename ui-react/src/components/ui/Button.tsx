import React from 'react'
import { Loader2 } from 'lucide-react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary:   'bg-primary-control hover:bg-primary-control-strong text-on-action',
  secondary: 'bg-panel hover:bg-canvas text-ink border border-control-border',
  danger:    'bg-red-600 hover:bg-red-700 text-white shadow-sm',
  ghost:     'hover:bg-edge/40 text-dim hover:text-ink',
}
const SIZES: Record<Size, string> = {
  sm: 'ui-button-small px-2.5 py-1',
  md: 'px-3.5 py-1.5',
  lg: 'ui-button-large px-5 py-2.5',
}

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

export function Button({ variant = 'primary', size = 'md', loading, className = '', children, disabled, ...rest }: Props) {
  return (
    <button
      {...rest}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={`ui-button inline-flex items-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {loading && <Loader2 size={16} aria-hidden className="ui-spinner animate-spin shrink-0" />}
      {children}
    </button>
  )
}
