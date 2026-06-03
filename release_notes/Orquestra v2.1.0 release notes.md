# ORQUESTRA — Release Notes
## Versão 2.1.0 · Sprint 1 · Junho/2026

---

Olá time! 👋

Temos novidades no **ORQUESTRA**. Esta versão traz melhorias diretas no dia a dia de quem opera e migra pipelines do DataStage para o Airflow.

---

## ✨ O que há de novo

### ▶ Execução Manual de Pipelines
Agora você pode executar qualquer pipeline **fora do agendamento**, diretamente pelo ORQUESTRA — sem precisar acessar o Airflow.

- Na aba **Pipelines**, clique no botão **▶** ao lado do pipeline desejado
- Também disponível na aba **Jobs** — botão **▶ Executar agora** aparece após buscar os jobs de um pipeline
- Após o disparo, o ORQUESTRA abre automaticamente a execução no Airflow Grid para acompanhamento
- Ideal para re-execuções durante o dia ou testes após ajustes

---

### 🔁 Regenerar DAG automaticamente após alterações
Ao salvar qualquer alteração em um pipeline ou job, o ORQUESTRA pergunta automaticamente:

> *"Deseja regenerar a DAG no Airflow agora para aplicar as mudanças?"*

- Responda **Sim** e o processo de geração é disparado na hora
- Responda **Não** para regenerar depois pelo botão "↺ Regenerar" na tabela
- Evita o esquecimento de regenerar após edições

---

### ⏸ Ativar/Desativar pipeline reflete no Airflow
Ao ativar ou inativar um pipeline pelo ORQUESTRA, o status é sincronizado automaticamente com o Airflow:

- **Ativar** → DAG é despausada no Airflow ✓
- **Inativar** → DAG é pausada no Airflow ✓
- Não é mais necessário entrar no Airflow para pausar/despausar manualmente

---

### ⬆ Importar Sequence DataStage *(lançado neste ciclo)*
Importe uma sequence completa do DataStage com um único upload:

- Selecione o projeto → informe o nome da sequence → ORQUESTRA extrai automaticamente todos os jobs, a ordem de execução e a lineage
- Revisão antes de confirmar: edite nomes, ignore jobs desnecessários
- Ao aprovar, o pipeline é criado com todos os dados já preenchidos

---

### 👤 Nome do usuário no cabeçalho
O header agora exibe seu **primeiro nome** ao invés da matrícula, buscando automaticamente no AD da CVP após o login.

---

## 🐛 Correções incluídas

- Botão **+** da Governança voltou a exibir detalhes de tabelas/SQL corretamente
- Ao trocar de aba, o estado anterior é limpo (filtros, resultados)
- Lineage de jobs importados via sequence agora funciona no botão "Extrair do DSX"

---

## 📦 Como atualizar

Substituir o arquivo `ui/index.html` pelo novo disponibilizado nesta versão.

```
Tag: v2.1.0-sprint1
```

---

*Dúvidas ou sugestões? Fale com a Engenharia de Dados — CVT38571*
