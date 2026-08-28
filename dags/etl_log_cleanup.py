"""etl_log_cleanup.py — limpeza diária de logs com mais de 10 dias.

Roda às 03h, remove arquivos .log com mtime > 10 dias e diretórios
vazios que sobram. Mantém 10 dias de histórico — suficiente para
depurar qualquer falha recente sem acumular gigabytes.
"""
from __future__ import annotations

import os
import subprocess

import pendulum
from airflow.decorators import dag, task

LOG_DIR = "/opt/airflow/logs"
RETENCAO_DIAS = 10


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

    limpar_logs()


etl_log_cleanup()
