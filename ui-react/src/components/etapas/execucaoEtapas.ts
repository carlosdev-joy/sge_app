// Modo Execução do canvas de Etapas (F3 da spec docs/spec-operacao-nivel-etapa.md,
// §3 Bloco A) — o CONTRATO do GET /pipelines/{p}/execucao (entregue pela F2) e a
// camada de leitura que a F3 pinta por cima do desenho.
//
// Módulo PURO de propósito: nada de React aqui. O que decide cor, rótulo,
// horário e "caminho percorrido" fica testável e num lugar só — a classe de bug
// que já derrubou uma tela deste repo foi front e back divergirem em nome de
// campo, e o antídoto é o contrato escrito uma vez, copiado da resposta REAL.
//
// ⚠️ DECISÃO DE IMPLEMENTAÇÃO REGISTRADA (usuário, F3) — **UMA FONTE SÓ DE
// HORÁRIO**: todo horário desta tela vem das ETAPAS (`etl_job_execution`). O
// intervalo do pipeline é derivado de min(início)/max(fim) DAS ETAPAS
// (`janelaDasEtapas`), NUNCA de `etl_pipeline_execucao.inicio/fim`. Motivo: as
// duas tabelas usam relógios diferentes — `GETDATE()` do SQL Server na 067 ×
// relógio local do factory na telemetria — e no ambiente dev divergem 3 horas
// (medido em 2026-08-03: corrida 12:49:55 → 12:50:20 na 067, etapas 09:49:59 →
// 09:50:15 na telemetria, a MESMA execução). Misturar as duas faria a tela
// mentir. Status e ODATE do pipeline seguem vindo da 067 normalmente — a regra
// vale só para HORÁRIO.
import { estiloStatus, type EstiloStatus } from '../malhas/statusExecucao'

// ═══════════════════════════ contrato do endpoint ═══════════════════════════
// Copiado da resposta REAL do dev (2026-08-03,
// GET /pipelines/DEV_F10_D/execucao?data_referencia=2026-08-03). Campos
// opcionais só onde a API pode legitimamente omitir.

export interface EtapaExecucaoApi {
  job_name: string
  task_id: string | null
  /** tipo do DESENHO (datastage|decisao|sql|…); null quando a etapa executou
   *  mas não está mais no desenho de hoje (`no_desenho: false`). */
  job_type: string | null
  execution_order: number | null
  depends_on_jobs: string[]
  /** false = rodou ontem e saiu do desenho — a F2 não esconde essas linhas. */
  no_desenho: boolean
  /** true = etapa do desenho SEM linha de execução → NEUTRA, nunca verde. */
  sem_execucao: boolean
  /** status CRU da telemetria (SUCCESS/FAILED/RUNNING/SKIPPED/…) ou null. */
  status: string | null
  inicio: string | null
  fim: string | null
  duration_seconds: number | null
  status_code: string | null
  /** número da tentativa CORRENTE (F4). Antes da migration 078 vinha null; o
   *  backfill marcou 1 nas linhas existentes. Os campos acima são sempre os da
   *  tentativa MAIS RECENTE — as anteriores vêm em `tentativas`. */
  attempt: number | null
  log_file: string | null
  host: string | null
  /** (F4) tentativas SUPERADAS, da mais antiga para a mais nova, SEM a
   *  corrente. Vazio = só houve uma (ou a migration 078 está pendente). */
  tentativas: TentativaApi[]
  /** anteriores + a corrente. 0 = etapa sem execução. */
  total_tentativas: number
}

/** Uma tentativa já superada de uma etapa (migration 078). */
export interface TentativaApi {
  attempt: number | null
  status: string | null
  inicio: string | null
  fim: string | null
  duration_seconds: number | null
  status_code: string | null
  host: string | null
  log_file: string | null
}

export interface CorridaApi {
  run_id: string | null
  status: string | null
  inicio: string | null
  fim: string | null
  disparado_por: string | null
  /** (F4) carimbo de aposentadoria por rerun com cascata — quando preenchido,
   *  esta corrida NÃO conta como sucesso vivo do dia (`liberado()` e
   *  `pipelines_todos_sucesso()` a ignoram). Sem ele, o aviso de ambiguidade
   *  mostrava duas corridas idênticas e o operador escolhia no escuro. */
  substituida_em?: string | null
}

