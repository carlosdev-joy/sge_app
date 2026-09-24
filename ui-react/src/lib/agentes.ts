/**
 * Tipos, constantes e helpers da tela `/agentes` (F3 da spec
 * docs/spec-agentes-datastage.md). No estilo de `lib/maestro.ts`: nada de
 * JSX aqui, só o que dá para testar sem montar componente.
 *
 * O backend (`api/routers/agentes.py`) responde erro com `detail` como
 * OBJETO (`{code, message}`), não string — então `err.message` de `apiFetch`
 * cai no fallback `"503 Service Unavailable"`, inútil na tela. `mensagemDeErro`
 * abaixo desdobra o `detail` primeiro; é o mesmo cuidado que
 * `lib/maestroAdmin.ts` e `lib/utilitariosAdmin.ts` já tomam.
 */

export interface AgenteCatalogo {
  id: string
  nome: string
  descricao: string
  curador: boolean
  /**
   * Spec admin (Fase B): o conjunto de ferramentas do agente. Vazio = agente
   * SÓ DE CONVERSA (sem projeto, grafo nem curadoria). Ausente = API anterior
   * à Fase B, que só tinha o DataStage (com todas).
   */
  ferramentas?: string[]
}

/** Agente só de conversa: a API mandou o conjunto, e ele está vazio. */
export function ehSoConversa(ag: Pick<AgenteCatalogo, 'ferramentas'>): boolean {
  return Array.isArray(ag.ferramentas) && ag.ferramentas.length === 0
}

/** Os 8 estados de `ia_provedor.sondar_usuario` (SONDA_*). */
export type EstadoSonda =
  | 'ok'
  | 'sem_cadastro'
  | 'chave_do_app_invalida'
  | 'gateway_indisponivel'
  | 'sem_contrato'
  | 'sem_matricula'
  | 'provedor_incompativel'
  | 'desligado'

export interface StatusAgentes {
  estado: EstadoSonda
  cache: boolean
}

export interface CatalogoResposta {
  agentes: AgenteCatalogo[]
  /**
   * `agentes_cadastro_texto` (Admin › Agentes). Vem no CATÁLOGO, não no
   * status: o catálogo já lê a config, e o `/agentes/status` tem um contrato
   * em que um acerto de cache não abre conexão nenhuma.
   *
   * Vir aqui não significa MOSTRAR: quem decide é `AvisoSonda`, e só no
   * estado `sem_cadastro` — `gateway_indisponivel` nunca fala em cadastro.
   */
  cadastro_texto?: string | null
}

/** `status` de `services/agentes.conversar()`. */
export type StatusRodada =
  | 'ok'
  | 'gateway_recusou'
  | 'erro_provedor'
  | 'limite_rodadas'
  | 'tempo_esgotado'

export interface ArtefatoFerramenta {
  ferramenta: string
  args?: Record<string, unknown>
  /** F6: a chamada falhou de forma permanente (categoria da falha). */
  falhou?: string
  /** F6: a chamada NÃO rodou — já tinha falhado (nesta conversa ou antes). */
  repetida?: boolean
  /** Spec admin B2: a ferramenta não é deste agente — recusada, não rodou. */
  recusada?: string
}

/** Estados de `etl_agente_proposta.estado` (F5). */
export type EstadoProposta = 'pendente' | 'aprovada' | 'recusada' | 'expirada'

/**
 * Uma interpretação do agente que só vira fato se o usuário aprovar (F5).
 * `evidencia` é um trecho LITERAL do que as ferramentas leram — o backend
 * recusa a proposta se não achar o trecho lá — e o cartão a mostra ao lado
 * do que será gravado (risco 15: aprovação sem leitura).
 */
export interface PropostaAgente {
  id: number
  ds_project: string
  job_name: string
  tipo: string
  chave: string
  valor: unknown
  evidencia: string | null
  motivo: string | null
  estado: EstadoProposta
  criada_em: string | null
  decidida_por: string | null
  decidida_em: string | null
  fato_id: number | null
}

