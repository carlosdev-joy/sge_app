> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Backlog proposto e critérios de aceite — experiência Pipeline

Data: 12/10/2026. Foco da referência: Informatica Cloud Data Integration (CDI), especialmente catálogo, taskflow designer, propriedades e monitoramento. Este documento propõe trabalho e aceite; não altera código, banco, motores ou contratos.

## Base e limites

Os IDs UX-01 a UX-12 são identificadores locais propostos. O backlog canônico `dbo.etl_backlog` não foi acessado; seu conteúdo e estado são desconhecidos. Antes de implementar, reconciliar duplicatas, responsáveis e status no backlog canônico. Os IDs não substituem as fases existentes.

Base documental SPEC: `docs/spec-ux-pipeline-profissional.md`, `docs/design/pipeline-experiencia.md`, `docs/matriz-paridade-pipeline.md` e README dos mockups, na revisão documental `52c0c589a3cf8f3dc5d7ee7c110a85416fd8fd85`. Base de código DEV: `92d14d596c95212d10bd30c3085edde4ce7c6b83`, auditada em leitura. As fases técnicas e as fases UX têm numerações próprias já ocupadas. F2 UX permanece pendente; F3, F4 e F5 UX têm implementação presente no código, mas aceite integrado F3, aceite nativo F5 e F6 UX continuam pendentes no registro consultado. F9 técnico histórico não fecha F6 UX atual.

Evidências UI referem-se exclusivamente às observações autorizadas encaminhadas na análise: UI-003–UI-020. Essas observações ocorreram por CUA. O endpoint REA 19222 estava inacessível e suas ferramentas ausentes; não atribuir a REA a inspeção da UI. Fonte DEV não certifica execução atual. Não foram produzidas medições de desempenho, acessibilidade ou QA da Informatica.

Esforço relativo: pequeno = revisão e QA em capacidade existente; médio = refinamento em vários componentes ou testes integrados; grande = dependência de API, migração de navegação ou coordenação operacional. Estimativas não são prazos. P0 identifica bloqueio do aceite/rollout; P1 melhoria central; P2 investigação ou escopo futuro.

## UX-01 — Descoberta unificada de publicados e rascunhos

- **Problema:** a listagem atual consulta `/pipelines`; novos rascunhos não têm descoberta unificada comprovada. O usuário pode criar trabalho e não reencontrá-lo pelo catálogo principal.
- **Resultado:** catálogo com identidade clara de pipeline, publicado/rascunho e caminho para continuar o trabalho autorizado.
- **Evidência:** DEV `Pipelines.tsx:51–61`, `DraftEndpoints.cs:31–35`; UI-003 mostra projetos, breadcrumb, busca e filtro; UI-005 busca por nome/descrição. DOC-INF02 documenta filtros de Explore, com leitura indexada parcial e HTTP 403 na abertura.
- **SPEC/escopo:** F2 UX real pendente, conforme spec UX e matriz. Não criar uma nova fase F2. Preservar permissões e campos do produto.
- **Prioridade/benefício/esforço:** P0; torna rascunhos recuperáveis e reduz caminhos paralelos. Grande: exige índice autorizado de publicados/rascunhos, além de listagem e estados de disponibilidade.
- **Dependências/risco:** contrato do índice, identidade pipeline/draft, RBAC, schema/flags. Risco de expor rascunho alheio ou duplicar publicado e rascunho como pipelines independentes.
- **Critérios verificáveis:** novo rascunho autorizado aparece e reabre a mesma identidade; pipeline com publicado e draft apresenta estado inequívoco; busca/filtro não perde identidade; ausência de permissão não retorna conteúdo restrito; catálogo indisponível produz estado de erro e recuperação, sem simular lista vazia.
- **Testes/evidência:** integração do índice com usuários autorizados e restritos; criação/reabertura; busca por nome/descrição; filtros e retorno ao catálogo; registros de IDs e capturas sem segredos.
- **DoD:** contrato aprovado, duplicata reconciliada no backlog canônico, cenários acima executados no ambiente-alvo e evidência ligada ao aceite F2.

## UX-02 — Entrada única do workspace com compatibilidade legada

