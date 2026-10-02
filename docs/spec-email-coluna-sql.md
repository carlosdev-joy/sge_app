# Spec: Valor de cada coluna do SQL no e-mail (`{coluna:…}`) — Orquestra
Data: 2026-10-02 · Status: 🏁 **CONCLUÍDA** — F1 #472, F2 (esta) · ⏳ deploy em produção pendente · versão 2.6.0 (migration 138)

Substitui o rascunho `/dados/bi/spec-email-placeholders-coluna-sql.md` (container
`orquestra-dev-sshd-amostra`), cuja sintaxe `{NO:ALIAS}` / `{:ALIAS}` não casava com o
`PLACEHOLDER_RE` real — ver §9.

## 1. Visão

O nó de e-mail já entrega `{tabela}` e `{tabela:NOME}` — o resultado INTEIRO da
consulta como bloco HTML. Alguns avisos precisam de **cada valor solto**: um número
num card de métrica, um mês no meio de uma frase, uma tabela de layout próprio. O
caso real é o `DM_CLIENTES_CONTRATOS_HIST_CVP`, cujo HTML tem os cards "Total
carregado", "Ativos", "Inativos" e "Ativos indevidos".

Esta spec entrega o marcador **`{coluna:ALIAS}`**: quando o nó SQL a montante devolve
**uma linha**, cada coluna vira um valor que o HTML usa onde quiser.

```sql
SELECT FORMAT(TotalInserido, 'N0', 'pt-BR') AS total, ...
```
```html
<td>Total carregado</td><td><b>{coluna:total}</b></td>   →   <b>17.326.307</b>
```

## 2. Escopo

**IN:**
- `{coluna:ALIAS}` — coluna `ALIAS` do **único** nó SQL imediatamente a montante.
- `{coluna:NO.ALIAS}` — coluna `ALIAS` do nó SQL `NO` (obrigatório com 2+ nós SQL).
- Vale no **corpo** (HTML escapado / texto puro) e no **assunto** (texto puro).
- Painel do nó: `coluna` no catálogo, opção "Coluna de um SQL: informar…" no seletor,
  prévia com valor de exemplo.
- Log da task explicando todo marcador que não resolve.
- Manual, release note, migration de versão, smoke; ajuste do pipeline CVP em DEV.

**OUT (explícito):**
- **Nome do anexo:** `{coluna:…}` não resolve ali (dado de banco em caminho de arquivo
  é superfície que não precisamos abrir). O painel avisa; o worker deixa literal.
- **Resultado com 0 ou 2+ linhas:** não resolve (literal + log). Série é `{tabela}`;
  "N-ésima linha" (`{coluna:NO.ALIAS.N}`) fica para spec própria se surgir caso.
- Coluna por posição (`{coluna:0}`) — o alias é a interface estável.
- Atravessar Decisão ou nós intermediários — só o vizinho imediato (regra da `{tabela}`).
- Formatação no marcador (casas, máscara de data) — quem formata é o SELECT.
- Listar as colunas automaticamente no seletor: a prévia do `PainelSql` é estado local
  (`useState`), não é gravada em lugar nenhum. Persistir as colunas no nó é spec futura.
- Parametrizar o SQL do nó com `{odate}` — o nó SQL não interpola marcadores hoje.

## 3. Arquitetura

### 3.1 Sintaxe — sem mudar o regex

`PLACEHOLDER_RE` (`dags/utils/email_envio.py:43`, `api/services/email_mime.py:49`, os
dois regex de `previaEmailDados.ts`) é `\{([a-z_]+)(?::([A-Za-z0-9_.\-]{1,128}))?\}`.
`coluna` é minúsculo e o qualificador já aceita `.` — **os 4 espelhos ficam como estão**.

Separação do qualificador: **no ÚLTIMO `.`** (`rsplit(".", 1)`), porque nome de nó
aceita `.` e `-` (`nomeSqlParaPlaceholderValido`). Consequência documentada: o alias
precisa ser `[A-Za-z0-9_]+` (alias com `.`/`-` exige `AS` simples no SELECT).

| Marcador | Resolve quando |
|---|---|
| `{coluna:total}` | há **exatamente 1** nó SQL a montante, com 1 linha e coluna `total` |
| `{coluna:SQL_1.total}` | o nó `SQL_1` está a montante, com 1 linha e coluna `total` |

Comparação do alias: **exata** (case-sensitive), igual à chave de `interpolar`. Se o
alias só diferir na caixa, o log sugere a grafia certa.

### 3.2 Worker — `dags/utils/email_operator.py`

`_marcadores_de_coluna(self, context, html, texto) -> dict`, análogo a
`_marcadores_de_tabela`:

1. Guard barato: se `"{coluna:"` não está no texto, devolve `{}` sem ler XCom.
2. `tabelas = self._tabelas_a_montante(context)` (já existe).
3. Para cada tabela com `len(rows) == 1`, para cada coluna com nome válido
   (`[A-Za-z0-9_]+`, não vazio, não repetido na tabela):
   - `coluna:NO.ALIAS` → `_valor(linha[i])`;
   - se só há 1 nó SQL a montante, também `coluna:ALIAS`.
