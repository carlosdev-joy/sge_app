"""Ferramenta de consulta a banco dos agentes da tela — integração (C1 de
docs/spec-agentes-ferramenta-banco.md). As camadas do SQL estão em
test_agentes_sql.py; aqui:

  1. **Cadastro** — ferramenta de banco ⇔ pelo menos um par; máscara ligada
     por padrão; linha editada à mão não amplia; sem a migration 122 o agente
     fica sem banco (fecha, não abre) e gravar banco pede a 122.
  2. **Acesso (C3)** — por perfil vale com a ferramenta de banco, não com
     `dsjob`/`isx_extrair`/`dsx_consulta`.
  3. **Rotas do admin** — pares NOVOS conferidos no servidor (os que não
     mudaram, não), avisos de escrita, conexões e bancos sem login.
  4. **Prompt** — pares por nome, regras de consulta, a linha do DataStage só
     com ferramenta de DataStage.
  5. **Execução** — par fora do agente é indisponível sem conectar; o SQL
     EXECUTADO fica intacto no artefato (nunca as linhas); recusa sem guarda;
     inexistente entra na guarda da conversa; ferramenta fora do agente é
     recusada antes do despachante.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

from services import agentes as svc  # noqa: E402
from services import agentes_aprendizado as ap  # noqa: E402
from services import agentes_registro as reg  # noqa: E402
from services import agentes_sql as asql  # noqa: E402
from tests.test_agentes_cadastro import PERFIS, _corpo, _linha, _user, cadastro  # noqa: E402,F401 — fixture
from tests.test_agentes_execucao import _conversar, _pedido, _Provedor  # noqa: E402

BANCO = ("banco_estrutura", "banco_consulta")
PAR = {"conexao": "dw_prod", "banco": "PREV"}


def _linha_banco(*, ferramentas=BANCO, bancos=(PAR,), mascarar=1, acesso="perfil", **kw):
    return _linha(ferramentas=ferramentas, acesso=acesso, **kw) + (json.dumps(list(bancos)), mascarar)


# ═══════════ 1. cadastro ══════════════════════════════════════════════════

def test_criacao_com_banco_exige_par_e_liga_a_mascara():
    campos = reg.validar_criacao(_corpo(ferramentas=list(BANCO), bancos=[PAR, dict(PAR)]), PERFIS)
    assert campos["bancos"] == [("dw_prod", "PREV")] and campos["mascarar_dados"] is True
    assert campos["ferramentas"] == list(BANCO)  # sem resolver_projeto: não depende de projeto
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(ferramentas=["banco_consulta"]), PERFIS)
    assert e.value.code == "bancos_obrigatorios"
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(bancos=[PAR]), PERFIS)
    assert e.value.code == "bancos_sem_ferramenta"


@pytest.mark.parametrize("bancos", ["dw/PREV", [{"conexao": "dw"}], [{"conexao": " ", "banco": "X"}],
                                    [{"conexao": 1, "banco": "X"}], [{"conexao": "c" * 101, "banco": "X"}],
                                    [{"conexao": "c", "banco": f"b{i}"} for i in range(51)]])
def test_bancos_com_formato_invalido(bancos):
    with pytest.raises(reg.AgenteInvalido):
        reg.validar_criacao(_corpo(ferramentas=["banco_consulta"], bancos=bancos), PERFIS)


def test_mascarar_so_booleano():
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(ferramentas=list(BANCO), bancos=[PAR], mascarar_dados="nao"), PERFIS)
    assert e.value.code == "mascarar_invalido"
    campos = reg.validar_criacao(_corpo(ferramentas=list(BANCO), bancos=[PAR], mascarar_dados=False), PERFIS)
    assert campos["mascarar_dados"] is False


def test_alteracao_tirar_a_ferramenta_limpa_os_pares():
    atual = reg.do_banco(_linha_banco(acesso="manual"))
    novo = reg.validar_alteracao(atual, {"ferramentas": [], "bancos": []}, PERFIS)
    assert novo["bancos"] == [] and novo["mascarar_dados"] is True
    with pytest.raises(reg.AgenteInvalido):
        reg.validar_alteracao(atual, {"bancos": []}, PERFIS)  # ferramenta sem par
    assert reg.pares_novos(atual, reg.validar_alteracao(atual, {"nome": "Outro"}, PERFIS)) == []
    novo = reg.validar_alteracao(atual, {"bancos": [PAR, {"conexao": "dw_prod", "banco": "VIDA"}]}, PERFIS)
    assert reg.pares_novos(atual, novo) == [("dw_prod", "VIDA")]


def test_tela_de_antes_da_c2_nao_apaga_os_bancos():
    """Revisão da C1: a tela atual reenvia `ferramentas` só com as de
    DataStage a cada edição — renomear apagava a consulta a banco."""
    atual = reg.do_banco(_linha_banco(acesso="manual"))
    novo = reg.validar_alteracao(atual, {"nome": "Outro", "ferramentas": ["base"]}, PERFIS)
    assert set(BANCO) <= set(novo["ferramentas"]) and novo["bancos"] == [("dw_prod", "PREV")]
    assert "resolver_projeto" in novo["ferramentas"]
    novo = reg.validar_alteracao(atual, {"ferramentas": [], "bancos": []}, PERFIS)  # tirar de propósito
    assert novo["ferramentas"] == [] and novo["bancos"] == []


def test_linha_editada_a_mao_nao_amplia():
    ag = reg.do_banco(_linha_banco(bancos=()))  # ferramenta sem par: a ferramenta sai
    assert ag["ferramentas"] == () and ag["bancos"] == ()
    ag = reg.do_banco(_linha_banco(ferramentas=(), bancos=(PAR,)))  # par sem ferramenta: o par sai
    assert ag["bancos"] == ()
    ag = reg.do_banco(_linha_banco(bancos=("lixo", {"conexao": "x"}, PAR, PAR)))
    assert ag["bancos"] == (("dw_prod", "PREV"),)
    ag = reg.do_banco(_linha_banco()[:11] + ("{nao json", None))
    assert ag["ferramentas"] == () and ag["mascarar_dados"] is True


def test_sem_a_122_o_agente_fica_sem_banco():
    ag = reg.do_banco(_linha(ferramentas=BANCO))  # 11 colunas: leitura antiga
    assert ag["ferramentas"] == () and ag["bancos"] == () and ag["mascarar_dados"] is True


class _CursorSem122:
    """Cursor em que as colunas da 122 não existem (erro 207)."""

    def __init__(self, linhas=()):
        self.linhas, self.execs = list(linhas), []

    def execute(self, sql, params=None):
        self.execs.append(sql)
        if "bancos_json" in sql or "mascarar_dados" in sql:
            raise RuntimeError("42S22", "[42S22] Invalid column name 'bancos_json'. (207)")

    def fetchall(self):
        return self.linhas

    def fetchone(self):
        return self.linhas[0] if self.linhas else None


def test_leitura_cai_para_as_colunas_antigas():
    cur = _CursorSem122([_linha("assistente", ferramentas=BANCO)])
    agentes = reg.carregar(cur)
    assert agentes["assistente"]["ferramentas"] == () and len(cur.execs) == 2
    assert reg.um(_CursorSem122([_linha("assistente")]), "assistente")["id"] == "assistente"


def test_gravar_banco_sem_a_122_pede_a_migration():
    conn = MagicMock()
    campos = reg.validar_criacao(_corpo(ferramentas=list(BANCO), bancos=[PAR]), PERFIS)
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.criar(conn, _CursorSem122(), campos, "ADM1")
    assert e.value.code == "migracao_pendente" and e.value.status == 503
    novo = reg.validar_alteracao(reg.do_banco(_linha()), {"nome": "Novo"}, PERFIS)
    cur = _CursorSem122()
    reg.alterar(conn, cur, "assistente", novo, "ADM1")  # sem banco: grava pelas colunas antigas
    assert "bancos_json" not in cur.execs[-1]


# ═══════════ 2. acesso (C3) ═══════════════════════════════════════════════

def test_por_perfil_vale_com_banco_e_nao_com_servidor():
    campos = reg.validar_criacao(_corpo(acesso="perfil", ferramentas=list(BANCO), bancos=[PAR]), PERFIS)
    assert campos["acesso"] == "perfil"
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(acesso="perfil", ferramentas=list(BANCO) + ["dsjob"], bancos=[PAR]), PERFIS)
    assert e.value.code == "acesso_perfil_com_servidor"
    ag = reg.do_banco(_linha_banco(acesso="perfil"))
    assert ag["acesso"] == "perfil"
    assert svc.motivo_sem_acesso(_user("desenvolvedor"), ag) is None
    assert svc.motivo_sem_acesso(_user("consulta"), ag) is not None


# ═══════════ 3. rotas do admin ════════════════════════════════════════════

def test_criar_confere_os_pares_e_devolve_os_avisos(cadastro):
    cliente, banco, _ = cadastro
    with patch.object(asql, "verificar_pares", return_value=["o login pode gravar"]) as v:
        r = cliente.post("/agentes/admin/agentes", json=_corpo(ferramentas=list(BANCO), bancos=[PAR]))
    assert r.status_code == 200, r.text
    v.assert_called_once_with([("dw_prod", "PREV")])
    corpo = r.json()
    assert corpo["avisos"] == ["o login pode gravar"]
    assert corpo["agente"]["bancos"] == [PAR] and corpo["agente"]["mascarar_dados"] is True
    assert corpo["agente"]["ferramentas"] == list(BANCO)
    lista = cliente.get("/agentes/admin/agentes").json()
    assert lista["ferramentas_banco"] == list(BANCO) and lista["ferramentas"] == list(svc.FERRAMENTAS_DATASTAGE)


def test_par_que_nao_confere_nao_grava(cadastro):
    cliente, banco, _ = cadastro
    with patch.object(asql, "verificar_pares", side_effect=ValueError("sem SHOWPLAN no banco 'PREV'")):
        r = cliente.post("/agentes/admin/agentes", json=_corpo(ferramentas=list(BANCO), bancos=[PAR]))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "banco_indisponivel"
    assert "SHOWPLAN" in r.json()["detail"]["message"]
    assert banco.agentes_db == {} and banco.prompts == []


def test_alterar_so_confere_o_par_novo(cadastro):
    cliente, banco, _ = cadastro
    with patch.object(asql, "verificar_pares", return_value=[]):
        cliente.post("/agentes/admin/agentes", json=_corpo(ferramentas=list(BANCO), bancos=[PAR]))
    with patch.object(asql, "verificar_pares", side_effect=AssertionError("não devia conferir")):
        r = cliente.put("/agentes/admin/agentes/assistente", json={"nome": "Renomeado"})
    assert r.status_code == 200 and r.json()["agente"]["bancos"] == [PAR]
    novo = {"conexao": "dw_prod", "banco": "VIDA"}
    with patch.object(asql, "verificar_pares", return_value=[]) as v:
        r = cliente.put("/agentes/admin/agentes/assistente", json={"bancos": [PAR, novo], "mascarar_dados": False})
    v.assert_called_once_with([("dw_prod", "VIDA")])
    assert r.json()["agente"]["bancos"] == [PAR, novo] and r.json()["agente"]["mascarar_dados"] is False


def test_conexoes_e_bancos_sem_login(cadastro, monkeypatch):
    cliente, _, estado = cadastro
    monkeypatch.setattr(asql, "listar_conexoes", lambda cur: [{"conexao": "dw_prod", "servidor": "h,1433",
                                                               "descricao": None}])
    assert cliente.get("/agentes/admin/conexoes").json() == {
        "conexoes": [{"conexao": "dw_prod", "servidor": "h,1433", "descricao": None}]}
    monkeypatch.setattr(asql, "bancos_da_conexao", lambda c: {
        "bancos": [{"banco": "PREV", "showplan": True, "escrita": True}], "sysadmin": False})
    r = cliente.get("/agentes/admin/conexoes/dw_prod/bancos").json()
    assert r["bancos"][0]["escrita"] is True and "login" not in json.dumps(r)

    def _cai(c):
        raise asql.BancoIndisponivel("conexão indisponível")
    monkeypatch.setattr(asql, "bancos_da_conexao", _cai)
    r = cliente.get("/agentes/admin/conexoes/nao_existe/bancos")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "banco_indisponivel"
    estado["perms"] = ["tela_agentes"]
    assert cliente.get("/agentes/admin/conexoes").status_code == 403


def test_listar_conexoes_so_mssql_e_sem_login():
    cur = MagicMock()
    cur.fetchall.return_value = [("dw_prod", "10.0.0.5", None, "DW"), ("kiprev", "h2", 1444, None)]
    assert asql.listar_conexoes(cur) == [{"conexao": "dw_prod", "servidor": "10.0.0.5", "descricao": "DW"},
                                         {"conexao": "kiprev", "servidor": "h2,1444", "descricao": None}]
    sql = cur.execute.call_args[0][0]
    assert "login" not in sql and "senha" not in sql and "mssql" in sql


# ═══════════ 4. prompt ════════════════════════════════════════════════════

def test_prompt_de_banco():
    antes, depois = svc.partes_fixas(None, False, BANCO, (("dw_prod", "PREV"), ("dw_prod", "VIDA")))
    assert antes == ""  # nada depende de projeto
    assert "Bancos liberados (conexao/banco): dw_prod/PREV, dw_prod/VIDA." in depois
    assert "Você só consulta: nunca executa nem sugere escrita" in depois
    assert "num bloco ```sql" in depois and "Nunca apresente como dado" in depois
    assert "DataStage" not in depois and "## Propostas" not in depois
    assert "Nunca peça, repita nem proponha senha" in depois


def test_prompt_misto_tem_as_duas_regras():
    _, depois = svc.partes_fixas("P", False, ("resolver_projeto", "dsjob", "banco_consulta"), (("c", "b"),))
    assert "Você NUNCA altera o DataStage" in depois and "Você só consulta" in depois
    assert "banco_estrutura {" not in depois and "banco_consulta {" in depois
    assert "## Propostas" in depois


# ═══════════ 5. execução ══════════════════════════════════════════════════

@pytest.fixture
def sem_aprendizado(monkeypatch):
    registrados = []
    monkeypatch.setattr(svc, "_recuperar_seguro", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_registrar_seguro", lambda _a, a, agente="": registrados.append(a))
    monkeypatch.setattr(svc, "_erro_conhecido_seguro", lambda *a, **k: None)
    return registrados


def _executou(monkeypatch, retorno=None, erro=None):
    chamadas = []

    def _consultar(conexao, banco, sql, **kw):
        chamadas.append((conexao, banco, sql, kw))
        if erro is not None:
            raise erro
        return retorno or {"sql": sql, "texto": "n\n3", "colunas": ["n"], "linhas": [(3,)],
                           "havia_mais": False, "ms": 12}
    monkeypatch.setattr(asql, "consultar", _consultar)
    return chamadas


@pytest.mark.asyncio
async def test_consulta_grava_o_sql_intacto_e_nunca_as_linhas(monkeypatch, sem_aprendizado):
    sql = "SELECT COUNT(*) n FROM dbo.usuario u WHERE u.token_expira > GETDATE()"
    chamadas = _executou(monkeypatch)
    p = _Provedor([_pedido("banco_consulta", conexao="dw_prod", banco="prev", sql=sql),
                   "São 3.\n```sql\n" + sql + "\n```"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=BANCO,
                         bancos=(("dw_prod", "PREV"),), mascarar=False)
    assert r["status"] == "ok"
    [(conexao, banco, sql_rodado, kw)] = chamadas
    assert (conexao, banco, sql_rodado) == ("dw_prod", "PREV", sql)  # banco sem diferenciar maiúsculas
    assert kw["bancos_da_conexao"] == {"PREV"} and kw["mascarar"] is False and kw["timeout_s"] <= 30
    [art] = r["artefatos"]
    assert art["args"] == {"conexao": "dw_prod", "banco": "PREV", "sql": sql}  # sem redigir()
    assert art["banco"] == {"conexao": "dw_prod", "banco": "PREV", "linhas": 1, "havia_mais": False, "ms": 12}
    assert "n\t" not in json.dumps(art) and "\\n3" not in json.dumps(art)
    assert "<ferramenta nome=\"banco_consulta\">\nn\n3\n</ferramenta>" in p.chamadas[1]["historico"][-1]["content"]


@pytest.mark.asyncio
async def test_par_fora_do_agente_nao_conecta(monkeypatch, sem_aprendizado):
    chamadas = _executou(monkeypatch)
    p = _Provedor([_pedido("banco_consulta", conexao="outra", banco="PREV", sql="SELECT 1"), "ok"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=BANCO, bancos=(("dw_prod", "PREV"),))
    assert chamadas == []
    assert "Banco indisponível para este agente. Bancos liberados: dw_prod/PREV." in (
        p.chamadas[1]["historico"][-1]["content"])
    assert r["artefatos"][0]["args"]["conexao"] == "outra" and "banco" not in r["artefatos"][0]


@pytest.mark.asyncio
async def test_um_par_so_dispensa_os_argumentos(monkeypatch, sem_aprendizado):
    chamadas = _executou(monkeypatch)
    p = _Provedor([_pedido("banco_consulta", sql="SELECT 1"), "ok"])
    await _conversar(monkeypatch, p, agente="assistente", ferramentas=BANCO, bancos=(("dw_prod", "PREV"),))
    assert chamadas[0][:2] == ("dw_prod", "PREV")


@pytest.mark.asyncio
async def test_recusa_nao_entra_na_guarda(monkeypatch, sem_aprendizado):
    _executou(monkeypatch, erro=asql.SqlRecusado("só SELECT"))
    p = _Provedor([_pedido("banco_consulta", sql="DELETE FROM t"), "ok"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=BANCO, bancos=(("dw_prod", "PREV"),))
    [art] = r["artefatos"]
    assert "falhou" not in art and art["banco"]["recusada"] is True
    assert art["args"]["sql"] == "DELETE FROM t"  # não executou: vai pelo caminho redigido de sempre
    assert "Consulta recusada: só SELECT." in p.chamadas[1]["historico"][-1]["content"]
    assert sem_aprendizado == []


@pytest.mark.asyncio
async def test_inexistente_entra_na_guarda_e_vira_aprendizado(monkeypatch, sem_aprendizado):
    erro = RuntimeError("42S02", "[42S02] [Microsoft][ODBC Driver 18][SQL Server]Invalid object name "
                                 "'dbo.nao'. (208) host=10.0.0.5 login=svc")
    _executou(monkeypatch, erro=erro)
    p = _Provedor([_pedido("banco_consulta", sql="SELECT * FROM dbo.nao"),
                   _pedido("banco_consulta", sql="SELECT * FROM dbo.nao"), "ok"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=BANCO, bancos=(("dw_prod", "PREV"),))
    primeiro, segundo = r["artefatos"]
    assert primeiro["falhou"] == "banco_objeto_inexistente" and segundo.get("repetida") is True
    visto = p.chamadas[1]["historico"][-1]["content"]
    assert "tabela ou objeto inexistente: dbo.nao" in visto and "10.0.0.5" not in visto and "svc" not in visto
    [aprendizado] = sem_aprendizado
    assert aprendizado["titulo"] == "Tabela ou coluna inexistente no banco — banco dw_prod/PREV"
    assert "10.0.0.5" not in aprendizado["evidencia"] and "Microsoft" not in aprendizado["evidencia"]


@pytest.mark.asyncio
async def test_indisponivel_e_mensagem_fixa(monkeypatch, sem_aprendizado):
    _executou(monkeypatch, erro=asql.BancoIndisponivel("conexão indisponível"))
    p = _Provedor([_pedido("banco_estrutura", filtro="x"), "ok"])
    monkeypatch.setattr(asql, "estrutura", lambda *a, **k: (_ for _ in ()).throw(
        asql.BancoIndisponivel("conexão indisponível")))
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=BANCO, bancos=(("dw_prod", "PREV"),))
    assert "conexão indisponível — avise o usuário" in p.chamadas[1]["historico"][-1]["content"]
    assert "falhou" not in r["artefatos"][0]


@pytest.mark.asyncio
async def test_ferramenta_de_banco_fora_do_agente_e_recusada(monkeypatch, sem_aprendizado):
    chamadas = _executou(monkeypatch)
    p = _Provedor([_pedido("banco_consulta", sql="SELECT 1"), "ok"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=("resolver_projeto", "base"))
    assert chamadas == [] and r["artefatos"][0]["recusada"] == "fora_do_agente"


@pytest.mark.asyncio
async def test_agente_so_de_banco_nao_cai_em_so_conversa(monkeypatch, sem_aprendizado):
    _executou(monkeypatch)
    p = _Provedor([_pedido("banco_consulta", sql="SELECT 1"), "ok"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=("banco_consulta",),
                         bancos=(("dw_prod", "PREV"),))
    assert len(p.chamadas) == 2 and r["artefatos"][0]["ferramenta"] == "banco_consulta"
    assert "Ferramentas disponíveis: banco_consulta." in p.chamadas[0]["sistema"]


def test_chave_da_consulta_nao_depende_do_projeto():
    args = {"conexao": "c", "banco": "b", "sql": "SELECT 1", "extra": "ignorado"}
    assert ap.chave_da_chamada("banco_consulta", args, "P1") == ap.chave_da_chamada(
        "banco_consulta", {k: v for k, v in args.items() if k != "extra"}, None)


def test_progresso():
    assert svc.texto_de_progresso("banco_consulta", {}, None) == "Consultando o banco…"
    assert svc.texto_de_progresso("banco_estrutura", {}, None) == "Lendo a estrutura do banco…"


@pytest.mark.asyncio
async def test_vaga_so_volta_quando_a_consulta_termina(monkeypatch):
    import asyncio
    import threading
    monkeypatch.setattr(svc, "_VAGAS_BANCO", None)
    monkeypatch.setattr(svc, "MAX_CONSULTAS_BANCO", 1)
    solta = threading.Event()

    def _lenta():
        solta.wait(5)
        return "ok"
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(svc._na_vaga(_lenta), timeout=0.05)
    vagas = svc._vagas_banco()
    assert vagas.locked()  # a thread ainda roda: a vaga não voltou
    solta.set()
    for _ in range(100):
        if not vagas.locked():
            break
        await asyncio.sleep(0.02)
    assert not vagas.locked()
    assert await svc._na_vaga(lambda: 7) == 7
