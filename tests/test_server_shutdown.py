"""Real HTTP streaming shutdown with the board entry's Uvicorn settings, no SDK."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request


@unittest.skipUnless(os.name == 'posix' and importlib.util.find_spec('uvicorn')
                     and importlib.util.find_spec('fastapi'), 'requires the board ASGI environment')
class ServerShutdownTests(unittest.TestCase):
    def test_live_stream_releases_connections_and_runs_lifespan_shutdown(self):
        source = Path(__file__).resolve().parents[1] / 'src' / 'ascend_board_server.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'run'
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == 'uvicorn']
        self.assertEqual(len(calls), 1)
        options = {kw.arg: ast.literal_eval(kw.value) for kw in calls[0].keywords
                   if kw.arg in ('log_level', 'timeout_graceful_shutdown')}
        child = '''
import asyncio,json,pathlib,sys,uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
marker=pathlib.Path(sys.argv[3])
@asynccontextmanager
async def lifespan(app):
    yield
    marker.write_text('shutdown completed')
app=FastAPI(lifespan=lifespan)
@app.get('/stream')
async def stream():
    async def frames():
        while True:
            yield b'frame\\n'
            await asyncio.sleep(.02)
    return StreamingResponse(frames())
try:
    uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),**json.loads(sys.argv[1]))
except KeyboardInterrupt:
    pass
'''
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'shutdown-marker'
            with tempfile.TemporaryFile() as output:
                proc = subprocess.Popen([sys.executable, '-u', '-c', child,
                                         json.dumps(options), str(port), str(marker)],
                                        stdout=output, stderr=subprocess.STDOUT)
                response = None
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        try:
                            response = urllib.request.urlopen('http://127.0.0.1:%d/stream' % port,
                                                              timeout=1)
                            break
                        except OSError:
                            if proc.poll() is not None:
                                output.seek(0)
                                self.fail('server exited: ' + output.read().decode(errors='replace'))
                            time.sleep(.05)
                    self.assertIsNotNone(response, 'stream never became available')
                    self.assertEqual(response.read(6), b'frame\n')
                    proc.send_signal(signal.SIGINT)
                    try:
                        code = proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.fail('open video stream prevented bounded graceful shutdown')
                    self.assertEqual(code, 0)
                    self.assertTrue(marker.exists(), 'lifespan cleanup was skipped')
                finally:
                    if response is not None:
                        response.close()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
