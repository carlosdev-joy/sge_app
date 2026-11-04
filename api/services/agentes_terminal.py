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

import hashlib
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta

from services import agentes_ferramentas as af
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

# Larguras das colunas NVARCHAR (migration 197) — contam UTF-16.
MAX_COMANDO = 2000
MAX_MOTIVO = 500
MAX_SAIDA = 4000
VALIDADE_PROPOSTA_S = 120  # 2 min: o card de confirmação expira

LIMITE_PADRAO = 50
LIMITE_MAX = 200


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
_PADROES_SEGREDO = (
    re.compile(r"(?i)(://[^/\s:@]+:)[^/\s]+(@)"),                                        # url user:senha@host (senha pode ter @)
    re.compile(r"(?i)(\bbearer\s+)" + _V),                                              # Authorization: Bearer X
    re.compile(r"(?i)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-[a-z-]*(?:auth|token|key|secret)[a-z-]*)\s*[:=]\s*)(?!bearer\b)[^'\"\n]+"),
    re.compile(r"(?i)(\b(?:password|passwd|senha|secret|token|api[_-]?key)\s*:\s*)" + _V),  # "password: x" (cabeçalho/arquivo)
    re.compile(r"(?i)(\s(?:-u|--user|--basic-auth)[\s=]+[^\s:'\"]+:)\S+"),                  # curl -u user:senha (até o fim do token)
    re.compile(r"(?i)(--(?:password|passwd|pass|pwd|token|secret|api-key|apikey|client-secret|access-key|secret-key)(?:=|\s+))" + _V),
    re.compile(r"(?i)(\b(?:mysql|mysqldump|mysqladmin|mysqlcheck|mariadb)\b[^|;&\n]*?\s-p)(?=[^\s=/-])" + _V),  # mysql -pSENHA
    re.compile(r"(\b(?:sqlcmd|bcp)\b[^|;&\n]*?\s-P\s*)" + _V),                            # sqlcmd -P SENHA
    re.compile(r"(?i)(\bsshpass\s+-p\s*)" + _V),                                          # sshpass -p SENHA
    re.compile(r"(?i)(\blogin\b[^|;&\n]*?\s-p\s+)" + _V),                                 # docker login -p SENHA
    re.compile(r"(?i)(\b[A-Za-z0-9_]*(?:pass|pwd|secret|token|apikey|api_key|credential)[A-Za-z0-9_]*\s*=\s*)" + _V),  # KEY_PASS=x
)


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
