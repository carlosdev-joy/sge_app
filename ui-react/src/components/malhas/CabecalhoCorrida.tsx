import { useState, type ReactNode } from 'react'
import {
  AlertTriangle, BellOff, PauseCircle, Unlock,
} from 'lucide-react'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Skeleton } from '../ui/Skeleton'
import { CorridaProgresso } from './CorridaProgresso'
import { RelogioCorrida } from './RelogioCorrida'
import { CORRIDA_INTERROMPIDA, type ResumoCorrida } from './statusExecucao'
import { carimboLongo, frescor, horaCurta } from './tempoCorrida'
import type { ProximaExecucao } from './proximaExecucao'
import type { CorridaApi } from '../../types'

// ─────────────────────────────────────────────────────────────────────────────
// A FAIXA DA CORRIDA — spec docs/spec-malha-execucao.md §9.6/§9.13 (F10).
//
// Zonas, em ordem FIXA: identidade/estado · progresso · relógio/prazo · travas.
// É a mesma hierarquia do card da lista (estado → progresso → tempo → culpado),
// e ela é fixa porque o olho aprende posição: uma faixa que reordena entre
// refreshes destrói a leitura periférica que ela existe para servir.
//
// ── O que esta faixa substitui ──────────────────────────────────────────────
// O banner verde "Malha concluída em…" (que afirmava conclusão a partir de um
// EVENTO — e o evento da corrida #1 do dia sobrevivia à corrida #2), as duas
// listas de bloqueio (`em_aberto` + `datas_divergentes`) e o texto de fase
// antiga. Quem afirma "concluída" agora é o STATUS DO CICLO, uma vez só.
//
// ── Os três banners da Decisão 66 ───────────────────────────────────────────
// Eles ficam na FAIXA, e não numa aba, porque cada um DECIDE A PRÓXIMA AÇÃO:
//   1. `fora_do_odate` — o incidente que originou esta spec; é o único caso em
//      que a barra está certa e o DIA está errado;
//   2. hold com contador e `Soltar` — hoje o cadeado existe só no nó, sem
//      banner e sem contador: quem chega às 3h não tem como saber que a malha
//      está parada porque alguém a segurou às 02:40;
//   3. aviso preso na fila do Teams — o PIOR cenário de plantão: webhook com
//      401, a guardiã loga e segue, e a malha falha em silêncio para todo
//      mundo menos para quem já está olhando esta tela.
//
// ── `Encerrar corrida…` (Decisão 62) ────────────────────────────────────────
// Existe em TODA corrida ABERTA, não só depois do limite vencido: os casos em
// que mais se precisa encerrar são `ABERTA · SEM_PROGRESSO` (DagRun morto) e
// `ABERTA · COM_FALHA` quando já se decidiu que a madrugada acabou. O que muda
// por estado é o TEXTO DA CONFIRMAÇÃO, nunca a presença do botão — e a
// confirmação diz a CONSEQUÊNCIA, não só a permissão.
// ─────────────────────────────────────────────────────────────────────────────

export interface NoSegurado {
  id: number
  tipo: string
  rotulo: string
  retido_em: string | null
  retido_por: string | null
}

