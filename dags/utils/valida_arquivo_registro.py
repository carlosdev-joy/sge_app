"""Resultado durável; nunca usar XCom como fonte exclusiva ou liberar após falha de escrita."""
import json
from utils import valida_arquivo as va

ERRO='Diagnóstico original da validação indisponível; destinos não podem ser liberados.'


def config_original(payload,no):
    config=(payload.get('validadores') or {}).get(no)
    if not config or not config.get('entradas') or type(config.get('revisao')) is not int or config['revisao']<1:
        raise ValueError(ERRO)
    return config


def canonicalizar(config,resultado):
    if not isinstance(resultado,dict) or not isinstance(resultado.get('entradas'),list):raise ValueError(ERRO)
    recebidos=resultado['entradas'];originais=config['entradas']
    if len(recebidos)!=len(originais):raise ValueError(ERRO)
    itens=[];erro=False
    for entrada,r in zip(originais,recebidos):
        if not isinstance(r,dict) or r.get('entrada_id')!=entrada['entrada_id']:raise ValueError(ERRO)
        estado=r.get('estado');linhas=r.get('linhas');fisicas=r.get('linhas_fisicas')
        if estado=='nao_avaliado' and not erro:raise ValueError(ERRO)
        if erro and estado!='nao_avaliado':raise ValueError(ERRO)
        if estado in ('dados','vazio') and entrada['tipo']=='arquivo':
            if type(fisicas) is not int or fisicas<0 or fisicas>va.MAX_CONTAGEM:raise ValueError(ERRO)
            if linhas!=max(0,fisicas-int(entrada['ignorar_cabecalho'])):raise ValueError(ERRO)
        elif fisicas is not None:raise ValueError(ERRO)
        item=va.decidir(entrada,estado,linhas,fisicas)
        itens.append(item);erro=erro or estado=='erro_tecnico'
    return dict(entradas=itens,destinos=va.combinar(itens),falhou=any(r['decisao']=='bloquear' for r in itens))


def registrar(hook,payload,no,tentativa,resultado):
    from utils.param_snapshot import _chave
    _chave(payload['pipeline'],payload['run_id'])
    if type(tentativa) is not int or tentativa<1:raise ValueError(ERRO)
    config=config_original(payload,no);resultado=canonicalizar(config,resultado)
    conn=hook.get_conn();cur=conn.cursor()
    try:
        cur.execute('SELECT revisao,resultado_json FROM dbo.etl_valida_arquivo_tentativa WITH (UPDLOCK,HOLDLOCK) WHERE pipeline_name=%s AND run_id=%s AND task_id=%s AND tentativa=%s',
                    (payload['pipeline'],payload['run_id'],no,tentativa))
        old=cur.fetchone()
        if old:
            if old[0]!=config['revisao']:raise ValueError(ERRO)
            salvo=canonicalizar(config,json.loads(old[1]));conn.commit();return salvo
        cur.execute('INSERT dbo.etl_valida_arquivo_tentativa(pipeline_name,run_id,task_id,tentativa,revisao,resultado_json) OUTPUT INSERTED.id VALUES(%s,%s,%s,%s,%s,%s)',
                    (payload['pipeline'],payload['run_id'],no,tentativa,config['revisao'],json.dumps(resultado,ensure_ascii=False)))
        ident=cur.fetchone()[0]
        for r in resultado['entradas']:
            cur.execute('INSERT dbo.etl_valida_arquivo_resultado(tentativa_id,entrada_id,alvo,estado,linhas,linhas_fisicas,decisao,motivo) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                        (ident,r['entrada_id'],r['alvo'],r['estado'],r['linhas'],r['linhas_fisicas'],r['decisao'],r['motivo']))
        conn.commit();return resultado
    except Exception:
        conn.rollback();raise ValueError('Não foi possível persistir o diagnóstico da validação; nenhum destino liberado.') from None
    finally:cur.close();conn.close()


def ler_tentativa(hook,payload,no,tentativa):
    config=config_original(payload,no)
    row=hook.get_first('SELECT revisao,resultado_json FROM dbo.etl_valida_arquivo_tentativa WHERE pipeline_name=%s AND run_id=%s AND task_id=%s AND tentativa=%s',
                       parameters=(payload['pipeline'],payload['run_id'],no,tentativa))
    if not row or row[0]!=config['revisao']:raise ValueError(ERRO)
    return canonicalizar(config,json.loads(row[1]))
