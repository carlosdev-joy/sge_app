FROM apache/airflow:2.11.2

# Copia os wheels para dentro da imagem (o diretório "wheels" precisa existir no mesmo nível do Dockerfile)
USER root
COPY wheels /wheels
RUN chown -R airflow:0 /wheels

# Utilitários nativos do SQL Server via repo apt da Microsoft (mesmo padrão
# do api/Dockerfile, que prova que o ambiente de build alcança o repositório):
#   - mssql-tools18 (bcp) → habilita o engine `bcp_native` do módulo Cópia de
#     Dados (dags/utils/bulk_copy.py): pipe `bcp queryout → bcp in` entre
#     servidores, C nas duas pontas — ordens de grandeza acima do streaming
#     Python por stream;
#   - msodbcsql18 → dependência do bcp e TAMBÉM habilita o fallback
#     pyodbc_fast_executemany (o driver ODBC 18 passa a existir no worker).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg2 unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] \
       https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 mssql-tools18 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV PATH="$PATH:/opt/mssql-tools18/bin"

# Instala como usuário airflow (Airflow não permite pip como root)
USER airflow
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl
