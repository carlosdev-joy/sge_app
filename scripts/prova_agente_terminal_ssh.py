"""Prova do agente Terminal com SSH de VERDADE no DEV (spec docs/spec-agente-terminal.md, F3).

O que prova (e que dublê nenhum prova): o shell REMOTO (bash) recebe só o que o classificador aprovou.
Bateria A: ~70 comandos adversários cujo EFEITO, se o truque furasse, seria criar `/tmp/CANARIO_<n>`
(`;`, `&&`, `|`, `$()`, crase, newline, `>`, `$'..'`, `sort -o`, `find -exec/-fprint`, `uniq a b`…). Os que o
classificador deixa passar como leitura são EXECUTADOS de verdade; os demais nunca chegam ao servidor. Depois
confere por SSH independente (`ls /tmp`) que NENHUM canário existe.
Bateria B: comandos legítimos devolvem a saída certa; recursivo não vaza `.env`; saída é redigida; limite de
bytes fecha o canal; caminho sensível nunca roda.

Como rodar (DEV; o container da API tem paramiko e as variáveis DS_SSH_* do sshd-amostra):
    C=orquestra-api
    docker exec $C rm -rf /tmp/f3 && docker cp api $C:/tmp/f3 && docker cp scripts/prova_agente_terminal_ssh.py $C:/tmp/prova_ssh.py
    docker exec $C sh -c 'cd /tmp/f3 && PYTHONPATH=/tmp/f3 python /tmp/prova_ssh.py'
    docker exec $C rm -rf /tmp/f3 /tmp/prova_ssh.py
(copia a `api/` INTEIRA da branch: misturar só `services/` com o `/app` do container quebra quando as linhas divergem — main × develop)
Nunca aponte para produção: ela escreve em /tmp do servidor de teste (e limpa depois).
"""
import dataclasses
import os
import sys
import time
import uuid

import paramiko

from services import agentes_terminal as aterm
from services import agentes_terminal_classe as cls
from services import agentes_terminal_ssh as tssh

os.environ.setdefault("TERMINAL_SSH_AUTO_ADD", "1")  # o sshd-amostra não tem known_hosts (só DEV)
FALHAS: list[str] = []


def ok(msg):
    print("OK  ", msg)


def falha(msg):
    FALHAS.append(msg)
    print("FALHA", msg)


def raw(cmd: str) -> str:
    """SSH independente do executor (para montar o cenário e conferir o resultado)."""
    srv = tssh.servidores()["datastage"]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(srv.host, srv.port, srv.user, srv.password, allow_agent=False, look_for_keys=False, timeout=10)
    try:
        _, o, e = c.exec_command(cmd, timeout=30)
        return o.read().decode("utf-8", "replace") + e.read().decode("utf-8", "replace")
    finally:
        c.close()


