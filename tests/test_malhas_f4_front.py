"""
F4 + F4+ da spec docs/spec-malha-execucao.md — a metade da fase que roda no
NAVEGADOR.

`test_malhas_f4_card.py` prova o que a API responde. Esta suíte prova o que o
operador LÊ, e existe porque três aceites da fase são afirmações sobre o
cliente, indemonstráveis no pytest sozinho:

  • **relógio deslocado 3 h** → o carimbo diz `agora`, nunca `há -3h`, e o
    alarme de dado velho dispara aos 90 s (F4+/4, Decisão 60). O defeito que
    ela evita SÓ existe quando os dois relógios existem: `apurado_em` vem do
    SQL Server (13:59 no dev) e `Date.now()` do navegador (10:59);
  • **"2 de 7", nunca "2 de 4"** (F4+/2, Decisão 52) — quem escreve a frase é
    `resumoCorrida()`; a API só devolve os números, e um `total − dispensados`
    no front recriaria o defeito do lado de cá;
  • **o travado FORA da barra** (F4+/3, Decisão 54) — é a separação entre
    `contagem` e `travados` no mesmo resumo.

── Como isto roda sem runner de JS ──────────────────────────────────────────
`ui-react/package.json` tem `dev`, `build` e `lint`, e mais nada. Acrescentar
vitest significaria acrescentar dependência de REDE a um produto que faz deploy
offline com wheels. Então a prova roda com o que já está instalado: o `sucrase`
que o Vite traz transpila os módulos PUROS — `tempoCorrida.ts`,
`statusExecucao.ts` e `fluxoExecucao.ts` nasceram sem React e sem import de
runtime exatamente para isto — e o Node executa o código do `src/`, byte a
byte. O único substituto é `lucide-react`, que vira um stub de MARCADORES para
que o teste possa afirmar *qual* ícone cada estado usa (Decisão 59: os três
vermelhos têm de ter ícones diferentes).

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar: quem roda o
pytest numa máquina sem o front instalado não pode ver vermelho por isso — mas
o salto é visível no `-rs`, e não silencioso.

── O que é provado por CONTRATO DO FONTE, e por quê ─────────────────────────
Dois aceites moram em JSX, dentro de componentes que só existem montados com
react-query, @xyflow/react e o roteador — montar isso aqui seria um runner de
testes disfarçado. São eles:

  • o card com o payload SEM a chave `corrida` (API velha) tem de cair no texto
    de hoje, sem exceção;
  • sem a 085, o banner verde do painel some JUNTO com o card verde.

Os dois viram asserção sobre o texto do fonte — a GUARDA literal que os
implementa. É prova mais fraca que executar, e por isso vem acompanhada de duas
defesas: `corrida?: CorridaApi` é OPCIONAL no tipo (acesso sem guarda não
compila, e o `tsc -b` é baseline de aceite da fase), e a mutação que apaga a
guarda deixa o teste vermelho — que é o critério de honestidade desta casa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f4_front_harness.cjs"
SRC = RAIZ / "ui-react" / "src"
MALHAS = SRC / "components" / "malhas"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente) — os testes de "
                 "contrato do fonte continuam valendo")

# O Vite exige Node moderno, mas a máquina pode ter DOIS: o do nvm no PATH e um
# `/usr/bin/node` antigo de pacote do sistema. O antigo não entende `??` — que
# `statusExecucao.ts` usa — e a bancada morreria com `SyntaxError` disfarçada de
# "teste vermelho", que é o pior dos dois mundos: nem prova, nem salta. Por isso
# a sonda pergunta a VERSÃO, e não só se o binário existe.
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


def _tem_runtime() -> bool:
    return _node() is not None


@pytest.fixture(scope="module")
def front() -> dict:
    """Roda a bancada UMA vez e devolve o JSON dos cenários.

    Um processo por sessão, não por teste: transpilar três módulos custa mais
    que o assert, e o que se prova aqui é o resultado, não o custo."""
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def _cenario(front: dict, nome: str) -> dict:
    """Cenário que levantou vira ESTE teste vermelho, não a suíte inteira."""
    dado = front[nome]
    assert "erro" not in dado, f"{nome} levantou no front:\n{dado.get('erro')}"
    return dado


# ═══════ F4+/4 — o relógio: o frescor é local, o decorrido vem do banco ══════

def test_o_frescor_diz_agora_com_o_banco_3h_a_frente(front):
    """Decisão 60, o aceite literal. No dev o SQL Server responde 13:59 e o
    navegador marca 10:59 — 3 h de desvio, MEDIDAS.

    A implementação ingênua (`Date.now() − apurado_em`) é publicada pela
    bancada junto com a real: é ela que prova que a armadilha existe NESTE
    cenário. Sem esse contraste, um teste de frescor num ambiente sem desvio
    passaria verde com a conta errada."""
    d = _cenario(front, "frescor_com_o_banco_3h_a_frente")
    # a armadilha é real aqui: a conta ingênua dá 3h NEGATIVAS
    assert d["ingenuo_ms"] == -3 * 3600_000 - 20_000
    # ...e o módulo não cai nela
    assert d["real"] == {"ms": 0, "texto": "agora", "velho": False}
    assert "-" not in d["real"]["texto"]
    # `apurado_em` sobrevive num lugar só: o texto ABSOLUTO do tooltip
    assert d["tooltip"] == "05/08/2026 13:59:20"


def test_o_alarme_de_dado_velho_dispara_aos_90s(front):
    """§9.4 — acima de 90 s sem refetch com sucesso o dado na tela é velho e o
    carimbo vira âmbar. Abaixo disso, não: um alarme que toca a cada polling
    de 20 s treina o operador a ignorar o alarme (Decisões 26/27)."""
    por_ms = {p["ms"]: p for p in _cenario(front, "frescor_por_idade")}
    assert por_ms[89_999]["velho"] is False
    assert por_ms[90_000]["velho"] is False
    assert por_ms[90_001]["velho"] is True
    assert por_ms[3_600_000]["velho"] is True


def test_o_frescor_tem_granularidade_grossa(front):
    """§9.4 — precisão de segundo em polling de 20 s sugere tempo real, e dois
    cards com "há 8s" e "há 31s" na mesma tela fazem duvidar dos dois."""
    por_ms = {p["ms"]: p["texto"] for p in _cenario(front, "frescor_por_idade")}
    assert por_ms[0] == "agora"
    assert por_ms[29_999] == "agora"
    assert por_ms[30_000] == "há menos de 1 min"
    assert por_ms[59_999] == "há menos de 1 min"
    assert por_ms[60_000] == "há 1 min"
    assert por_ms[150_000] == "há 2 min"
    # nenhum texto de frescor carrega segundos
    assert not any("s" == t.strip()[-1] and t[-2].isdigit()
                   for t in por_ms.values())


def test_relogio_local_ajustado_para_tras_nao_vira_tempo_negativo(front):
    """A outra ponta do mesmo defeito: o relógio da MÁQUINA sendo corrigido no
    meio da sessão faria "há -2 min", que é pior que a imprecisão do clamp."""
    assert _cenario(front, "frescor_com_relogio_local_para_tras") == {
        "ms": 0, "texto": "agora", "velho": False}


def test_o_decorrido_e_a_base_do_servidor_mais_o_delta_local(front):
    """`decorridoBase` vem subtraído pelo BANCO (`decorrido_min`); o front só
    soma o que passou no relógio DELE desde que a resposta chegou. Nenhuma das
    duas pontas mistura os dois relógios."""
    d = _cenario(front, "decorrido_soma_o_delta_local")
    assert d["base_mais_um_minuto"] == 43
    assert d["sem_base"] is None          # sem base não se inventa decorrido
    assert d["local_para_tras"] == 42     # nunca anda de ré


def test_a_faixa_mostra_o_decorrido_e_nao_o_relogio_do_banco(front):
    """O mesmo, já como TEXTO: 42 min de base + 61 s de relógio local = "há 43
    min". Se `apurado_em` (13:59) entrasse na conta contra a abertura lida do
    navegador, o card diria "há 3h49"."""
    assert _cenario(front, "tempo_relativo_com_a_corrida_aberta") == {
        "tempo": "há 43 min"}


def test_a_subtracao_entre_dois_carimbos_do_banco_e_legitima(front):
    """As duas pontas vêm do MESMO relógio: o desvio cancela. É o oposto de
    misturar `apurado_em` com `Date.now()`, e é o que dá o formato absoluto da
    corrida fechada."""
    d = _cenario(front, "duracao_entre_dois_carimbos_do_banco")
    assert d["corrida_inteira"] == 172 and d["texto"] == "2h52"
    assert d["formas"] == ["menos de 1 min", "1 min", "59 min", "1h", "1h30",
                           "24h", "25h 14min"]


def test_a_data_de_referencia_nao_anda_um_dia_para_tras(front):
    """`new Date('2026-08-05')` é lido como UTC e, em Brasília (UTC−3),
    `toLocaleDateString` devolve **04/08**: a corrida de HOJE apareceria como a
    de ontem no card. Por isso os carimbos são lidos por regex."""
    d = _cenario(front, "data_de_referencia_nao_anda_um_dia_para_tras")
    assert d["dia"] == "05/08" and d["dia_de_carimbo"] == "05/08"
    assert d["hora"] == "01:10"
    assert d["lixo"] == "sem formato"     # nunca "Invalid Date" na tela


# ═════════════════ o DEFEITO relatado, do lado do navegador ═════════════════

def test_o_card_diz_falhou_e_nomeia_carga_a(front):
    """O aceite da F4 no texto que o gestor lê às 8h: com `CARGA_A` em FALHA e
    `CARGA_B` concluído depois, o card não diz "sucesso · CARGA_B" — ele diz
    que a corrida está em andamento COM FALHA e escreve o nome do culpado."""
    d = _cenario(front, "o_defeito_relatado_no_texto_do_card")
    assert d["rotulo"] == "em andamento · com falha (ainda rodando)"
    assert d["culpado"] == "falhou: CARGA_A"
    assert "CARGA_B" not in d["rotulo"] and "CARGA_B" not in (d["culpado"] or "")
    # vermelho de CONTORNO (Decisão 59): acabou mal é cheio; isto ainda pode
    # virar, mas chama às 3h do mesmo jeito
    assert "border-red-400" in d["chip"] and "bg-red-50" in d["chip"]
    # e a faixa do painel usa a MESMA partição de cor: as duas superfícies não
    # podem discordar sobre o mesmo ciclo
    assert "red" in d["faixa"]
    # a palavra proibida não aparece em lugar nenhum deste card
    assert "conclu" not in d["rotulo"]
    assert "CARGA_A — falhou desde 03:00" in d["titulo"]


def test_a_saude_manda_na_cor_enquanto_o_ciclo_esta_aberto(front):
    """Decisão 11 + Decisão 59. Quatro saúdes, quatro leituras diferentes — e
    os DOIS âmbares (ATRASADA e SEM_PROGRESSO) se separam por ícone e por
    texto, nunca por cor."""
    d = _cenario(front, "a_saude_manda_na_cor_com_o_ciclo_aberto")
    assert d["OK"]["rotulo"] == "em andamento"
    assert "blue" in d["OK"]["chip"] and d["OK"]["animado"] is True
    assert d["COM_FALHA"]["rotulo"] == "em andamento · com falha (ainda rodando)"
    assert d["ATRASADA"]["rotulo"] == "em andamento · fora do prazo"
    assert d["SEM_PROGRESSO"]["rotulo"] == "em andamento · sem sinal"
    # os dois âmbares: mesma cor, ícones DIFERENTES
    assert d["ATRASADA"]["chip"] == d["SEM_PROGRESSO"]["chip"]
    assert d["ATRASADA"]["icone"] != d["SEM_PROGRESSO"]["icone"]
    # só o azul pulsa — animação em vermelho/âmbar seria alarme piscando
    assert not any(d[s]["animado"] for s in ("COM_FALHA", "ATRASADA",
                                             "SEM_PROGRESSO"))
    # corrida TERMINAL não herda saúde: o status já respondeu, e "concluída ·
    # com falha" seriam duas afirmações contraditórias na mesma linha
    assert d["TERMINAL_COM_SAUDE"]["rotulo"] == "concluída"


def test_os_tres_vermelhos_se_distinguem_sem_a_cor(front):
    """Decisão 59/(ii) — `FALHA`, `EXPIRADA` e `ABORTADA` compartilham o
    vermelho cheio, e é por isso que rótulo e ícone TÊM de diferir: senão o
    gestor reporta "3 incidentes" onde há três desfechos diferentes."""
    d = _cenario(front, "estilo_por_status")
    vermelhos = ["FALHA", "EXPIRADA", "ABORTADA"]
    assert len({d[s]["chip"] for s in vermelhos}) == 1
    assert len({d[s]["icone"] for s in vermelhos}) == 3
    assert len({d[s]["rotulo"] for s in vermelhos}) == 3
    # o único slate é "não havia trabalho" (Decisão 59): CANCELADA é âmbar,
    # porque cancelamento humano é item de auditoria e não pode virar cinza
    assert "slate" in d["SEM_TRABALHO"]["chip"]
    assert "amber" in d["CANCELADA"]["chip"]
    # status que o banco ganhe antes desta tela: neutro com o próprio texto,
    # nunca sumindo e nunca herdando a cor de outro estado
    assert d["ESTADO_QUE_NAO_EXISTE"]["rotulo"] == "estado que nao existe"
    assert "slate" in d["ESTADO_QUE_NAO_EXISTE"]["chip"]


def test_a_palavra_concluida_sai_de_um_estado_so(front):
    """Invariante 4 do §16 — nunca inventar verde. "concluída" é o rótulo de
    `CONCLUIDA` e de mais nada: `EXPIRADA` é "encerrada sem terminar",
    `ABORTADA` é "não chegou a começar"."""
    d = _cenario(front, "estilo_por_status")
    com_a_palavra = [s for s, e in d.items() if "conclu" in e["rotulo"]]
    assert com_a_palavra == ["CONCLUIDA"]


# ══════════ F4+/2 — o denominador do snapshot, que não encolhe ══════════════

def test_o_card_continua_dizendo_2_de_7_quando_a_guardia_pula_3(front):
    """Decisão 52, o aceite literal — o cenário `Carga_Vida`. Com
    `esperados = total − dispensados` o card passaria a dizer **`2 de 4`** e o
    olho leria "avançou" onde três pipelines foram BARRADOS.

    E a linha de baixo (Decisão 53) diz o que aconteceu, com o número."""
    d = _cenario(front, "duas_de_sete_com_tres_pulados")
    assert d["contagem"] == "2 de 7 pipelines concluídos"
    assert "2 de 4" not in d["contagem"]
    assert d["membros"] == ("7 membros nesta corrida · 3 não rodam hoje "
                            "(regra de dia)")
    assert d["vivos"] == "2 rodando"


def test_o_membro_inativado_na_sexta_nao_produz_um_sabado_verde_silencioso(front):
    """Decisão 53 — 7 no cadastro, 2 no snapshot: o card DIZ "5 fora desta
    corrida" ao lado do "2 de 2". Sem a subtração, o sábado sairia "2 de 2 ·
    concluída", verde, com um número dando autoridade à mentira."""
    d = _cenario(front, "membro_inativado_na_sexta_aparece_no_card")
    assert d["contagem"] == "2 de 2 pipelines concluídos"
    assert "5 fora desta corrida" in d["membros"]
    # corrida fechada usa o formato ABSOLUTO, nunca o relativo (§9.4)
    assert d["tempo"] == "01:10 → 04:02 · 2h52"


