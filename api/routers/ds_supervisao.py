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
  • O webhook do canal nunca trafega aqui: guarda-se só o grupo_id.
  • Cada tipo de alerta tem mensagem própria (migration 063): um job liga até
    quatro alertas e uma frase única não explica os quatro casos.
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

_CAMPOS_ALERTA = ("alerta_abortou", "alerta_nao_executou", "alerta_atraso", "alerta_estrutura",
                  "alerta_sucesso_falso", "alerta_filho_ausente")

# Tipos que aceitam mensagem própria — espelham o CHECK da migration 063.
TIPOS_MENSAGEM = ("ABORTOU", "NAO_EXECUTOU", "ATRASO", "ESTRUTURA", "SITUACAO_INICIAL",
                  "SUCESSO_FALSO", "FILHO_AUSENTE")

# Variáveis que o usuário pode usar no texto do alerta.
#
# ESPELHO de dags/utils/ds_mensagens.py:VARIAVEIS — a API não importa de dags/
# (containers separados), então o catálogo vive nos dois lugares e a paridade é
# travada por teste (tests/test_ds_mensagens.py). Mexeu aqui, mexa lá.
VARIAVEIS_MENSAGEM: list[tuple[str, str, str]] = [
    ("projeto",       "Projeto do DataStage",                      "BI_CVP"),
    ("job",           "Nome do job / sequence",                    "SeqSsdVida7Peps"),
    ("descricao",     "Descrição cadastrada do job",               "Carga diária de vida"),
    ("tipo",          "Tipo do alerta",                            "ATRASO"),
    ("data",          "Dia a que o alerta se refere",              "2026-07-29"),
    ("janela_inicio", "Início da janela esperada",                 "02:00"),
    ("janela_fim",    "Fim da janela esperada",                    "03:00"),
    ("tolerancia",    "Tolerância configurada, em minutos",        "15"),
    ("limite",        "Horário limite (fim da janela + tolerância)", "03:15"),
    ("dias",          "Dias da semana supervisionados",            "seg, ter, qua, qui, sex"),
    ("inicio",        "Início da execução observada",              "02:10"),
    ("fim",           "Término da execução observada",             "02:50"),
    ("duracao",       "Duração da execução observada",             "40 min"),
    ("situacao",      "Frase automática com a situação do dia",    "não iniciou até 03:15"),
    ("total_filhos",     "Quantos jobs rodaram abaixo do supervisionado", "12"),
    ("filhos_falharam",  "Jobs abaixo que abortaram",                 "CargaVida, CargaPrev"),
    ("filhos_ausentes",  "Jobs esperados que não rodaram",            "CargaMensal"),
    ("filhos_ok",        "Jobs abaixo que concluíram",                "CargaA, CargaB"),
]

