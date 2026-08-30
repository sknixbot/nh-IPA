
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import websockets

from auth import get_access_token

WS_URL = "wss://api.nhplug.com:7070/websocket"
DB = Path("data/market_monitor.db")


def token_value():
    t = get_access_token()
    if isinstance(t, dict):
        return t.get("access_token")
    return t


def init_db():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS foreign_member_flow (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        code TEXT,
        name TEXT,
        foreign_sell INTEGER,
        foreign_buy INTEGER,
        foreign_net INTEGER,
        foreign_net_change INTEGER,
        total_sell INTEGER,
        total_buy INTEGER,
        raw_json TEXT
    )
    """)
    con.commit()
    con.close()


def save(body):
    def num(k):
        try:
            return int(float(body.get(k, 0) or 0))
        except Exception:
            return 0

    con = sqlite3.connect(DB)
    con.execute("""
    INSERT INTO foreign_member_flow (
        collected_at, code, name,
        foreign_sell, foreign_buy, foreign_net, foreign_net_change,
        total_sell, total_buy, raw_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(timespec="seconds"),
        body.get("code"),
        body.get("hname"),
        num("N_offvolall"),
        num("N_bidvolall"),
        num("N_soonmaesu"),
        num("N_soonmaecha"),
        num("N_alloffvol"),
        num("N_allbidvol"),
        json.dumps(body, ensure_ascii=False)
    ))
    con.commit()
    con.close()


async def monitor(codes, seconds=600):
    init_db()
    token = token_value()
    if not token:
        raise RuntimeError("access token을 가져오지 못했습니다.")

    if not codes:
        print("감시 종목이 없습니다. config/watchlist.txt를 확인하세요.")
        return

    print(f"[시작] {len(codes)}종목 / {seconds}초")

    async with websockets.connect(
        WS_URL,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5
    ) as ws:

        for code in codes:
            req = {
                "header": {
                    "token": token,
                    "tr_type": "1"
                },
                "body": {
                    "tr_cd": "mg",
                    "tr_key": code
                }
            }
            await ws.send(json.dumps(req, ensure_ascii=False))
            await asyncio.sleep(0.12)

        end = asyncio.get_running_loop().time() + seconds

        while asyncio.get_running_loop().time() < end:
            timeout = min(5, max(0.1, end - asyncio.get_running_loop().time()))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                continue

            try:
                msg = json.loads(raw)
            except Exception:
                continue

            body = msg.get("body")
            if not isinstance(body, dict):
                continue

            # mg 실시간 데이터만 저장
            if "N_soonmaesu" not in body:
                continue

            save(body)

            print(
                f"[{body.get('time','')}] "
                f"{body.get('hname', body.get('code',''))} "
                f"외국계순매수={body.get('N_soonmaesu')} "
                f"변화={body.get('N_soonmaecha')}"
            )

    print("[종료] 실시간 수급 수집 완료")
