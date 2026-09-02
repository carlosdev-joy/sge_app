// A alça de arrasto que redimensiona uma coluna da tabela.
//
// Fica na borda direita do `<th>`, discreta até o ponteiro chegar perto. É
// focável e responde às setas — redimensionar só com mouse deixaria de fora
// quem navega por teclado.
import type { ColunasRedimensionaveis } from './useColunasRedimensionaveis'

export function AlcaColuna({ chave, cols, rotulo }: {
  chave: string
  cols: ColunasRedimensionaveis
  rotulo: string
}) {
  return (
    <span
      {...cols.alcaDe(chave)}
      role="separator"
      aria-orientation="vertical"
      aria-label={`Ajustar a largura da coluna ${rotulo}. Setas ajustam; duplo clique restaura.`}
      tabIndex={0}
      title="Arraste para ajustar · duplo clique restaura"
      className="absolute top-0 right-0 h-full w-2 cursor-col-resize select-none
                 flex items-center justify-center group/alca
                 focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500"
    >
      {/* O filete só aparece no hover/foco: presente quando se procura por ele,
          invisível no resto do tempo. */}
      <span className="h-3/5 w-px bg-edge group-hover/alca:bg-blue-400
                       group-focus-visible/alca:bg-blue-400 transition-colors" />
    </span>
  )
}
