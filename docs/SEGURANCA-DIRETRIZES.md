# Diretrizes de Segurança — ORQUESTRA

> Regras para **toda nova evolução** (endpoint, DAG, tela, config). Derivadas da
> análise em `docs/seguranca-analise.md`. Curtas e acionáveis: se um PR fere uma
> regra aqui, ele não entra sem justificativa explícita.

## Princípio
> **Falhar fechado.** Sem auth → 401. Sem origem CORS → bloqueia. Sem env de
> segredo → não sobe. Default nunca pode ser o caminho inseguro.

---

## 1. Autenticação & Autorização
- **Todo endpoint que muda estado (POST/PUT/PATCH/DELETE) tem `Depends(require_perm(...))`** ou `get_admin_user`. GET que expõe dado sensível (logs, conexões) também.
  - Não existe rota "incluída sem auth": ao criar um router, confira cada handler.
- **O ator de auditoria vem do principal autenticado** (`_auth["matricula"]`), **nunca do body** (`body.get("user")`).
- **Nunca** devolver credencial de serviço (Airflow/AD/DB) para o navegador. Chamada a sistema externo é **server-side**, com a credencial só no backend.
- Permissão por recurso (`PERM_EDITAR`/`PERM_EXECUTAR`/`tela_*`) coerente com a ação.

## 2. Segredos
- **Nunca** commitar segredo (senha, client_secret, webhook, token, Fernet key). Procurar antes de subir: `git grep -niE "password|secret|api_key|token" -- '*.py' '*.yaml'`.
- Segredo vem de **env / secret store** (`os.getenv`), nunca hardcoded. Default de env de segredo = **obrigatório** (`${VAR:?}`), nunca um valor funcional.
- Config sensível em `etl_app_config` deve ser **mascarada** na resposta da API (admin inclusive) e, idealmente, **criptografada em repouso**.
- `GET /config` público continua **filtrando** chaves sensíveis (`SENSITIVE_CONFIG`).
- `FERNET_KEY` do Airflow sempre setada (secrets de Connection/Variable criptografados).

## 3. SQL (injeção)
- **Sempre parametrizado**: `cur.execute(sql, params)` com `?`/`%s`. **Proibido** `f"... {valor_do_usuario} ..."`, `.format`, `+` ou `%` com entrada em SQL.
- WHERE/IN dinâmicos: monte **só placeholders** (`",".join("?" for _ in itens)`) e passe os valores em `params`. O texto do SQL nunca recebe input.
- Nomes de coluna/tabela dinâmicos só de fonte interna (ex.: `INFORMATION_SCHEMA`), nunca do request.
- `TOP`/`LIMIT`/datas: prefira `TOP (?)` / `-?`. Se usar `int`, **force `int()` e clamp** (`min/max`).

## 4. Comando / Shell (SSH, dsjob)
- **Nunca** interpolar nome de job/projeto/comando cru num comando shell.
- Validar identificadores contra allowlist **antes** de montar o comando:
  `_SAFE_JOB_RE = re.compile(r"^[A-Za-z0-9_.]+$")` — e **single-quote** o valor.
- Modelo correto: `dags/etl_ds_malha_status.py` (`_JOB_RE` + `'{j}'`). Modelo a evitar: interpolação crua.
- Para comando de usuário (shell job), `shlex.quote`.

## 5. Geração de código (DAG factory)
- Toda string vinda do banco embutida em código gerado usa **`repr()`/`json.dumps()`**, nunca `f'"{valor}"'`.
- `job_name`, `job_command`, `project`, `domain`, `url`, `module` validados por **allowlist no momento do register** (`api/routers/jobs.py`), não só no gerador.
- Manter o `ast.parse` final como rede, mas **não** como única defesa.

## 6. Entrada & Arquivos
- Path de arquivo a partir de input: passar por `_safe_project`/`_safe_project_name` (barra `/`, `\`, `..`) **e** validar containment (`os.path.realpath(...).startswith(base)`).
- XML/parsers: usar `xml.etree` (sem entidades externas) ou `defusedxml`. Nunca `lxml` com `resolve_entities=True`.
- Validar tipo/tamanho/charset de uploads; manter `client_max_body_size` no nginx.

## 7. Superfície da API
- **CORS** explícito (allow-list por env), **sem** `*`, e **sem** `*` junto de `allow_credentials=True`.
- **Erro pro cliente é genérico** (`"Erro interno"` + id de correlação); o detalhe vai pro **log server-side** (`log.exception`). Nunca devolver `str(e)`, stack, ou `r.text` de sistema interno.
- **Rate-limit** em `/auth/login` (nginx `limit_req` e/ou `slowapi`) + backoff por conta.
- Proxy para sistema externo: validar `dag_id`/ids (regex), **whitelist** de parâmetros e de campos do body; não repassar URL/host controlado pelo usuário (anti-SSRF).

## 8. Frontend
- React auto-escapa: **não** usar `dangerouslySetInnerHTML`/`innerHTML` com conteúdo do usuário. Se inevitável, **DOMPurify** antes.
- Token: preferir cookie `HttpOnly/Secure/SameSite`. Se `localStorage`, **CSP estrita** e TTL curto. Token sempre no header `Authorization`, nunca na URL.
- Sem `eval`/`new Function` com dado dinâmico.

## 9. Transporte & Sessão
- **TLS** ponta a ponta (terminar no VIP/nginx, redirect 80→443, **HSTS**). LDAP com TLS.
- Sessão com **idle timeout** + cap de TTL; ação admin de **revogar sessões** do usuário. Sessão guardada como **hash**.

## 10. Headers (nginx)
```
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'none'" always;
# com TLS: add_header Strict-Transport-Security "max-age=31536000" always;
server_tokens off;
```

---

## ✅ Checklist de PR (cole no template de PR)
- [ ] Endpoint que muda estado tem `Depends(require_perm/admin)`; ator vem do principal.
- [ ] Nenhum segredo no diff (rodou `git grep` de segredos); env de segredo é obrigatória.
- [ ] SQL 100% parametrizado (sem f-string/format/`+` com input).
- [ ] Comando shell: identificadores validados por regex + quoting; sem input cru.
- [ ] Código gerado usa `repr()`/`json.dumps()`; input validado no register.
- [ ] Path de arquivo passa por `_safe_project*` + containment.
- [ ] Erro ao cliente é genérico; detalhe só no log.
- [ ] CORS/headers/rate-limit não afrouxados.
- [ ] Frontend sem `dangerouslySetInnerHTML` de conteúdo do usuário.
