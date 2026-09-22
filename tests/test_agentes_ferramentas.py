"""api/services/agentes_ferramentas.py — as ferramentas do agente DataStage
(F2 da spec docs/spec-agentes-datastage.md).

O que estes testes prendem, e por que cada um existe:

  1. **`redigir()` mascara o VALOR, não some com a linha** — o operador
     precisa continuar vendo QUE campo existe; só o conteúdo sensível some.
     Canário: senha/token/Encrypted nunca sobrevivem, mesmo com variações de
     maiúscula/minúscula e separador (`:`/`=`).

  2. **`resolver_projeto` nunca toca o servidor** — só a BASE e a lista de
     `.dsx` (nomes, não conteúdo). Nome com caixa diferente casa e devolve o
     CANÔNICO (DataStage é sensível a caixa); nome desconhecido devolve
     sugestões, nunca inventa.

  3. **`ferramenta_dsjob` só aceita os 5 comandos da allowlist** — nem
     `logsum`/`logdetail` (podem trazer valor de dado), nem comando livre.
     Isso é reforçado ANTES de abrir qualquer sessão SSH.

  4. **O semáforo tem espera LIMITADA e nomeada** (`ServidorOcupado`), nunca
     trava a rodada indefinidamente; o teto muda em runtime sem derrubar
     quem já está dentro.

Nada aqui toca SSH de verdade: `run_dsjob` é sempre um dublê.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes_ferramentas as af  # noqa: E402
from services.ssh_datastage import DsConsoleError  # noqa: E402


# ═══════════ 1. redigir ══════════════════════════════════════════════════════

@pytest.mark.parametrize("linha,escondido", [
    ("senha: minhaSenha123", "minhaSenha123"),
    ("Password=abc123!!", "abc123!!"),
    ("PWD:  segredo", "segredo"),
    ("api_key = sk-ant-xxxxx", "sk-ant-xxxxx"),
    ("Token: eyJhbGciOi...", "eyJhbGciOi..."),
    ("valor Encrypted: {iisenc}AbCdEf==", "{iisenc}AbCdEf=="),
])
def test_redigir_esconde_o_valor(linha, escondido):
    saida = af.redigir(linha)
    assert escondido not in saida
    assert af._MASCARA in saida


def test_redigir_preserva_o_nome_do_campo():
    saida = af.redigir("senha: segredo123")
    assert "senha" in saida.lower()


def test_redigir_nao_mexe_em_linha_sem_segredo():
    texto = "job_name: BiCvp_Extrai_Pedidos\nstatus: RUN OK"
    assert af.redigir(texto) == texto


def test_redigir_texto_vazio_nao_levanta():
    assert af.redigir("") == ""
    assert af.redigir(None) == ""


def test_redigir_multiplas_linhas():
    texto = "job: X\nsenha: abc\nstatus: ok\ntoken: xyz"
    saida = af.redigir(texto)
    assert "abc" not in saida and "xyz" not in saida
    assert "job: X" in saida and "status: ok" in saida


# Achado real da revisão adversarial da F2: o nome do campo entre aspas
# (formato JSON, como `-report`/`-lparams` às vezes devolvem) quebrava o
# casamento ANTES do separador — miss silencioso — e o valor entre aspas
# só tinha a pontuação mascarada (a aspas de abertura), deixando o segredo
# de verdade 100% visível atrás de uma máscara enganosa.
@pytest.mark.parametrize("texto,escondido", [
    ('{"password":"abc123"}', "abc123"),
    ('{"password": "abc 123 com espaço"}', "abc 123 com espaço"),
    ("{'token': 'xyz-999'}", "xyz-999"),
])
def test_redigir_campo_entre_aspas_json_esconde_o_valor(texto, escondido):
    saida = af.redigir(texto)
    assert escondido not in saida


def test_redigir_encrypted_com_aspas_mascara_o_valor_de_verdade():
    """Antes, `Encrypted": "` só mascarava a aspas de abertura do valor — o
    valor real (`{iisenc}AbCdEf==`) sobrevivia intacto depois da máscara."""
    saida = af.redigir('  "Encrypted": "{iisenc}AbCdEf=="')
    assert "AbCdEf" not in saida
    assert af._MASCARA in saida


# Achado real da 2ª rodada da revisão adversarial da F2: o valor entre aspas
# parava na primeira aspa LITERAL, mesmo quando ela vinha escapada (`\"`,
# exatamente o que `json.dumps()` produz quando o segredo contém uma aspa) —
# o restante do valor, depois da aspa escapada, sobrevivia atrás da máscara.
@pytest.mark.parametrize("texto,escondido", [
    (r'{"Encrypted": "sec\"ret123suffix"}', "ret123suffix"),
    (r'[{"ParamName":"DB_PASS","Encrypted":"P@ss\"word123"}]', "word123"),
    (r'{"password": "abc\"def456"}', "def456"),
])
def test_redigir_valor_com_aspa_escapada_nao_vaza_o_resto(texto, escondido):
    assert escondido not in af.redigir(texto)


# Achado real da 3ª rodada da revisão adversarial da F2: a tentativa anterior
# de reconhecer "a aspa que fecha o valor" (via `\\.` antes de `[^"\\\n]`)
# tratava uma barra invertida comum ANTES de uma aspa REAL de fechamento
# (ex.: path Windows `"C:\Temp\"`) como se fosse uma aspa escapada, e seguia
# procurando a PRÓXIMA aspa — que podia ser a abertura de um CAMPO SEGUINTE
# inteiro. O segundo segredo saía sem nenhuma máscara (pior que o defeito
# original, que só vazava o resto do MESMO valor).
#
# A 4ª rodada da revisão adversarial notou que um caso ingênuo (keyword do
# 2º campo entre aspas, ex. `"password": "anothersecret"`) não expõe o bug
# de verdade — a aspa de FECHAMENTO da keyword ainda sobra no texto restante
# e o próprio regex (que aceita a keyword com ou sem aspas ao redor) acaba
# reencontrando-a numa iteração seguinte do mesmo `.sub()`, mascarando por
# "sorte". O caso que realmente expõe o bug é a keyword do 2º campo SEM
# aspas ao redor (formato `chave: "valor"`, comum em relatório de texto) —
# aí ela é engolida por completo dentro do "roubo", sem chance de recaptura,
# e o segredo sobra em claro. Confirmado contra o regex do commit anterior
# (1730de6): `REALSECRETHERE` vazava por completo com esse texto.
def test_redigir_barra_antes_da_aspa_real_nao_vaza_o_campo_seguinte():
    texto = r'{"token": "C:\Temp\", secret: "REALSECRETHERE"}'
    saida = af.redigir(texto)
    assert "REALSECRETHERE" not in saida


# O valor real de um parâmetro `Encrypted` do DataStage tem a forma
# `{iisenc}<base64>` — a chave `}` é parte do CONTEÚDO, não um delimitador.
# Uma tentativa anterior de "parar no primeiro `,`/`}`/`]`" cortava o valor
# bem no meio (achado que eu mesmo encontrei ao testar a correção anterior).
def test_redigir_no_valor_encrypted_do_datastage_com_chave_no_meio():
    saida = af.redigir('  "Encrypted": "{iisenc}AbCdEf=="')
    assert "AbCdEf" not in saida


# Achado real da 4ª rodada da revisão adversarial da F2b: o MESMO problema
# de `\b` corrigido em `_RE_NOME_PARAMETRO_SENSIVEL` (achado da 3ª rodada)
# também afetava `_RE_SEGREDO`/`_RE_ENCRYPTED` — as regexes ORIGINAIS de
# `redigir()`, já em produção desde a F2 (PR #421). `_` é caractere de
# PALAVRA em regex, então `\btoken\b`/`\bpassword\b` nunca casavam num
# nome de campo SNAKE_CASE em TEXTO LIVRE — exatamente o formato da saída
# ao vivo do `dsjob` (`ferramenta_dsjob` redige o stdout com `redigir()`
# antes de ir ao modelo, `-lparams`/`-report` do D-07 ainda não confirmado
# quanto ao formato exato, mas `"AUTH_TOKEN": "..."` é plausível).
@pytest.mark.parametrize("texto,escondido", [
    ('"AUTH_TOKEN": "eyJhbGciOiJIUzI1NiJ9.PAYLOADSECRETO123"', "PAYLOADSECRETO123"),
    ("DB_PASSWORD=supersenha123", "supersenha123"),
    ("API_KEY_PROD: sk-ant-xxxxx", "sk-ant-xxxxx"),
])
def test_redigir_nome_de_campo_snake_case_em_texto_livre(texto, escondido):
    assert escondido not in af.redigir(texto)


def test_redigir_snake_case_preserva_o_prefixo_do_nome():
    """O delimitador reconhecido (o `_` antes da keyword) fica DENTRO do
    grupo capturado — não distorce a estrutura ao redor da máscara."""
    saida = af.redigir('"AUTH_TOKEN": "segredo123"')
    assert saida.startswith('"AUTH_TOKEN":')  # nome do campo continua legível


# Achado real da 5ª rodada da revisão adversarial da F2b: um quantificador
# SEM limite (`[A-Za-z0-9_-]*`) logo antes de um separador OBRIGATÓRIO
# (`[:=]` em `_RE_SEGREDO`) é backtracking catastrófico — quando não há
# `:`/`=` no resto da linha, o motor consome o sufixo até o fim, falha, e
# recua caractere a caractere: O(tamanho da linha) por TENTATIVA, repetido
# a cada ocorrência da keyword — O(n²) total. Medido: uma linha de 44 000
# caracteres levava ~5s; a saída REAL do `dsjob` pode chegar a 200 000
# caracteres (`run_dsjob`/`ssh_datastage.py` já trunca nesse teto) — o
# suficiente para travar o event loop de um worker da API por dezenas de
# segundos, já que `ferramenta_dsjob` chama `redigir()` de forma SÍNCRONA
# (ao contrário de `run_dsjob`, que roda em thread por este mesmo motivo).
# Corrigido limitando o sufixo a `{0,40}` (generoso para qualquer nome de
# parâmetro real) — mesmo padrão de `test_lineage_isx_engine.py::
# test_cdata_e_mainloop_nao_sao_quadraticos`.
def test_redigir_nao_e_quadratico_em_linha_longa_sem_separador():
    import time
    hostil = "AUTH_TOKEN_" * 20000  # ~220 000 chars, sem ':'/'=' nenhum
    t0 = time.perf_counter()
    af.redigir(hostil)
    assert time.perf_counter() - t0 < 2.0


def test_redigir_nao_e_quadratico_saida_real_de_dsjob_200k():
    """O teto exato que `run_dsjob` já trunca em produção
    (`ssh_datastage.py`, `out[:200000]`) — mesmo tamanho, pior caso
    plausível (muitas ocorrências de keyword, sem separador)."""
    import time
    hostil = ("token_" * 33334)[:200000]
    t0 = time.perf_counter()
    af.redigir(hostil)
    assert time.perf_counter() - t0 < 2.0


# Achado real da 6ª rodada da revisão adversarial da F2b: um nome de
# campo mais VERBOSO que a janela de busca do separador (plausível em
# nomenclatura de ETL — D-07, o formato real do `dsjob`, segue aberta)
# não pode fazer a redação FALHAR POR COMPLETO — o design da 7ª rodada
# (`_redigir_linha`/`_corte_apos_keyword`) sempre masca a partir da
# keyword quando não acha separador na janela, nunca deixa de mascarar.
def test_redigir_nome_de_campo_mais_longo_que_a_janela_nao_vaza():
    texto = "API_KEY_FOR_EXTERNAL_PAYMENT_GATEWAY_INTEGRATION: xyz123segredo"
    saida = af.redigir(texto)
    assert "xyz123segredo" not in saida
    assert af._MASCARA in saida


def test_redigir_nome_curto_preserva_formatacao():
    texto = "senha: abc123"
    assert af.redigir(texto) == "senha: ••••"


# Achado real da 7ª rodada da revisão adversarial da F2b: a "rede de
# segurança" da 6ª rodada testava `_MASCARA in linha` (a LINHA INTEIRA)
# como proxy de "já tratada" — errado quando a MESMA linha tem DOIS
# campos sensíveis (um de nome curto, tratado; outro de nome longo, não)
# ou quando o texto original já continha "••••" por acaso: a linha
# inteira era pulada, vazando por completo. O design da 7ª rodada não
# tem mais essa heurística — processa sempre a PRIMEIRA ocorrência da
# linha e masca a partir dali até o fim (cobrindo qualquer segredo
# seguinte na mesma linha, tratado ou não pela regra "bonita").
def test_redigir_dois_segredos_na_mesma_linha_nenhum_vaza():
    texto = ('{"API_KEY_FOR_EXTERNAL_PAYMENT_GATEWAY_INTEGRATION": '
            '"leak1_segredo_real", "token": "leak2"}')
    saida = af.redigir(texto)
    assert "leak1_segredo_real" not in saida
    assert "leak2" not in saida


def test_redigir_mascara_preexistente_no_texto_nao_esconde_segredo_real():
    texto = ('log_marker: "••••" (progress) — '
            "API_KEY_FOR_EXTERNAL_PAYMENT_GATEWAY_INTEGRATION=leak3_real")
    saida = af.redigir(texto)
    assert "leak3_real" not in saida


# ═══════════ 2. truncagem ═════════════════════════════════════════════════════

def test_truncar_texto_curto_nao_muda():
    assert af._truncar("abc", limite=100) == "abc"


def test_truncar_texto_longo_avisa():
    texto = "x" * 10000
    saida = af._truncar(texto, limite=100)
    assert len(saida) < len(texto)
    assert "truncada" in saida


# ═══════════ 3. resolver_projeto — nunca toca o servidor ════════════════════

class _CurProjetos:
    def __init__(self, pipelines=(), isx=()):
        self.pipelines = pipelines
        self.isx = isx

    def execute(self, sql, params=None):
        s = sql.lower()
        if "distinct project_name from dbo.etl_pipeline" in s:
            self._rows = [(p,) for p in self.pipelines]
        elif "distinct ds_project from dbo.etl_ds_job_isx" in s:
            self._rows = [(p,) for p in self.isx]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


def test_resolver_projeto_nome_exato_resolve():
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, "BI_CVP")
    assert r == {"estado": "resolvido", "projeto": "BI_CVP", "sugerido": None,
                 "tem_dsx": False, "sugestoes": []}


def test_resolver_projeto_caixa_diferente_e_so_sugestao_nao_resolve_sozinho():
    """Critério 11 da F2: nome só diferente na caixa NUNCA resolve sozinho —
    só sugere, e quem confirma é o usuário (via o modelo, numa 2ª chamada)."""
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, "bi_cvp")
    assert r["estado"] == "quase"
    assert r["projeto"] is None  # NÃO resolvido ainda
    assert r["sugerido"] == "BI_CVP"  # a grafia CADASTRADA, para o modelo confirmar


def test_resolver_projeto_confirmado_com_a_grafia_exata_resolve():
    """A 2ª chamada, já com o nome exato sugerido, resolve — é assim que a
    'confirmação' do critério 11 se fecha, sem protocolo especial."""
    cur = _CurProjetos(pipelines=["BI_CVP"])
    quase = af.resolver_projeto(cur, "bi_cvp")
    confirmado = af.resolver_projeto(cur, quase["sugerido"])
    assert confirmado["estado"] == "resolvido" and confirmado["projeto"] == "BI_CVP"


def test_resolver_projeto_desconhecido_da_sugestoes_sem_inventar():
    cur = _CurProjetos(pipelines=["BI_CVP", "BI_VIDA"])
    r = af.resolver_projeto(cur, "NAO_EXISTE")
    assert r["estado"] == "desconhecido"
    assert r["projeto"] is None
    assert set(r["sugestoes"]) == {"BI_CVP", "BI_VIDA"}


def test_resolver_projeto_nome_vazio_e_desconhecido():
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, "")
    assert r["estado"] == "desconhecido"
    assert r["projeto"] is None


def test_resolver_projeto_nao_toca_o_servidor_datastage(monkeypatch):
    """Nenhuma chamada de rede/SSH — só banco e a lista LOCAL de .dsx."""
    def _explode(*a, **k):
        raise AssertionError("resolver_projeto não deveria tocar o servidor")
    monkeypatch.setattr(af, "run_dsjob", _explode)
    cur = _CurProjetos(pipelines=["BI_CVP"])
    af.resolver_projeto(cur, "BI_CVP")
    af.resolver_projeto(cur, "desconhecido")  # não levanta


def test_resolver_projeto_usa_isx_quando_pipeline_nao_tem():
    cur = _CurProjetos(pipelines=[], isx=["DM_CONTRATOS_CVP"])
    r = af.resolver_projeto(cur, "DM_CONTRATOS_CVP")
    assert r["estado"] == "resolvido" and r["projeto"] == "DM_CONTRATOS_CVP"


def test_resolver_projeto_degrada_se_o_banco_falhar():
    class _Explode:
        def execute(self, *a, **k):
            raise Exception("tabela ausente")

        def fetchall(self):
            return []
    r = af.resolver_projeto(_Explode(), "qualquer")
    assert r["estado"] == "desconhecido"


def test_projeto_do_pipeline_job_usa_lineage_isx(monkeypatch):
    from services import lineage_isx
    monkeypatch.setattr(lineage_isx, "job_do_pipeline",
                        lambda cur, pipeline, job: {"ds_project": "BI_CVP"} if pipeline == "PIPE_VIDA" else None)
    assert af.projeto_do_pipeline_job(None, "PIPE_VIDA", "JobRaiz") == "BI_CVP"
    assert af.projeto_do_pipeline_job(None, "OUTRO", "JobRaiz") is None


def test_resolver_projeto_via_pipeline_job_resolve_sem_perguntar(monkeypatch):
    """Critério 10 da F2: citar um pipeline/job do Orquestra resolve direto
    — nunca cai em 'quase' por causa da caixa (a grafia já vem da base)."""
    from services import lineage_isx
    monkeypatch.setattr(lineage_isx, "job_do_pipeline",
                        lambda cur, pipeline, job: {"ds_project": "BI_CVP"} if pipeline == "PIPE_VIDA" else None)
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, pipeline_name="PIPE_VIDA", job_name="JobRaiz")
    assert r == {"estado": "resolvido", "projeto": "BI_CVP", "sugerido": None,
                 "tem_dsx": False, "sugestoes": []}


def test_resolver_projeto_pipeline_job_desconhecido_nao_inventa(monkeypatch):
    from services import lineage_isx
    monkeypatch.setattr(lineage_isx, "job_do_pipeline", lambda cur, pipeline, job: None)
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, pipeline_name="NAO_EXISTE", job_name="JobX")
    assert r["estado"] == "desconhecido"


# ═══════════ 4. ferramenta_base ═══════════════════════════════════════════════

class _CurBase:
    def __init__(self, linha=None, stages=0):
        self.linha = linha
        self.stages = stages

    def execute(self, sql, params=None):
        s = sql.lower()
        if "from dbo.etl_ds_job_isx" in s:
            self._rows = [self.linha] if self.linha else []
        elif "count(*) from dbo.etl_job_lineage" in s:
            self._rows = [(self.stages,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_ferramenta_base_encontrado():
    linha = ("PIPE_VIDA", "JobRaiz", "\\Jobs\\Cat", "PARALLEL", "2026-09-01T10:00:00",
             "descricao", "[]", "[]", "ok", None, "2026-09-10 10:00:00")
    cur = _CurBase(linha=linha, stages=5)
    r = af.ferramenta_base(cur, "BI_CVP", "JobRaiz")
    assert r["encontrado"] is True
    assert r["pipeline_name"] == "PIPE_VIDA" and r["stages"] == 5


def test_ferramenta_base_nao_encontrado():
    cur = _CurBase(linha=None)
    r = af.ferramenta_base(cur, "BI_CVP", "JobFantasma")
    assert r == {"encontrado": False}


# Achado real da 2ª rodada da revisão adversarial da F2b: `parameters_json`/
# `flow_json` são gravados como um `json.dumps(...)` COMPACTO (uma linha só)
# por `lineage_isx._js()` — se `ferramenta_base` devolvesse essas colunas
# CRUAS (como string), `redigir_estrutura()` (que só desce em dict/list)
# trataria o blob inteiro como UMA folha só, reproduzindo o over-masking
# "até o fim da linha" exatamente onde moram os parâmetros `Encrypted`.
# `ferramenta_base` agora DESSERIALIZA essas colunas antes de devolver.
def test_ferramenta_base_desserializa_parameters_e_flow_json():
    import json
    parametros = [
        {"name": "DB_PASSWORD", "type": "Encrypted", "default": "{iisenc}AbCdEf==", "description": "senha"},
        {"name": "DB_HOST", "type": "string", "default": "oracle-prod01.empresa.local", "description": "host"},
    ]
    linha = ("PIPE_VENDAS", "JobCarga", "\\Jobs\\Cat", "PARALLEL", "2026-09-01T10:00:00",
             "descricao", json.dumps(parametros, ensure_ascii=False), "[]", "ok", None, "2026-09-10 10:00:00")
    r = af.ferramenta_base(_CurBase(linha=linha, stages=1), "BI_CVP", "JobCarga")
    # já veio desserializado — não é mais uma string JSON crua
    assert isinstance(r["parameters_json"], list)
    assert r["parameters_json"][1]["name"] == "DB_HOST"

    # e, combinado com redigir_estrutura(), o dado útil sobrevive ao lado do segredo
    texto = json.dumps(af.redigir_estrutura(r), ensure_ascii=False, default=str)
    assert "DB_HOST" in texto and "oracle-prod01.empresa.local" in texto
    assert "AbCdEf==" not in texto


# Achado real da 3ª rodada da revisão adversarial da F2b: `\b` NÃO é
# delimitador de palavra suficiente para nome de variável — `_` é
# caractere de PALAVRA em regex (`\w` inclui `_`), então `\btoken\b` não
# casava "TOKEN" dentro de "AUTH_TOKEN". SNAKE_CASE é o padrão dominante
# de nome de parâmetro em ETL (`AUTH_TOKEN`, `API_KEY_PROD`,
# `DB_PASSWORD`...) — um parâmetro de token/API key tipado `String` (não
# `Encrypted`) vazava o `default` sem máscara nenhuma, porque só o
# CAMINHO por `type == "Encrypted"` funcionava de verdade.
@pytest.mark.parametrize("nome", ["AUTH_TOKEN", "API_KEY_PROD", "MY_API_KEY", "DB_PASSWORD", "DB-PASSWORD"])
def test_parece_parametro_sensivel_reconhece_nome_snake_case(nome):
    assert af._parece_parametro_sensivel({"name": nome, "type": "String", "default": "x"}) is True


@pytest.mark.parametrize("nome", ["PIPELINE_NAME", "JOB_TYPE", "ds_project", "STAGE_NAME"])
def test_parece_parametro_sensivel_nao_gera_falso_positivo(nome):
    assert af._parece_parametro_sensivel({"name": nome, "type": "String", "default": "x"}) is False


def test_ferramenta_base_token_snake_case_tipado_string_nao_vaza():
    """Reprodução ponta a ponta do achado: parâmetro de token, tipado
    `String` (não `Encrypted` — plausível, nem todo parâmetro de
    credencial é tipado Encrypted no DataStage), com nome SNAKE_CASE."""
    import json
    parametros = [{"name": "AUTH_TOKEN", "type": "String",
                  "default": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.SECRETPAYLOAD",
                  "description": "token usado na chamada REST"}]
    linha = ("PIPE_API", "JobChamaApi", "\\Jobs\\Cat", "PARALLEL", "2026-09-01T10:00:00",
             "descricao", json.dumps(parametros, ensure_ascii=False), "[]", "ok", None, "2026-09-10 10:00:00")
    r = af.ferramenta_base(_CurBase(linha=linha, stages=1), "BI_CVP", "JobChamaApi")
    texto = json.dumps(af.redigir_estrutura(r), ensure_ascii=False, default=str)
    assert "SECRETPAYLOAD" not in texto
    assert "AUTH_TOKEN" in texto  # nome do parâmetro continua visível


def test_ferramenta_base_traz_idade_ja_calculada():
    """Critério 3 da F2: a resposta já informa a idade — o modelo não
    precisa calcular a partir de uma data crua."""
    import datetime as _dt
    ha_10_dias = (_dt.datetime.now() - _dt.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
    linha = ("PIPE_VIDA", "JobRaiz", "\\Jobs\\Cat", "PARALLEL", ha_10_dias,
             "descricao", "[]", "[]", "ok", None, "2026-09-10 10:00:00")
    r = af.ferramenta_base(_CurBase(linha=linha, stages=1), "BI_CVP", "JobRaiz")
    assert r["idade_dias"] in (9, 10, 11)  # tolerância de fuso/arredondamento


def test_ferramenta_base_data_ausente_idade_none():
    linha = ("PIPE_VIDA", "JobRaiz", "\\Jobs\\Cat", "PARALLEL", None,
             "descricao", "[]", "[]", "ok", None, "2026-09-10 10:00:00")
    r = af.ferramenta_base(_CurBase(linha=linha, stages=1), "BI_CVP", "JobRaiz")
    assert r["idade_dias"] is None


@pytest.mark.parametrize("bruto", ["não é uma data", "", "31/02/2026"])
def test_idade_dias_formato_inesperado_nao_levanta(bruto):
    assert af._idade_dias(bruto) is None


# ═══════════ 5. ferramenta_dsjob — allowlist e semáforo ═════════════════════

@pytest.mark.asyncio
async def test_dsjob_fora_da_allowlist_nunca_abre_ssh(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("run_dsjob não deveria ter sido chamado")
    monkeypatch.setattr(af, "run_dsjob", _explode)
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    for comando in ("logsum", "logdetail", "importar", "; rm -rf /"):
        with pytest.raises(DsConsoleError):
            await af.ferramenta_dsjob(comando, "BI_CVP", "Job", teto_sessoes=10, espera_max_s=1)


@pytest.mark.asyncio
async def test_dsjob_sem_ssh_configurado_e_dsconsoleerror(monkeypatch):
    monkeypatch.setattr(af, "ssh_configured", lambda: False)
    with pytest.raises(DsConsoleError):
        await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=10, espera_max_s=1)


@pytest.mark.asyncio
async def test_dsjob_comando_permitido_chama_run_dsjob_e_redige(monkeypatch):
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    chamadas = []

    def _fake(comando, projeto, job=None):
        chamadas.append((comando, projeto, job))
        return {"exit_code": 0, "stdout": "senha: abc123\njob_name: X", "stderr": "", "duration_ms": 50}
    monkeypatch.setattr(af, "run_dsjob", _fake)
    r = await af.ferramenta_dsjob("lparams", "BI_CVP", "JobX", teto_sessoes=10, espera_max_s=5)
    assert chamadas == [("lparams", "BI_CVP", "JobX")]
    assert "abc123" not in r["saida_redigida"]
    assert "job_name: X" in r["saida_redigida"]


@pytest.mark.asyncio
async def test_semaforo_limita_concorrencia_e_espera_estoura(monkeypatch):
    """Com teto 1, a 2ª chamada simultânea espera; se o servidor 'nunca
    solta', a espera estoura como ServidorOcupado nomeado (não um timeout
    genérico)."""
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    liberar = asyncio.Event()

    def _lento(comando, projeto, job=None):
        # roda em thread (asyncio.to_thread) — bloqueia até liberar() ser
        # setado no loop principal.
        import time as _t
        while not liberar.is_set():
            _t.sleep(0.01)
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1}
    monkeypatch.setattr(af, "run_dsjob", _lento)
    af.SEMAFORO_SSH = af.SemaforoSsh()  # semáforo limpo para este teste

    tarefa1 = asyncio.create_task(
        af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=5))
    await asyncio.sleep(0.05)  # garante que a 1ª já pegou o semáforo

    with pytest.raises(af.ServidorOcupado):
        await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=0.2)

    liberar.set()
    r1 = await tarefa1
    assert r1["exit_code"] == 0


@pytest.mark.asyncio
async def test_semaforo_libera_para_o_proximo_apos_terminar(monkeypatch):
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    monkeypatch.setattr(af, "run_dsjob",
                        lambda c, p, j=None: {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1})
    af.SEMAFORO_SSH = af.SemaforoSsh()
    r1 = await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=2)
    r2 = await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=2)
    assert r1["exit_code"] == 0 and r2["exit_code"] == 0


@pytest.mark.asyncio
async def test_cancelar_enquanto_na_fila_do_semaforo_nao_deixa_fantasma_rodando(monkeypatch):
    """Achado moderado da 3ª rodada da revisão adversarial da F2: só a fase
    'vaga obtida → trabalho → libera' de `ferramenta_dsjob` é protegida
    contra cancelamento externo (via `asyncio.shield`) — a fase de FILA
    (ainda sem vaga) precisa continuar cancelável DE VERDADE. Sem isso, uma
    tentativa "fantasma" (de uma pergunta cujo orçamento já estourou)
    continuaria tentando a vaga em segundo plano e chegaria a RODAR
    `run_dsjob` assim que a vaga abrisse — mesmo sem ninguém mais precisar
    do resultado. Prova pelo efeito observável (quantas vezes `run_dsjob`
    roda), não só pelo tempo de retorno de `.cancel()` — `asyncio.shield`
    sempre deixa quem CHAMOU `.cancel()` desistir rápido, isso sozinho não
    prova que não sobrou um fantasma rodando por trás."""
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    liberar1 = asyncio.Event()
    chamadas: list[str] = []

    def _run(comando, projeto, job=None):
        import time as _t
        chamadas.append(comando)
        if len(chamadas) == 1:  # só a 1ª chamada (tarefa1) bloqueia de propósito
            while not liberar1.is_set():
                _t.sleep(0.01)
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1}
    monkeypatch.setattr(af, "run_dsjob", _run)
    af.SEMAFORO_SSH = af.SemaforoSsh()

    tarefa1 = asyncio.create_task(
        af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=5))
    await asyncio.sleep(0.05)  # garante que a 1ª já pegou a vaga e está "trabalhando"

    tarefa2 = asyncio.create_task(
        af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=10))
    await asyncio.sleep(0.05)  # garante que a 2ª já está esperando na fila (sem vaga)

    tarefa2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarefa2

    liberar1.set()  # libera a tarefa1 — a vaga fica disponível de novo
    r1 = await tarefa1
    assert r1["exit_code"] == 0

    await asyncio.sleep(0.3)  # dá chance a um eventual "fantasma" da tarefa2 rodar
    assert chamadas == ["ljobs"]  # só a tarefa1 — o fantasma da tarefa2 nunca chegou a rodar
