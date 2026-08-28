// Cartão de indicador — o número grande com rótulo, cor e ícone.
//
// Vivia dentro de `pages/Dashboard.tsx`. Saiu de lá quando a aba Dashboard dos
// chamados precisou do MESMO cartão: duas cópias divergiriam no primeiro
// ajuste de espaçamento, e a tela do lado ficaria "quase igual" — que é pior
// que diferente, porque ninguém percebe.
//
// A paleta é fechada de propósito: cor fora do mapa cairia em `undefined` na
// classe e o cartão perderia o fundo, sem erro nenhum.
import type React from 'react'

export interface KpiProps {
  label: string
  value: React.ReactNode
  sub?: string
  icon: React.ReactNode
  color: 'blue' | 'green' | 'red' | 'yellow' | 'purple' | 'slate'
  onClick?: () => void
  pulse?: boolean
}

export function KpiCard({ label, value, sub, icon, color, onClick, pulse }: KpiProps) {
  const bg: Record<string, string> = {
    blue:   'from-blue-500/10   to-blue-500/5   border-blue-500/20',
    green:  'from-green-500/10  to-green-500/5  border-green-500/20',
    red:    'from-red-500/10    to-red-500/5    border-red-500/20',
    yellow: 'from-amber-500/10  to-amber-500/5  border-amber-500/20',
    purple: 'from-purple-500/10 to-purple-500/5 border-purple-500/20',
    slate:  'from-slate-500/10  to-slate-500/5  border-slate-500/20',
  }
  const txt: Record<string, string> = {
    blue: 'text-blue-500 dark:text-blue-400', green: 'text-green-500 dark:text-green-400',
    red: 'text-red-500 dark:text-red-400', yellow: 'text-amber-500 dark:text-amber-400',
    purple: 'text-purple-500 dark:text-purple-400', slate: 'text-slate-500 dark:text-slate-400',
  }
  return (
    <div
      onClick={onClick}
      className={`bg-gradient-to-br ${bg[color]} border rounded-xl p-3.5 flex flex-col gap-1.5 ${onClick ? 'cursor-pointer hover:brightness-110 transition-all' : ''} ${pulse ? 'animate-pulse' : ''}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-dim uppercase tracking-wider">{label}</span>
        <span className={`${txt[color]} opacity-70`}>{icon}</span>
      </div>
      <div className={`text-2xl font-bold ${txt[color]}`}>{value}</div>
      {sub && <div className="text-[10px] text-dim">{sub}</div>}
    </div>
  )
}
