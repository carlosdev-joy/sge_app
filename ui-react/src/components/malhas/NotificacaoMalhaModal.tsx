// ── Configuração do nó NOTIFICAÇÃO da malha (087) ───────────────────────────
//
// O nó existia no canvas desde a F14 e não tinha tela: a API aceitava `titulo`
// e `mensagem`, ninguém preenchia, e todo aviso saía pelo canal global da
// supervisão — quem opera duas frentes recebia tudo no mesmo lugar.
//
// Aqui ele ganha canal, modelo e mensagem, e os três vêm do MESMO catálogo que
// o nó de Notificação das ETAPAS já usa (`/msg/grupos`, `/msg/templates`).
// Nenhum cadastro novo: canal, webhook e modelos têm tela e API próprias há
// muito tempo, e o que faltava era a malha poder apontar para eles.
//
// ⚠️ A PRÉVIA vem do SERVIDOR, e não é capricho: ela renderiza pela mesma
// função que a guardiã usa no envio. Uma prévia calculada aqui no front seria
// um segundo caminho para o mesmo texto — e o jeito de descobrir a divergência
// seria às 3h, com o card errado já no celular de quem está de plantão.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BellRing, Eye } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Input, Select, Textarea } from '../ui/Input'
import { PlaceholderPicker } from '../ui/PlaceholderPicker'
import { toast } from '../ui/Toast'

/** Os nomes que o editor oferece — o MESMO conjunto que o servidor conhece
 *  (`services/msg_texto.PLACEHOLDERS_MALHA`). Divergir aqui ofereceria um
 *  token que a emissão não substitui, e ele chegaria cru ao celular. */
const PLACEHOLDERS = ['malha', 'data', 'pipelines', 'ciclo', 'quantidade']

export interface ConfigNotificacao {
  titulo?: string | null
  mensagem?: string | null
  grupo_id?: number | null
  template_id?: number | null
}

interface Grupo { id: number; nome: string; ativo: number | boolean; has_webhook?: boolean }
interface Template { id: number; nome: string; titulo?: string | null; corpo?: string | null }
interface Previa {
  titulo: string
  corpo: string
  valores: Record<string, string | number>
  desconhecidos: string[]
}

export interface NotificacaoMalhaModalProps {
  malha: string
  config: ConfigNotificacao | null
  podeEditar: boolean
  onSalvar: (cfg: ConfigNotificacao) => Promise<void>
  onClose: () => void
}

