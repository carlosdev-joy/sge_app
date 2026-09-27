import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { catalogoFromApi, legendaParametro, type CatalogoApi } from '../../lib/pipelineCatalogo'
import { Input, Select } from '../ui/Input'
import { Button } from '../ui/Button'
import type { JobTypeFieldsValue } from './JobTypeFields'

export function VinculosParametros({ pipeline, value, onChange }: {
  pipeline?: string; value: JobTypeFieldsValue; onChange: (p: Partial<JobTypeFieldsValue>) => void
}) {
  const [alvo, setAlvo] = useState('')
  const [erro, setErro] = useState('')
  const cap = useQuery<{ vinculos_disponiveis: boolean }>({
    queryKey: ['param-vinculos-status'], queryFn: () => apiFetch('/pipelines/parametros/catalogo-status'),
    enabled: !!pipeline, staleTime: 30_000,
  })
  const q = useQuery<{ parametros: CatalogoApi[] }>({
    queryKey: ['pipeline-catalogo', pipeline],
    queryFn: () => apiFetch(`/pipelines/${encodeURIComponent(pipeline ?? '')}/parametros?parametros_versao=2`),
    enabled: !!pipeline && !!cap.data?.vinculos_disponiveis, staleTime: 0,
  })
  const refs = value.param_vinculos ?? {}
  const py = value.python
  const campo = py?.modo === 'arquivo' ? 'script_path' : py?.modo === 'codigo' ? 'destino_dir' : null
  const catalogo = catalogoFromApi(q.data?.parametros)
  const opcoes = catalogo.filter(p => (value.job_type === 'datastage' ? p.param_destino === 'datastage' : (['String', 'Pathname'].includes(p.param_type) && p.param_source === 'fixo')))
  if (!pipeline || (value.job_type === 'python' && !campo)) return null
  if (!cap.data?.vinculos_disponiveis && !Object.keys(refs).length) return null
  function escolher(destino: string, nome: string) {
    const next = { ...refs }
    if (nome) next[destino] = nome
    else delete next[destino]
    onChange({ param_vinculos: next,
      ...(value.job_type === 'python' && py && nome ? { python: { ...py, [destino]: '' } } : {}) })
  }
  const destinos = value.job_type === 'python' ? [campo!] : Object.keys(refs)
  return <section className="space-y-3 border-t border-edge pt-3">
    <h3 className="text-sm font-semibold text-ink">Usar parâmetros do pipeline</h3>
    <p className="text-xs text-dim">Valores diretos no nó têm prioridade. A execução guarda a configuração original para retomadas. A primeira ativação exige publicar a DAG.</p>
    {(cap.isError || q.isError) && <p role="alert" className="text-sm text-red-700 dark:text-red-300">Não foi possível carregar o catálogo. As referências preenchidas foram mantidas.</p>}
    {destinos.map(destino => {
      const nome = refs[destino] ?? ''
      const selecionado = opcoes.find(p => p.param_name === nome)
      const direto = value.job_type === 'datastage'
        ? value.params.some(p => p.param_name.trim() === destino)
        : !!py?.[destino as 'script_path' | 'destino_dir']
      return <div key={destino} className="space-y-1">
        <Select label={value.job_type === 'python' ? 'Origem do caminho' : `Parâmetro do job: ${destino}`}
          value={nome} disabled={!q.isSuccess || !cap.data?.vinculos_disponiveis}
          onChange={e => escolher(destino, e.target.value)}>
          <option value="">Valor direto / sem referência</option>
          {nome && !selecionado && <option value={nome}>{nome} — indisponível</option>}
          {opcoes.map(p => <option key={p.param_name} value={p.param_name}>[{p.param_destino === 'datastage' ? 'DS' : 'ORQ'}] {p.param_name}</option>)}
        </Select>
        {nome && <p className="break-all text-xs text-dim">{direto ? 'O valor direto deste nó está sobrepondo a referência.' : legendaParametro(selecionado)}</p>}
        {value.job_type === 'datastage' && <Button type="button" variant="secondary" onClick={() => escolher(destino, '')}>Remover referência</Button>}
      </div>
    })}
    {value.job_type === 'datastage' && <div className="space-y-2">
      <Input label="Nome declarado pelo job DataStage" value={alvo} onChange={e => setAlvo(e.target.value)} />
      <Button type="button" variant="secondary" disabled={!q.isSuccess || !opcoes.length}
        onClick={() => {
          const nome = alvo.trim()
          if (!/^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$/.test(nome) || nome.length > 128) {
            setErro('Informe um nome válido declarado pelo job.'); return
          }
          if (nome in refs) { setErro('Este destino já tem uma referência.'); return }
          onChange({ param_vinculos: { ...refs, [nome]: opcoes[0].param_name } })
          setAlvo(''); setErro('')
        }}>Adicionar referência</Button>
      {erro && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{erro}</p>}
    </div>}
    {!opcoes.length && q.isSuccess && <p className="text-xs text-dim">Cadastre um parâmetro compatível em Parâmetros Globais do pipeline.</p>}
  </section>
}
