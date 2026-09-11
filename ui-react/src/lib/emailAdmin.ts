// Admin › E-mail — o lado puro (F1 da spec docs/spec-notificacao-email.md):
// tipos dos endpoints /email/*, listas ↔ texto do formulário e a régua local
// que espelha services/email_config.validar_config (a API é a fonte da
// verdade; aqui só se evita o 422 e se mostra a mensagem na hora).
//
// Exercitado pela bancada tests/js/ds_params_harness.cjs (seção 9).

export interface EmailConfigApi {
  enabled: boolean
  remetente: string
  limite_mb: number
  raizes: string[]
  dominios: string[]
  /** Migration 112: ligado, a opção *Corpo livre* some da lista do nó. */
  exigir_modelo?: boolean
  disponivel: boolean
  ssh_configurado?: boolean
  ssh_host?: string
}

export interface EmailLaudo {
  ok: boolean
  etapa: 'ok' | 'sendmail' | 'config' | 'ssh' | string
  mensagem: string
  host: string
  exit_code: number | null
  stderr: string
  duration_ms: number | null
  destinatarios: string[]
  remetente: string
  persistido?: boolean
}

export interface EmailLogItem {
  id: number
  pipeline_name: string
  job_name: string
  dag_run_id: string | null
  execution_id: string | null
  remetente: string
  destinatarios: string[]
  assunto: string
  anexo_path: string | null
  anexo_bytes: number | null
  status: string
  erro: string | null
  duracao_ms: number | null
  criado_por: string | null
  criado_em: string
}

/** Modelo do catálogo (migration 112). O `corpo` não vem na lista do Admin —
 *  só `corpo_tamanho` — para não trafegar todo o HTML de cada um. */
export interface EmailModelo {
  id: number
  nome: string
  descricao: string | null
  assunto: string | null
  corpo?: string
  corpo_tamanho?: number
  html: boolean
  ativo: boolean
  padrao: boolean
  criado_por: string | null
  criado_em: string
  atualizado_em: string | null
}

export interface EmailModeloForm {
  nome: string
  descricao: string
  assunto: string
  corpo: string
  html: boolean
  ativo: boolean
  padrao: boolean
}

export function formDoModelo(m: EmailModelo | null): EmailModeloForm {
  return {
    nome: m?.nome ?? '',
    descricao: m?.descricao ?? '',
    assunto: m?.assunto ?? '',
    corpo: m?.corpo ?? '',
    html: m?.html ?? true,
    ativo: m?.ativo ?? true,
    padrao: m?.padrao ?? false,
  }
}

/** Régua local do modelo — espelha `services/email_modelos.validar`. */
export function errosDoModelo(f: EmailModeloForm): string[] {
  const erros: string[] = []
  const nome = f.nome.trim()
  if (!nome) erros.push('Informe o nome do modelo')
  else if (nome.length > 120) erros.push('Nome com mais de 120 caracteres')
  else if (nome.split(/\r|\n/).length > 1) erros.push('O nome não pode ter quebra de linha')
  if (f.descricao.length > 400) erros.push('Descrição com mais de 400 caracteres')
  const assunto = f.assunto.trim()
  if (assunto && assunto.split(/\r|\n/).length > 1) erros.push('O assunto sugerido não pode ter quebra de linha')
  if (assunto.length > 500) erros.push('Assunto sugerido com mais de 500 caracteres')
  if (!f.corpo.trim()) erros.push('Informe o corpo do modelo')
  else if (f.corpo.length > 20000) erros.push('Corpo com mais de 20.000 caracteres')
  return erros
}

export interface EmailConfigForm {
  enabled: boolean
  remetente: string
  limite_mb: string
  raizesTexto: string
  dominiosTexto: string
  exigirModelo: boolean
}

