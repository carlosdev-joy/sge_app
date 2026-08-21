// A resposta do assistente, desenhada a partir dos blocos de markdown.ts.
//
// Antes a bolha usava `whitespace-pre-wrap` e o operador lia o Markdown cru:
// `## Status Principais`, `**Emitida**` e a tabela em canos. Aqui cada bloco
// vira elemento React — nunca HTML por string: o texto vem de um LLM, e
// dangerouslySetInnerHTML transformaria a resposta em markup executável.
//
// O texto herda a cor da bolha (`currentColor`), mas as BORDAS são brancas
// com alfa, e isso é deliberado: este componente só desenha dentro da bolha
// AZUL do assistente. `border-current/40` parecia mais elegante e não
// funciona — o Tailwind v3 não gera a classe com alfa sobre `currentColor`,
// ela é descartada em silêncio e a borda cai no cinza do preflight
// (`#e5e7eb`), apagando a diferença entre o traço do cabeçalho e o das
// linhas. Conferido no CSS gerado, não no que a documentação promete.
import { useMemo } from 'react'
import type { BlocoMd, PedacoInline } from '../lib/markdown'
import { parseMarkdown } from '../lib/markdown'

function Inline({ partes }: { partes: PedacoInline[] }) {
  return (
    <>
      {partes.map((p, i) => {
        if (p.codigo) {
          return (
            <code key={i} className="font-mono text-[11px] px-1 py-0.5 rounded bg-black/20">
              {p.texto}
            </code>
          )
        }
        if (p.negrito) return <strong key={i} className="font-semibold">{p.texto}</strong>
        if (p.italico) return <em key={i}>{p.texto}</em>
        return <span key={i}>{p.texto}</span>
      })}
    </>
  )
}

const TAMANHO_TITULO: Record<number, string> = {
  1: 'text-[13px]',
  2: 'text-[12.5px]',
  3: 'text-[12px]',
}

function Bloco({ b }: { b: BlocoMd }) {
  switch (b.tipo) {
    case 'titulo':
      return (
        <p className={`font-semibold ${TAMANHO_TITULO[b.nivel]} mt-1 first:mt-0`}>
          <Inline partes={b.partes} />
        </p>
      )

    case 'separador':
      return <hr className="border-0 border-t border-white/30 my-1" />

    case 'codigo':
      return (
        <pre className="text-[11px] font-mono bg-black/20 rounded p-2 overflow-x-auto whitespace-pre">
          {b.texto}
        </pre>
      )

    case 'lista':
      return b.ordenada ? (
        <ol className="list-decimal pl-4 flex flex-col gap-0.5">
          {b.itens.map((it, i) => <li key={i}><Inline partes={it} /></li>)}
        </ol>
      ) : (
        <ul className="list-disc pl-4 flex flex-col gap-0.5">
          {b.itens.map((it, i) => <li key={i}><Inline partes={it} /></li>)}
        </ul>
      )

    case 'tabela':
      // A bolha tem 384px e a tabela do modelo costuma ter 2-4 colunas: o
      // scroll fica NA TABELA, nunca no corpo do chat — barra horizontal na
      // conversa inteira é o defeito que este contêiner evita.
      return (
        <div className="overflow-x-auto -mx-1 px-1">
          <table className="text-[11px] border-collapse">
            <thead>
              <tr>
                {b.cabecalho.map((c, i) => (
                  <th key={i} className="text-left font-semibold align-top px-1.5 py-1 border-b border-white/50 whitespace-nowrap">
                    <Inline partes={c} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.linhas.map((linha, i) => (
                <tr key={i}>
                  {linha.map((celula, j) => (
                    <td key={j} className="align-top px-1.5 py-1 border-b border-white/20">
                      <Inline partes={celula} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )

    default:
      return <p><Inline partes={b.partes} /></p>
  }
}

export default function MensagemMarkdown({ texto }: { texto: string }) {
  // `useMemo` porque o estado do campo de digitação mora no ChatAssistant:
  // sem ele, CADA tecla digitada reprocessa a conversa inteira — tabelas
  // grandes inclusive — antes de o React comparar a árvore.
  const blocos = useMemo(() => parseMarkdown(texto), [texto])
  return (
    <div className="text-sm leading-snug flex flex-col gap-1.5 break-words">
      {blocos.map((b, i) => <Bloco key={i} b={b} />)}
    </div>
  )
}
