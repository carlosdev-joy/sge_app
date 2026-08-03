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
  /** hoje sempre null — a coluna existe e só passa a ser preenchida na F4. */
  attempt: number | null
  log_file: string | null
  host: string | null
}

export interface CorridaApi {
  run_id: string | null
  status: string | null
  inicio: string | null
  fim: string | null
  disparado_por: string | null
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

export interface PipelineExecucaoApi {
  pipeline_name: string
  data_referencia: string | null
  identidade: IdentidadeApi
  corrida: CorridaApi | null
  etapas: EtapaExecucaoApi[]
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
  /** tooltip completo (status, início, fim, duração, host, tentativa) */
  titulo: string
  pulada: boolean
}

export interface CamadaExecucao {
  /** job_name em casefold → etapa (colação CI do banco × dict case-sensitive
   *  do JS: é o incidente da PR #236 aplicado aqui). */
  porJob: Map<string, EtapaExecucaoApi>
  /** decorações prontas por nó, na mesma chave */
  noPorJob: Map<string, ExecNoEtapa>
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
    }
  }
  const ini = horaLonga(e.inicio)
  const fim = horaLonga(e.fim)
  const dur = e.duration_seconds != null ? duracaoCurta(e.duration_seconds) : null
  const resumo = [
    `${ini} → ${fim}`,
    dur,
  ].filter(Boolean).join(' · ')
  const linhas = [
    e.job_name,
    `status: ${e.status}${pulada ? ' (ramo não tomado — não é sucesso nem falha)' : ''}`,
    `início: ${e.inicio ?? '—'}`,
    `fim: ${e.fim ?? '—'}`,
    `duração: ${dur ?? '—'}`,
    e.attempt != null ? `tentativa: ${e.attempt}` : null,
    e.host ? `host: ${e.host}` : null,
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
  }
}

export function construirCamada(etapas: EtapaExecucaoApi[]): CamadaExecucao {
  const porJob = new Map<string, EtapaExecucaoApi>()
  const noPorJob = new Map<string, ExecNoEtapa>()
  for (const e of etapas) {
    const k = chave(e.job_name)
    if (!k || porJob.has(k)) continue
    porJob.set(k, e)
    noPorJob.set(k, decorarEtapa(e))
  }
  return { porJob, noPorJob }
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
}

export function resumoExecucao(etapas: EtapaExecucaoApi[]): ResumoExecucao {
  const r: ResumoExecucao = {
    total: etapas.length, sucesso: 0, falha: 0, executando: 0,
    pulado: 0, semExecucao: 0, outros: 0, foraDoDesenho: 0,
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
  ].filter(Boolean)
  return partes.join(' · ')
}
