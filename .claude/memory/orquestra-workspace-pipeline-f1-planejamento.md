# Workspace Pipeline — preparação e plano F1

Data: 2026-10-09. Estado atualizado: plano aprovado; implementação e validação local concluídas, integração DEV em preparação.

- DEV confirmado em `/opt/orquestra-dev`, develop `6e711e54e5883fb6d66edf13dfc1fe229df19c45`, árvore limpa e serviços ativos; nenhum serviço alterado.
- Worktree isolada `/root/orquestra-workspace-f1`, branch `feat/pipeline-workspace-f1`, baseada em origin/develop.
- Documentação e quatro mockups copiados da branch documental no SHA `9fec0ae23bf57cef321f030b3bb8c3d3f6e8af4c`; quatro PNGs abertos. Correção da informação inicial de ausência dos mockups após atualização informada pelo usuário.
- Plano: `docs/superpowers/plans/2026-10-09-pipeline-workspace-f1.md`; baseline sanitizado no JSON adjacente.
- Sessão opaca SHA-256 persistida em SQL; perfil único + extras; navegação permissiva com lista vazia; publicação legada usa acao_executar. Plano propõe capacidades explícitas sem habilitar escrita F1.
- Pytest: 7131 passed, 8 failed, 51 skipped; tsc/build passaram; lint 166 erros/12 avisos. SQL vivo não habilitado na suíte; metadata consultada por SELECT.
- SDK isolado 10.0.401 e ASP.NET 10.0.12 disponíveis e verificados; solução net10.0 implementada. Pacote offline com restore locked/cache vazia, save/load e rebuild consumidor sem rede aprovado; Linux/amd64 apenas, sem ensaio Caixa.
- Aprovação confirmada pelo usuário: “pode seguir” na sessão anterior; retomada e autorização para concluir todo processo F1 nesta sessão. Main/produção fora do escopo. F1 não cria drafts nem retira menus. Próximo passo deste registro: PR/deploy seletivo DEV após revisões aprovadas, seguindo docs/release-notes/workspace-pipeline-f1.md.

Verificação adicional: bytes NUL preexistentes em `ui-react/src/lib/lineageIsx.ts`, confirmados no blob de origin/develop. Registrados sem alteração de código; tratamento requer tarefa de correção apropriada.

## Implementação e gates observados na retomada

- Fundação .NET, contratos v1, compatibilidade Bearer/Basic, SQL parametrizado e capacidades estritas sem ações de escrita. Não há endpoint de leitura de definição implementado; IFlowAccess é contrato para fases seguintes.
- .NET 38 testes passaram, zero skips, incluindo SQL real em banco/login sintéticos isolados e somente SELECT. Nenhum usuário/sessão real foi usado na bancada.
- Pytest 7136 passed/8 baseline failed/51 skipped; tsc/build passaram; lint 166 errors/12 warnings sem novos. Dist permaneceu idêntica. Bytes NUL somente no arquivo já registrado.
- Revisão adversarial corrigiu invisibilidade de metadata SQL (agora SELECT direto/208 vs 229) e deadline Basic incluindo body. Reavaliação aprovada; revisão independente infra/empacotador sem vulnerabilidade confirmada.
- Proxy isolado validado; migration 140 versiona F1. Backup DEV COPY_ONLY com checksum e VERIFYONLY realizado antes da integração. Credencial de aplicação será somente SELECT por coluna em sessão/RBAC.
- Referência de entrega: docs/release-notes/workspace-pipeline-f1.md. Evidências operacionais ficam fora do Git, em /root/orquestra-f1-evidencias e registros/orquestra do contexto compartilhado; consultar o registro final para PR/SHA/deploy, não inferir implantação a partir desta memória de preparação.
- Pendências posteriores: F2 persistência de drafts, F4 granularidade de publicar; distribuição Caixa e DataStage real exigem validação própria.
