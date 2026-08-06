// Modal de confirmação do rerun a partir de uma etapa
// (F4 da spec docs/spec-operacao-nivel-etapa.md — §4 Bloco B, decisão 1 do §7).
//
// ⚠️ A DECISÃO 1 EM FORMA DE TELA. O texto da decisão, tomada pelo usuário:
//
//   "Cascata no rerun: SEMPRE PERGUNTAR. O modal oferece as duas opções — só
//    este pipeline ou este e os dependentes (cascata) — mostrando quais
//    pipelines seriam afetados em cada caso. Nunca decidir em silêncio, nos
//    dois sentidos: nem reprocessar cadeia inteira sem aviso, nem deixar
//    dependentes com dado velho achando que o rerun resolveu."
//
// Daí três regras que este componente respeita à risca:
//
//  1. **Nenhuma opção vem pré-selecionada como "certa".** As duas são
//     apresentadas com o mesmo peso visual e com a CONSEQUÊNCIA de cada uma
//     escrita por extenso. "Só este" começa marcada por ser a de menor
//     alcance — mas o que ela deixa para trás está dito na própria opção, que
//     é o segundo sentido do "nunca em silêncio".
//  2. **A lista de afetados é do servidor, não do palpite do front.** As
//     etapas vêm do `dry_run: true` do próprio `clearTaskInstances` e os
//     pipelines do fecho a jusante calculado no banco. O front não deduz nada.
//  3. **Enquanto a prévia não chega (ou falha), não dá para confirmar.**
//     Confirmar um gesto destrutivo sem saber o alcance é exatamente o que a
//     decisão proíbe.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, ArrowRight, CheckCircle2, GitBranch, Info, Layers,
  Loader2, RefreshCw,
} from 'lucide-react'
import { Modal } from '../ui/Modal'
import { apiFetch } from '../../lib/api'
import { toast } from '../ui/Toast'

// ─────────────────────────── contrato do servidor ───────────────────────────

interface CorridaAfetada {
  run_id: string | null
  status: string | null
  inicio: string | null
  fim: string | null
  disparado_por: string | null
  substituida_em: string | null
}

interface CascataPrevia {
  disponivel: boolean
  razao: string | null
  /** fecho a jusante inteiro, em ordem BFS (filhos, depois netos) */
  dependentes: string[]
  /** rodaram no ODATE → serão reabertos e rodam de novo */
  com_corrida: string[]
  /** não rodaram no ODATE → não há corrida a reabrir */
  sem_corrida: string[]
  corridas: Record<string, CorridaAfetada[]>
  truncado: boolean
  /** F8 — o CICLO da malha em que esta reexecução cai (§6.9/#3, Decisão 65).
   *  `null`/ausente = pipeline fora de malha, banco a meio deploy ou leitura
   *  indisponível: sem certeza, sem frase. */
  corrida?: CorridaDoCiclo | null
}

interface CorridaDoCiclo {
  malha: string
  data_referencia: string
  status: string
  /** 'em_andamento' | 'reabre' | 'fora_do_ciclo' */
  efeito: string
  mensagem: string
}

interface PreviaRerun {
  pipeline_name: string
  task_id: string
  data_referencia: string | null
  dag_run_id: string | null
  airflow_indisponivel: boolean
  /** true = DAG pausada no Airflow (o gesto recusa com 409); null = não deu
   *  para perguntar — e não saber não bloqueia nada. */
  dag_pausada: boolean | null
  /** etapas DESTE pipeline que o clear vai reexecutar (do dry_run real) */
  etapas: string[]
  /** log_start/log_end/publish_dataset/cards — não somem do relato */
  tasks_de_apoio: number
  total_tasks: number
  cascata: CascataPrevia
}

interface RespostaRerun {
  ok: boolean
  tasks_cleared: number
  cascata: boolean
  dependentes_reabertos: string[]
  corridas_substituidas: number
  /** outras corridas DESTE pipeline no mesmo ODATE, aposentadas junto */
  corridas_irmas_aposentadas: number
  auditado: boolean
  avisos: string[]
  /** F8 — ciclos que voltaram a ABERTA por causa deste gesto */
  corridas_reabertas?: { malha: string; data_referencia: string; tentativas: number }[]
  /** F8 — ciclos que NÃO reabriram e ficaram com o registro do reprocesso */
  corridas_com_reprocesso?: { malha: string; data_referencia: string; status: string }[]
}

