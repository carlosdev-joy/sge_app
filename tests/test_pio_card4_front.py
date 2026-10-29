"""Front do Card 4 (Em Análise): reaproveita a lógica pura do Card 1.

Prende: status `in_analysis`, chave `pio4-`, estado da foto próprio (situação,
críticas, quitação — a fonte não tem assinatura/pagamento), `listaDoCard` pela
foto e os componentes ligando o Card 4 a `/pio/card4/*`. Cards 1–3 inalterados.
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
    tmp = tempfile.mkdtemp(prefix="card4foto-")
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
  id_foto: 1, proposta: '1000000000001', nome: 'CLIENTE FICTICIO', cpf: '01234567890', agencia: '316',
  matricula: '12345', data_venda: '2026-10-16', dias_pendente: 13, produto: 'VIDA', area_produto: 'Vida em Grupo',
  premio: 100.25, imp_segurada: 50000, renda: null, cidade: '', uf: '', idade: 46, situacao: '', assinatura: '', pago: '',
  sub_situacao: 'Em Crítica', criticas: 3, quitacao: null,
  contato: { email: null, celular: null, residencial: null }, ...o });"""
PAGINA = """{data: {disponivel: true, referencia: '2026-10-29', atualizacao: '2026-10-29T07:41:30',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-10-29', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card4_e_in_analysis_e_entra_nos_cards_de_foto(rodar):
    assert rodar("return [m.STATUS_CARD4, m.STATUS_DE_FOTO];") == [
        "in_analysis", ["pending_signature", "awaiting_payment", "paid", "in_analysis"]]


def test_proposta_do_card4_tem_chave_propria_e_leva_as_criticas(rodar):
    r = rodar(ITEM + """
      const p = m.propostaDoCard1(item({id_foto: 5}), '2026-10-29', null, m.STATUS_CARD4);
      const c1 = m.propostaDoCard1(item({id_foto: 5, criticas: undefined}), '2026-10-29', null);
      return [p.id, p.status, p.number, p.foto.criticas, p.foto.subSituacao, p.foto.quitacao,
              p.daysInPending, p.region, 'criticas' in c1.foto];""")
    assert r == ["pio4-5", "in_analysis", "1000000000001", 3, "Em Crítica", None, 13, "", False]


def test_estado_da_foto_do_card4_e_o_dele_e_o_dos_outros_nao_muda(rodar):
    r = rodar("""
      const c = (q) => m.estadoDaFoto({idFoto: 1, referencia: null, atualizacao: null, situacao: '', assinatura: '',
        pago: '', criticas: 2, subSituacao: 'Aguardando Proposta Física', quitacao: q,
        contato: {email: null, celular: null, residencial: null}}).map(x => [x.rotulo, x.valor]);
      const velho = m.estadoDaFoto({idFoto: 1, referencia: null, atualizacao: null, situacao: 'AT',
        assinatura: 'CO', pago: 'S', contato: {email: null, celular: null, residencial: null}}).map(x => x.rotulo);
      return [c(null), c('2026-10-20'), velho];""")
    assert r[0] == [["Situação", "Aguardando Proposta Física"], ["Críticas", "2"], ["Quitação", "Não informada"]]
    assert r[1][2] == ["Quitação", "20/10/2026"]
    assert r[2] == ["Assinatura", "Pagamento", "Situação"]


def test_lista_do_card4_usa_a_foto_e_nao_chama_o_legado(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD4);
      return {{chamadas, total: lista.total, deFoto: lista.deFoto,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "status": ["in_analysis"]}


def test_componentes_ligam_o_card4_a_foto():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard4" in corpo and "usePropostasCard4" in corpo, arq
        assert "delete reais[STATUS_CARD4]" in corpo, arq
        assert "emCard4" in corpo and "[STATUS_CARD4]: resumoCard4" in corpo, arq


def test_hooks_do_card4_leem_os_endpoints_do_card4():
    corpo = _fonte(CAIXA / "lib" / "pioCard4.ts")
    assert "/pio/card4/resumo" in corpo and "/pio/card4/propostas" in corpo
    assert not any(f"/pio/card{n}" in corpo for n in (1, 2, 3))
    assert "data: referencia" in corpo


def test_router_do_card4_registrado_em_main():
    main = (RAIZ / "api" / "main.py").read_text(encoding="utf-8")
    assert main.count("pio_card4") == 2


def test_pendencias_so_aparecem_com_foto_do_card4_e_leem_o_endpoint_do_card4():
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "foto?.criticas !== undefined" in dialogo and "<PendenciasCard4" in dialogo
    # abaixo de Dados do Segurado, antes do motivo de declínio
    assert dialogo.index('titulo="Dados do Segurado"') < dialogo.index("<PendenciasCard4") < dialogo.index("Motivo do Declínio")
    hook = _fonte(CAIXA / "lib" / "pioCard4.ts")
    assert "/pio/card4/pendencias" in hook and "certificado" in hook
    comp = _fonte(CAIXA / "components" / "PendenciasCard4.tsx")
    assert "não está vazia" in comp and "Nenhuma pendência" in comp      # erro ≠ vazio
    for acao in ("Upload", "Samplemed", "href="):
        assert acao not in comp, "ação por crítica depende do mapa de negócio, ainda não definido"
