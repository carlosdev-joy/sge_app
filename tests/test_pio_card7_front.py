"""Front do Card 7 (Devolução de Prêmio, VG + AP): reaproveita a lógica pura do Card 1.

Prende: status `refund_scheduled`, chave `pio7-`, selo com o status REAL do movimento na cor do
sub-card, os 3 sub-cards (a lista só abre após o clique em um deles), lista de UM sub-card,
Resumo com dados da devolução e linha do tempo da devolução, dados bancários só no Resumo, e a
ligação dos componentes a `/pio/card7/*`. Cards 1–6 inalterados.
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
    tmp = tempfile.mkdtemp(prefix="card7foto-")
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
  id_foto: 1, segmento: 'VG', proposta: '1000000000001', nome: 'CLIENTE FICTICIO', cpf: '01234567890', agencia: '316',
  matricula: '12345', data_venda: '2026-10-01', dias_pendente: 0, produto: 'VIDA', area_produto: '',
  premio: 250.5, imp_segurada: null, renda: null, cidade: '', uf: '', idade: 46, situacao: '', assinatura: '', pago: '',
  sub_situacao: '', contato: { email: null, celular: null, residencial: null },
  devolucao: { situacao: 'realizada', status: 'Devolvido', retorno: 'Crédito Efetivado', data_movimento: '2026-10-20', declinio: '2026-10-15' },
  ...o });"""
