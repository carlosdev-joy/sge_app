# 🗄️ Agentes que consultam banco — só SELECT, com o SQL sempre à vista

**Compatibilidade:** a mesma dos agentes da tela (`docs/release-notes/agentes-admin.md`). Nos bancos consultados, as conexões **nativas SQL Server** já cadastradas em *Conexões de Dados*, com login que tenha **SHOWPLAN**
**Migrations:** **122** (`etl_agente.bancos_json` e `mascarar_dados`) e **123** (registra a versão desta entrega em Admin › Versões — o número do cabeçalho sobe sozinho) — etapa 6c, responder **s**. Idempotentes
**Spec:** `docs/spec-agentes-ferramenta-banco.md`
**Manual:** `docs/MANUAL_USUARIO.md` §3.12 (usar), §4.11 (administrar), §4.6 (deploy), §5 (FAQ)
**PRs:** #443 (spec) · #444 C1 (backend) · #445 C2 (tela) · C3 (esta nota, manual, smoke)

---

## 📋 Resumo

Os agentes criados pela tela passam a **consultar bancos**. O administrador escolhe, entre as conexões
já cadastradas no Orquestra, **quais servidores e quais bancos** cada agente enxerga. A partir daí, o
agente responde perguntas sobre os dados **consultando de verdade** e **mostrando o SQL que usou**. Quando
fizer sentido, ele também **sugere a consulta** para o usuário rodar sozinho.

A regra do usuário (C6) é a que manda: **o agente só executa SELECT — nunca escreve, mesmo que o login
da conexão possa gravar e mesmo que o usuário peça**. Para o que o usuário quiser saber, ele gera a
consulta.

```
┌────────────────────────────────────────────────────────────────────┐
│ Os 3 planos com mais adesões em 2026 são … Usei esta consulta:     │
│ ┌ Consulta SQL ─────────────────────────────────────── [Copiar] ┐ │
│ │ SELECT TOP 3 p.nome, COUNT(*) AS adesoes                        │ │
│ │ FROM dbo.adesao a JOIN dbo.plano p ON p.id = a.plano_id          │ │
│ │ WHERE a.data >= '2026-01-01' GROUP BY p.nome ORDER BY 2 DESC     │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│ ▾ Consulta executada (1)                                           │
│ ┌ Consulta SQL  dw_prod/PREV ────────────────────────── [Copiar] ┐ │
│ │ SELECT TOP 3 p.nome, COUNT(*) AS adesoes …                       │ │
│ └─────────────────────────────────────────────── 3 linhas · 812 ms ┘ │
│ Consultei: estrutura do banco dw_prod/PREV › banco dw_prod/PREV    │
└────────────────────────────────────────────────────────────────────┘
```

O bloco no meio da resposta é o que o **agente escreveu** (inclusive consultas sugeridas). Em
**Consultas executadas** (fechado por padrão, clique para abrir) está o SQL **exatamente como rodou**, com
o banco, as linhas e o tempo.

> **Impacto para os usuários:** perguntas sobre os dados viram resposta **com a consulta junto**, em
> bloco com realce e **Copiar**. Dá para conferir, reaproveitar e aprofundar sem pedir a ninguém.
>
> **Impacto para a operação:** cada consulta roda com **até 100 linhas** e **30 s**, cancelada no
> servidor se passar do tempo. São no máximo **4 consultas ao mesmo tempo** por processo da API e
> **4 ferramentas** por pergunta.
>
> **Impacto para a segurança:**
> - **Só SELECT**, garantido por **três camadas**, a do meio **pelo próprio SQL Server**;
> - os bancos são só os liberados;
> - host e login nunca chegam à IA;
> - dados pessoais mascarados por padrão.

---

## 🚚 O que entra

| Fase | PR | O quê |
|---|---|---|
| **Spec** | #443 | Decisões C1–C6 e as três camadas, com a matriz de ataques provada no SQL Server do DEV |
| **C1** | #444 | Migration 122. O módulo `agentes_sql.py` com as três camadas, o mascaramento e as mensagens fixas. As ferramentas `banco_estrutura` e `banco_consulta`, o prompt, o cadastro com os bancos liberados, os endpoints de conexões e bancos. A prova `scripts/prova_agentes_sql.py` |
| **C2** | #445 | **Tela:** *Consulta a banco*, *Bancos liberados*, avisos e *Mascarar dados pessoais* no cadastro. **Chat:** *Consulta SQL* (realce, Copiar), *Consultas executadas* e *Consultei:* com o banco |
| **C3** | esta | Manual, esta nota e o smoke |

