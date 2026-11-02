"""api/routers/pio_card8.py — Card 8 (Sensibilizações = último movimento de propostas Vida) lendo a FOTO.

  GET /pio/card8/resumo     — valor sensibilizado + identificações (tabela AGREGADA)
  GET /pio/card8/propostas  — lista paginada (tabela ANALÍTICA), uma linha por identificação

RITM0118664. Mesmo padrão dos Cards 1–7 (helpers de `routers/pio_card1.py`); a carga é o pipeline
Fabric do Card 8 (07:30) e esta API só LÊ:

    dbo.AGG_ORQ_CARD08_FOTO   grupos pré-agregados → número do card e total da lista
    dbo.FAT_ORQ_CARD08_FOTO   UMA LINHA POR IDENTIFICAÇÃO (COD_EMPRESA_SIVPF + NUM_IDENTIFICACAO_SIVPF)
    dbo.CTL_ORQ_CARD08_LOTE   controle: qual lote está PUBLICADO em cada data

A unidade é a IDENTIFICAÇÃO (do HIST_PROP_FIDELIZ), NÃO o número da proposta: `NUM_PROPOSTA` vem de
um LEFT JOIN e pode ser NULL. O que a foto guarda é o ÚLTIMO MOVIMENTO de cada identificação nos
últimos 12 meses — não todos os movimentos, nem só os do dia da foto.

⚠️ `QTD_CONTRATOS` conta identificações (use SUM, nunca COUNT(*) da AGG). `VLR_SENSIBILIZADO` é o
`VLR_PREMIO` do movimento selecionado: NÃO é prêmio pago, receita nem devolução efetivada. Negativos
e NULL são preservados (NULL = desconhecido, nunca zero).
⚠️ Status e motivo: valor NULL = "sem status"; 3 bytes NUL (0x000000, ~225 mil na foto de 02/11) ou
qualquer texto só de controle = "Código não identificado" — nunca rótulo vazio. O valor original
segue no banco.
⚠️ `STATUS_ULTIMO_MOV` (movimento: EMT, ENV, CAN…) e `SIT_PROPOSTA_ATUAL` (proposta: R, S, N…) são
estados DIFERENTES e não se misturam. O botão "Sensibilizar" só compara os dois por uma equivalência
declarada (`EQUIVALENTES`, decisão do usuário, 02/11) — única regra, aqui.
⚠️ POLÍTICA DE RETENÇÃO (02/11): a FAT guarda só hoje, D-1 e D-2 por `DTA_MOVIMENTO`; a AGG, 36 meses.
Foto mais antiga que D-2 (ou sem linhas de FAT no lote) = detalhe EXPIRADO, não "zero propostas":
`detalhe_disponivel=false`, e o `total` segue válido (vem da AGG).
⚠️ Volume: ~6,5 milhões de linhas por foto e as tabelas são do Fabric (sem índice novo). Por isso
o `total` sai da AGG (não de COUNT na FAT) e a lista ordena por (COD_EMPRESA_SIVPF,
NUM_IDENTIFICACAO_SIVPF) — o índice único existente —, nunca por data (ordenar 6,5 milhões a cada página).
⚠️ Geografia é da AGÊNCIA DE VENDA. Sem nome/CPF do segurado nesta foto; `COD_USUARIO`, `COD_ERRO` e
endereço da agência NÃO são expostos.

Placeholder `?` (pyodbc) — árvore `api/`. Tudo atrás de `tela_caixa_seguro`.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from db import get_db_conn
from deps import require_perm
from routers import pio_card1
from routers.pio_card1 import (
    _LIMITE_MAXIMO, _LIMITE_PADRAO, _data_iso, _dinheiro, _identificar, _resposta_base, _texto,
)
from routers.pio_card4 import _inteiro_texto

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# Nomes de objeto fixos: não aceitam parâmetro em T-SQL e nunca vêm da requisição.
AGG = "dbo.AGG_ORQ_CARD08_FOTO"
FAT = "dbo.FAT_ORQ_CARD08_FOTO"
CTL = "dbo.CTL_ORQ_CARD08_LOTE"

SEM_CODIGO = "Código não identificado"
SEM_STATUS = "Sem status"

# Equivalência declarada (usuário, 02/11): SIT_PROPOSTA_ATUAL → status de movimento que a CONFIRMA.
# S Enviado = ENV Enviada; R Integrado = EMT Emitida ou PAI Pago/Aceito. Fora disso (N, Pendente,
# código desconhecido, sem status) o botão "Sensibilizar" fica habilitado.
EQUIVALENTES: dict[str, frozenset[str]] = {"S": frozenset({"ENV"}), "R": frozenset({"EMT", "PAI"})}

_LINHA = {"VG": "Vida em Grupo", "AP": "Acidentes Pessoais"}

# Ordem do SELECT da lista — e a ordem em que `_item` lê cada linha.
_NOMES = (
    "ID_FOTO", "NUM_PROPOSTA", "NUM_IDENTIFICACAO_SIVPF", "COD_EMPRESA_SIVPF", "LINHA_NEGOCIO",
    "NOM_PRODUTO", "DATA_ULTIMO_MOVIMENTO", "STATUS_ULTIMO_MOV", "DESCRICAO_STATUS_ULTIMO_MOV",
    "COD_MOTIVO", "DESCRICAO_MOTIVO", "VLR_SENSIBILIZADO", "IND_ENVIO", "DATA_GERACAO_LOTE",
    "DATA_PROCESSAMENTO_LOTE", "DATA_PROPOSTA", "SIT_PROPOSTA_ATUAL", "DESCRICAO_SIT_ATUAL",
    "NUM_MATRI_VENDEDOR", "COD_AGENCIA_VENDA", "NOM_AGENCIA_VENDA", "SIG_UF_AGENCIA_VENDA",
    "NOM_CIDADE_AGENCIA",
)
_COLUNAS_LISTA = tuple(f"f.{n}" for n in _NOMES)


def _legivel(valor) -> str | None:
    """Texto legível ou `None`. NULL/vazio → `None`; texto SÓ de controle (os 3 bytes NUL da foto)
    → `SEM_CODIGO`; controle misturado a texto é descartado. Nunca devolve rótulo vazio."""
    if valor is None:
        return None
    bruto = str(valor)
    limpo = "".join(c for c in bruto if c.isprintable()).strip()
    if limpo:
        return limpo
    # Sem texto legível: só espaço/vazio = sem valor; sobrou caractere de controle (NUL) = código ilegível.
    return SEM_CODIGO if any(ord(c) < 32 or ord(c) == 127 for c in bruto if not c.isspace()) else None


def _codigo(valor) -> str:
    """Código de status limpo e em caixa alta, para comparar; vazio se não houver código válido."""
    t = _legivel(valor)
    return "" if t in (None, SEM_CODIGO) else t.upper()


def pode_sensibilizar(situacao_atual, status_ultimo_mov) -> bool:
    """O botão "Sensibilizar" habilita quando o status da proposta DIFERE do último movimento
    encaminhado — pela equivalência declarada (`EQUIVALENTES`); o que ela não cobre habilita."""
    return _codigo(status_ultimo_mov) not in EQUIVALENTES.get(_codigo(situacao_atual), frozenset())


def _item(linha) -> dict:
    r = dict(zip(_NOMES, linha))
    identificacao = _inteiro_texto(r["NUM_IDENTIFICACAO_SIVPF"])
    proposta = _inteiro_texto(r["NUM_PROPOSTA"]) if r["NUM_PROPOSTA"] is not None else ""
    if proposta.strip("0") == "":
        proposta = ""           # NULL ou 0 (placeholder): sem proposta, vale a identificação
    linha_negocio = (_texto(r["LINHA_NEGOCIO"]) or "").upper()
    desc_mov = _legivel(r["DESCRICAO_STATUS_ULTIMO_MOV"]) or _legivel(r["STATUS_ULTIMO_MOV"]) or SEM_STATUS
    desc_atual = _legivel(r["DESCRICAO_SIT_ATUAL"]) or _legivel(r["SIT_PROPOSTA_ATUAL"]) or SEM_STATUS
    motivo = _legivel(r["DESCRICAO_MOTIVO"])
    return {
        "id_foto": int(r["ID_FOTO"]),
        # O número exibido é a proposta; sem ela (LEFT JOIN), a identificação.
        "proposta": proposta or identificacao,
        "nome": _LINHA.get(linha_negocio, ""),      # a foto não traz o segurado: mostra a linha de negócio
        "cpf": "",
        "agencia": _inteiro_texto(r["COD_AGENCIA_VENDA"]),
        "matricula": _inteiro_texto(r["NUM_MATRI_VENDEDOR"]),
        "data_venda": _data_iso(r["DATA_PROPOSTA"]),
        "dias_pendente": 0,
        "produto": _texto(r["NOM_PRODUTO"]) or "",
        "area_produto": _LINHA.get(linha_negocio, ""),
        "premio": _dinheiro(r["VLR_SENSIBILIZADO"]),
        "imp_segurada": None,
        "renda": None,
        "cidade": "",
        "uf": "",
        "cidade_agencia": _texto(r["NOM_CIDADE_AGENCIA"]) or "",
        "uf_agencia": _texto(r["SIG_UF_AGENCIA_VENDA"]) or "",
        "idade": None,
        "situacao": "",
        "assinatura": "",
        "pago": "",
        "sub_situacao": "",
        "contato": {"email": None, "celular": None, "residencial": None},
        "sensibilizacao": {
            "identificacao": identificacao,
            "empresa": int(r["COD_EMPRESA_SIVPF"]) if r["COD_EMPRESA_SIVPF"] is not None else None,
            "linha": linha_negocio,
            "status_movimento": desc_mov,
            "status_movimento_codigo": _codigo(r["STATUS_ULTIMO_MOV"]),
            "status_atual": desc_atual,
            "status_atual_codigo": _codigo(r["SIT_PROPOSTA_ATUAL"]),
            "motivo": motivo,
            "data_movimento": _data_iso(r["DATA_ULTIMO_MOVIMENTO"]),
            "data_envio": _data_iso(r["DATA_GERACAO_LOTE"]),
            "data_processamento": _data_iso(r["DATA_PROCESSAMENTO_LOTE"]),
            "indicador_envio": _texto(r["IND_ENVIO"]),
            "pode_sensibilizar": pode_sensibilizar(r["SIT_PROPOSTA_ATUAL"], r["STATUS_ULTIMO_MOV"]),
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


@router.get("/pio/card8/resumo", dependencies=[Depends(_require_caixa)])
def pio_card8_resumo(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
) -> dict:
    """Valor sensibilizado e identificações do Card 8 na foto — lendo só a AGREGADA.

    `quantidade` = `SUM(QTD_CONTRATOS)` (identificações); `premio_total` (nome comum aos cards de
    foto) = `SUM(VLR_SENSIBILIZADO_TOTAL)`, ou `None` se nenhum movimento tem valor.
    `sem_status` = identificações sem status de movimento (NULL ou código de controle).
    `disponivel=false` é "não consegui ler"; `disponivel=true` com `quantidade=0` é "li e não há".
    """
    resposta = _resposta_base()
    resposta.update({"premio_total": None, "quantidade": 0, "grupos": 0, "premios_informados": 0,
                     "sem_status": 0})
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        agregado = None
        if foto:
            cur.execute(
                "SELECT COALESCE(SUM(QTD_CONTRATOS), 0), SUM(VLR_SENSIBILIZADO_TOTAL), COUNT_BIG(*),"
                " COALESCE(SUM(QTD_VALORES_INFORMADOS), 0), COALESCE(SUM(QTD_STATUS_INFORMADOS), 0)"
                f" FROM {AGG} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?",
                [foto[0], foto[1]])
            agregado = cur.fetchone()
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card8: resumo indisponível (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if foto and agregado:
        _identificar(resposta, foto)
        quantidade = int(agregado[0] or 0)
        informados = int(agregado[3] or 0)
        resposta["quantidade"] = quantidade
        resposta["grupos"] = int(agregado[2] or 0)
        resposta["premios_informados"] = informados       # < quantidade = valor parcial
        resposta["sem_status"] = max(quantidade - int(agregado[4] or 0), 0)
        resposta["premio_total"] = (_dinheiro(agregado[1]) or 0.0) if informados > 0 else (
            0.0 if quantidade == 0 else None)
    return resposta


@router.get("/pio/card8/propostas", dependencies=[Depends(_require_caixa)])
def pio_card8_propostas(
    data: date | None = Query(None, description="DTA_MOVIMENTO; padrão = última publicada"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de identificações do Card 8 na foto — lendo a FAT, em ordem de identificação.

    `total` = `SUM(QTD_CONTRATOS)` da AGG (igual à `quantidade` do `/resumo`; a FAT tem 6,5 milhões de
    linhas). `detalhe_disponivel=false` quando a foto é mais antiga que D-2 ou o lote não tem
    linhas na FAT: histórico EXPIRADO, não "zero propostas". Passe `data` (a do `/resumo`).
    """
    resposta = _resposta_base(limite, offset)
    resposta["ordem"] = "identificacao"
    conn = None
    linhas, foto, detalhe = [], None, True
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        foto = _foto(cur, data)
        if foto:
            chave = [foto[0], foto[1]]
            cur.execute(
                f"SELECT COALESCE(SUM(QTD_CONTRATOS), 0) FROM {AGG} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?",
                chave)
            total = cur.fetchone()
            resposta["total"] = int(total[0] or 0) if total else 0

            # Política 02/11: a FAT guarda hoje, D-1 e D-2. Mais antiga que isso, ou sem linhas do
            # lote, o detalhe expirou. A lista só é lida quando o detalhe existe.
            recente = isinstance(foto[0], date) and foto[0] >= pio_card1._hoje() - timedelta(days=2)
            existe = False
            if recente:
                cur.execute(f"SELECT TOP 1 1 FROM {FAT} WHERE DTA_MOVIMENTO = ? AND LOTE_ID = ?", chave)
                existe = cur.fetchone() is not None
            detalhe = recente and existe
            if detalhe:
                # (empresa, identificação) é o índice único da FAT: página barata e estável.
                cur.execute(
                    f"SELECT {', '.join(_COLUNAS_LISTA)} FROM {FAT} f"
                    " WHERE f.DTA_MOVIMENTO = ? AND f.LOTE_ID = ?"
                    " ORDER BY f.COD_EMPRESA_SIVPF ASC, f.NUM_IDENTIFICACAO_SIVPF ASC"
                    " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                    chave + [offset, limite])
                linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio card8: propostas indisponíveis (%s: %s)", type(e).__name__, e)
        _fechar(conn)
        return resposta

    resposta["disponivel"] = True
    if not foto:
        return resposta
    _identificar(resposta, foto)
    # Sem detalhe o total da AGG continua valendo; a lista é que não existe mais.
    resposta["detalhe_disponivel"] = detalhe or resposta["total"] == 0
    for linha in linhas:
        resposta["itens"].append(_item(linha))
    return resposta
