// Parâmetros de execução dos jobs DataStage — lado do front (F3 da spec
// docs/spec-parametros-job-datastage.md).
//
// O que mora aqui: o vocabulário (tipos, origens, âncoras), as réguas de
// validação que ESPELHAM api/services/job_params.py (a API é a fonte da
// verdade — aqui só se evita o 422 e se mostra a mensagem na hora) e a
// conversão entre o DRAFT do editor (tudo string, como o usuário digita) e o
// contrato da API. Sem cálculo de data: a prévia ("com a referência X o valor
// seria Y") vem do servidor (POST /pipelines/jobs/params/preview) — o
// TypeScript NÃO reimplementa o cálculo (decisão da spec §3).
//
// Módulo PURO (sem React) — exercitado pela bancada tests/js/ds_params_harness.cjs.
//
// ⚠️ Regex sempre como LITERAL `/…/`: uma string com escape duplo (`'\\d'`)
// nunca casa e passa tsc + lint + build (gotcha do repo).

export const DS_PARAM_TYPES = [
  'String', 'Integer', 'Float', 'Date', 'Time', 'Timestamp', 'Pathname', 'List', 'Encrypted',
] as const
export type DsParamType = typeof DS_PARAM_TYPES[number]

export const DS_PARAM_SOURCES = [
  { value: 'fixo', label: 'Valor fixo' },
  { value: 'data_referencia', label: 'Data de referência' },
  { value: 'data_logica', label: 'Data lógica (Airflow)' },
  { value: 'data_execucao', label: 'Data da execução' },
  { value: 'run_id', label: 'Run id da corrida' },
] as const
export type DsParamSource = typeof DS_PARAM_SOURCES[number]['value']

export const DS_SOURCES_DATA: readonly string[] = ['data_referencia', 'data_logica', 'data_execucao']
export const DS_TIPOS_COM_DATA: readonly string[] = ['String', 'Date', 'Timestamp']

export const DS_PARAM_ANCORAS = [
  { value: '', label: 'sem âncora' },
  { value: 'inicio_mes', label: 'início do mês' },
  { value: 'fim_mes', label: 'fim do mês' },
  { value: 'inicio_trimestre', label: 'início do trimestre' },
  { value: 'fim_trimestre', label: 'fim do trimestre' },
  { value: 'inicio_ano', label: 'início do ano' },
  { value: 'fim_ano', label: 'fim do ano' },
  { value: 'inicio_semana', label: 'segunda da semana' },
  { value: 'fim_semana', label: 'domingo da semana' },
] as const

export const DS_FORMATOS_SUGERIDOS = [
  '%Y-%m-%d', '%Y%m%d', '%d/%m/%Y', '%Y-%m', '%Y%m', '%Y-%m-%d %H:%M:%S',
]

// Sentinela da API: no GET, o valor Encrypted vem como `***` (+ tem_valor);
// no save, `***` manda preservar o token gravado.
export const DS_ENCRYPTED_MASCARA = '***'
export const DS_LIMITE_NOME = 128
export const DS_LIMITE_FORMATO = 40
export const DS_LIMITE_MESES = 120
export const DS_LIMITE_DIAS = 3660

