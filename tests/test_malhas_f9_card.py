"""
F9 da spec `docs/spec-malha-execucao.md` — o CARD da lista, provado
RENDERIZADO: `CorridaBadge`, `CorridaProgresso` e as derivações puras de
`statusExecucao.ts` que os alimentam.

O que esta suíte guarda, e por que cada coisa é um teste
────────────────────────────────────────────────────────
A F4 fez a VERACIDADE (o card parou de mentir sobre o ESTADO). A F9 responde a
segunda pergunta da §9.0 — **em que pé está?** — e é aqui que uma barra de
progresso pode voltar a mentir de três jeitos novos:

1. **barra CHEIA lida como "concluída".** Corrida `ABERTA` com todos os membros
   prontos ainda está fechando: o último pipeline ficou verde às 04:02 e a
   corrida fecha 15 min depois do último movimento. Chamar isso de concluída é
   antecipar a mentira de sempre em 15 minutos. As palavras `100%` e
   `concluída` são testadas como **ausência** — e note que `concluídos`, no
   masculino plural, é o vocabulário CORRETO ("4 de 7 pipelines concluídos"):
   o que não pode aparecer é o feminino, que descreve a CORRIDA;
2. **percentual de CONTAGEM** (Decisão 56). "4 de 7" lido como "57%" é
   percentual de um trabalho que não existe — os pipelines têm durações
   diferentes. E ele entra sem ninguém ver pela porta da acessibilidade: sem
   `aria-valuetext`, o leitor de tela CALCULA `valuenow/valuemax` e anuncia o
   percentual sozinho. Por isso a prova de ausência varre também os `aria-*`;
3. **sábado sem trabalho desenhado como 0 ou como cheio** (Decisão 57). Nenhum
   dos dois aconteceu: a barra tem de DESAPARECER, e "nenhuma barra" é uma
   afirmação sobre a árvore — uma barra com `total = 0` passaria em qualquer
   teste de string.

E o estado que não existia: **a corrida que não abriu** (Decisão 58), com o
atraso andando pelo relógio LOCAL sobre um número medido no SERVIDOR — nunca
`Date.now() − carimbo do banco`, que com o desvio de 3h do dev diria "há 10h"
onde são 6h.

── Como isto roda sem runner de JS ─────────────────────────────────────────
Mesma técnica de `test_malhas_f4_front.py` e `test_ui_base_f9.py`: o `sucrase`
que o Vite já traz transpila os arquivos do `src/` (JSX clássico apontando para
um `__h` nosso, que devolve a árvore como objeto puro) e o Node executa. Os dois
componentes são funções de renderização sem hook e sem estado — foi assim que
nasceram, e é por isso que dá para chamá-los direto.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar — visível no
`-rs`, nunca silenciosa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f9_card_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente)")
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
def card() -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def _cenario(card: dict, nome: str) -> dict:
    """Cenário que levantou vira ESTE teste vermelho, não a suíte inteira."""
    dado = card[nome]
    assert "__erro__" not in dado, \
        f"{nome} levantou no front:\n{dado.get('__erro__')}"
    return dado


# ═══════ 1. sábado com todos dispensados: NENHUMA barra (Decisão 57) ════════

def test_sabado_sem_trabalho_nao_desenha_barra_nenhuma(card):
    """O aceite literal, e ele é de AUSÊNCIA: sem barra, com "nada previsto", e
    a palavra "concluída" fora da tela.

    0% leria como "falhou tudo" e a barra cheia como "rodou tudo" — num sábado
    legítimo nenhum dos dois aconteceu, e o alarme que aparece todo sábado
    treina o operador a ignorar o alarme (Decisões 26/27)."""
    d = _cenario(card, "sabado_sem_trabalho")
    assert d["barra"] is None                     # NENHUMA barra na árvore
    assert d["nada_previsto"] == "nada previsto"
    assert d["contagem"] is None                  # nem "0 de 7", nem "7 de 7"
    assert d["membros"] == "os 7 membros não rodam hoje (regra de dia)"
    assert d["rotulo_do_estado"] == "sem trabalho hoje"
    lido = d["lido"].lower()
    assert "concluída" not in lido and "concluida" not in lido
    assert "%" not in lido


# ═══════ 2. barra CHEIA não é "concluída" (Decisões 45 e 56) ════════════════

def test_corrida_aberta_com_tudo_pronto_diz_fechando(card):
    """`ok == total − dispensados` com a corrida ABERTA: a barra fecha e o
    vocabulário NÃO muda.

    O rótulo é "7 de 7 · fechando", seguido do que falta — a REGRA antes da
    hora. Anunciar só "fecha às 04:17" produziria o chamado falso das 04:18,
    porque a carência REINICIA a cada movimento."""
    d = _cenario(card, "corrida_aberta_com_tudo_pronto")
    assert d["fechando"] is True
    assert d["contagem"] == "7 de 7 · fechando"
    assert d["fechamento"] == ("fecha 15 min após o último movimento; "
                               "se nada mais mexer, por volta de 04:17")
    # a barra está CHEIA — e cheia é um fato do desenho, não uma conclusão
    assert d["barra"]["valorAtual"] == d["barra"]["total"] == 7

    # ── a prova de AUSÊNCIA, sobre TUDO que é lido (texto, title, aria-*) ──
    lido = d["lido"].lower()
    assert "100%" not in lido and "%" not in lido
    assert "concluída" not in lido and "concluida" not in lido
    # o tooltip é lido pelo operador com o mouse parado: vale a mesma regra
    titulo = d["titulo_da_corrida"].lower()
    assert "100%" not in titulo and "concluída" not in titulo


def test_barra_cheia_com_dispensados_nao_encolhe_o_denominador(card):
    """5 prontos + 2 que não rodam hoje = os 7 do snapshot.

    O denominador é `membros_total` e ele NÃO ENCOLHE (Decisão 52): jamais
    "5 de 5". A barra fecha porque o trilho hachurado ocupa o resto — e a linha
    de baixo diz, sempre, quem não rodou (Decisão 53)."""
    d = _cenario(card, "barra_cheia_com_dispensados")
    assert d["contagem"] == "5 de 7 · fechando"
    assert d["membros"] == "7 membros neste ciclo · 2 não rodam hoje (regra de dia)"
    assert d["barra"]["total"] == 7 and d["barra"]["valorAtual"] == 5
    assert [s["chave"] for s in d["barra"]["segmentos"]] == ["ok", "dispensado"]
    assert d["barra"]["valorTexto"] == ("5 de 7 pipelines concluídos, "
                                        "2 não rodam hoje")
    lido = d["lido"].lower()
    assert "%" not in lido and "concluída" not in lido


def test_malha_com_no_fim_nao_descreve_o_relogio_errado(card):
    """Malha que fecha pelo nó Fim não tem carência: dizer "fecha 15 min após o
    último movimento" ali mandaria o operador esperar um relógio parado."""
    d = _cenario(card, "malha_com_no_fim_nao_promete_o_relogio_errado")
    assert d["fechamento"] == "aguarda o nó Fim registrar a conclusão"


