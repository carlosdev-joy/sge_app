"""DAG: etl_servicenow_sync — Espelho de chamados do ServiceNow.

Lê incident, sc_req_item, sc_task e change_request da Table API do ServiceNow
filtrado pelo(s) grupo(s) configurados em etl_app_config, faz upsert em
dbo.etl_chamado e registra o ciclo em dbo.etl_chamado_sync.

Intervalo configurável via etl_app_config.servicenow_intervalo_horas
(padrão 3h). Para alterar: atualizar no Admin e repausar/despausar a DAG.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable

log = logging.getLogger(__name__)

# ── Mapeamento estado → coluna kanban ────────────────────────────────────────
# Valores numéricos conforme display_value=false (valor interno do ServiceNow).
# Não mapeado → 'outros' (nunca some em silêncio).
_ESTADO_KANBAN = {
    "incident": {
        "1": "novo",        # New
        "2": "andamento",   # In Progress
        "3": "aguardando",  # On Hold
        "6": "resolvido",   # Resolved
        "7": "outros",      # Closed
        "8": "outros",      # Canceled
    },
    "sc_req_item": {
        "1":  "novo",       # Pending Approval / Open
        "2":  "andamento",  # Work in Progress
        "3":  "aguardando", # Closed Incomplete
        "4":  "resolvido",  # Closed Complete
        "7":  "aguardando", # Awaiting Approval
        "16": "aguardando", # Awaiting Catalog Task
        "10": "outros",     # Canceled
    },
    "sc_task": {
        "1": "novo",
        "2": "andamento",
        "3": "aguardando",
        "4": "resolvido",
        "7": "outros",
    },
    "change_request": {
        "-5": "aguardando",  # New
        "-4": "aguardando",  # Assess
        "-3": "aguardando",  # Authorize
        "-2": "aguardando",  # Scheduled
        "-1": "andamento",   # Implement
        "0":  "resolvido",   # Review
        "3":  "outros",      # Closed
        "4":  "outros",      # Canceled
    },
}

# Campos numérico que indicam chamado encerrado (ativo → False no espelho)
_ESTADOS_ENCERRADOS = {
    "incident":       {"7", "8"},
    "sc_req_item":    {"3", "4", "10"},
    "sc_task":        {"4", "7"},
    "change_request": {"3", "4"},
}

# Tipo legível por tabela
_TIPO = {
    "incident":      "incident",
    "sc_req_item":   "ritm",
    "sc_task":       "task",
    "change_request":"change",
}

# Campo de número por tabela
_CAMPO_NUMERO = {
    "incident":      "number",
    "sc_req_item":   "number",
    "sc_task":       "number",
    "change_request":"number",
}

# Campo de data de encerramento por tabela
_CAMPO_ENCERRADO = {
    "incident":      "closed_at",
    "sc_req_item":   "closed_at",
    "sc_task":       "closed_at",
    "change_request":"close_date",
}


def _get_config(cur, key: str, default: str = "") -> str:
    cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key = ?", (key,))
    row = cur.fetchone()
    return (row[0] or "").strip() if row else default


def _decrypt(cur, senha_enc: str) -> str:
    """Decifra senha usando o mesmo serviço da API (ORQUESTRA_CONN_KEY)."""
    if not senha_enc:
        return ""
    try:
        import sys, os
        sys.path.insert(0, "/opt/airflow/dags/Orquestrador")
        sys.path.insert(0, "/opt/airflow")
        from services.conn_crypto import decrypt_password
        return decrypt_password(senha_enc)
    except Exception as e:
        log.warning("decrypt falhou: %s — usando valor bruto", e)
        return senha_enc


def _trunc(s, n=400):
    if not s:
        return None
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def _parse_dt(v):
    if not v or v == "0001-01-01 00:00:00":
        return None
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _fetch_tabela(session, base_url: str, tabela: str, grupos: list[str]) -> list[dict]:
    """Busca todos os registros da tabela para os grupos especificados."""
    import requests as _req

    tipo = _TIPO[tabela]
    campo_num = _CAMPO_NUMERO[tabela]
    campo_enc = _CAMPO_ENCERRADO[tabela]

    campos = ",".join([
        "sys_id", campo_num, "short_description", "state",
        "priority", "assigned_to", "assignment_group",
        "opened_at", "sys_updated_on", campo_enc, "active",
    ])

    registros: list[dict] = []

    for grupo in grupos:
        grupo = grupo.strip()
        if not grupo:
            continue

        offset = 0
        limit = 500
        while True:
            query = f"assignment_group.name={grupo}"
            params = {
                "sysparm_query":         query,
                "sysparm_fields":        campos,
                "sysparm_display_value": "all",  # valor + display juntos
                "sysparm_limit":         limit,
                "sysparm_offset":        offset,
            }
            r = session.get(f"{base_url}/api/now/table/{tabela}", params=params, timeout=30)
            r.raise_for_status()
            data = r.json().get("result", [])
            if not data:
                break

            for rec in data:
                def _val(field):
                    v = rec.get(field)
                    if isinstance(v, dict):
                        return v.get("value") or ""
                    return str(v) if v else ""

                def _display(field):
                    v = rec.get(field)
                    if isinstance(v, dict):
                        return v.get("display_value") or v.get("value") or ""
                    return str(v) if v else ""

                estado_raw = _val("state")
                mapa = _ESTADO_KANBAN.get(tabela, {})
                estado_kanban = mapa.get(estado_raw, "outros")
                ativo = _val("active").lower() not in ("false", "0", "") and \
                        estado_raw not in _ESTADOS_ENCERRADOS.get(tabela, set())

                sys_id = _val("sys_id")
                base = base_url.rstrip("/")
                url_portal = f"{base}/nav_to.do?uri={tabela}.do?sys_id={sys_id}"

                registros.append({
                    "sys_id":        sys_id,
                    "numero":        _val(campo_num) or sys_id[:20],
                    "tipo":          tipo,
                    "titulo":        _trunc(_display("short_description")),
                    "estado_origem": _display("state"),
                    "estado_kanban": estado_kanban,
                    "prioridade":    _display("priority"),
                    "atribuido_a":   _trunc(_display("assigned_to"), 120),
                    "grupo":         _trunc(_display("assignment_group"), 120),
                    "aberto_em":     _parse_dt(_val("opened_at")),
                    "atualizado_em": _parse_dt(_val("sys_updated_on")),
                    "encerrado_em":  _parse_dt(_val(campo_enc)),
                    "ativo":         1 if ativo else 0,
                    "url":           url_portal[:500],
                })

            offset += len(data)
            if len(data) < limit:
                break

    return registros


def sync_servicenow(**_ctx):
    import pymssql
    import requests as _req
    import os

    conn_str = os.environ.get("MSSQL_CONN_STR", "")
    if not conn_str:
        raise RuntimeError("MSSQL_CONN_STR não definida")

    # pymssql a partir de MSSQL_CONN_STR (formato pyodbc → extrai host/db/user/pwd)
    import re as _re
    def _par(key):
        m = _re.search(rf"{key}=([^;]+)", conn_str, _re.I)
        return m.group(1).strip("{}") if m else ""

    db_conn = pymssql.connect(
        server=_par("SERVER") or _par("Data Source"),
        user=_par("UID") or _par("User ID"),
        password=_par("PWD") or _par("Password"),
        database=_par("DATABASE") or _par("Initial Catalog"),
        login_timeout=10,
    )
    cur = db_conn.cursor()

    # ── Ler config ────────────────────────────────────────────────────────
    base_url  = _get_config(cur, "servicenow_url").rstrip("/")
    grupos_str= _get_config(cur, "servicenow_grupos", "TI_CVP_GERESD_ED")
    usuario   = _get_config(cur, "servicenow_usuario")
    senha_enc = _get_config(cur, "servicenow_senha")

    if not base_url or not usuario:
        raise RuntimeError("servicenow_url e servicenow_usuario devem estar configurados no Admin")

    senha = _decrypt(cur, senha_enc)
    grupos = [g.strip() for g in grupos_str.split(",") if g.strip()]

    # ── Registrar início do ciclo ─────────────────────────────────────────
    cur.execute(
        "INSERT INTO dbo.etl_chamado_sync (iniciado_em, status) VALUES (GETDATE(), 'RODANDO')"
    )
    db_conn.commit()
    cur.execute("SELECT @@IDENTITY")
    sync_id = int(cur.fetchone()[0])

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else {}

    session = _req.Session()
    session.auth = (usuario, senha)
    session.headers["Accept"] = "application/json"
    if proxies:
        session.proxies.update(proxies)

    contagens: dict[str, int] = {}
    erros: list[str] = []
    qtd_desativados = 0

    tabelas = ["incident", "sc_req_item", "sc_task", "change_request"]

    for tabela in tabelas:
        try:
            registros = _fetch_tabela(session, base_url, tabela, grupos)
            contagens[tabela] = len(registros)

            for r in registros:
                cur.execute("""
                    MERGE dbo.etl_chamado AS t
                    USING (SELECT %(sys_id)s AS sys_id) AS s ON t.sys_id = s.sys_id
                    WHEN MATCHED THEN UPDATE SET
                        numero        = %(numero)s,
                        tipo          = %(tipo)s,
                        titulo        = %(titulo)s,
                        estado_origem = %(estado_origem)s,
                        estado_kanban = %(estado_kanban)s,
                        prioridade    = %(prioridade)s,
                        atribuido_a   = %(atribuido_a)s,
                        grupo         = %(grupo)s,
                        aberto_em     = %(aberto_em)s,
                        atualizado_em = %(atualizado_em)s,
                        encerrado_em  = %(encerrado_em)s,
                        ativo         = %(ativo)s,
                        url           = %(url)s,
                        sync_em       = GETDATE()
                    WHEN NOT MATCHED THEN INSERT
                        (sys_id, numero, tipo, titulo, estado_origem, estado_kanban,
                         prioridade, atribuido_a, grupo, aberto_em, atualizado_em,
                         encerrado_em, ativo, url, sync_em)
                    VALUES
                        (%(sys_id)s, %(numero)s, %(tipo)s, %(titulo)s, %(estado_origem)s,
                         %(estado_kanban)s, %(prioridade)s, %(atribuido_a)s, %(grupo)s,
                         %(aberto_em)s, %(atualizado_em)s, %(encerrado_em)s,
                         %(ativo)s, %(url)s, GETDATE());
                """, r)

            db_conn.commit()
            log.info("[SN-SYNC] %s: %d registros", tabela, len(registros))

        except Exception as e:
            erros.append(f"{tabela}: {e}")
            log.error("[SN-SYNC] Erro em %s: %s", tabela, e)

    # ── Desativar chamados que sumiram da fila (encerrados no SN) ─────────
    try:
        # sys_ids recém-sincronizados deste ciclo
        cur.execute(
            "UPDATE dbo.etl_chamado SET ativo = 0, sync_em = GETDATE() "
            "WHERE ativo = 1 AND sync_em < DATEADD(MINUTE, -10, GETDATE())"
        )
        qtd_desativados = cur.rowcount
        db_conn.commit()
    except Exception as e:
        log.warning("[SN-SYNC] Desativação falhou: %s", e)

    # ── Fechar registro do ciclo ──────────────────────────────────────────
    status = "ERRO" if erros else "OK"
    erro_msg = "; ".join(erros)[:1000] if erros else None
    cur.execute("""
        UPDATE dbo.etl_chamado_sync SET
            terminado_em    = GETDATE(),
            status          = %s,
            qtd_incident    = %s,
            qtd_ritm        = %s,
            qtd_task        = %s,
            qtd_change      = %s,
            qtd_desativados = %s,
            erro            = %s
        WHERE id = %s
    """, (
        status,
        contagens.get("incident", 0),
        contagens.get("sc_req_item", 0),
        contagens.get("sc_task", 0),
        contagens.get("change_request", 0),
        qtd_desativados,
        erro_msg,
        sync_id,
    ))
    db_conn.commit()
    cur.close()
    db_conn.close()

    if erros:
        raise RuntimeError(f"Sync com erros: {erro_msg}")

    log.info("[SN-SYNC] Ciclo OK — incident=%d ritm=%d task=%d change=%d desativados=%d",
             contagens.get("incident", 0), contagens.get("sc_req_item", 0),
             contagens.get("sc_task", 0), contagens.get("change_request", 0),
             qtd_desativados)


# ── Intervalo configurável via etl_app_config ─────────────────────────────
def _schedule() -> str:
    try:
        import pymssql, os, re as _re
        conn_str = os.environ.get("MSSQL_CONN_STR", "")
        def _par(key):
            m = _re.search(rf"{key}=([^;]+)", conn_str, _re.I)
            return m.group(1).strip("{}") if m else ""
        c = pymssql.connect(
            server=_par("SERVER") or _par("Data Source"),
            user=_par("UID") or _par("User ID"),
            password=_par("PWD") or _par("Password"),
            database=_par("DATABASE") or _par("Initial Catalog"),
            login_timeout=5,
        )
        cur = c.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key='servicenow_intervalo_horas'")
        row = cur.fetchone()
        c.close()
        horas = int((row[0] or "3").strip()) if row else 3
        horas = max(1, min(24, horas))
        return f"0 */{horas} * * *"
    except Exception:
        return "0 */3 * * *"


with DAG(
    dag_id="etl_servicenow_sync",
    description="Espelho de chamados do ServiceNow → dbo.etl_chamado",
    schedule_interval=_schedule(),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["servicenow", "sync"],
) as dag:

    PythonOperator(
        task_id="sync",
        python_callable=sync_servicenow,
    )
