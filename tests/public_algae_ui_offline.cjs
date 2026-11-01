'use strict';
// Actual shipped public controller, bounded memory DOM and fetch; no real network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const generated=spawnSync('python3',['-B','-c',`import json
from traitweaver import molecular,molecular_store,public_algae
from traitweaver.completed_cycle import CompletedCycle
c=CompletedCycle.from_file('data/synthetic-cycle/REVIEW_PACKAGE.json');s=c.current()
p={'current':s,'evidence':c.export()['source_bundle'],'eligible_checks':[],'history':[{'revision':r['revision'],'action':r['action']['type'],'saved_utc':r['saved_utc'],'hash':r['hash']} for r in c.history],'read_only':True,'completed_cycle':c.summary(),'molecular':molecular_store.Journal(molecular.catalog()).view(s),'public_algae':molecular_store.Journal(public_algae.catalog()).view(s),'public_algae_error':None,'live_enabled':False}
print(json.dumps(p))`],{encoding:'utf8',env:{PATH:'/usr/local/bin:/usr/bin:/bin',PYTHONPATH:'src',PYTHONNOUSERSITE:'1'}});
assert.equal(generated.status,0,generated.stderr);const data=JSON.parse(generated.stdout),clone=structuredClone;
let serverSnapshot=clone(data),savedPackage=null;const requests=[],downloads=[],checks=[],blobs=new Map();
const coreBefore=JSON.stringify(serverSnapshot.current),legacyBefore=JSON.stringify(serverSnapshot.molecular);
class Element{
 constructor(id,doc){this.id=id;this.doc=doc;this.owned=[];this.handlers={};this.attributes={};this.dataset={};this.files=[];this.value='';this.disabled=false;const set=new Set();this.classList={add:x=>set.add(x),remove:x=>set.delete(x),contains:x=>set.has(x),toggle:(x,v)=>{v=v??!set.has(x);v?set.add(x):set.delete(x);}};}
 set innerHTML(v){this.html=v;this.doc.parse(v,this);}get innerHTML(){return this.html||'';}
 addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}setAttribute(k,v){this.attributes[k]=v;}
 focus(){}scrollIntoView(){}
 async fire(type,extra={}){for(const fn of this.handlers[type]||[])await fn({target:this,preventDefault(){},...extra});}
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
   const n=new Element(attrs.id||'',this);n.attributes=attrs;n.disabled=/\sdisabled(?:\s|$)/.test(tag[2]);
   for(const [k,v] of Object.entries(attrs))if(k.startsWith('data-'))n.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;
   if(tag[1]==='textarea'){const end=html.indexOf('</textarea>',tag.index);n.value=html.slice(tag.index+tag[0].length,end);}
   owner.owned.push(n);this.nodes.push(n);if(n.id)this.ids.set(n.id,n);
  }
 }
 querySelectorAll(selector){const m=selector.match(/^\[data-([^\]]+)\]$/);if(m)return this.nodes.filter(n=>!n.removed&&n.attributes['data-'+m[1]]!==undefined);if(selector==='.demo-badge')return [this.getElementById('badge')];return [];}
}
const doc=new Document();for(const id of ['main','notice','primary-nav','breadcrumb-current','revision-label','assistant-panel','study-identity','navigation','menu-toggle','close-menu','badge'])doc.add(id);
const window={handlers:{},scrollTo(){},addEventListener(k,f){(this.handlers[k]??=[]).push(f);}};
const location={hash:'#gene-map'};
const memoryFetch=async(path,options={})=>{
 requests.push({path,method:options.method||'GET'});let value;
 if(path==='/api/session')value={token:'offline-session'};
 else if(path==='/api/state')value=clone(serverSnapshot);
 else if(path==='/api/public-algae/export.json')value=clone(savedPackage);
 else if(path==='/api/public-algae/export.txt')return {ok:true,text:async()=>('Public reference brief · XP_001700553.1 · PROVISIONAL')};
 else if(path==='/api/public-algae/save'){
  const b=JSON.parse(options.body),v=serverSnapshot.public_algae;assert.equal(b.expected_hash,serverSnapshot.current.hash);assert.equal(b.molecular_hash,v.current.hash);
  if(b.note==='simulate-error')return {ok:false,json:async()=>({error:'Offline stale reference review'})};
  const r={revision:v.current.revision+1,hash:String(v.current.revision+1).repeat(64).slice(0,64),saved_utc:'2026-10-30T00:00:00+00:00',action:{stage:b.stage},state:{selection:clone(b.selection),reviewed_stages:[b.stage],note:b.note,context:v.owning_context}};
  v.current=r;v.history.push({revision:r.revision,hash:r.hash,saved_utc:r.saved_utc,stage:b.stage});v.context_status='current';savedPackage={schema_version:'traitweaver.molecular_review.v2',catalog:clone(v.catalog),revisions:[clone(r)],limit:v.catalog.limit};value={public_algae:clone(v)};
 }else if(path==='/api/public-algae/open'){
  const b=JSON.parse(options.body);let p;try{p=JSON.parse(b.package_json);assert.equal(p.schema_version,'traitweaver.molecular_review.v2');}catch{return {ok:false,json:async()=>({error:'Invalid public reference review'})};}
  const v=serverSnapshot.public_algae;v.current=clone(p.revisions.at(-1));v.read_only=true;v.storage='imported_read_only';savedPackage=clone(p);value={public_algae:clone(v)};
 }else throw Error('Unexpected endpoint; no real network permitted: '+path);
 return {ok:true,json:async()=>value};
};
const context=vm.createContext({document:doc,window,location,fetch:memoryFetch,structuredClone,Blob,console,setTimeout:fn=>fn(),matchMedia:()=>({matches:false,addEventListener(){}}),URL:{createObjectURL(blob){const key='blob:memory-'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}}});
const run=s=>vm.runInContext(s,context);const html=()=>doc.getElementById('main').innerHTML;
const check=(name,v)=>{assert.ok(v,name);checks.push(name);};
const navigate=id=>{location.hash='#'+id;for(const f of window.handlers.hashchange||[])f();};
async function fire(id,type='click',value){const n=doc.getElementById(id);assert.ok(n,'Missing '+id);if(value!==undefined)n.value=value;await n.fire(type);}
async function stage(id){const n=doc.nodes.find(n=>!n.removed&&n.dataset.algaeStage===id);assert.ok(n,'Missing stage '+id);await n.fire('click');}
(async()=>{
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 check('real public reference is the default in existing mapping navigation',html().includes('XP_001700553.1')&&html().includes('GeneID:5726104')&&html().includes('CC-503 cw92 mt+'));
 check('header identifies the public reference rather than the owning synthetic Muse cycle',doc.getElementById('badge').textContent==='Public reference · offline'&&doc.getElementById('revision-label').textContent==='Reference review · revision 0');
 check('explicit selection is required even for one annotated transcript',run('algaeDraft.transcript_id')===null&&Boolean(doc.getElementById('algae-select-transcript')));
 check('source links resolve to local files and show locators and hashes',html().includes('/public-algae-source/refseq_XM_001700501.2.gb')&&html().includes(data.public_algae.catalog.sources.sources[0].sha256)&&html().includes('Materials and methods'));
 check('provisional annotation and strain equivalence limits remain visible',html().includes('PROVISIONAL')&&html().includes('unreviewed')&&html().includes('UVM4'));
 await fire('algae-select-transcript');check('actual selection resolves the public chain without changing saved selection',run('algaeDraft.transcript_id')==='XM_001700501.2'&&run('snapshot.public_algae.current.state.selection.transcript_id')===null);
 navigate('splice-map');check('real exon map does not invent alternative isoforms',html().includes('Three annotated exons. One admitted transcript.')&&!html().includes('Compare a second transcript'));
 await doc.nodes.find(n=>!n.removed&&n.dataset.algaeExon==='REF-exon-1').fire('click');
 const exon=doc.nodes.find(n=>!n.removed&&n.dataset.algaeExon==='REF-exon-2');await exon.fire('keydown',{key:'Enter'});
 check('click and keyboard exon inspection reveal exact genome transcript and protein intervals',html().includes('[726139, 726807)')&&html().includes('[1311, 1979)')&&html().includes('[181, 404)'));
 check('stop inclusion and codon boundary semantics are explicit',html().includes('2259 nt')&&html().includes('2256 nt → 752 aa')&&html().includes('not a GFF phase')&&html().includes('codon can span a junction'));
 navigate('crispr');await stage('question');await fire('algae-goal','change','decrease_expression');await stage('concept');
 check('goal dynamically changes the bounded CRISPR concept',html().includes('CRISPR interference concept')&&html().includes('not a validated intervention'));
 await stage('question');await fire('algae-goal','change','isoform_comparison');await stage('concept');
 check('real isoform comparison stays blocked when another transcript is absent',html().includes('Only one transcript is admitted; a real isoform comparison is unavailable.'));
 await fire('algae-note','input','<img src=x onerror=alert(1)>');await stage('review');
 check('notes are escaped and survive stage navigation',html().includes('&lt;img src=x')&&!html().includes('<img src=x')&&run('algaeNote').startsWith('<img'));
 await fire('algae-note','input','Public annotation review');await stage('measurements');
 check('experimental requirements are traced to their file without invented observations',html().includes('REQUIREMENTS.json')&&html().includes('No observation file has been admitted.')&&html().includes('recovered-product phosphorus'));
 await fire('algae-use-synthetic');check('synthetic example stays separate and explicitly labelled',html().includes('Synthetic coordinate example')&&run('molecularDraft.protein_id')==='DEMO-P-A.1');
 await fire('algae-use-public');check('returning to public mode preserves the public draft independently',run('algaeDraft.goal')==='isoform_comparison'&&run('algaeNote')==='Public annotation review');
 await fire('algae-save');check('save targets the v2 public reference journal only',requests.at(-1).path==='/api/public-algae/save'&&run('snapshot.public_algae.current.revision')===1);
 check('saved Muse study usage and legacy molecular review stay unchanged',JSON.stringify(serverSnapshot.current)===coreBefore&&JSON.stringify(serverSnapshot.molecular)===legacyBefore&&serverSnapshot.completed_cycle.estimated_cost_usd===data.completed_cycle.estimated_cost_usd);
 await fire('algae-export');const exported=await downloads.at(-1).blob.text();const p=JSON.parse(exported);
 check('download retains public source trace and v2 identity',p.schema_version==='traitweaver.molecular_review.v2'&&p.catalog.claims.length===4&&p.catalog.checks.translated_cds_equals_refseq_protein===true);
 await fire('algae-brief');check('readable export is local and labelled public',downloads.at(-1).name==='traitweaver-public-algae-review.txt'&&(await downloads.at(-1).blob.text()).includes('PROVISIONAL'));
 await fire('algae-note','input','simulate-error');await fire('algae-save');check('safe save error preserves the saved revision',doc.getElementById('notice').textContent==='Offline stale reference review'&&run('snapshot.public_algae.current.revision')===1);
 const posts=requests.filter(x=>x.method==='POST').length;doc.getElementById('algae-file').files=[{size:4194305,text:async()=>{throw Error('Do not read');}}];await fire('algae-file','change');
 check('oversized import is blocked before read or dispatch',requests.filter(x=>x.method==='POST').length===posts);
 doc.getElementById('algae-file').files=[{size:4,text:async()=>'{bad'}];await fire('algae-file','change');check('invalid import preserves current record',doc.getElementById('notice').textContent==='Invalid public reference review'&&run('snapshot.public_algae.current.revision')===1);
 doc.getElementById('algae-file').files=[{size:exported.length,text:async()=>exported}];await fire('algae-file','change');
 check('reopening public review is read-only',run('snapshot.public_algae.read_only')===true&&doc.getElementById('algae-save').disabled);
 run("snapshot.public_algae=null;snapshot.public_algae_error='Pinned public source validation failed';render();");
 check('source failure never silently substitutes a synthetic map',html().includes('public example is unavailable')&&!html().includes('DEMO-GENE-1.1')&&html().includes('Pinned public source validation failed'));
 check('controllers never request an external source or provider',requests.every(x=>x.path.startsWith('/api/'))&&requests.filter(x=>x.method==='POST').every(x=>['/api/public-algae/save','/api/public-algae/open'].includes(x.path)));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,real_network_requests:0,files_written:0,qualification:'Shipped controllers in memory, not rendered-browser or native file-dialog verification.'},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
