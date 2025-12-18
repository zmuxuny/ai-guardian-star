# # src/ascend_board_server.py
# import sys
# import os
# import time
# import threading
# import asyncio
# import uvicorn
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# from fastapi.responses import HTMLResponse # <--- 必须有这个

# # --- 路径设置 ---
# current_dir = os.path.dirname(os.path.abspath(__file__))
# sys.path.append(current_dir)
# from ascend_video_stream import start_stream, update_frame
# import ascend_voice_stream as audio_hw
# # 引用你的检测器类
# from ascend_main_other import AclLiteStreamDetector, MQTTAlertClient 

# app = FastAPI()
# web_clients = []

# # ==========================================
# # 👇👇👇 核心修改在这里：增加了主页路由 👇👇👇
# # ==========================================
# @app.get("/")
# async def get():
#     # 读取同级目录下的 index.html 文件
#     html_file = os.path.join(current_dir, "index.html")
#     if os.path.exists(html_file):
#         with open(html_file, "r", encoding="utf-8") as f:
#             return HTMLResponse(content=f.read())
#     return HTMLResponse(content=f"<h1>错误：找不到文件 {html_file}</h1>")
# # ==========================================

# @app.websocket("/ws/web_client")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     web_clients.append(websocket)
#     print(f"✅ 网页端已连接！IP: {websocket.client.host}")
#     try:
#         while True:
#             data = await websocket.receive_bytes()
#             audio_hw.put_audio_frame(data)
#     except WebSocketDisconnect:
#         if websocket in web_clients:
#             web_clients.remove(websocket)
#     except Exception:
#         pass

# def mic_broadcast_loop():
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     async def broadcast_task():
#         while True:
#             frame = audio_hw.get_audio_frame()
#             if frame and len(web_clients) > 0:
#                 for client in web_clients:
#                     try: await client.send_bytes(frame)
#                     except: pass
#             else:
#                 await asyncio.sleep(0.005)
#     loop.run_until_complete(broadcast_task())

# def run_system():
#     # 1. 启动硬件
#     threading.Thread(target=audio_hw.start_audio_service, daemon=True).start()
#     threading.Thread(target=mic_broadcast_loop, daemon=True).start()
#     # 2. 启动视频流
#     threading.Thread(target=start_stream, daemon=True).start()
    
#     # 3. 启动 YOLO (后台线程)
#     def inference_loop():
#         detector = AclLiteStreamDetector(model_path="/root/yolo/best.om", camera_index=0)
#         mqtt_client = MQTTAlertClient()
#         if detector.init():
#             try:
#                 while detector.running:
#                     res = detector.get_detected_frame()
#                     if res is None: break
#                     frame, alerts = res
#                     for alert in alerts:
#                         if "FALL" in alert.get('status', ''):
#                             mqtt_client.publish_fall_alert()
#                             break
#                     update_frame(frame)
#                     time.sleep(0.001)
#             finally:
#                 detector.stop()
#     threading.Thread(target=inference_loop, daemon=True).start()

#     # 4. 启动服务器
#     print("🚀 服务器启动中...")
#     print("请访问: http://192.168.137.100:8000")
#     uvicorn.run(app, host="0.0.0.0", port=8000)

# if __name__ == "__main__":
#     run_system()
# src/ascend_board_server.py
# # src/ascend_board_server.py
# import sys
# import os
# import time
# import cv2
# import threading
# import asyncio
# import uvicorn
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# from fastapi.responses import HTMLResponse, StreamingResponse

# # --- 路径与导入 ---
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# import ascend_voice_stream as audio_hw
# from ascend_main_other import AclLiteStreamDetector, MQTTAlertClient 

# # --- 全局变量 ---
# outputFrame = None
# lock = threading.Lock()
# web_clients = [] 
# app = FastAPI()

# # ==========================================
# # 1. 视频流逻辑 (MJPEG)
# # ==========================================
# def update_frame(frame):
#     global outputFrame, lock
#     with lock:
#         # 压缩图片，质量 60
#         _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
#         outputFrame = encoded

