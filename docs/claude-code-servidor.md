# Claude Code no servidor — instalação offline e rede

Como levar o Claude Code para um servidor que não baixa software da internet,
usando o mesmo canal por onde o `deploy.sh` já traz o Orquestra: a release do
GitHub.

## O que instalar não resolve

O Claude Code é um binário único (~339 MB), sem Node.js e sem npm — mas **não é
um programa offline**. Ele chama `api.anthropic.com` a cada mensagem e
`platform.claude.com` para autenticar. Instalado num servidor sem rota de saída,
ele abre e não responde. Não existe modo air-gapped.

Por isso a liberação de rede vem **antes** da instalação.

## 1. Pedido ao time de rede

Liberar no proxy corporativo, para o servidor:

| Host | Para quê | Obrigatório |
|---|---|---|
| `api.anthropic.com` | toda requisição ao modelo | **sim** |
| `platform.claude.com` | login e renovação do token | **sim** |
| `claude.ai` | login por conta claude.ai | sim, se o login for por conta claude.ai |
| `github.com`, `objects.githubusercontent.com` | baixar o pacote da release | sim (já liberado: o deploy clona o repo) |
| `downloads.claude.ai` | atualização automática | não — fica desligada |
| `registry.npmjs.org` | plugins e servidores MCP via `npx` | não |
| `code.claude.com` | consulta à documentação pelo agente embutido | não |
| `http-intake.logs.us5.datadoghq.com` | telemetria operacional | não — pode bloquear |

Para cortar a telemetria de vez, junte `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
ao bloco `env` do `settings.json`.

## 2. Instalar

No servidor, como **o usuário que vai usar** (nunca com `sudo`):

```bash
export HTTPS_PROXY=http://proxy.empresa:8080
export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-corporativa.pem   # se o proxy inspeciona TLS
bash scripts/instalar-claude.sh 2.1.228 linux-x64
```

O script baixa o pacote da release, confere o SHA256, extrai e chama o
instalador offline, que:

- recusa `sudo` — com ele tudo cairia no HOME do root;
- verifica que a plataforma do pacote é a da máquina (glibc × musl, x64 × arm64);
- exige **glibc ≥ 2.17** (RHEL 7+, Ubuntu 20.04+, Debian 10+);
- revalida o SHA256 do binário, pegando corrupção de transporte;
- instala em `~/.local/share/claude/versions/<versão>`, com atalho em
  `~/.local/bin/claude`;
- grava `~/.claude/settings.json` com o auto-update desligado e o proxy/CA que
  encontrar no ambiente — **um `settings.json` que já exista nunca é
  sobrescrito**, o script mostra o bloco a acrescentar;
- testa `api.anthropic.com` e diz, na cara, se o caminho de rede não existe.

A instalação é **por usuário**: cada operador que for usar roda o script no
próprio login.

## 3. Autenticar sem navegador

O servidor não abre navegador. Duas opções:

1. **Token de assinatura** (Pro/Max/Team) — numa máquina com navegador rode
   `claude setup-token`, faça o login e leve o token gerado.
2. **Chave da Console** (cobrança por uso) — `export ANTHROPIC_API_KEY=sk-ant-…`;
   o Claude Code pede aprovação da chave uma vez.

Conta gratuita do Claude.ai não dá acesso ao Claude Code.

## 4. Por que o proxy vai no settings.json, e não só no shell

Variável exportada no shell só vale para a sessão daquele terminal. Os agentes
de segundo plano rodam sob um supervisor à parte, que herda o ambiente de
qualquer shell que o tenha iniciado primeiro — ou nenhum. O bloco `env` do
`~/.claude/settings.json` é a única configuração que alcança todas as sessões.

## 5. Gerar o pacote (máquina com internet)

```bash
bash scripts/claude-offline/empacotar-claude-offline.sh linux-x64 stable
```

O script resolve a versão do canal, baixa o manifesto, **confere a assinatura
GPG** (fingerprint `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE`) e o
SHA256 do binário, e fecha `dist/claude-code-<versão>-<plataforma>.tar.gz`
(~91 MB) com o `.sha256` ao lado. Publique os dois como assets de uma release
com a tag `claude-code-<versão>`.

Plataformas aceitas: `linux-x64` (padrão), `linux-arm64`, `linux-x64-musl`,
`linux-arm64-musl`. O canal `stable` fica cerca de uma semana atrás do `latest`
e pula releases com regressão conhecida — é o que se quer num servidor.

## 6. Duas decisões que parecem detalhe e não são

**Não usamos `claude install`.** O instalador embutido no binário resolve o
canal `latest` e **baixa da internet**: num teste, um pacote 2.1.228 instalou
2.1.238 vindo da rede. Num servidor sem saída isso falha; num com saída,
instala uma versão diferente da homologada. A instalação é uma cópia
determinística do binário que veio no pacote.

**Não penduramos isso no `deploy.sh`.** O Claude Code é ferramenta de operação,
não artefato do produto. O `deploy.sh` roda com `set -e`: uma falha de download
aqui abortaria o deploy do Orquestra no meio. Fica em script separado, chamado
quando se quer.

## 7. Diagnóstico

```bash
claude --version   # versão instalada
claude doctor      # instalação e settings, sem abrir sessão
claude --debug     # log em ~/.claude/debug/<sessão>.txt: mostra proxy e CA carregados
```

No log do `--debug`, as linhas que confirmam a configuração:

```
CA certs: Appended extra certificates from NODE_EXTRA_CA_CERTS (/etc/ssl/certs/ca-corporativa.pem)
```

Dentro de uma sessão, `/status` mostra as linhas **Proxy** e
**Additional CA cert(s)**.

## 8. Atualizar

O auto-update fica desligado (`DISABLE_AUTOUPDATER=1`) — em servidor de versão
homologada o binário não pode se trocar sozinho. Atualizar = gerar o pacote da
nova versão, publicar a release e rodar o script de novo. As versões antigas
ficam em `~/.local/share/claude/versions/`; apague à mão o que não usar.
