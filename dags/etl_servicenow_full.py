"""dags/etl_servicenow_full.py — sync completo às 02h e 14h.

Fluxo: espelho_full → notas_e_anexos_full → snapshot
max_active_runs=1; dagrun_timeout=25min.
Na primeira execução: migra histórico de etl_chamado_sync para etl_chamado_ciclo.

Credencial: lida de etl_app_config (senha_enc decifrada com ORQUESTRA_CONN_KEY),
mesma lógica de etl_servicenow_sync.py e etl_servicenow_delta.py — sem import de api/services.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os

import pendulum
from airflow.decorators import dag, task
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from utils.servicenow_sync import (
    CAMPOS, MAX_PAGINAS, MSSQL_CONN_ID, PAGINA, TABELAS,
    buscar_anexos, buscar_notas,
    capturar_snapshot,
    grupos_ativos, query_do_grupo,
    normalizar, proxy_da_config,
    upsert_anexo_params, upsert_anexo_sql,
    upsert_nota_params, upsert_nota_sql,
    upsert_params, upsert_sql,
)

log = logging.getLogger("orquestra")

K_URL, K_USUARIO = "servicenow_url", "servicenow_usuario"
K_SENHA, K_HABILITADO = "servicenow_senha_enc", "servicenow_habilitado"
DAG_ID = "etl_servicenow_full"


def _decifrar(token: str) -> str:
    """Decifra senha com Fernet+ORQUESTRA_CONN_KEY (mesma lógica do sync e delta)."""
    from cryptography.fernet import Fernet
    chave = (os.getenv("ORQUESTRA_CONN_KEY") or "").strip()
    if not chave:
        raise ValueError(
            "ORQUESTRA_CONN_KEY não configurada no worker — defina no .env/"
            "compose o MESMO valor usado pelo orquestra-api")
    return Fernet(chave.encode()).decrypt(token.encode("ascii")).decode("utf-8")


@dag(
    dag_id=DAG_ID,
    schedule="0 2,14 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=_dt.timedelta(minutes=25),
    tags=["servicenow", "full"],
)
def etl_servicenow_full():

    @task
    def espelho_full() -> list[str]:
        """Full sync — todas as páginas + desativação + migração de histórico."""
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        conn = hook.get_conn()
        cur = conn.cursor()

        # ── config ──────────────────────────────────────────────────────────
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO, "servicenow_proxy"])
        cfg = dict(cur.fetchall())
        if (cfg.get(K_HABILITADO) or "").strip() != "1":
            log.info("full: servicenow_habilitado=0 — skip")
            cur.close()
            conn.close()
            return []

        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        senha_enc = (cfg.get(K_SENHA) or "").strip()
        senha = _decifrar(senha_enc)

        # ── migração única de etl_chamado_sync → etl_chamado_ciclo ─────────
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_chamado_ciclo WHERE modo='full'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO dbo.etl_chamado_ciclo "
                "  (modo, iniciado_em, terminado_em, status, "
                "   qtd_chamados, disparado_por, erro) "
                "SELECT 'full', iniciado_em, terminado_em, status, "
                "  ISNULL(qtd_incident,0)+ISNULL(qtd_ritm,0)+"
                "  ISNULL(qtd_task,0)+ISNULL(qtd_change,0), "
                "  disparado_por, erro "
                "FROM dbo.etl_chamado_sync "
                "WHERE iniciado_em IS NOT NULL")
            conn.commit()
            log.info("full: histórico migrado de etl_chamado_sync")

        # ── abre ciclo ───────────────────────────────────────────────────────
        inicio = _dt.datetime.now()   # horário local — compatível com GETDATE() do SQL Server
        cur.execute(
            "INSERT INTO dbo.etl_chamado_ciclo "
            "  (modo, iniciado_em, status, disparado_por) "
            "VALUES (%s,%s,%s,%s)",
            ("full", inicio, "ERRO", DAG_ID))
        conn.commit()
        cur.execute(
            "SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE disparado_por=%s",
            [DAG_ID])
        ciclo_id = cur.fetchone()[0]

        grupos = grupos_ativos(hook)
        if not grupos:
            log.warning("full: nenhum grupo ativo em etl_servicenow_grupo — skip")
            cur.close()
            conn.close()
            return []
        query_grupo = query_do_grupo(grupos)
        log.info("full: grupos = %s", grupos)

        proxy = proxy_da_config(cfg)
        log.info("full: proxy = %s", proxy or "(direto)")

        import httpx
        sys_ids_vistos: list[str] = []
        qtd_total = 0
        qtd_desativ = 0
        erro_msg = None

        try:
            with httpx.Client(auth=(usuario, senha), timeout=30,
                              proxy=proxy,
                              headers={"Accept": "application/json"}) as cli:
                for tabela, tipo in TABELAS:
                    pagina = 0
                    while pagina < MAX_PAGINAS:
                        offset = pagina * PAGINA
                        url = (f"{url_base}/api/now/table/{tabela}"
                               f"?sysparm_query={query_grupo}"
                               f"&sysparm_fields={CAMPOS}"
                               f"&sysparm_display_value=all"
                               f"&sysparm_limit={PAGINA}&sysparm_offset={offset}")
                        try:
                            resp = cli.get(url)
                            resp.raise_for_status()
                        except Exception as e:
                            log.warning("full: %s pagina %d erro: %s",
                                        tabela, pagina, e)
                            break
                        registros = resp.json().get("result", [])
                        if not registros:
                            break
                        sql_u = upsert_sql()
                        for reg in registros:
                            linha = normalizar(reg, tabela, tipo, url_base)
                            cur.execute(sql_u, upsert_params(linha))
                            sys_ids_vistos.append(linha["sys_id"])
                        conn.commit()
                        qtd_total += len(registros)
                        if len(registros) < PAGINA:
                            break
                        pagina += 1

            # ── desativação: chamados que não apareceram no full ────────────
            # sync_em < inicio significa que não foram atualizados neste ciclo
            cur.execute(
                "UPDATE dbo.etl_chamado SET ativo=0 "
                "WHERE ativo=1 AND sync_em < %s",
                [inicio])
            qtd_desativ = cur.rowcount
            conn.commit()
            log.info("full: %d desativados", qtd_desativ)

        except Exception as e:
            erro_msg = str(e)[:1000]
            log.error("full: erro: %s", erro_msg)
            qtd_desativ = 0

        status = "ERRO" if erro_msg else "OK"
        cur.execute(
            "UPDATE dbo.etl_chamado_ciclo "
            "SET terminado_em=%s, status=%s, qtd_chamados=%s, "
            "    qtd_desativados=%s, erro=%s "
            "WHERE id=%s",
            (_dt.datetime.now(), status, qtd_total,
             qtd_desativ, erro_msg, ciclo_id))
        conn.commit()
        cur.close()
        conn.close()
        return sys_ids_vistos

    @task
    def notas_e_anexos_full(sys_ids: list[str]) -> dict:
        """Varre TODOS os chamados ativos — cobertura de chamados antigos."""
        if not sys_ids:
            return {"qtd_notas": 0, "qtd_anexos": 0}

        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        conn = hook.get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO, "servicenow_proxy"])
        cfg = dict(cur.fetchall())
        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        senha = _decifrar(cfg.get(K_SENHA) or "")
        proxy = proxy_da_config(cfg)

        # No full, usamos todos os sys_ids ativos (não só os tocados no ciclo)
        cur.execute("SELECT sys_id FROM dbo.etl_chamado WHERE ativo=1")
        todos = [r[0] for r in cur.fetchall()]

        import httpx
        qtd_notas = qtd_anexos = 0
        sql_nota = upsert_nota_sql()
        sql_anx = upsert_anexo_sql()

        with httpx.Client(auth=(usuario, senha), timeout=30,
                          proxy=proxy,
                          headers={"Accept": "application/json"}) as cli:
            for sys_id in todos:
                for nota in buscar_notas(cli, url_base, sys_id):
                    cur.execute(sql_nota, upsert_nota_params(nota))
                    qtd_notas += 1
                anexos = buscar_anexos(cli, url_base, sys_id)
                for anx in anexos:
                    cur.execute(sql_anx, upsert_anexo_params(anx))
                    qtd_anexos += 1
                if anexos:
                    cur.execute(
                        "UPDATE dbo.etl_chamado SET tem_anexo=1 "
                        "WHERE sys_id=%s AND tem_anexo=0", [sys_id])
                conn.commit()

        # Atualiza qtd_notas/qtd_anexos no ciclo mais recente do full
        cur.execute(
            "UPDATE dbo.etl_chamado_ciclo "
            "SET qtd_notas=%s, qtd_anexos=%s "
            "WHERE id=(SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE modo='full')",
            [qtd_notas, qtd_anexos])
        conn.commit()
        cur.close()
        conn.close()
        log.info("notas_e_anexos_full: %d notas, %d anexos em %d chamados",
                 qtd_notas, qtd_anexos, len(todos))
        return {"qtd_notas": qtd_notas, "qtd_anexos": qtd_anexos}

    @task
    def snapshot(_contagens: dict) -> int:
        """Captura snapshot de indicadores após o full."""
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        snap_id = capturar_snapshot(hook)
        log.info("snapshot full: id=%d", snap_id)
        return snap_id

    sys_ids = espelho_full()
    contagens = notas_e_anexos_full(sys_ids)
    snapshot(contagens)


etl_servicenow_full()
