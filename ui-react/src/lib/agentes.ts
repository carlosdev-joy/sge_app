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
}

export interface RespostaConversa {
  conversa_id: string
  status: StatusRodada
  texto: string
  projeto: string | null
  artefatos: ArtefatoFerramenta[]
}

export interface MensagemChat {
  id: string
  papel: 'user' | 'assistant'
  texto: string
  /** Só nas do assistente: as ferramentas que rodaram naquela resposta. */
  artefatos?: ArtefatoFerramenta[]
  /** Só nas do assistente: destaca resposta que não terminou em `ok`. */
  status?: StatusRodada
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

/** Chave de storage da conversa aberta, por agente (mesma ideia de `lib/maestro.ts`). */
export function chaveDaConversa(agenteId: string): string {
  return `orquestra_agente_conversa_${agenteId}`
}
