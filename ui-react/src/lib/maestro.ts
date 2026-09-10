// Maestro — o assistente de parâmetros DataStage no front (F2 da spec
// docs/spec-maestro-parametros.md).
//
// Módulo PURO (sem React): o contrato com `POST /maestro/conversar`, o que
// vai no contexto (as linhas do editor SEM valor Encrypted — o provedor pode
// ser externo), a conversão da proposta da API em linhas do editor e a mescla
// com o que já está lá (substitui pelo nome exato, preserva o resto). A tela
// (MaestroChat/MaestroPainel) só orquestra estado e chamadas.
//
// Exercitado pela bancada tests/js/ds_params_harness.cjs (seção 7).
import {
  DS_PARAM_ANCORAS, DS_PARAM_SOURCES, paramsFromApi, type JobParam, type JobParamApi,
} from './dsParams'

export type JobParamLinha = JobParam

export const MAESTRO_NOME = 'Maestro'
export const MAESTRO_MAX_HISTORICO = 12      // rodadas enviadas por chamada (a API corta no mesmo teto)
export const MAESTRO_MAX_MENSAGEM = 4000     // o que o usuário digita (a API recusa acima)
export const MAESTRO_BOAS_VINDAS =
  'Olá! Sou o Maestro. Descreva o cenário desta etapa — por exemplo, "carga mensal do mês '
  + 'anterior com data inicial e final" — e eu digo como preencher cada parâmetro. '
  + 'Nada é salvo até você aplicar no editor e salvar a etapa.'
export const MAESTRO_BOAS_VINDAS_PIPELINE =
  'Olá! Sou o Maestro. Aqui você cadastra os parâmetros do pipeline: eles valem para toda etapa '
  + 'DataStage cujo job declarar o nome, sem configurar nada nas etapas (a etapa pode sobrepor). '
  + 'Descreva o cenário — por exemplo, "carga mensal do mês anterior com data inicial e final" — '
  + 'ou pergunte como a herança e as datas funcionam. Nada é salvo até você aplicar no editor e salvar o pipeline.'

export type MaestroStatusRodada = 'atendido' | 'nao_atendido' | 'pergunta' | 'explicacao'
/** Onde o usuário está: na etapa (Parâmetros do job) ou no pipeline (defaults do wizard). */
export type MaestroNivel = 'etapa' | 'pipeline'

export interface MaestroPrevia { param_name: string; valor: string; descricao: string }

/** O que `POST /maestro/conversar` devolve. */
export interface MaestroResposta {
  conversa_id: string
  resposta: string
  status: MaestroStatusRodada
  cenario: string | null
  motivo: string | null
  proposta: { params: JobParamApi[] } | null
  previa: MaestroPrevia[] | null
  avisos: string[]
  orientacao: string | null
  referencia: string
}

export type MaestroResultado = Omit<MaestroResposta, 'conversa_id' | 'resposta'>

export interface MaestroMensagem {
  id: number
  papel: 'user' | 'assistant'
  texto: string
  /** Só nas respostas do Maestro que vieram da API (a de boas-vindas e as de erro não têm). */
  resultado?: MaestroResultado
  /** Proposta já aplicada no editor (o botão vira "Aplicado"). */
  aplicada?: boolean
  /** Bolha de erro (provedor fora, 429…): não volta ao provedor no histórico. */
  erro?: boolean
  /** Boas-vindas: não vai ao provedor (a API descarta assistant antes do 1º user). */
  sistema?: boolean
}

export interface MaestroStatus { enabled: boolean; sugestoes: string[] }

export interface MaestroHistoricoRodada { mensagem: string; resposta: string | null; status: string }
export interface MaestroHistoricoConversa {
  conversa_id: string
  iniciado_em: string
  pipeline_name: string | null
  job_name: string | null
  rodadas: MaestroHistoricoRodada[]
}

// ── a conversa sobrevive à desmontagem do componente ────────────────────────
// No wizard do pipeline a seção de parâmetros só existe no passo 2: trocar de
// passo desmontava o MaestroChat e a conversa (com a proposta ainda não
// aplicada) sumia (achado 1 da revisão adversarial do complemento). O estado
// vive aqui, por chave (nível + pipeline + job), até "Nova conversa" ou o F5.

export interface ConversaGuardada {
  conversaId: string
  mensagens: MaestroMensagem[]
  aberto: boolean
}

const conversasGuardadas = new Map<string, ConversaGuardada>()

export function chaveDaConversa(nivel: MaestroNivel, pipeline?: string, jobName?: string): string {
  return `${nivel}|${(pipeline ?? '').trim()}|${nivel === 'etapa' ? (jobName ?? '').trim() : ''}`
}

