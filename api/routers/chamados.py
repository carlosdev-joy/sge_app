"""api/routers/chamados.py — os chamados da engenharia (espelho do ServiceNow).

Serve a tela /chamados a partir do espelho local (dbo.etl_chamado, migration
088), populado pela DAG `etl_servicenow_sync` a cada 15 min. Somente leitura:
a v1 não escreve no ServiceNow (decisão da spec).

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

from fastapi import APIRouter, Depends, HTTPException

from db import get_db_conn
from deps import PERM_EXECUTAR, get_current_user, require_perm

log = logging.getLogger("orquestra-api")

router = APIRouter()

PERM_CHAMADOS = "tela_chamados"

# A ordem aqui é a ordem das colunas na tela.
COLUNAS_KANBAN = ("novo", "andamento", "aguardando", "resolvido", "outros")

# Acima disto o carimbo de frescor vira âmbar. O número NÃO é absoluto: é
# múltiplo da cadência da DAG (`schedule` em dags/etl_servicenow_sync.py).
# Hoje: 60 min ≈ 4 ciclos de 15 min — silêncio longo o bastante para não
# acender no primeiro tropeço, curto o bastante para não deixar o espelho
# apodrecer meio turno. Com a cadência antiga (3h) eram 6h, pela MESMA regra.
# Mudar a cadência sem mudar este número deixa o alerta surdo ou histérico;
# tests/test_servicenow_cadencia.py recusa a combinação incoerente.
FRESCOR_ALERTA_MINUTOS = 60

# Faixas de aging. Os limites são o MESMO contrato do destaque no card
# (>3d atenção, >7d parado): duas réguas diferentes para a mesma pergunta
# fariam a aba discordar do kanban ao lado.
FAIXAS_AGING = (
    ("0-3 dias", 0, 3),
    ("4-7 dias", 4, 7),
    ("8-14 dias", 8, 14),
    ("mais de 14 dias", 15, None),
)

# Janela do fluxo de entradas × saídas.
DIAS_FLUXO = 14

# Quantos responsáveis o gráfico de carga mostra antes de dobrar o resto em
# "outros". O corte é DITO na resposta — silenciar o que foi cortado faria a
# soma do gráfico não bater com a fila.
TOPO_RESPONSAVEIS = 10

# ── O card é o TRABALHO, não o registro ─────────────────────────────────────
# No ServiceNow todo RITM gera uma sc_task filha. O espelho traz as duas, e a
# fila contava cada pedido DUAS vezes: 113 itens para ~60 trabalhos, medidos
# em produção (49 de 49 tasks ativas com pai na fila).
#
# Na fila, o filho vira uma linha DENTRO do card do pai (agrupado em Python,
# porque a tela precisa dos dois). Nos indicadores, que só agregam, o mesmo
# recorte é feito no SQL — senão a aba Indicadores diria 113 enquanto a aba
# Fila diz 60, e as duas estariam "certas".
#
# ⚠️ Task ÓRFÃ continua contando: `pai_sys_id` preenchido mas apontando para
# fora do espelho é o caso real de uma task atribuída ao grupo cujo RITM
# pertence a outro. Escondê-la perderia trabalho de vista — o oposto do que
# esta mudança existe para fazer.
def _so_trabalhos(entre_ativos: bool = True) -> str:
    """Predicado SQL: exclui o filho cujo pai está no espelho."""
    escopo = " WHERE ativo = 1" if entre_ativos else ""
    return (" AND (pai_sys_id IS NULL OR pai_sys_id = '' "
            f"     OR pai_sys_id NOT IN (SELECT sys_id FROM dbo.etl_chamado{escopo}))")


def _agrupar_por_pai(chamados: list[dict]) -> list[dict]:
    """Filho vai para dentro do card do pai; o resto fica na raiz.

    Preserva a ordem original das raízes (a query já ordena por abertura) e a
    dos filhos dentro de cada card.
    """
    por_sys_id = {c["sys_id"]: c for c in chamados if c.get("sys_id")}
    raizes: list[dict] = []
    for c in chamados:
        pai = por_sys_id.get((c.get("pai_sys_id") or "").strip())
        # `pai is not c` protege do auto-referente; sem isso um registro com
        # pai_sys_id == sys_id sumiria da fila inteira, sem erro nenhum.
        if pai is not None and pai is not c:
            pai.setdefault("filhos", []).append(c)
        else:
            raizes.append(c)
    return raizes


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
                         and idade_min > FRESCOR_ALERTA_MINUTOS),
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
        "alerta_fila_vazia": None, "registros": 0,
    }
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        sql = (
            "SELECT sys_id, numero, tipo, titulo, estado_origem, estado_kanban, "
            "       prioridade, atribuido_a, grupo, aberto_em, atualizado_em, "
            "       encerrado_em, ativo, url, sync_em, "
            "       DATEDIFF(DAY, aberto_em, GETDATE()) AS idade_dias, "
            "       pai_sys_id, pai_numero, estado_cru "
            "FROM dbo.etl_chamado")
        if not incluir_inativos:
            sql += " WHERE ativo = 1"
        sql += " ORDER BY aberto_em DESC"
        cur.execute(sql)
        linhas = []
        for r in cur.fetchall():
            linhas.append({
                "sys_id": r[0], "numero": r[1], "tipo": r[2], "titulo": r[3],
                "estado_origem": r[4], "estado_kanban": r[5],
                "prioridade": r[6], "atribuido_a": r[7], "grupo": r[8],
                "aberto_em": _fmt_dt(r[9]), "atualizado_em": _fmt_dt(r[10]),
                "encerrado_em": _fmt_dt(r[11]), "ativo": bool(r[12]),
                "url": r[13], "sync_em": _fmt_dt(r[14]),
                "idade_dias": r[15] if r[15] is not None else None,
                "pai_sys_id": r[16] or "", "pai_numero": r[17] or "",
                # O NÚMERO do estado, ao lado do rótulo: quando o card cai em
                # "Outros", é ele que diz o que cadastrar no mapa do kanban.
                "estado_cru": r[18] or "",
                "filhos": [],
            })
        resposta["chamados"] = _agrupar_por_pai(linhas)
        # O denominador honesto: quantos registros vieram do espelho, antes do
        # agrupamento. Sem isso a tela não consegue dizer "60 trabalhos (113
        # registros)" e o operador acha que sumiu chamado.
        resposta["registros"] = len(linhas)
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


@router.get("/chamados/indicadores", tags=["chamados"])
def indicadores(_auth: dict = Depends(get_current_user)):
    """Agregados para a aba de Indicadores — contas feitas no SQL, não na tela.

    Quatro leituras, cada uma respondendo a uma pergunta da gestão:
      - aging por faixa      → "tem coisa velha parada?"
      - tipo × estado        → "onde a fila está represada?"
      - entradas × saídas    → "estamos ganhando ou perdendo da fila?"
      - carga por responsável → "está distribuído?"

    Todo total vem acompanhado do denominador: a regra da casa é que nenhuma
    superfície mostre "%" sem o "x de y" ao lado, e o front só consegue montar
    essa frase se o denominador chegar junto.
    """
    saida = {
        "aging": [], "tipo_estado": {"tipos": [], "estados": list(COLUNAS_KANBAN),
                                     "celulas": []},
        "fluxo": [], "carga": [], "total_ativos": 0,
        "responsaveis_ocultos": 0, "migration_ausente": False,
    }
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()

        # ── aging por faixa (só o que está na fila) ──────────────────────────
        cur.execute(
            "SELECT CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END AS faixa, COUNT(*) "
            "FROM dbo.etl_chamado WHERE ativo = 1 AND aberto_em IS NOT NULL "
            + _so_trabalhos() +
            "GROUP BY CASE "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3 THEN '0-3 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 7 THEN '4-7 dias' "
            "  WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 14 THEN '8-14 dias' "
            "  ELSE 'mais de 14 dias' END")
        contagem = {linha[0]: linha[1] for linha in cur.fetchall()}
        # Faixa sem chamado vem com 0 EXPLÍCITO e na ordem fixa: buraco no
        # gráfico faria "nenhum chamado velho" parecer "não medi isso".
        saida["aging"] = [{"faixa": nome, "total": contagem.get(nome, 0)}
                          for nome, _i, _f in FAIXAS_AGING]

        # ── tipo × estado ───────────────────────────────────────────────────
        cur.execute(
            "SELECT tipo, estado_kanban, COUNT(*) FROM dbo.etl_chamado "
            "WHERE ativo = 1" + _so_trabalhos() +
            " GROUP BY tipo, estado_kanban")
        celulas = [{"tipo": r[0], "estado": r[1], "total": r[2]}
                   for r in cur.fetchall()]
        saida["tipo_estado"] = {
            "tipos": sorted({c["tipo"] for c in celulas}),
            "estados": list(COLUNAS_KANBAN),
            "celulas": celulas,
        }

        # ── entradas × saídas dos últimos 14 dias ───────────────────────────
        cur.execute(
            "SELECT CAST(aberto_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            "WHERE aberto_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            # Histórico: o pai pode já ter saído da fila, então o recorte
            # olha o espelho INTEIRO, não só os ativos.
            + _so_trabalhos(entre_ativos=False) +
            " GROUP BY CAST(aberto_em AS DATE)", [-(DIAS_FLUXO - 1)])
        entradas = {str(r[0])[:10]: r[1] for r in cur.fetchall()}
        cur.execute(
            "SELECT CAST(encerrado_em AS DATE), COUNT(*) FROM dbo.etl_chamado "
            "WHERE encerrado_em >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
            + _so_trabalhos(entre_ativos=False) +
            " GROUP BY CAST(encerrado_em AS DATE)", [-(DIAS_FLUXO - 1)])
        saidas = {str(r[0])[:10]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT CAST(GETDATE() AS DATE)")
        hoje = cur.fetchone()[0]
        import datetime as _dt
        if not isinstance(hoje, _dt.date):
            hoje = _dt.date.fromisoformat(str(hoje)[:10])
        # Todos os 14 dias, inclusive os sem movimento: dia sem encerramento é
        # um ZERO dito, não uma lacuna na série (critério de aceite da spec).
        saida["fluxo"] = [
            {"dia": (d := str(hoje - _dt.timedelta(days=i))),
             "entradas": entradas.get(d, 0), "saidas": saidas.get(d, 0)}
            for i in range(DIAS_FLUXO - 1, -1, -1)
        ]

        # ── carga por responsável ───────────────────────────────────────────
        cur.execute(
            "SELECT ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável'), "
            "       COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1 "
            + _so_trabalhos() +
            " GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(atribuido_a)), ''), 'sem responsável') "
            "ORDER BY COUNT(*) DESC")
        todos = [{"responsavel": r[0], "total": r[1]} for r in cur.fetchall()]
        saida["carga"] = todos[:TOPO_RESPONSAVEIS]
        saida["responsaveis_ocultos"] = max(0, len(todos) - TOPO_RESPONSAVEIS)

        cur.execute("SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1"
                    + _so_trabalhos())
        saida["total_ativos"] = cur.fetchone()[0]
        cur.close(); conn.close()
    except Exception as e:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        log.warning("indicadores: espelho indisponível (%s: %s)", type(e).__name__, e)
        saida["migration_ausente"] = True
    return saida


# ═══════════════════════════════════════════════════════════════════════════
# Sincronizar agora — o botão da tela
# ═══════════════════════════════════════════════════════════════════════════
DAG_SYNC = "etl_servicenow_sync"


@router.post("/chamados/sincronizar", tags=["chamados"])
async def sincronizar_agora(auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Dispara o ciclo do sync agora, sem esperar o próximo quarto de hora.

    Três recusas ANTES de disparar, e cada uma existe porque o contrário
    devolveria "disparado com sucesso" para um ciclo que nunca ia rodar:

      1. **integração desligada** — a DAG sai no interruptor sem tocar em
         nada, e o operador ficaria esperando uma fila que não muda;
      2. **credencial incompleta** — o ciclo abre, falha na 1ª chamada e
         grava ERRO; melhor recusar aqui, onde dá para dizer o que falta;
      3. **DAG pausada no Airflow** — este é o mais traiçoeiro: a API do
         Airflow ACEITA criar a run, devolve 200, e a run fica parada para
         sempre. Sucesso na tela, nada acontecendo no servidor.

    Quem disparou vai no `conf` e a DAG grava em `etl_chamado_sync.
    disparado_por` — sem isso todo ciclo aparece como "schedule" e o histórico
    não distingue o agendado do provocado.
    """
    from services import servicenow
    from routers.airflow import get_airflow_client

    cfg = servicenow.load_config()
    if not servicenow.configurado(cfg):
        raise HTTPException(
            status_code=422,
            detail="ServiceNow não configurado — informe URL, usuário e senha "
                   "em Admin > ServiceNow antes de sincronizar.")
    if not cfg["habilitado"]:
        raise HTTPException(
            status_code=422,
            detail="A sincronização está desabilitada em Admin > ServiceNow. "
                   "Ligue o interruptor antes de disparar.")

    quem = (auth or {}).get("matricula") or "?"
    try:
        async with get_airflow_client() as client:
            estado = await client.get(f"/api/v1/dags/{DAG_SYNC}")
            if estado.status_code == 404:
                raise HTTPException(
                    status_code=502,
                    detail=f"A DAG {DAG_SYNC} não existe no Airflow — o deploy "
                           f"das DAGs pode não ter sido aplicado.")
            if estado.is_success and (estado.json() or {}).get("is_paused"):
                raise HTTPException(
                    status_code=409,
                    detail=f"A DAG {DAG_SYNC} está PAUSADA no Airflow. Um "
                           f"disparo agora ficaria na fila sem executar — "
                           f"despause antes.")
            r = await client.post(
                f"/api/v1/dags/{DAG_SYNC}/dagRuns",
                json={"conf": {"disparado_por": f"manual:{quem}"}},
                headers={"Content-Type": "application/json"})
            if not r.is_success:
                raise HTTPException(
                    status_code=502,
                    detail=f"O Airflow recusou o disparo (HTTP {r.status_code}). "
                           f"{r.text[:200]}")
            corpo = r.json() or {}
    except HTTPException:
        raise
    except Exception as e:
        log.warning("chamados/sincronizar: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=502,
                            detail=f"Não foi possível falar com o Airflow: {e}")

    log.info("chamados: sync disparado manualmente por %s (run %s)",
             quem, corpo.get("dag_run_id"))
    return {
        "sucesso": True,
        "dag_run_id": corpo.get("dag_run_id"),
        # A tela usa isto para NÃO prometer dados na hora: o ciclo leva
        # minutos (a fila do grupo tem milhares de registros historicos), e um
        # "pronto!" imediato faria o operador recarregar e achar que falhou.
        "mensagem": "Sincronização disparada. O ciclo leva alguns minutos; "
                    "o carimbo de frescor atualiza quando terminar.",
    }
