// O projeto DataStage da conversa, e como trocá-lo.
//
// Por que isto existe (spec §3, "resolução do projeto"): `base`, `dsjob`,
// `dsx_consulta` e `isx_extrair` se RECUSAM a rodar sem projeto resolvido —
// é a guarda central contra consulta às cegas (risco 28). Quem conversa
// precisa ver, o tempo todo, em qual projeto o agente está olhando; sem isso
// a resposta "o job não existe" é indistinguível de "você está no projeto
// errado".
//
// Trocar o projeto não tem endpoint próprio: quem resolve é a ferramenta
// `resolver_projeto`, e o caminho para chamá-la é conversar. O botão aqui
// monta essa frase e a envia pelo mesmo POST de sempre — nada de um segundo
// contrato de API só para isso.
import { useState } from 'react'
import { FolderTree, Check } from 'lucide-react'

interface Props {
  projeto: string | null
  onTrocar: (novo: string) => void
  desabilitado?: boolean
}

export function IndicadorProjeto({ projeto, onTrocar, desabilitado }: Props) {
  const [abrindo, setAbrindo] = useState(false)
  const [novo, setNovo] = useState('')

  function confirmar() {
    const nome = novo.trim()
    if (!nome) return
    onTrocar(nome)
    setNovo('')
    setAbrindo(false)
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" data-agentes-projeto={projeto ?? ''}>
      <FolderTree className="w-4 h-4 text-dim" aria-hidden="true" />
      {projeto ? (
        <>
          <span className="text-dim">Projeto:</span>
          <span className="font-medium text-ink">{projeto}</span>
        </>
      ) : (
        <span className="text-dim">
          Nenhum projeto definido — diga qual projeto DataStage você quer consultar.
        </span>
      )}

      {!abrindo && (
        <button
          type="button"
          onClick={() => setAbrindo(true)}
          disabled={desabilitado}
          className="text-[#1A5FA8] dark:text-blue-400 hover:underline disabled:opacity-50 text-[13px]"
        >
          {projeto ? 'trocar projeto' : 'informar projeto'}
        </button>
      )}

      {abrindo && (
        <span className="flex items-center gap-1.5">
          <input
            autoFocus
            value={novo}
            onChange={e => setNovo(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); confirmar() }
              if (e.key === 'Escape') { setAbrindo(false); setNovo('') }
            }}
            aria-label="Nome do projeto DataStage"
            placeholder="ex.: BI_CVP"
            className="rounded border border-edge bg-panel text-ink px-2 py-1 text-[13px] w-40
                       focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]"
          />
          <button
            type="button"
            onClick={confirmar}
            disabled={!novo.trim()}
            aria-label="Confirmar projeto"
            className="rounded px-1.5 py-1 text-emerald-700 dark:text-emerald-300 hover:bg-canvas disabled:opacity-40"
          >
            <Check className="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => { setAbrindo(false); setNovo('') }}
            className="text-dim hover:text-ink text-[13px]"
          >
            cancelar
          </button>
        </span>
      )}
    </div>
  )
}