export function lerConversaGuardada(chave: string): ConversaGuardada | undefined {
  return conversasGuardadas.get(chave)
}

export function guardarConversa(chave: string, estado: ConversaGuardada): void {
  conversasGuardadas.set(chave, estado)
}

export function esquecerConversa(chave: string): void {
  conversasGuardadas.delete(chave)
}

// ── ids ─────────────────────────────────────────────────────────────────────

/** uuid v4 quando o browser tem `crypto.randomUUID`; senão um id aleatório que
 *  cabe na régua da API (`^[A-Za-z0-9_-]{8,36}$`). */
export function novoConversaId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  let s = ''
  while (s.length < 32) s += Math.random().toString(36).slice(2)
  return s.slice(0, 32)
}

export function mensagemDeBoasVindas(nivel: MaestroNivel = 'etapa'): MaestroMensagem {
  return { id: 0, papel: 'assistant', texto: nivel === 'pipeline' ? MAESTRO_BOAS_VINDAS_PIPELINE : MAESTRO_BOAS_VINDAS, sistema: true }
}

// ── contexto (o que vai ao servidor) ────────────────────────────────────────

const CHAVES_CONTEXTO = [
  'param_name', 'param_type', 'param_source', 'param_value',
  'param_offset_meses', 'param_ancora', 'param_offset_dias', 'param_formato',
] as const

export interface MaestroContexto {
  nivel: MaestroNivel
  pipeline_name?: string
  job_name?: string
  referencia: string
  params: Record<string, string>[]
}

/** As linhas do editor como o Maestro pode vê-las: só as colunas do
 *  contrato, sem `id`/`tem_valor`, e o valor de Encrypted NUNCA (o servidor
 *  também remove — aqui é a primeira barreira, antes de sair do browser). */
export function contextoDoEditor(pipeline: string | undefined, jobName: string | undefined,
                                 params: JobParam[], referencia: string,
                                 nivel: MaestroNivel = 'etapa'): MaestroContexto {
  const linhas: Record<string, string>[] = []
  for (const p of params) {
    const nome = (p.param_name ?? '').trim()
    if (!nome) continue
    const item: Record<string, string> = {}
    for (const c of CHAVES_CONTEXTO) {
      const v = p[c]
      if (v === undefined || v === null || v === '') continue
      item[c] = String(v)
    }
    if (p.param_type === 'Encrypted') delete item.param_value
    item.param_name = nome
    linhas.push(item)
  }
  const ctx: MaestroContexto = { nivel, referencia, params: linhas }
  if (pipeline?.trim()) ctx.pipeline_name = pipeline.trim()
  if (nivel === 'etapa' && jobName?.trim()) ctx.job_name = jobName.trim()
  return ctx
}

/** As últimas rodadas em `{role, content}`: sem boas-vindas, sem bolhas de
 *  erro (não são fala do modelo) e sem o bloco JSON (a API já o retirou do
 *  `resposta`). Corta no mesmo teto da API. */
export function historicoParaEnvio(mensagens: MaestroMensagem[]): { role: 'user' | 'assistant'; content: string }[] {
  return mensagens
    .filter(m => !m.sistema && !m.erro && m.texto.trim())
    .map(m => ({ role: m.papel, content: m.texto }))
    .slice(-MAESTRO_MAX_HISTORICO)
}

// ── proposta → editor ───────────────────────────────────────────────────────

// Sequência dos ids das linhas vindas do Maestro: `m_<n>_<nome>`. Só o índice
// da proposta não bastava — renomear uma linha aplicada e aplicar outra
// proposta com o mesmo nome dava dois ids iguais (key duplicada no editor).
let sequenciaId = 0

/** A proposta validada da API vira linhas do editor (mesma hidratação do GET
 *  da etapa): Encrypted chega com `param_value: ''` + `tem_valor: false`,
 *  então a linha nasce vazia para o usuário digitar. */
export function propostaParaEditor(params: JobParamApi[]): JobParam[] {
  return paramsFromApi(params).map(p => ({ ...p, id: `m_${++sequenciaId}_${p.param_name}` }))
}

export interface ResultadoAplicacao { params: JobParam[]; substituidos: string[]; adicionados: string[] }

/** Mescla a proposta nas linhas ATUAIS do editor: mesmo nome (caixa exata,
 *  como o DataStage) substitui a linha no lugar; nome novo entra no fim; o
 *  que o Maestro não citou fica como está.
 *
 *  Encrypted sobre Encrypted: a proposta vem SEM valor (o Maestro nunca o
 *  tem), então o segredo da linha atual — o token gravado (`tem_valor`) ou o
 *  que o usuário digitou e ainda não salvou — é PRESERVADO. Sem isso a linha
 *  virava "informe o valor" e travava o salvar de quem não sabe a senha
 *  (achado 1 da revisão adversarial da F2). */
