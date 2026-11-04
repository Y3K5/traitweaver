"""Standalone local read-only explorer. No remote fonts, scripts or requests."""
from .core import canonical


def render(package, trails):
    data=canonical({'package':package,'trails':trails}).replace('<','\\u003c').replace('&','\\u0026')
    return HTML.replace('__STUDY_DATA__',data)


HTML='''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>Traitweaver · Research review</title><style>
:root{color-scheme:light;--ink:#142c31;--line:#cad6cf;--paper:#f5f3eb;--green:#125747;--muted:#526b68}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,sans-serif}
main{max-width:1280px;margin:auto;padding:36px 28px}header{border-bottom:1px solid var(--line);padding-bottom:24px}
.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:700;color:var(--green)}h1{font:clamp(36px,5vw,60px)/1.1 Georgia,serif;margin:15px 0}h2{font:30px Georgia,serif}h3{margin:0 0 8px}
.notice{padding:14px 18px;background:#fff0cd;border-left:4px solid #946a18;border-radius:4px}.muted{color:var(--muted)}
.stats{display:flex;flex-wrap:wrap;gap:16px;margin:22px 0}.stat{background:white;padding:16px 22px;min-width:150px;border:1px solid var(--line);border-radius:10px}.stat b{display:block;font:30px Georgia,serif}
.controls{display:flex;flex-wrap:wrap;gap:15px;margin:25px 0}label{font-size:13px;font-weight:600}input,select{display:block;padding:10px;font:inherit;border:1px solid #879c95;border-radius:6px;background:white;max-width:100%}
input{min-width:290px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,500px),1fr));gap:18px}
article{border:1px solid var(--line);border-radius:12px;padding:24px;background:white}.badge{display:inline-block;padding:3px 9px;margin:0 5px 8px 0;border-radius:20px;background:#edf2ed;font-size:12px}.synthetic{background:#fff0cd}
.flow{display:flex;gap:6px;align-items:stretch;margin:20px 0;overflow:auto}.node{padding:10px;border:1px solid #9bb8ac;border-radius:6px;flex:1;min-width:105px;font-size:13px}.node small{display:block;color:var(--muted)}.arrow{align-self:center;color:var(--green)}
details{border-top:1px solid var(--line);padding-top:12px;margin-top:18px}summary{cursor:pointer;font-weight:600}a{color:#06604b;overflow-wrap:anywhere}.dashed{border-style:dashed}.row{padding:12px 0;border-bottom:1px solid var(--line)}
pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f2;padding:12px;max-height:400px;overflow:auto}
button{padding:9px 14px;border:1px solid var(--green);border-radius:6px;background:white;color:var(--green);cursor:pointer}footer{margin-top:40px;border-top:1px solid var(--line);padding-top:16px;font-size:13px}
@media(max-width:600px){main{padding:24px 16px}.flow{flex-direction:column}.arrow{transform:rotate(90deg)}.stat{flex:1}input{min-width:0;width:100%}.controls label{width:100%}}
</style></head><body><main>
<header><span class="eyebrow">TRAITWEAVER / CLOUD RESEARCH NOTEBOOK</span><h1>Traits, with their evidence.</h1>
<p>A source → component → recipient → endpoint review pipeline. Every link belongs to a study and its conditions.</p></header>
<p class="notice"><b>Offline software trial.</b> All displayed observations are synthetic test fixtures. No Muse request was sent. The six real workbook cases have not been imported or scientifically reviewed.</p>
<div id="stats" class="stats"></div>
<section aria-labelledby="trail-title"><h2 id="trail-title">Six real research trails · awaiting sources</h2><div id="trails"></div></section>
<section aria-labelledby="explorer-title"><h2 id="explorer-title">Inspect the pipeline</h2>
<p class="muted">Workbook: five reported human-curated categories, not yet verified here. Existing app: six illustrative capability categories. Neither is a Muse clustering result. Test categories below belong only to this synthetic trial.</p>
<div class="controls"><label>Search trait, component or recipient<input id="search" type="search" placeholder="e.g. extracted enzyme"></label>
<label>Endpoint scope<select id="scope"><option value="">All scopes</option><option>extracted_enzyme</option><option>intact_cell</option><option>whole_organism</option><option>material</option><option>unknown</option></select></label>
<label>Order<select id="order"><option value="trait">Trait name</option><option value="scope">Endpoint scope</option><option value="review">Review status</option></select></label>
<button id="reset" type="button">Reset filters</button></div><p id="count" aria-live="polite"></p><div id="cards" class="cards"></div></section>
<section><h2>Combinations remain separate</h2><p>Solid borders identify a structurally supported joint-context fixture. Dashed borders identify an untested pairing. Both are synthetic here; no biological stack is established.</p><div id="groups" class="cards"></div></section>
<section><h2>Checkpointed research queue</h2><div id="queue"></div></section>
<footer>Read-only local display. A source-check decision is a reviewer judgment, not proof of transferability in a new organism. Qualified scientific and biosafety review is required before any laboratory use. No sequences or laboratory procedures are generated.</footer>
</main><script id="study-data" type="application/json">__STUDY_DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('study-data').textContent), p=data.package;
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function append(host,tag,text,cls){const n=el(tag,text,cls);host.append(n);return n;}
function filtered(rows,query,scope,order){return rows.filter(r=>(!scope||r.record.endpoint.scope===scope)&&JSON.stringify(r.record).toLowerCase().includes(query.toLowerCase())).sort((a,b)=>String(order==='scope'?a.record.endpoint.scope:order==='review'?a.review_status:a.record.trait).localeCompare(String(order==='scope'?b.record.endpoint.scope:order==='review'?b.review_status:b.record.trait)));}
function show(){const host=document.getElementById('cards');host.replaceChildren();const rows=filtered(p.observations,document.getElementById('search').value,document.getElementById('scope').value,document.getElementById('order').value);document.getElementById('count').textContent=rows.length+' synthetic records shown';
for(const r of rows){const o=r.record,c=append(host,'article');append(c,'span','SYNTHETIC','badge synthetic');append(c,'span',r.review_status,'badge');append(c,'h3',o.trait);append(c,'p',o.category_assignments.map(a=>a.category+' · '+a.scheme).join(', '),'muted');
const flow=append(c,'div',undefined,'flow');[['Donor',o.donor.name],['Component',o.components.map(x=>x.name).join(', ')],['Recipient',o.recipient.name],['Endpoint',o.endpoint.name]].forEach(([role,value],i)=>{if(i)append(flow,'span','→','arrow');const n=append(flow,'div',undefined,'node');append(n,'small',role);append(n,'span',value);});
append(c,'p','Assay scope: '+o.endpoint.scope.replaceAll('_',' '));append(c,'p',o.endpoint.value===null?'Numeric result: unknown / not supplied':'Numeric result: '+o.endpoint.value+' '+o.endpoint.units);append(c,'p',o.endpoint.interpretation_limit,'notice');
const d=append(c,'details');append(d,'summary','Sources, dependencies and uncertainty');for(const citation of o.citations){const s=p.sources.find(x=>x.id===citation.source_id);append(d,'p',s.record.title+' · '+citation.locator);if(s.record.role!=='synthetic_fixture'){const a=append(d,'a','Open primary source');a.href=s.record.url;a.rel='noopener noreferrer';a.target='_blank';}}
append(d,'p','Dependencies: '+o.dependencies.map(x=>x.name+' — '+x.status).join('; '));append(d,'p','Uncertainty: '+o.uncertainty.join('; '));append(d,'p','Negative results: '+(o.negative_results===null?'not recorded; not evidence of absence':o.negative_results.join('; ')));append(d,'p','Transfer method: '+(o.transfer_method??'unknown')+' · Stability: '+(o.stability??'unknown'));append(d,'pre',JSON.stringify(r,null,2));}}
for(const [value,label] of [[p.observations.length,'synthetic records'],[p.observations.filter(r=>r.record.provenance.origin!=='synthetic_fixture').length,'real cases imported'],[p.model_calls,'Muse calls'],[data.trails.length,'planned real trails']]){const n=append(document.getElementById('stats'),'div',undefined,'stat');append(n,'b',value);append(n,'span',label);}
for(const t of data.trails){const n=append(document.getElementById('trails'),'div',undefined,'row');append(n,'b',t.workbook_id+' · '+t.topic);append(n,'span',' — '+t.review_question);append(n,'div','Awaiting workbook and exact study sources','muted');}
for(const g of p.groups){const n=append(document.getElementById('groups'),'article',undefined,g.record.kind==='proposed_pairing'?'dashed':'');append(n,'span','SYNTHETIC','badge synthetic');append(n,'h3',g.record.name);append(n,'p',g.record.kind.replaceAll('_',' '));append(n,'p',g.record.uncertainty.join('; '));}
for(const q of p.queue){const n=append(document.getElementById('queue'),'div',undefined,'row');append(n,'b',q.state.replaceAll('_',' '));append(n,'span',' · '+q.kind+' · attempts '+q.attempts);}
for(const id of ['search','scope','order'])document.getElementById(id).addEventListener('input',show);
document.getElementById('reset').addEventListener('click',()=>{document.getElementById('search').value='';document.getElementById('scope').value='';document.getElementById('order').value='trait';show();});show();
</script></body></html>'''
