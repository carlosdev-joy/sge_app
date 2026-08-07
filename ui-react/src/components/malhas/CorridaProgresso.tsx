import { AlertTriangle } from 'lucide-react'
import { Progress } from '../ui/Progress'
import type { ResumoCorrida } from './statusExecucao'

// ─────────────────────────────────────────────────────────────────────────────
// O PROGRESSO da corrida — spec docs/spec-malha-execucao.md §9.2 e §9.9.
//
// A F4 fez a VERACIDADE (o card parou de mentir sobre o estado). Esta é a outra
// pergunta, a segunda da §9.0: **em que pé está?**
//
// ── O que esta barra NÃO faz ────────────────────────────────────────────────
//  • **não mostra percentual** (Decisão 56). Nem no texto, nem no `title`, nem
//    no que o leitor de tela anuncia. "4 de 7" lido como "57%" é percentual de
//    um trabalho que não existe: os pipelines têm durações diferentes, e numa
//    malha em que o último leva 3h e os cinco primeiros 5 min, `5 de 6` é 83%
//    dos pipelines e 12% do trabalho. O percentual que o usuário pediu existe e
//    é outro número: ele mede TEMPO (Decisão 56b), ponderado pela duração
//    histórica de cada membro, e entra junto com a duração típica por membro;
//  • **não enche com o que travou** (Decisão 54). Vermelho ocupando comprimento
//    é lido como "quase pronto" a 1,5 m — em varredura de 40 cards o operador
//    lê COMPRIMENTO, não cor. O travado é chip ao lado, com ícone;
//  • **não encolhe o denominador** (Decisão 52). Ele é `membros_total` do
//    snapshot; um `PULADO` carimbado no meio da corrida muda a CLASSE do
//    membro, nunca o total. Com `total − dispensados`, `2 de 7` viraria
//    `2 de 4` sem nada ter acontecido e o olho leria "avançou" onde três
//    pipelines foram BARRADOS;
//  • **não chama barra cheia de "concluída"** (Decisão 45/§9.15/#15). Corrida
//    ABERTA com todos os membros OK está FECHANDO — e o que falta para ela
//    fechar vem escrito, com a regra antes da hora.
//
// Todos os textos são derivados por `resumoCorrida` (módulo puro, testado com o
// relógio deslocado): este componente só desenha. É o que garante que o card e
// a faixa do painel contem a mesma história a partir do mesmo agregado.
// ─────────────────────────────────────────────────────────────────────────────

export interface CorridaProgressoProps {
  resumo: ResumoCorrida
  /** `card` = a lista (barra fina, tudo em coluna) · `painel` = a faixa da
   *  visão de execução (barra mais alta). Só medida muda — nunca o texto. */
  variante?: 'card' | 'painel'
  /** Desfecho INTERROMPIDO (`EXPIRADA`/`ABORTADA`/`CANCELADA`): a barra congela
   *  no valor apurado no fechamento. `opacity-60` + a palavra "parou em" (que
   *  já veio no `resumo.contagem`) — nunca hachura, que nesta camada significa
   *  uma coisa só: "não roda hoje". */
  congelado?: boolean
  /** O chip vermelho é clicável no painel (leva à aba `Travando`, F10); no card
   *  ele é só sinal. Sem `onTravados`, sai como texto e não como botão morto. */
  onTravados?: () => void
  /** F12/Decisão 56b — `≈ 38% do tempo típico`, o percentual de TEMPO.
   *
   *  Ele é o SEGUNDO número da linha e nunca substitui o `x de y`, que
   *  continua primário e primeiro a ser lido. Chega pronto de fora (só o
   *  painel tem `tipicos[]` e `execucoes[]` para calculá-lo) e `null` é o caso
   *  comum: sem histórico em TODOS os membros ele some por completo — não é
   *  estimado, não é "aproximado com ressalva".
   *
   *  ⚠️ O CARD não o recebe de propósito: lá cabe um número só, e o que fica é
   *  o primário. */
  percentualTempo?: string | null
}

