> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Preservação funcional e validação da proposta provisória

Este documento transforma a comparação em critérios de preservação e provas necessárias. É proposta de validação, sem alteração do produto nem novas execuções. Código atual: develop `92d14d596c95212d10bd30c3085edde4ce7c6b83`. Referência documental: `52c0c589a3cf8f3dc5d7ee7c110a85416fd8fd85`. Implementação encontrada por fonte não significa runtime certificado. DEV, SQL, upstreams, catálogos externos e backlog vivo não foram acessados nesta auditoria.

As cinco abas e Configuração única, lease compartilhada, inspector real, desfazer/refazer, canvas e investigação F5 já existem no código. Os IDs UX-01–UX-12 usam os significados canônicos do documento05: descoberta, entrada/compatibilidade, sessão/dirty, canvas/painéis, teclado/foco, diagnóstico por campo, operação exata, paridade11/8, aceite F6/desempenho, novo escopo premium, glossário e gate comparativo, respectivamente. A descoberta unificada F2 permanece pendente; smoke nativo completo da pausa/liberação/retry F5 e aceite integrado F3 aparecem pendentes nos registros. Recomenda-se consolidá-los antes do piloto F6.

O usuário ampliou a análise para ensaios práticos em Databricks gratuito e Control-M free/trial antes de fechar a estrutura premium customizável. Databricks tem agora observação prática parcial de descoberta/autoria/configuração, com duas tarefas fictícias salvas na demonstração autorizada `ORQ_UX_DEMO`; não houve Run, agenda, dados ou corridas. Control-M foi observado nos tours guiados CTM-006–CTM-008; validação do motor real continua pendente e as propostas comparativas permanecem provisórias. Nenhum requisito premium novo é apresentado como obrigação já existente da SPEC. As restrições documentadas da edição gratuita Databricks, inclusive uso não comercial e5tarefas concorrentes, limitam o ensaio daquela edição e não estimam capacidade ORQUESTRA.

Fonte: [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations), atualizada29/09/2026 e aberta12/10/2026 em America/Sao_Paulo (13/10 em UTC); são5tarefas de job concorrentes por conta, não5pipelines ORQUESTRA.

Prioridades canônicas do documento05: P0 bloqueia aceite/rollout; P1 é melhoria central; P2 é investigação/escopo futuro. UX-01/UX-02/UX-03/UX-05/UX-07/UX-08/UX-09 são P0 nos aceites correspondentes; UX-04/UX-06/UX-11/UX-12 são P1; UX-10 é P2. O gate comparativo UX-12 não bloqueia por si só correções já contratadas.

## Autoridade, campos e destinos

1. Configuração edita atributos do pipeline; Montagem edita etapas/arestas/layout; Execução consulta snapshot/corrida e oferece somente ações autorizadas; Versões compara/restaura conforme contrato. Visão geral resume com atalhos. Não criar segundo editor de etapas ou segunda faixa Montagem/Execução.
2. Aplicar incorpora campos do inspector ao estado local. Salvar persiste revisão. Validar examina revisão salva. Publicar mantém intenção durável, hash e confirmação do motor. Executar usa configuração publicada. Esses eventos e autoridades não são intercambiáveis.
3. Preserve campos desconhecidos, chaves adicionais, defaults, nulls, tipos, ordem/casos de decisão e referências protegidas em todo round-trip. Editar um campo não recria o payload a partir de formulário reduzido. Compare somente transformação explicitamente pretendida.
4. Segredos/defaults Encrypted não entram em definição/layout, cache de histórico, URL, logs, IA ou evidências. Mantenha endpoint write-only/referência imutável e baseline histórico comprovado; cancelar não aplica referência. Nenhum GET resolve valor protegido.
5. Datas lógica/operacional, timestamps UTC da posse e horários da telemetria conservam origem/regras existentes. Fuso selecionável ou timeout global ilustrados no protótipo não recebem chave nova silenciosamente.
6. A experiência Desenvolvimento/Consulta/Sustentação escolhe entrada e apresentação; capabilities do servidor, flag/schema e sessão governam ação. Nunca inferir privilégios pelo perfil demonstrativo.

Fonte dos destinos: `workspaceTabs.ts:3–4`; instância única `PipelineWorkspace.tsx:86`; grupos `WorkspaceConfiguration.tsx:19–29`; guarda do editor `WorkspaceEditor.tsx:78–107`; servidor `DraftEndpoints.cs:17–26` e `Program.cs:91–97`.

