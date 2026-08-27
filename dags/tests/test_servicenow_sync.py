"""tests/test_servicenow_sync.py — unit tests for servicenow_sync helpers.

Run from /opt/airflow:
    docker exec orquestra-api python -m pytest tests/test_servicenow_sync.py -v
"""
import sys
import types
import datetime

sys.path.insert(0, "/opt/airflow/dags")
sys.path.insert(0, "/opt/airflow/dags/utils")

# Stub chamado_derivacoes so normalizar() works without DB
_der = types.ModuleType("utils.chamado_derivacoes")
_der.derivar = lambda linha: {
    "tipo_demanda": "Demanda técnica",
    "categoria_diaadia": "",
    "objetos": "",
}
sys.modules.setdefault("utils.chamado_derivacoes", _der)

_texto_sql = types.ModuleType("utils.texto_sql")
_texto_sql.cortar = lambda s, n: s[:n] if len(s) > n else s
_texto_sql.unidades_utf16 = lambda s: len(s)
sys.modules.setdefault("utils.texto_sql", _texto_sql)

_frescor = types.ModuleType("utils.frescor_modulo")
_frescor.carimbar = lambda *a, **kw: None
sys.modules.setdefault("utils.frescor_modulo", _frescor)

from utils import servicenow_sync as ss  # noqa: E402


# ── mapear_estado ─────────────────────────────────────────────────────────────

class TestMapearEstado:
    def test_incident_resolvido(self):
        assert ss.mapear_estado("incident", "6") == "resolvido"

    def test_ritm_pendente(self):
        # -5 deve ser "aguardando" (era bug: caia em 'outros')
        assert ss.mapear_estado("sc_req_item", "-5") == "aguardando"

    def test_sctask_pendente_nao_eh_novo(self):
        # -5 era 'novo' (bug), deve ser 'aguardando'
        assert ss.mapear_estado("sc_task", "-5") == "aguardando"

    def test_desconhecido_vira_outros(self):
        # estado nunca visto não pode silenciar o chamado
        assert ss.mapear_estado("incident", "99") == "outros"

    def test_tabela_desconhecida_vira_outros(self):
        assert ss.mapear_estado("tabela_fantasma", "1") == "outros"

    def test_estado_none_seguro(self):
        assert ss.mapear_estado("incident", None) == "outros"


# ── _pai ─────────────────────────────────────────────────────────────────────

class TestPai:
    """ss._pai() extracts (sys_id, numero) from a ServiceNow record."""

    def _reg(self, request_item=None, parent=None):
        reg = {}
        if request_item is not None:
            reg["request_item"] = request_item
        if parent is not None:
            reg["parent"] = parent
        return reg

    def _campo(self, value, display_value):
        return {"value": value, "display_value": display_value}

    def test_request_item_preferido_sobre_parent(self):
        reg = self._reg(
            request_item=self._campo("SYSID_RI", "RITM0001"),
            parent=self._campo("SYSID_P", "INC0001"),
        )
        pai_sys_id, _ = ss._pai(reg)
        assert pai_sys_id == "SYSID_RI"

    def test_sem_pai_retorna_vazio(self):
        assert ss._pai({}) == ("", "")

    def test_pai_somente_parent(self):
        reg = self._reg(parent=self._campo("SYSID_P", "INC0001"))
        sys_id, numero = ss._pai(reg)
        assert sys_id == "SYSID_P"
        assert numero == "INC0001"


# ── normalizar ────────────────────────────────────────────────────────────────

class TestNormalizar:
    def _base_reg(self, overrides=None):
        reg = {
            "sys_id": "FAKESYSID",
            "number": "RITM0001234",
            "short_description": "Teste",
            "state": {"value": "1", "display_value": "Em aberto"},
            "priority": {"value": "3", "display_value": "Moderado"},
            "assigned_to": {"value": "", "display_value": ""},
            "assignment_group": {"value": "", "display_value": "GESTR ED"},
            "opened_at": {"value": "2026-08-01 08:00:00", "display_value": ""},
            "sys_updated_on": {"value": "2026-08-10 10:00:00", "display_value": ""},
            "closed_at": {"value": "", "display_value": ""},
            "active": {"value": "true", "display_value": ""},
            "description": "",
            "work_notes": "",
            "cat_item": {"value": "", "display_value": ""},
            "requested_for": {"value": "", "display_value": ""},
            "estimated_delivery": {"value": "", "display_value": ""},
            "due_date": {"value": "", "display_value": ""},
            "u_sla_expired": {"value": "", "display_value": ""},
            "parent": {"value": "", "display_value": ""},
            "request_item": {"value": "", "display_value": ""},
        }
        if overrides:
            reg.update(overrides)
        return reg

    def test_normaliza_registro_basico(self):
        linha = ss.normalizar(self._base_reg(), "sc_req_item", "ritm", "https://sn")
        assert linha["sys_id"] == "FAKESYSID"
        assert linha["numero"] == "RITM0001234"
        assert linha["tipo"] == "ritm"
        assert linha["ativo"] == 1

    def test_estado_encerrado_desativa(self):
        reg = self._base_reg({"state": {"value": "7", "display_value": "Encerrado"}})
        linha = ss.normalizar(reg, "sc_req_item", "ritm", "https://sn")
        assert linha["ativo"] == 0

    def test_sla_vencido_booleano(self):
        reg = self._base_reg({"u_sla_expired": {"value": "true", "display_value": ""}})
        linha = ss.normalizar(reg, "sc_req_item", "ritm", "https://sn")
        assert linha["sla_vencido"] == 1

    def test_data_invalida_nao_derruba(self):
        reg = self._base_reg({"opened_at": {"value": "não-é-data", "display_value": ""}})
        linha = ss.normalizar(reg, "sc_req_item", "ritm", "https://sn")
        assert linha["aberto_em"] is None


# ── upsert_params ordem ───────────────────────────────────────────────────────

class TestUpsertParams:
    def test_len_params_correto(self):
        """(1 chave) + (N campos × 2 para UPDATE e INSERT) deve fechar."""
        n = len(ss.CAMPOS_UPSERT)
        linha = {c: None for c in ss.CAMPOS_UPSERT}
        linha["sys_id"] = "X"
        params = ss.upsert_params(linha)
        assert len(params) == 1 + n * 2

    def test_sys_id_primeiro(self):
        linha = {c: None for c in ss.CAMPOS_UPSERT}
        linha["sys_id"] = "MEID"
        params = ss.upsert_params(linha)
        assert params[0] == "MEID"
