# Validação — F5: guardas, grafo e encerramento

Base main8cf356b; fase sobre F4#459. Sem merge/deploy.

- Pytest completo: **7078 passed,51 skipped, mesmas8 falhas da base** (APIv2.4×4, rodapéKanban×3, smokeauth×1). Nenhuma falha nova.
- 34 testes específicos: guardas geradas nos dez tipos, salto de validação versus branch, prova de tentativa/início, combinações de políticas, falha de persistência, fechamento SSH e limite de identificadores.
- TypeScript/build aprovados, dist inalterado. Lint:71 achados distintos herdados, nenhum novo. Fontes sem NUL.
- QA adversarial e segurança independentes: corrigidos todos os defeitos confirmados. Revisão encontrou fechamento SSH encobrindo diagnóstico, task_id técnico maior que200, autorização de tentativa antiga, otimização de EmptyOperator e ramos indiretos sem guarda.

## Prova integrada local

Airflow2.11.2, SQL Server e SSH/SFTP reais, metadados Airflow/banco SQL/arquivos temporários isolados e removidos ao final. DAGs geradas pela fábrica, serializadas e reimportadas. Aguarde protegido tem `inherits_from_empty_operator=False`; hook não pode ser eliminado pela otimização do scheduler.

| Cenário | Resultado confirmado |
|---|---|
| Todos pulados, liberação desligada | SEM_MOVIMENTO, publish pulado |
| Todos pulados, liberação ligada | SEM_MOVIMENTO, publish aprovado |
| Primeiro destino pulado, segundo com dados | Segundo executa conforme sua política |
| Ambos com dados | Ambos executam na sequência |
| Arquivo binário como texto | Erro técnico persistido, restante não avaliado, FALHA e publish bloqueado |
| Branch escolhe um ramo | Outro ramo continua pulado |
| Decisão controlada pulada | Ramos não executam |
| Decisão pulada, ramos sem controle direto e outro pai bem-sucedido | Nenhum ramo é indevidamente reativado |
| Dois validadores, mesmo destino | Uma política de pular impede execução |
| Clear somente do validador após sucesso | Tentativa2 não autoriza consumidores da tentativa1; publicação recusada |

`DAG.test` normalmente omite início real ao chamar `_run_raw_task`; a bancada usou `TaskInstance.run` e, no replay, `DagRun.schedule_tis`/clear reais. Não foi um deploy nem um scheduler contínuo de produção. Efeitos legados de agenda/telemetria/disparo foram isolados; Shell executou `true` no servidor SSH de amostra, Aguarde e Branch foram reais. Não foram executados jobs DataStage, chamadas HTTP externas, procedures de negócio ou notificações externas.

Artefatos locais: `/root/orquestra-valida-f5-evidencias/` (airflow_smoke.py, airflow_inner.py, airflow-smoke.json, full-pytest-final.log, lint-comparison.json, build.log). Resultado sanitizado versionado em `docs/evidencias/valida-arquivo-f5-airflow.json`.

## Limites

Validação com dataset e dsjob/orchadmin reais somente no ambiente Caixa, conforme confirmação do usuário. F6 ainda implementará cadastro transacional no canvas e acompanhamento; não anunciar o nó disponível nesta fase. O disparo de pipelines dependentes conserva a implementação existente de deduplicação por corrida; esta bancada comprova sua barreira de autorização, não dispara pipelines reais externos.
