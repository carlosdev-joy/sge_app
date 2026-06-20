import { useState, useMemo, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Textarea } from '../ui/Input'
import { toast } from '../ui/Toast'
import { ChevronRight, ChevronDown, History, GitBranch, PowerOff, Settings, Play, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react'
import type { Pipeline, AuditRow, LineageObject, LineageJob } from '../../types/pipeline'
import { SCHEDULE_LABELS, critColor, buildCron } from './pipelineUtils'

// ── ViewModal ─────────────────────────────────────────────────────────────────

export function ViewModal({ pipeline: p, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const pill = (v: string, active = false) => (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${active ? 'bg-green-900/20 text-green-400 border-green-800/40' : 'bg-panel text-dim border-edge'}`}>{v}</span>
  )
  const cell = (label: string, val: React.ReactNode, spanFull = false) => (
    <div className={`flex flex-col gap-0.5 ${spanFull ? 'col-span-2' : ''}`}>
      <span className="text-[10px] font-bold uppercase tracking-wider text-dim">{label}</span>
      <div className="text-sm font-medium text-ink min-h-[1.25rem]">
        {val || <span className="text-dim/50 italic text-xs">—</span>}
      </div>
    </div>
  )
  const notifs = [p.envia_msg_inicio && 'Início', p.envia_msg_fim && 'Conclusão', p.envia_msg_erro && 'Erro'].filter(Boolean)
  const cron = p.schedule_type && p.schedule_type !== 'on_demand'
    ? buildCron(p.schedule_type, p.schedule_hour ?? 6, p.schedule_minute ?? 0, p.schedule_dow ?? 1, p.schedule_dom ?? 1)
    : null

  return (
    <Modal open title={p.pipeline_name} onClose={onClose} size="lg">
      <div className="overflow-y-auto max-h-[70vh] pr-1">
        {!p.active && (
          <div className="mb-4 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2.5">
            <div className="flex items-center gap-1.5 text-amber-400 font-semibold text-xs mb-1">
              <PowerOff size={13} /> Pipeline inativo — indisponível para execução
            </div>
            <div className="text-sm text-amber-200 whitespace-pre-wrap">
              {p.motivo_inativacao || <span className="italic text-amber-400/60">Motivo não informado.</span>}
            </div>
            {(p.inativado_por || p.inativado_em) && (
              <div className="text-[10px] text-amber-400/70 mt-1.5">
                {p.inativado_por ? `por ${p.inativado_por}` : ''}{p.inativado_em ? ` · ${p.inativado_em}` : ''}
              </div>
            )}
          </div>
        )}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Identificação</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Projeto',     p.project_name)}
            {cell('Domínio',     p.domain)}
            {cell('Ambiente',    p.ambiente)}
            {cell('Criticidade', <span className={`font-semibold ${critColor(p.criticidade)}`}>{p.criticidade}</span>)}
            {cell('Status',
              <div className="flex flex-wrap gap-1.5">
                {pill(p.active ? 'Ativo' : 'Inativo', !!p.active)}
                {pill(p.dag_criada ? 'DAG ✓' : 'DAG não gerada', !!p.dag_criada)}
              </div>
            )}
            {cell('Tags',
              p.tags
                ? <div className="flex flex-wrap gap-1">{p.tags.split(',').map(t => pill(t.trim(), true))}</div>
                : null
            )}
          </div>
        </div>

        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Agendamento</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Tipo',          p.schedule_type ? SCHEDULE_LABELS[p.schedule_type] ?? p.schedule_type : null)}
            {cell('Horário',       p.scheduled_time)}
            {cell('Expressão CRON', cron)}
            {cell('Data início',   p.dag_start_date || 'Imediato')}
            {cell('SLA',           p.sla_minutos ? `${p.sla_minutos} min` : null)}
            {cell('Depende de',
              p.depends_on
                ? <div className="flex flex-wrap gap-1">{p.depends_on.split(',').map(d => pill(d.trim()))}</div>
                : null
            )}
          </div>
        </div>

        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Execução</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Runs simultâneas', p.max_active_runs ?? 1)}
            {cell('Retries',          `${p.retries_count ?? 1}x · delay ${p.retry_delay_seconds ?? 300}s`)}
            {cell('Fila (pool)',       p.pool_name || 'padrão')}
            {cell('Notificações',      notifs.length ? notifs.join(' · ') : null)}
            {cell('Última execução',   p.last_execution)}
          </div>
        </div>

        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Metadados</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Criado em',  p.created_at)}
            {cell('Atualizado', p.updated_at)}
          </div>
        </div>

        {p.descricao && (
          <div className="mb-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Descrição</p>
            <p className="text-xs text-ink whitespace-pre-wrap leading-relaxed">{p.descricao}</p>
          </div>
        )}

        {p.runbook_md && (
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Runbook</p>
            <pre className="text-xs text-dim whitespace-pre-wrap font-mono bg-canvas border border-edge rounded-lg p-3 leading-relaxed">{p.runbook_md}</pre>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── AuditModal ────────────────────────────────────────────────────────────────

function AuditGroup({ day, rows }: { day: string; rows: AuditRow[] }) {
  const [open, setOpen] = useState(false)
  const fmt  = day.split('-').reverse().join('/')
  const user = rows[0]?.changed_by ?? '—'
  return (
    <div className="border border-edge rounded-lg mb-2 overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-canvas hover:bg-edge/20 transition-colors text-left">
        <span className="text-sm font-semibold">{fmt}</span>
        <span className="text-xs text-dim">{user} · {rows.length} campo(s)</span>
        {open ? <ChevronDown size={14} className="text-dim" /> : <ChevronRight size={14} className="text-dim" />}
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-t border-edge bg-canvas/50 text-dim">
                {['Hora','Usuário','Campo','Antes','Depois'].map(h => (
                  <th key={h} className="px-3 py-1.5 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const time = r.changed_at.includes('T')
                  ? r.changed_at.split('T')[1].substring(0, 8)
                  : r.changed_at.substring(11, 19)
                return (
                  <tr key={i} className="border-t border-edge/40">
                    <td className="px-3 py-1.5 text-dim">{time}</td>
                    <td className="px-3 py-1.5">{r.changed_by || '—'}</td>
                    <td className="px-3 py-1.5 font-medium">{r.field_name || '—'}</td>
                    <td className="px-3 py-1.5 text-dim truncate max-w-[150px]" title={r.old_value ?? ''}>{(r.old_value ?? '—').substring(0, 60)}</td>
                    <td className="px-3 py-1.5 truncate max-w-[150px]" title={r.new_value ?? ''}>{(r.new_value ?? '—').substring(0, 60)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function AuditModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ data: AuditRow[] }>({
    queryKey: ['pipeline-audit', pipeline.pipeline_name],
    queryFn: () => apiFetch(`/audit?pipeline_name=${encodeURIComponent(pipeline.pipeline_name)}&limit=50`),
  })
  const rows = data?.data ?? []
  const byDate = useMemo(() => {
    const m: Record<string, AuditRow[]> = {}
    rows.forEach(r => {
      const day = (r.changed_at || '').substring(0, 10) || 'Desconhecido'
      if (!m[day]) m[day] = []
      m[day].push(r)
    })
    return Object.entries(m).sort(([a], [b]) => b.localeCompare(a))
  }, [rows])

  return (
    <Modal open title={`Histórico — ${pipeline.pipeline_name}`} onClose={onClose} size="lg">
      <div className="text-xs text-dim bg-canvas border border-edge rounded-lg px-3 py-2 mb-3">
        📌 São exibidas as <strong className="text-ink">últimas 50 alterações</strong>. O registro de criação é sempre preservado.
      </div>
      {isLoading && <div className="py-8 text-center text-dim text-sm">Carregando…</div>}
      {!isLoading && rows.length === 0 && (
        <div className="py-12 flex flex-col items-center gap-2 text-dim">
          <History size={32} className="opacity-30" />
          <p className="text-sm">Sem histórico registrado</p>
          <p className="text-xs">Alterações futuras aparecerão aqui.</p>
        </div>
      )}
      {byDate.map(([day, dayRows]) => <AuditGroup key={day} day={day} rows={dayRows} />)}
    </Modal>
  )
}

// ── LineageModal ──────────────────────────────────────────────────────────────

export function LineageModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const { data, isLoading, error } = useQuery<{ pipeline_name: string; jobs: LineageJob[] }>({
    queryKey: ['pipeline-lineage', pipeline.pipeline_name],
    queryFn: () => apiFetch(`/lineage?pipeline_name=${encodeURIComponent(pipeline.pipeline_name)}`),
  })
  const jobs = data?.jobs ?? []

  const origens = useMemo(() => {
    const seen: Record<string, LineageObject> = {}
    jobs.forEach(j => (j.origens || []).forEach(o => {
      const k = o.object_name.toLowerCase()
      if (!seen[k]) seen[k] = o
    }))
    return Object.values(seen).sort((a, b) => a.object_name.localeCompare(b.object_name))
  }, [jobs])

  const destinos = useMemo(() => {
    const seen: Record<string, LineageObject> = {}
    jobs.forEach(j => (j.destinos || []).forEach(o => {
      const k = o.object_name.toLowerCase()
      if (!seen[k]) seen[k] = o
    }))
    return Object.values(seen).sort((a, b) => a.object_name.localeCompare(b.object_name))
  }, [jobs])

  return (
    <Modal open title={`Lineage — ${pipeline.pipeline_name}`} onClose={onClose} size="lg">
      {isLoading && <div className="py-8 text-center text-dim text-sm">Carregando lineage…</div>}
      {!!error && <p className="text-red-400 text-sm py-4">Erro ao carregar lineage</p>}
      {!isLoading && !error && jobs.length === 0 && (
        <div className="py-12 flex flex-col items-center gap-2 text-dim">
          <GitBranch size={32} className="opacity-30" />
          <p className="text-sm">Nenhum job cadastrado</p>
          <p className="text-xs">Adicione jobs ao pipeline para visualizar o lineage.</p>
        </div>
      )}
      {!isLoading && jobs.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[1fr_36px_auto_36px_1fr] gap-2 items-start py-2 min-w-[480px]">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 text-center">
                  Origens ({origens.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {origens.length ? origens.map(o => (
                    <div key={o.object_name}
                      className="border border-blue-800/40 bg-blue-900/10 rounded-lg px-2.5 py-1.5 text-xs"
                      title={`${o.object_name}${o.database_name ? ' · ' + o.database_name : ''}`}>
                      <div className="font-mono font-medium text-blue-300 truncate">{o.object_name}</div>
                      <div className="text-[10px] text-dim/60">{o.database_name || o.object_type}</div>
                    </div>
                  )) : <span className="text-xs text-dim/50 italic text-center block mt-2">sem origens</span>}
                </div>
              </div>
              <div className="text-center text-dim text-xl font-thin mt-8">→</div>
              <div className="flex flex-col items-center mt-4">
                <div className="border border-edge bg-panel rounded-xl px-4 py-3 min-w-[140px] text-center">
                  <div className="font-mono text-sm font-bold text-ink truncate">{pipeline.pipeline_name}</div>
                  <div className="text-[10px] text-dim mt-0.5">{jobs.length} job(s)</div>
                </div>
              </div>
              <div className="text-center text-dim text-xl font-thin mt-8">→</div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-green-400 mb-2 text-center">
                  Destinos ({destinos.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {destinos.length ? destinos.map(o => (
                    <div key={o.object_name}
                      className="border border-green-800/40 bg-green-900/10 rounded-lg px-2.5 py-1.5 text-xs"
                      title={`${o.object_name}${o.database_name ? ' · ' + o.database_name : ''}`}>
                      <div className="font-mono font-medium text-green-300 truncate">{o.object_name}</div>
                      <div className="text-[10px] text-dim/60">{o.database_name || o.object_type}</div>
                    </div>
                  )) : <span className="text-xs text-dim/50 italic text-center block mt-2">sem destinos</span>}
                </div>
              </div>
            </div>
          </div>
          <p className="text-xs text-dim/60 text-center border-t border-edge pt-2 mt-1">
            Visualização consolidada — para detalhe por job, use Governança › Lineage.
          </p>
        </>
      )}
    </Modal>
  )
}

// ── InactivateModal ───────────────────────────────────────────────────────────

export function InactivateModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const qc   = useQueryClient()
  const user = useAuthStore(s => s.user)
  const [motivo, setMotivo] = useState('')
  const motivoOk = motivo.trim().length >= 5
  const mut  = useMutation({
    mutationFn: () => apiFetch<{ dag_sync?: { attempted: boolean; exists: boolean | null; is_paused: boolean | null; error: string | null } | null }>('/pipelines/register', {
      method: 'POST',
      body: JSON.stringify({
        motivo_inativacao:   motivo.trim(),
        pipeline_name:       pipeline.pipeline_name,
        scheduled_time:      pipeline.scheduled_time ?? '00:00:00',
        schedule_type:       pipeline.schedule_type,
        schedule_hour:       pipeline.schedule_hour,
        schedule_minute:     pipeline.schedule_minute,
        schedule_dow:        pipeline.schedule_dow,
        schedule_dom:        pipeline.schedule_dom,
        active:              0,
        envia_msg_inicio:    pipeline.envia_msg_inicio,
        envia_msg_fim:       pipeline.envia_msg_fim,
        envia_msg_erro:      pipeline.envia_msg_erro,
        project_name:        pipeline.project_name ?? '',
        domain:              pipeline.domain ?? '',
        tags:                pipeline.tags ?? '',
        dag_criada:          pipeline.dag_criada,
        descricao:           pipeline.descricao ?? null,
        criticidade:         pipeline.criticidade ?? 'Media',
        sla_minutos:         pipeline.sla_minutos ?? null,
        ambiente:            pipeline.ambiente ?? 'PROD',
        max_active_runs:     pipeline.max_active_runs ?? 1,
        retries_count:       pipeline.retries_count ?? 1,
        retry_delay_seconds: pipeline.retry_delay_seconds ?? 300,
        pool_name:           pipeline.pool_name ?? null,
        depends_on:          pipeline.depends_on ?? null,
        runbook_md:          pipeline.runbook_md ?? null,
        dag_start_date:      pipeline.dag_start_date ?? null,
        changed_by:          user?.matricula ?? 'react-ui',
      }),
    }),
    onSuccess: (res) => {
      const ds = res?.dag_sync
      const base = `Pipeline "${pipeline.pipeline_name}" inativado`
      if (ds?.error)              toast.error(`${base}. Atenção: DAG não pausada no Airflow: ${ds.error}`)
      else if (ds?.exists && ds?.is_paused) toast.success(`${base} · DAG pausada no Airflow`)
      else if (ds?.exists === false)        toast.success(`${base} (sem DAG no Airflow)`)
      else                                  toast.success(base)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.message),
  })
  return (
    <Modal open title="Inativar pipeline" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Inativar <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span>?
          Pode ser reativado a qualquer momento pela edição.
        </p>
        <div className="flex flex-col gap-1">
          <Textarea
            label="Motivo da inativação *"
            rows={3}
            value={motivo}
            onChange={e => setMotivo(e.target.value)}
            placeholder="Ex.: aguardando correção da origem X / migração em andamento / solicitado pela área Y…"
            autoFocus
          />
          <span className="text-[11px] text-dim">
            Obrigatório. Fica visível na lista e nos detalhes do pipeline, para que a equipe saiba
            por que o fluxo está indisponível para execução.
          </span>
        </div>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={mut.isPending} disabled={!motivoOk}
            className="border-amber-800/40 text-amber-400 disabled:opacity-40 disabled:cursor-not-allowed"
            title={motivoOk ? 'Inativar pipeline' : 'Informe o motivo (mín. 5 caracteres)'}
            onClick={() => { if (motivoOk) mut.mutate() }}>
            <PowerOff size={13} /> Inativar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── GenDagModal ───────────────────────────────────────────────────────────────

type GenPhase = 'confirm' | 'working' | 'done' | 'timeout' | 'error'

export function GenDagModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const qc = useQueryClient()
  const [phase, setPhase]         = useState<GenPhase>('confirm')
  const [statusMsg, setStatusMsg] = useState('')
  const [errMsg, setErrMsg]       = useState('')
  const [finalPaused, setFinalPaused] = useState<boolean | null>(null)
  const cancelled = useRef(false)
  useEffect(() => () => { cancelled.current = true }, [])

  const sleep = (ms: number) => new Promise(res => setTimeout(res, ms))
  const enc = encodeURIComponent(pipeline.pipeline_name)

  async function run() {
    setPhase('working'); setErrMsg('')
    setStatusMsg('Disparando a geração da DAG (etl_dag_factory)…')
    try {
      await apiFetch(`/pipelines/${enc}/gerar-dag`, { method: 'POST' })
    } catch (e: any) {
      setErrMsg(e?.message || 'Falha ao disparar a geração'); setPhase('error'); return
    }
    setStatusMsg('DAG criada no servidor. Aguardando o Airflow registrá-la na UI…')
    const MAX = 36   // 36 × 5s = 3 min
    for (let i = 0; i < MAX; i++) {
      if (cancelled.current) return
      await sleep(5000)
      if (cancelled.current) return
      let r: any
      try {
        r = await apiFetch<{ exists: boolean; is_paused: boolean | null; ready: boolean; error: string | null }>(
          `/pipelines/${enc}/dag-sync`, { method: 'POST' })
      } catch { continue }   // erro transitório — segue tentando
      if (cancelled.current) return
      if (!r?.exists) { setStatusMsg(`Aguardando o Airflow registrar a DAG… (${i + 1}/${MAX})`); continue }
      if (r.ready) {
        qc.invalidateQueries({ queryKey: ['pipelines'] })
        setFinalPaused(!!r.is_paused); setPhase('done'); return
      }
      setStatusMsg(r.error ? `DAG registrada; ajustando estado… (${r.error})` : 'DAG registrada. Ativando…')
    }
    qc.invalidateQueries({ queryKey: ['pipelines'] })
    setPhase('timeout')
  }

  return (
    <Modal open title={pipeline.dag_criada ? 'Regenerar DAG' : 'Gerar DAG'} onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        {phase === 'confirm' && (
          <>
            <p className="text-sm text-dim">
              {pipeline.dag_criada
                ? <>Regenerar a DAG de <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span>? A DAG no Airflow será atualizada com as configurações atuais.</>
                : <>Gerar a DAG para <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span> no Airflow via etl_dag_factory?</>}
            </p>
            <p className="text-xs text-dim bg-canvas border border-edge rounded-lg px-3 py-2">
              O Orquestra dispara a geração, aguarda o Airflow registrar a DAG e a deixa
              {pipeline.active
                ? <span className="text-green-400 font-medium"> ativa</span>
                : <span className="text-amber-400 font-medium"> pausada (pipeline inativo)</span>}
              {' '}automaticamente. Só é concluída quando estiver disponível no estado correto.
            </p>
            {pipeline.dag_criada && (
              <p className="text-xs text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2">
                ⚠ A DAG existente será sobrescrita com as configurações atuais do pipeline.
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-edge pt-3">
              <Button variant="secondary" onClick={onClose}>Cancelar</Button>
              <Button className="border-blue-800/40 text-blue-400" onClick={run}>
                <Settings size={13} /> {pipeline.dag_criada ? 'Regenerar' : 'Gerar DAG'}
              </Button>
            </div>
          </>
        )}

        {phase === 'working' && (
          <div className="flex flex-col gap-3 py-1">
            <div className="flex items-center gap-2 text-sm text-ink">
              <Loader2 size={16} className="animate-spin text-blue-400" /> Processando…
            </div>
            <p className="text-xs text-dim min-h-[2rem]">{statusMsg}</p>
            <p className="text-[11px] text-dim">
              Pode levar de alguns segundos a poucos minutos (tempo do scheduler do Airflow
              parsear a DAG). Pode fechar — a ativação continua em segundo plano.
            </p>
            <div className="flex justify-end border-t border-edge pt-3">
              <Button variant="secondary" onClick={onClose}>Fechar</Button>
            </div>
          </div>
        )}

        {phase === 'done' && (
          <div className="flex flex-col gap-3 py-1">
            <div className="flex items-center gap-2 text-sm text-green-400 font-medium">
              <CheckCircle2 size={16} /> DAG pronta no Airflow
            </div>
            <p className="text-xs text-dim">
              <span className="font-mono text-ink">{pipeline.pipeline_name}</span> está disponível e{' '}
              {finalPaused
                ? <span className="text-amber-400">pausada (pipeline inativo)</span>
                : <span className="text-green-400">ativa para execução</span>}.
            </p>
            <div className="flex justify-end border-t border-edge pt-3">
              <Button className="border-green-800/40 text-green-400" onClick={onClose}>Concluir</Button>
            </div>
          </div>
        )}

        {phase === 'timeout' && (
          <div className="flex flex-col gap-3 py-1">
            <div className="flex items-center gap-2 text-sm text-amber-400 font-medium">
              <AlertTriangle size={16} /> Ainda registrando
            </div>
            <p className="text-xs text-dim">
              A DAG foi criada no servidor, mas o Airflow ainda não a disponibilizou. A ativação
              automática continua em segundo plano — recarregue a lista em alguns minutos.
            </p>
            <div className="flex justify-end border-t border-edge pt-3">
              <Button variant="secondary" onClick={onClose}>Fechar</Button>
            </div>
          </div>
        )}

        {phase === 'error' && (
          <div className="flex flex-col gap-3 py-1">
            <div className="flex items-center gap-2 text-sm text-red-400 font-medium">
              <AlertTriangle size={16} /> Erro ao gerar
            </div>
            <p className="text-xs text-red-300 break-words">{errMsg}</p>
            <div className="flex justify-end gap-2 border-t border-edge pt-3">
              <Button variant="secondary" onClick={onClose}>Fechar</Button>
              <Button className="border-blue-800/40 text-blue-400" onClick={() => setPhase('confirm')}>Tentar de novo</Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── ExecModal ─────────────────────────────────────────────────────────────────

export function ExecModal({ pipeline, onConfirm, onClose, loading }: {
  pipeline: Pipeline; onConfirm: () => void; onClose: () => void; loading: boolean
}) {
  return (
    <Modal open title="Executar pipeline agora" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Disparar <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span> agora, fora do agendamento?
        </p>
        <p className="text-xs text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2">
          ⚠ Inicia uma execução imediata no Airflow. Certifique-se que não há execução ativa.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancelar</Button>
          <Button loading={loading} className="border-green-800/40 text-green-400" onClick={onConfirm}>
            <Play size={13} /> Executar
          </Button>
        </div>
      </div>
    </Modal>
  )
}
