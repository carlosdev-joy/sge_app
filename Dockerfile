FROM apache/airflow:2.11.2

# Copia os wheels para dentro da imagem (o diretório "wheels" precisa existir no mesmo nível do Dockerfile)
USER root
COPY wheels /wheels
RUN chown -R airflow:0 /wheels

# Utilitários nativos do SQL Server — pacotes .deb VENDORADOS em docker/debs
# (build 100% offline, sem acesso a repositório externo — mesmo padrão dos
# wheels Python; fontes e instruções de atualização em docker/debs/README.md):
#   - mssql-tools18 (bcp) → habilita o engine `bcp_native` do módulo Cópia de
#     Dados (dags/utils/bulk_copy.py): pipe `bcp queryout → bcp in` entre
#     servidores, C nas duas pontas — ordens de grandeza acima do streaming
#     Python por stream;
#   - msodbcsql18 → dependência do bcp e TAMBÉM habilita o fallback
#     pyodbc_fast_executemany (o driver ODBC 18 passa a existir no worker).
COPY docker/debs/*.deb /tmp/debs/
RUN ACCEPT_EULA=Y dpkg -i /tmp/debs/*.deb && rm -rf /tmp/debs
ENV PATH="$PATH:/opt/mssql-tools18/bin"

# Instala como usuário airflow (Airflow não permite pip como root)
USER airflow
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl
