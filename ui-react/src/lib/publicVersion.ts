import { useQuery } from '@tanstack/react-query'
import { BASE } from './api'

/** Fonte pública mínima; não carrega histórico, autores nem configuração. */
export function usePublicVersion(): string | null {
  const { data } = useQuery({
    queryKey: ['versao-publica'], staleTime: 300_000, retry: false,
    queryFn: async ({ signal }) => {
      try {
        const res = await fetch(`${BASE}/versao/publica`, { signal, credentials: 'omit' })
        if (!res.ok) return null
        const body = await res.json()
        return typeof body?.versao === 'string' && /^\d{1,6}(?:\.\d{1,6}){1,3}$/.test(body.versao) ? body.versao : null
      } catch { return null }
    },
  })
  return data ?? null
}