# def generate_mjpeg():
#     global outputFrame, lock
#     while True:
#         with lock:
#             if outputFrame is None:
#                 continue
#             encodedImage = outputFrame.tobytes()
#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + encodedImage + b'\r\n')
#         time.sleep(0.03)

# @app.get("/video_feed")
# async def video_feed():
#     return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

# # ==========================================
# # 2. 语音对讲逻辑 (WebSocket)
# # ==========================================
# @app.websocket("/ws/intercom")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     web_clients.append(websocket)
#     try:
#         while True:
#             data = await websocket.receive_bytes()
#             audio_hw.put_audio_frame(data)
#     except:
#         if websocket in web_clients: web_clients.remove(websocket)

# def mic_broadcast_loop():
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     async def broadcast_task():
#         print("🎙️ 麦克风广播服务启动")
#         while True:
#             frame = audio_hw.get_audio_frame()
#             if frame and len(web_clients) > 0:
#                 for client in web_clients:
#                     try: await client.send_bytes(frame)
#                     except: pass
#             else:
#                 await asyncio.sleep(0.005)
#     loop.run_until_complete(broadcast_task())

# # ==========================================
# # 3. 你的定制 UI (已修复 Socket.IO 依赖)
# # ==========================================
# HTML_TEMPLATE = """
# <!DOCTYPE html>
# <html lang="zh-CN">
# <head>
#     <meta charset="UTF-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <title>跌倒检测监控 - 语音通话</title>
#     <style>
#         * { margin: 0; padding: 0; box-sizing: border-box; }
#         body {
#             font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
#             background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
#             min-height: 100vh;
#             color: #333;
#         }
#         .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
#         .header { text-align: center; margin-bottom: 30px; color: white; }
#         .header h1 { font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
#         .status-bar {
#             background: rgba(255,255,255,0.1); padding: 15px;
#             border-radius: 10px; margin-bottom: 20px;
#             backdrop-filter: blur(10px); color: white; text-align: center;
#         }
#         .status-item { display: inline-block; margin: 0 20px; font-weight: 500; }
#         .main-content { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px; }
#         .video-section, .call-section {
#             background: rgba(255,255,255,0.95); border-radius: 15px;
#             padding: 25px; box-shadow: 0 8px 32px rgba(0,0,0,0.1);
#         }
#         .section-title {
#             font-size: 1.5em; margin-bottom: 20px; color: #4a5568;
#             border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;
#         }
#         #videoFeed {
#             width: 100%; border-radius: 10px;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#             min-height: 360px; background: #000; object-fit: contain;
#         }
#         .call-area { display: flex; gap: 20px; margin-bottom: 20px; }
#         .audio-indicator, .call-video {
#             flex: 1; height: 200px; border-radius: 10px;
#             display: flex; flex-direction: column;
#             align-items: center; justify-content: center;
#             background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
#             color: white; font-size: 1.1em;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2);
#         }
#         .call-video { background: #2d3748; }
#         .indicator-icon { font-size: 3em; margin-bottom: 10px; }
#         .indicator-text { text-align: center; }
#         .controls { display: flex; justify-content: center; gap: 15px; }
#         button {
#             padding: 12px 25px; border: none; border-radius: 25px;
#             font-size: 16px; font-weight: 500; cursor: pointer;
#             transition: all 0.3s ease;
#             box-shadow: 0 4px 15px rgba(0,0,0,0.2); color: white;
#         }
#         #startBtn { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
#         #endBtn { background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%); }
#         button:disabled { opacity: 0.6; cursor: not-allowed; }
#         .footer { text-align: center; color: white; margin-top: 30px; font-size: 0.9em; opacity: 0.8; }
#         @media (max-width: 768px) { .main-content { grid-template-columns: 1fr; } }
#     </style>
# </head>
# <body>
#     <div class="container">
#         <div class="header">
#             <h1>🛡️ 跌倒检测监控系统</h1>
#             <p>实时监控与语音通话</p>
#         </div>
        
#         <div class="status-bar">
#             <div class="status-item">连接状态: <span id="ws_status">未连接</span></div>
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
#         <div class="footer"><p>© 2024 AI Guardian System | 支持蓝牙耳机语音通话</p></div>
#     </div>