export interface CabecalhoCorridaProps {
  /** `null` = não há ciclo nesta lente (ver `corridasNoDia` e `sem085`). */
  corrida: CorridaApi | null
  /** As frases já derivadas — a MESMA fonte do card da lista (D75/#5). */
  resumo: ResumoCorrida | null
  /** A faixa das últimas corridas + o atalho de data (Decisão 42). Chega como
   *  nó porque a navegação é da malha, não da corrida: ela continua existindo
   *  quando não há ciclo nenhum para descrever. */
  seletor: ReactNode
  /** Primeira carga do painel: a faixa reserva a altura em vez de saltar. */
  carregando: boolean
  /** Degradação por AUSÊNCIA (Decisão 41) — e ela é DITA, não só silenciosa. */
  sem085: boolean
  /** §18/12b — o operador navegou por DATA e o dia teve N corridas. O bloco
   *  `corrida` sai do payload de propósito; a tela manda escolher uma. */
  corridasNoDia?: number | null
  /** Decisão 61 — o prazo por padrão é o PRÓXIMO GATILHO da própria malha. */
  proximoGatilho?: ProximaExecucao | null
  /** F12/Decisão 56b — `≈ 38% do tempo típico`. Chega pronto do editor, que é
   *  quem tem `tipicos[]` e `execucoes[]` em mãos. `null` = sem histórico
   *  suficiente em algum membro: o número some por completo e fica o `x de y`,
   *  que nunca deixou de ser o primário. */
  percentualTempo?: string | null
  /** Instante local da última resposta (`dataUpdatedAt`) e o relógio local:
   *  o frescor é o navegador consigo mesmo, e com mais nenhum (Decisão 60). */
  respostaEm: number
  agoraLocal: number
  /** Nós com retenção posta — a fonte do banner 2 e do gesto `Soltar`. */
  nosSegurados: NoSegurado[]
  onSoltar?: (noId: number) => void
  soltando?: boolean
  /** Decisão 66/3 — `null` = nada preso (ou coluna ausente: não perguntei). */
  avisoPreso: { desde: string; quantos: number } | null
  /** Encerrar a corrida. Ausente = o operador não tem `acao_executar`: o botão
   *  aparece DESABILITADO com o motivo no `title` — esconder a saída de
   *  emergência faria o operador procurá-la onde ela não está. */
  onEncerrar?: (motivo: string) => Promise<void>
  encerrando?: boolean
  /** Abrir uma aba do painel lateral (o chip de travados leva a `Travando`). */
  onAbrirAba?: (aba: 'agora' | 'travando' | 'eventos') => void
}

