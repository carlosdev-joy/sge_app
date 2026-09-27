"""Contrato v1/v2: isolamento ORQ, preservação legada e segredos."""
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))

import pytest
from services import pipeline_params as pp
from tests.test_pipelines_params import cliente, _Conn, _Cursor
from routers import pipelines as P


def raw(nome='pA', **over):
    return dict(param_name=nome, param_type='String', param_source='fixo',
                param_value='valor', **over)


def salvo(nome='pA', **over):
    linhas, erros = P._preparar_params_ds([raw(nome)], {})
    assert not erros
    return dict(linhas[0], **(pp.PADRAO | over))


def preparar(itens, existentes=(), versao=2):
    return pp.preparar(itens, existentes, versao, P._preparar_params_ds)


def test_save_legado_preserva_orquestra_e_metadados_importados():
    ds = salvo(param_procedencia='datastage', param_import_project='PRJ', param_import_job='JOB')
    orq = salvo('diretorio', param_destino='orquestra')
    linhas, erros = preparar([raw()], [ds, orq], 1)
    assert not erros
    assert linhas[0]['param_import_job'] == 'JOB'
    assert linhas[1] == dict(orq, param_order=1)
    linhas, erros = preparar([], [ds, orq], 1)
    assert not erros and linhas == [orq]


def test_save_legado_nao_reclassifica_orquestra_por_nome():
    linhas, erros = preparar([raw()], [salvo(param_destino='orquestra')], 1)
    assert not linhas and erros


def test_v2_pode_remover_todos_sem_sobras_e_distingue_caixa():
    assert preparar([], [salvo()]) == ([], [])
    linhas, erros = preparar([raw('pA'), raw('pa', param_destino='orquestra')])
    assert not erros and len(linhas) == 2
    assert preparar([raw(), raw()])[1]


@pytest.mark.parametrize('campo,valor', [
    ('param_destino', None), ('param_destino', 'DATastage'),
    ('param_destino', []), ('param_procedencia', 'qualquer'),
    ('param_import_job', 'J'), ('param_descricao', '🙂' * 251),
    ('param_value', {}), ('param_value', 'abc\x00def'),
    ('param_name', []), ('param_type', 1),
])
def test_entrada_invalida_recusada_sem_exception(campo, valor):
    item = raw(); item[campo] = valor
    linhas, erros = preparar([item])
    assert not linhas and erros


def test_procedencia_importada_exige_fonte_e_nao_implica_destino():
    assert preparar([raw(param_procedencia='datastage')])[1]
    linhas, erros = preparar([raw(param_procedencia='datastage',
        param_import_project='PRJ', param_import_job='JOB', param_destino='orquestra')])
    assert not erros and linhas[0]['param_destino'] == 'orquestra'


def test_encrypted_cifrado_e_mascara_preservada(monkeypatch):
    monkeypatch.setattr('routers.jobs.encrypt_password', lambda v: 'cifrado:' + v)
    item = raw(param_destino='orquestra'); item['param_type'] = 'Encrypted'
    linhas, erros = preparar([item])
    assert not erros and linhas[0]['param_value'] == 'cifrado:valor'
    item['param_value'] = '***'
    novos, erros = preparar([item], linhas)
    assert not erros and novos == linhas
    assert preparar([item])[1]


class CatalogoCursor(_Cursor):
    def __init__(self, params=(), **kwargs):
        super().__init__(**kwargs)
        self.params = params
        self.fechado = False

    def fetchone(self):
        if 'INFORMATION_SCHEMA.COLUMNS' in self._ultimo:
            return (5,)
        return super().fetchone()

    def fetchall(self):
        if 'FROM dbo.etl_pipeline_param' in self._ultimo:
            return [tuple(p[k] for k in pp.COLS + pp.META) for p in self.params]
        return []

    def close(self):
        self.fechado = True


