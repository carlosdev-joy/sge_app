"""F4: diagnóstico obrigatório, tentativa exata, configuração original e políticas."""
import copy
import json
from unittest.mock import MagicMock
import pytest
from tests.test_valida_arquivo import entrada,config,jobs
from services import valida_arquivo as va
from utils import valida_arquivo_registro as reg
from utils import param_snapshot as snap


def original():
    cfg=va.normalizar(config(),[]);cfg['revisao']=1
    return dict(pipeline='P',run_id='R',validadores={'V':cfg},politica_sem_movimento={'liberar_dependentes':False,'notificar':True,'revisao':0})


def resultado(estado='dados'):
    e=original()['validadores']['V']['entradas'][0]
    return {'entradas':[va.decidir(e,estado,3 if estado=='dados' else None,3 if estado=='dados' else None)]}


def test_canonicalizacao_nao_aceita_decisao_forjada():
    p=original();r=resultado('erro_tecnico');r['entradas'][0]['decisao']='liberar';r['entradas'][0]['motivo']='segredo externo'
    out=reg.canonicalizar(p['validadores']['V'],r)
    assert out['falhou'] and out['destinos']=={'D':'bloquear'}
    assert 'segredo' not in str(out)


@pytest.mark.parametrize('mutation',[lambda r:r.update(entradas=[]),lambda r:r['entradas'][0].update(entrada_id='outra'),lambda r:r['entradas'][0].update(linhas_fisicas=9),lambda r:r['entradas'][0].update(estado='nao_avaliado')])
def test_resultado_incompleto_ou_incompativel_falha(mutation):
    r=resultado();mutation(r)
    with pytest.raises(ValueError):reg.canonicalizar(original()['validadores']['V'],r)


def test_snapshot_nao_muda_na_canonicalizacao():
    p=original();before=copy.deepcopy(p);reg.canonicalizar(p['validadores']['V'],resultado())
    assert p==before


def test_falha_persistida_antes_de_propagar():
    hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.side_effect=[None,(7,)]
    out=reg.registrar(hook,original(),'V',1,resultado('erro_tecnico'))
    assert out['falhou']
    hook.get_conn.return_value.commit.assert_called_once()
    assert any('INSERT dbo.etl_valida_arquivo_resultado' in str(c) for c in cur.execute.call_args_list)


def test_erro_persistencia_faz_rollback_e_nao_libera():
    hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.side_effect=[None,(7,)]
    def sql(s,*a):
        if 'INSERT dbo.etl_valida_arquivo_resultado' in s:raise RuntimeError('privado')
    cur.execute.side_effect=sql
    with pytest.raises(ValueError,match='nenhum destino') as exc:reg.registrar(hook,original(),'V',1,resultado())
    assert 'privado' not in str(exc.value)
    hook.get_conn.return_value.rollback.assert_called_once();hook.get_conn.return_value.commit.assert_not_called()


def test_idempotencia_preserva_primeiro_resultado_da_tentativa():
    hook=MagicMock();cur=hook.get_conn.return_value.cursor.return_value
    cur.fetchone.return_value=(1,json.dumps(resultado('erro_tecnico')))
    out=reg.registrar(hook,original(),'V',1,resultado())
    assert out['falhou']
    assert cur.execute.call_count==1


def test_leitura_exige_tentativa_exata_e_revisao_original():
    hook=MagicMock();hook.get_first.return_value=None
    with pytest.raises(ValueError):reg.ler_tentativa(hook,original(),'V',2)
    assert hook.get_first.call_args.kwargs['parameters']==('P','R','V',2)
    hook.get_first.return_value=(2,json.dumps(resultado()))
    with pytest.raises(ValueError):reg.ler_tentativa(hook,original(),'V',2)


def test_manifesto_ignora_valor_mas_trava_destino_conexao_e_ids():
    a=original()['validadores'];b=copy.deepcopy(a)
    b['V']['entradas'][0].update(arquivo='novo.csv',se_zero_linhas='executar')
    assert va.estrutura_validadores(a)==va.estrutura_validadores(b)
    b['V']['entradas'][0]['alvo']='PY'
    assert va.estrutura_validadores(a)!=va.estrutura_validadores(b)


def test_captura_sem_validadores_nao_exige_schema_novo():
    cur=MagicMock()
    assert snap.configuracoes_validacao(cur,'P',[dict(job_name='D',job_type='datastage')],[])==({}, {})
    cur.execute.assert_not_called()


def test_historico_api_nao_expoe_catalogo_ou_codigo(monkeypatch):
    from services import valida_arquivo_execucao as ve
    p=original();p.update(catalogo=[{'param_value':'cipher'}],jobs=[{'python_json':'codigo privado'}])
    monkeypatch.setattr(ve.ps,'original',lambda *a:p)
    cur=MagicMock();cur.fetchall.return_value=[];cur.fetchone.return_value=None
    out=ve.ler(cur,'P','R')
    assert out['original'] and out['validadores']['V']['revisao']==1
    assert 'catalogo' not in out and 'jobs' not in out and 'privado' not in str(out)


@pytest.mark.parametrize('body',[{}, {'revisao':0,'liberar_dependentes':'true','notificar':False},{'revisao':True,'liberar_dependentes':True,'notificar':True}])
def test_politica_rejeita_tipos_ambiguos(body):
    from routers.pipelines import put_politica_sem_movimento
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:put_politica_sem_movimento('P',body,{})
    assert exc.value.status_code==422


def test_politica_concorrente_nao_commita(monkeypatch):
    from routers import pipelines as router
    from services import valida_arquivo_execucao as ve
    from fastapi import HTTPException
    conn=MagicMock();conn.cursor.return_value.rowcount=0
    monkeypatch.setattr(router,'get_db_conn',lambda:conn);monkeypatch.setattr(ve,'disponivel',lambda c:True)
    with pytest.raises(HTTPException) as exc:router.put_politica_sem_movimento('P',dict(revisao=0,liberar_dependentes=True,notificar=False),{})
    assert exc.value.status_code==409
    conn.commit.assert_not_called();conn.rollback.assert_called_once()
