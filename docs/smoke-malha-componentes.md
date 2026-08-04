# Smoke de produção — Componentes de malha (F10–F15)

Roteiro **executável sem contexto**: qualquer pessoa com acesso de
desenvolvedor ao ORQUESTRA e leitura no SQL Server consegue rodar do zero.
Baseado nos cenários §14 do desenho (`docs/malha-componentes-desenho.md`).

**Regra de ouro:** todo o smoke acontece numa **malha de teste com pipelines de
teste** — nunca na malha de produção. Nada aqui exige parar nada.

## 0. Pré-requisitos

- Migrations **075 E 076** aplicadas (conferir por SELECT — o migrate descarta
  PRINT). ⚠️ **As duas**: o prompt da etapa 6c é padrão-NÃO, e quem já tinha a
  075 de um deploy anterior pode ter pulado a 076 — sem ela a FK da 067 recusa
  o marcador `#no:{id}` e **nenhum evento de nó nasce** (Notificação, Fim e o
  banner de conclusão ficam mudos para sempre, sem erro na tela):

  ```sql
  SELECT OBJECT_ID('dbo.etl_malha_no','U')     AS malha_no,     -- NOT NULL
         OBJECT_ID('dbo.etl_malha_aresta','U') AS malha_aresta, -- NOT NULL
         COL_LENGTH('dbo.etl_pipeline_dependencia','origem_no') AS origem_no,
         COL_LENGTH('dbo.etl_pipeline','agenda_no')             AS agenda_no,
         COL_LENGTH('dbo.etl_malha','agendamento_json')         AS agendamento;
  -- migration 076: a FK tem de ter SUMIDO (é o que libera o marcador #no:{id})
  SELECT COUNT(*) AS fk_ainda_existe          -- ⚠️ tem de vir 0
  FROM sys.foreign_keys
  WHERE name = 'FK_dep_evento_pipeline'
    AND parent_object_id = OBJECT_ID('dbo.etl_dependencia_evento');
  ```

  `fk_ainda_existe = 1` → **pare**: aplique a 076 antes de seguir (o passo 4
  falharia sem nenhuma mensagem de erro).

- 4 pipelines de teste **publicados** (DAG gerada) e baratos (ex.: um job
  `storedproc`/`http` inofensivo). Neste roteiro: `SMK_A`, `SMK_B`, `SMK_C`,
  `SMK_D`. Nenhum deles pode ter dependência prévia:

  ```sql
  SELECT pipeline_name, depends_on, dag_criada FROM dbo.etl_pipeline
  WHERE pipeline_name IN ('SMK_A','SMK_B','SMK_C','SMK_D');
  SELECT * FROM dbo.etl_pipeline_dependencia
  WHERE pipeline_name IN ('SMK_A','SMK_B','SMK_C','SMK_D')
     OR depende_de   IN ('SMK_A','SMK_B','SMK_C','SMK_D');   -- deve vir vazio
  ```

- Usuário com perfil desenvolvedor (montagem) e permissão **Executar**
  (disparo). A guardiã (`etl_dependencia_guardia`) ativa no Airflow.

## 1. Montagem (F10/F12) — desenhar é o teste

Na tela **Malha** ▸ criar a malha `SMOKE_COMPONENTES` ▸ abrir o diagrama ▸
adicionar `SMK_A`, `SMK_B`, `SMK_C`, `SMK_D` como membros. Depois, pela paleta
**Componentes**:

1. Arrastar **Início**, **Aguarde**, **Notificação** e **Fim** para o canvas.
2. Tentar arrastar um **segundo Início** → a paleta desabilita (e a API
   recusaria com 422). ✅
3. Ligar `Início → SMK_A` e `Início → SMK_B` (nenhuma confirmação de efeito
   composto ainda — sem agendamento configurado, o aviso manda configurar). ✅
4. Ligar `SMK_A → Aguarde` e `SMK_B → Aguarde`; depois `Aguarde → SMK_C` e
   `Aguarde → SMK_D`. **Cada gesto de saída mostra o modal com as dependências
   que serão criadas** (2×2 = 4 linhas no total). Confirmar. ✅
5. Ligar `Aguarde → Notificação`; usar **"prender as pontas soltas"** no banner
   para ligar `SMK_C`/`SMK_D` ao Fim. ✅
6. Recarregar a página: o desenho volta **idêntico** (round-trip). ✅

Prova no banco (as 4 linhas, **assinadas** pelo nó do Aguarde):

