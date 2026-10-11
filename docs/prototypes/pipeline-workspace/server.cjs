/* Servidor local de prévia. Não é parte do produto nem necessário ao abrir index.html. */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const mime = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.md': 'text/plain; charset=utf-8' };
const server = http.createServer((request, response) => {
  let filename;
  try { filename = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname); }
  catch { response.writeHead(400).end(); return; }
  const file = path.resolve(root, '.' + (filename === '/' ? '/index.html' : filename));
  if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
  fs.readFile(file, (error, data) => {
    if (error) { response.writeHead(404).end(); return; }
    response.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); response.end(data);
  });
});
server.listen(8767, '127.0.0.1', () => console.log('Local: http://127.0.0.1:8767'));
