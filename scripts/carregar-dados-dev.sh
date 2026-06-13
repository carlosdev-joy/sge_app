#!/bin/bash
# =============================================================
# carregar-dados-dev.sh — Carrega um dump de dados (gerado por
# sql/dump_dados.py) no SQL Server do ambiente DEV.
#
# Uso:
#   bash scripts/carregar-dados-dev.sh dump_prod.sql
#   SA_PASS='...' DEV_DB='orquestra_dev' bash scripts/carregar-dados-dev.sh dump_prod.sql
#
# Variáveis (com defaults para o dev local):
#   SA_PASS      senha do sa            (default: lê de MSSQL_SA_PASSWORD do container)
#   DEV_DB       banco destino          (default: orquestra_dev)
#   SQL_CTR      container do SQL Server (default: orquestra-sqlserver-dev)
# =============================================================
set -euo pipefail

DUMP="${1:-dump_prod.sql}"
SQL_CTR="${SQL_CTR:-orquestra-sqlserver-dev}"
DEV_DB="${DEV_DB:-orquestra_dev}"

if [[ ! -f "$DUMP" ]]; then
  echo "ERRO: arquivo '$DUMP' não encontrado." >&2
  exit 1
fi

# Descobre a senha do SA a partir do próprio container, se não informada
if [[ -z "${SA_PASS:-}" ]]; then
  SA_PASS=$(docker inspect "$SQL_CTR" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep -E 'MSSQL_SA_PASSWORD|SA_PASSWORD' | head -1 | cut -d= -f2-)
fi

if [[ -z "$SA_PASS" ]]; then
  echo "ERRO: não foi possível determinar a senha do SA. Informe via SA_PASS=..." >&2
  exit 1
fi

echo "[CARGA] Copiando dump para o container $SQL_CTR..."
docker cp "$DUMP" "$SQL_CTR:/tmp/_carga.sql"

echo "[CARGA] Aplicando em $DEV_DB..."
docker exec "$SQL_CTR" /opt/mssql-tools18/bin/sqlcmd \
  -C -S localhost -U sa -P "$SA_PASS" -d "$DEV_DB" \
  -i /tmp/_carga.sql -b

docker exec "$SQL_CTR" rm -f /tmp/_carga.sql

echo "[CARGA] ✓ Dados carregados em $DEV_DB."
echo "[CARGA]   Recarregue a UI (Ctrl+Shift+R) para ver os dados de produção."
