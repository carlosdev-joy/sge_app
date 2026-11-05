"""api/services/agentes_terminal.py — auditoria do agente Terminal (F2 da spec
docs/spec-agente-terminal.md).

Uma linha em `dbo.etl_agente_terminal_cmd` por comando que o Claude PROPÕE ou executa:
leitura, escrita (com confirmação) e bloqueado. O que entra aqui já passa pela REDAÇÃO
(`agentes_ferramentas.redigir`) e é cortado pela largura da coluna em UTF-16
(`cortar_utf16`) — nunca segredo em claro. O hash é o do texto que o USUÁRIO VÊ no card de
confirmação (o redigido); a F4 só executa o que bate com ele.

Nada aqui decide se um comando é leitura ou escrita (F3) nem executa nada (F3/F4): é só o
registro e a consulta. Toda função recebe o cursor — quem chama abre/fecha a conexão
(padrão de `agentes_aprendizado`).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import shlex
import unicodedata
import uuid
from datetime import date, datetime, timedelta

from services import agentes_ferramentas as af
from services import agentes_terminal_classe as cls
from services import agentes_terminal_ssh as tssh
from services.ssh_arquivos import cortar_utf16

CLASSES = ("leitura", "escrita", "proibido")
ESTADOS = ("proposto", "executando", "executado", "falhou", "recusado", "expirado", "bloqueado")
# Estados em que o comando já não muda (a auditoria não os reabre).
ESTADOS_FINAIS = ("executado", "falhou", "recusado", "expirado", "bloqueado")

# Máquina de estados (a F3/F4 só anda por aqui):
#   registrar: escrita → proposto · leitura → executando · proibido → bloqueado (nasce final)
#   iniciar:   proposto → executando   (só dentro do prazo, atômico)
#   finalizar: executando → executado|falhou · proposto → recusado|expirado
NASCE_EM = {"escrita": "proposto", "leitura": "executando", "proibido": "bloqueado"}
DE_ONDE = {"executado": ("executando",), "falhou": ("executando",),
           "recusado": ("proposto",), "expirado": ("proposto",)}

# Larguras das colunas NVARCHAR (migration 153) — contam UTF-16.
MAX_COMANDO = 2000
MAX_MOTIVO = 500
MAX_SAIDA = 4000
VALIDADE_PROPOSTA_S = 120  # 2 min: o card de confirmação expira

LIMITE_PADRAO = 50
LIMITE_MAX = 200


log = logging.getLogger(__name__)


class AuditoriaInvalida(ValueError):
    """Entrada recusada (classe/estado fora do conjunto, data inválida...)."""


_MASCARA = "••••"

# Formas de segredo de LINHA DE COMANDO (o `af.redigir` é feito para SAÍDA — "campo: valor" — e, num comando,
# engole tudo depois de uma palavra como "token": `grep -r token /opt` virava inutilizável; por isso NÃO é
# usado aqui). Cada regex mantém o prefixo (grupo 1) e mascara só o valor. Valor = entre aspas OU até o
# espaço. Conservador: na dúvida mascara — comando com segredo nunca é executado (ver `registrar`), então
# falso positivo vira só "bloqueado". `-p` NÃO é tratado em geral (é "porta"/"parents"/`-print`): só nos
# clientes que o usam como senha (mysql*, mariadb), em `sshpass` e em `docker login`; `-P` em sqlcmd/bcp.
_V = r"""(?:"[^"]*"|'[^']*'|[^\s'"]+)"""
# Palavra-chave de segredo dentro de um NOME (DB_PASS, KEY_PASSWORD, private_key…). Limites `{0,40}` nos dois lados e
# `{0,200}` nos "tudo até aqui" (`[^|;&\n]{0,200}?`): sem limite, cada ocorrência da palavra-chave varria a linha inteira
# e uma linha de 64 KB travava a API por 7–18 s (auditoria da F3, 1ª e 2ª rodadas).
_NOME_SEGREDO = (r"[A-Za-z0-9_]{0,40}(?:pass(?:word|wd|phrase)?|pwd|senha|secret|token|api[_-]?key|credential|private[_-]?key|"
                 r"access[_-]?key|fernet|session[_-]?id)[A-Za-z0-9_]{0,40}")
_ASPA = r"""["']?"""  # a chave pode vir entre aspas (JSON/YAML): "db_pass": "x"
_PADROES_SEGREDO = (
    re.compile(r"(?i)(://[^/\s:@]+:)[^/\s]+(@)"),                                        # url user:senha@host (senha pode ter @)
    re.compile(r"(?i)(\bbearer\s+)" + _V),                                              # Authorization: Bearer X
    re.compile(r"(?i)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-[a-z-]{0,30}(?:auth|token|key|secret)[a-z-]{0,30})\s*[:=]\s*)(?!bearer\b)[^'\"\n]+"),
    re.compile(r"(?i)(\b" + _NOME_SEGREDO + _ASPA + r"\s*:\s*)" + _V),                    # "password: x", "DB_PASS": "x" (YAML/JSON/cabeçalho)
    re.compile(r"(?i)(\b" + _ASPA + r"auth" + _ASPA + r"\s*[:=]\s*)" + _V),                # "auth": "<base64>" (~/.docker/config.json)
    re.compile(r"(?i)(\s(?:-u|--user|--basic-auth)[\s=]+[^\s:'\"]+:)\S+"),                  # curl -u user:senha (até o fim do token)
    re.compile(r"(?i)(--[a-z0-9-]{0,30}(?:password|passwd|pass|pwd|token|secret|api-?key|credential)[a-z0-9-]{0,30}(?:=|\s+))" + _V),  # --db-pass x
    re.compile(r"(?i)(\b(?:mysql|mysqldump|mysqladmin|mysqlcheck|mariadb)\b[^|;&\n]{0,200}?\s-p)(?=[^\s=/-])" + _V),  # mysql -pSENHA
    re.compile(r"(\b(?:sqlcmd|bcp)\b[^|;&\n]{0,200}?\s-P\s*)" + _V),                       # sqlcmd -P SENHA
    re.compile(r"(?i)(\bsshpass\s+-p\s*)" + _V),                                          # sshpass -p SENHA
    re.compile(r"(?i)(\blogin\b[^|;&\n]{0,200}?\s-p\s+)" + _V),                            # docker login -p SENHA
    re.compile(r"(?i)(\b" + _NOME_SEGREDO + _ASPA + r"\s*=\s*)" + _V),                    # KEY_PASS=x, fernet_key = x
    # Connection strings: "Server=h;Password=x;" / "pwd=x"
    re.compile(r"(?i)(\b(?:password|pwd)\s*=\s*)[^;\s'\"]+"),
)
# Formas pelo FORMATO do valor (a saída de logs/arquivos traz isso sem palavra-chave por perto).
_FORMATOS_SEGREDO = (
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{0,}"),               # JWT
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                                               # chave de acesso AWS
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),                                              # token GitHub
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),                                               # token GitHub (fine-grained)
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),                                                   # token GitLab
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),                                               # token Slack
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),                                                      # chave OpenAI/Anthropic
    re.compile(r"\bhvs\.[A-Za-z0-9_-]{20,}"),                                                   # token do Vault
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),                                                     # chave de API Google
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),                                                       # token npm
    # Chave privada: corpo inteiro até o END, OU (saída cortada, sem END) até 8 KB depois do cabeçalho. UM padrão com alternância:
    # a tentativa que falha o END consome o trecho no fallback, então N cabeçalhos repetidos custam ~N/8192 varreduras, não N
    # (com dois padrões separados, 2200 cabeçalhos em 64 KB levavam 1,2 s).
    re.compile(r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY-----(?:[\s\S]{0,8192}?-----END [A-Z ]{0,30}PRIVATE KEY-----|[\s\S]{0,8192})"),
    re.compile(r"PuTTY-User-Key-File-\d:[\s\S]{0,8192}?Private-MAC:[ \t]*\S{0,200}"),              # chave PuTTY (.ppk)
)
# Valor na LINHA SEGUINTE ("password:\n  hunter2"; block scalar `password: |`; "- name: DB_PASSWORD\n  value: hunter2") — só na saída.
_MULTILINHA_SEGREDO = (
    re.compile(r"(?im)^([ \t-]{0,20}" + _ASPA + _NOME_SEGREDO + _ASPA + r"[ \t]*[:=][ \t]*(?:[|>][-+]?[ \t]*)?\n(?:[ \t]*\n){0,3}[ \t]+)\S[^\n]{0,500}"),
    re.compile(r"(?im)(\bname[ \t]*:[ \t]*" + _NOME_SEGREDO + r"[ \t]*\n[ \t-]{0,20}value[ \t]*:[ \t]*)[^\n]{1,500}"),
)
MAX_LINHA_SAIDA = 8192  # linha maior que isto é cortada ANTES da redação (defesa extra contra regex lenta em linha gigante)


