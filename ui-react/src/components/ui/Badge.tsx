import React from 'react'

const MAP: Record<string, string> = {
  SUCCESS:  'bg-success-surface text-success border border-success/40',
  FAILED:   'bg-error-surface text-error border border-error/40',
  WARNING:  'bg-warning-surface text-warning border border-warning/40',
  RUNNING:  'bg-info-surface text-info border border-info/40',
  SKIPPED:  'bg-canvas text-dim border border-control-border',
  GERADA:   'bg-warning-surface text-warning border border-warning/40',
  TIMEOUT:  'bg-error-surface text-error border border-error/40',
  ERRO:     'bg-error-surface text-error border border-error/40',
  PENDING:  'bg-canvas text-dim border border-control-border',
  success:  'bg-success-surface text-success border border-success/40',
  error:    'bg-error-surface text-error border border-error/40',
  warning:  'bg-warning-surface text-warning border border-warning/40',
  info:     'bg-info-surface text-info border border-info/40',
  neutral:  'bg-canvas text-dim border border-control-border',
  alta:     'bg-error-surface text-error border border-error/40',
  media:    'bg-warning-surface text-warning border border-warning/40',
  baixa:    'bg-success-surface text-success border border-success/40',
  ALTA:     'bg-error-surface text-error border border-error/40',
  MEDIA:    'bg-warning-surface text-warning border border-warning/40',
  BAIXA:    'bg-success-surface text-success border border-success/40',
  ativo:    'bg-success-surface text-success border border-success/40',
  inativo:  'bg-canvas text-dim border border-control-border',
  admin:    'bg-purple-100 text-purple-700 border border-purple-300 dark:bg-purple-900/50 dark:text-purple-400 dark:border-purple-800',
  operador: 'bg-info-surface text-info border border-info/40',
  consulta: 'bg-canvas text-dim border border-control-border',
  sim:      'bg-success-surface text-success border border-success/40',
  não:      'bg-canvas text-dim border border-control-border',
}

export function Badge({ value, children }: { value?: string; children?: React.ReactNode }) {
  const key = value ?? String(children)
  const cls = MAP[key] ?? 'bg-canvas text-dim border border-control-border'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium max-w-full [overflow-wrap:anywhere] ${cls}`}>
      {children ?? value}
    </span>
  )
}
