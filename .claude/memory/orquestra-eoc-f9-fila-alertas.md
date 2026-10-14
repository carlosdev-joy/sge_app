---
name: EOC-F9 fila persistente de alertas
description: F9A fundação dry-run parcial, F9B dispatcher e autoridade ainda pendentes
---

F9 dividida antes de implementar conforme tarefa-F9: F9A fundação persistente, F9B dispatcher/recuperação. Base DEV1acf4919/2.26.0. Codex direto; não iniciar Claude. F9A usa migrations179(schema)/180(versão2.27.0 e gate Backlog). Conferir Git/handoff para publicação, candidato não prova DEV.

Sem endpoint de emissão e sem provider. enqueue_result recusa503; enqueue_dry_run restrito a pipeline/run __eoc_f9_ e source eoc-f9-fixture, snapshot original via workspace_execucao. Eventos+intenções commit único; referências por revisão/índice ou grupo, sem copiar endereços/credenciais. CHECKdry_run=1. Não ativar produtor de clientes enquanto Warning agregado/geraçãoClear não certificados. CapabilitiesF7 continuamfalse.

Ensaio real achou deadlock1205 em HOLDLOCK de chave ausente. Corrigido com sp_getapplock exclusivo transacional por eventKey, retorno negativo503 e SELECTUPDLOCK sem range; unique guards mantidos. Revisão independente ampla e confirmação dirigida da correção realizadas; nenhum scanner alegado. SQL isolado prova concorrência, atomicidade e reconexão; migration180 validada duas vezes em transação DEV revertida. Fixtures/banco removidos, nenhum job/envio.

Docs técnicas: docs/eoc-f9-persistencia-dispatcher.md. Evidências: /root/orquestra-eoc-evidencias/f9a. Suíte inicial inválida por node_modules ausente, preservada separadamente; não usar como baseline/regressão. Dependências reaproveitadas da worktreeF8 via symlink local ignorado. F9B depende de F9A publicada; não declarar F9 concluída por esta fundação.
