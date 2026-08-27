"""tests/test_chamado_derivacoes.py — unit tests for chamado_derivacoes.

Run from /opt/airflow:
    docker exec orquestra-api python -m pytest tests/test_chamado_derivacoes.py -v
"""
import sys
import os

# dags/utils/ is the real home of chamado_derivacoes; add it to path.
sys.path.insert(0, "/opt/airflow/dags")
sys.path.insert(0, "/opt/airflow/dags/utils")

# Stub heavy utilities that require Airflow internals
import types

_texto_sql = types.ModuleType("utils.texto_sql")
_texto_sql.cortar = lambda s, n: s[:n] if len(s) > n else s
_texto_sql.unidades_utf16 = lambda s: len(s)
sys.modules.setdefault("utils.texto_sql", _texto_sql)

_frescor = types.ModuleType("utils.frescor_modulo")
_frescor.carimbar = lambda *a, **kw: None
sys.modules.setdefault("utils.frescor_modulo", _frescor)

from utils import chamado_derivacoes as cd  # noqa: E402


# ── tipo_demanda ──────────────────────────────────────────────────────────────

class TestTipoDemanda:
    def test_inclusao_coluna(self):
        assert cd.tipo_demanda("Inclusão de coluna na tabela X") == "Inclusão de coluna/campo"

    def test_inclusao_sem_acento(self):
        assert cd.tipo_demanda("inclusao de coluna TB_VENDAS") == "Inclusão de coluna/campo"

    def test_extracao(self):
        assert cd.tipo_demanda("extração de dados mensais") == "Extração de dados"

    def test_catalogo_como_fallback(self):
        # título genérico → catálogo entra como segunda chance
        assert cd.tipo_demanda("Solicitação", "consulta de dados") == "Consulta de dados"

    def test_titulo_prevalece_sobre_catalogo(self):
        # título manda: se ambos casam, o do título vence
        assert cd.tipo_demanda("extração de dados", "consulta de dados") == "Extração de dados"

    def test_sem_match_retorna_padrao(self):
        assert cd.tipo_demanda("") == cd.TIPO_PADRAO
        assert cd.tipo_demanda("Algo sem categoria") == cd.TIPO_PADRAO

    def test_none_seguro(self):
        assert cd.tipo_demanda(None) == cd.TIPO_PADRAO
        assert cd.tipo_demanda(None, None) == cd.TIPO_PADRAO


# ── categoria_diaadia ─────────────────────────────────────────────────────────

class TestCategoriaDiaADia:
    def test_dia_a_dia(self):
        assert cd.categoria_diaadia("dia a dia - bug") == "dia a dia"

    def test_dia_a_dia_case_insensitive(self):
        assert cd.categoria_diaadia("Dia A Dia manutenção") == "dia a dia"

    def test_iniciativa(self):
        assert cd.categoria_diaadia("iniciativa estratégica 2026") == "iniciativa"

    def test_dia_a_dia_prevalece_sobre_iniciativa(self):
        # mesmo texto contendo os dois → "dia a dia" tem precedência
        assert cd.categoria_diaadia("dia a dia / iniciativa X") == "dia a dia"

    def test_sem_marcacao_retorna_vazio(self):
        assert cd.categoria_diaadia("") == ""
        assert cd.categoria_diaadia("nenhuma categoria aqui") == ""

    def test_none_seguro(self):
        assert cd.categoria_diaadia(None) == ""


# ── objetos_citados ───────────────────────────────────────────────────────────

class TestObjetosCitados:
    def test_captura_tb(self):
        assert "TB_CLIENTES" in cd.objetos_citados("ajuste na TB_CLIENTES")

    def test_captura_dmdb(self):
        assert "DMDB41..VENDAS" in cd.objetos_citados("tabela DMDB41..VENDAS precisa ser")

    def test_captura_vw(self):
        assert "VW_RELATORIO" in cd.objetos_citados("view VW_RELATORIO")

    def test_limite_3_por_padrao(self):
        texto = "TB_A TB_B TB_C TB_D TB_E"
        resultado = cd.objetos_citados(texto)
        assert resultado.count(",") <= 2  # at most 3 items → at most 2 commas

    def test_deduplica(self):
        texto = "TB_CLIENTES e depois TB_CLIENTES novamente"
        resultado = cd.objetos_citados(texto)
        assert resultado.count("TB_CLIENTES") == 1

    def test_sem_objeto(self):
        assert cd.objetos_citados("nenhum objeto técnico mencionado") == ""

    def test_none_seguro(self):
        assert cd.objetos_citados(None) == ""

    def test_nao_captura_prefixo_colado(self):
        # DBTB_VENDAS não deve capturar TB_VENDAS (borda esquerda)
        resultado = cd.objetos_citados("DBTB_VENDAS")
        assert "TB_VENDAS" not in resultado

    def test_aceita_digito_no_sufixo(self):
        # TB_CLIENTE2 deve capturar o nome inteiro, não truncar em TB_CLIENTE
        resultado = cd.objetos_citados("TB_CLIENTE2")
        assert "TB_CLIENTE2" in resultado
