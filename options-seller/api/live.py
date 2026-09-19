"""Shared Yahoo price stream with bounded minute-bar fallback and explicit freshness."""
import asyncio
from datetime import datetime, timezone
import json
import math
import re
import time
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api")
class LivePrices:
    def __init__(self):
        self.quotes = {}
        self.changed = asyncio.Event()
        self.wanted = {}
        self.subscribed = set()
        self.ws = None
        self.listener = None
        self.task = None
        self.lock = asyncio.Lock()
        self.fallback_gate = asyncio.Semaphore(4)
        self.polled = {}
    def publish(self):
        self.changed.set()
        self.changed = asyncio.Event()
    def receive(self, message):
        symbol = str(message.get("id", "")).upper()
        try:
            price = float(message["price"])
            stamp = float(message["time"])
            if stamp > 1e11: stamp /= 1000
            if not symbol or not math.isfinite(price) or price <= 0 or not math.isfinite(stamp) or stamp <= 0: return
        except (KeyError, ValueError, TypeError): return
        old = self.quotes.get(symbol)
        if old and old["timestamp"] > stamp: return
        change = message.get("changePercent")
        try: change = float(change) if change is not None else None
        except (ValueError, TypeError): change = None
        if change is not None and not math.isfinite(change): change = None
        self.quotes[symbol] = {"symbol":symbol,"price":price,"timestamp":stamp,
            "received_at":time.time(),"transport":"stream","change_pct":change,"source":"Yahoo Finance"}
        self.publish()
    def snapshot(self, symbol):
        quote = self.quotes.get(symbol)
        if not quote: return {"symbol":symbol,"price":None,"state":"connecting","source":"Yahoo Finance"}
        age = max(0,time.time()-quote["timestamp"])
        return {**quote,"as_of":datetime.fromtimestamp(quote["timestamp"],timezone.utc).isoformat(),
            "age_seconds":round(age,1),"state":"stale" if age > 90 else quote["transport"],
            "note":"Provider timestamps shown; exchange delays and closed-market periods may apply."}
    async def poll(self, symbol):
        async with self.fallback_gate:
            try:
                import yfinance as yf
                bars = await asyncio.to_thread(lambda: yf.Ticker(symbol).history(period="1d",interval="1m",prepost=True,auto_adjust=False,timeout=8))
                if bars.empty: return
                row = bars.iloc[-1]; stamp=bars.index[-1].timestamp(); price=float(row['Close'])
                if not math.isfinite(price) or price<=0:return
                old=self.quotes.get(symbol)
                if old and old['timestamp']>=stamp:return
                self.quotes[symbol]={"symbol":symbol,"price":price,"timestamp":stamp,
                    "received_at":time.time(),"transport":"polling","change_pct":None,"source":"Yahoo Finance · 1-minute bar"}
                self.publish()
            except Exception:
                # Keep the last dated quote, never substitute a demo price.
                pass
    async def run(self):
        import yfinance as yf
        while True:
            try:
                active={s for s,t in self.wanted.items() if time.time()-t < 900}
                if active:
                    try:
                        # yfinance 1.7 can retain a closed socket while listen() retries.
                        # Recreate that client so subscriptions resume after a network drop.
                        socket = getattr(self.ws, "_ws", None)
                        if socket is not None and getattr(socket, "close_code", None) is not None:
                            raise ConnectionError("Provider socket closed")
                        if self.ws is None:
                            self.ws=yf.AsyncWebSocket(verbose=False)
                        new=active-self.subscribed
                        if new:
                            await asyncio.wait_for(self.ws.subscribe(sorted(new)),5)
                            self.subscribed.update(new)
                        removed=self.subscribed-active
                        if removed:
                            await asyncio.wait_for(self.ws.unsubscribe(sorted(removed)),5)
                            self.subscribed-=removed
                        if self.listener is None or self.listener.done():
                            self.listener=asyncio.create_task(self.ws.listen(self.receive))
                    except Exception:
                        if self.listener: self.listener.cancel()
                        if self.ws:
                            try: await asyncio.wait_for(self.ws.close(),2)
                            except Exception: pass
                        self.ws=None;self.listener=None;self.subscribed.clear()
                    stale=[s for s in active if time.time()-self.quotes.get(s,{}).get('received_at',0)>20 and time.time()-self.polled.get(s,0)>20]
                    for s in stale:self.polled[s]=time.time()
                    if stale: await asyncio.gather(*(self.poll(s) for s in stale))
                await asyncio.sleep(3)
            except asyncio.CancelledError: break
    async def stop(self):
        if self.task:
            self.task.cancel()
            await self.task
        if self.listener:
            self.listener.cancel()
            await asyncio.gather(self.listener,return_exceptions=True)
        if self.ws: await self.ws.close()

live_prices=LivePrices()
@router.get('/live')
async def latest(symbols: str = Query(...,max_length=300)):
    requested=list(dict.fromkeys(s.strip().upper() for s in symbols.split(',')))[:20]
    requested=[s for s in requested if re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=-]{0,19}',s)]
    async with live_prices.lock:
        live_prices.wanted={s:t for s,t in live_prices.wanted.items() if time.time()-t<900}
        # Bound subscriptions independently of clients.
        for s in requested:
            if s in live_prices.wanted or len(live_prices.wanted)<100:
                live_prices.wanted[s]=time.time()
            else: raise HTTPException(429, "Live subscription capacity reached; retry later.")
    return {"quotes":[live_prices.snapshot(s) for s in requested],"refresh_seconds":2}


@router.get('/live/events')
async def events(request: Request, symbols: str = Query(...,max_length=300)):
    initial=await latest(symbols)
    selected=[q['symbol'] for q in initial['quotes']]
    async def stream():
        while not await request.is_disconnected():
            changed=live_prices.changed
            payload={"quotes":[live_prices.snapshot(s) for s in selected],"sent_at":time.time()}
            # Every event carries its delivery timestamp and provider timestamp.
            yield 'data: '+json.dumps(payload,separators=(',',':'))+'\n\n'
            try: await asyncio.wait_for(changed.wait(),15)
            except asyncio.TimeoutError: pass
            for s in selected: live_prices.wanted[s]=time.time()
    return StreamingResponse(stream(),media_type='text/event-stream',headers={
        'Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no','Connection':'keep-alive'})
