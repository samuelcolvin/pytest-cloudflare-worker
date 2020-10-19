# pytest cloudflare worker

[![CI](https://github.com/samuelcolvin/pytest-cloudflare-worker/workflows/ci/badge.svg?event=push)](https://github.com/samuelcolvin/pytest-cloudflare-worker/actions?query=event%3Apush+branch%3Amaster+workflow%3Aci)
[![Coverage](https://codecov.io/gh/samuelcolvin/pytest-cloudflare-worker/branch/master/graph/badge.svg)](https://codecov.io/gh/samuelcolvin/pytest-cloudflare-worker)
[![pypi](https://img.shields.io/pypi/v/pytest-cloudflare-worker.svg)](https://pypi.python.org/pypi/pytest-cloudflare-worker)
[![versions](https://img.shields.io/pypi/pyversions/pytest-cloudflare-worker.svg)](https://github.com/samuelcolvin/pytest-cloudflare-worker)
[![license](https://img.shields.io/github/license/samuelcolvin/pytest-cloudflare-worker.svg)](https://github.com/samuelcolvin/pytest-cloudflare-worker/blob/master/LICENSE)

CloudFlare worker system tests packaged as a pytest plugin.

Features:

* **real environment** - the plugin deploys your worker to a preview environment, then routes real HTTPS
  requests to the worker so you get a true environment in tests
* **advanced features** - like environment variables and KV worker database work out of the box
* **wrangler integration** - the plugin integrated with [wrangler](https://github.com/cloudflare/wrangler) to build
  your worker and setup bindings like environment variables and KV worker namespaces
* **logging** - logs from workers using `console.log(...)` are available in tests

**In beta, this package is currently active development, API may change at any time**

## Install

```bash
pip install pytest-cloudflare-worker
```

## Usage

TODO
