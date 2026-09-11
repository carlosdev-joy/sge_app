---
name: gotcha-compose-sem-env-file-dev
description: "⚠️ `docker compose up -d` sem `--env-file .env.dev` no Orquestra recria o SQL Server com a senha DEFAULT e ele fica unhealthy — derruba a stack inteira por dependência"
metadata:
  node_type: memory
  type: project
  originSessionId: 55c7dc0b-089c-4e39-9b3c-c60297f1190c
  modified: 2026-09-11T06:46:51.914Z
---

No DEV do Orquestra (`/opt/orquestra-dev`), **todo** comando `docker compose` precisa de `--env-file .env.dev` junto dos dois arquivos:

```
docker compose --env-file .env.dev -f docker-compose.yaml -f docker-compose.dev.yaml up -d <serviço>
```

Sem o `--env-file`, o compose resolve `${DEV_MSSQL_SA_PASSWORD:-Orquestra@Dev2024}` para o **default** do próprio arquivo. Como o env do container muda, o compose **recria** `orquestra-sqlserver-dev` — e aí o healthcheck tenta logar com a senha default enquanto o volume `sqlserver-dev-data` ainda guarda a senha verdadeira. Resultado: `Login failed for user 'sa'` em loop, container `unhealthy`, e qualquer `up` seguinte falha com `dependency failed to start`.

**Why:** o sintoma parece corrupção do banco, mas o dado está intacto — é só o env do container. A tentação é recriar o volume, e isso apagaria o DEV inteiro (migrations 106–111, pipelines de teste).

**How to apply:** confirmar o diagnóstico logando à mão com a senha do arquivo (`docker exec orquestra-sqlserver-dev /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "<senha do .env.dev>" -Q "SELECT 1" -C`); se logar, é só refazer o `up -d` **com** `--env-file .env.dev` e o container volta `healthy` sem perder nada. Nunca apagar o volume por causa disso. Subir a API também reinicia o `airflow-webserver`, e o login da API valida credenciais contra ele — os primeiros logins dão 500 até o webserver responder em `/health`. Relacionado: [[vps-ambiente-dev-orquestra]].
