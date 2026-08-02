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


def faltantes(cur, pipeline: str, data_ref: date) -> list:
    """Predecessores de `pipeline` SEM SUCESSO em `data_ref`.

    Port EXATO do SELECT de dags/utils/dependencias.liberado() (só o
    placeholder muda, %s→?): NOT EXISTS(... status='SUCESSO' na data) por
    predecessor — FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em OUTRA data
    contam como faltando (D20); PULADO intercalado não mascara um SUCESSO
    existente (D14). Exceção PROPAGA — a tradução D21 fica em `liberado()`.
    """
    cur.execute(
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