def test_a_faixa_do_painel_conta_a_mesma_subtracao_que_o_card(front):
    """⚠️ REGRESSÃO da revisão adversarial — a Decisão 53 valendo só em metade
    das superfícies.

    O card passa `qtd_pipelines` para `resumoCorrida`; a FAIXA do painel não
    tem o cadastro em mãos e chamava com dois argumentos. Resultado: o card
    dizia "2 de 2 · 5 fora desta corrida" e a faixa, sobre a MESMA corrida na
    mesma tela, dizia só "2 membros nesta corrida" — a omissão que a Decisão 53
    existe para matar, um andar acima.

    `membros_inativos` viaja no payload da corrida e é a segunda fonte. Vence a
    MAIOR das duas: o cadastro pega também quem ENTROU na malha depois da
    abertura, e o snapshot pega quem já estava inativo — cada uma enxerga
    metade do fato."""
    d = _cenario(front, "a_faixa_do_painel_tambem_diz_quem_ficou_fora")
    assert "5 fora desta corrida" in d["faixa"]
    assert d["faixa"] == d["card"]


def test_corrida_recem_aberta_nao_acusa_um_pipeline_por_ordem_alfabetica(front):
    """⚠️ REGRESSÃO da revisão adversarial — o alarme falso das 01:10.

    Nos primeiros segundos de TODA corrida o snapshot inteiro está sem linha e
    cai em `nao_partiu`. O servidor já não conta isso como travado; do lado do
    cliente, escrever "↳ não chegou a iniciar: A" num ciclo de 30 segundos
    seria acusar por ordem alfabética um pipeline que está apenas na fila —
    e o card ficaria azul com uma linha de culpa embaixo.

    Fechada a corrida, o MESMO dado vira veredito: aí "não chegou a iniciar" é
    a resposta certa, e ela volta."""
    d = _cenario(front, "corrida_recem_aberta_nao_acusa_ninguem")
    assert d["aberta_culpado"] is None
    assert d["aberta_travados"] is None
    assert d["aberta_rotulo"] == "em andamento"
    assert "blue" in d["aberta_faixa"]
    # e o veredito existe quando o ciclo acabou
    assert d["fechada_culpado"] == "não chegou a iniciar: A"


