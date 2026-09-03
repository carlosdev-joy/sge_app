// Utilitários › Ver arquivo — o modal de execução: abre no Iniciar já em
// "buscando", e vira o conteúdo inteiro (bloco mono escuro, mesma exceção de
// fundo fixo do Console DataStage) ou o erro. Apresentação pura: o estado vem
// da página por props; o modal só mostra e devolve gestos (fechar, tentar de
// novo com "últimas N linhas").
//
// Copiar: `lib/copiar.ts`, não `navigator.clipboard` direto — a produção é
// servida por HTTP e a API de clipboard só existe em HTTPS. O botão diz o que
// aconteceu (copiado / use Ctrl+C / não copiou) e, quando não copiou,
// seleciona o texto para o Ctrl+C do usuário pegar o conteúdo CERTO.
import { useRef, useState, type FormEvent } from 'react'
import { Check, Copy, AlertTriangle, FileText, RefreshCw } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Badge } from '../ui/Badge'
import { AVISO_COPIA, copiarTexto, type ResultadoCopia } from '../../lib/copiar'
import {
  ULTIMAS_LINHAS_MAX, ULTIMAS_LINHAS_PADRAO, resumoConteudo, ultimasLinhas,
  type ConteudoArquivo, type ErroLeitura, type PedidoLeitura,
} from '../../lib/utilitariosArquivo'

export type EstadoLeitura = 'buscando' | 'pronto' | 'erro'

export interface ModalConteudoArquivoProps {
  aberto: boolean
  pedido: PedidoLeitura | null
  estado: EstadoLeitura
  resultado: ConteudoArquivo | null
  erro: ErroLeitura | null
  onFechar: () => void
  /** Repete o pedido pedindo só as últimas N linhas (saída do 413). */
  onRetentar: (ultimas: number) => void
}

export function ModalConteudoArquivo({
  aberto, pedido, estado, resultado, erro, onFechar, onRetentar,
}: ModalConteudoArquivoProps) {
  const caminhoPedido = pedido ? `${pedido.diretorio.replace(/\/+$/, '')}/${pedido.nome}` : ''
  return (
    <Modal open={aberto} onClose={onFechar} title="Conteúdo do arquivo" size="2xl">
      <div className="flex flex-col gap-3" data-estado={estado}>
        <p className="text-xs text-dim font-mono break-all" data-caminho>
          {resultado?.caminho ?? caminhoPedido}
        </p>

        {estado === 'buscando' && (
          <div className="flex items-center gap-2 text-sm text-ink py-6 justify-center" data-buscando>
            <RefreshCw size={16} className="animate-spin text-[#1A5FA8] dark:text-blue-400" />
            <span>Conectando ao servidor e lendo o arquivo…</span>
          </div>
        )}

        {estado === 'erro' && erro && (
          <BlocoErro erro={erro} pedido={pedido} onRetentar={onRetentar} />
        )}

        {estado === 'pronto' && resultado && (
          <BlocoConteudo resultado={resultado} />
        )}

        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={onFechar} data-acao="fechar">Fechar</Button>
        </div>
      </div>
    </Modal>
  )
}

function BlocoErro({ erro, pedido, onRetentar }: {
  erro: ErroLeitura
  pedido: PedidoLeitura | null
  onRetentar: (ultimas: number) => void
}) {
  const [ultimas, setUltimas] = useState(String(pedido?.ultimas_linhas ?? ULTIMAS_LINHAS_PADRAO))
  const n = ultimasLinhas(ultimas)
  const acimaDoTeto = erro.status === 413
  const retentar = (e: FormEvent) => {
    e.preventDefault()
    if (typeof n === 'number') onRetentar(n)
  }
  return (
    <div className="flex flex-col gap-3" data-erro={erro.status ?? 'rede'}>
      <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
        <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
        <p className="text-sm text-red-700 dark:text-red-300">{erro.mensagem}</p>
      </div>
      {acimaDoTeto && (
        <form onSubmit={retentar} className="flex items-end gap-3 flex-wrap" data-form="ultimas-linhas">
          <div className="w-44">
            <Input label="Últimas N linhas" value={ultimas} inputMode="numeric" autoComplete="off"
              onChange={e => setUltimas(e.target.value)}
              error={n === 'invalido' || n === null ? `Inteiro entre 1 e ${ULTIMAS_LINHAS_MAX}.` : undefined} />
          </div>
          <Button type="submit" size="sm" disabled={typeof n !== 'number'} data-acao="ver-fim">
            <FileText size={13} /> Ver o fim do arquivo
          </Button>
        </form>
      )}
    </div>
  )
}

function BlocoConteudo({ resultado }: { resultado: ConteudoArquivo }) {
  const [aviso, setAviso] = useState<ResultadoCopia | null>(null)
  const alvo = useRef<HTMLPreElement | null>(null)
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null)

  const copiar = async () => {
    // `bruto`: o conteúdo INTEIRO, com o `\n` final e os espaços que o arquivo tem.
    const r = await copiarTexto(resultado.conteudo, { bruto: true })
    if (r !== 'copiado' && alvo.current) {
      try { globalThis.getSelection?.()?.selectAllChildren(alvo.current) } catch { /* resgate, não erro */ }
    }
    setAviso(r)
    if (relogio.current) clearTimeout(relogio.current)
    relogio.current = setTimeout(() => setAviso(null), 2500)
  }

  return (
    <div className="flex flex-col gap-2" data-conteudo>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-dim" data-resumo>
          {resumoConteudo(resultado).map(p => <li key={p}>{p}</li>)}
          {resultado.truncado && <li><Badge value="warning">truncado</Badge></li>}
        </ul>
        <span className="inline-flex items-center gap-2">
          {/* A região `aria-live` existe SEMPRE e só o texto muda: leitor de tela
              não anuncia região que nasce junto com o conteúdo. */}
          <span data-aviso aria-live="polite"
            className={`text-xs ${aviso === 'copiado'
              ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
            {aviso ? AVISO_COPIA[aviso] : ''}
          </span>
          <Button size="sm" variant="secondary" onClick={copiar} data-acao="copiar"
            disabled={!resultado.conteudo}
            title={resultado.conteudo ? 'Copiar o conteúdo inteiro do arquivo' : 'Arquivo vazio: nada a copiar'}
            aria-label="Copiar conteúdo">
            {aviso === 'copiado'
              ? <Check size={13} className="text-emerald-600 dark:text-emerald-400" />
              : <Copy size={13} />}
            Copiar conteúdo
          </Button>
        </span>
      </div>
      {/* Fundo fixo escuro: exceção documentada (docs/ui-temas-cores.md, seção 4),
          a mesma do Console DataStage — conteúdo de terminal lê melhor assim nos
          dois temas. Rola DENTRO do bloco; a página nunca rola na horizontal. */}
      <pre ref={alvo} data-texto
        className="bg-gray-950 text-gray-200 rounded-lg p-4 overflow-auto max-h-[60vh] font-mono text-xs leading-relaxed whitespace-pre">
        {resultado.conteudo || <span className="text-gray-500">(arquivo vazio)</span>}
      </pre>
    </div>
  )
}
