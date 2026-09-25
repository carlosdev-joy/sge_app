import { useState } from 'react'
import { Tabs } from '../components/ui/Tabs'
import { UtilitariosTab } from '../components/admin/UtilitariosTab'
import { AgentesTab } from '../components/admin/AgentesTab'
import { MaestroTab } from '../components/admin/MaestroTab'
import { EmailTab } from '../components/admin/EmailTab'
import { ConfigTab } from '../components/admin/abas/ConfigTab'
import { RegenDagsTab } from '../components/admin/abas/RegenDagsTab'
import { DeletePipelineTab } from '../components/admin/abas/DeletePipelineTab'
import { VersoesTab } from '../components/admin/abas/VersoesTab'
import { TiposJobTab } from '../components/admin/abas/TiposJobTab'
import { AgendamentoTab } from '../components/admin/abas/AgendamentoTab'
import { UsuariosTab } from '../components/admin/abas/UsuariosTab'
import { ProjetosTab } from '../components/admin/abas/ProjetosTab'
import { SlaReportTab } from '../components/admin/abas/SlaReportTab'
import { PowerBIAccessGuideTab } from '../components/admin/abas/PowerBIAccessGuideTab'
import { ComunicadosTab } from '../components/admin/abas/ComunicadosTab'
import { BacklogTab } from '../components/admin/abas/BacklogTab'
import { ServidorTab } from '../components/admin/abas/ServidorTab'
import { MonitoramentoTab } from '../components/admin/abas/MonitoramentoTab'
import { FluxoDsTab } from '../components/admin/abas/FluxoDsTab'
import { NotificacoesTab } from '../components/admin/abas/NotificacoesTab'
import { ConexoesTab } from '../components/admin/abas/ConexoesTab'
import { DagsInventarioTab } from '../components/admin/abas/DagsInventarioTab'
import { SondaServiceNowTab } from '../components/admin/abas/SondaServiceNowTab'
import { IATab } from '../components/admin/abas/IATab'

// ── Console DataStage ───────────────────────────────────────────────────────
// O console DataStage virou página própria (src/pages/DsConsole.tsx, rota /ds-console).

// Navegação em 2 níveis: grupo (nível 1, sub-abas) → aba (nível 2, pílulas).
const ADMIN_GROUPS = [
  { id: 'sistema', label: 'Sistema', tabs: [
    { id: 'config', label: 'Configurações' },
    { id: 'conexoes', label: 'Conexões de Dados' },
    { id: 'utilitarios', label: 'Utilitários' },
    { id: 'tipos', label: 'Tipos de Job' },
    { id: 'projetos', label: 'Projetos' },
    { id: 'versoes', label: 'Versões' },
    { id: 'backlog', label: 'Backlog' },
    { id: 'servidor', label: 'Servidor' },
    { id: 'dags', label: 'Inventário de DAGs' },
    { id: 'servicenow', label: 'ServiceNow' },
    { id: 'monitor', label: 'Monitoramento' },
    { id: 'fluxo_ds', label: 'Fluxo DS' },
  ] },
  { id: 'pipelines', label: 'Pipelines', tabs: [
    { id: 'regen', label: 'Publicar DAGs' },
    { id: 'delete', label: 'Excluir Pipeline' },
    { id: 'agenda', label: 'Agendamento' },
  ] },
  { id: 'acessos', label: 'Acessos & Comunicação', tabs: [
    { id: 'usuarios', label: 'Usuários & Perfis' },
    { id: 'comunicados', label: 'Comunicados' },
    { id: 'notificacoes', label: 'Notificações' },
    { id: 'powerbi', label: 'Power BI — Acessos' },
    { id: 'ia', label: 'IA' },
    { id: 'maestro', label: 'Maestro' },
    { id: 'agentes', label: 'Agentes' },
    { id: 'email', label: 'E-mail' },
  ] },
  { id: 'relatorios', label: 'Relatórios', tabs: [
    { id: 'sla', label: 'Relatório SLA' },
  ] },
]

// ── Main ────────────────────────────────────────────────────────
export default function Admin() {
  const [tab, setTab] = useState('config')
  const activeGroup = ADMIN_GROUPS.find(g => g.tabs.some(t => t.id === tab)) ?? ADMIN_GROUPS[0]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold text-ink">Administração</h1>
        <p className="text-xs text-dim mt-0.5">Gestão do sistema Orquestra</p>
      </div>

      {/* Nível 1 — grupos */}
      <Tabs
        tabs={ADMIN_GROUPS.map(g => ({ id: g.id, label: g.label }))}
        active={activeGroup.id}
        onChange={gid => { const g = ADMIN_GROUPS.find(x => x.id === gid); if (g) setTab(g.tabs[0].id) }}
        size="md"
      />

      {/* Nível 2 — abas do grupo (pílulas) */}
      {activeGroup.tabs.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {activeGroup.tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                tab === t.id ? 'bg-[#1A5FA8] text-white' : 'bg-edge/40 text-dim hover:text-ink hover:bg-edge/70'
              }`}>
              {t.label}
            </button>
          ))}
        </div>
      )}

      <div>
        {tab === 'config' && <ConfigTab />}
        {tab === 'conexoes' && <ConexoesTab />}
        {tab === 'utilitarios' && <UtilitariosTab />}
        {tab === 'backlog' && <BacklogTab />}
        {tab === 'servidor' && <ServidorTab />}
        {tab === 'dags' && <DagsInventarioTab />}
        {tab === 'servicenow' && <SondaServiceNowTab />}
        {tab === 'monitor' && <MonitoramentoTab />}
        {tab === 'fluxo_ds' && <FluxoDsTab />}
        {tab === 'regen' && <RegenDagsTab />}
        {tab === 'delete' && <DeletePipelineTab />}
        {tab === 'versoes' && <VersoesTab />}
        {tab === 'tipos' && <TiposJobTab />}
        {tab === 'agenda' && <AgendamentoTab />}
        {tab === 'usuarios' && <UsuariosTab />}
        {tab === 'comunicados' && <ComunicadosTab />}
        {tab === 'notificacoes' && <NotificacoesTab />}
        {tab === 'projetos' && <ProjetosTab />}
        {tab === 'sla' && <SlaReportTab />}
        {tab === 'powerbi' && <PowerBIAccessGuideTab />}
        {tab === 'ia' && <IATab />}
        {tab === 'maestro' && <MaestroTab />}
        {tab === 'agentes' && <AgentesTab />}
        {tab === 'email' && <EmailTab />}
      </div>
    </div>
  )
}
