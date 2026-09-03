// Utilitários — ferramentas sobre arquivos do servidor do DataStage por SFTP
// (spec docs/spec-utilitarios-arquivos.md). F3: a aba Ver arquivo. A aba
// Criar/editar chega na F5 — até lá ela não existe (mais honesto que "em breve").
//
// A página é o container: carrega `GET /utilitarios/config` (servidores, raízes
// ativas, teto), chama `POST /utilitarios/arquivo/ler` e passa estado para os
// componentes de apresentação (FormVerArquivo, ModalConteudoArquivo).
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Wrench, AlertTriangle } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Tabs } from '../components/ui/Tabs'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'
import { FormVerArquivo } from '../components/utilitarios/FormVerArquivo'
import { ModalConteudoArquivo, type EstadoLeitura } from '../components/utilitarios/ModalConteudoArquivo'
import { mensagemErro, migrationPendente, type ConfigUtil } from '../lib/utilitariosAdmin'
import { erroLeitura, type ConteudoArquivo, type ErroLeitura, type PedidoLeitura } from '../lib/utilitariosArquivo'

const TABS = [{ id: 'ver', label: 'Ver arquivo' }]

export default function Utilitarios() {
  const isAdmin = useAuthStore(s => s.isAdmin)
  const [aba, setAba] = useState('ver')
  const [pedido, setPedido] = useState<PedidoLeitura | null>(null)
  const [resultado, setResultado] = useState<ConteudoArquivo | null>(null)
  const [erro, setErro] = useState<ErroLeitura | null>(null)

  const config = useQuery<ConfigUtil>({ queryKey: ['utilitarios-config'], queryFn: () => apiFetch('/utilitarios/config') })

  const leitura = useMutation({
    mutationFn: (p: PedidoLeitura) =>
      apiFetch<ConteudoArquivo>('/utilitarios/arquivo/ler', { method: 'POST', body: JSON.stringify(p) }),
    onSuccess: r => { setResultado(r); setErro(null) },
    onError: e => { setResultado(null); setErro(erroLeitura(e)) },
  })

  const iniciar = (p: PedidoLeitura) => {
    setPedido(p); setResultado(null); setErro(null)
    leitura.mutate(p)
  }
  const retentar = (ultimas: number) => {
    if (!pedido) return
    iniciar({ ...pedido, ultimas_linhas: ultimas })
  }
  const fechar = () => { setPedido(null); setResultado(null); setErro(null); leitura.reset() }

  const estado: EstadoLeitura = leitura.isPending ? 'buscando' : erro ? 'erro' : 'pronto'

  if (config.isLoading) return <PageSpinner />
  if (config.error && migrationPendente(config.error)) {
    return (
      <div className="flex flex-col gap-4">
        <Cabecalho />
        <p className="p-4 rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 text-sm text-amber-800 dark:text-amber-200"
          data-estado="migration-pendente">
          <strong>Utilitários indisponíveis:</strong> a migration 105 ainda não foi aplicada neste banco.
        </p>
      </div>
    )
  }
  if (config.error || !config.data) {
    return (
      <div className="flex flex-col gap-4">
        <Cabecalho />
        <p className="text-sm text-red-600 dark:text-red-400" data-estado="erro">
          Falha ao carregar os Utilitários: {mensagemErro(config.error, 'erro desconhecido')}
        </p>
      </div>
    )
  }

  const cfg = config.data
  const raizesPorServidor: Record<string, string[]> = {}
  for (const r of cfg.raizes) (raizesPorServidor[r.servidor] ??= []).push(r.caminho)
  const semRaiz = cfg.raizes.length === 0
  const semServidor = cfg.servidores.every(s => !s.configurado)

  return (
    <div className="flex flex-col gap-4">
      <Cabecalho />

      <InfoBanner storageKey="utilitarios_ver_v1">
        Informe a <strong>pasta</strong> e o <strong>nome do arquivo</strong> no servidor e clique em
        <strong> Iniciar</strong>: o conteúdo abre num modal, com botão para copiar. Só pastas abaixo dos
        diretórios liberados pelo admin podem ser abertas; toda leitura fica registrada.
      </InfoBanner>

      {semRaiz && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800"
          data-aviso="sem-raiz">
          <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-800 dark:text-amber-200">
            Nenhum diretório liberado ainda. {isAdmin()
              ? <>Cadastre uma raiz em <strong>Admin › Sistema › Utilitários</strong>.</>
              : <>Peça ao administrador para cadastrar uma raiz em Admin › Utilitários.</>}
          </p>
        </div>
      )}

      {semServidor && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800"
          data-aviso="sem-servidor">
          <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-800 dark:text-amber-200">
            O servidor não está configurado nesta instância da API (DS_SSH_HOST/DS_SSH_USER). A leitura vai
            responder "servidor não configurado" até isso ser definido no ambiente.
          </p>
        </div>
      )}

      <Tabs tabs={TABS} active={aba} onChange={setAba} size="md" />

      {aba === 'ver' && (
        <FormVerArquivo
          servidores={cfg.servidores}
          raizesPorServidor={raizesPorServidor}
          iniciando={leitura.isPending}
          onIniciar={iniciar}
        />
      )}

      <ModalConteudoArquivo
        aberto={pedido !== null}
        pedido={pedido}
        estado={estado}
        resultado={resultado}
        erro={erro}
        onFechar={fechar}
        onRetentar={retentar}
      />
    </div>
  )
}

function Cabecalho() {
  return (
    <div className="flex items-start gap-3">
      <Wrench size={20} className="text-[#1A5FA8] dark:text-blue-400 mt-0.5 shrink-0" />
      <div>
        <h1 className="text-lg font-bold text-ink">Utilitários</h1>
        <p className="text-xs text-dim mt-0.5">
          Arquivos do servidor do DataStage, por SFTP, dentro dos diretórios liberados pelo admin.
        </p>
      </div>
    </div>
  )
}
