"""api/routers/malhas.py — CRUD da entidade Malha (F7, spec §4b de dependências).

Malha = agrupadora de pipelines: o análogo da sequence mestre do DataStage e da
malha/SMART Folder do Control-M. NÃO é um executor — quem roda continua sendo o
modelo da spec (ODATE + push + guardiã), e as dependências continuam GLOBAIS em
etl_pipeline_dependencia (migration 067). A malha agrupa e exibe; o diagrama de
montagem é a F8.

Endpoints:
  GET    /malhas                                   — lista com agregados por malha
  POST   /malhas                                   — cria malha
  GET    /malhas/{malha_name}                      — detalhe + membros + arestas (F8) + nós (F10)
  GET    /malhas/{malha_name}/execucao             — status + eventos por data (F9)
  PATCH  /malhas/{malha_name}                      — descricao / ativo / renomear / orientacao
  POST   /malhas/{malha_name}/pipelines            — adiciona membro (idempotente)
  DELETE /malhas/{malha_name}/pipelines/{pipeline_name} — remove membro
  PUT    /malhas/{malha_name}/layout               — persiste posições dos nós (F8/F10)
  POST   /malhas/{malha_name}/nos                  — cria nó especial do desenho (F10)
  PATCH  /malhas/{malha_name}/nos/{no_id}          — config/layout do nó (F10)
  DELETE /malhas/{malha_name}/nos/{no_id}          — exclui nó + as arestas dele (F10)
  POST   /malhas/{malha_name}/arestas              — aresta de nó, gramática §2.1 (F10)
  DELETE /malhas/{malha_name}/arestas/{aresta_id}  — remove aresta de nó (F10)
  POST   /dependencias                             — cria dependência REAL (F8)
  DELETE /dependencias                             — remove dependência REAL (F8)

F8: desenhar uma aresta no MalhaEditor É cadastrar a dependência GLOBAL em
etl_pipeline_dependencia (migration 067) — a mesma tabela da F1, com as MESMAS
validações (existência + ciclo BFS, importadas de routers.pipelines, nunca
reimplementadas). A aresta não tem escopo por malha: se dois pipelines aparecem
em duas malhas, a dependência aparece nas duas, porque é real nas duas.

F10 (docs/malha-componentes-desenho.md): nós especiais do desenho — Início,
Aguarde, Notificação e Fim (etl_malha_no/etl_malha_aresta, migration 075).
NESTA fase os nós são SÓ desenho: nenhuma linha da 067 nasce deles — a
compilação do Aguarde é a F11, o agendamento do Início é a F13 e os
observadores (guardiã) são a F14. A gramática das arestas de nó (§2.1) e os
avisos de desenho (§2.2) valem desde já; a aresta pipeline→pipeline continua
sendo o F8 acima (o CHECK CK_malha_ar_tem_no da 075 declara isso no modelo).

Degradação em deploy parcial (API nova + migration 070 ainda não aplicada):
cada endpoint checa UMA vez se as tabelas existem; leitura da lista degrada
para vazio com log, e escrita devolve 503 com instrução clara em pt-BR —
nunca um 500 cru com stack trace na tela. Mesma regra para a migration 067
nos endpoints de dependência: leitura degrada ("arestas": []), escrita dá 503.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import PERM_EDITAR, get_current_user, require_perm
# Port do ODATE para a árvore da API (o canônico é dags/utils/data_referencia.py;
# paridade garantida por teste — ver o docstring do módulo).
from services import data_referencia as dref
# Port da expansão dos nós de malha (F10 — canônico em dags/utils/malha_nos.py;
# paridade por teste). O upstream por nó que o GET devolve sai DAQUI: o front
# nunca reimplementa a expansão (uma autoridade só, a regra do ciclo da F8).
from services import malha_nos as malha_nos_svc
# Port do predicado de liberação (F5/D29 — canônico em dags/utils/dependencias.py;
# paridade por teste). virada_global/tabela_067 moraram aqui inline até a F5 e
# foram extraídos para o service, reusados também por routers/pipelines.
from services import dependencias as deps_svc
# Helpers da F1 — fonte ÚNICA das validações de dependência (não reimplementar:
# a mensagem de ciclo do servidor é ESPELHADA no cliente pelo MalhaEditor, e
# duas implementações divergiriam). Sem ciclo de import: pipelines.py não
# importa malhas — mesmo padrão de admin.py/copias.py importando de routers.X.
from routers.pipelines import _check_circular, _validar_existencia, deduplicar

log = logging.getLogger("orquestra-api")

router = APIRouter()

_MSG_SEM_MIGRATION = (
    "Recurso de malhas indisponível: a migration 070 (etl_malha/"
    "etl_malha_pipeline) ainda não foi aplicada neste banco."
)

_MSG_SEM_067 = (
    "Cadastro de dependências indisponível: a migration 067 "
    "(etl_pipeline_dependencia) ainda não foi aplicada neste banco."
)

_MSG_SEM_075 = (
    "Componentes de malha indisponíveis: a migration 075 "
    "(etl_malha_no/etl_malha_aresta) ainda não foi aplicada neste banco."
)

# Domínio dos nós especiais (F10). A coluna tipo não tem CHECK (padrão da
# casa): a API valida na escrita; a unicidade de Início/Fim tem o índice
# filtrado da 075 por baixo (o 2º chega a 422 aqui ANTES de estourar lá).
_TIPOS_NO = ("inicio", "aguarde", "notificacao", "fim")
_ROTULO_NO = {"inicio": "Início", "aguarde": "Aguarde",
              "notificacao": "Notificação", "fim": "Fim",
              "pipeline": "pipeline"}

# Domínio da orientação do diagrama de montagem (migration 074). A coluna não
# tem CHECK (padrão da casa): a API é quem valida na escrita e normaliza na
# leitura — valor estranho no banco vira 'horizontal', nunca tela quebrada.
_ORIENTACOES = ("horizontal", "vertical")

# Ordem de severidade da criticidade (mesmo domínio do CritBadge da tela Malha;
# comparação em caixa alta porque o valor em etl_pipeline é texto livre).
_CRIT_ORDEM = {"CRITICA": 3, "ALTA": 2, "MEDIA": 1, "BAIXA": 0}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _fechar_silencioso(conn):
    """Desfaz a transação e fecha, sem mascarar o erro original."""
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def _tabelas_070(cur) -> bool:
    """True se as tabelas da migration 070 existem. Checagem ÚNICA por request:
    é o que permite degradar num deploy parcial (API nova + banco antigo) em vez
    de estourar 'Invalid object name' na primeira query."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_malha', 'U'), OBJECT_ID('dbo.etl_malha_pipeline', 'U')"
        )
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das tabelas da migration 070 falhou: %s", e)
        return False


def _exigir_tabelas(cur, conn):
    """Escritas e detalhe não têm degradação útil: sem as tabelas, o erro tem
    de ser claro (503 + instrução), não um 500 cru de 'Invalid object name'."""
    if not _tabelas_070(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_MIGRATION)


def _tabela_067(cur) -> bool:
    """True se etl_pipeline_dependencia (migration 067) existe. Implementação
    extraída para services.dependencias na F5 (reuso pelos dois routers) — o
    alias local preserva os call sites."""
    return deps_svc.tabela_067(cur)


def _exigir_tabela_067(cur, conn):
    if not _tabela_067(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_067)


def _coluna_074(cur) -> bool:
    """True se etl_malha.orientacao (migration 074) existe. Guard de COLUNA no
    padrão de _has_card_cols (routers/mensagens.py): COL_LENGTH, best-effort —
    qualquer falha conta como ausente e a API degrada para o default."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_malha', 'orientacao')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem da coluna da migration 074 falhou: %s", e)
        return False


def _orientacao_norm(valor) -> str:
    """Normaliza o valor lido do banco para o domínio da API: fora de
    'horizontal'|'vertical' (coluna sem CHECK) devolve o default."""
    v = (str(valor).strip().lower() if valor else "")
    return v if v in _ORIENTACOES else "horizontal"


# ── helpers dos nós especiais (F10 — migration 075) ──────────────────────────

def _tabelas_075(cur) -> bool:
    """True se as tabelas da migration 075 existem. Mesma regra das outras
    checagens (070/067): uma consulta por request, para o deploy parcial
    degradar (leitura com flag, escrita 503) em vez de estourar
    'Invalid object name' — princípio 6 do desenho de componentes."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_malha_no', 'U'), "
            "OBJECT_ID('dbo.etl_malha_aresta', 'U')"
        )
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das tabelas da migration 075 falhou: %s", e)
        return False


