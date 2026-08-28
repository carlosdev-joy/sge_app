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
# A regra do corte mora em texto_sql: NVARCHAR conta unidades UTF-16,
# e reescrever isso em cada módulo já produziu o mesmo defeito duas vezes.
from utils.texto_sql import cortar as _cortar, unidades_utf16  # noqa: F401
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
          "estimated_delivery,due_date,u_sla_expired,"
          # O e-mail do analista: o dashboard filtra "Meu painel" por
          # IGUALDADE, e não por LIKE sobre o nome — nome do meio,
          # abreviação e homônimo fazem o LIKE trazer chamado alheio,
          # e a tela mostra a fila filtrada, nunca a regra.
          "assigned_to.email")

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
        # ⚠️ cru=3 é "Closed Complete" em sc_req_item: CONCLUÍDO.
        # Apurado contra a instância em 2026-08-21 e confirmado no dev
        # em 2026-08-28, com 1472 RITMs "Encerrado concluído" caindo
        # em 'aguardando'. Eles têm ativo=0, então não poluem a fila —
        # o estrago é nas contas que agrupam por estado_kanban sobre o
        # espelho INTEIRO (histórico, entradas × saídas, resolvidos):
        # lá, chamado concluído era contado como esperando alguém.
        # `4` é "Closed Incomplete": encerrado SEM entregar. Também é estado
        # FINAL — o pedido não volta a andar. Ficava em 'aguardando' junto com
        # o `3`, e pelo mesmo motivo: 84 RITMs "Encerrado incompleto" no
        # espelho do dev (2026-08-28) contados como pedido esperando alguém.
        #
        # Produção também erra este: a correção de lá parou no `3`. Depois de
        # arrumar o `3`, a coluna caiu de 1568 para 96 — e 84 dos 96 eram
        # exatamente estes. O que sobra em 'aguardando' são os 12 `-5`
        # ("Pendente"), que é o que a palavra quer dizer.
        #
        # O `5` fica como está: não apareceu no espelho, e mexer em estado que
        # não se viu é palpite — o mesmo palpite que pôs o `3` e o `4` aqui.
        "3": "encerrado", "4": "encerrado", "5": "aguardando",
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
        "atribuido_a": _cortar(_display(registro.get("assigned_to")), 120),
        # `_cru` e não `_display`: em assigned_to.email o valor É o
        # e-mail, e o display_value vem vazio para campos derivados
        # por ponto. Usar _display aqui gravaria '' em toda linha, e o
        # filtro do "Meu painel" não acharia ninguém — sem erro nenhum.
        "atribuido_a_email": _cortar(_cru(registro.get("assigned_to.email")), 200),
        "grupo": _cortar(_display(registro.get("assignment_group")), 120),
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
        "catalogo": _cortar(_display(registro.get("cat_item")), 200),
        "demandante": _cortar(_display(registro.get("requested_for")), 120),
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
    # migration 100 — e-mail do analista, para o filtro por igualdade
    "atribuido_a_email",
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


# ═══════════════════════════════════════════════════════════════════════════
# Delta, notas, anexos e snapshot — portados do motor que roda em produção.
#
# O ciclo completo (etl_servicenow_sync) varre a fila inteira a cada 15 min.
# O DELTA existe para o que não pode esperar 15 min e o FULL para a
# reconciliação periódica: sem os dois, ou a fila fica velha ou a instância
# recebe varredura completa o tempo todo.
#
# ⚠️ Árvore dags/: placeholder pymssql é %s. A árvore api/ usa ?, e trocar dá
# "Incorrect syntax near '?'" com a task VERDE, porque o try/except engole.
# ═══════════════════════════════════════════════════════════════════════════

