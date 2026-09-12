"""
Timeout da prévia/simulação de SQL — `sql_preview_timeout_s` em
`dbo.etl_app_config` (F2 da spec docs/spec-email-tabela-sql-e-ajustes.md).

O valor de fábrica é o que vale na prática: até a F2 ele era 15s, e o campo que
o regula estava renderizado no rodapé da aba de NOTIFICAÇÕES, entre os canais do
Teams — quem precisava de mais tempo não achava onde mexer e a prévia seguia
sendo cancelada. A fase subiu o default para 60s, o teto para 280s e levou o
campo para Sistema › Configurações.

⚠️ O teto é 280 e não 300 de propósito: o nginx corta a resposta de
`/orquestra/` em 300s (`config/nginx.conf`), e empatar os dois faria quem
estoura o limite receber o erro do PROXY, sem a mensagem que explica o que
aconteceu e onde regular.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
for _p in (str(_ROOT / "api"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="module")
def J():
    from routers import jobs
    return jobs


def test_o_default_de_fabrica_e_60s(J):
    """Ambiente sem a chave gravada (o caso do DEV e o de produção até agora)."""
    assert J._PREVIEW_TIMEOUT_DEFAULT == 60


def test_o_teto_deixa_folga_para_o_corte_do_nginx_DO_REPO(J):
    """280 < 300 (proxy_read_timeout de /orquestra/ em config/nginx.conf).

    Se o teto empatasse com o corte do proxy, a consulta que estoura devolveria
    erro de gateway em vez da mensagem da API — o operador veria "502" onde
    deveria ler quanto tempo passou e onde aumentar.

    ⚠️ LIMITE DESTE TESTE: ele lê o nginx.conf DO REPO, e o de produção está à
    frente (o deploy pergunta se sincroniza `config/` e a resposta lá é "n").
    Portanto ele prende a coerência do repo e NADA afirma sobre o proxy real —
    conferir no servidor é item do smoke desta fase:
    `docker exec airflow-ui grep -A8 "location /orquestra/" /etc/nginx/nginx.conf`.
    Se lá o valor for menor que 280, o teto precisa descer junto."""
    assert J._PREVIEW_TIMEOUT_MAX == 280
    nginx = (_ROOT / "config/nginx.conf").read_text(encoding="utf-8")
    bloco = nginx[nginx.index("location /orquestra/"):]
    bloco = bloco[:bloco.index("}")]
    corte = int(bloco.split("proxy_read_timeout")[1].split("s;")[0].strip())
    assert J._PREVIEW_TIMEOUT_MAX < corte, (
        f"teto ({J._PREVIEW_TIMEOUT_MAX}s) precisa ficar abaixo do corte do nginx ({corte}s)")


@pytest.mark.parametrize("entrada,esperado", [
    (1, 1), (15, 15), (60, 60), (280, 280),
    (0, 1), (-30, 1),          # abaixo do piso
    (281, 280), (3600, 280),   # acima do teto
])
def test_clamp(J, entrada, esperado):
    assert J._clamp_preview_timeout(entrada) == esperado


def test_valor_gravado_fora_da_faixa_e_recortado_na_leitura(J, monkeypatch):
    """A chave pode ter sido gravada à mão pelo editor genérico de
    `etl_app_config`, que aceita qualquer texto — a leitura não pode confiar."""
    from routers import admin
    monkeypatch.setattr(admin, "_get_app_config_value", lambda _k: "9999")
    assert J._get_preview_timeout_s() == 280
    monkeypatch.setattr(admin, "_get_app_config_value", lambda _k: " 45 ")
    assert J._get_preview_timeout_s() == 45


def test_valor_ilegivel_cai_no_default_em_vez_de_derrubar_a_previa(J, monkeypatch):
    """Texto no lugar de número (de novo: o editor genérico aceita) não pode
    fazer a prévia falhar — ela degrada para o valor de fábrica."""
    from routers import admin
    monkeypatch.setattr(admin, "_get_app_config_value", lambda _k: "sessenta")
    assert J._get_preview_timeout_s() == 60
    monkeypatch.setattr(admin, "_get_app_config_value", lambda _k: None)
    assert J._get_preview_timeout_s() == 60


def test_tabela_indisponivel_tambem_degrada(J, monkeypatch):
    """Migration pendente / banco fora: a prévia continua rodando com 60s."""
    from routers import admin

    def _explode(_k):
        raise RuntimeError("etl_app_config não existe")

    monkeypatch.setattr(admin, "_get_app_config_value", _explode)
    assert J._get_preview_timeout_s() == 60


def test_a_mensagem_de_timeout_diz_onde_aumentar(J):
    """Sem isto o operador lê "refine o SELECT" e não descobre que o limite é
    configurável — foi exatamente o que aconteceu com o default de 15s.

    O texto é conferido RENDERIZADO, não procurado no código-fonte: um teste que
    só olhasse o .py continuaria verde se alguém tirasse o `f` do f-string e a
    mensagem passasse a exibir `{_PREVIEW_TIMEOUT_MAX}` cru para o operador."""
    msg = J._msg_timeout_previa(60, "na pré-visualização")
    assert "60s na pré-visualização" in msg
    assert "Admin › Sistema › Configurações › Configurações de fluxo" in msg
    assert "(até 280s)" in msg          # o teto real, interpolado
    assert "{" not in msg and "}" not in msg, "f-string quebrada: marcador cru na mensagem"


def test_a_simulacao_da_decisao_usa_a_mesma_mensagem(J):
    """A simulação estoura pelo mesmo limite e antes só dizia "refine o SELECT".
    O texto de ajuda da tela fala em "preview/simulação": as duas precisam
    ensinar o mesmo caminho."""
    msg = J._msg_timeout_previa(120, "na simulação")
    assert "120s na simulação" in msg
    assert "Admin › Sistema › Configurações" in msg


def test_o_timeout_de_conexao_nao_acompanha_o_de_execucao(J):
    """`pyodbc.connect(timeout=…)` é LOGIN; `conn.timeout` é execução.

    O wizard de Cópia de Dados passava o timeout de EXECUÇÃO no connect: com o
    teto novo, um host inalcançável penduraria a prévia por até 280s antes
    sequer de rodar SQL — e o nginx cortaria antes, devolvendo o 504 mudo que o
    teto existe para evitar."""
    assert J._CONNECT_TIMEOUT_S == 5
    assert J._CONNECT_TIMEOUT_S < J._PREVIEW_TIMEOUT_DEFAULT

    copias = (_ROOT / "api/routers/copias.py").read_text(encoding="utf-8")
    assert "abrir_conexao_nativa(conn_id, database, timeout_s)" not in copias
    assert "abrir_conexao_nativa(src_conn_id, src_database, timeout_s)" not in copias
    # e o limite de execução precisa continuar sendo aplicado em algum lugar
    assert copias.count("conn.timeout = timeout_s") == 3


def test_a_previa_nao_bloqueia_o_event_loop(J):
    """`sql_preview` e `decisao_simular` são `async def` — o FastAPI roda handler
    assim NO event loop, e `cur.execute` do pyodbc é chamada C bloqueante. Com
    2 workers uvicorn (api/Dockerfile), duas prévias longas parariam a API
    inteira, laços de fundo do lifespan inclusive. Enquanto o limite era 15s o
    estrago era pequeno; com 280s deixou de ser aceitável."""
    fonte = (_ROOT / "api/routers/jobs.py").read_text(encoding="utf-8")
    for nome in ("async def sql_preview", "async def decisao_simular"):
        corpo = fonte[fonte.index(nome):]
        corpo = corpo[:corpo.index("\n@router.") if "\n@router." in corpo else len(corpo)]
        assert "asyncio.to_thread" in corpo, f"{nome} voltou a executar SQL no event loop"


def test_a_previa_deixa_o_event_loop_livre_de_verdade(J, monkeypatch):
    """Prova funcional do `asyncio.to_thread`, complementando a trava textual.

    Uma consulta que leva 0,8s roda enquanto outra corrotina pulsa a cada 50ms.
    Com o `execute` no event loop (como era), os pulsos só aconteceriam DEPOIS
    da consulta — que é o que parava a API inteira: 2 workers uvicorn, dois
    SELECTs pesados, e ninguém mais consegue nem entrar no sistema."""
    import asyncio
    import time

    class _Cur:
        description = [("x",)]

        def execute(self, *_a):
            time.sleep(0.4)          # chamada C bloqueante, como a do pyodbc

        def fetchall(self):
            return [(1,)]

        def close(self):
            pass

    class _Conn:
        timeout = 0

        def cursor(self):
            return _Cur()

        def close(self):
            pass

    async def _abrir(*_a, **_k):
        return _Conn()

    monkeypatch.setattr(J, "_abrir_conexao_edicao", _abrir)
    monkeypatch.setattr(J, "_get_preview_timeout_s", lambda: 60)

    async def cenario():
        inicio = time.monotonic()
        pulsos = []

        async def pulsar():
            for _ in range(4):
                await asyncio.sleep(0.05)
                pulsos.append(time.monotonic() - inicio)

        resp, _ = await asyncio.gather(
            J.sql_preview(body={"host": "h", "database": "master", "sql": "SELECT 1"},
                          _auth={"matricula": "TESTE"}),
            pulsar(),
        )
        return resp, pulsos, time.monotonic() - inicio

    resp, pulsos, total = asyncio.run(cenario())
    assert resp["columns"] == ["x"] and resp["rows"] == [[1]]
    assert total >= 0.8, "a consulta simulada precisa mesmo levar o tempo dela"
    assert pulsos[-1] < 0.5, (
        f"o loop ficou preso: o último pulso só saiu em {pulsos[-1]:.2f}s, "
        "depois da consulta — o SQL voltou a rodar no event loop")
