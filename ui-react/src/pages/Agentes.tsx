// Tela `/agentes` (F3 da spec docs/spec-agentes-datastage.md).
//
// Container: é daqui que saem as chamadas de API; os componentes em
// `components/agentes/` só desenham. Sem subrotas — agente e conversa vão em
// query (`?agente=&conversa=`), como a spec define.
//
// Três estados que a tela precisa distinguir, e que o critério 1 da F3
// verifica: (a) SEM grant nenhum, o catálogo volta VAZIO e isso não é erro —
// é o estado normal antes de o admin liberar o primeiro agente, e merece uma
// explicação, não um 403 em branco; (b) com grant, mas com a sonda do gateway
// impeditiva, a tela abre e explica o motivo sem deixar conversar; (c) tudo
// certo, conversa liberada.
import { useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bot } from 'lucide-react'
import { apiFetch } from '../lib/api'
import type {
  AgenteCatalogo, ArtefatoFerramenta, CatalogoResposta, EstadoSonda, MensagemChat,
  RespostaConversa, StatusAgentes,
} from '../lib/agentes'
import { SONDA, chaveDaConversa, mensagemDeErro } from '../lib/agentes'
import { AvisoSonda } from '../components/agentes/AvisoSonda'
import { ChatAgente } from '../components/agentes/ChatAgente'
import { GrafoJobAgente } from '../components/agentes/GrafoJobAgente'
import { IndicadorProjeto } from '../components/agentes/IndicadorProjeto'
import { toast } from '../components/ui/Toast'

interface ConversaGuardada {
  conversa_id: string
  projeto: string | null
  mensagens: MensagemChat[]
}

function lerGuardada(agenteId: string): ConversaGuardada | null {
  try {
    const cru = localStorage.getItem(chaveDaConversa(agenteId))
    if (!cru) return null
    const dado = JSON.parse(cru) as ConversaGuardada
    if (!dado?.conversa_id || !Array.isArray(dado.mensagens)) return null
    return dado
  } catch {
    return null  // storage bloqueado/corrompido nunca derruba a tela
  }
}

function guardar(agenteId: string, dado: ConversaGuardada) {
  try {
    localStorage.setItem(chaveDaConversa(agenteId), JSON.stringify(dado))
  } catch {
    /* cota/modo privado: a conversa segue no servidor, só não sobrevive ao F5 */
  }
}

/**
 * O par (pipeline, job) mais recente entre os artefatos — é o que permite
 * abrir o grafo. `GET /lineage/isx/job` precisa dos DOIS; um artefato que só
 * tenha `job_name` (o agente resolveu o projeto, mas o job não está mapeado
 * em nenhum pipeline) não dá para plotar, e aí o botão nem aparece.
 */
function jobPlotavel(mensagens: MensagemChat[]): { pipeline: string; job: string } | null {
  for (let i = mensagens.length - 1; i >= 0; i--) {
    const arts = mensagens[i].artefatos
    if (!arts) continue
    for (let j = arts.length - 1; j >= 0; j--) {
      const args = (arts[j] as ArtefatoFerramenta).args ?? {}
      const pipeline = typeof args.pipeline_name === 'string' ? args.pipeline_name.trim() : ''
      const job = typeof args.job_name === 'string' ? args.job_name.trim() : ''
      if (pipeline && job) return { pipeline, job }
    }
  }
  return null
}

let seq = 0
const novoId = () => `m${Date.now()}_${seq++}`

/**
 * A conversa com UM agente. Montado com `key={agente.id}`, o que faz o React
 * descartar e recriar todo este estado ao trocar de agente — em vez de um
 * `useEffect` que chamaria cinco `setState` em cascata só para zerar tudo
 * (é o "you might not need an effect": resetar estado ao mudar de entrada é
 * trabalho de `key`, não de efeito). O estado inicial vem do localStorage no
 * inicializador preguiçoso do `useState`, uma vez, sem render extra.
 */