_NOMES_VARIAVEIS = {v[0] for v in VARIAVEIS_MENSAGEM}
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


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
    """Valida grupo_id: existe e está ativo. Vazio → None.

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


def _descricao_obrigatoria(valor) -> str:
    """Descrição é obrigatória desde a 063 — é o rótulo que dá contexto ao alerta."""
    texto = (valor or "").strip()
    if not texto:
        raise HTTPException(
            status_code=422,
            detail="Informe a descrição do job — ela identifica o alerta no painel e no Teams.")
    return texto[:400]


def _validar_mensagens(bruto) -> dict[str, str]:
    """Valida {tipo: texto} do body. Texto vazio = volta ao padrão do sistema.

    Variável desconhecida é recusada: salvar '{tolerancia_min}' achando que
    funciona só se descobre quando o card chega ao canal com o texto cru."""
    if bruto is None:
        return {}
    if not isinstance(bruto, dict):
        raise HTTPException(status_code=422, detail="mensagens deve ser um objeto {tipo: texto}")

    limpo: dict[str, str] = {}
    for tipo, texto in bruto.items():
        if tipo not in TIPOS_MENSAGEM:
            raise HTTPException(status_code=422, detail=f"Tipo de mensagem desconhecido: {tipo}")
        conteudo = (texto or "").strip()
        if not conteudo:
            limpo[tipo] = ""          # marca para remover e voltar ao padrão
            continue
        desconhecidas = sorted({m for m in _PLACEHOLDER_RE.findall(conteudo)
                                if m not in _NOMES_VARIAVEIS})
        if desconhecidas:
            raise HTTPException(
                status_code=422,
                detail=(f"Variável inexistente na mensagem de {tipo}: "
                        f"{', '.join('{' + d + '}' for d in desconhecidas)}"))
        limpo[tipo] = conteudo[:2000]
    return limpo


def _salvar_mensagens(cur, sid: int, mensagens: dict[str, str]) -> None:
    """Upsert das mensagens; texto vazio remove a linha (volta ao padrão)."""
    for tipo, texto in mensagens.items():
        if not texto:
            cur.execute(
                "DELETE FROM dbo.etl_ds_supervisao_mensagem "
                "WHERE supervisao_id = ? AND tipo = ?", (sid, tipo))
            continue
        cur.execute(
            "UPDATE dbo.etl_ds_supervisao_mensagem SET mensagem = ?, updated_at = GETDATE() "
            "WHERE supervisao_id = ? AND tipo = ?", (texto, sid, tipo))
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO dbo.etl_ds_supervisao_mensagem (supervisao_id, tipo, mensagem) "
                "VALUES (?, ?, ?)", (sid, tipo, texto))


def _ler_mensagens(cur) -> dict[int, dict[str, str]]:
    """Mensagens de todos os jobs. Degrada para vazio sem a migration 063."""
    try:
        cur.execute("SELECT supervisao_id, tipo, mensagem FROM dbo.etl_ds_supervisao_mensagem")
        por_job: dict[int, dict[str, str]] = {}
        for r in cur.fetchall():
            por_job.setdefault(int(r[0]), {})[r[1]] = r[2]
        return por_job
    except Exception as e:
        log.warning("[DS SUPERV] mensagens indisponíveis (migration 063 aplicada?): %s", e)
        return {}


# ── Leitura ─────────────────────────────────────────────────────────────────

_SELECT_LISTA = """
    SELECT s.id, s.project, s.job_name, s.descricao,
           CONVERT(VARCHAR(8), s.janela_inicio, 108),
           CONVERT(VARCHAR(8), s.janela_fim, 108),
           s.tolerancia_min, s.dias_semana,
           CONVERT(VARCHAR(10), s.vigencia_inicio, 23),
           s.max_linhas, s.grupo_id,
           s.alerta_abortou, s.alerta_nao_executou, s.alerta_atraso, s.alerta_estrutura,
           s.ativo, s.created_by,
           CONVERT(VARCHAR(19), s.created_at, 120),
           CONVERT(VARCHAR(19), s.updated_at, 120),
           g.nome
    FROM dbo.etl_ds_supervisao_job s
    LEFT JOIN dbo.etl_msg_grupo g ON g.id = s.grupo_id
