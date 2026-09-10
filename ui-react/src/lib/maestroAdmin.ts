// Admin › Maestro — o lado puro (F3 da spec docs/spec-maestro-parametros.md):
// tipos dos endpoints /maestro/admin/*, o formulário do cenário (linhas da
// receita ↔ JSON da API, exemplos ↔ texto) e a régua local que espelha
// services/maestro.validar_cenario (a API é a fonte da verdade; aqui só se
// evita o 422 e se mostra a mensagem na hora).
//
// Exercitado pela bancada tests/js/ds_params_harness.cjs (seção 8).
import { DS_PARAM_NAME_RE, dsParamErrors, dsParamsToApi, type JobParam, type JobParamApi } from './dsParams'

export interface ReceitaApi { params: JobParamApi[]; exemplos: string[] }

export interface CenarioApi {
  id: number
  codigo: string
  titulo: string
  descricao: string
  receita: ReceitaApi
  ativo: boolean
  criado_em: string | null
  criado_por: string | null
  atualizado_em: string | null
  atualizado_por: string | null
}

export interface PedidoApi {
  id: number
  criado_em: string
  matricula: string
  pipeline_name: string | null
  job_name: string | null
  mensagem: string
  motivo: string | null
  tratado_em: string | null
  tratado_por: string | null
}

export interface ConfigMaestroApi {
  enabled: boolean
  ativo: boolean
  provedor: { provider: string; model: string; api_key_set: boolean }
  total_cenarios: number
  cenarios_ativos: number
  pedidos_abertos: number
  retencao_dias: number
}

export interface PreviaCenario { param_name: string; valor: string; descricao: string }

/** O formulário do modal: tudo string, como o usuário digita. */
export interface CenarioForm {
  codigo: string
  titulo: string
  descricao: string
  ativo: boolean
  linhas: JobParam[]
  exemplosTexto: string
}

export const CODIGO_RE = /^[a-z][a-z0-9_]{1,39}$/
/** Marcador da receita: o Maestro troca pelo nome real (`<DATA_INICIAL>`). */
export const MARCADOR_RE = /^<[A-Za-z_][A-Za-z0-9_]*>$/
export const LIMITE_TITULO = 120
export const LIMITE_DESCRICAO = 600
export const LIMITE_EXEMPLO = 200
export const MAX_EXEMPLOS = 10

let seq = 0
export function linhaVazia(): JobParam {
  return { id: `r_${++seq}`, param_name: '', param_type: 'Date', param_source: 'data_referencia',
           param_value: '', param_offset_meses: '', param_ancora: '', param_offset_dias: '', param_formato: '' }
}

export function cenarioVazio(): CenarioForm {
  return { codigo: '', titulo: '', descricao: '', ativo: true, linhas: [linhaVazia()], exemplosTexto: '' }
}

/** Da API para o formulário (o GET traz os params no contrato; aqui viram o
 *  draft do editor: números → string, null → ''). */
export function formDoCenario(c: CenarioApi): CenarioForm {
  const linhas: JobParam[] = (c.receita?.params ?? []).map(p => ({
    id: `r_${++seq}`,
    param_name: p.param_name ?? '',
    param_type: p.param_type ?? 'String',
    param_source: p.param_source ?? 'fixo',
    param_value: p.param_value ?? '',
    param_offset_meses: p.param_offset_meses == null ? '' : String(p.param_offset_meses),
    param_ancora: p.param_ancora ?? '',
    param_offset_dias: p.param_offset_dias == null ? '' : String(p.param_offset_dias),
    param_formato: p.param_formato ?? '',
  }))
  return { codigo: c.codigo, titulo: c.titulo, descricao: c.descricao, ativo: c.ativo,
           linhas: linhas.length ? linhas : [linhaVazia()], exemplosTexto: (c.receita?.exemplos ?? []).join('\n') }
}

/** Uma frase por linha; vazias e repetidas somem; no máximo MAX_EXEMPLOS
 *  (o excedente vira erro, não corte silencioso). */
export function exemplosDoTexto(texto: string): string[] {
  const saida: string[] = []
  for (const l of (texto ?? '').split('\n')) {
    const frase = l.trim()
    if (frase && !saida.includes(frase)) saida.push(frase)
  }
  return saida
}

