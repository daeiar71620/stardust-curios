/** Identity is supplied only by the existing Sites authentication boundary. */
export class SiteError extends Error {
 constructor(public code: string, public status = 409) { super(code); }
}
export function requireSiteUser(request: Request): string {
 const user = request.headers.get('oai-authenticated-user-id');
 if (!user) throw new SiteError('sign_in_required', 401);
 return user;
}