def _exigir_tabelas_075(cur, conn):
    """Escrita de nó/aresta sem a 075 não tem degradação útil: 503 com
    instrução clara, nunca 500 cru — padrão literal das guardas 070/067."""
    if not _tabelas_075(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_075)


def _coluna_origem_no(cur) -> bool:
    """True se etl_pipeline_dependencia.origem_no (assinatura da 075) existe.
    Guard de COLUNA no padrão de _coluna_074: COL_LENGTH, best-effort —
    qualquer falha conta como ausente e o GET usa o SQL de sempre."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline_dependencia', 'origem_no')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem da coluna origem_no da migration 075 falhou: %s", e)
        return False


def _nos_da_malha(cur, malha) -> list:
    """Nós do desenho da malha, ordenados por id (determinístico)."""
    cur.execute(
        "SELECT id, tipo, config_json, layout_x, layout_y "
        "FROM dbo.etl_malha_no WHERE malha_name = ? ORDER BY id",
        (malha,))
    return [{"id": int(r[0]), "tipo": (r[1] or "").strip().lower(),
             "config_json": r[2], "layout_x": r[3], "layout_y": r[4]}
            for r in cur.fetchall()]


def _arestas_da_malha(cur, malha) -> list:
    """Arestas de nó do desenho da malha, ordenadas por id."""
    cur.execute(
        "SELECT id, origem_no, origem_pipeline, destino_no, destino_pipeline "
        "FROM dbo.etl_malha_aresta WHERE malha_name = ? ORDER BY id",
        (malha,))
    return [{"id": int(r[0]),
             "origem_no": int(r[1]) if r[1] is not None else None,
             "origem_pipeline": r[2],
             "destino_no": int(r[3]) if r[3] is not None else None,
             "destino_pipeline": r[4]}
            for r in cur.fetchall()]


def _no_config(raw):
    """config_json do nó → objeto para o front. A API só grava JSON válido;
    valor quebrado por SQL direto degrada para None com log — nunca tela
    quebrada (mesmo espírito do _orientacao_norm)."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except Exception:
        log.warning("[MALHA] config_json ilegível em etl_malha_no — degradado para None")
        return None


def _erro_gramatica(origem_tipo, destino_tipo):
    """Gramática do desenho — célula a célula da tabela §2.1: devolve a
    mensagem do 422 para célula proibida, ou None para aresta permitida.

    Permitidas: inicio→pipeline · pipeline→aguarde · aguarde→pipeline ·
    aguarde→aguarde · pipeline/aguarde→notificacao · pipeline/aguarde→fim.
    pipeline→pipeline é recusada AQUI com a instrução da porta certa (F8):
    aresta direta é dependência REAL na 067, nunca desenho de nó (Decisão 2)."""
    if origem_tipo in ("notificacao", "fim"):
        return (f"Aresta inválida: {_ROTULO_NO[origem_tipo]} não tem saída — "
                "Notificação e Fim são observadores terminais do desenho "
                "(se tivessem saída, precisariam de um primitivo de runtime "
                "que não existe).")
    if destino_tipo == "inicio":
        return ("Aresta inválida: nada liga NO Início — ele é o ponto de "
                "partida do desenho, não um destino.")
    if origem_tipo == "inicio" and destino_tipo != "pipeline":
        return (f"Aresta inválida: Início → {_ROTULO_NO[destino_tipo]}. "
                "O Início só liga em pipeline — ele planta o agendamento da "
                "malha nas raízes, nada mais.")
    if origem_tipo == "pipeline" and destino_tipo == "pipeline":
        return ("Aresta pipeline → pipeline não entra no desenho de nós: use "
                "a aresta direta do diagrama (F8) — ela grava a dependência "
                "REAL na tabela global de dependências.")
    return None


def _avisos_desenho(nos, arestas) -> list:
    """Avisos de desenho do §2.2 — os ESTRUTURAIS desta fase (F10).

    A lição do nó Aguarde das Etapas (§5.5): ponta solta avisada no momento de
    consequência — cada gesto devolve a lista (toast) e o GET a repete (o
    banner persistente do editor, F12). Aviso NUNCA bloqueia: onde a tabela
    §2.2 diz aviso, o gesto é aceito e o efeito (ou a ausência dele) é DITO.
    Formato: {"no", "nivel" ('forte'|'leve'), "mensagem"}."""
    entradas: dict = {}
    saidas: dict = {}
    for a in arestas:
        if a["destino_no"] is not None:
            entradas[a["destino_no"]] = entradas.get(a["destino_no"], 0) + 1
        if a["origem_no"] is not None:
            saidas[a["origem_no"]] = saidas.get(a["origem_no"], 0) + 1
    avisos = []
    for no in nos:                       # ordenados por id → determinístico
        i, t = no["id"], no["tipo"]
        e, s = entradas.get(i, 0), saidas.get(i, 0)
        if t == "aguarde":
            if s > 0 and e == 0:
                avisos.append({"no": i, "nivel": "forte", "mensagem":
                               "Aguarde sem entradas: nenhuma dependência "
                               "será criada — ligue as entradas"})
            elif e == 1:
                avisos.append({"no": i, "nivel": "leve", "mensagem":
                               "Aguarde com uma única entrada — junção de uma "
                               "perna só (provável esquecimento)"})
            if s == 0:
                avisos.append({"no": i, "nivel": "leve", "mensagem":
                               "Aguarde sem saída — vale como marco visual; "
                               "nenhuma dependência nasce dele"})
        elif t in ("notificacao", "fim") and e == 0:
            avisos.append({"no": i, "nivel": "forte", "mensagem":
                           f"{_ROTULO_NO[t]} sem entrada — a guardiã não "
                           "avalia este nó (nada será emitido)"})
        elif t == "inicio" and s == 0:
            avisos.append({"no": i, "nivel": "forte", "mensagem":
                           "Início sem saída — o agendamento da malha não "
                           "alcançará nenhum pipeline"})
    return avisos


def _chave_ponta(no, pipe):
    """Identidade de uma ponta no grafo do desenho: nó por id, pipeline por
    casefold (colação CI do banco)."""
    return ("no", no) if no is not None else ("pipe", (pipe or "").casefold())


def _criaria_ciclo_desenho(arestas, chave_origem, chave_destino) -> bool:
    """True se origem→destino fecharia ciclo no grafo do DESENHO da malha
    (nós e pipelines ligados por arestas de nó): BFS para FRENTE a partir do
    destino — se alcançar a origem, a aresta proposta fecha o ciclo.

    FRONTEIRA F10/F11 (desenho §3.3, registrada de propósito): nesta fase o
    ciclo validado é o TOPOLÓGICO do desenho. O ciclo do conjunto
    PÓS-EXPANSÃO contra a 067 (Decisão 15 — um aguarde inocente pode fechar
    A→…→A por linhas que o gesto cria aos pares, validado com o BFS da F1 e a
    mensagem canônica compartilhada) chega com o compilador, na F11."""
    if chave_origem == chave_destino:
        return True
    adj: dict = {}
    for a in arestas:
        o = _chave_ponta(a["origem_no"], a["origem_pipeline"])
        d = _chave_ponta(a["destino_no"], a["destino_pipeline"])
        adj.setdefault(o, []).append(d)
    vistos, fila = set(), [chave_destino]
    while fila:
        atual = fila.pop(0)
        if atual == chave_origem:
            return True
        if atual in vistos:
            continue
        vistos.add(atual)
        fila.extend(adj.get(atual, ()))
    return False


