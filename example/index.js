addEventListener('fetch', e => e.respondWith(handleRequest(e.request)))

async function handleRequest(request) {
  const headers = {'x-foo': 'bar'}
  return new Response('pytest-cloudflare-worker example', {headers})
}