def redigir_comando(comando: str) -> str:
    """Mascara segredos de LINHA DE COMANDO (ver `_PADROES_SEGREDO`)."""
    t = comando
    for rx in _PADROES_SEGREDO:
        t = rx.sub(lambda m: m.group(1) + _MASCARA + (m.group(2) if m.lastindex and m.lastindex >= 2 else ""), t)
    return t


def _limpo(valor: str) -> str:
    """NFC e sem surrogate solto (`"\\ud83d"` vindo de JSON quebraria o `.encode`): o que se grava é
    exatamente o que se hasheia."""
    return unicodedata.normalize("NFC", str(valor)).encode("utf-8", "replace").decode("utf-8")


def _texto(valor: str | None, largura: int) -> str | None:
    """Redigido (campos "nome: valor"), normalizado e cortado pela largura da coluna em UTF-16."""
    if valor is None:
        return None
    return cortar_utf16(_limpo(af.redigir(_limpo(valor))), largura)


def preparar_comando(comando: str) -> tuple[str, str, bool]:
    """(texto que será gravado e MOSTRADO ao usuário, SHA-256 dele, `redigido`). O hash cobre o texto
    já redigido e cortado: é exatamente o que o card de confirmação exibe. `redigido=True` quer dizer
    que o texto MOSTRADO difere do pedido (havia segredo): esse comando não pode ser executado."""
    original = _limpo((comando or "").strip())
    if not original:
        raise AuditoriaInvalida("comando vazio")
    redigido_txt = redigir_comando(original)
    texto = cortar_utf16(_limpo(redigido_txt), MAX_COMANDO)
    return texto, hashlib.sha256(texto.encode("utf-8")).hexdigest(), redigido_txt != original


def registrar(cur, *, conversa_id: str | None, matricula: str, servidor: str, comando: str,
              classe: str, motivo: str | None = None, ip: str | None = None) -> dict:
    """Grava o comando no estado em que a CLASSE manda nascer (`NASCE_EM`) e devolve
    `{cmd_id, hash, comando, estado, redigido, validade_s}`. Não faz commit.

    Regras (o QA da F2 pediu a máquina fechada): o estado inicial vem da classe — o chamador não escolhe;
    comando que teve SEGREDO redigido só pode ser registrado como `proibido`/`bloqueado` (o texto
    mostrado não é o pedido, então executá-lo ou "confirmá-lo" seria mentir ao usuário). Os horários
    vêm do RELÓGIO DO BANCO (`GETDATE()`): o da API anda horas fora no DEV (medido em
    `services/malha_corrida.py`) e a janela de 2 min precisa comparar com o mesmo relógio que o `iniciar`."""
    if classe not in CLASSES:
        raise AuditoriaInvalida(f"classe inválida: {classe!r}")
    if not (matricula or "").strip():
        raise AuditoriaInvalida("matrícula obrigatória")
    texto, h, redigido = preparar_comando(comando)
    if redigido and classe != "proibido":
        raise AuditoriaInvalida("o comando contém segredo: só pode ser registrado como proibido")
    estado = NASCE_EM[classe]
    cmd_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dbo.etl_agente_terminal_cmd "
        "(cmd_id, conversa_id, matricula, servidor, comando, hash, classe, estado, motivo, ip, redigido, criado_em, expira_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), "
        "CASE WHEN ? = 'proposto' THEN DATEADD(second, ?, GETDATE()) ELSE NULL END)",
        [cmd_id, conversa_id, matricula.strip()[:20], (servidor or "")[:60], texto, h, classe, estado,
         _texto(motivo, MAX_MOTIVO), (ip or None) and ip[:45], 1 if redigido else 0, estado, VALIDADE_PROPOSTA_S])
    return {"cmd_id": cmd_id, "hash": h, "comando": texto, "estado": estado, "redigido": redigido,
            "validade_s": VALIDADE_PROPOSTA_S if estado == "proposto" else None}


