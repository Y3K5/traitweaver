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
 closest(selector){return this.inScopeForm&&selector==='#'+this.formId?this.doc.getElementById(this.formId):null;}
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
   const n=new Element(attrs.id||'',this);n.tag=tag[1];const form=html.match(/<form id="([^"]+)"/);n.formId=form?.[1];n.inScopeForm=!!form&&tag.index>form.index&&tag.index<html.indexOf('</form>',form.index);n.attributes=attrs;n.checked=/\schecked(?:\s|$)/.test(tag[2]);n.disabled=/\sdisabled(?:\s|$)/.test(tag[2]);
   for(const [k,v] of Object.entries(attrs))if(k.startsWith('data-'))n.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;
   if(tag[1]==='input')n.value=attrs.value||'';
   if(tag[1]==='select'){const end=html.indexOf('</select>',tag.index),part=html.slice(tag.index+tag[0].length,end);const choices=[...part.matchAll(/<option value="([^"]*)"([^>]*)>/g)];n.value=(choices.find(x=>x[2].includes('selected'))||choices[0]||[])[1]||'';}
   if(tag[1]==='textarea'){const end=html.indexOf('</textarea>',tag.index);n.value=html.slice(tag.index+tag[0].length,end).replaceAll('&amp;','&').replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&quot;','\"').replaceAll('&#39;',"'");}
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
 for(const file of ['completed-cycle-ui.js','molecular-ui.js','public-algae-ui.js','intelligence-ui.js','data-flow-ui.js','assistant-ui.js','research-story-ui.js','workbench-ui.js','workspace.js'])await run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
 location.hash='#workbench';run('render()');
 const stage=async id=>{const n=doc.nodes.find(n=>!n.removed&&n.dataset.wbCheckpoint===id);assert.ok(n);await n.fire('click');};
 const value=()=>run('snapshot.workbench');
 check('existing navigation exposes workbench without removing original views',doc.getElementById('primary-nav').innerHTML.includes('Study workbench')&&doc.getElementById('primary-nav').innerHTML.includes('Protein ↔ gene'));
 check('independent annotations remain editable over read-only original cycle',!doc.getElementById('wb-question').disabled&&!doc.getElementById('wb-notes').disabled&&!doc.getElementById('wb-save').disabled);
 check('research areas have accessible study cards',doc.nodes.filter(n=>!n.removed&&n.dataset.wbCase).length===4&&html().includes('Synthetic practice study'));
 check('question leads the main screen while technical records are expandable',html().includes('Could algae make phosphorus worth recovering?')&&html().includes('Open the saved record · source IDs, inputs and output')&&html().includes('Why this step?'));
 check('friendly source names preserve the endpoint without inventing a subject',run("wbSourceName(snapshot.workbench,'E_OVERPLUS_REMOVAL')").includes('removal')&&!run("wbSourceName(snapshot.workbench,'E_OVERPLUS_REMOVAL')").includes('undefined'));
 check('synthetic server cannot claim saved real Muse work',html().includes('Synthetic replay loaded')&&!html().includes('Saved real Muse cycle · algae only'));
 check('three columns share original public scientific evidence',html().includes('wb-frame')&&html().includes('wb-center')&&html().includes('wb-audit')&&html().includes('0.97 ± 0.04')&&html().includes('n=3'));
 check('desktop workbench hides original nav until menu opened',doc.body.classList.contains('workbench-mode')&&doc.getElementById('navigation').inert===true);
 await fire('menu-toggle');check('menu toggles accessible original navigation',doc.getElementById('navigation').inert===false&&doc.getElementById('menu-toggle').attributes['aria-expanded']==='true');
 await fire('close-menu');check('close menu restores inert hidden navigation',doc.getElementById('navigation').inert===true);
 await fire('wb-notes','input','Public-source annotation');await stage('identity');
 check('unsaved draft survives checkpoint presentation without becoming saved evidence',doc.getElementById('wb-notes').value==='Public-source annotation'&&value().annotation.notes===''&&value().science.local_checks.length===0);
 await fire('wb-case','change','PROTEIN_GFP');check('unsaved case change blocked and selected value restored',value().current.case_id==='ENV_ALGAE'&&doc.getElementById('wb-case').value==='ENV_ALGAE');
 await fire('wb-form','submit');check('explicit annotation save creates immutable successor',value().annotations.length===2&&value().annotation.notes==='Public-source annotation');
 check('identity uses current reference metadata and existing mapping links',html().includes('4772 nt')&&html().includes('752 aa')&&html().includes('#gene-map')&&html().includes('#splice-map'));
 const source=doc.nodes.find(n=>!n.removed&&n.dataset.wbSources);await source.fire('click');
 check('citation opens source drawer without executing tool',doc.getElementById('wb-source-tab').attributes['aria-selected']==='true'&&value().science.local_checks.length===0);
 await doc.getElementById('wb-source-tab').fire('keydown',{key:'Home'});check('audit tabs support keyboard navigation and selection',doc.getElementById('wb-audit-tab').attributes['aria-selected']==='true');
 await stage('check');await fire('wb-check');check('only explicit check dispatch records pre-result purpose and actual receipt',value().science.local_checks.length===1&&value().science.local_checks[0].decision.policy==='explicit_user_selected_local_check'&&doc.getElementById('wb-check').disabled);
 await stage('actions');check('proposal preview shows three complete task cards',html().includes('Three proposed actions')&&value().science.accepted_review===null&&doc.nodes.filter(n=>!n.removed&&n.dataset.wbSources).length>=3);
 await fire('wb-synthetic');check('synthetic prioritization is explicitly labelled and does not call model',value().science.accepted_review.receipt.provenance==='synthetic_fixture'&&html().includes('Sample priorities saved · synthetic response')&&doc.getElementById('wb-synthetic').disabled);
 await fire('wb-muse-prepare');check('Muse input preview is exact public not-sent data with no notes',run('wbPrepared').status==='not_sent'&&run('wbPrepared').body.model==='muse-spark-1.3'&&run('wbPrepared').body.max_output_tokens===1024&&!JSON.stringify(run('wbPrepared')).includes('Public-source annotation')&&html().includes('Exact unsent request'));
 await stage('plan');check('existing measurement cards retain independent units and researcher gates',html().includes('Independent units')&&html().includes('no executable edit/cassette/inoculation protocol'));
 await stage('export');check('export review exposes every saved annotation including immutable earlier text',html().includes('Review all saved notes (2 versions)')&&html().includes('Public-source annotation'));const count=downloads.length;await fire('wb-export');check('export refused before current annotation acknowledgment',downloads.length===count&&doc.getElementById('notice').classList.contains('error'));
 doc.getElementById('wb-privacy').checked=true;await fire('wb-privacy','change');await fire('wb-export');
 const saved=JSON.parse(await downloads.at(-1).blob.text());check('JSON contains exact history science and accepted local records',saved.schema_version==='traitweaver.workbench_package.v1'&&saved.annotations.length===2&&saved.annotations[1].notes==='Public-source annotation'&&saved.science.local_checks.length===1&&saved.human_review==='not_reviewed');
 await fire('wb-markdown');const markdown=await downloads.at(-1).blob.text();check('readable export retains unknowns labels and no hidden approval',markdown.includes('Human scientific review: NOT REVIEWED')&&markdown.includes('Public-source annotation')&&markdown.includes('actual\\_lab\\_run\\_id\":null'));
 const input=doc.getElementById('wb-file');input.files=[{size:JSON.stringify(saved).length,text:async()=>JSON.stringify(saved)}];await input.fire('change');
 check('file handler reopens exact science and all annotations read-only',value().current.read_only&&value().annotations.length===2&&JSON.stringify(value().science)===JSON.stringify(saved.science));
 await stage('check');check('read-only imported audit cannot rerun',doc.getElementById('wb-check').disabled&&doc.getElementById('wb-save').disabled);
 await stage('export');let read=false;doc.getElementById('wb-file').files=[{size:524289,text:async()=>{read=true;return '{}';}}];await fire('wb-file','change');check('oversize import refused before content read',!read);
 const before=JSON.stringify(value().current);doc.getElementById('wb-file').files=[{size:4,text:async()=>'{bad'}];await fire('wb-file','change');check('corrupt import preserves earlier valid view',JSON.stringify(value().current)===before);
 await fire('wb-return');check('return restores editable local case history rather than imported state',!value().current.read_only&&value().annotations.length===2);
 const gfpCard=doc.nodes.find(n=>!n.removed&&n.dataset.wbCase==='PROTEIN_GFP');await gfpCard.fire('click');check('human study card selects the preserved GFP case without implying algae AI applies',value().current.case_id==='PROTEIN_GFP'&&html().includes('First real Muse review pending')&&!html().includes('Saved real Muse cycle · algae only'));await stage('check');await fire('wb-check');check('GFP uses qualified existing source IDs and audit',value().science.local_checks[0].result.sequence_length===238&&value().science.case.case_id==='PROTEIN_GFP');
 await fire('wb-case','change','RNA_SYNTHETIC');await stage('check');await fire('wb-check');check('incomplete synthetic RNA metadata keeps zero versus null and readiness blocked',value().science.local_checks[0].result.fastq_files_supplied===0&&value().science.local_checks[0].result.read_count===null&&value().science.local_checks[0].result.analysis_ready===false);
 await fire('wb-case','change','REPRO_SYNTHETIC');await stage('check');await fire('wb-check');check('synthetic reproducibility stays unverified despite exit zero',value().science.local_checks[0].result.exit_code===0&&!value().science.local_checks[0].result.reproducibility_verified);
 await fire('wb-notes','input','Cookie: SYNTHETIC_CANARY');await fire('wb-form','submit');await stage('export');
 check('privacy finding exposes category and field rather than sensitive snippet',value().privacy.status==='blocked'&&value().privacy.findings[0].field==='notes'&&!JSON.stringify(value().privacy).includes('SYNTHETIC_CANARY')&&doc.getElementById('wb-export').disabled);
 await fire('wb-notes','input','Clean current annotation');await fire('wb-form','submit');check('older finding still blocks export with no silent history deletion',value().privacy.status==='blocked'&&value().annotations[1].notes==='Cookie: SYNTHETIC_CANARY');
 await fire('wb-case','change','ENV_ALGAE');await stage('export');doc.getElementById('wb-privacy').checked=true;await fire('wb-privacy','change');await stage('identity');await stage('export');
 check('changed view invalidates prior privacy acknowledgment',run('wbPrivacyHash')===null&&!doc.getElementById('wb-privacy').checked);
 location.hash='#research-story';run('render()');check('other views restore original layout and navigation',!doc.body.classList.contains('workbench-mode')&&!doc.getElementById('navigation').inert);
 location.hash='#workbench';run('render()');await run('refresh()');check('refresh preserves annotation history without new dispatch',value().annotations.length===2&&value().science.local_checks.length===1);
 check('underlying study and public mapping remain unchanged',JSON.stringify(run('snapshot.current'))===coreBefore&&JSON.stringify(run('snapshot.public_algae'))===referenceBefore);
 run("snapshot.completed_cycle.synthetic=false;render()");check('renderer exposes loaded real-cycle contribution only for the algae study',html().includes('Saved real Muse cycle · algae only')&&html().includes('these new action cards have not had a live review'));await fire('wb-case','change','RNA_SYNTHETIC');check('a saved algae contribution never promotes another area to real AI reviewed',!html().includes('Saved real Muse cycle · algae only')&&html().includes('First real Muse review pending'));run("snapshot.completed_cycle.synthetic=true;render()");
 check('all controller requests remain bounded local endpoints',requests.every(r=>r.path.startsWith('/api/')));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,socket_calls:0,external_requests:0,qualification:'Memory DOM and actual shipped handlers; native layout/picker qualification separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);process.exitCode=1;});
