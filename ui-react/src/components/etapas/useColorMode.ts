// Hook compartilhado: mantém o `colorMode` do React Flow (claro/escuro) em
// sincronia com o tema do app, que alterna por classe em `html.dark`
// (ver `src/lib/theme.ts`). Um MutationObserver observa a classe e reaplica.
import { useEffect, useState } from 'react'
import type { ColorMode } from '@xyflow/react'

export function useColorMode(): ColorMode {
  const read = (): ColorMode =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  const [mode, setMode] = useState<ColorMode>(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setMode(read()))
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })
    return () => obs.disconnect()
  }, [])
  return mode
}