interface Props {
  open: boolean
  onClose: () => void
  pipeline: string
  /** a etapa de onde retomar (task_id no Airflow) */
  taskId: string
  jobName: string
  /** ODATE em exibição no canvas */
  dataReferencia: string | null
  /** corrida escolhida à mão no aviso de ambiguidade da F3 (run_id) */
  runId: string | null
  /** status da etapa — só para o texto; o gesto NÃO exige FALHA (§4) */
  status: string | null
}

const RAZOES: Record<string, string> = {
  migration_067_pendente:
    'a migration 067 não está aplicada neste ambiente — sem ela não há registro '
    + 'de corrida por pipeline, e a cascata não tem como funcionar.',
  migration_078_pendente:
    'a migration 078 não está aplicada neste ambiente — sem a marca de corrida '
    + 'substituída, o claim continua barrando o segundo disparo do dependente.',
  // As duas metades do deploy têm conserto diferente: uma é rodar migration,
  // a outra é deployar dags/. Dizer sempre "migration 078" era o que fazia a
  // tela mandar o operador conferir o que já estava certo.
  dags_desatualizado:
    'o motor de dependências publicado (pasta dags/) ainda não entende corrida '
    + 'reaberta — as migrations foram aplicadas, o deploy de dags/ não. '
    + 'Reabrir agora aposentaria as corridas sem nada rodar de novo.',
  capacidade_dags_desconhecida:
    'não foi possível conferir se o motor publicado (pasta dags/) entende '
    + 'corrida reaberta. Enquanto isso a cascata fica indisponível — melhor do '
    + 'que prometer um reprocesso que pode não acontecer.',
  sem_data_referencia:
    'a data de referência desta execução não pôde ser determinada.',
  erro_na_consulta:
    'não foi possível consultar as dependências agora.',
}