export const LIMITE_ANEXO_MB_MIN = 1
export const LIMITE_ANEXO_MB_MAX = 25
/** `etl_app_config.config_value` é VARCHAR(1000): o JSON de cada lista tem de caber. */
export const LIMITE_VALOR = 1000
// Espelha EMAIL_RE de services/email_mime.py.
export const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
export const RAIZ_RE = /^\/[^\s'"]*[^\s'"/]$|^\/$/
export const DOMINIO_RE = /^[a-z0-9.-]+\.[a-z]{2,}$/

export const ETAPA_LAUDO: Record<string, string> = {
  ok: 'Enviado ao sendmail',
  sendmail: 'O sendmail recusou',
  config: 'Configuração incompleta',
  ssh: 'Não chegou ao servidor do DataStage',
}

/** Uma entrada por linha (ou vírgula/;), sem vazios e sem repetição. */
export function listaDoTexto(texto: string): string[] {
  const saida: string[] = []
  for (const parte of (texto ?? '').split(/[\n,;]+/)) {
    const v = parte.trim()
    if (v && !saida.includes(v)) saida.push(v)
  }
  return saida
}

export function textoDaLista(lista: string[] | undefined | null): string {
  return (lista ?? []).join('\n')
}

export function formDaConfig(c: EmailConfigApi): EmailConfigForm {
  return { enabled: c.enabled, remetente: c.remetente ?? '', limite_mb: String(c.limite_mb ?? 5),
           raizesTexto: textoDaLista(c.raizes), dominiosTexto: textoDaLista(c.dominios),
           exigirModelo: c.exigir_modelo === true }
}

export function configParaApi(f: EmailConfigForm) {
  return { enabled: f.enabled, remetente: f.remetente.trim(), limite_mb: Number(f.limite_mb),
           raizes: listaDoTexto(f.raizesTexto), dominios: listaDoTexto(f.dominiosTexto),
           exigir_modelo: f.exigirModelo }
}

/** Régua local — espelha validar_config: ligar exige remetente válido, limite
 *  1–25, raízes absolutas sem `..`/espaço/aspas, domínios `x.y`. */
export function errosDaConfig(f: EmailConfigForm): string[] {
  const erros: string[] = []
  const rem = f.remetente.trim()
  if (rem && !EMAIL_RE.test(rem)) erros.push('Remetente inválido (um endereço de e-mail)')
  if (f.enabled && !rem) erros.push('Informe o remetente antes de ligar o canal')
  const n = Number(f.limite_mb)
  if (!Number.isInteger(n) || n < LIMITE_ANEXO_MB_MIN || n > LIMITE_ANEXO_MB_MAX) {
    erros.push(`Limite de anexo entre ${LIMITE_ANEXO_MB_MIN} e ${LIMITE_ANEXO_MB_MAX} MB`)
  }
  const raizes = listaDoTexto(f.raizesTexto)
  for (const r of raizes) {
    const limpa = r.replace(/\/+$/, '') || '/'
    if (limpa === '/') erros.push('Raiz inválida: "/" abriria o servidor inteiro — use uma pasta')
    else if (!RAIZ_RE.test(limpa) || (limpa + '/').includes('/../') || limpa.startsWith('/..') || (limpa + '/').includes('/./')) {
      erros.push(`Raiz inválida: ${r} (caminho absoluto, sem espaços, aspas, "." ou "..")`)
    }
  }
  const dominios = listaDoTexto(f.dominiosTexto)
  for (const d of dominios) {
    if (!DOMINIO_RE.test(d.toLowerCase().replace(/^@/, ''))) erros.push(`Domínio inválido: ${d}`)
  }
  if (JSON.stringify(raizes).length > LIMITE_VALOR) erros.push(`Raízes: lista longa demais (limite ${LIMITE_VALOR} caracteres em JSON)`)
  if (JSON.stringify(dominios).length > LIMITE_VALOR) erros.push(`Domínios: lista longa demais (limite ${LIMITE_VALOR} caracteres em JSON)`)
  return erros
}

export function mensagemErroEmail(e: unknown, padrao: string): string {
  const err = e as { status?: number; message?: string; detail?: unknown } | null
  const detail = err?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as { errors?: unknown; mensagem?: unknown }
    if (Array.isArray(d.errors) && d.errors.length) return d.errors.map(String).join(' · ')
    if (typeof d.mensagem === 'string' && d.mensagem.trim()) return d.mensagem
  }
  if (typeof detail === 'string' && detail.trim()) return detail
  if (typeof err?.message === 'string' && err.message.trim() && !/^\d{3} /.test(err.message)) return err.message
  return padrao
}

// ⚠️ Migration pendente é 503 COM a migração nomeada. Banco fora do ar também
// dá 503, e a API separa os dois de propósito ("Banco fora do ar NÃO é
// 'migration pendente'"): tratar todo erro como migração faria a tela dar o
// único diagnóstico errado justamente quando o problema é outro.
function migrationPendente(e: unknown, numero: number): boolean {
  const err = e as { status?: number; message?: string; detail?: unknown } | null
  const texto = typeof err?.detail === 'string' ? err.detail : (err?.message ?? '')
  return err?.status === 503 && new RegExp(`migration ${numero}`, 'i').test(texto)
}

export function migration111Pendente(e: unknown): boolean {
  return migrationPendente(e, 111)
}

export function migration112Pendente(e: unknown): boolean {
  return migrationPendente(e, 112)
}