---

## ⚙️ Como funciona

**Duas ferramentas.**
- `banco_estrutura`: lista as tabelas e views de um banco liberado, com filtro por nome, ou as colunas de
  uma delas. Usa SQL **fixo** do Orquestra, que não passa pela IA. O teto é de 300 itens.
- `banco_consulta`: roda **uma** consulta SELECT (ou `WITH … SELECT`, com CTE) escrita pelo agente e
  devolve até 100 linhas.

**Onde roda.** Na conexão **nativa** cadastrada (`etl_conexao`), com a senha cifrada dela, **já aberta no
banco liberado**. Se a conexão não é nativa, se foi removida ou se o login não abre, a resposta é
*"conexão indisponível"*. **Nunca** se usa a credencial do próprio Orquestra.

**Só SELECT: as três camadas** (§4 da spec).
1. **Texto, antes de conectar.** Só palavras de consulta (lista positiva). São recusados:
   - comentários, `;` no meio, número colado a palavra (`1DELETE`);
   - `INTO`, `NEXT VALUE FOR`, dicas de lock, `OPTION`, `FOR XML/JSON`;
   - variáveis e `@@`, tabelas `#`/`##`, `sp_`/`xp_`, `OPENROWSET` e parecidas;
   - nomes de 3 ou 4 partes;
   - funções que revelam login ou servidor, e as que leem metadado de outro banco;
   - `sys.*` fora de uma lista de catálogo do próprio banco, e visões antigas `sys…`;
   - literal com cara de credencial.
2. **Plano do SQL Server, antes de executar.** Com `SET SHOWPLAN_XML ON`, o servidor **compila e devolve
   o plano sem executar nada**. O Orquestra exige:
   - uma instrução só, do tipo SELECT;
   - nada remoto (linked server), nada de sequence;
   - todo objeto num banco **liberado**. Synonyms, views e funções chegam **já resolvidos** pelo
     servidor.
3. **Transação sempre desfeita.** `BEGIN TRAN` → a consulta → `ROLLBACK`, sempre, com o tempo máximo
   definido antes.

**Login com escrita** **não bloqueia**: nada além do SELECT roda. Mas o Orquestra **avisa**, porque uma conexão
só de leitura é a proteção extra recomendada:
- **no formulário**, ao abrir a conexão: escrita **no nível do banco** (`db_owner`, `db_datawriter`, GRANT de
  INSERT/UPDATE/DELETE/EXECUTE no banco) e `sysadmin`;
- **ao salvar**, para cada banco **novo**: também GRANT de escrita numa **tabela, view ou procedure** (aviso em
  mensagem na tela). Um banco que já estava liberado não é reconferido.

**O que a IA vê e o que fica gravado.**
- **Para a IA:**
  - as linhas vão em texto compacto, com célula de até 200 caracteres e bloco de até 15.000;
  - célula com cara de segredo vira `••••`;
  - erros viram **mensagens fixas**, sem host, login ou texto do driver.
- **Mascarar dados pessoais** (por agente, ligado por padrão):
  - CPF e CNPJ **válidos** (dígito verificador), e-mail e telefone formatado viram marcas;
  - colunas com `cpf`, `cnpj`, `email`, `telefone`, `fone`, `celular`, `whatsapp` ou `documento` no nome
    ficam inteiras `[oculto]`.
- **Gravado:** em `artefatos_json`, o SQL **executado** (intacto), a conexão, o banco, o número de linhas e
  o tempo — **nunca as linhas**.

**Acesso (C3).** Com a consulta a banco, o agente **pode** ser *por perfil*. Com `dsjob`, `isx_extrair` ou
`dsx_consulta` continua **só manual**, e o perfil `consulta` nunca recebe agente.

---

## 🔒 Como a segurança foi provada

