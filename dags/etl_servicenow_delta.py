"""dags/etl_servicenow_delta.py — sync incremental a cada 5 min.

Fluxo: espelho_delta → notas_e_anexos → snapshot → triagem
max_active_runs=1 descarta o próximo disparo se o anterior ainda roda.

Credencial: lida de etl_app_config (senha_enc decifrada com ORQUESTRA_CONN_KEY),
mesma lógica de etl_servicenow_sync.py — sem import de api/services.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os

import pendulum
from airflow.decorators import dag, task
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from utils.frescor_modulo import conferir
from utils.servicenow_sync import (
    CAMPOS, MAX_PAGINAS, MSSQL_CONN_ID, PAGINA, TABELAS,
    buscar_anexos, buscar_notas,
    capturar_snapshot,
    grupos_ativos,
    normalizar, proxy_da_config,
    query_delta, ultimo_delta_em,
    upsert_anexo_params, upsert_anexo_sql,
    upsert_nota_params, upsert_nota_sql,
    upsert_params, upsert_sql,
)

log = logging.getLogger("orquestra")

K_URL, K_USUARIO = "servicenow_url", "servicenow_usuario"
K_SENHA, K_HABILITADO = "servicenow_senha_enc", "servicenow_habilitado"

DAG_ID = "etl_servicenow_delta"


def _decifrar(token: str) -> str:
    """Decifra senha com Fernet+ORQUESTRA_CONN_KEY (mesma lógica do sync full)."""
    from cryptography.fernet import Fernet
    chave = (os.getenv("ORQUESTRA_CONN_KEY") or "").strip()
    if not chave:
        raise ValueError(
            "ORQUESTRA_CONN_KEY não configurada no worker — defina no .env/"
            "compose o MESMO valor usado pelo orquestra-api")
    return Fernet(chave.encode()).decrypt(token.encode("ascii")).decode("utf-8")


@dag(
    dag_id=DAG_ID,
    schedule="*/5 * * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=_dt.timedelta(minutes=8),
    tags=["servicenow", "delta"],
)
def etl_servicenow_delta():

    @task
    def espelho_delta() -> list[str]:
        """Upsert incremental — retorna sys_ids tocados."""
        for aviso in conferir():
            log.warning("frescor: %s", aviso)
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
            log.info("delta: servicenow_habilitado=0 — skip")
            return []

        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        senha_enc = (cfg.get(K_SENHA) or "").strip()
        senha = _decifrar(senha_enc)

        grupos = grupos_ativos(hook)
        if not grupos:
            log.warning("delta: nenhum grupo ativo em etl_servicenow_grupo — skip")
            return []

        desde = ultimo_delta_em(hook)
        log.info("delta: ponto de corte = %s, grupos = %s", desde, grupos)

        proxy = proxy_da_config(cfg)
        log.info("delta: proxy = %s", proxy or "(direto)")

        # ── abre ciclo ───────────────────────────────────────────────────────
        inicio = _dt.datetime.now()   # horário local — compatível com GETDATE() do SQL Server
        cur.execute(
            "INSERT INTO dbo.etl_chamado_ciclo "
            "  (modo, iniciado_em, status, disparado_por) "
            "VALUES (%s,%s,%s,%s)",
            ("delta", inicio, "ERRO", DAG_ID))
        conn.commit()
        cur.execute(
            "SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE disparado_por=%s",
            [DAG_ID])
        ciclo_id = cur.fetchone()[0]

        import httpx
        sys_ids_tocados: list[str] = []
        qtd_total = 0
        erro_msg = None

        try:
            with httpx.Client(auth=(usuario, senha), proxy=proxy,
                              timeout=30) as cli:
                query = query_delta(grupos, desde)
                for tabela, tipo in TABELAS:
                    pagina = 0
                    while pagina < MAX_PAGINAS:
                        offset = pagina * PAGINA
                        url = (f"{url_base}/api/now/table/{tabela}"
                               f"?sysparm_query={query}"
                               f"&sysparm_fields={CAMPOS}"
                               f"&sysparm_display_value=all"
                               f"&sysparm_limit={PAGINA}&sysparm_offset={offset}")
                        try:
                            resp = cli.get(url)
                            resp.raise_for_status()
                        except Exception as e:
                            log.warning("delta: %s pagina %d erro: %s",
                                        tabela, pagina, e)
                            break
                        registros = resp.json().get("result", [])
                        if not registros:
                            break
                        sql_upsert = upsert_sql()
                        for reg in registros:
                            linha = normalizar(reg, tabela, tipo, url_base)
                            cur.execute(sql_upsert, upsert_params(linha))
                            sys_ids_tocados.append(linha["sys_id"])
                        conn.commit()
                        qtd_total += len(registros)
                        if len(registros) < PAGINA:
                            break
                        pagina += 1
        except Exception as e:
            erro_msg = str(e)[:1000]
            log.error("delta: erro geral: %s", erro_msg)

        status = "ERRO" if erro_msg else "OK"
        cur.execute(
            "UPDATE dbo.etl_chamado_ciclo "
            "SET terminado_em=%s, status=%s, qtd_chamados=%s, erro=%s "
            "WHERE id=%s",
            (_dt.datetime.now(), status, qtd_total, erro_msg, ciclo_id))
        conn.commit()
        cur.close()
        conn.close()
        return sys_ids_tocados

    @task
    def notas_e_anexos(sys_ids: list[str]) -> dict:
        """Busca notas e anexos dos chamados tocados no delta."""
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

        import httpx
        qtd_notas = qtd_anexos = 0
        sql_nota = upsert_nota_sql()
        sql_anx = upsert_anexo_sql()

        with httpx.Client(auth=(usuario, senha), proxy=proxy, timeout=30) as cli:
            for sys_id in sys_ids:
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

        # Atualiza qtd_notas/qtd_anexos no ciclo mais recente
        cur.execute(
            "UPDATE dbo.etl_chamado_ciclo "
            "SET qtd_notas=%s, qtd_anexos=%s "
            "WHERE id=(SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE modo='delta')",
            [qtd_notas, qtd_anexos])
        conn.commit()
        cur.close()
        conn.close()
        log.info("notas_e_anexos: %d notas, %d anexos", qtd_notas, qtd_anexos)
        return {"qtd_notas": qtd_notas, "qtd_anexos": qtd_anexos}

    @task
    def snapshot(_contagens: dict) -> int:
        """Captura snapshot de indicadores após o delta."""
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        snap_id = capturar_snapshot(hook)
        log.info("snapshot: id=%d", snap_id)
        return snap_id

    @task
    def triagem(_snap_id: int) -> None:
        """Triagem de chamados — comportamento atual sem mudança."""
        log.info("triagem: executando classificação IA")
        # TODO: extrair lógica de triagem para utils/triagem_sync.py
        # e chamar aqui — por ora, stub sem erro para não bloquear o delta.

    sys_ids = espelho_delta()
    contagens = notas_e_anexos(sys_ids)
    snap = snapshot(contagens)
    triagem(snap)


etl_servicenow_delta()
