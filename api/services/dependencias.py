"""
api/services/dependencias.py — o predicado de liberação por dependência, visto
da API (F5 da retomada, D29).

PORT de dags/utils/dependencias.py — **o canônico é o de dags/**: quem mudar a
regra muda lá primeiro e espelha aqui. A cópia existe pelo mesmo motivo de
api/services/data_referencia.py (F9): api/ e dags/ são árvores de deploy
separadas, e um import cruzado quebraria no primeiro deploy parcial. A paridade
é garantida por teste em DOIS níveis (tests/test_dependencias_f5_paridade.py):
o SQL capturado tem de ser IDÊNTICO ao do canônico (normalizado %s→?) e a
matriz semântica D14/D20/D21 tem de dar o MESMO resultado nas duas árvores.

Placeholder `?` (pyodbc — árvore api/); em dags/ é `%s` (pymssql). Trocar dá
"Incorrect syntax near '?'" com task verde — o GOTCHA registrado do projeto.

CONTRATO DE LEITURA (F2 §9): a liberação é
    EXISTS(pipeline=P AND data_referencia=D AND status='SUCESSO')
— nunca "linha mais recente", nunca COALESCE(inicio, criado_em), nenhuma
ordenação por criado_em em lugar nenhum deste módulo (D14, D15). Foi
exatamente o `TOP 1 ... ORDER BY COALESCE(inicio, criado_em)` do endpoint da
1ª F5 que fez o painel divergir do motor (B2/D14/D15/N9).

Este módulo NUNCA decide disparo: `liberado()` aqui é LEITURA para painel e
tooltip — quem dispara continua sendo o push/guardiã em dags/. Todas as
funções recebem `cur` (cursor aberto) e o CHAMADOR é dono da transação.
"""
from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger("orquestra-api")

# Sentinel de "não consegui perguntar" (≠ "condição não fechou") — o MESMO do
# canônico: erro de consulta nunca vira "pode disparar" (D21).
ERRO_CONSULTA = "erro na consulta:"


# Marca da migration 078 e fallback — o MESMO recurso do canônico de dags/
# (`_MARCA_078`/`_exec_com_fallback_078`), portado para cá pela regra de
# paridade: o predicado emite UMA consulta só, e ela tem de ser textualmente
# igual à do motor (o teste de paridade conta as chamadas). Um probe de coluna
# aqui gastaria uma consulta a mais e quebraria essa contagem.
_MARCA_078 = "substituida_em"


def _exec_com_fallback_078(cur, sql_078: str, sql_legado: str, params) -> bool:
    """Executa `sql_078`; se o banco ainda não tem a coluna da 078, repete com
    `sql_legado`. True = caiu no legado. Qualquer outro erro PROPAGA (a
    tradução D21 é de `liberado()`)."""
    try:
        cur.execute(sql_078, params)
        return False
    except Exception as e:  # noqa: BLE001 — reagimos SÓ ao Invalid column name da 078
        if _MARCA_078 not in str(e):
            raise
        cur.execute(sql_legado, params)
        return True


def faltantes(cur, pipeline: str, data_ref: date) -> list:
    """Predecessores de `pipeline` SEM SUCESSO VIVO em `data_ref`.

    Port EXATO do SELECT de dags/utils/dependencias.liberado() (só o
    placeholder muda, %s→?): NOT EXISTS(... status='SUCESSO' na data) por
    predecessor — FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em OUTRA data
    contam como faltando (D20); PULADO intercalado não mascara um SUCESSO
    existente (D14). Exceção PROPAGA — a tradução D21 fica em `liberado()`.

    Corrida com `substituida_em` (078) NÃO conta como SUCESSO — a correção da
    terceira porta do modelo de corrida, feita primeiro no canônico. O painel
    tem de contar a MESMA história do motor: com o dependente reaberto pela
    cascata, "aguardando o predecessor" é a verdade dos dois lados.
    """
    _exec_com_fallback_078(
        cur,
        "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
        "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE' "
        "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
        "WHERE e.pipeline_name = dd.depende_de "
        "AND e.data_referencia = ? AND e.status = 'SUCESSO' "
        "AND e.substituida_em IS NULL)",
        "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
        "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE' "
        "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
        "WHERE e.pipeline_name = dd.depende_de "
        "AND e.data_referencia = ? AND e.status = 'SUCESSO')",
        (pipeline, data_ref))
    return [r[0] for r in cur.fetchall()]


def liberado(cur, pipeline: str, data_ref: date):
    """Todos os predecessores de `pipeline` têm SUCESSO em `data_ref`?

    Devolve (liberado, faltantes) — a MESMA pergunta e a MESMA resposta do
    canônico de dags/. Qualquer exceção na consulta → NÃO liberado, com o
    sentinel ERRO_CONSULTA embutido nos faltantes (D21: erro nunca vira
    "pode disparar" — nem no painel).
    """
    try:
        falta = faltantes(cur, pipeline, data_ref)
        return (not falta), falta
    except Exception as e:  # noqa: BLE001 — D21: erro é NÃO liberado, nunca silêncio
        log.warning("[DEP] condicao de %s indisponivel (%s) — tratada como NAO liberada",
                    pipeline, e)
        return False, [f"{ERRO_CONSULTA} {e}"[:200]]


def resumo_predecessores(cur, pipeline: str, data_ref: date) -> dict:
    """Status por predecessor na data — {predecessor: {status, ...}};
    predecessor sem linha na data aparece com set VAZIO.

    SÓ para exibição e mensagem — NUNCA decide liberação: a pergunta de
    liberação é exclusivamente `liberado()` (proteção do D29, a mesma
    docstring do canônico da F4).
    """
    cur.execute(
        "SELECT dd.depende_de, e.status "
        "FROM dbo.etl_pipeline_dependencia dd "
        "LEFT JOIN dbo.etl_pipeline_execucao e "
        "ON e.pipeline_name = dd.depende_de AND e.data_referencia = ? "
        "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE'",
        (data_ref, pipeline))
    resumo: dict = {}
    for pred, status in cur.fetchall():
        resumo.setdefault(pred, set())
        if status is not None:
            resumo[pred].add(status)
    return resumo


def mais_recente_da_data(linhas):
    """A execução MAIS RECENTE entre `linhas` — a regra F9 (§6 risco 6 da
    spec), extraída de get_malha_execucao: vence a chave
    (inicio is not None, inicio, execution_id) — linha ainda sem inicio
    (AGUARDANDO_DEPENDENCIA) perde de qualquer linha iniciada; empate de
    inicio desempata por execution_id. NENHUMA menção a criado_em (D15).

    `linhas`: iterável de dicts com ao menos {"inicio", "execution_id"}.
    Devolve o dict vencedor, ou None se a sequência for vazia.
    """
    vencedora, chave_v = None, None
    for linha in linhas:
        chave = (linha.get("inicio") is not None, linha.get("inicio"),
                 str(linha.get("execution_id") or ""))
        if chave_v is None or chave > chave_v:
            vencedora, chave_v = linha, chave
    return vencedora


def virada_global(cur):
    """Valor CRU de etl_app_config['dependencia_hora_virada'] (a hora de virada
    GLOBAL do ODATE — mesma chave que dags/ lê), ou None se ausente/ilegível.
    O parse tolerante fica em services.data_referencia: config quebrado degrada
    para a virada padrão 00:00, nunca derruba a tela. (Extraído de malhas.py —
    reusado pelos dois routers.)"""
    try:
        cur.execute(
            "SELECT config_value FROM dbo.etl_app_config WHERE config_key = ?",
            ("dependencia_hora_virada",))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        log.warning("[DEP] leitura de dependencia_hora_virada falhou: %s", e)
        return None


