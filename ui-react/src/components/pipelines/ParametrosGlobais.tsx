import { useState } from 'react'
import { atualizarGrupo, type CatalogoParam } from '../../lib/pipelineCatalogo'
import { DS_PARAM_TYPES, DS_PARAM_SOURCES } from '../../lib/dsParams'
import { ParametrosPipelineSecao } from './ParametrosPipeline'
import { ImportarParametros } from './ImportarParametros'
import { ParametroCatalogoSelect } from './ParametroCatalogoSelect'

function TabelaParams({ params, onChange, titulo, destino }: {
  params: CatalogoParam[]
  onChange: (rows: CatalogoParam[]) => void
  titulo: string
  destino: 'datastage' | 'orquestra'
}) {
  const visiveis = params.filter(p => p.param_type !== 'Encrypted' && p.param_name.trim())
  if (visiveis.length === 0) return null

  function update(idx: number, patch: Partial<CatalogoParam>) {
    const copia = [...params]
    const real = params.findIndex((_, i) => params.filter(p => p.param_type !== 'Encrypted' && p.param_name.trim())[idx] === params[i])
    if (real === -1) return
    copia[real] = { ...copia[real], ...patch }
    onChange(copia)
  }

  return (
    <section className="space-y-1.5">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold text-dim uppercase tracking-wide">{titulo}</h3>
        <span className="rounded-full border border-edge bg-canvas px-1.5 py-0 text-[10px] text-dim">{visiveis.length}</span>
      </div>
      <div className="overflow-x-auto rounded-md border border-edge">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-edge bg-panel/60">
              <th className="px-2 py-1.5 text-left text-dim font-medium">Parâmetro</th>
              <th className="w-24 px-2 py-1.5 text-left text-dim font-medium">Tipo</th>
              <th className="w-28 px-2 py-1.5 text-left text-dim font-medium">Origem</th>
              <th className="px-2 py-1.5 text-left text-dim font-medium">Valor / Cálculo</th>
            </tr>
          </thead>
          <tbody>
            {visiveis.map((p, idx) => {
              const origem = p.param_source || 'fixo'
              const ehData = ['data', 'data_inicial', 'data_final'].includes(origem)
              return (
                <tr key={p.id ?? idx} className="border-b border-edge/40 last:border-0 hover:bg-panel/40 transition-colors">
                  <td className="px-2 py-1">
                    <span className="font-mono text-ink">{p.param_name}</span>
                    {destino === 'datastage' && <span className="ml-1 text-[10px] text-dim/60">[DS]</span>}
                  </td>
                  <td className="px-2 py-1">
                    <select
                      value={p.param_type}
                      onChange={e => update(idx, { param_type: e.target.value })}
                      className="w-full rounded border border-edge bg-panel px-1 py-0.5 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
                    >
                      {(destino === 'datastage' ? DS_PARAM_TYPES : ['String', 'Integer', 'Float', 'Boolean', 'Date']).map(t =>
                        <option key={t}>{t}</option>
                      )}
                    </select>
                  </td>
                  <td className="px-2 py-1">
                    {destino === 'datastage' ? (
                      <select
                        value={origem}
                        onChange={e => update(idx, { param_source: e.target.value })}
                        className="w-full rounded border border-edge bg-panel px-1 py-0.5 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        {DS_PARAM_SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    ) : (
                      <span className="text-dim">fixo</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    {ehData ? (
                      <span className="text-dim italic text-[11px]">calculado na execução</span>
                    ) : origem === 'run_id' ? (
                      <span className="text-dim italic text-[11px]">run_id</span>
                    ) : (
                      <input
                        type="text"
                        value={p.param_value}
                        onChange={e => update(idx, { param_value: e.target.value })}
                        placeholder="valor padrão"
                        className="w-full rounded border border-edge bg-panel px-1.5 py-0.5 font-mono text-xs text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function ParametrosGlobais({ params, onChange, pipeline, project }: {
  params: CatalogoParam[]; onChange: (p: CatalogoParam[]) => void; pipeline?: string; project: string
}) {
  const [consulta, setConsulta] = useState('')
  const dsParams = params.filter(p => p.param_destino === 'datastage')
  const orqParams = params.filter(p => p.param_destino === 'orquestra')

  return <div className="space-y-4">
    <p className="text-sm text-dim">Parâmetros compartilhados por este pipeline. Valores definidos na etapa prevalecem sobre seus defaults.</p>

    {/* Tabela DataStage — exibe sem Encrypted */}
    <TabelaParams
      params={dsParams}
      onChange={rows => onChange(atualizarGrupo(params, 'datastage', rows))}
      titulo="Parâmetros DataStage"
      destino="datastage"
    />

    {/* Seção completa para edição avançada (Maestro, referência) — oculta quando há itens na tabela */}
    {dsParams.filter(p => p.param_type !== 'Encrypted' && p.param_name.trim()).length === 0 && (
      <ParametrosPipelineSecao
        params={dsParams}
        onChange={rows => onChange(atualizarGrupo(params, 'datastage', rows))}
        pipeline={pipeline}
      />
    )}

    {/* Tabela Orquestra — exibe sem Encrypted */}
    {orqParams.filter(p => p.param_type !== 'Encrypted' && p.param_name.trim()).length > 0 && (
      <TabelaParams
        params={orqParams}
        onChange={rows => onChange(atualizarGrupo(params, 'orquestra', rows))}
        titulo="Parâmetros Orquestra"
        destino="orquestra"
      />
    )}

    {params.some(p => p.param_name.trim()) && <ParametroCatalogoSelect params={params} value={consulta} onChange={setConsulta} />}
    <ImportarParametros key={project} project={project} params={params} onChange={onChange} />
  </div>
}