export type DecisaoProposta = 'aprovar' | 'recusar'

export interface RespostaConversa {
  conversa_id: string
  status: StatusRodada
  texto: string
  projeto: string | null
  artefatos: ArtefatoFerramenta[]
  /** Propostas desta resposta, já gravadas (`pendente`). */
  propostas?: PropostaAgente[]
  /** Por que as demais propostas do modelo não passaram pela régua. */
  propostas_recusadas?: string[]
  /** F6: aprendizados validados que foram ao contexto desta resposta. */
  aprendizados_usados?: { id: number; titulo: string }[]
  /** F6: aprendizados que o agente sugeriu (rascunho, vão para a curadoria). */
  aprendizados_sugeridos?: string[]
  /** Quanto a resposta levou, do recebimento da pergunta até pronta. */
  duracao_ms?: number
}

export interface MensagemChat {
  id: string
  papel: 'user' | 'assistant'
  texto: string
  /** Só nas do assistente: as ferramentas que rodaram naquela resposta. */
  artefatos?: ArtefatoFerramenta[]
  /** Só nas do assistente: destaca resposta que não terminou em `ok`. */
  status?: StatusRodada
  /**
   * Quando a mensagem foi gravada (ISO do servidor). Só vem nas RETOMADAS:
   * o que o agente disse há três semanas pode ter envelhecido, e o
   * operador precisa ver a data antes de agir (critério 3 da F4). Mensagem
   * da rodada atual não precisa — acabou de acontecer.
   */
  em?: string | null
  /** Só nas do assistente: as propostas daquela resposta (F5). */
  propostas?: PropostaAgente[]
  /** Só na resposta da rodada atual: quantas a régua descartou e por quê. */
  propostasRecusadas?: string[]
  /** Só na resposta da rodada atual (F6): títulos dos aprendizados considerados. */
  aprendizadosUsados?: string[]
  /** Só na resposta da rodada atual (F6): o que foi sugerido à curadoria. */
  aprendizadosSugeridos?: string[]
  /** Só nas do assistente: quanto a resposta levou (também nas retomadas). */
  duracaoMs?: number
}

/** `conversa_id` aceito pelo backend: 8 a 36 chars, `[A-Za-z0-9_-]`. */
export const RE_CONVERSA_ID = /^[A-Za-z0-9_-]{8,36}$/

export const MAX_MENSAGEM = 4000

/**
 * O que a tela mostra para cada estado da sonda.
 *
 * `acao` distingue os dois grupos que a F3.3 separa explicitamente: só
 * `sem_cadastro` pede providência DO USUÁRIO (é onde entra o texto
 * configurável); todo o resto é problema de configuração/infra, e mandar o
 * usuário "pedir cadastro" nesses casos seria empurrá-lo para um chamado
 * inútil. `bloqueia` diz se dá para conversar mesmo assim.
 */
