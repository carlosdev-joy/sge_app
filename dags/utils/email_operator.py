"""dags/utils/email_operator.py — o nó `email` do pipeline em tempo de corrida
(spec docs/spec-notificacao-email.md, F2).

Tudo é lido do BANCO no `execute`, nada vem embutido na DAG gerada:

  * `etl_app_config` (chaves `email_*`) — interruptor, remetente, limite de
    anexo, raízes permitidas e domínios permitidos, do Admin › E-mail;
  * `etl_pipeline_job.notify_json` — a config do nó (assunto, corpo, lista
    própria, herdar a do fluxo, anexo);
  * `etl_pipeline.email_destinatarios` — a lista do fluxo.

É isso que faz "mudar destinatário na tela vale já na próxima corrida, sem
republicar a DAG" (critério de aceite da F2). O preço é uma leitura por
execução do nó, que é barata perto de abrir uma sessão SSH.

⚠️ O worker CACHEIA `dags/utils/`: mudança aqui só vale depois de reiniciar o
worker do Airflow (senão a task fica verde rodando o código velho).
"""
from __future__ import annotations

import json

from airflow.models import BaseOperator

try:                                           # Airflow 2.x
    from airflow.exceptions import AirflowSkipException
except ImportError:                            # pragma: no cover
    AirflowSkipException = Exception           # type: ignore[assignment,misc]

import re as _re

# `{tabela:NOME}` — o mesmo alfabeto de `PLACEHOLDER_RE` (utils/email_envio.py),
# usado só para avisar sobre marcador que não resolve.
_QUALIFICADOS_RE = _re.compile(r"\{tabela:([A-Za-z0-9_.\-]{1,128})\}")

MSSQL_CONN_ID = "SQL14_DMDB41"
PIPELINE_TESTE = "_teste_admin"


def _cortar_utf16(texto: str, limite: int) -> str:
    """Corta pelo que o NVARCHAR conta (unidades UTF-16), não por code points.

    `[:500]` em code points deixa 500 caracteres astrais virarem 1000 unidades:
    o INSERT do log estoura e a linha do envio some — o `_gravar_log` é
    best-effort e engole a exceção. Com subpasta no anexo (F3) o caminho ficou
    livre, então o estouro deixou de ser hipótese remota."""
    unidades = (texto or "").encode("utf-16-le")
    if len(unidades) // 2 <= limite:
        return texto or ""
    return unidades[:limite * 2].decode("utf-16-le", "ignore")


def _formatar_data(valor) -> str:
    """AAAAMMDD a partir de date/datetime/str ('2026-09-11' ou '20260911')."""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y%m%d")
    texto = str(valor or "").strip()
    so_digitos = "".join(c for c in texto if c.isdigit())
    return so_digitos[:8] if len(so_digitos) >= 8 else texto


