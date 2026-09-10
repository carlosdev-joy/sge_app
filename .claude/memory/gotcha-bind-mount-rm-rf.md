---
name: gotcha-bind-mount-rm-rf
description: "⚠️ apagar um diretório que é bind mount (rm -rf) deixa o container servindo vazio — HTTP 403 com tudo \"de pé\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80eeec2c-39eb-4217-a273-e34383d916bf
  modified: 2026-08-28T12:36:38.575Z
---

`rm -rf <dir> && rebuild` num diretório que está **montado num container** quebra o
mount: o bind guarda o **inode**, e recriar o diretório gera outro. O container continua
`Up`, o `ls` no host mostra os arquivos, e **dentro do container o diretório está vazio**.

Aconteceu em 2026-08-28 com `/opt/orquestra-dev/ui-react/dist` → `airflow-ui`
(`/usr/share/nginx/html`): resolvi conflito de merge com `rm -rf ui-react/dist && npm run
build`, e `orquestra.lcseguranca.com` passou a responder **403** — nginx sem `index.html`
para servir. Todos os containers `Up`/`healthy`, proxy 1/1, API 200. O sintoma não aponta
para a causa.

**Como diagnosticar:** `docker exec <container> ls -la <destino>` — `total 0` com arquivos
no host é a assinatura.

**Correção:** recriar o container —
`docker compose ... up -d --force-recreate ui-nginx`. Reiniciar (`restart`) NÃO resolve:
o mount é refeito só na criação.

**Como evitar:** esvaziar o conteúdo em vez de apagar o diretório —
`rm -rf dist/* dist/.[!.]*` preserva o inode. Vale para qualquer pasta montada
(`dags/`, `config/`, `dist/`).

**Why:** o modo de falha é silencioso e caro — leva a investigar nginx, permissão,
gitignore e build, quando o problema é o mount. Ver [[orquestra-coletar-producao]] e
[[vps-pkill-atinge-containers]] para outros casos em que o sintoma mente sobre a causa
neste ambiente.