def _uuid(cmd_id: str) -> str:
    try:
        return str(uuid.UUID(str(cmd_id)))
    except (ValueError, AttributeError, TypeError) as e:
        raise AuditoriaInvalida("cmd_id inválido") from e


def iniciar(cur, cmd_id: str, decidido_por: str) -> bool:
    """`proposto → executando`, ATÔMICO e só dentro do prazo (`expira_em > GETDATE()`): é o único
    caminho que a F4 usa para liberar a execução. `False` se já foi decidido/expirou (duplo clique,
    replay, prazo vencido). Quem decide é gravado aqui. Não faz commit."""
    if not (decidido_por or "").strip():
        raise AuditoriaInvalida("decidido_por obrigatório")
    cur.execute(
        "UPDATE dbo.etl_agente_terminal_cmd SET estado = 'executando', decidido_por = ?, decidido_em = GETDATE() "
        "WHERE cmd_id = ? AND estado = 'proposto' AND classe = 'escrita' AND redigido = 0 AND expira_em > GETDATE()",
        [decidido_por.strip()[:20], _uuid(cmd_id)])
    return cur.rowcount == 1


def finalizar(cur, cmd_id: str, estado: str, *, decidido_por: str | None = None, codigo_saida: int | None = None,
              duracao_ms: int | None = None, saida: str | None = None) -> bool:
    """Leva o comando ao estado final `estado`, só a partir dos estados permitidos (`DE_ONDE`):
    executando → executado|falhou; proposto → recusado|expirado. `False` se o comando não está num deles
    (já final, replay, nunca iniciado). `recusado` grava quem recusou. Não faz commit."""
    if estado not in DE_ONDE:
        raise AuditoriaInvalida(f"estado final inválido: {estado!r}")
    de = DE_ONDE[estado]
    marcas = ",".join("?" for _ in de)
    cur.execute(
        "UPDATE dbo.etl_agente_terminal_cmd SET estado = ?, codigo_saida = ?, duracao_ms = ?, saida_resumo = ?, "
        "decidido_por = COALESCE(?, decidido_por), "
        "decidido_em = CASE WHEN ? = 'recusado' THEN GETDATE() ELSE decidido_em END, "
        "executado_em = CASE WHEN ? IN ('executado','falhou') THEN GETDATE() ELSE executado_em END "
        f"WHERE cmd_id = ? AND estado IN ({marcas})",
        [estado, codigo_saida, duracao_ms, _texto(saida, MAX_SAIDA),
         (decidido_por or "").strip()[:20] or None, estado, estado, _uuid(cmd_id), *de])
    return cur.rowcount == 1


def _data(valor, rotulo: str, *, fim: bool = False) -> datetime | None:
    if valor in (None, ""):
        return None
    try:
        d = valor if isinstance(valor, (date, datetime)) else date.fromisoformat(str(valor)[:10])
    except ValueError as e:
        raise AuditoriaInvalida(f"{rotulo} inválida (use AAAA-MM-DD)") from e
    base = datetime(d.year, d.month, d.day)
    return base + timedelta(days=1) if fim else base  # `ate` é inclusivo: < dia seguinte


def listar(cur, *, matricula: str | None = None, estado: str | None = None, classe: str | None = None,
           desde=None, ate=None, limite: int = LIMITE_PADRAO, offset: int = 0) -> dict:
    """Consulta da auditoria (admin), mais recentes primeiro. Filtros combinados com AND; entrada
    inválida levanta `AuditoriaInvalida` ANTES de tocar o banco. `limite` fica em 1..LIMITE_MAX."""
    if estado and estado not in ESTADOS:
        raise AuditoriaInvalida(f"estado inválido: {estado!r}")
    if classe and classe not in CLASSES:
        raise AuditoriaInvalida(f"classe inválida: {classe!r}")
    d0, d1 = _data(desde, "data inicial"), _data(ate, "data final", fim=True)
    limite = max(1, min(int(limite), LIMITE_MAX))
    offset = max(0, int(offset))
    onde, args = [], []
    for coluna, valor in (("matricula", (matricula or "").strip() or None), ("estado", estado or None),
                          ("classe", classe or None)):
        if valor:
            onde.append(f"{coluna} = ?")
            args.append(valor)
    if d0:
        onde.append("criado_em >= ?")
        args.append(d0)
    if d1:
        onde.append("criado_em < ?")
        args.append(d1)
    filtro = (" WHERE " + " AND ".join(onde)) if onde else ""
    try:
        varrer_interrompidos(cur)  # a consulta do admin nunca mostra "em andamento"/"aguardando" eterno (best-effort)
        varrer_propostas_vencidas(cur)
    except Exception:  # noqa: BLE001
        pass
    cur.execute(f"SELECT COUNT(*) FROM dbo.etl_agente_terminal_cmd{filtro}", args)
    total = int(cur.fetchone()[0])
    cur.execute(
        "SELECT cmd_id, conversa_id, matricula, servidor, comando, classe, estado, motivo, codigo_saida, "
        "duracao_ms, saida_resumo, ip, criado_em, decidido_por, decidido_em, executado_em "
        f"FROM dbo.etl_agente_terminal_cmd{filtro} ORDER BY criado_em DESC, cmd_id "
        "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", [*args, offset, limite])
    chaves = ("cmd_id", "conversa_id", "matricula", "servidor", "comando", "classe", "estado", "motivo",
              "codigo_saida", "duracao_ms", "saida_resumo", "ip", "criado_em", "decidido_por", "decidido_em",
              "executado_em")
    itens = []
    for r in cur.fetchall():
        item = dict(zip(chaves, r))
        item["cmd_id"] = str(item["cmd_id"])
        for k in ("criado_em", "decidido_em", "executado_em"):
            item[k] = item[k].isoformat() if item[k] else None
        itens.append(item)
    return {"total": total, "limite": limite, "offset": offset, "itens": itens}


# ═══════════ Ferramenta `servidor_exec` (F3): LEITURA no servidor ═══════════
#
# Fluxo: classificar (determinístico, `agentes_terminal_classe`) → AUDITAR → executar → finalizar.
#   • leitura  → registra `executando`, roda os TOKENS re-citados, finaliza `executado`/`falhou`;
#   • proibido → registra `bloqueado` (nunca roda);
#   • escrita  → NÃO roda e NÃO registra `proposto` (a confirmação é a F4; sem a rota de confirmar e sem
#     quem expire propostas, uma linha `proposto` ficaria órfã). O modelo recebe o aviso.
# "Sem auditoria, sem execução": se o registro falhar (tabela ausente, banco fora), o comando NÃO roda.
# A saída passa por `af.redigir` (campos "nome: valor") e por `redigir_comando` (formas de linha de comando)
# ANTES de qualquer corte — a lição da 15ª rodada do dsjob — e só então pelos filtros em Python (o shell não
# tem pipe: grep/head/tail da saída são feitos aqui).

