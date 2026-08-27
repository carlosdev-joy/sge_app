"""dags/utils/job_operators.py — operadores reutilizáveis dos jobs gerados.

O factory gera DAGs que apenas CHAMAM estes operadores (igual ao DataStage).
Assim, melhorias na execução de um tipo de job (log, tratamento de erro, bind de
parâmetros…) entram aqui e TODAS as DAGs herdam no próximo parse do Airflow, SEM
precisar regenerar os arquivos. Só mudanças de ESTRUTURA (jobs, dependências,
agendamento) exigem regeneração.
"""
from __future__ import annotations

from airflow.models import BaseOperator
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.providers.ssh.operators.ssh import SSHOperator


class LogStartOperator(PythonOperator):
    """O ``log_start_<job>`` de toda etapa — um ``PythonOperator`` que o Airflow
    aceita **rescheduleando de verdade** (F5, docs/spec-operacao-nivel-etapa.md
    §5 Bloco C).

    ⚠️ **DEFEITO ENCONTRADO NA PROVA VIVA (dev, 2026-08-03), e a razão desta
    classe existir.** O portão da etapa em espera levanta
    ``AirflowRescheduleException``, e o ``taskinstance`` do Airflow 2.11 aceita
    isso de QUALQUER operador: a task vai para ``up_for_reschedule`` e a data do
    próximo teste é gravada em ``task_reschedule``. Só que quem decide *quando*
    trazer a task de volta é a dependência ``ReadyToRescheduleDep``, e ela
    começa assim::

        if not is_mapped and not getattr(ti.task, "reschedule", False) ...:
            yield self._passing_status(reason="Task is not in reschedule mode.")
            return

    Ou seja: sem o atributo ``reschedule``, a data gravada é **ignorada** e o
    scheduler recoloca a task na fila na primeira passagem. Medido na execução
    real: **56 verificações em ~5 minutos** (uma a cada ~5s) em vez de uma por
    minuto. Isso é polling caro disfarçado de espera barata — exatamente o que
    o §5 promete NÃO fazer ("o modo do Airflow que devolve o worker entre as
    verificações — não é polling que segura recurso").

    A correção usa o MESMO contrato do framework, não um truque: o
    ``BaseSensorOperator`` publica ``reschedule`` acrescentando o campo aos
    ``serialized_fields`` — é assim que o atributo chega ao scheduler, que
    trabalha sobre a DAG **serializada**. Uma classe com o atributo mas sem o
    campo serializado não funcionaria: o scheduler não veria nada.

    **Impacto quando NÃO há pausa: nenhum.** ``ReadyToRescheduleDep`` só olha o
    atributo para então consultar ``task_reschedule``; sem linha lá, devolve
    "There is no reschedule request for this task instance" e passa. O
    comportamento de execução, os kwargs, o trigger_rule e o task_id continuam
    os do ``PythonOperator`` de sempre — esta classe não sobrescreve
    ``execute``.
    """

    reschedule = True

    @classmethod
    def get_serialized_fields(cls):
        return super().get_serialized_fields() | {"reschedule"}

    @property
    def deps(self):
        """⚠️ **A SEGUNDA metade da correção — e ela também veio da prova viva.**

        Com o atributo ``reschedule`` serializado, a cadência continuou em ~4s.
        Motivo: ``ReadyToRescheduleDep`` **não está em** ``BaseOperator.deps``.
        Quem a acrescenta é o ``BaseSensorOperator``, por esta mesma
        propriedade — sem ela a dependência simplesmente não é avaliada, e a
        data gravada em ``task_reschedule`` nunca é consultada.

        A serialização carrega o conjunto porque o Airflow só o inclui quando
        ``op.deps != BaseOperator.deps`` (``_serialize_node``), e a
        desserialização aceita classes de ``airflow.ti_deps.deps`` — que é
        exatamente de onde esta vem.

        Sem linha em ``task_reschedule`` a dep devolve "There is no reschedule
        request for this task instance" e passa: no caminho normal, nada muda.
        """
        from airflow.ti_deps.deps.ready_to_reschedule import ReadyToRescheduleDep
        return super().deps | {ReadyToRescheduleDep()}

_INT_TYPES   = {"INT", "BIGINT", "SMALLINT", "TINYINT"}
# DECIMAL/NUMERIC/MONEY são exatos: coagir via float() perdia precisão em
# SILÊNCIO acima de ~15 dígitos (task verde, valor errado na proc — achado da
# revisão adversarial). decimal.Decimal preserva o literal; o pymssql o binda
# como decimal nativamente. FLOAT/REAL são aproximados por definição — float().
_EXACT_TYPES = {"DECIMAL", "NUMERIC", "MONEY"}
_FLOAT_TYPES = {"FLOAT", "REAL"}


