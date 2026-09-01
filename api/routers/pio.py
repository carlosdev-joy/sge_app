"""api/routers/pio.py — propostas do PIO para os cards do Workflow.

  GET /pio/contagens   — uma linha por CARD, para o número dos cards
  GET /pio/propostas   — o drill-down, paginado, para a lista do card

Lê **apenas** o agregado `dbo.PIO_AGG` e as tabelas de detalhe, no próprio banco
do Orquestra (SQL14_DMDB41). A carga vem de `PRC_PIO_CARGA_DIARIA`, que busca no
TDDB48 via linked server e roda uma vez por dia às 07:30 — a API NUNCA fala com
a fonte em runtime. Migration 102 cria as tabelas deste modelo.

⚠️ **Cada DET já vem filtrada pela carga**, sem `CA`/`EXP` e só com os últimos
30 dias de venda:

    PEND_ASSIN    STA_ASSINATURA='PE'                  (pendente de assinatura)
    PEND_PGTO     STA_ASSINATURA='CO' AND STA_PAGO='N' (assinada, não paga)
    ASSINA_PAGA   STA_ASSINATURA='CO' AND STA_PAGO='S' (assinada e paga)

Os cards 2 e 3 saem do MESMO `STA_ASSINATURA`: quem os separa é o `STA_PAGO`.
A API **não refiltra por status**: repetir o filtro aqui é a forma silenciosa de
zerar um card se a carga mudar de critério.

⚠️ Placeholder `?` (pyodbc) — esta é a árvore `api/`. A `dags/` usa `%s`, e
trocar dá "Incorrect syntax near '?'" com o endpoint aparentemente vivo.

Tudo atrás de `tela_caixa_seguro`, a mesma permissão da seção.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Query

from db import get_db_conn
from deps import require_perm

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_caixa = require_perm("tela_caixa_seguro")

# COD_CARD → (rótulo, tabela de detalhe).
#
# É a lista branca do parâmetro `card` E a origem do nome da tabela. O nome NUNCA
# vem da requisição: ele é lido deste dicionário depois que a chave é validada —
# nome de objeto não aceita parâmetro em T-SQL, então esta é a única forma segura
# de escolher o FROM.
CARDS: dict[str, tuple[str, str]] = {
    "PEND_ASSIN": ("Pendentes de Assinatura", "dbo.PIO_PROPOSTA_PENDENTE_DET"),
    "PEND_PGTO": ("Pendentes de Pagamento", "dbo.PIO_PROPOSTA_PEND_PGTO_DET"),
    "ASSINA_PAGA": ("Assinadas e Pagas", "dbo.PIO_PROPOSTA_ASSINA_PAGA_DET"),
}

# Busca nos TRÊS cards de uma vez. Quem procura uma proposta pelo número não
# sabe (nem tem por que saber) em qual estado ela está.
CARD_TODOS = "TODOS"

_LIMITE_PADRAO = 50
_LIMITE_MAXIMO = 200

# As colunas da lista, com alias, iguais nos três ramos do UNION ALL — o alias
# é o que permite ordenar do lado de fora. `DTA_VENDA` sai como 'YYYY-MM-DD',
# que ordena como texto na mesma ordem da data.
_COLUNAS = """
    d.COD_PROPOSTA AS COD_PROPOSTA, d.NOM_PESSOA AS NOM_PESSOA,
    d.COD_CPF AS COD_CPF, d.NUM_AGENCIA AS NUM_AGENCIA,
    d.NUM_MATRICULA AS NUM_MATRICULA,
    CONVERT(varchar(10), d.DTH_VENDA, 120) AS DTA_VENDA,
    DATEDIFF(day, d.DTH_VENDA, CAST(GETDATE() AS DATE)) AS DIAS_PENDENTE,
    d.NOM_PRODUTO AS NOM_PRODUTO, d.AREA_PRODUTO AS AREA_PRODUTO,
    d.VLR_PREMIO AS VLR_PREMIO, d.VLR_IMP_SEGURADA AS VLR_IMP_SEGURADA,
    d.NOM_CIDADE AS NOM_CIDADE, d.NOM_UF AS NOM_UF,
    d.NUM_DDD_TEL_CEL AS DDD_CEL, d.NUM_TEL_CEL AS TEL_CEL,
    d.NUM_DDD_TEL_RES AS DDD_RES, d.NUM_TEL_RES AS TEL_RES,
    d.DES_EMAIL AS DES_EMAIL,
    DATEDIFF(year, d.DTA_NASCIMENTO, CAST(GETDATE() AS DATE)) AS IDADE,
    d.STA_SITUACAO AS STA_SITUACAO, d.STA_PAGO AS STA_PAGO,
    CONVERT(varchar(10), d.DTH_REFERENCIA, 120) AS DTA_REFERENCIA,
    d.VLR_RENDA_FORMAL AS VLR_RENDA_FORMAL
