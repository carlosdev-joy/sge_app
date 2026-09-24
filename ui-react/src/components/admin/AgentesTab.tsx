// Admin › Agentes (F3 da spec docs/spec-agentes-datastage.md).
//
// Estrutura (reestruturação de 25/09, a pedido do usuário — a aba crescia
// ~1.000 px por agente novo): "Configuração geral" (interruptor geral +
// "Gateway e limites" recolhido) → a tabela dos agentes, que lidera → o
// DETALHE do agente escolhido em "Gerenciar", com as abas Acesso (quem usa +
// curadores) e Prompt. Um agente por vez; a altura não depende de quantos são.
//
// Duas metades:
//   1. CONFIG — os dois interruptores (o geral e o do agente), o campo do
//      gateway, o texto do aviso de cadastro, o teto de sessões SSH e a
//      validade dos fatos. Tudo por `POST /agentes/admin/config`, que valida
//      e devolve 422 com `detail.errors` quando algo não passa.
//   2. ACESSO POR AGENTE — quem pode usar cada agente, com incluir e remover.
//      A concessão é usuário a usuário (nunca por perfil — risco 26), e só a
//      quem o PERFIL já elegibiliza; `perfis_elegiveis` vem do backend junto
//      com a config, para não virar uma 2ª lista à mão aqui.
//
// CUIDADO com `user_perm_set`: ele SUBSTITUI a lista inteira de permissões
// extras do usuário (DELETE + INSERT). Incluir/remover um agente exige ler as
// atuais e reenviar o conjunto completo — mandar só `[agente_datastage]`
// apagaria silenciosamente qualquer outra permissão extra que a pessoa tenha.
import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { mensagemDeErro } from '../../lib/agentes'
import { PromptAgente } from './PromptAgente'
import { CadastroAgentes } from './CadastroAgentes'
import { Q_AGENTES_ADMIN, type AgentesAdminResposta } from '../../lib/agentes'
import { Button } from '../ui/Button'
import { InfoBanner } from '../ui/InfoBanner'
import { Input, Select } from '../ui/Input'
import { Switch } from '../ui/Switch'
import { toast } from '../ui/Toast'

interface AgenteAdmin {
  id: string
  nome: string
  recurso: string
  recurso_curador: string
  config_enabled: string
  perfis_elegiveis: string[]
}
/** O que as seções de acesso e o Prompt precisam — do código OU da tela (spec admin B3). */
interface AgenteComAcesso {
  id: string
  nome: string
  recurso: string
  /** `null`: agente só de conversa — sem curadoria. */
  recurso_curador: string | null
  perfis_elegiveis: string[]
  /** Só os criados pela tela podem ser 'perfil'. */
  acesso?: 'manual' | 'perfil'
}
interface ConfigResposta {
  sucesso: boolean
  config: Record<string, string>
  agentes: AgenteAdmin[]
}
interface UsuarioAdmin {
  matricula: string
  perfil: string
  primeiro_nome: string | null
  ultimo_nome: string | null
  ativo: boolean
}

const Q_CONFIG = ['agentes-admin-config'] as const
const Q_USUARIOS = ['admin-usuarios'] as const
const Q_PERMS = ['admin-user-perms'] as const

const adminPost = <T,>(action: string, extra: Record<string, unknown> = {}) =>
  apiFetch<T>('/admin', { method: 'POST', body: JSON.stringify({ action, ...extra }) })

