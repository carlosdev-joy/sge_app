# F2 — execução autorizada

Usuário autorizou continuar a próxima fase até concluir, após F1 entregue na develop/DEV. Branch feat/pipeline-workspace-f2 a partir de526ccd9b662fc7bf3aca008a733a42bbda98f005. Main requer autorização separada.

Entrega: schema141, release142, backend de rascunho/importação/consulta/save/descarte, revisão+lease+fence+transferência e auditoria. Nenhuma escrita nas tabelas ativas. Nova UI fica F3; publicação F4. Basic permanece consulta; mutações Bearer com RBAC atual.

Gates: .NET53 testes com SQL sintético e conta restrita, mesma assinatura de8falhas Python existentes e7138passes, TypeScript/build limpos, lint166errors/12warnings existentes, dist inalterada, NUL existente isolado. Revisão adversarial e de segurança independentes, distribuição/rebuild sem rede, backup verificado, PR individual, merge e deploy seletivoDEV com smoke de persistência/concurrency/revogação.

Durante revisão preliminar foram corrigidos: segredo em layout/posição, JSON textual com whitespace, associação parâmetros/valida_arquivo segundo collationSQL, descarte de readonly e comparação semântica de secretReference. Testes de regressão cobrem esses caminhos. Evidências finais: /root/orquestra-f2-evidencias e registro datado no segundo-cérebro.
