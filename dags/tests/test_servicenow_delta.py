"""Testa ponto de corte do delta e montagem da query incremental."""
import sys, types, datetime as _dt
from unittest.mock import MagicMock, patch

# ── stubs obrigatórios ────────────────────────────────────────────────────────
for mod in ("utils.chamado_derivacoes", "utils.texto_sql", "utils.frescor_modulo"):
    m = types.ModuleType(mod)
    if mod == "utils.texto_sql":
        m.cortar = lambda t, n: (t or "")[:n]
        m.unidades_utf16 = lambda t: len((t or "").encode("utf-16-le")) // 2
    elif mod == "utils.chamado_derivacoes":
        m.derivar = lambda linha: {}
    elif mod == "utils.frescor_modulo":
        m.carimbar = lambda f: None
        m.conferir = lambda f: None
    sys.modules[mod] = m

from utils.servicenow_sync import ultimo_delta_em, query_delta  # noqa: E402


class TestUltimoDeltaEm:
    def _hook(self, row):
        h = MagicMock()
        h.get_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = row
        conn.cursor.return_value = cur
        h.get_conn.return_value = conn
        return h

    def test_retorna_datetime_quando_existe(self):
        ts = _dt.datetime(2026, 8, 22, 10, 0, 0)
        h = self._hook((ts,))
        resultado = ultimo_delta_em(h)
        assert resultado == ts

    def test_fallback_30min_quando_nulo(self):
        h = self._hook((None,))
        antes = _dt.datetime.utcnow() - _dt.timedelta(minutes=31)
        resultado = ultimo_delta_em(h)
        depois = _dt.datetime.utcnow() - _dt.timedelta(minutes=29)
        assert antes <= resultado <= depois


class TestQueryDelta:
    def test_inclui_filtro_sys_updated_on(self):
        desde = _dt.datetime(2026, 8, 22, 10, 0, 0)
        q = query_delta(["Eng. Dados"], desde)
        assert "sys_updated_on>=" in q
        assert "2026-08-22" in q

    def test_inclui_filtro_de_grupo(self):
        q = query_delta(["Eng. Dados", "Dados Cloud"], _dt.datetime(2026, 8, 22))
        assert "assignment_group.name=Eng. Dados" in q
        assert "assignment_group.name=Dados Cloud" in q

    def test_levanta_se_grupos_vazio(self):
        import pytest
        with pytest.raises(ValueError):
            query_delta([], _dt.datetime(2026, 8, 22))
