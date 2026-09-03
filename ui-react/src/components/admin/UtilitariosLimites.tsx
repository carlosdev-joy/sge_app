// Admin › Utilitários › Limites — teto de tamanho e backup ao sobrescrever.
// Apresentação pura; o container remonta este componente (via `key`) quando o
// valor do servidor muda, então o estado local nasce sempre do que está gravado.
import { useState, type FormEvent } from 'react'
import { Gauge, Save } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Switch } from '../ui/Switch'
import { TETO_MAX_KB, tetoValido } from '../../lib/utilitariosAdmin'

export interface UtilitariosLimitesProps {
  tamanhoMaxKb: number
  backup: boolean
  salvando: boolean
  onSalvar: (tamanhoMaxKb: number, backup: boolean) => void
}

export function UtilitariosLimites({ tamanhoMaxKb, backup, salvando, onSalvar }: UtilitariosLimitesProps) {
  const [teto, setTeto] = useState(String(tamanhoMaxKb))
  const [bk, setBk] = useState(backup)
  const tetoNum = tetoValido(teto)
  const mudou = tetoNum !== tamanhoMaxKb || bk !== backup
  const podeSalvar = tetoNum !== null && mudou && !salvando

  const salvar = (e: FormEvent) => {
    e.preventDefault()
    if (!podeSalvar || tetoNum === null) return
    onSalvar(tetoNum, bk)
  }

  return (
    <section className="bg-panel border border-edge rounded-lg shadow-sm" data-secao="limites">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-edge">
        <Gauge size={16} className="text-[#1A5FA8] dark:text-blue-400 shrink-0" />
        <h3 className="text-sm font-semibold text-ink">Limites</h3>
      </header>
      <form onSubmit={salvar} className="grid grid-cols-1 md:grid-cols-[200px_1fr_auto] gap-4 items-start px-4 py-3" data-form="limites">
        <Input label="Teto por arquivo (KB)" value={teto} inputMode="numeric" autoComplete="off"
          onChange={e => setTeto(e.target.value)}
          error={tetoNum === null ? `Inteiro entre 1 e ${TETO_MAX_KB}.` : undefined}
          ajuda="Acima disso a leitura só mostra as últimas N linhas, e a gravação é recusada." />
        <div className="md:pt-6">
          <Switch label="Guardar cópia de segurança ao sobrescrever" checked={bk} onChange={e => setBk(e.target.checked)}
            hint="Antes de gravar por cima de um arquivo, o anterior vira nome.ext.bak-<data> na mesma pasta." />
        </div>
        <div className="md:pt-5">
          <Button type="submit" size="sm" disabled={!podeSalvar} loading={salvando} data-acao="salvar-limites">
            <Save size={13} /> Salvar
          </Button>
        </div>
      </form>
    </section>
  )
}
