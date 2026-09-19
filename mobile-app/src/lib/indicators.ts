import type { CBar } from "../components/Chart";
export function indicators(bars:CBar[]) {
  let ema=0;
  return bars.map((b,i)=>{
    const values=bars.slice(Math.max(0,i-19),i+1).map(x=>x.c);
    const sma=values.reduce((a,b)=>a+b,0)/values.length;
    ema=i===0?b.c:i===19?sma: i<19?sma:b.c*2/21+ema*19/21;
    const sd=Math.sqrt(values.reduce((a,v)=>a+(v-sma)**2,0)/values.length);
    return {sma:i>=19?sma:null,ema:i>=19?ema:null,upper:i>=19?sma+2*sd:null,lower:i>=19?sma-2*sd:null};
  });
}
