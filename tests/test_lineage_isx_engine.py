"""Lineage automático via ISX — F1 (spec docs/spec-lineage-isx.md): o engine.

Três camadas, sem rede e sem banco:
  1. funções PURAS de `dags/utils/isx_engine.py` e `ds_stage_types.py` —
     configuração pelo ambiente, lista branca de nomes/pastas, caminho do
     istool, o COMANDO (com `-authfile`, nunca `-password`), classificação;
  2. o parser sobre `.pjb`/`.sjb` SINTÉTICOS montados dos fragmentos documentados
     (o formato real chega pelos `.isx` que o usuário sobe ao DEV — teste marcado
     skip quando não existem em tests/fixtures/isx/, pasta fora do git);
  3. `localizar_job`/`checar_modificado` com API REST falsa e `exportar` com SSH
     falso (comando executado, remove em `finally`, tetos).
Mais o anti-drift: nenhum literal de segredo/host no engine, os conjuntos de
tipos contêm os do `dsx_engine`, migration 106 com guardas, variáveis no compose.
"""
from __future__ import annotations

import io
import re
import sys
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DAGS = ROOT / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))

from utils import ds_stage_types as T  # noqa: E402
from utils import isx_engine as E  # noqa: E402
from utils import dsx_engine as DSX  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "isx"

AMBIENTE = {
    "DS_ENGINE": "AMOSTRA.DEV",
    "DS_API_URL": "http://ds-api-amostra:9443/ibm/iis/ds/api/",
    "DS_API_USER": "amostra",
    "DS_API_PASSWORD": "amostra",
    "DS_API_VERIFY_SSL": "false",
    "DS_ISTOOL_HOME": "/opt/IBM/InformationServer/",
    "DS_ISTOOL_DOMAIN": "ds-api-amostra:9443",
    "DS_ISTOOL_AUTHFILE": "/config/.orquestra/istool.auth",
    "DS_ISTOOL_TMP": "/tmp",
    "DS_ISTOOL_CFG": "/config/.orquestra/istool_cfg",
}
CFG = E.ConfigISX.do_ambiente(AMBIENTE)


def sem(*chaves: str) -> dict:
    return {k: v for k, v in AMBIENTE.items() if k not in chaves}


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures sintéticas (fragmentos documentados na spec de origem, §5)
# ═══════════════════════════════════════════════════════════════════════════

XMLPROPS = (
    "&lt;?xml version='1.0' encoding='UTF-16'?&gt;&lt;Properties version='1.1'&gt;&lt;Connection&gt;"
    "&lt;DataSource type='string'&gt;&lt;![CDATA[#PSetSsdVida.ParmDbNameSsd#]]&gt;&lt;/DataSource&gt;"
    "&lt;Username type='string'&gt;&lt;![CDATA[#PSetSsdVida.ParmDbUserSsd#]]&gt;&lt;/Username&gt;"
    "&lt;Password type='string'&gt;&lt;![CDATA[SEGREDO_NAO_PODE_SAIR]]&gt;&lt;/Password&gt;&lt;/Connection&gt;"
    "&lt;Usage&gt;&lt;SQL&gt;&lt;SelectStatement type='string'&gt;&lt;![CDATA[select distinct\n  b.COD_CPF_CNPJ AS CPF_CNPJ\n"
    "from DM_003_PROPOSTA a join DM_056_PESSOA b on a.SEQ=b.SEQ\nwhere IND_NLIST &lt;&gt; 'N']]&gt;&lt;/SelectStatement&gt;"
    "&lt;/SQL&gt;&lt;/Usage&gt;&lt;/Properties&gt;"
)
XMLPROPS_TABELA = (
    "&lt;Properties&gt;&lt;Connection&gt;&lt;DataSource type='string'&gt;&lt;![CDATA[DSN_STG]]&gt;&lt;/DataSource&gt;&lt;/Connection&gt;"
    "&lt;Usage&gt;&lt;SQL&gt;&lt;BeforeSQL type='string'&gt;&lt;![CDATA[TRUNCATE TABLE dbo.TB_DESTINO]]&gt;&lt;/BeforeSQL&gt;&lt;/SQL&gt;"
    "&lt;TableName type='string'&gt;&lt;![CDATA[dbo.TB_DESTINO]]&gt;&lt;/TableName&gt;&lt;/Usage&gt;&lt;/Properties&gt;"
)

PJB = f"""<?xml version="1.0" encoding="UTF-8"?>
<ds:DSJobDefSDO xmlns:ds="http://www.ibm.com/datastage/ds" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xmi="http://www.omg.org/XMI" name="SsdVidaDimePessoa02Ftp" jobType="Parallel"
    shortDescription="ETL de amostra" longDescription="Homologado em 19/11/2011." createdByUser="usuario_amostra"
    modifiedByUser="usuario_amostra" lastModificationTimestamp="2026-08-04T00:37:15.253-0300" nLSMapName="ISO_8859-1:1987">
  <has_ParameterDef name="PSetSsdVida" typeCode="String" extendedType="Parameterset" defaultValue="(As pre-defined)" longDescription="Parametros VIDA"/>
  <has_ParameterDef name="$APT_NO_SORT_INSERTION" extendedType="Stringlist" defaultValue="False"/>
  <has_ParameterDef name="ParmSenhaBanco" typeCode="Encrypted" defaultValue="OFUSCADO_REVERSIVEL"/>
  <has_ParameterDef name="DbPassword" typeCode="String" defaultValue="abc123"/>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="DM_119_INFO" stageType="ODBCConnectorPX" internalID="V0S185" outputPins="V0S185P1">
    <has_ParameterVal parameterName="Context" valueExpression="source"/>
    <has_ParameterVal parameterName="Username" valueExpression="/Connection/Username"/>
    <has_ParameterVal parameterName="XMLProperties" valueExpression="{XMLPROPS}"/>
    <has_OutputPin name="LnkNlist"><has_DSMetaBag>
      <has_DSMetaData name="CPF_CNPJ" type="string" extendedType="string[max=20]"/>
      <has_DSMetaData name="RTColumnProp" value="x"/>
    </has_DSMetaBag></has_OutputPin>
  </contains_JobObject>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="TrfNlist" stageType="CTransformerStage" internalID="V0S169" inputPins="V0S169P1" outputPins="V0S169P2">
    <has_InputPin name="LnkNlist"><has_DSMetaBag><has_DSMetaData name="CPF_CNPJ" type="string" extendedType="string[max=20]"/></has_DSMetaBag></has_InputPin>
    <has_OutputPin name="LnkDadosNlist"><has_DSMetaBag>
      <has_DSMetaData name="IND_PESSOA_NLIST" type="string" extendedType="string[max=20]"/>
      <has_DSMetaData name="CHAVE_NLIST" type="int32"/>
    </has_DSMetaBag>
      <hasValue_Derivation name="IND_PESSOA_NLIST" expression="trim(Right(STR('0',20):LnkNlist.CPF_CNPJ,20))" sourceColumn="LnkNlist.CPF_CNPJ"/>
      <hasValue_Derivation name="CHAVE_NLIST" expression="1" sourceColumn=""/>
    </has_OutputPin>
    <of_DSMetaBag><has_DSMetaData name="TrxGenCode" value="// Generated file&#10;mainloop {{&#10;  LnkDadosNlist.IND_PESSOA_NLIST = trimc_string(x);&#10;  writerecord 0;&#10;}}&#10;finish {{ }}"/></of_DSMetaBag>
  </contains_JobObject>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="DST_FTP_NLIST" stageType="PxDataSet" internalID="V0S200" inputPins="V0S200P1">
    <has_ParameterVal Name="dataset" valueExpression="#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds" usage="In"/>
  </contains_JobObject>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="TB_DEST" stageType="ODBCConnectorPX" internalID="V0S210" inputPins="V0S210P1">
    <has_ParameterVal parameterName="Context" valueExpression="target"/>
    <has_ParameterVal parameterName="XMLProperties" valueExpression="{XMLPROPS_TABELA}"/>
  </contains_JobObject>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="Misterio" stageType="PxAlienStage" internalID="V0S300" inputPins="V0S300P1"/>
  <contains_JobObject xsi:type="ds:DSLinkSDO" name="LnkNlist"/>
  <has_DSDesignView lazyLoadInfo="StageID=185|StageNames=DM_119_INFO|StageTypeIDs=ODBCConnectorPX|LI=LinkNames=LnkNlist|LI=TargetStageIDs=V0S169 StageID=169|StageNames=TrfNlist|StageTypeIDs=CTransformerStage|LI=LinkNames=LnkDadosNlist|LI=TargetStageIDs=V0S200 StageID=200|StageNames=DST_FTP_NLIST|StageTypeIDs=PxDataSet StageID=300|StageNames=Misterio|StageTypeIDs=PxAlienStage"/>
</ds:DSJobDefSDO>
"""

