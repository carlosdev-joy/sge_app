"""Ferramenta de consulta a banco dos agentes (C1 da spec
docs/spec-agentes-ferramenta-banco.md).

C6 (decisão do usuário): "o agente só executa SELECT, nada além disso —
mesmo que o login da conexão possa gravar". Cinco rodadas de revisão
adversarial, com provas no SQL Server do DEV, mostraram que análise de texto
SOZINHA não garante isso em T-SQL (`SELECT 1DELETE FROM t SELECT 1COMMIT`
apagou dados; `NEXT VALUE FOR` grava a sequence mesmo com rollback). Por
isso são TRÊS camadas, e a do meio é o próprio servidor:

  1. **Análise léxica com lista positiva** (`validar`) — antes de conectar.
  2. **Plano do SQL Server** (`analisar_plano`): com `SET SHOWPLAN_XML ON` o
     servidor COMPILA e devolve o plano SEM executar nada; o Orquestra exige
     uma instrução do tipo SELECT, nada remoto, nada de sequence, e só os
     bancos liberados (com synonyms e views já resolvidos pelo servidor).
  3. **Transação sempre desfeita** (`consultar`): BEGIN TRAN → a consulta →
     ROLLBACK, com o tempo máximo definido antes de criar o cursor.

A conexão é a NATIVA cadastrada (`conn_native.abrir_conexao_nativa`), aberta
no banco liberado — nunca a credencial do próprio Orquestra (sem fallback).
Ao modelo vão só mensagens FIXAS: nunca host, porta, login ou texto do driver.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from services import agentes_ferramentas as af
from services import agentes_prompt as apr

log = logging.getLogger("orquestra-api")

MAX_LINHAS = 100            # C4
MAX_SQL = 20_000            # o mesmo da Cópia de Dados
MAX_CELULA = 200
MAX_BLOCO = 15_000
MAX_ESTRUTURA = 300
# Tempos (configuráveis em Admin › Agentes › Gateway e limites — chaves
# `agentes_banco_conexao_s` e `agentes_banco_consulta_s`, lidas a cada
# pergunta; os padrões valem quando a chave não existe).
CONEXAO_PADRAO_S, CONEXAO_MIN_S, CONEXAO_MAX_S = 10, 5, 60     # abrir a conexão (login)
CONSULTA_PADRAO_S, CONSULTA_MIN_S, CONSULTA_MAX_S = 30, 5, 120  # executar a consulta
TIMEOUT_MAX_S = CONSULTA_PADRAO_S  # nome antigo, mantido para quem já importava
# A conferência do plano (camada 2) só COMPILA — leva milissegundos (0,11 s numa
# consulta pesada na revisão da spec). Tem teto próprio, pequeno, para não
# disputar o orçamento da pergunta com a execução.
PLANO_MAX_S = 15


class SqlRecusado(ValueError):
    """A consulta não passa pela camada 1 ou 2 — `regra` é dito ao modelo."""

    def __init__(self, regra: str):
        super().__init__(regra)
        self.regra = regra


class BancoIndisponivel(RuntimeError):
    """Conexão removida, não nativa, sem rede/login ou sem SHOWPLAN — nunca
    diz por quê em detalhe (host e login não saem da API)."""


# ══════════════════════════════════════════════════════════════════════════
# Camada 1 — análise léxica
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Tok:
    tipo: str   # 'palavra' | 'nome' (delimitado) | 'numero' | 'literal' | 'simbolo'
    valor: str  # palavra em MAIÚSCULAS; nome/literal com o conteúdo sem delimitador


# Palavras reservadas do T-SQL (lista oficial da Microsoft — "Reserved Keywords
# (Transact-SQL)"). Uma reservada fora da lista positiva recusa a consulta.
RESERVADAS = frozenset("""
ADD ALL ALTER AND ANY AS ASC AUTHORIZATION BACKUP BEGIN BETWEEN BREAK BROWSE BULK BY CASCADE CASE CHECK
CHECKPOINT CLOSE CLUSTERED COALESCE COLLATE COLUMN COMMIT COMPUTE CONSTRAINT CONTAINS CONTAINSTABLE CONTINUE
CONVERT CREATE CROSS CURRENT CURRENT_DATE CURRENT_TIME CURRENT_TIMESTAMP CURRENT_USER CURSOR DATABASE DBCC
DEALLOCATE DECLARE DEFAULT DELETE DENY DESC DISK DISTINCT DISTRIBUTED DOUBLE DROP DUMP ELSE END ERRLVL ESCAPE
EXCEPT EXEC EXECUTE EXISTS EXIT EXTERNAL FETCH FILE FILLFACTOR FOR FOREIGN FREETEXT FREETEXTTABLE FROM FULL
FUNCTION GOTO GRANT GROUP HAVING HOLDLOCK IDENTITY IDENTITY_INSERT IDENTITYCOL IF IN INDEX INNER INSERT
INTERSECT INTO IS JOIN KEY KILL LEFT LIKE LINENO LOAD MERGE NATIONAL NOCHECK NONCLUSTERED NOT NULL NULLIF OF
OFF OFFSETS ON OPEN OPENDATASOURCE OPENQUERY OPENROWSET OPENXML OPTION OR ORDER OUTER OVER PERCENT PIVOT PLAN
PRECISION PRIMARY PRINT PROC PROCEDURE PUBLIC RAISERROR READ READTEXT RECONFIGURE REFERENCES REPLICATION
RESTORE RESTRICT RETURN REVERT REVOKE RIGHT ROLLBACK ROWCOUNT ROWGUIDCOL RULE SAVE SCHEMA SECURITYAUDIT SELECT
SEMANTICKEYPHRASETABLE SEMANTICSIMILARITYDETAILSTABLE SEMANTICSIMILARITYTABLE SESSION_USER SET SETUSER
SHUTDOWN SOME STATISTICS SYSTEM_USER TABLE TABLESAMPLE TEXTSIZE THEN TO TOP TRAN TRANSACTION TRIGGER TRUNCATE
TRY_CONVERT TSEQUAL UNION UNIQUE UNPIVOT UPDATE UPDATETEXT USE USER VALUES VARYING VIEW WAITFOR WHEN WHERE
WHILE WITH WITHIN WRITETEXT
""".split())

# As reservadas que uma CONSULTA usa (a lista positiva).
PERMITIDAS = frozenset("""
SELECT DISTINCT ALL TOP PERCENT FROM WHERE GROUP BY HAVING ORDER ASC DESC JOIN INNER LEFT RIGHT FULL OUTER
CROSS ON UNION EXCEPT INTERSECT PIVOT UNPIVOT AS AND OR NOT IN EXISTS BETWEEN LIKE ESCAPE IS NULL ANY SOME
CASE WHEN THEN ELSE END OVER COLLATE WITH WITHIN TABLESAMPLE FETCH VALUES COALESCE NULLIF CONVERT TRY_CONVERT
CURRENT_TIMESTAMP CURRENT_DATE CURRENT_TIME CURRENT
""".split())

# Não reservadas, mas que começam instrução ou mudam o comportamento — recusadas
# como palavra solta (entre colchetes, como nome, passam).
BLOQUEADAS = frozenset("""
THROW RECEIVE SEND MOVE GET ENABLE DISABLE NOLOCK TABLOCK TABLOCKX UPDLOCK XLOCK ROWLOCK PAGLOCK READPAST
READUNCOMMITTED READCOMMITTED READCOMMITTEDLOCK REPEATABLEREAD SERIALIZABLE SNAPSHOT NOWAIT FORCESEEK
FORCESCAN NOEXPAND
""".split())

# Funções que revelam o ambiente — recusadas QUANDO CHAMADAS (seguidas de '(').
# Como nome de coluna (`user_id`, `host_name`), passam.
FUNCOES_AMBIENTE = frozenset("""
SUSER_NAME SUSER_SNAME SUSER_ID SUSER_SID USER_NAME USER_ID ORIGINAL_LOGIN HOST_NAME HOST_ID APP_NAME
CONNECTIONPROPERTY SERVERPROPERTY LOGINPROPERTY IS_SRVROLEMEMBER IS_MEMBER IS_ROLEMEMBER HAS_PERMS_BY_NAME
HAS_DBACCESS DATABASEPROPERTYEX DATABASEPROPERTY DATABASE_PRINCIPAL_ID CONTEXT_INFO SESSION_CONTEXT
FN_TRACE_GETINFO DEFAULT_DOMAIN PERMISSIONS SESSIONPROPERTY CURRENT_REQUEST_ID FILEPROPERTY FILEGROUPPROPERTY
""".split())
# Leem nomes de OUTRO banco sem aparecer no plano — recusadas com mais de um
# argumento (ou, OBJECT_ID, com nome de 3 partes num literal); DB_NAME/DB_ID
# com qualquer argumento.
FUNCOES_METADADO = frozenset({"OBJECT_NAME", "OBJECT_SCHEMA_NAME"})
# Recebem um NOME de objeto em texto — e aceitam o de outro banco
# (`IDENT_CURRENT('outro.dbo.t')` devolveu a identity dele na revisão). Só
# com o 1º argumento sendo UM literal de até 2 partes: concatenação
# (`'outro.' + 'dbo.t'`), coluna ou variável não passam.
FUNCOES_NOME_EM_TEXTO = frozenset({"OBJECT_ID", "IDENT_CURRENT", "IDENT_SEED", "IDENT_INCR", "COL_LENGTH",
                                   "TYPE_ID", "SCHEMA_ID"})
# Sem argumento, revelam o esquema padrão do login (o próprio login no AD).
FUNCOES_SEM_ARG_PROIBIDO = frozenset({"SCHEMA_NAME", "SCHEMA_ID"})
FUNCOES_BANCO = frozenset({"DB_NAME", "DB_ID"})

# Visões de catálogo DO PRÓPRIO BANCO (lista positiva). Qualquer outro
# `sys.…` é recusado: `sys.login_token` e `sys.sysprocesses` devolveram o
# login na revisão.
SYS_PERMITIDAS = frozenset({"TABLES", "VIEWS", "COLUMNS", "SCHEMAS", "OBJECTS", "INDEXES", "INDEX_COLUMNS",
                            "TYPES", "FOREIGN_KEYS", "FOREIGN_KEY_COLUMNS", "EXTENDED_PROPERTIES"})
INFO_SCHEMA_PERMITIDAS = frozenset({"TABLES", "COLUMNS", "VIEWS", "ROUTINES", "KEY_COLUMN_USAGE",
                                    "TABLE_CONSTRAINTS"})

# Onde começa um nome de OBJETO (a posição que importa para `sys…`).
_ABRE_OBJETO = frozenset({"FROM", "JOIN", "APPLY"})
# Onde termina a lista de tabelas de um FROM (a vírgula deixa de ser "outra tabela").
_FECHA_FROM = frozenset({"WHERE", "GROUP", "HAVING", "ORDER", "UNION", "EXCEPT", "INTERSECT", "ON",
                         "PIVOT", "UNPIVOT", "OFFSET", "FETCH"})


def _letra(c: str) -> bool:
    return c.isalpha() or c == "_"


def tokenizar(sql: str) -> list[Tok]:
    """Tokens de verdade: literais, nomes delimitados, números, palavras e
    símbolos — o resto das regras olha SÓ para os tokens de código (uma
    palavra dentro de um literal nunca conta)."""
    toks: list[Tok] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c in " \t\r\n\f\v":
            i += 1
            continue
        if c.isspace():
            # Espaço Unicode (NBSP…): o que o analisador separa tem de ser o
            # que o servidor separa — na dúvida, recusa.
            raise SqlRecusado("espaço especial (fora do ASCII) não é aceito")
        if sql.startswith("--", i) or sql.startswith("/*", i):
            raise SqlRecusado("comentários não são aceitos")
        if c in "Nn" and i + 1 < n and sql[i + 1] == "'":
            i += 1
            c = "'"
        if c == "'":
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise SqlRecusado("texto entre aspas sem fechar")
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(sql[j])
                j += 1
            toks.append(Tok("literal", "".join(buf)))
            i = j + 1
            continue
        if c in "[\"":
            fecha = "]" if c == "[" else '"'
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise SqlRecusado("nome delimitado sem fechar")
                if sql[j] == fecha:
                    if j + 1 < n and sql[j + 1] == fecha:
                        buf.append(fecha)
                        j += 2
                        continue
                    break
                buf.append(sql[j])
                j += 1
            toks.append(Tok("nome", "".join(buf)))
            i = j + 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and sql[i + 1].isdigit()):
            j = i
            if sql.startswith(("0x", "0X"), i):
                j = i + 2
                while j < n and sql[j] in "0123456789abcdefABCDEF":
                    j += 1
            else:
                while j < n and sql[j].isdigit():
                    j += 1
                if j < n and sql[j] == ".":
                    j += 1
                    while j < n and sql[j].isdigit():
                        j += 1
                if j < n and sql[j] in "eE" and (j + 1 < n and (sql[j + 1].isdigit() or
                                                               (sql[j + 1] in "+-" and j + 2 < n
                                                                and sql[j + 2].isdigit()))):
                    j += 2
                    while j < n and sql[j].isdigit():
                        j += 1
            # Número COLADO a letra (`1DELETE`, `1.DELETE`, `1e0DELETE`): o
            # SQL Server lê como número + palavra — é como a revisão apagou dados.
            if j < n and (_letra(sql[j]) or sql[j] in "@#$"):
                raise SqlRecusado("número colado a uma palavra")
            toks.append(Tok("numero", sql[i:j]))
            i = j
            continue
        if _letra(c) or c in "@#":
            if c == "@":
                raise SqlRecusado("variáveis (@…) não são aceitas")
            if c == "#":
                raise SqlRecusado("tabelas temporárias (#…) não são aceitas")
            j = i + 1
            while j < n and (_letra(sql[j]) or sql[j].isdigit() or sql[j] in "@#$"):
                j += 1
            toks.append(Tok("palavra", sql[i:j].upper()))
            i = j
            continue
        if c in "{}":
            raise SqlRecusado("sequências ODBC {…} não são aceitas")
        if c == ":":
            raise SqlRecusado("rótulos e o operador ':' não são aceitos")
        if c in "(),.;*+-/%=<>!~&|^":
            if c in "<>!" and i + 1 < n and sql[i + 1] in "=<>":
                toks.append(Tok("simbolo", sql[i:i + 2]))
                i += 2
                continue
            toks.append(Tok("simbolo", c))
            i += 1
            continue
        raise SqlRecusado(f"caractere não aceito: {c!r}")
    return toks


def _cadeias_de_nome(toks: list[Tok]):
    """Cadeias `a.b.c` (com ou sem delimitador, com espaços) — devolve
    (índice inicial, índice final exclusivo, partes)."""
    i = 0
    while i < len(toks):
        if toks[i].tipo in ("palavra", "nome"):
            partes, j = [toks[i]], i + 1
            while j < len(toks) and toks[j] == Tok("simbolo", "."):
                if j + 1 < len(toks) and toks[j + 1] == Tok("simbolo", "*"):
                    partes.append(Tok("nome", "*"))   # `t.*` — fim da cadeia
                    j += 2
                    break
                if j + 1 < len(toks) and toks[j + 1].tipo in ("palavra", "nome"):
                    partes.append(toks[j + 1])
                    j += 2
                elif j + 1 < len(toks) and toks[j + 1] == Tok("simbolo", "."):
                    partes.append(Tok("nome", ""))   # `master..t` — parte vazia
                    j += 1
                else:
                    raise SqlRecusado("nome incompleto depois de '.'")
            yield i, j, partes
            i = j
        else:
            i += 1


def _args_da_chamada(toks: list[Tok], abre: int) -> list[list[Tok]]:
    """Os argumentos de uma chamada, a partir do '(' em `abre`."""
    args, atual, prof, k = [], [], 0, abre
    while k < len(toks):
        t = toks[k]
        if t == Tok("simbolo", "("):
            prof += 1
            if prof > 1:
                atual.append(t)
        elif t == Tok("simbolo", ")"):
            prof -= 1
            if prof == 0:
                if atual:
                    args.append(atual)
                return args
            atual.append(t)
        elif t == Tok("simbolo", ",") and prof == 1:
            args.append(atual)
            atual = []
        else:
            atual.append(t)
        k += 1
    return args


def validar(sql) -> str:
    """Camada 1. Devolve o texto a executar (o ORIGINAL, sem os `;` das
    pontas) ou levanta `SqlRecusado` dizendo a regra."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlRecusado("a consulta está vazia")
    texto = sql.strip()
    if len(texto) > MAX_SQL:
        raise SqlRecusado(f"a consulta passa de {MAX_SQL} caracteres")
    # `;WITH cte …` (hábito comum) e um `;` final: removidos do texto executado.
    texto = texto.lstrip().lstrip(";").strip().rstrip(";").strip()
    toks = tokenizar(texto)
    if not toks:
        raise SqlRecusado("a consulta está vazia")

    # ── uma instrução: parênteses e ';' ──
    prof = 0
    for t in toks:
        if t == Tok("simbolo", "("):
            prof += 1
        elif t == Tok("simbolo", ")"):
            prof -= 1
            if prof < 0:
                raise SqlRecusado("parênteses desbalanceados")
        elif t == Tok("simbolo", ";"):
            raise SqlRecusado("uma consulta só — ';' no meio não é aceito")
    if prof != 0:
        raise SqlRecusado("parênteses desbalanceados")

    # ── literais com cara de credencial: recusados, nunca mascarados ──
    for t in toks:
        if t.tipo == "literal" and apr.tem_segredo(t.valor):
            raise SqlRecusado("um texto da consulta parece uma credencial")

    # ── procedures de sistema/estendidas, em qualquer grafia ──
    for t in toks:
        if t.tipo in ("palavra", "nome") and t.valor.upper().startswith(("SP_", "XP_")):
            raise SqlRecusado("procedures de sistema (sp_…/xp_…) não são aceitas")

    # ── palavras: lista positiva, bloqueadas, funções sensíveis ──
    casos = 0
    # O que veio antes de cada '(' aberto — FOR só vale dentro de PIVOT ( … ).
    abertos: list[Tok | None] = []
    for k, t in enumerate(toks):
        if t == Tok("simbolo", "("):
            abertos.append(toks[k - 1] if k else None)
        elif t == Tok("simbolo", ")") and abertos:
            abertos.pop()
        if t.tipo != "palavra":
            continue
        w = t.valor
        seguinte = toks[k + 1] if k + 1 < len(toks) else None
        chamada = seguinte == Tok("simbolo", "(")
        if w.startswith("@@"):
            raise SqlRecusado("variáveis do servidor (@@…) não são aceitas")
        if w == "FOR":
            # Só `PIVOT (AGG(x) FOR col IN (…))`. Fora disso FOR é FOR XML/JSON,
            # FOR BROWSE ou NEXT VALUE FOR (grava a sequence).
            pai = abertos[-1] if abertos else None
            if not (pai is not None and pai.tipo == "palavra" and pai.valor in ("PIVOT", "UNPIVOT")
                    and toks[k - 1] in (Tok("simbolo", ")"), ) or
                    (pai is not None and pai.tipo == "palavra" and pai.valor == "UNPIVOT"
                     and toks[k - 1].tipo in ("palavra", "nome"))):
                raise SqlRecusado("'FOR' só em PIVOT/UNPIVOT (FOR XML/JSON e NEXT VALUE FOR não são aceitos)")
            continue
        if w in RESERVADAS and w not in PERMITIDAS:
            raise SqlRecusado(f"'{w}' não é aceito — só consultas SELECT")
        if w in BLOQUEADAS:
            raise SqlRecusado(f"'{w}' não é aceito numa consulta")
        if w == "CASE":
            casos += 1
        elif w == "END":
            if casos == 0:
                raise SqlRecusado("'END' fora de um CASE")
            casos -= 1
        elif w == "WITH":
            anterior = toks[k - 1].valor if k else ""
            if seguinte == Tok("simbolo", "("):
                raise SqlRecusado("dicas de tabela WITH (…) não são aceitas")
            if not (k == 0 or anterior == "," or
                    (seguinte and seguinte.tipo == "palavra" and seguinte.valor in ("TIES", "ROLLUP", "CUBE"))):
                raise SqlRecusado("'WITH' só no início (CTE), em WITH TIES ou WITH ROLLUP/CUBE")
        elif w == "CURRENT" and not (seguinte and seguinte.tipo == "palavra" and seguinte.valor == "ROW"):
            raise SqlRecusado("'CURRENT' só em CURRENT ROW")
        elif w == "FETCH":
            anterior = toks[k - 1] if k else None
            if not (anterior and anterior.tipo in ("palavra",) and anterior.valor in ("ROWS", "ROW")):
                raise SqlRecusado("'FETCH' só em OFFSET … ROWS FETCH NEXT … ROWS ONLY")
        if chamada and w in FUNCOES_AMBIENTE:
            raise SqlRecusado(f"a função {w} não é aceita (revela o ambiente)")
        if chamada and w in FUNCOES_BANCO and _args_da_chamada(toks, k + 1):
            raise SqlRecusado(f"{w} com argumento não é aceito")
        if chamada and w in FUNCOES_METADADO and len(_args_da_chamada(toks, k + 1)) > 1:
            raise SqlRecusado(f"{w} com banco não é aceito")
        if chamada and w in FUNCOES_SEM_ARG_PROIBIDO and not _args_da_chamada(toks, k + 1):
            raise SqlRecusado(f"{w}() sem argumento não é aceito (revela o login)")
        if chamada and w in FUNCOES_NOME_EM_TEXTO:
            args = _args_da_chamada(toks, k + 1)
            if args and not (len(args[0]) == 1 and args[0][0].tipo == "literal"
                             and args[0][0].valor.count(".") <= 1 and ".." not in args[0][0].valor):
                raise SqlRecusado(f"{w} só com o nome entre aspas, 'tabela' ou 'schema.tabela'")
    if casos:
        raise SqlRecusado("CASE sem END")

    # ── começa com SELECT ou WITH … AS ( … ) SELECT ──
    primeira = toks[0]
    if primeira.tipo != "palavra" or primeira.valor not in ("SELECT", "WITH"):
        raise SqlRecusado("a consulta precisa começar com SELECT (ou WITH … SELECT)")
    if primeira.valor == "WITH":
        _validar_cte(toks)

    # ── um novo SELECT no nível de fora só depois de UNION/EXCEPT/INTERSECT ──
    prof = 0
    for k, t in enumerate(toks):
        if t == Tok("simbolo", "("):
            prof += 1
        elif t == Tok("simbolo", ")"):
            prof -= 1
        elif prof == 0 and t == Tok("palavra", "SELECT") and k > 0:
            anterior = toks[k - 1]
            if not (anterior.tipo == "palavra" and anterior.valor in ("UNION", "ALL", "EXCEPT", "INTERSECT")):
                if not _select_da_cte(toks, k):
                    raise SqlRecusado("uma consulta só — um segundo SELECT solto não é aceito")

    # ── nomes: 3/4 partes, sys, INFORMATION_SCHEMA, visões de compatibilidade ──
    for ini, fim, partes in _cadeias_de_nome(toks):
        if len(partes) >= 3:
            raise SqlRecusado("nomes de 3 ou 4 partes não são aceitos — use apelidos (t.coluna)")
        esquema = partes[0].valor.upper() if len(partes) == 2 else ""
        if esquema == "SYS" and partes[1].valor.upper() not in SYS_PERMITIDAS:
            raise SqlRecusado(f"sys.{partes[1].valor} não é aceito — só o catálogo do próprio banco")
        if esquema == "INFORMATION_SCHEMA" and partes[1].valor.upper() not in INFO_SCHEMA_PERMITIDAS:
            raise SqlRecusado(f"INFORMATION_SCHEMA.{partes[1].valor} não é aceito")
        anterior = toks[ini - 1] if ini else None
        em_objeto = anterior is not None and (
            (anterior.tipo == "palavra" and anterior.valor in _ABRE_OBJETO)
            or (anterior == Tok("simbolo", ",") and _em_lista_de_tabelas(toks, ini)))
        if em_objeto and len(partes) == 1 and partes[0].valor.upper().startswith("SYS"):
            raise SqlRecusado(f"'{partes[0].valor}' não é aceito — visões de sistema antigas ficam fora")
    return texto


