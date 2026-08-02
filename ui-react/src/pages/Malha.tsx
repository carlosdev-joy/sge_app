import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { PageSpinner } from '../components/ui/Spinner'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Input, Textarea } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { toast } from '../components/ui/Toast'
import { CritBadge } from '../components/malhas/CritBadge'
import { MalhaEditor } from '../components/malhas/MalhaEditor'
import {
  RefreshCw, Network, X,
  Plus, Edit, Users, Power, Trash2, AlertTriangle, Boxes,
} from 'lucide-react'

// O inventário de pipelines (Cards/Diagrama + CSV) MIGROU para
// components/malhas/CatalogoPipelines.tsx e vive em Catálogo & Lineage
// (/governanca) desde a F9 — decisão do usuário na spec §8: esta tela exibe
// SÓ malhas. O DependencyGraph SVG legado morreu na realocação (spec §4b).

// ─── Malhas (F7) — agrupadoras de pipelines ──────────────────────────────────
// Malha = agrupador nomeado de pipelines (análogo da sequence mestre do
// DataStage / SMART Folder do Control-M). Nesta fase existe a entidade, os
// membros e a lista; o diagrama de montagem (MalhaEditor) chega na F8.

interface ApiMalha {
  malha_name: string
  descricao: string | null
  ativo: 0 | 1 | boolean
  criado_em: string | null
  qtd_pipelines: number
  qtd_ativos: number
  criticidade: string | null // agregada = a mais alta entre os membros
}

interface MalhasResponse {
  malhas: ApiMalha[]
  // Deploy parcial (API nova + migration 070 não aplicada): a API degrada
  // devolvendo lista vazia + esta flag, em vez de 500.
  migration_pendente?: boolean
}

interface MalhaMembro {
  pipeline_name: string
  active: 0 | 1 | boolean
  criticidade: string | null
  schedule_type: string | null
  layout_x: number | null
  layout_y: number | null
}

interface MalhaDetalheResponse {
  malha: ApiMalha
  membros: MalhaMembro[]
}

function formataData(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('pt-BR')
}

// ─── Card de malha (mesma linguagem do PipelineCard) ─────────────────────────

function MalhaCard({ malha, onAbrir, onMembros, onRenomear, onToggle }: {
  malha: ApiMalha
  onAbrir: () => void
  onMembros: () => void
  onRenomear: () => void
  onToggle: () => void
}) {
  const ativa = !!malha.ativo
  const criado = formataData(malha.criado_em)
  return (
    <div className="bg-panel border border-edge rounded-lg px-4 py-3 flex flex-col gap-2 hover:shadow-md hover:border-[#1A5FA8]/40 transition-all">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`w-2 h-2 rounded-full shrink-0 ${ativa ? 'bg-green-400' : 'bg-slate-400'}`} />
        <span className="font-mono text-sm font-semibold text-ink flex-1 min-w-0 truncate">{malha.malha_name}</span>
        {malha.criticidade && <CritBadge crit={malha.criticidade} />}
        {ativa ? (
          <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">● Ativa</span>
        ) : (
          <span className="text-[10px] text-dim">○ Inativa</span>
        )}
      </div>
      {malha.descricao && (
        <p className="text-[11px] text-dim line-clamp-2">{malha.descricao}</p>
      )}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-dim">
        <span>⚙ {malha.qtd_pipelines} pipeline{malha.qtd_pipelines !== 1 ? 's' : ''} ({malha.qtd_ativos} ativo{malha.qtd_ativos !== 1 ? 's' : ''})</span>
        {criado && <span>📅 criada em {criado}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-edge mt-auto">
        <Button size="sm" onClick={onAbrir} title="Abrir o diagrama de montagem — desenhar uma aresta cadastra a dependência real">
          <Network size={12} /> Abrir diagrama
        </Button>
        <Button variant="secondary" size="sm" onClick={onMembros} title="Ver e editar os pipelines desta malha">
          <Users size={12} /> Membros
        </Button>
        <Button variant="ghost" size="sm" onClick={onRenomear} title="Renomear a malha e editar a descrição">
          <Edit size={12} /> Renomear
        </Button>
        <Button variant="ghost" size="sm" onClick={onToggle} title={ativa ? 'Inativar a malha' : 'Reativar a malha'}>
          <Power size={12} /> {ativa ? 'Inativar' : 'Reativar'}
        </Button>
      </div>
    </div>
  )
}

// ─── Modal: nova malha ───────────────────────────────────────────────────────

function NovaMalhaModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')

  const criarMut = useMutation({
    mutationFn: () => apiFetch('/malhas', {
      method: 'POST',
      body: JSON.stringify({
        malha_name: nome.trim(),
        ...(descricao.trim() ? { descricao: descricao.trim() } : {}),
      }),
    }),
    onSuccess: () => {
      toast.success(`Malha "${nome.trim()}" criada.`)
      qc.invalidateQueries({ queryKey: ['malhas'] })
      setNome(''); setDescricao('')
      onClose()
    },
    // 422 da API (nome duplicado/inválido) chega como `detail` string em pt-BR.
    onError: (e: Error) => toast.error(e.message || 'Erro ao criar a malha'),
  })

  return (
    <Modal open={open} onClose={onClose} title="Nova malha">
      <div className="flex flex-col gap-3">
        <Input
          label="Nome"
          value={nome}
          onChange={e => setNome(e.target.value)}
          placeholder="ex: malha_fechamento_diario"
          ajuda="Identificador único da malha — os pipelines membros são adicionados depois, em Membros."
          autoFocus
        />
        <Textarea
          label="Descrição"
          value={descricao}
          onChange={e => setDescricao(e.target.value)}
          placeholder="opcional — o que esta malha orquestra"
          rows={3}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={() => criarMut.mutate()}
            loading={criarMut.isPending}
            disabled={!nome.trim()}
          >
            <Plus size={14} /> Criar malha
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Modal: renomear/editar malha ────────────────────────────────────────────

function RenomearMalhaModal({ malha, onClose }: { malha: ApiMalha; onClose: () => void }) {
  const qc = useQueryClient()
  const [nome, setNome] = useState(malha.malha_name)
  const [descricao, setDescricao] = useState(malha.descricao ?? '')

  const salvarMut = useMutation({
    mutationFn: (body: { novo_nome?: string; descricao?: string }) =>
      apiFetch(`/malhas/${encodeURIComponent(malha.malha_name)}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success('Malha atualizada.')
      qc.invalidateQueries({ queryKey: ['malhas'] })
      onClose()
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao atualizar a malha'),
  })

  function salvar() {
    const body: { novo_nome?: string; descricao?: string } = {}
    const nomeTrim = nome.trim()
    if (nomeTrim && nomeTrim !== malha.malha_name) body.novo_nome = nomeTrim
    if (descricao.trim() !== (malha.descricao ?? '')) body.descricao = descricao.trim()
    if (Object.keys(body).length === 0) { onClose(); return } // nada mudou: no-op
    salvarMut.mutate(body)
  }

  return (
    <Modal open onClose={onClose} title="Renomear malha">
      <div className="flex flex-col gap-3">
        <Input
          label="Nome"
          value={nome}
          onChange={e => setNome(e.target.value)}
          autoFocus
        />
        <Textarea
          label="Descrição"
          value={descricao}
          onChange={e => setDescricao(e.target.value)}
          placeholder="opcional — o que esta malha orquestra"
          rows={3}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={salvar} loading={salvarMut.isPending} disabled={!nome.trim()}>
            Salvar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Modal: membros da malha ─────────────────────────────────────────────────

function MembrosModal({ malhaName, onClose }: { malhaName: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [busca, setBusca] = useState('')

  const { data, isLoading, isError, error } = useQuery<MalhaDetalheResponse>({
    queryKey: ['malha', malhaName],
    queryFn: () => apiFetch(`/malhas/${encodeURIComponent(malhaName)}`),
  })
  const membros = data?.membros ?? []

  function invalidar() {
    qc.invalidateQueries({ queryKey: ['malha', malhaName] })
    qc.invalidateQueries({ queryKey: ['malhas'] }) // contagens/criticidade dos cards
  }

  const addMut = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch(`/malhas/${encodeURIComponent(malhaName)}/pipelines`, {
        method: 'POST',
        body: JSON.stringify({ pipeline_name }),
      }),
    onSuccess: (_r, pipeline_name) => {
      toast.success(`Pipeline "${pipeline_name}" adicionado à malha.`)
      setBusca('')
      invalidar()
    },
    // 422 da API: pipeline inexistente / já membro — detail em pt-BR.
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o pipeline'),
  })

  const removerMut = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch(`/malhas/${encodeURIComponent(malhaName)}/pipelines/${encodeURIComponent(pipeline_name)}`, {
        method: 'DELETE',
      }),
    onSuccess: (_r, pipeline_name) => {
      toast.success(`Pipeline "${pipeline_name}" removido da malha.`)
      invalidar()
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao remover o pipeline'),
  })

  function remover(pipeline_name: string) {
    if (!confirm(`Remover "${pipeline_name}" da malha "${malhaName}"?\n\nO pipeline continua existindo — sai apenas desta malha.`)) return
    removerMut.mutate(pipeline_name)
  }

  return (
    <Modal open onClose={onClose} title={`Membros — ${malhaName}`} size="lg">
      <div className="flex flex-col gap-4">

        {/* Adicionar por busca (mesmo padrão de autocomplete da tela de Etapas) */}
        <div className="flex items-end gap-2">
          <Autocomplete
            label="Adicionar pipeline"
            value={busca}
            onChange={setBusca}
            onSelect={setBusca}
            fetchSuggestions={q =>
              apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
                .then(r => r.data.map(p => p.pipeline_name))
            }
            placeholder="busque por nome..."
            className="flex-1"
          />
          <Button
            onClick={() => addMut.mutate(busca.trim())}
            loading={addMut.isPending}
            disabled={!busca.trim()}
          >
            <Plus size={14} /> Adicionar
          </Button>
        </div>

        {/* Lista de membros */}
        {isLoading ? (
          <PageSpinner />
        ) : isError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            Erro ao carregar os membros: {(error as Error)?.message ?? 'Erro desconhecido'}
          </div>
        ) : membros.length === 0 ? (
          <p className="text-sm text-dim text-center py-6">
            Nenhum pipeline nesta malha ainda — adicione pelo campo acima.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {membros.map(m => (
              <div key={m.pipeline_name} className="flex items-center gap-2 px-3 py-2 bg-canvas border border-edge rounded-md">
                <span className={`w-2 h-2 rounded-full shrink-0 ${m.active ? 'bg-green-400' : 'bg-slate-400'}`} />
                <span className="font-mono text-xs text-ink flex-1 min-w-0 truncate">{m.pipeline_name}</span>
                {m.criticidade && <CritBadge crit={m.criticidade} />}
                {m.schedule_type && (
                  <span className="text-[10px] text-dim">
                    {m.schedule_type === 'on_demand' ? 'sob demanda' : m.schedule_type}
                  </span>
                )}
                <button
                  onClick={() => remover(m.pipeline_name)}
                  title="Remover da malha"
                  className="text-dim hover:text-red-400 transition-colors shrink-0"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="text-[11px] text-dim border-t border-edge pt-3">
          Aqui você define apenas <strong className="text-ink">quem participa</strong> da malha —
          o diagrama de montagem (nós, dependências e layout) chega na F8.
        </p>
      </div>
    </Modal>
  )
}

// ─── Visão Malhas (lista) ────────────────────────────────────────────────────

function MalhasView({ onAbrir }: { onAbrir: (malha: string) => void }) {
  const [showCriar, setShowCriar] = useState(false)
  const [renomear, setRenomear] = useState<ApiMalha | null>(null)
  const [membrosDe, setMembrosDe] = useState<string | null>(null)

  const qc = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useQuery<MalhasResponse>({
    queryKey: ['malhas'],
    queryFn: () => apiFetch('/malhas'),
  })
  const malhas = data?.malhas ?? []
  const migrationPendente = data?.migration_pendente === true

  const toggleMut = useMutation({
    mutationFn: (m: ApiMalha) =>
      apiFetch(`/malhas/${encodeURIComponent(m.malha_name)}`, {
        method: 'PATCH',
        body: JSON.stringify({ ativo: !m.ativo }),
      }),
    onSuccess: (_r, m) => {
      toast.success(m.ativo ? `Malha "${m.malha_name}" inativada.` : `Malha "${m.malha_name}" reativada.`)
      qc.invalidateQueries({ queryKey: ['malhas'] })
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao alterar a malha'),
  })

  function alternar(m: ApiMalha) {
    const acao = m.ativo ? 'Inativar' : 'Reativar'
    if (!confirm(`${acao} a malha "${m.malha_name}"?`)) return
    toggleMut.mutate(m)
  }

  const ativas = malhas.filter(m => m.ativo).length
  const totalPipelines = malhas.reduce((s, m) => s + m.qtd_pipelines, 0)

  return (
    <div className="flex flex-col gap-4">

      {/* Aviso discreto de deploy parcial: API nova sem a migration 070. */}
      {migrationPendente && (
        <div className="flex items-center gap-2 text-[12px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          <AlertTriangle size={14} className="shrink-0" />
          <span>migration 070 pendente — as tabelas de malha ainda não existem neste ambiente; peça o deploy para criar malhas.</span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex gap-1 ml-auto">
          <Button
            onClick={() => setShowCriar(true)}
            disabled={migrationPendente}
            title={migrationPendente ? 'Indisponível até a migration 070 ser aplicada' : 'Criar uma nova malha'}
          >
            <Plus size={14} /> Nova malha
          </Button>
          <button
            onClick={() => refetch()}
            title="Atualizar dados"
            className="inline-flex items-center px-2.5 py-1.5 rounded-md text-sm border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40 transition-colors"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Stats bar (mesma linguagem das stats-pills do catálogo) */}
      {!isLoading && !isError && malhas.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: `${malhas.length}`, sub: `malha${malhas.length !== 1 ? 's' : ''}` },
            { label: `${ativas}`, sub: `ativa${ativas !== 1 ? 's' : ''}` },
            { label: `${totalPipelines}`, sub: `pipeline${totalPipelines !== 1 ? 's' : ''} agrupados` },
          ].map(s => (
            <div key={s.sub} className="bg-panel border border-edge rounded px-3 py-1.5 flex items-center gap-1.5">
              <strong className="text-ink font-bold text-sm">{s.label}</strong>
              <span className="text-dim text-xs">{s.sub}</span>
            </div>
          ))}
        </div>
      )}

      {/* Conteúdo */}
      {isLoading ? (
        <PageSpinner />
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          Erro ao carregar malhas: {(error as Error)?.message ?? 'Erro desconhecido'}
        </div>
      ) : malhas.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Boxes size={40} className="text-dim mb-3" />
          <p className="font-semibold text-ink">Nenhuma malha cadastrada</p>
          <p className="text-sm text-dim mt-1 max-w-md">
            Uma malha agrupa pipelines — o análogo da sequence mestre do DataStage.
            O diagrama de montagem chega na F8.
          </p>
          {!migrationPendente && (
            <Button className="mt-4" onClick={() => setShowCriar(true)}>
              <Plus size={14} /> Criar a primeira malha
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
          {malhas.map(m => (
            <MalhaCard
              key={m.malha_name}
              malha={m}
              onAbrir={() => onAbrir(m.malha_name)}
              onMembros={() => setMembrosDe(m.malha_name)}
              onRenomear={() => setRenomear(m)}
              onToggle={() => alternar(m)}
            />
          ))}
        </div>
      )}

      <NovaMalhaModal open={showCriar} onClose={() => setShowCriar(false)} />
      {renomear && (
        <RenomearMalhaModal
          key={renomear.malha_name}
          malha={renomear}
          onClose={() => setRenomear(null)}
        />
      )}
      {membrosDe && (
        <MembrosModal malhaName={membrosDe} onClose={() => setMembrosDe(null)} />
      )}
    </div>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────
// Desde a F9 a tela exibe SÓ malhas (decisão do usuário na spec §8) — o
// inventário de pipelines vive em Catálogo & Lineage (/governanca). Com
// `?malha=` na URL a página vira o diagrama de montagem em tela cheia (F8) —
// mesmo padrão de deep-link da tela Fluxos (?pipeline=).

export default function Malha() {
  const [searchParams, setSearchParams] = useSearchParams()
  const malhaAberta = (searchParams.get('malha') ?? '').trim()
  const [membrosAberto, setMembrosAberto] = useState(false)
  // Aviso da mudança de endereço do catálogo (F9) — dispensável, mesmo padrão
  // de banner com X que o catálogo desta tela usava.
  const [avisoCatalogo, setAvisoCatalogo] = useState(true)
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  // ── Diagrama de montagem em tela cheia (F8) ────────────────────────────────
  if (malhaAberta) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <Boxes size={20} className="text-[#1A5FA8]" /> Malha
            <span className="font-mono text-base text-dim">· {malhaAberta}</span>
          </h1>
          <div className="ml-auto flex items-center gap-2">
            {!isViewer && (
              <Button
                variant="secondary" size="sm"
                onClick={() => setMembrosAberto(true)}
                title="Ver e remover os pipelines membros desta malha"
              >
                <Users size={13} /> Membros
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => setSearchParams({})} title="Voltar à lista de malhas">
              <X size={13} /> Voltar
            </Button>
          </div>
        </div>
        <div className="h-[calc(100vh-11rem)]">
          <MalhaEditor malha={malhaAberta} readOnly={isViewer} />
        </div>
        {membrosAberto && (
          <MembrosModal malhaName={malhaAberta} onClose={() => setMembrosAberto(false)} />
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">

      <div>
        <h1 className="text-xl font-bold text-ink">Malha de Pipelines</h1>
        <p className="text-sm text-dim mt-0.5">
          Agrupe pipelines em malhas — a lente de montagem da orquestração
        </p>
      </div>

      {avisoCatalogo && (
        <div className="flex items-center gap-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2 text-[12px] text-blue-800 dark:text-blue-200">
          <span>
            O catálogo de pipelines agora vive em{' '}
            <Link to="/governanca" className="font-semibold underline underline-offset-2">
              Catálogo &amp; Lineage
            </Link>.
          </span>
          <button
            onClick={() => setAvisoCatalogo(false)}
            className="ml-auto shrink-0 text-blue-400 hover:text-blue-700 dark:hover:text-blue-100 transition-colors"
            aria-label="Dispensar"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <MalhasView onAbrir={n => setSearchParams({ malha: n })} />
    </div>
  )
}
