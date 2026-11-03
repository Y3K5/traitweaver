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
 constructor(id,doc){this.id=id;this.doc=doc;this.owned=[];this.handlers={};this.attributes={};this.dataset={};this.files=[];this.value='';this.disabled=false;this.checked=false;this.open=false;const set=new Set();this.classList={add:x=>set.add(x),remove:x=>set.delete(x),contains:x=>set.has(x),toggle:(x,v)=>{v=v??!set.has(x);v?set.add(x):set.delete(x);}};}
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
   const n=new Element(attrs.id||'',this);n.tag=tag[1];n.inScopeForm=tag.index>html.indexOf('<form id="intelligence-scope-form"')&&tag.index<html.indexOf('</form>')&&html.includes('<form id="intelligence-scope-form"');n.attributes=attrs;n.disabled=/\sdisabled(?:\s|$)/.test(tag[2]);n.checked=/\schecked(?:\s|$)/.test(tag[2]);n.open=/\sopen(?:\s|$)/.test(tag[2]);
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
 requests.push({path,method:options.method||'GET',body:options.body?JSON.parse(options.body):null});const r=await rpc({path,...options});
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
 check('v3 follow-up disclosure starts collapsed without an automatic request',!!doc.getElementById('intelligence-followup')&&!doc.getElementById('intelligence-followup').open&&!requests.some(r=>r.path.startsWith('/api/intelligence/followup/')));
 check('evidence map starts at missing recovery and preserves catalog source context',html().includes('Follow each claim back to its source')&&html().includes('Zero records is not a measured zero effect')&&html().includes('none has an admitted observation'));
 const mapRequests=requests.length,mapRevision=revision();
 await doc.nodes.find(n=>!n.removed&&n.dataset.evidenceEndpoint==='phosphate_uptake').fire('click');
 check('map browsing shows exact published uncertainty without changing scope or dispatch',html().includes('0.48 mmol P g dry_weight^-1 d^-1 ± 0.08 SE · n=3')&&requests.length===mapRequests&&revision()===mapRevision&&run('snapshot.intelligence.current.state.scope.target_endpoint')==='recovered_product_phosphorus');
 await doc.nodes.find(n=>!n.removed&&n.dataset.evidenceNode==='E_PHOSPHATE_UPTAKE_8_27').fire('click');
 check('observation inspector retains source locator, UVM4 context and typed connection',html().includes('Table 1 / PO4 uptake rate / 8-27')&&html().includes('PSR1 overexpression line in UVM4 background')&&html().includes('reported in'));
 const connection=id=>doc.nodes.find(n=>!n.removed&&n.dataset.evidenceNode===id&&n.attributes.class==='button');
 await connection('S_PSR1_2023').fire('click');
 await connection('E_GROWTH_UVM4').fire('click');
 const selectedEndpoint=()=>doc.nodes.find(n=>!n.removed&&n.dataset.evidenceEndpoint&&n.attributes['aria-pressed']==='true');
 check('typed source traversal to growth synchronizes endpoint highlight and observation inspector',run('intelligenceMapEndpoint')==='growth'&&selectedEndpoint().dataset.evidenceEndpoint==='growth'&&run('intelligenceMapNode')==='E_GROWTH_UVM4'&&html().includes('Table 1 / Specific growth rate / UVM4'));
 await connection('endpoint:growth').fire('click');
 check('typed endpoint traversal selects its record without changing saved scope or dispatching',run('intelligenceMapNode')==='endpoint:growth'&&selectedEndpoint().dataset.evidenceEndpoint==='growth'&&run('snapshot.intelligence.current.state.scope.target_endpoint')==='recovered_product_phosphorus'&&requests.length===mapRequests&&revision()===mapRevision);
 await fire('intelligence-map-continue');
 check('map continuation preserves the intelligence route without requests',location.hash==='#intelligence'&&requests.length===mapRequests);
 check('independent scope stays editable beside a read-only completed Muse cycle',!doc.getElementById('intelligence-endpoint').disabled&&run('snapshot.read_only')===true);
 const originalForm=doc.getElementById('intelligence-scope-form');await fire('intelligence-endpoint','change','phosphate_uptake');await fire('intelligence-growth','change','0');
 check('field changes retain the form and keep zero distinct from unknown',originalForm===doc.getElementById('intelligence-scope-form')&&run('intelligenceDraft.minimum_growth_ratio')===0);
 await fire('intelligence-growth','change','');doc.getElementById('intelligence-growth').value='0';
 await fire('intelligence-scope-form','submit');check('native-style value change without a change event still saves zero',run('snapshot.intelligence.current.state.scope.minimum_growth_ratio')===0);check('save creates separate scope revision with current context',revision()===1&&run('snapshot.intelligence.current.state.scope.target_endpoint')==='phosphate_uptake');
 await fire('intelligence-prepare');check('payload prepares without creating a revision or sending to a provider',revision()===1&&run('intelligencePreview.status')==='not_sent'&&html().includes('Exact public payload'));
 check('map uses the saved endpoint after scope revision',run('intelligenceMapEndpoint')==='phosphate_uptake');
 check('prepared body excludes owning free-text notes and targets bounded Muse schema',!run('intelligencePreview.body.input').includes('context_notes')&&run('intelligencePreview.body.max_output_tokens')===1024);
 await fire('intelligence-request-download');check('prepared request download is public and explicitly unsent',JSON.parse(await downloads.at(-1).blob.text()).status==='not_sent');
 await fire('intelligence-synthetic');check('synthetic selection persists a pre-result decision only',revision()===2&&run('snapshot.intelligence.current.state.cycles[0].result')===null&&html().includes('Run the saved local check'));
 check('cycle displays its synthetic provenance and pre-result purpose',html().includes('Why this check?')&&html().includes('Synthetic offline example'));
 await run("intelligencePost('synthetic',{phase:'selection',focus:'trait'})");check('duplicate selection is rejected without advancing history',revision()===2&&doc.getElementById('notice').classList.contains('error'));
 await fire('intelligence-run');check('actual local audit records source-bound supported association with zero margin',revision()===3&&html().includes('Actual local result')&&run('snapshot.intelligence.current.state.cycles[0].result.outcome')==='supported');
 await fire('intelligence-prepare');check('reassessment payload binds the saved result identity',run('intelligencePreview.phase')==='reassessment'&&run('JSON.parse(intelligencePreview.body.input).result.id')===run('snapshot.intelligence.current.state.cycles[0].result.id'));
 await fire('intelligence-synthetic');check('separate reassessment closes the cycle without automatic continuation',revision()===4&&run('snapshot.intelligence.current.state.cycles.length')===1&&html().includes('Separate reassessment'));
 check('continuation carries prior result and labelled requirements while blocking identical selection',html().includes('Deterministic local preview')&&html().includes('authored measurement requirement')&&doc.getElementById('intelligence-synthetic').disabled&&run('snapshot.intelligence.continuation.prior_cycles[0].result.id')===run('snapshot.intelligence.current.state.cycles[0].result.id'));
 const v2Revision=revision(),v2Owning=JSON.stringify(run('snapshot.intelligence.current'));
 check('v2 preparation requires an unchecked exact-preview acknowledgment',doc.getElementById('intelligence-next-prepare').disabled&&!doc.getElementById('intelligence-next-ack').checked);
 doc.getElementById('intelligence-next-ack').checked=true;await fire('intelligence-next-ack','change');await fire('intelligence-next-prepare');
 const v2Request=run('snapshot.intelligence_next.request');
 check('v2 request carries the actual prior result and only unchecked options',v2Request.schema_version==='traitweaver.intelligence_request.v2'&&JSON.parse(v2Request.body.input).continuation_context.prior_cycles[0].result.id===run('snapshot.intelligence.current.state.cycles[0].result.id')&&!v2Request.eligible_checks.includes('trait_evidence_audit')&&revision()===v2Revision);
 run('snapshot.intelligence.read_only=true;render()');
 check('read-only owning history disables v2 proposal updates even with matching lineage',doc.getElementById('intelligence-next-synthetic').disabled&&doc.getElementById('intelligence-next-validate').disabled);
 run('snapshot.intelligence.read_only=false;render()');
 await fire('intelligence-next-request-download');check('exact v2 download is unsent and excludes owning identifiers',JSON.parse(await downloads.at(-1).blob.text()).status==='not_sent'&&!v2Request.body.input.includes('study_id'));
 await fire('intelligence-next-check','change','transfer_coverage');await fire('intelligence-next-synthetic');
 check('synthetic v2 reply stays a typed proposal with actual prior references, never a new cycle',html().includes('Valid proposal only')&&run('snapshot.intelligence_next.proposal_review.receipt.provenance')==='synthetic_fixture'&&run('snapshot.intelligence_next.proposal_review.proposal.reviewed_result_ids.length')===1&&JSON.stringify(run('snapshot.intelligence.current'))===v2Owning&&doc.getElementById('intelligence-next-synthetic').disabled);
 const executionOwner=JSON.stringify(run('snapshot.intelligence.current')),executionProposal=JSON.stringify(run('snapshot.intelligence_next.package'));
 check('execution bridge requires a separate unchecked human approval',doc.getElementById('intelligence-execution-approve')?.disabled&&!doc.getElementById('intelligence-execution-ack')?.checked);
 const dispatches=()=>requests.filter(r=>r.path==='/api/intelligence/execution/run').length;
 const beforeApprovalDispatches=dispatches();
 const executionGuardSnapshot=structuredClone(run('snapshot.intelligence_execution'));
 run("snapshot.intelligence_execution=null;snapshot.intelligence_execution_error='Local execution history failed validation';render()");
 check('execution startup failure is visible and withholds fresh v1 selection',html().includes('Local execution history failed validation')&&doc.getElementById('intelligence-synthetic').disabled&&doc.getElementById('intelligence-prepare').disabled);
 context.executionGuardSnapshot=executionGuardSnapshot;run('snapshot.intelligence_execution=executionGuardSnapshot;snapshot.intelligence_execution_error=null;render()');
 doc.getElementById('intelligence-execution-ack').checked=true;await fire('intelligence-execution-ack','change');
 await fire('intelligence-growth','input','0');
 check('scope input immediately clears execution approval acknowledgment',!doc.getElementById('intelligence-execution-ack').checked&&doc.getElementById('intelligence-execution-approve').disabled);
 run('render()');
 doc.getElementById('intelligence-execution-ack').checked=true;await fire('intelligence-execution-ack','change');await fire('intelligence-execution-approve');
 check('approval saves a separate record without executing or modifying v1/v2',dispatches()===beforeApprovalDispatches&&run('snapshot.intelligence_execution.availability.can_run')===true&&JSON.stringify(run('snapshot.intelligence.current'))===executionOwner&&JSON.stringify(run('snapshot.intelligence_next.package'))===executionProposal);
 await fire('intelligence-execution-run');
 check('approved local check runs only on its separate action',dispatches()===beforeApprovalDispatches+1&&run('snapshot.intelligence_execution.availability.can_review')===true&&JSON.stringify(run('snapshot.intelligence.current'))===executionOwner&&JSON.stringify(run('snapshot.intelligence_next.package'))===executionProposal);
 check('v3 preparation waits for a separate human result review',run('snapshot.intelligence_followup.can_prepare')===false&&doc.getElementById('intelligence-followup-prepare').disabled);
 check('result requires an unchecked separate human review',doc.getElementById('intelligence-execution-reassess').disabled&&!doc.getElementById('intelligence-execution-review-ack').checked&&html().includes('Human review of authored result summary'));
 // Stale receipt review is a pure human acknowledgment; no stale execution or retry is permitted.
 run("const executionBeforeStaleReviewFixture=structuredClone(snapshot.intelligence_execution);snapshot.intelligence_execution.applicability='stale';snapshot.intelligence_execution.availability.can_review=true;snapshot.intelligence_execution.availability.can_run=true;snapshot.intelligence_execution.availability.can_retry=true;render()");
 check('stale recorded result remains available for explicit human review only',!doc.getElementById('intelligence-execution-review-ack').disabled&&doc.getElementById('intelligence-execution-run').disabled&&!run('intelligenceExecutionState(snapshot.intelligence).flags.retry')&&html().includes('earlier receipt in its original scope'));
 doc.getElementById('intelligence-execution-review-ack').checked=true;await fire('intelligence-execution-review-ack','change');
 check('acknowledging stale review enables only the human review action',!doc.getElementById('intelligence-execution-reassess').disabled&&dispatches()===beforeApprovalDispatches+1);
 run("const contextBeforeStaleReviewFixture=snapshot.intelligence.context_status;const draftBeforeStaleReviewFixture=structuredClone(intelligenceDraft);snapshot.intelligence.context_status='needs_review';intelligenceDraft={...intelligenceDraft,minimum_growth_ratio:.25};render()");
 await fire('intelligence-growth','input','.5');
 check('changed owning context and unsaved draft permit a fresh acknowledgment of the saved receipt only',!doc.getElementById('intelligence-execution-review-ack').disabled&&!doc.getElementById('intelligence-execution-review-ack').checked&&doc.getElementById('intelligence-execution-reassess').disabled&&doc.getElementById('intelligence-execution-run').disabled&&!run('intelligenceExecutionState(snapshot.intelligence).flags.retry')&&html().includes('earlier receipt in its original scope'));
 doc.getElementById('intelligence-execution-review-ack').checked=true;await fire('intelligence-execution-review-ack','change');
 check('fresh original-receipt acknowledgment remains actionable despite changed controls',!doc.getElementById('intelligence-execution-reassess').disabled&&dispatches()===beforeApprovalDispatches+1);
 run('snapshot.intelligence.context_status=contextBeforeStaleReviewFixture;intelligenceDraft=draftBeforeStaleReviewFixture');
 run('snapshot.intelligence_execution=executionBeforeStaleReviewFixture;intelligenceExecutionResetAcknowledgments();render()');
 doc.getElementById('intelligence-execution-review-ack').checked=true;await fire('intelligence-execution-review-ack','change');await fire('intelligence-execution-reassess');
 check('human reassessment does not dispatch another check or acquire model provenance',dispatches()===beforeApprovalDispatches+1&&!run('snapshot.intelligence_execution.availability.can_review')&&html().includes('No new Muse reassessment')&&JSON.stringify(run('snapshot.intelligence.current'))===executionOwner);
 const followupOwner=JSON.stringify(run('snapshot.intelligence.current')),followupV2=JSON.stringify(run('snapshot.intelligence_next.package')),followupExecution=JSON.stringify(run('snapshot.intelligence_execution.package'));
 const followupNavigationRequests=requests.length;await fire('intelligence-followup-open');
 check('explicit next-question navigation opens the compact disclosure without dispatch',doc.getElementById('intelligence-followup').open&&requests.length===followupNavigationRequests);
 check('v3 exact public preview requires its own fresh acknowledgment',doc.getElementById('intelligence-followup-prepare').disabled&&!doc.getElementById('intelligence-followup-ack').checked&&html().includes('One eligible check'));
 doc.getElementById('intelligence-followup-ack').checked=true;await fire('intelligence-followup-ack','change');
 const beforeFollowupFocus=requests.length;await focus('combinations');
 check('v3 focus change clears acknowledgment without dispatch or closing the disclosure',doc.getElementById('intelligence-followup-prepare').disabled&&!doc.getElementById('intelligence-followup-ack').checked&&doc.getElementById('intelligence-followup').open&&requests.length===beforeFollowupFocus);
 doc.getElementById('intelligence-followup-ack').checked=true;await fire('intelligence-followup-ack','change');await fire('intelligence-followup-prepare');
 const followupRequest=run('snapshot.intelligence_followup.request'),followupInput=JSON.stringify(JSON.parse(followupRequest.body.input));
 check('v3 request includes the actual bridge receipt and human review and excludes covered checks',followupRequest.schema_version==='traitweaver.intelligence_request.v3'&&followupInput.includes(run('snapshot.intelligence_execution.active.attempts[0].result.id'))&&followupInput.includes('human_acknowledgment_of_fixed_local_result')&&JSON.stringify(followupRequest.eligible_checks)===JSON.stringify(['combination_coverage']));
 await fire('intelligence-followup-request-download');check('exact v3 request download remains unsent',JSON.parse(await downloads.at(-1).blob.text()).request_sha256===followupRequest.request_sha256&&JSON.parse(await downloads.at(-1).blob.text()).status==='not_sent');
 await fire('intelligence-followup-check','change','combination_coverage');await fire('intelligence-followup-synthetic');
 check('synthetic v3 proposal alone remains a review and dispatches no check',run('snapshot.intelligence_followup.proposal_review.receipt.provenance')==='synthetic_fixture'&&html().includes('V3 proposal review only')&&doc.getElementById('intelligence-followup-synthetic').disabled&&dispatches()===beforeApprovalDispatches+1);
 check('reviewed v3 proposal has its own unchecked execution approval',!!doc.getElementById('intelligence-followup-execution-ack')&&!doc.getElementById('intelligence-followup-execution-ack').checked&&doc.getElementById('intelligence-followup-execution-approve').disabled&&html().includes('Approval is stored separately'));
 const beforeFollowupApprovalRequests=requests.length;
 await fire('intelligence-followup-execution-approve');
 check('v3 approval cannot dispatch before exact acknowledgment',requests.length===beforeFollowupApprovalRequests);
 doc.getElementById('intelligence-followup-execution-ack').checked=true;await fire('intelligence-followup-execution-ack','change');
 check('v3 acknowledgment enables approval but cannot run a check',!doc.getElementById('intelligence-followup-execution-approve').disabled&&doc.getElementById('intelligence-execution-run').disabled&&requests.length===beforeFollowupApprovalRequests);
 const exactFollowupHash=run('snapshot.intelligence_followup.review_hash');
 run('snapshot.intelligence_followup.review_hash="changed-review-fixture"');await fire('intelligence-followup-execution-approve');
 check('a changed v3 review hash invalidates an earlier approval acknowledgment before dispatch',requests.length===beforeFollowupApprovalRequests&&!run('intelligenceExecutionAcknowledged.approveFollowup'));
 context.exactFollowupHash=exactFollowupHash;run('snapshot.intelligence_followup.review_hash=globalThis.exactFollowupHash;render()');
 doc.getElementById('intelligence-followup-execution-ack').checked=true;await fire('intelligence-followup-execution-ack','change');
 await fire('intelligence-growth','input');
 check('unsaved input immediately clears v3 execution acknowledgment',!doc.getElementById('intelligence-followup-execution-ack').checked&&doc.getElementById('intelligence-followup-execution-approve').disabled);
 run('render()');
 for(const condition of ['snapshot.intelligence_followup.read_only=true','snapshot.intelligence_followup.applicability="stale"','snapshot.intelligence.read_only=true','snapshot.intelligence_execution.read_only=true','intelligenceDraft.minimum_growth_ratio=7']){
  const beforeGuard=structuredClone(run('({f:snapshot.intelligence_followup,v:snapshot.intelligence,e:snapshot.intelligence_execution,draft:intelligenceDraft})'));
  context.followupGuardState=beforeGuard;run(condition+';render()');
  check('v3 execution approval withheld for '+condition,doc.getElementById('intelligence-followup-execution-ack').disabled&&doc.getElementById('intelligence-followup-execution-approve').disabled);
  run('snapshot.intelligence_followup=globalThis.followupGuardState.f;snapshot.intelligence=globalThis.followupGuardState.v;snapshot.intelligence_execution=globalThis.followupGuardState.e;intelligenceDraft=globalThis.followupGuardState.draft;render()');
 }
 const followupSynthetic=run('snapshot.intelligence_followup.proposal_review.proposal'),followupSyntheticHash=run('snapshot.intelligence_followup.review_hash');
 doc.getElementById('intelligence-followup-ack').checked=true;await fire('intelligence-followup-ack','change');await fire('intelligence-followup-prepare');
 const followupImportedFixture={model:followupRequest.body.model,status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(followupSynthetic)}]}]};
 await fire('intelligence-followup-reply','input',JSON.stringify(followupImportedFixture));await fire('intelligence-followup-validate');
 check('saved v3 response validation is unverified and does not execute or mutate owning journals',run('snapshot.intelligence_followup.proposal_review.receipt.provenance')==='owner_imported_authenticity_unverified'&&dispatches()===beforeApprovalDispatches+1&&JSON.stringify(run('snapshot.intelligence.current'))===followupOwner&&JSON.stringify(run('snapshot.intelligence_next.package'))===followupV2&&JSON.stringify(run('snapshot.intelligence_execution.package'))===followupExecution);
 const archivedFollowup=doc.nodes.find(n=>!n.removed&&n.dataset.intelligenceFollowupHistory===followupSyntheticHash);assert.ok(archivedFollowup,'Synthetic v3 review stays archived');await archivedFollowup.fire('click');
 check('v3 archived proposal selection is read-only and preserves its original synthetic provenance',run('snapshot.intelligence_followup.read_only')===true&&run('snapshot.intelligence_followup.proposal_review.receipt.provenance')==='synthetic_fixture'&&doc.getElementById('intelligence-followup-validate').disabled&&doc.getElementById('intelligence-followup-execution-approve').disabled&&dispatches()===beforeApprovalDispatches+1);
 await fire('intelligence-followup-export');const followupExport=await downloads.at(-1).blob.text();
 doc.getElementById('intelligence-followup-file').files=[{size:followupExport.length,text:async()=>followupExport}];await fire('intelligence-followup-file','change');
 check('v3 export reopens read-only without changing source journals or dispatching',run('snapshot.intelligence_followup.read_only')===true&&JSON.stringify(run('snapshot.intelligence_followup.package'))===JSON.stringify(JSON.parse(followupExport))&&JSON.stringify(run('snapshot.intelligence.current'))===followupOwner&&JSON.stringify(run('snapshot.intelligence_next.package'))===followupV2&&JSON.stringify(run('snapshot.intelligence_execution.package'))===followupExecution&&dispatches()===beforeApprovalDispatches+1&&doc.getElementById('intelligence-followup-validate').disabled);
 await focus('transfer');
 check('bridge receipt visibly blocks duplicate v1 selection',doc.getElementById('intelligence-synthetic').disabled&&doc.getElementById('intelligence-prepare').disabled);
 const duplicateRevision=revision();await run("intelligencePost('synthetic',{phase:'selection',focus:'transfer'})");
 check('actual v1 admission rejects bridge duplicate without a revision',revision()===duplicateRevision&&doc.getElementById('notice').classList.contains('error'));
 await focus('trait');
 // A visibly synthetic failure view tests UI acknowledgment/routing only; server retry policy has separate handler tests.
 run("const executionBeforeFailureFixture=structuredClone(snapshot.intelligence_execution);const executionPostBeforeFailureFixture=intelligenceExecutionPost;let failureFixtureCalls=[];intelligenceExecutionPost=async(path,body)=>{failureFixtureCalls.push({path,body});};snapshot.intelligence_execution.status='failed';snapshot.intelligence_execution.active.attempts.at(-1).result={...snapshot.intelligence_execution.active.attempts.at(-1).result,status:'failed',outcome:'failed',facts:{},interpretation:'Synthetic UI fixture: local software check failed.'};snapshot.intelligence_execution.availability.can_retry=true;snapshot.intelligence_execution.availability.can_review=true;snapshot.intelligence_execution.availability.can_run=false;render()");
 await fire('intelligence-execution-retry');
 check('failure UI cannot approve a retry before explicit review',doc.getElementById('intelligence-execution-retry').disabled&&run('failureFixtureCalls.length')===0&&html().includes('Synthetic UI fixture'));
 doc.getElementById('intelligence-execution-retry-ack').checked=true;await fire('intelligence-execution-retry-ack','change');await fire('intelligence-execution-retry');
 check('reviewed failure routes a retry approval without running',run('failureFixtureCalls.length')===1&&run('failureFixtureCalls[0].path')==='retry'&&run('failureFixtureCalls[0].body.reason')==='reviewed_local_failure'&&run('failureFixtureCalls[0].body.acknowledged')===true);
 run("snapshot.intelligence_execution.active.attempts.push(structuredClone(snapshot.intelligence_execution.active.attempts[0]));snapshot.intelligence_execution.availability.can_retry=false;render()");
 check('second failure view displays final retry limit',doc.getElementById('intelligence-execution-retry').disabled&&html().includes('Two attempts are already recorded'));
 run('snapshot.intelligence_execution=executionBeforeFailureFixture;intelligenceExecutionPost=executionPostBeforeFailureFixture;render()');
 await fire('intelligence-execution-export');const executionExport=await downloads.at(-1).blob.text();
 doc.getElementById('intelligence-execution-file').files=[{size:executionExport.length,text:async()=>executionExport}];await fire('intelligence-execution-file','change');
 check('execution package reopens read-only with exact receipts and no dispatch',run('snapshot.intelligence_execution.read_only')===true&&JSON.stringify(run('snapshot.intelligence_execution.package'))===JSON.stringify(JSON.parse(executionExport))&&dispatches()===beforeApprovalDispatches+1&&doc.getElementById('intelligence-execution-run').disabled);
 await fire('intelligence-execution-local');
 check('returning to local execution history preserves duplicate protection',run('snapshot.intelligence_execution.read_only')===false&&dispatches()===beforeApprovalDispatches+1&&!run('snapshot.intelligence_execution.availability.can_run'));
 await fire('intelligence-next-export');const v2Export=await downloads.at(-1).blob.text();
 doc.getElementById('intelligence-next-file').files=[{size:v2Export.length,text:async()=>v2Export}];await fire('intelligence-next-file','change');
 check('v2 native-shaped reopen retains exact package and disables proposal updates',JSON.stringify(run('snapshot.intelligence_next.package'))===JSON.stringify(JSON.parse(v2Export))&&run('snapshot.intelligence_next.read_only')===true&&doc.getElementById('intelligence-next-validate').disabled&&revision()===v2Revision);
 doc.getElementById('intelligence-next-ack').checked=true;await fire('intelligence-next-ack','change');
 const nextRequests=requests.length,nextRevision=revision();
 await doc.nodes.find(n=>!n.removed&&n.dataset.continuationFocus==='combinations').fire('click');
 check('reviewing a deterministic alternative changes only focus, without request or revision',requests.length===nextRequests&&revision()===nextRevision&&run('intelligenceFocus')==='combinations'&&html().includes('Preferred next check:</strong> Protein-combination coverage audit')&&!doc.getElementById('intelligence-synthetic').disabled);
 check('changing preferred focus clears v2 preparation acknowledgment',doc.getElementById('intelligence-next-prepare').disabled&&!doc.getElementById('intelligence-next-ack').checked);
 check('combination pane shows unresolved role slots and unknown pair effects',html().includes('Protein identity unavailable')&&html().includes('Zero records is different'));
 await fire('intelligence-synthetic');await fire('intelligence-run');await fire('intelligence-synthetic');
 check('combination audit and reassessment retain unavailable effects',run('snapshot.intelligence.current.state.cycles[1].result.facts.synergy')===null&&run('snapshot.intelligence.current.state.cycles[1].assessment.outcome')==='unavailable');
 check('covered v1 and bridge inputs stop v3 continuation without erasing historical review',run('snapshot.intelligence_followup.can_prepare')===false&&doc.getElementById('intelligence-followup-prepare').disabled&&run('snapshot.intelligence_followup.applicability')==='stale'&&html().includes('No eligible local check remains'));
 check('v1 progression labels older v2 history stale while preserving its proposal',run('snapshot.intelligence_next.applicability')==='stale'&&run('snapshot.intelligence_next.proposal_review.proposal.check')==='transfer_coverage'&&doc.getElementById('intelligence-next-synthetic').disabled&&html().includes('Only one check is eligible'));
 await focus('transfer');await fire('intelligence-recipient','change','study_uvm4');await fire('intelligence-scope-form','submit');
 check('recipient change preserves earlier cycles and marks reassessment',run("snapshot.intelligence.current.state.cycles[0].applicability")==='needs_reassessment'&&html().includes('same species different context'));
 await fire('intelligence-synthetic');await fire('intelligence-run');await fire('intelligence-synthetic');
 check('transfer review refuses a success probability or cross-species claim',run('snapshot.intelligence.current.state.cycles.at(-1).result.facts.transfer_success_probability')===null&&html().includes('No cross-species recipient'));
 check('all covered inputs stop continuation even after an unrelated recipient change',run('snapshot.intelligence.continuation.status')==='stop_no_new_inputs'&&html().includes('Stop: no unchecked inputs remain')&&doc.getElementById('intelligence-synthetic').disabled&&doc.getElementById('intelligence-prepare').disabled);
 await fire('intelligence-continuation-download');const localPreview=JSON.parse(await downloads.at(-1).blob.text());
 check('local preview export is versioned, contains two-cycle lineage and is not a model request',localPreview.schema_version==='traitweaver.intelligence_continuation.v1'&&localPreview.prior_cycles.length===3&&localPreview.model_request===false&&localPreview.human_review_required===true);
 // A changed saved question admits one new audit; actual v3 approval reuses the existing execution controller.
 await focus('trait');await fire('intelligence-endpoint','change','growth');await fire('intelligence-scope-form','submit');
 doc.getElementById('intelligence-followup-ack').checked=true;await fire('intelligence-followup-ack','change');await fire('intelligence-followup-prepare');await fire('intelligence-followup-synthetic');
 const v3ExecutionBefore=JSON.stringify(run('snapshot.intelligence_execution.package')),v3SourceBefore=JSON.stringify(run('snapshot.intelligence.current')),v3ReviewBefore=JSON.stringify(run('snapshot.intelligence_followup.package')),v3NextBefore=JSON.stringify(run('snapshot.intelligence_next.package')),v3DispatchBefore=dispatches();
 const v3Binding=run('({intelligence_hash:snapshot.intelligence.current.hash,execution_hash:snapshot.intelligence_execution.execution_hash,followup_review_hash:snapshot.intelligence_followup.review_hash,expected_hash:snapshot.current.hash})');
 doc.getElementById('intelligence-followup-execution-ack').checked=true;await fire('intelligence-followup-execution-ack','change');await fire('intelligence-followup-execution-approve');
 const v3ApprovalRequest=requests.filter(r=>r.path==='/api/intelligence/execution/approve-followup').at(-1);
 check('v3 approval binds the exact owning execution and proposal hashes',!!v3ApprovalRequest&&Object.entries(v3Binding).every(([key,value])=>v3ApprovalRequest.body[key]===value)&&v3ApprovalRequest.body.acknowledged===true);
 check('v3 approval is separate from immutable proposal artifacts and runs nothing',JSON.stringify(run('snapshot.intelligence_execution.package'))!==v3ExecutionBefore&&JSON.stringify(run('snapshot.intelligence.current'))===v3SourceBefore&&JSON.stringify(run('snapshot.intelligence_followup.package'))===v3ReviewBefore&&JSON.stringify(run('snapshot.intelligence_next.package'))===v3NextBefore&&dispatches()===v3DispatchBefore&&run('snapshot.intelligence_execution.active.approval.proposal_version')==='v3'&&html().includes('Approval source:</strong> V3')&&!doc.getElementById('intelligence-execution-run').disabled);
 check('approved v3 source stays inspectable as proposal-only while fresh approval is blocked',html().includes('V3 proposal review only')&&html().includes('Approval recorded separately')&&doc.getElementById('intelligence-followup-execution-approve').disabled&&run('snapshot.intelligence_followup.applicability')==='stale');
 const beforeInspectExecution=requests.length;await fire('intelligence-followup-execution-inspect');
 check('inspecting the separately stored v3 approval cannot dispatch a check',requests.length===beforeInspectExecution);
 await fire('intelligence-execution-run');
 check('v3 approved audit uses only the separate shared Run action',dispatches()===v3DispatchBefore+1&&run('snapshot.intelligence_execution.active.attempts.at(-1).result.check')==='trait_evidence_audit'&&doc.getElementById('intelligence-execution-reassess').disabled&&JSON.stringify(run('snapshot.intelligence.current'))===v3SourceBefore);
 doc.getElementById('intelligence-execution-review-ack').checked=true;await fire('intelligence-execution-review-ack','change');await fire('intelligence-execution-reassess');
 check('v3 audit ends in human acknowledgment and no-new-input stop without a model call',run('snapshot.intelligence_execution.active.reassessment.provenance')==='human_acknowledgment_of_fixed_local_result'&&run('snapshot.intelligence_followup.preview.status')==='stop_no_new_inputs'&&dispatches()===v3DispatchBefore+1&&JSON.stringify(run('snapshot.intelligence_followup.package'))===v3ReviewBefore&&JSON.stringify(run('snapshot.intelligence_next.package'))===v3NextBefore);
 // Existing v1 preparation remains byte-compatible; direct admission still rejects bad responses.
 await run("intelligencePost('prepare',{phase:'selection',focus:'transfer'})");const before=revision();run("document.getElementById('intelligence-reply').value=JSON.stringify({model:'muse-spark-1.3',status:'completed',output:[{type:'function_call',name:'shell'}]})");await fire('intelligence-accept');
 check('rejected provider action cannot execute or save',revision()===before&&doc.getElementById('notice').classList.contains('error'));
 await fire('intelligence-export');const exported=await downloads.at(-1).blob.text(),packageData=JSON.parse(exported);
 check('download contains versioned source-bound accepted history and no raw provider reply',packageData.schema_version==='traitweaver.intelligence_package.v1'&&packageData.catalog.reference.strain.includes('CC-503')&&!exported.includes('function_call'));
 await fire('intelligence-readable');check('readable download retains qualification and separate result/reassessment',downloads.at(-1).name==='traitweaver-intelligence-review.txt'&&(await downloads.at(-1).blob.text()).includes('PROVISIONAL')&&(await downloads.at(-1).blob.text()).includes('SEPARATE REASSESSMENT'));
 const posts=requests.filter(x=>x.method==='POST').length;doc.getElementById('intelligence-file').files=[{size:4194305,text:async()=>{throw Error('Do not read');}}];await fire('intelligence-file','change');
 check('oversize import is rejected before file read or handler dispatch',requests.filter(x=>x.method==='POST').length===posts);
 doc.getElementById('intelligence-file').files=[{size:4,text:async()=>'{bad'}];await fire('intelligence-file','change');check('malformed import preserves current history',revision()===before);
 doc.getElementById('intelligence-file').files=[{size:exported.length,text:async()=>exported}];await fire('intelligence-file','change');
 check('file reopening restores actual package as read-only without execution',run('snapshot.intelligence.read_only')===true&&doc.getElementById('intelligence-synthetic').disabled&&revision()===before);
 check('reopen reconstructs the source map without adding a graph to the package',run('snapshot.intelligence.evidence_map.catalog_sha256')===run('snapshot.intelligence.current.catalog_sha256')&&!Object.hasOwn(packageData,'evidence_map'));
 location.hash='#handoff';for(const f of window.handlers.hashchange||[])f();check('handoff exposes a separate intelligence package without changing original exports',html().includes('Separate Muse intelligence package')&&html().includes('versioned intelligence package'));
 const state=await memoryFetch('/api/state',{headers:{'X-Traitweaver-Client':'workspace'}});const final=await state.json();
 check('original completed study and public-reference journal remain bit-for-bit unchanged',JSON.stringify(final.current)===coreBefore&&JSON.stringify(final.public_algae)===referenceBefore);
 check('only bounded local intelligence mutations were dispatched',requests.filter(x=>x.method==='POST').every(x=>x.path.startsWith('/api/intelligence/')));
 console.log(JSON.stringify({status:'passed',checks:checks.length,scenarios:checks,actual_handlers:true,actual_python_core:true,socket_calls:0,external_requests:0,files_written:0,qualification:'Memory DOM and actual memory handlers; rendered-browser checks remain separate.'},null,2));
 }finally{bridge.stdin.end();}})().catch(e=>{console.error(e);bridge.kill();process.exitCode=1;});
