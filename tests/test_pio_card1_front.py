"""Front do Card 1 (RITM0117336): a lógica pura de `card1Foto.ts` exercitada no node.

O front não tem test runner; o módulo é puro justamente para isso (compilado com
`tsc` e chamado pelo `node`, como `test_pio_regiao.py`). Prende:

  1. A chave da lista é `id_foto` (a query aceita pode repetir a proposta).
  2. Contato ausente fica VAZIO/`null`, nunca o texto "null"/"None"; o WhatsApp é
     o celular e nunca o residencial.
  3. O estado da foto usa só os códigos documentados; código novo aparece cru.
  4. `listaDoCard`: o Card 1 usa a foto e NÃO chama o mapeador legado; os outros
     cards seguem exatamente a carga legada.
  5. O contexto "Card 1" dos diálogos compartilhados vem de uma prop explícita
     (`foto`), nunca de `status` — a busca global também abre `pending_signature`.
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
    tmp = tempfile.mkdtemp(prefix="card1foto-")
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
  cidade: 'X', uf: 'SP', idade: 46, situacao: 'AT', assinatura: 'PE', pago: 'N',
  contato: { email: null, celular: null, residencial: null }, ...o });"""


def test_chave_da_lista_e_id_foto_e_proposta_repetida_nao_colide(rodar):
    ids = rodar(ITEM + """
      const a = m.propostaDoCard1(item({id_foto: 5}), '2026-10-27', null);
      const b = m.propostaDoCard1(item({id_foto: 6}), '2026-10-27', null);
      return [a.id, b.id, a.number, b.number];""")
    assert ids[0] != ids[1] and ids[2] == ids[3] == "SIM01"


def test_premio_em_real_pt_br_e_data_sem_deslocar_dia(rodar):
    p = rodar(ITEM + """
      const x = m.propostaDoCard1(item(), '2026-10-27', null);
      return [x.value.replace(/\\u00a0/g, ' '), x.date, m.formatarMoeda(680155.27).replace(/\\u00a0/g, ' ')];""")
    assert p == ["R$ 100,25", "20/10/2026", "R$ 680.155,27"]


def test_contato_ausente_vira_vazio_nunca_o_texto_null_ou_none(rodar):
    p = rodar(ITEM + """
      const x = m.propostaDoCard1(item(), null, null);
      return [x.email, x.phone, x.foto.contato];""")
    assert p[0] == "" and p[1] == ""
    assert p[2] == {"email": None, "celular": None, "residencial": None}


def test_canais_de_envio_whatsapp_e_so_celular(rodar):
    c = rodar("""
      return [
        m.canaisDeEnvio({email: 'a@b', celular: '(11) 9', residencial: '(11) 3'}),
        m.canaisDeEnvio({email: null, celular: '(11) 9', residencial: null}),
        m.canaisDeEnvio({email: null, celular: null, residencial: '(11) 3'}),
        m.canaisDeEnvio({email: null, celular: null, residencial: null}),
      ];""")
    assert c[0] == {"email": "a@b", "telefone": "(11) 3", "whatsapp": "(11) 9"}
    assert c[1] == {"email": None, "telefone": "(11) 9", "whatsapp": "(11) 9"}
    assert c[2] == {"email": None, "telefone": "(11) 3", "whatsapp": None}   # fixo não recebe WhatsApp
    assert c[3] == {"email": None, "telefone": None, "whatsapp": None}


def test_estado_da_foto_so_codigos_documentados(rodar):
    e = rodar("""
      const f = (s, a, p) => m.estadoDaFoto({idFoto: 1, referencia: null, atualizacao: null,
        situacao: s, assinatura: a, pago: p, contato: {email: null, celular: null, residencial: null}})
        .map(x => x.valor);
      return [f('AT', 'PE', 'N'), f('ZZ', 'XX', 'Q'), f('', '', '')];""")
    assert e[0] == ["Pendente de assinatura", "Não pago", "Ativa"]
    assert e[1] == ["XX", "Q", "ZZ"]                    # código desconhecido aparece CRU
    assert e[2] == ["Não informado"] * 3


def test_lista_do_card1_usa_a_foto_e_nao_chama_o_mapeador_legado(rodar):
    r = rodar(ITEM + """
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {data: {disponivel: true, referencia: 'LEGADO', total: 99, itens: [{}]}, isPending: false, isFetching: false},
        () => { chamadas++; return {}; },
        {data: {disponivel: true, referencia: '2026-10-27', atualizacao: null, desatualizado: false}, isPending: false},
        {data: {disponivel: true, referencia: '2026-10-27', atualizacao: '2026-10-27T07:41:30', desatualizado: false,
                dias_defasagem: 0, total: 3, limite: 50, offset: 0, detalhe_disponivel: true,
                itens: [item({id_foto: 1}), item({id_foto: 2}), item({id_foto: 3})]}, isPending: false, isFetching: false});
      return {chamadas, total: lista.total, n: lista.propostas.length, ref: lista.referencia, deFoto: lista.deFoto};""")
    assert r == {"chamadas": 0, "total": 3, "n": 3, "ref": "2026-10-27", "deFoto": True}


