import { useEffect, useRef, useState } from 'react'
import { CalendarDays, ChevronDown } from 'lucide-react'
import { estiloCorrida, quemFez, rotuloCorrida } from './statusExecucao'
import { tituloDoBloco } from './historicoCorridas'
import { diaCurto, horaCurta } from './tempoCorrida'
import type { CorridaCabecalho } from '../../types'

// ─────────────────────────────────────────────────────────────────────────────
// A FAIXA DAS ÚLTIMAS CORRIDAS — spec docs/spec-malha-execucao.md §9.6/§9.13
// (Decisão 42).
//
// ── Por que UM mecanismo, e não quatro ──────────────────────────────────────
// A tela tinha `◀ ▶` + `input[type=date]` + botão `agora`, e a fase pedia mais
// uma faixa. Quatro mecanismos de navegação temporal na mesma barra é decisão
// adiada, não flexibilidade: às 3h usa-se UM. Aqui a navegação é a FAIXA — os
// últimos ciclos, em ordem, clicáveis, com o corrente destacado —, e a data
// vira um ITEM DO MENU ("ir para uma data…"), que é o que ela sempre foi: um
// atalho, não a identidade.
//
// ── Por que a faixa e não o dropdown ────────────────────────────────────────
// A pergunta de plantão é "está pior que ontem?", e ela se responde de relance:
// nove blocos verdes e um vermelho é NOVIDADE (escala); três vermelhos
// seguidos no mesmo membro é CRÔNICO (espera o horário comercial). Um dropdown
// esconde a série inteira atrás de um clique.
//
// ── Duas corridas do MESMO dia (Decisão 42) ─────────────────────────────────
// São DOIS blocos, sempre — é para isso que a `sequencia` existe. Navegar por
// data resolveria para "a de maior sequência" e esconderia a primeira, que é
// exatamente o ciclo que o operador quer ver depois de um redisparo às 5h.
// Trocar entre elas aplica a LENTE (`?corrida={id}`), então elas nunca se
// sobrepõem no canvas.
//
// ── Estados ────────────────────────────────────────────────────────────────
//   • 1 corrida  → faixa de um bloco, sem controles mortos (nada de ◀ ▶
//     desabilitados ocupando espaço para dizer que não há para onde ir);
//   • 0 corridas → a faixa não é renderizada; sobra o menu de data, que é o
//     que funciona sem a 085 (o painel por dia é o de sempre);
//   • erro/carregando → idem: o menu de data continua servindo.
// ─────────────────────────────────────────────────────────────────────────────

export interface SeletorCorridaProps {
  /** Da mais NOVA para a mais antiga (é como `GET /corridas` entrega). */
  corridas: CorridaCabecalho[]
  /** A corrida em foco. `null` = a lente está numa data, não numa corrida. */
  corridaId: number | null
  onTrocar: (c: CorridaCabecalho) => void
  /** Data em exibição ('YYYY-MM-DD') — o valor do atalho de data. */
  dataExibida: string
  onIrParaData: (dia: string) => void
  /** Voltar ao que está acontecendo agora (sem lente e sem data). */
  onAgora: () => void
  /** Já está no "agora"? Desabilita o item em vez de escondê-lo. */
  noAgora: boolean
  carregando?: boolean
}

/** Quantos blocos cabem antes de a faixa virar tapete. Dez é o que o desenho
 *  da §9.13 mostra e o que uma quinzena de madrugadas exige para responder
 *  "está pior que antes?" sem rolagem. */
const BLOCOS_VISIVEIS = 10

