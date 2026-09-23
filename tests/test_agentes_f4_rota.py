"""api/routers/agentes.py — histórico de conversas (F4 da spec
docs/spec-agentes-datastage.md): `GET /agentes/conversas` e `/{id}`.

Os critérios de aceite da F4 que vivem na API, e por que cada um importa:

  1. **Cada um vê só as suas** (critério 1). O `WHERE matricula = ?` vem da
     SESSÃO, nunca do corpo ou da query. E conversa alheia dá **404 igual
     ao de conversa inexistente** — um 403 só para a alheia diria "existe,
     mas não é sua", e isso transforma o endpoint num oráculo de ids.

  2. **30 dias valem na LEITURA** (critério 2), não só na purga noturna.
     Uma conversa de 31 dias some da lista e não pode ser retomada MESMO
     que a DAG não tenha rodado — senão um `conversa_id` guardado no
     navegador ressuscitaria o que a tela já não mostra.

  3. **A busca não é um padrão de LIKE.** `%` e `_` digitados são
     escapados; o SQL leva `ESCAPE '\\'`.

  4. **Só as últimas 12 rodadas vão ao gateway** — o histórico inteiro fica
     no banco e na tela, mas o prompt não cresce sem teto.

  5. **O título é cortado em unidades UTF-16**, a largura real do
     NVARCHAR(200) (critério 5 encosta aqui: o que é gravado é o que foi
     redigido, e no tamanho que a coluna aceita).

Banco é dublê; nada toca SQL Server de verdade.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from deps import get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402


class _Cur:
    """Dublê que responde por trecho do SQL e GUARDA o que foi executado —
    é sobre o SQL emitido que os testes de isolamento e de ESCAPE falam."""

    def __init__(self, *, conversas=None, mensagens=None, dono="DEV1", idade_dias=0):
        self.conversas = conversas if conversas is not None else []
        self.mensagens = mensagens or []
        self.dono = dono
        self.idade_dias = idade_dias
        self.execs: list[tuple[str, tuple]] = []
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = " ".join(sql.lower().split())
        if "from dbo.etl_agente_conversa" in s and "datediff" in s:
            # cabeçalho de UMA conversa (detalhe / conversar)
            self._rows = [] if self.dono is None else [
                ("BI_CVP", "titulo", "PIPE", None, None, self.dono, self.idade_dias)
                if "select agente" not in s else
                ("datastage", "titulo", "PIPE", None, None, self.dono, self.idade_dias)]
            if "select projeto, matricula" in s:
                self._rows = [] if self.dono is None else [("BI_CVP", self.dono, self.idade_dias)]
        elif "from dbo.etl_agente_conversa" in s:
            self._rows = list(self.conversas)
        elif "from dbo.etl_agente_mensagem" in s:
            self._rows = list(self.mensagens)
        elif "from dbo.etl_app_config" in s:
            self._rows = [("agentes_enabled", "1"), ("agente_datastage_enabled", "1")]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass

    def sql_de(self, trecho: str):
        """O último SQL que contém `trecho` (normalizado), com os params."""
        for sql, params in reversed(self.execs):
            if trecho in " ".join(sql.lower().split()):
                return " ".join(sql.split()), params
        return None, None


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def close(self):
        pass


def _cliente(cur, *, matricula="DEV1", perms=("tela_agentes",)):
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": matricula, "perfil": "desenvolvedor",
        "permissoes": list(perms), "permissoes_extra": ["agente_datastage"]}
    return TestClient(_app)


@pytest.fixture(autouse=True)
def _limpa():
    yield
    _app.dependency_overrides.pop(get_current_user, None)
    svc._sonda_cache.clear()


# ═══════════ 1. isolamento por usuário ═══════════════════════════════════

def test_lista_filtra_pela_matricula_da_sessao():
    cur = _Cur(conversas=[("c1", "datastage", "t", "P", None, None)])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur, matricula="DEV9").get("/agentes/conversas")
    assert r.status_code == 200
    sql, params = cur.sql_de("from dbo.etl_agente_conversa")
    assert "WHERE matricula = ?" in sql
    assert params[0] == "DEV9", "a matrícula tem de vir da SESSÃO"


def test_matricula_no_corpo_ou_query_e_ignorada():
    """Não existe parâmetro de matrícula — forjar um não muda nada."""
    cur = _Cur(conversas=[])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur, matricula="DEV1").get("/agentes/conversas?matricula=OUTRO")
    assert r.status_code == 200
    _sql, params = cur.sql_de("from dbo.etl_agente_conversa")
    assert params[0] == "DEV1"
    assert "OUTRO" not in params


def test_conversa_alheia_da_404_igual_ao_de_inexistente():
    """Critério 1: sem oráculo. Os dois casos respondem o MESMO corpo."""
    cur_alheia = _Cur(dono="OUTRO")
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur_alheia)):
        alheia = _cliente(cur_alheia, matricula="DEV1").get("/agentes/conversas/abcdefgh1234")
    cur_nao_existe = _Cur(dono=None)
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur_nao_existe)):
        inexistente = _cliente(cur_nao_existe, matricula="DEV1").get("/agentes/conversas/abcdefgh1234")
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json(), "respostas diferentes viram oráculo de ids"


def test_conversa_alheia_nao_le_as_mensagens():
    """O 404 sai ANTES de buscar o conteúdo — nada da conversa alheia é lido."""
    cur = _Cur(dono="OUTRO", mensagens=[("user", "segredo alheio", None, None, None)])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur, matricula="DEV1").get("/agentes/conversas/abcdefgh1234")
    assert r.status_code == 404
    assert "segredo alheio" not in r.text
    assert not any("etl_agente_mensagem" in s.lower() for s, _ in cur.execs)


def test_historico_exige_tela_agentes():
    cur = _Cur()
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        cliente = _cliente(cur, perms=())
        assert cliente.get("/agentes/conversas").status_code == 403
        assert cliente.get("/agentes/conversas/abcdefgh1234").status_code == 403


# ═══════════ 2. os 30 dias valem na leitura ══════════════════════════════

def test_lista_filtra_por_30_dias_no_sql():
    cur = _Cur(conversas=[])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        _cliente(cur).get("/agentes/conversas")
    sql, params = cur.sql_de("from dbo.etl_agente_conversa")
    assert "ultima_msg_em >= DATEADD(day, -?, GETDATE())" in sql
    assert svc.RETENCAO_CONVERSAS_DIAS in params


@pytest.mark.parametrize("idade,esperado", [(29, 200), (30, 200), (31, 404)])
def test_retomar_respeita_os_30_dias_mesmo_sem_purga(idade, esperado):
    """Critério 2: com 31 dias não abre, ainda que a DAG de purga não tenha
    rodado e a linha continue no banco."""
    cur = _Cur(dono="DEV1", idade_dias=idade, mensagens=[])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur).get("/agentes/conversas/abcdefgh1234")
    assert r.status_code == esperado
    if esperado == 404:
        assert r.json()["detail"]["code"] == "conversa_expirada"


def test_conversar_recusa_conversa_vencida():
    """O mesmo prazo no POST: um `conversa_id` guardado no navegador não
    ressuscita uma conversa que a lista já não mostra."""
    cur = _Cur(dono="DEV1", idade_dias=45)
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur, perms=("tela_agentes", "acao_editar")).post(
            "/agentes/datastage/conversar",
            json={"mensagem": "oi", "conversa_id": "abcdefgh1234"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "conversa_expirada"


# ═══════════ 3. busca sem curinga solto ══════════════════════════════════

def test_busca_escapa_curingas_e_usa_escape_no_sql():
    cur = _Cur(conversas=[])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        _cliente(cur).get("/agentes/conversas?q=100%25_x")  # "100%_x"
    sql, params = cur.sql_de("from dbo.etl_agente_conversa")
    assert "LIKE ? ESCAPE '\\'" in sql
    termo = [p for p in params if isinstance(p, str) and p.startswith("%")][0]
    assert termo == r"%100\%\_x%"


def test_busca_vazia_nao_acrescenta_like():
    cur = _Cur(conversas=[])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        _cliente(cur).get("/agentes/conversas?q=%20%20")
    sql, _params = cur.sql_de("from dbo.etl_agente_conversa")
    assert "LIKE" not in sql


def test_agente_desconhecido_na_lista_da_404():
    cur = _Cur(conversas=[])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur).get("/agentes/conversas?agente=nao_existe")
    assert r.status_code == 404


# ═══════════ 4. só as últimas 12 rodadas vão ao gateway ══════════════════

@pytest.mark.asyncio
async def test_conversar_manda_no_maximo_12_rodadas_ao_gateway():
    msgs = []
    for i in range(30):
        msgs.append(("user", f"p{i}", None, None, None))
        msgs.append(("assistant", f"r{i}", None, None, None))
    cur = _Cur(dono="DEV1", idade_dias=1, mensagens=msgs)
    visto: dict = {}

    async def _conversar(_abrir, *, mensagens, **kw):
        visto["n"] = len(mensagens)
        visto["primeira"] = mensagens[0]
        return {"status": "ok", "texto": "ok", "projeto": "P", "artefatos": []}

    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)), \
         patch.object(svc, "conversar", new=_conversar):
        r = _cliente(cur, perms=("tela_agentes",)).post(
            "/agentes/datastage/conversar",
            json={"mensagem": "nova", "conversa_id": "abcdefgh1234"})
    assert r.status_code == 200
    # 12 rodadas = 24 do histórico + a pergunta desta vez
    assert visto["n"] == 25, visto
    assert visto["primeira"]["role"] == "user"


# ═══════════ 5. título gravado no tamanho que a coluna aceita ════════════

@pytest.mark.asyncio
async def test_titulo_da_conversa_nova_e_cortado_em_utf16():
    cur = _Cur(dono=None, mensagens=[])

    async def _conversar(_abrir, **kw):
        return {"status": "ok", "texto": "ok", "projeto": None, "artefatos": []}

    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)), \
         patch.object(svc, "conversar", new=_conversar):
        r = _cliente(cur).post("/agentes/datastage/conversar", json={"mensagem": "🙂" * 300})
    assert r.status_code == 200
    sql, params = cur.sql_de("insert into dbo.etl_agente_conversa")
    titulo = params[3]
    unidades = len(titulo.encode("utf-16-le", errors="surrogatepass")) // 2
    assert unidades <= svc.TITULO_MAX, f"{unidades} unidades estouram o NVARCHAR(200)"


# ═══════════ 6. critério 5: canário não chega ao banco ═══════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("canario,segredo", [
    ("a senha: hunter2xyz do job", "hunter2xyz"),
    ("DB_PASSWORD=Tr0ub4dor3 no parametro", "Tr0ub4dor3"),
    ("token: eyJSEGREDOCANARIO", "eyJSEGREDOCANARIO"),
])
async def test_segredo_digitado_no_chat_nao_e_gravado(canario, segredo):
    """Critério 5 da F4. A F4 acrescentou o HISTÓRICO — ou seja, o que for
    gravado agora fica visível por 30 dias e volta ao gateway a cada
    retomada. A redação acontece ANTES do INSERT e antes de a mensagem
    entrar no histórico que vai ao modelo (`af.redigir` no router), então
    nem o banco nem o gateway veem o canário."""
    cur = _Cur(dono=None, mensagens=[])
    visto: dict = {}

    async def _conversar(_abrir, *, mensagens, **kw):
        visto["ao_gateway"] = " ".join(m["content"] for m in mensagens)
        return {"status": "ok", "texto": "ok", "projeto": None, "artefatos": []}

    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)), \
         patch.object(svc, "conversar", new=_conversar):
        r = _cliente(cur).post("/agentes/datastage/conversar", json={"mensagem": canario})
    assert r.status_code == 200

    # 1. não foi para o banco (nem na mensagem, nem no título da conversa)
    gravado = " ".join(str(p) for _sql, params in cur.execs for p in params)
    assert segredo not in gravado, f"canário gravado: {gravado[:200]}"
    # 2. não foi para o gateway
    assert segredo not in visto["ao_gateway"]
    # 3. não voltou na resposta
    assert segredo not in r.text


@pytest.mark.asyncio
async def test_o_que_volta_do_historico_ja_esta_redigido():
    """Defesa em profundidade: o histórico devolvido pelo `GET /conversas/
    {id}` é o que foi GRAVADO — e o que foi gravado já passou por
    `redigir`. O teste prende que o endpoint não re-expõe nada: ele lê a
    coluna direto, sem des-redigir nada."""
    cur = _Cur(dono="DEV1", idade_dias=2,
               mensagens=[("user", "senha: ••••", None, None, None),
                          ("assistant", "o job usa um parâmetro Encrypted", None, "[]", None)])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur).get("/agentes/conversas/abcdefgh1234")
    assert r.status_code == 200
    msgs = r.json()["mensagens"]
    assert msgs[0]["conteudo"] == "senha: ••••"
    assert msgs[1]["artefatos"] == []


def test_artefatos_json_invalido_nao_derruba_o_historico():
    """Conteúdo de uma versão anterior do formato (ou truncado) vira lista
    vazia — a conversa continua legível, só sem a trilha de ferramentas."""
    cur = _Cur(dono="DEV1", idade_dias=1,
               mensagens=[("assistant", "resposta", "ok", "{nao é json", None)])
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        r = _cliente(cur).get("/agentes/conversas/abcdefgh1234")
    assert r.status_code == 200
    assert r.json()["mensagens"][0]["artefatos"] == []