#     <script>
#         let ws;
#         let audioCtx;
#         let scriptNode;
#         let source;
#         const SAMPLE_RATE = 48000;
#         const wsUrl = "ws://" + window.location.host + "/ws/intercom";

#         function updateStatus(text) { document.getElementById('ws_status').innerText = text; }
#         function updateMic(text) { 
#             document.getElementById('mic_status').innerText = text;
#             document.getElementById('mic_status_small').innerText = text;
#         }
#         function updateRemote(text) { document.getElementById('remote_status').innerText = text; }
#         function toggleBtns(active) {
#             document.getElementById('startBtn').disabled = active;
#             document.getElementById('endBtn').disabled = !active;
#         }

#         async function startCall() {
#             try {
#                 updateStatus('正在连接...');
                
#                 // 1. 初始化 AudioContext
#                 audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
                
#                 // 2. 获取麦克风 (这里最关键，需要浏览器配置白名单)
#                 if (!navigator.mediaDevices) {
#                     throw new Error("浏览器安全限制：无法访问麦克风。请配置 chrome://flags");
#                 }
#                 const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
#                 updateMic('工作中');
                
#                 // 3. 连接 WebSocket
#                 ws = new WebSocket(wsUrl);
#                 ws.binaryType = 'arraybuffer';
                
#                 ws.onopen = () => {
#                     updateStatus('通话中 (已连接)');
#                     updateRemote('在线');
#                     toggleBtns(true);
                    
#                     // 4. 发送音频
#                     source = audioCtx.createMediaStreamSource(stream);
#                     scriptNode = audioCtx.createScriptProcessor(2048, 1, 1);
#                     source.connect(scriptNode);
#                     scriptNode.connect(audioCtx.destination);
                    
#                     scriptNode.onaudioprocess = (e) => {
#                         if (ws.readyState === 1) {
#                             const input = e.inputBuffer.getChannelData(0);
#                             ws.send(floatTo16BitPCM(input));
#                         }
#                     };
#                 };

#                 // 5. 接收音频
#                 ws.onmessage = (e) => playPcm(e.data);
#                 ws.onclose = () => endCall();
#                 ws.onerror = (e) => { console.error(e); updateStatus('连接错误'); };

#             } catch (err) {
#                 alert("启动失败: " + err.message);
#                 console.error(err);
#                 endCall();
#             }
#         }

#         function endCall() {
#             if (ws) ws.close();
#             if (source) source.disconnect();
#             if (scriptNode) scriptNode.disconnect();
#             if (audioCtx) audioCtx.close();
#             updateStatus('已断开');
#             updateMic('未启动');
#             updateRemote('等待连接');
#             toggleBtns(false);
#         }

#         function playPcm(buffer) {
#             if (!audioCtx) return;
#             const int16 = new Int16Array(buffer);
#             const float32 = new Float32Array(int16.length);
#             for(let i=0; i<int16.length; i++) float32[i] = int16[i] / 32768.0;
#             const audioBuf = audioCtx.createBuffer(1, float32.length, SAMPLE_RATE);
#             audioBuf.getChannelData(0).set(float32);
#             const node = audioCtx.createBufferSource();
#             node.buffer = audioBuf;
#             node.connect(audioCtx.destination);
#             node.start();
#         }

#         function floatTo16BitPCM(input) {
#             let output = new Int16Array(input.length);
#             for (let i = 0; i < input.length; i++) {
#                 let s = Math.max(-1, Math.min(1, input[i]));
#                 output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
#             }
#             return output.buffer;
#         }
#     </script>
# </body>
# </html>
# """

# @app.get("/")
# async def get_index():
#     return HTMLResponse(content=HTML_TEMPLATE)

# # ==========================================
# # 4. 主程序入口
# # ==========================================
# def run_system():
#     # 启动音频
#     threading.Thread(target=audio_hw.start_audio_service, daemon=True).start()
#     threading.Thread(target=mic_broadcast_loop, daemon=True).start()