def test_barra_cheia_com_no_segurado_nao_promete_hora_de_fechamento(card):
    """HOLD: o relógio de fechamento NÃO está correndo, e a frase não pode
    fingir que está.

    Com nó segurado, "o teto não corre, a quiescência não avalia"
    (`malha_corrida.hold_da_malha`, §6.7/Decisão 30). `quiescencia_ate`
    continua sendo `último movimento + carência` e vira um carimbo que o hold
    deixou para trás: com movimento às 02:30 e retenção às 02:40, a frase de
    sempre anunciaria "por volta de 02:45" — uma hora JÁ PASSADA, para um
    fechamento que não vai acontecer enquanto o cadeado estiver posto.

    É o mesmo defeito que a F7 pagou na barra de limite (ela enchia durante o
    hold e contradizia o texto ao lado). A linha que se contradiz sozinha leva
    junto a confiança em todas as outras."""
    d = _cenario(card, "barra_cheia_com_no_segurado_nao_promete_hora")
    assert d["fechando"] is True
    assert d["contagem"] == "7 de 7 · fechando"
    assert d["fechamento"] == ("o fechamento está parado — 2 nós segurados "
                               "desde 02:40")
    # NENHUMA hora prometida, e nenhuma menção à carência que não está correndo
    assert "por volta de" not in d["lido"]
    assert "02:45" not in d["lido"]
    assert "15 min após" not in d["lido"]


