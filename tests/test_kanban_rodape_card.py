"""O rodapé do card do kanban: alarme só para quem ainda espera, prazo à vista.

Dois ajustes pedidos pelo dono do produto ao olhar o quadro:

  1. **O contador de idade não vale para chamado resolvido.** O rodapé mostrava
     "atenção 7d" em card RESOLVIDO — alarme sobre trabalho FEITO. Alarme que
     não pede ação nenhuma é o que ensina a ignorar os outros, inclusive os que
     pedem. Some junto o prazo, pela mesma razão.
  2. **O prazo aparece no card quando existe.** Quem abre o kanban precisa ver
     o que vence sem clicar em cada um — que é justamente o gesto que o quadro
     existe para evitar.

⚠️ ESTE ARQUIVO RENDERIZA. A primeira versão do teste procurava `{vivo &&` no
`.tsx` e passou VERDE com o defeito de pé: o arquivo tinha DUAS ocorrências, e
sabotar uma deixava a outra satisfazendo a busca. O que a fase entrega é uma
AUSÊNCIA, e ausência só se afirma olhando o que foi renderizado.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "rodape_card_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

VIVOS = ["novo_parado", "andamento", "aguardando"]
TERMINADOS = ["resolvido", "encerrado"]


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
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. o alarme, só para quem ainda espera ═════════════════════════

@pytest.mark.parametrize("estado", TERMINADOS)
def test_chamado_terminado_nao_mostra_idade(cen: dict, estado: str) -> None:
    """"parado 12d" num card resolvido é alarme sobre trabalho FEITO."""
    c = cen[estado]
    assert c["temIdade"] is False
    assert "12d" not in c["texto"]
    assert "parado" not in c["texto"]
    assert "atenção" not in c["texto"]


@pytest.mark.parametrize("estado", TERMINADOS)
def test_chamado_terminado_nao_mostra_prazo(cen: dict, estado: str) -> None:
    """Prazo de um chamado pronto não pede ação nenhuma."""
    assert cen[estado]["temPrazo"] is False
    assert "prazo" not in cen[estado]["texto"]


@pytest.mark.parametrize("estado", VIVOS)
def test_chamado_vivo_continua_alertando(cen: dict, estado: str) -> None:
    """A correção não pode calar quem ainda espera — é o alarme que serve."""
    c = cen[estado]
    assert c["temIdade"] is True
    assert "12d" in c["texto"]
    assert "parado" in c["texto"], "a faixa de idade traz rótulo, não só cor"


# ═══════════ 2. o prazo no card ═════════════════════════════════════════════

@pytest.mark.parametrize("estado", VIVOS)
def test_o_prazo_aparece_no_card(cen: dict, estado: str) -> None:
    """Sem isso, ver o que vence exige abrir chamado por chamado — o gesto
    que o quadro existe para evitar."""
    c = cen[estado]
    assert c["temPrazo"] is True
    assert "02/09/2026" in c["texto"], "a DATA, para conferir a olho"
    assert "faltam 5d" in c["texto"], "e o que ela significa, em palavras"


def test_sem_prazo_a_linha_nao_aparece(cen: dict) -> None:
    """Linha "prazo —" em todo card sem prazo é ruído em fila inteira."""
    c = cen["sem_prazo"]
    assert c["temPrazo"] is False
    assert c["temIdade"] is True, "a idade continua: o chamado segue esperando"


# ═══════════ 3. o que o rodapé nunca cala ═══════════════════════════════════

def test_sem_responsavel_e_dito_e_nao_deixado_em_branco(cen: dict) -> None:
    """Espaço vazio no lugar do nome parece falha de carregamento; o texto
    diz que o chamado não tem dono — que é a informação."""
    assert "sem responsável" in cen["sem_responsavel"]["texto"]
