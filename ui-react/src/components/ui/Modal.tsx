import React, { useRef } from 'react'
import { X } from 'lucide-react'
import { useOverlay, trapTabKey } from './overlay'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
}

const SIZES = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl', xl: 'max-w-4xl', '2xl': 'max-w-6xl' }

export function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  // Pilha de overlays + Esc no topo + gestão de foco (ver ui/overlay.ts).
  useOverlay(open, onClose, panelRef)

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={(e) => trapTabKey(e, panelRef.current)}
        className={`relative w-full ${SIZES[size]} bg-panel border border-edge rounded-xl shadow-2xl flex flex-col max-h-[90vh] focus:outline-none`}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-edge">
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            <button onClick={onClose} aria-label="Fechar" className="text-dim hover:text-white transition-colors">
              <X size={18} />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">{children}</div>
      </div>
    </div>
  )
}
