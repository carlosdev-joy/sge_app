"""isx_engine.py — lineage automático via ISX (istool export) — spec docs/spec-lineage-isx.md.

O que este módulo faz: dado um job do DataStage (projeto + pasta + nome), localiza-o
pela API REST, confere o `lastModified`, exporta a definição com o `istool` por SSH
(arquivo `.isx`, um ZIP com o XML `DSJobDefSDO`) e lê desse XML tudo que o lineage
precisa — parâmetros, stages com direção e classe, SQL e DSN dos conectores, path
de arquivos, colunas de saída e de entrada, expressões coluna a coluna, APT code do
Transformer, fluxo entre stages, filhos de um sequence.

Duas camadas, de propósito (o mesmo desenho de `services/ssh_arquivos.py` da API):
  * funções PURAS — validação de nomes, caminho do istool, montagem do comando,
    parse do XML, classificação — testáveis sem rede;
  * o que fala com o mundo recebe TRANSPORTES injetáveis: `rest(caminho) -> dict`
    (caminho RELATIVO à `DS_API_URL`, já validado por `_caminho_api_valido`) e
    `ssh() -> (executar, sftp)`. Na API os transportes são httpx + paramiko; nos
    testes, fakes em memória.

⚠️ Nada aqui conhece host, usuário ou senha. Tudo vem de `ConfigISX` (ambiente) e
a credencial do istool fica num `-authfile` NO SERVIDOR (`DS_ISTOOL_AUTHFILE`):
`-password` na linha de comando aparecia no `ps` e nos logs. Todo pedaço de nome
que vira shell passa por lista branca + `shlex.quote`. O `.isx` traz credenciais
de conexão dentro do `XMLProperties`: elas nunca saem do parser, e o arquivo
temporário nasce com `umask 077` numa pasta privada do usuário SSH.
"""
from __future__ import annotations

import hashlib
import html
import io
import os
import posixpath
import re
import shlex
import time
import urllib.parse
import uuid
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from utils.ds_stage_types import CATEGORIA_POR_CLASSE, classe_do_tipo, direcao

# Teto do .isx: um job parallel tem dezenas de KB; 20 MB já é um sequence enorme.
# Vale para o ZIP E para o membro descomprimido (bomba de descompressão).
ISX_MAX_BYTES = 20 * 1024 * 1024
# Busca em largura na árvore de pastas do projeto (BI_CVP tem 3.398 jobs).
LOCALIZAR_MAX_NOS = 5000
LOCALIZAR_MAX_S = 30.0
EXPORT_TETO_S = 60
XSI = "{http://www.w3.org/2001/XMLSchema-instance}"

_NOME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
# Componente de pasta: as pastas reais têm acento, espaço, ponto e parênteses
# ("03. Dimensões", "05. Projetos/AcumuloIS_Diaria"). `\w` é Unicode e NÃO casa
# caracteres de formato (zero-width, soft hyphen); tudo vai ao shell por `shlex.quote`.
_PASTA_COMP_RE = re.compile(r"^[\w. \-()&+,]{1,200}$")
# Caminhos que a API REST devolve (`id`, `$ref`) e que voltamos a pedir a ela: só
# estes dois prefixos, sem `..`, `//` nem `:` — nada de URL absoluta ou salto de host.
_API_CAMINHO_RE = re.compile(r"^(?:folders|jobdesigns)/[A-Za-z0-9%._-]+(?:/contents)?$")
# Extensões do istool por tipo, em ORDEM de tentativa: um sequence que chama outros
# jobs exporta como .qjb e um sequence simples como .sjb — a API REST diz só
# "SEQUENCE" para os dois (documento de origem, §4.4). `exportar_job` tenta em ordem.
_EXTS_POR_TIPO = {"PARALLEL": ("pjb",), "SEQUENCE": ("qjb", "sjb")}
# O istool diz assim quando o caminho não existe (pasta ou job); vale tentar o próximo.
_MARCAS_NAO_ENCONTRADO = ("not found", "no assets matched")
_RE_LEN = re.compile(r"\[(?:max=)?(\d{1,9})\]")
_RE_DB_HINT = re.compile(r"ParmDb(?:Name)?([A-Za-z0-9]{3,})")
# Parâmetro de job que carrega segredo (tipo Encrypted ou nome sugestivo): o
# defaultValue — ofuscado pelo engine, reversível — nunca sai.
_RE_PARAM_SEGREDO = re.compile(r"(?i)senha|password|pwd|secret|encrypted")
# TableName antes de BeforeSQL/AfterSQL: num destino, a tabela-alvo é o que importa.
_TAGS_SQL = ("SelectStatement", "WriteStatement", "InsertStatement", "UpdateStatement",
             "DeleteStatement", "TableName", "BeforeSQL", "AfterSQL")
