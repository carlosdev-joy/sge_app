"""Credencial executora do ServiceNow (config servicenow_* em etl_app_config).

"Executora" é o ponto: esta é a credencial que a DAG de sync usa para chamar a
API. O que os testes prendem:

  1. **A senha não volta.** `servicenow_get` devolve `tem_senha` (bool), nunca
     o valor — nem cifrado. Um token Fernet vazando na tela é material para
     ataque offline se a ORQUESTRA_CONN_KEY escapar depois.
  2. **A senha é mascarada no config_list.** A chave é `servicenow_senha_enc`
     e não casa com "secret"/"password"/"token" — sem o fragmento "senha" na
     lista de padrões ela sairia inteira na listagem de configuração. Este
     teste é a única coisa entre esse vazamento e a produção.
  3. **Editar URL/grupo não exige redigitar a senha.** Senha vazia = manter a
     atual; senão trocar o grupo apagaria a credencial em silêncio.
  4. **Habilitar sem credencial completa é recusado**, senão o sync agendado
     falharia de 3 em 3 horas com o operador achando que ligou.
  5. **O que falta é NOMEADO.** "não configurado" e "chave de cifra ausente"
     produzem o mesmo sintoma (sync que não roda) por causas diferentes.
  6. **A degradação sem a migration 088**: config vazia, não exceção — a aba
     do Admin não pode morrer num ambiente que ainda não migrou.

Nada toca banco: o cursor é dublê e o `get_db_conn` é substituído.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
# Chave Fernet fixa e descartável: os testes cifram/decifram de verdade, sem
# depender do ambiente. Gerada com Fernet.generate_key(); não é usada em lugar
# nenhum além destes testes.
os.environ.setdefault("ORQUESTRA_CONN_KEY",
                      "K_sKzYfPUx9hgIP4f5hrZmm9XX0UclK9beFd9RlREdo=")
from api.main import app  # noqa: E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from routers.admin import mask_secret  # noqa: E402
from services import servicenow  # noqa: E402

ALVO = "https://cvpsnprod.service-now.com"


class CursorFalso:
    """Cursor de mentira sobre um dict de config — sem banco nenhum."""

    def __init__(self, linhas: dict):
        self.linhas = dict(linhas)
        self.gravado: list[tuple] = []
        self._resultado: list[tuple] = []

    def execute(self, sql: str, params=None):
        params = params or []
        if sql.strip().upper().startswith("SELECT"):
            chaves = [p for p in params]
            self._resultado = [(k, v) for k, v in self.linhas.items() if k in chaves]
        else:                                   # MERGE (upsert)
            self.gravado.append((params[0], params[1]))
            self.linhas[params[0]] = params[1]
        return self

    def fetchall(self):
        return list(self._resultado)

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
    """Substitui get_db_conn nos dois módulos que o importaram por nome."""
    estado = {"cur": CursorFalso({})}

    def _fabrica():
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.admin.get_db_conn", _fabrica)
    monkeypatch.setattr("services.servicenow.get_db_conn", _fabrica)
    return estado


# ═══════════ 1. a senha nunca volta para a tela ═════════════════════════════

def test_get_nao_devolve_a_senha(admin_client, banco):
    banco["cur"] = CursorFalso({
        servicenow.K_URL: ALVO, servicenow.K_USUARIO: "svc_orquestra",
        servicenow.K_SENHA: "gAAAAABtoken-cifrado-longo", servicenow.K_GRUPOS: "Engenharia",
        servicenow.K_HABILITADO: "1"})
    corpo = admin_client.post("/admin", json={"action": "servicenow_get"}).json()
    cfg = corpo["config"]
    assert cfg["tem_senha"] is True
    assert cfg["configurado"] is True
    assert "senha" not in cfg and "senha_enc" not in cfg
    assert "gAAAAAB" not in str(corpo), "o token cifrado não pode aparecer na resposta"


def test_get_sem_credencial_diz_incompleto(admin_client, banco):
    banco["cur"] = CursorFalso({servicenow.K_URL: ALVO})
    cfg = admin_client.post("/admin", json={"action": "servicenow_get"}).json()["config"]
    assert cfg["tem_senha"] is False
    assert cfg["configurado"] is False


# ═══════════ 2. o mascaramento no config_list ═══════════════════════════════

def test_senha_do_servicenow_e_mascarada():
    """A chave é servicenow_senha_enc: não contém secret/password/token."""
    saida = mask_secret("servicenow_senha_enc", "gAAAAABtoken-cifrado-1234")
    assert saida == "•••• 1234"
    assert "gAAAAAB" not in saida


@pytest.mark.parametrize("chave", [
    "servicenow_senha_enc", "caixa_ia_api_key_enc", "teams_webhook_url",
    "algum_secret", "db_password", "api_token",
])
def test_todo_segredo_conhecido_e_mascarado(chave):
    assert mask_secret(chave, "valor-secreto-9999").startswith("••••")


@pytest.mark.parametrize("chave", ["servicenow_url", "servicenow_usuario",
                                   "servicenow_grupos", "app_base_url"])
def test_o_que_nao_e_segredo_passa_em_claro(chave):
    """Mascarar demais esconderia a URL e o usuário de quem opera."""
    assert mask_secret(chave, "valor-visivel") == "valor-visivel"


def test_valor_vazio_nao_vira_bolinhas():
    assert mask_secret("servicenow_senha_enc", "") == ""


# ═══════════ 3. gravação: senha vazia mantém a atual ════════════════════════

def test_salvar_sem_senha_preserva_a_atual(admin_client, banco):
    """Trocar só o grupo não pode apagar a credencial."""
    banco["cur"] = CursorFalso({
        servicenow.K_URL: ALVO, servicenow.K_USUARIO: "svc",
        servicenow.K_SENHA: "token-antigo", servicenow.K_HABILITADO: "0"})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "grupos": "Engenharia de Dados", "senha": ""})
    assert r.status_code == 200
    gravadas = dict(banco["cur"].gravado)
    assert servicenow.K_SENHA not in gravadas, "senha vazia não pode ser gravada"
    assert banco["cur"].linhas[servicenow.K_SENHA] == "token-antigo"
    assert gravadas[servicenow.K_GRUPOS] == "Engenharia de Dados"


def test_salvar_com_senha_cifra(admin_client, banco):
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "senha": "s3nh4-em-claro"})
    assert r.status_code == 200
    token = dict(banco["cur"].gravado)[servicenow.K_SENHA]
    assert token != "s3nh4-em-claro", "a senha não pode ir em claro para o banco"
    from services.conn_crypto import decrypt_password
    assert decrypt_password(token) == "s3nh4-em-claro"


def test_url_invalida_e_recusada_na_gravacao(admin_client, banco):
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": "https://evil.com", "usuario": "svc"})
    assert r.status_code == 422
    assert not banco["cur"].gravado, "nada pode ser gravado com URL recusada"


# ═══════════ 4. habilitar exige credencial completa ═════════════════════════

def test_habilitar_sem_senha_e_recusado(admin_client, banco):
    """Senão o sync agendado falharia de 3 em 3h com o operador achando que ligou."""
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "senha": "", "habilitado": True})
    assert r.status_code == 422
    assert "senha" in r.json()["detail"].lower()


def test_habilitar_com_credencial_completa_passa(admin_client, banco):
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "senha": "s3nh4", "habilitado": True})
    assert r.status_code == 200
    assert dict(banco["cur"].gravado)[servicenow.K_HABILITADO] == "1"


# ═══════════ 5. a credencial executora nomeia o que falta ═══════════════════

def test_credencial_executora_nomeia_o_que_falta():
    with pytest.raises(HTTPException) as e:
        servicenow.credencial_executora({"url": ALVO, "usuario": "", "senha_enc": ""})
    detalhe = e.value.detail
    assert "usuário" in detalhe and "senha" in detalhe
    assert "URL" not in detalhe, "não pode culpar o que ESTÁ preenchido"


def test_credencial_executora_decifra():
    from services.conn_crypto import encrypt_password
    cfg = {"url": ALVO, "usuario": "svc", "senha_enc": encrypt_password("abc123")}
    assert servicenow.credencial_executora(cfg) == (ALVO, "svc", "abc123")


# ═══════════ 6. degradação e utilitários ════════════════════════════════════

def test_load_config_sem_a_migration_nao_explode(monkeypatch):
    """Ambiente sem a 088/089: config vazia e dita, nunca exceção.

    O `proxy: ""` faz parte do contrato de degradação: ambiente sem a
    migration 089 precisa cair em rota DIRETA, não em KeyError no worker.
    """
    def _quebra():
        raise RuntimeError("Invalid object name 'dbo.etl_app_config'")
    monkeypatch.setattr("services.servicenow.get_db_conn", _quebra)
    cfg = servicenow.load_config()
    assert cfg == {"url": "", "usuario": "", "senha_enc": "", "grupos": "",
                   "habilitado": False, "proxy": ""}
    assert servicenow.configurado(cfg) is False


@pytest.mark.parametrize("bruto,esperado", [
    ("A; B ;;C", ["A", "B", "C"]),
    ("Engenharia de Dados", ["Engenharia de Dados"]),
    ("", []),
    ("  ;  ", []),
])
def test_parse_grupos(bruto, esperado):
    assert servicenow.parse_grupos(bruto) == esperado


@pytest.mark.parametrize("valor,esperado", [
    ("1", True), ("0", False), ("true", False), ("sim", False), ("", False),
])
def test_habilitado_so_com_o_literal_um(banco, valor, esperado):
    """Qualquer valor fora de '1' é desligado — 'true'/'sim' digitados direto
    no banco não podem ligar o sync agendado por acidente."""
    banco["cur"] = CursorFalso({servicenow.K_HABILITADO: valor})
    assert servicenow.load_config()["habilitado"] is esperado


# ═══════════ 7. a rota de saída (proxy, migration 089) ══════════════════════
# O sync roda no airflow-worker, que NÃO herda o HTTPS_PROXY do orquestra-api
# — foi o "Connection reset by peer" nas quatro tabelas. A rota virou config
# em vez de variável de ambiente porque variável só entra em container novo, e
# recriar o worker mata as tasks em execução.

def test_proxy_e_gravado_e_volta_na_leitura(admin_client, banco):
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "senha": "x", "proxy": "http://webproxycvp.adcorp.intranet/"})
    assert r.status_code == 200
    gravadas = dict(banco["cur"].gravado)
    assert gravadas[servicenow.K_PROXY] == "http://webproxycvp.adcorp.intranet/"


def test_proxy_volta_em_claro_para_a_tela(admin_client, banco):
    """Não é segredo — e é a PRIMEIRA coisa a conferir quando o sync dá erro
    de rede. Mascarar aqui esconderia justamente o campo do diagnóstico."""
    banco["cur"] = CursorFalso({servicenow.K_PROXY: "http://proxy:8080"})
    cfg = admin_client.post("/admin", json={"action": "servicenow_get"}).json()
    assert cfg["config"]["proxy"] == "http://proxy:8080"


def test_proxy_vazio_e_aceito_e_significa_direto(admin_client, banco):
    """Ambiente sem firewall de saída (o dev) grava vazio e funciona."""
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc", "proxy": ""})
    assert r.status_code == 200
    assert dict(banco["cur"].gravado)[servicenow.K_PROXY] == ""


def test_proxy_sem_esquema_e_recusado(admin_client, banco):
    """'webproxy:8080' sem http:// faz o httpx levantar erro de rede — o
    mesmo sintoma de firewall, com causa que está na tela."""
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "proxy": "webproxycvp.adcorp.intranet:8080"})
    assert r.status_code == 422
    assert not banco["cur"].gravado, "nada gravado com proxy recusado"


def test_proxy_com_espaco_no_meio_e_recusado(admin_client, banco):
    """Colar de um chat traz espaço invisível; o erro seria idêntico ao de
    firewall e o operador caçaria a rede em vez do campo."""
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "proxy": "http://web proxy:8080"})
    assert r.status_code == 422


@pytest.mark.parametrize("valor", ["ftp://proxy:21", "socks5://proxy:1080",
                                   "file:///etc/passwd", "//proxy:8080"])
def test_esquema_estranho_e_recusado(admin_client, banco, valor):
    banco["cur"] = CursorFalso({})
    r = admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "proxy": valor})
    assert r.status_code == 422


def test_proxy_e_aparado_antes_de_gravar(admin_client, banco):
    banco["cur"] = CursorFalso({})
    admin_client.post("/admin", json={
        "action": "servicenow_set", "url": ALVO, "usuario": "svc",
        "proxy": "  http://proxy:8080  "})
    assert dict(banco["cur"].gravado)[servicenow.K_PROXY] == "http://proxy:8080"
