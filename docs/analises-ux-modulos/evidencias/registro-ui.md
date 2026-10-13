# Registro de evidências sanitizadas

Rodada: 12/10/2026, America/Sao_Paulo. Ferramenta: conexão de navegador da sessão autorizada pelo usuário (CUA). IDs UI/DB são locais da auditoria; **não são Evidence IDs REA**. Endpoint CDP `127.0.0.1:19222` indisponível; REA CLI retornou `endpoint_unreachable`. Não foram contornadas proteções nem transferidas credenciais.

Os registros conservam tela, ação, resultado e limite. Organização, usuários, assets reais, projetos, IDs de corrida, logs, scripts, parâmetros e valores confidenciais foram omitidos. Não foram salvos dumps de DOM, HAR, cookies, tokens ou cabeçalhos. Não há garantia de reprodutibilidade da sessão autenticada futura.

## Informatica Data Integration

Todas as ações foram leitura/navegação. Nenhum objeto foi criado, salvo, validado, publicado, executado, excluído ou alterado. A revisão visual constatou que a API de screenshot não respeitou o deslocamento do recorte solicitado. Como as imagens ainda exibiam identificação de organização/asset, **todas as capturas Informatica foram retiradas da entrega**. Permanecem registros textuais sanitizados e a proposta de composição; não há imagem artificial apresentada como screenshot.

| ID | Tela / ação | Resultado observado | Limite / registro |
|---|---|---|---|
| UI-001 | Home CDI: ler entradas e recentes | Intenções Ingest/Transform/Orchestrate, recentes e My Jobs | Não exportar inventário ou nomes; registro textual |
| UI-002 | Abrir/fechar seletor do serviço | Produto atual e diálogo de serviços | Apenas CDI foi investigado; licença/acesso dos outros desconhecidos |
| UI-003 | Explore Projects and Folders; Show Filters/Add Filter | Breadcrumb, Find, filtros, sort, seleção e colunas/localização/status | Filtros de checkout/criação/nome/descrição/update inventariados; sem ações sobre rows |
| UI-004 | Explore → Asset Types; seletor Find Asset | Tipos; opção Taskflows; perspectivas Projects/Tags/Metering Tags | Tags apenas inventariadas, não aplicadas |
| UI-005 | Buscar tipo Taskflows e termo demonstrativo; Enter | Busca em nome/descrição e localização de candidato demo | Busca delimitada; não lista toda a organização |
| UI-006 | Abrir taskflow demonstrativo em leitura | Biblioteca/canvas; Start/End; dois Data Tasks e Parallel Paths; Save desabilitado, Publish/Run/Validation visíveis | Não acionar ações; registro textual sem nome de asset |
| UI-007 | Selecionar Data Task 1; aba Error Handling | Seleção muda inspector; abas General/Data Task/Input Fields/Events/Error Handling; grupos aviso/erro | Valores omitidos; não editar; sem prova de runtime/regras internas |
| UI-008 | Zoom In; recolher Properties | Canvas ganha altura; Save continua desabilitado | Registro textual; não prova persistência de preferência |
| UI-009 | Viewport 1440×960, painel recolhido | Pequeno fluxo visível; documento 1440 px | Observação visual/DOM; sem certificação de grafos grandes |
| UI-010 | Viewport 947×800 | Fluxo pequeno visível, largura restante reduzida | Observação visual/DOM, sem screenshot exportado |
| UI-011 | Viewport 390×844 e restaurar | Documento 390 px, mas canvas pouco útil; composição estreita residual após restore | Observação visual/DOM; não reproduzido como defeito persistente |
| UI-012 | My Jobs | No data to display; colunas instance/location/subtasks/start/end/rows/status; Refresh e Updated com PDT | Vazio da consulta pessoal não significa ausência global |
| UI-013 | My Jobs Filter/Add Field | Critérios asset/type/duration/error/location/rows/runtime/times | Somente critérios; sem extração de mensagens/valores |
| UI-014 | Templates | Categorias e pesquisa; criação de mapping/task disponível | Nenhum Create usado |
| UI-015 | New Asset → Orchestration/CDI → Cancel | Tipos descritos; Taskflow na categoria Orchestration | Não criar; categorias adicionais não exploradas |
| UI-016 | Monitor, escopo Data Integration: Running Jobs → View Subtasks | Lista operacional e filhos da instância | Só leitura; sem ações operacionais |
| UI-017 | Monitor/CDI All Jobs → detalhe de instância | Histórico paginado; Current Run com status Suspended, metadados e desenho; Resume/Skip/Stop/Download Log visíveis | Nenhum botão acionado; IDs/logs/valores omitidos; sem tentativa/reparo/transição observados |
| UI-018 | Taskflow → menu adicional | Unpublish, Properties Detail, Run Using, Show Dependencies | Apenas Show Dependencies foi acionado |
| UI-019 | Dependencies → Uses/Used By | Tabelas com direção, tipo, localização/status; Used By vazio do asset | Não equivale a dependência executável de pipeline; nomes/usuários omitidos |
| UI-020 | Abrir Mapping Task demonstrativa / read; expandir Task Schedule/Email Notification | Consulta em seções: detalhes/mapping/avançados/input/conexões/agenda/notificação; Edit visível, Run desabilitado | Edit não usado; valores/configuração confidencial não registrados |
| UI-021 | New Asset → Escape | Diálogo fecha; foco volta ao gatilho New | Um ensaio de foco, não auditoria integral de acessibilidade |

