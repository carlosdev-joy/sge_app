// Admin › Acessos & Comunicação › Maestro — o container (F3 da spec
// docs/spec-maestro-parametros.md): interruptor, catálogo de cenários e os
// pedidos que o Maestro não atendeu. react-query + mutations em cima de
// /maestro/admin/*; sem a migration 110 a API responde 503 nomeando-a e a
// aba diz isso em vez de "falha ao carregar".
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { InfoBanner } from '../ui/InfoBanner'
import { PageSpinner } from '../ui/Spinner'
import { Switch } from '../ui/Switch'
import { toast } from '../ui/Toast'
import { MaestroAvatar } from '../etapas/MaestroAvatar'
import {
  mensagemErroAdmin, migration110Pendente,
  type CenarioApi, type ConfigMaestroApi, type PedidoApi, type cenarioParaApi,
} from '../../lib/maestroAdmin'
import { MaestroCenarioModal } from './MaestroCenarioModal'

const Q_CONFIG = ['maestro-admin-config'] as const
const Q_CENARIOS = ['maestro-admin-cenarios'] as const
const Q_PEDIDOS = 'maestro-admin-pedidos'

export function MaestroTab() {
  const qc = useQueryClient()
  const [tratados, setTratados] = useState(false)
  const [editando, setEditando] = useState<CenarioApi | 'novo' | null>(null)
  const [chaveModal, setChaveModal] = useState(0)
  const [confirmandoExclusao, setConfirmandoExclusao] = useState<number | null>(null)

  const config = useQuery<ConfigMaestroApi>({ queryKey: Q_CONFIG, queryFn: () => apiFetch('/maestro/admin/config') })
  const cenarios = useQuery<{ cenarios: CenarioApi[] }>({ queryKey: Q_CENARIOS, queryFn: () => apiFetch('/maestro/admin/cenarios') })
  const pedidos = useQuery<{ pedidos: PedidoApi[] }>({
    queryKey: [Q_PEDIDOS, tratados], queryFn: () => apiFetch(`/maestro/admin/pedidos?tratados=${tratados}`),
  })

  // O chat lê `['maestro-status']` (visibilidade + sugestões do catálogo):
  // ligar/desligar ou mexer no catálogo tem de refletir lá na mesma sessão.
  const invalidar = () => Promise.all([
    qc.invalidateQueries({ queryKey: Q_CONFIG }),
    qc.invalidateQueries({ queryKey: Q_CENARIOS }),
    qc.invalidateQueries({ queryKey: [Q_PEDIDOS] }),
    qc.invalidateQueries({ queryKey: ['maestro-status'] }),
  ])

  const ligar = useMutation({
    mutationFn: (enabled: boolean) => apiFetch<{ enabled: boolean }>('/maestro/admin/config', { method: 'POST', body: JSON.stringify({ enabled }) }),
    onSuccess: async r => { toast.success(r.enabled ? 'Maestro ligado' : 'Maestro desligado'); await invalidar() },
    onError: (e: unknown) => toast.error(mensagemErroAdmin(e, 'Não foi possível alterar o interruptor')),
  })
  const salvar = useMutation({
    mutationFn: ({ corpo, id }: { corpo: ReturnType<typeof cenarioParaApi>; id: number | null }) =>
      apiFetch<{ cenario: CenarioApi }>(id === null ? '/maestro/admin/cenarios' : `/maestro/admin/cenarios/${id}`,
        { method: 'POST', body: JSON.stringify(corpo) }),
    onSuccess: async r => { toast.success(`Cenário "${r.cenario.codigo}" salvo`); setEditando(null); await invalidar() },
    onError: (e: unknown) => toast.error(mensagemErroAdmin(e, 'Não foi possível salvar o cenário')),
  })
  const excluir = useMutation({
    mutationFn: (id: number) => apiFetch<{ excluido: number }>(`/maestro/admin/cenarios/${id}/excluir`, { method: 'POST' }),
    onSuccess: async () => { toast.success('Cenário excluído'); setConfirmandoExclusao(null); await invalidar() },
    onError: (e: unknown) => { setConfirmandoExclusao(null); toast.error(mensagemErroAdmin(e, 'Não foi possível excluir')) },
  })
  const tratar = useMutation({
    mutationFn: ({ id, tratado }: { id: number; tratado: boolean }) =>
      apiFetch(`/maestro/admin/pedidos/${id}/tratar`, { method: 'POST', body: JSON.stringify({ tratado }) }),
    onSuccess: async (_r, v) => { toast.success(v.tratado ? 'Pedido marcado como tratado' : 'Pedido reaberto'); await invalidar() },
    onError: (e: unknown) => toast.error(mensagemErroAdmin(e, 'Não foi possível atualizar o pedido')),
  })

  if (config.isLoading) return <PageSpinner />
  if (config.isError || !config.data) {
    return (
      <InfoBanner icon="⚠">
        {migration110Pendente(config.error)
          ? 'O Maestro exige a migration 110 (tabelas etl_maestro_*). Aplique-a na etapa 6c do deploy e recarregue.'
          : `Falha ao carregar a configuração do Maestro: ${mensagemErroAdmin(config.error, 'erro desconhecido')}`}
      </InfoBanner>
    )
  }
  const cfg = config.data
  const lista = cenarios.data?.cenarios ?? []
  const listaPedidos = pedidos.data?.pedidos ?? []

  return (
    <div className="flex max-w-5xl flex-col gap-5" data-maestro-admin>
      <InfoBanner>
        O Maestro é o assistente conversacional da seção <em>Parâmetros do job</em> (Etapas e Fluxos): o usuário
        descreve o cenário e ele diz como preencher cada parâmetro. Ele só promete o que está no <strong>catálogo</strong>
        abaixo e se monta com o vocabulário dos parâmetros; o resto vira um <strong>pedido não atendido</strong> para
        você avaliar. Usa o provedor de IA configurado em <em>Caixa Seguro IA</em>.
      </InfoBanner>

      {/* ── Interruptor ─────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3 rounded-lg border border-edge bg-panel p-4 shadow-sm" data-maestro-interruptor>
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex h-11 w-11 items-center justify-center rounded-full border border-edge bg-canvas">
            <MaestroAvatar size={36} className={cfg.ativo ? '' : 'opacity-50'} />
          </span>
          <Switch
            label={cfg.enabled ? 'Maestro ligado' : 'Maestro desligado'}
            checked={cfg.enabled}
            disabled={ligar.isPending}
            onChange={e => ligar.mutate(e.target.checked)}
            hint="Ligado, o avatar aparece na seção Parâmetros do job para quem tem acesso a Etapas/Fluxos. Ligar exige o provedor de IA com chave em Caixa Seguro IA."
          />
          <div className="text-xs text-dim">
            Provedor: <span className="text-ink">{cfg.provedor.provider}</span>
            {cfg.provedor.model ? <> · modelo <span className="text-ink">{cfg.provedor.model}</span></> : null}
            {' · '}chave de API: {cfg.provedor.api_key_set
              ? <span className="text-emerald-700 dark:text-emerald-300">configurada</span>
              : <span className="text-amber-700 dark:text-amber-300">ausente (Admin › Caixa Seguro IA)</span>}
          </div>
        </div>
        {cfg.enabled && !cfg.provedor.api_key_set && (
          <p className="text-xs text-amber-700 dark:text-amber-300" data-maestro-sem-chave>
            Ligado, mas sem provedor de IA com chave: o avatar fica oculto e o chat responderia "sem provedor". Configure a chave em Caixa Seguro IA.
          </p>
        )}
        <p className="text-[11px] text-dim">
          {cfg.cenarios_ativos} de {cfg.total_cenarios} cenário(s) ativo(s) · {cfg.pedidos_abertos} pedido(s) não atendido(s) em aberto ·
          conversas guardadas por {cfg.retencao_dias} dias (limpeza diária da DAG etl_log_cleanup).
        </p>
      </section>

      {/* ── Catálogo ────────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3 rounded-lg border border-edge bg-panel p-4 shadow-sm" data-maestro-catalogo>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-ink">Catálogo de cenários</h3>
          <span className="text-xs text-dim">— o que o Maestro pode prometer; os exemplos viram as sugestões de abertura do chat</span>
          <Button size="sm" variant="primary" className="ml-auto" onClick={() => { setChaveModal(k => k + 1); setEditando('novo') }} data-maestro-novo>
            <Plus size={13} /> Novo cenário
          </Button>
        </div>
        {cenarios.isLoading ? <PageSpinner /> : cenarios.isError ? (
          <p className="text-sm text-red-600 dark:text-red-400">Falha ao carregar o catálogo: {mensagemErroAdmin(cenarios.error, 'erro desconhecido')}</p>
        ) : lista.length === 0 ? (
          <p className="text-sm text-dim">Nenhum cenário. Sem catálogo o Maestro só conhece o vocabulário dos parâmetros.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full text-xs">
              <thead className="bg-canvas/60 text-dim">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium">Código</th>
                  <th className="px-2 py-1.5 text-left font-medium">Título</th>
                  <th className="px-2 py-1.5 text-left font-medium">Parâmetros</th>
                  <th className="px-2 py-1.5 text-left font-medium">Exemplos</th>
                  <th className="px-2 py-1.5 text-left font-medium">Situação</th>
                  <th className="px-2 py-1.5 text-left font-medium">Atualizado</th>
                  <th className="w-24" />
                </tr>
              </thead>
              <tbody>
                {lista.map(c => (
                  <tr key={c.id} className="border-t border-edge/60 align-top" data-maestro-cenario={c.codigo}>
                    <td className="px-2 py-1.5 font-mono text-ink">{c.codigo}</td>
                    <td className="px-2 py-1.5 text-ink">
                      {c.titulo}
                      <p className="mt-0.5 line-clamp-2 text-[11px] text-dim">{c.descricao}</p>
                    </td>
                    <td className="px-2 py-1.5 font-mono text-dim">{c.receita.params.map(p => p.param_name).join(', ') || '—'}</td>
                    <td className="px-2 py-1.5 text-dim">{c.receita.exemplos.length}</td>
                    <td className="px-2 py-1.5"><Badge value={c.ativo ? 'ativo' : 'inativo'}>{c.ativo ? 'ativo' : 'inativo'}</Badge></td>
                    <td className="px-2 py-1.5 text-dim">{c.atualizado_em ?? c.criado_em ?? '—'}{c.atualizado_por || c.criado_por ? ` · ${c.atualizado_por ?? c.criado_por}` : ''}</td>
                    <td className="px-1 py-1.5">
                      <div className="flex items-center justify-end gap-0.5">
                        <button type="button" title="Editar" aria-label={`Editar ${c.codigo}`} className="rounded p-1 text-dim hover:text-ink"
                                onClick={() => { setChaveModal(k => k + 1); setEditando(c) }} data-maestro-editar={c.codigo}>
                          <Pencil size={13} />
                        </button>
                        {confirmandoExclusao === c.id ? (
                          <span className="flex items-center gap-1 text-[11px]">
                            <span className="text-dim">excluir?</span>
                            <Button size="sm" variant="danger" onClick={() => excluir.mutate(c.id)} disabled={excluir.isPending}>Sim</Button>
                            <Button size="sm" variant="ghost" onClick={() => setConfirmandoExclusao(null)}>Não</Button>
                          </span>
                        ) : (
                          <button type="button" title="Excluir" aria-label={`Excluir ${c.codigo}`} className="rounded p-1 text-dim hover:text-red-600"
                                  onClick={() => setConfirmandoExclusao(c.id)} data-maestro-excluir={c.codigo}>
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Pedidos não atendidos ───────────────────────────────────────── */}
      <section className="flex flex-col gap-3 rounded-lg border border-edge bg-panel p-4 shadow-sm" data-maestro-pedidos>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-ink">Pedidos não atendidos</h3>
          <span className="text-xs text-dim">— cenários que os usuários pediram e o Maestro não pôde prometer</span>
          <label className="ml-auto flex items-center gap-1.5 text-xs text-dim">
            <input type="checkbox" checked={tratados} onChange={e => setTratados(e.target.checked)} /> mostrar os já tratados
          </label>
        </div>
        {pedidos.isLoading ? <PageSpinner /> : pedidos.isError ? (
          <p className="text-sm text-red-600 dark:text-red-400">Falha ao carregar os pedidos: {mensagemErroAdmin(pedidos.error, 'erro desconhecido')}</p>
        ) : listaPedidos.length === 0 ? (
          <p className="text-sm text-dim">{tratados ? 'Nenhum pedido tratado.' : 'Nenhum pedido em aberto.'}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full text-xs">
              <thead className="bg-canvas/60 text-dim">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium">Quando</th>
                  <th className="px-2 py-1.5 text-left font-medium">Quem</th>
                  <th className="px-2 py-1.5 text-left font-medium">Pipeline / etapa</th>
                  <th className="px-2 py-1.5 text-left font-medium">Pedido</th>
                  <th className="px-2 py-1.5 text-left font-medium">Por que não atendeu</th>
                  <th className="w-28" />
                </tr>
              </thead>
              <tbody>
                {listaPedidos.map(p => (
                  <tr key={p.id} className="border-t border-edge/60 align-top" data-maestro-pedido={p.id}>
                    <td className="whitespace-nowrap px-2 py-1.5 text-dim">{p.criado_em}</td>
                    <td className="px-2 py-1.5 text-ink">{p.matricula}</td>
                    <td className="px-2 py-1.5 font-mono text-dim">{p.pipeline_name ?? '—'}{p.job_name ? ` / ${p.job_name}` : ''}</td>
                    <td className="px-2 py-1.5 text-ink">{p.mensagem}</td>
                    <td className="px-2 py-1.5 text-dim">{p.motivo ?? '—'}{p.tratado_em ? <span className="block text-[11px]">tratado em {p.tratado_em}{p.tratado_por ? ` por ${p.tratado_por}` : ''}</span> : null}</td>
                    <td className="px-1 py-1.5 text-right">
                      <Button size="sm" variant={p.tratado_em ? 'ghost' : 'secondary'} disabled={tratar.isPending}
                              onClick={() => tratar.mutate({ id: p.id, tratado: !p.tratado_em })} data-maestro-tratar={p.id}>
                        {p.tratado_em ? <><RotateCcw size={12} /> Reabrir</> : 'Marcar tratado'}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editando !== null && (
        <MaestroCenarioModal
          key={chaveModal}
          aberto={editando}
          salvando={salvar.isPending}
          onFechar={() => setEditando(null)}
          onSalvar={(corpo, id) => salvar.mutate({ corpo, id })}
        />
      )}
    </div>
  )
}