- **Problema:** abas e alias já existem, mas a entrada legada Fluxo de pipelines depende de piloto/capability para desaparecer. Navegação única não está certificada para todos os públicos.
- **Resultado:** usuário autorizado chega ao workspace por uma entrada previsível; links antigos continuam encaminhando ao contexto correto.
- **Evidência:** DEV `nav.ts:47/97`, `workspaceTabs.ts:3–4/23`, `PipelineWorkspace.tsx:53/60`; cinco abas existentes. UI-003 é referência de navegação hierárquica; DOC-CTM01 apenas complementa separação entre definição e operação.
- **SPEC/escopo:** F2 UX; Visão geral, Montagem, Execução, Configuração e Versões. Edição de etapas somente em Montagem; Configuração edita pipeline. Não introduzir menu Etapas nem segunda faixa de modos.
- **Prioridade/benefício/esforço:** P0; reduz ambiguidades de entrada. Médio: compatibilidade de URLs, flags, capability e fallback exigem regressão combinada.
- **Dependências/risco:** UX-01, mapa de rotas/alias, política do piloto. Risco de quebrar favoritos ou permitir aba sem autorização.
- **Critérios verificáveis:** aliases etapas/fluxo/ferramentas chegam a Montagem do pipeline correto; contexto sem capability cai em aba autorizada; entrada legada segue política do piloto; navegação preserva identidade e guarda de alterações não salvas; nenhuma lista concorrente permite editar etapas.
- **Testes/evidência:** matriz de rota nova/antiga × permissionamento × flag; capturas de navegação e IDs; links diretos com sessão nova.
- **DoD:** compatibilidade demonstrada, política de visibilidade documentada e aceite F2 registrado, sem declarar a entrada única universal antes da verificação.

## UX-03 — Aceite integrado da sessão contextual e do estado não salvo

- **Problema:** sessão compartilhada, dirty e lease estão implementados, mas fonte isolada não prova o comportamento integrado entre abas e duas sessões.
- **Resultado:** editar Montagem/Configuração mantém o mesmo rascunho, informa posse e impede perdas ou gravação por sessão obsoleta.
- **Evidência:** DEV `PipelineWorkspace.tsx:86`, `WorkspaceEditor.tsx:74/86/90/97/104/163–167/214`; `SqlDraftRepository.cs:121/138/150–152/180–189`. UI-007 contextualiza propriedades; UI-008 mostra Save desabilitado na referência, sem provar sua regra causal.
- **SPEC/escopo:** aceite F3 UX existente; QA e correção de defeitos encontrados. Não reimplementar sessão. Cache em memória não implica persistência após fechar navegador.
- **Prioridade/benefício/esforço:** P0; protege trabalho e concorrência. Médio: coordenação entre UI, lease, fence, revisão e expiração real.
- **Dependências/risco:** ambiente com schema correto e duas sessões autorizadas. Risco de perda silenciosa, falso saved, conflito de revisão ou posse stale.
- **Critérios verificáveis:** trocar Montagem/Configuração mantém valores e dirty; salvar confirma revisão válida; sair/descartar/encerrar segue decisão explícita e não perde alterações silenciosamente; transferência de posse invalida fence antigo; sessão sem posse não grava; expiração/indisponibilidade informa bloqueio e recuperação; reabrir navegador não promete recuperação que o contrato não suporta.
- **Testes/evidência:** roteiro integrado com duas sessões, troca de aba, saída, save/reload, expiração e transferência; registrar draft/session/fence/revisão de forma segura.
- **DoD:** aceite F3 integrado documentado e defeitos corrigidos com regressão; sem promover mera existência de código a homologação.

## UX-04 — Polimento do canvas, inspector e adaptação de layout

