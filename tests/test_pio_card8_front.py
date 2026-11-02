"""Front do Card 8 (Sensibilizações = último movimento Vida): reaproveita a lógica pura do Card 1.

Prende: status `sensitization_monitoring`, chave `pio8-`, sem "dias", selo com o status REAL do último
movimento, botão "Sensibilizar" (habilita pela regra do backend; o clique NÃO finge sucesso), lista por
nº de identificação, Resumo com valor/movimento/data de envio e sem dados do segurado, Workflow com os
DOIS estados reais e a ligação dos componentes a `/pio/card8/*`. Cards 1–7 inalterados.
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
    tmp = tempfile.mkdtemp(prefix="card8foto-")
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
  id_foto: 1, proposta: '123456789', nome: 'Vida em Grupo', cpf: '', agencia: '316', matricula: '12345',
  data_venda: '2025-12-01', dias_pendente: 0, produto: 'VIDA', area_produto: 'Vida em Grupo', premio: 120.4,
  imp_segurada: null, renda: null, cidade: '', uf: '', idade: null, situacao: '', assinatura: '', pago: '',
  sub_situacao: '', contato: { email: null, celular: null, residencial: null },
  sensibilizacao: { identificacao: '777000111', linha: 'VG', status_movimento: 'Enviada', status_movimento_codigo: 'ENV',
    status_atual: 'Enviado', status_atual_codigo: 'S', motivo: null, data_movimento: '2026-10-30',
    data_envio: '2026-10-31', pode_sensibilizar: false },
  ...o });"""
PAGINA = """{data: {disponivel: true, referencia: '2026-11-02', atualizacao: '2026-11-02T07:41:30', ordem: 'identificacao',
  desatualizado: false, dias_defasagem: 0, total: 2, limite: 50, offset: 0,
  detalhe_disponivel: true, itens: [item({id_foto: 1}), item({id_foto: 2})]},
  isPending: false, isFetching: false}"""
RESUMO = "{data: {disponivel: true, referencia: '2026-11-02', atualizacao: null, desatualizado: false}, isPending: false}"


def test_card8_e_sensitization_monitoring_e_entra_nos_cards_de_foto(rodar):
    assert rodar("return [m.STATUS_CARD8, m.STATUS_DE_FOTO.includes(m.STATUS_CARD8)];") == ["sensitization_monitoring", True]


def test_proposta_do_card8_tem_chave_propria_sem_dias_e_leva_a_sensibilizacao(rodar):
    r = rodar(ITEM + """
      const p = m.propostaDoCard1(item({id_foto: 5, dias_pendente: 9}), '2026-11-02', null, m.STATUS_CARD8);
      const velho = m.propostaDoCard1(item({sensibilizacao: undefined}), '2026-11-02', null);
      const s = p.foto.sensibilizacao;
      return [p.id, p.status, p.number, p.daysInPending, s.identificacao, s.statusMovimento, s.statusMovimentoCodigo,
              s.statusAtual, s.dataEnvio, s.dataMovimento, s.podeSensibilizar, 'sensibilizacao' in velho.foto];""")
    assert r == ["pio8-5", "sensitization_monitoring", "123456789", 0, "777000111", "Enviada", "ENV", "Enviado",
                 "2026-10-31", "2026-10-30", False, False]


def test_selo_mostra_o_status_real_do_ultimo_movimento(rodar):
    r = rodar(ITEM + """
      const sel = (o) => { const p = m.propostaDoCard1(item(o), '2026-11-02', null, m.STATUS_CARD8);
                           const s = m.seloDaProposta(p, 'bg-[#0F4C88]', 'Sensibilização'); return [s.classe, s.rotulo]; };
      const sens = (status) => ({sensibilizacao: {identificacao: '1', linha: 'VG', status_movimento: status, status_movimento_codigo: '',
        status_atual: 'x', status_atual_codigo: '', motivo: null, data_movimento: null, data_envio: null, pode_sensibilizar: true}});
      return [sel({}), sel(sens('Código não identificado')), sel(sens('Sem status')), sel(sens(''))];""")
    assert r[0] == ["bg-[#0F4C88] text-white", "Enviada"]
    assert r[1][1] == "Código não identificado" and r[2][1] == "Sem status"
    assert r[3][1] == "Sensibilização"                           # sem rótulo nenhum: o do card, nunca vazio


def test_estado_da_foto_do_card8_e_o_dele_e_o_dos_outros_nao_muda(rodar):
    r = rodar("""
      const base = {idFoto: 1, referencia: null, atualizacao: null, situacao: '', assinatura: '', pago: '',
        contato: {email: null, celular: null, residencial: null}};
      const c = (dia) => m.estadoDaFoto({...base, sensibilizacao: {identificacao: '1', linha: 'VG', statusMovimento: 'Enviada',
        statusMovimentoCodigo: 'ENV', statusAtual: 'Pendente', statusAtualCodigo: 'P', motivo: null, dataMovimento: dia,
        dataEnvio: null, podeSensibilizar: true}}).map(x => [x.rotulo, x.valor]);
      const velho = m.estadoDaFoto({...base, situacao: 'AT', assinatura: 'CO', pago: 'S'}).map(x => x.rotulo);
      return [c('2026-10-30'), c(null), velho];""")
    assert r[0] == [["Último movimento", "Enviada"], ["Data", "30/10/2026"], ["Situação da proposta", "Pendente"]]
    assert r[1][1] == ["Data", "Não informada"]
    assert r[2] == ["Assinatura", "Pagamento", "Situação"]