export function aplicarProposta(atuais: JobParam[], novos: JobParam[]): ResultadoAplicacao {
  const porNome = new Map(novos.map(n => [n.param_name.trim(), n]))
  const substituidos: string[] = []
  const params: JobParam[] = atuais.map(a => {
    const n = porNome.get(a.param_name.trim())
    if (!n) return a
    substituidos.push(a.param_name.trim())
    porNome.delete(a.param_name.trim())
    const linha: JobParam = { ...n, id: a.id ?? n.id }
    if (a.param_type === 'Encrypted' && n.param_type === 'Encrypted' && !n.param_value) {
      linha.param_value = a.param_value
      linha.tem_valor = a.tem_valor
    }
    return linha
  })
  const adicionados: string[] = []
  for (const n of porNome.values()) {
    params.push(n)
    adicionados.push(n.param_name.trim())
  }
  return { params, substituidos, adicionados }
}

/** O que se salva depois de aplicar: a etapa (Etapas/Fluxos) ou o pipeline (wizard). */
export function alvoDoSalvar(nivel: MaestroNivel = 'etapa'): string {
  return nivel === 'pipeline' ? 'salve o pipeline' : 'salve a etapa'
}

export function resumoAplicacao(r: ResultadoAplicacao, nivel: MaestroNivel = 'etapa'): string {
  const partes = [
    r.adicionados.length ? `${r.adicionados.length} parâmetro(s) adicionado(s)` : '',
    r.substituidos.length ? `${r.substituidos.length} substituído(s): ${r.substituidos.join(', ')}` : '',
  ].filter(Boolean)
  return `${partes.join(' · ') || 'nada mudou'} — confira os valores e ${alvoDoSalvar(nivel)}`
}

// ── rótulos (o cartão da proposta) ──────────────────────────────────────────

export function rotuloOrigem(origem?: string | null): string {
  return DS_PARAM_SOURCES.find(s => s.value === (origem ?? 'fixo'))?.label ?? String(origem ?? '')
}

export function rotuloAncora(ancora?: string | null): string {
  return DS_PARAM_ANCORAS.find(a => a.value === (ancora ?? ''))?.label ?? String(ancora ?? '')
}

/** Uma linha por parâmetro do cartão: "Date · Data de referência · −1 mês · fim do mês · %Y-%m-%d". */
export function descricaoDaLinha(p: JobParamApi): string {
  const partes = [p.param_type, rotuloOrigem(p.param_source)]
  const origemData = ['data_referencia', 'data_logica', 'data_execucao'].includes(p.param_source ?? '')
  if (origemData) {
    const meses = Number(p.param_offset_meses ?? 0)
    const dias = Number(p.param_offset_dias ?? 0)
    if (meses) partes.push(`${meses > 0 ? '+' : '−'}${Math.abs(meses)} ${Math.abs(meses) === 1 ? 'mês' : 'meses'}`)
    if (p.param_ancora) partes.push(rotuloAncora(p.param_ancora))
    if (dias) partes.push(`${dias > 0 ? '+' : '−'}${Math.abs(dias)} ${Math.abs(dias) === 1 ? 'dia' : 'dias'}`)
    partes.push(p.param_formato || '%Y-%m-%d')
  } else if (p.param_type === 'Encrypted') {
    partes.push('digite o valor no editor')
  } else if ((p.param_source ?? 'fixo') === 'fixo') {
    partes.push(`valor: ${p.param_value ?? ''}`)
  }
  return partes.join(' · ')
}

// ── erros da API → texto da bolha ───────────────────────────────────────────

export function mensagemDeErro(err: { status?: number; message?: string; detail?: unknown } | null | undefined): string {
  const status = err?.status
  const detail = err?.detail as { errors?: unknown } | string | undefined
  if (status === 429) return 'Limite de requisições do provedor de IA excedido. Aguarde um momento e tente de novo.'
  if (status === 402) return 'Créditos insuficientes no provedor de IA — contate o administrador.'
  if (status === 422 && detail && typeof detail === 'object' && Array.isArray(detail.errors)) {
    return `Não consegui enviar: ${(detail.errors as unknown[]).map(String).join('; ')}`
  }
  if (status === 503) return `${typeof detail === 'string' && detail ? detail : 'Maestro indisponível'} — contate o administrador.`
  if (status === 403) return 'Seu perfil não tem acesso ao Maestro.'
  return err?.message || 'Não foi possível falar com o Maestro agora.'
}