export const SONDA: Record<EstadoSonda, {
  titulo: string
  detalhe: string
  tom: 'ok' | 'aviso' | 'erro'
  acao: 'nenhuma' | 'cadastro' | 'admin'
  bloqueia: boolean
}> = {
  ok: {
    titulo: 'Cadastrado no gateway',
    detalhe: 'Sua matrícula está habilitada no gateway de IA.',
    tom: 'ok', acao: 'nenhuma', bloqueia: false,
  },
  sem_cadastro: {
    titulo: 'Sua matrícula ainda não está cadastrada no gateway de IA',
    detalhe: '',  // vem de `agentes_cadastro_texto` (editável no Admin)
    tom: 'aviso', acao: 'cadastro', bloqueia: true,
  },
  gateway_indisponivel: {
    titulo: 'Gateway indisponível',
    detalhe: 'Não foi possível falar com o gateway de IA agora. Tente de novo em alguns minutos — '
      + 'não é preciso solicitar cadastro.',
    tom: 'erro', acao: 'nenhuma', bloqueia: true,
  },
  chave_do_app_invalida: {
    titulo: 'Credencial do Orquestra recusada pelo gateway',
    detalhe: 'A chave do próprio Orquestra foi recusada — não é o seu cadastro. '
      + 'Avise o administrador.',
    tom: 'erro', acao: 'admin', bloqueia: true,
  },
  sem_contrato: {
    titulo: 'Gateway sem identificação por usuário',
    detalhe: 'O administrador ainda não configurou em que campo vai a identidade do usuário. '
      + 'Enquanto isso, o agente não pode ser usado.',
    tom: 'erro', acao: 'admin', bloqueia: true,
  },
  sem_matricula: {
    titulo: 'Sessão sem matrícula',
    detalhe: 'Sua sessão não tem matrícula — entre de novo. Persistindo, avise o administrador.',
    tom: 'erro', acao: 'admin', bloqueia: true,
  },
  provedor_incompativel: {
    titulo: 'Provedor de IA incompatível',
    detalhe: 'Os agentes exigem um provedor com identidade por usuário. Avise o administrador.',
    tom: 'erro', acao: 'admin', bloqueia: true,
  },
  desligado: {
    titulo: 'IA não configurada',
    detalhe: 'O provedor de IA não está configurado. Avise o administrador.',
    tom: 'erro', acao: 'admin', bloqueia: true,
  },
}

/** Aviso mostrado quando a rodada não terminou em `ok`. */
export const STATUS_RODADA: Record<StatusRodada, string | null> = {
  ok: null,
  gateway_recusou: 'O gateway recusou a chamada. Se persistir, confira seu cadastro com o administrador.',
  erro_provedor: 'O provedor de IA falhou nesta pergunta. Tente de novo.',
  limite_rodadas: 'A pergunta exigiu passos demais. Tente dividi-la em partes menores.',
  tempo_esgotado: 'A pergunta levou tempo demais. Tente algo mais específico (ex.: informe o job).',
}

/** Rótulo curto de cada ferramenta, para a linha de "o que eu consultei". */
export const FERRAMENTAS: Record<string, string> = {
  resolver_projeto: 'projeto',
  base: 'base do Orquestra',
  dsjob: 'DataStage ao vivo',
  dsx_consulta: 'arquivo DSX',
  isx_extrair: 'extração ISX',
}

/**
 * Texto de erro legível a partir do que `apiFetch` levanta.
 *
 * Ordem: `detail.message` (o formato do router de agentes) → `detail` string →
 * `detail.errors` (422 de config do Admin) → `err.message`, mas SÓ quando não
 * é o fallback `"<status> <statusText>"` de `lib/api.ts` (que começa com 3
 * dígitos e não diz nada ao usuário) → `padrao`.
 */
export function mensagemDeErro(e: unknown, padrao = 'Não foi possível concluir a operação'): string {
  const err = e as { message?: string; detail?: unknown } | null | undefined
  const detail = err?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: unknown; errors?: unknown }
    if (typeof d.message === 'string' && d.message.trim()) return d.message
    if (Array.isArray(d.errors) && d.errors.length) return d.errors.map(String).join('; ')
  }
  const msg = err?.message
  if (typeof msg === 'string' && msg.trim() && !/^\d{3} /.test(msg)) return msg
  return padrao
}

/** `code` do `detail`, quando houver — a tela decide por ele, não pelo texto. */
export function codigoDoErro(e: unknown): string | null {
  const detail = (e as { detail?: unknown } | null | undefined)?.detail
  if (detail && typeof detail === 'object') {
    const code = (detail as { code?: unknown }).code
    if (typeof code === 'string' && code) return code
  }
  return null
}

/** Uma conversa na lista do histórico (`GET /agentes/conversas`). */
export interface ConversaResumo {
  conversa_id: string
  agente: string
  titulo: string | null
  projeto: string | null
  criada_em: string | null
  ultima_msg_em: string | null
}