export interface IdentidadeApi {
  resolvido: boolean
  ts_nodash: string | null
  run_id: string | null
  dag_run_id: string | null
  logical_date: string | null
  data_referencia: string | null
  origem: string | null
  ambiguo: boolean
  candidatos: CorridaApi[]
  regra: string | null
  degradado: boolean
  motivo: string | null
}

/** (F5) Uma pausa de etapa — `dbo.etl_etapa_pausa`, migration 079.
 *
 *  Os dois estados que a TELA precisa distinguir não são dois `estado`
 *  diferentes, e sim `estado='PENDENTE'` com ou sem `aguardando_desde`:
 *    • sem  → pausa MARCADA: a etapa ainda não chegou ao portão;
 *    • com  → EM ESPERA: o processo está parado ali, agora.
 *  Chamar as duas de "pausada" esconderia justamente o que o operador precisa
 *  saber (se já parou ou não). */
export interface PausaApi {
  id: number
  job_name: string
  task_id: string | null
  /** PENDENTE | LIBERADA | CANCELADA | EXPIRADA */
  estado: string
  motivo: string | null
  observacao: string | null
  teto_minutos: number | null
  solicitado_por: string | null
  solicitado_em: string | null
  /** 1ª chegada da etapa ao portão — null = ainda não parou nada */
  aguardando_desde: string | null
  ultima_verificacao: string | null
  verificacoes: number | null
  resolvido_por: string | null
  resolvido_em: string | null
  alertado_em: string | null
  data_referencia: string | null
  /** minutos parados, calculados PELO BANCO (o carimbo é GETDATE(); medir com
   *  o relógio do cliente daria tempo negativo — o defeito do "-179 min"). */
  parado_min: number | null
}

export interface PipelineExecucaoApi {
  pipeline_name: string
  data_referencia: string | null
  identidade: IdentidadeApi
  corrida: CorridaApi | null
  etapas: EtapaExecucaoApi[]
  /** (F5) pausas desta corrida — pendentes e resolvidas. Ausente/vazio quando
   *  a migration 079 não está aplicada: a tela some com o recurso, não quebra. */
  pausas?: PausaApi[]
  /** (F5) a DAG PUBLICADA deste pipeline obedece a pausa?
   *
   *  As duas metades do deploy da F5 são o BANCO (migration 079) e a DAG
   *  (o portão só é emitido no fonte gerado, e só depois de republicar).
   *  Uma pausa criada em DAG sem portão não segura nada — o processo passa
   *  direto. Por isso o estado vem no payload: a tela avisa ANTES do clique,
   *  em vez de o operador descobrir pela recusa do servidor.
   *
   *  'ok' | 'dag_sem_portao' | 'portao_desconhecido' (ausente = API anterior). */
  portao?: string | null
  total_etapas: number
  etapas_executadas: number
  vazio: boolean
  razao: string | null
  migration_067_pendente: boolean
  airflow_indisponivel: boolean
}

// ══════════════════════════════ status da etapa ═════════════════════════════
// A paleta é a MESMA da malha (components/malhas/statusExecucao) — não se cria
// paleta nova. O que muda é o vocabulário: a 067 fala pt-BR (SUCESSO/FALHA…) e
// a telemetria de etapa fala Airflow (SUCCESS/FAILED…). Este mapa é a tradução,
// e só ela; status fora do mapa cai no fallback NEUTRO de `estiloStatus`, que
// exibe o texto cru — o operador vê o que o banco tem, sem cor inventada.
const MAPA_STATUS: Record<string, string> = {
  SUCCESS: 'SUCESSO',
  FAILED: 'FALHA',
  RUNNING: 'EXECUTANDO',
  // Regra de honestidade do §3: SKIPPED tem COR PRÓPRIA (o cinza do "pulado")
  // e não conta como sucesso nem como falha.
  SKIPPED: 'PULADO',
}

/** Estilo de uma etapa; `null` = SEM LINHA de execução (neutro, nunca verde). */
export function estiloEtapa(status: string | null | undefined): EstiloStatus | null {
  const cru = (status ?? '').trim()
  if (!cru) return null
  return estiloStatus(MAPA_STATUS[cru.toUpperCase()] ?? cru)
}

export const ehPulada = (status: string | null | undefined) =>
  (status ?? '').trim().toUpperCase() === 'SKIPPED'

const ehTerminalOk = (status: string | null | undefined) => {
  const s = (status ?? '').trim().toUpperCase()
  return !!s && s !== 'SKIPPED'
}

