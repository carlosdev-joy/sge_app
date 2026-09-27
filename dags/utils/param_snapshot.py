"""Snapshot cifrado de parâmetros antes dos consumidores; nunca retorna por XCom."""
import json
import os
from datetime import datetime
from cryptography.fernet import Fernet

ERRO = 'Configuração original de parâmetros indisponível. Preserve esta falha e inicie uma nova execução.'


def _cipher():
    try:
        return Fernet(os.environ['ORQUESTRA_CONN_KEY'].strip().encode())
    except Exception:
        raise ValueError('ORQUESTRA_CONN_KEY inválida para o snapshot de parâmetros.') from None


def _chave(pipeline, run_id):
    if not pipeline or not run_id or len(pipeline.encode('utf-16-le')) > 400 or len(run_id.encode('utf-16-le')) > 500:
        raise ValueError('Identificação da execução fora dos limites do snapshot.')


def _lista(cur, sql, args):
    cur.execute(sql, args)
    return [dict(zip([c[0] for c in cur.description], row)) for row in cur.fetchall()]


def capturar(hook, pipeline, run_id, primeira_tentativa=True, estrutura_esperada=None, projeto_esperado=None, ssh_esperado=None, validadores_esperados=None):
    """Uma transação serializa inicializações e copia catálogo/configuração completos."""
    _chave(pipeline, run_id)
    cipher = _cipher()
    conn = hook.get_conn()
    cur = conn.cursor()
    try:
        cur.execute('SELECT payload_cifrado FROM dbo.etl_parametro_snapshot WITH (UPDLOCK,HOLDLOCK) WHERE pipeline_name=%s AND run_id=%s',
                    (pipeline, run_id))
        row = cur.fetchone()
        if row:
            original = json.loads(cipher.decrypt(row[0].encode()))
            if estrutura_esperada is not None and (estrutura(original['jobs']) != estrutura_esperada or original.get('project') != projeto_esperado or (ssh_esperado is not None and original.get('pipeline_ssh', 'ssh_lnxprd021') != ssh_esperado)):
                raise ValueError(ERRO)
            if validadores_esperados is not None:
                from utils.valida_arquivo import estrutura_validadores
                if estrutura_validadores(original.get('validadores') or {}) != validadores_esperados:
                    raise ValueError(ERRO)
            conn.commit()
            return
        if not primeira_tentativa:
            raise ValueError(ERRO)
        catalogo = _lista(cur, 'SELECT * FROM dbo.etl_pipeline_param WITH (HOLDLOCK) WHERE pipeline_name=%s', (pipeline,))
        jobs = _lista(cur, 'SELECT * FROM dbo.etl_pipeline_job WITH (HOLDLOCK) WHERE pipeline_name=%s', (pipeline,))
        etapa = _lista(cur, 'SELECT * FROM dbo.etl_pipeline_job_param WITH (HOLDLOCK) WHERE pipeline_name=%s', (pipeline,))
        overrides = _lista(cur, 'SELECT job_name, param_name, param_value FROM dbo.etl_job_param_override WITH (HOLDLOCK) WHERE pipeline_name=%s AND dag_run_id=%s', (pipeline, run_id))
        cur.execute('SELECT project_name FROM dbo.etl_pipeline WITH (HOLDLOCK) WHERE pipeline_name=%s', (pipeline,))
        project_row=cur.fetchone()
        project = project_row[0] if project_row else None
        pipeline_ssh = ssh_esperado or 'ssh_lnxprd021'
        if estrutura_esperada is not None and (estrutura(jobs) != estrutura_esperada or project != projeto_esperado):
            raise ValueError('Estrutura mudou; publique a DAG antes de iniciar nova execução.')
        validadores,politica = configuracoes_validacao(cur,pipeline,jobs,catalogo)
        if validadores_esperados is not None:
            from utils.valida_arquivo import estrutura_validadores
            if estrutura_validadores(validadores) != validadores_esperados:
                raise ValueError(ERRO)
        payload = dict(validadores=validadores, politica_sem_movimento=politica, project=project, pipeline_ssh=pipeline_ssh, versao=1, pipeline=pipeline, run_id=run_id, catalogo=catalogo,
                       jobs=jobs, etapa=etapa, overrides=overrides, data_execucao=datetime.now().date().isoformat())
        token = cipher.encrypt(json.dumps(payload, ensure_ascii=False, default=str).encode()).decode()
        cur.execute('INSERT INTO dbo.etl_parametro_snapshot (pipeline_name,run_id,payload_cifrado) VALUES (%s,%s,%s)',
                    (pipeline, run_id, token))
        conn.commit()
    except Exception:
        conn.rollback()
        raise ValueError(ERRO) from None
    finally:
        cur.close()
        conn.close()


def carregar(hook, pipeline, run_id):
    _chave(pipeline, run_id)
    try:
        row = hook.get_first('SELECT payload_cifrado FROM dbo.etl_parametro_snapshot WHERE pipeline_name=%s AND run_id=%s',
                             parameters=(pipeline, run_id))
        if not row:
            raise ValueError(ERRO)
        payload = json.loads(_cipher().decrypt(row[0].encode()))
        if payload['versao'] != 1 or payload['pipeline'] != pipeline or payload['run_id'] != run_id:
            raise ValueError(ERRO)
        return payload
    except Exception:
        raise ValueError(ERRO) from None


