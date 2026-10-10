# Workspace — edição no Fluxo — candidato2.12.6

Pedido 10/10/2026: eliminar menu/aba Etapas e iniciar/editar desenvolvimento pelo Fluxo; nomenclaturas de acessos devem refletir estado atual.

Branch fix/workspace-edicao-no-fluxo baseada develop após PR489/DEV2.12.5. Remove aba/lista alternativa de edição; aliases /etapas→Fluxo preservam query/hash; entradas Jobs contextuais e paleta→Fluxo. Desenvolvimento sem aba específica inicia no Fluxo; PipelineCreate/import/restauração já fazem isso. Parâmetros do pipeline mantidos.

Menu duplicado Etapas removido. Label tela_jobs em Admin e Fluxo global passam a Fluxo de pipelines; chave técnica e grants preservados, backend inalterado. Rota Jobs protegida preservada para ferramentas legadas. Busca tem fallback /fluxos?pipeline=...&legado=1 fora das capabilities exigidas, sem redirecionamento indevido.

QA e segurança manual aprovados; evidências /root/orquestra-fluxo-evidencias. Snapshot candidato: entrega final/validações devem ser consultadas no registro compartilhado final. Main/produção sem autorização; lacunas F6 não cobertas.
