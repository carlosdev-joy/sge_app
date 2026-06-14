import React from 'react'

interface CardProps {
  title?: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}

export function Card({ title, children, className = '', action }: CardProps) {
  return (
    <div className={`bg-panel border border-edge rounded-lg ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-edge">
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}

export function KpiCard({ label, value, sub, color = 'blue' }: { label: string; value: string | number; sub?: string; color?: string }) {
  const colors: Record<string, string> = {
    blue:   'text-blue-400',
    green:  'text-green-400',
    red:    'text-red-400',
    yellow: 'text-yellow-400',
    purple: 'text-purple-400',
  }
  return (
    <div className="bg-panel border border-edge rounded-lg p-4 flex flex-col gap-1 min-w-0">
      <span className="text-xs text-dim font-medium uppercase tracking-wide truncate">{label}</span>
      <span className={`text-3xl font-bold leading-tight break-words ${colors[color] ?? 'text-ink'}`}>{value}</span>
      {sub && <span className="text-xs text-dim break-words">{sub}</span>}
    </div>
  )
}