- **Revisão da spec (5 rodadas) com provas no SQL Server do DEV.** A análise de texto **sozinha** falhou
  duas vezes: `SELECT 1DELETE FROM t SELECT 1COMMIT` **apagou dados** e `NEXT VALUE FOR` **gravou** a
  sequence mesmo com rollback. Por isso a garantia está no plano do servidor.
- **`scripts/prova_agentes_sql.py`** (DEV, `ORQ_PROVA_DEV=1`) roda com login `db_owner` e a **camada 1
  desligada**.
  - Os ataques que gravariam ou alcançariam outro banco são barrados, e o estado dos dois bancos fica
    **intacto** (contagem, checksum, sequence e objetos). Entre eles: `1DELETE`, `MERGE`, `SELECT INTO`,
    `IF`/`WHILE`, `EXEC` de string, synonym, view e UDF para outro banco, UDF com DMV, `sysprocesses`.
  - O script cria bancos e logins temporários e apaga tudo no fim.
  - **Rode a cada mudança em `api/services/agentes_sql.py`.**
- **Camada 2 contra 32 planos reais** capturados do SQL Server 2019 (`tests/fixtures/showplan/`).
- **Revisão adversarial de cada fase (2 rodadas):**
  - C1: 7 achados corrigidos — memória, `t.*`, metadado de outro banco, DMV em UDF, timeout, aviso de
    escrita por tabela e a tela antiga apagando os bancos;
  - C2: 2 achados corrigidos — o resgate do Copiar e a máscara escondida.

---

## 🚀 Deploy

| Passo | O quê |
|---|---|
| Antes | Conferir commits novos na branch `feat/agente-datastage-melhorias` e portar, como sempre |
| 6c | Migrations **122** e **123** → **s** (as 120 e 121 também, se ainda não foram). A 123 registra a versão desta entrega em **Admin › Versões** e o número do cabeçalho sobe (maior versão registrada, +1 no segundo número: 2.4.x → 2.5.0). Já registrada, não repete |
| `api/` | **sim** (C1) |
| `dags/` | não |
| `dist/` | **sim** (C2) |
| `.env` | nada novo |
| `config/` | **n** |
| Nos bancos consultados | Para cada banco que um agente vá consultar: login da conexão com **leitura** e `GRANT SHOWPLAN TO <usuário>` naquele banco. Sem SHOWPLAN, o banco aparece **indisponível** no formulário e o agente não o usa |

---

## ✅ Conferência pós-deploy

**Antes de responder `s` na 6c**, confira as versões já registradas — o número novo parte da maior
delas, e uma versão fora do padrão (sufixo como `-hotfix`, 5 partes, espaço) é ignorada no cálculo mas
não pelo cabeçalho:

```sql
SELECT versao, titulo, criado_em FROM dbo.etl_versao_ferramenta ORDER BY criado_em DESC;
```

Depois do deploy:

```sql
-- migration 122
SELECT COL_LENGTH('dbo.etl_agente', 'bancos_json'), COL_LENGTH('dbo.etl_agente', 'mascarar_dados');  -- dois valores
-- migration 123: a versão desta entrega (e o número que o cabeçalho mostra)
SELECT versao, titulo, criado_em FROM dbo.etl_versao_ferramenta WHERE titulo = N'Agentes pela tela e consulta a banco';
SELECT config_value FROM dbo.etl_app_config WHERE config_key = 'app_version';
-- agentes com consulta a banco e seus pares
SELECT agente_id, ferramentas_json, bancos_json, mascarar_dados, ativo FROM dbo.etl_agente
 WHERE bancos_json IS NOT NULL;
-- o que as consultas rodaram (SQL intacto, sem linhas)
SELECT TOP 20 m.criada_em, c.agente, m.artefatos_json
  FROM dbo.etl_agente_mensagem m JOIN dbo.etl_agente_conversa c ON c.conversa_id = m.conversa_id
 WHERE m.papel = 'assistant' AND m.artefatos_json LIKE '%banco_consulta%' ORDER BY m.id DESC;
```

No banco consultado, antes de liberar (§4.4 da spec), procure objetos que apontem para outro servidor —
views e synonyms a camada 2 já recusa; o que importa aqui são as **funções**:

