"""api/routers/chamados.py — os chamados da engenharia (espelho do ServiceNow).

Serve a tela /chamados a partir do espelho local (dbo.etl_chamado, migration
088), populado pela DAG `etl_servicenow_sync` a cada 3h. Somente leitura: a v1
não escreve no ServiceNow (decisão da spec).

Duas coisas que este router faz questão de DIZER, porque calar produziria o
mesmo sintoma com causas opostas:

  1. **Frescor.** A tela mostra "sincronizado há Xh". Sem isso, um espelho
     parado há dois dias tem exatamente a mesma cara de um espelho em dia.
  2. **Fila vazia × integração quebrada.** Zero chamados pode ser "a equipe
     zerou a fila" ou "o grupo está errado / a credencial foi negada". O
     último ciclo em dbo.etl_chamado_sync separa os dois, e a resposta carrega
     essa distinção em vez de deixar a tela adivinhar.

Degrada graciosamente sem a migration 088: `migration_ausente: true` e listas
vazias — a tela avisa "sistema em atualização" em vez de dar tela branca.

⚠️ Árvore `api/`: placeholder pyodbc é `?`. A árvore `dags/` usa `%s`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from db import get_db_conn
from deps import get_current_user

log = logging.getLogger("orquestra-api")

router = APIRouter()

PERM_CHAMADOS = "tela_chamados"

# A ordem aqui é a ordem das colunas na tela.
COLUNAS_KANBAN = ("novo", "andamento", "aguardando", "resolvido", "outros")

# Acima disto o carimbo de frescor vira âmbar: 2 ciclos de 3h perdidos.
FRESCOR_ALERTA_HORAS = 6


def _fmt_dt(v):
    return str(v)[:19] if v else None


def _ultimo_ciclo(cur) -> dict | None:
    """O ciclo mais recente — a fonte do frescor e do 'por que está vazio'."""
    cur.execute(
        "SELECT TOP 1 id, iniciado_em, terminado_em, status, qtd_incident, "
        "       qtd_ritm, qtd_task, qtd_change, qtd_desativados, erro, "
        "       DATEDIFF(MINUTE, iniciado_em, GETDATE()) AS idade_min "
        "FROM dbo.etl_chamado_sync ORDER BY iniciado_em DESC")
    linha = cur.fetchone()
    if not linha:
        return None
    idade_min = linha[10] if linha[10] is not None else None
    return {
        "id": linha[0],
        "iniciado_em": _fmt_dt(linha[1]),
        "terminado_em": _fmt_dt(linha[2]),
        "status": linha[3],
        "quantidades": {"incident": linha[4], "ritm": linha[5],
                        "task": linha[6], "change": linha[7]},
        "desativados": linha[8],
        "erro": linha[9],
        "idade_minutos": idade_min,
        # "nunca terminou" é diferente de "terminou com erro": o primeiro é
        # worker morto no meio, o segundo é a integração recusando.
        "em_andamento": linha[2] is None,
        "atrasado": bool(idade_min is not None
                         and idade_min > FRESCOR_ALERTA_HORAS * 60),
    }


@router.get("/chamados", tags=["chamados"])
def listar_chamados(incluir_inativos: int = 0,
                    _auth: dict = Depends(get_current_user)):
    """O espelho inteiro + o frescor. Filtro e busca são client-side (fila de
    ordem de dezenas — a spec dimensionou ~50), então a resposta é a fila toda
    e a tela não faz ida-e-volta a cada tecla."""
    resposta: dict = {
        "chamados": [], "colunas": list(COLUNAS_KANBAN), "ultimo_sync": None,
        "migration_ausente": False, "total": 0, "por_coluna": {},
        "alerta_fila_vazia": None,
    }
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        sql = (
            "SELECT sys_id, numero, tipo, titulo, estado_origem, estado_kanban, "
            "       prioridade, atribuido_a, grupo, aberto_em, atualizado_em, "
            "       encerrado_em, ativo, url, sync_em, "
            "       DATEDIFF(DAY, aberto_em, GETDATE()) AS idade_dias "
            "FROM dbo.etl_chamado")
        if not incluir_inativos:
            sql += " WHERE ativo = 1"
        sql += " ORDER BY aberto_em DESC"
        cur.execute(sql)
        for r in cur.fetchall():
            resposta["chamados"].append({
                "sys_id": r[0], "numero": r[1], "tipo": r[2], "titulo": r[3],
                "estado_origem": r[4], "estado_kanban": r[5],
                "prioridade": r[6], "atribuido_a": r[7], "grupo": r[8],
                "aberto_em": _fmt_dt(r[9]), "atualizado_em": _fmt_dt(r[10]),
                "encerrado_em": _fmt_dt(r[11]), "ativo": bool(r[12]),
                "url": r[13], "sync_em": _fmt_dt(r[14]),
                "idade_dias": r[15] if r[15] is not None else None,
            })
        resposta["ultimo_sync"] = _ultimo_ciclo(cur)
        cur.close(); conn.close(); conn = None
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        # Tabela ausente = migration 088 não rodou. Qualquer outro erro
        # também cai aqui, e em ambos os casos a tela precisa dizer algo em
        # vez de quebrar — mas o log guarda a causa real.
        log.warning("chamados: espelho indisponível (%s: %s)", type(e).__name__, e)
        resposta["migration_ausente"] = True
        return resposta

    resposta["total"] = len(resposta["chamados"])
    for coluna in COLUNAS_KANBAN:
        resposta["por_coluna"][coluna] = sum(
            1 for c in resposta["chamados"] if c["estado_kanban"] == coluna)

    # Fila vazia com sync OK é notícia boa; fila vazia com sync em ERRO (ou
    # sem sync nenhum) é a integração quebrada com cara de "tudo resolvido".
    if resposta["total"] == 0:
        ciclo = resposta["ultimo_sync"]
        if ciclo is None:
            resposta["alerta_fila_vazia"] = (
                "Nenhuma sincronização registrada ainda — verifique se o sync "
                "está habilitado em Admin > ServiceNow.")
        elif ciclo["status"] != "OK":
            resposta["alerta_fila_vazia"] = (
                "A última sincronização falhou — a fila pode não estar "
                "realmente vazia. " + (ciclo["erro"] or ""))
        else:
            resposta["alerta_fila_vazia"] = (
                "Nenhum chamado no grupo configurado. Se isso for inesperado, "
                "confira o grupo em Admin > ServiceNow.")
    return resposta
