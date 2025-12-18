# import os
# import requests
# import cv2
# import threading
# import numpy as np
# import time
# import asyncio
# import json
# import warnings

# # 抑制ALSA警告
# os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
# warnings.filterwarnings('ignore')

# from flask import Flask, Response, render_template_string
# from flask_socketio import SocketIO, emit, join_room

# from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
# from aiortc.mediastreams import VideoStreamTrack
# from av import VideoFrame

# # ---------------------- 配置常量 ----------------------
# SOCKETIO_CDN_URL = "https://cdn.jsdelivr.net/npm/socket.io-client@4/dist/socket.io.min.js"
# STATIC_FOLDER = "static"
# CLIENT_FILENAME = "socket.io.min.js"
# CLIENT_FILEPATH = os.path.join(STATIC_FOLDER, CLIENT_FILENAME)

# # ---------------------- 共享状态 ----------------------
# app = Flask(__name__)
# app.config['SECRET_KEY'] = 'fall_detection_secret'
# socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# processed_frame = None
# frame_lock = threading.Lock()

# WEBRTC_ROOM = 'devboard_call_room'
# pcs = set()
# aiortc_loop = None

# # 音频相关
# # 音频功能已停用（前端效果保留），服务器端暂不处理音频数据

# # ---------------------- 自动下载函数 ----------------------
# def download_socketio_client():
#     """检查并下载 Socket.IO 客户端脚本到 static/ 目录"""
#     if not os.path.exists(STATIC_FOLDER):
#         os.makedirs(STATIC_FOLDER)
#         print(f"创建目录: {STATIC_FOLDER}")

#     if os.path.exists(CLIENT_FILEPATH):
#         print(f"Socket.IO 客户端脚本已存在: {CLIENT_FILEPATH}")
#         return

#     print(f"正在从 CDN 下载 Socket.IO 客户端脚本: {SOCKETIO_CDN_URL}...")
#     try:
#         response = requests.get(SOCKETIO_CDN_URL, timeout=10)
#         response.raise_for_status()
#         with open(CLIENT_FILEPATH, 'wb') as f:
#             f.write(response.content)
#         print(f"✅ 下载完成并保存至: {CLIENT_FILEPATH}")
#     except requests.exceptions.RequestException as e:
#         print(f"❌ 警告: 自动下载 Socket.IO 客户端脚本失败。请检查网络连接或手动下载。错误: {e}")

# # ---------------------- 自定义视频轨道 (WebRTC 视频回传) ----------------------
# class CustomVideoStreamTrack(VideoStreamTrack):
#     def __init__(self):
#         super().__init__()
#         self.counter = 0

#     async def recv(self):
#         await asyncio.sleep(1 / 15)
#         with frame_lock:
#             frame_np = processed_frame.copy() if processed_frame is not None else None

#         if frame_np is not None:
#             try:
#                 frame_rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
#                 av_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
#                 av_frame.pts = self.counter
#                 av_frame.time_base = 1 / 15
#                 self.counter += 1
#                 return av_frame
#             except Exception:
#                 pass

#         return await super().recv()

# # ---------------------- 自定义音频轨道 (WebRTC 音频回传) ----------------------
# # 音频相关逻辑已删除 — 保留前端效果（HTML/JS）但不在服务器端处理音频

# # ---------------------- WebRTC Peer 逻辑函数 ----------------------
# async def create_new_peer_connection(offer_sdp):
#     for pc in list(pcs):
#         if pc.remoteDescription:
#             await pc.close()
#             pcs.discard(pc)

#     pc = RTCPeerConnection()
#     pcs.add(pc)

#     @pc.on("iceconnectionstatechange")
#     async def on_iceconnectionstatechange():
#         if pc.iceConnectionState in ["failed", "closed"]:
#             await pc.close()
#             pcs.discard(pc)

#     pc.addTrack(CustomVideoStreamTrack())

#     @pc.on("track")
#     def on_track(track):
#         # 音频回传已在服务器端停用；保留此回调用于调试或未来扩展
#         print(f"Received remote track: kind={track.kind}")

#     @pc.on("icecandidate")
#     async def on_icecandidate(candidate):
#         if candidate:
#             await asyncio.to_thread(socketio.emit,
#                                     'ice-candidate',
#                                     {'candidate': candidate.candidate,
#                                      'sdpMid': candidate.sdpMid,
#                                      'sdpMLineIndex': candidate.sdpMLineIndex},
#                                     room=WEBRTC_ROOM)