```sql
SELECT d.pipeline_name, d.depende_de, d.origem_no, n.tipo, n.malha_name
FROM dbo.etl_pipeline_dependencia d
JOIN dbo.etl_malha_no n ON n.id = d.origem_no
WHERE n.malha_name = 'SMOKE_COMPONENTES';
-- esperado: (SMK_C,SMK_A) (SMK_C,SMK_B) (SMK_D,SMK_A) (SMK_D,SMK_B)
SELECT pipeline_name, depends_on FROM dbo.etl_pipeline
WHERE pipeline_name IN ('SMK_C','SMK_D');   -- CSV espelhado: SMK_A,SMK_B
```

## 2. Proteção de linha assinada (F11, E3)

No modal de dependências do pipeline `SMK_C` (ou por outra malha que contenha
`SMK_A` e `SMK_C`): tentar **excluir** a dependência `SMK_C ← SMK_A` →
recusa **422 nomeando o Aguarde e a malha dona**; na malha dona a exclusão é
pelo desenho (aresta do nó). ✅

## 3. Início e agendamento (F13, E6/E7)

1. Duplo clique no **Início** ▸ configurar (ex.: diário 06:00, virada vazia)
   ▸ o modal lista as 2 raízes com `de → para`. Confirmar. ✅
2. Conferir a cópia campo a campo + assinatura + carimbo:

   ```sql
   SELECT pipeline_name, schedule_type, schedule_hour, schedule_minute,
          agenda_no, dag_config_pendente_em
   FROM dbo.etl_pipeline WHERE pipeline_name IN ('SMK_A','SMK_B');
   -- os DOIS idênticos, agenda_no = id do Início, carimbo preenchido
   ```

3. Republicar `SMK_A`–`SMK_D` (Pipelines ▸ Publicar nova versão). Os crons de
   `SMK_A`/`SMK_B` ficam idênticos; `SMK_C`/`SMK_D` ficam `schedule=None`
   (dependentes). ✅
4. Excluir a aresta `Início → SMK_B` → o modal avisa: `SMK_B` vira **sob
   demanda** (nunca o cron antigo de volta). Confirmar, conferir
   `schedule_type='on_demand'`, e **religar** a aresta + reaplicar o
   agendamento para o passo 4. ✅

## 4. Cenário-núcleo: disparo manual + cascata + observadores (F15/F14, E1/E9/E10)

1. Abrir a malha em **Execução** (data = hoje). Estado esperado antes de tudo:
   componentes **neutros/apagados**, "Sem execuções registradas nesta data". ✅
2. Clicar **▶ Disparar malha** → o modal lista `SMK_A` e `SMK_B` + a data de
   referência. Confirmar. ✅
3. Acompanhar (~1–3 min): `SMK_A` e `SMK_B` executam; ao terminar o último,
   `SMK_C` e `SMK_D` **partem sozinhos pelo push**, com a MESMA data:

   ```sql
   SELECT pipeline_name, data_referencia, status, disparado_por
   FROM dbo.etl_pipeline_execucao
   WHERE data_referencia = CAST(GETDATE() AS DATE)
     AND pipeline_name LIKE 'SMK_%' ORDER BY inicio;
   -- A e B: disparado_por = 'malha:SMOKE_COMPONENTES (SEU_USUARIO)'
   -- C e D: disparado_por = SMK_A ou SMK_B (o que fechou a conta)
   ```

4. No próximo ciclo da guardiã (≤5 min), os eventos dos nós:

   ```sql
   SELECT pipeline_name, tipo, data_referencia, detectado_em
   FROM dbo.etl_dependencia_evento
   WHERE pipeline_name LIKE '#no:%'
     AND data_referencia = CAST(GETDATE() AS DATE);
   -- 1× MALHA_NOTIFICACAO (nó da Notificação) + 1× MALHA_CONCLUIDA (nó do Fim)
   ```

5. Na tela (modo Execução, mesma data): **Aguarde satisfeito** (anel verde),
   **Notificação "emitida às HH:MM"**, **Fim "concluída às HH:MM"**, banner
   verde **"Malha concluída em … às …"**, e os dois eventos no painel da
   guardiã. ✅
6. Anti-duplicata: esperar 2+ ciclos da guardiã e repetir o SELECT do passo 4 —
   a contagem **não cresce** (chave idempotente). ✅

## 5. Anti-ruído (E11/E13)

1. Criar uma 2ª malha de teste com uma **Notificação sem entradas** → aviso
   forte no banner; após 1 ciclo da guardiã: **zero** evento desse nó. ✅
