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
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','intelligence-ui.js','assistant-ui.js','research-story-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 location.hash='#research-story';run('render()');
 const stage=async id=>{const n=doc.nodes.find(n=>!n.removed&&n.dataset.storyStage===id);assert.ok(n);await n.fire('click');};
 const view=()=>run('snapshot.research_story.current.view');
 check('scientific story integrates with the existing navigation',doc.getElementById('primary-nav').innerHTML.includes('Scientific story'));
 check('published scientific quantities show SE n units and source IDs',html().includes('0.97 ± 0.04')&&html().includes('n=3')&&html().includes('mmol P')&&html().includes('E_PHOSPHATE_UPTAKE_8_27'));
 run("var savedStoryApi=api,releaseStory;api=(...args)=>new Promise((resolve,reject)=>{releaseStory=()=>savedStoryApi(...args).then(resolve,reject)});var delayedStory=storyPresent({});");
 check('presentation controls disable while a local view change is pending',doc.getElementById('story-detail').disabled&&doc.nodes.filter(n=>!n.removed&&n.dataset.storyStage).every(n=>n.disabled));
 await run('releaseStory();delayedStory');run('api=savedStoryApi');
 check('controls reenable after the server returns the accepted presentation',!doc.getElementById('story-detail').disabled&&run('storyBusy')===false);
 check('unknown lab run is not silently changed to zero',run('snapshot.research_story.content.actual_lab_run_id')===null);
 await fire('story-subject','change','8-42');check('source line selection changes paired source summaries',view().subject==='8-42'&&html().includes('0.65 ± 0.02'));
 const growth=doc.nodes.find(n=>!n.removed&&n.dataset.storyMetric==='growth');await growth.fire('click');
 check('growth and uptake keep separate units and plot labels',view().metric==='growth'&&html().includes('Growth · published mean ± SE')&&html().includes('d^-1'));
 await stage('identity');check('genome view is one qualified locus and reference chain',html().includes('4,772 nt')&&html().includes('752 aa')&&html().includes('Region hash only')&&html().includes('CC-503'));
 await stage('materials');check('proposed material records remain uninstantiated with parent links',html().includes('PLAN_DNA')&&html().includes('Planned record only')&&html().includes('Actual material / sample: Not linked'));
 await stage('fluorescence');check('fluorescence has no fabricated signal and GFP stays separate',html().includes('Not supplied')&&html().includes('no inserted GFP')&&!html().includes('1,000'));
 await fire('story-examples');check('synthetic math requires explicit selection and a global label',view().examples===true&&html().includes('SYNTHETIC WORKED EXAMPLES')&&html().includes('1,000')&&html().includes('2,500'));
 await stage('phosphorus');check('mass accounting keeps four distinct numerical endpoints',html().includes('60')&&html().includes('64')&&html().includes('10')&&html().includes('96')&&html().includes('0.8 mg P')&&html().includes('invented inputs'));
 await fire('story-graphic');const graphic=await downloads.at(-1).blob.text();
 check('stage SVG preserves synthetic labels and meaningful compartment numbers',downloads.at(-1).name==='traitweaver-phosphorus.svg'&&graphic.includes('SYNTHETIC ILLUSTRATION')&&graphic.includes('60%')&&graphic.includes('64%')&&graphic.includes('96%'));
 check('stage graphic contains no scripts external assets or session values',!graphic.includes('<script')&&!graphic.includes('href=')&&!graphic.includes('story_hash'));
 await stage('reactor');check('reactor module is a matched comparison not an inoculation recipe',html().includes('Independent reactor units')&&html().includes('not an apparatus specification or inoculation procedure'));
 await stage('plan');await fire('story-detail');check('scientist detail exposes controls readouts units and required decisions',view().scientist===true&&html().includes('Independent units')&&html().includes('Required before a laboratory run')&&html().includes('PLAN_PLANT_USE'));
 await fire('story-export');const saved=JSON.parse(await downloads.at(-1).blob.text());
 check('JSON export preserves the exact scientific story and presentation',saved.schema_version==='traitweaver.research_story_package.v1'&&saved.view.stage==='plan'&&saved.view.examples===true&&saved.content.synthetic_calculations.phosphorus.mass_closure_percent===96);
 await fire('story-readable');let text=await downloads.at(-1).blob.text();check('scientist brief retains proposed protocols boundaries and synthetic values',text.includes('SYNTHETIC mathematical illustration')&&text.includes('Readouts:')&&text.includes('Required before run:')&&text.includes('actual_lab_run_id'));
 const input=doc.getElementById('story-file');input.files=[{size:JSON.stringify(saved).length,text:async()=>JSON.stringify(saved)}];await input.fire('change');
 check('actual file handler restores source-readonly package without a tool',run('snapshot.research_story.current.reopened')===true&&view().examples===true&&html().includes('Reopened plan package'));
 let read=false;doc.getElementById('story-file').files=[{size:262145,text:async()=>{read=true;return '{}';}}];await doc.getElementById('story-file').fire('change');check('oversized scientific package rejected before file read',!read);
 const before=JSON.stringify(run('snapshot.research_story.current'));doc.getElementById('story-file').files=[{size:4,text:async()=>'{bad'}];await doc.getElementById('story-file').fire('change');
 check('corrupt import leaves prior scientific presentation unchanged',JSON.stringify(run('snapshot.research_story.current'))===before&&doc.getElementById('notice').classList.contains('error'));
 await fire('story-examples');await stage('fluorescence');check('hiding math restores missing fluorescence rather than zero',view().examples===false&&html().includes('Not supplied')&&!html().includes('1,000'));
 await run('refresh()');check('refresh keeps selected source presentation',view().stage==='fluorescence'&&view().scientist===true);
 check('underlying study and public reference remain unchanged',JSON.stringify(run('snapshot.current'))===coreBefore&&JSON.stringify(run('snapshot.public_algae'))===referenceBefore);
 check('all requests remain bounded local endpoints',requests.every(r=>r.path.startsWith('/api/')));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,socket_calls:0,external_requests:0,qualification:'Memory DOM with shipped scripts and actual handlers. Rendered layout/native picker qualification separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);process.exitCode=1;});
