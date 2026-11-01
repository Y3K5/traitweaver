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
const location={hash:'#intelligence'};
const memoryFetch=async(path,options={})=>{
 requests.push({path,method:options.method||'GET'});const r=await rpc({path,...options});
 if(path==='/api/state'&&!coreBefore){coreBefore=JSON.stringify(r.payload.current);referenceBefore=JSON.stringify(r.payload.public_algae);}
 return {ok:r.ok,status:r.status,json:async()=>r.payload,text:async()=>r.text};
};
const context=vm.createContext({document:doc,window,location,fetch:memoryFetch,structuredClone,Blob,console,setTimeout:fn=>fn(),matchMedia:()=>({matches:false,addEventListener(){}}),URL:{createObjectURL(blob){const key='blob:memory-'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}}});
const run=s=>vm.runInContext(s,context),html=()=>doc.getElementById('main').innerHTML;
const check=(name,v)=>{assert.ok(v,name);checks.push(name);};
async function fire(id,type='click',value){const n=doc.getElementById(id);assert.ok(n,'Missing '+id);if(value!==undefined)n.value=value;await n.fire(type);}
async function focus(id){const n=doc.nodes.find(n=>!n.removed&&n.dataset.intelligenceFocus===id);assert.ok(n,'Missing focus '+id);await n.fire('click');}
const revision=()=>run('snapshot.intelligence.current.revision');
(async()=>{try{
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','intelligence-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 check('Muse intelligence navigation renders real public candidate and unknowns',doc.getElementById('primary-nav').innerHTML.includes('Muse intelligence')&&html().includes('XP_001700553.1')&&html().includes('PROVISIONAL'));
 check('independent scope stays editable beside a read-only completed Muse cycle',!doc.getElementById('intelligence-endpoint').disabled&&run('snapshot.read_only')===true);
 const originalForm=doc.getElementById('intelligence-scope-form');await fire('intelligence-endpoint','change','phosphate_uptake');await fire('intelligence-growth','change','0');
 check('field changes retain the form and keep zero distinct from unknown',originalForm===doc.getElementById('intelligence-scope-form')&&run('intelligenceDraft.minimum_growth_ratio')===0);
 await fire('intelligence-growth','change','');doc.getElementById('intelligence-growth').value='0';
 await fire('intelligence-scope-form','submit');check('native-style value change without a change event still saves zero',run('snapshot.intelligence.current.state.scope.minimum_growth_ratio')===0);check('save creates separate scope revision with current context',revision()===1&&run('snapshot.intelligence.current.state.scope.target_endpoint')==='phosphate_uptake');
 await fire('intelligence-prepare');check('payload prepares without creating a revision or sending to a provider',revision()===1&&run('intelligencePreview.status')==='not_sent'&&html().includes('Exact public payload'));
 check('prepared body excludes owning free-text notes and targets bounded Muse schema',!run('intelligencePreview.body.input').includes('context_notes')&&run('intelligencePreview.body.max_output_tokens')===1024);
 await fire('intelligence-request-download');check('prepared request download is public and explicitly unsent',JSON.parse(await downloads.at(-1).blob.text()).status==='not_sent');
 await fire('intelligence-synthetic');check('synthetic selection persists a pre-result decision only',revision()===2&&run('snapshot.intelligence.current.state.cycles[0].result')===null&&html().includes('Run the saved local check'));
 await run("intelligencePost('synthetic',{phase:'selection',focus:'trait'})");check('duplicate selection is rejected without advancing history',revision()===2&&doc.getElementById('notice').classList.contains('error'));
 await fire('intelligence-run');check('actual local audit records source-bound supported association with zero margin',revision()===3&&html().includes('Actual local result')&&run('snapshot.intelligence.current.state.cycles[0].result.outcome')==='supported');
 await fire('intelligence-prepare');check('reassessment payload binds the saved result identity',run('intelligencePreview.phase')==='reassessment'&&run('JSON.parse(intelligencePreview.body.input).result.id')===run('snapshot.intelligence.current.state.cycles[0].result.id'));
 await fire('intelligence-synthetic');check('separate reassessment closes the cycle without automatic continuation',revision()===4&&run('snapshot.intelligence.current.state.cycles.length')===1&&html().includes('Separate reassessment'));
 await focus('combinations');check('combination pane shows unresolved role slots and unknown pair effects',html().includes('Protein identity unavailable')&&html().includes('Zero records is different'));
 await fire('intelligence-synthetic');await fire('intelligence-run');await fire('intelligence-synthetic');
 check('combination audit and reassessment retain unavailable effects',run('snapshot.intelligence.current.state.cycles[1].result.facts.synergy')===null&&run('snapshot.intelligence.current.state.cycles[1].assessment.outcome')==='unavailable');
 await focus('transfer');await fire('intelligence-recipient','change','study_uvm4');await fire('intelligence-scope-form','submit');
 check('recipient change preserves earlier cycles and marks reassessment',run("snapshot.intelligence.current.state.cycles[0].applicability")==='needs_reassessment'&&html().includes('same species different context'));
 await fire('intelligence-synthetic');await fire('intelligence-run');await fire('intelligence-synthetic');
 check('transfer review refuses a success probability or cross-species claim',run('snapshot.intelligence.current.state.cycles.at(-1).result.facts.transfer_success_probability')===null&&html().includes('No cross-species recipient'));
 await fire('intelligence-prepare');const before=revision();run("document.getElementById('intelligence-reply').value=JSON.stringify({model:'muse-spark-1.3',status:'completed',output:[{type:'function_call',name:'shell'}]})");await fire('intelligence-accept');
 check('rejected provider action cannot execute or save',revision()===before&&doc.getElementById('notice').classList.contains('error'));
 await fire('intelligence-export');const exported=await downloads.at(-1).blob.text(),packageData=JSON.parse(exported);
 check('download contains versioned source-bound accepted history and no raw provider reply',packageData.schema_version==='traitweaver.intelligence_package.v1'&&packageData.catalog.reference.strain.includes('CC-503')&&!exported.includes('function_call'));
 await fire('intelligence-readable');check('readable download retains qualification and separate result/reassessment',downloads.at(-1).name==='traitweaver-intelligence-review.txt'&&(await downloads.at(-1).blob.text()).includes('PROVISIONAL')&&(await downloads.at(-1).blob.text()).includes('SEPARATE REASSESSMENT'));
 const posts=requests.filter(x=>x.method==='POST').length;doc.getElementById('intelligence-file').files=[{size:4194305,text:async()=>{throw Error('Do not read');}}];await fire('intelligence-file','change');
 check('oversize import is rejected before file read or handler dispatch',requests.filter(x=>x.method==='POST').length===posts);
 doc.getElementById('intelligence-file').files=[{size:4,text:async()=>'{bad'}];await fire('intelligence-file','change');check('malformed import preserves current history',revision()===before);
 doc.getElementById('intelligence-file').files=[{size:exported.length,text:async()=>exported}];await fire('intelligence-file','change');
 check('file reopening restores actual package as read-only without execution',run('snapshot.intelligence.read_only')===true&&doc.getElementById('intelligence-synthetic').disabled&&revision()===before);
 location.hash='#handoff';for(const f of window.handlers.hashchange||[])f();check('handoff exposes a separate intelligence package without changing original exports',html().includes('Separate Muse intelligence package')&&html().includes('versioned intelligence package'));
 const state=await memoryFetch('/api/state',{headers:{'X-Traitweaver-Client':'workspace'}});const final=await state.json();
 check('original completed study and public-reference journal remain bit-for-bit unchanged',JSON.stringify(final.current)===coreBefore&&JSON.stringify(final.public_algae)===referenceBefore);
 check('only bounded local intelligence mutations were dispatched',requests.filter(x=>x.method==='POST').every(x=>x.path.startsWith('/api/intelligence/')));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,socket_calls:0,external_requests:0,files_written:0,qualification:'Memory DOM and actual memory handlers; rendered-browser checks remain separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);bridge.kill();process.exitCode=1;});
