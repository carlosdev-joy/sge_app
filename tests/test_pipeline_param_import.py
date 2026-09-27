"""Importação somente leitura: limites, erros fechados e segredo fora da resposta."""
from unittest.mock import MagicMock, patch
import threading
import time
import pytest
from services import pipeline_param_import as imp
from tests.test_pipeline_catalogo import CatalogoCursor
from tests.test_pipelines_params import cliente, _Conn
from deps import get_current_user
from api.main import app


@pytest.mark.parametrize('project,jobs', [
    ('P;id', ['J']), ('P', ['J\n']), ('P', []), ('P', ['J'] * 2),
    ('P', [str(i) for i in range(6)]), (None, ['J']), ('P', [None]),
])
def test_pedido_invalido(project, jobs):
    with pytest.raises(imp.ImportErrorDS):
        imp.validar_pedido(project, jobs)


def test_parse_default_nao_current_e_encrypted_nao_vaza():
    text = 'Type : String (0)\nDefault Value : correto\nCurrent Value : incorreto\nOriginal Default Value : antigo'
    assert imp.parse_paraminfo(text, 'pA', 'P', 'J')['param_value'] == 'correto'
    text = 'Type : Encrypted (1)\nDefault Value : SEGREDO\nHelp Text : SEGREDO\nCurrent Value : SEGREDO'
    item = imp.parse_paraminfo(text, 'pA', 'P', 'J')
    assert 'SEGREDO' not in str(item)
    assert item['param_value'] == '' and not item['tem_valor']


@pytest.mark.parametrize('text', ['Type : Desconhecido', 'Type : String', 'Type : String\nType : String'])
def test_formato_desconhecido_nao_inventa(text):
    with pytest.raises(imp.ImportErrorDS):
        imp.parse_paraminfo(text, 'pA', 'P', 'J')


class Canal:
    def __init__(self, out=b'pA\n', err=b'', code=0):
        self.out, self.err, self.code, self.closed = out, err, code, False
    def recv_ready(self): return bool(self.out)
    def recv_stderr_ready(self): return bool(self.err)
    def recv(self, n):
        data, self.out = self.out[:n], self.out[n:]
        return data
    def recv_stderr(self, n):
        data, self.err = self.err[:n], self.err[n:]
        return data
    def exit_status_ready(self): return True
    def recv_exit_status(self): return self.code
    def close(self): self.closed = True


def executar(canal, deadline=None):
    client = MagicMock()
    stdout = MagicMock(channel=canal)
    client.exec_command.return_value = MagicMock(), stdout, MagicMock()
    return imp._executar(client, ['-lparams', 'P', 'J'], deadline or time.monotonic() + 5)


def test_drena_stdout_e_stderr_sem_deadlock():
    assert executar(Canal(b'a' * 20000, b'b' * 20000)) == 'a' * 20000


@pytest.mark.parametrize('canal', [Canal(code=1), Canal(err=b'Status code = -1'), Canal(b'x' * (imp.MAX_BYTES + 1))])
def test_erros_comando_sem_saida_bruta(canal):
    with pytest.raises(imp.ImportErrorDS) as error:
        executar(canal)
    assert canal.closed and len(str(error.value)) < 160


def test_timeout_antes_do_comando():
    with pytest.raises(imp.ImportErrorDS, match='Tempo limite'):
        executar(Canal(), time.monotonic() - 1)


def test_previa_limpa_falha_ssh_e_libera_vaga(monkeypatch):
    monkeypatch.setattr(imp.ssh, 'ssh_configured', lambda: True)
    monkeypatch.setattr(imp.ssh, '_conectar', MagicMock(side_effect=RuntimeError('SEGREDO')))
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(imp, '_SLOTS', slots)
    with pytest.raises(imp.ImportErrorDS) as error:
        imp.prever('P', ['J'])
    assert 'SEGREDO' not in str(error.value)
    assert slots.acquire(blocking=False)


def test_previa_completa_apenas_consulta(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(imp.ssh, 'ssh_configured', lambda: True)
    monkeypatch.setattr(imp.ssh, '_conectar', lambda: client)
    execute = MagicMock(side_effect=['pA\npA\n$ENV\n', 'Type : String\nDefault Value : v'])
    monkeypatch.setattr(imp, '_executar', execute)
    result = imp.prever('P', ['J'])
    assert len(result['parametros']) == 1 and len(result['avisos']) == 1
    assert [c.args[1] for c in execute.call_args_list] == [['-lparams', 'P', 'J'], ['-paraminfo', 'P', 'J', 'pA']]
    client.close.assert_called_once()


def test_rota_readonly_e_status(cliente):
    app.dependency_overrides[get_current_user] = lambda: {'matricula': 'U', 'permissoes': ['acao_editar']}
    cur = CatalogoCursor()
    with patch('routers.pipelines.get_db_conn', return_value=_Conn(cur)), patch('routers.pipelines._get_valid_projects', return_value=['P']), patch.object(imp, 'prever', return_value={'parametros': [], 'avisos': []}) as preview:
        assert cliente.get('/pipelines/parametros/catalogo-status').status_code == 200
        r = cliente.post('/pipelines/parametros/importar-previa', json={'project_name': 'P', 'jobs': ['J']})
    assert r.status_code == 200, r.text
    preview.assert_called_once_with('P', ['J'])
    assert not any(word in sql.upper() for sql, _ in cur.executados for word in ['INSERT ', 'UPDATE ', 'DELETE '])


def test_rota_recusa_projeto_e_schema_sem_ssh(cliente):
    app.dependency_overrides[get_current_user] = lambda: {'matricula': 'U', 'permissoes': ['acao_editar']}
    with patch('routers.pipelines.get_db_conn', return_value=_Conn(CatalogoCursor())), patch('routers.pipelines._get_valid_projects', return_value=[]), patch.object(imp, 'prever') as preview:
        assert cliente.post('/pipelines/parametros/importar-previa', json={'project_name': 'P', 'jobs': ['J']}).status_code == 422
        preview.assert_not_called()
    with patch('routers.pipelines.get_db_conn', return_value=_Conn(CatalogoCursor(tem_tabela=False))):
        assert cliente.get('/pipelines/parametros/catalogo-status').status_code == 503


def test_rota_exige_permissao(cliente):
    app.dependency_overrides[get_current_user] = lambda: {'matricula': 'U', 'perfil': 'operador', 'permissoes': []}
    with patch.object(imp, 'prever') as preview:
        assert cliente.post('/pipelines/parametros/importar-previa', json={'project_name': 'P', 'jobs': ['J']}).status_code == 403
        preview.assert_not_called()


@pytest.mark.parametrize('text', [
    'Type: String\nDefault Value: primeira\nsegunda\nPrompt: P',
    'Type: String\nDefault Value: primeira\nsegunda: parte',
])
def test_multilinha_nao_trunca(text):
    with pytest.raises(imp.ImportErrorDS, match='multilinha'):
        imp.parse_paraminfo(text, 'pA', 'P', 'J')


@pytest.mark.parametrize('project,jobs', [('1PROJECT', ['J']), ('P', ['JOB.1'])])
def test_origem_deve_ser_persistivel(project, jobs):
    with pytest.raises(imp.ImportErrorDS):
        imp.validar_pedido(project, jobs)
