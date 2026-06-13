import React from 'react'

interface CardProps {
  title?: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}

export function Card({ title, children, className = '', action }: CardProps) {
  return (
    <div className={`bg-[#1a1d27] border border-[#2a2d3a] rounded-lg ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a2d3a]">
          <h3 className="text-sm font-semibold text-[#e2e8f0]">{title}</h3>
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
    <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-col gap-1">
      <span className="text-xs text-[#94a3b8] font-medium uppercase tracking-wide">{label}</span>
      <span className={`text-3xl font-bold ${colors[color] ?? 'text-[#e2e8f0]'}`}>{value}</span>
      {sub && <span className="text-xs text-[#94a3b8]">{sub}</span>}
    </div>
  )
}