def tabela_067(cur) -> bool:
    """True se etl_pipeline_dependencia (migration 067) existe. Uma consulta
    por request, para o deploy parcial degradar em vez de estourar
    'Invalid object name'. (Extraída de malhas.py — reusada pelos dois
    routers.)"""
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_pipeline_dependencia', 'U')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[DEP] checagem da tabela da migration 067 falhou: %s", e)
        return False


# ── Assinatura de proveniência (F11 — origem_no da migration 075) ────────────
# Helpers EXCLUSIVOS da árvore api/ (não são port de dags/): a assinatura é
# proteção de ESCRITA (Decisão 4 do desenho de componentes — linha compilada
# só se mexe pela malha dona) e o motor nunca a lê — `liberado()` continua
# ignorando origem_no. Vivem aqui porque as TRÊS portas precisam da mesma
# resposta e da MESMA mensagem: DELETE /dependencias (routers/malhas.py),
# _gravar_dependencias do register (routers/pipelines.py) e o estado do modal
# F5 (GET /pipelines/dependencias/estado) — e pipelines.py não pode importar
# malhas.py (ciclo).

def coluna_origem_no(cur) -> bool:
    """True se etl_pipeline_dependencia.origem_no (migration 075) existe.
    Best-effort no padrão dos guards de coluna (073/074): qualquer falha conta
    como ausente e as portas se comportam como antes da F11."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline_dependencia', 'origem_no')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[DEP] checagem da coluna origem_no da migration 075 falhou: %s", e)
        return False


def assinatura(cur, pipeline: str, depende_de: str):
    """Assinatura da linha (pipeline, depende_de, PIPELINE) na 067:
    {"origem_no": id, "malha": nome} se ela foi COMPILADA por um nó de malha,
    None se é manual ou não existe. Chamar só com coluna_origem_no True."""
    cur.execute(
        "SELECT d.origem_no, n.malha_name "
        "FROM dbo.etl_pipeline_dependencia d "
        "LEFT JOIN dbo.etl_malha_no n ON n.id = d.origem_no "
        "WHERE d.pipeline_name = ? AND d.depende_de = ? AND d.tipo = 'PIPELINE'",
        (pipeline, depende_de))
    row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return {"origem_no": int(row[0]),
            "malha": (str(row[1]).strip() if row[1] else None)}


def linhas_assinadas(cur, pipeline: str) -> dict:
    """Linhas ASSINADAS do dependente: {casefold(depende_de): {"depende_de",
    "origem_no", "malha"}}. É o que o replace-all do register consulta ANTES
    do DELETE — remover uma delas por lá é 422 (Decisão 4), mantê-la na lista
    preserva a assinatura intacta (nunca re-gravada sem origem_no)."""
    cur.execute(
        "SELECT d.depende_de, d.origem_no, n.malha_name "
        "FROM dbo.etl_pipeline_dependencia d "
        "LEFT JOIN dbo.etl_malha_no n ON n.id = d.origem_no "
        "WHERE d.pipeline_name = ? AND d.tipo = 'PIPELINE' "
        "AND d.origem_no IS NOT NULL",
        (pipeline,))
    out = {}
    for r in cur.fetchall():
        dep = str(r[0] or "").strip()
        out[dep.casefold()] = {
            "depende_de": dep,
            "origem_no": int(r[1]),
            "malha": (str(r[2]).strip() if r[2] else None)}
    return out


def msg_linha_assinada(pipeline, depende_de, malha, origem_no) -> str:
    """Mensagem ÚNICA das três portas (Decisão 4): nomeia malha e nó donos e
    instrui a porta certa. Texto compartilhado de propósito — divergir entre
    as portas recriaria a classe cliente≠servidor que a F8 matou."""
    return (f"A dependência '{pipeline}' → '{depende_de}' é compilada pelo "
            f"Aguarde #{origem_no} da malha '{malha}' — edite pelo desenho da "
            "malha (linha assinada só se mexe pela malha dona).")
