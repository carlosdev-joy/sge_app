# Task 10 — QA Completo + Build + Deploy

**Data:** 2026-08-23
**Status:** DONE_WITH_CONCERNS

---

## Parte A — Testes Python/API

**Resultado: PASS — 92/92 testes passaram**

Suíte completa em `/opt/airflow/dags/tests/` (10 arquivos de teste):
- `test_chamado_derivacoes.py`
- `test_chamados_api.py`
- `test_servicenow_sync.py`
- `test_servicenow_delta.py`
- `test_servicenow_notas.py`
- `test_servicenow_snapshot.py`
- `test_chamados_detalhe.py`
- `test_chamados_anexo_proxy.py`
- `test_admin_servicenow.py`
- `test_indicadores_historico.py`

Comando executado: `docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/ -v --tb=short`

---

## Parte B — Migrations no banco

**Resultado: 9/9 tabelas encontradas. Coluna `tem_anexo` presente.**

Verificado via MsSqlHook com `conn_id=SQL14_DMDB41`:
```
9/9 tabelas encontradas:
  etl_chamado_anexo
  etl_chamado_ciclo
  etl_chamado_nota
  etl_indicador_meta
  etl_indicador_snapshot
  etl_indicador_snapshot_analista
  etl_indicador_snapshot_grupo
  etl_servicenow_gatilho
  etl_servicenow_grupo
tem_anexo em etl_chamado: SIM
```

Nota: conexão direta pymssql do scheduler falhou (Connection refused ao tentar `SQL14` sem porta explícita), mas MsSqlHook funcionou corretamente.

---

## Parte C — DAGs no scheduler

**Resultado: etl_servicenow_delta e etl_servicenow_full registradas.**

```
etl_servicenow_delta | /opt/airflow/dags/etl_servicenow_delta.py | airflow | True
etl_servicenow_full  | /opt/airflow/dags/etl_servicenow_full.py  | airflow | True
etl_servicenow_sync  | /opt/airflow/dags/etl_servicenow_sync.py  | orquestra | False
```

A DAG `etl_servicenow_sync` está pausada (False), como esperado.

---

## Parte D — Build do frontend e deploy

**Resultado: Build PASSOU (com correções). Deploy feito.**

**Problemas encontrados e corrigidos:**

1. **TypeScript error** em `ChamadoKanbanCard.tsx` (linha 73):
   - Prop `title` não existe em `LucideProps` — alterada para `aria-label`.
   - Arquivo: `/opt/git/sge_app/ui-react/src/components/ChamadoKanbanCard.tsx`

2. **Node.js incompatível**: versão instalada é 20.18.0, mas Vite 8.x requer 20.19+.
   - Solução: downgrade de Vite 8.x para Vite 5.4.21 e `@vitejs/plugin-react` de 6.x para 4.x.
   - Build bem-sucedido com Vite 5.

Build output:
```
dist/index.html                   0.47 kB │ gzip:  0.30 kB
dist/assets/index-peU81eJi.css   19.97 kB │ gzip:  4.63 kB
dist/assets/index-EwPETJTf.js   705.67 kB │ gzip: 211.01 kB
built in 5.06s
```

Deploy executado: `cp -r /opt/git/sge_app/ui-react/dist/* /opt/airflow/ui-react/dist/`

---

## Parte E — Endpoints API

**Resultado: Todos os endpoints respondem corretamente.**

| Endpoint | HTTP Code | Esperado |
|---|---|---|
| `GET /health` | 200 | OK |
| `GET /chamados/indicadores/historico` | 401 | 401 (auth requerida) |
| `GET /admin/servicenow/config` | 401 | 401 (auth requerida) |

**Concern identificado e corrigido:** O endpoint `GET /chamados/indicadores/historico` estava retornando 404 porque estava declarado DEPOIS de `@router.get("/chamados/{sys_id}/tasks")` — FastAPI casava `indicadores` com `{sys_id}` antes de chegar na rota estática. A rota foi movida para antes de todos os `/{sys_id}/...` em `/opt/airflow/api/routers/chamados.py`. Após o fix e reinício do container, o endpoint passou a responder 401 conforme esperado.

---

## Parte F — etl_servicenow_sync

Não pausada manualmente — já estava pausada (ativo=False) conforme visto no `dags list`.

---

## Concerns

1. **Vite / Node.js**: O projeto foi buildado com Vite 5.4.21 (downgraded de 8.x). O `package.json` agora referencia `"vite": "^5.4.21"` e `"@vitejs/plugin-react": "^4.x"`. Para atualizar Vite futuramente, será necessário atualizar Node.js para 20.19+ ou 22.12+.

2. **Chunk size warning**: Bundle JS de 705 KB (gzip: 211 KB) — acima do limite recomendado de 500 KB. Considerar code-splitting com `import()` dinâmico em builds futuros.

3. **Bug de rota corrigido em produção**: O route ordering de `indicadores/historico` vs `/{sys_id}/...` foi corrigido diretamente em `/opt/airflow/api/routers/chamados.py`. Este bug existia desde a implementação (Task 5).

4. **Testes de API rodando do container API**: Os testes Python estão em `/opt/airflow/dags/tests/` e são executados via `docker exec orquestra-api`. Não há diretório `tests/` na raiz do container `/app/` — o correto é especificar o path completo.
