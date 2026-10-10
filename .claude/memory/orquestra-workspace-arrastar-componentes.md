---
name: Arrastar componentes no workspace
description: Candidato2.12.4 recupera arraste da biblioteca para criação no ponto de soltura
type: project
---

10/10/2026: usuário pede arrastar componente para a área de desenho. Correção pontual de paridade do editor anterior, única PR em fix/workspace-arrastar-componentes baseada em develop3fa16c1. Biblioteca draggable somente editable/lease, MIME próprio e tipo validado; canvas usa screenToFlowPosition do viewport atual. Cria nó no ponto de soltura e seleciona para configurar. Clique permanece, touch tem clique como alternativa; nenhuma dependência/alteração servidor. Snapshot publicado preservado.

Este snapshot descreve candidato antes de integração/deploy. Migration152 registra2.12.4. Estado final SHA/PR/backup/smoke e limites serão registrados no segundo cérebro e memória viva. Produção/main não autorizados. Lacunas de F6 fora deste gesto continuam pendentes.

Why: permitir montar o fluxo com o gesto já disponível anteriormente.
How to apply: iniciar edição, arrastar da biblioteca para o canvas, configurar etapa e salvar rascunho.
