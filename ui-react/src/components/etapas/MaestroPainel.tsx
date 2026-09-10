// O painel do Maestro — só APRESENTAÇÃO (estado e chamadas moram em
// MaestroChat). Separado para a bancada tests/js/ds_params_harness.cjs render
// o painel com fixtures (proposta atendida, não atendida, pergunta, erro) sem
// portal nem rede.
//
// Visual nativo: tokens panel/edge/ink/canvas (claro+escuro), Button da casa.
// A resposta do Maestro é markdown desenhado por blocos (parser puro de
// caixa/lib/markdown.ts) — nunca HTML por string: o texto vem de um LLM.
import { useMemo } from 'react'
import { ArrowLeft, Check, History, RotateCcw, Send, X } from 'lucide-react'
import { Button } from '../ui/Button'
import { parseMarkdown, type BlocoMd, type PedacoInline } from '../../caixa/lib/markdown'
import {
  MAESTRO_MAX_MENSAGEM, MAESTRO_NOME, descricaoDaLinha,
  type MaestroHistoricoConversa, type MaestroMensagem,
} from '../../lib/maestro'
import { MaestroAvatar } from './MaestroAvatar'

export interface MaestroPainelProps {
  mensagens: MaestroMensagem[]
  carregando: boolean
  sugestoes: string[]
  entrada: string
  onEntrada: (v: string) => void
  onEnviar: () => void
  onSugestao: (s: string) => void
  onAplicar: (m: MaestroMensagem) => void
  onFechar: () => void
  onNovaConversa: () => void
  /** null = a lista de conversas anteriores está fechada. */
  historico: MaestroHistoricoConversa[] | null
  historicoCarregando?: boolean
  onHistorico: () => void
  onAbrirConversa: (c: MaestroHistoricoConversa) => void
  referencia: string
  rolagemRef?: React.RefObject<HTMLDivElement | null>
  onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void
}

function Inline({ partes }: { partes: PedacoInline[] }) {
  return (
    <>
      {partes.map((p, i) => {
        if (p.codigo) return <code key={i} className="rounded bg-canvas px-1 py-0.5 font-mono text-[11px]">{p.texto}</code>
        if (p.negrito) return <strong key={i} className="font-semibold">{p.texto}</strong>
        if (p.italico) return <em key={i}>{p.texto}</em>
        return <span key={i}>{p.texto}</span>
      })}
    </>
  )
}

function Bloco({ b }: { b: BlocoMd }) {
  switch (b.tipo) {
    case 'titulo':
      return <p className="mt-1 font-semibold first:mt-0"><Inline partes={b.partes} /></p>
    case 'separador':
      return <hr className="my-1 border-0 border-t border-edge" />
    case 'codigo':
      return <pre className="overflow-x-auto whitespace-pre rounded bg-canvas p-2 font-mono text-[11px]">{b.texto}</pre>
    case 'lista':
      return b.ordenada
        ? <ol className="flex list-decimal flex-col gap-0.5 pl-4">{b.itens.map((it, i) => <li key={i}><Inline partes={it} /></li>)}</ol>
        : <ul className="flex list-disc flex-col gap-0.5 pl-4">{b.itens.map((it, i) => <li key={i}><Inline partes={it} /></li>)}</ul>
    case 'tabela':
      return (
        <div className="-mx-1 overflow-x-auto px-1">
          <table className="border-collapse text-[11px]">
            <thead><tr>{b.cabecalho.map((c, i) => <th key={i} className="whitespace-nowrap border-b border-edge px-1.5 py-1 text-left font-semibold"><Inline partes={c} /></th>)}</tr></thead>
            <tbody>{b.linhas.map((l, i) => <tr key={i}>{l.map((c, j) => <td key={j} className="border-b border-edge/60 px-1.5 py-1 align-top"><Inline partes={c} /></td>)}</tr>)}</tbody>
          </table>
        </div>
      )
    default:
      return <p><Inline partes={b.partes} /></p>
  }
}

function MaestroMarkdown({ texto }: { texto: string }) {
  const blocos = useMemo(() => parseMarkdown(texto), [texto])
  return <div className="flex flex-col gap-1.5 break-words text-sm leading-snug">{blocos.map((b, i) => <Bloco key={i} b={b} />)}</div>
}

/** O cartão que acompanha uma resposta com resultado: a proposta (com a
 *  prévia e o botão de aplicar), ou o "não atendido" com a orientação. */