## Onze tipos de etapa: mapa de preservação

Cada linha requer fixture sanitizada de configuração completa antes/depois, inclusive campos desconhecidos e defaults. Prova de formulário não certifica integração externa. Toda aplicação exige posse atual/revisão/identidade; leitura operacional usa dados autorizados daquela versão/corrida.

| Tipo | Campos/capacidades existentes a conservar | Destino e componentes | Contrato/guarda a preservar | Prova necessária e limite |
|---|---|---|---|---|
| DataStage | Job, conexão SSH, parâmetros declarados/importação, vínculos, campos DataStage e lineage; consulta explícita de grafia no projeto do draft | Montagem → Configuração/Parâmetros/Lineage; SharedJobConfiguration, JobTypeFields, importadores, WorkspaceLineage | `configuration.legacyJob`, tabelas de parâmetros/lineage; projeto do draft, não substituição por cadastro ativo; referências protegidas | Round-trip + consulta catálogo indisponível/disponível; importar/cancelar/aplicar com revision/fence; teste real DataStage/InformationServer depende ambiente próprio e não foi realizado |
| Python | Modos arquivo existente/módulo/inline, SSH quando exigido, interpretador, recurso/código e opções de arquivo destino; parâmetros/vínculos | Montagem → Configuração; JobTypeFields/Python via SharedJobConfiguration; editor ampliável | Transformação pythonFromApi/pythonToApi e python_json; preservar modo/defaults/chaves adicionais; código como texto, sem execução na prévia por inferência | Testar três modos/condicionais, erros de recurso/conexão e round-trip; executar somente fixture própria autorizada quando plano exigir; não copiar scripts de referência |
| Shell | Comando, conexão SSH conforme contrato e parâmetros/políticas atuais | Montagem → Configuração; SharedJobConfiguration/JobTypeFields | legacyJob/comando/parâmetros, escaping de texto e posse; não converter command para payload de outro tipo | Round-trip e UI claro/escuro; drag/click, aplicar, salvar, reload; execução remota somente ensaio próprio separado |
| Stored Proc | Procedure, conexão MSSQL, banco, parâmetros nome/tipo/valor e vínculos | Montagem → Configuração/Parâmetros; SharedJobConfiguration/JobTypeFields | Identidade da procedure, tipos SQL, nulls/defaults e conexões existentes | Fixture com parâmetros adicionais e vazio/null; catalog error/legacy value; integração MSSQL desconhecida nesta análise |
| HTTP | URL/comando e opções realmente suportadas no contrato | Montagem → Configuração; JobTypeFields | Preservar opções existentes; não introduzir métodos/auth/headers novos pela referência | Round-trip de payload atual e validações; chamada remota não necessária para provar composição, deverá ser identificada como integração quando testada |
| SQL | Consulta, conexão, banco, política falhar/publicar resultado nulo, parâmetros e prévia autorizada | Montagem → Configuração; SpecializedConfiguration/PainelSql | Configuração SQL e política existentes; preview não grava publicado; resposta atrasada não descreve configuração nova | Fixtures com consulta/múltiplos campos/erro/nulo; prévia cancelada e erro upstream; não usar consulta de negócio; integração real exige plano/ambiente |
| Decisão | Condição/origens, Sim/Não, Switch, casos/ordem/default, saídas e simulação de ramo | Montagem → Condição/Saídas; SpecializedConfiguration/PainelDecisao | Configuração e arestas alteradas juntas; rename atualiza referências; ciclo/ramo inválido recusados | Testar adicionar/mover/remover caso/trocar modo/renomear; preservar branches/edges/unknowns; simulação local não certifica avaliação real de condição |
| Aguarde | Todas com sucesso/todas terminarem; dependências e conectar pontas soltas | Montagem → Liberação/Dependências; PainelAguarde/attachLooseEnds | Não fabricar sucesso nem ciclo; política “terminarem” distinta de todas-sucesso; arestas preservadas | Fixtures de paralelismo/falha/skipped e ligação de pontas; comprovar regra local e motor separadamente |
| Valida Arquivo | Configuração completa, regras, conexões, diretórios e prévia | Montagem → Validação; PainelValidaArquivo e `/workspace-adapter/valida-arquivo/preview` | Contrato estático F7B: grafo/config e diretórios String/Pathname fixos do draft; sem consultar SSH/banco/arquivo/secrets | Testar catálogo, payload/regras, cancelamento/atraso; marcar prévia estática explicitamente; presença/frescor arquivo real requer ensaio próprio |
| Notificação | Grupo Teams, modelo/template e mensagem; regras de parâmetros existentes | Montagem → Comunicação; PainelNotificacao | Referências reais a catálogo, fallback/indisponibilidade, staged/cancel | Round-trip e catálogo mock/real identificado; envio real só autorizado em ambiente/teste específico, não nesta análise |
| E-mail | Modelo ou corpo livre permitido, HTML, assunto, destinatários/herança, placeholders, anexo autorizado e prévia | Montagem → Comunicação; PainelEmail | Herança/validações/segurança HTML e anexo existentes; desconhecidos preservados; prévia não envia | Fixtures modelo/livre/HTML/herança/placeholders/anexo; prévia isolada e valores protegidos ausentes; envio não exercitado. Backlog versionado139 contém expansões de seletor/linha/ODATE, status vivo desconhecido |

