#!/usr/bin/env node
/**
 * Minimal HTTP reverse proxy using only Node.js built-ins.
 * Usage: node proxy-server.js <listenPort> <targetPort>
 * Example: node proxy-server.js 5274 5174
 */
const http = require('http');

const listenPort = parseInt(process.argv[2] || '5274', 10);
const targetPort = parseInt(process.argv[3] || '5174', 10);

const server = http.createServer((req, res) => {
  const options = {
    hostname: 'localhost',
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `localhost:${targetPort}` },
  };

  const proxy = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxy.on('error', (err) => {
    res.writeHead(502);
    res.end(`Proxy error: ${err.message}`);
  });

  req.pipe(proxy, { end: true });
});

server.listen(listenPort, () => {
  process.stdout.write(`Proxy :${listenPort} → :${targetPort}\n`);
});
