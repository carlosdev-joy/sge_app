// Admin › Agentes › Cadastro (B3 da spec docs/spec-agentes-admin.md §4.5).
//
// Lista TODOS os agentes — o DataStage (do código, só leitura aqui: liga e
// desliga em "Interruptores") e os criados pela tela — e cria/edita os da
// tela. Um agente novo nasce DESATIVADO: o admin confere o prompt e o acesso
// e só então liga.
//
// As regras de negócio são do backend (422 com `code`); `problemasDoAgente`
// só as antecipa para o admin não precisar de uma ida e volta. O acesso por
// perfil nunca vale com ferramenta que toca o servidor, e o perfil `consulta`
// nunca recebe agente (D3 da spec, confirmada pelo usuário).
//
// Consulta a banco (spec ferramenta-banco C2): UM interruptor liga as duas
// ferramentas de banco; com ele, "Bancos liberados" e "Mascarar dados
// pessoais". O PUT manda SEMPRE `bancos` — é o que diz à API que a tela
// conhece a consulta a banco (sem o campo, ela preserva as de banco).
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import {
  FERRAMENTAS, FERRAMENTAS_BANCO, Q_AGENTES_ADMIN, ROTULO_ACESSO, dataHoraCurta, mensagemDeErro, normalizarFerramentas,
  problemasDoAgente, usaBanco,
  type AcessoAgente, type AgenteAdminItem, type AgentesAdminResposta, type RascunhoAgente,
} from '../../lib/agentes'
import { BancosLiberados } from './BancosLiberados'
import { Button } from '../ui/Button'
import { InfoBanner } from '../ui/InfoBanner'
import { Input, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { Switch } from '../ui/Switch'
import { toast } from '../ui/Toast'

interface PerfilAdmin { perfil_nome: string; permissoes: string[] }

const adminPost = <T,>(action: string) =>
  apiFetch<T>('/admin', { method: 'POST', body: JSON.stringify({ action }) })

const VAZIO: RascunhoAgente = {
  id: '', nome: '', descricao: '', acesso: 'manual', perfis: ['desenvolvedor'], ferramentas: [], prompt: '', motivo: '',
  bancos: [], mascarar_dados: true,
}

function resumoFerramentas(ag: Pick<AgenteAdminItem, 'ferramentas' | 'bancos'>): string {
  if (!ag.ferramentas.length) return 'só conversa'
  const nomes = ag.ferramentas.filter(f => !usaBanco([f])).map(f => FERRAMENTAS[f] ?? f)
  if (usaBanco(ag.ferramentas)) {
    const n = ag.bancos?.length ?? 0
    nomes.push(`consulta a banco (${n === 1 ? '1 banco' : `${n} bancos`})`)
  }
  return nomes.join(', ')
}

export function CadastroAgentes() {
  const qc = useQueryClient()
  const lista = useQuery<AgentesAdminResposta>({
    queryKey: Q_AGENTES_ADMIN, queryFn: () => apiFetch('/agentes/admin/agentes'),
  })
  const perfis = useQuery<{ perfis: PerfilAdmin[] }>({
    queryKey: ['admin-perfis'], queryFn: () => adminPost('perfil_list'),
  })
  // null = fechado; `id` definido = edição daquele agente
  const [form, setForm] = useState<{ rascunho: RascunhoAgente; editando: string | null } | null>(null)

  async function invalidar() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: Q_AGENTES_ADMIN }),
      // a tela do usuário e as outras seções da aba leem estes
      qc.invalidateQueries({ queryKey: ['agentes-catalogo'] }),
      qc.invalidateQueries({ queryKey: ['agentes-admin-config'] }),
      qc.invalidateQueries({ queryKey: ['agentes-admin-prompt'] }),
      qc.invalidateQueries({ queryKey: ['agentes-admin-prompt-versoes'] }),
    ])
  }

  const salvar = useMutation({
    mutationFn: ({ rascunho, editando }: { rascunho: RascunhoAgente; editando: string | null }) => {
      const comum = {
        nome: rascunho.nome, descricao: rascunho.descricao, acesso: rascunho.acesso,
        perfis: rascunho.perfis, ferramentas: rascunho.ferramentas,
        bancos: usaBanco(rascunho.ferramentas) ? rascunho.bancos : [],
        // Sem a consulta a banco, o padrão (ligado): um valor escondido na
        // tela não vai para a API — e sem banco o backend grava mesmo sem a 122.
        mascarar_dados: usaBanco(rascunho.ferramentas) ? rascunho.mascarar_dados : true,
      }
      return editando
        ? apiFetch<{ agente: AgenteAdminItem; avisos?: string[] }>(`/agentes/admin/agentes/${encodeURIComponent(editando)}`,
          { method: 'PUT', body: JSON.stringify(comum) })
        : apiFetch<{ agente: AgenteAdminItem; avisos?: string[] }>('/agentes/admin/agentes', {
          method: 'POST',
          body: JSON.stringify({ ...comum, id: rascunho.id, prompt: rascunho.prompt, motivo: rascunho.motivo }),
        })
    },
    onSuccess: async (r, v) => {
      toast.success(v.editando ? 'Agente atualizado' : `Agente “${r.agente.nome}” criado — desativado até você ligar`)
      // C6: login com escrita só AVISA — a gravação já aconteceu.
      for (const aviso of r.avisos ?? []) toast.info(aviso)
      setForm(null)
      await invalidar()
    },
    onError: (e: unknown) => toast.error(mensagemDeErro(e, 'Não foi possível salvar o agente')),
  })

  const alternar = useMutation({
    mutationFn: ({ id, ativo }: { id: string; ativo: boolean }) =>
      apiFetch(`/agentes/admin/agentes/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ ativo }) }),
    onSuccess: (_r, v) => toast.success(v.ativo ? 'Agente ligado' : 'Agente desligado'),
    onError: (e: unknown) => toast.error(mensagemDeErro(e, 'Não foi possível alterar o agente')),
    onSettled: invalidar,
  })

  if (lista.isLoading) return <p className="text-sm text-dim">Carregando os agentes…</p>
  if (lista.isError || !lista.data) {
    return (
      <InfoBanner icon="⚠">
        {`Falha ao carregar os agentes: ${mensagemDeErro(lista.error, 'erro desconhecido')}`}
      </InfoBanner>
    )
  }
  const dados = lista.data
  const idsDoCodigo = dados.agentes.filter(a => a.origem === 'codigo').map(a => a.id)

  return (
    <section className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3" data-agentes-cadastro>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">Agentes</h3>
          <p className="text-xs text-dim mt-0.5">
            O DataStage vem do código. Os criados aqui nascem desligados: confira o prompt (seção Prompt, abaixo) e
            quem pode usar antes de ligar.
          </p>
        </div>
        <Button size="sm" onClick={() => setForm({ rascunho: { ...VAZIO }, editando: null })} data-agentes-novo>
          + Novo agente
        </Button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs" data-agentes-lista>
          <thead>
            <tr className="text-left text-dim border-b border-edge">
              <th scope="col" className="py-1.5 pr-3 font-medium">Agente</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Origem</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Acesso</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Ferramentas</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Ligado</th>
              <th scope="col" className="py-1.5 font-medium" aria-label="Ações" />
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {dados.agentes.map(ag => (
              <tr key={ag.id} className="text-ink align-top" data-agentes-item={ag.id}>
                <td className="py-2 pr-3 min-w-[12rem]">
                  <div className="font-medium">{ag.nome}</div>
                  <div className="text-dim">{ag.id}</div>
                </td>
                <td className="py-2 pr-3 whitespace-nowrap">{ag.origem === 'codigo' ? 'código' : 'tela'}</td>
                <td className="py-2 pr-3 min-w-[10rem]">
                  {ag.acesso === 'perfil' ? 'por perfil' : 'manual'}
                  <span className="text-dim">{` · ${ag.perfis.join(', ') || '—'}`}</span>
                </td>
                <td className="py-2 pr-3 min-w-[10rem]">{resumoFerramentas(ag)}</td>
                <td className="py-2 pr-3">
                  {ag.origem === 'codigo' ? (
                    <span className="text-dim">{ag.ativo ? 'sim' : 'não'} (em Interruptores)</span>
                  ) : (
                    <Switch
                      label={ag.ativo ? `${ag.nome}: ligado` : `${ag.nome}: desligado`}
                      checked={ag.ativo}
                      disabled={alternar.isPending}
                      onChange={e => alternar.mutate({ id: ag.id, ativo: e.target.checked })}
                    />
                  )}
                </td>
                <td className="py-2 text-right whitespace-nowrap">
                  {ag.origem === 'banco' && (
                    <Button size="sm" variant="ghost" aria-label={`Editar ${ag.nome}`}
                            onClick={() => setForm({
                              editando: ag.id,
                              rascunho: { ...VAZIO, id: ag.id, nome: ag.nome, descricao: ag.descricao, acesso: ag.acesso,
                                          perfis: ag.perfis, ferramentas: ag.ferramentas,
                                          bancos: ag.bancos ?? [], mascarar_dados: ag.mascarar_dados ?? true },
                            })}>
                      Editar
                    </Button>
                  )}
                  {ag.atualizado_por && (
                    <div className="text-[11px] text-dim">
                      {`alterado por ${ag.atualizado_por} em ${dataHoraCurta(ag.atualizado_em)}`}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {form && (
        <FormAgente
          inicial={form.rascunho}
          editando={form.editando}
          dados={dados}
          idsDoCodigo={idsDoCodigo}
          perfis={perfis.data?.perfis ?? []}
          perfisErro={perfis.isError ? mensagemDeErro(perfis.error, 'erro desconhecido') : null}
          salvando={salvar.isPending}
          onCancelar={() => setForm(null)}
          onSalvar={r => salvar.mutate({ rascunho: r, editando: form.editando })}
        />
      )}
    </section>
  )
}

function FormAgente({ inicial, editando, dados, idsDoCodigo, perfis, perfisErro, salvando, onCancelar, onSalvar }: {
  inicial: RascunhoAgente
  editando: string | null
  dados: AgentesAdminResposta
  idsDoCodigo: string[]
  perfis: PerfilAdmin[]
  perfisErro: string | null
  salvando: boolean
  onCancelar: () => void
  onSalvar: (r: RascunhoAgente) => void
}) {
  const [r, setR] = useState<RascunhoAgente>(inicial)
  const criacao = editando === null
  const bancoLigado = usaBanco(r.ferramentas)
  const ferramentasFinais = normalizarFerramentas(r.ferramentas, [...dados.ferramentas, ...(dados.ferramentas_banco ?? [])])
  const final = { ...r, ferramentas: ferramentasFinais }
  const problemas = problemasDoAgente(final, {
    criacao, ferramentasServidor: dados.ferramentas_servidor, perfisProibidos: dados.perfis_proibidos, idsDoCodigo,
  })
  const tocaServidor = ferramentasFinais.some(f => dados.ferramentas_servidor.includes(f))
  // Acesso por perfil: o menu só aparece para quem tem a `tela_agentes`.
  const semTela = r.acesso === 'perfil'
    ? r.perfis.filter(p => p !== 'admin' && !perfis.find(x => x.perfil_nome === p)?.permissoes.includes('tela_agentes'))
    : []
  const escolhiveis = perfis.filter(p => !dados.perfis_proibidos.includes(p.perfil_nome))
  // Perfil que o agente tem mas não existe mais (excluído em Perfis): aparece
  // marcado, com aviso, para o admin DESMARCAR — sem checkbox, o PUT o
  // reenviava e o backend recusava a edição inteira (revisão da B3).
  const inexistentes = perfis.length
    ? r.perfis.filter(p => !perfis.some(x => x.perfil_nome === p) && !dados.perfis_proibidos.includes(p))
    : []
  const todosProblemas = inexistentes.length
    ? [...problemas, `O perfil ${inexistentes.join(', ')} não existe mais — desmarque para salvar.`]
    : problemas

  const alternarLista = (campo: 'perfis' | 'ferramentas', valor: string) => setR(atual => {
    const conjunto = new Set(atual[campo])
    if (conjunto.has(valor)) conjunto.delete(valor)
    else conjunto.add(valor)
    return { ...atual, [campo]: [...conjunto] }
  })

  return (
    <Modal open onClose={onCancelar} size="lg" title={criacao ? 'Novo agente' : `Editar ${inicial.nome}`}>
      <div className="flex flex-col gap-4" data-agentes-form>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label="Nome" value={r.nome} maxLength={100} onChange={e => setR({ ...r, nome: e.target.value })} />
          <Input
            label="Id"
            value={r.id}
            disabled={!criacao}
            maxLength={30}
            onChange={e => setR({ ...r, id: e.target.value.toLowerCase() })}
            ajuda={criacao ? 'Minúsculas, números e _. Não muda depois e nunca é reaproveitado.' : 'O id não muda.'}
          />
        </div>
        <Input label="Descrição" value={r.descricao} maxLength={500}
               onChange={e => setR({ ...r, descricao: e.target.value })}
               ajuda="Aparece para o usuário no topo da tela do agente." />

        <fieldset className="flex flex-col gap-2">
          <legend className="text-xs font-semibold text-ink mb-1">Ferramentas</legend>
          <label className="flex items-center gap-2 text-xs text-ink">
            <input type="checkbox" checked={r.ferramentas.length === 0}
                   onChange={() => setR({ ...r, ferramentas: [] })} />
            Nenhuma — só conversa (sem acesso a sistemas)
          </label>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5">
            {dados.ferramentas.map(f => (
              <label key={f} className="flex items-center gap-2 text-xs text-ink">
                <input type="checkbox" checked={r.ferramentas.includes(f) || ferramentasFinais.includes(f)}
                       disabled={f === 'resolver_projeto' && ferramentasFinais.includes(f) && !r.ferramentas.includes(f)}
                       onChange={() => alternarLista('ferramentas', f)} />
                {FERRAMENTAS[f] ?? f}
                {dados.ferramentas_servidor.includes(f) && <span className="text-dim">(servidor)</span>}
              </label>
            ))}
          </div>
          {(dados.ferramentas_banco ?? []).length > 0 && (
            <label className="flex items-center gap-2 text-xs text-ink" data-agentes-consulta-banco>
              <input type="checkbox" checked={bancoLigado}
                     onChange={() => setR({
                       ...r,
                       ferramentas: bancoLigado
                         ? r.ferramentas.filter(f => !usaBanco([f]))
                         : [...r.ferramentas, ...FERRAMENTAS_BANCO],
                     })} />
              Consulta a banco <span className="text-dim">(só SELECT, nos bancos liberados abaixo)</span>
            </label>
          )}
          <p className="text-[11px] text-dim">
            Ferramenta nova só por desenvolvimento. “projeto” entra sozinho quando outra ferramenta precisa dele.
          </p>
        </fieldset>

        {bancoLigado && (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-xs font-semibold text-ink mb-1">Bancos liberados</legend>
            <BancosLiberados pares={r.bancos} onPares={bancos => setR(atual => ({ ...atual, bancos }))} />
            <p className="text-[11px] text-dim">
              O agente só executa SELECT, com no máximo 100 linhas e 30 s por consulta, mesmo que o login da conexão
              possa gravar. Ao salvar, o Orquestra confere cada banco novo no servidor.
            </p>
            <label className="flex items-center gap-2 text-xs text-ink" data-agentes-mascarar>
              <input type="checkbox" checked={r.mascarar_dados}
                     onChange={() => setR({ ...r, mascarar_dados: !r.mascarar_dados })} />
              Mascarar dados pessoais
              <span className="text-dim">(CPF, CNPJ, e-mail e telefone não chegam à IA)</span>
            </label>
          </fieldset>
        )}

        <fieldset className="flex flex-col gap-2">
          <legend className="text-xs font-semibold text-ink mb-1">Acesso</legend>
          {(['manual', 'perfil'] as AcessoAgente[]).map(a => (
            <label key={a} className="flex items-center gap-2 text-xs text-ink">
              <input type="radio" name="acesso-agente" checked={r.acesso === a}
                     disabled={a === 'perfil' && tocaServidor}
                     onChange={() => setR({ ...r, acesso: a })} />
              {ROTULO_ACESSO[a]}
              {a === 'perfil' && tocaServidor && (
                <span className="text-dim">— indisponível com ferramenta de servidor</span>
              )}
            </label>
          ))}
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 pt-1" role="group" aria-label="Perfis">
            {perfisErro ? (
              <p className="text-xs text-dim">{`Não foi possível carregar os perfis: ${perfisErro}`}</p>
            ) : (
              <>
                {escolhiveis.map(p => (
                  <label key={p.perfil_nome} className="flex items-center gap-2 text-xs text-ink">
                    <input type="checkbox" checked={r.perfis.includes(p.perfil_nome)}
                           onChange={() => alternarLista('perfis', p.perfil_nome)} />
                    {p.perfil_nome}
                  </label>
                ))}
                {inexistentes.map(p => (
                  <label key={p} className="flex items-center gap-2 text-xs text-ink" data-agentes-perfil-inexistente>
                    <input type="checkbox" checked onChange={() => alternarLista('perfis', p)} />
                    {p} <span className="text-dim">(não existe mais)</span>
                  </label>
                ))}
              </>
            )}
          </div>
          <p className="text-[11px] text-dim">
            {r.acesso === 'manual'
              ? 'Só estes perfis podem receber o agente; a concessão é feita usuário a usuário, em “Quem pode usar”.'
              : 'Todo usuário destes perfis usa o agente, sem concessão individual — desde que tenha a tela Agentes.'}
            {' O perfil consulta nunca recebe agente.'}
          </p>
          {semTela.length > 0 && (
            <InfoBanner icon="⚠">
              {`O perfil ${semTela.join(', ')} não tem a tela Agentes: o menu não vai aparecer para ele. `
                + 'Libere a tela em Perfis e Permissões — aqui ela não é concedida.'}
            </InfoBanner>
          )}
        </fieldset>

        {criacao && (
          <>
            <Textarea label="Prompt inicial (instruções do domínio)" rows={10} value={r.prompt}
                      className="font-mono text-xs" spellCheck={false}
                      onChange={e => setR({ ...r, prompt: e.target.value })}
                      ajuda="Vira a versão 1. As regras e o protocolo o Orquestra acrescenta sozinho." />
            <Input label="Motivo" value={r.motivo} maxLength={200} onChange={e => setR({ ...r, motivo: e.target.value })}
                   ajuda="Fica no histórico de versões do prompt." />
          </>
        )}

        {todosProblemas.length > 0 && (
          <ul className="text-xs text-dim list-disc pl-5" data-agentes-form-problemas>
            {todosProblemas.map(p => <li key={p}>{p}</li>)}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancelar} disabled={salvando}>Cancelar</Button>
          <Button disabled={todosProblemas.length > 0 || salvando} loading={salvando} onClick={() => onSalvar(final)}>
            {criacao ? 'Criar (desligado)' : 'Salvar'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