/** Do formulário para o corpo do POST (a receita pelo mesmo conversor da
 *  etapa — `dsParamsToApi` —, que ignora linha vazia e só manda cálculo com
 *  origem de data; os marcadores passam como nomes). */
export function cenarioParaApi(f: CenarioForm) {
  // Encrypted vai SEM valor (a receita inteira entra no prompt do provedor).
  const params = dsParamsToApi(f.linhas.map(l => (l.param_type === 'Encrypted' ? { ...l, param_value: '', tem_valor: false } : l)))
    .map(p => (p.param_type === 'Encrypted' ? { ...p, param_value: null } : p))
  return {
    codigo: f.codigo.trim().toLowerCase(),
    titulo: f.titulo.trim(),
    descricao: f.descricao.trim(),
    ativo: f.ativo,
    receita: { params, exemplos: exemplosDoTexto(f.exemplosTexto) },
  }
}

/** Régua local (espelha validar_cenario): o que a API recusaria, dito na
 *  hora. A receita é validada com os marcadores trocados por nomes válidos —
 *  a régua das linhas é a do editor (`dsParamErrors`). */
export function errosDoCenario(f: CenarioForm): string[] {
  const erros: string[] = []
  const codigo = f.codigo.trim().toLowerCase()
  if (!CODIGO_RE.test(codigo)) erros.push('Código: letras minúsculas, números e _, de 2 a 40 caracteres, começando por letra')
  if (!f.titulo.trim()) erros.push('Título obrigatório')
  else if (f.titulo.trim().length > LIMITE_TITULO) erros.push(`Título com mais de ${LIMITE_TITULO} caracteres`)
  if (!f.descricao.trim()) erros.push('Descrição obrigatória — é o que o Maestro lê para reconhecer o cenário')
  else if (f.descricao.trim().length > LIMITE_DESCRICAO) erros.push(`Descrição com mais de ${LIMITE_DESCRICAO} caracteres`)
  const comNome = f.linhas.filter(l => l.param_name.trim() || l.param_value.trim())
  if (!comNome.length) erros.push('A receita precisa de pelo menos um parâmetro')
  // Marcador repetido é checado ANTES da troca por p_n (senão `<D>` duas
  // vezes passaria e o Maestro entregaria dois nomes iguais). Caixa exata.
  const vistos = new Set<string>()
  for (const l of comNome) {
    const nome = l.param_name.trim()
    if (nome && vistos.has(nome)) erros.push(`Marcador/nome repetido na receita: ${nome}`)
    vistos.add(nome)
  }
  const trocadas = comNome.map((l, i) => {
    const nome = l.param_name.trim()
    // Encrypted na receita nunca tem valor (o usuário digita na etapa): a
    // régua do editor exigiria um — aqui vale como "mantido".
    const base = l.param_type === 'Encrypted' ? { ...l, param_value: '', tem_valor: true } : l
    if (MARCADOR_RE.test(nome)) return { ...base, param_name: `p_${i + 1}` }
    if (nome && !DS_PARAM_NAME_RE.test(nome)) {
      erros.push(`Parâmetro "${nome}": use um marcador <NOME> (o Maestro troca pelo nome real) ou um nome válido`)
      return { ...base, param_name: `p_${i + 1}` }
    }
    return base
  })
  erros.push(...dsParamErrors(trocadas))
  const exemplos = exemplosDoTexto(f.exemplosTexto)
  if (exemplos.length > MAX_EXEMPLOS) erros.push(`No máximo ${MAX_EXEMPLOS} exemplos (uma frase por linha)`)
  for (const e of exemplos) if (e.length > LIMITE_EXEMPLO) erros.push(`Exemplo com mais de ${LIMITE_EXEMPLO} caracteres: "${e.slice(0, 30)}…"`)
  return erros
}

/** Mensagem legível dos erros dos endpoints /maestro/admin/*: 422 estruturado
 *  (`errors`), 409 (`mensagem`), 503 (texto), senão o padrão. */
export function mensagemErroAdmin(e: unknown, padrao: string): string {
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

export function migration110Pendente(e: unknown): boolean {
  const err = e as { status?: number; message?: string; detail?: unknown } | null
  const texto = typeof err?.detail === 'string' ? err.detail : (err?.message ?? '')
  return err?.status === 503 && /migration 110/i.test(texto)
}
