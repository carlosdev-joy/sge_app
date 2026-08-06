"""
F10 da spec `docs/spec-malha-execucao.md` — **a faixa de corrida e o painel que
responde "o que está travando"**.

`test_malha_corrida_agregado_f10.py` prova o SERVIDOR desta fase (a consulta de
conjunto, o raio de alcance e o ordenamento do refetch). Esta suíte prova a
outra metade: o que o operador LÊ e o que ele PODE FAZER às 3h.

── Como isto roda sem runner de JS ──────────────────────────────────────────
Mesma técnica (e mesmas razões) do `test_malhas_f4_front.py`: `ui-react` não
tem runner de testes e acrescentar um traria dependência de REDE a um produto
que faz deploy offline com wheels. Os módulos PUROS da camada — `tempoCorrida`,
`statusExecucao` e `proximaExecucao` — são transpilados pelo `sucrase` que o
Vite já traz e executados pelo Node, byte a byte como estão no `src/`.

Sem Node ou sem `node_modules`, a suíte SALTA em vez de falhar — mas o salto é
visível no `-rs`, nunca silencioso.

── O que é provado por CONTRATO DO FONTE, e por quê ─────────────────────────
Quatro aceites desta fase moram em JSX de componentes que só existem montados
com react-query, @xyflow/react e o roteador; montar isso aqui seria um runner
de testes disfarçado. São eles:

  • `Encerrar corrida…` existe em TODA corrida `ABERTA` — e não só depois do
    limite vencido (Decisão 62);
  • a confirmação do encerramento diz a CONSEQUÊNCIA: os pipelines em execução
    continuam rodando;
  • existe UM mecanismo de navegação temporal, não quatro (Decisão 42);
  • `Segurar/Soltar` passa a existir também no modo Execução (§9.6).

Os quatro viram asserção sobre o texto do fonte — a GUARDA literal que os
implementa. É prova mais fraca que executar, e por isso vem acompanhada do
`tsc -b` e do `eslint` como baseline de aceite da fase, e da regra de sempre:
a mutação que apaga a guarda deixa o teste vermelho.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f10_painel_harness.cjs"
MALHAS = RAIZ / "ui-react" / "src" / "components" / "malhas"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente) — os testes de "
                 "contrato do fonte continuam valendo")
_MAJOR_MINIMO = 18


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= _MAJOR_MINIMO \
            else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def front() -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def _cenario(front: dict, nome: str) -> dict:
    dado = front[nome]
    assert "erro" not in dado, f"{nome} levantou no front:\n{dado.get('erro')}"
    return dado


def _fonte(nome: str) -> str:
    return (MALHAS / nome).read_text(encoding="utf-8")


# ═══════════ Decisão 62 — a aba que abre é derivada da SAÚDE ════════════════

def test_a_aba_inicial_e_derivada_da_saude(front):
    """O aceite literal da fase.

    Quando o operador abre o painel às 3h, as perguntas "está rodando?" e "em
    que pé está?" já foram respondidas pelo card ou pelo alarme que o trouxe
    até aqui. Obrigá-lo a clicar em `Travando` é um clique a mais na única
    coisa que ele veio fazer."""
    d = _cenario(front, "aba_inicial_por_saude")
    assert d["ABERTA:COM_FALHA"] == "travando"
    assert d["ABERTA:ATRASADA"] == "travando"
    assert d["ABERTA:SEM_PROGRESSO"] == "travando"
    assert d["ABERTA:OK"] == "agora"


def test_corrida_fechada_abre_em_eventos_mesmo_com_saude_suja(front):
    """A saúde só existe com o ciclo ABERTO (§6.1). Se um valor antigo
    sobreviver na linha, ele não pode mandar numa corrida que já acabou: o que
    resta a ler numa corrida fechada é o histórico dela."""
    d = _cenario(front, "aba_inicial_por_saude")
    for status in ("CONCLUIDA", "FALHA", "EXPIRADA", "CANCELADA",
                   "SEM_TRABALHO", "ABORTADA"):
        assert d[status] == "eventos", status
    # Sem corrida nenhuma (interruptor em 0, banco sem a 085, API anterior) o
    # painel continua sendo o de eventos da guardiã — o de hoje, byte a byte.
    assert d["sem_corrida"] == "eventos"
    assert d["indefinida"] == "eventos"


# ═══════════ Decisão 63 — o raio de alcance, e a ausência de medida ═════════

def test_o_raio_nao_apurado_some_da_tela_em_vez_de_virar_zero(front):
    """`alcance: null` é "não apurei" (grafo indisponível), e `0` é "ninguém
    atrás" — medida de verdade. Colapsar os dois faria a tela dizer "nenhum
    pipeline parado atrás" numa falha de leitura, que é o oposto do fato."""
    d = _cenario(front, "raio_de_alcance")
    assert d["nao_apurado"] is None
    assert d["ausente"] is None
    assert d["zero"] == "nenhum pipeline parado atrás"


