"""Bancada do front para o nó `email` no canvas (F2 da spec de notificação por
e-mail): `components/etapas/fluxoTypes.ts`.

A régua daqui ESPELHA `_validate_email` do backend (api/routers/jobs.py). Ela
existe para o operador ver o problema junto do nó, antes do save; a fonte da
verdade continua sendo o servidor. Se as duas divergirem, a tela passa a
prometer o que o save recusa — por isso os mesmos casos aparecem nos dois
arquivos de teste.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests/js/ds_params_harness.cjs"


@pytest.fixture(scope="module")
def e():
    node = shutil.which("node")
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["emailNo"]


def test_no_novo_nasce_util(e):
    """Arrastar o nó e ligar já produz um aviso que faz sentido: herda a lista
    do fluxo e traz assunto e corpo prontos."""
    p = e["padrao"]
    assert p["incluir_pipeline"] is True and p["destinatarios"] == []
    assert "{pipeline}" in p["assunto"] and p["corpo"].strip()
    assert p["anexo"] is None and p["html"] is False


def test_round_trip_com_a_api(e):
    vazio, completo, sujo, incluirAusente = e["doApi"]
    assert vazio["incluir_pipeline"] is True                  # null → default útil
    assert completo["anexo"] == {"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"}
    assert completo["incluir_pipeline"] is False              # escolha explícita sobrevive
    assert sujo["destinatarios"] == ["a@x.com"]               # espaços e vazios somem
    assert sujo["anexo"] == {"raiz": "/dados/saida", "nome": "r.csv"}
    # Ausente = ligado, como no backend: um round-trip não pode desligar a
    # herança sozinho (o e-mail sairia para menos gente, em silêncio).
    assert incluirAusente is True


def test_rotulo_do_card_diz_quem_recebe(e):
    assert e["rotulos"] == ["destinatários do fluxo", "ana@cvp.com.br",
                            "2 destinatários + fluxo", "sem destinatário"]


def test_regua_local_espelha_a_do_backend(e):
    r = e["erros"]
    assert r["padraoHerdando"] == [] and r["completo"] == []
    assert r["padraoSemDestinatario"] and "destinatário" in r["padraoSemDestinatario"][0]
    assert r["semAssunto"] == ["Informe o assunto"]
    assert r["semCorpo"] == ["Informe o corpo da mensagem"]
    assert "quebra de linha" in r["assuntoComQuebra"][0]
    assert r["destinatarioRuim"] == ["Destinatário inválido: sem-arroba"]


def test_anexo_so_dentro_das_pastas_liberadas(e):
    r = e["erros"]
    assert "não está entre as permitidas" in r["anexoForaDaRaiz"][0]
    assert "barra" in r["anexoComBarra"][0]


def test_anexo_incompleto_e_cobrado_em_vez_de_sumir(e):
    """A serialização descarta um anexo sem nome (vira null): sem esta régua o
    operador marcaria 'Anexar', salvaria, e o anexo não existiria — sem aviso."""
    r = e["erros"]
    assert any("nome do arquivo do anexo" in x for x in r["anexoSemNome"])
    assert any("Escolha a pasta do anexo" in x for x in r["anexoSemPasta"])


def test_lista_de_pastas_vazia_nao_trava_o_save(e):
    """Lista vazia pode ser 'Admin sem pasta liberada' OU falha ao consultar o
    status. Cobrar a pasta aqui travaria o fluxo inteiro por um erro de rede,
    sem caminho de saída — o backend continua sendo a palavra final."""
    assert e["erros"]["semRaizLiberada"] == []
