"""
etl_servicenow_sync.py

Espelha os chamados do(s) grupo(s) da engenharia do ServiceNow no SQL Server
(docs/spec-chamados-servicenow.md, F1/F2). A cada 15 min, uma task só.

⚠️ **A cadência tem um par**: `FRESCOR_ALERTA_MINUTOS` em `api/routers/chamados.py`
é quantos minutos de silêncio acendem o âmbar na tela, e só faz sentido em
função deste cron (hoje ~4 ciclos). Mudar um sem o outro deixa o alerta surdo
(cadência curta + limiar longo) ou histérico (cadência longa + limiar curto).
`tests/test_servicenow_cadencia.py` prende os dois.

Desenho, e o porquê de cada escolha:

  1. **A credencial vem da config, não de Airflow Connection nem de env.** É a
     credencial EXECUTORA salva em Admin > ServiceNow (`servicenow_*` em
     etl_app_config, senha em Fernet/ORQUESTRA_CONN_KEY). Um lugar só, com
     RBAC e auditoria de quem mudou.

  2. **Cada tabela sincroniza independente.** ACL do ServiceNow é por tabela:
     403 em `change_request` e 200 em `incident` é cenário real (risco #2 da
     spec). Falha numa NÃO derruba as outras — o log nomeia a tabela negada e
     as demais entram no espelho.

  3. **Desativa o que sumiu da fila, sem apagar.** Chamado que saiu do grupo
     (reatribuído) vira ativo=0 em vez de DELETE: os indicadores de
     entradas × saídas (F5) precisam do histórico. A desativação só alcança
     os tipos que sincronizaram COM SUCESSO neste ciclo — senão uma tabela
     negada por ACL zeraria a fila daquele tipo com cara de "tudo resolvido".

  4. **O ciclo é sempre registrado em etl_chamado_sync**, inclusive quando dá
     erro. É a fonte do carimbo de frescor da tela e o que separa "fila
     realmente vazia" de "grupo errado/credencial negada" — as duas mostram
     zero chamados, e só o log diz qual é (risco #4 da spec).

  5. **Interruptor `servicenow_habilitado`**: em 0, o ciclo não chama nada,
     não grava espelho e sai dizendo por quê. Sem isto, uma instalação sem
     credencial acumularia falha vermelha a cada ciclo.

⚠️ Placeholder `%s` (pymssql) — esta é a árvore `dags/`. A `api/` usa `?`.
"""
from __future__ import annotations

import datetime as _dt
import os

import pendulum
from airflow.decorators import dag, task
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from utils.frescor_modulo import conferir
from utils.servicenow_sync import (
    CAMPOS, MAX_PAGINAS, MSSQL_CONN_ID, PAGINA, TABELAS,
    normalizar, proxy_da_config, query_do_grupo, upsert_params, upsert_sql,
)

# Chaves da config (espelham api/services/servicenow.py — a fonte é a mesma
# tabela; duplicar o literal aqui evita a árvore dags/ importar de api/).
K_URL, K_USUARIO = "servicenow_url", "servicenow_usuario"
K_SENHA, K_GRUPOS = "servicenow_senha_enc", "servicenow_grupos"
K_HABILITADO = "servicenow_habilitado"

TIMEOUT_HTTP = 30


def _ler_config(hook) -> dict:
    linhas = hook.get_records(
        "SELECT config_key, config_value FROM dbo.etl_app_config "
        "WHERE config_key LIKE 'servicenow%'")
    return {k: (v or "").strip() for k, v in (linhas or [])}


def _decifrar(token: str) -> str:
    """Mesma chave e mesmo cofre das conexões (utils/conn_resolver)."""
    from cryptography.fernet import Fernet
    chave = (os.getenv("ORQUESTRA_CONN_KEY") or "").strip()
    if not chave:
        raise ValueError(
            "ORQUESTRA_CONN_KEY não configurada no worker — defina no .env/"
            "compose o MESMO valor usado pelo orquestra-api")
    return Fernet(chave.encode()).decrypt(token.encode("ascii")).decode("utf-8")


