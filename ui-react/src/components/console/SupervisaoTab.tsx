import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { Badge } from '../ui/Badge'
import { Modal } from '../ui/Modal'
import { Switch } from '../ui/Switch'
import { Checkbox } from '../ui/Checkbox'
import { toast } from '../ui/Toast'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Plus, Pencil, Trash2, ShieldCheck } from 'lucide-react'

// ── Cadastro dos jobs supervisionados (aba do Console DataStage) ────────────
// A coleta (DAG), o painel do dashboard e o card do Teams são as outras fases
// da spec docs/spec-supervisao-ds.md — aqui é só o cadastro.
//
// A ajuda dos campos usa a prop `ajuda` (texto visível abaixo do campo), NÃO o
// `hint`: o hint é um popover absolute que o `overflow-y-auto` do Modal corta.

export interface SupervisaoJob {
  id: number
  project: string
  job_name: string
  descricao: string
  janela_inicio: string      // HH:MM:SS
  janela_fim: string         // HH:MM:SS
  tolerancia_min: number
  dias_semana: string        // CSV ISO: 1=seg … 7=dom
  vigencia_inicio: string    // AAAA-MM-DD
  max_linhas: number
  grupo_id: number | null
  alerta_abortou: boolean
  alerta_nao_executou: boolean
  alerta_atraso: boolean
  alerta_estrutura: boolean
  ativo: boolean
  created_by: string | null
  created_at: string
  updated_at: string
  grupo_nome: string | null
  mensagens: Record<string, string>
}

interface MsgGrupo { id: number; nome: string; ativo: boolean; has_webhook: boolean }
interface Variavel { nome: string; descricao: string; exemplo: string }

const DIAS = [
  { v: '1', label: 'Seg' }, { v: '2', label: 'Ter' }, { v: '3', label: 'Qua' },
  { v: '4', label: 'Qui' }, { v: '5', label: 'Sex' }, { v: '6', label: 'Sáb' },
  { v: '7', label: 'Dom' },
]

// Cada tipo de alerta tem seu próprio card de mensagem: um job liga até quatro
// alertas diferentes e uma frase única não explica os quatro casos.
const ALERTAS = [
  {
    tipo: 'ABORTOU', campo: 'alerta_abortou', label: 'Job abortou',
    ajuda: 'Existe execução na janela, mas ela terminou abortada.',
    exemplo: '🚨 {job} ({projeto}) abortou em {data}. Início {inicio}, parada {fim}.',
  },
  {
    tipo: 'NAO_EXECUTOU', campo: 'alerta_nao_executou', label: 'Não executou',
    ajuda: 'O dia fechou sem nenhuma execução do job.',
    exemplo: '🚨 {job} não executou em {data}. Janela esperada: {janela_inicio}–{janela_fim}.',
  },
  {
    tipo: 'ATRASO', campo: 'alerta_atraso', label: 'Iniciou com atraso',
    ajuda: 'Passou o fim da janela mais a tolerância e o job ainda não tinha iniciado.',
    exemplo: '⏰ {job} não iniciou até {limite}. Janela {janela_inicio}–{janela_fim}, tolerância de {tolerancia} min.',
  },
  {
    tipo: 'ESTRUTURA', campo: 'alerta_estrutura', label: 'Falha de estrutura',
    ajuda: 'Não foi possível nem ler o job: projeto ou job inexistente, renomeado, ou servidor fora.',
    exemplo: '⚠️ Não foi possível verificar {job} ({projeto}) em {data}. {situacao}',
  },
] as const

const TIPO_INICIAL = 'SITUACAO_INICIAL'

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
  alerta_abortou: boolean
  alerta_nao_executou: boolean
  alerta_atraso: boolean
  alerta_estrutura: boolean
  mensagens: Record<string, string>
}

function formVazio(project: string, job: string): FormState {
  return {
    project, job_name: job, descricao: '',
    janela_inicio: '02:00', janela_fim: '03:00', tolerancia_min: '0',
    dias: ['1', '2', '3', '4', '5'], vigencia_inicio: hoje(), max_linhas: '200',
    grupo_id: '',
    alerta_abortou: true, alerta_nao_executou: true, alerta_atraso: true, alerta_estrutura: true,
    mensagens: {},
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
    alerta_abortou: j.alerta_abortou, alerta_nao_executou: j.alerta_nao_executou,
    alerta_atraso: j.alerta_atraso, alerta_estrutura: j.alerta_estrutura,
    mensagens: { ...(j.mensagens ?? {}) },
  }
}

