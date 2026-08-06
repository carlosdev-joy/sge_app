import type { ReactNode } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Faixa de aviso de largura total — spec docs/spec-malha-execucao.md §9.9
// (Decisão 71).
//
// PROMOÇÃO, não reescrita: o original é o `Banner` local de
// `components/etapas/PainelExecucaoEtapas.tsx` (que passa a importar daqui).
// As classes dos três tons vieram byte a byte de lá — trocar qualquer uma
// mudaria a aparência dos avisos do canvas de Etapas, que já estão em
// produção.
//
// POR QUE PROMOVER: o `MalhaEditor` carrega NOVE cópias literais das mesmas
// classes de faixa (:2037, :2074, :2104, :2116, :2130, :2177, :2191, :2200,
// :2214) e a camada de corrida acrescentaria mais três (os banners da Decisão
// 66). Nove cópias é o ponto em que a duplicação deixa de ser repetição e vira
// risco de regressão de tema: basta uma delas ficar sem o par escuro.
//
// Diferenças em relação ao original, e só elas:
//   • `icone` passa a ser OPCIONAL (o original exigia; todos os chamadores de
//     lá continuam passando);
//   • entra o tom `sucesso`, que o original não tinha;
//   • entra o slot `acao`, encostado à direita — é onde mora o botão `Soltar`
//     do banner de nós segurados (Decisão 66). Sem `acao` o desenho é
//     idêntico ao de hoje.
// ─────────────────────────────────────────────────────────────────────────────

export type TomBanner = 'info' | 'alerta' | 'erro' | 'sucesso'

export interface BannerProps {
  tom: TomBanner
  icone?: ReactNode
  /** Botão/link à direita — o `Soltar` da Decisão 66. */
  acao?: ReactNode
  children: ReactNode
}

// Par claro+escuro obrigatório em TODOS os tons (docs/ui-temas-cores.md:63-82).
const TOM: Record<TomBanner, string> = {
  erro:
    'border-red-200 bg-red-50 text-red-700 ' +
    'dark:border-red-800 dark:bg-red-900/20 dark:text-red-300',
  alerta:
    'border-amber-200 bg-amber-50 text-amber-700 ' +
    'dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400',
  info:
    'border-blue-200 bg-blue-50 text-blue-800 ' +
    'dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200',
  sucesso:
    'border-green-200 bg-green-50 text-green-700 ' +
    'dark:border-green-800 dark:bg-green-900/20 dark:text-green-300',
}

export function Banner({ tom, icone, acao, children }: BannerProps) {
  return (
    <div className={`flex items-start gap-2 border-b px-3 py-2 text-[12px] ${TOM[tom]}`}>
      {icone}
      {/* O `span` fica EXATAMENTE como no original: o alinhamento à direita da
          ação é feito por `ml-auto` nela, e não mexendo no fluxo do texto —
          assim os quatro chamadores que já existem renderizam byte a byte. */}
      <span>{children}</span>
      {acao && <span className="ml-auto shrink-0">{acao}</span>}
    </div>
  )
}
