"""Prova da auditoria do agente Terminal no SQL Server REAL do DEV (spec docs/spec-agente-terminal.md, F2).

Roda a migration 153 DUAS vezes, exercita `registrar`/`iniciar`/`finalizar`/`listar` com o driver pyodbc
de verdade (binding de parâmetros, GETDATE, COALESCE com NULL) e tenta inserir as combinações que os CHECKs
devem recusar — TUDO dentro de uma transação que termina em ROLLBACK (nada fica gravado; ele confere isso).

Por que existe: os testes de unidade usam dublê de cursor e NÃO executam T-SQL. Um CHECK com sintaxe inválida
(`(a = b) = (c = d)`, Msg 102) passou por todos eles e só o SQL Server real o pegou.

Como rodar (DEV; o container da API tem pyodbc e MSSQL_CONN_STR):
    C=orquestra-api
    docker cp api/services/agentes_terminal.py $C:/tmp/agentes_terminal_f2.py
    docker cp sql/migrations/153_agente_terminal.sql $C:/tmp/153_agente_terminal.sql
    docker cp scripts/prova_agente_terminal_sql.py $C:/tmp/prova_f2.py
    docker exec $C sh -c 'cd /app && python /tmp/prova_f2.py'
    docker exec $C rm -f /tmp/agentes_terminal_f2.py /tmp/153_agente_terminal.sql /tmp/prova_f2.py
Mexeu em `agentes_terminal.py` ou na 153? Rode de novo. Nunca aponte para produção.
"""
import sys, os, re, uuid, importlib.util
sys.path.insert(0, "/app")
import pyodbc
spec = importlib.util.spec_from_file_location("agentes_terminal_f2", "/tmp/agentes_terminal_f2.py")
at = importlib.util.module_from_spec(spec); spec.loader.exec_module(at)

conn = pyodbc.connect(os.environ["MSSQL_CONN_STR"], autocommit=False)
cur = conn.cursor()
ok = lambda m: print("OK  ", m)
def deve_falhar(m, fn):
    try:
        fn(); print("FALHA (devia recusar):", m); sys.exit(1)
    except (pyodbc.Error, at.AuditoriaInvalida) as e:
        ok(f"recusado — {m}: {str(e).splitlines()[0][:90]}")
