# ORQUESTRA — Manual de Utilização por Perfil

> Versão do produto: v2.3.0 · Acesso: `http://<servidor>` na rede corporativa
> Login: **matrícula e senha de rede** (as mesmas do Airflow). Sem acesso? Solicite ao administrador.

---

## Perfis de acesso

| Perfil | Quem é | O que pode fazer |
|---|---|---|
| **Consulta** | Analistas, gestores, auditoria | Visualizar Dashboard, Logs, Malha, Governança (lineage/catálogo) e Monitor DataStage |
| **Operador** | Operação/Sustentação ETL | Tudo do Consulta + executar pipelines manualmente, reexecutar falhas, acompanhar SLA |
| **Desenvolvedor ETL** | Equipe de engenharia de dados | Tudo do Operador + cadastrar/editar pipelines, jobs, lineage, agendamentos, importar sequences DSX |
| **Administrador** | Responsável pela plataforma | Tudo + aba Admin: configurações, tipos de job, regenerar DAGs, excluir pipelines, calendários/blackout |

> **Nota técnica (versão atual):** o sistema hoje distingue tecnicamente apenas *Administrador* vs. *demais usuários*. Os perfis Consulta/Operador/Desenvolvedor são uma convenção de uso até a implantação do RBAC (ver roadmap em `AUDITORIA_TECNICA.md`). Este manual já está organizado pelos quatro perfis para não precisar ser reescrito.

---

## 1. Perfil Consulta

### 1.1 Dashboard (aba ⌂)
Visão geral da saúde da malha:
- **KPIs do topo**: execuções do período, taxa de sucesso, falhas, duração média.
- **Executando agora**: pipelines em andamento em tempo real.
- **Últimas falhas**: as 5 mais recentes — clique para ver o log.
- **Alertas de performance**: execuções acima de 3h/6h/12h.
- **Gantt**: linha do tempo das execuções do dia.

### 1.2 Logs (aba 🗒)
Histórico completo de execuções:
1. Filtre por projeto, pipeline, status ou período.
2. Alterne entre **modo agregado** (uma linha por execução do pipeline) e **modo detalhe** (uma linha por job).
3. Clique numa execução para abrir o log de cada job (saída completa, código de retorno, duração).

### 1.3 Malha (aba ⊞)
Mapa de todos os pipelines e suas cadeias de jobs:
- **Visão cards**: um card por pipeline com horário, criticidade e a cadeia de jobs (jobs lado a lado = executam **em paralelo**; setas = ordem sequencial).
- **Visão diagrama**: fluxo visual da malha.
- **Filtros**: busca por nome/projeto, criticidade, status.
- **Exportar**: botão de exportação gera planilha (Excel/CSV) com a malha completa — útil para reuniões e auditoria.

### 1.4 Governança (aba ⚖)
- **Lineage**: para cada job, veja origens → transformação → destinos (tabelas, arquivos, colunas).
- **Catálogo**: busque qualquer tabela/arquivo, veja quais pipelines o produzem/consomem, classificação (PII, Confidencial...), dono (owner/steward) e tags.

### 1.5 Monitor DataStage (aba 🖥)
Fila e desempenho dos jobs DataStage: tempo em fila, duração, jobs filhos, histórico.

---

## 2. Perfil Operador

Tudo do Consulta, mais:

### 2.1 Executar um pipeline manualmente
1. Aba **Pipelines** → localize o pipeline (busca/filtros).
2. Clique em **▶ Executar agora**.
3. Acompanhe na aba Logs ou no Dashboard ("Executando agora").
> Execuções manuais **ignoram** calendário, blackout e filtro de horários — rodam imediatamente.

### 2.2 Reexecutar uma falha
1. Aba **Logs** → localize a execução com status `FAILED`.
2. Abra o detalhe, analise o log do job que falhou.
3. Use **Reexecutar** para disparar nova execução.

### 2.3 Alertas de SLA (Teams)
O monitor de SLA roda a cada 5 minutos e envia card no canal do Teams quando:
- **RISCO**: execução já consumiu ≥ 80% do SLA definido.
- **ESTOURO**: SLA ultrapassado.
Cada alerta é enviado uma única vez por execução (sem spam).

### 2.4 Janelas de blackout
Na aba **Pipelines → Agendamento**, consulte as janelas de blackout cadastradas (períodos em que execuções agendadas são suprimidas — ex.: fechamento contábil, manutenção de infra).

---

## 3. Perfil Desenvolvedor ETL

Tudo do Operador, mais:

