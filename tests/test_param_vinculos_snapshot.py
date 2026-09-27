"""F2b: referências, segredo, precedência e snapshot imutável."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dags'))
from services import param_vinculos as pv
from utils import param_snapshot as snap
from routers.jobs import _validate_python_node
from tests.test_dag_factory_python import factory, _pipeline, _py_job


def param(name='diretorio', value='/dados/a.py', typ='Pathname', dest='datastage'):
    return dict(param_name=name, param_value=value, param_type=typ, param_source='fixo', param_destino=dest)


def payload():
    return dict(versao=1, pipeline='P', run_id='R', data_execucao='2026-09-27',
                catalogo=[param(), param('senha', 'cipher', 'Encrypted')],
                jobs=[dict(job_name='D', job_type='datastage', param_vinculos_json='{"pDir":"diretorio"}'),
                      dict(job_name='PY', job_type='python', param_vinculos_json='{"script_path":"diretorio"}',
                           python_json='{"modo":"arquivo","script_path":""}')],
                etapa=[], overrides=[])


@pytest.mark.parametrize('raw,tipo,py', [
    ({'pDir': 'diretorio'}, 'datastage', None),
    ({'pSegredo': 'senha'}, 'datastage', None),
    ({'script_path': 'diretorio'}, 'python', {'modo':'arquivo'}),
    ({'destino_dir': 'diretorio'}, 'python', {'modo':'codigo'}),
])
def test_referencias_validas(raw,tipo,py):
    assert pv.normalizar(raw,tipo,payload()['catalogo'],py) == raw


@pytest.mark.parametrize('raw,tipo,py', [
    ({'script_path':'senha'},'python',{'modo':'arquivo'}),
    ({'destino_dir':'diretorio'},'python',{'modo':'arquivo'}),
    ({'script_path':'diretorio'},'python',{'modo':'modulo'}),
    ({'interpretador':'diretorio'},'python',{'modo':'arquivo'}),
    ({'pA':'ausente'},'datastage',None),
    ({'pA':'diretorio'},'shell',None),
    ({'pA;id':'diretorio'},'datastage',None),
    ([], 'datastage', None), ({'pA':None},'datastage',None),
])
def test_invalidos_fecham(raw,tipo,py):
    with pytest.raises(ValueError):
        pv.normalizar(raw,tipo,payload()['catalogo'],py)


def test_validacao_python_aceita_path_vazio_so_com_referencia():
    cfg={'modo':'arquivo','script_path':''}
    assert _validate_python_node(cfg,'SSH')
    assert not _validate_python_node(cfg,'SSH',{'script_path':'diretorio'})


def test_ds_local_vence_referencia_orq_nao_vaza_default():
    original=payload()
    rows, defaults, overrides = snap.etapa_ds(original,'D')
    assert rows[0]['param_name']=='pDir'
    assert rows[0]['param_value']=='/dados/a.py'
    assert [p['param_name'] for p in defaults] == ['diretorio','senha'] and not overrides
    original['etapa']=[dict(param('pDir','/local'),job_name='D')]
    assert snap.etapa_ds(original,'D')[0][0]['param_value']=='/local'


def test_python_literal_vence_e_snapshot_nao_muda():
    original=payload(); antes=copy.deepcopy(original)
    assert snap.python_config(original,'PY')['script_path']=='/dados/a.py'
    assert original==antes
    original['jobs'][1]['python_json']='{"modo":"arquivo","script_path":"/local.py"}'
    assert snap.python_config(original,'PY')['script_path']=='/local.py'


def test_referencia_ausente_ou_segredo_python_falha():
    original=payload(); original['catalogo']=[]
    with pytest.raises(ValueError): snap.etapa_ds(original,'D')
    with pytest.raises(ValueError): snap.python_config(original,'PY')
    original=payload();original['jobs'][1]['param_vinculos_json']='{"script_path":"senha"}'
    with pytest.raises(ValueError): snap.python_config(original,'PY')


def test_carregar_snapshot_cifrado_original(monkeypatch):
    key=Fernet.generate_key();monkeypatch.setenv('ORQUESTRA_CONN_KEY',key.decode())
    token=Fernet(key).encrypt(json.dumps(payload()).encode()).decode()
    hook=MagicMock();hook.get_first.return_value=(token,)
    assert snap.carregar(hook,'P','R')==payload()
    assert 'cipher' not in token
    with pytest.raises(ValueError): snap.carregar(hook,'P','OUTRA_CORRIDA')


@pytest.mark.parametrize('row', [None, ('invalido',)])
def test_snapshot_inexistente_ou_corrompido_nunca_recriado(row):
    hook=MagicMock();hook.get_first.return_value=row
    with pytest.raises(ValueError,match='original'):
        snap.carregar(hook,'P','R')


def test_captura_retry_sem_snapshot_nao_reconstroi(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY',Fernet.generate_key().decode())
    hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.return_value=None
    with pytest.raises(ValueError,match='original'):snap.capturar(hook,'P','R',False)
    assert cur.execute.call_count==1
    hook.get_conn.return_value.rollback.assert_called_once()


def test_captura_existente_idempotente_sem_reler_catalogo(monkeypatch):
    key=Fernet.generate_key();monkeypatch.setenv('ORQUESTRA_CONN_KEY',key.decode())
    hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.return_value=(Fernet(key).encrypt(json.dumps(payload()).encode()).decode(),)
    assert snap.capturar(hook,'P','R',False) is None
    assert cur.execute.call_count==1
    hook.get_conn.return_value.commit.assert_called_once()


def test_factory_congela_antes_de_liberar_e_ativa_operador(factory):
    job=_py_job({'modo':'arquivo','script_path':''},ssh='SSH')
    job['param_vinculos_json']='{"script_path":"diretorio"}'
    src=factory._generate_dag_source(_pipeline(),[job])
    assert 'snapshot_parametros=True' in src
    assert 'from utils.param_snapshot import capturar' in src
    check=src[src.index('def check_agenda('):]
    assert check.index('capturar(')<check.index('return ok')
    assert 'primeira_tentativa=context' in src
    compile(src,'gerado','exec')


def test_factory_flag_permanente_apos_remover_refs(factory):
    job=_py_job({'modo':'arquivo','script_path':'/local.py'},ssh='SSH')
    job['_snapshot_habilitado']=True
    src=factory._generate_dag_source(_pipeline(),[job])
    assert 'snapshot_parametros=True' in src and 'from utils.param_snapshot import capturar' in src


def test_orq_exclusivo_nao_vai_para_ds():
    with pytest.raises(ValueError,match='exclusivo'):
        pv.normalizar({'pAlvo':'pORQ'},'datastage',[param('pORQ',dest='orquestra')])


def test_payload_parcial_valida_tipo_python_persistido(monkeypatch):
    cur=MagicMock()
    cur.fetchone.side_effect=[(-1,),(1,),('python','{"modo":"arquivo","script_path":""}','{}')]
    monkeypatch.setattr(pv.pp,'ler',lambda c,p:payload()['catalogo'])
    with pytest.raises(ValueError,match='sem segredo'):
        pv.preparar(cur,'P',{'job_name':'PY','param_vinculos':{'script_path':'senha'}})


def test_modo_novo_nao_preserva_referencia_incompativel(monkeypatch):
    cur=MagicMock()
    cur.fetchone.side_effect=[(-1,),(1,),('python','{"modo":"arquivo"}','{"script_path":"diretorio"}')]
    monkeypatch.setattr(pv.pp,'ler',lambda c,p:payload()['catalogo'])
    with pytest.raises(ValueError,match='modo ativo'):
        pv.preparar(cur,'P',{'job_name':'PY','python':{'modo':'codigo','destino_dir':'/dados'}})


def test_api_previa_original_sem_overrides_editaveis():
    from services import param_snapshot as api
    p=payload()
    out=api.previa(p,['D','PY'])
    assert out[0]['original'] and out[1]['original']
    assert all(not x['editavel'] for e in out for x in e['itens'])
    assert next(x for x in out[0]['itens'] if x['param_name']=='senha')['valor_efetivo']=='***'
    assert 'cipher' not in json.dumps(out)


def test_estrutura_api_worker_identica():
    from services import param_snapshot as api
    original=payload()['jobs']
    assert api.estrutura(original)==snap.estrutura(original)
    changed=copy.deepcopy(original);changed[1]['ssh_conn_id']='outro'
    assert api.estrutura(changed)!=api.estrutura(original)


def test_publicacao_incompativel_recusada_sem_ler_valores(monkeypatch):
    key=Fernet.generate_key();monkeypatch.setenv('ORQUESTRA_CONN_KEY',key.decode())
    p=payload();p['project']='PRJ'
    hook=MagicMock()
    hook.get_records.return_value=[(Fernet(key).encrypt(json.dumps(p).encode()).decode(),)]
    snap.validar_publicacao(hook,'P','PRJ',p['jobs'])
    changed=copy.deepcopy(p['jobs']);changed[1]['ssh_conn_id']='outro'
    with pytest.raises(ValueError,match='incompatível'):snap.validar_publicacao(hook,'P','PRJ',changed)
    with pytest.raises(ValueError,match='incompatível'):snap.validar_publicacao(hook,'P','OUTRO_PROJETO',p['jobs'])


def test_captura_recusa_estrutura_diferente_da_dag(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY',Fernet.generate_key().decode())
    p=payload();hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.side_effect=[None,('PRJ',)]
    monkeypatch.setattr(snap,'_lista',MagicMock(side_effect=[p['catalogo'],p['jobs'],p['etapa'],p['overrides']]))
    with pytest.raises(ValueError):snap.capturar(hook,'P','R',estrutura_esperada=[],projeto_esperado='PRJ')
    assert not any('INSERT' in c.args[0] for c in cur.execute.call_args_list)


def test_api_original_nao_substitui_snapshot_ausente(monkeypatch):
    from services import param_snapshot as api
    monkeypatch.setattr(api,'ativo',lambda c,p:True)
    cur=MagicMock();cur.fetchone.return_value=None
    with pytest.raises(ValueError,match='original'):api.original(cur,'P','R')

@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['reorder', 'delete'])
async def test_alteracao_estrutural_rejeitada_faz_rollback_e_fecha(monkeypatch, operation):
    from fastapi import HTTPException
    from routers import jobs
    conn=MagicMock(); conn.cursor.return_value.rowcount=1
    monkeypatch.setattr(jobs,'get_db_conn',lambda:conn)
    def rejeitar(*args):
        raise ValueError('Corrida retomável')
    monkeypatch.setattr(jobs.ps,'validar_estrutura',rejeitar)
    with pytest.raises(HTTPException) as exc:
        if operation=='reorder':
            await jobs.reorder_pipeline_jobs({'pipeline_name':'P','jobs':[{'job_name':'D','execution_order':2}]},{})
        else:
            await jobs.delete_pipeline_job('P','D',{})
    assert exc.value.status_code==409
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()
    conn.cursor.return_value.close.assert_called_once()
    conn.close.assert_called_once()


def test_migration_parcial_nao_habilita_vinculos():
    cur=MagicMock();cur.fetchone.side_effect=[(1,),(0,)]
    assert not pv.disponivel(cur)


@pytest.mark.parametrize('incoming', [{}, {'python_json':'{"modo":"codigo","destino_dir":"/dados"}'}])
def test_python_parcial_preserva_ou_valida_json_alternativo(monkeypatch,incoming):
    cur=MagicMock();cur.fetchone.side_effect=[(-1,),(1,),('python','{"modo":"arquivo","script_path":"/dados/a.py"}','{"script_path":"diretorio"}')]
    monkeypatch.setattr(pv.pp,'ler',lambda *a:payload()['catalogo'])
    node=dict(job_name='PY',**incoming)
    if incoming:
        with pytest.raises(ValueError,match='modo ativo'): pv.preparar(cur,'P',node)
    else:
        assert json.loads(pv.preparar(cur,'P',node))=={'script_path':'diretorio'}
        assert node['python']['modo']=='arquivo' and node['job_type']=='python'


def test_corrida_concluida_nao_reexecuta_em_outro_servidor():
    from services import param_snapshot as api
    original=payload(); original['jobs'][0]['ssh_conn_id']='SSH_A'
    atual=copy.deepcopy(original['jobs']);atual[0]['ssh_conn_id']='SSH_B'
    cur=MagicMock();cols=list({k for j in atual for k in j})
    cur.description=[(c,) for c in cols]
    cur.fetchall.return_value=[tuple(j.get(c) for c in cols) for j in atual]
    cur.fetchone.return_value=(None,)
    with pytest.raises(ValueError,match='servidor'): api.validar_retomada(cur,original)
    with pytest.raises(ValueError,match='Servidor'): snap.validar_servidor(original,'D','datastage','SSH_B')


def test_worker_confere_servidor_antes_do_comando():
    original=payload();original['jobs'][0]['ssh_conn_id']='SSH_A'; original['project']='PROJ'
    snap.validar_servidor(original,'D','datastage','ssh_lnxprd021','PROJ')
    with pytest.raises(ValueError):snap.validar_servidor(original,'D','datastage','ssh_lnxprd021','OUTRO')


@pytest.mark.asyncio
@pytest.mark.parametrize('overrides', [[], [{'job_name':'D','param_name':'p','param_value':'novo'}]])
async def test_rerun_snapshot_resolve_id_historico_e_recusa_override(monkeypatch,overrides):
    from unittest.mock import AsyncMock
    from fastapi import HTTPException
    from routers import execucoes as e
    monkeypatch.setattr(e,'get_db_conn',lambda:MagicMock())
    monkeypatch.setattr(e.ps,'ativo',lambda *a:True)
    resolve=AsyncMock(return_value=('P',{'run_id':'R'},None))
    monkeypatch.setattr(e,'_resolve_alvo_rerun',resolve)
    orig=MagicMock(return_value=payload());monkeypatch.setattr(e.ps,'original',orig)
    monkeypatch.setattr(e.ps,'validar_retomada',lambda *a:None)
    clear=AsyncMock(return_value={'dag_run_id':'R','tasks_limpas':['D']})
    monkeypatch.setattr(e,'_clear_no_airflow',clear)
    monkeypatch.setattr(e,'_apagar_overrides_silencioso',lambda *a:None)
    monkeypatch.setattr(e,'_aplicar_cascata',lambda *a,**k:dict(dependentes_reabertos=[],corridas_substituidas=[],corridas_irmas_aposentadas=[],auditado=True,avisos=[]))
    body=dict(pipeline_name='P',task_id='D',execution_id='20260927T120000')
    if overrides:
        body.update(dag_run_id='R',parametros=overrides)
        with pytest.raises(HTTPException) as exc:await e.rerun_from_task(body,{})
        assert exc.value.status_code==409
        clear.assert_not_called()
    else:
        result=await e.rerun_from_task(body,{})
        assert result['dag_run_id']=='R'
        resolve.assert_awaited_once()
        assert orig.call_args.args[2]=='R'
        assert clear.call_args.args[1]=='R'