def grupos_ativos(hook) -> list[str]:
    """Os grupos que o delta e o full monitoram.

    ⚠️ DUAS FONTES PARA A MESMA PERGUNTA, e é por isso que esta função existe
    em vez de um SELECT solto. O ciclo completo (`etl_servicenow_sync`) lê
    `servicenow_grupos` de `dbo.etl_app_config` — o campo que a tela Admin
    edita. O delta e o full, que vieram de produção, leem a TABELA
    `dbo.etl_servicenow_grupo`.

    Se as duas divergirem, o ciclo completo e o incremental passam a olhar
    filas diferentes, e nada avisa: os dois continuam "OK", com contagens que
    ninguém compara.

    A ordem aqui resolve o conflito sem inventar regra nova:

      1. a TABELA manda, quando tem linha ativa — é o cadastro mais específico,
         com ativo/inativo por grupo, e é o que produção usa hoje;
      2. sem nenhuma linha ativa, cai para a CONFIG. Isso é o que faz um
         ambiente recém-migrado funcionar: a 098 cria a tabela vazia, e sem
         este fallback o delta pularia em silêncio para sempre — foi
         exatamente o que aconteceu no dev em 2026-08-28
         ("nenhum grupo ativo em etl_servicenow_grupo — skip").

    Lista vazia nos dois lugares levanta no caller: delta sem filtro traria a
    instância inteira.
    """
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT nome FROM dbo.etl_servicenow_grupo WHERE ativo=1 ORDER BY nome")
    rows = [r[0] for r in cur.fetchall() if (r[0] or "").strip()]

    if not rows:
        cur.execute(
            "SELECT config_value FROM dbo.etl_app_config "
            "WHERE config_key='servicenow_grupos'")
        linha = cur.fetchone()
        bruto = (linha[0] if linha else "") or ""
        # Mesmo separador que `servicenow.parse_grupos()` usa na árvore api/:
        # 'A; B ;;C' → ['A', 'B', 'C']. Divergir daqui faria a mesma string
        # significar coisas diferentes nos dois lados.
        rows = [g.strip() for g in bruto.split(";") if g.strip()]

    cur.close()
    conn.close()
    return rows


def ultimo_delta_em(hook) -> _dt.datetime:
    """Ponto de corte do delta. Fallback: NOW() - 30min."""
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(iniciado_em) FROM dbo.etl_chamado_ciclo "
        "WHERE modo='delta' AND status IN ('OK','PARCIAL')")
    row = cur.fetchone()
    cur.close()
    conn.close()
    ts = row[0] if row else None
    if ts is None:
        return _dt.datetime.now() - _dt.timedelta(minutes=30)
    return ts


def query_delta(grupos: list[str], desde: _dt.datetime) -> str:
    """sysparm_query com filtro de grupo E sys_updated_on >= desde."""
    if not grupos:
        raise ValueError("nenhum grupo configurado — delta sem filtro traria fila inteira")
    desde_str = desde.strftime("%Y-%m-%d %H:%M:%S")
    grupo_parte = "^OR".join(f"assignment_group.name={g}" for g in grupos)
    return f"{grupo_parte}^sys_updated_on>={desde_str}"


def buscar_notas(cliente, url: str, sys_id: str) -> list[dict]:
    """sys_journal_field para um chamado. Apenas work_notes."""
    endpoint = (f"{url}/api/now/table/sys_journal_field"
                f"?sysparm_query=element_id={sys_id}^element=work_notes"
                f"^ORDERBYcreated_on&sysparm_display_value=all"
                f"&sysparm_fields=sys_id,element_id,sys_created_by,"
                f"sys_created_on,value,element")
    resp = cliente.get(endpoint)
    resp.raise_for_status()
    notas = []
    for r in resp.json().get("result", []):
        sys_id_nota = _cru(r.get("sys_id")) or _display(r.get("sys_id"))
        notas.append({
            "sys_id_nota": sys_id_nota[:32],
            "sys_id_chamado": sys_id[:32],
            "autor": _cortar(_display(r.get("sys_created_by")), 120),
            "autor_email": "",  # sys_journal_field não expõe email diretamente
            "criado_em": _data(_cru(r.get("sys_created_on"))),
            "texto": truncar_texto(_cru(r.get("value"))),
            "tipo": (_cru(r.get("element")) or "work_notes")[:20],
        })
    return notas


