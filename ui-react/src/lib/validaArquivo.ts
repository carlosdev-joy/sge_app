import type { Edge, Node } from '@xyflow/react'

export interface EntradaArquivo {
  caminho_resolvido?: string
  entrada_id: string; ordem: number; tipo: 'arquivo' | 'dataset'; arquivo: string
  diretorio_literal: string; param_name: string | null; alvo: string
  se_nao_existe: 'pular' | 'falhar'; se_zero_linhas: 'pular' | 'falhar' | 'executar'
  ignorar_cabecalho: boolean
}
export interface ValidaConfig {
  revisao: number; ssh_conn_id: string; timeout_segundos: number; entradas: EntradaArquivo[]
}
export const novaEntrada = (): EntradaArquivo => ({ entrada_id: crypto.randomUUID(), ordem: 0,
  tipo: 'arquivo', arquivo: '', diretorio_literal: '', param_name: null, alvo: '',
  se_nao_existe: 'falhar', se_zero_linhas: 'falhar', ignorar_cabecalho: false })
export const novaValidacao = (): ValidaConfig => ({ revisao: 0, ssh_conn_id: '', timeout_segundos: 60, entradas: [novaEntrada()] })
export const ordenarEntradas = (entradas: EntradaArquivo[]) => entradas.map((e, ordem) => ({ ...e, ordem }))
export function renomearAlvo(n: Node, antigo: string, novo: string): Node {
  if (n.type !== 'valida_arquivo') return n
  const cfg = n.data.valida_arquivo as ValidaConfig
  return { ...n, data: { ...n.data, valida_arquivo: { ...cfg,
    entradas: cfg.entradas.map(e => e.alvo === antigo ? { ...e, alvo: novo } : e) } } }
}
// Todas as arestas, inclusive ramos de decisão, participam da prévia estática.
export function grafoValidacao(nodes: Node[], edges: Edge[]) {
  return nodes.map(n => ({ job_name: n.id,
    job_type: n.type === 'etapa' ? String(n.data.type) : n.type,
    depends_on_jobs: edges.filter(e => e.target === n.id).map(e => e.source) }))
}
export const decisaoLabel: Record<string, string> = {
  liberar: 'Liberado para executar', pular: 'Pular destino', bloquear: 'Bloquear destinos',
}
export const conclusaoLabel: Record<string, string> = {
  SEM_MOVIMENTO: 'Concluído sem movimento', COM_MOVIMENTO: 'Concluído com movimento',
  SEM_EXECUCAO: 'Concluído sem execução dos destinos', FALHA: 'Falha na execução',
}

// Somente valores/políticas do validador são lidos no início de cada corrida.
// O restante continua seguindo a publicação já exigida pelo editor.
export function exigePublicacaoValida(antes: Node[], depois: Node[], edgesAntes: Edge[], edgesDepois: Edge[]) {
  function ordenar(v: unknown): unknown {
    if (Array.isArray(v)) return v.map(ordenar)
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => [k, ordenar(x)]))
    return v
  }
  function assinatura(nodes: Node[], edges: Edge[]) {
    return JSON.stringify(ordenar({ nodes: nodes.map(n => {
      const data = { ...n.data }; delete data.isNew
      if (n.type === 'valida_arquivo') {
        const cfg = data.valida_arquivo as ValidaConfig
        data.valida_arquivo = { ssh_conn_id: cfg.ssh_conn_id,
          entradas: cfg.entradas.map(e => [e.entrada_id, e.alvo]).sort(([a], [b]) => a.localeCompare(b)) }
      }
      return { id: n.id, type: n.type, position: n.position, data }
    }).sort((a, b) => a.id.localeCompare(b.id)), edges: edges.map(e => [e.source, e.target, e.sourceHandle ?? null]).sort() }))
  }
  return assinatura(antes, edgesAntes) !== assinatura(depois, edgesDepois)
}
