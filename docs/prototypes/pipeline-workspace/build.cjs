/* Gera uma cópia portátil para abrir diretamente, sem instalar dependências. */
const fs = require('node:fs');
const path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
const result = read('index.html')
  .replace('<link rel="stylesheet" href="styles.css">', `<style>${read('styles.css')}</style>`)
  .replace('<script defer src="model.js"></script>', '')
  .replace('<script defer src="app.js"></script>', '')
  .replace('</body>', `<script>${read('model.js')}\n${read('app.js')}</script></body>`);
fs.writeFileSync(path.join(__dirname, 'pipeline-workspace.html'), result, 'utf8');
console.log('Criado: pipeline-workspace.html · cópia portátil sem dependências.');