"""

_CPF_SEM_MASCARA = "REPLACE(REPLACE(REPLACE(d.COD_CPF, '.', ''), '-', ''), ' ', '')"


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _filtro_da_busca(modo: str, termo: str) -> tuple[str, list]:
    """O pedaço de SQL (e os parâmetros) que aplica a busca do usuário.

    Cada modo compara o campo que a tela pediu, e todos comparam **dígitos**:
    a tela mostra `8047413032422-7` e `397.750.878-48`, o banco guarda de outro
    jeito, e exigir igualdade literal é o que faz a busca "não achar" um número
    que está bem ali. Nada é concatenado — os valores entram por parâmetro.
    """
    termo = (termo or "").strip()[:100]
    if not termo:
        return "", []
    digitos = _so_digitos(termo) or termo

    if modo == "proposta":
        return (" AND REPLACE(REPLACE(d.COD_PROPOSTA, '-', ''), '.', '') LIKE ?",
                [f"%{digitos}%"])
    if modo == "cpf":
        return (f" AND {_CPF_SEM_MASCARA} LIKE ?", [f"%{digitos}%"])
    if modo == "agencia":
        # Agência é igualdade, não "contém": buscar 316 não pode trazer 3160.
        # O padding zera a diferença entre "0316" e "316", que são a mesma
        # agência escrita de dois jeitos.
        return (" AND RIGHT(REPLICATE('0', 12) + REPLACE(d.NUM_AGENCIA, ' ', ''), 12)"
                " = RIGHT(REPLICATE('0', 12) + ?, 12)", [digitos])
    if modo == "matricula":
        # A matrícula CEF vem com dígito verificador que pode ser LETRA
        # ("0000122795-B"): comparar só os dígitos ignora o verificador em vez
        # de não achar nada por causa dele.
        return (" AND REPLACE(REPLACE(d.NUM_MATRICULA, '-', ''), ' ', '') LIKE ?",
                [f"%{digitos}%"])

    # livre: o que a lista do card usa — nome, proposta ou CPF.
    return (" AND (d.NOM_PESSOA LIKE ? OR d.COD_PROPOSTA LIKE ?"
            f"      OR {_CPF_SEM_MASCARA} LIKE ?)",
            [f"%{termo}%", f"%{termo}%", f"%{digitos}%"])


@router.get("/pio/contagens", dependencies=[Depends(_require_caixa)])
def pio_contagens() -> dict:
    """Quantidade por card na carga mais recente.

    **Degrada em vez de estourar.** Tabela ausente (ambiente sem a migration
    102) e tabela vazia (carga ainda não rodou) são coisas DIFERENTES e a tela
    precisa distinguir: `disponivel=false` diz "não consegui ler", enquanto
    lista vazia com `disponivel=true` diz "li, e não há carga". Sem essa
    distinção, as duas viram um card zerado — e zero é uma resposta que
    ninguém investiga.

    **Por que MAX(DTH_REFERENCIA) e não `= hoje`:** o guia do PIO filtra pela
    data de hoje, o que está certo enquanto a carga roda. Só que o SQL Agent
    Job ainda depende do DBA — e no dia em que a carga não rodar, `= hoje` não
    devolve linha nenhuma e os dois cards mostram zero, que é falso. Com o
    último snapshot, o número continua verdadeiro e a tela exibe a data dele,
    que é o que denuncia a carga parada. Como a `PIO_AGG` é TRUNCATE + INSERT,
    nos dias normais as duas leituras dão exatamente a mesma linha.
    """
    resposta: dict = {"disponivel": False, "referencia": None, "cards": []}
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT a.COD_CARD, a.DES_CARD, a.QTD_PROPOSTAS,
                   CONVERT(varchar(10), a.DTH_REFERENCIA, 120),
                   CONVERT(varchar(19), a.DTH_CARGA, 120)
              FROM dbo.PIO_AGG a
             WHERE a.DTH_REFERENCIA = (SELECT MAX(DTH_REFERENCIA) FROM dbo.PIO_AGG)
             ORDER BY a.COD_CARD
        """)
        linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None

        resposta["disponivel"] = True
        for cod, des, qtd, referencia, carga in linhas:
            codigo = (cod or "").strip().upper()
            rotulo = CARDS.get(codigo, ("", ""))[0]
            resposta["cards"].append({
                "card": codigo,
                "descricao": (des or "").strip() or rotulo or codigo,
                "quantidade": int(qtd or 0),
                "carga": carga,
            })
            resposta["referencia"] = referencia
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio: contagens indisponíveis (%s: %s)", type(e).__name__, e)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return resposta


