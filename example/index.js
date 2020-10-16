addEventListener('fetch', e => e.respondWith(handleRequest(e.request)))

async function handleRequest(request) {
  const url = new URL(request.url)
  console.log('handling request:', request.method, url.pathname)
  const data = {
    method: request.method,
    headers: as_object(request.headers),
    url: {
      hostname: url.hostname,
      pathname: url.pathname,
      hash: url.hash,
      params: as_object(url.searchParams),
    },
    body: await request.text(),
  }
  const headers = { 'x-foo': 'bar', 'content-type': 'application/json' }
  return new Response(JSON.stringify(data, null, 2) + '\n', { headers })
}

const as_object = v => {
  const entries = Array.from(v.entries())
  if (entries.length !== 0) {
    return Object.assign(...Array.from(v.entries()).map(([k, v]) => ({ [k]: v })))
  } else {
    return {}
  }
}
