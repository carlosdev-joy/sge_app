"""dags/utils/job_operators.py — operadores reutilizáveis dos jobs gerados.

O factory gera DAGs que apenas CHAMAM estes operadores (igual ao DataStage).
Assim, melhorias na execução de um tipo de job (log, tratamento de erro, bind de
parâmetros…) entram aqui e TODAS as DAGs herdam no próximo parse do Airflow, SEM
precisar regenerar os arquivos. Só mudanças de ESTRUTURA (jobs, dependências,
agendamento) exigem regeneração.
"""
from __future__ import annotations

from airflow.models import BaseOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.providers.ssh.operators.ssh import SSHOperator

_INT_TYPES   = {"INT", "BIGINT", "SMALLINT", "TINYINT"}
_FLOAT_TYPES = {"DECIMAL", "NUMERIC", "FLOAT", "MONEY", "REAL"}


def _coerce(value, ptype):
    """Converte o valor do parâmetro conforme o tipo declarado (runtime)."""
    ptype = (ptype or "VARCHAR").upper()
    if value is None or value == "":
        return None
    try:
        if ptype in _INT_TYPES:
            return int(value)
        if ptype in _FLOAT_TYPES:
            return float(value)
        if ptype == "BIT":
            return 1 if str(value).strip().lower() in ("1", "true", "sim", "yes", "y", "t") else 0
    except (TypeError, ValueError):
        return value
    return value


def _log_resultsets(cur, log):
    """Itera os result sets retornados e loga quantidade/amostra/linhas afetadas."""
    ssets = 0
    total = 0
    while True:
        if cur.description:
            rows = cur.fetchall()
            ssets += 1
            total += len(rows)
            log.info("[SQL] resultado %d: %d linha(s)", ssets, len(rows))
            for r in rows[:50]:
                log.info("[SQL]   %s", tuple(r))
        elif cur.rowcount is not None and cur.rowcount >= 0:
            log.info("[SQL] linhas afetadas: %d", cur.rowcount)
        if not cur.nextset():
            break
    return ssets, total


class StoredProcOperator(BaseOperator):
    """EXEC de stored procedure com bind de parâmetros e log do retorno/erro."""

    def __init__(self, *, proc, mssql_conn_id, params=None, database=None, **kwargs):
        super().__init__(**kwargs)
        self.proc = proc
        self.mssql_conn_id = mssql_conn_id
        self.params = params or []
        self.database = (database or "").strip() or None

    def execute(self, context):
        if not self.proc:
            raise ValueError("StoredProcOperator: 'proc' não informado")
        # Banco-alvo no MESMO servidor → nome de 3 partes: EXEC [banco].schema.proc
        target = f"[{self.database}].{self.proc}" if self.database else self.proc
        hook = MsSqlHook(mssql_conn_id=self.mssql_conn_id)
        conn = hook.get_conn()
        cur = conn.cursor()
        try:
            valid = [p for p in self.params if (p.get("name") or "").strip()]
            if valid:
                ph = ", ".join(
                    (str(p["name"]) if str(p["name"]).startswith("@") else "@" + str(p["name"])) + "=?"
                    for p in valid
                )
                vals = [_coerce(p.get("value"), p.get("type")) for p in valid]
                sql = f"EXEC {target} {ph}"
                self.log.info("[SQL] %s", sql)
                cur.execute(sql, vals)
            else:
                # Sem parâmetros → não envia nenhum parâmetro.
                self.log.info("[SQL] EXEC %s", target)
                cur.execute(f"EXEC {target}")
            ssets, total = _log_resultsets(cur, self.log)
            conn.commit()
            self.log.info("[SQL] proc %s OK (result sets=%d, linhas=%d)", target, ssets, total)
        except Exception as e:
            self.log.error("[SQL][ERRO] %s: %s", target, e)
            raise
        finally:
            try:
                cur.close(); conn.close()
            except Exception:
                pass


class SqlOperator(BaseOperator):
    """SQL livre com log do retorno/erro."""

    def __init__(self, *, sql, mssql_conn_id, **kwargs):
        super().__init__(**kwargs)
        self.sql = sql
        self.mssql_conn_id = mssql_conn_id

    def execute(self, context):
        hook = MsSqlHook(mssql_conn_id=self.mssql_conn_id)
        conn = hook.get_conn()
        cur = conn.cursor()
        try:
            self.log.info("[SQL] %s", self.sql)
            cur.execute(self.sql)
            ssets, total = _log_resultsets(cur, self.log)
            conn.commit()
            self.log.info("[SQL] OK (result sets=%d, linhas=%d)", ssets, total)
        except Exception as e:
            self.log.error("[SQL][ERRO] %s", e)
            raise
        finally:
            try:
                cur.close(); conn.close()
            except Exception:
                pass


class PythonModuleOperator(BaseOperator):
    """Importa um módulo e chama run(**context) ou main()."""

    def __init__(self, *, module, **kwargs):
        super().__init__(**kwargs)
        self.module = module

    def execute(self, context):
        import importlib
        self.log.info("[PY] importando %s", self.module)
        mod = importlib.import_module(self.module)
        if hasattr(mod, "run"):
            mod.run(**context)
        elif hasattr(mod, "main"):
            mod.main()
        else:
            raise AttributeError(f"módulo '{self.module}' não tem run() nem main()")
        self.log.info("[PY] %s concluído", self.module)


class HttpCallOperator(BaseOperator):
    """Chamada HTTP simples com raise_for_status."""

    def __init__(self, *, url, method="GET", timeout=30, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.method = method
        self.timeout = timeout

    def execute(self, context):
        import requests
        self.log.info("[HTTP] %s %s", self.method, self.url)
        resp = requests.request(self.method, self.url, timeout=self.timeout)
        resp.raise_for_status()
        self.log.info("[HTTP] status=%s bytes=%s", resp.status_code, len(resp.content))
        return resp.status_code


class ShellOperator(SSHOperator):
    """Job shell do ORQUESTRA — ponto central para evoluir o comportamento dos
    jobs shell (hoje, comportamento idêntico ao SSHOperator)."""
    pass