# DOCTYPE/ENTITY em qualquer codificação que o expat aceite (UTF-8, UTF-16 LE/BE),
# procurados no documento INTEIRO (um comentário longo antes do DOCTYPE não engana).
_MARCAS_DTD = tuple(m.encode(enc) for m in ("<!doctype", "<!entity")
                    for enc in ("utf-8", "utf-16-le", "utf-16-be"))


class ISXError(Exception):
    """Vira HTTPException no router. `interno` vai ao log, nunca à resposta."""

    def __init__(self, status: int, detail: str, *, interno: str | None = None, resultado: str = "erro"):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.interno = interno
        self.resultado = resultado


# ── Configuração (só nomes de variáveis; valores vêm do ambiente) ────────────

@dataclass(frozen=True)
class ConfigISX:
    engine: str
    api_url: str
    api_user: str | None
    api_password: str | None = field(repr=False)  # fora do repr: um log de %r não vaza
    api_verify: bool | str = True
    istool_home: str = "/opt/IBM/InformationServer"
    istool_launcher: str = "Clients/istools/cli/plugins/org.eclipse.equinox.launcher_1.1.0.v20100507.jar"
    istool_domain: str = ""
    istool_authfile: str | None = None
    istool_tmp: str = "~/.orquestra/tmp"
    istool_cfg: str = "~/.orquestra/istool_cfg"

    @classmethod
    def do_ambiente(cls, env=None) -> "ConfigISX":
        env = os.environ if env is None else env
        verify_bruto = (env.get("DS_API_VERIFY_SSL") or "true").strip()
        verify: bool | str
        if verify_bruto.lower() in ("false", "0", "no", "nao", "não"):
            verify = False
        elif verify_bruto.lower() in ("true", "1", "yes", "sim"):
            verify = True
        else:
            verify = verify_bruto  # caminho de um CA bundle
        return cls(
            engine=(env.get("DS_ENGINE") or "").strip(),
            api_url=(env.get("DS_API_URL") or "").strip().rstrip("/"),
            api_user=(env.get("DS_API_USER") or "").strip() or None,
            api_password=env.get("DS_API_PASSWORD") or None,
            api_verify=verify,
            istool_home=(env.get("DS_ISTOOL_HOME") or "/opt/IBM/InformationServer").rstrip("/"),
            istool_launcher=(env.get("DS_ISTOOL_LAUNCHER")
                             or "Clients/istools/cli/plugins/org.eclipse.equinox.launcher_1.1.0.v20100507.jar").strip(),
            istool_domain=(env.get("DS_ISTOOL_DOMAIN") or "").strip(),
            istool_authfile=(env.get("DS_ISTOOL_AUTHFILE") or "").strip() or None,
            # Pasta PRIVADA do usuário SSH, não /tmp: o .isx carrega credenciais de conexão.
            istool_tmp=(env.get("DS_ISTOOL_TMP") or "~/.orquestra/tmp").strip().rstrip("/") or "~/.orquestra/tmp",
            istool_cfg=(env.get("DS_ISTOOL_CFG") or "~/.orquestra/istool_cfg").strip(),
        )

    def faltas(self) -> list[str]:
        """Variáveis obrigatórias ausentes — o router responde 503 nomeando-as."""
        f = []
        if not self.engine:
            f.append("DS_ENGINE")
        if not self.api_url:
            f.append("DS_API_URL")
        if not self.api_user or not self.api_password:
            f.append("DS_API_USER/DS_API_PASSWORD")
        if not self.istool_domain:
            f.append("DS_ISTOOL_DOMAIN")
        if not self.istool_authfile:
            f.append("DS_ISTOOL_AUTHFILE")
        return f


# ── Funções puras: nomes, caminhos, comando ──────────────────────────────────

def validar_nome(valor, campo: str) -> str:
    s = str(valor or "").strip()
    if not _NOME_RE.match(s):
        raise ISXError(422, f"{campo} inválido: só letras, números, '_', '.' e '-' (até 200).")
    if s in (".", ".."):
        raise ISXError(422, f"{campo} inválido.")
    return s


def validar_pasta(folder_path) -> list[str]:
    """`\\Jobs\\SsdVida\\_Dime` (como a API devolve) ou `Jobs/SsdVida/_Dime` →
    ['Jobs', 'SsdVida', '_Dime']. Cada componente passa pela lista branca; `..`
    é recusado; a pasta precisa começar por `Jobs`."""
    bruto = str(folder_path or "").replace("\\", "/").strip()
    partes = [p for p in bruto.split("/") if p != ""]
    if not partes:
        raise ISXError(422, "Pasta do job vazia.")
    for p in partes:
        if p in (".", "..") or not _PASTA_COMP_RE.match(p) or p != p.strip():
            raise ISXError(422, f"Pasta do job inválida: componente {p!r}.")
    if partes[0] != "Jobs":
        raise ISXError(422, "Pasta do job precisa começar por 'Jobs'.")
    return partes


