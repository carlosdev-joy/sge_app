"""
F12 da spec `docs/spec-malha-execucao.md` — o que o operador LÊ da duração
típica (§9.5, Decisão 64).

`test_malhas_f12_tipicos.py` prova o SERVIDOR (a consulta de conjunto, o piso e
a degradação). Esta suíte prova a outra metade: o TEXTO.

── Como isto roda sem runner de JS ──────────────────────────────────────────
Mesma técnica (e mesmas razões) do `test_malhas_f10_painel.py`: `ui-react` não
tem runner de testes e acrescentar um traria dependência de REDE a um produto
que faz deploy offline com wheels. O módulo PURO desta fase (`duracaoTipica.ts`,
mais o `tempoCorrida` de que ele depende) é transpilado pelo `sucrase` que o
Vite já traz e executado pelo Node, byte a byte como está no `src/`.

Sem Node ou sem `node_modules`, a suíte SALTA em vez de falhar — mas o salto é
visível no `-rs`, nunca silencioso.

── Os aceites literais da fase, e o que cada um evita ───────────────────────
  • `há 12 min · típico 18 min (n=23)` — o número e a amostra no MESMO texto;
  • membro com 3 execuções → só o decorrido, **sem "típico" e sem `n`**: o piso
    é duro e o `n` nunca aparece sem o número ao lado;
  • 41 min sobre um p50 de 18 → `⚠ 2x`, âmbar, e **nada além disso**: a marca é
    leitura de tela, não evento. Um alarme por "está demorando" tocaria toda
    madrugada, e alarme que toca sempre é alarme que ninguém lê;
  • **a palavra proibida**: nada do que este módulo escreve chama o número de
    ETA, previsão ou conclusão. Somar típicos de membros não dá previsão de
    corrida — ela roda em paralelo e com dependências.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f12_tipicos_harness.cjs"
MALHAS = RAIZ / "ui-react" / "src" / "components" / "malhas"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente) — os testes de "
                 "contrato do fonte continuam valendo")
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
def front() -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def _cenario(front: dict, nome: str) -> dict:
    dado = front[nome]
    assert "erro" not in dado, f"{nome} levantou no front:\n{dado.get('erro')}"
    return dado


def _fonte(nome: str) -> str:
    return (MALHAS / nome).read_text(encoding="utf-8")


# ═══════════ o aceite: `há 12 min · típico 18 min (n=23)` ═══════════════════

def test_a_linha_do_membro_com_23_execucoes(front):
    """O aceite literal. O `n` está DENTRO do mesmo texto do típico — é assim
    que ele nunca aparece sozinho, e não por um `if` no componente."""
    d = _cenario(front, "linha_do_aceite")
    assert d["tipico"] == "típico 18 min (n=23)"
    assert d["texto"] == "há 12 min · típico 18 min (n=23)"
    # 12 min sobre 18 não é atípico: nada de âmbar numa corrida saudável.
    assert d["marca"] is None


# ═══════════ o piso duro: sem amostra não sai número ════════════════════════

def test_membro_sem_amostra_nao_deixa_o_n_sobrando(front):
    """Aceite: membro com **3** execuções → só o decorrido. O servidor não
    manda o item, e aqui a frase some INTEIRA — nunca "típico —", nunca
    `(n=3)`."""
    d = _cenario(front, "piso_duro")
    assert d["ausente"] is None
    assert d["texto_ausente"] is None
    assert d["texto_nulo"] is None and d["texto_indefinido"] is None
    # E o membro sem amostra também não ganha marca âmbar: sem p50 não há o que
    # comparar, e "não medi" jamais vira alerta.
    assert d["marca_sem_tipico"] is None


def test_o_bloco_ausente_degrada_para_vazio_sem_quebrar(front):
    """Chave ausente é o contrato da degradação (Decisão 41): API anterior à
    fase, erro de leitura ou lente sem corrida caem todos no mesmo lugar."""
    d = _cenario(front, "piso_duro")
    assert d["mapa_sem_bloco"] == 0
    assert d["mapa_indefinido"] == 0
    assert d["mapa_vazio"] == 0


# ═══════════ a marca âmbar `⚠ 2x` ══════════════════════════════════════════

def test_o_membro_rodando_ha_41_min_com_p50_de_18_ganha_a_marca(front):
    """O aceite, com o múltiplo TRUNCADO: 41/18 = 2,3× e a marca diz `2x`.
    Arredondar para cima diria `3x` de algo que ainda não é o triplo — e o
    operador confere a conta na mesma linha."""
    d = _cenario(front, "marca_atipica")
    assert d["quarenta_e_um"] == "⚠ 2x"
    assert d["tres_vezes"] == "⚠ 3x"
    assert d["fator"] == 2


def test_a_fronteira_da_marca_e_exata_e_a_ausencia_nao_alarma(front):
    """Exatamente 2× acende; um minuto abaixo, não. E sem decorrido apurado a
    marca não existe: ausência de medida nunca vira alerta."""
    d = _cenario(front, "marca_atipica")
    assert d["exatamente_2x"] == "⚠ 2x"
    assert d["quase_2x"] is None
    assert d["sem_decorrido"] is None and d["indefinido"] is None


def test_a_marca_se_declara_leitura_de_tela_e_nao_alarme(front):
    """A marca **não** vira evento no Teams, e o texto que a explica diz isso:
    um alarme por "está demorando" tocaria toda madrugada (Decisões 26/27)."""
    d = _cenario(front, "marca_atipica")
    assert "não alarme" in d["titulo"]
    assert "típico 18 min (n=23)" in d["titulo"]


# ═══════════ o número não é ETA, e o texto não deixa dúvida ════════════════

_PROIBIDAS = ("previs", "estimat", "prognóst", "conclusão da corrida",
              "vai terminar", "termina às")


def test_nenhum_texto_desta_fase_chama_o_numero_de_previsao(front):
    """Decisão 75/#3 e o aceite da fase: o número é a duração típica DAQUELE
    membro, medida. Somar típicos não dá previsão de conclusão da corrida — e
    nenhuma palavra do que a tela escreve pode sugerir que dá."""
    textos = []

    def colher(v):
        if isinstance(v, str):
            textos.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                colher(x)
        elif isinstance(v, list):
            for x in v:
                colher(x)

    colher(front)
    assert textos, "a bancada não produziu texto nenhum — cenário vazio"
    for t in textos:
        baixo = t.casefold()
        for proibida in _PROIBIDAS:
            assert proibida not in baixo, f"'{proibida}' apareceu em: {t}"
        # "ETA" como PALAVRA (e não dentro de "etapa", "meta"…)
        assert not re.search(r"\bETA\b", t), f"'ETA' apareceu em: {t}"


def test_o_painel_nao_escreve_ETA_nem_previsao_ao_lado_do_tipico(front):
    """O contrato do componente, porque o texto do JSX não passa pela bancada:
    a linha do painel só compõe decorrido + típico + marca."""
    fonte = _fonte("PainelCorridaLateral.tsx")
    # o que ele CHAMA (a guarda literal — apagá-la deixa o teste vermelho)
    assert "textoTipico(tipico)" in fonte
    assert "marcaAtipica(minutos, tipico)" in fonte
    # e o que ele não escreve em lugar nenhum
    for proibida in ("previsão", "estimativa", "prognóstico"):
        assert proibida not in fonte.casefold(), proibida


# ═══════════ arredondamento e a ponte de caixa ═════════════════════════════

def test_o_tipico_em_minutos_arredonda_e_nunca_publica_zero(front):
    """O típico é uma MEDIDA (arredonda), não um relógio correndo (que
    truncaria). E duração abaixo de um minuto vira "menos de 1 min" — nunca
    "0 min", que leria como medida de nada."""
    d = _cenario(front, "arredondamento")
    assert d["dezessete"] == "típico 17 min (n=30)"
    assert d["hora_e_meia"] == "típico 1h30 (n=9)"
    assert d["rapido"] == "típico menos de 1 min (n=7)"
    # payload estragado não vira "0 min" nem "NaN": some.
    assert d["zero"] is None and d["negativo"] is None and d["nulo"] is None


def test_a_grafia_do_snapshot_e_a_oficial_se_encontram(front):
    """O GOTCHA de caixa que já quebrou pipeline em produção, aqui na forma
    silenciosa: `tipicos[]` vem do SNAPSHOT e `execucoes[]` da grafia OFICIAL.
    Sem a ponte, o número somia da linha sem nada explicar."""
    d = _cenario(front, "ponte_de_caixa")
    assert d["oficial"] == "típico 18 min (n=23)"
    assert d["minusculo"] == "típico 18 min (n=23)"
    assert d["com_espaco"] == "típico 18 min (n=23)"
    # ...e continua sendo um índice, não um "acha qualquer um"
    assert d["outro"] is None