Fontes: `workspaceCatalog.ts:2–4`; `SharedJobConfiguration.tsx:24–68`; `SpecializedConfiguration.tsx:26–30,46,80–84`; `NodeProperties.tsx`; `workspaceJobFields` e `workspaceSpecialized`. A tabela preserva os11tipos técnicos; categorias demonstrativas de extração/transformação/qualidade/entrega não os substituem.

## Oito agendas: equivalência e prova

| Modalidade | Campos/regras a manter | Verificação local/contrato | Prova de integração necessária |
|---|---|---|---|
| Diário (`daily`) | Hora/minuto, scheduled_time, calendário/dias úteis quando aplicáveis | Carregar→editar hora→salvar→recarregar; campos não editados equivalentes | Cron/agenda publicados iguais para fixture e sem disparo inadvertido |
| Semanal (`weekly`) | Dia da semana e hora; regras existentes de calendário | Todos limites/valores aceitos; legacy value intacto; não converter ordinal do dia arbitrariamente | Comparar dias/cron gerados e data operacional |
| Mensal (`monthly`) | Dia/hora e limites atuais (formulário1–28) | Limites/invalid input e default; preservar payload adicional | Comparar cron e ocorrências em meses distintos, sem inventar regra de fim de mês |
| Quinzenal (`biweekly`) | Dia da primeira quinzena1–13, horário e regra atual das duas ocorrências |1/13 aceitos,0/14 recusados conforme servidor; round-trip sem perda | Conferir dias gerados/cron, não substituir por intervalo genérico de15dias |
| A cada N horas (`hourly_n`) | Intervalo1–23, hora inicial/final0–23, minuto0–59; normalização para custom/horários | Conferir horários resultantes/limites/janela; persistência equivalência após reload | Comparar janela/hora-minuto/cron; reconhecer representação persistida custom sem perder modo funcional |
| Horários específicos (`custom`) | Lista de horários e dias da semana; normalização/validação | Vários horários, duplicatas/invalids conforme regra existente; não apagar dias omitidos | Cron/dias equivalentes após publicação |
| Dia + Hora Específico (`monthly_days_times`) | Até5dias, dias1–28, vários horários; estrutura dias_horarios_mes | Editor estruturado adicionar/remover/limites; JSON normalizado conserva dados | Confirmar ocorrências por dia/hora, inclusive lista múltipla; texto livre protótipo não substitui editor |
| Sob demanda (`on_demand`) | Ausência de agenda automática; execução manual separada | Nova criação/round-trip sem horário automático fictício | Confirmar publicado sem agendamento e corrida somente quando solicitada/autorizada |

Fonte: `pipelineUtils.ts:3–9`; `WorkspacePipelineFields.tsx:19–35`. Para todas: manter data inicial da DAG, virada ODATE, calendário de feriados, dias úteis, predecessores/janelas, não-iniciar-antes e limite de aviso. Comparar tabelas relacionadas e CSV em conjunto, preservar linhas/chaves assinadas pela Malha. Catálogo indisponível não vira lista fictícia; valor legado ausente da lista continua visível/intacto.

Agenda≠pausa do motor≠ativo/inativo. Inativação publicada exige motivo conforme contrato. Falha técnica não libera dependentes como sucesso; política sem movimento mantém semântica existente. Responsável/fuso selecionável/timeout global adicionais da proposta exigem campo comprovado ou spec separada.

