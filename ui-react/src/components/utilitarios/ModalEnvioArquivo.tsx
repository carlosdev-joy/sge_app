// Utilitários › Enviar arquivo — o modal do envio: abre no Enviar já em
// "enviando" (barra de progresso e Cancelar), e vira o resultado, o pedido de
// confirmação (409: o arquivo existe — mostra tamanho e data do que será
// substituído), o cancelamento ou o erro. Apresentação pura: estado por props;
// devolve gestos (fechar, cancelar, sobrescrever).
//
// Cancelar só aparece enquanto o corpo ainda está subindo: depois que chegou
// inteiro (ao nginx ou à API) o servidor pode gravar mesmo assim — e a frase
// do cancelamento diz isso (spec §8.15). Nessa fase o X, o Esc e o backdrop
// também NÃO abortam (achado da revisão da F4: abortar ali perdia o resultado
// de um arquivo que o servidor gravou de qualquer forma); o modal só fecha
// quando o servidor responde. O 504 pede para conferir a pasta antes de
// reenviar (§8.18). Região `aria-live` sr-only com marcos, como na faixa de
// download. Botões type="button": o modal renderiza inline.
import { AlertTriangle, CheckCircle2, Upload, XCircle } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { formatarTamanho } from '../../lib/utilitariosArquivo'
import {
  anuncioEnvio, envioChegouInteiro, fraseCancelamento, percentual, resumoEnvio, textoProgresso,
  type ErroEnvio, type EstadoEnvio, type PedidoEnvio, type ResultadoEnvio,
} from '../../lib/utilitariosTransferencia'

const NADA = () => { /* o corpo já subiu: fechar aqui só perderia o resultado */ }

export interface ModalEnvioArquivoProps {
  aberto: boolean
  pedido: PedidoEnvio | null
  estado: EstadoEnvio
  progresso: { enviado: number; total: number } | null
  resultado: ResultadoEnvio | null
  erro: ErroEnvio | null
  /** No cancelamento: o corpo já tinha chegado inteiro quando o usuário cancelou. */
  chegouInteiro: boolean
  onFechar: () => void
  onCancelar: () => void
  /** Repete o pedido com `sobrescrever: true` (saída do 409). */
  onSobrescrever: () => void
}

export function ModalEnvioArquivo({
  aberto, pedido, estado, progresso, resultado, erro, chegouInteiro, onFechar, onCancelar, onSobrescrever,
}: ModalEnvioArquivoProps) {
  const caminhoPedido = pedido ? `${pedido.diretorio.replace(/\/+$/, '')}/${pedido.nome}` : ''
  const pct = progresso ? percentual(progresso.enviado, progresso.total) : null
  const subiuTudo = envioChegouInteiro(progresso)
  // Enquanto sobe, fechar = cancelar; depois que subiu inteiro, fechar não faz
  // nada (o servidor vai responder); fora do envio, fechar é fechar.
  const aoFechar = estado === 'enviando' ? (subiuTudo ? NADA : onCancelar) : onFechar
  return (
    <Modal open={aberto} onClose={aoFechar} title="Enviar arquivo" size="lg">
      <div className="flex flex-col gap-3" data-estado={estado}>
        <div aria-live="polite" className="sr-only" data-anuncio>
          {aberto ? anuncioEnvio(estado, progresso, erro, chegouInteiro) : ''}
        </div>
        <p className="text-xs text-dim font-mono break-all" data-caminho>{resultado?.caminho ?? caminhoPedido}</p>

        {estado === 'enviando' && (
          <div className="flex flex-col gap-3 py-2" data-enviando>
            <div className="flex items-center gap-2 text-sm text-ink">
              <Upload size={16} className="text-[#1A5FA8] dark:text-blue-400 shrink-0" />
              <span data-frase-envio>
                {subiuTudo
                  ? 'Enviado ao servidor; gravando… aguarde a resposta (até 4 min numa gravação lenta).'
                  : `Enviando… ${progresso ? textoProgresso(progresso.enviado, progresso.total) : ''}`.trim()}
              </span>
            </div>
            <div className="h-2 w-full rounded bg-edge overflow-hidden" data-barra
              role="progressbar" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={pct ?? undefined} aria-valuetext={pct === null ? 'em andamento' : `${pct}%`}>
              <div className={`h-full bg-[#1A5FA8] dark:bg-blue-400 ${pct === null || subiuTudo ? 'animate-pulse' : ''}`}
                style={{ width: `${subiuTudo ? 100 : (pct ?? 33)}%` }} data-preenchido={pct ?? 'indeterminado'} />
            </div>
            {!subiuTudo && (
              <div className="flex justify-end">
                <Button type="button" variant="secondary" size="sm" onClick={onCancelar} data-acao="cancelar-envio">
                  <XCircle size={13} /> Cancelar
                </Button>
              </div>
            )}
          </div>
        )}

        {estado === 'cancelado' && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800"
            data-cancelado={chegouInteiro ? 'chegou' : 'antes'}>
            <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <p className="text-sm text-amber-800 dark:text-amber-200">{fraseCancelamento(chegouInteiro)}</p>
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
                    {' '}Ao sobrescrever, o servidor guarda uma cópia de segurança (se estiver ligada no Admin) e o
                    arquivo sobe de novo.
                  </p>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={onFechar} data-acao="cancelar">Cancelar</Button>
              <Button type="button" variant="danger" size="sm" onClick={onSobrescrever} data-acao="sobrescrever">Sobrescrever</Button>
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
          <div className="flex items-start gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800"
            data-pronto>
            <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <ul className="text-sm text-emerald-800 dark:text-emerald-200 flex flex-col gap-0.5" data-resumo>
              {resumoEnvio(resultado).map(p => <li key={p}>{p}</li>)}
            </ul>
          </div>
        )}

        {estado !== 'existe' && estado !== 'enviando' && (
          <div className="flex justify-end">
            <Button type="button" variant="secondary" size="sm" onClick={onFechar} data-acao="fechar">Fechar</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}
