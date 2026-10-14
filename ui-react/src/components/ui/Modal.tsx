import React, { useContext, useRef } from 'react'
import { X } from 'lucide-react'
import { OverlayScope, useOverlay, trapTabKey } from './overlay'

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
  // Dentro de uma área oculta (OverlayScope) o modal fica montado e inerte:
  // mesma árvore, conteúdo preservado, fora da pilha e sem role de diálogo.
  const active = useContext(OverlayScope)
  // Pilha de overlays + Esc no topo + gestão de foco (ver ui/overlay.ts).
  useOverlay(open && active, onClose, panelRef)

  if (!open) return null

  return (
    // ⚠️ `nokey` é a marca do React Flow (@xyflow: `target.closest('.nokey')`
    // em `isInputDOMNode`): sem ela, uma tecla digitada DENTRO de um modal
    // aberto sobre o canvas de Etapas continua chegando aos atalhos do grafo,
    // porque o listener do React Flow é de `document` e o foco do overlay cai
    // num `div tabIndex={-1}` — que não é campo de texto. O caso que apareceu:
    // Backspace no navegador de pastas do anexo (onde a própria tela ensina
    // "Subir um nível (Backspace)") disparava o `deleteKeyCode` e abria
    // "Excluir nó" por cima. Vale para todo modal, não só aquele.
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 nokey" style={active ? undefined : { display: 'none' }}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={panelRef}
        role={active ? 'dialog' : undefined}
        aria-modal={active ? 'true' : undefined}
        aria-label={title}
        tabIndex={-1}
        onKeyDown={(e) => trapTabKey(e, panelRef.current)}
        className={`relative w-full ${SIZES[size]} ui-overlay-panel bg-panel border border-edge rounded-xl shadow-2xl flex flex-col max-h-[90vh] focus:outline-none`}
      >
        {title && (
          <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-edge">
            <h2 className="ui-section-title min-w-0 text-ink">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Fechar" className="ui-button ui-button-small ui-icon-button shrink-0 rounded text-dim hover:text-ink transition-colors">
              <X size={18} />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">{children}</div>
      </div>
    </div>
  )
}
