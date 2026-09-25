import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { Edit2, Trash2, Plus, Save, RefreshCw, Zap } from 'lucide-react'
import { InfoBanner } from '../../ui/InfoBanner'

// ── Conexões de Dados (dbo.etl_conexao via POST /admin) ───────────────────
// CRUD + teste das conexões usadas pela Cópia de Dados e pelos nós SQL.
// As credenciais vivem no ORQUESTRA (senha cifrada com Fernet — migration
// 054); a API NUNCA devolve a senha (edição com senha em branco mantém a
// atual). origem 'airflow' = conexão legada ainda não migrada (só leitura
// no Airflow) — o botão "Migrar do Airflow" traz todas com senha, via worker.
interface ConnRow {
  conn_id: string
  host: string
  port: number | null
  schema: string
  login: string
  description: string
  extra_charset: string | null
  origem: 'orquestra' | 'airflow'
}

const CHARSET_PADRAO = ['UTF-8', 'CP1252', 'CP850']

function ConnFormModal({ conn, onClose }: { conn: ConnRow | null; onClose: () => void }) {
  const isEdit = !!conn
  const [connId, setConnId] = useState(conn?.conn_id ?? '')
  const [host, setHost] = useState(conn?.host ?? '')
  const [port, setPort] = useState(conn?.port != null ? String(conn.port) : '1433')
  const [login, setLogin] = useState(conn?.login ?? '')
  const [password, setPassword] = useState('')
  const [description, setDescription] = useState(conn?.description ?? '')
  const [charsetSel, setCharsetSel] = useState(
    conn?.extra_charset ? (CHARSET_PADRAO.includes(conn.extra_charset) ? conn.extra_charset : 'outro') : '')
  const [charsetLivre, setCharsetLivre] = useState(
    conn?.extra_charset && !CHARSET_PADRAO.includes(conn.extra_charset) ? conn.extra_charset : '')
  const charset = charsetSel === 'outro' ? charsetLivre.trim() : charsetSel
  const [testando, setTestando] = useState(false)

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        conn_id: connId.trim(), host: host.trim(), port: port.trim(),
        login: login.trim(), description: description.trim(), charset,
      }
      // Senha em branco na edição = manter a atual (fica fora do update_mask no backend).
      if (password) body.password = password
      return adminPost<{ mensagem?: string }>('conn_upsert', body)
    },
    onSuccess: d => { toast.success(d?.mensagem ?? 'Connection salva'); queryClient.invalidateQueries({ queryKey: ['admin-conexoes'] }); onClose() },
    onError: (e: any) => toast.error(e?.message || 'Falha ao salvar a connection'),
  })

  // Teste com os dados do FORM (modo direto: a API monta a conn string com
  // host/porta/usuário/senha digitados e roda SELECT 1 — nada é salvo).
  const testarForm = async () => {
    setTestando(true)
    try {
      const d = await adminPost<{ ok: boolean; mensagem: string }>('conn_test', {
        host: host.trim(), port: port.trim(), login: login.trim(), password,
      })
      if (d.ok) toast.success(d.mensagem)
      else toast.error(d.mensagem)
    } catch (e: any) { toast.error(e?.message || 'Falha no teste de conexão') }
    finally { setTestando(false) }
  }

  // Conexão legada do Airflow: salvar CRIA o registro no Orquestra, então a
  // senha é obrigatória (ou use "Migrar do Airflow" para trazer sem redigitar).
  const criaNoOrquestra = !isEdit || conn?.origem === 'airflow'
  const podeTestar = !!host.trim() && !!login.trim() && !!password
  const podeSalvar = !!connId.trim() && !!host.trim() && !!login.trim() && (!criaNoOrquestra || !!password)

  return (
    <Modal open onClose={onClose} title={isEdit ? `Editar conexão — ${conn!.conn_id}` : 'Nova conexão'} size="lg">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input label="conn_id *" value={connId} onChange={e => setConnId(e.target.value)}
            disabled={isEdit} placeholder="ex.: MSSQL_BI_ORIGEM" autoFocus={!isEdit} />
          <Input label="Descrição" value={description} onChange={e => setDescription(e.target.value)}
            placeholder="Para que serve esta conexão" />
        </div>
        <div className="grid grid-cols-[1fr_7rem] gap-3">
          <Input label="Host *" value={host} onChange={e => setHost(e.target.value)}
            placeholder="servidor.dominio ou 10.0.0.1" autoFocus={isEdit} />
          <Input label="Porta" type="number" value={port} onChange={e => setPort(e.target.value)} placeholder="1433" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input label="Usuário *" value={login} onChange={e => setLogin(e.target.value)} placeholder="login do SQL Server" />
          <Input label={criaNoOrquestra ? 'Senha *' : 'Senha'} type="password" value={password}
            onChange={e => setPassword(e.target.value)} autoComplete="new-password"
            placeholder={criaNoOrquestra ? '••••••••' : 'deixe em branco para manter a atual'} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Select label="Charset (extra da connection)" value={charsetSel} onChange={e => setCharsetSel(e.target.value)}>
            <option value="">Padrão (sem override)</option>
            {CHARSET_PADRAO.map(c => <option key={c} value={c}>{c}</option>)}
            <option value="outro">Outro…</option>
          </Select>
          {charsetSel === 'outro' && (
            <Input label="Charset (campo livre)" value={charsetLivre}
              onChange={e => setCharsetLivre(e.target.value)} placeholder="ex.: LATIN1" />
          )}
        </div>
        <p className="text-[11px] text-dim">
          {conn?.origem === 'airflow'
            ? 'Conexão legada do Airflow — ao salvar (com senha) ela passa a viver no Orquestra. Para trazer sem redigitar a senha, use "Migrar do Airflow" na listagem.'
            : 'A senha é armazenada no Orquestra criptografada (Fernet) e nunca é exibida.'}
        </p>
        <div className="flex items-center justify-between border-t border-edge pt-3">
          <Button variant="secondary" size="sm" onClick={testarForm} loading={testando} disabled={!podeTestar}
            title={podeTestar ? 'Testa direto com os dados do formulário (SELECT 1)' : 'Preencha host, usuário e senha para testar'}>
            <Zap size={13} /> Testar conexão
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
            <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!podeSalvar}>
              <Save size={13} /> Salvar
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export function ConexoesTab() {
  const [form, setForm] = useState<{ open: boolean; conn: ConnRow | null }>({ open: false, conn: null })
  const [delConn, setDelConn] = useState<string | null>(null)
  const [testandoId, setTestandoId] = useState<string | null>(null)

  const { data, isLoading, isError, error } = useQuery<{ connections: ConnRow[] }>({
    queryKey: ['admin-conexoes'],
    queryFn: () => adminPost('conn_list'),
  })

  const delMut = useMutation({
    mutationFn: (conn_id: string) => adminPost<{ mensagem?: string }>('conn_delete', { conn_id }),
    onSuccess: d => { toast.success(d?.mensagem ?? 'Connection removida'); queryClient.invalidateQueries({ queryKey: ['admin-conexoes'] }) },
    // 409 quando referenciada: o detail lista as cópias/jobs que usam a connection.
    onError: (e: any) => toast.error(e?.message || 'Falha ao excluir a connection'),
  })

  // Migra as connections mssql do Airflow para o Orquestra COM senha — roda
  // no worker (DAG etl_admin_manage), a senha não trafega pela API/navegador.
  const migrarMut = useMutation({
    mutationFn: () => adminPost<{ mensagem?: string }>('conn_migrate'),
    onSuccess: d => { toast.success(d?.mensagem ?? 'Migração concluída'); queryClient.invalidateQueries({ queryKey: ['admin-conexoes'] }) },
    onError: (e: any) => toast.error(e?.message || 'Falha na migração das conexões'),
  })

  // Teste da conexão SALVA (conn_id): com a credencial cadastrada no
  // Orquestra; conexão legada cai no caminho antigo via Airflow (~30s).
  const testarSalva = async (conn_id: string) => {
    setTestandoId(conn_id)
    toast.info(`Testando "${conn_id}"…`)
    try {
      const d = await adminPost<{ ok: boolean; mensagem: string; via?: string }>('conn_test', { conn_id })
      if (d.ok) toast.success(d.mensagem)
      else toast.error(d.mensagem)
    } catch (e: any) { toast.error(e?.message || 'Falha no teste de conexão') }
    finally { setTestandoId(null) }
  }

  const conns = data?.connections ?? []
  const pendentesAirflow = conns.filter(c => c.origem === 'airflow').length

  return (
    <div className="flex flex-col gap-4">
      <InfoBanner storageKey="admin_conexoes_v2">
        As credenciais são armazenadas no Orquestra (senha criptografada). Esta tela gerencia as
        conexões mssql usadas pela Cópia de Dados e pelos jobs. Conexões marcadas como
        “Airflow” são legadas — use “Migrar do Airflow” para trazê-las com a senha.
      </InfoBanner>

      <div className="flex items-center justify-between">
        <p className="text-sm text-dim">
          Conexões <span className="font-mono text-xs">mssql</span> do Orquestra
          {pendentesAirflow > 0 && <> — {pendentesAirflow} pendente(s) de migração do Airflow</>}.
        </p>
        <div className="flex gap-2">
          {pendentesAirflow > 0 && (
            <Button size="sm" variant="secondary" onClick={() => migrarMut.mutate()} loading={migrarMut.isPending}
              title="Importa as connections mssql do Airflow (com senha) para o Orquestra — roda no worker, pode levar ~1 min">
              <RefreshCw size={13} /> Migrar do Airflow
            </Button>
          )}
          <Button size="sm" onClick={() => setForm({ open: true, conn: null })}><Plus size={13} /> Nova conexão</Button>
        </div>
      </div>

      {isLoading ? <PageSpinner /> : isError ? (
        <p className="text-sm text-red-600 dark:text-red-400">
          Falha ao listar as connections: {(error as any)?.message}
        </p>
      ) : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold">conn_id</th>
                <th className="px-4 py-2.5 text-left font-semibold">Host:porta</th>
                <th className="px-4 py-2.5 text-left font-semibold">Descrição</th>
                <th className="px-4 py-2.5 text-left font-semibold">Charset</th>
                <th className="px-4 py-2.5 text-left font-semibold">Origem</th>
                <th className="px-4 py-2.5 w-28"></th>
              </tr>
            </thead>
            <tbody>
              {conns.map(c => (
                <tr key={c.conn_id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2"><span className="font-mono text-xs text-[#1A5FA8] dark:text-blue-400">{c.conn_id}</span></td>
                  <td className="px-4 py-2 font-mono text-xs text-ink">{c.host}{c.port != null ? `:${c.port}` : ''}</td>
                  <td className="px-4 py-2 text-xs text-dim">{c.description || '—'}</td>
                  <td className="px-4 py-2">{c.extra_charset ? <Badge>{c.extra_charset}</Badge> : <span className="text-xs text-dim">—</span>}</td>
                  <td className="px-4 py-2">
                    {c.origem === 'orquestra'
                      ? <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">Orquestra</span>
                      : <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" title="Conexão legada — ainda no Airflow; use Migrar do Airflow">Airflow</span>}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => setForm({ open: true, conn: c })}
                        className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar">
                        <Edit2 size={13} />
                      </button>
                      <button onClick={() => testarSalva(c.conn_id)} disabled={testandoId !== null}
                        className="text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 p-1 rounded disabled:opacity-40"
                        title="Testar a connection salva (pode levar ~30s via Airflow)">
                        {testandoId === c.conn_id ? <RefreshCw size={13} className="animate-spin" /> : <Zap size={13} />}
                      </button>
                      <button onClick={() => setDelConn(c.conn_id)}
                        className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {conns.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-xs text-dim">Nenhuma conexão mssql cadastrada.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {form.open && <ConnFormModal conn={form.conn} onClose={() => setForm({ open: false, conn: null })} />}

      <ConfirmModal
        open={!!delConn}
        title="Excluir conexão"
        message={`Excluir a conexão "${delConn}"? Se estiver em uso por uma Cópia de Dados ou por um job, a exclusão será recusada.`}
        danger confirmLabel="Excluir"
        onConfirm={() => delConn && delMut.mutate(delConn)}
        onCancel={() => setDelConn(null)}
      />
    </div>
  )
}
