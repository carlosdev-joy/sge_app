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

export function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('modal')
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
    return () => {
      const i = modalStack.indexOf(id)
      if (i >= 0) modalStack.splice(i, 1)
      document.removeEventListener('keydown', handler)
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className={`relative w-full ${SIZES[size]} bg-panel border border-edge rounded-xl shadow-2xl flex flex-col max-h-[90vh]`}>
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-edge">
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            <button onClick={onClose} className="text-dim hover:text-white transition-colors">
              <X size={18} />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">{children}</div>
      </div>
    </div>
  )
}