```sql
-- objetos (funções, views, procedures) que referenciam outro servidor por nome de 4 partes
SELECT DISTINCT OBJECT_SCHEMA_NAME(d.referencing_id) AS esquema, OBJECT_NAME(d.referencing_id) AS objeto,
       d.referenced_server_name
  FROM sys.sql_expression_dependencies d WHERE d.referenced_server_name IS NOT NULL;
-- synonyms para outro servidor
SELECT name, base_object_name FROM sys.synonyms WHERE PARSENAME(base_object_name, 4) IS NOT NULL;
-- acesso ad hoc dentro de módulos
SELECT OBJECT_SCHEMA_NAME(object_id) AS esquema, OBJECT_NAME(object_id) AS objeto FROM sys.sql_modules
 WHERE definition LIKE '%OPENQUERY%' OR definition LIKE '%OPENROWSET%' OR definition LIKE '%OPENDATASOURCE%';
```

**Smoke automatizado:** `scripts/smoke_agentes.py`, com um usuário **admin**.
- Confere a API da C1, lista as conexões (sem login) e recusa a consulta a banco sem banco liberado.
- `SMOKE_CONEXAO=<conn_id>` lista os bancos com SHOWPLAN e o aviso de escrita no nível do banco.
- `SMOKE_AGENTE=<id>` de um agente com a consulta a banco faz duas perguntas.
  - A 1ª **falha** se a resposta não terminar em `ok` ou se houve consulta com erro e **nenhuma** rodou
    (conexão, SHOWPLAN, tempo). Confere que o que rodou foi SELECT e que as linhas não ficam no artefato.
    Um erro seguido de uma consulta que rodou (o modelo errou a coluna e corrigiu) só avisa.
  - A 2ª **pede** uma escrita e confere que ela não virou execução.
  - A prova de que **nada além de SELECT roda** é a do DEV (`scripts/prova_agentes_sql.py`), não o smoke.

O roteiro manual (itens **r**–**w**) cobre a tela e o mascaramento.

---

## ⚠️ Limites conhecidos (declarados)

- **Funções já existentes no banco.** Uma função não inline que chame `SUSER_SNAME()`/`HOST_NAME()` por
  dentro **não aparece no plano** (verificado no DEV). Chamada pelo agente, ela devolveria o que a
  função devolve. Uma CLR ou uma que chame `xp_` também tem efeito que o plano não mostra.
  Recomendação: login sem `EXECUTE` em CLR, e conferir as funções dos bancos liberados.
- **Linked server dentro de função** já existente pode não aparecer como operador remoto (a mesma
  recomendação).
- **Célula gigante.** A leitura para em 32 MB, mas **uma única** célula `VARBINARY(MAX)`/`NVARCHAR(MAX)`
  enorme entra inteira na memória da API antes de ser reduzida. **Aceito pelo usuário (24/09).**
- **Nomes de 3 partes** são recusados também como coluna (`a.b.c`): o agente usa apelido (`t.coluna`, `t.*`).
- **Mascaramento:** um apelido escolhido pelo modelo (`nr_cpf AS x`) só é pego se o valor passar no dígito
  verificador; **nomes de pessoa não são detectados**; o que o próprio usuário digita (a pergunta, os
  literais do SQL) não é mascarado.
- **Aviso de escrita** ao salvar custa uma varredura das permissões por objeto: 2,4 s num banco de 15 mil
  tabelas. Num banco bem maior, meça o tempo de salvar.
- O **DataStage** não ganha a ferramenta (T6). O prompt dele é o mesmo, byte a byte.

## 🔢 Número da versão

Até aqui, o número do cabeçalho (a **maior** versão em Admin › Versões) só mudava à mão, pela aba. A partir
desta entrega, a **migration de versão** faz isso no deploy: a 123 registra *"Agentes pela tela e consulta a
banco"* com o changelog e sincroniza `app_version`. O número é a maior versão já registrada com +1 no segundo
número; ele fica visível depois do deploy, e a aba continua servindo para corrigir o texto ou o número.
**Convenção para as próximas entregas:** uma migration `NNN_versao_<entrega>.sql` no mesmo formato (título
como chave, idempotente).

## 🧭 Próximos passos (backlog)

- Medir o salvar do cadastro num banco de produção muito grande (aviso de escrita).
- Se aparecer necessidade, um teto por célula no lado do servidor (exigiria reescrever a consulta, o que
  hoje é proibido pela spec).