def buscar_anexos(cliente, url: str, sys_id: str) -> list[dict]:
    """Metadados de anexos de um chamado via /api/now/attachment."""
    endpoint = (f"{url}/api/now/attachment"
                f"?sysparm_query=table_sys_id={sys_id}"
                f"&sysparm_fields=sys_id,file_name,content_type,size_bytes,"
                f"sys_created_on")
    resp = cliente.get(endpoint)
    resp.raise_for_status()
    anexos = []
    for r in resp.json().get("result", []):
        sys_id_anexo = (r.get("sys_id") or "")[:32]
        anexos.append({
            "sys_id_anexo": sys_id_anexo,
            "sys_id_chamado": sys_id[:32],
            "nome_arquivo": _cortar(r.get("file_name") or "", 255),
            "mime_type": _cortar(r.get("content_type") or "", 100),
            "tamanho_bytes": int(r["size_bytes"]) if r.get("size_bytes") else None,
            "url_download": _cortar(
                f"{url}/api/now/attachment/{sys_id_anexo}/file", 500),
            "criado_em": _data((r.get("sys_created_on") or "").strip()),
        })
    return anexos


def upsert_nota_sql() -> str:
    """MERGE por sys_id_nota — SOMENTE INSERT, notas são imutáveis."""
    return """
        MERGE dbo.etl_chamado_nota AS t
        USING (SELECT %s AS sys_id_nota) AS s ON t.sys_id_nota = s.sys_id_nota
        WHEN NOT MATCHED THEN INSERT
            (sys_id_nota, sys_id_chamado, autor, autor_email,
             criado_em, texto, tipo)
            VALUES (s.sys_id_nota, %s, %s, %s, %s, %s, %s);
    """


def upsert_nota_params(nota: dict) -> tuple:
    """Parâmetros do MERGE de nota: chave + INSERT."""
    return (
        nota["sys_id_nota"],
        nota["sys_id_chamado"], nota["autor"], nota["autor_email"],
        nota["criado_em"], nota["texto"], nota["tipo"],
    )


def upsert_anexo_sql() -> str:
    """MERGE por sys_id_anexo — INSERT apenas (sem update de metadados)."""
    return """
        MERGE dbo.etl_chamado_anexo AS t
        USING (SELECT %s AS sys_id_anexo) AS s ON t.sys_id_anexo = s.sys_id_anexo
        WHEN NOT MATCHED THEN INSERT
            (sys_id_anexo, sys_id_chamado, nome_arquivo, mime_type,
             tamanho_bytes, url_download, criado_em)
            VALUES (s.sys_id_anexo, %s, %s, %s, %s, %s, %s);
    """


def upsert_anexo_params(anexo: dict) -> tuple:
    return (
        anexo["sys_id_anexo"],
        anexo["sys_id_chamado"], anexo["nome_arquivo"], anexo["mime_type"],
        anexo["tamanho_bytes"], anexo["url_download"], anexo["criado_em"],
    )