/** Uma conversa retomada (`GET /agentes/conversas/{id}`). */
export interface ConversaDetalhe extends ConversaResumo {
  mensagens: {
    papel: 'user' | 'assistant'
    conteudo: string
    status: StatusRodada | null
    artefatos: ArtefatoFerramenta[]
    criada_em: string | null
    propostas?: PropostaAgente[]
    duracao_ms?: number
  }[]
}

/** Rótulo de cada `tipo` de fato/proposta (`agentes_conhecimento.TIPOS_FATO`). */
export const TIPOS_PROPOSTA: Record<string, string> = {
  stage: 'stage',
  parametro: 'parâmetro',
  tabela: 'tabela',
  campo: 'campo',
  lineage: 'lineage',
  descricao: 'descrição',
}

export const ESTADO_PROPOSTA: Record<EstadoProposta, string> = {
  pendente: 'Aguardando sua decisão',
  aprovada: 'Aprovada',
  recusada: 'Recusada',
  expirada: 'Expirada',
}

/** O valor proposto como texto: string direto, o resto como JSON legível. */
export function valorDaProposta(valor: unknown): string {
  if (typeof valor === 'string') return valor
  try {
    return JSON.stringify(valor, null, 2) ?? ''
  } catch {
    return String(valor)
  }
}

/**
 * Troca, em todas as mensagens, a proposta de mesmo `id` pela versão que o
 * servidor devolveu depois da decisão. Função pura: a tela chama dentro do
 * `setMensagens(m => ...)`, e o resultado vai também para o localStorage —
 * senão, ao recarregar, o cartão voltaria a pedir uma decisão já tomada.
 */
export function aplicarDecisao(mensagens: MensagemChat[], proposta: PropostaAgente): MensagemChat[] {
  // Mesma referência quando a proposta não está nestas mensagens (a conversa
  // na tela mudou enquanto a decisão era salva): quem chama usa isso para
  // NÃO regravar o localStorage com mensagens de outra conversa.
  if (!mensagens.some(m => m.propostas?.some(p => p.id === proposta.id))) return mensagens
  return mensagens.map(m => (
    m.propostas?.some(p => p.id === proposta.id)
      ? { ...m, propostas: m.propostas.map(p => (p.id === proposta.id ? proposta : p)) }
      : m
  ))
}

// ── Curadoria dos aprendizados (F6) ─────────────────────────────────────

export type EstadoAprendizado = 'rascunho' | 'validado' | 'obsoleto' | 'rejeitado'
export type AcaoAprendizado = 'validar' | 'rejeitar' | 'obsoletar'

/** Um item da base de aprendizados (`GET /agentes/aprendizados`). */
export interface Aprendizado {
  id: number
  tipo: string
  titulo: string
  corpo: string
  /** O que o curador lê para decidir — o modelo nunca recebe a evidência. */
  evidencia: string | null
  origem: 'ferramenta' | 'interpretacao' | 'semente' | string
  estado: EstadoAprendizado
  criado_em: string | null
  validado_por: string | null
  validado_em: string | null
  ultimo_uso_em: string | null
  usos: number
  revalidar_em: string | null
}

/** Espelha `agentes_aprendizado.ESTADOS` — a ordem é a das abas. */
export const ESTADOS_APRENDIZADO: { estado: EstadoAprendizado; rotulo: string }[] = [
  { estado: 'rascunho', rotulo: 'A revisar' },
  { estado: 'validado', rotulo: 'Validados' },
  { estado: 'obsoleto', rotulo: 'Obsoletos' },
  { estado: 'rejeitado', rotulo: 'Rejeitados' },
]

