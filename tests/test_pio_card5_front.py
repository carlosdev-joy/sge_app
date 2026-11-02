"""Front do Card 5 (Emitidas, VG + AP): reaproveita a lógica pura do Card 1.

Prende: status `emission_sent`, chave `pio5-`, selo por situação (azul emitida, amarelo
cobertura suspensa, vermelho cancelada), estado da foto próprio, motivo do cancelamento
no Resumo do Seguro e a ligação dos componentes a `/pio/card5/*`. Cards 1–4 inalterados.
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
    tmp = tempfile.mkdtemp(prefix="card5foto-")
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
  matricula: '12345', data_venda: '2026-10-16', dias_pendente: 0, produto: 'VIDA', area_produto: 'Vida em Grupo',
  premio: 100.25, imp_segurada: 50000, renda: null, cidade: '', uf: '', idade: 46, situacao: '', assinatura: '', pago: '',
  sub_situacao: 'Integrada', tom_status: 'emitida', segmento: 'VG', emissao: '2026-10-18', inativo: false,
  cancelamento: null, motivo_cancelamento: null,
  contato: { email: null, celular: null, residencial: null }, ...o });"""
PAGINA = """{data: {disponivel: true, referencia: '2026-11-02', atualizacao: '2026-11-02T07:41:30',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-11-02', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card5_e_emission_sent_e_entra_nos_cards_de_foto(rodar):
    assert rodar("return [m.STATUS_CARD5, m.STATUS_DE_FOTO.includes(m.STATUS_CARD5)];") == ["emission_sent", True]


def test_proposta_do_card5_tem_chave_propria_sem_dias_pendente_e_leva_a_emissao(rodar):
    r = rodar(ITEM + """
      const p = m.propostaDoCard1(item({id_foto: 5, dias_pendente: 9}), '2026-11-02', null, m.STATUS_CARD5);
      return [p.id, p.status, p.number, p.daysInPending, p.foto.emitida.tom, p.foto.emitida.segmento,
              p.foto.emitida.subSituacao, p.foto.emitida.motivo, 'criticas' in p.foto];""")
    assert r == ["pio5-5", "emission_sent", "1000000000001", 0, "emitida", "VG", "Integrada", None, False]


def test_selo_cor_por_tom_e_rotulo_e_a_situacao_real(rodar):
    r = rodar(ITEM + """
      const sel = (o) => { const p = m.propostaDoCard1(item(o), '2026-11-02', null, m.STATUS_CARD5);
                           const s = m.seloDaProposta(p, 'bg-blue-600', 'Emitida'); return [s.classe, s.rotulo]; };
      const velho = m.propostaDoCard1({...item(), tom_status: undefined}, '2026-11-02', null);
      return [sel({}), sel({tom_status: 'suspensa', sub_situacao: 'Cobertura Suspensa'}),
              sel({tom_status: 'cancelada', sub_situacao: 'Cancelada após Aceitação'}),
              sel({sub_situacao: ''}), m.seloDaProposta(velho, 'bg-amber-600', 'Pendente')];""")
    assert r[0] == ["bg-blue-600 text-white", "Integrada"]
    assert r[1] == ["bg-amber-400 text-slate-900", "Cobertura Suspensa"]
    assert r[2] == ["bg-red-700 text-white", "Cancelada após Aceitação"]
    assert r[3] == ["bg-blue-600 text-white", "Emitida"]            # sem situação: cai no rótulo do card
    assert r[4] == {"classe": "bg-amber-600 text-white", "rotulo": "Pendente"} or r[4] == ["bg-amber-600 text-white", "Pendente"]


def test_estado_da_foto_do_card5_e_o_dele_e_o_dos_outros_nao_muda(rodar):
    r = rodar("""
      const base = {idFoto: 1, referencia: null, atualizacao: null, situacao: '', assinatura: '', pago: '',
        contato: {email: null, celular: null, residencial: null}};
      const c = (emissao) => m.estadoDaFoto({...base, emitida: {tom: 'emitida', segmento: 'AP', subSituacao: 'Ativo',
        emissao, inativo: false, cancelamento: null, motivo: null}}).map(x => [x.rotulo, x.valor]);
      return [c('2026-10-18'), c(null), m.estadoDaFoto({...base, situacao: 'AT', assinatura: 'CO', pago: 'S'}).map(x => x.rotulo)];""")
    assert r[0] == [["Situação", "Ativo"], ["Emissão", "18/10/2026"], ["Segmento", "Acidentes Pessoais"]]
    assert r[1][1] == ["Emissão", "Não informada"]
    assert r[2] == ["Assinatura", "Pagamento", "Situação"]


def test_lista_do_card5_usa_a_foto_e_nao_chama_o_legado(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD5);
      return {{chamadas, total: lista.total, deFoto: lista.deFoto,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "status": ["emission_sent"]}


def test_componentes_ligam_o_card5_a_foto():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard5" in corpo and "usePropostasCard5" in corpo, arq
        assert "delete reais[STATUS_CARD5]" in corpo, arq
        assert "emCard5" in corpo and "[STATUS_CARD5]: resumoCard5" in corpo, arq
        assert "seloDaProposta(" in corpo, f"{arq}: a lista precisa do selo por situação"


def test_hooks_do_card5_leem_os_endpoints_do_card5():
    corpo = _fonte(CAIXA / "lib" / "pioCard5.ts")
    assert "/pio/card5/resumo" in corpo and "/pio/card5/propostas" in corpo
    assert not any(f"/pio/card{n}" in corpo for n in (1, 2, 3, 4))
    assert "data: referencia" in corpo


def test_resumo_do_seguro_do_card5_rotulo_e_motivo_por_ultimo():
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "Proposta/Certificado:" in dialogo and "foto?.emitida?.inativo" in dialogo
    venda = dialogo[dialogo.index('titulo="Dados da Venda"'):dialogo.index('titulo="Dados do Segurado"')]
    assert venda.index("Nº da Proposta") < venda.index("Usuário:") < venda.index("Motivo do Cancelamento:")
    assert "Não informado na origem" in venda          # sem motivo na fonte: diz, não some
