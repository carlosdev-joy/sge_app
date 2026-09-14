# E-mail institucional ORQ — reestruturação do modelo existente

Pedido: alinhar os e-mails do nó ao header e ao logo ORQ atuais. Entrega única
sobre main `0bedbe0`. O DEV possui apenas Aviso de fim de carga, id 1, padrão e ativo,
corpo idêntico à migration 113 (hash 1276B7...). Na ausência de outra indicação,
este é o modelo atualizado; corpos personalizados permanecem protegidos.

## Implementação

- Migration 114 substitui somente o corpo original da 113 por HTML Navy/ORQ,
  filete de 4 px, assinatura e rodapé atualizados. Mantém assunto/marcadores/config.
- Logo exportado da renderização do login (mesmo PNG/máscara já aprovados),
  arquivo de 23 KB, 360×144 para exibição em 180×72; sem nova geração ou redesenho.
- API e worker incorporam PNG local como MIME inline CID reservado
  orq-logo@orquestra. Sem URL remota, rede extra ou imagem base64 no HTML.
  Texto simples e anexos permanecem na estrutura MIME apropriada.
- Prévia substitui apenas o CID reservado pelo mesmo asset local, preservando
  iframe sandbox e conteúdo livre. Imagens/CIDs de terceiros não são resolvidos.

## Proteção e limites

Migration idempotente com guarda SHA256 UTF16LE no EXISTS e UPDATE preserva
modelos alterados pelo usuário. Logo vem de caminho fixo empacotado; dado do
modelo não determina arquivo ou URL. Nenhum e-mail real é enviado na validação.
Sem alteração de destinatários, SMTP, permissões, interpolação ou execuções.
Nenhum novo pacote Python; nenhuma dependência de serviço externo.

HTML usa tabelas, dimensões explícitas e cores inline compatíveis com o padrão
Outlook já adotado. Validação Chromium/MIME não substitui Outlook desktop real
ou as políticas de bloqueio de imagem do destinatário; conferir após deploy.

## Testes e deploy

Regressão antes: HTML não incorporava imagens e não havia migrationORQ.
Testes: API/worker anti-drift, CID+anexo+texto, modelos livres intactos, assets
iguais, hash de guarda/marcadores, preview reservado, compatibilidade HTML. Suíte
completa comparada ao baseline, build/lint e revisão adversarial/segurança.

Deploy inclui API, dags/utils com PNG e frontend dist, além de migration 114.
Atualizar API/worker com suporte CID antes de usar o novo modelo. Reiniciar
worker e scheduler para descartar módulos cacheados. Produção via etapa 6c,
sem envio automático de teste. Atualizações em modelo personalizado são manuais
usando docs/branding/orq-email-modelo.html após conferência do administrador.

Conferência: abrir nó→modelo→prévia, logo legível no Navy, parâmetros preservados;
gerar EML offline e conferir imagem inline e anexo; avaliar Outlook com envio
somente se o usuário autorizar destinatário e envio explicitamente.
