# Plano F1 — Fundação e contratos do workspace de Pipeline

Data: 2026-10-09. Estado: proposta para revisão; implementação não iniciada.

## Base, isolamento e referências

- Checkout servido: `/opt/orquestra-dev`, branch `develop`, HEAD e `origin/develop` em `6e711e54e5883fb6d66edf13dfc1fe229df19c45`. Árvore limpa na inspeção e na conferência posterior.
- Worktree: `/root/orquestra-workspace-f1`, branch `feat/pipeline-workspace-f1`, criada de `origin/develop`. Não copiados `.env`, tokens ou credenciais. Dependências Node existentes copiadas para a worktree para evitar instalar ou escrever no checkout servido.
- Referência documental: `origin/docs/pipeline-workspace-dotnet`, SHA `9fec0ae23bf57cef321f030b3bb8c3d3f6e8af4c`. Os três documentos solicitados e `docs/mockups/pipeline-workspace/` foram transportados para esta worktree, sem merge de código da branch documental.
- Lidos `CLAUDE.md`, `docs/fluxo-desenvolvimento.md`, `docs/ambiente-dev.md`, instruções do segundo-cérebro, ficha Orquestra e orientações locais de especificação/testes. Não encontrados AGENTS.md adicionais na árvore versionada do projeto nem nos diretórios ancestrais aplicáveis consultados. A instrução AGENTS fornecida pelo usuário continua aplicável.
- O roteiro menciona writing-plans e skill de worktrees, mas não foi localizado arquivo dessas skills nos catálogos locais consultados. Este documento concretiza o plano com arquivos, contratos, comandos e aceites; não afirma ter executado essas skills.

Os quatro PNGs foram abertos e inspecionados: execução, montagem, Malha e criação. Preservar cabeçalho contextual, abas, canvas, biblioteca lateral, propriedades e área inferior de eventos/validação. A F1 não implementa interface nova. Ambiente lateral deve acompanhar o contexto; parâmetros de execução ficam somente leitura; progresso/previsão exigem fonte real. Malha, novos modelos de criação e novos componentes de qualidade não entram por aparecerem nas imagens.

## Resultado da F1 e limites

Entregar uma API .NET modular, isolada e inicialmente somente leitura, com contrato versionado de fluxo/capacidades, autenticação equivalente, saúde/readiness e roteamento exclusivo no DEV. React, FastAPI, Airflow, SQL, DataStage e jobs Python/PySpark permanecem na arquitetura aprovada.

F1 não cria tabelas de rascunho/versão/lease, não habilita salvar/publicar pelo .NET, não altera DAGs, não remove Etapas/Fluxos e não muda a autenticação corporativa. Escritas e experiência completa começam nas fases correspondentes. Tudo parte de develop; nenhuma promoção para main ou alteração de produção está autorizada.

## Evidências do ambiente

| Item | Resultado observado |
|---|---|
| Serviços Compose DEV | 11 containers ativos: UI, API, webserver/worker/scheduler/triggerer Airflow, SQL Server, Postgres, Redis, SSH e API DataStage de amostra; serviços com healthcheck reportaram healthy |
| Proxy Swarm DEV | `orquestradev_proxy`, 1/1 |
| Saúde via UI | `GET http://127.0.0.1:8090/orquestra/health`: HTTP 200, status ok |
| Versão pública no SQL | `app_version=2.6.0`, release E-mail: valor de cada coluna do SQL |
| Versão de /health | `0.3.0`; não representa a versão pública e não serve como prova de release |
| Ferramentas | Node 22.18.0, npm 11.5.2, Python e Docker disponíveis; dotnet não encontrado; nenhuma imagem local dotnet/aspnet encontrada |
| Capacidade pontual | RAM 31 GiB, disponível 17 GiB, swap usada 0; disco livre 254 GiB. Não constitui benchmark |
| Uso pontual DEV | API ~185 MiB, SQL ~3,3 GiB, worker ~2 GiB, UI ~19 MiB; CPU baixa na amostra |
| SQL Server | Collation servidor/banco `SQL_Latin1_General_CP1_CI_AS`; GETDATE e GETUTCDATE coincidiram na amostra |
| Identificadores | pipeline_name e job_name nvarchar(200); matricula varchar(20), perfil varchar(30), recurso varchar(50) |
| Sessão | token_hash char(64), expira_em datetime; compatibilidade usa o relógio SQL atual |
| Migrations | controle consultado somente por SELECT; aplicadas até 139, em correspondência com o último arquivo do repositório observado; não foi executado migrate.py |
| Tipos presentes no cadastro DEV | datastage, decisao, http; amostras SQL/Python ainda precisam ser selecionadas ou preparadas para os testes posteriores |

