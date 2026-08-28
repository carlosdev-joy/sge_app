"""O detalhe do chamado: data da nota, tamanho do anexo e tipo da nota.

A rota `/chamados/{sys_id}/detalhe` existe desde a F2 e não tinha tela —
respondia e ninguém perguntava. Este é o consumidor dela, e o que estes testes
prendem são as três coisas que erram em silêncio nele.

  1. **Data de nota errada AFIRMA.** `new Date('2026-08-28T23:30:00Z')` lido à
     noite em Brasília devolve o dia anterior: o histórico mostraria a nota um
     dia antes de ela existir. Pior que nota sem data.
  2. **`0 B` não é "arquivo vazio".** O ServiceNow manda 0 quando não sabe o
     tamanho, e um anexo anunciado como vazio é um anexo que ninguém baixa.
  3. **`work_notes` ≠ `comments`.** Uma fica entre a equipe, a outra o
     solicitante lê. Mostradas iguais, alguém escreve para dentro achando que
     escreveu para fora — ou o contrário, que é pior.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "chamado_detalhe_harness.cjs"
MODAL = (RAIZ / "ui-react" / "src" / "components" / "chamados"
         / "ChamadoDetalheModal.tsx")
FILA = RAIZ / "ui-react" / "src" / "pages" / "Chamados.tsx"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"


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


# ═══════════ 1. a data da nota ══════════════════════════════════════════════

def test_a_data_da_nota_sai_com_hora(cen: dict) -> None:
    assert cen["nota_com_hora"] == "28/08/2026 11:43"
    assert cen["nota_iso"] == "28/08/2026 11:43"


def test_a_data_da_nota_nao_anda_para_tras(cen: dict) -> None:
    """O histórico mostraria a nota um dia antes de ela existir."""
    assert cen["nota_iso_utc"] == "28/08/2026 23:30"


def test_data_sem_hora_e_data_ausente(cen: dict) -> None:
    assert cen["nota_so_data"] == "28/08/2026"
    assert cen["nota_nula"] == "—"


def test_formato_desconhecido_volta_cru(cen: dict) -> None:
    """"Invalid Date" faria o operador achar que o chamado está corrompido."""
    assert cen["nota_estranha"] == "ontem à tarde"


# ═══════════ 2. o tamanho do anexo ══════════════════════════════════════════

def test_o_tamanho_sai_na_unidade_certa(cen: dict) -> None:
    assert cen["bytes"] == "500 B"
    assert cen["kb"] == "2 KB"
    assert cen["mb"] == "3.0 MB"


def test_zero_nao_vira_arquivo_vazio(cen: dict) -> None:
    """O ServiceNow manda 0 quando não sabe o tamanho.

    Anunciar "0 B" é dizer que o arquivo está vazio — que é outra coisa, e
    leva alguém a não baixar um anexo que existe.
    """
    assert cen["zero"] == "—"
    assert cen["sem_tamanho"] == "—"


# ═══════════ 3. o tipo da nota ══════════════════════════════════════════════

def test_nota_interna_e_comentario_publico_nao_se_confundem(cen: dict) -> None:
    assert cen["nota_interna"] == "nota interna"
    assert cen["nota_publica"] == "comentário ao solicitante"
    assert cen["nota_interna"] != cen["nota_publica"]


def test_tipo_desconhecido_aparece_em_vez_de_sumir(cen: dict) -> None:
    """Tipo novo na instância vira rótulo cru — some seria pior: a nota
    apareceria sem dizer se é interna ou pública."""
    assert cen["nota_tipo_novo"] == "additional_comments"
    assert cen["nota_sem_tipo"] == "nota"


# ═══════════ 4. a tela existe e é alcançável ════════════════════════════════

def test_o_modal_consome_a_rota_de_detalhe() -> None:
    fonte = MODAL.read_text(encoding="utf-8")
    assert "/detalhe" in fonte
    assert "migration_ausente" in fonte, (
        "sem tratar a marca, 'nenhuma nota' e 'não consegui ler as notas' "
        "ficam com a mesma cara")


def test_o_card_da_fila_abre_o_detalhe() -> None:
    """A rota sem tela era um endpoint que respondia e ninguém perguntava."""
    fila = FILA.read_text(encoding="utf-8")
    assert "ChamadoDetalheModal" in fila
    assert "setVerDetalhe(true)" in fila


def test_o_anexo_baixa_pelo_proxy_e_nao_do_servicenow() -> None:
    """A credencial do ServiceNow não pode ir para o navegador — e o proxy
    exige o par (anexo, chamado), então um id solto não baixa nada."""
    fonte = MODAL.read_text(encoding="utf-8")
    assert "anexo.url_proxy" in fonte
    assert "service-now.com" not in fonte.replace(
        "Abrir no ServiceNow", "")   # o link do chamado é legítimo
