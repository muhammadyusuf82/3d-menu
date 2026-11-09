import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dataDir = process.env.DATA_DIR ? path.resolve(process.env.DATA_DIR) : path.join(root, 'data');
const port = Number(process.env.PORT ?? 3000);

const { server } = createApp({
  dbPath: path.join(dataDir, 'sizzle.db'),
  dataDir,
  staticDir: path.join(root, 'dist'),
});

server.on('error', (e: NodeJS.ErrnoException) => {
  if (e.code === 'EADDRINUSE') console.error(`\nPort ${port} is already in use. Set another one, e.g. PORT=3001.\n`);
  else console.error(e);
  process.exit(1);
});

server.listen(port, '0.0.0.0', () => {
  const addrs = Object.values(os.networkInterfaces())
    .flat()
    .filter((i): i is os.NetworkInterfaceInfo => !!i && i.family === 'IPv4' && !i.internal)
    .map((i) => i.address);
  console.log('\n  Sizzle is running.\n');
  console.log(`  This computer : http://localhost:${port}`);
  for (const a of addrs) console.log(`  Tablets (LAN) : http://${a}:${port}`);
  console.log(`\n  Data folder   : ${dataDir}\n`);
});

const stop = () => { server.close(() => process.exit(0)); setTimeout(() => process.exit(0), 1500).unref(); };
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
