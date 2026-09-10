---
name: orquestra-indice-filtrado-quoted-identifier
description: "⚠️ GOTCHA SQL Server/Orquestra: índice FILTRADO (com WHERE) exige QUOTED_IDENTIFIER ON e o sqlcmd das migrations roda com OFF — o CREATE falha (Msg 1934) e, se criado, TODO DML na tabela passa a falhar pelo sqlcmd enquanto o pymssql da DAG segue gravando"
metadata: 
  node_type: memory
  type: project
  originSessionId: b6fa286c-27e3-404c-8ac0-af606e0cefb3
  modified: 2026-08-13T21:42:10.273Z
---

**Não use índice filtrado (`CREATE INDEX ... WHERE ...`) nas migrations do
Orquestra.** Descoberto em 2026-08-13 na migration 090 (parentesco dos
chamados), medindo no SQL Server do dev — não deduzido.

**Dois estragos, e o segundo é o grave:**

1. **O `CREATE INDEX` falha com `Msg 1934`** ("SET options have incorrect
   settings: 'QUOTED_IDENTIFIER'"). Como o CREATE costuma vir DEPOIS dos
   `ALTER TABLE ADD`, a migration para no meio: **colunas criadas, índice
   não**. Dependendo do executor, ainda pode ser marcada como aplicada.

2. **Se o índice for criado (ex.: por um cliente com a opção ON), TODA
   operação DML na tabela passa a exigir QUOTED_IDENTIFIER ON — para
   sempre.** Um `DELETE` trivial pelo sqlcmd falha com o mesmo Msg 1934.
   Toda migration futura que tocar aquela tabela quebra.

**A assimetria que faz isso custar caro:** o `pymssql` da árvore `dags/`
conecta com **QUOTED_IDENTIFIER ON** e não é afetado — a DAG segue gravando
verde. Quem quebra é o **sqlcmd** que aplica as migrations. Sync saudável +
migrations falhando = meio dia de diagnóstico.

**A regra:** índice sem `WHERE`. Se alguém insistir no filtro, o
`SET QUOTED_IDENTIFIER ON;` precisa estar no **mesmo batch** do CREATE — mas
isso só resolve o estrago 1, não o 2. Em tabela da ordem de centenas/milhares
de linhas o filtro não paga o preço.

**Como testar antes de mergear** (foi o que pegou): aplicar a migration no
SQL Server do dev, **reaplicar** (idempotência) e depois rodar um
`DELETE`/`UPDATE` na tabela **pelo sqlcmd**. O DML posterior é o teste que
revela o estrago 2 — rodar só o CREATE não revela nada.

Ver [[orquestra-sge-app]], [[orquestra-placeholder-pyodbc-pymssql]],
[[orquestra-modos-de-falso-verde]].