function CartaoResultado({ m, referencia, onAplicar }: { m: MaestroMensagem; referencia: string; onAplicar: (m: MaestroMensagem) => void }) {
  const r = m.resultado
  if (!r) return null
  if (r.status === 'nao_atendido') {
    return (
      <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] leading-snug text-amber-900 dark:border-amber-800/60 dark:bg-amber-900/20 dark:text-amber-200"
           data-maestro-nao-atendido>
        <p className="font-semibold">Cenário não atendido</p>
        {r.motivo && <p className="mt-0.5">{r.motivo}</p>}
        {r.orientacao && <p className="mt-1">{r.orientacao}</p>}
      </div>
    )
  }
  if (r.status !== 'atendido' || !r.proposta?.params.length) return null
  const previaPorNome = new Map((r.previa ?? []).map(p => [p.param_name, p]))
  // A referência que a API USOU para calcular esta prévia — não a atual do
  // editor, que o usuário pode ter trocado depois (o rótulo mentiria).
  const referenciaDaPrevia = r.referencia || referencia
  return (
    <div className="mt-2 rounded-lg border border-edge bg-canvas/60 px-3 py-2 text-[12px]" data-maestro-proposta data-maestro-status={r.status}>
      <p className="mb-1 font-semibold text-ink">Proposta{r.cenario ? <span className="font-normal text-dim"> · {r.cenario}</span> : null}</p>
      <ul className="flex flex-col gap-1">
        {r.proposta.params.map(p => {
          const previa = previaPorNome.get(p.param_name)
          return (
            <li key={p.param_name} className="flex flex-col" data-maestro-param={p.param_name}>
              <span className="font-mono font-semibold text-ink">{p.param_name}</span>
              <span className="text-dim">{descricaoDaLinha(p)}</span>
              {previa && p.param_type !== 'Encrypted' && (
                <span className="text-dim" title={previa.descricao} data-maestro-previa={previa.valor} data-maestro-referencia={referenciaDaPrevia}>
                  com a referência {referenciaDaPrevia}: <span className="font-mono text-ink">{previa.valor}</span>
                </span>
              )}
            </li>
          )
        })}
      </ul>
      {r.avisos.length > 0 && (
        <ul className="mt-1.5 flex flex-col gap-0.5 text-amber-800 dark:text-amber-300">
          {r.avisos.map(a => <li key={a} data-maestro-aviso>⚠ {a}</li>)}
        </ul>
      )}
      <div className="mt-2">
        {m.aplicada ? (
          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300" data-maestro-aplicada>
            <Check size={13} /> Aplicado no editor — confira e salve a etapa
          </span>
        ) : (
          <Button size="sm" variant="primary" onClick={() => onAplicar(m)} data-maestro-aplicar>
            Aplicar no editor
          </Button>
        )}
      </div>
    </div>
  )
}

