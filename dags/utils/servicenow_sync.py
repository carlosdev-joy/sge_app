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
          "parent,request_item")

# Limite da coluna titulo (NVARCHAR(400) na migration 088).
TITULO_MAX = 400

# Chave da rota de saída em etl_app_config (migration 089). O literal espelha
# K_PROXY de api/services/servicenow.py — a fonte é a mesma tabela; duplicar
# aqui evita a árvore dags/ importar de api/.
K_PROXY = "servicenow_proxy"

# Página da Table API. 100 é o teto confortável do endpoint sem timeout.
PAGINA = 100

# Teto de páginas por tabela — trava de segurança contra paginação infinita
# (filtro que não casa + API que ignora offset = laço eterno no worker).
MAX_PAGINAS = 50

# Janela do histórico trazido além do que está ATIVO, em dias. Precisa ser
# MAIOR que DIAS_FLUXO (14, api/routers/chamados.py): os indicadores de
# entradas × saídas olham 14 dias e leem `encerrado_em`, que só existe se o
# chamado ainda estiver vindo da API quando fecha. 30 dá margem para o ciclo
# falhar alguns dias seguidos sem abrir buraco na série.
DIAS_HISTORICO = 30

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
    return {
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
    }


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


def query_do_grupo(grupos: list[str], dias_historico: int = DIAS_HISTORICO) -> str:
    """sysparm_query: grupo(s) de atribuição + janela de relevância.

    Sem grupo NÃO devolve query vazia: uma consulta sem filtro traria a fila
    da empresa inteira. Quem chama trata a lista vazia antes.

    **A janela existe por volume.** Medido em produção: o filtro só-por-grupo
    trazia 3.376 registros por ciclo (103 incidents + 1.636 RITMs + 1.637
    tasks) para uma fila ATIVA de 113. Era o histórico inteiro do grupo,
    reescrito de 15 em 15 minutos — ~324 mil upserts e ~3.500 requisições
    diárias ao ServiceNow, numa conta de serviço compartilhada com o Power BI.

    O recorte é `ativo OU mexido nos últimos N dias`, não apenas `ativo`:
      • o que está na fila vem sempre, independente de idade;
      • o que fechou recentemente continua vindo, porque os indicadores de
        entradas × saídas olham 14 dias e precisam do `encerrado_em`;
      • o que fechou há muito tempo PARA de ser reescrito — e não some da
        tela: já está no espelho, e o que sai da consulta é marcado ativo=0
        pela rotina de desativação, que é o comportamento correto.

    ⚠️ Sintaxe do encoded query: `^` separa grupos AND e `^OR` encadeia dentro
    do grupo corrente. Então `g=A^ORg=B^active=true^ORsys_updated_on>=X` lê
    como `(g=A OU g=B) E (ativo OU mexido recentemente)`. Não existem
    parênteses na linguagem — a ordem é o que agrupa.
    """
    if not grupos:
        raise ValueError("nenhum grupo configurado — o sync sem filtro traria "
                         "a fila da empresa inteira")
    filtro_grupo = "^OR".join(f"assignment_group.name={g}" for g in grupos)
    if dias_historico <= 0:          # 0 = sem janela (o comportamento antigo)
        return filtro_grupo
    return (f"{filtro_grupo}"
            f"^active=true"
            f"^ORsys_updated_on>=javascript:gs.daysAgoStart({dias_historico})")


def pertence_ao_grupo(linha: dict, grupos: list[str]) -> bool:
    """O chamado é mesmo de um dos grupos configurados?

    Guarda de defesa em profundidade contra a sintaxe do encoded query. O
    ServiceNow não tem parênteses: `^` abre grupo AND, `^OR` encadeia dentro
    do grupo corrente, e a precedência é POSICIONAL. Se essa leitura estiver
    errada — ou mudar numa atualização da plataforma —, a janela de histórico
    poderia virar um OR solto e o espelho encheria com a fila da empresa
    inteira, que é exatamente o risco que `query_do_grupo` existe para evitar.

    Aqui a resposta da API é conferida contra a configuração antes de gravar.
    Sem grupo configurado devolve True: quem chama já recusou esse caso antes,
    e recusar de novo aqui esconderia o erro de configuração atrás de uma
    fila vazia.
    """
    if not grupos:
        return True
    alvo = (linha.get("grupo") or "").strip().casefold()
    return any(alvo == g.strip().casefold() for g in grupos)


def upsert_sql() -> str:
    """MERGE por sys_id — placeholder %s (pymssql, árvore dags/)."""
    return """
        MERGE dbo.etl_chamado AS t
        USING (SELECT %s AS sys_id) AS s ON t.sys_id = s.sys_id
        WHEN MATCHED THEN UPDATE SET
            numero=%s, tipo=%s, titulo=%s, estado_origem=%s, estado_kanban=%s,
            prioridade=%s, atribuido_a=%s, grupo=%s, aberto_em=%s,
            atualizado_em=%s, encerrado_em=%s, ativo=%s, url=%s,
            estado_cru=%s, pai_sys_id=%s, pai_numero=%s, sync_em=GETDATE()
        WHEN NOT MATCHED THEN INSERT
            (sys_id, numero, tipo, titulo, estado_origem, estado_kanban,
             prioridade, atribuido_a, grupo, aberto_em, atualizado_em,
             encerrado_em, ativo, url, estado_cru, pai_sys_id, pai_numero,
             sync_em)
            VALUES (s.sys_id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, GETDATE());
    """


def upsert_params(linha: dict) -> tuple:
    """Os parâmetros do MERGE, na ordem: chave + UPDATE + INSERT."""
    campos = (linha["numero"], linha["tipo"], linha["titulo"],
              linha["estado_origem"], linha["estado_kanban"],
              linha["prioridade"], linha["atribuido_a"], linha["grupo"],
              linha["aberto_em"], linha["atualizado_em"], linha["encerrado_em"],
              linha["ativo"], linha["url"],
              linha["estado_cru"], linha["pai_sys_id"], linha["pai_numero"])
    return (linha["sys_id"],) + campos + campos