#     await pc.setRemoteDescription(RTCSessionDescription(offer_sdp, "offer"))
#     answer = await pc.createAnswer()
#     await pc.setLocalDescription(answer)

#     await asyncio.to_thread(socketio.emit,
#                             'answer',
#                             {'sdp': pc.localDescription.sdp, 'type': 'answer'},
#                             room=WEBRTC_ROOM)

# # ---------------------- SocketIO 信令处理 ----------------------
# @socketio.on('connect')
# def handle_connect(sid=None, environ=None):
#     join_room(WEBRTC_ROOM)

# @socketio.on('offer')
# def handle_offer(data):
#     if aiortc_loop:
#         asyncio.run_coroutine_threadsafe(create_new_peer_connection(data['sdp']), aiortc_loop)

# @socketio.on('ice-candidate')
# def handle_candidate(data):
#     if not pcs:
#         return

#     candidate = RTCIceCandidate(
#         sdpMid=data['sdpMid'],
#         sdpMLineIndex=data['sdpMLineIndex'],
#         candidate=data['candidate'],
#     )

#     if aiortc_loop:
#         pc = next(iter(pcs))
#         asyncio.run_coroutine_threadsafe(pc.addIceCandidate(candidate), aiortc_loop)

# @socketio.on('disconnect')
# def handle_disconnect():
#     pass

# def run_aiortc_loop():
#     global aiortc_loop
#     aiortc_loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(aiortc_loop)
#     aiortc_loop.run_forever()

# # ---------------------- 网页模板 ----------------------
# HTML_TEMPLATE = '''
# <!DOCTYPE html>
# <html lang="zh-CN">
# <head>
#     <meta charset="UTF-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <title>跌倒检测监控 - 语音通话</title>
#     <script src="/static/socket.io.min.js"></script>
#     <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
#     <style>
#         * {
#             margin: 0;
#             padding: 0;
#             box-sizing: border-box;
#         }
#         body {
#             font-family: 'Roboto', sans-serif;
#             background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
#             min-height: 100vh;
#             color: #333;
#         }
#         .container {
#             max-width: 1400px;
#             margin: 0 auto;
#             padding: 20px;
#         }
#         .header {
#             text-align: center;
#             margin-bottom: 30px;
#             color: white;
#         }
#         .header h1 {
#             font-size: 2.5em;
#             margin-bottom: 10px;
#             text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
#         }
#         .status-bar {
#             background: rgba(255,255,255,0.1);
#             padding: 15px;
#             border-radius: 10px;
#             margin-bottom: 20px;
#             backdrop-filter: blur(10px);
#         }
#         .status-item {
#             display: inline-block;
#             margin: 0 20px;
#             font-weight: 500;
#         }
#         .main-content {
#             display: grid;
#             grid-template-columns: 1fr 1fr;
#             gap: 30px;
#             margin-bottom: 30px;
#         }
#         .video-section, .call-section {
#             background: rgba(255,255,255,0.95);
#             border-radius: 15px;
#             padding: 25px;
#             box-shadow: 0 8px 32px rgba(0,0,0,0.1);
#             backdrop-filter: blur(10px);
#         }
#         .section-title {
#             font-size: 1.5em;
#             margin-bottom: 20px;
#             color: #4a5568;
#             border-bottom: 2px solid #e2e8f0;
#             padding-bottom: 10px;
#         }
#         #videoFeed {
#             width: 100%;
#             border-radius: 10px;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         .call-area {
#             display: flex;
#             gap: 20px;
#             margin-bottom: 20px;
#         }
#         .audio-indicator, .call-video {
#             flex: 1;
#             height: 200px;
#             border-radius: 10px;
#             display: flex;
#             flex-direction: column;
#             align-items: center;
#             justify-content: center;
#             background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
#             color: white;
#             font-size: 1.1em;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         .call-video {
#             background: #2d3748;
#         }
#         .indicator-icon {
#             font-size: 3em;
#             margin-bottom: 10px;
#         }
#         .indicator-text {
#             text-align: center;
#         }
#         .controls {
#             display: flex;
#             justify-content: center;
#             gap: 15px;
#         }
#         button {
#             padding: 12px 25px;
#             border: none;
#             border-radius: 25px;
#             font-size: 16px;
#             font-weight: 500;
#             cursor: pointer;
#             transition: all 0.3s ease;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         #startBtn {
#             background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
#             color: white;
#         }
#         #startBtn:hover:not(:disabled) {
#             transform: translateY(-2px);
#             box-shadow: 0 6px 20px rgba(79,172,254,0.4);
#         }
#         #endBtn {
#             background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);
#             color: white;
#         }
#         #endBtn:hover:not(:disabled) {
#             transform: translateY(-2px);
#             box-shadow: 0 6px 20px rgba(255,154,158,0.4);
#         }
#         button:disabled {
#             opacity: 0.6;
#             cursor: not-allowed;
#             transform: none;
#         }
#         .footer {
#             text-align: center;
#             color: white;
#             margin-top: 30px;
#             font-size: 0.9em;
#             opacity: 0.8;
#         }
#         @media (max-width: 768px) {
#             .main-content {
#                 grid-template-columns: 1fr;
#             }
#             .call-area {
#                 flex-direction: column;
#             }
#             .header h1 {
#                 font-size: 2em;
#             }
#         }
#     </style>
# </head>
# <body>
#     <div class="container">
#         <div class="header">
#             <h1>🛡️ 跌倒检测监控系统</h1>
#             <p>实时监控与语音通话</p>
#         </div>
        
