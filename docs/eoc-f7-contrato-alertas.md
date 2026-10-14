# EOC-F7 — Contrato de alertas principais

SPEC aprovada: [alertas principais e EOC-F7](spec-experiencia-operacao-consolidada.md). Base DEV2.24.1, developd7299c24. Candidato2.25.0/migration177. F7 prepara contrato e prévia; F8 oferece o formulário, F9 persiste evento/intenção/tentativa e F10/F11 integram transportes. Nesta fase não há dispatcher, resolução corporativa ou envio.

## Política no mesmo draft e versão

`definition.alertPolicy` é uma extensão do contrato do workspace preservada por sua serialização existente. Não há tabela/editor paralelo. Salvar mantém o JSON; validar/publicar passa pelo adaptador de projeção, que bloqueia política desconhecida/inválida sem descartar a fonte. A versão imutável conserva o documento. Ausência de `alertPolicy` significa legado preservado; `null` explícito é inválido. Não aplicar configurações novas retroativamente às execuções antigas.

```json
{
  "schemaVersion": 1,
  "events": ["success", "warning", "failure"],
  "recipients": ["fixture@example.invalid"],
  "email": true,
  "teamsPersonal": true,
  "teamsChannel": {"groupId": 1},
  "attemptMode": "terminal"
}
```

Este exemplo é sintético. `teamsChannel` referencia cadastro existente por ID; não aceita webhook/token/URL no draft. O ID não comprova que o grupo existe/está ativo: a prévia não resolve destinos. E-mail e Teams pessoal são seleções independentes; o endereço não é uma API Teams nem comprova UPN/tenant/instalação.

Schema1: apenas os sete campos acima; eventos válidos únicos; até100 entradas de e-mail ASCII com limites320/64 e labels de domínio63; normalização corporativa em minúsculas e deduplicação por endereço; switches estritamente booleanos; groupId inteiro positivo até2147483647 ou null. Pelo menos um endereço quando E-mail/Teams pessoal está selecionado. Campos futuros e attemptMode não suportados impedem ativação; nada é truncado. Modo recuperável de tentativa não está habilitado no schema1, que trata resultado terminal.

Novos pipelines gerados pelo editor começam com `events/recipients` vazios, E-mail/Teams pessoal false, canal null e terminal. Flags legadas de comunicação de início/sucesso/falha também começam false, evitando envio por default antigo. Importações e edições de pipelines existentes conservam seus flags e tarefas. Presença da política nova não suprime alertas legados antes de um cutover explícito (F10); não há emissor novo que possa duplicá-los nesta fase.

## Prévia protegida, sem transporte

`POST /orquestra/workspace-adapter/alerts/{draftId}/preview`

```json
{
  "expectedRevision": 1,
  "fence": 1,
  "event": "failure"
}
```

`policy` opcional simula edição local sobre a revisão salva; não escreve o draft. Exige sessão Bearer, tela_pipelines+tela_jobs+acao_editar, revisão exata, rascunho ativo editável, ausência de publicação pendente e posse válida da mesma sessão/fence. Reutiliza guarded_draft; consulta transacional curta com rollback, sem write. Payload contextual limitado a1MB; unknown fields recusados. Falha de auth/permissão/posse não chama o simulador.

Resposta: `simulation:true`, `dispatch:false`, `destinationResolution:not_checked`, revisão de conteúdo, evento, lista/count de entregas hipotéticas e capabilities com causa. Um destinatário e os três canais selecionados geram3 itens; N pessoas geram N e-mails+N Teams pessoais+um canal por evento. Evento não selecionado gera0. Não retorna endereço, webhook ou corpo de mensagem; índices de destinatário são da lista normalizada. Ausência de política retorna modelegacy/countnull, não presume uma configuração vazia do legado. Falha422 usa code/field/detail fixos sem eco da entrada.

A prévia mostra o efeito da seleção; não garante entrega nem readiness. Nenhuma chamada SMTP/Graph/bot/webhook ocorre, nenhum destinatário é resolvido e nenhuma corrida/tarefa é iniciada.

## Evento, resultado e identidade

