---
name: vps-ambiente-dev-orquestra
description: "Ambiente DEV do Orquestra na VPS: liga/desliga por /root/orquestra-dev.sh, credenciais em .env.dev, UI na :8090 servindo ui-react/dist por volume. NO AR desde ~2026-08-28"
metadata: 
  node_type: memory
  type: project
  originSessionId: a34cdce7-292c-458c-a7e9-8860d9d70f07
  modified: 2026-09-08T02:16:44.418Z
---

**Estado em 2026-08-31: NO AR** (containers Up há ~3 dias, ou seja, religado por volta de
2026-08-28). Ficou parado entre 2026-08-14 e essa data. Não presuma o estado — `docker ps` responde.

## Como acessar (confirmado 2026-08-31)

| o quê | onde |
|---|---|
| UI do Orquestra | http://<IP-da-VPS-DEV>:8090 (e `orquestra.lcseguranca.com` pelo proxy swarm) |
| Airflow | http://<IP-da-VPS-DEV>:8082 |
| API | :8000 |

**Credenciais em `/opt/orquestra-dev/.env.dev`** (gitignored): `admin` / `afdev-a15545c168fffcd5` —
as MESMAS na tela do Orquestra e no Airflow, porque o login valida contra a REST do Airflow.
SA do SQL Server dev na mesma linha do arquivo.

⚠️ **Depois de recriar o `orquestra-api` (`up -d --no-deps orquestra-api`), `docker restart
airflow-ui`**: o nginx resolve o nome `orquestra-api` só na inicialização; com o IP novo do
container, tudo em `/orquestra/…` vira **502** (login inclusive) e a tela parece "sem menus"
(2026-09-08). Chamadas diretas na :8000 continuam funcionando — por isso o smoke não vê.

⚠️ **O container `airflow-ui` monta `ui-react/dist` como VOLUME** (`docker-compose.yaml:144`):
qualquer `npm run build` no repo aparece no DEV na hora, sem deploy e sem restart — só um
Ctrl+Shift+R, porque o `index.html` passa a apontar para assets com hash novo. Ótimo para testar
branch antes da PR; e um lembrete de que o DEV mostra a ÁRVORE DE TRABALHO, não a `main`.

Ligar/desligar leva segundos:

```bash
/root/orquestra-dev.sh subir     # religa tudo + o proxy público
/root/orquestra-dev.sh status    # estado dos containers + métricas da VPS
/root/orquestra-dev.sh parar     # desliga de novo
```

O script usa **stop/start, nunca down/up** — containers e volumes preservados, o Postgres do Airflow
e o SQL Server dev mantêm os dados. Antes de parar ele **verifica se há task em execução ou na fila**
e aborta se houver (`--forcar` ignora).

## Ganho medido (antes → 5 min depois)

| métrica | antes | depois |
|---|---|---|
| load (1/5/15 min) | 2,79 / 3,45 / 3,89 | **0,62 / 2,04 / 3,19** |
| memória usada | 10.507 MB | **6.059 MB** |
| memória disponível | 4.723 MB | **9.188 MB** |
| **swap** | **3.291 MB** de 4.095 | **394 MB** |
| pressão de CPU (PSI some avg10) | 6,07 | **1,98** |

A VPS tem 4 vCPU e 15 GiB: com load ~3,9 estava em ~100% de ocupação sustentada e paginando 3,2 GB.
Depois, sobra folga real. **Liberou ~4,4 GB de RAM e ~2,9 GB de swap.**

## O que compõe o ambiente (9 containers, projeto compose `orquestra-dev` em /opt/orquestra-dev)

`airflow-worker` (era o maior consumidor, **107% de CPU** sozinho), `airflow-scheduler`,
`airflow-triggerer`, `airflow-webserver`, `airflow-ui`, `orquestra-api`, `orquestra-dev-postgres`,
`orquestra-dev-redis` e `orquestra-sqlserver-dev` (~2 GiB de RAM). Mais o serviço swarm
**`orquestradev_proxy`** (stack `orquestradev`), que publica **orquestra.lcseguranca.com** e é
escalado para 0/1 junto.

## O que fica fora enquanto está parado

`orquestra.lcseguranca.com`, o Airflow dev e os bancos dev. **Nada de produção é afetado**:
conferido que os 30 serviços do swarm seguem 1/1 e que `app.lcseguranca.com/login` e
`lcseguranca.com` respondem 200. A produção do Orquestra roda na infra da Caixa, não aqui.

**Sem risco de avalanche ao religar:** as 4 DAGs ativas do dev são todas
`Never, external triggers only`; as outras 28 estão pausadas. Não há catchup pendente.

Ver [[nexxafarma-capacidade-vps-e-banco]] (o diagnóstico que motivou) e [[infra-lcseguranca]].
