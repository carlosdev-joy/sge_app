"""O contador de ETAPAS do dia no Dashboard (`GET /dashboard`, kpis).

"Execuções" conta pipelines; o KPI novo conta cada ETAPA (job) que rodou no
dia — a medida de grandeza do uso da ferramenta. Estes testes são o CONTRATO
do texto (o molde da §1 do `test_dashboard_rodando_agora_f9`): sem banco, eles
prendem o recorte da consulta — mesma janela, mesmo filtro de ambiente e de
projeto do KPI de execuções — e a semântica do "com sucesso". Quem decide se o
`COUNT(*)` enxerga as linhas certas é o SQL Server; o que se prende aqui é que
o texto não possa regredir em silêncio para um recorte diferente do KPI
vizinho (dois números na mesma linha de cards contando dias diferentes é o
Dashboard mentindo com aritmética certa).
"""
from __future__ import annotations

import inspect
import re

from routers.dashboard import get_dashboard

FONTE = inspect.getsource(get_dashboard)


def _bloco_etapas() -> str:
    """O trecho da consulta de etapas — do comentário-âncora até o fetch."""
    m = re.search(r"Etapas do dia(.*?)total_etapas_ok\s*=", FONTE, re.S)
    assert m, "o bloco 'Etapas do dia' sumiu de get_dashboard"
    return m.group(1)


def test_conta_linhas_de_job_e_nao_execucoes():
    """`COUNT(*)` direto sobre `etl_job_execution`, SEM `GROUP BY` por
    execução: agrupar viraria o KPI de execuções de novo, com outro nome."""
    bloco = _bloco_etapas()
    assert "COUNT(*)" in bloco
    assert "etl_job_execution" in bloco
    assert "GROUP BY" not in bloco


def test_mesmo_recorte_do_kpi_de_execucoes():
    """Janela por `start_time`, só ambiente PROD e o MESMO filtro opcional de
    projeto (`where_proj_alias`) — o recorte do KPI vizinho, linha a linha."""
    bloco = _bloco_etapas()
    assert "e.start_time >= ? AND e.start_time < ?" in bloco
    assert "COALESCE(p.ambiente, 'PROD') = 'PROD'" in bloco
    assert "{where_proj_alias}" in bloco
    # E o parâmetro do filtro entra condicionado, como em todo o arquivo.
    assert "[dt_ini, dt_fim] + ([fp] if fp else [])" in bloco


def test_com_sucesso_conta_so_SUCCESS():
    """RUNNING conta no total (a etapa rodou no dia) e NUNCA no "com sucesso".
    O contrato prende o único CASE do bloco a `status = 'SUCCESS'`: um
    `IN ('SUCCESS','WARNING')` aqui inflaria o subtítulo do card."""
    bloco = _bloco_etapas()
    cases = re.findall(r"CASE WHEN (.*?) THEN", bloco)
    assert cases == ["e.status = 'SUCCESS'"], cases


def test_os_dois_numeros_chegam_ao_kpi():
    """`total_etapas` e `total_etapas_ok` saem no dict `kpis` da resposta —
    é o nome que o front consome; sumir daqui é card eternamente em "—"."""
    assert '"total_etapas": total_etapas' in FONTE
    assert '"total_etapas_ok": total_etapas_ok' in FONTE
