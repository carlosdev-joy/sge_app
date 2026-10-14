# EOC-F9B — Dispatcher persistente dry-run (2.28.0)

F9A já publicada em2.27.0. F9B acrescenta claim/lease/fence e tentativa atômica, recuperaçãoUnknown sem reenvio automático e retries finitos no harness. Sem transporte real, ingestão de cliente, reexecução de job ou mudança de auth/motor/UI.

Loop no lifespan desligado por padrão. EOC_ALERT_DISPATCHER_DRY_RUN=1 habilita somente fixtures próprias e terminaDryRun. Não configurar a flag para ativar canais externos. Accepted de mock200 não atesta recebimento. Falhas429/500 simuladas têm máximo4tentativas; timeout ou leaseexpirada→Unknown. Querytimeout10s/locktimeout5s permitem shutdown sob concorrência.

Migration181_versao_dispatcher_alertas registra2.28.0; não altera CHECKdry_run=1. BackupSQL COPYONLY/CHECKSUM/VERIFYONLY antes da migration, idempotência duas vezes e somente restartAPI. UI/dist/.NET/DAGs inalterados. Sem dependência/wheel nova. Rollback do código preserva fila/schema, mantenha flagOFF. Nenhuma limpeza automática de pendências.

QA independente ampla encontrou locksemdeadline; corrigido e confirmação dirigida aprovada com SQLreal (shutdown4.863s/query10.01s). SQLisolado cobre8workers/atomicrollback/reconnect/fence/recovery/backoff/exhaustion/mocks. Suítefinal:8016PASS/exatas8FAIL/51SKIP,8075tests207.65s; IDs de falha/skip iguais à base90847f4a/DEV2.27.0. Lint176zeroassinatura nova. UI/dist intactos, hashes reaproveitados; sem rebuild necessário. PublicaçãoDEV: conferir handoff/evidências finais, candidato não prova deploy.

GateauthorityF9 (Warningagregado/geraçãoClear) permanece Backlog180. GatesF6humano/CaixaDataStage/SQLantespoll5s preservados. Entrega técnica não certifica esses aceites externos.
