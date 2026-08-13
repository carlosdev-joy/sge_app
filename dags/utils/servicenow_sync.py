"""dags/utils/servicenow_sync.py — o miolo do sync dos chamados.

Separado da DAG para poder ser testado sem Airflow e sem rede: a DAG só
orquestra, aqui mora a regra. O dev NÃO alcança o ServiceNow da empresa, então
tudo aqui é exercitado com o cliente HTTP stubado — a prova real é o smoke §7
em produção ("dev testa, produção manda").

⚠️ Esta árvore (`dags/`) fala com o banco por pymssql: placeholder é `%s`.
A árvore `api/` usa pyodbc (`?`). Trocar os dois dá "Incorrect syntax near '?'"
— ou, pior, gravação nenhuma com a task VERDE.
"""
from __future__ import annotations

import datetime as _dt
import os

# ── Constantes ANTES dos helpers (gotcha do dag_factory: helper que lê uma
#    const definida abaixo quebra no parse da DAG). ─────────────────────────
MSSQL_CONN_ID = "SQL14_DMDB41"

# As 4 tabelas do ServiceNow e o tipo curto que o espelho guarda.
TABELAS = (
    ("incident",       "incident"),
    ("sc_req_item",    "ritm"),
    ("sc_task",        "task"),
    ("change_request", "change"),
)

# Campos pedidos à Table API. `sysparm_display_value=all` devolve display E
# valor cru; pedimos os campos explicitamente para não trafegar o registro
# inteiro (fila de ~50, mas o payload completo do ServiceNow é gordo).
CAMPOS = ("sys_id,number,short_description,state,priority,assigned_to,"
          "assignment_group,opened_at,sys_updated_on,closed_at,active")

# Limite da coluna titulo (NVARCHAR(400) na migration 088).
TITULO_MAX = 400

# Página da Table API. 100 é o teto confortável do endpoint sem timeout.
PAGINA = 100

# Teto de páginas por tabela — trava de segurança contra paginação infinita
# (filtro que não casa + API que ignora offset = laço eterno no worker).
MAX_PAGINAS = 50

# ── Mapeamento estado → coluna do kanban ────────────────────────────────────
# Valores CRUS da API (o `state` numérico), por tabela. Conferidos contra a
# instância real pela sonda do Admin — o que NÃO estiver aqui cai em 'outros'
# e APARECE na tela; nada some em silêncio (risco #3 da spec).
ESTADOS = {
    "incident": {
        "1": "novo", "2": "andamento", "3": "aguardando",
        "6": "resolvido", "7": "encerrado", "8": "encerrado",
    },
    "sc_req_item": {
        "1": "novo", "2": "andamento", "3": "aguardando",
        "4": "aguardando", "5": "aguardando",
        "6": "resolvido", "7": "encerrado",
    },
    "sc_task": {
        "-5": "novo", "1": "novo", "2": "andamento", "3": "resolvido",
        "4": "encerrado", "7": "encerrado",
    },
    "change_request": {
        "-5": "novo", "-4": "novo", "-3": "andamento", "-2": "andamento",
        "-1": "aguardando", "0": "resolvido", "3": "encerrado", "4": "encerrado",
    },
}

# 'encerrado' não é coluna do kanban: sai da fila (ativo=0) mas continua no
# espelho para os indicadores de entradas × saídas (F5).
FORA_DO_KANBAN = "encerrado"

COLUNAS_KANBAN = ("novo", "andamento", "aguardando", "resolvido", "outros")


def mapear_estado(tabela: str, estado_cru) -> str:
    """Estado cru da API → coluna do kanban.

    Desconhecido vira 'outros' DE PROPÓSITO: um estado novo criado no
    ServiceNow não pode fazer o chamado desaparecer da tela — some da fila
    sem ninguém notar é pior que aparecer na coluna errada.
    """
    return ESTADOS.get(tabela, {}).get(str(estado_cru or "").strip(), "outros")


def truncar_titulo(titulo, limite: int = TITULO_MAX) -> str:
    """Corta COM reticência: o operador precisa ver que faltou texto.

    Truncar calado já mordeu antes (VARCHAR estourado, PR #161) — aqui o corte
    é explícito e a marca fica visível no card.
    """
    t = (titulo or "").strip()
    return t if len(t) <= limite else t[:limite - 1] + "…"