Feedbacks transitórios de carregamento foram confirmados com estado posterior. Falha/deadline de um seletor da automação não foi classificada automaticamente como falha do produto. Não há medição cronometrada de performance.

## Databricks Free Edition

O usuário abriu a sessão e depois autorizou especificamente a **criação** de ORQ_UX_DEMO com duas tarefas fictícias. Não autorizou execução/agendamento; nenhum Run, teste, repair, consulta, conexão externa ou pagamento foi acionado. O job demonstrativo permanece salvo para revisão.

| ID | Tela / ação | Resultado observado | Limite / registro |
|---|---|---|---|
| DB-001 | Home autenticada | Free Edition identificada; navegação de recursos e pesquisa Ctrl+P; aviso de automação não suportada | Navegação normal funcionou, sem alterar detecção/proteções; conta/workspace omitidos |
| DB-002 | Jobs & Pipelines | Lista inicialmente vazia, abas de recursos/runs, filtro nome/ID, filtros tipo e escopo | Vazio deste workspace; não indica inexistência de recursos no produto |
| DB-003 | Create Job autorizado → editar nome/Enter | Job persistido antes da primeira task; nome ORQ_UX_DEMO salvo | Exceção de escrita limitada ao fixture; não equivale a draft/publish Orquestra |
| DB-004 | Tipo task / campos / Save task | Inventário de tipos; duas condições literais, com Save explícito | [Formulário demonstrativo](DB-004-demo-tarefas.jpg); sem avaliar condições em runtime |
| DB-005 | Add task / Depends on / Run if | Segunda task depende de avaliar_condicao(true); All succeeded; aresta de ramo true | Não confundir dependência, condição de elegibilidade e resultado de execução |
| DB-006 | Add trigger → ler tipos/Scheduled → Cancel | Scheduled/File arrival/Table update/Continuous/Model update; Active/Paused, Interval/Schedule; diálogo cancelado sem Save | Nenhum trigger criado; calendário/fuso completos não certificados |
| DB-007 | Job sidebar / Advanced settings em leitura | Job details/parameters/tags/health/notifications/permissions, Queue e Max concurrent runs | Nenhuma permissão/política/default alterados |
| DB-008 | Runs do fixture | Sem job runs no intervalo padrão de 60 dias | Sem histórico gerado, log, retry, repair ou estado real do motor |
| DB-009 | Voltar ao catálogo / filter / Customize columns | ORQ_UX_DEMO reencontrado; opções Name/Type/Tags/ID/Run as/Created by/Tasks/Compute/Trigger/Trigger details/Recent runs | Não alterar checkboxes; persistência de preferências entre sessões desconhecida |
| DB-010 | Reabrir fixture → Tasks | Duas tarefas salvas e contexto do job disponíveis | [Prova sanitizada da criação](DB-010-demo-salva.jpg); nomes são fictícios autorizados |

## Outros registros do pacote

- [Fontes do develop](fontes-dev.md): observação de código com arquivo/linha, sem teste integrado desta rodada.
- [Fontes documentais oficiais](fontes-documentais.md): documentos efetivamente abertos e suplementos que retornaram 403.
- [Manifesto das fontes Orquestra](manifesto-fontes-orquestra.md): integridade, documentos, protótipo e capturas históricas.
- `manifesto-sha256.json`: hashes dos arquivos da entrega; integridade local não autentica resultados de motor.

CTM-006–008 acrescentam os tours oficiais Build a workflow, Error handling e Reference folder. CTM-001–005 preservam a descoberta do acesso. Tours não são execuções reais.



## Evidências adicionais

- DB-011: tentativa real inicial com Failed/RunExecutionError na lista e Skipped no detalhe; causa não determinada.
- DB-012: terceira tarefa notebook/fixture salva e execução Succeeded em17s, saída total30 confirmada, Graph/Timeline/List inspecionados.
- CTM-009: Forecast13/13, calendário/Why/what-if/SLA/caminho crítico guiados.
- CTM-010: Self-Healing16/16, retry/ciclo/escalonamento/alertas/políticas guiados.

Sem transferência de dados corporativos. Prova DB-012 contém apenas fixture/identificadores de demonstração. O agente não executou workflows reais Control-M.
