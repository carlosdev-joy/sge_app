import React from 'react'

const MAP: Record<string, string> = {
  SUCCESS:  'bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  FAILED:   'bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  WARNING:  'bg-amber-100 text-amber-700 border border-amber-300 dark:bg-yellow-900/50 dark:text-yellow-400 dark:border-yellow-800',
  RUNNING:  'bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/50 dark:text-blue-400 dark:border-blue-800',
  PENDING:  'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
  success:  'bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  error:    'bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  warning:  'bg-amber-100 text-amber-700 border border-amber-300 dark:bg-yellow-900/50 dark:text-yellow-400 dark:border-yellow-800',
  info:     'bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/50 dark:text-blue-400 dark:border-blue-800',
  neutral:  'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
  alta:     'bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  media:    'bg-amber-100 text-amber-700 border border-amber-300 dark:bg-yellow-900/50 dark:text-yellow-400 dark:border-yellow-800',
  baixa:    'bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  ALTA:     'bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  MEDIA:    'bg-amber-100 text-amber-700 border border-amber-300 dark:bg-yellow-900/50 dark:text-yellow-400 dark:border-yellow-800',
  BAIXA:    'bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  ativo:    'bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  inativo:  'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
  admin:    'bg-purple-100 text-purple-700 border border-purple-300 dark:bg-purple-900/50 dark:text-purple-400 dark:border-purple-800',
  operador: 'bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/50 dark:text-blue-400 dark:border-blue-800',
  consulta: 'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
  sim:      'bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  não:      'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
}

export function Badge({ value, children }: { value?: string; children?: React.ReactNode }) {
  const key = value ?? String(children)
  const cls = MAP[key] ?? 'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${cls}`}>
      {children ?? value}
    </span>
  )
}
