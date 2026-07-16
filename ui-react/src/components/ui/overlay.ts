// Comportamento compartilhado dos overlays do DS (Modal e Sheet): pilha
// global, Esc só no topo e gestão de foco. Vive em arquivo próprio (sem
// componentes) para o fast refresh do Vite não reclamar dos exports mistos.
import React, { useEffect, useRef } from 'react'

// Pilha global dos overlays abertos: com camadas empilhadas (ex.: detalhe →
// histórico na seção Caixa), o Esc deve fechar SÓ o do topo. Sem a pilha, o
// handler do overlay de baixo (registrado primeiro) fecha ele, o flush
// síncrono do React no evento discreto re-subscreve o listener do topo no
// meio do dispatch e o topo perde a vez — o Esc "pulava" a camada da frente.
const overlayStack: symbol[] = []

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Pilha + Esc no topo + gestão de foco (o Radix da seção Caixa dava isso de
// graça — F7/F8 da migração): foca o painel ao abrir e devolve o foco ao
// fechar. O sentinela de focusin cobre o que o trap de Tab por
// primeiro/último não pega (ex.: radio group sr-only tem UM tab-stop no
// primeiro rádio — o Tab sai dali sem nunca passar pelo "último focável").
export function useOverlay(open: boolean, onClose: () => void, panelRef: React.RefObject<HTMLDivElement | null>) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('overlay')
  // onClose via ref: o listener não é re-subscrito quando o pai recria a
  // função inline — re-subscrever no meio de um dispatch perde o evento.
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })

  useEffect(() => {
    if (!open) return
    const id = idRef.current!
    overlayStack.push(id)
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && overlayStack[overlayStack.length - 1] === id) onCloseRef.current()
    }
    document.addEventListener('keydown', handler)
    // Se um filho do overlay já tem foco (input autoFocus: o react-dom foca
    // no commit, ANTES deste efeito), não roubar — e não "devolver" o foco ao
    // fechar, que capturaria o próprio input desmontado (Admin/Governança/
    // Pipelines usam autoFocus).
    const active = document.activeElement as HTMLElement | null
    const focoJaDentro = !!(panelRef.current && active && panelRef.current.contains(active))
    const previouslyFocused = focoJaDentro ? null : active
    if (!focoJaDentro) panelRef.current?.focus()
    const onFocusIn = (e: FocusEvent) => {
      if (overlayStack[overlayStack.length - 1] !== id) return // só o topo prende
      const root = panelRef.current
      if (!root || !(e.target instanceof HTMLElement) || root.contains(e.target)) return
      // Overlays legítimos ACIMA (ex.: CommandPalette via Ctrl+K) se marcam
      // com data-modal-exempt e ficam fora do trap.
      if (e.target.closest('[data-modal-exempt]')) return
      root.focus()
    }
    document.addEventListener('focusin', onFocusIn)
    return () => {
      const i = overlayStack.indexOf(id)
      if (i >= 0) overlayStack.splice(i, 1)
      document.removeEventListener('keydown', handler)
      document.removeEventListener('focusin', onFocusIn)
      previouslyFocused?.focus?.()
    }
  }, [open, panelRef])
}

// Tab preso dentro do overlay (ciclo primeiro↔último focável).
export function trapTabKey(e: React.KeyboardEvent, root: HTMLDivElement | null) {
  if (e.key !== 'Tab' || !root) return
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
