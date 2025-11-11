import asyncio
import aiohttp
import json
import os
import traceback

HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = os.environ["HA_TOKEN"]
SERVER_URL = "wss://your-cloudrun-service-xyz.a.run.app/ws"
AUTH_TOKEN = os.environ["OASIRA_TOKEN"]

# Helper to call Home Assistant local API
async def call_home_assistant(method: str, path: str, body=None):
    try:
        async with aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {HA_TOKEN}",
                "Content-Type": "application/json",
            }
        ) as session:
            async with session.request(
                method,
                f"{HA_URL}{path}",
                json=body,
            ) as resp:
                text = await resp.text()
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text, "status": resp.status}
    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}

async def handle_command(ws, cmd):
    """Handles an inbound command from Cloud Run."""
    try:
        cmd_id = cmd.get("id")
        method = cmd.get("method", "GET")
        path = cmd.get("path", "/api/")
        body = cmd.get("body")

        print(f"→ Executing HA request: {method} {path}")
        result = await call_home_assistant(method, path, body)
        print(f"← Sending result for {cmd_id}")
        await ws.send_json({"type": "response", "id": cmd_id, "result": result})

    except Exception as e:
        await ws.send_json(
            {"type": "response", "id": cmd.get("id"), "error": str(e)}
        )

async def maintain_connection():
    """Main connection loop with auto-reconnect and heartbeats."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    SERVER_URL,
                    headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
                    heartbeat=25,  # ping Cloud Run every 25s
                ) as ws:
                    print("✅ Connected to Cloud Run")

                    # Identify this client (optional)
                    await ws.send_json({"type": "hello", "info": "HA bridge ready"})

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                            except Exception:
                                print("Invalid JSON from server:", msg.data)
                                continue

                            msg_type = data.get("type", "command")

                            if msg_type == "command":
                                await handle_command(ws, data)
                            elif msg_type == "ping":
                                await ws.send_json({"type": "pong"})
                            else:
                                print("Unknown message type:", data)

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print("WebSocket error:", msg.data)
                            break

        except Exception as e:
            print(f"⚠️ Connection lost: {e}")
            await asyncio.sleep(10)
            print("🔁 Reconnecting...")

async def main():
    await maintain_connection()

if __name__ == "__main__":
    asyncio.run(main())
