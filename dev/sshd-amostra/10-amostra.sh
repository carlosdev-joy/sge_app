#!/bin/sh
# dev/sshd-amostra/10-amostra.sh — árvore de amostra do servidor de arquivos de DEV.
#
# A VPS não tem servidor DataStage. O container `sshd-amostra`
# (docker-compose.dev.yaml) faz o papel dele SÓ para o SFTP da tela Utilitários
# (spec docs/spec-utilitarios-arquivos.md). Este script roda no arranque do
# container (linuxserver: /custom-cont-init.d) e monta, uma única vez, os casos
# que a spec manda provar ao vivo:
#
#   /dados/bi                       raiz 1 (cadastrar no Admin)
#     2026/cargas/carga_utf8.txt    texto UTF-8 com acento
#     consulta.sql                  texto simples
#     logs/grande.log               ~5 MB — acima do teto padrão (2 MB)
#     imagem.bin                    binário (NUL) → 415
#     .oculto.txt                   oculto (o navegador esconde por padrão)
#     link_fora -> /fora            symlink para FORA das raízes → 403
#   /dados/param                    raiz 2
#     parametros_latin1.param       Latin-1 com "ação" (bytes E7 E3)
#     sem_acesso/                   pasta root:700 — "existe, mas não é legível"
#   /fora/segredo.txt               fora de qualquer raiz (não pode aparecer)
#
# Nada disto vai para o git: o container gera tudo. `docker compose stop/start`
# preserva; só `down` apaga (e o script remonta no próximo `up`).
set -eu

MARCA=/dados/.amostra-pronta
BI=/dados/bi
PARAM=/dados/param
FORA=/fora

# Cada bloco tem o seu marcador e NENHUM sai do script (`exit`): um container
# criado antes de uma fase nova ganha só o que falta no próximo restart.
if [ -f "$MARCA" ]; then
    echo "[amostra] árvore dos Utilitários já montada — nada a fazer"
else

mkdir -p "$BI/2026/cargas" "$BI/logs" "$PARAM" "$FORA"

printf 'linha 1: carga diária\nlinha 2: ação concluída com sucesso\nlinha 3: fim\n' \
    > "$BI/2026/cargas/carga_utf8.txt"
printf 'SELECT 1 AS x;\n' > "$BI/consulta.sql"

# Latin-1: "ação" = a \347 \343 o (octal de E7 E3). Não passa pelo UTF-8 estrito.
printf 'PARAM_ORIGEM=/dados/bi\nDESCRICAO=a\347\343o de carga\nLIMITE=100\n' \
    > "$PARAM/parametros_latin1.param"

# Binário: NUL logo no começo.
printf '\000\000BIN\000' > "$BI/imagem.bin"
head -c 4096 /dev/urandom >> "$BI/imagem.bin"

printf 'segredo local — oculto\n' > "$BI/.oculto.txt"

# ~5 MB de log numerado (60.000 linhas × ~85 bytes).
awk 'BEGIN { for (i = 1; i <= 60000; i++)
    printf "2026-09-03 00:%02d:%02d linha %06d do log de exemplo para exercitar o teto de tamanho\n", (i/60)%60, i%60, i }' \
    > "$BI/logs/grande.log"

printf 'isto NÃO pode aparecer pela tela\n' > "$FORA/segredo.txt"
ln -sfn "$FORA" "$BI/link_fora"

# O usuário SSH (uid 1000) é dono das raízes: a F4 grava aqui.
chown -R 1000:1000 /dados
chmod -R u+rwX,go+rX /dados
chmod 755 "$FORA"; chmod 644 "$FORA/segredo.txt"

# Pasta que existe mas o usuário SSH não consegue listar (botão Testar do Admin).
mkdir -p "$PARAM/sem_acesso"
chown root:root "$PARAM/sem_acesso"
chmod 700 "$PARAM/sem_acesso"

touch "$MARCA"
echo "[amostra] árvore montada em /dados (raízes: $BI e $PARAM) e $FORA"

fi  # árvore dos Utilitários

