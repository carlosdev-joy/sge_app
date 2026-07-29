import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { ChevronDown, ChevronUp, ShieldCheck } from 'lucide-react'

// ── Supervisão DataStage no dashboard (F3) ──────────────────────────────────
// Lê só do banco (nenhum SSH no carregamento) e segue a data escolhida na
// toolbar do dashboard: trocar o dia mostra o histórico daquele dia.

interface SupervisaoRun {
  inicio: string | null
  fim: string | null
  duracao_seg: number | null
  resultado: string
  jobs_filhos: number | null
}

interface SupervisaoEvento {
  tipo: string
  detalhe: string | null
  detectado_em: string | null
  notificado_em: string | null
}

interface SupervisaoItem {
  id: number
  project: string
  job_name: string
  janela_inicio: string
  janela_fim: string
  dias_semana: string
  ativo: boolean
  vigencia_inicio: string
  previsto: boolean
  estado: string
  runs: SupervisaoRun[]
  eventos: SupervisaoEvento[]
}

interface SupervisaoResposta {
  date_ref: string
  data: SupervisaoItem[]
  resumo: { total: number; com_alerta: number }
}

// Rótulo + variante de cor por estado. O rótulo é TEXTO, não só cor: quem não
// distingue vermelho de âmbar precisa ler o que está acontecendo.
const ESTADO: Record<string, { label: string; badge: string }> = {
  sem_verificacao: { label: 'Sem verificação', badge: 'warning' },
  abortado:        { label: 'Abortou',         badge: 'error' },
  nao_executou:    { label: 'Não executou',    badge: 'error' },
  atrasado:        { label: 'Atrasado',        badge: 'warning' },
  executando:      { label: 'Em execução',     badge: 'info' },
  ok:              { label: 'Concluído',       badge: 'success' },
  sem_registro:    { label: 'Sem registro',    badge: 'neutral' },
}

const COM_ALERTA = new Set(['sem_verificacao', 'abortado', 'nao_executou', 'atrasado'])

// Cada evento é colorido pelo PRÓPRIO tipo, não pelo estado agregado do job:
// num dia com ATRASO e depois ABORTOU, os dois apareceriam vermelhos se
// usássemos o estado do job, escondendo qual foi qual.
const EVENTO: Record<string, { label: string; badge: string }> = {
  ABORTOU:          { label: 'Abortou',                badge: 'error' },
  NAO_EXECUTOU:     { label: 'Não executou',           badge: 'error' },
  ATRASO:           { label: 'Atrasado',               badge: 'warning' },
  ESTRUTURA:        { label: 'Sem verificação',        badge: 'warning' },
  SITUACAO_INICIAL: { label: 'Início do monitoramento', badge: 'info' },
}

/** '2026-07-29 02:10:15' → '02:10' */
function hora(iso: string | null): string {
  if (!iso) return '—'
  const parte = iso.split(' ')[1] ?? iso.split('T')[1]
  return parte ? parte.slice(0, 5) : '—'
}

function duracao(seg: number | null): string {
  if (seg == null) return ''
  const h = Math.floor(seg / 3600)
  const m = Math.floor((seg % 3600) / 60)
  return h ? `${h}h${String(m).padStart(2, '0')}m` : `${m}min`
}

function hhmm(valor: string): string {
  return (valor || '').slice(0, 5)
}