// ═══════════════════════════════ formatação ═════════════════════════════════

/** '2026-08-03 09:49:59' → '09:49:59'. Sem data: a tela já diz qual é o ODATE. */
export function horaLonga(iso: string | null | undefined): string {
  if (!iso) return '—'
  const parte = String(iso).split(' ')[1] ?? String(iso).split('T')[1]
  return parte ? parte.slice(0, 8) : '—'
}

/** Duração legível — mesma régua do `durStr` do modal de Logs (não importado
 *  daqui para não arrastar aquele módulo inteiro para o chunk do canvas). */
export function duracaoCurta(seg: number | null | undefined): string {
  if (seg == null) return '—'
  const s = Math.max(0, Math.round(seg))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  if (h > 0) return `${h}h ${m}m ${r}s`
  return m > 0 ? `${m}m ${r}s` : `${r}s`
}

// ═════════════════════════ a camada de execução ═════════════════════════════

/** O que cada NÓ do canvas mostra no modo Execução (pré-calculado aqui para os
 *  componentes de nó só desenharem). `status: null` = etapa sem linha. */
export interface ExecNoEtapa {
  status: string | null
  rotulo: string
  /** classes do anel (outline — não briga com o `ring` azul da seleção) */
  anel: string
  dot: string
  animado: boolean
  /** linha curta sob o nó: '09:49:59 → 09:50:15 · 16s' */
  resumo: string
  /** tooltip completo (status, início, fim, duração, host, tentativas) */
  titulo: string
  pulada: boolean
  /** (F4) número da tentativa em exibição (a mais recente) */
  tentativa: number | null
  /** (F4) tentativas superadas, para a linha do tempo do dock */
  tentativas: TentativaApi[]
  /** (F5) a pausa PENDENTE desta etapa, se houver */
  pausa?: PausaApi | null
  /** (F5) true = a etapa está PARADA no portão agora (aguardando liberação) */
  emEspera?: boolean
}

export interface CamadaExecucao {
  /** job_name em casefold → etapa (colação CI do banco × dict case-sensitive
   *  do JS: é o incidente da PR #236 aplicado aqui). */
  porJob: Map<string, EtapaExecucaoApi>
  /** decorações prontas por nó, na mesma chave */
  noPorJob: Map<string, ExecNoEtapa>
  /** (F5) pausa PENDENTE por etapa, na mesma chave */
  pausaPorJob: Map<string, PausaApi>
}

const chave = (nome: string | null | undefined) =>
  String(nome ?? '').trim().toLowerCase()

function decorarEtapa(e: EtapaExecucaoApi): ExecNoEtapa {
  const est = estiloEtapa(e.status)
  const pulada = ehPulada(e.status)
  if (!est) {
    // Etapa do desenho SEM execução: neutra e DITA — "sem execução" é
    // informação, não ausência de informação.
    return {
      status: null,
      rotulo: 'sem execução',
      anel: '',
      dot: 'bg-slate-300 dark:bg-slate-600',
      animado: false,
      resumo: 'sem execução nesta data',
      titulo: `${e.job_name}\nSem linha de execução nesta data — a etapa está `
        + 'no desenho, mas não rodou (nem sucesso, nem falha).',
      pulada: false,
      tentativa: null,
      tentativas: [],
    }
  }
  const ini = horaLonga(e.inicio)
  const fim = horaLonga(e.fim)
  const dur = e.duration_seconds != null ? duracaoCurta(e.duration_seconds) : null
  const resumo = [
    `${ini} → ${fim}`,
    dur,
  ].filter(Boolean).join(' · ')
  const anteriores = e.tentativas ?? []
  const linhas = [
    e.job_name,
    `status: ${e.status}${pulada ? ' (ramo não tomado — não é sucesso nem falha)' : ''}`,
    `início: ${e.inicio ?? '—'}`,
    `fim: ${e.fim ?? '—'}`,
    `duração: ${dur ?? '—'}`,
    e.attempt != null ? `tentativa: ${e.attempt}` : null,
    e.host ? `host: ${e.host}` : null,
    // (F4) A linha do tempo do dia no tooltip: o que está acima é a tentativa
    // MAIS RECENTE; as anteriores aparecem aqui, para o operador ver que
    // "falhou 10:12, reexecutado 11:03, passou" sem abrir nada.
    ...(anteriores.length
      ? ['— tentativas anteriores —',
         ...anteriores.map(t =>
           `  #${t.attempt ?? '?'}: ${t.status ?? '—'} · `
           + `${horaLonga(t.inicio)} → ${horaLonga(t.fim)}`
           + (t.duration_seconds != null ? ` · ${duracaoCurta(t.duration_seconds)}` : ''))]
      : []),
    e.no_desenho ? null : 'esta etapa rodou mas NÃO está no desenho atual',
  ].filter(Boolean)
  return {
    status: e.status,
    rotulo: est.rotulo,
    anel: est.anel,
    dot: est.dot,
    animado: !!est.animado,
    resumo,
    titulo: linhas.join('\n'),
    pulada,
    tentativa: e.attempt ?? null,
    tentativas: anteriores,
  }
}

