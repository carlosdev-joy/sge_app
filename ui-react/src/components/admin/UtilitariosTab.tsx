// Admin › Utilitários — o container: react-query + mutations em cima dos
// endpoints /utilitarios/admin/* (F1), e os três blocos de apresentação.
//
// Spec docs/spec-utilitarios-arquivos.md (F2). Sem a migration 105 a API
// responde 503 nomeando-a — a aba diz isso em vez de "falha ao carregar".
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { PageSpinner } from '../ui/Spinner'
import { InfoBanner } from '../ui/InfoBanner'
import { toast } from '../ui/Toast'
import { UtilitariosRaizes } from './UtilitariosRaizes'
import { UtilitariosExtensoes } from './UtilitariosExtensoes'
import { UtilitariosLimites } from './UtilitariosLimites'
import {
  mensagemErro, migrationPendente,
  type ConfigUtil, type ExtensaoUtil, type RaizUtil, type TesteRaiz,
} from '../../lib/utilitariosAdmin'

const Q_CONFIG = ['utilitarios-config'] as const
const Q_RAIZES = ['utilitarios-admin-raizes'] as const
const Q_EXTENSOES = ['utilitarios-admin-extensoes'] as const

export function UtilitariosTab() {
  const qc = useQueryClient()
  const [testes, setTestes] = useState<Record<number, TesteRaiz | undefined>>({})
  const [testandoId, setTestandoId] = useState<number | null>(null)

  const config = useQuery<ConfigUtil>({ queryKey: Q_CONFIG, queryFn: () => apiFetch('/utilitarios/config') })
  const raizes = useQuery<RaizUtil[]>({ queryKey: Q_RAIZES, queryFn: () => apiFetch('/utilitarios/admin/raizes') })
  const extensoes = useQuery<ExtensaoUtil[]>({ queryKey: Q_EXTENSOES, queryFn: () => apiFetch('/utilitarios/admin/extensoes') })

  // Devolve a promise: o `mutateAsync` só resolve com a lista nova na tela —
  // sem isto a linha editada mostrava o caminho antigo por um instante depois
  // do toast "alterada".
  const invalidar = () => Promise.all([
    qc.invalidateQueries({ queryKey: Q_CONFIG }),
    qc.invalidateQueries({ queryKey: Q_RAIZES }),
    qc.invalidateQueries({ queryKey: Q_EXTENSOES }),
  ])

  // `onSettled` (não só `onSuccess`): um 404/409 quer dizer que a lista da tela
  // está defasada (outro admin mexeu) — ressincroniza também no erro.
  const incluirRaiz = useMutation({
    mutationFn: (v: { servidor: string; caminho: string }) =>
      apiFetch<{ id: number; caminho: string }>('/utilitarios/admin/raizes', { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: d => toast.success(`Raiz ${d.caminho} cadastrada`),
    onError: e => toast.error(mensagemErro(e, 'Falha ao cadastrar a raiz')),
    onSettled: invalidar,
  })

  const ativarRaiz = useMutation({
    mutationFn: (v: { id: number; ativo: boolean }) =>
      apiFetch(`/utilitarios/admin/raizes/${v.id}`, { method: 'PATCH', body: JSON.stringify({ ativo: v.ativo }) }),
    onSuccess: (_d, v) => toast.success(v.ativo ? 'Raiz reativada' : 'Raiz desativada'),
    onError: e => toast.error(mensagemErro(e, 'Falha ao alterar a raiz')),
    onSettled: invalidar,
  })

  const editarRaiz = useMutation({
    mutationFn: (v: { id: number; caminho: string }) =>
      apiFetch<{ caminho: string }>(`/utilitarios/admin/raizes/${v.id}`, { method: 'PATCH', body: JSON.stringify({ caminho: v.caminho }) }),
    onSuccess: (d, v) => {
      toast.success(`Raiz alterada para ${d.caminho}`)
      // O resultado do Testar era do caminho antigo.
      setTestes(t => ({ ...t, [v.id]: undefined }))
    },
    onError: e => toast.error(mensagemErro(e, 'Falha ao alterar o caminho da raiz')),
    onSettled: invalidar,
  })

  const testarRaiz = async (id: number) => {
    // O caminho no momento do pedido: se a raiz for editada enquanto o teste
    // corre, a resposta é do caminho ANTIGO e não pode aparecer sob o novo.
    const caminhoTestado = raizes.data?.find(r => r.id === id)?.caminho
    setTestandoId(id)
    try {
      const r = await apiFetch<TesteRaiz>(`/utilitarios/admin/raizes/${id}/testar`, { method: 'POST' })
      const agora = qc.getQueryData<RaizUtil[]>(Q_RAIZES)?.find(x => x.id === id)?.caminho
      if (agora !== undefined && agora !== caminhoTestado) return
      setTestes(t => ({ ...t, [id]: r }))
    } catch (e) {
      toast.error(mensagemErro(e, 'Falha ao testar a raiz no servidor'))
    } finally {
      setTestandoId(null)
    }
  }

  const incluirExtensao = useMutation({
    mutationFn: (extensao: string) =>
      apiFetch<{ extensao: string }>('/utilitarios/admin/extensoes', { method: 'POST', body: JSON.stringify({ extensao }) }),
    onSuccess: d => toast.success(`Extensão .${d.extensao} incluída`),
    onError: e => toast.error(mensagemErro(e, 'Falha ao incluir a extensão')),
    onSettled: invalidar,
  })

  const excluirExtensao = useMutation({
    mutationFn: (extensao: string) =>
      apiFetch(`/utilitarios/admin/extensoes/${encodeURIComponent(extensao)}`, { method: 'DELETE' }),
    onSuccess: (_d, ext) => toast.success(`Extensão .${ext} excluída`),
    onError: e => toast.error(mensagemErro(e, 'Falha ao excluir a extensão')),
    onSettled: invalidar,
  })

  const salvarLimites = useMutation({
    mutationFn: (v: { tamanho_max_kb: number; backup_ao_sobrescrever: boolean }) =>
      apiFetch('/utilitarios/admin/config', { method: 'PUT', body: JSON.stringify(v) }),
    onSuccess: () => toast.success('Limites salvos'),
    onError: e => toast.error(mensagemErro(e, 'Falha ao salvar os limites')),
    onSettled: invalidar,
  })

  const erro = config.error ?? raizes.error ?? extensoes.error
  const semDados = !config.data || !raizes.data || !extensoes.data
  if (erro && migrationPendente(erro)) {
    return (
      <div className="p-4 rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 text-sm text-amber-800 dark:text-amber-200"
        data-estado="migration-pendente">
        <strong>Utilitários indisponíveis:</strong> a migration 105 ainda não foi aplicada neste banco
        (tabelas <span className="font-mono">etl_utilitario_*</span>). Rode o deploy com a etapa 6c e volte aqui.
      </div>
    )
  }
  if (semDados && (config.isLoading || raizes.isLoading || extensoes.isLoading)) return <PageSpinner />
  if (!config.data || !raizes.data || !extensoes.data) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" data-estado="erro">
        Falha ao carregar os Utilitários: {mensagemErro(erro, 'erro desconhecido')}
      </p>
    )
  }

  const cfg = config.data
  const semServidor = cfg.servidores.every(s => !s.configurado)

  return (
    <div className="flex flex-col gap-4" data-aba="utilitarios">
      <InfoBanner storageKey="admin_utilitarios_v1">
        A tela Utilitários lê e grava arquivos do servidor do DataStage por SFTP.
        Só o que está <strong>abaixo de uma raiz ativa</strong> pode ser aberto; as extensões
        dizem o que pode ser <strong>gravado</strong>. Toda leitura e gravação fica na auditoria.
      </InfoBanner>

      {/* Refetch que falhou com dados na tela: avisa, mas NÃO desmonta os
          formulários — o admin pode estar no meio de um caminho digitado. */}
      {erro && (
        <p className="text-xs text-amber-700 dark:text-amber-300" data-aviso="refetch">
          Não consegui atualizar os dados agora ({mensagemErro(erro, 'erro de rede')}); o que está
          na tela pode estar defasado.
        </p>
      )}

      {semServidor && (
        <p className="text-xs text-amber-700 dark:text-amber-300" data-aviso="sem-servidor">
          Nenhum servidor está configurado nesta instância da API (DS_SSH_HOST/DS_SSH_USER). O cadastro funciona,
          mas Testar e a própria tela Utilitários vão responder "servidor não configurado".
        </p>
      )}

      <UtilitariosRaizes
        servidores={cfg.servidores}
        raizes={raizes.data}
        testes={testes}
        testandoId={testandoId}
        incluindo={incluirRaiz.isPending}
        onIncluir={(servidor, caminho) => incluirRaiz.mutateAsync({ servidor, caminho }).then(() => true, () => false)}
        onTestar={testarRaiz}
        onAtivar={(id, ativo) => ativarRaiz.mutate({ id, ativo })}
        onEditar={(id, caminho) => editarRaiz.mutateAsync({ id, caminho }).then(() => true, () => false)}
      />

      <UtilitariosExtensoes
        extensoes={extensoes.data.map(e => e.extensao)}
        incluindo={incluirExtensao.isPending}
        onIncluir={ext => incluirExtensao.mutateAsync(ext).then(() => true, () => false)}
        onExcluir={ext => excluirExtensao.mutate(ext)}
      />

      <UtilitariosLimites
        key={`${cfg.tamanho_max_kb}-${cfg.backup_ao_sobrescrever ? 1 : 0}`}
        tamanhoMaxKb={cfg.tamanho_max_kb}
        backup={cfg.backup_ao_sobrescrever}
        salvando={salvarLimites.isPending}
        onSalvar={(tamanho_max_kb, backup_ao_sobrescrever) => salvarLimites.mutate({ tamanho_max_kb, backup_ao_sobrescrever })}
      />
    </div>
  )
}
