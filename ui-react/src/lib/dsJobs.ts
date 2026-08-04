// ── Conferência do nome do job contra o DataStage ────────────────────────────
// Incidente 2026-08-01: a etapa foi cadastrada como 'SsdVidaCobranca01…' e o job
// no DataStage chama-se 'SSDVidaCobranca01…'. O DataStage DIFERENCIA maiúsculas
// de minúsculas nos nomes de job; o SQL Server (colação padrão) NÃO. Resultado:
// o cadastro passou liso e a divergência só apareceu em produção, no traceback
// ("Cannot find job … Status code = -1004").
//
// Aqui a conferência acontece no CADASTRO: o backend (`GET /datastage/jobs`)
// devolve a lista real de jobs do projeto (cacheada por projeto, TTL 300s) e o
// veredito é calculado LOCALMENTE — sem uma ida ao servidor por tecla digitada,
// o que também alimenta o autocompletar.
//
// REGRA INEGOCIÁVEL: DataStage fora do ar NÃO bloqueia o cadastro. O endpoint
// responde 200 com `disponivel=false` e a UI mostra "não foi possível conferir
// agora" — visivelmente diferente de "conferido e OK". Nunca é erro, nunca trava.
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './api'
import type { Pipeline } from '../types/pipeline'

export interface DsJobsResp {
  project: string
  disponivel: boolean
  jobs: string[]
  total: number
  cached: boolean
  verificado_em: number
  motivo: string | null
}

// 'exato'         — o nome bate letra a letra com um job do projeto
// 'caixa'         — bate ignorando maiúsculas/minúsculas, MAS não é idêntico
//                   (é EXATAMENTE o caso do incidente — o mais importante)
// 'ausente'       — não existe job com esse nome no projeto
// 'indisponivel'  — não deu para conferir agora (aviso honesto, nunca erro)
// 'vazio'         — ainda não há nome digitado
export type ConferenciaStatus = 'exato' | 'caixa' | 'ausente' | 'indisponivel' | 'vazio'

export interface ConferenciaDs {
  status: ConferenciaStatus
  /** Grafia OFICIAL do DataStage — preenchida quando status === 'caixa'. */
  sugestao: string | null
  /** Candidatos acionáveis quando status === 'ausente'. */
  parecidos: string[]
  /** Motivo da indisponibilidade (só quando status === 'indisponivel'). */
  motivo: string | null
}

/** Tamanho do PREFIXO COMUM entre dois nomes já em minúsculas. */
function prefixoComum(a: string, b: string): number {
  const n = Math.min(a.length, b.length)
  let i = 0
  while (i < n && a[i] === b[i]) i++
  return i
}

/**
 * Veredito do nome contra a lista real de jobs do projeto.
 *
 * Ordem dos parecidos (status 'ausente'): maior PREFIXO COMUM primeiro, depois
 * os que contêm/estão contidos — tudo sem caixa. O caso "só a caixa difere"
 * nunca cai aqui: vira 'caixa'.
 *
 * ⚠️ Por que prefixo comum e não `startsWith`: o erro real de digitação quase
 * nunca deixa um nome como prefixo do outro. Na prova visual,
 * 'SSDVidaCobranca09Inexistente' × 'SSDVidaCobranca01…' não casava por
 * `startsWith` nem por substring — a faixa 'ausente' saía SEM sugestão nenhuma,
 * que é justamente o que ela existe para dar.
 */
export function conferirNomeDs(
  nome: string,
  resp: DsJobsResp | undefined,
  limiteParecidos = 6,
): ConferenciaDs {
  const alvo = (nome || '').trim()
  const vazio: ConferenciaDs = { status: 'vazio', sugestao: null, parecidos: [], motivo: null }
  if (!alvo) return vazio
  if (!resp || !resp.disponivel) {
    return {
      status: 'indisponivel',
      sugestao: null,
      parecidos: [],
      motivo: resp?.motivo ?? null,
    }
  }
  if (resp.jobs.includes(alvo)) {
    return { status: 'exato', sugestao: null, parecidos: [], motivo: null }
  }
  const alvoCf = alvo.toLowerCase()
  const mesmaCaixa = resp.jobs.find(j => j.toLowerCase() === alvoCf)
  if (mesmaCaixa) {
    return { status: 'caixa', sugestao: mesmaCaixa, parecidos: [], motivo: null }
  }
  const minPrefixo = Math.min(4, alvoCf.length)
  const porPrefixo: { nome: string; n: number }[] = []
  const contidos: string[] = []
  for (const j of resp.jobs) {
    const jCf = j.toLowerCase()
    const n = prefixoComum(jCf, alvoCf)
    if (n >= minPrefixo) porPrefixo.push({ nome: j, n })
    else if (jCf.includes(alvoCf) || alvoCf.includes(jCf)) contidos.push(j)
  }
  porPrefixo.sort((a, b) => b.n - a.n)
  return {
    status: 'ausente',
    sugestao: null,
    parecidos: [...porPrefixo.map(x => x.nome), ...contidos].slice(0, limiteParecidos),
    motivo: null,
  }
}

/** Sugestões do autocompletar — filtro LOCAL sobre a lista já carregada. */
export function sugestoesDs(q: string, resp: DsJobsResp | undefined, limite = 20): string[] {
  if (!resp?.disponivel) return []
  const termo = (q || '').trim().toLowerCase()
  if (!termo) return resp.jobs.slice(0, limite)
  const prefixo = resp.jobs.filter(j => j.toLowerCase().startsWith(termo))
  const resto = resp.jobs.filter(j => !j.toLowerCase().startsWith(termo) && j.toLowerCase().includes(termo))
  return [...prefixo, ...resto].slice(0, limite)
}

/**
 * Lista de jobs do projeto. UMA ida ao servidor por projeto (o backend ainda
 * cacheia por 5 min do lado dele — a chamada é SSH). `retry: false` porque a
 * indisponibilidade já vem como 200 + `disponivel:false`: repetir não ajuda.
 */
export function useDsJobs(project: string | null | undefined, enabled = true) {
  return useQuery<DsJobsResp>({
    queryKey: ['ds-jobs', project],
    queryFn: () => apiFetch(`/datastage/jobs?project=${encodeURIComponent(project!)}`),
    enabled: !!project && enabled,
    staleTime: 300_000,
    retry: false,
  })
}

/**
 * Projeto DataStage do pipeline. MESMO endpoint/queryKey do painel de pipeline
 * (`PainelPipeline`) e da biblioteca de Fluxos — o cache do TanStack costuma já
 * ter a resposta. `filter_name` é LIKE, então resolvemos o registro EXATO (com
 * fallback sem caixa, que é como a base guarda).
 */
export function usePipelineProject(pipeline: string | null | undefined) {
  const { data } = useQuery<{ data: Pipeline[]; total: number }>({
    queryKey: ['fluxos-biblioteca', pipeline],
    queryFn: () => apiFetch(`/pipelines?limit=30&filter_name=${encodeURIComponent(pipeline!)}`),
    enabled: !!pipeline,
    staleTime: 300_000,
  })
  const meta =
    data?.data.find(p => p.pipeline_name === pipeline)
    ?? data?.data.find(p => p.pipeline_name.toLowerCase() === (pipeline || '').toLowerCase())
    ?? null
  return meta?.project_name || null
}
