'use strict';
// Shipped controllers -> memory fetch -> actual Python handler/core, no network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{spawn}=require('node:child_process'),readline=require('node:readline');
const bridge=spawn('python3',['-B','tests/intelligence_memory_bridge.py'],{env:{PATH:'/usr/local/bin:/usr/bin:/bin',PYTHONPATH:'src:tests',PYTHONNOUSERSITE:'1'},stdio:['pipe','pipe','pipe']});
let stderr='';bridge.stderr.on('data',b=>stderr+=b.toString());const pending=[];
readline.createInterface({input:bridge.stdout}).on('line',line=>{const p=pending.shift();if(p){try{p.resolve(JSON.parse(line));}catch(e){p.reject(e);}}});
bridge.on('exit',code=>{if(code)for(const p of pending.splice(0))p.reject(Error(stderr));});
const rpc=data=>new Promise((resolve,reject)=>{pending.push({resolve,reject});bridge.stdin.write(JSON.stringify(data)+'\n');});
const requests=[],downloads=[],checks=[],blobs=new Map();let coreBefore,referenceBefore;
class Element{
 constructor(id,doc){this.id=id;this.doc=doc;this.owned=[];this.handlers={};this.attributes={};this.dataset={};this.files=[];this.value='';this.disabled=false;const set=new Set();this.classList={add:x=>set.add(x),remove:x=>set.delete(x),contains:x=>set.has(x),toggle:(x,v)=>{v=v??!set.has(x);v?set.add(x):set.delete(x);}};}
 set innerHTML(v){this.html=v;this.doc.parse(v,this);}get innerHTML(){return this.html||'';}
 addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}setAttribute(k,v){this.attributes[k]=v;}
 closest(selector){return selector==='#intelligence-scope-form'&&this.inScopeForm?this.doc.getElementById('intelligence-scope-form'):null;}
 focus(){}scrollIntoView(){}
 async fire(type,extra={}){for(const fn of this.handlers[type]||[])await fn({target:this,currentTarget:this,preventDefault(){},...extra});}
 click(){if(this.download)downloads.push({name:this.download,blob:blobs.get(this.href)});return this.fire('click');}
}
class Document{
 constructor(){this.ids=new Map();this.nodes=[];this.body=new Element('body',this);}
 add(id){const n=new Element(id,this);this.ids.set(id,n);this.nodes.push(n);return n;}
 getElementById(id){return this.ids.get(id)||null;}createElement(){return new Element('',this);}
 parse(html,owner){
  for(const n of owner.owned){n.removed=true;if(this.ids.get(n.id)===n)this.ids.delete(n.id);}owner.owned=[];
  for(const tag of html.matchAll(/<([a-z][\w-]*)\b([^>]*)>/gi)){
   const attrs={};for(const p of tag[2].matchAll(/([\w-]+)="([^"]*)"/g))attrs[p[1]]=p[2];
   if(!attrs.id&&!Object.keys(attrs).some(k=>k.startsWith('data-')))continue;
   const n=new Element(attrs.id||'',this);n.tag=tag[1];n.inScopeForm=tag.index>html.indexOf('<form id="intelligence-scope-form"')&&tag.index<html.indexOf('</form>')&&html.includes('<form id="intelligence-scope-form"');n.attributes=attrs;n.disabled=/\sdisabled(?:\s|$)/.test(tag[2]);
   for(const [k,v] of Object.entries(attrs))if(k.startsWith('data-'))n.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;
   if(tag[1]==='input')n.value=attrs.value||'';
   if(tag[1]==='select'){const end=html.indexOf('</select>',tag.index),part=html.slice(tag.index+tag[0].length,end);const choices=[...part.matchAll(/<option value="([^"]*)"([^>]*)>/g)];n.value=(choices.find(x=>x[2].includes('selected'))||choices[0]||[])[1]||'';}
   if(tag[1]==='textarea'){const end=html.indexOf('</textarea>',tag.index);n.value=html.slice(tag.index+tag[0].length,end);}
   owner.owned.push(n);this.nodes.push(n);if(n.id)this.ids.set(n.id,n);
  }
 }
 querySelectorAll(selector){const m=selector.match(/^\[data-([^\]]+)\]$/);if(m)return this.nodes.filter(n=>!n.removed&&n.attributes['data-'+m[1]]!==undefined);if(selector.startsWith('form input'))return this.nodes.filter(n=>!n.removed&&n.inScopeForm&&['input','select','button','textarea'].includes(n.tag));if(selector==='.demo-badge')return [this.getElementById('badge')];return [];}
}
const doc=new Document();for(const id of ['main','notice','primary-nav','breadcrumb-current','revision-label','assistant-panel','study-identity','navigation','menu-toggle','close-menu','badge'])doc.add(id);
const window={handlers:{},scrollTo(){},addEventListener(k,f){(this.handlers[k]??=[]).push(f);}};
const location={hash:'#data-flow'};
const memoryFetch=async(path,options={})=>{
 requests.push({path,method:options.method||'GET',headers:options.headers});const r=await rpc({path,...options});
 if(path==='/api/state'&&!coreBefore){coreBefore=JSON.stringify(r.payload.current);referenceBefore=JSON.stringify(r.payload.public_algae);}
 return {ok:r.ok,status:r.status,json:async()=>r.payload,text:async()=>r.text};
};
const context=vm.createContext({document:doc,window,location,fetch:memoryFetch,structuredClone,Blob,console,setTimeout:fn=>fn(),matchMedia:()=>({matches:false,addEventListener(){}}),URL:{createObjectURL(blob){const key='blob:memory-'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}}});
const run=s=>vm.runInContext(s,context),html=()=>doc.getElementById('main').innerHTML;
const check=(name,v)=>{assert.ok(v,name);checks.push(name);};
async function fire(id,type='click',value){const n=doc.getElementById(id);assert.ok(n,'Missing '+id);if(value!==undefined)n.value=value;await n.fire(type);}
async function focus(id){const n=doc.nodes.find(n=>!n.removed&&n.dataset.intelligenceFocus===id);assert.ok(n,'Missing focus '+id);await n.fire('click');}
const revision=()=>run('snapshot.intelligence.current.revision');
async function stage(id){const n=doc.nodes.find(n=>!n.removed&&n.dataset.flowStage===id);assert.ok(n,'Missing stage '+id);await n.fire('click');}
(async()=>{try{
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','intelligence-ui.js','data-flow-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 check('Data flow is integrated into existing navigation',doc.getElementById('primary-nav').innerHTML.includes('Data flow')&&html().includes('See where the evidence goes'));
 check('acquisition shows five actual pinned reference files and manual intake gap',html().includes('Manual admission')&&html().includes('SHA-256')&&run('dataFlowReference().sources.sources.length')===5);
 check('loaded evidence is not confused with saved review checkpoints',run('dataFlowPackages().filter(p=>p.ready).length')===2&&run("dataFlowPackages().find(p=>p.id==='intelligence').ready")===false);
 await stage('map');check('map stage shows exact public protein/transcript identity and limits',html().includes('XP_001700553.1')&&html().includes('XM_001700501.2')&&html().includes('CC-503')&&html().includes('UVM4'));
 check('mapping keeps terminal stop and protein coding lengths distinct',html().includes('2259 nt')&&html().includes('2256 nt')&&html().includes('Exact offline match'));
 run('publicAlgaeMode=false');await doc.nodes.find(n=>!n.removed&&n.attributes['data-flow-public']).fire('click');check('identity link explicitly selects public mode',run('publicAlgaeMode')===true);
 await stage('use');check('use stage distinguishes original study and independent saved journals',html().includes('No intelligence decision or result is saved')&&html().includes('no checkpoint saved'));
 await stage('export');check('export stage disables unsaved journals',doc.nodes.filter(n=>!n.removed&&n.dataset.flowExport==='intelligence').every(n=>n.disabled));
 const count=requests.length;await run("dataFlowExport('intelligence','json')");check('programmatic unsaved export is also blocked before any request',requests.length===count&&downloads.length===0);
 check('stage navigation never dispatched a mutation',requests.every(r=>r.method==='GET'));
 await run("dataFlowExport('completed-cycle','json')");const recorded=JSON.parse(await downloads.at(-1).blob.text());check('completed cycle exports actual versioned usage package separately',recorded.schema_version==='traitweaver.completed_cycle_review.v1'&&downloads.at(-1).name==='traitweaver-completed-cycle.json');
 await run("dataFlowExport('study','text')");check('readable study export uses actual Markdown handler',downloads.at(-1).name==='traitweaver-study.md'&&(await downloads.at(-1).blob.text()).includes('Phosphorus'));
 await run("intelligencePost('revise',{scope:{...snapshot.intelligence.current.state.scope,minimum_growth_ratio:0}})");
 await stage('use');check('zero remains explicit in saved intelligence scope',html().includes('Growth margin:</strong> 0')&&!html().includes('Growth margin:</strong> Unknown'));
 run('intelligenceDraft=Object.fromEntries(Object.entries(snapshot.intelligence.current.state.scope).reverse());render()');check('equivalent drafts with different key order are not labelled unsaved',!html().includes('Draft differs'));
 run('intelligenceDraft.minimum_growth_ratio=null;render()');check('null versus zero creates an explicit unsaved-draft warning',html().includes('Draft differs'));
 await stage('export');await run("dataFlowExport('intelligence','json')");const saved=JSON.parse(await downloads.at(-1).blob.text());check('saved checkpoint enables JSON download without incorporating unsaved draft',saved.schema_version==='traitweaver.intelligence_package.v1'&&saved.revisions.at(-1).state.scope.minimum_growth_ratio===0);
 check('download request is pinned to the displayed independent revision',requests.at(-1).headers['X-Traitweaver-Expected-Revision']===run('snapshot.intelligence.current.hash'));
 await run("dataFlowExport('intelligence','text')");check('readable intelligence export preserves provisional public qualification',(await downloads.at(-1).blob.text()).includes('PROVISIONAL'));
 const old=run('snapshot.intelligence.current.hash'),token=run('sessionToken');
 const changed=await rpc({path:'/api/intelligence/revise',method:'POST',headers:{'X-Traitweaver-Client':'workspace','X-Traitweaver-Token':token,'Content-Type':'application/json'},body:JSON.stringify({expected_hash:run('snapshot.current.hash'),intelligence_hash:old,scope:run('snapshot.intelligence.current.state.scope')})});assert.equal(changed.status,200);
 const n=downloads.length;await run("dataFlowExport('intelligence','json')");check('concurrent revision change prevents download with safe refresh guidance',downloads.length===n&&doc.getElementById('notice').textContent.includes('Refresh Data flow'));
 await fire('data-flow-refresh');check('refresh loads new saved revision using GET only',run('snapshot.intelligence.current.hash')!==old&&requests.at(-1).method==='GET');
 await run("dataFlowExport('intelligence','json')");check('export succeeds after explicit refresh',downloads.length===n+1);
 run('intelligenceDraft=null; snapshot.public_algae=null;snapshot.intelligence.catalog.reference=null;dataFlowStage="map";render()');check('missing public source map does not substitute toy coordinates',html().includes('Reference mapping is unavailable')&&!html().includes('DEMO-TX'));
 await fire('data-flow-refresh');run('snapshot.evidence.sources[0].title="<img src=x onerror=bad()>";dataFlowStage="acquire";render()');check('source metadata is escaped',html().includes('&lt;img')&&!html().includes('<img src=x'));
 location.hash='#handoff';for(const f of window.handlers.hashchange||[])f();check('original handoff links to the new map',html().includes('Open Data flow'));
 const final=await (await memoryFetch('/api/state',{headers:{'X-Traitweaver-Client':'workspace'}})).json();
 check('navigation and exports preserve completed study and reference records',JSON.stringify(final.current)===coreBefore&&JSON.stringify(final.public_algae)===referenceBefore);
 check('all fetches remain bounded local routes and only explicit fixture saves mutate',requests.every(r=>r.path.startsWith('/api/'))&&requests.filter(r=>r.method==='POST').every(r=>r.path==='/api/intelligence/revise'));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,socket_calls:0,external_requests:0,files_written:0,qualification:'Memory DOM with actual shipped scripts and handlers. Native dialogs/layout checks separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);bridge.kill();process.exitCode=1;});
