'use strict';
// Actual shipped scripts and event handlers, with memory-only DOM, downloads
// and fetch fixtures. No browser, socket, server, real API or provider is used.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
let current=JSON.parse(fs.readFileSync('data/synthetic-cycle/REVIEW_PACKAGE.json','utf8'));
const clone=v=>JSON.parse(JSON.stringify(v));
const checks=[],calls=[],downloads=[],blobs=new Map();
const check=(name,value)=>{assert.ok(value,name);checks.push(name);};
class Element{
 constructor(id,doc){this.id=id;this.doc=doc;this.handlers={};this.owned=[];this.attributes={};this.dataset={};this.files=[];this.disabled=false;this.textContent='';const flags=new Set();this.classList={add:x=>flags.add(x),remove:x=>flags.delete(x),contains:x=>flags.has(x),toggle:(x,on)=>{on=on??!flags.has(x);on?flags.add(x):flags.delete(x);}};}
 set innerHTML(value){this.html=value;this.doc.parse(value,this);}
 get innerHTML(){return this.html||'';}
 addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}
 setAttribute(name,value){this.attributes[name]=value;}
 focus(){}
 async fire(type){for(const fn of this.handlers[type]||[])await fn({target:this,preventDefault(){}});}
 click(){if(this.download)downloads.push({name:this.download,blob:blobs.get(this.href)});return this.fire('click');}
}
class Document{
 constructor(){this.ids=new Map();this.nodes=[];this.body=new Element('body',this);}
 add(id){const n=new Element(id,this);this.ids.set(id,n);this.nodes.push(n);return n;}
 getElementById(id){return this.ids.get(id)||null;}
 createElement(){return new Element('',this);}
 parse(html,owner){
  for(const old of owner.owned){old.removed=true;if(this.ids.get(old.id)===old)this.ids.delete(old.id);}
  owner.owned=[];
  for(const tag of html.matchAll(/<[a-z][\w-]*\b([^>]*)>/gi)){
   const attrs={};for(const pair of tag[1].matchAll(/([\w-]+)="([^"]*)"/g))attrs[pair[1]]=pair[2];
   if(!attrs.id&&!Object.keys(attrs).some(k=>k.startsWith('data-')))continue;
   const n=new Element(attrs.id||'',this);n.attributes=attrs;
   for(const [key,val] of Object.entries(attrs))if(key.startsWith('data-'))n.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=val;
   owner.owned.push(n);this.nodes.push(n);if(n.id)this.ids.set(n.id,n);
  }
 }
 querySelectorAll(selector){
  const attr=selector.match(/^\[data-([^\]]+)\]$/);
  if(attr)return this.nodes.filter(n=>!n.removed&&n.attributes['data-'+attr[1]]!==undefined);
  if(selector==='.demo-badge')return [this.getElementById('test-badge')];
  return [];
 }
}
const document=new Document();
for(const id of ['main','notice','primary-nav','breadcrumb-current','revision-label','assistant-panel','study-identity','navigation','menu-toggle','close-menu','test-badge'])document.add(id);
const window={handlers:{},scrollTo(){},addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}};
const location={value:'#muse-cycle',get hash(){return this.value;},set hash(value){this.value=value.startsWith('#')?value:'#'+value;}};
function snapshot(){const p=current.study_package;return {current:clone(p.revisions.at(-1)),evidence:clone(p.source_bundle),eligible_checks:[],history:p.revisions.map(r=>({revision:r.revision,saved_utc:r.saved_utc,action:r.action.type,hash:r.hash})),read_only:true,completed_cycle:clone(current.summary),live_enabled:false};}
const fetchMemory=async(path,options={})=>{
 assert.ok(['/api/session','/api/state','/api/cycle-review.json','/api/cycle-review/open'].includes(path),'Unexpected network/action path');
 calls.push({path,method:options.method||'GET'});
 let value;
 if(path==='/api/session')value={token:'synthetic-session-only'};
 else if(path==='/api/state')value=snapshot();
 else if(path==='/api/cycle-review.json')value=clone(current);
 else{
  const body=JSON.parse(options.body);assert.equal(body.expected_hash,current.study_package.revisions.at(-1).hash);
  try{const next=JSON.parse(body.review_json);if(next.schema_version!=='traitweaver.completed_cycle_review.v1')throw Error();current=next;value={current:snapshot().current,read_only:true};}
  catch{return {ok:false,json:async()=>({error:'Invalid completed-cycle review'})};}
 }
 return {ok:true,json:async()=>value};
};
const context=vm.createContext({document,window,location,fetch:fetchMemory,matchMedia:()=>({matches:false,addEventListener(){}}),Blob,
 URL:{createObjectURL(blob){const key='blob:synthetic-'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}},setTimeout:fn=>fn(),console});
