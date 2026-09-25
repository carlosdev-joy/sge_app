// ── Registro central do Admin (docs/spec-admin-reestruturacao.md §3.1) ──────
// Fonte ÚNICA de: sub-menu lateral, busca, cabeçalho da aba, redirecionamento
// dos ids antigos e — na F5 — filtro das chaves órfãs em Parâmetros avançados
// e trava de escrita no backend. Adicionar uma aba = uma entrada em ABAS_ADMIN.
//
// Regra de `chavesConfig` (prefixos de dbo.etl_app_config que a aba POSSUI):
//   • Só declara dono a aba que DE FATO grava a chave pela sua rota própria
//     (ex.: E-mail grava email_* por POST /email/admin/config). Na F5 o editor
//     genérico (config_upsert/config_delete) passa a recusar chave com dono —
//     declarar dono sem tela que edite deixaria a chave inalcançável.
//   • Cada item é um PREFIXO; uma chave inteira (ex.: 'servicenow_url') é o
//     prefixo que casa só com ela — usado quando a família tem chave que a aba
//     não grava (servicenow_admin_perfis é da tela /chamados;
//     agentes_titulo_redigido_em é marca de migration).
//   • Sem dono (ficam em Parâmetros avançados): app_*, dependencia_*, malha_*,
//     espera_*, sql_preview_* e powerbi_* (nenhuma aba edita as credenciais do
//     Power BI) e, até a F3, teams_* (a URL do webhook ainda é editada pelo
//     editor genérico; o "Testar Webhook" só vem para Teams na F3). A busca
//     acha teams_webhook_url pelas palavras-chave da aba Teams, e as órfãs pelas
//     de Parâmetros avançados (palavra-chave terminada em "_" é prefixo).
import { lazy } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'

export type GrupoAdminId = 'acesso' | 'ia' | 'comunicacao' | 'integracoes' | 'pipelines' | 'sistema'

export interface GrupoAdmin {
  id: GrupoAdminId
  rotulo: string
}

export interface AbaAdmin {
  grupo: GrupoAdminId
  /** slug da aba no endereço /admin/<grupo>/<id> */
  id: string
  rotulo: string
  /** uma frase: para que serve a aba (cabeçalho e busca) */
  descricao: string
  /** sinônimos que o admin digitaria */
  palavrasChave: string[]
  /** prefixos de etl_app_config que a aba grava (ver regra no topo) */
  chavesConfig: string[]
  componente: LazyExoticComponent<ComponentType>
  /** ids do Admin antigo (estado local, antes da F2) que apontam para esta aba */
  idsAntigos?: string[]
}

export const GRUPOS_ADMIN: GrupoAdmin[] = [
  { id: 'acesso', rotulo: 'Acesso' },
  { id: 'ia', rotulo: 'Inteligência Artificial' },
  { id: 'comunicacao', rotulo: 'Comunicação' },
  { id: 'integracoes', rotulo: 'Integrações & Dados' },
  { id: 'pipelines', rotulo: 'Pipelines & Ambiente' },
  { id: 'sistema', rotulo: 'Sistema' },
]

// As abas exportam componentes nomeados; o lazy precisa de `default`.
function carregar<T extends Record<string, unknown>>(imp: () => Promise<T>, nome: keyof T) {
  return lazy(() => imp().then((m) => ({ default: m[nome] as ComponentType })))
}

