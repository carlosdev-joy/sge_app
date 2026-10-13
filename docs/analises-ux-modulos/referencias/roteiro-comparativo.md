> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Validação prática Databricks e Control-M

Data: 12/10/2026. Escopo adicional solicitado pelo usuário: validar as mesmas jornadas também nessas ferramentas antes de fechar a estrutura premium/customizável. Este roteiro preserva a análise Informatica como primeira rodada e separa evidência prática de documentação.

## Acessos oficiais e limites

| Produto | Acesso | Limites relevantes |
|---|---|---|
| Databricks Free Edition | [Cadastro](https://login.databricks.com/?dbx_source=docs&intent=CE_SIGN_UP), [descrição](https://docs.databricks.com/aws/en/getting-started/free-edition) | Gratuito, uso não comercial; serverless/quota, até cinco tarefas de job concorrentes, sem equivalência ao plano empresarial |
| Databricks trial | [Trial oficial](https://docs.databricks.com/aws/en/getting-started/free-trial), [Express setup](https://docs.databricks.com/aws/en/getting-started/express-setup) | Créditos por 14 dias; Express sem conta prévia de nuvem; pagamento/Marketplace podem converter para cobrança conforme contrato |
| Control-M | [Biblioteca atual de tours](https://www.bmc.com/landing/control-m-product-demos-rc.html), [entrada oficial](https://www.bmc.com/product-trials-demos.html), [documentação do trial](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Free_Trial.htm) | Trial/tours não equivalem a edição gratuita permanente. O antigo /forms/control-m-trial.html retornou We're sorry; a biblioteca atual exige formulário Get Started para liberar demos. Duração/elegibilidade de trial real não foram assumidas |

Fontes consultadas oficialmente em 12/10/2026. [Limitações da Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) restringem uso comercial e não certificam RBAC/SSO/rede privada premium. A disponibilidade de um tipo na UI não garante licença nem execução. Cadastro/credenciais/aceite de termos são feitos pelo usuário; nenhum dado de organização foi transferido.

## Estado atual do acesso

Databricks foi aberto pelo usuário e identificado na UI como Free Edition. Home e Jobs & Pipelines foram acessados por navegação normal. A página exibe aviso de não suporte a controle automatizado e sugere navegação manual/Genie One MCP; não foram alteradas detecção ou proteções. O link normal funcionou, portanto o aviso não foi descrito como bloqueio total. Restrições efetivas serão registradas se ocorrerem.

Inicialmente a lista estava vazia. O usuário autorizou expressamente criar **ORQ_UX_DEMO com duas tarefas fictícias, sem execução, sem agenda e sem dados externos**. Essa autorização é específica dessa demonstração Databricks; não altera os limites da organização Informatica. A jornada e seu estado final são registrados em `10-jornadas-databricks.md` ao concluir a verificação.

O usuário liberou a biblioteca. Foram percorridos os tours Build a workflow (25 etapas), Error handling (15) e Reference folder (13), incluindo Planning e Monitoring guiados. Nenhum motor real foi executado. Ver documento11.

## Roteiro comum de comparação

| Cenário | Pergunta | Databricks | Control-M | Evidência mínima |
|---|---|---|---|---|
| Encontrar definição | Consigo pesquisar por nome/ID, filtrar e retornar sem perder contexto? | Jobs & Pipelines / Workspace | Planning / folders / workspaces | Tela+ação+resultado, filtros e contexto |
| Distinguir objeto | Job, task e pipeline têm qual responsabilidade? | Lakeflow Job vs task vs pipeline de dados | Folder/job/workflow | Glossário com fonte e exemplos |
| Ler desenho | Seleção/zoom/localizador preservam contexto? | Tasks/DAG | Map/Planning | Canvas genérico e propriedade selecionada |
| Configurar tarefa | Principais/avançados/validação são agrupados como? | Task form/type/source/depends/run-if | Job properties | Campos sem valores confidenciais |
| Configurar fluxo | Agenda/parâmetros/política ficam fora do canvas? | Job details / Schedules & Triggers | Folder/job scheduling | Separar responsabilidade de UI e contrato |
| Salvar definição | Mudança persiste automaticamente ou por save? | Demo autorizada, sem Run | Apenas leitura até autorização própria | Estado antes/depois e efeito exato |
| Explorar dependência | Aresta é condição de execução ou relação de asset? | Depends on / Run if | Events / resources / predecessors | Fonte, semântica e limites |
| Retomar trabalho | Há published/draft/checkout/version? | Conferir fonte de deployment/bundle | Planning/Check-in/deploy quando acessível | Não assumir equivalência ao Orquestra |
| Ver histórico | Qual instância e filtros estão selecionados? | Runs/job runs | Monitoring/Viewpoint | Identidade sanitizada e estado vazio/real |
| Investigar tentativa | Log/erro/output mantêm task/run/attempt? | Task run details/repair history | Log/Output/Waiting Info | Fixture sem dados corporativos |
| Entender bloqueio | O que espera e qual dependência falta? | Estado/Run if/queue | Waiting Info/events/resources | Explicação, não só cor |
| Customizar visão | Colunas/painéis/densidade/visões são preferências ou definição? | UI disponível na edição | Viewpoint/map/list/Gantt | Efeito/persistência/limite de licença |
| Operar por teclado | Foco/localizador/Escape/atalhos têm alternativa ao drag? | Superfícies existentes | Superfícies existentes | Cenário repetível; sem delete mutante |
| Responsividade | Existe canvas realmente útil em larguras contratadas? | 1440/1280/947/390 quando permitido | Mesmas larguras quando permitido | Não confundir ausência de overflow com tarefa concluída |

Histórico vazio não será preenchido por uma execução automática. Se for necessário produzir corridas, preparar fixture/literal, limite de custo, isolamento e limpeza e obter autorização específica **para executar** antes de qualquer Run/Test/Repair. Na demonstração atual, apenas criação está autorizada.

## Fechamento da estrutura customizável premium

O fechamento deve conter: decisão por comportamento; termos canônicos; evidência prática/documental; classificação SPEC/preservação/melhoria/novo escopo; componente reutilizado; custo/risco; e critério verificável. Não copiar cores, código, regras de negócio ou modelos proprietários.

Para cada preferência candidata (colunas, zoom, painel, densidade, filtros, visão salva), registrar: escopo usuário/projeto; duração sessão/persistente; reset; comportamento em largura estreita; compatibilidade com versionamento; ausência de segredos; e dependência de permissão. O núcleo de execução não muda porque a interface foi personalizada.

Pendências de acesso viram lacunas explícitas. Tours são demonstrações guiadas; não comprovam motor, colaboração, RBAC empresarial ou desempenho real. O escopo premium não será declarado fechado até revisão do usuário após Databricks/Control-M e aceites do Orquestra.



## Atualização após autorização de execução e estudo da Malha

O estado atual inclui DB-011/012: primeira tentativa real falhou com tarefas puladas; segunda, com notebook fictício adicional, concluiu Succeeded em17s e mostrou total30. Graph/Timeline/List foram inspecionados. As declarações anteriores de histórico vazio/ausência de execução descrevem a rodada inicial. Repair/retry, carga e RBAC premium continuam não ensaiados.

Control-M CTM-006–010 inclui cinco tours guiados: Build a workflow, Error handling, Reference folder, Forecast e Self-Healing. As pendências anteriores de liberação estão resolvidas. Sem console operacional, nenhum job real Control-M foi executado. A nova proposta de composição, configuração, operação, recursos e governança está em [12-malha-conceitos-e-reestruturacao.md](../modulos/malhas/conceitos-e-reestruturacao.md); amplia o estudo, sem reclassificar recursos novos como SPEC Pipeline existente.
