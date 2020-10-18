addEventListener('fetch', e => e.respondWith(handle(e.request)))

async function handle(request) {
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
  const path = clean_path(url)

  if (path === 'vars') {
    data['vars'] = {FOO, SPAM}
  }

  const headers = { 'x-foo': 'bar', 'content-type': 'application/json' }
  return new Response(JSON.stringify(data, null, 2) + '\n', { headers })
}

const clean_path = url => url.pathname.substr(1).replace(/\/+$/, '')

const as_object = v => {
  const entries = Array.from(v.entries())
  if (entries.length !== 0) {
    return Object.assign(...Array.from(v.entries()).map(([k, v]) => ({ [k]: v })))
  } else {
    return {}
  }
}
