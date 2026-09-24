// O chat do agente: bolhas, envio, e o que ele consultou em cada resposta.
//
// Apresentação pura — quem fala com a API é `pages/Agentes.tsx`. É o mesmo
// corte de `MaestroChat`/`MaestroPainel` (container = estado/rede, painel =
// render), e é o que deixa o componente testável sem servidor.
//
// Acessibilidade (critério 4 da F3):
//   • a lista de mensagens é `aria-live="polite"` — o leitor de tela anuncia
//     a resposta quando ela chega, sem roubar o foco de quem está digitando;
//   • depois de enviar, o foco VOLTA para o campo (quem conversa não precisa
//     pegar o mouse entre uma pergunta e outra);
//   • o "digitando" tem texto, não só animação.
// Sem cor fixa: tudo em tokens (`panel`, `canvas`, `edge`, `ink`, `dim`),
// exceto o azul da marca, que já vem com par claro/escuro no projeto.
import { useEffect, useRef } from 'react'
import { Send } from 'lucide-react'
import type { DecisaoProposta, MensagemChat } from '../../lib/agentes'
import {
  MAX_MENSAGEM, STATUS_RODADA, consultasExecutadas, formatarDuracao, quando, rotuloDoArtefato, textosDoChat,
} from '../../lib/agentes'
import { resumoConsulta } from '../../lib/sqlRealce'
import { BlocoSql } from './BlocoSql'
import { CartaoProposta } from './CartaoProposta'
import { MarkdownAgente } from './MarkdownAgente'

interface Props {
  mensagens: MensagemChat[]
  valor: string
  onValor: (v: string) => void
  onEnviar: () => void
  enviando: boolean
  /** Frase de progresso da rodada em curso (stream) — some quando a resposta chega. */
  statusTexto?: string | null
  /** Bloqueia o campo (sonda impeditiva, agente desligado). */
  bloqueado?: boolean
  motivoBloqueio?: string
  nomeAgente: string
  /** As ferramentas do agente — mudam o convite e o placeholder do chat. */
  ferramentas?: string[]
  /** F5: decidir uma proposta do agente. Sem ele, os cartões não aparecem. */
  onDecidir?: (id: number, decisao: DecisaoProposta) => void
  /** Ids com decisão em andamento (botões desabilitados). */
  decidindo?: ReadonlySet<number>
}

/**
 * "Consultas executadas": cada SQL que RODOU, exatamente como rodou, com o
 * banco, as linhas devolvidas e o tempo (spec ferramenta-banco §2, C5). As
 * linhas em si nunca chegam aqui — nem ficam gravadas.
 */
function ConsultasExecutadas({ artefatos }: { artefatos: NonNullable<MensagemChat['artefatos']> }) {
  const consultas = consultasExecutadas(artefatos)
  if (!consultas.length) return null
  return (
    <details className="mt-2 text-xs" data-agentes-consultas>
      <summary className="cursor-pointer text-[11px] text-dim select-none">
        {consultas.length === 1 ? 'Consulta executada (1)' : `Consultas executadas (${consultas.length})`}
      </summary>
      <div className="flex flex-col gap-1.5 mt-1">
        {consultas.map((c, i) => (
          <BlocoSql key={i} sql={c.sql} rotulo={`${c.meta.conexao}/${c.meta.banco}`} rodape={resumoConsulta(c.meta)} />
        ))}
      </div>
    </details>
  )
}

function LinhaFerramentas({ artefatos }: { artefatos: NonNullable<MensagemChat['artefatos']> }) {
  if (!artefatos.length) return null
  // Só os nomes, na ordem em que rodaram — é a trilha que o operador usa para
  // saber SE a resposta veio da base ou do DataStage ao vivo. F6: a chamada
  // que falhou ganha "(falhou)", e a que o Orquestra nem rodou — porque já
  // tinha falhado — "(não repetida)".
  const nomes = artefatos.map(a => {
    // Consulta a banco: "banco <conexão>/<banco>" (spec ferramenta-banco §2).
    const nome = rotuloDoArtefato(a)
    // Spec admin B2: a ferramenta não é deste agente — o Orquestra recusou.
    if (a.recusada) return `${nome} (indisponível)`
    if (a.repetida) return `${nome} (não repetida)`
    if (a.falhou) return `${nome} (falhou)`
    return nome
  })
  return (
    <p className="text-[11px] text-dim mt-1.5" data-agentes-ferramentas>
      Consultei: {nomes.join(' › ')}
    </p>
  )
}

