"""
Envio dos alertas da supervisão ao Teams (dags/utils/ds_teams.py + a etapa de
notificação da DAG).

O que estes testes protegem:

  • **`notificado_em` só depois do 2xx.** Marcar antes trocaria "avisei" por
    "tentei avisar", e o alerta sumiria em silêncio — falha total do propósito
    da feature.
  • **A URL do webhook nunca vaza** para log ou mensagem de erro: ela é
    credencial, quem tem a URL posta no canal.
  • **O card de início do monitoramento é visualmente distinto** dos alertas.
    Se ele saísse vermelho, a operação aprenderia a ignorar a cor.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

from utils.ds_teams import (  # noqa: E402
    ESTILO, enviar_card, montar_card, montar_card_dependencia,
)

WEBHOOK = "https://outlook.office.com/webhook/SEGREDO-abc123"


def _evento(**kw) -> dict:
    base = {
        "id": 1, "tipo": "ABORTOU", "data_ref": "2026-07-27",
        "detalhe": "detalhe técnico",
        "mensagem": "🚨 SeqSsdVida7Peps abortou em 2026-07-27. Início 02:10, parada 02:15.",
        "project": "BI_CVP", "job_name": "SeqSsdVida7Peps",
        "descricao": "Carga diária de vida",
        "janela_inicio": "02:00:00", "janela_fim": "03:00:00",
    }
    base.update(kw)
    return base


def _texto_do_card(card: dict) -> str:
    """Concatena todo texto visível do card, para asserções de conteúdo."""
    corpo = card["attachments"][0]["content"]["body"]
    partes = []
    for bloco in corpo:
        if bloco.get("type") == "TextBlock":
            partes.append(bloco.get("text", ""))
        if bloco.get("type") == "FactSet":
            for f in bloco["facts"]:
                partes.append(f"{f['title']}: {f['value']}")
    return "\n".join(partes)


# ── Estrutura do Adaptive Card ──────────────────────────────────────────────

def test_card_tem_o_envelope_esperado_pelo_teams():
    card = montar_card(_evento())
    anexo = card["attachments"][0]
    assert card["type"] == "message"
    assert anexo["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert anexo["content"]["type"] == "AdaptiveCard"
    assert anexo["content"]["version"] == "1.4"


def test_card_traz_projeto_job_dia_e_janela():
    texto = _texto_do_card(montar_card(_evento()))
    assert "BI_CVP" in texto
    assert "SeqSsdVida7Peps" in texto
    assert "2026-07-27" in texto
    assert "02:00–03:00" in texto            # janela formatada, sem segundos


def test_card_usa_a_mensagem_ja_renderizada():
    texto = _texto_do_card(montar_card(_evento()))
    assert "abortou em 2026-07-27. Início 02:10, parada 02:15." in texto


def test_sem_mensagem_cai_no_detalhe_tecnico():
    texto = _texto_do_card(montar_card(_evento(mensagem=None)))
    assert "detalhe técnico" in texto


def test_evento_incompleto_ainda_gera_card():
    # Card torto é melhor que alerta não enviado.
    card = montar_card({"tipo": "ATRASO"})
    texto = _texto_do_card(card)
    assert "—" in texto                      # campos ausentes viram travessão
    assert card["attachments"][0]["content"]["body"]


# ── Cor e rótulo por tipo ───────────────────────────────────────────────────

@pytest.mark.parametrize("tipo,cor", [
    ("ABORTOU", "Attention"),
    ("NAO_EXECUTOU", "Attention"),
    ("ATRASO", "Warning"),
    ("ESTRUTURA", "Warning"),
    ("SITUACAO_INICIAL", "Good"),
])
def test_cor_do_card_por_tipo(tipo, cor):
    card = montar_card(_evento(tipo=tipo))
    assert card["attachments"][0]["content"]["body"][0]["color"] == cor


def test_inicio_do_monitoramento_nao_parece_alerta():
    inicial = montar_card(_evento(tipo="SITUACAO_INICIAL"))
    alerta = montar_card(_evento(tipo="ABORTOU"))
    cor_inicial = inicial["attachments"][0]["content"]["body"][0]["color"]
    cor_alerta = alerta["attachments"][0]["content"]["body"][0]["color"]
    assert cor_inicial != cor_alerta
    assert cor_inicial == "Good"
    assert "Monitoramento iniciado" in _texto_do_card(inicial)


def test_tipo_desconhecido_nao_quebra_o_card():
    card = montar_card(_evento(tipo="INVENTADO"))
    assert card["attachments"][0]["content"]["body"][0]["color"] == "Warning"


def test_todo_tipo_conhecido_tem_estilo():
    for tipo in ("ABORTOU", "NAO_EXECUTOU", "ATRASO", "ESTRUTURA", "SITUACAO_INICIAL"):
        assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])


# ── Envio ───────────────────────────────────────────────────────────────────

class RespostaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code


def _mock_requests(monkeypatch, resposta=None, erro=None):
    modulo = MagicMock()
    if erro is not None:
        modulo.post.side_effect = erro
    else:
        modulo.post.return_value = resposta
    monkeypatch.setitem(sys.modules, "requests", modulo)
    return modulo


def test_webhook_vazio_nao_tenta_enviar(monkeypatch):
    mod = _mock_requests(monkeypatch, RespostaFalsa(200))
    ok, motivo = enviar_card("   ", {"a": 1})
    assert ok is False
    assert "sem webhook" in motivo
    mod.post.assert_not_called()


@pytest.mark.parametrize("status", [200, 201, 202, 204])
def test_2xx_autoriza_marcar_como_notificado(monkeypatch, status):
    _mock_requests(monkeypatch, RespostaFalsa(status))
    ok, motivo = enviar_card(WEBHOOK, {"a": 1})
    assert ok is True
    assert str(status) in motivo


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
def test_erro_http_nao_autoriza_marcar(monkeypatch, status):
    _mock_requests(monkeypatch, RespostaFalsa(status))
    ok, motivo = enviar_card(WEBHOOK, {"a": 1})
    assert ok is False
    assert str(status) in motivo


def test_falha_de_rede_nao_propaga_excecao(monkeypatch):
    _mock_requests(monkeypatch, erro=TimeoutError("timeout"))
    ok, motivo = enviar_card(WEBHOOK, {"a": 1})
    assert ok is False
    assert "TimeoutError" in motivo


@pytest.mark.parametrize("cenario", ["http", "rede", "vazio"])
def test_url_do_webhook_nunca_aparece_no_motivo(monkeypatch, cenario):
    if cenario == "http":
        _mock_requests(monkeypatch, RespostaFalsa(500))
        _ok, motivo = enviar_card(WEBHOOK, {})
    elif cenario == "rede":
        _mock_requests(monkeypatch, erro=ValueError(f"falhou ao chamar {WEBHOOK}"))
        _ok, motivo = enviar_card(WEBHOOK, {})
    else:
        _ok, motivo = enviar_card("", {})
    assert "SEGREDO" not in motivo
    assert "outlook.office.com" not in motivo


def test_card_e_enviado_como_json(monkeypatch):
    mod = _mock_requests(monkeypatch, RespostaFalsa(200))
    card = montar_card(_evento())
    enviar_card(WEBHOOK, card)
    _args, kwargs = mod.post.call_args
    assert kwargs["json"] == card
    assert kwargs["timeout"] == 15


# ── Card de dependência entre pipelines (F4 — guardiã) ──────────────────────

def _evento_dep(**kw) -> dict:
    base = {"id": 9, "tipo": "JANELA_ESTOUROU", "pipeline": "PIPE_C",
            "data_ref": "2026-08-01", "detalhe": "aguardando: PIPE_A",
            "detectado_em": "2026-08-01 08:05:00"}
    base.update(kw)
    return base


@pytest.mark.parametrize("tipo,cor", [
    ("JANELA_ESTOUROU", "Warning"),
    ("DATA_DIVERGENTE", "Warning"),
    ("PREDECESSOR_FALHOU", "Attention"),
    ("NAO_LIBEROU", "Attention"),
])
def test_card_de_dependencia_por_tipo(tipo, cor):
    """Os 4 tipos da guardiã têm estilo próprio no ESTILO (F4 §8)."""
    card = montar_card_dependencia(_evento_dep(tipo=tipo))
    assert card["attachments"][0]["content"]["body"][0]["color"] == cor
    assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])


def test_card_de_dependencia_traz_pipeline_data_e_detalhe():
    texto = _texto_do_card(montar_card_dependencia(_evento_dep()))
    assert "PIPE_C" in texto
    assert "2026-08-01" in texto
    assert "aguardando: PIPE_A" in texto        # o detalhe É o corpo
    assert "Detectado em: 2026-08-01 08:05:00" in texto


def test_card_de_dependencia_incompleto_ainda_sai():
    # Card torto é melhor que alerta não enviado (mesma regra do canal).
    card = montar_card_dependencia({"tipo": "NAO_LIBEROU"})
    assert "—" in _texto_do_card(card)
    assert card["attachments"][0]["content"]["body"]


def test_card_de_dependencia_no_mesmo_envelope_do_canal():
    card = montar_card_dependencia(_evento_dep())
    anexo = card["attachments"][0]
    assert card["type"] == "message"
    assert anexo["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert anexo["content"]["version"] == "1.4"


@pytest.mark.parametrize("tipo,rotulo", [
    ("MALHA_NOTIFICACAO", "Notificação da malha"),
    ("MALHA_CONCLUIDA", "Malha concluída"),
])
def test_card_dos_observadores_de_malha_tem_tom_positivo(tipo, rotulo):
    """F14 (Decisão 14): os 2 tipos novos são de CONCLUSÃO — cor Good, como o
    SITUACAO_INICIAL; vermelho aqui ensinaria a operação a ignorar a cor. O
    envelope é o MESMO montar_card_dependencia (pipeline = marcador #no:{id})."""
    card = montar_card_dependencia(_evento_dep(tipo=tipo, pipeline="#no:9"))
    corpo = card["attachments"][0]["content"]["body"]
    assert corpo[0]["color"] == "Good"
    assert rotulo in corpo[0]["text"]
    assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])
    assert "#no:9" in _texto_do_card(card)
