import { useQuery } from '@tanstack/react-query'
import { Button } from '../../ui/Button'
import { PageSpinner } from '../../ui/Spinner'
import { adminPost } from '../comum'
import { RefreshCw, Database } from 'lucide-react'

// ── Servidor (diagnóstico) ───────────────────────────────────────
// Seção de cima de Integrações › Bancos & Monitoramento (abas/BancosTab.tsx).
// Até a F2 de docs/spec-admin-reestruturacao.md era a aba própria "Bancos do
// servidor" (abas/ServidorTab.tsx); o conteúdo não mudou.
interface ServerDb { name: string; state: string; recovery: string; create_date: string | null; size_mb: number | null }

export function ServidorTab() {
  const { data, isLoading, refetch, isFetching } = useQuery<{ sucesso: boolean; server: string | null; databases: ServerDb[]; total: number }>({
    queryKey: ['server_databases'],
    queryFn: () => adminPost('server_databases'),
  })
  const dbs = data?.databases ?? []
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-[#1A5FA8] dark:text-blue-400" />
          <div>
            <h2 className="text-sm font-bold text-ink">Bancos do servidor</h2>
            <p className="text-xs text-dim mt-0.5">
              Lista os bancos do mesmo servidor SQL usando a credencial do ORQUESTRA (<code className="text-[11px]">sys.databases</code>).
              {data?.server && <> Servidor: <span className="font-mono text-ink">{data.server}</span></>}
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()} loading={isFetching}><RefreshCw size={13} /> Atualizar</Button>
      </div>

      {isLoading && <PageSpinner />}
      {!isLoading && dbs.length === 0 && (
        <div className="text-xs text-dim py-8 text-center">Nenhum banco retornado (ou a credencial não tem permissão para listar).</div>
      )}
      {dbs.length > 0 && (
        <>
          <div className="text-xs text-dim">{data?.total} banco(s) visível(is) com esta credencial.</div>
          <div className="overflow-x-auto border border-edge rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-edge/30 text-dim">
                <tr className="text-left">
                  <th className="px-3 py-2 font-medium">Banco</th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium">Recovery</th>
                  <th className="px-3 py-2 font-medium text-right">Tamanho (MB)</th>
                  <th className="px-3 py-2 font-medium">Criado em</th>
                </tr>
              </thead>
              <tbody>
                {dbs.map(d => (
                  <tr key={d.name} className="border-t border-edge/40 hover:bg-edge/20">
                    <td className="px-3 py-2 font-mono text-ink">{d.name}</td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${d.state === 'ONLINE'
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}`}>{d.state}</span>
                    </td>
                    <td className="px-3 py-2 text-dim text-xs">{d.recovery}</td>
                    <td className="px-3 py-2 text-right text-dim tabular-nums">{d.size_mb != null ? d.size_mb.toLocaleString('pt-BR') : '—'}</td>
                    <td className="px-3 py-2 text-dim text-xs">{d.create_date ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
