# Spec: UX profissional do Pipeline — ORQUESTRA
Data: 2026-10-11 · Status: rascunho para revisão
Base analisada: develop `df1a81caa3ef5400877bf3ab2f798011552143b2` (DEV 2.17.1).
Direção aprovada: ferramenta bonita, funcional e fácil de utilizar; eliminar configurações concorrentes e alcançar a composição dos mockups. Esta aprovação permite detalhar a proposta; os critérios e mudanças abaixo ainda precisam de revisão antes da implementação.

## 1. Visão
Desenvolvedores precisam montar e publicar sem procurar a configuração em várias telas. Leitores precisam entender finalidade, dependências e estado. Sustentação precisa identificar o que executa, por que espera e como investigar sem perder a corrida.
A entrega reorganiza a jornada Pipeline, da descoberta de um rascunho à investigação da execução, preservando React, a gestão .NET e o motor Airflow/DataStage/Python/PySpark. Beleza deve resultar de hierarquia, legibilidade e interação coerente, com fidelidade aos mockups aprovados.
O contrato visual complementar está em [pipeline-experiencia.md](design/pipeline-experiencia.md). Não basta obter build/testes passando: a aceitação inclui percursos reais e comparação visual.

### Evidências e limites
- Revisão de fonte, especificações F1–F9 e acesso autenticado ao DEV em 11/10/2026.
- QA5_A: Visão geral, Fluxo, Configuração do pipeline expandida e Execuções; largura normal do navegador e composição desktop 1440×960.
- Observado: Fluxo contém projeto/domínio, descrição, governança, SLA, agenda, dependências e notificações; não existe um destino Configuração na navegação principal do Pipeline.
- Em Execuções, o cabeçalho mantém Rascunho/revisão enquanto o conteúdo informa definição publicada; o inspector vazio contém instrução para editar propriedades. A semântica diverge entre superfícies.
- Cabeçalho Desenvolvimento e campo Ambiente PROD têm sentidos distintos sem rótulos suficientes. Não se conclui que o backend esteja executando em produção.
- QA5_A estava sem etapas na corrida/data consultada. Não houve criação, edição, publicação, disparo ou validação de transições reais neste acesso.
- O código operacional atual consulta periodicamente a cada 30s. Há tradução de estados e animação em componentes legados; o renderer WorkspaceFlowNode não aplica o indicador animado. Validar o renderer efetivamente montado por rota.
- Registros F9 são evidências anteriores; esta revisão não reexecutou seus testes nem certificou DataStage/IA externos.

## 2. Escopo
**IN:**
- Lista unificada de publicados e rascunhos, retomada, busca e indicação de edição em andamento.
- Criação essencial, espaço de trabalho, configuração única, montagem, versões/publicação e investigação contextual.
- Cinco destinos principais: Visão geral, Fluxo, Execuções, Configuração, Versões.
- Dois modos dentro de Fluxo: Montagem e Execução. Execuções abre o mesmo visualizador a partir do histórico, sem implementar uma segunda experiência gráfica.
- Inspector de etapa contextual; estados reais, atualização, acessibilidade, persistência de contexto e recuperação de erro.
- Sessão de edição compartilhada entre abas e redução de modais para operações frequentes.
- Critérios visuais e funcionais, protótipo navegável identificado como simulação, implantação incremental em DEV.
- Vocabulário, cores e componentes reutilizáveis por Malha/monitores posteriores.

**OUT:**
- Novo workspace versionado de Malha, monitores estratégico/operacional completos, heatmap e recomendação de horário: specs próprias subsequentes.
- Montagem integral por IA, novos conectores, qualidade de dados não existente e Academy/comunidade.
- Reescrever motores, aumentar concorrência, implantar Spark/Kubernetes ou prometer capacidade de 50 pipelines.
- Cancelamento geral remoto, execução multiversão simultânea ou reprocessamento de corrida antiga onde a guarda atual proíbe.
- Nova identidade de marca, fontes/CDNs externos e mudanças nos módulos Caixa/BI/Admin não necessárias à jornada Pipeline.
- Publicar em main/produção; esta spec não autoriza essa promoção.