def _coerce(value, ptype):
    """Converte o valor do parâmetro conforme o tipo declarado (runtime)."""
    ptype = (ptype or "VARCHAR").upper()
    if value is None or value == "":
        return None
    try:
        if ptype in _INT_TYPES:
            return int(value)
        if ptype in _EXACT_TYPES:
            import decimal
            try:
                return decimal.Decimal(str(value).strip())
            except decimal.InvalidOperation:
                return value    # mesmo fallback dos demais: SQL falha ALTO
        if ptype in _FLOAT_TYPES:
            return float(value)
        if ptype == "BIT":
            return 1 if str(value).strip().lower() in ("1", "true", "sim", "yes", "y", "t") else 0
    except (TypeError, ValueError):
        return value
    return value


def _log_resultsets(cur, log):
    """Itera os result sets retornados e loga quantidade/amostra/linhas afetadas."""
    ssets = 0
    total = 0
    while True:
        if cur.description:
            rows = cur.fetchall()
            ssets += 1
            total += len(rows)
            log.info("[SQL] resultado %d: %d linha(s)", ssets, len(rows))
            for r in rows[:50]:
                log.info("[SQL]   %s", tuple(r))
        elif cur.rowcount is not None and cur.rowcount >= 0:
            log.info("[SQL] linhas afetadas: %d", cur.rowcount)
        if not cur.nextset():
            break
    return ssets, total


class StoredProcOperator(BaseOperator):
    """EXEC de stored procedure com bind de parâmetros e log do retorno/erro.

    ⚠️ Os parâmetros da proc chegam em ``proc_params`` — NUNCA ``params``, que é
    kwarg RESERVADO do BaseOperator do Airflow, com dois modos de quebrar:
      1. no import: ``params`` exige mapping — a lista de dicts da factory dava
         ``TypeError: params must be a mapping`` e a DAG nem importava;
      2. em runtime: em run com ``dag_run.conf`` não-vazia o Airflow SOBRESCREVE
         ``self.params`` com os params mesclados da conf (dict de strings) —
         iterar isso dava ``AttributeError: 'str' object has no attribute 'get'``
         em TODO job storedproc disparado com conf (ex.: dependentes da F3).
    """

    def __init__(self, *, proc, mssql_conn_id, proc_params=None, database=None, **kwargs):
        super().__init__(**kwargs)
        self.proc = proc
        self.mssql_conn_id = mssql_conn_id
        self.proc_params = proc_params or []
        self.database = (database or "").strip() or None

    def execute(self, context):
        if not self.proc:
            raise ValueError("StoredProcOperator: 'proc' não informado")
        # Banco-alvo no MESMO servidor → nome de 3 partes: EXEC [banco].schema.proc
        target = f"[{self.database}].{self.proc}" if self.database else self.proc
        # Conexão resolvida pelo Orquestra (dbo.etl_conexao primeiro, Airflow
        # como fallback) — antes o MsSqlHook ignorava as conexões nativas.
        from utils.conn_resolver import abrir_conexao_mssql  # lazy
        conn = abrir_conexao_mssql(self.mssql_conn_id, appname="orquestra-storedproc")
        cur = conn.cursor()
        try:
            valid = [p for p in self.proc_params if (p.get("name") or "").strip()]
            if valid:
                # Placeholder %s + tupla: a conexão é pymssql (conn_resolver) —
                # '?' é do pyodbc da api/ e daria "Incorrect syntax near '?'".
                ph = ", ".join(
                    (str(p["name"]) if str(p["name"]).startswith("@") else "@" + str(p["name"])) + "=%s"
                    for p in valid
                )
                vals = tuple(_coerce(p.get("value"), p.get("type")) for p in valid)
                sql = f"EXEC {target} {ph}"
                self.log.info("[SQL] %s", sql)
                cur.execute(sql, vals)
            else:
                # Sem parâmetros → não envia nenhum parâmetro.
                self.log.info("[SQL] EXEC %s", target)
                cur.execute(f"EXEC {target}")
            ssets, total = _log_resultsets(cur, self.log)
            conn.commit()
            self.log.info("[SQL] proc %s OK (result sets=%d, linhas=%d)", target, ssets, total)
        except Exception as e:
            self.log.error("[SQL][ERRO] %s: %s", target, e)
            raise
        finally:
            try:
                cur.close(); conn.close()
            except Exception:
                pass


class SqlOperator(BaseOperator):
    """SQL livre com log do retorno/erro."""

    def __init__(self, *, sql, mssql_conn_id, **kwargs):
        super().__init__(**kwargs)
        self.sql = sql
        self.mssql_conn_id = mssql_conn_id

    def execute(self, context):
        from utils.conn_resolver import abrir_conexao_mssql  # lazy
        conn = abrir_conexao_mssql(self.mssql_conn_id, appname="orquestra-sql")
        cur = conn.cursor()
        try:
            self.log.info("[SQL] %s", self.sql)
            cur.execute(self.sql)
            ssets, total = _log_resultsets(cur, self.log)
            conn.commit()
            self.log.info("[SQL] OK (result sets=%d, linhas=%d)", ssets, total)
        except Exception as e:
            self.log.error("[SQL][ERRO] %s", e)
            raise
        finally:
            try:
                cur.close(); conn.close()
            except Exception:
                pass