def test_lista_dos_outros_cards_segue_a_carga_legada(rodar):
    r = rodar("""
      const lista = m.listaDoCard(false,
        {data: {disponivel: true, referencia: '2026-10-27', total: 8706, itens: [{n: 1}, {n: 2}]}, isPending: false, isFetching: false},
        (i) => ({id: 'legado-' + i.n}),
        {data: {disponivel: true, referencia: 'CARD1', quantidade: 3}, isPending: false},
        {data: undefined, isPending: true, isFetching: false});
      return {total: lista.total, ids: lista.propostas.map(p => p.id), deFoto: lista.deFoto, ref: lista.referencia};""")
    assert r == {"total": 8706, "ids": ["legado-1", "legado-2"], "deFoto": False, "ref": "2026-10-27"}


def test_sem_foto_publicada_nao_fica_consultando_para_sempre(rodar):
    r = rodar("""
      const lista = m.listaDoCard(true,
        {data: undefined, isPending: true, isFetching: false}, () => ({}),
        {data: {disponivel: true, referencia: null}, isPending: false},
        {data: undefined, isPending: true, isFetching: false});
      return {carregando: lista.carregando, disponivel: lista.disponivel, n: lista.propostas.length};""")
    assert r == {"carregando": False, "disponivel": True, "n": 0}


def test_resumo_em_leitura_ou_com_falha_sinaliza_sem_inventar(rodar):
    r = rodar("""
      const mk = (resumo) => m.listaDoCard(true, {data: undefined, isPending: true, isFetching: false}, () => ({}),
        resumo, {data: undefined, isPending: true, isFetching: false});
      return [mk({data: undefined, isPending: true}).carregando,
              mk({data: {disponivel: false}, isPending: false}).disponivel];""")
    assert r == [True, False]


# ═══════════ contexto Card 1 explícito, e só ele ════════════════════════════

def test_dialogo_de_detalhe_usa_prop_foto_e_nao_o_status():
    corpo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "foto?: FotoCard1" in corpo
    assert 'proposal.status === "pending_signature"' not in corpo, (
        "o contexto do Card 1 não pode ser deduzido do status: a busca global também abre pending_signature")
    assert "{foto && <CampoInfo" in corpo and "Nº da Proposta" in corpo


def test_card1_oculta_usuario_e_rodape_e_os_outros_cards_mantem():
    """Pedido do Carlos (27/10): no Card 1 o campo Usuário e o rodapé com o ponto
    verde saem da tela. Só com `foto`; sem ela o diálogo é o de sempre."""
    corpo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    antes_usuario = corpo.index('rotulo="Usuário:"')
    assert "{!foto && (" in corpo[antes_usuario - 120:antes_usuario]
    ponto = corpo.index("bg-emerald-500")
    assert "{!foto && (" in corpo[ponto - 900:ponto], "o rodapé deve sair só no Card 1"
    assert "aria-disabled" not in corpo and "opacity-50" not in corpo


def test_quem_passa_foto_e_so_a_lista_do_card1():
    inline = _fonte(CAIXA / "components" / "InlineWorkflow.tsx")
    assert "foto={selectedProposal.foto}" in inline
    busca = _fonte(CAIXA / "components" / "SearchProposals.tsx")
    assert "foto=" not in busca and "canaisDeEnvio" not in busca, "a busca global segue no legado"
    # só o mapeamento do Card 1 preenche `foto`
    for arq in (CAIXA / "lib" / "pio.ts",):
        assert "foto:" not in _fonte(arq)


def test_enviar_so_muda_com_contatos_do_card1():
    corpo = _fonte(CAIXA / "components" / "ResendLinkDialog.tsx")
    assert "Boolean(contatos) && !v" in corpo
    assert "Contato não informado" in corpo


def test_router_do_card1_registrado_em_main():
    main = (RAIZ / "api" / "main.py").read_text(encoding="utf-8")
    assert main.count("pio_card1") == 2          # import + lista de include


def test_foto_desatualizada_nao_gera_texto_fixo_so_o_tooltip():
    """Decisão do Carlos (28/10): depois da meia-noite, "foto de XX" no card e o
    aviso "Esta foto não é de hoje…" pareciam erro. A data da foto fica só no
    tooltip (`title`) do card."""
    for arq in ("Card1Valor.tsx", "InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "não é de hoje" not in corpo, arq
        assert "foto de {" not in corpo, arq
    assert "title={titulo}" in _fonte(CAIXA / "components" / "Card1Valor.tsx")