# ═════════════ F4+/3 — o travado FORA do que a barra preenche ═══════════════

def test_o_travado_e_chip_e_nao_comprimento_de_barra(front):
    """Decisão 54 — a barra responde UMA coisa: quanto já ficou pronto. O
    travado sai num campo PRÓPRIO, e o numerador não o absorve: `3 de 7` com 2
    travados nunca vira `5 de 7`."""
    d = _cenario(front, "travado_e_chip_e_nao_comprimento")
    assert d["contagem"] == "3 de 7 pipelines concluídos"
    assert d["travados"] == "2 travados"
    # o card nomeia UM culpado, e é o mais grave (o servidor já ordena)
    assert d["culpado"] == "falhou: CARGA_A"
    # ...e o tooltip nomeia os dois, cada um com a SUA classe — nunca "2
    # pendentes", que somaria dois problemas de donos diferentes (Decisão 21)
    assert "CARGA_A — falhou" in d["titulo"]
    assert "CARGA_Z — esperando outro pipeline" in d["titulo"]
    assert "2 pendentes" not in d["titulo"]


# ══════════ Decisão 57 — desfecho interrompido não é progresso ══════════════

def test_desfecho_interrompido_diz_parou_em_e_sem_trabalho_nao_tem_contagem(front):
    """Decisão 57 — 0% lê como "falhou tudo" e 100% como "rodou tudo", e nos
    três desfechos interrompidos nenhum dos dois é verdade."""
    d = _cenario(front, "desfechos_que_nao_sao_progresso")
    for status in ("EXPIRADA", "ABORTADA", "CANCELADA"):
        assert d[status]["contagem"] == "parou em 4 de 7"
        assert "conclu" not in d[status]["contagem"]
    assert d["CONCLUIDA"]["contagem"] == "4 de 7 pipelines concluídos"
    # SEM_TRABALHO: sem barra, sem "x de y", sem alarme — e a frase explica
    assert d["SEM_TRABALHO"]["contagem"] is None
    assert d["SEM_TRABALHO"]["membros"] == ("os 7 membros não rodam hoje "
                                            "(regra de dia)")
    # e sem alarme: sábado normal em vermelho é o alarme falso SEMANAL que
    # treina o operador a ignorar o alarme (Decisões 26/27)
    assert "red" not in d["SEM_TRABALHO"]["faixa"]
    assert "amber" not in d["SEM_TRABALHO"]["faixa"]


