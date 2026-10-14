---
name: EOC-F12 tratamento de falhas
description: Adapter transacional de ack, prioridade, versão e auditoria
type: project
---

Base DEV01fc4d1240f883dc865853e768e6a3263f91248e/2.30.0. F12 implementada
na worktree própria; evidências /root/orquestra-eoc-evidencias/f12.
Contrato em docs/eoc-f12-tratamento-alertas.md; migrations186/187.

Why: tratamento separado de processamento/comunicação/entrega, preservando
primeira comunicação legada depoiscommit/changed-only. Ler não assume;
resolver não mudaFAILED; repetir não reenvia. História preservada apósrelease.

How to apply: identidade exata, ator servidor, versão/expectedVersion,
conflitos409 e bulk atômico. Snapshot legado sem geração presumida. Link exato
sobrevive reload e navegação na mesma rota; UI usa permissão efetiva.
QA e smoke usam banco descartável e transportes mocks, nunca cliente.
Revisão independente corrigiu prioridade histórica, nome longo e UTC;
principal exigiu preservar primeira comunicação e contextoURL, com correções.
F9–11 internos de integração/cutover/formAdmin seguem paraF13 conforme tarefas;
capabilities/dispatcher continuamOFF. Não alegar ativação externa ou100%humano.

Candidato validado: suíte8255/8196PASS/exatas8FAIL51SKIP216.064s,lint176,
tsc-b/build/distPASS; SQLreal descartável2.344s,19dirigidosPASS; Chromium
1440claro/390escuro comAPIinterceptada confirmaURL/UTC e visualcorrigido.
Revisorhostpytest rejeitado e respeitado; confirmação final estática/visual.