// ═══════════════════════════ (F5) a pausa por cima ══════════════════════════

/** Só as pausas PENDENTES, por etapa. As resolvidas ficam para o histórico do
 *  modal — pintar o nó com uma pausa já liberada seria contar o passado como
 *  presente. */
export function pausasPendentes(pausas: PausaApi[] | undefined): Map<string, PausaApi> {
  const m = new Map<string, PausaApi>()
  for (const p of pausas ?? []) {
    if ((p.estado ?? '').toUpperCase() !== 'PENDENTE') continue
    const k = chave(p.job_name)
    if (k) m.set(k, p)
  }
  return m
}

/** Aplica a pausa sobre a decoração da etapa.
 *
 *  ⚠️ **A pausa só SOBRESCREVE o status quando a etapa está de fato parada**
 *  (`aguardando_desde` preenchido). Uma pausa apenas marcada não muda a cor de
 *  nada: a etapa continua "sem execução" — que é a verdade — e ganha só o aviso
 *  de que vai parar ali. Pintar antes da hora seria a tela prometendo um estado
 *  que o motor ainda não tem. */
function comPausa(base: ExecNoEtapa, p: PausaApi): ExecNoEtapa {
  const aguardando = !!p.aguardando_desde
  const quem = p.solicitado_por ?? '?'
  const teto = p.teto_minutos != null ? `${p.teto_minutos} min` : 'padrão'
  // ⚠️ **NUNCA hora absoluta da pausa ao lado da hora da etapa.** Os carimbos
  // da pausa (`aguardando_desde`, `solicitado_em`) vêm do GETDATE() do SQL
  // Server; os horários das etapas vêm do relógio do factory — e no dev eles
  // divergem 3h (a decisão registrada no topo deste arquivo). A prova visual
  // mostrou o estrago: "em espera desde 22:57:54" logo abaixo de
  // "19:56:03 → 19:57:51", como se a espera fosse no futuro.
  // A tela passa a falar em DURAÇÃO (`parado_min`, calculado no banco), que é
  // verdadeira em qualquer relógio; a hora absoluta só aparece no tooltip e
  // rotulada como "registro" — o mesmo tratamento que `rotuloCorrida` já dá.
  const linhas = [
    aguardando
      ? `EM ESPERA${p.parado_min != null ? ` há ${p.parado_min} min` : ''}`
        + ` — aguardando liberação (registro ${horaLonga(p.aguardando_desde)})`
      : 'Pausa marcada: a etapa vai parar aqui quando chegar',
    `pedida por: ${quem}`,
    p.motivo ? `motivo: ${p.motivo}` : null,
    `teto de espera: ${teto}`,
    aguardando && p.verificacoes ? `verificações do portão: ${p.verificacoes}` : null,
  ].filter(Boolean).join('\n')
  if (!aguardando) {
    return { ...base, pausa: p, emEspera: false, titulo: `${base.titulo}\n— ${linhas}` }
  }
  const est = estiloStatus('EM_ESPERA')
  return {
    ...base,
    status: 'EM_ESPERA',
    rotulo: est.rotulo,
    anel: est.anel,
    dot: est.dot,
    animado: !!est.animado,
    resumo: p.parado_min != null
      ? `em espera há ${p.parado_min} min`
      : 'aguardando liberação',
    titulo: `${p.job_name}\n${linhas}`,
    pausa: p,
    emEspera: true,
  }
}