def _em_lista_de_tabelas(toks: list[Tok], ini: int) -> bool:
    """A vírgula antes de `ini` separa tabelas de um FROM (e não colunas)?"""
    prof, k = 0, ini - 1
    while k >= 0:
        t = toks[k]
        if t == Tok("simbolo", ")"):
            prof += 1
        elif t == Tok("simbolo", "("):
            if prof == 0:
                return False
            prof -= 1
        elif prof == 0 and t.tipo == "palavra":
            if t.valor in _ABRE_OBJETO:
                return True
            if t.valor in _FECHA_FROM or t.valor == "SELECT":
                return False
        k -= 1
    return False


def _validar_cte(toks: list[Tok]) -> None:
    """`WITH nome [(colunas)] AS ( … ) [, nome …]* SELECT` no nível de fora."""
    k = 1
    while True:
        if k >= len(toks) or toks[k].tipo not in ("palavra", "nome"):
            raise SqlRecusado("CTE sem nome")
        k += 1
        if k < len(toks) and toks[k] == Tok("simbolo", "("):
            k = _pula_parenteses(toks, k)
        if k >= len(toks) or toks[k] != Tok("palavra", "AS"):
            raise SqlRecusado("CTE sem AS")
        k += 1
        if k >= len(toks) or toks[k] != Tok("simbolo", "("):
            raise SqlRecusado("CTE sem ( … )")
        k = _pula_parenteses(toks, k)
        if k < len(toks) and toks[k] == Tok("simbolo", ","):
            k += 1
            continue
        if k < len(toks) and toks[k] == Tok("palavra", "SELECT"):
            return
        raise SqlRecusado("depois da CTE vem um SELECT")


def _select_da_cte(toks: list[Tok], k: int) -> bool:
    """O SELECT em `k` é o que fecha a lista de CTEs (`WITH … AS (…) SELECT`)?"""
    return toks[0] == Tok("palavra", "WITH") and k > 0 and toks[k - 1] == Tok("simbolo", ")") \
        and _fim_das_ctes(toks) == k


def _fim_das_ctes(toks: list[Tok]) -> int:
    k = 1
    while k < len(toks):
        k += 1  # nome
        if k < len(toks) and toks[k] == Tok("simbolo", "("):
            k = _pula_parenteses(toks, k)
        k += 1  # AS
        k = _pula_parenteses(toks, k)
        if k < len(toks) and toks[k] == Tok("simbolo", ","):
            k += 1
            continue
        return k
    return k


def _pula_parenteses(toks: list[Tok], k: int) -> int:
    prof = 0
    while k < len(toks):
        if toks[k] == Tok("simbolo", "("):
            prof += 1
        elif toks[k] == Tok("simbolo", ")"):
            prof -= 1
            if prof == 0:
                return k + 1
        k += 1
    raise SqlRecusado("parênteses desbalanceados")


# ══════════════════════════════════════════════════════════════════════════
# Camada 2 — o plano do SQL Server
# ══════════════════════════════════════════════════════════════════════════

_NS = "{http://schemas.microsoft.com/sqlserver/2004/07/showplan}"
_TIPOS_SELECT = frozenset({"SELECT", "SELECT WITHOUT QUERY"})
_SEM_BANCO_ACEITOS = frozenset({"STRING_SPLIT", "OPENJSON"})
_ESCRITA = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE"})


def _sem_colchete(v: str | None) -> str:
    return (v or "").strip().strip("[]").strip()


def _banco_do_proc(proc: str | None) -> str:
    """`[db].[dbo].[fn]` → `db` (vazio se o nome não tem banco)."""
    partes = [p for p in re.split(r"\]\.\[|\.", (proc or "").strip("[]")) if p]
    return partes[0] if len(partes) >= 3 else ""


def analisar_plano(xmls: list[str], bancos_liberados: set[str]) -> None:
    """Camada 2. `xmls`: o que o servidor devolveu com SHOWPLAN_XML ON."""
    liberados = {b.lower() for b in bancos_liberados}
    if len(xmls) != 1:
        raise SqlRecusado("uma consulta só (o servidor viu mais de um plano)")
    try:
        raiz = ET.fromstring(xmls[0])
    except ET.ParseError as e:
        raise SqlRecusado("o plano do servidor não pôde ser lido") from e
    lotes = raiz.findall(f".//{_NS}Batch")
    if len(lotes) != 1:
        raise SqlRecusado("uma consulta só (mais de um lote)")
    instrucoes = lotes[0].find(f"{_NS}Statements")
    filhos = list(instrucoes) if instrucoes is not None else []
    if len(filhos) != 1:
        raise SqlRecusado("uma consulta só — o servidor viu mais de uma instrução")
    unica = filhos[0]
    if unica.tag != f"{_NS}StmtSimple" or (unica.get("StatementType") or "").upper() not in _TIPOS_SELECT:
        raise SqlRecusado(f"só SELECT — o servidor viu '{unica.get('StatementType') or unica.tag.replace(_NS, '')}'")

    pais = {filho: pai for pai in raiz.iter() for filho in pai}

    def dentro_de_udf(el):
        p = pais.get(el)
        while p is not None:
            if p.tag == f"{_NS}UDF":
                return p
            p = pais.get(p)
        return None

    for el in raiz.iter():
        for atributo in ("RemoteSource", "RemoteObject"):
            if el.get(atributo):
                raise SqlRecusado("nada remoto — a consulta alcança outro servidor")
        if el.tag == f"{_NS}RelOp":
            fisico = (el.get("PhysicalOp") or "")
            logico = (el.get("LogicalOp") or "")
            if fisico.startswith("Remote") or logico.startswith("Remote"):
                raise SqlRecusado("nada remoto — a consulta alcança outro servidor")
            if logico.upper() in _ESCRITA and dentro_de_udf(el) is None:
                raise SqlRecusado("só leitura — o plano tem escrita")
        if el.tag == f"{_NS}Intrinsic" and (el.get("FunctionName") or "").lower() == "getsequencenext":
            raise SqlRecusado("NEXT VALUE FOR não é aceito (grava a sequence)")
        if el.tag in (f"{_NS}UserDefinedFunction",):
            banco = _banco_do_proc(el.get("FunctionName"))
            if banco and banco.lower() not in liberados:
                raise SqlRecusado("a consulta chama uma função de outro banco")
        if el.tag == f"{_NS}UDF":
            banco = _banco_do_proc(el.get("ProcName"))
            if banco and banco.lower() not in liberados:
                raise SqlRecusado("a consulta chama uma função de outro banco")
        if el.tag == f"{_NS}Object":
            banco = _sem_colchete(el.get("Database"))
            if banco:
                if banco.lower() not in liberados and banco.lower() != "mssqlsystemresource":
                    raise SqlRecusado(f"a consulta alcança o banco '{banco}', que não está liberado")
                continue
            tabela = _sem_colchete(el.get("Table"))
            if tabela.upper() in _SEM_BANCO_ACEITOS or tabela.upper().startswith("OPENJSON") \
                    or tabela.startswith("@"):
                continue
            # Sem exceção para o corpo de função: uma UDF do banco liberado que
            # lê `sys.dm_exec_sessions` aparece aqui como `[SYSSESSIONS]` sem
            # banco e devolvia o login (revisão da C1).
            raise SqlRecusado("a consulta lê um objeto de sistema que não é aceito")


# ══════════════════════════════════════════════════════════════════════════
# Mascaramento de dados pessoais (C2) e formatação
# ══════════════════════════════════════════════════════════════════════════

_COLUNAS_PESSOAIS = ("cpf", "cnpj", "email", "e_mail", "telefone", "fone", "celular", "whatsapp", "documento")
_RE_CPF = re.compile(r"(?<![\d.\-/])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?![\d.\-/])")
_RE_CNPJ = re.compile(r"(?<![\d.\-/])(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})(?![\d.\-/])")
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_TELEFONE = re.compile(
    r"(?:\+55\s*)?\(\d{2}\)\s*9?\d{4}[-\s]?\d{4}"      # (11) 91234-5678
    r"|\+55\s*\d{2}\s*9?\d{4}[-\s]?\d{4}"                # +55 11 91234-5678
    r"|(?<!\d)9\d{4}-\d{4}(?!\d)")                       # 91234-5678


def cpf_valido(d: str) -> bool:
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (s * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def cnpj_valido(d: str) -> bool:
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n in (12, 13):
        p = pesos if n == 12 else [6] + pesos
        s = sum(int(d[i]) * p[i] for i in range(n))
        r = s % 11
        if (0 if r < 2 else 11 - r) != int(d[n]):
            return False
    return True


def mascarar_texto(v: str) -> str:
    """Por VALOR, em qualquer coluna: CPF/CNPJ que passam no dígito
    verificador, e-mail e telefone formatado."""
    v = _RE_EMAIL.sub("[email]", v)
    v = _RE_CNPJ.sub(lambda m: "[cnpj]" if cnpj_valido("".join(m.groups())) else m.group(0), v)
    v = _RE_CPF.sub(lambda m: "[cpf]" if cpf_valido("".join(m.groups())) else m.group(0), v)
    return _RE_TELEFONE.sub("[telefone]", v)


def coluna_pessoal(nome: str) -> bool:
    n = (nome or "").lower()
    return any(p in n for p in _COLUNAS_PESSOAIS)


def _celula(v, *, mascarar: bool, pessoal: bool) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(v)} bytes>"
    if isinstance(v, Binario):
        return str(v)
    t = str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    if mascarar and pessoal:
        return "[oculto]"
    if apr.tem_segredo(t):
        return "••••"
    t = af.redigir(t)
    if mascarar:
        t = mascarar_texto(t)
    return t if len(t) <= MAX_CELULA else t[:MAX_CELULA] + "…"


