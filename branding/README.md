# branding/ — logo da empresa (persistente, fora do deploy)

Esta pasta guarda o **logo oficial** da Caixa Vida e Previdência exibido no
header e na tela de login do ORQUESTRA.

## Por que existe

O nginx serve esta pasta em **`/branding/`** a partir de um volume (veja
`docker-compose.yaml` → serviço `ui-nginx`). Diferente do `ui-react/dist/`, o
conteúdo aqui **não é versionado** (está no `.gitignore`) e **fora** do build do
front. Resultado: o `scripts/deploy_prod.sh` (que faz `git pull`) **nunca
sobrescreve** o que você colocar aqui à mão.

## Como colocar o logo (no servidor)

1. Copie o arquivo oficial para esta pasta com o nome **exato**:

   ```
   <repo>/branding/logo-cvp.png
   ```

2. Recrie o nginx para o volume passar a existir (só na 1ª vez, ou após mudar o
   `docker-compose.yaml`):

   ```
   docker compose up -d --no-deps --force-recreate ui-nginx
   ```

   Nas próximas vezes que trocar **só a imagem** (mesmo nome), basta substituir o
   arquivo — o nginx serve na hora, sem restart.

3. Confira: abra `http://<host>:8090/branding/logo-cvp.png` no navegador.

## Fallback automático

Enquanto `logo-cvp.png` não existir, o nginx devolve 404 e o front cai
automaticamente no logo **vetorial versionado** em
`ui-react/public/images/logo-cvp.svg` (via `onError` do `<img>`). Ou seja: nada
quebra antes de você subir o arquivo.

## Formato recomendado

- PNG com **fundo transparente** (o logo aparece sobre o gradiente azul do header
  e do login).
- Versão clara/branca do logo (texto branco + símbolo laranja).
- Altura renderizada: ~36px no header / ~56px no login — exporte com folga
  (ex.: 512px de altura) para nitidez em telas retina.