export function MaestroPainel({
  mensagens, carregando, sugestoes, entrada, onEntrada, onEnviar, onSugestao, onAplicar, onFechar,
  onNovaConversa, historico, historicoCarregando, onHistorico, onAbrirConversa, referencia, rolagemRef, onKeyDown,
}: MaestroPainelProps) {
  const podeEnviar = !carregando && entrada.trim().length > 0 && entrada.length <= MAESTRO_MAX_MENSAGEM
  const soBoasVindas = mensagens.length <= 1 && !carregando
  return (
    <div
      className="fixed bottom-6 right-6 z-[60] flex h-[600px] max-h-[calc(100vh-3rem)] w-[26rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-edge bg-panel shadow-2xl"
      role="dialog"
      aria-label={`Chat com o ${MAESTRO_NOME}`}
      data-modal-exempt
      data-maestro-painel
      onKeyDown={onKeyDown}
    >
      {/* Cabeçalho */}
      <div className="flex items-center gap-2.5 border-b border-edge bg-canvas/60 px-3 py-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-full border border-edge bg-panel">
          <MaestroAvatar size={30} estado={carregando ? 'pensando' : 'ouvindo'} />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-tight text-ink">{MAESTRO_NOME}</p>
          <p className="text-[11px] text-dim" data-maestro-estado={carregando ? 'pensando' : 'ouvindo'}>
            {carregando ? 'Pensando…' : 'Assistente de parâmetros DataStage'}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-0.5">
          {/* Trocar de conversa com uma resposta em voo poria a resposta na
              conversa errada: os dois botões esperam o Maestro terminar. */}
          <button type="button" onClick={onNovaConversa} title="Nova conversa" aria-label="Nova conversa" disabled={carregando}
                  className="rounded p-1.5 text-dim transition-colors hover:bg-edge/60 hover:text-ink disabled:opacity-40" data-maestro-nova>
            <RotateCcw size={15} />
          </button>
          <button type="button" onClick={onHistorico} title="Conversas anteriores" aria-label="Conversas anteriores" disabled={carregando}
                  className={`rounded p-1.5 transition-colors hover:bg-edge/60 hover:text-ink disabled:opacity-40 ${historico ? 'text-ink' : 'text-dim'}`} data-maestro-historico>
            {historico ? <ArrowLeft size={15} /> : <History size={15} />}
          </button>
          <button type="button" onClick={onFechar} title="Fechar" aria-label="Fechar o chat"
                  className="rounded p-1.5 text-dim transition-colors hover:bg-edge/60 hover:text-ink" data-maestro-fechar>
            <X size={15} />
          </button>
        </div>
      </div>

      {historico ? (
        <div className="flex-1 overflow-y-auto p-3" data-maestro-lista-historico>
          <p className="mb-2 text-xs font-medium text-dim">Conversas anteriores</p>
          {historicoCarregando ? (
            <p className="py-6 text-center text-sm text-dim">Carregando…</p>
          ) : historico.length === 0 ? (
            <p className="py-6 text-center text-sm text-dim">Nenhuma conversa anterior.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {historico.map(c => (
                <button key={c.conversa_id} type="button" onClick={() => onAbrirConversa(c)}
                        className="rounded-lg border border-edge bg-canvas p-2.5 text-left transition-colors hover:border-blue-400"
                        data-maestro-conversa={c.conversa_id}>
                  <p className="truncate text-sm text-ink">{c.rodadas[0]?.mensagem ?? '(sem mensagem)'}</p>
                  <p className="mt-0.5 text-[11px] text-dim">
                    {c.iniciado_em}{c.job_name ? ` · ${c.job_name}` : ''} · {c.rodadas.length} rodada(s)
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div ref={rolagemRef} className="flex flex-1 flex-col gap-3 overflow-y-auto p-3" data-maestro-mensagens>
          {mensagens.map(m => (
            <div key={m.id} className={`flex ${m.papel === 'user' ? 'justify-end' : 'justify-start gap-2'}`} data-maestro-msg={m.papel}>
              {m.papel === 'assistant' && (
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-edge bg-panel">
                  <MaestroAvatar size={22} />
                </span>
              )}
              <div className={`min-w-0 max-w-[85%] rounded-lg px-3 py-2 ${
                m.papel === 'user'
                  ? 'bg-[#1A5FA8] text-white'
                  : m.erro
                    ? 'border border-red-300 bg-red-50 text-red-900 dark:border-red-800/60 dark:bg-red-900/20 dark:text-red-200'
                    : 'border border-edge bg-canvas text-ink'}`}>
                {m.papel === 'assistant' && !m.erro
                  ? <MaestroMarkdown texto={m.texto} />
                  : <p className="whitespace-pre-wrap text-sm leading-snug">{m.texto}</p>}
                <CartaoResultado m={m} referencia={referencia} onAplicar={onAplicar} />
              </div>
            </div>
          ))}
          {carregando && (
            <div className="flex items-center gap-2 text-xs text-dim" data-maestro-digitando>
              <span className="flex gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-dim" style={{ animationDelay: '0ms' }} />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-dim" style={{ animationDelay: '150ms' }} />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-dim" style={{ animationDelay: '300ms' }} />
              </span>
              {MAESTRO_NOME} está pensando…
            </div>
          )}
          {soBoasVindas && sugestoes.length > 0 && (
            <div className="mt-1 flex flex-col gap-1.5">
              <p className="text-xs font-medium text-dim">Cenários que eu atendo, por exemplo:</p>
              {sugestoes.map(s => (
                <button key={s} type="button" onClick={() => onSugestao(s)}
                        className="rounded-md border border-edge bg-canvas px-3 py-1.5 text-left text-xs text-ink transition-colors hover:border-blue-400"
                        data-maestro-sugestao>
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {!historico && (
        <div className="flex gap-2 border-t border-edge p-2.5">
          <textarea
            value={entrada}
            onChange={e => onEntrada(e.target.value)}
            onKeyDown={e => {
              // Enter envia; Shift+Enter quebra linha; Ctrl/Cmd+Enter fica
              // para os atalhos globais (no Fluxo, Ctrl+Enter salva o fluxo —
              // dar segundo significado à mesma tecla confundiria).
              if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
                e.preventDefault()
                if (podeEnviar) onEnviar()
              }
            }}
            placeholder="Descreva o cenário…"
            rows={2}
            disabled={carregando}
            maxLength={MAESTRO_MAX_MENSAGEM}
            className="min-w-0 flex-1 resize-none rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
            data-maestro-entrada
          />
          <Button variant="primary" size="md" onClick={onEnviar} disabled={!podeEnviar} aria-label="Enviar" data-maestro-enviar>
            <Send size={15} />
          </Button>
        </div>
      )}
    </div>
  )
}