export function construirCamada(
  etapas: EtapaExecucaoApi[], pausas?: PausaApi[],
): CamadaExecucao {
  const porJob = new Map<string, EtapaExecucaoApi>()
  const noPorJob = new Map<string, ExecNoEtapa>()
  for (const e of etapas) {
    const k = chave(e.job_name)
    if (!k) continue
    // (F4) Desempate por TENTATIVA, não por ordem de chegada. O servidor já
    // entrega uma linha por etapa (a mais recente), mas o "primeiro que
    // chegar vence" desta função era, antes da F4, o que faria a tela pintar
    // a tentativa que FALHOU depois de o operador já ter reexecutado e
    // passado. A regra fica explícita nos dois lados, não implícita em um.
    const atual = porJob.get(k)
    if (atual && (atual.attempt ?? 0) >= (e.attempt ?? 0)) continue
    porJob.set(k, e)
    noPorJob.set(k, decorarEtapa(e))
  }
  const pausaPorJob = pausasPendentes(pausas)
  for (const [k, p] of pausaPorJob) {
    const base = noPorJob.get(k)
    // Pausa numa etapa que nem está no desenho (etapa renomeada entre o pedido
    // e agora): não há nó para pintar — a pausa continua existindo e aparece
    // no painel de pausas, que lista pela API e não pelo canvas.
    if (base) noPorJob.set(k, comPausa(base, p))
  }
  return { porJob, noPorJob, pausaPorJob }
}

// ═══════════════════════ o caminho realmente percorrido ═════════════════════
// "o caminho realmente percorrido em destaque (ramos de decisão não tomados
// ficam apagados)" — §3. A regra é derivada do STATUS das pontas, nunca de uma
// releitura da condição da decisão: o que a tela mostra é o que o banco
// registrou, não o que o desenho prometia.
export type EstadoAresta = 'percorrida' | 'nao_tomada' | 'neutra'

export function estadoAresta(
  source: string, target: string, c: CamadaExecucao,
): EstadoAresta {
  const a = c.porJob.get(chave(source))
  const b = c.porJob.get(chave(target))
  // Uma das pontas PULADA ⇒ a ligação não foi percorrida. É o ramo não tomado
  // da decisão (e a cauda dele, que o Airflow também pula).
  if (ehPulada(a?.status) || ehPulada(b?.status)) return 'nao_tomada'
  if (ehTerminalOk(a?.status) && ehTerminalOk(b?.status)) return 'percorrida'
  // Sem informação nas duas pontas (execução ausente, etapa que ainda não
  // começou): NEUTRA. Nunca "não tomada" — não saber não é o mesmo que negar.
  return 'neutra'
}

// ═════════════════════════════ resumo do dia ════════════════════════════════

export interface ResumoExecucao {
  total: number
  sucesso: number
  falha: number
  executando: number
  /** SKIPPED — conta em separado de propósito: não é sucesso nem falha. */
  pulado: number
  semExecucao: number
  /** qualquer outro status cru que a telemetria tenha gravado */
  outros: number
  foraDoDesenho: number
  /** (F5) etapas PARADAS no portão agora */
  emEspera: number
  /** (F5) pausas pedidas cuja etapa ainda não chegou ao portão */
  pausaMarcada: number
}

export function resumoExecucao(
  etapas: EtapaExecucaoApi[], pausas?: PausaApi[],
): ResumoExecucao {
  const r: ResumoExecucao = {
    total: etapas.length, sucesso: 0, falha: 0, executando: 0,
    pulado: 0, semExecucao: 0, outros: 0, foraDoDesenho: 0,
    emEspera: 0, pausaMarcada: 0,
  }
  for (const p of pausasPendentes(pausas).values()) {
    if (p.aguardando_desde) r.emEspera += 1
    else r.pausaMarcada += 1
  }
  for (const e of etapas) {
    if (!e.no_desenho) r.foraDoDesenho += 1
    const s = (e.status ?? '').trim().toUpperCase()
    if (!s) { r.semExecucao += 1; continue }
    if (s === 'SUCCESS') r.sucesso += 1
    else if (s === 'FAILED') r.falha += 1
    else if (s === 'RUNNING') r.executando += 1
    else if (s === 'SKIPPED') r.pulado += 1
    else r.outros += 1
  }
  return r
}

// ═══════════════════ janela do pipeline — DERIVADA DAS ETAPAS ═══════════════

export interface JanelaExecucao {
  inicio: string | null
  fim: string | null
  segundos: number | null
  /** alguma etapa começou e ainda não terminou */
  emAndamento: boolean
}

