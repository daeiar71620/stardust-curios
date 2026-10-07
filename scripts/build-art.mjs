// The entire catalog is a SERVER seed, never a client/static asset directory.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.join(root, 'assets/server-art');
const manifestBytes = fs.readFileSync(path.join(source, 'manifest.json'));
const manifest = JSON.parse(manifestBytes);
const version = crypto.createHash('sha256').update(manifestBytes).digest('hex');
const payload = {}, metadata = {};
for (const [id, filename] of Object.entries(manifest.art)) {
 if (!/^[a-z0-9_-]{1,48}$/.test(id) || filename !== 'png/' + id + '.png') throw Error('Invalid private artwork manifest');
 const bytes = fs.readFileSync(path.join(source, filename));
 const digest = crypto.createHash('sha256').update(bytes).digest('hex');
 const row = manifest.items.find(row => row.art_id === id);
 if (!row || digest !== row.sha256 || bytes.length !== row.bytes) throw Error('Artwork digest mismatch: ' + id);
 payload[id] = {sha256: digest, base64: bytes.toString('base64')};
 metadata[id] = {sha256: digest, bytes: bytes.length};
}
function write(name, content) {
 const file = path.join(root, 'lib', name);
 if (!fs.existsSync(file) || fs.readFileSync(file, 'utf8') !== content) fs.writeFileSync(file, content);
}
const header = '// Generated from assets/server-art. SERVER ONLY; never import from client code.\n';
write('server-art-data.ts', header + 'export const PRIVATE_ART: Record<string,{sha256:string;base64:string}> = ' + JSON.stringify(payload) + ';\n');
write('server-art-manifest.ts', header + 'export const ART_VERSION = ' + JSON.stringify(version) + ';\nexport const PRIVATE_ART_METADATA: Record<string,{sha256:string;bytes:number}> = ' + JSON.stringify(metadata) + ';\n');
console.log(JSON.stringify({privateArt: Object.keys(payload).length, totalPngBytes: manifest.total_png_bytes, version}));