### Regras de organização
1. Cada campo tem um editor principal. Resumos em outras telas são somente leitura e possuem atalho para o destino.
2. Dependências entre etapas pertencem ao Fluxo; dependências entre pipelines pertencem à Configuração. A Malha mantém autoria/assinaturas das dependências que administra.
3. Rascunho, versão publicada e execução são contextos distintos e sempre identificados.
4. Uma ação conserva nome, efeito e autoridade em todas as entradas.
5. Experiência de uso escolhe prioridade/entrada; RBAC do servidor continua concedendo ou negando cada ação.

## 3. Arquitetura proposta

### Fonte e componentes reais
- Navegação/casca: ui-react/src/App.tsx, lib/nav.ts, lib/workspaceNavigation.ts.
- Descoberta/criação: pages/Pipelines.tsx, pages/PipelineCreate.tsx, components/pipelines/PipelineRow.tsx.
- Contexto: pages/PipelineWorkspace.tsx, lib/workspace.ts, lib/workspaceApi.ts.
- Montagem: components/workspace/WorkspaceEditor.tsx, WorkspaceCanvas.tsx, WorkspaceFlowNode.tsx, NodeProperties.tsx, SharedJobConfiguration.tsx, SpecializedConfiguration.tsx.
- Configuração: reutilizar WorkspaceDraftTools, WorkspacePipelineFields, WorkspaceParameters e WorkspaceFlowTools; extrair a responsabilidade sem copiar os formulários.
- Operação: WorkspaceOperations, WorkspaceRunProperties, componentes de etapas/FluxoEditor.tsx e execucaoEtapas.ts; evoluir um visualizador reutilizável com contrato explícito, em vez de manter grafos que divergem.
- Publicação: WorkspacePublication e WorkspaceVersions; manter guardas, intent, hash e reconciliação.
- .NET: Orquestra.Api/DraftEndpoints.cs, OperationEndpoints.cs, PublicationEndpoints.cs; Orquestra.Infrastructure/Drafts/SqlDraftRepository.cs.
- Adaptador atual: api/services/workspace_publication.py, workspace_operations.py e routers/pipelines.py. A projeção e reconciliação permanecem no adaptador durante a migração.

### Sessão do workspace
Um contexto de edição no nível do Pipeline guarda definição/layout locais, revisão-base, dirty, lease/fence e publicação pendente. Trocar Fluxo↔Configuração não perde alterações, não adquire uma segunda posse e não interrompe a renovação da posse atual.
Salvar rascunho persiste os campos alterados na mesma revisão por contrato existente. Aplicar no inspector incorpora mudanças locais; publicar continua separado.
Ao sair do Pipeline, recarregar ou mudar da definição em edição, confirmar descarte de alterações locais. Falha de save conserva o trabalho; revisão obsoleta exige reconciliação explícita, nunca sobrescrita silenciosa.
Cache local em memória não promete sobrevivência a fechar o navegador. Nenhum novo valor protegido fica em cache/URL/log.

### Descoberta unificada
Adicionar GET /workspace/pipeline-index no .NET, protegido por tela_pipelines e flag existente. Proposta de contrato:
- Filtros: search, project, domain, state=all|draft|published|editing|inactive; limit padrão50, máximo100; offset não negativo.
- Resultado: total, limit, offset, items.
- Item: pipelineName, displayName, project, domain, responsible, hasDraft, draftRevision, hasPublished, publishedVersionNumber, isActive, updatedAt, editorUser, leaseExpiresAt.
- Campos desconhecidos são null; não inferir edição pela existência de draft. editorUser só identifica posse ainda válida, calculada pelo servidor.
- Filtro draft inclui draft ativo; published inclui publicação conhecida; editing exige lease válida; inactive inclui cadastro publicado explicitamente inativo. Flags coexistem; os filtros não representam estados mutuamente exclusivos.
- Uma linha por pipeline segundo a collation real do SQL Server. Rascunho novo aparece sem inserir cadastro ativo ou DAG. Pipeline publicado com draft aparece uma única vez.
- Usuário sem tela_jobs recebe somente resumo autorizado, nunca definition/layout/segredos.
- Esquema indisponível retorna 503 identificando migration; piloto desabilitado conserva a lista antiga.
- Filtros/paginação no servidor com cancelamento de requisição e busca com debounce250ms; não baixar todos os pipelines para montar a tela.

