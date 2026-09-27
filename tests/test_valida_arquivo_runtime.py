"""F5: grafo gerado, barreiras de execução e classificação independente de notificação."""
import ast
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dags'))
from tests.test_dag_factory_aguarde import factory, _pipeline, _job
from services import valida_arquivo as va
import types
exc = sys.modules.setdefault('airflow.exceptions', types.ModuleType('airflow.exceptions'))
for exception_name in ('AirflowException', 'AirflowSkipException'):
    if not hasattr(exc, exception_name): setattr(exc, exception_name, type(exception_name, (Exception,), {}))
from utils import valida_arquivo_runtime as runtime


def cfg(alvos=('A',)):
    import uuid
    config = {'ssh_conn_id': 'ssh_amostra', 'timeout_segundos': 10, 'entradas': [dict(entrada_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, n)), tipo='arquivo', diretorio_literal='/tmp', arquivo=n+'.csv', alvo=n, se_nao_existe='pular', se_zero_linhas='pular', ignorar_cabecalho=False) for n in alvos]}
    out = va.normalizar(config, []); out['revisao'] = 1
    return out


def jobs(tipo='shell'):
    v = _job('V', 'valida_arquivo'); v['_valida_config'] = cfg()
    a = _job('A', tipo, order=2, depends='V')
    if tipo == 'python': a['python_json'] = '{"modo":"modulo","modulo":"test"}'
    if tipo == 'sql': a['sql_json'] = '{"sql":"SELECT 1"}'
    if tipo == 'decisao': a['condition_json'] = '{"tipo":"linhas_job","job":"V","operador":">","valor":0,"ramo_verdadeiro":[],"ramo_falso":[]}'
    return [v, a]


@pytest.mark.parametrize('tipo', sorted(va.TIPOS_ALVO))
def test_fabrica_guarda_todos_os_tipos(factory, tipo):
    src = factory._generate_dag_source(_pipeline(), jobs(tipo)); tree = ast.parse(src)
    constructors = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            args = {k.arg: k.value for k in node.keywords}
            if isinstance(args.get('task_id'), ast.Constant): constructors[args['task_id'].value] = args
    assert 'V' in constructors and 'A' in constructors
    assert constructors['A']['pre_execute'].id == '_guarda_valida'
    start = 'A' if tipo in ('decisao','notificacao','sql','aguarde','email') else 'log_start_A'
    assert constructors[start]['trigger_rule'].attr == 'ALL_DONE'
    assert 't_flow_close >> t_publish_dataset' in src
    assert 't_valida_V >> t_flow_close' in src
    assert 'validadores_esperados=' in src
    if tipo == 'aguarde':
        assert 't_wait_A = PythonOperator(' in src
        assert constructors['A']['python_callable'].id == '_aguarde_validado'
    if start != 'A': assert constructors['log_end_A']['trigger_rule'].attr == 'NONE_SKIPPED'


def test_sem_config_nao_publica(factory):
    js=jobs();js[0].pop('_valida_config')
    with pytest.raises(ValueError,match='sem configuração'):factory._generate_dag_source(_pipeline(),js)


@pytest.mark.parametrize('pais,propria,regra,esperado',[
    (['success'],'liberar','all_success','liberar'),
    (['validation_skip'],'liberar','all_success','liberar'),
    (['skipped'],'liberar','all_success','bloquear'),
    (['failed'],'pular','all_done','bloquear'),
    (['incomplete'],'liberar','all_done','bloquear'),
    (['success'],'pular','all_success','pular'),
    (['success'],'bloquear','all_success','bloquear'),
    (['success','skipped'],'liberar','none_failed_min_one_success','liberar'),
    (['validation_success','skipped'],'liberar','none_failed_min_one_success','bloquear'),
    (['skipped'],'liberar','all_done','liberar'),
    (['branch_skipped'],'liberar','all_done','bloquear'),
])
def test_guarda_nao_inventa_sucesso_operacional(pais,propria,regra,esperado):
    assert runtime.decidir_guarda(pais,propria,regra)==esperado


@pytest.mark.parametrize('libera',[True,False])
@pytest.mark.parametrize('notifica',[True,False])
def test_sem_movimento_politicas_independentes(libera,notifica):
    r=runtime.classificar({'A':{'estado':'skipped','por_validacao':True}},[],{'liberar_dependentes':libera,'notificar':notifica})
    assert r==dict(resultado='SEM_MOVIMENTO',liberar_dependentes=libera,notificar=notifica)


