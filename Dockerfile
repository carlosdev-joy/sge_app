FROM apache/airflow:2.11.2

# Copia os wheels para dentro da imagem (o diretório "wheels" precisa existir no mesmo nível do Dockerfile)
USER root
COPY wheels /wheels
RUN chown -R airflow:0 /wheels

# Instala como usuário airflow (Airflow não permite pip como root)
USER airflow
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl
