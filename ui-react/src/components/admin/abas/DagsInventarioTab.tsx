import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Badge } from '../../ui/Badge'
import { PageSpinner } from '../../ui/Spinner'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { InfoBanner } from '../../ui/InfoBanner'

// ── Inventário de DAGs do sistema ────────────────────────────────
// O catálogo (o que cada DAG faz, com que frequência) vem da API, que o
// mantém no código — documentação versionada junto das DAGs. O Airflow entra
// como fonte do ESTADO ao vivo: catalogada ausente é drift a investigar;
// presente e não catalogada é catálogo desatualizado. As DAGs de pipeline
// (geradas pela fábrica) não entram — o lugar delas é a tela Pipelines.
interface DagInventarioItem {
  dag_id: string
  funcionalidade: string
  frequencia: string
  categoria: string
  catalogada: boolean
  /** `null` = Airflow fora do ar ("não sei" ≠ "ausente"). */
  presente_no_airflow: boolean | null
  pausada: boolean | null
  agendamento: string | null
}

function EstadoDagBadge({ d, airflowOk }: { d: DagInventarioItem; airflowOk: boolean }) {
  if (!airflowOk || d.presente_no_airflow === null) return <Badge value="neutral">sem leitura</Badge>
  if (!d.presente_no_airflow) return <Badge value="error">ausente no Airflow</Badge>
  if (d.pausada) return <Badge value="warning">pausada</Badge>
  return <Badge value="success">ativa</Badge>
}

export function DagsInventarioTab() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<{
    airflow_disponivel: boolean; total: number; dags: DagInventarioItem[]
  }>({
    queryKey: ['admin-dags-inventario'],
    queryFn: () => apiFetch('/admin/dags/inventario'),
  })
  if (isLoading) return <PageSpinner />
  if (isError || !data) return (
    <p className="text-sm text-red-600 dark:text-red-400">
      Falha ao carregar o inventário de DAGs: {(error as Error | null)?.message}
    </p>
  )
  // A API já entrega ordenado por categoria (na ordem de exibição) e nome —
  // aqui só se agrupa o que chegou adjacente, sem reordenar nada.
  const grupos: { categoria: string; itens: DagInventarioItem[] }[] = []
  for (const d of data.dags) {
    const g = grupos[grupos.length - 1]
    if (g && g.categoria === d.categoria) g.itens.push(d)
    else grupos.push({ categoria: d.categoria, itens: [d] })
  }
  return (
    <div className="flex flex-col gap-4">
      <InfoBanner>
        As DAGs que fazem o Orquestra funcionar — o que cada uma faz e com que
        frequência roda. O catálogo vive no código (documentação versionada); o
        estado (ativa/pausada) é lido ao vivo do Airflow. As DAGs de pipeline
        geradas pela fábrica não entram aqui: o lugar delas é a tela Pipelines.
      </InfoBanner>
      {!data.airflow_disponivel && (
        <p className="flex items-center gap-1.5 text-[12px] text-amber-700 dark:text-amber-400">
          <AlertTriangle size={13} className="shrink-0" />
          Airflow indisponível agora — mostrando só o catálogo, sem o estado ao
          vivo (nenhuma DAG está sendo afirmada como ausente).
        </p>
      )}
      <div className="flex items-center gap-2">
        <span className="text-xs text-dim">{data.total} DAGs de sistema</span>
        <Button variant="secondary" size="sm" onClick={() => refetch()} loading={isFetching} className="ml-auto">
          <RefreshCw size={13} /> Atualizar
        </Button>
      </div>
      {grupos.map(g => (
        <div key={g.categoria} className="bg-panel border border-edge rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-edge">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-dim">{g.categoria}</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-dim text-left border-b border-edge/60">
                  <th className="font-medium px-4 py-2">DAG</th>
                  <th className="font-medium px-4 py-2">Funcionalidade</th>
                  <th className="font-medium px-4 py-2">Frequência de execução</th>
                  <th className="font-medium px-4 py-2">Estado</th>
                </tr>
              </thead>
              <tbody className="text-ink">
                {g.itens.map(d => (
                  <tr key={d.dag_id} className="border-b border-edge/40 last:border-0 align-top">
                    <td className="px-4 py-2 font-mono text-[11px] whitespace-nowrap">{d.dag_id}</td>
                    <td className="px-4 py-2">{d.funcionalidade}</td>
                    <td className="px-4 py-2">
                      {d.frequencia}
                      {d.agendamento && (
                        <div className="mt-0.5 font-mono text-[10px] text-dim" title="Agendamento em vigor no Airflow, lido ao vivo">
                          {d.agendamento}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      <EstadoDagBadge d={d} airflowOk={data.airflow_disponivel} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
