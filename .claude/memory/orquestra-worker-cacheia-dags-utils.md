---
name: orquestra-worker-cacheia-dags-utils
description: "⚠️ GOTCHA Orquestra: mudança só em dags/utils/ NÃO tem efeito sem restart do airflow-worker — o módulo fica em cache no processo Celery e a task segue VERDE rodando o código antigo; o arquivo da DAG (raiz de dags/) recarrega sozinho"
metadata: 
  node_type: memory
  type: project
  originSessionId: b6fa286c-27e3-404c-8ac0-af606e0cefb3
  modified: 2026-08-21T01:44:25.136Z
---

**Sintoma:** deploy verde, arquivo sincronizado no servidor, DAG executando com
status `OK`, task verde, log impecável — **e o código novo não roda**. Nenhum
erro em lugar nenhum.

**Causa:** o DagBag reprocessa o **arquivo da DAG** a cada execução (chega a
apagá-lo de `sys.modules` antes). Mas o `from utils.x import y` lá dentro é um
import comum: se o módulo já está em `sys.modules` do processo do worker
Celery, o import devolve a versão **em memória**, e os forks herdam esse cache.
O arquivo no disco muda e ninguém consulta de novo.

| o que mudou | recarrega sozinho? |
|---|---|
| `.py` na **raiz** de `dags/` (a DAG) | ✅ sim, o DagBag reprocessa |
| `.py` em **subpasta** (`dags/utils/`, `dags/Orquestrador/`) | ❌ **não** — precisa de restart do worker |

**Mordeu em 2026-08-13 (PR #312**, que mexia SÓ em
`dags/utils/servicenow_sync.py`): deploy às 18:46, ciclos das 19:00, 19:15 e
19:30 rodaram com o código antigo. ~1h30 de diagnóstico. Por contraste, a
PR #311 não sofreu porque mudou TAMBÉM o arquivo da DAG (import novo).

**Correção:** `docker compose restart airflow-worker`.
⚠️ **restart ≠ recreate**: o código vem de bind mount, então NÃO precisa de
imagem nova nem de recriar container. Mas derruba tasks em execução — e job
DataStage por SSH **não morre junto** (segue vivo no DS enquanto o Airflow o dá
por morto; o retry dispara o mesmo job de novo). Confira antes:
`docker compose exec airflow-worker celery -A
airflow.providers.celery.executors.celery_executor.app inspect active`

✅ **O `scripts/deploy.sh` passou a avisar (PR #313, `cee04a5`)**: detecta `.py`
em subpasta de `dags/`, explica que nada vai falhar, mostra as tasks ativas
resumidas (`▶ dag_id · task_id` — o dump cru do Celery é ilegível, toda task
se chama `execute_command`) e oferece o restart sob confirmação.

✅ **Guarda em runtime na PR #323** (`dags/utils/frescor_modulo.py`): cada
módulo auxiliar chama `carimbar(__file__)` no import, e a DAG — que sempre roda
fresca — compara o carimbo com o `mtime` do arquivo. Arquivo mais novo que o
import ⇒ o aviso entra em `erros`, o ciclo fecha com status **ERRO** e a
mensagem chega **à tela**, em vez de morrer num log. Módulo sem carimbo mas
presente em `sys.modules` também acusa — é o retrato do worker servindo versão
anterior à guarda. Funciona porque o módulo da guarda é NOVO: ele nunca está em
cache. **Por enquanto só `etl_servicenow_sync` usa; estender às demais DAGs é
backlog.**

⚠️ Pergunta recorrente do usuário (2026-08-21): "nunca fiz restart e sempre
funcionou". Coerente com a tabela acima — quase toda mudança dele cai na raiz
de `dags/`; e o worker é reiniciado por outros motivos (rebuild, `up`), o que
limpa o cache sem que ninguém associe.

Ver [[orquestra-modos-de-falso-verde]], [[orquestra-sge-app]],
[[orquestra-spec-chamados-servicenow]].
