> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Jornadas observadas no Informatica Data Integration

Rodada de leitura em 12/10/2026. Evidências UI em [registro-ui.md](../../evidencias/registro-ui.md). Identidade da organização, assets, projetos e corridas omitida. “Observado” descreve a interface; não descreve sua implementação interna.

## J1 — Entrar no serviço e escolher a intenção

**Passos:** página Home autenticada → ler produto atual → abrir seletor de serviços → fechar seletor → continuar em Data Integration.

**Observação direta — UI-001/002:** Home apresenta entradas Ingest, Transform e Orchestrate com explicações curtas, além de assets recentes e acesso a My Jobs. O cabeçalho identifica produto e organização. O seletor reúne serviços em um diálogo; sua presença não prova licença nem acesso a todos.

**Ponto forte:** entrada por intenção reduz a necessidade de conhecer o tipo técnico antes de começar. Recentes oferece retomada contextual.

**Dificuldade:** várias sugestões e produtos competem pela atenção. Para o Orquestra, criar/retomar pipeline e investigar corrida devem ser entradas claras, sem um catálogo de serviços novos.

**Aplicabilidade:** melhorar descoberta/retomada na lista F2; não incluir telas de ingestão/qualidade apenas por aparecerem no fornecedor.

## J2 — Encontrar um taskflow

**Passos:** Home → Explore → Projects and Folders → abrir opções do catálogo → Asset Types → Find Asset → procurar tipo Taskflow → Taskflows → Find com termo demonstrativo → Enter → escolher asset demonstrativo.

**Observação direta — UI-003/004/005:** o catálogo combina breadcrumb, tipo, localização, status e ações por linha. A pesquisa Find informa que retorna nome e descrição. Existem filtros adicionais, ordenação, seleção e paginação; colunas oferecem indicação de redimensionamento. O seletor de Explore expõe Projects and Folders, Asset Types, Tags e Metering Tags. Apenas as duas primeiras perspectivas foram percorridas; tags foram inventariadas.

**Decisão:** o leitor escolhe uma perspectiva e reduz a lista antes de entrar no objeto. Buscar asset e localizar sua pasta são caminhos complementares.

**Feedback:** contagem/título da perspectiva muda após carregar; um snapshot imediato pode ainda representar a tela anterior. A confirmação usou o estado estável posterior, não o primeiro retorno da automação.

**Ponto forte:** localização e status estão na mesma lista. **Dificuldade:** nomes técnicos extensos e ações por ícone tornam descoberta e truncamento importantes. Não houve benchmark de tempo nem teste de todas as colunas.

**Orquestra:** F2 deve oferecer uma linha por identidade técnica segundo collation, com publicado/draft/lease coexistentes. Projetos/domínios continuam cadastros reais, não uma árvore de pastas nova por semelhança.

## J3 — Ler e selecionar no desenho

**Passos:** abrir taskflow demonstrativo → reconhecer Start/End e dois Data Tasks em caminhos paralelos → selecionar Data Task 1 → observar destaque e propriedades → Zoom In → recolher painel inferior.

**Observação direta — UI-006/007/008:** biblioteca vertical à esquerda, canvas dominante, toolbar e propriedades abaixo. A biblioteca inclui Assignment, Data Task, IntegrationOps Task, Notification Task, Command Task, File Watch Task, Ingestion Task, Subtaskflow, Decision, Parallel Paths, Jump, Throw, Wait e End. São tipos do fornecedor, não componentes automaticamente disponíveis no Orquestra.

O nó selecionado recebe contorno azul; o painel muda para a etapa escolhida. Zoom/recolhimento não habilitaram Save. As propriedades recolhidas liberaram altura ao desenho. Não foi arrastado, incluído, recortado, colado, removido ou reconectado nenhum nó.

**Pontos fortes:** seleção contextual, distinção entre controle de navegação e comandos mutantes, painel que pode devolver espaço ao canvas.

