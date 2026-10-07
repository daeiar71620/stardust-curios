import {discoveredArtwork} from '@/lib/game-art';
import {requireSiteUser, SiteError} from '@/lib/site-auth';
export async function GET(request: Request, context: {params: Promise<{id: string}>}) {
 try {
  const user = requireSiteUser(request);
  const {id} = await context.params;
  const art = await discoveredArtwork(user, id, new URL(request.url).searchParams.get('stream'));
  const etag = '"' + art.digest + '"';
  const headers = {'Content-Type': 'image/png', 'Cache-Control': 'private, no-cache', 'X-Content-Type-Options': 'nosniff', ETag: etag};
  if (request.headers.get('if-none-match') === etag) return new Response(null, {status: 304, headers});
  return new Response(art.bytes, {headers});
 } catch (error) {
  const e = error instanceof SiteError ? error : new SiteError('art_unavailable', 503);
  return Response.json({error: e.code}, {status: e.status, headers: {'Cache-Control': 'no-store'}});
 }
}
