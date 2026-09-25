"""Registro central do Admin — `ui-react/src/lib/adminNav.ts` (F2 de
docs/spec-admin-reestruturacao.md).

O registro é a fonte ÚNICA do sub-menu, da busca, do redirecionamento dos ids
antigos e (F5) do filtro de chaves órfãs. O que se prende aqui:

  1. **Nenhuma aba some e nenhuma aparece duas vezes** (leitura do fonte, sem
     Node): cada arquivo de `components/admin/abas/*.tsx` e as quatro abas de
     `components/admin/` (Utilitários, Agentes, Maestro, E-mail) é carregada
     por exatamente UMA entrada. Aba nova esquecida no registro = aba que
     ninguém acha; entrada duplicada = dois endereços para a mesma tela.
  2. **Slugs únicos e endereços estáveis**: (grupo, id) único; todo id antigo
     do Admin anterior à F2 resolve para uma aba que existe (link salvo em
     favorito, runbook ou migalha de outra tela não pode cair no vazio).
  3. **Bancada** (`tests/js/admin_nav_harness.cjs`, TS real via sucrase):
     busca normaliza acento e caixa, acha a aba pela chave de configuração
     (`teams_webhook` → Teams, `email_remetente` → E-mail), `xyz` volta vazio;
     o resolvedor redireciona ids antigos, com e sem grupo, e não confunde
     propriedades de Object (`constructor`) com id; a última aba sobrevive a
     localStorage quebrado. Sem Node/sucrase, SALTA (não finge).
  4. **Remanejamentos da F3**: Acesso em 3 abas, Triagem em IA, Bancos &
     Monitoramento numa aba só (o slug `monitoramento` da F2 redireciona), e
     `teams_webhook_url*` com dono (Teams).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
REGISTRO = FRONT / "lib" / "adminNav.ts"
ABAS_DIR = FRONT / "components" / "admin" / "abas"
ABAS_FORA = ("UtilitariosTab", "AgentesTab", "MaestroTab", "EmailTab")
HARNESS = RAIZ / "tests" / "js" / "admin_nav_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

# Ids do Admin antes da F2 (estado local de pages/Admin.tsx na F1).
IDS_ANTIGOS = (
    "config", "conexoes", "utilitarios", "tipos", "projetos", "versoes", "backlog", "servidor",
    "dags", "servicenow", "monitor", "fluxo_ds", "regen", "delete", "agenda", "usuarios",
    "comunicados", "notificacoes", "powerbi", "ia", "maestro", "agentes", "email", "sla",
)

# Slugs publicados na F2 que a F3 aposentou (a aba foi fundida em outra) —
# continuam resolvendo, como id antigo, para o endereço novo.
SLUGS_APOSENTADOS_F3 = {"monitoramento": "/admin/integracoes/bancos"}

TOTAL_ABAS = 26

GRUPOS = ("acesso", "ia", "comunicacao", "integracoes", "pipelines", "sistema")


def _fonte() -> str:
    return REGISTRO.read_text(encoding="utf-8")


def _entradas(fonte: str) -> list[str]:
    corpo = fonte.split("export const ABAS_ADMIN", 1)[1].split("\n]\n", 1)[0]
    return re.findall(r"\n  \{\n.*?\n  \},", corpo, re.S)


# ═══════════ 1. cada aba exatamente uma vez ════════════════════════════════

def _importadas(fonte: str) -> list[str]:
    return re.findall(r"import\('\.\./components/admin/(?:abas/)?(\w+)'\),\s*'(\w+)'", fonte)


def test_toda_aba_aparece_exatamente_uma_vez_no_registro():
    esperadas = sorted([p.stem for p in ABAS_DIR.glob("*.tsx")] + list(ABAS_FORA))
    assert len(esperadas) == TOTAL_ABAS, esperadas
    pares = _importadas(_fonte())
    # O import dinâmico e o nome exportado apontam para o MESMO componente.
    assert all(arq == nome for arq, nome in pares), pares
    assert sorted(arq for arq, _ in pares) == esperadas


def test_aba_de_abas_importada_pelo_caminho_certo():
    fonte = _fonte()
    for p in ABAS_DIR.glob("*.tsx"):
        assert f"import('../components/admin/abas/{p.stem}')" in fonte, p.stem
    for nome in ABAS_FORA:
        assert f"import('../components/admin/{nome}')" in fonte, nome


def test_uma_entrada_por_import_e_campos_obrigatorios():
    entradas = _entradas(_fonte())
    assert len(entradas) == TOTAL_ABAS
    for e in entradas:
        for campo in ("grupo:", "id:", "rotulo:", "descricao:", "palavrasChave:", "chavesConfig:", "componente: carregar("):
            assert campo in e, (campo, e[:120])


# ═══════════ 2. slugs e ids antigos ═══════════════════════════════════════

def test_slugs_unicos_e_grupos_validos():
    pares = [re.search(r"grupo:\s*'(\w+)',\s*id:\s*'([\w-]+)'", e).groups() for e in _entradas(_fonte())]
    assert len(set(pares)) == len(pares), "(grupo, id) repetido"
    ids = [i for _, i in pares]
    assert len(set(ids)) == len(ids), "slug repetido entre grupos confunde busca e ⌘K"
    assert {g for g, _ in pares} == set(GRUPOS)
    for _, i in pares:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i), f"slug fora do padrão de URL: {i}"


def test_todo_id_antigo_declarado_uma_vez():
    declarados = re.findall(r"idsAntigos:\s*\[([^\]]*)\]", _fonte())
    ids = [x for bloco in declarados for x in re.findall(r"'([\w-]+)'", bloco)]
    assert sorted(ids) == sorted(IDS_ANTIGOS + tuple(SLUGS_APOSENTADOS_F3))


def test_saidas_da_f4_marcadas():
    fonte = _fonte()
    for slug in ("sla", "powerbi-acessos", "fluxo-ds"):
        antes = fonte.split(f"id: '{slug}'", 1)[0].rsplit("\n  {", 1)[0]
        assert antes.rstrip().splitlines()[-1].strip().startswith("// sai na F4"), slug


# ═══════════ 3. bancada JS ════════════════════════════════════════════════

@pytest.fixture(scope="module")
def bancada() -> dict:
    node = shutil.which("node")
    if not node or not SUCRASE.is_dir():
        pytest.skip("Node/Sucrase indisponível")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_bancada_registro_completo(bancada):
    assert bancada["grupos"] == list(GRUPOS)
    assert len(bancada["abas"]) == TOTAL_ABAS
    assert all(a["lazy"] for a in bancada["abas"]), "toda aba é lazy (chunk próprio)"
    assert all(a["descricao"].endswith(".") and len(a["descricao"]) <= 120 for a in bancada["abas"])
    assert bancada["abas"][0]["grupo"] == "acesso" and bancada["abas"][0]["id"] == "usuarios"


def test_bancada_ids_antigos_resolvem(bancada):
    existentes = {f"/admin/{a['grupo']}/{a['id']}" for a in bancada["abas"]}
    assert set(bancada["idsAntigos"]) == set(IDS_ANTIGOS) | set(SLUGS_APOSENTADOS_F3)
    assert set(bancada["idsAntigos"].values()) <= existentes
    assert bancada["idsAntigos"]["config"] == "/admin/sistema/parametros"
    assert bancada["idsAntigos"]["notificacoes"] == "/admin/comunicacao/teams"
    assert bancada["idsAntigos"]["utilitarios"] == "/admin/integracoes/servidor-datastage"


def test_bancada_busca(bancada):
    b = bancada["busca"]
    assert b["teams_webhook"]["caminho"] == "/admin/comunicacao/teams"
    assert b["TEAMS_WEBHOOK"]["caminho"] == "/admin/comunicacao/teams", "caixa não importa"
    assert b["teams_webhook"]["trecho"] == {"antes": "", "casou": "teams_webhook", "depois": "_url"}
    assert b["xyz"] == [] and b["vazio"] == []
    assert b["email_remetente"]["caminho"] == "/admin/comunicacao/email", "chave inteira casa com o prefixo dono"
    assert b["e-mail"]["caminho"] == "/admin/comunicacao/email"
    # acento: sem acento acha com acento, e o trecho destacado é o ORIGINAL
    assert b["configuracao"]["caminho"] == "/admin/sistema/parametros"
    assert b["configuracao"]["trecho"]["casou"] == "configuração"
    assert b["CONFIGURAÇÃO"]["caminho"] == "/admin/sistema/parametros"
    assert b["calendario"]["trecho"] == {"antes": "", "casou": "Calendário", "depois": "s & Blackout"}
    assert b["inteligencia"] == ["/admin/ia/provedor", "/admin/ia/maestro", "/admin/ia/agentes", "/admin/ia/triagem"]
    assert b["publicar dag"] == ["/admin/pipelines/publicar-dags"], "vários termos: todos precisam casar"
    assert b["agentes"]["caminho"] == "/admin/ia/agentes"
    assert b["powerbi_client_secret"] == ["/admin/sistema/parametros"], "chave órfã leva a Parâmetros avançados"
    # chaves avulsas sem dono de famílias com dono (achado do QA da F2)
    assert "/admin/sistema/parametros" in b["servicenow_admin_perfis"]
    assert "/admin/sistema/parametros" in b["agentes_titulo_redigido_em"]
    # ...mas o prefixo da família continua levando à aba DONA em 1º lugar
    assert b["servicenow_"]["caminho"] == "/admin/integracoes/servicenow"
    assert b["agentes_"]["caminho"] == "/admin/ia/agentes"
    # nome literal de chave só casa pelo começo: pedaço do meio não acha
    assert "/admin/sistema/parametros" not in b["admin_perfis"]


def test_bancada_resolvedor(bancada):
    d = bancada["destinos"]
    assert d[""] == {"tipo": "inicio"}
    assert d["comunicacao/email"] == {"tipo": "aba", "caminho": "/admin/comunicacao/email"}
    assert d["/comunicacao/email/"] == {"tipo": "aba", "caminho": "/admin/comunicacao/email"}
    assert d["comunicacao"] == {"tipo": "redirecionar", "para": "/admin/comunicacao/teams"}
    assert d["config"] == {"tipo": "redirecionar", "para": "/admin/sistema/parametros"}
    assert d["sistema/config"] == {"tipo": "redirecionar", "para": "/admin/sistema/parametros"}
    assert d["ia"] == {"tipo": "redirecionar", "para": "/admin/ia/provedor"}
    for s in ("foo", "foo/bar", "comunicacao/inexistente", "comunicacao/email/extra", "constructor", "toString"):
        assert d[s] == {"tipo": "nao-encontrada"}, s


def test_bancada_ultima_aba(bancada):
    u = bancada["ultima"]
    assert u["gravada"] == u["lida"] == "/admin/comunicacao/email"
    assert u["lixo"] is None, "endereço que não existe mais não vira destino"
    assert u["quebradoLer"] is None and u["quebradoGravarLancou"] is False


# ═══════════ 4. remanejamentos da F3 ══════════════════════════════════════

def test_f3_acesso_em_tres_abas_na_ordem_dos_blocos(bancada):
    acesso = [a["id"] for a in bancada["abas"] if a["grupo"] == "acesso"]
    assert acesso == ["usuarios", "perfis", "roles-airflow"]
    assert bancada["idsAntigos"]["usuarios"] == "/admin/acesso/usuarios"
    assert "/admin/acesso/perfis" in bancada["busca"]["perfil"][:2]


def test_f3_triagem_em_ia_com_as_chaves(bancada):
    b = bancada["busca"]
    assert b["triagem"][0] == "/admin/ia/triagem"
    assert "/admin/integracoes/servicenow" not in b["triagem"], "a triagem saiu do ServiceNow"
    assert b["chamados_triagem_lote"][0] == "/admin/ia/triagem"
    donos = {a["id"]: a["chavesConfig"] for a in bancada["abas"]}
    assert "chamados_triagem_" in donos["triagem"]
    assert "chamados_triagem_" not in donos["servicenow"]


def test_f3_teams_dono_do_webhook_padrao(bancada):
    donos = {a["id"]: a["chavesConfig"] for a in bancada["abas"]}
    assert donos["teams"] == ["teams_webhook_url"]
    for chave in ("teams_webhook_url", "teams_webhook_url_ack", "teams_webhook_url_resolved"):
        assert bancada["busca"]["chaves"][chave] == "/admin/comunicacao/teams", chave
    assert "até a F3" not in _fonte()


def test_f3_bancos_e_monitoramento_numa_aba(bancada):
    integ = [a["id"] for a in bancada["abas"] if a["grupo"] == "integracoes"]
    assert "monitoramento" not in integ and "bancos" in integ
    for antigo in ("servidor", "monitor", "monitoramento"):
        assert bancada["idsAntigos"][antigo] == "/admin/integracoes/bancos", antigo
    d = bancada["destinos"]
    for splat in ("integracoes/monitoramento", "servidor", "monitor", "integracoes/servidor"):
        assert d[splat] == {"tipo": "redirecionar", "para": "/admin/integracoes/bancos"}, splat
    assert bancada["busca"]["monitor"][0] == "/admin/integracoes/bancos"
    # última aba gravada com o slug aposentado segue o redirecionamento
    assert bancada["ultima"]["aposentada"] == "/admin/integracoes/bancos"


def test_f3_bancos_renderiza_servidor_em_cima_e_monitoramento_embaixo():
    fonte = (ABAS_DIR / "BancosTab.tsx").read_text(encoding="utf-8")
    assert fonte.index("<ServidorTab />") < fonte.index("<MonitoramentoTab />")


def test_f3_cada_bloco_movido_tem_comentario_de_onde_veio():
    """Critério da F3: cada movimento deixa, no ponto novo, o registro de que foi
    decisão da spec e de onde veio — senão a próxima passagem "conserta" de volta."""
    admin = FRONT / "components" / "admin"
    for arq in ("abas/PerfisTab.tsx", "abas/RolesAirflowTab.tsx", "abas/UsuariosTab.tsx", "abas/TriagemTab.tsx",
                "abas/BancosTab.tsx", "abas/NotificacoesTab.tsx", "abas/SondaServiceNowTab.tsx", "abas/ConfigTab.tsx"):
        fonte = (admin / arq).read_text(encoding="utf-8")
        assert "Decisão explícita da spec" in fonte and "F3" in fonte, arq
