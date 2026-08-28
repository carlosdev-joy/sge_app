"""As migrations do módulo ServiceNow: idempotentes, completas e sem armadilha.

As nove tabelas do módulo foram criadas **direto no banco de produção**, sem
migration. As 094–098 vieram da linhagem local do servidor; a 099
(`etl_sn_categoria`) não existia em lugar nenhum e foi escrita a partir do
schema REAL — não deduzida das queries, porque schema deduzido aceita os
`SELECT` de hoje e quebra no primeiro dado fora do formato imaginado.

O que estes testes prendem:

  1. **Toda migration é idempotente.** Em produção as tabelas JÁ existem: uma
     migration sem guarda abortaria o deploy na etapa 6c, com a API antiga no
     ar e o operador sem saber se pode repetir.
  2. **Nenhuma usa índice filtrado.** `CREATE INDEX ... WHERE` falha no sqlcmd
     por QUOTED_IDENTIFIER e, se criado assim, quebra TODO DML da tabela pelo
     sqlcmd enquanto o pymssql da DAG segue verde — falso verde de manual.
  3. **As dez tabelas estão cobertas.** Faltar uma só aparece quando a rota que
     a usa responde 500 em produção.
  4. **A numeração não retrocede** dentro da nossa linhagem.

⚠️ Isto é contrato do FONTE. A prova de que o T-SQL executa está no ambiente
dev, onde as seis foram aplicadas, tiveram o registro apagado e foram
**reaplicadas sobre o banco já populado** — o cenário de produção — sem erro.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
DIR = RAIZ / "sql" / "migrations"

# As migrations que este porte trouxe.
DO_MODULO = ["094_chamados_nota_anexo", "095_chamados_anexo",
             "096_chamado_ciclo", "097_indicador_snapshot",
             "098_sn_grupo_gatilho", "099_sn_categoria"]

# Toda tabela que o código do módulo consulta. A lista é a pergunta que
# importa: "existe migration para tudo que o router e o sync abrem?"
TABELAS = ["etl_chamado_anexo", "etl_chamado_ciclo", "etl_chamado_nota",
           "etl_indicador_meta", "etl_indicador_snapshot",
           "etl_indicador_snapshot_analista", "etl_indicador_snapshot_grupo",
           "etl_servicenow_grupo", "etl_servicenow_gatilho",
           "etl_sn_categoria"]


def _texto(nome: str) -> str:
    arq = DIR / f"{nome}.sql"
    assert arq.is_file(), f"{nome}.sql sumiu de sql/migrations/"
    return arq.read_text(encoding="utf-8")


def _sem_comentarios(sql: str) -> str:
    """Só o SQL que o servidor executa.

    Sem isto, um comentário que ADVIRTA contra um padrão faz o teste reprovar
    a migration que segue o conselho — foi o que aconteceu na primeira versão
    deste arquivo, com a 099 explicando por que NÃO usa índice filtrado.
    """
    return "\n".join(re.sub(r"--.*$", "", linha) for linha in sql.splitlines())


@pytest.mark.parametrize("nome", DO_MODULO)
def test_migration_e_idempotente(nome: str) -> None:
    """Sem guarda, a segunda execução aborta o deploy no meio."""
    sql = _sem_comentarios(_texto(nome))
    blocos_create = len(re.findall(r"CREATE\s+TABLE", sql, re.I))
    guardas = len(re.findall(r"IF\s+OBJECT_ID\([^)]*\)\s*IS\s+NULL", sql, re.I))
    assert blocos_create <= guardas, (
        f"{nome}: {blocos_create} CREATE TABLE para {guardas} guardas "
        f"IF OBJECT_ID(...) IS NULL — em produção as tabelas já existem")

    for alter in re.findall(r"ALTER\s+TABLE[^;]*ADD\s+(\w+)", sql, re.I):
        assert re.search(r"INFORMATION_SCHEMA\.COLUMNS|sys\.columns", sql, re.I), (
            f"{nome}: ALTER TABLE ... ADD {alter} sem checar se a coluna existe")


@pytest.mark.parametrize("nome", DO_MODULO)
def test_migration_nao_usa_indice_filtrado(nome: str) -> None:
    """`CREATE INDEX ... WHERE` quebra o sqlcmd — e só o sqlcmd.

    O pymssql da DAG continua funcionando, então o defeito aparece como
    "o deploy falha" e não como "o índice está errado".
    """
    sql = _sem_comentarios(_texto(nome))
    for trecho in re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX.*?(?:;|\bGO\b)",
                             sql, re.I | re.S):
        assert not re.search(r"\bWHERE\b", trecho, re.I), (
            f"{nome}: índice filtrado — falha no sqlcmd por QUOTED_IDENTIFIER "
            f"e, se criado, quebra todo DML da tabela por esse caminho")


@pytest.mark.parametrize("tabela", TABELAS)
def test_toda_tabela_do_modulo_tem_migration(tabela: str) -> None:
    """Faltar uma só aparece quando a rota responde 500 em produção."""
    todas = "\n".join(_sem_comentarios(_texto(n)) for n in DO_MODULO)
    assert re.search(rf"CREATE\s+TABLE\s+dbo\.{tabela}\b", todas, re.I), (
        f"{tabela} é usada pelo código e não é criada por migration nenhuma")


def test_a_numeracao_nao_retrocede() -> None:
    numeros = sorted(int(n[:3]) for n in DO_MODULO)
    assert numeros == list(range(94, 94 + len(DO_MODULO))), (
        f"numeração com lacuna ou repetição: {numeros}")

    anteriores = sorted(int(p.name[:3]) for p in DIR.glob("0*.sql")
                        if p.name[:3].isdigit() and int(p.name[:3]) < 94)
    assert max(anteriores) == 93, (
        "a linhagem anterior não termina na 093 — a numeração deste porte "
        "precisa ser revista antes de colidir com outra")


def test_o_conjunto_do_modulo_esta_completo() -> None:
    """Piso: se alguém acrescentar migration do módulo sem citá-la aqui, este
    teste some do radar — a lista precisa acompanhar o diretório."""
    no_disco = {p.stem for p in DIR.glob("09[4-9]_*.sql")}
    assert no_disco == set(DO_MODULO), (
        f"sql/migrations tem {sorted(no_disco - set(DO_MODULO))} a mais e "
        f"{sorted(set(DO_MODULO) - no_disco)} a menos que esta lista")