def test_snapshot_vazio_nao_publica_zero_de_zero(card):
    """`membros_total = 0` é fato do CADASTRO, não medida de trabalho.

    "0 de 0 pipelines concluídos" publicaria zero como se fosse a medida de um
    trabalho que não existiu — e essa frase chegava ao `title` do card, que é o
    que o operador lê com o mouse parado. §9.9 nomeia o estado: *"a corrida
    abriu sem membros ativos"*. É diferente de `membros_total` NULO, que é
    "não consegui apurar" e pede outra ação (tentar de novo, não olhar a
    malha)."""
    d = _cenario(card, "snapshot_vazio_nao_publica_zero_de_zero")
    assert d["contagem"] is None
    assert d["fechando"] is False        # barra CHEIA de nada não é "fechando"
    assert d["barra"] is None
    assert d["membros"].startswith("o ciclo abriu sem membros ativos")
    assert "0 de 0" not in d["lido"] and "0 de 0" not in d["titulo"]


def test_o_leitor_de_tela_ouve_o_singular_quando_o_membro_e_um(card):
    """O `aria-valuetext` é a única frase da barra que só quem NÃO enxerga
    ouve — e era a única da tela em português errado: "1 de 1 pipelines
    concluídos" enquanto o texto visível ao lado já dizia "pipeline
    concluído"."""
    d = _cenario(card, "um_membro_so_fala_no_singular")
    assert d["contagem"] == "0 de 1 pipeline concluído"
    assert d["valorTexto"] == "0 de 1 pipeline concluído, 1 em execução"


# ═══════ 3. desfecho interrompido: barra congelada (Decisões 57 e 67) ═══════

def test_expirada_congela_a_barra_e_diz_onde_parou(card):
    """"parou em 4 de 7" + `opacity-60`. A palavra "concluído" não aparece em
    nenhum dos três desfechos interrompidos (invariante 4 do §16: nunca
    inventar verde)."""
    d = _cenario(card, "expirada_congela_a_barra")
    assert d["contagem"] == "parou em 4 de 7"
    assert "opacity-60" in d["classes"]
    # o travado fica FORA do que a barra preenche (Decisão 54)
    assert d["travados"] == "2 travados"
    assert sum(s["valor"] for s in d["barra"]["segmentos"]) == 4
    assert d["barra"]["total"] == 7
    assert d["estilo"]["rotulo"] == "encerrado sem terminar"
    # ícone PRÓPRIO: os três vermelhos não podem ser indistinguíveis para quem
    # não separa vermelho de âmbar
    assert d["estilo"]["icone"] == "icone:TimerOff"
    assert "concluíd" not in d["lido"].lower()


def test_cancelada_mostra_quem_encerrou_e_o_motivo(card):
    """Decisão 67 — `fechada_por` e `motivo` são gravados desde a F3 e nunca
    foram mostrados. Fechar o mês com 3 corridas canceladas e não conseguir
    explicar nenhuma sem abrir o banco é o defeito que isto mata."""
    d = _cenario(card, "cancelada_diz_quem_e_por_que")
    assert d["contagem"] == "parou em 4 de 7"
    assert d["encerramento"] == "encerrada por C123456 às 05:20"
    assert d["motivo"] == 'motivo: "carga do dia 03 remarcada para a tarde"'
    # âmbar de CONTORNO, nunca cinza: é ação humana, e é item de auditoria
    assert "amber" in d["estilo"]["chip"]
    assert d["estilo"]["icone"] == "icone:Ban"
    # e ela está na lista que congela a barra — quem escreve "parou em" e quem
    # apaga a barra leem a MESMA lista
    assert set(d["congelado_pela_lista"]) == {"EXPIRADA", "ABORTADA", "CANCELADA"}


# ═══════ 4. a corrida que NÃO ABRIU (Decisão 58) ════════════════════════════

def test_nao_abriu_e_um_estado_da_tela(card):
    """Âmbar, com o horário previsto e o atraso — e sem barra nenhuma.

    Âmbar e não vermelho: pela partição da Decisão 59, vermelho CHEIO é "acabou
    mal", e este ciclo não chegou a começar."""
    d = _cenario(card, "nao_abriu")
    assert d["estilo"]["rotulo"] == "não abriu"
    assert d["estilo"]["icone"] == "icone:CalendarX"
    assert "amber" in d["estilo"]["chip"]
    assert d["cabecalho"] == "previsto para 01:00 · há 6h"
    assert d["sem_corrida"] == "nenhum ciclo de 05/08"
    # a pílula anuncia "não abriu" mesmo com a corrida de ONTEM em mãos: o que
    # o operador precisa saber às 8h não é que ontem foi bem
    assert "não abriu" in d["badge_lido"]
    assert "concluíd" not in d["badge_lido"].lower()
    # o tooltip diz o que fazer, não só o que houve
    assert "DAG do Início" in d["titulo"]


