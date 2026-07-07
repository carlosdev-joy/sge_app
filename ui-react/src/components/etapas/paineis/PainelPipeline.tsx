// ── Painel do PIPELINE (dock sem seleção) ────────────────────────────────────
// Benchmark Informatica: "o painel nunca é inútil" — sem nó selecionado, o dock
// inferior mostra as PROPRIEDADES DO PIPELINE (read-only; os metadados são
// editados no wizard de Pipelines), a contagem de nós do fluxo e a dica de uso
// do canvas. Layout no padrão dos demais painéis (fase 4): cabeçalho com chip +
// nome + subtítulo, e conteúdo em colunas no dock largo.
import { useQuery } from '@tanstack/react-query'
import { GitBranch, MousePointerClick } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import type { Pipeline } from '../../../types/pipeline'
import { SCHEDULE_LABELS, DOW_LABELS, critColor } from '../../pipelines/pipelineUtils'

// Contagem de nós por tipo — derivada do grafo VIVO no editor (inclui nós
// recém-criados ainda não salvos) e passada por prop.
export interface ContagemNos {
  etapas: number
  decisoes: number
  sql: number
  notificacoes: number
}

export interface PainelPipelineProps {
  pipeline: string
  contagem: ContagemNos
  // Espelha o modo do editor: sem paleta não faz sentido a dica de arrastar.
  readOnly?: boolean
}

// Agenda legível a partir dos campos de scheduling do registro (mesmos rótulos
// do wizard — SCHEDULE_LABELS/DOW_LABELS). Cobre os tipos persistidos e degrada
// para o rótulo cru quando o tipo é desconhecido.
function agendaLabel(p: Pipeline): string {
  const tipo = (p.schedule_type || 'daily').toLowerCase()
  const partes: string[] = [SCHEDULE_LABELS[tipo] ?? tipo]
  const hora = (p.scheduled_time || '').slice(0, 5)
    || (p.schedule_hour != null
      ? `${String(p.schedule_hour).padStart(2, '0')}:${String(p.schedule_minute ?? 0).padStart(2, '0')}`
      : '')
  if (tipo === 'weekly' && p.schedule_dow != null) {
    partes.push(DOW_LABELS.find(([n]) => n === p.schedule_dow)?.[1] ?? `dia ${p.schedule_dow}`)
  }
  if (tipo === 'monthly' && p.schedule_dom != null) partes.push(`dia ${p.schedule_dom}`)
  if (tipo === 'biweekly' && p.schedule_dom != null) partes.push(`dias ${p.schedule_dom} e ${p.schedule_dom + 15}`)
  if (tipo === 'custom' && p.horarios_especificos) partes.push(p.horarios_especificos)
  // Tipos sem hora única (sob demanda, N horas, custom, dia+hora) não anexam HH:MM.
  else if (!['on_demand', 'hourly_n', 'custom', 'monthly_days_times'].includes(tipo) && hora) {
    partes.push(hora)
  }
  if (p.somente_dias_uteis) partes.push('dias úteis')
  return partes.join(' · ')
}

// Um metadado do grid: rótulo pequeno em caps + valor (— quando ausente).
function Meta({ rotulo, className, children }: {
  rotulo: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-dim">{rotulo}</p>
      <p className={`truncate text-xs text-ink ${className ?? ''}`}>{children ?? '—'}</p>
    </div>
  )
}

