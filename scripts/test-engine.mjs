import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tests = fs.readdirSync(path.join(root, 'tests/engine')).filter(name => name.endsWith('.test.mjs')).sort().map(name => 'tests/engine/' + name);
const result = spawnSync(process.execPath, ['--experimental-strip-types', '--test', '--test-concurrency=1', ...tests], {
 cwd: root, stdio: 'inherit', env: {...process.env, PYTHONDONTWRITEBYTECODE: '1', STARDUST_ENGINE_SOURCE: process.env.STARDUST_ENGINE_SOURCE || path.join(root, 'reference/python/engine.py')},
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