- **Problema:** canvas comum, drag/conexão, inspector e histórico local já existem; precisam de validação visual e refinamento, sem substituir o editor real pelo protótipo.
- **Resultado:** biblioteca, canvas e propriedades mantêm hierarquia clara; nomes legíveis e ações alcançáveis em desktop, tablet e largura estreita.
- **Evidência:** DEV `WorkspaceEditor.tsx:224/231`, `WorkspaceCanvas.tsx:52–77`, `workspaceHistory.ts:6/54/64`; UI-006 biblioteca esquerda, canvas com dois Data Task/Parallel/Start/End; UI-007 abas de propriedades; UI-008 collapse/zoom; UI-009 1440, UI-010 947 e UI-011 390 documentam referências observadas, sem métricas de QA.
- **SPEC/escopo:** refinamento F4 UX existente e contrato visual. Preservar alternativa de clique/localizador, inspector real e limite/limpeza do histórico local.
- **Prioridade/benefício/esforço:** P1; melhora orientação e uso cotidiano. Médio: layout e estados de seleção atravessam biblioteca, canvas e painéis.
- **Dependências/risco:** critérios visuais vigentes e dados representativos. Risco de esconder ações, truncar nomes indistinguíveis ou permitir edição no canvas operacional.
- **Critérios verificáveis:** selecionar nó/aresta/painel mostra contexto correto; abrir/fechar inspector e zoom não oculta ações essenciais; nomes longos continuam identificáveis; em 1440/947/390 não há controle essencial inalcançável ou sobreposição impeditiva; Execução mantém renderer somente leitura; histórico não recupera valores protegidos descartados.
- **Testes/evidência:** capturas do produto Orquestra nas larguras acordadas, nomes longos, muitos nós, seleção e operação somente leitura; comparar com contrato visual, não medir a referência Informatica.
- **DoD:** diferenças justificadas e ajustes aprovados, sem copiar tokens, nomes de cliente ou contratos do fornecedor.

## UX-05 — Aceite de teclado, foco e controles do editor

- **Problema:** Enter, Delete guardado e alternativa ao drag aparecem no código, mas navegação por teclado e retorno de foco não foram reexecutados.
- **Resultado:** editar, selecionar e confirmar ações é possível com teclado; nenhum atalho dispara exclusão enquanto o usuário digita em campo.
- **Evidência:** DEV `WorkspaceCanvas.tsx:60/65–77`, biblioteca clicável em `WorkspaceEditor.tsx:224`. UI-008 documenta controles visíveis; não comprova suporte de teclado da referência.
- **SPEC/escopo:** aceite F4 UX, não implementação presumidamente ausente. Preservar permissões, seleção e confirmação.
- **Prioridade/benefício/esforço:** P0 para aceite; remove impedimentos de operação e exclusões acidentais. Médio: foco em canvas, campos, diálogos e painéis precisa ser testado como fluxo.
- **Dependências/risco:** UX-04 e sequência real de foco. Risco de foco perdido, trap, ação invisível ou Delete aplicado ao grafo durante digitação.
- **Critérios verificáveis:** foco visível e ordem coerente; controles têm nome acessível; inserir por clique/teclado oferece alternativa ao arraste; Enter atua somente no contexto esperado; Delete não altera grafo dentro de input/editor; confirmação devolve foco a alvo útil; usuário sem edição não ativa ferramentas mutáveis; validação é anunciada e alcançável.
- **Testes/evidência:** roteiro somente teclado, foco após cancelamento/remoção, campos com digitação, modo somente leitura e inspeção de nomes acessíveis; registrar falhas concretas.
- **DoD:** fluxo crítico concluído sem mouse e sem mutação indevida; correções com regressão associadas ao aceite F4.

## UX-06 — Diagnóstico contextual por campo e localizador

- **Problema:** diagnósticos e inspector existem; o caminho entre erro, etapa e campo necessita aceite para não obrigar o usuário a procurar manualmente no DAG.
- **Resultado:** diagnóstico direciona ao contexto resolvível, sem perder alterações nem esconder o erro original.
- **Evidência:** DEV `WorkspacePublication.tsx:31–38/54`, `WorkspaceEditor.tsx:231`; UI-007 inclui propriedades e Error Handling; DOC-INF01 mostra validation panel e diagnóstico de passos; DOC-ADF02 complementa detalhe de erro por atividade.
- **SPEC/escopo:** consolidação F4 e validação/publicação existentes. Localizador é navegação auxiliar; não criar segundo editor. Não converter status da referência em semântica Orquestra.
- **Prioridade/benefício/esforço:** P1; reduz tempo para localizar correção. Pequeno a médio: depende de qualidade dos identificadores de diagnóstico existentes.
- **Dependências/risco:** IDs estáveis de etapa/campo e mapeamento de validação. Risco de apontar campo errado ou sobrescrever dirty ao abrir painel.
- **Critérios verificáveis:** erro de pipeline leva a Configuração; erro de etapa seleciona nó/inspector e campo correspondente quando disponível; erro sem localização preserva mensagem e não inventa destino; avisos e bloqueios distinguem severidade; contexto e dirty persistem; publicar inválido não aparenta sucesso nem ignora validação do servidor.
- **Testes/evidência:** casos de campo ausente, edge inválida, diagnóstico de pipeline e retorno sem localização; registrar mensagem, target e revisão.
- **DoD:** mapa de diagnóstico verificado com exemplos reais, fallback documentado e defeitos encontrados tratados no backlog.