try:
    cur.execute("SELECT OBJECT_ID('dbo.etl_agente_terminal_cmd','U')"); antes = cur.fetchone()[0]
    print("tabela existia antes:", antes is not None)
    sql = open("/tmp/153_agente_terminal.sql", encoding="utf-8").read()
    for rodada in (1, 2):                       # idempotência: roda 2×
        for b in re.split(r"^\s*GO\s*$", sql, flags=re.M):
            if b.strip(): cur.execute(b)
        ok(f"migration 153 rodada {rodada}")
    cur.execute("SELECT COUNT(*) FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('dbo.etl_agente_terminal_cmd')"); ok(f"CHECKs criados: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.etl_agente_terminal_cmd') AND name LIKE 'IX_%'"); ok(f"índices: {cur.fetchone()[0]}")

    # registrar (driver real)
    r = at.registrar(cur, conversa_id="conv1", matricula="DEV1", servidor="airflow", comando="airflow dags unpause x", classe="escrita", motivo="reativar", ip="10.0.0.1")
    cur.execute("SELECT estado, DATEDIFF(second, criado_em, expira_em), redigido FROM dbo.etl_agente_terminal_cmd WHERE cmd_id=?", [r["cmd_id"]])
    est, dif, red = cur.fetchone(); assert (est, dif, red) == ("proposto", 120, False), (est, dif, red); ok(f"registrar escrita → proposto, prazo {dif}s no relógio do banco")
    rl = at.registrar(cur, conversa_id=None, matricula="DEV1", servidor="airflow", comando="tail -n 5 /x", classe="leitura"); assert rl["estado"] == "executando"; ok("registrar leitura → executando")
    rp = at.registrar(cur, conversa_id=None, matricula="DEV1", servidor="airflow", comando="mysql -pHUNTER2 db", classe="proibido")
    cur.execute("SELECT estado, comando, redigido FROM dbo.etl_agente_terminal_cmd WHERE cmd_id=?", [rp["cmd_id"]]); e, c, rd = cur.fetchone()
    assert e == "bloqueado" and "HUNTER2" not in c and rd is True; ok(f"proibido com segredo → bloqueado, redigido=1, texto: {c}")

    # iniciar / finalizar (binding real: COALESCE(?, col), CASE WHEN ? = ..., ? IN (...))
    assert at.iniciar(cur, r["cmd_id"], "DEV1") is True; ok("iniciar proposto → executando")
    assert at.iniciar(cur, r["cmd_id"], "DEV1") is False; ok("iniciar de novo (duplo clique) → False")
    assert at.finalizar(cur, r["cmd_id"], "executado", codigo_saida=0, duracao_ms=900, saida="DAG reativada") is True; ok("finalizar executando → executado")
    assert at.finalizar(cur, r["cmd_id"], "falhou") is False; ok("finalizar de estado final → False")
    assert at.finalizar(cur, rl["cmd_id"], "falhou", decidido_por=None, codigo_saida=1, duracao_ms=5, saida="erro") is True; ok("finalizar com decidido_por=None (COALESCE NULL) ok")
    r2 = at.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a", comando="systemctl restart x", classe="escrita")
    assert at.finalizar(cur, r2["cmd_id"], "recusado", decidido_por="DEV1") is True
    cur.execute("SELECT estado, decidido_por, CASE WHEN decidido_em IS NULL THEN 0 ELSE 1 END FROM dbo.etl_agente_terminal_cmd WHERE cmd_id=?", [r2["cmd_id"]]); row = tuple(cur.fetchone()); print("   linha recusada:", row); assert row == ("recusado", "DEV1", 1), row; ok("recusar grava quem e quando")
    assert at.finalizar(cur, r2["cmd_id"], "executado") is False; ok("recusada não vira executada")
    # prazo vencido: proposta com expira_em no passado não inicia
    r3 = at.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a", comando="touch /x", classe="escrita")
    cur.execute("UPDATE dbo.etl_agente_terminal_cmd SET expira_em = DATEADD(second,-1,GETDATE()) WHERE cmd_id=?", [r3["cmd_id"]])
    assert at.iniciar(cur, r3["cmd_id"], "DEV1") is False; ok("proposta vencida não inicia (relógio do banco)")
    assert at.finalizar(cur, r3["cmd_id"], "expirado") is True; ok("vencida → expirado")

    # listar (paginação/filtros/data)
    out = at.listar(cur, matricula="DEV1", desde="2020-01-01", ate="2099-12-31", limite=2)
    assert out["total"] >= 5 and len(out["itens"]) == 2 and out["itens"][0]["cmd_id"]; ok(f"listar total={out['total']} paginado em 2")
    out = at.listar(cur, estado="bloqueado", classe="proibido"); assert out["total"] == 1; ok("listar com filtros")

    # CHECKs do banco recusam o que a máquina proíbe (insert direto, sem passar pelo service)
    ins = "INSERT INTO dbo.etl_agente_terminal_cmd (matricula, servidor, comando, hash, classe, estado, redigido) VALUES ('X','s','c','%s',?,?,?)" % ("0"*64)
    for cl, es, rd in [("proibido","executando",0), ("leitura","bloqueado",0), ("leitura","proposto",0), ("leitura","recusado",0), ("escrita","proposto",1), ("leitura","executando",1), ("qualquer","executando",0), ("leitura","inventado",0)]:
        cur.execute("SAVE TRANSACTION s1") if False else None
        deve_falhar(f"classe={cl} estado={es} redigido={rd}", lambda cl=cl, es=es, rd=rd: cur.execute(ins, [cl, es, rd]))
    for cl, es, rd in [("leitura","executando",0), ("escrita","proposto",0), ("escrita","executado",0), ("proibido","bloqueado",1), ("proibido","bloqueado",0)]:
        cur.execute(ins, [cl, es, rd]); ok(f"aceito: classe={cl} estado={es} redigido={rd}")
finally:
    conn.rollback()
    cur.execute("SELECT OBJECT_ID('dbo.etl_agente_terminal_cmd','U')"); depois = cur.fetchone()[0]
    print("ROLLBACK feito; tabela existe depois:", depois is not None, "(esperado: igual a antes =", antes is not None, ")")
    conn.close()
