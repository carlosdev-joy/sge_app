// Modal da ETAPA EM ESPERA — pausar, liberar e cancelar a execução
// (F5 da spec docs/spec-operacao-nivel-etapa.md, §5 Bloco C; decisão 3 do §7:
// pausa em RUNTIME, na etapa que ainda não começou).
//
// ═══════════════════════════════════════════════════════════════════════════
// AS REGRAS DA CASA QUE ESTE MODAL CARREGA
// ═══════════════════════════════════════════════════════════════════════════
//
// 1. **O limite honesto aparece na TELA, não só na doc.** O §5 é explícito:
//    "só dá para pausar etapa que ainda não iniciou. Se ela já está rodando, a
//    pausa vale para as seguintes." Isso está dito aqui em português, no ponto
//    onde o operador decide — e o servidor recusa de qualquer forma (409), que
//    é o que impede a tela de prometer o que não acontece.
//
// 2. **Liberar e cancelar não são o mesmo gesto, nem parecem.** Liberar deixa
//    seguir; cancelar FALHA a corrida no Airflow. O segundo é destrutivo e usa
//    o vermelho da casa, com a consequência escrita antes do clique.
//
// 3. **Nunca "sucesso" mudo.** Todo retorno vira toast, os avisos do servidor
//    (ex.: SLA menor que o teto) saem em `toast.info` e as queries do modo
//    Execução são invalidadas — o mesmo fecho do ModalRerunEtapa.
import { useState } from 'react'
import {
  AlertTriangle, Ban, Clock, Info, Loader2, PauseCircle, PlayCircle,
} from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal } from '../ui/Modal'
import { apiFetch } from '../../lib/api'
import { toast } from '../ui/Toast'
import { horaLonga, type PausaApi } from './execucaoEtapas'

interface RespostaPausa {
  ok: boolean
  pausa_id: number
  ja_existia?: boolean
  estado?: string
  avisos?: string[]
}

interface Props {
  open: boolean
  onClose: () => void
  pipeline: string
  /** etapa alvo (id do nó = job_name = task_id no Airflow) */
  jobName: string
  /** ODATE em exibição */
  dataReferencia: string | null
  /** corrida escolhida à mão na ambiguidade (F3) */
  runId: string | null
  /** status CRU da etapa nesta corrida (null = ainda não rodou) */
  status: string | null
  /** a pausa PENDENTE desta etapa, quando já existe */
  pausa: PausaApi | null
  /** histórico de pausas desta etapa nesta corrida (todas, inclusive resolvidas) */
  historico: PausaApi[]
  /** etapas que AINDA dá para pausar nesta corrida — a resposta à pergunta que
   *  o operador faz logo depois de "aqui não dá": então onde dá? */
  etapasPausaveis: string[]
  /** (F5) estado do PORTÃO na DAG publicada: 'ok' | 'dag_sem_portao' |
   *  'portao_desconhecido' (ausente = API anterior, que não sabia responder).
   *  Ver o bloco de aviso abaixo — é a segunda metade do deploy da F5. */
  portao?: string | null
}

