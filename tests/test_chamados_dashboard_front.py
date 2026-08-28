"""Os cálculos do painel de chamados — prazo, contagens e leitura dos blocos.

A aba Dashboard que roda em produção está **quebrada**: o `DshPanel` foi
injetado à mão num bundle (`index-CeXrH6tU.js`) que um rebuild posterior deixou
órfão, e o `index.html` passou a carregar outro. O que sobrou é o componente do
fonte, que lê `d.backlog` como número enquanto a rota devolve
`{label, cor, total, chamados}` — objeto como filho não renderiza.

O que estes testes prendem:

  1. **A aritmética do prazo.** Erra em silêncio: "faltam 2 dias" para quem
     venceu ontem é plausível demais para alguém desconfiar. A data de hoje é
     INJETADA — sem isso o teste passaria hoje e falharia amanhã.
  2. **Hora do dia não decide.** Um prazo de hoje às 09:00 não está atrasado às
     14:00: vence hoje, e é isso que o operador precisa ler.
  3. **"Sem prazo" é categoria própria.** Somado a "dentro do prazo", o gráfico
     diria que está tudo sob controle quando ninguém combinou data.
  4. **Chamado finalizado não mostra prazo.** "Vencido há 40 dias" num
     resolvido é ruído que ensina a ignorar o aviso.
  5. **Bloco que chega como número devolve `null`** — é exatamente a forma do
     defeito que está em produção.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "dashboard_chamados_harness.cjs"
FONTE = RAIZ / "ui-react" / "src" / "lib" / "dashboardChamados.ts"
TELA = RAIZ / "ui-react" / "src" / "pages" / "ChamadosDashboard.tsx"
CHAMADOS = RAIZ / "ui-react" / "src" / "pages" / "Chamados.tsx"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente)")


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. dias até o prazo ════════════════════════════════════════════

def test_o_sinal_dos_dias_nao_se_inverte(cen: dict) -> None:
    """Positivo é ATRASO. Trocar o sinal pinta de verde quem venceu."""
    assert cen["venceu_ontem"] == 1
    assert cen["vence_hoje"] == 0
    assert cen["vence_amanha"] == -1


def test_a_hora_do_dia_nao_decide_o_atraso(cen: dict) -> None:
    """Prazo de hoje às 09:00 vence HOJE, não venceu."""
    assert cen["hoje_com_hora"] == 0


def test_sem_prazo_e_ausencia_e_nao_zero(cen: dict) -> None:
    """Zero significaria "vence hoje" e pintaria de laranja a fila inteira."""
    assert cen["sem_prazo"] is None
    assert cen["prazo_vazio"] is None
    assert cen["prazo_ilegivel"] is None


# ═══════════ 2. o prazo em palavras ═════════════════════════════════════════

def test_o_rotulo_diz_o_que_a_cor_diria(cen: dict) -> None:
    """Cor sozinha não informa quem não a distingue, nem sobrevive à impressão."""
    assert cen["rotulo_atrasado"] == {"texto": "3d de atraso", "tom": "atrasado"}
    assert cen["rotulo_hoje"] == {"texto": "vence hoje", "tom": "hoje"}
    assert cen["rotulo_no_prazo"] == {"texto": "faltam 5d", "tom": "no prazo"}
    assert cen["rotulo_sem_prazo"] is None


def test_chamado_finalizado_nao_mostra_prazo(cen: dict) -> None:
    assert cen["mostra_novo"] is True
    assert cen["mostra_aguardando"] is True
    assert cen["mostra_resolvido"] is False
    assert cen["mostra_encerrado"] is False


# ═══════════ 3. as contagens ═══════════════════════════════════════════════════

def test_responsavel_em_branco_conta_como_sem_dono(cen: dict) -> None:
    """'   ' é sem responsável: contá-lo como dono esconderia o backlog órfão."""
    assert cen["responsavel"] == [["com responsável", 1], ["sem responsável", 2]]


def test_sem_prazo_e_categoria_propria(cen: dict) -> None:
    """Somada a "dentro do prazo", diria que está tudo sob controle."""
    assert cen["prazo"] == [["dentro do prazo", 2], ["sem prazo", 1],
                            ["fora do prazo", 1]]


# ═══════════ 4. leitura dos blocos ══════════════════════════════════════════

def test_o_bloco_chega_com_rotulo_cor_total_e_lista(cen: dict) -> None:
    assert cen["bloco_ok"] == ["Demandas Backlog", "amber", 3, 1]


def test_bloco_que_chega_como_numero_e_recusado(cen: dict) -> None:
    """É a forma EXATA do defeito que está em produção.

    O painel de lá lê `d.backlog` como número; a rota devolve objeto. Aqui o
    contrário — número onde se espera objeto — devolve null em vez de deixar um
    número virar "bloco" e explodir no render.
    """
    assert cen["bloco_numero"] is None
    assert cen["bloco_ausente"] is None
    assert cen["bloco_resposta_indefinida"] is None


def test_bloco_sem_lista_nao_quebra(cen: dict) -> None:
    """Total sem `chamados` é resposta degradada, não motivo para tela branca."""
    assert cen["bloco_sem_lista"] == ["backlog", "neutral", 0]


# ═══════════ 5. a aba existe e usa a regra ══════════════════════════════════

def test_a_aba_dashboard_esta_ligada_na_tela() -> None:
    tela = CHAMADOS.read_text(encoding="utf-8")
    assert "{ id: 'dashboard', label: 'Dashboard' }" in tela
    assert "<ChamadosDashboard />" in tela


def test_o_painel_consome_a_rota_e_nao_recalcula_no_cliente() -> None:
    """Uma regra só.

    O painel de produção refaz os grupos no cliente a partir de `/chamados`, e
    é dessa duplicação que nasce painel discordando da fila ao lado. Aqui os
    blocos vêm prontos, já recortados no banco pela mesma regra da fila.
    """
    fonte = TELA.read_text(encoding="utf-8")
    assert "/chamados/dashboard?visao=" in fonte
    assert "bloco(data," in fonte, "os blocos vêm da resposta"