# ═══════════════════════════════════════════════════════════════════════════
# Information Server de MENTIRA (spec docs/spec-lineage-isx.md, F1)
#
# A API monta o comando do istool exatamente como em produção:
#   . $HOME_IS/ASBNode/bin/setupEnv.sh && "$JAVA_HOME"/bin/java -jar <launcher> … export …
# Aqui o setupEnv.sh aponta JAVA_HOME para um "jdk" cujo bin/java é um shell
# script: ele lê `-archive X` e `-datastage ENGINE/PROJ/Jobs/…/JOB.pjb` e copia
# /dados/bi/isx/JOB.isx para X (ou falha como o istool falharia). Os .isx reais
# o usuário sobe pela tela Utilitários › Enviar arquivo para /dados/bi/isx/.
# Marcador próprio: roda também em containers criados antes desta fase.
# ═══════════════════════════════════════════════════════════════════════════
MARCA_IS=/dados/.amostra-isx-pronta
IS=/opt/IBM/InformationServer
if [ ! -f "$MARCA_IS" ]; then
    mkdir -p "$IS/ASBNode/bin" "$IS/jdk/bin" "$IS/Clients/istools/cli/plugins" \
             "$IS/Clients/istools/cli/configuration" "$BI/isx"
    cat > "$IS/ASBNode/bin/setupEnv.sh" <<'EOF'
# setupEnv.sh de amostra: só o que o comando da API usa.
export JAVA_HOME=/opt/IBM/InformationServer/jdk
export DSHOME=/opt/IBM/InformationServer/Server/DSEngine
EOF
    cat > "$IS/jdk/bin/java" <<'EOF'
#!/bin/sh
# "java" de amostra: faz o papel do launcher do istool para o comando `export`.
archive=""; ds=""; auth=""; preview=0
while [ $# -gt 0 ]; do
    case "$1" in
        -archive)   archive=$2; shift ;;
        -datastage) ds=$2; shift ;;
        -authfile)  auth=$2; shift ;;
        -preview)   preview=1 ;;
        -password)  echo "amostra: -password na linha de comando e PROIBIDO" >&2; exit 9 ;;
    esac
    shift
done
# Como o istool de verdade: o -authfile tem de existir no servidor (o conteudo nao e
# lido aqui). Um `~` que chegue literal (entre aspas) cai neste erro.
[ -n "$auth" ] || { echo "amostra: faltou -authfile" >&2; exit 3; }
[ -f "$auth" ] || { echo "IISCOM000: authfile nao encontrado: $auth" >&2; exit 3; }
if [ "$preview" = 1 ]; then ls /dados/bi/isx/*.isx 2>/dev/null | sed 's#.*/##; s#\.isx$##'; exit 0; fi
[ -n "$archive" ] && [ -n "$ds" ] || { echo "amostra: faltou -archive ou -datastage" >&2; exit 2; }
job=$(basename "$ds"); job=${job%.*}
if [ -f "/dados/bi/isx/$job.isx" ]; then
    cp "/dados/bi/isx/$job.isx" "$archive" && echo "Exported 1 asset(s): $job"
else
    echo "IISCOM000: No assets matched $ds" >&2; exit 1
fi
EOF
    chmod 755 "$IS/jdk/bin/java"
    : > "$IS/Clients/istools/cli/plugins/org.eclipse.equinox.launcher_1.1.0.v20100507.jar"
    echo "# configuration de amostra" > "$IS/Clients/istools/cli/configuration/config.ini"
    chmod -R a+rX "$IS"
    # authfile de amostra: o java falso confere que o caminho existe (como o istool), não o lê.
    mkdir -p /config/.orquestra && printf 'user=amostra\npassword=amostra\n' > /config/.orquestra/istool.auth
    chown -R 1000:1000 /config/.orquestra "$BI/isx"; chmod 600 /config/.orquestra/istool.auth
    touch "$MARCA_IS"
    echo "[amostra] Information Server de mentira em $IS; .isx em $BI/isx"
fi