def test_get_v1_filtra_orq_e_v2_mascara_segredos(cliente):
    ds = salvo()
    orq = salvo('senha', param_destino='orquestra')
    orq.update(param_type='Encrypted', param_value='token-secreto')
    cur = CatalogoCursor([ds, orq])
    with patch.object(P, 'get_db_conn', return_value=_Conn(cur)):
        r = cliente.get('/pipelines/P/parametros')
        assert r.status_code == 200 and len(r.json()['parametros']) == 1
        r = cliente.get('/pipelines/P/parametros?parametros_versao=2')
    assert r.status_code == 200 and len(r.json()['parametros']) == 2
    assert 'token-secreto' not in r.text
    assert r.json()['parametros'][1]['tem_valor']
    assert cur.fechado


def test_get_v2_sem_schema_nomeia_migration(cliente):
    with patch.object(P, 'get_db_conn', return_value=_Conn(_Cursor())):
        r = cliente.get('/pipelines/P/parametros?parametros_versao=2')
    assert r.status_code == 503 and '129' in r.text


def test_get_erro_nao_expoe_internals(cliente):
    with patch.object(P, 'get_db_conn', side_effect=RuntimeError('senha:nao-expor')):
        r = cliente.get('/pipelines/P/parametros?parametros_versao=2')
    assert r.status_code == 503 and 'nao-expor' not in r.text


def test_insert_parametrizado_e_preserva_valor_literal():
    cur = CatalogoCursor()
    p = salvo(param_destino='orquestra'); p['param_value'] = "';DROP TABLE x;--"
    pp.gravar(cur, 'PIPE', [p])
    sql, values = cur.executados[-1]
    assert p['param_value'] not in sql and p['param_value'] in values
    assert sql.count('?') == len(values)


def test_runtime_legado_fallback_apenas_coluna_destino_ausente():
    from utils import ds_params as dp
    class Hook:
        def get_records(self, sql, parameters=None):
            if 'param_destino' in sql:
                raise RuntimeError("Invalid column name 'param_destino'")
            return [('pA', 'String', 'v', 'fixo', None, None, None, None)]
    assert dp.carregar_pipeline(Hook(), 'P')[0]['param_name'] == 'pA'
    class BadHook:
        def get_records(self, sql, parameters=None):
            raise RuntimeError("Invalid column name 'param_type'")
    with pytest.raises(RuntimeError):
        dp.carregar_pipeline(BadHook(), 'P')


def test_runtime_exclui_orq_antes_de_resolver_ou_decifrar():
    from utils import ds_params as dp
    class Hook:
        def get_records(self, sql, parameters=None):
            assert "param_destino='datastage'" in sql
            assert parameters == ('P',)
            return []
    assert dp.carregar_pipeline(Hook(), 'P') == []


def test_rerun_so_consulta_destino_datastage(monkeypatch):
    from services import rerun_params as rp
    monkeypatch.setattr(rp, '_tem_tabela', lambda *a: True)
    monkeypatch.setattr(rp, '_tem_coluna', lambda *a: True)
    cur = CatalogoCursor()
    assert rp._defaults_pipeline(cur, 'P') == []
    assert "param_destino='datastage'" in cur.executados[-1][0]


@pytest.mark.parametrize('versao', [1, 2])
def test_schema_parcial_bloqueia_get_sem_expor_orq(cliente, versao):
    cur = CatalogoCursor([salvo(param_destino='orquestra')])
    cur.fetchone = lambda: (1,)
    with patch.object(P, 'get_db_conn', return_value=_Conn(cur)):
        r = cliente.get(f'/pipelines/P/parametros?parametros_versao={versao}')
    assert r.status_code == 503 and '129' in r.text
    assert all('SELECT param_name' not in sql for sql, _ in cur.executados)


# Exercita register real com o dublê estatal do cadastro de pipelines.
from tests.test_dependencias_f5 import (FakePipeDb, FakePipeCur, _linha_pipeline,
                                      _body_registro, _patch_airflow)
from deps import get_current_user, PERM_EDITAR
from api.main import app


class CatalogoDb(FakePipeDb):
    def __init__(self, params=(), colunas=5):
        super().__init__(pipelines={'PIPE_A': _linha_pipeline()})
        self.params = list(params)
        self.colunas = colunas
        self.rollback_count = 0
        self.deletes = 0

    def cursor(self):
        return CatalogoCur(self)

    def rollback(self):
        self.rollback_count += 1


