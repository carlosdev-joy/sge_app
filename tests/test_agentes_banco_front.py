"""Tela da consulta a banco (C2 de docs/spec-agentes-ferramenta-banco.md).

As funções puras rodam DE VERDADE pelo harness `tests/js/agentes_banco_harness.cjs`
(realce de SQL, consultas executadas, pares, linguagem do bloco). O resto é
leitura do fonte, como os outros testes de front dos agentes:

  1. **Cadastro** — um interruptor liga as duas ferramentas de banco; o PUT
     manda SEMPRE `bancos` (é o que diz à API que a tela conhece o banco); os
     avisos de escrita que a API devolve aparecem; as rotas das conexões são
     as do §8; banco sem SHOWPLAN não se marca.
  2. **Chat** — ```sql vira "Consulta SQL" (inclusive a sugerida); "Consultas
     executadas" só com o que rodou; "Consultei:" com o par; Copiar por
     `lib/copiar.ts` (produção é HTTP); nada de HTML por string.
  3. **Cores** — só tokens, e tom com par `dark:`.
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
BANCOS = FRONT / "components" / "admin" / "BancosLiberados.tsx"
BLOCO = FRONT / "components" / "agentes" / "BlocoSql.tsx"
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
MARKDOWN = FRONT / "components" / "agentes" / "MarkdownAgente.tsx"
REALCE = FRONT / "lib" / "sqlRealce.ts"
ROUTER = RAIZ / "api" / "routers" / "agentes.py"


def test_funcoes_puras_rodam_no_node():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/agentes_banco_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"


# ═══════════ 1. cadastro ══════════════════════════════════════════════════

def test_put_e_post_mandam_sempre_bancos_e_mascara():
    """Sem `bancos` no corpo, a API PRESERVA as ferramentas de banco (proteção
    da tela antiga) — a tela nova precisa mandar sempre, senão desligar a
    consulta a banco não desligaria nada."""
    fonte = codigo(CADASTRO)
    comum = re.search(r"const comum = \{(.*?)\n      \}", fonte, re.S).group(1)
    assert "bancos: usaBanco(rascunho.ferramentas) ? rascunho.bancos : []" in comum
    # sem a consulta a banco, a máscara vai no padrão (revisão da C2: valor
    # escondido na tela virava 503 "migration 122" num agente sem banco)
    assert "mascarar_dados: usaBanco(rascunho.ferramentas) ? rascunho.mascarar_dados : true" in comum
    assert "body: JSON.stringify(comum)" in fonte and "...comum, id: rascunho.id" in fonte


def test_interruptor_liga_as_duas_ferramentas_de_banco():
    fonte = codigo(CADASTRO)
    assert "[...r.ferramentas, ...FERRAMENTAS_BANCO]" in fonte
    assert "r.ferramentas.filter(f => !usaBanco([f]))" in fonte
    assert "[...dados.ferramentas, ...(dados.ferramentas_banco ?? [])]" in fonte
    assert "{bancoLigado && (" in fonte and "<BancosLiberados" in fonte
    assert "Mascarar dados pessoais" in fonte


def test_edicao_carrega_bancos_e_mascara_do_agente():
    fonte = codigo(CADASTRO)
    assert "bancos: ag.bancos ?? [], mascarar_dados: ag.mascarar_dados ?? true" in fonte
    assert "bancos: [], mascarar_dados: true" in fonte  # criação: máscara ligada por padrão (C2)


def test_avisos_da_api_aparecem():
    fonte = codigo(CADASTRO)
    assert "for (const aviso of r.avisos ?? []) toast.info(aviso)" in fonte
    assert '"avisos": avisos' in ROUTER.read_text(encoding="utf-8")


def test_conexoes_e_bancos_pelas_rotas_proprias():
    fonte = codigo(BANCOS)
    assert "apiFetch('/agentes/admin/conexoes')" in fonte
    assert "`/agentes/admin/conexoes/${encodeURIComponent(conexao)}/bancos`" in fonte
    rotas = ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/agentes/admin/conexoes"' in rotas
    assert '@router.get("/agentes/admin/conexoes/{conn_id}/bancos"' in rotas


def test_sem_showplan_nao_se_marca_e_escrita_avisa():
    fonte = codigo(BANCOS)
    assert "disabled={!b.showplan && !marcado}" in fonte
    assert "dados.sysadmin || escolhidos.some(b => b.escrita)" in fonte
    assert "Este login também alcança:" in fonte
    assert "data-agentes-banco-orfao" in fonte and "data-agentes-banco-sumido" in fonte
    assert "data-agentes-banco-sem-lista" in fonte  # conexão fora do ar: pares ainda desmarcáveis


def test_resumo_da_lista_junta_as_de_banco():
    fonte = codigo(CADASTRO)
    assert "resumoFerramentas(ag)" in fonte and "consulta a banco (" in fonte


# ═══════════ 2. chat ══════════════════════════════════════════════════════

def test_bloco_sql_vira_consulta_sql():
    fonte = codigo(MARKDOWN)
    assert "b.tipo === 'codigo' && b.linguagem === 'sql'" in fonte and "<BlocoSql sql={b.texto} />" in fonte


def test_consultas_executadas_e_linha_consultei():
    fonte = codigo(CHAT)
    assert "consultasExecutadas(artefatos)" in fonte
    assert "rodape={resumoConsulta(c.meta)}" in fonte and "rotulo={`${c.meta.conexao}/${c.meta.banco}`}" in fonte
    assert "const nome = rotuloDoArtefato(a)" in fonte
    # a trilha antiga continua: falhou / não repetida / indisponível
    for marca in ["(indisponível)", "(não repetida)", "(falhou)"]:
        assert marca in fonte


def test_copiar_pelo_helper_e_sem_html_por_string():
    fonte = codigo(BLOCO)
    assert "copiarTexto(sql, { bruto: true })" in fonte and "AVISO_COPIA[copia]" in fonte
    # não copiou → o SQL fica SELECIONADO, senão "use Ctrl+C" mente
    assert "if (r !== 'copiado' && alvo.current)" in fonte and "selectAllChildren(alvo.current)" in fonte
    assert "<pre ref={alvo}" in fonte
    assert "navigator.clipboard" not in fonte
    for arq in (BLOCO, MARKDOWN, CHAT, BANCOS):
        assert "dangerouslySetInnerHTML" not in codigo(arq), arq.name
    assert "tokensSql(sql)" in fonte and "<code>" in fonte


def test_realce_sem_imports():
    """O harness Node executa o arquivo direto — import quebraria o teste."""
    assert not re.search(r"^import ", REALCE.read_text(encoding="utf-8"), re.M)


# ═══════════ 3. cores ═════════════════════════════════════════════════════

@pytest.mark.parametrize("arq", [BLOCO, BANCOS, CADASTRO, CHAT, MARKDOWN], ids=lambda p: p.name)
def test_so_tokens_de_cor(arq):
    fonte = codigo(arq)
    achados = [m.group(0) for m in _COR_UTIL.finditer(fonte)
               if m.group(0) != "text-white" and not _TOM_PERMITIDO.fullmatch(m.group(0))]
    assert not achados, sorted(set(achados))


def test_tom_do_realce_tem_par_escuro():
    fonte = codigo(BLOCO)
    for tom in ("emerald", "amber"):
        assert re.search(rf"text-{tom}-700 dark:text-{tom}-300", fonte), tom
    assert "text-cvp-blue dark:text-orq-primary" in fonte
