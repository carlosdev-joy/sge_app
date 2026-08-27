# Task 4 Report — DAG `etl_servicenow_full`

**Status:** DONE

**Data:** 2026-08-23

---

## Arquivo criado

`/opt/airflow/dags/etl_servicenow_full.py`

---

## Resultado dos checks

### Parse Python
```
docker exec airflow-airflow-scheduler-1 python -m py_compile /opt/airflow/dags/etl_servicenow_full.py && echo "OK"
→ OK
```

### Registro no scheduler
```
docker exec airflow-airflow-scheduler-1 airflow dags list 2>&1 | grep etl_servicenow_full
→ etl_servicenow_full | /opt/airflow/dags/etl_servicenow_full.py | airflow | None
```

DAG visível no scheduler sem erros de parse ou import.

---

## Decisões de implementação

1. **`_decifrar()` local**: Replicado exatamente do padrão de `etl_servicenow_delta.py` e `etl_servicenow_sync.py` — usa `cryptography.fernet.Fernet + ORQUESTRA_CONN_KEY`. Não importa `services.conn_crypto` (que não está no sys.path do scheduler).

2. **`proxy=` (singular)**: Alinhado com `etl_servicenow_sync.py` que usa `httpx 0.28+` onde `proxies=` foi removido. O plano original usava `proxies=` (do delta), mas o sync já havia documentado essa diferença de versão entre as árvores.

3. **`proxy_da_config` importado**: Adicionado ao import de `servicenow_sync`, seguindo o padrão do sync e do delta.

4. **Migração única `etl_chamado_sync → etl_chamado_ciclo`**: Executada quando `COUNT(*) WHERE modo='full' == 0`, conforme especificado. Migra `qtd_incident + qtd_ritm + qtd_task + qtd_change` como `qtd_chamados`.

5. **Desativação**: `UPDATE etl_chamado SET ativo=0 WHERE ativo=1 AND sync_em < inicio` — desativa todos os chamados que não foram tocados neste ciclo full (não segmentado por tipo como no sync antigo, pois o full cobre todas as tabelas).

6. **`notas_e_anexos_full`**: Varre `SELECT sys_id FROM etl_chamado WHERE ativo=1` (TODOS os ativos), não apenas os `sys_ids` tocados no ciclo — conforme constraint da task.

7. **Modo**: `'full'` em `etl_chamado_ciclo`.

8. **Schedule**: `0 2,14 * * *` (02h e 14h).

9. **`max_active_runs=1`, `dagrun_timeout=timedelta(minutes=25)`**: Conforme especificado.

10. **`etl_servicenow_sync` NÃO pausada**: Conforme instrução da task (pausar somente na Task 10 após smoke test).

---

## Concerns

Nenhum bloqueador. Uma observação:

- O plano original (Task 4, Step 1) importava `from services.conn_crypto import decrypt_password` dentro das tasks — padrão incorreto para o contexto do scheduler. A implementação corrigiu para `_decifrar()` local, alinhado com os demais arquivos já em produção.
