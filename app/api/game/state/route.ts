import {gameState} from '@/lib/game-authority';
import {requireSiteUser, SiteError} from '@/lib/site-auth';
export async function GET(request: Request) {
 try {
  const result = await gameState(requireSiteUser(request), request.headers.get('if-none-match'));
  const headers = {'Cache-Control': 'private, no-cache', ETag: result.etag};
  return result.unchanged ? new Response(null, {status: 304, headers}) : Response.json(result.body, {headers});
 } catch (error) {
  const e = error instanceof SiteError ? error : new SiteError('game_service_unavailable', 503);
  return Response.json({error: e.code}, {status: e.status, headers: {'Cache-Control': 'no-store'}});
 }
}
