"""Agente Terminal, F5 — integração (spec docs/spec-agente-terminal.md): DataStage ao vivo e banco no Terminal, resultado das leituras
no artefato da conversa, servidores, bancos do Terminal no Admin, retenção da auditoria (decisão do usuário: 180 dias, purga automática)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from api.main import app as _app  # noqa: F401,E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_terminal as aterm  # noqa: E402
from services import agentes_terminal_ssh as tssh  # noqa: E402
from tests.test_agente_terminal_fundacao import _Conn, _Cur  # noqa: E402
from tests.test_agentes_execucao import _conversar, _pedido, _Provedor  # noqa: E402

TERMINAL = svc.CATALOGO["terminal"]
PAR = '[{"conexao": "dw", "banco": "PREV"}]'


# ═══════════ 1. ferramentas do Terminal ════════════════════════════════

def test_terminal_tem_datastage_ao_vivo_banco_e_servidor():
    assert TERMINAL["ferramentas"] == ("resolver_projeto", "dsjob", "banco_estrutura", "banco_consulta", "servidor_exec")
    assert "isx_extrair" not in TERMINAL["ferramentas"] and "dsx_consulta" not in TERMINAL["ferramentas"]


def test_sem_par_de_banco_as_ferramentas_de_banco_saem():
    sem = svc.agente_terminal_para_conversa(TERMINAL, {})
    assert sem["ferramentas"] == ("resolver_projeto", "dsjob", "servidor_exec") and sem["bancos"] == ()
    com = svc.agente_terminal_para_conversa(TERMINAL, {"agente_terminal_bancos": PAR, "agente_terminal_mascarar": "0"})
    assert "banco_consulta" in com["ferramentas"] and com["bancos"] == (("dw", "PREV"),) and com["mascarar_dados"] is False
    assert svc.agente_terminal_para_conversa(TERMINAL, {"agente_terminal_bancos": PAR})["mascarar_dados"] is True, "mascarar por padrão"


@pytest.mark.parametrize("lixo", ["", "nao json", "{}", '[{"conexao": 1}]', '[{"conexao": "", "banco": "x"}]', "[1,2]", "null",
                                  '[{"conexao": "' + "c" * 300 + '", "banco": "b"}]'])
def test_config_de_bancos_com_lixo_fecha(lixo):
    assert svc.bancos_do_terminal({"agente_terminal_bancos": lixo}) == ()


def test_pares_repetidos_contam_uma_vez():
    v = '[{"conexao":"dw","banco":"PREV"},{"conexao":" dw ","banco":"PREV "}]'
    assert svc.bancos_do_terminal({"agente_terminal_bancos": v}) == (("dw", "PREV"),)


@pytest.mark.parametrize("valor,esperado", [("180", 180), ("30", 30), ("3650", 3650), ("29", 180), ("9999", 180), ("x", 180), (None, 180)])
def test_retencao_dentro_da_faixa(valor, esperado):
    assert svc.retencao_terminal_dias({"agente_terminal_retencao_dias": valor} if valor is not None else {}) == esperado


def test_prompt_composto_do_terminal():
    ag = svc.agente_terminal_para_conversa(TERMINAL, {"agente_terminal_bancos": PAR})
    antes, depois = svc.partes_fixas(None, False, ag["ferramentas"], ag["bancos"])
    assert "AINDA NÃO tem um projeto DataStage" in antes, "contexto do projeto (dsjob depende dele)"
    assert "Comandos do dsjob disponíveis" in depois and "servidor_exec {" in depois and "Bancos liberados" in depois
    assert "Você lê o servidor sozinho" in depois and "Pelo `dsjob` você só LÊ o DataStage" in depois
    assert "Você só consulta: nunca executa nem sugere escrita no banco" in depois
    assert "## Propostas" not in depois and "Você NUNCA altera o DataStage" not in depois


# ═══════════ 2. o resultado das leituras chega à tela ══════════════════

@pytest.fixture
def servidor(monkeypatch):
    srv = tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", None, None, None, ("/opt", "/var/log"))
    monkeypatch.setattr(tssh, "servidores", lambda: {"airflow": srv})
    return srv


def _abrir():
    cur = MagicMock(rowcount=1)
    return MagicMock(), cur


def test_leitura_devolve_o_bloco_redigido_e_cortado_para_a_tela(monkeypatch, servidor):
    async def _exec(*a, **k):
        return tssh.ResultadoExec("linha ok\npassword: hunter2\n" + "x" * 9000, "", 0, False, False, 7)
    monkeypatch.setattr(tssh, "executar", _exec)
    r = asyncio.run(aterm.ferramenta_servidor_exec(_abrir, {"comando": "cat /opt/a.log"}, matricula="DEV1", conversa_id="c",
                                                   ssh_max=3, espera_max_s=5))
    b = r["comando_executado"]
    assert b["classe"] == "leitura" and b["estado"] == "executado" and b["comando"] == "cat /opt/a.log" and b["codigo_saida"] == 0
    assert "hunter2" not in b["saida"] and "linha ok" in b["saida"]
    assert len(b["saida"]) <= aterm.MAX_SAIDA_TELA and b["truncada"] is True, "o histórico guarda no máximo 4000 caracteres"
    assert set(b) >= {"cmd_id", "servidor", "duracao_ms", "interrompido", "notas"}


def test_proibido_tambem_vira_bloco(monkeypatch, servidor):
    r = asyncio.run(aterm.ferramenta_servidor_exec(_abrir, {"comando": "cat /opt/app/.env"}, matricula="DEV1", conversa_id="c",
                                                   ssh_max=3, espera_max_s=5))
    b = r["comando_executado"]
    assert b["classe"] == "proibido" and b["estado"] == "bloqueado" and b["saida"] is None and "sensível" in b["motivo"]


@pytest.fixture
def sem_aprendizado(monkeypatch):
    monkeypatch.setattr(svc, "_recuperar_seguro", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_registrar_seguro", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_erro_conhecido_seguro", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_conversar_poe_o_bloco_no_artefato(monkeypatch, sem_aprendizado):
    async def _ferr(abrir, args, **kw):
        return {"texto": "saída", "comando_executado": {"cmd_id": "c1", "comando": "ls /opt", "estado": "executado"}}
    monkeypatch.setattr(aterm, "ferramenta_servidor_exec", _ferr)
    p = _Provedor([_pedido("servidor_exec", comando="ls /opt"), "ok"])
    r = await _conversar(monkeypatch, p, agente="terminal", ferramentas=TERMINAL["ferramentas"])
    assert r["artefatos"][0]["comando_executado"]["cmd_id"] == "c1"


@pytest.mark.asyncio
async def test_o_terminal_usa_o_dsjob_e_nao_e_recusado(monkeypatch, sem_aprendizado):
    chamadas = []

    async def _ex(abrir, nome, args, **kw):
        chamadas.append((nome, kw.get("agente")))
        return {"texto": "jobinfo ok"}, ("BI" if nome == "resolver_projeto" else None)
    monkeypatch.setattr(svc, "_executar_ferramenta", _ex)
    p = _Provedor([_pedido("resolver_projeto", projeto="BI"), _pedido("dsjob", comando="jobinfo", job_name="J1"), "ok"])
    r = await _conversar(monkeypatch, p, agente="terminal", ferramentas=TERMINAL["ferramentas"])
    assert chamadas == [("resolver_projeto", "terminal"), ("dsjob", "terminal")]
    assert not any(a.get("recusada") for a in r["artefatos"])


# ═══════════ 3. retenção ═══════════════════════════════════════════════

def test_purga_so_apaga_estado_final_e_respeita_a_faixa():
    cur = MagicMock(rowcount=7)
    assert aterm.purgar_antigos(cur, 180) == 7
    sql, args = cur.execute.call_args[0]
    assert sql.startswith("DELETE FROM dbo.etl_agente_terminal_cmd") and "DATEADD(day, ?, GETDATE())" in sql
    assert args[0] == -180 and tuple(args[1:]) == aterm.ESTADOS_FINAIS, "nunca apaga `proposto`/`executando`"
    for dias, esperado in ((5, -30), (99999, -3650)):
        aterm.purgar_antigos(cur, dias)
        assert cur.execute.call_args[0][1][0] == esperado


def test_purga_automatica_no_maximo_uma_vez_por_hora(monkeypatch):
    feitas = []
    monkeypatch.setattr(aterm, "_gravar_seguro", lambda abrir, fn: feitas.append(1))
    monkeypatch.setattr(aterm, "_ULTIMA_PURGA", [0.0])
    assert aterm.purgar_se_for_hora(None, 180, agora=10_000.0) is True
    assert aterm.purgar_se_for_hora(None, 180, agora=10_100.0) is False
    assert aterm.purgar_se_for_hora(None, 180, agora=10_000.0 + aterm.INTERVALO_PURGA_S + 1) is True
    assert len(feitas) == 2


# ═══════════ 4. rotas ══════════════════════════════════════════════════

@pytest.fixture
def cliente(monkeypatch):
    estado = {"user": {"matricula": "ADM1", "perfil": "admin", "permissoes": [PERM_ADMIN], "permissoes_extra": []}, "cur": _Cur()}
    _app.dependency_overrides[get_current_user] = lambda: estado["user"]
    with patch("routers.agentes.get_db_conn", side_effect=lambda: _Conn(estado["cur"])):
        yield TestClient(_app), estado
    _app.dependency_overrides.pop(get_current_user, None)


def test_servidores_sem_host_nem_usuario(cliente, monkeypatch):
    c, estado = cliente
    monkeypatch.setenv("AF_SSH_HOST", "af.interno")
    monkeypatch.setenv("AF_SSH_USER", "orq_ro")
    monkeypatch.setenv("AF_SSH_PASSWORD", "NUNCA")
    r = c.get("/agentes/terminal/servidores")
    assert r.status_code == 200 and {"id": "airflow", "label": "Servidor Orquestra/Airflow", "configurado": True} in r.json()["servidores"]
    for segredo in ("af.interno", "orq_ro", "NUNCA"):
        assert segredo not in r.text
    estado["user"] = {"matricula": "X", "perfil": "desenvolvedor", "permissoes": ["tela_agentes"], "permissoes_extra": []}
    assert c.get("/agentes/terminal/servidores").status_code == 403


def test_admin_salva_os_bancos_do_terminal_conferindo_so_os_novos(cliente, monkeypatch):
    c, estado = cliente
    conferidos = []

    async def _conf(pares):
        conferidos.append(list(pares))
        return ["aviso: login com escrita"]
    monkeypatch.setattr("routers.agentes._conferir_pares", _conf)
    estado["cur"].config = {"agente_terminal_bancos": PAR}
    r = c.put("/agentes/admin/terminal/bancos", json={"bancos": [{"conexao": "dw", "banco": "PREV"}, {"conexao": "dw", "banco": "VIDA"}],
                                                       "mascarar_dados": False})
    assert r.status_code == 200 and r.json()["avisos"] == ["aviso: login com escrita"]
    assert conferidos == [[("dw", "VIDA")]], "só o par NOVO vai ao servidor"
    gravado = estado["cur"].gravados
    assert json.loads(gravado["agente_terminal_bancos"]) == [{"conexao": "dw", "banco": "PREV"}, {"conexao": "dw", "banco": "VIDA"}]
    assert gravado["agente_terminal_mascarar"] == "0"


@pytest.mark.parametrize("corpo", [{"bancos": "x"}, {"bancos": [{"conexao": "dw"}]}, {"bancos": [{"conexao": "", "banco": "b"}]}])
def test_admin_bancos_formato_invalido_e_422(cliente, corpo):
    c, _ = cliente
    assert c.put("/agentes/admin/terminal/bancos", json=corpo).status_code == 422


def test_admin_bancos_so_para_admin(cliente):
    c, estado = cliente
    estado["user"] = {"matricula": "X", "perfil": "desenvolvedor", "permissoes": ["tela_agentes"], "permissoes_extra": ["agente_terminal"]}
    assert c.put("/agentes/admin/terminal/bancos", json={"bancos": []}).status_code == 403


@pytest.mark.parametrize("dias,ok", [(180, True), (30, True), (3650, True), (29, False), (4000, False), ("x", False)])
def test_retencao_configuravel_pelo_admin(cliente, dias, ok):
    c, estado = cliente
    r = c.post("/agentes/admin/config", json={"agente_terminal_retencao_dias": dias})
    assert (r.status_code == 200) is ok
    if ok:
        assert estado["cur"].gravados["agente_terminal_retencao_dias"] == str(dias)


def test_a_consulta_da_auditoria_aplica_a_retencao(cliente):
    c, estado = cliente
    deletes = []
    original = estado["cur"].execute

    def _exec(sql, params=None):
        if sql.startswith("DELETE FROM dbo.etl_agente_terminal_cmd"):
            deletes.append(params)
        return original(sql, params)
    estado["cur"].execute = _exec
    estado["cur"].config = {"agente_terminal_retencao_dias": "90"}
    assert c.get("/agentes/terminal/auditoria").status_code == 200
    assert deletes and deletes[0][0] == -90


def test_o_router_injeta_os_bancos_do_terminal_na_conversa():
    fonte = open(os.path.join(os.path.dirname(__file__), "..", "api", "routers", "agentes.py"), encoding="utf-8").read()
    assert "ag = svc.agente_terminal_para_conversa(ag, agentes_cfg)" in fonte


# ═══════════ 5. achados da auditoria final e do QA da F5 ══════════════════

def test_terminal_nao_grava_aprendizado_nem_interpretacao():
    gravou = []
    svc._registrar_seguro(lambda: gravou.append("abriu"), {"regra": "x"}, svc.AGENTE_TERMINAL)
    assert gravou == [], "o Terminal não tem curador: nada vai para a base de conhecimento"
    fonte = open(os.path.join(os.path.dirname(__file__), "..", "api", "services", "agentes.py"), encoding="utf-8").read()
    trecho = fonte.split("texto, brutas = ac.extrair_propostas(texto)", 1)[1][:400]
    assert "if agente == AGENTE_TERMINAL:" in trecho and "brutas, brutas_ap = [], []" in trecho


def test_proposta_igual_em_execucao_bloqueia_nova_proposta():
    cur = MagicMock()
    cur.fetchone.return_value = ("executando",)
    assert aterm.proposta_repetida(cur, "DEV1", "h" * 64) == "viva"
    sql = cur.execute.call_args[0][0]
    assert "estado = 'executando'" in sql, "o mesmo comando rodando não pode ser proposto (e confirmado) de novo"
    cur.fetchone.return_value = None
    assert aterm.proposta_repetida(cur, "DEV1", "h" * 64) is None


def test_confirmar_purga_antes_da_checagem_de_escrita(cliente, monkeypatch):
    """Retenção não depende da escrita: com o kill switch desligado a purga roda e a confirmação é recusada."""
    c, estado = cliente
    chamadas = []
    monkeypatch.setattr(aterm, "purgar_se_for_hora", lambda abrir, dias, agora=None: chamadas.append(dias))
    estado["cur"].config = {"agentes_enabled": "1", "agente_terminal_enabled": "1", "agente_terminal_escrita_enabled": "0",
                            "agente_terminal_retencao_dias": "60"}
    r = c.post("/agentes/terminal/confirmar", json={"cmd_id": "00000000-0000-0000-0000-000000000000", "hash": "0" * 64})
    assert r.status_code == 503 and chamadas == [60]


def test_conversar_com_o_terminal_aplica_a_retencao():
    fonte = open(os.path.join(os.path.dirname(__file__), "..", "api", "routers", "agentes.py"), encoding="utf-8").read()
    preparo = fonte.split("def _preparar_conversa", 1)[1].split("\ndef ", 1)[0]
    assert "aterm.purgar_se_for_hora(_abrir, svc.retencao_terminal_dias(agentes_cfg))" in preparo


def test_put_de_bancos_sem_a_chave_preserva_os_pares(cliente, monkeypatch):
    c, estado = cliente

    async def _conf(pares):
        assert list(pares) == [], "nenhum par novo: nada vai ao servidor"
        return []
    monkeypatch.setattr("routers.agentes._conferir_pares", _conf)
    estado["cur"].config = {"agente_terminal_bancos": PAR}
    r = c.put("/agentes/admin/terminal/bancos", json={"mascarar_dados": False})
    assert r.status_code == 200 and r.json()["bancos"] == [{"conexao": "dw", "banco": "PREV"}]
    assert json.loads(estado["cur"].gravados["agente_terminal_bancos"]) == [{"conexao": "dw", "banco": "PREV"}]
    assert estado["cur"].gravados["agente_terminal_mascarar"] == "0"


@pytest.mark.parametrize("bancos,tem_banco", [("[]", False), (PAR, True)])
def test_previa_do_prompt_usa_as_ferramentas_reais_do_terminal(cliente, bancos, tem_banco):
    from routers import agentes as rot
    _c, estado = cliente
    estado["cur"].config = {"agente_terminal_bancos": bancos}
    with patch("routers.agentes._conexao") as conx:
        conx.return_value.__enter__.return_value = (None, estado["cur"])
        ferramentas, pares = rot._ferramentas_do("terminal")
    assert ("banco_consulta" in ferramentas) is tem_banco and bool(pares) is tem_banco
    assert "servidor_exec" in ferramentas and "dsjob" in ferramentas
