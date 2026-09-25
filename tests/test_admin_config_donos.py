"""Parâmetros avançados só com chaves órfãs + trava de escrita (F5 de
docs/spec-admin-reestruturacao.md).

O que se prende aqui, e por quê:

  1. **Espelho front ↔ back.** A lista de donos do backend
     (`services/admin_config_donos.DONOS`) é igual — mesmos prefixos, mesmos
     rótulos, mesma ordem — ao `chavesConfig` do registro do front, com o rótulo
     de `rotuloAdmin`. E `dono_da_chave` decide igual a `donoDaChave` numa
     amostra (caixa e espaço inclusos). Os padrões de segredo da tela
     (`PADROES_SEGREDO`) são os do `mask_secret`. Bancada:
     tests/js/admin_nav_harness.cjs (TS real via sucrase).
  2. **A trava.** `config_upsert`/`config_delete` recusam chave com dono com
     422 e o `detail` que nomeia a aba — sem tocar o banco; chave órfã segue
     gravando e apagando. A máscara "••••" nunca é regravada.
  3. **Teams.** `teams_webhook_set` valida https, vazio = mantém, `limpar`
     explícito, nunca devolve a URL.
  4. **ServiceNow parcial.** Só triagem não toca a credencial; credencial sem
     triagem não toca a triagem; o corpo antigo completo continua igual.
  5. **Máscara.** `powerbi_client_secret` e segredos órfãos saem mascarados no
     config_list.

Nada toca banco: o cursor é dublê e o `get_db_conn` é substituído.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
os.environ.setdefault("ORQUESTRA_CONN_KEY",
                      "K_sKzYfPUx9hgIP4f5hrZmm9XX0UclK9beFd9RlREdo=")
from api.main import app  # noqa: E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from routers.admin import _PADROES_SEGREDO, mask_secret  # noqa: E402
from services import servicenow  # noqa: E402
from services.admin_config_donos import DONOS, dono_da_chave  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "admin_nav_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
ALVO = "https://cvpsnprod.service-now.com"
HOOK = "https://empresa.webhook.office.com/webhookb2/abc/IncomingWebhook/def/ghi"


# ═══════════ dublês ═════════════════════════════════════════════════════════

class Cursor:
    """Cursor de mentira sobre um dict de config. Entende o SELECT da
    listagem/leitura, o MERGE (1º parâmetro = chave, 2º = valor) e o DELETE."""

    def __init__(self, linhas: dict | None = None):
        self.linhas = dict(linhas or {})
        self.escritas: list[tuple[str, str | None]] = []
        self.sqls: list[str] = []
        self._res: list[tuple] = []

    def execute(self, sql: str, params=None):
        params = list(params or [])
        self.sqls.append(sql)
        s = sql.strip().upper()
        if s.startswith("SELECT"):
            if "LIKE 'CHAMADOS_TRIAGEM%'" in s:
                self._res = [(k, v) for k, v in self.linhas.items() if k.startswith("chamados_triagem")]
            elif params:
                self._res = [(k, v) for k, v in self.linhas.items() if k in params]
            else:
                self._res = sorted(self.linhas.items())
        elif s.startswith("MERGE"):
            self.escritas.append((params[0], params[1]))
            self.linhas[params[0]] = params[1]
        elif s.startswith("DELETE"):
            self.escritas.append((params[0], None))
            self.linhas.pop(params[0], None)
        return self

    def fetchall(self):
        return list(self._res)

    def fetchone(self):
        return self._res[0] if self._res else None

    def close(self):
        pass


@pytest.fixture
def admin_client():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN],
    }
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": Cursor(), "conexoes": 0}

    def _fabrica():
        estado["conexoes"] += 1
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.admin.get_db_conn", _fabrica)
    monkeypatch.setattr("services.servicenow.get_db_conn", _fabrica)
    return estado


def _post(cli, **corpo):
    return cli.post("/admin", json=corpo)


# ═══════════ 1. espelho front ↔ back ════════════════════════════════════════

@pytest.fixture(scope="module")
def bancada():
    node = shutil.which("node")
    if not node or not SUCRASE.exists():
        pytest.skip("Node/Sucrase indisponível")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_donos_do_backend_espelham_o_registro(bancada):
    assert [tuple(d) for d in bancada["donos"]] == list(DONOS)


def test_rotulos_dos_donos_sao_abas_que_existem(bancada):
    validos = set(bancada["rotulos"]["todas"])
    assert {r for _, r in DONOS} <= validos


def test_dono_da_chave_decide_igual_ao_front(bancada):
    for chave, rotulo in bancada["donoDaChave"].items():
        assert dono_da_chave(chave) == rotulo, chave


def test_padroes_de_segredo_iguais_nos_dois_lados(bancada):
    assert tuple(bancada["padroesSegredo"]) == _PADROES_SEGREDO
    for chave, sens in bancada["sensivel"].items():
        assert (mask_secret(chave, "valor-9999") != "valor-9999") is sens, chave


def test_orfas_agrupadas_por_prefixo(bancada):
    grupos = {g["rotulo"]: [k for k, _ in g["chaves"]] for g in bancada["orfas"]}
    assert list(grupos) == ["Aplicação", "Malha e dependências", "Power BI", "Prévia de SQL", "Outras"]
    assert grupos["Aplicação"] == ["app_base_url", "app_version"]
    assert grupos["Malha e dependências"] == ["dependencia_hora_virada", "espera_teto_minutos", "malha_corrida_ativa"]
    assert grupos["Outras"] == ["agentes_titulo_redigido_em", "servicenow_admin_perfis", "zzz_desconhecida"]
    todas = [k for ks in grupos.values() for k in ks]
    for com_dono in ("email_remetente", "teams_webhook_url", "servicenow_url", "chamados_triagem_lote", "maestro_enabled"):
        assert com_dono not in todas


def test_descricao_da_aba_e_a_copy_da_spec(bancada):
    aba = next(a for a in bancada["abas"] if a["id"] == "parametros")
    assert aba["descricao"] == "Chaves sem tela própria. Para as demais, use a busca."


# ═══════════ 2. trava do editor genérico ════════════════════════════════════

@pytest.mark.parametrize("chave,rotulo", [
    ("email_remetente", "Admin › Comunicação › E-mail"),
    ("EMAIL_REMETENTE", "Admin › Comunicação › E-mail"),
    ("teams_webhook_url_resolved", "Admin › Comunicação › Teams"),
    ("servicenow_senha_enc", "Admin › Integrações & Dados › ServiceNow"),
    ("chamados_triagem_habilitada", "Admin › Inteligência Artificial › Triagem de chamados"),
    ("ia_api_key_enc", "Admin › Inteligência Artificial › Provedor"),
    ("maestro_enabled", "Admin › Inteligência Artificial › Maestro"),
    ("utilitarios_arquivo_max_kb", "Admin › Integrações & Dados › Servidor DataStage (SFTP)"),
    ("agentes_enabled", "Admin › Inteligência Artificial › Agentes"),
])
def test_upsert_de_chave_com_dono_e_422(admin_client, banco, chave, rotulo):
    r = _post(admin_client, action="config_upsert", config_key=f" {chave} ", config_value="x")
    assert r.status_code == 422
    assert r.json()["detail"] == f"A chave {chave} é gerida em {rotulo}."
    assert banco["conexoes"] == 0, "a recusa não abre conexão com o banco"


def test_delete_de_chave_com_dono_e_422(admin_client, banco):
    banco["cur"] = Cursor({"email_remetente": "a@b"})
    r = _post(admin_client, action="config_delete", config_key="email_remetente")
    assert r.status_code == 422
    assert r.json()["detail"] == "A chave email_remetente é gerida em Admin › Comunicação › E-mail."
    assert banco["cur"].linhas == {"email_remetente": "a@b"}


@pytest.mark.parametrize("chave", ["app_base_url", "malha_teto_horas_padrao", "powerbi_client_id",
                                   "servicenow_admin_perfis", "agentes_titulo_redigido_em", "nova_chave"])
def test_chave_orfa_continua_gravando_e_apagando(admin_client, banco, chave):
    r = _post(admin_client, action="config_upsert", config_key=chave, config_value="valor")
    assert r.status_code == 200, r.text
    assert banco["cur"].escritas == [(chave, "valor")]
    r = _post(admin_client, action="config_delete", config_key=chave)
    assert r.status_code == 200
    assert chave not in banco["cur"].linhas


def test_mascara_nunca_e_regravada(admin_client, banco):
    banco["cur"] = Cursor({"powerbi_client_secret": "segredo-real-1234"})
    r = _post(admin_client, action="config_upsert", config_key="powerbi_client_secret", config_value="•••• 1234")
    assert r.status_code == 422
    assert "máscara" in r.json()["detail"]
    assert banco["cur"].linhas["powerbi_client_secret"] == "segredo-real-1234"


def test_rotas_proprias_nao_passam_pela_trava(admin_client, banco):
    """A trava vale só para as duas actions genéricas (risco 3 da spec)."""
    r = _post(admin_client, action="teams_webhook_set", valores={"teams_webhook_url": HOOK})
    assert r.status_code == 200
    r = _post(admin_client, action="servicenow_set", triagem_habilitada=True)
    assert r.status_code == 200


# ═══════════ 3. Teams: teams_webhook_set ════════════════════════════════════

def test_teams_grava_so_o_que_veio_preenchido(admin_client, banco):
    banco["cur"] = Cursor({"teams_webhook_url": "https://antigo", "teams_webhook_url_ack": "https://ack-antigo"})
    r = _post(admin_client, action="teams_webhook_set",
              valores={"teams_webhook_url": "", "teams_webhook_url_ack": None,
                       "teams_webhook_url_resolved": f"  {HOOK}  "})
    assert r.status_code == 200, r.text
    assert banco["cur"].escritas == [("teams_webhook_url_resolved", HOOK)]
    assert banco["cur"].linhas["teams_webhook_url"] == "https://antigo"
    assert banco["cur"].linhas["teams_webhook_url_ack"] == "https://ack-antigo"
    assert HOOK not in r.text, "a resposta nunca devolve a URL (tem token)"


@pytest.mark.parametrize("valor,trecho", [
    ("http://inseguro.com/x", "https://"),
    ("https://", "https://"),
    ("•••• ghi", "máscara"),
    ("https://a.com/x y", "espaço"),
    ("https://a.com/" + "x" * 1000, "longa"),
    (123, "texto"),
])
def test_teams_valida_a_url(admin_client, banco, valor, trecho):
    banco["cur"] = Cursor({"teams_webhook_url": "https://antigo"})
    r = _post(admin_client, action="teams_webhook_set", valores={"teams_webhook_url": valor})
    assert r.status_code == 422
    assert trecho in r.json()["detail"]
    assert banco["cur"].escritas == []


def test_teams_limpar_e_explicito(admin_client, banco):
    banco["cur"] = Cursor({"teams_webhook_url_ack": "https://ack"})
    r = _post(admin_client, action="teams_webhook_set", limpar=["teams_webhook_url_ack"])
    assert r.status_code == 200
    assert banco["cur"].linhas["teams_webhook_url_ack"] == ""
    assert r.json()["limpas"] == ["teams_webhook_url_ack"]


@pytest.mark.parametrize("corpo,trecho", [
    ({}, "Nada a alterar"),
    ({"valores": {"teams_webhook_url": "  "}}, "Nada a alterar"),
    ({"valores": {"email_remetente": HOOK}}, "fora do webhook"),
    ({"limpar": ["servicenow_url"]}, "fora do webhook"),
    ({"valores": {"teams_webhook_url": HOOK}, "limpar": ["teams_webhook_url"]}, "ao mesmo tempo"),
    ({"valores": [HOOK]}, "objeto"),
])
def test_teams_recusa_corpo_invalido(admin_client, banco, corpo, trecho):
    r = _post(admin_client, action="teams_webhook_set", **corpo)
    assert r.status_code == 422
    assert trecho in r.json()["detail"]
    assert banco["cur"].escritas == []


def test_teams_config_list_devolve_mascarado(admin_client, banco):
    banco["cur"] = Cursor({"teams_webhook_url": HOOK, "teams_webhook_url_ack": ""})
    cfg = _post(admin_client, action="config_list").json()["config"]
    assert cfg["teams_webhook_url"].startswith("••••") and "webhookb2" not in cfg["teams_webhook_url"]
    assert cfg["teams_webhook_url_ack"] == ""


# ═══════════ 4. ServiceNow parcial ══════════════════════════════════════════

CRED = {servicenow.K_URL: ALVO, servicenow.K_USUARIO: "svc", servicenow.K_SENHA: "token-cifrado",
        servicenow.K_GRUPOS: "Engenharia", servicenow.K_HABILITADO: "1", servicenow.K_PROXY: "http://proxy:8080"}


def test_so_triagem_nao_toca_a_credencial(admin_client, banco):
    banco["cur"] = Cursor({**CRED, "chamados_triagem_habilitada": "0", "chamados_triagem_lote": "20"})
    r = _post(admin_client, action="servicenow_set", triagem_habilitada=True, triagem_lote="35")
    assert r.status_code == 200, r.text
    assert dict(banco["cur"].escritas) == {"chamados_triagem_habilitada": "1", "chamados_triagem_lote": "35"}
    for k, v in CRED.items():
        assert banco["cur"].linhas[k] == v


def test_so_triagem_funciona_sem_instancia_configurada(admin_client, banco):
    r = _post(admin_client, action="servicenow_set", triagem_habilitada=False)
    assert r.status_code == 200
    assert banco["cur"].escritas == [("chamados_triagem_habilitada", "0")]


def test_so_triagem_valida_o_lote(admin_client, banco):
    r = _post(admin_client, action="servicenow_set", triagem_lote="abc")
    assert r.status_code == 422
    assert banco["cur"].escritas == []


def test_corpo_vazio_e_recusado(admin_client, banco):
    r = _post(admin_client, action="servicenow_set")
    assert r.status_code == 422
    assert banco["cur"].escritas == []


def test_credencial_sem_triagem_nao_toca_a_triagem(admin_client, banco):
    banco["cur"] = Cursor({**CRED, "chamados_triagem_habilitada": "1", "chamados_triagem_lote": "50"})
    r = _post(admin_client, action="servicenow_set", url=ALVO, usuario="svc2", grupos="G",
              proxy="", habilitado=True)
    assert r.status_code == 200, r.text
    gravadas = dict(banco["cur"].escritas)
    assert "chamados_triagem_habilitada" not in gravadas and "chamados_triagem_lote" not in gravadas
    assert servicenow.K_SENHA not in gravadas
    assert gravadas[servicenow.K_USUARIO] == "svc2"


def test_corpo_antigo_completo_continua_funcionando(admin_client, banco):
    """Bundle antigo da aba Triagem em cache: relia e reenviava a credencial."""
    banco["cur"] = Cursor({**CRED})
    r = _post(admin_client, action="servicenow_set", url=ALVO, usuario="svc", grupos="Engenharia",
              proxy="http://proxy:8080", habilitado=True, triagem_habilitada=True, triagem_lote=10)
    assert r.status_code == 200, r.text
    gravadas = dict(banco["cur"].escritas)
    assert gravadas["chamados_triagem_habilitada"] == "1" and gravadas["chamados_triagem_lote"] == "10"
    assert gravadas[servicenow.K_URL] == ALVO
    assert banco["cur"].linhas[servicenow.K_SENHA] == "token-cifrado"


def test_credencial_parcial_segue_validada(admin_client, banco):
    """Um campo de credencial presente = caminho completo, com url_valida."""
    r = _post(admin_client, action="servicenow_set", usuario="svc", triagem_habilitada=True)
    assert r.status_code == 422
    assert banco["cur"].escritas == []


# ═══════════ 5. máscara no config_list ══════════════════════════════════════

def test_segredo_orfao_sai_mascarado(admin_client, banco):
    banco["cur"] = Cursor({"powerbi_client_secret": "s3gr3d0-do-azure-9f2a", "powerbi_client_id": "id-publico",
                           "app_base_url": "http://orquestra", "x_api_key": "chave-crua-1234",
                           "y_senha_enc": "gAAAAAB-cifrado-5678"})
    corpo = _post(admin_client, action="config_list").json()
    cfg = corpo["config"]
    assert "s3gr3d0" not in json.dumps(corpo, ensure_ascii=False)
    assert cfg["powerbi_client_secret"].startswith("••••")
    assert cfg["x_api_key"].startswith("••••") and cfg["y_senha_enc"].startswith("••••")
    assert cfg["powerbi_client_id"] == "id-publico" and cfg["app_base_url"] == "http://orquestra"


# ═══════════ achados do QA + auditoria de segurança da F5 ═══════════════════

@pytest.mark.parametrize("chave", [
    "ｅmail_remetente",          # fullwidth: casa com a linha real no SQL Server (CI_AS)
    "﻿teams_webhook_url",       # BOM: peso zero na colação
    "\u0000servicenow_senha_enc",    # NUL
    "teams＿webhook_url",        # underscore fullwidth
    "email remetente",               # espaço no meio
    "x" * 101,
])
@pytest.mark.parametrize("action", ["config_upsert", "config_delete"])
def test_chave_fora_do_ascii_e_recusada_antes_do_banco(admin_client, banco, chave, action):
    r = _post(admin_client, action=action, config_key=chave, config_value="v")
    assert r.status_code == 422 and "Chave inválida" in r.json()["detail"]
    assert banco["conexoes"] == 0, "a recusa não pode tocar o banco"


def test_config_upsert_nao_ecoa_o_valor(admin_client, banco):
    r = _post(admin_client, action="config_upsert", config_key="powerbi_client_secret", config_value="s3gr3do-xyz")
    assert r.status_code == 200 and "s3gr3do-xyz" not in r.text


def test_config_publico_omite_todo_segredo(monkeypatch):
    """GET /config não exige login: nenhuma chave com padrão de segredo sai."""
    linhas = {"app_base_url": "https://x", "servicenow_senha_enc": "gAAAA-token",
              "ia_api_key_enc": "gAAAA-ia", "gateway_api_key": "k-123",
              "powerbi_client_secret": "s", "teams_webhook_url_ack": "https://h",
              "qualquer_api_token": "t"}
    cur = Cursor(linhas)
    conn = MagicMock(); conn.cursor.return_value = cur
    monkeypatch.setattr("routers.infra.get_db_conn", lambda: conn)
    corpo = TestClient(app).get("/config").json()
    assert corpo.get("app_base_url") == "https://x"
    vazou = [k for k in linhas if k != "app_base_url" and k in corpo]
    assert not vazou, vazou


def test_etl_admin_manage_so_admin_pelo_proxy():
    """A DAG confia no requested_by do conf: pelo proxy genérico (acao_executar)
    qualquer executor se passaria por admin."""
    from routers import airflow as rt_airflow
    assert "etl_admin_manage" in rt_airflow._DAGS_SO_ADMIN  # noqa: SLF001