export function CorridaProgresso({
  resumo, variante = 'card', congelado = false, onTravados,
  percentualTempo = null,
}: CorridaProgressoProps) {
  const { barra, contagem, membros, travados, fechamento, nadaPrevisto } = resumo

  // ── SEM_TRABALHO: a barra DESAPARECE (Decisão 57) ────────────────────────
  // Nem 0, nem "7 de 7": 0 leria como "falhou tudo" e a barra cheia como
  // "rodou tudo", e num sábado legítimo nenhum dos dois aconteceu. Traço
  // neutro, sem alarme e sem vermelho — alarme falso semanal treina o operador
  // a ignorar o alarme (Decisões 26/27).
  if (nadaPrevisto) {
    return (
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span
            className="h-px flex-1 border-t border-dashed border-current opacity-40"
            aria-hidden="true"
          />
          <span className="shrink-0 opacity-80">{nadaPrevisto}</span>
        </div>
        {membros && <span className="opacity-80">{membros}</span>}
      </div>
    )
  }

  // Sem denominador não há barra: `membros_total` nulo é "não consegui apurar"
  // (lock timeout às 3h), e desenhar uma barra vazia seria publicar zero como
  // se fosse medida. O ESTADO do ciclo continua na pílula, que é o que mais
  // importa quando o banco está ruim.
  if (!barra || !contagem) {
    return membros ? <span className="opacity-80">{membros}</span> : null
  }

  return (
    // `div`, e não `span`: a `ui/Progress` renderiza uma `div` com
    // `role="progressbar"`, e `div` dentro de `span` é aninhamento inválido —
    // o navegador desenha, o validador reclama e o próximo a mexer aqui herda
    // uma árvore que não bate com o HTML que ele lê.
    <div className={`flex flex-col gap-0.5 ${congelado ? 'opacity-60' : ''}`}>
      <Progress
        segmentos={barra.segmentos}
        total={barra.total}
        valorAtual={barra.valorAtual}
        ariaLabel={barra.ariaLabel}
        valorTexto={barra.valorTexto}
        altura={variante === 'painel' ? 'sm' : 'xs'}
      />
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="font-medium">{contagem}</span>
        {/* Decisão 56b — o SEGUNDO número, e ele nasce depois do primeiro na
            ordem do DOM, que é a ordem em que o leitor de tela o anuncia.
            `font-normal` + `opacity-80`: o olho tem de bater no `x de y`
            primeiro, e um percentual com o mesmo peso disputaria a leitura de
            2 segundos com o número que manda. */}
        {percentualTempo && (
          <span
            className="shrink-0 font-normal opacity-80"
            title={'Percentual do TEMPO típico deste ciclo, ponderado pela '
              + 'duração de cada membro — não é percentual de pipelines, e não '
              + 'é previsão de conclusão. Só aparece quando todos os membros '
              + 'têm histórico suficiente.'}
          >
            · {percentualTempo}
          </span>
        )}
        {travados && (
          onTravados ? (
            <button
              type="button"
              onClick={onTravados}
              title="Ver o que está travando este ciclo"
              className="ml-auto inline-flex shrink-0 items-center gap-1 rounded border border-red-300 bg-red-100 px-1 py-px text-[10px] font-semibold text-red-700 hover:bg-red-200 dark:border-red-700 dark:bg-red-900/60 dark:text-red-300 dark:hover:bg-red-900"
            >
              <AlertTriangle size={10} aria-hidden="true" /> {travados}
            </button>
          ) : (
            <span className="ml-auto inline-flex shrink-0 items-center gap-1 rounded border border-red-300 bg-red-100 px-1 py-px text-[10px] font-semibold text-red-700 dark:border-red-700 dark:bg-red-900/60 dark:text-red-300">
              <AlertTriangle size={10} aria-hidden="true" /> {travados}
            </span>
          )
        )}
      </div>
      {/* Decisão 53: a subtração vem SEMPRE junto do "x de y" — é ela que
          impede "2 de 2 · concluída, verde" num sábado em que alguém inativou
          5 dos 7 membros na sexta-feira. */}
      {membros && <span className="opacity-80">{membros}</span>}
      {/* Decisão 45: a barra encheu e a corrida NÃO acabou. A regra antes da
          hora, porque o relógio reinicia a cada movimento. */}
      {fechamento && <span className="opacity-80">↳ {fechamento}</span>}
    </div>
  )
}
