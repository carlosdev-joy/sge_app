// Peças compartilhadas SÓ pelos painéis de propriedades (./): campos de nome
// com draft/commit, o contrato das operações de caso do switch (CasoOps) e o
// tipo do resultado da simulação da decisão SQL (SimResult).
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Input } from '../../ui/Input'
import { Autocomplete } from '../../ui/Autocomplete'
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
// `fetchSuggestions` (opcional) liga o AUTOCOMPLETAR — hoje usado pela etapa
// DataStage, com os nomes REAIS dos jobs do projeto (ver lib/dsJobs.ts). Só vale
// no nó NOVO: num nó salvo o nome muda pelo rename transacional, não digitando.
export function NomeField({
  id, name, isNew, placeholder, onRename, fetchSuggestions, extra,
}: {
  id: string; name: string; isNew: boolean; placeholder: string
  onRename: (oldName: string, novo: string) => boolean
  fetchSuggestions?: (q: string) => Promise<string[]>
  extra?: ReactNode
}) {
  const [draft, setDraft] = useState(name)
  // Espelho em ref: o commit acontece no BLUR, e ao escolher uma sugestão do
  // autocompletar o blur pode disparar ANTES do re-render — lendo o state, o
  // commit veria o texto velho e a escolha se perderia em silêncio.
  const draftRef = useRef(name)
  function alterarDraft(v: string) { draftRef.current = v; setDraft(v) }
  useEffect(() => { draftRef.current = name; setDraft(name) }, [id, name])

  function commit() {
    const v = draftRef.current
    if (v.trim() === name) return
    // Nó salvo: onRename abre a confirmação do rename TRANSACIONAL (o input
    // volta ao nome atual; muda de verdade só depois do OK + sucesso da API).
    if (!onRename(id, v)) alterarDraft(name)
  }

  return (
    <div className="flex flex-col gap-1">
      {isNew && fetchSuggestions ? (
        // Commit no BLUR, igual ao Input — escolher uma sugestão só preenche o
        // campo. Um único caminho de confirmação evita rename em duplicidade.
        <Autocomplete
          label="Nome *"
          value={draft}
          onChange={alterarDraft}
          onBlur={commit}
          fetchSuggestions={fetchSuggestions}
          placeholder={placeholder}
          className="font-mono text-xs"
        />
      ) : (
        <Input
          label={isNew ? 'Nome *' : 'Nome'}
          value={draft}
          onChange={e => alterarDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
          placeholder={placeholder}
          className="font-mono text-xs"
        />
      )}
      {!isNew
        ? <p className="text-[11px] text-dim/70">Renomear um nó salvo atualiza dependências, condições e histórico — e pede confirmação.</p>
        : <p className="text-[11px] text-dim/70">Letras, números, _ . - (sem espaço)</p>}
      {extra}
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