### Operação e atualização
Usar name + runId + versão + taskId + attempt como identidade da investigação. O visualizador histórico usa snapshot confirmado da corrida; se desconhecido, explicitar que o desenho é a configuração atual.
Polling é a primeira opção: alvo proposto de 5s enquanto a corrida estiver ativa e aba visível, 30s sem corrida ativa; suspender em aba oculta e revalidar ao retornar. Corridas encerradas permanecem consultáveis sem animação de execução atual.
Antes de ativar 5s, medir leituras concorrentes/SQL/upstream; se ultrapassar orçamento, manter30s com frequência visível e entregar mecanismo incremental ou eventos em fase própria. Não fixar tecnologia SSE/SignalR sem evidência.
Mostrar última atualização de dados, origem e estado de conexão. Latência da interface se mede desde a disponibilidade do estado na API, separada do atraso de telemetria do motor.
Respostas antigas não substituem seleção de corrida/tentativa mais recente. Atualização não reposiciona nós, fecha inspector ou muda zoom.

### Alternativas avaliadas
- Apenas reorganizar CSS: insuficiente para duplicação, descoberta de drafts e identidade operacional.
- Trocar stack/reconstruir toda a aplicação: risco e escopo desnecessários.
- Reorganizar responsabilidades sobre os contratos atuais: opção recomendada; mantém investimento F1–F9 e permite entregas revisáveis.

## 4. Modelo de dados e contratos
Reutilizar etl_pipeline, etl_workspace_rascunho, etl_workspace_versao, etl_workspace_lease, etl_workspace_publicacao/evento/execucao. Não criar tabela por aba nem segunda definição de pipeline.
Estado em desenvolvimento deriva de draft ativo; edição em andamento deriva de lease válida. Não consolidar esses conceitos num booleano único.
Mapear a data de updatedAt à origem indicada (rascunho ou publicado); não inventar atualização histórica.
Índices para pipeline-index dependem de plano SQL e distribuição; se necessários, migration de schema pequena e idempotente. Sua numeração será o próximo número livre de develop no início da fase, nunca um número reservado concorrente.
Toda entrega funcional tem migration idempotente de versão conforme regra do projeto. Aplicação pelo roteiro DEV vigente; produção usa etapa6c do deploy.sh quando autorizada.
Erros: detail em português e code estável; 401 sessão,403 permissão,409 revisão/lease/gate,422 entrada,503 dependência. Fontes externas indisponíveis não viram dados fictícios.

### Matriz de destino
| Informação/ação | Editor principal | Resumo/atalho |
|---|---|---|
| Nome amigável, descrição, projeto/domínio, responsável e tags | Configuração / Identificação | Visão geral |
| Identificador técnico | Criação; depois somente leitura | Cabeçalho/copiar |
| Agenda, calendário, ODATE, predecessores/janelas | Configuração / Agenda e dependências | Visão geral |
| SLA, pool, concorrência, retries e política sem movimento | Configuração / Execução | Visão geral resumida |
| E-mail e notificações gerais | Configuração / Notificações | Visão geral se relevante |
| Parâmetros globais e referências protegidas | Configuração / Parâmetros | Inspector só vínculo/override da etapa |
| Etapas, arestas, decisões, ordem executável | Fluxo / Montagem | Visão geral com contagem |
| Comando, conexão, parâmetros e retries da etapa | Inspector da etapa / Montagem | Execução consulta snapshot |
| Lineage da etapa | Inspector / Lineage | Visão geral: atalho; catálogo externo mantém destino próprio |
| Runbook | Configuração / Documentação | Visão geral e investigação |
| Validar/publicar | Barra de ações + painel de diagnóstico | Versões registra resultado |
| Log/tentativa/reprocessar/pausa | Inspector / Execução | Histórico abre contexto |
| JSON/importação avançada | Ação avançada contextual | Nunca requisito do percurso comum |