def test_branch_nao_e_sem_movimento():
    r=runtime.classificar({'A':{'estado':'skipped','por_validacao':False}},[],{'liberar_dependentes':True,'notificar':False})
    assert r['resultado']=='SEM_EXECUCAO' and not r['liberar_dependentes']


def test_execucao_parcial_e_falha():
    destinos={'A':{'estado':'success','por_validacao':False},'B':{'estado':'skipped','por_validacao':True}}
    assert runtime.classificar(destinos,[],{})['resultado']=='COM_MOVIMENTO'
    r=runtime.classificar(destinos,['V'],{})
    assert r['resultado']=='FALHA' and not r['liberar_dependentes']


def test_prova_skip_exige_mesma_tentativa_inicio():
    ti=SimpleNamespace(state='skipped',task_id='log_start_A',try_number=2,start_date=datetime.now(timezone.utc))
    hook=MagicMock();payload={'pipeline':'P','run_id':'R'}
    hook.get_first.return_value=(runtime.identidade(ti)[1],'pular','[]')
    assert runtime.pulado_pela_validacao(hook,payload,ti)
    assert hook.get_first.call_args.kwargs['parameters']==('P','R','log_start_A',2)
    ti.start_date+=timedelta(seconds=1)
    assert not runtime.pulado_pela_validacao(hook,payload,ti)


def test_conclusao_falha_escrita_nao_libera(monkeypatch):
    class Erro(Exception): pass
    monkeypatch.setattr(runtime,'AirflowException',Erro)
    hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.return_value=None;cur.rowcount=0
    with pytest.raises(Erro,match='bloqueados'):
        runtime.persistir_conclusao(hook,{'pipeline':'P','run_id':'R'},{'resultado':'SEM_MOVIMENTO','liberar_dependentes':True,'notificar':False},{},'2026-09-27')
    hook.get_conn.return_value.rollback.assert_called_once();hook.get_conn.return_value.commit.assert_not_called()


def test_prova_rejeita_validador_limpo_isoladamente():
    prova={'decisao':'liberar','origens':[{'no':'V','tentativa':1,'decisao':'liberar'}]}
    assert runtime.prova_atual(prova,['V'],{'V':1})
    assert not runtime.prova_atual(prova,['V'],{'V':2})
    assert not runtime.prova_atual(prova,['V'],{})


def test_task_tecnica_nome_maximo_cabe_no_schema():
    source=(Path(__file__).resolve().parents[1]/'sql/migrations/133_valida_arquivo_guardas.sql').read_text()
    assert len('log_start_'+'A'*200)==210
    assert 'task_id NVARCHAR(250)' in source


def test_fechar_ssh_com_erro_preserva_diagnostico(monkeypatch):
    hook=MagicMock();hook.get_first.return_value=None
    monkeypatch.setattr(runtime,'MsSqlHook',lambda **kw:hook)
    p={'pipeline':'P','run_id':'R','validadores':{'V':cfg()},'catalogo':[]}
    monkeypatch.setattr(runtime.ps,'carregar',lambda *a:p)
    sh=MagicMock();sh.get_conn.return_value.close.side_effect=OSError('segredo')
    import types
    mod=types.ModuleType('airflow.providers.ssh.hooks.ssh');mod.SSHHook=lambda **kw:sh
    monkeypatch.setitem(sys.modules,mod.__name__,mod)
    from utils import valida_arquivo_io as remote
    monkeypatch.setattr(remote,'avaliar',lambda *a:{'falhou':False})
    salvar=MagicMock(return_value={'falhou':False});monkeypatch.setattr(runtime.registro,'registrar',salvar)
    runtime.avaliar_no('V','P','SQL',run_id='R',ti=SimpleNamespace(try_number=1,start_date=datetime.now(timezone.utc)))
    salvar.assert_called_once()


def test_ramos_de_decisao_pulada_tem_guarda_mesmo_sem_destino_explicito(factory):
    js=jobs('decisao');js[1]['condition_json']=json.dumps({'tipo':'linhas_job','job':'V','ramo_verdadeiro':['B'],'ramo_falso':['C']})
    js.extend([_job('X','shell',1),_job('B','shell',3,depends='X'),_job('C','aguarde',3,depends='X')])
    src=factory._generate_dag_source(_pipeline(),js);tree=ast.parse(src)
    for tid in ('log_start_B','B','C'):
        matches=[{k.arg:k.value for k in n.keywords} for n in ast.walk(tree) if isinstance(n,ast.Call) and any(k.arg=='task_id' and isinstance(k.value,ast.Constant) and k.value.value==tid for k in n.keywords)]
        assert matches[0]['pre_execute'].id=='_guarda_valida'
    assert 't_wait_C = PythonOperator(' in src