## Sessão, publicação e ações operacionais

| Capacidade | Invariante e fonte atual | Teste/evidência que falta nesta análise |
|---|---|---|
| Iniciar/renovar lease | Um draft ativo/uma posse; servidor decide tempo; `SqlDraftRepository:134–142,208–217`; editor renova `WorkspaceEditor:86–90` | Duas sessões disputam, uma recebe409; expiração/perda conexão preserva local; carimbo servidor |
| Trocar abas | Mesmo WorkspaceEditor/key entre Montagem/Configuração; formulário montado/hidden conserva staging; `PipelineWorkspace:86`, `WorkspaceEditor:214` | Alterar etapa e agenda, trocar várias vezes, lease/fence/revisão únicas; não adquirir posse adicional |
| Transferir/encerrar | Administrar+editar e fence crescente; save anterior recusado; `SqlDraftRepository:146–154,185–189` | Transferência autorizada/negativa; sessão antiga mantém trabalho mas não grava; confirmação dirty/unapplied |
| Aplicar/salvar | Mesclar somente campos tocados; revision/fence/identidade atuais; staging separado; `WorkspaceEditor:107,163,231` | Form aberto enquanto outro dado muda; conflito explícito; save não incorpora staging não aplicado; erro conserva local |
| Sair/recarregar/descartar | Guarda dirty||unapplied e mesmo workspace; reload/descartar confirmam; `WorkspaceEditor:104,165,167` | Link/back/history/experiência/fonte/version/reload; cancelar conserva estado; confirmação e foco corretos |
| Desfazer/refazer | Últimos50patches locais; sem side effects externos; proteção limpa histórico; `workspaceHistory:6,54,64` | Agrupamento texto/último passo/foco; não armazenar segredo/ref nova; limpar conforme sessão/save/reload |
| Validar | Revisão salva/diagnóstico por campo e etapa; erro/aviso distintos; `WorkspacePublication:29,37–54` | Diagnóstico abre etapa/campo; invalidação após edit/revisão; amplo grafo sem perder seleção |
| Publicar/retomar | Intent/idempotência/hash/gates; only estado publicado confirma; `WorkspacePublication:26–44`, PublicationEndpoints:8–10 |202→projeção→geração→confirmado/erro; reload retoma operação; retry mesma intenção; interrupção reconciliada |
| Gates publicado | Execução ativa/comando pendente impede publicação; escrita legada gerida bloqueada; histórico imutável | Prova transacional SQL/API com fixture própria e plano, sem tocar pipelines existentes |
| Versões/restore | Diff duas versões; restore publicada cria novo draft, não reescreve histórico; `WorkspaceVersions:13–21` | Comparar node/edge/layout/unknown/ref; restore sem captura histórica comprovada em consulta; gates/dep CSV preservados |
| Solicitar corrida | Só publicada/capability; identidade estável run; recebido≠fila≠executando; `WorkspaceOperations:94,125` | Capturar run retornado e seleção, evitar clique repetido; DAG pausada pode aguardar; nenhuma atividade antes telemetria |
| Aceitar resposta | Match pipeline/corrida/data; resposta antiga não troca desenho/seleção; `WorkspaceOperations:62–88`, `workspaceExecution:31–40` | Respostas invertidas/atrasadas entre datas/runs/sessões; negativa mantém source label não confirmada |
| Usar snapshot | Join pipeline/run/version; fallback publicado rotulado; `workspace_operations.py:74–80`, `WorkspaceOperations:75–82` | Corrida histórica mantém desenho imutável; sem snapshot admite desconhecido; draft nunca usado para executar |
| Log/tentativa | token/pipeline/run/task/attempt compõem cache e request; attempt pertence à corrida; `WorkspaceRunInspector:41,129–130,163–164` | Trocar tentativa/run enquanto consulta; velho log não aparece; texto escapado/vazio/error/403; não capturar conteúdo sensível |
| Reprocesso/pausa | Intenção congelada pela sessão/pipeline/data/run/stage/capability; task_id real e guard antes POST; `WorkspaceRunInspector:172–175` | Abrir modal, trocar contexto/capability; POST recusado; cascade prévia; corrida antiga/versão incompatível negadas |
| Corrida exata pausa | Consulta exata Airflow após guardas, timeout/timestamp normalizado; `execucoes.py:574,676–703` | Smoke próprio pause→release→retry, especialmente run `workspace__uuid`; falha upstream não escolhe corrida substituta. Pendente F5 nos registros |
| Atualizar | Poll30s visível, leituras suspendem aba oculta; fonte indisponível não anima; `WorkspaceOperations:66,74,112` | Ocultar/retornar aba, stale/reconnect, sem perder zoom/inspector; 5s só após orçamento medido SQL/upstream |
| Autorizar | Flags/schema/Bearer+perms reais; experiência não concede; `Program:91–97`, DraftEndpoints:17–26, OperationEndpoints:15–16 | Negativas UI/API edit/publish/execute/log/admin; revogar sessão; catálogo indevido não acessível; nenhum segredo no payload |