## UX-07 — Aceite operacional de execução exata, snapshot e tentativa

- **Problema:** operação exata e patch de pausa 2.21.1 estão no HEAD; smoke atual de pausa/liberação/retry permanece pendente. Um DAG correto visualmente não garante identidade operacional correta.
- **Resultado:** ações, estado, parâmetros e logs pertencem à execução/tarefa/tentativa selecionadas; snapshot histórico e fonte fallback ficam explícitos.
- **Evidência:** DEV `WorkspaceOperations.tsx:39/62–88/124/140–160`, `WorkspaceRunInspector.tsx:18/22/41/44/129–175`, `workspace_operations.py:74–80`, `execucoes.py:574/676/683–703`; UI-016 View Subtasks, UI-017 execução suspensa com Resume/Skip Resume/Stop visíveis, sem clique nem leitura de logs. DOC-DB01/02 documentam histórico de tarefas e alcance do reparo, como complemento.
- **SPEC/escopo:** aceite F5 UX e smoke patch 2.21.1. Não reimplementar snapshot, inspector ou pausa. Não transportar reprocessamento parcial/idempotência Databricks ao contrato atual.
- **Prioridade/benefício/esforço:** P0; impede ação sobre corrida errada. Grande para aceite: exige ambiente nativo, execução controlada, estados e tentativas reproduzíveis.
- **Dependências/risco:** permissões de operação/log, run e task reais, integração nativa e observabilidade. Risco crítico de alvo aproximado, cache cruzado, log de outra tentativa ou ação apresentada sem capacidade.
- **Critérios verificáveis:** resposta com pipeline/run divergente é recusada; snapshot usa corrida exata e jamais draft silencioso; ausência de snapshot rotula a publicada como fallback; seleção de tentativa muda consulta e saída corretas; vazio/erro de logs são distintos; pausa consulta/atua no alvo exato sem fallback aproximado; liberação/retry preservam contrato nativo; estado/ações respeitam RBAC; atualização segue cadência existente documentada de 30s e visibilidade, sem prometer 5s.
- **Testes/evidência:** smoke controlado pausa/liberação/retry; duas execuções concorrentes com IDs distintos; troca de tarefa/tentativa; resposta divergente, snapshot ausente e erro de logs; evidência backend/UI sem conteúdo sensível.
- **DoD:** smoke 2.21.1 e aceite nativo F5 registrados; pendências externas declaradas com dono e impacto. Até lá, status: implementado no código, aceite pendente.

## UX-08 — Preservação dos 11 tipos e das oito agendas