export function NotificacaoMalhaModal({
  malha, config, podeEditar, onSalvar, onClose,
}: NotificacaoMalhaModalProps) {
  const [titulo, setTitulo] = useState(config?.titulo ?? '')
  const [mensagem, setMensagem] = useState(config?.mensagem ?? '')
  const [grupoId, setGrupoId] = useState<number | null>(config?.grupo_id ?? null)
  const [templateId, setTemplateId] = useState<number | null>(config?.template_id ?? null)
  const [salvando, setSalvando] = useState(false)
  const [previa, setPrevia] = useState<Previa | null>(null)
  const [carregandoPrevia, setCarregandoPrevia] = useState(false)
  const msgRef = useRef<HTMLTextAreaElement>(null)

  // Os canais cadastrados. Degrada para lista vazia (endpoint/tabela ausentes)
  // e a tela diz que não há canal — em vez de um select vazio sem explicação.
  const { data: gruposData } = useQuery<{ data: Grupo[] }>({
    queryKey: ['msg-grupos'],
    queryFn: () => apiFetch('/msg/grupos'),
    staleTime: 300_000,
  })
  const grupos = useMemo(
    () => (gruposData?.data ?? []).filter(g => !!g.ativo),
    [gruposData])

  // Modelos DO canal escolhido: o catálogo os organiza por grupo, e oferecer
  // modelo de outro canal seria oferecer uma escolha que o envio ignora.
  const { data: tplData } = useQuery<{ data: Template[] }>({
    queryKey: ['msg-templates', grupoId],
    queryFn: () => apiFetch(`/msg/templates?grupo_id=${grupoId}`),
    enabled: grupoId != null,
    staleTime: 300_000,
  })
  const templates = tplData?.data ?? []

  // A prévia acompanha o rascunho, com respiro: cada tecla é uma ida ao
  // servidor, e o texto é digitado palavra a palavra.
  useEffect(() => {
    const id = setTimeout(async () => {
      setCarregandoPrevia(true)
      try {
        const r = await apiFetch<Previa>(
          `/malhas/${encodeURIComponent(malha)}/notificacao/previa`,
          { method: 'POST', body: JSON.stringify({ config: { titulo, mensagem, template_id: templateId } }) })
        setPrevia(r)
      } catch {
        // Prévia é ajuda, não gesto: falhar aqui não pode travar a edição nem
        // gritar com quem está escrevendo. O card do fim da tela some.
        setPrevia(null)
      } finally {
        setCarregandoPrevia(false)
      }
    }, 400)
    return () => clearTimeout(id)
  }, [malha, titulo, mensagem, templateId])

  async function salvar() {
    setSalvando(true)
    try {
      await onSalvar({
        titulo: titulo.trim() || null,
        mensagem: mensagem.trim() || null,
        grupo_id: grupoId,
        template_id: templateId,
      })
      onClose()
    } catch (e) {
      toast.error(`Não foi possível salvar: ${(e as Error).message}`)
    } finally {
      setSalvando(false)
    }
  }

  const semCanal = grupos.length === 0

  return (
    <Modal open onClose={onClose} title="Notificação da malha" size="lg">
      <div className="flex flex-col gap-4">
        <p className="flex items-start gap-2 text-[12px] text-dim">
          <BellRing size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            O aviso deste nó sai quando todas as entradas dele concluem. Sem
            canal escolhido, ele segue o canal geral da malha.
          </span>
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-[12px] text-dim">
            Canal do Teams
            <Select
              value={grupoId ?? ''}
              disabled={!podeEditar || semCanal}
              onChange={e => {
                const v = e.target.value
                setGrupoId(v ? Number(v) : null)
                // Trocar de canal zera o modelo: templates pertencem ao grupo,
                // e manter o antigo deixaria um id que o envio não encontra.
                setTemplateId(null)
              }}
            >
              <option value="">canal geral da malha</option>
              {grupos.map(g => (
                <option key={g.id} value={g.id}>{g.nome}</option>
              ))}
            </Select>
            {semCanal && (
              <span className="text-[11px] text-amber-600 dark:text-amber-400">
                Nenhum canal cadastrado — cadastre em Avisos para escolher aqui.
              </span>
            )}
          </label>

          <label className="flex flex-col gap-1 text-[12px] text-dim">
            Modelo de mensagem
            <Select
              value={templateId ?? ''}
              disabled={!podeEditar || grupoId == null}
              onChange={e => {
                const v = e.target.value
                setTemplateId(v ? Number(v) : null)
              }}
            >
              <option value="">sem modelo</option>
              {templates.map(t => (
                <option key={t.id} value={t.id}>{t.nome}</option>
              ))}
            </Select>
            <span className="text-[11px] text-dim">
              {grupoId == null
                ? 'escolha um canal para ver os modelos'
                : 'o texto escrito abaixo vence o do modelo'}
            </span>
          </label>
        </div>

        <label className="flex flex-col gap-1 text-[12px] text-dim">
          Título
          <Input
            value={titulo}
            disabled={!podeEditar}
            maxLength={120}
            placeholder="ex.: Carga da madrugada concluída"
            onChange={e => setTitulo(e.target.value)}
          />
        </label>

        <label className="flex flex-col gap-1 text-[12px] text-dim">
          Mensagem
          <Textarea
            ref={msgRef}
            value={mensagem}
            disabled={!podeEditar}
            rows={4}
            maxLength={800}
            placeholder="ex.: A malha {malha} terminou em {data}. Pipelines: {pipelines}."
            onChange={e => setMensagem(e.target.value)}
          />
        </label>
        {podeEditar && (
          <PlaceholderPicker
            placeholders={PLACEHOLDERS}
            targetRef={msgRef}
            value={mensagem}
            onChange={setMensagem}
            label="inserir no texto"
          />
        )}

        {/* A PRÉVIA — o servidor renderizando pela mesma regra do envio. */}
        <div className="rounded-md border border-edge bg-canvas p-3">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-dim">
            <Eye size={12} aria-hidden="true" />
            Como chega no Teams
            {carregandoPrevia && <span className="opacity-60">· atualizando…</span>}
          </div>
          {previa ? (
            <>
              <div className="text-[13px] font-semibold text-ink">
                📣 {previa.titulo}
              </div>
              {previa.corpo && (
                <div className="mt-1 whitespace-pre-wrap text-[12px] text-ink">
                  {previa.corpo}
                </div>
              )}
              {previa.desconhecidos.length > 0 && (
                <div className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
                  {previa.desconhecidos.length === 1
                    ? `O campo {${previa.desconhecidos[0]}} não existe e vai sair assim mesmo, cru, no aviso.`
                    : `Os campos ${previa.desconhecidos.map(d => `{${d}}`).join(', ')} não existem e vão sair assim mesmo, crus, no aviso.`}
                </div>
              )}
              <div className="mt-2 text-[11px] text-dim">
                exemplo com os pipelines desta malha; a data é a do ciclo quando
                o aviso sair
              </div>
            </>
          ) : (
            <div className="text-[12px] text-dim">
              {carregandoPrevia ? 'montando…' : 'a prévia aparece quando houver texto'}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {podeEditar ? 'Cancelar' : 'Fechar'}
          </Button>
          {podeEditar && (
            <Button size="sm" loading={salvando} onClick={salvar}>
              Salvar
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
