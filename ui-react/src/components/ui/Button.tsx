import React from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary:   'bg-blue-600 hover:bg-blue-500 text-white',
  secondary: 'bg-[#2a2d3a] hover:bg-[#343748] text-[#e2e8f0] border border-[#2a2d3a]',
  danger:    'bg-red-700 hover:bg-red-600 text-white',
  ghost:     'hover:bg-[#1a1d27] text-[#94a3b8] hover:text-[#e2e8f0]',
}
const SIZES: Record<Size, string> = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-1.5 text-sm',
  lg: 'px-5 py-2.5 text-base',
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
      disabled={disabled || loading}
      className={`inline-flex items-center gap-1.5 rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {loading && <span className="animate-spin text-xs">⟳</span>}
      {children}
    </button>
  )
}
