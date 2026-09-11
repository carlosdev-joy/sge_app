"""Destinatários de e-mail do FLUXO (`etl_pipeline.email_destinatarios`,
migration 111) no cadastro de pipelines — F2 da spec de notificação por e-mail.

Estes testes são ESTRUTURAIS (leitura do código com `ast`/regex), no mesmo
espírito da varredura de rotas em tests/test_email_admin.py. Montar um dublê do
`register` inteiro custaria mais do que vale: o que precisa ficar preso aqui são
três decisões que a revisão adversarial pegou, e todas são visíveis no texto do
módulo.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
for _p in (str(_ROOT / "api"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FONTE = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def P():
    from routers import pipelines
    return pipelines


def test_a_gravacao_nao_fica_no_try_que_engole_excecao():
    """⛔ Âncora. O bloco das colunas da 017 termina em `except Exception: pass`.
    Com a gravação da lista lá dentro, duas coisas quebravam de uma vez:

      1. o 503 "aplique a migration 111" era ENGOLIDO — a tela dizia "salvo"
         sem ter gravado nada;
      2. a exceção abortava o bloco antes do UPDATE da 017, e como o front
         manda `email_destinatarios` em TODO save, `calendario_nome`,
         `somente_dias_uteis` e `trigger_por_dependencia` deixavam de ser
         gravados em qualquer pipeline, mesmo sem nó de e-mail.
    """
    arvore = ast.parse(FONTE)
    fontes_de_try_engolidor = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Try):
            continue
        engole = any(
            isinstance(h.body[0], ast.Pass) and len(h.body) == 1 and
            (h.type is None or getattr(h.type, "id", "") == "Exception")
            for h in no.handlers if h.body)
        if engole:
            fontes_de_try_engolidor.append(ast.unparse(no))
    assert fontes_de_try_engolidor, "o try com `except Exception: pass` sumiu — reveja este teste"
    for trecho in fontes_de_try_engolidor:
        assert "email_destinatarios=?" not in trecho, (
            "a gravação de email_destinatarios voltou para dentro de um "
            "`try/except Exception: pass` — o 503 seria engolido")


def test_a_regua_de_dominios_vale_para_a_lista_do_fluxo():
    """⛔ Âncora. Sem a allowlist aqui, um endereço de domínio barrado entra na
    lista do fluxo; todo nó com "incluir os destinatários do fluxo" (o default)
    o herda; e a task de e-mail falha em TODA corrida, longe de quem digitou."""
    arvore = ast.parse(FONTE)
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "validar_destinatarios"
                and "email_destinatarios" in ast.unparse(n)]
    assert chamadas, "a validação dos destinatários do fluxo sumiu"
    for c in chamadas:
        assert len(c.args) >= 2, (
            "validar_destinatarios da lista do fluxo precisa receber os domínios "
            f"permitidos do Admin; hoje: {ast.unparse(c)}")


def test_mudanca_de_destinatarios_deixa_rastro(P):
    """Mudar quem recebe aviso de produção é gesto auditável."""
    assert "email_destinatarios" in P.AUDIT_FIELDS


def test_o_registro_anterior_le_a_coluna_para_o_diff(P):
    """Sem a coluna na fotografia do "antes", a auditoria registraria toda
    gravação como "vazio → lista" (ou nada)."""
    fonte_leitura = FONTE[FONTE.index("def _read_pipeline_record"):]
    fonte_leitura = fonte_leitura[:fonte_leitura.index("\ndef ", 10)]
    assert "email_destinatarios" in fonte_leitura
    assert "# migration 111" in fonte_leitura


def test_destinatarios_do_fluxo_nao_pedem_republicacao(P):
    """O nó lê a lista em runtime: mudar quem recebe NÃO pode marcar a DAG
    como pendente de publicação (seria pedir republicação à toa)."""
    assert "email_destinatarios" not in P.CAMPOS_QUE_AFETAM_DAG