/** Espelha `agentes_aprendizado.TRANSICOES`: o que se pode fazer em cada estado. */
export const ACOES_APRENDIZADO: Record<EstadoAprendizado, AcaoAprendizado[]> = {
  rascunho: ['validar', 'rejeitar'],
  validado: ['obsoletar', 'rejeitar'],
  obsoleto: ['validar', 'rejeitar'],
  rejeitado: [],
}

export const ROTULO_ACAO: Record<AcaoAprendizado, string> = {
  validar: 'Validar',
  rejeitar: 'Rejeitar',
  obsoletar: 'Marcar obsoleto',
}

export const TIPOS_APRENDIZADO: Record<string, string> = {
  acesso: 'acesso',
  busca: 'busca',
  leitura: 'leitura',
  detalhamento: 'detalhamento',
  erro: 'erro',
}

export const ORIGEM_APRENDIZADO: Record<string, string> = {
  ferramenta: 'comprovado por ferramenta',
  interpretacao: 'sugerido pelo agente',
  semente: 'semente inicial',
}

/** Dias que uma conversa fica disponível — espelha `RETENCAO_CONVERSAS_DIAS`. */
export const RETENCAO_CONVERSAS_DIAS = 30

/**
 * "hoje", "ontem", "há 3 dias" ou a data — para a lista do histórico e para
 * a data de cada resposta retomada (critério 3 da F4: o operador precisa
 * saber QUANDO o agente disse aquilo, porque o dado pode ter envelhecido).
 */
