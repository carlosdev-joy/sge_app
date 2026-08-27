# Task 3 Report — DAG `etl_servicenow_delta`

**Status:** DONE

## Arquivo criado

`/opt/airflow/dags/etl_servicenow_delta.py`

## Verificações de parse/import

### Syntax check
```
python -m py_compile /opt/airflow/dags/etl_servicenow_delta.py → SYNTAX OK
```

### Import check (com stubs dos módulos side-effect)
```
python -c "import dags.etl_servicenow_delta; print('IMPORT OK')" → IMPORT OK
```

### Airflow DAG list
```
airflow dags list | grep etl_servicenow_delta
etl_servicenow_delta | /opt/airflow/dags/etl_servicenow_delta.py | airflow | None
```

### Propriedades via DagBag
```
dag_id:           etl_servicenow_delta
schedule:         */5 * * * *
max_active_runs:  1
dagrun_timeout:   0:08:00
tasks:            ['espelho_delta', 'notas_e_anexos', 'snapshot', 'triagem']
```

### Grafo de dependências
```
espelho_delta → notas_e_anexos → snapshot → triagem
```

## Adaptações em relação ao plano

1. **`decrypt_password` de `services.conn_crypto`** — o path `api/services/conn_crypto.py`
   não está no `sys.path` do scheduler Airflow. Em vez de importar de `api/`, foi usada
   a função `_decifrar()` local com `cryptography.fernet.Fernet` + `ORQUESTRA_CONN_KEY`,
   idêntica à lógica existente em `etl_servicenow_sync.py`. Sem mudança de comportamento.

2. Todos os imports de `utils.servicenow_sync` usam os nomes reais confirmados no arquivo:
   `upsert_sql`, `upsert_params`, `normalizar`, `CAMPOS`, `PAGINA`, `MAX_PAGINAS`,
   `TABELAS`, `MSSQL_CONN_ID`, `proxy_da_config`, `grupos_ativos`, `ultimo_delta_em`,
   `query_delta`, `buscar_notas`, `buscar_anexos`, `upsert_nota_sql`, `upsert_nota_params`,
   `upsert_anexo_sql`, `upsert_anexo_params`, `capturar_snapshot`.

3. Task `triagem` implementada como stub (log + TODO), conforme especificado no plano.

## Concerns

Nenhum. A DAG parseia, importa e aparece no scheduler sem erros.
