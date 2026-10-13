> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Jornadas Databricks — Free Edition

Data: 12/10/2026. Estado: autoria e catálogo observados; operação demonstrativa DB-011/012, governança empresarial e Control-M guiado observado; motor real pendentes. Esta rodada acrescenta evidência direta à comparação antes apenas documental.

## Acesso, autorização e limites

O usuário abriu o workspace e autorizou a navegação. A UI identifica **Free Edition**. Há aviso de não suporte a controle automatizado do console, com indicação de navegação manual/Genie One MCP. Navegação normal funcionou; nenhuma detecção/proteção foi desativada ou contornada. A advertência foi registrada como limite de suporte, não como prova de acesso empresarial nem bloqueio total.

Jobs & Pipelines estava vazio. O usuário autorizou explicitamente criar **ORQ_UX_DEMO, duas tarefas fictícias, sem executar, sem agenda e sem conectar dados externos**. A criação persistiu no workspace. Essa exceção não autoriza alterações na organização Informatica.

Conteúdo demonstrativo: primeira condição literal `1 == 1`, segunda `2 == 2`; tarefas `avaliar_condicao` e `confirmar_dependencia`; segunda depende da saída true da primeira, com Run if dependencies = All succeeded. Não há notebook, script, consulta, dados ou conexão externa. O job ficou salvo; nenhuma chamada Run now/Run task, teste de conexão, retry ou repair foi acionada.

A Free Edition limita o que pode ser validado e tem uso não comercial conforme [documentação oficial](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations). A sessão serve como observação do ambiente aberto pelo usuário; a finalidade/licença para avaliação comercial premium precisa ser compatível. Não se infere RBAC, SSO, rede privada, SLA ou capacidade empresarial dessa edição.

## DB-J1 — Entrada, recursos e catálogo

**DB-001:** Home apresenta recursos, pesquisa global com atalho Ctrl+P, Workspace/Recents/Catalog, Jobs & Pipelines e Runs na navegação Data Engineering. Free Edition fica identificável no topo. Verificação de identidade não foi acionada; nenhum perfil foi exportado.

**DB-002:** Jobs & Pipelines reúne abas Jobs & pipelines/Runs; filtro por nome ou substring de ID; seletores All/Jobs/Pipelines e Owned by me/Accessible by me/Favorites. A lista inicial estava vazia. Cards Create distinguem Ingestion pipeline, ETL pipeline e Job.

**DB-009:** depois de criar/salvar, ORQ_UX_DEMO aparece no catálogo e pode ser filtrado pelo nome. Customize columns oferece Name, Type, Tags, ID, Run as, Created by, Tasks, Compute, Trigger, Trigger details e Recent runs. Nenhum checkbox de preferência foi alterado. Não foi testada persistência de customização entre sessões.

**Aplicabilidade:** descoberta contextual e filtros de escopo são referência útil para F2. “Owned” e “Accessible” são perspectivas, não prova de permissões. Colunas personalizáveis são candidato de apresentação premium, sem modificar definição/versão do pipeline.

## DB-J2 — Criar e nomear a demonstração

**DB-003:** escolher Job cria a entidade com nome inicial datado antes da primeira tarefa. Nome foi editado para ORQ_UX_DEMO e confirmado com Enter. Job details oferece autoria/run-as/descrição, Schedules & Triggers, parâmetros, tags, métricas de saúde, notificações, permissões e configurações avançadas.

**Observação:** a persistência ocorre em etapas; não há equivalência direta ao ciclo draft/save/publish do Orquestra. O catálogo posterior confirma descoberta do job criado. Não foi observado versionamento/publicação/lease concorrente do Databricks.

**Orquestra:** manter criação de rascunho explícita, sem ativar DAG. Melhorar reencontro na lista; não retirar a confirmação de versão porque a UI do fornecedor salva um Job de outra forma.

## DB-J3 — Tipos, campos e salvamento de tarefa

**DB-004:** formulário inicial Notebook mostra nome, tipo, source/path, compute, parâmetros/ambiente, notificações e políticas conforme tipo. O seletor apresenta diferentes famílias: notebooks/scripts/SQL/dbt/JAR, pipeline, Run Job, If/else condition, For each e outros. Alguns recursos dependem de edição/disponibilidade; AI Runtime apareceu desabilitado no seletor inicial. Listar uma opção não certifica execução nem licença.

A demonstração usou If/else condition para não depender de dados/compute. Campos mudaram para nome, operandos e operador. Save task persiste a alteração; ao terminar fica desabilitado. Run now tornou-se disponível, mas não foi acionado.

**Ponto forte:** tipo determina o formulário e separa configuração da ação operacional. **Dificuldade:** há forte densidade de opções e termos; uma taxonomia sem contexto pode confundir usuário novo. A presença de um tipo não justifica acrescentá-lo aos onze componentes do Orquestra.

## DB-J4 — Dependência e condição de execução

**DB-005:** Add a new task permite escolher outro tipo. A segunda condição foi configurada e salva. Depends on distingue a saída true e false da primeira condição; Run if dependencies apresentou All succeeded. O grafo mostra a conexão do ramo true, destaque da seleção e toolbar contextual de tarefa.

**Observação:** a aresta, o resultado da condição e a política de elegibilidade são conceitos diferentes. Nenhuma avaliação de condição foi executada. O desenho não é evidência de que a ramificação ocorreu em runtime.

**Orquestra:** preservar Decisão/Aguarde e seus contratos de ramos/casos/liberação. Explicar dependência/política no inspector, sem copiar All succeeded como tradução automática de outra regra. Seleção visual não substitui estado de execução.

## DB-J5 — Agenda e políticas em consulta