#     # 启动 YOLO (精简版循环)
#     def inference_loop():
#         detector = AclLiteStreamDetector(model_path="/root/yolo/best.om", camera_index=0)
#         mqtt_client = MQTTAlertClient()
#         if detector.init():
#             try:
#                 while detector.running:
#                     res = detector.get_detected_frame()
#                     if res is None: break
#                     frame, alerts = res
#                     update_frame(frame) # 更新视频
#                     for alert in alerts:
#                         if "FALL" in alert.get('status', ''):
#                             mqtt_client.publish_fall_alert()
#                             break
#                     time.sleep(0.001)
#             finally:
#                 detector.stop()
#     threading.Thread(target=inference_loop, daemon=True).start()

#     print("🚀 服务器启动中... 请访问: http://192.168.137.100:5000")
#     uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")

# if __name__ == "__main__":
#     run_system()





# import sys
# import os
# import time
# import socket
# import asyncio
# import threading
# import uvicorn
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# from fastapi.responses import HTMLResponse, StreamingResponse

# # --- 路径设置 ---
# current_dir = os.path.dirname(os.path.abspath(__file__))
# sys.path.append(current_dir)

# import ascend_voice_stream as audio_hw
# import ascend_video_stream as video_hw
# from ascend_main_other import AclLiteStreamDetector, MQTTAlertClient 

# app = FastAPI()
# ws_clients = []

# # --- 获取本机 IP ---
# def get_host_ip():
#     try:
#         s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         s.connect(('8.8.8.8', 80))
#         ip = s.getsockname()[0]
#     except Exception:
#         ip = '127.0.0.1'
#     finally:
#         s.close()
#     return ip

# BOARD_IP = get_host_ip()
# TARGET_PORT = 5000  # <--- 已修改为 5000

# # --- HTML 模板 ---
# HTML_CONTENT = f"""
# <!DOCTYPE html>
# <html lang="zh">
# <head>
#     <meta charset="UTF-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <title>Ascend 监控终端 ({BOARD_IP}:{TARGET_PORT})</title>
#     <style>
#         body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a1a; color: #fff; text-align: center; padding: 20px; }}
#         .container {{ max-width: 900px; margin: 0 auto; }}
#         h1 {{ color: #4facfe; text-shadow: 0 0 10px rgba(79,172,254,0.5); }}
#         #video-box {{ 
#             border: 3px solid #333; border-radius: 12px; overflow: hidden; 
#             margin-bottom: 20px; background: #000; min-height: 480px; 
#             box-shadow: 0 10px 30px rgba(0,0,0,0.5);
#         }}
#         img {{ width: 100%; height: auto; display: block; }}
#         .controls {{ 
#             background: #2d2d2d; padding: 20px; border-radius: 15px; 
#             display: flex; justify-content: space-around; align-items: center; 
#             box-shadow: 0 5px 15px rgba(0,0,0,0.3);
#         }}
#         button {{ 
#             padding: 15px 40px; font-size: 18px; border: none; border-radius: 50px; 
#             cursor: pointer; transition: all 0.3s; color: white; font-weight: bold;
#         }}
#         .btn-start {{ background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: #000; }}
#         .btn-start:hover {{ transform: scale(1.05); box-shadow: 0 0 20px rgba(67,233,123,0.6); }}
#         .btn-stop {{ background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%); color: #444; }}
#         .status-txt {{ margin-top: 5px; color: #888; font-size: 14px; }}
#         #ws-state {{ font-weight: bold; color: #ff5e62; }}
#     </style>
# </head>
# <body>
#     <div class="container">
#         <h1>🛡️ 昇腾实时监控系统</h1>
#         <div id="video-box">
#             <img src="/video_feed" onload="console.log('Video stream OK')" onerror="this.alt='❌ 视频流连接失败'">
#         </div>
#         <div class="controls">
#             <div style="text-align:left">
#                 <div id="status-text" style="font-size:1.2em">系统就绪</div>
#                 <div class="status-txt">连接状态: <span id="ws-state">未连接</span></div>
#                 <div class="status-txt">访问地址: http://{BOARD_IP}:{TARGET_PORT}</div>
#             </div>
#             <button id="btn-talk" class="btn-start" onclick="toggleCall()">📞 开始对讲</button>
#         </div>
#         <p style="color: #fce38a; font-size: 13px; margin-top: 25px; background: rgba(255,255,255,0.1); padding: 10px; border-radius: 5px;">
#             ⚠️ 麦克风权限提示：<br>
#             请在浏览器地址栏输入 <b>chrome://flags/#unsafely-treat-insecure-origin-as-secure</b><br>
#             将 <b>http://{BOARD_IP}:{TARGET_PORT}</b> 添加到白名单并重启浏览器。
#         </p>
#     </div>