# ═════════════════ Decisão 41 — a degradação, dos dois lados ════════════════

def test_payload_sem_o_bloco_corrida_nao_chama_nada_da_corrida(front):
    """Front NOVO contra API VELHA: a chave `corrida` não existe, o resumo é
    `null` e o fallback continua no payload. Zero exceção — e zero invenção."""
    d = _cenario(front, "api_velha_sem_o_bloco_corrida")
    assert d["resumo"] is None
    assert d["tem_fallback"] is True


def test_corrida_sem_contadores_nao_quebra_nem_desenha_zero(front):
    """Lock timeout na consulta do denominador: o ESTADO do ciclo sai, os
    contadores vêm `null`. `null` é "não consegui apurar" e é diferente de `0`,
    que a tela desenharia como barra vazia — uma medida que ninguém tomou."""
    d = _cenario(front, "corrida_sem_contadores_nao_quebra_a_tela")
    assert d["rotulo"] == "falhou"
    assert d["contagem"] is None and d["membros"] is None
    assert d["travados"] is None and d["vivos"] is None
    assert "0 de 0" not in json.dumps(d, ensure_ascii=False)
    assert "NaN" not in json.dumps(d) and "undefined" not in json.dumps(d)
    # o que ele SABE continua sendo dito
    assert d["tempo"] == "01:10 → 04:02 · 2h52"


