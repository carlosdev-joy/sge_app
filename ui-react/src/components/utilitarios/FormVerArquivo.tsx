// Utilitários › Ver arquivo — o formulário: servidor, pasta, nome, últimas N
// linhas (opcional) e Iniciar. Apresentação pura (props + callback): a rede
// fica na página, o que permite a bancada de node renderizar e clicar aqui.
//
// O campo Pasta diz a que raiz o caminho pertence ("abaixo de /dados/bi") ou
// que está fora das raízes — ANTES de chamar a API. O servidor continua a
// autoridade (realpath + auditoria); o aviso só poupa uma ida que vai falhar.
import { useState, type FormEvent } from 'react'
import { Play } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import type { ServidorUtil } from '../../lib/utilitariosAdmin'
import {
  ULTIMAS_LINHAS_MAX, avisoNome, avisoPasta, pedidoPronto, ultimasLinhas,
  type PedidoLeitura,
} from '../../lib/utilitariosArquivo'

export interface FormVerArquivoProps {
  servidores: ServidorUtil[]
  /** Raízes ATIVAS do servidor escolhido (caminhos). */
  raizesPorServidor: Record<string, string[]>
  iniciando: boolean
  onIniciar: (pedido: PedidoLeitura) => void
}

export function FormVerArquivo({ servidores, raizesPorServidor, iniciando, onIniciar }: FormVerArquivoProps) {
  const [servidor, setServidor] = useState(servidores[0]?.id ?? 'datastage')
  const [diretorio, setDiretorio] = useState('')
  const [nome, setNome] = useState('')
  const [ultimas, setUltimas] = useState('')

  const raizes = raizesPorServidor[servidor] ?? []
  const avPasta = avisoPasta(diretorio, raizes)
  const avNome = avisoNome(nome)
  const avUltimas = ultimasLinhas(ultimas) === 'invalido'
    ? `Inteiro entre 1 e ${ULTIMAS_LINHAS_MAX}.` : undefined
  const pronto = pedidoPronto(diretorio, nome, ultimas, raizes) && !iniciando
  const servidorAtual = servidores.find(s => s.id === servidor)

  const iniciar = (e: FormEvent) => {
    e.preventDefault()
    if (!pronto) return
    const n = ultimasLinhas(ultimas)
    const pedido: PedidoLeitura = { servidor, diretorio: diretorio.trim(), nome: nome.trim() }
    if (typeof n === 'number') pedido.ultimas_linhas = n
    onIniciar(pedido)
  }

  return (
    <form onSubmit={iniciar} className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3"
      data-form="ver-arquivo">
      <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-3">
        <Select label="Servidor" value={servidor} onChange={e => setServidor(e.target.value)}
          ajuda={servidorAtual && !servidorAtual.configurado ? 'SSH não configurado nesta instância da API' : undefined}>
          {servidores.map(s => (
            <option key={s.id} value={s.id}>{s.label}{s.configurado ? '' : ' (não configurado)'}</option>
          ))}
        </Select>
        <div className="flex flex-col gap-1">
          <Input label="Pasta" value={diretorio} onChange={e => setDiretorio(e.target.value)}
            placeholder={raizes[0] ? `${raizes[0]}/…` : '/caminho/da/pasta'} autoComplete="off" spellCheck={false}
            error={avPasta?.tom === 'erro' ? avPasta.texto : undefined}
            ajuda="Caminho absoluto no servidor, abaixo de uma raiz liberada." />
          {avPasta?.tom === 'neutro' && (
            <span className="text-[11px] text-dim" data-raiz-de>{avPasta.texto}</span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-[1fr_180px_auto] gap-3 items-start">
        <Input label="Nome do arquivo" value={nome} onChange={e => setNome(e.target.value)}
          placeholder="carga_20260903.txt" autoComplete="off" spellCheck={false}
          error={avNome ?? undefined} />
        <Input label="Últimas N linhas (opcional)" value={ultimas} onChange={e => setUltimas(e.target.value)}
          inputMode="numeric" placeholder="tudo" autoComplete="off"
          error={avUltimas}
          ajuda="Para log grande: mostra só o fim do arquivo." />
        <div className="md:pt-5">
          <Button type="submit" disabled={!pronto} loading={iniciando} data-acao="iniciar">
            <Play size={14} /> Iniciar
          </Button>
        </div>
      </div>
    </form>
  )
}