Os nomes arquivo:linha acima são relativos ao repositório auditado. Não são links a um checkout externo obrigatório para o leitor; a base SHA identifica a fonte. Fontes de execução não examinadas em runtime continuam desconhecidas, inclusive status do backlog `dbo.etl_backlog`.

## Matriz de validação por jornada

“Necessária” abaixo significa prova para aceite futuro, não teste executado nesta entrega. Preferir cenários reais relevantes aos contratos; não escrever testes que apenas repetem JSX/implementação. Dublês provam fronteiras de UI e contratos, não o motor.

| ID | Percurso/falha | Dados e método | Resultado exigido | Evidência a registrar |
|---|---|---|---|---|
| V01 | Criar→voltar lista→retomar | Draft próprio, projeto/domínio real autorizado; F2 índice | Uma linha, draft encontrado sem DAG/cadastro ativo artificial | Requests/respostas sanitizados, SHA/version, capturas lista |
| V02 | Publicado+draft/pesquisa/paginação | Fixture duplicidade/collation/search filtros | Uma linha por pipeline, total/offset consistentes, cancelamento busca | Contrato .NET/SQL e queryplan/carga do índice quando aplicável |
| V03 | Editor/refrescar posse | Duas sessões/perfis | Editing só lease válida; leitor encontra draft sem definition se sem tela_jobs | Negativas e badges, sem token |
| V04 | Configurar11tipos | Fixtures completas incluindo unknown/default/null | Alteração alvo somente; sem perda de informação/ref/edge | Diff sanitizado por tipo, payload antes/depois |
| V05 | Agendas8modalidades | Casos limites e publicação própria sem disparo | Mesmos cron/dias/ODATE/calendário/CSV relacionados | Tabela por modalidade e evidência SQL/gerador |
| V06 | Catálogo indisponível/legacy | Conexões/projeto/calendário/parâmetros | Valor legado conserva-se; erro claro sem dados fictícios | Capturas leitura/erro e contrato response |
| V07 | Biblioteca/drag/clique | Montagem editável/read-only |11tipos adicionáveis apenas com posse; posição/ID corretos | Vídeo/captura e round-trip local/save |
| V08 | Delete/aresta/rename/ciclo | Seleção node/edge/input; decisão Switch | Confirmação, referências/casos/layout preservados; ciclo recusado | Testes de regra e roteiro teclado/canvas |
| V09 | Organizar/ordem/importar | Grafo paralelo e importação com unknowns | Layout não altera dependência/prioridade; import aplica ao draft | Diff de layout/execution_order/grafo |
| V10 | Inspector staging | Alterar campo, trocar etapa/cancelar/aba | Aplicar≠salvar; troca confirma; foco/campo apropriado | Capturas e estado da revisão/dirty/unapplied |
| V11 | Montagem↔Configuração | Dirty nos dois e lease renovando | Mesma posse, conteúdo e revisão; overlay oculto inerte | Requests lease e percurso navegador |
| V12 | Save conflict/falha/reload | Revision antiga, fence antigo, desconexão |409 sem sobrescrita; trabalho local preservado e reconciliação explícita | Negativas API e captura erro/local |
| V13 | Transferir/expirar | Admin e sessão antiga | Fence cresce; sessão antiga negada; nenhum privilégio por experiência | Eventos sanitizados e respostas negativas |
| V14 | Sair navegador/history | Dirty/unapplied/back/experiência/fonte | Guarda e cancelar mantêm trabalho; confirmar descarta corretamente | Roteiro foco+navegação |
| V15 | Undo/redo50/protegido | Patches texto/grafo/layout e ref nova | Limite50; sem segredo; foco último passo não perdido | Teste regra e navegador, sem valores |
| V16 | Validar→diagnóstico→corrigir | Erro de cada família/campo | Abre destino canônico/field; revisão velha invalida resultado | Captura etapa+erro e response revision |
| V17 | Publicar/reload/retry | Fixture ociosa e interrupção controlada | Intent único, hash/version confirmados, erro recuperável | OperationID/hash/state, sem SQL de negócio |
| V18 | Guarda publicação×run | Fixture própria e concorrência planejada | Conflito explícito, sem artefato divergente | Prova SQL transacional/API e reconcile |
| V19 | Versão/diff/restore | Snapshots com dep/lineage/ref desconhecidos | Histórico imutável; nova draft; desconhecido read-only | Diff/versões/hash e motivos |
| V20 | Run solicitado/pausado | Fixture própria SQL/Shell autorizada no plano | Run retornado selecionado; solicitado/fila/início distinguíveis | RunId/date/version + timeline fonte |
| V21 | Running/success/paralelo | Mesma fixture e telemetria confirmada | Verde apenas sucesso daquela tentativa; paralelismo real | Transições disponíveis API e capturas iguais |
| V22 | Failure/retry/skipped | Fixture deliberada própria | Histórico tentativas intacto; skipped≠sucesso executado | Tentativas/duração/fonte/estados |
| V23 | Histórico snapshot/fallback | Corrida versionada e legacy | Nunca desenha draft; fallback explícito; fonte identifica limite | Run/version e comparação snapshots |
| V24 | Resposta atrasada | Dublê com pipeline/date/run invertidos | Velho dado não substitui contexto | Bancada de contrato/UI e captura aviso |
| V25 | Logs por tentativa | Conteúdo sintético + integração própria | Identity correta, texto escapado, erro/vazio separados | IDs/request e prova renderer; não incluir logs sensíveis |
| V26 | Reprocesso guard/preview | Modal abrir→contexto/capability mudar | Intenção invalida antes POST; cascade/restrição corretas | Negativas, escopo e efeitos esperados |
| V27 | Pausa exata/liberação/retry | Run próprio `workspace__uuid` | Alvo exato/timestamp normalizado; falha não escolhe outra corrida | Smoke nativo F5 e registro de limpeza |
| V28 | Frescor/poll/oculto | Perder fonte/aba ocultar/retornar | Último dado rotulado; animação suspensa;30s; revalida sem reposicionar | Requests/cadência/carimbo e captura fonte indisponível |
| V29 | Perfis e negativas | Dev/Consulta/Sustentação + funções acumuladas | UI e API concordam; sem editar/publish/run por experiência | Matriz capabilities/401/403/409 sanitizada |
| V30 | Deep links/retorno Malha | Aliases fluxo/etapas/logs/execucoes/parametros/ferramentas | Pipeline/run/date/stage/attempt/origem preservados | Casos URL sem segredo e retorno |
| V31 | Desktop1440/1280/947/390 | Mesma fixture/tema/seleção | Canvas útil, biblioteca/inspector acessíveis; sem overflow global | Capturas comparáveis, diferenças registradas |
| V32 | Teclado/foco/reducedmotion | Enter/Delete/Escape/Tab/undo/zoom/modal | Seleção acessível, Delete fora input, foco retorna, motion respeitado | Roteiro navegador e resultado por tecla |
| V33 | Carga50/100/300 | Bancada pareada/rota fria/método constante | Orçamento existente seleção300p95<200ms, rota<300KiBgzip; não INP campo | Amostras/método/bytes/carga concorrente; SQL/upstream separado |
| V34 | Piloto tarefas três públicos | Representantes reais, mesma jornada | Sucesso/tempo/retornos/dúvidas registrados; pendências explícitas | Roteiro/observações anonimizadas e aceite por critério |

