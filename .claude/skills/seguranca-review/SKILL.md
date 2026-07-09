---
description: >
  Revisão de segurança do ORQUESTRA antes de commitar mudanças em api/, dags/ ou
  config/nginx. Use SEMPRE que houver endpoint novo/alterado, SQL novo, comando
  shell/SSH, geração de código (factory), upload/arquivo, ou quando o usuário
  pedir "revisão de segurança", "está seguro?", "análise de vulnerabilidade".
---

# Revisão de segurança — ORQUESTRA

Fonte da verdade: `docs/SEGURANCA-DIRETRIZES.md` (regras) e `docs/seguranca-analise.md`
(racional). Princípio: **falhar fechado**. Rode os checks abaixo sobre o DIFF da mudança
e reporte cada item com arquivo:linha.

## 1. Auth & autorização (api/)
- [ ] Todo POST/PUT/PATCH/DELETE novo tem `Depends(require_perm(PERM_*))` ou `get_admin_user`?
      GET que expõe dado sensível (logs, conexões, config) também?
  ```bash
  # handlers sem Depends no diff — revisar um a um
  git diff main -- api/ | grep -B2 "async def\|^def" | grep -A2 "@router\."
  ```
- [ ] Ator de auditoria vem de `_auth["matricula"]`, nunca de `body.get(...)`?
- [ ] Nenhuma credencial (Airflow/AD/DB) devolvida ao navegador?

## 2. SQL (injeção)
- [ ] 100% parametrizado (`cur.execute(sql, params)` com `?`). Proibido f-string/format/`+`
      com input no texto do SQL:
  ```bash
  git diff main -- api/ dags/ | grep -nE 'execute\(f"|execute\(.*\.format|execute\(.*%\s*\(' 
  ```
- [ ] Identificador dinâmico (tabela/coluna) só de fonte interna ou validado
      (`_IDENT_RE`, `_valid_table_ident`); SELECT de usuário só via `_valid_select`
      (read-only, sem `;`/DML) e com timeout (`conn.timeout` + `TOP 100` — padrão sql-preview).

## 3. Shell/SSH e código gerado (dags/)
- [ ] Nome de job/projeto validado por regex allowlist ANTES de montar comando + single-quote
      (modelo: `dags/etl_ds_malha_status.py`); comando de usuário passa por `shlex.quote`.
- [ ] String do banco embutida em código gerado usa `repr()`/`json.dumps()` — nunca `f'"{valor}"'`
      (padrão do `etl_dag_factory.py`); validação acontece no register, `ast.parse` é só rede.

## 4. Segredos e SSRF
- [ ] Nenhum segredo no diff:
  ```bash
  git diff main | grep -niE "password|secret|api_key|token|webhook" | grep -v "PERM\|_test\|exemplo"
  ```
- [ ] Host/URL de request NUNCA usado direto: só hosts da allowlist
      (`_list_mssql_hosts()` — conexões `conn_type=="mssql"` do Airflow).
- [ ] Config sensível mascarada na API (`SENSITIVE_CONFIG`).

## 5. Frontend e superfície
- [ ] Sem `dangerouslySetInnerHTML`/`eval` com conteúdo de usuário:
  ```bash
  grep -rn "dangerouslySetInnerHTML\|eval(" ui-react/src --include=*.tsx | grep -v node_modules
  ```
- [ ] Erro ao cliente é genérico; `str(e)`/stack só no log server-side.
- [ ] CORS/headers/rate-limit não afrouxados (config/nginx).

## Veredito
Termine com: **APROVADO** ou lista de bloqueios (regra ferida + arquivo:linha + correção
sugerida). PR que fere regra não entra sem justificativa explícita.
