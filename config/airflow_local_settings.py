"""Política F4 aplicada novamente pelo Airflow antes da execução da tarefa.

O gate fica no pre_execute (exceções propagam), nunca em callback tolerante.
Não usa dag_run.conf/params resolvidos, que podem ser substituídos no disparo.
"""
import os
from datetime import timezone
from types import MethodType


def task_instance_mutation_hook(task_instance):
    if os.getenv("WORKSPACE_PUBLICATIONS_ENABLED", "false").lower() != "true":
        return
    task = task_instance.task
    if task is None or getattr(task, "_workspace_gate_installed", False):
        return
    original = task.pre_execute

    def guarded(self, context):
        from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
        params = self.dag.params
        queued_at = getattr(context["dag_run"], "queued_at", None)
        if queued_at is not None:
            queued_at = queued_at.astimezone(timezone.utc).replace(tzinfo=None)
        connection = MsSqlHook(mssql_conn_id="SQL14_DMDB41").get_conn()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC dbo.sp_workspace_guard_run @name=%s,@run_id=%s,@version=%s,@hash=%s,@queued_at=%s",
                (self.dag_id, context["dag_run"].run_id,
                 params.get("workspace_version_id"), params.get("workspace_content_hash"), queued_at),
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()
        return original(context=context)

    task.pre_execute = MethodType(guarded, task)
    task._workspace_gate_installed = True
