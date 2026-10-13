# Matriz de preservação funcional — Pipeline ORQUESTRA

Data: 11/10/2026. Fonte conferida: `develop` no commit `df1a81caa3ef5400877bf3ab2f798011552143b2`.

Decisões do usuário: Montagem e Execução são abas principais distintas. Histórico, tentativas e logs pertencem à Execução. Reduzir informação simultânea sem remover funcionalidades existentes. Este inventário é uma revisão do código, não uma certificação de funcionamento das integrações.

## Navegação e responsabilidade

`Visão geral | Montagem | Execução | Configuração | Versões`

Montagem e Execução reutilizam a representação do grafo, com responsabilidades distintas. Não haverá um segundo seletor Montagem/Execução abaixo das abas. Histórico abre sob demanda e retorna à corrida selecionada no canvas. Logs ficam no painel da etapa/tentativa, com opção de ampliar. A tabela operacional é uma alternativa ao grafo, preservando corrida e seleção.

Visão geral resume; Configuração edita dados do pipeline; Montagem edita dados da etapa. Não duplicar formulários. As funções globais de outros módulos não são eliminadas por esta reorganização.

## Inventário dos tipos de etapa

Fonte: [workspaceCatalog.ts](https://github.com/carlosdev-joy/sge_app/blob/df1a81caa3ef5400877bf3ab2f798011552143b2/ui-react/src/components/workspace/workspaceCatalog.ts), `SharedJobConfiguration`, `JobTypeFields`, `SpecializedConfiguration` e painéis especializados.

| Tipo existente | Configuração a preservar | Novo acesso | Protótipo atual |
|---|---|---|---|
| DataStage | Job, conexão SSH, campos e parâmetros DataStage, importação de parâmetros declarados, vínculos e lineage | Montagem → etapa → Configuração / Parâmetros / Lineage | Adição e campos principais; catálogo/importação/lineage pendentes |
| Python | SSH, interpretador, arquivo existente, módulo, código inline e opções de arquivo de destino; vínculos de parâmetros | Montagem → etapa → Configuração; editor ampliável | Adição, modo e recurso ilustrativo; formulários condicionais completos e execução remota pendentes |
| Shell | Comando e conexão SSH, parâmetros e políticas atuais | Montagem → etapa → Configuração | Adição e campos principais |
| Stored Proc | Procedure, conexão MSSQL, banco e parâmetros nome/tipo/valor | Montagem → etapa → Configuração / Parâmetros | Adição e campos principais; editor completo pendente |
| HTTP | URL/comando e todas as opções efetivamente suportadas pelo contrato atual | Montagem → etapa → Configuração | Adição e URL; não inventar novos métodos/auth |
| SQL | Consulta, conexão, banco, política falhar/publicar nulo e prévia autorizada | Montagem → etapa → Configuração | Adição, campos principais; prévia remota pendente |
| Decisão | Condição, origens suportadas, ramos Sim/Não, Switch, casos, ordem, saída padrão e simulação de ramo | Montagem → etapa → Condição / Saídas | Adição e indicação de modo; execução de condições e edição de ramos pendentes |
| Aguarde | Todas com sucesso/todas terminarem; conectar pontas soltas sem criar ciclo | Montagem → etapa → Liberação / Dependências | Adição e política ilustrativa; sem semântica de liberação especializada no simulador |
| Valida Arquivo | Configuração inteira, conexões, catálogo de diretórios e prévia de validação | Montagem → etapa → Validação | Adição e arquivo principal; regras e prévia completas pendentes |
| Notificação | Grupo Teams, template e mensagem | Montagem → etapa → Comunicação | Adição e campos; catálogo e envio pendentes |
| E-mail | Modelo ou corpo livre permitido; HTML, assunto, destinatários, herança do pipeline, placeholders, anexo autorizado e prévia | Montagem → etapa → Comunicação | Adição e campos principais; políticas, placeholders, catálogo, prévia e envio pendentes |

As categorias Extração, Transformação, Qualidade e Entrega da primeira demonstração não substituem estes 11 tipos. Podem futuramente ser templates sobre componentes existentes, mediante especificação própria. O simulador é genérico: não interpreta SQL, Python, Switch, e-mail ou política de Aguarde.

## Configuração do pipeline

Fonte: [WorkspacePipelineFields.tsx](https://github.com/carlosdev-joy/sge_app/blob/df1a81caa3ef5400877bf3ab2f798011552143b2/ui-react/src/components/workspace/WorkspacePipelineFields.tsx), `WorkspaceDraftTools`, `WorkspaceParameters`, `pipelineUtils`.

| Grupo/capacidade existente | Destino proposto | Evidência e aceite de preservação |
|---|---|---|
| Projeto e domínio; nome/identificação e descrição | Configuração → Identificação | Reutilizar catálogo existente; valores legados não disponíveis no catálogo permanecem visíveis e intactos |
| Tags, criticidade, ambiente/destino e SLA | Identificação e Políticas de execução | Preservar chaves, nulls, regras e distinção ambiente da aplicação/destino |
| Ativo e motivo de inativação | Políticas de execução | Publicado inativo exige motivo conforme regra atual; não confundir com pausa do motor |
| Diário, semanal, mensal, quinzenal | Agenda e dependências | Preservar hora e dia da semana/mês; limites reais, inclusive 1–13 na quinzenal |
| A cada N horas | Agenda e dependências | Intervalo, hora inicial/final e minuto; conferir cron/janela gerados |
| Horários específicos | Agenda e dependências | Lista de horários e dias da semana; preservar normalização/validação atual |
| Dia + Hora Específico | Agenda e dependências | Editor de até 5 dias, dias 1–28 e vários horários; não substituir no produto por um texto livre |
| Sob demanda | Agenda e dependências | Não cria agenda automática; execução manual preservada |
| Dias úteis e calendário de feriados | Agenda e dependências | Catálogo real e resposta de indisponibilidade; valor legado preservado |
| Data inicial da DAG e virada ODATE | Agenda e dependências | Mesma data lógica/operacional e regras de virada do contrato atual |
| Predecessores e janelas de dependência | Agenda e dependências | Seletor real, não iniciar antes e hora limite de aviso; preservar autoria das dependências geridas pela malha |
| Concorrência, retries, intervalo e pool | Políticas de execução | Mesmas chaves e limites; pool não equivale à capacidade global de 50 execuções |
| Liberar dependentes/notificar sem movimento | Políticas de execução | Falha técnica continua bloqueando; destino pulado não vira sucesso fabricado |
| Notificar início, conclusão e erro; destinatários | Notificações | Mesmas flags e herança de destinatários de e-mail; validações completas preservadas |
| Runbook Markdown | Documentação | Consulta e sustentação acessam sem entrar em edição |
| Parâmetros DataStage/Orquestra, defaults e vínculo por etapa | Parâmetros; etapa → Parâmetros | Tipo, origem, destino, descrição, precedência, data de referência e prévias preservados |
| Importar parâmetros, catálogo e Maestro | Parâmetros → ações contextuais | Reaproveitar componentes; aplicar proposta somente ao rascunho autorizado |
| Adicionar/alterar/remover valor protegido | Parâmetros → ação específica | Referências protegidas e validações existentes; nenhum segredo no protótipo, URL ou log |
| Configuração completa JSON | Configuração → Avançado | Preservar campos desconhecidos, não recriar o payload apenas com campos visíveis |

No protótipo as oito modalidades e principais campos de governança estão representados. Editor estruturado de dia+hora, seleção real de predecessores, importação, parâmetros completos e valores protegidos continuam pendentes. Campo ilustrativo não conta como integração entregue.

## Montagem, sessão, versões e operação

| Capacidade encontrada no código | Novo acesso | Regra/aceite |
|---|---|---|
| Iniciar, encerrar e assumir edição administrativamente | Contexto do rascunho / Mais | Lease/fence e RBAC do servidor; transferência não autoriza save da sessão anterior |
| Salvar, recarregar e descartar rascunho | Ações do rascunho | Mesma revisão entre Montagem/Configuração; confirmação para descarte; erro não perde alterações |
| Criar rascunho do publicado | Entrada em Montagem | Preservar draft/published e catálogo; não criar uma DAG só para tornar o rascunho localizável |
| Adicionar, mover e conectar etapas; remover aresta/nó | Canvas Montagem | 11 tipos, identificação única, preservação de payload e confirmações atuais |
| Renomear identificador e nome de exibição | Inspector → Identificação | Atualizar referências e ramos conforme contrato; não confundir nome amigável e ID técnico |
| Localizar etapa e organizar desenho | Ferramentas do canvas | Alternativa acessível ao drag; organizar só muda posições |
| Importar etapas e ordem executável | Montagem → Mais | Importação/ordem atuais; prioridade de execução não se confunde com posições do desenho |
| Validação da revisão e diagnóstico por etapa/campo | Resumo inferior e Validar | Revisão salva, guardas atuais, clique abre destino canônico; regras completas dos 11 tipos |
| Solicitar, acompanhar e retomar publicação | Publicar / Versões | Pendente → projetado → gerando → publicado/erro; só afirmar publicada após confirmação real |
| Histórico, comparação entre duas versões e restauração de versão publicada | Versões | Preservar seletores anterior/seguinte, diff de definição/layout e restrição de restauração; comparação rascunho × versão do protótipo é adicional e não substitui comparação entre versões |
| Solicitar execução com conf JSON/data lógica | Execução → Executar → confirmação | Cria solicitação Airflow; DAG pausada pode aguardar. Recebido, em fila e executando são diferentes |
| Data operacional, escolha da corrida e retorno à malha | Execução → seleção / Histórico | Preservar `run_id`, data e origem da navegação; corrida selecionada identifica snapshot ou limitações da fonte |
| Estados, espera, duração, origem e frescor | Canvas e resumo da execução | Sem telemetria não vira sucesso; animação acompanha estado confirmado |
| Tabela de etapas e busca | Execução → vista Tabela | Alternativa ao gráfico, mesma corrida/seleção, sem duplicar painel completo abaixo dele |
| Tentativas e logs Airflow | Inspector → Tentativas / Logs | Identidade pipeline/corrida/task/tentativa; erros e conteúdo vazio distintos; logs escapados |
| Reprocessamento de etapa/cascata e parâmetros | Inspector operacional → Reprocessar | Reutilizar ModalRerunEtapa e guardas; não permitir corrida antiga/versão incompatível onde o backend proíbe |
| Pausas de etapas e gerenciamento | Inspector operacional → Pausa | Reutilizar ModalPausaEtapa e guardas; não inventar cancelamento geral do pipeline |
| Capacidades por sessão/perfil | Ações e leitura conforme servidor | Desenvolvimento, Consulta e Sustentação são experiências; mudar seletor não concede permissão |

Fontes: `WorkspaceEditor.tsx`, `WorkspaceFlowTools.tsx`, `NodeProperties.tsx`, `WorkspacePublication.tsx`, `WorkspaceVersions.tsx`, `WorkspaceOperations.tsx`, `WorkspaceRunProperties.tsx`, `FluxoEditor.tsx` e `useWorkspaceCapabilities.ts`.

## Compatibilidade de acesso

Rotas atuais `fluxo`, `execucoes`, `logs`, `parametros` e `ferramentas` devem ter tratamento explícito. Proposta: `fluxo` abre Montagem; `execucoes` e `logs` abrem Execução, restaurando corrida/etapa/tentativa; `parametros` abre Configuração/Parâmetros; `ferramentas` resolve o destino contextual correspondente.

Preservar parâmetros de experiência, fonte, data, corrida, etapa, tentativa e retorno à malha. Não interpretar uma URL de rascunho como fonte de execução. Os aliases reais e o formato da tentativa serão definidos contra `App.tsx`/`workspaceNavigation` antes da alteração de rotas. Não publicar redirect presumido sem esse teste.

## Condições para substituir as telas no DEV

1. Para cada linha: registrar componente/campo/chave do payload, permissão, novo controle, endpoint, teste/evidência e estado. Nenhuma linha pode desaparecer como consequência da redução de abas.
2. Comparar fixtures de cada um dos 11 tipos antes/depois: valores, defaults, campos desconhecidos, ramos, arestas e referências protegidas permanecem equivalentes quando não editados.
3. Reexecutar testes existentes adequados a cada mudança; validar as oito agendas com cron/dias/ODATE equivalentes e round-trip dos catálogos.
4. Percorrer criar → montar → configurar → salvar → validar → publicar → confirmar → executar → investigar → reprocessar/pausar, com os três públicos e capacidades reais. Registrar operações externas não testadas como pendências.
5. Validar sessão entre abas e duas sessões concorrentes: conflito, expiração de posse e reconexão não sobrescrevem trabalho.
6. Testar links antigos e retorno à malha. Corrida histórica não adota silenciosamente o desenho do rascunho.
7. Não substituir a tela anterior enquanto houver capacidade existente sem destino implementado/testado. Manter piloto/rollback conforme flags atuais até paridade demonstrada.

**Estado desta entrega:** protótipo e especificação revistos; paridade funcional de produção ainda não certificada. A primeira aprovação é de organização e UX. Adaptação React/.NET e validação integrada são entregas subsequentes do DEV.

### Regra para campos adicionais da proposta
Responsável, fuso selecionável, timeout global ou outros controles que não correspondam a um campo comprovado no contrato atual devem ser classificados como proposta e especificados separadamente. Não mapear por semelhança de rótulo nem enviar chave nova silenciosamente. Reutilizar formas, limites e catálogos reais na implementação.

## Estado após a entrega 1 — 11/10/2026

Base `develop` `df1a81caa3ef5400877bf3ab2f798011552143b2`; documentos `52c0c589`; branch `feat/ux-pipeline-contexto` (candidato 2.18.0). Rotas relativas a `/pipelines/{p}/`. Permissões abreviadas: **E** = `consultStages`, **L** = `consultLogs`, **V** = `consultVersions`, **D** = `editDraft` com posse válida (o servidor decide cada escrita). Evidência **UX** = `tests/js/workspace_ux_contexto_harness.cjs` (código real renderizado); **F3/F5/REF** = bancadas existentes. Estado "Entregue" significa destino implementado e testado na bancada; a bancada não exercita DOM, CSS, foco nem o BrowserRouter real. O QA final em navegador do Codex (endpoints sintéticos, evidências em `/root/orquestra-ux-evidencias/`) cobriu sessão Montagem ↔ Configuração em seis variações, preservação de payload nas oito agendas, troca de Definição com alterações e foco/modal ao voltar/avançar entre grupos. O parecer adversarial final é SHIP após os seis achados e o residual de composição dos escopos de overlay. Isso não certifica motor, integrações remotas nem os cenários pendentes abaixo. Fechamento: PR #499 integrada em `develop` `8a57ac6a`, publicada no DEV como 2.18.0; smoke próprio PASS com duas sessões (incluindo a resposta 409 à sessão concorrente) e limpeza das fixtures; navegador PASS para saída pelo histórico e troca de Experiência com rascunho sujo (registro do Codex).

### Configuração do pipeline (editor único: `configuracao?grupo=…`)

Todas as linhas gravam em `definition.metadata.legacyPipeline` (ou `legacyTables`) pelo mesmo patch de antes, via `PUT /workspace/drafts/{id}` com `expectedRevision` e `fence` da sessão. Componente: `WorkspacePipelineGroup` → `WorkspaceGovernanceFields(section)` / `WorkspaceCatalogFields` / `WorkspaceScheduleFields` (inalterados por dentro).

| Capacidade | Chaves | Grupo | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Projeto e domínio (catálogo; legado fora do catálogo visível) | `project_name`, `domain` | identificacao | E (leitura) / D | UX inventário | Entregue |
| Nome amigável e identificador técnico | `identity.displayName`, `identity.pipelineName` | identificacao (leitura) + cabeçalho | E | UX | Entregue em leitura; edição não existe no contrato |
| Descrição, tags, criticidade, ambiente de destino | `descricao`, `tags`, `criticidade`, `ambiente` | identificacao | E / D | UX (edição de `descricao` no save) | Entregue |
| Responsável | `draft.responsible` | identificacao (leitura) + Visão geral | E | UX | Entregue em leitura |
| Oito agendas, dias úteis, calendário | `schedule_type`, `scheduled_time`, `schedule_dow`, `schedule_dom`, `horarios_especificos`, `dias_semana`, `dias_horarios_mes`, `somente_dias_uteis`, `calendario_nome` | agenda | E / D | UX (8 opções; `hourly_n` → `custom` + horários no save); navegador `browser-preservation.json` (8 agendas, payload sintético) | Entregue |
| Data inicial DAG e virada ODATE | `dag_start_date`, `hora_virada` | agenda | E / D | UX inventário | Entregue |
| Predecessores (seletor real) e janelas | `legacyTables.etl_pipeline_dependencia`, `depends_on`, `nao_iniciar_antes`, `hora_limite_dependencia` | agenda (`DependenciasModal`) | E / D | UX inventário; testes F9 de dependência inalterados | Entregue |
| Parâmetros, importação, catálogo, Maestro, protegidos | `legacyTables.etl_pipeline_param` / `parameters` | parametros (`WorkspaceParameters` inalterado) | E / D; segredo exige posse | UX (tabela protegida intacta no save); F7A | Entregue |
| Ativo e motivo | `active`, `motivo_inativacao` | politicas | E / D | UX inventário | Entregue |
| SLA, runs simultâneas, retries, delay, pool | `sla_minutos`, `max_active_runs`, `retries_count`, `retry_delay_seconds`, `pool_name` | politicas | E / D | UX (edição de SLA no save) | Entregue |
| Sem movimento | `liberar_dependentes_sem_movimento`, `notificar_sem_movimento` | politicas | E / D | UX inventário | Entregue |
| Notificar início/conclusão/falha e destinatários | `envia_msg_inicio`, `envia_msg_fim`, `envia_msg_erro`, `email_destinatarios` | notificacoes | E / D | UX inventário | Entregue |
| Runbook | `runbook_md` | documentacao; Visão geral indica disponibilidade | E / D | UX inventário | Entregue |
| Configuração completa JSON | `definition.metadata` inteiro | Configuração → Avançado | E / D | código reaproveitado sem mudança de regra | Entregue |

### Montagem, sessão e versões

| Capacidade | Novo acesso | Componente / endpoint | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Iniciar, encerrar, assumir edição; recarregar; descartar | Cabeçalho na Montagem/Configuração; Descartar abaixo | `WorkspaceEditor`; `/lease`, `/transfer`, `DELETE /lease`, `DELETE /drafts/{id}` | D / administer | UX (uma posse em quatro trocas de destino) | Entregue |
| Proteção de saída com alterações não salvas | Links, voltar/avançar, seletores Definição/Experiência, paleta Ctrl+K | `lib/navigationGuard` (diálogo da aplicação; popstate desfeito pelo `idx` do BrowserRouter); só fora da sessão (outro pipeline, fonte, experiência ou fora do Pipeline) | — | UX (History simulado: voltar na sessão sem diálogo; saída desfeita, cancelar conserva, confirmar navega uma vez e descarta o cache local; clique/programática com intenção verificada) | Entregue; navegador validou cancelar/confirmar Definição, saída por histórico e troca de Experiência |
| Vistas conservadas | Montagem ↔ Configuração; Execução ao voltar | Montagem e Configuração montadas na 1ª visita e ocultas por wrapper sem display; overlays de área oculta inertes (`OverlayScope` no `Modal`/`Sheet`) | — | UX (canvas e ferramentas renderizados sob `hidden`; nenhum `hidden` com utilitário de display; Modal inerte sem `role=dialog`) | Entregue; sessão em 6 variações e foco/modal de grupos no navegador; zoom operacional pendente |
| Salvar rascunho (mesma revisão) | Cabeçalho e rodapé da Configuração | `PUT /workspace/drafts/{id}` | D | UX (fence 41, revisão 7 → 8) | Entregue |
| Criar rascunho do publicado | Faixa na Visão geral/Montagem/Configuração | `POST /workspace/pipeline-drafts` | D | código inalterado | Entregue |
| 11 tipos, adicionar/mover/conectar/remover, renomear, localizar, organizar | `montagem` | `WorkspaceCanvas`, `NodeProperties` (inalterados) | E / D | UX (11 tipos na biblioteca, adição, payload intacto); REF/F3; navegador `browser-preservation.json` (11 tipos, campos desconhecidos e referências protegidas nas 8 agendas) | Entregue |
| Importar etapas (formulário e JSON) e ordem de execução | `montagem` → Ferramentas do fluxo | `WorkspaceFlowTools`, `WorkspaceJsonTools mode=import` | D | código reaproveitado | Entregue |
| Validar e publicar; acompanhar/retomar publicação; diagnóstico abre etapa | Abaixo do canvas na Montagem e da Configuração (uma instância) | `WorkspacePublicationPanel`; diagnóstico na Configuração leva à Montagem; acompanhamento não consulta com o editor oculto | V / publish | F4 existentes; UX (instância única nas duas vistas) | Entregue (barra unificada é F4) |
| Histórico, comparação e restauração de versões | `versoes` | `WorkspaceVersions` (restore abre `montagem`) | V / D | F4 existentes | Entregue |

### Execução (sempre configuração publicada ou snapshot da corrida)

| Capacidade | Novo acesso | Componente / endpoint | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Data operacional, corrida, retorno à malha | `execucao?data=…&run_id=…&de=malha:…[&corrida=…]` | `FluxoEditor` (BarraExecucao) / Tabela; `GET /workspace/executions`; `malhaReturnPath` (malha, data e corrida da malha; destino montado, nunca URL livre) | E + L | UX/F5 (aliases, query e hash) | Entregue |
| Cabeçalho da corrida | Cabeçalho | `workspaceHeaderContext` + identidade com origem (pipeline, data, corrida); nome/metadados do snapshot da versão ou da publicada, nunca do rascunho | E + L | UX (sem "Rascunho" em 4 casos; origem distinta por data/corrida) | Entregue |
| Solicitar execução (conf JSON/data lógica) | Cabeçalho → Executar pipeline | `RunRequest`; `POST /workspace/runs` | execute | F5 existentes | Entregue (guiado sem JSON é F5) |
| Tabela de etapas e busca; tentativas e logs | `execucao?vista=tabela[&etapa=…&tentativa=…]` | `WorkspaceOperations` vista Tabela; `GET /pipeline-task-log`. `etapa`/`tentativa`/`run_id` são o contrato entre gráfico, tabela e o link do inspector (sem segredo na URL); sem tentativa vale a corrente da etapa na corrida exibida; tentativa ou corrida que não corresponde não abre log | E + L | UX (corrente 3, histórica 1, tentativa 7 recusada, outra corrida recusada, etapa sem tentativa sem botão, log como texto) | Entregue; tabela permanente sob o gráfico removida |
| Investigação conservada | Gráfico ↔ Tabela; sair e voltar à Execução | Uma instância por pipeline; gráfico (zoom, seleção) e tabela (busca) montados, o inativo oculto e sem teclado/polling | E + L | UX (busca e gráfico conservados ao alternar; vista oculta sem log nem ação) | Entregue na bancada; zoom operacional e logs com API real pendentes |
| Reprocessar e pausas | Inspector operacional no gráfico | `ModalRerunEtapa`, `ModalPausaEtapa` (inalterados) | reprocess / pauseStages | F5 existentes | Entregue |
| Inspector operacional com abas Resumo/Tentativas/Logs, estados animados, polling 5s | — | — | — | — | Candidato F5 (ver [Candidato F5 — 2.21.0](#candidato-f5--2210-11102026)); polling 5 s não autorizado, 30 s vigente |

### Compatibilidade de acesso

| Endereço anterior | Destino | Acréscimo | Evidência |
|---|---|---|---|
| `fluxo`, `etapas`, `ferramentas` | `montagem` | — | UX |
| `execucoes` | `execucao` | — | UX, F5 |
| `logs` | `execucao` | `vista=tabela` | UX, F5 |
| `parametros` | `configuracao` | `grupo=parametros` | UX |
| `/jobs?pipeline=…`, `/fluxos?pipeline=…[&modo=execucao]` | `montagem` / `execucao` | `experiencia` conforme modo | UX, F5 |

Query e hash preservados integralmente; o destino canônico não redireciona de novo. Nenhuma linha da matriz original ficou sem destino.

### Cobertura final e limites do candidato 2.18.0

- Suite final de Claude após a correção de grupos: 7342 PASS, 8 falhas preexistentes idênticas e 51 skip; tsc PASS, lint com 73 assinaturas únicas e zero novas, build recompilado por último. Codex executou independentemente 7341 PASS / mesmas 8 falhas / 51 skip antes do último teste adicional. Fonte da rodada final: `claude-ux-group-result.json` nas evidências externas.
- `browser-session.json`: seis variações PASS (1440 claro/escuro, 1280, 947, 390 claro/escuro). `browser-preservation.json`: oito agendas PASS com os 11 tipos, campos desconhecidos e referências protegidas. `browser-dirty-after.json`: cancelar e confirmar troca de Definição PASS com diálogo da aplicação. `browser-groups.json`: Back não captura foco no grupo oculto; Forward conserva o modal e conteúdo, PASS.
- A regressão de grupos compõe `OverlayScope` herdado com grupo/aba ativa e cobre catálogo de parâmetros e seletor de predecessores reais na bancada. O contexto do minireact agora propaga Provider aos filhos; efeitos, pilha de overlays e Esc reais continuam fora da bancada. O teste de navegador cobre foco e conservação do modal entre grupos.
- Segurança manual sem bloqueador; `security-review` embutida indisponível/não executada. QA adversarial final SHIP para o candidato; sistema visual existente mantido, sem reparo/canonização do drift preexistente.
- Fechamento DEV: `develop` `8a57ac6a` (PR #499) publicado como 2.18.0; smoke próprio PASS com duas sessões (incluindo a resposta 409 à sessão concorrente) e limpeza; navegador PASS para saída pelo histórico e troca de Experiência com rascunho sujo. Sem motor/DataStage real e sem piloto com usuários.
- Permanecem pendentes: zoom operacional, logs com API real e percurso integrado com motor/capacidades reais. A restauração com rascunho sujo oculto conserva o comportamento anterior sem confirmação. F4/F5 (composição final, barra unificada, inspector operacional com abas e polling 5 s) não são certificadas por esta entrega F3 inicial. Evidência sintética e inventário de destino não equivalem à certificação integrada de paridade de produção.

## Candidato F4.1 — 2.19.0 (11/10/2026)

Base `develop` `8a57ac6a`; branch `feat/ux-pipeline-montagem-f4`. Evidência **UX** = seções 11–13 da mesma bancada (`tests/test_workspace_ux_montagem.py`). Navegador, commit, PR e DEV pendentes. Detalhes nas [release notes](release-notes/2.19.0-pipeline-ux-montagem.md).

| Capacidade | Novo acesso | Componente | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Largura do workspace | Montagem e Execução na largura da área de conteúdo; Visão geral/Configuração/Versões na largura anterior | `lib/shellFrame`, `AppShellV2` | — | UX (moldura por rota; demais telas iguais) | Candidato |
| Recolher biblioteca e inspector | Barra do canvas: Componentes, Propriedades | `WorkspaceEditor` | — | UX (seleção, vista, busca, JSON não aplicado e posse conservados) | Candidato |
| Localizar etapa | Barra do canvas | `WorkspaceEditor` | E | código | Candidato |
| Salvar, Validar e Publicar | Cabeçalho, ordem fixa | `WorkspaceEditor` + `WorkspacePublicationPanel` (instância única, portal) | D / V / publish | UX (gates, um pedido por clique, fence e revisão salvos) | Candidato |
| Diagnóstico recolhível | Abaixo do canvas, resumo sempre visível | `WorkspacePublicationPanel` | V | UX (abre com problema; diagnóstico reabre o inspector) | Candidato |
| Fonte da Execução | Linha de contexto | `WorkspaceOperations` | E + L | UX | Candidato |
| Desfazer/refazer, inspector em subseções | — | — | — | — | Pendente F4.2 |

F4.1 fechada: PR #500 integrada em `develop` `3900e7c2` e validada no DEV como 2.19.0.

## Candidato F4.2 — 2.20.0 (11/10/2026)

Base `develop` `3900e7c2`; branch `feat/ux-pipeline-inspector-f4`. Evidência **H** = `tests/js/workspace_history_harness.cjs` (módulos puros); **UX14** = seção 14 da bancada do editor; ambas presas por `tests/test_workspace_ux_inspector.py`. Navegador real com APIs sintéticas: 13 verificações dos formulários, 6 da proteção de alterações não aplicadas e 3 de foco/atalhos aprovadas. Diagnóstico no campo exato confirmado frio/quente (2 cenários). Visual final SHIP (12 capturas); suíte 7365 aprovados / mesmas 8 falhas / 51 ignorados, tsc aprovado e lint 176 ocorrências / 73 assinaturas sem novas. QA adversarial final SHIP (18 verificações); build aprovado e zero NUL novo. p95 local 300 etapas 116,9 ms (<200); commit, PR e DEV pendentes. Detalhes nas [release notes](release-notes/2.20.0-pipeline-ux-inspector.md).

| Capacidade | Novo acesso | Componente | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Configuração da etapa dos 11 tipos (campos, conexões, parâmetros, vínculos) | Inspector → Configuração, inline | `NodeProperties` + `SharedJobConfiguration` / `SpecializedConfiguration` (painéis existentes) | E / D | UX14; navegador (11 tipos inline, aplicação/salvamento, campos desconhecidos e referências preservados) | Candidato |
| Identificador, renomear, ordem de execução, remover | Inspector → Etapa | `NodeProperties` (`requestText`, modal de remoção existente) | D | UX14; H (renomear exato) | Candidato |
| Lineage da etapa e importação DSX/ISX | Inspector → Lineage, inline | `WorkspaceLineage` | E / D | UX14 (diagnóstico abre Lineage); H | Candidato |
| JSON da etapa | Inspector → Avançado (só quando pedido) | `NodeProperties` | E / D | UX14 (recusa alterar protegido) | Candidato |
| Valor protegido da etapa | Configuração → Valores protegidos → modal | `WorkspaceSecretParameter` (inalterado) | D | UX14 (referência, histórico reiniciado, sem valor em claro) | Candidato |
| Aplicar com mescla por campo e conflito explícito | Botão Aplicar de cada subseção | `lib/workspacePatch` | D | H (outro campo, clone, mesmo campo, removida, renomeada, ramos, repetida, ciclo); UX14 (Shell após save; SQL após SLA/arraste) | Candidato |
| Desfazer/refazer local (50 passos) | Barra do canvas; Ctrl/⌘+Z, Ctrl/⌘+Shift+Z, Ctrl+Y | `lib/workspaceHistory`, `WorkspaceEditor` | D com posse | H (limite, no-op, refazer, gesto, digitação, memória 300, foco após o último passo); navegador (último Desfazer/Refazer por ponteiro/Enter com atalho imediato); UX14 (seleção, servidor 0, arraste, atalhos, recarregar/salvar limpam) | Candidato |
| Modo focado | Inspector → Expandir propriedades; ampliar em Python/SQL/Decisão | `WorkspaceEditor` | — | UX14; navegador (formulário e canvas conservados, Esc) | Candidato |
| Diagnóstico abre subseção/campo | Painel de validação → etapa | `WorkspacePublicationPanel` → `NodeProperties` | V | UX14 (Configuração, Lineage, campo desconhecido); H (seção 9: alvo do foco e não roubar); navegador (Conexão MSSQL exata fria/quente/chunk retido; Etapa, nome, desconhecido; sem roubo ao trocar subseção, mover foco, recolher ou reselecionar) | Candidato |
| Troca de etapa com alterações não aplicadas | Canvas, localizador, diagnóstico, fechar | `WorkspaceEditor` (`confirmAction`) | — | UX14; navegador (SQL → Shell → SQL descarta só após confirmação) | Candidato |

Limites F4.2: `minireact` conserva estado ao voltar à mesma chave após desmontagem (A → B → A); a regressão de descarte foi verificada com React real, sem ampliar a bancada. Diálogos de navegação interna são da aplicação; fechar/recarregar fisicamente a aba usa `beforeunload` nativo. Segurança manual ratificada sem bloqueador confirmado; `security-review` embutida indisponível/não executada. Nenhuma execução/publicação real, piloto ou certificação integrada F3/F5/F2/F6 decorre destas fixtures.

Orçamento F4.2 em preview de produção: Montagem fria 246,3 KiB gzip; com primeiro SQL 284,9 KiB (ambos <300 KiB). Agregado aquecido após os 11 formulários lazy: 306,1 KiB (>300 KiB), registrado como limite sem encerrar o aceite total da F6.

Performance F4.2: p95 de 75,1 / 77,4 / 116,9 ms em 50 / 100 / 300 etapas, 25 amostras por tamanho, Chromium local em 1440 e APIs sintéticas; proxy de seleção até dois frames, não INP de campo. Diagnóstico final do Claude: 14 cenários aprovados; Lineage sem controle editável preserva foco na seção, sem prova integrada de edição desse cenário.

F4.2 fechada: PR #501 integrada em `develop` `52843c6e` e publicada no DEV como 2.20.0; suíte 7365 aprovados / mesmas 8 falhas preexistentes / 51 ignorados; fixture própria nativa SQL/Shell com rascunho e posse PASS.

## Candidato F5 — 2.21.0 (11/10/2026)

Base `develop` `52843c6e`; branch `feat/ux-pipeline-execucao-f5`; migration 167. Evidência **P** = bancada pura `tests/js/workspace_execution_harness.cjs`; **UX7** = seção 7 da bancada da tela; ambas presas por `tests/test_workspace_ux_execucao.py`. **NR** = navegador real (Chromium, APIs sintéticas, sem capturas, 13 verificações). Mutações dirigidas 12/12 derrubadas. No lote de acessibilidade, 7 mutações válidas. Em PR para `develop`; DEV e fixture própria pendentes até o merge e o deploy. Detalhes nas [release notes](release-notes/2.21.0-pipeline-ux-execucao.md). Substitui, na Execução do workspace, o `FluxoEditor`/`BarraExecucao` citados nas tabelas anteriores (o `FluxoEditor` segue nas telas legadas).

| Capacidade | Novo acesso | Componente / endpoint | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Visualizador comum | Execução → Gráfico | `WorkspaceCanvas`/`WorkspaceFlowNode` não editáveis; `GET /workspace/executions` | E + L | UX7 (um gráfico, sem ferramentas); smoke do root (seis ligações) | Candidato |
| Estados e ligações | Nó, legenda, tabela | `lib/workspaceExecution` (`nodeRunState`, `edgeRunState`), `WorkspaceRunStatus` | E + L | P (sem telemetria nunca verde; executando só anima com telemetria ativa; desconhecido com código); UX7 | Candidato |
| Fonte, frescor e identidade da resposta | Linha de contexto | `responseMatchesRequest` (pipeline pela grafia pedida ou oficial, corrida, data), `drawingSource` | E + L | P; UX7 (outro pipeline com mesmo `run_id`, outra corrida, outra data); NR (sem nó/título/versão errados) | Candidato |
| Inspector operacional | Direita; Expandir investigação | `WorkspaceRunInspector` (Resumo, Tentativas, Logs, Parâmetros) | E + L | UX7 (log texto, tentativa alheia recusada, anúncio só da selecionada); NR (zoom após aba e modo focado) | Candidato |
| Gráfico e Tabela alternativos, localizar | Barra da Execução | `WorkspaceOperations` | E + L | UX7 | Candidato |
| Histórico com filtros e paginação | Execução → Histórico | `WorkspaceRunHistory` (lazy); `GET /pipeline-run-history` | E + L (as três telas) | pytest (permissão e 422 antes do banco, nome exato, paginação, degradação, erro sanitizado); UX7; NR | Candidato |
| Executar guiado | Cabeçalho → Executar pipeline | `WorkspaceRunRequest` (lazy); `POST /workspace/runs` | execute | P; UX7 (sem JSON, inválido não dispara, mesmo identificador, Solicitado ≠ Em fila ≠ Executando, contexto trocado sem POST); NR (sessão trocada sem POST, sucesso tardio não seleciona, corrida devolvida selecionada) | Candidato |
| Reprocessar e pausas | Inspector → ações | `ModalRerunEtapa`/`ModalPausaEtapa` (lazy; `guard` opcional, legado igual) com alvo congelado e `task_id` real | reprocess / pauseStages | UX7 (descarte por etapa/corrida/sessão, envio com sessão trocada sem POST, `task_id` ≠ job); NR (prévia com `airflow.Consulta`; fechamento ao trocar etapa/corrida/aba, sem reabrir) | Candidato |
| Leituras ocultas e revalidação | — | `enabled` por aba ativa e navegador visível (execução, log, histórico, `ValidacaoExecucao`) | — | UX7; NR (zero leituras ocultas; uma ao voltar) | Candidato |
| Cadência | — | `EXECUTION_POLL` | — | P (30 s; 5 s só com medição) | 30 s vigente; 5 s não autorizado |
| Teclado e movimento reduzido no canvas comum | Montagem e Execução → etapa focada; Localizar etapa | `WorkspaceCanvas` (Enter em captura → `onSelect`), `lib/workspaceCanvasA11y` (`nodeForEnter`, `fitViewDuration`); medidas do React Flow devolvidas ao nó | E | P (Enter só na própria etapa, sem modificador/repetição/IME/diálogo/controle aninhado; duração 0 com `reduce`); NR (`browser_keyboard.py` do root; 23 verificações no preview e no `dist/`: foco mantido inclusive após ampliar, nenhuma etapa invisível ao trocar a seleção, ligação limpa, Delete/setas/Ctrl+Z da Montagem intactos, 1 passo de reenquadramento com `reduce` contra 14 sem) | Candidato; Esc com foco na etapa selecionada leva o foco ao documento (React Flow, preexistente, pendente) |

Correção 2.21.1 (branch `fix/ux-pipeline-identidade-pausa`, migration 168): na linha **Reprocessar e pausas**, a pausa, a prévia e a reexecução com corrida `workspace__<uuid>` ou com outro run_id do Orquestra leem a corrida exata no Airflow (`GET /dags/{dag}/dagRuns/{run_id}`) para obter o `ts_nodash`, depois das recusas existentes. Permissão, ODATE ambíguo, falta de corrida, modo degradado e escolha da corrida não mudam. Evidência: `tests/test_pausa_corrida_exata.py` (dublês); 12 mutações derrubadas e 1 equivalente, explicada nas release notes. Integrada pela PR #503 (`develop` `92d14d59`) e publicada no DEV como 2.21.1. O smoke nativo de pausa, liberação e retry está em andamento e não foi aprovado. Detalhes nas [release notes](release-notes/2.21.1-pausa-corrida-exata.md).

Correção 2.21.2 = EOC-F1 (candidato; branch `fix/ux-pipeline-tentativas-motor`, migration 169 candidata), na linha **Inspector operacional**:
- **Tentativas e Logs.** As abas listam as tentativas do motor (`GET /pipeline-task-attempts`, permissões E + L, corrida e tarefa exatas, sob demanda, chave por sessão/pipeline/corrida/tarefa).
- **Log.** Abre pelo `try_number` comprovado pelo motor, o mais recente iniciado por padrão. `tentativa` na URL é esse número.
- **Número SQL.** Vira "Tentativa operacional" (Resumo, seção própria, coluna da Tabela) e não abre log.
- **Evidência.** `tests/test_tentativas_motor.py`, bancadas P e UX7 ampliadas, 23 mutações derrubadas, 18 verificações em navegador real com APIs sintéticas. Na EOC-F1, leitura do Airflow em blocos com teto de 1 MiB, provada com `httpx` real (22 mutações derrubadas, 1 equivalente).
- **Limite.** O Airflow real fica para o smoke nativo do root. Detalhes nas [release notes](release-notes/2.21.2-tentativas-motor.md).

Critérios ainda externos (não certificados por estas evidências): fixture própria SQL/Shell no DEV com executing → success, paralelismo, falha/retry, pulada, pausa e sem telemetria; frequência medida com SQL/upstream/carga concorrente; comparação visual com mockup 01 e capturas 02/13/14 (passes visuais coordenados pelo root); smoke DEV §7 g–i. Orçamento (medição final do root no build final): Montagem fria 276,8 KiB, Execução fria 293,6 KiB e Execução com a primeira investigação de logs 293,6 KiB, em gzip JS+CSS (<300). Agregado aquecido após log, histórico e reprocesso: 301,3 KiB (>300, limite registrado, não remedido). Seleção p95 67,0 / 83,5 / 103,6 ms em 50 / 100 / 300 etapas (proxy local, não INP de campo).

## Candidato F2 — 2.22.0 (11/10/2026)

Base `develop` `f05bd4e9` (PR #505, EOC-F1); branch `feat/ux-pipeline-descoberta-f2`; migration 170. Evidência **B** = `tests/js/pipeline_index_harness.cjs` (código real; 14 mutações derrubadas); **E** = `PipelineIndexTests.cs` (endpoint, offline; a executar no feed fixado); **S** = `PipelineIndexSqlTests.cs` (`[SqlFact]`, SQL real); **NR** = navegador real com APIs sintéticas (38 verificações). Sem commit, PR ou DEV. Detalhes nas [release notes](release-notes/2.22.0-pipeline-ux-descoberta.md).

| Capacidade | Novo acesso | Componente / endpoint | Permissão | Evidência | Estado |
|---|---|---|---|---|---|
| Lista de publicados e rascunhos ativos, uma linha por pipeline pela collation | `/pipelines` (coorte) | `PipelineCatalog`; `GET /workspace/pipeline-index` (`SqlPipelineIndex`) | `tela_pipelines` | B; S (grafia divergente, acento, concorrência com `PublishAsync`); NR | Candidato |
| Busca, situação, projeto/domínio e páginas no servidor; filtros na URL | Barra de busca e filtros | `lib/pipelineIndex`, mesmo endpoint | `tela_pipelines`; `editing` também sem `tela_jobs` | B; E (422 antes do banco, `editing` 200 para leitor sem `tela_jobs`); S (páginas estáveis); NR (debounce, cancelamento, `offset`) | Candidato |
| Situação visível sem hover (publicado/versão, em desenvolvimento/revisão, em edição por, inativo) | Linha | `pipelineChips` | posse válida para todo leitor do índice; nunca `fence`/sessão | B; E/S (leitor sem `tela_jobs` vê editor válido; expirada some); NR | Candidato |
| Retomar rascunho sem perdê-lo | *Continuar montagem* / *Abrir montagem* | `resumeAction` → `montagem?experiencia=desenvolvimento` | `editDraft` + `consultStages` | B; NR (rascunho criado reencontrado e retomado) | Candidato |
| Menu secundário coerente | *Mais ações de …* | `pipelineMenu` (Visão geral, Montagem, Execução, Configuração, Versões) | capacidades do servidor | B; NR (teclado) | Candidato |
| Consultas do cadastro publicado (ver, lineage, histórico) | *Mais ações* em publicados | `ViewModal`, `LineageModal`, `AuditModal` (inalterados) pela grafia exata | como antes | B | Candidato |
| Editar, inativar, gerar DAG, executar e exportar modelo pelo cadastro anterior | *Lista clássica* (`?legado=1`) e fora da coorte | `Pipelines` anterior, inalterado | como antes | B; NR | Preservado |
| Criação essencial (nome, identificador, projeto/domínio do catálogo, descrição) | *Novo pipeline* → `/pipelines/novo` | `PipelineCreate`; `POST /workspace/pipelines` (inalterado) | `editDraft` | B (inválido sem POST, 409 no campo, rede); NR | Candidato |
| Agenda na criação | Configuração → Agenda e dependências | `WorkspaceScheduleFields` (inalterado) | `editDraft` | B (agenda ausente da criação); NR | Movida ao editor canônico |
| Esquema ausente | Lista | 503 `draft_schema_unavailable` nomeando a 141; *Usar lista clássica* | — | E; B; NR | Candidato |

Nenhuma linha anterior perdeu destino: a lista anterior continua acessível, com as mesmas ações, para a coorte e para quem está fora dela.
