import React from 'react'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function Input({ label, error, className = '', ...rest }: InputProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-xs text-[#94a3b8] font-medium">{label}</label>}
      <input
        {...rest}
        className={`bg-[#1a1d27] border ${error ? 'border-red-500' : 'border-[#2a2d3a]'} text-[#e2e8f0] rounded-md px-3 py-1.5 text-sm placeholder-[#94a3b8] focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
      />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
}

export function Select({ label, error, className = '', children, ...rest }: SelectProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-xs text-[#94a3b8] font-medium">{label}</label>}
      <select
        {...rest}
        className={`bg-[#1a1d27] border ${error ? 'border-red-500' : 'border-[#2a2d3a]'} text-[#e2e8f0] rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
      >
        {children}
      </select>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}

export function Textarea({ label, error, className = '', ...rest }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; error?: string }) {
  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-xs text-[#94a3b8] font-medium">{label}</label>}
      <textarea
        {...rest}
        className={`bg-[#1a1d27] border ${error ? 'border-red-500' : 'border-[#2a2d3a]'} text-[#e2e8f0] rounded-md px-3 py-1.5 text-sm placeholder-[#94a3b8] focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y ${className}`}
      />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}
