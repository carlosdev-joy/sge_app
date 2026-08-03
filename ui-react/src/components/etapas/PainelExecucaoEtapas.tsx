// Chrome do modo Execução do canvas de Etapas (F3, §3 Bloco A): a barra
// superior (data de referência + janela + resumo), os avisos honestos (vazio,
// ambiguidade, degradação, Airflow fora do ar) e a legenda do rodapé.
//
// Mora fora do FluxoEditor de propósito — o editor já tem 2.3k linhas e o
// modo Montagem não pode pagar por isto. A linguagem é a MESMA do MalhaEditor
// (mesmos controles de data, mesmo formato de banner, mesma legenda por
// bolinha), porque descer da malha para cá tem de parecer a mesma tela.
import type { ReactNode } from 'react'
import {
  Activity, AlertCircle, AlertTriangle, ChevronLeft, ChevronRight, Info,
  MousePointerClick, RefreshCw,
} from 'lucide-react'
import { STATUS_EXECUCAO, ORDEM_LEGENDA } from '../malhas/statusExecucao'
import {
  duracaoCurta, horaLonga, janelaDasEtapas, resumoExecucao, rotuloCorrida,
  textoRazao, type PipelineExecucaoApi,
} from './execucaoEtapas'

// Mesmo cálculo de dia do MalhaEditor (somaDia) — duplicado aqui em vez de
// importado para não puxar o módulo da malha inteiro para o chunk do canvas.
function somaDia(iso: string, delta: number): string {
  const d = new Date(`${iso}T12:00:00`)
  if (isNaN(d.getTime())) return iso
  d.setDate(d.getDate() + delta)
  return d.toISOString().slice(0, 10)
}

const navBtnCls =
  'inline-flex items-center px-1.5 py-1 rounded-md text-xs border border-edge bg-canvas ' +
  'text-dim hover:text-ink hover:bg-edge/40 transition-colors disabled:opacity-40 disabled:pointer-events-none'

interface BarraProps {
  pipeline: string
  /** data EXIBIDA (a pedida, ou o ODATE que o servidor calculou) */
  dataExibida: string
  /** null = já está no ODATE corrente (botão "hoje" desabilitado) */
  dataPedida: string | null
  onData: (d: string | null) => void
  carregando: boolean
  dados: PipelineExecucaoApi | undefined
  erro: Error | null
  /** corrida escolhida à mão no aviso de ambiguidade (run_id) */
  corridaEscolhida: string | null
  onCorrida: (runId: string | null) => void
}

// A "volta óbvia" (ex.: Voltar à malha) NÃO mora aqui: ela vive no cabeçalho
// da PÁGINA, junto de "Ver na Lista"/"Fechar", que é onde a navegação da tela
// já estava. Ter o mesmo botão a 40px de distância dele seria só ruído — e o
// do cabeçalho vale nos DOIS modos, este só valeria na Execução.

