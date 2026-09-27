import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { erroCatalogo } from '../../lib/pipelineCatalogo'
import { Button } from '../ui/Button'

interface Politica { disponivel: boolean; revisao: number; liberar_dependentes: boolean; notificar: boolean }
export function PoliticaSemMovimento({ pipeline }: { pipeline: string }) {
  const endpoint = `/pipelines/${encodeURIComponent(pipeline)}/politica-sem-movimento`
  const q = useQuery<Politica>({ queryKey: ['politica-sem-movimento', pipeline], queryFn: () => apiFetch(endpoint) })
  const [draft, setDraft] = useState<Politica | null>(null)
  const [mensagem, setMensagem] = useState('')
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const p = draft ?? q.data
  async function salvar() {
    if (!p) return
    setOcupado(true); setErro(''); setMensagem('')
    try {
      const r = await apiFetch<{ revisao: number }>(endpoint, { method: 'PUT', body: JSON.stringify(p) })
      setDraft({ ...p, revisao: r.revisao }); setMensagem('Política salva para novas execuções.'); void q.refetch()
    } catch (e) { setErro(erroCatalogo(e)) } finally { setOcupado(false) }
  }
  return <section className="space-y-3 border-t border-edge pt-4 text-xs text-ink" aria-label="Conclusão sem movimento">
    <h3 className="text-sm font-semibold">Quando todos os destinos forem pulados</h3>
    <p className="leading-relaxed text-dim">A execução registra “Concluído sem movimento”. O histórico é sempre mantido; estas opções controlam a liberação dos pipelines dependentes e a notificação.</p>
    {q.isLoading && <p role="status">Carregando política…</p>}
    {q.isError && <p role="alert">Não foi possível carregar a política. <Button size="sm" variant="ghost" onClick={() => q.refetch()}>Tentar novamente</Button></p>}
    {p?.disponivel === false && <p>Configuração indisponível. Aplique a migration 132.</p>}
    {p?.disponivel && <fieldset disabled={ocupado} className="space-y-3">
      <label className="flex items-start gap-2"><input type="checkbox" checked={p.liberar_dependentes} onChange={e => { setDraft({ ...p, liberar_dependentes: e.target.checked }); setMensagem('') }} />Liberar pipelines dependentes mesmo sem movimento</label>
      <label className="flex items-start gap-2"><input type="checkbox" checked={p.notificar} onChange={e => { setDraft({ ...p, notificar: e.target.checked }); setMensagem('') }} />Enviar notificação de conclusão sem movimento</label>
      <p className="text-dim">Falha técnica sempre bloqueia a liberação. Retomadas mantêm a política original.</p>
      <div className="flex flex-wrap gap-2"><Button size="sm" loading={ocupado} onClick={salvar}>Salvar política</Button><Button size="sm" variant="ghost" onClick={async () => { await q.refetch(); setDraft(null); setErro(''); setMensagem('') }}>Recarregar política</Button></div>
    </fieldset>}
    {erro && <p role="alert" className="text-red-700 dark:text-red-300">{erro}</p>}
    {mensagem && <p role="status">{mensagem}</p>}
  </section>
}