### Criação
Solicitar nome amigável, identificador sugerido/editável, projeto/domínio e descrição opcionais. Agenda padrão Sob demanda; configuração rica fica para depois da criação.
Responsável inicial vem da sessão; identificação técnica preserva regras atuais. Criar abre Montagem do novo rascunho e deixa claro que nenhuma DAG foi disparada.
Erro de campo aparece no campo e resumo acessível; indisponibilidade conserva formulário. Template em branco é o modelo obrigatório; novos templates recebem escopo próprio.

### Visão geral
Responder o que faz, quem mantém, qual definição está aberta e onde participa. Descrição, proprietário, projeto/domínio, versão, situação de desenvolvimento, resumo de agenda/dependências e runbook disponível.
Atalhos Editar configuração, Abrir fluxo, Ver execuções respeitam capabilities. Não repetir formulários nem mostrar tabelas/logs extensos na visão geral.
Sem informação, orientar onde cadastrar em vez de multiplicar Não informado.

### Fluxo / Montagem
Cabeçalho identifica rascunho/revisão, ambiente da aplicação e destino quando configurado; indicador de alterações locais separa salvo de não publicado.
Biblioteca, canvas dominante e inspector; seleção de uma etapa mostra campos principais diretamente. Configurações extensas usam subseções do inspector ou área expandida; modal permanece para confirmação, segredo e importação excepcional.
Biblioteca recolhível, busca por tipo; clicar/arrastar adiciona no rascunho. Conectar, excluir, organizar, desfazer/refazer atuam localmente. Organizar muda layout; ordem executável não altera dependências.
Histórico local de desfazer/refazer: últimos50 patches do draft (definição/layout), sem valores protegidos; limpa ao recarregar/restaurar/trocar versão. Não desfaz publicação, execução ou side effects externos.
Painel inferior de validação recolhível mostra erro/aviso, campo e etapa; selecionar diagnóstico abre a etapa correta. Se todos válidos, resumo curto; detalhes sob demanda.
Barra de ações consistente: Salvar rascunho, Validar, Publicar. Publicação pendente visível e preservada ao recarregar. Outros leitores veem editor/último save/revisão; ninguém vê mudanças não salvas de outra sessão.

### Fluxo / Execução e Execuções
Execuções lista corridas e situação/duração/origem/versão. Selecionar uma abre visualizador comum em modo Execução, preservando filtros de origem.
O cabeçalho operacional identifica corrida/data/versão; não mostra rascunho como definição executada. Sem corrida selecionada, apresenta escolha/estado vazio e não promete andamento.
Solicitar execução usa somente configuração publicada, capabilities e gate existentes; mostra recebimento da solicitação, fila e início como estados diferentes. Data lógica e parâmetros devem ter controles guiados para parâmetros declarados; JSON fica avançado.
Após resposta de disparo, abrir runId retornado no visualizador. A DAG pausada continua aguardando, com causa quando API a informar.
Inspector operacional tem Resumo, Tentativas, Logs e Parâmetros autorizados. Não contém instruções de editar. Reprocessar/pausas aparecem somente quando permitidos pelo servidor.
Tabela de etapas vira visualização alternativa, não bloco duplicado permanente abaixo do gráfico. Sem seleção, o inspector resume a corrida, não repete cadastro extenso.
Links antigos Logs/Etapas/Fluxos redirecionam preservando pipeline, modo, data, corrida, etapa, tentativa e origem. Se a origem inclui corrida de Malha, conservar identidade para retorno.
A aba Logs do Pipeline é substituída por investigação contextual, mantendo rota de compatibilidade. Publicação global mantém histórico de fábrica para suporte, claramente identificado e secundário à publicação de versão.

