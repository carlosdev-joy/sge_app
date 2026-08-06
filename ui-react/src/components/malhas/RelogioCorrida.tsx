import { Clock, PauseCircle, TimerReset } from 'lucide-react'
import { Progress } from '../ui/Progress'
import type { ResumoCorrida } from './statusExecucao'
import { textoDuracao } from './tempoCorrida'
import type { ProximaExecucao } from './proximaExecucao'
import type { CorridaApi } from '../../types'

// ─────────────────────────────────────────────────────────────────────────────
// Os RELÓGIOS da corrida — spec docs/spec-malha-execucao.md §9.4 e §9.9 (F10).
//
// Três relógios diferentes, e nenhum deles é o mesmo (Decisão 60):
//   • o DECORRIDO vem do banco (`decorrido_min`, já subtraído lá) somado ao
//     que passou no relógio LOCAL desde a resposta;
//   • o LIMITE DE SEGURANÇA é a razão entre dois carimbos do banco — grandeza
//     adimensional, o único jeito honesto de desenhar essa barra;
//   • o PRÓXIMO GATILHO é hora de parede contra hora de parede, e por isso é o
//     único que pode ser lido do relógio do navegador.
//
// ── Por que as props não são as oito da tabela da §9.9 ──────────────────────
// A tabela lista os campos crus (`aberta_em`, `fechada_em`, `teto_em`…). Este
// componente recebe o `ResumoCorrida` em vez deles porque as frases já nascem
// lá, num módulo PURO testado com o relógio deslocado — e é isso que faz o
// card da lista e a faixa do painel contarem a MESMA história (D75/#5: um
// agregado, uma fonte). Derivar os mesmos textos aqui criaria a segunda fonte
// que a spec inteira existe para matar. A `corrida` vem junto só para os dois
// fatos que o resumo não carrega: se há teto CONFIGURADO e o estado do ciclo.
//
// ── O que este componente NÃO desenha ───────────────────────────────────────
//   • barra de limite em malha SEM `teto_horas` (Decisão 61). O default global
//     de 24h é ANTI-TRAVAMENTO, não SLA: uma barra em 80% às 20h numa malha
//     que sempre fecha em 3h faria escalar por nada. Sem teto configurado só
//     existe a linha do próximo gatilho;
//   • recuo silencioso. Soltar um hold de 6h empurra `teto_em` e a barra ANDA
//     PARA TRÁS — e o crédito vem colado nela, nomeado, porque uma barra de
//     prazo que recua sem explicação destrói a confiança em todas as outras.
// ─────────────────────────────────────────────────────────────────────────────

export interface RelogioCorridaProps {
  corrida: CorridaApi
  /** Todas as frases de tempo já derivadas (módulo puro, uma fonte). */
  resumo: ResumoCorrida
  /** Decisão 61 — o prazo que aparece POR PADRÃO: o próximo gatilho da própria
   *  malha. `null` = malha sem agendamento legível (sob demanda, sem nó
   *  Início): a linha some, nunca vira "sem previsão" inventado. */
  proximoGatilho?: ProximaExecucao | null
  /** Relógio LOCAL, do `useDecorrido` — o mesmo tique da faixa. É o único
   *  relógio que a conta do próximo gatilho consulta. */
  agoraLocal: number
}

/** "em 2h50 (01:00)" — o tempo que falta para a próxima corrida partir.
 *
 *  Conta LOCAL contra LOCAL: `proximaExecucao` já resolveu o instante no
 *  relógio do navegador a partir do agendamento (hora de parede), e aqui se
 *  mede a distância até agora. É a exceção legítima da Decisão 60 — o que ela
 *  proíbe é misturar carimbo do BANCO com `Date.now()`, e nenhum dos dois
 *  lados desta subtração vem do banco. */
function faltaPara(p: ProximaExecucao, agora: number): string {
  if (!p.quando) return p.texto          // cadência sem instante (hourly)
  const min = Math.round((p.quando.getTime() - agora) / 60_000)
  const dur = textoDuracao(min)
  return dur ? `em ${dur} (${p.hora})` : p.texto
}