export function ChatAgente({
  mensagens, valor, onValor, onEnviar, enviando, statusTexto, bloqueado, motivoBloqueio, nomeAgente,
  onDecidir, decidindo, ferramentas,
}: Props) {
  const textos = textosDoChat(ferramentas)
  const rolagemRef = useRef<HTMLDivElement>(null)
  const campoRef = useRef<HTMLTextAreaElement>(null)
  const enviandoAntes = useRef(enviando)

  useEffect(() => {
    const el = rolagemRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [mensagens, enviando])

  // Devolve o foco ao campo quando a resposta chega (enviando: true → false).
  useEffect(() => {
    if (enviandoAntes.current && !enviando && !bloqueado) campoRef.current?.focus()
    enviandoAntes.current = enviando
  }, [enviando, bloqueado])

  const podeEnviar = !enviando && !bloqueado && valor.trim().length > 0 && valor.length <= MAX_MENSAGEM

  function aoTeclar(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter envia, Shift+Enter quebra linha — o mesmo do Maestro.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (podeEnviar) onEnviar()
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0" data-agentes-chat>
      <div
        ref={rolagemRef}
        // `overflow-y-auto` só AQUI: nenhum ancestral tem overflow-hidden, para
        // não matar o `sticky` do cabeçalho da página (lição do Caixa Seguro).
        className="flex-1 min-h-0 overflow-y-auto px-1 py-2 flex flex-col gap-3"
        aria-live="polite"
        aria-busy={enviando}
        aria-label={`Conversa com ${nomeAgente}`}
      >
        {mensagens.length === 0 && (
          <p className="text-sm text-dim px-2 py-6 text-center">
            {textos.convite}
            {textos.exemplo && (
              <>
                <br />
                Ex.: <span className="text-ink">{textos.exemplo}</span>
              </>
            )}
          </p>
        )}

        {mensagens.map(m => (
          m.papel === 'user' ? (
            <div key={m.id} className="self-end max-w-[85%]">
              <div className="rounded-lg rounded-br-sm px-3 py-2 bg-[#1A5FA8] text-white text-sm whitespace-pre-wrap break-words">
                {m.texto}
              </div>
            </div>
          ) : (
            <div key={m.id} className="self-start max-w-[92%]">
              <div className="rounded-lg rounded-bl-sm px-3 py-2 bg-panel border border-edge text-ink shadow-sm">
                <MarkdownAgente texto={m.texto} />
                {m.artefatos && <ConsultasExecutadas artefatos={m.artefatos} />}
                {m.artefatos && <LinhaFerramentas artefatos={m.artefatos} />}
                {typeof m.duracaoMs === 'number' && (
                  // Quanto levou: o usuário calibra a expectativa da próxima
                  // pergunta (uma extração ISX leva dezenas de segundos).
                  <p className="text-[11px] text-dim mt-1" data-agentes-duracao>
                    {formatarDuracao(m.duracaoMs)}
                  </p>
                )}
                {m.em && (
                  // Conversa retomada: QUANDO o agente disse isso. O dado
                  // pode ter envelhecido desde então (critério 3 da F4).
                  <p className="text-[11px] text-dim mt-1" data-agentes-quando>
                    {quando(m.em)}
                  </p>
                )}
              </div>
              {onDecidir && m.propostas?.map(p => (
                <CartaoProposta
                  key={p.id}
                  proposta={p}
                  decidindo={decidindo?.has(p.id) ?? false}
                  onDecidir={onDecidir}
                />
              ))}
              {m.propostasRecusadas && m.propostasRecusadas.length > 0 && (
                // Transparência: o modelo propôs, a régua descartou — o
                // operador sabe que houve algo e por quê (nada some calado).
                <p className="text-[11px] text-dim mt-1 px-1" data-agentes-propostas-recusadas>
                  {m.propostasRecusadas.length === 1
                    ? `1 proposta descartada: ${m.propostasRecusadas[0]}.`
                    : `${m.propostasRecusadas.length} propostas descartadas: ${m.propostasRecusadas.join('; ')}.`}
                </p>
              )}
              {m.aprendizadosUsados && m.aprendizadosUsados.length > 0 && (
                <p className="text-[11px] text-dim mt-1 px-1" data-agentes-aprendizados-usados
                   title={m.aprendizadosUsados.join('\n')}>
                  Considerei {m.aprendizadosUsados.length === 1
                    ? '1 aprendizado validado'
                    : `${m.aprendizadosUsados.length} aprendizados validados`}.
                </p>
              )}
              {m.aprendizadosSugeridos && m.aprendizadosSugeridos.length > 0 && (
                <p className="text-[11px] text-dim mt-1 px-1" data-agentes-aprendizados-sugeridos>
                  Sugeri à curadoria: {m.aprendizadosSugeridos.join('; ')}.
                </p>
              )}
              {m.status && STATUS_RODADA[m.status] && (
                <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-1 px-1"
                   data-agentes-status={m.status}>
                  {STATUS_RODADA[m.status]}
                </p>
              )}
            </div>
          )
        ))}

        {enviando && (
          <div className="self-start">
            <div className="rounded-lg rounded-bl-sm px-3 py-2 bg-panel border border-edge text-dim text-sm flex items-center gap-2">
              <span className="flex gap-1" aria-hidden="true">
                <span className="w-1.5 h-1.5 rounded-full bg-dim animate-bounce" />
                <span className="w-1.5 h-1.5 rounded-full bg-dim animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-dim animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
              <span data-agentes-progresso>{statusTexto || `${nomeAgente} está consultando…`}</span>
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-edge pt-3 mt-1">
        {bloqueado && motivoBloqueio && (
          <p className="text-xs text-dim mb-2">{motivoBloqueio}</p>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={campoRef}
            value={valor}
            onChange={e => onValor(e.target.value)}
            onKeyDown={aoTeclar}
            disabled={bloqueado}
            rows={2}
            maxLength={MAX_MENSAGEM}
            aria-label="Sua pergunta"
            placeholder={bloqueado ? 'Indisponível' : textos.placeholder}
            className="flex-1 resize-none rounded-lg border border-edge bg-panel text-ink placeholder:text-dim
                       px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1A5FA8] disabled:opacity-60"
          />
          <button
            type="button"
            onClick={onEnviar}
            disabled={!podeEnviar}
            aria-label="Enviar pergunta"
            className="shrink-0 rounded-lg px-3 py-2.5 bg-[#1A5FA8] text-white text-sm font-medium
                       hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            <Send className="w-4 h-4" aria-hidden="true" />
            Enviar
          </button>
        </div>
        {valor.length > MAX_MENSAGEM * 0.9 && (
          <p className="text-[11px] text-dim mt-1">{valor.length} / {MAX_MENSAGEM} caracteres</p>
        )}
      </div>
    </div>
  )
}