# ═══════════ a navegação entre duas corridas do MESMO ODATE ═════════════════

def test_duas_corridas_do_mesmo_dia_se_distinguem_no_texto(front):
    """Aceite da F4 — o ◀ ▶ anda por CORRIDA. Se as duas se chamassem "corrida
    de 05/08", navegar entre elas seria indistinguível de não navegar."""
    d = _cenario(front, "duas_corridas_do_mesmo_dia_tem_rotulos_distintos")
    assert d["primeira"] == "corrida de 05/08 · falhou · aberta 01:10"
    assert d["segunda"] == "2ª corrida de 05/08 · concluída · aberta 05:00"
    assert d["identidades"] == ["corrida de 05/08", "2ª corrida de 05/08"]
    # Decisão 74: o `#` do formato de máquina não aparece na interface — numa
    # malha diária "#12" lê-se como "12ª tentativa hoje", que é falso
    assert "#" not in "".join(d["identidades"] + [d["primeira"], d["segunda"]])


def test_nenhum_nome_de_maquina_chega_a_tela(front):
    """Decisão 74 — `aberta_por` e `fechada_por` são formato de máquina
    (`inicio:#12`, `manual:C123456`, `guardia`). Nenhum deles é publicado cru,
    e o `#` nunca sobrevive."""
    d = _cenario(front, "quem_fez_traduz_o_formato_de_maquina")
    assert d["manual"] == "C123456"          # a matrícula, sem o prefixo
    assert d["inicio"] == "o agendamento do Início"
    assert d["guardia"] == "o monitor automático"
    assert d["no_fim"] == "o nó Fim"
    assert d["vazio"] is None
    assert not any("#" in v for v in d.values() if isinstance(v, str))
    assert not any(":" in v for v in d.values() if isinstance(v, str))


