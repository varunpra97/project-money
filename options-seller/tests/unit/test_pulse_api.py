"""Chart transport and assistant authorization regressions."""
import asyncio
import json
import unittest
from unittest.mock import patch
import pandas as pd
from fastapi import HTTPException
from starlette.requests import Request
from api import main, assistant
class QuoteTests(unittest.TestCase):
    def setUp(self): main._cache.clear(); main.quote_cache.values.clear()
    def test_ohlc_volume_preserved_and_bad_rows_dropped(self):
        frame=pd.DataFrame({'Open':[10,11],'High':[13,float('nan')],'Low':[9,10],'Close':[12,11],'Volume':[1234,100]},index=pd.date_range('2026-01-01',periods=2,tz='UTC'))
        with patch('yfinance.download',return_value=frame): result=asyncio.run(main.quote('TEST','1mo',True))
        self.assertEqual(result['bars'],[{'t':1767225600,'o':10,'h':13,'l':9,'c':12,'v':1234}])
    def test_empty_provider_response_not_cached(self):
        with patch('yfinance.download',return_value=pd.DataFrame()): result=asyncio.run(main.quote('TEST','1mo',True))
        self.assertEqual(result.status_code,502)
        self.assertNotIn('quote:TEST:1mo',main._cache)
class AssistantSecurityTests(unittest.TestCase):
    def request(self,host='localhost:8505',origin=None,client='127.0.0.1',token=''):
        headers=[(b'host',host.encode()),(b'x-pulse-assistant',b'1'),(b'authorization',('Bearer '+token).encode())]
        if origin: headers.append((b'origin',origin.encode()))
        return Request({'type':'http','scheme':'http','path':'/api/assistant/status','headers':headers,'client':(client,123)})
    def test_cross_origin_rejected(self):
        with self.assertRaises(HTTPException): assistant.check_origin(self.request(origin='https://evil.example'))
    def test_rebinding_host_rejected(self):
        with self.assertRaises(HTTPException): assistant.check_origin(self.request(host='evil.example'))
    def test_remote_bootstrap_rejected(self):
        with self.assertRaises(HTTPException): asyncio.run(assistant.bootstrap(self.request(client='10.0.0.2')))
    def test_wrong_token_rejected(self):
        with patch.object(assistant,'secret_token',return_value='test-only-secret'):
            with self.assertRaises(HTTPException): asyncio.run(assistant.authorize(self.request(token='wrong')))
    def test_expired_pairing_rejected(self):
        with patch.object(assistant.Pairing,'expires',0),patch.object(assistant.Pairing,'attempts',{}):
            with self.assertRaises(HTTPException): asyncio.run(assistant.pair(assistant.PairInput(code='12345678'),self.request()))
if __name__=='__main__': unittest.main()
