"""api/routers/caixa_uso.py — monitoramento de uso do módulo Busca & Vendas.

  POST /caixa/uso/acesso    — registra a ABERTURA de uma tela de /caixa-seguro/*
  POST /caixa/uso/presenca  — batimento da aba visível ("online agora")
  GET  /caixa/uso/resumo    — KPIs, série, acessos por tela e ranking (tela "Uso do módulo")

Spec docs/spec-uso-busca-vendas.md. Tabelas da migration 141 (`etl_uso_evento`,
`etl_uso_presenca`); o recurso `caixa_seguro_uso` governa a LEITURA, concedido no Admin.

⚠️ **A matrícula vem do token, nunca do corpo.** O front só diz QUAL rota abriu; quem
abriu é `get_current_user`. Corpo com `matricula` é ignorado (o modelo nem o declara).

⚠️ **Rota fora do registro não grava nada.** `ROTAS` é um registro fechado: regex da
rota → rota canônica + rótulo da tela. Rota desconhecida responde 200 com
`registrado: false` — o front nunca ganha erro por medir, e a tabela não recebe lixo.
Rota nova no módulo exige entrada aqui; `tests/test_caixa_uso_api.py` lê o App.tsx e
reprova a divergência.

⚠️ **Acesso é deduplicado no SERVIDOR** (mesma matrícula + rota + detalhe nos últimos
30 min), porque o StrictMode e a navegação rápida disparam o efeito duas vezes.

⚠️ O relógio é o do BANCO (`GETDATE()`, Brasília) em tudo — gravação, janela de
dedupe, "online agora" e os limites dos períodos —, para não misturar com o fuso do
processo Python. O "hoje" do padrão da consulta usa America/Sao_Paulo pelo mesmo motivo.

Placeholder `?` (pyodbc) — árvore `api/`. Nomes de objeto e expressões de agrupamento
são fixos neste arquivo e nunca vêm da requisição.
"""
from __future__ import annotations

import logging
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import get_db_conn
from deps import require_perm

log = logging.getLogger("orquestra-api")

router = APIRouter()

PERM_ACESSAR = "tela_caixa_seguro"
PERM_VER_USO = "caixa_seguro_uso"
_require_modulo = require_perm(PERM_ACESSAR)
_require_ver_uso = require_perm(PERM_VER_USO)

EVENTO = "dbo.etl_uso_evento"
PRESENCA = "dbo.etl_uso_presenca"
USUARIO = "dbo.etl_usuario"

MODULO = "busca_vendas"
JANELA_DEDUPE_MIN = 30
JANELA_ONLINE_MIN = 10
LIMITE_RANKING = 50
LIMITE_NOMES_ONLINE = 20
ANO_MIN, ANO_MAX = 2000, 2100

_FUSO = ZoneInfo("America/Sao_Paulo")
_MSG_INDISPONIVEL = ("Uso do módulo indisponível — aplique as migrations 141 e 142 "
                     "(tabelas etl_uso_evento e etl_uso_presenca).")

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


class Rota(NamedTuple):
    padrao: re.Pattern
    canonica: str
    tela: str
    com_detalhe: bool = False


# Os 8 StatusWorkflow do front (`caixa/lib/workflow.ts`): o único `detalhe` aceito.
# Allowlist, não regex aberta: um `:status` livre deixaria um usuário gravar uma linha
# por valor inventado (dedupe é por detalhe) e inflar a tabela e os próprios acessos.
# tests/test_caixa_uso_api.py compara esta lista com o `workflow.ts`.
STATUS_ACOMPANHAMENTO = (
    "pending_signature", "awaiting_payment", "paid", "in_analysis",
    "emission_sent", "declined", "refund_scheduled", "sensitization_monitoring",
)

