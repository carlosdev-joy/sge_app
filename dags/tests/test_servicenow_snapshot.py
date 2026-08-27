"""Testa captura de snapshot de indicadores."""
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

from utils.servicenow_sync import capturar_snapshot  # noqa: E402


def _hook_com_dados():
    h = MagicMock()
    conn = MagicMock()
    cur = MagicMock()

    # Sequência de retornos do fetchone:
    # 1. SELECT contagens gerais
    # 2. SELECT idade_media
    # 3. SELECT tempo_medio_resolucao
    # 4. SELECT qtd_encerrados_7d
    # 5. SELECT qtd_abertos_7d
    # 6. SELECT qtd_iniciativas_abertas
    # 7. INSERT snapshot → id=99
    fetchone_seq = [
        (42, 5, 18, 12, 7, 0, 3),   # total, novo, andamento, aguardando, resolvido, outros, sla_vencidos
        (4.2,),          # idade_media_dias
        (18.5,),         # tempo_medio_resolucao_horas
        (22,),           # qtd_encerrados_7d
        (19,),           # qtd_abertos_7d
        (8,),            # qtd_iniciativas_abertas
        (99,),           # id do snapshot inserido
    ]
    cur.fetchone.side_effect = fetchone_seq
    # analistas e grupos: fetchall retorna listas vazias para simplificar
    cur.fetchall.return_value = []
    conn.cursor.return_value = cur
    h.get_conn.return_value = conn
    return h


class TestCapturarSnapshot:
    def test_retorna_id_do_snapshot(self):
        h = _hook_com_dados()
        snap_id = capturar_snapshot(h)
        assert snap_id == 99

    def test_chama_commit(self):
        h = _hook_com_dados()
        capturar_snapshot(h)
        h.get_conn.return_value.commit.assert_called()

    def test_insere_snapshot_principal(self):
        h = _hook_com_dados()
        capturar_snapshot(h)
        all_calls = " ".join(str(c) for c in
                             h.get_conn.return_value.cursor.return_value.execute.call_args_list)
        assert "etl_indicador_snapshot" in all_calls
