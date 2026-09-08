"""Aba Utilitários › Enviar arquivo (F4 da spec docs/spec-utilitarios-transferencia.md) — o front.

  1. **Bancada renderizada** (`tests/js/utilitarios_enviar_harness.cjs`): o
     formulário, o modal e as libs rodam no React mínimo da casa e a bancada
     CLICA — escolher um arquivo preenche o nome; extensão fora da lista,
     arquivo acima do teto e pasta fora das raízes desligam o Enviar antes de
     qualquer XHR; Enter não envia; o modal passa por enviando (barra +
     Cancelar, que some quando o corpo já subiu inteiro) → existe/pronto/
     cancelado/erro; `enviarArquivo` monta o PUT cru com Authorization e
     traduz 409, 502 em HTML, 504 e o cancelamento. Sem Node ou sem
     `node_modules`, SALTA.
  2. **Anti-drift** por leitura do fonte, sem Node: a página tem as três abas,
     segura o `File` entre o 409 e o Sobrescrever, cancela pelo XHR em curso,
     usa o teto do config; o formulário não submete; o transporte é XHR cru
     com `application/octet-stream`; nenhuma permissão nova.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "utilitarios_enviar_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
SRC = RAIZ / "ui-react" / "src"
PAGINA = SRC / "pages" / "Utilitarios.tsx"
FORM = SRC / "components" / "utilitarios" / "FormEnviarArquivo.tsx"
MODAL = SRC / "components" / "utilitarios" / "ModalEnvioArquivo.tsx"
LIB_E = SRC / "lib" / "utilitariosEnvio.ts"
API = SRC / "lib" / "api.ts"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True, timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. funções puras ══════════════════════════════════════════════

def test_extensao_e_a_ultima_em_minusculas(cen):
    assert cen["puras"]["extensaoDe"] == ["txt", "gz", None, None, None, "b"]


def test_aviso_do_envio_antes_da_api(cen):
    a = cen["puras"]["avisoEnvio"]
    assert a["vazio"] is None and a["ok"] is None
    assert a["barra"] and "Sem caracteres de controle" in a["controle"]
    assert "invisíveis" in a["invisivel"] and "215" in a["longo"]
    assert "sem extensão" in a["semExt"]
    assert a["foraDaLista"] == "Extensão sh não está na lista do admin."   # compara em minúsculas
    assert a["dupla"] == "Extensão sh não está na lista do admin."         # só a última conta
    assert "acima do teto de 50,0 MB" in a["teto"] and a["noTeto"] is None
    assert a["semTamanho"] is None


def test_envio_pronto_e_url(cen):
    p = cen["puras"]["pronto"]
    assert p == {"ok": True, "semPermissao": False, "semArquivo": False, "fora": False, "extRuim": False, "semPasta": False}
    assert cen["puras"]["url"] == ("/utilitarios/arquivo/enviar?servidor=datastage&diretorio=%2Fdados%2Fbi"
                                   "&nome=Relat%C3%B3rio+%C3%A7%C3%A3o.TXT&sobrescrever=true")


def test_erro_do_envio_traduzido(cen):
    e = cen["puras"]["erro"]
    assert e["conflito"] == {"status": 409, "mensagem": "O arquivo já existe. Confirme para gravar por cima.",
                             "existente": {"tamanho_bytes": 10, "modificado_em": "2026-09-07 10:00:00"}}
    assert "API do Orquestra não respondeu" in e["htmlNginx502"]["mensagem"]   # 502 HTML do nginx: sem detail
    assert e["htmlNginx413"] == {"status": 413, "mensagem": "Arquivo acima do teto de envio."}
    assert e["api413"]["mensagem"].startswith("Arquivo de 60,0 MB")
    assert e["timeout504"]["status"] == 504 and "Confira na pasta antes de reenviar" in e["timeout504"]["mensagem"]
    assert "transferências em andamento" in e["ocupado503"]["mensagem"]
    assert "parou no meio" in e["parou408"]["mensagem"]
    assert e["rede"] == {"status": None, "mensagem": "Não foi possível falar com a API."}
    # Status fora do mapa com corpo em texto puro: a régua "<status> " cai na frase
    # genérica em vez de mostrar "599" cru (achado da revisão da F4).
    assert e["cru500"] == {"status": 500, "mensagem": "Falha na API do Orquestra — tente de novo em instantes."}
    assert e["cru599"] == {"status": 599, "mensagem": "Não foi possível falar com a API."}


def test_anuncio_ao_vivo_do_envio_so_em_marcos(cen):
    a = cen["puras"]["anuncio"]
    assert a[0] == "Enviando…" and a[1] == "Enviando…"           # sem progresso / 24 %
    assert a[2] == "Enviando… 50%"
    assert a[3] == "Enviado ao servidor; gravando… aguarde."
    assert a[4] == "O arquivo já existe." and a[5] == "Arquivo enviado."
    assert "confira na pasta" in a[6] and a[7] == "Não respondeu."


def test_resumo_chegou_inteiro_e_frases_do_cancelamento(cen):
    assert cen["puras"]["resumo"] == ["arquivo sobrescrito", "3,0 MB", "sha256 abcdef012345…", "cópia de segurança em /x.bak-1", "1,2 s"]
    assert cen["puras"]["chegouInteiro"] == [False, False, True, True]
    antes, chegou = cen["puras"]["cancelamento"]
    assert "nada foi gravado" in antes and "confira na pasta" in chegou


# ═══════════ 2. transporte ═════════════════════════════════════════════════

def test_put_cru_com_authorization_progresso_e_resultado(cen):
    ok = cen["transporte"]["ok"]
    assert ok["open"] == [["PUT", "/orquestra/utilitarios/arquivo/enviar?servidor=datastage&diretorio=%2Fdados%2Fbi&nome=Relatorio.TXT&sobrescrever=false"]]
    assert ["Content-Type", "application/octet-stream"] in ok["headers"] and ["Authorization", "Bearer tok"] in ok["headers"]
    assert ok["enviouBlob"] is True and ok["progresso"] == [[5, 15], [15, 15]]
    assert ok["resultado"]["caminho"] == "/dados/bi/Relatorio.TXT" and ok["erro"] is None
    assert cen["transporte"]["semToken"]["headers"] == [["Content-Type", "application/octet-stream"]]


def test_erros_do_transporte(cen):
    t = cen["transporte"]
    assert t["conflito"]["erro"]["status"] == 409 and t["conflito"]["erro"]["detail"]["existente"]["tamanho_bytes"] == 10
    assert t["html502"]["erro"] == {"status": 502, "detail": None, "message": "502 ", "cancelado": False}   # HTML não vira detail; "<status> " é a régua
    assert t["api504"]["erro"]["status"] == 504 and t["api504"]["erro"]["detail"] == "O servidor não respondeu em 240 s."
    assert t["rede"]["erro"]["status"] is None and t["rede"]["erro"]["cancelado"] is False
    c = t["cancelado"]
    assert c["abort"] == 1 and c["erro"]["cancelado"] is True and c["progresso"] == [[5, 15]] and c["resultado"] is None
    e = t["expirou"]
    assert e["expirou"] == 1 and e["erro"]["status"] == 401
    assert t["texto500"]["erro"] == {"status": 500, "detail": None, "message": "500 ", "cancelado": False}


# ═══════════ 3. formulário ═════════════════════════════════════════════════

def test_escolher_arquivo_preenche_o_nome_e_liga_com_pasta(cen):
    f = cen["form"]
    assert f["inicio"]["enviar"] is True and f["inicio"]["escolhido"] == "" and "nenhum arquivo" in f["inicio"]["texto"]
    assert f["inicio"]["seletorTipo"] == "file" and f["inicio"]["seletorSrOnly"] is True
    assert f["inicio"]["todosTypeButton"] is True and f["inicio"]["teto"] is True
    assert f["escolheu"] == {"nome": "Relatorio.TXT", "texto": "Relatorio.TXT · 2,9 KB", "enviar": True}   # ainda sem pasta
    assert f["comPasta"] == {"enviar": False}


def test_avisos_desligam_o_enviar_antes_do_xhr_e_enter_nao_envia(cen):
    f = cen["form"]
    assert f["enterNoCampo"] == 0
    assert f["extRuim"] == {"enviar": True, "aviso": True}
    assert f["semExt"] == {"enviar": True, "aviso": True}
    assert f["fora"] == {"enviar": True, "aviso": True}
    assert f["teto"] == {"nome": "grande.txt", "enviar": True, "aviso": True}
    assert f["tetoNaoEnviou"] == 1                                  # o clique no botão desligado não passou do cinto


def test_enviar_manda_o_pedido_e_o_arquivo(cen):
    assert cen["form"]["enviou"] == [[{"servidor": "datastage", "diretorio": "/dados/bi/2026", "nome": "Relatorio.TXT", "sobrescrever": False}, "Relatorio.TXT"]]


def test_enviando_sem_permissao_e_sem_extensoes(cen):
    assert cen["formEnviando"] == {"enviar": True, "escolher": True, "loading": True}
    assert cen["formSemPermissao"] == {"aviso": ["sem-permissao"], "enviar": True, "escolher": True, "seletor": True}
    assert cen["formSemExtensoes"] == {"aviso": ["sem-extensoes"], "enviar": True}


# ═══════════ 4. modal ══════════════════════════════════════════════════════

def test_modal_enviando_com_barra_e_cancelar_que_some_quando_o_corpo_subiu(cen):
    m = cen["modal"]
    e = m["enviando"]
    assert e["caminho"] == "/dados/bi/Relatorio.TXT" and e["frase"] == "Enviando… 5 B de 15 B"
    assert e["valuenow"] == 33 and e["preenchido"] == "33"
    assert e["cancelar"] == 1 and e["fechar"] == 0 and e["cancelou"] == 1 and e["todosTypeButton"] is True
    assert e["fecharCancela"] == 3 and e["anuncio"] == "Enviando… 25%"      # X e backdrop cancelam enquanto sobe
    s = m["subiuTudo"]
    assert s["frase"].startswith("Enviado ao servidor; gravando…") and "até 4 min" in s["frase"]
    assert s["cancelar"] == 0 and s["preenchido"] == "100"
    assert s["anuncio"] == "Enviado ao servidor; gravando… aguarde."
    # Depois que o corpo subiu, X/backdrop/Esc NÃO abortam nem fecham: o servidor
    # vai gravar de qualquer forma e o resultado não pode se perder (achado médio).
    assert s["fecharNaoFaz"] == {"cancelar": 0, "fechar": 0}
    assert m["semProgresso"] == {"frase": "Enviando…", "preenchido": "indeterminado"}
    assert m["liveSempre"] is True                                          # região viva sr-only em todo estado


def test_modal_cancelado_existe_pronto_erro(cen):
    m = cen["modal"]
    ca = m["canceladoAntes"]
    assert {k: ca[k] for k in ("atributo", "frase", "fechar", "cancelar", "fechou")} == \
        {"atributo": "antes", "frase": True, "fechar": 1, "cancelar": 0, "fechou": 1}
    assert m["canceladoChegou"] == {"atributo": "chegou", "frase": True}
    assert m["existe"] == {"mensagem": True, "tamanho": True, "data": True, "fechar": 0, "todosTypeButton": True,
                           "sobrescreveu": 1, "cancelouFecha": 1}
    assert m["pronto"]["caminho"] == "/dados/bi/Relatorio.TXT" and m["pronto"]["fechar"] == 1
    assert "arquivo criado" in m["pronto"]["resumo"] and "3,0 MB" in m["pronto"]["resumo"]
    assert m["pronto"]["fechouPeloBackdrop"] == 1 and m["pronto"]["anuncio"] == "Arquivo enviado."
    assert m["canceladoAntes"]["anuncio"].startswith("Envio cancelado antes")
    assert m["erro504"]["atributo"] == 504 and m["erro504"]["confira"] is True
    assert "Confira na pasta" in m["erro504"]["anuncio"]
    assert m["fechado"] == 0


# ═══════════ 5. anti-drift (sem Node) ══════════════════════════════════════

def _sem_comentarios(fonte: str) -> str:
    fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", linha) for linha in fonte.splitlines())


def test_pagina_tem_as_tres_abas_e_o_fluxo_do_envio():
    pagina = _sem_comentarios(PAGINA.read_text(encoding="utf-8"))
    assert "id: 'enviar'" in pagina and "label: 'Enviar arquivo'" in pagina
    assert "ABAS_LEMBRADAS.has(lembrada)" in pagina                       # a aba lembrada aceita 'enviar'
    assert "enviarArquivo(p, arquivo" in pagina and "serieE.current === minha" in pagina
    assert "enviar({ ...pedidoE, sobrescrever: true }, arquivoE)" in pagina, "o Sobrescrever reenvia o MESMO File"
    assert "envioRef.current.cancelar()" in pagina
    assert "envioChegouInteiro(progressoE)" in pagina, "a frase do cancelamento depende de o corpo já ter subido"
    assert "tetoKb={cfg.transferencia_max_kb ?? TETO_TRANSFERENCIA_KB_PADRAO}" in pagina
    assert "<ModalEnvioArquivo" in pagina and 'storageKey="utilitarios_ver_v4"' in pagina
    assert "if (enviandoE) return" in pagina                               # fechar não vale enquanto sobe
    assert "typeof r !== 'object'" in pagina, "2xx sem JSON não pode prender o modal em 'enviando'"
    assert "chega na F" not in pagina


def test_formulario_nao_submete_e_o_seletor_e_acessivel():
    fonte = _sem_comentarios(FORM.read_text(encoding="utf-8"))
    assert "onSubmit={e => e.preventDefault()}" in fonte and 'type="submit"' not in fonte
    assert 'type="file"' in fonte and 'className="sr-only"' in fonte and "aria-label=" in fonte
    assert "sobrescrever: false" in fonte, "o primeiro envio nunca sobrescreve"
    assert "setDiretorio(p); setNome(n); nav.fechar()" in fonte, "escolher no navegador = ir por cima daquele nome"
    modal = _sem_comentarios(MODAL.read_text(encoding="utf-8"))
    for tag in re.findall(r"<Button\b[^>]*>", modal, flags=re.S):
        assert 'type="button"' in tag, tag[:80]
    assert "estado === 'enviando' ? (subiuTudo ? NADA : onCancelar) : onFechar" in modal, \
        "fechar enquanto sobe = cancelar; depois que subiu inteiro, fechar não aborta"
    assert 'aria-live="polite" className="sr-only"' in modal


def test_transporte_e_xhr_cru_com_a_sessao_da_api():
    lib = _sem_comentarios(LIB_E.read_text(encoding="utf-8"))
    assert "new XMLHttpRequest()" in lib and "'application/octet-stream'" in lib
    assert "xhr.open('PUT'" in lib and "expirarSessao" in lib and "xhr.upload.onprogress" in lib
    assert "FormData" not in lib, "o contrato da F3 é corpo cru, sem multipart"
    api = _sem_comentarios(API.read_text(encoding="utf-8"))
    assert "export function expirarSessao" in api and api.count("orquestra_token") == 2


def test_nenhuma_permissao_nova():
    for arquivo in SRC.rglob("*.ts*"):
        assert "acao_upload" not in arquivo.read_text(encoding="utf-8"), arquivo
    # a F4 da transferência não traz migration (a 106 é de outra spec: lineage ISX)
    migrations = (RAIZ / "sql" / "migrations").glob("*.sql")
    assert not [m.name for m in migrations if any(p in m.name.lower() for p in ("transfer", "enviar", "baixar", "upload", "download"))]
