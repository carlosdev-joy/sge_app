import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { Q_AGENTES_ADMIN, agenteInelegivel, mensagemDeErro } from '../../../lib/agentes'
import { RBAC_RECURSOS } from '../../../lib/rbacRecursos'
import { adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { Q_ADMIN_PERFIS, buscarPerfis, nomesDePerfis, type PerfilRow } from '../acesso'
import { Edit2, Trash2, Plus, Save, KeyRound } from 'lucide-react'

/**
 * Sinal ao lado de um grant de agente no modal de permissões extras quando o
 * perfil do usuário não pode usar aquele agente: MARCADO = sem efeito (continua
 * gravado, mas a régua de uso recusa — e volta a valer se o perfil voltar a ser
 * elegível); DESMARCADO = não dá para conceder (a API recusaria com 422).
 */
function SinalGrantAgente({ agente, perfil, marcado, ehAdmin }: {
  agente: string | null; perfil: string; marcado: boolean
  /** Tem `acao_admin` (pelo perfil ou nas extras): usa todo agente, grant ou não. */
  ehAdmin: boolean
}) {
  if (agente === null) return null
  // Com `acao_admin` ele USA o agente (a régua libera admin antes do perfil): o
  // grant marcado não acrescenta nada, mas "não pode usar" seria falso.
  if (marcado && ehAdmin) return null
  return marcado ? (
    <span className="text-[10px] text-amber-700 dark:text-amber-400" data-perm-sem-efeito
          title={`Volta a valer se o perfil ${perfil} voltar a poder usar ${agente}. Desmarque para remover.`}>
      {`(sem efeito — o perfil ${perfil} não pode usar ${agente})`}
    </span>
  ) : (
    <span className="text-[10px] text-dim" data-perm-nao-elegivel>(perfil não elegível)</span>
  )
}

// ── Usuários ────────────────────────────────────────────────────
// Decisão explícita da spec (docs/spec-admin-reestruturacao.md, F3): até a F2
// esta era a aba "Usuários & Perfis", com três blocos em sequência — Usuários,
// Perfis e Permissões, Mapeamento de Roles. Os dois últimos viraram as abas
// Acesso › Perfis e Permissões (abas/PerfisTab.tsx) e Acesso › Roles do
// Airflow (abas/RolesAirflowTab.tsx). Aqui fica a lista de usuários e o modal
// de permissões extras/identidade no gateway (com o SinalGrantAgente).
interface UsuarioRow { matricula: string; perfil: string; primeiro_nome?: string; ultimo_nome?: string; email?: string; ativo: boolean; ultimo_login?: string; identidade_gateway?: string | null }
export function UsuariosTab() {
  const [userForm, setUserForm] = useState({ matricula: '', perfil: 'consulta' })
  const [deleteUser, setDeleteUser] = useState<string | null>(null)
  // permissões extras por usuário (além do perfil)
  const [permUser, setPermUser] = useState<UsuarioRow | null>(null)
  const [permDraft, setPermDraft] = useState<Set<string>>(new Set())
  // identidade no gateway de IA (spec docs/spec-agentes-datastage.md, D-16):
  // cadastro que sobrepõe o padrão cvp-<matrícula>. Editada no mesmo modal
  // de permissões extras, mas salva por uma ação PRÓPRIA (user_identidade_set).
  const [identidadeDraft, setIdentidadeDraft] = useState('')

  const { data, isLoading } = useQuery<{ usuarios: UsuarioRow[] }>({ queryKey: ['admin-usuarios'], queryFn: () => adminPost('user_list') })
  // Perfis: o select do formulário e o "(do perfil)" do modal de extras. Mesma
  // query da aba Perfis e Permissões — ver components/admin/acesso.ts.
  const { data: perfis } = useQuery<{ perfis: PerfilRow[] }>({ queryKey: Q_ADMIN_PERFIS, queryFn: buscarPerfis })
  // Recursos dos agentes criados pela tela (spec admin B3) — vêm da API, não
  // de uma 2ª lista à mão. Só quando o modal abre; sem a lista, o modal segue
  // com os fixos (o `permDraft` reenvia os grants que não aparecem).
  const agentesDaTela = useQuery<{ agentes: { origem: string; nome: string; recurso: string; recurso_curador: string | null; perfis: string[] }[] }>({
    queryKey: Q_AGENTES_ADMIN, queryFn: () => apiFetch('/agentes/admin/agentes'), enabled: permUser !== null,
  })
  // Grant de agente para um perfil que não pode usá-lo: marcado, está SEM EFEITO
  // (a régua de uso confere o perfil a cada pergunta — e ele volta a valer se o
  // perfil voltar a ser elegível); desmarcado, não se concede (a API recusaria).
  const inelegivel = (rec: string) => permUser ? agenteInelegivel(rec, permUser.perfil, agentesDaTela.data?.agentes ?? []) : null
  const recursosDeAgentes: [string, string][] = (agentesDaTela.data?.agentes ?? [])
    .filter(a => a.origem === 'banco')
    .flatMap(a => [
      [a.recurso, `Agente — ${a.nome}`] as [string, string],
      ...(a.recurso_curador ? [[a.recurso_curador, `Agente — Curador — ${a.nome}`] as [string, string]] : []),
    ])
  const { data: userPerms } = useQuery<{ permissoes: Record<string, string[]> }>({ queryKey: ['admin-user-perms'], queryFn: () => adminPost('user_perm_list') })

  const userUpsert = useMutation({
    mutationFn: (p: { matricula: string; perfil: string }) => adminPost('user_upsert', { ...p, ativo: true }),
    onSuccess: () => { toast.success('Usuário salvo'); queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] }); setUserForm({ matricula: '', perfil: 'consulta' }) },
    onError: (e: any) => toast.error(e.message),
  })
  const userDelete = useMutation({
    mutationFn: (matricula: string) => adminPost('user_delete', { matricula }),
    onSuccess: () => { toast.success('Usuário removido'); queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] }); setDeleteUser(null) },
    onError: (e: any) => toast.error(e.message),
  })
  const userPermSet = useMutation({
    mutationFn: (p: { matricula: string; permissoes: string[] }) => adminPost('user_perm_set', p),
    onSuccess: (_, v) => { toast.success(`Permissões extras de ${v.matricula} salvas (sessões do usuário renovadas)`); queryClient.invalidateQueries({ queryKey: ['admin-user-perms'] }); setPermUser(null) },
    // `detail` do 422 de agente é OBJETO ({code, message}); `e.message` virava
    // só "422 Unprocessable Entity" (revisão da B3 da spec admin).
    onError: (e: unknown) => toast.error(mensagemDeErro(e, 'Não foi possível salvar as permissões')),
  })
  const userIdentidadeSet = useMutation({
    mutationFn: (p: { matricula: string; identidade_gateway: string }) => adminPost('user_identidade_set', p),
    onSuccess: (_, v) => { toast.success(`Identidade de gateway de ${v.matricula} salva`); queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] }) },
    onError: (e: Error) => toast.error(e.message),
  })

  const perfilOpts = perfis?.perfis ?? []
  const perfilNames = nomesDePerfis(perfilOpts)
  const usuarios = data?.usuarios ?? []

  return (
    <div className="flex flex-col gap-6">
      {/* Usuários */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-ink">Usuários</h3>
        {isLoading ? <PageSpinner /> : (
          <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                  <th className="px-4 py-2.5 text-left font-semibold">Matrícula</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Perfil</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Extras</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Último Login</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Ativo</th>
                  <th className="px-4 py-2.5 w-20"></th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map(u => (
                  <tr key={u.matricula} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                    <td className="px-4 py-2.5 font-mono text-xs font-medium text-[#1A5FA8] dark:text-blue-400">{u.matricula}</td>
                    <td className="px-4 py-2.5 text-xs text-ink">{[u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || '—'}</td>
                    <td className="px-4 py-2.5"><Badge value={u.perfil} /></td>
                    <td className="px-4 py-2.5 text-xs text-dim">
                      {(userPerms?.permissoes?.[u.matricula]?.length ?? 0) > 0
                        ? <span className="font-medium text-[#1A5FA8] dark:text-blue-400">+{userPerms!.permissoes[u.matricula].length}</span>
                        : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-dim">{u.ultimo_login ?? '—'}</td>
                    <td className="px-4 py-2.5 text-xs">{u.ativo ? '✓' : <span className="text-red-500">✕</span>}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => { setPermUser(u); setPermDraft(new Set(userPerms?.permissoes?.[u.matricula] ?? [])); setIdentidadeDraft(u.identidade_gateway ?? '') }} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Permissões extras"><KeyRound size={13} /></button>
                        <button onClick={() => setUserForm({ matricula: u.matricula, perfil: u.perfil })} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                        <button onClick={() => setDeleteUser(u.matricula)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Remover"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {usuarios.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-xs text-dim">Nenhum usuário — entram automaticamente no 1º login.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-wrap gap-3 items-end">
          <Input label="Matrícula" value={userForm.matricula} onChange={e => setUserForm(f => ({ ...f, matricula: e.target.value.toUpperCase() }))} className="w-40" placeholder="C123456" />
          <Select label="Perfil" value={userForm.perfil} onChange={e => setUserForm(f => ({ ...f, perfil: e.target.value }))} className="w-40">
            {perfilNames.map(p => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Button onClick={() => userUpsert.mutate(userForm)} loading={userUpsert.isPending} disabled={!userForm.matricula.trim()}><Plus size={13} /> Adicionar / Atualizar</Button>
        </div>
      </div>

      {permUser && (() => {
        const doPerfil = new Set(perfilOpts.find(p => p.perfil_nome === permUser.perfil)?.permissoes ?? [])
        // Com `acao_admin` (pelo perfil ou nas extras) ele usa todo agente — ver SinalGrantAgente.
        const ehAdmin = doPerfil.has('acao_admin') || permDraft.has('acao_admin')
        return (
          <Modal open onClose={() => setPermUser(null)} title={`Permissões extras — ${permUser.matricula}`} size="sm">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5 border-b border-edge pb-4">
                <label className="text-xs font-semibold text-ink">Identidade no gateway de IA</label>
                <p className="text-[11px] text-dim">
                  O identificador enviado ao gateway. Vazio usa o padrão <code>cvp-{permUser.matricula.toLowerCase()}</code>;
                  preencha só se o gateway conhecer este usuário por outro identificador.
                </p>
                <div className="flex items-center gap-2">
                  <Input value={identidadeDraft} onChange={e => setIdentidadeDraft(e.target.value)}
                    placeholder={`cvp-${permUser.matricula.toLowerCase()}`} className="flex-1" maxLength={100} />
                  <Button size="sm" variant="secondary" loading={userIdentidadeSet.isPending}
                    onClick={() => userIdentidadeSet.mutate({ matricula: permUser.matricula, identidade_gateway: identidadeDraft.trim() })}>
                    <Save size={11} /> Salvar
                  </Button>
                </div>
              </div>
              <p className="text-xs text-dim">
                Recursos concedidos <strong>além</strong> do perfil <Badge value={permUser.perfil} />.
                Os já herdados do perfil aparecem marcados e travados.
              </p>
              <div className="flex flex-col gap-1.5 max-h-80 overflow-y-auto">
                {RBAC_RECURSOS.map(([rec, lbl]) => {
                  const herdado = doPerfil.has(rec)
                  const agenteFora = inelegivel(rec)
                  const travado = herdado || (agenteFora !== null && !permDraft.has(rec))
                  return (
                    <label key={rec} className={`flex items-center gap-2 text-xs ${travado ? 'text-dim' : 'text-ink cursor-pointer'}`}>
                      <input
                        type="checkbox"
                        disabled={travado}
                        checked={herdado || permDraft.has(rec)}
                        onChange={() => setPermDraft(prev => {
                          const n = new Set(prev)
                          n.has(rec) ? n.delete(rec) : n.add(rec)
                          return n
                        })}
                      />
                      {lbl}
                      {herdado && <span className="text-[10px] text-dim">(do perfil)</span>}
                      {!herdado && <SinalGrantAgente agente={agenteFora} perfil={permUser.perfil} marcado={permDraft.has(rec)} ehAdmin={ehAdmin} />}
                    </label>
                  )
                })}
                {recursosDeAgentes.length > 0 && (
                  <p className="text-[11px] font-semibold text-dim pt-2" data-perm-agentes-da-tela>Agentes criados na tela</p>
                )}
                {recursosDeAgentes.map(([rec, lbl]) => (
                  <label key={rec} className={`flex items-center gap-2 text-xs ${inelegivel(rec) !== null && !permDraft.has(rec) ? 'text-dim' : 'text-ink cursor-pointer'}`}>
                    <input
                      type="checkbox"
                      disabled={inelegivel(rec) !== null && !permDraft.has(rec)}
                      checked={permDraft.has(rec)}
                      onChange={() => setPermDraft(prev => {
                        const n = new Set(prev)
                        if (n.has(rec)) n.delete(rec)
                        else n.add(rec)
                        return n
                      })}
                    />
                    {lbl}
                    <SinalGrantAgente agente={inelegivel(rec)} perfil={permUser.perfil} marcado={permDraft.has(rec)} ehAdmin={ehAdmin} />
                  </label>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="secondary" size="sm" onClick={() => setPermUser(null)}>Cancelar</Button>
                <Button size="sm" loading={userPermSet.isPending}
                  onClick={() => userPermSet.mutate({ matricula: permUser.matricula, permissoes: Array.from(permDraft) })}>
                  <Save size={11} /> Salvar
                </Button>
              </div>
            </div>
          </Modal>
        )
      })()}
      <ConfirmModal open={!!deleteUser} title="Remover Usuário" message={`Remover "${deleteUser}"? Volta ao perfil "consulta" se logar novamente.`} danger confirmLabel="Remover" onConfirm={() => deleteUser && userDelete.mutate(deleteUser)} onCancel={() => setDeleteUser(null)} />
    </div>
  )
}