def test_nao_abriu_bloqueada_diz_que_e_a_de_ontem_que_segura(card):
    """Muda a AÇÃO: não é "o Airflow morreu", é "alguém precisa fechar a de
    ontem" — o ciclo aberto bloqueia a partida da próxima."""
    d = _cenario(card, "nao_abriu_bloqueada_pela_de_ontem")
    assert d["bloqueio"] == ("o ciclo anterior continua aberto — enquanto ela "
                             "não fechar, a próxima não abre")


def test_o_atraso_anda_pelo_relogio_local_sobre_a_medida_do_servidor(card):
    """Decisão 60 aplicada ao atraso: o número vem medido do SERVIDOR e só
    ganha o que passou no relógio LOCAL desde a resposta.

    A conta ingênua (`Date.now() − atrasada_desde`) daria ~10h para um atraso de
    6h, porque `atrasada_desde` está na régua do BANCO — 3h à frente no dev. O
    cenário publica os dois números para que a armadilha seja provada existente
    ANTES de se provar que o módulo escapa dela."""
    d = _cenario(card, "atraso_anda_com_o_relogio_local")
    assert d["agora"] == "previsto para 01:00 · há 6h"
    assert d["um_minuto_depois"] == "previsto para 01:00 · há 6h01"
    assert d["ingenuo_min"] == 599        # a armadilha existe nesta bancada


# ═══════ 5. Decisão 56 — nenhum percentual, em superfície nenhuma ═══════════

def test_nenhum_estado_produz_percentual(card):
    """Cinco estados, tudo que é lido em cada um: texto, `title`, `aria-label` e
    `aria-valuetext`.

    O `%` de `style.width` é CSS (desenho, não leitura) e por isso não entra
    nesta varredura — o que entra é tudo que um olho ou um leitor de tela
    recebe como informação."""
    for i, d in enumerate(_cenario(card, "nada_de_percentual_em_lugar_nenhum")):
        assert "%" not in d["lido"], f"estado {i}"
        assert "%" not in (d["valuetext"] or ""), f"estado {i}"
        assert "%" not in (d["arialabel"] or ""), f"estado {i}"
        assert "%" not in d["titulo"], f"estado {i}"


def test_o_numero_de_maquina_nao_chega_na_interface(card):
    """Decisão 74 — `#` não aparece. `id`, `sequencia` e `aberta_por` são três
    numerações diferentes disputando a mesma notação, e "#12" numa malha diária
    lê-se como "12ª tentativa hoje", que é falso.

    A 2ª corrida do dia se chama "2º ciclo de 05/08"."""
    d = _cenario(card, "nada_de_numero_de_maquina")
    assert d["identidade"] == "2º ciclo de 05/08"
    for onde in ("lido", "titulo", "diagnostico"):
        assert "#" not in d[onde], onde
    # nome de máquina traduzido (Decisão 74): nada de `inicio:#12`
    assert "inicio:" not in d["titulo"]
    assert "o agendamento do Início" in d["titulo"]


# ═══════ 6. a barra: ordem fixa, o travado fora, o denominador inteiro ══════

def test_a_barra_responde_uma_coisa_so(card):
    """Ordem FIXA (`ok` · `vivo` · `dispensado`), só o vivo animado, e o travado
    FORA do comprimento.

    3 prontos + 1 rodando + 1 dispensado = 5 dos 7: os 2 travados não engordam
    a barra. Somá-los pintaria 5/7 e, a 1,5 m, leria-se "quase pronto" — em
    varredura de 40 cards o operador lê comprimento, não cor."""
    d = _cenario(card, "composicao_da_barra")
    assert d["chaves"] == ["ok", "vivo", "dispensado"]
    assert d["valores"] == [3, 1, 1]
    assert d["animados"] == [False, True, False]     # só o vivo (D75/#13)
    assert d["hachurados"] == [False, False, True]   # hachura = "não roda hoje"
    assert d["total"] == 7 and d["valor_atual"] == 3
    assert d["soma_dos_segmentos"] == 5              # os 2 travados ficam fora
    assert d["contagem"] == "3 de 7 pipelines concluídos"
    assert d["travados"] == "2 travados"
    assert d["culpado"] == "falhou: CARGA_A"


