---
name: orquestra-proxy-worker-vs-api
description: "⚠️ GOTCHA Orquestra: o proxy corporativo está SÓ no container orquestra-api — o airflow-worker não herda nada; DAG que chama a internet morre com 'Connection reset by peer' enquanto a sonda da mesma integração passa. Bônus: httpx 0.28 no worker × 0.27 na api"
metadata: 
  node_type: memory
  type: project
  originSessionId: b6fa286c-27e3-404c-8ac0-af606e0cefb3
  modified: 2026-08-13T19:53:54.892Z
---

**Sintoma:** a sonda/teste de conexão do Admin passa, e a DAG da MESMA
integração morre com `[Errno 104] Connection reset by peer` — em todos os
destinos, em ~1 segundo. Parece ACL ou credencial; não é nenhum dos dois
(ACL daria 403 por tabela, credencial daria 401). Conexão cortada antes do
TLS = firewall de saída.

**Causa: são containers diferentes.** No `docker-compose.yaml`, as variáveis
`HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` estão declaradas **só no serviço
`orquestra-api`**. O `airflow-worker` herda apenas o `x-airflow-common`, que
não tem nenhuma delas. Toda tela do Admin que "testa conexão" roda na API
(com proxy) enquanto a DAG correspondente roda no worker (sem).

**Aconteceu com o sync do ServiceNow em 2026-08-13**, corrigido na PR #311.

**A correção que NÃO foi escolhida — e por quê.** Pôr `HTTPS_PROXY` no worker
tem três problemas:
1. no worker ela valeria para TODA chamada HTTP de TODA DAG, inclusive os nós
   `HttpCall` de pipelines dos usuários, que apontam para hosts internos — a
   proteção seria o `NO_PROXY` estar completo, lista que ninguém revisa;
2. variável de ambiente **só entra em container NOVO**, e recriar o worker
   mata as tasks em execução (`stop_grace_period` default = 10s, sem tempo
   para o warm shutdown do Celery). ⚠️ Job DataStage disparado por SSH **não
   morre junto**: segue vivo no DS enquanto o Airflow o dá por morto, e o
   retry dispara o mesmo job de novo;
3. **`scripts/deploy_prod.sh` NÃO toca no worker** — só `orquestra-api` e
   `ui-nginx`. O passo seria manual, e o deploy sairia VERDE com a integração
   ainda quebrada.

**A correção que valeu:** a rota virou `servicenow_proxy` em `etl_app_config`
(migration 089) + campo na aba ServiceNow do Admin. Trocar = editar a tela, o
próximo ciclo usa, nada é recriado. A DAG lê `LIKE 'servicenow%'`, então a
chave nova entrou sem mudar a consulta. **Use este mesmo padrão** para
qualquer DAG futura que precise sair para a internet.

**⚠️ httpx: 0.28.1 no worker × 0.27.2 na api.** No worker `proxies=` (plural)
**não existe mais** — só `proxy=`. Na api os dois funcionam. O que compila em
`api/` quebra em `dags/`. Confirmado medindo dentro dos containers.

**Passar `proxy=` por parâmetro faz o httpx ignorar o `NO_PROXY`** (lição da
PR #304). É seguro só quando o cliente fala com UM host externo e nada
interno — que é o caso do sync do ServiceNow.

**Ordem de diagnóstico** para "a DAG não alcança a internet":
1. a primeira linha do log diz a rota? (`[SN] Saída: via proxy X` /
   `conexão direta`) — se não diz, a DAG precisa passar a dizer;
2. `docker compose exec airflow-worker env | grep -i proxy` — vazio explica tudo;
3. só então suspeitar de ACL/credencial no destino.

Ver [[orquestra-spec-chamados-servicenow]], [[orquestra-sge-app]],
[[orquestra-placeholder-pyodbc-pymssql]].
