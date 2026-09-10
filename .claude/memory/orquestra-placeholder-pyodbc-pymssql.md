---
name: orquestra-placeholder-pyodbc-pymssql
description: GOTCHA do Orquestra — SQL em dags/ usa %s (pymssql do MsSqlHook) e em api/ usa ? (pyodbc); trocar quebra em produção com WARNING silencioso
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2f861786-77b7-4a2e-b8b5-9f078cb50617
  modified: 2026-07-29T23:49:24.235Z
---

**No Orquestra (`/opt/orquestra-dev`) há DOIS dialetos de placeholder SQL, e
isso é correto:**

- `dags/**` → **`%s`** — o `MsSqlHook` do Airflow usa **pymssql**.
- `api/**` → **`?`** — a API FastAPI usa **pyodbc**.

**Why:** usar `?` numa DAG produz `Incorrect syntax near '?'` (DB-Lib error
20018) e **zero linha gravada**. Aconteceu de verdade no primeiro deploy da
supervisão DataStage (2026-07-29, corrigido na PR #214): a DAG conectou por SSH,
leu e parseou o log corretamente, e falhou em todas as escritas.

O que tornou o bug caro: como todo acesso a banco da coleta é envolto em
`try/except` (para um job problemático não derrubar o ciclo), o erro estrutural
virou **WARNING silencioso** — task **verde** no Airflow, log cheio de avisos,
banco vazio. Resiliência no lugar certo esconde erro no lugar errado.

**How to apply:**
1. Ao escrever SQL parametrizado, olhe primeiro em qual árvore o arquivo está.
2. Em teste de gravação, o cursor dublê tem de **rejeitar o dialeto errado** —
   um `CursorFalso` que aceita qualquer string não testa gravação, testa que o
   código chamou `execute()`. Ver `tests/test_ds_supervisao_dag.py`.
3. Complemente com varredura do fonte: há queries que nenhum teste exercita, e
   são exatamente as que só falham em produção.
4. Conversão em massa por regex de palavra-chave SQL **deixa passar linhas de
   continuação** do literal (ex.: `"  campo = ?, outro = ?, "`). Confira o
   resultado com o guard ligado.

Relacionado: [[orquestra-supervisao-ds-spec]] (§7.3 da spec registra a lição).