**DB-006:** Add trigger abriu Schedules & Triggers. Tipos visíveis: Scheduled, File arrival, Table update, Continuous e Model update. Scheduled oferece status Active/Paused e opções Interval/Schedule. A prévia mostrou intervalo temporal; **Cancel fechou sem Save e não adicionou trigger**. O formulário completo de calendário/fuso não foi confirmado; uma tentativa de selecionar Schedule não produziu mudança, e não houve insistência para forçar o controle.

**DB-007:** a lateral do job agrupa parâmetros, tags, saúde/limiares, notificações, permissões e Advanced settings. Foram lidos Queue e Maximum concurrent runs; nenhuma chave, política, permissão ou notificação foi alterada.

**Orquestra:** Configuração mantém organização própria. Oito agendas atuais são preservadas; gatilhos por arquivo/tabela/modelo, timeout/fuso selecionáveis e novas regras de health entram como escopo adicional quando não houver contrato. Queue/pool/concorrência não devem ser apresentados como conceitos idênticos.

## DB-J6 — Histórico sem executar

**DB-008:** aba Runs do job exibe ausência de corridas no intervalo padrão de 60 dias e oferece Run now. O job demonstrativo não foi executado, portanto não existem logs, tentativas, falha, repair ou transições reais a investigar nesta rodada.

**Aplicabilidade:** a definição e a lista de suas instâncias estão separadas. Estado vazio deve dizer o intervalo consultado. Histórico, identidade e reparo detalhados nos DOC-DB01/02 continuam informação documental; não viraram observação direta apenas porque a UI foi aberta.

## Composição e customização

A composição observada é canvas no corpo, formulário da tarefa abaixo e lateral com detalhes/políticas do job. Isso difere tanto do painel inferior do taskflow Informatica quanto do inspector lateral do contrato Orquestra. A melhor composição será decidida pela tarefa e pela largura útil, não pelo fornecedor escolhido.

O menu de colunas demonstra customização de **apresentação**. Não foi alterado nem avaliado seu armazenamento. Preferências de coluna/densidade/painel no Orquestra precisam de escopo, reset, persistência e governança próprios; não podem mudar execução, versão ou capacidades.

Não foram certificados desktop/mobile, tema claro, contraste, leitor de tela, performance ou fluxo com centenas de nós no Databricks. Dois nós não sustentam conclusão de escalabilidade.

## Comparação concreta que esta rodada acrescenta

| Pergunta | Informatica observado | Databricks observado | Direção Orquestra |
|---|---|---|---|
| Como encontro a definição? | Explore por projetos/tipos/busca | Lista jobs/pipelines com nome/ID e escopo | F2 índice e retomada, preservando cadastros |
| Onde ficam propriedades? | Taskflow painel inferior; Mapping Task consulta em seções | Task form abaixo do canvas e job sidebar | Contrato atual com inspector e Configuração; não duplicar |
| Como salvo? | Save visível/desabilitado; não ensaiado | Job criado antes de tasks; Save task ensaiado na demo | Draft/revisão/save/publish explícitos |
| O que é aresta? | Caminhos de taskflow; Uses separado | Depends on + resultado true/false + Run if | Diferenciar fluxo, regra e relação de asset |
| Onde investigo? | Monitor/All Jobs e Current Run reais | Runs vazio da demo | Contexto execução/snapshot/tentativa, sem criar histórico fictício |
| Como personalizo? | Filtros/painéis parcialmente lidos | Customize columns inventariado | Candidato premium de apresentação, contrato próprio |

## Pendências e prova necessária

- Confirmar governança/versão/publicação/concorrência em ambiente adequado; Free Edition não representa todos os recursos premium.
- Se necessário validar operação, obter autorização específica para executar uma fixture sem dados externos e com limites/custo/limpeza definidos. A criação atual não concede essa autorização.
- Observar Control-M em tour/trial, distinguindo demonstração guiada e uso real.
- Comparar terminologia e critérios no [glossário](../../geral/glossario-e-nomenclatura.md) e consolidar UX-11/12 antes do escopo premium final.
- Revalidar código e runtime do Orquestra; observação de fornecedor não certifica seu motor.

O job demonstrativo permanece como recurso do usuário para revisão. Não foi excluído nem desabilitado silenciosamente. Seu gatilho não foi cadastrado e o histórico consultado permanece vazio.



## Atualização operacional DB-011/012

O usuário ampliou expressamente a autorização para execução e estudo da Malha. DB-011: Run now gerou uma corrida real com Failed/RunExecutionError no catálogo e Skipped nas duas tarefas/detalhe, duração0s; eventos consultados não deram causa técnica conclusiva. Não atribuir a falha a quotas ou tipo sem evidência.

DB-012: criado ORQ_UX_FIXTURE, notebook Python com dois registros fictícios em memória, assert de contagem2/total30 e print; adicionada terceira tarefa validar_fixture, dependente do ramo true de confirmar_dependencia, Serverless. Segunda corrida Succeeded em17s, condições Succeeded (1s cada) e notebook Succeeded (14s). A saída confirma ORQ_UX_FIXTURE_OK: 2 registros ficticios; total=30. Não houve consulta a tabelas, arquivos externos, agenda ou alteração de permissões.

Inspecionadas Graph/Timeline/List da mesma corrida. Lista mostra status, tipo, recurso, duração e Depends on. Há Repair run/Repair task, mas nenhum reparo foi executado. Histórico inicial vazio (DB-008) continua evidência anterior à autorização; não representa o estado atual.

Isso comprova a fixture e o caminho de monitoramento desta edição. Não certifica processamento empresarial, falha controlada/retry/repair, concorrência, SLA ou versão premium. [Prova visual](../../evidencias/DB-012-execucao-fixture.jpg).
