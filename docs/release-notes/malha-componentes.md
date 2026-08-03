# 🧩 Componentes de malha — Início · Aguarde · Notificação · Fim

**Compatibilidade:** Apache Airflow 2.x | SQL Server
**Migrations:** **075 e 076** (deploy.sh etapa 6c — as DUAS são obrigatórias;
sem a 076 os eventos de nó não gravam e Notificação/Fim/banner nunca acendem)
**Desenho técnico:** `docs/malha-componentes-desenho.md` (F10–F15)
**Manual:** `docs/MANUAL_USUARIO.md` §3.6

---

## 📋 Resumo

A tela **Malha** ganhou quatro componentes de desenho que reproduzem a
"sequence mestre" do DataStage (ondas de sequences com Waits no meio) — sem
criar nenhum executor novo:

```
            ┌── Carga_Clientes ──┐                      ┌── Relatorio_A ──┐
▶ Início ──┤                     ├── ▮ Aguarde ────────┤                  ├── ⚑ Fim
            └── Carga_Contratos ─┘        │             └── Relatorio_B ──┘
                                          └── 🔔 Notificação ("cargas ok")
```

Os componentes são **açúcar de compilação** sobre os primitivos que já rodam em
produção: o Início vira colunas de agendamento nas raízes (mesmo cron, mesma
hora de virada — disparo em paralelo no mesmo tick do scheduler), o Aguarde
vira dependências reais na `etl_pipeline_dependencia` (expansão N×M, linhas
assinadas pelo nó), e Notificação/Fim viram eventos avaliados pela **guardiã**
(`MALHA_NOTIFICACAO` / `MALHA_CONCLUIDA`). Quem executa continua sendo o
scheduler + o disparo por dependência (push) — a malha desenha, o motor roda.

> **Impacto para engenheiros ETL:** a malha inteira se monta pela tela — ondas,
> esperas, aviso e conclusão — sem cadastrar dependência por dependência.
>
> **Impacto para a operação:** o modo Execução mostra a malha do dia com os
> componentes acesos/apagados, banner verde de conclusão e **disparo manual da
> malha** com confirmação (reprocesso e atraso deixam de ser disparo pipeline a
> pipeline).

---

## 🚚 Entregas por fase

| Fase | Entrega |
|---|---|
| **F10** | Modelo (migration 075: `etl_malha_no`, `etl_malha_aresta`, assinaturas `origem_no`/`agenda_no`, `agendamento_json`) + CRUD do desenho com a gramática validada |
| **F11** | Compilador do Aguarde: expansão N×M → linhas reais assinadas + espelho CSV + carimbo de republicação, com **dry_run** (o efeito é mostrado antes) e proteção de linha assinada em todas as portas |
| **F12** | Os quatro nós no canvas (paleta arrasta-para-criar, modal de efeito por gesto, banner de avisos, "prender as pontas soltas") |
| **F13** | Agendamento da malha no Início: um calendário por malha, copiado às raízes; desligar raiz vira `on_demand` (nunca cron antigo de volta) |
| **F14** | Guardiã avalia Notificação e Fim (janela {D, D−1}, idempotente, card do Fim opt-in); endpoint de execução devolve os eventos de nó. **Migration 076**: derruba `FK_dep_evento_pipeline` — sem ela o marcador `#no:{id}` do evento é recusado pela FK da 067 e nenhum evento de nó nasce |
| **F15** | Camada de execução dos componentes no modo Execução (Início raízes-na-data + próxima execução; Aguarde satisfeito/aguardando/bloqueado; Notificação/Fim acesos pelo evento do dia; banner verde de conclusão) + **disparo manual da malha** (raízes do Início com o mesmo ODATE via trigger REST; a cascata anda pelo push) + manual do usuário §3.6 |

---

## 🔒 O que NÃO muda

- `etl_dag_factory.py` **não foi tocado** — nenhuma DAG gerada muda de forma.
- O predicado de liberação (`liberado()`), o claim e o ciclo da guardiã seguem
  intocados; a política é uma só: **todas com sucesso na mesma data**.
- As portas de sempre (modal de dependências, aresta direta na malha, register)
  continuam funcionando — a malha só protege as linhas que **ela** compilou.
- Dependência continua **global** (uma fonte): o componente assina, não duplica.

## 🚀 Deploy

1. Migrations **075 e 076** na etapa 6c do `deploy.sh` (idempotentes;
   conferência por SELECT — `PRINT` é descartado pelo migrate). ⚠️ O prompt
   da 6c é **padrão-NÃO**: responder "não" com a 075 já aplicada de um deploy
   anterior deixa a **076 de fora**, e aí Notificação, Fim e o banner de
   conclusão **nunca acendem** (a FK da 067 barra o marcador `#no:{id}` em
   silêncio). O passo 0 do smoke prova as duas.
2. `api/` + front (F10–F13/F15) — sem regerar DAG nenhuma; o carimbo
   `dag_config_pendente_em` marca quem precisar de republicação.
3. `dags/` (F14 — guardiã); **sem force_all**.
4. Smoke: `docs/smoke-malha-componentes.md` (roteiro executável sem contexto),
   começando por uma malha de teste, nunca pela produção inteira.