def tipo_job(bruto) -> str:
    t = str(bruto or "PARALLEL").strip().upper()
    if t not in _EXTS_POR_TIPO:
        raise ISXError(422, f"Tipo de job desconhecido: {t!r} (esperado PARALLEL ou SEQUENCE; server jobs ficam fora).")
    return t


def caminhos_istool(engine: str, projeto: str, folder_path, job: str, tipo: str) -> list[str]:
    """Os caminhos `-datastage` a tentar, em ordem: `ENGINE/PROJETO/Jobs/A/B/JOB.pjb`
    para PARALLEL; `.qjb` e depois `.sjb` para SEQUENCE."""
    eng = validar_nome(engine, "Engine")
    proj = validar_nome(projeto, "Projeto")
    j = validar_nome(job, "Job")
    partes = validar_pasta(folder_path)
    base = f"{eng}/{proj}/{'/'.join(partes)}/{j}."
    return [base + ext for ext in _EXTS_POR_TIPO[tipo_job(tipo)]]


def caminho_istool(engine: str, projeto: str, folder_path, job: str, tipo: str) -> str:
    """O primeiro candidato de `caminhos_istool` (quem quer a lista inteira usa ela)."""
    return caminhos_istool(engine, projeto, folder_path, job, tipo)[0]


def _caminho_datastage_shell(caminho: str) -> str:
    """O istool quebra o `-datastage` no espaço MESMO entre aspas simples (medido em
    produção com pastas como `04. ODS`): o espaço vai escapado com `\\ ` dentro das
    aspas, e é o próprio istool que desfaz o escape."""
    return shlex.quote(caminho.replace(" ", "\\ "))


def nome_archive(cfg: ConfigISX, job: str) -> str:
    """Arquivo temporário único no servidor: `<tmp>/orq_<job>_<uuid8>.isx`."""
    return posixpath.join(cfg.istool_tmp, f"orq_{validar_nome(job, 'Job')}_{uuid.uuid4().hex[:8]}.isx")


def _caminho_shell(caminho: str) -> str:
    """`shlex.quote` com uma exceção: `~/x` vira `"$HOME"/'x'`, porque um til entre
    aspas não expande e os defaults de DS_ISTOOL_CFG/TMP são dentro do home do usuário SSH."""
    if caminho == "~":
        return '"$HOME"'
    if caminho.startswith("~/"):
        return '"$HOME"/' + shlex.quote(caminho[2:])
    return shlex.quote(caminho)


def caminho_sftp(caminho: str) -> str:
    """O SFTP não expande `~`: `~/x` vira `x` (relativo ao home do usuário SSH, que é
    o diretório inicial do sftp-server) e `~` vira `.`. O resto passa inalterado."""
    if caminho == "~":
        return "."
    if caminho.startswith("~/"):
        return caminho[2:] or "."
    return caminho


def comando_istool(cfg: ConfigISX, caminho: str, archive: str, *, preview: bool = False) -> str:
    """A linha de shell do export. Tudo que veio de fora passa por `shlex.quote`
    (`~/…` vira `"$HOME"/…`); `$JAVA_HOME` fica sem aspas de propósito (é o
    setupEnv.sh quem o define). Nenhum `-password`: a credencial vem do `-authfile`.
    `umask 077` + pasta temporária privada: o .isx traz credenciais de conexão e não
    pode nascer legível por todos num /tmp compartilhado. O `find` apaga órfãos de um
    export que estourou o teto (o istool continua depois de o canal SSH fechar)."""
    if not cfg.istool_authfile:
        raise ISXError(503, "istool sem authfile: defina DS_ISTOOL_AUTHFILE (arquivo no servidor do DataStage).")
    if not cfg.istool_domain:
        raise ISXError(503, "istool sem domínio: defina DS_ISTOOL_DOMAIN (host:porta dos serviços).")
    home = cfg.istool_home
    launcher = posixpath.join(home, cfg.istool_launcher)
    q = shlex.quote
    cfg_dir = _caminho_shell(cfg.istool_cfg)
    tmp_dir = _caminho_shell(cfg.istool_tmp)
    preparo = " && ".join([
        f". {q(home + '/ASBNode/bin/setupEnv.sh')} >/dev/null 2>&1",
        "umask 077",
        f"mkdir -p -m 700 {tmp_dir}",
        f"mkdir -p {cfg_dir}",
    ])
    # configuration/ precisa ser gravável: cópia por usuário, uma vez (cp -rn não sobrescreve).
    copia = f"cp -rn {q(home + '/Clients/istools/cli/configuration/.')} {cfg_dir}/ 2>/dev/null"
    limpeza = f"find {tmp_dir} -maxdepth 1 -name 'orq_*.isx' -mmin +10 -delete 2>/dev/null"
    export = (
        '"$JAVA_HOME"/bin/java -jar ' + q(launcher)
        + " -application com.ibm.iis.istools.cli.application"
        + f" -configuration {cfg_dir}"
        + " export"
        + f" -domain {q(cfg.istool_domain)}"
        + f" -authfile {q(cfg.istool_authfile)}"
        + f" -archive {_caminho_shell(archive)}"
        + f" -datastage {_caminho_datastage_shell(caminho)}"
        + (" -preview" if preview else "")
    )
    return f"{preparo} && {copia}; {limpeza}; {export}"