def test_sem_contadores_a_barra_some_e_o_estado_fica(card):
    """Lock timeout na apuração (`membros_total` nulo): sem barra e sem número.

    Publicar uma barra vazia seria mostrar zero como se fosse medida. O ESTADO
    do ciclo continua sendo dito — é o que mais importa quando o banco está ruim
    às 3h."""
    d = _cenario(card, "sem_contadores_nao_desenha_barra")
    assert d["barra"] is None
    assert d["contagem"] is None and d["membros"] is None
    assert d["rotulo"] == "em andamento"


# ═══════ 7. a pílula: um estado, três canais ════════════════════════════════

def test_cada_estado_tem_rotulo_e_icone_proprios(card):
    """Cor nunca é canal único (`SupervisaoCard.tsx:64-65`).

    Os três desfechos vermelhos e os dois âmbares têm de se distinguir por
    ícone e por texto — senão o gestor reporta "4 incidentes" quando três já
    acabaram e um ainda pode fechar verde."""
    d = _cenario(card, "pilula_por_estado")
    rotulos = {k: v["texto"] for k, v in d.items()}
    assert rotulos["ABERTA_OK"] == "em andamento"
    assert rotulos["ABERTA_COM_FALHA"] == "em andamento · com falha (ainda rodando)"
    assert rotulos["ABERTA_SEM_PROGRESSO"] == "em andamento · sem sinal há 40 min"
    assert rotulos["CONCLUIDA"] == "concluído"
    assert rotulos["EXPIRADA"] == "encerrado sem terminar"
    assert rotulos["ABORTADA"] == "não chegou a começar"
    assert rotulos["SEM_TRABALHO"] == "sem trabalho hoje"
    # ícones distintos entre os VERMELHOS
    vermelhos = {d[k]["icone"] for k in ("FALHA", "EXPIRADA", "ABORTADA")}
    assert len(vermelhos) == 3
    # animação semântica e escassa: só o ciclo ABERTO pulsa
    assert d["ABERTA_OK"]["animado"] is True
    assert d["CONCLUIDA"]["animado"] is False
    assert d["SEM_TRABALHO"]["animado"] is False


def test_sem_corrida_a_pilula_nao_renderiza(card):
    """Degradação por AUSÊNCIA (Decisão 41): a pílula não inventa um estado
    neutro. Quem escreve "(membro mais recente)" é o CHAMADOR, que é quem tem o
    dado antigo em mãos — e é lá que a palavra "concluída" continua proibida."""
    d = _cenario(card, "pilula_sem_dado_nao_renderiza")
    assert d["vazia"] is None
    assert d["vazia_com_esperada_nula"] is None


# ═══════ 8. o que mora no `MalhaCard`, provado no FONTE ═════════════════════
#
# O card inteiro só monta com react-query e o roteador — o que se prova aqui é
# o CONTRATO do fonte, como já faz `test_malhas_f4_front.py`. Cada asserção
# abaixo corresponde a um aceite que não tem outra superfície onde ser visto.

SRC = RAIZ / "ui-react" / "src"


def _codigo(caminho: Path) -> str:
    """O fonte SEM comentários. Estes arquivos explicam as regras em prosa:
    procurar `%` no texto inteiro acharia a frase que PROÍBE o `%`, e o teste
    provaria o contrário do que quer provar."""
    return "\n".join(
        ln for ln in caminho.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith(("//", "*", "/*", "{/*")))


def test_acompanhar_existe_sempre_e_as_posicoes_sao_fixas():
    """Decisão 72 — os dois defeitos de bancada.

    (i) O interruptor `malha_corrida_ativa` nasce em `0`: no dia do deploy
    nenhuma malha tem corrida, e um botão que só existisse com corrida deixaria
    a fase inteira NÃO TESTÁVEL. Por isso ele não é condicional — leva à lente
    de execução da data corrente, que já funciona hoje, e só ACRESCENTA a
    corrida quando ela existe.
    (ii) Botão que muda de lugar entre estados faz clicar em "Diagrama" no card
    1 e acertar "Membros" no card 2."""
    src = _codigo(SRC / "pages" / "Malha.tsx")
    # o botão não está dentro de nenhuma guarda de corrida
    assert "onClick={onAcompanhar}" in src
    assert "ciclo &&" not in src.split("onClick={onAcompanhar}")[0][-400:]
    # a lente vai com `modo=execucao`; a corrida entra só quando existe
    assert "modo: 'execucao', corrida: String(corrida)" in src
    assert "{ malha: n, modo: 'execucao' })" in src
    # ...e o editor sabe abrir nela (senão o parâmetro seria decoração)
    editor = _codigo(SRC / "components" / "malhas" / "MalhaEditor.tsx")
    assert "corridaInicial" in editor
    assert "useState<number | null>(corridaInicial)" in editor


