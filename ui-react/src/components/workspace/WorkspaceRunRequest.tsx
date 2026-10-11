import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Braces, Play } from 'lucide-react'
import { apiFetch, type ErroApi } from '../../lib/api'
import { STALE_INTENT_MESSAGE, advancedConfText, buildRunRequest, parseAdvancedConf, type RunRequestForm } from '../../lib/workspaceExecution'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'

type ErrorField = 'odate' | 'logicalDate' | 'conf' | 'runId' | 'request'
type FieldError = { field: ErrorField; message: string } | null
type Requested = { name: string; runId: string; state: string | null }
// Solicita uma corrida da configuração publicada. O identificador do pedido
// nasce com o diálogo e se repete em novas tentativas: o adaptador reconhece o
// mesmo pedido e não cria outra corrida. Fechar durante o envio não é permitido.
// `context` identifica o contexto exibido (sessão, pipeline, data, corrida,
// permissão; vazio com a aba fora de cena). O diálogo guarda o contexto em que
// abriu e confere antes do POST e antes de aplicar a resposta: desmontado ou
// noutro contexto, a resposta não seleciona nada.
export function WorkspaceRunRequest({ name, open, context, onClose, onRequested }: { name: string; open: boolean; context: string; onClose: () => void; onRequested: (run: Requested) => void }) {
 const busy = useRef(false)
 const close = () => { if (!busy.current) onClose() }
 return <Modal open={open} onClose={close} title="Executar a configuração publicada" size="lg">{open && <RunRequestForm name={name} context={context} onClose={close} onBusy={value => { busy.current = value }} onRequested={onRequested} />}</Modal>
}
function RunRequestForm({ name, context, onClose, onBusy, onRequested }: { name: string; context: string; onClose: () => void; onBusy: (busy: boolean) => void; onRequested: (run: Requested) => void }) {
 const id = useId()
 const [runId] = useState(() => `workspace__${crypto.randomUUID()}`)
 const [form, setForm] = useState<RunRequestForm>({ odate: '', logicalDate: '', extraConf: {} })
 const [advanced, setAdvanced] = useState<string | null>(null)
 const [error, setError] = useState<FieldError>(null)
 const [session] = useState(() => useAuthStore.getState().token)
 const [opened] = useState(context)
 const alive = useRef(true), current = useRef(context)
 useLayoutEffect(() => { current.current = context })
 useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
 const valid = () => alive.current && !!opened && current.current === opened && useAuthStore.getState().token === session
 const run = useMutation({
  onMutate: () => onBusy(true),
  onSettled: () => onBusy(false),
  mutationFn: async () => {
   // Sessão, permissão ou contexto mudaram com o diálogo aberto: nada é enviado.
   if (!valid()) throw Object.assign(new Error(STALE_INTENT_MESSAGE), { field: 'request', stale: true })
   let current = form
   if (advanced !== null) { const parsed = parseAdvancedConf(advanced); if (!parsed.ok) throw Object.assign(new Error(parsed.message), { field: 'conf' }); current = { ...form, odate: parsed.odate, extraConf: parsed.extraConf } }
   const built = buildRunRequest(current, runId)
   if (!built.ok) throw Object.assign(new Error(built.message), { field: built.field })
   return apiFetch<{ runId: string; state: string | null }>(`/workspace/runs?${new URLSearchParams({ name })}`, { method: 'POST', body: JSON.stringify(built.body) })
  },
  onSuccess: next => {
   const created = next.runId || runId
   // O contexto mudou durante o envio: a corrida existe, mas não é selecionada
   // na tela nova. Na mesma sessão, o aviso aponta onde encontrá-la.
   if (!valid()) { if (useAuthStore.getState().token === session) toast.info(`Execução solicitada (${created}) antes da mudança de tela; consulte pelo Histórico.`); return }
   onRequested({ name, runId: created, state: next.state ?? null })
  },
  onError: (e: Error) => {
   const field = (e as Error & { field?: ErrorField }).field, status = (e as ErroApi).status
   const message = field ? e.message : status === 403 ? 'Sua sessão não tem permissão para executar este pipeline.' : status === 409 ? `${e.message}. Nenhuma nova corrida foi criada.` : `${e.message || 'Não foi possível solicitar a execução'}. Você pode tentar novamente: o mesmo identificador evita corrida duplicada.`
   if (!alive.current) { if (useAuthStore.getState().token === session) toast.error(message); return }
   setError({ field: field ?? 'request', message })
  },
 })
 const describe = (field: string) => error?.field === field ? `${id}-${field}-erro` : undefined
 const fieldError = (field: string) => error?.field === field ? <p id={`${id}-${field}-erro`} className="text-xs text-red-700 dark:text-red-400">{error.message}</p> : null
 function toggleAdvanced() {
  if (advanced === null) { setAdvanced(advancedConfText(form)); setError(null); return }
  const parsed = parseAdvancedConf(advanced)
  if (!parsed.ok) { setError({ field: 'conf', message: parsed.message }); return }
  setForm(current => ({ ...current, odate: parsed.odate, extraConf: parsed.extraConf })); setAdvanced(null); setError(null)
 }
 const extraKeys = Object.keys(form.extraConf)
 return <form className="space-y-4" onSubmit={event => { event.preventDefault(); setError(null); run.mutate() }}>
  <p className="text-sm text-dim">Cria uma corrida no Airflow com a configuração publicada. O rascunho não é executado; publicar e executar são ações separadas. Uma DAG pausada continua aguardando ativação.</p>
  <dl className="grid gap-3 rounded-md border border-edge bg-canvas p-3 text-sm sm:grid-cols-2">
   <div><dt className="text-xs text-dim">Pipeline</dt><dd className="font-mono text-xs text-ink break-all mt-0.5">{name}</dd></div>
   <div><dt className="text-xs text-dim">Definição</dt><dd className="text-ink mt-0.5">Configuração publicada</dd></div>
   <div className="sm:col-span-2"><dt className="text-xs text-dim">Identificador da solicitação</dt><dd className="font-mono text-xs text-ink break-all mt-0.5">{runId}</dd><dd className="text-xs text-dim mt-1">Repetir o envio usa o mesmo identificador e não cria outra corrida.</dd></div>
  </dl>
  {advanced === null ? <div className="grid gap-3 sm:grid-cols-2">
   <div className="space-y-1"><Input label="Data de referência (ODATE)" type="date" value={form.odate} aria-invalid={error?.field === 'odate' || undefined} aria-describedby={describe('odate') ?? `${id}-odate-ajuda`} onChange={e => setForm(current => ({ ...current, odate: e.target.value }))} /><p id={`${id}-odate-ajuda`} className="text-xs text-dim">Opcional. Vazio: o motor calcula pela virada do pipeline.</p>{fieldError('odate')}</div>
   <div className="space-y-1"><Input label="Data lógica do Airflow (UTC)" type="datetime-local" step={1} value={form.logicalDate} aria-invalid={error?.field === 'logicalDate' || undefined} aria-describedby={describe('logicalDate') ?? `${id}-logical-ajuda`} onChange={e => setForm(current => ({ ...current, logicalDate: e.target.value }))} /><p id={`${id}-logical-ajuda`} className="text-xs text-dim">Opcional. Informada em UTC; vazio usa o horário do pedido.</p>{fieldError('logicalDate')}</div>
   {extraKeys.length > 0 && <p className="sm:col-span-2 text-xs text-dim">Também serão enviados os parâmetros avançados: {extraKeys.join(', ')}.</p>}
  </div> : <div className="space-y-1"><Textarea label="Parâmetros desta execução (JSON)" rows={8} value={advanced} aria-invalid={error?.field === 'conf' || undefined} aria-describedby={describe('conf')} onChange={e => setAdvanced(e.target.value)} className="font-mono text-xs" />{fieldError('conf')}<p className="text-xs text-dim">Chaves existentes são preservadas. data_referencia volta ao campo guiado.</p></div>}
  {fieldError('runId')}
  {error?.field === 'request' && <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">{error.message}</p>}
  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-edge pt-4">
   <Button type="button" variant="ghost" size="sm" disabled={run.isPending} aria-pressed={advanced !== null} onClick={toggleAdvanced}><Braces size={14} />{advanced === null ? 'Editar parâmetros em JSON' : 'Voltar ao formulário'}</Button>
   <div className="flex gap-2"><Button type="button" variant="secondary" disabled={run.isPending} onClick={onClose}>Cancelar</Button><Button type="submit" loading={run.isPending}><Play size={14} />{error?.field === 'request' ? 'Tentar novamente' : 'Confirmar execução'}</Button></div>
  </div>
 </form>
}