def test_lista_do_card8_usa_a_foto_leva_a_ordem_e_nao_chama_o_legado(rodar):
    r = rodar(ITEM + f"""
      let chamadas = 0;
      const lista = m.listaDoCard(true,
        {{data: {{disponivel: true, referencia: 'LEGADO', total: 99, itens: [{{}}]}}, isPending: false, isFetching: false}},
        () => {{ chamadas++; return {{}}; }},
        {RESUMO}, {PAGINA}, m.STATUS_CARD8);
      const legada = m.listaDoCard(false,
        {{data: {{disponivel: true, referencia: 'L', total: 1, itens: []}}, isPending: false, isFetching: false}},
        () => ({{}}), {RESUMO}, {PAGINA});
      return {{chamadas, total: lista.total, deFoto: lista.deFoto, ordem: lista.ordem, ordemLegada: legada.ordem,
               status: [...new Set(lista.propostas.map(p => p.status))]}};""")
    assert r == {"chamadas": 0, "total": 2, "deFoto": True, "ordem": "identificacao", "ordemLegada": None,
                 "status": ["sensitization_monitoring"]}


def test_componentes_ligam_o_card8_a_foto_e_a_ordem_nao_diz_mais_antigas():
    for arq in ("InlineWorkflow.tsx", "ProposalWorkflowSheet.tsx"):
        corpo = _fonte(CAIXA / "components" / arq)
        assert "useResumoCard8" in corpo and "usePropostasCard8" in corpo, arq
        assert "delete reais[STATUS_CARD8]" in corpo and "emCard8" in corpo, arq
        assert "[STATUS_CARD8]: resumoCard8" in corpo and "[STATUS_CARD8]: fotoCard8" in corpo, arq
        assert 'lista.ordem === "identificacao" ? "por nº de identificação" : "as mais antigas primeiro"' in corpo, arq


def test_hooks_do_card8_leem_os_endpoints_do_card8_sem_filtros():
    corpo = _fonte(CAIXA / "lib" / "pioCard8.ts")
    assert "/pio/card8/resumo" in corpo and "/pio/card8/propostas" in corpo
    assert not any(f"/pio/card{n}" in corpo for n in (1, 2, 3, 4, 5, 6, 7))
    assert "data: referencia" in corpo and "busca" not in corpo and "modo" not in corpo


def test_botao_sensibilizar_habilita_pela_regra_e_nao_finge_sucesso():
    corpo = _fonte(CAIXA / "components" / "InlineWorkflow.tsx")
    i = corpo.index('statusAtual === "sensitization_monitoring" && proposta.foto?.sensibilizacao')
    import re
    fim = re.search(r">\s*Sensibilizar\s*</Button>", corpo[i:])
    assert fim, "o botão precisa chamar-se Sensibilizar"
    bloco = corpo[i:i + fim.end()]
    assert "proposta.foto?.sensibilizacao" in bloco and "disabled={!proposta.foto.sensibilizacao.podeSensibilizar}" in bloco
    assert "toast.info(" in bloco and "toast.success" not in bloco and "Nenhum movimento foi enviado" in bloco
    # o botão simulado antigo só existe para propostas SEM foto (de exemplo)
    assert 'statusAtual === "sensitization_monitoring" && !proposta.foto?.sensibilizacao' in corpo


def test_resumo_mostra_valor_movimento_e_data_de_envio_e_nao_o_segurado():
    comp = _fonte(CAIXA / "components" / "SensibilizacaoCard8.tsx")
    for campo in ("Valor do prêmio", "Movimento encaminhado", "Data de envio do movimento", "Situação atual da proposta"):
        assert campo in comp, campo
    assert "não traz os dados do segurado" in comp
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "<SensibilizacaoCard8" in dialogo
    assert "{!foto?.sensibilizacao && (" in dialogo and dialogo.index("{!foto?.sensibilizacao && (") < dialogo.index('titulo="Dados do Segurado"')
    assert dialogo.index('titulo="Dados da Venda"') < dialogo.index('titulo="Dados da Sensibilização"') < dialogo.index('titulo="Dados do Segurado"')


def test_workflow_mostra_os_dois_estados_reais_movimento_e_proposta():
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "passos={[" in dialogo and "Movimento: ${foto.sensibilizacao.statusMovimento}" in dialogo
    assert "Proposta: ${foto.sensibilizacao.statusAtual}" in dialogo
    tl = _fonte(CAIXA / "components" / "ProposalTimeline.tsx")
    assert "if (passos) {" in tl and tl.index("if (passos) {") < tl.index("const isExceptionFlow")
