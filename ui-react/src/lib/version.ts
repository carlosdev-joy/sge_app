import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './api'

// Versão de fallback caso ainda não haja registros em /versao.
const FALLBACK_VERSION = '1.0'

interface VersaoEntry { versao: string }

// Compara duas versões "a.b.c" numericamente. Retorna >0 se a > b.
function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map(n => parseInt(n, 10) || 0)
  const pb = b.split('.').map(n => parseInt(n, 10) || 0)
  const len = Math.max(pa.length, pb.length)
  for (let i = 0; i < len; i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (diff !== 0) return diff
  }
  return 0
}

// Maior versão registrada — fonte única para header e dropdown.
// Evita divergência entre o "v2.1" hardcoded e o changelog (que mostrava 2.2).
export function useAppVersion(): string {
  const { data } = useQuery<{ data: VersaoEntry[] }>({
    queryKey: ['versao'],
    queryFn: () => apiFetch('/versao'),
    staleTime: 300_000,
  })
  const list = data?.data ?? []
  if (list.length === 0) return FALLBACK_VERSION
  return list.reduce((max, v) =>
    compareVersions(v.versao, max) > 0 ? v.versao : max, list[0].versao)
}
