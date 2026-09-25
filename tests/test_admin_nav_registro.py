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
  5. **Saídas da F4**: SLA, Power BI e Fluxo DS deixam de ser abas; o endereço
     velho (id antigo e slug da F2) leva à tela nova FORA do admin, e a última
     aba gravada com um deles não tira ninguém do /admin. As migalhas
     "Admin › …" de outras telas saem do registro (LinkAdmin/rotuloAdmin) — e o
     texto literal que sobrar tem de nomear uma aba que existe.
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

# Ids do Admin antes da F2 (estado local de pages/Admin.tsx na F1) que seguem
# apontando para uma aba do admin.
IDS_ANTIGOS = (
    "config", "conexoes", "utilitarios", "tipos", "projetos", "versoes", "backlog", "servidor",
    "dags", "servicenow", "monitor", "regen", "delete", "agenda", "usuarios",
    "comunicados", "notificacoes", "ia", "maestro", "agentes", "email",
)

# F4: ids antigos e slugs da F2 das abas que SAÍRAM do admin → tela nova.
SAIDAS_F4 = {
    "sla": "/performance#sla",
    "powerbi": "/powerbi#como-liberar-acessos",
    "powerbi-acessos": "/powerbi#como-liberar-acessos",
    "fluxo_ds": "/ds-console?aba=seqflow",
    "fluxo-ds": "/ds-console?aba=seqflow",
}

# Slugs publicados na F2 que a F3 aposentou (a aba foi fundida em outra) —
# continuam resolvendo, como id antigo, para o endereço novo.
SLUGS_APOSENTADOS_F3 = {"monitoramento": "/admin/integracoes/bancos"}

TOTAL_ABAS = 23

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
    # nenhum id de saída continua preso a uma aba (senão resolveria para dentro do admin)
    assert not set(ids) & set(SAIDAS_F4)


def test_f4_saidas_nao_sao_mais_abas():
    fonte = _fonte()
    corpo = fonte.split("export const ABAS_ADMIN", 1)[1].split("\n]\n", 1)[0]
    for slug in ("sla", "powerbi-acessos", "fluxo-ds"):
        assert f"id: '{slug}'" not in corpo, slug
    assert "sai na F4" not in fonte
    for arq in ("SlaReportTab", "PowerBIAccessGuideTab", "FluxoDsTab"):
        assert not (ABAS_DIR / f"{arq}.tsx").exists(), arq


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
    assert bancada["externos"] == SAIDAS_F4
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


# ═══════════ 5. saídas da F4 e migalhas ═══════════════════════════════════

def test_f4_sistema_so_com_as_tres_abas(bancada):
    sistema = [a["id"] for a in bancada["abas"] if a["grupo"] == "sistema"]
    assert sistema == ["parametros", "versoes", "backlog"]


def test_f4_endereco_velho_leva_a_tela_nova_fora_do_admin(bancada):
    d = bancada["destinos"]
    esperado = {
        "sla": "/performance#sla", "sistema/sla": "/performance#sla",
        "powerbi": "/powerbi#como-liberar-acessos", "sistema/powerbi": "/powerbi#como-liberar-acessos",
        "sistema/powerbi-acessos": "/powerbi#como-liberar-acessos", "powerbi-acessos": "/powerbi#como-liberar-acessos",
        "fluxo_ds": "/ds-console?aba=seqflow", "sistema/fluxo_ds": "/ds-console?aba=seqflow",
        "sistema/fluxo-ds": "/ds-console?aba=seqflow", "fluxo-ds": "/ds-console?aba=seqflow",
    }
    for splat, para in esperado.items():
        assert d[splat] == {"tipo": "redirecionar", "para": para}, splat
        # destino fora do /admin: pages/Admin.tsx navega com replace e não há laço
        assert not para.startswith("/admin")


def test_f4_ultima_aba_que_saiu_nao_tira_do_admin(bancada):
    assert bancada["ultima"]["saiuDoAdmin"] == {
        "/admin/sistema/sla": None, "/admin/sistema/powerbi-acessos": None, "/admin/sistema/fluxo-ds": None,
    }, "lerUltimaAba só aceita aba do admin; o /admin cai na aba padrão"


