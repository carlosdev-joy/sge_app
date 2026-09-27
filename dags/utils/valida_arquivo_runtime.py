"""Barreiras antes do executor: resultado durável e pais operacionais autorizam o trabalho."""
import json
from datetime import timezone
from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from utils import param_snapshot as ps, valida_arquivo as va, valida_arquivo_registro as registro

ERRO = 'Validação indisponível; execução bloqueada. Consulte o diagnóstico da corrida.'
TERMINAIS = {'success', 'skipped', 'failed', 'upstream_failed', 'removed'}


def identidade(ti):
    # Airflow 2.11 mantém try_number na coluna; não somar/subtrair após conclusão.
    n = ti.try_number
    inicio = ti.start_date
    if type(n) is not int or n < 1 or inicio is None:
        raise AirflowException(ERRO)
    return n, inicio.astimezone(timezone.utc).isoformat(timespec='microseconds')


def gravar_guarda(hook, payload, ti, decisao, origens):
    tentativa, inicio = identidade(ti)
    args = (payload['pipeline'], payload['run_id'], ti.task_id, tentativa)
    conn = hook.get_conn(); cur = conn.cursor()
    try:
        cur.execute('SELECT inicio_tentativa,decisao,origens_json FROM dbo.etl_valida_arquivo_guarda WITH (UPDLOCK,HOLDLOCK) WHERE pipeline_name=%s AND run_id=%s AND task_id=%s AND tentativa=%s', args)
        row = cur.fetchone()
        if row:
            # Reschedule preserva tentativa, mas o framework pode atualizar start_date.
            # Só sobrescrever após nova avaliação completa; nunca ler uma marca antiga como autorização.
            cur.execute('UPDATE dbo.etl_valida_arquivo_guarda SET inicio_tentativa=%s,decisao=%s,origens_json=%s,criado_em=SYSUTCDATETIME() WHERE pipeline_name=%s AND run_id=%s AND task_id=%s AND tentativa=%s',
                        (inicio, decisao, json.dumps(origens)) + args)
        else:
            cur.execute('INSERT dbo.etl_valida_arquivo_guarda(pipeline_name,run_id,task_id,tentativa,inicio_tentativa,decisao,origens_json) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                        args + (inicio, decisao, json.dumps(origens)))
        conn.commit()
    except Exception:
        conn.rollback(); raise AirflowException(ERRO) from None
    finally:
        cur.close(); conn.close()


def ler_guarda(hook, payload, ti):
    if ti is None: return None
    try: tentativa, inicio = identidade(ti)
    except AirflowException: return None
    row = hook.get_first('SELECT inicio_tentativa,decisao,origens_json FROM dbo.etl_valida_arquivo_guarda WHERE pipeline_name=%s AND run_id=%s AND task_id=%s AND tentativa=%s',
                         parameters=(payload['pipeline'], payload['run_id'], ti.task_id, tentativa))
    if not row or row[0] != inicio: return None
    return dict(decisao=row[1], origens=json.loads(row[2]))


def prova_atual(prova, controladores, tentativas):
    if not prova or prova['decisao'] not in ('liberar', 'pular'): return False
    origens = prova['origens']
    if len(origens) != len(controladores) or {o['no'] for o in origens} != set(controladores): return False
    return all(tentativas.get(o['no']) == o['tentativa'] and o['decisao'] in ('liberar', 'pular') for o in origens)


def pulado_pela_validacao(hook, payload, ti, controladores=None, tentativas=None):
    if ti is None or str(ti.state) != 'skipped': return False
    prova = ler_guarda(hook, payload, ti)
    return bool(prova and prova['decisao'] == 'pular' and (controladores is None or prova_atual(prova, controladores, tentativas or {})))


def avaliar_no(no, pipeline, mssql_conn_id, **context):
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    payload = ps.carregar(hook, pipeline, context['run_id'])
    config = registro.config_original(payload, no)
    tentativa, _ = identidade(context['ti'])
    # Uma repetição da mesma tentativa reaproveita seu diagnóstico; retry novo reavalia
    # o arquivo, sempre com configuração ORIGINAL, nunca com cadastro editado.
    row = hook.get_first('SELECT revisao,resultado_json FROM dbo.etl_valida_arquivo_tentativa WHERE pipeline_name=%s AND run_id=%s AND task_id=%s AND tentativa=%s',
                         parameters=(pipeline, context['run_id'], no, tentativa))
    if row:
        resultado = registro.ler_tentativa(hook, payload, no, tentativa)
    else:
        from airflow.providers.ssh.hooks.ssh import SSHHook
        from utils.valida_arquivo_io import avaliar
        ssh = None
        try:
            sh = SSHHook(ssh_conn_id=config['ssh_conn_id'], conn_timeout=config['timeout_segundos'], banner_timeout=config['timeout_segundos'], cmd_timeout=config['timeout_segundos'])
            extras = sh.get_connection(config['ssh_conn_id']).extra_dejson
            ssh = sh.get_conn()
            resultado = avaliar(config, payload['catalogo'], ssh, extras)
        except Exception:
            resultado = {'entradas': [va.decidir(e, 'erro_tecnico' if i == 0 else 'nao_avaliado') for i, e in enumerate(config['entradas'])]}
        finally:
            if ssh is not None:
                try: ssh.close()
                except Exception: pass  # Não encobrir diagnóstico já obtido.
        resultado = registro.registrar(hook, payload, no, tentativa, resultado)
    if resultado['falhou']:
        raise AirflowException('Validação falhou; diagnóstico preservado e destinos bloqueados.')
    # Nenhum conteúdo/configuração em XCom.


def decidir_guarda(pais, propria, regra="all_success"):
    """Pais já resolvidos: success, validation_skip, skipped, failed ou incomplete."""
    if any(p in ('failed', 'incomplete', 'branch_skipped') for p in pais): return 'bloquear'
    # Um skip comprovado de validação pode ser atravessado por liberação explícita.
    # Skip de branch/canal/manual não equivale a validação sem dados.
    if 'skipped' in pais and regra != 'all_done':
        if regra not in ('none_failed_min_one_success', 'none_failed') or 'success' not in pais:
            return 'bloquear'
    return propria


def guarda(context, pipeline, mssql_conn_id, mapa):
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    payload = ps.carregar(hook, pipeline, context['run_id'])
    ti = context['ti']
    no = next((n for n, d in mapa.items() if ti.task_id in (d['inicio'], d['executor'])), None)
    if no is None: raise AirflowException(ERRO)
    infos = {t.task_id: t for t in context['dag_run'].get_task_instances()}
    config = mapa[no]; origens = []; escolhas = []
    tentativas_atuais = {n: identidade(infos[c['executor']])[0] for n, c in mapa.items() if c['tipo'] == 'valida_arquivo' and c['executor'] in infos and str(infos[c['executor']].state) == 'success'}
    for validador in config['controladores']:
        vti = infos.get(mapa[validador]['executor'])
        if vti is None or str(vti.state) != 'success':
            escolhas.append('bloquear'); continue
        tentativa, _ = identidade(vti)
        resultado = registro.ler_tentativa(hook, payload, validador, tentativa)
        decisao = resultado['destinos'].get(no)
        if decisao not in ('liberar', 'pular', 'bloquear'): raise AirflowException(ERRO)
        escolhas.append(decisao)
        origens.append(dict(no=validador, tentativa=tentativa, decisao=decisao))
    propria = 'bloquear' if 'bloquear' in escolhas else 'pular' if 'pular' in escolhas else 'liberar'
    pais = []
    for pai in config['pais']:
        p = mapa[pai]; fim = infos.get(p['fim']); executor = infos.get(p['executor'])
        estados = {str(t.state) if t else 'missing' for t in (fim, executor)}
        if estados == {'success'}: pais.append('validation_success' if p['tipo'] == 'valida_arquivo' else 'success')
        elif estados & {'failed', 'upstream_failed', 'removed'}: pais.append('failed')
        elif any(s not in TERMINAIS for s in estados): pais.append('incomplete')
        elif 'skipped' in estados:
            if p['tipo'] == 'decisao':
                pais.append('branch_skipped'); continue
            marca = infos.get(p['inicio'])
            pais.append('validation_skip' if pulado_pela_validacao(hook, payload, marca, p['controladores'], tentativas_atuais) else 'skipped')
    decisao = decidir_guarda(pais, propria, config['regra'])
    # Na segunda barreira o log_start também precisa ter realmente concluído.
    if ti.task_id == config['executor'] and config['inicio'] != config['executor']:
        inicio = infos.get(config['inicio'])
        if not inicio or str(inicio.state) != 'success': decisao = 'bloquear'
    gravar_guarda(hook, payload, ti, decisao, origens)
    if decisao != 'liberar':
        raise AirflowSkipException('Sem dados conforme política original.' if decisao == 'pular' else 'Bloqueado pela validação ou por dependência não satisfeita.')


def classificar(destinos, falhas, politica):
    """Classifica o trabalho real dos consumidores, sem esconder etapas a montante."""
    if falhas: resultado = 'FALHA'
    elif any(d['estado'] == 'success' for d in destinos.values()): resultado = 'COM_MOVIMENTO'
    elif destinos and all(d['estado'] == 'skipped' and d['por_validacao'] for d in destinos.values()): resultado = 'SEM_MOVIMENTO'
    else: resultado = 'SEM_EXECUCAO'
    liberar = resultado == 'COM_MOVIMENTO' or (resultado == 'SEM_MOVIMENTO' and bool(politica['liberar_dependentes']))
    notificar = resultado != 'SEM_MOVIMENTO' or bool(politica['notificar'])
    return dict(resultado=resultado, liberar_dependentes=liberar, notificar=notificar)


def persistir_conclusao(hook, payload, conclusao, detalhes, data_ref):
    conn = hook.get_conn(); cur = conn.cursor()
    try:
        chave = (payload['pipeline'], payload['run_id'])
        cur.execute('SELECT resultado FROM dbo.etl_valida_arquivo_conclusao WITH (UPDLOCK,HOLDLOCK) WHERE pipeline_name=%s AND run_id=%s', chave)
        existe = cur.fetchone()
        values = (conclusao['resultado'], int(conclusao['liberar_dependentes']), int(conclusao['notificar']), json.dumps(detalhes, ensure_ascii=False))
        if existe:
            cur.execute('UPDATE dbo.etl_valida_arquivo_conclusao SET resultado=%s,liberar_dependentes=%s,notificar=%s,detalhes_json=%s,atualizado_em=SYSUTCDATETIME() WHERE pipeline_name=%s AND run_id=%s', values + chave)
        else:
            cur.execute('INSERT dbo.etl_valida_arquivo_conclusao(resultado,liberar_dependentes,notificar,detalhes_json,pipeline_name,run_id) VALUES(%s,%s,%s,%s,%s,%s)', values + chave)
        status = 'FALHA' if conclusao['resultado'] == 'FALHA' else 'SUCESSO' if conclusao['liberar_dependentes'] else 'PULADO'
        motivo = {'SEM_MOVIMENTO': 'Concluído sem movimento', 'SEM_EXECUCAO': 'Concluído sem execução dos destinos', 'FALHA': 'Falha na execução ou na validação', 'COM_MOVIMENTO': None}[conclusao['resultado']]
        cur.execute('UPDATE dbo.etl_pipeline_execucao SET status=%s,motivo=%s,fim=GETDATE(),atualizado_em=GETDATE() WHERE pipeline_name=%s AND execution_id=%s AND data_referencia=%s',
                    (status, motivo) + chave + (data_ref,))
        if cur.rowcount != 1: raise ValueError('Identidade da corrida ausente ou ambígua.')
        conn.commit()
    except Exception:
        conn.rollback(); raise AirflowException('Encerramento não persistido; publicação e dependentes bloqueados.') from None
    finally:
        cur.close(); conn.close()


def finalizar(context, pipeline, mssql_conn_id, mapa, data_ref):
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    payload = ps.carregar(hook, pipeline, context['run_id'])
    infos = {t.task_id: t for t in context['dag_run'].get_task_instances()}
    falhas = []; observados = {}; tentativas = {}
    for no, config in mapa.items():
        for tid in {config['inicio'], config['executor'], config['fim']}:
            ti = infos.get(tid); estado = str(ti.state) if ti else 'missing'
            observados[tid] = dict(estado=estado, tentativa=ti.try_number if ti else None)
            if estado not in ('success', 'skipped'): falhas.append(tid)
        if config['tipo'] == 'valida_arquivo':
            ti = infos.get(config['executor'])
            if ti and str(ti.state) == 'success':
                tentativa, _ = identidade(ti)
                resultado = registro.ler_tentativa(hook, payload, no, tentativa)
                tentativas[no] = tentativa
                if resultado['falhou']: falhas.append(no)
    destinos = {}
    for no, config in mapa.items():
        if not config['controladores']: continue
        ti = infos.get(config['executor']); ini = infos.get(config['inicio'])
        estado = str(ti.state) if ti else 'missing'
        prova = ler_guarda(hook, payload, ti) if estado == 'success' else ler_guarda(hook, payload, ini) or ler_guarda(hook, payload, ti)
        atual = prova_atual(prova, config['controladores'], tentativas)
        if estado == 'success' and (not atual or prova['decisao'] != 'liberar'):
            falhas.append(no + ': autorização de outra tentativa ou ausente')
        if estado == 'skipped' and prova and prova['decisao'] == 'pular' and not atual:
            falhas.append(no + ': salto de outra tentativa')
        destinos[no] = dict(estado=estado, por_validacao=bool(estado == 'skipped' and atual and prova['decisao'] == 'pular'))
    conclusao = classificar(destinos, falhas, payload['politica_sem_movimento'])
    detalhes = dict(destinos=destinos, falhas=sorted(set(falhas)), tarefas=observados, tentativas=tentativas,
                    executados_montante=[n for n, c in mapa.items() if not c['controladores'] and c['tipo'] != 'valida_arquivo' and observados[c['executor']]['estado'] == 'success'])
    persistir_conclusao(hook, payload, conclusao, detalhes, data_ref)
    if falhas: raise AirflowException('Corrida em falha; publicação de sucesso bloqueada.')
    return conclusao


def permitir_publicacao(context, pipeline, mssql_conn_id, mapa, data_ref):
    # Reconfere estados/tentativas até num clear somente do publish: não usa conclusão antiga.
    conclusao = finalizar(context, pipeline, mssql_conn_id, mapa, data_ref)
    if not conclusao['liberar_dependentes']:
        raise AirflowSkipException('Conclusão registrada; política original não libera dependentes.')


def permitir_notificacao(context, pipeline, mssql_conn_id):
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    row = hook.get_first('SELECT notificar FROM dbo.etl_valida_arquivo_conclusao WHERE pipeline_name=%s AND run_id=%s', parameters=(pipeline, context['run_id']))
    if row and not row[0]: raise AirflowSkipException('Notificação de conclusão sem movimento desativada.')
