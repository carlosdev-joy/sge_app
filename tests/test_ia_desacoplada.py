"""Teste de desacoplamento da F0 (docs/spec-agentes-datastage.md): a camada
de IA (api/services/ia_provedor.py, dags/utils/triagem_ia.py) não depende do
módulo Caixa Seguro — e os dois lados (API e dags/, que NÃO se importam)
concordam sobre o nome de cada chave.

O que estes testes prendem, e por que cada um existe:

  1. **O módulo antigo não existe mais duas vezes.** `caixa_ia.py` foi
     RENOMEADO para `ia_provedor.py` — se alguém recriar o arquivo antigo
     (ex.: resolvendo um conflito de merge errado), volta a ter dois módulos
     lendo/gravando a mesma tabela por caminhos diferentes.

  2. **Nada fora do módulo Caixa importa o nome antigo.** Um `from services
     import caixa_ia` esquecido em algum router quebraria em `ImportError`
     assim que o arquivo fosse de fato apagado.

  3. **api/ e dags/ concordam sobre `_LEGADO` — o risco mais caro de errar
     em silêncio.** `dags/utils/triagem_ia.py` não importa de `api/` (o
     worker não tem aquela árvore no path — ver o docstring de
     `triagem_ia.py`), então cada lado mantém sua PRÓPRIA cópia do mapa
     chave-nova → chave-antiga. Se alguém trocar um nome só de um lado (ex.:
     um PR que mexe só em `dags/`), os dois lados passam a ler chaves
     DIFERENTES da mesma tabela sem nenhum erro — a triagem lê uma
     configuração e o Maestro lê outra, cada um "funcionando", mas sobre
     dados diferentes. É exatamente o risco 21 da spec ("Espelho api × dags
     diverge"), e é o tipo de divergência que passa limpo no `pytest` de
     cada módulo isoladamente — só aparece comparando os dois lado a lado,
     que é o que este arquivo faz.

  4. **`caixa_ia_enabled` nunca aparece como par de uma chave nova**, dos
     dois lados: ele é do módulo Caixa, não do provedor compartilhado, e
     "migrar" ele por engano ligaria/desligaria o Maestro ou a triagem junto
     com os assistentes Diego/Lari/Léo.

  5. **`"Caixa Seguro IA"` (o texto da aba antiga) só sobrevive onde é
     esperado.** Fora do módulo Caixa e de migrations antigas, o texto que o
     usuário vê deve dizer "Admin › IA" — sobrar o nome antigo é o sintoma
     mais visível de um lugar que a F0 esqueceu de atualizar.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))
sys.path.insert(0, str(RAIZ / "dags"))

from services import ia_provedor  # noqa: E402
from utils import triagem_ia  # noqa: E402

# Arquivos onde "caixa_ia"/"Caixa Seguro IA" é esperado: o módulo Caixa em si
# (assistentes Diego/Lari/Léo), migrations (registro histórico — nunca
# reescritas) e este próprio arquivo de teste (que precisa CITAR os nomes
# para testá-los).
_PERMITIDO_CAIXA_IA = (
    "api/routers/caixa_chat.py",
    "tests/test_ia_desacoplada.py",
)
_PERMITIDO_TEXTO_ANTIGO = ("sql/migrations/",)


def _grep(raiz: Path, termo: str, extensoes: tuple[str, ...]) -> list[Path]:
    """Arquivos (relativos a `raiz`) cujo conteúdo cita `termo`, ignorando
    dist/, node_modules/ e o próprio .git — sem depender do `grep` do
    sistema, para o teste rodar igual em qualquer ambiente de CI."""
    achados: list[Path] = []
    for caminho in raiz.rglob("*"):
        if caminho.is_dir():
            continue
        if caminho.suffix not in extensoes:
            continue
        partes = caminho.relative_to(raiz).parts
        # ".claude/worktrees": checkouts de OUTRAS branches (agentes em
        # paralelo) que o próprio Claude Code cria dentro do repo — têm o
        # caixa_ia.py antigo e o Admin.tsx velho, e não são código desta
        # branch; sem isso o teste falha em quem tem um worktree aberto.
        if any(p in ("dist", "node_modules", ".git", "__pycache__", "worktrees")
               for p in partes):
            continue
        try:
            texto = caminho.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if termo in texto:
            achados.append(caminho.relative_to(raiz))
    return achados


# ═══════════ 1. o módulo antigo não existe mais ═════════════════════════════

def test_arquivo_antigo_nao_existe():
    assert not (RAIZ / "api" / "services" / "caixa_ia.py").exists(), (
        "caixa_ia.py foi RENOMEADO para ia_provedor.py na F0 — os dois não "
        "podem coexistir, ou passam a ler/gravar a mesma tabela por dois "
        "caminhos.")


def test_ia_provedor_existe():
    assert (RAIZ / "api" / "services" / "ia_provedor.py").exists()


# ═══════════ 2. nada fora do Caixa importa o nome antigo ═══════════════════

_RE_IMPORT_ANTIGO = re.compile(
    r"^\s*(from\s+services\s+import\s+[^#\n]*\bcaixa_ia\b"
    r"|import\s+services\.caixa_ia\b)", re.MULTILINE)


def test_nenhum_import_python_do_modulo_antigo():
    ofensores = []
    for pasta in ("api", "dags", "tests"):
        for py in (RAIZ / pasta).rglob("*.py"):
            rel = py.relative_to(RAIZ).as_posix()
            if "__pycache__" in rel:
                continue
            texto = py.read_text(encoding="utf-8", errors="ignore")
            if _RE_IMPORT_ANTIGO.search(texto):
                ofensores.append(rel)
    assert ofensores == [], (
        f"import do módulo antigo (services.caixa_ia) sobrevivendo em: {ofensores}")


# ═══════════ 3. api/ e dags/ concordam sobre _LEGADO (risco 21) ════════════

def test_legado_de_api_e_dags_e_identico():
    """`ia_provedor._LEGADO` e `triagem_ia._LEGADO` são mantidos por mão em
    dois arquivos que não se importam (dags/ não enxerga api/ no worker) —
    a trava é este teste, não o Python. A triagem não lê `ultima_verificacao`
    (não é dela — só o Admin verifica e grava o laudo), então o dict dela é
    um SUBCONJUNTO do de ia_provedor; nas chaves em comum, os pares
    precisam ser byte-a-byte iguais."""
    for nova, antiga in triagem_ia._LEGADO.items():
        assert nova in ia_provedor._LEGADO, (
            f"{nova} existe em triagem_ia._LEGADO mas não em ia_provedor._LEGADO "
            "(risco 21 da spec: os dois lados precisam concordar)")
        assert ia_provedor._LEGADO[nova] == antiga, (
            f"{nova} mapeia para chaves DIFERENTES em cada lado: "
            f"ia_provedor diz {ia_provedor._LEGADO[nova]!r}, triagem_ia diz {antiga!r} "
            "(risco 21 da spec)")
    extra = set(ia_provedor._LEGADO) - {ia_provedor.K_ULTIMA_VERIF} - set(triagem_ia._LEGADO)
    assert extra == set(), (
        f"chave(s) nova(s) em ia_provedor._LEGADO sem par em triagem_ia._LEGADO "
        f"(e não é ultima_verificacao, que a triagem legitimamente não lê): {extra}")


def test_legado_cobre_exatamente_as_chaves_do_provedor():
    """Nenhuma chave K_* (além de K_ENABLED) fica de fora de _LEGADO, dos
    dois lados — senão load_config()/config_da_triagem() silenciosamente
    param de cair para o valor antigo para essa chave."""
    esperadas = {ia_provedor.K_PROVIDER, ia_provedor.K_MODEL,
                 ia_provedor.K_BASE_URL, ia_provedor.K_API_KEY,
                 ia_provedor.K_USA_PROXY, ia_provedor.K_ULTIMA_VERIF}
    assert set(ia_provedor._LEGADO) == esperadas
    # A triagem não lê ultima_verificacao (não é dela) — sua fatia de
    # _LEGADO é um subconjunto, e mesmo assim IDÊNTICO ao de ia_provedor
    # nas chaves que os dois compartilham (conferido no teste anterior).
    assert set(triagem_ia._LEGADO) == {
        triagem_ia.K_PROVIDER, triagem_ia.K_MODEL, triagem_ia.K_BASE_URL,
        triagem_ia.K_API_KEY, triagem_ia.K_USA_PROXY}


def test_enabled_nao_e_par_de_nenhuma_chave_nova_dos_dois_lados():
    assert ia_provedor.K_ENABLED == "caixa_ia_enabled"
    assert ia_provedor.K_ENABLED not in ia_provedor._LEGADO
    assert ia_provedor.K_ENABLED not in ia_provedor._LEGADO.values()
    assert triagem_ia.K_HABILITADA == "chamados_triagem_habilitada"
    assert "caixa_ia_enabled" not in triagem_ia._LEGADO.values()


def test_nomes_novos_seguem_o_padrao_ia_e_antigos_caixa_ia():
    for nova, antiga in ia_provedor._LEGADO.items():
        assert nova.startswith("ia_"), nova
        assert antiga == f"caixa_ia_{nova[len('ia_'):]}", (nova, antiga)


# ═══════════ 4. texto residual ══════════════════════════════════════════════

def test_caixa_ia_so_citado_onde_e_esperado():
    achados = _grep(RAIZ, "caixa_ia", (".py", ".ts", ".tsx"))
    fora = [str(p) for p in achados
            if p.as_posix() not in _PERMITIDO_CAIXA_IA
            and "caixa" not in p.parts]  # api/routers/caixa_chat.py e
                                         # ui-react/src/caixa/** ficam de fora
    # O que sobra fora dessas duas árvores é o esperado: os módulos que
    # ESPELHAM a config (ia_provedor.py, triagem_ia.py, etl_servicenow_sync.py),
    # o admin.py com os aliases e o mask_secret, e os comentários de
    # maestro.py/email_config.py comparando o "mesmo gesto". Nenhum deles é
    # um bug — este teste documenta a lista para quem for auditar de novo.
    esperado_fora = {
        "api/routers/admin.py", "api/services/ia_provedor.py",
        "api/services/email_config.py", "api/services/maestro.py",
        "api/routers/maestro.py", "dags/etl_servicenow_sync.py",
        "dags/utils/triagem_ia.py", "tests/test_ia_provedor_config.py",
        "tests/test_triagem_ia.py", "tests/test_servicenow_config.py",
        # Aba ServiceNow (extraída de pages/Admin.tsx na F1 de
        # docs/spec-admin-reestruturacao.md): comentário comparando chaves.
        "ui-react/src/components/admin/abas/SondaServiceNowTab.tsx",
        # F1 (docs/spec-agentes-datastage.md): o dublê de cursor do teste da
        # rota de agentes simula as duas gerações de chave (ia_*/caixa_ia_*)
        # para provar que GET /agentes/status discrimina certo entre elas.
        "tests/test_agentes_rota.py",
        # F2: o mesmo dublê de cursor, agora no teste do endpoint de conversa.
        "tests/test_agentes_conversar_rota.py",
        # F2 de docs/spec-admin-reestruturacao.md: o registro do Admin declara
        # que as chaves legadas caixa_ia_* (espelhadas pelo ia_set) são da aba
        # IA › Provedor — é dado de posse de chave, não código novo de IA.
        "ui-react/src/lib/adminNav.ts",
        # F5: o espelho em Python desse mesmo registro (trava de escrita do
        # editor genérico) — idem, dado de posse de chave.
        "api/services/admin_config_donos.py",
    }
    inesperado = sorted(set(fora) - esperado_fora)
    assert inesperado == [], (
        f"'caixa_ia' aparece em arquivo(s) fora da lista esperada: {inesperado} "
        "— se é um lugar novo e legítimo (ex.: um comentário comparando o "
        "mesmo padrão de outro serviço), acrescente a `esperado_fora`; se é "
        "resíduo do desacoplamento, corrija.")


def test_texto_admin_caixa_seguro_ia_so_em_migration_antiga():
    """O texto 'Caixa Seguro IA' (rótulo da aba pré-F0) só sobrevive em
    migrations antigas — a aba mudou de nome para 'IA' em todo o resto."""
    achados = _grep(RAIZ, "Caixa Seguro IA", (".py", ".ts", ".tsx", ".sql"))
    este_arquivo = Path(__file__).resolve().relative_to(RAIZ).as_posix()
    fora = [str(p) for p in achados
            if not p.as_posix().startswith(_PERMITIDO_TEXTO_ANTIGO)
            and p.as_posix() != este_arquivo]
    assert fora == [], (
        f"'Caixa Seguro IA' sobrevivendo fora de migrations antigas: {fora} "
        "— o rótulo da aba é 'IA' desde a F0 (docs/spec-agentes-datastage.md).")