Bind mounts da UI/API/DAGs tornam builds ou troca de branch no checkout servido operacionais. Nenhum build foi executado nele. Nenhum serviço foi reiniciado, banco/volume recriado ou migration aplicada.

## Autenticação e divergências reais

Fontes: `api/deps.py`, `api/routers/auth.py`, `ui-react/src/store/auth.ts`, `ui-react/src/lib/api.ts`, `ui-react/src/lib/nav.ts`, `ui-react/src/App.tsx`.

1. Login valida Basic contra Airflow, emite `secrets.token_urlsafe(32)`, grava apenas SHA-256 hexadecimal na `etl_sessao`. Não é JWT; não criar emissor JWT nem novo login .NET.
2. Bearer calcula SHA-256 dos bytes UTF-8 após o prefixo e consulta sessão com `expira_em > GETDATE()`. TTL padrão 12 horas, configurável. Logout remove a linha. Cada request carrega usuário e permissões novamente.
3. Usuário ativo recebe perfil único mais concessões individuais, unidos e sem duplicação. Usuário inativo recebe 403. Usuário ausente recebe fallback consulta no legado. Roles Airflow selecionam um perfil pela prioridade; não há múltiplos perfis persistidos.
4. Basic é compatibilidade legada: valida Airflow e usa cache de cinco minutos, depois carrega RBAC. Proposta F1: Bearer nativo SQL; Basic, caso usado, passa por adaptador interno para `GET /me` do legado, com header transitório, timeout e sem registro do Authorization. Testar equivalência; não usar credencial de serviço nem expor senha ao navegador.
5. Falha SQL em Bearer hoje pode retornar 500 com exceção em detail. .NET retorna 503 com mensagem fixa sem detalhe interno, mantendo fail closed. Documentar essa diferença deliberada.
6. `canAccess` trata lista vazia como navegação liberada. Várias leituras legadas exigem apenas sessão, enquanto menu exige tela. .NET exige recursos explicitamente: lista vazia nega acesso ao workspace. Não reproduzir abertura implícita nem ampliar guards legados como efeito colateral da F1.
7. `acao_editar`, `acao_executar` e `acao_admin` são os recursos gerais existentes. Gerar DAG usa `acao_executar`; publicar/cancelar/reprocessar não são permissões independentes hoje. Não apresentar granularidade nova como já disponível.

### Matriz dos públicos e capacidades proposta

| Experiência | Entrada futura | Pré-requisitos efetivos | Negativas e teste |
|---|---|---|---|
| Desenvolvimento | Fluxo/Montagem | tela_pipelines para contexto; tela_jobs para definição de etapas; acao_editar para futura edição | editor sem executar não publica; consulta sem editar não grava |
| Consulta | Visão geral publicada | tela_pipelines; tela_jobs apenas para etapas; tela_logs para dados de execução/logs | pipeline visível não libera etapas ou logs implicitamente |
| Sustentação | Execuções | tela_pipelines e tela_logs para consulta contextual; acao_executar para operação legada autorizada | operador sem editar pode operar apenas as ações autorizadas |
| Responsabilidades acumuladas | Preferência de entrada separada de RBAC | união perfil + extras existente | trocar experiência não acrescenta recurso; testar combinação de concessões individuais |

F1 publica ações como capacidades distintas, mas todas as ações de rascunho/publicação permanecem false. Definir recurso específico de publicar antes da F4, com migration/RBAC/nav se aprovado. Cancelar e reprocessar permanecem diferenciados no contrato e marcados como agrupados sob acao_executar no legado. O perfil de experiência não é autoridade de segurança.

## Inventário funcional e destino de paridade

Rotas abaixo são internas da API; o browser usa prefixo `/orquestra`. Guards de tela são hoje predominantemente frontend; a coluna descreve a autoridade atual por ação, sem afirmar que toda leitura aplica tela no servidor.