"""


def _row_to_dict(r) -> dict:
    return {
        "id": r[0], "project": r[1], "job_name": r[2], "descricao": r[3],
        "janela_inicio": r[4], "janela_fim": r[5],
        "tolerancia_min": r[6], "dias_semana": r[7],
        "vigencia_inicio": r[8], "max_linhas": r[9],
        "grupo_id": r[10],
        "alerta_abortou": bool(r[11]), "alerta_nao_executou": bool(r[12]),
        "alerta_atraso": bool(r[13]), "alerta_estrutura": bool(r[14]),
        "ativo": bool(r[15]), "created_by": r[16],
        "created_at": r[17], "updated_at": r[18],
        "grupo_nome": r[19],
        "mensagens": {},          # preenchido em listar()
    }


@router.get("/admin/ds/supervisao/variaveis", tags=["ds-supervisao"])
def variaveis(_auth: dict = Depends(require_ds_console)):
    """Variáveis disponíveis nas mensagens de alerta, para a tela de cadastro.

    Fonte única do que a tela oferece; a interpolação em si acontece na coleta
    (dags/utils/ds_mensagens.py), cujo catálogo é espelho deste."""
    return {
        "tipos": list(TIPOS_MENSAGEM),
        "variaveis": [{"nome": n, "descricao": d, "exemplo": e}
                      for n, d, e in VARIAVEIS_MENSAGEM],
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
        mensagens = _ler_mensagens(cur)
        for item in data:
            item["mensagens"] = mensagens.get(item["id"], {})
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
    desc    = _descricao_obrigatoria(body.get("descricao"))
    msgs    = _validar_mensagens(body.get("mensagens"))

    conn = get_db_conn(); cur = conn.cursor()
    try:
        grupo = _ref_opcional(cur, body.get("grupo_id"), "etl_msg_grupo", "Canal do Teams")

        cur.execute(
            "SELECT id, ativo FROM dbo.etl_ds_supervisao_job WHERE project = ? AND job_name = ?",
            (project, job))
        existente = cur.fetchone()

        if existente and existente[1]:
            raise HTTPException(
                status_code=409,
                detail=f"{project}.{job} já está supervisionado.")

        campos = (ini, fim, tol, dias, vig, maxl, grupo,
                  _bit(body, "alerta_abortou"), _bit(body, "alerta_nao_executou"),
                  _bit(body, "alerta_atraso"), _bit(body, "alerta_estrutura"), desc)

        if existente:
            # Reativação: mesmo id, vigência nova. O histórico anterior segue ligado.
            cur.execute(
                "UPDATE dbo.etl_ds_supervisao_job SET "
                "  janela_inicio = ?, janela_fim = ?, tolerancia_min = ?, dias_semana = ?, "
                "  vigencia_inicio = ?, max_linhas = ?, grupo_id = ?, "
                "  alerta_abortou = ?, alerta_nao_executou = ?, alerta_atraso = ?, "
                "  alerta_estrutura = ?, descricao = ?, ativo = 1, updated_at = GETDATE() "
                "WHERE id = ?", campos + (existente[0],))
            _salvar_mensagens(cur, int(existente[0]), msgs)
            conn.commit()
            log.info("DS superv: %s reativou %s.%s (id=%s)", user.get("matricula"), project, job, existente[0])
            return {"ok": True, "id": int(existente[0]), "reativado": True}

        cur.execute(
            "INSERT INTO dbo.etl_ds_supervisao_job "
            "(project, job_name, janela_inicio, janela_fim, tolerancia_min, dias_semana, "
            " vigencia_inicio, max_linhas, grupo_id, alerta_abortou, "
            " alerta_nao_executou, alerta_atraso, alerta_estrutura, descricao, created_by) "
            "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project, job) + campos + (user.get("matricula"),))
        nid = int(cur.fetchone()[0])
        _salvar_mensagens(cur, nid, msgs)
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
            setc("descricao", _descricao_obrigatoria(body.get("descricao")))
        if "grupo_id" in body:
            setc("grupo_id", _ref_opcional(cur, body.get("grupo_id"), "etl_msg_grupo", "Canal do Teams"))
        for campo in _CAMPOS_ALERTA:
            if campo in body:
                setc(campo, _bit(body, campo))
        if "ativo" in body:
            setc("ativo", _bit(body, "ativo"))

        msgs = _validar_mensagens(body.get("mensagens")) if "mensagens" in body else {}

        if not campos and not msgs:
            return {"ok": True}

        n = 1
        if campos:
            campos.append("updated_at = GETDATE()")
            cur.execute(
                f"UPDATE dbo.etl_ds_supervisao_job SET {', '.join(campos)} WHERE id = ?",
                params + [sid])
            n = cur.rowcount
        if msgs:
            _salvar_mensagens(cur, sid, msgs)
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
    "sucesso_falso",     # SUCESSO_FALSO — sequence disse OK, mas um filho abortou
    "nao_executou",      # NAO_EXECUTOU — o dia fechou sem run
    "filho_ausente",     # FILHO_AUSENTE — rodou sem um job que sempre roda
    "atrasado",          # ATRASO — passou a janela, dia ainda aberto
    "executando",
    "ok",
    "sem_registro",      # nada coletado (DAG parada? dia futuro?)
]

_EVENTO_PARA_ESTADO = {
    "ESTRUTURA":     "sem_verificacao",
    "ABORTOU":       "abortado",
    "SUCESSO_FALSO": "sucesso_falso",
    "NAO_EXECUTOU":  "nao_executou",
    "FILHO_AUSENTE": "filho_ausente",
    "ATRASO":        "atrasado",
}

_RUN_PARA_ESTADO = {
    "aborted": "abortado",
    "running": "executando",
    "ok":      "ok",
}

# sucesso_falso entra aqui de propósito: é o caso em que o DataStage diz OK e o
# dia NÃO pode aparecer como bom — foi o que motivou a análise de dependência.
ESTADOS_COM_ALERTA = {"sem_verificacao", "abortado", "sucesso_falso",
                      "nao_executou", "filho_ausente", "atrasado"}


def _pior(estados: list[str]) -> str:
    for estado in _PRECEDENCIA:
        if estado in estados:
            return estado
    return "sem_registro"


# Códigos de status do DataStage para job filho, traduzidos para a tela.
_STATUS_FILHO = {
    1: "concluído", 2: "com avisos", 3: "ABORTADO", 13: "validação falhou",
    96: "crash", 97: "parado", 0: "em execução", -1: "sem status no log",
}
# Só o abort gera alerta hoje (decisão do usuário); os demais aparecem no painel.
_CODIGO_ABORTADO = 3


def _ler_filhos(cur, dia) -> dict[int, list[dict]]:
    """Status de cada job filho no dia, agrupado por job supervisionado.

    Degrada para vazio sem a migration 064 — o painel perde o detalhe de
    dependência, mas continua mostrando o resto."""
    try:
        # nivel/job_pai só existem a partir da 065 — o fallback mantém o painel
        # vivo se o deploy do front chegar antes da migration.
        try:
            cur.execute(
                "SELECT supervisao_id, CONVERT(VARCHAR(19), run_inicio, 120), "
                "       job_filho, status_code, nivel, job_pai "
                "FROM dbo.etl_ds_supervisao_run_filho WHERE data_ref = ? "
                "ORDER BY run_inicio, nivel, job_filho", (dia,))
            linhas = [(r[0], r[1], r[2], r[3], int(r[4] or 1), r[5]) for r in cur.fetchall()]
        except Exception:
            cur.execute(
                "SELECT supervisao_id, CONVERT(VARCHAR(19), run_inicio, 120), "
                "       job_filho, status_code "
                "FROM dbo.etl_ds_supervisao_run_filho WHERE data_ref = ? "
                "ORDER BY run_inicio, job_filho", (dia,))
            linhas = [(r[0], r[1], r[2], r[3], 1, None) for r in cur.fetchall()]

        por_job: dict[int, list[dict]] = {}
        for sid, run_inicio, nome, codigo_bruto, nivel, pai in linhas:
            codigo = int(codigo_bruto)
            por_job.setdefault(int(sid), []).append({
                "run_inicio": run_inicio, "job_filho": nome, "status_code": codigo,
                "status": _STATUS_FILHO.get(codigo, f"código {codigo}"),
                "falhou": codigo == _CODIGO_ABORTADO,
                "nivel": nivel, "job_pai": pai,
            })
        return por_job
    except Exception as e:
        log.warning("[DS SUPERV] filhos indisponíveis (migration 064 aplicada?): %s", e)
        return {}


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

        # Jobs ABAIXO do supervisionado: é o detalhe que mostra de onde veio o
        # veredito quando a sequence diz OK e um filho abortou.
        filhos_por_job = _ler_filhos(cur, dia)
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
            "filhos": filhos_por_job.get(sid, []),
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