Envelope v1 puro: schemaVersion, pipeline, run, cycleGeneration, event, policyRevision, source, sourceStatus, sourceAt, receivedAt. Datas UTC explícitas ISO8601, sem inferir UTC de GETDATE do legado. Nomepipeline máximo200UTF-16, run250, source100. Estado terminal deve corresponder ao evento: SUCCESS/SUCESSO→success; WARNING→warning; FAILED/FALHA→failure. UP_FOR_RETRY não é falha definitiva. DELIVER_FAILED não cria Warning/Falha de processamento. Priorização/tratamento da ocorrência são outros contratos; não fazem parte desse resultado.

`event_contract` valida formato e produz eventKey determinístico. **Validar o envelope não autentica/certifica a autoridade.** Não existe endpoint público de emissão nem evento persistido nesta fase. A F9 deve conectar o adapter confiável antes de produzir eventos, com geração e timestamps reais. Contexto opcional de tasks/Malha/ODATE, IDs persistidos e auditoria serão tratados pelas respectivas fases, sem fabricar dados ausentes.

policyRevision = GUID da versão original + SHA256 do conteúdo normalizado da política. `policy_for_run` consulta somente o vínculo `etl_workspace_execucao → etl_workspace_versao`, nunca o publicado atual. Corrida sem vínculo retorna409 alert_run_unbound; indisponibilidade503 saneada. Reprocesso explícito usa outra cycleGeneration e mantém a policyRevision original mesmo que exista uma publicação posterior. Retry do motor não cria geração automaticamente. Chave de evento cobre pipeline/run/geração/evento/política; chave de entrega cobre evento/canal/referência efetiva protegida. F9 deve persistir unique guards e destinos efetivos; hashes sozinhos não são um dispatcher idempotente.

O gate atual de reprocesso da aplicação continua exigindo versão publicada compatível. A prova de política original não concede permissão para contornar esse gate nem executa reprocessamento.

## Fonte e capabilities honestas

Auditoria do factory: `_registrar_execucao` escreve SUCESSO/FALHA/PULADO/EXECUTANDO por run; Clear reaproveita run_id e altera a mesma linha. Não existe Warning agregado certificado nem geração operacional monotônica para Clear. Warning de job/mensagem não comprova resultado agregado do pipeline; transportes não são autoridade de processamento.

Por isso `result.available:false`, com origem/causa explícitas. E-mail e canal possuem transportes de tarefas existentes, mas alertas principais ficam indisponíveis até dispatcher/cutover F9/F10. Teams pessoal fica indisponível até provider, resolução/consentimento e tenant certificados em F11. Não fabricar Warning, geração1, sucesso pela ausência de falhas ou envio ao canal padrão. O adapter de resultado é um gate da F9, não uma certificação obtida por simulação F7.

Nós E-mail/Teams/Notificação permanecem tarefas customizadas independentes com SQL/templates/dados e seus tratamentos existentes. Esta política não os remove, não suprime o alerta principal futuro nem altera status/retry dos jobs.

## Validação, rollout e limites

Bancadas: schema/tipos/e-mail/header injection, campos futuros sem perda, default sem canais, fan-out com canal único, revisão original após outra política e identidades por geração/destino, envelope terminal/datas/UTF16, guardas e erros saneados, projeção mantendo flags/configurações. SQL real em banco descartável testa o JOIN original contra segunda versão e chaves diferentes; não cria run/reprocesso no Airflow. Prova DEV: criar/salvar draft próprio com policy, preview real3destinos/0evento não selecionado/guardas negativas/legado/unknownpolicy e limpeza; sem publicação/run/envio. Fontes `.NET`/DAGs/transportes permanecem inalteradas.

Deploy: backup verificado, migration177→2.25.0, API+dist; restart somente orquestra-api para carregar serviço/rota Python. Sem dependências, alteração de env, restart de worker ou .NET. Prévia está condicionada à flag existente de publicação workspace e à posse. Restaurar candidato anterior por PR/versão de correção se necessário; nunca apagar snapshots/execuções/DB/volumes. Main/produção exigem autorização própria. Artefatos e decisão QA em `/root/orquestra-eoc-evidencias/f7`.
