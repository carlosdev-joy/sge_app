# Lições Aprendidas — O Que Não Fazer

Erros reais que já aconteceram neste projeto. Antes de codar, leia.

---

## DAGs / Python

### 1. SELECT sem todas as chaves que o código usa depois

**Errado:**
```python
cur.execute("SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO])
cfg = dict(cur.fetchall())
proxy = proxy_da_config(cfg)  # cfg não tem 'servicenow_proxy' → retorna None
```

**Certo:** incluir TODAS as chaves que serão lidas do `cfg` no `WHERE IN`.

**Sintoma:** log mostra `proxy = (direto)`, `Connection reset by peer`. Não há erro de Python — o bug é silencioso.

---

### 2. Sintaxe de proxy do httpx — `proxy=` vs `proxies=`

**Errado (httpx >= 0.20):**
```python
proxies = {"https://": proxy} if proxy else None
httpx.Client(..., proxies=proxies)
```

**Certo:**
```python
httpx.Client(..., proxy=proxy)   # proxy=None desativa silenciosamente
```

**Sintoma:** mesmo com proxy configurado, a conexão vai direta e falha com `Connection reset by peer`.

---

### 3. Conexão aberta sem fechar em funções utilitárias

**Errado:**
```python
def grupos_ativos(hook):
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT nome FROM ...")
    return [r[0] for r in cur.fetchall()]
    # conn e cur nunca fechados — leak a cada chamada
```

**Certo:**
```python
def grupos_ativos(hook):
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT nome FROM ...")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows
```

**Sintoma:** pool de conexões esgota após muitas execuções, erros intermitentes de banco.

---

### 4. Passar argumento para função que não aceita parâmetros

**Errado:**
```python
for aviso in conferir(__file__):
    log.warning(...)
```

**Certo:**
```python
for aviso in conferir():
    log.warning(...)
```

**Sintoma:** `TypeError: conferir() takes 0 positional arguments but 1 was given` — a DAG falha imediatamente sem executar nada.

---

### 5. DAG de sync sem filtro de grupo traz dados de toda a empresa

**Errado:**
```python
url = f"{url_base}/api/now/table/{tabela}?sysparm_fields={CAMPOS}..."
# sem sysparm_query → traz TODOS os chamados da instância
```

**Certo:** sempre aplicar `sysparm_query` com filtro de `assignment_group.name`:
```python
query = query_do_grupo(grupos)
url = f"{url_base}/api/now/table/{tabela}?sysparm_query={query}&sysparm_fields={CAMPOS}..."
```

**Sintoma:** tabela `etl_chamado` acumula chamados de grupos alheios, dados inconsistentes.

---

## Bundle React (Vite minificado)

### 6. Todos os identificadores de 3 chars já estão em uso no bundle

**Errado:** tentar nomear funções ou variáveis injetadas com nomes curtos como `Sn`, `GS`, `Cs` — colide com variáveis existentes do bundle minificado.

**Certo:** usar nomes longos e únicos: `SnGruposSection`, `SnCiclosSection`.

---

### 7. Padrão de fechamento de `jsxs` em rows do `.map()`

**Errado:**
```js
// fecha com dois parênteses — um extra
(0,U.jsxs)('tr', {children: [...]}, key))
```

**Certo:** dentro de `.map(l => { ... })`, a row fecha com UM parêntese (fecha o `jsxs`); o segundo parêntese que fecha o `.map()` vem do contexto do tbody no f-string:
```js
(0,U.jsxs)('tr', {children: [...]}, key)
// depois: ...map(l=>{ return ROW })  ← o ) que fecha map() está aqui
```

**Sintoma:** `SyntaxError: Unexpected token '.'` ou `Unexpected token '}'` no bundle em produção.

---

### 8. `return(EXPR)` com parênteses extras quebra o checker de brackets

**Errado:**
```js
return((0,U.jsxs)(...))
```

**Certo:**
```js
return (0,U.jsxs)(...)
```

**Sintoma:** checker de brackets reporta `) extra` no final da função.

---

### 9. F-string Python com objetos JS — escapar chaves

Dentro de f-strings Python, `{` e `}` são delimitadores de interpolação.

**Errado:**
```python
f"children:[{value}]"  # Python tenta interpolar `value` como variável
```

**Certo:**
```python
f"children:[{{value}}]"  # {{ → { e }} → } no output final
```

---

## Banco de Dados (SQL Server via pymssql)

### 10. Placeholder diferente entre `dags/` e `api/`

- `dags/` usa **pymssql** → placeholder `%s`
- `api/` usa **pyodbc** → placeholder `?`

**Errado:** usar `?` em queries dentro de DAGs, ou `%s` dentro de routers da API.

**Sintoma:** `Incorrect syntax near '?'` ou gravação silenciosa na coluna errada.

---

### 11. Limpar tabelas com FK sem respeitar a ordem

**Errado:** `DELETE FROM etl_chamado` antes de deletar `etl_chamado_nota` → erro de FK.

**Ordem correta (filhas antes das mães):**
1. `etl_chamado_nota`
2. `etl_chamado_anexo`
3. `etl_indicador_snapshot_analista`
4. `etl_indicador_snapshot_grupo`
5. `etl_indicador_snapshot`
6. `etl_chamado_ciclo`
7. `etl_chamado`

---

### 13. `UPDATE TOP(1) ... ORDER BY` é inválido no SQL Server

**Errado:**
```sql
UPDATE TOP(1) dbo.etl_chamado_ciclo
SET qtd_notas=%s
WHERE modo='full' ORDER BY id DESC
```

**Certo:** usar subquery para selecionar o ID alvo:
```sql
UPDATE dbo.etl_chamado_ciclo
SET qtd_notas=%s
WHERE id=(SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE modo='full')
```

**Sintoma:** `Incorrect syntax near the keyword 'ORDER'` — a task falha antes de gravar qualquer dado.

---

### 14. `datetime.utcnow()` vs `GETDATE()` — fuso horário destrói registros

**Errado:**
```python
inicio = _dt.datetime.utcnow()   # UTC — 3h à frente do SQL Server no Brasil
# ...
cur.execute("UPDATE etl_chamado SET ativo=0 WHERE sync_em < %s", [inicio])
# sync_em foi gravado com GETDATE() (UTC-3) — SEMPRE é menor que inicio (UTC)
# → TODOS os registros são desativados imediatamente após serem inseridos
```

**Certo:**
```python
inicio = _dt.datetime.now()   # horário local — mesmo fuso do GETDATE() do SQL Server
```

**Regra:** Se o banco usa `GETDATE()` (hora local), compare sempre com `datetime.now()` em Python.
Use `utcnow()` apenas se o banco usar `GETUTCDATE()` em todos os campos de timestamp.

**Sintoma:** log mostra `N desativados` igual ao total de registros inseridos,
logo após um full sync bem-sucedido. Chamados "somem" da tela imediatamente.

---

## Infraestrutura

### 12. O worker Airflow serve módulos de cache — código velho pode rodar

Após editar um arquivo em `dags/utils/`, o worker Celery pode continuar usando a versão antiga em memória.

**Como forçar reload:** o sistema `frescor_modulo.py` detecta divergência e loga aviso. Se o comportamento não mudar após editar um utilitário, reiniciar o worker resolve.

---