### Configuração e Versões
Configuração agrupa Identificação, Agenda/dependências, Parâmetros, Execução, Notificações e Documentação; navegação interna em vez de formulário vertical único.
Mesmo draft/lease e ação Salvar das demais abas. Uma edição apenas de agenda não abre o canvas nem altera a versão publicada antes da publicação confirmada.
Versões: publicada/importada/não confirmada explícitas; comparação por campo/etapa/aresta e layout em seção separada. Restaurar cria novo draft conforme guardas existentes; nunca reescreve histórico.

### Estados visuais e semântica de execução
| Estado/fato | Tratamento | Ação/informação |
|---|---|---|
| Sem execução | Neutro + rótulo | Escolher corrida ou executar se autorizado |
| Aguardando dependência | Espera + ícone/texto | Mostrar predecessores pendentes quando informados |
| Em fila por recurso | Espera + rótulo distinto | Recurso/pool e tempo de fila se disponíveis |
| Executando | Azul + indicador discreto | Etapa, tentativa e duração disponível |
| Sucesso confirmado | Verde + check | Duração e tentativa |
| Falha | Vermelho + ícone de erro | Motivo, log, reprocessar se permitido |
| Pulada | Cinza + ícone/rótulo próprio | Não conta como sucesso |
| Pausa marcada | Marcador adicional | Não transforma etapa ainda não parada em pausa |
| Em espera no portão | Âmbar + pausa | Motivo e duração do servidor |
| Estado desconhecido | Neutro + código/rótulo disponível | Informar fonte sem adivinhar |
| Fonte indisponível | Último estado + aviso | Carimbo e tentar novamente; parar animação de atividade atual |

Verde exige sucesso confirmado do nó naquela corrida/tentativa. Etapas concluídas não precisam ocorrer em sequência: paralelismo deve aparecer.
Conexões distinguem caminho efetivamente observado, ramo pulado e informação desconhecida; não usar apenas estado não nulo das pontas como prova de sucesso nem prometer que dados estão trafegando. Há helper legado ehTerminalOk com semântica ampla; revisar seu uso ao adaptar o renderer.
Uma tentativa nova pode voltar de sucesso/falha para execução; histórico de tentativas permanece acessível. “4 de6 etapas concluídas” não representa percentual de tempo nem permite previsão de fim.
Animação limitada a estados atuais confiáveis; sem percorrer conexões de ramos pulados, sem animação em histórico encerrado e respeitando prefers-reduced-motion.
Relógios da telemetria e do registro operacional são distintos no legado; normalizar fonte/fuso na API antes de combinar durações. Até lá, usar duração da origem e rotular horários.

## 5. Fases
Cada fase pode ser dividida em PRs pequenas (alvo ~500 linhas úteis), sempre a partir de develop. Nenhuma fase fecha só por aparência; manter destinos e compatibilidade até paridade comprovada.
**Validação comum:** pytest e lint contra base (zero novos achados), tsc-b, build/dist por último, testes .NET afetados, migrations idempotentes, revisão adversarial antes da PR e segurança quando pertinente. DEV: backup/serviços específicos, versão/saúde/migrations, smoke e evidências. Fontes sem NUL novos.

### F1 — contrato de experiência e protótipo
- Entregável: spec revisada, contrato visual e protótipo navegável com dados simulados claramente marcados.
- Inclui: criação, lista, Visão geral, Montagem, Configuração, Versões, histórico e Execução no mesmo modelo.
- Aceite: cada item da matriz tem um destino; comparação lado a lado dos mockups01/02/04; mostrar edição concorrente, save, validação inválida, publicação pendente, execução paralela, falha/retry e perda de conexão.
- Validação: revisão de conteúdo/links; se houver código de protótipo, verificações aplicáveis e screenshots claro/escuro. Protótipo não acessa APIs de escrita reais.

