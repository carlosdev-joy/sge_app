// O filtro de responsáveis da aba de Indicadores, com múltipla escolha.
//
// Era um `<select>` de um nome só. A gestão compara duas ou três pessoas — e
// com um seletor único isso vira olhar uma, guardar o número de cabeça, olhar
// a outra. O que se quer comparar são justamente os números que a troca apaga.
//
// ⚠️ A PRIMEIRA VERSÃO USAVA `<details>`, E TRAVAVA A TELA.
// O argumento era que ele dispensava tratar o clique-fora. Estava errado:
// `<details>` fecha SÓ pelo próprio gatilho. Depois de marcar um nome, a caixa
// ficava aberta sobre o conteúdo — e o conteúdo é justamente o que a pessoa
// acabou de filtrar para ver. Só um recarregamento da página resolvia, e aí o
// filtro se perdia junto.
//
// A correção não é "não usar `<details>`": é que uma camada flutuante precisa
// de uma forma de fechar que NÃO exija acertar o gatilho de novo. São três, e
// nenhuma delas é opcional — quem usa mouse fecha clicando fora, quem usa
// teclado fecha com Esc, e o gatilho continua alternando.
import { useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { alternar, resumoDoFiltro } from '../../lib/filtroResponsaveis'

export interface OpcaoResponsavel {
  nome: string
  total: number
}

export function FiltroResponsaveis({ opcoes, escolhidos, aoMudar, totalGeral }: {
  opcoes: OpcaoResponsavel[]
  escolhidos: string[]
  aoMudar: (nomes: string[]) => void
  totalGeral: number
}) {
  const [aberto, setAberto] = useState(false)

  return (
    <div className="relative"
      // Esc fecha. O foco está dentro da caixa enquanto a pessoa marca as
      // opções, então o evento chega aqui por borbulhamento.
      onKeyDown={e => { if (e.key === 'Escape') setAberto(false) }}>
      <button type="button" data-gatilho onClick={() => setAberto(a => !a)}
        aria-expanded={aberto} aria-haspopup="listbox"
        className="flex items-center gap-1.5 w-full bg-canvas border border-edge
          rounded-md text-xs px-2 py-1 text-ink min-w-56 text-left">
        <span className="flex-1 truncate">
          {resumoDoFiltro(escolhidos, totalGeral)}
        </span>
        {/* A contagem no gatilho fechado: sem ela, um filtro de três pessoas
            fica indistinguível de nenhum filtro quando a lista está fechada. */}
        {escolhidos.length > 0 && (
          <span data-contagem className="shrink-0 text-[10px] px-1 rounded
            bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300">
            {escolhidos.length}
          </span>
        )}
        <ChevronDown size={12} aria-hidden
          className={`shrink-0 text-dim transition-transform
            ${aberto ? 'rotate-180' : ''}`} />
      </button>

      {aberto && (
        <>
          {/* O fundo que captura o clique fora. Invisível e em tela cheia,
              ABAIXO da caixa: clicar numa opção não o alcança, clicar em
              qualquer outro lugar fecha. É o que faltava na versão anterior. */}
          <div data-fundo className="fixed inset-0 z-10"
            onClick={() => setAberto(false)} aria-hidden />

          <div data-caixa role="listbox" aria-multiselectable
            className="absolute z-20 mt-1 w-72 max-h-72 overflow-y-auto
              bg-panel border border-edge rounded-md shadow-lg p-1 flex flex-col">
            {/* "Todos" é o gesto de LIMPAR, e mora junto das opções porque é
                lá que a pessoa está olhando quando decide desfazer o recorte. */}
            <button type="button" data-limpar onClick={() => aoMudar([])}
              className="flex items-center gap-2 text-left text-xs px-2 py-1.5
                rounded hover:bg-canvas text-ink">
              <span className="w-3.5 shrink-0">
                {escolhidos.length === 0 && <Check size={13} aria-hidden />}
              </span>
              <span className="flex-1">todos</span>
              <span className="text-dim tabular-nums">{totalGeral}</span>
            </button>

            <div className="border-t border-edge my-1" />

            {opcoes.length === 0 && (
              <p className="text-[11px] text-dim px-2 py-1.5">
                Nenhum responsável na fila.
              </p>
            )}

            {opcoes.map(o => {
              const marcado = escolhidos.includes(o.nome)
              return (
                // `<label>` embrulhando o input: a área de clique vira a linha
                // inteira, e não um quadrado de 13px.
                <label key={o.nome} data-opcao={o.nome}
                  className="flex items-center gap-2 text-xs px-2 py-1.5 rounded
                    hover:bg-canvas cursor-pointer text-ink">
                  <input type="checkbox" checked={marcado}
                    onChange={() => aoMudar(alternar(escolhidos, o.nome))}
                    className="w-3.5 h-3.5 shrink-0 accent-blue-600" />
                  <span className="flex-1 truncate" title={o.nome}>{o.nome}</span>
                  {/* O total ao lado do nome: quem analisa escolhe melhor vendo
                      "Fulano (12)" do que uma lista de nomes soltos. */}
                  <span className="text-dim tabular-nums shrink-0">{o.total}</span>
                </label>
              )
            })}

            {/* A saída DITA. O clique fora funciona, mas não se anuncia — e
                quem não descobriu fica preso à caixa, que foi exatamente o
                relato que originou esta correção. */}
            <div className="border-t border-edge mt-1 pt-1">
              <button type="button" data-fechar onClick={() => setAberto(false)}
                className="w-full text-[11px] text-blue-600 dark:text-blue-400
                  px-2 py-1 rounded hover:bg-canvas text-left">
                fechar
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