def capturar_snapshot(hook) -> int:
    """Grava snapshot + filhas. Retorna id do snapshot gravado."""
    conn = hook.get_conn()
    cur = conn.cursor()

    # ── contagens gerais ─────────────────────────────────────────────────────
    cur.execute(
        "SELECT COUNT(*) AS total, "
        "  SUM(CASE WHEN estado_kanban='novo' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='andamento' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='aguardando' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='resolvido' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='outros' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN sla_vencido=1 THEN 1 ELSE 0 END) "
        "FROM dbo.etl_chamado WHERE ativo=1")
    r = cur.fetchone() or (0,)*7
    total, novo, andamento, aguardando, resolvido, outros, sla_vencidos = (
        r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0)

    cur.execute(
        "SELECT AVG(CAST(DATEDIFF(DAY, aberto_em, GETDATE()) AS DECIMAL(6,1))) "
        "FROM dbo.etl_chamado WHERE ativo=1 AND aberto_em IS NOT NULL")
    idade_media = (cur.fetchone() or (None,))[0]

    cur.execute(
        "SELECT AVG(CAST(DATEDIFF(HOUR, aberto_em, encerrado_em) AS DECIMAL(8,1))) "
        "FROM dbo.etl_chamado "
        "WHERE encerrado_em >= DATEADD(DAY, -30, GETDATE()) "
        "  AND aberto_em IS NOT NULL AND encerrado_em IS NOT NULL")
    tempo_medio = (cur.fetchone() or (None,))[0]

    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_chamado "
        "WHERE encerrado_em >= DATEADD(DAY, -7, GETDATE())")
    qtd_enc_7d = (cur.fetchone() or (0,))[0] or 0

    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_chamado "
        "WHERE aberto_em >= DATEADD(DAY, -7, GETDATE())")
    qtd_ab_7d = (cur.fetchone() or (0,))[0] or 0

    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_chamado "
        "WHERE ativo=1 AND tipo_demanda='iniciativa'")
    qtd_inic = (cur.fetchone() or (0,))[0] or 0

    # ── INSERT snapshot cabeçalho ────────────────────────────────────────────
    cur.execute(
        "INSERT INTO dbo.etl_indicador_snapshot "
        "  (total_ativos, novo, andamento, aguardando, resolvido, outros, "
        "   sla_vencidos, idade_media_dias, tempo_medio_resolucao_horas, "
        "   qtd_encerrados_7d, qtd_abertos_7d, qtd_iniciativas_abertas) "
        "OUTPUT INSERTED.id "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (total, novo, andamento, aguardando, resolvido, outros, sla_vencidos,
         idade_media, tempo_medio, qtd_enc_7d, qtd_ab_7d, qtd_inic))
    snap_id = cur.fetchone()[0]

    # ── por analista ─────────────────────────────────────────────────────────
    cur.execute(
        # ⚠️ AGRUPA PELA CHAVE, não por nome + chave.
        #
        # A PK de etl_indicador_snapshot_analista é (id_snapshot,
        # atribuido_a_email). Agrupando por `atribuido_a, atribuido_a_email`,
        # dois analistas com o MESMO e-mail — ou, muito mais comum, dois
        # chamados SEM responsável, cujo e-mail é '' — produzem duas linhas com
        # a mesma chave, e o INSERT seguinte viola a PK.
        #
        # Não é hipótese: com a coluna recém-criada (todos os e-mails vazios), o
        # ciclo inteiro abortou no dev em 2026-08-28 com
        # "Violation of PRIMARY KEY constraint 'PK_snapshot_analista'". Em
        # produção o defeito está latente — basta um segundo chamado sem
        # responsável na fila ativa.
        #
        # MAX(atribuido_a) escolhe um nome representativo para o balde. Quando o
        # e-mail existe ele É a identidade (foi para isso que a coluna veio);
        # quando não existe, o balde é "sem responsável" e o nome é decorativo.
        "SELECT ISNULL(MAX(atribuido_a),''), ISNULL(atribuido_a_email,''), "
        "  COUNT(*), "
        "  SUM(CASE WHEN sla_vencido=1 THEN 1 ELSE 0 END), "
        "  AVG(CAST(DATEDIFF(DAY, aberto_em, GETDATE()) AS DECIMAL(6,1))) "
        "FROM dbo.etl_chamado WHERE ativo=1 "
        "GROUP BY ISNULL(atribuido_a_email,'')")
    for ra in cur.fetchall():
        cur.execute(
            "INSERT INTO dbo.etl_indicador_snapshot_analista "
            "  (id_snapshot, atribuido_a, atribuido_a_email, "
            "   total_ativos, sla_vencidos, idade_media_dias) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (snap_id, ra[0], ra[1], ra[2], ra[3] or 0, ra[4]))

    # ── por grupo ────────────────────────────────────────────────────────────
    cur.execute(
        # Mesma armadilha do bloco por analista, um degrau mais discreta: o
        # SELECT já normaliza com ISNULL, mas o GROUP BY era pela coluna CRUA.
        # Um `grupo` NULL e outro '' são dois grupos para o GROUP BY e o MESMO
        # valor depois do ISNULL — duas linhas com a chave (id_snapshot, '').
        # A PK é (id_snapshot, grupo): o INSERT seguinte violaria.
        "SELECT ISNULL(grupo,''), COUNT(*), "
        "  SUM(CASE WHEN sla_vencido=1 THEN 1 ELSE 0 END), "
        "  AVG(CAST(DATEDIFF(DAY, aberto_em, GETDATE()) AS DECIMAL(6,1))) "
        "FROM dbo.etl_chamado WHERE ativo=1 "
        "GROUP BY ISNULL(grupo,'')")
    for rg in cur.fetchall():
        cur.execute(
            "INSERT INTO dbo.etl_indicador_snapshot_grupo "
            "  (id_snapshot, grupo, total_ativos, sla_vencidos, idade_media_dias) "
            "VALUES (%s,%s,%s,%s,%s)",
            (snap_id, rg[0], rg[1], rg[2] or 0, rg[3]))

    conn.commit()
    return snap_id
