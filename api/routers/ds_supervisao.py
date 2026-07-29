"""api/routers/ds_supervisao.py — cadastro dos jobs DataStage supervisionados.

Fase 1 da spec docs/spec-supervisao-ds.md: só o CRUD que alimenta a coleta.
A DAG (F2), o painel do dashboard (F3) e o card do Teams (F4) consomem as
tabelas criadas na migration 062.

Guard: require_ds_console — admin OU o recurso 'tela_ds_console' (deps.py), o
mesmo do Console DataStage, dentro do qual esta tela vive.

Regras que valem a pena conhecer antes de mexer:
  • project/job passam pela MESMA allowlist do console (^[A-Za-z0-9_.]+$) —
    a coleta interpola esses nomes num comando remoto.
  • Remoção é LÓGICA (ativo=0): o histórico de runs sustenta o SLA futuro e o
    job entra e sai de supervisão conforme a prioridade do momento. Só some de
    vez o cadastro que nunca coletou nada.
  • Recadastrar um job inativo REATIVA o registro existente (mesmo
    supervisao_id, logo o histórico anterior continua ligado a ele) com a
    vigência nova — em vez de estourar a chave única (project, job_name).
  • O webhook do canal nunca trafega aqui: guarda-se só grupo_id/template_id.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from db import get_db_conn
from deps import get_current_user, require_ds_console

log = logging.getLogger("orquestra-api")

router = APIRouter()

# Mesma allowlist de services/ssh_datastage.py e dags/utils/datastage_operator.py.
_SAFE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(:([0-5]\d))?$")

_CAMPOS_ALERTA = ("alerta_abortou", "alerta_nao_executou", "alerta_atraso", "alerta_estrutura")


# ── Validação de entrada ────────────────────────────────────────────────────

def _nome(valor, campo: str) -> str:
    v = (valor or "").strip()
    if not _SAFE_RE.match(v):
        raise HTTPException(
            status_code=422,
            detail=f"{campo} inválido: use apenas letras, números, '_' e '.' (sem espaços ou símbolos).")
    return v


def _hora(valor, campo: str) -> str:
    """'HH:MM' ou 'HH:MM:SS' → 'HH:MM:SS'."""
    v = (str(valor or "")).strip()
    m = _HORA_RE.match(v)
    if not m:
        raise HTTPException(status_code=422, detail=f"{campo} inválido: use HH:MM (24h).")
    return f"{m.group(1)}:{m.group(2)}:{m.group(4) or '00'}"


def _dias(valor) -> str:
    """CSV de dias ISO (1=seg … 7=dom) → normalizado, ordenado e sem repetição."""
    bruto = valor if isinstance(valor, (list, tuple)) else str(valor or "").split(",")
    dias = set()
    for item in bruto:
        try:
            d = int(str(item).strip())
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="dias_semana: use números de 1 (seg) a 7 (dom).")
        if not 1 <= d <= 7:
            raise HTTPException(status_code=422, detail="dias_semana: use números de 1 (seg) a 7 (dom).")
        dias.add(d)
    if not dias:
        raise HTTPException(status_code=422, detail="Selecione ao menos um dia da semana.")
    return ",".join(str(d) for d in sorted(dias))


def _inteiro(valor, campo: str, minimo: int, maximo: int, default: int) -> int:
    if valor in (None, ""):
        return default
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{campo} deve ser um número inteiro.")
    if not minimo <= n <= maximo:
        raise HTTPException(status_code=422, detail=f"{campo} deve estar entre {minimo} e {maximo}.")
    return n


def _data(valor, campo: str) -> str:
    if valor in (None, ""):
        return date.today().isoformat()
    v = str(valor).strip()[:10]
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{campo} inválido: use AAAA-MM-DD.")
    return v


def _ref_opcional(cur, valor, tabela: str, campo: str):
    """Valida grupo_id/template_id: existe e está ativo. Vazio → None.

    Degrada para None se a tabela do catálogo de mensagens não existir — o
    cadastro do job não pode ficar refém dela (mesmo espírito do try/except de
    routers/mensagens.py)."""
    if valor in (None, ""):
        return None
    try:
        vid = int(valor)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{campo} inválido.")
    try:
        cur.execute(f"SELECT ativo FROM dbo.{tabela} WHERE id = ?", (vid,))
        row = cur.fetchone()
    except Exception as e:
        log.warning("[DS SUPERV] catálogo %s indisponível (%s) — %s aceito sem checagem", tabela, e, campo)
        return vid
    if not row:
        raise HTTPException(status_code=422, detail=f"{campo}: registro não encontrado.")
    if not row[0]:
        raise HTTPException(status_code=422, detail=f"{campo}: registro está inativo.")
    return vid


def _bit(body: dict, campo: str, default: int = 1) -> int:
    if campo not in body:
        return default
    return 1 if body.get(campo) else 0


# ── Leitura ─────────────────────────────────────────────────────────────────

_SELECT_LISTA = """
    SELECT s.id, s.project, s.job_name, s.descricao,
           CONVERT(VARCHAR(8), s.janela_inicio, 108),
           CONVERT(VARCHAR(8), s.janela_fim, 108),
           s.tolerancia_min, s.dias_semana,
           CONVERT(VARCHAR(10), s.vigencia_inicio, 23),
           s.max_linhas, s.grupo_id, s.template_id,
           s.alerta_abortou, s.alerta_nao_executou, s.alerta_atraso, s.alerta_estrutura,
           s.ativo, s.created_by,
           CONVERT(VARCHAR(19), s.created_at, 120),
           CONVERT(VARCHAR(19), s.updated_at, 120),
           g.nome, t.nome
    FROM dbo.etl_ds_supervisao_job s
    LEFT JOIN dbo.etl_msg_grupo    g ON g.id = s.grupo_id
    LEFT JOIN dbo.etl_msg_template t ON t.id = s.template_id
