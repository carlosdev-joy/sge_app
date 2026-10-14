import { useMemo, useState } from 'react'
import type { Node } from '@xyflow/react'
import { Input } from '../ui/Input'
import { COMPONENTE_META, type TipoComponente } from './componenteMeta'

function identidade(no: Node) {
  const tipo = no.data.tipo as TipoComponente | undefined
  const componente = tipo && COMPONENTE_META[tipo]
  return {
    nome: typeof no.data.name === 'string' ? no.data.name : `${componente ? componente.rotulo : 'Nó'} #${no.data.noId ?? no.id}`,
    tipo: componente ? componente.rotulo : 'Pipeline',
  }
}

// Só recebe os nós da lente apresentada; nunca consulta o catálogo atual nem grava layout.
export function LocalizadorMalha({ nodes, onLocalizar }: {
  nodes: Node[]
  onLocalizar: (id: string) => void
}) {
  const [busca, setBusca] = useState('')
  const resultados = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase('pt-BR')
    return nodes.filter(no => {
      const item = identidade(no)
      return `${item.nome} ${item.tipo} ${no.id}`.toLocaleLowerCase('pt-BR').includes(termo)
    })
  }, [nodes, busca])
  const selecionados = nodes.filter(no => no.selected)
  const alvo = selecionados.length === 1 ? selecionados[0] : undefined
  const exec = alvo?.data.exec as { titulo?: string } | undefined

  return (
    <details className="shrink-0 border-b border-edge bg-panel text-ink">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px]">
        Localizar / lista de nós ({nodes.length}) e propriedades
      </summary>
      <div className="grid max-h-60 gap-3 overflow-y-auto px-3 pb-3 md:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <Input label="Localizar nó nesta visão" value={busca} onChange={e => setBusca(e.target.value)} placeholder="Nome, tipo ou identificador" />
          <p className="text-xs text-dim" role="status">{resultados.length} nó(s) encontrado(s). Selecione para centralizar e ver propriedades.</p>
          <ul aria-label="Nós da malha" className="max-h-40 overflow-y-auto">
            {resultados.map(no => {
              const item = identidade(no)
              return <li key={no.id}>
                <button type="button" aria-pressed={!!no.selected} onClick={() => onLocalizar(no.id)}
                  className="w-full rounded px-2 py-2 text-left text-xs hover:bg-canvas focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px]">
                  <span className="block break-words [overflow-wrap:anywhere] font-medium">{item.nome}</span>
                  <span className="text-dim">{item.tipo}</span>
                </button>
              </li>
            })}
          </ul>
          {resultados.length === 0 && <p className="text-xs text-dim">Nenhum nó corresponde à busca. Limpe o campo para ver todos.</p>}
        </div>
        <section aria-label="Propriedades do nó" className="min-w-0 text-xs">
          <h3 className="mb-2 font-semibold">Propriedades do nó</h3>
          {alvo ? <dl className="space-y-1 break-words [overflow-wrap:anywhere]">
            <dt className="text-dim">Nome</dt><dd>{identidade(alvo).nome}</dd>
            <dt className="text-dim">Tipo / identificador</dt><dd>{identidade(alvo).tipo} · {alvo.id}</dd>
            {exec?.titulo && <><dt className="text-dim">Execução nesta visão</dt><dd>{exec.titulo}</dd></>}
          </dl> : <p className="text-dim">Selecione um único nó na lista ou no canvas. As ações disponíveis continuam na barra do canvas.</p>}
          <p className="mt-3 text-dim">Localizar e selecionar alteram somente a apresentação. Dependências e posições permanecem iguais. Na execução, consulte Agora, Travando e Eventos para as causas informadas pela fonte.</p>
        </section>
      </div>
    </details>
  )
}
