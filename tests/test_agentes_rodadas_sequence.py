"""Ajuste feito em produção em 23/09/2026 (commit 3bf0565 da branch
`feat/agente-datastage-melhorias`), portado para o próximo deploy não o
desfazer:

  • `MAX_RODADAS_FERRAMENTA` 3 → 4: resolver_projeto → (uma intermediária) →
    isx_extrair → resposta cabe numa pergunta;
  • prompt: para os filhos de uma sequence, ir DIRETO ao isx_extrair (sem
    dsjob antes, que gastava uma rodada e não traz os filhos).

A 4ª rodada não afrouxa o teto de tempo: o orçamento de 240 s é por RELÓGIO.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402


def test_quatro_rodadas_de_ferramenta_por_pergunta():
    assert svc.MAX_RODADAS_FERRAMENTA == 4


def test_prompt_manda_ir_direto_ao_isx_para_filhos_de_sequence():
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert "vá DIRETO ao isx_extrair — NÃO chame dsjob antes" in p


@pytest.mark.asyncio
async def test_quarta_rodada_ainda_respeita_o_teto_de_tempo(monkeypatch):
    """Com o relógio além do orçamento, a rodada para — por mais rodadas que
    o limite de contagem ainda permitisse."""
    agora = {"t": 0.0}
    monkeypatch.setattr(svc.time, "monotonic", lambda: agora["t"])
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda n: False)
    chamadas = []

    async def _provedor(cfg, sistema, historico, identidade=None, campo_identidade=None):
        chamadas.append(1)
        agora["t"] += 100  # cada ida ao gateway "leva" 100 s
        return '```json\n' + json.dumps({"ferramenta": "base", "args": {"job_name": "J"}}) + '\n```', "m"
    monkeypatch.setattr(ia_provedor, "chat_conversa", _provedor)
    monkeypatch.setattr(af, "ferramenta_base", lambda cur, p, j: {"encontrado": False})

    def _abrir():
        c = MagicMock()
        c.fetchall.return_value = []
        return c, c
    r = await svc.conversar(_abrir, mensagens=[{"role": "user", "content": "oi"}], projeto_atual="P",
                            provedor_cfg={}, identidade="x", campo_identidade=None, ssh_max=10)
    assert r["status"] == "tempo_esgotado"
    assert len(chamadas) < svc.MAX_RODADAS_FERRAMENTA + 1
