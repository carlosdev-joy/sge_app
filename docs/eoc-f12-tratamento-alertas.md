# EOC-F12 — Gestão e tratamento das falhas

A Gestão de Falhas mantém a identidade original `(execution_id, pipeline)` de
`etl_job_execution` e usa `etl_failure_ack` como fonte do tratamento. Prioridade,
responsável da sessão, histórico e link exato são visíveis na tela existente.
Abrir a lista/histórico não assume uma ocorrência. Resolver não altera FAILED.

## Contrato e compatibilidade

- ACK/resolve/bulk existentes usam o ator autenticado; campos `user` e
  `display_name` do cliente não determinam autoria. Outra pessoa responsável
  produz409, assim como resolução diferente sem reabertura ou alvo desconhecido.
- Mutações serializam a chave com UPDLOCK/HOLDLOCK no índice único legado;
  lotes são atômicos, ordenados e limitados a200 ocorrências sem duplicatas.
- `version` expõe o ROWVERSION em hexadecimal; a UI envia `expectedVersion`
  (null quando sem ack). Delta contra versão antiga produz409. Uma repetição
  realmente sem delta permanece idempotente. ACK/resolve de consumidores antigos
  sem expectedVersion continuam compatíveis e serializados. A nova rota de
  prioridade exige expectedVersion e uma ocorrência aberta do próprio operador.
- Histórico registra ação, ator, nota/ticket, prioridade efetiva, versão anterior
  e UTC com offset explícito. Preserva até200 ações recentes na consulta; desfazer
  ack não apaga auditoria. Snapshot legado é identificado, sem inventar geração,
  timestamp de ação antiga ou relacionamento com corrida mais recente.
- Campos ack_at/resolved_at legados permanecem GETDATE no relógio de origem;
  datas novas da auditoria usam DATETIME2/SYSUTCDATETIME e resposta UTC explícita.
- Link `/logs?execution_id=...&pipeline=...&exact=1` permanece na URL para
  recarregar/copiar. Nova identidade na mesma rota sincroniza filtros; consulta
  de pipeline usa igualdade nesse modo, sem LIKE. Limpar/editar manualmente
  abandona o contexto exato de forma explícita.

## Comunicação e limites

Primeira assunção/resolução preserva os helpers Teams e a notificação pessoal
legados, somente quando changed=true e depois do commit. Bulk envia um resumo
somente dos itens alterados. Repetição, leitura, conflito, rollback, reabertura,
remoção, prioridade e backfill não enviam essa comunicação. Transporte é
best-effort sem retry cego; seu erro não muda o tratamento ou o processamento.
Esse caminho legado não certifica recebimento. Fila principal F9/F10 continua
OFF, sem ativação automática de tenant/canal ou alteração da política de jobs.

Rotas de escrita mantêm PERM_EXECUTAR; histórico novo exige sessão. UI segue a
permissão acao_executar, incluindo overrides. Autenticação/API do restante do
produto preservadas. Chave desconhecida é bloqueada sem retarget; geração de
ocorrência legada permanece desconhecida. Tratamento não infere comunicação
lida/entregue nem altera nós customizados, auth, motor ou pipelines de cliente.

## Deploy e smoke

Aplicar186 (prioridade/rowversion/auditoria e ampliação do nome de resolução)
e187 (versão2.31.0), ambas idempotentes. Backup DEV antes, restart apenas API,
dist recompilada e commitada. Sem dependência/env/DAG/.NET novos.

QA usa SQL descartável próprio, HTTP com atores de fixture e transportes mocks;
confirma duas corridas, concorrência, versões obsoletas409, repetição1/0,
rollback bulk, estadoFAILED, RBAC403, UTC e reaplicação. Smoke publicado deve
repetir fixtures com limpeza, conferir saúde/login/versão/migrations/assets e
navegação desktop/mobile sem jobs ou mensagens reais. Caixa/DataStage e piloto
humano permanecem gates externos registrados separadamente.
