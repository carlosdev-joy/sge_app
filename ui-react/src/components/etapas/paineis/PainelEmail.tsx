// ── Painel de um nó de E-MAIL ────────────────────────────────────────────────
// Spec docs/spec-notificacao-email.md (F2). Layout LARGO do dock inferior, o
// mesmo do painel de notificação: 2 colunas no lg+ — esquerda = identidade,
// destinatários e anexo; direita = assunto, corpo e placeholders.
//
// A régua (raízes de anexo permitidas, canal ligado) vem do Admin › E-mail por
// GET /email/status: o que a tela oferece é exatamente o que o envio aceita.
import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Node } from '@xyflow/react'
import { Mail, Paperclip, Trash2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select, Textarea } from '../../ui/Input'
import { PlaceholderPicker } from '../../ui/PlaceholderPicker'
import type { EmailNodeData } from '../EmailNode'
import { defaultEmailNo, errosDoEmailNo, EMAIL_PLACEHOLDERS, type EmailNoConfig } from '../fluxoTypes'
import { NomeField } from './shared'

interface EmailStatus {
  enabled: boolean
  limite_mb: number
  raizes: string[]
  dominios: string[]
  disponivel: boolean
}

export interface PainelEmailProps {
  node: Node
  onRename: (oldName: string, novo: string) => boolean
  onPatchEmail: (nodeId: string, patch: Partial<EmailNoConfig>) => void
  onDelete: (id: string) => void
}