# Registro FECHADO das telas medidas. O `:status` do Acompanhamento vira `detalhe`.
ROTAS: tuple[Rota, ...] = (
    Rota(re.compile(r"^/caixa-seguro/?$"), "/caixa-seguro", "Consulta de Propostas"),
    Rota(re.compile(r"^/caixa-seguro/acompanhamento/?$"),
         "/caixa-seguro/acompanhamento", "Monitoramento Tático de Emissão"),
    Rota(re.compile(r"^/caixa-seguro/acompanhamento/(" + "|".join(STATUS_ACOMPANHAMENTO) + r")/?$"),
         "/caixa-seguro/acompanhamento/:status", "Acompanhamento por status", True),
    Rota(re.compile(r"^/caixa-seguro/portabilidades/?$"),
         "/caixa-seguro/portabilidades", "Portabilidades"),
    Rota(re.compile(r"^/caixa-seguro/ia-operacional/?$"),
         "/caixa-seguro/ia-operacional", "Painel de IA Operacional"),
    Rota(re.compile(r"^/caixa-seguro/uso/?$"), "/caixa-seguro/uso", "Uso do módulo"),
)


class TelaResolvida(NamedTuple):
    rota: str
    tela: str
    detalhe: str | None


def resolver_rota(bruta: str) -> TelaResolvida | None:
    """Rota do navegador → tela do registro; `None` se não for do módulo/registro."""
    caminho = (bruta or "").strip()
    if not caminho or len(caminho) > 200:
        return None
    for r in ROTAS:
        m = r.padrao.match(caminho)
        if m:
            return TelaResolvida(r.canonica, r.tela, m.group(1) if r.com_detalhe else None)
    return None


class CorpoRota(BaseModel):
    # Só a rota. `matricula` no corpo é ignorado: o modelo não a declara.
    rota: str = Field(default="", max_length=200)


def _indisponivel(e: Exception) -> HTTPException:
    log.warning("caixa_uso: banco indisponível (%s: %s)", type(e).__name__, e)
    return HTTPException(status_code=503, detail=_MSG_INDISPONIVEL)


# ── Escrita ────────────────────────────────────────────────────────────────

@router.post("/caixa/uso/acesso")
def registrar_acesso(corpo: CorpoRota, user: dict = Depends(_require_modulo)) -> dict:
    tela = resolver_rota(corpo.rota)
    if tela is None:
        return {"registrado": False, "motivo": "rota fora do módulo"}
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # INSERT … WHERE NOT EXISTS numa instrução só: o dedupe e a gravação não
        # deixam brecha entre o SELECT e o INSERT. O CAST força VARCHAR nos parâmetros:
        # o pyodbc envia `str` como NVARCHAR e, com collation SQL, a comparação com a
        # coluna VARCHAR viraria scan (e o HOLDLOCK travaria um intervalo grande).
        cur.execute(f"""
            INSERT INTO {EVENTO} (matricula, modulo, rota, tela, detalhe)
            SELECT ?, ?, ?, ?, ?
             WHERE NOT EXISTS (
                   SELECT 1 FROM {EVENTO} WITH (UPDLOCK, HOLDLOCK)
                    WHERE matricula = CAST(? AS VARCHAR(20)) AND rota = CAST(? AS VARCHAR(120))
                      AND ISNULL(detalhe, '') = ISNULL(CAST(? AS VARCHAR(40)), '')
                      AND ocorrido_em > DATEADD(MINUTE, ?, GETDATE()))
        """, [user["matricula"], MODULO, tela.rota, tela.tela, tela.detalhe,
              user["matricula"], tela.rota, tela.detalhe, -JANELA_DEDUPE_MIN])
        gravou = (cur.rowcount or 0) > 0
        conn.commit()
        cur.close()
        return {"registrado": gravou}
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado antes da 141
        # Medir nunca quebra a tela: o front ignora a falha. O aviso fica no log, e o
        # GET /resumo devolve 503 nomeando a migration para quem olha a tela.
        log.warning("caixa_uso: acesso não gravado (%s: %s)", type(e).__name__, e)
        return {"registrado": False, "motivo": "indisponível"}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:       # noqa: BLE001
                pass


@router.post("/caixa/uso/presenca")
def registrar_presenca(corpo: CorpoRota, user: dict = Depends(_require_modulo)) -> dict:
    tela = resolver_rota(corpo.rota)
    if tela is None:
        return {"registrado": False, "motivo": "rota fora do módulo"}
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(f"""
            MERGE {PRESENCA} WITH (HOLDLOCK) AS t
            USING (SELECT ? AS matricula) AS s ON t.matricula = s.matricula
            WHEN MATCHED THEN UPDATE SET rota = ?, atualizado_em = GETDATE()
            WHEN NOT MATCHED THEN INSERT (matricula, rota, atualizado_em)
                 VALUES (s.matricula, ?, GETDATE());
        """, [user["matricula"], tela.rota, tela.rota])
        conn.commit()
        cur.close()
        return {"registrado": True}
    except Exception as e:      # noqa: BLE001
        log.warning("caixa_uso: presença não gravada (%s: %s)", type(e).__name__, e)
        return {"registrado": False, "motivo": "indisponível"}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:       # noqa: BLE001
                pass


