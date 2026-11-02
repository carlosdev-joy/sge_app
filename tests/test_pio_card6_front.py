"""Front do Card 6 (Rejeitadas, Vida em Grupo): reaproveita a lógica pura do Card 1.

Prende: status `declined`, chave `pio6-`, sem "dias" ao lado de Rejeitada, estado da foto próprio
(situação, motivos, declínio, quitação), motivos no Resumo como ÚLTIMA informação de Dados da
Venda, botão "Gerenciar Devolução" fora da rejeitada, Workflow terminando em "Proposta
Rejeitada" e a ligação dos componentes a `/pio/card6/*`. Cards 1–5 inalterados.
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
    tmp = tempfile.mkdtemp(prefix="card6foto-")
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
  matricula: '12345', data_venda: '2026-10-01', dias_pendente: 0, produto: 'VIDA', area_produto: 'Vida em Grupo',
  premio: 100.25, imp_segurada: 50000, renda: null, cidade: '', uf: '', idade: 46, situacao: '', assinatura: '', pago: '',
  sub_situacao: 'Não Aceita', motivos: 4, quitacao: '2026-10-08', declinio: '2026-10-20', dias_venda_declinio: 12,
  contato: { email: null, celular: null, residencial: null }, ...o });"""
PAGINA = """{data: {disponivel: true, referencia: '2026-11-02', atualizacao: '2026-11-02T07:41:30',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-11-02', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card6_e_declined_e_entra_nos_cards_de_foto(rodar):
    assert rodar("return [m.STATUS_CARD6, m.STATUS_DE_FOTO.includes(m.STATUS_CARD6)];") == ["declined", True]


def test_proposta_do_card6_tem_chave_propria_sem_dias_e_leva_os_motivos(rodar):
    r = rodar(ITEM + """
      const p = m.propostaDoCard1(item({id_foto: 5, dias_pendente: 9}), '2026-11-02', null, m.STATUS_CARD6);
      const c1 = m.propostaDoCard1(item({id_foto: 5, motivos: undefined}), '2026-11-02', null);
      return [p.id, p.status, p.number, p.daysInPending, p.foto.rejeitada.motivos, p.foto.rejeitada.declinio,
              p.foto.rejeitada.diasVendaDeclinio, p.foto.rejeitada.quitacao, 'criticas' in p.foto, 'emitida' in p.foto,
              'rejeitada' in c1.foto];""")
    assert r == ["pio6-5", "declined", "1000000000001", 0, 4, "2026-10-20", 12, "2026-10-08", False, False, False]


def test_estado_da_foto_do_card6_e_o_dele_e_o_dos_outros_nao_muda(rodar):
    r = rodar("""
      const base = {idFoto: 1, referencia: null, atualizacao: null, situacao: '', assinatura: '', pago: '',
        contato: {email: null, celular: null, residencial: null}};
      const c = (d, q) => m.estadoDaFoto({...base, rejeitada: {subSituacao: 'Não Aceita', motivos: 3, quitacao: q,
        declinio: d, diasVendaDeclinio: null}}).map(x => [x.rotulo, x.valor]);
      const velho = m.estadoDaFoto({...base, situacao: 'AT', assinatura: 'CO', pago: 'S'}).map(x => x.rotulo);
      return [c('2026-10-20', '2026-10-08'), c(null, null), velho];""")
    assert r[0] == [["Situação", "Não Aceita"], ["Motivos", "3"], ["Declínio", "20/10/2026"], ["Quitação", "08/10/2026"]]
    assert r[1][2:] == [["Declínio", "Não informado"], ["Quitação", "Não informada"]]
    assert r[2] == ["Assinatura", "Pagamento", "Situação"]


def test_lista_do_card6_usa_a_foto_e_nao_chama_o_legado(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD6);
      return {{chamadas, total: lista.total, deFoto: lista.deFoto,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "status": ["declined"]}


def test_componentes_ligam_o_card6_a_foto():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard6" in corpo and "usePropostasCard6" in corpo, arq
        assert "delete reais[STATUS_CARD6]" in corpo, arq
        assert "emCard6" in corpo and "[STATUS_CARD6]: resumoCard6" in corpo, arq


def test_hooks_do_card6_leem_os_endpoints_do_card6():
    corpo = _fonte(CAIXA / "lib" / "pioCard6.ts")
    assert "/pio/card6/resumo" in corpo and "/pio/card6/propostas" in corpo and "/pio/card6/motivos" in corpo
    assert not any(f"/pio/card{n}" in corpo for n in (1, 2, 3, 4, 5))
    assert "data: referencia" in corpo and "certificado" in corpo


def test_gerenciar_devolucao_sai_da_rejeitada_e_fica_na_devolucao():
    corpo = _fonte(CAIXA / "components" / "InlineWorkflow.tsx")
    i = corpo.index("Gerenciar Devolução")
    assert 'statusAtual === "refund_scheduled" && (' in corpo[i - 200:i]
    assert 'statusAtual === "declined"' not in corpo[i - 200:i]


def test_motivos_sao_a_ultima_informacao_de_dados_da_venda_e_so_com_foto_do_card6():
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "foto?.rejeitada" in dialogo and "<MotivosCard6" in dialogo
    venda = dialogo[dialogo.index('titulo="Dados da Venda"'):dialogo.index('titulo="Dados do Segurado"')]
    assert venda.index("Usuário:") < venda.index("<MotivosCard6")
    comp = _fonte(CAIXA / "components" / "MotivosCard6.tsx")
    assert "não está vazia" in comp and "Nenhum motivo" in comp          # erro ≠ vazio
    for acao in ("Upload", "Samplemed", "href="):
        assert acao not in comp, "nenhuma ação é inferida do texto do motivo"


def test_workflow_da_rejeitada_termina_no_status_real():
    tl = _fonte(CAIXA / "components" / "ProposalTimeline.tsx")
    bloco = tl[tl.index('currentStatus === "declined"'):tl.index("if (isExceptionFlow)")]
    assert "Proposta Rejeitada" in bloco and "Proposta Emitida" not in bloco and "VERMELHO" in bloco


def test_valor_longo_encolhe_no_celular_em_vez_de_quebrar_no_meio_do_numero():
    """O prêmio do Card 5/6 ("R$ 492.469.590,63") quebrava no meio no card estreito do celular."""
    corpo = _fonte(CAIXA / "components" / "Card1Valor.tsx")
    assert "tamanhoDoValor(valorTexto, destaque)" in corpo
    # classes literais (o Tailwind só gera o que está escrito inteiro)
    assert '"sm:text-lg"' in corpo and '"sm:text-xl"' in corpo and "text-sm" in corpo and "text-base" in corpo