class PythonModuleOperator(BaseOperator):
    """Importa um módulo e chama run(**context) ou main()."""

    def __init__(self, *, module, **kwargs):
        super().__init__(**kwargs)
        self.module = module

    def execute(self, context):
        import importlib
        self.log.info("[PY] importando %s", self.module)
        mod = importlib.import_module(self.module)
        if hasattr(mod, "run"):
            mod.run(**context)
        elif hasattr(mod, "main"):
            mod.main()
        else:
            raise AttributeError(f"módulo '{self.module}' não tem run() nem main()")
        self.log.info("[PY] %s concluído", self.module)


class HttpCallOperator(BaseOperator):
    """Chamada HTTP simples com raise_for_status."""

    def __init__(self, *, url, method="GET", timeout=30, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.method = method
        self.timeout = timeout

    def execute(self, context):
        import requests
        self.log.info("[HTTP] %s %s", self.method, self.url)
        resp = requests.request(self.method, self.url, timeout=self.timeout)
        resp.raise_for_status()
        self.log.info("[HTTP] status=%s bytes=%s", resp.status_code, len(resp.content))
        return resp.status_code


class PythonScriptOperator(SSHOperator):
    """Job python do ORQUESTRA em SERVIDOR REMOTO (nó Python v2, migration 059).

    Dois modos — ambos executam via SSH no servidor do ``ssh_conn_id``:
      - ``modo='arquivo'``: roda um script .py que JÁ existe no servidor
        (``<interpretador> <script_path>``).
      - ``modo='codigo'``: PUBLICA o código do usuário no servidor via SFTP
        (``mkdir -p`` + escrita de ``<destino_dir>/<arquivo>``) e então executa
        (``cd <destino_dir> && <interpretador> <arquivo>``). O arquivo é
        sobrescrito a cada execução — a fonte da verdade é o Orquestra.

    O modo legado 'modulo' NÃO passa por aqui (segue no PythonModuleOperator,
    dentro do worker). ``template_ext=()`` pela mesma razão do ShellOperator:
    caminho terminando em .sh/.py não pode virar arquivo de template Jinja.
    Aspas/espacos nos caminhos são tratados com shlex.quote em RUNTIME (aqui),
    não na geração do código."""
    template_ext = ()

    def __init__(self, *, modo, script_path=None, destino_dir=None, arquivo=None,
                 codigo=None, interpretador=None, **kwargs):
        import shlex
        interp = (interpretador or "python3").strip() or "python3"
        if modo == "codigo":
            command = (f"cd {shlex.quote(destino_dir or '')} && "
                       f"{interp} {shlex.quote(arquivo or '')}")
        else:
            command = f"{interp} {shlex.quote(script_path or '')}"
        super().__init__(command=command, **kwargs)
        self.modo = modo
        self.script_path = script_path
        self.destino_dir = destino_dir
        self.arquivo = arquivo
        self.codigo = codigo
        self.interpretador = interp

    def execute(self, context):
        if self.modo == "codigo":
            self._publicar_arquivo()
        return super().execute(context)

    def _publicar_arquivo(self):
        """Publica o código no servidor (mkdir -p + SFTP). Falha ALTO em
        qualquer degrau — publicar pela metade e executar seria pior."""
        import posixpath
        import shlex
        from airflow.providers.ssh.hooks.ssh import SSHHook  # lazy (worker)

        remoto = posixpath.join(self.destino_dir or "", self.arquivo or "")
        dados = (self.codigo or "").encode("utf-8")
        self.log.info("[PY] publicando %s (%d bytes) via SFTP em %s",
                      remoto, len(dados), self.ssh_conn_id)
        hook = SSHHook(ssh_conn_id=self.ssh_conn_id)
        with hook.get_conn() as client:
            _, out, err = client.exec_command(
                f"mkdir -p {shlex.quote(self.destino_dir or '')}")
            rc = out.channel.recv_exit_status()
            if rc != 0:
                detalhe = err.read().decode(errors="replace")[:400]
                raise RuntimeError(
                    f"mkdir -p {self.destino_dir!r} falhou (rc={rc}): {detalhe}")
            sftp = client.open_sftp()
            try:
                with sftp.open(remoto, "wb") as fh:
                    fh.write(dados)
            finally:
                sftp.close()
        self.log.info("[PY] publicado — executando: %s", self.command)


class ShellOperator(SSHOperator):
    """Job shell do ORQUESTRA — SSH no servidor do ``ssh_conn_id`` e executa o
    comando lá.

    ``template_ext`` VAZIO de propósito: o SSHOperator herda ``('.sh',)`` e o
    Jinja do Airflow trata QUALQUER campo templated terminando em .sh como
    CAMINHO de arquivo de template a carregar do disco — um comando legítimo
    como ``cd /x && ./script.sh`` morria com TemplateNotFound no render
    (incidente SHELL_LIMPA_FS_DATASTAGE, 2026-07-07). O comando do usuário é
    sempre string inline; macros Jinja ``{{ ds }}`` continuam funcionando
    (``template_fields`` fica intacto)."""
    template_ext = ()
