import { useMemo, useState } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Search, X, AlertTriangle, Check } from 'lucide-react'
import type { Pipeline } from '../../types/pipeline'

// Escolha das dependências de um pipeline.
//
// Substitui o campo de texto livre "pipelines separados por vírgula", onde um
// nome digitado errado era aceito e virava espera infinita em produção: no modo
// sensor o pipeline falhava depois de 1h; no modo Dataset nunca disparava, em
// silêncio. Aqui não há como digitar um nome — só escolher da lista.
//
// Duas coisas que a lista mostra e a digitação escondia:
//   • o PROJETO de cada pipeline, porque nomes se parecem entre projetos;
//   • se o pipeline está INATIVO — depender de um inativo é uma armadilha, o
//     dependente nunca vai liberar.

export function DependenciasModal({
  open, onClose, pipelineAtual, selecionadas, pipelines, onConfirmar,
}: {
  open: boolean
  onClose: () => void
  pipelineAtual: string
  selecionadas: string[]
  pipelines: Pipeline[]
  onConfirmar: (nomes: string[]) => void
}) {
  const [busca, setBusca] = useState('')
  const [projeto, setProjeto] = useState('Todos')
  const [escolhidas, setEscolhidas] = useState<string[]>(selecionadas)

  const projetos = useMemo(() => {
    const set = new Set<string>()
    pipelines.forEach(p => { if (p.project_name) set.add(p.project_name) })
    return ['Todos', ...[...set].sort()]
  }, [pipelines])

  // O próprio pipeline nunca aparece: depender de si mesmo é recusado pelo
  // banco (CHECK) e oferecer a opção só produziria um erro evitável.
  const candidatos = useMemo(() => {
    const termo = busca.trim().toLowerCase()
    return pipelines
      .filter(p => p.pipeline_name !== pipelineAtual)
      .filter(p => projeto === 'Todos' || p.project_name === projeto)
      .filter(p => !termo || p.pipeline_name.toLowerCase().includes(termo)
        || (p.project_name ?? '').toLowerCase().includes(termo))
      .sort((a, b) => a.pipeline_name.localeCompare(b.pipeline_name))
  }, [pipelines, pipelineAtual, projeto, busca])

  const alternar = (nome: string) =>
    setEscolhidas(prev => prev.includes(nome) ? prev.filter(n => n !== nome) : [...prev, nome])

  const inativasEscolhidas = escolhidas.filter(
    nome => pipelines.find(p => p.pipeline_name === nome)?.active === 0)

  return (
    <Modal open={open} onClose={onClose} title="Escolher dependências" size="lg">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-dim">
          Este pipeline só vai iniciar depois que <strong className="text-ink">todos</strong> os
          escolhidos concluírem com sucesso na mesma data de referência.
        </p>

        {/* Escolhidas primeiro: o resultado da ação fica visível sem rolar. */}
        {escolhidas.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {escolhidas.map(nome => (
              <span key={nome}
                className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full border border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 text-[11px] text-blue-700 dark:text-blue-300">
                <span className="font-mono">{nome}</span>
                <button onClick={() => alternar(nome)} aria-label={`Remover ${nome}`}
                  className="hover:text-red-600 dark:hover:text-red-400">
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        {inativasEscolhidas.length > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/15 px-3 py-2">
            <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <p className="text-[11px] text-amber-800 dark:text-amber-300">
              {inativasEscolhidas.join(', ')} {inativasEscolhidas.length === 1 ? 'está inativo' : 'estão inativos'} —
              enquanto seguir assim, este pipeline não vai ser liberado.
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-dim" />
            <input
              value={busca}
              onChange={e => setBusca(e.target.value)}
              placeholder="Buscar por nome ou projeto"
              aria-label="Buscar pipeline"
              className="w-full bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <select
            value={projeto}
            onChange={e => setProjeto(e.target.value)}
            aria-label="Filtrar por projeto"
            className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {projetos.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <div className="border border-edge rounded-lg divide-y divide-edge max-h-[45vh] overflow-y-auto">
          {candidatos.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-dim">
              Nenhum pipeline encontrado com esse filtro.
            </p>
          )}
          {candidatos.map(p => {
            const marcado = escolhidas.includes(p.pipeline_name)
            return (
              <button
                key={p.pipeline_name}
                onClick={() => alternar(p.pipeline_name)}
                aria-pressed={marcado}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                  marcado ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-edge/30'
                }`}
              >
                <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                  marcado ? 'bg-[#1A5FA8] border-[#1A5FA8] text-white' : 'border-edge'
                }`}>
                  {marcado && <Check size={11} />}
                </span>
                <span className="font-mono text-[11px] text-ink break-all flex-1">{p.pipeline_name}</span>
                <span className="text-[10px] text-dim shrink-0">{p.project_name ?? '—'}</span>
                {p.active === 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-edge text-dim shrink-0">inativo</span>
                )}
              </button>
            )
          })}
        </div>

        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="text-xs text-dim">
            {escolhidas.length === 0 ? 'Nenhuma dependência'
              : escolhidas.length === 1 ? '1 dependência'
              : `${escolhidas.length} dependências`}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
            <Button variant="primary" onClick={() => { onConfirmar(escolhidas); onClose() }}>
              Confirmar
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