export const ABAS_ADMIN: AbaAdmin[] = [
  // ── Acesso ──────────────────────────────────────────────────────────────
  {
    grupo: 'acesso', id: 'usuarios', rotulo: 'Usuários & Perfis', idsAntigos: ['usuarios'],
    descricao: 'Usuários, perfis com suas permissões e o mapeamento de roles do Airflow para perfis.',
    palavrasChave: ['usuário', 'perfil', 'permissão', 'rbac', 'role', 'acesso', 'senha', 'matrícula', 'login', 'airflow'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/UsuariosTab'), 'UsuariosTab'),
  },
  // ── Inteligência Artificial ─────────────────────────────────────────────
  {
    grupo: 'ia', id: 'provedor', rotulo: 'Provedor', idsAntigos: ['ia'],
    descricao: 'Provedor, modelo e chave de API compartilhados pelo Maestro, pela triagem e pelos agentes.',
    palavrasChave: ['ia', 'llm', 'modelo', 'anthropic', 'claude', 'openai', 'gateway', 'api key', 'chave de api', 'proxy', 'assistente'],
    chavesConfig: ['ia_', 'caixa_ia_'],
    componente: carregar(() => import('../components/admin/abas/IATab'), 'IATab'),
  },
  {
    grupo: 'ia', id: 'maestro', rotulo: 'Maestro', idsAntigos: ['maestro'],
    descricao: 'Liga o Maestro, mantém os cenários de conversa e trata os pedidos que ele registrou.',
    palavrasChave: ['maestro', 'cenário', 'pedido', 'chat', 'assistente', 'conversa'],
    chavesConfig: ['maestro_'],
    componente: carregar(() => import('../components/admin/MaestroTab'), 'MaestroTab'),
  },
  {
    grupo: 'ia', id: 'agentes', rotulo: 'Agentes', idsAntigos: ['agentes'],
    descricao: 'Cadastro dos agentes, prompts, bancos liberados, limites e quem pode usar cada um.',
    palavrasChave: ['agente', 'datastage', 'prompt', 'banco', 'ssh', 'gateway', 'cadastro', 'fato', 'aprendizado'],
    chavesConfig: [
      'agentes_enabled', 'agente_datastage_enabled', 'agentes_gateway_campo_usuario', 'agentes_cadastro_texto',
      'agentes_ssh_max', 'agentes_fato_validade_dias', 'agentes_banco_conexao_s', 'agentes_banco_consulta_s',
    ],
    componente: carregar(() => import('../components/admin/AgentesTab'), 'AgentesTab'),
  },
  // ── Comunicação ─────────────────────────────────────────────────────────
  {
    grupo: 'comunicacao', id: 'teams', rotulo: 'Teams', idsAntigos: ['notificacoes'],
    descricao: 'Canais do Teams (webhooks) e modelos de card usados pelo nó de notificação.',
    // teams_webhook_url: achável pela busca, mas ainda sem dono (ver regra no topo).
    palavrasChave: ['teams', 'webhook', 'card', 'canal', 'notificação', 'mensagem', 'teams_webhook_url', 'teams_'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/NotificacoesTab'), 'NotificacoesTab'),
  },
  {
    grupo: 'comunicacao', id: 'email', rotulo: 'E-mail', idsAntigos: ['email'],
    descricao: 'Remetente, domínios permitidos, anexos e modelos do envio de e-mail, com envio de teste.',
    palavrasChave: ['email', 'e-mail', 'smtp', 'remetente', 'modelo', 'anexo', 'domínio', 'correio'],
    chavesConfig: ['email_'],
    componente: carregar(() => import('../components/admin/EmailTab'), 'EmailTab'),
  },
  {
    grupo: 'comunicacao', id: 'comunicados', rotulo: 'Comunicados', idsAntigos: ['comunicados'],
    descricao: 'Comunicados em markdown enviados aos usuários do Orquestra.',
    palavrasChave: ['comunicado', 'aviso', 'anúncio', 'mensagem', 'markdown'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/ComunicadosTab'), 'ComunicadosTab'),
  },
  // ── Integrações & Dados ─────────────────────────────────────────────────
  {
    grupo: 'integracoes', id: 'conexoes', rotulo: 'Conexões de Dados', idsAntigos: ['conexoes'],
    descricao: 'Conexões SQL Server (mssql) do Orquestra e a migração das que ainda estão no Airflow.',
    palavrasChave: ['conexão', 'banco', 'database', 'sql server', 'mssql', 'conn_id', 'host', 'airflow'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/ConexoesTab'), 'ConexoesTab'),
  },
  {
    grupo: 'integracoes', id: 'servicenow', rotulo: 'ServiceNow', idsAntigos: ['servicenow'],
    descricao: 'Credencial da integração com o ServiceNow, triagem de chamados e sonda de descoberta.',
    palavrasChave: ['servicenow', 'chamado', 'incidente', 'sonda', 'diagnóstico', 'triagem', 'fila', 'grupo'],
    chavesConfig: [
      'servicenow_url', 'servicenow_usuario', 'servicenow_senha_enc', 'servicenow_grupos',
      'servicenow_habilitado', 'servicenow_proxy',
      'chamados_triagem_', // vai para IA › Triagem de chamados na F3
    ],
    componente: carregar(() => import('../components/admin/abas/SondaServiceNowTab'), 'SondaServiceNowTab'),
  },
  {
    grupo: 'integracoes', id: 'servidor-datastage', rotulo: 'Servidor DataStage (SFTP)', idsAntigos: ['utilitarios'],
    descricao: 'Pastas e extensões liberadas no servidor DataStage e os limites da tela Utilitários.',
    palavrasChave: ['sftp', 'ssh', 'utilitários', 'arquivo', 'pasta', 'raiz', 'extensão', 'backup', 'datastage'],
    chavesConfig: ['utilitarios_'],
    componente: carregar(() => import('../components/admin/UtilitariosTab'), 'UtilitariosTab'),
  },
  {
    grupo: 'integracoes', id: 'bancos', rotulo: 'Bancos do servidor', idsAntigos: ['servidor'],
    descricao: 'Bancos do mesmo servidor SQL, listados com a credencial do Orquestra.',
    palavrasChave: ['servidor', 'banco', 'database', 'sql server', 'tamanho'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/ServidorTab'), 'ServidorTab'),
  },
  {
    grupo: 'integracoes', id: 'monitoramento', rotulo: 'Monitoramento de tabelas', idsAntigos: ['monitor'],
    descricao: 'Última atualização e volume diário das tabelas importantes, com alerta de atraso ou queda.',
    palavrasChave: ['monitoramento', 'monitor', 'tabela', 'volume', 'alerta', 'atraso', 'snapshot'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/MonitoramentoTab'), 'MonitoramentoTab'),
  },
  // ── Pipelines & Ambiente ────────────────────────────────────────────────
  {
    grupo: 'pipelines', id: 'publicar-dags', rotulo: 'Publicar DAGs', idsAntigos: ['regen'],
    descricao: 'Recria as DAGs dos pipelines com as regras atuais e dispara a publicação no Airflow.',
    palavrasChave: ['dag', 'publicar', 'regenerar', 'airflow', 'pipeline', 'deploy'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/RegenDagsTab'), 'RegenDagsTab'),
  },
  {
    grupo: 'pipelines', id: 'excluir-pipeline', rotulo: 'Excluir Pipeline', idsAntigos: ['delete'],
    descricao: 'Remove de forma irreversível um pipeline, com seus jobs, execuções e lineage.',
    palavrasChave: ['excluir', 'apagar', 'remover', 'deletar', 'pipeline'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/DeletePipelineTab'), 'DeletePipelineTab'),
  },
  {
    grupo: 'pipelines', id: 'calendarios', rotulo: 'Calendários & Blackout', idsAntigos: ['agenda'],
    descricao: 'Calendários e janelas de blackout usados pelos agendamentos dos pipelines.',
    palavrasChave: ['calendário', 'blackout', 'agendamento', 'feriado', 'dia útil', 'janela', 'agenda'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/AgendamentoTab'), 'AgendamentoTab'),
  },
  {
    grupo: 'pipelines', id: 'projetos', rotulo: 'Projetos', idsAntigos: ['projetos'],
    descricao: 'Projetos disponíveis nas telas de cadastro; inative para ocultar sem excluir.',
    palavrasChave: ['projeto', 'datastage', 'ds_project'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/ProjetosTab'), 'ProjetosTab'),
  },
  {
    grupo: 'pipelines', id: 'tipos-de-job', rotulo: 'Tipos de Job', idsAntigos: ['tipos'],
    descricao: 'Tipos de job aceitos no cadastro, com a regra de lineage de cada um.',
    palavrasChave: ['tipo', 'job', 'ds_job_type', 'lineage'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/TiposJobTab'), 'TiposJobTab'),
  },
  {
    grupo: 'pipelines', id: 'dags-do-sistema', rotulo: 'DAGs do sistema', idsAntigos: ['dags'],
    descricao: 'DAGs de sistema do Airflow por categoria, com o agendamento em vigor.',
    palavrasChave: ['dag', 'inventário', 'airflow', 'sistema', 'agenda'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/DagsInventarioTab'), 'DagsInventarioTab'),
  },
  // ── Sistema ─────────────────────────────────────────────────────────────
  {
    grupo: 'sistema', id: 'parametros', rotulo: 'Parâmetros avançados', idsAntigos: ['config'],
    // Na F5 mostra só as chaves órfãs; aí a descrição vira a copy da spec.
    descricao: 'Chaves de configuração do sistema (etl_app_config) e as configurações de fluxo.',
    palavrasChave: [
      'configuração', 'parâmetro', 'chave', 'config', 'etl_app_config', 'malha', 'dependência', 'espera', 'power bi',
      // prefixos das chaves sem dono (terminados em "_": a chave inteira digitada casa)
      'app_', 'dependencia_', 'malha_', 'espera_', 'sql_preview_', 'powerbi_',
    ],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/ConfigTab'), 'ConfigTab'),
  },
  {
    grupo: 'sistema', id: 'versoes', rotulo: 'Versões', idsAntigos: ['versoes'],
    descricao: 'Versões do Orquestra com as notas de cada entrega, editáveis em markdown.',
    palavrasChave: ['versão', 'release', 'changelog', 'deploy', 'app_version'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/VersoesTab'), 'VersoesTab'),
  },
  {
    grupo: 'sistema', id: 'backlog', rotulo: 'Backlog', idsAntigos: ['backlog'],
    descricao: 'Repositório oficial das pendências e melhorias do produto.',
    palavrasChave: ['backlog', 'pendência', 'melhoria', 'tarefa', 'roadmap', 'bug'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/BacklogTab'), 'BacklogTab'),
  },
  // sai na F4 (vai para /performance)
  {
    grupo: 'sistema', id: 'sla', rotulo: 'Relatório SLA', idsAntigos: ['sla'],
    descricao: 'Percentual de pipelines entregues dentro do SLA no período, com exportação em CSV.',
    palavrasChave: ['sla', 'relatório', 'aderência', 'atraso', 'csv'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/SlaReportTab'), 'SlaReportTab'),
  },
  // sai na F4 (vai para /powerbi)
  {
    grupo: 'sistema', id: 'powerbi-acessos', rotulo: 'Power BI — Acessos', idsAntigos: ['powerbi'],
    descricao: 'Guia de como liberar o acesso aos relatórios do Power BI.',
    palavrasChave: ['power bi', 'powerbi', 'relatório', 'acesso', 'workspace', 'guia'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/PowerBIAccessGuideTab'), 'PowerBIAccessGuideTab'),
  },
  // sai na F4 (duplica a aba "Fluxo (XML)" do /ds-console)
  {
    grupo: 'sistema', id: 'fluxo-ds', rotulo: 'Fluxo DS', idsAntigos: ['fluxo_ds'],
    descricao: 'Lê o fluxo de uma sequence DataStage do XML do projeto, para validar o parser.',
    palavrasChave: ['fluxo', 'datastage', 'xml', 'job', 'stage'],
    chavesConfig: [],
    componente: carregar(() => import('../components/admin/abas/FluxoDsTab'), 'FluxoDsTab'),
  },
]

export const ABA_PADRAO: AbaAdmin = ABAS_ADMIN[0]

export function caminhoDaAba(aba: Pick<AbaAdmin, 'grupo' | 'id'>): string {
  return `/admin/${aba.grupo}/${aba.id}`
}

export function grupoDaAba(aba: Pick<AbaAdmin, 'grupo'>): GrupoAdmin {
  return GRUPOS_ADMIN.find((g) => g.id === aba.grupo)!
}

export function abasDoGrupo(grupo: string): AbaAdmin[] {
  return ABAS_ADMIN.filter((a) => a.grupo === grupo)
}

export function resolverAba(grupo: string | undefined, aba: string | undefined): AbaAdmin | null {
  if (!grupo || !aba) return null
  return ABAS_ADMIN.find((a) => a.grupo === grupo && a.id === aba) ?? null
}

/** id antigo do Admin (antes da F2) → caminho novo. */
export const IDS_ANTIGOS: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(ABAS_ADMIN.flatMap((a) => (a.idsAntigos ?? []).map((id) => [id, caminhoDaAba(a)]))),
)

export type DestinoAdmin =
  | { tipo: 'aba'; aba: AbaAdmin }
  | { tipo: 'redirecionar'; para: string }
  | { tipo: 'inicio' }
  | { tipo: 'nao-encontrada' }

/** Interpreta o splat de /admin/* (ex.: "comunicacao/email", "config", "sistema/config"). */
export function interpretarCaminhoAdmin(splat: string | undefined): DestinoAdmin {
  const partes = (splat ?? '').split('/').filter(Boolean)
  if (partes.length === 0) return { tipo: 'inicio' }
  const [p1, p2, ...resto] = partes
  if (resto.length > 0) return { tipo: 'nao-encontrada' }
  if (p2 === undefined) {
    const doGrupo = abasDoGrupo(p1)
    if (doGrupo.length > 0) return { tipo: 'redirecionar', para: caminhoDaAba(doGrupo[0]) }
    if (Object.hasOwn(IDS_ANTIGOS, p1)) return { tipo: 'redirecionar', para: IDS_ANTIGOS[p1] }
    return { tipo: 'nao-encontrada' }
  }
  const aba = resolverAba(p1, p2)
  if (aba) return { tipo: 'aba', aba }
  // /admin/<qualquer>/<idAntigo> (ex.: /admin/sistema/config) — link antigo com grupo.
  if (Object.hasOwn(IDS_ANTIGOS, p2)) return { tipo: 'redirecionar', para: IDS_ANTIGOS[p2] }
  return { tipo: 'nao-encontrada' }
}

// ── Busca ─────────────────────────────────────────────────────────────────

/** minúsculas e sem acento, preservando o mapa de posições para o destaque. */
function normalizarComMapa(texto: string): { norm: string; mapa: number[] } {
  let norm = ''
  const mapa: number[] = []
  for (let i = 0; i < texto.length; i++) {
    const n = texto[i].normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    for (let k = 0; k < n.length; k++) { norm += n[k]; mapa.push(i) }
  }
  return { norm, mapa }
}

export function normalizar(texto: string): string {
  return normalizarComMapa(texto).norm
}

export type CampoBusca = 'rotulo' | 'grupo' | 'palavraChave' | 'chaveConfig' | 'descricao'

export interface Trecho {
  antes: string
  casou: string
  depois: string
}

export interface ResultadoBusca {
  aba: AbaAdmin
  campo: CampoBusca
  /** o texto do campo que casou, partido para destacar a parte que casou */
  trecho: Trecho
  pontos: number
}

const PESO: Record<CampoBusca, number> = { rotulo: 100, palavraChave: 60, chaveConfig: 55, grupo: 30, descricao: 20 }

function partir(texto: string, termoNorm: string): Trecho | null {
  const { norm, mapa } = normalizarComMapa(texto)
  const i = norm.indexOf(termoNorm)
  if (i < 0) return null
  const ini = mapa[i]
  const fim = mapa[i + termoNorm.length - 1] + 1
  return { antes: texto.slice(0, ini), casou: texto.slice(ini, fim), depois: texto.slice(fim) }
}

interface Casamento { campo: CampoBusca; trecho: Trecho; pontos: number }

// Melhor casamento de UM termo numa aba. Início de palavra vale mais.
function casarTermo(aba: AbaAdmin, termo: string): Casamento | null {
  const candidatos: Casamento[] = []
  const considerar = (campo: CampoBusca, texto: string) => {
    const t = partir(texto, termo)
    if (!t) return
    const inicio = t.antes === '' ? 1.2 : /[\s_\-(/]$/.test(t.antes) ? 1.1 : 1
    candidatos.push({ campo, trecho: t, pontos: PESO[campo] * inicio })
  }
  considerar('rotulo', aba.rotulo)
  considerar('grupo', grupoDaAba(aba).rotulo)
  for (const palavra of aba.palavrasChave) {
    const p = normalizar(palavra)
    if (p.includes(termo)) considerar('palavraChave', palavra)
    // Palavra-chave terminada em "_" é prefixo de chave de config: a chave
    // inteira digitada (powerbi_client_secret) casa com ela (powerbi_).
    else if (p.endsWith('_') && termo.startsWith(p)) {
      candidatos.push({ campo: 'palavraChave', trecho: { antes: '', casou: termo, depois: '' }, pontos: PESO.palavraChave })
    }
  }
  considerar('descricao', aba.descricao)
  for (const prefixo of aba.chavesConfig) {
    const p = normalizar(prefixo)
    if (p.includes(termo)) considerar('chaveConfig', prefixo)
    // Chave inteira digitada (email_remetente) casa com o prefixo dono (email_).
    else if (termo.startsWith(p)) {
      candidatos.push({ campo: 'chaveConfig', trecho: { antes: '', casou: termo, depois: '' }, pontos: PESO.chaveConfig * 1.2 })
    }
  }
  return candidatos.reduce<Casamento | null>((m, c) => (!m || c.pontos > m.pontos ? c : m), null)
}

/**
 * Busca no cliente: todos os termos precisam casar (E); ordena por relevância
 * (rótulo > palavra-chave > chave de config > grupo > descrição) e, no empate,
 * pela ordem do registro. O trecho devolvido é o do termo de maior peso.
 */
export function buscarAbas(consulta: string, abas: AbaAdmin[] = ABAS_ADMIN): ResultadoBusca[] {
  const termos = normalizar(consulta).split(/\s+/).filter(Boolean)
  if (termos.length === 0) return []
  const out: ResultadoBusca[] = []
  for (const aba of abas) {
    const casamentos = termos.map((t) => casarTermo(aba, t))
    if (casamentos.some((c) => c === null)) continue
    const validos = casamentos as Casamento[]
    const d = validos.reduce((m, c) => (c.pontos > m.pontos ? c : m))
    out.push({ aba, campo: d.campo, trecho: d.trecho, pontos: validos.reduce((s, c) => s + c.pontos, 0) })
  }
  const ordem = new Map(abas.map((a, i) => [a, i]))
  return out.sort((a, b) => b.pontos - a.pontos || ordem.get(a.aba)! - ordem.get(b.aba)!)
}

// ── Última aba visitada ────────────────────────────────────────────────────
export const CHAVE_ULTIMA_ABA = 'orquestra-admin-ultima-aba'

export function lerUltimaAba(): string | null {
  try {
    const v = window.localStorage.getItem(CHAVE_ULTIMA_ABA)
    if (!v) return null
    const partes = v.replace(/^\/admin\//, '')
    const d = interpretarCaminhoAdmin(partes)
    return d.tipo === 'aba' ? caminhoDaAba(d.aba) : null
  } catch {
    return null
  }
}

export function gravarUltimaAba(aba: AbaAdmin): void {
  try { window.localStorage.setItem(CHAVE_ULTIMA_ABA, caminhoDaAba(aba)) } catch { /* modo privado/cota: segue sem lembrar */ }
}
