import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { erroCatalogo } from '../../lib/pipelineCatalogo'
import { conclusaoLabel, decisaoLabel, type ValidaConfig } from '../../lib/validaArquivo'
import { Button } from '../ui/Button'

interface Historico {
  original: boolean; validadores: Record<string, ValidaConfig>
  tentativas: { task_id: string; tentativa: number; revisao: number; criado_em: string;
    resultado: { entradas: { entrada_id: string; alvo: string; motivo: string; estado: string;
      linhas: number | null; linhas_fisicas: number | null; decisao: string }[] } }[]
  conclusao: { resultado: string; liberar_dependentes: boolean; notificar: boolean } | null
}
export function ValidacaoExecucao({ pipeline, runId }: { pipeline: string; runId: string }) {
  const q = useQuery<Historico>({ queryKey: ['validacao-execucao', pipeline, runId],
    queryFn: () => apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/validacao-execucao?run_id=${encodeURIComponent(runId)}`),
    refetchInterval: 15_000 })
  const h = q.data
  if (h && !h.original) return null
  return <details className="max-h-72 shrink-0 overflow-y-auto border-b border-edge bg-panel px-4 py-2 text-xs text-ink">
    <summary className="cursor-pointer font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500">
      Validação de arquivos · {h?.conclusao ? conclusaoLabel[h.conclusao.resultado] ?? h.conclusao.resultado : q.isError ? 'Histórico indisponível' : 'Consultar diagnóstico'}
    </summary>
    <div className="space-y-3 pt-3">
      <p className="break-all text-dim">Execução: {runId}. Configuração original preservada na retomada. “Liberado para executar” é uma decisão da validação; consulte o estado da etapa no canvas para saber se ela executou.</p>
      {q.isLoading && <p role="status">Carregando histórico…</p>}
      {q.isError && <p role="alert">{erroCatalogo(q.error)} <Button size="sm" variant="ghost" onClick={() => q.refetch()}>Tentar novamente</Button></p>}
      {h && !h.original && <p>Esta execução não possui configuração original de Valida Arquivo.</p>}
      {h?.original && !h.tentativas.length && <p>Nenhuma tentativa registrada ainda.</p>}
      {h?.conclusao && <p>Dependentes: {h.conclusao.liberar_dependentes ? 'liberação autorizada' : 'liberação bloqueada'} · Notificação: {h.conclusao.notificar ? 'habilitada' : 'dispensada'}.</p>}
      {h?.tentativas.map(t => <section key={`${t.task_id}-${t.tentativa}`} className="space-y-2 border-t border-edge pt-3">
        <h4 className="font-semibold">{t.task_id} · Tentativa {t.tentativa} · Revisão original {t.revisao}</h4>
        {t.resultado.entradas.map(e => {
          const original = h.validadores[t.task_id]?.entradas.find(x => x.entrada_id === e.entrada_id)
          return <div key={e.entrada_id} className="grid gap-1 border-b border-edge pb-2 sm:grid-cols-2">
            <div className="min-w-0"><p className="break-all font-medium">{original?.arquivo ?? e.entrada_id} → {e.alvo}</p>
              <p>{e.motivo}</p><p>{decisaoLabel[e.decisao] ?? e.decisao}</p></div>
            <div className="min-w-0 text-dim"><p>Linhas físicas: {e.linhas_fisicas ?? 'não se aplica'} · Registros considerados: {e.linhas ?? 'não disponível'}</p>
              {original && <p className="break-all">Caminho original: {original.caminho_resolvido || original.diretorio_literal || `parâmetro ${original.param_name}`} · Cabeçalho: {original.ignorar_cabecalho ? 'ignorado' : 'mantido'} · Ausente: {original.se_nao_existe} · Vazio: {original.se_zero_linhas}</p>}</div>
          </div>
        })}
      </section>)}
    </div>
  </details>
}