**Dificuldades:** labels truncados na biblioteca; parte do canvas não aparece semanticamente na árvore de acessibilidade usada; controles de tamanho expõem chaves internas de internacionalização nessa árvore. Isso sugere atenção à acessibilidade, mas não certifica o comportamento com leitor de tela.

**Decisão para Orquestra:** preservar inspector lateral do contrato e os onze tipos reais. Reutilizar WorkspaceCanvas/NodeProperties e manter alternativa por clique/localizador ao drag. Start/End ilustrativos não viram jobs executáveis fictícios.

## J4 — Entender as propriedades da etapa

**Passos:** seleção Data Task 1 → General → ler organização das abas → abrir Error Handling → consultar rótulos e opções, sem modificar.

**Observação direta — UI-007:** abas General, Data Task, Input Fields, Events e Error Handling. Tratamento de aviso e erro aparece em grupos diferentes, com opções Ignore/Suspend Taskflow e controles de falha ao concluir quando a tarefa falha ou não roda. Os valores da organização não foram registrados.

**Ponto forte:** decisões técnicas relacionadas ficam agrupadas no inspector. **Limite:** não foram copiados expressões, vínculos, scripts, conexões, valores ou payloads; regras de aplicação/save não foram testadas.

**Orquestra:** reorganizar sobre SharedJobConfiguration/SpecializedConfiguration sem alterar o significado de retry, Aguarde, decisão ou falha técnica. Não transportar “Ignore”, “Suspend” ou “Skip” do fornecedor para o motor atual. Aplicar≠Salvar≠Publicar deve permanecer explícito conforme a SPEC.

## J5 — Conhecer opções de criação sem criar

**Passos:** Templates → observar categorias/busca → New → Orchestration → observar Taskflow → Data Integration → observar tipos → Cancel. Em ensaio separado: New → Escape → conferir foco no gatilho New.

**Observação direta — UI-014/015/021:** New Asset abre diálogo por categorias. Em Orchestration, Taskflow descreve o controle de múltiplas tarefas CDI. Em Data Integration, aparecem Data Transfer Task, Dynamic Mapping Task, Mapping, Mapping Task e Mapplet. Cancel não criou objeto. Escape fechou o diálogo e devolveu foco ao botão New.

**Ponto forte:** descrição ajuda a distinguir objeto de lógica e tarefa configurada. **Dificuldade:** a primeira categoria aberta não deve ser assumida como a intenção do usuário. Templates e Create ficaram sem acionamento.

**Orquestra:** começar em branco com identificação essencial, conforme mockup04 e SPEC. Templates novos ou subtaskflows são novo escopo. Não adicionar uma taxonomia que substitua os onze tipos.

## J6 — Navegar dependências e detalhes de configuração

**Passos:** retornar ao taskflow → menu adicional → ler Unpublish/Properties Detail/Run Using/Show Dependencies → escolher apenas Show Dependencies → Uses → Used By → retornar a Uses → abrir Mapping Task demonstrativa → consultar seções → expandir Task Schedule/Email Notification Options.

**Observação direta — UI-018/019/020:** dependências têm perspectivas Uses/Used By e tabela com tipo/localização/status. Used By apresentou zero dependentes nesse asset. A Mapping Task abriu uma página de **consulta**, com Edit visível e Run desabilitado. Seus grupos incluem Task Details, Task Mapping, SQL ELT Optimization, Advanced Session Properties, Mapping Image, Input Parameters, Transformations with Connections, Task Schedule, Email Notification Options e Advanced Options.

**Pontos fortes:** configuração extensa não exige ocupar permanentemente o canvas; dependências têm direção explícita. Há relação de asset para tarefa referenciada, diferente de aresta executável do fluxo.

**Limites:** Edit não foi acionado; configuração confidencial e referências de conexões não foram copiadas. Agenda completa e confirmação de publicação continuam documentais. “Used By vazio” só vale para o objeto/consulta selecionados, não para a organização.

**Orquestra:** Configuração concentra agenda/governança/parâmetros. Lineage e dependências devem informar origem/autoridade; uses de asset não se confunde com predecessor de pipeline ou dependência assinada pela Malha.