"""


def _row_to_dict(r) -> dict:
    return {
        "id": r[0], "project": r[1], "job_name": r[2], "descricao": r[3],
        "janela_inicio": r[4], "janela_fim": r[5],
        "tolerancia_min": r[6], "dias_semana": r[7],
        "vigencia_inicio": r[8], "max_linhas": r[9],
        "grupo_id": r[10], "template_id": r[11],
        "alerta_abortou": bool(r[12]), "alerta_nao_executou": bool(r[13]),
        "alerta_atraso": bool(r[14]), "alerta_estrutura": bool(r[15]),
        "ativo": bool(r[16]), "created_by": r[17],
        "created_at": r[18], "updated_at": r[19],
        "grupo_nome": r[20], "template_nome": r[21],
    }


@router.get("/admin/ds/supervisao", tags=["ds-supervisao"])
def listar(_auth: dict = Depends(require_ds_console)):
    """Lista todos os jobs supervisionados (ativos e inativos — o front separa).

    Degrada para lista vazia se a migration 062 ainda não foi aplicada, no mesmo
    padrão de routers/monitor.py."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(_SELECT_LISTA + " ORDER BY s.ativo DESC, s.project, s.job_name")
        data = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("[DS SUPERV] listar falhou (migration 062 pendente?): %s", e)
        return {"data": []}


# ── Escrita ─────────────────────────────────────────────────────────────────