export function CabecalhoCorrida({
  corrida, resumo, seletor, carregando, sem085, corridasNoDia = null,
  proximoGatilho = null, percentualTempo = null, respostaEm, agoraLocal,
  nosSegurados, onSoltar, soltando = false, avisoPreso, onEncerrar,
  encerrando = false, onAbrirAba,
}: CabecalhoCorridaProps) {
  const [confirmando, setConfirmando] = useState(false)
  const [motivo, setMotivo] = useState('')

  const f = frescor(respostaEm, agoraLocal)
  // ⚠️ `respostaEm` é o `dataUpdatedAt` do react-query, e ele vale **0**
  // enquanto NENHUMA resposta chegou — inclusive depois de um erro, quando a
  // faixa continua na tela. Carimbar esse zero daria "⚠ dado sem atualizar há
  // 466702h", que é o carimbo de frescor mentindo sobre o próprio frescor (a
  // Decisão 60 pelo avesso). Sem resposta não há o que carimbar: some.
  const carimbo = respostaEm > 0 ? (
    <span
      className={`ml-auto shrink-0 text-[10px] ${f.velho ? 'font-semibold text-amber-700 dark:text-amber-400' : 'text-dim'}`}
      title={carimboLongo(corrida?.apurado_em)
        ? `apurado em ${carimboLongo(corrida?.apurado_em)} (relógio do banco)`
        : undefined}
    >
      {/* Acima de 90 s sem refetch com sucesso o carimbo vira ALARME: o
          operador precisa saber que está olhando dado velho antes de agir. */}
      {f.velho ? '⚠ dado sem atualizar ' : '· atualizado '}{f.texto}
    </span>
  ) : null

  // ── Banner 2 (Decisão 66/2): nós segurados + o gesto de soltar ───────────
  // Ele nasce AQUI, fora dos ramos, porque é o ÚNICO dos três que não fala da
  // corrida: a condição da Decisão 66 é `retido_em` em algum nó, e nada mais.
  // Prendê-lo à existência de um ciclo apagava o banner exatamente no caso que
  // ele existe para cobrir — **Início segurado**, que impede a corrida de
  // abrir: sem ciclo, sem banner, e a malha parada sem ninguém saber por quê.
  // É também o que mantém a Decisão 66/2 testável com o interruptor
  // `malha_corrida_ativa` em `0`, onde não há corrida nenhuma no banco.
  const maisAntigo = nosSegurados[0] ?? null
  const bannerHold = maisAntigo ? (
    <Banner
      tom="alerta"
      icone={<PauseCircle size={14} className="mt-0.5 shrink-0" />}
      acao={onSoltar ? (
        <button
          type="button"
          disabled={soltando}
          onClick={() => onSoltar(maisAntigo.id)}
          title={`Soltar ${maisAntigo.rotulo} — os pipelines depois dele voltam a ser avaliados no próximo ciclo; o tempo em que a malha ficou segurada é devolvido ao limite de segurança`}
          className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 transition-colors hover:bg-amber-200 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-200 dark:hover:bg-amber-900/60"
        >
          <Unlock size={11} aria-hidden="true" />
          {soltando ? 'soltando…' : `Soltar ${maisAntigo.rotulo}`}
        </button>
      ) : undefined}
    >
      <strong>
        {nosSegurados.length === 1
          ? '1 nó segurado'
          : `${nosSegurados.length} nós segurados`}
        {maisAntigo.retido_em ? ` desde ${horaCurta(maisAntigo.retido_em)}` : ''}
        {maisAntigo.retido_por ? ` (por ${maisAntigo.retido_por})` : ''}
      </strong>
      {' — '}
      {corrida
        ? 'o ciclo não avança e os relógios estão parados.'
        : 'enquanto a trava estiver posta, a malha não parte no horário agendado.'}
      {/* Um botão que solta N nós de uma vez pode falhar no meio e deixar
          a malha meio presa sem ninguém saber qual metade. O gesto é
          nominal: solta o mais antigo, e o banner volta com o próximo. */}
      {nosSegurados.length > 1 && ' Soltar libera um por vez, do mais antigo.'}
    </Banner>
  ) : null

  // ── Carregando: altura reservada ─────────────────────────────────────────
  // A faixa não pode saltar. Um cabeçalho que aparece 400 ms depois empurra o
  // canvas para baixo e o clique do operador cai noutro lugar.
  if (carregando && !resumo) {
    return (
      <div className="flex flex-col gap-1 border-b border-edge bg-panel px-3 py-2">
        <div className="flex items-center gap-2">{seletor}</div>
        <Skeleton className="h-4 w-72" />
        <Skeleton className="h-3 w-48" />
      </div>
    )
  }

  // ── Sem ciclo nesta lente ────────────────────────────────────────────────
  if (!corrida || !resumo) {
    return (
      <>
        {sem085 && (
          <Banner
            tom="alerta"
            icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}
          >
            <span title="A migration 085 (o registro do ciclo da malha) ainda não foi aplicada neste banco. O que a tela mostra continua verdadeiro; o que falta é o ciclo.">
              sem dados de ciclo — sistema em atualização
            </span>
          </Banner>
        )}
        {bannerHold}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-edge bg-panel px-3 py-2 text-[12px] text-dim">
          {seletor}
          {/* §18/12b — a tela deixa de ser MUDA. Sem esta frase o operador vê o
              canvas do dia sem faixa e não tem como saber que está olhando
              DUAS madrugadas empilhadas no mesmo desenho. */}
          {corridasNoDia && corridasNoDia > 1 ? (
            <span className="font-medium text-amber-700 dark:text-amber-400">
              este dia teve {corridasNoDia} corridas — escolha uma na faixa de
              corridas para ver o ciclo separado (o desenho abaixo mistura
              {corridasNoDia === 2 ? ' as duas' : ` as ${corridasNoDia}`})
            </span>
          ) : (
            !sem085 && <span>nenhum ciclo registrado nesta lente</span>
          )}
          {carimbo}
        </div>
      </>
    )
  }

  const congelado = CORRIDA_INTERROMPIDA.has(corrida.status)
  const aberta = corrida.status === 'ABERTA'

  return (
    <>
      {/* ── Banner 1 (Decisão 66): data de referência divergente ───────────
          O incidente que ORIGINOU esta spec. Nominal: o operador precisa dos
          NOMES para saber quais pipelines recarimbar. */}
      {resumo.foraDoOdate && (
        <Banner
          tom="alerta"
          icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}
        >
          <strong>{resumo.foraDoOdate}</strong> — eles rodaram neste ciclo
          carimbando outro dia, então a contagem da barra está certa e o DIA
          deles está errado.
        </Banner>
      )}

      {/* ── Banner 2 (Decisão 66): nós segurados + o gesto de soltar ─────────
          Montado lá em cima, fora dos ramos: ele é o único dos três que vale
          COM e SEM ciclo (a condição é `retido_em`, e nada mais). */}
      {bannerHold}

      {/* ── Banner 3 (Decisão 66): o aviso que ninguém recebeu ─────────────── */}
      {avisoPreso && (
        <Banner
          tom="erro"
          icone={<BellOff size={14} className="mt-0.5 shrink-0" />}
        >
          <strong>
            {avisoPreso.quantos === 1
              ? 'aviso ao Teams na fila'
              : `${avisoPreso.quantos} avisos ao Teams na fila`}
            {` desde ${horaCurta(avisoPreso.desde)}`}
          </strong>
          {' — '}ninguém foi avisado ainda. Quem está de plantão não sabe desta
          malha; confira o webhook do Teams antes de contar com o alerta.
        </Banner>
      )}

      {/* ── A faixa ────────────────────────────────────────────────────────── */}
      <div className={`flex flex-col gap-1 border-b px-3 py-2 text-[12px] ${resumo.faixa}`}>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {seletor}
          {carimbo}
        </div>

        <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
          {/* Zona 1 — identidade e estado. */}
          <div className="flex min-w-[13rem] flex-col gap-0.5">
            <span className="flex flex-wrap items-center gap-1.5">
              <span
                className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold ${resumo.estilo.chip}`}
                title={resumo.titulo}
              >
                {resumo.estilo.animado && (
                  <span className={`h-1.5 w-1.5 shrink-0 animate-pulse rounded-full ${resumo.estilo.dot}`} />
                )}
                <resumo.estilo.Icone size={12} className="shrink-0" aria-hidden="true" />
                {resumo.estilo.rotulo}
              </span>
              <span className="font-medium">{resumo.identidade}</span>
            </span>
            {/* Decisão 43 — quem abriu, se foi reaberta e como esta malha
                fecha: as três primeiras perguntas de plantão, todas
                respondíveis pelo banco e nenhuma pela tela até esta fase. */}
            {resumo.diagnostico && (
              <span className="text-[11px] opacity-75">{resumo.diagnostico}</span>
            )}
            {/* Auditoria (Decisão 67): quem encerrou, quando e por quê. */}
            {resumo.encerramento && (
              <span className="text-[11px]">{resumo.encerramento}</span>
            )}
            {/* O motivo é texto LIVRE do operador (até 300 chars no endpoint,
                e a coluna acumula até 500). Sem o clamp, uma frase longa
                empilha ~15 linhas numa coluna de 13rem e a faixa — que a
                Decisão 71 manda ter altura estável, a ponto de o estado
                "carregando" ser um skeleton de altura fixa — cresce para
                empurrar a barra e o botão de encerrar para fora da primeira
                tela. Duas linhas na faixa, o resto no `title`, igual ao card. */}
            {resumo.motivo && (
              <span className="line-clamp-2 text-[11px] italic"
                    title={resumo.motivo}>{resumo.motivo}</span>
            )}
            {/* Decisão 68 — o `SEM_TRABALHO` que merece atenção. A cor já subiu
                para âmbar em `resumo.faixa`; esta é a palavra que a acompanha,
                porque cor nunca é canal único. */}
            {resumo.diaAtipico && (
              <span className="text-[11px] font-medium">
                ⚠ {resumo.diaAtipico}
              </span>
            )}
            {/* Decisão 68 — o FATO de ontem, que é a resposta mais direta a
                "está pior que ontem?". Exige `n = 1`, não `n ≥ 5`: isto é
                registro, não mediana. */}
            {resumo.anterior && (
              <span className="text-[11px] opacity-75">{resumo.anterior}</span>
            )}
          </div>

          {/* Zona 2 — progresso. O chip de travados é CLICÁVEL e leva à aba
              `Travando`: um clique até o problema (Decisão 62). */}
          <div className="min-w-[16rem] flex-1">
            <CorridaProgresso
              resumo={resumo}
              variante="painel"
              congelado={congelado}
              onTravados={onAbrirAba ? () => onAbrirAba('travando') : undefined}
              /* Decisão 56b — o percentual de TEMPO, sempre o SEGUNDO número.
                 Só a faixa o recebe: no card cabe um número só, e o que fica é
                 o `x de y`. */
              percentualTempo={percentualTempo}
            />
            {resumo.culpado && (
              <span className="mt-0.5 block text-[11px] font-medium">
                ↳ {resumo.culpado}
              </span>
            )}
            {resumo.vivos && onAbrirAba && (
              <button
                type="button"
                onClick={() => onAbrirAba('agora')}
                title="Ver quem está rodando agora"
                className="mt-0.5 text-[11px] underline decoration-dotted underline-offset-2 hover:opacity-80"
              >
                {resumo.vivos}
              </button>
            )}
          </div>

          {/* Zona 3 — relógios e prazo. */}
          <div className="min-w-[15rem]">
            <RelogioCorrida
              corrida={corrida}
              resumo={resumo}
              proximoGatilho={proximoGatilho}
              agoraLocal={agoraLocal}
            />
          </div>

          {/* Zona 4 — a porta de saída (Decisão 62/§6.8). */}
          {aberta && (
            <div className="ml-auto shrink-0">
              <Button
                size="sm"
                variant="secondary"
                disabled={!onEncerrar}
                onClick={() => { setMotivo(''); setConfirmando(true) }}
                title={onEncerrar
                  ? 'Encerrar o ciclo desta madrugada e liberar o disparo do próximo ciclo'
                  : 'Encerrar o ciclo exige a permissão de execução'}
              >
                Encerrar ciclo…
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* ── A confirmação, com a CONSEQUÊNCIA escrita ─────────────────────── */}
      <Modal
        open={confirmando}
        onClose={() => setConfirmando(false)}
        title="Encerrar o ciclo"
        size="lg"
      >
        <div className="flex flex-col gap-3 text-sm text-ink">
          <p>
            Isto fecha o ciclo da <strong>{resumo.identidade}</strong>
            {resumo.tempo ? <> (<span>{resumo.tempo}</span>)</> : null} e{' '}
            <strong>libera o disparo do próximo ciclo desta malha</strong>.
          </p>
          {/* A dúvida que faz o operador NÃO apertar o botão, respondida antes
              do clique: encerrar não é matar. */}
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            <strong>Nenhum pipeline é interrompido.</strong>{' '}
            {corrida.membros_vivos
              ? `Os ${corrida.membros_vivos} pipelines em execução CONTINUAM rodando`
              : 'O que estiver rodando CONTINUA rodando'}
            {' '}— encerrar fecha o REGISTRO do ciclo, não os processos. Para
            parar um pipeline, use a tela de Execuções.
          </div>
          {/* Decisão 74: o nome que o motor dá a esta classe de execução, e o
              nome que o Airflow dá ao processo morto, NÃO chegam à tela — os
              dois são vocabulário de máquina, e este texto é lido às 3h por
              quem opera. O FATO ("terminou sem registrar o fim") diz a mesma
              coisa, é a tradução que a §9.11 fixa, e ainda aponta a ação. */}
          {corrida.saude === 'SEM_PROGRESSO' && (
            <p className="text-[13px] text-dim">
              Este ciclo está sem sinal
              {corrida.sem_sinal_min ? ` há ${corrida.sem_sinal_min} min` : ''}:
              é o sintoma de um pipeline que terminou sem registrar o fim.
              Encerrar aqui não conserta essa execução — ela continua aberta na
              Finalização Manual.
            </p>
          )}
          {corrida.saude === 'COM_FALHA' && (
            <p className="text-[13px] text-dim">
              Este ciclo já tem falha detectada. Encerrar registra que a
              madrugada acabou assim; o reprocesso continua possível depois.
            </p>
          )}
          <label className="flex flex-col gap-1 text-[13px]">
            <span className="font-medium">
              Motivo (obrigatório — fica no histórico da corrida)
            </span>
            <textarea
              value={motivo}
              onChange={e => setMotivo(e.target.value)}
              rows={2}
              maxLength={300}
              placeholder="ex.: carga do dia 03 remarcada para a tarde"
              className="rounded-md border border-edge bg-canvas px-2 py-1.5 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40"
            />
            <span className="text-[11px] text-dim">
              No fechamento do mês, uma corrida cancelada sem razão registrada é
              um buraco no histórico justamente no dia em que algo deu errado.
            </span>
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirmando(false)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={encerrando}
              disabled={!motivo.trim() || !onEncerrar}
              onClick={async () => {
                if (!onEncerrar) return
                await onEncerrar(motivo.trim())
                setConfirmando(false)
              }}
            >
              Encerrar ciclo
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
