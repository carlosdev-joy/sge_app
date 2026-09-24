# Spec: ferramenta de consulta a banco para os agentes

**Data:** 2026-09-23
**Status:** ✅ ENTREGUE — C1 (#444), C2 (#445), C3 (manual, release note `docs/release-notes/agentes-banco.md`,
smoke). Histórico da spec: 1ª e 2ª revisões (análise de texto) reprovadas em escrita → **3ª abordagem: plano do SQL
Server**, que bloqueou toda escrita nas provas no DEV; 2 rodadas dela ajustaram alcance e sigilo. Limite aceito pelo
usuário na C1 (24/09): uma única célula `(MAX)` gigante entra inteira na memória da API antes de ser reduzida.
**Base:** `docs/spec-agentes-admin.md` (agentes criados pela tela, entregue #432–#440) · conexões de `dbo.etl_conexao`
(migration 054, Admin › Conexões) · `api/services/conn_native.py`
**Pedido do usuário (23/09, depois da implantação):** "nas ferramentas permitir consultas em banco, com base nas
conexões existentes no Orquestra; o usuário seleciona o servidor e o banco, podendo ser múltiplos servidores e
múltiplos bancos" — a ferramenta lista as conexões **já cadastradas** no próprio Orquestra.

---

## 1. Decisões do usuário (23/09)

| # | Decisão |
|---|---|
| C1 | O agente consulta os bancos das **conexões já cadastradas** (`etl_conexao`, as nativas SQL Server). Na criação/edição, o admin escolhe **um ou mais servidores** e, em cada um, **um ou mais bancos** |
| C2 | **Dados pessoais: escolha por agente** — interruptor *Mascarar dados pessoais* no cadastro |
| C3 | **Acesso por perfil permitido** com a ferramenta de banco. Exceção à D3 **só para ela**: `dsjob`, `isx_extrair` e `dsx_consulta` continuam só por concessão manual |
| C4 | **Até 100 linhas** por consulta |
| C5 | **O SQL é sempre mostrado.** O agente apresenta a consulta que usou e, quando fizer sentido, **sugere a consulta** para o usuário rodar. No chat, SQL numa estrutura própria: **realce de sintaxe**, fonte monoespaçada, **Copiar** |
| C6 | **"Quem faz as queries é o agente; ele pode usar CTE para consultar; não pode fazer escrita, mesmo que o login tenha permissão; sempre gera query para o usuário, nunca ação de escrita."** A garantia **não depende do login**: vem do Orquestra **e do próprio SQL Server** (plano de execução, §4). Login com escrita só gera aviso |

Decisões técnicas tomadas junto:

- **T1 — Duas ferramentas:**
  - `banco_estrutura`: tabelas/views de um banco liberado, com filtro por nome, ou as colunas de uma delas;
  - `banco_consulta`: um `SELECT`.
- **T2 — Só SELECT em três camadas** (§4):
  1. análise léxica com **lista positiva**;
  2. **plano do SQL Server** (`SHOWPLAN_XML`): uma instrução, do tipo SELECT, só nos bancos liberados;
  3. transação sempre desfeita.

  Nenhum embrulho: a consulta roda como veio.
- **T3 — Nada de conexão nova.** Usa `abrir_conexao_nativa(conn_id, banco)`: a credencial cifrada da conexão, com
  o banco fixo na sessão. **Sem fallback**: se a conexão não é nativa, a ferramenta responde "indisponível". Nunca
  usa a credencial do próprio Orquestra.
- **T4 — Migration 122:** `bancos_json` e `mascarar_dados` em `etl_agente`.
- **T5 — Sem dependência nova no front.** O realce de SQL é um tokenizador próprio, testável no harness Node.
- **T6 — O DataStage não ganha a ferramenta.** Ele mantém a lista do `CATALOGO`. Os agentes da tela passam a usar
  uma allowlist própria (§7).

---

## 2. O que muda para o usuário

**Admin › Agentes › Novo/Editar agente:**

- *Ferramentas* ganha **Consulta a banco**. Marcada, aparece **Bancos liberados**:
  - as conexões **nativas SQL Server** cadastradas, por endpoint próprio (§8): nome e servidor, **sem login nem
    senha**;
  - ao escolher uma conexão, os bancos que ela alcança, com checkboxes;
  - vários servidores e vários bancos; pelo menos um par.
- Ao salvar, o Orquestra confere cada par **novo ou alterado**: a conexão abre, o banco existe e o login tem
  `SHOWPLAN`. Pares que não mudaram não são reconferidos, e um servidor fora do ar não impede renomear o agente.
- **Aviso de login com escrita:** se o login da conexão puder gravar naquele banco (`db_owner`, `db_datawriter`,
  `sysadmin`, permissão de INSERT/UPDATE/DELETE/EXECUTE), o formulário mostra:
  - *"o login desta conexão pode gravar — o agente só executa SELECT, mas uma conexão só de leitura é a proteção
    extra recomendada"*;
  - e *"este login também alcança: X, Y"* quando ele enxerga outros bancos do servidor além dos escolhidos.
- **Mascarar dados pessoais**, ligado por padrão.
- **Por perfil** fica disponível com a ferramenta de banco, mas indisponível com `dsjob`, `isx_extrair` ou
  `dsx_consulta`, como hoje.

**Tela do agente (`/agentes`):**

- Abaixo da resposta, **Consultas executadas**: cada SQL que rodou, **exatamente como rodou**, com o banco, as linhas
  devolvidas, o tempo e o **Copiar**.
- Todo bloco ```` ```sql ```` na resposta, inclusive as consultas **sugeridas**, aparece como **Consulta SQL**:
  - realce de palavras-chave, textos, números e comentários, nos temas claro e escuro;
  - rolagem horizontal;
  - **Copiar**.
- A linha *Consultei:* mostra *banco `<conexão>/<banco>`*.

```
┌────────────────────────────────────────────────────────────────────┐
│ Os 3 planos com mais adesões em 2026 são …                         │
│                                                                    │
│ ┌ Consulta SQL ──────────────────────────────── kiprev_prod/PREV ┐ │
│ │ SELECT TOP 3 p.nome, COUNT(*) AS adesoes              [Copiar] │ │
│ │ FROM dbo.adesao a JOIN dbo.plano p ON p.id = a.plano_id        │ │
│ │ WHERE a.data >= '2026-01-01' GROUP BY p.nome ORDER BY 2 DESC   │ │
│ └────────────────────────────────────────── 3 linhas · 0,8 s ───┘ │
│ Consultei: estrutura do banco › banco kiprev_prod/PREV             │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Modelo de dados — migration 122

```sql
IF COL_LENGTH('dbo.etl_agente', 'bancos_json') IS NULL
    ALTER TABLE dbo.etl_agente ADD bancos_json NVARCHAR(MAX) NULL;   -- [{"conexao": "kiprev_prod", "banco": "PREV"}, …]
IF COL_LENGTH('dbo.etl_agente', 'mascarar_dados') IS NULL
    ALTER TABLE dbo.etl_agente ADD mascarar_dados BIT NOT NULL CONSTRAINT DF_etl_agente_mascarar DEFAULT 1;
```

- `bancos_json` só é válido com a ferramenta de banco, e ela exige pelo menos um par. O par é guardado pelo
  `conn_id`, não pelo host.
- **Na execução**, um par fora do cadastro, ou uma conexão removida ou não nativa, vira resposta de ferramenta
  *"indisponível"*. Nunca abre conexão, nunca dá 500.

---

## 4. Só SELECT (C6) — três camadas

A 2ª revisão provou no SQL Server que **análise de texto sozinha não garante "só SELECT"** em T-SQL:
- `SELECT 1DELETE FROM t SELECT 1COMMIT` apagou dados;
- `NEXT VALUE FOR` grava a sequence mesmo com rollback;
- `IF`/`WHILE`/`RAISERROR` começam instruções sem palavra proibida.

Por isso a garantia vem do **servidor**, e a análise de texto é a primeira barreira.

### 4.1 Camada 1 — análise léxica com lista POSITIVA (`agentes_sql.py`, antes de conectar)

**Tokens de verdade.**
- O analisador separa literais (`'…'`, `N'…'` com `''`), identificadores delimitados (`[…]` com `]]`, `"…"`),
  números, palavras e símbolos.
- Um **número colado a letras é recusado** (`1DELETE`, `1.DELETE`, `1e0DELETE`); só valem `1e5` e `0x…`.
- Comentários são recusados.

**Uma instrução.**
- Parênteses balanceados.
- Um `;` só é aceito no final (removido) ou logo antes de um `WITH` inicial (`;WITH cte …`, hábito comum).
- **No nível de fora**, só palavras de cláusula de consulta: `WITH` (CTE, só no início ou depois de `,`), `SELECT`,
  `DISTINCT`, `TOP`, `PERCENT`, `TIES`, `FROM`, `WHERE`, `GROUP BY`, `ROLLUP`, `CUBE`, `GROUPING SETS`, `HAVING`,
  `ORDER BY`, `ASC`, `DESC`, `OFFSET … ROWS FETCH NEXT … ROWS ONLY`, `JOIN`/`INNER`/`LEFT`/`RIGHT`/`FULL`/`OUTER`/
  `CROSS`/`APPLY`/`ON`, `UNION [ALL]`/`EXCEPT`/`INTERSECT`, `PIVOT`/`UNPIVOT`, `AS`, `AND`/`OR`/`NOT`, `IN`,
  `EXISTS`, `BETWEEN`, `LIKE … ESCAPE`, `IS NULL`, `ANY`/`SOME`/`ALL`, `CASE…WHEN…THEN…ELSE…END`,
  `OVER`/`PARTITION BY`/`ROWS`/`RANGE`, `WITHIN GROUP`, `AT TIME ZONE`, `TABLESAMPLE`, `COLLATE`, `TOP n WITH TIES`,
  `FETCH FIRST|NEXT`, `NULL`, `VALUES` (em `FROM (VALUES …)`), as funções reservadas de uso comum (`COALESCE`,
  `NULLIF`, `CONVERT`, `TRY_CONVERT`, `CAST`, `TRY_CAST`, `CURRENT_TIMESTAMP`, `LEFT`/`RIGHT` como função), nomes
  de função, nomes de objeto e coluna.
- **O que é "palavra-chave":** as **palavras reservadas do T-SQL** (lista oficial da Microsoft, versionada no
  código). Uma palavra reservada fora da lista positiva recusa a consulta. Palavra não reservada é nome (coluna,
  apelido, função). **Dentro de parênteses** vale a mesma lista, mais o que só existe ali: tipos de `CAST`/`CONVERT`
  e a moldura de janela `ROWS BETWEEN … PRECEDING/FOLLOWING/CURRENT ROW`. Um `SELECT` dentro de parênteses abre uma
  subconsulta e segue as mesmas regras.
- Um novo `SELECT` só vale **dentro de parênteses** ou logo depois de `UNION`/`EXCEPT`/`INTERSECT`.
- **Qualquer outra palavra no nível de fora recusa a consulta**: `IF`, `WHILE`, `DECLARE`, `SET`, `EXEC`,
  `RAISERROR`, `PRINT`, `GOTO`, rótulo, `INSERT`… A lista positiva torna a lista negativa desnecessária.
- A 1ª instrução é `SELECT` ou `WITH … AS ( … ) SELECT`. **CTE é permitida** (C6).

**Recusados em qualquer posição do código:**
- `INTO` (o `SELECT … INTO`);
- `NEXT VALUE FOR`;
- dicas de tabela `WITH ( … )` depois de um objeto: `NOLOCK`, `TABLOCKX`, `UPDLOCK`, `XLOCK`, `HOLDLOCK`… Os locks
  ficam com o servidor, na leitura confirmada padrão;
- `OPTION ( … )`;
- `FOR XML`/`FOR JSON` (a saída não cabe no formato de linhas);
- `@@…`;
- funções que revelam o ambiente **quando chamadas** (nome seguido de `(`; o mesmo nome como coluna, como
  `user_id`, passa): `SUSER_NAME`/`SUSER_SNAME`/`SUSER_ID`/`SUSER_SID`, `USER_NAME`/`USER_ID`, `ORIGINAL_LOGIN`,
  `HOST_NAME`, `HOST_ID`, `APP_NAME`, `CONNECTIONPROPERTY`, `SERVERPROPERTY`, `LOGINPROPERTY`, `IS_SRVROLEMEMBER`,
  `IS_MEMBER`, `HAS_PERMS_BY_NAME`, `HAS_DBACCESS`, `DATABASEPROPERTYEX`, `DB_NAME`/`DB_ID` com argumento, e
  `OBJECT_NAME`/`OBJECT_SCHEMA_NAME`/`OBJECT_ID` **com mais de um argumento ou com nome de 3 partes em literal**
  (leem nomes de outro banco sem aparecer no plano). As reservadas sem parênteses `SYSTEM_USER`, `SESSION_USER`,
  `CURRENT_USER` e `USER` são recusadas sempre — já ficam fora da lista positiva;
- as chaves ODBC `{fn …}`, `{d …}`, `{t …}`: recusadas;
- **objetos do esquema `sys` e `INFORMATION_SCHEMA`: lista POSITIVA.** Só as visões de catálogo **do próprio
  banco**: `INFORMATION_SCHEMA.TABLES/COLUMNS/VIEWS/ROUTINES/KEY_COLUMN_USAGE/TABLE_CONSTRAINTS`, `sys.tables`,
  `sys.views`, `sys.columns`, `sys.schemas`, `sys.objects`, `sys.indexes`, `sys.index_columns`, `sys.types`,
  `sys.foreign_keys`, `sys.foreign_key_columns`, `sys.extended_properties`. **Qualquer outro `sys.…` é recusado**:
  `sys.sysprocesses`, `sys.login_token`, `sys.user_token`, `sys.dm_*`, `sys.server_*`, `sys.databases`, logins…
  A revisão provou que `sys.login_token` e `sys.sysprocesses` devolvem o login e passam pelo plano. A regra vale para
  **todas as grafias** do esquema: `sys.x`, `[sys].[x]`, `"sys"."x"`, `sys . x`;
- **visões de compatibilidade sem prefixo:** qualquer objeto de **uma parte** cujo nome comece com `sys`
  (`sysprocesses`, `syscacheobjects`, `sysusers`, `syslockinfo`, `sysobjects`…) é recusado. A revisão provou que
  `SELECT loginame FROM sysprocesses` devolve o login, e que `syscacheobjects` devolve o texto de consultas de outras
  sessões;
- **tabelas temporárias `#…`/`##…`**: uma `##` global de outra sessão foi lida na revisão;
- **literal com cara de credencial** (a regra de `prompt_com_segredo` aplicada aos literais): é recusado, nunca
  mascarado, para o SQL gravado ser sempre o executado (§5);
- `OPENROWSET`/`OPENQUERY`/`OPENDATASOURCE`/`OPENXML`;
- identificador `xp_…`/`sp_…`.

**Nome de objeto de 3 ou 4 partes, em qualquer posição** (depois de `FROM`/`JOIN`/`APPLY`/`,` de lista de tabelas, e
em chamada de função `a.b.c(`), em todas as grafias: colchetes, aspas, espaços, `..`. Coluna qualificada
(`alias.coluna`) não é objeto e passa.

O resultado da camada 1 é uma lista de **tokens**, e não um texto "limpo". As camadas seguintes rodam **o texto
original**, sem reescrita.

### 4.2 Camada 2 — o plano do SQL Server (antes de executar)

Na conexão já aberta **no banco liberado**:
1. `SET SHOWPLAN_XML ON`;
2. executa a consulta **inteira**: o servidor **compila e devolve o plano sem executar nada**;
3. `SET SHOWPLAN_XML OFF`.

O Orquestra lê o XML e exige:
- **Uma instrução no nível de fora.** O elemento `Statements` do lote tem **exatamente um filho**, e ele é
  `StmtSimple` com `StatementType` = `SELECT` ou `SELECT WITHOUT QUERY` (o `SELECT GETDATE()`). `StmtCond`
  (`IF`/`WHILE`), um segundo `StmtSimple` ou qualquer outro tipo recusam a consulta: `DELETE`, `COMMIT TRANSACTION`,
  `SELECT INTO`, `EXECUTE PROC`, `EXECUTE STRING`, `ASSIGN`, `RAISERROR`, `PRINT`, `WAITFOR`, `DBCC`…
- **O corpo de funções** que o plano expande, como UDF não inline ou TVF de várias instruções, com seus `SELECT`,
  `INSERT` na variável de retorno e `RETURN`, **não conta** para a regra acima. É conferido só quanto ao alcance.
- **Alcance.** Em todo `Object`, `Database` ∈ **bancos liberados daquela conexão**, **sem exceção para tempdb**.
  Spool, sort e janela nem geram `Object`.
- **`Object` sem `Database` é recusado**, com três exceções nomeadas:
  - as funções de tabela embutidas `STRING_SPLIT` e `OPENJSON` (e `OPENJSON_*`);
  - a variável de retorno (`Table` começando com `@`) de uma TVF de várias instruções;
  - objetos dentro do corpo de uma função que o plano já mostrou pertencer a um banco liberado.

  Todo o resto sem `Database` — as TVFs de sistema por trás de `sysprocesses`, `syscacheobjects` e `sys.login_token`
  — recusa a consulta. É a segunda barreira do vazamento que a camada 1 também fecha. As visões de catálogo que o SQL Server resolve em
  `[mssqlsystemresource]` também são aceitas, porque a camada 1 já restringe quais visões `sys` passam. Como o plano
  vem com synonyms e views resolvidos, isso fecha o alcance a outro banco do mesmo servidor.
- **Nada remoto.** Qualquer operador `Remote*` (`Remote Query`, `Remote Scan`…) ou atributo `RemoteSource` recusa a
  consulta. A revisão provou que um synonym para linked server aparece **só** como `Remote Query`, sem nenhum `Object`.
- **Nada de sequence.** Qualquer `Intrinsic FunctionName="GetSequenceNext"` recusa. O `NEXT VALUE FOR` não aparece
  como operador; `Sequence Project` é o operador de `ROW_NUMBER`/`LAG` e **não** é recusado.
- **Nenhum operador de escrita** em objeto permanente (`Insert`/`Update`/`Delete`/`Merge` fora do corpo de função).

**Sem permissão de `SHOWPLAN`**, a conexão é **indisponível para os agentes**: o admin vê isso ao liberar o banco, e
a ferramenta responde *"conexão indisponível"*. A consulta nunca roda sem a conferência do plano.

**Provado na revisão:**
- `SET SHOWPLAN_XML ON` precisa ser a **única** instrução do lote (erro 1067), por isso são três `execute`
  separados;
- com ele ligado, **nada executa**: DML, DDL, `SET` e `EXEC` de string deixaram o estado intacto;
- a compilação de uma consulta pesada levou 0,11 s;
- sem a permissão, o erro é o 262, e `HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'SHOWPLAN')` serve para a checagem
  ao salvar.

### 4.3 Camada 3 — execução

- `conn.timeout = min(30, orçamento restante)` é definido **antes de criar qualquer cursor**, e vale também para a
  compilação da camada 2. O cursor devolvido por `abrir_conexao_nativa` é descartado: a 2ª revisão provou que ele não
  herda o timeout.
- `BEGIN TRAN` → a consulta, **como veio** → `fetchmany(101)` → **`ROLLBACK` sempre**, inclusive em erro ou
  cancelamento, e depois fecha a conexão. Vão **100** linhas; a 101ª só diz *"havia mais"*.
- Isolamento padrão (`READ COMMITTED`): sem leitura suja, e o dado mostrado é o confirmado.
- Mais de um conjunto de resultado é impossível: a camada 2 garante uma instrução no nível de fora, e `IF`/`WHILE`
  são recusados.

### 4.4 O que continua fora do alcance (declarado)

- **Linked server dentro de uma função** já existente: se a função lê um servidor remoto por dentro, o plano pode não
  expor isso como operador remoto. Recomendação: conferir, no smoke em produção, se os bancos liberados têm synonyms,
  views ou funções com `RemoteSource`.

- **Funções já existentes no banco** (UDF, CLR) são chamadas pelo SELECT com o que elas fazem por dentro. Uma UDF
  T-SQL não pode gravar. Uma CLR ou uma que chame `xp_` pode. O plano mostra a chamada, mas não o efeito.
  Recomendação: login sem `EXECUTE` em CLR.
- **Login com escrita** gera **aviso** no admin (C6), mas não bloqueia: pela 2ª camada, nada além do SELECT roda.

### 4.5 Estrutura e erros

`banco_estrutura {"conexao", "banco", "filtro"?, "tabela"?}`:
- lê `INFORMATION_SCHEMA.TABLES`/`COLUMNS` com SQL **fixo e parametrizado**, do próprio Orquestra, sem passar
  pelo modelo;
- `filtro` é um `LIKE` parametrizado sobre o nome;
- teto de 300 itens, com *"use `filtro` para ver o resto"* quando passa.

**Erros:** ao modelo vão só mensagens **fixas**:
- *conexão indisponível*;
- *banco sem acesso*;
- *tabela ou coluna inexistente: `<nome>`*;
- *consulta recusada: `<regra>`*, dizendo qual regra da camada 1 ou 2;
- *sintaxe inválida perto de `<trecho>`*;
- *tempo esgotado*.

Nunca vão host, porta, login ou texto do driver. Só **inexistente** e **sem acesso** viram aprendizado permanente;
recusa e sintaxe não (são do modelo).

## 5. Dados que vão à IA

- **Formato:** texto compacto, com cabeçalho de colunas e linhas separadas por tabulação. Célula até 200 caracteres,
  bloco até 15.000; o que passar vira *"… (N linhas não mostradas)"*.
- **Credenciais nas LINHAS:** o mascaramento de credencial vale por **célula**, não por linha. Uma célula com cara
  de segredo vira `••••`, e as outras ficam.
- **O SQL não passa pelo `redigir()` de linha** (a 1ª revisão mostrou que `u.token_expira` apagava o resto da
  consulta). As **duas** gravações de artefato (`agentes.py`, `args` via `redigir_estrutura`) abrem exceção para
  `banco_consulta.sql`. O SQL fica **idêntico** ao que rodou — o que aparece em *Consultas executadas* e no
  **Copiar**. Um literal com cara de credencial no SQL escrito pelo modelo é **recusado** pela camada 1, e não
  mascarado: assim o SQL gravado nunca precisa diferir do executado.
- **Com *Mascarar dados pessoais*** (C2), sobre os **dados vindos do banco** e as **mensagens de erro**, antes de ir
  à IA e antes de gravar qualquer coisa:
  - **por valor, em qualquer coluna:**
    - sequência de 11 dígitos, com ou sem pontuação, que passe no **dígito verificador de CPF**;
    - de 14 dígitos que passe no de **CNPJ**;
    - e-mail;
    - telefone **com formatação** (`(11) 91234-5678`, `+55 …`). Números soltos não, para não pegar ids e datas;
  - **por nome de coluna (substring, sem diferenciar maiúsculas):** `cpf`, `cnpj`, `email`, `e_mail`, `telefone`,
    `fone`, `celular`, `whatsapp`, `documento`. Pega `NUM_CPF_CNPJ` e `nu_documento`;
  - **limites declarados:**
    - apelido escolhido pelo modelo (`nr_cpf AS x`) só é pego se o valor passar no dígito verificador;
    - nomes de pessoa não são detectados.
  - **Não se aplica** ao que o próprio usuário digitou: a pergunta e os literais do SQL mostrado. O **Copiar** copia
    a consulta verdadeira.
- **O que fica gravado:**
  - em `artefatos_json`: o SQL executado, a conexão, o banco, as linhas devolvidas e o tempo — **nunca** as linhas;
  - em `etl_agente_mensagem`: a resposta do modelo, que só viu dados já mascarados;
  - na **evidência de aprendizado**: a mensagem fixa de erro, nunca a do driver.
- **Propostas:** a consulta a banco não é "leitura de job" e não serve de evidência de proposta.

---

## 6. Prompt (blocos fixos)

- **Bloco 3 (protocolo), com a ferramenta de banco:**
  - `banco_estrutura {"conexao", "banco", "filtro"?, "tabela"?}` e `banco_consulta {"conexao", "banco", "sql"}`;
  - os **pares liberados** por nome (`kiprev_prod/PREV`), nunca host ou login;
  - as regras: uma instrução `SELECT` (ou `WITH … SELECT`), até 100 linhas, sem nome de 3 partes; ver a estrutura
    antes de consultar tabela desconhecida.
- **Bloco 4 (regras), por agente:**
  - o *"NUNCA altera o DataStage"* só entra quando o agente tem ferramenta de DataStage;
  - com a ferramenta de banco entram:
    - **"Você só consulta: nunca executa nem sugere escrita no banco (INSERT, UPDATE, DELETE, DDL, procedure) —
      mesmo que o usuário peça. Para o que ele quiser saber, gere a consulta SELECT."** (C6)
    - **"Sempre mostre ao usuário, num bloco ```` ```sql ````, a consulta que você usou; quando o usuário puder
      aprofundar sozinho, sugira a consulta pronta para ele rodar."** (C5)
    - **"Nunca apresente como dado o que não veio de uma consulta."**
- **Prévia do admin:** a *Parte fixa montada pelo Orquestra* mostra os pares do agente.

---

## 7. Ferramentas, allowlists e acesso

- **Allowlists:**
  - `CATALOGO["datastage"]["ferramentas"]` continua `FERRAMENTAS_DATASTAGE`. O DataStage não muda;
  - nova `FERRAMENTAS_BANCO = ("banco_estrutura", "banco_consulta")`;
  - nova `FERRAMENTAS_TELA = FERRAMENTAS_DATASTAGE + FERRAMENTAS_BANCO`, a allowlist dos agentes criados pela tela.
    `_normalizar_ferramentas`, a validação da criação e `partes_fixas` passam a usá-la.
- **Recusa fora do conjunto do agente:** o teste passa a ser sobre `FERRAMENTAS_TELA`. Um agente sem a ferramenta
  que peça `banco_consulta` é recusado antes do despachante. O filtro do início de `conversar()` (hoje
  `FERRAMENTAS_DATASTAGE`) passa a usar `FERRAMENTAS_TELA`. Sem isso, um agente só de banco cairia em "só conversa".
- **Guarda e aprendizados:** as duas entram em `FERRAMENTAS_COM_GUARDA`, `_ARGS_RELEVANTES` (conexão, banco,
  sql/tabela) e nas categorias de falha.
- **Acesso (C3):** as de banco **não** entram em `FERRAMENTAS_SERVIDOR`, então *por perfil* é permitido com elas.
  `consulta` continua proibido, e a `tela_agentes` continua exigida.

---

## 8. Endpoints novos (admin)

```
GET /agentes/admin/conexoes                              → nativas SQL Server: conn_id, host, descrição (sem login/senha)
GET /agentes/admin/conexoes/{conn_id}/bancos             → bancos que ela alcança (HAS_DBACCESS) + aviso de escrita por banco
```

Os dois exigem admin. **Não reaproveitam** as rotas existentes:
- `conn_list` devolve o login;
- `/copias/conexoes` mistura conexões do Airflow que não são nativas;
- `/jobs/databases` com uma conexão não nativa lista os bancos do **servidor do Orquestra**.

---

## 9. Entregas

| Fase | O quê | Deploy |
|---|---|---|
| **C1** ✅ #444 | migration 122; `agentes_sql.py` (as três camadas da §4); as duas ferramentas; mascaramento (§5); prompt (§6); allowlists e acesso (§7); endpoints (§8), inclusive a checagem de `SHOWPLAN`; validação dos pares alterados | 6c `s` (122) + API |
| **C2** ✅ #445 | Admin: *Consulta a banco*, *Bancos liberados*, avisos de login, *Mascarar dados pessoais*; chat: **Consulta SQL** (realce + Copiar; `markdownLlm` guarda a linguagem do bloco), *Consultas executadas* | `dist/` |
| **C3** ✅ | manual, release note (`docs/release-notes/agentes-banco.md`), smoke; migration **123**: registra a versão da entrega em Admin › Versões (o número do cabeçalho sobe no deploy) | 6c `s` (123) |

## 10. Critérios de aceite

1. O agente só consulta os pares liberados. Nome de 3/4 partes no texto é recusado sem conectar. Synonym ou view
   existente que aponte para outro banco é recusada pelo plano (camada 2).
2. **Só `SELECT` roda, mesmo com login de escrita.** A matriz de ataques das três revisões é recusada — pela camada
   1 sem conectar, ou pela camada 2 sem executar:
   - `1DELETE`/`1COMMIT`;
   - `IF`/`WHILE`/`RAISERROR`/`PRINT`;
   - `NEXT VALUE FOR`;
   - dicas de lock;
   - funções de login e servidor;
   - duas instruções;
   - 3/4 partes em qualquer posição;
   - synonym ou view para outro banco (camada 2);
   - synonym para linked server (`Remote Query`);
   - `##` de outra sessão;
   - `sys.login_token` e `sys.sysprocesses`, com e sem prefixo, em todas as grafias; `syscacheobjects`;
   - `OBJECT_NAME(id, banco)` e `DATABASEPROPERTYEX('outro', …)`.

   Passam: `WITH … SELECT`, `;WITH`, `ORDER BY`, `OFFSET … FETCH NEXT … ONLY`, `TOP … WITH TIES`, `COUNT(*)`, joins,
   `UNION`, `STRING_AGG … WITHIN GROUP`, janela (`ROW_NUMBER`, `LAG`), `SELECT GETDATE()`, UDF do próprio banco,
   `COALESCE`, `NULLIF`, `CONVERT(…, 103)`, `ELSE NULL`, `FROM (VALUES …)`, `STRING_SPLIT`, `OPENJSON`, coluna
   chamada `user_id` ou `host_name`, `INFORMATION_SCHEMA`/`sys.tables`, e literais com `;`, `DELETE`, `--` ou
   `MERGE`.
   **Esta matriz vira teste automatizado contra o SQL Server do DEV**, rodado a cada mudança do analisador. Os testes rodam no SQL Server do DEV com um login **de escrita**, e nada se
   altera.
3. No máximo 100 linhas e 30 s por consulta. A pergunta continua limitada a 240 s.
4. Com *Mascarar dados pessoais*, CPF e CNPJ válidos, e-mail e telefone formatado **vindos do banco consultado** (e
   das mensagens de erro) não chegam à IA nem ficam gravados. Os limites declarados na §5 valem.
5. O SQL executado aparece **idêntico** ao que rodou, com realce e **Copiar**, e fica em `artefatos_json`. As linhas
   não ficam.
6. Com a ferramenta de banco o agente pode ser *por perfil*; com `dsjob`/`isx_extrair`/`dsx_consulta`, não.
7. Conexão ou banco removidos, conexão não nativa ou login sem `SHOWPLAN` dão *"indisponível"*, nunca 500 e nunca
   a credencial do Orquestra. Host e login nunca chegam à IA: as funções de ambiente são recusadas e os erros são
   fixos.
8. O DataStage e os agentes existentes não mudam: o prompt do DataStage fica byte a byte igual.

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Escrita no banco | camada 1 (lista positiva) + camada 2 (plano do servidor: uma instrução, do tipo SELECT) + camada 3 (rollback sempre); UDF/CLR existente declarada na §4.4 |
| Consulta pesada em produção | `fetchmany(101)`, 30 s com cancelamento no servidor, no máximo 4 ferramentas por pergunta |
| Dado pessoal na IA | interruptor por agente, ligado por padrão; dígito verificador + nome de coluna; limites declarados |
| Alcançar outro banco | 3/4 partes e `USE` recusados; banco fixo na sessão; aviso de alcance do login |
| Credencial exposta | a IA e a tela veem só `conexao/banco`; erros fixos; sem fallback |
| O analisador errar | a camada 2 não depende dele; matriz de ataques das duas revisões testada no SQL Server do DEV com login de escrita |
| Login sem `SHOWPLAN` | a conexão fica indisponível para os agentes, com aviso no admin — nunca roda sem o plano |
