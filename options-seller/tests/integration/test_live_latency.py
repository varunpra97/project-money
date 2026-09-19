"""Real TCP/HTTP streaming tests. Measures backend-ingress to SSE-client latency.

Run: PYTHONPATH=src:. api/.venv-pulse/bin/python -m unittest discover -s tests/integration -p test_live_latency.py -v
This isolates our delivery path from Yahoo latency. It is not a WAN/phone benchmark.
"""
import asyncio
import json
import socket
import statistics
import time
import unittest
from unittest.mock import patch
import pandas as pd
from fastapi import FastAPI
import uvicorn
from api import live

class SSEClient:
    async def connect(self, port):
        self.reader,self.writer=await asyncio.open_connection('127.0.0.1',port)
        self.writer.write(b'GET /api/live/events?symbols=TEST HTTP/1.1\r\nHost: localhost\r\nAccept: text/event-stream\r\n\r\n')
        await self.writer.drain()
        headers=await self.reader.readuntil(b'\r\n\r\n')
        assert b'200 OK' in headers,headers
        assert b'transfer-encoding: chunked' in headers.lower()
        return self
    async def event(self):
        while True:
            size=int((await asyncio.wait_for(self.reader.readline(),2)).strip(),16)
            if not size:raise EOFError('SSE stream closed')
            chunk=await self.reader.readexactly(size)
            await self.reader.readexactly(2)
            for line in chunk.splitlines():
                if line.startswith(b'data: '):return json.loads(line[6:])
    async def close(self):
        self.writer.close();await self.writer.wait_closed()

class LiveLatencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.feed=live.LivePrices()
        self.patch=patch.object(live,'live_prices',self.feed);self.patch.start()
        app=FastAPI();app.include_router(live.router)
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0));self.sock.listen();self.sock.setblocking(False)
        self.port=self.sock.getsockname()[1]
        self.server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
        self.task=asyncio.create_task(self.server.serve(sockets=[self.sock]))
        for _ in range(100):
            if self.server.started:break
            await asyncio.sleep(.01)
        self.assertTrue(self.server.started)
        self.clients=[]
    async def client(self):
        c=await SSEClient().connect(self.port);self.clients.append(c);return c
    async def asyncTearDown(self):
        for c in self.clients:await c.close()
        self.server.should_exit=True
        await asyncio.wait_for(self.task,5)
        self.patch.stop()
    def tick(self,price,stamp=None):
        self.feed.receive({'id':'TEST','price':price,'time':(stamp or time.time())*1000})
    async def test_latency_under_slow_provider_with_three_clients(self):
        clients=[await self.client() for _ in range(3)]
        for c in clients:await c.event()
        # Exercise the production HTTP-fallback path during a slow provider call.
        def slow_history(*args, **kwargs):
            time.sleep(1)
            return pd.DataFrame()
        provider_patch=patch('yfinance.Ticker')
        ticker=provider_patch.start()
        self.addCleanup(provider_patch.stop)
        ticker.return_value.history.side_effect=slow_history
        slow=asyncio.create_task(self.feed.poll('SLOW'))
        durations=[]
        for i in range(100):
            start=time.perf_counter()
            self.tick(100+i)
            packets=await asyncio.gather(*(c.event() for c in clients))
            durations.append((time.perf_counter()-start)*1000)
            for p in packets:
                self.assertEqual(p['quotes'][0]['price'],100+i)
                self.assertEqual(p['quotes'][0]['state'],'stream')
            await asyncio.sleep(.005)
        await slow
        ordered=sorted(durations);p95=ordered[94]
        print(f'\n100 updates / 3 TCP clients: p50={statistics.median(durations):.2f}ms p95={p95:.2f}ms max={max(durations):.2f}ms',flush=True)
        self.assertLess(p95,250,'Delivery regression: p95 exceeds 250ms local budget')
        self.assertLess(max(durations),1000,'Delivery unexpectedly blocked for a second')
    async def test_reconnect_gets_latest_and_old_ticks_do_not_replace_new(self):
        now=time.time();self.tick(200,now)
        first=await self.client();self.assertEqual((await first.event())['quotes'][0]['price'],200)
        self.tick(100,now-100)
        second=await self.client();self.assertEqual((await second.event())['quotes'][0]['price'],200)
    async def test_stale_data_is_not_labelled_streaming(self):
        self.tick(200,time.time()-300)
        c=await self.client();q=(await c.event())['quotes'][0]
        self.assertEqual(q['state'],'stale');self.assertGreaterEqual(q['age_seconds'],300)
    async def test_bad_ticks_are_ignored(self):
        self.tick(200)
        self.feed.receive({'id':'TEST','price':float('nan'),'time':time.time()*1000})
        self.assertEqual(self.feed.snapshot('TEST')['price'],200)

if __name__=='__main__':unittest.main()
