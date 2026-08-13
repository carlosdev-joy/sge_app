"""A cadência do sync × o que depende dela — o teste que recusa o incoerente.

O `schedule` de `dags/etl_servicenow_sync.py` não é um número solto. Três
outros valores só fazem sentido em função dele, e nenhum mora no mesmo arquivo:

  1. **`FRESCOR_ALERTA_MINUTOS`** (`api/routers/chamados.py`) — quanto silêncio
     acende o âmbar na tela. Cadência de 15 min com limiar de 6h (o valor da
     época dos 3h) deixaria 24 ciclos morrerem antes de a tela reclamar: o
     alerta existiria e não alertaria. O contrário — cadência de 3h com limiar
     de 1h — pinta de âmbar a operação NORMAL, e alerta que acende sempre é
     alerta que ninguém lê.
  2. **`dagrun_timeout`** — com `max_active_runs=1`, uma run que atravessa o
     slot seguinte empurra a fila indefinidamente. O teto tem que caber no
     intervalo.
  3. **`retry_delay`** — a tentativa 2 precisa acontecer dentro da janela;
     retentar depois do próximo ciclo é trabalho jogado fora.

Nada aqui afirma que 15 min é o número certo — isso é decisão de operação.
O que os testes prendem é a **coerência entre os quatro**, para que mexer na
cadência e esquecer o resto quebre a suíte em vez de degradar em silêncio.

Leitura por regex sobre o fonte: importar a DAG exigiria Airflow instalado
(e o parse dela abre hook de banco). Os valores são literais estáticos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

RAIZ = Path(__file__).resolve().parents[1]
DAG_PY = RAIZ / "dags" / "etl_servicenow_sync.py"

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()

from routers.chamados import FRESCOR_ALERTA_MINUTOS  # noqa: E402


def _fonte_da_dag() -> str:
    return DAG_PY.read_text(encoding="utf-8")


def _cadencia_minutos() -> int:
    """Minutos entre ciclos, lidos do `schedule` da DAG.

    Cobre as duas formas que este projeto usa — `*/N * * * *` (a cada N min) e
    `0 */H * * *` (a cada H horas). Cron mais exótico que isso falha o teste de
    propósito: se a cadência virar algo que esta função não sabe ler, a regra
    de coerência abaixo não estaria mais sendo verificada, e um teste que não
    verifica nada é pior que teste nenhum.
    """
    m = re.search(r'schedule="([^"]+)"', _fonte_da_dag())
    assert m, "schedule não encontrado em dags/etl_servicenow_sync.py"
    cron = m.group(1)

    if (por_min := re.fullmatch(r"\*/(\d+) \* \* \* \*", cron)):
        return int(por_min.group(1))
    if (por_hora := re.fullmatch(r"0 \*/(\d+) \* \* \*", cron)):
        return int(por_hora.group(1)) * 60
    raise AssertionError(
        f"schedule '{cron}' não é uma das formas que este teste sabe ler "
        f"(*/N * * * * ou 0 */H * * *) — ensine a função ou reveja a cadência, "
        f"mas não deixe a coerência com FRESCOR_ALERTA_MINUTOS sem verificação")


def _minutos_do_timedelta(trecho: str) -> int:
    m = re.search(r"_dt\.timedelta\(minutes=(\d+)\)", trecho)
    assert m, f"timedelta(minutes=…) não encontrado em: {trecho[:80]}"
    return int(m.group(1))


# ═══════════ 1. o alerta de frescor × a cadência ════════════════════════════

def test_frescor_alerta_entre_dois_e_oito_ciclos():
    """Menos de 2 ciclos = âmbar no primeiro tropeço. Mais de 8 = o espelho
    apodrece antes de a tela reclamar."""
    ciclo = _cadencia_minutos()
    ciclos_ate_o_alerta = FRESCOR_ALERTA_MINUTOS / ciclo
    assert 2 <= ciclos_ate_o_alerta <= 8, (
        f"FRESCOR_ALERTA_MINUTOS={FRESCOR_ALERTA_MINUTOS} são "
        f"{ciclos_ate_o_alerta:.1f} ciclos de {ciclo} min — fora da faixa 2–8. "
        f"A cadência mudou e o limiar de api/routers/chamados.py ficou para trás "
        f"(ou vice-versa).")


def test_frescor_nunca_alerta_dentro_de_um_ciclo():
    """Limiar abaixo de um ciclo pintaria de âmbar a operação normal: entre um
    sync e o seguinte o espelho SEMPRE tem essa idade."""
    assert FRESCOR_ALERTA_MINUTOS > _cadencia_minutos()


# ═══════════ 2. teto e retry cabem no intervalo ═════════════════════════════

def test_dagrun_timeout_cabe_no_intervalo():
    """max_active_runs=1 + run que atravessa o slot = fila empurrada para
    sempre, cada ciclo começando mais tarde que o anterior."""
    fonte = _fonte_da_dag()
    timeout = _minutos_do_timedelta(
        re.search(r"dagrun_timeout=([^,]+),", fonte).group(1))
    assert timeout <= _cadencia_minutos(), (
        f"dagrun_timeout={timeout} min excede o intervalo de "
        f"{_cadencia_minutos()} min entre ciclos")


def test_retry_acontece_antes_do_proximo_ciclo():
    """Retentar depois de o próximo ciclo já ter começado é trabalho perdido —
    o ciclo novo faria a mesma coisa, com dados mais frescos."""
    fonte = _fonte_da_dag()
    delay = _minutos_do_timedelta(
        re.search(r'"retry_delay":\s*([^}]+)}', fonte).group(1))
    assert delay < _cadencia_minutos(), (
        f"retry_delay={delay} min não cabe no intervalo de "
        f"{_cadencia_minutos()} min")


# ═══════════ 3. o que a tela e o catálogo PROMETEM ao operador ══════════════

def test_catalogo_de_dags_anuncia_a_cadencia_real():
    """O inventário de DAGs do Admin é lido como documentação viva. Anunciar
    'a cada 3h' rodando de 15 em 15 min é o próprio Admin mentindo."""
    from routers.admin import CATALOGO_DAGS
    freq = CATALOGO_DAGS["etl_servicenow_sync"]["frequencia"]
    ciclo = _cadencia_minutos()
    esperado = f"{ciclo} min" if ciclo < 60 else f"{ciclo // 60}h"
    assert esperado in freq, (
        f"CATALOGO_DAGS anuncia '{freq}', mas o cron roda a cada {ciclo} min")
