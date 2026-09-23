"""Versões do domínio do prompt (A1 de docs/spec-agentes-admin.md §3.2–§3.5).

O que se prende, e por quê:

  1. **Regra de segredo** — a tabela da §3.3, testada na 3ª revisão da spec:
     recusa credencial de verdade e aceita texto normal de prompt; o prompt
     padrão inteiro não dispara (senão restaurar a versão 0 seria recusado).
  2. **Validação antes do banco** — um 422 não abre conexão.
  3. **Só acrescenta** — gravar e restaurar criam a versão seguinte; nenhum
     UPDATE/DELETE em `etl_agente_prompt`.
  4. **Concorrência** — `versao_base` velha e a corrida no UNIQUE viram 409.
  5. **Vale na próxima pergunta** — o router lê a versão ativa a cada
     pergunta, passa o domínio ao `conversar` e grava versão+hash na resposta;
     falha de leitura cai no padrão sem derrubar o chat.
  6. **Só admin**, e agente fora do catálogo é 404.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_prompt as apr  # noqa: E402
from tests.test_agentes_f6_rota import _BancoRota, _CursorRota  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PADRAO = svc.PROMPT_DOMINIO_PADRAO[svc.AGENTE_DATASTAGE].strip()  # o padrão é servido aparado
URL = "/agentes/admin/agentes/datastage/prompt"


# ═══════════ dublê: etl_agente_prompt com transação e UNIQUE ══════════════

class _BancoPrompt(_BancoRota):
    def __init__(self):
        self.prompts: list[dict] = []
        self.falhar_leitura = False
        self.antes_do_insert = None  # simula outro admin gravando no meio
        self.erro_no_insert = None   # exceção que o INSERT levanta (ex.: deadlock)
        self.aberturas = 0
        super().__init__()

    def _fixar(self):
        super()._fixar()
        self._salvo_pr = copy.deepcopy(getattr(self, "prompts", []))

    def rollback(self):
        super().rollback()
        self.prompts = copy.deepcopy(self._salvo_pr)

    def cursor(self):
        return _CursorPrompt(self)

    def gravar(self, versao, texto, *, agente="datastage", motivo="m", por="ADM1", origem=None, criado_em=None):
        self.prompts.append({"agente_id": agente, "versao": versao, "texto": texto, "motivo": motivo,
                             "origem_versao": origem, "criado_em": criado_em or self.agora(), "criado_por": por})
        self._fixar()


class _CursorPrompt(_CursorRota):
    def execute(self, sql, params=None):
        b = self.b
        p = list(params or ())
        s = " ".join(sql.lower().split())
        if s == "select getdate()":
            self._rows = [(b.agora(),)]
            return
        if s.startswith("select m.artefatos_json from dbo.etl_agente_mensagem m join"):
            # o dublê só tem conversas do DataStage
            self._rows = [] if p[0] != "datastage" else [
                (m["artefatos"],) for msgs in b.mensagens.values() for m in msgs
                if m["papel"] == "assistant" and m["artefatos"] and "prompt_versao" in m["artefatos"]]
            return
        if "etl_agente_prompt" not in s:
            return super().execute(sql, params)
        b.execs.append((sql, tuple(p)))
        self._rows, self.rowcount = [], -1

        def linha(r):
            return (r["versao"], r["texto"], r["motivo"], r["origem_versao"], r["criado_em"], r["criado_por"])

        do_agente = sorted((r for r in b.prompts if r["agente_id"] == p[0]), key=lambda r: -r["versao"])
        if s.startswith("select"):
            if b.falhar_leitura:
                raise RuntimeError("Invalid object name 'dbo.etl_agente_prompt'")
            if "and versao = ?" in s:
                self._rows = [linha(r) for r in do_agente if r["versao"] == p[1]]
            elif "top 1" in s:
                self._rows = [linha(r) for r in do_agente[:1]]
            else:
                self._rows = [linha(r) for r in do_agente]
        elif s.startswith("insert into dbo.etl_agente_prompt"):
            if b.antes_do_insert:
                f, b.antes_do_insert = b.antes_do_insert, None
                f(b)
            agente, versao, texto, motivo, origem, por = p
            if b.erro_no_insert:
                raise b.erro_no_insert
            if any(r["agente_id"] == agente and r["versao"] == versao for r in b.prompts):
                raise RuntimeError("Violation of UNIQUE KEY constraint 'UQ_etl_agente_prompt_versao'. (2627)")
            b.prompts.append({"agente_id": agente, "versao": versao, "texto": texto, "motivo": motivo,
                              "origem_versao": origem, "criado_em": b.agora(), "criado_por": por})
        else:
            raise AssertionError(f"SQL inesperado em etl_agente_prompt: {sql}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


@pytest.fixture
def ambiente():
    estado = {"perms": ["tela_agentes", PERM_ADMIN], "matricula": "ADM1", "perfil": "admin", "extras": []}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": estado["matricula"], "perfil": estado["perfil"],
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    banco = _BancoPrompt()

    def _abre():
        banco.aberturas += 1
        return banco
    with patch("routers.agentes.get_db_conn", side_effect=_abre):
        yield TestClient(_app), banco, estado
    _app.dependency_overrides.pop(get_current_user, None)


def _put(cliente, texto="Você é o agente de teste.", motivo="ajuste de teste", versao_base=0):
    return cliente.put(URL, json={"texto": texto, "motivo": motivo, "versao_base": versao_base})


# ═══════════ 1. regra de segredo (tabela da §3.3) ═════════════════════════

RECUSA = ["senha=$enha123!", "senha=#abc123",  # não são referência (forma estrita)
          "senha=Abc123", "PWD=Xk2!pz", "api_key=9f8e7d6c5b", "DB_PASSWORD=Abc123!", "client_secret=Xy9zAbcdef",
          "access_token=abcdef123456", '"senha": "Abc123"', "password: S3nh@Forte",
          "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv", "sk-proj-AbCdEfGhIjKlMnOpQrStUv",
          "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdef", "-----BEGIN RSA PRIVATE KEY-----",
          "senha:\xa0Abc123!", "senha\xa0=\xa0Abc123!"]  # NBSP de texto colado do Word/Outlook
ACEITA = ["nunca peça a senha ao usuário", "Senha: nunca peça", "parâmetros do tipo Encrypted",
          "o stage TokenizerTransform", "secretaria de vendas", "pwd=#PS_ORA.PWD#", "senha=$PS_BD.senha",
          "password: #PS_CONEXAO.password#", "senha=********", "PWD=<valor>", 'token: {"job_name": "X"}',
          "risk-assessment-flow-da-area-de-riscos", "disk-usage", "o token expira em 1 hora",
          "Nunca proponha senha, token ou valor de parâmetro"]


@pytest.mark.parametrize("texto", RECUSA)
def test_credencial_e_recusada(texto):
    assert apr.tem_segredo(texto), texto
    with pytest.raises(apr.PromptInvalido) as e:
        apr.validar_texto(f"Você é um agente.\n{texto}\n")
    assert e.value.code == "prompt_com_segredo"


@pytest.mark.parametrize("texto", ACEITA)
def test_texto_normal_passa(texto):
    assert not apr.tem_segredo(texto), texto


def test_prompt_padrao_inteiro_passa_na_validacao():
    """Restaurar a versão 0 precisa passar — e o prompt MONTADO também não
    dispara (o bloco de propostas fala em "senha, token")."""
    assert apr.validar_texto(PADRAO) == PADRAO
    assert not apr.tem_segredo(svc._prompt_sistema("BI_CVP"))


# ═══════════ validações puras ═════════════════════════════════════════════

@pytest.mark.parametrize("texto, code", [
    ("", "prompt_vazio"), ("   \n ", "prompt_vazio"), (None, "prompt_vazio"),
    ("x" * (apr.TEXTO_MAX + 1), "prompt_grande"), (123, "prompt_invalido"),
    ('Termine com {"ferramenta": "base"}', "prompt_com_marcador"),
    ('responda {"propostas": []}', "prompt_com_marcador"),
    ("use <aprendizados>", "prompt_com_marcador"),
])
def test_validar_texto_codigos(texto, code):
    with pytest.raises(apr.PromptInvalido) as e:
        apr.validar_texto(texto)
    assert e.value.code == code


def test_texto_no_limite_passa_e_e_aparado():
    assert apr.validar_texto("  " + "x" * apr.TEXTO_MAX + "  ") == "x" * apr.TEXTO_MAX


@pytest.mark.parametrize("motivo", ["", "ab", None, 5, "x" * 201, "😀" * 101])
def test_motivo_invalido(motivo):
    """O teto é em unidades UTF-16 (o que o NVARCHAR(200) conta): 101 emojis
    são 101 caracteres, mas 202 unidades."""
    with pytest.raises(apr.PromptInvalido) as e:
        apr.validar_motivo(motivo)
    assert e.value.code == "motivo_obrigatorio"


def test_motivo_no_limite_utf16_passa():
    assert apr.validar_motivo("😀" * 100) == "😀" * 100


@pytest.mark.parametrize("v", [None, "1", True, -1, 1.0, 2**31, 10**30])
def test_versao_base_invalida(v):
    with pytest.raises(apr.PromptInvalido) as e:
        apr.validar_versao(v)
    assert e.value.code == "versao_base_invalida"


# ═══════════ 6. só admin; agente desconhecido ═════════════════════════════

def _todas(cliente, agente="datastage"):
    base = f"/agentes/admin/agentes/{agente}/prompt"
    corpo = {"texto": "t válido", "motivo": "motivo", "versao_base": 0}
    return [cliente.get(base), cliente.put(base, json=corpo), cliente.get(base + "/versoes"),
            cliente.get(base + "/versoes/0"),
            cliente.post(base + "/restaurar", json={"versao": 0, "motivo": "motivo", "versao_base": 0})]


def test_nao_admin_e_403_em_todos(ambiente):
    cliente, banco, estado = ambiente
    estado["perms"], estado["perfil"], estado["extras"] = ["tela_agentes"], "desenvolvedor", ["agente_datastage"]
    assert [r.status_code for r in _todas(cliente)] == [403] * 5
    assert banco.prompts == []


def test_agente_desconhecido_e_404_sem_tocar_o_banco(ambiente):
    cliente, banco, _ = ambiente
    for r in _todas(cliente, "nao_existe"):
        assert r.status_code == 404 and r.json()["detail"]["code"] == "agente_desconhecido"
    assert banco.aberturas == 0


# ═══════════ leitura ══════════════════════════════════════════════════════

def test_sem_versao_a_ativa_e_o_padrao_e_a_parte_fixa_vem_montada(ambiente):
    cliente, _, _ = ambiente
    r = cliente.get(URL).json()
    assert r["ativa"]["versao"] == 0 and r["ativa"]["padrao"] is True
    assert r["ativa"]["texto"] == PADRAO and r["ativa"]["hash"] == apr.hash_do_texto(PADRAO)
    antes, depois = r["parte_fixa"]["antes"], r["parte_fixa"]["depois"]
    assert antes.startswith("## Contexto desta conversa") and "<projeto da conversa>" in antes
    for trecho in ("## Como usar as ferramentas", "## Regras que valem sempre", "## Propostas e aprendizados"):
        assert trecho in depois
    assert "Ordem de custo" not in antes + depois  # o domínio não vai na parte fixa
    # é exatamente o que o prompt usa, não uma cópia
    montado = svc._prompt_sistema("<projeto da conversa>")
    assert montado == f"{antes}\n\n{PADRAO.strip()}\n\n{depois}\n"
    assert r["limites"] == {"texto_max": apr.TEXTO_MAX, "motivo_min": 3, "motivo_max": 200}


# ═══════════ 2. validação antes do banco ══════════════════════════════════

@pytest.mark.parametrize("corpo, code", [
    ({"texto": "", "motivo": "motivo", "versao_base": 0}, "prompt_vazio"),
    ({"texto": "senha=Abc123", "motivo": "motivo", "versao_base": 0}, "prompt_com_segredo"),
    ({"texto": '{"ferramenta": "x"}', "motivo": "motivo", "versao_base": 0}, "prompt_com_marcador"),
    ({"texto": "ok ok", "motivo": "", "versao_base": 0}, "motivo_obrigatorio"),
    ({"texto": "ok ok", "motivo": "motivo"}, "versao_base_invalida"),
])
def test_put_invalido_e_422_sem_abrir_conexao(ambiente, corpo, code):
    cliente, banco, _ = ambiente
    r = cliente.put(URL, json=corpo)
    assert r.status_code == 422 and r.json()["detail"]["code"] == code
    assert banco.aberturas == 0 and banco.prompts == []


def test_restaurar_invalido_e_422_sem_abrir_conexao(ambiente):
    cliente, banco, _ = ambiente
    r = cliente.post(URL + "/restaurar", json={"versao": "1", "motivo": "motivo", "versao_base": 0})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "versao_invalida"
    assert banco.aberturas == 0


# ═══════════ 3. gravar e restaurar só acrescentam ═════════════════════════

def test_put_grava_a_versao_seguinte_com_autor_e_motivo(ambiente):
    cliente, banco, _ = ambiente
    r = _put(cliente, texto="  Domínio novo.  ", motivo="primeiro ajuste")
    assert r.status_code == 200
    ativa = r.json()["ativa"]
    assert ativa["versao"] == 1 and ativa["texto"] == "Domínio novo." and ativa["padrao"] is False
    [linha] = banco.prompts
    assert linha == {**linha, "versao": 1, "texto": "Domínio novo.", "motivo": "primeiro ajuste",
                     "criado_por": "ADM1", "origem_versao": None}
    assert _put(cliente, texto="Outro.", versao_base=1).json()["ativa"]["versao"] == 2
    assert cliente.get(URL).json()["ativa"]["texto"] == "Outro."


def test_listar_versoes_da_mais_nova_ate_o_padrao_sem_texto(ambiente):
    cliente, _, _ = ambiente
    _put(cliente, texto="Um.")
    _put(cliente, texto="Dois.", versao_base=1)
    r = cliente.get(URL + "/versoes").json()
    assert r["ativa"] == 2
    assert [v["versao"] for v in r["versoes"]] == [2, 1, 0]
    assert [v["padrao"] for v in r["versoes"]] == [False, False, True]
    assert all("texto" not in v for v in r["versoes"])
    assert r["versoes"][2]["hash"] == apr.hash_do_texto(PADRAO)


def test_ver_uma_versao(ambiente):
    cliente, _, _ = ambiente
    _put(cliente, texto="Um.")
    assert cliente.get(URL + "/versoes/1").json()["versao"]["texto"] == "Um."
    assert cliente.get(URL + "/versoes/0").json()["versao"]["texto"] == PADRAO
    for v in (2, 99, -1):
        r = cliente.get(URL + f"/versoes/{v}")
        assert r.status_code == 404 and r.json()["detail"]["code"] == "versao_nao_encontrada"


def test_restaurar_cria_versao_nova_com_a_origem(ambiente):
    cliente, banco, _ = ambiente
    _put(cliente, texto="Um.")
    _put(cliente, texto="Dois.", versao_base=1)
    r = cliente.post(URL + "/restaurar", json={"versao": 1, "motivo": "voltar ao um", "versao_base": 2})
    assert r.status_code == 200
    assert r.json()["ativa"]["versao"] == 3 and r.json()["ativa"]["texto"] == "Um."
    assert banco.prompts[-1]["origem_versao"] == 1
    assert [p["texto"] for p in banco.prompts] == ["Um.", "Dois.", "Um."]  # nada sobrescrito


def test_restaurar_a_versao_zero_grava_o_padrao_atual(ambiente):
    cliente, banco, _ = ambiente
    _put(cliente, texto="Um.")
    r = cliente.post(URL + "/restaurar", json={"versao": 0, "motivo": "de volta ao padrão", "versao_base": 1})
    assert r.status_code == 200 and r.json()["ativa"]["versao"] == 2
    assert banco.prompts[-1]["texto"] == PADRAO and banco.prompts[-1]["origem_versao"] == 0
    # mesmo texto efetivo → mesmo hash e tamanho da versão 0 (útil para o BK-1)
    versoes = cliente.get(URL + "/versoes").json()["versoes"]
    assert versoes[0]["hash"] == versoes[-1]["hash"] and versoes[0]["tamanho"] == versoes[-1]["tamanho"]


def test_restaurar_versao_inexistente_e_404_e_nao_grava(ambiente):
    cliente, banco, _ = ambiente
    r = cliente.post(URL + "/restaurar", json={"versao": 7, "motivo": "motivo", "versao_base": 0})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "versao_nao_encontrada"
    assert banco.prompts == []


def test_restaurar_versao_que_hoje_nao_passa_e_422(ambiente):
    """Uma versão antiga gravada antes de uma regra nova não volta por esta
    porta sem passar pela régua de hoje."""
    cliente, banco, _ = ambiente
    banco.gravar(1, 'antigo com {"ferramenta": "base"}')
    r = cliente.post(URL + "/restaurar", json={"versao": 1, "motivo": "motivo", "versao_base": 1})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "prompt_com_marcador"
    assert len(banco.prompts) == 1


def test_nenhum_update_ou_delete_em_etl_agente_prompt(ambiente):
    cliente, banco, _ = ambiente
    _put(cliente, texto="Um.")
    cliente.post(URL + "/restaurar", json={"versao": 0, "motivo": "motivo", "versao_base": 1})
    sqls = [" ".join(q.lower().split()) for q, _ in banco.execs if "etl_agente_prompt" in q.lower()]
    assert sqls and not any(q.startswith(("update", "delete", "merge")) for q in sqls)
    fonte = (RAIZ / "api/services/agentes_prompt.py").read_text(encoding="utf-8").lower()
    assert "update dbo.etl_agente_prompt" not in fonte and "delete from dbo.etl_agente_prompt" not in fonte


# ═══════════ 4. concorrência ══════════════════════════════════════════════

def test_versao_base_velha_e_409_e_nao_grava(ambiente):
    cliente, banco, _ = ambiente
    _put(cliente, texto="Um.")
    r = _put(cliente, texto="Meu texto.", versao_base=0)
    assert r.status_code == 409
    assert r.json()["detail"] == {**r.json()["detail"], "code": "prompt_mudou", "versao_atual": 1}
    assert [p["texto"] for p in banco.prompts] == ["Um."]


def test_corrida_no_unique_vira_409(ambiente):
    """Outro admin grava ENTRE a leitura da versão ativa e o INSERT: o
    UNIQUE (agente_id, versao) recusa, e a resposta é 409 com a versão nova."""
    cliente, banco, _ = ambiente
    banco.antes_do_insert = lambda b: b.gravar(1, "O outro admin.")
    r = _put(cliente, texto="Meu texto.", versao_base=0)
    assert r.status_code == 409 and r.json()["detail"]["versao_atual"] == 1
    assert [p["texto"] for p in banco.prompts] == ["O outro admin."]
    assert banco.rollbacks >= 1


def test_restaurar_com_base_velha_e_409(ambiente):
    cliente, banco, _ = ambiente
    _put(cliente, texto="Um.")
    r = cliente.post(URL + "/restaurar", json={"versao": 0, "motivo": "motivo", "versao_base": 0})
    assert r.status_code == 409 and len(banco.prompts) == 1


# ═══════════ 5. vale na próxima pergunta ══════════════════════════════════

@pytest.fixture
def chat(ambiente, monkeypatch):
    cliente, banco, estado = ambiente
    recebido: list = []

    async def _fake(abrir_conn, **kw):
        recebido.append(kw)
        return {"status": "ok", "texto": "resposta", "projeto": "BI_CVP", "artefatos": []}
    monkeypatch.setattr(svc, "conversar", _fake)
    return cliente, banco, recebido


def _artefatos_da_ultima_resposta(banco):
    [msgs] = banco.mensagens.values() if len(banco.mensagens) == 1 else [list(banco.mensagens.values())[-1]]
    return json.loads([m for m in msgs if m["papel"] == "assistant"][-1]["artefatos"])


def test_pergunta_sem_versao_usa_o_padrao_e_grava_versao_zero(chat):
    cliente, banco, recebido = chat
    assert cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"}).status_code == 200
    assert recebido[-1]["dominio"] == PADRAO
    assert {"prompt_versao": 0, "prompt_hash": apr.hash_do_texto(PADRAO)} in _artefatos_da_ultima_resposta(banco)


def test_versao_gravada_vale_na_proxima_pergunta_sem_restart(chat):
    cliente, banco, recebido = chat
    cid = "conversa-teste-01"
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi", "conversa_id": cid})
    assert recebido[-1]["dominio"] == PADRAO
    _put(cliente, texto="Domínio editado pelo admin.")
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "de novo", "conversa_id": cid})
    assert recebido[-1]["dominio"] == "Domínio editado pelo admin."
    assert {"prompt_versao": 1, "prompt_hash": apr.hash_do_texto("Domínio editado pelo admin.")} \
        in _artefatos_da_ultima_resposta(banco)


def test_falha_na_leitura_do_prompt_nao_derruba_o_chat(chat):
    cliente, banco, recebido = chat
    banco.gravar(1, "Versão que não dá para ler.")
    banco.falhar_leitura = True
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert r.status_code == 200
    assert recebido[-1]["dominio"] == PADRAO
    assert {"prompt_versao": 0, "prompt_hash": apr.hash_do_texto(PADRAO)} in _artefatos_da_ultima_resposta(banco)


def test_rastreio_nao_aparece_como_ferramenta_ao_retomar(chat):
    """`_separar_artefatos` ignora a chave nova: a linha "Consultei:" e os
    cartões continuam só com ferramenta e proposta."""
    from routers.agentes import _separar_artefatos
    ferramentas, ids, duracao = _separar_artefatos(
        [{"ferramenta": "base", "args": {}}, {"duracao_ms": 5}, {"prompt_versao": 3, "prompt_hash": "abc"}])
    assert ferramentas == [{"ferramenta": "base", "args": {}}] and ids == [] and duracao == 5


def test_agente_sem_padrao_no_codigo_propaga_a_falha_de_leitura():
    """Fase B: agente do banco não tem para onde cair — o chamador dá 503."""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("Invalid object name")
    with pytest.raises(RuntimeError):
        apr.dominio_em_uso(cur, "agente_sem_padrao")


# ═══════════ o domínio chega ao prompt montado ════════════════════════════

@pytest.mark.asyncio
async def test_conversar_monta_o_prompt_com_o_dominio_recebido(monkeypatch):
    from services import agentes_ferramentas as af
    from services import ia_provedor
    from tests._banco_agentes_f6 import BancoF6
    sistemas: list = []

    async def _provedor(cfg, sistema, historico, identidade=None, campo_identidade=None):
        sistemas.append(sistema)
        return "resposta direta", "modelo-teste"
    monkeypatch.setattr(ia_provedor, "chat_conversa", _provedor)
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda nome: False)
    banco = BancoF6()
    await svc.conversar(banco.abrir, mensagens=[{"role": "user", "content": "oi"}], projeto_atual="BI_CVP",
                        provedor_cfg={}, identidade="cvp-dev1", campo_identidade=None, ssh_max=10,
                        matricula="DEV1", dominio="DOMÍNIO DE TESTE")
    assert "DOMÍNIO DE TESTE" in sistemas[0] and "Ordem de custo" not in sistemas[0]
    assert "## Como usar as ferramentas" in sistemas[0]


# ═══════════ lacunas apontadas pela revisão adversarial da A1 ═════════════

@pytest.mark.parametrize("texto", ["a_" * 10000, "ab1_" * 5000, "a_" * 9990 + "senha",
                                   "senha=" * 3333, ("token: " + "a" * 50 + " ") * 300])
def test_regra_de_segredo_e_linear_no_pior_caso(texto):
    """A 1ª versão da regex era quadrática: "a_" * 10000 levava ~10 s de CPU
    dentro do event loop. O teto aqui é folgado para máquina lenta."""
    import time
    t0 = time.perf_counter()
    apr.tem_segredo(texto[: apr.TEXTO_MAX])
    assert time.perf_counter() - t0 < 0.5


def test_migration_120_tem_o_unique_que_barra_a_corrida():
    sql = (RAIZ / "sql/migrations/120_agentes_prompt.sql").read_text(encoding="utf-8")
    assert "CONSTRAINT UQ_etl_agente_prompt_versao UNIQUE (agente_id, versao)" in sql
    assert "UQ_etl_agente_prompt_versao" in (RAIZ / "api/services/agentes_prompt.py").read_text(encoding="utf-8")


def test_erro_do_insert_que_nao_e_unique_nao_vira_409(ambiente):
    """Deadlock/timeout no INSERT é erro do servidor, não "outro admin gravou"."""
    cliente, banco, _ = ambiente
    banco.erro_no_insert = RuntimeError("Transaction was deadlocked on lock resources (1205)")
    r = TestClient(_app, raise_server_exceptions=False).put(
        URL, json={"texto": "Texto.", "motivo": "motivo", "versao_base": 0})
    assert r.status_code == 500
    assert banco.prompts == [] and banco.rollbacks >= 1


def test_hash_e_sha256_com_12_hex():
    import hashlib
    h = apr.hash_do_texto("abc")
    assert h == hashlib.sha256(b"abc").hexdigest()[:12] and len(h) == 12


def test_fallback_registra_warning(chat, caplog):
    cliente, banco, _ = chat
    banco.falhar_leitura = True
    with caplog.at_level("WARNING", logger="services.agentes_prompt"):
        cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert any("usando o padrão do código" in r.getMessage() for r in caplog.records)


def test_versao_enorme_e_422_ou_404_sem_abrir_conexao(ambiente):
    cliente, banco, _ = ambiente
    r = cliente.get(URL + f"/versoes/{2**63}")
    assert r.status_code in (404, 422)
    r = cliente.post(URL + "/restaurar", json={"versao": 10**30, "motivo": "motivo", "versao_base": 0})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "versao_invalida"
    r = cliente.put(URL, json={"texto": "Texto.", "motivo": "motivo", "versao_base": 10**30})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "versao_base_invalida"
    assert banco.aberturas == 0


# ═══════════ BK-1: vigência e uso de cada versão ══════════════════════════

def test_vigencia_pura_inicio_fim_e_duracao():
    import datetime as dt
    t = dt.datetime(2026, 9, 23, 10, 0, 0)
    versoes = [{"versao": 2, "criado_em": t + dt.timedelta(hours=3)}, {"versao": 1, "criado_em": t}]
    v = apr.vigencia(versoes, agora=t + dt.timedelta(hours=5))
    assert v[0] == {"vigente_de": None, "vigente_ate": t, "duracao_s": None}   # padrão: desde o deploy
    assert v[1] == {"vigente_de": t, "vigente_ate": t + dt.timedelta(hours=3), "duracao_s": 3 * 3600}
    assert v[2] == {"vigente_de": t + dt.timedelta(hours=3), "vigente_ate": None, "duracao_s": 2 * 3600}


def test_vigencia_sem_versao_gravada_so_tem_a_zero_ativa_sem_inicio():
    assert apr.vigencia([], agora=object()) == {0: {"vigente_de": None, "vigente_ate": None, "duracao_s": None}}


def test_listar_versoes_traz_vigencia_duracao_e_respostas(chat):
    import datetime as dt
    cliente, banco, _ = chat
    t = dt.datetime(2026, 9, 23, 10, 0, 0)
    banco.deslocamento = t - dt.datetime.now()          # "agora" do banco = 10:00
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "com o padrão"})      # v0
    _put(cliente, texto="Um.")                                                           # v1 às 10:00
    banco.deslocamento += dt.timedelta(hours=2)
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "com a v1"})          # v1
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "de novo com a v1"})  # v1
    _put(cliente, texto="Dois.", versao_base=1)                                          # v2 às 12:00
    banco.deslocamento += dt.timedelta(minutes=30)                                        # agora 12:30
    r = cliente.get(URL + "/versoes").json()
    por = {v["versao"]: v for v in r["versoes"]}
    assert por[1]["vigente_de"] == "2026-09-23 10:00:00" and por[1]["vigente_ate"] == "2026-09-23 12:00:00"
    assert por[1]["duracao_s"] == 2 * 3600 and por[1]["respostas"] == 2
    assert por[2]["vigente_ate"] is None and por[2]["duracao_s"] == 30 * 60 and por[2]["respostas"] == 0
    assert por[0]["vigente_de"] is None and por[0]["vigente_ate"] == "2026-09-23 10:00:00"
    assert por[0]["respostas"] == 1 and por[0]["duracao_s"] is None
    assert isinstance(por[1]["duracao_media_ms"], int)
    assert r["agora"] == "2026-09-23 12:30:00" and r["retencao_dias"] == svc.RETENCAO_CONVERSAS_DIAS


def test_uso_ignora_artefato_torto_e_conta_sem_duracao():
    cur = MagicMock()
    cur.fetchall.return_value = [
        ('[{"prompt_versao": 1, "prompt_hash": "x"}, {"duracao_ms": 100}]',),
        ('[{"prompt_versao": 1}, {"duracao_ms": 300}]',),
        ('[{"prompt_versao": 1}]',),                    # sem duração: conta a resposta, não a média
        ('não é json',), ('{"prompt_versao": 1}',), (None,),
        ('[{"prompt_versao": true}, {"prompt_versao": "2"}]',),
    ]
    assert apr.uso_por_versao(cur, "datastage") == {1: {"respostas": 3, "duracao_media_ms": 200}}
    sql, params = cur.execute.call_args[0]
    assert "c.agente = ?" in sql and params == ["datastage", '%"prompt_versao"%']
