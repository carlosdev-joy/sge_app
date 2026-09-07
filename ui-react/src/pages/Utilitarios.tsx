// Utilitários — ferramentas sobre arquivos do servidor do DataStage por SFTP
// (spec docs/spec-utilitarios-arquivos.md). Duas abas: Ver arquivo e
// Criar/editar arquivo. A página é o container: carrega `GET /utilitarios/config`
// (servidores, raízes ativas, extensões, teto, pode_gravar), chama
// `POST /utilitarios/arquivo/ler` e `POST /utilitarios/arquivo/gravar`, e passa
// estado para os componentes de apresentação.
//
// Download (spec docs/spec-utilitarios-transferencia.md, F2): a página também
// é dona do download em curso — UM por vez, com número de série contra a
// resposta de um download já dispensado — e passa `onBaixar` ao modal de
// conteúdo e aos navegadores de pastas; a faixa de transferência mostra o
// progresso, o resultado ou o erro.
//
// Upload (F4): terceira aba, Enviar arquivo. A página segura o `File` escolhido
// entre o 409 e o Sobrescrever (o MESMO arquivo sobe de novo com
// `sobrescrever: true`), o gesto de cancelar do XHR em curso e o progresso;
// o modal de envio mostra enviando → existe/pronto/cancelado/erro.
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
import { BarraTransferencia } from '../components/utilitarios/BarraTransferencia'
import { FormEnviarArquivo } from '../components/utilitarios/FormEnviarArquivo'
import { ModalEnvioArquivo } from '../components/utilitarios/ModalEnvioArquivo'
import { mensagemErro, migrationPendente, type ConfigUtil } from '../lib/utilitariosAdmin'
import { erroLeitura, type ConteudoArquivo, type ErroLeitura, type PedidoLeitura } from '../lib/utilitariosArquivo'
import {
  erroGravacao, nomeArquivoCompleto,
  type ErroGravacao, type PedidoGravacao, type ResultadoGravacao,
} from '../lib/utilitariosGravacao'
import {
  TETO_TRANSFERENCIA_KB_PADRAO, emCurso, envioChegouInteiro, erroEnvio, erroTransferencia,
  type ErroEnvio, type EstadoEnvio, type EstadoTransferencia, type PedidoDownload, type PedidoEnvio, type ResultadoEnvio,
} from '../lib/utilitariosTransferencia'
import { baixarArquivo } from '../lib/utilitariosDownload'
import { enviarArquivo, type EnvioEmCurso, type ErroEnvioTransporte } from '../lib/utilitariosEnvio'
import type { Listagem } from '../lib/utilitariosNavegador'
import type { ListarPasta } from '../components/utilitarios/useNavegadorPastas'

// Navegador de pastas (F6): a listagem vem daqui; os formulários cuidam do resto.
const listarPasta: ListarPasta = (servidor, caminho, mostrarOcultos) => {
  const q = new URLSearchParams({ servidor })
  if (caminho) q.set('caminho', caminho)
  if (mostrarOcultos) q.set('mostrar_ocultos', 'true')
  return apiFetch<Listagem>(`/utilitarios/pasta/listar?${q.toString()}`)
}

const TABS = [
  { id: 'ver', label: 'Ver arquivo' },
  { id: 'editar', label: 'Criar/editar arquivo' },
  { id: 'enviar', label: 'Enviar arquivo' },
]
const ABA_CHAVE = 'orq.utilitarios.aba'
const ABAS_LEMBRADAS = new Set(['editar', 'enviar'])

