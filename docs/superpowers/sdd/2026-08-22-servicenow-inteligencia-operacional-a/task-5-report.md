# Task 5 Report — Endpoints API

**Status:** DONE

**Data:** 2026-08-23

---

## O que foi feito

### 1. `FRESCOR_ALERTA_MINUTOS` alterado para `8`
- Arquivo: `/opt/airflow/api/routers/chamados.py` linha ~47
- Era `60`, agora `8` (delta a cada 5 min + margem de 3 min).

### 2. Endpoints implementados em `api/routers/chamados.py`

Total de **12 novos endpoints**:

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/chamados/indicadores/historico` | Histórico de snapshots (períodos: hoje/30d/historico) |
| GET | `/chamados/{sys_id}/detalhe` | Detalhe completo: chamado + notas + anexos |
| GET | `/chamados/{sys_id}/anexos/{sys_id_anexo}` | Proxy streaming de anexo |
| GET | `/admin/servicenow/config` | Lê configuração de integração |
| PUT | `/admin/servicenow/config` | Salva configuração de integração |
| POST | `/admin/servicenow/testar` | Testa conectividade com ServiceNow |
| GET | `/admin/servicenow/grupos` | Lista grupos monitorados |
| POST | `/admin/servicenow/grupos` | Cria novo grupo |
| PUT | `/admin/servicenow/grupos/{id}` | Edita grupo (ativo/nome) |
| GET | `/admin/servicenow/ciclos` | Lista últimos 20 ciclos de sync |
| POST | `/admin/servicenow/disparar-delta` | Dispara DAG delta via Airflow REST API |
| GET | `/admin/servicenow/perfis-acesso` | Lê perfis com acesso admin |
| PUT | `/admin/servicenow/perfis-acesso` | Salva perfis com acesso admin |

### 3. Ordenação de rotas (constraint crítico)
`/chamados/indicadores/historico` foi declarado **antes** de `/{sys_id}/detalhe` e `/{sys_id}/anexos/{sys_id_anexo}`, evitando que `indicadores` case com `{sys_id}` no matching do FastAPI.

### 4. Arquivos de teste criados

| Arquivo | Testes | Status |
|---------|--------|--------|
| `dags/tests/test_chamados_detalhe.py` | 4 | PASS |
| `dags/tests/test_chamados_anexo_proxy.py` | 4 | PASS |
| `dags/tests/test_admin_servicenow.py` | 15 | PASS |
| `dags/tests/test_indicadores_historico.py` | 10 | PASS |

### 5. Suite completa

```
92 passed, 1 warning in 0.63s
```

Nenhuma regressão nos testes existentes.

---

## Concerns

1. **`requests` não disponível no container API** — O plano especificava `import requests` para o endpoint `disparar-delta`. O módulo `requests` não está instalado no container `orquestra-api`. A implementação foi adaptada para usar `httpx` (já disponível via `_httpx`), mantendo comportamento idêntico. Se futuramente precisar do `requests`, instalar via `requirements.txt`.

2. **Tabelas ainda não existem no banco** — Os endpoints dependem das tabelas das migrations 094-098 (`etl_chamado_nota`, `etl_chamado_anexo`, `etl_chamado_ciclo`, `etl_indicador_snapshot`, `etl_servicenow_grupo`). Os endpoints degradam graciosamente com `500` se as migrations não foram aplicadas — o mesmo comportamento do resto da API. Quando as migrations forem aplicadas em produção, os endpoints passam a funcionar imediatamente.

3. **`decrypt_password` importado no nível do módulo** — A importação `from services.conn_crypto import decrypt_password` ocorre no nível do módulo (fora das funções), o que é correto e necessário para o patching nos testes. Não cria cache da credencial.

---

## Arquivos modificados/criados

- `/opt/airflow/api/routers/chamados.py` — FRESCOR=8, 12 novos endpoints
- `/opt/airflow/dags/tests/test_chamados_detalhe.py` — criado
- `/opt/airflow/dags/tests/test_chamados_anexo_proxy.py` — criado
- `/opt/airflow/dags/tests/test_admin_servicenow.py` — criado
- `/opt/airflow/dags/tests/test_indicadores_historico.py` — criado