def test_o_raio_diz_o_numero_e_o_quanto_dele_e_critico(front):
    """18 parados atrás sem nenhum crítico espera o horário comercial; 2 com um
    `ALTA` no meio, não. O segundo número é o que muda a resposta."""
    d = _cenario(front, "raio_de_alcance")
    assert d["um"] == "1 pipeline parado atrás"
    assert d["muitos"] == "18 pipelines parados atrás"
    assert d["com_alta"] == "2 pipelines parados atrás (1 de criticidade alta)"


# ═══════ Decisão 66/3 — o aviso preso na fila, e os DOIS relógios ═══════════

def test_o_aviso_preso_e_medido_entre_dois_carimbos_do_banco(front):
    """A armadilha da Decisão 60, no banner mais grave da fase.

    A bancada publica a conta INGÊNUA junto com a real: com o desvio de 3 h
    medido no dev, `Date.now() − criado_em` dá NEGATIVO — o evento pareceria do
    futuro e o banner nunca acenderia. Um alarme de silêncio que fica em
    silêncio é o pior defeito possível nesta camada."""
    d = _cenario(front, "aviso_preso_na_fila")
    assert d["ingenuo_min"] < 0            # a armadilha existe neste cenário
    assert d["preso"] == {"desde": "2026-08-05 13:07:00", "quantos": 1}


def test_o_banner_de_fila_tem_carencia_para_nao_virar_alarme_falso(front):
    """A guardiã drena a fila a cada ciclo de 5 min. SEM carência, toda falha
    de malha acenderia "ninguém foi avisado" por alguns minutos e apagaria
    sozinha — o alarme falso que treina o operador a ignorar justamente o
    banner que existe para o webhook com 401 (Decisões 26/27)."""
    d = _cenario(front, "aviso_preso_na_fila")
    assert d["carencia_min"] >= 5
    assert d["recente"] is None            # 3 min na fila não é notícia
    assert d["avisado"] is None


def test_coluna_ausente_nao_acusa_e_sucesso_na_fila_nao_e_incidente(front):
    """Duas ausências que NÃO são acusação:

      • chave `notificado_em` ausente = o banco não tem a coluna. Tratá-la como
        `null` acenderia o banner vermelho em toda malha de um banco antigo;
      • `MALHA_CONCLUIDA` é opt-in e `MALHA_SEM_TRABALHO` nem vira card
        (Decisão 48) — nenhum dos dois pendurado na fila é notícia."""
    d = _cenario(front, "aviso_preso_na_fila")
    assert d["coluna_ausente"] is None
    assert d["conclusao_na_fila"] is None
    assert d["sem_apurado"] is None
    # Com vários presos, o banner conta todos e diz desde quando pelo MAIS
    # ANTIGO — e o `MALHA_CONCLUIDA` do lote continua fora da conta.
    assert d["varios"] == {"desde": "2026-08-05 13:07:00", "quantos": 2}


# ═════════ Decisão 61 — o prazo por padrão é o PRÓXIMO GATILHO ══════════════

def test_o_proximo_gatilho_tem_instante_e_nao_so_texto(front):
    """Às 04:00 "faltam 21h de teto" é irrelevante; o que importa é que a
    próxima corrida parte às 01:00 e a corrida aberta BLOQUEIA essa partida.
    Para escrever "parte em 2h50 (01:00)" é preciso o instante."""
    d = _cenario(front, "proximo_gatilho")
    assert d["texto"] == "amanhã 01:00"
    assert d["hora"] == "01:00"
    assert d["falta_min"] == 170           # 22:10 → 01:00 = 2h50
    # O texto de sempre (F15, o card do nó Início) não mudou de forma.
    assert d["texto_legado"] == d["texto"]


def test_cadencia_sem_hora_exata_nao_inventa_instante(front):
    """`hourly` não tem uma próxima partida nomeável, e sob demanda não tem
    partida nenhuma. Nos dois casos a linha da faixa some ou vira cadência —
    nunca um horário inventado."""
    d = _cenario(front, "proximo_gatilho")
    assert d["hourly"]["quando"] is None
    assert d["hourly"]["texto"] == "a cada hora no minuto 30"
    assert d["sob_demanda"] is None
    assert d["sem_agendamento"] is None