- **Problema:** tipos, formulários especializados e agendas já existem; redesign pode reduzir campos, mudar payload ou apagar opções desconhecidas em round-trip.
- **Resultado:** experiência refinada conserva capacidade funcional e configuração previamente válida.
- **Evidência:** DEV `workspaceCatalog.ts:2–4`, `SharedJobConfiguration.tsx:66/68`, `SpecializedConfiguration.tsx:80–84`, `pipelineUtils.ts:3–9`, `WorkspacePipelineFields.tsx:19–35`, `WorkspaceConfiguration.tsx:28–29`; UI-014 templates apenas vistos, não criados; UI-015 New Asset cancelado; UI-020 Mapping Task consultado com seções Task Details, Task Mapping, SQL ELT, Advanced Session, Mapping Image, Input Parameters, Transformations With Connections, Task Schedule, Email Notification Options e Advanced Options. Edit visível não clicado, Run desabilitado; agenda/notificações em accordions de leitura, sem copiar valores. DOC-INF01 templates não equivalem aos tipos Orquestra.
- **SPEC/escopo:** matriz de paridade e complemento técnico já implementado. Onze tipos: DataStage, SQL, Python, Shell, Stored Proc, HTTP, Decisão, Aguarde, Notificação, E-mail e Valida Arquivo. Agendas: daily, weekly, monthly, biweekly, hourly_n, custom, monthly_days_times e on_demand. Não criar novos tipos nem reduzir catálogo.
- **Prioridade/benefício/esforço:** P0 para paridade; evita regressão funcional. Grande para QA abrangente: variedade de formulários, valores protegidos, parâmetros e agendas.
- **Dependências/risco:** fixtures válidas, schema/adaptadores e integrações disponíveis. Risco de perda de campos avançados ou alteração de cron/horários; testes de formulário não certificam sistemas externos.
- **Critérios verificáveis:** cada tipo abre, edita e salva os campos contratados; cancelar não grava staging; valores protegidos não reaparecem no undo; desconhecidos avançados são preservados; cada agenda mantém valores e payload ao reabrir; monthly_days_times respeita limite existente de cinco dias e pares dia/hora; on_demand não cria disparo periódico; aplicação e ambiente de destino continuam distintos; catálogos indisponíveis informam erro.
- **Testes/evidência:** matriz 11 tipos × operações básicas e oito agendas × round-trip; comparação de payload antes/depois e cron quando aplicável; execução externa separada e somente onde autorizada/disponível.
- **DoD:** matriz preenchida com passou/falhou/não verificado e justificativa; nenhuma célula desconhecida é marcada aprovada por existência de código.

## UX-09 — F6 UX: aceite por três públicos, desempenho e rollout

- **Problema:** homologação histórica técnica e capturas de protótipo não constituem aceite UX atual nem piloto operacional dos três públicos.
- **Resultado:** montagem, operação e governança são aprovadas por representantes dos públicos previstos na spec; rollout tem critérios, responsáveis e reversão verificável.
- **Evidência:** DEV `docs/ux-pipeline-progresso.md:7–15` e `workspace-homologacao-f9.md:52–58`; `useWorkspaceCapabilities.ts:7`, autorização/flags em `Program.cs:91–97`. UI-009–UI-013 ajudam a formular cenários, mas não são medições de desempenho. DOC-DB03 documenta risco de densidade em matriz, não capacidade Orquestra.
- **SPEC/escopo:** F6 UX real pendente. Usar os três públicos da spec e suas permissões reais; não conceder ações por persona ou experiência. Fases F8/F9 técnicas já ocupadas permanecem referência histórica.
- **Prioridade/benefício/esforço:** P0 para rollout; transforma implementação em evidência de uso. Grande: coordenação de usuários, ambientes, cenários, medidas e suporte.
- **Dependências/risco:** UX-01–08, disponibilidade dos públicos e ambiente-alvo; critérios de desempenho aprovados antes do teste. Risco de aprovação genérica, dataset irreal ou piloto sem caminho de reversão.
- **Critérios verificáveis:** cada público conclui seus fluxos autorizados e explica contexto/estado/versão; negadas permanecem negadas via UI e API; dataset representativo e medidas de abertura, interação e atualização são registrados; limites/limiares são acordados antes da execução, sem inventar números; piloto registra flag/capability, coorte, observação e suporte; desligar piloto preserva dados/contratos e compatibilidade; pendências externas possuem responsável e decisão de bloqueio ou restrição.
- **Testes/evidência:** roteiro assinado por público; logs técnicos saneados; capturas, dataset/tamanho/ambiente/versão; medições de Orquestra identificadas como novas e separadas da referência; ensaio de reversão.
- **DoD:** aceite F6 registrado com restrições explícitas; decisão de ampliar piloto baseada em critérios cumpridos, não em código presente ou captura de Informatica.

## UX-10 — Avaliar novos escopos em propostas independentes