| Ação/fonte | API atual | Dados/efeito | Permissão atual | Destino posterior e prova de paridade |
|---|---|---|---|---|
| Lista/cadastro Pipeline; Pipelines.tsx, PipelineFormModal.tsx | GET /pipelines; POST /pipelines/register | etl_pipeline, parâmetros, agenda e intenção de DAG conforme cadastro | leitura/sessão conforme router; gravação acao_editar | lista/contexto; criação em rascunho não gera DAG; identidade original preservada |
| Criar/editar etapa; Jobs.tsx | POST /pipelines/jobs/register | etl_pipeline_job e parâmetros via upsert | acao_editar | lista interna e propriedades; round-trip por tipo |
| Remover etapa | DELETE /pipelines/jobs/{pipeline}/{job} | remove job e lineage | acao_editar | remoção no rascunho; publicado intacto até F4 |
| Inativação | Jobs.tsx expõe active no tipo de dados, mas não foi encontrada ação dedicada de inativar etapa na tela inspecionada | não presumir que remover seja inativar | não atribuir permissão de operação não confirmada | registrar lacuna; preservar status existentes e confirmar API/SP antes da fase de edição |
| Ordenar | POST /pipelines/jobs/reorder | execution_order | acao_editar | lista/canvas; ordem e dependências mantidas |
| Renomear | POST /pipelines/jobs/{pipeline}/{job}/rename | dependências, condições, parâmetros, lineage, histórico e auditoria | acao_editar | renomear no rascunho; sem afetar histórico durante montagem |
| Abrir/salvar FluxoEditor.tsx | GET/POST /pipelines/{pipeline}/fluxo | jobs, arestas por depends_on_jobs, condições, layout, configurações por tipo; deleted remove jobs/lineage | sessão / acao_editar | contrato do fluxo; round-trip sem perda e sem acesso ao ativo no futuro draft |
| Publicação atual | POST /pipelines/{pipeline}/gerar-dag; /dag-sync | intenção/reconciliação de DAG | acao_executar | publicação versionada F4; F1 indisponível |
| Parâmetros Pipeline/importação | GET /pipelines/{pipeline}/parametros; POST /pipelines/parametros/importar-previa; cadastro /register | catálogo/snapshot/vínculos; prévia e gravação são diferentes | leitura sessão; importação/cadastro acao_editar | aba Parâmetros; valores secretos não entram em fixtures/JSON |
| Configuração por tipo; JobTypeFields.tsx | consultas de conexões, params/preview e configuração do fluxo | python_json, sql_json, notify_json, aguarde_json, condições, email/validação e referências | varia por consulta; escrita acao_editar | painel contextual; caso por tipo e desconhecido somente leitura |
| Lineage | GET /lineage; PUT /lineage/job; POST /lineage/extract-dsx e /normalize | etl_job_lineage; extração pode gravar | sessão para consulta; acao_editar para gravação | Dados e qualidade/etapa; separar leitura de importação que grava |
| Importação em lote de etapas | POST /pipelines/jobs/register | cadastro ativo em lote | acao_editar | importar para draft apenas quando suportado; nenhuma escrita ativa |
| Execução | POST /airflow/dags/{dag}/dagRuns | disparo Airflow e reconciliação existente | acao_executar | Execuções; preservar conf/data/mode e não confundir com publicação |
| Reprocessar | GET /pipelines/{pipeline}/rerun/previa; POST /execucoes/rerun | intenção/reset de tentativas e operação | acao_executar | contexto de execução; prévia, seleção e parâmetros equivalentes |
| Pausar/retomar/cancelar pausa | POST /execucoes/pausas; /{id}/liberar; /{id}/cancelar | etl_etapa_pausa e operação | acao_executar | Execuções; distinguir pausa de etapa, DAG pausada e cancelamento |
| Estado e logs | GET /pipelines/{pipeline}/execucao, /corrida, /pausas; /airflow/.../logs/{try_number} | execução/tentativas/logs publicados | sessão, guard tela_logs no percurso UI | canvas em execução + eventos/logs; origem/tentativa visíveis |
| Política sem movimento | GET/PUT /pipelines/{pipeline}/politica-sem-movimento | configuração publicada; escrita independente do botão Salvar fluxo | acao_editar | propriedades draft; interceptar também essa escrita |
| Prévias SQL/decisão/arquivo | POST /jobs/sql-preview, /jobs/decisao-simular, /pipelines/{pipeline}/valida-arquivo/{task}/previa | podem consultar fontes externas; revisar side effects individualmente | sessão ou acao_editar por endpoint | capabilities separadas; não executar implicitamente no modo consulta |
| Maestro | POST /maestro/conversar; GET /maestro/historico | conversa/IA existentes | contrato próprio legado | preservar; não habilitar aplicação/publicação IA na F1 |

