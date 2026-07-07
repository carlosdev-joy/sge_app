// ── Painel de uma NOTIFICAÇÃO (Teams) ────────────────────────────────────────
// Fase 4 do redesign: layout LARGO para o dock inferior — 2 colunas no lg+
// (esquerda = identidade + canal/modelo; direita = mensagem + placeholders).
import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Node } from '@xyflow/react'
import { BellRing, Trash2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Select, Textarea } from '../../ui/Input'
import { PlaceholderPicker } from '../../ui/PlaceholderPicker'
import type { NotificacaoNodeData } from '../NotificacaoNode'
import { defaultNotify, type NotifyConfig, type MsgGrupo, type MsgTemplate } from '../fluxoTypes'
import { NomeField } from './shared'

export interface PainelNotificacaoProps {
  node: Node
  grupos: MsgGrupo[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchNotify: (nodeId: string, patch: Partial<NotifyConfig>) => void
  onDelete: (id: string) => void
}

export function PainelNotificacao({ node, grupos, onRename, onPatchNotify, onDelete }: PainelNotificacaoProps) {
  const d = node.data as NotificacaoNodeData
  const isNew = !!d.isNew
  const cfg = d.notify ?? defaultNotify()
  const patch = (p: Partial<NotifyConfig>) => onPatchNotify(node.id, p)
  const msgRef = useRef<HTMLTextAreaElement>(null)

  // Templates do grupo selecionado (Select "Modelo"). Sem grupo → não busca.
  // Degrada para [] se a tabela/endpoint não existir (try/except no backend).
  const { data: tplData } = useQuery<{ data: MsgTemplate[] }>({
    queryKey: ['msg-templates', cfg.grupo_id],
    queryFn: () => apiFetch(`/msg/templates?grupo_id=${cfg.grupo_id}`),
    enabled: cfg.grupo_id != null,
    staleTime: 300_000,
  })
  const templates = tplData?.data ?? []

  // Troca de grupo: zera o modelo (templates pertencem ao grupo).
  function onGrupoChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value
    patch({ grupo_id: v ? Number(v) : null, template_id: null })
  }

  return (
    <div className="flex flex-1 flex-col">
      {/* Cabeçalho do painel — o Excluir mora no topo direito (mesmo padrão
          nos 4 painéis). */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-teal-500 text-white">
          <BellRing size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">Notificação (Teams)</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir notificação
        </Button>
      </div>

      {/* 2 colunas no lg+: esquerda = identidade + canal/modelo; direita = mensagem. */}
      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* ── Coluna esquerda: identidade + canal/modelo ──────────────────── */}
        <div className="flex min-w-0 flex-col gap-2">
          <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: AVISA_TIME" onRename={onRename} />

          <div className="flex flex-col gap-1">
            <Select
              label="Grupo (canal) *"
              value={cfg.grupo_id != null ? String(cfg.grupo_id) : ''}
              onChange={onGrupoChange}
              className="text-xs"
            >
              <option value="">Selecione um canal…</option>
              {grupos.map(g => (
                <option key={g.id} value={g.id}>{g.nome}</option>
              ))}
              {/* Mantém o grupo salvo visível mesmo se ele não estiver mais na lista */}
              {cfg.grupo_id != null && !grupos.some(g => g.id === cfg.grupo_id) && (
                <option value={cfg.grupo_id}>#{cfg.grupo_id} (fora da lista)</option>
              )}
            </Select>
            {grupos.length === 0 && (
              <p className="text-[10px] text-dim/70">
                Nenhum canal cadastrado — crie um em Mensagens (Teams) antes de notificar.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <Select
              label="Modelo (opcional)"
              value={cfg.template_id != null ? String(cfg.template_id) : ''}
              onChange={e => patch({ template_id: e.target.value ? Number(e.target.value) : null })}
              disabled={cfg.grupo_id == null}
              className={`text-xs ${cfg.grupo_id == null ? 'opacity-60' : ''}`}
            >
              <option value="">Nenhum (mensagem livre)</option>
              {templates.map(t => (
                <option key={t.id} value={t.id}>{t.nome}</option>
              ))}
              {/* Mantém o modelo salvo visível mesmo se ele não estiver na lista atual */}
              {cfg.template_id != null && !templates.some(t => t.id === cfg.template_id) && (
                <option value={cfg.template_id}>#{cfg.template_id} (fora da lista)</option>
              )}
            </Select>
            {cfg.grupo_id == null
              ? <p className="text-[10px] text-dim/70">Escolha um canal para listar os modelos.</p>
              : templates.length === 0 && (
                <p className="text-[10px] text-dim/70">Nenhum modelo neste canal — use a mensagem abaixo.</p>
              )}
          </div>

          {/* Aviso quando falta o canal (grupo_id obrigatório no save). */}
          {cfg.grupo_id == null && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              Selecione um canal (grupo) antes de salvar o fluxo.
            </p>
          )}
        </div>

        {/* ── Coluna direita: mensagem (corpo livre + placeholders) ───────── */}
        <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-edge lg:pl-4">
          <div className="flex items-center gap-1.5">
            <BellRing size={12} className="text-teal-600 dark:text-teal-300" />
            <span className="text-xs font-semibold text-ink">Mensagem do Teams</span>
          </div>

          <div className="flex flex-col gap-1">
            <Textarea
              ref={msgRef}
              label="Mensagem (opcional)"
              value={cfg.mensagem ?? ''}
              rows={7}
              onChange={e => patch({ mensagem: e.target.value })}
              placeholder="ex: Pipeline {pipeline} concluído com status {status}."
              className="text-xs"
            />
            <p className="text-[10px] text-dim/70">Vazio = usa o corpo do modelo.</p>
            <PlaceholderPicker
              label="Inserir:"
              placeholders={['pipeline', 'job', 'linhas', 'status', 'data']}
              targetRef={msgRef}
              value={cfg.mensagem ?? ''}
              onChange={v => patch({ mensagem: v })}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
