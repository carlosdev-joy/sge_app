"""Achados da auditoria de segurança FINAL (F7) da entrega dos agentes.

  1. A conversa guardada no navegador é por USUÁRIO (chave com a matrícula) e
     sai no logout/sessão expirada — antes, o próximo usuário da mesma estação
     via a última conversa do anterior.
  2. O nome de colaborador (`_resolver_matriculas`) vai ao MODELO, mas não à
     evidência — que pode virar aprendizado, que não vence.
  3. Teto de 2 rodadas em andamento por usuário (429 nomeado), nos dois
     endpoints; a vaga volta quando a rodada termina — inclusive com erro.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from deps import get_current_user  # noqa: E402
from routers import agentes as rota  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402
from tests.test_agentes_f6_rota import _BancoRota  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"


def _codigo(p: Path) -> str:
    fonte = re.sub(r"/\*.*?\*/", " ", p.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


# ═══════════ 1. conversa no navegador por usuário ════════════════════════

def test_chave_do_navegador_tem_a_matricula():
    lib = _codigo(FRONT / "lib" / "agentes.ts")
    assert "export function chaveDaConversa(agenteId: string, matricula: string)" in lib
    assert "${PREFIXO_CONVERSA_AGENTE}${matricula.trim().toUpperCase()}_${agenteId}" in lib
    pagina = _codigo(FRONT / "pages" / "Agentes.tsx")
    assert "useAuthStore(s => s.user?.matricula ?? '')" in pagina
    assert "if (!matricula) return null" in pagina and "if (!matricula) return" in pagina


def test_prefixo_da_chave_e_o_mesmo_nos_dois_arquivos():
    """`lib/agentes.ts` monta a chave, `lib/api.ts` a apaga no logout — os dois
    são autocontidos (os harnesses os executam sozinhos), então o prefixo se
    repete e tem de ser igual."""
    padrao = r"export const PREFIXO_CONVERSA_AGENTE = '([^']+)'"
    a = re.search(padrao, _codigo(FRONT / "lib" / "agentes.ts")).group(1)
    b = re.search(padrao, _codigo(FRONT / "lib" / "api.ts")).group(1)
    assert a == b == "orquestra_agente_conversa_"


def test_logout_e_sessao_expirada_apagam_as_conversas_do_navegador():
    assert "esquecerConversasDeAgentes()" in _codigo(FRONT / "store" / "auth.ts")
    api = _codigo(FRONT / "lib" / "api.ts")
    corpo = api[api.index("export function expirarSessao"):]
    assert "esquecerConversasDeAgentes()" in corpo[:corpo.index("}")]


# ═══════════ 2. nome de colaborador fora da evidência ═════════════════════

class _Provedor:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def __call__(self, cfg, sistema, historico, identidade=None, campo_identidade=None):
        self.chamadas.append({"historico": list(historico)})
        return self.respostas.pop(0), "m"


@pytest.mark.asyncio
async def test_nome_vai_ao_modelo_mas_nao_a_evidencia(monkeypatch):
    async def _executor(fn, *args, teto):
        return fn(*args)
    monkeypatch.setattr(af, "isx_no_executor", _executor)
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG")
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda n: False)
    monkeypatch.setattr(af.lineage_isx, "extrair", lambda *a: (
        {"last_modified": "x"}, {"created_by": "CVP1", "stages": [{"stage_name": "Ler"}]}, False))
    monkeypatch.setattr(svc, "_resolver_matriculas",
                        lambda cur, p: p.update(created_by="Maria Souza (CVP1)"))
    registrados = []
    monkeypatch.setattr(svc, "_registrar_seguro", lambda abrir, a: registrados.append(a))
    # este teste não trata da guarda nem da recuperação (o cursor dublê diria "achei" a tudo)
    monkeypatch.setattr(svc, "_erro_conhecido_seguro", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_recuperar_seguro", lambda *a, **k: [])
    bloco = json.dumps({"aprendizados": [{"tipo": "leitura", "titulo": "t", "corpo": "c"}]})
    prov = _Provedor(['```json\n{"ferramenta": "isx_extrair", "args": {"job_name": "JobX"}}\n```',
                      f"ok\n```json\n{bloco}\n```"])
    monkeypatch.setattr(ia_provedor, "chat_conversa", prov)

    def _abrir():
        c = MagicMock()
        c.fetchall.return_value = []
        return c, c
    await svc.conversar(_abrir, mensagens=[{"role": "user", "content": "x"}], projeto_atual="BI_CVP",
                        provedor_cfg={}, identidade="x", campo_identidade=None, ssh_max=10,
                        acao_editar=True, matricula="DEV1")
    assert "Maria Souza" in prov.chamadas[1]["historico"][-1]["content"]  # o modelo recebe
    [sug] = [a for a in registrados if a and a.get("origem") == "interpretacao"]
    assert "Maria Souza" not in sug["evidencia"] and "CVP1" in sug["evidencia"]


# ═══════════ 3. teto de rodadas por usuário ═══════════════════════════════

@pytest.fixture
def ambiente():
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor", "permissoes": ["tela_agentes"],
        "permissoes_extra": ["agente_datastage"]}
    banco = _BancoRota()
    rota._RODADAS_POR_USUARIO.clear()
    with patch("routers.agentes.get_db_conn", side_effect=lambda: banco):
        yield TestClient(_app), banco
    rota._RODADAS_POR_USUARIO.clear()
    _app.dependency_overrides.pop(get_current_user, None)


def test_terceira_rodada_simultanea_e_429_sem_gravar(ambiente, monkeypatch):
    cliente, banco = ambiente
    rota._RODADAS_POR_USUARIO["DEV1"] = rota.MAX_RODADAS_POR_USUARIO

    async def _explode(*a, **k):
        raise AssertionError("não devia rodar")
    monkeypatch.setattr(svc, "conversar", _explode)
    for url in ("/agentes/datastage/conversar", "/agentes/datastage/conversar/stream"):
        r = cliente.post(url, json={"mensagem": "oi"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "rodadas_simultaneas"
    assert banco.conversas == {}  # nada gravado sem vaga


def test_vaga_volta_quando_a_rodada_termina_ou_falha(ambiente, monkeypatch):
    cliente, _banco = ambiente

    async def _ok(abrir_conn, **kw):
        return {"status": "ok", "texto": "t", "projeto": None, "artefatos": []}
    monkeypatch.setattr(svc, "conversar", _ok)
    for _ in range(3):
        assert cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"}).status_code == 200
    assert rota._RODADAS_POR_USUARIO == {}

    async def _falha(abrir_conn, **kw):
        raise RuntimeError("gateway caiu")
    monkeypatch.setattr(svc, "conversar", _falha)
    with pytest.raises(RuntimeError):
        cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert rota._RODADAS_POR_USUARIO == {}
    # validação que falha na preparação também devolve a vaga
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi", "conversa_id": "x"})
    assert rota._RODADAS_POR_USUARIO == {}


def test_stream_libera_a_vaga_no_fim(ambiente, monkeypatch):
    cliente, _banco = ambiente

    async def _ok(abrir_conn, emit_status=None, **kw):
        return {"status": "ok", "texto": "t", "projeto": None, "artefatos": []}
    monkeypatch.setattr(svc, "conversar", _ok)
    with cliente.stream("POST", "/agentes/datastage/conversar/stream", json={"mensagem": "oi"}) as r:
        r.read()
    assert rota._RODADAS_POR_USUARIO == {}