Tipos aceitos pelo backend: datastage, shell, python, storedproc, http, decisao, notificacao, sql, aguarde, email, valida_arquivo. Não reduzir aos tipos encontrados no banco ou exibidos nos mockups. Nós virtuais do canvas e referências a pipeline não equivalem automaticamente a novos tipos persistidos.

Risco principal: trocar apenas o endpoint de Salvar não isola rascunho. Rename, política, lineage, cadastro/importação, previews com efeitos e geração de DAG precisam ser classificados. F1 formaliza `IFlowAccess` e matriz de operações; a extração do editor e bloqueio de todas as escritas ativas serão implementados/testados nas fases seguintes.

## Tarefas executáveis da F1 após revisão

### 1. Fixar toolchain e pacote offline antes de scaffold

Proposta: target `net10.0` (.NET 10 LTS). Fonte oficial consultada: https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core. O host atual não tem SDK/runtime, nem imagens locais. Isso é pendência, não autorização para instalar agora.

Na implementação, validar SO/arquitetura DEV e alvo offline; selecionar patch suportado, pin de SDK em `backend-dotnet/global.json`, versões NuGet e lock files. Construir com imagem SDK e executar com imagem ASP.NET fixadas por digest. Não depender de runtime no host. Preparar tar de imagem, manifest/checksums, SBOM e feed NuGet offline para build reproduzível ou artefato runtime pré-compilado conforme ambiente-alvo. Ensaiar `docker load`/execução sem egress em ambiente de teste. Não afirmar distribuibilidade antes desse ensaio.

Critério de passagem: disponibilidade do SDK/imagens, compatibilidade Linux/SQL Server e distribuição offline comprovadas. Falha mantém piloto desligado; não substituir versão silenciosamente.

### 2. Contratos versionados e fixtures

Arquivos novos previstos:
- `docs/contracts/pipeline-workspace-v1.md` e `docs/contracts/pipeline-workspace-v1.schema.json`.
- `backend-dotnet/Orquestra.Domain/Flows/PipelineDefinition.cs` e `FlowNode.cs`.
- `backend-dotnet/Orquestra.Application/Capabilities/WorkspaceCapabilities.cs`.
- `backend-dotnet/Orquestra.Application/Flows/IFlowAccess.cs`.
- `backend-dotnet/Orquestra.Tests/Fixtures/` com identidades sintéticas e casos SQL, Python, DataStage e demais tipos aceitos.

Assinaturas propostas: `Task<FlowReadResult> ReadPublishedAsync(PipelineIdentity id, CancellationToken ct)`; `Task<WorkspaceCapabilities> GetAsync(WorkspacePrincipal principal, CancellationToken ct)`; nenhuma implementação de save/publish F1.

DTO: schemaVersion=1, identidade original, metadados/agenda/parâmetros, nós tipados e arestas/condições; layout separado; extension data preserva desconhecidos e marca readOnly com motivo. JSON contém referências de conexão e parâmetros secretos redigidos, nunca ciphertext/segredo. Hash futuro separa conteúdo e layout e exige canonicalização especificada, não hash de serialização instável.

Fixtures derivadas do contrato/código, sem exportar conteúdo privado do DEV. Round-trip cobre omissão versus null, parâmetros/vínculos, Encrypted mascarado, dependências e ramos, Unicode, caixa original, limites UTF-16 e nomes codificados. Tipo desconhecido não pode ser salvo nem eliminado silenciosamente.

### 3. Solução .NET modular mínima

Criar `backend-dotnet/Orquestra.sln`, projetos `Orquestra.Api`, `.Application`, `.Domain`, `.Infrastructure`, `.Tests`. Api referencia Application/Infrastructure; Domain não depende de HTTP/SQL; SQL de sessão em Infrastructure, com Microsoft.Data.SqlClient e comandos parametrizados. Evitar ORM/migrations paralelas na F1.

Arquivos principais: `Orquestra.Api/Program.cs`, `Endpoints/CapabilitiesEndpoints.cs`, `Authentication/LegacySessionHandler.cs`, `Orquestra.Infrastructure/Security/SqlSessionRepository.cs`, `LegacyBasicIdentityClient.cs`, `Orquestra.Application/Security/WorkspaceAuthorization.cs`.