/** min(início) / max(fim) das ETAPAS — ver a decisão registrada no topo do
 *  arquivo. Comparação lexicográfica: 'YYYY-MM-DD HH:MM:SS' ordena igual ao
 *  tempo, e comparar string evita reinterpretar fuso no caminho. */
export function janelaDasEtapas(etapas: EtapaExecucaoApi[]): JanelaExecucao {
  let inicio: string | null = null
  let fim: string | null = null
  let emAndamento = false
  for (const e of etapas) {
    if (e.inicio && (inicio === null || e.inicio < inicio)) inicio = e.inicio
    if (e.fim && (fim === null || e.fim > fim)) fim = e.fim
    if (e.inicio && !e.fim) emAndamento = true
  }
  let segundos: number | null = null
  if (inicio && fim) {
    const a = Date.parse(inicio.replace(' ', 'T'))
    const b = Date.parse(fim.replace(' ', 'T'))
    if (Number.isFinite(a) && Number.isFinite(b) && b >= a) {
      segundos = Math.round((b - a) / 1000)
    }
  }
  return { inicio, fim, segundos, emAndamento }
}

// ════════════════════════════ o "vazio" explicado ═══════════════════════════
// `razao` vem do vocabulário FECHADO do serviço de identidade — a tela traduz,
// nunca inventa. Motivo desconhecido cai no texto genérico com o código cru.
const RAZOES: Record<string, string> = {
  sem_execucao_na_data:
    'Nenhuma execução deste pipeline nesta data de referência. O canvas mostra '
    + 'o desenho atual, com todas as etapas neutras.',
  sem_etapas_registradas:
    'A corrida existe, mas nenhuma etapa registrou telemetria nesta execução.',
  run_id_nao_traduzivel:
    'A corrida existe, mas não foi possível traduzir o identificador dela para '
    + 'a chave da telemetria (o Airflow não respondeu).',
  sem_dag_run_correspondente:
    'A corrida está registrada, mas o Airflow não tem mais o dag_run '
    + 'correspondente (run expurgado ou DAG recriada).',
  sem_execucao_para_ts:
    'As etapas foram lidas, mas nenhuma corrida do pipeline casou com esta '
    + 'execução — falta o lado do registro de pipeline.',
  migration_067_pendente:
    'migration 067 pendente neste ambiente — a resposta veio por aproximação '
    + 'sobre a telemetria das etapas.',
  airflow_indisponivel:
    'O Airflow não respondeu; sem ele não dá para fechar a identidade da '
    + 'corrida. Nada foi escondido — o que falta é dito.',
  ambiguo:
    'Há mais de uma corrida nesta data e nenhuma pôde ser escolhida com '
    + 'segurança.',
}

export function textoRazao(razao: string | null | undefined): string {
  const r = (razao ?? '').trim()
  if (!r) return 'Sem execução para mostrar nesta data.'
  return RAZOES[r] ?? `Sem execução para mostrar nesta data (motivo: ${r}).`
}

/** Rótulo curto de uma corrida candidata (lista do aviso de ambiguidade).
 *
 *  ⚠️ O horário aqui é o do REGISTRO da corrida (`etl_pipeline_execucao`), não
 *  o das etapas — daí a palavra "registro" no texto, e o rodapé do bloco que
 *  explica a diferença. Ele entra porque é a única coisa que distingue duas
 *  corridas do mesmo dia disparadas pela mesma origem; ele NÃO se mistura com
 *  a linha do tempo do canvas, que continua saindo só das etapas (ver a
 *  decisão registrada no topo deste arquivo). */
export function rotuloCorrida(c: CorridaApi): string {
  const partes = [
    c.status ?? 'status ?',
    c.inicio ? `registro ${horaLonga(c.inicio)}` : null,
    c.disparado_por ? `por ${c.disparado_por}` : null,
    // Uma corrida APOSENTADA por um rerun com cascata tem o mesmo status e o
    // mesmo horário de qualquer outra — e não conta mais como sucesso do dia.
    // Sem esta marca, o operador escolhia entre duas linhas indistinguíveis.
    c.substituida_em ? 'substituída por rerun' : null,
  ].filter(Boolean)
  return partes.join(' · ')
}

/** Uma corrida aposentada por rerun com cascata? (o carimbo `substituida_em`
 *  da migration 078). Serve à tela para não tratá-la como a corrida viva. */
export function corridaSubstituida(c: CorridaApi | null | undefined): boolean {
  return !!(c?.substituida_em ?? null)
}