#         <div class="status-bar">
#             <div class="status-item">WebRTC状态: <span id="webrtc_status">正在连接...</span></div>
#             <div class="status-item">麦克风: <span id="mic_status">未启动</span></div>
#         </div>
        
#         <div class="main-content">
#             <div class="video-section">
#                 <h2 class="section-title">📹 实时视频监控</h2>
#                 <img id="videoFeed" src="/video_feed" alt="实时监控视频流">
#             </div>
            
#             <div class="call-section">
#                 <h2 class="section-title">🎤 语音通话</h2>
#                 <div class="call-area">
#                     <div class="audio-indicator">
#                         <div class="indicator-icon">🎧</div>
#                         <div class="indicator-text">
#                             <div>本地麦克风</div>
#                             <div id="mic_status_small" style="font-size: 0.8em; opacity: 0.8;">未启动</div>
#                         </div>
#                     </div>
#                     <div class="call-video">
#                         <div class="indicator-icon">📞</div>
#                         <div class="indicator-text">
#                             <div>远程音频</div>
#                             <div id="remote_status" style="font-size: 0.8em; opacity: 0.8;">等待连接</div>
#                         </div>
#                     </div>
#                 </div>
#                 <div class="controls">
#                     <button id="startBtn" onclick="startCall()">📞 发起通话</button>
#                     <button id="endBtn" onclick="endCall()" disabled>❌ 结束通话</button>
#                 </div>
#             </div>
#         </div>
        
#         <div class="footer">
#             <p>© 2024 AI Guardian System | 支持蓝牙耳机语音通话</p>
#         </div>
#     </div>

#     <audio id="remoteAudio" autoplay></audio>

