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
                                                     + eventos de nó #no:* e
                                                     malha_concluida (F14)
  POST   /malhas/{malha_name}/disparo              — disparo MANUAL da malha (F15;
                                                     dry_run no body): raízes do
                                                     Início via trigger REST
  PATCH  /malhas/{malha_name}                      — descricao / ativo / renomear / orientacao
  POST   /malhas/{malha_name}/pipelines            — adiciona membro (idempotente)
  DELETE /malhas/{malha_name}/pipelines/{pipeline_name} — remove membro
  PUT    /malhas/{malha_name}/layout               — persiste posições dos nós (F8/F10)
  POST   /malhas/{malha_name}/agendamento          — agendamento da malha + compilação
                                                     nas raízes (F13; dry_run no body)
  POST   /malhas/{malha_name}/nos                  — cria nó especial do desenho (F10)
  PATCH  /malhas/{malha_name}/nos/{no_id}          — config/layout do nó (F10)
  DELETE /malhas/{malha_name}/nos/{no_id}          — exclui nó + DESCOMPILA (F11; ?dry_run)
  POST   /malhas/{malha_name}/arestas              — aresta de nó + COMPILA (F11; dry_run no body)
  DELETE /malhas/{malha_name}/arestas/{aresta_id}  — remove aresta + RECOMPILA (F11; ?dry_run)
  POST   /dependencias                             — cria dependência REAL (F8)
  DELETE /dependencias                             — remove dependência REAL (F8;
                                                     linha assinada → 422, F11/Decisão 4)

F8: desenhar uma aresta no MalhaEditor É cadastrar a dependência GLOBAL em
etl_pipeline_dependencia (migration 067) — a mesma tabela da F1, com as MESMAS
validações (existência + ciclo BFS, importadas de routers.pipelines, nunca
reimplementadas). A aresta não tem escopo por malha: se dois pipelines aparecem
em duas malhas, a dependência aparece nas duas, porque é real nas duas.

F10 (docs/malha-componentes-desenho.md): nós especiais do desenho — Início,
Aguarde, Notificação e Fim (etl_malha_no/etl_malha_aresta, migration 075).
A gramática das arestas de nó (§2.1) e os avisos de desenho (§2.2) valem
desde a F10; a aresta pipeline→pipeline continua sendo o F8 acima (o CHECK
CK_malha_ar_tem_no da 075 declara isso no modelo).

F11 (desenho §3/§7): o Aguarde ganha EFEITO — cada gesto que o envolve
compila a expansão N×M (dags/utils/malha_nos.py via o port em services) para
linhas NORMAIS da 067, ASSINADAS com origem_no, com espelho CSV depends_on e
carimbo dag_config_pendente_em na MESMA transação (Decisão 7: incremental por
gesto, o desenho É o compilado). dry_run devolve o efeito §7.2 sem gravar; o
write RECOMPUTA (a autoridade é o estado corrente). Descompilar remove SÓ o
que a expansão perdeu — linha manual coincidente nunca é adotada nem removida
(Decisão 5) e linha que a expansão de OUTRA malha também produz é TRANSFERIDA
(re-assinada, §7.3), nunca derrubada em silêncio. O ciclo passa a ser validado
sobre o conjunto PÓS-expansão com o BFS canônico da F1 e a mensagem literal
compartilhada (Decisão 15); o ciclo topológico do desenho segue de retaguarda
para o ciclo só-de-nós, que não compila nada.

F13 (desenho §4): o Início ganha EFEITO — o agendamento mora na MALHA
(etl_malha.agendamento_json, Decisão 8) e compilar é COPIAR os campos para as
colunas reais de cada raiz ligada ao Início + assinar agenda_no + carimbar,
na mesma transação (POST /malhas/{name}/agendamento, dry_run no body).
Todas as raízes com o MESMO cron e a MESMA virada (Decisão 9) disparam no
mesmo tick do scheduler, cada uma na própria DAG — nenhum disparador novo.
Raiz com dependência na 067 não pode ser ligada ao Início (422, §2.2); raiz
assinada por Início de OUTRA malha idem (422, Decisão 11); desligar a raiz
(aresta/nó excluído) vira on_demand + carimbo — nunca cron restaurado
(Decisão 10). Os observadores (Notificação/Fim) são avaliados pela GUARDIÃ
(F14 — dags/etl_dependencia_guardia.py): aqui só nasce o desenho, a validação
do config por tipo (_validar_config_no) e a leitura dos eventos #no:* no
endpoint de execução.

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
from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user, require_perm
# F15 (disparo manual da malha): o disparo reusa o MESMO caminho do trigger
# manual de pipeline (proxy REST do Airflow) — nenhum executor novo; o client
# e a validação de dag_id vêm do proxy para não nascer uma segunda cópia.
from routers.airflow import _DAG_ID_RE, get_airflow_client
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
# Ponte de identidade / canonização de pipeline (F2 — spec de operação no nível
# de etapa). Aqui entra só `pipeline_oficial`, que morava inline neste módulo.
from services import execucao_identidade as ident_svc
# Helpers da F1 — fonte ÚNICA das validações de dependência (não reimplementar:
# a mensagem de ciclo do servidor é ESPELHADA no cliente pelo MalhaEditor, e
# duas implementações divergiriam). Sem ciclo de import: pipelines.py não
# importa malhas — mesmo padrão de admin.py/copias.py importando de routers.X.
# _check_circular_grafo (F11): o NÚCLEO do BFS com adjacência injetada — o
# ciclo pós-expansão do compilador (Decisão 15) roda o MESMO algoritmo e emite
# a MESMA mensagem literal do cadastro da F1.
# F13 (Decisão 8): o agendamento da malha é validado pelas MESMAS funções do
# register — _build_cron para o domínio, _validate_dias_horarios_mes,
# _parse_horarios_especificos e _parse_hora_opcional (D35) — nunca uma
# reimplementação (a regra que salvou o texto do ciclo na F8).
from routers.pipelines import (_build_cron, _check_circular,
                               _check_circular_grafo, _parse_hora_opcional,
                               _parse_horarios_especificos,
                               _validar_existencia,
                               _validate_dias_horarios_mes, deduplicar)

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
    Implementação extraída para services.dependencias na F11 (as TRÊS portas
    da Decisão 4 precisam do mesmo guard) — o alias local preserva os call
    sites, como _tabela_067."""
    return deps_svc.coluna_origem_no(cur)


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


def _validar_config_no(tipo, config):
    """Validação rica do config por tipo (F14 — a pendência declarada da F13;
    desenho §5/§6). Levanta 422 com instrução; config None passa (limpar é
    gesto legítimo).

    • notificacao: {"titulo"?: str, "mensagem"?: str} — vira o corpo do
      evento MALHA_NOTIFICACAO e do card (a guardiã renderiza na detecção);
    • fim: {"notificar_teams"?: bool} — o card do Teams é OPT-IN (Decisão
      14, default False); o evento e o painel são sempre;
    • inicio/aguarde: sem schema AQUI de propósito — o agendamento do Início
      mora na MALHA (Decisão 8, POST /malhas/{name}/agendamento) e o Aguarde
      não tem configuração; a validação estrutural (objeto JSON) já foi
      feita pelo chamador.

    Chave desconhecida é 422, não silêncio: config que o motor ignora é a
    tela contando uma história e a guardiã outra (princípio 5)."""
    if config is None or tipo not in ("notificacao", "fim"):
        return
    if tipo == "notificacao":
        extras = sorted(set(config) - {"titulo", "mensagem"})
        if extras:
            raise HTTPException(
                status_code=422,
                detail="config da Notificação aceita apenas 'titulo' e "
                       f"'mensagem' — chave(s) desconhecida(s): {', '.join(extras)}")
        for chave in ("titulo", "mensagem"):
            v = config.get(chave)
            if v is not None and not isinstance(v, str):
                raise HTTPException(
                    status_code=422,
                    detail=f"'{chave}' da Notificação deve ser texto")
        return
    extras = sorted(set(config) - {"notificar_teams"})
    if extras:
        raise HTTPException(
            status_code=422,
            detail="config do Fim aceita apenas 'notificar_teams' — "
                   f"chave(s) desconhecida(s): {', '.join(extras)}")
    v = config.get("notificar_teams")
    if v is not None and not isinstance(v, bool):
        raise HTTPException(
            status_code=422,
            detail="'notificar_teams' do Fim deve ser booleano "
                   "(o card do Teams é opt-in — Decisão 14)")


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
    nome é canonizado ANTES de qualquer gravação. Implementação extraída para
    services.execucao_identidade na F2 (o drill-down por etapa precisa da MESMA
    canonização) — mesmo padrão de _virada_global delegando para o service."""
    return ident_svc.pipeline_oficial(cur, pipeline_name)


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


# ── Compilador do Aguarde (F11 — desenho §3/§7) ──────────────────────────────
# O Aguarde é açúcar de compilação: a expansão N×M (canônico em dags/utils/
# malha_nos.py, port em services) vira linhas NORMAIS da 067 assinadas com
# origem_no. O diff de cada gesto é calculado sobre o estado PROSPECTIVO do
# desenho × o estado CORRENTE da 067 — dry_run devolve o efeito §7.2 sem
# gravar; o write recomputa e aplica na MESMA transação (espelho CSV +
# carimbo). Nada aqui é lido pelo motor: quem libera segue sendo liberado().


def _efeito_vazio() -> dict:
    """O bloco `efeito` do §7.2 com todas as chaves — o schema é contrato
    (o modal da F12 itera as listas): gesto sem efeito devolve listas vazias,
    nunca chave ausente. `agendamentos` é preenchido pela F13 (Início)."""
    return {"dependencias_criar": [], "dependencias_remover": [],
            "dependencias_transferir": [], "ja_existentes_manuais": [],
            "agendamentos": [], "republicar": []}


def _nos_globais(cur) -> dict:
    """Mapa global id → {"malha", "tipo"} de etl_malha_no: é o que diz de QUEM
    é cada linha assinada da 067 (a ponte da Decisão 1) e quais OUTRAS malhas
    são candidatas na transferência (§7.3)."""
    cur.execute("SELECT id, malha_name, tipo FROM dbo.etl_malha_no")
    return {int(r[0]): {"malha": (str(r[1]) or "").strip(),
                        "tipo": (str(r[2]) or "").strip().lower()}
            for r in cur.fetchall()}


def _linhas_067(cur) -> dict:
    """Todas as linhas tipo PIPELINE da 067 COM a assinatura, num SELECT só
    (agregação em Python — o padrão do arquivo): {(dep_cf, pred_cf):
    {"dependente", "predecessor", "origem_no"}}. Chamar só com a coluna
    origem_no presente (o chamador guarda)."""
    cur.execute(
        "SELECT pipeline_name, depende_de, origem_no "
        "FROM dbo.etl_pipeline_dependencia WHERE tipo = 'PIPELINE'")
    out = {}
    for r in cur.fetchall():
        dep = str(r[0] or "").strip()
        pred = str(r[1] or "").strip()
        out[(dep.casefold(), pred.casefold())] = {
            "dependente": dep, "predecessor": pred,
            "origem_no": int(r[2]) if r[2] is not None else None}
    return out


def _pares_expansao(dependencias) -> dict:
    """Conjunto compilado {(dep, pred, no_id)} → pares por chave CI:
    {(dep_cf, pred_cf): {"dependente", "predecessor", "nos": set[int]}}.
    Dois Aguardes da mesma malha podem produzir o MESMO par (a 067 tem uma
    linha só por par — ux_dep): o dono é UM nó por vez; o menor id é o
    escolhido determinístico quando a linha nasce."""
    pares: dict = {}
    for dependente, predecessor, no_id in dependencias:
        ch = (dependente.casefold(), predecessor.casefold())
        item = pares.setdefault(ch, {"dependente": dependente,
                                     "predecessor": predecessor, "nos": set()})
        item["nos"].add(no_id)
    return pares


def _dag_criada(cur, pipeline) -> bool:
    """dag_criada do pipeline — decide quem entra em `republicar` (o carimbo
    só existe para DAG publicada; pipeline nunca publicado não tem versão
    velha rodando — a mesma regra do WHERE dag_criada = 1 da 073)."""
    cur.execute("SELECT CAST(dag_criada AS INT) FROM dbo.etl_pipeline "
                "WHERE pipeline_name = ?", (pipeline,))
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) == 1)


