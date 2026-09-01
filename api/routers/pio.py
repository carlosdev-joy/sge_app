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

_LIMITE_PADRAO = 50
_LIMITE_MAXIMO = 200


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


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
    card: str = Query("PEND_ASSIN", description="COD_CARD (PEND_ASSIN, PEND_PGTO)"),
    busca: str = Query("", description="proposta, nome ou CPF"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página da lista de propostas do card, mais antigas primeiro.

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
    if codigo not in CARDS:
        return resposta
    tabela = CARDS[codigo][1]

    termo = (busca or "").strip()[:100]
    digitos = _so_digitos(termo)

    # Sem filtro de status: a DET já é do card. Filtra-se só pela referência
    # (a carga é TRUNCATE + INSERT, mas uma carga parcial deixaria duas datas
    # na tabela e a lista misturaria dois dias) e pela busca do usuário.
    filtro = (f"WHERE d.DTH_REFERENCIA = (SELECT MAX(DTH_REFERENCIA) FROM {tabela})")
    params: list = []
    if termo:
        # CPF e número de proposta vêm com máscara na tela e sem máscara no
        # banco (ou o contrário). Comparar só os dígitos evita a busca que não
        # acha nada e parece "não existe".
        filtro += (" AND (d.NOM_PESSOA LIKE ? OR d.COD_PROPOSTA LIKE ?"
                   "      OR REPLACE(REPLACE(REPLACE(d.COD_CPF, '.', ''), '-', ''), ' ', '') LIKE ?)")
        params.extend([f"%{termo}%", f"%{termo}%", f"%{digitos or termo}%"])

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM {tabela} d {filtro}", params)
        linha = cur.fetchone()
        resposta["total"] = int(linha[0]) if linha else 0

        cur.execute(f"""
            SELECT d.COD_PROPOSTA, d.NOM_PESSOA, d.COD_CPF, d.NUM_AGENCIA,
                   d.NUM_MATRICULA, CONVERT(varchar(10), d.DTH_VENDA, 120),
                   DATEDIFF(day, d.DTH_VENDA, CAST(GETDATE() AS DATE)),
                   d.NOM_PRODUTO, d.AREA_PRODUTO, d.VLR_PREMIO, d.VLR_IMP_SEGURADA,
                   d.NOM_CIDADE, d.NOM_UF,
                   d.NUM_DDD_TEL_CEL, d.NUM_TEL_CEL, d.NUM_DDD_TEL_RES, d.NUM_TEL_RES,
                   d.DES_EMAIL, DATEDIFF(year, d.DTA_NASCIMENTO, CAST(GETDATE() AS DATE)),
                   d.STA_SITUACAO, d.STA_PAGO,
                   CONVERT(varchar(10), d.DTH_REFERENCIA, 120)
              FROM {tabela} d
              {filtro}
             ORDER BY d.DTH_VENDA ASC, d.COD_PROPOSTA ASC
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
                "cidade": (r[11] or "").strip(),
                "uf": (r[12] or "").strip(),
                "telefone": telefone,
                "email": (r[17] or "").strip(),
                "idade": int(r[18]) if r[18] is not None else None,
                "situacao": (r[19] or "").strip(),
                "pago": (r[20] or "").strip(),
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
