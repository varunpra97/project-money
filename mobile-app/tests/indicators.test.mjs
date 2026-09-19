import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import vm from 'node:vm';
const result=await build({entryPoints:['src/lib/indicators.ts'],bundle:true,write:false,platform:'node',format:'cjs'});
const module={exports:{}};
vm.runInNewContext(result.outputFiles[0].text,{module,exports:module.exports});
const {indicators}=module.exports;
const bars=values=>values.map((c,t)=>({c,t}));
test('warmup does not invent short-period values',()=>{
  assert.equal(indicators(bars(Array(19).fill(100)))[18].sma,null);
});
test('constant input has zero band width and constant averages',()=>{
  const s=indicators(bars(Array(40).fill(100)))[39];
  for(const key of ['sma','ema','upper','lower'])assert.equal(s[key],100);
});
test('known 20-value window and seeded EMA',()=>{
  const s=indicators(bars(Array.from({length:21},(_,i)=>i+1)));
  assert.equal(s[19].sma,10.5);assert.equal(s[19].ema,10.5);
  assert.ok(Math.abs(s[19].upper-(10.5+2*Math.sqrt(33.25)))<1e-10);
  assert.equal(s[20].sma,11.5);assert.equal(s[20].ema,11.5);
});
