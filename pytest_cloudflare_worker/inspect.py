import asyncio
import json
import warnings
from threading import Event
from typing import Any, Dict, List, Optional

import websockets

__all__ = 'inspect', 'LogMsg'


def inspect(*, session_id: str, log: List['LogMsg'], ready: Event, stop: Event, received: Event):
    async def async_inspect() -> None:
        async with websockets.connect(f'wss://cloudflareworkers.com/inspect/{session_id}') as ws:
            for msg in inspect_start_msgs:
                await ws.send(msg)

            while True:
                f = ws.recv()
                try:
                    msg = await asyncio.wait_for(f, timeout=0.1)
                except asyncio.TimeoutError:
                    pass
                else:
                    data = json.loads(msg)
                    if data.get('id') == 8:  # this is the id of the last element of inspect_start_msgs
                        ready.set()

                    log_msg = LogMsg.from_raw(data)
                    if log_msg:
                        log.append(log_msg)
                        received.set()

                if stop.is_set():
                    return

    asyncio.run(async_inspect())


# we don't need all of these, but not clear which we do
inspect_start_msgs = [
    json.dumps({'id': 1, 'method': 'Profiler.enable'}),
    json.dumps({'id': 2, 'method': 'Runtime.enable'}),
    json.dumps({'id': 3, 'method': 'Debugger.enable'}),
    json.dumps({'id': 4, 'method': 'Debugger.setPauseOnExceptions', 'params': {'state': 'none'}}),
    json.dumps({'id': 5, 'method': 'Debugger.setAsyncCallStackDepth', 'params': {'maxDepth': 32}}),
    json.dumps({'id': 6, 'method': 'Network.enable', 'params': {'maxPostDataSize': 65536}}),
    json.dumps({'id': 7, 'method': 'Debugger.setBlackboxPatterns', 'params': {'patterns': []}}),
    # json.dumps({'id': 7, 'method': 'Runtime.runIfWaitingForDebugger'}),
    json.dumps({'id': 8, 'method': 'Runtime.getIsolateId'}),
]

ignored_methods = {
    'Runtime.executionContextCreated',
    'Runtime.executionContextDestroyed',
    'Debugger.scriptParsed',
    'Profiler.enable',
    'Network.enable',
    'Network.dataReceived',
    'Network.loadingFinished',
}
known_methods = {
    'Runtime.consoleAPICalled',
    'Runtime.exceptionThrown',
    'Network.requestWillBeSent',
    'Network.responseReceived',
}


class LogMsg:
    def __init__(self, method: str, data):
        # debug(data)
        self.full = data
        params = data['params']
        if method == 'Runtime.consoleAPICalled':
            self.level = params['type'].upper()
            self.args = [self.parse_arg(arg) for arg in params['args']]
            self.message = ', '.join(json.dumps(arg) for arg in self.args)
            frame = params['stackTrace']['callFrames'][0]
            self.file = frame['url']
            self.line = frame['lineNumber'] + 1
        elif method == 'Runtime.exceptionThrown':
            self.level = 'ERROR'
            details = params['exceptionDetails']
            self.message = details['exception']['description']
            self.file = details['url']
            self.line = details['lineNumber'] + 1
        elif method == 'Network.requestWillBeSent':
            self.level = 'INFO'
            request = params['request']
            self.message = 'request {method} {url}'.format(**request)
            self.headers = request['headers']
            self.file = '<unknown>'
            self.line = params['initiator']['lineNumber'] + 1
        else:
            assert method == 'Network.responseReceived', method
            self.level = 'INFO'
            response = params['response']
            self.message = 'response {status}'.format(**response)
            self.headers = response['headers']
            self.file = '<unknown>'
            self.line = 0

    @classmethod
    def from_raw(cls, data: Dict[str, Any]) -> Optional['LogMsg']:
        method = data.get('method')
        if not method or method in ignored_methods:
            return
        elif method in known_methods:
            return cls(method, data)
        else:
            raise RuntimeError(f'unknown message from inspect websocket, type {method}\n{data}')

    @classmethod
    def parse_arg(cls, arg: Dict[str, Any]) -> Any:
        arg_type = arg['type']
        value = arg.get('value')
        if arg_type == 'string':
            return value
        if arg_type == 'number':
            return float(value)
        elif arg_type == 'boolean':
            return value == 'true'
        elif value == 'null':
            return None
        elif value == 'undefined':
            # no good python equivalent
            return '<undefined>'

        # TODO in theory to get more information about objects we need to do
        # send a "Runtime.getProperties" message
        if arg_type == 'object' and (description := arg.get('description')):
            return description
        else:  # pragma: no cover
            warnings.warn(f'unknown inspect log argument {arg}')
            return str(arg)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return other == str(self)
        elif isinstance(other, dict):
            self_dict = {k: self.__dict__[k] for k in other.keys()}
            return other == self_dict
        else:
            return False

    def endswith(self, *s: str) -> bool:
        return str(self).endswith(*s)

    def startswith(self, *s: str) -> bool:
        return str(self).startswith(*s)

    def __str__(self):
        return f'{self.level} {self.file}:{self.line}> {self.message}'

    def __repr__(self):
        return repr(str(self))