def _resolver_ponta(cur, conn, malha, ponta, lado):
    """Resolve uma ponta {"no": id} | {"pipeline": nome} da aresta (§9).

    Nó: precisa existir NESTA malha (nó de outra malha é desenho de outra
    malha — 422 claro). Pipeline: canonizado pela grafia registrada (PR #236)
    e precisa ser MEMBRO da malha — aresta para não-membro deixaria o desenho
    apontando para fora do conjunto (o outro lado desse invariante, recusar
    remover membro ligado a nó, chega na F11 com o §7.3).
    Devolve {"no": id|None, "pipeline": nome|None, "tipo": tipo}."""
    if not isinstance(ponta, dict) or (("no" in ponta) == ("pipeline" in ponta)):
        _fechar_silencioso(conn)
        raise HTTPException(
            status_code=422,
            detail=f"{lado} deve ter exatamente uma das chaves: 'no' ou 'pipeline'")
    if "no" in ponta:
        no_id = ponta.get("no")
        if not isinstance(no_id, int) or isinstance(no_id, bool):
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail=f"{lado}.no deve ser o id numérico do nó")
        cur.execute("SELECT id, tipo FROM dbo.etl_malha_no "
                    "WHERE id = ? AND malha_name = ?", (no_id, malha))
        row = cur.fetchone()
        if row is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        return {"no": int(row[0]), "pipeline": None,
                "tipo": (row[1] or "").strip().lower()}
    nome = (str(ponta.get("pipeline") or "")).strip()
    if not nome:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=422, detail=f"{lado}.pipeline é obrigatório")
    oficial = _pipeline_oficial(cur, nome)
    if oficial is None:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=422, detail=f"Pipeline inexistente: '{nome}'")
    cur.execute("SELECT 1 FROM dbo.etl_malha_pipeline "
                "WHERE malha_name = ? AND pipeline_name = ?", (malha, oficial))
    if not cur.fetchone():
        _fechar_silencioso(conn)
        raise HTTPException(
            status_code=422,
            detail=f"'{oficial}' não é membro da malha '{malha}' — adicione-o "
                   "à malha antes de ligá-lo a um componente")
    return {"no": None, "pipeline": oficial, "tipo": "pipeline"}


def _rotulo_ponta(p) -> str:
    """Rótulo de uma ponta para mensagem de erro: pipeline pelo nome, nó pelo
    tipo + id — o texto do ciclo é ESPELHADO no cliente (regra F8)."""
    if p["pipeline"] is not None:
        return f"'{p['pipeline']}'"
    return f"{_ROTULO_NO.get(p['tipo'], 'nó')} #{p['no']}"


