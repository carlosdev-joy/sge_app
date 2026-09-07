# ⬇️⬆️ Utilitários — baixar e enviar arquivos do servidor do DataStage pela tela

**Compatibilidade:** Apache Airflow 2.x | SQL Server | servidor Unix com SFTP (OpenSSH)
**Migration:** nenhuma (a coluna `acao` da auditoria já comporta `baixar` e `enviar`)
**Spec:** `docs/spec-utilitarios-transferencia.md` (F1–F5, PRs #364–#368)
**Manual:** `docs/MANUAL_USUARIO.md` §2.5 (Baixar), §3.8 (Enviar arquivo), §4.7 (Admin), §5 (FAQ)
**Depende de:** Utilitários de arquivos (`docs/release-notes/utilitarios-arquivos.md`, migration 105)

---

## 📋 Resumo

A tela **Utilitários** passa a levar arquivos nos dois sentidos entre o
computador do usuário e o servidor do DataStage, sem cliente SFTP e sem
credencial na mão: **Baixar** qualquer arquivo abaixo das raízes liberadas
(binário incluído — o `.dsx`, o `.zip`, o log inteiro que o Ver arquivo
recusava) e a aba **Enviar arquivo**, com barra de progresso, cancelamento e a
mesma confirmação de sobrescrita, cópia de segurança e escrita atômica da
gravação de texto. Teto de **50 MB** por transferência. Tudo auditado.

```
Utilitários (Operação)
┌─────────────────────────────────────────────────────────────────────┐
│ [Ver arquivo] [Criar/editar arquivo] [Enviar arquivo]               │
│                                                                     │
│  Ver arquivo › modal:  conteúdo … [Copiar] [Baixar]                 │
│                        "não é texto" / "acima do teto"              │
│                                          [Baixar o arquivo]         │
│  Navegar… › cada arquivo: nome  tamanho  data  ⬇                    │
│                                                                     │
│  Enviar arquivo:  Pasta [Navegar…]  [Escolher arquivo…] nome.ext    │
│                   Nome no servidor [Relatorio.TXT]  [Enviar]        │
│                   modal: ▓▓▓▓▓▓▓░░░ 12 MB de 40 MB  [Cancelar]      │
│                          "já existe" → [Sobrescrever]               │
└─────────────────────────────────────────────────────────────────────┘
                 faixa: Baixando carga.bin… 12 MB de 40 MB
```

> **Impacto para a operação:** um log inteiro ou um arquivo sequencial desce
> para o computador em um clique, pela mesma tela onde já se lia.
>
> **Impacto para a engenharia ETL:** planilha de parâmetros, `.dsx` exportado
> ou arquivo de carga sobe para o servidor com progresso, sem WinSCP, com
> confirmação antes de sobrescrever e cópia de segurança do que estava lá.
>
> **Impacto para a segurança:** mesmas raízes, mesmas permissões (baixar =
> ter a tela; enviar = cadastrar/editar), mesma política de caminho da
> leitura e da gravação; nenhuma permissão nova, nenhuma migration; toda
> transferência na auditoria com matrícula, caminho, tamanho e hash.

---

## 🚚 O que entra

| Fase | Entrega |
|---|---|
| **F1** | `GET /utilitarios/arquivo/baixar`: qualquer arquivo abaixo de uma raiz, até 50 MB, 413 pelo `stat` antes de abrir, resposta em blocos com `Content-Length` exato e nome com acento preservado; **2 vagas de transferência** por worker (503 "ocupado" na hora), timeout próprio de 240 s; auditoria `baixar`; `transferencia_max_kb` no config |
| **F2** | **Baixar** ao lado de Copiar no modal, **Baixar o arquivo** quando a leitura recusa (não é texto / acima do teto), **ícone de download por linha** no navegador de pastas; faixa de transferência com progresso, acima do modal que a disparou; download autenticado (o token vive no navegador, não em cookie) contando os bytes contra o `Content-Length` — arquivo pela metade é recusado, nunca salvo truncado |
| **F3** | `PUT /utilitarios/arquivo/enviar`: corpo cru (sem multipart, sem dependência nova), nome mantido como está e só a última extensão conferida com a lista; **413 pelo `Content-Length` antes de ler um byte**, corpo contado, vaga só com o corpo inteiro, 408 se o envio parar; mesmo miolo da gravação (409, `.tmp` exclusivo, backup, rename atômico, permissões preservadas); auditoria `enviar` com o **desfecho tardio** de um envio que estourou o tempo |
| **F4** | Aba **Enviar arquivo**: seletor de arquivo, nome pré-preenchido e editável, avisos antes da API (extensão, teto, pasta), barra de progresso, **Cancelar** (só enquanto sobe — depois que o corpo chegou, fechar o modal não interrompe, porque o servidor grava de qualquer forma), 409 → **Sobrescrever** com o mesmo arquivo, região de leitor de tela com marcos |
| **F5** | Manual (§2.5, §3.8, §4.7, FAQ), esta release note, smoke no DEV e backlog registrado |

## 🔒 Como a segurança funciona

- **Nada novo de acesso**: baixar exige a tela `tela_utilitarios` (como ler);
  enviar exige a tela **e** `acao_editar` (como gravar). Sem relogin.
- **Caminhos**: a mesma régua de `..`, `//`, links e prefixos enganosos, antes
  do SSH e de novo no servidor, pasta a pasta. Nome com caracteres de controle
  ou **invisíveis de formatação** (o U+202E que inverte a leitura de
  `‮txt.exe`) é recusado nos dois sentidos.
- **O download alarga o que se lê** — só a heurística "é texto" saía da
  frente, não um controle de acesso: um `.param` já saía inteiro pelo Ver
  arquivo. O controle continua sendo a raiz; por isso o manual do admin pede
  para não cadastrar a instalação nem os projetos do InformationServer.
- **O envio não cria executável**: arquivo novo nasce com o umask do servidor;
  sobrescrita preserva as permissões do existente (como a gravação de texto).
  A lista de extensões é uma só para editar e enviar — incluir `jar`/`so` é
  decisão consciente do admin.
- **Recursos**: teto de 50 MB nos dois sentidos, recusado **antes** de o
  corpo ocupar disco; 2 transferências por worker (a 3ª ouve "ocupado"); o
  arquivo passa por um spool (8 MB em memória, resto em disco temporário, sem
  nome — não sobra órfão); cliente lento não segura vaga.
- **Auditoria** em `dbo.etl_utilitario_arquivo_log`: ações `baixar` e
  `enviar` com tamanho, hash SHA-256, resultado e detalhe. **Nunca o conteúdo.**
  Um envio que estourou o tempo ganha uma segunda linha quando a gravação
  termina depois — a auditoria diz o que a tela não pôde dizer.

## 🚀 Deploy

1. **Sem migration**, sem `dags/`, sem wheel nova, sem `config/` do nginx
   (`client_max_body_size 64M` e `proxy_*_timeout 300s` já bastam — o de
   produção está à frente do repo: responder **n**).
2. `api/` (imagem da API) e `ui-react/dist`. Sem relogin (nenhuma permissão nova).
3. **Antes de liberar, conferir as raízes ativas** em Admin › Sistema ›
   Utilitários (`SELECT servidor, caminho FROM dbo.etl_utilitario_raiz WHERE
   ativo = 1`): nenhuma pode cobrir a instalação ou um projeto do DataStage —
   o download passa a entregar binários que o Ver arquivo barrava.
4. **Porta 8000 da API**: o compose publica `${API_PORT:-8000}:8000` em todas
   as interfaces. Se em produção ela for alcançável sem o nginx, publicar
   `127.0.0.1:8000:8000` (o nginx fala pela rede do compose). A API se protege
   (vaga só com o corpo inteiro, 408 de corpo parado), mas o nginx é a régua.
5. **`/tmp` gravável no container da API** (o spool acima de 8 MB vai para
   disco). Deploy com `read_only`/`tmpfs` precisa montar `/tmp`.
6. **gzip no nginx de produção**: o front conta os bytes do download contra o
   `Content-Length`; se alguém ligou `gzip` para `application/octet-stream`,
   todo download seria recusado como incompleto. Conferir:
   ```bash
   curl -sI -H 'Accept-Encoding: gzip' -H "Authorization: Bearer $TOKEN" \
     'http://<prod>/orquestra/utilitarios/arquivo/baixar?diretorio=<raiz>&nome=<arquivo>' | grep -i content-encoding
   # esperado: nada
   ```
7. Rodar `scripts/smoke_utilitarios_transferencia.sh` (itens b–n pela API;
   a, d, k e l pela tela) e conferir a auditoria.

## ⚠️ Limites conhecidos (backlog)

- Um arquivo por vez; sem download de pasta como `.zip`.
- Teto de 50 MB fixo (não configurável no Admin); acima de 64 MB o nginx
  responde antes da API.
- Download por `fetch` + Blob: o arquivo passa pela memória do navegador
  (50 MB no máximo). Um link direto com ticket assinado fica para depois.
- Cancelar o envio depois de o arquivo subir inteiro não impede a gravação (o
  nginx já recebeu tudo); a tela diz isso.
- A lista de extensões é uma só para editar texto e enviar binário; sem cota
  de disco por usuário; `.bak` sem expurgo (backlog anterior).
- Um servidor só (DataStage).
