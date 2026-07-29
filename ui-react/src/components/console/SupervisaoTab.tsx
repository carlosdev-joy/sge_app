import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { Badge } from '../ui/Badge'
import { Modal } from '../ui/Modal'
import { Switch } from '../ui/Switch'
import { Checkbox } from '../ui/Checkbox'
import { toast } from '../ui/Toast'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Plus, Pencil, Trash2, ShieldCheck } from 'lucide-react'

// ── Cadastro dos jobs supervisionados (aba do Console DataStage) ────────────
// A coleta (DAG), o painel do dashboard e o card do Teams são as fases
// seguintes da spec docs/spec-supervisao-ds.md — aqui é só o cadastro.

export interface SupervisaoJob {
  id: number
  project: string
  job_name: string
  descricao: string | null
  janela_inicio: string      // HH:MM:SS
  janela_fim: string         // HH:MM:SS
  tolerancia_min: number
  dias_semana: string        // CSV ISO: 1=seg … 7=dom
  vigencia_inicio: string    // AAAA-MM-DD
  max_linhas: number
  grupo_id: number | null
  template_id: number | null
  alerta_abortou: boolean
  alerta_nao_executou: boolean
  alerta_atraso: boolean
  alerta_estrutura: boolean
  ativo: boolean
  created_by: string | null
  created_at: string
  updated_at: string
  grupo_nome: string | null
  template_nome: string | null
}

interface MsgGrupo { id: number; nome: string; ativo: boolean; has_webhook: boolean }
interface MsgTemplate { id: number; nome: string; ativo: boolean }

const DIAS = [
  { v: '1', label: 'Seg' }, { v: '2', label: 'Ter' }, { v: '3', label: 'Qua' },
  { v: '4', label: 'Qui' }, { v: '5', label: 'Sex' }, { v: '6', label: 'Sáb' },
  { v: '7', label: 'Dom' },
]

const ALERTAS = [
  { campo: 'alerta_abortou',      label: 'Job abortou',          hint: 'Run encontrado na janela, mas terminou abortado.' },
  { campo: 'alerta_nao_executou', label: 'Não executou',         hint: 'Nenhum run no dia previsto.' },
  { campo: 'alerta_atraso',       label: 'Iniciou com atraso',   hint: 'Passou o fim da janela + tolerância sem iniciar.' },
  { campo: 'alerta_estrutura',    label: 'Falha de estrutura',   hint: 'O dsjob não conseguiu ler o job (projeto/job inexistente, SSH fora).' },
] as const