## O que as referências demonstram e o que não demonstram

CUA confirmou composição do designer (UI-006), propriedades de Data Task e tratamento de warning/error em leitura (UI-007), zoom/minimização sem Save habilitar (UI-008), lists/filtros (UI-003/UI-012/UI-013/UI-016/UI-017), dependências Uses/UsedBy (UI-018/UI-019). UI-020 consultou resumo Mapping Task por Uses, com TaskDetails/TaskMapping/imagem/input/conexões/agenda/notificações/opções avançadas; expandir TaskSchedule/EmailNotification conservou leitura, Edit não clicado e Run desabilitado. Essa observação apoia preservação de campos/catálogos UX-08 e inspector UX-04; não prova editor Mapping, valores de configuração, novas conexões ou regra de herança equivalente ao ORQUESTRA.

UI-021 comprovou somente o gesto Escape no modal New Asset: fechou e retornou foco ao botão New, sem criar objeto. É referência concreta para V32, sem certificação de acessibilidade completa. Conforme esclarecimento do usuário e UI-016/UI-017, Monitor inclui execução ativa e histórico All Jobs; My Jobs vazio UI-012 não representa ausência de histórico do produto.

### Databricks: evidência prática parcial e exceção autorizada

O root observou sessão Free Edition pelo navegador. Um aviso informou detecção de controle automatizado e sugeriu uso manual/Genie One; Jobs & Pipelines funcionou por navegação normal, sem desabilitar proteções. Essa limitação deve constar junto das evidências; não invalida os gestos efetivamente observados nem comprova superfícies bloqueadas.