### 3.1 Cadastrar um pipeline (wizard)
Aba **Pipelines → + Novo pipeline**. O wizard tem etapas:
1. **Identificação**: nome (padrão do projeto), projeto, domínio, descrição, tags.
2. **Classificação**: criticidade, SLA em minutos, ambiente, runbook.
3. **Agendamento** — tipos disponíveis:
   - **Diário** (hora:minuto), **Semanal** (dias da semana), **Mensal** (dia do mês), **De hora em hora**;
   - **Quinzenal**: escolha um dia de 1 a 15 — roda no dia D e no dia D+15 de cada mês;
   - **Horários específicos**: lista de horários exatos (ex.: 09:00, 10:30, 13:00...) + dias da semana (ex.: seg–sex). Ideal para cargas intradiárias;
   - Opções: **somente dias úteis**, **calendário** (feriados), **trigger por dependência** (dispara quando o pipeline antecessor termina).
4. **Execução**: retries, retry delay, max active runs, pool.
5. **Jobs**: adicione os jobs com **ordem de execução**. Jobs com a **mesma ordem executam em paralelo**; a ordem seguinte só inicia quando todos da anterior terminam. Na edição, os jobs já cadastrados são carregados automaticamente. Remover uma linha aqui **não exclui** o job do banco — exclusão definitiva só na tela Jobs.
6. **Lineage** (opcional aqui; obrigatório se cadastrar pela tela Jobs).
7. **Revisão** → salvar. Depois clique em **Gerar DAG** para publicar no Airflow.

### 3.2 Gerenciar jobs (aba ⚙ Jobs)
- Cadastro/edição completa: tipo (`datastage`, `shell`, `python`, `storedproc`), comando, conexão SSH.
- **Reordenar** por arrastar-e-soltar.
- **Lineage obrigatório**: pelo menos 1 origem e 1 destino por job.
- **Extrair lineage do DSX**: para jobs DataStage, importe o `.dsx` e o sistema extrai origens/destinos automaticamente.

### 3.3 Importar sequence DataStage (.dsx)
Aba Pipelines → **Importar sequence**: faça upload do `.dsx`, revise o rascunho gerado (pipeline + jobs + ordem), ajuste e aprove. O ORQUESTRA cria tudo de uma vez.

### 3.4 Dependência entre pipelines
Marque **trigger por dependência** e informe o pipeline antecessor: o ORQUESTRA usa Datasets do Airflow — quando o antecessor conclui com sucesso, o dependente dispara automaticamente.

---

## 4. Perfil Administrador

Tudo dos demais, mais a aba **Admin** (visível apenas para administradores):

### 4.1 Configurações da aplicação
Chave/valor em `etl_app_config` (ex.: URL do webhook Teams, parâmetros de monitor). Alterações valem sem redeploy.

### 4.2 Tipos de job
CRUD dos tipos de job aceitos no cadastro (nome, descrição, lineage habilitado, status).

### 4.3 Manutenção de DAGs
- **Regenerar todos os DAGs**: reconstrói os arquivos em `dags/generated/` a partir do banco (use após migrations ou correções no factory).
- **Excluir pipeline**: remove pipeline + jobs + DAG gerado. **Irreversível** — confira duas vezes.

### 4.4 Calendários e blackout
- **Calendários** (ex.: feriados nacionais/ANBIMA): cadastre datas; pipelines vinculados não rodam nessas datas.
- **Blackout**: janelas início/fim em que execuções agendadas são suprimidas globalmente ou por pipeline.

### 4.5 Rotina de deploy (servidor air-gapped)
```bash
cd /opt/airflow && git pull
# se houver migration nova:
sqlcmd -S SQL14 -d DMDB41 -i sql/migrations/0XX_*.sql
docker compose build orquestra-api && docker compose up -d --no-deps orquestra-api
docker compose restart ui-nginx
# se o factory mudou: Admin → Regenerar todos os DAGs
```
Lembretes:
- Segredos só em `/opt/airflow/.env` (nunca no Git).
- Dependências novas chegam via Git (`wheels/`), nunca via pip/internet no servidor.

---

## 5. Perguntas frequentes

**O pipeline não rodou no horário. Por quê?** Verifique, nesta ordem: (1) pipeline ativo? (2) data está num calendário de feriado ou blackout? (3) tipo "horários específicos": o horário consta na lista? (4) DAG gerado/atualizado após a última edição? (5) DAG despausado no Airflow?

**Editei o pipeline e nada mudou.** Edições de agendamento exigem **Gerar DAG** novamente.

**Jobs em paralelo não rodam juntos.** Confirme que têm exatamente a mesma ordem de execução e que há workers Celery disponíveis.

**Execução manual rodou em feriado.** Comportamento esperado: execuções manuais ignoram calendário/blackout/horários.

**Não vejo a aba Admin.** Seu usuário não é administrador — solicite ao responsável pela plataforma.
