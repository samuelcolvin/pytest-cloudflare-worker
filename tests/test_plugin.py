async def test_basic_client_usage(client):
    r = await client.get('/')
    assert r.status == 200
    assert await r.text() == 'pytest-cloudflare-worker example'
    assert r.headers['x-foo'] == 'bar'
