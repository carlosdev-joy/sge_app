import { useMemo, type ReactNode } from 'react'
import {
  Activity, AlertTriangle, Hourglass, Layers, RefreshCw, Search, ShieldAlert,
} from 'lucide-react'
import { Tabs } from '../ui/Tabs'
import { CritBadge } from './CritBadge'
import {
  CLASSES_TRAVADAS, ROTULO_EVENTO_CORRIDA, ROTULO_PENDENCIA, estiloEvento,
  textoAlcance, type ExecucaoPipeline,
} from './statusExecucao'
import { decorridoMin, duracaoEntre, horaCurta, textoDuracao } from './tempoCorrida'
import {
  mapaTipicos, marcaAtipica, textoTipico, tipicoDe, tituloAtipico,
} from './duracaoTipica'
import type { CorridaApi, PendenteCorrida, TipicosApi } from '../../types'

// ─────────────────────────────────────────────────────────────────────────────
// O PAINEL LATERAL DA CORRIDA — spec docs/spec-malha-execucao.md §9.5 (F10).
//
// ── O buraco que ele fecha ──────────────────────────────────────────────────
// Até aqui o painel lateral era de EVENTOS DA GUARDIÃ — e corrida saudável não
// gera evento, então ele ficava VAZIO justamente durante a corrida. Descobrir
// o que estava rodando era varrer o canvas com o olho procurando anel azul.
//
// ── Três abas, e a que abre é derivada da SAÚDE (Decisão 62) ────────────────
//   COM_FALHA | ATRASADA | SEM_PROGRESSO → Travando
//   OK                                    → Agora
//   corrida fechada                       → Eventos
// Quando o operador abre o painel às 3h, as perguntas "está rodando?" e "em que
// pé está?" já foram respondidas pelo card ou pelo alarme que o trouxe até
// aqui: obrigá-lo a clicar em `Travando` é um clique a mais na única coisa que
// ele veio fazer.
//
// ── Um clique até o problema ────────────────────────────────────────────────
// Clicar na LINHA acende a cadeia no canvas e centraliza o nó — sem sair da
// lente de execução. O botão `▶ etapas` desce ao pipeline sem exigir que o
// operador ache o nó no desenho.
//
// ── O que este painel NÃO faz ───────────────────────────────────────────────
//   • não soma classes distintas em "3 pendentes" (Decisão 21/D75#10): são
//     três problemas com três donos, e a ação é diferente em cada um;
//   • não conta linha de `execucoes[]` para dizer progresso (D75/#5) — os
//     números vêm do agregado; daqui saem só os NOMES;
//   • não pinta `nao_partiu` de vermelho: às 01:10 ele é o estado normal de
//     todo membro de toda corrida recém-aberta.
// ─────────────────────────────────────────────────────────────────────────────

export type AbaCorrida = 'agora' | 'travando' | 'eventos'

/** Evento já unificado pelo editor (guardiã + nós observadores + ciclo). */
export interface EventoPainelCorrida {
  rotulo: string
  ehNo: boolean
  tipo: string
  criado_em: string
  mensagem: string | null
  /** `undefined` = a coluna não veio; `null` = na fila; texto = avisado. */
  notificado_em?: string | null
}

export interface PainelCorridaLateralProps {
  corrida: CorridaApi | null
  execucoes: ExecucaoPipeline[]
  eventos: EventoPainelCorrida[]
  aba: AbaCorrida
  onAba: (aba: AbaCorrida) => void
  /** Acende a cadeia no canvas e centraliza o nó — sem sair da lente. */
  onFocar: (pipeline: string) => void
  /** Drill-down até as etapas. Ausente = o gesto some (a malha segue igual). */
  onAbrirEtapas?: (pipeline: string) => void
  /** Decisão 65 — o botão SÓ existe com a frase do efeito na corrida em voo.
   *  O editor só passa este callback com uma corrida ABERTA em foco, que é a
   *  condição em que a frase pode ser escrita com certeza. */
  onReexecutar?: (pipeline: string) => void
  /** A frase da Decisão 65, escrita pelo editor (que conhece o ciclo). */
  fraseReexecucao?: string | null
  /** F12 (Decisão 64) — a duração típica por membro, com `n` e piso `n ≥ 5` já
   *  aplicados no servidor. Ausente/`null` = não apurei: a linha mostra só o
   *  decorrido, exatamente como antes desta fase. */
  tipicos?: TipicosApi | null
  /** Instante local da resposta e o relógio local — Decisão 60. */
  respostaEm: number
  agoraLocal: number
}

const STATUS_VIVO = new Set(['EXECUTANDO', 'AGUARDANDO_DEPENDENCIA'])