@router.get("/pio/propostas", dependencies=[Depends(_require_caixa)])
def pio_propostas(
    card: str = Query("PEND_ASSIN",
                      description="COD_CARD (PEND_ASSIN, PEND_PGTO, ASSINA_PAGA) ou TODOS"),
    busca: str = Query("", description="termo da busca"),
    modo: str = Query("livre",
                      description="livre | proposta | cpf | agencia | matricula"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página de propostas, mais antigas primeiro.

    Serve a dois usos: a lista de UM card (o drill-down do Workflow) e a busca
    em **TODOS** os cards (a Consulta de Propostas, que procura pelo número sem
    saber em que estado a proposta está). Com `card=TODOS`, cada item volta
    dizendo de qual card veio — é dali que sai o status na tela.

    Paginado de propósito: a carga traz ~8.700 propostas em PEND_ASSIN e
    ~22.500 em PEND_PGTO. Devolver tudo faria a tela montar milhares de cards;
    o `total` do cabeçalho é o que dá a dimensão real, e o que a página mostra
    é o começo da fila — onde está o trabalho mais atrasado.
    """
    codigo = (card or "").strip().upper()
    resposta: dict = {
        "disponivel": False,
        "card": codigo,
        "referencia": None,
        "total": 0,
        "limite": limite,
        "offset": offset,
        "itens": [],
    }
    if codigo == CARD_TODOS:
        alvos = list(CARDS.items())
    elif codigo in CARDS:
        alvos = [(codigo, CARDS[codigo])]
    else:
        return resposta

    filtro_busca, params_busca = _filtro_da_busca((modo or "").strip().lower(),
                                                 busca)

    # Um ramo por tabela, unidos. Sem filtro de status: a DET já é do card. A
    # referência é filtrada por tabela (a carga é TRUNCATE + INSERT, mas uma
    # carga parcial deixaria duas datas e a lista misturaria dois dias).
    #
    # `cod` e `tabela` saem do dicionário CARDS, nunca da requisição — nome de
    # objeto não aceita parâmetro em T-SQL, e a lista branca é o que separa
    # isto de uma injeção. Os parâmetros da busca se repetem por ramo.
    ramos, params = [], []
    for cod, (_rotulo, tabela) in alvos:
        ramos.append(f"""
            SELECT {_COLUNAS}, '{cod}' AS COD_CARD
              FROM {tabela} d
             WHERE d.DTH_REFERENCIA = (SELECT MAX(DTH_REFERENCIA) FROM {tabela})
             {filtro_busca}
        """)
        params.extend(params_busca)
    corpo = " UNION ALL ".join(ramos)

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM ({corpo}) t", params)
        linha = cur.fetchone()
        resposta["total"] = int(linha[0]) if linha else 0

        cur.execute(f"""
            SELECT t.* FROM ({corpo}) t
             ORDER BY t.DTA_VENDA ASC, t.COD_PROPOSTA ASC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, limite])

        for r in cur.fetchall() or []:
            ddd_cel, cel, ddd_res, res = r[13], r[14], r[15], r[16]
            telefone = ""
            if cel:
                telefone = f"({(ddd_cel or '').strip()}) {cel.strip()}".strip()
            elif res:
                telefone = f"({(ddd_res or '').strip()}) {res.strip()}".strip()
            resposta["itens"].append({
                "proposta": (r[0] or "").strip(),
                "nome": (r[1] or "").strip(),
                "cpf": (r[2] or "").strip(),
                "agencia": (r[3] or "").strip(),
                "matricula": (r[4] or "").strip(),
                "data_venda": r[5],
                "dias_pendente": int(r[6] or 0),
                "produto": (r[7] or "").strip(),
                "area_produto": (r[8] or "").strip(),
                "premio": float(r[9]) if r[9] is not None else None,
                "imp_segurada": float(r[10]) if r[10] is not None else None,
                # Renda declarada do proponente. NÃO confundir com `premio`: o
                # modal exibia o prêmio sob o rótulo "Renda Individual" até
                # 2026-09-01, e era essa a diferença que ninguém explicava.
                "renda": float(r[22]) if r[22] is not None else None,
                "cidade": (r[11] or "").strip(),
                "uf": (r[12] or "").strip(),
                "telefone": telefone,
                "email": (r[17] or "").strip(),
                "idade": int(r[18]) if r[18] is not None else None,
                "situacao": (r[19] or "").strip(),
                "pago": (r[20] or "").strip(),
                # De qual card a linha veio. Com card=TODOS é o que diz o
                # status na tela; sem ele, a busca acharia a proposta e não
                # saberia dizer em que estado ela está.
                "card": (r[23] or "").strip() if len(r) > 23 else codigo,
            })
            resposta["referencia"] = r[21]

        cur.close()
        conn.close()
        conn = None
        resposta["disponivel"] = True
    except Exception as e:      # noqa: BLE001 — tabela ausente é esperado
        log.warning("pio: propostas indisponíveis (%s: %s)", type(e).__name__, e)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return resposta