def _data(valor):
    """'2026-08-13 10:49:51' → datetime; vazio/ilegível → None.

    Data ilegível não pode derrubar o ciclo inteiro por causa de um registro:
    o chamado entra com a data em branco e o resto do sync segue.
    """
    texto = (valor or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _display(campo):
    """A Table API devolve referência como {'display_value':…,'value':…}."""
    if isinstance(campo, dict):
        return (campo.get("display_value") or "").strip()
    return (campo or "").strip() if isinstance(campo, str) else ""


def _cru(campo):
    """O valor CRU (o `state` numérico), mesmo em display_value=all."""
    if isinstance(campo, dict):
        return (campo.get("value") or "").strip()
    return (campo or "").strip() if isinstance(campo, str) else ""


def normalizar(registro: dict, tabela: str, tipo: str, url_base: str) -> dict:
    """Registro cru da API → linha do espelho."""
    sys_id = _display(registro.get("sys_id")) or _cru(registro.get("sys_id"))
    estado_cru = _cru(registro.get("state"))
    ativo_bruto = (_cru(registro.get("active")) or "").lower()
    estado_kanban = mapear_estado(tabela, estado_cru)
    # `active` da origem manda; 'encerrado' também sai da fila mesmo que a
    # origem ainda diga ativo (estado terminal com active=true acontece).
    ativo = ativo_bruto == "true" and estado_kanban != FORA_DO_KANBAN
    return {
        "sys_id": sys_id,
        "numero": _display(registro.get("number"))[:20],
        "tipo": tipo,
        "titulo": truncar_titulo(_display(registro.get("short_description"))),
        "estado_origem": (_display(registro.get("state")) or estado_cru)[:60],
        "estado_kanban": estado_kanban if estado_kanban != FORA_DO_KANBAN else "resolvido",
        "prioridade": _display(registro.get("priority"))[:20],
        "atribuido_a": _display(registro.get("assigned_to"))[:120],
        "grupo": _display(registro.get("assignment_group"))[:120],
        "aberto_em": _data(_cru(registro.get("opened_at"))),
        "atualizado_em": _data(_cru(registro.get("sys_updated_on"))),
        "encerrado_em": _data(_cru(registro.get("closed_at"))),
        "ativo": 1 if ativo else 0,
        "url": f"{url_base}/nav_to.do?uri={tabela}.do?sys_id={sys_id}"[:500],
    }


def proxy_configurado() -> str | None:
    """Proxy de saída do sync (`SERVICENOW_PROXY`), ou None para rota direta.

    A variável é PRÓPRIA em vez do `HTTPS_PROXY` do ambiente, e a diferença é
    deliberada. O worker do Airflow executa TODA DAG do Orquestra, inclusive
    os nós HttpCall de pipelines cadastrados pelos usuários, que apontam para
    hosts internos. `HTTPS_PROXY` no worker valeria para todos eles, e o que
    os protegeria seria o `NO_PROXY` estar completo — uma lista que ninguém
    revisa até um pipeline de produção quebrar.

    Este cliente httpx fala com UM host externo e mais nada, então passar o
    proxy por parâmetro é seguro aqui: a ressalva da PR #304 (parâmetro faz o
    httpx ignorar o `NO_PROXY`) só morde quando o mesmo cliente precisa
    alcançar hosts internos, que não é o caso.

    Vazio, só espaços ou ausente = None = conexão direta (é assim que o dev
    roda). Quem chama IMPRIME a rota escolhida: "sem proxy" e "com proxy"
    falhando dão o mesmo erro de rede, e só o log separa os dois.
    """
    return (os.getenv("SERVICENOW_PROXY") or "").strip() or None


def query_do_grupo(grupos: list[str]) -> str:
    """sysparm_query filtrando por grupo de atribuição.

    Sem grupo NÃO devolve query vazia: uma consulta sem filtro traria a fila
    da empresa inteira. Quem chama trata a lista vazia antes.
    """
    if not grupos:
        raise ValueError("nenhum grupo configurado — o sync sem filtro traria "
                         "a fila da empresa inteira")
    return "^OR".join(f"assignment_group.name={g}" for g in grupos)


def upsert_sql() -> str:
    """MERGE por sys_id — placeholder %s (pymssql, árvore dags/)."""
    return """
        MERGE dbo.etl_chamado AS t
        USING (SELECT %s AS sys_id) AS s ON t.sys_id = s.sys_id
        WHEN MATCHED THEN UPDATE SET
            numero=%s, tipo=%s, titulo=%s, estado_origem=%s, estado_kanban=%s,
            prioridade=%s, atribuido_a=%s, grupo=%s, aberto_em=%s,
            atualizado_em=%s, encerrado_em=%s, ativo=%s, url=%s, sync_em=GETDATE()
        WHEN NOT MATCHED THEN INSERT
            (sys_id, numero, tipo, titulo, estado_origem, estado_kanban,
             prioridade, atribuido_a, grupo, aberto_em, atualizado_em,
             encerrado_em, ativo, url, sync_em)
            VALUES (s.sys_id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, GETDATE());
    """


def upsert_params(linha: dict) -> tuple:
    """Os parâmetros do MERGE, na ordem: chave + UPDATE + INSERT."""
    campos = (linha["numero"], linha["tipo"], linha["titulo"],
              linha["estado_origem"], linha["estado_kanban"],
              linha["prioridade"], linha["atribuido_a"], linha["grupo"],
              linha["aberto_em"], linha["atualizado_em"], linha["encerrado_em"],
              linha["ativo"], linha["url"])
    return (linha["sys_id"],) + campos + campos
