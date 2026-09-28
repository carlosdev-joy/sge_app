import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { aplicarImportacao, erroCatalogo, type CatalogoParam, type Importado } from '../../lib/pipelineCatalogo'
import { Button } from '../ui/Button'
import { Textarea } from '../ui/Input'

function legendaSemEncrypted(p: Importado): string {
  if (p.param_type === 'Encrypted') return ''
  if (p.param_source && p.param_source !== 'fixo') return 'Calculado na execução'
  return p.param_value ?? ''
}

export function ImportarParametros({ project, params, onChange }: {
  project: string; params: CatalogoParam[]; onChange: (p: CatalogoParam[]) => void
}) {
  const [jobs, setJobs] = useState('')
  const [previa, setPrevia] = useState<{ parametros: Importado[]; avisos: string[] } | null>(null)
  const [escolhidos, setEscolhidos] = useState<Record<string, number>>({})
  const [substituir, setSubstituir] = useState<Record<string, boolean>>({})
  const [erro, setErro] = useState('')

  const consulta = useMutation({
    mutationFn: () => apiFetch<{ parametros: Importado[]; avisos: string[] }>('/pipelines/parametros/importar-previa', {
      method: 'POST', body: JSON.stringify({ project_name: project, jobs: jobs.split(/[\n,;]+/).map(x => x.trim()).filter(Boolean) }),
    }),
    onMutate: () => { setPrevia(null); setErro(''); setEscolhidos({}); setSubstituir({}) },
    onSuccess: data => setPrevia(data),
    onError: e => setErro(erroCatalogo(e)),
  })

  // Filtra Encrypted da prévia — senha nunca deve aparecer em listagem
  const parametrosFiltrados = previa?.parametros.filter(p => p.param_type !== 'Encrypted') ?? []
  const nomes = [...new Set(parametrosFiltrados.map(p => p.param_name))]

  function aplicar() {
    // Aplica com escolhidos — params Encrypted ficam fora do escolhidos, não serão importados
    const r = aplicarImportacao(params, parametrosFiltrados, escolhidos, substituir)
    if (r.erros.length) { setErro(r.erros.join(' ')); return }
    onChange(r.params); setPrevia(null); setErro('')
  }

  return (
    <section className="space-y-3 border-t border-edge pt-4">
      <h3 className="text-sm font-semibold text-ink">Importar do DataStage</h3>
      <p className="text-sm text-dim">
        Projeto: <strong className="text-ink">{project || 'não selecionado'}</strong>. Consulte os jobs que declaram os parâmetros desejados. Nenhum job será executado.
      </p>
      <Textarea label="Jobs de origem" value={jobs} disabled={consulta.isPending} rows={2}
        onChange={e => { setJobs(e.target.value); setPrevia(null); setErro('') }}
        ajuda="Até 5 jobs, um por linha. A prévia não altera o pipeline." />
      <Button type="button" variant="secondary" disabled={!project || !jobs.trim() || consulta.isPending}
        onClick={() => consulta.mutate()}>
        {consulta.isPending ? 'Consultando parâmetros…' : 'Consultar parâmetros'}
      </Button>
      {consulta.isPending && <p role="status" className="text-sm text-dim">A consulta pode levar até 45 segundos.</p>}
      {erro && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{erro}</p>}

      {previa && (
        <div className="space-y-3" aria-label="Prévia da importação">
          {previa.avisos.map((aviso, i) => (
            <p key={i} className="text-xs text-amber-800 dark:text-amber-200">{aviso}</p>
          ))}
          {!nomes.length ? (
            <p role="status" className="text-sm text-dim">Nenhum parâmetro compatível encontrado (parâmetros Encrypted são excluídos). Confira os jobs ou adicione manualmente.</p>
          ) : (
            <div className="rounded-lg border border-edge bg-canvas/60 px-3 py-2 text-[12px]">
              <p className="mb-2 font-semibold text-ink">
                {nomes.length} parâmetro{nomes.length !== 1 ? 's' : ''} encontrado{nomes.length !== 1 ? 's' : ''}
                <span className="ml-1 font-normal text-dim">— marque os que deseja importar</span>
              </p>
              <ul className="flex flex-col gap-2">
                {nomes.map(nome => {
                  const candidatos = parametrosFiltrados.map((p, i) => ({ p, i })).filter(({ p }) => p.param_name === nome)
                  const selecionado = (escolhidos[nome] ?? -1) >= 0
                  const existe = params.some(p => p.param_name.trim() === nome)
                  // Quando há só um candidato, seleciona automaticamente ao marcar o checkbox
                  const idxAuto = candidatos.length === 1 ? candidatos[0].i : -1
                  return (
                    <li key={nome} className="flex flex-col gap-0.5" data-param-nome={nome}>
                      <label className="flex items-start gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          className="mt-0.5 accent-blue-500"
                          checked={selecionado}
                          onChange={e => {
                            const novo = e.target.checked ? (idxAuto >= 0 ? idxAuto : 0) : -1
                            setEscolhidos({ ...escolhidos, [nome]: novo })
                          }}
                        />
                        <span className="flex flex-col min-w-0">
                          <span className="font-mono font-semibold text-ink break-all">{nome}</span>
                          {/* Quando há múltiplos candidatos, exibe select; senão exibe info direto */}
                          {candidatos.length > 1 && selecionado ? (
                            <select
                              className="mt-0.5 rounded border border-edge bg-panel px-1.5 py-0.5 text-[11px] text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
                              value={escolhidos[nome] ?? candidatos[0].i}
                              onChange={e => setEscolhidos({ ...escolhidos, [nome]: Number(e.target.value) })}
                            >
                              {candidatos.map(({ p, i }) => (
                                <option key={i} value={i}>{p.param_import_job} · {p.param_type}</option>
                              ))}
                            </select>
                          ) : (
                            candidatos.slice(0, 1).map(({ p }) => (
                              <span key={p.param_name} className="text-dim">
                                {p.param_import_job} · {p.param_type}
                                {legendaSemEncrypted(p) && (
                                  <span className="ml-1 font-mono text-ink/70">{legendaSemEncrypted(p)}</span>
                                )}
                              </span>
                            ))
                          )}
                          {selecionado && existe && (
                            <label className="mt-0.5 flex items-center gap-1.5 text-dim cursor-pointer">
                              <input type="checkbox" className="accent-blue-500"
                                checked={!!substituir[nome]}
                                onChange={e => setSubstituir({ ...substituir, [nome]: e.target.checked })} />
                              Substituir valor existente
                            </label>
                          )}
                          {candidatos[0]?.p.aviso && (
                            <span className="text-amber-800 dark:text-amber-200">⚠ {candidatos[0].p.aviso}</span>
                          )}
                        </span>
                      </label>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={!Object.values(escolhidos).some(i => i >= 0)} onClick={aplicar}>
              Aplicar seleção ao formulário
            </Button>
            <Button type="button" variant="secondary" onClick={() => { setPrevia(null); setErro('') }}>
              Descartar prévia
            </Button>
          </div>
          <p className="text-xs text-dim">Os valores só serão gravados ao salvar o pipeline. Defaults importados não são sincronizados automaticamente.</p>
        </div>
      )}
    </section>
  )
}