# ── Leitura ────────────────────────────────────────────────────────────────

def hoje_brasilia() -> date:
    return datetime.now(_FUSO).date()


class Janela(NamedTuple):
    inicio: datetime        # inclusivo
    fim: datetime           # EXCLUSIVO
    granularidade: str      # hora | dia | mes
    ref_fim: date           # último dia coberto (para a resposta)


def janela_do_periodo(periodo: str, ref: date) -> Janela:
    """Limites [inicio, fim) do período que contém `ref`."""
    if periodo == "dia":
        ini = datetime(ref.year, ref.month, ref.day)
        return Janela(ini, ini + timedelta(days=1), "hora", ref)
    if periodo == "mes":
        ini = datetime(ref.year, ref.month, 1)
        fim = datetime(ref.year + (ref.month == 12), (ref.month % 12) + 1, 1)
        return Janela(ini, fim, "dia", date(ref.year, ref.month, monthrange(ref.year, ref.month)[1]))
    ini = datetime(ref.year, 1, 1)
    return Janela(ini, datetime(ref.year + 1, 1, 1), "mes", date(ref.year, 12, 31))


# Expressão do balde de cada granularidade — FIXA (nunca vem da requisição).
_BALDE = {"hora": "DATEPART(HOUR, ocorrido_em)", "dia": "DAY(ocorrido_em)",
          "mes": "MONTH(ocorrido_em)"}


def rotulos_da_serie(janela: Janela) -> list[tuple[int, str]]:
    """(balde, rótulo) de TODOS os baldes do período, para a série sem buracos."""
    if janela.granularidade == "hora":
        return [(h, f"{h:02d}h") for h in range(24)]
    if janela.granularidade == "dia":
        return [(d, f"{d:02d}") for d in range(1, janela.ref_fim.day + 1)]
    return [(i + 1, m) for i, m in enumerate(MESES)]


def _inteiro(v) -> int:
    return int(v or 0)


def _iso_hora(v) -> str | None:
    if v is None:
        return None
    return v.isoformat(timespec="seconds") if hasattr(v, "isoformat") else str(v)


def _nome(primeiro, ultimo, matricula: str) -> str:
    nome = " ".join(p.strip() for p in (primeiro, ultimo) if p and str(p).strip())
    return nome or matricula