#     <script>
#         let ws;
#         let isCalling = false;
#         let audioCtx;
#         let scriptNode;
#         let micSource;
#         const SAMPLE_RATE = 48000;
#         const statusText = document.getElementById("status-text");
#         const wsState = document.getElementById("ws-state");
#         const btn = document.getElementById("btn-talk");

#         function playPCM(arrayBuffer) {{
#             if (!audioCtx) return;
#             let int16 = new Int16Array(arrayBuffer);
#             let float32 = new Float32Array(int16.length);
#             for (let i=0; i<int16.length; i++) float32[i] = int16[i] / 32768.0;
#             let audioBuffer = audioCtx.createBuffer(1, float32.length, SAMPLE_RATE);
#             audioBuffer.getChannelData(0).set(float32);
#             let source = audioCtx.createBufferSource();
#             source.buffer = audioBuffer;
#             source.connect(audioCtx.destination);
#             source.start();
#         }}

#         function floatTo16BitPCM(input) {{
#             let output = new Int16Array(input.length);
#             for (let i = 0; i < input.length; i++) {{
#                 let s = Math.max(-1, Math.min(1, input[i]));
#                 output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
#             }}
#             return output.buffer;
#         }}

#         async function toggleCall() {{
#             if (!isCalling) startCall();
#             else endCall();
#         }}

#         async function startCall() {{
#             try {{
#                 statusText.innerText = "⏳ 正在请求权限...";
#                 audioCtx = new (window.AudioContext || window.webkitAudioContext)({{sampleRate: SAMPLE_RATE}});
                
#                 const stream = await navigator.mediaDevices.getUserMedia({{ audio: true, video: false }});
                
#                 // 动态构建 WebSocket 地址
#                 let wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
#                 ws = new WebSocket(wsProtocol + "://" + window.location.host + "/ws/intercom");
#                 ws.binaryType = 'arraybuffer';

#                 ws.onopen = () => {{
#                     isCalling = true;
#                     btn.innerText = "❌ 结束通话";
#                     btn.className = "btn-stop";
#                     statusText.innerText = "🎙️ 通话中...";
#                     statusText.style.color = "#43e97b";
#                     wsState.innerText = "已连接";
#                     wsState.style.color = "#43e97b";

#                     micSource = audioCtx.createMediaStreamSource(stream);
#                     scriptNode = audioCtx.createScriptProcessor(2048, 1, 1);
#                     micSource.connect(scriptNode);
#                     scriptNode.connect(audioCtx.destination);

#                     scriptNode.onaudioprocess = (e) => {{
#                         if (ws.readyState === WebSocket.OPEN) {{
#                             ws.send(floatTo16BitPCM(e.inputBuffer.getChannelData(0)));
#                         }}
#                     }};
#                 }};

#                 ws.onmessage = (e) => playPCM(e.data);
#                 ws.onclose = () => endCall();
#                 ws.onerror = (e) => {{ console.error(e); statusText.innerText = "❌ 连接错误"; }};

#             }} catch (err) {{
#                 alert("无法启动麦克风:\\n" + err.message + "\\n\\n请按照页面底部的黄色提示配置浏览器白名单！");
#                 endCall();
#             }}
#         }}

#         function endCall() {{
#             isCalling = false;
#             if (ws) {{ ws.close(); ws = null; }}
#             if (micSource) micSource.disconnect();
#             if (scriptNode) scriptNode.disconnect();
#             if (audioCtx) audioCtx.close();
            
#             btn.innerText = "📞 开始对讲";
#             btn.className = "btn-start";
#             statusText.innerText = "系统就绪";
#             statusText.style.color = "white";
#             wsState.innerText = "未连接";
#             wsState.style.color = "#ff5e62";
#         }}
#     </script>
# </body>
# </html>
# """