def _buscar_tabela(cliente, url: str, tabela: str, query: str) -> list[dict]:
    """Todas as páginas de uma tabela. Erro sobe para quem chama tratar por
    tabela — o ciclo não morre porque uma delas foi negada."""
    registros: list[dict] = []
    for pagina in range(MAX_PAGINAS):
        resposta = cliente.get(
            f"{url}/api/now/table/{tabela}",
            params={"sysparm_query": query, "sysparm_fields": CAMPOS,
                    "sysparm_display_value": "all",
                    "sysparm_limit": PAGINA,
                    "sysparm_offset": pagina * PAGINA})
        if resposta.status_code != 200:
            raise RuntimeError(f"HTTP {resposta.status_code}")
        lote = (resposta.json() or {}).get("result") or []
        registros.extend(lote)
        if len(lote) < PAGINA:
            return registros
    print(f"[SN] AVISO: {tabela} atingiu o teto de {MAX_PAGINAS} páginas — "
          f"o espelho pode estar incompleto para este tipo.")
    return registros


@dag(
    dag_id="etl_servicenow_sync",
    description="Espelha os chamados do ServiceNow do grupo da engenharia",
    # 15 min durante a equalização da fila (era 3h). Ao voltar a afrouxar,
    # mexa TAMBÉM em FRESCOR_ALERTA_MINUTOS (api/routers/chamados.py) e nos
    # dois valores abaixo — o teste de cadência recusa a combinação incoerente.
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    # Teto e retry cabem DENTRO do intervalo: com max_active_runs=1, uma run
    # que atravessasse o próximo slot empurraria a fila para sempre. Pior
    # caso = 1ª tentativa + 2 min de espera + 2ª tentativa, e o teto corta em
    # 10 min de qualquer jeito.
    dagrun_timeout=_dt.timedelta(minutes=10),
    tags=["servicenow", "chamados", "sistema"],
    default_args={"owner": "orquestra", "retries": 1,
                  "retry_delay": _dt.timedelta(minutes=2)},
)
def etl_servicenow_sync():

    @task
    def ciclo(**contexto) -> dict:
        import httpx

        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        cfg = _ler_config(hook)
        disparado_por = (contexto.get("params") or {}).get("disparado_por") or "schedule"

        if cfg.get(K_HABILITADO) != "1":
            print("[SN] Sync desabilitado (servicenow_habilitado=0) — "
                  "nada a fazer. Ligue em Admin > ServiceNow.")
            return {"status": "DESABILITADO"}

        url = (cfg.get(K_URL) or "").rstrip("/")
        usuario, senha_enc = cfg.get(K_USUARIO), cfg.get(K_SENHA)
        grupos = [g.strip() for g in (cfg.get(K_GRUPOS) or "").split(";") if g.strip()]

        inicio = _dt.datetime.now()
        # O ciclo é registrado ANTES de qualquer chamada: se o worker morrer no
        # meio, a linha fica lá com terminado_em nulo — visível como ciclo que
        # não fechou, em vez de sumir da história (lição do factory_log órfão).
        hook.run("INSERT INTO dbo.etl_chamado_sync (iniciado_em, status, disparado_por) "
                 "VALUES (%s, 'ERRO', %s)", parameters=(inicio, disparado_por))
        id_ciclo = hook.get_first(
            "SELECT MAX(id) FROM dbo.etl_chamado_sync WHERE iniciado_em = %s "
            "AND disparado_por = %s", parameters=(inicio, disparado_por))[0]

        def _fechar(status: str, contagens: dict, desativados, erro=None):
            hook.run(
                "UPDATE dbo.etl_chamado_sync SET terminado_em=GETDATE(), status=%s, "
                "qtd_incident=%s, qtd_ritm=%s, qtd_task=%s, qtd_change=%s, "
                "qtd_desativados=%s, erro=%s WHERE id=%s",
                parameters=(status, contagens.get("incident"), contagens.get("ritm"),
                            contagens.get("task"), contagens.get("change"),
                            desativados, (erro or "")[:1000], id_ciclo))

        try:
            if not (url and usuario and senha_enc):
                raise ValueError("ServiceNow não configurado — informe URL, "
                                 "usuário e senha em Admin > ServiceNow.")
            if not grupos:
                raise ValueError("Nenhum grupo de atribuição configurado — sem "
                                 "filtro o sync traria a fila da empresa inteira.")
            senha = _decifrar(senha_enc)
            query = query_do_grupo(grupos)
        except Exception as e:
            print(f"[SN] ERRO de configuração: {e}")
            _fechar("ERRO", {}, None, str(e))
            raise

        contagens: dict = {}
        erros: list[str] = []
        tipos_ok: list[str] = []

        # ── O worker está mesmo rodando o código que foi deployado? ─────────
        # Este arquivo (DAG na raiz de dags/) é reprocessado a cada execução,
        # mas os módulos de utils/ vêm do cache em memória do worker Celery.
        # A conferência entra em `erros` de propósito: assim o ciclo fecha com
        # status ERRO e a MENSAGEM APARECE NA TELA, em vez de morrer num log
        # que ninguém abre. O sync continua — dado velho gravado é melhor que
        # nenhum —, mas para de se dizer saudável.
        for aviso in conferir():
            print(aviso)
            erros.append(aviso)
        # Rota de saída. Ver proxy_da_config() para o porquê de vir da
        # config e não de variável de ambiente do worker.
        proxy = proxy_da_config(cfg)
        print(f"[SN] Saída: {'via proxy ' + proxy if proxy else 'conexão direta'}")
        # ⚠️ `proxy=` (singular). O worker roda httpx 0.28+, onde `proxies=` já
        # não existe — a `api/` roda 0.27 e aceita os dois. Duas árvores, duas
        # versões: o que compila lá não necessariamente importa aqui.
        # A CONSTRUÇÃO do cliente também pode falhar (proxy malformado, por
        # exemplo) — e falhar aqui, sem fechar o ciclo, deixaria a linha órfã
        # em "em andamento" para sempre.
        try:
            _cliente = httpx.Client(auth=(usuario, senha), timeout=TIMEOUT_HTTP,
                                    proxy=proxy,
                                    headers={"Accept": "application/json"})
        except Exception as e:
            _fechar("ERRO", contagens, None, f"cliente HTTP: {type(e).__name__} {e}")
            raise
        with _cliente as cliente:
            for tabela, tipo in TABELAS:
                try:
                    registros = _buscar_tabela(cliente, url, tabela, query)
                except Exception as e:
                    # ACL por tabela é cenário real: 403 aqui, 200 ali.
                    erros.append(f"{tabela}: {type(e).__name__} {e}")
                    contagens[tipo] = None
                    print(f"[SN] {tabela}: FALHOU — {e}")
                    continue
                try:
                    for cru in registros:
                        linha = normalizar(cru, tabela, tipo, url)
                        if not linha["sys_id"]:
                            continue  # registro sem chave natural: ignorado
                        hook.run(upsert_sql(), parameters=upsert_params(linha))
                except Exception as e:
                    # A GRAVAÇÃO falha por motivos diferentes da busca, e o mais
                    # provável deles é coluna que ainda não existe: as migrations
                    # (etapa 6c) e o deploy de dags/ (etapa 5) são passos
                    # SEPARADOS, e nada obriga a ordem entre eles. Sem este
                    # tratamento a exceção escapa da task e a linha do ciclo fica
                    # com terminado_em NULL para sempre — a tela lê "em
                    # andamento" e nunca aprende a causa (o factory_log órfão da
                    # PR #234, de novo).
                    erros.append(f"{tabela} (gravação): {type(e).__name__} {e}")
                    contagens[tipo] = None
                    print(f"[SN] {tabela}: FALHOU ao gravar — {e}")
                    continue
                contagens[tipo] = len(registros)
                tipos_ok.append(tipo)
                print(f"[SN] {tabela}: {len(registros)} chamado(s) espelhado(s)")

        # Desativa o que sumiu da fila — SÓ nos tipos que sincronizaram bem.
        # Sem esse recorte, uma tabela negada por ACL zeraria a fila daquele
        # tipo e a tela mostraria "tudo resolvido" (falso verde do risco #4).
        desativados = 0
        if tipos_ok:
            try:
                marcadores = ",".join(["%s"] * len(tipos_ok))
                hook.run(
                    f"UPDATE dbo.etl_chamado SET ativo=0 "
                    f"WHERE ativo=1 AND tipo IN ({marcadores}) AND sync_em < %s",
                    parameters=(*tipos_ok, inicio))
                linha = hook.get_first(
                    f"SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo=0 AND "
                    f"tipo IN ({marcadores}) AND sync_em < %s",
                    parameters=(*tipos_ok, inicio))
                desativados = (linha or [0])[0]
            except Exception as e:
                # Falhar aqui não pode apagar o trabalho já gravado nem deixar
                # o ciclo sem fechar: vira erro registrado, e o espelho fica
                # com fila possivelmente desatualizada — dito, não escondido.
                erros.append(f"desativação: {type(e).__name__} {e}")
                print(f"[SN] Desativação FALHOU — {e}")

        total = sum(v for v in contagens.values() if v is not None)
        if erros and not tipos_ok:
            _fechar("ERRO", contagens, desativados, " | ".join(erros))
            raise RuntimeError(f"Nenhuma tabela sincronizou: {' | '.join(erros)}")
        # Parcial conta como ERRO no log (o operador precisa ver), mas a task
        # NÃO falha: o espelho recebeu dado bom e a tela deve servi-lo.
        _fechar("ERRO" if erros else "OK", contagens, desativados,
                " | ".join(erros) if erros else None)
        print(f"[SN] Ciclo concluído: {total} chamado(s), "
              f"{desativados} fora da fila, {len(erros)} tabela(s) com erro.")
        return {"status": "PARCIAL" if erros else "OK", "total": total,
                "contagens": contagens, "desativados": desativados}

    @task
    def triagem(_anterior=None) -> dict:
        """Classifica os chamados novos ou alterados: dá para começar?

        Task SEPARADA do ciclo de espelho, de propósito. Ela fala com outro
        sistema (o gateway de IA) e falha por outros motivos; junto do sync,
        um gateway fora do ar pintaria de vermelho a sincronização — que
        funcionou — e o operador perderia a distinção entre "os chamados não
        chegaram" e "os chamados chegaram, mas não foram analisados".

        Nunca falha: sem gateway, o veredito sai da heurística. O que a task
        NÃO faz é fingir que a análise foi de IA (ver triagem_origem).
        """
        from utils.triagem_ia import (
            config_da_triagem, pendentes, params_gravar, sql_candidatos,
            sql_gravar, triar,
        )

        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        linhas = hook.get_records(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key LIKE 'caixa_ia%' OR config_key LIKE 'chamados_triagem%'")
        conf = config_da_triagem({k: (v or "").strip() for k, v in (linhas or [])})

        if not conf["habilitada"]:
            print("[TRIAGEM] desligada (chamados_triagem_habilitada=0) — "
                  "ligue em Admin > ServiceNow.")
            return {"status": "DESABILITADA", "triados": 0}

        api_key = ""
        if conf["api_key_enc"]:
            try:
                api_key = _decifrar(conf["api_key_enc"])
            except Exception as e:
                # Chave ilegível não pode parar a triagem: ela segue pela
                # heurística, e o motivo fica gravado em cada laudo.
                print(f"[TRIAGEM] chave de API ilegível ({e}) — heurística.")

        try:
            candidatos = hook.get_records(sql_candidatos())
        except Exception as e:
            # Colunas da 093 ainda não aplicadas é o caso esperado aqui.
            print(f"[TRIAGEM] não foi possível ler a fila: {e}")
            return {"status": "ERRO", "triados": 0, "erro": str(e)[:400]}

        fila = pendentes(candidatos or [], conf["lote"])
        if not fila:
            print("[TRIAGEM] nada a triar — a fila viva está toda analisada.")
            return {"status": "OK", "triados": 0}

        por_origem: dict = {}
        for chamado in fila:
            laudo = triar(chamado, conf, api_key)
            por_origem[laudo["origem"]] = por_origem.get(laudo["origem"], 0) + 1
            hook.run(sql_gravar(),
                     parameters=params_gravar(laudo, chamado["hash"],
                                              chamado["sys_id"]))
            marca = laudo["origem"].upper()
            print(f"[TRIAGEM] {chamado['numero']}: {laudo['veredito']} ({marca})"
                  + (f" — {laudo['erro']}" if laudo["erro"] else ""))

        restantes = max(0, len(candidatos or []) - len(fila))
        print(f"[TRIAGEM] {len(fila)} analisado(s): {por_origem}. "
              f"{restantes} candidato(s) ficaram para o próximo ciclo.")
        return {"status": "OK", "triados": len(fila), "por_origem": por_origem,
                "restantes": restantes}

    # A triagem roda DEPOIS do espelho: analisar antes do sync usaria o texto
    # do ciclo passado. Encadeada pelo retorno, e não por >>, para que uma
    # falha do sync não dispare a triagem sobre dados que não chegaram.
    triagem(ciclo())


etl_servicenow_sync()
