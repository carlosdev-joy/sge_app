---
name: orquestra-claude-code-offline
description: "Pacote e scripts para instalar o Claude Code no servidor da Caixa (sem internet, atrás de proxy) — PR #321 aberta, release pendente"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f271463-f62f-424c-b6a1-1e07dbd2b1dc
  modified: 2026-08-21T00:42:35.045Z
---

Levar o Claude Code para o servidor de produção: binário nativo de ~339 MB
(91 MB comprimido), glibc ≥ 2.17, sem Node/npm. **PR #321** (`chore/claude-code-offline`,
commits `33dbdcc` + `aebd73b`) — aberta em 2026-08-20, **aguardando merge do usuário**.

Arquivos: `scripts/claude-offline/{empacotar-claude-offline.sh,instalar.sh,LEIAME.md}`,
`scripts/instalar-claude.sh`, `docs/claude-code-servidor.md`.

**Decisões do usuário:** entrega por **GitHub Release** (repo é público; asset
baixado no servidor pelo mesmo canal do clone do deploy) e servidor **atrás de
proxy corporativo**.

**PENDENTE:**
1. **Publicar a release** — `gh release create claude-code-2.1.228` com o
   `.tar.gz` + `.sha256`; o repo nunca teve release. Não autorizada ainda.
2. **Plataforma do servidor não confirmada** — o pacote pronto é `linux-x64`
   glibc. Falta `uname -m; ldd --version` de lá.
3. **Liberação de rede** — `api.anthropic.com` e `platform.claude.com` são
   obrigatórios (`claude.ai` se o login for por assinatura). Tabela completa na
   §1 do doc.
4. **Autenticação** — decidir entre `claude setup-token` (assinatura, gerado
   noutra máquina com navegador) e `ANTHROPIC_API_KEY` (Console).

**⚠️ GOTCHAS descobertos por teste (todos documentados na §6 do doc):**
- **`claude install` BAIXA da internet**: resolve o canal `latest`. Um pacote
  2.1.228 instalou 2.1.238 vindo da rede — passa verde em máquina com saída e
  falha no servidor. A instalação é cópia determinística do binário do pacote.
- **Sonda de conectividade mente fácil**: `curl -w '%{http_code}'` já imprime
  `000` na falha (o `|| echo 000` fazia "000000"); e aceitar qualquer 1xx–5xx
  deixa passar o **407 do proxy** e a página de bloqueio. A sonda pede
  `GET /v1/models` e exige `401` + `authentication_error`.
- **407 em HTTPS não chega ao `%{http_code}`**: o proxy recusa no `CONNECT` e o
  código fica `000` — só o stderr do curl nomeia a causa.
- **Pin de fingerprint GPG só vale via `VALIDSIG`**: comparar o primeiro
  fingerprint do chaveiro não constrange quem assinou, porque `gpg --verify`
  aceita qualquer chave importada.

**Fora do `deploy.sh` de propósito**: ferramenta de operação, não artefato do
produto, e o deploy roda com `set -e`. Ver [[orquestra-sge-app]] e
[[orquestra-dev-testa-producao-manda]].

## ⚠️ PR #321 FECHADA em 2026-08-29 (limpeza de PRs antigas)

**A branch NÃO foi apagada** — o código vive em
`origin/chore/claude-code-offline`, com 5 arquivos que existem só lá:

```
scripts/claude-offline/empacotar-claude-offline.sh
scripts/claude-offline/instalar.sh
scripts/claude-offline/LEIAME.md
scripts/instalar-claude.sh
docs/claude-code-servidor.md
```

Recuperar com `git fetch origin chore/claude-code-offline`.

A necessidade CONTINUA de pé; o que faltava não era código, eram três
providências externas: publicar o asset de release, liberar os hosts no proxy
e resolver a autenticação sem navegador.