const ICONE_CLASSE: Record<string, typeof AlertTriangle> = {
  falhou: AlertTriangle,
  orfa: AlertTriangle,
  nao_liberou: Hourglass,
  nao_partiu: Hourglass,
}

/** Vermelho para o que ACABOU MAL, âmbar para o que está esperando — a mesma
 *  partição de cor da faixa e do card (Decisão 59): o painel não pode discordar
 *  de si mesmo três centímetros acima. */
const COR_CLASSE: Record<string, string> = {
  falhou: 'text-red-600 dark:text-red-400',
  orfa: 'text-red-600 dark:text-red-400',
  nao_liberou: 'text-amber-600 dark:text-amber-400',
  nao_partiu: 'text-dim',
}

const LINHA =
  'rounded-md border border-edge bg-canvas px-2 py-1.5 transition-colors hover:border-blue-400'

/** O CORPO da linha é um `<button>` de verdade, e as ações são IRMÃS dele.
 *  Botão dentro de `div role="button"` desenha igual e mente para o leitor de
 *  tela (um controle dentro do outro), então o clique da linha mora aqui. */
function CorpoDaLinha({
  onClick, title, children,
}: { onClick: () => void; title: string; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="w-full text-left"
    >
      {children}
    </button>
  )
}

function BotaoAcao({
  onClick, title, children,
}: { onClick: () => void; title: string; children: ReactNode }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded border border-edge px-1.5 py-px text-[10px] font-medium text-dim transition-colors hover:bg-panel hover:text-ink"
    >
      {children}
    </button>
  )
}

