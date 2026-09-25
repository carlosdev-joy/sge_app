// Recursos RBAC (espelha RBAC_RECURSOS da UI legada).
//
// Esta é a lista que o Admin oferece em "Perfis e Permissões" e no modal de
// permissões extras por usuário. Recurso que a migration concede mas que NÃO
// está aqui vira permissão sem interruptor: quem já tem, tem; o admin não
// consegue conceder a mais ninguém nem revogar (foi o caso de `tela_chamados`
// entre as PRs #307 e esta). Toda `perm` do NAV precisa de entrada aqui —
// tests/test_rbac_recursos_admin.py prende as duas listas.
export const RBAC_RECURSOS: [string, string][] = [
  ['tela_dashboard', 'Dashboard'], ['tela_pipelines', 'Pipelines'],
  ['tela_jobs', 'Etapas'], ['tela_logs', 'Logs'],
  ['tela_governanca', 'Catálogo & Lineage'],
  ['tela_malha', 'Malha'], ['tela_admin', 'Admin'],
  ['tela_impacto_campo', 'Impacto de Campo'], ['tela_plano_ajuste', 'Planos de Ajuste'],
  ['tela_powerbi', 'Power BI'],
  ['tela_ds_console', 'Console DataStage'],
  ['tela_utilitarios', 'Utilitários'],
  ['tela_performance', 'Performance'],
  ['tela_copia_dados', 'Cópia de Dados'],
  ['tela_inventario', 'Inventário de Consumidores'],
  ['tela_finalizacao', 'Finalizar Pipeline'],
  ['tela_chamados', 'Chamados'],
  ['tela_caixa_seguro', 'Caixa Seguro'],
  ['caixa_seguro_operacional', 'Caixa Seguro — Operacional'],
  // Agentes de IA (spec docs/spec-agentes-datastage.md). `tela_agentes` é um
  // recurso normal (perfil ∪ overrides), como qualquer `tela_*` acima. Os
  // `agente_*`, ao contrário, são SEMPRE concedidos usuário a usuário —
  // por isso ficam FORA de RBAC_RECURSOS_PERFIS (não aparecem na matriz de
  // perfis; só no modal de permissões extras). Ver risco 26 da spec.
  ['tela_agentes', 'Agentes'],
  ['agente_datastage', 'Agente — Mapeamento DataStage'],
  ['agente_curador', 'Agente — Curador dos aprendizados'],
  ['acao_executar', 'Executar/Rerun/Ack'],
  ['acao_editar', 'Cadastrar/Editar'],
  ['acao_admin', 'Administração'],
]

// Só os recursos que fazem sentido conceder a um PERFIL inteiro — usada na
// matriz "Perfis e Permissões". `agente_*` nunca aparece aqui: conceder
// usuário a usuário é a regra, sem exceção — mesmo que alguém marque
// `agente_datastage` num perfil por engano (pela API, fora desta tela),
// `require_agente` (services/agentes.py) ignora essa origem para não-admin.
export const RBAC_RECURSOS_PERFIS = RBAC_RECURSOS.filter(([rec]) => !rec.startsWith('agente_'))
