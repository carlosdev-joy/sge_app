// Utilitários › Criar/editar arquivo — o modal da gravação: abre no Gravar já
// em "gravando" e vira o resultado, o pedido de confirmação (409: o arquivo
// existe — mostra tamanho e data do que será substituído) ou o erro.
// Apresentação pura: estado por props; devolve gestos (fechar, sobrescrever,
// ver o arquivo gravado).
import { AlertTriangle, CheckCircle2, RefreshCw, FileText } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { formatarTamanho } from '../../lib/utilitariosArquivo'
import { nomeArquivoCompleto, resumoGravacao, type ErroGravacao, type PedidoGravacao, type ResultadoGravacao } from '../../lib/utilitariosGravacao'

export type EstadoGravacao = 'gravando' | 'pronto' | 'existe' | 'erro'

export interface ModalGravacaoArquivoProps {
  aberto: boolean
  pedido: PedidoGravacao | null
  estado: EstadoGravacao
  resultado: ResultadoGravacao | null
  erro: ErroGravacao | null
  onFechar: () => void
  /** Repete o pedido com `sobrescrever: true` (saída do 409). */
  onSobrescrever: () => void
  /** Abre o conteúdo do arquivo que acabou de ser gravado. */
  onVerArquivo: (caminho: string) => void
}

export function ModalGravacaoArquivo({
  aberto, pedido, estado, resultado, erro, onFechar, onSobrescrever, onVerArquivo,
}: ModalGravacaoArquivoProps) {
  const caminhoPedido = pedido
    ? `${pedido.diretorio.replace(/\/+$/, '')}/${nomeArquivoCompleto(pedido.nome, pedido.extensao)}` : ''
  return (
    <Modal open={aberto} onClose={onFechar} title="Gravar arquivo" size="lg">
      <div className="flex flex-col gap-3" data-estado={estado}>
        <p className="text-xs text-dim font-mono break-all" data-caminho>{resultado?.caminho ?? caminhoPedido}</p>

        {estado === 'gravando' && (
          <div className="flex items-center gap-2 text-sm text-ink py-6 justify-center" data-gravando>
            <RefreshCw size={16} className="animate-spin text-[#1A5FA8] dark:text-blue-400" />
            <span>Gravando no servidor…</span>
          </div>
        )}

        {estado === 'existe' && erro && (
          <div className="flex flex-col gap-3" data-existe>
            <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800">
              <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-800 dark:text-amber-200">
                <p>{erro.mensagem}</p>
                {erro.existente && (
                  <p className="mt-1 text-xs">
                    O que está lá hoje: <strong>{formatarTamanho(erro.existente.tamanho_bytes)}</strong>
                    {erro.existente.modificado_em ? <>, modificado em <strong>{erro.existente.modificado_em}</strong></> : null}.
                    {' '}Ao sobrescrever, o servidor guarda uma cópia de segurança (se estiver ligada no Admin).
                  </p>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={onFechar} data-acao="cancelar">Cancelar</Button>
              <Button variant="danger" size="sm" onClick={onSobrescrever} data-acao="sobrescrever">Sobrescrever</Button>
            </div>
          </div>
        )}

        {estado === 'erro' && erro && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800"
            data-erro={erro.status ?? 'rede'}>
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{erro.mensagem}</p>
          </div>
        )}

        {estado === 'pronto' && resultado && (
          <div className="flex flex-col gap-3" data-pronto>
            <div className="flex items-start gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800">
              <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
              <ul className="text-sm text-emerald-800 dark:text-emerald-200 flex flex-col gap-0.5" data-resumo>
                {resumoGravacao(resultado).map(p => <li key={p}>{p}</li>)}
              </ul>
            </div>
          </div>
        )}

        {estado !== 'existe' && (
          <div className="flex justify-end gap-2">
            {estado === 'pronto' && resultado && (
              <Button variant="secondary" size="sm" onClick={() => onVerArquivo(resultado.caminho)} data-acao="ver-arquivo">
                <FileText size={13} /> Ver arquivo
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={onFechar} data-acao="fechar">Fechar</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}