@router.post("/admin/ds/supervisao", tags=["ds-supervisao"])
def criar(body: dict = Body(default={}), user: dict = Depends(require_ds_console)):
    """Cadastra um job supervisionado.

    Se o par (project, job_name) já existir INATIVO, reativa aquele registro com
    os dados enviados — preservando o histórico ligado ao id original. Se
    existir ATIVO, devolve 409."""
    project = _nome(body.get("project"), "Projeto")
    job     = _nome(body.get("job_name"), "Job")
    ini     = _hora(body.get("janela_inicio"), "Janela de início")
    fim     = _hora(body.get("janela_fim"), "Fim da janela")
    dias    = _dias(body.get("dias_semana"))
    vig     = _data(body.get("vigencia_inicio"), "Início da vigência")
    tol     = _inteiro(body.get("tolerancia_min"), "Tolerância", 0, 1440, 0)
    maxl    = _inteiro(body.get("max_linhas"), "Limite de linhas do log", 1, 2000, 200)
    desc    = (body.get("descricao") or "").strip()[:400] or None

    conn = get_db_conn(); cur = conn.cursor()
    try:
        grupo    = _ref_opcional(cur, body.get("grupo_id"), "etl_msg_grupo", "Canal do Teams")
        template = _ref_opcional(cur, body.get("template_id"), "etl_msg_template", "Template")

        cur.execute(
            "SELECT id, ativo FROM dbo.etl_ds_supervisao_job WHERE project = ? AND job_name = ?",
            (project, job))
        existente = cur.fetchone()

        if existente and existente[1]:
            raise HTTPException(
                status_code=409,
                detail=f"{project}.{job} já está supervisionado.")

        campos = (ini, fim, tol, dias, vig, maxl, grupo, template,
                  _bit(body, "alerta_abortou"), _bit(body, "alerta_nao_executou"),
                  _bit(body, "alerta_atraso"), _bit(body, "alerta_estrutura"), desc)

        if existente:
            # Reativação: mesmo id, vigência nova. O histórico anterior segue ligado.
            cur.execute(
                "UPDATE dbo.etl_ds_supervisao_job SET "
                "  janela_inicio = ?, janela_fim = ?, tolerancia_min = ?, dias_semana = ?, "
                "  vigencia_inicio = ?, max_linhas = ?, grupo_id = ?, template_id = ?, "
                "  alerta_abortou = ?, alerta_nao_executou = ?, alerta_atraso = ?, "
                "  alerta_estrutura = ?, descricao = ?, ativo = 1, updated_at = GETDATE() "
                "WHERE id = ?", campos + (existente[0],))
            conn.commit()
            log.info("DS superv: %s reativou %s.%s (id=%s)", user.get("matricula"), project, job, existente[0])
            return {"ok": True, "id": int(existente[0]), "reativado": True}

        cur.execute(
            "INSERT INTO dbo.etl_ds_supervisao_job "
            "(project, job_name, janela_inicio, janela_fim, tolerancia_min, dias_semana, "
            " vigencia_inicio, max_linhas, grupo_id, template_id, alerta_abortou, "
            " alerta_nao_executou, alerta_atraso, alerta_estrutura, descricao, created_by) "
            "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project, job) + campos + (user.get("matricula"),))
        nid = int(cur.fetchone()[0])
        conn.commit()
        log.info("DS superv: %s cadastrou %s.%s (id=%s)", user.get("matricula"), project, job, nid)
        return {"ok": True, "id": nid, "reativado": False}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        log.exception("[DS SUPERV] falha ao cadastrar %s.%s", project, job)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


@router.patch("/admin/ds/supervisao/{sid}", tags=["ds-supervisao"])
def editar(sid: int = Path(...), body: dict = Body(default={}),
           user: dict = Depends(require_ds_console)):
    """Edição parcial. project/job_name são imutáveis — o histórico é ligado a eles.

    Tentar alterá-los é recusado em vez de ignorado em silêncio: renomear aqui
    faria os runs já coletados apontarem para um job que não existe mais."""
    if "project" in body or "job_name" in body:
        raise HTTPException(
            status_code=422,
            detail="Projeto e job não podem ser alterados. Remova a supervisão e cadastre o job novo.")

    conn = get_db_conn(); cur = conn.cursor()
    campos: list[str] = []
    params: list = []

    def setc(col: str, val) -> None:
        campos.append(f"{col} = ?"); params.append(val)

    try:
        if "janela_inicio" in body:
            setc("janela_inicio", _hora(body.get("janela_inicio"), "Janela de início"))
        if "janela_fim" in body:
            setc("janela_fim", _hora(body.get("janela_fim"), "Fim da janela"))
        if "dias_semana" in body:
            setc("dias_semana", _dias(body.get("dias_semana")))
        if "vigencia_inicio" in body:
            setc("vigencia_inicio", _data(body.get("vigencia_inicio"), "Início da vigência"))
        if "tolerancia_min" in body:
            setc("tolerancia_min", _inteiro(body.get("tolerancia_min"), "Tolerância", 0, 1440, 0))
        if "max_linhas" in body:
            setc("max_linhas", _inteiro(body.get("max_linhas"), "Limite de linhas do log", 1, 2000, 200))
        if "descricao" in body:
            setc("descricao", (body.get("descricao") or "").strip()[:400] or None)
        if "grupo_id" in body:
            setc("grupo_id", _ref_opcional(cur, body.get("grupo_id"), "etl_msg_grupo", "Canal do Teams"))
        if "template_id" in body:
            setc("template_id", _ref_opcional(cur, body.get("template_id"), "etl_msg_template", "Template"))
        for campo in _CAMPOS_ALERTA:
            if campo in body:
                setc(campo, _bit(body, campo))
        if "ativo" in body:
            setc("ativo", _bit(body, "ativo"))

        if not campos:
            return {"ok": True}

        campos.append("updated_at = GETDATE()")
        cur.execute(
            f"UPDATE dbo.etl_ds_supervisao_job SET {', '.join(campos)} WHERE id = ?",
            params + [sid])
        n = cur.rowcount
        conn.commit()
        if not n:
            raise HTTPException(status_code=404, detail="Job supervisionado não encontrado.")
        log.info("DS superv: %s editou id=%s (%s)", user.get("matricula"), sid, ", ".join(campos))
        return {"ok": True}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        log.exception("[DS SUPERV] falha ao editar id=%s", sid)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()


# ── Painel do dashboard ─────────────────────────────────────────────────────

# Estado do dia, do pior para o melhor. A ordem É a regra de precedência: um job
# que abortou e depois não foi verificado aparece como "sem verificação", porque
# é isso que precisa de ação primeiro.
_PRECEDENCIA = [
    "sem_verificacao",   # ESTRUTURA — nem deu para ler o job
    "abortado",          # ABORTOU
    "nao_executou",      # NAO_EXECUTOU — o dia fechou sem run
    "atrasado",          # ATRASO — passou a janela, dia ainda aberto
    "executando",
    "ok",
    "sem_registro",      # nada coletado (DAG parada? dia futuro?)
]

_EVENTO_PARA_ESTADO = {
    "ESTRUTURA":    "sem_verificacao",
    "ABORTOU":      "abortado",
    "NAO_EXECUTOU": "nao_executou",
    "ATRASO":       "atrasado",
}

_RUN_PARA_ESTADO = {
    "aborted": "abortado",
    "running": "executando",
    "ok":      "ok",
}

ESTADOS_COM_ALERTA = {"sem_verificacao", "abortado", "nao_executou", "atrasado"}


def _pior(estados: list[str]) -> str:
    for estado in _PRECEDENCIA:
        if estado in estados:
            return estado
    return "sem_registro"


@router.get("/dashboard/supervisao", tags=["ds-supervisao"])
def painel(date_ref: str | None = Query(None), _user: dict = Depends(get_current_user)):
    """Situação dos jobs supervisionados em uma data — leitura para o dashboard.

    Lê SÓ do banco: nenhuma chamada SSH acontece aqui. O estado de cada job é
    DERIVADO dos eventos que a DAG já gravou, nunca reclassificado — ter a regra
    escrita em dois lugares (DAG e API) é garantia de divergência.

    Jobs inativos aparecem quando têm histórico na data: quem tira um job da
    supervisão hoje ainda precisa enxergar os dias em que ele era supervisionado.
    """
    dr = (date_ref or "").strip() or date.today().isoformat()
    try:
        dia = datetime.strptime(dr[:10], "%Y-%m-%d").date()
    except ValueError:
        # Mesmo contrato de erro de /dashboard (routers/dashboard.py).
        raise HTTPException(status_code=400, detail=f"date_ref inválido: '{dr}' — use AAAA-MM-DD")

    try:
        conn = get_db_conn(); cur = conn.cursor()
    except Exception as e:
        log.warning("[DS SUPERV] painel sem banco: %s", e)
        return {"date_ref": dia.isoformat(), "data": [], "resumo": {"total": 0, "com_alerta": 0}}

    try:
        cur.execute(
            "SELECT s.id, s.project, s.job_name, "
            "       CONVERT(VARCHAR(8), s.janela_inicio, 108), "
            "       CONVERT(VARCHAR(8), s.janela_fim, 108), "
            "       s.dias_semana, s.ativo, CONVERT(VARCHAR(10), s.vigencia_inicio, 23) "
            "FROM dbo.etl_ds_supervisao_job s "
            "WHERE s.ativo = 1 "
            "   OR EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_run r "
            "              WHERE r.supervisao_id = s.id AND r.data_ref = ?) "
            "   OR EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_evento e "
            "              WHERE e.supervisao_id = s.id AND e.data_ref = ?) "
            "ORDER BY s.project, s.job_name", (dia, dia))
        jobs = cur.fetchall()

        cur.execute(
            "SELECT supervisao_id, CONVERT(VARCHAR(19), run_inicio, 120), "
            "       CONVERT(VARCHAR(19), run_fim, 120), duracao_seg, resultado, jobs_filhos "
            "FROM dbo.etl_ds_supervisao_run WHERE data_ref = ? ORDER BY run_inicio", (dia,))
        runs_por_job: dict[int, list[dict]] = {}
        for r in cur.fetchall():
            runs_por_job.setdefault(int(r[0]), []).append({
                "inicio": r[1], "fim": r[2], "duracao_seg": r[3],
                "resultado": r[4], "jobs_filhos": r[5],
            })

        cur.execute(
            "SELECT supervisao_id, tipo, detalhe, "
            "       CONVERT(VARCHAR(19), detectado_em, 120), "
            "       CONVERT(VARCHAR(19), notificado_em, 120) "
            "FROM dbo.etl_ds_supervisao_evento WHERE data_ref = ? "
            "ORDER BY detectado_em", (dia,))
        eventos_por_job: dict[int, list[dict]] = {}
        for r in cur.fetchall():
            eventos_por_job.setdefault(int(r[0]), []).append({
                "tipo": r[1], "detalhe": r[2],
                "detectado_em": r[3], "notificado_em": r[4],
            })
    except Exception as e:
        # Migration 062 pendente ou banco fora: painel vazio em vez de erro na
        # tela inteira do dashboard.
        log.warning("[DS SUPERV] painel indisponível (migration 062 aplicada?): %s", e)
        return {"date_ref": dia.isoformat(), "data": [], "resumo": {"total": 0, "com_alerta": 0}}
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass

    dados = []
    for j in jobs:
        sid = int(j[0])
        runs = runs_por_job.get(sid, [])
        eventos = eventos_por_job.get(sid, [])

        estados = [_EVENTO_PARA_ESTADO[e["tipo"]] for e in eventos
                   if e["tipo"] in _EVENTO_PARA_ESTADO]
        estados += [_RUN_PARA_ESTADO[r["resultado"]] for r in runs
                    if r["resultado"] in _RUN_PARA_ESTADO]
        estado = _pior(estados)

        try:
            dias = {int(d) for d in (j[5] or "").split(",") if d.strip().isdigit()}
        except ValueError:
            dias = set()

        dados.append({
            "id": sid, "project": j[1], "job_name": j[2],
            "janela_inicio": j[3], "janela_fim": j[4],
            "dias_semana": j[5], "ativo": bool(j[6]), "vigencia_inicio": j[7],
            # previsto=False → o job não roda nesse dia da semana; a tela mostra
            # "não previsto" em vez de sugerir que faltou executar.
            "previsto": dia.isoweekday() in dias,
            "estado": estado,
            "runs": runs,
            "eventos": eventos,
        })

    com_alerta = sum(1 for d in dados if d["estado"] in ESTADOS_COM_ALERTA)
    return {"date_ref": dia.isoformat(), "data": dados,
            "resumo": {"total": len(dados), "com_alerta": com_alerta}}


@router.delete("/admin/ds/supervisao/{sid}", tags=["ds-supervisao"])
def excluir(sid: int = Path(...), user: dict = Depends(require_ds_console)):
    """Remoção LÓGICA (ativo=0), preservando o histórico já coletado.

    Cadastro que nunca produziu run nem evento é apagado de fato — não há
    histórico a preservar e deixar lixo inativo na tela não ajuda ninguém.
    Devolve {"removido": "logico"|"fisico"} para o front escolher a mensagem."""
    conn = get_db_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM dbo.etl_ds_supervisao_job WHERE id = ?", (sid,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Job supervisionado não encontrado.")

        cur.execute(
            "SELECT (SELECT COUNT(*) FROM dbo.etl_ds_supervisao_run    WHERE supervisao_id = ?) "
            "     + (SELECT COUNT(*) FROM dbo.etl_ds_supervisao_evento WHERE supervisao_id = ?)",
            (sid, sid))
        historico = int(cur.fetchone()[0] or 0)

        if historico:
            cur.execute(
                "UPDATE dbo.etl_ds_supervisao_job SET ativo = 0, updated_at = GETDATE() WHERE id = ?",
                (sid,))
            conn.commit()
            log.info("DS superv: %s desativou id=%s (%s registros de histórico preservados)",
                     user.get("matricula"), sid, historico)
            return {"ok": True, "removido": "logico", "historico": historico}

        cur.execute("DELETE FROM dbo.etl_ds_supervisao_job WHERE id = ?", (sid,))
        conn.commit()
        log.info("DS superv: %s excluiu id=%s (sem histórico)", user.get("matricula"), sid)
        return {"ok": True, "removido": "fisico", "historico": 0}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        log.exception("[DS SUPERV] falha ao remover id=%s", sid)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
