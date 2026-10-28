"""Front do Card 2 (Pendentes de Pagamento): reaproveita a lógica pura do Card 1.

Prende: o Card 2 mapeia a foto com `status=awaiting_payment` e chave própria
(`pio2-`), `listaDoCard` escolhe a fonte pelo status, o Card 1 segue igual, e os
dois componentes que listam propostas ligam o Card 2 à foto (`/pio/card2/*`).
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
    tmp = tempfile.mkdtemp(prefix="card2foto-")
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
  matricula: 'M1', data_venda: '2026-10-20', dias_pendente: 7, produto: 'Vida',
  area_produto: 'Vida', premio: 100.25, imp_segurada: 50000, renda: 4000,
  cidade: 'X', uf: 'SP', idade: 46, situacao: 'AT', assinatura: 'CO', pago: 'N',
  contato: { email: null, celular: null, residencial: null }, ...o });"""

PAGINA = """{data: {disponivel: true, referencia: '2026-10-27', atualizacao: '2026-10-27T07:41:30',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-10-27', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card2_e_awaiting_payment_e_card1_segue_pending_signature(rodar):
    assert rodar("return [m.STATUS_CARD1, m.STATUS_CARD2, m.STATUS_DE_FOTO];") == [
        "pending_signature", "awaiting_payment", ["pending_signature", "awaiting_payment"]]


def test_proposta_do_card2_tem_status_e_chave_proprios(rodar):
    r = rodar(ITEM + """
      const c1 = m.propostaDoCard1(item({id_foto: 5}), '2026-10-27', null);
      const c2 = m.propostaDoCard1(item({id_foto: 5}), '2026-10-27', null, m.STATUS_CARD2);
      return [c1.status, c1.id, c2.status, c2.id, c2.foto.assinatura, c2.foto.pago];""")
    assert r == ["pending_signature", "pio1-5", "awaiting_payment", "pio2-5", "CO", "N"]


def test_lista_do_card2_usa_a_foto_com_o_status_do_card2(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD2);
      return {{chamadas, total: lista.total, deFoto: lista.deFoto,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "status": ["awaiting_payment"]}


def test_sem_status_a_lista_continua_a_do_card1(rodar):
    r = rodar(ITEM + f"""
      const lista = m.listaDoCard(true, {{isPending: false, isFetching: false}}, () => ({{}}), {RESUMO}, {PAGINA});
      return lista.propostas.map(p => p.status);""")
    assert set(r) == {"pending_signature"}


def test_componentes_ligam_o_card2_a_foto():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard2" in corpo and "usePropostasCard2" in corpo, arq
        assert "STATUS_CARD2" in corpo, arq
        assert "delete reais[STATUS_CARD2]" in corpo, arq   # nunca a contagem legada
        assert "usePropostasPio(emCard1 || emCard2 ? undefined" in corpo, arq


def test_hooks_do_card2_leem_os_endpoints_do_card2():
    corpo = _fonte(CAIXA / "lib" / "pioCard2.ts")
    assert "/pio/card2/resumo" in corpo and "/pio/card2/propostas" in corpo
    assert "/pio/card1" not in corpo
    assert "data: referencia" in corpo        # mesma foto do resumo na lista


def test_router_do_card2_registrado_em_main():
    main = (RAIZ / "api" / "main.py").read_text(encoding="utf-8")
    assert main.count("pio_card2") == 2          # import + lista de include


def test_aviso_de_foto_ausente_nomeia_o_card_pelo_status():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "Nenhuma foto do Card 1" not in corpo, arq
        assert "Ainda não há foto publicada para {STATUS_LABEL_CURTO[selectedStatus as StatusWorkflow]}" in corpo, arq