# ═════════ Decisão 54 — o que entra (e o que não entra) em `Travando` ═══════

def test_nao_partiu_fica_fora_da_lista_vermelha(front):
    """Às 01:10 "ainda não começou" é o estado normal de TODO membro de TODA
    corrida recém-aberta: chipá-lo de vermelho seria um alarme falso por noite,
    em toda malha. Ele aparece na aba como linha quieta, com o número."""
    d = _cenario(front, "classes_travadas")
    assert d["falhou"] and d["orfa"] and d["nao_liberou"]
    assert d["nao_partiu"] is False


def test_as_classes_nunca_viram_tres_pendentes(front):
    """Decisão 21/§9.15#10: `falhou`, `nao_liberou`, `nao_partiu` e `orfa` são
    problemas com DONOS diferentes e ações diferentes. Cada um tem rótulo
    próprio em português de reunião (Decisão 74)."""
    d = _cenario(front, "classes_travadas")
    assert len(set(d["rotulos"].values())) == 4
    for texto in d["rotulos"].values():
        assert "_" not in texto            # nenhum nome de máquina na tela


# ═══════════════════ contrato do FONTE — os aceites em JSX ══════════════════

def test_encerrar_corrida_existe_em_toda_corrida_aberta():
    """Decisão 62, a metade que a Decisão 32 existe para proteger.

    O botão NÃO pode nascer condicionado ao teto vencido: os casos em que mais
    se precisa encerrar são `ABERTA · SEM_PROGRESSO` (DagRun morto) e
    `ABERTA · COM_FALHA` quando já se decidiu que a madrugada acabou. A única
    condição é `status === 'ABERTA'`."""
    fonte = _fonte("CabecalhoCorrida.tsx")
    assert "Encerrar corrida…" in fonte
    trecho = fonte.split("Zona 4", 1)[1].split("</Modal>", 1)[0]
    assert "{aberta && (" in trecho, (
        "o botão de encerrar deixou de ser guardado por `aberta` — ou a zona "
        "mudou de forma e esta régua precisa acompanhar")
    # A guarda é o ESTADO do ciclo, e nada mais: teto vencido, saúde e limite
    # não podem entrar na condição de EXISTÊNCIA do botão.
    for proibido in ("teto_vencido", "teto_configurado", "saude ==="):
        assert proibido not in trecho.split("<Button", 1)[0], (
            f"a existência do botão de encerrar passou a depender de "
            f"'{proibido}' — a Decisão 62 manda o contrário")


def test_a_confirmacao_do_encerramento_diz_a_consequencia():
    """"Encerrar" não é "matar", e essa é a dúvida que faz o operador NÃO
    apertar o botão. A confirmação responde antes do clique."""
    fonte = _fonte("CabecalhoCorrida.tsx")
    assert "Nenhum pipeline é interrompido" in fonte
    assert "CONTINUAM rodando" in fonte
    assert "libera o disparo da próxima corrida" in fonte
    # Motivo obrigatório (Decisão 32): sem ele o botão não confirma.
    assert "disabled={!motivo.trim()" in fonte


def test_existe_UM_mecanismo_de_navegacao_temporal():
    """Decisão 42/§9.15#17. A barra do editor tinha três (◀ ▶ · input de data ·
    botão "agora") e a fase acrescentaria uma faixa: quatro mecanismos para a
    mesma pergunta na mesma barra é decisão adiada, não flexibilidade.

    A faixa de corridas é o mecanismo; a data e o "agora" viram itens do menu
    DELA. A régua: o editor não pode ter `input type="date"` nem os chevrons de
    navegação — eles moram no `SeletorCorrida`, e só lá."""
    editor = _fonte("MalhaEditor.tsx")
    assert 'type="date"' not in editor, (
        "o editor voltou a ter um seletor de data próprio — a navegação "
        "temporal é UMA só, e ela mora no SeletorCorrida")
    assert "ChevronLeft" not in editor and "ChevronRight" not in editor, (
        "o ◀ ▶ por dia/corrida voltou ao editor")
    seletor = _fonte("SeletorCorrida.tsx")
    assert 'type="date"' in seletor and "ir para…" in seletor