export function SeletorCorrida({
  corridas, corridaId, onTrocar, dataExibida, onIrParaData, onAgora, noAgora,
  carregando = false,
}: SeletorCorridaProps) {
  const [menuAberto, setMenuAberto] = useState(false)
  const raiz = useRef<HTMLDivElement>(null)

  // Fecha em clique-fora e Esc — o mesmo contrato do `ui/DropdownMenu`. Não se
  // reusa aquele componente porque o conteúdo aqui não é uma lista de itens:
  // é um `input[type=date]`, e enfiá-lo num `role="menu"` daria a um campo de
  // formulário a semântica de item de menu.
  useEffect(() => {
    if (!menuAberto) return
    const fora = (alvo: EventTarget | null) =>
      raiz.current != null && !raiz.current.contains(alvo as Node)
    const onDown = (e: MouseEvent) => { if (fora(e.target)) setMenuAberto(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuAberto(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuAberto])

  // Da mais ANTIGA para a mais nova, esquerda → direita: é a ordem do tempo, e
  // é a que faz "a última" ficar onde o olho a procura (na ponta direita,
  // encostada no presente).
  const blocos = corridas.slice(0, BLOCOS_VISIVEIS).slice().reverse()

  return (
    <div ref={raiz} className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {blocos.length > 0 && (
        <>
          <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">
            Corridas
          </span>
          <div
            className="flex items-end gap-1"
            role="group"
            aria-label="Últimas ciclos desta malha"
          >
            {blocos.map(c => {
              const estilo = estiloCorrida(c.status)
              const emFoco = c.id === corridaId
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => onTrocar(c)}
                  /* `aria-pressed` porque o botão AGE COMO FILTRO da tela
                     inteira (molde de PainelRealce): quem usa leitor precisa
                     saber qual bloco está aplicado, e não só que existe. */
                  aria-pressed={emFoco}
                  /* F12 (Decisões 67 e 68) — o `title` deixa de ser só o nome:
                     `04/08 · concluída · 2h41 · travou: CARGA_A`, mais quem
                     encerrou, por qual porta e com que motivo. É o que
                     transforma dez quadradinhos coloridos em DIAGNÓSTICO —
                     três madrugadas seguidas travando no mesmo membro é
                     crônico e espera o horário comercial; nove verdes e uma
                     vermelha é novidade e escala.

                     O `aria-label` continua CURTO de propósito: leitor de tela
                     lê o rótulo do botão a cada passagem de foco, e despejar
                     seis linhas de auditoria em cada um dos dez blocos
                     transformaria a navegação por teclado num parágrafo. */
                  title={tituloDoBloco(c, s => estiloCorrida(s).rotulo, quemFez)}
                  aria-label={rotuloCorrida(c)}
                  className={`h-5 w-3.5 shrink-0 rounded-sm transition-all ${estilo.dot} ${
                    emFoco
                      ? 'ring-2 ring-offset-1 ring-blue-500 ring-offset-panel'
                      : 'opacity-60 hover:opacity-100'
                  }`}
                />
              )
            })}
          </div>
          {/* O rótulo por extenso ao lado da faixa: o bloco responde "como foi"
              de relance, mas a corrida EM FOCO precisa ser nomeada — cor não é
              canal único nesta casa. */}
          {corridaId !== null && (
            <span className="text-[11px] text-dim">
              {(() => {
                const c = corridas.find(x => x.id === corridaId)
                if (!c) return null
                const dia = diaCurto(c.data_referencia) ?? c.data_referencia
                const nome = c.sequencia > 1
                  ? `${c.sequencia}º ciclo de ${dia}`
                  : `ciclo de ${dia}`
                const h = horaCurta(c.aberta_em)
                return h ? `${nome} · aberta ${h}` : nome
              })()}
            </span>
          )}
        </>
      )}
      {carregando && blocos.length === 0 && (
        <span className="text-[11px] text-dim">carregando as corridas…</span>
      )}

      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuAberto(o => !o)}
          aria-haspopup="dialog"
          aria-expanded={menuAberto}
          aria-label="Ir para uma data de referência"
          title="Ir para uma data de referência — o dia inteiro, sem lente de ciclo"
          className="inline-flex items-center gap-1 rounded-md border border-edge bg-canvas px-1.5 py-0.5 text-[11px] text-dim transition-colors hover:text-ink"
        >
          <CalendarDays size={12} aria-hidden="true" /> ir para…
          <ChevronDown size={11} aria-hidden="true" />
        </button>
        {menuAberto && (
          <div
            role="dialog"
            aria-label="Ir para uma data de referência"
            // `left-0`, e não `right-0`: o gatilho é o PRIMEIRO elemento da
            // faixa, colado na borda esquerda do painel. Alinhado pela
            // direita, os 16rem do menu se estendiam para fora da área de
            // conteúdo e sumiam por baixo do menu lateral — o seletor de data
            // ficava inalcançável, que é o mesmo que não existir.
            className="absolute left-0 z-50 mt-1 flex w-64 flex-col gap-2 rounded-md border border-edge bg-panel p-2 shadow-lg"
          >
            <label className="flex flex-col gap-1 text-[11px] text-dim">
              Data de referência
              <input
                type="date"
                value={dataExibida}
                onChange={e => {
                  if (!e.target.value) return
                  onIrParaData(e.target.value)
                  setMenuAberto(false)
                }}
                aria-label="Data de referência"
                className="rounded-md border border-edge bg-canvas px-2 py-1 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40"
              />
            </label>
            <button
              type="button"
              disabled={noAgora}
              onClick={() => { onAgora(); setMenuAberto(false) }}
              className="rounded-md border border-edge px-2 py-1 text-left text-[11px] text-ink transition-colors hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
            >
              voltar ao que está acontecendo agora
            </button>
            <p className="text-[10px] leading-snug text-dim">
              Navegar por data mostra o DIA INTEIRO. Se aquele dia teve mais de
              uma corrida, escolha uma na faixa: descrever uma corrida sobre a
              lista do dia todo é o card mentindo com layout novo.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