PAGINA = """{data: {disponivel: true, referencia: '2026-11-02', atualizacao: '2026-11-02T07:41:30',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-11-02', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card7_e_refund_scheduled_e_entra_nos_cards_de_foto(rodar):
    assert rodar("return [m.STATUS_CARD7, m.STATUS_DE_FOTO.includes(m.STATUS_CARD7)];") == ["refund_scheduled", True]


def test_proposta_do_card7_tem_chave_propria_sem_dias_e_leva_a_devolucao(rodar):
    r = rodar(ITEM + """
      const p = m.propostaDoCard1(item({id_foto: 5, dias_pendente: 9}), '2026-11-02', null, m.STATUS_CARD7);
      const velho = m.propostaDoCard1(item({devolucao: undefined}), '2026-11-02', null);
      return [p.id, p.status, p.number, p.daysInPending, p.value, p.foto.devolucao.situacao, p.foto.devolucao.segmento,
              p.foto.devolucao.status, p.foto.devolucao.dataMovimento, 'devolucao' in velho.foto];""")
    assert r == ["pio7-5", "refund_scheduled", "1000000000001", 0, "R$\u00a0250,50", "realizada", "VG", "Devolvido", "2026-10-20", False]


def test_selo_mostra_o_status_real_na_cor_do_subcard(rodar):
    r = rodar(ITEM + """
      const sel = (o) => { const p = m.propostaDoCard1(item(o), '2026-11-02', null, m.STATUS_CARD7);
                           const s = m.seloDaProposta(p, 'bg-amber-700', 'Devolução de Prêmio'); return [s.classe, s.rotulo]; };
      const d = (situacao, status) => ({devolucao: {situacao, status, retorno: '', data_movimento: null, declinio: null}});
      return [sel({}), sel(d('andamento', 'Processando')), sel(d('pendente', 'Sem Movimento')), sel(d('pendente', ''))];""")
    assert r[0] == ["bg-emerald-600 text-white", "Devolvido"]
    assert r[1] == ["bg-amber-600 text-white", "Processando"]
    assert r[2] == ["bg-red-700 text-white", "Sem Movimento"]
    assert r[3] == ["bg-red-700 text-white", "Devolução Pendente"]            # sem status: o rótulo do sub-card


def test_estado_da_foto_do_card7_e_o_dele_e_o_dos_outros_nao_muda(rodar):
    r = rodar("""
      const base = {idFoto: 1, referencia: null, atualizacao: null, situacao: '', assinatura: '', pago: '',
        contato: {email: null, celular: null, residencial: null}};
      const c = (s, dia) => m.estadoDaFoto({...base, devolucao: {situacao: s, segmento: 'VG', status: 'Processando',
        retorno: '', dataMovimento: dia, declinio: null}}).map(x => [x.rotulo, x.valor]);
      const velho = m.estadoDaFoto({...base, situacao: 'AT', assinatura: 'CO', pago: 'S'}).map(x => x.rotulo);
      return [c('andamento', '2026-11-05'), c('realizada', null), velho];""")
    assert r[0] == [["Situação", "Devolução em Andamento"], ["Movimento", "Processando"], ["Previsão", "05/11/2026"]]
    assert r[1][2] == ["Data", "Não informada"]
    assert r[2] == ["Assinatura", "Pagamento", "Situação"]


def test_lista_do_card7_usa_a_foto_e_nao_chama_o_legado(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD7);
      return {{chamadas, total: lista.total, deFoto: lista.deFoto,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "status": ["refund_scheduled"]}


def test_componentes_ligam_o_card7_a_foto_e_escondem_a_lista_sem_subcard():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard7" in corpo and "usePropostasCard7" in corpo, arq
        assert "delete reais[STATUS_CARD7]" in corpo and "emCard7" in corpo, arq
        assert "[STATUS_CARD7]: resumoCard7" in corpo and "<DevolucaoSubcards" in corpo, arq
        assert "const semLista = emCard7 && devolucao === null" in corpo, arq
        assert "setDevolucao(null)" in corpo, arq                    # trocar de card limpa o sub-card
        # nenhum aviso de lista aparece enquanto não há sub-card escolhido
        assert "{cardSelecionado && lista." not in corpo and "{lista.deFoto && lista." not in corpo, arq


def test_hooks_do_card7_leem_os_endpoints_do_card7_e_a_lista_exige_subcard():
    corpo = _fonte(CAIXA / "lib" / "pioCard7.ts")
    assert "/pio/card7/resumo" in corpo and "/pio/card7/propostas" in corpo and "/pio/card7/devolucao" in corpo
    assert not any(f"/pio/card{n}" in corpo for n in (1, 2, 3, 4, 5, 6))
    assert "situacao !== null" in corpo and "data: referencia" in corpo


def test_subcards_somam_o_card_e_nao_inventam_valor():
    comp = _fonte(CAIXA / "components" / "DevolucaoSubcards.tsx")
    assert 'SITUACOES: SituacaoDevolucao[] = ["realizada", "andamento", "pendente"]' in comp
    assert "aria-pressed" in comp and "onSelecionar(ativo ? null : s)" in comp      # clicar de novo desmarca
    assert 'bloco.valor === null && bloco.quantidade > 0 ? "—"' in comp           # desconhecido ≠ R$ 0,00
    assert "não são zero" in comp and "Ainda não há foto" in comp


def test_resumo_da_devolucao_traz_banco_so_no_resumo_e_nao_inventa_contato():
    comp = _fonte(CAIXA / "components" / "DevolucaoCard7.tsx")
    for campo in ("Valor devolvido", "Status da devolução", "Data prevista para crédito", "Data do crédito",
                  "Instituição financeira", "Agência", "Operação", "Conta", "Dígito da conta"):
        assert campo in comp, campo
    assert comp.count("Não disponível nesta foto") >= 1 and "E-mail do cliente" in comp and "Celular do cliente" in comp
    assert "não estão vazios" in comp                                              # erro ≠ vazio
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "<DevolucaoCard7" in dialogo and "!foto?.devolucao && <CampoInfo" in dialogo
    # os dados bancários não passam pelo mapeamento da lista
    puro = _fonte(PURO)
    import re
    lista = puro.split("export interface DevolucaoDetalhe")[0]
    for proibido in (r"NUM_CONTA", r"\bconta\b", r"digito_conta", r"\bbanco\b", r"COD_BANCO"):
        assert not re.search(proibido, lista), proibido


def test_linha_do_tempo_da_devolucao_e_o_fluxo_ate_a_devolucao_com_o_estado_real():
    """Desde 02/11 o Resumo mostra o FLUXO inteiro (tests/test_fluxo_proposta.py); a etapa atual é o sub-card."""
    tl = _fonte(CAIXA / "components" / "ProposalTimeline.tsx")
    assert "refundStep?: 0 | 1 | 2" in tl and "const etapa = refundStep ?? 1" in tl        # o fluxo antigo (Acompanhamento) segue
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "atualDoFluxo(foto)" in dialogo
    assert "ROTULO_SUBCARD_DEVOLUCAO[d.situacao]" in _fonte(CAIXA / "lib" / "card1Foto.ts")


def test_resumo_trata_zeros_como_nao_informado_menos_o_digito_da_conta():
    comp = _fonte(CAIXA / "components" / "DevolucaoCard7.tsx")
    for campo in ("d.banco", "d.agencia", "d.operacao", "d.conta"):
        assert f"presente({campo})" in comp, campo
    assert "presente(d.digito_conta)" not in comp and "d.digito_conta ?? NAO_INFORMADO" in comp   # 0 é dígito válido


def test_gerenciar_devolucao_so_no_subcard_pendente_e_botao_do_dialogo_renomeado():
    """Pedido do Carlos (03/11): sem o botão nos sub-cards verde (Realizada) e laranja (em Andamento)."""
    corpo = _fonte(CAIXA / "components" / "InlineWorkflow.tsx")
    i = corpo.index('statusAtual === "refund_scheduled" &&')
    bloco = corpo[i:corpo.index("Gerenciar Devolução", i) + 20]
    assert 'proposta.foto?.devolucao?.situacao !== "realizada"' in bloco
    assert 'proposta.foto?.devolucao?.situacao !== "andamento"' in bloco
    assert "setRefundDialogOpen" in bloco                           # no pendente (e nas de exemplo) o botão segue abrindo o diálogo
    dialogo = _fonte(CAIXA / "components" / "RefundManagementDialog.tsx")
    assert "Salvar Dados Bancários" in dialogo and "Programar Devolução" not in dialogo
    assert '"Processando..."' in dialogo


def test_workflow_da_tela_principal_abre_por_padrao():
    corpo = _fonte(CAIXA / "components" / "InlineWorkflow.tsx")
    assert "const [isExpanded, setIsExpanded] = useState(true);" in corpo
    assert "setIsExpanded(!isExpanded)" in corpo                    # a barra ainda recolhe