@router.get("/caixa/uso/resumo")
def resumo(
    periodo: str = Query("dia", description="dia | mes | ano"),
    referencia: str | None = Query(None, description="AAAA-MM-DD; padrão = hoje (Brasília)"),
    _user: dict = Depends(_require_ver_uso),
) -> dict:
    if periodo not in ("dia", "mes", "ano"):
        raise HTTPException(status_code=422, detail="periodo deve ser dia, mes ou ano")
    try:
        ref = date.fromisoformat(referencia) if referencia else hoje_brasilia()
    except ValueError:
        raise HTTPException(status_code=422, detail="referencia deve ser AAAA-MM-DD")
    if not ANO_MIN <= ref.year <= ANO_MAX:
        # Fora disso o datetime do SQL Server (>= 1753) ou o próprio calendário estouram
        # — e o `except` abaixo transformaria em um 503 que acusa a migration, sem culpa dela.
        raise HTTPException(status_code=422, detail=f"referencia deve estar entre {ANO_MIN} e {ANO_MAX}")
    janela = janela_do_periodo(periodo, ref)
    limites = [janela.inicio, janela.fim]

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT matricula) FROM {EVENTO} "
                    "WHERE ocorrido_em >= ? AND ocorrido_em < ?", limites)
        acessos, usuarios = (list(cur.fetchone() or (0, 0)) + [0, 0])[:2]

        cur.execute(f"SELECT {_BALDE[janela.granularidade]}, COUNT(*), COUNT(DISTINCT matricula) "
                    f"FROM {EVENTO} WHERE ocorrido_em >= ? AND ocorrido_em < ? "
                    f"GROUP BY {_BALDE[janela.granularidade]}", limites)
        por_balde = {int(b): (_inteiro(a), _inteiro(u)) for b, a, u in (cur.fetchall() or [])}

        cur.execute(f"SELECT rota, MAX(tela), COUNT(*), COUNT(DISTINCT matricula) FROM {EVENTO} "
                    "WHERE ocorrido_em >= ? AND ocorrido_em < ? "
                    "GROUP BY rota ORDER BY COUNT(*) DESC, rota", limites)
        por_tela = [{"tela": t or r, "rota": r, "acessos": _inteiro(a), "usuarios": _inteiro(u)}
                    for r, t, a, u in (cur.fetchall() or [])]

        cur.execute(f"""
            SELECT TOP ({LIMITE_RANKING}) e.matricula, MAX(u.primeiro_nome), MAX(u.ultimo_nome),
                   COUNT(*), COUNT(DISTINCT CAST(e.ocorrido_em AS DATE)), MAX(e.ocorrido_em)
              FROM {EVENTO} e LEFT JOIN {USUARIO} u ON u.matricula = e.matricula
             WHERE e.ocorrido_em >= ? AND e.ocorrido_em < ?
             GROUP BY e.matricula ORDER BY COUNT(*) DESC, e.matricula
        """, limites)
        base = cur.fetchall() or []

        cur.execute(f"""
            SELECT matricula, tela FROM (
                SELECT matricula, tela,
                       ROW_NUMBER() OVER (PARTITION BY matricula
                                          ORDER BY COUNT(*) DESC, MAX(ocorrido_em) DESC) AS rn
                  FROM {EVENTO} WHERE ocorrido_em >= ? AND ocorrido_em < ?
                 GROUP BY matricula, tela) x
             WHERE rn = 1
        """, limites)
        tela_top = {m: t for m, t in (cur.fetchall() or [])}

        cur.execute(f"SELECT MIN(ocorrido_em) FROM {EVENTO}")
        primeiro = (cur.fetchone() or (None,))[0]

        cur.execute(f"""
            SELECT TOP ({LIMITE_NOMES_ONLINE}) p.matricula, u.primeiro_nome, u.ultimo_nome
              FROM {PRESENCA} p LEFT JOIN {USUARIO} u ON u.matricula = p.matricula
             WHERE p.atualizado_em >= DATEADD(MINUTE, ?, GETDATE())
             ORDER BY p.atualizado_em DESC
        """, [-JANELA_ONLINE_MIN])
        online = [_nome(p, s, m) for m, p, s in (cur.fetchall() or [])]
        cur.execute(f"SELECT COUNT(*) FROM {PRESENCA} WHERE atualizado_em >= DATEADD(MINUTE, ?, GETDATE())",
                    [-JANELA_ONLINE_MIN])
        online_total = _inteiro((cur.fetchone() or (0,))[0])

        cur.close()
    except Exception as e:      # noqa: BLE001
        raise _indisponivel(e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:       # noqa: BLE001
                pass

    acessos, usuarios = _inteiro(acessos), _inteiro(usuarios)
    return {
        "online_agora": online_total,
        "usuarios_online": online,
        "primeiro_registro": primeiro.date().isoformat() if hasattr(primeiro, "date") else (
            str(primeiro)[:10] if primeiro else None),
        "periodo": {"inicio": janela.inicio.date().isoformat(),
                    "fim": janela.ref_fim.isoformat(),
                    "granularidade": janela.granularidade},
        "kpis": {"usuarios": usuarios, "acessos": acessos,
                 "acessos_por_usuario": round(acessos / usuarios, 1) if usuarios else 0.0},
        "serie": [{"rotulo": rot, "acessos": por_balde.get(b, (0, 0))[0],
                   "usuarios": por_balde.get(b, (0, 0))[1]}
                  for b, rot in rotulos_da_serie(janela)],
        "por_tela": por_tela,
        "ranking": [{"matricula": m, "nome": _nome(p, s, m), "acessos": _inteiro(a),
                     "dias_ativos": _inteiro(d), "ultimo_acesso": _iso_hora(ult),
                     "tela_top": tela_top.get(m, "")}
                    for m, p, s, a, d, ult in base],
    }
