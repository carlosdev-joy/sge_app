# Workspace de Pipeline — F2

Persistência de rascunhos em quatro tabelas próprias, com importação da configuração publicada, revisão, lease por sessão com fence crescente, transferência administrativa e auditoria transacional. Uma configuração salva continua disponível após desconexão e reinício; duas sessões não possuem a edição simultaneamente.

Migrations141(schema idempotente) e142(versão pública, incremento minor). Conta SQL dedicada recebe leitura do cadastro legado e escrita somente nas tabelas workspace; versões base e eventos não permitem alteração. A importação preserva campos e tipos desconhecidos sem transportar valores encrypted. Configuração incompatível permanece somente leitura e pode ser descartada.

Piloto exclusivamente DEV, flag WORKSPACE_DRAFTS_ENABLED. Não modifica tabelas ativas, gera DAGs nem habilita publicação/execução. A interface permanece nesta entrega; F3 tratará a edição visual. Contratos em docs/contracts/workspace-drafts-v1.md; ameaças em docs/workspace-f2-ameacas.md.

Validação final: suíte .NET com SQL sintético, baseline Python/TypeScript/lint/build, revisões independentes, pacote offline e smoke do ciclo de rascunho no serviço DEV. Evidências finais registradas no segundo-cérebro e no diretório de entrega da F2.
