'use strict';
// Actual shipped controllers, memory-only DOM/files and local Python catalog.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const generated=spawnSync('python3',['-B','-c',`import json
from traitweaver import molecular,molecular_store
from traitweaver.completed_cycle import CompletedCycle
c=CompletedCycle.from_file('data/synthetic-cycle/REVIEW_PACKAGE.json')
b=molecular.catalog();j=molecular_store.Journal(b);s=c.current()
p={'current':s,'evidence':c.export()['source_bundle'],'eligible_checks':[],'history':[{'revision':r['revision'],'action':r['action']['type'],'saved_utc':r['saved_utc'],'hash':r['hash']} for r in c.history],'read_only':True,'completed_cycle':c.summary(),'molecular':j.view(s),'live_enabled':False}
cases=[]
for protein in [p['id'] for p in b['synthetic_models']['proteins']]+['P42212']:
 for t in [None]+[t['id'] for t in b['synthetic_models']['transcripts'] if t['protein_id']==protein]:
  for other in [None]+[x['id'] for x in b['synthetic_models']['transcripts'] if t is not None and x['gene_id']==b['transcript_maps'][t]['gene']['id'] and x['id']!=t]:
   selection={'protein_id':protein,'transcript_id':t,'comparison_id':other,'goal':'increase_expression'}
   cases.append({'selection':selection,'expected':molecular.assess(selection,b)})
