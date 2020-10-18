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
      params: as_object(url.searchParams),
    },
    body: await request.text(),
  }
  const path = clean_path(url)

  if (path === 'vars') {
    data['vars'] = {FOO, SPAM}
  } else if (path === 'kv') {
    const key = url.searchParams.get('key') || 'the-key'
    const value = data['body']
    console.log('settings KV', key, value)
    // console.log('settings KV', {[key]: value})
    await THINGS.put(key, value, {expirationTtl: 3600})
    data['KV'] = {[key]: await THINGS.get(key)}
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
