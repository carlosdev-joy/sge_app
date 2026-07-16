// ── Sheet: gaveta lateral nativa do DS ───────────────────────────────────────
// Primitivo novo da F8 da migração Caixa (docs/spec-caixa-ds-nativo.md) —
// substitui o Sheet shadcn/Radix. Compartilha com o Modal a pilha de overlays,
// o Esc-no-topo e a gestão de foco (useOverlay/trapTabKey). NÃO mexe no
// overflow do body: o scroll da página nunca fica travado ao abrir/fechar
// (critério da fase); o conteúdo rola dentro do painel.
import React, { useRef } from 'react'
import { X } from 'lucide-react'
import { useOverlay, trapTabKey } from './overlay'

interface SheetProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  side?: 'right' | 'left'
  /** classe de largura máxima do painel (default max-w-2xl) */
  widthClass?: string
}

export function Sheet({ open, onClose, title, children, side = 'right', widthClass = 'max-w-2xl' }: SheetProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  useOverlay(open, onClose, panelRef)

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={(e) => trapTabKey(e, panelRef.current)}
        className={`absolute top-0 ${side === 'right' ? 'right-0' : 'left-0'} h-full w-full ${widthClass} bg-panel ${
          side === 'right' ? 'border-l' : 'border-r'
        } border-edge shadow-2xl flex flex-col focus:outline-none animate-[sheetIn_0.25s_ease-out]`}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-edge shrink-0">
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            <button onClick={onClose} aria-label="Fechar" className="text-dim hover:text-ink transition-colors">
              <X size={18} />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">{children}</div>
      </div>
      <style>{`
        @keyframes sheetIn {
          from { transform: translateX(${side === 'right' ? '24px' : '-24px'}); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