SJB = """<?xml version="1.0" encoding="UTF-8"?>
<ds:DSJobDefSDO xmlns:ds="http://www.ibm.com/datastage/ds" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    name="SeqSsdVidaDime" jobType="Sequence" shortDescription="Sequence de amostra">
  <contains_JobObject xsi:type="ds:DSStageSDO" name="Act_Pessoa" stageType="CJobActivity" internalID="V0S1" outputPins="V0S1P1">
    <has_ParameterVal parameterName="JobName" valueExpression="SsdVidaDimePessoa02Ftp"/>
  </contains_JobObject>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="SsdVidaOutroJob" stageType="CJobActivity" internalID="V0S2" inputPins="V0S2P1"/>
  <contains_JobObject xsi:type="ds:DSStageSDO" name="Seq1" stageType="CSequencerActivity" internalID="V0S3" inputPins="V0S3P1" outputPins="V0S3P2"/>
  <has_DSDesignView lazyLoadInfo="StageID=1|StageNames=Act_Pessoa|StageTypeIDs=CJobActivity|LI=LinkNames=ok|LI=TargetStageIDs=V0S3 StageID=3|StageNames=Seq1|StageTypeIDs=CSequencerActivity|LI=LinkNames=out|LI=TargetStageIDs=V0S2 StageID=2|StageNames=SsdVidaOutroJob|StageTypeIDs=CJobActivity"/>
</ds:DSJobDefSDO>
"""


