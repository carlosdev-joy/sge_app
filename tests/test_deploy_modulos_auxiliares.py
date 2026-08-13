"""scripts/deploy.sh — a distinção entre DAG e módulo auxiliar.

Por que este teste existe, em uma frase: **o deploy prometia uma coisa que
não acontecia, e nada falhava**.

O script dizia "o scheduler/worker recarrega pelo volume nas proximas
execucoes". Isso vale para o ARQUIVO DA DAG — o DagBag reprocessa a cada
execução e chega a apagá-lo de `sys.modules` antes. Não vale para os módulos
importados por ela: `from utils.x import y` é import comum, e se o módulo já
está em `sys.modules` do processo do worker Celery, o import devolve a versão
EM MEMÓRIA. Os forks herdam esse cache. O arquivo no disco muda e ninguém
consulta de novo.

Mordeu em 2026-08-13 (PR #312, que mexia SÓ em `dags/utils/`): o deploy
sincronizou o arquivo, três ciclos do sync rodaram depois disso — todos com
status OK, task verde, log impecável — gravando pelo código antigo. Uma hora e
meia de diagnóstico para achar um módulo em cache.

O que estes testes prendem:

  1. **A classificação**: `.py` em subpasta é módulo (precisa de restart);
     `.py` na raiz é DAG (recarrega sozinha); o que não é `.py` não conta.
  2. **O aviso e a oferta de restart continuam no script** — sem eles a
     detecção não serve para nada.
  3. **O restart NÃO vira automático**: derruba tasks em execução, então
     segue a regra da casa (padrão não, pergunta explícita).

A função é exercitada de verdade, extraída do script e rodada em bash — não
uma reimplementação da regex em Python, que passaria mesmo com o script
quebrado.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
DEPLOY_SH = RAIZ / "scripts" / "deploy.sh"


def _classificar(linhas: list[str]) -> list[str]:
    """Roda `_modulos_auxiliares` do próprio deploy.sh sobre as linhas dadas.

    Extrai a função do script e a executa em bash: se alguém mudar a regex lá,
    este teste sente. Reimplementar a regra aqui em Python daria um teste que
    concorda consigo mesmo e ignora o script.
    """
    fonte = DEPLOY_SH.read_text(encoding="utf-8")
    corpo = re.search(r"^_modulos_auxiliares\(\) \{.*?^\}", fonte, re.S | re.M)
    assert corpo, "_modulos_auxiliares() sumiu de scripts/deploy.sh"
    entrada = "".join(f"    {l}\n" for l in linhas)
    r = subprocess.run(
        ["bash", "-c", f"{corpo.group(0)}\n_modulos_auxiliares"],
        input=entrada, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


# ═══════════ 1. módulo em subpasta × DAG na raiz ════════════════════════════

@pytest.mark.parametrize("caminho", [
    "utils/servicenow_sync.py",
    "utils/conn_resolver.py",
    "utils/malha_corrida.py",
    "Orquestrador/qualquer.py",
    "utils/sub/mais_fundo.py",
])
def test_py_em_subpasta_e_modulo_e_exige_restart(caminho):
    assert _classificar([caminho]) == [caminho]


@pytest.mark.parametrize("caminho", [
    "etl_servicenow_sync.py",
    "etl_dag_factory.py",
    "orquestra_sla_monitor.py",
])
def test_py_na_raiz_e_dag_e_recarrega_sozinha(caminho):
    """DAG na raiz não pode disparar o aviso: pediria restart do worker (que
    derruba job) para uma mudança que o DagBag aplica sozinho."""
    assert _classificar([caminho]) == []


@pytest.mark.parametrize("caminho", [
    "utils/notas.md", "algum.txt", "utils/config.json", "README.md",
])
def test_arquivo_que_nao_e_python_nao_conta(caminho):
    assert _classificar([caminho]) == []


def test_lista_mista_separa_certo():
    """O caso real do deploy que falhou, com ruído em volta."""
    saida = _classificar([
        "etl_servicenow_sync.py",
        "utils/servicenow_sync.py",
        "README.md",
        "utils/conn_resolver.py",
    ])
    assert saida == ["utils/servicenow_sync.py", "utils/conn_resolver.py"]


def test_lista_vazia_nao_quebra():
    assert _classificar([]) == []


# ═══════════ 2. o aviso e a oferta continuam no script ══════════════════════

def test_script_oferece_restart_do_worker():
    """Detectar sem agir não resolveria nada — o operador precisa da saída."""
    fonte = DEPLOY_SH.read_text(encoding="utf-8")
    assert "restart airflow-worker" in fonte
    assert "_modulos_auxiliares" in fonte, "a detecção não está sendo chamada"


def test_script_mostra_o_que_esta_rodando_antes_de_oferecer():
    """Perguntar 'reiniciar?' sem dizer o que morre empurra a decisão para o
    escuro — e no Orquestra uma task morta pode ser job DataStage."""
    fonte = DEPLOY_SH.read_text(encoding="utf-8")
    assert "inspect active" in fonte


def test_restart_nao_e_automatico():
    """Regra da casa: nada que derrube job roda sem pergunta explícita. Um
    `restart` solto, fora de _confirmar, seria exatamente isso."""
    fonte = DEPLOY_SH.read_text(encoding="utf-8")
    bloco = fonte[fonte.index("_modulos_auxiliares)"):]
    linha_restart = next(l for l in bloco.splitlines()
                         if "restart airflow-worker" in l and "docker compose" in l)
    # A linha do restart tem que estar DENTRO do if de confirmação.
    antes = bloco[:bloco.index(linha_restart)]
    assert "_confirmar" in antes, (
        "o restart do worker precisa estar sob _confirmar — ele derruba tasks")
