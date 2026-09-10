// Seção "Parâmetros desta reexecução" do modal de rerun (F5 da spec
// docs/spec-parametros-job-datastage.md).
//
// Por etapa DataStage que vai rodar de novo, o servidor manda os parâmetros
// EFETIVOS (defaults do pipeline < etapa) com o valor que iria ao DataStage na
// referência da corrida. O operador pode trocar o valor SÓ nesta corrida —
// Encrypted não (mostra `***`, sem campo). Componente de apresentação: o
// estado (o que foi digitado) vive no modal, por chave `job param`.
import type { ReactNode } from 'react'
import { chaveOverride, overridesParaEnviar, type ParametrosRerunEtapa } from '../../lib/rerunParams'

const FONTE_LABEL: Record<string, string> = { etapa: 'etapa', pipeline: 'default do pipeline' }

export function ParametrosRerun({ parametros, valores, onChange, indisponiveis, cabecalho }: {
  parametros: ParametrosRerunEtapa[]
  valores: Record<string, string>
  onChange: (chave: string, valor: string) => void
  /** o servidor não conseguiu calcular (a prévia diz; o gesto segue sem sobreposição) */
  indisponiveis?: boolean
  cabecalho?: ReactNode
}) {
  if (indisponiveis) {
    return (
      <p className="text-[11px] leading-snug text-amber-700 dark:text-amber-400" data-parametros-rerun="indisponiveis">
        Não foi possível calcular os parâmetros das etapas — a reexecução segue com os valores cadastrados.
      </p>
    )
  }
  if (!parametros.length) return null
  const n = overridesParaEnviar(parametros, valores).length
  return (
    <div className="flex flex-col gap-2" data-parametros-rerun="lista" data-sobrepostos={n}>
      {cabecalho}
      {parametros.map(e => (
        <div key={e.job_name} className="rounded-lg border border-edge bg-canvas px-3 py-2" data-etapa-params={e.job_name}>
          <p className="mb-1 font-mono text-[11px] font-semibold text-ink">{e.job_name}</p>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-dim">
                <th className="pb-0.5 text-left font-medium">Parâmetro</th>
                <th className="pb-0.5 text-left font-medium">Valor nesta corrida</th>
                <th className="pb-0.5 text-left font-medium">Novo valor (só agora)</th>
              </tr>
            </thead>
            <tbody>
              {e.itens.map(it => {
                const chave = chaveOverride(e.job_name, it.param_name)
                const digitado = valores[chave] ?? ''
                const mudou = digitado !== '' && digitado !== (it.valor_efetivo ?? '')
                return (
                  <tr key={it.param_name} className="border-t border-edge/40 align-top" data-item-rerun={it.param_name}>
                    <td className="py-1 pr-2">
                      <span className="font-mono text-ink">{it.param_name}</span>
                      <span className="block text-[10px] text-dim">
                        {it.param_type} · {FONTE_LABEL[it.fonte] ?? it.fonte}
                        {it.condicional ? ' (se o job declarar)' : ''}
                      </span>
                    </td>
                    <td className="py-1 pr-2" title={it.descricao}>
                      <span className="font-mono text-ink" data-valor-efetivo={it.valor_efetivo ?? ''}>
                        {it.valor_efetivo ?? '—'}
                      </span>
                      {it.descricao && it.descricao !== 'fixo' && (
                        <span className="block text-[10px] text-dim/80">{it.descricao}</span>
                      )}
                    </td>
                    <td className="py-1">
                      {it.editavel ? (
                        <input
                          type="text"
                          value={digitado}
                          onChange={ev => onChange(chave, ev.target.value)}
                          placeholder="manter"
                          title={it.condicional
                            ? 'Default do pipeline: se o job não declarar este parâmetro, a etapa falha antes de disparar (a lista do job vem no erro)'
                            : 'Vale só nesta reexecução'}
                          data-override={it.param_name}
                          data-mudou={mudou ? '1' : '0'}
                          className={`w-full min-w-0 rounded-md border bg-panel px-2 py-1 font-mono text-[11px] text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 ${mudou ? 'border-amber-400 dark:border-amber-500' : 'border-edge'}`}
                        />
                      ) : (
                        <span className="text-[10px] text-dim" data-nao-editavel={it.param_name}>Encrypted — não sobrepõe</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
      {n > 0 && (
        <p className="text-[11px] leading-snug text-amber-700 dark:text-amber-400" data-aviso-sobreposicao>
          {n} valor(es) valem <strong>só nesta reexecução</strong>; a corrida agendada seguinte volta ao cadastro.
        </p>
      )}
    </div>
  )
}