def isx(membros: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, texto in membros.items():
            zf.writestr(nome, texto.encode("utf-8") if isinstance(texto, str) else texto)
    return buf.getvalue()


ISX_PJB = isx({"SsdVidaDimePessoa02Ftp.pjb": PJB})
ISX_SJB = isx({"SeqSsdVidaDime.sjb": SJB, "SsdVidaDimePessoa02Ftp.pjb": PJB})


# ═══════════════════════════════════════════════════════════════════════════
# 1. Configuração, nomes, caminho, comando
# ═══════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_do_ambiente_normaliza(self):
        assert CFG.api_url == "http://ds-api-amostra:9443/ibm/iis/ds/api"   # sem barra final
        assert CFG.istool_home == "/opt/IBM/InformationServer"
        assert CFG.api_verify is False
        assert CFG.faltas() == []
        assert E.ConfigISX.do_ambiente(sem("DS_ISTOOL_TMP")).istool_tmp == "~/.orquestra/tmp"   # privado, não /tmp

    def test_verify_ssl_aceita_caminho_de_ca(self):
        c = E.ConfigISX.do_ambiente({**AMBIENTE, "DS_API_VERIFY_SSL": "/etc/ssl/ca-interna.pem"})
        assert c.api_verify == "/etc/ssl/ca-interna.pem"
        assert E.ConfigISX.do_ambiente({**AMBIENTE, "DS_API_VERIFY_SSL": "true"}).api_verify is True
        assert E.ConfigISX.do_ambiente({**AMBIENTE, "DS_API_VERIFY_SSL": ""}).api_verify is True

    def test_faltas_nomeiam_as_variaveis(self):
        c = E.ConfigISX.do_ambiente({})
        assert c.faltas() == ["DS_ENGINE", "DS_API_URL", "DS_API_USER/DS_API_PASSWORD", "DS_ISTOOL_DOMAIN", "DS_ISTOOL_AUTHFILE"]
        assert E.ConfigISX.do_ambiente({**AMBIENTE, "DS_API_PASSWORD": ""}).faltas() == ["DS_API_USER/DS_API_PASSWORD"]

    def test_repr_nao_mostra_a_senha(self):
        c = E.ConfigISX.do_ambiente({**AMBIENTE, "DS_API_PASSWORD": "S3gr3d0-xyz"})
        assert c.api_password == "S3gr3d0-xyz"
        assert "S3gr3d0-xyz" not in repr(c) and "S3gr3d0-xyz" not in str(c) and "S3gr3d0-xyz" not in f"{c!r}"


class TestNomesECaminhos:
    def test_nomes_validos_e_invalidos(self):
        assert E.validar_nome(" BI_VIDA ", "Projeto") == "BI_VIDA"
        assert E.validar_nome("Ssd.Vida-02", "Job") == "Ssd.Vida-02"
        for ruim in ("", "a b", "x;rm -rf /", "$(id)", "a/b", "..", "ação", "a" * 201):
            with pytest.raises(E.ISXError) as ei:
                E.validar_nome(ruim, "Job")
            assert ei.value.status == 422

    def test_pasta_como_a_api_devolve(self):
        assert E.validar_pasta("\\Jobs\\SsdVida\\_Dime") == ["Jobs", "SsdVida", "_Dime"]
        assert E.validar_pasta("Jobs/Com Espaco/x") == ["Jobs", "Com Espaco", "x"]
        # pastas reais: "03. Dimensões", "05. Projetos/AcumuloIS_Diaria", parênteses
        assert E.validar_pasta("\\Jobs\\03. Dimensões\\Sub (v2) & cia") == ["Jobs", "03. Dimensões", "Sub (v2) & cia"]
        for ruim in ("", "\\Outra\\x", "\\Jobs\\..\\etc", "\\Jobs\\a;b", "\\Jobs\\ x", "\\Jobs\\a$(id)", "\\Jobs\\a'b",
                     "\\Jobs\\a​b", "\\Jobs\\a­b", "\\Jobs\\a`b", "\\Jobs\\a|b"):
            with pytest.raises(E.ISXError):
                E.validar_pasta(ruim)

    def test_caminho_istool(self):
        assert E.caminho_istool("AMOSTRA.DEV", "BI_VIDA", "\\Jobs\\SsdVida\\_Dime", "SsdVidaDimePessoa02Ftp", "parallel") == \
            "AMOSTRA.DEV/BI_VIDA/Jobs/SsdVida/_Dime/SsdVidaDimePessoa02Ftp.pjb"
        # sequence: .qjb primeiro (chama outros jobs), .sjb depois — a API diz só SEQUENCE
        assert E.caminhos_istool("E", "P", "\\Jobs", "Seq", "SEQUENCE") == ["E/P/Jobs/Seq.qjb", "E/P/Jobs/Seq.sjb"]
        assert E.caminhos_istool("E", "P", "\\Jobs", "J", "PARALLEL") == ["E/P/Jobs/J.pjb"]
        assert E.caminho_istool("E", "P", "\\Jobs", "Seq", "SEQUENCE").endswith("/Jobs/Seq.qjb")
        with pytest.raises(E.ISXError):
            E.caminho_istool("E", "P", "\\Jobs", "x; id", "PARALLEL")
        with pytest.raises(E.ISXError):
            E.tipo_job("SERVER")

    def test_nome_archive_unico(self):
        a, b = E.nome_archive(CFG, "Job1"), E.nome_archive(CFG, "Job1")
        assert a.startswith("/tmp/orq_Job1_") and a.endswith(".isx") and a != b
        assert E.nome_archive(E.ConfigISX.do_ambiente(sem("DS_ISTOOL_TMP")), "J").startswith("~/.orquestra/tmp/orq_J_")

    def test_caminho_sftp_nao_tem_til(self):
        assert E.caminho_sftp("~/.orquestra/tmp/x.isx") == ".orquestra/tmp/x.isx"
        assert E.caminho_sftp("/tmp/x.isx") == "/tmp/x.isx"
        assert E.caminho_sftp("~") == "." and E.caminho_sftp("~/") == "."


class TestComandoIstool:
    def test_comando_com_authfile_e_sem_senha(self):
        cmd = E.comando_istool(CFG, "AMOSTRA.DEV/BI_VIDA/Jobs/A/J.pjb", "/tmp/orq_J_abc.isx")
        assert cmd.startswith(". /opt/IBM/InformationServer/ASBNode/bin/setupEnv.sh >/dev/null 2>&1 && umask 077 && mkdir -p -m 700 /tmp && ")
        assert '"$JAVA_HOME"/bin/java -jar /opt/IBM/InformationServer/Clients/istools/cli/plugins/org.eclipse.equinox.launcher_1.1.0.v20100507.jar' in cmd
        assert "-authfile /config/.orquestra/istool.auth" in cmd
        assert "-archive /tmp/orq_J_abc.isx -datastage AMOSTRA.DEV/BI_VIDA/Jobs/A/J.pjb" in cmd
        assert "find /tmp -maxdepth 1 -name 'orq_*.isx' -mmin +10 -delete 2>/dev/null; " in cmd
        assert "-password" not in cmd and "amostra" not in cmd.replace("ds-api-amostra", "")
        assert "cp -rn" in cmd and "-preview" not in cmd
        assert "-preview" in E.comando_istool(CFG, "E/P/Jobs/*/*.*", "/dev/null", preview=True)

    def test_tudo_que_vem_de_fora_e_citado(self):
        c = E.ConfigISX.do_ambiente({**AMBIENTE, "DS_ISTOOL_AUTHFILE": "/tmp/pasta com espaco/auth", "DS_ISTOOL_CFG": "/tmp/c$fg",
                                     "DS_ISTOOL_TMP": "/tmp/t m p"})
        cmd = E.comando_istool(c, "E/P/Jobs/J.pjb", "/tmp/t m p/a b.isx")
        assert "-authfile '/tmp/pasta com espaco/auth'" in cmd
        assert "-configuration '/tmp/c$fg'" in cmd and "-archive '/tmp/t m p/a b.isx'" in cmd
        assert "mkdir -p -m 700 '/tmp/t m p'" in cmd and "find '/tmp/t m p' -maxdepth 1" in cmd

    def test_til_vira_home_fora_das_aspas(self):
        # defaults de DS_ISTOOL_CFG e DS_ISTOOL_TMP são no home: entre aspas o til não expandiria
        c = E.ConfigISX.do_ambiente(sem("DS_ISTOOL_CFG", "DS_ISTOOL_TMP"))
        cmd = E.comando_istool(c, "E/P/Jobs/J.pjb", E.nome_archive(c, "J"))
        assert 'mkdir -p -m 700 "$HOME"/.orquestra/tmp && mkdir -p "$HOME"/.orquestra/istool_cfg' in cmd
        assert '-configuration "$HOME"/.orquestra/istool_cfg ' in cmd
        assert '-archive "$HOME"/.orquestra/tmp/orq_J_' in cmd and 'find "$HOME"/.orquestra/tmp -maxdepth 1' in cmd
        assert "'~" not in cmd
        assert E._caminho_shell("~") == '"$HOME"' and E._caminho_shell("~/a b") == '"$HOME"/\'a b\''  # noqa: SLF001
        assert E._caminho_shell("/x/~y") == "'/x/~y'"  # noqa: SLF001

    def test_datastage_com_espaco_vai_escapado_dentro_das_aspas(self):
        # o istool quebra o caminho no espaço mesmo entre aspas simples (medido em produção)
        cmd = E.comando_istool(CFG, "E/P/Jobs/04. ODS/03. Dimensões/Seq.qjb", "/tmp/x.isx")
        assert "-datastage 'E/P/Jobs/04.\\ ODS/03.\\ Dimensões/Seq.qjb'" in cmd
        assert E._caminho_datastage_shell("E/P/Jobs/J.pjb") == "E/P/Jobs/J.pjb"  # noqa: SLF001

    def test_authfile_com_password_no_nome_do_caminho_nao_quebra(self):
        c = E.ConfigISX.do_ambiente({**AMBIENTE, "DS_ISTOOL_AUTHFILE": "/etc/ds-password/auth"})
        cmd = E.comando_istool(c, "E/P/Jobs/J.pjb", "/tmp/x.isx")
        assert "-authfile /etc/ds-password/auth" in cmd and " -password " not in cmd

    def test_sem_authfile_ou_dominio_e_503(self):
        with pytest.raises(E.ISXError) as ei:
            E.comando_istool(E.ConfigISX.do_ambiente({**AMBIENTE, "DS_ISTOOL_AUTHFILE": ""}), "E/P/Jobs/J.pjb", "/tmp/x")
        assert ei.value.status == 503 and "DS_ISTOOL_AUTHFILE" in ei.value.detail
        with pytest.raises(E.ISXError) as ei:
            E.comando_istool(E.ConfigISX.do_ambiente({**AMBIENTE, "DS_ISTOOL_DOMAIN": ""}), "E/P/Jobs/J.pjb", "/tmp/x")
        assert ei.value.status == 503


class TestClassificacao:
    def test_mapa_do_banco_manda(self):
        mapa = {"ODBCConnectorPX": {"type_category": "banco", "type_label": "Banco de Dados ODBC"}}
        assert T.classe_do_tipo("ODBCConnectorPX", mapa) == ("banco", "Banco de Dados ODBC", True)
        assert T.classe_do_tipo("PxDataSet", mapa) == ("arquivo", "Arquivo", True)      # fallback do conjunto
        assert T.classe_do_tipo("CTransformerStage") == ("transformacao", "Transformer", True)
        assert T.classe_do_tipo("CJobActivity") == ("sequence", "Sequence", True)
        assert T.classe_do_tipo("CSequencer") == ("sequence", "Sequence", True)
        assert T.classe_do_tipo("MeuConnectorNovo") == ("banco", "ODBC", False)       # pelo nome, não reconhecido
        assert T.classe_do_tipo("PxAlienStage") == (None, "PxAlienStage", False)

    def test_direcao(self):
        assert T.direcao("transformacao", None, True, True) == "transformacao"
        assert T.direcao("banco", "source", True, True) == "origem"
        assert T.direcao("banco", "target", True, True) == "destino"
        assert T.direcao("arquivo", None, False, True) == "origem"
        assert T.direcao("arquivo", None, True, False) == "destino"
        assert T.direcao(None, None, True, True) == "transformacao"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Parser
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def r():
    return E.parse_isx(ISX_PJB)


class TestParseParallel:
    def test_cabecalho_e_parametros(self, r):
        assert r["job_name"] == "SsdVidaDimePessoa02Ftp" and r["job_type"] == "PARALLEL"
        assert r["job_description"] == "ETL de amostra" and r["job_long_description"].startswith("Homologado")
        assert r["last_modification_xml"] == "2026-08-04T00:37:15.253-0300" and r["nls_map"] == "ISO_8859-1:1987"
        assert r["parameters"] == [
            {"name": "PSetSsdVida", "type": "Parameterset", "default": "(As pre-defined)", "description": "Parametros VIDA"},
            {"name": "$APT_NO_SORT_INSERTION", "type": "Stringlist", "default": "False", "description": ""},
            {"name": "ParmSenhaBanco", "type": "Encrypted", "default": "***", "description": ""},   # segredo mascarado
            {"name": "DbPassword", "type": "String", "default": "***", "description": ""},          # pelo nome
        ]
        assert "OFUSCADO_REVERSIVEL" not in str(r) and "abc123" not in str(r)
        assert r["isx_bytes"] == len(ISX_PJB) and len(r["isx_sha256"]) == 64 and r["membro"] == "SsdVidaDimePessoa02Ftp.pjb"

    def test_stages_direcao_e_classe(self, r):
        por = {s["stage_name"]: s for s in r["stages"]}
        assert [s["stage_name"] for s in r["stages"]] == ["DM_119_INFO", "TrfNlist", "DST_FTP_NLIST", "TB_DEST", "Misterio"]
        assert por["DM_119_INFO"]["direction"] == "origem" and por["DM_119_INFO"]["object_type"] == "ODBC"
        assert por["TrfNlist"]["direction"] == "transformacao" and por["TrfNlist"]["object_type"] == "Transformer"
        assert por["DST_FTP_NLIST"]["direction"] == "destino" and por["DST_FTP_NLIST"]["object_type"] == "Arquivo"
        assert por["TB_DEST"]["direction"] == "destino"
        assert por["DM_119_INFO"]["internal_id"] == "V0S185"
        # links (DSLinkSDO) não viram stage
        assert "LnkNlist" not in por

    def test_sql_dsn_e_segredo_nunca_sai(self, r):
        o = {s["stage_name"]: s for s in r["stages"]}["DM_119_INFO"]
        assert o["sql_expression"].startswith("select distinct") and "DM_056_PESSOA" in o["sql_expression"]
        assert "<> 'N'" in o["sql_expression"] and o["sql_tag"] == "SelectStatement"
        assert o["database_hint"] == "Ssd" and o["database_name"] == "Ssd"
        assert "SEGREDO_NAO_PODE_SAIR" not in str(r)
        d = {s["stage_name"]: s for s in r["stages"]}["TB_DEST"]
        assert d["database_name"] == "DSN_STG" and d["database_hint"] is None
        # a tabela-alvo vence o BeforeSQL (TRUNCATE) — é ela que o lineage quer
        assert d["sql_expression"] == "dbo.TB_DESTINO" and d["sql_tag"] == "TableName"

    def test_colunas_expressoes_apt_e_arquivo(self, r):
        por = {s["stage_name"]: s for s in r["stages"]}
        assert por["DM_119_INFO"]["output_columns"] == [{"name": "CPF_CNPJ", "type": "string", "length": 20}]
        t = por["TrfNlist"]
        assert t["input_columns"] == [{"name": "CPF_CNPJ", "type": "string", "length": 20}]
        assert t["output_columns"] == [{"name": "IND_PESSOA_NLIST", "type": "string", "length": 20},
                                       {"name": "CHAVE_NLIST", "type": "int32", "length": None}]
        assert t["expressions"] == [
            {"output_col": "IND_PESSOA_NLIST", "expression": "trim(Right(STR('0',20):LnkNlist.CPF_CNPJ,20))", "source_col": "LnkNlist.CPF_CNPJ"},
            {"output_col": "CHAVE_NLIST", "expression": "1", "source_col": ""},
        ]
        assert t["apt_code"].startswith("mainloop {") and t["apt_code"].endswith("}") and "finish" not in t["apt_code"]
        assert por["DST_FTP_NLIST"]["file_path"] == "#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds"
        # destino sem schema herda as colunas de saída de quem o alimenta
        assert por["DST_FTP_NLIST"]["input_columns"] == t["output_columns"]

    def test_fluxo_e_nao_reconhecidos(self, r):
        assert r["flow"] == [
            {"from": "DM_119_INFO", "from_type": "ODBCConnectorPX", "link": "LnkNlist", "to": "TrfNlist", "to_type": "CTransformerStage"},
            {"from": "TrfNlist", "from_type": "CTransformerStage", "link": "LnkDadosNlist", "to": "DST_FTP_NLIST", "to_type": "PxDataSet"},
        ]
        assert r["nao_reconhecidos"] == [{"stage": "Misterio", "stage_type": "PxAlienStage", "motivo": "tipo fora do mapa"}]
        assert r["children"] == []

    def test_mapa_do_banco_troca_o_rotulo(self):
        r = E.parse_isx(ISX_PJB, {"ODBCConnectorPX": {"type_category": "banco", "type_label": "Banco de Dados ODBC"},
                                  "PxAlienStage": {"type_category": "transformacao", "type_label": "Alien"}})
        por = {s["stage_name"]: s for s in r["stages"]}
        assert por["DM_119_INFO"]["object_type"] == "Banco de Dados ODBC"
        assert por["Misterio"]["direction"] == "transformacao" and r["nao_reconhecidos"] == []


class TestParseSequence:
    def test_filhos_e_tipo(self):
        r = E.parse_isx(ISX_SJB)
        assert r["job_type"] == "SEQUENCE" and r["membro"] == "SeqSsdVidaDime.sjb"   # o .sjb manda mesmo com .pjb junto
        # só a atividade COM JobName vira filho; a outra vai para nao_reconhecidos (sem chute pelo nome)
        assert r["children"] == [{"job_name": "SsdVidaDimePessoa02Ftp", "activity": "Act_Pessoa"}]
        assert r["nao_reconhecidos"] == [{"stage": "SsdVidaOutroJob", "stage_type": "CJobActivity", "motivo": "atividade de job sem JobName"}]
        por = {s["stage_name"]: s for s in r["stages"]}
        assert por["Act_Pessoa"]["direction"] == "transformacao" and por["Act_Pessoa"]["object_type"] == "Sequence"
        assert all(s["sql_expression"] is None for s in r["stages"])
        assert [f["to"] for f in r["flow"]] == ["Seq1", "SsdVidaOutroJob"]

    def test_sequence_real_jobname_no_atributo_e_lazyload_sem_espaco(self):
        # forma documentada do .qjb: `jobname` no próprio stage, IDs V22S<n>, blocos sem espaço,
        # vários links por nó (paralelismo) separados por vírgula
        qjb = """<?xml version="1.0" encoding="UTF-8"?>
<com.ibm.datastage.ai.dtm.ds:DSJobDefSDO xmlns:com.ibm.datastage.ai.dtm.ds="http://www.ibm.com/datastage/ds"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="SeqSsdPrs_CargaDiaria" jobType="Sequence">
  <contains_JobObject xsi:type="com.ibm.datastage.ai.dtm.ds:DSStageSDO" stageType="CJobActivity" name="Dimensoes" jobname="SeqSsdPrs_Dim" internalID="V22S3" outputPins="V22S3P1"/>
  <contains_JobObject xsi:type="com.ibm.datastage.ai.dtm.ds:DSStageSDO" stageType="CJobActivity" name="ODS" jobname="SeqSsdPrs_ODS" internalID="V22S5" inputPins="V22S5P1"/>
  <contains_JobObject xsi:type="com.ibm.datastage.ai.dtm.ds:DSStageSDO" stageType="CJobActivity" name="AcmIS" jobname="SeqSsdPrs_AcmIS" internalID="V22S8" inputPins="V22S8P1"/>
  <contains_JobObject xsi:type="com.ibm.datastage.ai.dtm.ds:DSStageSDO" stageType="CSequencer" name="Junta" internalID="V22S9" inputPins="V22S9P1"/>
  <has_DSDesignView lazyLoadInfo="StageID=3|StageNames=Dimensoes|StageTypeIDs=CJobActivity|LI=LinkNames=LinkParaODS,LinkParaAcm|LI=TargetStageIDs=V22S5,V22S8StageID=5|StageNames=ODS|StageTypeIDs=CJobActivityStageID=8|StageNames=AcmIS|StageTypeIDs=CJobActivity|LI=LinkNames=ok|LI=TargetStageIDs=V22S9StageID=9|StageNames=Junta|StageTypeIDs=CSequencer"/>
</com.ibm.datastage.ai.dtm.ds:DSJobDefSDO>
"""
        r = E.parse_isx(isx({"SeqSsdPrs_CargaDiaria.qjb": qjb}))
        assert r["job_type"] == "SEQUENCE" and r["membro"].endswith(".qjb")
        assert r["children"] == [{"job_name": "SeqSsdPrs_Dim", "activity": "Dimensoes"},
                                 {"job_name": "SeqSsdPrs_ODS", "activity": "ODS"},
                                 {"job_name": "SeqSsdPrs_AcmIS", "activity": "AcmIS"}]
        assert r["nao_reconhecidos"] == []
        assert [(f["from"], f["link"], f["to"], f["to_type"]) for f in r["flow"]] == [
            ("Dimensoes", "LinkParaODS", "ODS", "CJobActivity"), ("Dimensoes", "LinkParaAcm", "AcmIS", "CJobActivity"),
            ("AcmIS", "ok", "Junta", "CSequencer")]
        assert {s["stage_name"]: s["object_type"] for s in r["stages"]}["Junta"] == "Sequence"

    def test_membro_escolhido_pelo_job_pedido(self):
        z = isx({"SeqZ_principal.sjb": SJB.replace('name="SeqSsdVidaDime"', 'name="SeqZ_principal"'),
                 "SeqA_filho.sjb": SJB.replace('name="SeqSsdVidaDime"', 'name="SeqA_filho"')})
        assert E.parse_isx(z)["membro"] == "SeqA_filho.sjb"                       # sem job: alfabético
        r = E.parse_isx(z, job="SeqZ_principal")
        assert r["membro"] == "SeqZ_principal.sjb" and r["job_name"] == "SeqZ_principal"
        assert E.parse_isx(z, job="NaoTem")["membro"] == "SeqA_filho.sjb"          # sem membro do job: cai no padrão


class TestParseTolerancia:
    def test_variantes_do_xml(self):
        # PJB é f-string: as chaves duplas do fonte já viraram simples aqui
        pjb = PJB.replace('value="// Generated file&#10;mainloop {', 'value="sem mainloop aqui {').replace("}&#10;finish { }", "}")
        assert "sem mainloop aqui" in pjb and "finish" not in pjb
        r = E.parse_isx(isx({"x.pjb": pjb}))
        t = {s["stage_name"]: s for s in r["stages"]}["TrfNlist"]
        assert t["apt_code"].startswith("sem mainloop aqui")           # sem `mainloop`: devolve o bloco inteiro
        sem_ext = PJB.replace('type="string" extendedType="string[max=20]"/>\n      <has_DSMetaData name="RTColumnProp"',
                              'type="string"/>\n      <has_DSMetaData name="RTColumnProp"')
        r2 = E.parse_isx(isx({"x.pjb": sem_ext}))
        assert {s["stage_name"]: s for s in r2["stages"]}["DM_119_INFO"]["output_columns"] == [{"name": "CPF_CNPJ", "type": "string", "length": None}]
        # comprimento absurdo não explode o int()
        absurdo = PJB.replace('extendedType="string[max=20]"', 'extendedType="string[max=99999999999999999]"', 1)
        r3 = E.parse_isx(isx({"x.pjb": absurdo}))
        assert {s["stage_name"]: s for s in r3["stages"]}["DM_119_INFO"]["output_columns"][0]["length"] is None

    def test_arquivo_pelo_metadado_do_pin_e_metadado_nao_vira_coluna(self):
        # sem has_ParameterVal Name="dataset": o path vem do has_DSMetaData name="dataset" value=… do pin,
        # e esse metadado (sem type) NÃO entra na lista de colunas
        pjb = PJB.replace('<has_ParameterVal Name="dataset" valueExpression="#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds" usage="In"/>',
                          '<has_InputPin name="LnkDadosNlist"><has_DSMetaBag><has_DSMetaData name="dataset" value="/dados/dst/NLIST.ds"/>'
                          '<has_DSMetaData name="IND_PESSOA_NLIST" type="string" extendedType="string[max=20]"/></has_DSMetaBag></has_InputPin>')
        d = {s["stage_name"]: s for s in E.parse_isx(isx({"x.pjb": pjb}))["stages"]}["DST_FTP_NLIST"]
        assert d["file_path"] == "/dados/dst/NLIST.ds"
        assert d["input_columns"] == [{"name": "IND_PESSOA_NLIST", "type": "string", "length": 20}]

    def test_varios_links_por_stage_e_stage_sem_atributo_de_pins(self):
        pjb = PJB.replace("LI=LinkNames=LnkDadosNlist|LI=TargetStageIDs=V0S200", "LI=LinkNames=LnkDadosNlist,LnkOutro|LI=TargetStageIDs=V0S200,V0S210")
        pjb = pjb.replace("StageID=300|StageNames=Misterio", "StageID=210|StageNames=TB_DEST|StageTypeIDs=ODBCConnectorPX StageID=300|StageNames=Misterio")
        pjb = pjb.replace('name="DST_FTP_NLIST" stageType="PxDataSet" internalID="V0S200" inputPins="V0S200P1">',
                          'name="DST_FTP_NLIST" stageType="PxDataSet" internalID="V0S200">\n    <has_InputPin name="LnkDadosNlist"/>')
        r = E.parse_isx(isx({"x.pjb": pjb}))
        assert [(f["link"], f["to"]) for f in r["flow"]][1:] == [("LnkDadosNlist", "DST_FTP_NLIST"), ("LnkOutro", "TB_DEST")]
        assert {s["stage_name"]: s for s in r["stages"]}["DST_FTP_NLIST"]["direction"] == "destino"   # pelo has_InputPin

    def test_recusas(self):
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(b"nao e zip")
        assert ei.value.status == 422
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"leia-me.txt": "x"}))
        assert ei.value.status == 422 and ".pjb" in ei.value.detail
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"x.pjb": '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY b "c">]><a>&b;</a>'}))
        assert ei.value.status == 422 and "DOCTYPE" in ei.value.detail
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"x.pjb": "<a><b></a>"}))
        assert ei.value.status == 422
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(b"x" * (E.ISX_MAX_BYTES + 1))
        assert ei.value.status == 413

    def test_formato_inesperado_nao_cala(self):
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"x.pjb": "<a/>"}))
        assert ei.value.status == 422 and "DSJobDefSDO" in ei.value.detail
        envolto = '<xmi:XMI xmlns:xmi="http://www.omg.org/XMI">' + PJB.split("?>", 1)[1] + "</xmi:XMI>"
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"x.pjb": envolto}))
        assert ei.value.status == 422 and "XMI" in ei.value.detail
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"x.pjb": '<ds:DSJobDefSDO xmlns:ds="http://www.ibm.com/datastage/ds" name="Vazio"/>'}))
        assert ei.value.status == 422 and "stage" in ei.value.detail

    def test_doctype_escondido_e_utf16(self):
        tarde = '<?xml version="1.0"?><!--' + "x" * 6000 + '--><!DOCTYPE a [<!ENTITY b "c">]><a>&b;</a>'
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(isx({"x.pjb": tarde}))
        assert ei.value.status == 422 and "DOCTYPE" in ei.value.detail
        for enc in ("utf-16-le", "utf-16-be", "utf-16"):
            u16 = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE a [<!ENTITY b "c">]><a>&b;</a>').encode(enc)
            with pytest.raises(E.ISXError) as ei:
                E.parse_isx(isx({"x.pjb": u16}))
            assert ei.value.status == 422 and "DOCTYPE" in ei.value.detail, enc

    def test_bomba_zip_e_recusada_antes_de_descomprimir(self):
        bomba = isx({"x.pjb": b"0" * (E.ISX_MAX_BYTES + 1)})
        assert len(bomba) < 200_000                                             # comprime ~1000:1
        with pytest.raises(E.ISXError) as ei:
            E.parse_isx(bomba)
        assert ei.value.status == 413
        # cabeçalho mentindo o tamanho: a leitura com teto pega
        zf_bytes = bytearray(bomba)
        # (não dá para forjar o file_size sem reescrever o ZIP; provamos o segundo teto direto)
        with zipfile.ZipFile(io.BytesIO(bytes(zf_bytes))) as zf:
            info = zf.getinfo("x.pjb")
            info.file_size = 10
            with pytest.raises(E.ISXError) as ei:
                E._membro_principal(zf)  # noqa: SLF001
            assert ei.value.status in (413, 422)

    def test_cdata_e_mainloop_nao_sao_quadraticos(self):
        hostil = "<SelectStatement " * 3000 + "x"
        t0 = time.perf_counter()
        assert E._cdata(hostil, "SelectStatement") is None  # noqa: SLF001
        assert E._mainloop("mainloop {" * 3000 + "x") is None  # noqa: SLF001
        assert time.perf_counter() - t0 < 1.0
        assert E._cdata("<T type='s'><![CDATA[ a ]]></T>", "T") == "a" and E._cdata("<Tx>b</Tx><T>c</T>", "T") == "c"  # noqa: SLF001
        assert E._mainloop("x mainloop\n{\n a\n}\nfinish") == "mainloop\n{\n a\n}"  # noqa: SLF001


