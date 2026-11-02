"""api/routers/pio_card5.py — Card 5 (Emitidas, VIDA = VG + AP) lendo a FOTO diária.

  GET /pio/card5/resumo     — prêmio e quantidade do card (tabela AGREGADA)
  GET /pio/card5/propostas  — lista paginada do drill-down (tabela ANALÍTICA)

RITM0118510 (SCTASK0120198). Mesmo padrão dos Cards 1–4 (helpers de
`routers/pio_card1.py`); a carga é o pipeline Fabric do Card 5 (07:30), que publica
uma foto por `DTA_MOVIMENTO` no DMDB41 — esta API só LÊ:

    dbo.AGG_ORQ_CARD05_FOTO   grupos pré-agregados → número do card
    dbo.FAT_ORQ_CARD05_FOTO   UMA LINHA POR CONTRATO (SEGMENTO + NUM_SIVPF) → lista
    dbo.CTL_ORQ_CARD05_LOTE   controle: qual lote está PUBLICADO em cada data

⚠️ **A foto é um ESTOQUE do ano corrente, não "vendas novas do dia"**. Fotos de dias
diferentes nunca se somam. Uma foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`;
nada de GETDATE/MAX/janela de datas aqui (o ano corrente é da CARGA).
⚠️ A chave do contrato é (`SEGMENTO`, `NUM_SIVPF`): o mesmo número pode existir em VG
(certificado) e AP (apólice). `NUM_SIVPF` NÃO é um número de proposta distinto — a
tela o rotula "Proposta/Certificado" (decisão do usuário, 02/11).
⚠️ Prêmio e IS podem ser NULL (preservado pela carga). `QTD_PREMIOS_INFORMADOS` diz
quantos contratos têm prêmio: sem nenhum, o prêmio do card é desconhecido, não zero.
⚠️ UF/cidade da query são da AGÊNCIA DE COBRANÇA, não do segurado (e em AP a agência
pode faltar): seguem em campos próprios e `uf`/`cidade` ficam vazios.

Cor do selo de status (única regra, aqui): CANCELADA → `cancelada` (vermelho);
COBERTURA SUSPENSA → `suspensa` (amarelo); o restante → `emitida` (azul). Códigos:
VG `4` cancelada, VG `6` suspensa, AP `2` cancelada (`DES_COD_SIT_CONTRATO`).
O motivo do cancelamento só sai quando `SIT_CONTRATO = 'Inativo'`.

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
    _LIMITE_MAXIMO, _LIMITE_PADRAO, _data_iso, _dinheiro, _idade, _identificar,
    _resposta_base, _telefone, _texto,
)
from routers.pio_card4 import _busca_sem_zeros, _documento, _inteiro_texto

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# Nomes de objeto fixos: não aceitam parâmetro em T-SQL e nunca vêm da requisição.
AGG = "dbo.AGG_ORQ_CARD05_FOTO"
FAT = "dbo.FAT_ORQ_CARD05_FOTO"
CTL = "dbo.CTL_ORQ_CARD05_LOTE"

_BUSCA = {
    "COD_PROPOSTA": "f.NUM_SIVPF",
    "NOM_PESSOA": "f.NOM_PESSOA",
    "COD_CPF": "f.COD_CPF_CNPJ",
    "NUM_AGENCIA": "f.NUM_AGENCIA",
    "NUM_MATRICULA": "f.NUM_MATRI_VENDEDOR",
}

# `ID_FOTO` é a PK IDENTITY da FAT (DDL da carga: `ID_FOTO bigint IDENTITY PRIMARY KEY`), única por
# linha — vale para a chave React e para `foto.idFoto`, mesmo com o mesmo NUM_SIVPF em VG e AP.
# Ordem do SELECT da lista — e a ordem em que `_item` lê cada linha.
_NOMES = (
    "ID_FOTO", "SEGMENTO", "NUM_SIVPF", "NOM_PESSOA", "COD_CPF_CNPJ", "NOM_PESSOA_PROD",
    "NUM_AGENCIA", "NUM_MATRI_VENDEDOR", "DTH_VENDA", "DTH_EMISSAO", "DTH_NASCIMENTO",
    "NOM_PRODUTO", "DES_RAMO_PRODUTO", "VLR_CONTRATO", "VLR_IS_VENDA",
    "NOM_CIDADE_AGENCIA", "SIG_UF_AGENCIA", "NOM_SUB_SITUACAO", "SIT_CONTRATO",
    "DES_COD_SIT_CONTRATO", "DTH_CANCELAMENTO", "MOT_CANCELAMENTO", "DES_EMAIL",
    "COD_DDD_CONTATO", "COD_CONTATO", "TIP_CONTATO",
)
_COLUNAS_LISTA = tuple(f"f.{n}" for n in _NOMES)


def tom_do_status(segmento, cod_situacao) -> str:
    """`cancelada` | `suspensa` | `emitida` — a regra da cor do selo (ver docstring)."""
    seg = (_texto(segmento) or "").upper()
    cod = (_texto(cod_situacao) or "").upper()
    if (seg == "VG" and cod == "4") or (seg == "AP" and cod == "2"):
        return "cancelada"
    if seg == "VG" and cod == "6":
        return "suspensa"
    return "emitida"


def _item(linha, referencia: date | None) -> dict:
    r = dict(zip(_NOMES, linha))
    tom = tom_do_status(r["SEGMENTO"], r["DES_COD_SIT_CONTRATO"])
    inativo = (_texto(r["SIT_CONTRATO"]) or "").lower() == "inativo"
    contato = _telefone(r["COD_DDD_CONTATO"], r["COD_CONTATO"])
    celular = (_texto(r["TIP_CONTATO"]) or "").lower() == "celular"
    return {
        "id_foto": int(r["ID_FOTO"]),
        "segmento": (_texto(r["SEGMENTO"]) or "").upper(),
        "proposta": _inteiro_texto(r["NUM_SIVPF"]),
        "nome": _texto(r["NOM_PESSOA"]) or "",
        "cpf": _documento(r["COD_CPF_CNPJ"], r["NOM_PESSOA_PROD"]),
        "agencia": _inteiro_texto(r["NUM_AGENCIA"]),
        "matricula": _inteiro_texto(r["NUM_MATRI_VENDEDOR"]),
        "data_venda": _data_iso(r["DTH_VENDA"]),
        "dias_pendente": 0,     # já emitida: não há "dias pendente"
        "produto": _texto(r["NOM_PRODUTO"]) or "",
        "area_produto": _texto(r["DES_RAMO_PRODUTO"]) or "",
        "premio": _dinheiro(r["VLR_CONTRATO"]),
        "imp_segurada": _dinheiro(r["VLR_IS_VENDA"]),
        "renda": None,
        "cidade": "",
        "uf": "",
        "cidade_agencia": _texto(r["NOM_CIDADE_AGENCIA"]) or "",
        "uf_agencia": _texto(r["SIG_UF_AGENCIA"]) or "",
        "nascimento": r["DTH_NASCIMENTO"],
        "situacao": "",
        "assinatura": "",
        "pago": "",
        "sub_situacao": _texto(r["NOM_SUB_SITUACAO"]) or "",
        "tom_status": tom,
        "inativo": inativo,
        "emissao": _data_iso(r["DTH_EMISSAO"]),
        "cancelamento": _data_iso(r["DTH_CANCELAMENTO"]) if inativo else None,
        "motivo_cancelamento": (_texto(r["MOT_CANCELAMENTO"]) if inativo else None),
        # A fonte tem UM contato por contrato (celular se houver, senão fixo).
        "contato": {
            "email": _texto(r["DES_EMAIL"]),
            "celular": contato if celular else None,
            "residencial": None if celular else contato,
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


@router.get("/pio/card5/resumo", dependencies=[Depends(_require_caixa)])
def pio_card5_resumo(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Prêmio e quantidade de contratos do Card 5 na foto — lendo só a AGREGADA.

    `quantidade` = `SUM(QTD_CONTRATOS)`; `premio_total` = `SUM(VLR_PREMIO_TOTAL)`, ou
    `None` se nenhum contrato tem prêmio informado. `disponivel=false` é "não consegui
    ler"; `disponivel=true` com `quantidade=0` é "li a foto e não há".
    """
    resposta = _resposta_base()
    resposta.update({"premio_total": None, "quantidade": 0, "grupos": 0, "premios_informados": 0})
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        agregado = None
        if foto:
            cur.execute(
                "SELECT COALESCE(SUM(QTD_CONTRATOS), 0), SUM(VLR_PREMIO_TOTAL), COUNT_BIG(*),"
                " COALESCE(SUM(QTD_PREMIOS_INFORMADOS), 0)"
                f" FROM {AGG} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?",
                [foto[0], foto[1]])
            agregado = cur.fetchone()
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card5: resumo indisponível (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if foto and agregado:
        _identificar(resposta, foto)
        resposta["quantidade"] = int(agregado[0] or 0)
        resposta["grupos"] = int(agregado[2] or 0)
        informados = int(agregado[3] or 0)
        resposta["premios_informados"] = informados   # < quantidade = prêmio parcial
        # Sem nenhum prêmio informado o total é desconhecido; com algum, a soma vale.
        resposta["premio_total"] = (_dinheiro(agregado[1]) or 0.0) if informados > 0 else (
            0.0 if resposta["quantidade"] == 0 else None)
    return resposta


@router.get("/pio/card5/propostas", dependencies=[Depends(_require_caixa)])
def pio_card5_propostas(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
    busca: str = Query("", description="termo da busca"),
    modo: str = Query("livre", description="livre | proposta | cpf | agencia | matricula"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de contratos do Card 5 na foto, mais antigos primeiro — lendo a FAT.

    Passe `data` (a do `/resumo`) para número e lista serem da mesma foto.
    `detalhe_disponivel=false` quando a foto existe no agregado mas a fato já saiu da
    retenção (fato 24 meses, agregado 36). Dados pessoais: atrás de `tela_caixa_seguro`,
    no máximo `limite` linhas por resposta, nada em log.
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
            chave = [foto[0], foto[1]]
            # Chave única da foto = (DTA_MOVIMENTO, SEGMENTO, NUM_SIVPF): COUNT_BIG(*) é
            # a quantidade de contratos (a carga bloqueia o lote se houver duplicidade).
            cur.execute(
                f"SELECT COUNT_BIG(*) FROM {FAT} f"
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

            # SEGMENTO + NUM_SIVPF fecham a ordenação: a página 2 não repete nem pula.
            cur.execute(
                f"SELECT {', '.join(_COLUNAS_LISTA)} FROM {FAT} f"
                f" WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ?{filtro_busca}"
                " ORDER BY f.DTH_VENDA ASC, f.SEGMENTO ASC, f.NUM_SIVPF ASC"
                " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                chave + params_busca + [offset, limite])
            linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card5: propostas indisponíveis (%s: %s)", type(e).__name__, e)
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