#     <script>
#         * {
#             margin: 0;
#             padding: 0;
#             box-sizing: border-box;
#         }
#         body {
#             font-family: 'Roboto', sans-serif;
#             background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
#             min-height: 100vh;
#             color: #333;
#         }
#         .container {
#             max-width: 1400px;
#             margin: 0 auto;
#             padding: 20px;
#         }
#         .header {
#             text-align: center;
#             margin-bottom: 30px;
#             color: white;
#         }
#         .header h1 {
#             font-size: 2.5em;
#             margin-bottom: 10px;
#             text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
#         }
#         .status-bar {
#             background: rgba(255,255,255,0.1);
#             padding: 15px;
#             border-radius: 10px;
#             margin-bottom: 20px;
#             backdrop-filter: blur(10px);
#         }
#         .status-item {
#             display: inline-block;
#             margin: 0 20px;
#             font-weight: 500;
#         }
#         .main-content {
#             display: grid;
#             grid-template-columns: 1fr 1fr;
#             gap: 30px;
#             margin-bottom: 30px;
#         }
#         .video-section, .call-section {
#             background: rgba(255,255,255,0.95);
#             border-radius: 15px;
#             padding: 25px;
#             box-shadow: 0 8px 32px rgba(0,0,0,0.1);
#             backdrop-filter: blur(10px);
#         }
#         .section-title {
#             font-size: 1.5em;
#             margin-bottom: 20px;
#             color: #4a5568;
#             border-bottom: 2px solid #e2e8f0;
#             padding-bottom: 10px;
#         }
#         #videoFeed {
#             width: 100%;
#             border-radius: 10px;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         .call-area {
#             display: flex;
#             gap: 20px;
#             margin-bottom: 20px;
#         }
#         .audio-indicator, .call-video {
#             flex: 1;
#             height: 200px;
#             border-radius: 10px;
#             display: flex;
#             flex-direction: column;
#             align-items: center;
#             justify-content: center;
#             background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
#             color: white;
#             font-size: 1.1em;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         .call-video {
#             background: #2d3748;
#         }
#         .indicator-icon {
#             font-size: 3em;
#             margin-bottom: 10px;
#         }
#         .indicator-text {
#             text-align: center;
#         }
#         .controls {
#             display: flex;
#             justify-content: center;
#             gap: 15px;
#         }
#         button {
#             padding: 12px 25px;
#             border: none;
#             border-radius: 25px;
#             font-size: 16px;
#             font-weight: 500;
#             cursor: pointer;
#             transition: all 0.3s ease;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         #startBtn {
#             background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
#             color: white;
#         }
#         #startBtn:hover:not(:disabled) {
#             transform: translateY(-2px);
#             box-shadow: 0 6px 20px rgba(79,172,254,0.4);
#         }
#         #endBtn {
#             background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);
#             color: white;
#         }
#         #endBtn:hover:not(:disabled) {
#             transform: translateY(-2px);
#             box-shadow: 0 6px 20px rgba(255,154,158,0.4);
#         }
#         button:disabled {
#             opacity: 0.6;
#             cursor: not-allowed;
#             transform: none;
#         }
#         .footer {
#             text-align: center;
#             color: white;
#             margin-top: 30px;
#             font-size: 0.9em;
#             opacity: 0.8;
#         }
#         @media (max-width: 768px) {
#             .main-content {
#                 grid-template-columns: 1fr;
#             }
#             .call-area {
#                 flex-direction: column;
#             }
#             .header h1 {
#                 font-size: 2em;
#             }
#         }
#     </style>
# </head>
# <body>
#     <div class="container">
#         <div class="header">
#             <h1>🛡️ 跌倒检测监控系统</h1>
#             <p>实时监控与语音通话</p>
#         </div>
        
#         <div class="status-bar">
#             <div class="status-item">WebRTC状态: <span id="webrtc_status">正在连接...</span></div>
#             <div class="status-item">麦克风: <span id="mic_status">未启动</span></div>
#         </div>
        
#         <div class="main-content">
#             <div class="video-section">
#                 <h2 class="section-title">📹 实时视频监控</h2>
#                 <img id="videoFeed" src="/video_feed" alt="实时监控视频流">
#             </div>
            
#             <div class="call-section">
#                 <h2 class="section-title">🎤 语音通话</h2>
#                 <div class="call-area">
#                     <div class="audio-indicator">
#                         <div class="indicator-icon">🎧</div>
#                         <div class="indicator-text">
#                             <div>本地麦克风</div>
#                             <div id="mic_status_small" style="font-size: 0.8em; opacity: 0.8;">未启动</div>
#                         </div>
#                     </div>
#                     <div class="call-video">
#                         <div class="indicator-icon">📞</div>
#                         <div class="indicator-text">
#                             <div>远程音频</div>
#                             <div id="remote_status" style="font-size: 0.8em; opacity: 0.8;">等待连接</div>
#                         </div>
#                     </div>
#                 </div>
#                 <div class="controls">
#                     <button id="startBtn" onclick="startCall()">📞 发起通话</button>
#                     <button id="endBtn" onclick="endCall()" disabled>❌ 结束通话</button>
#                 </div>
#             </div>
#         </div>
        
#         <div class="footer">
#             <p>© 2024 AI Guardian System | 支持蓝牙耳机语音通话</p>
#         </div>
#     </div>

#     <audio id="remoteAudio" autoplay></audio>

#     <script>
#         // ----------------------------------------------------
#         // 全局变量声明
#         // ----------------------------------------------------
#         let socket = null; 
#         let peerConnection = null;   
#         let localStream = null;     
        
