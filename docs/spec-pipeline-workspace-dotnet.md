# Espaço de trabalho de Pipeline e gestão em .NET
Data: 2026-10-09 · Status: direção e continuidade autorizadas; detalhamento técnico no DEV · Projeto: ORQUESTRA

## 1. Visão
Concentrar criação, montagem, configuração, publicação e investigação no espaço de trabalho de Pipeline, seguindo a direção visual dos mockups aprovados na conversa. Retirar os menus Etapas e Fluxos quando suas funções estiverem acessíveis dentro do Pipeline. Manter React e migrar a gestão progressivamente para .NET, preservando Airflow, DataStage, SQL e jobs Python/PySpark.

Esta especificação cobre o primeiro piloto de Pipeline. A nova experiência de Malha e o assistente de linguagem natural são projetos subsequentes, apoiados nos contratos desta entrega.

## 2. Escopo
**IN**
- Lista de pipelines, criação simples e espaço de trabalho contextual.
- Abas Visão geral, Fluxo, Execuções, Parâmetros e Versões. Dados e qualidade reaproveita recursos existentes; não promete novas regras nesta entrega.
- Montagem e leitura da execução no mesmo contexto, mantendo edição de etapas em lista como opção interna.
- Backend .NET modular para rascunhos, versões, bloqueio de edição e intenção de publicação.
- Definição estruturada do fluxo, contratos de compatibilidade e adaptador para o motor atual.
- Preservação de permissões, parâmetros, identidade dos pipelines, agenda, condições e data de referência.
- Piloto atrás de flag e integração por PR em develop, com validação no DEV.

**OUT**
- Reescrever jobs Python/PySpark ou substituir Airflow.
- Migrar todos os módulos FastAPI, autenticação corporativa ou banco de dados.
- Redesenhar Caixa Seguro, chamados, BI e administração.
- Implantar cluster Spark/Kubernetes, garantir capacidade sem benchmark ou aumentar concorrência global.
- Criar novos conectores, regras de qualidade ou importadores apenas porque aparecem nos mockups.
- Publicação de IA sem revisão, execução de código gerado por IA ou acesso de IA a segredos.
- Promover para main ou implantar em produção sem autorização própria.

## 3. Base técnica e arquitetura
Base de implementação: develop, SHA observado 6e711e54e5883fb6d66edf13dfc1fe229df19c45. Revalidar HEAD e árvore antes de cada fase; não reservar números de migrations agora.

Arquivos existentes:
- ui-react/src/App.tsx: rotas atualmente derivadas do registro NAV.
- ui-react/src/lib/nav.ts: menus e recursos RBAC.
- ui-react/src/pages/Pipelines.tsx: listagem e cadastro.
- ui-react/src/pages/Jobs.tsx: lista e ações de etapas.
- ui-react/src/pages/Fluxos.tsx: abertura do editor e contexto de execução.
- ui-react/src/components/etapas/FluxoEditor.tsx: canvas e modo execução.
- ui-react/src/components/etapas/JobTypeFields.tsx: configurações por tipo.
- ui-react/src/lib/api.ts: base /orquestra, bearer, tratamento de 401 e erros.
- api/deps.py: sessão e permissões existentes.
- api/routers/pipelines.py, jobs.py, execucoes.py e factory.py: integração atual.
- api/services/dag_reconcile.py e dags/etl_dag_factory.py: publicação e geração.
- sql/migrate.py, docker-compose.dev.yaml e docs/fluxo-desenvolvimento.md: migrations e DEV.

Estrutura proposta, ainda não criada:
- backend-dotnet/Orquestra.Api: endpoints e compatibilidade de autenticação.
- backend-dotnet/Orquestra.Application: comandos, validação e publicação.
- backend-dotnet/Orquestra.Domain: rascunhos, versões, leases e estados.
- backend-dotnet/Orquestra.Infrastructure: SQL Server, sessão, reconciliação e adaptador.
- backend-dotnet/Orquestra.Tests: testes de domínio, contratos e integração.
- ui-react/src/pages/PipelineWorkspace.tsx e components/pipeline-workspace/: contexto e componentes da nova experiência.

A versão suportada do SDK/runtime .NET será fixada antes da F1, após conferir a política da equipe e disponibilidade de imagem/runtime no DEV e no ambiente offline. Não instalar runtime no host de produção como parte deste piloto.

### Responsabilidades
.NET controla exclusivamente as tabelas novas de rascunho/versão e a intenção de publicação. FastAPI mantém os módulos ainda não migrados. O motor atual continua executando a projeção publicada nas tabelas etl_* existentes.