4. `_valor`: `None`/`""` → `""` (**nunca** `None`: `interpolar` deixaria literal);
   resto `str(v)`; no corpo HTML, `html.escape(..., quote=False)` — `valor_publicavel`
   **não escapa** (o escape da tabela está em `sql_node._celula`). Assunto: sem escape.
5. Logs (só para marcadores presentes no texto e não resolvidos), prefixo `[EMAIL]`:
   - `{coluna:X} não resolve — SQL_1 trouxe N linhas (esperado: 1)`;
   - `{coluna:X} não resolve — SQL_1 não tem a coluna X (colunas: a, b, c)` (+ dica de caixa);
   - `{coluna:X} não resolve — 2 nós SQL a montante (A, B): use {coluna:NO.X}`;
   - `{coluna:NO.X} não resolve — a montante existem: A, B`;
   - `coluna sem nome/repetida em SQL_1 (posição k) — dê um alias no SELECT`;
   - aviso de que `LIMITE_COLUNAS=15` corta colunas (`colunas_ocultas > 0`) e que a
     célula chega cortada em `LIMITE_CELULA=200` caracteres.
   - resolvidos: `[EMAIL] coluna SQL_1.total resolvida` (sem o valor — pode ser dado sensível).

Integração em `execute()`:

```python
corpo = ev.interpolar(corpo_bruto, {**mapa,
        **self._marcadores_de_tabela(context, html, corpo_bruto),
        **self._marcadores_de_coluna(context, html, corpo_bruto)})
assunto = ev.interpolar(assunto_bruto, {**mapa,
        **self._marcadores_do_assunto(context),
        **self._marcadores_de_coluna(context, False, assunto_bruto)})
```

Chaves `coluna:*` e `tabela:*` não colidem (prefixos diferentes). O anexo continua
interpolado só com o `mapa` — `{coluna:…}` sai literal ali por construção.

⚠️ O escalar (`return_value`) e a chave `tabela` do XCom **não mudam**.
⚠️ `dags/utils/` é cacheado pelo worker: restart obrigatório no deploy.

### 3.3 Painel / prévia (front)

- `EMAIL_PLACEHOLDERS` (`fluxoTypes.ts`) ganha `coluna`; `emailPlaceholderCatalogo`
  o exclui do campo `anexo` (como já faz com `tabela`).
- `EmailPlaceholderPicker`: opção **"Coluna de um SQL: informar…"** → campos
  "Coluna (alias do SELECT)" e "Nó SQL" (lista `sqlNames` + "o único a montante").
  Insere `{coluna:ALIAS}` ou `{coluna:NO.ALIAS}` na posição do cursor. Validação do
  alias `[A-Za-z0-9_]{1,64}`.
- `VALORES_EXEMPLO.coluna` + `interpolarExemplo`: a prévia mostra o **nome da coluna
  destacado** (ex.: `‹total›`, escapado) — não há corrida na tela para saber o valor; o
  aviso de "dados fictícios" já existente cobre.
- `marcadoresDesconhecidos` passa a conhecer `coluna`; aviso no painel quando
  `{coluna:…}` aparece no nome do anexo.
- Texto de ajuda: "resolve só com resultado de 1 linha; o alias é o `AS` do SELECT".

## 4. Modelo de dados

Nenhuma tabela/coluna nova. Só a migration idempotente de **versão** (138 → 2.6.0).

## 5. Fases (ordem de execução: front validado → backend)

⚠️ Tela e worker saem na MESMA PR (F1). O teste-âncora de paridade
(`tests/test_email_previa.py`) exige que todo marcador oferecido pelo seletor seja
resolvido pelo operador: mergear só a tela deixaria o botão *Inserir* produzindo um
marcador que o envio deixa literal. A execução segue a regra — tela primeiro,
validada com impeccable + Chrome, e só então o worker.

### F1 — Tela + worker
- **Tela (§3.3):** catálogo, opção "Coluna de um SQL: informar alias…", prévia
  `‹alias›`, avisos do grafo (`avisosColunaEmail`), anexo sem `coluna`.
- **Worker (§3.2):** `_marcadores_de_coluna` no corpo e no assunto.
- **Aceite (tela):** inserir `{coluna:total}` e `{coluna:SQL_1.total}` no cursor, com
  foco preservado; com 2+ SQL o *Inserir* só libera após escolher o nó; prévia mostra
  `‹total›`; anexo não oferece `coluna` e avisa se digitado; claro/escuro.
- **Aceite (pytest):** 1 linha resolve nas duas formas; 0 e 2 linhas → literal + log;
  teto de leitura não conta como 1 linha; 2 nós → forma curta literal, longa resolve;
  coluna inexistente/caixa errada → literal + dica; NULL → vazio; `<b>&"` escapado no
  HTML e cru no assunto/texto; nó com `.` no nome; alias vazio/repetido com log;
  `{tabela:SQL_1}` + `{coluna:SQL_1.x}` juntos; anexo não resolve; sem marcador não
  lê nem avisa.
