// functions/story.html.js
// Server-side 301 redirect from old ?id=slug URLs to new /story/{slug}/ paths.
// Runs on Cloudflare Pages edge before any static asset is served.

const VALID_CATS = new Set([
  'neeti', 'podupu', 'tenali', 'panchatantra',
  'ramayana', 'samethalu', 'janapada', 'bhagavatam',
]);

export function onRequest({ request }) {
  const url  = new URL(request.url);
  const id   = url.searchParams.get('id');
  const from = url.searchParams.get('from');

  if (!id) {
    return Response.redirect('https://www.telugukathalu.in/', 301);
  }

  if (!/^[a-z0-9-]+$/i.test(id)) {
    return Response.redirect('https://www.telugukathalu.in/', 301);
  }

  // Preserve category context so the back button on the story page shows
  // the right category instead of "← అన్ని కథలు".
  const fromSuffix = (from && VALID_CATS.has(from)) ? `?from=${from}` : '';
  return Response.redirect(`https://www.telugukathalu.in/story/${id}/${fromSuffix}`, 301);
}
