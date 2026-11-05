// Admin › Inteligência Artificial › Agentes › Terminal — abas "Bancos" e "Auditoria" (spec docs/spec-agente-terminal.md, F5).
//
// Bancos: os pares conexão/banco que o Terminal consulta (só-SELECT), o mesmo seletor dos agentes da tela (`BancosLiberados`) e a
// mesma conferência no servidor ao salvar; a máscara de dados pessoais e a retenção da auditoria (180 dias por padrão).
// Auditoria: cada comando que o Terminal executou, propôs ou bloqueou — quem pediu, onde, o que (já redigido) e como terminou.
// Cores: tokens do tema + pares claro/escuro (docs/ui-temas-cores.md).
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import type { BancoLiberado } from '../../lib/agentes'
import { mensagemDeErro } from '../../lib/agentes'
import { ROTULO_ESTADO } from '../../lib/terminalComando'
import { BancosLiberados } from './BancosLiberados'
import { toast } from '../ui/Toast'

function paresDaConfig(bruto: string | undefined): BancoLiberado[] {
  try {
    const v = JSON.parse(bruto || '[]')
    return Array.isArray(v) ? v.filter(p => p && typeof p.conexao === 'string' && typeof p.banco === 'string') : []
  } catch {
    return []
  }
}

export function TerminalBancos({ config, onSalvo }: { config: Record<string, string>; onSalvo: () => Promise<void> | void }) {
  const [pares, setPares] = useState<BancoLiberado[]>(() => paresDaConfig(config.agente_terminal_bancos))
  const [mascarar, setMascarar] = useState((config.agente_terminal_mascarar ?? '1') !== '0')
  const [retencao, setRetencao] = useState(config.agente_terminal_retencao_dias ?? '180')
  const salvar = useMutation({
    mutationFn: async () => {
      const r = await apiFetch<{ avisos: string[] }>('/agentes/admin/terminal/bancos', {
        method: 'PUT', body: JSON.stringify({ bancos: pares, mascarar_dados: mascarar }),
      })
      try {
        await apiFetch('/agentes/admin/config', { method: 'POST', body: JSON.stringify({ agente_terminal_retencao_dias: Number(retencao) }) })
      } catch (e) {
        // Os bancos JÁ foram salvos: a mensagem não pode dizer que nada foi salvo.
        throw new Error(`Bancos salvos; a retenção NÃO foi salva: ${mensagemDeErro(e, 'erro desconhecido')}`, { cause: e })
      }
      return r
    },
    onSuccess: async r => {
      toast.success('Bancos e retenção do Terminal salvos')
      r.avisos?.forEach(a => toast.info(a))
      await onSalvo()
    },
    onError: e => toast.error(mensagemDeErro(e, 'Não foi possível salvar')),
  })
  const retencaoValida = /^\d+$/.test(retencao) && Number(retencao) >= 30 && Number(retencao) <= 3650
  return (
    <div className="flex flex-col gap-4 max-w-3xl" data-terminal-admin-bancos>
      <section className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold text-ink">Bancos que o Terminal consulta</h4>
        <p className="text-xs text-dim">Só consultas (SELECT), garantidas pelo plano do SQL Server. Sem nenhum banco marcado, o Terminal não oferece consulta a banco.</p>
        <BancosLiberados pares={pares} onPares={setPares} />
        <label className="flex items-center gap-2 text-xs text-ink">
          <input type="checkbox" checked={mascarar} onChange={() => setMascarar(m => !m)} />
          Mascarar dados pessoais nos resultados (CPF, e-mail, telefone…)
        </label>
      </section>
      <section className="flex flex-col gap-1">
        <label htmlFor="terminal-retencao" className="text-sm font-semibold text-ink">Retenção da auditoria (dias)</label>
        <input id="terminal-retencao" inputMode="numeric" value={retencao} onChange={e => setRetencao(e.target.value.trim())}
               aria-invalid={!retencaoValida} aria-describedby="terminal-retencao-ajuda"
               className="h-9 w-32 rounded-md border border-edge bg-panel text-ink text-sm px-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]" />
        <p id="terminal-retencao-ajuda" className={`text-xs ${retencaoValida ? 'text-dim' : 'text-red-700 dark:text-red-400'}`}>
          {retencaoValida ? 'Comandos encerrados há mais tempo que isso são apagados automaticamente (entre 30 e 3650).' : 'Informe um número entre 30 e 3650.'}
        </p>
      </section>
      <div>
        <button type="button" disabled={salvar.isPending || !retencaoValida} onClick={() => salvar.mutate()}
                className="h-9 px-4 rounded-md bg-[#1A5FA8] text-white text-sm font-medium hover:bg-[#164f8c] disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8] focus-visible:ring-offset-2">
          {salvar.isPending ? 'Salvando…' : 'Salvar'}
        </button>
      </div>
    </div>
  )
}