### F2 — descoberta e entrada única
- Entregável: pipeline-index, lista unificada e criação essencial.
- Aceite: criar draft, voltar à lista e retomar; outro leitor autorizado encontra Em desenvolvimento e quem edita; publicado+draft sem duplicata; filtros e paginação reais; nomes/estado acessíveis sem hover; pipelines geridos oferecem entrada única e menu secundário coerente.
- Validação: contrato .NET/SQL, RBAC, collation, publicação concorrente com leitura, carga do índice; validação comum.

### F3 — contexto e Configuração única
- Entregável: cinco abas, formulários remanejados e sessão de edição contínua.
- Aceite: descrição/agenda/parâmetros editáveis só no destino canônico; resumo tem atalho; alterações sobrevivem Fluxo↔Configuração; mesma lease/fence; leitura simultânea e transferência não permitem save obsoleto; rascunho/publicado/corrida não se confundem.
- Validação: interação por teclado, navegação com dirty, conflito/expiração, permissão combinada; validação comum.

### F4 — montagem fiel e eficiente
- Entregável: inspector, painéis recolhíveis, barra de ações, desfazer/refazer e diagnóstico contextual.
- Aceite: percurso comum dos11tipos sem JSON; conexão/decisão/drag/Delete/ordem/importação/lineage preservados; aplicar≠salvar≠publicar; focus e cancel corretos; canvas utilizável sem rolar por governança/agenda; mockup02 comparado.
- Validação: contratos puros de patches e histórico, segredos fora de cache, 50/100/300nós e composição; validação comum.

### F5 — execução e investigação
- Entregável: visualizador comum, histórico, estados/animações, logs/tentativas e atualização.
- Aceite: fixture real própria DEV com SQL/Shell incluída no plano aprovado; corrida retornada selecionada; nó executing→success, paralelismo, falha/retry, skipped, pausa e sem telemetria distinguíveis. Sem rascunho no cabeçalho da corrida; um inspector e uma visão alternativa de tabela; seleção/zoom preservados; fonte indisponível sinalizada.
- Validação: atualização/ordenação de respostas, identidade histórica, guards de ação, scripts/logs como texto, frequência medida e carga concorrente; mockup01; validação comum.
- Limite: testes DataStage/InformationServer reais permanecem dependentes do ambiente correspondente; animação simulada não comprova execução real.

### F6 — aceite da jornada e preparação das próximas telas
- Entregável: evidências por critério, documentação de uso, piloto e pendências explícitas.
- Aceite: três públicos percorrem tarefas essenciais; registrar sucesso da tarefa, tempo, desvios/retornos e dúvidas. Sem exposição acidental de ações; reprodução de leitura, erro, lease, publicação/restore e investigação. Listar itens ainda externos sem declarar100%.
- Desempenho: manter orçamento vigente da rota <300KiB gzip e seleção300nós p95<200ms na bancada comparável; medir atualização separadamente e investigar regressões.
- Validação: evidências desktop1440/1280, intermediário947 e móvel390, claro/escuro; teclado/foco/reduced-motion; usuário revisa jornada e comparação. Testes apropriados comuns.
- Próximas specs: Malha versionada; monitores e capacidade; montagem por IA; Academy. Não implementar módulos novos para encerrar esta fase.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|---|---|---|
|1|Reorganizar abas perde draft/lease|Perda de trabalho ou conflito|Contexto no Pipeline, revisão/fence e proteção dirty; testes de navegação|
|2|Rascunho confundido com corrida|Operador avalia definição incorreta|Cabeçalho contextual e snapshot/runId explícitos|
|3|Polling5s sobrecarrega SQL/Airflow|Latência e impacto no motor|Benchmark concorrente, aba visível, estados ativos, fallback documentado|
|4|Remover destino antes de paridade|Função inacessível|Matriz dos11tipos, rotas compatíveis e rollout por capabilities|
|5|Estado desconhecido fica verde|Falsa conclusão|Contrato fechado, ícone/rótulo/fonte e teste negativos|
|6|Inspector/modal perde dados protegidos|Exposição/corrupção|Referências write-only, patches conservativos, nunca segredo em histórico local|
|7|Redesign cresce para todos os módulos|Entrega incompleta|Pipeline primeiro; specs próprias para Malha/monitores/IA|
|8|Critério só visual|Tela bonita sem percurso funcional|Aceite por tarefas e estados reais, comparação visual e evidências separadas|
|9|Dependência assinada por Malha alterada|Orquestração corrompida|Preservar autoria/gates do servidor e comportamento F9|

