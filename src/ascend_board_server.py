import sys
import os
import time
import socket
import asyncio
import threading
import secrets
import uuid
import uvicorn
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, Response, JSONResponse

# --- 路径设置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

import ascend_video_stream as video_hw
from ascend_main_other import AclLiteStreamDetector, MQTTAlertClient, MODEL_PATH, draw_results
from guardian_runtime import AlertEpisodeTracker
from guardian_recording_config import RecordingConfig
from guardian_storage import initialize_storage
from guardian_history import HistoryStore
from guardian_event_cache import EventClipCache
from guardian_recording import RecordingManager
from guardian_continuous import ContinuousCaptureSink
from guardian_ffmpeg_backend import create_backend
from guardian_cleanup import CleanupScheduler
from guardian_history_api import create_history_router
from guardian_heartbeat import MqttHeartbeatPublisher, heartbeat_interval
try:
    import ascend_voice_stream as audio_hw
except Exception:
    class _AudioStub:
        @staticmethod
        def start_audio_service():
            return None
        @staticmethod
        def get_audio_frame():
            return None
        @staticmethod
        def put_audio_frame(_frame):
            return None
        @staticmethod
        def stop_audio_service():
            return None
    audio_hw = _AudioStub()

app = FastAPI()
history_store = None
event_cache = None
cleanup_scheduler = None
alert_mqtt = None
heartbeat_publisher = None
care_runtime = None
care_initialization_failed = False
care_worker = None
care_audio_player = None
care_last_poll = 0.0
continuous_store = None
continuous_recorder = None
continuous_cleanup = None
ws_clients = []
system_detector = None
video_frame_started_at = 0.0
udp_thread = None
audio_thread = None
inference_thread = None
mic_broadcast_handle = None
shutdown_lock = threading.Lock()
shutdown_started = False

UDP_PORT = 8888
udp_socket = None
phone_addr = None


def dispatch_care_detection(runtime, alerts, new_events, frame_shape=None):
    """Executed by the detection loop; failure cannot replace legacy alerts."""
    if runtime is None:
        return {'mode':'off', 'states':[], 'event_refs':{}, 'record_refs':[]}
    try:
        if frame_shape is not None and runtime.config.personal_baseline_enabled:
            result = runtime.process_frame(alerts, new_events, frame_shape=frame_shape)
        else:
            result = runtime.process_frame(alerts, new_events)
        dispatch_care_audio(result.get('states', []))
        return result
    except Exception as exc:
        print(f'[Care] frame_failed code={type(exc).__name__}')
        return {'mode': 'failed', 'states': [], 'event_refs': {}, 'record_refs': []}


def dispatch_care_audio(steps):
    player = globals().get('care_audio_player')
    if player is not None:
        try:
            player.handle_steps(steps)
        except Exception as exc:
            print(f'[CareAudio] dispatch_failed code={type(exc).__name__}')


def play_intercom_audio(data):
    player = globals().get('care_audio_player')
    if player is not None:
        player.intercom(data)
    else:
        audio_hw.put_audio_frame(data)


def trigger_history_event(cache, kind, alert, care_result, at, runtime=None):
    ref = care_result['event_refs'].get((kind, alert.get('id')))
    if ref is not None:
        result = record_event(cache, ref)
    else:
        result = cache.trigger(kind, at=at, person_id=None if alert.get('id') is None else str(alert['id']),
                               payload={'kind': kind})
    if runtime is not None:
        try:
            runtime.observe_history_result(cache,kind,alert,result)
        except Exception:
            # Private observation cannot fail or re-trigger the real recording.
            pass
    return result


def poll_care_without_observation(runtime):
    global care_last_poll
    if runtime is not None and time.monotonic() - care_last_poll >= 1:
        care_last_poll = time.monotonic()
        try:
            dispatch_care_audio(runtime.tick())
        except Exception as exc:
            print(f'[Care] tick_failed code={type(exc).__name__}')

def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

