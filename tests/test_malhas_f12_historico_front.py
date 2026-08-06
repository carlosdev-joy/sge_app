"""
F12 da spec `docs/spec-malha-execucao.md` — o que o operador LÊ do HISTÓRICO
FACTUAL (§9.7, Decisão 68), da AUDITORIA na tela (Decisão 67) e do PERCENTUAL
DE TEMPO (Decisão 56b).

`test_malhas_f12_historico.py` prova o SERVIDOR (as consultas de conjunto, a
janela, o dia atípico e a degradação). Esta suíte prova a outra metade: o
TEXTO, a COR e — o mais importante nesta fase — as AUSÊNCIAS.

── Como isto roda sem runner de JS ──────────────────────────────────────────
Mesma técnica (e mesmas razões) do `test_malhas_f9_card.py`: `ui-react` não tem
runner de testes e acrescentar um traria dependência de REDE a um produto que
faz deploy offline com wheels. O `sucrase` que o Vite já traz transpila os
módulos do `src/` e o Node executa o código byte a byte como ele está lá — os
componentes desta camada são funções de renderização sem hook, e é por isso que
dá para chamá-los direto.

Sem Node ou sem `node_modules`, a suíte SALTA em vez de falhar — mas o salto é
visível no `-rs`, nunca silencioso.

── O aceite que manda nesta fase, e por que ele é de AUSÊNCIA ───────────────
⚠️ **Esta é a única fase da spec que depende de corrida real gravada.** Antes do
smoke o histórico é literalmente ZERO — e um número sem amostra é o que esta
spec inteira existe para não produzir. Por isso o primeiro teste daqui é o do
DIA 1: com zero corridas fechadas, NENHUMA frase desta fase é renderizada e
nada quebra. `n = 0` é ausência, nunca "0%".

A prova de ausência é feita sobre a ÁRVORE INTEIRA — texto, `title` e `aria-*`
—, porque é exatamente por `title` e `aria-valuetext` que um texto escapa sem
ninguém ver (foi assim que a Decisão 56 quase voltou pela porta da
acessibilidade na F9).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f12_historico_harness.cjs"
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


def _cenario(front: dict, nome: str):
    dado = front[nome]
    if isinstance(dado, dict):
        assert "__erro__" not in dado, \
            f"{nome} levantou no front:\n{dado.get('__erro__')}"
    return dado


def _fonte(nome: str) -> str:
    return (MALHAS / nome).read_text(encoding="utf-8")


def _literais(nome: str) -> str:
    """Só o que pode virar TEXTO NA TELA — os literais, sem os comentários.

    Os comentários deste módulo CITAM as palavras proibidas de propósito, para
    explicar por que elas não entram; varrer o arquivo inteiro faria o teste
    proibir a própria documentação da regra."""
    sem_comentario = [
        linha for linha in _fonte(nome).splitlines()
        if not linha.lstrip().startswith(("//", "*", "/*"))]
    return "\n".join(
        re.findall(r"'[^']*'|`[^`]*`", "\n".join(sem_comentario)))


# ═══════════ O ACEITE DO DIA 1 — zero corridas, zero frases ════════════════

def test_dia_1_nenhuma_frase_desta_fase_e_renderizada(front):
    """*"histórico com **zero** corridas fechadas (dia 1) → nenhuma das frases
    desta fase é renderizada, e nada quebra"*.

    É o aceite que manda na fase inteira, e ele é de AUSÊNCIA: no dia do deploy
    o interruptor está em `0`, nenhuma corrida fechou ainda, e o card não pode
    inventar "falhou 0 das últimas 0 corridas" nem "≈ 0%"."""
    d = _cenario(front, "dia_1_sem_historico")
    assert d["historico_falhas"] is None
    assert d["anterior"] is None
    assert d["dia_atipico"] is None
    assert d["percentual"] is None
    # E nada disso vaza por `title`/`aria-*`, que é por onde texto escapa.
    for onde in ("lido_card", "lido_badge", "titulo"):
        texto = d[onde]
        for proibido in ("falhou", "corrida anterior", "%", "tiveram trabalho"):
            assert proibido not in texto, \
                f"{proibido!r} apareceu em {onde} no dia 1:\n{texto}"


def test_dia_1_o_card_continua_contando_o_que_ele_ja_contava(front):
    """"Nada quebra" é a outra metade do aceite: sem histórico, o card é —
    byte a byte — o da F11. Um teste que só provasse a ausência ficaria verde
    com o bloco inteiro sumindo da tela."""
    d = _cenario(front, "dia_1_sem_historico")
    assert d["contagem"] == "4 de 7 pipelines concluídos"
    assert "em andamento" in d["lido_badge"]


# ═══════════ `falhou 2 das últimas 7 corridas` (Decisão 68) ════════════════

def test_a_frase_do_card_conta_o_que_aconteceu(front):
    """O aceite literal do card. Ele responde "está pior que antes?" sem
    obrigar o gestor a abrir malha por malha às 8h."""
    d = _cenario(front, "falhou_2_de_7")
    assert d["frase"] == "falhou 2 das últimas 7 corridas"


def test_sem_falha_no_periodo_o_historico_se_cala(front):
    """Zero falhas não vira "falhou 0 das últimas 7": em 40 cards, uma linha
    para dizer que está tudo como sempre esteve é ruído. O histórico só fala
    quando tem notícia — e a corrida ANTERIOR continua aparecendo, porque ela
    responde outra pergunta."""
    d = _cenario(front, "sem_falha_nenhuma_cala")
    assert d["frase"] is None
    assert d["anterior"].startswith("corrida anterior: 04/08")


def test_o_denominador_e_o_do_servidor_nunca_a_janela_pedida(front):
    """Malha de três semanas: existiram 4 corridas, e é `4` que a frase diz.
    "das últimas 7" sobre 4 corridas inventaria três madrugadas — o número
    certo com o denominador errado é a família de mentira desta spec."""
    assert _cenario(front, "malha_nova_denominador_do_servidor")["frase"] \
        == "falhou 1 das últimas 4 corridas"


def test_com_uma_corrida_so_a_fracao_nao_existe(front):
    """"falhou 1 das últimas 1 corridas" é a frase que faz o leitor duvidar do
    número ao lado. O fato é o mesmo e a frase é outra."""
    assert _cenario(front, "uma_corrida_so_no_singular")["frase"] \
        == "falhou na última corrida"


def test_a_corrida_anterior_e_fato_com_hora_e_duracao(front):
    """*"faixa — `corrida anterior: 03/08 · concluída · 01:10 → 04:02`"*.

    Exige `n = 1`, e não o piso `n ≥ 5` da duração típica: isto é REGISTRO, não
    mediana — e é a resposta mais direta a "está pior que ontem?".

    O formato é ABSOLUTO (Decisão 60): corrida fechada não ganha "há 22h"."""
    d = _cenario(front, "falhou_2_de_7")
    assert d["anterior"] == \
        "corrida anterior: 04/08 · concluída · 01:10 → 04:02 · 2h52"


# ═══════════ `SEM_TRABALHO`: a terça âmbar × o sábado mudo ═════════════════

def test_terca_atipica_sobe_para_ambar_com_a_frase_junto(front):
    """*"malha que rodou nas últimas 4 terças e hoje (terça) sai
    `SEM_TRABALHO` → card **âmbar** com 'as últimas 4 terças tiveram
    trabalho'"*.

    A cor E a frase saem do MESMO `resumoCorrida`: pintar de âmbar sem dizer
    por quê seria um alarme sem causa, e a regra da casa é que cor nunca é
    canal único."""
    d = _cenario(front, "terca_atipica_vira_ambar")
    assert d["frase"] == "as últimas 4 terças tiveram trabalho"
    assert "amber" in d["chip"] and "amber" in d["faixa"]
    assert "amber" in d["classes_badge"]
    # O ESTADO não muda: continua "sem trabalho hoje". O que mudou foi a
    # atenção que ele merece, não o fato.
    assert d["rotulo"] == "sem trabalho hoje"


def test_a_terca_ambar_continua_sem_barra(front):
    """Decisão 57 — `SEM_TRABALHO` não tem barra, e âmbar não ressuscita uma
    barra que não tem o que preencher: 0 leria "falhou tudo" e a barra cheia,
    "rodou tudo"."""
    d = _cenario(front, "terca_atipica_vira_ambar")
    assert d["barra"] is False
    assert d["nada_previsto"] == "nada previsto"


def test_no_sabado_a_MESMA_malha_continua_cinza_e_muda(front):
    """*"no sábado, a mesma malha continua **cinza e muda**"*.

    É a metade que importa da Decisão 68, e ela é o que separa esta fase de um
    alarme de sábado toda semana — que treinaria o operador a ignorar o alarme
    (Decisão 26) e, com ele, a terça, que era a única que importava."""
    d = _cenario(front, "sabado_legitimo_fica_cinza_e_mudo")
    assert d["frase"] is None
    assert "slate" in d["chip"] and "amber" not in d["chip"]
    assert "amber" not in d["classes_badge"]
    assert "tiveram trabalho" not in d["titulo"]


def test_tres_ocorrencias_nao_bastam_para_afirmar(front):
    """O servidor exige QUATRO ocorrências do mesmo dia da semana. Com três, a
    tela não afirma nada: uma frase com número errado é pior que silêncio, e
    "as últimas 2 terças" não é evidência de nada num calendário com feriado."""
    d = _cenario(front, "tres_tercas_nao_bastam")
    assert d["frase"] is None
    assert "amber" not in d["faixa"]


def test_o_dia_da_semana_e_lido_em_UTC(front):
    """⚠️ `new Date('2026-08-04')` é interpretado como UTC e, lido em hora local
    (Brasília, UTC−3), volta um dia: a TERÇA viraria segunda no rótulo, e a
    frase acusaria o dia errado.

    É o mesmo defeito que `tempoCorrida` documenta para os carimbos, e aqui ele
    apareceria como uma frase que contradiz o calendário na cara do operador."""
    d = _cenario(front, "nome_do_dia_da_semana")
    assert d["terca"] == "terças"          # 2026-08-04 é terça
    assert d["quarta"] == "quartas"        # 2026-08-05 é quarta
    assert d["sabado"] == "sábados"
    assert d["domingo"] == "domingos"
    assert d["sem_data"] is None


# ═══════════ auditoria na tela (Decisão 67) ════════════════════════════════

def test_cancelada_diz_quem_encerrou_quando_e_por_que(front):
    """*"corrida `CANCELADA` → card e faixa dizem `encerrada por C123456 às
    05:20 — motivo: "…"`"*.

    É o que torna o fechamento do mês explicável **sem abrir o banco**: três
    corridas canceladas com o rótulo mudo "encerrada pelo operador" não
    explicam nenhuma."""
    d = _cenario(front, "cancelada_diz_quem_e_por_que")
    assert d["encerramento"] == "encerrada por C123456 às 05:20"
    assert d["motivo"] == 'motivo: "carga do dia 03 remarcada para a tarde"'
    # O prefixo composto pelo servidor não é transcrito duas vezes: quem e
    # quando já saem na linha estruturada acima.
    assert "encerrada por C123456:" not in d["motivo"]


def test_a_reabertura_aparece_com_quem_reabriu(front):
    """`reaberta 1x por C999999` — e nunca "1ª tentativa" (Decisão 74). A faixa
    já dizia isto dentro do diagnóstico; o CARD calava, e "já mexeram aqui?" é
    uma das três primeiras perguntas de plantão."""
    d = _cenario(front, "cancelada_diz_quem_e_por_que")
    assert d["reaberta"] == "reaberta 1x por C999999"
    assert "tentativa" not in d["reaberta"]


def test_corrida_interrompida_nao_diz_concluida(front):
    """Invariante 4 do §16, e ela continua valendo com a auditoria por cima: a
    palavra "concluído" não aparece num desfecho interrompido."""
    d = _cenario(front, "cancelada_diz_quem_e_por_que")
    assert d["contagem"] == "parou em 4 de 7"
    assert "conclu" not in d["contagem"]


def test_fechador_automatico_nao_transcreve_o_vocabulario_do_motor(front):
    """O critério é o SUJEITO, não o status.

    Quem fecha a imensa maioria das corridas é o monitor automático, e o
    `motivo` que ele grava é o texto do MOTOR ("3 pipeline(s) sem concluir:
    CARGA_A (falhou)…"). Publicá-lo no card levaria nome de classe de máquina
    para a tela lida às 3h — o que a Decisão 74 mantém fora. A história dele é
    a aba de eventos."""
    d = _cenario(front, "fechada_pelo_monitor_nao_transcreve_o_motor")
    assert d["encerramento"] is None
    assert d["motivo"] is None
    assert "nao_liberou" not in d["titulo"] and "sem concluir" not in d["titulo"]


def test_origem_implicita_diz_sem_no_inicio_no_card(front):
    """*"malha `origem = implicita` → o card diz `sem nó Início`"* (Decisão 44).

    Nas 3 de 4 malhas sem Início o ODATE é "o que o primeiro membro achou", e
    apresentá-lo como "o ODATE da corrida" lhe dá uma autoridade que ele não
    tem. A faixa complementa dizendo de QUAL raiz ele veio."""
    d = _cenario(front, "origem_implicita_diz_sem_no_inicio")
    assert d["origem"] == "sem nó Início"
    # E a faixa nomeia a raiz — a outra metade do aceite.
    assert "primeira raiz a partir (CARGA_C)" in d["diagnostico"]
    assert "não tem nó Início" in d["diagnostico"]


def test_origem_manual_nomeia_quem_disparou(front):
    """Na lista, uma corrida manual é hoje indistinguível de uma agendada — e
    são coisas diferentes na hora de entender por que a madrugada foi
    diferente."""
    assert _cenario(front, "origem_manual_nomeia_quem_disparou")["origem"] \
        == "início manual (C123456)"


def test_a_corrida_agendada_nao_ganha_linha_nenhuma(front):
    """O caso normal fica MUDO: uma linha em todo card para dizer "abriu como
    sempre abre" é ruído em 40 cards."""
    assert _cenario(front, "origem_agendada_cala")["origem"] is None


# ═══════════ o `title` do bloco da faixa (Decisões 42/67/68) ═══════════════

def test_o_bloco_da_faixa_nomeia_quem_travou(front):
    """*"`title` do bloco = `04/08 · concluída · 2h41 · travou: CARGA_A`"*.

    É o que transforma dez quadradinhos coloridos em DIAGNÓSTICO: três
    madrugadas seguidas travando no mesmo membro é problema CRÔNICO e espera o
    horário comercial; nove verdes e uma vermelha é NOVIDADE e escala."""
    t = _cenario(front, "titulo_do_bloco_com_travado")
    assert "corrida de 04/08" in t and "falhou" in t
    assert "01:10 → 03:51 · 2h41" in t
    assert "travou: CARGA_A" in t


def test_o_bloco_da_faixa_carrega_a_auditoria(front):
    """Decisão 67 — "a lista de corridas traz a coluna". Sem isto, a faixa
    responde "foi ruim" e para aí."""
    t = _cenario(front, "titulo_do_bloco_com_auditoria")
    assert "encerrada por C123456 às 05:20" in t
    assert 'motivo: "carga do dia 03 remarcada para a tarde"' in t
    assert "reaberta 1x por C999999" in t


def test_corrida_limpa_nao_inventa_travado(front):
    """`travou: null` é "apurei e ninguém travou" — e ele cala, em vez de
    escrever "travou: —". A chave AUSENTE ("não apurei") cala pela mesma
    razão, e as duas leituras precisam continuar distinguíveis no payload."""
    t = _cenario(front, "titulo_do_bloco_sem_travou_apurado")
    assert "travou" not in t
    assert "2ª corrida de 03/08 · concluída" in t


# ═══════════ Decisão 56b — o percentual de TEMPO ═══════════════════════════

def test_cinco_de_seis_pipelines_sao_doze_por_cento_do_trabalho(front):
    """O desenho literal da Decisão 56b: malha de 6 em que o último leva 3h e
    os cinco primeiros 5 min cada.

    `5 de 6` é 83% dos PIPELINES e **12% do trabalho**. O percentual de
    contagem mandaria o operador dormir faltando 87% do tempo; o ponderado diz
    12%, que é a verdade."""
    d = _cenario(front, "cinco_de_seis_nao_e_83_por_cento")
    assert d["pct"] == 12
    assert d["texto"] == "≈ 12% do tempo típico"


def test_o_prefixo_e_o_sufixo_sao_parte_do_dado(front):
    """*"Prefixo `≈` e sufixo `do tempo típico`, sempre. Nunca `60%` solto,
    nunca 'concluído'"*. O `≈` remove a promessa de precisão que um percentual
    dá a uma mediana."""
    for nome in ("cinco_de_seis_nao_e_83_por_cento",
                 "teto_em_99_enquanto_nao_terminou", "atrasada_passa_de_cem"):
        texto = _cenario(front, nome)["texto"]
        assert texto.startswith("≈ ")
        assert texto.endswith("% do tempo típico")
        assert "conclu" not in texto


def test_membro_em_execucao_nao_ultrapassa_a_propria_fatia(front):
    """*"Membro em execução entra pelo tempo já decorrido, limitado à própria
    duração típica — nunca ultrapassa a própria fatia"*.

    Sem o teto por membro, um pipeline que já roda o dobro do típico pintaria
    progresso onde há atraso: 6h sobre uma fatia de 3h dariam 175% num total em
    que nada mais aconteceu."""
    d = _cenario(front, "membro_em_execucao_nao_passa_da_propria_fatia")
    assert d["pct"] == 87        # a fatia inteira de F, e nem um minuto além


def test_corrida_atrasada_passa_de_cem_e_nao_e_truncada(front):
    """*"Corrida `ATRASADA` mostra o percentual mesmo passando de 100% do
    típico — aí ele vira `≈ 140% do tempo típico`, que é exatamente o sinal de
    atraso, e não é truncado em 100: truncar esconderia o que o operador
    precisa ver"*."""
    d = _cenario(front, "atrasada_passa_de_cem")
    assert d["pct"] > 100
    assert d["texto"] == "≈ 187% do tempo típico"


def test_o_teto_e_99_enquanto_a_corrida_nao_terminou(front):
    """*"`Math.floor`, teto em 99 enquanto a corrida não for terminal"*.

    Com TODOS os membros concluídos e a corrida ainda ABERTA (o estado
    "fechando"), o número para em 99: "100%" com a corrida aberta é a palavra
    "pronto" dita por um número, e é o arredondamento `99,6 → 100` da Decisão
    56(i) com roupa nova."""
    d = _cenario(front, "teto_em_99_enquanto_nao_terminou")
    assert d["pct"] == 99


def test_esperar_dependencia_nao_e_trabalho(front):
    """Fila não acumula: contá-la faria o número SUBIR enquanto nada acontece,
    que é o oposto do que ele existe para dizer. É a mesma regra da marca
    `⚠ 2x`, que também ignora quem está esperando."""
    assert _cenario(front, "esperando_dependencia_nao_acumula")["pct"] == 0
    assert _cenario(front, "falha_e_pulado_somam_zero")["pct"] == 0


def test_um_membro_sem_amostra_apaga_o_numero_inteiro(front):
    """*"Só aparece com `n ≥ 5` em TODOS os membros do snapshot. Faltando
    histórico em um só, o percentual some (não é estimado, não é 'aproximado
    com ressalva')"*.

    O piso é do CONJUNTO porque a fatia do membro sem amostra seria ZERO no
    denominador — e um denominador incompleto infla tudo o que está em cima."""
    d = _cenario(front, "um_membro_sem_amostra_apaga_o_numero")
    assert d["completo"] is False
    assert d["resultado"] is None


def test_corrida_terminal_nao_tem_percentual(front):
    """*"e **sem percentual nenhum** em corrida terminal: lá o estado já diz
    tudo"*. Um "≈ 94%" ao lado de "concluída" só levantaria a dúvida de onde
    foram parar os 6%."""
    d = _cenario(front, "corrida_terminal_nao_tem_percentual")
    assert d["concluida"] is None
    assert d["falha"] is None
    assert d["sem_trabalho"] is None


def test_o_decorrido_do_percentual_respeita_os_dois_relogios(front):
    """Decisão 60 aplicada ao percentual: o decorrido do membro vivo é
    `inicio → apurado_em` (os DOIS do banco) mais o que passou no relógio
    LOCAL desde a resposta.

    Com o navegador 3h atrás — o desvio MEDIDO no dev —, um `Date.now() −
    inicio` daria negativo e o número nasceria em 0% a madrugada inteira. E ele
    ANDA entre refetches, senão o painel congelaria por 15 s a cada ciclo."""
    d = _cenario(front, "relogio_do_banco_mais_o_local")
    assert d["no_instante"]["pct"] == 29
    assert d["dez_min_depois"]["pct"] > d["no_instante"]["pct"]


def test_o_x_de_y_continua_sendo_o_PRIMEIRO_numero(front):
    """*"Ele nunca substitui o `x de y`, que continua sendo o número primário e
    o primeiro a ser lido. O percentual é o SEGUNDO"*.

    A ordem é a do DOM, que é a ordem em que o leitor de tela anuncia — não
    basta ser o segundo no CSS."""
    d = _cenario(front, "percentual_e_o_segundo_numero_da_faixa")
    ordem = [t for t in d["ordem"] if t not in ("·",)]
    assert ordem[0] == "4 de 7 pipelines concluídos"
    assert ordem[1] == "≈ 38% do tempo típico"


def test_a_barra_continua_sem_percentual_de_contagem(front):
    """A Decisão 56 não volta pela porta da acessibilidade: o `aria-valuetext`
    da barra continua sendo `x de y` em pipelines, sem "%".

    É o percentual de CONTAGEM que ela proíbe — `4/7` anunciado como "57%" é
    progresso de um trabalho que não existe. O percentual desta fase mede
    TEMPO, é texto irmão da barra, e não o que ela anuncia."""
    d = _cenario(front, "percentual_e_o_segundo_numero_da_faixa")
    assert "%" not in d["aria_da_barra"]
    assert d["aria_da_barra"].startswith("4 de 7 pipelines concluídos")


def test_o_card_da_lista_nao_recebe_o_segundo_numero(front):
    """*"O percentual … some antes dele em qualquer aperto de espaço (card
    estreito, mobile)"*. No card cabe um número só, e o que fica é o primário."""
    assert "%" not in _cenario(front, "card_nao_recebe_percentual")["lido"]


# ═══════════ a palavra proibida: isto NÃO é previsão ═══════════════════════

_PROIBIDAS = ("previsão", "previsto para concluir", "estimativa", "ETA",
              "provavelmente", "tendência", "vai falhar", "risco de")


def test_nenhum_texto_desta_fase_promete_o_futuro():
    """Decisão 68 traça a fronteira: **contar desfechos PASSADOS não é
    previsão**, e prever é que está fora. O produto conta o que ACONTECEU e
    quem decide é a pessoa.

    O teste é sobre o FONTE (e não sobre um cenário) porque a proibição vale
    para toda frase do módulo, inclusive as que nenhum cenário exercita — é a
    mesma técnica com que a F12 protegeu a palavra "ETA" na duração típica."""
    literais = _literais("historicoCorridas.ts")
    for palavra in _PROIBIDAS:
        assert not re.search(rf"\b{re.escape(palavra)}\b", literais,
                             re.IGNORECASE), (
            f"a palavra {palavra!r} entrou num literal de "
            f"historicoCorridas.ts — este módulo CONTA, não prevê:\n"
            + literais)


def test_o_percentual_nunca_se_chama_progresso_nem_conclusao():
    """Decisão 56b: o rótulo é `≈ N% do tempo típico`, e o substantivo é
    TEMPO. "N% concluído" seria o percentual de contagem de volta, agora com
    minutos por baixo e a mesma leitura errada por cima."""
    fonte = _fonte("duracaoTipica.ts")
    assert "do tempo típico" in fonte
    for proibido in ("% concluído", "% do progresso", "progresso: "):
        assert proibido not in fonte


def test_o_piso_do_conjunto_esta_no_codigo_e_nao_so_no_comentario():
    """A regra que apaga o número inteiro (`completo !== true`) é a que mais
    custa a quem lê o código depois — e a mais fácil de "simplificar" fora sem
    perceber. Ela fica travada aqui pelo fonte."""
    fonte = _fonte("duracaoTipica.ts")
    assert "completo !== true" in fonte
    assert "TETO_PERCENTUAL_EM_VOO" in fonte