## 7. Smoke pós-deploy
a) Conferir SHA/versão/saúde/migrations e flag do grupo DEV; confirmar legado fora do grupo.
b) Criar draft próprio; voltar à lista e reencontrar sem DAG ativa. Outra sessão autorizada encontra seu estado.
c) Iniciar edição; montar etapas e editar agenda na Configuração; alternar abas e salvar uma revisão coerente.
d) Outra sessão consulta e não escreve; transferência administrativa auditada invalida fence antiga.
e) Falha de save/conexão conserva trabalho; revisar conflito sem sobrescrever mudanças de terceiros.
f) Validar erro numa etapa e ir ao campo; corrigir, salvar, validar e publicar. Confirmar versão só após reconciliação.
g) Executar fixture própria explicitamente autorizada; verificar runId, versão e mudanças reais sem animar sucesso antes de confirmado.
h) Selecionar etapa/tentativa/log; refresh conserva contexto. Reprocessamento respeita guardas; pausa marcada distinta de parada efetiva.
i) Encerrar corrida, consultar histórico e snapshot; voltar ao draft sem misturar estados.
j) Abrir URLs antigas com pipeline/modo/data/run/etapa/origem e conferir destino/contexto/permissões.
k) Conferir teclado, claro/escuro, larguras e reduced-motion; terminar fixtures de teste inativas e sem comandos pendentes.
l) Registrar screenshot por estado e evidência funcional correspondente; não chamar simulação de teste do motor.

## 8. Pendências e decisões em aberto
- Direção e elaboração documental autorizadas pelo usuário em11/10/2026. Especificação detalhada e contrato visual estão em revisão; produto não alterado por esta entrega.
- Validar protótipo e nomes das cinco abas antes de remanejar UI; alterações de regra operacional são apresentadas para revisão.
- Fixtures próprias DEV e seus disparos serão identificados no plano de F5; execução de pipelines existentes fica fora do escopo dos ensaios.
- Cadência5s é alvo condicionado ao benchmark. Persistência/atualização incremental recebe desenho próprio se necessário.
- Definições futuras de Malha/capacidade/IA não são dependências para entregar Pipeline.
- Número de migration/versão pública será definido contra develop no início de cada fase.

## Referências
- [Spec original](spec-pipeline-workspace-dotnet.md), [complemento de paridade](spec-workspace-paridade-complemento.md), [homologaçãoF9](workspace-homologacao-f9.md).
- [Mockups aprovados](mockups/pipeline-workspace/README.md):01Execução,02Montagem,03Malha,04Criação.03 é referência futura, sem ampliar este piloto.
- [DataStage: designer/contexto](https://www.ibm.com/docs/en/ws-and-kc?topic=datastage-designing-flows).
- [Databricks: histórico por tarefa](https://docs.databricks.com/aws/en/jobs/monitor).
- [Control-M: monitoramento/esperas/logs](https://documents.bmc.com/supportu/9.0.22/en-US/Documentation/Monitoring.htm).
As referências externas orientam princípios; não alteram contratos do ORQUESTRA nem prometem paridade de recursos desses produtos.
