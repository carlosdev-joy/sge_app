// ─────────────────────────────────────────────────────────────────────────────
// CONTEÚDO do painel de propriedades — edita o nó selecionado ao vivo.
// Desde a fase 3 do redesign é renderizado dentro do DOCK INFERIOR do
// FluxoEditor (que fornece o chrome: header com resumo do nó, botões de
// colapsar/maximizar/fechar e a alça de redimensionar). Este componente cuida
// só do formulário por tipo de nó.
// ─────────────────────────────────────────────────────────────────────────────
import type { Node } from '@xyflow/react'
import { MousePointerClick } from 'lucide-react'
import type { NodeCondition } from '../DecisaoNode'
import type { NotifyConfig, SqlConfig, AguardeConfig, MsgGrupo } from '../fluxoTypes'
import type { CasoOps } from './shared'
import { PainelEtapa } from './PainelEtapa'
import { PainelDecisao } from './PainelDecisao'
import { PainelNotificacao } from './PainelNotificacao'
import { PainelSql } from './PainelSql'
import { PainelAguarde } from './PainelAguarde'

interface PropriedadesPanelProps extends CasoOps {
  node: Node | null
  nodes: Node[]
  ramos: Record<string, string[]>
  jobNames: string[]
  sqlNodeNames: string[]
  sshConns: { conn_id: string; host: string }[]
  mssqlConns: { conn_id: string; host: string }[]
  grupos: MsgGrupo[]
  readOnly: boolean
  onRename: (oldName: string, novo: string) => boolean
  onPatchData: (nodeId: string, patch: Record<string, unknown>) => void
  onPatchCondition: (nodeId: string, patch: Partial<NodeCondition>) => void
  onPatchNotify: (nodeId: string, patch: Partial<NotifyConfig>) => void
  onPatchSql: (nodeId: string, patch: Partial<SqlConfig>) => void
  onPatchAguarde: (nodeId: string, patch: Partial<AguardeConfig>) => void
  // Quantas etapas chegam no Aguarde selecionado, e quais pontas soltas a ação
  // "prender" ligaria nele. Derivados das arestas pelo editor.
  aguardeEntradas: number
  aguardePontasSoltas: string[]
  onPrenderPontasSoltas: (nodeId: string) => void
  onSimular: (decisaoId: string, ramo: string) => void
  onDelete: (id: string) => void
  // Maximiza o dock (modo focado) — repassado aos painéis com editor de SQL
  // e à etapa python (editor de código embutido).
  onMaximizar?: () => void
  // Hover numa linha de caso → destaca a aresta do ramo no canvas.
  onHoverRamo?: (nodeId: string, ramo: string | null) => void
}

export function PropriedadesPanel({
  node, nodes, ramos, jobNames, sqlNodeNames, sshConns, mssqlConns, grupos,
  readOnly, onRename, onPatchData, onPatchCondition, onPatchNotify, onPatchSql, onSimular, onDelete,
  onPatchAguarde, aguardeEntradas, aguardePontasSoltas, onPrenderPontasSoltas,
  onMaximizar, onHoverRamo,
  onAlternarModo, onAddCaso, onUpdateCaso, onRemoveCaso, onMoveCaso,
}: PropriedadesPanelProps) {
  return (
    // No modo leitura o fieldset desabilita TODOS os campos/botões do painel
    // de uma vez (inclui Excluir/Simular) — o layout não muda. Fase 4: cada
    // painel gerencia a própria largura (layouts em 2 colunas no dock largo).
    <fieldset disabled={readOnly} className="flex min-h-0 w-full flex-1 flex-col">
      {!node ? (
        <PainelVazio />
      ) : node.type === 'decisao' ? (
        <PainelDecisao
          key={node.id}
          node={node}
          nodes={nodes}
          ramos={ramos}
          jobNames={jobNames}
          sqlNodeNames={sqlNodeNames}
          mssqlConns={mssqlConns}
          onRename={onRename}
          onPatchCondition={onPatchCondition}
          onSimular={onSimular}
          onDelete={onDelete}
          onMaximizar={onMaximizar}
          onHoverRamo={onHoverRamo}
          onAlternarModo={onAlternarModo}
          onAddCaso={onAddCaso}
          onUpdateCaso={onUpdateCaso}
          onRemoveCaso={onRemoveCaso}
          onMoveCaso={onMoveCaso}
        />
      ) : node.type === 'notificacao' ? (
        <PainelNotificacao
          key={node.id}
          node={node}
          grupos={grupos}
          onRename={onRename}
          onPatchNotify={onPatchNotify}
          onDelete={onDelete}
        />
      ) : node.type === 'aguarde' ? (
        <PainelAguarde
          key={node.id}
          node={node}
          entradas={aguardeEntradas}
          pontasSoltas={aguardePontasSoltas}
          onRename={onRename}
          onPatchAguarde={onPatchAguarde}
          onPrenderPontasSoltas={onPrenderPontasSoltas}
          onDelete={onDelete}
        />
      ) : node.type === 'sql' ? (
        <PainelSql
          key={node.id}
          node={node}
          mssqlConns={mssqlConns}
          onRename={onRename}
          onPatchSql={onPatchSql}
          onDelete={onDelete}
          onMaximizar={onMaximizar}
        />
      ) : (
        <PainelEtapa
          key={node.id}
          node={node}
          sshConns={sshConns}
          mssqlConns={mssqlConns}
          onRename={onRename}
          onPatchData={onPatchData}
          onDelete={onDelete}
          onMaximizar={onMaximizar}
        />
      )}
    </fieldset>
  )
}

// Estado-guia quando nada está selecionado (usado no branch node=null e
// disponível para o estado vazio do dock).
export function PainelVazio() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-5 py-10 text-center">
      <MousePointerClick size={26} className="text-dim/60" />
      <p className="text-sm font-medium text-ink">Selecione um nó para editar suas propriedades</p>
      <p className="text-xs leading-relaxed text-dim">
        Clique em uma etapa ou decisão no canvas. Para criar um novo nó,
        <strong className="text-ink"> arraste </strong> um tipo da paleta (à esquerda) para o canvas.
      </p>
    </div>
  )
}
