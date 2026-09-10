"""Maestro — as rotas (F1 da spec docs/spec-maestro-parametros.md).

O que se prende, de ponta a ponta com TestClient (banco e provedor por dublê):

  1. **Gate.** Sem `tela_jobs` → 403. Interruptor desligado (ou provedor sem
     chave) → status enabled=false e conversar 503, sem tocar o provedor nem
     gravar. Sem a migration 110 → status degrada (enabled=false) e conversar
     503 com a dica da 110.
  2. **O contrato da rodada.** A resposta traz o texto sem o bloco JSON, o
     status decidido pela régua, a proposta validada (Encrypted vazio), a
     prévia com a referência pedida, os avisos e — em nao_atendido — a
     orientação de procurar o administrador. E cada rodada vira uma linha em
     etl_maestro_conversa, sem valor Encrypted.
  3. **O que o provedor recebe.** O system prompt leva o catálogo, os nomes
     declarados no ISX e as linhas do editor SEM o valor Encrypted; as
     mensagens vão cortadas ao histórico máximo.
  4. **Erros do provedor.** 429 passa como 429; 500 (config) vira 503 genérico;
     ambos registram a rodada como 'erro'.
  5. **422 estruturado** para corpo inválido.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import caixa_ia, maestro  # noqa: E402

RECEITA = ('{"params":[{"param_name":"<DATA_INICIAL>","param_type":"Date","param_source":"data_referencia",'
           '"param_offset_meses":-1,"param_ancora":"inicio_mes","param_offset_dias":0,"param_formato":"%Y-%m-%d"},'
           '{"param_name":"<DATA_FINAL>","param_type":"Date","param_source":"data_referencia",'
           '"param_offset_meses":-1,"param_ancora":"fim_mes","param_offset_dias":0,"param_formato":"%Y-%m-%d"}],'
           '"exemplos":["carga mensal do mês anterior"]}')

RESPOSTA_MENSAL = """Entendi: carga mensal do mês anterior.

**pDataIni** — Tipo: Date · Origem: data_referencia · Meses: -1 · Âncora: início do mês
**pDataFim** — Tipo: Date · Origem: data_referencia · Meses: -1 · Âncora: fim do mês

```json
{"status": "atendido", "cenario": "mensal_anterior", "motivo": null, "params": [
 {"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia", "param_value": null,
  "param_offset_meses": -1, "param_ancora": "inicio_mes", "param_offset_dias": 0, "param_formato": "%Y-%m-%d"},
 {"param_name": "pDataFim", "param_type": "Date", "param_source": "data_referencia", "param_value": null,
  "param_offset_meses": -1, "param_ancora": "fim_mes", "param_offset_dias": 0, "param_formato": "%Y-%m-%d"}]}
```"""

RESPOSTA_NAO = """Último dia útil exige calendário de feriados, que o cálculo de data não tem.
Procure o administrador do Orquestra — o pedido fica registrado.

