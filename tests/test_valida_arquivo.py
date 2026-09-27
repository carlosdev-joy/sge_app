"""Contrato F3: decisões, caminhos, grafo, contagem, timeout e limites."""
import copy
import errno
import io
from pathlib import Path
import stat
import sys
from unittest.mock import MagicMock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dags'))
from services import valida_arquivo as va
from services import valida_arquivo_store as store
from utils import valida_arquivo_io as remote


def entrada(**kw):
    return dict(dict(entrada_id='00000000-0000-0000-0000-000000000001',tipo='arquivo',arquivo='Arquivo.CSV',
                     diretorio_literal='/dados',param_name=None,alvo='D',se_nao_existe='pular',se_zero_linhas='pular',ignorar_cabecalho=False),**kw)


def config(**kw):return dict(dict(ssh_conn_id='SSH',entradas=[entrada()]),**kw)


def jobs():return [dict(job_name=n,job_type=t,depends_on_jobs=d) for n,t,d in [('V','valida_arquivo',[]),('D','datastage',['V']),('PY','python',['D']),('R','http',['V']),('J','email',['PY','R'])]]


def test_anti_drift():
    root=Path(__file__).resolve().parents[1]
    assert (root/'api/services/valida_arquivo.py').read_bytes()==(root/'dags/utils/valida_arquivo.py').read_bytes()


@pytest.mark.parametrize('estado,politica,esperado', [('ausente','pular','pular'),('ausente','falhar','bloquear'),('vazio','pular','pular'),('vazio','falhar','bloquear'),('vazio','executar','liberar'),('dados','pular','liberar'),('erro_tecnico','pular','bloquear')])
def test_politicas(estado,politica,esperado):
    e=entrada(se_nao_existe=politica,se_zero_linhas=politica)
    r=va.decidir(e,estado,1 if estado=='dados' else 0 if estado=='vazio' else None)
    assert r['decisao']==esperado


def test_erro_bloqueia_todos_destinos_pular_combina_por_and():
    a=va.decidir(entrada(),'dados',1);b=va.decidir(entrada(),'ausente')
    assert va.combinar([a,b])=={'D':'pular'}
    c=va.decidir(entrada(alvo='X'),'erro_tecnico')
    assert va.combinar([a,c])=={'D':'bloquear','X':'bloquear'}


@pytest.mark.parametrize('typ',sorted(va.TIPOS_ALVO))
def test_todos_tipos_sao_destinos(typ):
    graph=jobs();graph[1]['job_type']=typ
    out=va.impacto(va.normalizar(config(),[]),graph,'V',[])
    assert out['entradas'][0]['dependentes_transitivos']==['J','PY']
    assert out['entradas'][0]['convergencias']==['J']
    assert out['entradas'][0]['caminho']=='/dados/Arquivo.CSV'


@pytest.mark.parametrize('change',[{'diretorio_literal':'../etc'},{'arquivo':'../nome'},{'arquivo':'x\n.csv'},{'tipo':'binary'},{'tipo':'dataset','ignorar_cabecalho':True},{'se_nao_existe':'executar'},{'ignorar_cabecalho':1},{'entrada_id':'no'}])
def test_config_invalida(change):
    with pytest.raises(ValueError):va.normalizar(config(entradas=[entrada(**change)]),[])


def test_literal_vence_referencia_sem_vazar_segredo():
    assert va.diretorio(entrada(param_name='segredo'),[])=='/dados'
    with pytest.raises(ValueError,match='sem segredo'):
        va.diretorio(entrada(diretorio_literal='',param_name='segredo'),[dict(param_name='segredo',param_type='Encrypted',param_source='fixo',param_value='secret')])


@pytest.mark.parametrize('graph',[[],[dict(job_name='V',job_type='valida_arquivo',depends_on_jobs=['V'])],jobs()+[dict(job_name='V')]])
def test_grafo_invalido(graph):
    with pytest.raises(ValueError):va.impacto(va.normalizar(config(),[]),graph,'V',[])


