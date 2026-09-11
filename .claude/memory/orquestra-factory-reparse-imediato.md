---
name: orquestra-factory-reparse-imediato
description: "Publicar DAG no Orquestra pedia reparse prioritário ao scheduler (dag_priority_parsing_request) — ajuste feito pelo usuário DIRETO em produção e portado para o repo"
metadata:
  node_type: memory
  type: project
  originSessionId: 55c7dc0b-089c-4e39-9b3c-c60297f1190c
  modified: 2026-09-11T18:32:25.470Z
---

**O problema:** o Airflow varre a pasta de DAGs a cada `dag_dir_list_interval` (**5 min** por padrão). Depois de publicar, a DAG levava minutos para aparecer — e o fluxo "Gerar DAG" da UI, que ESPERA a ativação, chegava a marcar **TIMEOUT numa publicação que deu certo** (o reconciliador desiste em 900 s, `api/services/dag_reconcile.py`).

**A solução (do usuário, feita direto no servidor de produção em 2026-09-11):** gravar uma linha em `dag_priority_parsing_request` — a fila de prioridade do próprio scheduler (Airflow 2.6+) — logo depois de escrever o arquivo da DAG. O `_refresh_requested_filelocs` roda a cada iteração do DagFileProcessorManager e o arquivo fura a fila.

⚠️ **O ajuste nasceu FORA do git:** ele editou `/opt/airflow/dags/etl_dag_factory.py` em produção e commitou em `/opt/git/sge_app` na branch `backup/producao-20260827` (commit `924a558`), **sem push** — o GitHub não tinha. Sem o porte, o próximo deploy que atualizasse `dags/` teria sobrescrito. Portado nesta PR (branch `feat/factory-reparse-imediato`). Lição: quando o usuário diz "ajustei direto em produção", pedir o **diff do commit**, não o arquivo — produção costuma estar ATRÁS da main no resto do arquivo.

**O que o porte mudou em relação ao código dele (tudo com motivo):**
- **uma conexão para o lote** em vez de uma por arquivo (a regeração em massa passa por centenas de pipelines) — mas o **alvo do clique fura a fila na hora**, porque a `sp_etl_pipelines_pendentes_criar` é GLOBAL e o pipeline do usuário pode estar atrás de dezenas de pendentes de terceiros;
- **`unquote`** em user/senha/dbname: a senha vem percent-encoded na URL (`@` → `%40`) e a conexão falharia justamente nas senhas com caractere especial;
- **`connect_timeout=10` E `options="-c statement_timeout=15000"`** — os dois cobrem coisas diferentes: o primeiro limita o aperto de mão, o segundo o comando já conectado. Sem o segundo, um lock na tabela penduraria o INSERT sem prazo, e como a chamada acontece ANTES do fechamento do log da geração, o resultado seria o [[orquestra-factory-log-orfao]] em RUNNING;
- **id = md5(fileloc)**, como o Airflow faz (`generate_md5_hash` em `models/dagbag.py`): a tabela **não tem unique em `fileloc`** (índice grande demais para o MySQL) e o md5 na PK é o jeito de o modelo impor unicidade — com id aleatório o `ON CONFLICT` nunca dispararia;
- **um `try` por arquivo**: falha no terceiro de oitenta não cala os setenta e sete seguintes.

**Best-effort de propósito:** o arquivo já está gravado quando a função roda; o scheduler o leria na varredura seguinte de qualquer forma. Falhar aqui não pode derrubar a geração — o `import psycopg2` está dentro do `try`, e metastore que não é Postgres sai calado.

**Provado no DEV:** geração às 18:10:19 → `DEV_F10_A` reparseada às **18:10:25** (6 s) e `PIPE_VIDA` às 18:10:29; com alvo, o pedido sai no mesmo segundo da gravação. A fila volta a 0 (o scheduler consome e apaga).

**⚠️ Smoke pós-deploy:** publicar um pipeline e procurar no log da task `[FACTORY] reparse prioritario solicitado para N arquivo(s)` **ou** `[FACTORY] aviso: reparse nao solicitado (…)`. A ausência das DUAS linhas significa que `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` não chegou ao worker (ou produção usa `..._CMD`/`..._SECRET`), e o recurso está inerte — sem quebrar nada.