export function SupervisaoCard({ date }: { date: string }) {
  const [aberto, setAberto] = useState<number | null>(null)

  const { data, isLoading, isError } = useQuery<SupervisaoResposta>({
    queryKey: ['dashboard-supervisao', date],
    queryFn: () => apiFetch(`/dashboard/supervisao?date_ref=${date}`),
  })

  // Falha de rede não deve deixar um bloco quebrado no meio do dashboard.
  if (isError) return null

  // Quem precisa de ação primeiro aparece primeiro; o resto mantém a ordem
  // alfabética que o servidor já devolve.
  const itens = [...(data?.data ?? [])].sort(
    (a, b) => Number(COM_ALERTA.has(b.estado)) - Number(COM_ALERTA.has(a.estado)))
  const comAlerta = data?.resumo.com_alerta ?? 0

  return (
    <div className="bg-panel border border-edge rounded-xl overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-edge">
        <ShieldCheck size={16} className="text-dim shrink-0" />
        <h2 className="text-sm font-semibold text-ink">Supervisão DataStage</h2>
        {itens.length > 0 && (
          <Badge value={comAlerta > 0 ? 'error' : 'success'}>
            {comAlerta > 0
              ? `${comAlerta} de ${itens.length} com problema`
              : `${itens.length} sem problema`}
          </Badge>
        )}
        <span className="ml-auto text-[11px] text-dim">{data?.date_ref ?? date}</span>
      </div>

      {isLoading && <p className="px-4 py-6 text-xs text-dim">Carregando…</p>}

      {!isLoading && itens.length === 0 && (
        <div className="px-4 py-8 flex flex-col items-center gap-1.5 text-center">
          {/* Jobs ativos vêm sempre, independente da data: lista vazia significa
              cadastro vazio, não dia sem dados. A mensagem tem de dizer isso. */}
          <p className="text-sm text-ink font-medium">Nenhum job supervisionado cadastrado</p>
          <p className="text-xs text-dim">
            Cadastre os jobs na aba <strong>Supervisão</strong> do{' '}
            <Link to="/ds-console" className="text-blue-600 dark:text-blue-400 underline underline-offset-2">
              Console DataStage
            </Link>
            .
          </p>
        </div>
      )}

      {!isLoading && itens.length > 0 && (
        <ul className="divide-y divide-edge">
          {itens.map(item => {
            const estado = ESTADO[item.estado] ?? ESTADO.sem_registro
            const alerta = COM_ALERTA.has(item.estado)
            const expandido = aberto === item.id
            const ultimo = item.runs[item.runs.length - 1]
            return (
              <li key={item.id} className={alerta ? 'bg-red-50/40 dark:bg-red-900/10' : ''}>
                <button
                  onClick={() => setAberto(expandido ? null : item.id)}
                  aria-expanded={expandido}
                  className="w-full flex flex-wrap items-center gap-2 px-4 py-2.5 text-left hover:bg-edge/30 transition-colors"
                >
                  {expandido
                    ? <ChevronUp size={14} className="text-dim shrink-0" />
                    : <ChevronDown size={14} className="text-dim shrink-0" />}
                  <span className="font-mono text-[11px] text-ink break-all">
                    {item.project}.{item.job_name}
                  </span>
                  {!item.ativo && <Badge value="inativo">fora da supervisão</Badge>}
                  {!item.previsto
                    ? <Badge value="neutral">não previsto neste dia</Badge>
                    : <Badge value={estado.badge}>{estado.label}</Badge>}
                  <span className="text-[11px] text-dim">
                    janela {hhmm(item.janela_inicio)}–{hhmm(item.janela_fim)}
                  </span>
                  {ultimo && (
                    <span className="ml-auto text-[11px] text-dim">
                      {hora(ultimo.inicio)} → {hora(ultimo.fim)} {duracao(ultimo.duracao_seg)}
                    </span>
                  )}
                </button>

                {expandido && (
                  <div className="px-4 pb-3 pt-0.5 flex flex-col gap-2 border-t border-edge/60">
                    {item.eventos.length > 0 && (
                      <div className="flex flex-col gap-1 mt-2">
                        {item.eventos.map((ev, i) => (
                          <div key={i} className="flex flex-wrap items-baseline gap-2">
                            <Badge value={EVENTO[ev.tipo]?.badge ?? 'neutral'}>
                              {EVENTO[ev.tipo]?.label ?? ev.tipo}
                            </Badge>
                            <span className="text-[11px] text-ink">{ev.detalhe}</span>
                            {ev.notificado_em
                              ? <span className="text-[10px] text-dim">avisado {hora(ev.notificado_em)}</span>
                              : <span className="text-[10px] text-dim">ainda não avisado</span>}
                          </div>
                        ))}
                      </div>
                    )}

                    {item.runs.length > 0 ? (
                      <table className="text-[11px] w-full mt-1">
                        <thead>
                          <tr className="text-dim text-left">
                            <th className="font-medium py-1">Início</th>
                            <th className="font-medium py-1">Fim</th>
                            <th className="font-medium py-1">Duração</th>
                            <th className="font-medium py-1">Resultado</th>
                            <th className="font-medium py-1">Jobs</th>
                          </tr>
                        </thead>
                        <tbody className="text-ink">
                          {item.runs.map((r, i) => (
                            <tr key={i} className="border-t border-edge/40">
                              <td className="py-1">{hora(r.inicio)}</td>
                              <td className="py-1">{hora(r.fim)}</td>
                              <td className="py-1">{duracao(r.duracao_seg) || '—'}</td>
                              <td className="py-1">{r.resultado}</td>
                              <td className="py-1">{r.jobs_filhos ?? '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p className="text-[11px] text-dim mt-1">
                        Nenhuma execução registrada neste dia.
                      </p>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