Interfaces: `Task<SessionLookupResult> FindValidAsync(string tokenHash, CancellationToken ct)` e `Task<WorkspacePrincipal> LoadAsync(string matricula, CancellationToken ct)`. Hash só vive internamente; não vai para resposta/log. Consultas reproduzem expiração GETDATE, união perfil/extras e usuário inativo. Compatibilidade de tabela de extras ausente deve identificar especificamente ausência da tabela, sem ignorar indisponibilidade SQL genericamente.

Endpoint público de infraestrutura: `GET /health/live` indica processo; `GET /health/ready` consulta SQL e schema de sessão/RBAC necessário, sem DDL, retornando 503 quando não pronto. Respostas sem connection string ou exceções. Não exigir tabelas draft ainda inexistentes para readiness F1. `GET /workspace/capabilities` autenticado retorna schemaVersion, disponibilidade, recursos reais de consulta e ações draft/publicação false; resposta por usuário sem cache compartilhado.

Testes de segurança: sem token, formato inválido, token inexistente/expirado/revogado →401; usuário inativo→403; usuário ausente conforme fallback legado; lista vazia→capabilities negadas; perfil+extras unidos; mudança de permissão refletida em novo request; admin sem recurso não ganha bypass geral. SQL indisponível→503 fail closed; Basic inválido e legado indisponível sem fallback permissivo; headers e secrets ausentes de logs/erros.

### 4. DEV: serviço e roteamento sem colisão

Arquivos previstos: `backend-dotnet/Dockerfile`, `docker-compose.workspace.dev.yaml`, `config/nginx.workspace.dev.conf` e roteiro `docs/dev-workspace-dotnet.md`. Overlay novo exclusivamente DEV; configuração de proxy habilitada só pelo overlay, sem mudar comportamento de produção no nginx padrão.

Adicionar location mais específica `/orquestra/workspace/`, encaminhando ao .NET e preservando path interno `/workspace/`. Endpoint exato `/orquestra/workspace` deve ter política explícita (redirect relativo 308 ou resposta definida). `/orquestra/health`, `/orquestra/me`, `/orquestra/pipelines` e `/api/v1/` continuam legados. Não criar fallback de escrita para FastAPI se .NET cair.

Nginx deve resolver upstream .NET em runtime com DNS Docker e `valid`/timeout limitado, ou mecanismo equivalente comprovado, evitando impedir a subida do proxy se o serviço não existir. Tratar 502/504 no prefixo workspace como 503 JSON com detail estável. Testar prefixo/barra/query e impedir que `/workspaceXYZ` capture tráfego legado. .NET sem porta pública, acessível só na rede DEV. Propagar Authorization sem registrá-lo; correlação sanitizada.

Nenhuma mudança operacional agora. Deploy futuro seletivo usa `-f docker-compose.yaml -f docker-compose.dev.yaml -f docker-compose.workspace.dev.yaml --env-file .env.dev`; somente serviço workspace e UI/proxy necessários. Nunca `up` global, `down -v` ou bootstrap de banco. Nginx bind mount de arquivo requer conferir inode/reload/recriação seletiva no roteiro de entrega. Cada comando deve ser aplicado ao SHA validado.

### 5. Integração e degradação

Arquivos de teste previstos: `Orquestra.Tests/Security/LegacySessionTests.cs`, `WorkspaceAuthorizationTests.cs`, `Contracts/PipelineDefinitionTests.cs`, `Integration/SessionSqlTests.cs`, `HealthTests.cs`, `tests/test_workspace_proxy_config.py` e smoke `scripts/smoke_workspace_f1.py`.

Integração SQL usa banco de teste separado com schema mínimo/sessões sintéticas, sem alterar usuários ou sessões reais do DEV. Fixtures limpas pela própria bancada, nunca recriação de volumes. SessionSqlTests prova relógio, expiração, revogação, collation e perfil+extras; testes unitários não substituem esse gate.

Teste proxy com .NET saudável, parado, ausente na resolução DNS e SQL indisponível. Em todos, FastAPI/UI/consulta Airflow continuam acessíveis. Capabilities não inventa edição/publicação e não mostra ações negadas. Como F1 não adiciona UI de ações, ocultação na nova interface só poderá receber aceite completo nas fases F3/F5.

### 6. Entrega e revisão

