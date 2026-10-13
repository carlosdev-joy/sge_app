# Spec: UX profissional do Pipeline — ORQUESTRA
Data: 2026-10-11 · Status: especificação detalhada; protótipo disponível para validação visual
Base analisada: develop `df1a81caa3ef5400877bf3ab2f798011552143b2` (DEV 2.17.1).
Direção aprovada: ferramenta bonita, funcional e fácil de utilizar; eliminar configurações concorrentes e alcançar a composição dos mockups. A autorização inclui detalhar a proposta e preparar o protótipo navegável de UX. A validação visual do protótipo e a revisão dos critérios precedem a implementação no DEV.

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
- Cinco destinos principais: Visão geral, Montagem, Execução, Configuração, Versões.
- Montagem e Execução são abas distintas, com um renderer reutilizado. Histórico, tabela, tentativas e logs pertencem a Execução e abrem sob demanda; não há uma segunda faixa de modos nem abas principais separadas de Execuções/Logs.
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
Um contexto de edição no nível do Pipeline guarda definição/layout locais, revisão-base, dirty, lease/fence e publicação pendente. Trocar Montagem↔Configuração não perde alterações, não adquire uma segunda posse e não interrompe a renovação da posse atual.
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
- Usuário sem tela_jobs recebe somente resumo autorizado, inclusive editor de posse válida e filtro editing, nunca definition/layout/fence/sessão/segredos.
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
| SLA, pool, concorrência, retries e política sem movimento | Configuração / Políticas de execução | Visão geral resumida |
| E-mail e notificações gerais | Configuração / Notificações | Visão geral se relevante |
| Parâmetros globais e referências protegidas | Configuração / Parâmetros | Inspector só vínculo/override da etapa |
| Etapas, arestas, decisões, ordem executável | Montagem | Visão geral com contagem |
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

### Montagem
Cabeçalho identifica rascunho/revisão, ambiente da aplicação e destino quando configurado; indicador de alterações locais separa salvo de não publicado.
Biblioteca, canvas dominante e inspector; seleção de uma etapa mostra campos principais diretamente. Configurações extensas usam subseções do inspector ou área expandida; modal permanece para confirmação, segredo e importação excepcional.
Biblioteca recolhível, busca por tipo; clicar/arrastar adiciona no rascunho. Conectar, excluir, organizar, desfazer/refazer atuam localmente. Organizar muda layout; ordem executável não altera dependências.
Histórico local de desfazer/refazer: últimos50 patches do draft (definição/layout), sem valores protegidos; limpa ao recarregar/restaurar/trocar versão. Não desfaz publicação, execução ou side effects externos.
Painel inferior de validação recolhível mostra erro/aviso, campo e etapa; selecionar diagnóstico abre a etapa correta. Se todos válidos, resumo curto; detalhes sob demanda.
Barra de ações consistente: Salvar rascunho, Validar, Publicar. Publicação pendente visível e preservada ao recarregar. Outros leitores veem editor/último save/revisão; ninguém vê mudanças não salvas de outra sessão.

### Execução: gráfico, histórico e logs
Histórico dentro de Execução lista corridas e situação/duração/origem/versão. Selecionar uma retorna ao mesmo visualizador, preservando filtros de origem; não ocupar permanentemente a altura do canvas.
O cabeçalho operacional identifica corrida/data/versão; não mostra rascunho como definição executada. Sem corrida selecionada, apresenta escolha/estado vazio e não promete andamento.
Solicitar execução usa somente configuração publicada, capabilities e gate existentes; mostra recebimento da solicitação, fila e início como estados diferentes. Data lógica e parâmetros devem ter controles guiados para parâmetros declarados; JSON fica avançado.
Após resposta de disparo, abrir runId retornado no visualizador. A DAG pausada continua aguardando, com causa quando API a informar.
Inspector operacional tem Resumo, Tentativas, Logs e Parâmetros autorizados. Não contém instruções de editar. Reprocessar/pausas aparecem somente quando permitidos pelo servidor.
Tabela de etapas vira visualização alternativa, não bloco duplicado permanente abaixo do gráfico. Sem seleção, o inspector resume a corrida, não repete cadastro extenso.
Links antigos Logs/Etapas/Fluxos redirecionam preservando pipeline, modo, data, corrida, etapa, tentativa e origem. Se a origem inclui corrida de Malha, conservar identidade para retorno.
A aba Logs do Pipeline é substituída por investigação contextual, mantendo rota de compatibilidade. Publicação global mantém histórico de fábrica para suporte, claramente identificado e secundário à publicação de versão.