class Sftp:
    def __init__(self,data=b'',error=None):self.data=data;self.error=error
    def get_channel(self):return MagicMock()
    def stat(self,path):
        if self.error:raise self.error
        return type('Info',(),{'st_mode':stat.S_IFREG,'st_size':len(self.data)})()
    def open(self,*a):return io.BytesIO(self.data)
    def close(self):pass


@pytest.mark.parametrize('data,header,fisicas,linhas',[(b'',False,0,0),(b'h',True,1,0),(b'h\n',True,1,0),(b'h\na',True,2,1),(b'a\nb',False,2,2),(b'a\nb\n',False,2,2),(b'\n',False,1,1)])
def test_linhas_cabecalho_e_final_sem_newline(data,header,fisicas,linhas):
    ssh=MagicMock();ssh.open_sftp.return_value=Sftp(data)
    e=entrada(ignorar_cabecalho=header)
    out=remote.avaliar_entrada(e,[],ssh,{},60)
    assert out['linhas']==linhas and out['linhas_fisicas']==fisicas


@pytest.mark.parametrize('err,estado',[(errno.ENOENT,'ausente'),(errno.EACCES,'erro_tecnico'),(errno.EIO,'erro_tecnico')])
def test_so_enoent_significa_ausencia(err,estado):
    ssh=MagicMock();ssh.open_sftp.return_value=Sftp(error=OSError(err,'erro privado'))
    out=remote.avaliar(config(timeout_segundos=60),[],ssh,{})
    assert out['entradas'][0]['estado']==estado
    assert 'privado' not in str(out)


def test_falha_interrompe_sem_liberar_outros():
    ssh=MagicMock();ssh.open_sftp.side_effect=RuntimeError('senha privada')
    cfg=config(timeout_segundos=60,entradas=[entrada(),entrada(entrada_id='00000000-0000-0000-0000-000000000002',alvo='X')])
    result=remote.avaliar(cfg,[],ssh,{})
    assert result['falhou'] and result['destinos']=={'D':'bloquear','X':'bloquear'}
    assert [r['estado'] for r in result['entradas']]==['erro_tecnico','nao_avaliado']
    assert 'privada' not in str(result)


def test_binario_limite_e_timeout_falham(monkeypatch):
    with pytest.raises(remote.ErroTecnico):remote.contar_texto(Sftp(b'\0'),'p')
    with pytest.raises(remote.ErroTecnico):remote.contar_texto(Sftp(b'abc'),'p',max_bytes=2)
    ticks=iter([0,61]);monkeypatch.setattr(remote.time,'monotonic',lambda:next(ticks))
    with pytest.raises(remote.ErroTecnico):remote.contar_texto(Sftp(b'a'),'p',timeout=60)


@pytest.mark.parametrize('raw',['partition 0: 50 records','Total records: abc','Total records: 1\nTotal records: 2','ERROR 0 rows','Total records: -1','Total records: 9223372036854775808',''])
def test_parser_dataset_nunca_chuta(raw):
    with pytest.raises(ValueError):va.parse_dataset(raw)


def test_parser_dataset_contrato_explicito():
    assert va.parse_dataset('partition 0\nTotal records: 42\nbytes 900')==42
    assert va.parse_dataset('Total rows = 0')==0


def test_comando_escapa_path_preserva_caixa():
    import shlex
    cmd=remote.comando_dataset("/dados/X'$(touch x).DS",{'valida_dsenv':'/opt/ds/dsenv','valida_orchadmin':'/opt/px/bin/orchadmin'})
    assert shlex.split(cmd)[-1]=="/dados/X'$(touch x).DS"
    assert 'describe -d -l' in cmd


def test_concorrencia_recusa_antes_de_mutar(monkeypatch):
    cur=MagicMock();monkeypatch.setattr(store,'ler',lambda *a,**k:dict(revisao=5))
    with pytest.raises(store.Conflito):store.salvar(cur,'P','V',config(),4)
    cur.execute.assert_not_called()

