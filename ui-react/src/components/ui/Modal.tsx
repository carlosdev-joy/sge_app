import React, { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
}

const SIZES = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl', xl: 'max-w-4xl', '2xl': 'max-w-6xl' }

// Pilha global dos modais abertos: com modais empilhados (ex.: detalhe →
// histórico na seção Caixa), o Esc deve fechar SÓ o do topo. Sem a pilha, o
// handler do modal de baixo (registrado primeiro) fecha ele, o flush síncrono
// do React no evento discreto re-subscreve o listener do modal do topo no
// meio do dispatch e o topo perde a vez — o Esc "pulava" o modal da frente.
const modalStack: symbol[] = []

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('modal')
  const panelRef = useRef<HTMLDivElement>(null)
  // onClose via ref: o listener não é re-subscrito quando o pai recria a
  // função inline — re-subscrever no meio de um dispatch perde o evento.
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })

  useEffect(() => {
    if (!open) return
    const id = idRef.current!
    modalStack.push(id)
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && modalStack[modalStack.length - 1] === id) onCloseRef.current()
    }
    document.addEventListener('keydown', handler)
    // Gestão de foco (o Radix da seção Caixa dava isso de graça — F7 da
    // migração): foca o painel ao abrir e devolve o foco ao fechar. O
    // sentinela de focusin cobre o que o trap de Tab por primeiro/último não
    // pega (ex.: radio group sr-only tem UM tab-stop no primeiro rádio — o
    // Tab sai dali sem nunca passar pelo "último focável").
    // Se um filho do modal já tem foco (input autoFocus: o react-dom foca no
    // commit, ANTES deste efeito), não roubar — e não "devolver" o foco ao
    // fechar, que capturaria o próprio input desmontado (Admin/Governança/
    // Pipelines usam autoFocus; achado da revisão da F7).
    const active = document.activeElement as HTMLElement | null
    const focoJaDentro = !!(panelRef.current && active && panelRef.current.contains(active))
    const previouslyFocused = focoJaDentro ? null : active
    if (!focoJaDentro) panelRef.current?.focus()
    const onFocusIn = (e: FocusEvent) => {
      if (modalStack[modalStack.length - 1] !== id) return // só o modal do topo prende
      const root = panelRef.current
      if (!root || !(e.target instanceof HTMLElement) || root.contains(e.target)) return
      // Overlays legítimos ACIMA do modal (ex.: CommandPalette via Ctrl+K)
      // se marcam com data-modal-exempt e ficam fora do trap.
      if (e.target.closest('[data-modal-exempt]')) return
      root.focus()
    }
    document.addEventListener('focusin', onFocusIn)
    return () => {
      const i = modalStack.indexOf(id)
      if (i >= 0) modalStack.splice(i, 1)
      document.removeEventListener('keydown', handler)
      document.removeEventListener('focusin', onFocusIn)
      previouslyFocused?.focus?.()
    }
  }, [open])

  if (!open) return null

  // Tab preso dentro do modal (ciclo primeiro↔último focável).
  const handleTabTrap = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab') return
    const root = panelRef.current
    if (!root) return
    const focusables = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (focusables.length === 0) { e.preventDefault(); return }
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const active = document.activeElement
    if (e.shiftKey && (active === first || active === root)) {
      e.preventDefault(); last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault(); first.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={handleTabTrap}
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
