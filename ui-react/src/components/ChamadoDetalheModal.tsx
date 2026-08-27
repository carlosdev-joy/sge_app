import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Paperclip } from 'lucide-react'
import { apiFetch } from '../lib/api'
import type { ChamadoDetalhe, NotaChamado, AnexoChamado } from '../lib/chamado'
import { isINCAtivo, formatBytes, formatDataNota } from '../lib/chamado'
import { Modal } from './ui/Modal'
import { Spinner } from './ui/Spinner'

interface Props {
  sysId: string
  numero: string
  onClose: () => void
}

const TIPO_NOTA_LABEL: Record<string, string> = {
  work_notes: 'notas internas',
  comments: 'comentários',
}

const ESTADO_LABEL: Record<string, string> = {
  novo: 'Em aberto',
  andamento: 'Em andamento',
  aguardando: 'Aguardando',
  resolvido: 'Resolvido',
  outros: 'Outros',
}

function NotaItem({ nota }: { nota: NotaChamado }) {
  return (
    <div className="rounded-md border border-[#2a2d3a] bg-[#12141e] p-3 flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2 text-[11px] text-[#94a3b8]">
        <span className="font-medium text-[#e2e8f0]">{nota.autor ?? '—'}</span>
        <span className="flex items-center gap-2">
          <span>{formatDataNota(nota.criado_em)}</span>
          <span className="px-1.5 py-0.5 rounded bg-[#1a1d27] border border-[#2a2d3a] text-[10px]">
            {TIPO_NOTA_LABEL[nota.tipo] ?? nota.tipo}
          </span>
        </span>
      </div>
      <p className="text-xs text-[#e2e8f0] whitespace-pre-wrap leading-relaxed">{nota.texto ?? '—'}</p>
    </div>
  )
}

function AnexoItem({ anexo }: { anexo: AnexoChamado }) {
  const isImagem = (anexo.mime_type ?? '').startsWith('image/')
  const url = `/orquestra${anexo.url_proxy}`
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-[#2a2d3a] bg-[#12141e] px-3 py-2 text-xs">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-base">{isImagem ? '🖼' : '📄'}</span>
        <span className="text-[#e2e8f0] truncate" title={anexo.nome_arquivo ?? undefined}>{anexo.nome_arquivo ?? 'anexo'}</span>
        <span className="text-[#64748b] shrink-0">{formatBytes(anexo.tamanho_bytes)}</span>
      </div>
      <a
        href={url}
        target={isImagem ? '_blank' : undefined}
        download={isImagem ? undefined : (anexo.nome_arquivo ?? true)}
        rel="noopener noreferrer"
        className="shrink-0 text-blue-400 hover:text-blue-300 transition-colors"
      >
        {isImagem ? 'ver' : 'baixar'}
      </a>
    </div>
  )
}

export function ChamadoDetalheModal({ sysId, numero, onClose }: Props) {
  const { data, isLoading, isError, error } = useQuery<ChamadoDetalhe>({
    queryKey: ['chamado-detalhe', sysId],
    queryFn: () => apiFetch<ChamadoDetalhe>(`/chamados/${sysId}/detalhe`),
    staleTime: 60_000,
  })

  const c = data?.chamado
  const incAtivo = c ? isINCAtivo(c) : false
  const titulo = c ? `${c.numero} · ${c.titulo ?? '(sem título)'}` : numero

  return (
    <Modal open onClose={onClose} title={titulo} size="lg">
      {isLoading && (
        <div className="flex justify-center py-10"><Spinner /></div>
      )}

      {isError && (
        <div className="rounded-md border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
          Erro ao carregar detalhes: {(error as Error).message}
        </div>
      )}

      {c && (
        <div className="flex flex-col gap-4 text-sm">
          {incAtivo && (
            <div className="rounded-md border border-red-800 bg-red-900/20 px-3 py-2 text-xs text-red-300 font-medium">
              Incidente ativo — acompanhe resolução
            </div>
          )}

          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
            <div className="text-[#94a3b8]">Analista: <span className="text-[#e2e8f0]">{c.atribuido_a ?? '—'}</span></div>
            <div className="text-[#94a3b8]">Grupo: <span className="text-[#e2e8f0]">{c.grupo ?? '—'}</span></div>
            <div className="text-[#94a3b8]">Estado: <span className="text-[#e2e8f0]">{ESTADO_LABEL[c.estado_kanban] ?? c.estado_kanban}</span></div>
            <div className="text-[#94a3b8]">Aberto: <span className="text-[#e2e8f0]">{formatDataNota(c.aberto_em)}</span></div>
          </div>

          {c.descricao && (
            <div className="flex flex-col gap-1">
              <h3 className="text-[10px] font-semibold text-[#94a3b8] uppercase tracking-wider">Descrição</h3>
              <p className="text-xs text-[#e2e8f0] whitespace-pre-wrap leading-relaxed bg-[#12141e] rounded-md border border-[#2a2d3a] p-3">{c.descricao}</p>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <h3 className="text-[10px] font-semibold text-[#94a3b8] uppercase tracking-wider">
              Histórico de notas {data!.notas.length > 0 ? `(${data!.notas.length})` : ''}
            </h3>
            {data!.notas.length === 0
              ? <p className="text-xs text-[#64748b]">Nenhuma nota registrada.</p>
              : data!.notas.map(n => <NotaItem key={n.sys_id_nota} nota={n} />)
            }
          </div>

          {data!.anexos.length > 0 && (
            <div className="flex flex-col gap-2">
              <h3 className="text-[10px] font-semibold text-[#94a3b8] uppercase tracking-wider flex items-center gap-1">
                <Paperclip size={11} /> Anexos ({data!.anexos.length})
              </h3>
              {data!.anexos.map(a => <AnexoItem key={a.sys_id_anexo} anexo={a} />)}
            </div>
          )}

          {c.url && (
            <a
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors self-start"
            >
              <ExternalLink size={12} /> Abrir no ServiceNow
            </a>
          )}
        </div>
      )}
    </Modal>
  )
}
