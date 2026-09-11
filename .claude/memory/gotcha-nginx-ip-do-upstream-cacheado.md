---
name: gotcha-nginx-ip-do-upstream-cacheado
description: "⚠️ Recriar o container da API deixa a UI do Orquestra com 502: o nginx resolveu o nome do upstream uma vez, no boot, e o container novo tem IP novo. Corrige com `nginx -s reload`"
metadata:
  node_type: memory
  type: project
  originSessionId: 55c7dc0b-089c-4e39-9b3c-c60297f1190c
  modified: 2026-09-11T11:49:25.430Z
---

No DEV do Orquestra, quem serve a interface na porta 8090 é o container **`airflow-ui`** (nginx). O `/etc/nginx/nginx.conf` dele faz:

```
location /orquestra/ { proxy_pass http://orquestra-api:8000/; }
```

Com `proxy_pass` apontando para um **nome literal** e sem `resolver` no bloco, o nginx resolve o DNS **uma única vez, ao iniciar**, e guarda o IP. Recriar o container da API (`docker compose up -d orquestra-api`, rebuild, etc.) lhe dá um **IP novo** na rede `orquestra-dev_default` — e o nginx segue batendo no IP velho.

**Sintoma:** a tela carrega normalmente (o `dist` é servido pelo mesmo nginx, direto do disco) mas **nada busca dado**: pipelines vazios, execuções vazias. No navegador as chamadas voltam **502**. A API está sã: `curl` direto em `127.0.0.1:8000` responde 200, o que faz parecer problema de código ou de front.

**Correção (segundos, sem downtime):**

```
docker exec airflow-ui nginx -s reload
```

Confirmar com o caminho que o navegador usa, não com a porta da API:

```
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" \
  -d '{"usuario":"x","senha":"y"}' http://127.0.0.1:8090/orquestra/auth/login
```

**502** = o nginx não alcança a API (o problema acima). **403** = alcança e recusou a credencial falsa, ou seja, está funcionando.

**Why:** o diagnóstico engana. A API responde, o front carrega, os testes passam, e a tentação é procurar o defeito no código que acabou de mudar. O problema é de rede e não tem nada a ver com a mudança.

**How to apply:** **toda vez** que recriar `orquestra-api` no DEV, recarregue o `airflow-ui` logo depois. Vale para qualquer container que o nginx referencie por nome. Em produção o encadeamento é o mesmo (o proxy do Swarm `orquestradev_proxy` encaminha para a porta 8090 do host), então um deploy que recrie a API pede o mesmo reload. Relacionado: [[vps-ambiente-dev-orquestra]], [[gotcha-compose-sem-env-file-dev]].