def test_f4_busca_nao_acha_o_que_saiu(bancada):
    """Decisão da F4: a busca do admin indexa só abas do admin. O que saiu tem
    tela própria no menu principal (e no ⌘K), com RBAC próprio."""
    assert bancada["busca"]["sla"] == [] and bancada["busca"]["fluxo ds"] == []
    assert "/admin/sistema/sla" not in bancada["busca"]["relatório"]


def test_f4_admin_tsx_nao_monta_casca_para_destino_externo():
    fonte = (FRONT / "pages" / "Admin.tsx").read_text(encoding="utf-8")
    assert "ehCaminhoAdmin(redirecionarPara)" in fonte
    assert "navigate(redirecionarPara, { replace: true })" in fonte


def test_f4_rotulo_da_migalha_sai_do_registro(bancada):
    r = bancada["rotulos"]
    assert r["email"] == "Admin › Comunicação › E-mail"
    assert r["emailModelos"] == "Admin › Comunicação › E-mail › Modelos"
    assert r["sftp"] == "Admin › Integrações & Dados › Servidor DataStage (SFTP)"
    # aba que não existe: nunca lança, e não inventa a aba nem a seção
    assert r["inexistente"] == r["inexistenteComSecao"] == "Admin › Sistema"


_CHAMADA_LINK = re.compile(r'<LinkAdmin\s+grupo="(\w+)"\s+aba="([\w-]+)"')
_CHAMADA_ROTULO = re.compile(r"rotuloAdmin\('(\w+)',\s*'([\w-]+)'")


def _fontes_ui():
    for arq in sorted(FRONT.rglob("*.ts*")):
        yield arq, arq.read_text(encoding="utf-8")


def test_f4_toda_migalha_aponta_para_aba_que_existe(bancada):
    existentes = {(a["grupo"], a["id"]) for a in bancada["abas"]}
    usos = []
    for arq, fonte in _fontes_ui():
        if arq.name in ("adminNav.ts", "LinkAdmin.tsx"):
            continue
        usos += [(arq.name, g, a) for g, a in _CHAMADA_LINK.findall(fonte) + _CHAMADA_ROTULO.findall(fonte)]
    assert len(usos) >= 20, "as migalhas da F4 sumiram?"
    orfas = [u for u in usos if (u[1], u[2]) not in existentes]
    assert not orfas, orfas


def _sem_comentarios(texto: str) -> str:
    texto = re.sub(r"\{/\*.*?\*/\}|/\*.*?\*/", "", texto, flags=re.DOTALL)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", linha) for linha in texto.splitlines())


def test_f4_nenhuma_migalha_de_texto_com_caminho_velho(bancada):
    """Critério da F4: "nenhuma migalha de texto sobra". O que continua texto
    (hint, mensagem de validação, lib pura sem o registro) tem de começar por
    um caminho "Admin › Grupo › Aba" que EXISTE; grafia velha ("Admin > X",
    "Admin ▸ X", "Admin → X") não vale em lugar nenhum da UI."""
    validos = tuple(bancada["rotulos"]["todas"])
    ruins = []
    for arq, fonte in _fontes_ui():
        texto = _sem_comentarios(fonte)
        for m in re.finditer(r"Admin\s*(?:&gt;|▸|→|>(?=\s*[A-Z]))\s*\w", texto):
            ruins.append((str(arq.relative_to(FRONT)), m.group(0)))
        for m in re.finditer(r"Admin › [^'\"`<{\n]*", texto):
            if not m.group(0).startswith(validos):
                ruins.append((str(arq.relative_to(FRONT)), m.group(0)))
    assert not ruins, ruins