- **Problema:** referências e protótipo ilustram capacidades além do contrato atual; incorporá-las ao polimento comprometeria paridade, prazo e backend.
- **Resultado:** oportunidades ficam registradas e avaliadas separadamente, sem alterar payload ou motores do Pipeline atual.
- **Evidência:** manifesto documental identifica owner/fuso/timeout/concurrency50 ilustrativos; DEV confirma versão/diff/restauração já existentes em `WorkspaceVersions.tsx:13–21`; UI-018 Show Dependencies e UI-019 Uses/Used By vazios apenas demonstram controles/resultados observados. DOC-INF01 subtaskflow; DOC-ADF02 fuso; DOC-DB04 triggers avançados/Beta são referência, não contrato.
- **SPEC/escopo:** proposta futura separada: fuso selecionável, timeout configurável, taskflow embutido, malha versionada, agendas/gatilhos avançados e customização apresentacional de colunas do catálogo. DB-009 sustenta existência desse controle Databricks, sem provar persistência de preferência ou suporte Orquestra. Não implementar neste escopo, não reutilizar fases ocupadas, não apresentar diff/restauração atuais como novidade.
- **Prioridade/benefício/esforço:** P2; permite evolução sem regressão contratual. Pequeno para descoberta/documentação; implementação não estimável até contrato e dependências serem definidos.
- **Dependências/risco:** patrocinador, spec própria, impacto de payload/migração/autorização e reconciliação canônica. Risco de copiar limite de fornecedor, confundir dependência visual com execução embutida ou alterar semântica de agenda.
- **Critérios verificáveis:** cada oportunidade explicita problema, usuário, capacidades atuais, contrato novo, riscos e alternativa; fuso define origem/exibição/DST; timeout define aplicação e efeitos; embedding define limites/ciclo/versionamento; malha define baseline e execução; agenda avançada distingue Beta de capacidade estável; nenhum campo novo é enviado pelo trabalho atual.
- **Testes/evidência:** revisão de contrato e levantamento de suporte backend; critérios de teste futuros escritos, sem resultados simulados; comparação com fonte oficial rotulada.
- **DoD:** registro proposto reconciliado no backlog canônico antes de implementação e decisão explícita de escopo. Proposta não é compromisso de entrega nem autorização para mudanças no produto.

## UX-11 — Glossário semântico e nomenclatura de mercado