# @app.get("/")
# async def get_index():
#     return HTMLResponse(content=HTML_CONTENT)

# @app.get("/video_feed")
# async def video_feed():
#     def generate():
#         while True:
#             frame_data = video_hw.get_current_frame()
#             if frame_data:
#                 yield (b'--frame\r\n'
#                        b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
#             time.sleep(0.04) 
#     return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

# @app.websocket("/ws/intercom")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     ws_clients.append(websocket)
#     try:
#         while True:
#             data = await websocket.receive_bytes()
#             audio_hw.put_audio_frame(data)
#     except:
#         if websocket in ws_clients: ws_clients.remove(websocket)

# async def mic_broadcast_task():
#     print("🚀 音频广播服务已就绪")
#     while True:
#         frame = audio_hw.get_audio_frame()
#         if frame and ws_clients:
#             for client in ws_clients:
#                 try: await client.send_bytes(frame)
#                 except: pass
#         else:
#             await asyncio.sleep(0.01)

# def run_system():
#     # 1. 启动音频 (守护线程)
#     threading.Thread(target=audio_hw.start_audio_service, daemon=True).start()

#     # 2. 启动 YOLO (守护线程)
#     def inference_loop():
#         detector = AclLiteStreamDetector(model_path="/root/yolo/best.om", camera_index=0)
#         mqtt_client = MQTTAlertClient()
#         if detector.init():
#             try:
#                 while detector.running:
#                     res = detector.get_detected_frame()
#                     if res is None: break
#                     frame, alerts = res
#                     video_hw.update_frame(frame)
#                     for alert in alerts:
#                         if "FALL" in alert.get('status', ''):
#                             mqtt_client.publish_fall_alert()
#                             break
#                     time.sleep(0.005) 
#             finally:
#                 detector.stop()
#     threading.Thread(target=inference_loop, daemon=True).start()

#     # 3. 注册启动事件
#     @app.on_event("startup")
#     async def startup_event():
#         asyncio.create_task(mic_broadcast_task())

#     # 4. 打印巨大的提示信息
#     print("\n" + "="*50)
#     print(f"✅ 系统启动成功！")
#     print(f"🌍 请在电脑浏览器访问: http://{BOARD_IP}:{TARGET_PORT}")
#     print(f"⚠️  如果无法访问，请在板子上运行: iptables -F")
#     print("="*50 + "\n")

#     # 5. 启动 Web 服务 (端口 5000)
#     uvicorn.run(app, host="0.0.0.0", port=TARGET_PORT, log_level="error")

# if __name__ == "__main__":
#     run_system()
import sys
import os
import time
import socket
import asyncio
import threading
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse

# --- 路径设置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

import ascend_voice_stream as audio_hw
import ascend_video_stream as video_hw
from ascend_main_other import AclLiteStreamDetector, MQTTAlertClient 

app = FastAPI()
ws_clients = []

# --- 获取本机 IP ---
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