BOARD_IP = get_host_ip()
TARGET_PORT = 5000

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智护星 · AI 守护管理系统</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Noto+Sans+SC:wght@300;500;700&display=swap" rel="stylesheet">
<style>
:root{
    --brand:#3b82f6;--brand-dark:#1d4ed8;
    --bg:#0f172a;--surface:#1e293b;
    --text:#f8fafc;--muted:#94a3b8;
    --success:#10b981;--danger:#f43f5e;--warning:#f59e0b;
    --border:rgba(255,255,255,0.08);
}
*{margin:0;padding:0;box-sizing:border-box;}
html,body{height:100%;overflow:hidden;}
body{font-family:'Noto Sans SC',sans-serif;background:var(--bg);color:var(--text);display:flex;flex-direction:column;}
header{flex-shrink:0;height:48px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 20px;}
.brand{display:flex;align-items:center;gap:8px;font-weight:700;letter-spacing:1px;color:var(--brand);font-size:14px;}
.hd-info{display:flex;align-items:center;gap:20px;font-size:12px;font-family:'JetBrains Mono';color:var(--muted);line-height:1;}
.hd-info span{display:flex;align-items:center;gap:4px;}
.hd-info b{color:var(--text);}
main{flex:1;min-height:0;display:grid;grid-template-columns:1fr 1fr 1fr;overflow:hidden;}
.col{display:flex;flex-direction:column;padding:12px;gap:10px;min-height:0;overflow:hidden;}
.col-left{border-right:1px solid var(--border);}
.col-mid{border-right:1px solid var(--border);}
.card{background:var(--surface);border-radius:12px;border:1px solid var(--border);padding:12px 14px;flex-shrink:0;}
.card-label{font-size:11px;color:var(--muted);margin-bottom:8px;letter-spacing:.05em;text-transform:uppercase;}
/* 视频 */
.video-box{flex:1;background:#000;border-radius:12px;border:1px solid var(--border);position:relative;overflow:hidden;}
#videoFeed{width:100%;height:100%;object-fit:cover;display:block;}
.cam-tags{position:absolute;top:8px;left:8px;display:flex;gap:6px;z-index:2;}
.tag{background:rgba(0,0,0,0.65);backdrop-filter:blur(4px);padding:3px 8px;border-radius:5px;font-size:11px;font-family:'JetBrains Mono';}
/* 终端 */
.log-box{flex:1;min-height:0;background:rgba(30,41,59,0.6);border-radius:12px;padding:12px 14px;border:1px solid var(--border);overflow-y:auto;font-family:'JetBrains Mono';font-size:12px;}
.log-box::-webkit-scrollbar{width:3px;}
.log-box::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px;}
.log-line{margin-bottom:5px;line-height:1.4;display:flex;gap:8px;}
.log-ts{color:var(--brand);opacity:.6;white-space:nowrap;}
.log-cat{font-weight:700;min-width:58px;}
/* 状态徽章 */
.status-badge{display:inline-block;padding:5px 14px;border-radius:7px;font-size:20px;font-weight:700;margin-bottom:8px;}
.status-badge.ok{background:rgba(16,185,129,0.15);color:var(--success);}
.status-badge.danger{background:rgba(244,63,94,0.15);color:var(--danger);}
.status-badge.warn{background:rgba(245,158,11,0.15);color:var(--warning);}
.stat-sub{display:flex;gap:16px;font-size:11px;color:var(--muted);}
.stat-sub b{color:var(--brand);}
/* 数据统计三列 */
.stats-grid{display:flex;align-items:center;}
.stats-item{flex:1;text-align:center;padding:6px 0;}
.stats-val{font-size:26px;font-weight:700;font-family:'JetBrains Mono';}
.stats-lbl{font-size:11px;color:var(--muted);margin-top:3px;}
.stats-sep{width:1px;height:44px;background:var(--border);flex-shrink:0;}
/* 置信度 */
.kpt-card{flex:1;min-height:130px;max-height:240px;display:flex;flex-direction:column;}
.kpt-title{font-size:11px;color:var(--muted);margin-bottom:6px;letter-spacing:.04em;text-transform:uppercase;}
.kpt-bars{flex:1;display:flex;flex-direction:column;justify-content:space-evenly;}
.kpt-row{display:flex;align-items:center;gap:6px;font-size:11px;}
.kpt-name{width:36px;color:var(--muted);font-family:'JetBrains Mono';}
.kpt-bar-wrap{flex:1;height:4px;background:#1e3a5f;border-radius:2px;overflow:hidden;}
.kpt-bar{height:100%;background:var(--brand);border-radius:2px;transition:width .4s;}
.kpt-score{width:28px;text-align:right;color:var(--muted);font-family:'JetBrains Mono';}
/* 人脸 */
.face-card{flex-shrink:0;}
.face-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);}
.face-row:last-child{border-bottom:none;}
.face-avatar{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;}
.face-name{font-size:12px;font-weight:700;}
.face-sub{font-size:10px;color:var(--muted);}
.face-conf{font-size:11px;font-weight:700;margin-left:auto;font-family:'JetBrains Mono';}
/* 右栏 */
.right-col{display:flex;flex-direction:column;gap:10px;padding:12px;overflow:hidden;min-height:0;}
.call-card{flex:1;display:flex;flex-direction:column;min-height:0;}
.card-title{font-size:12px;color:var(--muted);margin-bottom:10px;letter-spacing:.05em;text-transform:uppercase;}
.alert-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px;}
.alert-row:last-child{border-bottom:none;padding-bottom:0;}
.alert-key{color:var(--muted);}
.alert-val{font-weight:600;}
/* 音频可视化 */
.audio-vis{display:flex;align-items:flex-end;gap:3px;height:48px;justify-content:center;margin:10px 0 8px;}
.av-bar{width:5px;border-radius:3px;background:var(--brand);height:4px;transition:background .3s;}
.audio-vis.active .av-bar:nth-child(1){animation:av1 .72s ease-in-out infinite;}
.audio-vis.active .av-bar:nth-child(2){animation:av2 .88s ease-in-out infinite .08s;}
.audio-vis.active .av-bar:nth-child(3){animation:av3 .64s ease-in-out infinite .16s;}
.audio-vis.active .av-bar:nth-child(4){animation:av4 .80s ease-in-out infinite .24s;}
.audio-vis.active .av-bar:nth-child(5){animation:av5 .68s ease-in-out infinite .12s;}
.audio-vis.active .av-bar:nth-child(6){animation:av6 .92s ease-in-out infinite .04s;}
.audio-vis.active .av-bar:nth-child(7){animation:av7 .76s ease-in-out infinite .20s;}
@keyframes av1{0%,100%{height:6px}50%{height:38px}}
@keyframes av2{0%,100%{height:14px}50%{height:26px}}
@keyframes av3{0%,100%{height:22px}50%{height:10px}}
@keyframes av4{0%,100%{height:8px}50%{height:44px}}
@keyframes av5{0%,100%{height:18px}50%{height:12px}}
@keyframes av6{0%,100%{height:4px}50%{height:32px}}
@keyframes av7{0%,100%{height:26px}50%{height:8px}}
.call-status{font-size:11px;color:var(--muted);text-align:center;margin-bottom:6px;min-height:16px;}
.btn{width:100%;padding:11px;border:none;border-radius:10px;font-weight:700;font-size:13px;cursor:pointer;font-family:'Noto Sans SC',sans-serif;display:flex;align-items:center;justify-content:center;gap:6px;transition:all .2s;}
.btn:disabled{opacity:.35;cursor:not-allowed;}
.btn-blue{background:var(--brand);color:#fff;}
.btn-blue:hover:not(:disabled){background:var(--brand-dark);transform:translateY(-1px);}
.btn-red{background:rgba(244,63,94,.12);color:var(--danger);border:1px solid rgba(244,63,94,.25);}
.vol-row{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin:10px 0 4px;}
.call-hint{font-size:10px;color:rgba(148,163,184,0.5);line-height:1.5;margin-top:auto;padding-top:10px;border-top:1px solid var(--border);}
.si-row{display:flex;justify-content:space-between;font-size:12px;padding:7px 0;border-bottom:1px solid var(--border);}
.si-row:last-child{border-bottom:none;}
.si-k{color:var(--muted);}
.si-v{font-weight:500;}
.si-v.ok{color:var(--success);}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px;}
.dot-green{background:var(--success);box-shadow:0 0 6px var(--success);}
.dot-pulse{animation:pulse-dot 2s infinite;}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:.3}}
/* 关怀：延续监护台深色系统，以真实状态和提醒正文为中心。 */
:root{--care:#5ee3c1;--care-ink:#b7f5e5;--muted:#a8b6cc;}
button:focus-visible,summary:focus-visible{outline:2px solid var(--care);outline-offset:4px;}
::selection{background:#245981;color:#fff;}
.col-mid,.right-col{overflow-y:auto;scrollbar-width:thin;scrollbar-color:#475569 transparent;}
.care-card{padding:18px;}
.care-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;}
.care-head h2{font-size:15px;line-height:1.4;font-weight:700;}
.care-mode{font-size:11px;padding:4px 8px;border-radius:5px;background:#334155;color:#d7e0ed;white-space:nowrap;}
.care-mode.on{background:#123f3b;color:var(--care);}
.care-mode.issue{background:#49351e;color:#ffce8b;}
.care-title{font-size:23px;font-weight:700;line-height:1.4;margin-bottom:8px;letter-spacing:-.02em;}
.care-copy{font-size:12px;line-height:1.8;color:var(--muted);max-width:65ch;}
.care-people{display:grid;gap:0;margin-top:14px;}
.care-person{padding:12px 0;border-top:1px solid var(--border);}
.care-person-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:6px;}
.care-person-name{font-size:14px;font-weight:700;overflow-wrap:anywhere;}
.care-person-time{font-size:12px;color:var(--care-ink);white-space:nowrap;font-variant-numeric:tabular-nums;}
.care-message{font-size:16px;line-height:1.65;overflow-wrap:anywhere;color:#e9fff7;}
.care-person-meta{font-size:11px;line-height:1.8;color:var(--muted);margin-top:6px;}
.care-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:18px;padding-top:12px;border-top:1px solid var(--border);}
.care-updated{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums;}
.care-refresh{border:1px solid #52657f;border-radius:7px;padding:7px 11px;background:transparent;color:var(--text);font:inherit;font-size:11px;cursor:pointer;min-height:34px;}
.care-refresh:hover{background:#334155;}
.care-refresh:disabled{opacity:.6;cursor:wait;}
.care-note{font-size:10px;line-height:1.7;color:var(--muted);margin-top:10px;}
@media(min-width:1100px){main{grid-template-columns:minmax(0,1.12fr) minmax(0,1fr) minmax(0,.88fr);}}
@media(max-width:900px){
 html,body{height:auto;min-height:100%;overflow:auto;}
 header{height:auto;min-height:56px;gap:12px;flex-wrap:wrap;padding:14px 16px;}
 .hd-info{gap:12px;flex-wrap:wrap;line-height:1.5;font-size:10px;}
 main{display:grid;grid-template-columns:1fr 1fr;overflow:visible;}
 .col,.right-col{overflow:visible;min-width:0;}
 .col-mid{grid-column:2;grid-row:1 / span 2;}
 .right-col{grid-column:1;}
 .video-box{flex:none;aspect-ratio:4/3;min-height:180px;}
 .log-box{flex:none;max-height:180px;min-height:100px;}
 .call-card{flex:none;}.call-hint{padding-top:14px;}
}
@media(max-width:600px){
 main{display:flex;flex-direction:column;}.col-mid{order:1;}.col-left{order:0;}.right-col{order:2;}
 .col-left,.col-mid{border-right:0;}.col,.right-col{padding:10px 14px;gap:12px;}
 .col-left .log-box{display:none;}.video-box{aspect-ratio:16/10;min-height:0;}
 .care-card{padding:18px;}.care-title{font-size:24px;}
 .care-refresh{min-height:44px;padding:8px 14px;}
 .btn{min-height:44px;}.card-label,.card-title{font-size:12px;}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;}}
</style>
</head>
<body>
<header>
    <div class="brand">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        智护星 · AI GUARDIAN
    </div>
    <div class="hd-info">
        <span>Uptime: <b id="uptime">00:00:00</b></span>
        <span>NPU: <b style="color:var(--success)">在线</b></span>
        <span>Stream: <b id="hd-stream" style="color:var(--warning)">启动中</b></span>
        <span>FPS: <b id="hd-fps">--</b></span>
    </div>
</header>

<main>

<!-- ── 左栏：视频 + 终端 ── -->
<div class="col col-left">
    <div class="video-box">
        <div class="cam-tags">
            <div class="tag" style="color:var(--success)">● REC</div>
            <div class="tag" id="fps_tag">FPS: --</div>
            <div class="tag">POSE_ENG_V4</div>
        </div>
        <img id="videoFeed" alt="">
    </div>
    <div class="log-box" id="logBox">
        <div class="log-line">
            <span class="log-ts">--:--:--</span>
            <span class="log-cat" style="color:var(--brand)">[SYS]</span>
            <span style="color:var(--muted)">系统初始化中...</span>
        </div>
    </div>
</div>

<!-- ── 中栏：状态 → 数据统计 → 置信度 → 人脸 ── -->
<div class="col col-mid">
    <section class="card care-card" aria-labelledby="care-heading">
        <div class="care-head"><h2 id="care-heading">关怀提醒</h2><span id="care-mode" class="care-mode">连接中</span></div>
        <div id="care-announcement" role="status" aria-live="polite" aria-atomic="true">
            <div id="care-title" class="care-title">正在读取关怀状态</div>
            <p id="care-copy" class="care-copy">连接设备后，将显示当前人员的关怀进度。</p>
        </div>
        <div id="care-people" class="care-people"></div>
        <div class="care-footer"><span id="care-updated" class="care-updated">等待设备数据</span><button id="care-refresh" class="care-refresh" type="button">刷新状态</button></div>
        <p class="care-note">打开本页面不会开启关怀。提醒已触发不等于语音已播放。</p>
    </section>
    <!-- 检测状态 -->
    <div class="card">
        <div class="card-label">当前检测状态</div>
        <div class="status-badge ok" id="det-status">正常</div>
        <div class="stat-sub">
            <span>检测人数 <b id="det-persons">--</b></span>
            <span>推理 <b id="det-fps2">--</b> fps</span>
        </div>
    </div>

    <!-- 数据统计（替代久坐磁贴） -->
    <div class="card">
        <div class="card-label">数据统计</div>
        <div class="stats-grid">
            <div class="stats-item">
                <div class="stats-val" id="s-fall" style="color:var(--danger);">0</div>
                <div class="stats-lbl">摔倒</div>
            </div>
            <div class="stats-sep"></div>
            <div class="stats-item">
                <div class="stats-val" id="s-sit" style="color:var(--warning);">0</div>
                <div class="stats-lbl">久坐</div>
            </div>
            <div class="stats-sep"></div>
            <div class="stats-item">
                <div class="stats-val" id="s-stranger" style="color:#a855f7;">0</div>
                <div class="stats-lbl">陌生人</div>
            </div>
        </div>
    </div>

    <!-- 关键点置信度 -->
    <div class="card kpt-card">
        <div class="kpt-title">关键点置信度</div>
        <div class="kpt-bars">
            <div class="kpt-row"><span class="kpt-name">头部</span><div class="kpt-bar-wrap"><div class="kpt-bar" id="kpt-head" style="width:0%"></div></div><span class="kpt-score" id="kpt-head-v">--</span></div>
            <div class="kpt-row"><span class="kpt-name">肩部</span><div class="kpt-bar-wrap"><div class="kpt-bar" id="kpt-shoulder" style="width:0%"></div></div><span class="kpt-score" id="kpt-shoulder-v">--</span></div>
            <div class="kpt-row"><span class="kpt-name">髋部</span><div class="kpt-bar-wrap"><div class="kpt-bar" id="kpt-hip" style="width:0%"></div></div><span class="kpt-score" id="kpt-hip-v">--</span></div>
            <div class="kpt-row"><span class="kpt-name">膝部</span><div class="kpt-bar-wrap"><div class="kpt-bar" id="kpt-knee" style="width:0%"></div></div><span class="kpt-score" id="kpt-knee-v">--</span></div>
            <div class="kpt-row"><span class="kpt-name">踝部</span><div class="kpt-bar-wrap"><div class="kpt-bar" id="kpt-ankle" style="width:0%"></div></div><span class="kpt-score" id="kpt-ankle-v">--</span></div>
        </div>
    </div>

    <!-- 人脸识别（动态多人，底部） -->
    <div class="card face-card">
        <div class="card-label">人脸识别</div>
        <div style="color:var(--muted);font-size:11px;padding:4px 0;">上传不同方向的照片，有助于加快识别并提高精度；照片数量不作要求，一张也可登记。</div>
        <div id="face-list">
            <div style="color:var(--muted);font-size:11px;padding:4px 0;">无检测对象</div>
        </div>
    </div>
</div>

<!-- ── 右栏：设备状态 + 语音对讲(flex:1) + 系统信息 ── -->
<div class="right-col">
    <!-- 设备状态（原告警统计，删掉三个告警行） -->
    <div class="card">
        <div class="card-title">📡 设备状态</div>
        <div class="alert-row"><span class="alert-key">连续监测时长</span><span class="alert-val" id="r-uptime">00:00:00</span></div>
        <div class="alert-row"><span class="alert-key">累计处理帧数</span><span class="alert-val" id="r-frames">0</span></div>
        <div class="alert-row"><span class="alert-key">平均推理帧率</span><span class="alert-val" id="r-fps" style="color:var(--brand)">-- fps</span></div>
    </div>

    <!-- 语音对讲（flex:1 撑满中间空间） -->
    <div class="card call-card">
        <div class="card-title">🎙️ 语音对讲</div>
        <!-- 音频可视化（通话时动） -->
        <div class="audio-vis" id="audio-vis">
            <div class="av-bar"></div><div class="av-bar"></div><div class="av-bar"></div>
            <div class="av-bar"></div><div class="av-bar"></div><div class="av-bar"></div>
            <div class="av-bar"></div>
        </div>
        <div class="call-status" id="call-status">待机中</div>
        <button id="startBtn" class="btn btn-blue" onclick="startCall()">📞 开始通话</button>
        <button id="endBtn" class="btn btn-red" onclick="endCall()" style="display:none;margin-top:8px;">✕ 结束通话</button>
        <div class="vol-row"><span>本声道增益</span><span id="vol_val">85%</span></div>
        <input type="range" style="width:100%;accent-color:var(--brand)" min="0" max="100" value="85"
            oninput="document.getElementById('vol_val').innerText=this.value+'%'">
        <div style="margin-top:8px;font-size:11px;color:var(--muted);line-height:1.6;">
            麦克风：<span id="mic-status">未启动</span> &nbsp;|&nbsp; 远程：<span id="remote-status">等待连接</span>
        </div>
        <div class="call-hint">
            提示：如无法启动麦克风，请在浏览器地址栏输入<br>
            <span style="color:var(--brand);font-family:'JetBrains Mono';font-size:9px;">chrome://flags</span>
            并将 <span style="color:var(--brand);font-family:'JetBrains Mono';font-size:9px;">Insecure origins treated as secure</span> 设为启用。
        </div>
    </div>

    <!-- 系统信息（贴底，不撑大） -->
    <div class="card" style="flex-shrink:0;">
        <div class="card-title">⚙️ 系统信息</div>
        <div class="si-row"><span class="si-k">硬件平台</span><span class="si-v">香橙派 AIpro（昇腾 310B4）</span></div>
        <div class="si-row"><span class="si-k">推理框架</span><span class="si-v">AscendCL · ACLLite</span></div>
        <div class="si-row"><span class="si-k">检测模型</span><span class="si-v">YOLOv8-Pose .om</span></div>
        <div class="si-row"><span class="si-k">通信协议</span><span class="si-v">MQTT · WebSocket</span></div>
        <div class="si-row"><span class="si-k">App 平台</span><span class="si-v">HarmonyOS NEXT</span></div>
        <div class="si-row"><span class="si-k">视频流</span><span class="si-v ok"><span class="dot dot-green dot-pulse"></span>MJPEG 流</span></div>
    </div>
</div>

</main>

<script>
// 以服务端 uptime_seconds 为准，拿到之前先按页面打开时间计
let startTs = Date.now();
function fmtTime(ms){
    const s=Math.floor(ms/1000);
    return String(Math.floor(s/3600)).padStart(2,'0')+':'+
           String(Math.floor((s%3600)/60)).padStart(2,'0')+':'+
           String(s%60).padStart(2,'0');
}
setInterval(()=>{
    const t=fmtTime(Date.now()-startTs);
    document.getElementById('uptime').textContent=t;
    document.getElementById('r-uptime').textContent=t;
},1000);

function addLog(cat,msg,color='var(--muted)'){
    const c=document.getElementById('logBox');
    const d=document.createElement('div');
    d.className='log-line';
    const ts=new Date().toLocaleTimeString('zh-CN',{hour12:false});
    d.innerHTML=`<span class="log-ts">${ts}</span><span class="log-cat" style="color:${color}">[${cat}]</span><span style="color:var(--muted)">${msg}</span>`;
    c.appendChild(d);
    while(c.children.length>80)c.removeChild(c.firstChild);
    c.scrollTop=c.scrollHeight;
}

const videoEl=document.getElementById('videoFeed');
let streamOk=false;
function setStreamOk(ok){
    if(ok===streamOk)return;
    streamOk=ok;
    const el=document.getElementById('hd-stream');
    el.textContent=ok?'运行中':'重连中';
    el.style.color=ok?'var(--success)':'var(--warning)';
    addLog('VIDEO',ok?'视频流连接成功':'视频流断开，重连中...',ok?'var(--success)':'var(--warning)');
}
// 用 fetch 逐帧读 MJPEG：<img src> 断流后不会自己恢复；超过 6 秒无新帧就断开重连。
(function(){
    let ctrl=null,last=0,shown=null,pending=false;
    const find=(b,m,from)=>{for(let i=from;i<b.length-1;i++){if(b[i]===255&&b[i+1]===m)return i;}return -1;};
    const show=bytes=>{
        last=Date.now();
        const url=URL.createObjectURL(new Blob([bytes],{type:'image/jpeg'}));
        const old=shown;shown=url;videoEl.src=url;
        if(old)setTimeout(()=>URL.revokeObjectURL(old),1000);
        setStreamOk(true);
    };
    const retry=()=>{if(pending)return;pending=true;setStreamOk(false);setTimeout(()=>{pending=false;run();},2000);};
    async function run(){
        const c=ctrl=new AbortController();last=Date.now();
        try{
            const r=await fetch('/video_feed?t='+Date.now(),{cache:'no-store',signal:c.signal});
            if(!r.ok||!r.body)throw new Error('http '+r.status);
            const rd=r.body.getReader();let buf=new Uint8Array(0);
            for(;;){
                const x=await rd.read();if(x.done)break;
                const nb=new Uint8Array(buf.length+x.value.length);nb.set(buf);nb.set(x.value,buf.length);buf=nb;
                for(;;){
                    const s=find(buf,216,0);
                    if(s<0){buf=buf.slice(Math.max(0,buf.length-1));break;}
                    const e=find(buf,217,s+2);
                    if(e<0){if(s>0)buf=buf.slice(s);break;}
                    show(buf.slice(s,e+2));buf=buf.slice(e+2);
                }
            }
        }catch(_){}
        if(c===ctrl)retry();
    }
    setInterval(()=>{if(ctrl&&!pending&&Date.now()-last>6000){const c=ctrl;ctrl=null;c.abort();retry();}},1000);
    run();
})();

// 人脸日志限频：每个标签独立计时，2分钟内只记录一次
const _faceLogTimes={};
function canLogFace(key){
    const now=Date.now();
    if(!_faceLogTimes[key]||now-_faceLogTimes[key]>120000){
        _faceLogTimes[key]=now;
        return true;
    }
    return false;
}

let _lastSitLog=0;

async function fetchStats(){
    if(fetchStats.pending)return;
    fetchStats.pending=true;
    const refresh=document.getElementById('care-refresh');
    refresh.disabled=true;
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),5000);
    try{
        const r=await fetch('/api/stats',{cache:'no-store',signal:controller.signal});
        if(!r.ok)throw new Error('stats_unavailable');
        const d=await r.json();
        renderCare(d.care);

        // 检测状态
        const st=d.status||'正常';
        const el=document.getElementById('det-status');
        el.textContent=st;
        el.className='status-badge '+(st.includes('摔倒')?'danger':st.includes('久坐')?'warn':'ok');
        document.getElementById('det-persons').textContent=d.detections!=null?d.detections:'--';
        if(d.uptime_seconds!=null)startTs=Date.now()-d.uptime_seconds*1000;
        const fps=d.fps??0;
        if(fps>0){
            const fpsStr=fps.toFixed(1);
            document.getElementById('det-fps2').textContent=fpsStr;
            document.getElementById('r-fps').textContent=fpsStr+' fps';
            document.getElementById('hd-fps').textContent=fpsStr;
            document.getElementById('fps_tag').textContent='FPS: '+fpsStr;
        } else {
            document.getElementById('det-fps2').textContent='--';
            document.getElementById('r-fps').textContent='-- fps';
            document.getElementById('hd-fps').textContent='--';
            document.getElementById('fps_tag').textContent='FPS: --';
        }

        // 设备状态
        if(d.frame_count!=null){
            document.getElementById('r-frames').textContent=d.frame_count.toLocaleString();
            // 首次有帧数据时在终端提示模型加载完成
            if(d.frame_count>0&&!window._inferStarted){
                window._inferStarted=true;
                addLog('NPU','推理引擎已就绪，开始处理视频流','var(--success)');
            }
        }
        // 模型加载提示（只提示一次）
        if(d.frame_count===0&&streamOk&&!window._loadingLogged){
            window._loadingLogged=true;
            addLog('NPU','模型加载中，请稍候...','var(--warning)');
        }

        // 数据统计三列
        document.getElementById('s-fall').textContent=d.fall_count??0;
        document.getElementById('s-sit').textContent=d.sit_count??0;
        document.getElementById('s-stranger').textContent=d.stranger_count??0;

        // 摔倒事件日志
        if(d.last_fall_time&&d.last_fall_time!==window._lastFallTime){
            window._lastFallTime=d.last_fall_time;
            addLog('摔倒','⚠ 检测到摔倒！已上报 MQTT','var(--danger)');
        }

        // 久坐日志（2分钟内最多一条）
        const sitDur=d.sit_duration??0;
        if(sitDur>0){
            const now=Date.now();
            if(now-_lastSitLog>120000){
                _lastSitLog=now;
                // sit_duration 单位是分钟，阈值只有 10 秒，不足 1 分钟按秒显示
                const sitTxt=sitDur>=1?Math.floor(sitDur)+' 分钟':Math.round(sitDur*60)+' 秒';
                addLog('久坐','连续静止 '+sitTxt,'var(--warning)');
            }
        }

        // 关键点置信度
        if(d.keypoint_scores){
            const ks=d.keypoint_scores;
            function setKpt(id,val){
                const pct=Math.round((val||0)*100);
                document.getElementById('kpt-'+id).style.width=pct+'%';
                document.getElementById('kpt-'+id+'-v').textContent=(val||0).toFixed(2);
                document.getElementById('kpt-'+id).style.background=pct<40?'var(--warning)':'var(--brand)';
            }
            setKpt('head',ks.head);setKpt('shoulder',ks.shoulder);
            setKpt('hip',ks.hip);setKpt('knee',ks.knee);setKpt('ankle',ks.ankle);
        }

        // 人脸识别：多人动态渲染
        const faces=d.faces||[];
        const faceList=document.getElementById('face-list');
        faceList.innerHTML='';
        if(faces.length===0){
            faceList.innerHTML='<div style="color:var(--muted);font-size:11px;padding:4px 0;">无检测对象</div>';
        } else {
            faces.forEach(f=>{
                const raw=f.label||'pending';
                const isStranger=raw==='stranger';
                const isKnown=raw.startsWith('known:');
                const name=isKnown?raw.slice(6):(isStranger?'陌生人':'等待识别');
                const score=(f.score??0).toFixed(2);
                const avatarBg=isStranger?'rgba(244,63,94,0.15)':(isKnown?'rgba(16,185,129,0.15)':'rgba(148,163,184,0.12)');
                const avatarColor=isStranger?'var(--danger)':(isKnown?'var(--success)':'var(--muted)');
                const nameColor=isStranger?'var(--danger)':'var(--text)';
                const confColor=isStranger?'var(--danger)':'var(--brand)';
                const avatarChar=isKnown?name.charAt(0):(isStranger?'?':'·');
                const reasons={too_dark:'光线不足',overexposed:'光线过强',low_contrast:'人脸细节不足',blurred:'画面模糊',landmarks_unavailable:'关键区域不清晰',no_face:'等待清晰人脸',low_light:'弱光处理中'};
                const waitText=f.timeout_seconds>0?`（${Math.floor(f.wait_seconds||0)}/${Math.ceil(f.timeout_seconds)}秒）`:'';
                const subText=isStranger?(f.reason==='timeout'?'识别超时，暂列陌生人':'未匹配登记人员'):(isKnown?'已登记人员':((reasons[f.reason]||'等待识别结果')+waitText));
                const showConf=(isKnown||isStranger)&&f.score!=null;
                const row=document.createElement('div');
                row.className='face-row';
                row.innerHTML=
                    `<div class="face-avatar" style="background:${avatarBg};color:${avatarColor};">${avatarChar}</div>`+
                    `<div><div class="face-name" style="color:${nameColor};">${name}</div><div class="face-sub">${subText}</div></div>`+
                    `<div style="text-align:right;"><div style="font-size:9px;color:var(--muted);margin-bottom:1px;">匹配分数</div>`+
                    `<div class="face-conf" style="color:${confColor};">${showConf?score:'--'}</div></div>`;
                faceList.appendChild(row);
                // 日志：每标签2分钟限频
                if(canLogFace(raw)){
                    if(isStranger) addLog('人脸','检测到陌生人！已上报','var(--danger)');
                    else if(isKnown) addLog('人脸','识别到：'+name+' ('+score+')','var(--success)');
                }
            });
        }
    }catch(e){renderCare(null,true);}
    finally{clearTimeout(timeout);fetchStats.pending=false;refresh.disabled=false;}
}
function renderCare(care,disconnected=false){
    const setText=(el,value)=>{if(el.textContent!==value)el.textContent=value;};
    const mode=document.getElementById('care-mode');
    const title=document.getElementById('care-title');
    const copy=document.getElementById('care-copy');
    const people=document.getElementById('care-people');
    const updated=document.getElementById('care-updated');
    people.replaceChildren();
    mode.className='care-mode';
    if(disconnected||!care||!['off','shadow','live'].includes(care.mode)){
        mode.textContent=disconnected?'连接中断':'状态待确认';mode.classList.add('issue');
        setText(title,disconnected?'暂时无法读取设备':'关怀状态暂不可用');
        setText(copy,disconnected?'连接恢复后会自动更新，也可以点击刷新重试。':'当前设备未返回有效关怀状态，请稍后刷新。');
        updated.textContent='未取得最新状态';return;
    }
    updated.textContent='已更新 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});
    if(care.mode==='off'){
        mode.textContent='已关闭';setText(title,'关怀暂未开启');
        setText(copy,'实时监测仍可查看。开启关怀后，这里会显示已识别人员的累计时长和提醒。');return;
    }
    mode.textContent=care.mode==='shadow'?'演示模式':'关怀已开启';mode.classList.add('on');
    const rows=Array.isArray(care.people)?care.people:[];
    setText(title,rows.length&&rows.every(p=>p.uncertainty_reason)?'当前计时已暂停':rows.some(p=>p.reminder)?'该起来活动一下了':rows.length?'正在关注久坐状态':'等待已识别人员入镜');
    setText(copy,rows.length?(care.audio_available?'语音通道可用；对讲时优先播放对讲声音。':'当前仅显示提醒，未启用关怀语音。'):'面部可识别后开始展示，无需画面中只有一人。');
    const phases={IDLE:'等待坐姿',SITTING:'正在累计',L0:'温和提醒',L1:'再次提醒',EXHAUSTED:'本轮提醒已完成',ACK:'已确认，稍后再关怀'};
    rows.forEach(p=>{
        const row=document.createElement('article');row.className='care-person';
        const head=document.createElement('div');head.className='care-person-head';
        const name=document.createElement('span');name.className='care-person-name';name.textContent=p.name;
        const time=document.createElement('span');time.className='care-person-time';
        const seconds=Math.max(0,Math.floor(Number(p.seated_seconds)||0));
        time.textContent='累计 '+(seconds>=60?Math.floor(seconds/60)+' 分 '+seconds%60+' 秒':seconds+' 秒');
        head.append(name,time);row.append(head);
        if(p.reminder){const text=document.createElement('p');text.className='care-message';text.textContent=p.reminder.text||'请起身活动一下';row.append(text);}
        const meta=document.createElement('p');meta.className='care-person-meta';
        meta.textContent=(p.uncertainty_reason?'计时已暂停':phases[p.phase]||'正在监测')+' · 温和提醒 '+(p.counts?.L0||0)+' 次 · 再次提醒 '+(p.counts?.L1||0)+' 次';
        row.append(meta);people.append(row);
    });
}
document.getElementById('care-refresh').addEventListener('click',fetchStats);
setInterval(fetchStats,800);fetchStats();

let ws,audioCtx,scriptNode,micSource;
const SAMPLE_RATE=48000;

async function startCall(){
    try{
        addLog('通话','正在开启本地麦克风...','var(--brand)');
        audioCtx=new(window.AudioContext||window.webkitAudioContext)({sampleRate:SAMPLE_RATE});
        const stream=await navigator.mediaDevices.getUserMedia({audio:true});
        addLog('通话','正在连接语音通道...','var(--brand)');
        const proto=window.location.protocol==='https:'?'wss':'ws';
        ws=new WebSocket(proto+'://'+window.location.host+'/ws/intercom');
        ws.binaryType='arraybuffer';
        ws.onopen=()=>{
            addLog('通话','通话已建立','var(--success)');
            document.getElementById('startBtn').style.display='none';
            document.getElementById('endBtn').style.display='flex';
            document.getElementById('mic-status').textContent='工作中';
            document.getElementById('remote-status').textContent='在线';
            document.getElementById('call-status').textContent='通话中';
            document.getElementById('audio-vis').classList.add('active');
            micSource=audioCtx.createMediaStreamSource(stream);
            scriptNode=audioCtx.createScriptProcessor(2048,1,1);
            micSource.connect(scriptNode);scriptNode.connect(audioCtx.destination);
            scriptNode.onaudioprocess=(e)=>{
                if(ws.readyState===WebSocket.OPEN)
                    ws.send(floatTo16BitPCM(e.inputBuffer.getChannelData(0)));
            };
        };
        ws.onmessage=(e)=>playPcm(e.data);
        ws.onclose=()=>{addLog('通话','通话已结束','var(--muted)');endCall();};
        ws.onerror=()=>addLog('通话','WebSocket 错误','var(--danger)');
    }catch(err){
        addLog('通话','启动失败: '+err.message,'var(--danger)');
    }
}
function endCall(){
    if(ws)ws.close();
    if(micSource)micSource.disconnect();
    if(scriptNode)scriptNode.disconnect();
    if(audioCtx)audioCtx.close();
    document.getElementById('startBtn').style.display='flex';
    document.getElementById('endBtn').style.display='none';
    document.getElementById('mic-status').textContent='未启动';
    document.getElementById('remote-status').textContent='等待连接';
    document.getElementById('call-status').textContent='待机中';
    document.getElementById('audio-vis').classList.remove('active');
    addLog('通话','通话频道已释放','var(--muted)');
}
function playPcm(buf){
    if(!audioCtx)return;
    const i16=new Int16Array(buf),f32=new Float32Array(i16.length);
    for(let i=0;i<i16.length;i++)f32[i]=i16[i]/32768.0;
    const ab=audioCtx.createBuffer(1,f32.length,SAMPLE_RATE);
    ab.getChannelData(0).set(f32);
    const n=audioCtx.createBufferSource();n.buffer=ab;
    n.connect(audioCtx.destination);n.start();
}
function floatTo16BitPCM(inp){
    const out=new Int16Array(inp.length);
    for(let i=0;i<inp.length;i++){const s=Math.max(-1,Math.min(1,inp[i]));out[i]=s<0?s*0x8000:s*0x7FFF;}
    return out.buffer;
}
</script>
</body>
</html>"""

# ==========================================
# 后端路由
# ==========================================

@app.get("/")
async def get_index():
    return HTMLResponse(content=HTML_CONTENT)


def camera_video_is_live():
    return (system_detector is not None and system_detector.camera_is_live()
            and video_frame_started_at >= system_detector.camera_connected_since
            and time.monotonic() - video_frame_started_at < 3.0)


@app.get("/api/stats")
async def api_stats():
    s = dict(video_hw.get_stats())
    camera_connected = system_detector is not None and system_detector.camera_is_live()
    if not camera_video_is_live():
        s.update(fps=0.0, detections=0, status="摄像头离线" if not camera_connected else "等待新画面",
                 keypoint_scores=None, face_label=None, face_score=None, faces=[], sit_duration=0)
    elif (not system_detector.inference_enabled
          or time.monotonic() - system_detector.last_successful_inference_at > 3.0):
        s.update(fps=0.0, detections=0,
                 status="推理已暂停" if not system_detector.inference_enabled else "等待有效推理",
                 keypoint_scores=None, face_label=None, face_score=None, faces=[], sit_duration=0)
    return JSONResponse({
        "camera_connected": camera_connected,
        "fps":             s["fps"],
        "detections":      s["detections"],
        "fall_count":      s["fall_count"],
        "status":          s["status"],
        "mqtt_connected":  s["mqtt_connected"],
        "uptime_seconds":  int(time.monotonic() - s["start_time"]),
        "last_fall_time":  s.get("last_fall_time"),
        "keypoint_scores": s.get("keypoint_scores"),
        "frame_count":     s.get("frame_count", 0),
        "sit_duration":    s.get("sit_duration", 0),
        "sit_count":       s.get("sit_count", 0),
        "stranger_count":  s.get("stranger_count", 0),
        "face_label":      s.get("face_label"),   # 向后兼容
        "face_score":      s.get("face_score"),   # 向后兼容
        "faces":           s.get("faces", []),    # 多人人脸数组
        "care": care_display_snapshot(care_runtime, s.get("faces", []), care_audio_player is not None,
                                      initialization_failed=care_initialization_failed),
    })


def care_display_snapshot(runtime, faces, audio_available, initialization_failed=False):
    """Current public display only: no private IDs, history, tokens or mutation."""
    if runtime is None:
        return {'mode': 'unavailable' if initialization_failed else 'off', 'audio_available': False, 'people': []}
    try:
        people, seen = [], set()
        messages = runtime.shadow_broadcasts() if runtime.config.mode == 'shadow' else []
        for face in faces:
            label = face.get('label', '')
            if not label.startswith('known:'):
                continue
            name = label[6:]
            identity = runtime.config.face_label_ids.get(name, name)
            if identity not in runtime.config.person_ids or identity in seen:
                continue
            seen.add(identity)
            state = runtime.state(identity)
            latest = next((m for m in reversed(messages) if m.get('person_id') == identity), None)
            reminder = None
            if latest and state.get('level') and sum(state.get('counts', {}).values()) > 0:
                reminder = {key: latest.get(key) for key in ('level', 'text', 'wall_time')}
            elif state.get('level') in ('L0', 'L1') and sum(state.get('counts', {}).values()) > 0:
                from sedentary_care import TEXTS
                reminder = dict(level=state['level'], text=TEXTS[state['level']][1], wall_time=None)
            people.append(dict(name=name, state=state.get('state'), phase=state.get('phase'),
                               seated_seconds=state.get('seated_seconds', 0),
                               level=state.get('level'), counts=state.get('counts', {}),
                               uncertainty_reason=state.get('uncertainty_reason'), reminder=reminder))
        return {'mode': runtime.config.mode, 'audio_available': bool(audio_available), 'people': people}
    except Exception:
        return {'mode': 'unavailable', 'audio_available': False, 'people': []}


@app.get("/video_feed")
async def video_feed():
    async def generate():
        last_frame = None
        while True:
            frame_data = video_hw.get_current_frame() if camera_video_is_live() else None
            # 帧去重：只在有新帧时才发送，消除重复帧对 FRP 缓冲的积压
            if frame_data is not None and frame_data is not last_frame:
                last_frame = frame_data
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.04)
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
            "Pragma": "no-cache", "Expires": "0", "X-Accel-Buffering": "no",
        },
    )


@app.get("/video_frame")
async def video_frame():
    frame_data = video_hw.get_current_frame() if camera_video_is_live() else None
    if frame_data:
        return Response(
            content=frame_data, media_type="image/jpeg",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    return Response(status_code=204)


@app.websocket("/ws/intercom")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    print("🎧 WebSocket intercom connected")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data:
                play_intercom_audio(data)
    except WebSocketDisconnect:
        print("🎧 WebSocket intercom disconnected")
    except Exception as e:
        print(f"🎧 WebSocket intercom error: {e}")
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)
        print("🎧 WebSocket intercom closed")


# ==========================================
# 后台任务
# ==========================================

def udp_receive_thread():
    global phone_addr
    print(f"📡 UDP 监听启动: 端口 {UDP_PORT} ...")
    while True:
        try:
            if udp_socket is None:
                break
            data, addr = udp_socket.recvfrom(4096)
            if phone_addr != addr:
                phone_addr = addr
                print(f"🔗 更新连接目标: {addr}")
            if data:
                play_intercom_audio(data)
        except socket.timeout:
            continue
        except Exception as e:
            if udp_socket is None:
                break
            print(f"UDP Error: {e}")
            time.sleep(0.1)


def cleanup_system():
    global system_detector, shutdown_started, udp_socket, heartbeat_publisher
    with shutdown_lock:
        if shutdown_started:
            return
        shutdown_started = True
    if heartbeat_publisher is not None:
        heartbeat_publisher.stop()
        heartbeat_publisher = None
    if system_detector is not None:
        try:
            system_detector.stop()
        except Exception:
            pass
        system_detector = None
    if care_audio_player is not None:
        care_audio_player.close()
    if hasattr(audio_hw, "stop_audio_service"):
        try:
            audio_hw.stop_audio_service()
        except Exception as e:
            print(f"[Shutdown] audio stop failed: {e}")
    if udp_socket is not None:
        udp_to_close = udp_socket
        udp_socket = None
        try:
            udp_to_close.close()
        except OSError:
            pass
    for worker in (audio_thread, udp_thread, inference_thread):
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=3.0)


async def mic_broadcast_task():
    print("🚀 音频广播服务已就绪")
    idle_rounds = 0
    while True:
        frame = audio_hw.get_audio_frame()
        if frame:
            idle_rounds = 0
            dead_clients = []
            for client in list(ws_clients):
                try:
                    await client.send_bytes(frame)
                except Exception:
                    dead_clients.append(client)
            for client in dead_clients:
                if client in ws_clients:
                    ws_clients.remove(client)
            if udp_socket and phone_addr:
                try:
                    udp_socket.sendto(frame, phone_addr)
                except Exception:
                    pass
            # UDP-only delivery has no WebSocket await; yield so HTTP stays responsive.
            await asyncio.sleep(0)
        else:
            idle_rounds += 1
            if idle_rounds % 200 == 0 and ws_clients:
                try:
                    print(f"[Audio] waiting mic frame, status={audio_hw.get_audio_status()}")
                except Exception:
                    print("[Audio] waiting mic frame, status unavailable")
            await asyncio.sleep(0.03)


def run_system():
    global shutdown_started, udp_socket, udp_thread, audio_thread, inference_thread, system_detector, mic_broadcast_handle
    shutdown_started = False

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(1.0)
    udp_socket.bind(('0.0.0.0', UDP_PORT))

    udp_thread = threading.Thread(target=udp_receive_thread, name="guardian-udp", daemon=True)
    udp_thread.start()

    audio_thread = threading.Thread(target=audio_hw.start_audio_service, name="guardian-audio", daemon=True)
    audio_thread.start()

    # Event-triggered clips stay fully disabled unless AI_GUARDIAN_RECORDING_CONFIG
    # enables them; a broken recording setup must never stop detection.
    global history_store, event_cache, cleanup_scheduler, alert_mqtt
    history_store = None
    event_cache = None
    cleanup_scheduler = None
    alert_mqtt = None

    def on_clip_ready(event_ids, recording_id):
        """片段封装完成：MQTT 通知手机可按需下载（下载走 /api/history）。"""
        client = alert_mqtt
        if client is None:
            return
        try:
            client.publish_record_ready(recording_id, event_ids)
        except Exception as exc:
            print(f"[Record] publish_record_ready failed: {type(exc).__name__}")

    try:
        recording_config = RecordingConfig.from_env()
        if recording_config.enabled:
            initialize_storage(recording_config)
            history_store = HistoryStore(recording_config)
            candidate = EventClipCache(recording_config, history_store, create_backend,
                                       on_clip_ready=on_clip_ready)
            if candidate.start():
                event_cache = candidate
                app.include_router(create_history_router(
                    recording_config, store=history_store, recorder=event_cache))
                print("[Record] 历史查询接口已注册 /api/history")
                scheduler = CleanupScheduler(history_store,
                                             recording_config.cleanup_interval_seconds)
                if scheduler.start():
                    cleanup_scheduler = scheduler
                    print("[Record] 七天清理调度已启动")
                else:
                    print("[Record] 清理调度未启动，保留策略不生效")
                print(f"[Record] 事件录像已启用 pre={recording_config.pre_roll_seconds}s "
                      f"post={recording_config.post_roll_seconds}s "
                      f"fps={recording_config.record_fps}")
            else:
                print("[Record] 事件录像缓存未能启动，保持关闭")
        else:
            print("[Record] 事件录像默认关闭")
    except Exception as exc:
        print(f"[Record] 事件录像初始化失败，已跳过: {type(exc).__name__}")
        history_store = None
        event_cache = None
        cleanup_scheduler = None

    global care_runtime, record_event, care_initialization_failed
    care_initialization_failed = False
    try:
        care_runtime = None
        if os.environ.get('AI_GUARDIAN_CARE_CONFIG'):
            from care_runtime import runtime_from_env, record_event
            from care_api import create_care_router
            care_runtime = runtime_from_env()
        if care_runtime is not None:
            care_runtime.recorder = event_cache
            app.include_router(create_care_router(care_runtime))
            print(f'[Care] initialized mode={care_runtime.config.mode}')
    except Exception as exc:
        print(f'[Care] init_failed code={type(exc).__name__}')
        care_initialization_failed = True
        care_runtime = None

    global care_audio_player
    care_audio_player = None
    audio_directory = os.environ.get('AI_GUARDIAN_CARE_AUDIO_DIR')
    demo_audio = os.environ.get('AI_GUARDIAN_CARE_DEMO_AUDIO') == '1'
    if care_runtime is not None and audio_directory and (care_runtime.config.mode == 'live' or demo_audio):
        try:
            from care_audio import CareAudioPlayer
            care_audio_player = CareAudioPlayer(audio_directory, audio_hw.put_audio_frame,
                lambda: bool(getattr(audio_hw, 'get_audio_status', lambda: {})().get('output_enabled')))
            care_audio_player.start()
        except Exception as exc:
            print(f'[CareAudio] init_failed code={type(exc).__name__}')
            care_audio_player = None

    # Continuous video has its own managed root, quota and rolling 24-hour
    # retention. It uses the existing camera capture, never a second opener.
    global continuous_store, continuous_recorder, continuous_cleanup
    continuous_store = continuous_recorder = continuous_cleanup = None
    try:
        continuous_config = RecordingConfig.from_env(
            config_env_var="AI_GUARDIAN_CONTINUOUS_CONFIG")
        if continuous_config.enabled:
            if continuous_config.retention_hours != 24:
                raise ValueError("continuous recording requires 24-hour retention")
            if (history_store is not None and
                    continuous_config.data_root.resolve() == history_store.config.data_root.resolve()):
                raise ValueError("continuous and event recording roots must differ")
            initialize_storage(continuous_config)
            continuous_store = HistoryStore(continuous_config)
            candidate = RecordingManager(continuous_config, continuous_store, create_backend)
            if not candidate.start():
                raise RuntimeError("continuous recorder failed to start")
            continuous_recorder = candidate
            app.include_router(create_history_router(
                continuous_config, store=continuous_store, recorder=continuous_recorder,
                prefix="/api/continuous"))
            continuous_cleanup = CleanupScheduler(
                continuous_store, continuous_config.cleanup_interval_seconds)
            if not continuous_cleanup.start():
                raise RuntimeError("continuous cleanup failed to start")
            print("[Record] 24 小时连续录像已启用 /api/continuous")
    except Exception as exc:
        print(f"[Record] 连续录像初始化失败，已跳过: {type(exc).__name__}")
        if continuous_recorder is not None:
            continuous_recorder.stop(timeout=15)
        if continuous_cleanup is not None:
            continuous_cleanup.stop(timeout=5)
        if continuous_store is not None:
            continuous_store.close()
        continuous_store = continuous_recorder = continuous_cleanup = None

    def inference_loop():
        global system_detector, video_frame_started_at, heartbeat_publisher, care_worker, care_last_poll
        detector = AclLiteStreamDetector(model_path=MODEL_PATH, camera_index=0)
        continuous_sink = None
        if continuous_recorder is not None:
            continuous_sink = ContinuousCaptureSink(
                continuous_recorder, continuous_recorder.config.record_fps)
        # 实时画面直接取摄像头帧（15 帧），叠加最近一次推理的框；推理本身仍按原节奏运行。
        latest_overlay = {"alerts": [], "at": 0.0}

        def on_captured(frame, captured_at, monotonic_at):
            global video_frame_started_at
            if continuous_sink is not None:
                continuous_sink(frame, captured_at, monotonic_at)
            alerts = latest_overlay["alerts"]
            if alerts and monotonic_at - latest_overlay["at"] <= 1.0:
                frame = draw_results(frame.copy(), alerts)
            video_hw.update_frame(frame)
            video_frame_started_at = monotonic_at

        detector.on_captured_frame = on_captured
        system_detector = detector
        mqtt_client = MQTTAlertClient()
        global alert_mqtt
        alert_mqtt = mqtt_client
        heartbeat_publisher = MqttHeartbeatPublisher(
            mqtt_client.client,
            "ai_guardian/alerts/heartbeat",
            "ascend_board",
            lambda: {
                "cameraConnected": detector.camera_is_live(),
                "aiRunning": detector.running and detector.inference_enabled,
            },
            interval_seconds=heartbeat_interval(
                os.environ.get("AI_GUARDIAN_HEARTBEAT_SECONDS", "10")
            ),
        )
        heartbeat_publisher.start()
        _fps_count = 0
        _fps_timer = time.time()
        if care_runtime is not None and care_runtime.config.sync_enabled:
            from care_transport import DeliveryWorker, MqttCareSender
            care_worker = DeliveryWorker(care_runtime, MqttCareSender(mqtt_client.client))
            care_worker.start()
        event_tracker = AlertEpisodeTracker()
        _last_face_label = None

        if detector.init():
            try:
                while detector.running:
                    frame_started_at = time.monotonic()
                    res = detector.get_detected_frame()
                    if (not detector.camera_is_live()
                            or frame_started_at < detector.camera_connected_since):
                        poll_care_without_observation(care_runtime)
                        _fps_count = 0
                        _fps_timer = time.time()
                        time.sleep(0.015)
                        continue
                    if res is None:
                        poll_care_without_observation(care_runtime)
                        time.sleep(0.015)
                        continue

                    frame, alerts = res
                    if detector.last_frame_inferred:
                        latest_overlay["alerts"] = alerts
                        latest_overlay["at"] = time.monotonic()
                    # Raw/throttled frames do not establish an empty or recovered scene.
                    if not detector.last_frame_inferred:
                        poll_care_without_observation(care_runtime)
                        continue
                    # Submit the ANNOTATED frame (inference ran on it): clips keep the
                    # boxes, skeleton and status text so playback shows why an event
                    # fired. Throttled raw frames must NOT enter the ring buffer.
                    if event_cache is not None:
                        try:
                            event_cache.submit_frame(frame, captured_at=time.time(),
                                                     monotonic_at=time.monotonic())
                        except Exception as _cache_exc:
                            print(f"[Record] submit_frame failed: {type(_cache_exc).__name__}")

                    is_fallen = any("FALL" in a.get('status', '') for a in alerts)
                    kpt_scores = None
                    face_label = None
                    face_score = None
                    any_sitting = False
                    max_sit_sec = 0.0
                    faces = []

                    for _a in alerts:
                        _k = _a.get('kpts', [])
                        if len(_k) >= 17 and kpt_scores is None:
                            def _m(k, *i): v=[float(k[x][2]) for x in i if x<len(k)]; return round(sum(v)/len(v),3) if v else 0.0
                            kpt_scores = {"head":_m(_k,0,1,2,3,4),"shoulder":_m(_k,5,6),"hip":_m(_k,11,12),"knee":_m(_k,13,14),"ankle":_m(_k,15,16)}
                        fl = _a.get('face_label')
                        # 向后兼容：取第一个有效人脸
                        if fl and face_label is None:
                            face_label = fl
                            face_score = _a.get('face_score')
                        # Include pending tracks so a detected person shows "等待识别".
                        if fl:
                            faces.append({
                                "label": fl,
                                "score": _a.get('face_score'),
                                "reason": _a.get('face_reason', 'waiting'),
                                "wait_seconds": _a.get('face_wait_seconds', 0.0),
                                "timeout_seconds": _a.get('face_timeout_seconds', 0.0),
                                "person_id": _a.get('id'),
                            })
                        if _a.get('is_sitting'):
                            any_sitting = True
                            d_sec = float(_a.get('sit_duration_sec', 0.0) or 0.0)
                            if d_sec > max_sit_sec:
                                max_sit_sec = d_sec

                    _now = time.time()
                    _fps_count += 1
                    fps_val = None
                    if _now - _fps_timer >= 2.0:
                        fps_val = _fps_count / (_now - _fps_timer)
                        _fps_count = 0
                        _fps_timer = _now

                    if is_fallen:
                        status_text = "摔倒检测！"
                    elif any_sitting:
                        status_text = "久坐告警！"
                    else:
                        status_text = "正常"

                    video_hw.update_stats(
                        detections=len(alerts),
                        status=status_text,
                        fps=fps_val,
                        keypoint_scores=kpt_scores,
                        frame_count_inc=True,
                        face_label=face_label,
                        face_score=face_score,
                        sit_duration=max_sit_sec / 60.0 if any_sitting else 0.0,
                        faces=faces,
                    )

                    new_events = event_tracker.update(alerts, _now)
                    care_result = dispatch_care_detection(care_runtime, alerts, new_events, frame.shape[:2])
                    if event_cache is not None:
                        for _kind in ("fall", "sit", "stranger"):
                            for _alert in new_events.get(_kind, []):
                                try:
                                    trigger_history_event(event_cache, _kind, _alert, care_result, _now, care_runtime)
                                except Exception as exc:
                                    print(f"[Record] trigger {_kind} failed: {type(exc).__name__}")
                    for alert in new_events["fall"]:
                        video_hw.update_stats(fall_count_inc=True, last_fall_time=_now)
                        print(f"[Event] 摔倒检测 person_id={alert.get('id')}")
                    for _ in new_events["sit"]:
                        video_hw.update_stats(sit_count_inc=True)
                    for _ in new_events["stranger"]:
                        video_hw.update_stats(stranger_count_inc=True)

                    for alert in alerts:
                        if "FALL" in alert.get('status', ''):
                            mqtt_client.publish_fall_alert()
                            break

                    if any_sitting:
                        sit_person = next((a.get('id') for a in alerts if a.get('is_sitting')), None)
                        mqtt_client.publish_sit_alert(duration_seconds=max_sit_sec, person_id=sit_person)

                    for alert in alerts:
                        if alert.get("face_label") == "stranger":
                            mqtt_client.publish_stranger_alert(
                                person_id=alert.get("id"),
                                score=alert.get("face_score"),
                            )
                            break

                    if face_label and face_label.startswith('known:') and face_label != _last_face_label:
                        clean_name = face_label[6:]
                        mqtt_client.publish_face_alert(name=clean_name, score=face_score)
                    _last_face_label = face_label

                    time.sleep(0.008)
            finally:
                detector.stop()
                detector.release_acl()
                system_detector = None
        else:
            detector.stop()
            detector.release_acl()
            system_detector = None

    inference_thread = threading.Thread(target=inference_loop, name="guardian-inference", daemon=True)
    inference_thread.start()

    @app.on_event("startup")
    async def startup_event():
        global mic_broadcast_handle
        mic_broadcast_handle = asyncio.create_task(mic_broadcast_task())

    @app.on_event("shutdown")
    async def shutdown_event():
        global mic_broadcast_handle
        if care_audio_player is not None:
            care_audio_player.close()
        if care_worker is not None:
            care_worker.stop()
        if care_runtime is not None:
            care_runtime.close()
        if continuous_recorder is not None:
            try:
                continuous_recorder.stop(timeout=30)
            except Exception as exc:
                print(f"[Record] 停止连续录像失败: {type(exc).__name__}")
        if continuous_cleanup is not None:
            continuous_cleanup.stop(timeout=5)
        if continuous_store is not None:
            continuous_store.close()
        if event_cache is not None:
            try:
                event_cache.stop(timeout=15)
                print("[Record] 事件录像已停止")
            except Exception as exc:
                print(f"[Record] 停止事件录像失败: {type(exc).__name__}")
        if cleanup_scheduler is not None:
            try:
                cleanup_scheduler.stop(timeout=5)
            except Exception:
                pass
        if history_store is not None:
            try:
                history_store.close()
            except Exception:
                pass
        if mic_broadcast_handle is not None:
            mic_broadcast_handle.cancel()
            try:
                await mic_broadcast_handle
            except asyncio.CancelledError:
                pass
            mic_broadcast_handle = None
        cleanup_system()

    print("\n" + "=" * 50)
    print(f"✅ 系统启动成功！")
    print(f"🌍 网页访问: http://{BOARD_IP}:{TARGET_PORT}")
    print("=" * 50 + "\n")

    try:
        uvicorn.run(app, host="0.0.0.0", port=TARGET_PORT, log_level="error",
                    timeout_graceful_shutdown=5)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_system()


# ==========================================
# 人脸录入 API（追加）
# ==========================================
import sqlite3 as _sqlite3
import shutil
from fastapi import UploadFile, File, Form

_DB_PATH = os.environ.get("AI_GUARDIAN_DB_PATH", "").strip() or "/root/ai_guardian/db/guardian.db"
_FACE_DIR = os.path.join(current_dir, "known_faces")
_FACE_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
_FACE_ADMIN_TOKEN = os.environ.get("AI_GUARDIAN_FACE_ADMIN_TOKEN", "").strip()


def require_face_admin(x_admin_token: str = Header(default="", alias="X-Admin-Token")):
    if not _FACE_ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="人脸管理未启用：请设置 AI_GUARDIAN_FACE_ADMIN_TOKEN")
    if not secrets.compare_digest(x_admin_token, _FACE_ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="管理员令牌无效")


def _validate_face_fields(name: str, user_id: str):
    if (not name or len(name) > 64 or name in (".", "..")
            or any(c in name for c in ("/", "\\", "\x00"))
            or not name.strip() or any(ord(c) < 32 for c in name)):
        raise HTTPException(status_code=400, detail="name 无效")
    allowed_user_id = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not user_id or len(user_id) > 64 or any(c not in allowed_user_id for c in user_id):
        raise HTTPException(status_code=400, detail="user_id 只能包含字母、数字、下划线和连字符")


_FACE_ENROLL_HINT = "上传不同方向的照片，有助于加快识别并提高精度；照片数量不作要求，一张也可登记。"


def _face_sample_paths(person_dir, user_id):
    if not os.path.isdir(person_dir):
        return []
    paths = []
    for file_name in sorted(os.listdir(person_dir)):
        stem, extension = os.path.splitext(file_name)
        owner, separator, token = stem.rpartition("_")
        # Match the complete ID, not a prefix (user and user_a are different).
        is_uuid = len(token) == 32 and all(c in "0123456789abcdefABCDEF" for c in token)
        is_legacy_timestamp = 9 <= len(token) <= 13 and token.isdigit()
        if (separator and owner == user_id and extension.lower() == ".jpg"
                and (is_uuid or is_legacy_timestamp)):
            path = os.path.join(person_dir, file_name)
            if os.path.isfile(path):
                paths.append(path)
    return paths


def _connect_face_db():
    parent = os.path.dirname(_DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = _sqlite3.connect(_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS t_face_feature ("
        "user_id TEXT PRIMARY KEY, name TEXT NOT NULL, feature_blob BLOB NOT NULL, create_time INTEGER NOT NULL)"
    )
    return conn


def _db_get_face_name(user_id: str):
    conn = _connect_face_db()
    try:
        row = conn.execute("SELECT name FROM t_face_feature WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def _db_log_face(user_id: str, name: str, feature_blob: bytes):
    conn = _connect_face_db()
    try:
        old_row = conn.execute("SELECT name FROM t_face_feature WHERE user_id=?", (user_id,)).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO t_face_feature(user_id, name, feature_blob, create_time) VALUES(?,?,?,?)",
            (user_id, name, feature_blob, int(time.time()))
        )
        conn.commit()
        return old_row[0] if old_row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _db_delete_face(user_id: str):
    conn = _connect_face_db()
    try:
        row = conn.execute("SELECT name FROM t_face_feature WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM t_face_feature WHERE user_id=?", (user_id,))
        conn.commit()
        return row[0]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _db_list_faces():
    conn = _connect_face_db()
    try:
        rows = conn.execute(
            "SELECT user_id, name, create_time FROM t_face_feature ORDER BY create_time DESC"
        ).fetchall()
        return [{"user_id": r[0], "name": r[1], "create_time": r[2],
                 "photo_count": len(_face_sample_paths(os.path.join(_FACE_DIR, r[1]), r[0]))} for r in rows]
    finally:
        conn.close()

def _reload_face_library_for_api(sample_path=None):
    if system_detector is None or not hasattr(system_detector, "face_library"):
        return "service_offline"
    try:
        library = system_detector.face_library
        library.load()
        with library._state_lock:
            if sample_path is not None and not any(
                    entry.get("path") == sample_path for entry in library.entries):
                return "photo_unusable"
        return "ready"
    except Exception as exc:
        print(f"[FaceAPI] face library reload failed: {exc}")
        return "reload_failed"


@app.post("/api/face/enroll", dependencies=[Depends(require_face_admin)])
async def face_enroll(
    name: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...)
):
    _validate_face_fields(name, user_id)
    img_bytes = await file.read(_FACE_UPLOAD_MAX_BYTES + 1)
    if not img_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(img_bytes) > _FACE_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 8 MiB")

    image = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise HTTPException(status_code=400, detail="上传内容不是可识别的图片")
    if image.shape[0] * image.shape[1] > 40_000_000:
        raise HTTPException(status_code=400, detail="图片分辨率过大")
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise HTTPException(status_code=400, detail="图片转换失败")
    stored_bytes = encoded.tobytes()

    person_dir = os.path.join(_FACE_DIR, name)
    os.makedirs(person_dir, exist_ok=True)
    img_path = os.path.join(person_dir, f"{user_id}_{uuid.uuid4().hex}.jpg")
    with open(img_path, "xb") as f:
        f.write(stored_bytes)
    moved_files = []
    try:
        old_name = _db_get_face_name(user_id)
        if old_name and old_name != name:
            _validate_face_fields(old_name, user_id)
            old_dir = os.path.join(_FACE_DIR, old_name)
            for old_path in _face_sample_paths(old_dir, user_id):
                new_path = os.path.join(person_dir, os.path.basename(old_path))
                if os.path.exists(new_path):
                    raise FileExistsError("renamed sample already exists")
                os.rename(old_path, new_path)
                moved_files.append((old_path, new_path))
        # feature_blob 沿用旧表结构，实际保存规范化后的图片字节。
        _db_log_face(user_id, name, stored_bytes)
    except Exception as e:
        for old_path, new_path in reversed(moved_files):
            try:
                os.rename(new_path, old_path)
            except OSError as rollback_error:
                print(f"[FaceEnroll] sample move rollback failed: {rollback_error}")
        try:
            os.remove(img_path)
        except OSError:
            pass
        print(f"[FaceEnroll] database write failed: {e}")
        raise HTTPException(status_code=500, detail="人脸记录写入失败") from e

    # Same-user uploads append; renaming preserves and moves that user's samples.
    if old_name and old_name != name:
        old_dir = os.path.join(_FACE_DIR, old_name)
        if os.path.isdir(old_dir) and not os.listdir(old_dir):
            try:
                os.rmdir(old_dir)
            except OSError:
                pass

    recognition_status = _reload_face_library_for_api(img_path)
    return JSONResponse({"ok": True, "user_id": user_id, "name": name,
                         "recognition_status": recognition_status,
                         "photo_count": len(_face_sample_paths(person_dir, user_id)),
                         "hint": _FACE_ENROLL_HINT})


@app.delete("/api/face/{user_id}", dependencies=[Depends(require_face_admin)])
async def face_delete(user_id: str):
    allowed_user_id = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not user_id or len(user_id) > 64 or any(c not in allowed_user_id for c in user_id):
        raise HTTPException(status_code=400, detail="user_id 无效")
    name = _db_get_face_name(user_id)
    if name is None:
        raise HTTPException(status_code=404, detail="人脸记录不存在")
    _validate_face_fields(name, user_id)

    # 先把图片移到临时名；数据库失败时可恢复文件，避免只删一半。
    person_dir = os.path.join(_FACE_DIR, name)
    moved_files = []
    try:
        if os.path.isdir(person_dir):
            for original_path in _face_sample_paths(person_dir, user_id):
                hidden_path = original_path + ".deleting-" + uuid.uuid4().hex
                os.replace(original_path, hidden_path)
                moved_files.append((original_path, hidden_path))
        deleted_name = _db_delete_face(user_id)
        if deleted_name is None:
            raise HTTPException(status_code=404, detail="人脸记录已不存在")
    except Exception as e:
        for original_path, hidden_path in moved_files:
            if os.path.exists(hidden_path):
                os.replace(hidden_path, original_path)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="人脸记录删除失败") from e
    for _, hidden_path in moved_files:
        try:
            os.remove(hidden_path)
        except OSError as e:
            print(f"[FaceDelete] deferred image cleanup failed: {e}")
    if os.path.isdir(person_dir) and not os.listdir(person_dir):
        shutil.rmtree(person_dir, ignore_errors=True)
    recognition_status = _reload_face_library_for_api()
    return JSONResponse({"ok": True, "deleted": user_id,
                         "recognition_status": recognition_status})


@app.get("/api/face/list", dependencies=[Depends(require_face_admin)])
async def face_list():
    return JSONResponse({"ok": True, "faces": _db_list_faces(), "hint": _FACE_ENROLL_HINT})


if __name__ == "__main__":
    run_system()
