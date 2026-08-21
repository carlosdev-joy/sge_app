"""A guarda contra módulo servido de cache velho (dags/utils/frescor_modulo.py).

O defeito que ela existe para tornar visível não tem sintoma: o worker Celery
serve `utils/*` de `sys.modules`, o arquivo muda no disco, e o ciclo roda o
código antigo com task VERDE e log impecável. Mordeu em 13/08 (PR #312).

O que estes testes prendem:

  1. **Arquivo mais novo que o import é acusado.** É o caso central.
  2. **Módulo em dia não gera ruído.** Guarda que avisa sempre é guarda que
     ninguém lê — e aí o aviso verdadeiro passa junto com os falsos.
  3. **Módulo sem carimbo mas presente em sys.modules é acusado**: é
     exatamente o retrato de um worker servindo a versão anterior a esta
     guarda, que é quando ela mais precisa funcionar.
  4. **A guarda nunca derruba o import.** Trocar um defeito mudo por uma
     exceção no lugar errado seria piorar.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

from utils import frescor_modulo  # noqa: E402


def _limpa_registro():
    frescor_modulo._REGISTRO.clear()


def test_modulo_em_dia_nao_gera_aviso(tmp_path, monkeypatch):
    arquivo = tmp_path / "servicenow_sync.py"
    arquivo.write_text("# código")
    _limpa_registro()
    frescor_modulo.carimbar(str(arquivo))
    monkeypatch.setattr(frescor_modulo, "ESPERADOS", ("utils.servicenow_sync",))
    assert frescor_modulo.conferir() == []


def test_arquivo_mudou_depois_do_import_e_acusado(tmp_path, monkeypatch):
    arquivo = tmp_path / "servicenow_sync.py"
    arquivo.write_text("# versão antiga")
    _limpa_registro()
    frescor_modulo.carimbar(str(arquivo))

    # O deploy reescreve o arquivo; o módulo em memória continua o antigo.
    marca = frescor_modulo._REGISTRO["utils.servicenow_sync"]
    marca["mtime_no_import"] -= 600
    marca["importado_em"] -= 600

    monkeypatch.setattr(frescor_modulo, "ESPERADOS", ("utils.servicenow_sync",))
    avisos = frescor_modulo.conferir()
    assert len(avisos) == 1
    assert "código antigo" in avisos[0]
    assert "Reinicie o worker" in avisos[0], "o aviso precisa dizer o que fazer"


def test_modulo_sem_carimbo_mas_importado_e_acusado(monkeypatch):
    """Retrato do worker servindo a versão anterior a esta guarda."""
    _limpa_registro()
    monkeypatch.setitem(sys.modules, "utils.modulo_velho", object())
    monkeypatch.setattr(frescor_modulo, "ESPERADOS", ("utils.modulo_velho",))
    avisos = frescor_modulo.conferir()
    assert len(avisos) == 1
    assert "SEM carimbo" in avisos[0]


def test_modulo_nunca_importado_nao_gera_aviso(monkeypatch):
    """Sem o módulo em memória não há cache velho — e alarme falso ensina a
    ignorar o alarme."""
    _limpa_registro()
    monkeypatch.delitem(sys.modules, "utils.jamais_importado", raising=False)
    monkeypatch.setattr(frescor_modulo, "ESPERADOS", ("utils.jamais_importado",))
    assert frescor_modulo.conferir() == []


def test_carimbo_de_arquivo_inexistente_nao_levanta():
    """A guarda roda no import: uma exceção aqui derrubaria o módulo que ela
    protege."""
    _limpa_registro()
    frescor_modulo.carimbar("/caminho/que/nao/existe.py")  # não pode levantar
    assert "utils.existe" not in frescor_modulo._REGISTRO


def test_modulos_reais_carimbam():
    """A ponte com o mundo: os módulos que a DAG usa precisam estar
    carimbados, senão a guarda confere o vazio e nunca acusa nada.

    O reload é necessário porque outro teste desta sessão pode já ter
    importado os módulos (o carimbo roda no import, uma vez só) — sem ele o
    teste passaria ou falharia conforme a ORDEM de execução.
    """
    import importlib

    import utils.chamado_derivacoes
    import utils.servicenow_sync
    _limpa_registro()
    importlib.reload(utils.chamado_derivacoes)
    importlib.reload(utils.servicenow_sync)
    for nome in frescor_modulo.ESPERADOS:
        assert nome in frescor_modulo._REGISTRO, f"{nome} não carimbou no import"