function hoje(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/** 'HH:MM:SS' → 'HH:MM' (o input type=time trabalha com HH:MM). */
function hhmm(valor: string): string {
  return (valor || '').slice(0, 5)
}

function rotuloDias(csv: string): string {
  const set = new Set((csv || '').split(',').map(s => s.trim()))
  if (set.size === 7) return 'todos os dias'
  const uteis = ['1', '2', '3', '4', '5']
  if (set.size === 5 && uteis.every(d => set.has(d))) return 'seg–sex'
  return DIAS.filter(d => set.has(d.v)).map(d => d.label).join(', ') || '—'
}

interface FormState {
  project: string
  job_name: string
  descricao: string
  janela_inicio: string
  janela_fim: string
  tolerancia_min: string
  dias: string[]
  vigencia_inicio: string
  max_linhas: string
  grupo_id: string
  template_id: string
  alerta_abortou: boolean
  alerta_nao_executou: boolean
  alerta_atraso: boolean
  alerta_estrutura: boolean
}

function formVazio(project: string, job: string): FormState {
  return {
    project, job_name: job, descricao: '',
    janela_inicio: '02:00', janela_fim: '03:00', tolerancia_min: '0',
    dias: ['1', '2', '3', '4', '5'], vigencia_inicio: hoje(), max_linhas: '200',
    grupo_id: '', template_id: '',
    alerta_abortou: true, alerta_nao_executou: true, alerta_atraso: true, alerta_estrutura: true,
  }
}

function formDeJob(j: SupervisaoJob): FormState {
  return {
    project: j.project, job_name: j.job_name, descricao: j.descricao ?? '',
    janela_inicio: hhmm(j.janela_inicio), janela_fim: hhmm(j.janela_fim),
    tolerancia_min: String(j.tolerancia_min),
    dias: (j.dias_semana || '').split(',').map(s => s.trim()).filter(Boolean),
    vigencia_inicio: j.vigencia_inicio, max_linhas: String(j.max_linhas),
    grupo_id: j.grupo_id ? String(j.grupo_id) : '',
    template_id: j.template_id ? String(j.template_id) : '',
    alerta_abortou: j.alerta_abortou, alerta_nao_executou: j.alerta_nao_executou,
    alerta_atraso: j.alerta_atraso, alerta_estrutura: j.alerta_estrutura,
  }
}

export function SupervisaoTab({ project, job }: { project: string; job: string }) {
  const queryClient = useQueryClient()
  const [editando, setEditando] = useState<SupervisaoJob | null>(null)
  const [criando, setCriando] = useState(false)
  const [removendo, setRemovendo] = useState<SupervisaoJob | null>(null)
  const [form, setForm] = useState<FormState>(() => formVazio('', ''))

  const lista = useQuery<{ data: SupervisaoJob[] }>({
    queryKey: ['ds-supervisao'],
    queryFn: () => apiFetch('/admin/ds/supervisao'),
  })
  const grupos = useQuery<{ data: MsgGrupo[] }>({
    queryKey: ['msg-grupos'],
    queryFn: () => apiFetch('/msg/grupos'),
  })
  const templates = useQuery<{ data: MsgTemplate[] }>({
    queryKey: ['msg-templates'],
    queryFn: () => apiFetch('/msg/templates'),
  })

  const invalidar = () => queryClient.invalidateQueries({ queryKey: ['ds-supervisao'] })

  const fecharForm = () => { setCriando(false); setEditando(null) }

  const salvar = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      editando
        ? apiFetch<{ ok: boolean }>(`/admin/ds/supervisao/${editando.id}`, {
            method: 'PATCH', body: JSON.stringify(payload),
          })
        : apiFetch<{ ok: boolean; reativado: boolean }>('/admin/ds/supervisao', {
            method: 'POST', body: JSON.stringify(payload),
          }),
    onSuccess: (res) => {
      const reativado = (res as { reativado?: boolean }).reativado
      toast.success(editando ? 'Supervisão atualizada'
        : reativado ? 'Job reativado — o histórico anterior foi mantido'
        : 'Job incluído na supervisão')
      invalidar(); fecharForm()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remover = useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ removido: string; historico: number }>(`/admin/ds/supervisao/${id}`, { method: 'DELETE' }),
    onSuccess: (res) => {
      toast.success(res.removido === 'logico'
        ? `Job desativado — ${res.historico} registro(s) de histórico preservados`
        : 'Cadastro removido (não havia histórico)')
      invalidar(); setRemovendo(null)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const abrirNovo = () => {
    setForm(formVazio(project.trim(), job.trim()))
    setEditando(null); setCriando(true)
  }

  const abrirEdicao = (j: SupervisaoJob) => {
    setForm(formDeJob(j))
    setCriando(false); setEditando(j)
  }

  const alternarDia = (v: string) => setForm(f => ({
    ...f,
    dias: f.dias.includes(v) ? f.dias.filter(d => d !== v) : [...f.dias, v],
  }))

  const submeter = () => {
    if (!form.dias.length) { toast.error('Selecione ao menos um dia da semana.'); return }
    const payload: Record<string, unknown> = {
      descricao: form.descricao,
      janela_inicio: form.janela_inicio,
      janela_fim: form.janela_fim,
      tolerancia_min: form.tolerancia_min,
      dias_semana: form.dias.join(','),
      vigencia_inicio: form.vigencia_inicio,
      max_linhas: form.max_linhas,
      grupo_id: form.grupo_id === '' ? null : form.grupo_id,
      template_id: form.template_id === '' ? null : form.template_id,
      alerta_abortou: form.alerta_abortou,
      alerta_nao_executou: form.alerta_nao_executou,
      alerta_atraso: form.alerta_atraso,
      alerta_estrutura: form.alerta_estrutura,
    }
    // project/job_name são imutáveis na edição: o histórico é ligado a eles.
    if (!editando) { payload.project = form.project; payload.job_name = form.job_name }
    salvar.mutate(payload)
  }

  const jobs = lista.data?.data ?? []
  const gruposAtivos = (grupos.data?.data ?? []).filter(g => g.ativo)
  const templatesAtivos = (templates.data?.data ?? []).filter(t => t.ativo)
  const formAberto = criando || !!editando

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ShieldCheck size={16} className="text-dim shrink-0" />
          <p className="text-xs text-dim">
            Jobs acompanhados automaticamente: a coleta roda a cada 15 min, compara com a
            janela esperada e avisa no canal escolhido. A supervisão passa a valer a partir
            da <strong>data de vigência</strong> — e o primeiro ciclo já envia a situação do
            dia para você conferir a configuração.
          </p>
          <Button size="sm" className="ml-auto" onClick={abrirNovo}>
            <Plus size={14} className="mr-1" /> Supervisionar job
          </Button>
        </div>

        {lista.isLoading && <p className="text-xs text-dim">Carregando…</p>}

        {!lista.isLoading && jobs.length === 0 && (
          <p className="text-xs text-dim">
            Nenhum job supervisionado ainda. Selecione projeto e job acima e clique em
            <strong> Supervisionar job</strong> — os campos já vêm preenchidos.
          </p>
        )}

        {jobs.length > 0 && (
          <div className="overflow-x-auto">
            <Table dense>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Janela</TableHead>
                  <TableHead>Dias</TableHead>
                  <TableHead>Vigência</TableHead>
                  <TableHead>Canal</TableHead>
                  <TableHead>Alertas</TableHead>
                  <TableHead>Situação</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map(j => {
                  const ligados = ALERTAS.filter(a => j[a.campo]).length
                  return (
                    <TableRow key={j.id} className={j.ativo ? '' : 'opacity-60'}>
                      <TableCell>
                        <span className="font-mono text-[11px] text-ink break-all">{j.project}.{j.job_name}</span>
                        {j.descricao && <p className="text-[11px] text-dim">{j.descricao}</p>}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs">
                        {hhmm(j.janela_inicio)}–{hhmm(j.janela_fim)}
                        {j.tolerancia_min > 0 && <span className="text-dim"> +{j.tolerancia_min}min</span>}
                      </TableCell>
                      <TableCell className="text-xs">{rotuloDias(j.dias_semana)}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">{j.vigencia_inicio}</TableCell>
                      <TableCell className="text-xs">
                        {j.grupo_nome ?? <span className="text-dim">sem canal</span>}
                      </TableCell>
                      <TableCell className="text-xs">{ligados} de {ALERTAS.length}</TableCell>
                      <TableCell>
                        <Badge value={j.ativo ? 'ativo' : 'inativo'}>
                          {j.ativo ? 'supervisionado' : 'desativado'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <Button size="sm" variant="secondary" onClick={() => abrirEdicao(j)}
                          aria-label={`Editar a supervisão de ${j.project}.${j.job_name}`}
                          title={`Editar a supervisão de ${j.job_name}`}>
                          <Pencil size={14} />
                        </Button>
                        <Button size="sm" variant="secondary" className="ml-1" onClick={() => setRemovendo(j)}
                          aria-label={`Remover ${j.project}.${j.job_name} da supervisão`}
                          title={`Remover ${j.job_name} da supervisão`}>
                          <Trash2 size={14} />
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Formulário — criar ou editar */}
      <Modal open={formAberto} onClose={fecharForm} size="lg"
        title={editando ? `Supervisão de ${editando.project}.${editando.job_name}` : 'Supervisionar job'}>
        <div className="flex flex-col gap-3">
          {!editando && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input label="Projeto" value={form.project} autoFocus
                onChange={e => setForm(f => ({ ...f, project: e.target.value }))}
                hint="Letras, números, '_' e '.'" />
              <Input label="Job (sequence)" value={form.job_name}
                onChange={e => setForm(f => ({ ...f, job_name: e.target.value }))}
                hint="Mesmo nome usado no console" />
            </div>
          )}

          <Input label="Descrição (opcional)" value={form.descricao}
            onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} />

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Input label="Deve iniciar a partir de" type="time" value={form.janela_inicio}
              onChange={e => setForm(f => ({ ...f, janela_inicio: e.target.value }))} />
            <Input label="Até" type="time" value={form.janela_fim}
              onChange={e => setForm(f => ({ ...f, janela_fim: e.target.value }))} />
            <Input label="Tolerância (min)" type="number" min={0} max={1440}
              value={form.tolerancia_min}
              onChange={e => setForm(f => ({ ...f, tolerancia_min: e.target.value }))}
              hint="Espera após o fim da janela" />
          </div>

          <div>
            <p className="text-xs font-medium text-ink mb-1.5">Dias em que o job deve rodar</p>
            <div className="flex flex-wrap gap-3">
              {DIAS.map(d => (
                <Checkbox key={d.v} label={d.label} checked={form.dias.includes(d.v)}
                  onChange={() => alternarDia(d.v)} />
              ))}
            </div>
            <p className="text-[11px] text-dim mt-1">
              Fora desses dias nada é avaliado — nem atraso, nem “não executou”.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Monitorar a partir de" type="date" value={form.vigencia_inicio}
              onChange={e => setForm(f => ({ ...f, vigencia_inicio: e.target.value }))}
              hint="Nada antes desta data é avaliado" />
            <Input label="Linhas do log a ler" type="number" min={1} max={2000}
              value={form.max_linhas}
              onChange={e => setForm(f => ({ ...f, max_linhas: e.target.value }))}
              hint="'-max' do logsum (1 a 2000). Job verboso pede mais." />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Select label="Canal do Teams" value={form.grupo_id}
              onChange={e => setForm(f => ({ ...f, grupo_id: e.target.value }))}
              hint="Comece pelo canal de homologação">
              <option value="">Sem canal (só no painel)</option>
              {gruposAtivos.map(g => (
                <option key={g.id} value={g.id}>
                  {g.nome}{g.has_webhook ? '' : ' (sem webhook)'}
                </option>
              ))}
            </Select>
            <Select label="Template da mensagem" value={form.template_id}
              onChange={e => setForm(f => ({ ...f, template_id: e.target.value }))}
              hint="Vazio usa o card padrão do alerta">
              <option value="">Card padrão</option>
              {templatesAtivos.map(t => <option key={t.id} value={t.id}>{t.nome}</option>)}
            </Select>
          </div>

          <div>
            <p className="text-xs font-medium text-ink mb-1.5">Quando avisar</p>
            <div className="flex flex-col gap-2">
              {ALERTAS.map(a => (
                <Switch key={a.campo} label={a.label} hint={a.hint} checked={form[a.campo]}
                  onChange={e => setForm(f => ({ ...f, [a.campo]: e.target.checked }))} />
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="secondary" onClick={fecharForm}>Cancelar</Button>
            <Button onClick={submeter} loading={salvar.isPending}>
              {editando ? 'Salvar' : 'Supervisionar'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Confirmação de remoção */}
      <Modal open={!!removendo} onClose={() => setRemovendo(null)} size="sm" title="Remover da supervisão">
        <p className="text-sm text-ink">
          Parar de supervisionar <strong>{removendo?.project}.{removendo?.job_name}</strong>?
        </p>
        <p className="text-xs text-dim mt-2">
          O histórico já coletado é preservado e continua visível ao navegar para dias
          anteriores no dashboard. Para voltar a supervisionar, é só cadastrar o job de novo.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="secondary" onClick={() => setRemovendo(null)}>Cancelar</Button>
          <Button variant="danger" loading={remover.isPending}
            onClick={() => removendo && remover.mutate(removendo.id)}>
            Remover
          </Button>
        </div>
      </Modal>
    </div>
  )
}
