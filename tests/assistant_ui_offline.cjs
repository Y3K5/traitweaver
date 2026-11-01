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
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','intelligence-ui.js','assistant-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 location.hash='#assistant';run('render()');
 const stage=async key=>{const n=doc.nodes.find(n=>!n.removed&&n.dataset.assistantStage===key);assert.ok(n,'Missing stage '+key);await n.fire('click');};
 check('Research assistant is in navigation and has four controlled case choices',doc.getElementById('primary-nav').innerHTML.includes('Research assistant')&&run('snapshot.assistant.cases.length')===4);
 check('initial evidence is public and explicitly withholds a recovery winner',html().includes('Supported evidence')&&html().includes('ENV_WITHHELD')&&html().includes('No accepted response yet'));
 const start=requests.length;await stage('checks');
 check('stage navigation does not dispatch a tool',requests.length===start&&html().includes('Run one local readiness audit'));
 await fire('assistant-check');check('actual local audit receipt is shown with pre-result purpose',run('snapshot.assistant.checks.length')===1&&html().includes('Actual local audit')&&html().includes('Pre-result decision'));
 await stage('plan');check('three complete proposal cards show input deliverable completion and readiness',doc.querySelectorAll('[data-assistant-inputs]').length===3&&html().includes('Required input')&&html().includes('Complete when')&&html().includes('Needs human approval'));
 const trait=doc.nodes.find(n=>!n.removed&&n.dataset.assistantPlanStage==='combination');await trait.fire('click');
 check('trait-development map exposes unqualified cassette and cross-species questions',html().includes('Cassette composition')&&html().includes('no cross-species recipient is qualified')&&html().includes('href="#intelligence"'));
 await fire('assistant-synthetic');check('synthetic action review is clearly accepted without model transport',run('snapshot.assistant.review.receipt.provenance')==='synthetic_fixture'&&html().includes('Synthetic / imported review accepted'));
 const input=doc.querySelectorAll('[data-assistant-inputs]')[0];await input.fire('click');
 check('action citations open the evidence inspector without an external request',html().includes('Inspecting:')&&run('assistantStage')==='evidence');
 for(const cid of ['PROTEIN_GFP','RNA_SYNTHETIC','REPRO_SYNTHETIC']){
  await fire('assistant-case','change',cid);check('case selector updates evidence '+cid,run('snapshot.assistant.case.case_id')===cid);
  await stage('checks');await fire('assistant-check');await stage('plan');await fire('assistant-synthetic');
  check('actual local audit and accepted three-action review '+cid,run('snapshot.assistant.checks[0].result.status')==='completed'&&run('snapshot.assistant.review.actions.length')===3);
 }
 await fire('assistant-case','change','RNA_SYNTHETIC');
 check('incomplete RNA case keeps zero files null reads and metadata conflicts',html().includes('SYN-T2')&&html().includes('library layout conflicts')&&run('snapshot.assistant.case.records[2].value.fastq_files_supplied')===0&&run('snapshot.assistant.case.records[2].value.read_count')===null);
 await stage('export');await fire('assistant-export');let saved=JSON.parse(await downloads.at(-1).blob.text());
 check('actual JSON download contains accepted actions and actual local receipt',saved.schema_version==='traitweaver.assistant_workspace_package.v1'&&saved.assistant_package.accepted_review.actions.length===3&&saved.local_checks[0].result.duplicates[0]==='SYN-T2');
 await fire('assistant-readable');const readable=await downloads.at(-1).blob.text();
 check('readable download retains exact action IDs claims limitations and synthetic label',readable.includes('RNA_SYNTHETIC_A1')&&readable.includes('RNA_WITHHELD')&&readable.includes('synthetic_fixture')&&readable.includes('No differential-expression conclusion'));
 const file=doc.getElementById('assistant-file');file.files=[{size:JSON.stringify(saved).length,text:async()=>JSON.stringify(saved)}];await file.fire('change');
 check('actual file handler reopens browser package read-only with unchanged receipts',run('snapshot.assistant.read_only')===true&&run('snapshot.assistant.checks[0].result.duplicates[0]')==='SYN-T2'&&html().includes('Reopened · read-only'));
 await stage('plan');check('reopened action plan cannot accept another synthetic reply',doc.getElementById('assistant-synthetic').disabled);
 await stage('checks');check('reopened audit cannot rerun',doc.getElementById('assistant-check').disabled);
 const before=JSON.stringify(run('snapshot.assistant.current'));await stage('export');
 let read=false;doc.getElementById('assistant-file').files=[{size:262145,text:async()=>{read=true;return '{}';}}];await doc.getElementById('assistant-file').fire('change');
 check('oversized import is rejected before reading',read===false&&JSON.stringify(run('snapshot.assistant.current'))===before);
 doc.getElementById('assistant-file').files=[{size:5,text:async()=>'{bad'}];await doc.getElementById('assistant-file').fire('change');
 check('corrupt import keeps the accepted view intact and reports error',JSON.stringify(run('snapshot.assistant.current'))===before&&doc.getElementById('notice').classList.contains('error'));
 await fire('assistant-return');check('return from read-only import restores the prior local case',run('snapshot.assistant.read_only')===false&&run('snapshot.assistant.review.case_id')==='RNA_SYNTHETIC');
 await fire('assistant-case','change','PROTEIN_GFP');
 run("snapshot.assistant.review.claims.supports[0].text='<img src=x onerror=alert(1)>';render()");
 check('record content is escaped rather than executed',html().includes('&lt;img')&&!html().includes('<img src=x'));
 await run('refresh()');check('refresh preserves server-owned local case and review',run('snapshot.assistant.case.case_id')==='PROTEIN_GFP'&&run('snapshot.assistant.review.case_id')==='PROTEIN_GFP');
 run("snapshot.assistant.review.receipt.provenance='owner_imported_reply_authenticity_unverified';assistantStage='plan';render()");
 check('imported priorities are labelled unverified rather than synthetic or authenticated',html().includes('Imported priorities · provider authenticity unverified')&&!html().includes('Prioritization is a synthetic fixture in this demo.'));
 check('original completed cycle and reference records remain unchanged',JSON.stringify(run('snapshot.current'))===coreBefore&&JSON.stringify(run('snapshot.public_algae'))===referenceBefore);
 check('all assistant requests use bounded local routes',requests.every(r=>r.path.startsWith('/api/')));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,socket_calls:0,external_requests:0,qualification:'Memory DOM with actual scripts/handlers; rendered-browser and native picker checks separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);process.exitCode=1;});