@pytest.mark.skipif(not FIXTURES.is_dir() or not list(FIXTURES.glob("*.isx")), reason="sem .isx reais em tests/fixtures/isx/")
class TestParseReal:
    def test_isx_reais_parseiam_sem_calar(self):
        for arquivo in sorted(FIXTURES.glob("*.isx")):
            r = E.parse_isx(arquivo.read_bytes())
            assert r["job_name"] and r["stages"], arquivo.name
            assert all(s["direction"] in ("origem", "transformacao", "destino") for s in r["stages"])


# ═══════════════════════════════════════════════════════════════════════════
# 3. API REST falsa e SSH falso
# ═══════════════════════════════════════════════════════════════════════════

ROTAS = {
    "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs/contents": {"children": [
        {"$ref": "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida/contents", "children": True, "name": "SsdVida"},
        {"id": "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CJobRaiz", "jobType": "PARALLEL", "lastModifiedTimestamp": "2026-01-10T10:00:00.000+0000", "name": "JobRaiz"},
    ]},
    "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida/contents": {"children": [
        {"$ref": "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime/contents", "children": True, "name": "_Dime"},
    ]},
    "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime/contents": {"children": [
        {"id": "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5CSsdVidaDimePessoa02Ftp", "jobType": "PARALLEL",
         "lastModifiedTimestamp": "2026-08-04T03:37:15.253+0000", "name": "SsdVidaDimePessoa02Ftp"},
    ]},
    "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5CSsdVidaDimePessoa02Ftp": {
        "name": "SsdVidaDimePessoa02Ftp", "jobType": "PARALLEL", "folderPath": "\\Jobs\\SsdVida\\_Dime",
        "shortDescription": "d", "longDescription": "l", "lastModified": {"timestamp": "2026-08-04T03:37:15.253+0000"},
    },
}


def _rest(chamadas=None, rotas=None):
    rotas = ROTAS if rotas is None else rotas

    def rest(caminho):
        if chamadas is not None:
            chamadas.append(caminho)
        return rotas.get(caminho)
    return rest


class TestLocalizar:
    def test_acha_no_terceiro_nivel_e_devolve_a_pasta(self):
        chamadas = []
        r = E.localizar_job(_rest(chamadas), "AMOSTRA.DEV", "BI_VIDA", "SsdVidaDimePessoa02Ftp")
        assert r == {"api_id": "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5CSsdVidaDimePessoa02Ftp",
                     "folder_path": "\\Jobs\\SsdVida\\_Dime", "job_type": "PARALLEL",
                     "last_modified": "2026-08-04T03:37:15.253+0000"}
        assert chamadas == list(ROTAS)[:3]                              # largura: Jobs → SsdVida → _Dime
        assert E.localizar_job(_rest(), "AMOSTRA.DEV", "BI_VIDA", "JobRaiz")["folder_path"] == "\\Jobs"

    def test_nao_achado_e_tetos(self):
        assert E.localizar_job(_rest(), "AMOSTRA.DEV", "BI_VIDA", "NaoExiste") is None
        with pytest.raises(E.ISXError) as ei:
            E.localizar_job(_rest(), "AMOSTRA.DEV", "BI_VIDA", "SsdVidaDimePessoa02Ftp", max_nos=2)
        assert ei.value.status == 504 and "informe a pasta" in ei.value.detail
        relogio = iter([0.0, 0.0, 100.0, 100.0])
        with pytest.raises(E.ISXError) as ei:
            E.localizar_job(_rest(), "AMOSTRA.DEV", "BI_VIDA", "SsdVidaDimePessoa02Ftp", teto_s=30, relogio=lambda: next(relogio))
        assert ei.value.status == 504 and "30 s" in ei.value.detail
        with pytest.raises(E.ISXError):
            E.localizar_job(_rest(), "AMOSTRA.DEV", "BI_VIDA", "x;y")

    def test_refs_e_ids_hostis_sao_ignorados(self):
        # a API é confiável, mas o transporte anexa Basic auth ao que pedir: só caminhos desta API
        hostis = {"folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs/contents": {"children": [
            {"$ref": "http://evil.example/x", "children": True, "name": "X"},
            {"$ref": "/folders/../../launchpad/contents", "children": True, "name": "Y"},
            {"$ref": "folders/A%5CB/contents/../..", "children": True, "name": "Z"},
            {"id": "jobdesigns/../../../x", "name": "Alvo"},
            {"id": "https://evil.example/jobdesigns/x", "name": "Alvo"},
            {"$ref": "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5COk/contents", "children": True, "name": "Ok"},
        ]}, "folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5COk/contents": {"children": [
            {"id": "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5COk%5CAlvo", "name": "Alvo", "jobType": "PARALLEL"}]}}
        chamadas = []
        r = E.localizar_job(_rest(chamadas, hostis), "AMOSTRA.DEV", "BI_VIDA", "Alvo")
        assert r["api_id"] == "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5COk%5CAlvo" and r["folder_path"] == "\\Jobs\\Ok"
        assert chamadas == list(hostis)                                  # nenhum pedido fora de folders/…
        for ruim in ("http://evil.example/j", "jobdesigns/../x", "/jobdesigns/x:y", "folders/A/contents", ""):
            with pytest.raises(E.ISXError) as ei:
                E.checar_modificado(_rest(), ruim)
            assert ei.value.status == 422, ruim

    def test_checar_modificado_e_api_id(self):
        m = E.checar_modificado(_rest(), "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5CSsdVidaDimePessoa02Ftp")
        assert m == {"last_modified": "2026-08-04T03:37:15.253+0000", "job_type": "PARALLEL",
                     "folder_path": "\\Jobs\\SsdVida\\_Dime", "description": "d", "long_description": "l"}
        with pytest.raises(E.ISXError) as ei:
            E.checar_modificado(_rest(), "jobdesigns/nada")
        assert ei.value.status == 404
        assert E.api_id_de("AMOSTRA.DEV", "BI_VIDA", "\\Jobs\\SsdVida\\_Dime", "SsdVidaDimePessoa02Ftp") == \
            "jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5CSsdVidaDimePessoa02Ftp"


