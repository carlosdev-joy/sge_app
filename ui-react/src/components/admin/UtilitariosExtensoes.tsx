// Admin › Utilitários › Extensões — quais extensões a tela pode GRAVAR (a
// leitura é limitada só pelas raízes). Apresentação pura: dados e callbacks por
// props; confirmação antes de excluir e antes de incluir extensão de script.
import { useState, type FormEvent } from 'react'
import { FileType2, Plus, X, AlertTriangle } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { extensaoPedeConfirmacao, normalizarExtensao } from '../../lib/utilitariosAdmin'

export interface UtilitariosExtensoesProps {
  extensoes: string[]
  incluindo: boolean
  /** Devolve true quando o servidor aceitou — só então o campo é limpo. */
  onIncluir: (extensao: string) => Promise<boolean> | boolean
  onExcluir: (extensao: string) => void
}

export function UtilitariosExtensoes({ extensoes, incluindo, onIncluir, onExcluir }: UtilitariosExtensoesProps) {
  const [nova, setNova] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [confirmarScript, setConfirmarScript] = useState<string | null>(null)
  const [confirmarExclusao, setConfirmarExclusao] = useState<string | null>(null)

  const incluir = async (e: FormEvent) => {
    e.preventDefault()
    const r = normalizarExtensao(nova)
    if (!r.ok) { setErro(r.erro); return }
    setErro(null)
    if (extensoes.includes(r.valor)) { setErro(`'${r.valor}' já está na lista.`); return }
    if (extensaoPedeConfirmacao(r.valor)) { setConfirmarScript(r.valor); return }
    if (await onIncluir(r.valor)) setNova('')
  }

  const confirmarIncluirScript = async () => {
    const ext = confirmarScript
    setConfirmarScript(null)
    if (ext && await onIncluir(ext)) setNova('')
  }

  return (
    <section className="bg-panel border border-edge rounded-lg shadow-sm" data-secao="extensoes">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-edge">
        <FileType2 size={16} className="text-[#1A5FA8] dark:text-blue-400 shrink-0" />
        <h3 className="text-sm font-semibold text-ink">Extensões graváveis</h3>
        <span className="text-xs text-dim">— valem para criar e editar; ler não depende da extensão.</span>
      </header>

      <form onSubmit={incluir} className="flex flex-col md:flex-row gap-3 items-start px-4 py-3 border-b border-edge/60"
        data-form="incluir-extensao">
        <div className="w-full md:w-56">
          <Input label="Nova extensão" value={nova} placeholder="txt" autoComplete="off" spellCheck={false}
            onChange={e => { setNova(e.target.value); if (erro) setErro(null) }}
            error={erro ?? undefined} ajuda="Sem ponto; minúsculas e números, até 15 caracteres." />
        </div>
        <div className="md:pt-5">
          <Button type="submit" size="sm" disabled={!nova.trim() || incluindo} loading={incluindo} data-acao="incluir-extensao">
            <Plus size={13} /> Incluir
          </Button>
        </div>
      </form>

      <div className="px-4 py-3">
        {extensoes.length === 0 ? (
          <p className="text-xs text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5" data-vazio="extensoes">
            <AlertTriangle size={12} /> Nenhuma extensão cadastrada: ninguém consegue gravar arquivos pela tela.
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2" data-lista="extensoes">
            {extensoes.map(ext => (
              <li key={ext} data-extensao={ext}
                className="inline-flex items-center gap-1 pl-2.5 pr-1 py-0.5 rounded-full border border-edge bg-canvas text-xs font-mono text-ink">
                .{ext}
                <button type="button" onClick={() => setConfirmarExclusao(ext)}
                  className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 rounded-full p-0.5"
                  title={`Excluir a extensão ${ext}`} aria-label={`Excluir ${ext}`} data-acao="excluir">
                  <X size={12} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Modal open={confirmarExclusao !== null} onClose={() => setConfirmarExclusao(null)} title="Excluir extensão" size="sm">
        <div className="flex flex-col gap-5">
          <p className="text-sm text-ink">
            Excluir <span className="font-mono">.{confirmarExclusao}</span>? Ninguém mais conseguirá criar ou editar
            arquivos com essa extensão pela tela. Os arquivos que já existem no servidor não mudam.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirmarExclusao(null)}>Cancelar</Button>
            <Button variant="danger" size="sm" data-acao="confirmar-exclusao"
              onClick={() => { if (confirmarExclusao) onExcluir(confirmarExclusao); setConfirmarExclusao(null) }}>
              Excluir
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={confirmarScript !== null} onClose={() => setConfirmarScript(null)} title="Extensão de script" size="sm">
        <div className="flex flex-col gap-5">
          <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800">
            <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <p className="text-sm text-amber-800 dark:text-amber-200">
              <span className="font-mono">.{confirmarScript}</span> permite gravar scripts — inclusive os que
              os jobs shell executam em pipeline. Quem tem permissão de editar passa a poder trocar o que roda.
              Incluir mesmo assim?
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirmarScript(null)}>Cancelar</Button>
            <Button size="sm" data-acao="confirmar-script" onClick={confirmarIncluirScript}>
              Incluir
            </Button>
          </div>
        </div>
      </Modal>
    </section>
  )
}
