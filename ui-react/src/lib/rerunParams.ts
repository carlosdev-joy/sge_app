// Parâmetros DataStage na REEXECUÇÃO — lado do front (F5 da spec
// docs/spec-parametros-job-datastage.md). Tipos do contrato da prévia
// (`GET /pipelines/{p}/rerun/previa` → `parametros`) e as funções puras que o
// modal usa para decidir O QUE enviar. Sem React (a regra
// react-refresh/only-export-components não deixa helper exportado em arquivo de
// componente) — exercitado pela bancada tests/js/ds_params_harness.cjs.

export interface ItemParametroRerun {
  param_name: string
  param_type: string
  param_source: string
  fonte: 'etapa' | 'pipeline' | string
  /** default do pipeline: só vale se o job declarar o nome */
  condicional: boolean
  valor_efetivo: string | null
  descricao: string
  editavel: boolean
}

export interface ParametrosRerunEtapa {
  job_name: string
  itens: ItemParametroRerun[]
}

export interface OverrideRerun {
  job_name: string
  param_name: string
  param_value: string
}

/** Chave do estado "o que o operador digitou" — por etapa e parâmetro. */
export function chaveOverride(job: string, param: string): string {
  return `${job}::${param}`
}

/** As sobreposições a enviar: só o que foi digitado, difere do efetivo e é
 *  editável (Encrypted nunca). */
export function overridesParaEnviar(
  parametros: ParametrosRerunEtapa[], valores: Record<string, string>,
): OverrideRerun[] {
  const saida: OverrideRerun[] = []
  for (const e of parametros) {
    for (const it of e.itens) {
      if (!it.editavel) continue
      const v = valores[chaveOverride(e.job_name, it.param_name)]
      if (v === undefined || v === '' || v === (it.valor_efetivo ?? '')) continue
      saida.push({ job_name: e.job_name, param_name: it.param_name, param_value: v })
    }
  }
  return saida
}
