// A aba do navegador está visível? Consulta periódica fica suspensa quando não
// está; ao voltar, a tela revalida (refetch on focus do React Query).
import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  document.addEventListener('visibilitychange', onChange)
  return () => document.removeEventListener('visibilitychange', onChange)
}
const visible = () => typeof document === 'undefined' || document.visibilityState !== 'hidden'

export function usePageVisible(): boolean {
  return useSyncExternalStore(subscribe, visible, () => true)
}
