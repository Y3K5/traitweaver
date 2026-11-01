'use strict';
// Shipped controllers -> memory fetch -> actual Python handler/core, no network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{spawn}=require('node:child_process'),readline=require('node:readline');
const bridge=spawn('python3',['-B','tests/intelligence_memory_bridge.py'],{env:{PATH:'/usr/local/bin:/usr/bin:/bin',PYTHONPATH:'src:tests',PYTHONNOUSERSITE:'1'},stdio:['pipe','pipe','pipe']});
let stderr='';bridge.stderr.on('data',b=>stderr+=b.toString());const pending=[];
readline.createInterface({input:bridge.stdout}).on('line',line=>{const p=pending.shift();if(p){try{p.resolve(JSON.parse(line));}catch(e){p.reject(e);}}});
bridge.on('exit',code=>{if(code)for(const p of pending.splice(0))p.reject(Error(stderr));});
const rpc=data=>new Promise((resolve,reject)=>{pending.push({resolve,reject});bridge.stdin.write(JSON.stringify(data)+'\n');});
const requests=[],downloads=[],checks=[],blobs=new Map();let coreBefore,referenceBefore,timerFn=null;
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
const context=vm.createContext({document:doc,window,location,fetch:memoryFetch,structuredClone,Blob,console,setTimeout:fn=>fn(),setInterval:fn=>{timerFn=fn;return 1;},clearInterval:()=>{timerFn=null;},matchMedia:()=>({matches:false,addEventListener(){}}),URL:{createObjectURL(blob){const key='blob:memory-'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}}});
const run=s=>vm.runInContext(s,context),html=()=>doc.getElementById('main').innerHTML;
const check=(name,v)=>{assert.ok(v,name);checks.push(name);};
async function fire(id,type='click',value){const n=doc.getElementById(id);assert.ok(n,'Missing '+id);if(value!==undefined)n.value=value;await n.fire(type);}
async function focus(id){const n=doc.nodes.find(n=>!n.removed&&n.dataset.intelligenceFocus===id);assert.ok(n,'Missing focus '+id);await n.fire('click');}
const revision=()=>run('snapshot.intelligence.current.revision');
(async()=>{try{
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','intelligence-ui.js','data-flow-ui.js','assistant-ui.js','research-story-ui.js','workbench-ui.js','journey-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 location.hash='#journey';run('render()');
 check('journey appears in the existing navigation',doc.getElementById('primary-nav').innerHTML.includes('Research journey'));
 check('playback visibly distinguishes illustration from model or tool execution',html().includes('Illustration')&&html().includes('no new inference')&&html().includes('no live calls'));
 check('qualified public protein mapping remains source linked',html().includes('XP_001700553.1')&&html().includes('752 aa')&&html().includes('CC-503'));
 check('entry offers the working study and a deliberate presentation control',html().includes('Open the working study')&&doc.getElementById('journey-focus'));
 const scrollRequests=requests.length;const jump=doc.nodes.find(n=>!n.removed&&n.dataset.journeyScroll==='journey-records');await jump.fire('click');check('evidence jump is local navigation and preserves scientific records',requests.length===scrollRequests&&doc.getElementById('journey-records'));

 check('published endpoints show their separate source units SE n and basis',html().includes('0.48')&&html().includes('0.97')&&html().includes('mmol P g dry_weight^-1 d^-1')&&html().includes('d^-1')&&html().includes('culture replicate')&&html().includes('S_PSR1_2023'));
 check('loaded synthetic usage cannot be presented as a real contribution',html().includes('data-journey-ai="synthetic"')&&html().includes('simulated requests')&&html().includes('synthetic usage'));
 const focusRequests=requests.length;
 check('presentation mode opens full width and keeps closed navigation inert',doc.body.classList.contains('journey-focus')&&doc.getElementById('navigation').inert===true);
 await fire('menu-toggle');check('presentation navigation remains keyboard accessible',doc.getElementById('navigation').inert===false&&doc.getElementById('menu-toggle').attributes['aria-expanded']==='true');
 for(const fn of window.handlers.keydown||[])fn({key:'Escape'});
 check('Escape closes the presentation menu without executing anything',doc.getElementById('navigation').inert===true&&requests.length===focusRequests);
 await fire('journey-focus');check('exiting presentation restores ordinary desktop navigation',!doc.body.classList.contains('journey-focus')&&doc.getElementById('navigation').inert===false);
 const nav=doc.getElementById('primary-nav').innerHTML;
 check('primary navigation is focused and every existing tool remains available',nav.includes('Evidence, mapping &amp; tools')||nav.includes('Evidence, mapping & tools'));
 check('gene splice intelligence and data-flow routes are preserved', ['#gene-map','#splice-map','#intelligence','#data-flow'].every(h=>nav.includes('href="'+h+'"')));
 run('var storyBackup=structuredClone(snapshot.research_story);snapshot.research_story.content.summaries.phosphate_uptake.rows.find(r=>r.record.subject==="UVM4").record.value=0;snapshot.research_story.content.summaries.phosphate_uptake.rows.find(r=>r.record.subject==="8-27").record.value=null;render();');
 check('zero and missing remain visibly distinct in the new evidence cards',html().includes('<strong>0</strong>')&&html().includes('<strong>Unknown</strong>'));
 run('snapshot.research_story=storyBackup;var oldStory=snapshot.research_story;snapshot.research_story=null;render();');
 check('missing source qualification withholds numeric cards and identity claims',html().includes('Source snapshot unavailable')&&!html().includes('<strong>0.97</strong>')&&!html().includes('XP_001700553.1'));
 run('snapshot.research_story=oldStory;render();');
 const noLoadRequests=requests.length;run('var cycleBackup=snapshot.completed_cycle;var readOnlyBackup=snapshot.read_only;snapshot.read_only=false;snapshot.completed_cycle=null;render();');
 check('unloaded AI records show no invented usage or real contribution',html().includes('data-journey-ai="not-loaded"')&&!html().includes('saved requests')&&requests.length===noLoadRequests);
 run('snapshot.completed_cycle=cycleBackup;snapshot.read_only=readOnlyBackup;render();');

 check('exactly five scenes with Meta decision and actual result cards',run('journeyStages.length')===5&&html().includes('Muse chose this check')&&html().includes('The software found this')&&html().includes('Muse reassessed'));
 check('pilot absence cannot fabricate a successful result',html().includes('No result loaded'));
 const beforeRequests=requests.length;await fire('journey-play');assert.ok(timerFn);timerFn();
 check('play advances locally without any HTTP/tool/model request',run('journeyIndex')===1&&requests.length===beforeRequests);
 await fire('journey-play');check('pause stops the timer',timerFn===null);
 await fire('journey-next');check('reference companions retain transcript length exons and locus qualification',html().includes('4772')&&html().includes('3 annotated exons')&&html().includes('Region hash only'));check('manual stage navigation changes the explanation',run('journeyIndex')===2&&html().includes('GeneID:5726104'));
 const design=doc.nodes.find(n=>!n.removed&&n.dataset.journeyStage==='4');await design.fire('click');
 check('CRISPR sequence and method stages stay pending rather than fabricate results',html().includes('not an executable CRISPR')&&html().includes('human review required'));
 check('design companions preserve question controls independent units completion and citation IDs',html().includes('PLAN_PHOSPHORUS')&&html().includes('Independent units:')&&html().includes('Controls:')&&html().includes('Done when:'));
 await fire('journey-focus');location.hash='#question';run('render();navigation(false)');check('leaving the journey removes focus layout without trapping navigation',!doc.body.classList.contains('journey-focus')&&doc.getElementById('navigation').inert===false);location.hash='#journey';run('render()');await fire('journey-focus');
 await fire('journey-svg');const svg=await downloads.at(-1).blob.text();
 check('standalone SVG preserves loaded provenance and illustration labels',downloads.at(-1).name==='traitweaver-research-pathway.svg'&&svg.includes('Synthetic offline replay')&&svg.includes('Illustration only'));
 check('SVG has no external asset script or session identifier',!svg.includes('<script')&&!svg.includes('href=')&&!svg.includes('steps_hash'));
 const step=()=>run('snapshot.steps.projection.steps[0]');check('tracking starts unresolved in a separate synthetic RNA example',step().status==='not_started'&&html().includes('separate synthetic RNA example'));
 await fire('journey-check');check('actual local handler validates metadata and saves source-bound completion',step().status==='completed'&&step().completion_receipt.status==='passed'&&step().completion_receipt.record_ids[0]==='RNA_SAMPLES');
 check('completed check cannot be repeated by the displayed button',doc.getElementById('journey-check').disabled&&html().includes('Completion receipt saved'));
 check('other research tasks stay unresolved',run('snapshot.steps.projection.steps.slice(1).every(s=>s.status==="unresolved")'));
 await fire('journey-steps-export');const saved=JSON.parse(await downloads.at(-1).blob.text());
 check('JSON export retains immutable source-bound decision and result history',saved.schema_version==='traitweaver.completed_steps_package.v1'&&saved.revisions.length===3&&saved.revisions[1].action.type==='decide'&&saved.revisions[2].action.type==='result');
 const input=doc.getElementById('journey-file');input.files=[{size:JSON.stringify(saved).length,text:async()=>JSON.stringify(saved)}];await input.fire('change');
 check('actual file handler reopens completed records read-only',run('snapshot.steps.read_only')===true&&step().status==='completed'&&doc.getElementById('journey-source').disabled);
 await fire('journey-local');check('returning local preserves earlier completed work',run('snapshot.steps.read_only')===false&&step().status==='completed');
 await fire('journey-source','change','RNA_BEFORE');check('changed source needs reassessment and cannot borrow prior receipt',step().status==='needs_reassessment'&&step().completion_receipt===null);
 await fire('journey-check');check('conflicting synthetic metadata produces a blocker not completion',step().status==='blocked'&&step().completion_receipt.duplicates[0]==='SYN-B');
 let read=false;doc.getElementById('journey-file').files=[{size:524289,text:async()=>{read=true;return '{}';}}];await doc.getElementById('journey-file').fire('change');check('oversized package is rejected before reading',!read);
 const before=JSON.stringify(run('snapshot.steps.current'));doc.getElementById('journey-file').files=[{size:4,text:async()=>'{bad'}];await doc.getElementById('journey-file').fire('change');
 check('corrupt reopen preserves current tracking history',JSON.stringify(run('snapshot.steps.current'))===before&&doc.getElementById('notice').classList.contains('error'));
 await run('refresh()');check('refresh retains the active source-bound state',step().status==='blocked');
 run('var oldMatchMedia=matchMedia;matchMedia=()=>({matches:true});');const count=requests.length;await fire('journey-play');
 check('reduced motion avoids automatic playback and requests',timerFn===null&&requests.length===count);run('matchMedia=oldMatchMedia');
 check('main study and public mapping records remain unchanged',JSON.stringify(run('snapshot.current'))===coreBefore&&JSON.stringify(run('snapshot.public_algae'))===referenceBefore);
 check('requests stay within fixed local endpoints',requests.every(r=>r.path.startsWith('/api/')));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,external_requests:0,socket_calls:0,qualification:'Memory DOM with actual scripts and handlers; animation timers are controlled and native layout/dialogs are separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);process.exitCode=1;});
