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

from utils.chamado_derivacoes import derivar
from utils.frescor_modulo import carimbar

# Carimbo de frescor: a DAG confere se este módulo em memória é o do disco.
# Ver utils/frescor_modulo.py — o worker Celery serve módulos auxiliares de
# cache, e o código velho rodando não produz sintoma nenhum.
carimbar(__file__)

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
          "assignment_group,opened_at,sys_updated_on,closed_at,active,"
          # Parentesco: no catálogo, `request_item` liga a sc_task ao RITM que
          # a gerou; `parent` é o genérico das demais tabelas. Pedimos os dois
          # e usamos o que vier — campo inexistente numa tabela é simplesmente
          # omitido pela Table API, não dá erro.
          "parent,request_item,"
          # Conteúdo (migration 091): sem descrição e work notes não há
          # triagem possível — nem por IA nem por heurística. `u_sla_expired`
          # é campo customizado da instância; se não existir na tabela, a
          # Table API apenas o omite.
          "description,work_notes,cat_item,requested_for,"
          "estimated_delivery,due_date,u_sla_expired")

# Limite da coluna titulo (NVARCHAR(400) na migration 088).
TITULO_MAX = 400

# Limite de descricao e work_notes (NVARCHAR(4000) na migration 091). A
# triagem lê bem menos que isso (o painel usa 1500 e 2000), então o corte não
# tira informação de decisão — e ele é explícito, com reticência.
TEXTO_MAX = 4000

# Chave da rota de saída em etl_app_config (migration 089). O literal espelha
# K_PROXY de api/services/servicenow.py — a fonte é a mesma tabela; duplicar
# aqui evita a árvore dags/ importar de api/.
K_PROXY = "servicenow_proxy"

# Página da Table API. 100 é o teto confortável do endpoint sem timeout.
PAGINA = 100

# Teto de páginas por tabela — trava de segurança contra paginação infinita
# (filtro que não casa + API que ignora offset = laço eterno no worker).
MAX_PAGINAS = 50