def test_f4_backend_nao_cita_caminho_velho_do_admin(bancada):
    """Achado do QA da F4: mensagens da API/worker chegam à tela (o front repassa
    o `detail`) — "Admin › Utilitários" num 403 ao lado do banner com o caminho
    novo. Todo "Admin › …" em api/ e dags/ (código E comentário) começa por um
    caminho que existe no registro; grafia velha "Admin > X" não vale.
    Exceção: dags/etl_dag_factory.py e o que ele gerou (dags/generated/) — o
    texto vai para DAGs JÁ GERADAS e corrigi-lo exige republicar (Backlog, F6)."""
    raiz = FRONT.parents[1]
    validos = tuple(bancada["rotulos"]["todas"])
    ruins = []
    arquivos = [p for p in list((raiz / "api").rglob("*.py")) + list((raiz / "dags").rglob("*.py"))
                if "wheels" not in p.parts and "generated" not in p.parts and p.name != "etl_dag_factory.py"]
    for arq in arquivos:
        texto = re.sub(r"\n\s*#\s*", " ", arq.read_text(encoding="utf-8"))  # junta comentário quebrado
        for m in re.finditer(r"Admin\s*>\s*[A-Z]\w*", texto):
            ruins.append((str(arq.relative_to(raiz)), m.group(0)))
        for m in re.finditer(r"Admin › [^'\"`\n.;:{},—×]*", texto):
            if not m.group(0).startswith(validos):
                ruins.append((str(arq.relative_to(raiz)), m.group(0)))
    assert arquivos and not ruins, ruins


def test_f4_link_admin_respeita_permissao_e_edicao():
    fonte = (FRONT / "components" / "admin" / "LinkAdmin.tsx").read_text(encoding="utf-8")
    assert "canAccess('tela_admin', perms)" in fonte, "sem tela_admin: só o texto"
    assert 'target="_blank"' in fonte and "noopener" in fonte
    # telas de edição sem guarda de alterações abrem o admin em outra aba
    for arq in ("components/etapas/paineis/PainelEmail.tsx", "components/etapas/paineis/PainelNotificacao.tsx",
                "components/utilitarios/FormEditarArquivo.tsx", "components/utilitarios/FormEnviarArquivo.tsx",
                "components/pipelines/PipelineFormModal.tsx"):
        usos = _CHAMADA_LINK.findall((FRONT / arq).read_text(encoding="utf-8"))
        linhas = [l for l in (FRONT / arq).read_text(encoding="utf-8").splitlines() if "<LinkAdmin" in l]
        assert usos and all("novaAba" in l for l in linhas), arq


def test_f4_secoes_no_fim_das_telas_de_destino():
    perf = (FRONT / "pages" / "Performance.tsx").read_text(encoding="utf-8")
    corpo = perf.split("return (", 1)[1]
    # a seção é o ÚLTIMO bloco da tela (decisão §9.2) — nada acima mudou de lugar
    assert corpo.rstrip().endswith("<AderenciaSla />\n    </div>\n  )\n}")
    assert corpo.index("{/* Filtro */}") < corpo.index("{/* KPIs */}") < corpo.index("{/* Tabela */}") < corpo.index("<AderenciaSla />")
    sla = (FRONT / "components" / "performance" / "AderenciaSla.tsx").read_text(encoding="utf-8")
    assert "/execucoes/sla-report?" in sla and "Aderência ao SLA" in sla and "id={ANCORA_SLA}" in sla
    assert "export const ANCORA_SLA = 'sla'" in sla

    pbi = (FRONT / "pages" / "PowerBI.tsx").read_text(encoding="utf-8")
    assert pbi.count("<SecaoComoLiberarAcessos />") == 2, "nos dois estados da tela (configurado ou não)"
    for bloco in pbi.split("<SecaoComoLiberarAcessos />")[1:]:
        # depois da seção, só o modal (que não ocupa lugar na tela) e o fecho
        resto = re.sub(r"\{selectedRow && <DatasetDetailModal[^\n]*\n", "", bloco)
        assert re.match(r"\s*</div>\s*\)", resto), resto[:120]
    guia = (FRONT / "components" / "powerbi" / "GuiaAcessosPowerBI.tsx").read_text(encoding="utf-8")
    assert "<details id={ANCORA_PBI_ACESSOS}" in guia and " open" not in guia.split("<details", 1)[1].split(">", 1)[0], \
        "fechada por padrão"
    assert "Como liberar acessos" in guia and "Fase A — Habilitar Admin API" in guia


def test_f4_ds_console_abre_no_fluxo_xml_pelo_endereco():
    fonte = (FRONT / "pages" / "DsConsole.tsx").read_text(encoding="utf-8")
    assert "searchParams.get('aba') === 'seqflow' ? 'seqflow' : 'geral'" in fonte
    assert "{ id: 'seqflow', label: 'Fluxo (XML)' }" in fonte