def _tabelas_067_execucao(cur) -> bool:
    """True se etl_pipeline_execucao E etl_dependencia_evento (migration 067)
    existem. Mesma regra das outras checagens: uma consulta por request, para a
    visão de execução (F9) degradar num deploy parcial em vez de estourar
    'Invalid object name' — a malha continua abrindo, sem status."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_pipeline_execucao', 'U'), "
            "OBJECT_ID('dbo.etl_dependencia_evento', 'U')"
        )
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das tabelas de execução da migration 067 falhou: %s", e)
        return False


def _virada_global(cur):
    """Valor CRU de etl_app_config['dependencia_hora_virada'] — implementação
    extraída para services.dependencias na F5 (reuso pelos dois routers); o
    parse tolerante segue em services.data_referencia."""
    return deps_svc.virada_global(cur)


def _ligar_dag_config_pendente(cur, pipeline_name) -> bool:
    """Liga a pendência de publicação (migration 073) do DEPENDENTE, na MESMA
    transação da escrita da dependência (Decisão 6/D30): mudar dependência
    troca o `schedule` da DAG do filho — o pai NÃO precisa regerar (F3 §2.2:
    ele lê a tabela ao vivo). Grava o CARIMBO GETDATE() em vez de um bit
    (achado 2 da revisão — TOCTOU): o reconciliador só limpa carimbos <=
    início da publicação concluída, então uma edição feita DURANTE uma
    publicação em voo sobrevive ao clear. `WHERE dag_criada = 1`: pipeline
    nunca publicado não tem versão velha rodando. Sem a coluna (073 pendente),
    degrada em silêncio — comportamento = hoje. Devolve True se a flag foi
    ligada (a resposta ao front segue sendo o booleano)."""
    try:
        cur.execute(
            "UPDATE dbo.etl_pipeline SET dag_config_pendente_em = GETDATE() "
            "WHERE pipeline_name = ? AND dag_criada = 1",
            (pipeline_name,))
        return (cur.rowcount or 0) > 0
    except Exception as e:
        log.debug("[MALHA] dag_config_pendente_em indisponível (migration 073?): %s", e)
        return False


def _agora() -> datetime:
    """Relógio do servidor, isolado para os testes congelarem o tempo."""
    return datetime.now()


def _malha_oficial(cur, malha_name):
    """Grafia registrada da malha (a colação CI casa qualquer caixa; o retorno
    é a oficial) ou None se não existe."""
    cur.execute("SELECT malha_name FROM dbo.etl_malha WHERE malha_name = ?",
                (malha_name,))
    row = cur.fetchone()
    return (row[0] or "").strip() if row else None


def _pipeline_oficial(cur, pipeline_name):
    """Grafia registrada do pipeline em etl_pipeline, ou None se não existe.

    Mesma regra da PR #236 (incidente 2026-08-01): membro gravado em grafia
    divergente do registro some nos dicts case-sensitive do Python — aqui o
    nome é canonizado ANTES de qualquer gravação."""
    cur.execute("SELECT pipeline_name FROM dbo.etl_pipeline WHERE pipeline_name = ?",
                (pipeline_name,))
    row = cur.fetchone()
    return (row[0] or "").strip() if row else None


def _espelho_csv(cur, pipeline, depende_de, acao):
    """Sincroniza o CSV etl_pipeline.depends_on do DEPENDENTE com a tabela 067,
    na MESMA transação da escrita (regra da F6 da spec: o CSV é o fallback do
    etl_dag_factory e do preview até a retomada — divergir aqui recriaria o
    defeito que a F1 fechou, a tela contando uma história e a DAG outra).

    acao: 'add' acrescenta se ausente; 'remove' tira se presente — sempre por
    comparação case-insensitive (a colação do banco é CI) e sem duplicar
    (deduplicar da F1). Devolve True se o CSV mudou."""
    cur.execute("SELECT depends_on FROM dbo.etl_pipeline WHERE pipeline_name = ?",
                (pipeline,))
    row = cur.fetchone()
    raw = str(row[0]).strip() if row and row[0] else ""
    lista = deduplicar(d for d in raw.split(",") if d.strip())
    chave = (depende_de or "").casefold()
    if acao == "add":
        if any(d.casefold() == chave for d in lista):
            return False
        lista.append(depende_de)
    else:
        nova = [d for d in lista if d.casefold() != chave]
        if len(nova) == len(lista):
            return False
        lista = nova
    cur.execute(
        "UPDATE dbo.etl_pipeline SET depends_on = ?, updated_at = GETDATE() "
        "WHERE pipeline_name = ?", (",".join(lista) or None, pipeline))
    return True


def criticidade_agregada(criticidades):
    """A criticidade da malha é a MAIS ALTA entre os membros
    (Critica > Alta > Media > Baixa) — regra do cartão da tela.

    Valor fora do domínio conta como Media (o mesmo default do ISNULL do
    GET /malha) para um texto livre inesperado não derrubar a listagem.
    Malha sem membros devolve None: não se inventa criticidade do nada."""
    melhor = None          # valor como está gravado (a tela upper-casa)
    melhor_rank = -1
    for crit in criticidades:
        c = (str(crit).strip() if crit else "") or "Media"
        rank = _CRIT_ORDEM.get(c.upper(), _CRIT_ORDEM["MEDIA"])
        if rank > melhor_rank:
            melhor, melhor_rank = c, rank
    return melhor


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/malhas", tags=["malhas"])
def list_malhas(_auth: dict = Depends(get_current_user)):
    """Lista malhas com agregados por malha: qtd de pipelines, qtd de ativos e
    a criticidade mais alta entre os membros. Ordenada por nome."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if not _tabelas_070(cur):
            cur.close(); conn.close()
            log.warning("[MALHA] tabelas da migration 070 ausentes — lista degradada para vazio")
            # migration_pendente é CONTRATO com o front: é ela que liga o banner
            # de deploy parcial e desabilita o "Nova malha" na tela.
            return {"malhas": [], "migration_pendente": True}

        # orientacao (074) é ADITIVA na lista: o card pode ignorar; a coluna
        # ausente degrada para o default sem mudar o SQL de hoje.
        tem_074 = _coluna_074(cur)
        cur.execute(
            "SELECT malha_name, descricao, CAST(ativo AS INT) AS ativo, "
            "criado_em, criado_por, atualizado_em"
            + (", orientacao" if tem_074 else "") +
            " FROM dbo.etl_malha ORDER BY malha_name"
        )
        data = []
        indice: dict[str, dict] = {}
        for r in cur.fetchall():
            rec = {
                "malha_name": r[0], "descricao": r[1], "ativo": int(r[2] or 0),
                "criado_em": _fmt_dt(r[3]), "criado_por": r[4],
                "atualizado_em": _fmt_dt(r[5]),
                "orientacao": _orientacao_norm(r[6]) if tem_074 else "horizontal",
                "qtd_pipelines": 0, "qtd_ativos": 0, "criticidade": None,
            }
            data.append(rec)
            indice[rec["malha_name"]] = rec

        # Membros num SELECT só (agregação em Python): evita N+1 e mantém a
        # regra da criticidade num único lugar testável.
        cur.execute(
            "SELECT mp.malha_name, CAST(p.active AS INT) AS active, "
            "ISNULL(p.criticidade, 'Media') AS criticidade "
            "FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name"
        )
        crits: dict[str, list] = {}
        for malha, active, crit in cur.fetchall():
            rec = indice.get(malha)
            if rec is None:
                continue
            rec["qtd_pipelines"] += 1
            rec["qtd_ativos"] += int(active or 0)
            crits.setdefault(malha, []).append(crit)
        for malha, lista in crits.items():
            indice[malha]["criticidade"] = criticidade_agregada(lista)

        cur.close(); conn.close()
        return {"malhas": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas", tags=["malhas"])
def create_malha(body: dict = Body(default={}),
                 _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria uma malha. 422 para nome vazio ou duplicado (a colação do banco é
    case-insensitive — 'Fechamento' e 'FECHAMENTO' são a mesma malha)."""
    nome = (body.get("malha_name") or "").strip()
    descricao = (body.get("descricao") or "").strip() or None
    if not nome:
        raise HTTPException(status_code=422, detail="malha_name é obrigatório")
    if len(nome) > 200:
        raise HTTPException(status_code=422, detail="malha_name excede 200 caracteres")
    # '/' e '\' no nome tornariam a malha inendereçável nos endpoints de path
    # (o ASGI decodifica %2F antes do match de rota e o 404 vem do roteador).
    if "/" in nome or "\\" in nome:
        raise HTTPException(status_code=422,
                            detail="malha_name não pode conter '/' nem '\\'")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        existente = _malha_oficial(cur, nome)
        if existente is not None:
            cur.close(); conn.close()
            raise HTTPException(status_code=422,
                                detail=f"Já existe uma malha com este nome: '{existente}'")
        criado_por = None
        if isinstance(_auth, dict):
            criado_por = (str(_auth.get("matricula") or "").strip() or None)
        cur.execute(
            "INSERT INTO dbo.etl_malha (malha_name, descricao, criado_por) VALUES (?, ?, ?)",
            (nome, descricao, (criado_por or "")[:100] or None),
        )
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "malha_name": nome}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.get("/malhas/{malha_name}", tags=["malhas"])
def get_malha_detalhe(malha_name: str, _auth: dict = Depends(get_current_user)):
    """Detalhe da malha + membros (nome, ativo, criticidade, agendamento e a
    posição salva do nó no diagrama da F8)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        # orientacao (074): preferência de visão que viaja com o layout — sem a
        # coluna, degrada para 'horizontal' (o comportamento de sempre).
        tem_074 = _coluna_074(cur)
        cur.execute(
            "SELECT malha_name, descricao, CAST(ativo AS INT) AS ativo, "
            "criado_em, criado_por, atualizado_em"
            + (", orientacao" if tem_074 else "") +
            " FROM dbo.etl_malha WHERE malha_name = ?",
            (malha_name,),
        )
        row = cur.fetchone()
        if row is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        malha = {
            "malha_name": row[0], "descricao": row[1], "ativo": int(row[2] or 0),
            "criado_em": _fmt_dt(row[3]), "criado_por": row[4],
            "atualizado_em": _fmt_dt(row[5]),
            "orientacao": _orientacao_norm(row[6]) if tem_074 else "horizontal",
        }
        # JOIN em etl_pipeline: além dos metadados, garante que membro de
        # pipeline excluído simplesmente some (aceite da F7) — e a FK CASCADE
        # da 070 já removeu a linha de qualquer forma.
        cur.execute(
            "SELECT p.pipeline_name, CAST(p.active AS INT) AS active, "
            "ISNULL(p.criticidade, 'Media') AS criticidade, p.schedule_type, "
            "mp.layout_x, mp.layout_y "
            "FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
            "WHERE mp.malha_name = ? ORDER BY p.pipeline_name",
            (malha["malha_name"],),
        )
        membros = [
            {
                "pipeline_name": r[0], "active": int(r[1] or 0),
                "criticidade": r[2], "schedule_type": r[3],
                "layout_x": r[4], "layout_y": r[5],
            }
            for r in cur.fetchall()
        ]
        # Arestas (F8): dependências GLOBAIS da 067 em que AMBAS as pontas são
        # membros desta malha — a mesma dependência aparece em toda malha que
        # contenha os dois pipelines (aceite da F8: a aresta é real nas duas).
        # Filtro em Python sobre um SELECT só, como nos agregados da listagem.
        # Deploy parcial (067 pendente): a malha ainda abre, com "arestas": [] —
        # migration_067_pendente é o sinal para o front avisar e travar a edição.
        # F10: as tabelas da 075 habilitam os nós do desenho e a anotação
        # compilada_por das arestas diretas — checadas UMA vez por request.
        tem_075 = _tabelas_075(cur)
        arestas = []
        if _tabela_067(cur):
            # Mapa casefold → grafia OFICIAL (a dos nós do diagrama). Linhas
            # legadas da 067 podem carregar grafia divergente (o register da F1
            # gravava como digitado e a 069 não normalizou esta tabela — a 071
            # normaliza); sem canonizar aqui, o React Flow descarta a aresta em
            # silêncio (id não casa com nó) e ela some do desenho.
            membro_oficial = {m["pipeline_name"].casefold(): m["pipeline_name"]
                              for m in membros}
            if tem_075 and _coluna_origem_no(cur):
                # Com a assinatura da 075 (§7.4 do desenho de componentes):
                # linha assinada por nó DESTA malha não vira aresta direta (ela
                # é o desenho do nó); assinada por nó de OUTRA malha vira
                # aresta anotada compilada_por — o editor a desenha com
                # cadeado, somente-leitura (F12). Na F10 nada assina linhas
                # (a compilação é a F11): o contrato de leitura nasce pronto.
                cur.execute(
                    "SELECT d.pipeline_name, d.depende_de, d.origem_no, n.malha_name "
                    "FROM dbo.etl_pipeline_dependencia d "
                    "LEFT JOIN dbo.etl_malha_no n ON n.id = d.origem_no "
                    "WHERE d.tipo = 'PIPELINE'")
                linhas_067 = [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]
            else:
                cur.execute(
                    "SELECT pipeline_name, depende_de FROM dbo.etl_pipeline_dependencia "
                    "WHERE tipo = 'PIPELINE'")
                linhas_067 = [(r[0], r[1], None, None) for r in cur.fetchall()]
            for dep_pipe, dep_de, origem_no, malha_do_no in linhas_067:
                a = membro_oficial.get(str(dep_pipe or "").strip().casefold())
                b = membro_oficial.get(str(dep_de or "").strip().casefold())
                if not (a and b):
                    continue
                if origem_no is not None and malha_do_no is not None and \
                        str(malha_do_no).strip().casefold() == \
                        malha["malha_name"].casefold():
                    continue    # desenho do nó desta malha, não aresta direta
                item = {"pipeline_name": a, "depende_de": b}
                if origem_no is not None:
                    item["compilada_por"] = {"malha": malha_do_no,
                                             "no": int(origem_no)}
                arestas.append(item)
            arestas.sort(key=lambda x: (x["pipeline_name"], x["depende_de"]))
        else:
            log.warning("[MALHA] migration 067 ausente — malha '%s' aberta sem arestas",
                        malha["malha_name"])
            malha["migration_067_pendente"] = True

        # Nós do desenho (F10) — com o upstream calculado pelo SERVIDOR (port
        # da expansão com paridade): o front nunca expande. Sem a 075, o resto
        # da malha segue intacto e a flag liga o aviso de deploy parcial.
        nos_payload, arestas_no_payload, avisos = [], [], []
        if tem_075:
            nos_l = _nos_da_malha(cur, malha["malha_name"])
            arestas_l = _arestas_da_malha(cur, malha["malha_name"])
            expansao = malha_nos_svc.expandir(nos_l, arestas_l)
            nos_payload = [{
                "id": n["id"], "tipo": n["tipo"],
                "config": _no_config(n["config_json"]),
                "layout_x": n["layout_x"], "layout_y": n["layout_y"],
                "upstream": sorted(expansao["nos"][n["id"]]["upstream"]),
            } for n in nos_l]
            arestas_no_payload = arestas_l
            avisos = _avisos_desenho(nos_l, arestas_l)
        else:
            log.warning("[MALHA] migration 075 ausente — malha '%s' aberta sem nós",
                        malha["malha_name"])
            malha["migration_075_pendente"] = True
        cur.close(); conn.close()
        malha["membros"] = membros
        malha["arestas"] = arestas
        malha["nos"] = nos_payload
        malha["arestas_no"] = arestas_no_payload
        malha["avisos"] = avisos
        malha["qtd_pipelines"] = len(membros)
        malha["qtd_ativos"] = sum(m["active"] for m in membros)
        malha["criticidade"] = criticidade_agregada(m["criticidade"] for m in membros)
        return malha
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.get("/malhas/{malha_name}/execucao", tags=["malhas"])
def get_malha_execucao(malha_name: str, data_referencia: str | None = None,
                       _auth: dict = Depends(get_current_user)):
    """Visão de execução da malha numa data de referência (F9, spec §4b).

    Devolve, APENAS para pipelines MEMBROS da malha, a execução MAIS RECENTE de
    cada um na data (regra do §6 risco 6: pipeline com horários específicos
    roda N vezes ao dia — vale a última) e os eventos da guardiã
    (etl_dependencia_evento) da mesma data, do mais novo para o mais antigo.

    Sem `data_referencia` na query, usa o ODATE corrente calculado com a hora
    de virada GLOBAL de etl_app_config — mesma semântica de
    dags/utils/data_referencia.py (port com teste de paridade).

    Produção PRÉ-retomada (F2–F4): as tabelas da 067 existem mas NADA as
    alimenta — a resposta é o estado vazio HONESTO (arrays vazios), nunca tela
    quebrada nem promessa falsa. Deploy parcial SEM a 067: arrays vazios +
    migration_067_pendente, e a malha continua abrindo.
    """
    # Valida a data ANTES de abrir conexão: 422 de formato não gasta banco.
    data_ref = None
    if data_referencia is not None and str(data_referencia).strip() != "":
        try:
            data_ref = datetime.strptime(str(data_referencia).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"data_referencia inválida: '{data_referencia}' "
                       "(use o formato YYYY-MM-DD)")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        if data_ref is None:
            # ODATE corrente: virada GLOBAL (a mesma chave que dags/ lê) sobre o
            # relógio do servidor. Config ausente/ruim degrada para 00:00.
            data_ref = dref.calcular(_agora(), _virada_global(cur))

        # Membros da malha (JOIN garante que pipeline excluído some, como no
        # detalhe) — mapa casefold → grafia OFICIAL, a mesma canonização das
        # arestas da F8: linha de execução legada com caixa divergente não pode
        # sumir do colorido dos nós por causa de dict case-sensitive.
        cur.execute(
            "SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
            "WHERE mp.malha_name = ?",
            (malha,))
        membro_oficial = {str(r[0]).strip().casefold(): str(r[0]).strip()
                          for r in cur.fetchall()}

        resposta = {
            "data_referencia": data_ref.strftime("%Y-%m-%d"),
            "execucoes": [],
            "eventos": [],
        }
        if not _tabelas_067_execucao(cur):
            log.warning("[MALHA] migration 067 ausente — visão de execução da "
                        "malha '%s' degradada para vazio", malha)
            resposta["migration_067_pendente"] = True
            cur.close(); conn.close()
            return resposta

        # Execuções do dia num SELECT só (filtro de membros em Python, como nos
        # agregados da listagem); por pipeline vence a MAIS RECENTE — regra F9
        # extraída para services.dependencias.mais_recente_da_data na F5:
        # maior inicio, desempate por execution_id (linha AGUARDANDO ainda sem
        # start perde de qualquer linha iniciada). Status vai CRU — a legenda
        # da tela fala o mesmo domínio da tabela (AGUARDANDO_DEPENDENCIA |
        # EXECUTANDO | SUCESSO | FALHA | PULADO | NAO_LIBEROU).
        cur.execute(
            "SELECT pipeline_name, status, inicio, fim, disparado_por, motivo, "
            "execution_id FROM dbo.etl_pipeline_execucao "
            "WHERE data_referencia = ?",
            (data_ref,))
        linhas_membro: dict[str, list] = {}
        for r in cur.fetchall():
            oficial = membro_oficial.get(str(r[0] or "").strip().casefold())
            if oficial is None:
                continue        # execução de quem não é membro não aparece
            linhas_membro.setdefault(oficial, []).append({
                "status": r[1], "inicio": r[2], "fim": r[3],
                "disparado_por": r[4], "motivo": r[5],
                "execution_id": str(r[6] or "")})
        for oficial in sorted(linhas_membro):
            vencedora = deps_svc.mais_recente_da_data(linhas_membro[oficial])
            item = {
                "pipeline_name": oficial,
                "status": vencedora["status"],
                "inicio": _fmt_dt(vencedora["inicio"]),
                "fim": _fmt_dt(vencedora["fim"]),
                "disparado_por": vencedora["disparado_por"],
                "motivo": vencedora["motivo"],
            }
            # F5 (D32): quem está esperando ganha `faltantes` ADITIVO — de quem
            # a corrida espera, pelo MESMO predicado do motor (o port, nunca um
            # "mais recente" paralelo). Campo novo opcional: front antigo ignora.
            if vencedora["status"] in ("AGUARDANDO_DEPENDENCIA", "NAO_LIBEROU"):
                _, falt = deps_svc.liberado(cur, oficial, data_ref)
                item["faltantes"] = falt
            resposta["execucoes"].append(item)

        # Eventos da guardiã da MESMA data, só de membros, mais novo primeiro.
        cur.execute(
            "SELECT pipeline_name, tipo, detectado_em, detalhe "
            "FROM dbo.etl_dependencia_evento WHERE data_referencia = ?",
            (data_ref,))
        eventos = []
        for r in cur.fetchall():
            oficial = membro_oficial.get(str(r[0] or "").strip().casefold())
            if oficial is None:
                continue
            eventos.append({
                "pipeline_name": oficial,
                "tipo": r[1],
                "criado_em": _fmt_dt(r[2]),
                "mensagem": r[3],
            })
        eventos.sort(key=lambda e: (e["criado_em"] or "", e["pipeline_name"]),
                     reverse=True)
        resposta["eventos"] = eventos

        cur.close(); conn.close()
        return resposta
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.patch("/malhas/{malha_name}", tags=["malhas"])
def update_malha(malha_name: str, body: dict = Body(default={}),
                 _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Atualiza descricao/ativo/orientacao e/ou renomeia a malha.

    Renomear atualiza as DUAS tabelas na MESMA transação: a FK da 070 é
    cascade de DELETE, não de UPDATE — trocar o PK com filhas apontando para
    ele viola a FK em qualquer ordem de UPDATE simples. O caminho é criar a
    linha-mãe nova (preservando criado_em/criado_por), migrar as filhas e
    apagar a antiga (já sem filhas, o CASCADE não leva nada junto).

    orientacao (074): 'horizontal' | 'vertical' — outro valor é 422. Sem a
    coluna (deploy parcial), NÃO é 503: o precedente do arquivo para COLUNA
    opcional é o degrade suave (_ligar_dag_config_pendente / migration 073) —
    log + migration_074_pendente=True na resposta, e a tela avisa. O 503 fica
    reservado às TABELAS (070/067), sem as quais o recurso inteiro não existe.
    """
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        atual = _malha_oficial(cur, malha_name)
        if atual is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")

        tem_descricao = "descricao" in body
        descricao = (str(body.get("descricao") or "").strip() or None) if tem_descricao else None
        tem_ativo = "ativo" in body
        if tem_ativo:
            if body.get("ativo") not in (0, 1, True, False):
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422, detail="ativo deve ser 0 ou 1")
            ativo = int(bool(body.get("ativo")))
        # Valida a orientação ANTES de qualquer escrita (um rename não pode ir
        # pela metade por causa de um valor inválido aqui). Caixa é tolerada na
        # entrada ('Vertical' vale) e o gravado é o canônico minúsculo — mesmo
        # espírito da colação CI do banco.
        tem_orientacao = "orientacao" in body
        if tem_orientacao:
            orientacao = str(body.get("orientacao") or "").strip().lower()
            if orientacao not in _ORIENTACOES:
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail="orientacao deve ser 'horizontal' ou 'vertical'")
        tem_074 = _coluna_074(cur)

        novo_nome = (body.get("novo_nome") or "").strip()
        renomeada = False
        if novo_nome and novo_nome != atual:
            if len(novo_nome) > 200:
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422, detail="novo_nome excede 200 caracteres")
            if "/" in novo_nome or "\\" in novo_nome:
                # mesma regra da criação: nome com '/' fica inendereçável no path
                _fechar_silencioso(conn)
                raise HTTPException(status_code=422,
                                    detail="novo_nome não pode conter '/' nem '\\'")
            if novo_nome.casefold() == atual.casefold():
                # Só mudança de caixa: para a colação CI é o MESMO valor, então
                # o UPDATE direto não viola a FK — o insert/migra/apaga acima
                # estouraria o PK (a linha nova colidiria com a antiga).
                cur.execute(
                    "UPDATE dbo.etl_malha SET malha_name = ?, atualizado_em = SYSDATETIME() "
                    "WHERE malha_name = ?", (novo_nome, atual))
                cur.execute(
                    "UPDATE dbo.etl_malha_pipeline SET malha_name = ? WHERE malha_name = ?",
                    (novo_nome, atual))
            else:
                duplicada = _malha_oficial(cur, novo_nome)
                if duplicada is not None:
                    _fechar_silencioso(conn)
                    raise HTTPException(status_code=422,
                                        detail=f"Já existe uma malha com este nome: '{duplicada}'")
                # Com a 074, a orientação viaja junto no rename — a cópia por
                # lista explícita de colunas deixaria a linha nova cair no
                # DEFAULT 'horizontal' e a preferência salva se perderia.
                if tem_074:
                    cur.execute(
                        "INSERT INTO dbo.etl_malha "
                        "(malha_name, descricao, ativo, criado_em, criado_por, "
                        "atualizado_em, orientacao) "
                        "SELECT ?, descricao, ativo, criado_em, criado_por, "
                        "SYSDATETIME(), orientacao "
                        "FROM dbo.etl_malha WHERE malha_name = ?",
                        (novo_nome, atual))
                else:
                    cur.execute(
                        "INSERT INTO dbo.etl_malha "
                        "(malha_name, descricao, ativo, criado_em, criado_por, atualizado_em) "
                        "SELECT ?, descricao, ativo, criado_em, criado_por, SYSDATETIME() "
                        "FROM dbo.etl_malha WHERE malha_name = ?",
                        (novo_nome, atual))
                cur.execute(
                    "UPDATE dbo.etl_malha_pipeline SET malha_name = ? WHERE malha_name = ?",
                    (novo_nome, atual))
                cur.execute("DELETE FROM dbo.etl_malha WHERE malha_name = ?", (atual,))
            atual = novo_nome
            renomeada = True

        if tem_descricao:
            cur.execute(
                "UPDATE dbo.etl_malha SET descricao = ?, atualizado_em = SYSDATETIME() "
                "WHERE malha_name = ?", (descricao, atual))
        if tem_ativo:
            cur.execute(
                "UPDATE dbo.etl_malha SET ativo = ?, atualizado_em = SYSDATETIME() "
                "WHERE malha_name = ?", (ativo, atual))
        migration_074_pendente = False
        if tem_orientacao:
            if tem_074:
                cur.execute(
                    "UPDATE dbo.etl_malha SET orientacao = ?, atualizado_em = SYSDATETIME() "
                    "WHERE malha_name = ?", (orientacao, atual))
            else:
                # Degrade suave (ver docstring): a tela segue funcionando na
                # orientação escolhida; só a persistência espera a 074.
                migration_074_pendente = True
                log.warning("[MALHA] migration 074 ausente — orientacao da "
                            "malha '%s' não foi persistida", atual)

        conn.commit(); cur.close(); conn.close()
        # Chaves da orientação são CONDICIONAIS (aditivas): quem não mexeu nela
        # recebe a resposta de sempre, byte a byte.
        resp = {"ok": True, "malha_name": atual, "renomeada": renomeada}
        if tem_orientacao:
            resp["orientacao"] = orientacao
            if migration_074_pendente:
                resp["migration_074_pendente"] = True
        return resp
    except HTTPException:
        raise
    except Exception as e:
        # Rollback explícito: o rename é insert/migra/apaga na mesma transação —
        # uma falha no meio não pode deixar a malha duplicada ou sem filhas.
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/pipelines", tags=["malhas"])
def add_membro(malha_name: str, body: dict = Body(default={}),
               _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Adiciona um pipeline à malha.

    Pré-valida a existência do pipeline (422 com o nome, ANTES da FK) e grava a
    grafia CANONIZADA pelo registro em etl_pipeline — mesma regra da PR #236.
    Idempotente: membro que já existe devolve 200 sem regravar nada."""
    nome_pedido = (body.get("pipeline_name") or "").strip()
    if not nome_pedido:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        pipeline = _pipeline_oficial(cur, nome_pedido)
        if pipeline is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=422,
                                detail=f"Pipeline inexistente: '{nome_pedido}'")
        cur.execute(
            "SELECT 1 FROM dbo.etl_malha_pipeline WHERE malha_name = ? AND pipeline_name = ?",
            (malha, pipeline))
        if cur.fetchone():
            cur.close(); conn.close()
            return {"ok": True, "malha_name": malha, "pipeline_name": pipeline,
                    "ja_membro": True}
        cur.execute(
            "INSERT INTO dbo.etl_malha_pipeline (malha_name, pipeline_name) VALUES (?, ?)",
            (malha, pipeline))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "malha_name": malha, "pipeline_name": pipeline,
                "ja_membro": False}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/pipelines/{pipeline_name}", tags=["malhas"])
def remove_membro(malha_name: str, pipeline_name: str,
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove um pipeline da malha (só o vínculo — o pipeline continua
    existindo, e a dependência global da 067 NÃO é tocada aqui)."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        cur.execute(
            "DELETE FROM dbo.etl_malha_pipeline WHERE malha_name = ? AND pipeline_name = ?",
            (malha, (pipeline_name or "").strip()))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"'{pipeline_name}' não é membro da malha '{malha}'")
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "malha_name": malha}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.put("/malhas/{malha_name}/layout", tags=["malhas"])
def salvar_layout(malha_name: str, body: dict = Body(default={}),
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Persiste a posição dos nós do diagrama (F8) em etl_malha_pipeline.

    Só MEMBROS da malha são atualizados: posição de não-membro é ignorada e
    contada fora de 'atualizados' (o UPDATE não afeta linha) — o front pode
    ter um nó recém-removido da malha no estado local, e isso não é erro.
    Tudo na MESMA transação: um salvar não pode deixar metade do layout novo.

    F10 (§9 do desenho de componentes): entrada com pipeline_name "no:{id}"
    é posição de NÓ ESPECIAL e grava em etl_malha_no.layout_* — mesma regra
    de tolerância (nó de outra malha/excluído conta em 'ignorados'). Sem a
    075, entrada de nó dá 503 instrutivo; layout só de pipelines segue ok."""
    posicoes = body.get("posicoes")
    if not isinstance(posicoes, list):
        raise HTTPException(status_code=422, detail="posicoes deve ser uma lista")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        atualizados = 0
        ignorados = 0
        tem_075 = None      # lazy: só consulta o banco se aparecer nó especial
        for pos in posicoes:
            nome = (pos.get("pipeline_name") or "").strip() if isinstance(pos, dict) else ""
            x = pos.get("layout_x") if isinstance(pos, dict) else None
            y = pos.get("layout_y") if isinstance(pos, dict) else None
            # bool é subclasse de int em Python: true/false no JSON passaria
            # como número e viraria 1.0/0.0 no banco em silêncio.
            if (not nome
                    or not isinstance(x, (int, float)) or isinstance(x, bool)
                    or not isinstance(y, (int, float)) or isinstance(y, bool)):
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail="Cada posição precisa de pipeline_name, layout_x e "
                           "layout_y numéricos")
            if nome.startswith("no:"):
                # Nó especial (F10): "no:{id}" é o contrato do §9 — o prefixo
                # não colide com pipeline real (nome com ':' não é dag_id
                # válido no Airflow).
                if tem_075 is None:
                    tem_075 = _tabelas_075(cur)
                if not tem_075:
                    _fechar_silencioso(conn)
                    raise HTTPException(status_code=503, detail=_MSG_SEM_075)
                try:
                    no_id = int(nome[3:])
                except ValueError:
                    _fechar_silencioso(conn)
                    raise HTTPException(
                        status_code=422,
                        detail="Posição de nó deve usar o formato 'no:{id}'")
                cur.execute(
                    "UPDATE dbo.etl_malha_no SET layout_x = ?, layout_y = ? "
                    "WHERE id = ? AND malha_name = ?",
                    (float(x), float(y), no_id, malha))
            else:
                cur.execute(
                    "UPDATE dbo.etl_malha_pipeline SET layout_x = ?, layout_y = ? "
                    "WHERE malha_name = ? AND pipeline_name = ?",
                    (float(x), float(y), malha, nome))
            if (cur.rowcount or 0) > 0:
                atualizados += 1
            else:
                ignorados += 1
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "atualizados": atualizados, "ignorados": ignorados}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Nós especiais (F10) — o DESENHO dos componentes de malha ─────────────────
# SÓ desenho, ZERO efeito no motor nesta fase: nenhuma linha da 067 nasce
# destes gestos — a compilação do Aguarde (expansão → 067 assinada + espelho
# CSV + carimbo + dry_run) é a F11; o agendamento do Início é a F13; os
# observadores (guardiã) são a F14.

@router.post("/malhas/{malha_name}/nos", tags=["malhas"])
def add_no(malha_name: str, body: dict = Body(default={}),
           _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria um nó especial do desenho (F10 — §1/§2 do desenho de componentes).

    `config` nesta fase é validado só na ESTRUTURA (objeto JSON) — a validação
    rica por tipo (agendamento do Início, título/mensagem da Notificação) é a
    F13. Um Início e um Fim por malha: 422 aqui e índice filtrado da 075 por
    baixo — um INSERT por SQL direto também estoura."""
    tipo = (body.get("tipo") or "").strip().lower()
    if tipo not in _TIPOS_NO:
        raise HTTPException(status_code=422,
                            detail="tipo deve ser um de: inicio, aguarde, "
                                   "notificacao, fim")
    config = body.get("config")
    if config is not None and not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config deve ser um objeto JSON")
    x = body.get("layout_x")
    y = body.get("layout_y")
    for v in (x, y):
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            raise HTTPException(status_code=422,
                                detail="layout_x/layout_y devem ser numéricos")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        if tipo in ("inicio", "fim"):
            cur.execute("SELECT 1 FROM dbo.etl_malha_no "
                        "WHERE malha_name = ? AND tipo = ?", (malha, tipo))
            if cur.fetchone():
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=f"A malha já tem um nó {_ROTULO_NO[tipo]} — só "
                           "pode haver um por malha")
        criado_por = None
        if isinstance(_auth, dict):
            criado_por = (str(_auth.get("matricula") or "").strip() or None)
        cur.execute(
            "INSERT INTO dbo.etl_malha_no "
            "(malha_name, tipo, config_json, layout_x, layout_y, criado_por) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
            (malha, tipo,
             json.dumps(config, ensure_ascii=False) if config is not None else None,
             None if x is None else float(x), None if y is None else float(y),
             (criado_por or "")[:100] or None))
        novo_id = int(cur.fetchone()[0])
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": novo_id, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.patch("/malhas/{malha_name}/nos/{no_id}", tags=["malhas"])
def update_no(malha_name: str, no_id: int, body: dict = Body(default={}),
              _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Atualiza config e/ou layout de um nó (F10 — §9).

    `tipo` NÃO é editável: trocar o tipo mudaria a semântica do desenho por
    baixo do que já está ligado — recriar o nó é o gesto honesto. `config`
    presente com None LIMPA a configuração; a validação rica por tipo é F13."""
    tem_config = "config" in body
    config = body.get("config")
    if tem_config and config is not None and not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config deve ser um objeto JSON")
    tem_layout = ("layout_x" in body) or ("layout_y" in body)
    if tem_layout:
        x, y = body.get("layout_x"), body.get("layout_y")
        for v in (x, y):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise HTTPException(status_code=422,
                                    detail="layout_x e layout_y devem vir "
                                           "juntos e numéricos")
    if not tem_config and not tem_layout:
        raise HTTPException(status_code=422,
                            detail="Nada para atualizar: envie config e/ou "
                                   "layout_x/layout_y")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        cur.execute("SELECT id, tipo FROM dbo.etl_malha_no "
                    "WHERE id = ? AND malha_name = ?", (no_id, malha))
        if cur.fetchone() is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        if tem_config:
            cur.execute(
                "UPDATE dbo.etl_malha_no SET config_json = ? "
                "WHERE id = ? AND malha_name = ?",
                (json.dumps(config, ensure_ascii=False) if config is not None else None,
                 no_id, malha))
        if tem_layout:
            cur.execute(
                "UPDATE dbo.etl_malha_no SET layout_x = ?, layout_y = ? "
                "WHERE id = ? AND malha_name = ?",
                (float(x), float(y), no_id, malha))
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/nos/{no_id}", tags=["malhas"])
def remove_no(malha_name: str, no_id: int,
              _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Exclui um nó do desenho, removendo PRIMEIRO as arestas dele na MESMA
    transação — a FK NO ACTION da 075 (§1.3/§1.4) não deixa outra ordem: um
    DELETE de nó por SQL direto com arestas penduradas falha alto, nunca leva
    desenho junto em silêncio.

    FRONTEIRA F10/F11: nesta fase nós não têm linhas ASSINADAS na 067 (a
    compilação ainda não existe), então não há descompilação — na F11 este
    gesto ganha dry_run e o efeito §7.3 (remover/transferir linhas assinadas
    entre malhas); o Início assinado (raiz vira on_demand) é a F13. As FKs
    origem_no/agenda_no garantem que essa ordem também será obrigatória lá."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        cur.execute("SELECT id, tipo FROM dbo.etl_malha_no "
                    "WHERE id = ? AND malha_name = ?", (no_id, malha))
        if cur.fetchone() is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        cur.execute("DELETE FROM dbo.etl_malha_aresta "
                    "WHERE origem_no = ? OR destino_no = ?", (no_id, no_id))
        arestas_removidas = max(cur.rowcount or 0, 0)
        cur.execute("DELETE FROM dbo.etl_malha_no WHERE id = ?", (no_id,))
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "arestas_removidas": arestas_removidas,
                "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/arestas", tags=["malhas"])
def add_aresta_no(malha_name: str, body: dict = Body(default={}),
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria uma aresta do desenho envolvendo nó (F10), com a GRAMÁTICA COMPLETA
    da tabela §2.1 — cada célula proibida devolve 422 com a mensagem da célula;
    pipeline→pipeline é recusado AQUI com a instrução da porta certa (a aresta
    direta do F8 grava dependência REAL na 067 — outra semântica, outra porta).

    Body (§9): {"origem": {"no": id} | {"pipeline": nome}, "destino": {...}}.
    Idempotente: aresta que já existe devolve ja_existia=True sem regravar.
    O ciclo validado nesta fase é o TOPOLÓGICO do desenho (ver
    _criaria_ciclo_desenho — a fronteira F10/F11 está registrada lá); o
    dry_run com o efeito compilado (§7.2) chega na F11."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        origem = _resolver_ponta(cur, conn, malha, body.get("origem"), "origem")
        destino = _resolver_ponta(cur, conn, malha, body.get("destino"), "destino")
        erro = _erro_gramatica(origem["tipo"], destino["tipo"])
        if erro:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erro)
        arestas = _arestas_da_malha(cur, malha)
        chave_o = _chave_ponta(origem["no"], origem["pipeline"])
        chave_d = _chave_ponta(destino["no"], destino["pipeline"])
        for a in arestas:
            if (_chave_ponta(a["origem_no"], a["origem_pipeline"]) == chave_o
                    and _chave_ponta(a["destino_no"], a["destino_pipeline"]) == chave_d):
                # Idempotente (aceite F8: re-salvar é no-op) — nem commit.
                avisos = _avisos_desenho(_nos_da_malha(cur, malha), arestas)
                cur.close(); conn.close()
                return {"ok": True, "id": a["id"], "ja_existia": True,
                        "avisos": avisos}
        if _criaria_ciclo_desenho(arestas, chave_o, chave_d):
            _fechar_silencioso(conn)
            # Texto espelhado no cliente (regra F8) — determinístico.
            raise HTTPException(
                status_code=422,
                detail=f"Ciclo no desenho: {_rotulo_ponta(origem)} → "
                       f"{_rotulo_ponta(destino)} fecha um ciclo (o caminho "
                       f"volta para {_rotulo_ponta(origem)})")
        cur.execute(
            "INSERT INTO dbo.etl_malha_aresta "
            "(malha_name, origem_no, origem_pipeline, destino_no, destino_pipeline) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
            (malha, origem["no"], origem["pipeline"],
             destino["no"], destino["pipeline"]))
        novo_id = int(cur.fetchone()[0])
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": novo_id, "ja_existia": False, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/arestas/{aresta_id}", tags=["malhas"])
def remove_aresta_no(malha_name: str, aresta_id: int,
                     _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove UMA aresta de nó do desenho (F10 — sem efeito no motor: nenhuma
    linha da 067 é tocada; a recompilação do nó afetado, o dry_run e a
    confirmação de remoção de linhas reais chegam na F11, §7.3)."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        cur.execute("DELETE FROM dbo.etl_malha_aresta "
                    "WHERE id = ? AND malha_name = ?", (aresta_id, malha))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Aresta {aresta_id} não existe na malha '{malha}'")
        avisos = _avisos_desenho(_nos_da_malha(cur, malha),
                                 _arestas_da_malha(cur, malha))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Dependências (F8) — a aresta do diagrama é a dependência REAL da F1 ──────

@router.post("/dependencias", tags=["malhas"])
def add_dependencia(body: dict = Body(default={}),
                    _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria UMA dependência em etl_pipeline_dependencia (tipo PIPELINE).

    É a porta de gravação do MalhaEditor: desenhar a aresta chama aqui, com as
    MESMAS validações do cadastro da F1 (existência e ciclo BFS, importadas de
    routers.pipelines) e a MESMA mensagem de ciclo — o cliente espelha o texto.

    Idempotente: aresta que já existe devolve ja_existia=True sem revalidar
    ciclo (ela foi validada quando nasceu; reprovar um re-salvar quebraria o
    aceite 'salvar sem mudanças é no-op'). Nos dois casos o espelho CSV
    etl_pipeline.depends_on do dependente é reconciliado na mesma transação."""
    nome_dep = (body.get("pipeline_name") or "").strip()
    nome_pred = (body.get("depende_de") or "").strip()
    if not nome_dep or not nome_pred:
        raise HTTPException(status_code=422,
                            detail="pipeline_name e depende_de são obrigatórios")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabela_067(cur, conn)
        # Canoniza as DUAS grafias pela registrada (regra da PR #236): a tabela
        # e o CSV têm de contar a mesma história que os dicts case-sensitive
        # do Python leem depois.
        pipeline = _pipeline_oficial(cur, nome_dep)
        if pipeline is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail=f"Pipeline inexistente: '{nome_dep}'")
        faltando = _validar_existencia(cur, [nome_pred])
        if faltando:
            _fechar_silencioso(conn)
            # Mesmo texto do cadastro da F1 (register_pipeline) de propósito.
            raise HTTPException(
                status_code=422,
                detail="Pipeline inexistente em 'depende de': "
                       + ", ".join(f"'{n}'" for n in faltando))
        depende_de = _pipeline_oficial(cur, nome_pred)
        if pipeline.casefold() == depende_de.casefold():
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422,
                                detail="Pipeline não pode depender de si mesmo")

        cur.execute(
            "SELECT 1 FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE'",
            (pipeline, depende_de))
        ja_existia = cur.fetchone() is not None
        if not ja_existia:
            # BFS da F1 sobre TODAS as dependências — ValueError vira 422 com a
            # mensagem do servidor (o aceite exige cliente e servidor iguais).
            _check_circular(cur, pipeline, [depende_de])
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            cur.execute(
                "INSERT INTO dbo.etl_pipeline_dependencia "
                "(pipeline_name, depende_de, tipo, criado_por) VALUES (?, ?, 'PIPELINE', ?)",
                (pipeline, depende_de, (criado_por or "")[:100] or None))
        mudou_csv = _espelho_csv(cur, pipeline, depende_de, "add")
        # Dependência NOVA troca o schedule da DAG do dependente: liga a
        # pendência de publicação na MESMA transação (Decisão 6/D30). Aresta
        # que já existia não mudou configuração — não liga nada.
        dag_pendente = _ligar_dag_config_pendente(cur, pipeline) if not ja_existia else False
        if not ja_existia or mudou_csv:
            conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "ja_existia": ja_existia,
                "dag_config_pendente": dag_pendente}
    except HTTPException:
        raise
    except ValueError as e:
        # _check_circular sinaliza ciclo por ValueError — mesma tradução da F1.
        _fechar_silencioso(conn)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/dependencias", tags=["malhas"])