function nomeCompleto(u: UsuarioAdmin) {
  return [u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || u.matricula
}

export function AgentesTab() {
  const qc = useQueryClient()
  const config = useQuery<ConfigResposta>({
    queryKey: Q_CONFIG, queryFn: () => apiFetch('/agentes/admin/config'),
  })
  const usuarios = useQuery<{ usuarios: UsuarioAdmin[] }>({
    queryKey: Q_USUARIOS, queryFn: () => adminPost('user_list'),
  })
  const perms = useQuery<{ permissoes: Record<string, string[]> }>({
    queryKey: Q_PERMS, queryFn: () => adminPost('user_perm_list'),
  })
  // Os criados pela tela (spec admin B3) — o mesmo cache da seção Cadastro.
  const doBanco = useQuery<AgentesAdminResposta>({
    queryKey: Q_AGENTES_ADMIN, queryFn: () => apiFetch('/agentes/admin/agentes'),
  })

  const [rascunho, setRascunho] = useState<Record<string, string> | null>(null)
  const [aIncluir, setAIncluir] = useState<Record<string, string>>({})
  // O agente aberto no detalhe (um por vez) e a seção dele.
  const [selecionado, setSelecionado] = useState<string | null>(null)
  const [secao, setSecao] = useState<'acesso' | 'prompt'>('acesso')
  // O prompt aberto tem texto NÃO salvo? (as duas abas ficam montadas; só
  // trocar de agente, fechar ou Esc desmontam — e aí pedimos confirmação).
  const [promptSujo, setPromptSujo] = useState(false)
  // "Gateway e limites": o estado de aberto é do usuário (controlado), para
  // salvar/descartar não recolher a seção por baixo dele.
  const [limitesAbertos, setLimitesAbertos] = useState(false)
  const tituloRef = useRef<HTMLHeadingElement>(null)
  // Abrir o detalhe leva o foco ao título dele (leitor de tela anuncia o agente).
  useEffect(() => {
    if (selecionado) tituloRef.current?.focus()
  }, [selecionado])

  // Base do servidor + o que está sendo editado (o rascunho é parcial).
  const cfg = { ...(config.data?.config ?? {}), ...(rascunho ?? {}) }
  const agentes = config.data?.agentes ?? []
  // "Quem pode usar", "Curadores" e o Prompt valem para TODOS: os do código
  // (da config, com o interruptor próprio) e os criados pela tela.
  const todos: AgenteComAcesso[] = [
    ...agentes,
    ...(doBanco.data?.agentes ?? []).filter(a => a.origem === 'banco').map(a => ({
      id: a.id, nome: a.nome, recurso: a.recurso, recurso_curador: a.recurso_curador,
      perfis_elegiveis: a.perfis, acesso: a.acesso,
    })),
  ]

  async function invalidar() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: Q_CONFIG }),
      qc.invalidateQueries({ queryKey: Q_PERMS }),
      // a TELA do usuário lê estas duas — ligar/desligar tem de refletir
      // na mesma sessão, sem F5.
      qc.invalidateQueries({ queryKey: ['agentes-catalogo'] }),
      qc.invalidateQueries({ queryKey: ['agentes-status'] }),
    ])
  }

  // `boolean` nos interruptores (nunca '1'/'0' como string): o backend
  // testa a veracidade do valor, e a string "0" é VERDADEIRA em Python —
  // desligar pela tela ligava no banco (achado da revisão adversarial da
  // F3). O backend também passou a entender "0"/"false", mas o cliente
  // manda o tipo certo: é o padrão de `MaestroTab`.
  const salvar = useMutation({
    mutationFn: (valores: Record<string, string | boolean>) =>
      apiFetch<{ sucesso: boolean }>('/agentes/admin/config', {
        method: 'POST', body: JSON.stringify(valores),
      }),
    onSuccess: async () => {
      toast.success('Configuração dos agentes salva')
      setRascunho(null)
      await invalidar()
    },
    onError: (e: unknown) => toast.error(mensagemDeErro(e, 'Não foi possível salvar a configuração')),
  })

  const trocarAcesso = useMutation({
    mutationFn: async ({ matricula, recurso, conceder }:
      { matricula: string; recurso: string; conceder: boolean }) => {
      // Lê as permissões ATUAIS e reenvia o conjunto inteiro: `user_perm_set`
      // substitui tudo (ver comentário no topo do arquivo).
      //
      // SEM a lista carregada não dá para montar esse conjunto: um
      // `?? []` aqui viraria "a pessoa só tem este recurso" e o DELETE +
      // INSERT apagaria TODAS as outras permissões extras dela, sem erro
      // na tela. A UI já bloqueia o botão, mas a guarda fica aqui também —
      // é o último ponto antes do efeito destrutivo (achado da revisão
      // adversarial da F3).
      if (!perms.data?.permissoes) {
        throw new Error('A lista de permissões ainda não carregou — recarregue a página e tente de novo.')
      }
      const atuais = new Set(perms.data.permissoes[matricula] ?? [])
      if (conceder) atuais.add(recurso)
      else atuais.delete(recurso)
      return adminPost('user_perm_set', { matricula, permissoes: [...atuais] })
    },
    // `onSettled`: um 422 quer dizer que a lista da tela está defasada —
    // ressincroniza também no erro.
    onSettled: invalidar,
    onSuccess: (_r, v) => toast.success(v.conceder ? 'Acesso concedido' : 'Acesso removido'),
    onError: (e: unknown) => toast.error(mensagemDeErro(e, 'Não foi possível alterar o acesso')),
  })

  const porRecurso = useMemo(() => {
    const mapa: Record<string, UsuarioAdmin[]> = {}
    const todos = usuarios.data?.usuarios ?? []
    const permsMapa = perms.data?.permissoes ?? {}
    for (const u of todos) {
      for (const rec of permsMapa[u.matricula] ?? []) {
        (mapa[rec] ??= []).push(u)
      }
    }
    return mapa
  }, [usuarios.data, perms.data])

  if (config.isLoading) return <p className="text-sm text-dim">Carregando…</p>
  if (config.isError || !config.data) {
    return (
      <InfoBanner icon="⚠">
        {`Falha ao carregar a configuração dos agentes: ${mensagemDeErro(config.error, 'erro desconhecido')}`}
      </InfoBanner>
    )
  }

  // O rascunho guarda SÓ o que o formulário edita. Antes ele partia de
  // `{...cfg}`, então "Salvar alterações" reenviava `agentes_enabled` junto
  // — e, com o bug do '0', RELIGAVA os agentes ao salvar qualquer campo.
  // Os interruptores têm caminho próprio (`salvar.mutate` no onChange).
  const editar = (k: string, v: string) => setRascunho({ ...(rascunho ?? {}), [k]: v })
  const ligado = (k: string) => cfg[k] === '1'
  // Conceder/remover exige a lista de permissões carregada — ver a guarda
  // em `trocarAcesso`. Sem ela a seção mostra o motivo e não deixa clicar,
  // em vez de parecer que "ninguém tem acesso".
  const acessoPronto = !!perms.data?.permissoes && !!usuarios.data?.usuarios

  const agenteSel = todos.find(a => a.id === selecionado) ?? null
  const cadastroSel = (doBanco.data?.agentes ?? []).find(a => a.id === selecionado) ?? null
  const papeisDe = (ag: AgenteComAcesso) => [
    // Dois papéis, a MESMA política (perfil elegível + concessão usuário a
    // usuário): usar o agente e ser curador dos aprendizados dele (F6).
    { chave: `${ag.id}:uso`, recurso: ag.recurso, titulo: 'Quem pode usar',
      texto: 'Concedido usuário a usuário, nunca por perfil.' },
    // Curadoria só existe em agente com ferramentas (os só de conversa não geram aprendizados).
    ...(ag.recurso_curador ? [{ chave: `${ag.id}:curador`, recurso: ag.recurso_curador, titulo: 'Curadores',
      texto: 'Validam, rejeitam e marcam como obsoletos os aprendizados do agente, na aba Curadoria da tela Agentes — o curador também precisa estar em “Quem pode usar” para abrir a tela.' }] : []),
  ]

  /** Sair do agente aberto descarta o rascunho do prompt: confirma antes. */
  function podeSair(): boolean {
    return !promptSujo
      || window.confirm('O prompt deste agente tem alterações não salvas. Sair e descartá-las?')
  }

  function gerenciar(id: string) {
    if (selecionado !== null && !podeSair()) return
    setSelecionado(atual => (atual === id ? null : id))
    setSecao('acesso')
  }

  function fecharDetalhe() {
    const id = selecionado
    if (!podeSair()) return
    setSelecionado(null)
    // O foco volta para o "Gerenciar" da linha — quem usa teclado não se perde.
    if (id) requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-agentes-gerenciar="${id}"]`)?.focus())
  }

  // Abas do detalhe: setas trocam, como num tablist de verdade.
  const SECOES = [{ id: 'acesso', rotulo: 'Acesso' }, { id: 'prompt', rotulo: 'Prompt' }] as const
  function teclaNaAba(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const i = SECOES.findIndex(x => x.id === secao)
    const prox = SECOES[(i + (e.key === 'ArrowRight' ? 1 : SECOES.length - 1)) % SECOES.length].id
    setSecao(prox)
    requestAnimationFrame(() => document.getElementById(`agente-aba-${prox}`)?.focus())
  }

  return (
    // Um agente por vez (reestruturação de 25/09): a tabela lidera; o detalhe
    // — acesso, curadores e prompt — abre embaixo dela, só do agente escolhido.
    // Antes, cada agente novo somava três seções à aba (~1.000 px por agente).
    <div className="flex flex-col gap-8" data-agentes-admin>
      <section className="bg-panel border border-edge rounded-lg shadow-sm" data-agentes-geral>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">Configuração geral</h3>
            <p className="text-xs text-dim mt-0.5">Vale para todos os agentes.</p>
          </div>
          <Switch
            label={ligado('agentes_enabled') ? 'Agentes ligados' : 'Agentes desligados'}
            checked={ligado('agentes_enabled')}
            disabled={salvar.isPending}
            onChange={e => salvar.mutate({ agentes_enabled: e.target.checked })}
            hint="Interruptor geral. Desligado, ninguém vê agente nenhum — nem o administrador."
            data-agentes-interruptor-geral
          />
        </div>
        {/* Usado raramente: começa fechado; aberto/fechado é escolha do usuário. */}
        <details className="group border-t border-edge" open={limitesAbertos}
                 onToggle={e => setLimitesAbertos(e.currentTarget.open)} data-agentes-limites>
          <summary className="flex items-center gap-2 px-4 py-2.5 cursor-pointer select-none text-sm text-ink
                              hover:bg-canvas focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]
                              [&::-webkit-details-marker]:hidden list-none">
            <ChevronRight className="w-4 h-4 text-dim transition-transform duration-150 group-open:rotate-90
                                     motion-reduce:transition-none" aria-hidden="true" />
            <span className="font-medium">Gateway e limites</span>
            <span className="text-xs text-dim truncate">
              identidade no gateway, aviso de cadastro, sessões SSH, validade dos fatos, tempos da consulta a banco
            </span>
            {rascunho && (
              <span className="ml-auto shrink-0 text-[11px] px-1.5 py-0.5 rounded border border-amber-600/40
                               text-amber-700 dark:text-amber-300 dark:border-amber-300/40" data-agentes-limites-pendente>
                alterações não salvas
              </span>
            )}
          </summary>
          <div className="px-4 pb-4 pt-1 flex flex-col gap-4">
        <Input
          label="Campo da identidade no gateway"
          value={cfg.agentes_gateway_campo_usuario ?? ''}
          onChange={e => editar('agentes_gateway_campo_usuario', e.target.value)}
          placeholder="header:X-User  ou  body:user"
          hint="Onde vai a identidade de quem pergunta (cvp-<matrícula>). Vazio: o agente não roda."
        />
        <Input
          label="Aviso de cadastro no gateway"
          value={cfg.agentes_cadastro_texto ?? ''}
          onChange={e => editar('agentes_cadastro_texto', e.target.value)}
          hint="Mostrado a quem ainda não tem cadastro. Diga o canal real (chamado, e-mail) — até 500 caracteres."
        />
        <div className="flex flex-wrap gap-4">
          <Input
            label="Sessões SSH simultâneas"
            type="number" min={1} max={50}
            value={cfg.agentes_ssh_max ?? ''}
            onChange={e => editar('agentes_ssh_max', e.target.value)}
            hint="Teto de consultas ao vivo no DataStage ao mesmo tempo (1 a 50)."
          />
          <Input
            label="Validade dos fatos (dias)"
            type="number" min={1} max={365}
            value={cfg.agentes_fato_validade_dias ?? ''}
            onChange={e => editar('agentes_fato_validade_dias', e.target.value)}
            hint="Depois disso o agente reconsulta em vez de confiar no que já sabia."
          />
          <Input
            label="Tempo para conectar ao banco (s)"
            type="number" min={5} max={60}
            value={cfg.agentes_banco_conexao_s ?? ''}
            onChange={e => editar('agentes_banco_conexao_s', e.target.value)}
            hint="Consulta a banco: quanto esperar o servidor aceitar a conexão (5 a 60). Vale também para listar os bancos aqui no admin."
            data-agentes-banco-conexao
          />
          <Input
            label="Tempo máximo de cada consulta (s)"
            type="number" min={5} max={120}
            value={cfg.agentes_banco_consulta_s ?? ''}
            onChange={e => editar('agentes_banco_consulta_s', e.target.value)}
            hint="Consulta a banco: passou disso, a consulta é cancelada no servidor (5 a 120). A pergunta inteira continua limitada a 4 minutos."
            data-agentes-banco-consulta
          />
        </div>
            {rascunho && (
              <div className="flex items-center gap-2">
                <Button onClick={() => salvar.mutate(rascunho)} loading={salvar.isPending}>
                  Salvar alterações
                </Button>
                <Button variant="ghost" onClick={() => setRascunho(null)} disabled={salvar.isPending}>
                  Descartar
                </Button>
              </div>
            )}
          </div>
        </details>
      </section>

      {/* Cadastro dos agentes (spec docs/spec-agentes-admin.md, B3) — o índice da aba. */}
      <CadastroAgentes
        selecionado={selecionado}
        onGerenciar={gerenciar}
        interruptorDoCodigo={id => {
          const ag = agentes.find(a => a.id === id)
          if (!ag) return null
          return (
            <span className="inline-flex flex-col items-start gap-0.5">
              <Switch
                label={ligado(ag.config_enabled) ? 'ligado' : 'desligado'}
                aria-label={ligado(ag.config_enabled) ? `${ag.nome}: ligado` : `${ag.nome}: desligado`}
                aria-describedby={ligado('agentes_enabled') ? undefined : 'agentes-geral-desligado'}
                checked={ligado(ag.config_enabled)}
                disabled={salvar.isPending || !ligado('agentes_enabled')}
                onChange={e => salvar.mutate({ [ag.config_enabled]: e.target.checked })}
              />
              {/* Texto visível, não balão: a tabela tem rolagem horizontal e
                  cortaria um balão (o mesmo problema da #441). */}
              {!ligado('agentes_enabled') && (
                <span id="agentes-geral-desligado" className="text-[11px] text-dim" data-agentes-geral-desligado>
                  o interruptor geral está desligado
                </span>
              )}
            </span>
          )
        }}
      />

      {agenteSel && (
        <section
          id="agente-detalhe"
          aria-labelledby="agente-detalhe-titulo"
          className="bg-panel border border-edge rounded-lg shadow-sm"
          data-agentes-detalhe={agenteSel.id}
          onKeyDown={e => {
            // Esc fecha o painel — mas não quando vem de um campo (o usuário
            // está digitando) nem de um modal aberto dentro dele (Ver versão,
            // Restaurar): no React o evento do portal sobe até aqui.
            const alvo = e.target as HTMLElement
            if (e.key === 'Escape' && !e.defaultPrevented && !alvo.closest('textarea, input, select, [role="dialog"]')) {
              fecharDetalhe()
            }
          }}
        >
          <header className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4">
            <div className="min-w-0">
              <h3 id="agente-detalhe-titulo" ref={tituloRef} tabIndex={-1}
                  className="text-base font-semibold text-ink focus:outline-none">
                {agenteSel.nome}
              </h3>
              <p className="text-xs text-dim mt-0.5">
                {agenteSel.id}
                {` · acesso ${agenteSel.acesso === 'perfil' ? 'por perfil' : 'manual'}`}
                {` · perfis ${agenteSel.perfis_elegiveis.join(', ') || '—'}`}
                {cadastroSel?.bancos?.length ? ` · ${cadastroSel.bancos.length === 1 ? '1 banco' : `${cadastroSel.bancos.length} bancos`}` : ''}
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={fecharDetalhe} data-agentes-detalhe-fechar>Fechar</Button>
          </header>

          <div role="tablist" aria-label={`Seções de ${agenteSel.nome}`}
               className="flex gap-1 px-4 mt-3 border-b border-edge">
            {SECOES.map(x => (
              <button
                key={x.id}
                id={`agente-aba-${x.id}`}
                type="button"
                role="tab"
                aria-selected={secao === x.id}
                aria-controls={`agente-painel-${x.id}`}
                tabIndex={secao === x.id ? 0 : -1}
                onClick={() => setSecao(x.id)}
                onKeyDown={teclaNaAba}
                className={`-mb-px h-9 px-3 text-sm border-b-2 transition-colors focus:outline-none
                            focus-visible:ring-2 focus-visible:ring-[#1A5FA8] rounded-t
                            ${secao === x.id
                              ? 'border-[#1A5FA8] text-ink font-medium dark:border-blue-400'
                              : 'border-transparent text-dim hover:text-ink'}`}
              >
                {x.rotulo}
              </button>
            ))}
          </div>

          {/* As duas abas ficam MONTADAS (a inativa só escondida): trocar de aba
              não perde o rascunho do prompt. `key`: outro agente = outro rascunho. */}
          <div id="agente-painel-prompt" role="tabpanel" aria-labelledby="agente-aba-prompt"
               hidden={secao !== 'prompt'} className="p-4">
            <PromptAgente key={agenteSel.id} agente={agenteSel} embutido onSujo={setPromptSujo} />
          </div>
          <div id="agente-painel-acesso" role="tabpanel" aria-labelledby="agente-aba-acesso"
               hidden={secao !== 'acesso'} className="p-4">
            {(
              <div className="flex flex-col gap-4">
                <p className="text-xs text-dim max-w-[75ch]">
                  {`Só usuários ativos dos perfis elegíveis (${agenteSel.perfis_elegiveis.join(', ') || '—'}) aparecem para conceder; `
                    + 'o administrador já tem acesso por acao_admin, sem precisar de concessão.'}
                </p>
                <div className="grid gap-6 lg:grid-cols-2">
                  {papeisDe(agenteSel).map(papel => {
                    const ag = agenteSel
                    // Acesso POR PERFIL não tem concessão individual: a seção explica em
                    // vez de oferecer um "Conceder" que não mudaria nada.
                    if (ag.acesso === 'perfil' && papel.chave.endsWith(':uso')) {
                      return (
                        <section key={papel.chave} className="flex flex-col gap-1"
                                 data-agentes-acesso={papel.chave}>
                          <h4 className="text-sm font-semibold text-ink">{papel.titulo}</h4>
                          <p className="text-sm text-ink">
                            {`Todo usuário dos perfis ${ag.perfis_elegiveis.join(', ')} que tenha a tela Agentes.`}
                          </p>
                          <p className="text-xs text-dim">Acesso por perfil — sem concessão individual. Mude em Agentes › Editar.</p>
                        </section>
                      )
                    }
                    const comAcesso = porRecurso[papel.recurso] ?? []
                    const elegiveis = (usuarios.data?.usuarios ?? []).filter(
                      u => u.ativo
                        && ag.perfis_elegiveis.includes(u.perfil)
                        && !comAcesso.some(c => c.matricula === u.matricula))
                    return (
                      <section key={papel.chave} className="flex flex-col gap-3"
                               data-agentes-acesso={papel.chave}>
                        <div>
                          <h4 className="text-sm font-semibold text-ink">{papel.titulo}</h4>
                          <p className="text-xs text-dim mt-0.5">{papel.texto}</p>
                        </div>

                        {!acessoPronto ? (
                          <p className="text-sm text-dim" data-agentes-acesso-indisponivel>
                            {perms.isError || usuarios.isError
                              ? `Não foi possível carregar quem tem acesso: ${mensagemDeErro(perms.error ?? usuarios.error, 'erro desconhecido')}. Recarregue a página.`
                              : 'Carregando quem tem acesso…'}
                          </p>
                        ) : comAcesso.length === 0 ? (
                          <p className="text-sm text-dim">Ninguém além dos administradores.</p>
                        ) : (
                          <ul className="flex flex-col divide-y divide-edge">
                            {comAcesso.map(u => (
                              <li key={u.matricula} className="flex items-center justify-between gap-3 py-2">
                                <span className="text-sm text-ink">
                                  {nomeCompleto(u)} <span className="text-dim">· {u.matricula} · {u.perfil}</span>
                                </span>
                                <Button
                                  variant="ghost" size="sm"
                                  disabled={trocarAcesso.isPending || !acessoPronto}
                                  onClick={() => trocarAcesso.mutate(
                                    { matricula: u.matricula, recurso: papel.recurso, conceder: false })}
                                >
                                  Remover
                                </Button>
                              </li>
                            ))}
                          </ul>
                        )}

                        <div className="flex flex-wrap items-end gap-2 pt-1">
                          <Select
                            label="Incluir usuário"
                            value={aIncluir[papel.chave] ?? ''}
                            disabled={!acessoPronto}
                            onChange={e => setAIncluir({ ...aIncluir, [papel.chave]: e.target.value })}
                          >
                            <option value="">Selecione…</option>
                            {elegiveis.map(u => (
                              <option key={u.matricula} value={u.matricula}>
                                {nomeCompleto(u)} · {u.matricula}
                              </option>
                            ))}
                          </Select>
                          <Button
                            disabled={!aIncluir[papel.chave] || trocarAcesso.isPending || !acessoPronto}
                            loading={trocarAcesso.isPending}
                            onClick={() => {
                              const mat = aIncluir[papel.chave]
                              if (!mat) return
                              trocarAcesso.mutate({ matricula: mat, recurso: papel.recurso, conceder: true })
                              setAIncluir({ ...aIncluir, [papel.chave]: '' })
                            }}
                          >
                            Conceder
                          </Button>
                          {acessoPronto && elegiveis.length === 0 && (
                            <p className="text-xs text-dim pb-2">
                              Nenhum usuário ativo com perfil elegível fora da lista.
                            </p>
                          )}
                        </div>
                      </section>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
