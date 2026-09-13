"""Login ORQ: cliente público isolado e número público sem histórico interno."""
from pathlib import Path
import shutil
import subprocess
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def test_cliente_login_e_interceptador_global():
    node = shutil.which('node')
    if not node or not (RAIZ / 'ui-react/node_modules/sucrase').is_dir():
        pytest.skip('Node/Sucrase indisponível')
    r = subprocess.run([node, str(RAIZ / 'tests/js/login_api_harness.cjs')],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize('linhas,esperado', [
    ([('1.9',), ('1.10',), ('1.2',)], '1.10'),
    ([('2.0.1',), ('2.0',), ('1.99',)], '2.0.1'),
    ([('titulo interno',), ('<script>',), (None,), ('1.0\nsegredo',)], None),
    ([], None),
])
def test_versao_publica_so_numero_sem_historico(monkeypatch, linhas, esperado):
    from routers import infra
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchall.return_value = linhas
    monkeypatch.setattr(infra, 'get_db_conn', lambda: conn)
    assert infra.get_versao_publica() == {'versao': esperado}
    assert cur.execute.call_args.args == ('SELECT DISTINCT versao FROM dbo.etl_versao_ferramenta',)
    cur.close.assert_called_once()
    conn.close.assert_called_once()


def test_versao_publica_falha_sem_vazar_infra(monkeypatch):
    from routers import infra
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError('credencial interna de teste')
    monkeypatch.setattr(infra, 'get_db_conn', lambda: conn)
    assert infra.get_versao_publica() == {'versao': None}
    conn.close.assert_called_once()


def test_versao_publica_nao_exige_autenticacao():
    from routers.infra import router
    route = next(r for r in router.routes if r.path == '/versao/publica')
    assert route.methods == {'GET'}
    assert not route.dependant.dependencies
