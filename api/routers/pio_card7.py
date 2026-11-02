"""api/routers/pio_card7.py — Card 7 (Devolução de Prêmio, VG + AP) lendo a FOTO diária.

  GET /pio/card7/resumo      — valor devolvido + contratos, total e por sub-card (AGREGADA)
  GET /pio/card7/propostas   — lista paginada de UM sub-card, um contrato por linha (ANALÍTICA)
  GET /pio/card7/devolucao   — dados da devolução e bancários de UM contrato (ANALÍTICA)

RITM0118567. Mesmo padrão dos Cards 1–6 (helpers de `routers/pio_card1.py`); a carga é o
pipeline Fabric do Card 7 (07:30) e esta API só LÊ:

    dbo.AGG_ORQ_CARD07_FOTO   grupos pré-agregados → números do card e dos 3 sub-cards
    dbo.FAT_ORQ_CARD07_FOTO   UMA LINHA POR CONTRATO (chave SEGMENTO + certificado|bilhete)
    dbo.CTL_ORQ_CARD07_LOTE   controle: qual lote está PUBLICADO em cada data

Os 3 sub-cards (decisão do usuário, 02/11) classificam o ÚLTIMO movimento de devolução:
  realizada  = VG código 1 (crédito efetivado) ou F (finalizado) · AP código 2
  andamento  = VG 3 (enviado, aguarda retorno) · VG 7 (reprogramado) · VG 8 processando
  pendente   = todo o resto: sem movimento (NULL), VG 0, VG 2 (retornado com pendência) e
               VG 8 cancelado (restrição na conta). Código desconhecido cai em pendente — assim
               os 3 sub-cards SEMPRE somam o total do card.
O VG 8 "cancelado" vs "processando" vem de `DES_SIT_MOVIMENTO` (a origem usa CODRET, que não
é guardado). A regra mora aqui, num só lugar (`_BUCKET`), para AGG e FAT.

⚠️ `VLR_DEVOLUCAO` NÃO é prêmio. O total do card inclui TODOS os status (pendentes e cancelados
também). Crédito efetivado é só o sub-card "realizada". Valor NULL é desconhecido, nunca zero.
⚠️ Uma foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; fotos de dias diferentes nunca se
somam. O ano/regra de período (VG: declínio ≥ início do ano; AP: venda no ano) é da CARGA.
⚠️ Dados bancários (banco, agência, conta) ficam FORA da lista: só o endpoint `/devolucao`, que
abre o Resumo de UM contrato, os devolve. Nada disso vai para log.
⚠️ A foto NÃO traz e-mail, telefone, celular, nome do banco nem dígito da agência; o front mostra
"não disponível", nunca inventa. UF é da agência; não há cidade nesta query.

Placeholder `?` (pyodbc) — árvore `api/`. Tudo atrás de `tela_caixa_seguro`.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from db import get_db_conn
from deps import require_perm
from routers.pio import _filtro_da_busca
from routers.pio_card1 import (
    _LIMITE_MAXIMO, _LIMITE_PADRAO, _data_iso, _dinheiro, _idade, _identificar,
    _resposta_base, _texto,
)
from routers.pio_card4 import _busca_sem_zeros, _documento, _inteiro_texto

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# Nomes de objeto fixos: não aceitam parâmetro em T-SQL e nunca vêm da requisição.
AGG = "dbo.AGG_ORQ_CARD07_FOTO"
FAT = "dbo.FAT_ORQ_CARD07_FOTO"
CTL = "dbo.CTL_ORQ_CARD07_LOTE"

SITUACOES = ("realizada", "andamento", "pendente")
Situacao = Literal["realizada", "andamento", "pendente"]


def _bucket(prefixo: str = "") -> str:
    """O CASE dos 3 sub-cards sobre `SEGMENTO`, `COD_SIT_MOVIMENTO` e `DES_SIT_MOVIMENTO`.
    A mesma expressão serve à AGG (sem prefixo) e à FAT (`f.`): é a regra única."""
    seg, cod, des = f"{prefixo}SEGMENTO", f"{prefixo}COD_SIT_MOVIMENTO", f"{prefixo}DES_SIT_MOVIMENTO"
    return (
        "CASE"
        f" WHEN ({seg} = 'VG' AND {cod} IN ('1', 'F')) OR ({seg} = 'AP' AND {cod} = '2')"
        " THEN 'realizada'"
        f" WHEN {seg} = 'VG' AND ({cod} IN ('3', '7')"
        f" OR ({cod} = '8' AND COALESCE({des}, '') <> 'Cancelado'))"
        " THEN 'andamento'"
        " ELSE 'pendente' END"
    )


_BUSCA = {
    "COD_PROPOSTA": "COALESCE(f.NUM_SIVPF, f.NUM_BILHETE_TITULO)",
    "NOM_PESSOA": "f.NOM_PESSOA",
    "COD_CPF": "f.COD_CPF_CNPJ",
    "NUM_AGENCIA": "f.NUM_AGENCIA",
    "NUM_MATRICULA": "f.NUM_MATRI_VENDEDOR",
}

# Ordem do SELECT da lista — e a ordem em que `_item` lê cada linha. SEM dados bancários.
_NOMES = (
    "ID_FOTO", "SEGMENTO", "NUM_SIVPF", "NUM_BILHETE_TITULO", "NOM_PESSOA", "COD_CPF_CNPJ",
    "NOM_PESSOA_PROD", "NUM_AGENCIA", "NUM_MATRI_VENDEDOR", "DTH_VENDA", "DTH_NASCIMENTO",
    "NOM_PRODUTO", "SIG_UF_AGENCIA", "VLR_DEVOLUCAO", "COD_SIT_MOVIMENTO", "DES_SIT_MOVIMENTO",
    "DES_RETORNO", "DTH_VENCIMENTO_MOV", "DTH_DECLINIO",
)
_COLUNAS_LISTA = tuple(f"f.{n}" for n in _NOMES)


def _numero(r: dict) -> str:
    """O número que identifica o contrato: certificado (VG) ou bilhete (AP)."""
    bruto = r["NUM_SIVPF"] if (_texto(r["SEGMENTO"]) or "").upper() == "VG" else r["NUM_BILHETE_TITULO"]
    return _inteiro_texto(bruto)


def _item(linha, situacao: str) -> dict:
    r = dict(zip(_NOMES, linha))
    return {
        "id_foto": int(r["ID_FOTO"]),
        "segmento": (_texto(r["SEGMENTO"]) or "").upper(),
        "proposta": _numero(r),
        "nome": _texto(r["NOM_PESSOA"]) or "",
        "cpf": _documento(r["COD_CPF_CNPJ"], r["NOM_PESSOA_PROD"]),
        "agencia": _inteiro_texto(r["NUM_AGENCIA"]),
        "matricula": _inteiro_texto(r["NUM_MATRI_VENDEDOR"]),
        "data_venda": _data_iso(r["DTH_VENDA"]),
        "dias_pendente": 0,
        "produto": _texto(r["NOM_PRODUTO"]) or "",
        "area_produto": "",
        "premio": _dinheiro(r["VLR_DEVOLUCAO"]),        # aqui é o valor DEVOLVIDO, não o prêmio
        "imp_segurada": None,
        "renda": None,
        "cidade": "",
        "uf": "",
        "cidade_agencia": "",
        "uf_agencia": _texto(r["SIG_UF_AGENCIA"]) or "",
        "nascimento": r["DTH_NASCIMENTO"],
        "situacao": "",
        "assinatura": "",
        "pago": "",
        "sub_situacao": "",
        # O contato não existe nesta foto: vazio, e o Resumo diz que não está disponível.
        "contato": {"email": None, "celular": None, "residencial": None},
        "devolucao": {
            "situacao": situacao,
            "status": _texto(r["DES_SIT_MOVIMENTO"]) or "Sem Movimento",
            "retorno": _texto(r["DES_RETORNO"]) or "Sem Movimento",
            "data_movimento": _data_iso(r["DTH_VENCIMENTO_MOV"]),
            "declinio": _data_iso(r["DTH_DECLINIO"]),
        },
    }


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


def _vazio_por_situacao() -> dict:
    return {s: {"quantidade": 0, "valor": None, "valores_informados": 0} for s in SITUACOES}


@router.get("/pio/card7/resumo", dependencies=[Depends(_require_caixa)])
def pio_card7_resumo(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Valor devolvido (todos os status) e contratos, no total e por sub-card — só a AGREGADA.

    `premio_total` (nome comum aos cards de foto) = SUM(VLR_DEVOLUCAO_TOTAL) de TODOS os status;
    `quantidade` = SUM(QTD_CONTRATOS). `por_situacao` traz o mesmo por sub-card e SOMA o total.
    `valor` NULL = nenhum contrato do grupo tem valor informado (desconhecido, não zero).
    """
    resposta = _resposta_base()
    resposta.update({"premio_total": None, "quantidade": 0, "grupos": 0, "premios_informados": 0,
                     "por_situacao": _vazio_por_situacao()})
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        linhas = []
        if foto:
            caso = _bucket()
            cur.execute(
                f"SELECT {caso}, COALESCE(SUM(QTD_CONTRATOS), 0), SUM(VLR_DEVOLUCAO_TOTAL),"
                " COALESCE(SUM(QTD_VALORES_INFORMADOS), 0), COUNT_BIG(*)"
                f" FROM {AGG} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?"
                f" GROUP BY {caso}",
                [foto[0], foto[1]])
            linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card7: resumo indisponível (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if not foto:
        return resposta
    _identificar(resposta, foto)
    total_valor, informados_total = 0.0, 0
    for situacao, qtd, valor, informados, grupos in linhas:
        if situacao not in SITUACOES:
            continue
        bloco = resposta["por_situacao"][situacao]
        bloco["quantidade"] = int(qtd or 0)
        bloco["valores_informados"] = int(informados or 0)
        bloco["valor"] = _dinheiro(valor) if int(informados or 0) > 0 else None
        resposta["quantidade"] += int(qtd or 0)
        resposta["grupos"] += int(grupos or 0)
        informados_total += int(informados or 0)
        total_valor += bloco["valor"] or 0.0
    resposta["premios_informados"] = informados_total
    # Sem nenhum valor informado o total é desconhecido; com algum, a soma vale.
    resposta["premio_total"] = round(total_valor, 2) if informados_total > 0 else (
        0.0 if resposta["quantidade"] == 0 else None)
    return resposta


@router.get("/pio/card7/propostas", dependencies=[Depends(_require_caixa)])
def pio_card7_propostas(
    situacao: Situacao = Query(..., description="sub-card: realizada | andamento | pendente"),
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
    busca: str = Query("", description="termo da busca"),
    modo: str = Query("livre", description="livre | proposta | cpf | agencia | matricula"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de contratos de UM sub-card do Card 7 na foto, mais antigos primeiro — lendo a FAT.

    Passe `data` (a do `/resumo`) para número e lista serem da mesma foto. `total` = COUNT_BIG(*)
    do sub-card = `por_situacao[situacao].quantidade` do `/resumo`. `detalhe_disponivel=false`
    quando a foto existe no agregado mas a fato já saiu da retenção (fato 24 meses, agregado 36).
    Sem dados bancários nem contato nesta lista.
    """
    resposta = _resposta_base(limite, offset)
    modo = (modo or "").strip().lower()
    filtro_busca, params_busca = _filtro_da_busca(modo, _busca_sem_zeros(modo, busca), _BUSCA)
    conn = None
    linhas, foto, qtd_agregada = [], None, 0
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        if foto:
            filtro = f" WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ? AND {_bucket('f.')} = ?{filtro_busca}"
            chave = [foto[0], foto[1], situacao]
            cur.execute(f"SELECT COUNT_BIG(*) FROM {FAT} f{filtro}", chave + params_busca)
            total = cur.fetchone()
            resposta["total"] = int(total[0]) if total else 0

            if resposta["total"] == 0 and not filtro_busca:
                cur.execute(
                    f"SELECT COALESCE(SUM(QTD_CONTRATOS), 0) FROM {AGG}"
                    f" WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ? AND {_bucket()} = ?", chave)
                agg = cur.fetchone()
                qtd_agregada = int(agg[0] or 0) if agg else 0

            # SEGMENTO + números + ID_FOTO fecham a ordenação: a página 2 não repete nem pula.
            cur.execute(
                f"SELECT {', '.join(_COLUNAS_LISTA)} FROM {FAT} f{filtro}"
                " ORDER BY f.DTH_VENDA ASC, f.SEGMENTO ASC, f.NUM_SIVPF ASC,"
                " f.NUM_BILHETE_TITULO ASC, f.ID_FOTO ASC"
                " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                chave + params_busca + [offset, limite])
            linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card7: propostas indisponíveis (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    resposta["situacao"] = situacao
    if not foto:
        return resposta
    referencia = _identificar(resposta, foto)
    resposta["detalhe_disponivel"] = not (resposta["total"] == 0 and qtd_agregada > 0)
    for linha in linhas:
        item = _item(linha, situacao)
        nasc = item.pop("nascimento")
        item["idade"] = _idade(nasc, referencia) if isinstance(referencia, date) else None
        resposta["itens"].append(item)
    return resposta


@router.get("/pio/card7/devolucao", dependencies=[Depends(_require_caixa)])
def pio_card7_devolucao(
    segmento: Literal["VG", "AP"] = Query(..., description="VG (certificado) ou AP (bilhete)"),
    numero: int = Query(..., ge=1, le=999_999_999_999_999, description="NUM_SIVPF (VG) ou NUM_BILHETE_TITULO (AP); numeric(15,0)"),
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Dados da devolução e BANCÁRIOS de UM contrato, na foto — lendo a FAT.

    É o único lugar que devolve banco/agência/conta; abre só no Resumo do contrato. `encontrado`
    = a linha existe na foto. Campos ausentes na fonte vêm `null` (a tela diz "não informado").
    O nome do banco e o dígito da agência NÃO existem na foto: só o código do banco.
    """
    resposta = _resposta_base()
    resposta.update({"segmento": segmento, "numero": numero, "encontrado": False, "devolucao": None})
    chave_col = "f.NUM_SIVPF" if segmento == "VG" else "f.NUM_BILHETE_TITULO"
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        linha = None
        if foto:
            cur.execute(
                "SELECT f.VLR_DEVOLUCAO, f.COD_SIT_MOVIMENTO, f.DES_SIT_MOVIMENTO, f.DES_RETORNO,"
                " f.DTH_VENCIMENTO_MOV, f.DTH_LANCAMENTO, f.NUM_PARCELA, f.COD_BANCO,"
                " f.COD_AGENCIA_MOV, f.OPE_CONTA_DEBITO, f.NUM_CONTA_DEBITO, f.DIG_CONTA_DEBITO,"
                " f.NOM_FORMA_PAGAMENTO, f.SEGMENTO, f.COD_SIT_MOVIMENTO,"
                f" {_bucket('f.')}"
                f" FROM {FAT} f WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ? AND f.SEGMENTO = ?"
                f" AND {chave_col} = ?",
                [foto[0], foto[1], segmento, numero])
            linha = cur.fetchone()
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card7: devolução indisponível (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if foto:
        _identificar(resposta, foto)
    if linha:
        (valor, cod, des, ret, dia_mov, dia_lanc, parcela, banco, agencia, operacao, conta,
         digito, forma, _seg, _cod2, situacao) = linha
        resposta["encontrado"] = True
        resposta["devolucao"] = {
            "situacao": situacao,
            "valor": _dinheiro(valor),
            "status": _texto(des) or "Sem Movimento",
            "retorno": _texto(ret) or "Sem Movimento",
            "codigo_movimento": _texto(cod),
            "data_movimento": _data_iso(dia_mov),
            "data_lancamento": _data_iso(dia_lanc),
            "parcela": int(parcela) if parcela is not None else None,
            "forma_pagamento": _texto(forma),
            "banco": _inteiro_texto(banco) if banco is not None else None,
            "agencia": _inteiro_texto(agencia) if agencia is not None else None,
            "operacao": _inteiro_texto(operacao) if operacao is not None else None,
            "conta": _inteiro_texto(conta) if conta is not None else None,
            "digito_conta": _inteiro_texto(digito) if digito is not None else None,
        }
    return resposta
