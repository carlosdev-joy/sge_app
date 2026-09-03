// Utilitários — ferramentas sobre arquivos do servidor do DataStage por SFTP
// (spec docs/spec-utilitarios-arquivos.md). Duas abas: Ver arquivo e
// Criar/editar arquivo. A página é o container: carrega `GET /utilitarios/config`
// (servidores, raízes ativas, extensões, teto, pode_gravar), chama
// `POST /utilitarios/arquivo/ler` e `POST /utilitarios/arquivo/gravar`, e passa
// estado para os componentes de apresentação.
import { useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Wrench, AlertTriangle } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Tabs } from '../components/ui/Tabs'
import { Modal } from '../components/ui/Modal'
import { Button } from '../components/ui/Button'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'
import { toast } from '../components/ui/Toast'
import { FormVerArquivo } from '../components/utilitarios/FormVerArquivo'
import { ModalConteudoArquivo, type EstadoLeitura } from '../components/utilitarios/ModalConteudoArquivo'
import { FormEditarArquivo, type CarregadoExistente } from '../components/utilitarios/FormEditarArquivo'
import { ModalGravacaoArquivo, type EstadoGravacao } from '../components/utilitarios/ModalGravacaoArquivo'
import { mensagemErro, migrationPendente, type ConfigUtil } from '../lib/utilitariosAdmin'
import { erroLeitura, type ConteudoArquivo, type ErroLeitura, type PedidoLeitura } from '../lib/utilitariosArquivo'
import {
  erroGravacao, pastaENomeDoCaminho,
  type ErroGravacao, type PedidoGravacao, type ResultadoGravacao,
} from '../lib/utilitariosGravacao'

const TABS = [
  { id: 'ver', label: 'Ver arquivo' },
  { id: 'editar', label: 'Criar/editar arquivo' },
]
const ABA_CHAVE = 'orq.utilitarios.aba'