# ── API REST: localizar e conferir modificação ───────────────────────────────

def _quote_ds(*partes: str) -> str:
    """`A\\B\\C` percent-encoded como a API espera: `A%5CB%5CC`."""
    return "%5C".join(urllib.parse.quote(p, safe="") for p in partes)


def caminho_pastas(engine: str, projeto: str, partes: list[str] | None = None) -> str:
    base = [engine, projeto] + (partes or ["Jobs"])
    return f"folders/{_quote_ds(*base)}/contents"


def api_id_de(engine: str, projeto: str, folder_path, job: str) -> str:
    partes = validar_pasta(folder_path)
    return f"jobdesigns/{_quote_ds(engine, projeto, *partes, validar_nome(job, 'Job'))}"


def _folder_path_de(partes: list[str]) -> str:
    return "\\" + "\\".join(partes)


def _caminho_api_valido(caminho) -> str | None:
    """`id`/`$ref` da resposta da API: só `folders/…[/contents]` e `jobdesigns/…`
    relativos, com a lista branca de caracteres. Qualquer outra coisa (URL absoluta,
    `..`, outro prefixo) é ignorada — a API é confiável, mas o transporte da F2 anexa
    Basic auth ao que pedir, e o escopo tem de ser o desta API."""
    s = str(caminho or "").strip().lstrip("/")
    return s if _API_CAMINHO_RE.match(s) else None


def localizar_job(rest, engine: str, projeto: str, job: str, *, max_nos: int = LOCALIZAR_MAX_NOS,
                  teto_s: float = LOCALIZAR_MAX_S, relogio=time.monotonic) -> dict | None:
    """Busca em largura a partir de `Jobs/` até achar o job. Devolve
    {api_id, folder_path, job_type, last_modified} ou None. Teto de nós e de
    tempo (a árvore do BI_CVP é grande): estourou → ISXError(504)."""
    eng = validar_nome(engine, "Engine")
    proj = validar_nome(projeto, "Projeto")
    alvo = validar_nome(job, "Job")
    inicio = relogio()
    fila: list[tuple[str, list[str]]] = [(caminho_pastas(eng, proj), ["Jobs"])]
    vistos = 0
    while fila:
        caminho, partes = fila.pop(0)
        vistos += 1
        if vistos > max_nos:
            raise ISXError(504, f"A árvore do projeto {proj} passa de {max_nos} pastas — informe a pasta do job.")
        if relogio() - inicio > teto_s:
            raise ISXError(504, f"A busca do job na árvore do projeto {proj} passou de {teto_s:g} s.")
        resposta = rest(caminho) or {}
        for filho in resposta.get("children") or []:
            if not isinstance(filho, dict):
                continue
            ident = _caminho_api_valido(filho.get("id"))
            if ident and ident.startswith("jobdesigns/"):
                if filho.get("name") == alvo:
                    return {
                        "api_id": ident,
                        "folder_path": _folder_path_de(partes),
                        "job_type": str(filho.get("jobType") or "PARALLEL").upper(),
                        "last_modified": filho.get("lastModifiedTimestamp") or filho.get("lastModified"),
                    }
                continue
            ref = _caminho_api_valido(filho.get("$ref"))
            nome = str(filho.get("name") or "")
            if ref and ref.startswith("folders/") and nome:
                fila.append((ref, partes + [nome]))
    return None


def checar_modificado(rest, api_id: str) -> dict:
    """Metadados do job pelo `jobdesigns/…`: {last_modified, job_type, folder_path,
    description, long_description}. 404 se a API não acha; 422 se o id não é um
    caminho `jobdesigns/…` desta API."""
    caminho = _caminho_api_valido(api_id)
    if not caminho or not caminho.startswith("jobdesigns/"):
        raise ISXError(422, "Identificador do job na API do DataStage inválido.")
    meta = rest(caminho)
    if not meta or not isinstance(meta, dict):
        raise ISXError(404, "Job não encontrado no DataStage.")
    lm = meta.get("lastModified") or {}
    return {
        "last_modified": (lm.get("timestamp") if isinstance(lm, dict) else None) or meta.get("lastModifiedTimestamp"),
        "job_type": str(meta.get("jobType") or "PARALLEL").upper(),
        "folder_path": meta.get("folderPath"),
        "description": meta.get("shortDescription") or "",
        "long_description": meta.get("longDescription") or "",
    }