export default function Utilitarios() {
  const isAdmin = useAuthStore(s => s.isAdmin)
  // Aba lembrada por navegador (`localStorage` LANÇA em janela privada: try/catch dos dois lados).
  const [aba, setAbaEstado] = useState(() => {
    try {
      const lembrada = localStorage.getItem(ABA_CHAVE) ?? ''
      return ABAS_LEMBRADAS.has(lembrada) ? lembrada : 'ver'
    } catch { return 'ver' }
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

  // Sem refetch ao focar a janela: um refetch que falha (API reiniciando) NÃO
  // pode desmontar o editor com texto por gravar — e abaixo o erro só derruba
  // a página quando não há dado nenhum.
  const config = useQuery<ConfigUtil>({
    queryKey: ['utilitarios-config'], queryFn: () => apiFetch('/utilitarios/config'), refetchOnWindowFocus: false,
  })

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
  // Fechar o modal NÃO reseta a mutation: `gravando` segue verdadeiro até o
  // pedido em voo responder, senão o Gravar religava e um segundo pedido podia
  // aterrissar antes do primeiro (que então gravaria por cima, sem backup).
  const fecharGravacao = () => {
    serieG.current++
    setPedidoG(null); setResultadoG(null); setErroG(null)
  }
  const estadoG: EstadoGravacao = gravacao.isPending ? 'gravando'
    : erroG?.status === 409 ? 'existe' : erroG ? 'erro' : resultadoG ? 'pronto' : 'gravando'

  // "Carregar existente": lê pelo mesmo endpoint da aba Ver arquivo.
  const carregar = async (p: { servidor: string; diretorio: string; nome: string }): Promise<CarregadoExistente | null> => {
    setCarregando(true)
    try {
      const r = await apiFetch<ConteudoArquivo>('/utilitarios/arquivo/ler', { method: 'POST', body: JSON.stringify(p) })
      return { conteudo: r.conteudo, codificacao: r.codificacao }
    } catch (e) {
      const erro = erroLeitura(e)
      // Acima do teto o `ler` sugere "últimas N linhas", que não existe aqui:
      // um arquivo desse tamanho não se edita pelo Orquestra.
      toast.error(erro.status === 413
        ? `O arquivo passa do teto de ${config.data?.tamanho_max_kb ?? '?'} KB e não dá para editá-lo por aqui.`
        : erro.mensagem)
      return null
    } finally {
      setCarregando(false)
    }
  }
  // "Ver arquivo" do resultado da gravação: abre o modal de conteúdo no que foi
  // gravado — pelo caminho que o usuário digitou (lexical), não pelo real que a
  // API devolve: com raiz que é symlink, o real cai fora das raízes e o `ler`
  // responderia 403.
  const verGravado = () => {
    if (!pedidoG) return
    const pedidoLeitura: PedidoLeitura = {
      servidor: pedidoG.servidor, diretorio: pedidoG.diretorio, nome: nomeArquivoCompleto(pedidoG.nome, pedidoG.extensao),
    }
    fecharGravacao()
    iniciar(pedidoLeitura)
  }

  // ── download ───────────────────────────────────────────────────────────────
  const [transferencia, setTransferencia] = useState<EstadoTransferencia | null>(null)
  const serieT = useRef(0)
  const baixando = emCurso(transferencia)

  const baixar = (p: PedidoDownload) => {
    if (baixando) return  // um por vez: o botão já está desligado, isto é o cinto
    const minha = ++serieT.current
    const nome = p.nome.trim()
    setTransferencia({ fase: 'conectando', nome })
    baixarArquivo(p, (feito, total) => {
      if (serieT.current === minha) setTransferencia({ fase: 'baixando', nome, feito, total })
    })
      .then(r => { if (serieT.current === minha) setTransferencia({ fase: 'pronto', nome: r.nome, total: r.total }) })
      .catch(e => {
        if (serieT.current !== minha) return
        const erro = erroTransferencia(e)
        setTransferencia({ fase: 'erro', nome, status: erro.status, mensagem: erro.mensagem })
      })
  }
  const fecharTransferencia = () => { serieT.current++; setTransferencia(null) }
  // Baixar de dentro do modal de conteúdo: o arquivo do pedido em curso, pelo
  // caminho DIGITADO (lexical) — com raiz-symlink, o real cairia fora das raízes.
  const baixarDoModal = () => { if (pedido) baixar({ servidor: pedido.servidor, diretorio: pedido.diretorio, nome: pedido.nome }) }

  // ── envio (upload) ─────────────────────────────────────────────────────────
  const [pedidoE, setPedidoE] = useState<PedidoEnvio | null>(null)
  // O `File` fica na página: o Sobrescrever (saída do 409) reenvia o MESMO arquivo.
  const [arquivoE, setArquivoE] = useState<File | null>(null)
  const [progressoE, setProgressoE] = useState<{ enviado: number; total: number } | null>(null)
  const [resultadoE, setResultadoE] = useState<ResultadoEnvio | null>(null)
  const [erroE, setErroE] = useState<ErroEnvio | null>(null)
  const [enviandoE, setEnviandoE] = useState(false)
  const [canceladoE, setCanceladoE] = useState<{ chegouInteiro: boolean } | null>(null)
  const envioRef = useRef<EnvioEmCurso | null>(null)
  const serieE = useRef(0)

  const enviar = (p: PedidoEnvio, arquivo: File) => {
    if (enviandoE) return
    const minha = ++serieE.current
    setPedidoE(p); setArquivoE(arquivo); setResultadoE(null); setErroE(null); setCanceladoE(null)
    setProgressoE({ enviado: 0, total: arquivo.size }); setEnviandoE(true)
    const envio = enviarArquivo(p, arquivo, (enviado, total) => {
      if (serieE.current === minha) setProgressoE({ enviado, total })
    })
    envioRef.current = envio
    envio.promessa
      .then(r => {
        if (serieE.current !== minha) return
        // 2xx sem JSON (nunca acontece com a API do repo): sem isto o modal
        // ficaria preso em "enviando" sem saída.
        if (!r || typeof r !== 'object') {
          setResultadoE(null)
          setErroE({ status: null, mensagem: 'A API respondeu sem o resultado — confira na pasta antes de reenviar.' })
          return
        }
        setResultadoE(r); setErroE(null)
      })
      .catch((e: ErroEnvioTransporte) => {
        if (serieE.current !== minha) return
        if (e?.cancelado) return  // `cancelarEnvio` já registrou o que importa
        setResultadoE(null); setErroE(erroEnvio(e))
      })
      .finally(() => { if (serieE.current === minha) { setEnviandoE(false); envioRef.current = null } })
  }
  // Saída do 409: o MESMO arquivo e o mesmo destino, agora com sobrescrever.
  const sobrescreverEnvio = () => { if (pedidoE && arquivoE) enviar({ ...pedidoE, sobrescrever: true }, arquivoE) }
  const cancelarEnvio = () => {
    if (!envioRef.current) return
    // Se o corpo já tinha subido inteiro, o servidor pode gravar mesmo assim —
    // a frase do cancelamento diz isso (spec §8.15).
    setCanceladoE({ chegouInteiro: envioChegouInteiro(progressoE) })
    envioRef.current.cancelar()
  }
  const fecharEnvio = () => {
    if (enviandoE) return  // enquanto sobe, o gesto é Cancelar
    serieE.current++
    setPedidoE(null); setResultadoE(null); setErroE(null); setCanceladoE(null); setProgressoE(null)
  }
  // O último ramo (`'erro'` sem `erroE`) é inalcançável — o `.then` acima
  // garante resultado ou erro — mas, se um dia for, o modal mostra Fechar.
  const estadoE: EstadoEnvio = enviandoE ? 'enviando'
    : canceladoE ? 'cancelado'
      : erroE?.status === 409 ? 'existe' : erroE ? 'erro' : resultadoE ? 'pronto' : 'erro'

  // Troca de aba com texto não gravado no editor: pergunta antes de descartar.
  const mudarAba = (id: string) => {
    if (id === aba) return
    if (aba === 'editar' && sujo) { setAbaPendente(id); return }
    setAba(id)
  }
  const confirmarTroca = () => { if (abaPendente) { setSujo(false); setAba(abaPendente) } ; setAbaPendente(null) }

  if (config.isLoading) return <PageSpinner />
  if (config.error && !config.data && migrationPendente(config.error)) {
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
  if (!config.data) {
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

      <InfoBanner storageKey="utilitarios_ver_v4">
        <strong>Ver arquivo</strong>: informe a pasta e o nome e clique em Iniciar — o conteúdo abre num modal, com
        botões para copiar e para <strong>baixar</strong> o arquivo para o seu computador (o Baixar também está em
        cada arquivo do navegador de pastas, e vale para binários). <strong>Criar/editar arquivo</strong>: escreva
        no editor, escolha a extensão e a pasta e grave; para alterar um arquivo que já existe, use "Carregar
        existente". <strong>Enviar arquivo</strong>: escolha um arquivo do seu computador (até o teto, com extensão
        da lista) e a pasta de destino; se já existir um com esse nome, a tela pede confirmação. Só pastas abaixo dos
        diretórios liberados pelo admin; toda leitura, download, gravação e envio fica registrado.
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

      {config.isError && (
        <p className="text-xs text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5" data-aviso="config-desatualizada">
          <AlertTriangle size={12} /> Não foi possível atualizar a configuração dos Utilitários
          ({mensagemErro(config.error, 'erro desconhecido')}); usando a última carregada.
        </p>
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
          onListar={listarPasta}
          onBaixar={baixar}
          baixando={baixando}
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
          sujo={sujo}
          onSujo={setSujo}
          onCarregar={carregar}
          onGravar={gravar}
          onListar={listarPasta}
          onBaixar={baixar}
          baixando={baixando}
        />
      )}

      {aba === 'enviar' && (
        <FormEnviarArquivo
          servidores={cfg.servidores}
          raizesPorServidor={raizesPorServidor}
          extensoes={cfg.extensoes}
          tetoKb={cfg.transferencia_max_kb ?? TETO_TRANSFERENCIA_KB_PADRAO}
          podeGravar={cfg.pode_gravar}
          enviando={enviandoE}
          onEnviar={enviar}
          onListar={listarPasta}
          onBaixar={baixar}
          baixando={baixando}
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
        onBaixar={baixarDoModal}
        baixando={baixando}
      />

      <BarraTransferencia estado={transferencia} onFechar={fecharTransferencia} />

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

      <ModalEnvioArquivo
        aberto={pedidoE !== null}
        pedido={pedidoE}
        estado={estadoE}
        progresso={progressoE}
        resultado={resultadoE}
        erro={erroE}
        chegouInteiro={canceladoE?.chegouInteiro ?? false}
        onFechar={fecharEnvio}
        onCancelar={cancelarEnvio}
        onSobrescrever={sobrescreverEnvio}
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