#         const configuration = {
#             iceServers: [
#                 { urls: 'stun:stun.l.google.com:19302' },
#                 { urls: 'stun:stun1.l.google.com:19302' },
#                 { urls: 'stun:stun2.l.google.com:19302' }
#             ]
#         };

#         let statusEl, micStatusEl, micStatusSmallEl, remoteStatusEl, startBtn, endBtn;

#         // 辅助函数 (全局可用)
#         function updateStatus(text) {
#             if(statusEl) statusEl.textContent = text;
#         }

#         function updateMicStatus(text) {
#             if(micStatusEl) micStatusEl.textContent = text;
#             if(micStatusSmallEl) micStatusSmallEl.textContent = text;
#         }

#         function updateRemoteStatus(text) {
#             if(remoteStatusEl) remoteStatusEl.textContent = text;
#         }

#         function updateButtonState(isCalling) {
#             if(startBtn) startBtn.disabled = isCalling;
#             if(endBtn) endBtn.disabled = !isCalling;
#         }

#         function getUserMediaCompat(constraints) {
#             if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
#                 return navigator.mediaDevices.getUserMedia(constraints);
#             }
#             return Promise.reject(new Error('浏览器不支持媒体设备访问'));
#         }

#         // ----------------------------------------------------
#         // 全局函数：endCall 
#         // ----------------------------------------------------
#         window.endCall = function() {
#             updateButtonState(false); 
            
#             if (peerConnection) {
#                 try { peerConnection.close(); } catch(e) { console.error("PeerConnection close failed:", e); }
#                 peerConnection = null;
#             }
            
#             if (localStream) {
#                 try {
#                     localStream.getTracks().forEach(track => {
#                         if (track.stop) track.stop();
#                     });
#                 } catch(e) { console.error("Local stream stop failed:", e); }
#                 localStream = null;
#             }
            
#             const remoteAudio = document.getElementById('remoteAudio');

#             if (remoteAudio) remoteAudio.srcObject = null;

#             updateStatus('通话已结束');
#             updateMicStatus('未启动');
#             updateRemoteStatus('等待连接');
#         }

#         // ----------------------------------------------------
#         // 全局函数：startCall 
#         // ----------------------------------------------------
#         window.startCall = function() {
#             window.endCall(); 
#             updateButtonState(true); 

#             if (!socket || !socket.connected) {
#                 updateStatus('Socket.IO 未连接，无法开始通话。请检查服务器和网络。');
#                 updateButtonState(false);
#                 return;
#             }
            
#             updateStatus('正在获取本地麦克风...');
#             updateMicStatus('获取中...');

#             const constraints = { video: false, audio: true };
            
#             getUserMediaCompat(constraints)
#                 .then(stream => {
#                     localStream = stream;
#                     updateMicStatus('已开启');
#                     peerConnection = new RTCPeerConnection(configuration);
#                     updateStatus('PeerConnection 已创建，发送 Offer...');

#                     stream.getTracks().forEach(track => {
#                         peerConnection.addTrack(track, stream);
#                     });

#                     peerConnection.ontrack = e => {
#                         const mediaStream = e.streams[0];
#                         if (e.track.kind === 'audio') {
#                             document.getElementById('remoteAudio').srcObject = mediaStream;
#                             updateStatus('WebRTC 连接成功，双向音频已建立');
#                             updateRemoteStatus('已连接');
#                         }
#                     };
                    
#                     peerConnection.oniceconnectionstatechange = () => {
#                         updateStatus(`ICE 状态: ${peerConnection.iceConnectionState}`);
#                         if (peerConnection.iceConnectionState === 'disconnected' || 
#                             peerConnection.iceConnectionState === 'failed' || 
#                             peerConnection.iceConnectionState === 'closed') {
#                             window.endCall();
#                         }
#                     };

#                     peerConnection.onicecandidate = e => {
#                         if (e.candidate) socket.emit('ice-candidate', {
#                             candidate: e.candidate.candidate,
#                             sdpMid: e.candidate.sdpMid,
#                             sdpMLineIndex: e.candidate.sdpMLineIndex
#                         });
#                     };
                    
