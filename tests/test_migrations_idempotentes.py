"""Toda migration precisa poder rodar DUAS vezes sem quebrar.

Pergunta do dono do produto, ao preparar o deploy de produção:

    "os migrations não pode ter essa validação na hora de rodar elas, assim se
     rodar não gera impacto?"

Pode, e quase todas já têm. Este arquivo transforma "quase" em "todas".

**Por que a proteção do runner não basta.** O `deploy.sh` consulta
`dbo.etl_schema_version` e pula o que já foi aplicado. Isso é proteção de FORA,
e ela não cobre:

  * banco restaurado de um backup parcial (a tabela existe, o registro não);
  * migration aplicada à mão, no susto, sem registrar;
  * deploy interrompido no meio — o objeto foi criado, o registro não chegou;
  * ambiente novo montado a partir de um dump antigo.

Em qualquer um desses, a migration roda de novo. Se ela não for idempotente, o
deploy PARA com erro no meio — e parar no meio de uma sequência de migrations é
o pior lugar para parar, porque metade do esquema mudou.

⚠️ **Um achado real:** das 100 migrations do repo, `010_datastage_job_log.sql`
era a única cuja segunda execução falhava ("There is already an object named
'etl_ds_job_log'"). Corrigida junto com este teste.

**O que conta como guarda.** Qualquer condicional. O repo usa
`IF OBJECT_ID(...) IS NULL`, `IF COL_LENGTH(...) IS NULL`,
`IF (SELECT COUNT(*) ...) = 0`, `IF @len < 250`, `CREATE OR ALTER`,
`WHERE NOT EXISTS` e `MERGE` — todas resolvem o mesmo problema. Uma primeira
versão deste teste ENUMERAVA as formas conhecidas e acusou a migration 072, que
é correta: enumerar transforma o teste numa lista de estilos aprovados, e o
próximo estilo correto vira uma falha.

⚠️ **Limite declarado:** um regex não julga se a condição está CERTA. `IF 1=1`
passaria. O que este teste prende é a ausência de condicional nenhuma — que foi
o defeito real encontrado.

**O que NÃO é analisado:** o corpo de procedures e funções. Lá dentro o
`INSERT` é código de runtime, executado a cada chamada — a pergunta de
idempotência não se aplica a ele, e sim ao `CREATE OR ALTER` que o define.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MIGRACOES = sorted((RAIZ / "sql" / "migrations").glob("*.sql"))

# Instruções que, sem guarda, quebram na segunda execução.
DDL = re.compile(
    r"^\s*(CREATE\s+(?:UNIQUE\s+)?(?:CLUSTERED\s+|NONCLUSTERED\s+)?"
    r"(?:TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER)"
    r"|ALTER\s+TABLE\s+[\w\.\[\]]+\s+(?:ADD|DROP)"
    r"|INSERT\s+INTO\s+dbo\."
    r"|DROP\s+(?:TABLE|INDEX|VIEW|PROCEDURE))",
    re.I)

# QUALQUER condicional conta como guarda.
#
# ⚠️ Uma versão anterior listava as formas conhecidas (`IF NOT EXISTS`,
# `IF OBJECT_ID`, `IF COL_LENGTH`…) e acusou a migration 072, cuja guarda é
# `IF @len IS NOT NULL AND @len < 250` — legítima, idempotente e fora da lista.
# Enumerar formas transforma o teste numa lista de estilos aprovados, e o
# próximo estilo correto vira uma falha.
#
# LIMITE ASSUMIDO E DECLARADO: um regex não julga se a CONDIÇÃO está certa.
# `IF 1=1` passaria. O que este teste prende é a ausência de condicional
# nenhuma — que foi o defeito real encontrado (migration 010).
GUARDA = re.compile(r"^\s*(ELSE\s+)?IF\b", re.I)

# Idempotentes por construção — não precisam de bloco em volta.
POR_CONSTRUCAO = re.compile(r"CREATE\s+OR\s+ALTER|WHERE\s+NOT\s+EXISTS|^\s*MERGE\s", re.I)

ABRE_ROTINA = re.compile(
    r"^\s*(CREATE|ALTER)\s+(OR\s+ALTER\s+)?(PROC|PROCEDURE|FUNCTION|TRIGGER)\b", re.I)


def _limpar(texto: str) -> str:
    """Sem comentários.

    ⚠️ O comentário que documenta uma guarda CONTÉM a guarda, e o que documenta
    o defeito contém o defeito. É o falso positivo que este repo já pagou três
    vezes (`test_migration_nao_usa_indice_filtrado`, a varredura de classes de
    grade e a do `deploy_prod.sh`).
    """
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return "\n".join(re.sub(r"--.*$", "", linha) for linha in texto.splitlines())


def _instrucoes_desprotegidas(caminho: Path) -> list[tuple[int, str]]:
    """As instruções que rodariam duas vezes e quebrariam na segunda."""
    achados: list[tuple[int, str]] = []
    linhas = _limpar(caminho.read_text(encoding="utf-8", errors="replace")).splitlines()

    dentro_de_rotina = False
    pilha: list[bool] = []      # um item por BEGIN aberto; True = sob guarda
    guarda_pendente = False

    for numero, linha in enumerate(linhas, start=1):
        nu = linha.strip()
        if not nu:
            continue

        if re.fullmatch(r"GO", nu, re.I):
            # Fim do lote: o corpo da rotina acabou e o estado zera.
            dentro_de_rotina = False
            pilha, guarda_pendente = [], False
            continue

        if ABRE_ROTINA.match(nu):
            # O `CREATE OR ALTER PROC` em si é idempotente; o miolo é runtime.
            dentro_de_rotina = True
            continue
        if dentro_de_rotina:
            continue

        if GUARDA.search(nu):
            guarda_pendente = True

        protegida = any(pilha) or guarda_pendente
        if DDL.match(nu) and not POR_CONSTRUCAO.search(nu) and not protegida:
            achados.append((numero, nu[:80]))

        for palavra in re.findall(r"\b(BEGIN|END)\b", nu, re.I):
            if palavra.upper() == "BEGIN":
                pilha.append(guarda_pendente)
                guarda_pendente = False
            elif pilha:
                pilha.pop()

    return achados


def test_ha_migrations_para_analisar() -> None:
    """Um glob que não acha nada deixaria todos os outros testes verdes por
    vacuidade — a forma mais silenciosa de um teste deixar de existir."""
    assert len(MIGRACOES) >= 100, f"achei só {len(MIGRACOES)} migrations"


@pytest.mark.parametrize("caminho", MIGRACOES, ids=lambda p: p.name)
def test_a_migration_pode_rodar_duas_vezes(caminho: Path) -> None:
    """Cada instrução que cria ou insere precisa de uma guarda.

    Rodar de novo tem de ser um SKIP silencioso, não um erro — é isso que
    permite retomar um deploy interrompido sem decidir, no susto, "de onde
    continuar".
    """
    desprotegidas = _instrucoes_desprotegidas(caminho)
    assert not desprotegidas, (
        f"{caminho.name} quebra se rodar duas vezes:\n"
        + "\n".join(f"  linha {n}: {t}" for n, t in desprotegidas)
        + "\n\nEnvolva em `IF OBJECT_ID(...) IS NULL BEGIN … END`, "
          "`IF NOT EXISTS (SELECT 1 FROM sys.indexes …)` ou equivalente."
    )


def test_o_analisador_reconhece_uma_instrucao_sem_guarda(tmp_path: Path) -> None:
    """⚠️ O teste do teste. Um analisador que nunca acusa nada passa em todas
    as migrations e não prova nada — foi exatamente assim que uma varredura
    desta suíte já passou verde com o defeito de pé."""
    arquivo = tmp_path / "999_sem_guarda.sql"
    arquivo.write_text("CREATE TABLE dbo.etl_teste (id INT);\n", encoding="utf-8")
    assert _instrucoes_desprotegidas(arquivo)


def test_o_analisador_aceita_a_mesma_instrucao_com_guarda(tmp_path: Path) -> None:
    arquivo = tmp_path / "999_com_guarda.sql"
    arquivo.write_text(
        "IF OBJECT_ID('dbo.etl_teste', 'U') IS NULL\n"
        "BEGIN\n"
        "    CREATE TABLE dbo.etl_teste (id INT);\n"
        "    CREATE INDEX ix_teste ON dbo.etl_teste (id);\n"
        "END\n", encoding="utf-8")
    assert not _instrucoes_desprotegidas(arquivo)


def test_o_analisador_ignora_o_corpo_de_uma_procedure(tmp_path: Path) -> None:
    """Dentro da SP o INSERT é código de runtime — a pergunta de idempotência
    é sobre o `CREATE OR ALTER` que a define, não sobre o que ela executa."""
    arquivo = tmp_path / "999_proc.sql"
    arquivo.write_text(
        "CREATE OR ALTER PROCEDURE dbo.sp_teste AS\n"
        "BEGIN\n"
        "    INSERT INTO dbo.etl_teste (id) VALUES (1);\n"
        "END\n"
        "GO\n", encoding="utf-8")
    assert not _instrucoes_desprotegidas(arquivo)


def test_o_analisador_nao_se_engana_com_o_proprio_comentario(tmp_path: Path) -> None:
    """Comentário que documenta o padrão contém o padrão."""
    arquivo = tmp_path / "999_comentario.sql"
    arquivo.write_text(
        "-- Antes esta migration fazia CREATE TABLE dbo.etl_teste sem guarda.\n"
        "IF OBJECT_ID('dbo.etl_teste', 'U') IS NULL\n"
        "    CREATE TABLE dbo.etl_teste (id INT);\n", encoding="utf-8")
    assert not _instrucoes_desprotegidas(arquivo)
