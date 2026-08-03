import { useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { toast } from '../ui/Toast'
import { Search, X, AlertTriangle, Check, Ban, Lock } from 'lucide-react'
import type { Pipeline, DependenciasEstadoApi } from '../../types/pipeline'
import { criaCiclo, type ArestaGrafo } from '../etapas/layoutGrafo'
import { msgCiclo, msgRepublicar, msgLinhaAssinada } from '../malhas/mensagensDependencia'
import { estiloStatus } from '../malhas/statusExecucao'

// Escolha das dependências de um pipeline (F5 da retomada).
//
// Substitui o campo de texto livre "pipelines separados por vírgula": um nome
// digitado errado era aceito e virava espera infinita em produção (D33). Aqui
// não há como digitar um nome — só escolher da lista.
//
// Fonte dos candidatos: paginação AGREGADA (padrão Pipelines.tsx) — NUNCA um
// limit único: o clamp do servidor é min(100, …) e o `limit=2000` da correção E
// era inerte, deixando o pipeline nº 101 inescolhível (D28).
//
// Duas portas de escrita (Decisão 1 do desenho):
//   • CRIAÇÃO — a seleção volta ao formulário e viaja no body do register
//     (replace-all sobre tabela vazia = só INSERTs; cancelar não grava nada);
//   • EDIÇÃO — o modal aplica o DIFF NA HORA, aresta a aresta, pelos endpoints
//     da F8 (POST/DELETE /dependencias) — a mesma porta do MalhaEditor, com a
//     canonização e o espelho CSV na mesma transação. O replace-all destrutivo
//     não existe mais neste caminho (causa C).
//
// D31: este componente só é MONTADO quando o modal está aberto (render
// condicional no pai) — o estado nasce do fetch a cada abertura, nada congela.

interface Props {
  pipelineAtual: string
  isEdit: boolean
  // Criação: seleção local do formulário. Edição: fallback (CSV espelho) para
  // quando o pipeline não aparece no /estado (ex.: inativo ou 067 pendente).
  selecionadas: string[]
  onClose: () => void
  onConfirmar: (nomes: string[]) => void
}

export function DependenciasModal({ pipelineAtual, isEdit, selecionadas, onClose, onConfirmar }: Props) {
  const qc = useQueryClient()
  const [busca, setBusca] = useState('')
  const [projeto, setProjeto] = useState('Todos')
  // null = o usuário ainda não mexeu — a lista exibida cai na hidratação do
  // servidor (edição) ou na seleção do formulário (criação).
  const [escolhidas, setEscolhidas] = useState<string[] | null>(isEdit ? null : selecionadas)
  const [aplicando, setAplicando] = useState(false)
  // 422 do servidor exibido INLINE, ao lado do chip que o causou (aceite F5).
  const [errosItem, setErrosItem] = useState<Record<string, string>>({})
  // O que está gravado na TABELA (verdade) — base do diff da edição; entre
  // aplicações parciais registra o que JÁ foi gravado com sucesso.
  const atuaisRef = useRef<string[] | null>(null)

  // Todos os pipelines, agregando as páginas do backend (clamp de 100/req
  // INTACTO — paginar é o contrato, D28). Filtros aplicados client-side.
  const { data: todos, isLoading: carregandoPipes } = useQuery<{ total: number; data: Pipeline[] }>({
    queryKey: ['pipelines-todos-deps'],
    queryFn: async () => {
      const primeira = await apiFetch<{ total: number; data: Pipeline[] }>('/pipelines?limit=100&offset=0')
      const all: Pipeline[] = [...primeira.data]
      const total = primeira.total
      let offset = 100
      while (all.length < total && offset <= 5000) {  // 5000 = guarda de segurança
        const r = await apiFetch<{ total: number; data: Pipeline[] }>(`/pipelines?limit=100&offset=${offset}`)
        all.push(...r.data)
        offset += 100
      }
      return { total, data: all }
    },
    staleTime: 60_000,
  })
  const pipelines = useMemo(() => todos?.data ?? [], [todos])

  // Estado das dependências: grafo global (data[].predecessores), status da
  // última execução de cada predecessor e a flag de degradação sem a 067.
  const estadoQuery = useQuery<DependenciasEstadoApi>({
    queryKey: ['deps-estado'],
    queryFn: () => apiFetch('/pipelines/dependencias/estado'),
  })
  const sem067 = estadoQuery.data?.migration_067_pendente === true
  // Em edição sem a 067 o POST/DELETE daria 503 — trava a edição e mostra os
  // chips derivados do CSV espelho, somente leitura (padrão do MalhaEditor).
  const travado = isEdit && sem067

  // Hidratação da EDIÇÃO: a seleção nasce da TABELA (entrada do próprio
  // pipeline no /estado), não do CSV — o fallback (CSV, via `selecionadas`)
  // cobre pipeline fora do /estado (inativo/sem dependência/067 pendente).
  // DERIVADA do fetch, sem setState em effect: null enquanto carrega; a cada
  // abertura o componente nasce de novo e re-hidrata (D31).
  const atuaisServidor = useMemo<string[] | null>(() => {
    if (!isEdit) return []
    if (estadoQuery.isLoading) return null
    const entrada = (estadoQuery.data?.data ?? []).find(
      d => d.pipeline_name.toLowerCase() === pipelineAtual.toLowerCase())
    return entrada ? entrada.predecessores.map(p => p.nome) : selecionadas
  }, [isEdit, estadoQuery.isLoading, estadoQuery.data, pipelineAtual, selecionadas])

  // Linha COMPILADA por Aguarde de malha (F11/Decisão 4): o chip fica TRAVADO
  // — só a malha dona mexe nela. Mapa casefold(predecessor) → {malha, no} da
  // entrada do próprio pipeline no /estado (campo ADITIVO compilada_por).
  const compiladaPorPred = useMemo(() => {
    const m = new Map<string, { malha: string | null; no: number }>()
    if (!isEdit) return m
    const entrada = (estadoQuery.data?.data ?? []).find(
      d => d.pipeline_name.toLowerCase() === pipelineAtual.toLowerCase())
    for (const p of entrada?.predecessores ?? []) {
      if (p.compilada_por) m.set(p.nome.toLowerCase(), p.compilada_por)
    }
    return m
  }, [isEdit, estadoQuery.data, pipelineAtual])

  // Grafo GLOBAL de dependências (source = predecessor → target = dependente):
  // é sobre ele que o criaCiclo desabilita candidato que fecharia ciclo —
  // inclusive por caminho que passa por pipeline de fora de qualquer malha.
  const arestasGlobais = useMemo<ArestaGrafo[]>(() => {
    const out: ArestaGrafo[] = []
    for (const item of estadoQuery.data?.data ?? []) {
      for (const p of item.predecessores) out.push({ source: p.nome, target: item.pipeline_name })
    }
    return out
  }, [estadoQuery.data])

  // Status de exibição por pipeline (última execução na data corrente) — o
  // chip do predecessor ganha o badge de estado (estilos da F9).
  const statusPorPipeline = useMemo(() => {
    const m = new Map<string, string>()
    for (const item of estadoQuery.data?.data ?? []) {
      if (item.corrida) m.set(item.pipeline_name.toLowerCase(), item.corrida.status)
      for (const p of item.predecessores) if (p.status) m.set(p.nome.toLowerCase(), p.status)
    }
    return m
  }, [estadoQuery.data])

  const projetos = useMemo(() => {
    const set = new Set<string>()
    pipelines.forEach(p => { if (p.project_name) set.add(p.project_name) })
    return ['Todos', ...[...set].sort()]
  }, [pipelines])

  // O próprio pipeline nunca aparece: auto-dependência é impossível de
  // escolher (MSG_SELF fica para o 422 de quem forçar por API).
  const candidatos = useMemo(() => {
    const termo = busca.trim().toLowerCase()
    return pipelines
      .filter(p => p.pipeline_name.toLowerCase() !== pipelineAtual.toLowerCase())
      .filter(p => projeto === 'Todos' || p.project_name === projeto)
      .filter(p => !termo || p.pipeline_name.toLowerCase().includes(termo)
        || (p.project_name ?? '').toLowerCase().includes(termo))
      .sort((a, b) => a.pipeline_name.localeCompare(b.pipeline_name))
  }, [pipelines, pipelineAtual, projeto, busca])

  const lista = escolhidas ?? atuaisServidor ?? []
  const alternar = (nome: string) => {
    if (travado || aplicando) return
    // Chip TRAVADO (F11/Decisão 4): linha compilada por Aguarde de malha não
    // sai por aqui — a recusa usa a MESMA mensagem que o 422 do servidor
    // daria, nomeando a malha e o nó donos.
    const cp = compiladaPorPred.get(nome.toLowerCase())
    if (cp && lista.some(n => n.toLowerCase() === nome.toLowerCase())) {
      toast.error(msgLinhaAssinada(pipelineAtual, nome, cp.malha, cp.no))
      return
    }
    setErrosItem(prev => {
      if (!(nome in prev)) return prev
      const resto = { ...prev }
      delete resto[nome]
      return resto
    })
    setEscolhidas(prev => {
      const atual = prev ?? atuaisServidor ?? []
      return atual.some(n => n.toLowerCase() === nome.toLowerCase())
        ? atual.filter(n => n.toLowerCase() !== nome.toLowerCase())
        : [...atual, nome]
    })
  }

  // D33: depender de INATIVO é armadilha — o dependente nunca vai liberar.
  const inativasEscolhidas = lista.filter(
    nome => pipelines.find(p => p.pipeline_name.toLowerCase() === nome.toLowerCase())?.active === 0)

  // ── Aplicação por DIFF, aresta a aresta (EDIÇÃO — §2.3 do desenho) ────────
  async function aplicarEdicao() {
    if (atuaisRef.current === null) atuaisRef.current = atuaisServidor ?? []
    const atuais = atuaisRef.current
    const finais = lista
    const adicionadas = finais.filter(n => !atuais.some(a => a.toLowerCase() === n.toLowerCase()))
    const removidas = atuais.filter(a => !finais.some(n => n.toLowerCase() === a.toLowerCase()))
    const total = adicionadas.length + removidas.length
    if (total === 0) { onConfirmar(finais); onClose(); return }
    setAplicando(true)
    let aplicadas = 0
    let republicar = false
    // O que JÁ está gravado — atualizado item a item, para uma segunda
    // tentativa (após erro parcial) calcular o diff certo.
    let gravadas = [...atuais]
    const erros: Record<string, string> = {}
    for (const nome of adicionadas) {
      try {
        const r = await apiFetch<{ ok: boolean; ja_existia: boolean; dag_config_pendente?: boolean }>(
          '/dependencias', {
            method: 'POST',
            body: JSON.stringify({ pipeline_name: pipelineAtual, depende_de: nome }),
          })
        if (r.dag_config_pendente) republicar = true
        gravadas = [...gravadas, nome]
        aplicadas += 1
      } catch (err) {
        // 422 (ciclo/inexistente/self) chega com o detail pt-BR do servidor —
        // a autoridade; o texto aparece INLINE no item e o modal fica aberto.
        const httpErr = err as Error & { status?: number }
        erros[nome] = httpErr.message || 'Erro ao criar a dependência'
      }
    }
    for (const nome of removidas) {
      try {
        const r = await apiFetch<{ ok: boolean; dag_config_pendente?: boolean }>('/dependencias', {
          method: 'DELETE',
          body: JSON.stringify({ pipeline_name: pipelineAtual, depende_de: nome }),
        })
        if (r.dag_config_pendente) republicar = true
        gravadas = gravadas.filter(a => a.toLowerCase() !== nome.toLowerCase())
        aplicadas += 1
      } catch (err) {
        const httpErr = err as Error & { status?: number }
        if (httpErr.status === 404) {
          // Já não existia no servidor (removida por outra tela/pessoa):
          // o estado final é o mesmo — segue.
          gravadas = gravadas.filter(a => a.toLowerCase() !== nome.toLowerCase())
          aplicadas += 1
        } else {
          erros[nome] = httpErr.message || 'Erro ao excluir a dependência'
        }
      }
    }
    atuaisRef.current = gravadas
    setAplicando(false)
    // A dependência é real e global: malhas, lista de pipelines (badge de
    // publicação pendente) e o próprio estado precisam refletir já.
    qc.invalidateQueries({ queryKey: ['malha'] })
    qc.invalidateQueries({ queryKey: ['pipelines'] })
    qc.invalidateQueries({ queryKey: ['deps-estado'] })
    if (Object.keys(erros).length > 0) {
      setErrosItem(erros)
      toast.error(`${aplicadas} de ${total} aplicadas — veja os itens marcados.`)
      return   // modal ABERTO: o usuário decide corrigir ou cancelar
    }
    toast.success(total === 1 ? 'Dependência aplicada.' : `${total} dependências aplicadas.`)
    if (republicar) toast.info(msgRepublicar(pipelineAtual))
    onConfirmar(finais)
    onClose()
  }

  function confirmar() {
    if (isEdit) { void aplicarEdicao(); return }
    onConfirmar(lista)
    onClose()
  }

  const carregando = carregandoPipes || (isEdit && atuaisServidor === null)

  return (
    <Modal open onClose={onClose} title="Escolher dependências" size="lg">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-dim">
          Este pipeline só vai iniciar depois que <strong className="text-ink">todos</strong> os
          escolhidos concluírem com sucesso na mesma data de referência.
        </p>
        {isEdit && !travado && (
          <p className="text-[11px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-800/40 rounded-lg px-3 py-2">
            Em edição a dependência é <strong>real e global</strong>: “Aplicar” grava na hora,
            independente do “Salvar alterações” do assistente — cancelar o assistente depois não desfaz.
          </p>
        )}

        {sem067 && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/15 px-3 py-2">
            <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <p className="text-[11px] text-amber-800 dark:text-amber-300">
              migration 067 pendente — {isEdit
                ? 'a edição de dependências está desabilitada neste ambiente; os chips abaixo vêm do espelho CSV, somente leitura.'
                : 'o estado dos predecessores não está disponível neste ambiente.'}
            </p>
          </div>
        )}

        {/* Escolhidas primeiro: o resultado da ação fica visível sem rolar.
            O chip ganha o badge de estado do predecessor na data corrente. */}
        {lista.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {lista.map(nome => {
              const st = statusPorPipeline.get(nome.toLowerCase())
              const estilo = st ? estiloStatus(st) : null
              // Chip TRAVADO (F11/Decisão 4): compilada por Aguarde de malha —
              // cadeado no lugar do X, nomeando a malha dona no tooltip.
              const cp = compiladaPorPred.get(nome.toLowerCase())
              return (
                <span key={nome} className="inline-flex flex-col gap-0.5">
                  <span
                    className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full border border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 text-[11px] text-blue-700 dark:text-blue-300">
                    <span className="font-mono">{nome}</span>
                    {estilo && (
                      <span className={`inline-flex items-center gap-1 rounded border px-1 py-px text-[9px] font-bold ${estilo.badge}`}
                        title={`Última execução na data corrente: ${estilo.rotulo}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${estilo.dot}`} />
                        {estilo.rotulo}
                      </span>
                    )}
                    {cp ? (
                      <span title={msgLinhaAssinada(pipelineAtual, nome, cp.malha, cp.no)}>
                        <Lock size={11} className="text-dim" />
                      </span>
                    ) : !travado && (
                      <button onClick={() => alternar(nome)} aria-label={`Remover ${nome}`}
                        className="hover:text-red-600 dark:hover:text-red-400">
                        <X size={12} />
                      </button>
                    )}
                  </span>
                  {errosItem[nome] && (
                    <span className="text-[10px] text-red-600 dark:text-red-400 max-w-[280px]">
                      {errosItem[nome]}
                    </span>
                  )}
                </span>
              )
            })}
          </div>
        )}

        {inativasEscolhidas.length > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/15 px-3 py-2">
            <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <p className="text-[11px] text-amber-800 dark:text-amber-300">
              {inativasEscolhidas.join(', ')} {inativasEscolhidas.length === 1 ? 'está inativo' : 'estão inativos'} —
              enquanto seguir assim, este pipeline não vai ser liberado.
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-dim" />
            <input
              value={busca}
              onChange={e => setBusca(e.target.value)}
              placeholder="Buscar por nome ou projeto"
              aria-label="Buscar pipeline"
              className="w-full bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <select
            value={projeto}
            onChange={e => setProjeto(e.target.value)}
            aria-label="Filtrar por projeto"
            className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {projetos.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <div className="border border-edge rounded-lg divide-y divide-edge max-h-[42vh] overflow-y-auto">
          {carregando && (
            <p className="px-3 py-6 text-center text-xs text-dim">Carregando pipelines…</p>
          )}
          {!carregando && candidatos.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-dim">
              Nenhum pipeline encontrado com esse filtro.
            </p>
          )}
          {!carregando && candidatos.map(p => {
            const marcado = lista.some(n => n.toLowerCase() === p.pipeline_name.toLowerCase())
            // Ciclo detectado client-side sobre o grafo GLOBAL — o candidato
            // fica desabilitado COM a explicação (mesma mensagem do 422 do
            // servidor), em vez de deixar o erro para o Aplicar (D33).
            const fechaCiclo = !marcado
              && criaCiclo(arestasGlobais, p.pipeline_name, pipelineAtual)
            // Linha compilada por Aguarde de malha (F11): desmarcar por aqui
            // também é recusado — mesmo tratamento do chip travado.
            const cpCand = marcado
              ? compiladaPorPred.get(p.pipeline_name.toLowerCase()) : undefined
            const desabilitado = travado || fechaCiclo || !!cpCand
            return (
              <button
                key={p.pipeline_name}
                onClick={() => { if (!desabilitado) alternar(p.pipeline_name) }}
                disabled={desabilitado}
                aria-pressed={marcado}
                title={cpCand
                  ? msgLinhaAssinada(pipelineAtual, p.pipeline_name, cpCand.malha, cpCand.no)
                  : fechaCiclo ? msgCiclo(pipelineAtual, p.pipeline_name) : undefined}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                  marcado ? 'bg-blue-50 dark:bg-blue-900/20'
                    : desabilitado ? 'opacity-50 cursor-not-allowed'
                      : 'hover:bg-edge/30'
                }`}
              >
                <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                  marcado ? 'bg-[#1A5FA8] border-[#1A5FA8] text-white' : 'border-edge'
                }`}>
                  {marcado && <Check size={11} />}
                  {!marcado && fechaCiclo && <Ban size={11} className="text-dim" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-[11px] text-ink break-all block">{p.pipeline_name}</span>
                  {fechaCiclo && (
                    <span className="text-[10px] text-amber-700 dark:text-amber-400 block">
                      {msgCiclo(pipelineAtual, p.pipeline_name)}
                    </span>
                  )}
                  {cpCand && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-dim">
                      <Lock size={10} /> compilada pelo Aguarde #{cpCand.no} da
                      malha '{cpCand.malha}' — edite pelo desenho da malha
                    </span>
                  )}
                </span>
                <span className="text-[10px] text-dim shrink-0">{p.project_name ?? '—'}</span>
                {p.active === 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-edge text-dim shrink-0">inativo</span>
                )}
              </button>
            )
          })}
        </div>

        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="text-xs text-dim">
            {lista.length === 0 ? 'Nenhuma dependência'
              : lista.length === 1 ? '1 dependência'
              : `${lista.length} dependências`}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose} disabled={aplicando}>Cancelar</Button>
            <Button onClick={confirmar} loading={aplicando} disabled={travado || carregando}
              title={travado ? 'Edição indisponível até a migration 067 ser aplicada' : undefined}>
              {isEdit ? 'Aplicar mudanças' : 'Confirmar'}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