export function quando(iso: string | null | undefined, agora: Date = new Date()): string {
  if (!iso) return ''
  // `T` no lugar do espaço: sem isso o Safari devolve Invalid Date.
  const d = new Date(iso.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return ''
  const dias = Math.floor((agora.getTime() - d.getTime()) / 86_400_000)
  if (dias <= 0) return `hoje ${d.toTimeString().slice(0, 5)}`
  if (dias === 1) return 'ontem'
  if (dias < 7) return `há ${dias} dias`
  return d.toLocaleDateString('pt-BR')
}

// ── Progresso em tempo real (SSE) e duração — spec docs/spec-agentes-feedback-progresso.md ──

/** Um evento do `POST /agentes/datastage/conversar/stream`. */
export type EventoConversa =
  | { tipo: 'status'; texto: string }
  | ({ tipo: 'resposta' } & RespostaConversa)
  | { tipo: 'erro'; detail: unknown }

/**
 * Separa, do que já chegou pela rede, os eventos SSE COMPLETOS e devolve o
 * resto (um evento pela metade) para juntar com o próximo pedaço.
 *
 * O `reader.read()` entrega pedaços arbitrários: um evento pode chegar
 * partido em dois, ou dois eventos no mesmo pedaço. Separar cada pedaço por
 * `\n` e dar `JSON.parse` na linha (o exemplo da spec) quebra no primeiro
 * evento partido. Aqui só sai o que terminou em linha em branco; comentário
 * (`: keep-alive`) é ignorado; JSON inválido é descartado sem derrubar a
 * leitura. `\r\n` também vale como fim de linha (o padrão SSE permite).
 */
export function lerEventosSSE(acumulado: string): { eventos: EventoConversa[]; resto: string } {
  const texto = acumulado.replace(/\r\n/g, '\n')
  const blocos = texto.split('\n\n')
  const resto = blocos.pop() ?? ''
  const eventos: EventoConversa[] = []
  for (const bloco of blocos) {
    const dados = bloco.split('\n')
      .filter(l => l.startsWith('data:'))
      .map(l => l.slice(5).replace(/^ /, ''))
    if (!dados.length) continue
    try {
      const ev = JSON.parse(dados.join('\n'))
      if (ev && typeof ev === 'object' && typeof ev.tipo === 'string') eventos.push(ev as EventoConversa)
    } catch {
      /* evento corrompido: ignora e segue lendo */
    }
  }
  return { eventos, resto }
}

/** "respondido em 4s" / "respondido em 42s" / "respondido em 2min 15s". */
export function formatarDuracao(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return ''
  const s = Math.max(1, Math.round(ms / 1000))
  if (s < 120) return `respondido em ${s}s`
  return `respondido em ${Math.floor(s / 60)}min ${s % 60}s`
}

/** Data curta (dd/mm/aaaa) — para datas FUTURAS, que `quando` não trata. */
export function dataCurta(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('pt-BR')
}

/** Grupos do histórico, na ordem em que aparecem. */
export const GRUPOS_HISTORICO = ['Hoje', 'Ontem', 'Últimos 7 dias', 'Mais antigas'] as const
export type GrupoHistorico = typeof GRUPOS_HISTORICO[number]

function dataLocal(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? null : d
}

/** Em que grupo do histórico a conversa cai — por DIA de calendário, não por 24 h
 *  (uma conversa de ontem às 23h é "Ontem" mesmo às 8h de hoje). Sem data → "Mais antigas". */
export function grupoDaConversa(iso: string | null | undefined, agora: Date = new Date()): GrupoHistorico {
  const d = dataLocal(iso)
  if (!d) return 'Mais antigas'
  const dia = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const dias = Math.round((dia(agora) - dia(d)) / 86_400_000)
  if (dias <= 0) return 'Hoje'
  if (dias === 1) return 'Ontem'
  if (dias < 7) return 'Últimos 7 dias'
  return 'Mais antigas'
}

/** Hora (HH:MM) se for de hoje; senão a data curta (dd/mm). O grupo já diz o dia. */
export function horaOuDia(iso: string | null | undefined, agora: Date = new Date()): string {
  const d = dataLocal(iso)
  if (!d) return ''
  if (grupoDaConversa(iso, agora) === 'Hoje') return d.toTimeString().slice(0, 5)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
}

// O mesmo prefixo de `lib/api.ts` (que apaga estas chaves no logout) — os dois
// arquivos são autocontidos; `tests/test_agentes_f7_seguranca.py` prende a igualdade.
export const PREFIXO_CONVERSA_AGENTE = 'orquestra_agente_conversa_'

/**
 * Chave de storage da conversa aberta — por USUÁRIO e por agente. Sem a
 * matrícula na chave, quem entrasse depois no mesmo navegador via a última
 * conversa do anterior (achado da auditoria de segurança da F7).
 */
export function chaveDaConversa(agenteId: string, matricula: string): string {
  return `${PREFIXO_CONVERSA_AGENTE}${matricula.trim().toUpperCase()}_${agenteId}`
}


// ── Prompt do domínio: versões (spec docs/spec-agentes-admin.md A2 + BK-1) ──

/** Uma versão do domínio do prompt (`/agentes/admin/agentes/{id}/prompt…`). */
export interface VersaoPrompt {
  versao: number
  motivo: string
  origem_versao: number | null
  criado_em: string | null
  criado_por: string | null
  /** Versão 0 = padrão do código (vale desde o deploy; início não registrado). */
  padrao: boolean
  tamanho: number
  hash: string
  texto?: string
  // BK-1 — só na listagem
  vigente_de?: string | null
  /** `null` = é a ativa. */
  vigente_ate?: string | null
  duracao_s?: number | null
  respostas?: number
  duracao_media_ms?: number | null
}

export interface PromptResposta {
  agente: string
  ativa: VersaoPrompt & { texto: string }
  parte_fixa: { antes: string; depois: string }
  limites: { texto_max: number; motivo_min: number; motivo_max: number }
}

export interface VersoesPromptResposta {
  agente: string
  ativa: number
  versoes: VersaoPrompt[]
  agora: string | null
  retencao_dias: number
}

/**
 * O motivo obrigatório de uma versão. O backend conta em unidades UTF-16 (o
 * que o `NVARCHAR(200)` conta) — e `String.length` do JS já é UTF-16, então a
 * mesma régua vale dos dois lados.
 */
export function motivoValido(motivo: string, min = 3, max = 200): boolean {
  const n = motivo.trim().length
  return n >= min && n <= max
}

/** Quanto tempo uma versão ficou (ou está) em uso: "3 h 20 min", "2 d 4 h". */
export function duracaoDaVigencia(segundos: number | null | undefined): string {
  if (typeof segundos !== 'number' || !Number.isFinite(segundos) || segundos < 0) return '—'
  if (segundos < 60) return 'menos de 1 min'
  const min = Math.floor(segundos / 60)
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return min % 60 ? `${h} h ${min % 60} min` : `${h} h`
  const d = Math.floor(h / 24)
  return h % 24 ? `${d} d ${h % 24} h` : `${d} d`
}

/** Tempo médio de resposta: "850 ms", "12,4 s". */
export function tempoMedio(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1).replace('.', ',')} s`
}

/** "23/09/2026 14:02" — data e hora do BANCO, sem conversão de fuso. */
export function dataHoraCurta(iso: string | null | undefined): string {
  if (!iso) return '—'
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}` : '—'
}