export function SupervisaoTab({ project, job, projetos }: {
  project: string
  job: string
  projetos: string[]
}) {
  const queryClient = useQueryClient()
  const [editando, setEditando] = useState<SupervisaoJob | null>(null)
  const [criando, setCriando] = useState(false)
  const [removendo, setRemovendo] = useState<SupervisaoJob | null>(null)
  const [form, setForm] = useState<FormState>(() => formVazio('', ''))
  const areas = useRef<Record<string, HTMLTextAreaElement | null>>({})

  const lista = useQuery<{ data: SupervisaoJob[] }>({
    queryKey: ['ds-supervisao'],
    queryFn: () => apiFetch('/admin/ds/supervisao'),
  })
  const grupos = useQuery<{ data: MsgGrupo[] }>({
    queryKey: ['msg-grupos'],
    queryFn: () => apiFetch('/msg/grupos'),
  })
  const vars = useQuery<{ tipos: string[]; variaveis: Variavel[] }>({
    queryKey: ['ds-supervisao-variaveis'],
    queryFn: () => apiFetch('/admin/ds/supervisao/variaveis'),
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

  const setMensagem = (tipo: string, texto: string) =>
    setForm(f => ({ ...f, mensagens: { ...f.mensagens, [tipo]: texto } }))

  /** Insere {variavel} na posição do cursor da mensagem daquele tipo. */
  const inserirVariavel = (tipo: string, nome: string) => {
    const area = areas.current[tipo]
    const atual = form.mensagens[tipo] ?? ''
    const token = `{${nome}}`
    if (!area) { setMensagem(tipo, atual + token); return }
    const ini = area.selectionStart ?? atual.length
    const fim = area.selectionEnd ?? atual.length
    const novo = atual.slice(0, ini) + token + atual.slice(fim)
    setMensagem(tipo, novo)
    // Devolve o foco com o cursor depois do token inserido.
    requestAnimationFrame(() => {
      area.focus()
      area.setSelectionRange(ini + token.length, ini + token.length)
    })
  }

  const submeter = () => {
    if (!form.dias.length) { toast.error('Selecione ao menos um dia da semana.'); return }
    if (!form.descricao.trim()) { toast.error('Informe a descrição do job.'); return }
    const payload: Record<string, unknown> = {
      descricao: form.descricao,
      janela_inicio: form.janela_inicio,
      janela_fim: form.janela_fim,
      tolerancia_min: form.tolerancia_min,
      dias_semana: form.dias.join(','),
      vigencia_inicio: form.vigencia_inicio,
      max_linhas: form.max_linhas,
      grupo_id: form.grupo_id === '' ? null : form.grupo_id,
      alerta_abortou: form.alerta_abortou,
      alerta_nao_executou: form.alerta_nao_executou,
      alerta_atraso: form.alerta_atraso,
      alerta_estrutura: form.alerta_estrutura,
      mensagens: form.mensagens,
    }
    // project/job_name são imutáveis na edição: o histórico é ligado a eles.
    if (!editando) { payload.project = form.project; payload.job_name = form.job_name }
    salvar.mutate(payload)
  }

  const jobs = lista.data?.data ?? []
  const gruposAtivos = (grupos.data?.data ?? []).filter(g => g.ativo)
  const variaveis = vars.data?.variaveis ?? []
  const formAberto = criando || !!editando

  // Bloco de mensagem reusado pelos cards de alerta e pelo de situação inicial.
  const cardMensagem = (tipo: string, exemplo: string) => (
    <>
      <Textarea
        ref={el => { areas.current[tipo] = el }}
        rows={3}
        value={form.mensagens[tipo] ?? ''}
        onChange={e => setMensagem(tipo, e.target.value)}
        placeholder={exemplo}
        ajuda="Deixe em branco para usar o texto padrão do sistema."
      />
      {variaveis.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {variaveis.map(v => (
            <button
              key={v.nome}
              type="button"
              onClick={() => inserirVariavel(tipo, v.nome)}
              title={`${v.descricao} — ex.: ${v.exemplo}`}
              className="px-1.5 py-0.5 rounded border border-edge bg-canvas text-[10px] font-mono text-dim hover:text-ink hover:border-blue-500 transition-colors"
            >
              {'{' + v.nome + '}'}
            </button>
          ))}
        </div>
      )}
    </>
  )

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
      <Modal open={formAberto} onClose={fecharForm} size="xl"
        title={editando ? `Supervisão de ${editando.project}.${editando.job_name}` : 'Supervisionar job'}>
        <div className="flex flex-col gap-4">

          <section className="flex flex-col gap-3">
            {!editando && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Lista fechada: digitar o projeto errado só apareceria como
                    falha de estrutura depois do primeiro ciclo da coleta. */}
                <Select label="Projeto" value={form.project}
                  onChange={e => setForm(f => ({ ...f, project: e.target.value }))}
                  ajuda="Projetos cadastrados no Orquestra.">
                  <option value="">Selecione…</option>
                  {projetos.map(p => <option key={p} value={p}>{p}</option>)}
                </Select>
                <Input label="Job (sequence)" value={form.job_name}
                  onChange={e => setForm(f => ({ ...f, job_name: e.target.value }))}
                  ajuda="Exatamente como no console: letras, números, '_' e '.'" />
              </div>
            )}

            <Input label="Descrição" value={form.descricao} required
              onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))}
              ajuda="Obrigatória. Identifica o job no painel e nos alertas — ex.: “Carga diária de vida”." />
          </section>

          <section className="flex flex-col gap-3 border-t border-edge pt-3">
            <h3 className="text-xs font-semibold text-ink">Quando o job deve rodar</h3>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Input label="Deve iniciar a partir de" type="time" value={form.janela_inicio}
                onChange={e => setForm(f => ({ ...f, janela_inicio: e.target.value }))}
                ajuda="Começo da janela esperada." />
              <Input label="Até" type="time" value={form.janela_fim}
                onChange={e => setForm(f => ({ ...f, janela_fim: e.target.value }))}
                ajuda="Fim da janela. Se for menor que o início, a janela atravessa a meia-noite." />
              <Input label="Tolerância (min)" type="number" min={0} max={1440}
                value={form.tolerancia_min}
                onChange={e => setForm(f => ({ ...f, tolerancia_min: e.target.value }))}
                ajuda="Espera adicional após o fim da janela antes de acusar atraso." />
            </div>

            <div>
              <p className="text-xs text-dim font-medium mb-1.5">Dias em que o job deve rodar</p>
              <div className="flex flex-wrap gap-3">
                {DIAS.map(d => (
                  <Checkbox key={d.v} label={d.label} checked={form.dias.includes(d.v)}
                    onChange={() => alternarDia(d.v)} />
                ))}
              </div>
              <p className="text-[11px] leading-snug text-dim mt-1">
                Fora desses dias nada é avaliado — nem atraso, nem “não executou”.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input label="Monitorar a partir de" type="date" value={form.vigencia_inicio}
                onChange={e => setForm(f => ({ ...f, vigencia_inicio: e.target.value }))}
                ajuda="Nada anterior a esta data é avaliado. No primeiro ciclo você recebe a situação do dia para validar a configuração." />
              <Input label="Linhas do log a ler" type="number" min={1} max={2000}
                value={form.max_linhas}
                onChange={e => setForm(f => ({ ...f, max_linhas: e.target.value }))}
                ajuda="Parâmetro -max do logsum (1 a 2000). Job com log verboso precisa de mais linhas para cobrir o dia." />
            </div>
          </section>

          <section className="flex flex-col gap-3 border-t border-edge pt-3">
            <h3 className="text-xs font-semibold text-ink">Para onde avisar</h3>
            <Select label="Canal do Teams" value={form.grupo_id}
              onChange={e => setForm(f => ({ ...f, grupo_id: e.target.value }))}
              ajuda="Comece pelo canal de homologação; depois troque para o oficial. Sem canal, o alerta aparece só no painel.">
              <option value="">Sem canal (só no painel)</option>
              {gruposAtivos.map(g => (
                <option key={g.id} value={g.id}>
                  {g.nome}{g.has_webhook ? '' : ' (sem webhook)'}
                </option>
              ))}
            </Select>
          </section>

          <section className="flex flex-col gap-3 border-t border-edge pt-3">
            <h3 className="text-xs font-semibold text-ink">Alertas e mensagens</h3>
            <p className="text-[11px] leading-snug text-dim -mt-1">
              Cada situação tem sua própria mensagem. Clique numa variável para inseri-la no
              texto — ela é trocada pelo valor real quando o alerta é enviado.
            </p>

            {ALERTAS.map(a => (
              <div key={a.tipo} className="border border-edge rounded-lg p-3 flex flex-col gap-2">
                <Switch label={a.label} checked={form[a.campo]}
                  onChange={e => setForm(f => ({ ...f, [a.campo]: e.target.checked }))} />
                <p className="text-[11px] leading-snug text-dim">{a.ajuda}</p>
                {form[a.campo] && cardMensagem(a.tipo, a.exemplo)}
              </div>
            ))}

            <div className="border border-edge rounded-lg p-3 flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-ink">Início do monitoramento</span>
                <Badge value="info">sempre enviado</Badge>
              </div>
              <p className="text-[11px] leading-snug text-dim">
                Enviado uma vez, quando a vigência começa, com a situação do dia — mesmo
                quando está tudo certo. É o aviso que confirma se a configuração ficou correta.
              </p>
              {cardMensagem(TIPO_INICIAL,
                '✅ Monitoramento iniciado para {job} ({projeto}). Janela {janela_inicio}–{janela_fim}. {situacao}')}
            </div>
          </section>

          <div className="flex justify-end gap-2 pt-1 border-t border-edge">
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
