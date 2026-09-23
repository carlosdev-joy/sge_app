// Admin › Agentes (F3 da spec docs/spec-agentes-datastage.md).
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
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { mensagemDeErro } from '../../lib/agentes'
import { PromptAgente } from './PromptAgente'
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

  const [rascunho, setRascunho] = useState<Record<string, string> | null>(null)
  const [aIncluir, setAIncluir] = useState<Record<string, string>>({})

  // Base do servidor + o que está sendo editado (o rascunho é parcial).
  const cfg = { ...(config.data?.config ?? {}), ...(rascunho ?? {}) }
  const agentes = config.data?.agentes ?? []

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

  return (
    <div className="flex flex-col gap-6" data-agentes-admin>
      <section className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-ink">Interruptores</h3>
        <Switch
          label={ligado('agentes_enabled') ? 'Agentes ligados' : 'Agentes desligados'}
          checked={ligado('agentes_enabled')}
          disabled={salvar.isPending}
          onChange={e => salvar.mutate({ agentes_enabled: e.target.checked })}
          hint="Interruptor geral. Desligado, ninguém vê agente nenhum — nem o administrador."
          data-agentes-interruptor-geral
        />
        {agentes.map(ag => (
          <Switch
            key={ag.id}
            label={ligado(ag.config_enabled) ? `${ag.nome}: ligado` : `${ag.nome}: desligado`}
            checked={ligado(ag.config_enabled)}
            disabled={salvar.isPending || !ligado('agentes_enabled')}
            onChange={e => salvar.mutate({ [ag.config_enabled]: e.target.checked })}
            hint={`Só vale com o interruptor geral ligado. Elegível a: ${ag.perfis_elegiveis.join(', ')}.`}
          />
        ))}
      </section>

      <section className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-ink">Gateway e limites</h3>
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
      </section>

      {agentes.flatMap(ag => [
        // Dois papéis, a MESMA política (perfil elegível + concessão usuário a
        // usuário): usar o agente e ser curador dos aprendizados dele (F6).
        { chave: `${ag.id}:uso`, recurso: ag.recurso, titulo: `Quem pode usar — ${ag.nome}`,
          texto: 'Concedido usuário a usuário, nunca por perfil.' },
        { chave: `${ag.id}:curador`, recurso: ag.recurso_curador, titulo: `Curadores — ${ag.nome}`,
          texto: 'Validam, rejeitam e marcam como obsoletos os aprendizados do agente, na aba Curadoria da tela Agentes — o curador também precisa estar em “Quem pode usar” para abrir a tela.' },
      ].map(papel => {
        const comAcesso = porRecurso[papel.recurso] ?? []
        const elegiveis = (usuarios.data?.usuarios ?? []).filter(
          u => u.ativo
            && ag.perfis_elegiveis.includes(u.perfil)
            && !comAcesso.some(c => c.matricula === u.matricula))
        return (
          <section key={papel.chave} className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3"
                   data-agentes-acesso={papel.chave}>
            <div>
              <h3 className="text-sm font-semibold text-ink">{papel.titulo}</h3>
              <p className="text-xs text-dim mt-0.5">
                {papel.texto} Só perfis elegíveis
                ({ag.perfis_elegiveis.join(', ')}) aparecem na lista; o administrador já tem acesso
                por `acao_admin`, sem precisar de concessão.
              </p>
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
      }))}

      {/* Prompt do domínio, com versões (spec docs/spec-agentes-admin.md A2). */}
      {agentes.map(ag => <PromptAgente key={`prompt-${ag.id}`} agente={ag} />)}
    </div>
  )
}
