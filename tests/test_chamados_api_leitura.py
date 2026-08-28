"""As rotas de leitura do módulo: dashboard, histórico, categorias, detalhe e anexo.

Portadas do módulo que roda em produção (F2 do porte).

O que estes testes prendem:

  1. **O dashboard conta o MESMO que a fila.** Produção recortava com
     `tipo != 'task'`, que descarta toda tarefa — inclusive a órfã, que a fila
     mostra como card. Com os dois convivendo, no dia em que aparecer uma órfã
     o painel diria um número e a tela ao lado outro, e ambos pareceriam
     certos. Aqui o recorte é `_so_trabalhos()`, o mesmo do resto do módulo.
  2. **Cada bloco se explica.** `label`, `cor`, `total` e a lista — número
     solto num painel obriga quem lê a adivinhar o critério.
  3. **O anexo só sai pelo chamado a que pertence.** A consulta exige o PAR
     (anexo, chamado): sem isso, quem tem um id de anexo baixa arquivo de
     chamado que não pode ver.
  4. **Espelho indisponível avisa, não mente.** Dizer "nenhuma nota" quando a
     consulta falhou é uma afirmação — e falsa.
  5. **A ordem das rotas.** `/chamados/indicadores/historico` tem dois
     segmentos e precisa vir ANTES de `/chamados/{sys_id}/...`: o FastAPI casa
     na ordem, e ali `indicadores` casaria com `{sys_id}`. A rota responderia
     200 com o corpo errado.

Nada toca banco: cursor dublê e `get_db_conn` substituído.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402
from routers import chamados as mod  # noqa: E402


class CursorFalso:
    def __init__(self, filas=None, explode=False, padrao=None):
        self.filas = list(filas or [])
        self.explode = explode
        # `padrao` é o que `fetchone` devolve quando não há fila preparada.
        # None reproduz "não achou" (é o que o teste de 404 precisa); uma
        # tupla deixa a rota seguir até o fim, que é o que os testes de
        # ESTRUTURA da consulta precisam — sem ela a rota morre no primeiro
        # `fetchone()[0]` e as consultas seguintes nunca são emitidas.
        self.padrao = padrao
        self.sqls: list[str] = []
        self._ultimo = ""

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self._ultimo = sql
        if self.explode:
            raise RuntimeError("Invalid object name 'dbo.etl_chamado_nota'")
        return self

    def fetchall(self):
        return self.filas.pop(0) if self.filas else []

    def fetchone(self):
        linhas = self.filas.pop(0) if self.filas else []
        if linhas:
            return linhas[0]
        # Dublê HONESTO: responde o TIPO que a pergunta pede. `SELECT CAST(
        # GETDATE() AS DATE)` recebe uma data — devolver 0 ali faz a rota
        # morrer em `fromisoformat('0')` e as consultas seguintes nunca são
        # emitidas, então o teste "a consulta X existe" passaria por não achar
        # o que também não foi executado.
        if self.padrao is not None and "GETDATE() AS DATE)" in getattr(self, "_ultimo", ""):
            return ("2026-08-28",)
        return self.padrao

    def close(self):
        pass


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "operador",
        "permissoes": ["tela_chamados"], "email": "fulano@caixa.gov.br"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": CursorFalso()}

    class ConexaoFalsa:
        def cursor(self):
            return estado["cur"]

        def close(self):
            pass

    monkeypatch.setattr(mod, "get_db_conn", lambda: ConexaoFalsa())
    return estado


@pytest.fixture
def banco_ate_o_fim(monkeypatch):
    """Como `banco`, mas com `fetchone` devolvendo `(0,)` em vez de None.

    Os testes que inspecionam QUAIS consultas a rota emite precisam que ela
    termine: com None, a rota morre no primeiro `fetchone()[0]` e as consultas
    seguintes nunca chegam a ser emitidas — o teste passaria por não achar o
    que também não foi executado.
    """
    estado = {"cur": CursorFalso(padrao=(0,))}

    class ConexaoFalsa:
        def cursor(self):
            return estado["cur"]

        def close(self):
            pass

    monkeypatch.setattr(mod, "get_db_conn", lambda: ConexaoFalsa())
    return estado


# ═══════════ 1. o dashboard usa o mesmo recorte da fila ═════════════════════

def test_o_dashboard_recorta_como_a_fila(cliente, banco):
    """`tipo != 'task'` descartaria a órfã, que a fila mostra como card."""
    cliente.get("/chamados/dashboard?visao=geral")
    sql = " ".join(banco["cur"].sqls)
    assert "_so_trabalhos" not in sql, "o predicado é interpolado, não literal"
    assert "pai_sys_id <> sys_id" in sql, (
        "o dashboard precisa do MESMO recorte do resto do módulo")
    assert "tipo != 'task'" not in sql and "tipo!='task'" not in sql, (
        "recorte de produção descarta toda tarefa, inclusive a órfã")


def test_todo_bloco_do_dashboard_se_explica(cliente, banco):
    corpo = cliente.get("/chamados/dashboard?visao=geral").json()
    blocos = [v for v in corpo.values() if isinstance(v, dict) and "total" in v]
    assert len(blocos) == 10, f"esperados 10 blocos, vieram {len(blocos)}"
    for b in blocos:
        assert b["label"], "número sem rótulo obriga a adivinhar o critério"
        assert b["cor"], "a cor é contrato da tela"
        assert isinstance(b["chamados"], list)


def test_a_visao_propria_filtra_pelo_email_de_quem_esta_logado(cliente, banco):
    """Por igualdade no e-mail, não por LIKE no nome.

    Nome do meio, abreviação e homônimo fazem o LIKE trazer chamado de outra
    pessoa — e quem olha o painel não tem como perceber.
    """
    cliente.get("/chamados/dashboard?visao=proprio")
    sql = " ".join(banco["cur"].sqls)
    assert "atribuido_a_email" in sql
    assert "LIKE" not in sql.upper().replace("LIKE 'FALHA:", "")


def test_visao_desconhecida_nao_derruba_o_painel(cliente, banco):
    r = cliente.get("/chamados/dashboard?visao=inventada")
    assert r.status_code == 200
    assert r.json()["visao"] == "inventada"


# ═══════════ 2. histórico de indicadores ════════════════════════════════════

@pytest.mark.parametrize("periodo", ["hoje", "30d", "historico"])
def test_o_historico_responde_nos_tres_periodos(cliente, banco, periodo):
    r = cliente.get(f"/chamados/indicadores/historico?periodo={periodo}")
    assert r.status_code == 200
    assert "snapshots" in r.json()


def test_a_rota_de_historico_nao_e_engolida_pela_de_detalhe(cliente, banco):
    """Se `/chamados/{sys_id}/...` viesse antes, `indicadores` casaria com
    `{sys_id}` e a resposta seria 200 com o corpo errado — sem erro nenhum."""
    corpo = cliente.get("/chamados/indicadores/historico").json()
    assert "snapshots" in corpo, "a rota do histórico foi engolida"
    assert "tasks" not in corpo


def test_o_periodo_nao_entra_cru_na_consulta(cliente, banco):
    """`periodo` decide o GROUP BY por if/elif, e o valor do usuário nunca
    chega ao SQL. Um valor inventado cai no ramo padrão."""
    cliente.get("/chamados/indicadores/historico?periodo=';DROP TABLE x--")
    sql = " ".join(banco["cur"].sqls)
    assert "DROP TABLE" not in sql.upper()


# ═══════════ 3. detalhe e anexo ═════════════════════════════════════════════

def test_o_anexo_so_sai_pelo_chamado_a_que_pertence(cliente, banco):
    """Sem o par (anexo, chamado), quem tem um id de anexo baixa arquivo de
    chamado que não pode ver."""
    cliente.get("/chamados/SID1/anexos/ANEXO1")
    sql = " ".join(banco["cur"].sqls)
    assert "sys_id_anexo=?" in sql and "sys_id_chamado=?" in sql


def test_anexo_inexistente_e_404_e_nao_500(cliente, banco):
    banco["cur"] = CursorFalso([[]])
    assert cliente.get("/chamados/SID1/anexos/NAOEXISTE").status_code == 404


def test_espelho_indisponivel_no_detalhe_avisa_em_vez_de_mentir(cliente, banco):
    banco["cur"] = CursorFalso(explode=True)
    r = cliente.get("/chamados/SID1/detalhe")
    assert r.status_code == 200
    assert r.json().get("migration_ausente") is True, (
        "sem a marca, a tela anuncia 'sem notas' — afirmação, e falsa")


# ═══════════ 4. categorias ══════════════════════════════════════════════════

def test_categorias_responde_lista(cliente, banco):
    r = cliente.get("/chamados/categorias")
    assert r.status_code == 200
    assert isinstance(r.json().get("categorias"), list)


def test_espelho_indisponivel_nas_categorias_avisa(cliente, banco):
    banco["cur"] = CursorFalso(explode=True)
    r = cliente.get("/chamados/categorias")
    assert r.status_code == 200
    assert r.json().get("migration_ausente") is True


# ═══════════ 5. o filtro por responsável dos Indicadores ════════════════════
# Pedido dos gestores: um filtro só, valendo para TODA a análise da aba.

def test_o_filtro_alcanca_todas_as_agregacoes(cliente, banco_ate_o_fim):
    """Filtro que alcança metade das contas é pior que filtro nenhum.

    A aba mostraria o aging de uma pessoa ao lado do fluxo de todas, com os
    dois números parecendo certos — a mesma armadilha da Fila × Indicadores
    que a F5 fechou, só que dentro da mesma tela.
    """
    cliente.get("/chamados/indicadores?responsavel=Fulano")
    sobre_o_espelho = [s for s in banco_ate_o_fim["cur"].sqls
                       if "dbo.etl_chamado" in s and "GETDATE()) AS DATE)" not in s]
    sem_filtro = [s for s in sobre_o_espelho
                  if "WHERE ativo = 1" in s and "atribuido_a = ?" not in s
                  # a consulta das OPÇÕES do seletor é a única que não filtra,
                  # de propósito: com o filtro, o seletor ficaria com uma opção
                  # só e não haveria como trocar
                  and "GROUP BY NULLIF(LTRIM(RTRIM(atribuido_a))" not in s]
    assert not sem_filtro, (
        "estas consultas ignoram o filtro e falariam da fila inteira:\n" +
        "\n".join(f"  {s[:80]}…" for s in sem_filtro[:5]))


def test_sem_responsavel_e_um_balde_filtravel(cliente, banco_ate_o_fim):
    """É o que o gestor procura primeiro: o que ninguém pegou.

    Comparar com a string "sem responsável" não acharia ninguém — ela é
    rótulo da tela, e o banco guarda NULL ou vazio.
    """
    cliente.get("/chamados/indicadores?responsavel=sem responsável")
    sql = " ".join(banco_ate_o_fim["cur"].sqls)
    assert "NULLIF(LTRIM(RTRIM(atribuido_a)), '') IS NULL" in sql
    assert "atribuido_a = ?" not in sql, (
        "'sem responsável' é condição, não valor — comparar por igualdade "
        "devolveria zero sempre")


def test_as_opcoes_do_seletor_nao_encolhem_com_a_escolha(cliente, banco_ate_o_fim):
    """Com o filtro aplicado nelas, a tela prenderia quem analisa na escolha
    que acabou de fazer: uma opção só, sem como voltar."""
    cliente.get("/chamados/indicadores?responsavel=Fulano")
    opcoes = [s for s in banco_ate_o_fim["cur"].sqls
              if "GROUP BY NULLIF(LTRIM(RTRIM(atribuido_a))" in s]
    assert opcoes, "a consulta das opções sumiu"
    assert "atribuido_a = ?" not in opcoes[0]


def test_a_resposta_diz_qual_filtro_esta_em_vigor(cliente, banco):
    """Número filtrado sem aviso vira 'a fila tem 16 chamados' num print."""
    corpo = cliente.get("/chamados/indicadores?responsavel=Fulano").json()
    assert corpo["responsavel"] == "Fulano"
    assert cliente.get("/chamados/indicadores").json()["responsavel"] is None


def test_espaco_em_branco_nao_vira_filtro(cliente, banco_ate_o_fim):
    """`?responsavel=%20` filtraria por ninguém e devolveria zero em tudo."""
    corpo = cliente.get("/chamados/indicadores?responsavel=%20%20").json()
    assert corpo["responsavel"] is None
    assert "atribuido_a = ?" not in " ".join(banco_ate_o_fim["cur"].sqls)