# ==========================================
# 👇 恢复你最开始的 UI 设计 (HTML/CSS) 👇
# ==========================================
HTML_CONTENT = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>跌倒检测监控 - 语音通话</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; color: white; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }}
        .status-bar {{
            background: rgba(255,255,255,0.1); padding: 15px;
            border-radius: 10px; margin-bottom: 20px;
            backdrop-filter: blur(10px); color: white; text-align: center;
        }}
        .status-item {{ display: inline-block; margin: 0 20px; font-weight: 500; }}
        .main-content {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px; }}
        .video-section, .call-section {{
            background: rgba(255,255,255,0.95); border-radius: 15px;
            padding: 25px; box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-size: 1.5em; margin-bottom: 20px; color: #4a5568;
            border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;
        }}
        #videoFeed {{
            width: 100%; border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            min-height: 360px; background: #000; object-fit: contain;
        }}
        .call-area {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .audio-indicator, .call-video {{
            flex: 1; height: 200px; border-radius: 10px;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white; font-size: 1.1em;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }}
        .call-video {{ background: #2d3748; }}
        .indicator-icon {{ font-size: 3em; margin-bottom: 10px; }}
        .indicator-text {{ text-align: center; }}
        .controls {{ display: flex; justify-content: center; gap: 15px; }}
        button {{
            padding: 12px 25px; border: none; border-radius: 25px;
            font-size: 16px; font-weight: 500; cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); color: white;
        }}
        #startBtn {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
        #endBtn {{ background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%); }}
        button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
        .footer {{ text-align: center; color: white; margin-top: 30px; font-size: 0.9em; opacity: 0.8; }}
        .ip-hint {{ font-size: 0.8em; margin-top: 5px; color: #eee; }}
        @media (max-width: 768px) {{ .main-content {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ 跌倒检测监控系统</h1>
            <p>实时监控与语音通话</p>
            <div class="ip-hint">访问地址: http://{BOARD_IP}:{TARGET_PORT}</div>
        </div>
        
        <div class="status-bar">
            <div class="status-item">连接状态: <span id="ws_status">未连接</span></div>
            <div class="status-item">麦克风: <span id="mic_status">未启动</span></div>
        </div>
        
        <div class="main-content">
            <div class="video-section">
                <h2 class="section-title">📹 实时视频监控</h2>
                <img id="videoFeed" src="/video_feed" alt="实时监控视频流" onerror="this.alt='无法连接视频流'">
            </div>
            
            <div class="call-section">
                <h2 class="section-title">🎤 语音通话</h2>
                <div class="call-area">
                    <div class="audio-indicator">
                        <div class="indicator-icon">🎧</div>
                        <div class="indicator-text">
                            <div>本地麦克风</div>
                            <div id="mic_status_small" style="font-size: 0.8em; opacity: 0.8;">未启动</div>
                        </div>
                    </div>
                    <div class="call-video">
                        <div class="indicator-icon">📞</div>
                        <div class="indicator-text">
                            <div>远程音频</div>
                            <div id="remote_status" style="font-size: 0.8em; opacity: 0.8;">等待连接</div>
                        </div>
                    </div>
                </div>
                <div class="controls">
                    <button id="startBtn" onclick="startCall()">📞 发起通话</button>
                    <button id="endBtn" onclick="endCall()" disabled>❌ 结束通话</button>
                </div>
                <div style="margin-top:15px; font-size:0.8em; color:#666; text-align:center;">
                    如果无法启动，请在 chrome://flags 中配置 Insecure origins treated as secure
                </div>
            </div>
        </div>
        <div class="footer"><p>© 2025 AI Guardian System | 支持昇腾开发板</p></div>
    </div>

    <script>
        let ws;
        let audioCtx;
        let scriptNode;
        let micSource;
        const SAMPLE_RATE = 48000;

        // UI 辅助函数
        function updateStatus(text) {{ document.getElementById('ws_status').innerText = text; }}
        function updateMic(text) {{ 
            document.getElementById('mic_status').innerText = text;
            document.getElementById('mic_status_small').innerText = text;
        }}
        function updateRemote(text) {{ document.getElementById('remote_status').innerText = text; }}
        function toggleBtns(active) {{
            document.getElementById('startBtn').disabled = active;
            document.getElementById('endBtn').disabled = !active;
        }}

        async function startCall() {{
            try {{
                updateStatus('正在连接...');
                
                // 1. 初始化 AudioContext
                audioCtx = new (window.AudioContext || window.webkitAudioContext)({{ sampleRate: SAMPLE_RATE }});
                
                // 2. 获取麦克风
                const stream = await navigator.mediaDevices.getUserMedia({{ audio: true, video: false }});
                updateMic('工作中');
                
                // 3. 连接 WebSocket (自动构建地址)
                const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
                const wsUrl = protocol + "://" + window.location.host + "/ws/intercom";
                ws = new WebSocket(wsUrl);
                ws.binaryType = 'arraybuffer';
                
                ws.onopen = () => {{
                    updateStatus('通话中 (已连接)');
                    updateRemote('在线');
                    toggleBtns(true);
                    
                    // 4. 音频采集处理
                    micSource = audioCtx.createMediaStreamSource(stream);
                    scriptNode = audioCtx.createScriptProcessor(2048, 1, 1);
                    micSource.connect(scriptNode);
                    scriptNode.connect(audioCtx.destination);
                    
                    scriptNode.onaudioprocess = (e) => {{
                        if (ws.readyState === WebSocket.OPEN) {{
                            const input = e.inputBuffer.getChannelData(0);
                            ws.send(floatTo16BitPCM(input));
                        }}
                    }};
                }};

                // 5. 接收音频并播放
                ws.onmessage = (e) => playPcm(e.data);
                ws.onclose = () => endCall();
                ws.onerror = (e) => {{ console.error(e); updateStatus('连接错误'); }};

            }} catch (err) {{
                alert("启动失败: " + err.message + "\\n请检查 chrome://flags 白名单配置！");
                console.error(err);
                endCall();
            }}
        }}

        function endCall() {{
            if (ws) {{ ws.close(); ws = null; }}
            if (micSource) micSource.disconnect();
            if (scriptNode) scriptNode.disconnect();
            if (audioCtx) audioCtx.close();
            
            updateStatus('已断开');
            updateMic('未启动');
            updateRemote('等待连接');
            toggleBtns(false);
        }}

        function playPcm(buffer) {{
            if (!audioCtx) return;
            const int16 = new Int16Array(buffer);
            const float32 = new Float32Array(int16.length);
            for(let i=0; i<int16.length; i++) float32[i] = int16[i] / 32768.0;
            const audioBuf = audioCtx.createBuffer(1, float32.length, SAMPLE_RATE);
            audioBuf.getChannelData(0).set(float32);
            const node = audioCtx.createBufferSource();
            node.buffer = audioBuf;
            node.connect(audioCtx.destination);
            node.start();
        }}

        function floatTo16BitPCM(input) {{
            let output = new Int16Array(input.length);
            for (let i = 0; i < input.length; i++) {{
                let s = Math.max(-1, Math.min(1, input[i]));
                output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }}
            return output.buffer;
        }}
    </script>
</body>
</html>
"""

# ==========================================
# 后端逻辑 (保持不变)
# ==========================================

@app.get("/")
async def get_index():
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/video_feed")
async def video_feed():
    def generate():
        while True:
            frame_data = video_hw.get_current_frame()
            if frame_data:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            time.sleep(0.04) 
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws/intercom")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_bytes()
            audio_hw.put_audio_frame(data)
    except:
        if websocket in ws_clients: ws_clients.remove(websocket)

async def mic_broadcast_task():
    print("🚀 音频广播服务已就绪")
    while True:
        frame = audio_hw.get_audio_frame()
        if frame and ws_clients:
            for client in ws_clients:
                try: await client.send_bytes(frame)
                except: pass
        else:
            await asyncio.sleep(0.01)

def run_system():
    # 1. 启动硬件音频
    threading.Thread(target=audio_hw.start_audio_service, daemon=True).start()

    # 2. 启动 YOLO
    def inference_loop():
        detector = AclLiteStreamDetector(model_path="/root/yolo/best.om", camera_index=0)
        mqtt_client = MQTTAlertClient()
        if detector.init():
            try:
                while detector.running:
                    res = detector.get_detected_frame()
                    if res is None: break
                    frame, alerts = res
                    video_hw.update_frame(frame)
                    for alert in alerts:
                        if "FALL" in alert.get('status', ''):
                            mqtt_client.publish_fall_alert()
                            break
                    time.sleep(0.005) 
            finally:
                detector.stop()
    threading.Thread(target=inference_loop, daemon=True).start()

    # 3. 注册启动事件
    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(mic_broadcast_task())

    # 4. 打印提示
    print("\n" + "="*50)
    print(f"✅ 系统启动成功！")
    print(f"🌍 访问地址: http://{BOARD_IP}:{TARGET_PORT}")
    print(f"   (使用原版 UI 界面)")
    print("="*50 + "\n")

    # 5. 启动 Web 服务
    uvicorn.run(app, host="0.0.0.0", port=TARGET_PORT, log_level="error")

if __name__ == "__main__":
    run_system()