export function PainelCorridaLateral({
  corrida, execucoes, eventos, aba, onAba, onFocar, onAbrirEtapas,
  onReexecutar, fraseReexecucao = null, tipicos = null, respostaEm, agoraLocal,
}: PainelCorridaLateralProps) {
  // ── Quem está vivo AGORA — os NOMES saem de `execucoes[]`, que já vem ────
  const vivos = useMemo(
    () => execucoes.filter(e => STATUS_VIVO.has(e.status)),
    [execucoes])

  // ── O que está travando — do AGREGADO, calculado uma vez no servidor ─────
  // `nao_partiu` fica de fora da lista vermelha (Decisão 54) e vira a linha
  // quieta do rodapé da aba.
  const travando = useMemo<PendenteCorrida[]>(
    () => (corrida?.pendentes ?? []).filter(p => CLASSES_TRAVADAS.has(p.classe)),
    [corrida])
  const naoPartiram = useMemo(
    () => (corrida?.pendentes ?? []).filter(p => p.classe === 'nao_partiu'),
    [corrida])

  // ── A duração típica de cada membro (F12, Decisão 64) ────────────────────
  // O índice é em `casefold` porque as duas pontas escrevem o nome com a
  // grafia de origens diferentes (a oficial de `etl_pipeline` em `execucoes[]`,
  // a do snapshot em `tipicos[]`) — e o `Map` distingue caixa onde o banco não
  // distingue.
  const tipicoPorPipeline = useMemo(() => mapaTipicos(tipicos), [tipicos])

  /** Há quanto tempo esta linha está assim, EM MINUTOS. Os dois carimbos são
   *  do BANCO (`inicio` e `apurado_em`), subtraídos entre si, e só depois
   *  somados ao que passou no relógio LOCAL desde a resposta (Decisão 60).
   *  Nunca `Date.now() − inicio`: no dev o banco está 3h à frente do
   *  navegador. */
  const minutosDesde = (carimbo: string | null): number | null =>
    decorridoMin(duracaoEntre(carimbo, corrida?.apurado_em),
                 respostaEm, agoraLocal)

  const abas = [
    {
      id: 'agora',
      label: 'Agora',
      badge: vivos.length,
      // `Agora (2)` são dois pipelines SAUDÁVEIS rodando: com o badge vermelho
      // de sempre, o operador leria "2 problemas" às 3h.
      badgeTom: 'neutro' as const,
    },
    { id: 'travando', label: 'Travando', badge: travando.length },
    { id: 'eventos', label: 'Eventos', badge: eventos.length,
      badgeTom: 'neutro' as const },
  ]

  return (
    <div className="flex w-72 shrink-0 flex-col border-r border-edge bg-panel">
      <Tabs
        tabs={abas}
        active={aba}
        onChange={id => onAba(id as AbaCorrida)}
        size="sm"
      />
      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-2">

        {/* ── AGORA ─────────────────────────────────────────────────────── */}
        {aba === 'agora' && (vivos.length === 0 ? (
          <p className="px-1 py-4 text-center text-[11px] leading-relaxed text-dim">
            Nenhum pipeline em execução agora.
          </p>
        ) : vivos.map(e => {
          const esperando = e.status === 'AGUARDANDO_DEPENDENCIA'
          const minutos = minutosDesde(e.inicio)
          const ha = minutos === null ? null : textoDuracao(minutos)
          const tipico = tipicoDe(tipicoPorPipeline, e.pipeline_name)
          const quantoCostuma = textoTipico(tipico)
          // A marca só existe para quem está RODANDO. Quem espera acumula
          // tempo de FILA, e comparar fila com duração de execução seria somar
          // duas coisas diferentes para pintar um alerta — o membro apareceria
          // âmbar por causa do vizinho que travou, não do próprio tempo.
          const marca = esperando
            ? null
            : marcaAtipica(minutos, tipico)
          return (
            <div key={e.pipeline_name} className={LINHA}>
              <CorpoDaLinha
                onClick={() => onFocar(e.pipeline_name)}
                title="Acender a cadeia deste pipeline no desenho e centralizar o nó"
              >
                <span className="flex items-center gap-1.5">
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${esperando ? 'bg-amber-500' : 'animate-pulse bg-blue-500'}`}
                    aria-hidden="true"
                  />
                  <span className="truncate font-mono text-[11px] text-ink">
                    {e.pipeline_name}
                  </span>
                  {/* ⚠ 2x — âmbar, e SÓ aqui: é leitura de tela, não evento.
                      Um alarme por "está demorando" tocaria toda madrugada, e
                      alarme que toca sempre é alarme que ninguém lê. */}
                  {marca && (
                    <span
                      className="ml-auto shrink-0 rounded border border-amber-300 bg-amber-50 px-1 py-px text-[9px] font-bold text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                      title={tituloAtipico(tipico) ?? undefined}
                    >
                      {marca}
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-[10px] text-dim">
                  {esperando
                    ? (e.faltantes && e.faltantes.length > 0
                      ? `esperando ${e.faltantes.join(', ')}`
                      : 'esperando outro pipeline')
                    : (ha ? `rodando há ${ha}` : 'em execução')}
                  {esperando && ha ? ` · há ${ha}` : ''}
                  {/* A duração típica DESTE membro (Decisão 64) — o número que
                      responde "posso esperar". Sem amostra (`n < 5`) o servidor
                      não manda o item e aqui não sobra nada: fica só o
                      decorrido, sem "típico" e sem `n` solto. */}
                  {quantoCostuma ? ` · ${quantoCostuma}` : ''}
                </span>
              </CorpoDaLinha>
              {onAbrirEtapas && (
                <div className="mt-1 flex flex-wrap gap-1">
                  <BotaoAcao
                    onClick={() => onAbrirEtapas(e.pipeline_name)}
                    title={`Abrir ${e.pipeline_name} etapa a etapa nesta data`}
                  >
                    <Layers size={10} aria-hidden="true" /> etapas
                  </BotaoAcao>
                </div>
              )}
            </div>
          )
        }))}

        {/* ── TRAVANDO ──────────────────────────────────────────────────── */}
        {aba === 'travando' && (
          <>
            {travando.length === 0 && naoPartiram.length === 0 && (
              <p className="px-1 py-4 text-center text-[11px] leading-relaxed text-dim">
                {corrida
                  ? 'Nada travando — os pendentes estão em dia.'
                  : 'Sem corrida nesta lente: não há o que travar.'}
              </p>
            )}
            {travando.map(p => {
              const Icone = ICONE_CLASSE[p.classe] ?? AlertTriangle
              const alcance = textoAlcance(p)
              const podeRerodar = onReexecutar
                && (p.classe === 'falhou' || p.classe === 'orfa')
              return (
                <div key={p.pipeline} className={LINHA}>
                  <CorpoDaLinha
                    onClick={() => onFocar(p.pipeline)}
                    title="Acender a cadeia deste pipeline no desenho e centralizar o nó"
                  >
                    <span className="flex items-center gap-1.5">
                      <Icone
                        size={11}
                        className={`shrink-0 ${COR_CLASSE[p.classe] ?? 'text-dim'}`}
                        aria-hidden="true"
                      />
                      <span className="truncate font-mono text-[11px] text-ink">
                        {p.pipeline}
                      </span>
                      {/* A criticidade é o segundo número da Decisão 63: ela
                          muda a resposta muito mais que o total. */}
                      {p.criticidade && <CritBadge crit={p.criticidade} />}
                    </span>
                    <span className={`mt-0.5 block text-[10px] ${COR_CLASSE[p.classe] ?? 'text-dim'}`}>
                      {ROTULO_PENDENCIA[p.classe] ?? p.classe}
                      {p.desde ? ` desde ${horaCurta(p.desde)}` : ''}
                    </span>
                    {/* De quem ele espera — a resposta do MESMO predicado do
                        motor, agora em lote (nunca um "mais recente"
                        paralelo). `faltantes` ausente = não apurado; `[]` =
                        não falta ninguém, que é outra coisa e outra
                        investigação. */}
                    {p.faltantes && p.faltantes.length > 0 && (
                      <span className="mt-0.5 block truncate text-[10px] text-dim"
                            title={p.faltantes.join(', ')}>
                        esperando {p.faltantes.join(', ')}
                      </span>
                    )}
                    {alcance && (
                      <span className="mt-0.5 block text-[10px] font-medium text-dim">
                        {alcance}
                      </span>
                    )}
                  </CorpoDaLinha>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <BotaoAcao
                      onClick={() => onFocar(p.pipeline)}
                      title="Acender a cadeia deste pipeline e centralizar o nó no desenho"
                    >
                      <Search size={10} aria-hidden="true" /> realçar cadeia
                    </BotaoAcao>
                    {onAbrirEtapas && (
                      <BotaoAcao
                        onClick={() => onAbrirEtapas(p.pipeline)}
                        title={`Abrir ${p.pipeline} etapa a etapa nesta data`}
                      >
                        <Layers size={10} aria-hidden="true" /> etapas
                      </BotaoAcao>
                    )}
                    {podeRerodar && (
                      <BotaoAcao
                        onClick={() => onReexecutar(p.pipeline)}
                        /* Decisão 65: a frase do efeito na corrida em voo vem
                           ANTES do clique. Sem ela o editor não passa o
                           callback e este botão simplesmente não existe. */
                        title={fraseReexecucao
                          ?? 'Abrir a prévia da reexecução deste pipeline'}
                      >
                        <RefreshCw size={10} aria-hidden="true" /> reexecutar
                      </BotaoAcao>
                    )}
                  </div>
                </div>
              )
            })}
            {/* Número, nunca alarme: "ainda não começou" às 01:10 e "não chegou
                a iniciar" às 04:00 são o mesmo dado com relógios diferentes. */}
            {naoPartiram.length > 0 && (
              <p className="px-1 pt-1 text-[10px] leading-snug text-dim">
                {naoPartiram.length === 1
                  ? '1 membro ainda não começou'
                  : `${naoPartiram.length} membros ainda não começaram`}
                : <span className="font-mono">
                  {naoPartiram.slice(0, 6).map(p => p.pipeline).join(', ')}
                  {naoPartiram.length > 6 ? ` +${naoPartiram.length - 6}` : ''}
                </span>
              </p>
            )}
          </>
        )}

        {/* ── EVENTOS ───────────────────────────────────────────────────── */}
        {aba === 'eventos' && (eventos.length === 0 ? (
          <p className="px-1 py-4 text-center text-[11px] leading-relaxed text-dim">
            Nenhum evento nesta corrida.
          </p>
        ) : eventos.map((ev, i) => (
          <div key={`${ev.rotulo}-${ev.criado_em}-${i}`}
               className="rounded-md border border-edge bg-canvas px-2 py-1.5">
            <div className="flex items-center gap-1.5">
              <span className={`rounded border px-1 py-px text-[9px] font-bold ${estiloEvento(ev.tipo)}`}
                    title={ev.tipo}>
                {ROTULO_EVENTO_CORRIDA[ev.tipo] ?? ev.tipo}
              </span>
              <span className="ml-auto text-[10px] text-dim">
                {horaCurta(ev.criado_em)}
              </span>
            </div>
            <div className={`mt-0.5 truncate text-[10px] text-ink ${ev.ehNo ? 'font-medium' : 'font-mono'}`}
                 title={ev.rotulo}>
              {ev.rotulo}
            </div>
            {ev.mensagem && (
              <p className="mt-0.5 text-[10px] leading-snug text-dim">{ev.mensagem}</p>
            )}
            {/* `notificado_em` existe desde a 067 e nunca foi lido: chave
                ausente = não perguntei (nada se diz), `null` = na fila. */}
            {ev.notificado_em !== undefined && (
              <p className="mt-0.5 text-[10px] text-dim">
                {ev.notificado_em
                  ? `avisado às ${horaCurta(ev.notificado_em)} · Teams`
                  : 'ainda na fila de aviso'}
              </p>
            )}
          </div>
        )))}
      </div>

      {/* Rodapé de identidade do painel — sem ele, três abas soltas no canto
          esquerdo não dizem de QUE eles falam. */}
      <div className="flex items-center gap-1.5 border-t border-edge px-3 py-1.5 text-[10px] text-dim">
        {corrida ? (
          <>
            <Activity size={11} className="shrink-0" aria-hidden="true" />
            <span>o que esta corrida está fazendo</span>
          </>
        ) : (
          <>
            <ShieldAlert size={11} className="shrink-0" aria-hidden="true" />
            <span>eventos do monitor automático nesta data</span>
          </>
        )}
      </div>
    </div>
  )
}
