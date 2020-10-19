addEventListener('fetch', e => e.respondWith(handle(e.request)))

const TESTING = typeof __TESTING__ !== 'undefined' && __TESTING__ === 'TRUE'

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
    TESTING,
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
  } else if (path === 'console') {
    console.log('object', {foo: 'bar', spam: 1})
    console.log('list', ['s', 1, 2.0, true, false, null, undefined])
    const n = new Date()
    console.log('date', n)
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
