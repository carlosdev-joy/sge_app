// Hook simples de media query (SPA client-only). Inicializa de forma síncrona
// para evitar flash no primeiro render e reage a mudanças de viewport.
import { useEffect, useState } from 'react'

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    try { return window.matchMedia(query).matches } catch { return false }
  })
  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    onChange()
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return matches
}
