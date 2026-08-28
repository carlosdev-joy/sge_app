// O rodapé do card do kanban: responsável, idade e prazo.
//
// Componente próprio porque o que ele decide é o que NÃO mostrar, e isso é
// invisível de fora: o card simplesmente aparece com uma linha a menos. Aqui a
// decisão fica renderizável — e o teste pergunta ao DOM em vez de procurar
// texto no fonte, que foi como um teste meu passou verde com o defeito de pé.
import { dataDoPrazo, mostraPrazo, rotuloDoPrazo } from '../../lib/prazoChamados'

// O tom do prazo. Sempre com o TEXTO ao lado: cor não informa quem não a
// distingue, nem sobrevive a uma impressão em preto e branco.
const TOM_PRAZO: Record<string, string> = {
  atrasado: 'text-red-600 dark:text-red-400 font-medium',
  hoje: 'text-orange-600 dark:text-orange-400 font-medium',
  'no prazo': 'text-emerald-600 dark:text-emerald-400',
}

export interface DadosDoRodape {
  estado_kanban: string
  atribuido_a: string | null
  demandante?: string | null
  idade_dias: number | null
  prazo: string | null
}

export function RodapeCard({ c, textoIdade, faixaIdade }: {
  c: DadosDoRodape
  textoIdade: (dias: number | null) => string
  faixaIdade: (dias: number | null) => { classe: string; rotulo: string }
}) {
  // Um chamado que terminou não está esperando nada: nem a idade nem o prazo
  // dizem algo sobre ele. "parado há 40 dias" num card RESOLVIDO é alarme
  // sobre trabalho FEITO — e alarme que não pede ação nenhuma é o que ensina
  // a ignorar os outros, inclusive os que pedem.
  const vivo = mostraPrazo(c.estado_kanban)
  const prazo = vivo ? rotuloDoPrazo(c.prazo) : null
  const data = vivo ? dataDoPrazo(c.prazo) : null
  const faixa = faixaIdade(c.idade_dias)

  return (
    <>
      {/* QUEM PEDIU, em linha própria. Antes ele existia só no `title` do
          responsável — quer dizer: só para quem passasse o mouse, e não para
          quem estivesse no toque ou lendo a fila de relance. São duas pessoas
          diferentes e as duas importam: uma para saber a quem cobrar, a outra
          para saber a quem responder. */}
      {c.demandante && (
        <div data-solicitante
          className="flex items-baseline gap-1 text-[11px] min-w-0">
          <span className="text-dim shrink-0">de</span>
          <span className="text-ink truncate" title={`Solicitante: ${c.demandante}`}>
            {c.demandante}
          </span>
        </div>
      )}
      <div className="flex items-center justify-between gap-2 text-[11px] text-dim">
        <span className="truncate"
          title={`Responsável: ${c.atribuido_a || 'sem responsável'}`}>
          {c.atribuido_a || 'sem responsável'}
        </span>
        {/* Idade: cor E rótulo. A cor sozinha não informa quem não a distingue. */}
        {vivo && (
          <span data-idade title={textoIdade(c.idade_dias)}
            className={`shrink-0 flex items-center gap-1 ${faixa.classe}`}>
            {faixa.rotulo && (
              <span className="uppercase tracking-wide text-[9px]">{faixa.rotulo}</span>
            )}
            {c.idade_dias !== null ? `${c.idade_dias}d` : '—'}
          </span>
        )}
      </div>

      {/* O prazo NO CARD, e não só no detalhe: quem abre o kanban precisa ver
          o que vence sem clicar em cada um — que é justamente o gesto que o
          quadro existe para evitar. */}
      {prazo && data && (
        <div data-prazo className="flex items-center gap-1.5 text-[10px]">
          <span className="text-dim">prazo</span>
          <span className="text-ink tabular-nums">{data}</span>
          <span className={TOM_PRAZO[prazo.tom]}>{prazo.texto}</span>
        </div>
      )}
    </>
  )
}
