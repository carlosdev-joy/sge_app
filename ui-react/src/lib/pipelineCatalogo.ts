import { dsParamsToApi, paramsFromApi, type JobParam, type JobParamApi } from './dsParams'

export interface CatalogoMeta {
  param_destino: 'datastage' | 'orquestra'
  param_procedencia: 'manual' | 'datastage'
  param_import_project: string | null
  param_import_job: string | null
  param_descricao: string | null
}
export type CatalogoParam = JobParam & CatalogoMeta
export type CatalogoApi = JobParamApi & CatalogoMeta
export type Importado = CatalogoApi & { aviso: string | null }
export const metaManual = (destino: CatalogoMeta['param_destino']): CatalogoMeta => ({
  param_destino: destino, param_procedencia: 'manual', param_import_project: null,
  param_import_job: null, param_descricao: null,
})

export function catalogoFromApi(rows: CatalogoApi[] = []): CatalogoParam[] {
  return paramsFromApi(rows).map((p, i) => ({
    ...p, param_destino: rows[i].param_destino ?? 'datastage',
    param_procedencia: rows[i].param_procedencia ?? 'manual',
    param_import_project: rows[i].param_import_project ?? null,
    param_import_job: rows[i].param_import_job ?? null,
    param_descricao: rows[i].param_descricao ?? null,
  }))
}

export function catalogoToApi(rows: CatalogoParam[]): CatalogoApi[] {
  return rows.filter(p => p.param_name.trim()).map(p => ({
    ...dsParamsToApi([p])[0], param_destino: p.param_destino, param_procedencia: p.param_procedencia,
    param_import_project: p.param_import_project, param_import_job: p.param_import_job,
    param_descricao: p.param_descricao,
  }))
}

export function atualizarGrupo(atual: CatalogoParam[], destino: CatalogoMeta['param_destino'], rows: JobParam[]): CatalogoParam[] {
  const anteriores = atual.filter(p => p.param_destino === destino)
  return [...atual.filter(p => p.param_destino !== destino), ...rows.map(p => {
    const anterior = anteriores.find(a => p.id ? a.id === p.id : a.param_name === p.param_name)
    return { ...metaManual(destino), ...anterior, ...p, param_destino: destino }
  })]
}

export function legendaParametro(p?: Pick<JobParam, 'param_type' | 'param_value' | 'param_source'>): string {
  if (!p) return 'Selecione um parâmetro para consultar seu valor.'
  if (p.param_type === 'Encrypted') return 'Valor protegido — nunca exibido.'
  if (p.param_source && p.param_source !== 'fixo') return 'Calculado na execução.'
  return p.param_value || 'Valor vazio.'
}

export function aplicarImportacao(atual: CatalogoParam[], candidatos: Importado[], escolhidos: Record<string, number>, substituir: Record<string, boolean>) {
  const selecionados = Object.entries(escolhidos).filter(([, i]) => i >= 0)
  const erros: string[] = []
  const novos: CatalogoParam[] = []
  for (const [nome, i] of selecionados) {
    const p = candidatos[i]
    if (!p || p.param_name !== nome) { erros.push('A seleção da prévia ficou inválida. Consulte novamente.'); continue }
    if (atual.some(a => a.param_name.trim() === nome) && !substituir[nome]) {
      erros.push(`Confirme a substituição de ${nome} ou mantenha o valor atual.`); continue
    }
    novos.push(...catalogoFromApi([p]).map(x => ({ ...x, id: `import_${nome}` })))
  }
  if (erros.length) return { params: atual, erros }
  const nomes = new Set(novos.map(p => p.param_name))
  return { params: [...atual.filter(p => !nomes.has(p.param_name.trim())), ...novos], erros }
}

export function erroCatalogo(error: unknown): string {
  const e = error as { detail?: { errors?: unknown }; message?: string }
  return Array.isArray(e?.detail?.errors) ? e.detail.errors.join('; ') : e?.message || 'Não foi possível concluir. Tente novamente.'
}
