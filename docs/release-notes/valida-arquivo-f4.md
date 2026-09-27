# F4 — Configuração original e histórico de validação

A configuração de cada Valida Arquivo e a política de conclusão sem movimento passam a integrar o snapshot cifrado da corrida. Edições só afetam novas execuções. Tentativas guardam estados, contagens e decisões, com idempotência e transação; falha de gravação impede qualquer liberação.

A API oferece histórico por run e política de liberação/notificação com revisão concorrente. O histórico técnico não pode ser desligado. Esta fase não habilita o nó no canvas nem executa validações: F5/F6 completam a integração.

## Aplicação

Após merges autorizados, aplicar migrations pendentes até 132 pela etapa 6c do deploy. Atualizar API e dags/utils, reiniciar worker para limpar cache. Não há dependências Python novas. Preservar ORQUESTRA_CONN_KEY: snapshots dependem dessa chave. Não apagar snapshot/histórico durante rollback; reverter código antes de habilitar novos nós, preservando tabelas aditivas. A ativação final exige publicação inicial das DAGs afetadas conforme F5.

## Verificação

Ver `docs/validacao-valida-arquivo-f4.md`. Conferir leitura autenticada, permissão de edição, conflito 409 por revisão desatualizada e 503 nomeando migration quando instalação incompleta. Testar após F5 retomada original, tentativa em falha consultável e gravação recusada bloqueando destinos. Dataset real continua dependente do smoke assistido na Caixa.