def _diff_compilacao(cur, malha, nos_l, arestas_l):
    """O diff §7.2 do gesto: expansão do desenho PROSPECTIVO da malha × estado
    corrente da 067. Devolve o dict interno (itens carregam origem_no para o
    apply; a versão pública sai de _efeito_publico):

      criar      — pares novos, assinados com o menor nó produtor
      manuais    — par desejado que JÁ EXISTE manual (origem_no NULL): não é
                   adotado nem re-criado (Decisão 5 — a linha continua do
                   operador; a exclusão do nó não a leva)
      transferir — linha assinada cujo nó dono deixou de produzi-la mas que a
                   expansão (desta malha OU de outra, §7.3) ainda produz:
                   re-assinada, nunca removida — dentro da própria malha isso
                   também é obrigatório, senão a FK da 075 travaria o DELETE
                   do nó e a proveniência mentiria
      remover    — linha assinada por nó DESTA malha que expansão nenhuma
                   produz mais
      avisos     — par desejado já compilado por OUTRA malha (Decisão 4: não
                   re-assinado; quem manda é a dona — se ela descompilar, a
                   transferência §7.3 o traz para cá)
      republicar — dependentes de criar/remover com dag_criada=1
      pares_pos  — o conjunto PÓS-gesto {(dep_cf,pred_cf): (dep, pred)} — a
                   base do ciclo da Decisão 15 e do preview_expandido (F12)
    """
    expansao = malha_nos_svc.expandir(nos_l, arestas_l)
    desejado = _pares_expansao(expansao["dependencias"])
    nos_info = _nos_globais(cur)
    linhas = _linhas_067(cur)
    malha_cf = malha.casefold()

    def _malha_do_no(no_id):
        info = nos_info.get(no_id)
        return (info["malha"] if info else "").casefold()

    criar, remover, transferir, manuais, avisos = [], [], [], [], []

    # 1) pares que a expansão PROSPECTIVA desta malha produz
    for ch in sorted(desejado):
        item = desejado[ch]
        linha = linhas.get(ch)
        no_alvo = min(item["nos"])
        if linha is None:
            criar.append({"dependente": item["dependente"],
                          "predecessor": item["predecessor"],
                          "origem_no": no_alvo})
        elif linha["origem_no"] is None:
            manuais.append({"dependente": linha["dependente"],
                            "predecessor": linha["predecessor"]})
        elif _malha_do_no(linha["origem_no"]) == malha_cf:
            if linha["origem_no"] not in item["nos"]:
                # o nó dono saiu do desenho (ou perdeu o par), mas OUTRO nó
                # desta malha ainda o produz: re-assina — transferência dentro
                # da própria malha
                transferir.append({"dependente": linha["dependente"],
                                   "predecessor": linha["predecessor"],
                                   "para_malha": malha, "para_no": no_alvo,
                                   "origem_no": linha["origem_no"]})
            # senão: já compilada por este desenho — nada a fazer
        else:
            dona = nos_info.get(linha["origem_no"], {})
            avisos.append(
                f"'{linha['dependente']}' → '{linha['predecessor']}' já "
                f"compilada pelo Aguarde #{linha['origem_no']} da malha "
                f"'{dona.get('malha')}' — não re-assinada (a linha continua "
                "da malha dona; se ela descompilar, a assinatura transfere)")

    # 2) linhas assinadas por nós DESTA malha que a expansão nova não produz:
    #    transferência para OUTRA malha que as produza (§7.3) ou remoção
    cache_outras: dict = {}
    for ch in sorted(linhas):
        linha = linhas[ch]
        if linha["origem_no"] is None or ch in desejado:
            continue
        if _malha_do_no(linha["origem_no"]) != malha_cf:
            continue
        destino = _transferencia_externa(cur, ch, malha_cf, nos_info,
                                         cache_outras)
        if destino is not None:
            transferir.append({"dependente": linha["dependente"],
                               "predecessor": linha["predecessor"],
                               "para_malha": destino[0], "para_no": destino[1],
                               "origem_no": linha["origem_no"]})
        else:
            remover.append({"dependente": linha["dependente"],
                            "predecessor": linha["predecessor"],
                            "origem_no": linha["origem_no"]})

    # 3) republicar: dependentes afetados COM DAG publicada (transferência não
    #    muda o grafo do motor — só a proveniência — e fica de fora)
    republicar = []
    for nome in sorted({i["dependente"] for i in criar + remover},
                       key=str.casefold):
        if _dag_criada(cur, nome):
            republicar.append(nome)

    # 4) o conjunto PÓS-gesto (067 − remoções ∪ adições) — Decisão 15 e preview
    pares_pos = {ch: (linha["dependente"], linha["predecessor"])
                 for ch, linha in linhas.items()}
    for item in remover:
        pares_pos.pop((item["dependente"].casefold(),
                       item["predecessor"].casefold()), None)
    for item in criar:
        pares_pos[(item["dependente"].casefold(),
                   item["predecessor"].casefold())] = (item["dependente"],
                                                       item["predecessor"])

    return {"criar": criar, "remover": remover, "transferir": transferir,
            "manuais": manuais, "avisos": avisos, "republicar": republicar,
            "pares_pos": pares_pos}


def _transferencia_externa(cur, ch, malha_cf, nos_info, cache):
    """Outra malha cuja expansão produz o par `ch` (§7.3): devolve
    (malha_oficial, no_id) ou None. Só malhas com nó Aguarde entram; a busca é
    determinística (malhas em ordem CI, menor nó produtor) e o resultado por
    malha é cacheado dentro do gesto — malhas são dezenas, não milhares."""
    candidatas = sorted({info["malha"] for info in nos_info.values()
                         if info["tipo"] == "aguarde"
                         and info["malha"].casefold() != malha_cf},
                        key=str.casefold)
    for outra in candidatas:
        if outra not in cache:
            expansao = malha_nos_svc.expandir(_nos_da_malha(cur, outra),
                                              _arestas_da_malha(cur, outra))
            cache[outra] = _pares_expansao(expansao["dependencias"])
        pares = cache[outra]
        if ch in pares:
            return outra, min(pares[ch]["nos"])
    return None


def _erros_ciclo_canonico(diff) -> list:
    """Ciclo sobre o conjunto PÓS-expansão do gesto (Decisão 15), com o BFS
    canônico da F1 (_check_circular_grafo) e a MESMA mensagem literal — o
    defeito 3 do QA não renasce pela porta da expansão: um aguarde inocente
    pode fechar A→…→A por linhas que o gesto cria aos pares."""
    if not diff["criar"]:
        return []
    adjacencia: dict = {}
    for dependente, predecessor in diff["pares_pos"].values():
        adjacencia.setdefault(dependente.casefold(), []).append(predecessor)
    por_dependente: dict = {}
    for item in diff["criar"]:
        por_dependente.setdefault(item["dependente"], []).append(item["predecessor"])
    erros = []
    for dependente in sorted(por_dependente, key=str.casefold):
        try:
            _check_circular_grafo(
                dependente, sorted(por_dependente[dependente], key=str.casefold),
                lambda nome: adjacencia.get(nome.casefold(), []))
        except ValueError as e:
            erros.append(str(e))
    return erros


def _aplicar_compilacao(cur, diff, criado_por):
    """Aplica o diff na transação ABERTA do gesto (quem commita é o endpoint —
    uma transação só, rollback explícito): transferências primeiro (UPDATE de
    assinatura — obrigatórias ANTES do DELETE do nó, §1.4), depois remoções e
    criações, cada uma com o espelho CSV do dependente na MESMA transação (o
    mesmíssimo _espelho_csv das portas F5/F8 — nunca uma cópia), e por fim o
    carimbo de republicação dos afetados (WHERE dag_criada = 1)."""
    for item in diff["transferir"]:
        cur.execute(
            "UPDATE dbo.etl_pipeline_dependencia SET origem_no = ? "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE'",
            (item["para_no"], item["dependente"], item["predecessor"]))
    afetados = {i["dependente"] for i in diff["criar"]}
    for item in diff["remover"]:
        # DELETE pela ASSINATURA: linha manual coincidente (origem_no NULL)
        # nunca é atingida — Decisão 5, garantida no próprio WHERE.
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND depende_de = ? AND tipo = 'PIPELINE' "
            "AND origem_no = ?",
            (item["dependente"], item["predecessor"], item["origem_no"]))
        if (cur.rowcount or 0) > 0:
            # Espelho e carimbo SÓ para remoção EFETIVADA (achado da revisão):
            # rowcount 0 = gesto concorrente transferiu/limpou a assinatura
            # entre o cômputo do diff e o apply — tirar o predecessor do CSV
            # com a linha da 067 ainda viva recriaria a divergência que a F6
            # existe para impedir.
            _espelho_csv(cur, item["dependente"], item["predecessor"], "remove")
            afetados.add(item["dependente"])
    for item in diff["criar"]:
        cur.execute(
            "INSERT INTO dbo.etl_pipeline_dependencia "
            "(pipeline_name, depende_de, tipo, criado_por, origem_no) "
            "VALUES (?, ?, 'PIPELINE', ?, ?)",
            (item["dependente"], item["predecessor"],
             (criado_por or "")[:100] or None, item["origem_no"]))
        _espelho_csv(cur, item["dependente"], item["predecessor"], "add")
    for nome in sorted(afetados, key=str.casefold):
        _ligar_dag_config_pendente(cur, nome)


def _efeito_publico(diff) -> dict:
    """O bloco `efeito` do contrato §7.2 (chaves literais; origem_no interno
    fica de fora — a proveniência pública é a do transferir)."""
    if diff is None:
        return _efeito_vazio()
    return {
        "dependencias_criar": [
            {"dependente": i["dependente"], "predecessor": i["predecessor"]}
            for i in diff["criar"]],
        "dependencias_remover": [
            {"dependente": i["dependente"], "predecessor": i["predecessor"]}
            for i in diff["remover"]],
        "dependencias_transferir": [
            {"dependente": i["dependente"], "predecessor": i["predecessor"],
             "para_malha": i["para_malha"], "para_no": i["para_no"]}
            for i in diff["transferir"]],
        "ja_existentes_manuais": list(diff["manuais"]),
        "agendamentos": [],          # F13 (Início) — chave presente por contrato
        "republicar": list(diff["republicar"]),
    }


def _avisos_gesto(nos_l, arestas_l, diff) -> list:
    """Avisos do gesto = estruturais do desenho (§2.2, formato F10) + os do
    COMPILADOR (par já compilado por outra malha — Decisão 4), no MESMO
    formato {"no", "nivel", "mensagem"} para o toast/banner da F12 renderizar
    uma lista só (aviso de compilação não pertence a um nó do desenho:
    no=None)."""
    avisos = _avisos_desenho(nos_l, arestas_l)
    for msg in (diff["avisos"] if diff else []):
        avisos.append({"no": None, "nivel": "leve", "mensagem": msg})
    return avisos


def _preview_expandido(diff) -> list:
    """O conjunto PÓS-gesto como pares {pipeline_name, depende_de} — ADITIVO ao
    §7.2, é sobre ele que o espelho client-side do ciclo (criaCiclo, F12) roda
    (§3.3: cliente avisa antes, servidor é a autoridade, texto idêntico)."""
    if diff is None:
        return []
    return [{"pipeline_name": dep, "depende_de": pred}
            for dep, pred in sorted(diff["pares_pos"].values(),
                                    key=lambda p: (p[0].casefold(),
                                                   p[1].casefold()))]


def _exigir_compilacao(cur, conn):
    """Gesto que COMPILA (envolve Aguarde) precisa da 067 e da coluna de
    assinatura: sem elas não existe 'gravar sem assinar' honesto — 503 com a
    migration certa, no padrão das guardas do arquivo."""
    _exigir_tabela_067(cur, conn)
    if not _coluna_origem_no(cur):
        _fechar_silencioso(conn)
        raise HTTPException(status_code=503, detail=_MSG_SEM_075)


def _descompilacao_possivel(cur) -> bool:
    """Gesto que só DESCOMPILA (remover aresta/nó): sem 067 ou sem a coluna de
    assinatura não EXISTE linha compilada — o gesto segue como na F10, com
    diff vazio (deploy parcial não trava a limpeza do desenho)."""
    return _tabela_067(cur) and _coluna_origem_no(cur)


# ── Compilador do Início (F13 — desenho §4) ──────────────────────────────────
# O agendamento mora na MALHA (etl_malha.agendamento_json, Decisão 8); o nó
# Início é a representação visual e o fio que diz QUEM recebe. Compilar =
# COPIAR os campos para as colunas reais de cada raiz ligada + assinar
# agenda_no + carimbar dag_config_pendente_em — o scheduler do Airflow dispara
# todas no mesmo tick, cada uma na própria DAG; nenhum disparador novo (§4.2).
# O motor NUNCA lê o JSON da malha.

# O schema do agendamento é EXATAMENTE o subconjunto de campos do register
# (§4.1) — chave fora dele é 422: o JSON é fonte de compilação, não saco de
# configuração. hora_virada incluída de propósito (Decisão 9: UMA virada por
# malha, aplicada a TODAS as raízes — mata o risco 4 da spec na raiz).
_CAMPOS_AGENDAMENTO = (
    "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow",
    "schedule_dom", "horarios_especificos", "dias_semana",
    "dias_horarios_mes", "somente_dias_uteis", "calendario_nome",
    "hora_virada",
)