| Evidência | Gesto e resultado confirmado | Aplicabilidade à preservação | Limite da prova |
|---|---|---|---|
| DB-001 | Home Free Edition com Jobs & Pipelines/Runs/Workspace/Recents | UX-01/UX-02, encontrar/retomar; UX-11 vocabulário | Não certifica entrada premium ou todos serviços |
| DB-002 | Jobs & Pipelines vazio, busca nome/ID, radios Jobs/Pipelines, Customize Columns e cards de criação | V01/V02/UX-01: vazio acionável/filtros | Customização inteira não exercitada; cards não autorizam conectores novos |
| DB-003 | Create Job persistiu objeto antes da primeira task; rename Enter salvou | UX-01/UX-03: distinguir criação, conteúdo, dirty e persistência | É mutação externa explicitamente autorizada, não modelo de publicação ORQUESTRA |
| DB-004 | Catálogo20tasktypes; duas If Else com literais1==1/2==2, Save Task explícito | V04/V10: formulário por tipo e feedback de persistência | Outros tipos só listados; AI Runtime disabled; sem notebook/código/dados/integração |
| DB-005 | Segunda depende `avaliar_condicao` true, Run If All Succeeded; grafo2tasks e aresta true; Save Task disabled após salvar | V08/UX-04/UX-03/UX-08: ramo preservado e dirty preciso | Dependência salva, não avaliada em execução |
| DB-006 | Types Scheduled/File Arrival/Table Update/Continuous/Model Update; Active/Paused e Interval/Schedule/Every1Day preview; Cancel | V05/UX-08: agendas reais; novos triggers seguem UX-10 | Nenhum Save/trigger; calendar/fuso não inspecionados; gesto Schedule falhou e não repetido |
| DB-007 | Sidebar Details/Triggers/Job Parameters/Tags/Health Thresholds/Notifications/Permissions/Advanced Settings (Max Concurrent Runs/Queue) em leitura | UX-03/UX-08: sessão/configuração e campos preservados; novos campos seguem UX-10 | Nenhuma permissão/setting alterada; presença não prova RBAC premium, queue ou threshold funcionando |
| DB-008 | Runs vazio últimas60dias, Run Now não clicado | V20–V28/UX-07: sem dados não inventar corrida | Nenhum repair/log/tentativa/transição/execução observado;60dias não vira retenção local |
| DB-009 | Após reload, catálogo confirma ORQ_UX_DEMO; All/Jobs/Pipelines, Owned by me/Accessible by me/Favorites e menu Customize Columns com identificação/autoria/tarefas/compute/triggers/recent runs | V01/UX-10: persistência do objeto e apresentação customizável | Nenhuma preferência alterada; personalização deve permanecer separada de definição/agenda/payload/capabilities e não vira obrigação SPEC |

Autorização específica do usuário permitiu somente criar `ORQ_UX_DEMO` com `avaliar_condicao` e `confirmar_dependencia`, usando condições fictícias e sem Run/agenda/dados. A demonstração foi persistida; não se afirmar análise exclusivamente sem mutação externa. Informatica permaneceu sem mutação. Não houve alteração de código ORQUESTRA nem novo smoke DEV/SQL/upstream; V01–V34 continuam provas necessárias para o produto, não resultados herdados da referência.

