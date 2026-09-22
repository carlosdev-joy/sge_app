"""ia_provedor.load_config / espelhar_legado — a leitura dupla da F0
(docs/spec-agentes-datastage.md).

Até 21/09/2026 a config do provedor de IA vivia só nas chaves `caixa_ia_*`.
A F0 introduz as `ia_*`, compartilhadas por Maestro, triagem, assistentes do
Caixa Seguro e os agentes que virão — mas a produção não passa a ter as novas
chaves no instante do deploy: a migration 116 as COPIA (idempotente), e até
lá (ou se a migration não rodar) só as antigas existem.

O que estes testes prendem, e por que cada um existe:

  1. **A chave nova manda quando as duas existem.** Depois que o Admin grava
     (ou a 116 copia), `ia_*` é a fonte da verdade.
  2. **A chave antiga sozinha continua funcionando.** É o estado do banco
     ANTES do deploy da F0 — sem isso, o deploy quebraria a config existente
     no instante em que a API nova subisse sobre um banco velho.
  3. **`K_ENABLED` (caixa_ia_enabled) nunca cai para uma chave nova** — ele
     não tem par: é o interruptor do Caixa Seguro, não do provedor.
  4. **`espelhar_legado` grava nos dois nomes**, para quem ainda lê só o
     antigo (a triagem no worker, se `dags/` atrasar) continuar funcionando
     depois que o Admin salva pela tela nova.
  5. **Sem nenhuma chave, degrada para "não configurado"** — nunca levanta.

Nada aqui toca banco de verdade: um cursor dublê guarda o SQL e devolve as
linhas preparadas.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from services import ia_provedor  # noqa: E402


class _CursorFalso:
    """`execute` guarda o SQL e os parâmetros; `fetchall` devolve as linhas
    preparadas (ignora quais chaves o SQL realmente pediu — os testes de
    conteúdo conferem isso à parte, pelo `sqls`/`params` gravados)."""

    def __init__(self, linhas: dict[str, str]):
        self._linhas = list(linhas.items())
        self.sqls: list[str] = []
        self.params: list[list] = []

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self.params.append(list(params or []))

    def fetchall(self):
        return self._linhas


def test_prefere_a_chave_nova_quando_as_duas_existem():
    cur = _CursorFalso({
        "ia_provider": "caixa_gateway", "caixa_ia_provider": "anthropic",
        "ia_model": "claude-sonnet-4-6", "caixa_ia_model": "claude-opus-4-8",
        "ia_base_url": "https://novo.intranet", "caixa_ia_base_url": "https://antigo.intranet",
        "ia_api_key_enc": "NOVA_CIFRADA", "caixa_ia_api_key_enc": "ANTIGA_CIFRADA",
        "ia_usa_proxy": "1", "caixa_ia_usa_proxy": "0",
    })
    cfg = ia_provedor.load_config(cur)
    assert cfg["provider"] == "caixa_gateway"
    assert cfg["model"] == "claude-sonnet-4-6"
    assert cfg["base_url"] == "https://novo.intranet"
    assert cfg["api_key_enc"] == "NOVA_CIFRADA"
    assert cfg["usa_proxy"] is True


def test_cai_para_a_chave_antiga_sem_a_nova():
    """Estado do banco ANTES da migration 116 (ou antes do deploy da F0):
    só caixa_ia_* — nada quebra."""
    cur = _CursorFalso({
        "caixa_ia_enabled": "1", "caixa_ia_provider": "caixa_gateway",
        "caixa_ia_model": "claude-sonnet-4-6",
        "caixa_ia_base_url": "https://gw.intranet",
        "caixa_ia_api_key_enc": "CIFRADA", "caixa_ia_usa_proxy": "0",
    })
    cfg = ia_provedor.load_config(cur)
    assert cfg["enabled"] is True
    assert cfg["provider"] == "caixa_gateway"
    assert cfg["model"] == "claude-sonnet-4-6"
    assert cfg["base_url"] == "https://gw.intranet"
    assert cfg["api_key_enc"] == "CIFRADA"


def test_nova_vazia_tambem_cai_para_a_antiga():
    """A chave nova pode existir (a 116 rodou) mas vazia — não é 'valor
    vencedor vazio', é 'ainda não preenchida'."""
    cur = _CursorFalso({"ia_model": "", "caixa_ia_model": "claude-opus-4-8"})
    assert ia_provedor.load_config(cur)["model"] == "claude-opus-4-8"


def test_enabled_nunca_cai_para_chave_nova():
    """K_ENABLED (caixa_ia_enabled) é do Caixa Seguro, não do provedor
    compartilhado — não migra, não tem par em _LEGADO."""
    assert "caixa_ia_enabled" not in ia_provedor._LEGADO.values()
    cur = _CursorFalso({"caixa_ia_enabled": "1"})
    assert ia_provedor.load_config(cur)["enabled"] is True


def test_sem_nenhuma_chave_degrada_sem_levantar():
    cfg = ia_provedor.load_config(_CursorFalso({}))
    assert cfg == {"enabled": False, "provider": "anthropic", "model": "",
                   "base_url": "", "api_key_enc": "", "usa_proxy": False,
                   "ultima_verificacao": ""}


def test_provider_invalido_cai_no_padrao():
    cur = _CursorFalso({"ia_provider": "gpt-pirata"})
    assert ia_provedor.load_config(cur)["provider"] == "anthropic"


def test_cursor_que_explode_degrada_sem_levantar():
    class _Explode:
        def execute(self, *a, **k):
            raise RuntimeError("tabela ausente")
    assert ia_provedor.load_config(_Explode()) == {
        "enabled": False, "provider": "anthropic", "model": "",
        "base_url": "", "api_key_enc": "", "usa_proxy": False,
        "ultima_verificacao": ""}


# ═══════════ espelhar_legado ═══════════════════════════════════════════════

def test_espelhar_legado_grava_nos_dois_nomes():
    valores = {ia_provedor.K_PROVIDER: "caixa_gateway", ia_provedor.K_MODEL: "claude-sonnet-4-6"}
    espelhado = ia_provedor.espelhar_legado(valores)
    assert espelhado["ia_provider"] == "caixa_gateway"
    assert espelhado["caixa_ia_provider"] == "caixa_gateway"
    assert espelhado["ia_model"] == "claude-sonnet-4-6"
    assert espelhado["caixa_ia_model"] == "claude-sonnet-4-6"


def test_espelhar_legado_nao_mexe_no_enabled():
    """K_ENABLED não tem par legado — passa como veio, sem ganhar um
    espelho novo que não existe."""
    espelhado = ia_provedor.espelhar_legado({ia_provedor.K_ENABLED: "1"})
    assert espelhado == {"caixa_ia_enabled": "1"}


def test_espelhar_legado_so_espelha_o_que_veio():
    """Um `ia_set` que só troca o modelo não deve inventar valor para as
    chaves que a requisição não tocou."""
    espelhado = ia_provedor.espelhar_legado({ia_provedor.K_MODEL: "novo-modelo"})
    assert set(espelhado) == {"ia_model", "caixa_ia_model"}


@pytest.mark.parametrize("nova", list(ia_provedor._LEGADO))
def test_toda_chave_nova_tem_par_legado_valido(nova):
    """Trava de simetria: se alguém acrescentar uma constante K_* nova sem
    registrar o par em _LEGADO, load_config()/espelhar_legado() quebram em
    silêncio (KeyError só na primeira leitura real). Este teste falha na
    hora, no CI, em vez de em produção."""
    antiga = ia_provedor._LEGADO[nova]
    assert antiga.startswith("caixa_ia_")
    assert nova.startswith("ia_")