MAX_LINHAS_SAIDA = 2000
MAX_FILTRO = 100
TEXTO_SEM_ESCRITA = ("Este comando altera o servidor (ou não é um comando de leitura reconhecido) e a execução de comandos "
                     "que alteram o servidor não está liberada para este usuário (ou está desligada pelo administrador). "
                     "Não foi executado nem registrado. Use um comando de leitura (ls, cat, tail, head, grep, find, ps, df, "
                     "docker ps/logs, journalctl, airflow dags list…).")
MAX_PROPOSTAS_VIVAS = 5  # propostas `proposto` simultâneas por usuário (impede inundar a tela de cards)


def _inteiro(valor, minimo: int, maximo: int) -> int | None:
    """Inteiro dentro da faixa, ou None. `True`/`False`, `inf`/`nan` (o JSON do modelo aceita `Infinity`) e texto
    inválido NUNCA levantam — antes, `int(float('inf'))` estourava `OverflowError` DEPOIS do registro e deixava a linha
    de auditoria presa em `executando`."""
    if isinstance(valor, bool):
        return None
    try:
        n = int(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if minimo <= n <= maximo else None


def filtrar_saida(texto: str, *, filtrar: str | None = None, primeiras: int | None = None,
                  ultimas: int | None = None) -> tuple[str, int]:
    """(texto filtrado, linhas descartadas). `filtrar` é substring LITERAL, sem regex (nada de ReDoS) e sem
    diferenciar caixa; depois `primeiras`/`ultimas` (no máximo um dos dois)."""
    linhas = (texto or "").splitlines()
    total = len(linhas)
    if filtrar:
        alvo = filtrar.lower()
        linhas = [l for l in linhas if alvo in l.lower()]
    if primeiras:
        linhas = linhas[:primeiras]
    elif ultimas:
        linhas = linhas[-ultimas:]
    if len(linhas) > MAX_LINHAS_SAIDA:
        linhas = linhas[:MAX_LINHAS_SAIDA]
    return "\n".join(linhas), total - len(linhas)


def redigir_saida(texto: str) -> str:
    """Segredos fora da SAÍDA: campos "nome: valor" (`af.redigir`), formas de linha de comando que apareçam em `ps`,
    `docker ps`, logs… (`redigir_comando`), formatos conhecidos (JWT, AWS, GitHub, Slack, chave privada) e valores na
    linha seguinte. Sempre ANTES de cortar/filtrar. Entrada limitada a 128 KB (o executor já corta em 64 KB)."""
    t = (texto or "")[:131072]
    if any(len(l) > MAX_LINHA_SAIDA for l in t.split("\n")):
        t = "\n".join(l if len(l) <= MAX_LINHA_SAIDA else l[:MAX_LINHA_SAIDA] + " …[linha cortada]" for l in t.split("\n"))
    for rx in _MULTILINHA_SEGREDO:  # PRIMEIRO: `af.redigir` mascara a linha da palavra-chave e esconderia o padrão
        t = rx.sub(lambda m: m.group(1) + _MASCARA, t)
    # Os padrões DESTE módulo primeiro: `af.redigir` (feito para "campo: valor" de dsjob) engole o resto da linha e deixa a aspa
    # do valor sem fechar (`"db_pass":"x••••`), o que fazia o padrão de JSON deixar de casar. Depois dele, sobra a rede de segurança.
    t = af.redigir(redigir_comando(t))
    for rx in _FORMATOS_SEGREDO:
        t = rx.sub(_MASCARA, t)
    return t


def _gravar(abrir_conn, fn):
    """Conexão curta + commit; levanta se falhar (quem chama decide — aqui, falhar = não executar)."""
    conn, cur = abrir_conn()
    try:
        r = fn(cur)
        conn.commit()
        return r
    finally:
        for x in (cur, conn):
            try:
                x.close()
            except Exception:  # noqa: BLE001
                pass


def _resposta(comando: str, servidor: str, res: tssh.ResultadoExec | None, corpo: str, descartadas: int = 0) -> str:
    cab = f"$ {comando}\n[servidor: {servidor}"
    if res is not None:
        cab += f" · código de saída: {res.exit_code if res.exit_code is not None else 'n/d'} · {res.duracao_ms} ms"
    cab += "]"
    notas = []
    if res is not None and (res.estourou_tempo or res.exit_code in (124, 137)):
        notas.append(f"[interrompido: passou do limite de {tssh.TIMEOUT_PADRAO_S} s]")
    if res is not None and res.truncada:
        notas.append("[saída cortada no servidor: passou do limite de tamanho]")
    if descartadas:
        notas.append(f"[{descartadas} linha(s) fora do filtro/limite]")
    return "\n".join([cab, af._truncar(corpo), *notas]).strip()


async def ferramenta_servidor_exec(abrir_conn, args: dict, *, matricula: str | None, conversa_id: str | None,
                                   ssh_max: int, espera_max_s: float, pode_escrever: bool = False) -> dict:
    """Executa UM comando de LEITURA no servidor pedido. Devolve `{"texto": ...}` para o modelo; nunca levanta
    por regra de negócio (recusas e falhas viram texto nomeado)."""
    matricula = (matricula or "").strip()
    if not matricula:
        return {"texto": "Não foi possível identificar o usuário desta conversa — comando não executado."}
    disponiveis = tssh.servidores()
    if not disponiveis:
        return {"texto": "Nenhum servidor está configurado para o Terminal nesta instância (peça ao administrador)."}
    pedido = str(args.get("servidor") or "").strip().lower() or next(iter(disponiveis))
    srv = disponiveis.get(pedido)
    if srv is None:
        return {"texto": f"Servidor '{pedido[:30]}' não está configurado. Disponíveis: {', '.join(disponiveis)}."}
    bruto = str(args.get("comando") or "").strip()
    if not bruto:
        return {"texto": "Informe o comando em args.comando."}
    if len(bruto) > cls.MAX_COMANDO:
        return {"texto": f"Comando maior que {cls.MAX_COMANDO} caracteres — não executado."}

    texto, _hash, redigido = preparar_comando(bruto)
    veredito = (cls.Veredito("proibido", "bloqueado: o comando contém segredo (senha/token/chave) — nunca é executado")
                if redigido else cls.classificar(texto, raizes=srv.raizes, containers=srv.containers))

    if veredito.classe == "escrita":
        return _propor_escrita(abrir_conn, texto, srv, veredito, args, matricula=matricula, conversa_id=conversa_id,
                               pode_escrever=pode_escrever)

    # Parse dos filtros ANTES de registrar: nada que possa levantar fica entre o registro e a execução.
    filtrar = str(args.get("filtrar") or "").strip()[:MAX_FILTRO] or None
    primeiras = _inteiro(args.get("primeiras"), 1, MAX_LINHAS_SAIDA)
    ultimas = _inteiro(args.get("ultimas"), 1, MAX_LINHAS_SAIDA) if primeiras is None else None
    linha = cls.linha_de_execucao(veredito.argv) if veredito.classe == "leitura" else ""

    _gravar_seguro(abrir_conn, lambda cur: (varrer_interrompidos(cur), varrer_propostas_vencidas(cur)))  # best-effort
    try:
        reg = _gravar(abrir_conn, lambda cur: registrar(
            cur, conversa_id=conversa_id, matricula=matricula, servidor=srv.id, comando=texto,
            classe=veredito.classe, motivo=veredito.motivo))
    except Exception as e:  # noqa: BLE001 — sem auditoria, sem execução
        log.warning("terminal: auditoria indisponível (%s) — comando NÃO executado", type(e).__name__)
        return {"texto": "A auditoria do Terminal está indisponível — por segurança o comando não foi executado."}

    if veredito.classe == "proibido":
        return {"texto": f"$ {texto}\n{veredito.motivo}. Nada foi executado.",
                "comando_executado": _bloco_para_tela(reg["cmd_id"], texto, srv.id, "proibido", "bloqueado", motivo=veredito.motivo)}

    res: tssh.ResultadoExec | None = None
    try:
        res = await tssh.executar(srv, linha, teto_sessoes=ssh_max, espera_max_s=espera_max_s)
    except af.ServidorOcupado as e:
        _finalizar_seguro(abrir_conn, reg["cmd_id"], "falhou", saida=str(e))
        return {"texto": af.redigir(str(e))}
    except tssh.TerminalSshErro as e:
        _finalizar_seguro(abrir_conn, reg["cmd_id"], "falhou", saida=str(e))
        return {"texto": f"{e} Comando não executado."}
    except asyncio.CancelledError:
        _finalizar_seguro(abrir_conn, reg["cmd_id"], "falhou", saida="cancelado (orçamento da rodada)")
        raise
    except Exception as e:  # noqa: BLE001
        _finalizar_seguro(abrir_conn, reg["cmd_id"], "falhou", saida=f"erro inesperado ({type(e).__name__})")
        return {"texto": f"Falha ao executar no servidor ({type(e).__name__}) — tente de novo."}

    bruto_saida = res.stdout + (("\n" + res.stderr) if res.stderr.strip() else "")
    limpo = redigir_saida(bruto_saida)  # ANTES de cortar/filtrar
    corpo, descartadas = filtrar_saida(limpo, filtrar=filtrar, primeiras=primeiras, ultimas=ultimas)
    ok = res.exit_code == 0 and not res.estourou_tempo
    _finalizar_seguro(abrir_conn, reg["cmd_id"], "executado" if ok else "falhou", codigo_saida=res.exit_code,
                      duracao_ms=res.duracao_ms, saida=corpo)
    notas = []
    if any(a.startswith("--exclude=") for a in veredito.argv):
        notas.append("[busca recursiva: arquivos sensíveis (.env, chaves, *.cfg, *.conf…) são omitidos — a ausência de ocorrência pode ser por isso]")
    if args.get("primeiras") not in (None, "") and args.get("ultimas") not in (None, ""):
        notas.append("[`primeiras` e `ultimas` juntos: só `primeiras` foi aplicado]")
    return {"texto": _resposta(texto, srv.id, res, corpo, descartadas) + ("\n" + "\n".join(notas) if notas else ""),
            "comando_executado": _bloco_para_tela(reg["cmd_id"], texto, srv.id, "leitura", "executado" if ok else "falhou",
                                                  saida=corpo, codigo_saida=res.exit_code, duracao_ms=res.duracao_ms,
                                                  truncada=res.truncada, interrompido=res.estourou_tempo or res.exit_code in (124, 137),
                                                  notas=notas)}


MAX_SAIDA_TELA = 4000  # a saída que vai ao artefato (gravado em artefatos_json) — já redigida


def _bloco_para_tela(cmd_id: str, comando: str, servidor: str, classe: str, estado: str, *, saida: str | None = None,
                     codigo_saida: int | None = None, duracao_ms: int | None = None, truncada: bool = False,
                     interrompido: bool = False, motivo: str | None = None, notas=()) -> dict:
    """O que a TELA recebe de um comando executado/bloqueado (F5). Tudo já redigido: comando (`preparar_comando`) e saída
    (`redigir_saida`); a saída é cortada em `MAX_SAIDA_TELA` porque fica gravada no histórico da conversa."""
    corte = saida is not None and len(saida) > MAX_SAIDA_TELA
    return {"cmd_id": cmd_id, "comando": comando, "servidor": servidor, "classe": classe, "estado": estado,
            "saida": (saida[:MAX_SAIDA_TELA] if saida else saida), "codigo_saida": codigo_saida, "duracao_ms": duracao_ms,
            "truncada": bool(truncada or corte), "interrompido": bool(interrompido), "motivo": motivo, "notas": list(notas)}


_ULTIMA_PURGA = [0.0]
INTERVALO_PURGA_S = 3600


def purgar_antigos(cur, dias: int) -> int:
    """Retenção da auditoria (decisão do usuário, 05/11/2026: 180 dias, purga automática): apaga linhas em estado FINAL com mais de
    `dias`. Nunca apaga `proposto`/`executando`. Não faz commit."""
    dias = max(30, min(int(dias), 3650))
    marcas = ",".join("?" for _ in ESTADOS_FINAIS)
    cur.execute(f"DELETE FROM dbo.etl_agente_terminal_cmd WHERE criado_em < DATEADD(day, ?, GETDATE()) AND estado IN ({marcas})",
                [-dias, *ESTADOS_FINAIS])
    return max(0, cur.rowcount or 0)


def purgar_se_for_hora(abrir_conn, dias: int, agora: float | None = None) -> bool:
    """Purga no máximo uma vez por hora por processo (best-effort; o índice (estado, criado_em) cobre o DELETE)."""
    import time as _t
    agora = _t.monotonic() if agora is None else agora
    if agora - _ULTIMA_PURGA[0] < INTERVALO_PURGA_S and _ULTIMA_PURGA[0]:
        return False
    _ULTIMA_PURGA[0] = agora
    _gravar_seguro(abrir_conn, lambda cur: purgar_antigos(cur, dias))
    return True


def varrer_interrompidos(cur, minutos: int = 5) -> int:
    """Leitura OU escrita que ficou `executando` há mais de `minutos` (a API caiu/foi reiniciada entre `registrar`/`iniciar` e
    `finalizar`) vira `falhou` — a auditoria nunca fica "em andamento" para sempre. 5 min porque o pior caso legítimo (fila + conexão +
    sessão + 30 s de execução) fica abaixo de ~110 s. Escrita é medida pelo `decidido_em` e ganha a nota "PODE ter sido executado";
    `falhou` é final, então nada reabre nem repete. Idempotente. Não faz commit."""
    # Leitura: pelo `criado_em`. ESCRITA presa em `executando` (API morta entre `iniciar` e `finalizar`): pelo `decidido_em` (a proposta
    # pode ter até 120 s de idade) e com a nota HONESTA de que o comando PODE ter rodado — `falhou` é final, nada reabre nem repete.
    n = -abs(int(minutos))
    cur.execute(
        "UPDATE dbo.etl_agente_terminal_cmd SET estado = 'falhou', executado_em = GETDATE(), "
        "saida_resumo = CASE WHEN classe = 'escrita' THEN 'interrompido: o comando PODE ter sido executado (a API não registrou o fim)' "
        "ELSE 'interrompido: a API não registrou o fim da execução' END "
        "WHERE estado = 'executando' AND ((classe = 'leitura' AND criado_em < DATEADD(minute, ?, GETDATE())) "
        "OR (classe = 'escrita' AND decidido_em < DATEADD(minute, ?, GETDATE())))",
        [n, n])
    return max(0, cur.rowcount or 0)


def _gravar_seguro(abrir_conn, fn) -> None:
    try:
        _gravar(abrir_conn, fn)
    except Exception as e:  # noqa: BLE001
        log.warning("terminal: tarefa de manutenção da auditoria falhou (%s)", type(e).__name__)


def _finalizar_seguro(abrir_conn, cmd_id: str, estado: str, *, codigo_saida=None, duracao_ms=None, saida=None) -> None:
    """Fecha o registro; se o banco falhar AGORA o comando já rodou — só registra o aviso no log."""
    try:
        if not _gravar(abrir_conn, lambda cur: finalizar(cur, cmd_id, estado, codigo_saida=codigo_saida,
                                                         duracao_ms=duracao_ms, saida=saida)):
            log.warning("terminal: %s já não estava `executando` ao finalizar como %s (varrido como interrompido?)", cmd_id, estado)
    except Exception as e:  # noqa: BLE001
        log.warning("terminal: não foi possível finalizar %s em %s (%s)", cmd_id, estado, type(e).__name__)


# ═══════════ F4: ESCRITA com confirmação do usuário ════════════════════════
#
# Fluxo: o modelo PROPÕE (`servidor_exec` → classe `escrita`) → o backend grava `proposto` com o texto EXATO e o hash
# → a tela mostra o card → o usuário clica Confirmar/Recusar → `confirmar_comando`/`recusar_comando`.
# O que garante que "o que o usuário viu é o que roda":
#   • o COMANDO nunca vem do cliente na confirmação: o cliente manda só `cmd_id` + o `hash` que viu; o texto executado é
#     o gravado em `etl_agente_terminal_cmd` (e o hash é recalculado a partir dele — adulteração no banco também falha);
#   • só o MESMO usuário que recebeu a proposta confirma (nem o admin confirma proposta alheia);
#   • `iniciar` é atômico (`proposto → executando` só dentro do prazo e uma única vez): duplo clique = uma execução;
#   • o kill switch e o recurso de escrita são checados na confirmação (`exigir_escrita`), não só na proposta;
#   • o comando é RECLASSIFICADO na hora de rodar: se a denylist passou a proibi-lo, não roda;
#   • comando com segredo (`redigido`) e `proibido` nunca chegam a `proposto` (CHECKs do banco + `registrar`).
# O texto executado roda num `/bin/sh -c` com o `timeout` remoto: o shell vê EXATAMENTE a string do card.

class ConfirmacaoErro(Exception):
    """Recusa nomeada da confirmação/recusa (vira HTTP no router)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def obter(cur, cmd_id: str) -> dict | None:
    """Linha de auditoria pelo id (None se não existe). `expira_em` é comparado no BANCO (`segundos_restantes`)."""
    cur.execute(
        "SELECT cmd_id, conversa_id, matricula, servidor, comando, hash, classe, estado, motivo, redigido, "
        "DATEDIFF(second, GETDATE(), expira_em), decidido_por, codigo_saida, duracao_ms, saida_resumo, executado_em, decidido_em "
        "FROM dbo.etl_agente_terminal_cmd WHERE cmd_id = ?", [_uuid(cmd_id)])
    r = cur.fetchone()
    if not r:
        return None
    chaves = ("cmd_id", "conversa_id", "matricula", "servidor", "comando", "hash", "classe", "estado", "motivo", "redigido",
              "segundos_restantes", "decidido_por", "codigo_saida", "duracao_ms", "saida_resumo", "executado_em", "decidido_em")
    d = dict(zip(chaves, r))
    d["cmd_id"] = str(d["cmd_id"])
    d["redigido"] = bool(d["redigido"])
    for k in ("executado_em", "decidido_em"):
        d[k] = d[k].isoformat() if d[k] else None
    return d


def varrer_propostas_vencidas(cur) -> int:
    """`proposto` com prazo vencido (relógio do BANCO) vira `expirado`. Idempotente. Não faz commit."""
    cur.execute("UPDATE dbo.etl_agente_terminal_cmd SET estado = 'expirado' "
                "WHERE estado = 'proposto' AND expira_em IS NOT NULL AND expira_em <= GETDATE()")
    return max(0, cur.rowcount or 0)


JANELA_RECUSA_MIN = 10  # um comando recusado não pode ser re-proposto por este tempo (o modelo não vence o usuário por cansaço)


def proposta_repetida(cur, matricula: str, hash_: str) -> str | None:
    """`"viva"` se o MESMO comando (hash) já aguarda confirmação deste usuário; `"recusada"` se ele o recusou há menos de
    `JANELA_RECUSA_MIN` min; senão None."""
    cur.execute(
        "SELECT TOP 1 estado FROM dbo.etl_agente_terminal_cmd WHERE matricula = ? AND hash = ? AND classe = 'escrita' AND "
        "((estado = 'proposto' AND expira_em > GETDATE()) OR estado = 'executando' "
        "OR (estado = 'recusado' AND decidido_em > DATEADD(minute, ?, GETDATE()))) "
        "ORDER BY criado_em DESC", [matricula, hash_, -JANELA_RECUSA_MIN])
    r = cur.fetchone()
    return None if not r else ("recusada" if r[0] == "recusado" else "viva")


def contar_propostas_vivas(cur, matricula: str) -> int:
    cur.execute("SELECT COUNT(*) FROM dbo.etl_agente_terminal_cmd WHERE matricula = ? AND estado = 'proposto' "
                "AND expira_em > GETDATE()", [matricula])
    return int(cur.fetchone()[0])


def reabrir(cur, cmd_id: str) -> bool:
    """`executando → proposto`, SÓ se ainda dentro do prazo e SÓ para escrita: usado quando a execução falhou ANTES de sair (fila de
    sessões cheia/conexão recusada) — o comando não rodou, então o usuário pode confirmar de novo. Atômico. Não faz commit."""
    cur.execute(
        "UPDATE dbo.etl_agente_terminal_cmd SET estado = 'proposto', decidido_por = NULL, decidido_em = NULL "
        "WHERE cmd_id = ? AND estado = 'executando' AND classe = 'escrita' AND redigido = 0 AND expira_em > GETDATE()", [_uuid(cmd_id)])
    return cur.rowcount == 1


def _propor_escrita(abrir_conn, texto: str, srv, veredito, args: dict, *, matricula: str, conversa_id: str | None,
                    pode_escrever: bool) -> dict:
    """Registra a PROPOSTA (não executa). Sem permissão de escrita, nada é registrado."""
    if not pode_escrever:
        return {"texto": f"{TEXTO_SEM_ESCRITA} Motivo: {veredito.motivo}."}
    # O `motivo` é do MODELO (e aparece ao lado do comando no card): redigido como o resto, cortado, e o card mostra o MESMO texto
    # que fica gravado. Não-string (lista/dict) vale como ausente — nada de `str(dict)` no card.
    bruto = args.get("motivo")
    if isinstance(bruto, str):  # sem controle/bidi/zero-width: o motivo também aparece no card (auditoria da F4, 2ª rodada)
        bruto = "".join(c for c in bruto if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp"))
    motivo = (_texto(redigir_comando(bruto.strip()[:2000]), MAX_MOTIVO) if isinstance(bruto, str) and bruto.strip() else None) or veredito.motivo
    _h = preparar_comando(texto)[1]
    try:
        def _fn(cur):
            varrer_propostas_vencidas(cur)
            varrer_interrompidos(cur)  # escrita presa em `executando` (API caiu) não bloqueia a re-proposta para sempre
            if proposta_repetida(cur, matricula, _h) == "recusada":
                return "recusada"
            if proposta_repetida(cur, matricula, _h) == "viva":
                return "viva"
            if contar_propostas_vivas(cur, matricula) >= MAX_PROPOSTAS_VIVAS:
                return None
            return registrar(cur, conversa_id=conversa_id, matricula=matricula, servidor=srv.id, comando=texto,
                             classe="escrita", motivo=motivo)
        reg = _gravar(abrir_conn, _fn)
    except Exception as e:  # noqa: BLE001 — sem auditoria, sem proposta
        log.warning("terminal: auditoria indisponível ao propor (%s)", type(e).__name__)
        return {"texto": "A auditoria do Terminal está indisponível — por segurança nenhuma proposta foi registrada."}
    if reg == "recusada":
        return {"texto": f"O usuário RECUSOU este mesmo comando há menos de {JANELA_RECUSA_MIN} minutos. Não o proponha de novo: "
                         "pergunte o que ele prefere ou ofereça outra abordagem."}
    if reg == "viva":
        return {"texto": "Este mesmo comando já está AGUARDANDO a confirmação do usuário ou EXECUTANDO. Não o proponha de novo; "
                         "avise que o card está pendente (ou que a execução está em andamento)."}
    if reg is None:
        return {"texto": f"Já há {MAX_PROPOSTAS_VIVAS} comandos aguardando confirmação deste usuário. Peça para confirmar ou "
                         "recusar os pendentes antes de propor outro."}
    return {
        "texto": (f"Proposta registrada e AGUARDANDO a confirmação do usuário (válida por {reg['validade_s']} s): `{reg['comando']}` "
                  f"em {srv.id}. O comando NÃO foi executado. Diga ao usuário que ele precisa confirmar ou recusar no card; "
                  "não proponha o mesmo comando de novo e não tente executá-lo de outra forma."),
        "proposta_comando": {"cmd_id": reg["cmd_id"], "hash": reg["hash"], "comando": reg["comando"], "servidor": srv.id,
                             "motivo": motivo, "classe": "escrita", "estado": "proposto",
                             "segundos_restantes": reg["validade_s"]},
    }


def _dono_ou_erro(row: dict | None, usuario: dict) -> dict:
    if row is None:
        raise ConfirmacaoErro(404, "comando_inexistente", "Comando não encontrado.")
    if (row["matricula"] or "").strip() != (usuario.get("matricula") or "").strip():
        # 404 (e não 403): não confirma a existência do comando de outra pessoa.
        raise ConfirmacaoErro(404, "comando_inexistente", "Comando não encontrado.")
    return row


def recusar_comando(abrir_conn, *, cmd_id: str, usuario: dict) -> dict:
    """O usuário RECUSA a proposta. Só o dono; só enquanto `proposto`."""
    try:
        def _fn(cur):
            row = _dono_ou_erro(obter(cur, cmd_id), usuario)
            ok = finalizar(cur, cmd_id, "recusado", decidido_por=usuario["matricula"])
            return row, ok
        row, ok = _gravar(abrir_conn, _fn)
    except AuditoriaInvalida as e:
        raise ConfirmacaoErro(422, "cmd_id_invalido", str(e)) from None
    if not ok:
        raise ConfirmacaoErro(409, "ja_decidido", "Este comando já foi decidido ou expirou.")
    return {"cmd_id": row["cmd_id"], "estado": "recusado", "decidido_por": usuario["matricula"]}


async def confirmar_comando(abrir_conn, *, cmd_id: str, hash_visto: str, usuario: dict, ssh_max: int,
                            espera_max_s: float = 10.0) -> dict:
    """O usuário CONFIRMA: executa o texto gravado, uma única vez. Quem chama já passou por `exigir_escrita` (kill switch +
    recurso de escrita). Levanta `ConfirmacaoErro`; nunca executa nada fora dos casos abaixo."""
    hash_visto = (hash_visto or "").strip().lower()
    try:
        row = _gravar(abrir_conn, lambda cur: (varrer_propostas_vencidas(cur), varrer_interrompidos(cur), obter(cur, cmd_id))[2])
    except AuditoriaInvalida as e:
        raise ConfirmacaoErro(422, "cmd_id_invalido", str(e)) from None
    row = _dono_ou_erro(row, usuario)
    if row["classe"] != "escrita" or row["redigido"]:
        raise ConfirmacaoErro(409, "nao_confirmavel", "Este comando não pode ser confirmado.")
    if hash_visto != row["hash"]:
        raise ConfirmacaoErro(409, "hash_diferente", "O comando mudou desde que você o viu — peça a proposta de novo.")
    if hashlib.sha256((row["comando"] or "").encode("utf-8")).hexdigest() != row["hash"]:
        log.error("terminal: hash do comando %s não confere com o texto gravado", row["cmd_id"])
        raise ConfirmacaoErro(500, "integridade", "Falha de integridade do comando — nada foi executado.")
    if row["estado"] == "expirado" or (row["estado"] == "proposto" and (row["segundos_restantes"] or 0) <= 0):
        raise ConfirmacaoErro(409, "expirada", "A proposta expirou. Peça o comando de novo.")
    if row["estado"] != "proposto":
        raise ConfirmacaoErro(409, "ja_decidido", "Este comando já foi decidido.")
    srv = tssh.servidores().get(row["servidor"])
    if srv is None:
        raise ConfirmacaoErro(503, "servidor_indisponivel", "O servidor deste comando não está mais configurado.")
    # Reclassifica AGORA: uma denylist atualizada depois da proposta vale (nunca roda o que passou a ser proibido).
    if cls.classificar(row["comando"], raizes=srv.raizes, containers=srv.containers).classe == "proibido":
        _gravar_seguro(abrir_conn, lambda cur: finalizar(cur, cmd_id, "recusado", decidido_por=usuario["matricula"]))
        raise ConfirmacaoErro(409, "agora_proibido", "Este comando passou a ser proibido — não foi executado.")

    # Libera a execução: ATÔMICO, uma vez, só dentro do prazo (relógio do banco).
    if not _gravar(abrir_conn, lambda cur: iniciar(cur, cmd_id, usuario["matricula"])):
        raise ConfirmacaoErro(409, "ja_decidido", "Este comando já foi decidido ou expirou.")

    linha = "/bin/sh -c " + shlex.quote(row["comando"])  # o shell remoto recebe EXATAMENTE o texto do card
    try:
        res = await tssh.executar(srv, linha, teto_sessoes=ssh_max, espera_max_s=espera_max_s)
    except asyncio.CancelledError:
        # `executar` usa `asyncio.shield`: a sessão pode seguir rodando depois do cancelamento — o resultado é DESCONHECIDO.
        _finalizar_seguro(abrir_conn, cmd_id, "falhou", saida="interrompido: o comando PODE ter sido executado (requisição cancelada)")
        raise
    except (af.ServidorOcupado, tssh.TerminalSshErro) as e:
        # Falha CERTA e anterior à execução (fila de sessões cheia, conexão recusada, known_hosts): o comando NÃO saiu. Devolve a
        # proposta a `proposto` (se ainda dentro do prazo) para o usuário poder confirmar de novo sem pedir ao modelo outra vez.
        voltou = False
        try:
            voltou = _gravar(abrir_conn, lambda cur: reabrir(cur, cmd_id))
        except Exception:  # noqa: BLE001
            pass
        if not voltou:
            _finalizar_seguro(abrir_conn, cmd_id, "falhou", saida=f"não executado: {e}")
        raise ConfirmacaoErro(503, "servidor_ocupado_ou_indisponivel",
                              f"{af.redigir(str(e))} O comando NÃO foi executado" + (" — você pode confirmar de novo." if voltou else ".")) from None
    except Exception as e:  # noqa: BLE001 — falha DEPOIS de abrir a sessão: o resultado é ambíguo, não reabre
        _finalizar_seguro(abrir_conn, cmd_id, "falhou", saida=f"erro inesperado ({type(e).__name__}); o comando PODE ter sido executado")
        raise ConfirmacaoErro(502, "falha_na_execucao", f"Falha ao executar ({type(e).__name__}). O comando PODE ter sido executado.") from None
    try:
        corpo = redigir_saida(res.stdout + (("\n" + res.stderr) if res.stderr.strip() else ""))
        corpo, descartadas = filtrar_saida(corpo)
    except Exception as e:  # noqa: BLE001 — o comando JÁ rodou: fecha a linha e nunca devolve a saída crua
        log.warning("terminal: falha ao redigir a saída da escrita %s (%s)", cmd_id, type(e).__name__)
        corpo = "[saída indisponível: falha ao redigir — o comando foi executado]"
    ok = res.exit_code == 0 and not res.estourou_tempo
    _finalizar_seguro(abrir_conn, cmd_id, "executado" if ok else "falhou", codigo_saida=res.exit_code,
                      duracao_ms=res.duracao_ms, saida=corpo)
    return {"cmd_id": row["cmd_id"], "estado": "executado" if ok else "falhou", "comando": row["comando"], "servidor": srv.id,
            "codigo_saida": res.exit_code, "duracao_ms": res.duracao_ms, "saida": af._truncar(corpo),
            "truncada": res.truncada, "interrompido": res.estourou_tempo or res.exit_code in (124, 137),
            "decidido_por": usuario["matricula"]}