def test_o_cancelamento_fica_auditavel_no_card(front):
    """Decisão 67 — no fechamento do mês, três corridas canceladas precisam ser
    explicáveis sem abrir o banco: quem, quando e por quê. E o prefixo que o
    servidor compõe não é repetido em cima da frase que o operador escreveu."""
    d = _cenario(front, "cancelamento_e_auditavel")
    assert d["encerramento"] == "encerrada por C123456 às 04:02"
    assert d["motivo"] == 'motivo: "fonte indisponível, refazemos amanhã"'
    assert "encerrada por C123456:" not in d["motivo"]
    assert "amber" in d["faixa"]             # ação humana é âmbar, não cinza


def test_a_divergencia_de_odate_e_nominal(front):
    """Decisão 66 — o incidente que originou a spec (`Carga_Vida`) aparece como
    banner com NÚMERO, não como nota de rodapé."""
    assert _cenario(front, "fora_do_odate_e_nominal_e_ambar")["foraDoOdate"] == (
        "3 pipelines de outra data de referência")


def test_sem_sinal_diz_ha_quanto_tempo(front):
    """§9.3 — "sem sinal" sem o tempo não decide nada; e os minutos vêm do
    BANCO (`sem_sinal_min`, já subtraído lá), não de conta no cliente."""
    d = _cenario(front, "sem_progresso_conta_pelo_relogio_do_banco")
    assert d["rotulo"] == "em andamento · sem sinal há 40 min"
    assert "amber" in d["faixa"]


# ═══════════════════ §9.9 — o canvas da visão de execução ═══════════════════