Um endereço público e sessão existentes permanecem para o usuário. O proxy encaminha /orquestra/workspace/* ao .NET; os demais caminhos continuam no backend atual. O navegador não escolhe serviço nem recebe credencial de serviço.

A autenticação .NET deve validar a sessão persistida e carregar os mesmos recursos de api/deps.py, incluindo expiração, revogação e usuário inativo. Não assumir que o bearer atual é JWT. Compatibilidade exata deve ser testada antes de habilitar gravação.

Não modificar diretamente o FluxoEditor para apontar ao rascunho sem mapear suas chamadas: o editor existente grava configuração ativa. Introduzir uma interface de acesso ao fluxo e testar todos os caminhos de escrita. Modo rascunho só será editável quando nenhuma operação alcançar o cadastro publicado.

## 4. Modelo de dados e contratos
Nomes propostos; larguras de identificadores e collation devem corresponder às tabelas existentes, sem truncamento ou mudança de caixa.

- etl_workspace_rascunho: draft_id uniqueidentifier PK; pipeline_name com tipo/largura compatíveis; base_version_id nullable; definition_json nvarchar(max); layout_json nvarchar(max); revision bigint; estado; criado_por; responsavel; criado_em/atualizado_em datetime2 UTC.
- etl_workspace_versao: version_id uniqueidentifier PK; pipeline_name; numero int; definition_json; layout_json; content_hash; criada_por; criada_em. Unique pipeline/numero. Conteúdo imutável.
- etl_workspace_lease: draft_id uniqueidentifier PK/FK; holder_user; holder_session_hash; fence bigint; expires_at datetime2 UTC. Nenhum token de sessão em claro.
- etl_workspace_publicacao: operation_id uniqueidentifier PK; version_id; pipeline_name; expected_active_hash; estado; tentativas; erro_resumido; timestamps.
- etl_workspace_evento: event_id bigint; entidade/id; ator; ação; revision; operation_id; timestamp e detalhe sem segredos.

Migrations idempotentes separadas para schema e versão pública da aplicação, com o próximo número livre de develop no momento da implementação. Leitura indisponível retorna capacidade desabilitada; escrita sem schema retorna 503 com a migration necessária. Não criar DDL durante request.

### Definição do pipeline
schemaVersion, identidade, metadados, agenda, parâmetros, nós tipados, arestas, condições, referências a conexões, tentativas e limites. Layout visual separado. Segredos nunca entram no JSON; apenas identificadores de conexão.

O contrato preserva exatamente a semântica dos tipos existentes. Nós/configurações não suportados pelo piloto tornam o pipeline somente leitura e exibem o motivo; não remover nem normalizar silenciosamente campos desconhecidos.

### Endpoints propostos
- GET /workspace/capabilities: funcionalidades habilitadas e versões do contrato.
- GET /workspace/pipelines/{nome}: visão contextual, publicado e rascunho.
- POST /workspace/pipelines: cria identidade e rascunho sem DAG nem agendamento ativo.
- POST /workspace/pipelines/{nome}/drafts: cria rascunho da configuração publicada.
- GET /workspace/drafts/{id}: definição, revisão e informação de edição.
- PUT /workspace/drafts/{id}: salva exigindo revisão e lease vigente.
- POST /workspace/drafts/{id}/lease: aquisição/renovação atômica.
- DELETE /workspace/drafts/{id}/lease: libera a sessão de edição.
- POST /workspace/drafts/{id}/transfer: transferência administrativa auditada.
- POST /workspace/drafts/{id}/validate: diagnósticos por nó/campo.
- POST /workspace/drafts/{id}/publish: persiste intenção; retorna 202 e operation_id.
- GET /workspace/publications/{id}: resultado e reconciliação.
- GET /workspace/pipelines/{nome}/versions: versões e comparação.

Erros mantêm detail compatível com apiFetch e código estável: 401 sessão, 403 permissão, 409 revisão/lease/configuração divergente, 422 validação, 503 dependência indisponível. Mensagens em português.

### Edição e publicação
Um rascunho ativo por pipeline no piloto, vários leitores autorizados e uma sessão de edição. Lease padrão de 120 segundos, renovado a cada 30 segundos; tempos configuráveis. Hora e validade são decididas pelo servidor. Cada posse recebe fence crescente; uma sessão antiga não recupera escrita após transferência. Dados salvos não expiram com a lease.

Rascunho possui revision para evitar sobrescrita por aba antiga, IA ou outra sessão. Salvar exige ator autorizado, lease e revisão. Transferência exige administrador; solicitar transferência na UI apenas explica o procedimento, sem criar canal de mensagens nesta fase.

Importar a configuração atual cria uma versão base identificada como importada, sem afirmar que todas as execuções históricas têm versão conhecida.

Publicar cria versão imutável e operação durável. O adaptador valida novamente e aplica projeção em transação, com comparação do hash ativo. Uma publicação interrompida é reconciliada por operation_id; repetir o comando não cria nova versão ou DAG.

Publicação e execução têm relógios distintos: só mostrar Publicado quando a geração/reconciliação confirmar a versão esperada. Guardar hash/version_id nos artefatos e parâmetros de execução para rastreio.

O motor atual não foi comprovado para execução simultânea de múltiplas versões do mesmo pipeline. Neste piloto, bloquear publicação enquanto houver execuções ativas ou comandos de disparo pendentes; serializar disparo/publicação e testar a corrida. Alterações legadas em pipelines geridos pelo piloto são bloqueadas no servidor. Execuções existentes continuam sendo consultadas.

Retornar a versão anterior cria nova operação de publicação, mantendo as mesmas guardas; reverter a flag da UI não reverte schema ou artefatos automaticamente.

## 5. Experiência e navegação
Rotas propostas /pipelines/novo e /pipelines/:nome/* com nome codificado e identidade original preservada. Lista atual permanece em /pipelines.

Criação pede o essencial. Nome amigável é separado do identificador técnico; não renomear pipelines existentes nem seus dag_ids. Fluxo em branco é o único modelo novo obrigatório no piloto; importar usa recursos atuais somente quando compatíveis.

Workspace: cabeçalho com ambiente, versão, responsável e estado; abas contextuais; canvas com biblioteca e propriedades; lista de etapas acessível internamente; eventos/logs no contexto de execução. Não apresentar métricas previstas ou percentuais sem fonte real.

Tokens semânticos existentes, modo claro e escuro, navegação por teclado, foco e erros por campo. Não transportar informações essenciais apenas por cor.

Preservar regras tela_pipelines/tela_jobs e acao_editar/acao_executar: a união visual não amplia permissão. Pipeline pode ser visível enquanto suas ações de etapa estão negadas.

Após a paridade funcional, retirar /jobs e /fluxos do menu, preservando rotas de compatibilidade fora do registro NAV, com guards próprios. Links com pipeline/job/modo/data/de mantêm o contexto; link sem pipeline abre seleção no workspace. Busca global abre o objeto selecionado.

### Perfis de uso e permissões
O piloto atende desenvolvimento, consulta e sustentação desde sua primeira entrega utilizável. Perfil de experiência escolhe a aba inicial; permissões por ação continuam sendo autoridade no servidor. Usuário pode acumular responsabilidades sem receber privilégios implicitamente.

| Experiência | Entrada preferencial | Recursos essenciais |
|---|---|---|
| Desenvolvimento | Fluxo em Montagem | Rascunho, parâmetros, validação e versões |
| Consulta | Visão geral publicada | Descrição, responsáveis, fluxo e dependências |
| Sustentação | Execuções | Data operacional, bloqueios, logs e runbook |

Consultar definição, consultar logs/dados autorizados, editar, publicar, executar, cancelar, reprocessar e administrar são capacidades separadas. Mapear para o RBAC real antes de criar recursos; não inferir autorização pelo nome do perfil. Operador sem editar pode reprocessar se autorizado; editor sem publicar não promove versão.

Critérios comuns: testar os três percursos, usuário com funções acumuladas e negativa de cada ação pela API; não exibir segredos na consulta. Retirada de Etapas/Fluxos mantém acesso equivalente para cada público.

### Preparação para monitores, capacidade e conhecimento
A fundação reserva identificadores e eventos para evolução futura, sem incluir novas telas de monitoramento ou Academy no piloto.
- Execuções distinguem previsto_em, dependencias_liberadas_em, enfileirado_em, iniciado_em e concluido_em. Campo indisponível é nulo com origem informada, nunca estimado como fato.
- Registrar motor, pool/fila, executor e identificador de tentativa quando a fonte os fornecer. Não chamar limite de tarefas do worker de limite de pipelines.
- Relacionar runbooks e ajuda por identificador estável de pipeline/componente; textos sensíveis seguem RBAC.
- Definições e eventos trazem schemaVersion, versão publicada e correlação; armazenamento histórico tem política explícita de retenção antes de ampliar coleta.

## 6. Fases
Cada fase tem PR própria para develop, revisão adversarial antes da PR e deploy/smoke no DEV quando altera comportamento. Dividir fases grandes em PRs menores que permaneçam funcionais.

### F1 Fundação e contratos
Entregar contrato versionado, mapa de funções de Jobs/Fluxos, projeto .NET com saúde/readiness, validação de sessão/RBAC e roteamento DEV. Nenhuma edição ativa nem remoção de menus.
Aceite: matriz dos três públicos e capacidades é documentada; sessão expirada/inativa é recusada; ações negadas não aparecem nem são aceitas; API atual continua funcional; ausência do .NET não afeta módulos antigos.

### F2 Rascunhos e edição concorrente
Entregar schema, importação fiel, CRUD, revision, lease e auditoria.
Aceite: dois usuários não adquirem lease simultânea; posse antiga não salva; perda de conexão preserva dados; rascunho não modifica tabelas ativas.

### F3 Workspace e criação
Entregar criação simples, cabeçalho, abas e modos com acesso desacoplado do editor.
Aceite: desenvolvimento, consulta e sustentação abrem o contexto adequado sem ampliar permissão; criação abre rascunho; outro usuário consulta sem editar; todos os tipos usados no piloto preservam configuração; modo consulta não grava nem altera layout.

### F4 Validação e publicação
Entregar versões, comparação, adaptador e reconciliação.
Aceite: publicação repetida é idempotente; reinício retoma intenção; DAG/hash são conferidos; publicação com execução ativa é recusada; escrita legada no pipeline gerido é recusada.

### F5 Operação contextual e retirada de menus
Entregar execuções, logs, lista interna, busca contextual e redirects.
Aceite: funções inventariadas têm destino e permissão equivalentes; links antigos preservam contexto; menus Etapas/Fluxos desaparecem apenas para o grupo habilitado; UI informa capacidades reais.

### F6 Piloto e consolidação
Entregar evidências funcionais, orçamento de desempenho medido, roteiro offline e recuperação.
Aceite: criação até execução funciona no DEV, falhas e concorrência são exercitadas, aplicação antiga continua operacional e candidato é identificado por SHA. Limites de DataStage simulado são registrados.

### Validação comum a todas as fases
- Frontend: tsc -b, lint comparado com base da PR, build e dist recompilado por último.
- Backend legado: pytest comparado com base; registrar skips e executar testes SQL reais quando relevantes.
- .NET: build, testes de domínio/contrato e integração SQL Server; falhas/reinícios/publicação concorrente testados.
- Sem bytes NUL em fontes; migrations idempotentes; compatibilidade de payloads com casos reais anonimizados.
- Revisão adversarial e de segurança quando toca sessão, entrada, execução ou segredos.
- Smoke de tema claro/escuro, permissões, teclado, estados vazios/erro e fluxos grandes.
- Nenhuma fase recebe status concluída apenas por screenshot ou teste simulado.

## 7. Riscos e mitigações
| Risco | Impacto | Mitigação |
|---|---|---|
| Editor grava no publicado enquanto mostra rascunho | Alteração operacional indevida | Desacoplar acesso e testar toda escrita |
| Dois backends alteram o mesmo pipeline | Perda de atualização | Proprietário único por estado e guardas no legado |
| Publicação interrompida | Banco e DAG divergentes | Intenção durável, hash e reconciliação |
| Lease antiga volta após transferência | Sobrescrita de alterações | Fence crescente e revisão obrigatória |
| Unificação de telas amplia RBAC | Acesso indevido | Guards de tela/ação e testes de negativa |
| DEV compartilha VPS com outros serviços | Saturação ou interrupção | Inspeção de recursos e alterações só em serviços necessários |
| Ambiente offline sem runtime/dependências | Instalação indisponível | Artefatos .NET versionados e ensaio de instalação offline |
| Versão publicada muda durante execução | Comportamento inconsistente | Guarda operacional e serialização até suporte comprovado |

## 8. Smoke pós-deploy
a) Conferir SHA, versão visível, saúde dos serviços e migrations.
b) Entrar como desenvolvedor, leitor e sustentação; conferir abas iniciais, papéis acumulados e negativas na UI/API.
c) Criar pipeline novo e conferir que nenhuma DAG é disparada.
d) Abrir com dois usuários e conferir bloqueio, expiração e revisão.
e) Salvar rascunho e verificar configuração publicada intacta.
f) Validar erro de conexão/parâmetro e localizar etapa no canvas.
g) Publicar pipeline ocioso; conferir operação, hash, DAG e versão.
h) Reiniciar reconciliador durante publicação e confirmar resultado único.
i) Executar carga de teste SQL/Python e investigar etapa/log sem sair do contexto.
j) Tentar publicar durante execução e obter conflito explícito.
k) Testar links antigos, permissões e retirada dos menus no grupo piloto.
l) Desabilitar piloto e conferir consultas antigas; não presumir rollback dos dados.

## 9. Evoluções seguintes
Malha recebe especificação própria: versões de composição e dependências, travas independentes, referências explícitas a pipelines e tratamento de dependências globais hoje compartilhadas entre malhas. Não atribuir isolamento por malha ao modelo global existente.

IA recebe especificação própria: proposta de alteração no mesmo contrato, contexto autorizado, revisão visual, validation e revision; aplicação exige lease e permissão do usuário. Sem execução/publicação autônoma.

Python/PySpark permanecem motores de processamento. Escala futura mede fila, latência de disparo, memória, CPU, I/O e limites das fontes; runtime da aplicação não recebe cargas pesadas.

### Monitores estratégico e operacional
Evolução própria após Pipeline e Malha. Estratégico acompanha entregas/serviços de negócio, SLA, qualidade e impacto; operacional acompanha execuções, dependências, filas, falhas e recuperação. Mesmos dados, granularidades diferentes.
Cadastrar compromisso de entrega, calendário, prazo, responsável e relação com pipelines/consumidores antes de calcular aderência.
Navegação contextual: entrega → malha → pipeline → etapa/log. Painel de sala é somente leitura, mostra última atualização e degradação da fonte.

### Capacidade por horário e apoio ao agendamento
Primeiro entregar coleta confiável e histórico; depois recomendar horários.
Conferir no DEV e na configuração-alvo quantos workers existem, concorrência efetiva, pools, filas e limites externos. O valor 50 observado em worker_concurrency não prova 50 pipelines simultâneos.
Medir concorrência por tarefa/recurso, fila, espera por dependência, espera por capacidade e duração. Mapa de calor por dia/horário, curva ocupação/fila e timeline detalham as cargas sobrepostas.
Desenvolvimento compara janelas e impacto da nova carga; consulta vê janela/risco da entrega; sustentação identifica recurso bloqueador e ações autorizadas.
Simulação usa histórico ou duração explicitamente estimada para pipeline novo, calendário, paralelismo, dependências e prazo. Exibir amostra, período, confiança e data da previsão. Sem amostra suficiente, informar ausência de recomendação.
Não otimizar apenas pela faixa vazia, prometer início exato ou sugerir aumento automático de concorrência. Testar horários operacionais, dias úteis, cargas atípicas, indisponibilidade e mudanças de capacidade.

### Academy e comunidade
Evolução futura, sem fórum/LMS nesta entrega. Prever trilhas por perfil, artigos versionados, runbooks, exemplos, modelos e perguntas/respostas.
Conteúdo usa IDs estáveis, autor, responsável por revisão, versão aplicável, data de revisão e acesso. Distinguir contribuição comunitária de orientação validada.
Ajuda contextual acompanha agendamento, montagem e investigação. Busca futura relaciona objetos técnicos e conteúdos autorizados.
IA consulta somente conhecimento autorizado, cita fonte/versão e não transforma resposta comunitária em regra de execução.

### Ordem das entregas seguintes
1. Workspace de Pipeline e fundação .NET (F1–F6 desta spec).
2. Workspace de Malha e composição versionada.
3. Monitor operacional e histórico de capacidade por recurso/horário.
4. Monitor estratégico por entrega e recomendação de agendamento baseada no histórico.
5. Assistente de montagem por linguagem natural sobre o contrato já validado.
6. Academy e comunidade, aproveitando ajuda contextual e runbooks desde as fases anteriores.
Coleta e IDs necessários às etapas seguintes são considerados nos contratos da F1; implementação de cada produto recebe spec própria.

## 10. Condições para execução
- Confirmar acesso atual ao DEV e caminho da cópia de trabalho.
- Conferir SDK/runtime .NET e disponibilidade offline antes de F1.
- Registrar baseline real da branch develop e estado do DEV.
- Escolher pipeline de teste sem dados sensíveis com cenários SQL/Python e amostra DataStage.
- O usuário autorizou ajuste da documentação e continuidade em 2026-10-09. Conferir divergências da base/ambiente e detalhar o plano de F1 no servidor antes de escrever código. Alterações de escopo ou regras operacionais devem ser apresentadas para revisão.
