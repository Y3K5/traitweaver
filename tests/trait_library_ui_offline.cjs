'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),cp=require('node:child_process');
const snapshot={evidence:JSON.parse(fs.readFileSync('data/algae-public.v1.json')),trait_library:JSON.parse(cp.execFileSync('python3',['-B','-c','from traitweaver.trait_library import Session; import json; print(json.dumps(Session().view()))'],{env:{...process.env,PYTHONPATH:'src'}}))};
const location={hash:'#trait-library'},escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let calls=0;const context=vm.createContext({snapshot,location,URL,esc:escape,label:v=>String(v??'Unknown').replaceAll('_',' '),list:a=>'<ul>'+a.map(x=>'<li>'+escape(x)+'</li>').join('')+'</ul>',pretty:v=>JSON.stringify(v,null,2),detail:()=>'',fetch:()=>{calls++;throw Error('No network');},api:()=>{calls++;throw Error('No mutation');}});
const run=s=>vm.runInContext(s,context);for(const file of ['trait-categories-ui.js','trait-library-ui.js'])run(fs.readFileSync('src/traitweaver/web/'+file,'utf8'));
const before=JSON.stringify(snapshot);let checks=0;const check=(value,message)=>{assert.ok(value,message);checks++;};
check(run('traitLibraryView()').includes('Six')||run('traitLibraryView()').includes('SIX'),'library index');
for(const t of snapshot.trait_library.catalog.traits){
 location.hash='#trait-categories/'+t.category;check(run('traitCategoryView()').includes('#trait-library/'+t.id),'category links to '+t.id);
 for(const r of snapshot.trait_library.catalog.recipients){
  location.hash='#trait-library/'+t.id+'/'+r.id;const html=run('traitLibraryView()');
  check(html.includes(t.name)&&html.includes(r.organism),'native/recipient '+t.id+'/'+r.id);
  check(html.includes('Documented observation')&&html.includes('Evidence-backed inference')&&html.includes('Untested transfer idea'),'three evidence roles');
  check(html.includes('Human scientific review pending')&&html.includes('Sufficiency: <b>unknown'),'no transfer promotion');
  check(t.claims.every(c=>html.includes(c.id)),'claim IDs inspectable');
 }
}
for(const h of ['#trait-library/missing','#trait-library/psr1-uptake/missing','#trait-library/psr1-uptake/alga/extra']){location.hash=h;check(run('traitLibraryView()').includes('unavailable'),'bad route fails closed');}
check(JSON.stringify(snapshot)===before,'browsing preserves all source and review records');check(calls===0,'browsing has no side effects');
location.hash='#trait-library/gfp-reporting';snapshot.trait_library.catalog.traits.at(-1).claims[0].text='<img src=x onerror=alert(1)>';
check(!run('traitLibraryView()').includes('<img src=x'),'claim content escaped');
snapshot.trait_library=null;check(run('traitLibraryView()').includes('Library unavailable'),'missing catalog fails closed');
run(fs.readFileSync('src/traitweaver/web/research-homes-ui.js','utf8'));
for(const id of ['PSR1_2023','PSR1_2023" data-injected="yes',"quote' & <b>text</b> /?#"]){
 const html=run('rhSources('+JSON.stringify([id])+')');
 const expected=`<a class="rh-source-link" href="${escape('#trait-library/sources/'+encodeURIComponent(id))}">${escape(id)} ↗</a>`;
 check(html===expected,'source IDs are URL-encoded and attribute/text escaped');
 check((html.match(/<a /g)||[]).length===1&&(html.match(/<\/a>/g)||[]).length===1,'one source link only');
 check(!html.includes('" data-injected=')&&!html.includes('<b>'),'source ID cannot create attributes or markup');
}
console.log(JSON.stringify({status:'passed',checks}));
