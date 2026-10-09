# Espaço de trabalho de Pipeline e gestão em .NET
Data: 2026-10-09 · Status: rascunho para revisão · Projeto: ORQUESTRA

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

## 6. Fases
Cada fase tem PR própria para develop, revisão adversarial antes da PR e deploy/smoke no DEV quando altera comportamento. Dividir fases grandes em PRs menores que permaneçam funcionais.

### F1 Fundação e contratos
Entregar contrato versionado, mapa de funções de Jobs/Fluxos, projeto .NET com saúde/readiness, validação de sessão/RBAC e roteamento DEV. Nenhuma edição ativa nem remoção de menus.
Aceite: sessão expirada/inativa é recusada; ações negadas não aparecem nem são aceitas; API atual continua funcional; ausência do .NET não afeta módulos antigos.

### F2 Rascunhos e edição concorrente
Entregar schema, importação fiel, CRUD, revision, lease e auditoria.
Aceite: dois usuários não adquirem lease simultânea; posse antiga não salva; perda de conexão preserva dados; rascunho não modifica tabelas ativas.

### F3 Workspace e criação
Entregar criação simples, cabeçalho, abas e modos com acesso desacoplado do editor.
Aceite: criação abre rascunho; outro usuário consulta sem editar; todos os tipos usados no piloto preservam configuração; modo consulta não grava nem altera layout.

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
b) Entrar como editor e leitor; validar ações permitidas/negadas.
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

## 10. Condições para execução
- Confirmar acesso atual ao DEV e caminho da cópia de trabalho.
- Conferir SDK/runtime .NET e disponibilidade offline antes de F1.
- Registrar baseline real da branch develop e estado do DEV.
- Escolher pipeline de teste sem dados sensíveis com cenários SQL/Python e amostra DataStage.
- Revisar esta especificação antes de escrever o plano detalhado e implementar.
