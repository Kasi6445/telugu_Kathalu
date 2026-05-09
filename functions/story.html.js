// functions/story.html.js
// Server-side 301 redirect from old ?id=slug URLs to new /story/{slug}/ paths.
// Runs on Cloudflare Pages edge before any static asset is served.

export function onRequest({ request }) {
  const url = new URL(request.url);
  const id = url.searchParams.get('id');

  if (!id) {
    return Response.redirect('https://www.telugukathalu.in/', 301);
  }

  if (!/^[a-z0-9-]+$/i.test(id)) {
    return Response.redirect('https://www.telugukathalu.in/', 301);
  }

  return Response.redirect(`https://www.telugukathalu.in/story/${id}/`, 301);
}
