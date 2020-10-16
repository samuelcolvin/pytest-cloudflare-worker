async def test_basic_client_usage(client):
    r = await client.get('/')
    assert r.status == 200
    obj = await r.json()
    assert obj['method'] == 'GET'
    assert r.headers['x-foo'] == 'bar'
    log = await client.logs(1)
    assert log == ['LOG: handling request: GET /']
