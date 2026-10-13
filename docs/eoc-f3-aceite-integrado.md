# EOC-F3 — Aceite integrado e preservação do Pipeline

Data: 2026-10-13 · Subfase **EOC-F3a** (documental: roteiro, matrizes e próximo lote), atualizada pela **EOC-F3b** (L2 e correções A1–A5, candidato 2.22.1, seção 10) e pela **EOC-F3c** (L3, corretivo R1/R2 da leitura da agenda, D1, corretivo M1/M2 do QA final pós-D1 e gate final pós-M1/M2, seção 11) · SPEC: [experiência e operação consolidada](spec-experiencia-operacao-consolidada.md) §EOC-F3 · Inventário: [EOC-F0](eoc-inventario-e-rastreabilidade.md) · Paridade: [matriz Pipeline](matriz-paridade-pipeline.md).

## 1. Base, escopo e regra de evidência

| Item | Valor |
|---|---|
| Base | `develop` `56484d774902a502f31e064ce9dbfefafe28a0ac` (merge da PR #506, EOC-F2), publicada no DEV como 2.22.0, migration 170 |
| Branch | `feat/eoc-f3-aceite-integrado` |
| F3a (esta seção até a 9) | Só documentação: nenhum código de aplicação, migration, teste novo, suíte, smoke, publicação ou envio. |
| Candidato atual (seções 10 e 11) | **Há correção de aplicação**: API (`validate_projection`, A1–A5), UI (leitura da agenda, R1/R2) com `dist/` reconstruída, testes novos e migration 171. Commit único e PR para `develop` depois do gate estático final pós-M1/M2 (seção 11); sem merge, publicação, migration aplicada ou deploy. |
| Fase | Nenhuma subfase fecha a EOC-F3; L1, L4 e os limites externos continuam abertos (seção 9). |

Na F3a **nenhum teste foi executado** (as rodadas da F3b e da F3c estão nas seções 10 e 11). Todo "PASS" abaixo cita a rodada original e o SHA dela. Testes que existem no repositório na base, mas sem rodada registrada que os ligue a esta jornada, aparecem como **existente**, não como aprovado.

Legenda de estado:

- **Provado-N**: smoke nativo no DEV com fixture própria, SHA e artefato.
- **Provado-S**: navegador real com APIs sintéticas, ou bancada/pytest/.NET em rodada registrada com SHA.
- **Existente**: teste presente na base que cobre o risco, sem prova integrada da jornada.
- **Lacuna**: risco sem teste. Pede teste novo (seção 6).
- **Externo**: depende de ambiente ou pessoas fora do DEV. Não fecha por mock.

Fontes das evidências citadas (fora do Git, só leitura nesta rodada):

| Sigla | Artefato | SHA / versão | Resultado registrado |
|---|---|---|---|
| N-F1 | `/root/orquestra-eoc-evidencias/f1/native-read.json` | `f05bd4e9`, DEV 2.21.2 | Fixture própria `workspace__22bf36c2…`: tentativas do motor `[2,1]`, logs 1 e 2 com HTTP 200 e marcador, 4 ligações do snapshot, número operacional separado, seleção e foco por teclado. Só leitura; nenhuma execução nova. |
| N-F2 | `/root/orquestra-eoc-evidencias/f2/native-catalogo-r3.json` | `56484d77`, DEV 2.22.0 | Rascunho criado pela UI nativa, sem cadastro publicado nem DAG, retomado com a mesma identidade. Leitor só com `tela_pipelines`: `editing` 200; rascunho e posse 403. Fixture e perfil removidos. |
| H-F2 | `f2/health-dev.json` | `56484d77` | 19 verificações PASS (saúde, versão pública, assets servidos iguais ao commit) |
| SQL-F2 | `f2/root-final-sha-gate.json` | head `4c53b7e8`, árvore .NET `f20a7da8…` | Três `[SqlFact]` do índice, 3 rodadas, 9/9 PASS |
| UI-F2 | `f2/root-ui-review-final.md`, `f2/final-browser/` | build `d2e2d054…` | Harness 41/42. A falha é a expectativa de uma 2ª requisição dentro do `staleTime`, refutada por `reader-cache-functional.json` PASS. |
| B-218 | `browser-preservation.json` (evidências do Codex em `/root/orquestra-ux-evidencias/`) | PR #499, `8a57ac6a`, 2.18.0 | 8 agendas com os 11 tipos, campos desconhecidos e referências protegidas preservados (payload sintético). Registro em [matriz §2.18.0](matriz-paridade-pipeline.md#cobertura-final-e-limites-do-candidato-2180). Não reconferido nesta rodada. |
| B-220 | Navegador F4.2 | PR #501, `52843c6e`, 2.20.0 | 11 tipos inline, aplicação e salvamento, desconhecidos e referências preservados. Registro em [matriz F4.2](matriz-paridade-pipeline.md#candidato-f42--2200-11102026). |
| K-F5 | `browser_keyboard.py` do root (23 verificações) | candidato F5 2.21.0 | Enter só na etapa, foco mantido, `reduce` com 1 passo. Esc com foco na etapa leva o foco ao documento (preexistente, pendente). |
| F9 | `/root/orquestra-f9-restore-evidencias/` | DEV 2.17.1 | Recuperação e restore nativos, cinco publicações próprias ([homologação F9](workspace-homologacao-f9.md)) |
| SUITE | Release note 2.22.0, linha "pytest tests" | candidato `4c53b7e8` | 7532 PASS, 8 falhas preexistentes, 51 skip; histórico da base. A suíte final do candidato (pós-M1/M2) está na seção 11 |
| P-221 | `/root/orquestra-ux-pausa-evidencias/registro-dev-pausa.md` → `/root/orquestra-ux-execucao-evidencias/native-pause-run-read.json` | PR #503, `develop` `92d14d59`, DEV 2.21.1 | `passed: true`. Corrida própria `workspace__dd75720a-3679-4a17-bd09-18e34d8a3490` (fixture `__workspace_ux_f5_c1038ef910`), snapshot com 4 ligações. A 2ª corrida entrou no gate da ConsultaParalela e foi **liberada** pelo modal (200, estado LIBERADA) → SUCCESS, logs e histórico PASS. **Não prova cancelamento** da pausa. Só leitura. |
| PAR-221 | `/root/orquestra-ux-execucao-evidencias/native-parallel-real.json` (citado no mesmo registro) | DEV 2.21.1 | Paralelismo real numa corrida **sem** pausa (overlap de 30,43 s entre ConsultaParalela e ShellParalelo pelas taskInstances do Airflow). Fonte separada da pausa. Não reaberto nesta rodada. |

## 2. Jornada salvar → validar → publicar → executar → investigar

A identidade que precisa atravessar a jornada é: `draftId` + sessão/`fence` + `revision`, depois `operationId` + versão/hash publicado, depois `run_id` (`workspace__<uuid>`) + snapshot da versão, depois task + `try_number` do motor.

| Passo | Invariante (SPEC §EOC-F3) | Fonte | Prova existente | Estado | Lacuna |
|---|---|---|---|---|---|
| Criar/retomar | Mesma identidade de rascunho entre lista, Montagem e Configuração | `PipelineCreate`, `PipelineCatalog`, `SqlDraftRepository` | N-F2 (criar → reencontrar → retomar); `tests/test_workspace_ux_contexto.py:29` (uma posse, `fence` 41 em quatro trocas de aba) | Provado-N | — |
| Salvar | `PUT /workspace/drafts/{id}` com `expectedRevision` e `fence`; concorrente 409; falha conserva trabalho local | `DraftEndpoints.cs`, `SqlDraftRepository.cs`, `WorkspaceEditor` | `DraftSqlTests.cs:17` (ciclo durável, cercado e auditado); `DraftEndpointTests.cs:21,42,53`; smoke 2.18.0 com duas sessões e 409 (matriz §2.18.0) | Provado-S / Provado-N (2.18.0) | Save que falha (409/503) **preserva o formulário local**: só bancada; sem prova nativa na base atual |
| Validar | Validação da revisão salva; diagnóstico abre etapa/campo; desconhecido não some em silêncio | `workspace_publication.validate_projection`, `WorkspacePublicationPanel` | `tests/test_workspace_publication_f4.py` (agendas válidas e inválidas, `test_no_silent_loss_or_unresolvable_secret`); `tests/test_workspace_ux_inspector.py:82,103` | Existente | Projeção positiva: 11/11 tipos no candidato F3b (seções 4 e 10) |
| Publicar | 202 é intenção aceita; só "publicada" após confirmação por artefato/hash; versão imutável | `PublicationEndpoints.cs`, `services/workspace_publication.py` | `PublicationSqlTests.cs:13` (cerca da intenção, versão imutável, gate de runtime, corrida reaberta, SQL real); F9 (cinco publicações nativas) | Provado-S; Provado-N em 2.17.1 | Nenhuma publicação nativa desde 2.18.0 encadeada à mesma sessão de rascunho |
| Executar | Run UUID devolvido; execução usa a versão publicada, nunca o rascunho; Solicitado ≠ Em fila ≠ Executando | `POST /workspace/runs`, `WorkspaceRunRequest`, `OperationEndpoints.cs` | `tests/test_workspace_operations_f5.py:40,47,55,82,92`; `OperationEndpointTests.cs:42,48`; `test_workspace_ux_execucao.py:98` | Provado-S | Run nativo pedido pelo workspace e ligado ao hash publicado, na base atual |
| Investigar | Histórico distinto do rascunho; tentativas e logs 1/2 da corrida exata; troca de contexto e aba oculta não cruzam dados | `WorkspaceRunInspector`, `GET /pipeline-task-attempts`, `/pipeline-task-log`, `responseMatchesRequest` | N-F1; `tests/test_tentativas_motor.py:94,137,166,195`; `test_workspace_ux_execucao.py:76,88`; `test_workspace_ux_contexto.py:40` | Provado-N (só leitura, corrida própria já encerrada) | O run investigado em N-F1 não nasceu de uma publicação do mesmo percurso |

**Conclusão honesta:** cada segmento tem prova, mas em fixtures, SHAs e rodadas diferentes. **Nenhuma prova encadeia os cinco passos com a mesma identidade.** Esse é o critério central da F3 ainda aberto (seção 6, item L1).

## 3. Invariantes transversais

| Invariante | Fonte | Prova existente | Estado | Observação / lacuna |
|---|---|---|---|---|
| Aliases (`fluxo`, `etapas`, `ferramentas`, `execucoes`, `logs`, `parametros`, `/jobs?pipeline=`, `/fluxos?pipeline=`) | `App.tsx`, `workspaceNavigation` | `test_workspace_ux_contexto.py:36` (6 aliases, query e hash); `test_workspace_f3.py:20,28` (alias de execução: RBAC antes da leitura; barra, `%`, Unicode e data); `test_workspace_operations_f5.py:40,103` | Provado-S | Sem prova nativa de link antigo com `run_id`/`tentativa` na base 2.22.0 |
| Campos protegidos | `WorkspaceSecretParameter`, `services/workspace_secrets`, `DraftValidation` | `test_workspace_secrets.py:37,45,79,84,98`; `DraftValidationTests.cs:15`; `test_workspace_ux_inspector.py:56,60,107` (nunca entram no histórico local); `test_workspace_catalog.py:4`; `test_workspace_publication_f4.py:30–34` (referência materializada pela localização exata); B-218, B-220 | Provado-S | Sem prova nativa de publicação com referência protegida na base atual |
| Campos desconhecidos | `workspace_f3_harness`, `NodeProperties`, `validate_projection` | `test_workspace_f3.py:11`; `test_workspace_job_fields.py:5`; `DraftValidationTests.cs:34`; B-218 | Provado-S | Regra real: o rascunho **preserva** o desconhecido, mas a publicação **recusa** configuração desconhecida (`test_no_silent_loss_or_unresolvable_secret`, `unknown_config` e `unknown_table`). O roteiro deve tratar isso como "não perde em silêncio", não como "publica". |
| Sessão / `fence` | `SqlDraftRepository`, `WorkspaceEditor` | `DraftSqlTests.cs:17`; `test_workspace_ux_contexto.py:29`; `test_workspace_ux_inspector.py:111` (sem posse não aplica nem desfaz) | Provado-S; Provado-N (2.18.0, 2.20.0) | Transferência de posse com save tardio da sessão anterior: sem prova nativa recente |
| Revisão | `expectedRevision` | `DraftSqlTests.cs:17`; bancada UX (revisão 7 → 8) | Provado-S | — |
| Versão | `etl_workspace_versao`, `WorkspaceVersions` | `PublicationSqlTests.cs:13`; F9 (restore cria rascunho novo) | Provado-S / Provado-N (2.17.1) | Ligar versão publicada → `run_id` → cabeçalho da Execução (L1) |
| Corrida | `responseMatchesRequest`, `operationScope` | `test_workspace_ux_execucao.py:45,88`; `test_tentativas_motor.py:137`; N-F1 | Provado-S / Provado-N (leitura) | — |
| Teclado | `lib/workspaceCanvasA11y`, `WorkspaceCanvas` | `test_workspace_ux_execucao.py:56`; `test_workspace_ux_inspector.py:73,77`; K-F5; N-F1 (`keyboardSelectionAndFocus`) | Provado-S / Provado-N (seleção) | Esc com foco na etapa vai ao documento (pendência preexistente da F5) |
| Pausa | `ModalPausaEtapa`, `routers/execucoes` (corrida exata) | `test_pausa_corrida_exata.py:111–565` (identidade exata, recusas antes do Airflow); `test_pausa_etapa_f5.py:277,287` (cancelar falha o DagRun; liberar não toca o Airflow); P-221 (entrar no gate e liberar pelo modal → SUCCESS) | Provado-S; pausa e liberação Provado-N (2.21.1) | **Divergência documental resolvida para pausa e liberação:** o root localizou P-221, que sustenta o "smoke próprio posterior aprovado" da SPEC (§1) e do inventário F0 (§4). O "em andamento" da [matriz](matriz-paridade-pipeline.md#candidato-f5--2210-11102026) (correção 2.21.1) fica como histórico anterior ao registro. Paralelismo é fonte separada (PAR-221). **Continuam pendentes:** cancelamento nativo da pausa e pausa encadeada à corrida de L1 (L4). |
| Retries | `GET /pipeline-task-attempts` | `test_tentativas_motor.py:94,156,166,179`; N-F1 (tentativas 2 e 1, logs corretos) | Provado-N | Retry com falha **nova** dentro do percurso (L1) não foi exercitado; N-F1 lê uma corrida já encerrada |
| Nós customizados × alertas | `dag_factory` E-mail/Notificação | `test_dag_factory_email.py`, `test_dag_factory_notificacao.py` | Existente | Política de alertas principais é F7–F13; a F3 só preserva a configuração do nó (seção 4) |

## 4. Matriz dos 11 tipos (orientada por risco)

Cada tipo tem três camadas independentes: **F** formulário/rascunho (preservação no editor), **P** projeção/validação na publicação (`validate_projection`), **M** factory/motor (DAG gerada). Não é um produto com as agendas.

| Tipo | Risco principal | F (rascunho) | P (projeção positiva) | M (factory) | Lacuna prioritária |
|---|---|---|---|---|---|
| DataStage | Grafia case-sensitive do job; parâmetros e lineage | B-218, B-220; `test_workspace_job_fields.py:5` | `test_workspace_publication_f4.py:37` | `test_dag_factory_datastage.py` | Execução real é **Externo** (Caixa). A4 (vínculo) corrigido no candidato 2.22.1 |
| SQL | Política nulo; conexão errada; SQL destrutivo | B-220; `workspace_job_fields` | `:37`; diagnóstico por nó (`test_wrong_connection_cycle_and_bad_sql_have_node_diagnostics`) | `test_dag_factory_sql_node.py` | — |
| Python | Arquivo/módulo/inline; vínculos | B-220 | F3b: `test_eoc_f3_paridade_tipos.py` (arquivo, código com vínculo, módulo) | `test_dag_factory_python.py` | A1 e A2 corrigidos no candidato 2.22.1 |
| Shell | Comando e SSH | B-220 | `:37` | `test_dag_factory_shell.py` | A5 (vínculo que sobrou, também nos demais tipos sem vínculo) corrigido no candidato 2.22.1 |
| Stored Proc | Parâmetros nome/tipo/valor | B-220 | `:37` | `test_storedproc_operator.py`, `test_storedproc_params.py` | — |
| HTTP | Não inventar métodos/auth | B-220 | `:37` | `test_dag_factory_http.py` | — |
| Decisão | Ramos, Switch, saída padrão | `test_workspace_specialized.py:5` (grafo de decisão atômico) | F3b (binária e switch) | `test_dag_factory_decisao.py` | — |
| Aguarde | Liberação sem ciclo | B-220 | F3b (com e sem config, uma entrada) | `test_dag_factory_aguarde.py` | A3 corrigido no candidato 2.22.1 |
| Valida Arquivo | Tabelas filhas `etl_valida_arquivo_*` | `test_workspace_specialized.py:5` | F3b (tabelas filhas por entrada; mutação M1) | `test_valida_arquivo_*.py` | — |
| Notificação | Best-effort legado; não suprimir alerta | B-220 | F3b | `test_dag_factory_notificacao.py` | Obrigação é F13 |
| E-mail | Destinatários e domínios do Admin; obrigatório falha a task | B-220 | F3b (corpo livre, modelo, `exigir modelo` com nó novo e existente) | `test_dag_factory_email.py` | — |

## 5. Matriz das 8 agendas (orientada por risco)

Fonte dos modos: `ui-react/src/components/pipelines/pipelineUtils.ts:3`. Sete modos são persistidos (os oito da UI menos `hourly_n`). `hourly_n` é açúcar de UI: é gravado como `custom` com a lista de horários, tanto no legado (`PipelineFormModal.tsx:449`) quanto no workspace (`WorkspacePipelineFields.tsx:27`). Ao reabrir, os dois mostram "Horários específicos" (`PipelineFormModal.tsx:118`, `WorkspacePipelineFields.tsx:19`). É paridade, não regressão.

| Modo | Risco principal | Projeção (válido/inválido) | Factory / cron | Rascunho (UI) | Lacuna |
|---|---|---|---|---|---|
| `daily` | Hora | `test_workspace_publication_f4.py:132` | `test_pipeline_sob_demanda.py:113,132` | B-218 | L3 provado (seção 11): 09:30, 00:00, 23:59 |
| `weekly` | `schedule_dow` 0–6, `None`, booleano | válido e inválido (`True`) | `etl_dag_factory.py:239`; L3 | B-218 | L3 provado: domingo (0) e sábado (6) |
| `monthly` | `schedule_dom` 1–28 | válido e inválido (0) | idem | B-218 | L3 provado: 1 e 28 |
| `biweekly` | `schedule_dom` 1–13 | válido (13) e inválido (14) | idem | B-218 | L3 provado: 13 (cron `13,28`) |
| `hourly_n` | Janela de N horas virar lista diferente da do legado | Bancada UX e L3 | via `custom` | B-218 | L3 provado: 6 janelas com a mesma lista; janela invertida recusada |
| `custom` | Normalização de horários e dias | válido e inválidos (`99:00`, vazio) | `test_dag_factory_monthly_days_times.py:77` | B-218 | L3 provado (cron e agenda efetiva; texto bruto pode diferir) |
| `monthly_days_times` | Até 5 dias 1–28 | válido e inválidos (29, `[]`, objeto) | `test_dag_factory_monthly_days_times.py:58–103`; `test_pipelines_dias_horarios_mes.py` | B-218 | L3 provado |
| `on_demand` | Não pode virar cron 06:00 | padrão de `flow()` | `test_pipeline_sob_demanda.py:75–145` | B-218 | L3 provado: cron `None`, inclusive com resto de agenda |

Todas as provas L3 são offline (Provado-S). Linha existente com tipo NULL ou com horários em tipo não `custom` abria no workspace num tipo diferente do que o motor executa (R1/R2); corrigido no candidato (seção 11).

Transversal às agendas: `somente_dias_uteis` e `calendario_nome` (catálogo real) e virada ODATE/`dag_start_date` só têm prova de inventário na bancada UX. Calendário avançado, fuso e DST são EOC-F17, fora desta fase.

O que falta não é mais uma combinação, é **uma igualdade**: o mesmo cadastro, entrando pelo formulário legado ou pela projeção do workspace, precisa gerar o mesmo cron e as mesmas constantes na DAG (L3).

## 6. Próximo lote mínimo revisável (EOC-F3b)

Lote de **testes** sobre a base `56484d77`. Não muda código de aplicação. Se um teste revelar defeito, a correção vira subfase funcional própria, com migration de versão 171 (base 170 confirmada), conforme o CLAUDE.md.

| # | Entrega | Tipo | Onde | Prova que fecha |
|---|---|---|---|---|
| L1 | **Percurso nativo único** com fixture própria SQL/Shell: criar → salvar (revisão n → n+1, mesmo `fence`) → 409 numa 2ª sessão → save falho conserva o formulário → validar → publicar (202, aguardar confirmação por hash) → executar pelo workspace (`run_id` UUID) → a corrida mostra a versão/hash publicados, não o rascunho → falha controlada na 1ª tentativa e sucesso na 2ª → tentativas e logs 1/2 → link antigo `logs?…&tentativa=` reabre a mesma tentativa → limpeza. **Desconhecido:** um campo desconhecido posto só na própria fixture é retido no rascunho após salvar e reabrir; a publicação é bloqueada com diagnóstico que aponta etapa/campo, sem perder o campo nem o restante do formulário; só então o campo é retirado, **apenas na própria fixture**, e o percurso segue para publicar. **Protegido:** fora do nativo, por teste direcionado offline, ou no nativo só com referência protegida própria e autorizada, sem copiar nem registrar segredo; mock não conta como prova externa | Smoke nativo do root (Claude não acessa DEV); teste offline para o protegido | Novo script em `/root/orquestra-eoc-evidencias/f3/` | Um JSON com uma identidade por passo e o encadeamento conferido; caso desconhecido com bloqueio e retenção registrados; caso protegido identificado (offline ou referência própria) |
| L2 | Projeção positiva dos 6 tipos sem caso: Python, Decisão, Aguarde, Valida Arquivo, Notificação e E-mail (nó). Payload legado válido de cada um → `validate_projection` sem erro, linha projetada igual ao `legacyJob`, definição de entrada intacta | pytest | Ampliar `tests/test_workspace_publication_f4.py:37` ou criar `tests/test_eoc_f3_paridade_tipos.py` | 11/11 tipos com P positivo; mutação dirigida (remover um campo da projeção) derrubada |
| L3 | Igualdade legado × workspace para as 8 agendas: payload do `PipelineFormModal` e projeção do workspace → mesmo `_build_cron`/constantes na DAG; `hourly_n` com a mesma janela → mesma lista | pytest (+ bancada para `hourlyTimes`) | `tests/test_eoc_f3_paridade_agendas.py` | 8/8 modos; mutação dirigida em um modo derrubada |
| L4 | Cancelamento nativo da pausa (cancelar a pausa não cancela job remoto) e pausa encadeada à corrida de L1. Pausa e liberação históricas já têm P-221; não repetir só por causa da documentação antiga | Smoke nativo do root | Mesmo script de L1 | Cancelamento e encadeamento F3 registrados no JSON de L1 |

Fora deste lote: piloto dos três públicos (EOC-F6), alertas/canais (EOC-F7–13), calendário/DST (EOC-F17), polimento visual (EOC-F4/F5) e o Esc preexistente do canvas.

Validação do lote: pytest dos arquivos novos e tocados e, antes da PR, **suíte completa** (`python3 -m pytest tests -q`) comparada com a base `56484d77`, critério zero falha nova, mesmo sem mudança de produção, porque o lote cria ou toca testes (CLAUDE.md, validação antes de toda PR). QA adversarial antes da PR. Nesta F3a nenhum teste foi executado.

## 7. Limites externos (não fecham por mock)

- **Caixa / DataStage / Information Server**: execução real de DataStage só na Caixa. O DEV não substitui (CLAUDE.md, decisão de 27/09).
- **Provider Microsoft / Teams pessoal** (G-MICROSOFT), destinatários de teste e envio real: fora da F3, pendentes.
- **Pilotos com os três públicos**: EOC-F6, donos a confirmar.
- **Backlog canônico** (G-BACKLOG): continua aberto.
- Carga de produção, INP de campo e polling de 5 s: não medidos, 30 s vigente.

## 8. Achados desta leitura

Na leitura da F3a, nenhum defeito de aplicação foi confirmado. As subfases seguintes confirmaram e corrigiram sete (itens 5 a 8). Registros:

1. **Lacuna de teste (L2)**: `validate_projection` valida Python, Decisão, Aguarde, Notificação, E-mail e Valida Arquivo (`api/services/workspace_publication.py:236–254`), mas nenhum teste do workspace exercita a projeção positiva desses tipos. Hoje só os 5 tipos de `test_workspace_publication_f4.py:37–45` são provados.
2. **Lacuna de teste (L3)**: nenhum teste compara o cron/constantes gerados a partir da projeção do workspace com os do formulário legado.
3. **Divergência documental da pausa**: resolvida para pausa e liberação históricas por P-221 (seção 3), localizado pelo root. Textos históricos não alterados. Cancelamento e encadeamento F3 continuam em L4.
4. **Nuance de contrato**: configuração desconhecida é preservada no rascunho e bloqueia a publicação. Não é defeito; o roteiro de aceite deve esperar o bloqueio com diagnóstico.
5. **Defeitos encontrados pela L2 (F3b)**: três divergências entre a projeção do workspace e o save legado, confirmadas pelo root e corrigidas no candidato 2.22.1 (seção 10):
   - A1: vínculo Python inválido publicava e falhava na corrida;
   - A2: Python no modo módulo sem SSH era recusado;
   - A3: Aguarde sem entrada publicava.
   O item 1 acima está resolvido pela L2, e o item 2 pela L3 (seção 11).
6. **Achado do root depois de A1–A3** (`root-repro-datastage-vinculo.json`): vínculo DataStage para parâmetro inexistente publicava, e o `normalizar` legado recusa. Foi corrigido como A4 no mesmo candidato 2.22.1 (seção 10).
7. **Achado do root depois do A4** (`root-repro-vinculo-outros-tipos.json`): Shell com vínculo que sobrou publicava, e o `normalizar` legado recusa ("Vínculos disponíveis somente em DataStage e Python."). Foi corrigido como A5 no mesmo candidato 2.22.1 (seção 10).
8. **Achados da L3** (`repro-f3c-agendas.json`), corrigidos no mesmo candidato (seção 11):
   - R1: linha existente com `schedule_type` NULL abria no workspace como "Sob demanda", mas a DAG publicada roda diário (`0 6 * * *`);
   - R2: linha `daily` com `horarios_especificos` abria como Diário com um horário só, mas o cron segue os horários específicos.
   O3 (`on_demand` com `dias_semana`) é observação sem divergência.
9. **Achados do QA final pós-D1** (revisão estática, reproduzidos pelo Codex sem runtime: `M1.legacyParserRejects: true`, `M2.effectiveAfterPartialUpdateCron: "0 24 * * *"`), corrigidos no mesmo candidato (seção 11):
   - M1: `daily` com `horarios_especificos` alterado de `09:00,14:00` para `09:00,14;00` publicava. O parser do cadastro recusa, e a factory gera só `0 9 * * *`, perdendo as 14h sem aviso. O D1 conferia só a faixa das entradas legíveis.
   - M2: publicada `on_demand` com `24:00`; rascunho passa a `daily` **sem** a chave `horarios_especificos`. A validação via `None` e passava; o `UPDATE` parcial de `sync_rows` mantém `24:00` e a factory gera `0 24 * * *`. Alcance: rascunho montado fora da tela (a tela não remove chaves).
   - B1 (relacionado, corrigido junto): `dias_semana` que o motor usa fora de `custom` só era conferido em `custom`.
   - B2, B3 e B4 ficam registrados como limites, sem alteração (seção 11). B3 foi reclassificado como informativo no gate final.
10. **Gate estático final pós-M1/M2** (`f3-post-m1-m2-qa-inline-20261013T225215Z-review.md`, exit 0): M1, M2 e B1 aprovados, nenhum defeito material. Residuais N1–N5 registrados na seção 11.

## 9. Estado

| Critério SPEC §EOC-F3 | Estado |
|---|---|
| Mesma sessão/fence/revisão/versão/corrida | Por segmento: Provado-S/N. **Encadeado: lacuna (L1)** |
| Falha conserva trabalho | Provado-S; nativo pendente (L1) |
| Campos protegidos/desconhecidos preservados | Provado-S (B-218, B-220, pytest/.NET). Desconhecido nativo pendente (caso próprio em L1: retido no rascunho, publicação bloqueada com diagnóstico). Protegido pendente: L1 só o fecha com teste offline direcionado ou referência própria autorizada; sem esse caso, não fecha |
| Aliases, teclado, pausa e retries | Aliases e teclado Provado-S; retries Provado-N; pausa e liberação Provado-N (P-221, 2.21.1); cancelamento da pausa e encadeamento F3 pendentes (L4) |
| 11 tipos / 8 agendas | F: Provado-S; P: 11/11 tipos no candidato (pytest offline; A1–A5 corrigidos e revisados); agendas: igualdade legado × workspace 8/8 modos e `hourly_n` em 6 janelas (L3, Provado-S offline); leitura da agenda no workspace alinhada ao motor (R1/R2, revisado); M: existente |
| Leitura visual do corretivo | Rodada 1 de navegador (readonly, APIs sintéticas): 4/4 casos PASS. Não prova salvar/editar/publicar nem backend nativo (seção 11) |
| Limites externos declarados | Seção 7 |

EOC-F3: **não fechada**. EOC-F3a: documento candidato com os quatro ajustes da revisão independente do Codex aplicados. EOC-F3b: L2 e correções A1–A5 revisadas pelo Codex (seção 10). EOC-F3c: L3 (8 modos, 6 janelas) e corretivo R1/R2 revisados pelo Codex (seção 11). Suíte completa do root sem falha nova (seção 11). D1: suíte pós-D1 do Codex 7745 PASS / 8 falhas preexistentes / 51 skip (histórico). Corretivo M1/M2 (seção 11): 262 testes focados PASS; suíte final 7795 PASS / 8 falhas preexistentes / 51 skip, **zero falha nova** (as 8 conferidas pelo root como as mesmas da baseline); gate estático final aprovado, sem defeito material. Isso **não** é suíte toda verde: as 8 falhas preexistentes continuam. Mutação dirigida do M1/M2 não foi feita. Faltam L1, L4 (helper nativo próprio do Codex, ainda não executado), backup, merge, deploy, aplicação da migration, health no DEV e os limites externos. Nenhum gate externo aprovado. Aceite global da F3 aberto. Commit e PR desta entrega; sem merge, publicação ou deploy; migration 171 não aplicada.

Pendência de processo: a memória `.claude/memory/` **não foi atualizada**. A escrita foi recusada pelo controle de permissão da sessão Claude ("sensitive file") e não foi contornada; a recusa continua valendo. A proposta está em `/root/orquestra-eoc-evidencias/f3/memoria-proposta.md`, e o resumo e a proposta externos são mantidos pelo Codex.

## 10. EOC-F3b — L2 e correções A1–A5 (candidato 2.22.1)

Base `56484d77`, mesma branch, sem commit. Evidências fora do Git, em `/root/orquestra-eoc-evidencias/f3/`.

| Item | Entrega | Prova | Estado |
|---|---|---|---|
| L2 | `tests/test_eoc_f3_paridade_tipos.py`: projeção positiva dos seis tipos, volta idêntica das linhas e filhas, colunas JSON byte a byte, inválidos com diagnóstico na etapa | 36 testes e mutações M1–M3 (`mutation-f3b-types.json`); revisão independente do Codex sem achado material no teste | Candidato revisado |
| A1 | Vínculo Python conferido por `param_vinculos.normalizar` sobre o catálogo projetado | Casos inexistente, caixa, tipo, origem, campo de destino e não objeto; vazio ignorado; texto byte a byte | Candidato revisado |
| A2 | Modo módulo publica sem SSH; arquivo/código continuam exigindo; conexão informada inválida recusada | Casos módulo sem SSH, módulo com SSH inválida (×2), arquivo/código sem SSH | Candidato revisado |
| A3 | Aguarde exige entrada vinda de etapa do próprio rascunho, com a mensagem do legado | Sem entrada, CSV vazio, só etapa ausente; uma entrada publica | Candidato revisado |
| A4 | Vínculo DataStage conferido por `param_vinculos.normalizar` (tipo `datastage`) sobre o mesmo catálogo projetado | Recusa com a mensagem do legado: inexistente, caixa, exclusivo Orquestra, destino inválido e não objeto. Publicam: vazio (`''`, `{}`, `null`, sem coluna), válido byte a byte, linha sem `param_destino` (DEFAULT `datastage`) e valor direto de mesmo nome, que tem prioridade na corrida | Candidato revisado |
| A5 | Vínculo nos demais nove tipos conferido pelo mesmo helper e `normalizar`, com o tipo **atual** da etapa | Recusa com a mensagem do legado em Shell, SQL, procedure, HTTP, decisão, Aguarde, notificação, e-mail e Valida Arquivo (vínculo válido no DataStage e não objeto). Publicam: vazio (`''`, `{}`, `null`, `[]`, sem coluna) em todos. Troca de tipo: vale o tipo da etapa, não o da linha antiga. Python e DataStage com um único diagnóstico | Candidato revisado (`root-independent-review-f3b-vinculos-outros.md`) |

Prova antes/depois (`mutation-f3b-correction.json`):

- **Antes.** O código de aplicação da base, numa árvore temporária isolada, dá exatamente as 10 falhas de A1–A3.
- **Depois.** Os 57 testes do arquivo passam e os 59 da F4 continuam passando.
- **Mutações.** 10 dirigidas, todas derrubadas.

A reprodução do root (`repro_f3b_types.py`) passa a mostrar as três divergências como resolvidas (`repro-f3b-correction.json`).

Prova do A4 (`mutation-f3b-datastage.json`):

- **Antes.** O estado A1–A3, reconstruído por reversão exata e conferido por sha256, dá só as 5 falhas dos vínculos DataStage inválidos.
- **Depois.** O arquivo passa inteiro (69) e a F4 também (59).
- **Mutações.** 16 dirigidas, todas derrubadas: 10 do DataStage e do catálogo compartilhado, mais 6 de A1–A3 adaptadas ao helper comum.
- **Repro do root.** Inexistente, caixa e exclusivo Orquestra deixam de divergir; o vínculo válido não divergia antes e continua igual.

Prova do A5 (`mutation-f3b-vinculos-outros.json`):

- **Antes.** O estado A4, reconstruído por reversão exata e conferido por sha256, dá só as 19 falhas esperadas: 18 dos vínculos nos nove tipos e a da troca de tipo.
- **Depois.** O arquivo passa inteiro (95) e a F4 também (59).
- **Mutações.** 17 dirigidas, todas derrubadas: 9 do A5 (só DataStage, só formulário compartilhado, sem Shell, regra DataStage nos outros, tipo da linha antiga, limpar o residual em silêncio, Python duplicado, DataStage duplicado, vazio conferido) e 8 de A1–A4.
- **Repro** (`repro_f3b_vinculos_outros.py`). Os cinco casos de Shell, procedure, HTTP e troca DataStage → Shell deixam de divergir; o JSON publicado não muda.

**Suíte completa (estado A1–A3, histórico).** Sem dependências JS, contra a base registrada: nenhuma falha nova (10/51 iguais). Com dependências JS locais (symlink, sem rede): 7590 / 8 / 0 / 51, e as 8 são as preexistentes. A comparação final, com baseline JS, está na seção 11 e substitui esta.

**Limites.**

- Provas offline: não exercitam motor, DEV nem cliente.
- A Montagem não mostra campo de vínculo fora de DataStage e Python. Com o A5, uma etapa desses tipos com vínculo que sobrou fica bloqueada na publicação, sem como limpá-lo pela própria Montagem. Hoje a limpeza passa pelo cadastro legado (o canvas legado envia vínculo vazio nesse caminho, `FluxoEditor.tsx:1858`) e por um rascunho novo. Uma ação de limpeza na Montagem é mudança de UI, fora deste lote.
- O baseline com dependências JS foi feito pelo root depois da L3 (seção 11).

## 11. EOC-F3c — L3 e corretivo R1/R2 (mesmo candidato 2.22.1)

Mesma base e branch, sem commit. Evidências em `/root/orquestra-eoc-evidencias/f3/`.

| Item | Entrega | Prova | Estado |
|---|---|---|---|
| L3 | `tests/test_eoc_f3_paridade_agendas.py` + bancada `tests/js/eoc_f3_agendas_harness.cjs`. Legado (`PipelineFormModal` real → `register` sobre `FakePipeDb`) × workspace (`WorkspaceScheduleFields` montado → `validate_projection`) → mesmo `_build_cron`, linha `schedule=` e constantes da DAG, com o cron esperado pinado | 8/8 modos da tela e 7 persistidos; `hourly_n` em 6 janelas com a mesma lista; janela invertida recusada; limites de faixa, NULL, booleano e `on_demand` sem cron. 48 testes; 12 mutações derrubadas (`mutation-f3c-agendas.json`); root 48 PASS na VPS | Candidato revisado (`root-independent-review-f3c-agendas.md`) |
| R1/R2 | `effectiveScheduleType` (função pura em `ui-react/src/lib/workspace.ts`), usada em `WorkspacePipelineFields.tsx` e no resumo "Agenda" de `PipelineWorkspace.tsx`. Sem tipo → Diário (R1); `daily`/`weekly`/`monthly`/`biweekly` (ou sem tipo) com horário legível → Horários específicos (R2); `on_demand`, `custom` e `monthly_days_times` ficam como estão. Só leitura: não chama `onChange` nem reescreve o rascunho; motor, projeção, fence/revisão e campos desconhecidos/protegidos intactos | 16 testes novos (red 16 falhas na UI do `HEAD` → green 64 no arquivo); 10/10 mutações derrubadas (`mutation-f3c-correcao.json`), revisadas pelo root; repro R1, R1b, R2, O3 sem divergência; root 64 PASS na VPS (`root-f3c-correcao-final-gate.json`) | Candidato revisado (`root-independent-review-f3c-correcao.md`) |
| D1 (QA pré-PR) | `validate_projection` confere a faixa 00–23/00–59 dos horários que o `_build_cron` usa nos tipos `daily`/`weekly`/`monthly`/`biweekly` (ou sem tipo). A leitura é a do motor (`engine_schedule_times`: mesmo `split`/`int()`, entrada ilegível ignorada). Diagnóstico em `horarios_especificos` com a mensagem do legado, antes de escrever em `etl_pipeline`. Só quando `schedule_type` ou `horarios_especificos` muda em relação à linha ativa: agenda antiga não alterada fica como está. `custom`, `on_demand`, `monthly_days_times`, o texto publicado e a leitura não mudam | 53 testes novos (5 tipos × 5 valores fora da faixa com o cron da factory; limites `00:00, 23:59`; misto legível/ilegível; antiga ilegível e antiga fora da faixa sem alteração; 4 alterações; tipos que o motor não usa; anti-drift). Red: 39 falhas, 14 positivos verdes. Green: 117 no arquivo, 212 com o de tipos, 141 nos 5 da publicação. 18/18 mutações derrubadas por script externo, fonte inalterada (`mutation-d1-fix-20261013T214307Z.json`) | Fechado: suíte pós-D1 do Codex (7745 / 8 preexistentes / 51) e QA final feito (achou M1/M2, corrigidos na linha abaixo). Histórico: o "misto legível/ilegível publica" foi refutado pelo QA final (M1) e substituído na linha abaixo |
| M1/M2 (QA final pós-D1) | `validate_projection` confere a agenda **efetiva depois do `sync_rows`**: sobreposição local `{**linha publicada, **linha projetada}` (chave omitida conserva a coluna, `null` explícito limpa, tipo omitido vale o publicado e NULL vale diário). A projeção e o snapshot não mudam; nenhuma chave é restaurada. **M1:** quando o tipo efetivo não é `custom`, `on_demand` nem `monthly_days_times` e `schedule_type`, `horarios_especificos` ou `dias_semana` efetivos diferem da linha publicada, os horários passam pelo `_parse_horarios_especificos` do cadastro só para o diagnóstico (formato e faixa, primeira entrada recusada na ordem do texto, mensagem do legado em `horarios_especificos`); o retorno normalizado é descartado e o texto publica como está. **B1:** na mesma condição, `dias_semana` passa pela regra já usada em `custom` quando o motor o usa (diário sempre; semanal/mensal/quinzenal só com horário legível). **M2:** `custom`, `monthly_days_times` e `schedule_dow`/`schedule_dom` passam a ler os mesmos valores efetivos, sem mudar as regras. Agenda efetiva igual à publicada continua como está, mesmo inválida | Testes novos/ajustados em `test_eoc_f3_paridade_agendas.py`: alteração para ilegível nos 5 tipos (`09:00,14;00`, misto, `9:`, `14h`) com o que a factory usaria; limites `-1:00`/`23:60` e ordem do diagnóstico; formatos aceitos pelo cadastro publicam sem normalizar; legado inválido inalterado (também com chaves omitidas); M2 com troca de tipo e horários/dias herdados, tipo omitido (semanal, `custom`, `on_demand`), `null` explícito; B1 usado × ignorado. O teste do D1 que aceitava alteração ilegível foi corrigido, e o de linha antiga inalterada usa só a linha publicada real. Gate final: 262 focados PASS; suíte 7795 / 8 preexistentes / 51 skip, zero falha nova (`root-m1-m2-suite-compare.json`); gate estático `f3-post-m1-m2-qa-inline-20261013T225215Z-review.md` exit 0 | Suíte e QA estático fechados; mutação dirigida do M1/M2 **não feita**; runtime não provado |
| Front | `tsc -b` exit 0; ESLint diferencial 0 → 0 nos 3 arquivos; `npm run build` exit 0. **`dist/` reconstruída** (vai no commit desta entrega, sem rebuild novo; UI inalterada desde esta prova): `index.html` sha256 `c2e9aaa18a6b10bd0d71e40fba187afe32a6e433a855a439d82d6cc7ef5aca6a`, 178 assets, chunks com hash rotacionado | `front-f3c-correcao.json`; detector impeccable do root `[]` | Candidato revisado |

**Suíte completa do root** (`root-suite-final-compare.json`, `passed: true`), com dependências JS locais nos dois lados:

| Lado | Passed | Failed | Error | Skipped |
|---|---|---|---|---|
| Base `develop` `56484d77` | 7532 | 8 | 0 | 51 |
| Candidato | 7692 | 8 | 0 | 51 |

Nenhuma falha nova, nenhum teste removido ou corrigido; os 160 testes só do candidato passam. As 8 falhas são as preexistentes. Não é gate de PR nem de deploy.

**Suíte pós-D1** (Codex, histórico): 7745 passed / 8 falhas preexistentes / 51 skipped.

**Suíte final pós-M1/M2** (Codex; XML `root-m1-m2-suite-host-20261013T225100Z.xml`, sha256 `824f23f02d5f569fdda761d1464f612fb114e24cabdcdf14f816ba40f580fcc7`; comparação `root-m1-m2-suite-compare.json`): **7795 passed / 8 failed / 51 skipped**. Zero falha nova: o root confirmou que as 8 são exatamente as preexistentes da baseline. Não é suíte toda verde. O delta de 7745 para 7795 (+50) bate com os casos parametrizados novos. Testes focados: 262 PASS.

**Gate estático final** (`f3-post-m1-m2-qa-inline-20261013T225215Z-review.md`, exit 0): M1, M2 e B1 aprovados, nenhum defeito material. O Codex conferiu ainda, sem runtime, que o hash ativo da migration 159 inclui as colunas da agenda e que o endpoint de publicação exige a validação completa do adaptador; isso responde ao contexto que o QA não recebeu, mas não é prova de execução. Residuais, nenhum material: N1 (mensagem confusa com tipo e `scheduled_time` omitidos sobre `on_demand`), N2 (`custom` sem bypass de linha inalterada e campo de diagnóstico diferente), N3 (`kind` sem `.lower().strip()`), N4 (valor não hashable em `schedule_type`/`criticidade`/`ambiente`, anterior a esta correção) e N5 (sem teste anti-drift ligando o efetivo ao `sync_rows` real).

**Pendências reconciliadas.** Fechados: suíte pós-D1, QA final pós-D1 (gerou M1/M2), suíte pós-M1/M2 e QA estático pós-M1/M2. Continuam PENDENTES: mutação dirigida do M1/M2 (não feita, sem PASS), L1 e L4 nativos, backup, merge, deploy, aplicação da migration 171, health no DEV, smokes de edição no DEV e os limites externos. UI e .NET não mudaram desde as últimas provas pinadas; não houve rebuild nem capturas novas.

**Rodada visual 1 de navegador** (`root-browser-f3-round1.json`, `root-visual-review-round1.md`): Chromium real contra a `dist/` pinada acima, APIs sintéticas interceptadas, modo consulta. 4/4 casos PASS (R1 e R2 em 1440 claro e 390 escuro), seis capturas examinadas pelo root, sem erro de console/página, rota desconhecida ou overflow. R1 nulo mostra Diário e 09:45; R2 mostra Horários específicos e `09:15,18:30`; resumo R2 coerente. Uma rodada F3 consumida; resta no máximo uma de confirmação. **Não prova** salvar, editar ou publicar, nem backend nativo; não é auditoria WCAG completa.

**Limites.**

- Provas offline: não exercitam motor, Airflow, DEV nem cliente. O lado legado da L3 roda sobre `FakePipeDb`; o `validateStep` legado não foi executado (a recusa da janela invertida só tem a mensagem pinada).
- `schedule_hour`/`schedule_minute` e o `scheduled_time` de `monthly_days_times` diferem entre os lados; a factory não os usa para o cron, e outros consumidores (preview, malha, SLA) não foram auditados.
- **Quatro divergências preexistentes do legado com o motor**, fora deste corretivo e não ampliadas. O `pipelineToForm` legado abre: `schedule_type=''` como `''`; horários ilegíveis como `custom` (a factory faz diário); `on_demand` com horários como `custom` (a factory não gera cron); `daily` com `dias_horarios_mes` como `monthly_days_times` (a factory faz diário). Ficam em `LEGADO_DIVERGE_DO_MOTOR`, excluídas só da comparação com o legado; o workspace segue o motor.
- **Aproximação ASCII:** a regra de "horário legível" aceita dígitos ASCII, sinal e espaços; o `int()` do Python aceita também `_` e dígitos Unicode, casos degenerados não modelados. Tipo em maiúsculas ou só espaços é exibido cru, e a projeção recusa como antes.
- O resumo da página tem só pino de fonte, sem montagem; a leitura visual dele é a da rodada 1.
- **D1.**
  - A suíte completa e a rodada visual acima são anteriores ao corretivo. O D1 não muda o front nem o `dist/`.
  - Agenda antiga fora da faixa e não alterada continua publicável, como já estava ativa.
  - Não foram executados: o import error do Airflow, o estado final da operação e o smoke de edição no DEV (linha diária com horários editada para `24:00`, esperando diagnóstico).
- **M1/M2.**
  - Executados pelo Codex: 262 focados e a suíte final (acima). Mutação dirigida e smoke continuam pendentes.
  - Casos antigos não alterados: agenda efetiva igual à publicada (inclusive com chaves omitidas) publica mesmo com horário ilegível, fora da faixa ou `dias_semana` inválido; `custom` continua conferindo sempre, sem esse desvio; `on_demand` e `monthly_days_times` continuam ignorando horários e `dias_semana`, como o motor; a regra de `schedule_dow`/`schedule_dom` não mudou, só passou a ler o valor efetivo.
  - A conferência de `scheduled_time` e do tipo suportado continua sobre a linha projetada. Com chave omitida ela já era igual ou mais restritiva que a efetiva; tipo legado fora do conjunto, não alterado, não é reavaliado.
  - Ficam mais permissivos só rascunhos com chave omitida cujo valor publicado é válido (por exemplo, tipo omitido sobre `on_demand` publicado com horários alterados, que o motor ignora). Com todas as chaves presentes, como a tela grava, a agenda efetiva é a projetada.
  - Pipeline sem linha publicada: a sobreposição é a própria linha projetada; o DEFAULT de coluna omitida no `INSERT` não foi auditado.
  - "Alteração" compara `schedule_type`, `horarios_especificos` e `dias_semana` com o valor lido da linha ativa; `scheduled_time` fica fora porque sua representação lida do banco pode diferir do texto do rascunho.
  - **Não alterados, por escopo:** B2 (resumo "Agenda" vazio para tipo NULL, `PipelineWorkspace.tsx`, pinado em teste), B3 (informativo: `python_json` corrompido vira modo módulo e publica sem SSH; o fallback da factory confirma o modo módulo, igual ao NULL gravado pelo register, e sobra só a fidelidade do texto) e B4 (legibilidade ASCII da tela × `int()`, só exibição).
  - **I1:** a nota de versão 2.22.1 registra a recusa de formato/faixa. O texto de Admin › Versões na migration 171, o comentário do harness (`lib/workspace.ts:62`) e o teste de `test_eoc_f3_paridade_tipos.py` que exige a 171 como última migration estão fora dos arquivos autorizados desta entrega e continuam como estão. A próxima fase deve ajustar o teste de sequência antes da migration 172.
- **L1 e L4 pendentes**: dependem de helper nativo próprio do Codex (preflight em `root-native-l1-l4-preflight.md`), ainda não executado. O QA adversarial estático antes da PR foi feito (gate final acima). Backup, merge, deploy, migration, health e DEV continuam pendentes; a decisão é do Codex após os gates.
