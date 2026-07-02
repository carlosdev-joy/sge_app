"""
etl_admin_manage.py
===================
DAG administrativa — operações restritas ao usuário admin.

Gerencia:
  1. etl_app_config  — UPSERT / DELETE de parâmetros
  2. etl_pipeline    — DELETE cascade via sp_etl_pipeline_delete
  3. etl_conexao     — conn_migrate: importa as Airflow Connections mssql
                       (com senha, cifrada com ORQUESTRA_CONN_KEY)

Entrada via conf:
  action         : 'config_upsert' | 'config_delete' | 'pipeline_delete' |
                   'dag_file_delete' | 'regenerate_all_dags' | 'conn_migrate'
  requested_by   : str   — matrícula (validada no backend também)

  Para config_upsert:
    config_key   : str
    config_value : str
    descricao    : str (opcional)

  Para config_delete:
    config_key   : str

  Para pipeline_delete:
    pipeline_name : str

Saída XCom:
  { "sucesso": bool, "mensagem": str, "detalhes": dict }
"""

from __future__ import annotations
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = 'etl_admin_manage'
MSSQL_CONN_ID = 'SQL14_DMDB41'
LOCAL_TZ      = 'America/Sao_Paulo'

default_args = {'owner': 'airflow', 'depends_on_past': False, 'retries': 0}


def _is_admin(hook, matricula):
    """Permissão de admin vem do banco (RBAC — migration 019)."""
    rows = hook.get_records(
        "SELECT 1 FROM dbo.etl_usuario u "
        "JOIN dbo.etl_perfil_permissao p ON p.perfil_nome = u.perfil_nome "
        "WHERE u.matricula = %s AND u.ativo = 1 AND p.recurso = 'acao_admin'",
        parameters=(matricula,))
    return bool(rows)