function PainelConversa({ agente, sonda, cadastroTexto, onRecarregarSonda, recarregandoSonda }: {
  agente: AgenteCatalogo
  sonda?: EstadoSonda
  cadastroTexto?: string | null
  onRecarregarSonda: () => void
  recarregandoSonda: boolean
}) {
  const guardada = useMemo(() => lerGuardada(agente.id), [agente.id])
  const [mensagens, setMensagens] = useState<MensagemChat[]>(() => guardada?.mensagens ?? [])
  const [projeto, setProjeto] = useState<string | null>(() => guardada?.projeto ?? null)
  const [conversaId, setConversaId] = useState<string | null>(() => guardada?.conversa_id ?? null)
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [grafoAberto, setGrafoAberto] = useState(false)
  const [stageSel, setStageSel] = useState<string | null>(null)
  // Descarta resposta que chega DEPOIS de "nova conversa" — mesmo cuidado do
  // `pedidoRef` do MaestroChat.
  const pedidoRef = useRef(0)

  const infoSonda = sonda ? SONDA[sonda] : null
  const bloqueado = infoSonda?.bloqueia ?? false

  async function enviar(mensagemBruta?: string) {
    const conteudo = (mensagemBruta ?? texto).trim()
    if (!conteudo || enviando) return
    const meuPedido = ++pedidoRef.current
    setMensagens(m => [...m, { id: novoId(), papel: 'user', texto: conteudo }])
    setTexto('')
    setEnviando(true)
    try {
      const r = await apiFetch<RespostaConversa>(`/agentes/${agente.id}/conversar`, {
        method: 'POST',
        body: JSON.stringify(conversaId
          ? { mensagem: conteudo, conversa_id: conversaId }
          : { mensagem: conteudo }),
      })
      if (pedidoRef.current !== meuPedido) return  // conversa trocou no meio
      setConversaId(r.conversa_id)
      setProjeto(r.projeto)
      setMensagens(m => {
        const novas = [...m, {
          id: novoId(), papel: 'assistant' as const, texto: r.texto,
          artefatos: r.artefatos, status: r.status,
        }]
        guardar(agente.id, { conversa_id: r.conversa_id, projeto: r.projeto, mensagens: novas })
        return novas
      })
    } catch (e) {
      if (pedidoRef.current !== meuPedido) return
      const msg = mensagemDeErro(e, 'Não foi possível falar com o agente agora.')
      toast.error(msg)
      setMensagens(m => [...m, { id: novoId(), papel: 'assistant', texto: msg }])
    } finally {
      if (pedidoRef.current === meuPedido) setEnviando(false)
    }
  }

  function novaConversa() {
    pedidoRef.current++
    setMensagens([])
    setProjeto(null)
    setConversaId(null)
    setGrafoAberto(false)
    setStageSel(null)
    setEnviando(false)
    try { localStorage.removeItem(chaveDaConversa(agente.id)) } catch { /* ignore */ }
  }

  const plotavel = useMemo(() => jobPlotavel(mensagens), [mensagens])

  return (
    <>
      {mensagens.length > 0 && (
        <div className="flex justify-end -mt-2">
          <button
            type="button"
            onClick={novaConversa}
            className="text-[13px] text-[#1A5FA8] dark:text-blue-400 hover:underline"
          >
            nova conversa
          </button>
        </div>
      )}

      {sonda && (
        <AvisoSonda
          estado={sonda}
          cadastroTexto={cadastroTexto}
          onTentarDeNovo={onRecarregarSonda}
          recarregando={recarregandoSonda}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <IndicadorProjeto
          projeto={projeto}
          desabilitado={bloqueado || enviando}
          onTrocar={nome => enviar(`Usar o projeto DataStage ${nome}.`)}
        />
        {plotavel && (
          <button
            type="button"
            onClick={() => setGrafoAberto(v => !v)}
            className="text-[13px] text-[#1A5FA8] dark:text-blue-400 hover:underline"
          >
            {grafoAberto ? 'ocultar grafo' : `ver grafo de ${plotavel.job}`}
          </button>
        )}
      </div>

      {grafoAberto && plotavel && (
        <GrafoJobAgente
          pipeline={plotavel.pipeline}
          job={plotavel.job}
          stageSel={stageSel}
          onSelecionarStage={setStageSel}
          onFechar={() => setGrafoAberto(false)}
        />
      )}

      <div className="flex-1 min-h-0 bg-canvas rounded-lg">
        <ChatAgente
          mensagens={mensagens}
          valor={texto}
          onValor={setTexto}
          onEnviar={() => enviar()}
          enviando={enviando}
          bloqueado={bloqueado}
          motivoBloqueio={infoSonda?.bloqueia ? infoSonda.titulo : undefined}
          nomeAgente={agente.nome}
        />
      </div>
    </>
  )
}

export default function Agentes() {
  const [params, setParams] = useSearchParams()
  const agenteParam = params.get('agente')

  const catalogo = useQuery<CatalogoResposta>({
    queryKey: ['agentes-catalogo'],
    queryFn: () => apiFetch('/agentes/catalogo'),
  })
  const status = useQuery<StatusAgentes>({
    queryKey: ['agentes-status'],
    queryFn: () => apiFetch('/agentes/status'),
    retry: false,
  })

  const agentes = useMemo(() => catalogo.data?.agentes ?? [], [catalogo.data])
  const agente = useMemo(
    () => agentes.find(a => a.id === agenteParam) ?? agentes[0] ?? null,
    [agentes, agenteParam])

  if (catalogo.isLoading) {
    return <p className="text-sm text-dim p-6">Carregando agentes…</p>
  }

  // Critério 1 da F3: sem grant o catálogo volta VAZIO — e isso é o estado
  // normal antes de o admin liberar o primeiro agente, não um erro. A tela
  // abre e explica; quem chamar a API direto é que leva 403.
  if (!agente) {
    return (
      <div className="p-6 max-w-2xl" data-agentes-vazio>
        <div className="bg-panel border border-edge rounded-lg p-6 shadow-sm text-center">
          <Bot className="w-8 h-8 mx-auto text-dim" aria-hidden="true" />
          <h2 className="text-base font-semibold text-ink mt-3">Nenhum agente liberado para você</h2>
          <p className="text-sm text-dim mt-2">
            Os agentes de IA são liberados usuário a usuário pelo administrador. Se você precisa
            usar o agente de mapeamento DataStage, peça a liberação em Admin › Agentes.
          </p>
          {catalogo.isError && (
            <p className="text-sm text-dim mt-3">
              {mensagemDeErro(catalogo.error, 'Não foi possível carregar o catálogo de agentes.')}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 h-[calc(100vh-7rem)] min-h-0">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Bot className="w-5 h-5 text-[#1A5FA8] dark:text-blue-400" aria-hidden="true" />
            {agente.nome}
          </h1>
          <p className="text-sm text-dim mt-0.5 max-w-2xl">{agente.descricao}</p>
        </div>
        {agentes.length > 1 && (
          <label className="text-sm text-dim flex items-center gap-2">
            Agente
            <select
              value={agente.id}
              onChange={e => {
                const p = new URLSearchParams(params)
                p.set('agente', e.target.value)
                setParams(p, { replace: true })
              }}
              className="rounded border border-edge bg-panel text-ink px-2 py-1 text-sm
                         focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]"
            >
              {agentes.map(a => <option key={a.id} value={a.id}>{a.nome}</option>)}
            </select>
          </label>
        )}
      </header>

      {/* `key`: trocar de agente descarta a conversa anterior por completo. */}
      <PainelConversa
        key={agente.id}
        agente={agente}
        sonda={status.data?.estado}
        cadastroTexto={catalogo.data?.cadastro_texto}
        onRecarregarSonda={() => { void status.refetch() }}
        recarregandoSonda={status.isFetching}
      />
    </div>
  )
}
