"""Front do monitoramento de uso (spec docs/spec-uso-busca-vendas.md): lógica pura no node.

`usoDatas.ts` e `usoRegras.ts` são puros de propósito (como `card1Foto.ts`): compilados
com `tsc` e chamados pelo `node`. Prendem:

  1. Navegar entre períodos nunca pula nem repete mês (31/03 − 1 mês não vira 03/03).
  2. O próximo período não passa de hoje; o "período atual" vale para dia, mês e ano.
  3. O rótulo do mês tem maiúscula só na 1ª letra ("Outubro de 2026").
  4. Datas são lidas SEM fuso: `2026-10-28` continua 28, não vira 27 por UTC.
  5. O acesso é deduplicado por rota na janela de 30 min, e só /caixa-seguro/* é medido.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "ui-react"
LIB = UI / "src" / "caixa" / "lib"


@pytest.fixture(scope="module")
def rodar():
    if not (shutil.which("node") and shutil.which("npx")):
        pytest.skip("node/npx ausentes")
    tmp = tempfile.mkdtemp(prefix="usobv-")
    r = subprocess.run(
        ["npx", "tsc", str(LIB / "usoDatas.ts"), str(LIB / "usoRegras.ts"), "--ignoreConfig",
         "--outDir", tmp, "--module", "commonjs", "--target", "es2020", "--skipLibCheck"],
        cwd=UI, capture_output=True, text=True, timeout=300)
    datas = next(Path(tmp).rglob("usoDatas.js"), None)
    regras = next(Path(tmp).rglob("usoRegras.js"), None)
    assert datas and regras, f"tsc não emitiu os módulos: {r.stdout}{r.stderr}"

    def chamar(corpo: str):
        script = (f"const d = require({json.dumps(str(datas))});"
                  f"const r = require({json.dumps(str(regras))});"
                  f"const saida = (() => {{ {corpo} }})();"
                  "console.log(JSON.stringify(saida));")
        p = subprocess.run(["node", "-e", script], cwd=UI, capture_output=True,
                           text=True, timeout=120)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)

    return chamar


def test_navegar_mes_nao_pula_nem_repete(rodar):
    assert rodar("""return [
      d.deslocarReferencia('mes', '2026-03-31', -1),
      d.deslocarReferencia('mes', '2026-10-31', 1),
      d.deslocarReferencia('mes', '2026-01-15', -1),
      d.deslocarReferencia('mes', '2026-12-10', 1)];""") == [
        "2026-02-01", "2026-11-01", "2025-12-01", "2027-01-01"]


def test_navegar_dia_e_ano(rodar):
    assert rodar("""return [
      d.deslocarReferencia('dia', '2026-03-01', -1),
      d.deslocarReferencia('dia', '2026-12-31', 1),
      d.deslocarReferencia('ano', '2026-10-28', -1)];""") == [
        "2026-02-28", "2027-01-01", "2025-01-01"]


def test_periodo_atual_e_limite_de_hoje(rodar):
    assert rodar("""const h = '2026-10-28';
      return [
        d.ehPeriodoAtual('dia', '2026-10-28', h), d.ehPeriodoAtual('dia', '2026-10-27', h),
        d.ehPeriodoAtual('mes', '2026-10-01', h), d.ehPeriodoAtual('mes', '2026-09-30', h),
        d.ehPeriodoAtual('ano', '2026-01-01', h), d.ehPeriodoAtual('ano', '2025-12-31', h),
        d.limitarAHoje('2026-11-02', h), d.limitarAHoje('2026-10-01', h)];""") == [
        True, False, True, False, True, False, "2026-10-28", "2026-10-01"]


def test_rotulos_pt_br_sem_fuso(rodar):
    assert rodar("""return [
      d.rotuloPeriodo('mes', '2026-10-28'), d.rotuloPeriodo('ano', '2026-10-28'),
      d.rotuloPeriodo('dia', '2026-10-28'), d.paraIso(d.deIso('2026-10-28')),
      d.dataBrDeIso('2026-10-28T14:05:00'), d.dataBrDeIso(null)];""") == [
        "Outubro de 2026", "2026", "28/10/2026", "2026-10-28", "28/10/2026", "—"]


def test_acesso_dedupe_por_rota_na_janela_de_30_min(rodar):
    assert rodar("""const v = new Map(); const min = 60 * 1000;
      return [
        r.deveRegistrarAcesso('/caixa-seguro', 0, v),
        r.deveRegistrarAcesso('/caixa-seguro', 10 * min, v),
        r.deveRegistrarAcesso('/caixa-seguro/uso', 10 * min, v),
        r.deveRegistrarAcesso('/caixa-seguro', 29 * min, v),
        r.deveRegistrarAcesso('/caixa-seguro', 31 * min, v)];""") == [True, False, True, False, True]


def test_so_o_modulo_e_medido(rodar):
    assert rodar("""return ['/caixa-seguro', '/caixa-seguro/uso', '/caixa-seguro/acompanhamento/pendentes',
      '/caixa-seguro-x', '/admin', '/'].map(r.ehRotaDoModulo);""") == [
        True, True, True, False, False, False]


def test_front_nao_carrega_mais_dados_simulados():
    """A F1 usava um mock atrás de USO_USA_MOCK; a F3 o removeu (o simulado nunca vai a produção)."""
    fontes = [p for p in (UI / "src").rglob("*.ts*") if "node_modules" not in p.parts]
    assert not (LIB / "usoMock.ts").exists()
    achados = [str(p.relative_to(RAIZ)) for p in fontes
               if re.search(r"USO_USA_MOCK|usoMock|resumoUsoSimulado", p.read_text(encoding="utf-8"))]
    assert achados == [], achados


def test_tracker_so_envia_rota_do_modulo_e_nunca_a_matricula():
    fonte = (LIB / "usoRastreio.ts").read_text(encoding="utf-8")
    assert "matricula" not in re.sub(r"//.*", "", fonte)
    assert 'JSON.stringify({ rota })' in fonte