# ── SSH: exportar ────────────────────────────────────────────────────────────

def exportar(ssh, cfg: ConfigISX, caminho: str, *, job: str, teto_s: int = EXPORT_TETO_S) -> bytes:
    """`istool export` no servidor, arquivo temporário único na pasta privada,
    leitura por SFTP com teto (o `st_size` pode mudar entre o `stat` e a leitura),
    `remove` em `finally` (sucesso ou falha). `stderr` do istool vai ao `interno`
    (log), nunca à resposta."""
    archive = nome_archive(cfg, job)
    remoto = caminho_sftp(archive)
    comando = comando_istool(cfg, caminho, archive)
    with ssh() as (executar, sftp):
        try:
            rc, saida, erro = executar(comando, teto_s)
            if rc != 0:
                texto = (str(erro) + " " + str(saida)).lower()
                nao_achou = any(m in texto for m in _MARCAS_NAO_ENCONTRADO)
                raise ISXError(
                    502, "O istool falhou ao exportar o job — detalhe registrado no log da API.",
                    interno=f"rc={rc} stderr={str(erro)[-800:]!r} stdout={str(saida)[-300:]!r}",
                    resultado="nao_encontrado" if nao_achou else "erro")
            try:
                st = sftp.stat(remoto)
            except OSError as e:
                raise ISXError(
                    502, "O istool terminou sem gerar o arquivo — detalhe registrado no log da API.",
                    interno=f"stat {remoto}: {e!r} stdout={str(saida)[-300:]!r}") from e
            tamanho = int(getattr(st, "st_size", 0) or 0)
            if tamanho > ISX_MAX_BYTES:
                raise ISXError(413, f"O export do job tem {tamanho} bytes, acima do teto de {ISX_MAX_BYTES}.")
            with sftp.open(remoto, "rb") as fl:
                dados = fl.read(ISX_MAX_BYTES + 1)
            if len(dados) > ISX_MAX_BYTES:
                raise ISXError(413, f"O export do job passa do teto de {ISX_MAX_BYTES} bytes.")
        finally:
            try:
                sftp.remove(remoto)
            except Exception:  # noqa: BLE001 — limpeza best-effort
                pass
    return dados


def exportar_job(ssh, cfg: ConfigISX, engine: str, projeto: str, folder_path, job: str, tipo: str,
                 *, teto_s: int = EXPORT_TETO_S) -> tuple[bytes, str]:
    """`exportar` sobre os candidatos de `caminhos_istool`, em ordem (SEQUENCE: `.qjb`,
    depois `.sjb`). "not found"/"No assets matched" do istool → próximo candidato;
    esgotou → 404; qualquer outra falha → a ISXError original (502/413), sem insistir.
    Devolve (bytes do .isx, caminho que funcionou)."""
    ultimo: ISXError | None = None
    for caminho in caminhos_istool(engine, projeto, folder_path, job, tipo):
        try:
            return exportar(ssh, cfg, caminho, job=job, teto_s=teto_s), caminho
        except ISXError as e:
            if e.status == 502 and e.resultado == "nao_encontrado":
                ultimo = e
                continue
            raise
    raise ISXError(404, "Job não encontrado no repositório do DataStage pelo istool — confira projeto, pasta e nome.",
                   interno=ultimo.interno if ultimo else None, resultado="nao_encontrado")


# ── Parse do XML ─────────────────────────────────────────────────────────────

def _simples(tag: str) -> str:
    return tag.split("}")[-1]


def _xtype(elem) -> str:
    return (elem.get(XSI + "type") or elem.get("type") or "").split(":")[-1]


def _cdata(dec: str, tag: str) -> str | None:
    """Conteúdo de `<tag …>…</tag>` (com ou sem CDATA), por `str.find` — uma regex
    com `.*?` aqui era quadrática num XMLProperties hostil."""
    abre = "<" + tag
    i = dec.find(abre)
    while i != -1:
        k = i + len(abre)
        if k < len(dec) and dec[k] in ">/ \t\r\n":
            break
        i = dec.find(abre, k)
    if i == -1:
        return None
    fim_abre = dec.find(">", i)
    if fim_abre == -1:
        return None
    fecha = dec.find("</" + tag + ">", fim_abre + 1)
    if fecha == -1:
        return None
    corpo = dec[fim_abre + 1:fecha].strip()
    if corpo.startswith("<![CDATA["):
        corpo = corpo[len("<![CDATA["):]
        j = corpo.find("]]>")
        if j != -1:
            corpo = corpo[:j]
    v = corpo.strip()
    return v or None