Atualizar `docs/dev-workspace-dotnet.md` com instalação offline, configuração por nomes de variáveis, SHA/digests, smoke e recuperação. Se houver entrega funcional, migration idempotente de versão separada atualiza Admin → Versões e app_version/app_release_name; número e release só serão escolhidos após novo fetch de develop. Hoje o maior número é 139; não reservar 140. Tabelas workspace ficam na F2.

Antes da PR: revisão adversarial independente e revisão de segurança, aplicar achados e repetir checks afetados. F1 pode ser dividida em sub-PRs funcionais de contratos/fundação/integração se necessário para revisão. PR para develop com O que muda / Validação / Deploy e commit convencional em pt-BR conforme instruções locais. Implementação, PR, integração e deploy não foram feitos nesta preparação.

## Validação, baseline e comandos

Baseline medido na worktree em SHA develop, antes de código: `tsc -b` passou; lint tem 166 erros e 12 avisos; `npm run build` passou com aviso de chunks >500 kB. Dependências vieram da cópia DEV, não de instalação limpa por lockfile: registrar esse limite. Build não modificou dist versionada nesta execução. Pytest completo: 7.131 passed, 8 failed, 51 skipped, 28 warnings em 83,19 s. As falhas são baseline desta base, não regressões novas. Testes SQL vivos que dependem de configuração própria não foram habilitados; a inspeção SQL por SELECT não os substitui. A busca de bytes NUL encontrou `ui-react/src/lib/lineageIsx.ts`; confirmado também no blob de origin/develop, portanto preexistente, registrado sem corrigir código nesta preparação.

Comandos na worktree:
```bash
python3 -m pytest tests -q
cd ui-react
./node_modules/.bin/tsc -b
./node_modules/.bin/eslint . -f json
npm run build
```

Após toolchain disponível, de `backend-dotnet`:
```bash
dotnet restore Orquestra.sln --locked-mode
dotnet build Orquestra.sln --no-restore -c Release
dotnet test Orquestra.sln --no-build -c Release
```

Integration SQL recebe configuração por canal local seguro; nunca escrever conexão na linha de comando ou relatório. Comparar falhas pytest e lint por caso/arquivo/regra/primeira linha com base da PR. Recompilar dist por último nas fases que mudarem front; buscar bytes NUL nos fontes. Não aplicar baseline histórico como verdade atual.

Smoke F1 após deploy futuro: a) conferir SHA/release/readiness; b) login legado e capabilities do workspace com perfis sintéticos; c) negar inválido/expirado/revogado/inativo e ação sem permissão; d) parar somente workspace e verificar endpoints antigos/UI; e) simular SQL indisponível na bancada isolada e conferir 503 sem segredo; f) confirmar menus e cadastro antigo operacionais; g) desabilitar overlay/flag e verificar retorno ao roteamento legado sem mexer nos dados.

## Contratos para evoluções posteriores

Reservar schemaVersion, versionId, correlationId, motor, pool/fila, executor/tentativa e timestamps previsto_em, dependencias_liberadas_em, enfileirado_em, iniciado_em, concluido_em com origem e nullable. Hoje execução expõe inicio/fim/tentativas e há queued_seconds DataStage; não há comprovação de todos os timestamps nem capacidade por pipeline. Não ampliar coleta/retenção na F1.

Malha terá composição versionada própria e dependências globais explicitadas. Monitores estratégico/operacional precisam de fontes e compromissos reais. Capacidade por horário exige histórico por recurso, fila e benchmark; concorrência de tarefas não comprova quantidade de pipelines. IA futura propõe alterações no mesmo contrato, com RBAC/revision/lease/revisão. Academy/runbooks usam IDs estáveis, versão, origem e acesso. Cada evolução terá spec própria.

## Pendências para revisão e gates antes do código

- Revisar este plano; a direção React + .NET + motores preservados já está aprovada e não precisa ser reaberta.
- Confirmar escolha proposta net10.0 e formato offline com disponibilidade real das imagens/pacotes e compatibilidade do alvo. Nenhuma instalação realizada.
- Validar política proposta de capacidades estritas e compatibilidade Basic; granularidade específica de publicação precisa ser definida antes da F4.
- Escolher/preparar pipelines sintéticos SQL/Python e DataStage simulado. DEV não prova funcionamento com Information Server real ou cargas da Caixa.
- Concluir baseline pytest e listar falhas/skips concretos; nenhum resultado parcial vale como suíte aprovada.
- Aprovação do plano não dispensa revisão adversarial antes da PR nem autoriza main/produção.
