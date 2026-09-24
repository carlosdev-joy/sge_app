"""Tela do cadastro de agentes (B3 de docs/spec-agentes-admin.md §4.5).

As funções puras rodam DE VERDADE pelo harness `tests/js/agentes_cadastro_harness.cjs`.
O resto é leitura do fonte, como os outros testes de front dos agentes. O que
se prende, e por quê:

  1. **Ordem da aba** — o cadastro entra depois de "Gateway e limites" e antes
     das seções de acesso e do Prompt; nada do que existia muda de lugar.
  2. **Contrato com a API** — o corpo do POST/PUT tem os campos que o backend
     aceita; ligar/desligar manda boolean; os tipos espelham o backend.
  3. **As regras de D3 na tela** — acesso por perfil indisponível com
     ferramenta de servidor, `consulta` fora da lista, aviso de perfil sem a
     tela Agentes.
  4. **Acesso por agente** — "Quem pode usar" e "Curadores" valem para os da
     tela; por perfil não oferece "Conceder"; curadoria só com ferramentas.
  5. **Tela /agentes** — só conversa sem projeto e grafo; ferramenta recusada
     aparece como "(indisponível)".
  6. **Admin › Usuários** — os grants dos agentes da tela vêm da API.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_agentes_f3_front import _COR_UTIL, _TOM_PERMITIDO, codigo

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
CADASTRO = FRONT / "components" / "admin" / "CadastroAgentes.tsx"
ABA = FRONT / "components" / "admin" / "AgentesTab.tsx"
PAGINA = FRONT / "pages" / "Agentes.tsx"
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
ADMIN = FRONT / "pages" / "Admin.tsx"
LIB = FRONT / "lib" / "agentes.ts"
ROUTER = RAIZ / "api" / "routers" / "agentes.py"
REGISTRO = RAIZ / "api" / "services" / "agentes_registro.py"


def test_funcoes_puras_rodam_no_node():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/agentes_cadastro_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"


# ═══════════ 1. ordem da aba ══════════════════════════════════════════════

def test_cadastro_entra_entre_gateway_e_acessos_sem_reordenar():
    fonte = codigo(ABA)
    marcos = ["Interruptores", "Gateway e limites", "<CadastroAgentes />", "{todos.flatMap(ag =>", "<PromptAgente"]
    posicoes = [fonte.index(m) for m in marcos]
    assert posicoes == sorted(posicoes), dict(zip(marcos, posicoes))


# ═══════════ 2. contrato com a API ════════════════════════════════════════

def test_corpo_da_criacao_e_da_edicao():
    fonte = codigo(CADASTRO)
    comum = re.search(r"const comum = \{(.*?)\}", fonte, re.S).group(1)
    campos = set(re.findall(r"(\w+): rascunho\.\w+", comum))
    # `bancos` vai sempre, condicionado à ferramenta (spec ferramenta-banco C2)
    assert "bancos: usaBanco(rascunho.ferramentas) ? rascunho.bancos : []" in comum
    assert "mascarar_dados: usaBanco(rascunho.ferramentas) ? rascunho.mascarar_dados : true" in comum
    campos |= {"bancos", "mascarar_dados"}
    assert campos == {"nome", "descricao", "acesso", "perfis", "ferramentas", "bancos", "mascarar_dados"}
    # PUT só com o que o backend deixa alterar (sem id, prompt, motivo)
    alteraveis = set(re.search(r"CAMPOS_ALTERAVEIS = \((.*?)\)", REGISTRO.read_text(encoding="utf-8")).group(1)
                     .replace('"', "").replace(" ", "").split(","))
    assert campos <= alteraveis
    assert "{ method: 'PUT', body: JSON.stringify(comum) }" in fonte
    assert "JSON.stringify({ ...comum, id: rascunho.id, prompt: rascunho.prompt, motivo: rascunho.motivo })" in fonte


def test_ligar_manda_boolean():
    fonte = codigo(CADASTRO)
    assert "alternar.mutate({ id: ag.id, ativo: e.target.checked })" in fonte
    assert "JSON.stringify({ ativo })" in fonte


def test_datastage_nao_se_edita_nem_se_liga_pelo_cadastro():
    fonte = codigo(CADASTRO)
    assert "ag.origem === 'codigo' ? (" in fonte and "(em Interruptores)" in fonte
    assert "{ag.origem === 'banco' && (" in fonte  # só os da tela têm "Editar"


def _campos_da_interface(nome: str) -> set[str]:
    bloco = re.search(rf"export interface {nome}[^{{]*\{{(.*?)\n\}}", codigo(LIB), re.S).group(1)
    return set(re.findall(r"^\s*(\w+)\??:", bloco, re.M))


def test_tipos_espelham_o_backend():
    fonte = ROUTER.read_text(encoding="utf-8")
    item = re.search(r"def _agente_para_admin.*?return \{(.*?)\}\n", fonte, re.S).group(1)
    assert set(re.findall(r'"(\w+)":', item)) == _campos_da_interface("AgenteAdminItem")
    lista = re.search(r"async def agentes_admin_lista.*?return \{(.*?)\}\n", fonte, re.S).group(1)
    assert set(re.findall(r'"(\w+)":', lista)) == _campos_da_interface("AgentesAdminResposta")


def test_id_e_reservados_iguais_aos_do_backend():
    reg = REGISTRO.read_text(encoding="utf-8")
    lib = codigo(LIB)
    padrao_back = re.search(r'RE_ID = re\.compile\(r"\\A(.*?)\\Z"\)', reg).group(1)
    padrao_front = re.search(r"export const RE_ID_AGENTE = /\^(.*?)\$/", lib).group(1)
    assert padrao_back == padrao_front
    rotas_back = set(re.findall(r'"(\w+)"', re.search(r"_IDS_DE_ROTA = frozenset\(\{(.*?)\}\)", reg).group(1)))
    rotas_front = set(re.findall(r"'(\w+)'", re.search(r"\|\| \[(.*?)\]\.includes\(id\)", lib).group(1)))
    assert rotas_back == rotas_front


# ═══════════ 3. D3 na tela ════════════════════════════════════════════════

def test_acesso_por_perfil_indisponivel_com_ferramenta_de_servidor():
    fonte = codigo(CADASTRO)
    assert "disabled={a === 'perfil' && tocaServidor}" in fonte
    assert "const tocaServidor = ferramentasFinais.some(f => dados.ferramentas_servidor.includes(f))" in fonte


def test_consulta_fora_da_lista_de_perfis_e_aviso_de_tela():
    fonte = codigo(CADASTRO)
    assert "const escolhiveis = perfis.filter(p => !dados.perfis_proibidos.includes(p.perfil_nome))" in fonte
    assert "escolhiveis.map(p =>" in fonte
    assert "permissoes.includes('tela_agentes')" in fonte  # avisa, não concede


def test_problemas_bloqueiam_o_botao_de_salvar():
    fonte = codigo(CADASTRO)
    assert "disabled={todosProblemas.length > 0 || salvando}" in fonte
    assert "onSalvar(final)" in fonte  # manda o conjunto já normalizado (com resolver_projeto)


def test_perfil_excluido_aparece_para_ser_desmarcado():
    """Revisão da B3: perfil que o agente tem mas foi excluído não tinha
    checkbox — o PUT o reenviava e a edição inteira era recusada."""
    fonte = codigo(CADASTRO)
    assert "inexistentes.map(p =>" in fonte and "data-agentes-perfil-inexistente" in fonte
    assert "onChange={() => alternarLista('perfis', p)}" in fonte
    assert "não existe mais — desmarque para salvar" in fonte


def test_interruptor_com_o_nome_do_agente_e_grupo_de_perfis():
    fonte = codigo(CADASTRO)
    assert "label={ag.ativo ? `${ag.nome}: ligado` : `${ag.nome}: desligado`}" in fonte
    assert 'role="group" aria-label="Perfis"' in fonte


def test_erro_do_modal_de_permissoes_diz_o_motivo():
    assert "onError: (e: unknown) => toast.error(mensagemDeErro(e, 'Não foi possível salvar as permissões'))" in \
        codigo(ADMIN)


# ═══════════ 4. acesso por agente ═════════════════════════════════════════

def test_secoes_de_acesso_valem_para_os_da_tela():
    fonte = codigo(ABA)
    assert "...(doBanco.data?.agentes ?? []).filter(a => a.origem === 'banco')" in fonte
    assert "...(ag.recurso_curador ? [{ chave: `${ag.id}:curador`" in fonte
    bloco = fonte[fonte.index("if (ag.acesso === 'perfil' && papel.chave.endsWith(':uso'))"):]
    bloco = bloco[:bloco.index("</section>")]
    assert "Conceder" not in bloco and "sem concessão individual" in bloco


def test_prompt_para_todos_os_agentes():
    assert "{todos.map(ag => <PromptAgente key={`prompt-${ag.id}`} agente={ag} />)}" in codigo(ABA)


# ═══════════ 5. tela /agentes ═════════════════════════════════════════════

def test_so_conversa_sem_projeto_nem_grafo():
    fonte = codigo(PAGINA)
    # C2 da spec ferramenta-banco: sem ferramenta de DataStage (só conversa OU
    # só banco) = sem projeto nem grafo; o harness do banco prende a função.
    assert "const soConversa = semProjetoDataStage(agente)" in fonte
    i = fonte.index("{!soConversa && (")
    assert i < fonte.index("<IndicadorProjeto") < fonte.index("{!soConversa && grafoAberto && plotavel && (")


def test_ferramenta_recusada_aparece_como_indisponivel():
    assert "if (a.recusada) return `${nome} (indisponível)`" in codigo(CHAT)


# ═══════════ 6. Admin › Usuários ══════════════════════════════════════════

def test_grants_dos_agentes_da_tela_vem_da_api():
    fonte = codigo(ADMIN)
    assert "queryKey: Q_AGENTES_ADMIN, queryFn: () => apiFetch('/agentes/admin/agentes'), enabled: permUser !== null" in fonte
    assert ".filter(a => a.origem === 'banco')" in fonte
    assert "recursosDeAgentes.map(([rec, lbl]) =>" in fonte
    assert "checked={permDraft.has(rec)}" in fonte


# ═══════════ estilo e isolamento ══════════════════════════════════════════

def test_cadastro_usa_so_os_tokens_de_cor():
    fonte = codigo(CADASTRO)
    achados = [m.group(0) for m in _COR_UTIL.finditer(fonte) if not _TOM_PERMITIDO.fullmatch(m.group(0))]
    assert not achados, f"cor fora dos tokens: {sorted(set(achados))}"
    assert "overflow-hidden" not in fonte and "sr-only" not in fonte


def test_lib_agentes_continua_sem_import():
    assert not re.search(r"^\s*import\s", LIB.read_text(encoding="utf-8"), re.M)


# ═══════════ grant sem efeito (decisão do usuário, 23/09) ═════════════════

def test_modal_sinaliza_grant_de_agente_sem_efeito():
    """Grant de agente para um perfil que não pode usá-lo: marcado = "sem
    efeito" (não dá acesso, e volta a valer se o perfil voltar a ser
    elegível); desmarcado = não se concede (a API recusaria). Vale para os
    agentes do código (lista fixa) e para os da tela."""
    fonte = codigo(ADMIN)
    assert "const inelegivel = (rec: string) => permUser ? agenteInelegivel(rec, permUser.perfil, agentesDaTela.data?.agentes ?? []) : null" in fonte
    # lista fixa (DataStage e curador)
    assert "const travado = herdado || (agenteFora !== null && !permDraft.has(rec))" in fonte
    assert "disabled={travado}" in fonte
    assert "{!herdado && <SinalGrantAgente agente={agenteFora} perfil={permUser.perfil} marcado={permDraft.has(rec)} ehAdmin={ehAdmin} />}" in fonte
    assert "const ehAdmin = doPerfil.has('acao_admin') || permDraft.has('acao_admin')" in fonte
    assert fonte.index("const ehAdmin =") < fonte.index("{RBAC_RECURSOS.map(([rec, lbl]) =>")
    # agentes da tela
    assert "disabled={inelegivel(rec) !== null && !permDraft.has(rec)}" in fonte
    assert "<SinalGrantAgente agente={inelegivel(rec)} perfil={permUser.perfil} marcado={permDraft.has(rec)} ehAdmin={ehAdmin} />" in fonte
    # o sinal: sem efeito (marcado) × não elegível (desmarcado), com par escuro na cor
    sinal = fonte[fonte.index("function SinalGrantAgente"):]
    sinal = sinal[:sinal.index("\n}\n")]
    assert "sem efeito — o perfil ${perfil} não pode usar ${agente}" in sinal and "(perfil não elegível)" in sinal
    assert "text-amber-700 dark:text-amber-400" in sinal
    # com acao_admin ele USA o agente: "não pode usar" seria falso (revisão)
    assert "if (marcado && ehAdmin) return null" in sinal
    # a query traz os perfis de cada agente
    assert "recurso_curador: string | null; perfis: string[] }[]" in fonte


def test_formulario_do_modal_usa_ajuda_e_nao_hint():
    """O `hint` é um popover que abre para CIMA e é cortado pelo corpo com
    rolagem do Modal (Input.tsx explica) — no campo Id, só a última linha
    aparecia (relato de 23/09). Dentro de modal, a regra do repo é `ajuda`."""
    fonte = codigo(CADASTRO)
    assert "hint=" not in fonte
    assert fonte.count("ajuda=") >= 4
