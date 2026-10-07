import {gameInput, gameToolState, gameAction, gameQueryInput, gameQuery, ACTION_NAMES, QUERY_NAMES} from '@/lib/game-authority';
import {SiteError, requireSiteUser} from '@/lib/site-auth';
const legacyProtocols = ['2025-06-18', '2025-03-26', '2024-11-05'];
const modernProtocol = '2026-07-28';
const serverInfo = {name: 'Stardust Curios', version: '0.2.0'};
const instructions = '这是模拟经营游戏，不涉及现实交易或资金。网页与工具共用当前店铺状态。先读取revision，每个经营选择使用唯一operation_id；不确定结果时保持原ID和参数重试。initialize会明确新开测试或正式存档并保留前局备份，仅在用户要求新局时使用。';
const tools = [
 {name: 'stardust_game_state', description: '读取当前模拟店铺的公开状态、存档模式与revision；不读取隐藏箱内物品、精确预算或随机序列。', inputSchema: {type: 'object', properties: {}, additionalProperties: false}, annotations: {readOnlyHint: true, destructiveHint: false, openWorldHint: false}},
 {name: 'stardust_game_query', description: '只读查询当前模拟店铺的市场、顾客、图鉴、物品或最终报价预览，不耗精力、不改变随机数。', inputSchema: {type: 'object', properties: {command: {type: 'string', enum: QUERY_NAMES}, args: {type: 'array', items: {type: 'string'}, maxItems: 2}}, required: ['command', 'args'], additionalProperties: false}, annotations: {readOnlyHint: true, destructiveHint: false, openWorldHint: false}},
 {name: 'stardust_game_action', description: '操作当前模拟游戏，非现实交易。先读revision，每次选择提供唯一operation_id；结果不确定时原ID原参数重试。initialize的args可为[]、[test]或[formal]，会明确新开一局并保留前局备份，仅在用户要求新局时使用。其余命令参数遵循公开游戏说明。', inputSchema: {type: 'object', properties: {operation_id: {type: 'string', pattern: '^[A-Za-z0-9_-]{1,80}$'}, expected_revision: {type: 'integer', minimum: 0, maximum: 1000000000000}, command: {type: 'string', enum: ACTION_NAMES}, args: {type: 'array', items: {type: 'string'}, maxItems: 2}}, required: ['operation_id', 'expected_revision', 'command', 'args'], additionalProperties: false}, annotations: {readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false}},
];
// MCP 2026-07-28: per-request metadata, mirrored headers and complete results.
// Retain the already-connected legacy handshake; neither era grants identity.
function json(body: unknown, status = 200) {
 return Response.json(body, {status, headers: {'Cache-Control': 'no-store'}});
}
function record(value: unknown): value is Record<string, unknown> {
 return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function nameHeader(value: string | null): string | null {
 if (value === null) return null;
 if (value.startsWith('=?base64?') && value.endsWith('?=')) {
  const encoded = value.slice(9, -2);
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) return null;
  try { return new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0))); }
  catch { return null; }
 }
 return /^[\x20-\x7e\t]*$/.test(value) && value.trim() === value ? value : null;
}
export async function POST(request: Request) {
 const protocol = request.headers.get('mcp-protocol-version');
 const modernHeader = protocol !== null && !legacyProtocols.includes(protocol);
 if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') return json({error: 'json_required'}, 415);
 const origin = request.headers.get('origin');
 if (origin && origin !== new URL(request.url).origin) return json({error: 'cross_origin_forbidden'}, 403);
 if (Number(request.headers.get('content-length') || 0) > 16384) return json({error: 'request_too_large'}, 413);
 let rpc: Record<string, unknown>;
 try {
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > 16384) return json({error: 'request_too_large'}, 413);
  rpc = JSON.parse(text);
 } catch { return json({jsonrpc: '2.0', ...(modernHeader ? {} : {id: null}), error: {code: -32700, message: 'Parse error'}}, 400); }
 if (!record(rpc) || rpc.jsonrpc !== '2.0' || typeof rpc.method !== 'string') return json({jsonrpc: '2.0', ...(modernHeader ? {} : {id: null}), error: {code: -32600, message: 'Invalid Request'}}, 400);
 const params = record(rpc.params) ? rpc.params : {};
 const meta = record(params._meta) ? params._meta : {};
 const modern = rpc.method === 'server/discover' || Object.hasOwn(meta, 'io.modelcontextprotocol/protocolVersion') || (protocol !== null && !legacyProtocols.includes(protocol));
 const validId = typeof rpc.id === 'string' || (typeof rpc.id === 'number' && Number.isSafeInteger(rpc.id));
 const id = validId ? rpc.id : null;
 const failure = (code: number, message: string, status = 400, data?: Record<string, unknown>) => json({jsonrpc: '2.0', ...(modern && !validId ? {} : {id}), error: {code, message, ...(data ? {data} : {})}}, status);
 const reply = (result: Record<string, unknown>) => json({jsonrpc: '2.0', id, result: modern ? {...result, resultType: 'complete', _meta: {'io.modelcontextprotocol/serverInfo': serverInfo}} : result});
 if (modern) {
  if (!validId) return failure(-32600, 'Requests require a string or integer ID');
  const version = meta['io.modelcontextprotocol/protocolVersion'];
  if (typeof version !== 'string' || !record(meta['io.modelcontextprotocol/clientCapabilities'])) return failure(-32602, 'Required per-request protocol metadata is missing or invalid');
  const client = meta['io.modelcontextprotocol/clientInfo'];
  if (client !== undefined && (!record(client) || typeof client.name !== 'string' || typeof client.version !== 'string')) return failure(-32602, 'Invalid clientInfo');
  if (protocol !== version || request.headers.get('mcp-method') !== rpc.method) return failure(-32020, 'Header mismatch: required version or method header is absent or differs from the body');
  if (rpc.method === 'tools/call' && typeof params.name !== 'string') return failure(-32602, 'Invalid tool call');
  if (rpc.method === 'tools/call' && nameHeader(request.headers.get('mcp-name')) !== params.name) return failure(-32020, 'Header mismatch: required tool name header is absent, malformed or differs from the body');
  if (version !== modernProtocol) return failure(-32022, 'Unsupported protocol version', 400, {supported: [modernProtocol], requested: version});
  if (rpc.method === 'server/discover') {
   if (Object.keys(params).some(key => key !== '_meta')) return failure(-32602, 'Discovery takes only standard request metadata');
   return reply({supportedVersions: [modernProtocol], capabilities: {tools: {}}, instructions, ttlMs: 0, cacheScope: 'private'});
  }
 } else {
  if (rpc.method === 'notifications/initialized') return new Response(null, {status: 202});
  if (rpc.method === 'initialize') {
   const requested = typeof params.protocolVersion === 'string' ? params.protocolVersion : '';
   return reply({protocolVersion: legacyProtocols.includes(requested) ? requested : '2025-03-26', capabilities: {tools: {listChanged: false}}, serverInfo, instructions});
  }
 }
 if (rpc.method === 'ping') return reply({});
 if (rpc.method === 'tools/list') {
  if (modern && params.cursor !== undefined) return failure(-32602, 'Unknown cursor');
  return reply({tools, ...(modern ? {ttlMs: 0, cacheScope: 'private'} : {})});
 }
 if (rpc.method === 'tools/call' && !validId) return failure(-32600, 'Tool calls require a request ID');
 if (rpc.method !== 'tools/call') return failure(-32601, 'Method not found', 404);
 try {
  const user = requireSiteUser(request);
  if (modern && params.arguments !== undefined && !record(params.arguments)) return failure(-32602, 'Invalid tool arguments');
  let result: unknown;
  if (params.name === 'stardust_game_query') result = await gameQuery(user, gameQueryInput(params.arguments));
  else if (params.name === 'stardust_game_state') {
   const args = params.arguments ?? {};
   if (!record(args) || Object.keys(args).length) throw new SiteError('invalid_arguments', 422);
   result = await gameToolState(user);
  } else if (params.name === 'stardust_game_action') result = await gameAction(user, gameInput(params.arguments));

  else {
   if (modern) return failure(-32602, 'Unknown tool');
   throw new SiteError('unknown_test_tool', 404);
  }
  return reply({content: [{type: 'text', text: JSON.stringify(result)}], structuredContent: result, isError: false});
 } catch (error) {
  const e = error instanceof SiteError ? error : new SiteError('test_service_unavailable', 503);
  if (e.status === 401) return json({error: e.code}, 401);
  if (modern && e.code === 'invalid_arguments') return failure(-32602, 'Invalid tool arguments');
  return reply({content: [{type: 'text', text: JSON.stringify({ok: false, error: e.code})}], isError: true});
 }
}
export function GET() { return new Response('Use stateless MCP POST requests', {status: 405, headers: {Allow: 'POST'}}); }