class _Arq:
    def __init__(self, dados: bytes):
        self.dados = dados
        self.pedidos: list[int] = []

    def read(self, n=-1):
        self.pedidos.append(n)
        return self.dados if n is None or n < 0 else self.dados[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Sftp:
    def __init__(self, arquivos: dict[str, bytes], tamanho_mentira: int | None = None):
        self.arquivos = dict(arquivos)
        self.removidos: list[str] = []
        self.abertos: list[str] = []
        self.tamanho_mentira = tamanho_mentira

    def stat(self, caminho):
        if caminho not in self.arquivos:
            raise OSError(2, "No such file")
        tam = self.tamanho_mentira if self.tamanho_mentira is not None else len(self.arquivos[caminho])
        return type("St", (), {"st_size": tam})()

    def open(self, caminho, modo="rb"):
        self.abertos.append(caminho)
        return _Arq(self.arquivos[caminho])

    def remove(self, caminho):
        self.removidos.append(caminho)
        self.arquivos.pop(caminho, None)


def _ssh(rc=0, saida="Exported 1 asset", erro="", isx_bytes=ISX_PJB, gerar=True, tamanho_mentira=None):
    registro = {"comandos": [], "sftp": None}

    @contextmanager
    def ssh():
        sftp = _Sftp({}, tamanho_mentira)
        registro["sftp"] = sftp

        def executar(cmd, timeout):
            registro["comandos"].append((cmd, timeout))
            if gerar:
                m = re.search(r"-archive (\S+)", cmd)
                caminho = m.group(1)
                # o shell expandiria "$HOME"/x; o sftp-server vê x relativo ao home
                caminho = caminho[len('"$HOME"/'):] if caminho.startswith('"$HOME"/') else caminho
                sftp.arquivos[caminho] = isx_bytes
            return rc, saida, erro
        yield executar, sftp
    return ssh, registro


class TestExportar:
    def test_exporta_le_e_apaga(self):
        ssh, reg = _ssh()
        dados = E.exportar(ssh, CFG, "AMOSTRA.DEV/BI_VIDA/Jobs/A/J.pjb", job="J", teto_s=45)
        assert dados == ISX_PJB
        cmd, teto = reg["comandos"][0]
        assert teto == 45 and "-authfile" in cmd and "-password" not in cmd and "umask 077" in cmd
        assert len(reg["sftp"].removidos) == 1 and reg["sftp"].arquivos == {}       # apagou o temporário
        assert reg["sftp"].abertos == reg["sftp"].removidos and reg["sftp"].removidos[0].startswith("/tmp/orq_J_")

    def test_tmp_no_home_vira_caminho_relativo_no_sftp(self):
        c = E.ConfigISX.do_ambiente(sem("DS_ISTOOL_TMP"))
        ssh, reg = _ssh()
        assert E.exportar(ssh, c, "E/P/Jobs/J.pjb", job="J") == ISX_PJB
        assert reg["sftp"].removidos[0].startswith(".orquestra/tmp/orq_J_") and reg["sftp"].arquivos == {}

    def test_exportar_job_tenta_qjb_depois_sjb(self):
        respostas = {".qjb": (1, "", "IISCOM123: DataStageSequenceJob not found"), ".sjb": (0, "Exported 1 asset", "")}
        tentativas: list[str] = []

        def ssh_por_extensao(respostas):
            @contextmanager
            def ssh():
                sftp = _Sftp({})

                def executar(cmd, timeout):
                    m = re.search(r"-datastage '?([^' ]+)'?", cmd)
                    caminho = m.group(1)
                    tentativas.append(caminho)
                    rc, out, err = respostas[caminho[-4:]]
                    if rc == 0:
                        sftp.arquivos[re.search(r"-archive (\S+)", cmd).group(1)] = ISX_SJB
                    return rc, out, err
                yield executar, sftp
            return ssh

        dados, caminho = E.exportar_job(ssh_por_extensao(respostas), CFG, "E", "P", "\\Jobs", "Seq", "SEQUENCE")
        assert dados == ISX_SJB and caminho == "E/P/Jobs/Seq.sjb" and tentativas == ["E/P/Jobs/Seq.qjb", "E/P/Jobs/Seq.sjb"]
        # nenhum candidato existe → 404 (não 502), com o stderr só no interno
        tentativas.clear()
        with pytest.raises(E.ISXError) as ei:
            E.exportar_job(ssh_por_extensao({".qjb": (1, "", "No assets matched x"), ".sjb": (1, "", "DataStageFolder not found")}),
                           CFG, "E", "P", "\\Jobs", "Seq", "SEQUENCE")
        assert ei.value.status == 404 and "not found" in ei.value.interno and len(tentativas) == 2
        # erro que NÃO é "não achei" (ex.: login) → 502 na hora, sem tentar o .sjb
        tentativas.clear()
        with pytest.raises(E.ISXError) as ei:
            E.exportar_job(ssh_por_extensao({".qjb": (1, "", "Login failed"), ".sjb": (0, "", "")}),
                           CFG, "E", "P", "\\Jobs", "Seq", "SEQUENCE")
        assert ei.value.status == 502 and tentativas == ["E/P/Jobs/Seq.qjb"]
        # parallel: um candidato só
        tentativas.clear()
        _, caminho = E.exportar_job(ssh_por_extensao({".pjb": (0, "", "")}), CFG, "E", "P", "\\Jobs", "J", "PARALLEL")
        assert caminho == "E/P/Jobs/J.pjb" and tentativas == ["E/P/Jobs/J.pjb"]

    def test_rc_diferente_de_zero_502_com_stderr_so_no_interno(self):
        ssh, reg = _ssh(rc=1, erro="IISCOM000: No assets matched", gerar=False)
        with pytest.raises(E.ISXError) as ei:
            E.exportar(ssh, CFG, "E/P/Jobs/J.pjb", job="J")
        assert ei.value.status == 502 and "IISCOM000" not in ei.value.detail and "IISCOM000" in ei.value.interno
        assert len(reg["sftp"].removidos) == 1                                        # remove mesmo sem arquivo

    def test_sem_arquivo_gerado_502_e_teto_413(self):
        ssh, _ = _ssh(rc=0, gerar=False)
        with pytest.raises(E.ISXError) as ei:
            E.exportar(ssh, CFG, "E/P/Jobs/J.pjb", job="J")
        assert ei.value.status == 502 and "sem gerar" in ei.value.detail
        ssh, reg = _ssh(isx_bytes=b"x" * (E.ISX_MAX_BYTES + 1))
        with pytest.raises(E.ISXError) as ei:
            E.exportar(ssh, CFG, "E/P/Jobs/J.pjb", job="J")
        assert ei.value.status == 413 and len(reg["sftp"].removidos) == 1 and reg["sftp"].abertos == []   # nem abriu
        # stat mentindo (arquivo cresceu depois): a leitura com teto pega
        ssh, reg = _ssh(isx_bytes=b"x" * (E.ISX_MAX_BYTES + 1), tamanho_mentira=10)
        with pytest.raises(E.ISXError) as ei:
            E.exportar(ssh, CFG, "E/P/Jobs/J.pjb", job="J")
        assert ei.value.status == 413 and len(reg["sftp"].removidos) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 4. Anti-drift
# ═══════════════════════════════════════════════════════════════════════════

def test_engine_nao_tem_segredo_nem_host_literal():
    fonte = (DAGS / "utils" / "isx_engine.py").read_text(encoding="utf-8")
    # senha/usuário só podem vir do ambiente: nenhuma atribuição literal, nenhum host real
    for proibido in ("-password ", 'password="', "password='", ".intranet", "lnxprd"):
        assert proibido not in fonte, proibido
    assert re.search(r"(?i)(password|senha|user|usuario|login)\s*=\s*['\"][^'\"]+['\"]", fonte) is None
    assert "field(repr=False)" in fonte
    assert "tests/fixtures/isx/" in (ROOT / ".gitignore").read_text(encoding="utf-8")   # .isx real nunca entra no git


def test_conjuntos_de_tipos_contem_os_do_dsx():
    assert DSX._TRANSFORM_TYPES <= (T.TRANSFORM_TYPES | T.SEQUENCE_TYPES)  # noqa: SLF001
    assert DSX._DB_TYPES <= T.DB_TYPES  # noqa: SLF001
    assert DSX._FILE_TYPES <= T.FILE_TYPES  # noqa: SLF001


def test_migration_106_idempotente_e_sem_mexer_no_pipeline_name():
    sql = (ROOT / "sql" / "migrations" / "106_lineage_isx.sql").read_text(encoding="utf-8")
    assert "IF OBJECT_ID('dbo.etl_ds_job_isx', 'U') IS NULL" in sql
    assert sql.count("IF COL_LENGTH('dbo.etl_job_lineage'") == 4
    assert "IF NOT EXISTS (SELECT 1 FROM sys.indexes" in sql
    assert "WHEN NOT MATCHED THEN" in sql and "WHEN MATCHED" not in sql.replace("WHEN NOT MATCHED", "")
    assert "ALTER COLUMN pipeline_name" not in sql and "DROP CONSTRAINT FK_etl_job_lineage_job" not in sql
    assert "FK_etl_ds_job_isx_job FOREIGN KEY (pipeline_name, job_name)" in sql
    # apagar/renomear o job no pipeline não pode passar a falhar por causa do cabeçalho ISX
    assert sql.count("ON DELETE CASCADE") >= 2 and "delete_referential_action = 0" in sql


def test_variaveis_de_ambiente_no_compose_e_no_example():
    compose = (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")
    example = (ROOT / ".env.dev.example").read_text(encoding="utf-8")
    for chave in ("DS_ENGINE", "DS_API_URL", "DS_API_USER", "DS_API_PASSWORD", "DS_API_VERIFY_SSL",
                  "DS_ISTOOL_HOME", "DS_ISTOOL_DOMAIN", "DS_ISTOOL_AUTHFILE"):
        assert f"{chave}:" in compose, chave
        assert f"{chave}=" in example, chave
    assert "DS_ISTOOL_TMP=/tmp" not in example and 'DS_ISTOOL_TMP:-/tmp' not in compose     # pasta privada, não /tmp
    assert "ds-api-amostra" in (ROOT / "docker-compose.dev.yaml").read_text(encoding="utf-8")
    amostra = (ROOT / "dev" / "sshd-amostra" / "10-amostra.sh").read_text(encoding="utf-8")
    assert "-password)" in amostra and "exit 9" in amostra                            # o java falso recusa senha na linha