def test_duas_corridas_do_mesmo_dia_sao_dois_blocos():
    """Decisão 42: a `sequencia` existe justamente para isto. A faixa desenha
    UM bloco por corrida (`corridas.map`), sem agrupar por data — agrupar
    esconderia a primeira madrugada depois de um redisparo às 5h, que é
    exatamente o ciclo que o operador quer ver."""
    fonte = _fonte("SeletorCorrida.tsx")
    assert "blocos.map(c =>" in fonte
    # E trocar aplica a LENTE (`?corrida={id}`), nunca a data: é o que impede
    # as duas de se sobreporem no mesmo canvas.
    assert "onTrocar(c)" in fonte
    editor = _fonte("MalhaEditor.tsx")
    assert "onTrocar={irParaCorrida}" in editor
    assert "setCorridaRef(alvo.id)" in editor


def test_segurar_soltar_existe_tambem_no_modo_execucao():
    """§9.6: hoje destravar exige SAIR da lente de acompanhamento no meio do
    incidente — trocar de modo é perder o recorte da corrida, a faixa e o
    painel de quem está travando, exatamente quando eles são o que se lê.

    Uma função só nos dois modos: duas cópias do mesmo botão seriam duas
    chances de os textos divergirem, e este é o botão cuja frase decide se o
    operador entende que segurar o Início NÃO para o ciclo em voo."""
    fonte = _fonte("MalhaEditor.tsx")
    assert "const botaoRetencao = () =>" in fonte
    assert fonte.count("{botaoRetencao()}") == 2, (
        "o botão de retenção deixou de existir nos DOIS modos")
    # A trava de EDIÇÃO continua valendo na execução; retenção não é edição.
    assert "visão de execução — edição travada" in fonte


def test_soltar_um_hold_nao_exige_sair_da_lente():
    """O banner da Decisão 66/2 carrega o gesto: quem chega às 3h vê que a
    malha está segurada desde 02:40 E consegue soltar dali mesmo."""
    fonte = _fonte("CabecalhoCorrida.tsx")
    assert "nós segurados" in fonte and "Soltar" in fonte
    assert "onSoltar" in fonte
    editor = _fonte("MalhaEditor.tsx")
    assert "onSoltar={" in editor and "alternarRetencao(noId, false)" in editor


def test_o_dia_com_varias_corridas_deixa_de_ser_mudo():
    """Pendência 12b da §18. A API já OMITE o bloco `corrida` quando o dia teve
    mais de uma (descrever uma corrida sobre a lista do dia inteiro é a mesma
    mentira que a fase mata) e devolve `corridas_no_dia`. Até aqui o front só
    deixava de mostrar a faixa: honesto, e mudo."""
    fonte = _fonte("CabecalhoCorrida.tsx")
    assert "corridasNoDia" in fonte
    assert "escolha uma na faixa" in fonte
    editor = _fonte("MalhaEditor.tsx")
    assert "corridasNoDia={execData?.corridas_no_dia ?? null}" in editor


def test_reexecutar_so_existe_com_a_frase_do_efeito():
    """Decisão 65: o gesto mais delicado do modelo não pode virar um clique de
    3h no escuro. O botão só é oferecido com um ciclo ABERTO em foco — que é a
    condição em que a frase "esta reexecução entra nele e o relógio de
    fechamento NÃO reinicia" pode ser escrita com certeza — e o clique abre a
    PRÉVIA, que traz do servidor a mesma frase."""
    painel = _fonte("PainelCorridaLateral.tsx")
    assert "onReexecutar" in painel
    assert "fraseReexecucao" in painel
    # Sem o callback o botão não é renderizado — não é um botão desabilitado.
    assert "const podeRerodar = onReexecutar" in painel
    editor = _fonte("MalhaEditor.tsx")
    assert "corrida?.status === 'ABERTA'" in editor.split("onReexecutar=", 1)[1][:400]
    assert "NÃO" in editor.split("fraseReexecucao=", 1)[1][:400]
    assert "reinicia" in editor.split("fraseReexecucao=", 1)[1][:400]
    assert "<ModalRerunEtapa" in editor


def test_clicar_numa_linha_acende_a_cadeia_e_centraliza_sem_sair_da_lente():
    """Um clique até o problema (§9.5). Acender SEM centralizar deixa o realce
    fora da viewport numa malha de 40 nós: o operador clica, "nada acontece" e
    ele volta a varrer o desenho com o olho — o gesto que esta fase existe para
    eliminar. E nada disso troca o modo: a lente de execução não se perde."""
    fonte = _fonte("MalhaEditor.tsx")
    corpo = fonte.split("const focarPipeline = useCallback(", 1)[1][:600]
    assert "realceFocarNo(pipeline)" in corpo
    assert "rf.fitView(" in corpo and "nodes: [{ id: pipeline }]" in corpo
    assert "setModo(" not in corpo         # não sai da lente
    assert "onFocar={focarPipeline}" in fonte