#                     return peerConnection.createOffer();
#                 })
#                 .then(offer => peerConnection.setLocalDescription(offer))
#                 .then(() => socket.emit('offer', {sdp: peerConnection.localDescription.sdp, type: 'offer'}))
#                 .catch(err => {
#                     console.error('WebRTC 流程失败:', err);
#                     window.endCall(); 
#                     updateStatus('通话启动失败: ' + (err.name || 'Error') + ' - ' + (err.message || 'Unknown error'));
#                     updateMicStatus('失败');
#                 });
#         }

#         // ----------------------------------------------------
#         // DOMContentLoaded：初始化元素和 Socket
#         // ----------------------------------------------------
#         document.addEventListener('DOMContentLoaded', () => {
#             statusEl = document.getElementById('webrtc_status');
#             micStatusEl = document.getElementById('mic_status');
#             micStatusSmallEl = document.getElementById('mic_status_small');
#             remoteStatusEl = document.getElementById('remote_status');
#             startBtn = document.getElementById('startBtn');
#             endBtn = document.getElementById('endBtn');

#             if (typeof io !== 'undefined') {
#                 // 动态获取服务器地址，无需手动修改
#                 const SERVER_URL = 'http://' + window.location.hostname + ':5000'; 
#                 socket = io(SERVER_URL, {
#                     transports: ['polling'],
#                     reconnection: true,
#                     reconnectionAttempts: 5, 
#                     reconnectionDelay: 1000 
#                 }); 
#                 updateStatus('Socket.IO 正在连接...');
#             } else {
#                 updateStatus('致命错误：Socket.IO 库未加载！');
#                 return;
#             }

#             socket.on('connect', () => {
#                 updateStatus('Socket.IO 连接成功，等待通话');
#                 updateButtonState(false); 
#             });
            
#             socket.on('connect_error', (error) => {
#                 console.error("Socket.IO 连接失败:", error);
#                 updateStatus('Socket.IO 连接失败！请检查网络。');
#                 updateButtonState(true); 
#             });

#             socket.on('answer', answer => {
#                 if (peerConnection) {
#                     peerConnection.setRemoteDescription(new RTCSessionDescription(answer.sdp, 'answer'))
#                         .catch(err => console.error('设置 Answer 失败:', err));
#                 }
#             });

#             socket.on('ice-candidate', candidate => {
#                 if (peerConnection && peerConnection.remoteDescription) {
#                     peerConnection.addIceCandidate(new RTCIceCandidate(candidate))
#                         .catch(err => console.error('添加 ICE 候选失败:', err));
#                 } 
#             });
#         });
#     </script>
# </body>
# </html>
# '''

# # Note: keep the full HTML_TEMPLATE from your existing video_stream.py in the actual file.

# # ---------------------- 视频流 M-JPEG 逻辑 ----------------------
# def generate_frames():
#     global processed_frame
#     while True:
#         frame_bytes = None
#         with frame_lock:
#             frame_to_send = processed_frame.copy() if processed_frame is not None else None

#         if frame_to_send is not None:
#             try:
#                 ret, buffer = cv2.imencode('.jpg', frame_to_send, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
#                 if ret:
#                     frame_bytes = buffer.tobytes()
#             except Exception as e:
#                 print(f"Frame encoding failed: {e}")
#                 pass

#         if frame_bytes is not None:
#             yield (b'--frame\r\n'
#                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
#         else:
#             time.sleep(0.01)

# @app.route('/')
# def index():
#     return render_template_string(HTML_TEMPLATE)

# @app.route('/video_feed')
# def video_feed_route():
#     return Response(generate_frames(),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')

# # ---------------------- 启动函数 ----------------------
# def start_stream():
#     """启动带SocketIO和aiortc的视频流服务"""
#     download_socketio_client()
#     aiortc_thread = threading.Thread(target=run_aiortc_loop, daemon=True)
#     aiortc_thread.start()
#     try:
#         print("M-JPEG/SocketIO 服务已启动，端口 5000")
#         socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
#     except Exception as e:
#         print(f"视频流服务启动失败：{e}")

# def update_frame(frame):
#     """更新最新的处理帧 (供主循环调用)"""
#     global processed_frame
#     with frame_lock:
#         processed_frame = frame
# src/ascend_video_stream.py
# 纯净版 MJPEG 推流服务 - 无需 Socket.IO
# import time
# import cv2
# import threading
# from flask import Flask, Response

# # 全局变量存放当前帧
# outputFrame = None
# lock = threading.Lock()

# # 初始化 Flask
# app = Flask(__name__)