## J7 — Investigar por My Jobs e Monitor

**Passos:** My Jobs → ler vazio e carimbo → Filter → Add Field → observar critérios → abrir Monitor/CDI → Running Jobs → View Subtasks → All Jobs → escolher instância existente → Current Run.

**Observação direta — UI-012/013/016/017:** My Jobs estava vazio nesta sessão, com “No data to display”, busca/filtro, Refresh e atualização em PDT. Seus critérios incluem asset, tipo, duração, erro, localização, linhas, ambiente e horários. Isso não significa que não existam execuções na organização.

O **Monitor**, destacado pelo usuário, ofereceu Running Jobs e All Jobs do Data Integration. All Jobs tinha histórico acessível e paginação. View Subtasks abriu a lista correspondente à instância. Um detalhe Current Run apresentou status Suspended, identidade de instância, horários/duração, usuário e ambiente, além de desenho e duração de passos. Os valores foram omitidos.

Resume from faulted step, Skip faulted step and resume, Stop e Download Log estavam visíveis. **Nenhum foi acionado**. A existência de botão não valida sua guarda de servidor. Input Fields estava disponível como aba, mas valores não foram extraídos. Logs e mensagens de negócio não foram baixados nem copiados.

**Ponto forte:** o objeto operacional é uma instância identificada, com drill-down para passos/subtarefas. **Dificuldade:** My Jobs e Monitor são entradas distintas; o vazio de uma não deve ser comunicado como ausência global. Horários devem sempre informar origem/fuso.

**Orquestra:** Execução concentra histórico e investigação do pipeline; monitores globais existentes continuam entradas complementares. A seleção usa pipeline/run/version/task/attempt e mantém origem/retorno à Malha. Não criar um segundo grafo divergente para imitar a separação de serviços do Informatica.

## J8 — Verificar distribuição de espaço

**Passos:** designer em largura original → propriedades recolhidas → 1440×960 → 947×800 → 390×844 → restaurar viewport.

**Observação direta — UI-009/010/011:** desktop/intermediário permitem ver o pequeno fluxo com painel recolhido. Em 390 px, a lateral e biblioteca consumiram grande parte da largura; o canvas ficou estreito demais para avaliar o desenho. A largura do documento permaneceu 390, o que não certifica usabilidade. Após restaurar viewport houve composição estreita residual do iframe na observação; não foi reaberta a página para estabelecer reprodução de um defeito persistente.

**Orquestra:** manter o contrato de drawers/painéis adaptáveis e modo focado. Exigir teste funcional a 1440/1280/947/390, não apenas ausência de overflow. Gráficos grandes, nomes longos, conexão e configuração devem continuar acessíveis.

## Jornadas que permanecem documentais ou pendentes

| Jornada | Conhecido | Validação necessária |
|---|---|---|
| Criar→salvar→validar→publicar | Controles visíveis e treinamento oficial DOC-INF01 | Demo autorizada; nesta organização não executar |
| Publicação e agenda | DOC-INF01 e suplemento indexado DOC-INF02; Task Schedule em consulta | Editor de agenda e confirmação sem mutação; registrar limites de edição/trial |
| Conflito/lease/versões | Não observado no Informatica | Sessões demonstrativas próprias; não presumir mecanismo interno |
| Falha→retry→log | Corrida suspensa e ações visíveis; docs de monitoramento | Log sanitizado de fixture e autorização para operação real em ambiente próprio |
| Comparar histórico/tentativas | All Jobs e Current Run observados; detalhes adicionais documentais | Escolher corridas de fixture, estabelecer versão e tentativa sem adivinhar |
| Acesso restrito/carregamento/erro | Estados de vazio diretamente observados; carregamento transitório percebido | Perfil autorizado de leitura e ensaio controlado; sem provocar falhas na organização |

Não há métricas cronometradas de tempo/passos humanos, entrevista de usuário ou teste de leitor de tela. Os passos acima descrevem a navegação realizada, sem contar retries da automação como fricção comprovada do produto.
