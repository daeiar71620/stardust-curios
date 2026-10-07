export async function sha256(text: string): Promise<string> {
 return sha256Bytes(new TextEncoder().encode(text));
}
export async function sha256Bytes(input: Uint8Array): Promise<string> {
 const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', input as BufferSource));
 return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
}