def formatar(colunas: list[str], linhas: list, *, mascarar: bool, havia_mais: bool,
             por_tamanho: bool = False) -> str:
    """Texto compacto para o modelo: cabeçalho + linhas separadas por TAB."""
    pessoais = [mascarar and coluna_pessoal(c) for c in colunas]
    saida = ["\t".join(c or f"col{i + 1}" for i, c in enumerate(colunas))]
    total, cortadas = len(saida[0]), 0
    for linha in linhas:
        txt = "\t".join(_celula(v, mascarar=mascarar, pessoal=pessoais[i]) for i, v in enumerate(linha))
        if total + len(txt) + 1 > MAX_BLOCO:
            cortadas += 1
            continue
        saida.append(txt)
        total += len(txt) + 1
    if cortadas:
        saida.append(f"… ({cortadas} linhas não mostradas — tamanho)")
    if havia_mais and por_tamanho:
        saida.append("… (a leitura parou pelo volume de dados — colunas muito grandes; "
                      "selecione só as colunas necessárias)")
    elif havia_mais:
        saida.append(f"… (havia mais de {MAX_LINHAS} linhas — refine a consulta)")
    return "\n".join(saida)


# ══════════════════════════════════════════════════════════════════════════
# Erros → mensagens fixas
# ══════════════════════════════════════════════════════════════════════════

_RE_NUM_ERRO = re.compile(r"\((\d{2,6})\)")
_RE_ENTRE_ASPAS = re.compile(r"'([^']{1,128})'")


def mensagem_de_erro(e: Exception, *, mascarar: bool) -> tuple[str, str | None]:
    """(mensagem fixa ao modelo, categoria de falha permanente ou None)."""
    if isinstance(e, (SqlRecusado, BancoIndisponivel)):
        return str(e), None
    args = getattr(e, "args", None) or ()
    # pyodbc: args = (SQLSTATE, mensagem do driver)
    texto = str(args[-1]) if len(args) >= 2 else str(e)
    estado = str(args[0]) if len(args) >= 2 else ""
    nums = _RE_NUM_ERRO.findall(texto)
    num = int(nums[-1]) if nums else 0

    def nome():
        m = _RE_ENTRE_ASPAS.search(texto)
        v = m.group(1) if m else "?"
        return mascarar_texto(v) if mascarar else v

    if estado == "HYT00" or "[HYT00]" in texto:
        return "tempo esgotado — a consulta demorou demais; refine (filtre, agregue, limite)", None
    if num in (208, 4121):
        return f"tabela ou objeto inexistente: {nome()}", "banco_objeto_inexistente"
    if num == 207:
        return f"coluna inexistente: {nome()}", "banco_objeto_inexistente"
    if num in (229, 230, 262, 297, 916, 4060):
        return "banco sem acesso para esta consulta", "banco_sem_acesso"
    if num in (18456, 18452) or estado.startswith("08"):
        return "conexão indisponível", None
    if num in (102, 105, 156, 170, 4145, 8155, 8156):
        return f"sintaxe inválida perto de {nome()}", None
    return f"a consulta falhou no servidor (erro {num or 'desconhecido'})", None


# ══════════════════════════════════════════════════════════════════════════
# Conexão e execução
# ══════════════════════════════════════════════════════════════════════════

def limitar(valor, minimo: int, maximo: int, padrao: int) -> int:
    """Valor de config (texto) → inteiro dentro da faixa; lixo = padrão."""
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao
    return max(minimo, min(maximo, n))


def _abrir(conn_id: str, banco: str, timeout_s: float, conexao_s: float = CONEXAO_PADRAO_S):
    """Conexão NATIVA no banco, com o tempo máximo já definido — o cursor
    que `abrir_conexao_nativa` devolve é descartado (não herda o timeout).
    `conexao_s`: quanto esperar o LOGIN; `timeout_s`: cada comando depois."""
    from services.conn_native import abrir_conexao_nativa
    espera = max(1, int(conexao_s))
    inicio = time.monotonic()
    try:
        par = abrir_conexao_nativa(conn_id, banco, timeout_s=espera)
    except Exception as e:  # noqa: BLE001 — login/rede: nunca o texto do driver
        log.warning("agentes_sql: conexão %s/%s falhou: %s", conn_id, banco, type(e).__name__)
        # Só é "não respondeu no tempo" se o tempo de fato passou: host
        # inexistente e porta fechada também chegam como "Login timeout"
        # do driver, mas na hora — e aí aumentar o tempo não resolve.
        esperou = time.monotonic() - inicio >= espera * 0.8
        if esperou and ("HYT00" in str(e) or "Login timeout" in str(e)):
            # O servidor não respondeu no tempo: é o caso que o admin resolve
            # aumentando "Tempo para conectar ao banco" — a mensagem diz o tempo.
            raise BancoIndisponivel(f"conexão indisponível — o servidor não respondeu em {espera} s") from None
        raise BancoIndisponivel("conexão indisponível") from None
    if par is None:
        # Não nativa (só no Airflow) ou ilegível: SEM fallback para a
        # credencial do Orquestra (T3).
        raise BancoIndisponivel("conexão indisponível")
    cx, cur0 = par
    try:
        cur0.close()
    except Exception:  # noqa: BLE001
        pass
    cx.autocommit = True
    cx.timeout = max(1, int(timeout_s))
    return cx