- **Problema:** Pipeline, Job, taskflow, etapa e execução têm significados diferentes entre fornecedores. Usar a palavra de mercado sem explicitar seu objeto pode confundir configuração, grafo, disparo e tentativa.
- **Resultado:** vocabulário canônico para Orquestra e mapa de equivalências parciais nos materiais de comparação, conforme [glossário](../geral/glossario-e-nomenclatura.md).
- **Evidência:** SPEC já fixa Montagem/Execução/Configuração/Versões; DEV possui pipeline/run/task/attempt separados. DB-002 distingue Jobs/Pipelines no catálogo; DB-004/005 distingue tarefa, dependência e condição. [Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/) define job como recurso que coordena tarefas em DAG; [Spark Declarative Pipelines](https://docs.databricks.com/aws/en/ldp/) trata de processamento declarativo, não é sinônimo desse job. DOC-INF01 taskflow e DOC-CTM03 condição/evento complementam a comparação documental.
- **SPEC/escopo:** refinamento editorial proposto; não renomear campos, entidades, endpoints ou fases ocupadas. Pipeline é a composição Orquestra; Etapa é unidade configurada; Run/execução é instância identificada; Tentativa é execução de tarefa dentro do contexto contratado. Job, taskflow, condition e event devem conservar a acepção do fornecedor quando citados. DAG descreve grafo acíclico e não promete ausência de ciclos sem contrato verificado.
- **Prioridade/benefício/esforço:** P1; melhora compreensão e suporte. Pequeno: revisão de rótulos, ajuda e documentação; médio apenas se surgirem alterações de UI aprovadas.
- **Dependências/risco:** revisão de produto/operação e UX-07 para identidade runtime. Risco de chamar um run de tentativa ou de converter equivalência conceitual em interoperabilidade prometida.
- **Critérios verificáveis:** glossário contém Pipeline, Etapa, Run, Tentativa, Job, DAG, taskflow, condition e event; cada termo informa objeto, contexto e equivalências não exatas; UI/documentos distinguem definição e instância; exemplos de dois runs e duas tentativas não trocam seus IDs; tradução de nomes de fornecedor permanece rastreável; glossário não cria suporte a embedded taskflow/eventos externos.
- **Testes/evidência:** revisão terminológica dos fluxos críticos e exercício de compreensão com os públicos F6; registrar ambiguidades encontradas e decisão de rótulo, sem inventar resultado de pesquisa.
- **DoD:** glossário aprovado e referências editoriais alinhadas; qualquer mudança funcional segue item próprio e backlog canônico.

## UX-12 — Gate de comparação prática e cobertura Premium

- **Problema:** a nova rodada Databricks cobre configuração autenticada em Free Edition, mas não comprova execução, logs, reparo ou RBAC Premium. Control-M foi observado em três tours guiados; o motor real não foi ensaiado; a comparação prática completa permanece pendente.
- **Resultado:** matriz de cobertura por produto/edição/jornada, com lacunas explícitas antes de concluir comparação Premium; detalhamento em [jornadas Databricks](../referencias/databricks/jornadas-e-execucoes.md).
- **Evidência:** DB-001 Home apresentou aviso de navegador automatizado não suportado; navegação padrão funcionou, sem contorno. DB-002 catálogo vazio com filtro por nome/ID, Jobs/Pipelines e Customize Columns. DB-003 job criado por autosave antes das tarefas e renomeado com Enter; DB-004 tipo de tarefa e Save Task explícito; DB-005 dependência True e Run if All succeeded. DB-006 preview de gatilhos Scheduled/File arrival/Table update/Continuous/Model update; Scheduled Interval 1 Day e estados Active/Paused vistos, diálogo cancelado sem salvar. DB-007 sidebar Parameters/Tags/Health/Notifications/Permissions/Advanced/Queue/Max concurrency apenas em leitura. DB-008 Runs vazio, com indicação de últimos 60 dias. DB-009 catálogo carregado mostra ORQ_UX_DEMO, All/Jobs/Pipelines e Owned by me/Accessible by me/Favorites; Customize Columns contém Name, Type, Tags, ID, Run as, Created by, Tasks, Compute, Trigger, Trigger details e Recent runs. Nenhuma preferência alterada; campos não observados não integram a evidência.
- **SPEC/escopo:** atividade comparativa adicional, sem ocupar numeração de fases existentes e sem ampliar requisitos atuais. Única criação autorizada: `ORQ_UX_DEMO`, com duas tarefas If/else literais, `avaliar_condicao` (1 == 1) e `confirmar_dependencia` (2 == 2), aresta True e All succeeded, salvas. Nenhuma execução, agenda ou dado externo; futuras ações mutáveis/executáveis exigem autorização específica.
- **Prioridade/benefício/esforço:** P1 para concluir cobertura comparativa; não bloqueia por si só correções já contratadas em Orquestra. Médio a grande: depende de acesso a edições/ambientes e Control-M, não apenas trabalho editorial.
- **Dependências/risco:** ambiente Premium autorizado, representante de Control-M e roteiros equivalentes. Risco de extrapolar Free para Premium, confundir controle visível com eficácia ou afirmar operação a partir de Runs vazio.
- **Critérios verificáveis:** cada jornada registra edição, data, ações feitas e não feitas; criado/salvo é distinto de executado; preview cancelado não conta como agenda; Permissions visível não certifica RBAC; logs/reparo ficam não verificados; Control-M distingue tour guiado de console operacional; o relatório não declara comparação prática integral ou certificação Premium antes de completar os gates; nenhuma barreira de automação é contornada.
- **Testes/evidência:** revisar DB-001–DB-012 e inventário do único artefato criado; quando houver acesso autorizado, acrescentar captura/roteiro real com identidade de edição e resultado de cada jornada. Execução, agenda e recursos externos não fazem parte do teste atual.
- **DoD:** cobertura completa por recorte autorizado ou entrega parcial explicitamente aceita com lacunas; status atual: Databricks configuração prática parcial, Premium operacional não certificado, Control-M guiado observado; motor real pendente. Nenhuma conclusão de sucesso integral da comparação.

## Fontes oficiais e notas de origem

- DOC-INF01: [Taskflow for Orchestrating your Data Integration tasks](https://www.informatica.com/content/dam/informatica-cxp/techtuesdays-slides-pdf/Advanced%20Taskflow%20for%20Data%20Integration.pdf), PDF oficial aberto; treinamento histórico, não comprova UI atual. Sustenta templates, designer, propriedades, publicação, My Jobs e Monitor.
- DOC-INF02: [CDI Taskflows, novembro/2024](https://docs.informatica.com/content/dam/source/GUID-8/GUID-89D0C881-8DA9-4C78-A348-61C72A98256F/56/en/CDI_November2024_Taskflows_en.pdf), trecho oficial indexado da página 135; abertura HTTP 403. Sustenta Explore e versão publicada usada no agendamento, com limite de leitura parcial.
- DOC-INF03: [CDI Permissions](https://docs.informatica.com/integration-cloud/cloud-data-integration/current-version/asset-management/project-and-asset-management/permissions.html), trecho indexado, abertura HTTP 403. Leitura/edição/execução são conceitos de referência; não definem RBAC Orquestra.
- DOC-INF04: [Monitoring taskflow status with the status resource](https://docs.informatica.com/integration-cloud/cloud-data-integration/current-version/taskflows/taskflows/monitoring-taskflow-status-with-the-status-resource.html), trecho indexado, abertura HTTP 403. API de status não prova UX nem implementação Orquestra.
- DOC-DB01: [Monitor Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/monitor), aberto; atualizado em 08/10/2026. DOC-DB02: [Troubleshoot and repair job failures](https://docs.databricks.com/aws/en/jobs/repair-job-failures), aberto; atualizado em 09/10/2026. Complementam execução/tentativa e alcance de reparo.
- DOC-DB03: [Jobs with a large number of tasks](https://docs.databricks.com/aws/en/jobs/large-jobs), aberto; atualizado em 11/09/2026. DOC-DB04: [Automate jobs with schedules and triggers](https://docs.databricks.com/aws/en/jobs/triggers), aberto; atualizado em 06/10/2026. Limites/Beta permanecem específicos do fornecedor.
- DOC-ADF01: [Visual authoring](https://learn.microsoft.com/en-us/azure/data-factory/author-visually), aberto; atualizado em 25/03/2026. DOC-ADF02: [Visually monitor Azure Data Factory](https://learn.microsoft.com/en-au/azure/data-factory/monitor-visually), aberto; complementam inspector e diagnóstico; sem equivalência com Fabric.
- DOC-CTM01: [Control-M Navigation](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Navigation.htm) e DOC-CTM02: [Monitoring Navigation](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Monitoring_Navigation.htm), ambos abertos; complementam separação de definição/operação e causas de espera. Datas editoriais não explicitadas.

Consulta inicial das fontes em 12/10/2026, América/São Paulo; rodada adicional Databricks conforme registro das jornadas. As páginas oficiais Lakeflow Jobs e Spark Declarative Pipelines foram abertas para conferir nomenclatura (ambas atualizadas em 09/10/2026). Observações UI-/DB-, documentação oficial, fonte DEV e inferências de proposta são evidências distintas. Este documento não contém resultados de execução Databricks, smoke Orquestra atual, carga, integração externa ou aprovação de usuários. Control-M acrescenta os tours guiados CTM-006–CTM-008; nenhuma execução real foi feita.




## Atualização após autorização de execução e estudo da Malha

O estado atual inclui DB-011/012: primeira tentativa real falhou com tarefas puladas; segunda, com notebook fictício adicional, concluiu Succeeded em17s e mostrou total30. Graph/Timeline/List foram inspecionados. As declarações anteriores de histórico vazio/ausência de execução descrevem a rodada inicial. Repair/retry, carga e RBAC premium continuam não ensaiados.

Control-M CTM-006–010 inclui cinco tours guiados: Build a workflow, Error handling, Reference folder, Forecast e Self-Healing. As pendências anteriores de liberação estão resolvidas. Sem console operacional, nenhum job real Control-M foi executado. A nova proposta de composição, configuração, operação, recursos e governança está em [12-malha-conceitos-e-reestruturacao.md](../modulos/malhas/conceitos-e-reestruturacao.md); amplia o estudo, sem reclassificar recursos novos como SPEC Pipeline existente.
