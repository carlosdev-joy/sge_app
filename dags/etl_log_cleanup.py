"""etl_log_cleanup.py — limpeza diária de logs com mais de 10 dias.

Roda às 03h, remove arquivos .log com mtime > 10 dias e diretórios
vazios que sobram. Mantém 10 dias de histórico — suficiente para
depurar qualquer falha recente sem acumular gigabytes.

Também apaga as conversas do Maestro (dbo.etl_maestro_conversa, migration
110) com mais de 180 dias — spec docs/spec-maestro-parametros.md, F3. Tarefa
separada: falha no banco não impede a limpeza dos logs, e vice-versa.
"""
from __future__ import annotations

import os
import subprocess

import pendulum
from airflow.decorators import dag, task

LOG_DIR = "/opt/airflow/logs"
RETENCAO_DIAS = 10
# Mesma conexão das outras DAGs de manutenção (etl_admin_manage).
MSSQL_CONN_ID = "SQL14_DMDB41"
# Espelha services/maestro.RETENCAO_CONVERSAS_DIAS (api/ e dags/ não se importam).
RETENCAO_CONVERSAS_MAESTRO_DIAS = 180
_SQL_APAGAR_CONVERSAS = ("DELETE FROM dbo.etl_maestro_conversa "
                         "WHERE criado_em < DATEADD(day, -%s, GETDATE())")


def apagar_conversas_antigas(conn, dias: int = RETENCAO_CONVERSAS_MAESTRO_DIAS) -> dict:
    """DELETE das conversas do Maestro mais velhas que `dias`. Sem a tabela
    (migration 110 pendente) não faz nada e diz isso — nunca quebra a DAG.
    Cursor pymssql: placeholders `%s` (gotcha do repo)."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_maestro_conversa', 'U')")
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"tabela": "ausente (migration 110 pendente)", "apagadas": 0, "retencao_dias": dias}
        cur.execute(_SQL_APAGAR_CONVERSAS, (int(dias),))
        apagadas = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
        conn.commit()
        return {"tabela": "ok", "apagadas": int(apagadas), "retencao_dias": dias}
    finally:
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass


@dag(
    dag_id="etl_log_cleanup",
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Sao_Paulo"),
    catchup=False,
    tags=["manutencao"],
)
def etl_log_cleanup():

    @task
    def limpar_logs() -> dict:
        result = subprocess.run(
            ["find", LOG_DIR, "-name", "*.log",
             "-mtime", f"+{RETENCAO_DIAS}", "-delete"],
            capture_output=True, text=True)
        subprocess.run(
            ["find", LOG_DIR, "-type", "d", "-empty", "-delete"],
            capture_output=True, text=True)
        # uso atual após limpeza
        total = subprocess.run(
            ["du", "-sh", LOG_DIR], capture_output=True, text=True)
        disco = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True)
        return {
            "log_dir_uso": total.stdout.split()[0] if total.stdout else "?",
            "disco": disco.stdout,
            "stderr": result.stderr[:200] if result.stderr else "",
        }

    @task
    def limpar_conversas_maestro() -> dict:
        from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
        conn = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID).get_conn()
        try:
            return apagar_conversas_antigas(conn)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    limpar_logs()
    limpar_conversas_maestro()


etl_log_cleanup()