def _plano(cx, texto: str) -> list[str]:
    """SHOWPLAN_XML ON / a consulta / OFF — três `execute`: o SET tem de ser
    o único comando do lote (erro 1067), e com ele NADA executa."""
    cur = cx.cursor()
    xmls: list[str] = []
    cur.execute("SET SHOWPLAN_XML ON")
    try:
        cur.execute(texto)
        while True:
            if cur.description is not None:     # conjunto sem linhas não tem description
                xmls.extend(str(r[0]) for r in cur.fetchall())
            if not cur.nextset():
                break
    finally:
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass
        c2 = cx.cursor()
        c2.execute("SET SHOWPLAN_XML OFF")
        c2.close()
    return xmls


def _fechar(cx) -> None:
    try:
        c = cx.cursor()
        c.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
        c.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        cx.close()
    except Exception:  # noqa: BLE001
        pass


def consultar(conn_id: str, banco: str, sql: str, *, bancos_da_conexao: set[str], mascarar: bool,
              timeout_s: float, conexao_s: float = CONEXAO_PADRAO_S, plano_s: float | None = None) -> dict:
    """As três camadas. Devolve {sql (o texto EXECUTADO), texto, colunas,
    linhas, havia_mais, ms}.
    Levanta `SqlRecusado`, `BancoIndisponivel` ou a exceção do driver (o
    chamador a traduz com `mensagem_de_erro`)."""
    texto = validar(sql)                       # camada 1 — antes de conectar
    t0 = time.monotonic()
    execucao = min(CONSULTA_MAX_S, timeout_s)
    plano = min(PLANO_MAX_S, execucao) if plano_s is None else plano_s
    cx = _abrir(conn_id, banco, plano, conexao_s)  # o timeout vale para os cursores criados DEPOIS
    try:
        try:
            xmls = _plano(cx, texto)           # camada 2 — compila, não executa
        except Exception as e:  # noqa: BLE001
            if "(262)" in str(e) or "SHOWPLAN permission" in str(e):
                raise BancoIndisponivel("conexão indisponível (sem permissão SHOWPLAN)") from None
            raise
        analisar_plano(xmls, bancos_da_conexao)
        cx.timeout = max(1, int(execucao))      # antes de criar o cursor da execução
        cur = cx.cursor()                       # camada 3 — transação desfeita
        cur.execute("BEGIN TRANSACTION")
        cur.execute(texto)
        colunas = [d[0] for d in (cur.description or [])]
        linhas, havia_mais, por_tamanho = _ler_linhas(cur) if colunas else ([], False, False)
        try:
            cur.cancel()
        except Exception:  # noqa: BLE001
            pass
        return {"sql": texto, "colunas": colunas, "linhas": linhas, "havia_mais": havia_mais,
                "texto": formatar(colunas, linhas, mascarar=mascarar, havia_mais=havia_mais,
                                  por_tamanho=por_tamanho),
                "ms": int((time.monotonic() - t0) * 1000)}
    finally:
        _fechar(cx)                             # ROLLBACK sempre


class Binario:
    """Uma célula binária já lida — só o tamanho sobrevive."""

    def __init__(self, tamanho: int):
        self.tamanho = tamanho

    def __str__(self) -> str:
        return f"<{self.tamanho} bytes>"


def _reduzir(v):
    """A célula como ela fica guardada: texto até `_GUARDA_CELULA` (o corte
    de 200 é depois da máscara, em `_celula`), binário vira o tamanho."""
    if isinstance(v, (bytes, bytearray, memoryview)):
        return Binario(len(v))
    if isinstance(v, str) and len(v) > _GUARDA_CELULA:
        return v[:_GUARDA_CELULA]
    return v


_GUARDA_CELULA = 2_000
# Teto do que o driver entrega (antes de reduzir). Uma coluna VARBINARY(MAX)
# de 10 MB em 100 linhas levava a API a GB (revisão da C1): as linhas vêm UMA
# a UMA, reduzidas na hora, e a leitura para ao passar deste volume.
MAX_BYTES_LIDOS = 32 * 1024 * 1024


def _tamanho_bruto(v) -> int:
    if isinstance(v, (bytes, bytearray, memoryview, str)):
        return len(v)
    return 16


def _ler_linhas(cur) -> tuple[list[tuple], bool, bool]:
    """(linhas, havia_mais, parou_por_tamanho)."""
    linhas: list[tuple] = []
    lidos = 0
    while True:
        r = cur.fetchone()
        if r is None:
            return linhas, False, False
        if len(linhas) == MAX_LINHAS:
            return linhas, True, False        # a 101ª só diz "havia mais"
        lidos += sum(_tamanho_bruto(v) for v in r)
        linhas.append(tuple(_reduzir(v) for v in r))
        del r
        if lidos > MAX_BYTES_LIDOS:
            return linhas, True, True


def _escapar_like(v: str) -> str:
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("[", "\\[")


def estrutura(conn_id: str, banco: str, *, filtro: str | None, tabela: str | None, mascarar: bool,
              timeout_s: float, conexao_s: float = CONEXAO_PADRAO_S) -> dict:
    """`banco_estrutura`: SQL FIXO e parametrizado do próprio Orquestra (não
    passa pelo modelo) — tabelas/views (com filtro) ou as colunas de uma."""
    t0 = time.monotonic()
    cx = _abrir(conn_id, banco, min(CONSULTA_MAX_S, timeout_s), conexao_s)
    try:
        cur = cx.cursor()
        if tabela:
            partes = [p.strip("[] ") for p in str(tabela).split(".")]
            if len(partes) > 2 or not all(partes):
                raise SqlRecusado("tabela: use 'tabela' ou 'schema.tabela'")
            esquema, nome = (partes if len(partes) == 2 else (None, partes[0]))
            cur.execute(
                f"SELECT TOP ({MAX_ESTRUTURA + 1}) TABLE_SCHEMA, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, "
                "IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND (? IS NULL OR TABLE_SCHEMA = ?) "
                "ORDER BY TABLE_SCHEMA, ORDINAL_POSITION", [nome, esquema, esquema])
            colunas = ["schema", "coluna", "tipo", "tamanho", "nulo"]
        else:
            padrao = f"%{_escapar_like(filtro)}%" if filtro else None
            cur.execute(
                f"SELECT TOP ({MAX_ESTRUTURA + 1}) TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                "FROM INFORMATION_SCHEMA.TABLES WHERE (? IS NULL OR TABLE_NAME LIKE ? ESCAPE '\\') "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME", [padrao, padrao])
            colunas = ["schema", "nome", "tipo"]
        linhas = [tuple(r) for r in cur.fetchall()]
        havia_mais = len(linhas) > MAX_ESTRUTURA
        linhas = linhas[:MAX_ESTRUTURA]
        txt = formatar(colunas, linhas, mascarar=False, havia_mais=False)
        if havia_mais:
            txt += f"\n… (mais de {MAX_ESTRUTURA} itens — use \"filtro\" para ver o resto)"
        if not linhas:
            txt = "nenhuma tabela encontrada" if not tabela else f"tabela não encontrada: {tabela}"
        return {"texto": txt, "linhas": len(linhas), "ms": int((time.monotonic() - t0) * 1000)}
    finally:
        _fechar(cx)


