// Admin › E-mail › Modelos (F2 da spec docs/spec-email-modelos-e-navegacao.md).
//
// O catálogo é o LAYOUT institucional. O nó guarda só o id e o corpo é lido no
// envio, então editar um modelo aqui vale para todos os fluxos que o usam, sem
// republicar DAG nem reeditar nó — e é por isso que o editor mostra a prévia ao
// lado: o erro daqui chega em muita gente de uma vez.
//
// ⚠️ Excluir modelo EM USO é recusado pela API (409 nomeando os fluxos). É a
// lição do catálogo de cards do Teams, onde apagar o template faz o envio cair
// em silêncio para a mensagem embutida. Aqui se DESATIVA: some da lista de
// escolha e quem já usa continua enviando.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Star, Trash2 } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Input, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { Switch } from '../ui/Switch'
import { toast } from '../ui/Toast'
import { PreviaEmail } from '../etapas/PreviaEmail'
import {
  errosDoModelo, formDoModelo, mensagemErroEmail, migration112Pendente,
  type EmailModelo, type EmailModeloForm,
} from '../../lib/emailAdmin'

const Q_MODELOS = ['email-admin-modelos'] as const

export function EmailModelos() {
  const qc = useQueryClient()
  const [editando, setEditando] = useState<EmailModelo | null | undefined>(undefined)
  const [excluindo, setExcluindo] = useState<EmailModelo | null>(null)

  const lista = useQuery<{ modelos: EmailModelo[]; exigir_modelo: boolean }>({
    queryKey: Q_MODELOS, queryFn: () => apiFetch('/email/admin/modelos'), retry: false,
  })

  const excluir = useMutation({
    mutationFn: (id: number) => apiFetch(`/email/admin/modelos/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      toast.success('Modelo excluído')
      setExcluindo(null)
      await qc.invalidateQueries({ queryKey: Q_MODELOS })
    },
    onError: (e: unknown) => toast.error(mensagemErroEmail(e, 'Não foi possível excluir o modelo')),
  })

  if (lista.isError) {
    // Migração pendente e banco fora do ar são 503 os dois, e a API os separa
    // de propósito: mandar "aplique a migration 112" para quem está com o
    // banco caído é o único diagnóstico errado que esta tela sabe dar.
    const pendente112 = migration112Pendente(lista.error)
    return (
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
        {pendente112
          ? 'Catálogo de modelos indisponível — aplique a migration 112.'
          : `Catálogo de modelos indisponível: ${mensagemErroEmail(lista.error, 'falha ao consultar o catálogo')}.`}
        {' '}Os nós de e-mail continuam funcionando com corpo livre.
      </p>
    )
  }

  const modelos = lista.data?.modelos ?? []

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-edge bg-panel p-4 shadow-sm">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink">Modelos</h3>
          <p className="text-xs text-dim">
            O layout que os fluxos usam. Editar um modelo vale na próxima corrida de todos os nós
            que o escolheram, sem republicar nada.
          </p>
        </div>
        <Button variant="secondary" size="sm" className="ml-auto shrink-0"
                onClick={() => setEditando(null)}>
          <Plus size={13} /> Novo modelo
        </Button>
      </div>

      {modelos.length === 0 ? (
        <p className="text-xs text-dim">Nenhum modelo cadastrado.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-dim">
              <tr className="border-b border-edge">
                <th className="py-1.5 pr-3 font-medium">Nome</th>
                <th className="py-1.5 pr-3 font-medium">Formato</th>
                <th className="py-1.5 pr-3 font-medium">Tamanho</th>
                <th className="py-1.5 pr-3 font-medium">Situação</th>
                <th className="py-1.5 font-medium" />
              </tr>
            </thead>
            <tbody>
              {modelos.map(m => (
                <tr key={m.id} className="border-b border-edge/60 last:border-0">
                  <td className="py-2 pr-3">
                    <div className="flex items-center gap-1.5">
                      {m.padrao && <Star size={12} className="text-amber-500" aria-label="padrão" />}
                      <span className="font-medium text-ink">{m.nome}</span>
                    </div>
                    {m.descricao && <p className="text-[11px] text-dim">{m.descricao}</p>}
                  </td>
                  <td className="py-2 pr-3 text-dim">{m.html ? 'HTML' : 'texto'}</td>
                  <td className="py-2 pr-3 tabular-nums text-dim">
                    {(m.corpo_tamanho ?? 0).toLocaleString('pt-BR')} car.
                  </td>
                  <td className="py-2 pr-3">
                    <span className={m.ativo
                      ? 'text-emerald-700 dark:text-emerald-300'
                      : 'text-dim'}>
                      {m.ativo ? 'ativo' : 'inativo'}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    <button type="button" className="mr-2 text-dim hover:text-ink"
                            onClick={() => setEditando(m)} title="Editar">
                      <Pencil size={13} />
                    </button>
                    <button type="button" className="text-dim hover:text-red-600"
                            onClick={() => setExcluindo(m)} title="Excluir">
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editando !== undefined && (
        <ModeloModal
          modelo={editando}
          onFechar={() => setEditando(undefined)}
          onSalvo={async () => {
            const id = editando?.id
            setEditando(undefined)
            await qc.invalidateQueries({ queryKey: Q_MODELOS })
            await qc.invalidateQueries({ queryKey: ['email-modelos'] })
            // o detalhe também: sem isso o editor reabre com o corpo anterior
            if (id != null) await qc.invalidateQueries({ queryKey: ['email-admin-modelo', id] })
          }}
        />
      )}

      {excluindo && (
        <Modal open title="Excluir modelo" size="sm" onClose={() => setExcluindo(null)}>
          <div className="flex flex-col gap-3">
            <p className="text-sm text-ink">
              Excluir <strong>{excluindo.nome}</strong>? Se algum fluxo estiver usando, a exclusão
              é recusada — nesse caso, desative o modelo: ele some da lista de escolha e quem já
              usa continua enviando.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setExcluindo(null)}>Cancelar</Button>
              <Button variant="danger" onClick={() => excluir.mutate(excluindo.id)}
                      disabled={excluir.isPending}>
                {excluir.isPending ? 'Excluindo…' : 'Excluir'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </section>
  )
}

function ModeloModal({ modelo, onFechar, onSalvo }: {
  modelo: EmailModelo | null
  onFechar: () => void
  onSalvo: () => void
}) {
  const ehEdicao = modelo != null
  const [form, setForm] = useState<EmailModeloForm>(() => formDoModelo(modelo))
  const erros = errosDoModelo(form)

  // Na edição, o corpo não vem na lista (só o tamanho) — busca o modelo inteiro.
  const detalhe = useQuery<{ modelo: EmailModelo; pipelines: string[] }>({
    queryKey: ['email-admin-modelo', modelo?.id],
    queryFn: () => apiFetch(`/email/admin/modelos/${modelo!.id}`),
    enabled: ehEdicao,
    // ⚠️ Sempre do servidor. Com cache, reabrir o modelo logo depois de salvar
    // traria o corpo ANTIGO para o editor — e o próximo Salvar reverteria a
    // edição em TODOS os fluxos que usam o modelo (o vínculo é vivo).
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: 'always',
  })
  // Ajuste de estado DURANTE a renderização (padrão do React para "derivar de
  // uma prop que mudou"), e não num efeito: no efeito o formulário pisca com o
  // valor velho antes de trocar. A trava é o id JÁ CARREGADO, não um booleano
  // — assim o formulário é preenchido de novo se o modelo aberto mudar.
  const [carregadoDe, setCarregadoDe] = useState<number | null>(null)
  if (ehEdicao && detalhe.data && carregadoDe !== detalhe.data.modelo.id) {
    setCarregadoDe(detalhe.data.modelo.id)
    setForm(formDoModelo(detalhe.data.modelo))
  }
  const emUso = detalhe.data?.pipelines ?? []
  // Edição com o corpo ainda a caminho (ou com a busca falhada): o formulário
  // não representa o modelo, e salvar assim apagaria o corpo de todo mundo.
  const carregandoCorpo = ehEdicao && carregadoDe !== modelo!.id

  const salvar = useMutation({
    mutationFn: () => apiFetch(
      ehEdicao ? `/email/admin/modelos/${modelo!.id}` : '/email/admin/modelos',
      {
        method: ehEdicao ? 'PUT' : 'POST',
        body: JSON.stringify({
          nome: form.nome.trim(),
          descricao: form.descricao.trim() || null,
          assunto: form.assunto.trim() || null,
          corpo: form.corpo,
          html: form.html,
          ativo: form.ativo,
          padrao: form.padrao,
        }),
      }),
    onSuccess: () => { toast.success(ehEdicao ? 'Modelo salvo' : 'Modelo criado'); onSalvo() },
    onError: (e: unknown) => toast.error(mensagemErroEmail(e, 'Não foi possível salvar o modelo')),
  })

  const f = <K extends keyof EmailModeloForm>(k: K, v: EmailModeloForm[K]) =>
    setForm(atual => ({ ...atual, [k]: v }))

  return (
    <Modal open title={ehEdicao ? 'Editar modelo' : 'Novo modelo'} size="xl" onClose={onFechar}>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-2">
          <Input label="Nome *" value={form.nome} onChange={e => f('nome', e.target.value)}
                 placeholder="Aviso de fim de carga" className="text-xs" />
          <Input label="Quando usar" value={form.descricao}
                 onChange={e => f('descricao', e.target.value)}
                 hint="Aparece abaixo da lista, no painel do nó."
                 placeholder="Use para avisar o fim de uma carga." className="text-xs" />
          <Input label="Assunto sugerido" value={form.assunto}
                 onChange={e => f('assunto', e.target.value)}
                 hint="Sugestão para quem monta o fluxo. O assunto de cada nó continua sendo dele."
                 placeholder="[Orquestra] {pipeline} — {status}" className="text-xs" />
          <Textarea label="Corpo *" value={form.corpo} rows={14}
                    onChange={e => f('corpo', e.target.value)}
                    hint="Aceita os mesmos marcadores do nó, trocados no envio."
                    className="font-mono text-[11px]" />
          <div className="flex flex-wrap items-center gap-4">
            <Switch checked={form.html} onChange={e => f('html', e.target.checked)}
                    label="Corpo em HTML" />
            <Switch checked={form.ativo} onChange={e => f('ativo', e.target.checked)}
                    label="Ativo" />
            <Switch checked={form.padrao} onChange={e => f('padrao', e.target.checked)}
                    label="Padrão" />
          </div>
          <p className="text-[10px] text-dim/70">
            O modelo padrão já vem escolhido no nó novo. Só um pode ser padrão por vez.
          </p>
          {emUso.length > 0 && (
            <p className="rounded-lg border border-edge bg-canvas px-3 py-2 text-[10px] text-dim">
              Em uso em {emUso.length} fluxo{emUso.length > 1 ? 's' : ''}:{' '}
              {emUso.slice(0, 6).join(', ')}{emUso.length > 6 ? ' …' : ''}. O que você salvar aqui
              vale na próxima corrida de todos eles.
            </p>
          )}
          {detalhe.isError && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              Não foi possível carregar o corpo deste modelo. Feche e abra de novo — salvar
              agora gravaria um modelo pela metade para todos os fluxos que o usam.
            </p>
          )}
          {erros.length > 0 && !carregandoCorpo && (
            <ul className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              {erros.map(e => <li key={e}>{e}</li>)}
            </ul>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-2">
          <PreviaEmail corpo={form.corpo} html={form.html} altura={420} />
        </div>
      </div>

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onFechar}>Cancelar</Button>
        {/* Enquanto o corpo não chegou do servidor, o formulário está pela
            metade (a lista não traz o corpo, só o tamanho): salvar aí gravaria
            um modelo vazio para todos os fluxos que o usam. */}
        <Button onClick={() => salvar.mutate()}
                disabled={salvar.isPending || erros.length > 0 || carregandoCorpo}>
          {salvar.isPending ? 'Salvando…'
            : carregandoCorpo ? (detalhe.isError ? 'Indisponível' : 'Carregando…')
            : 'Salvar'}
        </Button>
      </div>
    </Modal>
  )
}
