"""api/services/lineage_isx.py — lineage automático via ISX (spec docs/spec-lineage-isx.md, F2).

O engine (`dags/utils/isx_engine.py`) é puro e recebe transportes; este módulo é o
lado da API: os TRANSPORTES reais (API REST do DataStage por httpx, SSH/SFTP por
paramiko com as mesmas variáveis DS_SSH_* do Console e dos Utilitários) e a
PERSISTÊNCIA (pyodbc, placeholders `?`): cabeçalho em `etl_ds_job_isx` e uma linha
por stage em `etl_job_lineage` com `extraction_method = 'isx_auto'`.

Tudo aqui é síncrono e bloqueante — o router roda no executor dedicado. Nenhuma
função conhece host, usuário ou senha: vêm do ambiente pelo `ConfigISX` e pela
`credencial('datastage')` dos Utilitários. `interno` das ISXError vai ao log, nunca
à resposta.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import sys
import time
import urllib.parse
from contextlib import contextmanager

from fastapi import HTTPException

from db import get_db_conn
from services import ssh_arquivos as arq

log = logging.getLogger("orquestra-api")

METODO = "isx_auto"
# Larguras das colunas (schema_prod_dev.sql / migration 106). VARCHAR conta bytes
# da collation; NVARCHAR conta unidades UTF-16 — `cortar_utf16` serve aos dois
# (corta pelo pior caso).
_L = {
    "object_type": 100, "object_name": 500, "stage_name": 200, "stage_type_raw": 100,
    "database_name": 200, "file_path": 500, "stage_internal_id": 20,
    "ds_project": 50, "ds_folder_path": 500, "ds_job_type": 20, "ds_last_modified": 40,
    "job_description": 2000, "erro": 500, "extracted_by": 100,
}
_VARCHAR_SEM_ACENTO = ("stage_name", "database_name", "file_path")


# ── engine e configuração ─────────────────────────────────────────────────────

def engine():
    """Importa o engine do pacote das DAGs (o container da API monta `dags/`)."""
    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    try:
        from utils import isx_engine  # type: ignore
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Engine ISX não disponível: {e}")
    return isx_engine


def config():
    """`ConfigISX` do ambiente; 503 nomeando as variáveis que faltam."""
    E = engine()
    cfg = E.ConfigISX.do_ambiente()
    faltas = cfg.faltas()
    if faltas:
        raise E.ISXError(
            503, "Lineage ISX não configurado nesta instância da API — defina "
                 + ", ".join(faltas) + " no ambiente.")
    # `usuario:senha@host` na URL iria em claro para o log do httpx (que imprime a
    # URL de cada pedido) e nem seria usado (o `auth=` explícito vence).
    if urllib.parse.urlsplit(cfg.api_url).username is not None:
        raise E.ISXError(503, "DS_API_URL não pode conter usuário:senha — use DS_API_USER e DS_API_PASSWORD.")
    return cfg


def aviso_arranque() -> None:
    """Uma vez, no import do router: diz o que falta e avisa se o TLS da API REST
    está desligado (spec §3). Nunca levanta."""
    try:
        E = engine()
        cfg = E.ConfigISX.do_ambiente()
        faltas = cfg.faltas()
        if faltas:
            log.info("Lineage ISX: desligado nesta instância (faltam %s).", ", ".join(faltas))
            return
        if cfg.api_verify is False:
            log.warning("Lineage ISX: DS_API_VERIFY_SSL=false — certificado da API REST do DataStage "
                        "NÃO é verificado; prefira um caminho de CA.")
        if not (os.getenv("DS_SSH_KNOWN_HOSTS") or "").strip():
            log.warning("Lineage ISX: DS_SSH_KNOWN_HOSTS ausente — o SSH aceita qualquer host key "
                        "(AutoAddPolicy) e o canal transporta o .isx com credenciais de conexão; "
                        "defina o known_hosts do servidor do DataStage.")
    except Exception:  # noqa: BLE001 — aviso é best-effort
        log.info("Lineage ISX: engine indisponível nesta instância.", exc_info=True)


# ── transportes ──────────────────────────────────────────────────────────────

@contextmanager
def rest_transport(cfg):
    """`rest(caminho) -> dict | None` sobre httpx: GET `DS_API_URL/<caminho>` com Basic
    auth. 404 → None; credencial recusada / erro / não-JSON → ISXError 502 (detalhe
    só no `interno`). O caminho já vem validado pelo engine (`folders/…`,
    `jobdesigns/…`); aqui a conferência é repetida por defesa."""
    import httpx  # import tardio: só existe em runtime, não nos testes

    E = engine()
    # trust_env=False: chamada DIRETA ao DataStage (intranet) — nunca pelo proxy
    # corporativo de HTTP(S)_PROXY, que receberia o Basic em claro (spec §8.13).
    cliente = httpx.Client(auth=(cfg.api_user or "", cfg.api_password or ""),
                           verify=cfg.api_verify, timeout=httpx.Timeout(15.0, connect=10.0),
                           trust_env=False)

    def rest(caminho: str):
        if E._caminho_api_valido(caminho) is None:  # noqa: SLF001
            raise E.ISXError(422, "Caminho inválido para a API REST do DataStage.", interno=repr(caminho)[:200])
        url = f"{cfg.api_url}/{caminho}"
        try:
            r = cliente.get(url)
        except httpx.HTTPError as e:
            raise E.ISXError(
                502, "A API REST do DataStage não respondeu — detalhe registrado no log da API.",
                interno=f"{type(e).__name__}: {e}"[:300]) from e
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            raise E.ISXError(
                502, "A API REST do DataStage recusou a credencial (DS_API_USER/DS_API_PASSWORD).",
                interno=f"HTTP {r.status_code} em {caminho}")
        if r.status_code >= 400:
            raise E.ISXError(
                502, "A API REST do DataStage respondeu erro — detalhe registrado no log da API.",
                interno=f"HTTP {r.status_code} em {caminho}: {r.text[:300]!r}")
        try:
            dados = r.json()
        except ValueError as e:
            raise E.ISXError(
                502, "A API REST do DataStage devolveu algo que não é JSON.",
                interno=f"{caminho}: {r.text[:200]!r}") from e
        return dados if isinstance(dados, dict) else None

    try:
        yield rest
    finally:
        cliente.close()


@contextmanager
def ssh_transport():
    """`ssh() -> (executar, sftp)` sobre paramiko, com as variáveis DS_SSH_* (a
    `credencial('datastage')` dos Utilitários e o mesmo DS_SSH_KNOWN_HOSTS).

    `allow_agent=False` e `look_for_keys=False`: com senha, o paramiko tentaria o
    agente/chaves do container e falharia com "Authentication failed" (medido no
    servidor do DataStage; `key_filename` explícito continua valendo).
    O canal SFTP é aberto à mão com timeout (home em NFS pendurado seguraria a
    thread para sempre — mesmo cuidado de `conexao_sftp`)."""
    E = engine()
    try:
        cred = arq.credencial("datastage")
        known = arq._known_hosts()  # noqa: SLF001 — mesma política do Console/Utilitários
    except arq.ArquivoError as e:
        raise E.ISXError(e.status, e.detail, interno=e.interno) from e
    import paramiko  # import tardio

    client = paramiko.SSHClient()
    if known:
        client.load_host_keys(known)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=cred.host, port=cred.port, username=cred.user,
            password=cred.password, key_filename=cred.key_file,
            timeout=10, banner_timeout=15, auth_timeout=15,
            allow_agent=False, look_for_keys=False,
        )
        transporte = client.get_transport()
        transporte.set_keepalive(15)
        canal = transporte.open_session(timeout=10)
        canal.settimeout(60)
        canal.invoke_subsystem("sftp")
        sftp = paramiko.SFTPClient(canal)
    except Exception as e:  # noqa: BLE001 — paramiko lança de tudo
        client.close()
        log.warning("Lineage ISX: falha ao conectar por SSH em %s:%s: %r", cred.host, cred.port, e)
        raise E.ISXError(
            502, "Falha ao conectar ao servidor do DataStage por SSH — detalhe registrado no log da API.",
            interno=f"{cred.host}:{cred.port}: {e!r}"[:300]) from e

    def executar(cmd: str, teto: int):
        """rc, stdout, stderr. Lê a saída ANTES do exit status, com o timeout do canal:
        `recv_exit_status` sem isso esperaria um istool pendurado para sempre."""
        try:
            _, out, err = client.exec_command(cmd, timeout=teto)
            saida = out.read().decode(errors="replace")
            erro = err.read().decode(errors="replace")
            rc = out.channel.recv_exit_status()
        except socket.timeout as e:
            raise E.ISXError(504, f"O istool não terminou em {teto} s.", interno="timeout do canal SSH") from e
        return rc, saida, erro

    try:
        yield executar, sftp
    finally:
        try:
            sftp.close()
        finally:
            client.close()


# ── banco: leitura ───────────────────────────────────────────────────────────

@contextmanager
def banco():
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        yield conn, cur
    finally:
        for x in (cur, conn):
            try:
                x.close()
            except Exception:  # noqa: BLE001
                pass


def exigir_tabela(cur) -> None:
    cur.execute("SELECT OBJECT_ID('dbo.etl_ds_job_isx', 'U')")
    row = cur.fetchone()
    if not row or row[0] is None:
        raise HTTPException(
            status_code=503,
            detail="Lineage ISX indisponível: migration 106 pendente (tabela etl_ds_job_isx ausente).")


def job_do_pipeline(cur, pipeline: str, job: str) -> dict | None:
    """Projeto DataStage e tipo do job pelo pipeline — a regra do usuário: só há
    lineage ISX para job mapeado num pipeline."""
    cur.execute(
        "SELECT p.project_name, j.job_type, j.pipeline_name, j.job_name FROM dbo.etl_pipeline_job j "
        "JOIN dbo.etl_pipeline p ON p.pipeline_name = j.pipeline_name "
        "WHERE j.pipeline_name = ? AND j.job_name = ?", [pipeline, job])
    row = cur.fetchone()
    if not row:
        return None
    # A colação do SQL Server é CI; o DataStage distingue caixa: daqui saem os nomes
    # na grafia cadastrada (gotcha da PR #269).
    return {"ds_project": str(row[0] or "").strip(), "job_type": row[1],
            "pipeline_name": str(row[2] or pipeline), "job_name": str(row[3] or job)}


_COLS_CAB = ("id", "pipeline_name", "job_name", "ds_project", "ds_folder_path", "ds_job_type",
             "ds_last_modified", "job_description", "job_long_description", "parameters_json",
             "flow_json", "children_json", "nao_reconhecidos_json", "isx_sha256", "isx_bytes",
             "status", "erro", "extracted_at", "extracted_by", "duracao_ms")


def cabecalho(cur, pipeline: str, job: str) -> dict | None:
    cur.execute(
        f"SELECT {', '.join(_COLS_CAB)} FROM dbo.etl_ds_job_isx "
        "WHERE pipeline_name = ? AND job_name = ?", [pipeline, job])
    row = cur.fetchone()
    return dict(zip(_COLS_CAB, row)) if row else None


def conta_linhas(cur, pipeline: str, job: str) -> int:
    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_job_lineage l WHERE l.pipeline_name = ? AND l.job_name = ? "
        "AND l.extraction_method = 'isx_auto'", [pipeline, job])
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def mapa_tipos(cur) -> dict:
    """Linhas de `etl_stage_type_map` por tipo. A coluna-chave é `type_raw` ou
    `stage_type` conforme o ambiente (migration 106); sem a tabela, mapa vazio e o
    engine usa os conjuntos embutidos."""
    cur.execute("SELECT COL_LENGTH('dbo.etl_stage_type_map', 'type_raw'), "
                "COL_LENGTH('dbo.etl_stage_type_map', 'stage_type')")
    row = cur.fetchone()
    chave = "type_raw" if row and row[0] is not None else ("stage_type" if row and row[1] is not None else None)
    if not chave:
        return {}
    cur.execute(f"SELECT {chave}, type_label, type_category, role_hint FROM dbo.etl_stage_type_map")
    return {r[0]: {"type_label": r[1], "type_category": r[2], "role_hint": r[3]}
            for r in cur.fetchall() if r and r[0]}


# ── DataStage: localizar e extrair (rodam no executor) ───────────────────────

def localizar(cfg, projeto: str, job: str, pasta_conhecida: str | None) -> dict | None:
    """Metadados do job na API REST: {api_id, folder_path, job_type, last_modified,
    description, long_description} ou None. Com a pasta já conhecida (cabeçalho),
    confere direto o `jobdesigns/…`; se o job saiu de lá, cai na busca em largura."""
    E = engine()
    with rest_transport(cfg) as rest:
        if pasta_conhecida:
            try:
                api_id = E.api_id_de(cfg.engine, projeto, pasta_conhecida, job)
                meta = E.checar_modificado(rest, api_id)
                # a API real pode omitir folderPath no detalhe: a pasta conhecida continua valendo
                return {"api_id": api_id, **meta, "folder_path": meta.get("folder_path") or pasta_conhecida}
            except E.ISXError as e:
                if e.status not in (404, 422):
                    raise
        achado = E.localizar_job(rest, cfg.engine, projeto, job)
        if achado is None:
            return None
        meta = E.checar_modificado(rest, achado["api_id"])
        return {**achado, **{k: v for k, v in meta.items() if v}}


def extrair(cfg, projeto: str, job: str, cab: dict | None, tem_linhas: bool, forcar: bool, mapa: dict):
    """(meta, resultado_do_parse | None, cache_hit). Cache: cabeçalho `ok`, linhas
    presentes e `ds_last_modified` igual ao da API — sem tocar o SSH."""
    E = engine()
    meta = localizar(cfg, projeto, job, (cab or {}).get("ds_folder_path"))
    if meta is None:
        raise E.ISXError(404, f"Job {job} não encontrado no projeto {projeto} do DataStage "
                              "(a API REST não o acha em nenhuma pasta de Jobs).", resultado="nao_encontrado")
    lm = str(meta.get("last_modified") or "")
    if (not forcar and cab and cab.get("status") == "ok" and tem_linhas
            and lm and str(cab.get("ds_last_modified") or "") == lm):
        return meta, None, True
    try:
        dados, caminho = E.exportar_job(ssh_transport, cfg, cfg.engine, projeto, meta["folder_path"], job, meta["job_type"])
        r = E.parse_isx(dados, mapa, job=job)
        if r.get("job_name") and r["job_name"].lower() != job.lower():
            raise E.ISXError(422, f"O .isx exportado é do job {r['job_name']}, não de {job} — confira o nome no DataStage.")
    except E.ISXError as e:
        e.meta = meta  # o cabeçalho da tentativa registra pasta/tipo/timestamp já conhecidos
        raise
    r["caminho_istool"] = caminho
    return meta, r, False


# ── banco: gravação ──────────────────────────────────────────────────────────

def _c(valor, campo: str):
    """Corta pelo limite da coluna; None e '' viram None."""
    if valor is None:
        return None
    s = str(valor)
    if s == "":
        return None
    return arq.cortar_utf16(s, _L[campo])


def _js(v) -> str | None:
    return json.dumps(v, ensure_ascii=False) if v else None


def _object_name(s: dict) -> str:
    """O que a tela lista como "objeto": a tabela-alvo quando o conector a declara,
    o arquivo quando é stage de arquivo, senão o nome do stage."""
    if s.get("sql_tag") == "TableName" and s.get("sql_expression"):
        return s["sql_expression"].strip().splitlines()[0]
    if s.get("classe") == "arquivo" and s.get("file_path"):
        return s["file_path"]
    return s.get("stage_name") or "?"


def _linhas(pipeline: str, job: str, resultado: dict) -> tuple[list[list], list[dict]]:
    """Parâmetros do INSERT por stage + avisos de coluna VARCHAR com acento
    (a collation pode gravar '?': fica registrado em `nao_reconhecidos_json`)."""
    nao = list(resultado.get("nao_reconhecidos") or [])
    linhas = []
    for s in resultado.get("stages") or []:
        for campo in _VARCHAR_SEM_ACENTO:
            v = s.get(campo)
            if v and not str(v).isascii():
                nao.append({"stage": s.get("stage_name") or "", "stage_type": s.get("stage_type_raw") or "",
                            "motivo": f"{campo} com caractere fora de ASCII: a coluna VARCHAR pode gravar '?'"})
        linhas.append([
            pipeline, job, s.get("direction") or "transformacao",
            _c(s.get("object_type"), "object_type"), _c(_object_name(s), "object_name"),
            _c(s.get("stage_name"), "stage_name"), _c(s.get("stage_type_raw"), "stage_type_raw"),
            _c(s.get("database_name"), "database_name"), s.get("sql_expression") or None,
            _c(s.get("file_path"), "file_path"), METODO,
            _js(s.get("output_columns")), _js(s.get("input_columns")),
            s.get("apt_code") or None, _js(s.get("expressions")), _c(s.get("internal_id"), "stage_internal_id"),
        ])
    return linhas, nao


_SQL_INSERT_LINHA = (
    "INSERT INTO dbo.etl_job_lineage (pipeline_name, job_name, direction, object_type, object_name, "
    "stage_name, stage_type_raw, database_name, sql_expression, file_path, extraction_method, "
    "columns_json, input_columns_json, apt_code, expressions_json, stage_internal_id, "
    "extracted_at, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE(), GETDATE())"
)

_CAMPOS_CAB = ("ds_project", "ds_folder_path", "ds_job_type", "ds_last_modified", "job_description",
               "job_long_description", "parameters_json", "flow_json", "children_json",
               "nao_reconhecidos_json", "isx_sha256", "isx_bytes", "status", "erro", "extracted_by", "duracao_ms")


def _cabecalho_upsert(cur, pipeline: str, job: str, valores: dict) -> None:
    """UPDATE dos campos informados; sem linha, INSERT (UNIQUE em (pipeline, job))."""
    campos = [c for c in _CAMPOS_CAB if c in valores]
    cur.execute(
        "UPDATE dbo.etl_ds_job_isx SET " + ", ".join(f"{c} = ?" for c in campos)
        + ", extracted_at = GETDATE() WHERE pipeline_name = ? AND job_name = ?",
        [valores[c] for c in campos] + [pipeline, job])
    if int(cur.rowcount or 0) > 0:
        return
    cur.execute(
        "INSERT INTO dbo.etl_ds_job_isx (pipeline_name, job_name, " + ", ".join(campos)
        + ", extracted_at) VALUES (?, ?, " + ", ".join("?" for _ in campos) + ", GETDATE())",
        [pipeline, job] + [valores[c] for c in campos])


def gravar(conn, cur, *, pipeline: str, job: str, projeto: str, meta: dict, resultado: dict,
           usuario: str, duracao_ms: int) -> int:
    """Uma transação: DELETE das linhas `isx_auto` do job + INSERT por stage + upsert do
    cabeçalho. Linhas `manual`/`dsx_auto` do mesmo job ficam. Devolve as linhas gravadas."""
    linhas, nao = _linhas(pipeline, job, resultado)
    valores = {
        "ds_project": _c(projeto, "ds_project"),
        "ds_folder_path": _c(meta.get("folder_path"), "ds_folder_path"),
        "ds_job_type": _c(resultado.get("job_type") or meta.get("job_type"), "ds_job_type"),
        "ds_last_modified": _c(meta.get("last_modified"), "ds_last_modified"),
        "job_description": _c(resultado.get("job_description") or meta.get("description"), "job_description"),
        "job_long_description": (resultado.get("job_long_description") or meta.get("long_description") or None),
        "parameters_json": _js(resultado.get("parameters")),
        "flow_json": _js(resultado.get("flow")),
        "children_json": _js(resultado.get("children")),
        "nao_reconhecidos_json": _js(nao),
        "isx_sha256": resultado.get("isx_sha256"),
        "isx_bytes": resultado.get("isx_bytes"),
        "status": "ok", "erro": None,
        "extracted_by": _c(usuario, "extracted_by"), "duracao_ms": int(duracao_ms),
    }
    E = engine()
    try:
        cur.execute(
            "DELETE FROM dbo.etl_job_lineage WHERE pipeline_name = ? AND job_name = ? "
            "AND extraction_method = 'isx_auto'", [pipeline, job])
        # Duas extrações do MESMO job ao mesmo tempo (2 workers × 2 threads, sem lock
        # em processo): sob RCSI o DELETE de uma não vê as linhas não commitadas da
        # outra e o job ficaria com as linhas dobradas. O applock (na transação que o
        # DELETE já abriu) serializa; sem esperar (timeout 0): a perdedora responde 409.
        cur.execute(
            "DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
            "@LockOwner = 'Transaction', @LockTimeout = 0; SELECT @r", [_recurso_lock(pipeline, job)])
        row = cur.fetchone()
        if row is None or int(row[0] or 0) < 0:
            raise E.ISXError(409, f"Outra extração do job {job} está em andamento — tente de novo em instantes.",
                             resultado="ocupado")
        # com o lock em mãos, o DELETE de novo enxerga o que a outra extração commitou
        cur.execute(
            "DELETE FROM dbo.etl_job_lineage WHERE pipeline_name = ? AND job_name = ? "
            "AND extraction_method = 'isx_auto'", [pipeline, job])
        for linha in linhas:
            cur.execute(_SQL_INSERT_LINHA, linha)
        _cabecalho_upsert(cur, pipeline, job, valores)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    return len(linhas)


def _recurso_lock(pipeline: str, job: str) -> str:
    """Nome do applock (≤ 255): hash da chave em caixa baixa (a colação é CI)."""
    return "isx:" + hashlib.sha1(f"{pipeline}\0{job}".casefold().encode("utf-8")).hexdigest()


def registrar_erro(conn, cur, *, pipeline: str, job: str, projeto: str, meta: dict | None,
                   frase: str, usuario: str, duracao_ms: int) -> None:
    """O cabeçalho registra a TENTATIVA (status `erro` + frase pública); as linhas da
    última extração boa ficam. Best-effort: falha aqui vai ao log, não à resposta."""
    valores = {"ds_project": _c(projeto, "ds_project"), "status": "erro", "erro": _c(frase, "erro"),
               "extracted_by": _c(usuario, "extracted_by"), "duracao_ms": int(duracao_ms)}
    if meta:
        valores.update({
            "ds_folder_path": _c(meta.get("folder_path"), "ds_folder_path"),
            "ds_job_type": _c(meta.get("job_type"), "ds_job_type"),
            "ds_last_modified": _c(meta.get("last_modified"), "ds_last_modified"),
        })
    try:
        _cabecalho_upsert(cur, pipeline, job, valores)
        conn.commit()
    except Exception:  # noqa: BLE001
        log.warning("Lineage ISX: falha ao registrar o erro de %s/%s", pipeline, job, exc_info=True)


# ── banco: resposta ──────────────────────────────────────────────────────────

def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _json_ou(v, padrao):
    if not v:
        return padrao
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return padrao


_COLS_LINHA = ("direction", "object_type", "object_name", "stage_name", "stage_type_raw", "database_name",
               "sql_expression", "file_path", "columns_json", "input_columns_json", "apt_code",
               "expressions_json", "stage_internal_id", "extracted_at")


def linhas_isx(cur, pipeline: str, job: str) -> list[dict]:
    cur.execute(
        f"SELECT {', '.join(_COLS_LINHA)} FROM dbo.etl_job_lineage "
        "WHERE pipeline_name = ? AND job_name = ? AND extraction_method = 'isx_auto' "
        "ORDER BY CASE direction WHEN 'origem' THEN 1 WHEN 'transformacao' THEN 2 WHEN 'destino' THEN 3 ELSE 9 END, id",
        [pipeline, job])
    saida = []
    for row in cur.fetchall():
        d = dict(zip(_COLS_LINHA, row))
        saida.append({
            "direction": d["direction"], "object_type": d["object_type"], "object_name": d["object_name"],
            "stage_name": d["stage_name"], "stage_type_raw": d["stage_type_raw"],
            "stage_internal_id": d["stage_internal_id"], "database_name": d["database_name"],
            "sql_expression": d["sql_expression"], "file_path": d["file_path"],
            "output_columns": _json_ou(d["columns_json"], []), "input_columns": _json_ou(d["input_columns_json"], []),
            "apt_code": d["apt_code"], "expressions": _json_ou(d["expressions_json"], []),
            "extracted_at": _fmt_dt(d["extracted_at"]),
        })
    return saida


def montar(cur, pipeline: str, job: str) -> dict | None:
    """Cabeçalho + stages do job, do banco. None sem cabeçalho."""
    cab = cabecalho(cur, pipeline, job)
    if not cab:
        return None
    return {
        "pipeline_name": pipeline, "job_name": job,
        "ds_project": cab["ds_project"], "ds_folder_path": cab["ds_folder_path"],
        "job_type": cab["ds_job_type"], "ds_last_modified": cab["ds_last_modified"],
        "job_description": cab["job_description"], "job_long_description": cab["job_long_description"],
        "status": cab["status"], "erro": cab["erro"],
        "extracted_at": _fmt_dt(cab["extracted_at"]), "extracted_by": cab["extracted_by"],
        "duracao_ms": cab["duracao_ms"], "isx_sha256": cab["isx_sha256"], "isx_bytes": cab["isx_bytes"],
        "parameters": _json_ou(cab["parameters_json"], []),
        "flow": _json_ou(cab["flow_json"], []),
        "children": _json_ou(cab["children_json"], []),
        "nao_reconhecidos": _json_ou(cab["nao_reconhecidos_json"], []),
        "stages": linhas_isx(cur, pipeline, job),
    }


def estado_pipeline(cur, pipeline: str) -> dict | None:
    """Um item por job do pipeline com o estado ISX (para a lista da aba)."""
    cur.execute("SELECT project_name FROM dbo.etl_pipeline WHERE pipeline_name = ?", [pipeline])
    row = cur.fetchone()
    if not row:
        return None
    projeto = str(row[0] or "").strip()
    cur.execute(
        "SELECT j.job_name, j.execution_order, j.job_type, c.status, c.ds_job_type, c.ds_last_modified, "
        "c.extracted_at, c.extracted_by, c.erro, c.ds_folder_path, "
        "(SELECT COUNT(*) FROM dbo.etl_job_lineage l WHERE l.pipeline_name = j.pipeline_name "
        " AND l.job_name = j.job_name AND l.extraction_method = 'isx_auto') AS linhas_isx "
        "FROM dbo.etl_pipeline_job j "
        "LEFT JOIN dbo.etl_ds_job_isx c ON c.pipeline_name = j.pipeline_name AND c.job_name = j.job_name "
        "WHERE j.pipeline_name = ? ORDER BY j.execution_order, j.job_name", [pipeline])
    jobs = []
    for r in cur.fetchall():
        jobs.append({
            "job_name": r[0], "execution_order": int(r[1] or 0), "job_type": r[2],
            "isx": None if r[3] is None else {
                "status": r[3], "ds_job_type": r[4], "ds_last_modified": r[5],
                "extracted_at": _fmt_dt(r[6]), "extracted_by": r[7], "erro": r[8],
                "ds_folder_path": r[9], "linhas": int(r[10] or 0),
            },
        })
    return {"pipeline_name": pipeline, "ds_project": projeto, "jobs": jobs}


def ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)
