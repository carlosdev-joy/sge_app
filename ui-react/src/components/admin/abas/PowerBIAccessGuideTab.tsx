import { Badge } from '../../ui/Badge'
import { AlertTriangle } from 'lucide-react'

// ── Power BI — Guia de Acessos ───────────────────────────────────
interface PbiLayer {
  num: string
  titulo: string
  paraQueServe: React.ReactNode
  dependencias: React.ReactNode
  somenteLeitura: React.ReactNode
  escrita?: React.ReactNode
  recomendacao: React.ReactNode
  endpoints: string
  exigePremium: boolean
}

const PBI_LAYERS: PbiLayer[] = [
  {
    num: '1',
    titulo: 'Admin API',
    paraQueServe: (
      <>
        Ver <strong>todo o tenant</strong> (~100+ workspaces) sem depender de alguém convidar
        manualmente o service principal em cada um. Hoje, se um workspace novo é criado e ninguém
        adiciona o SP como membro, o ORQUESTRA simplesmente não o vê. Com a Admin API, o inventário
        passa a ser automático: descobre workspaces/datasets/reports/dataflows/apps novos, identifica
        quem é o dono de cada um e ajuda a achar "órfãos" (sem responsável claro).
      </>
    ),
    dependencias: (
      <>
        <strong>Pré-requisito único, sem custo:</strong> Fase A do runbook abaixo — (1) consentimento de
        admin no Azure AD para a permissão <code>Tenant.Read.All</code> e (2) o toggle "Allow service
        principals to use Power BI APIs" no Admin Portal, com o grupo de segurança do service principal
        adicionado. Não depende de capacidade Premium — funciona em qualquer licenciamento.
      </>
    ),
    somenteLeitura: (
      <>
        Listar tudo (workspaces, datasets, reports, dataflows, apps, capacities), ver detalhes de cada
        item e quem tem acesso a cada dataset/report. <strong>Não</strong> permite mover workspace de
        capacidade, restaurar workspace excluído nem alterar nada.
      </>
    ),
    escrita: (
      <>
        Com <code>Tenant.ReadWrite.All</code> no Azure AD (em vez de <code>Tenant.Read.All</code>),
        endpoints de escrita da Admin API passam a responder: mover workspaces entre capacidades,
        restaurar workspace excluído, rotacionar chave de encriptação. Nenhum desses é necessário para
        o que o ORQUESTRA faz (sustentação/observabilidade).
      </>
    ),
    recomendacao: 'Pedir só leitura (Tenant.Read.All + "read-only admin APIs"). Não há necessidade de escrita.',
    endpoints: 'admin/groups, admin/datasets, admin/reports, admin/dataflows, admin/apps, admin/capacities, admin/datasets/{id}/users, admin/reports/{id}/users',
    exigePremium: false,
  },
  {
    num: '2',
    titulo: 'Activity Events API',
    paraQueServe: (
      <>
        Auditoria de uso real: saber quem abriu, exportou ou compartilhou cada relatório, quando e a
        partir de onde. Serve para detectar uso indevido, levantar relatórios "zumbis" (sem acesso há
        meses — candidatos a descontinuar) e responder rapidamente "quem acessou esse dado sensível".
      </>
    ),
    dependencias: (
      <>
        <strong>Mesmo gate da camada 1 (Fase A)</strong> — usa a mesma permissão{' '}
        <code>Tenant.Read.All</code> e o mesmo toggle de Admin API liberado para service principals.
        Não exige nenhuma configuração adicional além da Fase A já feita.
      </>
    ),
    somenteLeitura: 'É a única forma de uso que existe — um log de auditoria não tem operação de escrita.',
    recomendacao: 'Sempre leitura. Não há decisão a tomar aqui além de habilitar.',
    endpoints: "admin/activityevents?startDateTime=...&endDateTime=...",
    exigePremium: false,
  },
  {
    num: '3',
    titulo: 'Scanner API',
    paraQueServe: (
      <>
        Documentar automaticamente a <strong>lógica de negócio</strong> dentro dos modelos: toda
        fórmula DAX (medidas) e toda transformação M (Power Query) de cada dataset, sem precisar abrir
        o .pbix manualmente. Permite montar um catálogo de "de onde vem cada métrica" e mapear
        dependências entre datasets (lineage) — essencial para análise de impacto de mudança.
      </>
    ),
    dependencias: (
      <>
        <strong>Duas dependências, as duas obrigatórias:</strong> (1) a Fase A já feita — Scanner API é
        um endpoint <code>admin/*</code>, então usa o <em>mesmo gate</em> da camada 1 (sem ele, dá 401
        mesmo com Premium ativo); e (2) o workspace que será escaneado precisa estar atribuído a uma
        capacidade <strong>Premium, PPU ou Fabric</strong> (Capacity Admin verifica/atribui em Workspace
        → Settings → Premium). Ter só uma das duas não é suficiente — as duas precisam estar prontas.
      </>
    ),
    somenteLeitura: 'A Scanner API só lê metadados — não existe modo de escrita; nunca altera o modelo.',
    recomendacao: 'Sempre leitura. A decisão real de "dá pra usar" depende de checar as duas dependências acima, não só da capacidade.',
    endpoints: 'admin/workspaces/getInfo?datasetSchema=true&datasetExpressions=true&lineage=true&datasourceDetails=true (fluxo assíncrono: getInfo → scanStatus/{id} → scanResult/{id})',
    exigePremium: true,
  },
  {
    num: '4',
    titulo: 'XMLA Endpoint',
    paraQueServe: (
      <>
        Conectar ferramentas especializadas (Tabular Editor, DAX Studio, SSMS) direto no modelo do
        Power BI, como se fosse um banco de dados Analysis Services — visão completa de tabelas,
        relacionamentos, medidas, partições e diagnóstico de performance, em tempo real. Não é REST, é
        o protocolo TOM (Tabular Object Model).
      </>
    ),
    somenteLeitura: (
      <>
        Modo <strong>"Read Only"</strong>: consultar dados via DAX, ver metadados completos do modelo,
        diagnosticar performance de medidas (ex.: DAX Studio). Não permite alterar nada no modelo.
      </>
    ),
    escrita: (
      <>
        Modo <strong>"Read/Write"</strong>: tudo do Read Only, mais publicar alterações no modelo
        remotamente (ex.: editar uma medida no Tabular Editor e publicar sem passar pelo Power BI
        Desktop), gerenciar partições e fazer refresh incremental via XMLA.
      </>
    ),
    dependencias: (
      <>
        <strong>Independente da Fase A</strong> — XMLA não usa endpoints <code>admin/*</code>, então não
        precisa do gate de Admin API. Mas tem duas dependências próprias, as duas obrigatórias: (1)
        capacidade <strong>Premium/PPU/Fabric</strong> com o setting "XMLA Endpoint" mudado de "Off" para
        "Read Only" (ou "Read/Write") pelo Capacity Admin; e (2) o service principal precisa ser{' '}
        <strong>Member, Contributor ou Admin</strong> de cada workspace que será acessado — Viewer não
        basta para conectar via XMLA.
      </>
    ),
    recomendacao: 'Pedir "Read Only". O ORQUESTRA é ferramenta de sustentação/observação, não de edição remota de modelos.',
    endpoints: 'powerbi://api.powerbi.com/v1.0/myorg/{workspace}',
    exigePremium: true,
  },
  {
    num: '5',
    titulo: 'Execute Queries REST',
    paraQueServe: (
      <>
        Rodar uma consulta DAX pontual via API para validar se uma medida está calculando certo, sem
        abrir o relatório no navegador. Também permite testar Row-Level Security simulando um usuário
        específico (parâmetro <code>impersonatedUserName</code>) — útil para confirmar que a segurança
        de linha está funcionando como esperado antes de liberar o relatório.
      </>
    ),
    dependencias: (
      <>
        <strong>Independente da Fase A.</strong> Duas dependências próprias, as duas obrigatórias: (1)
        capacidade <strong>Premium/PPU/Fabric</strong> + tenant setting "Dataset Execute Queries REST
        API" habilitado pelo Power Platform/Fabric Administrator; e (2) permissão de{' '}
        <strong>Build</strong> do service principal no dataset específico (mesma exigência da camada 4,
        mas no nível do dataset em vez do workspace).
      </>
    ),
    somenteLeitura: 'Por natureza só avalia/lê expressões DAX — nunca grava dados de volta no dataset. Não existe modo de escrita aqui.',
    recomendacao: 'Seguro habilitar — não há risco de escrita envolvido.',
    endpoints: 'groups/{id}/datasets/{id}/executeQueries',
    exigePremium: true,
  },
]

interface PbiStep {
  responsavel: string
  texto: React.ReactNode
}

interface PbiPhase {
  id: string
  titulo: string
  subtitulo: string
  premium: boolean
  steps: PbiStep[]
}

const PBI_PHASES: PbiPhase[] = [
  {
    id: 'A',
    titulo: 'Fase A — Habilitar Admin API (camadas 1 e 2)',
    subtitulo: 'Sem custo de licença — só permissão.',
    premium: false,
    steps: [
      {
        responsavel: 'Global Admin / Privileged Role Admin do Azure AD',
        texto: (
          <>
            <strong>Azure AD — permissão de aplicação.</strong> No app registration já usado pelo
            ORQUESTRA (mesmo client_id/secret configurado em <code>powerbi_*</code>), ir em{' '}
            <em>API permissions → Add a permission → Power BI Service → Application permissions</em>.
            Selecionar <code>Tenant.Read.All</code> (somente leitura — suficiente para tudo da Fase A/B)
            ou <code>Tenant.ReadWrite.All</code> (só se formos escrever via admin API). Clicar{' '}
            <em>Grant admin consent for [tenant]</em> — só um Global Admin confirma esse consentimento.
          </>
        ),
      },
      {
        responsavel: 'Power Platform Administrator / Fabric Administrator',
        texto: (
          <>
            <strong>Power BI Admin Portal — liberar o service principal.</strong> Acessar{' '}
            app.powerbi.com → engrenagem → <em>Admin portal → Tenant settings → Developer settings</em>.
            Habilitar <em>"Allow service principals to use Power BI APIs"</em> e em "Specific security
            groups" adicionar o grupo do Azure AD que contém o service principal (criar o grupo se não
            existir). Repetir para <em>"Allow service principals to use read-only Power BI Admin APIs"</em>
            {' '}(mesmo grupo). Salvar — propagação pode levar até 15 min.
            <br />
            <span className="text-dim">
              Com isso, <code>/powerbi/status</code> no backend do ORQUESTRA deve reportar{' '}
              <code>admin_api_liberada: true</code>.
            </span>
          </>
        ),
      },
    ],
  },
  {
    id: 'B',
    titulo: 'Fase B — Scanner API / DAX e M (camada 3)',
    subtitulo: 'Exige capacidade Premium, PPU ou Fabric.',
    premium: true,
    steps: [
      {
        responsavel: 'Capacity Admin',
        texto: (
          <>
            Os workspaces que queremos escanear precisam estar atribuídos a uma capacidade{' '}
            <strong>Premium, PPU ou Fabric</strong> (Admin Portal → Capacity settings, ou Workspace →
            Settings → Premium).
          </>
        ),
      },
      {
        responsavel: '— (nenhum toggle adicional)',
        texto: (
          <>
            A Scanner API usa o mesmo gate da Fase A. Uma vez liberada, já é possível chamar{' '}
            <code>admin/workspaces/getInfo</code> com <code>datasetExpressions=true</code>.
          </>
        ),
      },
    ],
  },
  {
    id: 'C',
    titulo: 'Fase C — XMLA Endpoint (camada 4)',
    subtitulo: 'Exige capacidade Premium, PPU ou Fabric.',
    premium: true,
    steps: [
      {
        responsavel: 'Capacity Admin',
        texto: (
          <>
            <strong>Habilitar XMLA na capacidade.</strong> Admin Portal → Capacity settings →
            capacidade em questão → <em>XMLA Endpoint</em> → mudar de "Off" para{' '}
            <strong>"Read Only"</strong> (ou "Read/Write" só se formos editar modelo remotamente —
            não recomendado por ora).
          </>
        ),
      },
      {
        responsavel: 'Dono de cada workspace',
        texto: (
          <>
            <strong>Permissão de Build no workspace.</strong> O service principal precisa ser{' '}
            <em>Member, Contributor ou Admin</em> do workspace (não basta Viewer) para conectar via
            XMLA com ferramentas como Tabular Editor/DAX Studio.
          </>
        ),
      },
    ],
  },
  {
    id: 'D',
    titulo: 'Fase D — Execute Queries REST (camada 5, opcional)',
    subtitulo: 'Exige capacidade Premium, PPU ou Fabric.',
    premium: true,
    steps: [
      {
        responsavel: 'Power Platform / Fabric Administrator',
        texto: (
          <>
            <strong>Tenant setting.</strong> Admin Portal → Tenant settings →{' '}
            <em>"Dataset Execute Queries REST API"</em> → habilitar (pode restringir a grupo de
            segurança também).
          </>
        ),
      },
      {
        responsavel: 'Dono do dataset',
        texto: (
          <>
            <strong>Permissão de Build no dataset.</strong> Mesma exigência de Build da Fase C, mas em
            nível de dataset específico, se quisermos restringir mais.
          </>
        ),
      },
    ],
  },
]

export function PowerBIAccessGuideTab() {
  return (
    <div className="flex flex-col gap-6">
      <div className="bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800 rounded-lg p-4">
        <p className="text-sm text-ink">
          Hoje o ORQUESTRA acessa o Power BI pela <strong>API padrão</strong> — escopo do service
          principal, limitado aos workspaces onde ele é membro. Para ter granularidade tenant-wide e
          ver a lógica interna dos modelos (DAX/M), faltam <strong>4 camadas</strong> de acesso abaixo,
          cada uma com um gate diferente. Esta página serve como referência para a conversa com o time
          de Infra/Segurança/Licenciamento.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {PBI_LAYERS.map((l) => (
          <div key={l.num} className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-bold text-ink">
                <span className="text-dim mr-1.5">#{l.num}</span>{l.titulo}
              </h4>
              {l.exigePremium ? <Badge value="warning">Requer Premium/PPU/Fabric</Badge> : <Badge value="success">Sem custo de licença</Badge>}
            </div>

            <div className="mb-3">
              <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">Para que serve</p>
              <p className="text-sm text-ink leading-relaxed">{l.paraQueServe}</p>
            </div>

            <div className="mb-3 bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800 rounded-md p-3 flex gap-2">
              <AlertTriangle size={16} className="shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wide mb-1">
                  Dependências para funcionar
                </p>
                <p className="text-sm text-ink leading-relaxed">{l.dependencias}</p>
              </div>
            </div>

            <div className={`grid gap-3 mb-3 ${l.escrita ? 'sm:grid-cols-2' : ''}`}>
              <div className="bg-canvas/50 border border-edge rounded-md p-3">
                <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">
                  <Badge value="success">Somente leitura</Badge> — o que conseguimos fazer
                </p>
                <p className="text-sm text-ink leading-relaxed mt-1.5">{l.somenteLeitura}</p>
              </div>
              {l.escrita && (
                <div className="bg-canvas/50 border border-edge rounded-md p-3">
                  <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">
                    <Badge value="warning">Leitura/Escrita</Badge> — o que mais poderá ser feito
                  </p>
                  <p className="text-sm text-ink leading-relaxed mt-1.5">{l.escrita}</p>
                </div>
              )}
            </div>

            <div className="mb-2">
              <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">Recomendação para o chamado</p>
              <p className="text-sm text-ink leading-relaxed">{l.recomendacao}</p>
            </div>

            <p className="text-xs text-dim font-mono mt-2 break-all">{l.endpoints}</p>
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-sm font-bold text-ink mb-1">Passo a passo da solicitação (runbook de acesso)</h3>
        <p className="text-xs text-dim mb-3">
          Recomendação: peça a Fase A primeiro — é grátis, rápida (2 toggles + 1 consentimento) e já
          desbloqueia o inventário tenant-wide e a auditoria de uso real. As Fases B/C/D só valem a
          pena se já existir (ou estiver nos planos) capacidade Premium/PPU/Fabric.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {PBI_PHASES.map((phase) => (
          <div key={phase.id} className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <h4 className="text-sm font-bold text-ink">{phase.titulo}</h4>
              {phase.premium ? <Badge value="warning">Requer Premium/PPU/Fabric</Badge> : <Badge value="success">Sem custo de licença</Badge>}
            </div>
            <p className="text-xs text-dim mb-3">{phase.subtitulo}</p>
            <ol className="flex flex-col gap-3">
              {phase.steps.map((step, i) => (
                <li key={i} className="flex gap-3">
                  <span className="shrink-0 w-6 h-6 rounded-full bg-canvas border border-edge text-xs font-semibold text-dim flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <div className="flex-1">
                    <Badge value="info">{step.responsavel}</Badge>
                    <p className="text-sm text-ink mt-1.5 leading-relaxed">{step.texto}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  )
}
