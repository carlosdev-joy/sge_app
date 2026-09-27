"""Reconciliação atômica, CAS e compatibilidade do canvas com validadores."""
from copy import deepcopy
from unittest.mock import MagicMock
import uuid
import pytest
from services import valida_arquivo_fluxo as vf
from services import valida_arquivo_store as store


def cfg(revisao=0, alvo='A'):
    return dict(revisao=revisao, ssh_conn_id='SSH', timeout_segundos=60, entradas=[dict(
        entrada_id=str(uuid.uuid4()), tipo='arquivo', arquivo='dados.csv', diretorio_literal='/dados',
        param_name=None, alvo=alvo, se_nao_existe='falhar', se_zero_linhas='pular', ignorar_cabecalho=True)])


@pytest.fixture
def banco(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [('V', 'valida_arquivo', None, None), ('A', 'shell', 'V', None)]
    original = cfg(2)
    monkeypatch.setattr(store, 'disponivel', lambda c: True)
    monkeypatch.setattr(vf, 'runtime_disponivel', lambda c: True)
    monkeypatch.setattr(vf.pp, 'ler', lambda *a: [])
    monkeypatch.setattr(store, 'ler', lambda *a, **kw: deepcopy(original) if a[2] == 'V' else None)
    return cur, original


def test_cliente_antigo_preserva_tipo_e_configuracao(banco):
    cur, original = banco
    plano = vf.preparar(cur, 'P', [{'job_name': 'A', 'layout_x': 12}], set())
    assert plano['configs']['V']['config']['entradas'][0]['arquivo'] == 'dados.csv'
    assert not plano['configs']['V']['escrever']
    assert plano['configs']['V']['revisao'] == original['revisao']


@pytest.mark.parametrize('tipo', ['valida_arquivo', 'VALIDA_ARQUIVO', ' valida_arquivo '])
def test_tipo_normalizado_nao_permite_novo_sem_config(banco, tipo):
    cur, _ = banco
    cur.fetchall.return_value = []
    with pytest.raises(ValueError, match='Configure'):
        vf.preparar(cur, 'P', [{'job_name': 'NOVO', 'job_type': tipo}], set())


def test_revisao_antiga_recusa_antes_das_exclusoes(banco):
    cur, original = banco
    original = deepcopy(original); original['revisao'] = 1
    with pytest.raises(store.Conflito):
        vf.preparar(cur, 'P', [{'job_name': 'V', 'job_type': 'valida_arquivo', 'valida_arquivo': original}], {'A'})
    assert not any(x.args[0].startswith('DELETE') for x in cur.execute.call_args_list)


def test_remocao_do_alvo_sem_remapear_recusada(banco):
    cur, _ = banco
    with pytest.raises(ValueError, match='destino'):
        vf.preparar(cur, 'P', [], {'A'})


def test_remapeamento_e_exclusao_respeitam_fks(banco, monkeypatch):
    cur, original = banco
    nova = deepcopy(original); nova['entradas'][0]['alvo'] = 'B'
    nodes = [dict(job_name='V', job_type='valida_arquivo', valida_arquivo=nova),
             dict(job_name='B', job_type='python', depends_on_jobs=['V'])]
    plano = vf.preparar(cur, 'P', nodes, {'A'})
    vf.antes_de_excluir(cur, 'P', plano)
    assert any('DELETE FROM dbo.etl_valida_arquivo_config' in x.args[0] for x in cur.execute.call_args_list)
    salvar = MagicMock(return_value=dict(revisao=3, exige_publicacao=False))
    monkeypatch.setattr(store, 'salvar', salvar)
    assert vf.aplicar(cur, 'P', plano)['V'] == dict(revisao=3, exige_publicacao=True)
    assert salvar.call_args.args[-1] == 2


def test_excluir_validador_remove_filhos_antes_do_cabecalho(banco):
    cur, _ = banco
    plano = vf.preparar(cur, 'P', [{'job_name': 'A', 'job_type': 'shell', 'depends_on_jobs': []}], {'V'})
    cur.execute.reset_mock()
    vf.antes_de_excluir(cur, 'P', plano)
    chamadas = cur.execute.call_args_list
    assert 'etl_valida_arquivo_config' in chamadas[0].args[0]
    assert 'etl_valida_arquivo_no' in chamadas[1].args[0]


def test_nao_troca_tipo_de_validador(banco):
    cur, _ = banco
    with pytest.raises(ValueError, match='tipo'):
        vf.preparar(cur, 'P', [dict(job_name='V', job_type='shell')], set())


def test_runtime_incompleto_recusa_configuracao(banco, monkeypatch):
    cur, _ = banco
    monkeypatch.setattr(vf, 'runtime_disponivel', lambda c: False)
    with pytest.raises(ValueError, match='130 a 133'):
        vf.preparar(cur, 'P', [], set())


def test_novo_tipo_normalizado_exige_migration(monkeypatch):
    monkeypatch.setattr(store, 'disponivel', lambda c: False)
    with pytest.raises(ValueError, match='131'):
        vf.preparar(MagicMock(), 'P', [dict(job_name='V', job_type=' VALIDA_ARQUIVO ')], set())


def test_grafia_nao_contorna_tipo_persistido(banco):
    cur, _ = banco
    with pytest.raises(ValueError, match='grafia'):
        vf.preparar(cur, 'P', [dict(job_name='v', job_type='shell')], set())


@pytest.mark.parametrize('nome', ['VALIDA', 'valida', 'VaLiDa'])
def test_rota_legada_nao_converte_validador_por_colacao(monkeypatch, nome):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from deps import get_current_user, PERM_EDITAR
    from routers import jobs
    class Cursor:
        def __init__(self, pipeline):
            self.pipeline = pipeline; self.executed = []; self._last = ''
        def execute(self, sql, params=()):
            self._last = sql; self.executed.append((sql, params))
        def fetchone(self):
            if 'INFORMATION_SCHEMA.COLUMNS' in self._last: return (1,)
            if 'FROM dbo.etl_pipeline WHERE pipeline_name' in self._last: return (self.pipeline,)
            return None
        def close(self): pass
        def fetchall(self):
            if 'SELECT job_name, job_type FROM dbo.etl_pipeline_job' in self._last:
                return [('VALIDA', 'valida_arquivo')]
            return []
    cur = Cursor('P'); conn = MagicMock(); conn.cursor.return_value = cur
    monkeypatch.setattr(jobs, 'get_db_conn', lambda: conn)
    app = FastAPI(); app.include_router(jobs.router)
    app.dependency_overrides[get_current_user] = lambda: {'permissoes': [PERM_EDITAR]}
    with TestClient(app) as client:
        r = client.post('/pipelines/jobs/register', json={'pipeline_name': 'P', 'require_lineage': False,
            'jobs': [dict(job_name=nome, execution_order=1, job_type='shell', job_command='true')]})
    assert r.status_code == 422
    assert 'canvas' in str(r.json())
    conn.commit.assert_not_called()
    assert not any('sp_etl_pipeline_job_upsert' in sql for sql, _ in cur.executed)
