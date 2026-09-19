"""Single-flight asynchronous cache; stale replies are explicitly labelled."""
import asyncio
import time

class AsyncCache:
    def __init__(self):
        self.values = {}
        self.inflight = {}
        self.fetches = {}
        self.worker = None
        self.gate = asyncio.Semaphore(4)
    def response(self, entry, stale=False, error=None):
        _, updated, value = entry
        result = dict(value)
        result['cache_stale'] = stale
        result['cache_age_seconds'] = round(max(0,time.time()-updated),3)
        if error: result['cache_warning'] = str(error)
        return result
    async def get(self, key, fetch, ttl=20, force=False, max_stale=600, timeout=15, touch=True):
        now = time.monotonic()
        if touch:
            if len(self.fetches)>=512 and key not in self.fetches:
                self.fetches.pop(next(iter(self.fetches)))
            self.fetches[key]=(fetch,ttl,now)
        hit = self.values.get(key)
        if not force and hit and hit[0] > now: return self.response(hit)
        task = self.inflight.get(key)
        if task is None:
            async def refresh():
                async with self.gate:
                    value = await asyncio.to_thread(fetch)
                if isinstance(value,dict) and value.get('error'): raise RuntimeError(value['error'])
                entry=(time.monotonic()+ttl,time.time(),value)
                if len(self.values)>=512 and key not in self.values:
                    self.values.pop(next(iter(self.values)))
                self.values[key]=entry
                return entry
            task=asyncio.create_task(refresh())
            self.inflight[key]=task
            def done(t):
                if self.inflight.get(key) is t: self.inflight.pop(key,None)
                if not t.cancelled(): t.exception()  # consume background failures
            task.add_done_callback(done)
        if not force and hit and hit[0]+max_stale>now:
            return self.response(hit,stale=True)
        try:
            fresh=await asyncio.wait_for(asyncio.shield(task),timeout)
            return self.response(fresh)
        except Exception as error:
            if hit and hit[0]+max_stale>now: return self.response(hit,stale=True,error=error)
            raise
    async def maintain(self):
        while True:
            now=time.monotonic()
            self.fetches={k:v for k,v in self.fetches.items() if now-v[2]<900}
            for key,(fetch,ttl,_) in list(self.fetches.items()):
                hit=self.values.get(key)
                if key not in self.inflight and (hit is None or hit[0]<=now+5):
                    # Start a refresh without blocking upkeep of other symbols.
                    task=asyncio.create_task(self.get(key,fetch,ttl=ttl,force=True,touch=False))
                    task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
            await asyncio.sleep(5)
    async def close(self):
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker,return_exceptions=True)

        pending=list(self.inflight.values())
        for task in pending:task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        self.inflight.clear()

quote_cache=AsyncCache()
