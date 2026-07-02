# Pacotes .deb vendorados — mssql-tools18 (bcp) + driver ODBC

Instalados pelo `Dockerfile` (imagem Airflow) **sem acesso à internet** durante o
build — mesmo padrão offline dos wheels Python. Habilitam o engine `bcp_native`
do módulo Cópia de Dados e o driver ODBC 18 (fallback `pyodbc_fast_executemany`).

Alvo: Debian 12 (bookworm) amd64 — base da imagem `apache/airflow:2.11.2`.

| Pacote | Origem |
|---|---|
| `msodbcsql18`, `mssql-tools18` | https://packages.microsoft.com/debian/12/prod/pool/main/m/ |
| `unixodbc`, `unixodbc-common`, `libodbc2`, `libodbcinst2`, `odbcinst` | http://deb.debian.org/debian/pool/main/u/unixodbc/ |

Para atualizar: baixar as versões novas (mesma arquitetura/distro) das URLs acima,
substituir os arquivos e validar com um `docker build` (o RUN do Dockerfile falha
se faltar dependência). A EULA da Microsoft é aceita via `ACCEPT_EULA=Y` no build.