def _propriedades_xml(valor: str) -> dict:
    """O `XMLProperties` de um conector é um XML embutido, escapado, no atributo
    `valueExpression`. Devolve database_name/hint e a primeira SQL encontrada.
    Username/Password NUNCA saem daqui."""
    dec = html.unescape(valor or "")
    r: dict = {}
    ds = _cdata(dec, "DataSource")
    if ds:
        if ds.startswith("#"):
            hint = _RE_DB_HINT.search(ds)
            r["database_hint"] = hint.group(1) if hint else ds
            r["database_name"] = r["database_hint"]
        else:
            r["database_name"] = ds
    for tag in _TAGS_SQL:
        sql = _cdata(dec, tag)
        if sql:
            r["sql_expression"] = sql
            r["sql_tag"] = tag
            break
    return r


def _colunas(pin) -> list[dict]:
    cols = []
    for bag in pin:
        if _simples(bag.tag) != "has_DSMetaBag":
            continue
        for m in bag:
            if _simples(m.tag) != "has_DSMetaData":
                continue
            nome = m.get("name") or ""
            ext = m.get("extendedType") or ""
            base = m.get("type") or ""
            # Coluna tem tipo; metadado de propriedade (RTColumnProp, dataset=…) tem só `value`.
            if not nome or nome == "RTColumnProp" or not (ext or base):
                continue
            tam = None
            mt = _RE_LEN.search(ext)
            if mt:
                tam = int(mt.group(1))
                tipo = re.sub(r"\[.*\]", "", ext).strip()
            else:
                tipo = ext or base
            cols.append({"name": nome, "type": tipo or None, "length": tam})
    return cols


def _arquivo_dos_pins(stage) -> str | None:
    """Fallback do path de arquivo: `has_DSMetaData name="dataset|file|filename"
    value="…"` dentro de um pin (documento de origem, §5.7)."""
    for pin in stage:
        if _simples(pin.tag) not in ("has_InputPin", "has_OutputPin"):
            continue
        for bag in pin:
            if _simples(bag.tag) != "has_DSMetaBag":
                continue
            for m in bag:
                if _simples(m.tag) == "has_DSMetaData" and (m.get("name") or "").lower() in ("dataset", "file", "filename") \
                        and m.get("value"):
                    return m.get("value")
    return None


def _mainloop(bruto: str) -> str | None:
    """`mainloop { … \\n}` do TrxGenCode por `str.find` (a regex `.+?` era quadrática)."""
    i = bruto.find("mainloop")
    while i != -1:
        k = i + len("mainloop")
        while k < len(bruto) and bruto[k] in " \t\r\n":
            k += 1
        if k < len(bruto) and bruto[k] == "{":
            j = bruto.find("\n}", k + 1)
            return bruto[i:j + 2] if j != -1 else None
        i = bruto.find("mainloop", k)
    return None


def _apt_code(stage) -> str | None:
    for m in stage.iter():
        if _simples(m.tag) == "has_DSMetaData" and m.get("name") == "TrxGenCode":
            bruto = html.unescape(m.get("value") or "").replace("\r\n", "\n").replace("\r", "\n")
            trecho = _mainloop(bruto)
            return (trecho if trecho else bruto).strip() or None
    return None


def _expressoes(stage) -> list[dict]:
    saida = []
    for d in stage.iter():
        if _simples(d.tag) != "hasValue_Derivation":
            continue
        expr = d.get("expression") or ""
        if not expr:
            continue
        saida.append({"output_col": d.get("name") or "", "expression": expr, "source_col": d.get("sourceColumn") or ""})
    return saida


def _fluxo(root) -> list[dict]:
    for dv in root:
        if _simples(dv.tag) != "has_DSDesignView":
            continue
        info = dv.get("lazyLoadInfo") or ""
        por_id: dict[str, dict] = {}
        setas = []
        # Parallel separa os blocos por " StageID="; sequence por "StageID=" sem espaço.
        for blk in [b for b in re.split(r"\s*StageID=", info) if b.strip()]:
            sid = re.match(r"^(\w+)", blk)
            nome = re.search(r"StageNames=([^|]+)", blk)
            tipo = re.search(r"StageTypeIDs=([^|]+)", blk)
            links = re.findall(r"LI=LinkNames=([^|]+)\|LI=TargetStageIDs=([^|\s]+)", blk)
            if sid and nome:
                por_id["V0S" + sid.group(1)] = {"name": nome.group(1), "type": tipo.group(1) if tipo else ""}
            for lnomes, alvos in links:
                # Vários links do mesmo stage vêm separados por vírgula nos dois lados.
                ln, al = lnomes.split(","), alvos.split(",")
                pares = list(zip(ln, al)) if len(ln) == len(al) else [(lnomes, alvos)]
                for lnome, alvo in pares:
                    if nome and lnome and alvo:
                        setas.append({"from": nome.group(1), "from_type": tipo.group(1) if tipo else "",
                                      "link": lnome, "to_id": alvo})
        def resolver(to_id: str) -> dict:
            # Parallel referencia V0S<id>; sequence usa outro prefixo (V22S3) com o mesmo <id>.
            d = por_id.get(to_id)
            if d is None:
                m = re.match(r"^V\d+S(\w+)$", to_id)
                d = por_id.get("V0S" + m.group(1)) if m else None
            return d or {}

        return [{"from": a["from"], "from_type": a["from_type"], "link": a["link"],
                 "to": resolver(a["to_id"]).get("name", a["to_id"]),
                 "to_type": resolver(a["to_id"]).get("type", "")} for a in setas]
    return []


