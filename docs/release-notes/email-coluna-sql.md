# Release note — Valor de cada coluna do SQL no e-mail (2.6.0)

Spec: `docs/spec-email-coluna-sql.md` · PR #472 (código) · Migration **138** (versão)

## O que entra

| O que muda | Onde aparece |
|---|---|
| Marcador **`{coluna:ALIAS}`** e **`{coluna:NO.ALIAS}`** — o valor de uma coluna do resultado (1 linha) do SQL ligado logo antes do e-mail | Corpo e assunto do nó de e-mail; modelos do Admin |
| Opção **"Coluna de um SQL: informar alias…"** no seletor de marcadores | Etapas › nó de e-mail · Admin › Comunicação › E-mail › Modelos |
| Prévia mostra o nome da coluna (`‹total›`); painel avisa marcador que não vai resolver | Painel do nó de e-mail |
| Log da task explica todo `{coluna:…}` que não resolve | Log da etapa de e-mail |

`{tabela}`, `{tabela:NO}`, o escalar lido pela Decisão `valor_sql` e o
`PLACEHOLDER_RE` **não mudam**.

## Ordem do deploy

1. **Migration 138** na etapa **6c** do `deploy.sh` — só registra a versão
   (2.5.3 → **2.6.0**); idempotente.
2. **`dags/`** — e **reiniciar o worker**. `dags/utils/` é cacheado: sem o
   restart a etapa fica verde com o código antigo e o `{coluna:…}` chega
   **literal** no e-mail.
3. **`dist/`**.
4. `config/` → **n**.
5. **Nada a republicar**: o resultado do SQL já é publicado desde a 2.x
   (`{tabela}`). Pipeline com nó SQL que **nunca** foi republicado depois da
   entrega do `{tabela}` precisa ser — sem isso não há resultado para ler, e o
   log diz "nenhum nó SQL imediatamente a montante".

## Conferência (smoke)

a) **Tela:** no nó de e-mail ligado a um SQL, escolher *Coluna de um SQL*,
   digitar `total`, **Inserir** — entra `{coluna:total}` no cursor; a prévia
   mostra `‹total›`.
b) **Worker reiniciado:** numa corrida com `{coluna:…}` no corpo, o log da
   etapa de e-mail tem `[EMAIL] coluna <NO>.<alias> resolvida`. Sem essa linha,
   o worker está com código em cache.
c) **E-mail recebido** (destinatário interno): os valores no lugar dos
   marcadores, nenhum `{coluna:…}` literal.
d) **2 linhas** (`SELECT … UNION ALL SELECT …`): marcador literal e log
   `trouxe 2 linha(s) (esperado: 1)`.
e) **Dois SQL ligados:** `{coluna:total}` literal com log pedindo
   `{coluna:NOME_DO_NO.total}`; a forma longa resolve.
f) **Regressão:** fluxo com `{tabela}` inalterado; Decisão `valor_sql`
   roteando igual.

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| `{coluna:x}` literal e **nenhuma** linha `[EMAIL] coluna` no log | worker sem restart |
| literal com `trouxe N linha(s) (esperado: 1)` | o SELECT não devolve exatamente uma linha |
| literal com `não tem a coluna x (colunas: …)` | alias diferente do `AS` (caixa conta) ou coluna além da 15ª |
| literal com `N nós SQL a montante` | usar `{coluna:NOME_DO_NO.x}` |
| literal com `nenhum nó SQL imediatamente a montante` | e-mail não ligado direto no SQL (Decisão no meio) ou pipeline não republicado |
| literal com `a montante existem: …` (forma `{coluna:NO.x}`) | nome do nó diferente dos listados no log, pipeline não republicado, ou o SQL falhou/foi pulado nesta corrida (sem resultado publicado) |
| valor terminando em `…` | célula acima de 200 caracteres (corte do resultado) |

## Reversão

Reverter o merge da PR #472 e reiniciar o worker; o `dist/` anterior volta com
o deploy. A migration 138 só registra a versão — não há dado a desfazer.
Marcadores `{coluna:…}` já gravados em nós/modelos passam a sair literais.
O rótulo da versão **não volta sozinho**: `app_version` continua 2.6.0 e
`app_release_name` continua "E-mail: valor de cada coluna do SQL". Ajuste em
Admin › Versões, se a reversão for definitiva.
