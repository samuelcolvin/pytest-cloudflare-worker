
pytest_plugins = 'pytester'


async def test_hello_default(client):
    r = await client.get('/')
    assert r.status == 200


# def test_client_get(testdir):
#     testdir.makepyfile(
#         """
# async def test_hello_default(client):
#     r = await client.get('/')
#     assert r.status == 200
# """
#     )
#     result = testdir.runpytest()
#
#     result.assert_outcomes(passed=1)
