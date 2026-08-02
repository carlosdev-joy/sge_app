"""
Testes da validação/normalização do nó Aguarde no backend
(_validate_aguarde/_normalize_aguarde em api/routers/jobs.py).

Funções puras (não tocam banco) — importadas via fixture, como nos vizinhos.

O nó Aguarde é o ponto de encontro entre pernas paralelas (migration 068).
A política decide a trigger rule que o dag_factory vai emitir, então um valor
fora do domínio precisa ser REJEITADO — aceitar em silêncio produziria uma DAG
com semântica que ninguém pediu.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


# ── Validação ────────────────────────────────────────────────────────────────

def test_config_ausente_e_aceita(J):
    """Sem config o nó é válido — degrada para o default na normalização."""
    assert J._validate_aguarde(None) == []


def test_dict_vazio_e_aceito(J):
    assert J._validate_aguarde({}) == []


def test_nao_dict_invalido(J):
    assert J._validate_aguarde("todas_sucesso")


def test_politica_todas_sucesso_ok(J):
    assert J._validate_aguarde({"politica": "todas_sucesso"}) == []


def test_politica_todas_terminarem_ok(J):
    assert J._validate_aguarde({"politica": "todas_terminarem"}) == []


def test_politica_desconhecida_rejeitada(J):
    errs = J._validate_aguarde({"politica": "quando_der"})
    assert any("política do nó Aguarde inválida" in e for e in errs)


def test_politica_vazia_e_aceita(J):
    """String vazia não é erro — cai no default conservador."""
    assert J._validate_aguarde({"politica": "  "}) == []


# ── Normalização ─────────────────────────────────────────────────────────────

def test_normaliza_ausente_para_conservador(J):
    assert J._normalize_aguarde(None) == {"politica": "todas_sucesso"}


def test_normaliza_invalida_para_conservador(J):
    """Ninguém herda 'segue mesmo com falha' por acidente."""
    assert J._normalize_aguarde({"politica": "quando_der"}) == {"politica": "todas_sucesso"}


def test_normaliza_nao_dict_para_conservador(J):
    assert J._normalize_aguarde("x") == {"politica": "todas_sucesso"}


def test_normaliza_preserva_todas_terminarem(J):
    assert J._normalize_aguarde({"politica": "todas_terminarem"}) == {"politica": "todas_terminarem"}


def test_normaliza_case_e_espaco(J):
    assert J._normalize_aguarde({"politica": "  Todas_Terminarem "}) == {"politica": "todas_terminarem"}


def test_normaliza_sempre_tem_a_chave(J):
    """A chave 'politica' é o contrato do round-trip com o painel e do factory."""
    for cfg in (None, {}, {"politica": "lixo"}, {"outra": 1}):
        assert "politica" in J._normalize_aguarde(cfg)


def test_normaliza_descarta_chaves_estranhas(J):
    out = J._normalize_aguarde({"politica": "todas_sucesso", "timeout": 3600})
    assert out == {"politica": "todas_sucesso"}


# ── Round-trip (o defeito que derrubou a spec de dependências) ───────────────

def test_round_trip_nao_perde_a_politica(J):
    """Normalizar o que já foi normalizado não muda nada.

    Na spec de dependências entre pipelines, três campos eram gravados e nunca
    lidos de volta — resultado: todo save zerava os três. Aqui a saída da
    normalização precisa ser ponto fixo, senão um segundo save de um Aguarde
    'todas_terminarem' o rebaixaria para o default e a limpeza pararia de rodar.
    """
    for politica in ("todas_sucesso", "todas_terminarem"):
        uma_vez = J._normalize_aguarde({"politica": politica})
        assert J._normalize_aguarde(uma_vez) == uma_vez
        assert uma_vez["politica"] == politica


# ── Tipo aceito no fluxo ─────────────────────────────────────────────────────

def test_aguarde_e_tipo_valido(J):
    assert "aguarde" in J.VALID_JOB_TYPES


def test_tipos_anteriores_preservados(J):
    """Não-regressão: a 068 só ADICIONA um tipo."""
    assert {"datastage", "shell", "python", "storedproc", "http",
            "decisao", "notificacao", "sql"} <= J.VALID_JOB_TYPES