def test_esperando_deixa_de_ser_igual_a_ninguem_pediu(front):
    """Até esta fase `AGUARDANDO_DEPENDENCIA` devolvia `null` e a linha ficava
    IDÊNTICA à de quem não rodou — a diferença entre "ninguém pediu" e "está
    parado esperando alguém" sumia justamente no desenho que existe para
    mostrar onde a corrida parou."""
    d = _cenario(front, "estado_do_pipeline_no_canvas")
    assert d["AGUARDANDO_DEPENDENCIA"] == "esperando"
    assert d["SUCESSO"] == "concluido" and d["EXECUTANDO"] == "ativo"
    assert d["FALHA"] == "bloqueado" and d["NAO_LIBEROU"] == "bloqueado"
    # PULADO continua NEUTRO: o dia foi barrado pela regra de agenda, e pintar
    # de vermelho mandaria o plantonista investigar um sábado normal
    assert d["PULADO"] is None and d["null"] is None


def test_a_linha_que_espera_nao_anda(front):
    """Animação em cima de espera é a tela prometendo movimento que não está
    acontecendo. E o traço tem padrão PRÓPRIO: duas coisas tracejadas na mesma
    tela (o cadeado da linha compilada por outra malha é `6 3`) precisam de um
    segundo canal."""
    d = _cenario(front, "a_linha_que_espera_nao_anda")
    assert d["esperando"]["animated"] is False
    assert d["esperando"]["style"]["strokeDasharray"] == "4 4"
    assert d["ativo"]["animated"] is True
    assert "strokeDasharray" not in d["ativo"]["style"]
    # âmbar nos dois temas (a casa exige par claro+escuro)
    assert d["esperando"]["style"]["stroke"] != d["escuro"]
    # o trecho para quem ESPERA vem antes do "predecessor pronto = avançando"
    assert d["aresta_pronta_para_quem_espera"] == "esperando"
    assert d["aresta_pronta_para_quem_nao_partiu"] == "ativo"
    assert d["aresta_bloqueada"] == "bloqueado"
    # cor nunca é canal único: cada estado tem rótulo em pt-BR
    assert set(d["rotulos"]) == {"concluido", "ativo", "esperando", "bloqueado",
                                 "inerte"}
    assert d["rotulos"]["esperando"] == "esperando outro pipeline"


# ═════════ contrato do FONTE: as duas guardas que moram no JSX ══════════════

