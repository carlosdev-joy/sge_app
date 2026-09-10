---
name: orquestra-grafia-pipeline-name
description: "Incidente da grafia dupla de pipeline_name (SQL CI × dict Python) — PR #236 + migration 069; ✅ EM PRODUÇÃO desde 2026-08-12; backlog: ramos de decisão case-sensitive e modo Lista opção B"
metadata: 
  node_type: memory
  type: project
  originSessionId: f83b731c-0876-4438-b369-1dd4f50c0621
  modified: 2026-08-13T02:40:55.950Z
---

Incidente do [[orquestra-sge-app]] (2026-08-01/02): pipeline registrado como
`SEQSSDVIDA6SINISTRO` com 6 etapas gravadas como `SeqSsdVida6Sinistro` (import
.dsx) + nó aguarde em maiúsculas (canvas). **A colação CI do SQL Server junta
as grafias; os dicts Python da factory não** → "pipeline sem nenhuma etapa —
nada a gerar" (e, antes da #234, o timeout mudo). Evidência: coluna Pipeline
da tela de Etapas mostrando as duas grafias.

✅ **PR #236 MERGEADA em 2026-08-02** (branch fix/geracao-grafia-e-pendentes):
factory agrupa etapas E params por chave CI (`_chave_ci`); pendência de OUTRO
pipeline vira aviso em run específico (a `sp_etl_pipelines_pendentes_criar` é
GLOBAL — um pendente vazio reprovava qualquer run, colateral da #234); alvo
fora do lote reprova com causa; dep inexistente → ValueError claro; dep com
caixa divergente resolve para a grafia real; API canoniza `pipeline_name` pela
grafia registrada (register, fluxo v2, aprovação .dsx — onde o incidente
nasceu); gerar-dag de pipeline inativo → 409. **Migration 069** normaliza as 3
tabelas de etapa (job/param/lineage), idempotente (BIN2 + DATALENGTH).
Validação: 1035 passed (+28), mesmas 5 falhas pré-existentes; revisão
adversarial aprovou com 2 defeitos que foram corrigidos na própria PR.

**Investigação (2 workflows adversariais) também provou:**
- A "recusa de save com on_demand" foi COINCIDÊNCIA — não existe caminho no
  código que recuse on_demand aceitando daily; o que o usuário via era o erro
  de geração da grafia. Pipeline pode voltar a Sob demanda após o deploy.
- O deploy de produção estava completo (aguarde persistido = API nova; mensagem
  da #234 = dags/ novo). O problema era só dado.

⚠️ **GOTCHAs novos:**
- A etapa **6c do deploy.sh é opt-in com default NÃO** (e sem terminal responde
  não) — migration esquecida se ninguém responder "s".
- O padrão perigoso é **junção cross-table por nome em dict Python** (job×
  pipeline, param×job): SQL junta CI, Python não. Ao criar junção nova por
  nome, usar `_chave_ci`.
- O modal de publicação (GenDagModal) NUNCA mostra erro da factory — só
  /publicacao mostra; num erro de geração ele termina em "Ainda registrando"
  ou num "pronto" falso de republicação.

✅ **DEPLOY FEITO em 2026-08-12** (migration 069 no trem —
[[orquestra-deploy-trem-producao]]). ⚠️ **Sem confirmação item a item** os
gestos manuais que o deploy não faz sozinho: regerar a DAG do
SEQSSDVIDA6SINISTRO, voltar o agendamento para Sob demanda + regerar de novo,
faxina dos pendentes vazios (query no rodapé da 069), e o smoke §8.1 do
[[orquestra-no-aguarde]] (passo 8 é o crítico). Perguntar antes de dá-los como
feitos.

📌 **BACKLOG:**
- Membros de ramo de decisão comparados case-sensitive
  (`dag_factory` ~l.744, `m in _job_names`): condition_json com caixa
  divergente perde a aresta EM SILÊNCIO — mesma classe do incidente, fora do
  diff da #236 porque toca a emissão dos ramos. Corrigir com o mapa
  `_job_real_ci` que a #236 introduziu.
- Modo Lista da tela de Etapas — avaliação feita, recomendação **opção B**
  (manter e corrigir): Ordem exibe "—" p/ nós especiais; banner + Ordem
  read-only quando o pipeline tem deps explícitas (exige expor flag no
  GET /jobs); Fluxo como default (metade já existe). NÃO remover: a Lista tem
  3 capacidades exclusivas (busca cross-pipeline, Colar lista em massa,
  reorder dos pipelines legados em modo ondas — onde execution_order É o
  grafo). Aguardando aprovação do usuário para virar spec/PR.
