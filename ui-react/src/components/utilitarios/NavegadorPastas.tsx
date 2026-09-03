// Utilitários — navegador de pastas (F6): desce das raízes cadastradas até a
// pasta desejada e devolve a pasta (Usar esta pasta) ou o arquivo clicado.
// Apresentação pura: a listagem vem por props (a página chama a API); daqui
// saem só gestos. É o que permite a bancada de node renderizar e clicar.
//
// Nunca sobe acima da raiz: o "Subir" segue o `pai` que a API devolve (null na
// raiz) e o nível zero é a lista de raízes. Ocultos ficam escondidos por
// padrão — `.ssh`, `.bash_history` e afins não aparecem por acidente.
import { useState, type KeyboardEvent } from 'react'
import { Folder, FolderOpen, FileText, Link2, ArrowUp, RefreshCw, AlertTriangle, Check, EyeOff, Eye } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Switch } from '../ui/Switch'
import {
  caminhoDaEntrada, descricaoEntrada, ehArquivo, migalhas, podeDescer,
  type EntradaPasta, type Listagem,
} from '../../lib/utilitariosNavegador'

export interface NavegadorPastasProps {
  aberto: boolean
  /** null = nível zero (raízes). */
  listagem: Listagem | null
  carregando: boolean
  erro: string | null
  mostrarOcultos: boolean
  /** null = voltar ao nível zero. */
  onNavegar: (caminho: string | null) => void
  onMostrarOcultos: (v: boolean) => void
  onUsarPasta: (caminho: string) => void
  /** Clique num arquivo: pasta real + nome. */
  onEscolherArquivo: (pasta: string, nome: string) => void
  onFechar: () => void
}