def test_o_card_que_nao_abriu_ordena_primeiro():
    """Decisão 58 — a malha que não rodou é a que hoje não aparece em lugar
    nenhum; numa grade de 40 cards em ordem alfabética ela some no meio das que
    rodaram bem.

    E é a ÚNICA reordenação: ordenar por gravidade embaralharia a lista a cada
    refetch de 20 s, e um card que troca de lugar debaixo do cursor é um clique
    errado às 3h."""
    src = _codigo(SRC / "pages" / "Malha.tsx")
    assert "Number(!!b.corrida_esperada) - Number(!!a.corrida_esperada)" in src
    # Contador próprio na stats bar, e SÓ quando existe (uma pílula "0 não
    # abriram" todo dia treinaria o olho a passar por ela).
    #
    # F11 generalizou o contador: ele virou um dos cinco estados de corrida,
    # com a MESMA regra de só aparecer com número > 0 — e a regra passou a
    # valer para os cinco. O predicado do "não abriu" continua sendo a presença
    # de `corrida_esperada`, e é ele que a lista pergunta.
    assert "contagens[def.chave] > 0" in src
    estados = _codigo(SRC / "components" / "malhas" / "corridasDaLista.ts")
    assert "case 'nao_abriu':" in estados
    assert "return !!m.corrida_esperada" in estados


def test_api_anterior_a_fase_faz_o_card_DIZER_que_falta_informacao():
    """Aceite: front novo × API velha → "(membro mais recente)" **e** a linha
    "sem dados de ciclo — sistema em atualização".

    O `deploy.sh` publica o `dist/` na etapa 3 e a `api/` só na 7: nesse
    intervalo o front novo conversa com a API velha, que não manda `corrida`
    nem flag nenhuma. Sem um marcador POSITIVO de versão, o front concluiria
    "está tudo certo" e degradaria em silêncio — que é o oposto de degradar
    dizendo."""
    src = _codigo(SRC / "pages" / "Malha.tsx")
    assert "data.corrida_suportada !== true" in src
    assert "sem dados de ciclo — sistema em atualização" in src
    assert "(membro mais recente" in src
    # a degradação continua sendo decidida POR MALHA, pela ausência da chave
    assert "const corrida = malha.corrida ?? null" in src


def test_nenhum_percentual_e_nenhum_numero_de_maquina_no_fonte():
    """O aceite da fase escrito como ele aparece na spec: um `grep` pelos
    componentes de corrida não casa percentual EXIBIDO (Decisão 56) nem `#N` de
    interface (Decisão 74).

    O `%` legítimo do produto vive em `ui/Progress.tsx`, dentro de
    `style.width` — é CSS, não é o que se lê; por isso ele não entra nesta
    varredura, e a prova de que ele não vaza para o texto está nos testes de
    ausência acima, que varrem `aria-valuetext` e `title`."""
    import re
    malhas = SRC / "components" / "malhas"
    for arquivo in ("statusExecucao.ts", "CorridaBadge.tsx", "CorridaProgresso.tsx"):
        codigo = _codigo(malhas / arquivo)
        assert "%" not in codigo, arquivo
        assert not re.search(r"#\d", codigo), arquivo


def test_o_no_fim_tem_o_terceiro_estado_de_ciclo_aberto():
    """§9.3 — o nó Fim tinha DOIS estados (verde quando a malha concluiu, e
    apagado). "Apagado" descreve tanto "ninguém chegou aqui" quanto "o ciclo
    está aberto e ele está esperando", que são coisas diferentes.

    Anel azul e `title`, SEM texto no nó: o número já está na faixa a 3 cm
    (§9.15/#11), e o anel não entra na lista dos três animados (§9.15/#13)."""
    src = _codigo(SRC / "components" / "malhas" / "MalhaComponenteNodes.tsx")
    assert "e.cicloAberto ? ANEL.azul : ''" in src
    # sem animação no anel do Fim
    trecho = src.split("azul:")[1].split("\n")[0]
    assert "animate" not in trecho
    # e quem alimenta o estado é a CORRIDA, não um evento solto
    editor = _codigo(SRC / "components" / "malhas" / "MalhaEditor.tsx")
    assert "const cicloAberto = corrida?.status === 'ABERTA'" in editor