def admin_manage(**context):
    conf         = context['dag_run'].conf or {}
    action       = (conf.get('action') or '').strip()
    requested_by = (conf.get('requested_by') or '').strip().upper()

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # Validação de segurança no backend (RBAC em dbo.etl_usuario/etl_perfil_permissao)
    if not requested_by or not _is_admin(hook, requested_by):
        raise PermissionError(
            f"Usuário '{requested_by}' não tem permissão para operações administrativas."
        )
    if not action:
        raise ValueError("Parâmetro 'action' obrigatório.")

    # ── config_upsert ────────────────────────────────────────────────────────
    if action == 'config_upsert':
        key   = (conf.get('config_key')   or '').strip()
        value = (conf.get('config_value') or '').strip()
        desc  = (conf.get('descricao')    or '').strip() or None
        if not key:  raise ValueError("config_key obrigatório.")
        if not value: raise ValueError("config_value obrigatório.")

        hook.run("""
            MERGE dbo.etl_app_config AS t
            USING (SELECT %s AS k, %s AS v, %s AS d) AS s
            ON t.config_key = s.k
            WHEN MATCHED     THEN UPDATE SET config_value=%s, descricao=COALESCE(%s,t.descricao),
                                             updated_by=%s, updated_at=GETDATE()
            WHEN NOT MATCHED THEN INSERT (config_key,config_value,descricao,updated_by,updated_at)
                                  VALUES (s.k, s.v, s.d, %s, GETDATE());
        """, parameters=[key, value, desc, value, desc, requested_by, requested_by])

        print(f"[ADMIN] config_upsert: {key} = {value} (by {requested_by})")
        return {'sucesso': True, 'mensagem': f'Parâmetro "{key}" salvo com sucesso.', 'detalhes': {'key': key, 'value': value}}

    # ── config_delete ────────────────────────────────────────────────────────
    elif action == 'config_delete':
        key = (conf.get('config_key') or '').strip()
        if not key: raise ValueError("config_key obrigatório.")

        rows = hook.run("DELETE FROM dbo.etl_app_config WHERE config_key = %s", parameters=[key])
        print(f"[ADMIN] config_delete: {key} (by {requested_by})")
        return {'sucesso': True, 'mensagem': f'Parâmetro "{key}" removido.', 'detalhes': {'key': key}}

    # ── pipeline_delete ──────────────────────────────────────────────────────
    elif action == 'pipeline_delete':
        pipeline_name = (conf.get('pipeline_name') or '').strip()
        if not pipeline_name: raise ValueError("pipeline_name obrigatório.")

        # Buscar dependências antes de deletar (para retornar no resultado)
        deps = hook.get_first("""
            SELECT total_jobs, total_lineage, dag_criada
            FROM   dbo.vw_pipeline_dependencies
            WHERE  pipeline_name = %s
        """, parameters=[pipeline_name])

        if not deps:
            raise ValueError(f"Pipeline '{pipeline_name}' não encontrado.")

        hook.run(
            "EXEC dbo.sp_etl_pipeline_delete %s, %s",
            parameters=[pipeline_name, requested_by]
        )

        detalhes = {
            'pipeline_name':   pipeline_name,
            'jobs_removidos':  deps[0] if deps else 0,
            'lineage_removidos': deps[1] if deps else 0,
            'dag_existia':     bool(deps[2]) if deps else False,
        }
        print(f"[ADMIN] pipeline_delete: {pipeline_name} — {detalhes} (by {requested_by})")
        return {
            'sucesso': True,
            'mensagem': f'Pipeline "{pipeline_name}" e todas as dependências foram removidos.',
            'detalhes': detalhes,
        }

    # ── dag_file_delete ─────────────────────────────────────────────
    elif action == 'dag_file_delete':
        pipeline_name = (conf.get('pipeline_name') or '').strip()
        if not pipeline_name:
            raise ValueError("pipeline_name obrigatório.")

        import os, glob

        # dag_id = pipeline_name em minúsculo (padrão da etl_dag_factory)
        dag_id = pipeline_name.lower()

        # Diretórios onde a factory pode ter criado o arquivo
        dags_base = os.environ.get('DAGS_FOLDER', '/opt/airflow/dags')
        candidates = [
            os.path.join(dags_base, dag_id + '.py'),
            os.path.join(dags_base, 'Orquestrador', dag_id + '.py'),
            os.path.join(dags_base, pipeline_name + '.py'),
            os.path.join(dags_base, 'Orquestrador', pipeline_name + '.py'),
        ]
        # Busca por glob para cobrir variações de nome
        candidates += glob.glob(os.path.join(dags_base, '**', dag_id + '.py'), recursive=True)
        candidates += glob.glob(os.path.join(dags_base, '**', pipeline_name + '.py'), recursive=True)

        removed = []
        for path in set(candidates):
            if os.path.isfile(path):
                os.remove(path)
                removed.append(path)
                print(f"[ADMIN] Arquivo DAG removido: {path}")

        if not removed:
            print(f"[ADMIN] Nenhum arquivo .py encontrado para pipeline '{pipeline_name}' — pode já ter sido removido.")

        return {
            'sucesso': True,
            'mensagem': f'{len(removed)} arquivo(s) removido(s) para "{pipeline_name}".',
            'detalhes': {'arquivos_removidos': removed},
        }

    # ── regenerate_all_dags ──────────────────────────────────────────────────
    elif action == 'regenerate_all_dags':
        filter_project = (conf.get('filter_project') or '').strip()

        # Resetar dag_criada=0 para os pipelines selecionados
        if filter_project:
            affected = hook.get_first(
                "SELECT COUNT(*) FROM dbo.etl_pipeline WHERE project_name=%s AND DAG_CRIADA=1",
                parameters=(filter_project,)
            )
            n = affected[0] if affected else 0
            hook.run(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                "WHERE project_name=%s AND DAG_CRIADA=1",
                parameters=(filter_project,),
            )
            print(f"[ADMIN] dag_criada=0 para {n} pipeline(s) do projeto '{filter_project}'")
        else:
            affected = hook.get_first(
                "SELECT COUNT(*) FROM dbo.etl_pipeline WHERE DAG_CRIADA=1"
            )
            n = affected[0] if affected else 0
            hook.run(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() WHERE DAG_CRIADA=1"
            )
            print(f"[ADMIN] dag_criada=0 para {n} pipeline(s) (todos os projetos)")

        return {
            'sucesso': True,
            'mensagem': f'{n} pipeline(s) marcados para regeneração.',
            'instrucao': 'Dispare etl_dag_factory com force_all=true para regenerar as DAGs.',
            'detalhes': {'pipelines_marcados': n, 'filter_project': filter_project or '(todos)'},
        }

    # ── conn_migrate ─────────────────────────────────────────────────────────
    # Migra as Airflow Connections mssql para dbo.etl_conexao (migration 054),
    # cifrando a senha com a ORQUESTRA_CONN_KEY (Fernet — a mesma chave do
    # orquestra-api). Roda AQUI porque só o worker enxerga a senha em texto
    # (metadados do Airflow via ORM); a API nunca vê a senha. Conexões que já
    # existem em dbo.etl_conexao são preservadas (não sobrescreve edições).
    elif action == 'conn_migrate':
        import os
        from airflow import settings
        from airflow.models.connection import Connection
        from cryptography.fernet import Fernet

        key = (os.getenv('ORQUESTRA_CONN_KEY') or '').strip()
        if not key:
            raise ValueError(
                "ORQUESTRA_CONN_KEY não configurada nos containers do Airflow — "
                "defina no .env/compose o MESMO valor do orquestra-api.")
        fernet = Fernet(key.encode())

        session = settings.Session()
        try:
            airflow_conns = (session.query(Connection)
                             .filter(Connection.conn_type == 'mssql').all())
            # Materializa os campos DENTRO da sessão (password decifra via ORM)
            candidatas = [{'conn_id': c.conn_id, 'host': c.host, 'port': c.port,
                           'login': c.login, 'password': c.password,
                           'description': c.description, 'extra': c.extra}
                          for c in airflow_conns]
        finally:
            session.close()

        migradas, ja_existiam, sem_dados = [], [], []
        for c in candidatas:
            if hook.get_records("SELECT 1 FROM dbo.etl_conexao WHERE conn_id = %s",
                                parameters=(c['conn_id'],)):
                ja_existiam.append(c['conn_id'])
                continue
            if not (c['host'] and c['login'] and c['password']):
                sem_dados.append(c['conn_id'])
                continue
            senha_enc = fernet.encrypt(c['password'].encode('utf-8')).decode('ascii')
            hook.run(
                "INSERT INTO dbo.etl_conexao "
                "  (conn_id, conn_type, host, port, login, senha_enc, "
                "   descricao, extra_json, origem, criado_por) "
                "VALUES (%s, 'mssql', %s, %s, %s, %s, %s, %s, 'migrada_airflow', %s)",
                parameters=(c['conn_id'], c['host'], c['port'], c['login'],
                            senha_enc, c['description'] or None,
                            c['extra'] or None, requested_by))
            migradas.append(c['conn_id'])

        print(f"[ADMIN] conn_migrate: migradas={migradas} "
              f"ja_existiam={ja_existiam} sem_dados={sem_dados} (by {requested_by})")
        partes = [f"{len(migradas)} conexão(ões) migrada(s)"]
        if ja_existiam:
            partes.append(f"{len(ja_existiam)} já existia(m) no Orquestra")
        if sem_dados:
            partes.append(f"{len(sem_dados)} sem host/login/senha (ignorada(s))")
        return {
            'sucesso': True,
            'mensagem': "Migração concluída: " + "; ".join(partes) + ".",
            'detalhes': {'migradas': migradas, 'ja_existiam': ja_existiam,
                         'sem_dados': sem_dados},
        }

    else:
        raise ValueError(f"Action desconhecida: '{action}'")


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description='Operações administrativas do ORQUESTRA (restrito)',
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=['etl', 'admin', 'restrito'],
    access_control={'Op': {'can_read', 'can_edit'}},
) as dag:

    PythonOperator(
        task_id='admin_manage',
        python_callable=admin_manage,
        do_xcom_push=True,
    )