def _fonte(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _codigo(caminho: Path) -> str:
    """O fonte SEM os comentários de linha. Estes arquivos explicam as regras
    em prosa — procurar `Date.now()` no texto inteiro acharia a frase que
    proíbe `Date.now()`, e o teste provaria o contrário do que quer provar."""
    return "\n".join(ln for ln in _fonte(caminho).splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*")))


def test_o_card_le_a_corrida_por_guarda_e_nao_por_flag():
    """Decisão 41 — a degradação é por AUSÊNCIA DE CAMPO, POR MALHA. O card
    testa `malha.corrida`, nunca `migration_085_pendente`: uma API velha não
    manda flag nenhuma, e um front que decidisse pela flag concluiria "está
    tudo certo" e renderizaria `corrida` indefinida.

    (Prova de fonte, e não de execução: o guard mora dentro do `MalhaCard`, que
    só monta com react-query e o roteador. A segunda defesa é o tipo —
    `corrida?: CorridaApi` é opcional, e acesso sem guarda não compila.)"""
    src = _fonte(SRC / "pages" / "Malha.tsx")
    assert "const corrida = malha.corrida ?? null" in src
    assert "corrida ? resumoCorrida(" in src
    # o fallback continua existindo, e CONFESSA de onde veio o status
    assert "(membro mais recente" in src
    # o tipo é opcional: sem isso, o `tsc -b` deixaria passar acesso sem guarda
    assert "corrida?: CorridaApi" in src
    # e a flag NÃO decide renderização — ela só acrescenta a linha de aviso
    assert "!resumo && sem085" in src


def test_sem_a_085_o_banner_verde_do_painel_some_junto_com_o_card():
    """Aceite da F4 — "card e painel degradam JUNTOS: o banner verde some junto
    com o card verde, e a palavra 'concluída' não aparece em nenhum dos dois".

    Sem a 085 o card perde a chave `corrida` e cai no "(membro mais recente)",
    que nunca diz "concluída". O painel precisa da MESMA disciplina: o evento
    `MALHA_CONCLUIDA` continua na tabela e pintaria o banner verde sozinho, com
    o card ao lado sem poder afirmar nada. `!sem085` é a guarda que impede um
    verde sobrando de cada vez."""
    src = _fonte(MALHAS / "MalhaEditor.tsx")
    assert "emExecucao && !corrida && !sem085 && execData?.malha_concluida?.em" in src
    assert "const sem085 = execData?.migration_085_pendente === true" in src
    # com corrida, quem afirma "concluída" é o STATUS dela — nunca o evento
    assert "const corrida = execData?.corrida ?? null" in src


def test_o_no_FIM_no_canvas_nao_fica_verde_com_a_corrida_em_falha():
    """⚠️ REGRESSÃO da revisão adversarial da F4 — a mentira voltando pela
    porta do CANVAS.

    `eventos_no` é recortado por DATA e nunca por corrida: a tabela
    `etl_dependencia_evento` é chaveada por (pipeline, data, tipo) e o marcador
    `#no:{id}` não carrega o id do ciclo (é a Decisão 49, que só chega na F9).
    Então o `MALHA_CONCLUIDA` que a corrida #1 de 04/08 emitiu às 04:02
    CONTINUA na resposta quando a lente está na corrida #2 do MESMO dia — o
    redisparo às 05h depois de um incidente, que é gesto diário e é o próprio
    aceite "duas corridas no mesmo ODATE" desta fase.

    A API já parou de publicar `malha_concluida` nesse caso (o banner verde foi
    corrigido). O nó Fim lia o evento CRU: ficava verde, com o tooltip "malha
    concluída às 04:02", a 3 cm de uma faixa dizendo "em andamento · com
    falha" — e a aresta que chega nele virava "trecho percorrido", verde também
    (`estadoDoComponente` deriva de `concluidaEm`). Metade da correção desfeita
    pelo desenho.

    A guarda: com corrida no payload, o verde do Fim depende do STATUS DELA;
    sem corrida (API anterior, banco sem a 085), o nó volta a ler o evento —
    degradação junto com o card, nunca um verde sobrando de cada vez."""
    src = _codigo(MALHAS / "MalhaEditor.tsx")
    # o evento deixa de ir direto para `concluidaEm`
    assert "concluidaEm: ciclo.concluido === false ? null : evento" in src
    # e o que decide é o status do ciclo, com `null` = "não há corrida"
    assert "const cicloConcluido = corrida === null ? null : " \
           "corrida.status === 'CONCLUIDA'" in src
    assert "{ aberto: cicloAberto, concluido: cicloConcluido }" in src


def test_os_modulos_da_corrida_continuam_puros():
    """`tempoCorrida.ts` só é testável com o relógio deslocado porque é PURO —
    um import de React nele tiraria dele exatamente a propriedade que o torna
    confiável, e esta bancada pararia de existir. O hook fica à parte."""
    # Só as linhas de CÓDIGO: os dois módulos explicam a regra em comentário
    # ("sem React, sem import nenhum"; "nunca subtrair de `Date.now()`"), e um
    # `in` sobre o arquivo inteiro pegaria a explicação em vez do fato.
    tempo = _codigo(MALHAS / "tempoCorrida.ts")
    assert not [ln for ln in tempo.splitlines()
                if ln.lstrip().startswith(("import ", "import{", "require("))], (
        "tempoCorrida.ts ganhou um import — o módulo tem de continuar puro")
    assert "Date.now()" not in tempo, (
        "tempoCorrida.ts leu o relógio por conta própria — os dois instantes "
        "entram por PARÂMETRO, senão o teste com relógio deslocado não existe")
    # ...e o relógio de verdade mora no hook, que é quem pode ter React
    hook = _codigo(MALHAS / "useDecorrido.ts")
    assert "from 'react'" in hook and "Date.now()" in hook


@pytest.mark.skipif(not _tem_runtime(), reason=_MOTIVO_SALTO)
def test_a_bancada_do_front_roda_os_modulos_do_src_e_nao_uma_copia():
    """Meta-teste: a bancada transpila `ui-react/src/...` — se alguém mover ou
    renomear os módulos, isto fica vermelho em vez de a suíte inteira SALTAR e
    ninguém perceber que o front deixou de ser testado."""
    for modulo in ("tempoCorrida.ts", "statusExecucao.ts", "fluxoExecucao.ts"):
        assert (MALHAS / modulo).is_file()
    assert HARNESS.is_file()
    assert "ui-react', 'src', 'components', 'malhas'" in _fonte(HARNESS)
