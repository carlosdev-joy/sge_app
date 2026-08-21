# Claude Code — instalação offline

Pacote auto-contido: o binário nativo, o manifesto assinado e o instalador.
Nada aqui baixa nada da internet.

## Instalar

```bash
tar -xzf claude-code-<versão>-<plataforma>.tar.gz
cd claude-code-<versão>-<plataforma>
bash instalar.sh
```

Rode como **o usuário que vai usar o Claude Code** — nunca com `sudo`, que
instalaria no HOME do root. Rodar logado como root é permitido (containers,
servidores operados só por root) e o instalador avisa que a instalação vale
apenas para o root. Tudo é instalado no HOME de quem executa:

- binário → `~/.local/share/claude/versions/<versão>`
- atalho  → `~/.local/bin/claude`

Nada vai para `/usr`, nada exige root, nada precisa de Node.js ou npm.

## Requisitos da máquina

| Item | Exigência |
|---|---|
| Sistema | Linux x64 ou ARM64 (o pacote é de uma plataforma só) |
| glibc | 2.17 ou mais nova — RHEL 7+, Ubuntu 20.04+, Debian 10+ |
| musl (Alpine) | precisa do pacote `-musl`, mais `libgcc`, `libstdc++` e `ripgrep` |
| RAM | ~512 MB livres para instalar; 4 GB+ para usar |
| Disco | ~700 MB (o binário tem ~339 MB e fica em duas cópias durante a instalação) |

O instalador recusa a instalação quando a plataforma do pacote não é a da
máquina — trocar glibc por musl daria um "not found" que não explica a causa.

## Rede — o ponto que instalar NÃO resolve

O Claude Code fala com a API da Anthropic **a cada mensagem**. Instalado num
servidor sem saída, ele abre e não responde. Libere no firewall/proxy:

| Host | Para quê |
|---|---|
| `api.anthropic.com` | toda requisição ao modelo — **obrigatório** |
| `platform.claude.com` | login e renovação do token — obrigatório para autenticar |
| `claude.ai` | login por conta claude.ai |
| `downloads.claude.ai` | só para atualizar; dispensável neste modo offline |
| `registry.npmjs.org` | só para plugins e servidores MCP via `npx` |

Atrás de proxy corporativo, exporte antes de abrir o `claude`:

```bash
export HTTPS_PROXY=http://proxy.empresa:8080
export NO_PROXY="localhost,127.0.0.1,.empresa.local"
# quando o proxy inspeciona TLS (Zscaler, Falcon e afins):
export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-corporativa.pem
```

Se o proxy exigir autenticação, a senha vai na URL
(`http://usuario:senha@proxy.empresa:8080`) e o instalador a copia para
`~/.claude/settings.json` — arquivo que ele cria com modo 600 e avisa na tela.
Ainda assim root e as rotinas de backup leem esse arquivo: prefira pedir ao time
de rede uma exceção sem autenticação para o servidor.

Se a CA corporativa já estiver no truststore do sistema, o binário nativo a lê
sozinho — `NODE_EXTRA_CA_CERTS` só é necessário quando não está.

Para valer em qualquer shell e em agentes de segundo plano, ponha as mesmas
variáveis no bloco `env` de `~/.claude/settings.json` em vez de só exportar.

## Autenticar sem navegador no servidor

Duas opções — o servidor não abre navegador:

1. **Token de assinatura** (Pro/Max/Team): numa máquina com navegador, rode
   `claude setup-token`, faça o login e leve o token gerado para o servidor.
2. **Chave da Console** (cobrança por uso): `export ANTHROPIC_API_KEY=sk-ant-...`
   — o Claude Code pede aprovação da chave uma única vez.

Conta gratuita do Claude.ai não dá acesso ao Claude Code.

## Auto-update

O instalador grava `DISABLE_AUTOUPDATER: "1"` em `~/.claude/settings.json`
quando o arquivo ainda não existe — num ambiente de versão homologada o binário
não pode se trocar sozinho. Se o arquivo já existia, ele não é tocado e o
instalador avisa o que acrescentar.

Para bloquear também o `claude update` manual, use `DISABLE_UPDATES: "1"`.

Atualizar = gerar um pacote novo na máquina com internet e repetir a instalação.

## Conferir depois

```bash
claude --version   # imprime a versão instalada
claude doctor      # diagnóstico de instalação e configuração, sem abrir sessão
claude --debug     # log em ~/.claude/debug/<sessão>.txt — mostra proxy e CA carregados
```

## Desinstalar

```bash
rm -f  ~/.local/bin/claude
rm -rf ~/.local/share/claude
# configurações e histórico (opcional):
rm -rf ~/.claude ~/.claude.json
```