export function ModalRerunEtapa({
  open, onClose, pipeline, taskId, jobName, dataReferencia, runId, status,
}: Props) {
  const qc = useQueryClient()
  const [cascata, setCascata] = useState(false)

  const previa = useQuery<PreviaRerun>({
    queryKey: ['rerun-previa', pipeline, taskId, dataReferencia, runId],
    queryFn: () => {
      const q = new URLSearchParams({ task_id: taskId })
      // `run_id` tem precedência: se o operador escolheu uma corrida no aviso
      // de ambiguidade da F3, é DELA que estamos falando. Mandar a data junto
      // seria pedir ao servidor que escolhesse de novo — e ele recusaria.
      if (runId) q.set('run_id', runId)
      else if (dataReferencia) q.set('data_referencia', dataReferencia)
      return apiFetch(
        `/pipelines/${encodeURIComponent(pipeline)}/rerun/previa?${q.toString()}`)
    },
    enabled: open && !!taskId,
    // Prévia de gesto destrutivo não se serve de cache velho.
    staleTime: 0,
    gcTime: 0,
    retry: false,
  })

  const p = previa.data
  const deps = p?.cascata
  const podeCascata = !!deps?.disponivel && (deps?.com_corrida.length ?? 0) > 0
  // A opção marcada só vale se a prévia disser que ela é possível. Sem esta
  // trava, uma prévia que voltou "cascata indisponível" DEPOIS de o operador
  // ter marcado a opção mandaria `cascata: true` e o botão prometeria um
  // alcance que o servidor não entrega — a mentira que a decisão 1 proíbe.
  const cascataEfetiva = cascata && podeCascata

  const executar = useMutation<RespostaRerun>({
    mutationFn: () => apiFetch('/execucoes/rerun', {
      method: 'POST',
      body: JSON.stringify({
        pipeline_name: pipeline,
        task_id: taskId,
        cascata: cascataEfetiva,
        ...(runId ? { dag_run_id: runId } : {}),
        ...(dataReferencia ? { data_referencia: dataReferencia } : {}),
      }),
    }),
    onSuccess: (r) => {
      const extra = r.cascata && r.dependentes_reabertos.length
        ? ` · ${r.dependentes_reabertos.length} dependente(s) reaberto(s)`
        : ''
      toast.success(`Reexecução disparada — ${r.tasks_cleared} tarefa(s) limpa(s)${extra}`)
      // `corridas_irmas_aposentadas` vem como aviso do servidor (e o loop
      // abaixo o mostra): a aposentadoria das outras corridas do dia é um
      // efeito colateral real do gesto e não pode passar em silêncio.
      // Os avisos do servidor NUNCA são engolidos: um rerun que aconteceu mas
      // não reabriu ninguém precisa ser dito, senão o operador sai achando que
      // a cascata funcionou. (`toast` só tem success/error/info — e `error`
      // mentiria: o gesto deu certo, o alcance é que foi menor.)
      for (const a of r.avisos ?? []) toast.info(`Atenção: ${a}`)
      qc.invalidateQueries({ queryKey: ['pipeline-execucao'] })
      qc.invalidateQueries({ queryKey: ['execucoes'] })
      qc.invalidateQueries({ queryKey: ['malha-execucao'] })
      onClose()
    },
    onError: (e: unknown) => toast.error(mensagemErro(e)),
  })

  const carregando = previa.isLoading || previa.isFetching
  // Sem prévia não se confirma: é o alcance do gesto que está faltando. DAG
  // pausada também trava o botão — o servidor recusa com 409, e oferecer um
  // clique que só pode dar erro é a tela mentindo sobre o que é possível.
  const bloqueado = carregando || !!previa.error || !p || !p.dag_run_id
    || p.dag_pausada === true

  return (
    <Modal open={open} onClose={onClose} size="lg"
           title={`Reexecutar a partir de "${jobName}"`}>
      <div className="flex flex-col gap-4 text-sm">

        {/* ── Cabeçalho: de onde se está partindo ───────────────────────── */}
        <div className="rounded-lg border border-edge bg-canvas px-3 py-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
            <span className="font-mono text-ink">{pipeline}</span>
            <span className="text-dim">·</span>
            <span className="text-dim">data de referência</span>
            <span className="font-mono text-ink">{p?.data_referencia ?? dataReferencia ?? '—'}</span>
            {status && (
              <>
                <span className="text-dim">·</span>
                <span className="text-dim">etapa em {status}</span>
              </>
            )}
          </div>
          {p?.dag_run_id && (
            <div className="mt-1 truncate font-mono text-[10px] text-dim/80"
                 title={p.dag_run_id}>
              corrida: {p.dag_run_id}
            </div>
          )}
          {/* Retomar de uma etapa que DEU CERTO é legítimo (§4) — e dizê-lo
              evita que o operador ache que está fazendo algo indevido. */}
          {status && status.toUpperCase() === 'SUCCESS' && (
            <p className="mt-1.5 text-[11px] leading-snug text-dim">
              Esta etapa concluiu com sucesso. Retomar a partir dela é legítimo —
              é o caminho de quem corrigiu o dado de origem e quer refazer daqui
              para frente.
            </p>
          )}
        </div>

        {/* ── Estados de carregamento / erro ────────────────────────────── */}
        {carregando && (
          <div className="flex items-center gap-2 text-[12px] text-dim">
            <Loader2 size={14} className="animate-spin" />
            Calculando o alcance da reexecução…
          </div>
        )}

        {!!previa.error && (
          <Aviso tom="erro" icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
            {mensagemErro(previa.error)}
          </Aviso>
        )}

        {p && !p.dag_run_id && (
          <Aviso tom="erro" icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
            Não foi possível identificar a corrida desta execução no Airflow.
            Sem ela o comando atingiria todas as corridas da DAG — por isso a
            reexecução fica indisponível aqui.
          </Aviso>
        )}

        {p?.dag_pausada === true && (
          <Aviso tom="erro" icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
            Este pipeline está <strong>pausado</strong> no Airflow. Reexecutar
            agora limparia as etapas sem nada rodar, e a corrida ficaria presa
            em execução bloqueando os dependentes. Ative o pipeline e volte
            aqui.
          </Aviso>
        )}

        {p?.airflow_indisponivel && p.dag_run_id && (
          <Aviso tom="alerta" icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
            O Airflow não respondeu à simulação — a lista de etapas abaixo pode
            estar incompleta. Nada foi escondido; o que falta é dito.
          </Aviso>
        )}

        {/* ── O que acontece com o CICLO da malha (F8, Decisão 65) ───────
            "O gesto mais delicado do modelo não pode virar um clique de 3h no
            escuro": reexecutar dentro de um ciclo em voo o ALIMENTA sem
            reiniciar o relógio dele; reexecutar um ciclo já fechado o REABRE;
            e com outro ciclo em andamento, o antigo não volta. Só aparece
            quando o servidor teve certeza — sem certeza, sem frase. */}
        {deps?.corrida && (
          <Aviso tom={deps.corrida.efeito === 'reabre' ? 'alerta' : 'info'}
                 icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
            <strong>Malha {deps.corrida.malha}</strong> — ciclo de{' '}
            {deps.corrida.data_referencia}: {deps.corrida.mensagem}
          </Aviso>
        )}

        {/* ── O que acontece NESTE pipeline ─────────────────────────────── */}
        {p && (
          <section>
            <h3 className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold text-ink">
              <Layers size={13} /> Neste pipeline
            </h3>
            <div className="rounded-lg border border-edge bg-canvas px-3 py-2">
              <p className="text-[12px] text-ink">
                <strong>{p.etapas.length}</strong>{' '}
                etapa{p.etapas.length !== 1 ? 's' : ''}{' '}
                {p.etapas.length === 1 ? 'será reexecutada' : 'serão reexecutadas'}{' '}
                <span className="text-dim">(a partir desta, com tudo que depende dela)</span>
              </p>
              {p.etapas.length > 0 && (
                <ul className="mt-1.5 flex flex-wrap gap-1">
                  {p.etapas.map(e => (
                    <li key={e}
                        className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${
                          e.toLowerCase() === jobName.toLowerCase()
                            ? 'border-[#1A5FA8] bg-[#1A5FA8]/10 font-semibold text-[#1A5FA8] dark:text-blue-300'
                            : 'border-edge text-dim'}`}>
                      {e}
                    </li>
                  ))}
                </ul>
              )}
              {p.tasks_de_apoio > 0 && (
                <p className="mt-1.5 text-[10px] leading-snug text-dim">
                  Mais {p.tasks_de_apoio} tarefa(s) de apoio (marcação de
                  início/fim, publicação e cartões de notificação) — inclusive a
                  publicação que avisa os dependentes.
                </p>
              )}
            </div>
          </section>
        )}

        {/* ── A escolha da cascata: as DUAS opções, com os afetados ─────── */}
        {p && (
          <section>
            <h3 className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold text-ink">
              <GitBranch size={13} /> E os pipelines que dependem deste?
            </h3>

            {!deps?.disponivel && (deps?.dependentes.length ?? 0) > 0 && (
              <Aviso tom="alerta" icone={<AlertTriangle size={14} className="mt-0.5 shrink-0" />}>
                Cascata indisponível: {RAZOES[deps?.razao ?? ''] ?? 'motivo não informado.'}
                {' '}Só a opção “apenas este pipeline” está disponível.
              </Aviso>
            )}

            {(deps?.dependentes.length ?? 0) === 0 ? (
              <div className="flex items-start gap-2 rounded-lg border border-edge bg-canvas px-3 py-2 text-[12px] text-dim">
                <Info size={14} className="mt-0.5 shrink-0" />
                Nenhum pipeline depende deste. A escolha de cascata não se aplica.
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <Opcao
                  marcada={!cascata}
                  onMarcar={() => setCascata(false)}
                  titulo="Apenas este pipeline"
                  resumo={`${deps!.dependentes.length} dependente(s) NÃO serão reexecutados`}
                >
                  {/* O segundo sentido do "nunca em silêncio": o que fica para
                      trás está escrito, não subentendido. */}
                  <p className="text-[11px] leading-snug text-amber-700 dark:text-amber-400">
                    <AlertTriangle size={11} className="mr-1 inline" />
                    Os dependentes continuam com o resultado da execução
                    anterior. Se este reprocesso mudar o dado, eles ficam
                    desatualizados até rodarem de novo.
                  </p>
                  <ListaPipelines nomes={deps!.dependentes} corridas={deps!.corridas} />
                </Opcao>

                <Opcao
                  marcada={cascata}
                  onMarcar={() => podeCascata && setCascata(true)}
                  desabilitada={!podeCascata}
                  titulo="Este e os dependentes (cascata)"
                  resumo={
                    deps!.com_corrida.length > 0
                      ? `${deps!.com_corrida.length} pipeline(s) rodam de novo, na mesma data de referência`
                      : 'nenhum dependente rodou nesta data — não há o que reabrir'
                  }
                >
                  {deps!.com_corrida.length > 0 && (
                    <>
                      <p className="text-[11px] leading-snug text-dim">
                        A corrida de hoje de cada um é aposentada (o histórico
                        dela fica) e eles são disparados de novo pelo caminho
                        normal, quando este pipeline concluir.
                      </p>
                      <ListaPipelines nomes={deps!.com_corrida}
                                      corridas={deps!.corridas} destaque />
                    </>
                  )}
                  {deps!.sem_corrida.length > 0 && (
                    <p className="text-[11px] leading-snug text-dim">
                      Sem corrida nesta data (nada a reabrir):{' '}
                      <span className="font-mono">{deps!.sem_corrida.join(', ')}</span>.
                      {' '}Eles rodam sozinhos quando a condição fechar.
                    </p>
                  )}
                  {deps!.truncado && (
                    <p className="text-[11px] leading-snug text-amber-700 dark:text-amber-400">
                      <AlertTriangle size={11} className="mr-1 inline" />
                      A cadeia é maior que o limite de segurança — pode haver
                      pipeline a jusante fora desta lista.
                    </p>
                  )}
                </Opcao>
              </div>
            )}
          </section>
        )}

        {/* ── Ações ────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-2 border-t border-edge pt-3">
          <button
            onClick={onClose}
            className="rounded-md border border-edge px-3 py-1.5 text-[12px] text-dim hover:bg-edge/40 hover:text-ink"
          >
            Cancelar
          </button>
          <button
            onClick={() => executar.mutate()}
            disabled={bloqueado || executar.isPending}
            className="inline-flex items-center gap-1.5 rounded-md bg-[#1A5FA8] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[#164e8b] disabled:opacity-40 disabled:pointer-events-none"
          >
            {executar.isPending
              ? <Loader2 size={13} className="animate-spin" />
              : <RefreshCw size={13} />}
            {cascataEfetiva ? 'Reexecutar com dependentes' : 'Reexecutar apenas este'}
            <ArrowRight size={13} />
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ─────────────────────────────── auxiliares ─────────────────────────────────

function Opcao({
  marcada, onMarcar, desabilitada = false, titulo, resumo, children,
}: {
  marcada: boolean
  onMarcar: () => void
  desabilitada?: boolean
  titulo: string
  resumo: string
  children?: React.ReactNode
}) {
  return (
    <label
      className={[
        'flex cursor-pointer gap-2 rounded-lg border px-3 py-2 transition-colors',
        desabilitada ? 'cursor-not-allowed opacity-50' : '',
        marcada
          ? 'border-[#1A5FA8] bg-[#1A5FA8]/5'
          : 'border-edge bg-canvas hover:border-dim',
      ].join(' ')}
    >
      <input
        type="radio"
        name="rerun-cascata"
        checked={marcada}
        disabled={desabilitada}
        onChange={onMarcar}
        className="mt-0.5 shrink-0 accent-[#1A5FA8]"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-ink">
          {marcada && <CheckCircle2 size={12} className="text-[#1A5FA8]" />}
          {titulo}
        </span>
        <span className="text-[11px] text-dim">{resumo}</span>
        {children}
      </div>
    </label>
  )
}

/** Lista de pipelines afetados, com o status da corrida de hoje de cada um —
 *  é o que responde "o que exatamente vai ser mexido". */
function ListaPipelines({
  nomes, corridas, destaque = false,
}: {
  nomes: string[]
  corridas: Record<string, CorridaAfetada[]>
  destaque?: boolean
}) {
  if (!nomes.length) return null
  return (
    <ul className="flex flex-col gap-0.5">
      {nomes.map(n => {
        const c = (corridas[n.toLowerCase()] ?? [])[0]
        return (
          <li key={n} className="flex items-center gap-1.5 text-[11px]">
            <span className={`h-1 w-1 shrink-0 rounded-full ${
              destaque ? 'bg-[#1A5FA8]' : 'bg-dim'}`} />
            <span className="truncate font-mono text-ink">{n}</span>
            {c?.status && <span className="shrink-0 text-dim">· {c.status}</span>}
            {c?.disparado_por && (
              <span className="hidden shrink-0 text-dim/70 sm:inline">
                · por {c.disparado_por}
              </span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function Aviso({ tom, icone, children }: {
  // `info` (F8): o ciclo em voo que só ganha um pipeline a mais NÃO é um
  // problema — pintá-lo de âmbar junto com "DAG pausada" ensinaria o olho a
  // ignorar o âmbar justamente onde ele importa.
  tom: 'info' | 'alerta' | 'erro'
  icone: React.ReactNode
  children: React.ReactNode
}) {
  const cls = tom === 'erro'
    ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
    : tom === 'info'
    ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300'
    : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[11px] leading-snug ${cls}`}>
      {icone}
      <span>{children}</span>
    </div>
  )
}

/** O 409 de ambiguidade chega com `detail` OBJETO (erro/mensagem/candidatos).
 *
 *  `apiFetch` só usa `detail` como `message` quando ele é STRING — com objeto a
 *  mensagem vira "409 Conflict", que não diz nada ao operador. O detalhe cru
 *  fica em `err.detail` de propósito (ver lib/api.ts), e é dele que sai o
 *  texto: sem isto, a recusa mais importante desta fase — "há N corridas neste
 *  dia, escolha qual" — apareceria como um código HTTP. */
function mensagemErro(e: unknown): string {
  const det = (e as { detail?: unknown })?.detail
  if (det && typeof det === 'object' && 'mensagem' in (det as object)) {
    return String((det as { mensagem: unknown }).mensagem)
  }
  if (typeof det === 'string' && det) return det
  return (e as { message?: string })?.message || 'Erro desconhecido'
}
