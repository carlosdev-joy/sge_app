"""api/services/conn_crypto.py — criptografia das senhas de dbo.etl_conexao.

Fernet (AES-128-CBC + HMAC-SHA256, da lib `cryptography` — já presente como
dependência do paramiko). A chave vem de ORQUESTRA_CONN_KEY e PRECISA ser a
mesma no orquestra-api e nos containers do Airflow (worker decifra ao resolver
a conexão em dags/utils/conn_resolver.py).

Gerar a chave (uma vez, no .env do host):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import os

from fastapi import HTTPException

_ENV_KEY = "ORQUESTRA_CONN_KEY"


def _fernet():
    from cryptography.fernet import Fernet  # import tardio — mensagem clara abaixo
    key = (os.getenv(_ENV_KEY) or "").strip()
    if not key:
        raise HTTPException(
            status_code=500,
            detail=(f"{_ENV_KEY} não configurada — gere com "
                    "python -c \"from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())\" e defina o MESMO "
                    "valor no orquestra-api e nos containers do Airflow"))
    try:
        return Fernet(key.encode())
    except Exception:
        raise HTTPException(status_code=500,
                            detail=f"{_ENV_KEY} inválida — precisa ser uma chave Fernet")


def encrypt_password(plain: str) -> str:
    """Senha em texto → token Fernet (base64 ASCII, cabe em VARCHAR(2000))."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_password(token: str) -> str:
    """Token Fernet → senha em texto. O chamador NUNCA deve logar o retorno."""
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(str(token).encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise HTTPException(
            status_code=500,
            detail=("Senha cifrada ilegível — a ORQUESTRA_CONN_KEY atual não "
                    "corresponde à chave usada ao salvar a conexão. Redefina a "
                    "senha da conexão ou restaure a chave original."))
