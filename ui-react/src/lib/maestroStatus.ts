// Visibilidade do Maestro decidida pelo backend (GET /maestro/status: o
// interruptor do Admin E o provedor de IA com chave). Enquanto a resposta não
// chega — ou em erro, ou sem a migration 110 — o avatar fica oculto: a tela
// nunca promete um assistente que não vai responder.
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './api'
import type { MaestroStatus } from './maestro'

const OCULTO: MaestroStatus = { enabled: false, sugestoes: [] }

export function useMaestroStatus(ativo: boolean): MaestroStatus {
  const { data } = useQuery<MaestroStatus>({
    queryKey: ['maestro-status'],
    queryFn: () => apiFetch('/maestro/status'),
    enabled: ativo,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
  if (!ativo || !data?.enabled) return OCULTO
  return { enabled: true, sugestoes: Array.isArray(data.sugestoes) ? data.sugestoes : [] }
}
