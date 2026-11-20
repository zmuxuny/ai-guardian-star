"""Local-only UI preview with explicit synthetic data; never contacts the board."""
import argparse
import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ('off', 'reminder', 'waiting', 'paused', 'disconnected')


def page(scenario):
    tree = ast.parse((ROOT / 'src/ascend_board_server.py').read_text(encoding='utf-8'))
    html = next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HTML_CONTENT' for t in n.targets))
    links = ' · '.join('<a style="color:#b7f5e5" href="/?scenario=%s">%s</a>' % (key, text)
                       for key, text in zip(SCENARIOS, ('已关闭', '提醒中', '等待识别', '计时暂停', '连接中断')))
    banner = '<div style="padding:10px 16px;background:#193d37;color:#d6fff1;font-size:12px;line-height:1.8;flex-shrink:0">本地设计预览 · 全部为示例数据 · 不连接开发板　' + links + '</div>'
    html = html.replace('<body>', '<body>' + banner, 1)
    html = html.replace("fetch('/api/stats'", "fetch('/api/stats?scenario=" + scenario + "'")
    html = html.replace('<img id="videoFeed" alt="">', '<img id="videoFeed" alt="" style="visibility:hidden"><div style="position:absolute;inset:0;display:grid;place-content:center;text-align:center;color:#a8b6cc;font-size:13px;line-height:2">本地预览不连接摄像头<br><span style="font-size:11px">实际页面保留实时监护画面</span></div>')
    return html


def stats(scenario):
    person = dict(name='演示人员', state='L0', phase='L0', seated_seconds=125,
                  counts={'L0':1, 'L1':0}, uncertainty_reason=None,
                  reminder=dict(level='L0', text='坐了一会儿，起来走走，活动一下吧。'))
    if scenario == 'paused':
        person.update(state='PAUSED', uncertainty_reason='identity_missing')
    care = dict(mode='off' if scenario == 'off' else 'shadow', audio_available=False,
                people=[person] if scenario in ('reminder', 'paused') else [])
    return dict(camera_connected=False, fps=0, detections=0, fall_count=0, status='预览示例',
                mqtt_connected=False, uptime_seconds=0, frame_count=0, keypoint_scores=None,
                sit_count=0, stranger_count=0, faces=[], care=care)


class Handler(BaseHTTPRequestHandler):
    override_mode=None
    def json_response(self, value, status=200, cookie=None):
        body=json.dumps(value).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def do_POST(self):
        if self.path=='/api/care-control/unlock':
            try:body=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),512)))
            except ValueError:body={}
            ok=body.get('password')=='demo'
            self.json_response({'unlocked':ok},200 if ok else 401,'preview-unlocked=1; Path=/; HttpOnly' if ok else None)
        elif self.path=='/api/care-control/lock':self.json_response({'unlocked':False},cookie='preview-unlocked=; Max-Age=0; Path=/')
        else:self.send_error(404)

    def do_PUT(self):
        if self.path!='/api/care-control/mode':self.send_error(404);return
        if 'preview-unlocked=1' not in self.headers.get('Cookie',''):self.json_response({},401);return
        try:body=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),512)))
        except ValueError:body={}
        if type(body.get('enabled')) is not bool:self.json_response({},422);return
        type(self).override_mode=body['enabled'];self.json_response({'status':'done'},202)

    def do_GET(self):
        url = urlsplit(self.path)
        scenario = parse_qs(url.query).get('scenario', ['off'])[0]
        if scenario not in SCENARIOS:
            self.send_error(400)
            return
        if url.path == '/':
            body, content = page(scenario).encode('utf-8'), 'text/html; charset=utf-8'
        elif url.path=='/api/care-control/status':
            if 'preview-unlocked=1' not in self.headers.get('Cookie',''):self.json_response({},401);return
            self.json_response(dict(status='idle',unlocked=True,mode='shadow' if type(self).override_mode else 'off'));return
        elif url.path == '/api/stats' and scenario != 'disconnected':
            if type(self).override_mode is not None:scenario='reminder' if type(self).override_mode else 'off'
            body, content = json.dumps(stats(scenario), ensure_ascii=False).encode('utf-8'), 'application/json'
        else:
            self.send_error(503 if url.path == '/api/stats' else 404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=15502)
    args = parser.parse_args()
    print('Local synthetic preview: http://127.0.0.1:%d/' % args.port, flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