### Configuração e Versões
Configuração agrupa Identificação, Agenda/dependências, Parâmetros, Políticas de execução, Notificações e Documentação; navegação interna em vez de formulário vertical único.
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
- Aceite: descrição/agenda/parâmetros editáveis só no destino canônico; resumo tem atalho; alterações sobrevivem Montagem↔Configuração; mesma lease/fence; leitura simultânea e transferência não permitem save obsoleto; rascunho/publicado/corrida não se confundem.
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


## Protótipo navegável de referência (F1)
Preparado em 11/10/2026 e isolado do produto. Veja [o roteiro e os limites](prototypes/pipeline-workspace/README.md), [a verificação](prototypes/pipeline-workspace/VALIDACAO.md) e [o HTML portátil](prototypes/pipeline-workspace/pipeline-workspace.html). Baixe o HTML para interagir; o GitHub mostra o código.
O protótipo demonstra catálogo com rascunhos, criação, montagem, configuração única, publicação/versões e execução com estados, falha, retomada e investigação. Perfis, editor ativo e telemetria são ilustrativos; não implementam autenticação, lease ou execução reais. A implementação produtiva continua pendente no DEV. A fonte canônica para os critérios de aceitação permanece esta especificação; divergências simplificadas do protótipo estão registradas no README.


## Preservação funcional e revisão de navegação — 11/10/2026
Decisão do usuário: Montagem e Execução são abas principais. Histórico/logs integram Execução, sem uma segunda faixa de modos. O inventário dos 11 componentes, oito agendas, sessão, publicação e ações operacionais está na [matriz de preservação funcional](matriz-paridade-pipeline.md). Essa matriz é requisito para implementação: reduzir densidade não autoriza perder campos, payloads, permissões ou funcionalidades. Integrações e campos especializados não cobertos pelo protótipo permanecem pendências explícitas.