export const DS_PARAM_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$/
export const DS_FORMATO_RE = /^(?:%[YmdyHMS]|[-/._: ])+$/
const DS_INTEIRO_RE = /^-?\d+$/
const DS_VALOR_FIXO_RE: Record<string, RegExp> = {
  Integer: /^-?\d+$/,
  Float: /^-?\d+(?:\.\d+)?$/,
  Date: /^\d{4}-\d{2}-\d{2}$/,
  Time: /^\d{2}:\d{2}:\d{2}$/,
  Timestamp: /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
  Pathname: /^\/[^\s'"]+$/,
}

// ── Draft do editor × contrato da API ───────────────────────────────────────

// Linha do editor. storedproc usa só nome/tipo/valor; datastage usa o resto.
// Tudo string (é o que o input entrega); a conversão para a API é aqui.
export interface JobParam {
  id?: string
  param_name: string
  param_type: string
  param_value: string
  param_source?: string
  param_offset_meses?: string
  param_ancora?: string
  param_offset_dias?: string
  param_formato?: string
  // Encrypted com token gravado: valor vazio no draft = "manter".
  tem_valor?: boolean
}

export interface JobParamApi {
  param_name: string
  param_type: string
  param_value: string | null
  param_order?: number
  param_source?: string
  param_offset_meses?: number | null
  param_ancora?: string | null
  param_offset_dias?: number | null
  param_formato?: string | null
  tem_valor?: boolean
}

export function ehOrigemData(origem?: string | null): boolean {
  return DS_SOURCES_DATA.includes(origem ?? '')
}

// GET → draft (vale para storedproc e datastage: os campos extras chegam
// 'fixo'/null no storedproc e não atrapalham). Encrypted: o `***` do GET vira
// campo vazio com tem_valor — o usuário só digita para TROCAR.
export function paramsFromApi(items?: JobParamApi[] | null): JobParam[] {
  return (items ?? []).map((p, i) => {
    const encrypted = p.param_type === 'Encrypted'
    const temValor = encrypted ? !!(p.tem_valor ?? (p.param_value && p.param_value !== '')) : undefined
    return {
      id: `p_${i}_${p.param_name}`,
      param_name: p.param_name,
      param_type: p.param_type,
      param_value: encrypted ? '' : (p.param_value ?? ''),
      param_source: p.param_source ?? 'fixo',
      param_offset_meses: p.param_offset_meses == null ? '' : String(p.param_offset_meses),
      param_ancora: p.param_ancora ?? '',
      param_offset_dias: p.param_offset_dias == null ? '' : String(p.param_offset_dias),
      param_formato: p.param_formato ?? '',
      ...(encrypted ? { tem_valor: temValor } : {}),
    }
  })
}

// storedproc: byte a byte o que a tela sempre mandou (nome/tipo/valor).
export function storedprocParamsToApi(params: JobParam[]): JobParamApi[] {
  return params
    .filter(p => p.param_name.trim())
    .map(p => ({ param_name: p.param_name.trim(), param_type: p.param_type, param_value: p.param_value }))
}

function inteiroOuNulo(v?: string): number | null {
  const s = (v ?? '').trim()
  if (!s) return null
  const n = parseInt(s, 10)
  return Number.isFinite(n) ? n : null
}

// datastage: origem SEMPRE (a API a exige sem default — achado da revisão da
// F1), cálculo só com origem de data (CHECK da migration 107), Encrypted vazio
// com token gravado → `***` (manter).
export function dsParamsToApi(params: JobParam[]): JobParamApi[] {
  return params
    .filter(p => p.param_name.trim())
    .map(p => {
      const origem = p.param_source || 'fixo'
      const data = ehOrigemData(origem)
      let valor: string | null = p.param_value
      if (origem !== 'fixo') valor = null
      else if (p.param_type === 'Encrypted' && !p.param_value && p.tem_valor) valor = DS_ENCRYPTED_MASCARA
      return {
        param_name: p.param_name.trim(),
        param_type: p.param_type,
        param_source: origem,
        param_value: valor,
        param_offset_meses: data ? inteiroOuNulo(p.param_offset_meses) : null,
        param_ancora: data ? ((p.param_ancora ?? '').trim() || null) : null,
        param_offset_dias: data ? inteiroOuNulo(p.param_offset_dias) : null,
        param_formato: data ? ((p.param_formato ?? '').trim() || null) : null,
      }
    })
}

// Despacho por tipo de etapa — o que vai na chave `params` do save.
export function paramsToApi(jobType: string, params: JobParam[]): JobParamApi[] {
  if (jobType === 'storedproc') return storedprocParamsToApi(params)
  if (jobType === 'datastage') return dsParamsToApi(params)
  return []
}

// Itens para a PRÉVIA: os mesmos da API, mas o segredo NUNCA sai para a prévia
// (ela devolve `***` de qualquer forma) — manda um marcador no lugar.
export function previewItens(params: JobParam[]): JobParamApi[] {
  return dsParamsToApi(params).map(p => (
    p.param_type === 'Encrypted' && p.param_source === 'fixo'
      ? { ...p, param_value: p.param_value ? 'x' : '' }
      : p
  ))
}

// ── Validação (espelho de normalizar_item/normalizar_lista da API) ──────────

function inteiroNaFaixa(v: string | undefined, rotulo: string, limite: number, erros: string[]) {
  const s = (v ?? '').trim()
  if (!s) return
  if (!DS_INTEIRO_RE.test(s)) { erros.push(`${rotulo} inválido — informe um inteiro`); return }
  if (Math.abs(parseInt(s, 10)) > limite) erros.push(`${rotulo} fora da faixa ±${limite}`)
}

export function dsParamErrors(params: JobParam[]): string[] {
  const erros: string[] = []
  const vistos = new Set<string>()
  params.forEach((p, i) => {
    const nome = p.param_name.trim()
    const rotulo = nome ? `Parâmetro "${nome}"` : `Parâmetro #${i + 1}`
    // Linha totalmente vazia = linha do editor ainda não preenchida (a API a ignora).
    if (!nome && !(p.param_value ?? '').trim()) return
    if (!nome || !DS_PARAM_NAME_RE.test(nome)) {
      erros.push(`${rotulo}: nome inválido — letras/números/_ e no máximo um ponto (PSet.Param)`)
    } else if (nome.length > DS_LIMITE_NOME) {
      erros.push(`${rotulo}: nome com ${nome.length} caracteres — máximo ${DS_LIMITE_NOME}`)
    }
    if (!(DS_PARAM_TYPES as readonly string[]).includes(p.param_type)) {
      erros.push(`${rotulo}: tipo inválido`)
    }
    const origem = p.param_source || ''
    if (!origem || !DS_PARAM_SOURCES.some(s => s.value === origem)) {
      erros.push(`${rotulo}: escolha a origem do valor`)
      return
    }
    if (ehOrigemData(origem)) {
      if (!DS_TIPOS_COM_DATA.includes(p.param_type)) {
        erros.push(`${rotulo}: origem de data só com tipo String, Date ou Timestamp`)
      }
      inteiroNaFaixa(p.param_offset_meses, `${rotulo}: meses`, DS_LIMITE_MESES, erros)
      inteiroNaFaixa(p.param_offset_dias, `${rotulo}: dias`, DS_LIMITE_DIAS, erros)
      const ancora = (p.param_ancora ?? '').trim()
      if (ancora && !DS_PARAM_ANCORAS.some(a => a.value === ancora)) erros.push(`${rotulo}: âncora inválida`)
      const formato = (p.param_formato ?? '').trim()
      if (formato && !DS_FORMATO_RE.test(formato)) {
        erros.push(`${rotulo}: formato inválido — só %Y %m %d %y %H %M %S e separadores - / . _ :`)
      } else if (formato.length > DS_LIMITE_FORMATO) {
        erros.push(`${rotulo}: formato com ${formato.length} caracteres — máximo ${DS_LIMITE_FORMATO}`)
      }
    } else if (origem === 'run_id') {
      if (p.param_type !== 'String') erros.push(`${rotulo}: origem run_id só com tipo String`)
    } else {
      const valor = p.param_value ?? ''
      if (p.param_type === 'Encrypted') {
        if (!valor && !p.tem_valor) erros.push(`${rotulo}: informe o valor (Encrypted)`)
      } else if (!valor && p.param_type !== 'String') {
        erros.push(`${rotulo}: valor obrigatório para origem fixa`)
      } else if (/[\r\n]/.test(valor)) {
        erros.push(`${rotulo}: valor não pode ter quebra de linha`)
      } else if (DS_VALOR_FIXO_RE[p.param_type] && !DS_VALOR_FIXO_RE[p.param_type].test(valor)) {
        erros.push(`${rotulo}: "${valor}" não é um ${p.param_type} válido`)
      }
    }
    // Duplicata por CAIXA EXATA: o DataStage distingue pData de pdata.
    if (nome) {
      if (vistos.has(nome)) erros.push(`${rotulo}: duplicado`)
      vistos.add(nome)
    }
  })
  return erros
}
