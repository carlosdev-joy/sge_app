// Peças compartilhadas SÓ pelos painéis de propriedades (./): campos de nome
// com draft/commit, o contrato das operações de caso do switch (CasoOps) e o
// tipo do resultado da simulação da decisão SQL (SimResult).
import { useEffect, useState } from 'react'
import { Input } from '../../ui/Input'
import type { CasoSwitch } from '../DecisaoNode'

// Operações de caso do SWITCH expostas ao painel (implementadas no editor,
// porque mexem nas ARESTAS além da condição).
export interface CasoOps {
  onAlternarModo: (nodeId: string, paraSwitch: boolean) => void
  onAddCaso: (nodeId: string) => void
  // Retorna false quando a validação rejeitou (o input de nome reverte o draft).
  onUpdateCaso: (nodeId: string, idx: number, patch: Partial<CasoSwitch>) => boolean
  onRemoveCaso: (nodeId: string, idx: number) => void
  onMoveCaso: (nodeId: string, idx: number, delta: -1 | 1) => void
}

// Resultado de uma simulação da decisão SQL (POST /jobs/decisao-simular).
// Binária devolve resultado/ramo; switch devolve `caso` (nome ou 'senao').
export interface SimResult { valor_obtido: string | null; resultado?: boolean; ramo?: 'sim' | 'nao'; caso?: string }

// Campo de nome reutilizado pelos dois painéis: editável só se `isNew`.
export function NomeField({
  id, name, isNew, placeholder, onRename,
}: { id: string; name: string; isNew: boolean; placeholder: string; onRename: (oldName: string, novo: string) => boolean }) {
  const [draft, setDraft] = useState(name)
  useEffect(() => { setDraft(name) }, [id, name])

  function commit() {
    if (draft.trim() === name) return
    // Nó salvo: onRename abre a confirmação do rename TRANSACIONAL (o input
    // volta ao nome atual; muda de verdade só depois do OK + sucesso da API).
    if (!onRename(id, draft)) setDraft(name)
  }

  return (
    <div className="flex flex-col gap-1">
      <Input
        label={isNew ? 'Nome *' : 'Nome'}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
        placeholder={placeholder}
        className="font-mono text-xs"
      />
      {!isNew
        ? <p className="text-[11px] text-dim/70">Renomear um nó salvo atualiza dependências, condições e histórico — e pede confirmação.</p>
        : <p className="text-[11px] text-dim/70">Letras, números, _ . - (sem espaço)</p>}
    </div>
  )
}

// Nome de um CASO do switch: draft local com commit no blur/Enter — validar por
// keystroke tornaria certos nomes impossíveis de digitar (ex.: um nome que passa
// por um prefixo de caso existente, ou limpar o campo para redigitar).
export function CasoNomeInput({
  nome, placeholder, onCommit,
}: { nome: string; placeholder: string; onCommit: (novo: string) => boolean }) {
  const [draft, setDraft] = useState(nome)
  useEffect(() => { setDraft(nome) }, [nome])
  return (
    <Input
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onBlur={() => {
        if (draft.trim() === nome) { setDraft(nome); return }
        if (!onCommit(draft)) setDraft(nome)
      }}
      onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
      placeholder={placeholder}
      className="w-full font-mono text-xs"
    />
  )
}
