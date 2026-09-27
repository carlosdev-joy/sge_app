import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { aplicarImportacao, erroCatalogo, legendaParametro, type CatalogoParam, type Importado } from '../../lib/pipelineCatalogo'
import { Button } from '../ui/Button'
import { Textarea } from '../ui/Input'

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
  const nomes = [...new Set(previa?.parametros.map(p => p.param_name))]
  function aplicar() {
    const r = aplicarImportacao(params, previa?.parametros ?? [], escolhidos, substituir)
    if (r.erros.length) { setErro(r.erros.join(' ')); return }
    onChange(r.params); setPrevia(null); setErro('')
  }
  return <section className="space-y-3 border-t border-edge pt-4">
    <h3 className="text-sm font-semibold text-ink">Importar do DataStage</h3>
    <p className="text-sm text-dim">Projeto: <strong className="text-ink">{project || 'não selecionado'}</strong>. Consulte os jobs que declaram os parâmetros desejados. Nenhum job será executado.</p>
    <Textarea label="Jobs de origem" value={jobs} disabled={consulta.isPending} rows={2}
      onChange={e => { setJobs(e.target.value); setPrevia(null); setErro('') }}
      ajuda="Até 5 jobs, um por linha. A prévia não altera o pipeline." />
    <Button type="button" variant="secondary" disabled={!project || !jobs.trim() || consulta.isPending}
      onClick={() => consulta.mutate()}>{consulta.isPending ? 'Consultando parâmetros…' : 'Consultar parâmetros'}</Button>
    {consulta.isPending && <p role="status" className="text-sm text-dim">A consulta pode levar até 45 segundos.</p>}
    {erro && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{erro}</p>}
    {previa && <div className="space-y-4" aria-label="Prévia da importação">
      {previa.avisos.map((aviso, i) => <p key={i} className="text-sm text-amber-800 dark:text-amber-200">{aviso}</p>)}
      {!nomes.length && <p role="status" className="text-sm text-dim">Nenhum parâmetro compatível encontrado. Confira os jobs ou adicione manualmente.</p>}
      {nomes.map(nome => {
        const existe = params.some(p => p.param_name.trim() === nome)
        const candidatos = previa.parametros.map((p, i) => ({ p, i })).filter(({ p }) => p.param_name === nome)
        return <fieldset key={nome} className="min-w-0 space-y-2 border-t border-edge pt-3">
          <legend className="max-w-full break-all text-sm font-semibold text-ink">{nome}</legend>
          {candidatos.length > 1 && <p className="text-sm text-dim">Há mais de uma origem. Escolha uma para este nome.</p>}
          <label className="flex min-h-9 items-center gap-2 text-sm text-dim"><input type="radio" name={`import-${nome}`}
            checked={(escolhidos[nome] ?? -1) === -1} onChange={() => setEscolhidos({ ...escolhidos, [nome]: -1 })} />
            {existe ? 'Manter parâmetro atual' : 'Não importar'}</label>
          {candidatos.map(({ p, i }) => <label key={i} className="flex min-h-11 items-start gap-2 text-sm text-ink">
            <input className="mt-1" type="radio" name={`import-${nome}`} checked={escolhidos[nome] === i}
              onChange={() => setEscolhidos({ ...escolhidos, [nome]: i })} />
            <span className="min-w-0 break-all">{p.param_import_job} · {p.param_type}<span className="block text-dim">{legendaParametro({ ...p, param_value: p.param_value ?? '' })}</span>
              {p.aviso && <span className="block text-amber-800 dark:text-amber-200">{p.aviso}</span>}</span>
          </label>)}
          {existe && (escolhidos[nome] ?? -1) >= 0 && <label className="flex min-h-11 items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={!!substituir[nome]} onChange={e => setSubstituir({ ...substituir, [nome]: e.target.checked })} />
            Substituir {nome} no formulário, incluindo tipo e valor.</label>}
        </fieldset>
      })}
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={!Object.values(escolhidos).some(i => i >= 0)} onClick={aplicar}>Aplicar seleção ao formulário</Button>
        <Button type="button" variant="secondary" onClick={() => { setPrevia(null); setErro('') }}>Descartar prévia</Button>
      </div>
      <p className="text-xs text-dim">Os valores só serão gravados ao salvar o pipeline. Defaults importados não são sincronizados automaticamente.</p>
    </div>}
  </section>
}