interface LinhaAuditoria {
  cmd_id: string; conversa_id: string | null; matricula: string; servidor: string; comando: string; classe: string; estado: string
  motivo: string | null; codigo_saida: number | null; duracao_ms: number | null; saida_resumo: string | null; ip: string | null
  criado_em: string | null; decidido_por: string | null; decidido_em: string | null; executado_em: string | null
}

const TOM_ESTADO: Record<string, string> = {
  executado: 'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  falhou: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  bloqueado: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  proposto: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800',
  executando: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
}
const ESTADOS = ['', 'executado', 'falhou', 'bloqueado', 'proposto', 'executando', 'recusado', 'expirado']
const CLASSES = ['', 'leitura', 'escrita', 'proibido']
const LIMITE = 50

function dataHora(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })
}

export function AuditoriaTerminal() {
  const [filtro, setFiltro] = useState({ matricula: '', estado: '', classe: '', desde: '', ate: '' })
  const [offset, setOffset] = useState(0)
  // A matrícula é digitada: espera 300 ms parada antes de consultar (sem uma consulta por tecla).
  const [matriculaDigitada, setMatriculaDigitada] = useState('')
  useEffect(() => {
    const t = setTimeout(() => { setFiltro(f => ({ ...f, matricula: matriculaDigitada })); setOffset(0) }, 300)
    return () => clearTimeout(t)
  }, [matriculaDigitada])
  const [aberta, setAberta] = useState<string | null>(null)
  const qs = useMemo(() => {
    const p = new URLSearchParams({ limite: String(LIMITE), offset: String(offset) })
    for (const [k, v] of Object.entries(filtro)) if (v.trim()) p.set(k, v.trim())
    return p.toString()
  }, [filtro, offset])
  const dados = useQuery<{ total: number; itens: LinhaAuditoria[] }>({
    queryKey: ['agentes-terminal-auditoria', qs], queryFn: () => apiFetch(`/agentes/terminal/auditoria?${qs}`),
    placeholderData: keepPreviousData,  // trocar o filtro não apaga a tabela enquanto a nova página chega
  })
  const muda = (k: keyof typeof filtro) => (e: { target: { value: string } }) => { setFiltro(f => ({ ...f, [k]: e.target.value })); setOffset(0) }
  const campo = 'h-8 rounded-md border border-edge bg-panel text-ink text-[13px] px-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]'
  const total = dados.data?.total ?? 0
  return (
    <div className="flex flex-col gap-3" data-terminal-auditoria>
      <div className="flex flex-wrap items-end gap-2" role="group" aria-label="Filtros da auditoria">
        <label className="flex flex-col gap-0.5 text-[12px] text-dim">Matrícula<input className={campo} value={matriculaDigitada} onChange={e => setMatriculaDigitada(e.target.value)} maxLength={20} /></label>
        <label className="flex flex-col gap-0.5 text-[12px] text-dim">Estado
          <select className={campo} value={filtro.estado} onChange={muda('estado')}>{ESTADOS.map(e => <option key={e} value={e}>{e ? (ROTULO_ESTADO as Record<string, string>)[e] ?? e : 'todos'}</option>)}</select></label>
        <label className="flex flex-col gap-0.5 text-[12px] text-dim">Classe
          <select className={campo} value={filtro.classe} onChange={muda('classe')}>{CLASSES.map(c => <option key={c} value={c}>{c || 'todas'}</option>)}</select></label>
        <label className="flex flex-col gap-0.5 text-[12px] text-dim">De<input type="date" className={campo} value={filtro.desde} onChange={muda('desde')} /></label>
        <label className="flex flex-col gap-0.5 text-[12px] text-dim">Até<input type="date" className={campo} value={filtro.ate} onChange={muda('ate')} /></label>
      </div>
      {dados.isLoading ? <p className="text-sm text-dim">Carregando a auditoria…</p>
        : dados.isError ? <p className="text-sm text-red-700 dark:text-red-400">{mensagemDeErro(dados.error, 'Não foi possível carregar a auditoria.')}</p>
        : total === 0 ? <p className="text-sm text-dim" data-terminal-auditoria-vazia>Nenhum comando registrado com estes filtros.</p>
        : (
          <div className="relative overflow-x-auto border border-edge rounded-lg">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Comandos do Terminal</caption>
              <thead className="bg-canvas text-dim text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">Quando</th><th className="px-3 py-2 font-medium">Usuário</th>
                  <th className="px-3 py-2 font-medium">Servidor</th><th className="px-3 py-2 font-medium">Comando</th>
                  <th className="px-3 py-2 font-medium">Classe</th><th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium text-right">Código</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {dados.data!.itens.map(l => (
                  <tr key={l.cmd_id} className="align-top">
                    <td className="px-3 py-2 text-dim whitespace-nowrap">{dataHora(l.criado_em)}</td>
                    <td className="px-3 py-2 text-ink">{l.matricula}{l.decidido_por && l.decidido_por !== l.matricula ? ` (decidido por ${l.decidido_por})` : ''}</td>
                    <td className="px-3 py-2 text-ink">{l.servidor}</td>
                    <td className="px-3 py-2 max-w-[28rem]">
                      <button type="button" onClick={() => setAberta(a => a === l.cmd_id ? null : l.cmd_id)} aria-expanded={aberta === l.cmd_id}
                              className="text-left font-mono text-ink break-words [overflow-wrap:anywhere] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8] rounded">
                        {l.comando}
                      </button>
                      {aberta === l.cmd_id && (
                        <div className="mt-1 text-[12px] text-dim flex flex-col gap-1">
                          {l.motivo && <span>Motivo: {l.motivo}</span>}
                          {l.saida_resumo && <pre className="font-mono whitespace-pre-wrap break-all bg-canvas border border-edge rounded p-2 text-ink">{l.saida_resumo}</pre>}
                          <span>{l.duracao_ms != null ? `${l.duracao_ms} ms` : ''}{l.executado_em ? ` · executado ${dataHora(l.executado_em)}` : ''}</span>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {l.classe === 'escrita'
                        ? <span className="inline-block px-2 py-0.5 rounded border text-[12px] bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800">escrita</span>
                        : <span className="text-ink">{l.classe}</span>}
                    </td>
                    <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 rounded border text-[12px] ${TOM_ESTADO[l.estado] ?? 'bg-canvas text-dim border-edge'}`}>{(ROTULO_ESTADO as Record<string, string>)[l.estado] ?? l.estado}</span></td>
                    <td className="px-3 py-2 text-right text-ink tabular-nums">{l.codigo_saida ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {total > LIMITE && (
        <div className="flex items-center gap-2 text-[13px] text-dim">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - LIMITE))}
                  className="h-8 px-3 rounded-md border border-edge bg-panel text-ink disabled:opacity-50">Anteriores</button>
          <span>{offset + 1}–{Math.min(offset + LIMITE, total)} de {total}</span>
          <button type="button" disabled={offset + LIMITE >= total} onClick={() => setOffset(o => o + LIMITE)}
                  className="h-8 px-3 rounded-md border border-edge bg-panel text-ink disabled:opacity-50">Próximos</button>
        </div>
      )}
    </div>
  )
}