export function PainelPipeline({ pipeline, contagem, readOnly = false }: PainelPipelineProps) {
  // MESMO endpoint/queryKey da biblioteca de Fluxos (pages/Fluxos.tsx): se o
  // usuário chegou filtrando pelo nome, o cache do TanStack já tem a resposta.
  // staleTime generoso — metadados do pipeline mudam raramente (wizard).
  const { data, isLoading } = useQuery<{ data: Pipeline[]; total: number }>({
    queryKey: ['fluxos-biblioteca', pipeline],
    queryFn: () => apiFetch(`/pipelines?limit=30&filter_name=${encodeURIComponent(pipeline)}`),
    enabled: !!pipeline,
    staleTime: 300_000,
  })
  // filter_name é LIKE %nome% — resolve o registro EXATO (fallback caso a base
  // devolva o nome com caixa diferente). Sem registro → degrada graciosamente:
  // o painel mostra só a contagem de nós e a dica (nunca quebra).
  const meta =
    data?.data.find(p => p.pipeline_name === pipeline)
    ?? data?.data.find(p => p.pipeline_name.toLowerCase() === pipeline.toLowerCase())
    ?? null

  const ativo = meta ? !!meta.active : null
  const totalNos = contagem.etapas + contagem.decisoes + contagem.sql + contagem.notificacoes

  return (
    <div className="flex flex-1 flex-col">
      {/* Cabeçalho — chip + nome do pipeline + subtítulo (padrão dos 4 painéis). */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#1A5FA8] text-white">
          <GitBranch size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate font-mono text-sm font-semibold text-ink">{pipeline}</p>
          <p className="text-[11px] text-dim">Pipeline</p>
        </div>
        {ativo != null && (
          <span
            className={[
              'ml-auto shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold',
              ativo
                ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/30 dark:text-green-300'
                : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
            ].join(' ')}
          >
            {ativo ? 'ativo' : 'inativo'}
          </span>
        )}
      </div>

      {/* 3 colunas no lg+: metadados (2 colunas) + contagem/dica à direita. */}
      <div className="grid gap-4 p-4 lg:grid-cols-3">
        {/* ── Metadados do pipeline (read-only — edição no wizard) ─────────── */}
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
          {meta ? (
            <>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                <Meta rotulo="Agenda">{agendaLabel(meta)}</Meta>
                <Meta rotulo="Projeto">{meta.project_name || '—'}</Meta>
                <Meta rotulo="Domínio">{meta.domain || '—'}</Meta>
                <Meta rotulo="Ambiente">{meta.ambiente || '—'}</Meta>
                <Meta rotulo="Criticidade" className={`font-medium ${critColor(meta.criticidade)}`}>
                  {meta.criticidade || '—'}
                </Meta>
                <Meta rotulo="Última execução">{meta.last_execution || '—'}</Meta>
              </div>
              {meta.descricao && (
                <p className="line-clamp-2 border-t border-edge pt-2 text-[11px] leading-relaxed text-dim">
                  {meta.descricao}
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-dim">
              {isLoading
                ? 'Carregando os metadados do pipeline…'
                : 'Metadados do pipeline indisponíveis no momento.'}
            </p>
          )}
          <p className="mt-auto text-[10px] text-dim/70">
            Metadados do pipeline (agenda, projeto, criticidade…) são editados no cadastro de Pipelines.
          </p>
        </div>

        {/* ── Contagem de nós + dica de uso do canvas ──────────────────────── */}
        <div className="flex min-w-0 flex-col gap-3 lg:border-l lg:border-edge lg:pl-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-dim">Neste fluxo</p>
            <p className="mt-1 text-xs text-ink">
              {totalNos === 0 ? (
                'Nenhum nó ainda — o canvas está vazio.'
              ) : (
                <>
                  <strong>{contagem.etapas}</strong> etapa{contagem.etapas !== 1 ? 's' : ''}
                  {' · '}<strong>{contagem.decisoes}</strong> decis{contagem.decisoes !== 1 ? 'ões' : 'ão'}
                  {' · '}<strong>{contagem.sql}</strong> SQL
                  {' · '}<strong>{contagem.notificacoes}</strong> notificaç{contagem.notificacoes !== 1 ? 'ões' : 'ão'}
                </>
              )}
            </p>
          </div>
          <div className="flex items-start gap-2 rounded-lg border border-edge bg-canvas/60 px-3 py-2.5">
            <MousePointerClick size={14} className="mt-0.5 shrink-0 text-dim/70" />
            <p className="text-[11px] leading-relaxed text-dim">
              Clique em uma etapa ou decisão no canvas para editar suas propriedades —
              <strong className="text-ink"> duplo-clique</strong> abre o modo focado.
              {!readOnly && (
                <>
                  {' '}Para criar um novo nó,
                  <strong className="text-ink"> arraste </strong>
                  um tipo da paleta (à esquerda) para o canvas.
                </>
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
