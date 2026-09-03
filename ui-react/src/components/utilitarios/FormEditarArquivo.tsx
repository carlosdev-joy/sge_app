// Utilitários › Criar/editar arquivo — o formulário: servidor, pasta, nome (sem
// extensão), extensão da lista do admin, codificação, editor mono com contador,
// Carregar existente e Gravar. Apresentação pura (props + callbacks): a rede
// fica na página; a bancada de node renderiza e clica aqui.
//
// Quem não pode gravar (operador) vê o editor DESABILITADO com a explicação —
// não um 403 surpresa depois de digitar. Ctrl+Enter grava (mesmo gesto do
// editor de fluxo); Enter num campo de texto NÃO grava — gravar cria arquivo no
// servidor, e o gesto tem de ser o botão ou o atalho.
//
// `sujo` (texto ainda não gravado) é da PÁGINA: ela zera quando a gravação
// responde e é ela quem segura a troca de aba. Um estado espelhado aqui
// dessincronizava depois da primeira gravação (revisão da F5).
import { useState, type KeyboardEvent } from 'react'
import { Save, FolderOpen, AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { CampoPasta } from './CampoPasta'
import { NavegadorPastas } from './NavegadorPastas'
import { useNavegadorPastas, type ListarPasta } from './useNavegadorPastas'
import type { ServidorUtil } from '../../lib/utilitariosAdmin'
import { avisoPasta } from '../../lib/utilitariosArquivo'
import { inicioNavegacao } from '../../lib/utilitariosNavegador'
import {
  CODIFICACOES_OPCOES, avisoNomeBase, codificacaoValida, contarBytes, contarLinhas, ehCodificacao, extensaoPadrao,
  extensaoValida, foraDoLatin1, gravacaoPronta, nomeArquivoCompleto, separarNomeExtensao,
  type Codificacao, type PedidoGravacao,
} from '../../lib/utilitariosGravacao'

export interface CarregadoExistente {
  conteudo: string
  codificacao: string
}

export interface FormEditarArquivoProps {
  servidores: ServidorUtil[]
  raizesPorServidor: Record<string, string[]>
  extensoes: string[]
  podeGravar: boolean
  gravando: boolean
  carregando: boolean
  /** Há texto no editor que ainda não foi gravado (estado da página). */
  sujo: boolean
  onSujo: (sujo: boolean) => void
  /** Lê o arquivo (nome completo) e devolve conteúdo + codificação detectada; null se falhou. */
  onCarregar: (pedido: { servidor: string; diretorio: string; nome: string }) => Promise<CarregadoExistente | null>
  onGravar: (pedido: PedidoGravacao) => void
  /** Lista pastas para o navegador; sem ele o botão Navegar… não aparece. */
  onListar?: ListarPasta
  /** Preenchimento inicial (ex.: vindo do "Ver arquivo"). */
  inicial?: { diretorio?: string; nome?: string; extensao?: string }
}

export function FormEditarArquivo({
  servidores, raizesPorServidor, extensoes, podeGravar, gravando, carregando, sujo, onSujo, onCarregar, onGravar,
  onListar, inicial,
}: FormEditarArquivoProps) {
  const [servidor, setServidor] = useState(servidores[0]?.id ?? 'datastage')
  const [diretorio, setDiretorio] = useState(inicial?.diretorio ?? '')
  const [nome, setNome] = useState(inicial?.nome ?? '')
  // Só o que o usuário ESCOLHEU; enquanto não escolhe, vale o padrão da lista —
  // derivado a cada render, então extensões que chegam depois (refetch após o
  // admin cadastrar) entram sem efeito nem estado preso em ''.
  const [extensaoEscolhida, setExtensaoEscolhida] = useState(inicial?.extensao ?? '')
  const extensao = extensaoEscolhida || extensaoPadrao(extensoes)
  const [codificacao, setCodificacao] = useState<Codificacao>('utf-8')
  const [conteudo, setConteudo] = useState('')
  const nav = useNavegadorPastas(servidor, onListar)

  const raizes = raizesPorServidor[servidor] ?? []
  const avPasta = avisoPasta(diretorio, raizes)
  const avNome = avisoNomeBase(nome, extensao)
  const semExtensoes = extensoes.length === 0
  const extOk = extensaoValida(extensao, extensoes)
  const fora = codificacao === 'latin-1' ? foraDoLatin1(conteudo) : null
  const pronto = gravacaoPronta({ diretorio, nome, extensao, conteudo, codificacao }, raizes, extensoes, podeGravar)
    && !gravando && !carregando
  const podeCarregar = podeGravar && !!diretorio.trim() && !!nome.trim() && !(avPasta && avPasta.tom === 'erro')
    && !avNome && extOk && !carregando && !gravando
  const servidorAtual = servidores.find(s => s.id === servidor)
  const bytes = contarBytes(conteudo, codificacao)
  const linhas = contarLinhas(conteudo)

  const mudarConteudo = (v: string) => { setConteudo(v); onSujo(true) }

  const gravar = () => {
    if (!pronto) return
    onGravar({ servidor, diretorio: diretorio.trim(), nome: nome.trim(), extensao: extensao.trim().toLowerCase(),
               conteudo, codificacao, sobrescrever: false })
  }
  const teclas = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); gravar() }
  }

  const carregar = async () => {
    if (!podeCarregar) return
    const r = await onCarregar({ servidor, diretorio: diretorio.trim(), nome: nomeArquivoCompleto(nome, extensao) })
    if (!r) return
    setConteudo(r.conteudo)
    // A codificação passa a ser a detectada: gravar de volta mantém os bytes.
    setCodificacao(codificacaoValida(r.codificacao))
    onSujo(false)
  }

  // Mudar o nome pelo campo aceita "carga.txt" (em qualquer caixa) e separa a
  // extensão, se ela estiver na lista.
  const mudarNome = (v: string) => {
    const { nome: n, extensao: e } = separarNomeExtensao(v)
    if (e && extensoes.includes(e) && v.trim().toLowerCase().endsWith(`.${e}`)) { setNome(n); setExtensaoEscolhida(e) }
    else setNome(v)
  }
  // Arquivo escolhido no navegador: pasta + nome separado da extensão. Extensão
  // fora da lista fica marcada "(não liberada)" — o Carregar existente funciona
  // (leitura não depende da lista), o Gravar fica desligado e diz por quê.
  const escolherArquivo = (pasta: string, completo: string) => {
    setDiretorio(pasta)
    const { nome: n, extensao: e } = separarNomeExtensao(completo)
    if (e) { setNome(n); setExtensaoEscolhida(e) } else setNome(completo)
    nav.fechar()
  }

  const desabilitado = !podeGravar

  return (
    <form onSubmit={e => e.preventDefault()} className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3"
      data-form="editar-arquivo">
      {desabilitado && (
        <p className="text-xs text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5" data-aviso="sem-permissao">
          <AlertTriangle size={12} /> Seu perfil só lê: criar e editar arquivos exige a permissão de cadastrar/editar.
        </p>
      )}
      {!desabilitado && semExtensoes && (
        <p className="text-xs text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5" data-aviso="sem-extensoes">
          <AlertTriangle size={12} /> Nenhuma extensão liberada — o admin inclui em Admin › Utilitários.
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-3">
        <Select label="Servidor" value={servidor} onChange={e => setServidor(e.target.value)} disabled={desabilitado}
          ajuda={servidorAtual && !servidorAtual.configurado ? 'SSH não configurado nesta instância da API' : undefined}>
          {servidores.map(s => (
            <option key={s.id} value={s.id}>{s.label}{s.configurado ? '' : ' (não configurado)'}</option>
          ))}
        </Select>
        <CampoPasta value={diretorio} onChange={setDiretorio} raizes={raizes} disabled={desabilitado}
          ajuda="Caminho absoluto no servidor, abaixo de uma raiz liberada. A pasta precisa existir."
          onNavegar={nav.disponivel ? () => nav.abrir(inicioNavegacao(diretorio, raizes)) : undefined} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_160px_200px_auto] gap-3 items-start">
        <Input label="Nome do arquivo (sem a extensão)" value={nome} onChange={e => mudarNome(e.target.value)}
          placeholder="parametros_carga" autoComplete="off" spellCheck={false} disabled={desabilitado}
          error={avNome ?? undefined} />
        <Select label="Extensão" value={extensao} onChange={e => setExtensaoEscolhida(e.target.value)}
          disabled={desabilitado || semExtensoes} data-campo="extensao"
          error={!semExtensoes && extensao && !extOk ? 'Extensão não liberada.' : undefined}>
          {extensoes.map(x => <option key={x} value={x}>.{x}</option>)}
          {extensao && !extensoes.includes(extensao) && <option value={extensao}>.{extensao} (não liberada)</option>}
        </Select>
        <Select label="Codificação" value={codificacao} data-campo="codificacao" disabled={desabilitado}
          onChange={e => { if (ehCodificacao(e.target.value)) setCodificacao(e.target.value) }}
          ajuda="O servidor do DataStage costuma usar Latin-1.">
          {CODIFICACOES_OPCOES.map(o => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
        </Select>
        <div className="md:pt-5">
          <Button type="button" variant="secondary" onClick={() => void carregar()} disabled={!podeCarregar}
            loading={carregando} data-acao="carregar" title="Traz o conteúdo do arquivo que já existe para o editor">
            <FolderOpen size={14} /> Carregar existente
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <Textarea label="Conteúdo" value={conteudo} onChange={e => mudarConteudo(e.target.value)} onKeyDown={teclas}
          rows={16} spellCheck={false} disabled={desabilitado} data-campo="conteudo"
          className="font-mono text-xs leading-relaxed whitespace-pre"
          error={fora ? `Caractere fora do Latin-1 na linha ${fora.linha} (${JSON.stringify(fora.char)}): grave em UTF-8 ou troque o caractere.` : undefined}
          ajuda="Quebras de linha do Windows (CRLF) viram LF ao gravar; o arquivo termina com quebra de linha. Ctrl+Enter grava." />
        <div className="flex items-center justify-between text-[11px] text-dim">
          <span data-contador>{`${linhas} ${linhas === 1 ? 'linha' : 'linhas'} · ${bytes} bytes (${codificacao})${sujo ? ' · não gravado' : ''}`}</span>
          <span className="inline-flex items-center gap-2">
            {gravando && <RefreshCw size={12} className="animate-spin" />}
            <Button type="button" size="sm" onClick={gravar} disabled={!pronto} loading={gravando} data-acao="gravar">
              <Save size={13} /> Gravar
            </Button>
          </span>
        </div>
      </div>

      {nav.disponivel && (
        <NavegadorPastas
          aberto={nav.aberto} listagem={nav.listagem} carregando={nav.carregando} erro={nav.erro}
          mostrarOcultos={nav.ocultos} onNavegar={nav.navegar} onMostrarOcultos={nav.mudarOcultos}
          onUsarPasta={c => { setDiretorio(c); nav.fechar() }}
          onEscolherArquivo={escolherArquivo}
          onFechar={nav.fechar}
        />
      )}
    </form>
  )
}