class EmailOperator(BaseOperator):
    """Envia o e-mail do nó pelo sendmail do servidor do DataStage.

    Falhas e seus destinos (decisão §8 da spec — falha de envio FALHA a task):
      canal desligado no Admin ........... task `skipped` (não é erro: o
                                           administrador desligou de propósito)
      sem destinatário ................... falha (o nó não faz sentido vazio)
      anexo ausente/grande/não-regular ... ENVIA sem anexo, com aviso no log e
                                           `status='sem_anexo'` no etl_email_log
      SSH fora ou sendmail rc != 0 ....... falha
    """

    ui_color = "#0d9488"          # teal-600, o mesmo do nó na tela

    def __init__(self, *, pipeline_name: str, job_name: str, ssh_conn_id: str,
                 mssql_conn_id: str = MSSQL_CONN_ID, **kwargs):
        super().__init__(**kwargs)
        self.pipeline_name = pipeline_name
        self.job_name = job_name
        self.ssh_conn_id = ssh_conn_id
        self.mssql_conn_id = mssql_conn_id

    # ── leitura do banco ────────────────────────────────────────────────────
    def _hook(self):
        from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook  # lazy (worker)

        return MsSqlHook(mssql_conn_id=self.mssql_conn_id)

    def _ler_config(self, hook) -> dict:
        """Config global do Admin › E-mail. `dags/` usa `%s` (pymssql)."""
        from utils import email_envio as ev

        linhas = hook.get_records(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s,%s)",
            parameters=("email_habilitado", "email_remetente", "email_limite_anexo_mb",
                        "email_anexo_raizes", "email_dominios_permitidos"))
        rows = {r[0]: r[1] for r in (linhas or [])}
        limite, _ = ev.validar_limite_anexo(rows.get("email_limite_anexo_mb"))

        def _lista(valor):
            try:
                dados = json.loads(valor or "[]")
            except (TypeError, ValueError):
                return []
            return [str(x) for x in dados] if isinstance(dados, list) else []

        return {
            "disponivel": "email_habilitado" in rows,
            "enabled": str(rows.get("email_habilitado") or "").strip() == "1",
            "remetente": str(rows.get("email_remetente") or "").strip(),
            "limite_mb": limite or ev.LIMITE_ANEXO_MB_PADRAO,
            "raizes": _lista(rows.get("email_anexo_raizes")),
            "dominios": _lista(rows.get("email_dominios_permitidos")),
        }

    def _ler_no(self, hook) -> dict:
        linha = hook.get_first(
            "SELECT notify_json FROM dbo.etl_pipeline_job "
            "WHERE pipeline_name=%s AND job_name=%s",
            parameters=(self.pipeline_name, self.job_name))
        if not linha or not linha[0]:
            return {}
        try:
            cfg = json.loads(linha[0])
        except (TypeError, ValueError):
            return {}
        return cfg if isinstance(cfg, dict) else {}

    def _ler_modelo(self, hook, modelo_id: int) -> dict:
        """O modelo do catálogo (migration 112), lido A CADA CORRIDA.

        É isso que faz trocar o layout no Admin valer para todos os nós sem
        republicar DAG nem reeditar nó.

        ⚠️ Modelo que sumiu **falha a etapa**. O catálogo de cards do Teams faz
        o oposto — template apagado ou desativado cai em silêncio para a
        mensagem embutida, e o aviso sai com a cara errada sem ninguém saber.
        Aqui, o cadastro já recusa apagar modelo em uso, então chegar aqui sem
        linha significa que alguém apagou direto no banco: é erro, não rotina.
        Modelo DESATIVADO continua valendo para quem já o escolheu — desativar
        tira da lista de escolha, não quebra quem está usando."""
        try:
            linha = hook.get_first(
                "SELECT corpo, CAST(html AS INT), nome FROM dbo.etl_email_modelo WHERE id=%s",
                parameters=(int(modelo_id),))
        except Exception as e:  # noqa: BLE001 — sem a 112 o nó não deveria ter modelo
            raise RuntimeError(
                f"Modelo {modelo_id} não pôde ser lido (migration 112 pendente?): {e}")
        if not linha or not linha[0]:
            raise RuntimeError(
                f"O modelo {modelo_id} não existe mais no catálogo (Admin › E-mail › Modelos). "
                "Escolha outro modelo no nó, ou recadastre o modelo.")
        return {"corpo": linha[0], "html": bool(linha[1]), "nome": linha[2]}

    def _ler_lista_do_pipeline(self, hook) -> list[str]:
        try:
            linha = hook.get_first(
                "SELECT email_destinatarios FROM dbo.etl_pipeline WHERE pipeline_name=%s",
                parameters=(self.pipeline_name,))
        except Exception as e:  # noqa: BLE001 — coluna da 111 pode não existir
            self.log.warning("[EMAIL] lista do fluxo indisponível (%s)", e)
            return []
        if not linha or not linha[0]:
            return []
        try:
            dados = json.loads(linha[0])
        except (TypeError, ValueError):
            return []
        return [str(x) for x in dados] if isinstance(dados, list) else []

    # ── placeholders ────────────────────────────────────────────────────────
    def _jobs_a_montante(self) -> list[str]:
        """Nomes dos JOBS imediatamente a montante.

        ⚠️ O factory liga o e-mail ao `t_end_*` da etapa, cujo task_id é
        `log_end_<job>` — e é o task_id `<job>` (o operador da etapa) que
        carrega o `rows_out` no XCom. Sem tirar o prefixo, `{linhas}` sairia
        SEMPRE vazio: o `log_end_` não devolve XCom nenhum."""
        nomes = []
        for tid in sorted(getattr(self, "upstream_task_ids", None) or []):
            t = str(tid)
            for prefixo in ("log_end_", "log_start_"):
                if t.startswith(prefixo):
                    t = t[len(prefixo):]
                    break
            if t and t not in nomes:
                nomes.append(t)
        return nomes

    def _linhas_a_montante(self, hook, context) -> str:
        """`{linhas}` = soma do `rows_out` dos jobs imediatamente a montante.

        Mesma regra do nó de notificação Teams: primeiro o XCom do run, depois
        `etl_ds_job_log` da execução. Nada disponível → string vazia, e o texto
        sai sem o número em vez de quebrar o envio."""
        ti = (context or {}).get("ti")
        execution_id = (context or {}).get("ts_nodash")
        total, achou = 0, False
        for job in self._jobs_a_montante():
            valor = None
            if ti is not None:
                try:
                    bruto = ti.xcom_pull(task_ids=job)
                    if bruto:
                        obj = json.loads(bruto) if isinstance(bruto, str) else bruto
                        if isinstance(obj, dict) and obj.get("rows_out") is not None:
                            valor = int(obj["rows_out"])
                except Exception:  # noqa: BLE001 — placeholder nunca derruba o envio
                    valor = None
            if valor is None and execution_id:
                try:
                    linha = hook.get_first(
                        "SELECT TOP 1 rows_out FROM dbo.etl_ds_job_log "
                        "WHERE execution_id=%s AND pipeline_name=%s AND job_name=%s "
                        "ORDER BY COALESCE(updated_at, last_polled_at) DESC",
                        parameters=(str(execution_id), self.pipeline_name, job))
                    if linha and linha[0] is not None:
                        valor = int(linha[0])
                except Exception as e:  # noqa: BLE001
                    self.log.info("[EMAIL] rows_out de %s indisponível (%s)", job, e)
            if valor is not None:
                total += valor; achou = True
        return str(total) if achou else ""

    def _odate(self, hook, context) -> str:
        """`{odate}` = a DATA DE REFERÊNCIA da corrida (o ODATE do produto), no
        formato AAAAMMDD — a que nomeia os arquivos do DataStage.

        ⚠️ NÃO é `ds_nodash`: em pipeline agendado, o `logical_date` é o INÍCIO
        do intervalo, ou seja, o dia ANTERIOR — o anexo `relatorio_{odate}.xlsx`
        apontaria para o arquivo de ontem e o e-mail sairia sem anexo. A fonte
        certa é a linha da corrida (a mesma que o operador DataStage usa para o
        `-param`); sem ela, o fim do intervalo; por último, a data de hoje."""
        ctx = context or {}
        dag_run = ctx.get("dag_run")
        run_id = getattr(dag_run, "run_id", None)
        if run_id:
            try:
                linha = hook.get_first(
                    "SELECT TOP 1 data_referencia FROM dbo.etl_pipeline_execucao "
                    "WHERE pipeline_name=%s AND execution_id=%s ORDER BY id",
                    parameters=(self.pipeline_name, run_id))
                if linha and linha[0] is not None:
                    return _formatar_data(linha[0])
            except Exception as e:  # noqa: BLE001 — sem a linha, cai no intervalo
                self.log.info("[EMAIL] data de referência da corrida indisponível (%s)", e)
        momento = ctx.get("data_interval_end") or ctx.get("logical_date")
        if momento is not None:
            return _formatar_data(momento)
        import datetime as _dt
        return _dt.date.today().strftime("%Y%m%d")

    def _status_geral(self, hook, context) -> str:
        """`{status}` = o estado agregado do pipeline nesta execução, a MESMA
        regra do card de fim do Teams.

        Fixar 'concluído' seria mentir: com um nó Aguarde de política
        'todas_terminarem', o e-mail roda depois de uma etapa que FALHOU."""
        execution_id = (context or {}).get("ts_nodash")
        if not execution_id:
            return "INFO"
        try:
            linha = hook.get_first(
                "SELECT CASE WHEN SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END)>0 THEN 'FAILED' "
                "     WHEN SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END)>0 THEN 'WARNING' "
                "     WHEN SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)>0 THEN 'SUCCESS' "
                "     WHEN SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END)>0 THEN 'SKIPPED' "
                "     ELSE 'INFO' END "
                "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s",
                parameters=(str(execution_id), self.pipeline_name))
            return (linha[0] if linha and linha[0] else "INFO")
        except Exception as e:  # noqa: BLE001
            self.log.info("[EMAIL] status geral indisponível (%s)", e)
            return "INFO"

    def _mapa(self, hook, context) -> dict:
        """Placeholders do assunto, do corpo e do NOME do anexo."""
        import datetime as _dt

        ctx = context or {}
        agora = _dt.datetime.now()
        dag_run = ctx.get("dag_run")
        inicio = getattr(dag_run, "start_date", None)
        try:                       # o fuso da tela é o de São Paulo
            from airflow.utils.timezone import convert_to_utc  # noqa: F401
            import zoneinfo
            if inicio is not None:
                inicio = inicio.astimezone(zoneinfo.ZoneInfo("America/Sao_Paulo"))
        except Exception:          # noqa: BLE001 — sem tz, usa como veio
            pass
        duracao = ""
        if inicio is not None:
            try:
                segundos = int((_dt.datetime.now(inicio.tzinfo) - inicio).total_seconds())
                # Relógio do worker atrás do início do run daria negativo, e a
                # formatação imprimiria lixo ("-1:16:26") no corpo do e-mail.
                segundos = max(0, segundos)
                duracao = f"{segundos // 3600:02d}:{(segundos % 3600) // 60:02d}:{segundos % 60:02d}"
            except Exception:      # noqa: BLE001
                duracao = ""
        return {
            "pipeline": self.pipeline_name,
            "job": self.job_name,
            "data": agora.strftime("%d/%m/%Y %H:%M"),
            # {odate} é a data de REFERÊNCIA da corrida (AAAAMMDD) — a que
            # nomeia os arquivos do DataStage; {data} é o relógio de quando o
            # e-mail saiu.
            "odate": self._odate(hook, context),
            "execution_id": str(ctx.get("ts_nodash") or ""),
            "inicio": inicio.strftime("%d/%m/%Y %H:%M") if inicio is not None else "",
            "duracao": duracao,
            # Sem `rows_out` a montante (o caso de quem liga o e-mail direto num
            # nó SQL ou numa Decisão), `{linhas}` vinha VAZIO e o modelo
            # institucional mostrava a linha "Linhas processadas" em branco, como
            # se a carga não tivesse trazido nada. O travessão diz "não se
            # aplica" — que é a verdade.
            "linhas": self._linhas_a_montante(hook, context) or "—",
            "status": self._status_geral(hook, context),
        }

    # ── tabela do nó SQL (F5 da spec de tabela do SQL) ──────────────────────
    def _tabelas_a_montante(self, context) -> dict:
        """`{nome do nó SQL: tabela}` dos nós imediatamente a montante.

        A tabela é publicada pelo nó SQL em `xcom_push(key="tabela")` (F4). Nó
        que não é SQL simplesmente não tem a chave, e nó SQL de uma DAG gerada
        ANTES da F4 também não — nesse caso o marcador se comporta como se não
        houvesse resultado, e o pipeline precisa ser republicado para ganhar o
        recurso. Nada aqui pode levantar: o e-mail sai sem a tabela, nunca falha
        por causa dela."""
        ti = (context or {}).get("ti")
        if ti is None:
            return {}
        achadas = {}
        for job in self._jobs_a_montante():
            try:
                dados = ti.xcom_pull(task_ids=job, key="tabela")
            except Exception as e:  # noqa: BLE001
                self.log.info("[EMAIL] tabela de %s indisponível (%s)", job, e)
                continue
            if isinstance(dados, dict) and dados.get("columns") is not None:
                achadas[job] = dados
        return achadas

    def _marcadores_de_tabela(self, context, html: bool, texto: str = "") -> dict:
        """As chaves `tabela` e `tabela:<NO>` já renderizadas.

        `{tabela}` sem qualificador só resolve quando há UM nó SQL a montante.
        Com dois, escolher um seria adivinhar — e o aviso sairia com o resultado
        da consulta errada, que é pior do que não sair. Nesse caso o bloco diz
        "(sem resultado)" e o log explica o que fazer (usar `{tabela:NOME}`).

        `texto` é o que vai ser interpolado: os avisos só saem quando o marcador
        é REALMENTE usado. Sem isso, um nó de e-mail que só diz "carga fechou",
        posto depois de duas consultas, passaria a reclamar em toda corrida de um
        marcador que ninguém escreveu."""
        from utils import sql_node as sq

        render = sq.tabela_html if html else sq.tabela_texto
        tabelas = self._tabelas_a_montante(context)
        marcadores = {f"tabela:{nome}": render(t) for nome, t in tabelas.items()}
        usa_marcador = "{tabela" in (texto or "")

        if len(tabelas) == 1:
            nome, dados = next(iter(tabelas.items()))
            marcadores["tabela"] = render(dados)
        else:
            marcadores["tabela"] = render({})
            if tabelas and usa_marcador:
                self.log.warning(
                    "[EMAIL] %d nós SQL a montante (%s): {tabela} não escolhe por você — "
                    "use {tabela:NOME_DO_NO}.", len(tabelas), ", ".join(sorted(tabelas)))

        if usa_marcador:
            if tabelas:
                # ⚠️ Linha de SUCESSO — é por ela que o smoke sabe que o worker
                # está com o código novo. Worker com `dags/utils/` em cache e
                # worker funcionando produziriam logs idênticos sem isto, e um
                # e-mail sem tabela passaria por "a consulta não trouxe nada".
                for nome, dados in sorted(tabelas.items()):
                    self.log.info("[EMAIL] tabela de %s: %s", nome,
                                  sq.resumo_para_log(dados))
            else:
                # Zero tabelas com o marcador escrito: o caso comum é o nó de
                # e-mail NÃO estar ligado direto ao nó SQL (`SQL → Decisão →
                # E-mail`, por exemplo), porque só o vizinho imediato é lido. Sem
                # esta linha o operador não tem como descobrir o porquê.
                self.log.warning(
                    "[EMAIL] {tabela} usado, mas nenhum nó SQL imediatamente a montante "
                    "(vizinhos: %s). Só o vizinho IMEDIATO é lido — ligue o nó de e-mail "
                    "direto no nó SQL, e republique o pipeline se ele é anterior à "
                    "publicação da tabela.", ", ".join(self._jobs_a_montante()) or "nenhum")
            nao_resolvidos = [m for m in _QUALIFICADOS_RE.findall(texto or "")
                              if f"tabela:{m}" not in marcadores]
            if nao_resolvidos:
                self.log.warning(
                    "[EMAIL] {tabela:%s} não resolve: a montante existem %s. O marcador sai "
                    "literal no e-mail.", "}, {tabela:".join(nao_resolvidos),
                    ", ".join(sorted(tabelas)) or "nenhum nó SQL")
        return marcadores

    def _marcadores_do_assunto(self, context) -> dict:
        """No assunto a tabela vira um resumo (`3 linhas × 2 colunas`).

        Markup — ou o bloco de texto com quebras de linha — num cabeçalho de
        e-mail faria a régua do assunto recusar a mensagem DEPOIS de resolver os
        marcadores, derrubando a etapa por algo que a tela deixou escrever."""
        from utils import sql_node as sq

        tabelas = self._tabelas_a_montante(context)
        saida = {f"tabela:{nome}": sq.resumo_curto(t) for nome, t in tabelas.items()}
        saida["tabela"] = sq.resumo_curto(next(iter(tabelas.values())) if len(tabelas) == 1 else {})
        return saida

    # ── execução ────────────────────────────────────────────────────────────
    def execute(self, context):
        from utils import email_envio as ev

        hook = self._hook()
        cfg = self._ler_config(hook)
        if not cfg["disponivel"]:
            raise RuntimeError(
                "E-mail indisponível: migration 111 pendente (chaves email_* em etl_app_config).")
        if not cfg["enabled"]:
            raise AirflowSkipException(
                "Canal de e-mail desligado em Admin › E-mail — nó pulado de propósito.")
        if not cfg["remetente"]:
            raise RuntimeError("Canal de e-mail ligado sem remetente configurado em Admin › E-mail.")

        no = self._ler_no(hook)
        if not no:
            raise RuntimeError(
                f"Nó de e-mail '{self.job_name}' sem configuração gravada (notify_json vazio).")

        brutos = list(no.get("destinatarios") or [])
        if no.get("incluir_pipeline", True):
            brutos += self._ler_lista_do_pipeline(hook)
        destinatarios, erros = ev.validar_destinatarios(brutos, cfg["dominios"])
        if erros:
            # Domínio barrado DEPOIS do cadastro (o Admin mudou a allowlist):
            # falha explícita, nunca envio parcial silencioso.
            raise RuntimeError("Destinatários recusados: " + "; ".join(erros))
        if not destinatarios:
            raise RuntimeError(
                "Nó de e-mail sem destinatário: nem a lista do nó nem a do fluxo têm endereço.")

        # Corpo: do MODELO quando o nó aponta para um; senão, o corpo próprio
        # (a opção "Corpo livre" da lista).
        modelo_id = no.get("modelo_id")
        corpo_bruto = str(no.get("corpo") or "")
        html = bool(no.get("html"))
        if modelo_id is not None:
            modelo = self._ler_modelo(hook, modelo_id)
            corpo_bruto, html = modelo["corpo"], modelo["html"]
            self.log.info("[EMAIL] corpo do modelo '%s' (#%s)", modelo["nome"], modelo_id)

        mapa = self._mapa(hook, context)
        # A tabela entra por último e em DUAS versões: no corpo ela é HTML (ou
        # texto, se o corpo não for HTML) e no assunto vira resumo.
        corpo = ev.interpolar(corpo_bruto,
                              {**mapa, **self._marcadores_de_tabela(context, html, corpo_bruto)})
        assunto = ev.interpolar(str(no.get("assunto") or ""),
                                {**mapa, **self._marcadores_do_assunto(context)})
        assunto_ok, erro = ev.validar_assunto(assunto)
        if erro:
            raise RuntimeError(f"Assunto inválido depois de resolver os placeholders: {erro}")

        anexo_nome = anexo_bytes = None
        anexo_path = None
        aviso = None
        anexo_cfg = no.get("anexo") or None
        status = "enviado"
        if isinstance(anexo_cfg, dict) and anexo_cfg.get("raiz") and anexo_cfg.get("nome"):
            from airflow.providers.ssh.hooks.ssh import SSHHook  # lazy (worker)

            try:
                with SSHHook(ssh_conn_id=self.ssh_conn_id).get_conn() as client:
                    sftp = client.open_sftp()
                    try:
                        anexo_bytes, aviso, detalhe = ev.resolver_anexo(
                            sftp, anexo_cfg["raiz"], anexo_cfg["nome"], cfg["raizes"],
                            cfg["limite_mb"], mapa)
                    finally:
                        sftp.close()
                anexo_path = detalhe.get("caminho")
            except Exception as e:  # noqa: BLE001 — SSH fora ao BUSCAR o anexo
                # Não pode derrubar a task antes do log: sem isto, a falha de
                # conexão na busca do anexo não deixaria linha nenhuma em
                # etl_email_log, ao contrário da mesma falha no envio.
                anexo_bytes, anexo_path = None, None
                aviso = (f"anexo não pôde ser buscado em {anexo_cfg['raiz']} "
                         f"({type(e).__name__}: {e}) — e-mail enviado sem anexo")
            if anexo_bytes is None:
                status = "sem_anexo"
                if aviso:
                    self.log.warning("[EMAIL] %s", aviso)
            else:
                anexo_nome = (anexo_path or "").rsplit("/", 1)[-1]

        mensagem = ev.montar_mensagem(
            cfg["remetente"], destinatarios, assunto_ok, corpo,
            html=html, anexo_nome=anexo_nome, anexo_bytes=anexo_bytes,
            cabecalho_extra={"X-Orquestra-Pipeline": self.pipeline_name,
                             "X-Orquestra-Job": self.job_name})

        from airflow.providers.ssh.hooks.ssh import SSHHook  # lazy (worker)

        erro_envio = None
        resultado = {"exit_code": None, "stderr": "", "duration_ms": None}
        try:
            with SSHHook(ssh_conn_id=self.ssh_conn_id).get_conn() as client:
                resultado = ev.enviar(client, mensagem, cfg["remetente"])
            if resultado["exit_code"] != 0:
                erro_envio = (f"sendmail devolveu rc={resultado['exit_code']}: "
                              f"{resultado['stderr'] or 'sem detalhe'}")
        except Exception as e:  # noqa: BLE001 — vira falha da task, mas com log gravado
            erro_envio = f"{type(e).__name__}: {e}"

        self._gravar_log(hook, context, remetente=cfg["remetente"], destinatarios=destinatarios,
                         assunto=assunto_ok, anexo_path=anexo_path,
                         anexo_bytes=(len(anexo_bytes) if anexo_bytes else None),
                         status=("falhou" if erro_envio else status),
                         erro=(erro_envio or aviso), duracao_ms=resultado.get("duration_ms"))
        if erro_envio:
            raise RuntimeError(f"Falha ao enviar o e-mail: {erro_envio}")
        self.log.info("[EMAIL] enviado para: %s (anexo: %s)", ", ".join(destinatarios),
                      anexo_path if anexo_bytes else (aviso or "nenhum"))
        return {"destinatarios": destinatarios, "status": status, "anexo": anexo_path if anexo_bytes else None}

    def _gravar_log(self, hook, context, **campos) -> None:
        """Uma linha em etl_email_log. NUNCA derruba a task: o log é rastro, e
        perder o rastro é ruim, mas mentir sobre o envio é pior."""
        ctx = context or {}
        dag_run = ctx.get("dag_run")
        try:
            hook.run(
                "INSERT INTO dbo.etl_email_log (pipeline_name, job_name, dag_run_id, execution_id, "
                " remetente, destinatarios, assunto, anexo_path, anexo_bytes, status, erro, duracao_ms) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                parameters=(
                    self.pipeline_name[:200], self.job_name[:200],
                    (getattr(dag_run, "run_id", None) or None),
                    (str(ctx.get("ts_nodash")) if ctx.get("ts_nodash") else None),
                    campos["remetente"][:200],
                    json.dumps(campos["destinatarios"], ensure_ascii=False),
                    campos["assunto"][:500],
                    (_cortar_utf16(campos["anexo_path"], 500) if campos.get("anexo_path") else None),
                    campos["anexo_bytes"],
                    campos["status"][:20],
                    (campos["erro"][:1000] if campos.get("erro") else None),
                    campos.get("duracao_ms")))
        except Exception as e:  # noqa: BLE001
            self.log.warning("[EMAIL] envio registrado no log da task, mas não em etl_email_log (%s)", e)
