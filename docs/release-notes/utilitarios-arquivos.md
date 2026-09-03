# 🧰 Utilitários — arquivos do servidor do DataStage pela tela

**Compatibilidade:** Apache Airflow 2.x | SQL Server | servidor Unix com SFTP (OpenSSH)
**Migration:** **105** (`105_utilitarios_arquivos.sql`, deploy.sh etapa 6c — responder **s**)
**Spec:** `docs/spec-utilitarios-arquivos.md` (F1–F7, PRs #356–#363)
**Manual:** `docs/MANUAL_USUARIO.md` §2.5 (ver), §3.7 (criar/editar), §4.7 (Admin)

---

## 📋 Resumo

Nova tela **Utilitários** (menu Operação, depois do Console DataStage) para
quem precisa **ver o conteúdo de um arquivo** do servidor do DataStage — um
`.param`, um log, uma carga — e para quem precisa **criar ou editar** um
arquivo de parâmetro ou de configuração, sem pedir acesso SSH nem esperar
alguém copiar o arquivo. Tudo passa pela API por SFTP, **só abaixo dos
diretórios que o administrador liberou**, com auditoria de cada leitura,
listagem e gravação.

```
Admin › Sistema › Utilitários            Utilitários (Operação)
┌─────────────────────────────┐          ┌──────────────────────────────────┐
│ Diretórios-raiz             │          │ [Ver arquivo] [Criar/editar]     │
│  /dados/bi          Testar  │  ──────▶ │ Servidor  Pasta [Navegar…]       │
│  /dados/param       Testar  │          │ Nome do arquivo   [Iniciar]      │
│ Extensões graváveis         │          │                                  │
│  txt sql param cfg …        │          │  ┌ modal: conectando → lendo ┐   │
│ Limites: teto 2048 KB, .bak │          │  │ conteúdo … [Copiar]       │   │
└─────────────────────────────┘          └──┴───────────────────────────┴───┘
```

> **Impacto para a operação:** o conteúdo de um `.param` ou o fim de um log
> aparece na tela em segundos, com botão Copiar, sem abrir chamado para a
> sustentação.
>
> **Impacto para a engenharia ETL:** parâmetro de carga se edita pela tela,
> com cópia de segurança automática e sem risco de deixar o arquivo pela
> metade (o job que lê no meio vê o antigo ou o novo, nunca meio arquivo).
>
> **Impacto para a segurança:** nenhum diretório vem de fábrica; o admin
> cadastra as raízes, testa cada uma e decide as extensões graváveis. Fora das
> raízes a resposta é sempre "fora dos diretórios liberados", sem revelar se o
> caminho existe. Toda tentativa fica na auditoria com matrícula e caminho.

---

## 🚚 O que entra

| Fase | Entrega |
|---|---|
| **F1** | Migration 105 (`etl_utilitario_raiz`, `etl_utilitario_extensao` com semente de 15 extensões — `sh` fora —, `etl_utilitario_arquivo_log`, chaves de config, permissão `tela_utilitarios`), `POST /utilitarios/arquivo/ler` (texto até o teto, "últimas N linhas" para log grande, UTF-8/Latin-1 detectados), CRUD de raízes e extensões, harness `sshd-amostra` no DEV |
| **F2** | Admin › Sistema › **Utilitários**: raízes com Testar/Editar/Desativar/Reativar, extensões com confirmação (alerta para `sh`), teto por arquivo e cópia de segurança |
| **F3** | Tela **Utilitários › Ver arquivo**: pasta + nome (+ últimas N linhas), modal conectando → lendo → conteúdo, Copiar (funciona em HTTP), avisos antes de chamar a API |
| **F4** | `POST /utilitarios/arquivo/gravar`: extensão da lista, CRLF → LF, codificação escolhida, 409 antes de sobrescrever, `.bak-<data-hora>` na mesma pasta, escrita atômica preservando permissões |
| **F5** | Aba **Criar/editar arquivo**: editor com contador, Carregar existente, Ctrl+Enter, confirmação de sobrescrita com tamanho e data do atual, resultado com hash e cópia; guarda de texto não gravado ao trocar de aba; a **causa** do erro de gravação na tela (pasta somente leitura, sem espaço, sem permissão) |
| **F6** | **Navegar…** nas duas abas: lista das raízes, migalhas, Subir/Backspace sem passar da raiz, ocultos escondidos por padrão, clique em arquivo preenche os campos |
| **F7** | Manual, esta release note, smoke no DEV e backlog registrado |

## 🔒 Como a segurança funciona

- **Raízes**: só o que o admin cadastrou (e está ativo) pode ser aberto — e
  tudo abaixo. Pastas do sistema (`/etc`, `/usr`, `/dev`, `/root`…) são recusadas
  no cadastro **e** quando uma raiz aponta para elas por link no servidor.
- **Caminhos**: `..`, `//`, links simbólicos e prefixos enganosos (`/dados2`
  sob `/dados`) são conferidos antes do SSH e de novo no servidor, pasta a
  pasta. Link para dentro de uma raiz vale; para fora, é negado.
- **Extensões** valem para **gravar**; ler depende só da raiz. `sh`, `bat` e
  afins não vêm na semente — o admin inclui conscientemente.
- **Auditoria** em `dbo.etl_utilitario_arquivo_log`: matrícula, servidor, ação
  (`ler`, `listar`, `gravar`, `testar`, `raiz`), caminho real, tamanho, hash
  SHA-256, resultado (`ok` / `negado` / `erro`) e duração. **Nunca o conteúdo.**
- **Quem faz o quê**: operador lê e navega; desenvolvedor e admin também
  gravam; perfis sem a tela não veem o menu e recebem 403 na API.

## 🚀 Deploy

1. Migration **105** na etapa 6c do `deploy.sh` (idempotente; a semente de
   extensões só entra com a tabela vazia — reexecutar não ressuscita extensão
   excluída). `config/` do nginx: **n**.
2. `api/` (imagem da API) e `ui-react/dist`. Sem `dags/`, sem wheel nova.
3. No `.env` da API: as mesmas variáveis do Console DataStage (`DS_SSH_HOST`,
   `DS_SSH_USER`, `DS_SSH_PASSWORD` ou `DS_SSH_KEY_FILE`). **Recomendado**
   `DS_SSH_KNOWN_HOSTS` — com ela, só a host key conhecida do servidor entra.
   O arquivo precisa estar **dentro do container da API**: o compose só monta
   `dags/` e `dsx/` (`/opt/airflow/dags`, `/opt/airflow/dsx`). Gere e aponte:
   ```bash
   ssh-keyscan -p "${DS_SSH_PORT:-22}" "$DS_SSH_HOST" > dsx/known_hosts   # no host, em /opt/airflow
   # .env: DS_SSH_KNOWN_HOSTS=/opt/airflow/dsx/known_hosts
   ```
   Caminho do host que o container não enxerga = 503 "aponta para um arquivo
   que a API não consegue ler" em toda a tela.
4. **Relogin**: a permissão `tela_utilitarios` só aparece depois de sair e
   entrar de novo (as permissões vivem no navegador até o próximo login).
5. Admin › Sistema › Utilitários: cadastrar as raízes de produção e clicar
   **Testar** em cada uma. **Decisão registrada na spec (§8.9): não cadastrar
   como raiz diretórios de projeto com `.param` de credencial** — toda raiz
   ativa vale para ler e gravar.
6. Rodar o smoke §7 da spec (a–p) e conferir a auditoria.

## ⚠️ Limites conhecidos (backlog)

- Uma raiz vale para ler **e** gravar (sem "só leitura" por raiz).
- `.bak` não é expurgado no servidor; o log de auditoria também não.
- O editor só grava `nome.extensão` em minúscula: `RELATORIO.TXT` ou `README`
  se leem pela aba Ver arquivo, mas não se editam por aqui.
- Um servidor só (DataStage); levar o utilitário ao Console e a outros
  servidores é uma entrada nova no registro `SERVIDORES`.
