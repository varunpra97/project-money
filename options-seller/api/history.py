"""Bounded historical technical scans. Signals use only information available at that bar."""
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import secrets
import threading
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Depends
from urllib.parse import urlparse
from pydantic import BaseModel, Field, model_validator
import pandas as pd
from options_seller.paths import data_dir

router=APIRouter(prefix='/api/history')
DATA=data_dir()/'historical_scanners.json'
STORE_LOCK=threading.Lock()
RULES={'sma20_cross_up':'Cross above SMA 20','above_sma200':'Close above SMA 200',
       'rsi14_oversold':'RSI 14 below 30','rsi14_overbought':'RSI 14 above 70',
       'breakout20':'Close above prior 20-bar high'}
def trusted_client(request:Request):
    if request.headers.get('x-pulse-scanner')!='1':raise HTTPException(403,'Open scanners from Pulse.')
    origin=request.headers.get('origin')
    if origin and urlparse(origin).netloc!=request.headers.get('host'):raise HTTPException(403,'Cross-site scanner changes are not allowed.')

class ScanConfig(BaseModel):
    name:str=Field(default='My scanner',min_length=1,max_length=80)
    symbols:list[str]=Field(min_length=1,max_length=20)
    start:date
    end:date
    interval:Literal['1d','1wk','1mo']='1d'
    rule:Literal['sma20_cross_up','above_sma200','rsi14_oversold','rsi14_overbought','breakout20']='sma20_cross_up'
    @model_validator(mode='after')
    def validate_config(self):
        self.symbols=list(dict.fromkeys(s.strip().upper() for s in self.symbols))
        if any(not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=-]{0,19}',s) for s in self.symbols):raise ValueError('Invalid ticker symbol')
        if self.start>self.end:raise ValueError('Start must be before end')
        if self.end>datetime.now(timezone.utc).date():raise ValueError('End cannot be in the future')
        if (self.end-self.start).days>3653:raise ValueError('Choose a range of ten years or less')
        return self

def evaluate(frame, config, symbol):
    if frame.empty:return [],'No history returned'
    frame=frame.sort_index();close=frame['Close'];high=frame['High']
    sma20=close.rolling(20,min_periods=20).mean();sma200=close.rolling(200,min_periods=200).mean()
    delta=close.diff();gain=delta.clip(lower=0);loss=-delta.clip(upper=0)
    # Wilder's seed is the first 14 arithmetic gains/losses, then recursive smoothing.
    ag=gain.rolling(14,min_periods=14).mean().copy()*float('nan');al=ag.copy()
    if len(close)>14:
        ag.iloc[14]=gain.iloc[1:15].mean();al.iloc[14]=loss.iloc[1:15].mean()
        for i in range(15,len(close)):
            ag.iloc[i]=(ag.iloc[i-1]*13+gain.iloc[i])/14
            al.iloc[i]=(al.iloc[i-1]*13+loss.iloc[i])/14
    rsi=100-100/(1+ag/al)
    rsi=rsi.mask((al==0)&(ag>0),100).mask((al==0)&(ag==0),50)
    if config.rule=='sma20_cross_up': signal=(close>sma20)&(close.shift(1)<=sma20.shift(1));indicator=sma20
    elif config.rule=='above_sma200': signal=close>sma200;indicator=sma200
    elif config.rule=='rsi14_oversold': signal=rsi<30;indicator=rsi
    elif config.rule=='rsi14_overbought': signal=rsi>70;indicator=rsi
    else:
        indicator=high.shift(1).rolling(20,min_periods=20).max();signal=close>indicator
    results=[]
    for i in range(len(frame)):
        day=frame.index[i].date()
        if config.start<=day<=config.end and bool(signal.iloc[i]) and pd.notna(indicator.iloc[i]):
            results.append({'symbol':symbol,'date':day.isoformat(),'close':round(float(close.iloc[i]),4),
                'indicator':round(float(indicator.iloc[i]),4),'rule':config.rule})
    required=200 if config.rule=='above_sma200' else 20
    warning='Some early bars lack indicator warmup history.' if len(frame[frame.index.date<config.start])<required else None
    return results,warning

jobs={}
job_tasks=set()

def run_scan(config):
    import yfinance as yf
    rows=[];errors=[];warnings=[];bars_scanned={}
    # Fetch enough earlier bars for each interval; never include them in result dates.
    warmup={'1d':400,'1wk':1600,'1mo':6300}[config.interval]
    for symbol in config.symbols:
        try:
            frame=yf.Ticker(symbol).history(start=(config.start-timedelta(days=warmup)).isoformat(),
                end=(config.end+timedelta(days=1)).isoformat(),interval=config.interval,auto_adjust=True,timeout=12)
            bars_scanned[symbol]=len(frame)
            matches,warning=evaluate(frame,config,symbol);rows.extend(matches)
            if warning:warnings.append(symbol+': '+warning)
        except Exception as e:errors.append({'symbol':symbol,'error':str(e)[:200]})
    rows.sort(key=lambda r:(r['date'],r['symbol']),reverse=True)
    return {'matches':rows[:2000],'total_matches':len(rows),'truncated':len(rows)>2000,'errors':errors,'warnings':warnings,'bars_scanned':bars_scanned,
        'source':'Yahoo Finance · adjusted OHLC','completed_at':datetime.now(timezone.utc).isoformat(),
        'note':'Historical technical signals, not simulated trades. Corporate-action adjustments may revise past prices.'}

@router.get('/scanners')
def saved():
    with STORE_LOCK:
        try:return json.loads(DATA.read_text())
        except (OSError,ValueError):return []
@router.post('/scanners',dependencies=[Depends(trusted_client)])
def save(config:ScanConfig):
    with STORE_LOCK:
        try:items=json.loads(DATA.read_text())
        except (OSError,ValueError):items=[]
        if len(items)>=100:raise HTTPException(409,'Saved scanner limit reached (100).')
        item={'id':secrets.token_hex(8),**config.model_dump(mode='json')};items.append(item)
        DATA.parent.mkdir(parents=True,exist_ok=True)
        temporary=DATA.with_suffix('.tmp');temporary.write_text(json.dumps(items));temporary.replace(DATA)
    return item
@router.post('/run',dependencies=[Depends(trusted_client)])
async def run(config:ScanConfig):
    if sum(j['state']=='running' for j in jobs.values())>=2:raise HTTPException(429,'Two scans are already running. Try again shortly.')
    if len(jobs)>=100:
        oldest=next((key for key,j in jobs.items() if j['state']!='running'),None)
        if oldest:jobs.pop(oldest)
    key=secrets.token_hex(10);job={'id':key,'state':'running','config':config.model_dump(mode='json'),'result':None,'error':None};jobs[key]=job
    async def work():
        try:job.update(state='completed',result=await asyncio.to_thread(run_scan,config))
        except Exception as e:job.update(state='failed',error=str(e)[:300])
    task=asyncio.create_task(work());job_tasks.add(task);task.add_done_callback(job_tasks.discard)
    return job
@router.get('/jobs/{key}')
async def result(key:str):
    if key not in jobs:raise HTTPException(404,'Scan not found. The server may have restarted; run the scanner again.')
    return jobs[key]