# def update_frame(frame):
#     """
#     主程序调用此函数更新画面
#     """
#     global outputFrame, lock
#     with lock:
#         # 压缩一下图片质量以降低延迟 (质量 60)
#         # 如果追求画质可以改大，追求速度改小
#         _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
#         outputFrame = encoded

# def generate():
#     """
#     视频流生成器
#     """
#     global outputFrame, lock
#     while True:
#         with lock:
#             if outputFrame is None:
#                 continue
#             # 获取当前帧的二进制数据
#             encodedImage = outputFrame.tobytes()

#         # 生成 MJPEG 数据流格式
#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + encodedImage + b'\r\n')
        
#         # 控制帧率，避免 CPU 100%
#         time.sleep(0.03)

# @app.route("/video_feed")
# def video_feed():
#     """
#     网页 img 标签访问的路由
#     """
#     return Response(generate(),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')

# @app.route("/")
# def index():
#     return "Video Stream Running..."

# def start_stream():
#     """
#     启动 Flask 服务器 (阻塞式，需在线程运行)
#     """
#     # 禁用 Flask 的启动广告
#     import logging
#     log = logging.getLogger('werkzeug')
#     log.setLevel(logging.ERROR)
    
#     print("🎥 [Video] MJPEG 视频流服务已启动: http://0.0.0.0:5000/video_feed")
#     # host='0.0.0.0' 允许外部访问
#     app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
# src/ascend_video_stream.py
# # 纯净版 MJPEG 推流服务 - 无需 Socket.IO
# import time
# import cv2
# import threading
# from flask import Flask, Response

# # 全局变量存放当前帧
# outputFrame = None
# lock = threading.Lock()

# # 初始化 Flask
# app = Flask(__name__)

# def update_frame(frame):
#     """
#     主程序调用此函数更新画面
#     """
#     global outputFrame, lock
#     with lock:
#         # 压缩一下图片质量以降低延迟 (质量 60)
#         # 如果追求画质可以改大，追求速度改小
#         _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
#         outputFrame = encoded

# def generate():
#     """
#     视频流生成器
#     """
#     global outputFrame, lock
#     while True:
#         with lock:
#             if outputFrame is None:
#                 continue
#             # 获取当前帧的二进制数据
#             encodedImage = outputFrame.tobytes()

#         # 生成 MJPEG 数据流格式
#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + encodedImage + b'\r\n')
        
#         # 控制帧率，避免 CPU 100%
#         time.sleep(0.03)

# @app.route("/video_feed")
# def video_feed():
#     """
#     网页 img 标签访问的路由
#     """
#     return Response(generate(),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')

# @app.route("/")
# def index():
#     return "Video Stream Running..."

# def start_stream():
#     """
#     启动 Flask 服务器 (阻塞式，需在线程运行)
#     """
#     # 禁用 Flask 的启动广告
#     import logging
#     log = logging.getLogger('werkzeug')
#     log.setLevel(logging.ERROR)
    
#     print("🎥 [Video] MJPEG 视频流服务已启动: http://0.0.0.0:5000/video_feed")
#     # host='0.0.0.0' 允许外部访问
#     app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
# # src/ascend_video_stream.py
# import threading
# import cv2

# # 全局共享变量
# outputFrame = None
# lock = threading.Lock()

# def update_frame(frame):
#     global outputFrame, lock
#     with lock:
#         # 压缩图片
#         _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
#         outputFrame = encoded

# def start_stream():
#     pass
import threading
import cv2

# 全局共享变量
outputFrame = None
lock = threading.Lock()

def update_frame(frame):
    """
    更新当前视频帧
    ascend_main_other.py 中的检测循环会调用此函数
    """
    global outputFrame, lock
    with lock:
        # 压缩图片 (质量 65) 以减少内存占用并准备传输
        _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        outputFrame = encoded

def get_current_frame():
    """
    获取当前视频帧 
    FastAPI 服务器会调用此函数获取数据推流
    """
    global outputFrame, lock
    with lock:
        if outputFrame is None:
            return None
        return outputFrame.tobytes()

# ==========================================
# 👇 兼容性修复 👇
# ==========================================
def start_stream():
    """
    保留此函数是为了防止 ascend_main_other.py 报错。
    现在视频流由 ascend_board_server.py 中的 FastAPI 统一管理，
    所以这里不需要做任何事。
    """
    pass