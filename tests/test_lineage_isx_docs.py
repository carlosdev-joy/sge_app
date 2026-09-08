# -*- coding: utf-8 -*-
"""F5 do lineage ISX (spec docs/spec-lineage-isx.md): manual, release note, smoke e
backlog existem, batem com o código e não carregam segredo nem host real.

Anti-drift de documentação: se alguém renomear a aba, um endpoint ou uma variável
de ambiente sem tocar nos documentos, aqui quebra.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "MANUAL_USUARIO.md"
RELEASE = ROOT / "docs" / "release-notes" / "lineage-isx.md"
SPEC = ROOT / "docs" / "spec-lineage-isx.md"
SMOKE = ROOT / "scripts" / "smoke_lineage_isx.sh"
BACKLOG = ROOT / "sql" / "backlog" / "lineage_isx.sql"

# Tudo que o código lê do ambiente tem de estar explicado para quem faz o deploy.
VARIAVEIS = ("DS_ENGINE", "DS_API_URL", "DS_API_USER", "DS_API_PASSWORD", "DS_API_VERIFY_SSL",
             "DS_ISTOOL_HOME", "DS_ISTOOL_LAUNCHER", "DS_ISTOOL_DOMAIN", "DS_ISTOOL_AUTHFILE",
             "DS_ISTOOL_TMP", "DS_ISTOOL_CFG", "DS_SSH_KNOWN_HOSTS", "AIRFLOW_CONN_ORQUESTRA_API")
ENDPOINTS = ("/lineage/isx/localizar", "/lineage/isx/extrair", "/lineage/isx/job",
             "/lineage/isx/pipeline", "/lineage/isx/lote")
# Nenhum documento pode trazer senha literal, host real ou o `-password` do istool.
# valor "de verdade" = 3+ caracteres de senha; `password=`)` (doc do formato) e `<senha>` não casam
_SEGREDO = re.compile(r"(?i)(?:password|senha)\s*[=:]\s*['\"]?[A-Za-z0-9@#%^&+./:_-]{3,}")
# credencial embutida em URL (http://usuario:senha@host) — só placeholders <usuario>:<senha>@ passam
_URL_CRED = re.compile(r"://[^<\s:/@]+:[^<\s@/]+@")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PROIBIDOS = (".intranet", "lnxprd", "-password ")


def _sem_segredo(texto: str, nome: str) -> None:
    for m in _SEGREDO.finditer(texto):
        trecho = m.group(0)
        # `password=` seguido de placeholder (<senha>, ***, …) ou o nome de outra variável é doc, não segredo
        assert re.search(r"(?i)(?:password|senha)\s*[=:]\s*(?:<|\*|\$|DS_|senha\b|password\b)", trecho), f"{nome}: {trecho!r}"
    assert _URL_CRED.search(texto) is None, f"{nome}: credencial embutida em URL: {_URL_CRED.search(texto).group(0)!r}"
    for ip in _IPV4.findall(texto):
        assert ip in ("127.0.0.1", "0.0.0.0"), f"{nome}: IP real {ip!r}"
    for p in _PROIBIDOS:
        assert p not in texto, f"{nome}: {p!r}"


# ═══════════ manual ═══════════════════════════════════════════════════════════

def test_manual_tem_as_secoes_do_lineage_isx():
    texto = MANUAL.read_text(encoding="utf-8")
    assert "### 3.9 Lineage automático do job DataStage" in texto
    assert "### 4.8 Lineage ISX (DataStage)" in texto
    # a aba aparece no perfil Consulta (§1.4) e nas linhas de perfil
    sec14 = texto[texto.index("### 1.4 Governança"):texto.index("### 1.5")]
    assert "**Job DataStage**" in sec14 and "§3.9" in sec14
    perfis = texto[texto.index("## Perfis de acesso"):texto.index("## 1. Perfil Consulta")]
    assert "Job DataStage" in perfis and "lote do lineage" in perfis
    # o que o usuário vê tem o nome que a tela usa
    sec39 = texto[texto.index("### 3.9"):texto.index("## 4. Perfil Administrador")]
    for rotulo in ("Extrair", "Atualizar", "não extraído", "não é job DataStage", "dados do cache",
                   "extraído agora do DataStage", "fora deste pipeline", "Jobs chamados por esta sequence",
                   "job só com pipeline", "60 s"):
        assert rotulo in sec39, rotulo
    # frases da API que o usuário vai ler, na tabela de mensagens
    for frase in ("Outra extração do job", "não terminou em 60 s", "não encontrado no repositório do DataStage",
                  "tipo fora do mapa"):
        assert frase in sec39, frase
    # o admin sabe configurar: variáveis, authfile, lote, mapa de tipos, migration
    sec48 = texto[texto.index("### 4.8"):texto.index("## 5. Perguntas frequentes")]
    for v in VARIAVEIS:
        assert v in sec48, v
    for trecho in ("-authfile", "600", "etl_lineage_extract_isx", "Extrair todos (lote)", "etl_stage_type_map",
                   "106", "acao_editar", "host key", "GET /lineage"):
        assert trecho in sec48, trecho
    assert "-password" not in sec48.replace("nunca `-password`", "").replace("nunca -password", "")
    faq = texto[texto.index("## 5. Perguntas frequentes"):]
    assert faq.count("Job DataStage") >= 3
    _sem_segredo(sec39 + sec48 + faq, "MANUAL_USUARIO.md")


# ═══════════ release note ═════════════════════════════════════════════════════

def test_release_note_bate_com_o_codigo():
    texto = RELEASE.read_text(encoding="utf-8")
    assert "**Migration:** **106**" in texto and "106_lineage_isx.sql" in texto
    assert "docs/spec-lineage-isx.md" in texto and "MANUAL_USUARIO.md" in texto
    for pr in ("#369", "#370", "#371", "#373"):
        assert pr in texto, pr
    for e in ENDPOINTS:
        assert e in texto, e
    for v in VARIAVEIS:
        assert v in texto, v
    for trecho in ("-authfile", "etl_lineage_extract_isx", "etl_ds_job_isx", "isx_auto", "acao_editar",
                   "## 🚀 Deploy", "## ⚠️ Limites conhecidos", "airflow-worker", "GET /lineage",
                   "sql/backlog/lineage_isx.sql", "smoke_lineage_isx.sh"):
        assert trecho in texto, trecho
    _sem_segredo(texto, "release-notes/lineage-isx.md")


def test_spec_concluida_e_smoke_fechado():
    texto = SPEC.read_text(encoding="utf-8")
    assert "Status: **concluída**" in texto
    assert "#373" in texto
    sec7 = texto[texto.index("## 7. Smoke pós-deploy"):texto.index("## 8. Pendências")]
    assert "c–i e k" in sec7 and "Resultado no DEV" in sec7


# ═══════════ smoke ════════════════════════════════════════════════════════════

def test_smoke_fechado_cobre_o_lote_e_imprime_o_roteiro():
    texto = SMOKE.read_text(encoding="utf-8")
    r = subprocess.run(["bash", "-n", str(SMOKE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for trecho in ("/lineage/isx/lote", "/lineage/isx/lote/$(enc", "SMOKE_LOTE", "LOTE_TETO_S", "403",
                   "success|failed", "roteiro manual", "set -euo pipefail"):
        assert trecho in texto, trecho
    # itens manuais listados no roteiro
    for item in ("a) migration 106", "b) .env da API", "j) Governança", "l) de dentro do worker", "m) log da API"):
        assert item in texto, item
    # a senha nunca vai para o argv nem para a tela
    assert "ORQ_PASS" not in texto.split("echo \"▶ login\"")[1].split("ok \"token obtido\"")[0].replace(
        'os.environ["ORQ_PASS"]', "")
    assert 'echo "$ORQ_PASS' not in texto and "-d \"$ORQ_PASS" not in texto
    _sem_segredo(texto, "smoke_lineage_isx.sh")


# ═══════════ backlog ══════════════════════════════════════════════════════════

_TITULO = re.compile(r"^\(N'((?:[^']|'')+)',\s*$", re.M)


@pytest.fixture(scope="module")
def backlog():
    return BACKLOG.read_text(encoding="utf-8")


def test_backlog_idempotente_por_titulo(backlog):
    assert "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_backlog b WHERE b.titulo = i.titulo)" in backlog
    assert "IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL" in backlog
    assert "N'spec-lineage-isx-f5'" in backlog and "N'#369-#371,#373'" in backlog
    titulos = _TITULO.findall(backlog)
    assert len(titulos) >= 10, titulos
    assert len(set(titulos)) == len(titulos), "título repetido"
    for t in titulos:
        assert t.startswith("Lineage"), t
        assert len(t) <= 200, t
    # o que a spec pediu para o backlog está lá (§5 F5)
    for tema in ("contexto para IA", "filhos do sequence em cadeia", "mapa de tipos de stage",
                 "expurgo de cabeçalhos", "stage_type × type_raw", "NVARCHAR", "DS_API_VERIFY_SSL",
                 "Parameter Set"):
        assert any(tema in t for t in titulos), tema
    _sem_segredo(backlog, "backlog/lineage_isx.sql")


def test_backlog_valores_dentro_do_dominio(backlog):
    # tipo feature|bug|debt|spike; area backend|frontend|datastage|deploy|infra|outro; prioridade P0..P3
    linhas = re.findall(r"^\s*N'(feature|bug|debt|spike)',\s*N'(backend|frontend|datastage|deploy|infra|outro)',"
                        r"\s*N'(P[0-3])',\s*N'([a-z,]+)'\)[,;]$", backlog, re.M)
    assert len(linhas) == len(_TITULO.findall(backlog)), "cada item tem tipo/area/prioridade/tags válidos"
    for _, _, _, tags in linhas:
        assert "lineage" in tags.split(","), tags
    # o backlog anterior (utilitários) continua com o mesmo formato — o runner do Admin lê os dois
    anterior = (ROOT / "sql" / "backlog" / "utilitarios_transferencia.sql").read_text(encoding="utf-8")
    assert "INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por, ref_pr)" in anterior
    assert "INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por, ref_pr)" in backlog
