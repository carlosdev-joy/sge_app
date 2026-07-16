// ── Skeleton: placeholder pulsante de carregamento ───────────────────────────
// bg-ink/10 acompanha o tema (ink escuro no claro, claro no escuro), então o
// mesmo componente funciona nas duas variantes sem ajuste por contexto.
import React from 'react'

export function Skeleton({ className = '', ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={`animate-pulse rounded-md bg-ink/10 ${className}`} />
}
