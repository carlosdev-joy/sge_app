"""Leitura protegida de configuração original e guarda de alterações estruturais."""
import json
from services.conn_crypto import decrypt_password

ERRO = 'Esta corrida exige sua configuração original. Para usar alterações, preserve a falha e inicie uma nova execução.'


def ativo(cur, pipeline):
    cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline','param_snapshot_ativo')")
    row=cur.fetchone()
    if not row or row[0] is None:
        return False
    cur.execute('SELECT param_snapshot_ativo FROM dbo.etl_pipeline WHERE pipeline_name=?', (pipeline,))
    row=cur.fetchone()
    return bool(row and row[0])


def original(cur, pipeline, run):
    if not ativo(cur,pipeline):
        return None
    cur.execute('SELECT payload_cifrado FROM dbo.etl_parametro_snapshot WHERE pipeline_name=? AND run_id=?',(pipeline,run))
    row=cur.fetchone()
    if not row:
        raise ValueError(ERRO)
    try:
        p=json.loads(decrypt_password(row[0]))
        if p['pipeline'] != pipeline or p['run_id'] != run or p['versao'] != 1:
            raise ValueError(ERRO)
        return p
    except Exception:
        raise ValueError(ERRO) from None


def estrutura(jobs):
    result=[]
    for j in jobs:
        py=json.loads(j.get('python_json') or '{}')
        result.append([j['job_name'], j.get('job_type') or 'datastage',
                       j.get('execution_order'), j.get('depends_on_jobs') or '',
                       j.get('ssh_conn_id') or '', j.get('condition_json') or '',
                       py.get('modo') or 'modulo'])
    return sorted(result, key=lambda j: j[0])


def validar_estrutura(cur, pipeline):
    if not ativo(cur,pipeline):
        return
    cur.execute("""SELECT s.payload_cifrado FROM dbo.etl_parametro_snapshot s
        WHERE s.pipeline_name=? AND NOT EXISTS (
          SELECT 1 FROM dbo.etl_pipeline_execucao e
          WHERE e.pipeline_name COLLATE Latin1_General_BIN2=s.pipeline_name AND e.run_id COLLATE Latin1_General_BIN2=s.run_id
          AND e.status IN ('SUCESSO','PULADO','CANCELADO'))""", (pipeline,))
    tokens=[r[0] for r in cur.fetchall()]
    if not tokens:
        return
    cur.execute('SELECT * FROM dbo.etl_pipeline_job WHERE pipeline_name=?', (pipeline,))
    cols=[c[0] for c in cur.description]
    atual=estrutura([dict(zip(cols,r)) for r in cur.fetchall()])
    cur.execute('SELECT project_name FROM dbo.etl_pipeline WHERE pipeline_name=?',(pipeline,))
    row=cur.fetchone(); projeto=row[0] if row else None
    for token in tokens:
        try:
            p=json.loads(decrypt_password(token))
            igual=atual==estrutura(p['jobs']) and p.get('project')==projeto
        except Exception:
            raise ValueError('Não foi possível conferir a configuração original; alteração estrutural bloqueada.') from None
        if not igual:
            raise ValueError('Há uma corrida com configuração original ainda retomável. Conclua/cancele essa corrida ou use outro pipeline para alterar nós, dependências, modo Python ou servidor. Valores de parâmetros podem ser editados para novas execuções.')


def validar_retomada(cur, payload):
    cur.execute('SELECT * FROM dbo.etl_pipeline_job WHERE pipeline_name=?', (payload['pipeline'],))
    cols=[c[0] for c in cur.description]
    atual=estrutura([dict(zip(cols,r)) for r in cur.fetchall()])
    cur.execute('SELECT project_name FROM dbo.etl_pipeline WHERE pipeline_name=?',(payload['pipeline'],))
    row=cur.fetchone()
    if atual != estrutura(payload['jobs']) or (row[0] if row else None) != payload.get('project'):
        raise ValueError('Esta corrida tem estrutura ou servidor diferente do cadastro atual. Preserve seu histórico e inicie uma nova execução após publicar a DAG.')


def previa(p, etapas):
    cat={x['param_name']:x for x in p['catalogo']}
    saida=[]
    for j in p['jobs']:
        if j['job_name'] not in etapas or j['job_type'] not in ('datastage','python'):
            continue
        itens=[]
        if j['job_type']=='datastage':
            effective={n:dict(x,condicional=True) for n,x in cat.items() if x.get('param_destino')=='datastage'}
            for alvo,nome in json.loads(j.get('param_vinculos_json') or '{}').items():
                effective[alvo]=dict(cat[nome],param_name=alvo)
            effective.update({x['param_name']:x for x in p['etapa'] if x['job_name']==j['job_name']})
            for override in p['overrides']:
                if override['job_name']==j['job_name'] and override['param_name'] in effective:
                    effective[override['param_name']]=dict(effective[override['param_name']],param_source='fixo',param_value=override['param_value'])
            for x in effective.values():
                value='***' if x['param_type']=='Encrypted' else x.get('param_value') if x['param_source']=='fixo' else None
                itens.append(dict(param_name=x['param_name'],param_type=x['param_type'],param_source=x['param_source'],
                                  fonte='original',valor_efetivo=value,descricao='Configuração original desta corrida',editavel=False,
                                  condicional=bool(x.get('condicional'))))
        saida.append(dict(job_name=j['job_name'],original=True,itens=itens))
    return saida