@pytest.fixture
def cliente(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import jobs as router
    from deps import get_current_user,PERM_EDITAR
    app=FastAPI();app.include_router(router.router)
    user={'permissoes':[PERM_EDITAR]}
    app.dependency_overrides[get_current_user]=lambda:user
    conn=MagicMock();monkeypatch.setattr(router,'get_db_conn',lambda:conn)
    monkeypatch.setattr(store,'disponivel',lambda c:True)
    monkeypatch.setattr(router,'_contexto_valida',lambda *a:('P',jobs(),[]))
    with TestClient(app) as c:yield c,conn,user


def test_api_previa_nao_grava_e_reflete_cenarios(cliente):
    c,conn,_=cliente
    r=c.post('/pipelines/P/valida-arquivo/V/previa',json={'config':config()})
    assert r.status_code==200
    assert r.json()['entradas'][0]['cenarios']['erro_tecnico']=='bloquear'
    conn.commit.assert_not_called()


def test_api_save_revisao_conflict_sem_commit(cliente,monkeypatch):
    c,conn,_=cliente
    def conflito(*a):raise store.Conflito('Recarregue')
    monkeypatch.setattr(store,'salvar',conflito)
    r=c.put('/pipelines/P/valida-arquivo/V',json={'config':config(),'revisao':0})
    assert r.status_code==409
    conn.commit.assert_not_called();conn.rollback.assert_called_once()


def test_api_ausencia_migration_informa_503(cliente,monkeypatch):
    c,_,_=cliente;monkeypatch.setattr(store,'disponivel',lambda c:False)
    r=c.post('/pipelines/P/valida-arquivo/V/previa',json={'config':config()})
    assert r.status_code==503 and '131' in str(r.json())


@pytest.mark.parametrize('method,suffix',[('get',''),('put',''),('post','/previa')])
def test_sem_permissao_nem_acessa_banco(cliente,method,suffix):
    c,conn,user=cliente;user['permissoes']=[]
    r=getattr(c,method)('/pipelines/P/valida-arquivo/V'+suffix)
    assert r.status_code==403
    conn.cursor.assert_not_called()


def test_convergencia_no_proprio_alvo():
    graph=jobs();graph[1]['depends_on_jobs']=['V','R']
    r=va.impacto(va.normalizar(config(),[]),graph,'V',[])
    assert r['entradas'][0]['convergencias']==['D','J']


@pytest.mark.parametrize('cond',[{'ramo_verdadeiro':['D']},{'casos':[{'ramo':['D']}]}])
def test_ramo_decisao_e_aresta_de_impacto(cond):
    graph=[dict(job_name='V',job_type='valida_arquivo'),dict(job_name='C',job_type='decisao',depends_on_jobs=['V'],condition=cond),dict(job_name='D',job_type='python')]
    r=va.impacto(va.normalizar(config(),[]),graph,'V',[])
    assert r['entradas'][0]['alvo']=='D'
    r=va.impacto(va.normalizar(config(entradas=[entrada(alvo='C')]),[]),graph,'V',[])
    assert r['entradas'][0]['dependentes_transitivos']==['D']


@pytest.mark.parametrize('typ',[[],{}])
def test_tipo_malformado_retorna_422(cliente,typ):
    c,_,_=cliente;graph=jobs();graph[1]['job_type']=typ
    assert c.post('/pipelines/P/valida-arquivo/V/previa',json={'config':config(),'nodes':graph}).status_code==422


@pytest.mark.parametrize('phase',['exec','sftp'])
def test_timeout_cobre_negociacao_exec_e_sftp(phase):
    import threading,time
    released=threading.Event()
    ssh=MagicMock();ssh.close.side_effect=released.set
    def bloqueio(*a,**k):
        assert released.wait(2),'negociação não foi interrompida'
        raise OSError('fechado')
    if phase=='exec':ssh.get_transport.return_value.open_session.return_value.exec_command.side_effect=bloqueio
    else:ssh.open_sftp.side_effect=bloqueio
    start=time.monotonic()
    with pytest.raises((remote.ErroTecnico,OSError)):
        if phase=='exec':remote.executar_limitado(ssh,'comando fixo',.05)
        else:remote.avaliar_entrada(entrada(),[],ssh,{},.05)
    assert time.monotonic()-start<1
    ssh.close.assert_called()
