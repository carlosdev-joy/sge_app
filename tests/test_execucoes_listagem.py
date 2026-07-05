"""Teste do mapeamento POSICIONAL do GET /execucoes (modo agregado).

O dict é montado por índice r[0..21]; qualquer coluna nova no agg CTE desloca
tudo — foi exatamente o risco introduzido por duracao_wall_segundos e
jobs_skipped (onda 2). Este teste trava o shape completo (agg + ack + resolved).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch


_DT_INI = datetime(2026, 7, 4, 6, 0, 0)
_DT_FIM = datetime(2026, 7, 4, 6, 5, 0)
_DT_ACK = datetime(2026, 7, 4, 7, 0, 0)
_DT_RES = datetime(2026, 7, 4, 8, 0, 0)

# Linha com o shape COMPLETO do SELECT agregado (agg 0..13 + ack 14..16 + resolved 17..21)
_ROW22 = (
    "20260704T060000", "BI_CVP", "PIPE_X",          # 0..2
    _DT_INI, _DT_FIM,                                 # 3..4 inicio/fim
    900,                                              # 5  duracao_total (SOMA)
    300,                                              # 6  duracao_wall
    3, 2, 0, 0, 0, 1,                                 # 7..12 total/ok/falha/warn/run/skip
    "SUCCESS",                                        # 13 status_geral
    "carlos", "Carlos H", _DT_ACK,                    # 14..16 ack
    "maria", "Maria S", _DT_RES, "nota", "INC123",   # 17..21 resolved
)


def test_execucoes_agregado_mapeia_colunas_na_posicao_certa(client):
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchone.return_value = (1,)                      # COUNT
    cur.fetchall.side_effect = [[_ROW22], []]             # agg, fila (etl_ds_job_log)

    with patch("routers.execucoes.get_db_conn", return_value=conn):
        r = client.get("/execucoes?limit=10")
    assert r.status_code == 200, r.text
    d = r.json()["data"][0]

    assert d["execution_id"] == "20260704T060000"
    assert d["project"] == "BI_CVP"
    assert d["pipeline"] == "PIPE_X"
    # o par soma × wall — o deslocamento clássico trocaria estes dois
    assert d["duracao_total_segundos"] == 900
    assert d["duracao_wall_segundos"] == 300
    assert d["total_jobs"] == 3
    assert d["jobs_ok"] == 2
    assert d["jobs_falha"] == 0
    assert d["jobs_warning"] == 0
    assert d["jobs_running"] == 0
    assert d["jobs_skipped"] == 1
    assert d["status_geral"] == "SUCCESS"
    # bloco ack/resolved — o deslocamento faria ack_by == 'SUCCESS'
    assert d["ack_by"] == "carlos"
    assert d["display_name"] == "Carlos H"
    assert d["resolved_by"] == "maria"
    assert d["resolution_note"] == "nota"
    assert d["snow_ticket"] == "INC123"
    assert d["fila_total_segundos"] == 0