export function BarraExecucao({
  pipeline, dataExibida, dataPedida, onData, carregando, dados, erro,
  corridaEscolhida, onCorrida,
}: BarraProps) {
  const etapas = dados?.etapas ?? []
  const janela = janelaDasEtapas(etapas)
  const resumo = resumoExecucao(etapas, dados?.pausas)
  const ident = dados?.identidade
  const candidatos = ident?.candidatos ?? []
  const ambiguo = !!ident?.ambiguo && candidatos.length > 1
  // A corrida em exibição: a escolhida à mão, senão a que a identidade resolveu.
  const runExibido = ident?.run_id ?? null

  return (
    <>
      {/* ── Barra superior: modo, data, janela e resumo ─────────────────── */}
      <div className="flex flex-wrap items-center gap-2 border-b border-edge bg-panel px-3 py-2">
        <span className="inline-flex items-center gap-1 rounded-md bg-[#1A5FA8] px-2.5 py-1 text-xs font-medium text-white">
          <Activity size={12} /> Execução
        </span>
        <span className="font-mono text-[11px] text-dim">{pipeline}</span>

        {/* Janela do pipeline — DERIVADA DAS ETAPAS (decisão registrada em
            execucaoEtapas.ts): nunca os horários de etl_pipeline_execucao. */}
        {janela.inicio && (
          <span
            className="hidden items-center gap-1 text-[11px] text-dim sm:inline-flex"
            title={'Janela derivada das ETAPAS desta execução (min do início, '
              + 'max do fim). Os horários do registro do pipeline usam outro '
              + 'relógio e não entram nesta conta.'}
          >
            ⏱ {horaLonga(janela.inicio)} → {janela.emAndamento ? 'em andamento' : horaLonga(janela.fim)}
            {janela.segundos != null && !janela.emAndamento && (
              <span className="text-dim/70">· {duracaoCurta(janela.segundos)}</span>
            )}
          </span>
        )}

        {/* Resumo honesto: pulado conta em separado, e "sem execução" aparece. */}
        {etapas.length > 0 && (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-dim">
            <span>{resumo.total} etapa{resumo.total !== 1 ? 's' : ''}</span>
            {resumo.sucesso > 0 && <Chip cor="bg-green-500" n={resumo.sucesso} t="sucesso" />}
            {resumo.falha > 0 && <Chip cor="bg-red-500" n={resumo.falha} t="falha" />}
            {resumo.executando > 0 && <Chip cor="bg-blue-500" n={resumo.executando} t="executando" />}
            {resumo.pulado > 0 && <Chip cor="bg-slate-400" n={resumo.pulado} t="pulada" ts="puladas" />}
            {resumo.outros > 0 && <Chip cor="bg-slate-400" n={resumo.outros} t="outro status" ts="outros status" />}
            {resumo.semExecucao > 0 && (
              <Chip cor="bg-slate-300 dark:bg-slate-600" n={resumo.semExecucao}
                t="sem execução" ts="sem execução" />
            )}
            {/* (F5) Os dois chips separados de propósito: "em espera" é o
                processo PARADO agora; "pausa marcada" é um pedido que ainda não
                segurou nada. Somar os dois esconderia a única diferença que
                importa para quem está olhando a tela durante um incidente. */}
            {resumo.emEspera > 0 && (
              <Chip cor="bg-fuchsia-500" n={resumo.emEspera}
                t="em espera" ts="em espera" />
            )}
            {resumo.pausaMarcada > 0 && (
              <Chip cor="bg-fuchsia-300 dark:bg-fuchsia-800" n={resumo.pausaMarcada}
                t="pausa marcada" ts="pausas marcadas" />
            )}
          </span>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-dim">Data de referência</span>
          <button
            onClick={() => onData(somaDia(dataExibida, -1))}
            disabled={!dataExibida}
            title="Dia anterior"
            className={navBtnCls}
          >
            <ChevronLeft size={13} />
          </button>
          <input
            type="date"
            value={dataExibida}
            onChange={e => onData(e.target.value || null)}
            aria-label="Data de referência da execução"
            className="rounded-md border border-edge bg-canvas px-2 py-1 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40"
          />
          <button
            onClick={() => onData(somaDia(dataExibida, 1))}
            disabled={!dataExibida}
            title="Dia seguinte"
            className={navBtnCls}
          >
            <ChevronRight size={13} />
          </button>
          <button
            onClick={() => onData(null)}
            disabled={dataPedida === null}
            title="Voltar à data de referência corrente (ODATE, calculado pela virada global)"
            className={`${navBtnCls} px-2`}
          >
            hoje
          </button>
          {carregando && <RefreshCw size={12} className="animate-spin text-dim" />}
        </div>
      </div>

      {/* ── Avisos ──────────────────────────────────────────────────────── */}
      {erro && (
        <Banner tom="erro" icone={<AlertCircle size={14} className="shrink-0" />}>
          Não foi possível carregar a execução desta data: {erro.message || 'erro desconhecido'}
        </Banner>
      )}

      {dados?.migration_067_pendente && (
        <Banner tom="alerta" icone={<AlertTriangle size={14} className="shrink-0" />}>
          migration 067 pendente — a corrida foi resolvida por APROXIMAÇÃO sobre
          a telemetria das etapas (agrupada pela janela do ODATE). Os horários
          continuam sendo os reais das etapas; o que é aproximado é a associação
          corrida ↔ data.
        </Banner>
      )}

      {dados?.airflow_indisponivel && (
        <Banner tom="alerta" icone={<AlertTriangle size={14} className="shrink-0" />}>
          O Airflow não respondeu — a identidade da corrida pode estar
          incompleta. O que foi possível ler está na tela; nada foi inventado.
        </Banner>
      )}

      {/* Vazio ≠ erro: o desenho abre neutro e a razão é dita por extenso. */}
      {dados?.vazio && !erro && (
        <Banner tom="info" icone={<Info size={14} className="shrink-0" />}>
          {textoRazao(dados.razao)}{' '}
          <strong className="font-semibold">
            Nenhuma etapa aparece como concluída — ausência de linha não é sucesso.
          </strong>
        </Banner>
      )}

      {/* Ambiguidade: DECLARA qual corrida está na tela e oferece as outras. */}
      {ambiguo && (
        <div className="border-b border-amber-200 bg-amber-50 px-3 py-1.5 dark:border-amber-800 dark:bg-amber-900/20">
          <div className="flex items-start gap-1.5 text-[11px] text-amber-800 dark:text-amber-300">
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            <span>
              <strong>{candidatos.length} corridas</strong> deste pipeline em{' '}
              {dataExibida}. A tela mostra{' '}
              {corridaEscolhida ? 'a que você escolheu' : 'a mais recente'}
              {ident?.regra ? ` (regra ${ident.regra} — a MESMA do painel da malha)` : ''}.
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {candidatos.map((c, i) => {
              const atual = !!c.run_id && c.run_id === runExibido
              return (
                <button
                  key={c.run_id ?? `sem-run-${i}`}
                  disabled={atual || !c.run_id}
                  onClick={() => onCorrida(c.run_id)}
                  title={c.run_id ?? undefined}
                  className={[
                    'inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] transition-colors',
                    atual
                      ? 'border-amber-400 bg-amber-100 font-semibold text-amber-900 dark:border-amber-600 dark:bg-amber-900/50 dark:text-amber-200'
                      : 'border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50',
                  ].join(' ')}
                >
                  {atual && <span className="shrink-0">▸</span>}
                  <span className="truncate">{rotuloCorrida(c)}</span>
                </button>
              )
            })}
            {corridaEscolhida && (
              <button
                onClick={() => onCorrida(null)}
                className="inline-flex items-center gap-1 rounded border border-amber-300 px-1.5 py-0.5 text-[10px] text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-900/50"
              >
                voltar à mais recente
              </button>
            )}
          </div>
          <p className="mt-1 text-[10px] leading-snug text-amber-700/80 dark:text-amber-400/80">
            O horário “registro” identifica a corrida em{' '}
            <span className="font-mono">etl_pipeline_execucao</span> e usa outro
            relógio — os horários do canvas vêm sempre das etapas da execução em
            exibição.
          </p>
        </div>
      )}
    </>
  )
}

function Chip({ cor, n, t, ts }: { cor: string; n: number; t: string; ts?: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`h-1.5 w-1.5 rounded-full ${cor}`} />
      {n} {n === 1 ? t : (ts ?? `${t}s`)}
    </span>
  )
}

function Banner({ tom, icone, children }: {
  tom: 'info' | 'alerta' | 'erro'
  icone: ReactNode
  children: ReactNode
}) {
  const cls = tom === 'erro'
    ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
    : tom === 'alerta'
      ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
      : 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200'
  return (
    <div className={`flex items-start gap-2 border-b px-3 py-2 text-[12px] ${cls}`}>
      {icone}
      <span>{children}</span>
    </div>
  )
}

// ── Legenda do rodapé — os mesmos status da malha + os dois estados que só
// existem no nível de etapa (sem execução e ramo não tomado). ────────────────
export function LegendaExecucao() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-edge bg-panel px-3 py-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">Legenda</span>
      {ORDEM_LEGENDA.filter(s => s !== 'AGUARDANDO_DEPENDENCIA' && s !== 'NAO_LIBEROU').map(s => {
        const e = STATUS_EXECUCAO[s]
        return (
          <span key={s} className="flex items-center gap-1 text-[10px] text-dim">
            <span className={`h-2 w-2 rounded-full ${e.dot} ${e.animado ? 'animate-pulse' : ''}`} />
            {e.rotulo}
          </span>
        )
      })}
      <span className="flex items-center gap-1 text-[10px] text-dim"
        title="A etapa está no desenho e não tem linha de execução nesta data. Neutra — nunca verde.">
        <span className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />
        sem execução
      </span>
      {/* (F5) Desenhado à mão, e não pela ORDEM_LEGENDA: 'em espera' só existe
          no nível de ETAPA — pôr na lista compartilhada faria a legenda da
          MALHA oferecer um estado que nenhum pipeline dela tem. */}
      <span className="flex items-center gap-1 text-[10px] text-dim"
        title={'A etapa está parada no portão, aguardando alguém liberar. Só dá '
          + 'para pausar etapa que ainda não começou — se ela já estava rodando, '
          + 'a pausa vale para as seguintes.'}>
        <span className={`h-2 w-2 rounded-full ${STATUS_EXECUCAO.EM_ESPERA.dot} animate-pulse`} />
        {STATUS_EXECUCAO.EM_ESPERA.rotulo}
      </span>
      <span className="flex items-center gap-1 text-[10px] text-dim"
        title="Ligação para uma etapa PULADA (ramo de decisão não tomado): tracejada e apagada.">
        <svg width="18" height="6" aria-hidden className="opacity-40">
          <line x1="0" y1="3" x2="18" y2="3" stroke="currentColor" strokeWidth="2" strokeDasharray="6 5" />
        </svg>
        ramo não tomado
      </span>
      <span className="ml-auto flex items-center gap-1 text-[10px] text-dim">
        <MousePointerClick size={11} /> clique num nó para acender a cadeia de dependências
      </span>
    </div>
  )
}