# Nomes dos dias p/ resumo humano (D05 de guarda: convenção cron, 0=domingo).
_DOW_NOMES = {0: "dom", 1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex",
              6: "sáb"}


def _colunas_agenda(cur) -> bool:
    """True se as colunas de agendamento da 075 existem (etl_malha.
    agendamento_json + etl_pipeline.agenda_no). Best-effort no padrão dos
    guards de coluna (073/074): falha conta como ausente e o Início se
    comporta como na F12 (só desenho, zero efeito)."""
    try:
        cur.execute(
            "SELECT COL_LENGTH('dbo.etl_malha', 'agendamento_json'), "
            "COL_LENGTH('dbo.etl_pipeline', 'agenda_no')")
        row = cur.fetchone()
        return bool(row and row[0] is not None and row[1] is not None)
    except Exception as e:
        log.warning("[MALHA] checagem das colunas de agendamento da 075 falhou: %s", e)
        return False


def _int_agenda(bruto, campo, minimo, maximo, default):
    """Inteiro de um campo do agendamento, com faixa: o JSON da malha é
    superfície NOVA — dá para validar faixa sem quebrar paridade com o
    register (que herda a tolerância do formulário)."""
    v = bruto.get(campo)
    if v is None or v == "":
        return default
    if isinstance(v, bool) or not isinstance(v, int):
        raise HTTPException(status_code=422,
                            detail=f"{campo} deve ser um inteiro")
    if not (minimo <= v <= maximo):
        raise HTTPException(
            status_code=422,
            detail=f"{campo} fora do intervalo ({minimo}-{maximo}): {v}")
    return v


def _validar_agendamento(bruto):
    """Valida e NORMALIZA o agendamento da malha (§4.1, Decisão 8) — pelas
    MESMAS funções do register: _validate_dias_horarios_mes,
    _parse_horarios_especificos (422 nos inválidos) e _parse_hora_opcional
    (hora_virada inválida degrada para NULL com aviso — D35). Devolve
    (agendamento_normalizado, avisos_texto).

    'on_demand' é recusado de propósito: desligar raiz do cron é o gesto de
    DESLIGAR a aresta/o Início (Decisão 10) — um agendamento 'sob demanda'
    seria um não-agendamento guardado como se fosse um."""
    if not isinstance(bruto, dict) or not bruto:
        raise HTTPException(status_code=422,
                            detail="agendamento deve ser um objeto com os "
                                   "campos do agendamento da malha")
    extras = sorted(set(bruto) - set(_CAMPOS_AGENDAMENTO))
    if extras:
        raise HTTPException(
            status_code=422,
            detail="Campos fora do schema do agendamento da malha: "
                   + ", ".join(extras))
    st = str(bruto.get("schedule_type") or "").strip().lower()
    if not st:
        raise HTTPException(status_code=422,
                            detail="schedule_type é obrigatório no "
                                   "agendamento da malha")
    if st == "on_demand":
        raise HTTPException(
            status_code=422,
            detail="O agendamento da malha não aceita 'on_demand' — para "
                   "tirar uma raiz do cron, desligue-a do Início (a raiz "
                   "vira sob demanda no gesto).")
    avisos: list[str] = []
    horarios = _parse_horarios_especificos(bruto.get("horarios_especificos"))
    if st == "custom" and not horarios:
        raise HTTPException(
            status_code=422,
            detail="horarios_especificos é obrigatório para schedule_type "
                   "'custom'")
    dias_horarios = _validate_dias_horarios_mes(bruto.get("dias_horarios_mes"))
    if st == "monthly_days_times" and not dias_horarios:
        # Mesma mensagem literal do register.
        raise HTTPException(
            status_code=422,
            detail="dias_horarios_mes é obrigatório para schedule_type "
                   "'monthly_days_times'")
    dias_semana = None
    dias_raw = str(bruto.get("dias_semana") or "").strip()
    if dias_raw:
        dias = []
        for d in dias_raw.split(","):
            d = d.strip()
            if not d:
                continue
            if not d.isdigit() or not (0 <= int(d) <= 6):
                raise HTTPException(
                    status_code=422,
                    detail=f"dias_semana inválido: '{d}' (use 0-6, 0=domingo)")
            dias.append(int(d))
        dias_semana = ",".join(str(d) for d in sorted(set(dias))) or None
    hora = _int_agenda(bruto, "schedule_hour", 0, 23, 6)
    minuto = _int_agenda(bruto, "schedule_minute", 0, 59, 0)
    dom = _int_agenda(bruto, "schedule_dom", 1, 28, 1)
    if st == "biweekly" and dom > 13:
        # Quinzenal é dia D e D+15: dom 17–28 gera cron com dia 32–43 (não
        # existe → Broken DAG após republicar, e a raiz PARA de agendar) e
        # 14–16 cai em 29–31, que pula meses curtos — quinzena falsa. A MESMA
        # regra e mensagem do wizard (defeito GRAVE da revisão adversarial).
        raise HTTPException(
            status_code=422,
            detail=f"Dia da 1ª quinzena inválido (1–13): {dom}")
    # custom/monthly_days_times: hora/minuto seguem o PRIMEIRO horário — a
    # mesma derivação do wizard (buildSchedulePayload), para as colunas das
    # raízes contarem uma história só.
    if st == "custom" and horarios:
        hora, minuto = int(horarios[:2]), int(horarios[3:5])
    elif st == "monthly_days_times" and dias_horarios:
        primeiro = json.loads(dias_horarios)[0]["horarios"][0]
        hora, minuto = int(primeiro[:2]), int(primeiro[3:5])
    return {
        "schedule_type": st,
        "schedule_hour": hora,
        "schedule_minute": minuto,
        "schedule_dow": _int_agenda(bruto, "schedule_dow", 0, 6, 1),
        "schedule_dom": dom,
        "horarios_especificos": horarios,
        "dias_semana": dias_semana,
        "dias_horarios_mes": dias_horarios,
        "somente_dias_uteis": 1 if bruto.get("somente_dias_uteis") in (1, True) else 0,
        "calendario_nome": (str(bruto.get("calendario_nome") or "").strip() or None),
        "hora_virada": _parse_hora_opcional("hora_virada",
                                            bruto.get("hora_virada"), avisos),
    }, avisos


def _scheduled_time_do_agendamento(ag) -> str:
    """scheduled_time DERIVADO do agendamento (a mesma derivação do wizard):
    o gerador de DAGs monta o cron a partir de scheduled_time — sem alinhar a
    coluna, cada raiz dispararia no horário antigo dela e o aceite 'crons
    idênticos' (§10-F13) seria impossível. Não entra no schema §4.1 porque é
    derivado, nunca escolhido."""
    st = ag.get("schedule_type")
    if st == "custom" and ag.get("horarios_especificos"):
        return f"{ag['horarios_especificos'][:5]}:00"
    if st == "monthly_days_times" and ag.get("dias_horarios_mes"):
        try:
            primeiro = json.loads(ag["dias_horarios_mes"])[0]["horarios"][0]
            return f"{primeiro}:00"
        except Exception:
            pass
    return f"{int(ag.get('schedule_hour') or 0):02d}:" \
           f"{int(ag.get('schedule_minute') or 0):02d}:00"


def _resumo_agendamento(ag) -> str:
    """Resumo humano de um agendamento (o 'de'/'para' do diff §7.2 e o
    subtítulo do nó Início). Display-only: a autoridade do gatilho é o
    scheduler — mesmo estatuto do calcularDataRef da F5."""
    if not isinstance(ag, dict) or not ag:
        return "sem agendamento"
    st = str(ag.get("schedule_type") or "").strip().lower()
    if st == "on_demand":
        return "sob demanda"
    try:
        h = int(ag.get("schedule_hour") or 0)
        m = int(ag.get("schedule_minute") or 0)
    except (TypeError, ValueError):
        h, m = 0, 0
    hm = f"{h:02d}:{m:02d}"
    if st == "weekly":
        # dow 0 é DOMINGO (D05) — `or 1` engoliria o zero e viraria segunda.
        dow_raw = ag.get("schedule_dow")
        try:
            dow = int(dow_raw) if dow_raw not in (None, "") else 1
        except (TypeError, ValueError):
            dow = 1
        corpo = f"semanal ({_DOW_NOMES.get(dow, '?')}) {hm}"
    elif st == "monthly":
        corpo = f"mensal (dia {ag.get('schedule_dom') or 1}) {hm}"
    elif st == "biweekly":
        try:
            d = int(ag.get("schedule_dom") or 1)
        except (TypeError, ValueError):
            d = 1
        corpo = f"quinzenal (dias {d} e {d + 15}) {hm}"
    elif st == "hourly":
        corpo = f"de hora em hora (minuto {m:02d})"
    elif st == "custom":
        corpo = f"horários {ag.get('horarios_especificos') or '—'}"
        dias = str(ag.get("dias_semana") or "").strip()
        if dias:
            nomes = ", ".join(_DOW_NOMES.get(int(d), "?")
                              for d in dias.split(",") if d.strip().isdigit())
            corpo += f" ({nomes})"
    elif st == "monthly_days_times":
        try:
            entradas = json.loads(ag.get("dias_horarios_mes") or "[]")
            corpo = "dia+hora: " + "; ".join(
                f"dia {e['dia']} às {', '.join(e['horarios'])}"
                for e in entradas)
        except Exception:
            corpo = "dia+hora (configuração ilegível)"
    elif st == "daily":
        corpo = f"diário {hm}"
    else:
        corpo = f"{st} {hm}"
    extras = []
    if int(ag.get("somente_dias_uteis") or 0):
        extras.append("só dias úteis")
    if ag.get("calendario_nome"):
        extras.append(f"calendário {ag['calendario_nome']}")
    if ag.get("hora_virada"):
        extras.append(f"virada {str(ag['hora_virada'])[:5]}")
    return " · ".join([corpo] + extras)


def _agendamento_da_malha(cur, malha):
    """agendamento_json da malha → dict, ou None (ausente/ilegível — mesmo
    espírito do _no_config: valor quebrado por SQL direto degrada com log,
    nunca tela quebrada). Chamar só com _colunas_agenda True."""
    cur.execute("SELECT agendamento_json FROM dbo.etl_malha "
                "WHERE malha_name = ?", (malha,))
    row = cur.fetchone()
    return _no_config(row[0] if row else None)


def _agenda_da_raiz(cur, pipeline):
    """Fotografia de agendamento de um pipeline raiz: o dict de agenda (o
    'de' do diff), a assinatura agenda_no (+ malha dona do nó) e dag_criada.
    Chamar só com _colunas_agenda True."""
    cur.execute(
        "SELECT p.schedule_type, CAST(p.schedule_hour AS INT), "
        "CAST(p.schedule_minute AS INT), CAST(p.schedule_dow AS INT), "
        "CAST(p.schedule_dom AS INT), p.horarios_especificos, p.dias_semana, "
        "p.dias_horarios_mes, CAST(p.somente_dias_uteis AS INT), "
        "p.calendario_nome, CONVERT(VARCHAR(5), p.hora_virada, 108), "
        "p.agenda_no, n.malha_name, CAST(p.dag_criada AS INT) "
        "FROM dbo.etl_pipeline p "
        "LEFT JOIN dbo.etl_malha_no n ON n.id = p.agenda_no "
        "WHERE p.pipeline_name = ?", (pipeline,))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "agendamento": {
            "schedule_type": (str(row[0]).strip().lower() if row[0] else None),
            "schedule_hour": row[1], "schedule_minute": row[2],
            "schedule_dow": row[3], "schedule_dom": row[4],
            "horarios_especificos": row[5], "dias_semana": row[6],
            "dias_horarios_mes": row[7], "somente_dias_uteis": row[8],
            "calendario_nome": row[9], "hora_virada": row[10],
        },
        "agenda_no": int(row[11]) if row[11] is not None else None,
        "agenda_malha": (str(row[12]).strip() if row[12] else None),
        "dag_criada": int(row[13] or 0),
    }


def _mesma_agenda(agenda_raiz, ag_malha) -> bool:
    """True se a raiz JÁ carrega o agendamento da malha, campo a campo (hora
    normalizada para HH:MM — a coluna devolve VARCHAR(5), o JSON guarda
    HH:MM:SS). Decide se um re-salvar de aresta tem efeito ou é no-op."""
    def _hv(v):
        return str(v)[:5] if v else None

    for campo in _CAMPOS_AGENDAMENTO:
        a, b = agenda_raiz.get(campo), ag_malha.get(campo)
        if campo == "hora_virada":
            a, b = _hv(a), _hv(b)
        elif campo == "somente_dias_uteis":
            a, b = int(a or 0), int(b or 0)
        elif campo in ("schedule_hour", "schedule_minute", "schedule_dow",
                       "schedule_dom"):
            a = int(a) if a is not None else None
            b = int(b) if b is not None else None
        else:
            a = str(a).strip() if a not in (None, "") else None
            b = str(b).strip() if b not in (None, "") else None
        if a != b:
            return False
    return True


def _raiz_tem_dependencia(cur, pipeline) -> bool:
    """True se o pipeline tem QUALQUER dependência (tipo PIPELINE) na 067 —
    a pergunta do 422 de raiz (§2.2): dependente vira schedule=None no
    gerador, e o agendamento plantado seria mentira."""
    cur.execute(
        "SELECT TOP 1 1 FROM dbo.etl_pipeline_dependencia "
        "WHERE pipeline_name = ? AND tipo = 'PIPELINE'", (pipeline,))
    return cur.fetchone() is not None


def _msg_raiz_com_dependencia(pipeline) -> str:
    """422 do §2.2 (a pendência declarada pela revisão da F12): raiz não pode
    ter dependência — o schedule=None do motor venceria o cron e o
    agendamento da malha seria mentira."""
    return (f"'{pipeline}' não pode ser raiz da malha: raiz não pode ter "
            "dependência — o schedule=None do motor venceria o cron e o "
            "agendamento da malha seria mentira. Remova a dependência ou "
            "chegue a ele por um Aguarde.")


def _msg_raiz_de_outra_malha(pipeline, malha_dona, no_id) -> str:
    """422 da Decisão 11: um dono por vez — nunca last-write-wins mudo entre
    malhas; transferência é gesto explícito na malha dona."""
    return (f"'{pipeline}' já é agendado pelo Início #{no_id} da malha "
            f"'{malha_dona}' — um dono por vez: desligue-o de lá antes de "
            "agendá-lo por aqui.")


def _aplicar_agenda_na_raiz(cur, pipeline, ag, no_id):
    """COPIA o agendamento da malha para as colunas REAIS da raiz + assina
    agenda_no + carimba a republicação (WHERE dag_criada=1), na transação
    ABERTA do gesto (§4.2 — quem commita é o endpoint). UM UPDATE só, sem
    try/except por grupo de migration: o endpoint já exigiu a 075, e banco
    com a 075 tem as colunas de agenda (017/018/024/067) — falha aqui é
    rollback TOTAL, nunca cópia pela metade."""
    cur.execute(
        "UPDATE dbo.etl_pipeline SET scheduled_time = ?, schedule_type = ?, "
        "schedule_hour = ?, schedule_minute = ?, schedule_dow = ?, "
        "schedule_dom = ?, horarios_especificos = ?, dias_semana = ?, "
        "dias_horarios_mes = ?, somente_dias_uteis = ?, calendario_nome = ?, "
        "hora_virada = ?, agenda_no = ?, updated_at = GETDATE() "
        "WHERE pipeline_name = ?",
        (_scheduled_time_do_agendamento(ag), ag["schedule_type"],
         ag.get("schedule_hour"), ag.get("schedule_minute"),
         ag.get("schedule_dow"), ag.get("schedule_dom"),
         ag.get("horarios_especificos"), ag.get("dias_semana"),
         ag.get("dias_horarios_mes"), int(ag.get("somente_dias_uteis") or 0),
         ag.get("calendario_nome"), ag.get("hora_virada"), no_id, pipeline))
    _ligar_dag_config_pendente(cur, pipeline)


def _desligar_raiz(cur, pipeline):
    """Decisão 10: desligar a raiz do Início = 'on_demand' + limpar a
    assinatura + carimbo — NUNCA restauração do agendamento antigo (classe
    D40: pipeline voltando a rodar sozinho em silêncio). on_demand →
    schedule=None no gerador: DAG ativa, só manual, visível. As demais
    colunas de agenda ficam como estão — inertes para o gatilho (o
    on_demand curto-circuita o cron no gerador) e a hora_virada é
    PRESERVADA de propósito: mudá-la mudaria o rótulo ODATE de execuções
    já registradas."""
    cur.execute(
        "UPDATE dbo.etl_pipeline SET schedule_type = 'on_demand', "
        "agenda_no = NULL, updated_at = GETDATE() WHERE pipeline_name = ?",
        (pipeline,))
    _ligar_dag_config_pendente(cur, pipeline)


def _raizes_assinadas_do_no(cur, no_id) -> list:
    """Pipelines cuja assinatura agenda_no aponta para o nó — a fonte honesta
    para a exclusão do Início (§7.3): a FK NO ACTION da 075 derruba o DELETE
    do nó com assinatura pendurada, então desligar TODAS antes é a única
    ordem possível."""
    cur.execute("SELECT pipeline_name FROM dbo.etl_pipeline "
                "WHERE agenda_no = ?", (no_id,))
    return sorted((str(r[0]).strip() for r in cur.fetchall()),
                  key=str.casefold)


def _msg_disparo_raiz_com_dependencia(pipeline) -> str:
    """Aviso do dry_run do disparo manual (F15): a raiz tem dependência na
    067 — o trigger manual NÃO consulta liberado(), então a corrida parte por
    cima do predecessor. Mesma linguagem do 422 do §2.2 (raiz não pode ter
    dependência), em tom de aviso: o gesto continua sendo do operador."""
    return (f"'{pipeline}' tem dependência cadastrada — o disparo manual não "
            "consulta a liberação: a corrida parte POR CIMA do predecessor, "
            "sem esperar o SUCESSO dele na data. Se a intenção é respeitar a "
            "dependência, dispare o predecessor.")


def _msg_corrida_existente(pipeline, quantas, data_ref) -> str:
    """Aviso do dry_run do disparo manual (F15): já existe corrida da raiz na
    data. Os DEPENDENTES são protegidos pelo claim serializable (uma corrida
    por data), a RAIZ não — disparar de novo roda de novo."""
    return (f"'{pipeline}' já tem {quantas} corrida(s) registrada(s) em "
            f"{data_ref.strftime('%Y-%m-%d')} — disparar de novo executa o "
            "pipeline outra vez (a proteção de corrida única vale para os "
            "dependentes, não para a raiz disparada à mão).")


def _msg_contradicao(pipeline) -> str:
    """Aviso do badge de contradição (§2.2, última linha): raiz assinada que
    ganhou dependência por OUTRA porta — aviso, nunca bloqueio das portas."""
    return (f"raiz '{pipeline}' tem dependência cadastrada — o motor obedece "
            "a dependência e o agendamento da malha está inerte nela")


def _mesclar_efeito_agenda(efeito, efeito_ag, republicar_ag):
    """Anexa o efeito de agendamento do Início (F13) ao bloco §7.2 do gesto —
    `agendamentos` deixa de ser sempre-vazio e `republicar` une compilação e
    agenda, sem duplicar."""
    if efeito_ag:
        efeito["agendamentos"] = list(efeito_ag)
    if republicar_ag:
        efeito["republicar"] = sorted({*efeito["republicar"], *republicar_ag},
                                      key=str.casefold)
    return efeito


# ── Agregados do CARD da lista (etapas · última execução · gatilho) ──────────
# Os três campos são ADITIVOS no contrato do GET /malhas (front antigo ignora)
# e cada um degrada SOZINHO quando a migration que o sustenta falta. Nenhum
# deles abre consulta POR MALHA: a lista pode ter dezenas de malhas e um N+1
# aqui viraria dezenas de round-trips a cada refresh da tela.

# Campos de agendamento que o resumo do GATILHO lê do MEMBRO. É EXATAMENTE
# _CAMPOS_AGENDAMENTO (o mesmo schema da malha), inclusive os qualificadores
# somente_dias_uteis/calendario_nome/hora_virada: eles viram extras no
# _resumo_agendamento ("· só dias úteis · calendário X") e omiti-los faria a
# MESMA malha ter duas verdades — texto completo quando o gatilho vem do
# Início, texto podado quando vem dos membros. Uma linguagem só no card.
_CAMPOS_CRON_MEMBRO = _CAMPOS_AGENDAMENTO


def _ultima_execucao_por_pipeline(cur) -> dict:
    """{pipeline_casefold: (momento, status, pipeline)} — a corrida MAIS
    RECENTE de cada pipeline que é membro de ALGUMA malha. A composição por
    malha é feita em Python, sobre as linhas de membros que o endpoint já leu.

    O timestamp que responde "quando esta malha foi usada" é o **início da
    corrida** (COALESCE com criado_em, porque corrida ainda não partida —
    AGUARDANDO_DEPENDENCIA — tem inicio NULL e mesmo assim é registro real).
    NÃO é `data_referencia`: o ODATE é o dia de PROCESSAMENTO e pode estar no
    futuro ou no passado do relógio (uma corrida de 05/08 iniciada em 03/08 é
    rotina) — exibi-lo como "última execução" mentiria para o operador. E NÃO
    é `fim`: corrida EXECUTANDO ainda não tem fim e sumiria justamente quando
    é mais interessante.

    FORMA da consulta (top-1 por pipeline com CROSS APPLY, não um ROW_NUMBER
    sobre o JOIN inteiro): etl_pipeline_execucao é HISTÓRICO sem expurgo e
    esta leitura roda a cada abertura da tela. Ranquear o JOIN inteiro obriga
    a varrer a tabela toda; o APPLY entra por `pipeline_name = ?` — um SEEK
    por pipeline membro no índice ix_pipe_exec_ultima (migration 077), lendo
    só as corridas de quem está em alguma malha. NÃO existe recorte por data
    de propósito: malha parada há meses tem de continuar mostrando quando
    rodou pela última vez.

    Chamar só com _tabelas_067_execucao True."""
    cur.execute(
        "SELECT m.pipeline_name, u.status, u.momento "
        "FROM (SELECT DISTINCT pipeline_name FROM dbo.etl_malha_pipeline) m "
        "CROSS APPLY ("
        " SELECT TOP 1 e.status AS status,"
        "        COALESCE(e.inicio, e.criado_em) AS momento"
        " FROM dbo.etl_pipeline_execucao e"
        " WHERE e.pipeline_name = m.pipeline_name"
        " ORDER BY COALESCE(e.inicio, e.criado_em) DESC, e.id DESC) u")
    out = {}
    for pipeline, status, momento in cur.fetchall():
        out[str(pipeline or "").strip().casefold()] = (momento, status,
                                                       pipeline)
    return out


def _pipelines_com_dependencia(cur) -> set:
    """Nomes (casefold) dos pipelines que têm QUALQUER dependência PIPELINE na
    067. Dependente vira schedule=None no gerador: o cron gravado nele está
    INERTE, e contá-lo como gatilho da malha seria mentira na tela. Uma
    consulta só — chamar com _tabela_067 True."""
    cur.execute("SELECT DISTINCT pipeline_name "
                "FROM dbo.etl_pipeline_dependencia WHERE tipo = 'PIPELINE'")
    return {str(r[0]).strip().casefold() for r in cur.fetchall() if r[0]}


def _malhas_com_agenda_vigente(cur) -> set:
    """Malhas em que o agendamento salvo está REALMENTE VIGENTE: existe nó
    Início E existe ao menos uma raiz ASSINADA por ele (etl_pipeline.agenda_no
    apontando para aquele nó).

    Por que a checagem existe: `agendamento_json` sobrevive de propósito à
    exclusão do Início (§7.3/Decisão 10 — o nó é o plugue, recriá-lo não perde
    a configuração) e pode ser salvo ANTES de o Início ser desenhado. Nos dois
    casos as raízes estão em `on_demand` e NADA dispara — anunciar o horário
    guardado no card seria a mentira mais cara do produto, e ainda permanente
    (não há rota para limpar o agendamento).

    Uma consulta de CONJUNTO — chamar só com _tabelas_075 e _colunas_agenda
    True."""
    cur.execute(
        "SELECT DISTINCT n.malha_name FROM dbo.etl_malha_no n "
        "JOIN dbo.etl_pipeline p ON p.agenda_no = n.id "
        "WHERE n.tipo = 'inicio'")
    return {str(r[0]).strip() for r in cur.fetchall() if r[0]}


def _gatilho_sob_demanda() -> dict:
    """O gatilho honesto de quem não tem cron nenhum: a malha só anda por
    disparo manual (ou por push de um pipeline de fora dela)."""
    return {"origem": "nenhum", "resumo": "sob demanda", "horario": None,
            "qtd_pipelines": 0, "horarios": [], "detalhes": [],
            "agendamento": None}


def _gatilho_da_malha(ag) -> dict:
    """Gatilho quando a MALHA tem agendamento próprio VIGENTE (F13, Decisão 8):
    o resumo sai do MESMO _resumo_agendamento que o nó Início mostra — duas
    derivações do mesmo JSON divergiriam e a tela contradiria o diagrama.

    Chamar só para malha em _malhas_com_agenda_vigente: agendamento guardado
    sem Início ligado NÃO dispara nada e não pode virar horário no card."""
    return {"origem": "malha", "resumo": _resumo_agendamento(ag),
            "horario": _scheduled_time_do_agendamento(ag)[:5],
            "qtd_pipelines": 0, "horarios": [], "detalhes": [],
            "agendamento": ag}


def _gatilho_dos_membros(membros_cron) -> dict:
    """Gatilho DERIVADO dos membros que disparam sozinhos — cada item é
    {"pipeline", "agendamento"} já filtrado (ATIVO, schedule_type ≠ on_demand
    e sem dependência na 067).

    Um horário só → "diário 06:00 (2 pipelines)". Horários distintos → o MAIS
    CEDO com a indicação de que há outros ("06:00 · +2 horários"): o card não
    tem espaço para a lista, e esconder que existem outros faria o operador
    achar que a malha inteira parte às 06:00."""
    if not membros_cron:
        return _gatilho_sob_demanda()
    detalhes, horarios, resumos = [], [], []
    for m in membros_cron:
        ag = m["agendamento"]
        resumo = _resumo_agendamento(ag)
        hm = _scheduled_time_do_agendamento(ag)[:5]
        detalhes.append({"pipeline": m["pipeline"], "resumo": resumo,
                         "horario": hm})
        horarios.append(hm)
        resumos.append(resumo)
    detalhes.sort(key=lambda d: (d["horario"], d["pipeline"].casefold()))
    distintos = sorted(set(horarios))
    n = len(membros_cron)
    plural = "s" if n != 1 else ""
    if len(set(resumos)) == 1:
        # Todos com o MESMO agendamento: o resumo completo cabe e é exato.
        texto = f"{resumos[0]} ({n} pipeline{plural})"
    else:
        extras = len(distintos) - 1
        texto = f"{distintos[0]} · +{extras} horário{'s' if extras != 1 else ''}" \
            if extras > 0 else f"{distintos[0]} ({n} pipeline{plural})"
    return {"origem": "membros", "resumo": texto, "horario": distintos[0],
            "qtd_pipelines": n, "horarios": distintos, "detalhes": detalhes,
            "agendamento": None}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/malhas", tags=["malhas"])
def list_malhas(_auth: dict = Depends(get_current_user)):
    """Lista malhas com agregados por malha: qtd de pipelines, qtd de ativos, a
    criticidade mais alta entre os membros e — o que o card da tela mostra —
    total de ETAPAS, ÚLTIMA EXECUÇÃO e GATILHO. Ordenada por nome.

    Os três últimos são ADITIVOS (front antigo ignora) e degradam sozinhos:
    sem a 067 não há última execução (`null`) nem como saber quem é dependente;
    sem a coluna de agendamento da 075 o gatilho sai só dos membros. Tudo em
    consultas de CONJUNTO — nenhuma por malha.

    O `gatilho` só afirma o que VALE HOJE: agendamento da malha exige Início
    ligado a raiz assinada (senão vira `agendamento_guardado` e a precedência
    segue), e membro só conta se estiver ATIVO, com cron e sem dependência —
    inativo tem DAG pausada, dependente vira schedule=None."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if not _tabelas_070(cur):
            cur.close(); conn.close()
            log.warning("[MALHA] tabelas da migration 070 ausentes — lista degradada para vazio")
            # migration_pendente é CONTRATO com o front: é ela que liga o banner
            # de deploy parcial e desabilita o "Nova malha" na tela.
            return {"malhas": [], "migration_pendente": True}

        # orientacao (074) é ADITIVA na lista: o card pode ignorar; a coluna
        # ausente degrada para o default sem mudar o SQL de hoje. Idem
        # agendamento_json (075): sem a coluna, o gatilho cai nos membros.
        tem_074 = _coluna_074(cur)
        tem_agenda = _colunas_agenda(cur)
        cur.execute(
            "SELECT malha_name, descricao, CAST(ativo AS INT) AS ativo, "
            "criado_em, criado_por, atualizado_em"
            + (", orientacao" if tem_074 else "")
            + (", agendamento_json" if tem_agenda else "") +
            " FROM dbo.etl_malha ORDER BY malha_name"
        )
        data = []
        indice: dict[str, dict] = {}
        ag_malha: dict[str, dict] = {}
        for r in cur.fetchall():
            rec = {
                "malha_name": r[0], "descricao": r[1], "ativo": int(r[2] or 0),
                "criado_em": _fmt_dt(r[3]), "criado_por": r[4],
                "atualizado_em": _fmt_dt(r[5]),
                "orientacao": _orientacao_norm(r[6]) if tem_074 else "horizontal",
                "qtd_pipelines": 0, "qtd_ativos": 0, "qtd_etapas": 0,
                "criticidade": None, "ultima_execucao": None,
                "gatilho": _gatilho_sob_demanda(),
                # Existe agendamento salvo que NÃO está vigente (sem Início
                # ligado a nenhuma raiz)? O `gatilho` não pode anunciá-lo, mas
                # o front tem direito de dizer que ele está guardado — some
                # sozinho quando o Início for (re)ligado.
                "agendamento_guardado": False,
            }
            data.append(rec)
            indice[rec["malha_name"]] = rec
            if tem_agenda:
                ag = _no_config(r[7 if tem_074 else 6])
                if ag:
                    ag_malha[rec["malha_name"]] = ag

        # Membros num SELECT só (agregação em Python): evita N+1 e mantém a
        # regra da criticidade num único lugar testável. As etapas entram como
        # COUNT correlacionado (PK de etl_pipeline_job é pipeline_name+job_name
        # — a contagem é um seek) e as colunas de cron alimentam o gatilho
        # derivado dos membros, sem uma segunda ida ao banco.
        cur.execute(
            "SELECT mp.malha_name, CAST(p.active AS INT) AS active, "
            "ISNULL(p.criticidade, 'Media') AS criticidade, "
            "(SELECT COUNT(*) FROM dbo.etl_pipeline_job j "
            " WHERE j.pipeline_name = mp.pipeline_name) AS qtd_etapas, "
            "p.pipeline_name, p.schedule_type, "
            "CAST(p.schedule_hour AS INT), CAST(p.schedule_minute AS INT), "
            "CAST(p.schedule_dow AS INT), CAST(p.schedule_dom AS INT), "
            "p.horarios_especificos, p.dias_semana, p.dias_horarios_mes, "
            "CAST(p.somente_dias_uteis AS INT), p.calendario_nome, "
            "CONVERT(VARCHAR(5), p.hora_virada, 108) "
            "FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name"
        )
        membros_linhas = cur.fetchall()

        # Quem é DEPENDENTE não conta como gatilho: o gerador troca o cron dele
        # por schedule=None. Sem a 067 ninguém é dependente (a tabela não
        # existe) e o schedule_type sozinho decide — o comportamento pré-F1.
        dependentes: set = set()
        if _tabela_067(cur):
            dependentes = _pipelines_com_dependencia(cur)
        else:
            log.warning("[MALHA] migration 067 ausente — gatilho da lista sem "
                        "o filtro de dependentes")

        crits: dict[str, list] = {}
        cron: dict[str, list] = {}
        for row in membros_linhas:
            malha, active, crit, qtd_etapas, pipeline, st = row[0], row[1], row[2], row[3], row[4], row[5]
            rec = indice.get(malha)
            if rec is None:
                continue
            rec["qtd_pipelines"] += 1
            rec["qtd_ativos"] += int(active or 0)
            rec["qtd_etapas"] += int(qtd_etapas or 0)
            crits.setdefault(malha, []).append(crit)
            # Pipeline INATIVO não dispara: a tela de pipelines PAUSA a DAG no
            # Airflow ao inativar e a SP de geração filtra active=1. O cron
            # continua gravado na linha, mas está morto — contá-lo faria o
            # card anunciar um horário que ninguém honra.
            if not int(active or 0):
                continue
            tipo = (str(st).strip().lower() if st else "")
            if not tipo or tipo == "on_demand":
                continue
            if str(pipeline or "").strip().casefold() in dependentes:
                continue
            cron.setdefault(malha, []).append({
                "pipeline": pipeline,
                "agendamento": dict(zip(_CAMPOS_CRON_MEMBRO,
                                        (tipo,) + tuple(row[6:16]))),
            })
        for malha, lista in crits.items():
            indice[malha]["criticidade"] = criticidade_agregada(lista)

        # Agendamento da malha só vale se estiver VIGENTE (Início ligado a pelo
        # menos uma raiz assinada). Sem as tabelas da 075 não há nó nenhum:
        # nenhum agendamento é vigente e o gatilho cai nos membros.
        vigentes: set = set()
        if ag_malha and _tabelas_075(cur):
            vigentes = _malhas_com_agenda_vigente(cur)
        for malha, rec in indice.items():
            # Agendamento PRÓPRIO da malha (F13) manda — quando ele de fato
            # está plantado nas raízes. Guardado-porém-inerte não é gatilho:
            # vira só a flag, e a precedência segue para os membros.
            if malha in ag_malha and malha in vigentes:
                rec["gatilho"] = _gatilho_da_malha(ag_malha[malha])
                continue
            if malha in ag_malha:
                rec["agendamento_guardado"] = True
            if malha in cron:
                rec["gatilho"] = _gatilho_dos_membros(cron[malha])

        # Última execução: UMA consulta (top-1 por pipeline membro) e a
        # composição por malha aqui, sobre as linhas de membros já lidas —
        # o mesmo padrão de agregação-em-Python da criticidade.
        if _tabelas_067_execucao(cur):
            por_pipeline = _ultima_execucao_por_pipeline(cur)
            melhor: dict[str, tuple] = {}
            for row in membros_linhas:
                malha = row[0]
                if indice.get(malha) is None:
                    continue
                u = por_pipeline.get(str(row[4] or "").strip().casefold())
                if u is None:
                    continue
                # Desempate por nome do pipeline: duas corridas no mesmo
                # instante não podem alternar entre refreshes da tela.
                atual = melhor.get(malha)
                if atual is None or (u[0], u[2].casefold()) > (atual[0],
                                                               atual[2].casefold()):
                    melhor[malha] = u
            for malha, (momento, status, pipeline) in melhor.items():
                indice[malha]["ultima_execucao"] = {
                    "em": _fmt_dt(momento), "status": status,
                    "pipeline": pipeline}
        else:
            log.warning("[MALHA] tabelas de execução da 067 ausentes — lista "
                        "sem 'última execução'")

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
        # F10/F13: as tabelas da 075 habilitam nós e assinaturas — checadas UMA
        # vez por request; as colunas de agendamento (F13) têm guard próprio,
        # porque a 075 pode estar aplicada pela metade num deploy parcial.
        tem_075 = _tabelas_075(cur)
        tem_agenda = tem_075 and _colunas_agenda(cur)
        # JOIN em etl_pipeline: além dos metadados, garante que membro de
        # pipeline excluído simplesmente some (aceite da F7) — e a FK CASCADE
        # da 070 já removeu a linha de qualquer forma. agenda_no (F13) é
        # ADITIVO: entra no SELECT só com as colunas da 075 presentes.
        cur.execute(
            "SELECT p.pipeline_name, CAST(p.active AS INT) AS active, "
            "ISNULL(p.criticidade, 'Media') AS criticidade, p.schedule_type, "
            "mp.layout_x, mp.layout_y"
            + (", p.agenda_no" if tem_agenda else "") +
            " FROM dbo.etl_malha_pipeline mp "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
            "WHERE mp.malha_name = ? ORDER BY p.pipeline_name",
            (malha["malha_name"],),
        )
        membros = []
        for r in cur.fetchall():
            m = {
                "pipeline_name": r[0], "active": int(r[1] or 0),
                "criticidade": r[2], "schedule_type": r[3],
                "layout_x": r[4], "layout_y": r[5],
            }
            if tem_agenda:
                m["agenda_no"] = int(r[6]) if r[6] is not None else None
            membros.append(m)
        # Arestas (F8): dependências GLOBAIS da 067 em que AMBAS as pontas são
        # membros desta malha — a mesma dependência aparece em toda malha que
        # contenha os dois pipelines (aceite da F8: a aresta é real nas duas).
        # Filtro em Python sobre um SELECT só, como nos agregados da listagem.
        # Deploy parcial (067 pendente): a malha ainda abre, com "arestas": [] —
        # migration_067_pendente é o sinal para o front avisar e travar a edição.
        tem_067 = _tabela_067(cur)
        arestas = []
        if tem_067:
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
            # F13: o agendamento da MALHA (Decisão 8) + os avisos de agenda —
            # Início ligado sem agendamento configurado (aviso forte enquanto
            # durar) e o badge de contradição da raiz assinada que ganhou
            # dependência por outra porta (§2.2, última linha).
            if tem_agenda:
                agendamento = _agendamento_da_malha(cur, malha["malha_name"])
                malha["agendamento"] = agendamento
                malha["agendamento_resumo"] = (
                    _resumo_agendamento(agendamento) if agendamento else None)
                inicio = next((n for n in nos_l if n["tipo"] == "inicio"), None)
                if inicio is not None:
                    tem_saida_inicio = any(a["origem_no"] == inicio["id"]
                                           for a in arestas_l)
                    if agendamento is None and tem_saida_inicio:
                        avisos.append({
                            "no": inicio["id"], "nivel": "forte", "mensagem":
                            "o Início está ligado a raízes, mas a malha ainda "
                            "não tem agendamento — configure no painel do "
                            "Início"})
                    if tem_067:
                        for m in membros:
                            if m.get("agenda_no") != inicio["id"]:
                                continue
                            if _raiz_tem_dependencia(cur, m["pipeline_name"]):
                                m["agenda_contradicao"] = True
                                # `tipo` (F15): chave ESTÁVEL para o front
                                # filtrar este aviso na visão de Execução (é
                                # onde mora o disparo manual, que atropela a
                                # dependência) sem casar texto — a mensagem
                                # continua tendo uma fonte só, aqui.
                                avisos.append({
                                    "no": inicio["id"], "nivel": "forte",
                                    "tipo": "contradicao",
                                    "mensagem": _msg_contradicao(
                                        m["pipeline_name"])})
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
            # F14: eventos dos nós observadores desta malha (marcador #no:{id}
            # resolvido para o id — risco 6 do desenho: o único leitor do
            # marcador é este endpoint) e a conclusão da malha na data.
            "eventos_no": [],
            "malha_concluida": None,
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

        # Nós desta malha (F14): resolve o marcador '#no:{id}' dos eventos de
        # observador. Sem a 075 (deploy parcial) degrada — eventos_no vazio +
        # flag, o resto da visão intacto (princípio 6; padrão do GET detalhe).
        marcador_no: dict[str, dict] = {}
        if _tabelas_075(cur):
            for n in _nos_da_malha(cur, malha):
                marcador_no[f"#no:{n['id']}"] = n
        else:
            resposta["migration_075_pendente"] = True

        # Eventos da guardiã da MESMA data — de membros (F9) e dos nós desta
        # malha (F14) — mais novo primeiro. Marcador de nó de OUTRA malha não
        # resolve aqui e não aparece (mesma regra do filtro por membro).
        cur.execute(
            "SELECT pipeline_name, tipo, detectado_em, detalhe "
            "FROM dbo.etl_dependencia_evento WHERE data_referencia = ?",
            (data_ref,))
        eventos = []
        eventos_no = []
        for r in cur.fetchall():
            bruto = str(r[0] or "").strip()
            no = marcador_no.get(bruto)
            if no is not None:
                eventos_no.append({
                    "no_id": no["id"],
                    "tipo_no": no["tipo"],
                    "tipo": r[1],
                    "criado_em": _fmt_dt(r[2]),
                    "mensagem": r[3],
                })
                continue
            oficial = membro_oficial.get(bruto.casefold())
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
        eventos_no.sort(key=lambda e: (e["criado_em"] or "", e["no_id"]),
                        reverse=True)
        resposta["eventos"] = eventos
        resposta["eventos_no"] = eventos_no
        # Conclusão da malha na data (§6): o evento MALHA_CONCLUIDA do nó Fim.
        # Evento emitido é histórico verdadeiro (F4 §7.2) — o banner some só
        # trocando a data consultada, nunca por apagamento.
        for ev in eventos_no:
            if ev["tipo"] == "MALHA_CONCLUIDA" and ev["tipo_no"] == "fim":
                resposta["malha_concluida"] = {"em": ev["criado_em"]}
                break

        cur.close(); conn.close()
        return resposta
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/disparo", tags=["malhas"])
async def disparar_malha(malha_name: str, body: dict = Body(default={}),
                         auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Disparo MANUAL da malha (F15): dispara as RAÍZES ligadas ao Início com
    o MESMO ODATE, via trigger REST do Airflow — a cascata anda pelo push da
    F3 (o filho herda a data e dispara em segundos após o último predecessor).

    NENHUM executor novo (princípio 1 do desenho): este endpoint é o mesmo
    gesto de "rodar pipeline" da tela Pipelines, repetido para cada raiz, com
    o conf da casa (o schema de montar_conf do push, §7 da retomada):
      • data_referencia — o rótulo ODATE pedido (default: ODATE corrente pela
        virada da MALHA — Decisão 9 — ou, sem agendamento, pela virada global);
        o filho NÃO recalcula: herança pela cadeia inteira;
      • dia_operacional — HOJE (F3: o dia de um disparo manual é o dia em que
        o operador ordenou — as regras de DIA julgam contra ele);
      • disparado_por — auditoria: malha + matrícula de quem disparou (o
        registro da corrida grava em etl_pipeline_execucao.disparado_por).
    run_id com prefixo 'manual' — a origem F3 do disparo é 'manual' (não
    julga hora, julga dia), como no botão da tela Pipelines.

    Body: {"data_referencia"?: "YYYY-MM-DD", "dry_run"?: bool}. dry_run
    devolve o que SERÁ disparado (raízes + ODATE + avisos) sem tocar o
    Airflow — o modal de confirmação da tela mostra essa lista (§7.2, a
    mesma cadência dos gestos do desenho). Os avisos por raiz são honestos
    sobre o que o gesto atropela: DAG não publicada, pipeline inativo, raiz
    COM DEPENDÊNCIA (o trigger manual não consulta liberado() — a corrida
    parte por cima do predecessor) e corrida JÁ existente na data (o claim
    protege os dependentes, não a raiz disparada à mão). O write reporta
    erro POR RAIZ (uma raiz recusada não impede as outras — o resultado é
    dito, nunca escondido). Permissão: acao_executar, a mesma do trigger de
    pipeline.

    Sem a 075 não existe desenho (Início/raízes) — 503 instrutivo. Malha
    sem Início ou Início sem raízes é 422: não há o que disparar."""
    dry_run = bool(body.get("dry_run"))
    # Valida a data ANTES de abrir conexão (mesma regra do GET /execucao).
    data_ref = None
    bruto = body.get("data_referencia")
    if bruto is not None and str(bruto).strip() != "":
        try:
            data_ref = datetime.strptime(str(bruto).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"data_referencia inválida: '{bruto}' "
                       "(use o formato YYYY-MM-DD)")
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
        nos_l = _nos_da_malha(cur, malha)
        arestas_l = _arestas_da_malha(cur, malha)
        inicio = next((n for n in nos_l if n["tipo"] == "inicio"), None)
        if inicio is None:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"A malha '{malha}' não tem componente Início — o "
                       "disparo manual parte das raízes ligadas a ele. "
                       "Adicione o Início no diagrama e ligue-o às raízes.")
        raizes = sorted({a["destino_pipeline"] for a in arestas_l
                         if a["origem_no"] == inicio["id"]
                         and a["destino_pipeline"]}, key=str.casefold)
        if not raizes:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=422,
                detail=f"O Início da malha '{malha}' não está ligado a "
                       "nenhuma raiz — ligue-o aos pipelines que abrem a "
                       "malha antes de disparar.")
        if data_ref is None:
            # ODATE corrente pela virada GLOBAL — a MESMA régua do
            # GET /execucao (o painel de onde o gesto parte). Uma fonte só
            # para o ODATE default: usar a virada da MALHA aqui faria o
            # painel mostrar D e o disparo carimbar D+1 no mesmo minuto
            # (virada da malha 20:00 × global 00:00, às 21:00) — divergência
            # entre a tela e o que foi disparado, a doença que a retomada
            # inteira existiu para matar. Se um dia a régua do painel passar
            # a ser a virada da malha (Decisão 9), muda-se no /execucao e
            # este default acompanha; não é escopo da F15. Na prática o front
            # sempre manda a data EXIBIDA — este default é a rede de proteção
            # de quem chama a API direto.
            data_ref = dref.calcular(_agora(), _virada_global(cur))

        # Fotografia honesta por raiz (avisos ditos ANTES do gesto — §2.2).
        avisos: list = []
        cur.execute("SELECT CAST(ativo AS INT) FROM dbo.etl_malha "
                    "WHERE malha_name = ?", (malha,))
        row = cur.fetchone()
        if row is not None and int(row[0] or 0) == 0:
            avisos.append({"no": None, "nivel": "forte", "mensagem":
                           "malha inativa — os observadores (Notificação e "
                           "Fim) não emitem eventos enquanto ativo=0; o "
                           "disparo das raízes acontece mesmo assim"})
        tem_067 = _tabela_067(cur)
        tem_exec_067 = _tabelas_067_execucao(cur)
        raizes_info = []
        for p in raizes:
            cur.execute(
                "SELECT CAST(active AS INT), CAST(dag_criada AS INT) "
                "FROM dbo.etl_pipeline WHERE pipeline_name = ?", (p,))
            r = cur.fetchone()
            ativo_p = int(r[0] or 0) if r else 0
            dag_criada = int(r[1] or 0) if r else 0
            info = {"pipeline": p, "active": ativo_p, "dag_criada": dag_criada,
                    "tem_dependencia": False, "corridas_na_data": 0}
            raizes_info.append(info)
            # Raiz que ganhou dependência por outra porta (§2.2): o disparo
            # manual parte a corrida POR CIMA do predecessor — o trigger
            # manual não consulta liberado(). Aviso, nunca bloqueio (a mesma
            # régua do badge de contradição): o gesto é do operador, mas ele
            # precisa saber o que está atropelando ANTES de confirmar.
            if tem_067 and _raiz_tem_dependencia(cur, p):
                info["tem_dependencia"] = True
                avisos.append({"no": inicio["id"], "nivel": "forte",
                               "tipo": "contradicao",
                               "mensagem": _msg_disparo_raiz_com_dependencia(p)})
            # Corrida JÁ registrada na data: os filhos são protegidos pelo
            # claim serializable, a RAIZ não — disparar de novo roda de novo.
            if tem_exec_067:
                cur.execute(
                    "SELECT COUNT(*) FROM dbo.etl_pipeline_execucao "
                    "WHERE pipeline_name = ? AND data_referencia = ?",
                    (p, data_ref))
                row_c = cur.fetchone()
                n_corridas = int(row_c[0] or 0) if row_c else 0
                info["corridas_na_data"] = n_corridas
                if n_corridas > 0:
                    avisos.append({
                        "no": inicio["id"], "nivel": "forte",
                        "tipo": "corrida_existente",
                        "mensagem": _msg_corrida_existente(p, n_corridas,
                                                           data_ref)})
            if dag_criada == 0:
                avisos.append({"no": inicio["id"], "nivel": "forte",
                               "mensagem": f"'{p}': a DAG ainda não foi "
                               "publicada — o disparo desta raiz vai falhar "
                               "no Airflow (Pipelines ▸ Publicar nova versão)"})
            elif ativo_p == 0:
                avisos.append({"no": inicio["id"], "nivel": "leve",
                               "mensagem": f"'{p}' está inativo — a DAG pode "
                               "estar pausada no Airflow; a corrida criada "
                               "só anda com a DAG despausada"})
        # O banco fecha ANTES das chamadas ao Airflow: uma rede lenta não
        # pode segurar conexão de pool aberta (padrão do proxy).
        cur.close(); conn.close(); conn = None

        if dry_run:
            return {"data_referencia": data_ref.strftime("%Y-%m-%d"),
                    "raizes": raizes_info, "avisos": avisos}

        hoje = _agora().date()
        quem = (str(auth.get("matricula") or "").strip() or "?")
        conf = {
            "data_referencia": data_ref.strftime("%Y-%m-%d"),
            "dia_operacional": hoje.strftime("%Y-%m-%d"),
            "disparado_por": f"malha:{malha} ({quem})",
        }
        disparadas: list = []
        falhas: list = []
        async with get_airflow_client() as client:
            for p in raizes:
                if not _DAG_ID_RE.match(p):
                    falhas.append({"pipeline": p, "erro":
                                   "nome de pipeline não é um dag_id válido"})
                    continue
                # Mesmo formato do novo_run_id da retomada, origem 'manual'.
                carimbo = datetime.now().strftime("%Y%m%dT%H%M%S%f")
                run_id = (f"manual__{data_ref.strftime('%Y-%m-%d')}__"
                          f"{p[:60]}__{carimbo}")
                try:
                    r = await client.post(
                        f"/api/v1/dags/{p}/dagRuns",
                        json={"dag_run_id": run_id, "conf": conf},
                        headers={"Content-Type": "application/json"})
                    if r.is_success:
                        disparadas.append({
                            "pipeline": p,
                            "dag_run_id": r.json().get("dag_run_id", run_id)})
                    elif r.status_code == 404:
                        falhas.append({"pipeline": p, "erro":
                                       "DAG não encontrada no Airflow — "
                                       "publique o pipeline antes de disparar "
                                       "(Pipelines ▸ Publicar nova versão)"})
                    elif r.status_code == 409:
                        falhas.append({"pipeline": p, "erro":
                                       "o Airflow recusou: já existe uma "
                                       "corrida com este run_id"})
                    else:
                        falhas.append({"pipeline": p, "erro":
                                       f"Airflow recusou o disparo "
                                       f"(HTTP {r.status_code}): {r.text[:200]}"})
                except Exception as e:      # noqa: BLE001 — erro POR RAIZ
                    falhas.append({"pipeline": p, "erro":
                                   f"falha ao contatar o Airflow: {e}"})
        log.info("[MALHA] disparo manual da malha '%s' por %s — data_ref=%s, "
                 "%d disparada(s), %d falha(s)", malha, quem,
                 conf["data_referencia"], len(disparadas), len(falhas))
        return {"ok": len(falhas) == 0,
                "data_referencia": conf["data_referencia"],
                "disparadas": disparadas, "falhas": falhas, "avisos": avisos}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
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
    existindo, e a dependência global da 067 NÃO é tocada aqui).

    F11 (§7.3): membro LIGADO a componente do desenho é recusado com 422 —
    remover o membro por baixo do desenho deixaria arestas apontando para um
    não-membro. Desligar primeiro (excluir a aresta/nó) é o gesto honesto,
    com o diff da descompilação dito lá. Sem a 075 (deploy parcial), o
    comportamento é o de sempre — não existe desenho para proteger."""
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        nome = (pipeline_name or "").strip()
        if _tabelas_075(cur):
            cur.execute(
                "SELECT 1 FROM dbo.etl_malha_aresta WHERE malha_name = ? "
                "AND (origem_pipeline = ? OR destino_pipeline = ?)",
                (malha, nome, nome))
            if cur.fetchone():
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=f"'{nome}' está ligado a componente(s) do desenho "
                           f"da malha '{malha}' — desligue-o dos componentes "
                           "primeiro (exclua as arestas dele no diagrama).")
        cur.execute(
            "DELETE FROM dbo.etl_malha_pipeline WHERE malha_name = ? AND pipeline_name = ?",
            (malha, nome))
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


@router.post("/malhas/{malha_name}/agendamento", tags=["malhas"])
def salvar_agendamento_malha(malha_name: str, body: dict = Body(default={}),
                             _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Salva o agendamento da MALHA (F13 — §4, Decisão 8) e o COMPILA para as
    raízes ligadas ao Início: cópia campo a campo para as colunas reais
    (scheduled_time derivado incluído), assinatura agenda_no e carimbo de
    republicação, numa transação única. Todas as raízes ficam com o MESMO
    cron e a MESMA virada (Decisão 9) → o scheduler dispara todas no mesmo
    tick, em paralelo, cada uma na própria DAG (§4.2) — nenhum disparador
    novo, nenhuma DAG-mestre.

    Body (§9): {"agendamento": {...subconjunto do register, §4.1...},
    "dry_run"?}. dry_run devolve o efeito §7.2 sem gravar ({efeito, avisos,
    erros} — conflito de assinatura vai em `erros`, HTTP 200, como o ciclo
    do compilador); o write RECOMPUTA sobre o estado corrente e o conflito
    vira 422 nomeando a malha e o nó donos (Decisão 11). Raiz assinada que
    ganhou dependência por outra porta recebe AVISO de contradição (badge
    §2.2) — nunca bloqueio. Sem nó Início (ou sem saídas) o JSON é salvo
    com aviso forte: o nó é o plugue, a configuração não se perde ao
    recriá-lo (Decisão 8)."""
    dry_run = bool(body.get("dry_run"))
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabelas(cur, conn)
        _exigir_tabelas_075(cur, conn)
        if not _colunas_agenda(cur):
            _fechar_silencioso(conn)
            raise HTTPException(status_code=503, detail=_MSG_SEM_075)
        malha = _malha_oficial(cur, malha_name)
        if malha is None:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                                detail=f"Malha não encontrada: '{malha_name}'")
        ag, avisos_validacao = _validar_agendamento(body.get("agendamento"))
        resumo_para = _resumo_agendamento(ag)
        nos_l = _nos_da_malha(cur, malha)
        arestas_l = _arestas_da_malha(cur, malha)
        inicio = next((n for n in nos_l if n["tipo"] == "inicio"), None)
        raizes = sorted({a["destino_pipeline"] for a in arestas_l
                         if inicio is not None
                         and a["origem_no"] == inicio["id"]
                         and a["destino_pipeline"]}, key=str.casefold)

        tem_067 = _tabela_067(cur)
        erros: list = []
        efeito = _efeito_vazio()
        avisos = _avisos_desenho(nos_l, arestas_l)
        for msg in avisos_validacao:        # hora_virada inválida → NULL (D35)
            avisos.append({"no": None, "nivel": "leve", "mensagem": msg})
        if inicio is None:
            avisos.append({"no": None, "nivel": "forte", "mensagem":
                           "a malha não tem nó Início — o agendamento fica "
                           "guardado e só alcança raízes quando um Início "
                           "for ligado"})
        aplicar: list = []          # raízes que recebem a cópia no write
        for p in raizes:
            info = _agenda_da_raiz(cur, p)
            if info is None:
                continue    # membro sumiu num gesto concorrente — defensivo
            if info["agenda_no"] is not None and \
                    (info["agenda_malha"] or "").casefold() != malha.casefold():
                # Decisão 11: um dono por vez — nunca last-write-wins mudo.
                erros.append(_msg_raiz_de_outra_malha(
                    p, info["agenda_malha"], info["agenda_no"]))
                continue
            if tem_067 and _raiz_tem_dependencia(cur, p):
                avisos.append({"no": inicio["id"], "nivel": "forte",
                               "mensagem": _msg_contradicao(p)})
            if info["agenda_no"] == inicio["id"] and \
                    _mesma_agenda(info["agendamento"], ag):
                continue            # já compilada campo a campo — no-op honesto
            aplicar.append(p)
            efeito["agendamentos"].append({
                "pipeline": p,
                "de": _resumo_agendamento(info["agendamento"]),
                "para": resumo_para})
            if info["dag_criada"] == 1:
                efeito["republicar"].append(p)

        if dry_run:
            cur.close(); conn.close()
            return {"efeito": efeito, "avisos": avisos, "erros": erros}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        cur.execute(
            "UPDATE dbo.etl_malha SET agendamento_json = ?, "
            "atualizado_em = SYSDATETIME() WHERE malha_name = ?",
            (json.dumps(ag, ensure_ascii=False), malha))
        for p in aplicar:
            _aplicar_agenda_na_raiz(cur, p, ag, inicio["id"])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "efeito": efeito, "avisos": avisos,
                "agendamento": ag, "agendamento_resumo": resumo_para,
                # o cron pela MESMA função do register (conferência visual —
                # a autoridade do gatilho segue sendo o scheduler)
                "cron": _build_cron(ag["schedule_type"], ag["schedule_hour"],
                                    ag["schedule_minute"], ag["schedule_dow"],
                                    ag["schedule_dom"])}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Nós especiais (F10) — o DESENHO dos componentes de malha ─────────────────
