"""Persistência transacional do contrato Valida Arquivo; commit pertence ao caller."""
from services import valida_arquivo as va

MIGRATION='Aplique a migration 131 de configuração Valida Arquivo.'
CAMPOS=('entrada_id','ordem','tipo','param_name','diretorio_literal','arquivo','alvo','se_nao_existe','se_zero_linhas','ignorar_cabecalho')


class Conflito(ValueError):pass


def disponivel(cur):
    cur.execute("SELECT CASE WHEN OBJECT_ID('dbo.etl_valida_arquivo_no','U') IS NOT NULL AND OBJECT_ID('dbo.etl_valida_arquivo_config','U') IS NOT NULL THEN 1 ELSE 0 END")
    row=cur.fetchone()
    return bool(row and row[0])


def ler(cur,pipeline,no,lock=False):
    hint=' WITH (UPDLOCK,HOLDLOCK)' if lock else ''
    cur.execute('SELECT ssh_conn_id,timeout_segundos,revisao FROM dbo.etl_valida_arquivo_no'+hint+' WHERE pipeline_name=? AND task_id=?',(pipeline,no))
    head=cur.fetchone()
    if not head:return None
    cur.execute('SELECT '+','.join(CAMPOS)+' FROM dbo.etl_valida_arquivo_config'+hint+' WHERE pipeline_name=? AND task_id=? ORDER BY ordem',(pipeline,no))
    entries=[]
    for row in cur.fetchall():
        e=dict(zip(CAMPOS,row));e['entrada_id']=str(e['entrada_id']);e['ignorar_cabecalho']=bool(e['ignorar_cabecalho']);e['diretorio_literal']=e['diretorio_literal'] or ''
        entries.append(e)
    return dict(ssh_conn_id=head[0],timeout_segundos=head[1],revisao=head[2],entradas=entries)


def estrutura(config):
    if not config:return None
    return config['ssh_conn_id'], sorted((e['entrada_id'],e['alvo']) for e in config['entradas'])


def salvar(cur,pipeline,no,config,revisao):
    if type(revisao) is not int or revisao<0:raise ValueError('Informe a revisão esperada.')
    old=ler(cur,pipeline,no,lock=True)
    if (old['revisao'] if old else 0)!=revisao:
        raise Conflito('Configuração alterada por outra pessoa. Recarregue antes de salvar.')
    novo=revisao+1
    if old:
        cur.execute('UPDATE dbo.etl_valida_arquivo_no SET ssh_conn_id=?,timeout_segundos=?,revisao=?,atualizado_em=SYSUTCDATETIME() WHERE pipeline_name=? AND task_id=?',
                    (config['ssh_conn_id'],config['timeout_segundos'],novo,pipeline,no))
    else:
        cur.execute('INSERT dbo.etl_valida_arquivo_no(pipeline_name,task_id,ssh_conn_id,timeout_segundos,revisao) VALUES(?,?,?,?,?)',
                    (pipeline,no,config['ssh_conn_id'],config['timeout_segundos'],novo))
    cur.execute('DELETE FROM dbo.etl_valida_arquivo_config WHERE pipeline_name=? AND task_id=?',(pipeline,no))
    for e in config['entradas']:
        cur.execute('INSERT dbo.etl_valida_arquivo_config(pipeline_name,task_id,'+','.join(CAMPOS)+') VALUES('+','.join('?' for _ in range(12))+')',
                    (pipeline,no,*(e[k] for k in CAMPOS)))
    return dict(revisao=novo,exige_publicacao=estrutura(old)!=estrutura(config))


def ler_todos(cur,pipeline,jobs):
    nomes=[j['job_name'] for j in jobs if j.get('job_type')=='valida_arquivo']
    if not nomes:return {}
    if not disponivel(cur):raise ValueError(MIGRATION)
    out={}
    for nome in nomes:
        cfg=ler(cur,pipeline,nome)
        if not cfg:raise ValueError('Validador sem configuração: '+nome)
        out[nome]=cfg
    return out


def validar_catalogo(cur,pipeline,catalogo):
    if not disponivel(cur):return
    cur.execute("SELECT job_name,job_type FROM dbo.etl_pipeline_job WHERE pipeline_name=? AND job_type='valida_arquivo'",(pipeline,))
    jobs=[dict(job_name=r[0],job_type=r[1]) for r in cur.fetchall()]
    for cfg in ler_todos(cur,pipeline,jobs).values():va.normalizar(cfg,catalogo)