# ══════════════════════════════════════════════════════════════════════════
# Admin: conexões e bancos
# ══════════════════════════════════════════════════════════════════════════

def listar_conexoes(cur) -> list[dict]:
    """As conexões NATIVAS SQL Server — sem login nem senha."""
    cur.execute("SELECT conn_id, host, port, descricao FROM dbo.etl_conexao "
                "WHERE ISNULL(conn_type, 'mssql') = 'mssql' ORDER BY conn_id")
    return [{"conexao": r[0], "servidor": f"{r[1]}{',' + str(r[2]) if r[2] else ''}", "descricao": r[3]}
            for r in cur.fetchall()]


def bancos_da_conexao(conn_id: str, conexao_s: float = CONEXAO_PADRAO_S) -> dict:
    """Os bancos que a conexão alcança, com SHOWPLAN e o aviso de escrita
    por banco (C6: escrita só AVISA). Levanta `BancoIndisponivel`."""
    cx = _abrir(conn_id, "master", 15, conexao_s)
    try:
        cur = cx.cursor()
        cur.execute(
            "SELECT d.name, HAS_PERMS_BY_NAME(d.name, 'DATABASE', 'SHOWPLAN'), "
            "CASE WHEN HAS_PERMS_BY_NAME(d.name, 'DATABASE', 'INSERT') = 1 "
            "  OR HAS_PERMS_BY_NAME(d.name, 'DATABASE', 'UPDATE') = 1 "
            "  OR HAS_PERMS_BY_NAME(d.name, 'DATABASE', 'DELETE') = 1 "
            "  OR HAS_PERMS_BY_NAME(d.name, 'DATABASE', 'EXECUTE') = 1 THEN 1 ELSE 0 END "
            "FROM sys.databases d WHERE d.state_desc = 'ONLINE' AND HAS_DBACCESS(d.name) = 1 "
            "AND d.database_id > 4 ORDER BY d.name")
        bancos = [{"banco": r[0], "showplan": bool(r[1]), "escrita": bool(r[2])} for r in cur.fetchall()]
        cur.execute("SELECT IS_SRVROLEMEMBER('sysadmin')")
        sysadmin = bool((cur.fetchone() or [0])[0])
        return {"bancos": bancos, "sysadmin": sysadmin}
    except BancoIndisponivel:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("agentes_sql: listar bancos de %s falhou: %s", conn_id, type(e).__name__)
        raise BancoIndisponivel("conexão indisponível") from None
    finally:
        _fechar(cx)


def _escrita_em_objeto(conn_id: str, banco: str, conexao_s: float = CONEXAO_PADRAO_S) -> bool:
    """GRANT de escrita numa tabela/view/procedure (o nível de
    banco de `bancos_da_conexao` não vê — revisão da C1). Só ao salvar, e
    só para os bancos escolhidos. Se não der para conferir, avisa (na
    dúvida, o aviso é o lado seguro)."""
    try:
        cx = _abrir(conn_id, banco, 20, conexao_s)
    except BancoIndisponivel:
        return True
    try:
        cur = cx.cursor()
        # Permissão EFETIVA por objeto (já inclui a concedida no esquema). O
        # esquema em si não serve: membro de `db_datareader` "tem" INSERT no
        # esquema vazio `db_datareader`, que é da própria role.
        nome = "QUOTENAME(SCHEMA_NAME(o.schema_id)) + '.' + QUOTENAME(o.name)"
        cur.execute(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM sys.objects o WHERE o.is_ms_shipped = 0 AND ("
            f"(o.type IN ('U', 'V') AND (HAS_PERMS_BY_NAME({nome}, 'OBJECT', 'INSERT') = 1 "
            f"OR HAS_PERMS_BY_NAME({nome}, 'OBJECT', 'UPDATE') = 1 "
            f"OR HAS_PERMS_BY_NAME({nome}, 'OBJECT', 'DELETE') = 1)) "
            f"OR (o.type IN ('P', 'PC', 'X') AND HAS_PERMS_BY_NAME({nome}, 'OBJECT', 'EXECUTE') = 1))) "
            "THEN 1 ELSE 0 END")
        return bool((cur.fetchone() or [1])[0])
    except Exception:  # noqa: BLE001
        return True
    finally:
        _fechar(cx)


def verificar_pares(pares: list[tuple[str, str]], conexao_s: float = CONEXAO_PADRAO_S) -> list[str]:
    """Ao salvar o agente: cada par NOVO ou alterado precisa abrir, existir e
    ter SHOWPLAN (§2 da spec). Levanta `ValueError` com a mensagem para o
    admin; devolve os AVISOS (login com escrita — C6: avisa, não bloqueia).
    Uma ida ao servidor por conexão."""
    avisos: list[str] = []
    por_conexao: dict[str, list[str]] = {}
    for conexao, banco in pares:
        por_conexao.setdefault(conexao, []).append(banco)
    for conexao, bancos in por_conexao.items():
        try:
            info = bancos_da_conexao(conexao, conexao_s)
        except BancoIndisponivel as e:
            if "não respondeu" in str(e):
                raise ValueError(f"a conexão '{conexao}' não abriu: o servidor não respondeu no tempo "
                                 "configurado (Admin › Agentes › Gateway e limites)") from None
            raise ValueError(f"a conexão '{conexao}' não abriu (removida, não nativa, fora do ar ou "
                             "login recusado)") from None
        alcancaveis = {b["banco"].lower(): b for b in info["bancos"]}
        for banco in bancos:
            b = alcancaveis.get(banco.lower())
            if b is None:
                raise ValueError(f"o banco '{banco}' não existe na conexão '{conexao}' ou o login não o alcança")
            if not b["showplan"]:
                raise ValueError(f"o login da conexão '{conexao}' não tem SHOWPLAN no banco '{banco}' — "
                                 "sem ele o Orquestra não confere a consulta e o agente não usa o banco")
            if b["escrita"] or info["sysadmin"] or _escrita_em_objeto(conexao, b["banco"], conexao_s):
                avisos.append(f"o login de '{conexao}' pode gravar em '{banco}' — o agente só executa SELECT, "
                              "mas uma conexão só de leitura é a proteção extra recomendada")
    return avisos
