# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        # 存放所有连接的客户端（包括网页端和昇腾板子）
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"客户端已连接，当前在线: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"客户端断开，当前在线: {len(self.active_connections)}")

    async def broadcast(self, message: bytes, sender: WebSocket):
        """
        将音频数据广播给除发送者以外的所有人
        """
        for connection in self.active_connections:
            if connection != sender:
                try:
                    await connection.send_bytes(message)
                except Exception:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket)
    try:
        while True:
            # 接收二进制数据 (PCM音频)
            data = await websocket.receive_bytes()
            # 广播给其他客户端
            await manager.broadcast(data, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    # 监听 0.0.0.0 允许局域网访问
    uvicorn.run(app, host="0.0.0.0", port=8000)