def test_a_aba_agora_tem_badge_NEUTRO():
    """`Agora (2)` são dois pipelines SAUDÁVEIS rodando. Com o vermelho que a
    `ui/Tabs` pinta por padrão, o operador leria "2 problemas" às 3h."""
    fonte = _fonte("PainelCorridaLateral.tsx")
    trecho = fonte.split("const abas = [", 1)[1].split("]\n", 1)[0]
    agora = trecho.split("id: 'agora'", 1)[1].split("{", 1)[0]
    assert "badgeTom: 'neutro'" in agora
    travando = trecho.split("id: 'travando'", 1)[1].split("},", 1)[0]
    assert "badgeTom" not in travando, (
        "a aba `Travando` declarou um tom: o default (alerta) é o certo, e "
        "declarar convida a trocá-lo sem perceber")


def test_a_barra_de_limite_so_existe_com_teto_configurado_na_malha():
    """Decisão 61: o default global de 24h é ANTI-TRAVAMENTO, não SLA. Uma
    barra em 80% às 20h numa malha que sempre fecha em 3h faria escalar por
    nada. Sem `teto_horas` configurado sobra a linha do PRÓXIMO GATILHO."""
    fonte = _fonte("RelogioCorrida.tsx")
    assert "const temLimite = resumo.prazo !== null" in fonte
    assert "{temLimite && (" in fonte
    # E a linha do gatilho não depende do teto — ela é o prazo por padrão.
    gatilho = fonte.split("{proximoGatilho && (", 1)[1][:500]
    assert "a próxima corrida parte" in gatilho
    assert "enquanto esta não fechar, ela não abre" in gatilho


def test_o_credito_de_retencao_nunca_e_silencioso():
    """Decisão 61: soltar um hold de 6 h empurra `teto_em` e a barra ANDA PARA
    TRÁS. Uma barra de prazo que recua sem explicação destrói a confiança em
    todas as outras — o crédito vem colado nela, nomeado."""
    fonte = _fonte("RelogioCorrida.tsx")
    assert "{resumo.credito && (" in fonte
    # E o evento correspondente tem nome em português no painel (Decisão 74).
    status = _fonte("statusExecucao.ts")
    assert "MALHA_TETO_CREDITADO: 'limite adiado por retenção'" in status


def test_a_barra_de_limite_anuncia_LIMITE_e_nunca_progresso():
    """§9.11/Decisão 75: `role="progressbar"` com valuenow/valuemax faz o
    LEITOR DE TELA calcular e anunciar o percentual sozinho. Toda barra nova
    passa pela `ui/Progress`, que exige `aria-valuetext` — e o texto aqui diz
    "limite", nunca "progresso" nem contagem de pipelines."""
    fonte = _fonte("RelogioCorrida.tsx")
    assert "<Progress" in fonte
    assert "valorTexto={resumo.prazo ?? 'limite de segurança'}" in fonte
    assert 'ariaLabel="limite de segurança da corrida"' in fonte
    progress = (RAIZ / "ui-react" / "src" / "components" / "ui"
                / "Progress.tsx").read_text(encoding="utf-8")
    assert "aria-valuetext={texto}" in progress


def test_nenhum_nome_de_maquina_chega_a_tela_do_painel():
    """Decisão 74, o aceite verificável da §9.11: `grep` nos componentes da
    malha não casa texto EXIBIDO com vocabulário de motor. Casar em comentário
    e em nome de variável é esperado — o que não pode é virar frase."""
    proibidos = ("quiescência com", "ODATE ", "dispensado ", "guardiã diz")
    for arquivo in ("CabecalhoCorrida.tsx", "PainelCorridaLateral.tsx",
                    "RelogioCorrida.tsx", "SeletorCorrida.tsx"):
        fonte = _fonte(arquivo)
        # As linhas de JSX que produzem texto visível — nunca as de comentário.
        visivel = "\n".join(l for l in fonte.splitlines()
                            if not l.lstrip().startswith(("//", "*", "/*")))
        for termo in proibidos:
            assert termo not in visivel, f"{arquivo}: '{termo}'"
        # `#N` não aparece na interface (três numerações disputam a notação).
        assert "#{" not in visivel, arquivo