2. Malha incompleta na data corrente: **entre** os passos 4.2 e 4.3 — com
   `SMK_A` já em SUCESSO e `SMK_B` ainda executando — rode o SELECT do passo
   4.4: vem **vazio**. Nenhum evento de nó sai enquanto faltar um SUCESSO. ✅
   (a guardiã só avalia a data corrente e a anterior — conferir isso "amanhã"
   não prova nada, porque data futura nunca entra na janela).

## 5b. Republicar os pipelines da malha

O gesto que faz os vínculos desenhados valerem no Airflow. Exige a migration
**080** (`COL_LENGTH('dbo.etl_dag_pendente','modo_verificacao')` não-NULL) —
sem ela o botão publica, mas ninguém confere o desfecho.

1. Com a malha aberta em **Montagem**, ligar `SMK_B` a um Aguarde (ou desenhar
   qualquer aresta nova). O card do dependente ganha o chip âmbar
   **⟳ republicar** e o botão **Republicar pipelines** passa a exibir a
   contagem. ✅
2. O arquivo publicado ainda é o ANTIGO — provar antes de republicar:
   ```bash
   grep -n "schedule=" dags/generated/<projeto>/<dominio>/SMK_B.py
   ```
   (dependente publicado tem `schedule=None  # dependente: …`; se ainda mostra
   cron, é a versão anterior — é exatamente o que o botão resolve).
3. Clicar em **Republicar pipelines**: a janela lista os membros ATIVOS, marca
   com **primeira publicação** quem ainda não tem DAG no Airflow, com
   **desatualizada** quem tem carimbo, e mostra em *Fora desta publicação* os
   **inativos** com o motivo. Confirmar. ✅
4. Acompanhar em **Publicação**: o run tem escopo `Malha <NOME> (N pipeline(s))`
   e fecha **SUCCESS** com N geradas. Pendência de pipeline de **fora** da
   malha aparece como `aviso` — nunca reprova o run. ✅
5. Depois do run: o chip ⟳ some sozinho (a factory zera o carimbo) e o
   `grep` do passo 2 mostra a versão nova. ✅
6. Fila de conferência (deve haver uma linha por membro, em modo verificação,
   e **nenhuma** notificação "DAG … pronta no Airflow"):
   ```sql
   SELECT pipeline_name, status, modo_verificacao, tentativas
     FROM dbo.etl_dag_pendente
    WHERE dag_run_id LIKE 'orquestra_malha%'
    ORDER BY id DESC;
   ```
7. **Membro inativo**: inativar um pipeline da malha e republicar → ele sai em
   *Fora desta publicação* com o motivo, o run leva só os ativos e fecha
   SUCCESS. ✅

⚠️ **Ainda não reproduzido ao vivo** (coberto por teste unitário): DAG gerada
com erro de **carga** (NameError no import). O esperado é notificação de erro
severidade `error` apontando para /publicacao e o chip ⟳ **voltando a acender**
— o Airflow mantém a versão anterior ativa nesse caso, e o pior desfecho seria
a tela dizer "publicado e em dia".

## 6. Limpeza

```sql
-- A exclusão dos nós pela TELA descompila (remove as linhas assinadas).
-- Ordem: excluir os componentes no diagrama (cada um mostra o efeito),
-- depois remover os membros e INATIVAR a malha de teste (⚠️ não existe
-- "excluir malha" — nem na tela nem na API: o card oferece Renomear e
-- Inativar, e inativar já silencia os observadores, §12 do desenho).
```

Conferência final: os SELECTs do passo 1 voltam vazios para `SMK_%`;
`SMK_A`/`SMK_B` ficam como o time de teste os quer (sob demanda ou o
agendamento próprio, reaplicado à mão — a malha nunca devolve cron antigo).

| Se falhar | Onde olhar |
|---|---|
| Raiz não parte no disparo | resposta do endpoint lista o erro POR RAIZ (DAG não publicada? pausada?) |
| C/D não partem | log da task `dep_dependentes` da DAG do último pai; `SELECT` da 067 |
| Evento de nó não sai | **1º: a migration 076 foi aplicada?** (o SELECT do passo 0 — a FK barra o marcador em silêncio); depois o log da guardiã (`etl_dependencia_guardia`, task ciclo, responsabilidade 5) — upstream vazio e virada divergente PULAM com log |
| Tela neutra com dados no banco | GET `/malhas/{m}/execucao` — conferir `eventos_no[]`/`malha_concluida` no JSON |
