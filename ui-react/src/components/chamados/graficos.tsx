// As formas das abas de Chamados — painel e barras horizontais.
//
// SVG puro, sem biblioteca (padrão da casa: o Gantt do Dashboard e as
// sparkbars do Admin fazem igual). A régua de cor e o `x de y` moram em
// `escalas.ts`, ao lado.
//
// Duas regras que valem em tudo que sai daqui:
//   • nenhuma percentagem aparece sem o "x de y" — percentagem sozinha esconde
//     se são 2 de 4 ou 200 de 400;
//   • nenhuma série é identificada só por cor: há rótulo direto, porque cor não
//     informa quem não a distingue nem sobrevive a uma impressão.
import type React from 'react'
import { passoRampa, xDeY } from './escalas'

export function Painel({ titulo, descricao, children }: {
  titulo: string; descricao: string; children: React.ReactNode
}) {
  return (
    <section className="bg-panel border border-edge rounded-lg p-4 flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
        <p className="text-[11px] text-dim">{descricao}</p>
      </div>
      {children}
    </section>
  )
}

/** Barras horizontais com rótulo direto — serve aging e carga. */
export function BarrasHorizontais({ itens, total }: {
  itens: { rotulo: string; valor: number }[]; total: number
}) {
  const maximo = Math.max(1, ...itens.map(i => i.valor))
  if (itens.length === 0) {
    return <p className="text-xs text-dim">nenhum chamado na fila</p>
  }
  return (
    <div className="flex flex-col gap-1.5">
      {itens.map(i => (
        <div key={i.rotulo} className="flex items-center gap-2 text-xs">
          <span className="w-36 shrink-0 text-dim truncate" title={i.rotulo}>
            {i.rotulo}
          </span>
          <div className="flex-1 min-w-0 h-4 flex items-center">
            <svg width="100%" height="16" role="img"
              aria-label={`${i.rotulo}: ${xDeY(i.valor, total)}`}>
              {/* 4px de raio na ponta do dado, ancorada na linha de base */}
              <rect x="0" y="3" rx="4" ry="4" height="10"
                width={`${(i.valor / maximo) * 100}%`}
                fill={passoRampa(i.valor, maximo)} />
            </svg>
          </div>
          {/* Valor em token de texto, nunca na cor da série */}
          <span className="w-28 shrink-0 text-right text-ink tabular-nums">
            {xDeY(i.valor, total)}
          </span>
        </div>
      ))}
    </div>
  )
}