const run=code=>vm.runInContext(code,context);
const main=()=>document.getElementById('main').innerHTML;
const navigate=hash=>{location.hash='#'+hash;for(const fn of window.handlers.hashchange||[])fn();};
async function fire(id,type='click'){const n=document.getElementById(id);assert.ok(n,'Missing '+id);await n.fire(type);}
(async()=>{
 run(fs.readFileSync('src/traitweaver/web/completed-cycle-ui.js','utf8'));
 await run(fs.readFileSync('src/traitweaver/web/workspace.js','utf8'));
 check('default audit uses its own decision heading',main().includes('Audit the endpoint before comparing paths.'));
 for(const metric of ['growth','phosphate_uptake']){
  const sample=snapshot();const c=sample.current.state.cycles[0];const records=sample.evidence.evidence.filter(e=>e.metric===metric&&e.source_id==='S_PSR1_2023');
  const control=records.find(e=>e.subject==='UVM4');
  c.decision.check='published_contrasts';c.decision.arguments={metric};
  c.result={tool:'published_contrasts',metric,rows:records.filter(e=>e.subject!=='UVM4').map(e=>({subject:e.subject,reported_mean:e.value,reported_uncertainty:e.uncertainty,difference_from_control:e.value-control.value,ratio_to_control:e.value/control.value})),uncertainty_limit:'Synthetic view case using published means only'};
  run('snapshot='+JSON.stringify(sample)+';reviewStep=0;render();');
  check(metric+' decision heading reflects the selected contrast',main().includes('Describe published '+metric.replaceAll('_',' ')+' contrasts.')&&!main().includes('<h2>Audit the endpoint'));
  run('reviewStep=1;render();');
  check(metric+' result heading names the selected metric',main().includes('Published '+metric.replaceAll('_',' ')+' contrasts against the source control.'));
 }
 run('snapshot='+JSON.stringify(snapshot())+';reviewStep=3;render();');
 await fire('download-cycle-review');
 const saved=await downloads.at(-1).blob.text();
 check('actual download handler includes the study and usage summary',JSON.parse(saved).summary.estimated_cost_usd===current.summary.estimated_cost_usd);
 navigate('handoff');
 check('handoff offers the separate cycle-with-usage picker',Boolean(document.getElementById('cycle-review-file')));
 document.getElementById('cycle-review-file').files=[{size:saved.length,text:async()=>saved}];
 await fire('cycle-review-file','change');
 check('actual file-picker handler reopens the review view',location.hash==='#muse-cycle'&&run('snapshot.read_only')===true);
 check('reopened walkthrough starts at its saved decision',main().includes('1 of 4 · Decision'));
 check('reopen preserves synthetic label and exact recorded cost',main().includes('Synthetic offline replay')&&main().includes('$0.000590'));
 check('reopen preserves four revisions without a new result',run('snapshot.current.revision')===4);
 navigate('handoff');const posts=calls.filter(c=>c.method==='POST').length;
 document.getElementById('cycle-review-file').files=[{size:4194305,text:async()=>{throw Error('Oversized file must not be read');}}];
 await fire('cycle-review-file','change');
 check('oversize file is refused before reading or posting',calls.filter(c=>c.method==='POST').length===posts);
 document.getElementById('cycle-review-file').files=[{size:4,text:async()=>'{bad'}];
 await fire('cycle-review-file','change');
 check('invalid-file error is visible and current view stays intact',document.getElementById('notice').textContent.includes('Invalid completed-cycle review')&&run('snapshot.current.revision')===4&&location.hash==='#handoff');
 check('only memory view-open mutations were used',calls.filter(c=>c.method==='POST').every(c=>c.path==='/api/cycle-review/open'));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,real_network_requests:0,files_written:0,qualification:'Memory DOM/controller fixtures; not browser rendering.'},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