- **Validação:** `tsc -b`; eslint zero delta; pytest completo vs. `develop`; build com
  `dist/`; impeccable detect + Chrome no DEV; restart do worker do DEV.
- PR: `feat(email): marcador {coluna:…} — valor de uma coluna do SQL no e-mail`.

### F2 — Docs, versão e smoke
- **Inclui:** manual (seção `{coluna:…}`: quando resolve, quando fica literal, limites
  15 colunas / 200 caracteres, alias), release note, migration `138` (2.6.0),
  roteiro de deploy (rebuild `dist/` + restart do worker) e §7.
- PR: `docs(email): marcador {coluna:…} + versão 2.6.0`.

Depois da F2 (configuração, não PR): ajuste do `DM_CLIENTES_CONTRATOS_HIST_CVP` em DEV
(§6) e promoção para a `main` mediante autorização.

## 6. Pipeline `DM_CLIENTES_CONTRATOS_HIST_CVP` (configuração)

O pipeline não está no repositório — o ajuste é feito pela interface, em DEV primeiro.

1. **Antes de tudo:** conferir se há Decisão `valor_sql` a jusante do `SQL_1`. O escalar
   é a 1ª célula crua; a query nova muda a 1ª coluna de `resumo` para `mes`. Se houver,
   ajustar a condição junto (ou manter `resumo` como 1ª coluna).
2. Query do `SQL_1` com colunas nomeadas (1 linha):
   ```sql
   SELECT
       CONCAT(LEFT(CAST(AnoMes AS char(6)),4),'/',RIGHT(CAST(AnoMes AS char(6)),2)) AS mes,
       FORMAT(ISNULL(TotalInserido,0),      'N0','pt-BR') AS total,
       FORMAT(ISNULL(QtdAtivos,0),          'N0','pt-BR') AS ativos,
       FORMAT(ISNULL(QtdInativos,0),        'N0','pt-BR') AS inativos,
       FORMAT(ISNULL(QtdAtivosIndevidos,0), 'N0','pt-BR') AS indevidos,
       CAST(ISNULL(DATEDIFF(minute, DtaInicio, DtaFim),0) AS varchar(10)) AS duracao_min,
       CAST(CAST(100.0*QtdInativos/NULLIF(TotalInserido,0) AS decimal(5,2)) AS varchar(10)) AS pct_inativos
   FROM dbo.ctrl_carga_hist_cvp
   WHERE AnoMes = CAST(FORMAT(DATEADD(month,-1,GETDATE()),'yyyyMM') AS int)
   ```
   O `WHERE` derivado de `GETDATE()` é proposta — **a regra do mês de referência é do
   analista do pipeline** (pendência §8.1). `duracao_min` evita colidir com o `{duracao}`
   do mapa padrão.
3. HTML do `NOTIFICA_CLIENTE`: `{mes}`, `{total}`… → `{coluna:mes}`, `{coluna:total}`…
   `{status}` continua (status do pipeline, mapa padrão).
4. Corrida de teste em DEV: nenhum `{…}` literal; cards com os valores reais.

## 7. Smoke pós-deploy

a) Prévia (F1): `{coluna:total}` mostra `‹total›`; seletor insere as duas formas.
b) Worker reiniciado: log da task de e-mail tem `[EMAIL] coluna SQL_1.total resolvida`
   (sem essa linha = código velho em cache).
c) CVP em DEV: e-mail recebido com valores nos cards, nenhum `{…}` literal.
d) 2 linhas (`UNION ALL`): literal + log `trouxe 2 linhas (esperado: 1)`.
e) Forma curta com 1 nó resolve; com 2 nós sai literal + log; forma longa resolve.
f) Regressão: fluxo com `{tabela}` inalterado; Decisão `valor_sql` roteando igual.

## 8. Pendências

1. Regra do mês de referência na query do CVP (analista do pipeline).
2. Decisão `valor_sql` a jusante do `SQL_1` do CVP — conferir antes da troca da query.
3. Futuro: persistir as colunas da prévia no nó SQL para o seletor listar sozinho.

## 9. Diferenças em relação ao rascunho de 02/10

| Rascunho | Esta spec | Motivo |
|---|---|---|
| `{SQL_1:mes}` / `{:mes}` + mudança do regex em 3 espelhos | `{coluna:SQL_1.mes}` / `{coluna:mes}`, regex intacto | O grupo externo real é `[a-z_]+`; são 4 espelhos; sintaxe do rascunho colidia com nó chamado `tabela` |
| "`valor_publicavel` já escapa" | escape próprio no worker | o escape está só em `_celula` |
| — | NULL → vazio | `interpolar` deixa literal valor `None` |
| seletor lê "última prévia salva" | campo "informar coluna" | a prévia do SQL não é persistida |
| F4 = PR do pipeline | configuração em DEV | pipeline não está no repo |
| `{odate}` no SQL | `GETDATE()` / decisão do analista | nó SQL não interpola marcadores |
