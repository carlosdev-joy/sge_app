"""A região do card e os campos que saíram do "Resumo do seguro" (2026-09-01).

Duas coisas são prendidas aqui:

  1. **`regiaoDaUf` é EXERCITADA de verdade**, não lida por regex. O front do
     Orquestra não tem test runner, então o módulo (que é puro justamente para
     isso) é compilado com `tsc` e chamado pelo `node` — as 27 UFs, caixa
     baixa, espaço em volta, vazio e sigla inexistente. Um mapa escrito à mão
     com uma UF faltando mostraria "MS" solto no meio de "Sudeste", "Sul"…

  2. **Os campos fixos não voltam.** "Sexo: Masculino", a profissão, o estado
     civil e a seção inteira do beneficiário eram literais no TSX, iguais em
     toda proposta. E "Renda Individual" exibia `proposal.value`, que é o
     PRÊMIO — rótulo de um dado com o número de outro, que é como a tela
     produzia uma diferença que ninguém explicava.

O teste 1 é pulado (skip) se `node`/`npx` não existirem no ambiente.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "ui-react"
REGIAO_TS = UI / "src" / "caixa" / "lib" / "regiao.ts"
MODAL_TSX = UI / "src" / "caixa" / "components" / "ProposalDetailDialog.tsx"
PIO_TS = UI / "src" / "caixa" / "lib" / "pio.ts"

# As 27 unidades federativas e a região do IBGE de cada uma.
UF_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}


def _sem_comentarios(arquivo: Path) -> str:
    """O código do arquivo sem comentários — `/* */` (a forma usada dentro do
    JSX) e `//`. Procurar literal em fonte comentada acusa a explicação junto
    com o defeito."""
    import re
    fonte = arquivo.read_text(encoding="utf-8")
    fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


def test_o_leitor_de_fonte_nao_apagou_tudo():
    """Guarda dos testes de literal: se `_sem_comentarios` passar a devolver
    vazio, todos eles passariam sem verificar nada."""
    corpo = _sem_comentarios(MODAL_TSX)
    assert "Dados do Segurado" in corpo and "CampoInfo" in corpo, (
        "o leitor de fonte quebrou — os testes de literal viraram falso verde")


@pytest.fixture(scope="module")
def regiao_de():
    """Compila `regiao.ts` e devolve uma função que chama `regiaoDaUf` no node.

    `--ignoreConfig` é obrigatório: com arquivos na linha de comando o tsc
    recusa o tsconfig do projeto e sai com erro em vez de compilar.
    """
    if not (shutil.which("node") and shutil.which("npx")):
        pytest.skip("node/npx ausentes")

    tmp = tempfile.mkdtemp(prefix="regiao-")
    r = subprocess.run(
        ["npx", "tsc", str(REGIAO_TS), "--ignoreConfig", "--outDir", tmp,
         "--module", "commonjs", "--target", "es2020"],
        cwd=UI, capture_output=True, text=True, timeout=300)
    js = Path(tmp) / "regiao.js"
    assert js.exists(), f"tsc não emitiu {js}: {r.stdout}{r.stderr}"

    def chamar(entradas: list) -> list:
        script = (f"const {{regiaoDaUf}} = require({json.dumps(str(js))});"
                  f"console.log(JSON.stringify("
                  f"{json.dumps(entradas)}.map(regiaoDaUf)));")
        saida = subprocess.run(["node", "-e", script], cwd=UI,
                               capture_output=True, text=True, timeout=120)
        assert saida.returncode == 0, saida.stderr
        return json.loads(saida.stdout)

    return chamar


def test_as_27_ufs_tem_regiao(regiao_de):
    ufs = sorted(UF_REGIAO)
    obtidas = dict(zip(ufs, regiao_de(ufs)))
    erradas = {u: (obtidas[u], UF_REGIAO[u]) for u in ufs if obtidas[u] != UF_REGIAO[u]}
    assert not erradas, f"UF com região errada (obtida, esperada): {erradas}"


def test_caixa_e_espaco_nao_atrapalham(regiao_de):
    """A carga vem de sistema legado: " pr " e "sp" acontecem."""
    assert regiao_de(["pr", " RJ ", "Sp"]) == ["Sul", "Sudeste", "Sudeste"]


def test_uf_vazia_some_e_uf_desconhecida_aparece(regiao_de):
    """Vazio → campo some da tela. Sigla inexistente → ela PRÓPRIA na tela: se
    a carga trouxer lixo em NOM_UF, é para dar na vista, não sumir."""
    assert regiao_de(["", None, "  "]) == ["", "", ""]
    assert regiao_de(["XX", "ZZ"]) == ["XX", "ZZ"]


def test_o_card_usa_a_regiao_e_nao_cidade_barra_uf():
    fonte = PIO_TS.read_text(encoding="utf-8")
    assert "region: regiaoDaUf(item.uf)" in fonte, "o card voltou a montar a região à mão"
    assert 'join(" / ")' not in fonte, "cidade/UF voltou para o campo Região"


# ═══════════ os campos que saíram do "Resumo do seguro" ═════════════════════

@pytest.mark.parametrize("literal", [
    "Masculino",                                    # Sexo, fixo
    "SUPERV, INSPETOR E AGENTE DE COMPRAS/VENDAS",  # Profissão, fixa
    "Solteiro",                                     # Estado Civil, fixo
    "Herdeiros Legais",                             # Beneficiário, fixo
    "Dados do Beneficiário",                        # a seção inteira
])
def test_valor_inventado_nao_volta_ao_modal(literal):
    """Todos estes eram literais no TSX, iguais em toda proposta. Voltar com
    qualquer um deles é reencher a tela de dado que não é do cliente.

    O comentário que explica a remoção CITA os literais — daí o cuidado de
    tirar comentários antes de procurar, blocos `/* */` inclusive (é a forma do
    comentário dentro do JSX). Sem isso o teste acusaria a própria explicação.
    """
    assert literal not in _sem_comentarios(MODAL_TSX), (
        f"{literal!r} voltou ao Resumo do seguro — a carga do PIO não traz esse dado")


def test_renda_nao_exibe_o_premio():
    """O bug que motivou a revisão: rótulo "Renda Individual" sobre o valor do
    prêmio. A renda tem campo próprio (`individualIncome` ← VLR_RENDA_FORMAL)."""
    fonte = MODAL_TSX.read_text(encoding="utf-8")
    import re
    for rotulo, valor in re.findall(r'rotulo="([^"]*)"\s+valor=\{([^}]*)\}', fonte):
        if "Renda" in rotulo:
            assert "individualIncome" in valor, (
                f'"{rotulo}" está exibindo `{valor.strip()}` — o prêmio de novo?')
            assert "proposal.value" not in valor


def test_a_renda_vem_de_coluna_propria():
    """Guarda do teste acima: se a renda deixar de ser mapeada em `pio.ts`, o
    campo some da tela e ninguém percebe que o dado sumiu."""
    fonte = PIO_TS.read_text(encoding="utf-8")
    assert "individualIncome: item.renda" in fonte, (
        "a renda deixou de vir da carga")


# ═══════════ os três valores que a tela não pode confundir ══════════════════
# `value` = PRÊMIO (o que se paga por mês) · `individualIncome` = RENDA do
# proponente · `insuredAmount` = IMPORTÂNCIA SEGURADA (o capital coberto).
# Prêmio e renda já foram o mesmo número na tela uma vez, com rótulos
# diferentes; estes testes prendem cada um na sua coluna.

@pytest.mark.parametrize("campo,coluna", [
    ("value", "item.premio"),
    ("individualIncome", "item.renda"),
    ("insuredAmount", "item.imp_segurada"),
])
def test_cada_valor_vem_da_sua_coluna(campo, coluna):
    import re
    fonte = PIO_TS.read_text(encoding="utf-8")
    m = re.search(rf"^\s*{campo}: (.+?),$", fonte, re.M)
    assert m, f"`{campo}` não é mais preenchido em propostaDoPio()"
    assert coluna in m.group(1), (
        f"`{campo}` passou a ler `{m.group(1).strip()}` em vez de `{coluna}` — "
        f"prêmio, renda e importância segurada são três valores diferentes")


def test_os_tres_valores_tem_rotulo_proprio_no_modal():
    """Dois rótulos sobre a mesma variável é como o prêmio virou "renda"."""
    import re
    fonte = MODAL_TSX.read_text(encoding="utf-8")
    pares = re.findall(r'rotulo="([^"]*)"\s+valor=\{([^}]*)\}', fonte)
    variaveis = [v.strip() for _r, v in pares]
    repetidas = {v for v in variaveis if variaveis.count(v) > 1}
    assert not repetidas, f"o mesmo valor exibido sob rótulos diferentes: {repetidas}"


def test_a_importancia_segurada_aparece_no_modal():
    """Ela vinha do banco, chegava no front e parava — nenhuma tela a exibia."""
    corpo = _sem_comentarios(MODAL_TSX)
    assert "Importância Segurada" in corpo, "o campo sumiu do Resumo do seguro"
    assert "proposal.insuredAmount" in corpo