Coberturas B drag/Delete não executadas; D salvar/validar/publicar/concorrência apenas controles/documentos; E agenda/retries/timeouts incompletos; F logs/tentativas/transições não observadas. Resume/SkipResume/Stop/DownloadLog estavam visíveis e não foram acionados; logs externos não foram lidos.390 sem overflow global com canvas estreito não certifica uso mobile. Templates/NewAsset foram consultados e cancelados, sem criar objetos. A observação usa CUA autorizado; REA indisponível não pode ser apresentada como evidência REA.

Documentação oficial sustenta padrões de contexto/monitoramento/inspector: [Informatica taskflow, treinamento histórico](https://www.informatica.com/content/dam/informatica-cxp/techtuesdays-slides-pdf/Advanced%20Taskflow%20for%20Data%20Integration.pdf), [Databricks monitor](https://docs.databricks.com/aws/en/jobs/monitor), [Databricks repair](https://docs.databricks.com/aws/en/jobs/repair-job-failures), [ADF visual authoring](https://learn.microsoft.com/en-us/azure/data-factory/author-visually), [ADF visual monitoring](https://learn.microsoft.com/en-au/azure/data-factory/monitor-visually), [Control-M monitoring](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Monitoring_Navigation.htm). Semânticas específicas desses produtos não são contratos ORQUESTRA. Fontes Informatica Permissions/Scheduling/Status com abertura403 são evidência parcial indexada, não certificação de interface atual.

## Sequência de aceite e fechamento

- F2 descoberta/entrada (UX-01/UX-02): implementar/validar contrato já definido e percurso criar→retomar, sem fazer pipeline ativo só para aparecer na lista.
- F5/F3 (UX-07/UX-03): consolidar prova nativa própria pausa→liberação→retry, corrida/snapshot/log/histórico e percurso salvar→publicar→executar→investigar; reconciliar documentos históricos de candidato com SHA realmente publicado. Preservação11/8 é UX-08.
- F4 (UX-04/UX-05/UX-06): polimento canvas/painéis, teclado/foco e diagnóstico por campo. F6 (UX-09): piloto com três públicos/desempenho/rollout; registrar limites upstream/Caixa/IA/performance campo. Só declarar critérios cuja evidência exista.
- UX-01–UX-09 refinam/comprovam requisitos vigentes; UX-10 identifica novos escopos independentes; UX-11 trata glossário e UX-12 cobertura comparativa. Nenhum ID é fase nova. Malha versionada, monitores completos, IA integral, novos conectores, bypass/cancelamento geral, fuso/timeout sem campo e main/produção mantêm escopo próprio.
- UX-11: revisar glossário dos termos task/job/pipeline/workspace por produto sem renomear identidade técnica. UX-12: concluir observação prática CTM free/trial e registrar os limites operacionais Databricks; depois revisar cobertura e fechar proposta premium customizável UX-10 separadamente da SPEC. DB sem corridas não certifica repair/logs/execução.

Backlog canônico é `dbo.etl_backlog` de produção; nesta análise, seu estado é desconhecido. Documentos/migrations indicam intenções históricas, não status vivo. Nada foi escrito ao backlog, banco ou repositório do ORQUESTRA. Houve apenas a criação externa Databricks explicitamente autorizada descrita acima; Informatica continuou em leitura. O resultado são documentos de proposta e provas necessárias.



## Atualização após autorização de execução e estudo da Malha

O estado atual inclui DB-011/012: primeira tentativa real falhou com tarefas puladas; segunda, com notebook fictício adicional, concluiu Succeeded em17s e mostrou total30. Graph/Timeline/List foram inspecionados. As declarações anteriores de histórico vazio/ausência de execução descrevem a rodada inicial. Repair/retry, carga e RBAC premium continuam não ensaiados.

Control-M CTM-006–010 inclui cinco tours guiados: Build a workflow, Error handling, Reference folder, Forecast e Self-Healing. As pendências anteriores de liberação estão resolvidas. Sem console operacional, nenhum job real Control-M foi executado. A nova proposta de composição, configuração, operação, recursos e governança está em [12-malha-conceitos-e-reestruturacao.md](../modulos/malhas/conceitos-e-reestruturacao.md); amplia o estudo, sem reclassificar recursos novos como SPEC Pipeline existente.
