import React from 'react'


const MAP: Record<string, string> = {
  SUCCESS:  'bg-green-900/50 text-green-400 border border-green-800',
  FAILED:   'bg-red-900/50 text-red-400 border border-red-800',
  WARNING:  'bg-yellow-900/50 text-yellow-400 border border-yellow-800',
  RUNNING:  'bg-blue-900/50 text-blue-400 border border-blue-800',
  PENDING:  'bg-gray-800 text-gray-400 border border-gray-700',
  success:  'bg-green-900/50 text-green-400 border border-green-800',
  error:    'bg-red-900/50 text-red-400 border border-red-800',
  warning:  'bg-yellow-900/50 text-yellow-400 border border-yellow-800',
  info:     'bg-blue-900/50 text-blue-400 border border-blue-800',
  neutral:  'bg-gray-800 text-gray-400 border border-gray-700',
  alta:     'bg-red-900/50 text-red-400 border border-red-800',
  media:    'bg-yellow-900/50 text-yellow-400 border border-yellow-800',
  baixa:    'bg-green-900/50 text-green-400 border border-green-800',
  ALTA:     'bg-red-900/50 text-red-400 border border-red-800',
  MEDIA:    'bg-yellow-900/50 text-yellow-400 border border-yellow-800',
  BAIXA:    'bg-green-900/50 text-green-400 border border-green-800',
  ativo:    'bg-green-900/50 text-green-400 border border-green-800',
  inativo:  'bg-gray-800 text-gray-400 border border-gray-700',
}

export function Badge({ value, children }: { value?: string; children?: React.ReactNode }) {
  const key = value ?? String(children)
  const cls = MAP[key] ?? 'bg-gray-800 text-gray-400 border border-gray-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {children ?? value}
    </span>
  )
}
