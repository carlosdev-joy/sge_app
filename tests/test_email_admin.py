"""E-mail — configuração e envio de teste pela API (F1 da spec
docs/spec-notificacao-email.md).

O que se prende:

  1. **Toda rota /email/admin/* exige acao_admin** (varredura por AST + 403 real).
  2. **Config**: leitura degrada sem a 111 (`disponivel=False`, status oculto);
     gravar valida (remetente, ligar sem remetente, limite, raízes, domínios)
     com 422 estruturado e grava por MERGE; a resposta relê.
  3. **Testar**: monta a mensagem com o remetente salvo e o e-mail do usuário
     (ou `para`), entrega pelo `run_sendmail` (mockado) e devolve o LAUDO —
     rc 0 → ok; rc ≠ 0 → etapa sendmail; sem SSH configurado → etapa config;
     rede caída → etapa ssh (nunca 500); cada tentativa vira uma linha em
     etl_email_log com status enviado/falhou, sem quebrar a resposta se o log
     falhar.
  4. **`run_sendmail`**: comando FIXO (`<bin> -t -i`), mensagem no stdin,
     binário do ambiente validado, conexão fechada.
  5. **Log**: `GET /email/log` com/sem pipeline, 503 sem a 111.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import email_config, ssh_datastage  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "api" / "routers" / "email.py"

CONFIG_OK = {"email_habilitado": "1", "email_remetente": "orquestra@cvp.com.br", "email_limite_anexo_mb": "5",
             "email_anexo_raizes": '["/dados/saida"]', "email_dominios_permitidos": '["cvp.com.br"]'}


class _Cur:
    def __init__(self, config=None, sem_111=False, log_rows=None):
        self.config = dict(config) if config is not None else dict(CONFIG_OK)
        self.sem_111, self.log_rows = sem_111, log_rows or []
        self.execs: list[tuple[str, tuple]] = []
        self.inseridos: list[tuple] = []
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = " ".join(sql.lower().split())
        if "from dbo.etl_app_config" in s:
            self._rows = [] if self.sem_111 else [(k, v) for k, v in self.config.items()]
        elif s.startswith("merge dbo.etl_app_config"):
            self.config[params[0]] = params[1]; self._rows = []
        elif "insert into dbo.etl_email_log" in s:
            if self.sem_111:
                raise Exception("Invalid object name 'dbo.etl_email_log'")
            self.inseridos.append(params); self._rows = []
        elif "from dbo.etl_email_log" in s:
            if self.sem_111:
                raise Exception("Invalid object name 'dbo.etl_email_log'")
            self._rows = list(self.log_rows)
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _Conn:
    def __init__(self, cur):
        self._cur, self.commits = cur, 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1

    def close(self):
        pass


# ═══════════ puro: config ════════════════════════════════════════════════════

def test_load_config_le_e_degrada():
    cfg = email_config.load_config(_Cur())
    assert cfg == {"enabled": True, "remetente": "orquestra@cvp.com.br", "limite_mb": 5,
                   "raizes": ["/dados/saida"], "dominios": ["cvp.com.br"],
                   "exigir_modelo": False, "disponivel": True, "erro": None}
    cfg = email_config.load_config(_Cur(sem_111=True))
    assert cfg["disponivel"] is False and cfg["enabled"] is False and cfg["erro"] is None

    class _CurFora(_Cur):
        def execute(self, sql, params=None):
            raise Exception("Login timeout expired")
    cfg = email_config.load_config(_CurFora())
    assert cfg["disponivel"] is False and "Login timeout" in cfg["erro"]      # banco fora ≠ migration pendente
    cfg = email_config.load_config(_Cur(config={**CONFIG_OK, "email_limite_anexo_mb": "lixo", "email_anexo_raizes": "{"}))
    assert cfg["limite_mb"] == 5 and cfg["raizes"] == []


def test_validar_config():
    valores, erros = email_config.validar_config({"enabled": True, "remetente": " Orq@CVP.com.br ", "limite_mb": "10",
                                                  "raizes": "/a\n/b/", "dominios": ["cvp.com.br", "@x.io"]})
    assert erros == []
    assert valores == {"email_habilitado": "1", "email_remetente": "Orq@cvp.com.br", "email_limite_anexo_mb": "10",
                       "email_anexo_raizes": '["/a", "/b"]', "email_dominios_permitidos": '["cvp.com.br", "x.io"]'}
    _, erros = email_config.validar_config({"enabled": True, "remetente": "", "limite_mb": 30, "raizes": ["rel"], "dominios": ["ruim"]})
    assert any("antes de ligar" in e for e in erros) and any("entre 1 e 25" in e for e in erros)
    assert any("raiz inválida" in e for e in erros) and any("domínio inválido" in e for e in erros)
    _, erros = email_config.validar_config({"enabled": False, "remetente": "ruim"})
    assert erros == ["remetente inválido (um endereço de e-mail, sem quebras de linha)"]
    assert email_config.validar_config({"enabled": False})[1] == []            # desligado sem remetente pode
    assert email_config.validar_config("x")[1]
    # "false" pela API direta NÃO liga (bool("false") ligaria); "lixo" é erro
    assert email_config.validar_config({"enabled": "false", "remetente": ""})[0]["email_habilitado"] == "0"
    assert email_config.validar_config({"enabled": "1", "remetente": "a@x.com"})[0]["email_habilitado"] == "1"
    assert any("true/false" in e for e in email_config.validar_config({"enabled": "lixo"})[1])
    # teto da coluna VARCHAR(1000): lista longa é 422, não 500 opaco no MERGE
    muitas = [f"/opt/IBM/InformationServer/Server/Projects/PROJ{i:02d}/saida" for i in range(20)]
    _, erros = email_config.validar_config({"enabled": False, "raizes": muitas})
    assert any("raízes: lista longa demais" in e for e in erros)
    valores, _ = email_config.validar_config({"enabled": False, "raizes": ["/dados/saída"]})
    assert valores["email_anexo_raizes"] == '["/dados/sa\\u00edda"]'          # JSON só-ASCII na coluna VARCHAR


def test_save_config_faz_merge_por_chave():
    cur = _Cur()
    email_config.save_config(cur, {"email_habilitado": "0", "chave_estranha": "x"}, "ADM")
    assert len(cur.execs) == 1 and cur.execs[0][0].startswith("MERGE dbo.etl_app_config")
    assert cur.execs[0][1][:3] == ("email_habilitado", "0", "ADM")


# ═══════════ run_sendmail ════════════════════════════════════════════════════

class _Canal:
    def __init__(self, rc):
        self.rc, self.fechado = rc, False

    def shutdown_write(self):
        self.fechado = True

    def recv_exit_status(self):
        return self.rc


class _Fluxo:
    def __init__(self, canal, dados=b""):
        self.channel, self._dados, self.escrito = canal, dados, b""

    def write(self, b):
        self.escrito += b

    def read(self):
        return self._dados


class _ClienteSsh:
    def __init__(self, rc=0, stderr=b""):
        self.canal = _Canal(rc)
        self.stdin, self.stdout, self.stderr = _Fluxo(self.canal), _Fluxo(self.canal), _Fluxo(self.canal, stderr)
        self.comandos, self.fechado = [], False

    def exec_command(self, cmd, timeout=None):
        self.comandos.append(cmd)
        return self.stdin, self.stdout, self.stderr

    def close(self):
        self.fechado = True


def test_run_sendmail_comando_fixo_stdin_e_fecha(monkeypatch):
    monkeypatch.setenv("DS_SSH_HOST", "lnxprd021"); monkeypatch.setenv("DS_SSH_USER", "orq")
    monkeypatch.delenv("EMAIL_SENDMAIL_BIN", raising=False)
    c = _ClienteSsh(rc=0)
    monkeypatch.setattr(ssh_datastage, "_conectar", lambda: c)
    r = ssh_datastage.run_sendmail(b"From: a@x.com\nTo: b@x.com\nSubject: s; rm -rf /\n\ncorpo", "orquestra@cvp.com.br")
    assert c.comandos == ["/usr/sbin/sendmail -t -i -f orquestra@cvp.com.br"]   # o assunto malicioso ficou no stdin, não no shell
    assert c.stdin.escrito.startswith(b"From:") and c.canal.fechado and c.fechado
    assert r == {"exit_code": 0, "stderr": "", "duration_ms": r["duration_ms"], "host": "lnxprd021"}
    monkeypatch.setenv("EMAIL_SENDMAIL_BIN", "/usr/sbin/sendmail.postfix")
    c2 = _ClienteSsh(rc=1, stderr=b"erro")
    monkeypatch.setattr(ssh_datastage, "_conectar", lambda: c2)
    assert ssh_datastage.run_sendmail(b"x", "a@x.com")["stderr"] == "erro" and c2.comandos == ["/usr/sbin/sendmail.postfix -t -i -f a@x.com"]
    monkeypatch.setenv("EMAIL_SENDMAIL_BIN", "/usr/sbin/sendmail; id")
    with pytest.raises(ssh_datastage.DsConsoleError):
        ssh_datastage.run_sendmail(b"x", "a@x.com")
    monkeypatch.setenv("EMAIL_SENDMAIL_BIN", "/usr/sbin/sendmail")
    for rem in ("a@x.com; id", "$(id)@x.com", "", "a b@x.com"):
        with pytest.raises(ssh_datastage.DsConsoleError):
            ssh_datastage.run_sendmail(b"x", rem)
    monkeypatch.delenv("DS_SSH_HOST")
    with pytest.raises(ssh_datastage.DsConsoleError):
        ssh_datastage.run_sendmail(b"x", "a@x.com")


# ═══════════ rotas ═══════════════════════════════════════════════════════════

def _rotas_admin() -> list[tuple[str, str]]:
    achados = []
    for no in ast.walk(ast.parse(FONTE.read_text(encoding="utf-8"))):
        if not isinstance(no, ast.FunctionDef):
            continue
        for dec in no.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "router"
                    and dec.args and isinstance(dec.args[0], ast.Constant)
                    and str(dec.args[0].value).startswith("/email/admin")):
                achados.append((dec.func.attr.upper(), dec.args[0].value))
    return achados


@pytest.fixture
def ambiente(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app
    from deps import get_current_user

    estado = {"perms": ["acao_admin", "tela_jobs"], "email": "eu@cvp.com.br"}
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADM1", "perfil": "admin", "permissoes": estado["perms"], "email": estado["email"]}
    cur = _Cur()
    conn = _Conn(cur)
    monkeypatch.setenv("DS_SSH_HOST", "lnxprd021"); monkeypatch.setenv("DS_SSH_USER", "orq")
    envio = {"resposta": {"exit_code": 0, "stderr": "", "duration_ms": 12, "host": "lnxprd021"}, "mensagens": []}

    def _fake_sendmail(mensagem, remetente, timeout=60):
        envio["mensagens"].append(mensagem)
        envio["remetente"] = remetente
        if isinstance(envio["resposta"], Exception):
            raise envio["resposta"]
        return dict(envio["resposta"])
    monkeypatch.setattr(ssh_datastage, "run_sendmail", _fake_sendmail)
    with patch("routers.email.get_db_conn", return_value=conn):
        yield TestClient(app), cur, conn, estado, envio
    app.dependency_overrides.pop(get_current_user, None)


def test_ha_rotas_admin_para_varrer():
    assert len(_rotas_admin()) >= 3


@pytest.mark.parametrize("metodo, caminho", _rotas_admin())
def test_toda_rota_admin_exige_acao_admin(ambiente, metodo, caminho):
    cliente, _cur, _conn, estado, envio = ambiente
    estado["perms"] = ["tela_jobs"]
    r = cliente.request(metodo, caminho, json={})
    assert r.status_code == 403 and envio["mensagens"] == []


def test_status_publico_e_config_admin(ambiente):
    cliente, cur, *_ = ambiente
    assert cliente.get("/email/status").json() == {"enabled": True, "limite_mb": 5, "raizes": ["/dados/saida"],
                                                   "dominios": ["cvp.com.br"], "disponivel": True}
    d = cliente.get("/email/admin/config").json()["config"]
    assert d["remetente"] == "orquestra@cvp.com.br" and d["ssh_configurado"] is True and d["ssh_host"] == "lnxprd021"
    cur.sem_111 = True
    assert cliente.get("/email/status").json()["disponivel"] is False
    r = cliente.get("/email/admin/config")
    assert r.status_code == 503 and "migration 111" in r.json()["detail"]
    original = cur.execute

    def _fora(sql, params=None):
        raise Exception("Login timeout expired")
    cur.execute = _fora
    r = cliente.get("/email/admin/config")
    assert r.status_code == 503 and "falha ao ler a configuração" in r.json()["detail"] and "migration" not in r.json()["detail"]
    cur.execute = original


def test_config_set_valida_grava_e_rele(ambiente):
    cliente, cur, conn, *_ = ambiente
    r = cliente.post("/email/admin/config", json={"enabled": True, "remetente": "", "limite_mb": 5})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "email_config_invalida" and conn.commits == 0
    r = cliente.post("/email/admin/config", json={"enabled": False, "remetente": "novo@cvp.com.br", "limite_mb": 10,
                                                 "raizes": "/x\n/y", "dominios": ""})
    assert r.status_code == 200 and conn.commits == 1
    assert r.json()["config"]["remetente"] == "novo@cvp.com.br" and r.json()["config"]["enabled"] is False
    assert r.json()["config"]["raizes"] == ["/x", "/y"] and r.json()["config"]["limite_mb"] == 10
    merges = [e for e in cur.execs if e[0].startswith("MERGE")]
    # As 5 chaves base vão sempre; `email_exigir_modelo` só quando vem no corpo
    # (chave ausente preserva o valor — uma tela antiga não pode desligar a
    # padronização em silêncio).
    base = set(email_config.CHAVES) - {email_config.K_EXIGIR_MODELO}
    assert {m[1][0] for m in merges} == base and all(m[1][2] == "ADM1" for m in merges)
    cur.sem_111 = True
    assert cliente.post("/email/admin/config", json={"enabled": False}).status_code == 503


def test_testar_ok_para_o_proprio_usuario(ambiente):
    cliente, cur, conn, estado, envio = ambiente
    r = cliente.post("/email/admin/testar", json={})
    assert r.status_code == 200, r.text
    laudo = r.json()["laudo"]
    assert laudo["ok"] is True and laudo["etapa"] == "ok" and laudo["host"] == "lnxprd021" and laudo["exit_code"] == 0
    assert laudo["destinatarios"] == ["eu@cvp.com.br"] and laudo["remetente"] == "orquestra@cvp.com.br"
    assert envio["remetente"] == "orquestra@cvp.com.br"          # o -f vai com o remetente do Admin
    msg = envio["mensagens"][0]
    assert b"From: orquestra@cvp.com.br" in msg and b"To: eu@cvp.com.br" in msg and b"Subject: [Orquestra] Teste de e-mail" in msg
    assert len(cur.inseridos) == 1 and conn.commits == 1
    linha = cur.inseridos[0]
    assert linha[0] == "_teste_admin" and linha[1] == "testar" and linha[9] == "enviado" and linha[12] == "ADM1"
    assert json.loads(linha[5]) == ["eu@cvp.com.br"]


def test_testar_para_informado_dominio_e_sem_email(ambiente):
    cliente, cur, _conn, estado, envio = ambiente
    r = cliente.post("/email/admin/testar", json={"para": "outro@cvp.com.br"})
    assert r.json()["laudo"]["destinatarios"] == ["outro@cvp.com.br"]
    r = cliente.post("/email/admin/testar", json={"para": "fora@gmail.com"})
    assert r.status_code == 422 and "domínio não permitido" in r.json()["detail"]["errors"][0]
    estado["email"] = None
    r = cliente.post("/email/admin/testar", json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "email_destinatario_invalido"
    cur.config["email_remetente"] = ""
    r = cliente.post("/email/admin/testar", json={"para": "x@cvp.com.br"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "email_sem_remetente"
    cur.config["email_remetente"] = "gravado à mão"              # fora da régua → 422, não 500
    r = cliente.post("/email/admin/testar", json={"para": "x@cvp.com.br"})
    assert r.status_code == 422 and "não monta uma mensagem válida" in r.json()["detail"]["errors"][0]


def test_testar_laudo_por_etapa_e_registro_falhou(ambiente):
    cliente, cur, _conn, _estado, envio = ambiente
    envio["resposta"] = {"exit_code": 75, "stderr": "relay recusou", "duration_ms": 5, "host": "lnxprd021"}
    laudo = cliente.post("/email/admin/testar", json={}).json()["laudo"]
    assert laudo["ok"] is False and laudo["etapa"] == "sendmail" and "rc=75" in laudo["mensagem"]
    assert cur.inseridos[-1][9] == "falhou" and "relay recusou" in cur.inseridos[-1][10]
    envio["resposta"] = ssh_datastage.DsConsoleError("SSH do DataStage não configurado")
    laudo = cliente.post("/email/admin/testar", json={}).json()["laudo"]
    assert laudo["etapa"] == "config" and "não configurado" in laudo["mensagem"]
    envio["resposta"] = TimeoutError("timed out")
    r = cliente.post("/email/admin/testar", json={})
    assert r.status_code == 200 and r.json()["laudo"]["etapa"] == "ssh" and "TimeoutError" in r.json()["laudo"]["mensagem"]


def test_testar_sem_a_111_e_falha_no_log_nao_derruba(ambiente):
    cliente, cur, _conn, _estado, envio = ambiente
    original = cur.execute

    def _execute(sql, params=None):
        if "insert into dbo.etl_email_log" in sql.lower():
            raise Exception("deadlock")
        return original(sql, params)
    cur.execute = _execute
    r = cliente.post("/email/admin/testar", json={})
    assert r.status_code == 200 and r.json()["laudo"]["ok"] is True and r.json()["laudo"]["persistido"] is False
    cur.execute = original
    cur.sem_111 = True
    assert cliente.post("/email/admin/testar", json={}).status_code == 503


def test_log(ambiente):
    cliente, cur, *_ = ambiente
    cur.log_rows = [(1, "P", "J", "manual__x", "20260910T100000", "orq@cvp.com.br", '["a@cvp.com.br"]', "s",
                     "/dados/saida/rel.xlsx", 1200, "enviado", None, 300, None, "2026-09-10 10:00:00")]
    d = cliente.get("/email/log?pipeline=P&limite=5").json()
    assert d["envios"][0]["destinatarios"] == ["a@cvp.com.br"] and d["envios"][0]["status"] == "enviado"
    assert "WHERE pipeline_name = ?" in cur.execs[-1][0] and "TOP (5)" in cur.execs[-1][0]
    cliente.get("/email/log")
    assert "WHERE" not in cur.execs[-1][0]

    # Filtro por CORRIDA feito no banco: a tela de execução filtrava em memória
    # sobre os últimos do pipeline, e o bloco sumia das corridas antigas.
    cliente.get("/email/log?pipeline=P&execution_id=20260910T100000")
    sql = cur.execs[-1][0]
    assert "WHERE pipeline_name = ? AND execution_id = ?" in sql
    assert cur.execs[-1][1] == ("P", "20260910T100000")
    cliente.get("/email/log?execution_id=20260910T100000")
    assert "WHERE execution_id = ?" in cur.execs[-1][0]

    cur.sem_111 = True
    assert cliente.get("/email/log").status_code == 503


def test_interruptor_de_exigir_modelo():
    """Migration 112: ligado, a opção *Corpo livre* some da lista do nó."""
    valores, erros = email_config.validar_config(
        {"enabled": False, "remetente": "", "exigir_modelo": True})
    assert erros == [] and valores[email_config.K_EXIGIR_MODELO] == "1"
    valores, _ = email_config.validar_config({"enabled": False, "exigir_modelo": False})
    assert valores[email_config.K_EXIGIR_MODELO] == "0"
    # chave AUSENTE não grava: preserva o que estava valendo
    valores, _ = email_config.validar_config({"enabled": False})
    assert email_config.K_EXIGIR_MODELO not in valores
    assert any("true/false" in e for e in
               email_config.validar_config({"enabled": False, "exigir_modelo": "talvez"})[1])


def test_exigir_modelo_ausente_no_banco_e_desligado():
    """Ambiente sem a 112 não pode ficar com a padronização ligada por acidente."""
    cfg = email_config.load_config(_Cur(config={k: v for k, v in CONFIG_OK.items()}))
    assert cfg["exigir_modelo"] is False
    cfg = email_config.load_config(_Cur(config={**CONFIG_OK, "email_exigir_modelo": "1"}))
    assert cfg["exigir_modelo"] is True