export function RelogioCorrida({
  corrida, resumo, proximoGatilho = null, agoraLocal,
}: RelogioCorridaProps) {
  const aberta = corrida.status === 'ABERTA'
  // A barra de limite só existe com teto CONFIGURADO na malha (Decisão 61) —
  // e `resumo.prazo` já nasce `null` quando não há. A checagem é do resumo, e
  // não de `teto_configurado` aqui, para não haver duas regras para o mesmo
  // fato: a que decide o texto e a que decide a barra têm de ser a mesma.
  const temLimite = resumo.prazo !== null

  return (
    <div className="flex flex-col gap-0.5 text-[11px]">
      {/* Relativo enquanto aberta ("há 42 min"); ABSOLUTO quando fechada
          ("01:10 → 04:02 · 2h52"). Nunca os dois formatos no mesmo lugar. */}
      {resumo.tempo && (
        <span className="inline-flex items-center gap-1.5">
          <Clock size={11} className="shrink-0" aria-hidden="true" />
          {resumo.tempo}
        </span>
      )}

      {/* O LIMITE DE SEGURANÇA. Sem `teto_horas` na malha esta linha inteira
          não existe — nem a barra, nem o texto (Decisão 61). */}
      {temLimite && (
        <span className="inline-flex items-center gap-1.5">
          {resumo.prazoPct !== null && (
            <Progress
              className="w-20"
              segmentos={[{
                chave: 'limite',
                valor: resumo.prazoPct,
                cor: resumo.prazoPct >= 100
                  ? 'bg-red-500 dark:bg-red-500'
                  : 'bg-amber-500 dark:bg-amber-500',
                rotulo: 'do limite decorrido',
              }]}
              total={100}
              valorAtual={resumo.prazoPct}
              ariaLabel="limite de segurança da corrida"
              /* `aria-valuetext` explícito: sem ele o leitor de tela converte
                 valuenow/valuemax em percentual sozinho. Aqui o percentual É
                 do tempo (não de contagem de pipelines, que a Decisão 56
                 proíbe), mas quem o anuncia tem de ser o texto que a tela
                 mostra — e ele diz "limite", nunca "progresso". */
              valorTexto={resumo.prazo ?? 'limite de segurança'}
            />
          )}
          {resumo.prazo}
        </span>
      )}

      {/* O CRÉDITO vem colado no limite porque ele é a explicação de uma barra
          que andou para trás. Aparece mesmo SEM barra: quem não configurou
          teto próprio também precisa saber que o limite global foi adiado. */}
      {resumo.credito && (
        <span className="inline-flex items-center gap-1.5 text-blue-700 dark:text-blue-300">
          <TimerReset size={11} className="shrink-0" aria-hidden="true" />
          {resumo.credito}
        </span>
      )}

      {/* Decisão 61 — o prazo POR PADRÃO. Às 04:00 "faltam 21h de teto" é
          irrelevante; o que importa é que a próxima corrida parte às 01:00 e a
          corrida aberta BLOQUEIA essa partida. A consequência só é dita com a
          corrida ABERTA: com ela fechada, o gatilho é informação, não trava. */}
      {proximoGatilho && (
        <span className="inline-flex flex-wrap items-center gap-x-1.5 opacity-90">
          <Clock size={11} className="shrink-0" aria-hidden="true" />
          <span>a próxima corrida parte {faltaPara(proximoGatilho, agoraLocal)}</span>
          {aberta && (
            <span className="font-medium">
              — enquanto esta não fechar, ela não abre
            </span>
          )}
        </span>
      )}

      {/* O HOLD: com nó segurado os relógios NÃO ESTÃO CORRENDO (Decisão 30) —
          nem o teto, nem a quiescência. Dizer isso é o que impede a barra
          congelada de parecer defeito. */}
      {resumo.hold && (
        <span className="inline-flex w-fit items-center gap-1 rounded border border-amber-300 bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800 dark:border-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
          <PauseCircle size={11} className="shrink-0" aria-hidden="true" />
          {resumo.hold}
        </span>
      )}

      {/* Decisão 45 — a REGRA antes da hora. "fecha 15 min após o último
          movimento; se nada mais mexer, por volta de 04:17": anunciar só a
          hora produziria o chamado falso das 04:18, porque o relógio da
          carência REINICIA a cada movimento. */}
      {resumo.fechamento && (
        <span className="opacity-80">↳ {resumo.fechamento}</span>
      )}
    </div>
  )
}
