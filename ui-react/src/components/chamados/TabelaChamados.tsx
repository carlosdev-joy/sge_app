// A tabela de chamados — uma só, para todo lugar onde chamado aparece por linha.
//
// ⚠️ POR QUE TABELA, E NÃO A LISTA QUE HAVIA ANTES
// A lista era um `flex` onde prazo e data só eram RENDERIZADOS quando existiam.
// Um chamado sem prazo perdia duas células e o responsável escorregava para o
// lugar delas: a mesma coluna visual mostrava prazo numa linha e nome na
// seguinte. Aqui a célula vazia CONTINUA OCUPANDO a coluna — é isso, e só isso,
// que garante "o responsável está sempre embaixo de Responsável".
//
// A largura é arrastável porque nome de pessoa não cabe em largura fixa e
// `truncate` sem saída transforma "Cristiane Gomes de Moura" em "Cristiane
// Gomes…" para sempre. Sem biblioteca de grid: o deploy da Caixa é OFFLINE, com
// wheels — um pacote novo custaria rede que a instalação não tem.
import { useRef, useState } from 'react'
import {
  LARGURA_MINIMA, larguraDasColunas, lerLarguras, novaLargura, salvarLarguras,
} from '../../lib/tabelaChamados'

export interface ColunaTabela<T> {
  chave: string
  rotulo: string
  /** Largura inicial em px, antes de o usuário arrastar. */
  largura: number
  minima?: number
  /** Números alinham à direita: é o que deixa comparar grandeza a olho. */
  direita?: boolean
  conteudo: (item: T) => React.ReactNode
  /** O valor INTEIRO, para o `title` — o resgate de quem ainda não arrastou. */
  titulo?: (item: T) => string
}

export function TabelaChamados<T>({ id, colunas, itens, chaveDe, vazio }: {
  /** Identidade da tabela — é por ela que a largura escolhida é lembrada. */
  id: string
  colunas: ColunaTabela<T>[]
  itens: T[]
  chaveDe: (item: T) => string
  vazio: string
}) {
  const [larguras, setLarguras] = useState<Record<string, number>>(
    () => larguraDasColunas(colunas, lerLarguras(id)))
  // O arrasto em curso. Em `ref` porque ele muda a cada pixel do ponteiro e
  // não deve, sozinho, disparar render.
  const arrasto = useRef<{ chave: string; x: number; largura: number } | null>(null)

  const largura = (c: ColunaTabela<T>) => larguras[c.chave] ?? c.largura

  // Ponteiro, não mouse: o mesmo código atende toque e caneta. E a captura
  // mantém os eventos vindo para a alça mesmo quando o cursor sai dela — sem
  // isso, arrastar rápido "solta" a coluna no meio do caminho.
  const comecar = (c: ColunaTabela<T>, e: React.PointerEvent) => {
    e.preventDefault()
    arrasto.current = { chave: c.chave, x: e.clientX, largura: largura(c) }
    ;(e.target as Element & { setPointerCapture?: (id: number) => void })
      .setPointerCapture?.(e.pointerId)
  }
  const mover = (e: React.PointerEvent) => {
    const a = arrasto.current
    if (!a) return
    const col = colunas.find(c => c.chave === a.chave)
    setLarguras(atual => ({
      ...atual,
      [a.chave]: novaLargura(a.largura, e.clientX - a.x, col?.minima),
    }))
  }
  const soltar = () => {
    if (!arrasto.current) return
    arrasto.current = null
    // Salva no FIM do arrasto, não a cada pixel: gravar em `localStorage` a
    // cada `pointermove` é escrita síncrona no meio da interação.
    setLarguras(atual => { salvarLarguras(id, atual); return atual })
  }

  if (!itens.length) return <p className="text-xs text-dim">{vazio}</p>

  return (
    // A tabela larga rola DENTRO do seu container. Sem isto, arrastar uma
    // coluna para além da tela empurraria a página inteira na horizontal.
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse"
        style={{ tableLayout: 'fixed', width: 'max-content', minWidth: '100%' }}>
        <colgroup>
          {colunas.map(c => <col key={c.chave} style={{ width: largura(c) }} />)}
        </colgroup>
        <thead>
          <tr className="text-dim text-left border-b border-edge">
            {colunas.map(c => (
              <th key={c.chave} scope="col"
                className={`font-medium py-1 pr-3 relative select-none
                  ${c.direita ? 'text-right' : ''}`}>
                <span className="block truncate" title={c.rotulo}>{c.rotulo}</span>
                {/* A alça. `title` porque uma faixa de 6px não se anuncia
                    sozinha: quem não tentar arrastar não descobre que dá. */}
                <span data-alca={c.chave} onPointerDown={e => comecar(c, e)}
                  onPointerMove={mover} onPointerUp={soltar} onPointerCancel={soltar}
                  title={`Arraste para mudar a largura de "${c.rotulo}"`}
                  className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize
                    hover:bg-blue-400/60 active:bg-blue-500" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {itens.map(item => (
            <tr key={chaveDe(item)} className="border-b border-edge last:border-0">
              {colunas.map(c => (
                // ⚠️ A célula é renderizada SEMPRE, mesmo vazia. É o que
                // mantém cada valor embaixo do seu cabeçalho.
                <td key={c.chave}
                  className={`py-1 pr-3 align-top ${c.direita ? 'text-right' : ''}`}
                  title={c.titulo?.(item) || undefined}>
                  <div className="truncate">{c.conteudo(item)}</div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export { LARGURA_MINIMA }
