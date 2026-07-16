// ── Table: tabela nativa do DS ───────────────────────────────────────────────
// Compound components no mesmo shape do shadcn/table (facilita o porte da
// seção Caixa Seguro), estilizados com os tokens semânticos do Orquestra —
// mesmo visual das tabelas cruas de Logs/Governança (thead text-xs text-dim
// bg-canvas, bordas edge). O wrapper rola horizontal; a página nunca rola.
// GOTCHA: o wrapper overflow-x-auto vira scroll-container nos DOIS eixos —
// thead sticky não gruda no scroll da página e overlays absolutos dentro de
// célula (Hint, menus) são clipados por ele.
import React from 'react'

export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  /** Compacta o padding vertical das células (listas densas tipo Logs). */
  dense?: boolean
}

export function Table({ dense = false, className = '', ...rest }: TableProps) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table
        {...rest}
        className={`w-full caption-bottom text-sm ${dense ? '[&_td]:py-1 [&_th]:py-1' : ''} ${className}`}
      />
    </div>
  )
}

export function TableHeader({ className = '', ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      {...rest}
      className={`text-xs text-dim [&_tr]:border-b [&_tr]:border-edge [&_tr]:bg-canvas [&_tr:hover]:bg-canvas ${className}`}
    />
  )
}

export function TableBody({ className = '', ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...rest} className={`[&_tr:last-child]:border-0 ${className}`} />
}

export function TableFooter({ className = '', ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tfoot
      {...rest}
      className={`border-t border-edge bg-canvas font-medium text-ink ${className}`}
    />
  )
}

export function TableRow({ className = '', ...rest }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      {...rest}
      className={`border-b border-edge transition-colors hover:bg-canvas/60 ${className}`}
    />
  )
}

export function TableHead({ className = '', ...rest }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      {...rest}
      className={`px-4 py-2 text-left align-middle font-medium ${className}`}
    />
  )
}

export function TableCell({ className = '', ...rest }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td {...rest} className={`px-4 py-2 align-middle text-ink ${className}`} />
}

// Célula de ações por linha: encolhe à largura do conteúdo (w-px +
// whitespace-nowrap) e alinha os botões à direita.
export function TableActionCell({ className = '', ...rest }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td {...rest} className={`w-px whitespace-nowrap px-4 py-2 text-right align-middle ${className}`} />
}

export function TableCaption({ className = '', ...rest }: React.HTMLAttributes<HTMLTableCaptionElement>) {
  return <caption {...rest} className={`mt-2 text-xs text-dim ${className}`} />
}
