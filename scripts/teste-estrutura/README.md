# Teste de estrutura — validação mínima do host

Página estática (sem dependências) para validar, no novo host
(`orquestra.caixavidaeprevidencia.intranet`), o mínimo de conectividade:

1. o **servidor/nginx** responde neste host (DNS + nginx + `server_name`);
2. a **API Orquestra** via proxy `/orquestra/` (bate em `/orquestra/health`);
3. o **Airflow** via proxy `/api/v1/` (bate em `/api/v1/health`).

## Já vem no deploy (automático)

A mesma página é incluída no build do front (`ui-react/public/teste.html` →
`ui-react/dist/teste.html`), então **depois de subir o app ela já está disponível
automaticamente** em:

```
http://orquestra.caixavidaeprevidencia.intranet/teste.html
```

Sem passo manual — o nginx do app serve o arquivo direto. Use essa URL como
health-check de conectividade em qualquer host onde o app rodar.

## Uso avulso (antes de o app existir)

Esta pasta (`scripts/teste-estrutura/`) serve para testar a estrutura **antes**
de subir o app inteiro, com um nginx avulso:

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
