"""Download nos Utilitários — o front (F2 da spec docs/spec-utilitarios-transferencia.md).

  1. **Bancada renderizada** (`tests/js/utilitarios_transferencia_harness.cjs`):
     modal de conteúdo, navegador de pastas, faixa de transferência e as libs
     `utilitariosTransferencia`/`utilitariosDownload` rodam no React mínimo da
     casa e a bancada CLICA — Baixar ao lado de Copiar e como saída do 415/413
     (não do 403); no navegador só em arquivo e só com `onBaixar`, sem
     escolher nem fechar; a faixa passa por conectando → progresso →
     pronto/erro com `aria-live` sempre presente; `baixarArquivo` conta bytes
     contra o Content-Length e recusa download pela metade. Sem Node ou sem
     `node_modules`, SALTA.
  2. **Anti-drift** por leitura do fonte, sem Node: `apiFetch` continua JSON
     por cima de `apiFetchBruto` (que não injeta Content-Type); o download
     passa pela `apiFetchBruto` (o token vive no localStorage — `<a href>`
     direto chegaria sem Authorization); a página é dona do download com
     número de série; todo botão novo é `type="button"`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "utilitarios_transferencia_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
SRC = RAIZ / "ui-react" / "src"
API = SRC / "lib" / "api.ts"
PAGINA = SRC / "pages" / "Utilitarios.tsx"
MODAL = SRC / "components" / "utilitarios" / "ModalConteudoArquivo.tsx"
NAVEGADOR = SRC / "components" / "utilitarios" / "NavegadorPastas.tsx"
BARRA = SRC / "components" / "utilitarios" / "BarraTransferencia.tsx"
LIB_T = SRC / "lib" / "utilitariosTransferencia.ts"
LIB_D = SRC / "lib" / "utilitariosDownload.ts"


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

def test_url_do_download_codifica_e_apara(cen):
    u = cen["puras"]["url"]
    assert u[0] == "/utilitarios/arquivo/baixar?servidor=datastage&diretorio=%2Fdados%2Fbi%2F2026&nome=relat%C3%B3rio+%C3%A7%C3%A3o.txt"
    assert u[1] == "/utilitarios/arquivo/baixar?servidor=datastage&diretorio=%2Fdados%2Fbi&nome=a%2Bb%26c%25d.bin"


def test_nome_do_content_disposition(cen):
    n = cen["puras"]["nome"]
    assert n[0] == "relatório ção.txt"      # filename* vale antes do resgate ASCII
    assert n[1] == "carga.bin" and n[2] == "carga.bin"
    assert n[3] == "pedido.txt"             # sem cabeçalho: o nome pedido
    assert n[4] == "res.txt"                # percent inválido: cai no filename
    assert n[5] == "pedido.txt"


def test_progresso_percentual_e_quando_oferecer(cen):
    p = cen["puras"]
    assert p["progresso"] == ["1,5 KB de 40,0 MB", "512 B"]
    assert p["percentual"] == [0, 25, 100, None, 33]
    assert p["oferece"] == [True, True, False, False]
    assert p["emCurso"] == [False, True, True, False, False]


def test_erro_e_frases(cen):
    e = cen["puras"]["erro"]
    assert e[0] == {"status": 413, "mensagem": "Arquivo acima do teto de download."}
    assert e[1]["status"] == 503 and "transferências em andamento" in e[1]["mensagem"]
    assert "API do Orquestra não respondeu" in e[2]["mensagem"]
    assert e[3] == {"status": None, "mensagem": "Não foi possível falar com a API."}
    assert e[4]["status"] is None and "incompleto" in e[4]["mensagem"]
    f = cen["puras"]["frases"]
    assert f[0] == "Conectando ao servidor e lendo a.bin…"
    assert f[1] == "Baixando a.bin… 5 B de 15 B"
    assert f[2] == "Baixando a.bin… 5 B"
    assert f[3] == "Baixado a.bin (15 B)."
    assert f[4] == "Não foi possível baixar a.bin: acima do teto"


def test_anuncio_ao_vivo_so_em_marcos(cen):
    """A frase visível muda a cada bloco; o leitor de tela só ouve 25/50/75/100 %."""
    a = cen["puras"]["anuncio"]
    assert a[0] == ""
    assert a[1] == "Conectando ao servidor e lendo a.bin…"
    assert a[2] == "Baixando a.bin…" and a[3] == "Baixando a.bin…"     # 0 % e 24 %: sem número
    assert a[4] == "Baixando a.bin… 25%" and a[5] == "Baixando a.bin… 50%"
    assert a[6] == "Baixando a.bin… 100%"
    assert a[7] == "Baixando a.bin…"                                    # sem total: nunca um número
    assert a[8] == "Baixado a.bin (15 B)."
    assert a[9] == "Não foi possível baixar a.bin: acima do teto"


# ═══════════ 2. baixarArquivo ══════════════════════════════════════════════

def test_download_conta_bytes_entrega_o_blob_com_o_nome_do_cabecalho(cen):
    ok = cen["download"]["ok"]
    assert ok["urls"] == ["/utilitarios/arquivo/baixar?servidor=datastage&diretorio=%2Fdados%2Fbi&nome=imagem.bin"]
    assert ok["progresso"] == [[5, 15], [10, 15], [15, 15]]
    assert ok["entregues"] == [{"tamanho": 15, "nome": "imagem.bin"}]
    assert ok["bytes"] == list(range(1, 16))
    assert ok["resultado"] == {"nome": "imagem.bin", "total": 15, "sha256": "abc"}
    assert ok["erro"] is None


def test_download_pela_metade_e_recusado_sem_entregar(cen):
    i = cen["download"]["incompleto"]
    assert i["entregues"] == [] and i["resultado"] is None
    assert i["erro"]["status"] is None
    assert "incompleto (15 de 20 bytes)" in i["erro"]["detail"]


def test_download_sem_stream_sem_total_e_sem_cabecalho(cen):
    s = cen["download"]["semStream"]
    assert s["progresso"] == [[15, 15]] and s["entregues"] == [{"tamanho": 15, "nome": "imagem.bin"}]
    t = cen["download"]["semTotal"]
    assert t["progresso"] == [[5, None], [10, None], [15, None]]
    assert t["entregues"] == [{"tamanho": 15, "nome": "x.bin"}] and t["erro"] is None
    c = cen["download"]["semCabecalho"]
    assert c["entregues"] == [{"tamanho": 15, "nome": "imagem.bin"}]   # o nome PEDIDO, aparado
    v = cen["download"]["vazio"]
    assert v["entregues"] == [{"tamanho": 0, "nome": "imagem.bin"}] and v["erro"] is None


def test_erro_da_api_propaga_com_status_e_detail(cen):
    e = cen["download"]["erroApi"]
    assert e["entregues"] == [] and e["progresso"] == []
    assert e["erro"]["status"] == 413 and "acima do teto" in e["erro"]["detail"]


# ═══════════ 3. modal ══════════════════════════════════════════════════════

def test_modal_pronto_tem_baixar_ao_lado_de_copiar(cen):
    p = cen["modal"]["pronto"]
    assert p == {"botoes": 1, "type": "button", "desligado": False, "chamou": 1, "copiarAindaExiste": 1}
    assert cen["modal"]["prontoBaixando"] == {"desligado": True}
    assert cen["modal"]["prontoSemOnBaixar"] == {"botoes": 0}
    assert cen["modal"]["buscando"] == {"botoes": 0}


def test_modal_oferece_baixar_no_415_e_no_413_nao_no_403(cen):
    e415 = cen["modal"]["erro415"]
    assert e415["botoes"] == 1 and e415["type"] == "button" and e415["chamou"] == 1
    assert e415["formUltimas"] == 0 and "baixar o arquivo inteiro" in e415["texto"]
    e413 = cen["modal"]["erro413"]
    assert e413["botoes"] == 1 and e413["formUltimas"] == 1        # as duas saídas convivem
    assert e413["texto"].startswith("Ou baixe")
    assert cen["modal"]["erro403"] == {"botoes": 0, "saida": 0}
    assert cen["modal"]["erro415SemOnBaixar"] == {"botoes": 0}


# ═══════════ 4. navegador ══════════════════════════════════════════════════

def test_navegador_baixa_por_linha_sem_escolher_nem_fechar(cen):
    n = cen["navegador"]["comOnBaixar"]
    assert n["icones"] == 3
    assert n["quem"] == ["consulta.sql", "imagem.bin", "atalho.param"]   # arquivo e link→arquivo; pasta/link fora não
    assert n["todosTypeButton"] is True
    assert n["ariaLabel"] == "Baixar consulta.sql"
    assert n["chamadas"] == {"baixar": [["/dados/bi", "consulta.sql"], ["/dados/bi", "atalho.param"]],
                             "arquivo": [], "fechar": 0, "navegar": []}
    assert n["escolheu"] == [["/dados/bi", "consulta.sql"]]           # o botão principal continua escolhendo
    assert cen["navegador"]["baixando"] == {"desligados": True, "total": 3}
    assert cen["navegador"]["semOnBaixar"] == {"icones": 0}
    assert cen["navegador"]["nivelZero"] == {"icones": 0}


# ═══════════ 5. faixa ══════════════════════════════════════════════════════

def test_faixa_de_transferencia(cen):
    b = cen["barra"]
    n = b["nenhuma"]
    assert n["fase"] == "nenhuma" and n["painel"] == 0 and n["frase"] is None
    assert n["live"] == 1 and n["liveSrOnly"] is True and n["anuncio"] == ""   # a região viva existe SEMPRE
    c = b["conectando"]
    assert c["painel"] == 1 and c["frase"] == "Conectando ao servidor e lendo a.bin…"
    assert c["anuncio"] == "Conectando ao servidor e lendo a.bin…"
    assert c["barra"] is True and c["preenchido"] == "indeterminado" and c["fechar"] == 0
    d = b["baixando"]
    assert d["frase"] == "Baixando a.bin… 5 B de 15 B" and d["valuenow"] == 33 and d["preenchido"] == "33"
    assert d["anuncio"] == "Baixando a.bin… 25%"                                # o marco, não o bloco
    assert d["fechar"] == 0
    assert b["baixandoSemTotal"]["preenchido"] == "indeterminado"
    p = b["pronto"]
    assert p["frase"] == "Baixado a.bin (15 B)." and p["barra"] is False and p["fechar"] == 1 and p["fechou"] == 1
    e = b["erro"]
    assert e["fase"] == "erro" and "acima do teto" in e["frase"] and e["fechar"] == 1
    for v in b.values():
        assert v["todosTypeButton"] and v["live"] == 1 and v["roleStatus"] == 0
    # Os botões de Baixar vivem DENTRO de um Modal (z-50 + backdrop) que segue
    # aberto: a faixa tem de ficar acima dele e fora do trap de foco.
    for fase in ("conectando", "baixando", "pronto", "erro"):
        assert b[fase]["acimaDoModal"] is True and b[fase]["foraDoTrap"] is True, fase


# ═══════════ 6. anti-drift (sem Node) ══════════════════════════════════════

def _sem_comentarios(fonte: str) -> str:
    fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", linha) for linha in fonte.splitlines())


def test_api_fetch_continua_json_por_cima_do_bruto():
    api = _sem_comentarios(API.read_text(encoding="utf-8"))
    assert "export async function apiFetchBruto(path: string, opts?: RequestInit): Promise<Response>" in api
    bruto, json_ = api.split("export async function apiFetch<T>", 1)
    assert "Content-Type" not in bruto, "o bruto não pode fixar Content-Type (quebra multipart e download)"
    assert "'Content-Type': 'application/json'" in json_ and "apiFetchBruto(" in json_ and "res.json()" in json_
    # 401 e o shape do erro vivem UMA vez, no bruto.
    assert bruto.count("orquestra_token") == 2 and "err.status = res.status" in bruto
    assert "orquestra_token" not in json_


def test_download_passa_pela_api_bruta_e_revoga_a_url():
    lib = _sem_comentarios(LIB_D.read_text(encoding="utf-8"))
    assert "apiFetchBruto" in lib and not re.search(r"\bapiFetch\(", lib)
    assert "URL.createObjectURL" in lib and "URL.revokeObjectURL" in lib
    assert "a.download = nome" in lib
    assert "/utilitarios/arquivo/baixar" in _sem_comentarios(LIB_T.read_text(encoding="utf-8"))


def test_pagina_e_dona_do_download_com_numero_de_serie():
    pagina = _sem_comentarios(PAGINA.read_text(encoding="utf-8"))
    assert "baixarArquivo(p, " in pagina and "serieT.current === minha" in pagina
    assert pagina.count("onBaixar={baixar}") == 3          # os três formulários (navegador): ver, editar, enviar
    assert "onBaixar={baixarDoModal}" in pagina and "<BarraTransferencia" in pagina
    # O banner reaparece uma vez a cada novidade (v3 = download, v4 = envio); a chave só sobe.
    versao = re.search(r'storageKey="utilitarios_ver_v(\d+)"', pagina)
    assert versao and int(versao.group(1)) >= 3


def test_faixa_acima_do_modal_e_abaixo_do_toast():
    """A ordem de empilhamento é uma premissa entre três arquivos: se o Modal
    ou o Toast mudarem de camada, este teste avisa antes da tela."""
    modal = _sem_comentarios((SRC / "components" / "ui" / "Modal.tsx").read_text(encoding="utf-8"))
    toast = _sem_comentarios((SRC / "components" / "ui" / "Toast.tsx").read_text(encoding="utf-8"))
    barra = _sem_comentarios(BARRA.read_text(encoding="utf-8"))
    assert "z-50" in modal and "z-[100]" in toast
    assert "z-[60]" in barra and "data-modal-exempt" in barra
    assert 'role="status"' not in barra           # região viva dentro de região viva anuncia duas vezes
    navegador = _sem_comentarios(NAVEGADOR.read_text(encoding="utf-8"))
    assert re.search(r"\[aberto, carregando, listagem, baixando\]", navegador), \
        "o foco tem de voltar ao painel quando o ícone Baixar vira disabled"


def test_todo_botao_novo_e_type_button():
    for arquivo in (NAVEGADOR, BARRA):
        fonte = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
        for tag in re.findall(r"<button\b[^>]*>", fonte, flags=re.S):
            assert 'type="button"' in tag, f"{arquivo.name}: {tag[:60]}"
    modal = _sem_comentarios(MODAL.read_text(encoding="utf-8"))
    for tag in re.findall(r"<Button\b[^>]*data-acao=\"baixar[^>]*>", modal, flags=re.S):
        assert 'type="button"' in tag, tag[:80]
