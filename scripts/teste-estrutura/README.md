# Teste de estrutura — validação mínima do host

Página estática (sem dependências) para validar, no novo host
(`orquestra.caixavidaeprevidencia.intranet`), o mínimo de conectividade **antes**
de migrar o app inteiro:

1. o **servidor/nginx** responde neste host (DNS + nginx + `server_name`);
2. a **API Orquestra** via proxy `/orquestra/` (bate em `/orquestra/health`);
3. o **Airflow** via proxy `/api/v1/` (bate em `/api/v1/health`).

## Como usar

**Opção A — junto do nginx do app** (copiar para o web root do servidor novo):

```bash
# no servidor novo, com o nginx servindo /usr/share/nginx/html
cp index.html /usr/share/nginx/html/teste.html
# abrir no navegador:
#   http://orquestra.caixavidaeprevidencia.intranet/teste.html
```

**Opção B — nginx avulso só para o teste** (nem precisa do app):

```bash
docker run --rm -p 80:80 \
  -v "$(pwd)":/usr/share/nginx/html:ro \
  nginx:1.27
# abrir: http://orquestra.caixavidaeprevidencia.intranet/
```

## Como ler o resultado

- 🟢 **verde** = ok.
- 🟡 **amarelo** = alcançável (o serviço respondeu, mas com auth/rota — o **proxy
  funciona**). Para o Airflow, `HTTP 401/403/404` é esperado e conta como sucesso
  de conectividade.
- 🔴 **vermelho** = sem resposta (DNS/nginx/porta) ou serviço fora (`502/503/504`).

> Servindo só esta página (Opção B), o check **1** fica verde e os checks **2/3**
> ficam vermelhos — é o esperado enquanto a API e o Airflow não estão no ar.
> Conforme você sobe os serviços, os checks vão ficando verdes.
