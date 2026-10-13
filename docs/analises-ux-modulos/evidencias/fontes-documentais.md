# Referências documentais oficiais — UX Orquestra

Consulta: 12/10/2026, América/São Paulo (13/10/2026 UTC). Evidência documental pública; nenhuma observação direta do produto ou sessão privada. Dez páginas/documentos oficiais abertos integralmente por ferramenta web. Comportamentos abaixo são documentados pelo fornecedor; aplicabilidade a Orquestra é inferência de design, não contrato existente. Não foram copiados scripts.

## Fontes abertas com sucesso

### DOC-INF01 — Taskflow for Orchestrating your Data Integration tasks

URL: https://www.informatica.com/content/dam/informatica-cxp/techtuesdays-slides-pdf/Advanced%20Taskflow%20for%20Data%20Integration.pdf

Data editorial: não explicitada no PDF; material histórico de treinamento oficial. Aberto em 12/10/2026, PDF de 30 páginas.

Documentado: templates básicos, paralelos e sequenciais; Run no designer; publicação gera endpoints; agendamento associa taskflow a schedule. My Jobs lista subtarefas; Monitor mostra trajetória e estado dos passos; visão avançada contém variáveis e logs (páginas 14, 23, 26–27). Execução por API pode restringir usuários/grupos (página 15).

Aplicabilidade: separar desenho, versão publicada e execução; detalhe do nó com estado e evidência operacional. Limite: treinamento antigo, não prova interface ou RBAC atuais. Não sustenta rollback/versionamento completo. Agenda e binding/API são conceitos distintos.

### DOC-DB01 — Monitor Lakeflow Jobs

URL: https://docs.databricks.com/aws/en/jobs/monitor

Atualizado: 08/10/2026. Aberto em 12/10/2026.

Documentado: lista filtrável por execução; matriz tarefa × execução; detalhe com graph, timeline e lista; clicar nó abre metadados, saída e logs; histórico da tarefa selecionável. Histórico retido até 60 dias. Jobs implantados por bundle ficam somente leitura na UI por padrão; mudanças após desconexão não atualizam automaticamente a origem.

Aplicabilidade: contexto execução → tentativa → nó, com preservação de filtros e identidade; complementar DAG com lista. Limite: retenção e configuração por bundle são características Databricks, não requisitos Orquestra. Estados agregados dependem de tarefas folha; não copiar sua semântica para o contrato atual.

### DOC-DB02 — Troubleshoot and repair job failures

URL: https://docs.databricks.com/aws/en/jobs/repair-job-failures

Atualizado: 09/10/2026. Aberto em 12/10/2026.

Documentado: matriz identifica falha ou salto por dependência; detalhe mostra erro; Repair run apresenta tarefas malsucedidas e dependentes antes de executar. Reparo usa configuração atual e reinicia tarefas do começo; histórico permanece. Reparo apenas para jobs com duas ou mais tarefas. Duração inclui intervalo desde início original até reparo final.

Aplicabilidade: oferecer preview do alcance de retentativa e histórico de tentativas. Limite: reparo não garante idempotência; operação e semântica devem existir no backend Orquestra antes da ação na UI. Não confundir tentativa com nova execução independente.

### DOC-DB03 — Jobs with a large number of tasks

URL: https://docs.databricks.com/aws/en/jobs/large-jobs

Atualizado: 11/09/2026. Aberto em 12/10/2026.

Documentado: até 1000 tarefas; matriz com muitas tarefas e execuções pode ficar lenta ou mostrar apenas resumo. Reduzir intervalo de tempo melhora visualização.

Aplicabilidade: listas filtráveis e renderização progressiva para DAG/histórico grandes. Limite: números são limites do fornecedor; não representam capacidade demonstrada de Orquestra.

### DOC-DB04 — Automate jobs with schedules and triggers

URL: https://docs.databricks.com/aws/en/jobs/triggers

Atualizado: 06/10/2026. Aberto em 12/10/2026.

Documentado: gatilhos por horário, tabela, arquivo, modelo e contínuo; seção Schedules & Triggers permite editar, pausar, retomar e remover. Pausar impede novos disparos, mantendo execuções ativas. Múltiplos gatilhos são Beta e dependem de habilitação pelo administrador.

Aplicabilidade: explicar impacto de pausar agenda e distinguir estado do gatilho de estado da execução. Limite: não transportar gatilhos avançados/Beta ao escopo contratado; são novo escopo quando backend não oferece suporte.

### DOC-ADF01 — Visual authoring in Azure Data Factory

URL: https://learn.microsoft.com/en-us/azure/data-factory/author-visually

Atualizado: 25/03/2026. Aberto em 12/10/2026.

Documentado: atividades arrastadas para canvas; execuções de teste/debug; propriedades gerais à direita, subrecursos no painel inferior; Related identifica referências ao recurso selecionado; Manage reúne conexões, triggers e runtimes.

Aplicabilidade: inspector contextual e dependências navegáveis; separar edição e operação. Limite: documentação cobre ADF/Synapse, não Microsoft Fabric; diferenças de produto não devem ser amalgamadas.

### DOC-ADF02 — Visually monitor Azure Data Factory

URL: https://learn.microsoft.com/en-au/azure/data-factory/monitor-visually

Data editorial: não registrada na extração. Aberto em 12/10/2026.

Documentado: lista por intervalo/status/pipeline; detalhe da atividade com entrada, saída e erro; rerun desde atividade falha e histórico de reruns; Gantt por pipeline/tag e atividade. Atualização da lista exige Refresh manual; autorefresh não suportado. Até cinco propriedades promovidas para monitoramento.

Aplicabilidade: filtragem previsível, detalhe do erro e histórico de tentativas. Limite: fuso local do navegador e escolha de fuso são documentados no ADF, mas para Orquestra constituem NOVO ESCOPO se ausentes no contrato. Timeout também não é requisito inferível. Autorefresh Orquestra necessita contrato próprio; não deduzir de referência.

### DOC-CTM01 — Control-M Navigation

URL: https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Navigation.htm

Data editorial: não explicitada; footer 2005–2025 não equivale à data de atualização. Aberto em 12/10/2026.

Documentado: Planning cria workspaces, folders e definições; Monitoring acompanha e controla fluxo ativo; Configuration administra servidores, agentes, perfis, usuários, roles e tokens.

Aplicabilidade: arquitetura de navegação distingue definição e execução; permissões governam disponibilidade de ações. Limite: página SaaS, não estabelecer equivalência visual com versões desktop antigas.

### DOC-CTM02 — Monitoring Navigation

URL: https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Monitoring_Navigation.htm

Data editorial: não explicitada. Aberto em 12/10/2026.

Documentado: alternância Map/List/Gantt; inspector com Summary, Waiting Info, Log e Output; Waiting Info explica eventos/recursos aguardados; ações mostram predecessores/sucessores; busca por nome, arquivo ou Run ID inclui histórico.

Aplicabilidade: estado bloqueado deve explicar causa e dependência, com navegação de vizinhança. Limite: ações de bypass, hold e set OK dependem de contrato operacional; não adicioná-las só por existirem no benchmark.

### DOC-CTM03 — Conditions management

URL: https://documents.bmc.com/supportu/ctrlm8/help/Main_help/en-US/Tools_Conditions.htm

Data editorial: não explicitada; versão histórica ctrlm8. Aberto em 12/10/2026.

Documentado: predecessor gera condição requerida pelo sucessor; condições podem ser externas/manuais; janela permite monitorar/filtrar condições; Auto Refresh é opção.

Aplicabilidade: apresentar dependência como condição verificável, incluindo causas externas. Limite: modelo de condições é específico Control-M; não presume que edges de Orquestra sejam eventos persistentes ou editáveis durante execução.

## Suplementos oficiais indexados — abertura retornou HTTP 403

Não contabilizar os itens abaixo entre as dez fontes abertas. Ferramenta de busca recuperou o conteúdo oficial indexado; chamada de abertura falhou. Servem como pistas documentais com ressalva explícita, não como observação direta ou leitura integral.

### DOC-INF02 — Scheduling a taskflow (Cloud Data Integration, novembro/2024)

URL: https://docs.informatica.com/content/dam/source/GUID-8/GUID-89D0C881-8DA9-4C78-A348-61C72A98256F/56/en/CDI_November2024_Taskflows_en.pdf

Consulta 12/10/2026. Trecho oficial indexado (página 135): publicar antes de agendar; mudanças não publicadas mantêm agenda na última versão publicada; unpublish impede disparos; Scheduled Jobs lista associações. Explore filtra Projects and Folders, Asset Types e Tags; Actions > Schedule abre associação a agenda existente ou nova. Remover associação durante execução deixa a execução concluir e cancela disparos adicionais. Limite: guia CDI novembro/2024 e leitura parcial. Útil para catálogo filtrável e indicação de versão publicada versus rascunho, a confirmar no contrato Orquestra.

### DOC-INF03 — Permissions (Cloud Data Integration, current-version)

URL: https://docs.informatica.com/integration-cloud/cloud-data-integration/current-version/asset-management/project-and-asset-management/permissions.html

Consulta 12/10/2026. Trecho oficial indexado: Read, Update, Delete, Execute e Change permissions; Update implica Read; Execute abrange monitorar/parar/reiniciar taskflows. Permissões não acompanham cópia/exportação. Limite: sem abertura integral e sem inventário de roles atuais. Útil para testar separação visualizar/editar/executar, sem declarar equivalência exata de RBAC.

### DOC-INF04 — Monitoring taskflow status with the status resource

URL: https://docs.informatica.com/integration-cloud/cloud-data-integration/current-version/taskflows/taskflows/monitoring-taskflow-status-with-the-status-resource.html

Consulta 12/10/2026. Trecho oficial indexado: requer privilégio de consultar resultados no Monitor; runId, status, usuário e subtarefas; paginação rowLimit máximo 50, padrão até 10; sem intervalo retorna últimas 24 horas. Limite: API documentada não comprova UX atual. UTC é contrato desse endpoint; escolha de fuso/normalização em Orquestra é NOVO ESCOPO quando não contratada.

## Controle de inferências

- Nenhuma referência comprova implementação, segurança, capacidade, atualização automática ou endpoints de Orquestra.
- Não copiar linguagens de expressão, scripts, chamadas API ou modelos de permissão de fornecedores.
- Versão publicada/rascunho, inspector, estados legíveis, identidade da execução e diagnóstico são padrões candidatos de UX.
- Reparo parcial, timeout, fuso selecionável, eventos externos, bypass e retenção ampliada requerem decisão explícita e backend; marcar novo escopo quando ausentes no contrato atual.

## Acréscimos desta rodada — terminologia e acesso

Consulta local: 12/10/2026, America/Sao_Paulo. Os links abaixo foram abertos ou verificados no navegador público; não representam teste de integração do Orquestra.

| ID | Fonte | Uso e limite |
|---|---|---|
| DOC-DB05 | https://docs.databricks.com/aws/en/getting-started/free-edition | Acesso gratuito e escopo pessoal; não valida plano empresarial |
| DOC-DB06 | https://docs.databricks.com/aws/en/getting-started/free-edition-limitations | Limites e uso não comercial; disponibilidade da UI não prova licença/capacidade |
| DOC-DB07 | https://docs.databricks.com/aws/en/getting-started/free-trial | Trial/créditos de 14 dias e diferença Express/Marketplace; não foi iniciado pelo agente |
| DOC-TERM01 | https://docs.databricks.com/aws/en/jobs/ | Job/task/trigger/DAG; léxico conceitual, sem transportar limites do fornecedor |
| DOC-TERM02 | https://docs.databricks.com/aws/en/ldp/ | Pipeline declarativa de dados é recurso distinto da orquestração de tasks |
| DOC-TERM03 | https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html | Instância, data lógica/intervalo e hora real; stable3.3.2 não comprova versão do motor atual |
| DOC-TERM04 | https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/tasks.html | Task e tentativa/estados; contrato Orquestra continua autoridade |
| DOC-TERM05 | https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Events.htm | Evento/prerequisito tem semântica específica, não equivalente a qualquer edge |
| DOC-TERM06 | https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Variables.htm | ODATE e data de ordenação; não traduzir automaticamente para data de execução |
| DOC-CTM04 | https://www.bmc.com/product-trials-demos.html | Entrada atual de demos; encaminha à biblioteca abaixo |
| DOC-CTM05 | https://www.bmc.com/landing/control-m-product-demos-rc.html | Biblioteca atual confirmada no navegador; Build a workflow abre cadastro GetStarted; tours ainda não liberados |

Correção de acesso: https://www.bmc.com/forms/control-m-trial.html apareceu em resultado indexado, mas no navegador atual retornou We're sorry. Não tratá-lo como cadastro válido. O formulário de parceiro iOne está publicado, porém a entrada principal BMC foi preferida. Nenhum cadastro, aceite, marketing ou contato externo foi enviado.