def remove_dependencia(body: dict = Body(default={}),
                       _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove UMA dependência REAL (tabela 067 + espelho CSV, mesma transação).

    A confirmação explícita ('isto apaga a dependência real, não só o desenho' —
    §4b da spec) é responsabilidade do MalhaEditor ANTES de chamar aqui: a API
    executa, quem avisa é a tela."""
    nome_dep = (body.get("pipeline_name") or "").strip()
    nome_pred = (body.get("depende_de") or "").strip()
    if not nome_dep or not nome_pred:
        raise HTTPException(status_code=422,
                            detail="pipeline_name e depende_de são obrigatórios")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabela_067(cur, conn)
        # A colação CI do banco casa qualquer caixa no DELETE; o espelho CSV
        # também remove por casefold — canonização aqui seria redundante.
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE'",
            (nome_dep, nome_pred))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Dependência não encontrada: '{nome_dep}' depende de '{nome_pred}'")
        _espelho_csv(cur, nome_dep, nome_pred, "remove")
        # Remoção também muda o schedule da DAG do dependente (pode voltar ao
        # cron): mesma pendência de publicação, mesma transação (Decisão 6).
        dag_pendente = _ligar_dag_config_pendente(cur, nome_dep)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "dag_config_pendente": dag_pendente}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