# ── Mapeamento estado → coluna do kanban ────────────────────────────────────
# Valores CRUS da API (o `state` numérico), por tabela. Conferidos contra a
# instância real pela sonda do Admin — o que NÃO estiver aqui cai em 'outros'
# e APARECE na tela; nada some em silêncio (risco #3 da spec).
# ✅ = valor CONFERIDO contra a instância cvpsnprod em 2026-08-13, pela coluna
#      estado_cru do espelho (migration 090). Os demais seguem ASSUMIDOS da
#      spec: quando aparecerem, `estado_cru` os revela sem palpite —
#      SELECT tipo, estado_cru, estado_origem, estado_kanban, COUNT(*)
#      FROM dbo.etl_chamado WHERE ativo=1 GROUP BY ...
ESTADOS = {
    "incident": {
        "1": "novo", "2": "andamento", "3": "aguardando",
        "6": "resolvido",                       # ✅ "Resolvido(a)"
        "7": "encerrado", "8": "encerrado",
    },
    "sc_req_item": {
        # ⚠️ '-5' FALTAVA aqui: "Pendente" caía em 'outros'. A coluna
        # Aguardando ficava vazia enquanto os pendentes se acumulavam fora
        # dela — a tela dizia "não sei" sobre um estado corriqueiro.
        "-5": "aguardando",                     # ✅ "Pendente"
        "1": "novo",                            # ✅ "Em aberto"
        "2": "andamento",                       # ✅ "Trabalho em andamento"
        "3": "aguardando", "4": "aguardando", "5": "aguardando",
        "6": "resolvido",                       # ✅ "Resolvido"
        "7": "encerrado",
    },
    "sc_task": {
        # ⚠️ '-5' apontava para 'novo' — pior que 'outros': o chamado PARADO
        # esperando aparecia como recém-chegado, e ninguém desconfia de um
        # card na coluna Novo. Erro que não parece erro.
        "-5": "aguardando",                     # ✅ "Pendente"
        "1": "novo",                            # ✅ "Em aberto"
        "2": "andamento",                       # ✅ "Trabalho em andamento"
        "3": "resolvido", "4": "encerrado", "7": "encerrado",
    },
    "change_request": {
        # Nenhum change no grupo até agora (qtd_change=0 com ciclo OK, ou
        # seja, fila vazia mesmo — não ACL). Tudo aqui segue assumido.
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


def unidades_utf16(texto: str) -> int:
    """Quantas unidades NVARCHAR o texto ocupa.

    NVARCHAR(n) conta unidades UTF-16, não caracteres: emoji fora do BMP
    (🙂, 🔥) ocupa DUAS. Medir com `len()` do Python deixa passar um texto de
    4000 caracteres que ocupa 4300 unidades, e o SQL Server responde com
    Msg 8152 no meio do ciclo — justamente o texto colado do Teams que a
    migration 091 diz esperar.
    """
    return len(texto.encode("utf-16-le")) // 2


def _cortar(texto: str, limite: int) -> str:
    """Corta pelo limite REAL da coluna, sem partir um par substituto.

    Iterar por caractere garante que um emoji nunca é cortado ao meio — o que
    produziria texto inválido no banco.
    """
    if unidades_utf16(texto) <= limite:
        return texto
    alvo = limite - 1            # a reticência ocupa 1 unidade
    saida, total = [], 0
    for ch in texto:
        custo = unidades_utf16(ch)
        if total + custo > alvo:
            break
        saida.append(ch)
        total += custo
    return "".join(saida) + "…"


def truncar_titulo(titulo, limite: int = TITULO_MAX) -> str:
    """Corta COM reticência: o operador precisa ver que faltou texto.

    Truncar calado já mordeu antes (VARCHAR estourado, PR #161) — aqui o corte
    é explícito e a marca fica visível no card.
    """
    return _cortar((titulo or "").strip(), limite)


def truncar_texto(texto, limite: int = TEXTO_MAX) -> str:
    """Mesma regra do título, para descrição e work notes: corta COM
    reticência. O leitor precisa saber que o texto continua no ServiceNow."""
    return _cortar((texto or "").strip(), limite)


def _booleano(valor):
    """'true'/'false' da API → 1/0; ausente → None.

    None e 0 não são a mesma coisa: `u_sla_expired` é campo customizado e não
    existe em toda tabela. Colapsar ausência em 0 faria a tela dizer "está no
    prazo" sobre chamado cujo SLA ninguém mediu.
    """
    texto = (valor or "").strip().lower()
    if texto in ("true", "1"):
        return 1
    if texto in ("false", "0"):
        return 0
    return None


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


def _pai(registro: dict) -> tuple[str, str]:
    """(sys_id, numero) do chamado pai, ou ('', '') se não houver.

    `request_item` manda sobre `parent`: numa sc_task de catálogo os dois
    costumam vir preenchidos, e é o request_item que aponta para o RITM — o
    parent pode apontar para outra coisa na hierarquia.

    Com `sysparm_display_value=all` o campo de referência volta inteiro na
    MESMA requisição: display_value é o número (RITM0096880), value é o
    sys_id. Guardamos os dois — o sys_id dá join exato contra o espelho, o
    número é o que a tela mostra. Sem chamada extra à API.
    """
    for campo in ("request_item", "parent"):
        bruto = registro.get(campo)
        sys_id, numero = _cru(bruto), _display(bruto)
        if sys_id or numero:
            return sys_id[:32], numero[:20]
    return "", ""


def normalizar(registro: dict, tabela: str, tipo: str, url_base: str) -> dict:
    """Registro cru da API → linha do espelho."""
    sys_id = _display(registro.get("sys_id")) or _cru(registro.get("sys_id"))
    estado_cru = _cru(registro.get("state"))
    ativo_bruto = (_cru(registro.get("active")) or "").lower()
    estado_kanban = mapear_estado(tabela, estado_cru)
    pai_sys_id, pai_numero = _pai(registro)
    # `active` da origem manda; 'encerrado' também sai da fila mesmo que a
    # origem ainda diga ativo (estado terminal com active=true acontece).
    ativo = ativo_bruto == "true" and estado_kanban != FORA_DO_KANBAN
    linha = {
        "sys_id": sys_id,
        "numero": _display(registro.get("number"))[:20],
        "tipo": tipo,
        "titulo": truncar_titulo(_display(registro.get("short_description"))),
        "estado_origem": (_display(registro.get("state")) or estado_cru)[:60],
        # O NÚMERO do estado, ao lado do rótulo. `estado_origem` guarda
        # "Pendente"; o mapa do kanban é por número. Sem esta coluna, corrigir
        # um estado que caiu em 'outros' exige ir perguntar à API — e quando
        # dois números apontam para a mesma coluna, nem isso resolve.
        "estado_cru": estado_cru[:20],
        "pai_sys_id": pai_sys_id,
        "pai_numero": pai_numero,
        "estado_kanban": estado_kanban if estado_kanban != FORA_DO_KANBAN else "resolvido",
        "prioridade": _display(registro.get("priority"))[:20],
        "atribuido_a": _display(registro.get("assigned_to"))[:120],
        "grupo": _display(registro.get("assignment_group"))[:120],
        "aberto_em": _data(_cru(registro.get("opened_at"))),
        "atualizado_em": _data(_cru(registro.get("sys_updated_on"))),
        "encerrado_em": _data(_cru(registro.get("closed_at"))),
        "ativo": 1 if ativo else 0,
        "url": f"{url_base}/nav_to.do?uri={tabela}.do?sys_id={sys_id}"[:500],
        # ── Conteúdo (migration 091) ────────────────────────────────────
        # `description` e `work_notes` vêm como texto puro; nas referências
        # (`cat_item`, `requested_for`) o que interessa é o display_value.
        "descricao": truncar_texto(_display(registro.get("description"))
                                   or _cru(registro.get("description"))),
        "work_notes": truncar_texto(_display(registro.get("work_notes"))
                                    or _cru(registro.get("work_notes"))),
        "catalogo": _display(registro.get("cat_item"))[:200],
        "demandante": _display(registro.get("requested_for"))[:120],
        "prazo": _data(_cru(registro.get("estimated_delivery"))),
        "vencimento": _data(_cru(registro.get("due_date"))),
        "sla_vencido": _booleano(_cru(registro.get("u_sla_expired"))),
    }
    # Derivações (migration 092) na INGESTÃO, não na leitura: regex por linha
    # a cada request faria a tela pagar o custo toda vez e — pior — o
    # resultado variaria conforme a versão do código que respondeu.
    linha.update(derivar(linha))
    return linha


def proxy_da_config(cfg: dict) -> str | None:
    """Proxy de saída do sync, vindo de `servicenow_proxy` (migration 089).

    **Config e não variável de ambiente**, de propósito. O worker do Airflow
    já roda com o ambiente que tem: variável nova só entra em container NOVO,
    e recriar o worker mata as tasks em execução — inclusive jobs DataStage,
    que seguem vivos no DS enquanto o Airflow os dá por mortos. Pela config,
    trocar a rota é editar um campo no Admin e esperar o próximo ciclo.

    Passar o proxy por PARÂMETRO ao httpx (em vez de deixar o `trust_env`
    ler HTTPS_PROXY) faz o cliente ignorar o `NO_PROXY` — a ressalva da
    PR #304. Aqui isso é inofensivo: este cliente fala com UM host externo e
    mais nada, então não existe host interno para o NO_PROXY isentar.

    Vazio ou só espaços = None = conexão direta (é assim que o dev roda).
    Quem chama IMPRIME a rota escolhida: proxy ausente e proxy errado dão o
    mesmo erro de rede, e só o log separa os dois.
    """
    return (cfg.get(K_PROXY) or "").strip() or None


def query_do_grupo(grupos: list[str]) -> str:
    """sysparm_query filtrando por grupo de atribuição.

    Sem grupo NÃO devolve query vazia: uma consulta sem filtro traria a fila
    da empresa inteira. Quem chama trata a lista vazia antes.
    """
    if not grupos:
        raise ValueError("nenhum grupo configurado — o sync sem filtro traria "
                         "a fila da empresa inteira")
    return "^OR".join(f"assignment_group.name={g}" for g in grupos)


# A ordem desta tupla é a ÚNICA fonte da ordem dos campos no MERGE: o SQL e os
# parâmetros são montados a partir dela. Antes, a lista aparecia três vezes
# escrita à mão (UPDATE, INSERT e params) e acrescentar uma coluna significava
# acertar as três — errar uma grava o valor na coluna vizinha, sem erro nenhum
# no log.
CAMPOS_UPSERT = (
    "numero", "tipo", "titulo", "estado_origem", "estado_kanban",
    "prioridade", "atribuido_a", "grupo", "aberto_em", "atualizado_em",
    "encerrado_em", "ativo", "url", "estado_cru", "pai_sys_id", "pai_numero",
    # migration 091
    "descricao", "work_notes", "catalogo", "demandante", "prazo",
    "vencimento", "sla_vencido",
    # migration 092 — derivadas na ingestão
    "tipo_demanda", "categoria_diaadia", "objetos",
)


def upsert_sql() -> str:
    """MERGE por sys_id — placeholder %s (pymssql, árvore dags/)."""
    atribuicoes = ", ".join(f"{c}=%s" for c in CAMPOS_UPSERT)
    colunas = ", ".join(CAMPOS_UPSERT)
    valores = ", ".join(["%s"] * len(CAMPOS_UPSERT))
    return f"""
        MERGE dbo.etl_chamado AS t
        USING (SELECT %s AS sys_id) AS s ON t.sys_id = s.sys_id
        WHEN MATCHED THEN UPDATE SET
            {atribuicoes}, sync_em=GETDATE()
        WHEN NOT MATCHED THEN INSERT
            (sys_id, {colunas}, sync_em)
            VALUES (s.sys_id, {valores}, GETDATE());
    """


def upsert_params(linha: dict) -> tuple:
    """Os parâmetros do MERGE, na ordem: chave + UPDATE + INSERT."""
    campos = tuple(linha[c] for c in CAMPOS_UPSERT)
    return (linha["sys_id"],) + campos + campos
