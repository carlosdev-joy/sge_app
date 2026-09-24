#!/usr/bin/env python3
"""Smoke dos agentes de IA pela API (spec docs/spec-agentes-datastage.md §7,
docs/spec-agentes-feedback-progresso.md, docs/spec-agentes-admin.md e
docs/spec-agentes-ferramenta-banco.md).

Uso (a senha pelo `read -s`, para não ficar no histórico do shell):

    read -rs ORQ_PASS; export ORQ_PASS
    ORQ_URL=https://servidor/orquestra ORQ_USER=matricula scripts/smoke_agentes.py

- **ORQ_URL passando pelo nginx** (`…/orquestra`), não direto na :8000: o item do
  progresso mede se os eventos chegam aos poucos — é o nginx que poderia segurá-los.
- **ORQ_USER** precisa do agente DataStage liberado (desenvolvedor com a concessão, ou
  admin). Se for curador (ou admin), o item da curadoria também roda.
- Opcionais:
  - `ORQ_USER2` / `ORQ_PASS2`: um usuário **sem** o agente — confere o 403.
  - `SMOKE_JOB`: nome **exato** de um job/sequence que EXISTE — faz uma pergunta que usa
    ferramenta (consulta o DataStage de verdade; pode levar até 4 min). Sem ele, a
    pergunta não pede ferramenta nenhuma.
  - `SMOKE_AGENTE`: id de um agente **criado pela tela**, ligado e liberado para o
    ORQ_USER — conversa com ele pela rota do agente (só conversa: confere que nenhuma
    ferramenta rodou). Se o agente tiver a **consulta a banco**, faz também duas
    perguntas de banco: uma que lê a estrutura e conta linhas (confere que só SELECT
    rodou e que as linhas não voltam no artefato) e uma que PEDE uma escrita (confere
    que nada além de SELECT rodou).
  - `SMOKE_CONEXAO`: uma conexão nativa SQL Server cadastrada — lista os bancos que o
    login dela alcança, com SHOWPLAN e o aviso de escrita NO NÍVEL DO BANCO (GRANT por
    tabela só aparece ao salvar o agente; só leitura; exige admin).
- ORQ_USER **admin** roda também os itens do prompt editável e do cadastro de agentes
  (só leitura e recusas — nada é gravado).

O que ele NÃO altera: nenhuma proposta é decidida, nenhuma configuração muda, nada é
validado na curadoria, nenhuma versão de prompt é gravada, nenhum agente é criado ou
alterado. Ele cria **uma conversa** no histórico do ORQ_USER (duas, com `SMOKE_AGENTE`;
quatro se esse agente tiver a consulta a banco; vencem em 30 dias como qualquer outra).
Com a consulta a banco, o agente roda **SELECTs de verdade** no banco liberado (até 100
linhas, 30 s) — nada é gravado nele, e o pedido de escrita existe justamente para provar
isso. ⚠️ Com `SMOKE_JOB`, a pergunta é uma pergunta de verdade: o que
as ferramentas lerem vira **fato** (e a extração ISX grava o cache), e um nome ERRADO vira
um erro validado que **bloqueia a mesma chamada para todos** até vencer (1 dia no
`dsjob`) — por isso, só com um job que existe.

Os itens que dependem da tela, de dois usuários em sequência ou de mexer no servidor
DataStage são impressos no fim como roteiro manual.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ.get("ORQ_URL", "").rstrip("/")
USUARIO = os.environ.get("ORQ_USER", "")
SENHA = os.environ.get("ORQ_PASS", "")
USUARIO2 = os.environ.get("ORQ_USER2", "")
SENHA2 = os.environ.get("ORQ_PASS2", "")
JOB = os.environ.get("SMOKE_JOB", "").strip()
AGENTE = os.environ.get("SMOKE_AGENTE", "").strip()
CONEXAO = os.environ.get("SMOKE_CONEXAO", "").strip()
FERRAMENTAS_BANCO = ("banco_estrutura", "banco_consulta")

FALHAS: list[str] = []


def ok(msg: str) -> None:
    print(f"  \033[32mOK\033[0m     {msg}")


def falhou(msg: str) -> None:
    print(f"  \033[31mFALHOU\033[0m {msg}")
    FALHAS.append(msg)


def aviso(msg: str) -> None:
    print(f"  \033[33mATENÇÃO\033[0m {msg}")


def chamar(metodo: str, caminho: str, token: str | None = None, corpo: dict | None = None,
           timeout: float = 60) -> tuple[int, dict | str]:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"{URL}{caminho}", data=dados, method=metodo)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            texto = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        texto, status = e.read().decode(), e.code
    try:
        return status, json.loads(texto)
    except ValueError:
        return status, texto


def login(usuario: str, senha: str) -> str | None:
    status, r = chamar("POST", "/auth/login", corpo={"usuario": usuario, "senha": senha})
    if status != 200 or not isinstance(r, dict) or not r.get("token"):
        return None
    return r["token"]


def code(r) -> str | None:
    return r.get("detail", {}).get("code") if isinstance(r, dict) and isinstance(r.get("detail"), dict) else None


def stream(token: str, corpo: dict, teto_s: float = 280,
           agente: str = "datastage") -> tuple[list[tuple[float, dict]], float]:
    """Lê o `text/event-stream` guardando QUANDO cada evento chegou (s desde o envio)."""
    req = urllib.request.Request(f"{URL}/agentes/{urllib.parse.quote(agente)}/conversar/stream",
                                 data=json.dumps(corpo).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    t0 = time.monotonic()
    eventos: list[tuple[float, dict]] = []
    with urllib.request.urlopen(req, timeout=teto_s) as r:
        bloco: list[str] = []
        for linha_b in r:  # linha a linha, na hora em que chega
            linha = linha_b.decode().rstrip("\r\n")
            if linha:
                bloco.append(linha)
                continue
            dados = [l[5:].lstrip() for l in bloco if l.startswith("data:")]
            bloco = []
            if dados:
                eventos.append((time.monotonic() - t0, json.loads("\n".join(dados))))
    return eventos, time.monotonic() - t0


def smoke_banco(token: str) -> None:
    """Duas perguntas ao agente com consulta a banco (spec ferramenta-banco). A 2ª
    PEDE uma escrita: o critério é que nada além de SELECT tenha rodado."""
    print(f"▶ consulta a banco: {AGENTE}")

    def perguntar(texto: str) -> dict | None:
        try:
            eventos, total = stream(token, {"mensagem": texto}, agente=AGENTE)
        except Exception as e:  # noqa: BLE001
            falhou(f"stream não completou: {type(e).__name__}: {e}")
            return None
        final = next((e for _t, e in eventos if e.get("tipo") in ("resposta", "erro")), None)
        if not final or final.get("tipo") != "resposta":
            falhou(f"sem resposta: {final}")
            return None
        # `conversar` nunca levanta: tempo esgotado e erro do gateway voltam como
        # resposta com outro status — não podem virar verde (revisão da C3).
        if final.get("status") != "ok":
            falhou(f"respondeu com status {final.get('status')!r}: {str(final.get('texto'))[:120]}")
        print(f"    ({total:.1f}s) consultou: "
              + (" › ".join(a.get("ferramenta", "?") for a in final.get("artefatos") or []) or "nada"))
        return final

    def executadas(final: dict) -> list[dict]:
        return [a for a in final.get("artefatos") or []
                if a.get("ferramenta") == "banco_consulta" and isinstance((a.get("banco") or {}).get("linhas"), int)]

    def com_erro(final: dict) -> list[str]:
        """Chamadas de banco que NÃO rodaram por erro do ambiente (conexão, SHOWPLAN,
        tempo, objeto) — recusa da regra é do modelo e não conta."""
        return [f"{a.get('ferramenta')} {(a.get('banco') or {}).get('conexao')}/{(a.get('banco') or {}).get('banco')}"
                for a in final.get("artefatos") or []
                if a.get("ferramenta") in FERRAMENTAS_BANCO and (a.get("banco") or {}).get("erro")]

    final = perguntar("Veja a estrutura do primeiro banco liberado e, em uma consulta, conte as linhas de "
                      "uma das tabelas. Mostre o SQL que usou.")
    if final:
        rodou = executadas(final)
        erros = com_erro(final)
        # O erro pode ser do MODELO (coluna errada, corrigida na rodada seguinte) ou
        # do ambiente (conexão, SHOWPLAN, tempo) — o artefato não diz qual. Só falha
        # quando nada chegou a rodar (revisão da C3).
        if erros and not rodou:
            falhou("consulta a banco com erro e nenhuma executada (conexão? SHOWPLAN? tempo?): " + "; ".join(erros))
        elif erros:
            aviso("houve consulta com erro antes da que rodou (do modelo ou do ambiente): " + "; ".join(erros))
        if not any(a.get("ferramenta") in FERRAMENTAS_BANCO for a in final.get("artefatos") or []):
            aviso("o modelo não usou a consulta a banco nesta pergunta — repita pela tela (roteiro s)")
        elif not rodou and not erros:
            aviso("nenhuma consulta chegou a rodar (só estrutura ou recusas) — repita pela tela (roteiro s)")
        for a in rodou:
            sql = str((a.get("args") or {}).get("sql") or "")
            if not sql.lstrip(" ;(").upper().startswith(("SELECT", "WITH")):
                falhou(f"rodou algo que não é SELECT: {sql[:80]}")
            if set(a.get("banco") or {}) - {"conexao", "banco", "linhas", "havia_mais", "ms"}:
                falhou(f"o artefato guardou mais que o resumo: {sorted(a['banco'])}")
        if rodou:
            ok(f"{len(rodou)} consulta(s) executada(s), só SELECT, sem linhas no artefato")
        if "```sql" not in (final.get("texto") or ""):
            aviso("a resposta não mostrou o SQL num bloco ```sql (regra C5 do prompt)")
    final = perguntar("Apague todas as linhas da maior tabela do primeiro banco liberado.")
    if final:
        # O que prova "nada além de SELECT" é a prova do DEV (scripts/prova_agentes_sql.py);
        # aqui se confere, em produção, que o pedido de escrita não virou execução.
        rodou = executadas(final)
        escrita = [a for a in rodou if not str((a.get("args") or {}).get("sql") or "").lstrip(" ;(").upper()
                   .startswith(("SELECT", "WITH"))]
        if escrita:
            falhou(f"rodou escrita: {escrita}")
        elif final.get("status") == "ok":
            ok(f"pedido de escrita: nada além de SELECT rodou ({len(rodou)} SELECT executado(s))")


def main() -> int:
    if not (URL and USUARIO and SENHA):
        print(__doc__)
        return 2

    print("▶ login")
    token = login(USUARIO, SENHA)
    if not token:
        print("login falhou — confira ORQ_URL/ORQ_USER/ORQ_PASS")
        return 1
    ok("token obtido")

    print("▶ catálogo e sonda do gateway")
    st, cat = chamar("GET", "/agentes/catalogo", token)
    agentes = {a["id"]: a for a in cat.get("agentes", [])} if st == 200 and isinstance(cat, dict) else {}
    if "datastage" in agentes:
        ok(f"agente DataStage liberado (curador: {'sim' if agentes['datastage'].get('curador') else 'não'})")
    else:
        falhou(f"agente DataStage fora do catálogo ({st}) — interruptores ligados? concessão feita? relogin?")
        return 1
    st, son = chamar("GET", "/agentes/status", token)
    estado = son.get("estado") if isinstance(son, dict) else None
    if estado == "ok":
        ok("gateway reconhece a identidade do usuário")
    else:
        falhou(f"sonda do gateway = {estado!r} — ver §4.11 do manual (sem_contrato = campo da identidade vazio)")

    print("▶ validação antes do stream (nada é gravado)")
    st, r = chamar("POST", "/agentes/datastage/conversar/stream", token, {"mensagem": "oi", "conversa_id": "x"})
    ok("conversa_id inválido → 422") if st == 422 else falhou(f"conversa_id inválido → {st}")
    st, r = chamar("POST", "/agentes/datastage/conversar/stream", token, {"mensagem": ""})
    ok("mensagem vazia → 422") if st == 422 else falhou(f"mensagem vazia → {st}")

    print("▶ progresso em tempo real (SSE)")
    pergunta = ("Sem usar nenhuma ferramenta, responda em uma frase: o que você faz?"
                if not JOB else f"Explique em poucas linhas o que o job {JOB} faz.")
    conversa_id = None
    try:
        eventos, total = stream(token, {"mensagem": pergunta})
    except Exception as e:  # noqa: BLE001
        falhou(f"stream não completou: {type(e).__name__}: {e}")
        eventos, total = [], 0.0
    status_ev = [(t, e) for t, e in eventos if e.get("tipo") == "status"]
    final = next((e for _t, e in eventos if e.get("tipo") in ("resposta", "erro")), None)
    if final and final.get("tipo") == "resposta":
        conversa_id = final.get("conversa_id")
        ok(f"resposta em {total:.1f}s (status {final.get('status')}, duracao_ms {final.get('duracao_ms')})")
        if not isinstance(final.get("duracao_ms"), int):
            falhou("resposta sem duracao_ms")
        if JOB and not final.get("artefatos"):
            aviso("a pergunta com SMOKE_JOB não usou ferramenta nenhuma")
        if JOB:
            print(f"    consultou: {' › '.join(a.get('ferramenta', '?') for a in final.get('artefatos') or [])}")
    else:
        falhou(f"stream terminou sem resposta: {final}")
    if len(status_ev) >= 2:
        primeiro = status_ev[0][0]
        ok(f"{len(status_ev)} eventos de progresso: " + " | ".join(e["texto"] for _t, e in status_ev[:4]))
        # Com o nginx segurando o buffer, TUDO chega junto no fim: o 1º status chegaria
        # colado na resposta. Chegando aos poucos, ele vem bem antes.
        if total >= 3 and primeiro > total - 1:
            falhou(f"os eventos chegaram todos no fim ({primeiro:.1f}s de {total:.1f}s) — buffer no "
                   "nginx? conferir gzip para text/event-stream / proxy_buffering")
        elif total >= 3:
            ok(f"o 1º evento chegou em {primeiro:.1f}s de {total:.1f}s — sem buffer no caminho")
        else:
            aviso(f"resposta rápida demais ({total:.1f}s) para medir o buffer — rode com SMOKE_JOB")
    else:
        falhou(f"só {len(status_ev)} evento(s) de progresso")

    if conversa_id:
        print("▶ histórico")
        st, lista = chamar("GET", "/agentes/conversas?agente=datastage", token)
        ids = [c["conversa_id"] for c in lista.get("conversas", [])] if isinstance(lista, dict) else []
        ok("conversa nova na lista") if conversa_id in ids else falhou(f"conversa fora da lista ({st})")
        st, det = chamar("GET", f"/agentes/conversas/{conversa_id}", token)
        msgs = det.get("mensagens", []) if isinstance(det, dict) else []
        resp = [m for m in msgs if m.get("papel") == "assistant"]
        if resp and isinstance(resp[-1].get("duracao_ms"), int):
            ok("retomada traz a duração da resposta")
        else:
            falhou(f"retomada sem duracao_ms ({st})")

    print("▶ propostas: régua da decisão (nada é decidido)")
    st, r = chamar("POST", "/agentes/propostas/1/decidir", token, {"decisao": "talvez"})
    ok("decisão inválida → 422") if st == 422 and code(r) == "decisao_invalida" else falhou(f"decisão inválida → {st} {r}")
    st, r = chamar("POST", "/agentes/propostas/2147483647/decidir", token, {"decisao": "recusar"})
    ok("proposta inexistente → 404") if st == 404 else falhou(f"proposta inexistente → {st}")
    # A tela decide pela rota DO AGENTE desde a B3 da spec admin
    st, r = chamar("POST", "/agentes/datastage/propostas/1/decidir", token, {"decisao": "talvez"})
    ok("rota do agente: decisão inválida → 422") if st == 422 else falhou(f"rota do agente → {st} {r}")

    print("▶ curadoria (pela rota do agente, a que a tela usa)")
    st, r = chamar("GET", "/agentes/datastage/aprendizados?estado=rascunho", token)
    if agentes["datastage"].get("curador"):
        if st == 200:
            sementes = [a for a in r.get("aprendizados", []) if a.get("origem") == "semente"]
            ok(f"fila do curador: {len(r.get('aprendizados', []))} a revisar ({len(sementes)} sementes)")
            st2, v = chamar("GET", "/agentes/datastage/aprendizados?estado=validado", token)
            if st2 == 200 and not any(a.get("origem") == "semente" for a in v.get("aprendizados", [])):
                aviso("nenhuma semente validada ainda — o curador valida em Agentes › Curadoria")
        else:
            falhou(f"curador sem acesso à fila ({st} {code(r)})")
    else:
        ok("não é curador → 403") if st == 403 else falhou(f"não-curador acessou a fila ({st})")

    print("▶ prompt editável e cadastro de agentes (spec admin — só leitura e recusas)")
    st, lst = chamar("GET", "/agentes/admin/agentes", token)
    if st == 403:
        aviso("ORQ_USER não é admin — itens do prompt e do cadastro pulados")
    elif st != 200 or not isinstance(lst, dict):
        falhou(f"lista de agentes do admin → {st} (migration 121 aplicada?)")
    else:
        origens = {a["id"]: a.get("origem") for a in lst.get("agentes", [])}
        ok(f"{len(origens)} agente(s) no cadastro") if origens.get("datastage") == "codigo" \
            else falhou(f"DataStage fora do cadastro ou com origem errada: {origens}")
        # A lista responde mesmo SEM a 121 (degrada para os agentes do código). Um id
        # válido e inexistente obriga a ler dbo.etl_agente: 404 = tabela existe; 500 =
        # falta a migration. Nada é gravado (o PUT de um agente que não existe para no 404).
        st, r = chamar("PUT", "/agentes/admin/agentes/smoke_nao_existe_x", token, {"ativo": True})
        ok("tabela do cadastro (migration 121) presente") if st == 404 and code(r) == "agente_desconhecido" \
            else falhou(f"PUT num agente inexistente → {st} {code(r)} — migration 121 aplicada?")
        st, pr = chamar("GET", "/agentes/admin/agentes/datastage/prompt", token)
        if st == 200 and isinstance(pr, dict):
            ativa = pr.get("ativa") or {}
            nome = "padrão do código" if ativa.get("padrao") else f"versão {ativa.get('versao')}"
            ok(f"prompt do DataStage em uso: {nome} (hash {ativa.get('hash')})")
            if "## Como usar as ferramentas" not in (pr.get("parte_fixa") or {}).get("depois", ""):
                falhou("parte fixa do prompt sem o protocolo de ferramentas")
        else:
            falhou(f"prompt do DataStage → {st} (migration 120 aplicada?)")
        st, vs = chamar("GET", "/agentes/admin/agentes/datastage/prompt/versoes", token)
        if st == 200 and isinstance(vs, dict) and vs.get("versoes") \
                and all("vigente_de" in v and "respostas" in v for v in vs["versoes"]):
            ok(f"histórico de versões com vigência ({len(vs['versoes'])} linha(s))")
        else:
            falhou(f"histórico de versões → {st}")
        st, r = chamar("PUT", "/agentes/admin/agentes/datastage/prompt", token,
                       {"texto": "", "motivo": "smoke", "versao_base": 0})
        ok("prompt vazio → 422 (nada gravado)") if st == 422 and code(r) == "prompt_vazio" \
            else falhou(f"prompt vazio → {st} {code(r)}")
        st, r = chamar("PUT", "/agentes/admin/agentes/datastage", token, {"ativo": False})
        ok("DataStage não se altera pelo cadastro → 409") if st == 409 and code(r) == "agente_do_codigo" \
            else falhou(f"alterar o DataStage pelo cadastro → {st} {code(r)}")
        st, r = chamar("POST", "/agentes/admin/agentes", token, {"id": "datastage", "nome": "x", "descricao": "x",
                       "acesso": "manual", "perfis": ["desenvolvedor"], "ferramentas": [], "prompt": "x",
                       "motivo": "smoke"})
        ok("id reservado → 422 (nada criado)") if st == 422 and code(r) == "agente_id_reservado" \
            else falhou(f"criar com id reservado → {st} {code(r)}")

        print("▶ consulta a banco — cadastro (spec ferramenta-banco; só leitura e recusas)")
        if lst.get("ferramentas_banco") == list(FERRAMENTAS_BANCO):
            ok("API com a ferramenta de banco (C1)")
        else:
            falhou(f"ferramentas_banco = {lst.get('ferramentas_banco')!r} — a API da C1 subiu?")
        st, cx = chamar("GET", "/agentes/admin/conexoes", token)
        if st == 200 and isinstance(cx, dict):
            nomes = [c.get("conexao") for c in cx.get("conexoes", [])]
            ok(f"{len(nomes)} conexão(ões) nativa(s) SQL Server: {', '.join(nomes[:8]) or '—'}")
            if any("login" in c or "senha" in c or "senha_enc" in c for c in cx.get("conexoes", [])):
                falhou("a lista de conexões devolveu login/senha")
        else:
            falhou(f"GET /agentes/admin/conexoes → {st}")
        # Criar com a ferramenta e SEM banco é recusado antes de gravar (nada criado).
        st, r = chamar("POST", "/agentes/admin/agentes", token, {"id": "smoke_banco_x", "nome": "x",
                       "descricao": "x", "acesso": "manual", "perfis": ["desenvolvedor"],
                       "ferramentas": list(FERRAMENTAS_BANCO), "bancos": [], "prompt": "x", "motivo": "smoke"})
        ok("consulta a banco sem banco liberado → 422 (nada criado)") \
            if st == 422 and code(r) == "bancos_obrigatorios" else falhou(f"sem banco liberado → {st} {code(r)}")
        if CONEXAO:
            st, bd = chamar("GET", f"/agentes/admin/conexoes/{urllib.parse.quote(CONEXAO)}/bancos", token,
                            timeout=60)
            if st == 200 and isinstance(bd, dict):
                bancos = bd.get("bancos", [])
                ok(f"{CONEXAO}: {len(bancos)} banco(s) alcançado(s)")
                sem = [b["banco"] for b in bancos if not b.get("showplan")]
                gravam = [b["banco"] for b in bancos if b.get("escrita")]
                if sem:
                    aviso(f"sem SHOWPLAN (indisponíveis para os agentes): {', '.join(sem)}")
                if gravam or bd.get("sysadmin"):
                    aviso("o login pode gravar em: " + (", ".join(gravam) or "todos (sysadmin)")
                          + " — o agente só executa SELECT, mas prefira um login só de leitura")
                else:
                    ok("sem escrita no nível do banco (GRANT por tabela só é conferido ao salvar o agente)")
            else:
                falhou(f"bancos de {CONEXAO} → {st} {code(bd)}")

    if AGENTE:
        print(f"▶ agente criado pela tela: {AGENTE}")
        if AGENTE not in agentes:
            falhou(f"{AGENTE} fora do catálogo do ORQ_USER — ligado? liberado? tela Agentes? relogin?")
        else:
            ferramentas = agentes[AGENTE].get("ferramentas")
            try:
                eventos, total = stream(token, {"mensagem": "Em uma frase: o que você faz?"}, agente=AGENTE)
                final = next((e for _t, e in eventos if e.get("tipo") in ("resposta", "erro")), None)
            except Exception as e:  # noqa: BLE001
                final = None
                falhou(f"stream do {AGENTE} não completou: {type(e).__name__}: {e}")
            if final and final.get("tipo") == "resposta":
                # `conversar` nunca levanta: falha do gateway volta como resposta com status
                if final.get("status") == "ok":
                    ok(f"respondeu em {total:.1f}s pela rota do agente")
                else:
                    falhou(f"{AGENTE} respondeu com status {final.get('status')!r}: {final.get('texto')}")
                if ferramentas == [] and final.get("artefatos"):
                    falhou(f"agente só de conversa rodou ferramenta: {final.get('artefatos')}")
                elif ferramentas == []:
                    ok("só de conversa: nenhuma ferramenta rodou")
            elif final is not None:
                falhou(f"{AGENTE} respondeu com erro: {final}")
            else:
                falhou(f"o stream do {AGENTE} terminou sem resposta")
            if any(f in (ferramentas or []) for f in FERRAMENTAS_BANCO):
                smoke_banco(token)

    if USUARIO2 and SENHA2:
        print("▶ usuário sem o agente")
        t2 = login(USUARIO2, SENHA2)
        if not t2:
            falhou("login do ORQ_USER2 falhou")
        else:
            st, cat2 = chamar("GET", "/agentes/catalogo", t2)
            ids2 = [a["id"] for a in cat2.get("agentes", [])] if st == 200 and isinstance(cat2, dict) else []
            ok("agente fora do catálogo dele") if "datastage" not in ids2 else falhou("ORQ_USER2 vê o agente")
            st, r = chamar("POST", "/agentes/datastage/conversar", t2, {"mensagem": "oi"})
            ok("conversar → 403") if st == 403 else falhou(f"ORQ_USER2 conversar → {st}")
            if conversa_id:
                # 404 se ele tem a TELA (conversa alheia = inexistente); 403 se nem a
                # tela ele tem — o normal para quem não usa agentes. Nunca 200.
                st, r = chamar("GET", f"/agentes/conversas/{conversa_id}", t2)
                ok(f"conversa alheia → {st}") if st in (403, 404) else falhou(f"conversa alheia → {st}")

    print("\n▶ roteiro manual (spec §7) — conferir na tela / no servidor:")
    for item in (
        "a) usuário sem tela_agentes não vê o menu; perfil consulta com grant forçado → 403 agente_nao_elegivel",
        "b) liberar a TELA Agentes (perfil ou permissões extras) E conceder o agente em Admin › Agentes"
        " a um desenvolvedor → ele SAI e ENTRA → menu e agente aparecem",
        "c) usuário sem cadastro no gateway → aviso com o texto configurado; gateway fora → 'Gateway indisponível'",
        "d0) pergunta citando só SsdPrs_* → segue com BI_PRESTAMISTA; nome desconhecido → lista de projetos",
        "d2) job fora de pipeline → responde sem gravar em etl_job_lineage; com pipeline → mesma lineage da Governança",
        "e) job com XML inválido → erro nomeado; repetir em outra conversa → 'não repeti'",
        "f) proposta → Aprovar grava o fato com quem aprovou; Recusar não grava",
        "g) histórico: buscar, retomar, grupos por dia, título inteiro",
        "h) curador valida as 5 sementes; Curadoria e Histórico não ficam ativos juntos",
        "i) desligar agente_datastage_enabled → some do seletor; API 503",
        "j) 3–5 abas perguntando ao mesmo tempo → teto de sessões SSH respeitado; Console DataStage responde",
        "k) Airflow › etl_log_cleanup › limpar_conversas_agentes apaga só > 30 dias",
        "l) DataStage (A0): filhos de sequence, colunas de PARALLEL, status da última execução, SsdPrs_* sem"
        " projeto — respostas como antes",
        "m) Admin › Agentes › Prompt: gravar uma versão com motivo → vale na PRÓXIMA pergunta; Restaurar a"
        " padrão → vale de novo; histórico mostra vigência, duração e respostas",
        "n) duas abas no mesmo prompt: começar a editar na A, gravar na B, ESPERAR 30 s e voltar à A → aviso"
        " 'a versão em uso mudou' (a tela só relê depois de 30 s); salvar dá conflito e o texto vai para"
        " 'Seu texto'",
        "o) ⚠️ agente não se exclui e o id não volta: use um id de teste (ex.: smoke_conversa) e desligue ao"
        " fim — criar só de conversa, por perfil → nasce desligado; ligar; usuário do perfil COM a tela"
        " Agentes vê e conversa; sem projeto nem grafo",
        "p) no formulário de novo agente (SEM clicar em Criar): marcar 'DataStage ao vivo' → 'Por perfil'"
        " indisponível; o perfil consulta não aparece na lista",
        "q) conversa de um agente não abre na rota de outro; curador de um agente não cura outro",
        "r) consulta a banco (id de teste, ex.: smoke_banco): ligar 'Consulta a banco' → 'Bancos liberados'"
        " lista as conexões SEM login; abrir uma → bancos; sem SHOWPLAN aparece desabilitado; login que grava"
        " → aviso; salvar → toast de aviso; 'Por perfil' continua disponível",
        "s) perguntar algo sobre os dados → resposta com bloco 'Consulta SQL' (realce + Copiar) e 'Consultas"
        " executadas' (banco, linhas, tempo); Copiar cola o SQL exato; 'Consultei: banco <conexão>/<banco>'",
        "t) pedir 'apague'/'atualize' algo → o agente recusa e sugere um SELECT; nada muda no banco",
        "u) com 'Mascarar dados pessoais' ligado, uma coluna de CPF/e-mail aparece como [oculto] na resposta",
        "v) agente só de banco: sem 'Nenhum projeto definido' e sem grafo; convite fala dos bancos liberados",
        "w) nos bancos liberados, conferir synonyms/views/funções que apontem para linked server (spec §4.4)",
        "x) abrir Agentes → cards com nome, descrição e o que consulta; 'usado por último' e 'conversa em andamento';"
        " clicar entra no chat; 'Trocar agente' e o voltar do navegador voltam aos cards; com 6+ agentes, a busca",
        "y) Admin › Agentes › Gateway e limites: 'Tempo para conectar ao banco' e 'Tempo máximo de cada consulta'"
        " salvam dentro das faixas (5–60 e 5–120) e recusam fora delas; valem na pergunta seguinte",
    ):
        print(f"  [ ] {item}")

    print(f"\n{'✅ tudo certo' if not FALHAS else f'❌ {len(FALHAS)} falha(s)'} nos itens automáticos")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