## Entrega 1 — contexto e Configuração única (F3 inicial) — 11/10/2026
Implementação autorizada pelo usuário em 11/10/2026 sobre `develop` `df1a81caa3ef5400877bf3ab2f798011552143b2` (DEV 2.17.1), com estes documentos importados de `origin/docs/ux-pipeline-profissional` `52c0c589`. Branch `feat/ux-pipeline-contexto`, candidato 2.18.0 (migration 164). Detalhes de rotas e validação nas [release notes](release-notes/2.18.0-pipeline-ux-contexto.md); destino de cada capacidade na [matriz](matriz-paridade-pipeline.md#estado-após-a-entrega-1--11102026). Candidato sem QA independente, sem smoke DEV e sem capturas de navegador até o registro de fechamento.

**Aceites entregues (verificados por teste automatizado no código real):**
- Cinco destinos na ordem aprovada; sem abas Execuções/Logs/Parâmetros/Ferramentas e sem seletor Montagem/Execução abaixo das abas.
- Configuração fora do canvas, seis grupos com um visível por vez; cada campo do pipeline tem um único editor e o grupo canônico da matriz; oito agendas presentes; leitura sem campo editável.
- Mesma sessão entre Montagem e Configuração (e mantida oculta nos demais destinos): uma posse, mesma fence, alterações das duas abas no mesmo save; 11 tipos, campos desconhecidos, arestas, layout e referências protegidas preservados.
- Cabeçalho da Execução identifica corrida/data/versão e nunca o rascunho; publicado e rascunho seguem identificados nos demais destinos.
- Aliases antigos preservam query integral (experiência, fonte, data, corrida, etapa, tentativa, origem de malha e chaves desconhecidas) e hash; destinos canônicos não redirecionam de novo.
- Histórico/corrida, tentativas e logs acessíveis dentro de Execução (gráfico ou Tabela e logs); nenhuma funcionalidade anterior removida sem substituto.

**Pendências desta entrega (próximas fases ou validação externa):**
- Capturas e percurso em navegador 1440/1280/947/390, claro/escuro, teclado e reduced-motion; comparação lado a lado com mockups 01/02 e protótipo 12/13/15/17.
- QA adversarial independente, smoke DEV (§7 c, d, e, j) e registro de fechamento com SHA publicado.
- F4: barra Salvar/Validar/Publicar no cabeçalho, painel de validação recolhível, biblioteca/inspector recolhíveis, desfazer/refazer, inspector com subseções em vez de modais frequentes.
- F5: inspector operacional com abas Resumo/Tentativas/Logs, estados/animações, polling condicionado ao benchmark, histórico com filtros e retorno, execução guiada sem JSON.
- F2: `pipeline-index` e lista unificada (fora desta entrega por decisão de escopo).
- Edição do nome amigável do pipeline e de responsável não existe no contrato atual; Identificação mostra ambos em leitura.
- Grupo de Configuração e vista da Execução ficam na URL (`grupo`, `vista`). Alterações locais seguem em cache de memória da aba, sem sobreviver a fechar o navegador; ao trocar Experiência ou Definição a sessão é outra (remonta, como antes).

**Fechamento (registro do Codex):** PR #499 integrada em `develop` `8a57ac6a` e publicada no DEV como 2.18.0. Smoke próprio PASS com duas sessões (incluindo a resposta 409 à sessão concorrente) e limpeza das fixtures; navegador PASS para saída pelo histórico e troca de Experiência com rascunho sujo. Sem motor/DataStage real e sem piloto com usuários. Estado das fases em [ux-pipeline-progresso.md](ux-pipeline-progresso.md).

## Entrega F4.1 — canvas amplo, painéis recolhíveis e barra de publicação (candidato 2.19.0)
Base `develop` `8a57ac6a`, branch `feat/ux-pipeline-montagem-f4`, migration 165. Montagem e Execução usam a largura da área de conteúdo (a moldura de 1600 px do shell era a causa das faixas laterais); Visão geral, Configuração e Versões conservam a largura anterior. Biblioteca e inspector recolhíveis sem perder seleção, vista, busca, formulário em edição ou posse; Salvar/Validar/Publicar no cabeçalho reutilizando a instância única de publicação; diagnóstico recolhível com resumo; Execução nomeia a fonte. Detalhes e limites nas [release notes](release-notes/2.19.0-pipeline-ux-montagem.md). Pendentes: F4.2 (desfazer/refazer, inspector em subseções), F5, F2 e F6.

F4.1 fechada: PR #500 integrada em `develop` `3900e7c2` e validada no DEV como 2.19.0.

## Entrega F4.2 — inspector em subseções, desfazer/refazer e modo focado (candidato 2.20.0)
Base `develop` `3900e7c2`, branch `feat/ux-pipeline-inspector-f4`, migration 166. A seleção mostra os campos principais do formulário real de cada um dos 11 tipos no inspector, com subseções Configuração, Etapa, Lineage e Avançado; os modais de configuração e lineage saem do percurso comum. Aplicar mescla só os campos alterados e recusa conflito; trocar de etapa com alterações pede confirmação. Desfazer/refazer local de até 50 passos com patches diferenciais, limpo ao salvar, recarregar, descartar ou trocar de sessão; valores protegidos fora do histórico (estado anterior e posterior conferidos). Modo focado na área do canvas e diagnóstico que abre a subseção do campo. Detalhes e limites nas [release notes](release-notes/2.20.0-pipeline-ux-inspector.md). Pendentes: navegador/QA independente e DEV deste candidato, F5, F2, F6 e o aceite integrado da F3.

F4.2 fechada: PR #501 integrada em `develop` `52843c6e` e publicada no DEV como 2.20.0.

## Entrega F5 — execução e investigação (candidato 2.21.0)
Base `develop` `52843c6e`, branch `feat/ux-pipeline-execucao-f5`, migration 167. A Execução usa o renderer da Montagem sem ferramentas de edição; inspector operacional à direita (Resumo, Tentativas, Logs, Parâmetros) com modo focado; Gráfico e Tabela alternativos; histórico sob demanda com filtros e paginação (`GET /pipeline-run-history`, leitura); executar guiado sem JSON com identificador estável; estados com ícone e rótulo, atividade só com telemetria ativa e `motion-safe`. A resposta só é usada se nomear este pipeline, a corrida e a data pedidas; confirmações de reprocesso, pausa e execução valem só para a sessão, a corrida, a etapa e a capacidade em que foram abertas. Leituras param com a aba oculta e revalidam ao voltar. No canvas comum, Enter na etapa focada seleciona como o clique (inspector e URL) e o reenquadramento é instantâneo com `prefers-reduced-motion`. Cadência de 30 s mantida: 5 s depende de medição de SQL/upstream/carga concorrente. Detalhes, validação e limites nas [release notes](release-notes/2.21.0-pipeline-ux-execucao.md). QA, segurança e visual finais do root aprovados no escopo do candidato; em PR para `develop`. Pendentes: revisão do SHA exato, DEV, prova nativa com a fixture própria SQL/Shell, DataStage real, piloto, F2, F6 e o aceite integrado da F3.

F5 integrada pela PR #502 (`develop` `e38bf7f8`) e publicada no DEV como 2.21.0. No smoke nativo com corrida própria, o root ratificou a primeira corrida, o histórico, o log e o snapshot. A pausa numa corrida `workspace__<uuid>` foi recusada (409 `corrida_sem_execution_id`).

### Correção 2.21.1 — pausa pela corrida exata (em PR)
Base `develop` `e38bf7f8`, branch `fix/ux-pipeline-identidade-pausa`, migration 168. Os gestos que resolvem o alvo por `_resolve_alvo_rerun` (pausa, prévia e reexecução) leem no Airflow a corrida exata pedida (`GET /dags/{dag}/dagRuns/{run_id}`) quando o run_id não traduz o `ts_nodash`. Isso só acontece depois das recusas existentes, com teto de 8 s e guardas de corrida, DAG e logical date UTC normalizada. Se falhar, a recusa de antes continua, e nenhuma outra corrida é usada. Detalhes nas [release notes](release-notes/2.21.1-pausa-corrida-exata.md). Revisão do root e QA independente aprovadas; UI idêntica à F5 pela prova canônica do root. Integrada pela PR #503 (`develop` `92d14d59`, head `6ce33c5c`) e publicada no DEV como 2.21.1 (migration 168). O smoke nativo de pausa, liberação e retry com a fixture própria do root está em andamento; o aceite nativo da F5 não foi aprovado.

### Correção 2.21.2 — tentativas do motor na investigação (candidato)
Executada como EOC-F1 da SPEC EOC (`docs/spec-experiencia-operacao-consolidada.md`, integrada pela EOC-F0), aprovada pelo usuário em 13/10/2026. Base `develop` `92d14d59`, branch `fix/ux-pipeline-tentativas-motor`, versão candidata 2.21.2, migration 169 candidata. Na fixture própria do root, o Shell com `retries=1` falhou duas vezes: o Airflow registrou `try_number=2`. A telemetria SQL ficou em 1 de 1, porque o ciclo operacional é contado pelo `log_start`, fora do retry. A tela só abria o log 1. Agora as abas Tentativas e Logs leem as tentativas do motor sob demanda (`GET /pipeline-task-attempts`, corrida e tarefa exatas, mesmo RBAC do log). O log segue o `try_number` comprovado pelo motor. O número SQL continua visível como tentativa operacional, com a origem explicada. Fila sem início, lacunas, tarefa mapeada e motor indisponível são ditos, sem estado presumido. Na EOC-F1, a leitura do Airflow passou a ser em blocos, com teto de 1 MiB por resposta. Ela para no bloco que ultrapassa o teto, fecha a resposta e cancela a leitura irmã. O contrato `/tries` foi conferido na fonte 2.11.2. Detalhes nas [release notes](release-notes/2.21.2-tentativas-motor.md). Pendentes: QA/segurança, PR, DEV e a prova nativa com a fixture; o aceite nativo da F5 segue não aprovado.

Integrada pela PR #505 (`develop` `f05bd4e9`) e publicada no DEV como 2.21.2 (migration 169); smoke real do root aprovado.

## Entrega F2 — descoberta e entrada única (candidato 2.22.0)
Base `develop` `f05bd4e9` (PR #505, EOC-F1), branch `feat/ux-pipeline-descoberta-f2`, migration 170. `GET /workspace/pipeline-index` no .NET une publicados e rascunhos ativos num lote SQL de um só comando. A collation real das colunas decide a igualdade entre grafias, e cada pipeline aparece numa linha, mesmo com publicado e rascunho. Filtros, situações que coexistem, paginação e ordem estável ficam no servidor. A posse só aparece quando válida e faz parte do resumo de todo leitor autorizado, inclusive sem `tela_jobs` (correção EOC-F2); o resumo não leva definição, layout, SQL, segredos, `fence` nem sessão. A 141 ausente gera 503 com o nome da migration. A leitura só vê dado confirmado e, num deadlock com autoria ou publicação, é sempre a vítima: roda em `DEADLOCK_PRIORITY LOW` num pool próprio. Só o erro 1205 é repetido, com a leitura inteira refeita, até 5 tentativas num prazo único de 10 s; esgotado, a resposta é 503 honesto (correção EOC-F2 do deadlock encontrado no SQL real do root). A leitura é feita em instruções curtas que não seguram lock de rascunho ou posse enquanto esperam a escrita: posse, ids ativos e resumo do rascunho são lidos à parte, e a página só compõe essas leituras (segunda correção EOC-F2, da contenção vista na segunda rodada nativa do root). A coorte da navegação contextual entra pela lista única: situação em texto, *Continuar montagem*, menu secundário coerente e consultas do cadastro publicado. A lista anterior continua para quem está fora da coorte e em *Lista clássica*. A criação essencial pede nome, identificador, projeto/domínio dos cadastros existentes e descrição; a agenda ficou na Configuração. Detalhes, validação e limites nas [release notes](release-notes/2.22.0-pipeline-ux-descoberta.md).

Pendentes desta entrega: os `[SqlFact]` do índice pelo root na imagem de teste nova (a rodada anterior reprovou por deadlock, causa desta correção; nenhuma aprovação SQL foi registrada ainda); revisão do Codex; passe visual combinado do root; imagem .NET de deploy pinada; e smoke DEV §7 b com fixture própria. Também ficam pendentes F6, DataStage real, piloto e o aceite integrado da F3. Nenhum índice novo de banco foi criado.
