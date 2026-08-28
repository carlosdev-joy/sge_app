"""A tela do Admin precisa conseguir gravar a PRIMEIRA senha do ServiceNow.

O backend (`servicenow_set`) trata string vazia como "mantenha a senha atual",
e isso está certo: impede que salvar o grupo ou o proxy apague a credencial sem
querer. O preço é que a tela precisa saber QUANDO mandar a senha de verdade.

Ela renderiza o botão "Trocar senha" só quando `tem_senha` é true. Num ambiente
recém-configurado esse botão não existe, então a flag `trocarSenha` nunca vira
true — e a senha digitada era substituída por '' no corpo do POST. O resultado
era o pior tipo de falha: `{"ok": true}`, toast de "Configuração salva", e o
`servicenow_senha_enc` continuando vazio no banco. Nada na tela dizia isso.
Sintoma reproduzido no ambiente dev em 2026-08-28.

⚠️ Um `grep` por `senhaParaEnviar` no `Admin.tsx` NÃO serviria: ficaria verde
com a chamada presente e a regra invertida. O que se afirma aqui é o VALOR que
sai da função em cada estado do formulário.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar — visível no
`-rs`, nunca silenciosa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "servicenow_senha_harness.cjs"
FONTE = RAIZ / "ui-react" / "src" / "lib" / "servicenowConfig.ts"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente)")
_MAJOR_MINIMO = 18


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= _MAJOR_MINIMO \
            else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def cenarios() -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def test_primeira_senha_e_enviada_sem_precisar_trocar(cenarios: dict) -> None:
    """O caso do defeito: banco sem senha, operador digita, tem que ir."""
    assert cenarios["primeira_senha_sem_trocar"] == "nova-senha", (
        "com o banco sem senha a tela precisa ENVIAR o que foi digitado — "
        "senão o save responde ok e não grava nada")


def test_campo_vazio_no_primeiro_cadastro_nao_inventa_valor(cenarios: dict) -> None:
    assert cenarios["primeira_senha_campo_vazio"] == ""


def test_senha_existente_nao_e_sobrescrita_ao_salvar_outro_campo(cenarios: dict) -> None:
    """Salvar grupo/proxy não pode apagar a credencial já gravada."""
    assert cenarios["senha_existente_sem_trocar"] == ""
    assert cenarios["senha_existente_campo_sujo"] == "", (
        "sem clicar em 'Trocar senha', resíduo no campo NÃO pode viajar")


def test_troca_deliberada_envia_a_nova_senha(cenarios: dict) -> None:
    assert cenarios["troca_deliberada"] == "outra-senha"


def test_a_regra_mora_em_funcao_propria_e_nao_inline_no_jsx() -> None:
    """Anti-drift: a decisão não pode voltar para dentro do JSX.

    Inline, ela volta a ser invisível — foi assim que o defeito nasceu e
    sobreviveu. O piso (`senhaParaEnviar` existir no fonte) evita que este
    teste passe verde depois de alguém renomear tudo.
    """
    assert FONTE.is_file(), "lib/servicenowConfig.ts sumiu"
    fonte = FONTE.read_text(encoding="utf-8")
    assert "export function senhaParaEnviar" in fonte

    admin = (RAIZ / "ui-react" / "src" / "pages" / "Admin.tsx").read_text(
        encoding="utf-8")
    assert "senhaParaEnviar(" in admin, "Admin.tsx deixou de usar a regra"
    assert "trocarSenha ? cfgForm.senha" not in admin, (
        "a condição antiga voltou para o JSX — é ela que ignora a primeira senha")
