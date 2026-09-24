// A resposta do agente, desenhada a partir dos blocos de lib/markdownLlm.ts.
//
// Mesmo parser do Caixa Seguro e do Maestro — e, como lá, NUNCA
// dangerouslySetInnerHTML: o texto vem de um LLM, e HTML por string
// transformaria a resposta em markup executável.
//
// O que muda em relação a `caixa/components/MensagemMarkdown.tsx`: lá as
// bordas são `border-white/30` e os fundos `bg-black/20`, deliberadamente
// presos à bolha AZUL do assistente do Caixa. Aqui a bolha é `bg-panel`
// (branca no claro), onde branco-sobre-branco simplesmente desaparece —
// então cada cor vem de token (`edge`, `canvas`, `dim`), que já tem par
// claro+escuro. Nenhuma cor fixa (critério 4 da F3).
//
// Bloco ```sql vira "Consulta SQL" (realce + Copiar — spec ferramenta-banco C5),
// inclusive as consultas que o agente SUGERE ao usuário.
import { useMemo } from 'react'
import type { BlocoMd, PedacoInline } from '../../lib/markdownLlm'
import { parseMarkdown } from '../../lib/markdownLlm'
import { BlocoSql } from './BlocoSql'

function Inline({ partes }: { partes: PedacoInline[] }) {
  return (
    <>
      {partes.map((p, i) => {
        if (p.codigo) {
          return (
            <code key={i} className="font-mono text-[11px] px-1 py-0.5 rounded bg-canvas border border-edge">
              {p.texto}
            </code>
          )
        }
        if (p.negrito) return <strong key={i} className="font-semibold">{p.texto}</strong>
        if (p.italico) return <em key={i} className="italic">{p.texto}</em>
        return <span key={i}>{p.texto}</span>
      })}
    </>
  )
}

const TAMANHO_TITULO: Record<number, string> = { 1: 'text-[15px]', 2: 'text-sm', 3: 'text-sm' }

function Bloco({ b }: { b: BlocoMd }) {
  if (b.tipo === 'titulo') {
    return (
      <p className={`font-semibold ${TAMANHO_TITULO[b.nivel] ?? 'text-sm'} mt-1 first:mt-0`}>
        <Inline partes={b.partes} />
      </p>
    )
  }
  if (b.tipo === 'separador') return <hr className="border-0 border-t border-edge my-1" />
  if (b.tipo === 'codigo' && b.linguagem === 'sql') return <BlocoSql sql={b.texto} />
  if (b.tipo === 'codigo') {
    return (
      <pre className="text-[11px] font-mono bg-canvas border border-edge rounded p-2 overflow-x-auto whitespace-pre">
        {b.texto}
      </pre>
    )
  }
  if (b.tipo === 'lista') {
    const Tag = b.ordenada ? 'ol' : 'ul'
    return (
      <Tag className={`${b.ordenada ? 'list-decimal' : 'list-disc'} pl-4 flex flex-col gap-0.5`}>
        {b.itens.map((it, i) => <li key={i}><Inline partes={it} /></li>)}
      </Tag>
    )
  }
  if (b.tipo === 'tabela') {
    return (
      <div className="overflow-x-auto -mx-1 px-1">
        <table className="text-[11px] border-collapse">
          <thead>
            <tr>
              {b.cabecalho.map((c, i) => (
                <th key={i} className="text-left font-semibold align-top px-1.5 py-1 border-b border-edge whitespace-nowrap">
                  <Inline partes={c} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {b.linhas.map((linha, i) => (
              <tr key={i}>
                {linha.map((celula, j) => (
                  <td key={j} className="align-top px-1.5 py-1 border-b border-edge">
                    <Inline partes={celula} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return <p><Inline partes={b.partes} /></p>
}

export function MarkdownAgente({ texto }: { texto: string }) {
  const blocos = useMemo(() => parseMarkdown(texto), [texto])
  return (
    <div className="text-sm leading-snug flex flex-col gap-1.5 break-words">
      {blocos.map((b, i) => <Bloco key={i} b={b} />)}
    </div>
  )
}