def _valor_param(stage, *nomes: str) -> str | None:
    """`has_ParameterVal` por `parameterName` OU `Name` (o DataSet usa `Name`)."""
    alvos = {n.lower() for n in nomes}
    for pv in stage:
        if _simples(pv.tag) != "has_ParameterVal":
            continue
        chave = (pv.get("parameterName") or pv.get("Name") or pv.get("name") or "").lower()
        if chave in alvos:
            return pv.get("valueExpression") or pv.get("value") or ""
    return None


def _filhos_sequence(stages: list) -> list[dict]:
    """Só atividades de job COM `JobName`: sem ele, o nome da atividade seria um chute
    (vai para `nao_reconhecidos` no parse)."""
    return [{"job_name": st["_job_filho"], "activity": st["stage_name"]}
            for st in stages if st["stage_type_raw"] == "CJobActivity" and st.get("_job_filho")]


def _membro_principal(zf: zipfile.ZipFile, job: str | None = None) -> tuple[str, bytes]:
    """O `.pjb`/`.sjb` do job: prefere o membro cujo nome-base é o job pedido; sem
    isso, um `.sjb/.qjb` (sequence exportado com filhos traz vários membros) e por
    fim a ordem alfabética. Teto de tamanho ANTES de descomprimir (o `file_size`
    do cabeçalho) e DEPOIS (leitura com teto: o cabeçalho pode mentir)."""
    nomes = [n for n in zf.namelist() if n.lower().endswith((".pjb", ".sjb", ".qjb"))]
    if not nomes:
        raise ISXError(422, "O .isx não contém definição de job (.pjb/.sjb).")
    alvo = (job or "").strip().lower()

    def chave(n: str):
        base = posixpath.basename(n).rsplit(".", 1)[0].lower()
        return (0 if alvo and base == alvo else 1, 0 if n.lower().endswith((".sjb", ".qjb")) else 1, n)

    nomes.sort(key=chave)
    nome = nomes[0]
    if zf.getinfo(nome).file_size > ISX_MAX_BYTES:
        raise ISXError(413, "A definição do job passa do teto de tamanho.")
    try:
        with zf.open(nome) as fl:
            dados = fl.read(ISX_MAX_BYTES + 1)
    except Exception as e:  # noqa: BLE001 — ZIP cifrado, compressão exótica, dado corrompido
        raise ISXError(422, "Não foi possível descomprimir a definição do job dentro do .isx.") from e
    if len(dados) > ISX_MAX_BYTES:
        raise ISXError(413, "A definição do job passa do teto de tamanho.")
    return nome, dados