export function ModalPausaEtapa({
  open, onClose, pipeline, jobName, dataReferencia, runId, status, pausa,
  historico, etapasPausaveis, portao,
}: Props) {
  const qc = useQueryClient()
  const [motivo, setMotivo] = useState('')
  const [observacao, setObservacao] = useState('')
  const [confirmaCancelar, setConfirmaCancelar] = useState(false)

  // A etapa já rodou nesta corrida? É o limite do §5, e ele é derivado do
  // MESMO dado que o servidor usa (existir linha de execução), não de uma
  // regra paralela do front.
  const jaIniciou = !!(status ?? '').trim()
  const aguardando = !!pausa?.aguardando_desde

  // ── (F5) A DAG PUBLICADA obedece a pausa? ──────────────────────────────────
  // O banco ter a migration 079 NÃO basta: o portão que segura a etapa é uma
  // linha emitida DENTRO do fonte gerado da DAG, e só existe depois de o
  // pipeline ser republicado (`force_all` do deploy). Sem portão, "Pausar
  // aqui" respondia 200, a tela pintava "pausa marcada" e o pipeline passava
  // direto — a regra da casa é nunca mostrar como garantido o que não está.
  // Por isso o botão fica DESLIGADO aqui, e não só o POST recusa.
  const semPortao = portao === 'dag_sem_portao'
  const portaoIncerto = portao === 'portao_desconhecido'

  const invalida = () => {
    qc.invalidateQueries({ queryKey: ['pipeline-execucao'] })
    qc.invalidateQueries({ queryKey: ['execucoes'] })
    qc.invalidateQueries({ queryKey: ['malha-execucao'] })
  }

  const feito = (msg: string) => (r: RespostaPausa) => {
    toast.success(msg)
    for (const a of r.avisos ?? []) toast.info(`Atenção: ${a}`)
    invalida()
    onClose()
  }

  const pedir = useMutation<RespostaPausa>({
    mutationFn: () => apiFetch('/execucoes/pausas', {
      method: 'POST',
      body: JSON.stringify({
        pipeline_name: pipeline,
        job_name: jobName,
        motivo: motivo.trim() || undefined,
        ...(runId ? { dag_run_id: runId } : {}),
        ...(dataReferencia ? { data_referencia: dataReferencia } : {}),
      }),
    }),
    onSuccess: (r) => {
      // `ja_existia` não é erro nem sucesso novo: alguém (ou outra aba) já
      // tinha pausado esta etapa. Dizer isso é diferente de fingir que o
      // clique criou algo.
      if (r.ja_existia) toast.info(`A etapa "${jobName}" já estava marcada para pausa.`)
      else toast.success(`Etapa "${jobName}" marcada para pausa.`)
      for (const a of r.avisos ?? []) toast.info(`Atenção: ${a}`)
      invalida()
      onClose()
    },
    onError: (e: unknown) => toast.error(mensagemErro(e)),
  })

  const liberar = useMutation<RespostaPausa>({
    mutationFn: () => apiFetch(`/execucoes/pausas/${pausa?.id}/liberar`, {
      method: 'POST',
      body: JSON.stringify({ observacao: observacao.trim() || undefined }),
    }),
    onSuccess: feito(`Etapa "${jobName}" liberada — a execução segue daqui.`),
    onError: (e: unknown) => toast.error(mensagemErro(e)),
  })

  const cancelar = useMutation<RespostaPausa>({
    mutationFn: () => apiFetch(`/execucoes/pausas/${pausa?.id}/cancelar`, {
      method: 'POST',
      body: JSON.stringify({ observacao: observacao.trim() || undefined }),
    }),
    onSuccess: feito('Execução cancelada — o ciclo foi marcada como falha.'),
    onError: (e: unknown) => toast.error(mensagemErro(e)),
  })

  const ocupado = pedir.isPending || liberar.isPending || cancelar.isPending
  const titulo = pausa
    ? (aguardando ? `Etapa "${jobName}" em espera` : `Pausa marcada em "${jobName}"`)
    : `Pausar antes de "${jobName}"`

  return (
    <Modal open={open} onClose={onClose} size="lg" title={titulo}>
      <div className="flex flex-col gap-4 text-sm">

        {/* ── Contexto ───────────────────────────────────────────────────── */}
        <div className="rounded-lg border border-edge bg-canvas px-3 py-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
            <span className="font-mono text-ink">{pipeline}</span>
            <span className="text-dim">·</span>
            <span className="text-dim">data de referência</span>
            <span className="font-mono text-ink">{dataReferencia ?? '—'}</span>
            <span className="text-dim">·</span>
            <span className="text-dim">
              etapa {status ? `em ${status}` : 'ainda não iniciada'}
            </span>
          </div>
        </div>

        {/* ── A segunda metade do deploy: a DAG publicada tem portão? ─────── */}
        {!pausa && (semPortao || portaoIncerto) && (
          <Aviso tom={semPortao ? 'erro' : 'alerta'}
                 icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
            {semPortao ? (
              <>
                Este pipeline foi <strong>publicado antes da etapa em
                espera</strong>: a DAG que está no Airflow não tem o portão que
                obedece a pausa. Marcar uma pausa aqui{' '}
                <strong>não seguraria nada</strong> — a execução passaria
                direto. Gere a DAG novamente (publicar o pipeline) e a pausa
                volta a valer.
              </>
            ) : (
              <>
                Não foi possível confirmar se a DAG publicada deste pipeline tem
                o portão de espera. Se ela tiver sido publicada antes desta
                funcionalidade, a pausa <strong>não vai segurar</strong> a
                execução — republique o pipeline para ter certeza.
              </>
            )}
          </Aviso>
        )}

        {/* ── O limite honesto do §5, dito onde se decide ─────────────────── */}
        {!pausa && (
          <Aviso tom={jaIniciou ? 'erro' : 'info'}
                 icone={jaIniciou
                   ? <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                   : <Info size={14} className="mt-0.5 shrink-0" />}>
            {jaIniciou ? (
              <>
                Esta etapa <strong>já iniciou</strong> nesta execução — o portão
                dela ficou para trás e a pausa não teria efeito. Só dá para
                pausar etapa que ainda não começou.
                {etapasPausaveis.length > 0 ? (
                  <>
                    {' '}Nesta corrida ainda dá para pausar:
                    <span className="mt-1 flex flex-wrap gap-1">
                      {etapasPausaveis.map(e => (
                        <span key={e}
                          className="rounded border border-red-300 bg-white/60 px-1.5 py-0.5 font-mono text-[10px] dark:border-red-800 dark:bg-black/20">
                          {e}
                        </span>
                      ))}
                    </span>
                  </>
                ) : (
                  <> Nesta corrida <strong>nenhuma etapa</strong> está mais
                    disponível para pausa — todas já começaram. Para refazer a
                    partir daqui, use “Reexecutar daqui”.</>
                )}
              </>
            ) : (
              <>
                A pausa segura a etapa <strong>antes</strong> de ela começar. Se
                ela já estivesse rodando, a pausa valeria só para as seguintes —
                por isso o gesto só existe em etapa que ainda não iniciou.
                Nenhuma DAG é republicada: a pausa é estado em tabela.
              </>
            )}
          </Aviso>
        )}

        {/* ── Estado da pausa existente ───────────────────────────────────── */}
        {pausa && (
          <div className="rounded-lg border border-fuchsia-300 bg-fuchsia-50 px-3 py-2 dark:border-fuchsia-800 dark:bg-fuchsia-900/20">
            <p className="flex items-center gap-1.5 text-[12px] font-semibold text-fuchsia-800 dark:text-fuchsia-300">
              <PauseCircle size={13} />
              {aguardando
                ? (pausa.parado_min != null
                    ? `Parada há ${pausa.parado_min} min, aguardando liberação`
                    : 'Parada, aguardando liberação')
                : 'Marcada para pausa — a etapa ainda não chegou aqui'}
            </p>
            <ul className="mt-1 flex flex-col gap-0.5 text-[11px] text-dim">
              {/* "registro" e não "às": este carimbo é o relógio do BANCO, que
                  não é o mesmo dos horários das etapas (ver execucaoEtapas.ts).
                  Mesma palavra que `rotuloCorrida` usa, pelo mesmo motivo. */}
              <li>pedida por <strong className="text-ink">{pausa.solicitado_por ?? '?'}</strong>
                {pausa.solicitado_em ? ` (registro ${horaLonga(pausa.solicitado_em)})` : ''}</li>
              {aguardando && pausa.aguardando_desde && (
                <li>parou no portão em {horaLonga(pausa.aguardando_desde)} (registro)</li>
              )}
              {pausa.motivo && <li>motivo: {pausa.motivo}</li>}
              <li className="flex items-center gap-1">
                <Clock size={11} />
                teto de espera: {pausa.teto_minutos ?? '—'} min
                {aguardando && (
                  <span className="text-dim/80">
                    · o portão verifica de tempos em tempos; passar do teto
                    interrompe a execução com alerta
                  </span>
                )}
              </li>
            </ul>
          </div>
        )}

        {/* ── Campo de texto do gesto ─────────────────────────────────────── */}
        {!pausa && !jaIniciou && !semPortao && (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-dim">
              Motivo da pausa <span className="font-normal">(fica na auditoria)</span>
            </span>
            <input
              value={motivo}
              onChange={e => setMotivo(e.target.value)}
              maxLength={200}
              placeholder="ex.: conferir o total da carga antes de publicar"
              className="rounded-md border border-edge bg-canvas px-2 py-1.5 text-[12px] text-ink placeholder:text-dim/60 focus:border-[#1A5FA8] focus:outline-none"
            />
          </label>
        )}

        {pausa && (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-dim">
              Observação <span className="font-normal">(quem liberou/cancelou e por quê)</span>
            </span>
            <input
              value={observacao}
              onChange={e => setObservacao(e.target.value)}
              maxLength={200}
              placeholder="ex.: número conferido, pode seguir"
              className="rounded-md border border-edge bg-canvas px-2 py-1.5 text-[12px] text-ink placeholder:text-dim/60 focus:border-[#1A5FA8] focus:outline-none"
            />
          </label>
        )}

        {/* ── Cancelar a execução: consequência ANTES do clique ───────────── */}
        {pausa && (
          <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-900/20">
            <input
              type="checkbox"
              checked={confirmaCancelar}
              onChange={e => setConfirmaCancelar(e.target.checked)}
              className="mt-0.5 shrink-0 accent-red-600"
            />
            <span className="text-[11px] leading-snug text-red-700 dark:text-red-300">
              Quero <strong>cancelar a execução</strong> em vez de liberar. A
              corrida é marcada como <strong>falha</strong> no Airflow (nunca
              como sucesso pela metade) e as etapas seguintes não rodam. Para
              retomar depois, use “Reexecutar daqui”.
            </span>
          </label>
        )}

        {/* ── Histórico: a auditoria visível ──────────────────────────────── */}
        {historico.filter(h => h.estado !== 'PENDENTE').length > 0 && (
          <section>
            <h3 className="mb-1 text-[12px] font-semibold text-ink">
              Pausas anteriores nesta execução
            </h3>
            <ul className="flex flex-col gap-0.5">
              {historico.filter(h => h.estado !== 'PENDENTE').map(h => (
                <li key={h.id} className="flex flex-wrap items-center gap-1.5 text-[11px] text-dim">
                  <span className={`h-1 w-1 shrink-0 rounded-full ${
                    h.estado === 'LIBERADA' ? 'bg-green-500'
                      : h.estado === 'EXPIRADA' ? 'bg-red-500' : 'bg-slate-400'}`} />
                  <span className="font-semibold text-ink">{h.estado.toLowerCase()}</span>
                  {h.resolvido_por && <span>por {h.resolvido_por}</span>}
                  {h.resolvido_em && <span>· {horaLonga(h.resolvido_em)}</span>}
                  {h.observacao && <span className="truncate">· {h.observacao}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* ── Ações ──────────────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-edge pt-3">
          <button
            onClick={onClose}
            className="rounded-md border border-edge px-3 py-1.5 text-[12px] text-dim hover:bg-edge/40 hover:text-ink"
          >
            Fechar
          </button>

          {pausa && (
            <button
              onClick={() => cancelar.mutate()}
              disabled={!confirmaCancelar || ocupado}
              className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-red-700 disabled:opacity-40 disabled:pointer-events-none"
            >
              {cancelar.isPending
                ? <Loader2 size={13} className="animate-spin" />
                : <Ban size={13} />}
              Cancelar a execução
            </button>
          )}

          {pausa && (
            <button
              onClick={() => liberar.mutate()}
              disabled={ocupado}
              className="inline-flex items-center gap-1.5 rounded-md bg-[#1A5FA8] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[#164e8b] disabled:opacity-40 disabled:pointer-events-none"
            >
              {liberar.isPending
                ? <Loader2 size={13} className="animate-spin" />
                : <PlayCircle size={13} />}
              Liberar e seguir
            </button>
          )}

          {!pausa && (
            <button
              onClick={() => pedir.mutate()}
              disabled={jaIniciou || semPortao || ocupado}
              title={jaIniciou
                ? 'A etapa já iniciou nesta execução — a pausa não teria efeito'
                : semPortao
                  ? 'A DAG publicada não tem o portão de espera — publique o pipeline novamente'
                  : 'Marca a etapa para parar e aguardar liberação'}
              className="inline-flex items-center gap-1.5 rounded-md bg-[#1A5FA8] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[#164e8b] disabled:opacity-40 disabled:pointer-events-none"
            >
              {pedir.isPending
                ? <Loader2 size={13} className="animate-spin" />
                : <PauseCircle size={13} />}
              Pausar nesta etapa
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}

// ─────────────────────────────── auxiliares ─────────────────────────────────

function Aviso({ tom, icone, children }: {
  tom: 'info' | 'alerta' | 'erro'
  icone: React.ReactNode
  children: React.ReactNode
}) {
  const cls = tom === 'erro'
    ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
    : tom === 'alerta'
      ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
      : 'border-[#1A5FA8]/30 bg-[#1A5FA8]/5 text-ink dark:border-blue-800 dark:bg-blue-900/20'
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[11px] leading-snug ${cls}`}>
      {icone}
      <span>{children}</span>
    </div>
  )
}

/** Mesma leitura de erro do ModalRerunEtapa: o 409 desta fase chega com
 *  `detail` OBJETO (etapa_ja_iniciou, pausa_ja_resolvida, migration_079…), e
 *  `apiFetch` só usa `detail` como mensagem quando ele é STRING. Sem isto a
 *  recusa mais importante — "a etapa já iniciou" — apareceria como "409
 *  Conflict". O detalhe cru fica em `err.detail` (ver lib/api.ts). */
function mensagemErro(e: unknown): string {
  const det = (e as { detail?: unknown })?.detail
  if (det && typeof det === 'object' && 'mensagem' in (det as object)) {
    return String((det as { mensagem: unknown }).mensagem)
  }
  if (typeof det === 'string' && det) return det
  return (e as { message?: string })?.message || 'Erro desconhecido'
}
