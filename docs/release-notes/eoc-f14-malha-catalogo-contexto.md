# EOC-F14 — Malha: catálogo e contexto

O catálogo distingue a definição ativa da situação da corrida. Os cards acomodam nomes longos e a busca ocupa a largura disponível em dispositivos menores, nos temas claro e escuro.

Ao abrir as etapas de um pipeline a partir da execução de uma Malha, a navegação leva o `run_id` da linha selecionada, a Malha, a corrida e a data de processamento. APIs legadas sem identidade não abrem uma execução aproximada. Voltar, avançar e recarregar mantêm o contexto; a seleção por dia continua agregada e a corrida atual implícita registra seu ID antes de recarregar.

Motor, ações, permissões e componentes existentes permanecem no contrato atual. Canvas, propriedades e diagnóstico completo pertencem à EOC-F15. Não há novos contratos de autenticação nem alteração no Airflow/.NET.

Publicação DEV: migration idempotente `193_versao_malha_catalogo_contexto.sql`, versão 2.33.0, API e dist compilada. Fazer backup COPY_ONLY/CHECKSUM/VERIFYONLY, aplicar a única migration pendente e reiniciar somente a API. Confirmar saúde, login, SHA, versão Admin, assets, idempotência SQL e smoke com fixtures próprias removidas. Nenhum job ou envio externo é necessário.

Gates humanos e externos registrados no Backlog continuam pendentes; esta entrega não certifica piloto humano ou execução Caixa/DataStage.
