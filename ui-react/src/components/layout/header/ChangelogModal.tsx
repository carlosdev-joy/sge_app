import { useId, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, Tag } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { ORQUESTRA_NAME, ORQUESTRA_SUBTITLE } from '../Logo'
import { useOverlay, trapTabKey } from '../../ui/overlay'

interface VersaoEntry {
  id: number
  versao: string
  titulo: string
  descricao_md: string | null
  criado_em: string | null
  criado_por: string | null
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return ''
  return iso.substring(0, 10).split('-').reverse().join('/')
}

export function ChangelogModal({ onClose }: { onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  useOverlay(true, onClose, panelRef)
  const { data, isLoading } = useQuery<{ total: number; data: VersaoEntry[] }>({
    queryKey: ['versao'],
    queryFn: () => apiFetch('/versao'),
    staleTime: 300_000,
  })

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 nokey">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
        onKeyDown={e => trapTabKey(e, panelRef.current)}
        className="relative bg-panel border border-edge rounded-2xl shadow-2xl w-full max-w-xl flex flex-col max-h-[80vh] focus:outline-none">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-edge shrink-0">
          <div className="min-w-0">
            <h2 id={titleId} className="text-sm font-bold text-ink">Histórico de versões</h2>
            <p className="text-xs font-semibold text-ink mt-1">{ORQUESTRA_NAME}</p>
            <p className="text-[11px] text-dim mt-0.5">{ORQUESTRA_SUBTITLE}</p>
          </div>
          <button type="button" aria-label="Fechar histórico de versões" onClick={onClose} className="shrink-0 w-10 h-10 flex items-center justify-center text-dim hover:text-ink rounded hover:bg-edge/50 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-current">
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 px-5 py-4">
          {isLoading && (
            <div className="py-12 text-center text-dim text-sm">Carregando histórico…</div>
          )}
          {!isLoading && (!data?.data || data.data.length === 0) && (
            <div className="py-12 text-center text-dim text-sm">Nenhum registro de versão cadastrado.</div>
          )}
          {!isLoading && data?.data && data.data.length > 0 && (
            <div className="flex flex-col gap-5">
              {data.data.map((v, i) => (
                <div key={v.id} className="relative pl-6">
                  {/* Timeline line */}
                  {i < data.data.length - 1 && (
                    <div className="absolute left-[7px] top-5 bottom-[-1.25rem] w-px bg-edge/50" />
                  )}
                  {/* Dot */}
                  <div className={`absolute left-0 top-1 w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center ${i === 0 ? 'bg-blue-500 border-blue-400' : 'bg-canvas border-edge'}`} />

                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${i === 0 ? 'bg-blue-500/15 text-blue-400 border-blue-500/40' : 'bg-edge text-dim border-edge'}`}>
                        <Tag size={9} /> v{v.versao}
                      </span>
                      <span className="text-sm font-semibold text-ink">{v.titulo}</span>
                    </div>
                    <span className="text-[10px] text-dim whitespace-nowrap flex-shrink-0">{fmtDate(v.criado_em)}</span>
                  </div>

                  {v.descricao_md && (
                    <div className="text-xs text-dim leading-relaxed whitespace-pre-line mt-1 pl-0.5">
                      {v.descricao_md}
                    </div>
                  )}

                  {v.criado_por && (
                    <div className="text-[10px] text-dim/50 mt-1">por {v.criado_por}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-edge shrink-0 flex justify-end">
          <button type="button" onClick={onClose} className="min-h-9 text-xs text-dim hover:text-ink px-3 py-1.5 rounded border border-edge hover:bg-edge/50 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-current">
            Fechar
          </button>
        </div>
      </div>
    </div>
  )
}
