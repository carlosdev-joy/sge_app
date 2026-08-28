"""A fila da tela conta TRABALHOS, e a órfã continua card.

Todo RITM do catálogo gera uma sc_task, e o espelho traz as duas como linhas
irmãs. Medido no ambiente dev em 2026-08-28, contra a instância real: **95
registros para 59 trabalhos** — 36 tasks, todas com pai. O card passa a ser o
pedido, e a tarefa vira linha dentro dele.

O que estes testes prendem, e por que cada um existe:

  1. **A task com pai sai da lista de cards** — é a fase inteira.
  2. **A ÓRFÃ CONTINUA CARD.** A regra da instância diz que ela não deveria
     existir; se aparecer, é sintoma (do filtro de grupo, ou de a task ter
     chegado antes do pai) e esconder o sintoma é o oposto do que esta tela
     existe para fazer. Medição de 2026-08-28: zero órfãs — o teste guarda o
     caso que ainda não aconteceu.
  3. **String vazia é ausência.** O sync grava `''`, não NULL. Tratar `''`
     como valor faria TODA linha ter pai e a fila inteira desapareceria, sem
     erro nenhum.
  4. **A ordem não importa** — filho antes do pai dá o mesmo resultado.
  5. **Só a task é recusada.** Um RITM com pai (dado torto) continua card:
     senão um defeito de dado tiraria pedidos da fila.

⚠️ Um `grep` por `separarFila` no `Chamados.tsx` não serviria: ficaria verde
com a chamada presente e a regra invertida. O que se afirma aqui é o RESULTADO
da separação em cada cenário.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar — visível no
`-rs`, nunca silenciosa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "fila_agrupada_harness.cjs"
FONTE = RAIZ / "ui-react" / "src" / "lib" / "filaChamados.ts"
TELA = RAIZ / "ui-react" / "src" / "pages" / "Chamados.tsx"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente)")
_MAJOR_MINIMO = 18


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= _MAJOR_MINIMO \
            else None
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


def test_task_com_pai_vira_linha_do_card_e_nao_card(cen: dict) -> None:
    c = cen["par_ritm_task"]
    assert c["cards"] == ["R1"], "a task com pai não pode virar card"
    assert c["filhas"] == {"R1": ["T1"]}, "e precisa aparecer sob o pai"


def test_orfa_continua_card(cen: dict) -> None:
    """Some da fila é diferente de sumir do sistema."""
    c = cen["orfa_nula"]
    assert set(c["cards"]) == {"R1", "T9"}, (
        "task sem pai é sintoma, e a tela existe para mostrar sintoma")
    assert c["filhas"] == {}


def test_string_vazia_do_sync_conta_como_sem_pai(cen: dict) -> None:
    """O sync grava '' — não NULL. Tratar '' como valor esvaziaria a fila."""
    c = cen["orfa_string_vazia"]
    assert set(c["cards"]) == {"R1", "T9"}
    assert c["filhas"] == {}


def test_ordem_de_chegada_nao_muda_o_resultado(cen: dict) -> None:
    assert cen["filho_antes_do_pai"] == cen["par_ritm_task"]


def test_duas_tarefas_no_mesmo_pedido(cen: dict) -> None:
    c = cen["duas_filhas"]
    assert c["cards"] == ["R1"]
    assert c["filhas"] == {"R1": ["T1", "T2"]}


def test_task_com_pai_fora_da_fila_sai_da_lista_de_cards(cen: dict) -> None:
    """Registra o preço da regra em vez de fingir que não existe.

    O pai não está na fila (encerrado, ou fora do grupo), então a filha vai
    para o índice sob uma chave que ninguém renderiza — e some da tela. É o
    caso que a medição no dev não encontrou (zero em 36 tasks) e que a §7.1 da
    spec mede em produção antes de qualquer deploy.
    """
    c = cen["pai_fora_da_fila"]
    assert c["cards"] == ["R1"]
    assert c["filhas"] == {"R-INEXISTENTE": ["T2"]}


def test_apenas_task_e_recusada(cen: dict) -> None:
    """Dado torto não pode tirar PEDIDO da fila."""
    assert set(cen["ritm_com_pai_continua_card"]["cards"]) == {"R1", "R2"}
    assert cen["incidente"]["cards"] == ["I1"]


def test_a_contagem_da_fila_e_de_trabalhos(cen: dict) -> None:
    """3 registros, 2 trabalhos — é o número que o rodapé mostra."""
    assert cen["contagem"] == 2


def test_a_regra_mora_em_modulo_proprio_e_a_tela_a_usa() -> None:
    """Anti-drift: inline no JSX, a recusa volta a ser invisível."""
    assert FONTE.is_file(), "lib/filaChamados.ts sumiu"
    assert "export function separarFila" in FONTE.read_text(encoding="utf-8")

    tela = TELA.read_text(encoding="utf-8")
    assert "separarFila(" in tela, "Chamados.tsx deixou de usar a regra"
    assert "d.total} na fila" not in tela, (
        "o rodapé voltou a contar REGISTROS (d.total vem da API e inclui as "
        "tarefas já representadas no card do pai)")
