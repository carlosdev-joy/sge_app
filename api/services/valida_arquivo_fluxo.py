"""Reconciliação de validadores na mesma transação do canvas (sem commit próprio)."""
from services import valida_arquivo as va
from services import valida_arquivo_store as store
from services import valida_arquivo_execucao as historico
from services import pipeline_params as pp


class Indisponivel(ValueError):
    pass


def runtime_disponivel(cur):
    if not store.disponivel(cur) or not historico.disponivel(cur):
        return False
    cur.execute("SELECT CASE WHEN OBJECT_ID('dbo.etl_valida_arquivo_guarda','U') IS NOT NULL THEN 1 ELSE 0 END")
    row = cur.fetchone()
    return bool(row and row[0])


def preparar(cur, pipeline, nodes, deleted):
    nodes = [{**n, 'job_name': n['job_name'].strip(),
              **({'job_type': (n['job_type'] or 'datastage').strip().lower()} if 'job_type' in n else {})} for n in nodes]
    solicitados = any(n.get('job_type') == 'valida_arquivo' for n in nodes)
    if not store.disponivel(cur):
        if solicitados:
            raise Indisponivel(store.MIGRATION)
        return None
    # A trava mantém a configuração e a topologia coerentes até o commit.
    cur.execute('SELECT job_name,job_type,depends_on_jobs,condition_json FROM dbo.etl_pipeline_job WITH (UPDLOCK,HOLDLOCK) WHERE pipeline_name=?', (pipeline,))
    existentes = {r[0]: dict(zip(('job_name', 'job_type', 'depends_on_jobs', 'condition_json'), r)) for r in cur.fetchall()}
    if not solicitados and not any(n['job_type'] == 'valida_arquivo' for n in existentes.values()):
        return None
    if not runtime_disponivel(cur):
        raise Indisponivel('Aplique as migrations 130 a 133 antes de usar Valida Arquivo.')
    nomes_ci = {nome.casefold(): nome for nome in existentes}
    for n in nodes:
        oficial = nomes_ci.get(n['job_name'].casefold())
        if oficial and oficial != n['job_name']:
            raise ValueError('Use a grafia cadastrada do nó: ' + oficial)
    catalogo = pp.ler(cur, pipeline)
    recebidos = {n['job_name']: n for n in nodes}
    removidos = set(deleted) - set(recebidos)
    finais = {nome: n.copy() for nome, n in existentes.items() if nome not in removidos}
    for nome, n in recebidos.items():
        if nome in existentes and 'job_type' in n and n['job_type'] != existentes[nome]['job_type']:
            raise ValueError('Não é possível trocar o tipo de um nó existente: ' + nome)
        finais[nome] = {'job_type': 'datastage', **finais.get(nome, {}), **n}
    configs = {}
    for nome, n in finais.items():
        if n['job_type'] != 'valida_arquivo':
            if 'valida_arquivo' in n:
                raise ValueError('Configuração Valida Arquivo em nó de outro tipo.')
            continue
        old = store.ler(cur, pipeline, nome, lock=True)
        raw = recebidos.get(nome, {}).get('valida_arquivo', old)
        if raw is None:
            raise ValueError('Configure o nó Valida Arquivo: ' + nome)
        revisao = raw.get('revisao', 0) if isinstance(raw, dict) else None
        if type(revisao) is not int or revisao != (old['revisao'] if old else 0):
            raise store.Conflito('Configuração alterada por outra pessoa. Recarregue antes de salvar: ' + nome)
        config = va.normalizar(raw, catalogo)
        va.impacto(config, list(finais.values()), nome, catalogo)
        configs[nome] = dict(config=config, revisao=revisao, old=old,
                             escrever='valida_arquivo' in recebidos.get(nome, {}) or old is None)
    return dict(configs=configs, removidos=removidos, antigos=existentes)


def antes_de_excluir(cur, pipeline, plano):
    if plano is None:
        return
    # Retira FKs antes de excluir alvos; a configuração já foi validada. Qualquer
    # falha posterior desfaz TUDO, inclusive estas exclusões.
    for nome in plano['removidos']:
        if plano['antigos'].get(nome, {}).get('job_type') == 'valida_arquivo':
            cur.execute('DELETE FROM dbo.etl_valida_arquivo_config WHERE pipeline_name=? AND task_id=?', (pipeline, nome))
            cur.execute('DELETE FROM dbo.etl_valida_arquivo_no WHERE pipeline_name=? AND task_id=?', (pipeline, nome))
    for nome, item in plano['configs'].items():
        if item['old'] and any(e['alvo'] in plano['removidos'] for e in item['old']['entradas']):
            cur.execute('DELETE FROM dbo.etl_valida_arquivo_config WHERE pipeline_name=? AND task_id=?', (pipeline, nome))


def aplicar(cur, pipeline, plano):
    if plano is None:
        return {}
    revisoes = {}
    for nome, item in plano['configs'].items():
        if item['escrever']:
            resultado = store.salvar(cur, pipeline, nome, item['config'], item['revisao'])
            resultado['exige_publicacao'] = store.estrutura(item['old']) != store.estrutura(item['config'])
            revisoes[nome] = resultado
    if plano['configs']:
        cur.execute('UPDATE dbo.etl_pipeline SET param_snapshot_ativo=1 WHERE pipeline_name=?', (pipeline,))
    return revisoes