// ── Cadastro de agentes (spec docs/spec-agentes-admin.md, B3) ──────────────

/** Um agente na lista do Admin (`GET /agentes/admin/agentes`). */
export interface BancoLiberado {
  conexao: string
  banco: string
}

export interface AgenteAdminItem {
  id: string
  nome: string
  descricao: string
  /** 'codigo' = o DataStage (não se altera por aqui); 'banco' = criado pela tela. */
  origem: 'codigo' | 'banco'
  acesso: AcessoAgente
  perfis: string[]
  ferramentas: string[]
  /** Pares liberados à consulta a banco (vazio sem a ferramenta). */
  bancos: BancoLiberado[]
  /** C2 da spec ferramenta-banco: mascarar CPF/CNPJ/e-mail/telefone. */
  mascarar_dados: boolean
  ativo: boolean
  recurso: string
  recurso_curador: string | null
  criado_em: string | null
  criado_por: string | null
  atualizado_em: string | null
  atualizado_por: string | null
}

export interface AgentesAdminResposta {
  agentes: AgenteAdminItem[]
  /** As ferramentas de DataStage, na ordem canônica (um checkbox cada). */
  ferramentas: string[]
  /** As que tocam o servidor — nunca com acesso por perfil. */
  ferramentas_servidor: string[]
  /** As de consulta a banco — um interruptor só na tela liga as duas. */
  ferramentas_banco: string[]
  /** Perfis que nunca recebem agente (`consulta`). */
  perfis_proibidos: string[]
}

export type AcessoAgente = 'manual' | 'perfil'

/** Chave do cache de `GET /agentes/admin/agentes` — a mesma no Cadastro, na aba e no Admin. */
export const Q_AGENTES_ADMIN = ['agentes-admin-agentes'] as const

export const ROTULO_ACESSO: Record<AcessoAgente, string> = {
  manual: 'Manual — o admin libera usuário a usuário',
  perfil: 'Por perfil — todo usuário dos perfis escolhidos',
}

/** Teto do texto do prompt — espelha `agentes_prompt.TEXTO_MAX` (a API manda o mesmo em `limites`). */
export const LIMITE_PROMPT = 50000

/** O mesmo formato de id que o backend aceita (`agentes_registro.RE_ID`). */
export const RE_ID_AGENTE = /^[a-z][a-z0-9_]{2,29}$/

/** Ids que o backend recusa (código, rotas e o sufixo de curador). */
export function idReservado(id: string, idsDoCodigo: readonly string[] = ['datastage']): boolean {
  return idsDoCodigo.includes(id)
    || ['admin', 'catalogo', 'status', 'conversas', 'propostas', 'aprendizados'].includes(id)
    || id === 'curador' || id.endsWith('_curador')
}

const DE_PROJETO = ['base', 'dsjob', 'dsx_consulta', 'isx_extrair']