export function NavegadorPastas({
  aberto, listagem, carregando, erro, mostrarOcultos,
  onNavegar, onMostrarOcultos, onUsarPasta, onEscolherArquivo, onFechar,
}: NavegadorPastasProps) {
  const [filtro, setFiltro] = useState('')
  const atual = listagem?.caminho_real ?? null
  const trilha = migalhas(atual, listagem?.raiz ?? null)
  const nivelZero = atual === null
  const entradas = (listagem?.entradas ?? []).filter(e =>
    !filtro.trim() || e.nome.toLowerCase().includes(filtro.trim().toLowerCase()))

  const subir = () => {
    if (!listagem) return
    if (listagem.pai) onNavegar(listagem.pai)
    else if (!nivelZero) onNavegar(null)
  }
  const teclas = (e: KeyboardEvent<HTMLDivElement>) => {
    // Backspace fora de um campo de texto sobe um nível (nunca acima da raiz:
    // na raiz volta ao nível zero, no nível zero não faz nada).
    const alvo = e.target as HTMLElement
    if (e.key === 'Backspace' && alvo.tagName !== 'INPUT' && alvo.tagName !== 'TEXTAREA') {
      e.preventDefault(); subir()
    }
  }
  const abrir = (e: EntradaPasta) => {
    if (podeDescer(e)) { setFiltro(''); onNavegar(caminhoDaEntrada(atual, e)) }
    else if (ehArquivo(e) && atual) onEscolherArquivo(atual, e.nome)
  }

  return (
    <Modal open={aberto} onClose={onFechar} title="Navegar pelas pastas" size="lg">
      <div className="flex flex-col gap-3" onKeyDown={teclas} data-navegador>
        {/* migalhas */}
        <nav className="flex flex-wrap items-center gap-1 text-xs" aria-label="Caminho" data-migalhas>
          <button type="button" onClick={() => onNavegar(null)}
            className={`px-1.5 py-0.5 rounded hover:bg-canvas ${nivelZero ? 'text-ink font-semibold' : 'text-[#1A5FA8] dark:text-blue-400'}`}
            data-migalha="raizes">raízes</button>
          {trilha.map((m, i) => (
            <span key={m.caminho} className="inline-flex items-center gap-1">
              <span className="text-dim">/</span>
              <button type="button" onClick={() => onNavegar(m.caminho)}
                className={`px-1.5 py-0.5 rounded hover:bg-canvas font-mono ${i === trilha.length - 1 ? 'text-ink font-semibold' : 'text-[#1A5FA8] dark:text-blue-400'}`}
                data-migalha={m.caminho}>{m.rotulo}</button>
            </span>
          ))}
        </nav>

        <div className="flex items-center gap-2 flex-wrap">
          <Button type="button" size="sm" variant="secondary" onClick={subir} disabled={nivelZero || carregando}
            title="Subir um nível (Backspace)" data-acao="subir">
            <ArrowUp size={13} /> Subir
          </Button>
          <input value={filtro} onChange={e => setFiltro(e.target.value)} placeholder="filtrar por nome"
            aria-label="Filtrar por nome" autoComplete="off" spellCheck={false} data-campo="filtro"
            className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 w-44" />
          <span className="ml-auto">
            <Switch label="mostrar ocultos" checked={mostrarOcultos} onChange={e => onMostrarOcultos(e.target.checked)}
              disabled={nivelZero} data-campo="ocultos" />
          </span>
        </div>

        {erro && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800" data-erro>
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{erro}</p>
          </div>
        )}

        <div className="border border-edge rounded-lg overflow-auto max-h-[50vh]" data-lista>
          {carregando ? (
            <div className="flex items-center gap-2 text-sm text-ink py-6 justify-center" data-carregando>
              <RefreshCw size={16} className="animate-spin text-[#1A5FA8] dark:text-blue-400" />
              <span>Listando…</span>
            </div>
          ) : (
            <ul className="divide-y divide-edge/50">
              {entradas.map(e => {
                const desce = podeDescer(e)
                const arquivo = ehArquivo(e)
                const inerte = !desce && !arquivo
                return (
                  <li key={e.nome} data-entrada={e.nome} data-tipo={e.tipo} data-alvo={e.alvo ?? undefined}>
                    <button type="button" onClick={() => abrir(e)} disabled={inerte}
                      className="w-full flex items-center gap-3 px-3 py-1.5 text-left hover:bg-canvas disabled:opacity-50 disabled:cursor-not-allowed"
                      title={inerte ? 'Fora dos diretórios liberados ou link quebrado' : desce ? 'Entrar (Enter)' : 'Escolher este arquivo'}>
                      {e.tipo === 'link'
                        ? <Link2 size={14} className="text-slate-400 shrink-0" />
                        : desce
                          ? <Folder size={14} className="text-amber-500 shrink-0" />
                          : <FileText size={14} className="text-slate-400 shrink-0" />}
                      <span className="font-mono text-xs text-ink truncate flex-1">{e.nome}</span>
                      <span className="text-[11px] text-dim shrink-0">{descricaoEntrada(e)}</span>
                      {e.modificado_em && <span className="text-[11px] text-dim shrink-0 hidden md:inline">{e.modificado_em}</span>}
                    </button>
                  </li>
                )
              })}
              {entradas.length === 0 && (
                <li className="px-3 py-6 text-center text-xs text-dim" data-vazio>
                  {filtro ? 'Nada com esse nome nesta pasta.' : nivelZero ? 'Nenhuma raiz liberada.' : 'Pasta vazia.'}
                </li>
              )}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 flex-wrap text-[11px] text-dim">
          <span data-rodape>
            {listagem?.truncado && <span className="text-amber-700 dark:text-amber-300">Lista truncada em {listagem.entradas.length} entradas. </span>}
            {listagem && listagem.ocultos_omitidos > 0 && !mostrarOcultos && (
              <span className="inline-flex items-center gap-1"><EyeOff size={11} /> {listagem.ocultos_omitidos} ocultos escondidos</span>
            )}
            {listagem && mostrarOcultos && !nivelZero && <span className="inline-flex items-center gap-1"><Eye size={11} /> ocultos visíveis</span>}
          </span>
          <span className="inline-flex gap-2">
            <Button variant="secondary" size="sm" onClick={onFechar} data-acao="fechar">Fechar</Button>
            <Button size="sm" onClick={() => atual && onUsarPasta(atual)} disabled={nivelZero || carregando}
              title={nivelZero ? 'Entre numa raiz primeiro' : 'Preenche o campo Pasta com esta pasta'} data-acao="usar-pasta">
              {nivelZero ? <FolderOpen size={13} /> : <Check size={13} />} Usar esta pasta
            </Button>
          </span>
        </div>
      </div>
    </Modal>
  )
}