# O desenho e sua validação: a compilação do Aguarde (expansão → 067 assinada
# + espelho CSV + carimbo + dry_run) é a F11; o agendamento do Início é a F13;
# os observadores (Notificação/Fim) são avaliados pela guardiã (F14) — aqui a
# F14 só valida o config por tipo (_validar_config_no).

@router.post("/malhas/{malha_name}/nos", tags=["malhas"])
def add_no(malha_name: str, body: dict = Body(default={}),
           _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria um nó especial do desenho (F10 — §1/§2 do desenho de componentes).

    `config` é validado na estrutura (objeto JSON) e por TIPO
    (_validar_config_no, F14): Notificação {titulo?, mensagem?}, Fim
    {notificar_teams?} — o agendamento do Início mora na MALHA (F13,
    Decisão 8). Um Início e um Fim por malha: 422 aqui e índice filtrado da
    075 por baixo — um INSERT por SQL direto também estoura."""
    tipo = (body.get("tipo") or "").strip().lower()
    if tipo not in _TIPOS_NO:
        raise HTTPException(status_code=422,
                            detail="tipo deve ser um de: inicio, aguarde, "
                                   "notificacao, fim")
    config = body.get("config")
    if config is not None and not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config deve ser um objeto JSON")
    _validar_config_no(tipo, config)
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
    presente com None LIMPA a configuração; config não-nulo é validado por
    TIPO (_validar_config_no, F14) — o tipo vem da LINHA, não do body."""
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
        linha_no = cur.fetchone()
        if linha_no is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        if tem_config and config is not None:
            try:
                _validar_config_no((str(linha_no[1] or "")).strip().lower(),
                                   config)
            except HTTPException:
                _fechar_silencioso(conn)
                raise
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
def remove_no(malha_name: str, no_id: int, dry_run: bool = False,
              _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Exclui um nó do desenho — gesto destrutivo (§7.3): a MESMA transação
    DESCOMPILA as linhas assinadas do nó (remove com espelho CSV + carimbo, ou
    TRANSFERE a assinatura quando a expansão de outra malha — ou de outro nó
    desta — ainda produz o par), remove as arestas do nó e o nó, nesta ordem.
    A FK NO ACTION da 075 (§1.3/§1.4) não deixa ordem outra: um DELETE de nó
    por SQL direto com arestas ou assinaturas penduradas falha alto, nunca
    leva desenho ou dependência junto em silêncio.

    ?dry_run=true devolve o efeito §7.2 sem gravar. A recompilação pode
    CRIAR linhas (067 divergida do desenho) — o ciclo canônico da Decisão 15
    vale aqui também: dry_run devolve em `erros`, write é 422. O Início
    assinado (raiz vira on_demand) é a F13 — a FK agenda_no garantirá a
    mesma ordem lá."""
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
        row = cur.fetchone()
        if row is None:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=404,
                                detail=f"Nó {no_id} não existe na malha '{malha}'")
        tipo_no = (row[1] or "").strip().lower()
        nos_l = _nos_da_malha(cur, malha)
        arestas = _arestas_da_malha(cur, malha)
        nos_prospectivos = [n for n in nos_l if n["id"] != no_id]
        prospectivas = [a for a in arestas
                        if a["origem_no"] != no_id and a["destino_no"] != no_id]
        # Só a exclusão de AGUARDE muda compilação: pela gramática §2.1 nenhum
        # outro tipo entra no upstream nem nas saídas de um Aguarde.
        diff, erros = None, []
        if tipo_no == "aguarde" and _descompilacao_possivel(cur):
            diff = _diff_compilacao(cur, malha, nos_prospectivos, prospectivas)
            # A recompilação (Decisão 7) pode conter CRIAÇÕES quando a 067
            # divergiu do desenho (achado da revisão: linha manual apagada +
            # aresta inversa criada no vão) — criação passa pelo MESMO ciclo
            # canônico do add, senão a remoção recriaria o par fechando A↔D.
            erros = _erros_ciclo_canonico(diff)

        # F13 — excluir o INÍCIO (Decisão 10/§7.3): toda raiz ASSINADA por
        # este nó vira on_demand + carimbo, ANTES do DELETE — a FK agenda_no
        # (NO ACTION, §1.4) derruba o DELETE com assinatura pendurada, então
        # esta é a única ordem possível. O agendamento_json da MALHA fica:
        # o nó é o plugue; recriar o Início não perde a configuração
        # (Decisão 8).
        efeito_ag, republicar_ag = [], []
        if tipo_no == "inicio" and _colunas_agenda(cur):
            for p in _raizes_assinadas_do_no(cur, no_id):
                info = _agenda_da_raiz(cur, p)
                if info is None:
                    continue
                efeito_ag.append({
                    "pipeline": p,
                    "de": _resumo_agendamento(info["agendamento"]),
                    "para": "sob demanda"})
                if info["dag_criada"] == 1:
                    republicar_ag.append(p)

        if dry_run:
            avisos = _avisos_gesto(nos_prospectivos, prospectivas, diff)
            cur.close(); conn.close()
            return {"efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                     efeito_ag, republicar_ag),
                    "avisos": avisos, "erros": erros,
                    "preview_expandido": _preview_expandido(diff)}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        if diff is not None:
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            # Descompila ANTES do DELETE do nó — com linha assinada pendurada
            # a FK FK_dep_origem_no derrubaria o DELETE (a ordem do §1.4).
            _aplicar_compilacao(cur, diff, criado_por)
        for item in efeito_ag:
            _desligar_raiz(cur, item["pipeline"])
        cur.execute("DELETE FROM dbo.etl_malha_aresta "
                    "WHERE origem_no = ? OR destino_no = ?", (no_id, no_id))
        arestas_removidas = max(cur.rowcount or 0, 0)
        cur.execute("DELETE FROM dbo.etl_malha_no WHERE id = ?", (no_id,))
        avisos = _avisos_gesto(nos_prospectivos, prospectivas, diff)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "arestas_removidas": arestas_removidas,
                "avisos": avisos,
                "efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                 efeito_ag, republicar_ag)}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/malhas/{malha_name}/arestas", tags=["malhas"])
def add_aresta_no(malha_name: str, body: dict = Body(default={}),
                  _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria uma aresta do desenho envolvendo nó, com a GRAMÁTICA COMPLETA da
    tabela §2.1 — cada célula proibida devolve 422 com a mensagem da célula;
    pipeline→pipeline é recusado AQUI com a instrução da porta certa (a aresta
    direta do F8 grava dependência REAL na 067 — outra semântica, outra porta).

    Body (§9): {"origem": {"no": id} | {"pipeline": nome}, "destino": {...},
    "dry_run": bool?}. Idempotente: aresta que já existe devolve
    ja_existia=True — e o write ainda RECONCILIA a compilação se a 067 tiver
    divergido do desenho (o invariante da Decisão 7: o desenho É o compilado).

    F11 — aresta envolvendo AGUARDE compila (expansão → 067 assinada + espelho
    CSV + carimbo, uma transação): dry_run devolve o efeito §7.2 sem gravar
    (erros de ciclo vão na lista `erros`, HTTP 200 — o modal da F12 mostra);
    o write recomputa sobre o estado corrente e o ciclo vira 422. O ciclo é
    validado PRIMEIRO sobre o conjunto pós-expansão (BFS canônico da F1 +
    mensagem literal — Decisão 15); o topológico do desenho segue de
    retaguarda para o ciclo só-de-nós, que não compila nada."""
    dry_run = bool(body.get("dry_run"))
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
        nos_l = _nos_da_malha(cur, malha)
        arestas = _arestas_da_malha(cur, malha)
        chave_o = _chave_ponta(origem["no"], origem["pipeline"])
        chave_d = _chave_ponta(destino["no"], destino["pipeline"])
        ja_existia = next(
            (a for a in arestas
             if _chave_ponta(a["origem_no"], a["origem_pipeline"]) == chave_o
             and _chave_ponta(a["destino_no"], a["destino_pipeline"]) == chave_d),
            None)
        prospectivas = arestas if ja_existia is not None else arestas + [{
            "id": None, "origem_no": origem["no"],
            "origem_pipeline": origem["pipeline"],
            "destino_no": destino["no"],
            "destino_pipeline": destino["pipeline"]}]

        # Compilação (F11): só aresta que toca AGUARDE tem efeito na 067 —
        # Início planta agenda (F13) e Notificação/Fim observam (F14).
        diff, erros = None, []
        if "aguarde" in (origem["tipo"], destino["tipo"]):
            _exigir_compilacao(cur, conn)
            diff = _diff_compilacao(cur, malha, nos_l, prospectivas)
            erros = _erros_ciclo_canonico(diff)
        if ja_existia is None and not erros \
                and _criaria_ciclo_desenho(arestas, chave_o, chave_d):
            # Retaguarda topológica (texto espelhado no cliente, regra F8).
            erros.append(
                f"Ciclo no desenho: {_rotulo_ponta(origem)} → "
                f"{_rotulo_ponta(destino)} fecha um ciclo (o caminho "
                f"volta para {_rotulo_ponta(origem)})")

        # F13 — Início → pipeline: o Início planta o agendamento da malha na
        # raiz (§4.2). As validações são do MOMENTO DO GESTO (aresta NOVA,
        # como a gramática): raiz com dependência na 067 → 422 (§2.2 — o
        # schedule=None do motor venceria o cron e o agendamento da malha
        # seria mentira); raiz assinada por Início de OUTRA malha → 422
        # nomeando a dona (Decisão 11). Re-salvar aresta existente segue
        # no-op reconciliável: a contradição vira aviso/badge, nunca recusa.
        efeito_ag, avisos_ag, republicar_ag = [], [], []
        ag_malha = None
        if origem["tipo"] == "inicio" and destino["pipeline"] is not None:
            if ja_existia is None and _tabela_067(cur) \
                    and _raiz_tem_dependencia(cur, destino["pipeline"]):
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=_msg_raiz_com_dependencia(destino["pipeline"]))
            if _colunas_agenda(cur):
                info = _agenda_da_raiz(cur, destino["pipeline"])
                assinada_outra = (
                    info is not None and info["agenda_no"] is not None
                    and (info["agenda_malha"] or "").casefold()
                    != malha.casefold())
                if assinada_outra and ja_existia is None:
                    _fechar_silencioso(conn)
                    raise HTTPException(
                        status_code=422,
                        detail=_msg_raiz_de_outra_malha(
                            destino["pipeline"], info["agenda_malha"],
                            info["agenda_no"]))
                ag_malha = _agendamento_da_malha(cur, malha)
                if ag_malha is None:
                    # Liga só o fio, com o aviso do §4.2 — nada plantado.
                    avisos_ag.append({
                        "no": origem["no"], "nivel": "forte", "mensagem":
                        "configure o agendamento no Início — o fio fica "
                        "ligado, mas nenhuma agenda foi plantada ainda"})
                elif assinada_outra:
                    # Re-salvar de aresta cuja raiz é de outra malha: nunca
                    # re-assinada (o mesmo espírito da Decisão 4) — dito.
                    avisos_ag.append({
                        "no": origem["no"], "nivel": "leve", "mensagem":
                        _msg_raiz_de_outra_malha(
                            destino["pipeline"], info["agenda_malha"],
                            info["agenda_no"]) + " Nada foi re-assinado."})
                elif info is not None and not (
                        info["agenda_no"] == origem["no"]
                        and _mesma_agenda(info["agendamento"], ag_malha)):
                    # A cópia acontece (P com agendamento próprio NÃO
                    # assinado pode — a substituição é consentida no diff).
                    efeito_ag.append({
                        "pipeline": destino["pipeline"],
                        "de": _resumo_agendamento(info["agendamento"]),
                        "para": _resumo_agendamento(ag_malha)})
                    if info["dag_criada"] == 1:
                        republicar_ag.append(destino["pipeline"])
                if ja_existia is not None and _tabela_067(cur) \
                        and _raiz_tem_dependencia(cur, destino["pipeline"]):
                    # Badge de contradição (§2.2): aviso, nunca bloqueio.
                    avisos_ag.append({"no": origem["no"], "nivel": "forte",
                                      "mensagem": _msg_contradicao(
                                          destino["pipeline"])})

        if dry_run:
            avisos = _avisos_gesto(nos_l, prospectivas, diff) + avisos_ag
            efeito = _mesclar_efeito_agenda(_efeito_publico(diff),
                                            efeito_ag, republicar_ag)
            cur.close(); conn.close()
            return {"efeito": efeito, "avisos": avisos,
                    "erros": erros,
                    "preview_expandido": _preview_expandido(diff)}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        novo_id = ja_existia["id"] if ja_existia is not None else None
        if ja_existia is None:
            cur.execute(
                "INSERT INTO dbo.etl_malha_aresta "
                "(malha_name, origem_no, origem_pipeline, destino_no, destino_pipeline) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                (malha, origem["no"], origem["pipeline"],
                 destino["no"], destino["pipeline"]))
            novo_id = int(cur.fetchone()[0])
        tem_efeito = diff is not None and (diff["criar"] or diff["remover"]
                                           or diff["transferir"])
        if tem_efeito:
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            _aplicar_compilacao(cur, diff, criado_por)
        if efeito_ag:
            # F13: cópia do agendamento + assinatura + carimbo, na MESMA
            # transação da aresta (§4.2) — o desenho É o compilado.
            _aplicar_agenda_na_raiz(cur, destino["pipeline"], ag_malha,
                                    origem["no"])
        avisos = _avisos_gesto(nos_l, prospectivas, diff) + avisos_ag
        if ja_existia is None or tem_efeito or efeito_ag:
            conn.commit()
        # aresta re-salvada SEM efeito novo: no-op de verdade — nem commit
        cur.close(); conn.close()
        return {"ok": True, "id": novo_id,
                "ja_existia": ja_existia is not None, "avisos": avisos,
                "efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                 efeito_ag, republicar_ag)}
    except HTTPException:
        raise
    except Exception as e:
        _fechar_silencioso(conn)
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/malhas/{malha_name}/arestas/{aresta_id}", tags=["malhas"])
def remove_aresta_no(malha_name: str, aresta_id: int, dry_run: bool = False,
                     _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove UMA aresta de nó do desenho e RECOMPILA o efeito (F11, §7.3):
    linha assinada que a expansão nova não produz é removida (com espelho CSV
    e carimbo) — ou TRANSFERIDA quando a expansão desta ou de OUTRA malha
    ainda a produz. ?dry_run=true devolve o efeito §7.2 sem gravar; a
    confirmação quando remove ≥1 linha real é gesto da tela (F12), como no
    DELETE /dependencias do F8 — a API executa, quem avisa é a tela. Como a
    recompilação pode CRIAR linhas (067 divergida do desenho), o ciclo
    canônico da Decisão 15 vale AQUI também: dry_run devolve em `erros`,
    write é 422 com a mensagem literal da F1."""
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
        nos_l = _nos_da_malha(cur, malha)
        arestas = _arestas_da_malha(cur, malha)
        alvo = next((a for a in arestas if a["id"] == aresta_id), None)
        if alvo is None:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Aresta {aresta_id} não existe na malha '{malha}'")
        prospectivas = [a for a in arestas if a["id"] != aresta_id]
        tipos = {n["id"]: n["tipo"] for n in nos_l}
        envolve_aguarde = ("aguarde" in (tipos.get(alvo["origem_no"]),
                                         tipos.get(alvo["destino_no"])))
        diff, erros = None, []
        if envolve_aguarde and _descompilacao_possivel(cur):
            diff = _diff_compilacao(cur, malha, nos_l, prospectivas)
            # A recompilação pode conter CRIAÇÕES quando a 067 divergiu do
            # desenho (achado da revisão) — ciclo canônico como no add: sem
            # isto o gesto de remoção recriaria uma linha que fecha A↔D.
            erros = _erros_ciclo_canonico(diff)

        # F13 — desligar a raiz do Início (Decisão 10): raiz ASSINADA por este
        # Início vira on_demand + carimbo — nunca restauração do agendamento
        # antigo, nunca cron remanescente. Sem as colunas da 075 (deploy
        # parcial) não existe assinatura — o gesto segue como na F12.
        efeito_ag, republicar_ag = [], []
        if tipos.get(alvo["origem_no"]) == "inicio" \
                and alvo["destino_pipeline"] and _colunas_agenda(cur):
            info = _agenda_da_raiz(cur, alvo["destino_pipeline"])
            if info is not None and info["agenda_no"] == alvo["origem_no"]:
                efeito_ag.append({
                    "pipeline": alvo["destino_pipeline"],
                    "de": _resumo_agendamento(info["agendamento"]),
                    "para": "sob demanda"})
                if info["dag_criada"] == 1:
                    republicar_ag.append(alvo["destino_pipeline"])

        if dry_run:
            avisos = _avisos_gesto(nos_l, prospectivas, diff)
            cur.close(); conn.close()
            return {"efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                     efeito_ag, republicar_ag),
                    "avisos": avisos, "erros": erros,
                    "preview_expandido": _preview_expandido(diff)}
        if erros:
            _fechar_silencioso(conn)
            raise HTTPException(status_code=422, detail=erros[0])

        if diff is not None:
            criado_por = None
            if isinstance(_auth, dict):
                criado_por = (str(_auth.get("matricula") or "").strip() or None)
            _aplicar_compilacao(cur, diff, criado_por)
        for item in efeito_ag:
            _desligar_raiz(cur, item["pipeline"])
        cur.execute("DELETE FROM dbo.etl_malha_aresta "
                    "WHERE id = ? AND malha_name = ?", (aresta_id, malha))
        if (cur.rowcount or 0) == 0:
            _fechar_silencioso(conn)
            raise HTTPException(
                status_code=404,
                detail=f"Aresta {aresta_id} não existe na malha '{malha}'")
        avisos = _avisos_gesto(nos_l, prospectivas, diff)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "avisos": avisos,
                "efeito": _mesclar_efeito_agenda(_efeito_publico(diff),
                                                 efeito_ag, republicar_ag)}
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
    executa, quem avisa é a tela.

    F11 (Decisão 4): linha ASSINADA (compilada por Aguarde de malha) é recusada
    com 422 nomeando malha e nó donos — apagá-la por aqui deixaria o desenho da
    malha dona contando uma história e o motor outra (e o Aguarde dela a
    recriaria... ou nunca). A porta certa é o desenho da malha."""
    nome_dep = (body.get("pipeline_name") or "").strip()
    nome_pred = (body.get("depende_de") or "").strip()
    if not nome_dep or not nome_pred:
        raise HTTPException(status_code=422,
                            detail="pipeline_name e depende_de são obrigatórios")
    conn = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _exigir_tabela_067(cur, conn)
        if _coluna_origem_no(cur):
            ass = deps_svc.assinatura(cur, nome_dep, nome_pred)
            if ass is not None:
                _fechar_silencioso(conn)
                raise HTTPException(
                    status_code=422,
                    detail=deps_svc.msg_linha_assinada(
                        nome_dep, nome_pred, ass["malha"], ass["origem_no"]))
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
