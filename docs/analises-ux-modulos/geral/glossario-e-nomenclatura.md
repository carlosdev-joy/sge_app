> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Glossário comparativo e nomenclatura proposta

Data: 12/10/2026. Pedido do usuário: estruturar terminologia para discutir o padrão do mercado e uma experiência customizável premium. Este documento é uma **proposta de linguagem**, não uma alteração dos contratos ou de chaves legadas.

Não existe equivalência universal entre “job”, “pipeline” e “workspace”. A comparação deve começar pelo objeto e pela responsabilidade. Termos consolidados de orquestração convivem com nomes específicos de cada fornecedor.

## Fontes e grau de confiança

- **Informatica:** rótulos diretamente observados em UI-001…UI-021; DOC-INF01 para conceitos de taskflow/publicação/monitor. Documentos com HTTP 403 continuam suplementos parciais, não leitura integral.
- **Databricks:** DB-001…DB-012 observados no workspace Free Edition e no job demonstrativo autorizado; [Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/) e [Spark Declarative Pipelines](https://docs.databricks.com/aws/en/ldp/) para distinções conceituais. Usada a orientação `databricks-docs` para conferir a documentação oficial.
- **Control-M:** fontes oficiais de [navegação](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Navigation.htm), [Monitor](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Monitoring_Navigation.htm), [trial e definições](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Free_Trial.htm), [eventos](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Events.htm) e [variáveis](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Variables.htm). Complementado por tours guiados CTM-006–010; motor real não ensaiado.
- **Airflow:** [DAG Runs](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html) e [Tasks](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/tasks.html), documentação stable consultada em 3.3.2; serve para linguagem, não comprova a versão/configuração do motor do Orquestra.
- **Orquestra:** SPEC/matriz em `52c0c589` e fonte `develop` em `92d14d596c95`. Os aliases, schemas e guardas existentes prevalecem sobre qualquer tradução proposta.

## Mapa entre produtos

| Conceito | Informatica CDI | Databricks | Control-M (documentos e tours) | Uso proposto no Orquestra / cuidado |
|---|---|---|---|---|
| Fluxo de orquestração | Taskflow | Lakeflow Job composto por tasks | Workflow de jobs/folders | **Pipeline** como objeto principal já existente |
| Unidade do desenho | Step, com tipo Data Task/Decision/Wait etc. | Task | Job | **Etapa**; não trocar o nome público por Job sem distinguir o legado |
| Trabalho executável externo | Mapping Task referenciada por Data Task | Notebook/script/SQL/pipeline task | Job executado por Agent | Recurso/job da etapa, identificado por tipo e conexão; não é o pipeline inteiro |
| Transformação de dados | Mapping / Mapplet | Pipeline declarativa de dados | Workload de job específico | Não chamar qualquer canvas de transformação de dados; o Orquestra orquestra tipos distintos |
| Desenho/controle | Taskflow designer | Tasks/DAG | Planning/Map | **Montagem**; “Fluxo” como conceito/desenho e alias compatível |
| Execução específica | Instance / Current Run | Job run / task run | Instância de job no Monitoring | **Execução**, com `runId`; “corrida” pode permanecer em detalhe técnico/legado |
| Tentativa | Não verificada nesta UI | Task retry/repair history documental | Rerun/run count, conforme contrato do produto | **Tentativa da etapa**; não igualar repair, rerun e retry |
| Histórico | My Jobs e Monitor/All Jobs, entradas distintas | Runs | Monitoring e histórico conforme edição | **Histórico de execuções**, dentro de Execução; monitores globais podem encaminhar |
| Ambiente de trabalho | Serviço/organização + catálogo | Workspace é ambiente com recursos | Workspace é área de autoria no Planning | **Espaço de trabalho do pipeline**, explicitando escopo; não equivale ao ambiente Databricks |
| Agrupamento | Project / Folder | Workspace folders e organização de recursos | Folder / SMART folder | Projeto/domínio existentes; folder não equivale automaticamente a Malha |
| Agendamento temporal | Schedule | Scheduled trigger | Scheduling/calendar | **Agenda** e **Agendamento**, preservando oito modalidades atuais |
| Iniciador de execução | Agenda/API/Run conforme taskflow | Trigger temporal ou por evento | Order/run/scheduling conforme contexto | **Disparo** ou “Solicitar execução”; novos gatilhos exigem contrato |
| Dependência executável | Passos/ramos no taskflow | Depends on + Run if | Events/prerequisites/resources | **Dependência** com origem e condição; não apresentar todas como “dados fluindo” |
| Relação entre assets | Uses / Used By | Referências/lineage conforme recurso | Relações e predecessors/successors | Diferenciar **usa/é usado por**, lineage e predecessor executável |
| Decisão | Decision | If/else condition | Condições/eventos conforme recurso | **Decisão**, preservando Sim/Não/Switch e casos atuais |
| Espera/convergência | Wait / Parallel Paths | Dependências e Run if; sem equivalência direta a Wait | Waiting Info, events/resources | **Aguarde**, política existente; não copiar semântica de espera temporal |
| Configuração global | Taskflow properties e task settings | Job details/sidebar | Folder/job properties e Configuration | **Configuração do pipeline**; cadastro administrativo continua próprio |
| Configuração local | Step properties | Task form | Job properties | **Propriedades da etapa**, no inspector de Montagem |
| Runtime | Runtime Environment / Secure Agent | Compute / serverless | Agent / Server | Rotular **ambiente de execução** e conexão/agente real; não presumir equivalência de capacidade |
| Definição publicada | Publish/Unpublish em taskflow | Job editado/salvo; deployments/Git dependem da origem | Check-in/deploy conforme edição/fluxo | **Versão publicada** é contrato Orquestra; não inferir draft/published universal no Databricks |
| Recuperação operacional | Resume/Skip/Stop visíveis, não testados | Repair/rerun documentais, não executados | Rerun/hold/bypass etc. documentais | **Reprocessar**, **pausa de etapa** com guardas atuais; nenhum novo botão por semelhança |
| Exibição personalizável | Filtros/colunas/painéis observados parcialmente | Customize columns observado | Viewpoint/Map/List/Gantt documentais | **Preferência de visualização**, separada de definição e autorização |
| Permissão | Read/Update/Execute etc. documentais | Permissions no job, sem ensaio empresarial | Roles/authorizations documentais | **Capacidade autorizada pelo servidor**; experiência não concede acesso |

O equivalente mais útil ao Pipeline do Orquestra para comparar **orquestração** é o Lakeflow Job, não qualquer recurso chamado Pipeline. Uma task Databricks pode disparar uma pipeline de dados. No Informatica, Mapping define transformação e Mapping Task a configura para execução; Taskflow organiza o controle. Esses objetos não devem ser comprimidos em um único “job” na conversa.

## Vocabulário canônico para discussão e UI

| Termo recomendado | Definição no Orquestra | Evitar |
|---|---|---|
| Pipeline | Definição versionada que organiza etapas, dependências e políticas | “Job” para o pipeline e para a etapa na mesma frase |
| Etapa | Unidade configurável dentro do pipeline, com ID e tipo | Novo menu separado de edição Etapas |
| Tipo de etapa | Um dos onze componentes reais | “Componente premium” sem contrato executável |
| Fluxo | Grafo de etapas e dependências | Confundir desenho/layout com ordem executável |
| Montagem | Destino de autoria do fluxo | “Desenvolvimento” como se concedesse permissão |
| Execução | Destino operacional e instância identificada de corrida | Mostrar rascunho como definição executada |
| Histórico de execuções | Lista de instâncias que seleciona o visualizador comum | Histórico como segundo editor/grafo |
| Tentativa da etapa | Ocorrência de execução daquela etapa dentro de contexto conhecido | Somar solicitação operacional como tentativa do motor |
| Parâmetro | Entrada declarada com tipo/origem/precedência/valor ou referência protegida | “Variável” para qualquer campo de configuração |
| Agenda | Regra temporal/calendário/ODATE já suportados | “Trigger” como promessa de evento de arquivo/tabela não existente |
| Dependência | Restrição de precedência/condição com origem e autoridade | Aresta verde como prova de transferência de dados |
| Versão publicada | Definição confirmada pelo processo de publicação/reconciliação | Toast “publicado” antes de confirmação |
| Rascunho | Definição em edição com revisão/posse | Draft como sinônimo de objeto inválido ou de editor ativo |
| Preferência de visualização | Organização pessoal de colunas/painéis/filtros | Confundir preferência com mudança de pipeline |
| Ambiente da aplicação | DEV/HML/PROD da aplicação servida | Misturar com conexão/destino do job |
| Destino / ambiente de execução | Onde o workload realmente será executado, quando conhecido | Inferir produção apenas pelo rótulo de interface |

Os nomes das cinco abas permanecem os alinhados pelo usuário. Adotar “Execução” em linguagem pública não autoriza renomear `run_id`, tabelas, endpoints, `task_id`, índices de log ou campos de integração. Mapear aliases e manter compatibilidade.

## Estados e verbos devem expressar fatos diferentes

| Palavra/ação | Significado exigido | Não implica |
|---|---|---|
| Aplicar | Incorporar staging ao draft local | Persistência no servidor ou publicação |
| Salvar rascunho | Confirmar revisão persistida com posse válida | Nova DAG ativa |
| Validar | Obter diagnóstico segundo revisão e regras atuais | Executar SQL/job ou garantir dados reais |
| Publicar | Solicitar e confirmar versão pelo processo existente | “Save” de preferência pessoal |
| Solicitar execução | Enviar intenção e receber identidade/resultados autorizados | Início imediato do motor |
| Em fila | Aguardar recurso/fila informados | Esperar predecessor necessariamente |
| Aguardando dependência | Restrição ainda não satisfeita | Falha técnica ou pausa manual |
| Executando | Estado atual confirmado pela fonte | Pulsação inferida a partir do relógio |
| Pulada | Etapa não executada segundo regra/fonte | Sucesso da etapa |
| Pausa marcada | Pedido/portão configurado conforme contrato | Processo remoto já interrompido |
| Fonte indisponível | Sem confirmação recente; mostrar carimbo/último estado | Apagar histórico ou fabricar sucesso |
| Reprocessar | Operação permitida para etapa/corrida/escopo conhecidos | Novo pipeline, cancelamento geral ou repair universal |

**Retry**, **rerun** e **repair** devem ter entrada de glossário ligada ao contrato concreto: retry pode ser tentativa do motor; rerun pode ser nova execução ou reprocesso; repair pode selecionar tarefas e dependentes preservando histórico de uma instância. No Orquestra, a confirmação precisa descrever alvo/alcance real, sem importar a regra do Databricks de usar configuração atual.

## Datas: a diferença que precisa permanecer visível

Logical date/data interval do Airflow não são automaticamente hora real de início. ODATE no Control-M está associado à data de ordenação/agendamento definida por seu contrato. A data operacional e a virada ODATE do Orquestra são regras existentes; não devem ser rebatizadas como equivalentes perfeitas de um campo externo.

Mostrar: data de referência/operacional; início/fim da execução com origem/fuso; carimbo de atualização; duração calculada pela fonte. Fuso selecionável é novo controle se não existir no contrato. Uma UI marcada PDT ou um endpoint UTC não estabelece que o motor do Orquestra tenha a mesma política temporal.

## Como validar a nomenclatura

1. Criar roteiro de leitura para Desenvolvimento, Consulta e Sustentação: identificar pipeline/etapa/execução/versão sem ajuda; explicar o efeito dos verbos antes de acioná-los.
2. Registrar ambiguidades e termos usados espontaneamente. Não trocar um termo só porque aparece em um fornecedor.
3. Revisar labels, ajuda, confirmações, documentação e aliases juntos; preservar chaves legadas e códigos estáveis.
4. Confirmar contratos de tentativas, pausa, agenda e datas no ambiente próprio. Control-M foi observado nos tours guiados CTM-006–CTM-008; validação do motor real continua pendente.
5. Consolidar a decisão de linguagem no contrato visual depois da rodada, com lista de mudanças e migração de ajuda/links. Não editar a SPEC original nesta entrega.

Esse trabalho é UX-11 no backlog proposto. Mudanças de semântica operacional ficam em escopo próprio; um glossário não é uma migração de motor.



## Atualização após autorização de execução e estudo da Malha

O estado atual inclui DB-011/012: primeira tentativa real falhou com tarefas puladas; segunda, com notebook fictício adicional, concluiu Succeeded em17s e mostrou total30. Graph/Timeline/List foram inspecionados. As declarações anteriores de histórico vazio/ausência de execução descrevem a rodada inicial. Repair/retry, carga e RBAC premium continuam não ensaiados.

Control-M CTM-006–010 inclui cinco tours guiados: Build a workflow, Error handling, Reference folder, Forecast e Self-Healing. As pendências anteriores de liberação estão resolvidas. Sem console operacional, nenhum job real Control-M foi executado. A nova proposta de composição, configuração, operação, recursos e governança está em [12-malha-conceitos-e-reestruturacao.md](../modulos/malhas/conceitos-e-reestruturacao.md); amplia o estudo, sem reclassificar recursos novos como SPEC Pipeline existente.
