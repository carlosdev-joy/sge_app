"""api/routers/pio_card2.py — Card 2 (Pendentes de Pagamento) lendo a FOTO diária.

  GET /pio/card2/resumo     — prêmio e quantidade do card (tabela AGREGADA)
  GET /pio/card2/propostas  — lista paginada do drill-down (tabela ANALÍTICA)

Mesmo padrão do Card 1 (`routers/pio_card1.py`, de onde vêm os helpers puros):
só as tabelas mudam. A carga é o pipeline Fabric do Card 2 (07:30), que publica
uma foto por `DTA_MOVIMENTO` em três tabelas do DMDB41 — esta API só LÊ:

    dbo.AGG_ORQ_CARD02_FOTO   grupos pré-agregados → número do card
    dbo.FAT_ORQ_CARD02_FOTO   linhas da query aceita → lista, detalhe e contatos
    dbo.CTL_ORQ_CARD02_LOTE   controle: qual lote está PUBLICADO em cada data

A query da carga: assinatura `CO`/`SO`, `STA_PAGO='N'`, sem `CA`/`EX`, venda nos
últimos 30 dias — tudo na CARGA. Aqui não se reaplica GETDATE nem D-30.

⚠️ **Uma foto = `DTA_MOVIMENTO` + `LOTE_ID`** (o CTL `PUBLICADO` diz qual). Não se
somam datas: a mesma venda reaparece em cada foto.
⚠️ **Quantidade = `SUM(QTD_REGISTROS)`** (linhas da query). `QTD_PROPOSTAS_DISTINTAS`
é por grupo e não se soma como distinto global; os JOINs podem multiplicar linhas
e isso não é removido aqui.
⚠️ Prêmio em `Decimal`; telefones `int` (0/NULL/vazio = sem contato).

Placeholder `?` (pyodbc) — árvore `api/`. Tudo atrás de `tela_caixa_seguro`.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query

from db import get_db_conn
from deps import require_perm
from routers.pio import _filtro_da_busca
from routers.pio_card1 import (
    _BUSCA, _COLUNAS_ITEM, _LIMITE_MAXIMO, _LIMITE_PADRAO,
    _dinheiro, _identificar, _idade, _item, _resposta_base,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# Nomes de objeto fixos: não aceitam parâmetro em T-SQL e nunca vêm da requisição.
AGG = "dbo.AGG_ORQ_CARD02_FOTO"
FAT = "dbo.FAT_ORQ_CARD02_FOTO"
CTL = "dbo.CTL_ORQ_CARD02_LOTE"


def _foto(cur, data: date | None):
    """A foto publicada: a de `data`, ou a mais recente. `None` se não houver.
    O CTL diz qual lote vale — nunca `MAX(DTA_MOVIMENTO)` em AGG/FAT."""
    filtro, params = ("", [])
    if data is not None:
        filtro, params = (" AND DTA_MOVIMENTO = ?", [data])
    cur.execute(
        f"SELECT TOP 1 DTA_MOVIMENTO, LOTE_ID, DTH_PUBLICACAO FROM {CTL}"
        f" WHERE STATUS = 'PUBLICADO'{filtro}"
        " ORDER BY DTA_MOVIMENTO DESC, DTH_PUBLICACAO DESC", params)
    return cur.fetchone()


def _fechar(conn) -> None:
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


@router.get("/pio/card2/resumo", dependencies=[Depends(_require_caixa)])
def pio_card2_resumo(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Prêmio e quantidade do Card 2 na foto — lendo só a AGREGADA.

    `disponivel=false` é "não consegui ler"; `disponivel=true` com `quantidade=0`
    é "li a foto e não há pendência". `desatualizado` = foto de dia anterior.
    """
    resposta = _resposta_base()
    resposta.update({"premio_total": None, "quantidade": 0, "grupos": 0})
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        agregado = None
        if foto:
            cur.execute(
                "SELECT COALESCE(SUM(QTD_REGISTROS), 0), SUM(VLR_PREMIO_TOTAL), COUNT_BIG(*)"
                f" FROM {AGG} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?",
                [foto[0], foto[1]])
            agregado = cur.fetchone()
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card2: resumo indisponível (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if foto and agregado:
        _identificar(resposta, foto)
        resposta["quantidade"] = int(agregado[0] or 0)
        resposta["premio_total"] = _dinheiro(agregado[1]) or 0.0
        resposta["grupos"] = int(agregado[2] or 0)
    return resposta


@router.get("/pio/card2/propostas", dependencies=[Depends(_require_caixa)])
def pio_card2_propostas(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
    busca: str = Query("", description="termo da busca"),
    modo: str = Query("livre", description="livre | proposta | cpf | agencia | matricula"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de propostas do Card 2 na foto, mais antigas primeiro — lendo a FAT.

    Passe `data` (a do `/resumo`) para número e lista serem da mesma foto.
    `detalhe_disponivel=false` quando a foto existe no agregado mas a fato já
    saiu da retenção (fato 24 meses, agregado 36). Dados pessoais: atrás de
    `tela_caixa_seguro`, no máximo `limite` linhas por resposta.
    """
    resposta = _resposta_base(limite, offset)
    filtro_busca, params_busca = _filtro_da_busca((modo or "").strip().lower(), busca, _BUSCA)
    conn = None
    linhas, foto, qtd_agregada = [], None, 0
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        if foto:
            chave = [foto[0], foto[1]]
            cur.execute(
                f"SELECT COUNT_BIG(*) FROM {FAT} f"
                f" WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ?{filtro_busca}",
                chave + params_busca)
            total = cur.fetchone()
            resposta["total"] = int(total[0]) if total else 0

            if resposta["total"] == 0 and not filtro_busca:
                cur.execute(
                    f"SELECT COALESCE(SUM(QTD_REGISTROS), 0) FROM {AGG}"
                    " WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?", chave)
                agg = cur.fetchone()
                qtd_agregada = int(agg[0] or 0) if agg else 0

            colunas = ", ".join(
                "DATEDIFF(day, f.DTH_VENDA, f.DTA_MOVIMENTO)" if c == "DIAS_PENDENTE"
                else f"f.{c}" for c in _COLUNAS_ITEM)
            # ID_FOTO fecha a ordenação: a query repete proposta (JOIN) e, sem
            # desempate, a página 2 repete/pula linhas.
            cur.execute(
                f"SELECT {colunas} FROM {FAT} f"
                f" WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ?{filtro_busca}"
                " ORDER BY f.DTH_VENDA ASC, f.COD_PROPOSTA ASC, f.ID_FOTO ASC"
                " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                chave + params_busca + [offset, limite])
            linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card2: propostas indisponíveis (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if not foto:
        return resposta
    referencia = _identificar(resposta, foto)
    resposta["detalhe_disponivel"] = not (resposta["total"] == 0 and qtd_agregada > 0)
    for linha in linhas:
        item = _item(linha)
        nasc = item.pop("nascimento")
        item["idade"] = _idade(nasc, referencia) if isinstance(referencia, date) else None
        resposta["itens"].append(item)
    return resposta
