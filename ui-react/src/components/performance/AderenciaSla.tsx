import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Download } from 'lucide-react'

// ── Aderência ao SLA — seção no fim de /performance ─────────────────────────
// Veio da aba Admin › Sistema › Relatório SLA (F4 de
// docs/spec-admin-reestruturacao.md, decisão §9.2: seção no FIM da tela, sem
// reordenar o que já existe acima). Mesma chamada (GET /execucoes/sla-report,
// que exige só login) e mesmo resultado; mudou só a moldura — painel, título e
// campos no padrão da tela Performance. Endereço antigo /admin/sistema/sla
// chega aqui por /performance#sla (a página rola até o `id` abaixo).
export const ANCORA_SLA = 'sla'

interface SlaRow {
  pipeline: string
  project: string
  criticidade: string
  sla_minutos: number | null
  total_exec: number
  exec_sucesso: number
  exec_falha: number
  exec_estouro_sla: number
  aderencia_sla_pct: number | null
  avg_dur_minutos: number
  max_dur_minutos: number
  ultima_exec: string | null
}

interface SlaReportData {
  periodo: { ini: string; fim: string }
  resumo: { total_pipelines: number; pipelines_com_sla: number; aderencia_media_pct: number | null }
  data: SlaRow[]
}

export function AderenciaSla() {
  // Período padrão: últimos 30 dias (calculado uma vez, na montagem).
  const [dateIni, setDateIni] = useState(() => new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10))
  const [dateFim, setDateFim] = useState(() => new Date().toISOString().slice(0, 10))
  const [project, setProject] = useState('')
  const [enabled, setEnabled] = useState(false)

  const { data, isFetching, isError, error, refetch } = useQuery<SlaReportData>({
    queryKey: ['sla-report', dateIni, dateFim, project],
    queryFn: () => {
      const p = new URLSearchParams({ date_ini: dateIni, date_fim: dateFim })
      if (project) p.set('project', project)
      return apiFetch(`/execucoes/sla-report?${p}`)
    },
    enabled,
    staleTime: 60_000,
  })

  function exportCsv() {
    if (!data?.data.length) return
    const esc = (v: string | number | null) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const header = ['Pipeline','Projeto','Criticidade','SLA (min)','Execuções','Sucesso','Falha',
      'Estouro SLA','Aderência %','Dur. Média (min)','Dur. Máx (min)','Última exec']
    const rows = data.data.map(r => [
      r.pipeline, r.project, r.criticidade, r.sla_minutos ?? '',
      r.total_exec, r.exec_sucesso, r.exec_falha, r.exec_estouro_sla,
      r.aderencia_sla_pct ?? 'N/A', r.avg_dur_minutos, r.max_dur_minutos, r.ultima_exec ?? '',
    ].map(esc).join(','))
    const csv = '﻿' + [header.map(esc).join(','), ...rows].join('\r\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = `sla_aderencia_${dateIni}_${dateFim}.csv`
    a.click()
  }

  const critColor = (c: string) => {
    const u = c.toUpperCase()
    if (u === 'ALTA' || u === 'CRITICA') return 'text-red-600 dark:text-red-400'
    if (u === 'MEDIA') return 'text-amber-600 dark:text-amber-400'
    return 'text-green-600 dark:text-green-400'
  }

  const adColor = (pct: number | null) => {
    if (pct === null) return 'text-dim'
    if (pct >= 95) return 'text-green-600 dark:text-green-400 font-semibold'
    if (pct >= 80) return 'text-amber-600 dark:text-amber-400 font-semibold'
    return 'text-red-600 dark:text-red-400 font-semibold'
  }

  return (
    <section id={ANCORA_SLA} aria-labelledby="sla-titulo"
      className="scroll-mt-4 bg-panel border border-edge rounded-lg p-4 flex flex-col gap-4" data-secao-sla>
      <div>
        <h2 id="sla-titulo" tabIndex={-1} className="text-base font-semibold text-ink focus:outline-none">
          Aderência ao SLA
        </h2>
        <p className="text-sm text-dim mt-1">Percentual de pipelines entregues dentro do SLA no período selecionado.</p>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-end">
        <Input label="De" type="date" value={dateIni} onChange={e => setDateIni(e.target.value)} className="w-40 h-9" />
        <Input label="Até" type="date" value={dateFim} onChange={e => setDateFim(e.target.value)} className="w-40 h-9" />
        <Input label="Projeto" placeholder="Todos" value={project} onChange={e => setProject(e.target.value)} className="w-40 h-9" />
        <div className="flex gap-2 items-end">
          <Button size="sm" onClick={() => { setEnabled(true); refetch() }} disabled={isFetching}>
            {isFetching ? 'Carregando…' : 'Gerar relatório'}
          </Button>
          {data && (
            <Button size="sm" variant="secondary" onClick={exportCsv}>
              <Download size={12} /> Exportar CSV
            </Button>
          )}
        </div>
      </div>

      {isError && (
        <div role="alert" className="text-sm text-red-700 border border-red-200 bg-red-50 dark:text-red-300 dark:bg-red-900/20 dark:border-red-800 rounded px-3 py-2">
          Erro: {(error as Error)?.message}
        </div>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div className="flex flex-wrap gap-2">
            {[
              { label: String(data.resumo.total_pipelines), sub: 'pipelines analisados' },
              { label: String(data.resumo.pipelines_com_sla), sub: 'com SLA definido' },
              {
                label: data.resumo.aderencia_media_pct != null ? `${data.resumo.aderencia_media_pct}%` : 'N/A',
                sub: 'aderência média ao SLA',
              },
            ].map(s => (
              <div key={s.sub} className="bg-canvas border border-edge rounded px-3 py-2 flex items-center gap-2">
                <strong className="text-ink text-sm font-bold">{s.label}</strong>
                <span className="text-dim text-xs">{s.sub}</span>
              </div>
            ))}
          </div>

          {/* Table */}
          <div className="overflow-x-auto rounded border border-edge">
            <table className="w-full text-xs">
              <thead className="bg-canvas border-b border-edge">
                <tr>
                  {['Pipeline','Projeto','Crit.','SLA','Execuções','Sucesso','Falha','Estouro','Aderência','Dur. Méd.','Dur. Máx.'].map(h => (
                    <th key={h} className="px-2 py-1.5 text-left text-dim font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.data.map(r => (
                  <tr key={r.pipeline} className="border-b border-edge/50 hover:bg-canvas transition-colors">
                    <td className="px-2 py-1.5 font-mono text-ink text-[11px]">{r.pipeline}</td>
                    <td className="px-2 py-1.5 text-dim">{r.project}</td>
                    <td className={`px-2 py-1.5 font-semibold text-[10px] ${critColor(r.criticidade)}`}>{r.criticidade}</td>
                    <td className="px-2 py-1.5 text-dim">{r.sla_minutos != null ? `${r.sla_minutos}min` : '—'}</td>
                    <td className="px-2 py-1.5 text-center text-ink">{r.total_exec}</td>
                    <td className="px-2 py-1.5 text-center text-green-600 dark:text-green-400">{r.exec_sucesso}</td>
                    <td className="px-2 py-1.5 text-center text-red-600 dark:text-red-400">{r.exec_falha || '—'}</td>
                    <td className="px-2 py-1.5 text-center text-amber-600 dark:text-amber-400">{r.exec_estouro_sla || '—'}</td>
                    <td className={`px-2 py-1.5 text-center ${adColor(r.aderencia_sla_pct)}`}>
                      {r.aderencia_sla_pct != null ? `${r.aderencia_sla_pct}%` : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-center text-dim">{r.avg_dur_minutos}min</td>
                    <td className="px-2 py-1.5 text-center text-dim">{r.max_dur_minutos}min</td>
                  </tr>
                ))}
                {data.data.length === 0 && (
                  <tr><td colSpan={11} className="px-2 py-8 text-center text-dim">Nenhuma execução no período.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
