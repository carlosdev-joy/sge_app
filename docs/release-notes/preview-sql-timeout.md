# Release note — Tempo da prévia/simulação de SQL (F2)

Spec: `docs/spec-email-tabela-sql-e-ajustes.md` · Fase F2

## O que muda

1. **O tempo de fábrica da prévia sobe de 15s para 60s** e o teto configurável de
   120s para **280s**.
2. **O campo que regula isso mudou de lugar**: saiu de *Acessos & Comunicação ›
   Notificações* (onde ficava no rodapé, depois dos canais do Teams) e passou a
   viver em **Sistema › Configurações**, no fim da página — ao lado do editor de
   parâmetros, que é onde se procura configuração.
3. **A mensagem de quem estoura o limite passa a dizer onde aumentar.** Antes
   mandava só "refine o SELECT". Vale também para a **simulação da decisão**, que
   antes nem isso dizia.
4. **Correções de bastidor que vieram junto** (ambas são o motivo de a fase não
   ser só "trocar dois números"):
   - a prévia e a simulação passaram a rodar o SQL **fora do event loop**
     (`asyncio.to_thread`). Os dois endpoints são `async def`, e o `execute` do
     pyodbc é bloqueante: com 2 workers uvicorn, duas prévias longas parariam a
     API inteira — login, dashboard e os laços de fundo. Com 15s o estrago era
     pequeno; com 280s deixaria de ser;
   - o **wizard de Cópia de Dados** usava o mesmo valor como timeout de **login**
     do pyodbc. Um servidor inalcançável penduraria a prévia por até 280s antes
     de rodar qualquer SQL. O login voltou a ter limite curto e fixo (5s), e o
     valor configurável ficou só para a execução.

## Como ajustar (sem deploy)

**Admin › Sistema › Configurações › Configurações de fluxo › "Timeout de
preview/simulação (s)"**. Vale na hora, para todo mundo. Cada prévia em andamento
ocupa um dos processos da API — subir para o teto com várias pessoas prevendo ao
mesmo tempo deixa o sistema mais lento.

A chave é `sql_preview_timeout_s` em `dbo.etl_app_config`. Ela também aparece
crua na tabela de parâmetros da mesma aba; prefira o campo, que recorta o valor
para a faixa 1..280 (a tabela genérica grava qualquer texto).

## ⚠️ Antes de subir para produção, confira duas coisas no servidor

1. **O corte do nginx de produção.** O teto de 280s foi escolhido para ficar
   abaixo do `proxy_read_timeout` de 300s do bloco `location /orquestra/`. O
   `config/nginx.conf` **de produção está à frente do repo** (no deploy, a
   resposta para `config/` é **n**), então o valor real precisa ser lido lá:

   ```bash
   docker exec airflow-ui grep -A 8 "location /orquestra/" /etc/nginx/nginx.conf
   ```

   Se o `proxy_read_timeout` de lá for **menor que 280s**, o teto precisa descer
   junto — senão quem estourar recebe o 504 mudo do proxy em vez da mensagem que
   explica o que houve. Se houver VIP/F5 na frente, o idle timeout dele vale pelo
   mesmo motivo.

2. **Se alguém já gravou um valor alto à mão.**

   ```sql
   SELECT config_key, config_value FROM dbo.etl_app_config
    WHERE config_key = 'sql_preview_timeout_s';
   ```

   Um valor acima de 120 (digamos 600) hoje é recortado para 120; **depois deste
   deploy passa a valer 280**, sem ninguém abrir a tela. Não se perde
   configuração, mas o comportamento muda sozinho — se não for o desejado,
   regrave pelo campo do Admin.

## Ordem do deploy

Só `api/` e `dist/`. **Sem migration** e **sem mexer em `dags/`** — o worker não
participa desta fase. Responder **n** para `config/`, como sempre.

## Conferência pós-deploy

a) Abrir **Admin › Sistema › Configurações** e ver a seção "Configurações de
   fluxo" no fim da página, com o campo aceitando até 280.
b) Abrir **Acessos & Comunicação › Notificações** e confirmar que a seção **não**
   está mais lá (a aba fica só com "Canais" e "Modelos de card").
c) Em ambiente que nunca configurou a chave, o campo deve mostrar **60**.
d) Salvar 280 e recarregar: o valor persiste, e a linha `sql_preview_timeout_s`
   da tabela de parâmetros acima mostra o mesmo número.
e) Num nó SQL, rodar a prévia de uma consulta que antes estourava em 15s — deve
   trazer a amostra.
f) Rodar uma consulta deliberadamente pesada até estourar: a mensagem precisa
   citar o tempo em vigor **e** o caminho `Admin › Sistema › Configurações`.
g) Repetir (f) na **simulação da decisão** (nó de Decisão › Simular): mesma
   mensagem.
h) Com uma prévia longa em andamento, abrir outra aba e navegar pelo sistema: a
   UI precisa continuar respondendo (é o que o `asyncio.to_thread` garante).
i) No wizard de **Cópia de Dados**, apontar para uma conexão com host
   inalcançável e clicar em Pré-visualizar: o erro precisa vir em poucos
   segundos, não depois de minutos.

## Reversão

Reverter `api/` e `dist/` para a versão anterior. O valor gravado em
`etl_app_config` **permanece**, e a versão antiga volta a recortá-lo em 120 —
nada a limpar. Quem estiver com o campo aberto na aba Configurações verá a seção
sumir dali e voltar para a aba de Notificações.
