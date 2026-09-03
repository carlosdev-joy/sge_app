// Utilitários — o campo Pasta dos dois formulários (Ver arquivo e Criar/editar):
// caminho absoluto abaixo de uma raiz, com o aviso "abaixo de /raiz" ou o erro
// ANTES da API, e o botão Navegar… (F6) que abre o navegador de pastas quando o
// formulário oferece `onNavegar`.
import { FolderSearch } from 'lucide-react'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { avisoPasta } from '../../lib/utilitariosArquivo'

export interface CampoPastaProps {
  value: string
  onChange: (v: string) => void
  /** Raízes ATIVAS do servidor escolhido. */
  raizes: string[]
  disabled?: boolean
  ajuda?: string
  /** Abre o navegador; sem ele o botão não aparece. */
  onNavegar?: () => void
}

export function CampoPasta({ value, onChange, raizes, disabled, ajuda, onNavegar }: CampoPastaProps) {
  const aviso = avisoPasta(value, raizes)
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <Input label="Pasta" value={value} onChange={e => onChange(e.target.value)} disabled={disabled}
            placeholder={raizes[0] ? `${raizes[0]}/…` : '/caminho/da/pasta'} autoComplete="off" spellCheck={false}
            error={aviso?.tom === 'erro' ? aviso.texto : undefined}
            ajuda={ajuda ?? 'Caminho absoluto no servidor, abaixo de uma raiz liberada.'} />
        </div>
        {onNavegar && (
          <div className="pt-5">
            <Button type="button" variant="secondary" onClick={onNavegar} disabled={disabled || raizes.length === 0}
              title="Escolher a pasta navegando a partir das raízes liberadas" data-acao="navegar">
              <FolderSearch size={14} /> Navegar…
            </Button>
          </div>
        )}
      </div>
      {aviso?.tom === 'neutro' && (
        <span className="text-[11px] text-dim" data-raiz-de>{aviso.texto}</span>
      )}
    </div>
  )
}