def parse_isx(dados: bytes, mapa: dict[str, dict] | None = None, *, job: str | None = None) -> dict:
    """ZIP → XML `DSJobDefSDO` → dict com job, parâmetros, stages, fluxo, filhos.
    Tolerante com o que não reconhece (vai para `nao_reconhecidos`), mas NUNCA cala
    um formato inesperado: raiz que não é `DSJobDefSDO` ou job sem stage → 422.
    `job` (opcional) escolhe o membro do ZIP quando há vários; quem chama confere
    `job_name` com o job pedido."""
    if len(dados) > ISX_MAX_BYTES:
        raise ISXError(413, f"O .isx tem {len(dados)} bytes, acima do teto de {ISX_MAX_BYTES}.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(dados))
    except Exception as e:  # noqa: BLE001 — BadZipFile e primos
        raise ISXError(422, "O arquivo devolvido pelo istool não é um .isx (ZIP) válido.") from e
    with zf:
        membro, xml_bytes = _membro_principal(zf, job)
    baixo = xml_bytes.lower()
    if any(marca in baixo for marca in _MARCAS_DTD):
        raise ISXError(422, "A definição do job traz DOCTYPE/ENTITY — recusada por segurança.")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ISXError(422, f"XML da definição do job inválido ({e}).") from e
    if _simples(root.tag) != "DSJobDefSDO":
        raise ISXError(422, f"XML inesperado no .isx: raiz {_simples(root.tag)!r} em vez de DSJobDefSDO.")

    nao: list[dict] = []
    tipo = "SEQUENCE" if (root.get("jobType") or "").lower().startswith("seq") or membro.lower().endswith((".sjb", ".qjb")) else "PARALLEL"
    params = []
    stages_raw = []
    for filho in root:
        tag = _simples(filho.tag)
        if tag == "has_ParameterDef":
            nome_p = filho.get("name") or ""
            tipo_p = filho.get("extendedType") or filho.get("typeCode") or ""
            padrao = filho.get("defaultValue") or ""
            if padrao and (_RE_PARAM_SEGREDO.search(tipo_p) or _RE_PARAM_SEGREDO.search(nome_p)):
                padrao = "***"
            params.append({
                "name": nome_p,
                "type": tipo_p,
                "default": padrao,
                "description": filho.get("longDescription") or filho.get("shortDescription") or "",
            })
        elif tag == "contains_JobObject" and "Stage" in _xtype(filho):
            stages_raw.append(filho)
    if not stages_raw:
        raise ISXError(422, "A definição do job não tem nenhum stage — .isx inesperado.")

    stages = []
    for st in stages_raw:
        stype = st.get("stageType") or ""
        classe, rotulo, reconhecido = classe_do_tipo(stype, mapa)
        if not reconhecido:
            nao.append({"stage": st.get("name") or "", "stage_type": stype, "motivo": "tipo fora do mapa"})
        contexto = _valor_param(st, "Context")
        tags_filhos = {_simples(c.tag) for c in st}
        tem_in = bool((st.get("inputPins") or "").strip()) or "has_InputPin" in tags_filhos
        tem_out = bool((st.get("outputPins") or "").strip()) or "has_OutputPin" in tags_filhos
        item: dict = {
            "stage_name": st.get("name") or "",
            "stage_type_raw": stype,
            "internal_id": st.get("internalID") or "",
            "direction": direcao(classe, contexto, tem_in, tem_out),
            "object_type": rotulo if classe else stype,
            "classe": classe,
            "database_name": None, "database_hint": None, "sql_expression": None, "sql_tag": None,
            "file_path": None,
            "output_columns": [], "input_columns": [],
            "apt_code": None, "expressions": [],
        }
        xmlprops = _valor_param(st, "XMLProperties")
        if xmlprops:
            item.update({k: v for k, v in _propriedades_xml(xmlprops).items() if k in item})
        if classe == "arquivo" or not classe:
            caminho = _valor_param(st, "dataset", "file", "filename", "path") or _arquivo_dos_pins(st)
            if caminho:
                item["file_path"] = caminho
        for pin in st:
            t = _simples(pin.tag)
            if t == "has_OutputPin":
                item["output_columns"].extend(_colunas(pin))
            elif t == "has_InputPin":
                item["input_columns"].extend(_colunas(pin))
        if classe in ("transformacao", "sequence") or stype in ("CTransformerStage", "TransformerStage"):
            item["apt_code"] = _apt_code(st)
            item["expressions"] = _expressoes(st)
        if stype == "CJobActivity":
            # O job chamado fica no ATRIBUTO `jobname` do stage (documento de origem, §5b);
            # o has_ParameterVal JobName é o fallback.
            filho_nome = (st.get("jobname") or st.get("jobName") or st.get("JobName")
                          or _valor_param(st, "JobName", "job", "jobname") or "").strip()
            if filho_nome:
                item["_job_filho"] = filho_nome
            else:
                nao.append({"stage": item["stage_name"], "stage_type": stype, "motivo": "atividade de job sem JobName"})
        stages.append(item)

    fluxo = _fluxo(root)
    # Destino sem schema no design (DataSet): herda as colunas de saída de quem o alimenta.
    por_nome = {s["stage_name"]: s for s in stages}
    for seta in fluxo:
        alvo = por_nome.get(seta["to"])
        origem = por_nome.get(seta["from"])
        if alvo is not None and origem is not None and not alvo["input_columns"] and origem["output_columns"]:
            alvo["input_columns"] = list(origem["output_columns"])

    filhos = _filhos_sequence(stages) if tipo == "SEQUENCE" or any(s["stage_type_raw"] == "CJobActivity" for s in stages) else []
    for s in stages:
        s.pop("_job_filho", None)
    return {
        "job_name": root.get("name") or "",
        "job_type": tipo,
        "job_description": root.get("shortDescription") or "",
        "job_long_description": root.get("longDescription") or "",
        "created_by": root.get("createdByUser") or "",
        "modified_by": root.get("modifiedByUser") or "",
        "last_modification_xml": root.get("lastModificationTimestamp") or "",
        "nls_map": root.get("nLSMapName") or "",
        "membro": membro,
        "parameters": params,
        "stages": stages,
        "flow": fluxo,
        "children": filhos,
        "nao_reconhecidos": nao,
        "isx_sha256": hashlib.sha256(dados).hexdigest(),
        "isx_bytes": len(dados),
    }


def rotulo_objeto(classe: str | None) -> str:
    return CATEGORIA_POR_CLASSE.get(classe or "", "") or ""