def etapa_ds(payload, job):
    """Referência é default local; um valor direto da etapa sempre prevalece."""
    catalogo = {p['param_name']: p for p in payload['catalogo']}
    cfg = next((j for j in payload['jobs'] if j['job_name'] == job), None)
    if cfg is None:
        raise ValueError(ERRO)
    refs = json.loads(cfg.get('param_vinculos_json') or '{}')
    locais = [p for p in payload['etapa'] if p['job_name'] == job]
    nomes = {p['param_name'] for p in locais}
    for alvo, fonte in refs.items():
        if alvo in nomes:
            continue
        if fonte not in catalogo or catalogo[fonte].get('param_destino') != 'datastage':
            raise ValueError('Referência ausente na configuração original.')
        locais.append(dict(catalogo[fonte], param_name=alvo))
    defaults = [p for p in payload['catalogo'] if p.get('param_destino') == 'datastage']
    overrides = [p for p in payload['overrides'] if p['job_name'] == job]
    return locais, defaults, overrides


def python_config(payload, job):
    cfg = next((j for j in payload['jobs'] if j['job_name'] == job), None)
    if cfg is None:
        raise ValueError(ERRO)
    py = json.loads(cfg.get('python_json') or '{}')
    refs = json.loads(cfg.get('param_vinculos_json') or '{}')
    catalogo = {p['param_name']: p for p in payload['catalogo']}
    for campo, fonte in refs.items():
        if campo not in ('script_path', 'destino_dir'):
            raise ValueError('Campo Python não permitido.')
        if py.get(campo):
            continue
        p = catalogo.get(fonte)
        if not p or p.get('param_type') not in ('String', 'Pathname') or p.get('param_source') != 'fixo':
            raise ValueError('Referência de caminho Python inválida.')
        py[campo] = p.get('param_value')
    return py


def estrutura(jobs):
    result=[]
    for j in jobs:
        py=json.loads(j.get('python_json') or '{}')
        result.append([j['job_name'], j.get('job_type') or 'datastage',
                       j.get('execution_order'), j.get('depends_on_jobs') or '',
                       j.get('ssh_conn_id') or '', j.get('condition_json') or '',
                       py.get('modo') or 'modulo'])
    return sorted(result, key=lambda j: j[0])



def validar_publicacao(hook, pipeline, projeto, jobs, validadores=None):
    rows = hook.get_records("""SELECT s.payload_cifrado FROM dbo.etl_parametro_snapshot s
        WHERE s.pipeline_name=%s AND NOT EXISTS (
          SELECT 1 FROM dbo.etl_pipeline_execucao e
          WHERE e.pipeline_name COLLATE Latin1_General_BIN2=s.pipeline_name AND e.run_id COLLATE Latin1_General_BIN2=s.run_id
          AND e.status IN ('SUCESSO','PULADO','CANCELADO'))""", parameters=(pipeline,))
    atual = estrutura(jobs)
    for row in rows:
        try:
            p=json.loads(_cipher().decrypt(row[0].encode()))
            from utils.valida_arquivo import estrutura_validadores
            igual=(p.get('project')==projeto and estrutura(p['jobs'])==atual
                   and estrutura_validadores(p.get('validadores') or {})==estrutura_validadores(validadores or {}))
        except Exception:
            raise ValueError('Configuração original ilegível; publicação bloqueada.') from None
        if not igual:
            raise ValueError('Publicação incompatível com corrida retomável. Conclua/cancele a corrida ou use outro pipeline.')


def validar_servidor(payload, job, tipo, ssh, projeto=None):
    cfg = next((j for j in payload['jobs'] if j['job_name'] == job), None)
    if cfg is None or (cfg.get('job_type') or 'datastage') != tipo:
        raise ValueError(ERRO)
    # DataStage usa a conexão do pipeline gerado; o campo SSH do job é ignorado pela fábrica legada.
    original_ssh = payload.get('pipeline_ssh', 'ssh_lnxprd021') if tipo == 'datastage' else (cfg.get('ssh_conn_id') or 'ssh_lnxprd021')
    if original_ssh != ssh or (projeto is not None and payload.get('project') != projeto):
        raise ValueError('Servidor/projeto diferente da configuração original; nenhum comando executado.')


def configuracoes_validacao(cur,pipeline,jobs,catalogo):
    nomes={j['job_name'] for j in jobs if j.get('job_type')=='valida_arquivo'}
    if not nomes:return {},{}
    from utils.valida_arquivo import normalizar
    headers=_lista(cur,'SELECT * FROM dbo.etl_valida_arquivo_no WITH (HOLDLOCK) WHERE pipeline_name=%s',(pipeline,))
    entradas=_lista(cur,'SELECT * FROM dbo.etl_valida_arquivo_config WITH (HOLDLOCK) WHERE pipeline_name=%s ORDER BY ordem',(pipeline,))
    cfgs={}
    for h in headers:
        nome=h['task_id']
        if nome not in nomes:continue
        rows=[]
        for e in entradas:
            if e['task_id']==nome:
                e=dict(e,entrada_id=str(e['entrada_id']),ignorar_cabecalho=bool(e['ignorar_cabecalho']))
                rows.append(e)
        cfg=normalizar(dict(h,entradas=rows),catalogo)
        cfg['revisao']=h['revisao'];cfgs[nome]=cfg
    if set(cfgs)!=nomes:raise ValueError('Validador sem configuração original.')
    cur.execute('SELECT liberar_dependentes_sem_movimento,notificar_sem_movimento,politica_sem_movimento_revisao FROM dbo.etl_pipeline WITH (HOLDLOCK) WHERE pipeline_name=%s',(pipeline,))
    p=cur.fetchone()
    if p is None:raise ValueError(ERRO)
    return cfgs,dict(liberar_dependentes=bool(p[0]),notificar=bool(p[1]),revisao=p[2])
