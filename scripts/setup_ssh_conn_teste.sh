#!/usr/bin/env bash
# =============================================================================
# setup_ssh_conn_teste.sh
# Cria a conexão SSH de teste no Airflow via CLI
#
# Uso:
#   SSH_HOST=servidor.exemplo.com \
#   SSH_USER=airflow_user \
#   SSH_KEY_PATH=/path/to/private_key \
#   bash setup_ssh_conn_teste.sh
#
# Ou, se preferir senha:
#   SSH_HOST=servidor.exemplo.com SSH_USER=usuario SSH_PASS=senha bash setup_ssh_conn_teste.sh
# =============================================================================
set -euo pipefail

SSH_CONN_ID="${SSH_CONN_ID:-ssh_teste_dev}"
SSH_HOST="${SSH_HOST:?Informe SSH_HOST=hostname_do_servidor}"
SSH_USER="${SSH_USER:?Informe SSH_USER=usuario_ssh}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"
SSH_PASS="${SSH_PASS:-}"

CONTAINER="${AIRFLOW_SCHEDULER_CONTAINER:-orquestra-airflow-scheduler}"

echo "=== Criando conexão SSH no Airflow ==="
echo "  Conn ID : $SSH_CONN_ID"
echo "  Host    : $SSH_HOST"
echo "  User    : $SSH_USER"
echo "  Port    : $SSH_PORT"
echo ""

# Remove se já existir (garante idempotência)
docker exec "$CONTAINER" airflow connections delete "$SSH_CONN_ID" 2>/dev/null || true

if [ -n "$SSH_KEY_PATH" ]; then
    # Autenticação por chave privada
    PRIVATE_KEY=$(cat "$SSH_KEY_PATH")
    docker exec "$CONTAINER" airflow connections add "$SSH_CONN_ID" \
        --conn-type ssh \
        --conn-host "$SSH_HOST" \
        --conn-login "$SSH_USER" \
        --conn-port "$SSH_PORT" \
        --conn-extra "{\"private_key\": $(echo "$PRIVATE_KEY" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}"
else
    # Autenticação por senha
    docker exec "$CONTAINER" airflow connections add "$SSH_CONN_ID" \
        --conn-type ssh \
        --conn-host "$SSH_HOST" \
        --conn-login "$SSH_USER" \
        --conn-port "$SSH_PORT" \
        --conn-password "${SSH_PASS:-}"
fi

echo ""
echo "=== Verificando conexão criada ==="
docker exec "$CONTAINER" airflow connections get "$SSH_CONN_ID"

echo ""
echo "=== ATENÇÃO ==="
echo "O factory usa SSH_CONN_ID = 'ssh_lnxprd021' nos DAGs gerados."
echo "Para usar '$SSH_CONN_ID' nos testes, execute o SQL abaixo NO BANCO:"
echo ""
echo "  UPDATE dbo.etl_pipeline"
echo "  SET    dag_criada = 0"
echo "  WHERE  pipeline_name = 'ORQUESTRA_TESTE_SHELL';"
echo ""
echo "Depois regenere o DAG na UI e edite SSH_CONN_ID no arquivo gerado,"
echo "OU altere temporariamente a constante no etl_dag_factory.py:"
echo "  SSH_CONN_ID = \"$SSH_CONN_ID\""
