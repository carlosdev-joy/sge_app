"""Testa busca e MERGE de notas do sys_journal_field."""
import sys, types
from unittest.mock import MagicMock

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

from utils.servicenow_sync import buscar_notas, upsert_nota_sql  # noqa: E402


_NOTA_API = {
    "sys_id": {"value": "NOTA001", "display_value": "NOTA001"},
    "element_id": {"value": "SYS001"},
    "sys_created_by": {"value": "joao.silva", "display_value": "João Silva"},
    "sys_created_on": {"value": "2026-08-20 10:32:15"},
    "value": "Verificado o job — coluna ausente.",
    "element": {"value": "work_notes"},
}


class TestBuscarNotas:
    def _cliente(self, payload):
        cli = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"result": payload}
        resp.raise_for_status = MagicMock()
        cli.get.return_value = resp
        return cli

    def test_retorna_lista_estruturada(self):
        cli = self._cliente([_NOTA_API])
        notas = buscar_notas(cli, "https://inst.service-now.com", "SYS001")
        assert len(notas) == 1
        n = notas[0]
        assert n["sys_id_nota"] == "NOTA001"
        assert n["sys_id_chamado"] == "SYS001"
        assert n["tipo"] == "work_notes"
        assert "João Silva" in (n["autor"] or "")

    def test_lista_vazia_sem_erro(self):
        cli = self._cliente([])
        notas = buscar_notas(cli, "https://inst.service-now.com", "SYS001")
        assert notas == []

    def test_sem_update_nas_notas(self):
        """upsert_nota_sql não pode ter UPDATE SET — notas são imutáveis."""
        sql = upsert_nota_sql()
        assert "WHEN MATCHED THEN UPDATE" not in sql
        assert "WHEN NOT MATCHED" in sql

    def test_placeholder_pymssql(self):
        sql = upsert_nota_sql()
        assert "%s" in sql
        assert "?" not in sql