```json
{"status": "nao_atendido", "cenario": null, "motivo": "dia útil exige calendário de feriados", "params": []}
```"""


class _Cur:
    """Responde por trecho do SQL e guarda o que foi executado."""

    def __init__(self, *, enabled="1", sem_110=False, catalogo=None, historico=None):
        self.enabled, self.sem_110 = enabled, sem_110
        self.catalogo = catalogo if catalogo is not None else [
            ("mensal_anterior", "Carga mensal do mês anterior", "Primeiro e último dia do mês anterior.", RECEITA)]
        self.historico = historico or []
        self.execs: list[tuple[str, tuple]] = []
        self.inseridos: list[tuple] = []
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = sql.lower()
        if "etl_app_config" in s:
            self._rows = [(self.enabled,)] if params == (maestro.K_ENABLED,) else []
        elif "etl_maestro_cenario" in s:
            if self.sem_110:
                raise Exception("Invalid object name 'dbo.etl_maestro_cenario'")
            self._rows = list(self.catalogo)
        elif "insert into dbo.etl_maestro_conversa" in s:
            if self.sem_110:
                raise Exception("Invalid object name 'dbo.etl_maestro_conversa'")
            self.inseridos.append(params)
            self._rows = []
        elif "from dbo.etl_maestro_conversa" in s:
            if self.sem_110:
                raise Exception("Invalid object name 'dbo.etl_maestro_conversa'")
            self._rows = list(self.historico)
        elif "information_schema.tables" in s:
            self._rows = [(0,)]           # sem a 108: sem defaults
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


class _Provedor:
    """Dublê de caixa_ia.chat_conversa: guarda o que recebeu e devolve o texto."""

    def __init__(self, texto=RESPOSTA_MENSAL, erro=None):
        self.texto, self.erro, self.chamadas = texto, erro, []

    async def __call__(self, cfg, system, mensagens):
        self.chamadas.append({"cfg": cfg, "system": system, "mensagens": mensagens})
        if self.erro:
            raise self.erro
        return self.texto, "modelo-x"


@pytest.fixture
def ambiente(monkeypatch):
    """(cliente, cur, conn, provedor) com tudo ligado; os testes ajustam."""
    from fastapi.testclient import TestClient
    from api.main import app
    from deps import get_current_user
    from services import lineage_isx

    estado = {"perms": ["tela_jobs"]}
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "desenvolvedor", "permissoes": estado["perms"]}
    cur = _Cur()
    conn = _Conn(cur)
    provedor = _Provedor()
    monkeypatch.setattr(caixa_ia, "load_config", lambda c=None: {
        "enabled": False, "provider": "anthropic", "model": "claude-x", "base_url": "",
        "api_key_enc": "cifrado", "usa_proxy": False, "ultima_verificacao": ""})
    monkeypatch.setattr(caixa_ia, "chat_conversa", provedor)
    monkeypatch.setattr(lineage_isx, "cabecalho", lambda c, p, j: {
        "parameters_json": json.dumps([{"name": "pDataIni", "type": "Date"}, {"name": "pDataFim", "type": "Date"},
                                       {"name": "pSenha", "type": "Encrypted"}]),
        "status": "ok", "extracted_at": "2026-09-10 10:00:00"} if (p, j) == ("PIPE_VIDA", "JobRaiz") else None)
    with patch("routers.maestro.get_db_conn", return_value=conn):
        yield TestClient(app), cur, conn, provedor, estado
    app.dependency_overrides.pop(get_current_user, None)


def _corpo(**extra):
    corpo = {"conversa_id": "conv-0001", "mensagens": [{"role": "user", "content": "carga mensal do mês anterior"}],
             "contexto": {"pipeline_name": "PIPE_VIDA", "job_name": "JobRaiz", "referencia": "2026-03-15",
                          "params": [{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo",
                                      "param_value": "segredo!"}]}}
    corpo.update(extra)
    return corpo


# ═══════════ 1. gate ═════════════════════════════════════════════════════════

def test_sem_tela_jobs_e_403(ambiente):
    cliente, _cur, _conn, provedor, estado = ambiente
    estado["perms"] = []
    assert cliente.get("/maestro/status").status_code == 403
    assert cliente.post("/maestro/conversar", json=_corpo()).status_code == 403
    assert cliente.get("/maestro/historico").status_code == 403
    assert provedor.chamadas == []


def test_status_ligado_traz_sugestoes(ambiente):
    cliente, *_ = ambiente
    r = cliente.get("/maestro/status")
    assert r.status_code == 200 and r.json() == {"enabled": True, "sugestoes": ["carga mensal do mês anterior"]}


def test_status_desligado_ou_sem_chave_ou_sem_110(ambiente, monkeypatch):
    cliente, cur, _conn, _prov, _estado = ambiente
    cur.enabled = "0"
    assert cliente.get("/maestro/status").json() == {"enabled": False, "sugestoes": []}
    cur.enabled = "1"
    monkeypatch.setattr(caixa_ia, "load_config", lambda c=None: {"api_key_enc": "", "provider": "anthropic"})
    assert cliente.get("/maestro/status").json() == {"enabled": False, "sugestoes": []}


def test_status_degrada_sem_a_110(ambiente):
    cliente, cur, *_ = ambiente
    cur.sem_110 = True
    assert cliente.get("/maestro/status").json() == {"enabled": False, "sugestoes": []}


def test_conversar_desligado_e_503_sem_provedor_nem_registro(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    cur.enabled = "0"
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 503 and "desligado" in r.json()["detail"]
    assert provedor.chamadas == [] and cur.inseridos == []


def test_conversar_ligado_sem_chave_diz_qual_admin_falta(ambiente, monkeypatch):
    """Interruptor ligado × provedor sem chave são donos diferentes."""
    cliente, cur, _conn, provedor, _estado = ambiente
    monkeypatch.setattr(caixa_ia, "load_config", lambda c=None: {"api_key_enc": "", "provider": "anthropic"})
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 503 and "Caixa Seguro IA" in r.json()["detail"]
    assert "desligado" not in r.json()["detail"]
    assert provedor.chamadas == [] and cur.inseridos == []


def test_conversar_sem_a_110_e_503_com_a_dica(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    cur.sem_110 = True
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 503 and "migration 110" in r.json()["detail"]
    assert provedor.chamadas == []


# ═══════════ 2. o contrato da rodada ═════════════════════════════════════════

def test_conversar_caso_mensal(ambiente):
    cliente, cur, conn, provedor, _estado = ambiente
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["conversa_id"] == "conv-0001" and d["status"] == "atendido" and d["cenario"] == "mensal_anterior"
    assert d["motivo"] is None and d["orientacao"] is None and d["referencia"] == "2026-03-15"
    assert "```" not in d["resposta"] and d["resposta"].startswith("Entendi")
    assert [p["param_name"] for p in d["proposta"]["params"]] == ["pDataIni", "pDataFim"]
    assert d["proposta"]["params"][0]["param_ancora"] == "inicio_mes"
    assert [p["valor"] for p in d["previa"]] == ["2026-02-01", "2026-02-28"]
    assert d["avisos"] == []
    # Registro: uma linha, commitada, com a proposta e sem segredo.
    assert len(cur.inseridos) == 1 and conn.commits == 1
    linha = cur.inseridos[0]
    assert linha[0] == "conv-0001" and linha[1] == "U1" and linha[2:4] == ("PIPE_VIDA", "JobRaiz")
    assert linha[4] == "carga mensal do mês anterior" and linha[6] == "atendido" and linha[7] == "mensal_anterior"
    assert '"pDataFim"' in linha[8] and linha[10] == "modelo-x" and isinstance(linha[11], int)
    assert "segredo" not in json.dumps(linha, default=str)


def test_conversar_nao_atendido_traz_orientacao_e_registra_o_pedido(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    provedor.texto = RESPOSTA_NAO
    r = cliente.post("/maestro/conversar", json=_corpo(
        mensagens=[{"role": "user", "content": "último dia útil do mês anterior"}]))
    d = r.json()
    assert r.status_code == 200 and d["status"] == "nao_atendido"
    assert d["proposta"] is None and d["previa"] is None
    assert d["motivo"] == "dia útil exige calendário de feriados"
    assert d["orientacao"] == maestro.ORIENTACAO_ADMIN
    assert cur.inseridos[0][6] == "nao_atendido" and cur.inseridos[0][9] == "dia útil exige calendário de feriados"


def test_conversar_regua_derruba_proposta_invalida(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    provedor.texto = RESPOSTA_MENSAL.replace('"param_ancora": "fim_mes"', '"param_ancora": "ultimo_dia_util"')
    d = cliente.post("/maestro/conversar", json=_corpo()).json()
    assert d["status"] == "nao_atendido" and "ultimo_dia_util" in d["motivo"]
    assert d["orientacao"] == maestro.ORIENTACAO_ADMIN and d["proposta"] is None


def test_conversar_encrypted_sai_vazio_e_avisa_tipo_divergente(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    provedor.texto = """Proponho a senha sem valor.
```json
{"status": "atendido", "cenario": null, "params": [
 {"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo", "param_value": "NUNCA"},
 {"param_name": "pDataIni", "param_type": "String", "param_source": "data_referencia"}]}
```"""
    d = cliente.post("/maestro/conversar", json=_corpo()).json()
    assert d["status"] == "atendido"
    assert d["proposta"]["params"][0] == {
        "param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo", "param_value": "",
        "param_offset_meses": None, "param_ancora": None, "param_offset_dias": None, "param_formato": None,
        "tem_valor": False}
    assert d["previa"][0]["valor"] == "***"
    assert any("declara 'pDataIni' como Date; a proposta usa String" in a for a in d["avisos"])
    assert "NUNCA" not in json.dumps(d) and "NUNCA" not in json.dumps(cur.inseridos, default=str)


def test_conversar_sem_bloco_json_e_pergunta(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    provedor.texto = "Quais são os nomes dos parâmetros no Designer?"
    d = cliente.post("/maestro/conversar", json=_corpo()).json()
    assert d["status"] == "pergunta" and d["proposta"] is None and d["orientacao"] is None
    assert cur.inseridos[0][6] == "pergunta"


def test_conversar_gera_conversa_id_quando_nao_vem(ambiente):
    cliente, *_ = ambiente
    corpo = _corpo()
    corpo.pop("conversa_id")
    d = cliente.post("/maestro/conversar", json=corpo).json()
    assert len(d["conversa_id"]) == 36


# ═══════════ 3. o que o provedor recebe ══════════════════════════════════════

def test_provedor_recebe_catalogo_isx_editor_sem_segredo_e_historico_cortado(ambiente):
    cliente, _cur, _conn, provedor, _estado = ambiente
    mensagens = []
    for i in range(20):
        mensagens.append({"role": "user", "content": f"u{i}"})
        mensagens.append({"role": "assistant", "content": f"a{i}"})
    mensagens.append({"role": "user", "content": "final"})
    cliente.post("/maestro/conversar", json=_corpo(mensagens=mensagens))
    chamada = provedor.chamadas[0]
    assert chamada["cfg"]["api_key_enc"] == "cifrado"
    system = chamada["system"]
    assert "[mensal_anterior]" in system and "pDataIni (date)" in system and "pSenha (encrypted)" in system
    assert '"param_name":"pSenha"' in system and "segredo" not in system
    assert "2026-03-15" in system and "PIPE_VIDA" in system and "JobRaiz" in system
    assert len(chamada["mensagens"]) == maestro.MAX_HISTORICO
    assert chamada["mensagens"][-1] == {"role": "user", "content": "final"}


def test_resposta_longa_anterior_do_maestro_nao_mata_a_conversa(ambiente):
    """O teto de 4.000 é para o que o USUÁRIO digita; a resposta anterior do
    Maestro (até ~12k chars com MAX_TOKENS 4096) é truncada, não recusada —
    senão toda rodada depois de uma resposta longa daria 422."""
    cliente, _cur, _conn, provedor, _estado = ambiente
    longa = "x" * (maestro.MAX_MENSAGEM_HISTORICO + 500)
    r = cliente.post("/maestro/conversar", json=_corpo(mensagens=[
        {"role": "user", "content": "mensal"}, {"role": "assistant", "content": longa},
        {"role": "user", "content": "pDataIni e pDataFim"}]))
    assert r.status_code == 200, r.text
    enviadas = provedor.chamadas[0]["mensagens"]
    assert len(enviadas[1]["content"]) == maestro.MAX_MENSAGEM_HISTORICO
    assert enviadas[-1]["content"] == "pDataIni e pDataFim"


def test_provedor_sem_isx_o_prompt_pede_os_nomes(ambiente):
    cliente, _cur, _conn, provedor, _estado = ambiente
    d = cliente.post("/maestro/conversar", json=_corpo(
        contexto={"pipeline_name": "PIPE_VIDA", "job_name": "Outro"})).json()
    assert "Sem lineage ISX extraído" in provedor.chamadas[0]["system"]
    assert any("sem lineage ISX" in a for a in d["avisos"])


# ═══════════ 4. erros do provedor ════════════════════════════════════════════

def test_provedor_429_passa_e_registra_erro(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    provedor.erro = HTTPException(status_code=429, detail="Limite de requisições excedido no provedor de IA")
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 429
    assert cur.inseridos[0][6] == "erro" and "Limite" in cur.inseridos[0][9] and cur.inseridos[0][5] is None


def test_provedor_500_vira_503_generico(ambiente):
    cliente, cur, _conn, provedor, _estado = ambiente
    provedor.erro = HTTPException(status_code=500, detail="Biblioteca 'anthropic' não instalada")
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 503 and "anthropic" not in r.json()["detail"]
    assert "contate o administrador" in r.json()["detail"]
    assert cur.inseridos[0][6] == "erro"


def test_falha_no_registro_nao_derruba_a_resposta(ambiente):
    cliente, cur, _conn, _prov, _estado = ambiente
    original = cur.execute

    def _execute(sql, params=None):
        if "insert into dbo.etl_maestro_conversa" in sql.lower():
            raise Exception("deadlock")
        return original(sql, params)
    cur.execute = _execute
    r = cliente.post("/maestro/conversar", json=_corpo())
    assert r.status_code == 200 and r.json()["status"] == "atendido"


# ═══════════ 5. corpo inválido ═══════════════════════════════════════════════

@pytest.mark.parametrize("corpo, trecho", [
    ({}, "mensagens é obrigatório"),
    (_corpo(mensagens=[{"role": "assistant", "content": "x"}]), "última mensagem deve ser do usuário"),
    (_corpo(mensagens=[{"role": "user", "content": "x" * 4001}]), "excede 4000"),
    (_corpo(conversa_id="a b"), "conversa_id inválido"),
    (_corpo(contexto={"referencia": "15/03/2026"}), "referencia inválida"),
    (_corpo(contexto={"params": "x"}), "contexto.params"),
    (_corpo(contexto=[1]), "contexto deve ser um objeto"),
])
def test_corpo_invalido_e_422_estruturado(ambiente, corpo, trecho):
    cliente, _cur, _conn, provedor, _estado = ambiente
    r = cliente.post("/maestro/conversar", json=corpo)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "maestro_corpo_invalido" and any(trecho in e for e in detail["errors"])
    assert provedor.chamadas == []


# ═══════════ 6. histórico ════════════════════════════════════════════════════

def test_historico(ambiente):
    cliente, cur, *_ = ambiente
    cur.historico = [("c1", "PIPE_VIDA", "JobRaiz", "m1", "r1", "pergunta", "2026-09-10 10:00:00"),
                     ("c1", "PIPE_VIDA", "JobRaiz", "m2", "r2", "atendido", "2026-09-10 10:01:00")]
    d = cliente.get("/maestro/historico").json()
    assert d["conversas"][0]["conversa_id"] == "c1"
    assert [r["mensagem"] for r in d["conversas"][0]["rodadas"]] == ["m1", "m2"]
    cur.sem_110 = True
    assert cliente.get("/maestro/historico").status_code == 503
