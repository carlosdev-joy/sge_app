"""Fluxo da proposta no Resumo do Seguro: todas as etapas até a do card atual.

O usuário pediu (02/11) que a linha do tempo mostre o FLUXO inteiro até a etapa selecionada, com as
anteriores como sucesso. Ex.: no Card 4 (Em Análise): Pendente de Assinatura ✓ → Pendente de Pagamento ✓
→ Assinada e Paga ✓ → Em Análise (atual). Prende o caminho de cada card (com os desvios reais:
rejeitada não passa por "Emitida"; devolução vem depois da rejeição; sensibilização acompanha emitidas),
a etapa atual com o estado real (Cancelada, Devolução em Andamento…) e a ligação do Resumo.
A lógica é pura e roda no node de verdade.
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


def _fonte(caminho: Path) -> str:
    texto = caminho.read_text(encoding="utf-8")
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith("//"))


def _compila(arquivo: Path, saida: str) -> Path:
    if not (shutil.which("node") and shutil.which("npx")):
        pytest.skip("node/npx ausentes")
    tmp = tempfile.mkdtemp(prefix=saida)
    r = subprocess.run(
        ["npx", "tsc", str(arquivo), "--ignoreConfig", "--outDir", tmp, "--module", "commonjs",
         "--target", "es2020", "--skipLibCheck"], cwd=UI, capture_output=True, text=True, timeout=300)
    js = next(Path(tmp).rglob(arquivo.stem + ".js"), None)
    assert js is not None, f"tsc não emitiu {arquivo.stem}.js: {r.stdout}{r.stderr}"
    return js


def _rodador(js: Path):
    def chamar(corpo: str):
        script = (f"const m = require({json.dumps(str(js))});"
                  f"const saida = (() => {{ {corpo} }})();"
                  "console.log(JSON.stringify(saida));")
        p = subprocess.run(["node", "-e", script], cwd=UI, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)
    return chamar


@pytest.fixture(scope="module")
def fluxo():
    return _rodador(_compila(CAIXA / "lib" / "fluxoProposta.ts", "fluxo-"))


@pytest.fixture(scope="module")
def card1():
    return _rodador(_compila(CAIXA / "lib" / "card1Foto.ts", "fluxoatual-"))


def test_card4_mostra_o_fluxo_inteiro_ate_em_analise_com_as_anteriores_como_sucesso(fluxo):
    r = fluxo("return m.passosDoFluxo('in_analysis').map(p => [p.id, p.label, p.tom, p.estado]);")
    assert r == [
        ["pending_signature", "Pendente de Assinatura", "verde", "completed"],
        ["awaiting_payment", "Pendente de Pagamento", "verde", "completed"],
        ["paid", "Assinada e Paga", "verde", "completed"],
        ["in_analysis", "Em Análise", "vermelho", "active"],
    ]


@pytest.mark.parametrize("status,caminho", [
    ("pending_signature", ["pending_signature"]),
    ("awaiting_payment", ["pending_signature", "awaiting_payment"]),
    ("paid", ["pending_signature", "awaiting_payment", "paid"]),
    ("in_analysis", ["pending_signature", "awaiting_payment", "paid", "in_analysis"]),
    ("emission_sent", ["pending_signature", "awaiting_payment", "paid", "in_analysis", "emission_sent"]),
    # rejeitada NÃO passa por "Emitida"; devolução vem depois da rejeição
    ("declined", ["pending_signature", "awaiting_payment", "paid", "in_analysis", "declined"]),
    ("refund_scheduled", ["pending_signature", "awaiting_payment", "paid", "in_analysis", "declined", "refund_scheduled"]),
    # sensibilização acompanha propostas emitidas
    ("sensitization_monitoring", ["pending_signature", "awaiting_payment", "paid", "in_analysis", "emission_sent", "sensitization_monitoring"]),
])
def test_caminho_de_cada_card_segue_o_fluxo_e_so_a_ultima_etapa_e_a_atual(fluxo, status, caminho):
    r = fluxo(f"const p = m.passosDoFluxo('{status}'); return [p.map(x => x.id), p.map(x => x.estado), p.slice(0, -1).every(x => x.tom === 'verde')];")
    assert r[0] == caminho
    assert r[1] == ["completed"] * (len(caminho) - 1) + ["active"]
    assert r[2] is True                                # histórico = sucesso


def test_todos_os_oito_cards_do_workflow_tem_fluxo_na_ordem_da_operacao(fluxo):
    r = fluxo("""const ordem = ['pending_signature','awaiting_payment','paid','in_analysis','emission_sent','declined','refund_scheduled','sensitization_monitoring'];
      return ordem.map(s => { const p = m.passosDoFluxo(s); return [s, p.length, p[p.length-1].id === s]; });""")
    assert all(ultimo for _, _, ultimo in r) and len(r) == 8


def test_etapa_atual_leva_o_estado_real_do_card_e_o_historico_nao_muda(fluxo):
    r = fluxo("""
      const a = m.passosDoFluxo('emission_sent', {rotulo: 'Cancelada após Aceitação', tom: 'vermelho'});
      const b = m.passosDoFluxo('refund_scheduled', {rotulo: 'Devolução em Andamento', tom: 'ambar'});
      const c = m.passosDoFluxo('emission_sent', {});
      return [a[a.length-1], a.slice(0, -1).map(x => x.label), b[b.length-1].label, b.length, c[c.length-1]];""")
    assert r[0] == {"id": "emission_sent", "label": "Cancelada após Aceitação", "tom": "vermelho", "estado": "active"}
    assert r[1] == ["Pendente de Assinatura", "Pendente de Pagamento", "Assinada e Paga", "Em Análise"]
    assert r[2] == "Devolução em Andamento" and r[3] == 6
    assert r[4]["label"] == "Emitida" and r[4]["tom"] == "azul"        # sem override: o nome e a cor do card


@pytest.mark.parametrize("status", ["pending_dps", "refund_pending", "approved", "signed_proposal", "all", "", "valores_programados", "toString"])
def test_status_fora_dos_cards_do_workflow_fica_no_fluxo_antigo(fluxo, status):
    assert fluxo(f"return m.passosDoFluxo({json.dumps(status)});") is None


def test_atual_do_fluxo_le_o_estado_real_da_foto_de_cada_card(card1):
    r = card1("""
      const base = {idFoto: 1, referencia: null, atualizacao: null, situacao: '', assinatura: '', pago: '',
        contato: {email: null, celular: null, residencial: null}};
      const emit = (tom, sub) => m.atualDoFluxo({...base, emitida: {tom, segmento: 'VG', subSituacao: sub, emissao: null, inativo: false, cancelamento: null, motivo: null}});
      const dev = (s) => m.atualDoFluxo({...base, devolucao: {situacao: s, segmento: 'VG', status: 'x', retorno: '', dataMovimento: null, declinio: null}});
      return [emit('emitida', 'Integrada'), emit('suspensa', 'Cobertura Suspensa'), emit('cancelada', 'Cancelada após Aceitação'), emit('cancelada', ''),
              dev('realizada'), dev('andamento'), dev('pendente'),
              m.atualDoFluxo({...base, sensibilizacao: {identificacao: '1', linha: 'VG', statusMovimento: 'Enviada', statusMovimentoCodigo: 'ENV', statusAtual: 'S', statusAtualCodigo: 'S', motivo: null, dataMovimento: null, dataEnvio: null, podeSensibilizar: false}}),
              m.atualDoFluxo({...base, criticas: 2, subSituacao: 'Em Crítica', quitacao: null}),
              m.atualDoFluxo({...base, criticas: 2, subSituacao: '', quitacao: null}),
              m.atualDoFluxo({...base, rejeitada: {subSituacao: 'Não Aceita', motivos: 3, quitacao: null, declinio: null, diasVendaDeclinio: null}}),
              m.atualDoFluxo(undefined), m.atualDoFluxo(base)];""")
    assert r[0] == {"rotulo": "Integrada", "tom": "azul"} and r[1] == {"rotulo": "Cobertura Suspensa", "tom": "ambar"}
    assert r[2] == {"rotulo": "Cancelada após Aceitação", "tom": "vermelho"} and r[3]["tom"] == "vermelho" and r[3].get("rotulo") is None
    assert r[4] == {"rotulo": "Devolução Realizada", "tom": "verde"} and r[5] == {"rotulo": "Devolução em Andamento", "tom": "ambar"}
    assert r[6] == {"rotulo": "Devolução Pendente", "tom": "vermelho"}
    assert r[7] == {"rotulo": "Sensibilização · Enviada"} and r[8] == {"rotulo": "Em Análise · Em Crítica"}
    assert r[9] is None and r[10] is None and r[11] is None and r[12] is None


def test_resumo_do_seguro_usa_o_fluxo_para_todos_os_cards():
    dialogo = _fonte(CAIXA / "components" / "ProposalDetailDialog.tsx")
    assert "passosDoFluxo(proposal.status, atualDoFluxo(foto))" in dialogo
    assert "passos={passosDoFluxo" in dialogo and dialogo.count("<ProposalTimeline") == 1       # um só caminho
    assert "refundStep" not in dialogo and 'currentStatus="refund_pending"' not in dialogo


def test_linha_do_tempo_desenha_o_fluxo_concluidas_com_check_e_rola_no_celular():
    tl = _fonte(CAIXA / "components" / "ProposalTimeline.tsx")
    assert "if (passos) {" in tl and tl.index("if (passos) {") < tl.index("const isExceptionFlow")
    assert 'p.estado === "completed" ? <Check' in tl                       # etapa concluída = check (sucesso)
    assert "overflow-x-auto" in tl and "min-w-max sm:min-w-0" in tl and "min-w-[104px]" in tl
    # o fluxo antigo continua para o que não é card (Acompanhamento, pending_dps)
    assert "isRefundFlow" in tl and "isExceptionFlow" in tl


def test_linha_do_tempo_abre_na_etapa_atual_e_o_circulo_fica_acima_do_traco():
    tl = _fonte(CAIXA / "components" / "ProposalTimeline.tsx")
    assert "el.scrollLeft = el.scrollWidth" in tl and "steps.length > 3" in tl and "ref={trilho}" in tl
    assert "relative z-10 w-12 h-12 rounded-full" in tl                    # o traço não corta o check


def test_emitida_cancelada_nao_leva_check_na_etapa_atual():
    tl = _fonte(CAIXA / "components" / "ProposalTimeline.tsx")
    assert 'p.id === "emission_sent" && p.tom === "vermelho" ? <XCircle' in tl
