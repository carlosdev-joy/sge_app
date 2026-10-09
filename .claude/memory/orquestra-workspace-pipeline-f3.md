---
name: Workspace Pipeline F3
description: Criação e interface de rascunhos com três experiências e RBAC
type: project
---

F3 autorizada pelo usuário até sua conclusão. Branch feat/pipeline-workspace-f3, base develop65aeb5c. Editor novo desacoplado do FluxoEditor ativo; mutações apenas /workspace. Criação abre fluxo vazio em rascunho, nome humano separado da identidade exata. Header/abas e experiências desenvolvimento/consulta/sustentação obedecem capacidades da sessão e lease/revision/fence do servidor. Execuções exigem tela_pipelines+tela_jobs+tela_logs em .NET e FastAPI. Aliases query preservam slash/percentual/Unicode. Alterações não salvas só na memória da aba, apagadas na troca de sessão.

**Why:** evitar publicação automática, perda de configuração ou bypass por modo de apresentação.
**How to apply:** consultar docs/spec-pipeline-workspace-dotnet.md e docs/release-notes/workspace-pipeline-f3.md. Menus de compatibilidade continuam até F5. Publicação/validação funcional seguem F4. Entrega por PR em develop/DEV, migration143 de versão, backup e smoke obrigatórios; main/produção separados. Evidências locais /root/orquestra-f3-evidencias e registro final na base compartilhada confirmam SHA/deploy, não inferir conclusão a partir desta nota pré-integração.

Validação pré-PR: .NET63PASS com SQL; Python7144PASS/8falhas preexistentes/51SKIP sem regressões; lint166erros12avisos sem novas assinaturas; TypeScript/build; offline68pacotes/120checksums,61PASS/2SQLSKIP cobertos pelo gateSQL. Revisões adversarial/segurança aprovaram código.
