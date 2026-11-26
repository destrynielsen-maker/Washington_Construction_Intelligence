import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
const base=process.argv[2]+'/', live=process.argv[3]+'/';
const read=(p)=>fs.readFileSync(p,'utf8');
const permits=JSON.parse(read(live+'data/permits.json')).permits;
class FixedDate extends Date { constructor(...args){super(...(args.length?args:['2026-11-26T18:49:49Z']))} static now(){return 1795718989000;} }
async function page(path) {
 const html=read(path);
 const elements={};
 for(const m of html.matchAll(/id="([^"]+)"/g)) elements[m[1]]={value:'',addEventListener(event,fn){this[event]=fn},insertAdjacentHTML(){}};
 elements.days.value=html.match(/id="days".*?value="(\d+)" selected/s)[1];
 elements.minScore.value=html.match(/id="minScore".*?value="(\d+)" selected/s)[1];
 const buttons=Object.fromEntries([...html.matchAll(/data-sort="([^"]+)"/g)].map(m=>[m[1],{dataset:{sort:m[1]},addEventListener(e,f){this[e]=f},querySelector(){return this.span??=( {})}}]));
 let blob, downloaded;
 const c=vm.createContext({...elements,Date:FixedDate,Blob,
  URL:{createObjectURL(b){blob=b;return 'blob:offline'},revokeObjectURL(){}},setTimeout,
  fetch:async u=>({json:async()=>JSON.parse(read(live+u.split('?')[0]))}),
  document:{getElementById:id=>elements[id],querySelectorAll:()=>Object.values(buttons),body:{appendChild(){}},createElement:()=>({click(){downloaded=this.download},remove(){}})}
 });
 await vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],c);
 return {html,c,e:elements,buttons,async export(){elements.exportCsv.click();assert.equal(downloaded,'washington-matching-permits.csv');return blob.text();}};
}
function parse(text) {
 const result=[];
 let row=[],cell='',quoted=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(ch==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++}else quoted=!quoted}
  else if(!quoted&&(ch===','||ch==='\r')){row.push(cell);cell='';if(ch==='\r'){assert.equal(text[++i],'\n');result.push(row);row=[]}}
  else cell+=ch;
 }
 assert.equal(quoted,false);assert.equal(row.length,0);return result;
}
const old=await page(base+'index.html'), next=await page(live+'index.html');
assert.match(next.html,/Seattle only/);
assert.match(next.html,/Reported contractor/);
assert.equal(old.e.rows.innerHTML,next.e.rows.innerHTML);
assert.equal(next.e.count.textContent,'38 matching · showing 1–38');
assert.equal(parse(await next.export()).length,39);
for(const p of [old,next]){p.e.days.value='0';p.e.minScore.value='0';p.e.days.change();}
assert.ok(old.e.rows.innerHTML.startsWith(next.e.rows.innerHTML));
assert.equal(next.e.rows.innerHTML.match(/<tr>/g).length,100);
assert.equal(next.e.count.textContent,'2,342 matching · showing 1–100');
assert.equal(next.e.previousPage.disabled,true);
const allPageIds=[];
for(let i=1;i<=24;i++){
 const ids=[...next.e.rows.innerHTML.matchAll(/rel="noopener">([^<]+)<\/a>/g)].map(x=>x[1]);
 allPageIds.push(...ids);
 if(i<24)next.e.nextPage.click();
}
assert.equal(allPageIds.length,2342);
assert.equal(new Set(allPageIds).size,2342);
assert.equal(next.e.count.textContent,'2,342 matching · showing 2,301–2,342');
assert.equal(next.e.nextPage.disabled,true); next.e.previousPage.click();
assert.equal(next.e.pageLabel.textContent,'Page 23 of 24');

const [header,...rows]=parse(await next.export());
const sorted=permits.slice().sort((a,b)=>b.score-a.score);
assert.equal(rows.length,2342);
assert.deepEqual(rows.map(r=>r[header.indexOf('Permit number')]),sorted.map(p=>p.permit_number));
assert.deepEqual(allPageIds,sorted.map(p=>p.permit_number));
assert.deepEqual(rows.map(r=>r[header.indexOf('Source-reported contractor')]),sorted.map(p=>p.contractor||''));
next.buttons.issued.click();
assert.equal(next.e.pageLabel.textContent,'Page 1 of 24');
assert.equal(next.buttons.issued.span.textContent,'▼');
const sortedDates=permits.slice().sort((a,b)=>b.issued_date.localeCompare(a.issued_date));
assert.deepEqual(parse(await next.export()).slice(1).map(r=>r[header.indexOf('Permit number')]),sortedDates.map(p=>p.permit_number));
next.e.search.value=sorted[0].permit_number;next.e.search.input();
assert.equal(parse(await next.export()).length,2);
next.e.search.value='zzzz-not-a-permit';next.e.search.input();
assert.equal(next.e.count.textContent,'0 matching · 0 shown');assert.equal(next.e.exportCsv.disabled,true);
next.e.reset.click();assert.equal(next.e.count.textContent,'38 matching · showing 1–38');
const cells=['=2+2','  +1','-1','@SUM(A1)','\tfoo','\u200b=1+1','José "A,B"\r\nCo.','',-5,null];
next.c.cells=cells;
assert.deepEqual(parse(vm.runInContext('cells.map(csvCell).join(",")+"\\r\\n"',next.c))[0],[...cells.slice(0,6).map(v=>"'"+v),...cells.slice(6,8),'-5','']);
const hrefs=p=>[...p.html.matchAll(/href="(feeds\/[^"]+)"/g)].map(x=>x[1]);
assert.deepEqual(hrefs(old),hrefs(next));
assert.equal(hrefs(next).length,5);
for(const href of hrefs(next)){
 const legacy=read(base+href), actual=read(live+href);
 assert.equal(actual,legacy);
 const ids=[...actual.matchAll(/<guid[^>]*>([^<]+)<\/guid>/g)].map(x=>x[1]);
 assert.equal(new Set(ids).size,ids.length);
 console.log(href,ids.length,createHash('sha256').update(actual).digest('hex'));
}
console.log('PASS baseline markup parity, 38 default, 2342 all across 24 pages without duplication, download rows and escaping, zero/reset, five RSS');
