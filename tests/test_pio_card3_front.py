"""Front do Card 3 (Assinadas e Pagas): reaproveita a lógica pura do Card 1.

Prende: status `paid`, chave própria (`pio3-`), sem "dias pendente" (já está paga),
`listaDoCard` pela foto com o status do Card 3, Cards 1 e 2 inalterados e os dois
componentes ligando o Card 3 a `/pio/card3/*`.
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
CAIXA = UI / "src" / "caixa"
PURO = CAIXA / "lib" / "card1Foto.ts"


def _fonte(caminho: Path) -> str:
    texto = caminho.read_text(encoding="utf-8")
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith("//"))


@pytest.fixture(scope="module")
def rodar():
    if not (shutil.which("node") and shutil.which("npx")):
        pytest.skip("node/npx ausentes")
    tmp = tempfile.mkdtemp(prefix="card3foto-")
    r = subprocess.run(
        ["npx", "tsc", str(PURO), "--ignoreConfig", "--outDir", tmp,
         "--module", "commonjs", "--target", "es2020", "--skipLibCheck"],
        cwd=UI, capture_output=True, text=True, timeout=300)
    js = next(Path(tmp).rglob("card1Foto.js"), None)
    assert js is not None, f"tsc não emitiu card1Foto.js: {r.stdout}{r.stderr}"

    def chamar(corpo: str):
        script = (f"const m = require({json.dumps(str(js))});"
                  f"const saida = (() => {{ {corpo} }})();"
                  "console.log(JSON.stringify(saida));")
        p = subprocess.run(["node", "-e", script], cwd=UI, capture_output=True,
                           text=True, timeout=120)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)

    return chamar


ITEM = """const item = (o = {}) => ({
  id_foto: 1, proposta: 'SIM01', nome: 'CLIENTE FICTICIO', cpf: '', agencia: '0001',
  matricula: 'M1', data_venda: '2026-03-20', dias_pendente: 222, produto: 'Vida',
  area_produto: 'Vida', premio: 100.25, imp_segurada: 50000, renda: 4000,
  cidade: 'X', uf: 'SP', idade: 46, situacao: 'AT', assinatura: 'CO', pago: 'S',
  contato: { email: null, celular: null, residencial: null }, ...o });"""

PAGINA = """{data: {disponivel: true, referencia: '2026-10-28', atualizacao: '2026-10-28T07:41:30',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-10-28', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card3_e_paid_e_os_outros_seguem(rodar):
    assert rodar("return [m.STATUS_CARD1, m.STATUS_CARD2, m.STATUS_CARD3, m.STATUS_DE_FOTO];") == [
        "pending_signature", "awaiting_payment", "paid",
        ["pending_signature", "awaiting_payment", "paid"]]


def test_proposta_do_card3_tem_chave_propria_e_nao_mostra_dias_pendente(rodar):
    r = rodar(ITEM + """
      const c1 = m.propostaDoCard1(item({id_foto: 5}), '2026-10-28', null);
      const c2 = m.propostaDoCard1(item({id_foto: 5}), '2026-10-28', null, m.STATUS_CARD2);
      const c3 = m.propostaDoCard1(item({id_foto: 5}), '2026-10-28', null, m.STATUS_CARD3);
      return [c1.id, c2.id, c3.id, c3.status, c3.daysInPending, c1.daysInPending, c2.daysInPending,
              c3.foto.assinatura, c3.foto.pago];""")
    assert r == ["pio1-5", "pio2-5", "pio3-5", "paid", 0, 222, 222, "CO", "S"]


def test_lista_do_card3_usa_a_foto_e_nao_chama_o_legado(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD3);
      return {{chamadas, total: lista.total, deFoto: lista.deFoto,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "status": ["paid"]}


def test_estado_da_foto_do_card3_assinada_e_paga(rodar):
    e = rodar("""
      return m.estadoDaFoto({idFoto: 1, referencia: null, atualizacao: null, situacao: 'AT',
        assinatura: 'CO', pago: 'S', contato: {email: null, celular: null, residencial: null}})
        .map(x => x.valor);""")
    assert e == ["Assinada", "Pago", "Ativa"]


def test_componentes_ligam_o_card3_a_foto():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard3" in corpo and "usePropostasCard3" in corpo, arq
        assert "delete reais[STATUS_CARD3]" in corpo, arq   # nunca a contagem legada
        assert "usePropostasPio(emFoto ? undefined" in corpo, arq
        assert "STATUS_DE_FOTO.includes" in corpo, arq


def test_hooks_do_card3_leem_os_endpoints_do_card3():
    corpo = _fonte(CAIXA / "lib" / "pioCard3.ts")
    assert "/pio/card3/resumo" in corpo and "/pio/card3/propostas" in corpo
    assert "/pio/card1" not in corpo and "/pio/card2" not in corpo
    assert "data: referencia" in corpo


def test_router_do_card3_registrado_em_main():
    main = (RAIZ / "api" / "main.py").read_text(encoding="utf-8")
    assert main.count("pio_card3") == 2
