"""api/routers/pio.py — propostas do PIO para os cards do Workflow.

  GET /pio/contagens   — uma linha por categoria, para o número dos cards
  GET /pio/propostas   — o drill-down, paginado, para a lista do card

Lê **apenas** `dbo.PIO_PROPOSTA_PENDENTE_AGG` e `_DET`, no próprio banco do
Orquestra (SQL14_DMDB41). A carga vem de `PRC_PIO_CARGA_PROPOSTA_PENDENTE`,
que busca no TDDB48 via linked server e roda uma vez por dia às 07:30 — a API
NUNCA fala com a fonte em runtime. Migration 101 cria as duas tabelas.

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

# STA_ASSINATURA → rótulo, como na carga. Serve para DUAS coisas: traduzir a
# categoria quando a linha do AGG vier sem DES_CATEGORIA, e ser a lista branca
# do parâmetro `categoria` — o valor entra numa consulta parametrizada, mas
# recusar cedo o que não é categoria evita varrer a tabela à toa.
CATEGORIAS: dict[str, str] = {
    "PE": "Pendentes de Assinatura",
    "PP": "Pendentes de Pagamento",
    "AP": "Assinadas e Pagas",
    "AN": "Em Análise",
    "EM": "Emitidas",
    "RE": "Rejeitadas",
}

_LIMITE_PADRAO = 50
_LIMITE_MAXIMO = 200


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


@router.get("/pio/contagens", dependencies=[Depends(_require_caixa)])
def pio_contagens() -> dict:
    """Quantidade por categoria na carga mais recente.

    **Degrada em vez de estourar.** Tabela ausente (ambiente sem a migration
    101) e tabela vazia (carga ainda não rodou) são coisas DIFERENTES e a tela
    precisa distinguir: `disponivel=false` diz "não consegui ler", enquanto
    lista vazia com `disponivel=true` diz "li, e não há carga". Sem essa
    distinção, as duas viram um card zerado — e zero é uma resposta que
    ninguém investiga.
    """
    resposta: dict = {"disponivel": False, "referencia": None, "categorias": []}
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # A carga é TRUNCATE + INSERT, então só existe uma referência; filtrar
        # pela máxima mesmo assim custa nada e protege de uma carga parcial
        # deixar duas datas na tabela.
        cur.execute("""
            SELECT a.STA_CATEGORIA, a.DES_CATEGORIA, a.QTD_PROPOSTAS,
                   CONVERT(varchar(10), a.DTH_REFERENCIA, 120),
                   CONVERT(varchar(19), MAX(a.DTH_CARGA), 120)
              FROM dbo.PIO_PROPOSTA_PENDENTE_AGG a
             WHERE a.DTH_REFERENCIA = (SELECT MAX(DTH_REFERENCIA)
                                         FROM dbo.PIO_PROPOSTA_PENDENTE_AGG)
             GROUP BY a.STA_CATEGORIA, a.DES_CATEGORIA, a.QTD_PROPOSTAS,
                      a.DTH_REFERENCIA
        """)
        linhas = cur.fetchall() or []
        cur.close()
        conn.close()
        conn = None

        resposta["disponivel"] = True
        for cat, des, qtd, referencia, carga in linhas:
            codigo = (cat or "").strip().upper()
            resposta["categorias"].append({
                "categoria": codigo,
                "descricao": (des or "").strip() or CATEGORIAS.get(codigo, codigo),
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
    categoria: str = Query("PE", description="STA_ASSINATURA (PE, PP, AP, AN, EM, RE)"),
    busca: str = Query("", description="proposta, nome ou CPF"),
    limite: int = Query(_LIMITE_PADRAO, ge=1, le=_LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
) -> dict:
    """Página da lista de propostas da categoria, mais antigas primeiro.

    Paginado de propósito: a primeira carga trouxe **8.706** propostas em `PE`
    sozinha. Devolver tudo faria a tela montar milhares de cards e o `total` do
    cabeçalho é o que dá a dimensão real — o que a página mostra é o começo da
    fila, que é onde está o trabalho atrasado.
    """
    codigo = (categoria or "").strip().upper()
    resposta: dict = {
        "disponivel": False,
        "categoria": codigo,
        "referencia": None,
        "total": 0,
        "limite": limite,
        "offset": offset,
        "itens": [],
    }
    if codigo not in CATEGORIAS:
        return resposta

    termo = (busca or "").strip()[:100]
    digitos = _so_digitos(termo)

    # O filtro de busca é montado em pedaços, mas TODO valor entra por
    # parâmetro — o SQL abaixo não concatena entrada de usuário.
    filtro = ("WHERE d.STA_ASSINATURA = ? "
              "  AND d.DTH_REFERENCIA = (SELECT MAX(DTH_REFERENCIA) "
              "                            FROM dbo.PIO_PROPOSTA_PENDENTE_DET)")
    params: list = [codigo]
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

        cur.execute(f"SELECT COUNT(*) FROM dbo.PIO_PROPOSTA_PENDENTE_DET d {filtro}",
                    params)
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
              FROM dbo.PIO_PROPOSTA_PENDENTE_DET d
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