print(json.dumps({'snapshot':p,'cases':cases}))`],{encoding:'utf8',env:{PATH:'/usr/local/bin:/usr/bin:/bin',PYTHONPATH:'src',PYTHONNOUSERSITE:'1'}});
assert.equal(generated.status,0,generated.stderr);const data=JSON.parse(generated.stdout),clone=structuredClone;
let serverSnapshot=clone(data.snapshot),savedPackage=null;const requests=[],downloads=[],checks=[],blobs=new Map();
const coreBefore=JSON.stringify(serverSnapshot.current);
class Element{
 constructor(id,doc){this.id=id;this.doc=doc;this.owned=[];this.handlers={};this.attributes={};this.dataset={};this.files=[];this.value='';this.disabled=false;const set=new Set();this.classList={add:x=>set.add(x),remove:x=>set.delete(x),contains:x=>set.has(x),toggle:(x,v)=>{v=v??!set.has(x);v?set.add(x):set.delete(x);}};}
 set innerHTML(v){this.html=v;this.doc.parse(v,this);}get innerHTML(){return this.html||'';}
 addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}setAttribute(k,v){this.attributes[k]=v;}
 focus(){}scrollIntoView(){}
 async fire(type){for(const fn of this.handlers[type]||[])await fn({target:this,preventDefault(){}});}
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
 requests.push({path,method:options.method||'GET'});
 let value;
 if(path==='/api/session')value={token:'synthetic-session'};
 else if(path==='/api/state')value=clone(serverSnapshot);
 else if(path==='/api/molecular/export.txt')return {ok:true,text:async()=>('Synthetic readable molecular brief · '+serverSnapshot.molecular.current.state.selection.protein_id)};
 else if(path==='/api/molecular/export.json')value=clone(savedPackage);
 else if(path==='/api/molecular/save'){
  const body=JSON.parse(options.body);assert.equal(body.expected_hash,serverSnapshot.current.hash);assert.equal(body.molecular_hash,serverSnapshot.molecular.current.hash);
  if(body.note.includes('simulate-error'))return {ok:false,json:async()=>({error:'Synthetic stale review'})};
  const v=serverSnapshot.molecular,r={revision:v.current.revision+1,hash:String(v.current.revision+1).repeat(64).slice(0,64),saved_utc:'2026-10-30T00:00:00+00:00',state:{selection:clone(body.selection),reviewed_stages:[body.stage],note:body.note,context:v.owning_context},action:{stage:body.stage}};
  v.current=r;v.history.push({revision:r.revision,hash:r.hash,saved_utc:r.saved_utc,stage:body.stage});v.context_status='current';
  savedPackage={schema_version:'traitweaver.molecular_review.v1',catalog:clone(v.catalog),revisions:[clone(r)],limit:v.catalog.limit};value={molecular:clone(v)};
 }else if(path==='/api/molecular/open'){
  const body=JSON.parse(options.body);let p;
  try{p=JSON.parse(body.package_json);assert.equal(p.schema_version,'traitweaver.molecular_review.v1');}catch{return {ok:false,json:async()=>({error:'Invalid molecular package'})};}
  const v=serverSnapshot.molecular;v.current=clone(p.revisions.at(-1));v.read_only=true;v.storage='imported_read_only';savedPackage=clone(p);value={molecular:clone(v)};
 }else throw Error('Unexpected endpoint; no real network permitted: '+path);
 return {ok:true,json:async()=>value};
};
const context=vm.createContext({document:doc,window,location,fetch:memoryFetch,structuredClone,Blob,console,setTimeout:fn=>fn(),matchMedia:()=>({matches:false,addEventListener(){}}),URL:{createObjectURL(blob){const key='blob:memory-'+blobs.size;blobs.set(key,blob);return key;},revokeObjectURL(){}}});
const run=s=>vm.runInContext(s,context);const html=()=>doc.getElementById('main').innerHTML;
const check=(name,v)=>{assert.ok(v,name);checks.push(name);};
const navigate=id=>{location.hash='#'+id;for(const f of window.handlers.hashchange||[])f();};
async function fire(id,type='click',value){const n=doc.getElementById(id);assert.ok(n,'Missing '+id);if(value!==undefined)n.value=value;await n.fire(type);}
(async()=>{
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 check('navigation contains all three molecular views',doc.getElementById('primary-nav').innerHTML.includes('Splicing maps')&&html().includes('One protein can have more than one transcript'));
 check('no transcript is selected implicitly',run('molecularDraft.transcript_id')===null);
 for(const item of data.cases){run('molecularDraft='+JSON.stringify(item.selection));const a=JSON.parse(run('JSON.stringify(molecularAnalysis(molecularDraft,snapshot.molecular.catalog))'));
  assert.equal(a.mapping_status,item.expected.mapping_status);assert.deepEqual(a.mapping,item.expected.mapping);
  if(a.comparison)for(const key of Object.keys(a.comparison))assert.deepEqual(a.comparison[key],item.expected.comparison[key]);
 }
 check('all permitted coordinate comparisons match authoritative Python assessment',true);
 run('molecularDraft=snapshot.molecular.current.state.selection;');
 const transcriptButton=doc.nodes.find(n=>!n.removed&&n.dataset.molecularTranscript==='DEMO-TX-A.1');await transcriptButton.fire('click');
 check('actual candidate click resolves synthetic identity chain',html().includes('DEMO-GENE-1.1')&&html().includes('TOY-ASSEMBLY.1'));
 navigate('splice-map');await fire('molecular-comparison','change','DEMO-TX-UTR.1');
 check('UTR comparison displays real zero coding and protein deltas',run('molecularAnalysis(molecularDraft,snapshot.molecular.catalog).comparison.coding_delta_nt')===0&&html().includes('U4'));
 const exon=doc.nodes.find(n=>!n.removed&&n.dataset.molecularExon==='U4');await exon.fire('click');
 check('exon inspector distinguishes noncoding null from phase zero',html().includes('Not supplied / noncoding')&&html().includes('Noncoding'));
 await fire('molecular-comparison','change','DEMO-TX-PARTIAL.1');
 check('incomplete coding model keeps protein projection unknown',html().includes('Unknown')&&html().includes('not divisible by three'));
 await fire('molecular-protein','change','DEMO-P-M.1');await fire('molecular-transcript','change','DEMO-TX-MINUS.1');
 check('minus strand explicitly shows reverse transcription direction',html().includes('right to left')&&html().includes('M1'));
 await fire('molecular-protein','change','P42212');
 check('public GFP remains unmapped rather than inheriting synthetic coordinates',html().includes('A gene label is not an exact mapping.')&&!html().includes('<svg viewBox'));
 navigate('crispr');await fire('molecular-goal','change','decrease_expression');
 const concept=doc.nodes.find(n=>!n.removed&&n.dataset.molecularStage==='concept');await concept.fire('click');
 check('objective and stage clicks change planning concept dynamically',html().includes('CRISPR interference concept'));
 await fire('molecular-note','input','<img src=x onerror=alert(1)>');
 const identityStage=doc.nodes.find(n=>!n.removed&&n.dataset.molecularStage==='identity');await identityStage.fire('click');
 check('review notes are escaped instead of becoming markup',html().includes('&lt;img src=x')&&!html().includes('<img src=x'));
 await fire('molecular-note','input','Synthetic checkpoint');
 const previous=doc.nodes.find(n=>!n.removed&&n.dataset.molecularStage==='transcripts');await previous.fire('click');
 check('unsaved notes survive stage navigation',doc.getElementById('molecular-note').value==='Synthetic checkpoint');
 await fire('molecular-save');
 check('save targets only separate molecular journal',requests.at(-1).path==='/api/molecular/save'&&run('snapshot.molecular.current.revision')===1);
 check('saved Muse cycle and usage remain unchanged',JSON.stringify(serverSnapshot.current)===coreBefore&&serverSnapshot.completed_cycle.estimated_cost_usd===data.snapshot.completed_cycle.estimated_cost_usd);
 await fire('molecular-export');const text=await downloads.at(-1).blob.text();check('download is a separately versioned molecular review',JSON.parse(text).schema_version==='traitweaver.molecular_review.v1');
 await fire('molecular-readable');check('readable export uses a local plain-text download',downloads.at(-1).name==='traitweaver-molecular-review.txt'&&(await downloads.at(-1).blob.text()).includes('P42212'));
 await fire('molecular-note','input','simulate-error');await fire('molecular-save');check('save errors are visible without a new revision',doc.getElementById('notice').textContent==='Synthetic stale review'&&run('snapshot.molecular.current.revision')===1);
 const posts=requests.filter(x=>x.method==='POST').length;doc.getElementById('molecular-file').files=[{size:4194305,text:async()=>{throw Error('Do not read');}}];await fire('molecular-file','change');check('oversize review refused before read or post',requests.filter(x=>x.method==='POST').length===posts);
 doc.getElementById('molecular-file').files=[{size:4,text:async()=>'{bad'}];await fire('molecular-file','change');check('invalid import leaves review intact',run('snapshot.molecular.current.revision')===1&&doc.getElementById('notice').textContent==='Invalid molecular package');
 doc.getElementById('molecular-file').files=[{size:text.length,text:async()=>text}];await fire('molecular-file','change');
 check('reopen preserves molecular record as read-only',run('snapshot.molecular.read_only')===true&&doc.getElementById('molecular-save').disabled);
 navigate('handoff');check('handoff distinguishes molecular exports from the original study and Muse package',html().includes('Separate molecular review')&&html().includes('separate versioned molecular JSON'));
 check('only bounded memory molecular mutations were used',requests.filter(x=>x.method==='POST').every(x=>['/api/molecular/save','/api/molecular/open'].includes(x.path)));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,coordinate_cases:data.cases.length,real_network_requests:0,files_written:0,qualification:'Actual scripts and handlers in memory; not rendered-browser or native file-dialog verification.'},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
