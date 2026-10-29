"""api/routers/pio_card4.py — Card 4 (Em Análise = críticas Vida em Grupo) lendo a FOTO diária.

  GET /pio/card4/resumo      — contratos, prêmio e nº de críticas (tabela AGREGADA)
  GET /pio/card4/propostas   — lista paginada, UMA LINHA POR CERTIFICADO (tabela ANALÍTICA)
  GET /pio/card4/pendencias  — as mensagens de crítica de UM certificado

Mesmo padrão dos Cards 1–3 (helpers de `routers/pio_card1.py`), com uma diferença que
muda tudo: a unidade é o **certificado** (`NUM_SIVPF`). A FAT guarda UMA LINHA POR
MENSAGEM DE CRÍTICA e o mesmo certificado repete; o prêmio (`VLR_CONTRATO`) repete
junto. Por isso:

    dbo.AGG_ORQ_CARD04_FOTO   certificado já consolidado → número do card
    dbo.FAT_ORQ_CARD04_FOTO   uma linha por crítica → lista (agrupada), pendências
    dbo.CTL_ORQ_CARD04_LOTE   controle: qual lote está PUBLICADO em cada data

⚠️ **Nunca somar `VLR_CONTRATO` nem contar linhas da FAT para o card**: o contrato
entra uma vez. `QTD_CONTRATOS` e `VLR_PREMIO_TOTAL` da AGG já vêm sem repetição (a
carga bloqueia a publicação se o prêmio ou o contexto do certificado forem ambíguos);
`QTD_CRITICAS` conta mensagens, não eventos únicos.
⚠️ **Uma foto = `DTA_MOVIMENTO` + `LOTE_ID`**. Não se somam datas nem se reaplica
GETDATE/D-30 (o D-30 é da CARGA).
⚠️ UF/cidade da query são da AGÊNCIA DE COBRANÇA, não do segurado: seguem em campos
próprios (`uf_agencia`/`cidade_agencia`) e `uf`/`cidade` ficam vazios, para a "região"
da lista não passar a significar outra coisa nos Cards 1–3 e no 4.

Placeholder `?` (pyodbc) — árvore `api/`. Tudo atrás de `tela_caixa_seguro`.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from db import get_db_conn
from deps import require_perm
from routers.pio import _filtro_da_busca
from routers.pio_card1 import (
    _LIMITE_MAXIMO, _LIMITE_PADRAO, _data_iso, _dinheiro, _idade, _identificar,
    _resposta_base, _telefone, _texto,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# Nomes de objeto fixos: não aceitam parâmetro em T-SQL e nunca vêm da requisição.
AGG = "dbo.AGG_ORQ_CARD04_FOTO"
FAT = "dbo.FAT_ORQ_CARD04_FOTO"
CTL = "dbo.CTL_ORQ_CARD04_LOTE"

# Colunas da FAT que o filtro de busca conhece (o "proposta" é o certificado).
_BUSCA = {
    "COD_PROPOSTA": "f.NUM_SIVPF",
    "NOM_PESSOA": "f.NOM_PESSOA",
    "COD_CPF": "f.COD_CPF_CNPJ",
    "NUM_AGENCIA": "f.NUM_AGENCIA",
    "NUM_MATRICULA": "f.NUM_MATRI_VENDEDOR",
}

# Ordem do SELECT da lista — e a ordem em que `_item` lê cada linha. Cada coluna
# é MIN() porque a carga provou que o contexto do certificado é único.
_COLUNAS_LISTA = (
    "MIN(f.ID_FOTO)", "f.NUM_SIVPF", "MIN(f.NOM_PESSOA)", "MIN(f.COD_CPF_CNPJ)",
    "MIN(f.NOM_PESSOA_PROD)", "MIN(f.NUM_AGENCIA)", "MIN(f.NUM_MATRI_VENDEDOR)",
    "MIN(f.DTH_VENDA)", "MIN(f.DTH_NASCIMENTO)", "MIN(f.NOM_PRODUTO)",
    "MIN(f.DES_RAMO_PRODUTO)", "MIN(f.VLR_CONTRATO)", "MIN(f.VLR_IS_VENDA)",
    "MIN(f.NOM_CIDADE_AGENCIA)", "MIN(f.SIG_UF_AGENCIA)", "MIN(f.NOM_SUB_SITUACAO)",
    "COUNT_BIG(*)", "MIN(f.DTH_QUITACAO)", "MIN(f.DES_EMAIL)",
    "MIN(f.COD_DDD_TELEFONE)", "MIN(f.COD_TELEFONE)",
    "MIN(f.COD_DDD_CELULAR)", "MIN(f.NUM_CELULAR)",
)
_NOMES = (
    "ID_FOTO", "NUM_SIVPF", "NOM_PESSOA", "COD_CPF_CNPJ", "NOM_PESSOA_PROD",
    "NUM_AGENCIA", "NUM_MATRI_VENDEDOR", "DTH_VENDA", "DTH_NASCIMENTO", "NOM_PRODUTO",
    "DES_RAMO_PRODUTO", "VLR_CONTRATO", "VLR_IS_VENDA", "NOM_CIDADE_AGENCIA",
    "SIG_UF_AGENCIA", "NOM_SUB_SITUACAO", "QTD_CRITICAS", "DTH_QUITACAO", "DES_EMAIL",
    "COD_DDD_TELEFONE", "COD_TELEFONE", "COD_DDD_CELULAR", "NUM_CELULAR",
)


def _inteiro_texto(valor, largura: int = 0) -> str:
    """`numeric(n,0)` → texto de dígitos (sem `.0`), com zeros à esquerda se pedido."""
    if valor is None:
        return ""
    digitos = str(int(Decimal(str(valor))))
    return digitos.zfill(largura) if largura else digitos


def _documento(valor, tipo_pessoa) -> str:
    """CPF/CNPJ numérico perde os zeros à esquerda: PF volta a 11 dígitos, PJ a 14."""
    if valor is None:
        return ""
    return _inteiro_texto(valor, 14 if (_texto(tipo_pessoa) or "").upper() == "PJ" else 11)


def _item(linha, referencia: date | None) -> dict:
    r = dict(zip(_NOMES, linha))
    venda = r["DTH_VENDA"] if isinstance(r["DTH_VENDA"], date) else None
    dias = (referencia - venda).days if venda and isinstance(referencia, date) else 0
    nasc = r["DTH_NASCIMENTO"]
    return {
        "id_foto": int(r["ID_FOTO"]),
        "proposta": _inteiro_texto(r["NUM_SIVPF"]),
        "nome": _texto(r["NOM_PESSOA"]) or "",
        "cpf": _documento(r["COD_CPF_CNPJ"], r["NOM_PESSOA_PROD"]),
        "agencia": _inteiro_texto(r["NUM_AGENCIA"]),
        "matricula": _inteiro_texto(r["NUM_MATRI_VENDEDOR"]),
        "data_venda": _data_iso(r["DTH_VENDA"]),
        "dias_pendente": max(dias, 0),
        "produto": _texto(r["NOM_PRODUTO"]) or "",
        "area_produto": _texto(r["DES_RAMO_PRODUTO"]) or "",
        "premio": _dinheiro(r["VLR_CONTRATO"]),
        "imp_segurada": _dinheiro(r["VLR_IS_VENDA"]),
        "renda": None,
        # Geografia da AGÊNCIA DE COBRANÇA: campos próprios; uf/cidade (do segurado
        # nos Cards 1–3) ficam vazios aqui.
        "cidade": "",
        "uf": "",
        "cidade_agencia": _texto(r["NOM_CIDADE_AGENCIA"]) or "",
        "uf_agencia": _texto(r["SIG_UF_AGENCIA"]) or "",
        "nascimento": nasc,
        "situacao": "",
        "assinatura": "",
        "pago": "",
        "sub_situacao": _texto(r["NOM_SUB_SITUACAO"]) or "",
        "criticas": int(r["QTD_CRITICAS"] or 0),
        "quitacao": _data_iso(r["DTH_QUITACAO"]),
        "contato": {
            "email": _texto(r["DES_EMAIL"]),
            "celular": _telefone(r["COD_DDD_CELULAR"], r["NUM_CELULAR"]),
            "residencial": _telefone(r["COD_DDD_TELEFONE"], r["COD_TELEFONE"]),
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


@router.get("/pio/card4/resumo", dependencies=[Depends(_require_caixa)])
def pio_card4_resumo(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Contratos (certificados), prêmio sem repetição e nº de críticas — só a AGREGADA.

    `quantidade` = `SUM(QTD_CONTRATOS)` (aditiva: um certificado não entra em dois
    grupos); `criticas` = `SUM(QTD_CRITICAS)` (mensagens). `disponivel=false` é
    "não consegui ler"; `disponivel=true` com `quantidade=0` é "li a foto e não há".
    """
    resposta = _resposta_base()
    resposta.update({"premio_total": None, "quantidade": 0, "grupos": 0, "criticas": 0})
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        agregado = None
        if foto:
            cur.execute(
                "SELECT COALESCE(SUM(QTD_CONTRATOS), 0), SUM(VLR_PREMIO_TOTAL), COUNT_BIG(*),"
                " COALESCE(SUM(QTD_CRITICAS), 0)"
                f" FROM {AGG} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?",
                [foto[0], foto[1]])
            agregado = cur.fetchone()
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card4: resumo indisponível (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if foto and agregado:
        _identificar(resposta, foto)
        resposta["quantidade"] = int(agregado[0] or 0)
        resposta["premio_total"] = _dinheiro(agregado[1]) or 0.0
        resposta["grupos"] = int(agregado[2] or 0)
        resposta["criticas"] = int(agregado[3] or 0)
    return resposta


@router.get("/pio/card4/propostas", dependencies=[Depends(_require_caixa)])
def pio_card4_propostas(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
    busca: str = Query("", description="termo da busca"),
    modo: str = Query("livre", description="livre | proposta | cpf | agencia | matricula"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de CERTIFICADOS do Card 4 na foto, mais antigos primeiro — lendo a FAT.

    Uma linha por certificado (a FAT tem uma por crítica). `total` =
    `COUNT(DISTINCT NUM_SIVPF)`, igual à `quantidade` do `/resumo` da mesma foto.
    `detalhe_disponivel=false` quando a foto existe no agregado mas a fato já saiu
    da retenção (fato 24 meses, agregado 36).
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
                f"SELECT COUNT(DISTINCT f.NUM_SIVPF) FROM {FAT} f"
                f" WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ?{filtro_busca}",
                chave + params_busca)
            total = cur.fetchone()
            resposta["total"] = int(total[0]) if total else 0

            if resposta["total"] == 0 and not filtro_busca:
                cur.execute(
                    f"SELECT COALESCE(SUM(QTD_CONTRATOS), 0) FROM {AGG}"
                    " WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?", chave)
                agg = cur.fetchone()
                qtd_agregada = int(agg[0] or 0) if agg else 0

            # NUM_SIVPF fecha a ordenação: a página 2 não repete nem pula certificado.
            cur.execute(
                f"SELECT {', '.join(_COLUNAS_LISTA)} FROM {FAT} f"
                f" WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ?{filtro_busca}"
                " GROUP BY f.NUM_SIVPF"
                " ORDER BY MIN(f.DTH_VENDA) ASC, f.NUM_SIVPF ASC"
                " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                chave + params_busca + [offset, limite])
            linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card4: propostas indisponíveis (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if not foto:
        return resposta
    referencia = _identificar(resposta, foto)
    resposta["detalhe_disponivel"] = not (resposta["total"] == 0 and qtd_agregada > 0)
    for linha in linhas:
        item = _item(linha, referencia)
        nasc = item.pop("nascimento")
        item["idade"] = _idade(nasc, referencia) if isinstance(referencia, date) else None
        resposta["itens"].append(item)
    return resposta


@router.get("/pio/card4/pendencias", dependencies=[Depends(_require_caixa)])
def pio_card4_pendencias(
    certificado: int = Query(..., ge=1, description="NUM_SIVPF"),
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """As mensagens de crítica de UM certificado, na foto — lendo a FAT.

    Só LEITURA: o mapa `COD_MSG_CRITICA → ação (Upload/Samplemed)` ainda não foi
    definido pelo negócio e nenhuma ação é inferida do texto. Dados pessoais não
    saem aqui (só mensagem, complemento, data e valores do contrato).
    """
    resposta = _resposta_base()
    resposta.update({"certificado": certificado, "itens": []})
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        linhas = []
        if foto:
            cur.execute(
                "SELECT f.COD_MSG_CRITICA, f.DES_MSG_CRITICA, f.DES_COMPLEMENTAR, f.DTH_CRITICA,"
                " f.VLR_IS_VENDA, f.VLR_CONTRATO"
                f" FROM {FAT} f WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ? AND f.NUM_SIVPF = ?"
                " ORDER BY f.DTH_CRITICA DESC, f.COD_MSG_CRITICA, f.ID_FOTO",
                [foto[0], foto[1], certificado])
            linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card4: pendências indisponíveis (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if foto:
        _identificar(resposta, foto)
    for cod, descricao, complemento, dia, imp, premio in linhas:
        resposta["itens"].append({
            "codigo": int(cod) if cod is not None else None,
            "descricao": _texto(descricao) or "",
            "complemento": _texto(complemento) or "",
            "data_critica": _data_iso(dia),
            "imp_segurada": _dinheiro(imp),
            "premio": _dinheiro(premio),
        })
    return resposta