export default function Utilitarios() {
  const isAdmin = useAuthStore(s => s.isAdmin)
  // Aba lembrada por navegador (`localStorage` LANÇA em janela privada: try/catch dos dois lados).
  const [aba, setAbaEstado] = useState(() => {
    try { return localStorage.getItem(ABA_CHAVE) === 'editar' ? 'editar' : 'ver' } catch { return 'ver' }
  })
  const setAba = (id: string) => {
    setAbaEstado(id)
    try { localStorage.setItem(ABA_CHAVE, id) } catch { /* sem memória, sem drama */ }
  }
  const [abaPendente, setAbaPendente] = useState<string | null>(null)
  const [sujo, setSujo] = useState(false)

  // ── leitura ────────────────────────────────────────────────────────────────
  const [pedido, setPedido] = useState<PedidoLeitura | null>(null)
  const [resultado, setResultado] = useState<ConteudoArquivo | null>(null)
  const [erro, setErro] = useState<ErroLeitura | null>(null)
  // Número de série do pedido em curso. A resposta de um pedido que o usuário
  // já fechou (ou substituiu por "últimas N linhas") chega depois e NÃO pode
  // sobrescrever o modal do pedido atual: `reset()` do TanStack só desliga o
  // observer, os callbacks do nível do hook continuariam rodando.
  const serie = useRef(0)

  const config = useQuery<ConfigUtil>({ queryKey: ['utilitarios-config'], queryFn: () => apiFetch('/utilitarios/config') })

  const leitura = useMutation({
    mutationFn: (p: PedidoLeitura) =>
      apiFetch<ConteudoArquivo>('/utilitarios/arquivo/ler', { method: 'POST', body: JSON.stringify(p) }),
  })

  const iniciar = (p: PedidoLeitura) => {
    const minha = ++serie.current
    setPedido(p); setResultado(null); setErro(null)
    leitura.mutate(p, {
      onSuccess: r => { if (serie.current === minha) { setResultado(r); setErro(null) } },
      onError: e => { if (serie.current === minha) { setResultado(null); setErro(erroLeitura(e)) } },
    })
  }
  const retentar = (ultimas: number) => {
    if (!pedido) return
    iniciar({ ...pedido, ultimas_linhas: ultimas })
  }
  const fechar = () => {
    serie.current++
    setPedido(null); setResultado(null); setErro(null); leitura.reset()
  }
  const estado: EstadoLeitura = leitura.isPending ? 'buscando' : erro ? 'erro' : resultado ? 'pronto' : 'buscando'

  // ── gravação ───────────────────────────────────────────────────────────────
  const [pedidoG, setPedidoG] = useState<PedidoGravacao | null>(null)
  const [resultadoG, setResultadoG] = useState<ResultadoGravacao | null>(null)
  const [erroG, setErroG] = useState<ErroGravacao | null>(null)
  const [carregando, setCarregando] = useState(false)
  const serieG = useRef(0)

  const gravacao = useMutation({
    mutationFn: (p: PedidoGravacao) =>
      apiFetch<ResultadoGravacao>('/utilitarios/arquivo/gravar', { method: 'POST', body: JSON.stringify(p) }),
  })

  const gravar = (p: PedidoGravacao) => {
    const minha = ++serieG.current
    setPedidoG(p); setResultadoG(null); setErroG(null)
    gravacao.mutate(p, {
      onSuccess: r => { if (serieG.current === minha) { setResultadoG(r); setErroG(null); setSujo(false) } },
      onError: e => { if (serieG.current === minha) { setResultadoG(null); setErroG(erroGravacao(e)) } },
    })
  }
  // Saída do 409: o MESMO pedido, agora com sobrescrever.
  const sobrescrever = () => { if (pedidoG) gravar({ ...pedidoG, sobrescrever: true }) }
  const fecharGravacao = () => {
    serieG.current++
    setPedidoG(null); setResultadoG(null); setErroG(null); gravacao.reset()
  }
  const estadoG: EstadoGravacao = gravacao.isPending ? 'gravando'
    : erroG?.status === 409 ? 'existe' : erroG ? 'erro' : resultadoG ? 'pronto' : 'gravando'

  // "Carregar existente": lê pelo mesmo endpoint da aba Ver arquivo.
  const carregar = async (p: { servidor: string; diretorio: string; nome: string }): Promise<CarregadoExistente | null> => {
    setCarregando(true)
    try {
      const r = await apiFetch<ConteudoArquivo>('/utilitarios/arquivo/ler', { method: 'POST', body: JSON.stringify(p) })
      if (r.truncado) toast.info('O arquivo veio truncado (acima do teto): o editor tem só o fim dele.')
      return { conteudo: r.conteudo, codificacao: r.codificacao }
    } catch (e) {
      toast.error(erroLeitura(e).mensagem)
      return null
    } finally {
      setCarregando(false)
    }
  }
  // "Ver arquivo" do resultado da gravação: abre o modal de conteúdo no que foi gravado.
  const verGravado = (caminho: string) => {
    const { diretorio, nome } = pastaENomeDoCaminho(caminho)
    const servidor = pedidoG?.servidor ?? 'datastage'
    fecharGravacao()
    iniciar({ servidor, diretorio, nome })
  }

  // Troca de aba com texto não gravado no editor: pergunta antes de descartar.
  const mudarAba = (id: string) => {
    if (id === aba) return
    if (aba === 'editar' && sujo) { setAbaPendente(id); return }
    setAba(id)
  }
  const confirmarTroca = () => { if (abaPendente) { setSujo(false); setAba(abaPendente) } ; setAbaPendente(null) }

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

      <InfoBanner storageKey="utilitarios_ver_v2">
        <strong>Ver arquivo</strong>: informe a pasta e o nome e clique em Iniciar — o conteúdo abre num modal, com
        botão para copiar. <strong>Criar/editar arquivo</strong>: escreva no editor, escolha a extensão e a pasta e
        grave; para alterar um arquivo que já existe, use "Carregar existente". Só pastas abaixo dos diretórios
        liberados pelo admin; toda leitura e gravação fica registrada.
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
            O servidor não está configurado nesta instância da API (DS_SSH_HOST/DS_SSH_USER). A leitura e a gravação
            vão responder "servidor não configurado" até isso ser definido no ambiente.
          </p>
        </div>
      )}

      <Tabs tabs={TABS} active={aba} onChange={mudarAba} size="md" />

      {aba === 'ver' && (
        <FormVerArquivo
          servidores={cfg.servidores}
          raizesPorServidor={raizesPorServidor}
          iniciando={leitura.isPending}
          onIniciar={iniciar}
        />
      )}

      {aba === 'editar' && (
        <FormEditarArquivo
          servidores={cfg.servidores}
          raizesPorServidor={raizesPorServidor}
          extensoes={cfg.extensoes}
          podeGravar={cfg.pode_gravar}
          gravando={gravacao.isPending}
          carregando={carregando}
          onCarregar={carregar}
          onGravar={gravar}
          onSujo={setSujo}
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

      <ModalGravacaoArquivo
        aberto={pedidoG !== null}
        pedido={pedidoG}
        estado={estadoG}
        resultado={resultadoG}
        erro={erroG}
        onFechar={fecharGravacao}
        onSobrescrever={sobrescrever}
        onVerArquivo={verGravado}
      />

      <Modal open={abaPendente !== null} onClose={() => setAbaPendente(null)} title="Alterações não gravadas" size="sm">
        <div className="flex flex-col gap-5">
          <p className="text-sm text-ink">
            Há texto no editor que ainda não foi gravado. Trocar de aba descarta o que foi digitado.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setAbaPendente(null)} data-acao="ficar">Ficar no editor</Button>
            <Button variant="danger" size="sm" onClick={confirmarTroca} data-acao="descartar">Descartar e trocar</Button>
          </div>
        </div>
      </Modal>
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
