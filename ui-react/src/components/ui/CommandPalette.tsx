import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { GitBranch, Briefcase, Database, Search } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Pipeline {
  pipeline_name: string
  project_name: string | null
  domain: string | null
}

interface Job {
  pipeline_name: string
  job_name: string
  job_type: string | null
}

interface CatalogPipeline {
  pipeline_name: string
  project_name: string | null
}

interface ResultItem {
  id: string
  label: string
  sub: string
  group: 'Pipelines' | 'Etapas' | 'Catálogo'
  href: string
}

// ── CommandPalette ────────────────────────────────────────────────────────────

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [cursor, setCursor] = useState(0)

  // Debounce
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 150)
    return () => clearTimeout(t)
  }, [query])

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery('')
      setDebounced('')
      setCursor(0)
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [open])

  const enabled = debounced.length >= 2

  const { data: pipelinesData } = useQuery<{ data: Pipeline[] }>({
    queryKey: ['cmd-pipelines', debounced],
    queryFn: () => apiFetch(`/pipelines?filter_name=${encodeURIComponent(debounced)}&limit=10`),
    enabled,
    staleTime: 30_000,
  })

  const { data: jobsData } = useQuery<{ data: Job[] }>({
    queryKey: ['cmd-jobs', debounced],
    queryFn: () => apiFetch(`/jobs?filter_job_name=${encodeURIComponent(debounced)}&limit=10`),
    enabled,
    staleTime: 30_000,
  })

  const { data: catalogData } = useQuery<{ pipelines?: CatalogPipeline[] }>({
    queryKey: ['cmd-catalog', debounced],
    queryFn: () =>
      apiFetch('/catalogo', {
        method: 'POST',
        body: JSON.stringify({ mode: 'list_pipelines' }),
      }),
    enabled,
    staleTime: 60_000,
    select: (d) => ({
      pipelines: (d.pipelines ?? [])
        .filter((p) => p.pipeline_name.toLowerCase().includes(debounced.toLowerCase()))
        .slice(0, 10),
    }),
  })

  // Build flat result list
  const items: ResultItem[] = []

  if (pipelinesData?.data) {
    for (const p of pipelinesData.data) {
      items.push({
        id: `pipeline-${p.pipeline_name}`,
        label: p.pipeline_name,
        sub: [p.project_name, p.domain].filter(Boolean).join(' · ') || 'Pipeline',
        group: 'Pipelines',
        href: `/pipelines`,
      })
    }
  }

  if (jobsData?.data) {
    for (const j of jobsData.data) {
      items.push({
        id: `job-${j.pipeline_name}-${j.job_name}`,
        label: j.job_name,
        sub: j.pipeline_name + (j.job_type ? ` · ${j.job_type}` : ''),
        group: 'Etapas',
        href: `/jobs`,
      })
    }
  }

  if (catalogData?.pipelines) {
    for (const c of catalogData.pipelines) {
      items.push({
        id: `cat-${c.pipeline_name}`,
        label: c.pipeline_name,
        sub: c.project_name ?? 'Catálogo',
        group: 'Catálogo',
        href: `/governanca`,
      })
    }
  }

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Não deixa o Esc vazar para o listener de documento do Modal — com
        // um modal aberto atrás da palette, fecharia os dois de uma vez.
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor((c) => Math.min(c + 1, items.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor((c) => Math.max(c - 1, 0))
      } else if (e.key === 'Enter' && items[cursor]) {
        navigate(items[cursor].href)
        onClose()
      }
    },
    [items, cursor, navigate, onClose]
  )

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.children[cursor] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  // Reset cursor when results change
  useEffect(() => { setCursor(0) }, [debounced])

  if (!open) return null

  const groupOrder: ResultItem['group'][] = ['Pipelines', 'Etapas', 'Catálogo']
  const groupIcons: Record<ResultItem['group'], React.ReactNode> = {
    Pipelines: <GitBranch size={12} />,
    Etapas: <Briefcase size={12} />,
    Catálogo: <Database size={12} />,
  }

  let flatIdx = 0

  return (
    <div
      // data-modal-exempt: overlay legítimo acima do Modal nativo — o
      // sentinela de foco do Modal ignora alvos aqui dentro (ver Modal.tsx).
      data-modal-exempt
      className="fixed inset-0 z-[9999] flex items-start justify-center pt-[10vh] p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Panel */}
      <div className="relative bg-panel border border-edge rounded-2xl shadow-2xl w-full max-w-lg flex flex-col overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-edge">
          <Search size={15} className="text-dim shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Buscar pipelines, jobs, catálogo…"
            className="flex-1 bg-transparent text-sm text-ink placeholder:text-dim outline-none"
          />
          <kbd className="text-[10px] text-dim border border-edge rounded px-1.5 py-0.5 shrink-0">ESC</kbd>
        </div>

        {/* Results */}
        <ul ref={listRef} className="max-h-[50vh] overflow-y-auto py-2">
          {!enabled && (
            <li className="px-4 py-8 text-center text-dim text-sm">
              Digite pelo menos 2 caracteres para buscar…
            </li>
          )}
          {enabled && items.length === 0 && (
            <li className="px-4 py-8 text-center text-dim text-sm">
              Nenhum resultado encontrado.
            </li>
          )}

          {enabled && groupOrder.map((group) => {
            const groupItems = items.filter((it) => it.group === group)
            if (groupItems.length === 0) return null
            return (
              <li key={group}>
                {/* Group label */}
                <div className="flex items-center gap-1.5 px-4 py-1.5 text-[10px] font-semibold text-dim uppercase tracking-widest">
                  {groupIcons[group]}
                  {group}
                </div>
                <ul>
                  {groupItems.map((item) => {
                    const idx = flatIdx++
                    const active = cursor === idx
                    return (
                      <li key={item.id}>
                        <button
                          className={`w-full flex items-center gap-3 px-4 py-2 text-left transition-colors ${
                            active
                              ? 'bg-blue-500/15 text-ink'
                              : 'text-ink hover:bg-edge/40'
                          }`}
                          onMouseEnter={() => setCursor(idx)}
                          onClick={() => { navigate(item.href); onClose() }}
                        >
                          <span className="text-sm font-medium truncate flex-1">{item.label}</span>
                          <span className="text-xs text-dim truncate max-w-[40%]">{item.sub}</span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </li>
            )
          })}
        </ul>

        {/* Footer hint */}
        {items.length > 0 && (
          <div className="px-4 py-2 border-t border-edge flex items-center gap-3 text-[10px] text-dim">
            <span><kbd className="border border-edge rounded px-1">↑↓</kbd> navegar</span>
            <span><kbd className="border border-edge rounded px-1">↵</kbd> abrir</span>
            <span><kbd className="border border-edge rounded px-1">esc</kbd> fechar</span>
          </div>
        )}
      </div>
    </div>
  )
}