export function PainelEmail({ node, onRename, onPatchEmail, onDelete }: PainelEmailProps) {
  const d = node.data as EmailNodeData
  const isNew = !!d.isNew
  const cfg = d.email ?? defaultEmailNo()
  const patch = (p: Partial<EmailNoConfig>) => onPatchEmail(node.id, p)
  const corpoRef = useRef<HTMLTextAreaElement>(null)
  const assuntoRef = useRef<HTMLInputElement>(null)

  // Régua do Admin. Degrada para desligado/sem raízes: a tela então explica o
  // que falta em vez de oferecer um anexo que o envio recusaria.
  const { data: status, isError: statusFalhou } = useQuery<EmailStatus>({
    queryKey: ['email-status'],
    queryFn: () => apiFetch('/email/status'),
    staleTime: 300_000,
  })
  const raizes = status?.raizes ?? []
  const erros = errosDoEmailNo(cfg, raizes)

  const anexoLigado = cfg.anexo != null
  function alternarAnexo(ligado: boolean) {
    patch({ anexo: ligado ? { raiz: raizes[0] ?? '', nome: '' } : null })
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        {/* teal-600: o glifo branco precisa de 3:1 (WCAG 1.4.11) — como no nó. */}
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-teal-600 text-white">
          <Mail size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">E-mail</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir e-mail
        </Button>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* ── Coluna esquerda: identidade, destinatários e anexo ──────────── */}
        <div className="flex min-w-0 flex-col gap-2">
          <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: AVISA_EQUIPE" onRename={onRename} />

          <div className="flex flex-col gap-1">
            <Textarea
              label="Destinatários"
              hint={'Um endereço por linha (ou separados por vírgula).\nPode ficar vazio se você herdar a lista do fluxo abaixo.'}
              value={cfg.destinatarios.join('\n')}
              rows={3}
              onChange={e => patch({
                destinatarios: e.target.value.split(/[\n,;]+/).map(x => x.trim()).filter(Boolean),
              })}
              placeholder={'ana@cvp.com.br\ncarlos@cvp.com.br'}
              className="text-xs"
            />
            <label className="flex cursor-pointer items-start gap-2 text-[11px] text-ink">
              <input
                type="checkbox"
                className="mt-0.5 h-3.5 w-3.5 rounded border-edge"
                checked={cfg.incluir_pipeline}
                onChange={e => patch({ incluir_pipeline: e.target.checked })}
              />
              <span>
                Incluir os destinatários do fluxo
                <span className="block text-[10px] text-dim/70">
                  Soma a lista cadastrada no fluxo (cadastro do pipeline › Destinatários de e-mail do fluxo), sem repetir endereço.
                </span>
              </span>
            </label>
            {status?.dominios?.length ? (
              <p className="text-[10px] text-dim/70">
                Domínios permitidos no Admin: {status.dominios.join(', ')}.
              </p>
            ) : null}
          </div>

          {/* ── Anexo: pasta da lista do Admin + nome livre ───────────────── */}
          <div className="flex flex-col gap-1.5 rounded-lg border border-edge p-2.5">
            <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-ink">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-edge"
                checked={anexoLigado}
                onChange={e => alternarAnexo(e.target.checked)}
                // Sem pasta liberada dá para DESMARCAR, nunca marcar: senão um
                // nó que já tem anexo ficaria sem como remover o anexo.
                disabled={raizes.length === 0 && !anexoLigado}
              />
              <Paperclip size={12} className="text-teal-600 dark:text-teal-300" />
              Anexar um arquivo do servidor
            </label>
            {raizes.length === 0 && !anexoLigado ? (
              <p className="text-[10px] text-dim/70">
                {statusFalhou
                  ? 'Não foi possível consultar as pastas liberadas agora — tente de novo em instantes.'
                  : 'Nenhuma pasta liberada para anexo — cadastre as pastas em Admin › E-mail.'}
              </p>
            ) : anexoLigado && cfg.anexo ? (
              <>
                <Select
                  label="Pasta"
                  hint="Apenas as pastas liberadas em Admin › E-mail aparecem aqui."
                  value={cfg.anexo.raiz}
                  onChange={e => patch({ anexo: { ...cfg.anexo!, raiz: e.target.value } })}
                  className="text-xs"
                >
                  {!raizes.includes(cfg.anexo.raiz) && (
                    <option value={cfg.anexo.raiz}>
                      {cfg.anexo.raiz || 'Selecione…'}{cfg.anexo.raiz ? ' (fora da lista)' : ''}
                    </option>
                  )}
                  {raizes.map(r => <option key={r} value={r}>{r}</option>)}
                </Select>
                <Input
                  label="Nome do arquivo"
                  hint={'O arquivo pode ainda não existir: ele costuma ser gerado pela própria corrida.\nAceita placeholders — ex.: relatorio_{odate}.xlsx'}
                  value={cfg.anexo.nome}
                  onChange={e => patch({ anexo: { ...cfg.anexo!, nome: e.target.value } })}
                  placeholder="relatorio_{odate}.xlsx"
                  className="text-xs"
                />
                <p className="text-[10px] text-dim/70">
                  Se o arquivo não estiver lá na hora do envio, o e-mail sai mesmo assim, sem anexo, e o log avisa.
                  Limite de {status?.limite_mb ?? 5} MB.
                </p>
              </>
            ) : null}
          </div>

          {status && !status.enabled && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              O canal de e-mail está desligado em Admin › E-mail. O nó fica salvo, mas a corrida vai pular este envio.
            </p>
          )}
          {erros.length > 0 && (
            <ul className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              {erros.map(e => <li key={e}>{e}</li>)}
            </ul>
          )}
        </div>

        {/* ── Coluna direita: assunto, corpo e placeholders ────────────────── */}
        <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-edge lg:pl-4">
          <div className="flex items-center gap-1.5">
            <Mail size={12} className="text-teal-600 dark:text-teal-300" />
            <span className="text-xs font-semibold text-ink">Mensagem</span>
          </div>

          <Input
            ref={assuntoRef}
            label="Assunto *"
            hint={'Aceita os placeholders do seletor abaixo.\nSem quebra de linha.'}
            value={cfg.assunto}
            onChange={e => patch({ assunto: e.target.value })}
            placeholder="[Orquestra] {pipeline} — {status}"
            className="text-xs"
          />

          <div className="flex flex-col gap-1">
            <Textarea
              ref={corpoRef}
              label="Corpo *"
              hint="Aceita os mesmos placeholders, trocados na hora do envio."
              value={cfg.corpo}
              rows={7}
              onChange={e => patch({ corpo: e.target.value })}
              placeholder="A carga {pipeline} terminou em {data} com {linhas} linhas."
              className="text-xs"
            />
            <PlaceholderPicker
              label="Inserir:"
              placeholders={EMAIL_PLACEHOLDERS}
              targetRef={corpoRef}
              value={cfg.corpo}
              onChange={v => patch({ corpo: v })}
            />
            <label className="flex cursor-pointer items-center gap-2 text-[11px] text-ink">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-edge"
                checked={cfg.html}
                onChange={e => patch({ html: e.target.checked })}
              />
              Corpo em HTML
            </label>
            <p className="text-[10px] text-dim/70">
              Com HTML ligado, quem não consegue ver HTML recebe a mesma mensagem sem as marcações.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
