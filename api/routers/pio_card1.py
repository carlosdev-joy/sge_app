"""api/routers/pio_card1.py — Card 1 (Pendentes de Assinatura) lendo a FOTO diária.

  GET /pio/card1/resumo     — prêmio e quantidade do card (tabela AGREGADA)
  GET /pio/card1/propostas  — lista paginada do drill-down (tabela ANALÍTICA)

Substitui, SÓ para o Card 1, a leitura de `dbo.PIO_AGG` / `PIO_PROPOSTA_PENDENTE_DET`
(`routers/pio.py`, intocado: os outros sete cards e a busca em todos os cards
seguem nele). A carga é o pipeline Fabric `PL_ORQ_CARD01_FOTO_DIARIA` (07:30), que
publica uma foto por `DTA_MOVIMENTO` em três tabelas do DMDB41 — esta API só LÊ:

    dbo.AGG_ORQ_CARD01_FOTO   grupos pré-agregados → número do card (performance)
    dbo.FAT_ORQ_CARD01_FOTO   linhas da query aceita → lista, detalhe e contatos
    dbo.CTL_ORQ_CARD01_LOTE   controle: qual lote está PUBLICADO em cada data

⚠️ **Uma foto = `DTA_MOVIMENTO` + `LOTE_ID`.** Toda leitura de AGG e FAT filtra os
dois, resolvidos pelo CTL (`STATUS='PUBLICADO'`). Somar datas conta a mesma venda
mais de uma vez, e um lote substituído ainda pode ter linhas durante a troca. O
filtro D-30 e o `GETDATE()` ficam na CARGA: aqui não se reaplica nenhum dos dois.
Os dias pendentes e a idade são medidos na data da foto, não na de hoje.

⚠️ **Quantidade = `SUM(QTD_REGISTROS)`**, as linhas devolvidas pela query aceita —
a mesma conta do total da lista. `QTD_PROPOSTAS_DISTINTAS` é por grupo e NÃO se
soma como distinto global; não há identificador de "contrato" na fonte. Se a query
passar a multiplicar linhas por JOIN, a quantidade acompanha (risco conhecido).

⚠️ **O prêmio é somado em `Decimal`.** `float` acumula erro de centavo.

⚠️ Os telefones da FAT são `int` (DDD e número). O mapeamento da DET legada faz
`.strip()` neles — aqui não: `NULL`, `0` e texto vazio são "sem contato".

Placeholder `?` (pyodbc) — árvore `api/`. Tudo atrás de `tela_caixa_seguro`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from db import get_db_conn
from deps import require_perm
from routers.pio import _filtro_da_busca

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# Nomes de objeto fixos: não aceitam parâmetro em T-SQL e nunca vêm da requisição.
AGG = "dbo.AGG_ORQ_CARD01_FOTO"
FAT = "dbo.FAT_ORQ_CARD01_FOTO"
CTL = "dbo.CTL_ORQ_CARD01_LOTE"

_FUSO = ZoneInfo("America/Sao_Paulo")
_LIMITE_PADRAO = 50
_LIMITE_MAXIMO = 200

# Colunas da FAT que o filtro de busca do legado conhece, com o alias da lista.
_BUSCA = {
    "COD_PROPOSTA": "f.COD_PROPOSTA",
    "NOM_PESSOA": "f.NOM_PESSOA",
    "COD_CPF": "f.COD_CPF",
    "NUM_AGENCIA": "f.NUM_AGENCIA",
    "NUM_MATRICULA": "f.NUM_MATRICULA",
}

# A ordem do SELECT da lista — e a ordem em que `_item` lê cada linha.
_COLUNAS_ITEM = (
    "ID_FOTO", "COD_PROPOSTA", "COD_VENDA", "NOM_PESSOA", "COD_CPF",
    "NUM_AGENCIA", "NUM_MATRICULA", "DTH_VENDA", "DTA_NASCIMENTO",
    "NOM_PRODUTO", "AREA_PRODUTO", "VLR_PREMIO", "VLR_IMP_SEGURADA",
    "VLR_RENDA_FORMAL", "NOM_CIDADE", "NOM_UF",
    "STA_SITUACAO", "STA_ASSINATURA", "STA_PAGO",
    "NUM_DDD_TEL_RES", "NUM_TEL_RES", "NUM_DDD_TEL_CEL", "NUM_TEL_CEL",
    "DES_EMAIL", "DIAS_PENDENTE",
)


def _texto(valor) -> str | None:
    """Texto aparado; `NULL` e vazio/espaços viram `None` (ausência de verdade,
    nunca a string 'None')."""
    if valor is None:
        return None
    limpo = str(valor).strip()
    return limpo or None


def _dinheiro(valor) -> float | None:
    if valor is None:
        return None
    return float(Decimal(str(valor)).quantize(Decimal("0.01")))


def _data_iso(valor) -> str | None:
    if valor is None:
        return None
    return valor.isoformat()[:10] if hasattr(valor, "isoformat") else str(valor)[:10]


def _telefone(ddd, numero) -> str | None:
    """`(41) 99876-5432` a partir de DDD e número inteiros; sem número, `None`.

    `0` é placeholder de fonte, não telefone. O DDD ausente deixa só o número.
    """
    digitos = "".join(c for c in str(numero if numero is not None else "") if c.isdigit())
    digitos = digitos.lstrip("0") if set(digitos) == {"0"} else digitos
    if not digitos or set(digitos) == {"0"}:
        return None
    corte = max(len(digitos) - 4, 1)
    formatado = f"{digitos[:corte]}-{digitos[corte:]}" if len(digitos) > 4 else digitos
    prefixo = "".join(c for c in str(ddd if ddd is not None else "") if c.isdigit())
    prefixo = "" if not prefixo or set(prefixo) == {"0"} else prefixo
    return f"({prefixo}) {formatado}" if prefixo else formatado


def _idade(nascimento, referencia: date) -> int | None:
    """Idade completa NA DATA DA FOTO (o `DATEDIFF(year)` do legado erra por até
    um ano e usa o dia de hoje)."""
    if not isinstance(nascimento, date) or nascimento > referencia:
        return None
    ja_fez = (referencia.month, referencia.day) >= (nascimento.month, nascimento.day)
    return referencia.year - nascimento.year - (0 if ja_fez else 1)


def _hoje() -> date:
    return datetime.now(_FUSO).date()


def _foto(cur, data: date | None):
    """A foto publicada: a de `data`, ou a mais recente. `None` se não houver.

    O CTL é quem diz qual lote vale — "somente um PUBLICADO por data". Nada de
    `MAX(DTA_MOVIMENTO)` em AGG/FAT: lote aberto ou substituído apareceria.
    """
    filtro, params = ("", [])
    if data is not None:
        filtro, params = (" AND DTA_MOVIMENTO = ?", [data])
    cur.execute(
        f"SELECT TOP 1 DTA_MOVIMENTO, LOTE_ID, DTH_PUBLICACAO FROM {CTL}"
        f" WHERE STATUS = 'PUBLICADO'{filtro}"
        " ORDER BY DTA_MOVIMENTO DESC, DTH_PUBLICACAO DESC", params)
    return cur.fetchone()


def _resposta_base(limite: int | None = None, offset: int | None = None) -> dict:
    base: dict = {"disponivel": False, "referencia": None, "atualizacao": None,
                  "lote_id": None, "desatualizado": False, "dias_defasagem": 0}
    if limite is not None:
        base.update({"total": 0, "limite": limite, "offset": offset, "itens": [],
                     "detalhe_disponivel": True})
    return base


def _identificar(base: dict, foto) -> date:
    referencia, lote, publicacao = foto[0], foto[1], foto[2]
    base["referencia"] = _data_iso(referencia)
    base["lote_id"] = str(lote).lower() if lote is not None else None
    base["atualizacao"] = (publicacao.strftime("%Y-%m-%dT%H:%M:%S")
                           if hasattr(publicacao, "strftime") else None)
    dias = (_hoje() - referencia).days if isinstance(referencia, date) else 0
    base["dias_defasagem"] = max(dias, 0)
    base["desatualizado"] = dias > 0
    return referencia


@router.get("/pio/card1/resumo", dependencies=[Depends(_require_caixa)])
def pio_card1_resumo(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Prêmio e quantidade do Card 1 na foto — lendo só a AGREGADA.

    `disponivel=false` é "não consegui ler"; `disponivel=true` com `quantidade=0`
    é "li a foto e não há pendência". A tela distingue as duas (zero é uma
    resposta que ninguém investiga). `desatualizado` diz que a foto não é de hoje
    — a carga das 07:30 pode ter falhado.
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
        log.warning("pio card1: resumo indisponível (%s: %s)", type(e).__name__, e)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        return resposta

    resposta["disponivel"] = True
    if foto and agregado:
        _identificar(resposta, foto)
        resposta["quantidade"] = int(agregado[0] or 0)
        resposta["premio_total"] = _dinheiro(agregado[1]) or 0.0
        resposta["grupos"] = int(agregado[2] or 0)
    return resposta


def _item(linha) -> dict:
    r = dict(zip(_COLUNAS_ITEM, linha))
    celular = _telefone(r["NUM_DDD_TEL_CEL"], r["NUM_TEL_CEL"])
    residencial = _telefone(r["NUM_DDD_TEL_RES"], r["NUM_TEL_RES"])
    return {
        "id_foto": int(r["ID_FOTO"]),
        "proposta": _texto(r["COD_PROPOSTA"]) or "",
        "cod_venda": int(r["COD_VENDA"]) if r["COD_VENDA"] is not None else None,
        "nome": _texto(r["NOM_PESSOA"]) or "",
        "cpf": _texto(r["COD_CPF"]) or "",
        "agencia": _texto(r["NUM_AGENCIA"]) or "",
        "matricula": _texto(r["NUM_MATRICULA"]) or "",
        "data_venda": _data_iso(r["DTH_VENDA"]),
        "dias_pendente": int(r["DIAS_PENDENTE"] or 0),
        "produto": _texto(r["NOM_PRODUTO"]) or "",
        "area_produto": _texto(r["AREA_PRODUTO"]) or "",
        "premio": _dinheiro(r["VLR_PREMIO"]),
        "imp_segurada": _dinheiro(r["VLR_IMP_SEGURADA"]),
        "renda": _dinheiro(r["VLR_RENDA_FORMAL"]),
        "cidade": _texto(r["NOM_CIDADE"]) or "",
        "uf": _texto(r["NOM_UF"]) or "",
        "nascimento": r["DTA_NASCIMENTO"],
        "situacao": _texto(r["STA_SITUACAO"]) or "",
        "assinatura": _texto(r["STA_ASSINATURA"]) or "",
        "pago": _texto(r["STA_PAGO"]) or "",
        "contato": {
            "email": _texto(r["DES_EMAIL"]),
            "celular": celular,
            "residencial": residencial,
        },
    }


@router.get("/pio/card1/propostas", dependencies=[Depends(_require_caixa)])
def pio_card1_propostas(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
    busca: str = Query("", description="termo da busca"),
    modo: str = Query("livre", description="livre | proposta | cpf | agencia | matricula"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de propostas do Card 1 na foto, mais antigas primeiro — lendo a FAT.

    A mesma foto do `/resumo` (passe `data` para não depender de uma publicação
    nova entre as duas chamadas). `detalhe_disponivel=false` quando a foto existe
    no agregado mas a fato não tem linhas dela: a retenção é diferente (fato 24
    meses, agregado 36), e a tela explica em vez de falhar.

    Dados pessoais: o detalhe fica atrás de `tela_caixa_seguro`, como a DET
    legada, e a resposta nunca devolve mais que `limite` linhas.
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
            # ID_FOTO fecha a ordenação: a query aceita pode repetir proposta
            # (JOIN), e sem desempate a página 2 repete/pula linhas.
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
        log.warning("pio card1: propostas indisponíveis (%s: %s)", type(e).__name__, e)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
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