class CatalogoCur(FakePipeCur):
    def execute(self, sql, params=()):
        if 'COLUMN_NAME IN' in sql and 'etl_pipeline_param' in sql:
            self._rows = [(self.db.colunas,)]; return
        if 'INFORMATION_SCHEMA.TABLES' in sql and 'etl_pipeline_param' in sql:
            self._rows = [(1,)]; return
        if sql.startswith('SELECT param_name') and 'FROM dbo.etl_pipeline_param' in sql:
            self._rows = [tuple(p[k] for k in pp.COLS + pp.META) for p in self.db.params]; return
        if sql.startswith('DELETE FROM dbo.etl_pipeline_param'):
            self.db.params = []; self.db.deletes += 1; return
        if sql.startswith('INSERT INTO dbo.etl_pipeline_param'):
            self.db.params.append(dict(zip(pp.COLS + pp.META, params[1:]))); return
        return super().execute(sql, params)


@pytest.fixture
def editor(cliente):
    app.dependency_overrides[get_current_user] = lambda: {
        'matricula': 'U1', 'perfil': 'desenvolvedor', 'permissoes': [PERM_EDITAR]}
    return cliente


def test_register_v1_preserva_orq_e_v2_edita_catalogo(editor):
    db = CatalogoDb([salvo('interno', param_destino='orquestra')])
    with patch.object(P, 'get_db_conn', return_value=db), _patch_airflow():
        r = editor.post('/pipelines/register', json=_body_registro(parametros=[raw()]))
        assert r.status_code == 200, r.text
        assert len(db.params) == 2
        r = editor.post('/pipelines/register', json=_body_registro(
            parametros_versao=2, parametros=[raw('novo', param_destino='orquestra')]))
        assert r.status_code == 200, r.text
        assert [p['param_name'] for p in db.params] == ['novo']
        r = editor.post('/pipelines/register', json=_body_registro())
        assert r.status_code == 200 and db.params[0]['param_name'] == 'novo'


@pytest.mark.parametrize('colunas,expected', [(0, 503), (1, 503), (4, 503), (5, 422)])
def test_register_recusa_antes_de_escrever_e_faz_rollback(editor, colunas, expected):
    db = CatalogoDb(colunas=colunas)
    with patch.object(P, 'get_db_conn', return_value=db), _patch_airflow():
        r = editor.post('/pipelines/register', json=_body_registro(
            parametros_versao=2, parametros=[raw(param_destino='invalido')]))
    assert r.status_code == expected, r.text
    assert db.deletes == 0 and db.commits == 0 and db.rollback_count == 1


def test_erro_v1_continua_legivel_e_nao_expoe_valor_oculto(editor):
    db = CatalogoDb([salvo(param_destino='orquestra')])
    with patch.object(P, 'get_db_conn', return_value=db), _patch_airflow():
        r = editor.post('/pipelines/register', json=_body_registro(parametros=[raw()]))
    assert r.status_code == 422
    assert isinstance(r.json()['detail'], str) and 'Orquestra' in r.json()['detail']
    assert db.deletes == 0


def test_editor_sem_permissao_nao_chega_ao_banco(cliente):
    with patch.object(P, 'get_db_conn') as db:
        r = cliente.post('/pipelines/register', json=_body_registro(
            parametros_versao=2, parametros=[raw(param_destino='orquestra')]))
    assert r.status_code == 403
    db.assert_not_called()


def test_register_v2_sem_tabela_retorna_503(editor, monkeypatch):
    db = CatalogoDb()
    monkeypatch.setattr(P, '_tem_tabela_pipeline_param', lambda cur: False)
    with patch.object(P, 'get_db_conn', return_value=db), _patch_airflow():
        r = editor.post('/pipelines/register', json=_body_registro(
            parametros_versao=2, parametros=[raw(param_destino='orquestra')]))
    assert r.status_code == 503 and '129' in r.text
    assert db.deletes == 0 and db.commits == 0
