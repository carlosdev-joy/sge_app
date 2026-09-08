// Utilitários › Enviar arquivo — o formulário (spec
// docs/spec-utilitarios-transferencia.md, F4): servidor, pasta (com Navegar…),
// o arquivo do PC, o nome no servidor (pré-preenchido com o nome local,
// editável) e Enviar. Apresentação pura: a rede fica na página, o que permite
// a bancada de node renderizar e clicar aqui.
//
// Enviar é type="button" e o <form> não submete: Enter num campo NÃO pode
// disparar um upload (mesma regra do Gravar). Quem não pode gravar vê o
// formulário desabilitado com a explicação. Os avisos (extensão fora da lista,
// arquivo acima do teto, pasta fora das raízes) vêm ANTES da API — o servidor
// continua a autoridade (realpath, lista, teto, auditoria).
import { useRef, useState, type ChangeEvent } from 'react'
import { Upload, FolderOpen, AlertTriangle } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { CampoPasta } from './CampoPasta'
import { NavegadorPastas } from './NavegadorPastas'
import { useNavegadorPastas, type ListarPasta } from './useNavegadorPastas'
import type { ServidorUtil } from '../../lib/utilitariosAdmin'
import { formatarTamanho } from '../../lib/utilitariosArquivo'
import { inicioNavegacao } from '../../lib/utilitariosNavegador'
import {
  avisoEnvio, envioPronto, type PedidoDownload, type PedidoEnvio,
} from '../../lib/utilitariosTransferencia'

export interface FormEnviarArquivoProps {
  servidores: ServidorUtil[]
  raizesPorServidor: Record<string, string[]>
  extensoes: string[]
  /** Teto do envio em KB (`transferencia_max_kb` do config). */
  tetoKb: number
  podeGravar: boolean
  enviando: boolean
  onEnviar: (pedido: PedidoEnvio, arquivo: File) => void
  /** Lista pastas para o navegador; sem ele o botão Navegar… não aparece. */
  onListar?: ListarPasta
  /** Baixa um arquivo escolhido no navegador; sem ele o ícone não aparece. */
  onBaixar?: (pedido: PedidoDownload) => void
  baixando?: boolean
}

export function FormEnviarArquivo({
  servidores, raizesPorServidor, extensoes, tetoKb, podeGravar, enviando, onEnviar, onListar, onBaixar, baixando,
}: FormEnviarArquivoProps) {
  const [servidor, setServidor] = useState(servidores[0]?.id ?? 'datastage')
  const [diretorio, setDiretorio] = useState('')
  const [nome, setNome] = useState('')
  const [arquivo, setArquivo] = useState<File | null>(null)
  const seletor = useRef<HTMLInputElement>(null)
  const nav = useNavegadorPastas(servidor, onListar)

  const raizes = raizesPorServidor[servidor] ?? []
  const tamanho = arquivo ? arquivo.size : null
  const avNome = avisoEnvio(nome, tamanho, extensoes, tetoKb)
  const semExtensoes = extensoes.length === 0
  const pronto = envioPronto(diretorio, nome, tamanho, raizes, extensoes, tetoKb, podeGravar) && !enviando
  const servidorAtual = servidores.find(s => s.id === servidor)
  const desabilitado = !podeGravar

  // Arquivo escolhido: o nome no servidor começa igual ao local (editável).
  const escolher = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setArquivo(f)
    if (f) setNome(f.name)
  }
  const enviar = () => {
    if (!pronto || !arquivo) return
    onEnviar({ servidor, diretorio: diretorio.trim(), nome: nome.trim(), sobrescrever: false }, arquivo)
  }

  return (
    <form onSubmit={e => e.preventDefault()} className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3"
      data-form="enviar-arquivo">
      {desabilitado && (
        <p className="text-xs text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5" data-aviso="sem-permissao">
          <AlertTriangle size={12} /> Seu perfil só lê: enviar arquivos exige a permissão de cadastrar/editar.
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

      <div className="grid grid-cols-1 md:grid-cols-[auto_1fr_auto] gap-3 items-start">
        <div className="relative flex flex-col gap-1">
          <span className="text-xs text-dim font-medium">Arquivo do seu computador</span>
          {/* O input real fica só para leitor de tela e teclado; o botão abre o seletor.
              `relative` no pai: sr-only é absolute e, sem ancestral posicionado, esticaria
              a página (ver ui/Checkbox). */}
          <input ref={seletor} type="file" className="sr-only" onChange={escolher} disabled={desabilitado || enviando}
            aria-label="Escolher arquivo do seu computador" data-campo="arquivo" />
          <Button type="button" variant="secondary" onClick={() => seletor.current?.click()}
            disabled={desabilitado || enviando} data-acao="escolher">
            <FolderOpen size={14} /> Escolher arquivo…
          </Button>
          <span className="text-[11px] text-dim break-all" data-arquivo-escolhido={arquivo ? arquivo.name : ''}>
            {arquivo ? `${arquivo.name} · ${formatarTamanho(arquivo.size)}` : 'nenhum arquivo escolhido'}
          </span>
          <span className="text-[11px] text-dim">
            Até {formatarTamanho(tetoKb * 1024)}{semExtensoes ? '' : `; extensões: ${extensoes.map(x => `.${x}`).join(', ')}`}.
          </span>
        </div>
        <Input label="Nome no servidor" value={nome} onChange={e => setNome(e.target.value)}
          placeholder="relatorio.txt" autoComplete="off" spellCheck={false} disabled={desabilitado || enviando}
          error={avNome ?? undefined}
          ajuda="Começa igual ao nome do arquivo escolhido; a extensão (a última) precisa estar na lista. Fica como você digitar." />
        <div className="md:pt-5">
          <Button type="button" onClick={enviar} disabled={!pronto} loading={enviando} data-acao="enviar"
            title={arquivo ? 'Envia o arquivo para a pasta no servidor' : 'Escolha um arquivo primeiro'}>
            <Upload size={14} /> Enviar
          </Button>
        </div>
      </div>

      {nav.disponivel && (
        <NavegadorPastas
          aberto={nav.aberto} listagem={nav.listagem} carregando={nav.carregando} erro={nav.erro}
          mostrarOcultos={nav.ocultos} filtro={nav.filtro} onFiltro={nav.mudarFiltro}
          onNavegar={nav.navegar} onMostrarOcultos={nav.mudarOcultos}
          onUsarPasta={c => { setDiretorio(c); nav.fechar() }}
          // Escolher um arquivo existente = "vai por cima deste nome": a pasta
          // e o nome vêm de lá; o 409 pede a confirmação na hora do envio.
          onEscolherArquivo={(p, n) => { setDiretorio(p); setNome(n); nav.fechar() }}
          onFechar={nav.fechar}
          onBaixar={onBaixar ? (p, n) => onBaixar({ servidor, diretorio: p, nome: n }) : undefined}
          baixando={baixando}
        />
      )}
    </form>
  )
}
