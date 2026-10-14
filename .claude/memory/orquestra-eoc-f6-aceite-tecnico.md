---
name: EOC-F6 aceite técnico do Pipeline
description: Métricas, logs sob demanda, três perfis DEV e piloto humano pendente
type: project
---

Base develop98a77293/2.24.0. Codex desenvolve diretamente; Claude parado conforme decisão do usuário. Candidato2.24.1/migration176. Contrato/medidas/limites em docs/eoc-f6-aceite-pipeline.md, release correspondente. Pendências humanas/Caixa e benchmark antes de5s registradas no Backlog por176, não encerradas por testes técnicos. FonteAPI/.NET/DAGs inalterada; dist atualizado.

Why: orçamento de carga de Execução ultrapassou300KiB em114bytes; logs só precisam carregar ao abrir. Perfis personalizados exigem visibilidade por permissão, não pelo nomeconsulta.

How to apply: manter Dashboard principal síncrono; LazyLogDialog captura rejeição local e permiteCancelar/Esc na espera. Não prometer retry deReact.lazy rejeitado sem recarregar. 3 perfis DEV eoc_dev_sem_admin/eoc_consulta/eoc_sustentacao são configuração administrativa autorizada; contas/sessões deprova foram descartadas. Não concederadmin nem incluir automaticamente na coorte. Logs guardamRerun/Ack comacao_executar. Testes automáticos/real login não são piloto com pessoas. ConsultaExecução p95 local544,80ms; polling30s. Provas/pós-deploy em /root/orquestra-eoc-evidencias/f6; confirmarSHA/PR/versão vivos antes de inferir implantação.