/**
 * Como o backend grava o conjunto: só as da allowlist, na ordem dela, e
 * `resolver_projeto` junto de qualquer uma que dependa de projeto. A tela
 * mostra o resultado ANTES de salvar, para o admin não se surpreender.
 */
export function normalizarFerramentas(escolhidas: readonly string[], allowlist: readonly string[]): string[] {
  const conjunto = new Set(escolhidas.filter(f => allowlist.includes(f)))
  if (DE_PROJETO.some(f => conjunto.has(f))) conjunto.add('resolver_projeto')
  return allowlist.filter(f => conjunto.has(f))
}

export interface RascunhoAgente {
  id: string
  nome: string
  descricao: string
  acesso: AcessoAgente
  perfis: string[]
  ferramentas: string[]
  prompt: string
  motivo: string
}

/**
 * Os problemas que o backend recusaria (422), ditos na tela antes de enviar.
 * Não substitui a validação do servidor — só poupa a ida e volta. `criacao`
 * false = edição (sem id, prompt e motivo).
 */
export function problemasDoAgente(r: RascunhoAgente, opcoes: {
  criacao: boolean
  ferramentasServidor: readonly string[]
  perfisProibidos: readonly string[]
  idsDoCodigo?: readonly string[]
}): string[] {
  const erros: string[] = []
  if (opcoes.criacao) {
    if (!RE_ID_AGENTE.test(r.id)) erros.push('Id: 3 a 30 caracteres — minúsculas, números e _, começando por letra.')
    else if (idReservado(r.id, opcoes.idsDoCodigo)) erros.push(`O id "${r.id}" é reservado.`)
  }
  if (!r.nome.trim()) erros.push('Informe o nome.')
  else if (r.nome.trim().length > 100) erros.push('O nome passa de 100 caracteres.')
  if (!r.descricao.trim()) erros.push('Informe a descrição.')
  else if (r.descricao.trim().length > 500) erros.push('A descrição passa de 500 caracteres.')
  if (!r.perfis.length) erros.push('Escolha ao menos um perfil.')
  const proibidos = r.perfis.filter(p => opcoes.perfisProibidos.includes(p))
  if (proibidos.length) erros.push(`O perfil ${proibidos.join(', ')} não pode receber agente.`)
  const servidor = r.ferramentas.filter(f => opcoes.ferramentasServidor.includes(f))
  if (r.acesso === 'perfil' && servidor.length) {
    erros.push(`Acesso por perfil não vale com ferramenta que toca o servidor (${servidor.join(', ')}) — use o acesso manual.`)
  }
  if (opcoes.criacao) {
    if (!r.prompt.trim()) erros.push('Escreva o prompt inicial.')
    else if (r.prompt.trim().length > LIMITE_PROMPT) erros.push(`O prompt passa de ${LIMITE_PROMPT.toLocaleString('pt-BR')} caracteres.`)
    if (!motivoValido(r.motivo)) erros.push('Informe o motivo (3 a 200 caracteres).')
  }
  return erros
}

/**
 * O agente dono de `recurso` (uso ou curador) quando o `perfil` NÃO pode usá-lo —
 * o nome dele —, ou `null` (pode, não é recurso de agente, ou a lista ainda não
 * carregou). No modal de permissões extras: um grant MARCADO nessa situação está
 * "sem efeito" (a régua de uso confere o perfil a cada pergunta); um grant
 * DESMARCADO não pode ser concedido (a API recusaria com 422). Admin usa tudo.
 */
export function agenteInelegivel(
  recurso: string,
  perfil: string,
  agentes: readonly Pick<AgenteAdminItem, 'nome' | 'recurso' | 'recurso_curador' | 'perfis'>[],
): string | null {
  if (perfil === 'admin') return null
  const ag = agentes.find(a => a.recurso === recurso || a.recurso_curador === recurso)
  if (!ag || ag.perfis.includes(perfil)) return null
  return ag.nome
}