def main() -> int:
    base = tssh.servidores().get("datastage")
    if base is None:
        print("DS_SSH_HOST/USER não configurados neste container")
        return 2
    srv = dataclasses.replace(base, raizes=("/opt", "/var/log", "/tmp"))
    tag = uuid.uuid4().hex[:8]
    C = f"/tmp/CANARIO_{tag}_"
    pasta = f"/tmp/prova_terminal_{tag}"
    raw(f"rm -rf {pasta}; mkdir -p {pasta}/sub; "
        f"printf 'inicio\\nlinha erro 1\\nlinha ok\\nlinha ERRO 2\\nfim\\n' > {pasta}/a.log; "
        f"printf 'SEGREDO_CANARIO=abc123\\n' > {pasta}/.env; printf 'SEGREDO_CANARIO=zzz\\n' > {pasta}/sub/chave.pem; "
        f"printf 'nada aqui\\n' > {pasta}/notes.txt; "
        f"printf 'password: hunter2\\nDB_TOKEN=xyz789\\nuser: bob\\n' > {pasta}/cfg.txt; "
        f"head -c 300000 /dev/zero | tr '\\\\0' 'x' > {pasta}/grande.txt; touch '{pasta}/x;touch {C}Q1'")
    try:
        # ───────────── Bateria A: nenhum truque cria o canário ─────────────
        adversarios = [
            f"ls /opt; touch {C}1", f"ls /opt && touch {C}2", f"ls /opt || touch {C}3", f"ls /opt | touch {C}4",
            f"ls /opt & touch {C}5", f"ls $(touch {C}6)", f"ls `touch {C}7`", f"ls /opt\ntouch {C}8", f"ls /opt\rtouch {C}9",
            f"ls /opt > {C}10", f"cat {pasta}/a.log >> {C}11", f"$'touch' {C}12", f"ls /opt{{,/x}}; touch {C}13",
            f"touch {C}14", f"sort -o {C}15 {pasta}/a.log", f"sort --output={C}16 {pasta}/a.log", f"uniq {pasta}/a.log {C}17",
            f"find /opt -maxdepth 1 -exec touch {C}18 ;", f"find /opt -maxdepth 1 -fprint {C}19", f"find /opt -maxdepth 1 -fprintf {C}20 %p",
            f"find /opt -maxdepth 1 -ok touch {C}21 ;", f"find /opt -maxdepth 1 -delete", f"cp {pasta}/a.log {C}22", f"tee {C}23",
            f"dd if={pasta}/a.log of={C}24", f"bash -c 'touch {C}25'", f"sh -c 'touch {C}26'", f"env touch {C}27", f"xargs touch {C}28",
            f"awk 'BEGIN{{system(\"touch {C}29\")}}'", f"python3 -c 'open(\"{C}30\",\"w\")'", f"ls ${{IFS}}/opt${{IFS}}; touch {C}31",
            f"ls /opt;{{touch,{C}32}}", f"head -n1 {pasta}/a.log | tee {C}33", f"grep -r x {pasta} > {C}34",
            f"tail -f {pasta}/a.log; touch {C}35", f"ls /opt\x00touch {C}36", f"ls /opt\x1b[0;touch {C}37", f"ls /opt\;touch {C}38",
            f"ls '/opt';touch {C}39", f'ls "/opt"; touch {C}40', f"(touch {C}41)", f"{{ touch {C}42; }}", f"!touch {C}43",
            f"ls /opt #; touch {C}44", f"ls /opt/é; touch {C}45", f"cat {pasta}/a.log; $(touch {C}46)", f"ls /opt --; touch {C}47",
            f"FOO=1 touch {C}48", f"/usr/bin/touch {C}49", f"./touch {C}50", f"~/touch {C}51", f"touch\t{C}52", f"touch\u2028{C}53",
            f"ls {pasta}/*; touch {C}54", f"grep -e x {pasta}/a.log; touch {C}55", f"stat -c %n {pasta}/a.log; touch {C}56",
            f"du -sh /opt; touch {C}57", f"ps aux; touch {C}58", f"df -h & touch {C}59", f"uptime; touch {C}60",
            # chegam ao servidor como LEITURA com metacaracteres DENTRO de aspas — têm de chegar como texto, sem efeito:
            f"ls '{pasta}/x;touch {C}Q2'", f'ls "{pasta}/$(touch {C}Q3)"'.replace("$", ""), f"grep -e ';touch {C}Q4' {pasta}/a.log",
            f"grep -E 'a|b;touch {C}Q5&&x' {pasta}/a.log", f"find {pasta} -name 'x;touch {C}Q6'", f"ls '{pasta}/x;touch {C}Q1'",
        ]
        n_exec = n_barrado = 0
        for cmd in adversarios:
            v = cls.classificar(cmd, raizes=srv.raizes)
            if v.classe != "leitura":
                n_barrado += 1
                continue
            n_exec += 1
            tssh.executar_bloqueante(srv, cls.linha_de_execucao(v.argv), timeout_s=15)
        ok(f"bateria A: {len(adversarios)} comandos adversários — {n_barrado} barrados pelo classificador, {n_exec} executados como leitura (com metacaracteres só dentro de aspas)")
        if n_exec == 0:
            falha("a bateria A precisa executar alguns comandos de leitura com aspas (senão não prova nada)")
        achados = [l for l in raw(f"ls /tmp | grep CANARIO_{tag}").splitlines() if l.strip()]
        # `Q1` é o arquivo que NÓS criamos no setup (nome com `;touch`), não um canário criado por truque
        criados_por_truque = [a for a in achados if not a.endswith("Q1")]
        if criados_por_truque:
            falha(f"CANÁRIOS CRIADOS (o shell executou algo extra): {criados_por_truque}")
        else:
            ok("nenhum canário existe no servidor — o shell remoto só recebeu o que foi classificado")

        # ───────────── Bateria B: o que é legítimo funciona ─────────────
        def roda(cmd, **kw):
            v = cls.classificar(cmd, raizes=srv.raizes)
            assert v.classe == "leitura", (cmd, v)
            r = tssh.executar_bloqueante(srv, cls.linha_de_execucao(v.argv), timeout_s=20, **kw)
            return r

        r = roda(f"cat {pasta}/a.log"); (ok if "linha ok" in r.stdout and r.exit_code == 0 else falha)("cat devolve o arquivo")
        r = roda(f"tail -n 2 {pasta}/a.log"); (ok if r.stdout.strip().splitlines() == ["linha ERRO 2", "fim"] else falha)("tail -n 2 devolve as 2 últimas")
        r = roda(f"head -n 1 {pasta}/a.log"); (ok if r.stdout.strip() == "inicio" else falha)("head -n 1")
        r = roda(f"grep -i -n erro {pasta}/a.log"); (ok if "2:linha erro 1" in r.stdout and "4:linha ERRO 2" in r.stdout else falha)("grep -i -n")
        r = roda(f"wc -l {pasta}/a.log"); (ok if r.stdout.split()[0] == "5" else falha)("wc -l")
        r = roda(f"ls -la {pasta}"); (ok if "a.log" in r.stdout and ".env" in r.stdout else falha)("ls lista nomes (só nomes — o conteúdo do .env não)")
        r = roda("ps aux"); (ok if "PID" in r.stdout else falha)("ps aux")
        r = roda("df -h /tmp"); (ok if "Filesystem" in r.stdout else falha)("df -h")
        r = roda("whoami"); (ok if r.stdout.strip() == srv.user else falha)("whoami")
        r = roda(f"find {pasta} -name '*.log'"); (ok if r.stdout.strip() == f"{pasta}/a.log" else falha)("find -name")
        r = roda(f"stat -c %s {pasta}/notes.txt"); (ok if r.stdout.strip() == "10" else falha)("stat -c")

        # recursivo nunca vaza `.env`/`.pem` (os excludes são injetados pelo classificador)
        v = cls.classificar(f"grep -r -n -e SEGREDO_CANARIO {pasta}", raizes=srv.raizes)
        r = tssh.executar_bloqueante(srv, cls.linha_de_execucao(v.argv), timeout_s=20)
        (ok if "abc123" not in r.stdout and "zzz" not in r.stdout else falha)("grep -r NÃO vaza o conteúdo de .env nem de .pem")
        sem_exclude = raw(f"grep -r -n -e SEGREDO_CANARIO {pasta}")
        (ok if "abc123" in sem_exclude else falha)("controle: SEM os excludes o segredo apareceria (o teste é discriminante)")

        # caminho sensível nunca roda
        for c in (f"cat {pasta}/.env", f"cat {pasta}/sub/chave.pem", f"head {pasta}/.env"):
            (ok if cls.classificar(c, raizes=srv.raizes).classe == "proibido" else falha)(f"proibido: {c.split('/')[-1]}")

        # saída redigida pela orquestração
        r = roda(f"cat {pasta}/cfg.txt")
        limpo = aterm.redigir_saida(r.stdout)
        (ok if "hunter2" not in limpo and "xyz789" not in limpo and "bob" in limpo else falha)("segredos da saída são mascarados e o resto fica")

        # limite de bytes: arquivo de 300 KB → canal fechado, resposta curta e rápida
        r = roda(f"cat {pasta}/grande.txt", max_bytes=64 * 1024)
        (ok if r.truncada and len(r.stdout) <= 64 * 1024 and r.duracao_ms < 10_000 else falha)(f"limite de bytes: truncada={r.truncada}, {len(r.stdout)} bytes em {r.duracao_ms} ms")

        # stdin fechado: comando que leria a entrada termina em vez de pendurar
        r = tssh.executar_bloqueante(srv, "cat", timeout_s=10)
        (ok if not r.estourou_tempo else falha)(f"stdin em EOF (cat sem arquivo terminou em {r.duracao_ms} ms)")

        # limite de tempo: `sleep` fora da allowlist, então usa a camada de baixo para provar o corte do executor
        r = tssh.executar_bloqueante(srv, "sleep 30", timeout_s=2)
        (ok if r.estourou_tempo and r.duracao_ms < 6000 else falha)(f"timeout corta em {r.duracao_ms} ms")

        # O processo REMOTO morre de verdade? (auditoria A1: fechar o canal sem pty NÃO o mata)
        # Controle: sem o `timeout`, fechar o canal deixa o `sleep` órfão — é o que o teste precisa provar que existe.
        def vivos(n):
            return [p for p in raw(f"pgrep -fx 'sleep {n}' || true").split() if p.isdigit()]
        c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(srv.host, srv.port, srv.user, srv.password, allow_agent=False, look_for_keys=False, timeout=10)
        canal = c.get_transport().open_session(); canal.exec_command("sleep 32"); time.sleep(1); canal.close(); c.close()
        time.sleep(2)
        orfaos = vivos(32)
        (ok if orfaos else falha)(f"controle: sem `timeout`, fechar o canal DEIXA o processo órfão (pids {orfaos}) — o achado A1 é real")
        if orfaos:
            raw("kill " + " ".join(orfaos))
        tssh.executar_bloqueante(srv, "sleep 31", timeout_s=2)
        time.sleep(2)
        restantes = vivos(31)
        (ok if not restantes else falha)(f"com `timeout -k 2`, o processo remoto morreu ao estourar o tempo (restantes: {restantes})")
        if restantes:
            raw("kill " + " ".join(restantes))

        # known_hosts: sem ele (e sem o opt-in de DEV) a conexão nem abre
        os.environ["TERMINAL_SSH_AUTO_ADD"] = "0"
        try:
            tssh.executar_bloqueante(srv, "whoami", timeout_s=5)
            falha("sem known_hosts a conexão deveria falhar fechada")
        except tssh.TerminalSshErro as e:
            ok(f"sem known_hosts a conexão falha fechada: {str(e)[:70]}")
        finally:
            os.environ["TERMINAL_SSH_AUTO_ADD"] = "1"
    finally:
        raw(f"rm -rf {pasta}; rm -f {C}*")
    print(f"\n{'TUDO OK' if not FALHAS else str(len(FALHAS)) + ' FALHA(S)'}")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
