'use strict';
// Authored browsing taxonomy. Read-only projection; no scientific owner or dispatch.
const traitCategoryViews=[['trait-categories','Trait Categories']];
let taFilter='all',taSearch='';
const taCategories=[
 {id:'nutrient-capture',name:'Nutrient capture',verb:'Take in',description:'How nutrients move between water and living systems.',color:'mint',number:'01'},
 {id:'growth',name:'Growth & persistence',verb:'Grow',description:'How growth changes with a defined source context.',color:'sage',number:'02'},
 {id:'resource-recovery',name:'Resource recovery',verb:'Recover',description:'The open questions between capture and a useful material.',color:'ochre',number:'03'},
 {id:'materials',name:'Materials & pigments',verb:'Make',description:'A future lens on the materials living systems could produce.',color:'rose',number:'04'},
 {id:'environmental-response',name:'Environmental response',verb:'Respond',description:'Future questions about capture, exposure and residual hazards.',color:'blue',number:'05'},
 {id:'living-partnerships',name:'Living partnerships',verb:'Connect',description:'Future questions at the meeting of organisms and materials.',color:'lilac',number:'06'}
];
const taTraits=[
 {id:'phosphate-uptake',category:'nutrient-capture',name:'Phosphate uptake',role:'documented',summary:'Phosphate entering algae under reported culture conditions.',definition:'Uptake describes phosphate entering cells. Here, the admitted record is a rate reported for specific algal lines and source conditions.',metric:'phosphate_uptake',records:['E_PHOSPHATE_UPTAKE_UVM4','E_PHOSPHATE_UPTAKE_8_27','E_PHOSPHATE_UPTAKE_8_42','E_PHOSPHATE_UPTAKE_8_2'],boundary:'Uptake is not recovery. These observations do not measure phosphorus in a collected product or its usefulness to plants.',question:'What phosphorus-containing material could be collected, and how would its phosphorus be measured separately?',context:'Water → algal cells',related:['growth','phosphorus-recovery']},
 {id:'medium-removal',category:'nutrient-capture',name:'Medium phosphate removal',role:'documented',summary:'A source-specific observation about phosphate leaving the medium.',definition:'Medium removal describes a change in the surrounding medium. Its destination and later recoverability require separate evidence.',metric:'medium_phosphate_removal',records:['E_OVERPLUS_REMOVAL'],boundary:'The admitted observation is qualitative. No numeric removal values are available here; medium removal is not harvested-product recovery.',question:'Which compartments account for the removed phosphorus, and which can be collected?',context:'Surrounding medium → destination to resolve',related:['phosphate-uptake','phosphorus-recovery']},
 {id:'growth',category:'growth',name:'Algal growth',role:'documented',summary:'Growth observations, kept beside uptake rather than treated as the same outcome.',definition:'Growth describes change in cells or biomass. The admitted summaries retain their own units and controls; they do not establish a growth acceptance threshold.',metric:'growth',records:['E_GROWTH_UVM4','E_GROWTH_8_27','E_GROWTH_8_42','E_GROWTH_8_2','E_OVERPLUS_GROWTH'],boundary:'Growth and phosphorus accumulation are separate outcomes. These sources do not establish equivalence, a cross-study winner or performance in a new environment.',question:'What growth constraint and uncertainty would matter for a proposed recovery study?',context:'Source culture → growth observation',related:['phosphate-uptake','phosphorus-recovery']},
 {id:'phosphorus-recovery',category:'resource-recovery',name:'Phosphorus recovery',role:'goal',summary:'An open goal: measure phosphorus in material actually collected.',definition:'The desired outcome is phosphorus in a defined collected material. Uptake into cells alone does not establish this outcome.',records:[],boundary:'No recovered-product phosphorus result is admitted. No extraction method, yield or useful product is established.',question:'What is collected, what phosphorus does it contain, and what is the material balance?',context:'Algae → collected material? → characterized phosphorus?',related:['phosphate-uptake','plant-use']},
 {id:'plant-use',category:'resource-recovery',name:'Usefulness to plants',role:'goal',summary:'A separate open question after collection and characterization.',definition:'A collected phosphorus-containing material would need separate evidence of availability and benefit in a defined intended-use context.',records:[],boundary:'No plant-use result is admitted. Collection does not establish fertilizer performance, safety or field benefit.',question:'What evidence would distinguish phosphorus content from availability and benefit?',context:'Characterized material? → intended use?',related:['phosphorus-recovery']},
 {id:'pigment-production',category:'materials',name:'Pigment production',role:'future',summary:'A proposed place for future source-linked color and material traits.',definition:'A future record could connect a documented pigment trait to an organism, measured material and source conditions.',records:[],boundary:'No pigment trait records, organisms, yields or methods are admitted to this view. The colors here organize categories; they are not pigment measurements.',question:'Which public records would establish pigment identity, organism context and measurement conditions?',context:'Organism? → material? → documented properties?',related:[]},
 {id:'metal-capture',category:'environmental-response',name:'Metal capture',role:'future',summary:'A future question about partitioning and retained contaminants.',definition:'A future evidence review could distinguish metal capture from transformation, residual contamination and safe material handling.',records:[],boundary:'No metal-capture records or treatment performance are admitted. Capture or movement does not make metals or radioactivity disappear.',question:'Where does the contaminant end up, and which residual hazards remain?',context:'Contaminated material? → retained fraction? → residual hazards?',related:[]},
 {id:'biomass-processing',category:'living-partnerships',name:'Biomass processing',role:'future',summary:'A future question about fungi and the fate of contaminated biomass.',definition:'A future review could ask how an additional organism affects a defined biomass stream and the fate of contaminants.',records:[],boundary:'No fungal processing result, qualified organism pairing or contaminant fate is admitted. Breakdown of biomass does not establish destruction of contaminants.',question:'Which organisms, material boundaries and residual measurements would make this question testable?',context:'Biomass? → organism interaction? → residual material?',related:[]}
];
const taCategory=id=>taCategories.find(c=>c.id===id);
const taTrait=id=>taTraits.find(t=>t.id===id);
function taRoute(){
 const parts=location.hash.slice(1).split('/');
 if(parts.length===1)return {level:'categories'};
 const category=taCategory(parts[1]);
 if(category&&parts.length===2)return {level:'category',category};
 const trait=taTrait(parts[2]);
 if(category&&trait?.category===category.id&&parts.length===3)return {level:'trait',category,trait};
 return {level:'missing'};
}
function taRecords(trait){
 return trait.records.flatMap(id=>{
  const r=snapshot.evidence?.evidence?.find(x=>x.id===id);
  const expectedSource=id.startsWith('E_OVERPLUS_')?'S_OVERPLUS_2024':'S_PSR1_2023';
  const s=snapshot.evidence?.sources?.find(x=>x.id===r?.source_id);
  if(!r||r.role!=='published_observation'||r.endpoint!==trait.metric||r.metric!==trait.metric||r.source_id!==expectedSource||r.organism!=='Chlamydomonas reinhardtii'||!s?.title||!taSourceUrl(s.url))return [];
  return [{record:r,source:s}];
 });
}
function taSourceUrl(value){try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password?url.href:null;}catch{return null;}}
function taStatus(trait){return trait.role==='documented'?(taRecords(trait).length?'Published observations':'Records unavailable'):trait.role==='goal'?'Open goal':'Future question';}
const taHref=trait=>'#trait-categories/'+trait.category+'/'+trait.id;
function taArt(category){
 // Original abstract contour marks. Decorative: no quantities, geometry or biology encoded.
 const seed=Number(category.number),paths=Array.from({length:13},(_,i)=>{
  const radius=25+i*5.8;
  const points=Array.from({length:101},(_,j)=>{
   const a=j/100*Math.PI*2,r=radius*(1+.12*Math.sin(a*3+seed)+.06*Math.cos(a*5+seed/2));
   return `${j?'L':'M'}${(150+Math.cos(a)*r).toFixed(2)},${(116+Math.sin(a)*r*.81).toFixed(2)}`;
  }).join(' ');
  return `<path d="${points} Z"/>`;
 }).join('');
 return `<svg class="ta-art" viewBox="0 0 300 235" aria-hidden="true" focusable="false"><g>${paths}</g><circle cx="150" cy="116" r="3"/></svg>`;
}
function taLegend(){return '<div class="ta-legend" aria-label="Record roles"><span><i class="ta-dot"></i>Published observations</span><span><i class="ta-dot ta-dot-open"></i>Open goal</span><span><i class="ta-dot ta-dot-future"></i>Future question</span><small>Color identifies a category, not confidence.</small></div>';}
function taChrome(content){return `<div class="trait-atlas"><div class="ta-masthead"><a href="#trait-categories" class="ta-wordmark">TRAITWEAVER <span>/ FIELD NOTES</span></a><a href="#journey">Phosphorus showcase <span aria-hidden="true"><span class="ta-link-arrow" aria-hidden="true"></span></span></a></div>${content}<footer class="ta-footer"><span>TRAITS FIRST. ORGANISMS IN CONTEXT.</span><p>A curated beginning, not a validated atlas of life. Abstract category art is illustrative. Explore the source-backed library for native systems and unresolved receiving contexts.</p><a href="#intelligence">Explore the existing Muse evidence map <span class="ta-link-arrow" aria-hidden="true"></span></a></footer></div>`;}
function taCategoriesView(){
 return taChrome(`<header class="ta-intro"><div><span class="ta-eyebrow">AN INDEX OF CAPABILITIES / 01</span><h1>Trait Categories<span>What can life do?</span></h1></div><p>Begin with a capability.<br>Follow it to the evidence, the organism<br class="ta-desktop-break"> and the questions still open.</p></header>${typeof tlCategoryPanel==='function'?'<p class="ta-annotation"><a href="#trait-library">New: six source-backed native systems and recipient comparisons →</a></p>':''}${taLegend()}<form id="ta-filter-form" class="ta-filters" role="search"><div><button type="button" data-ta-filter="all" aria-pressed="${taFilter==='all'}">All categories</button><button type="button" data-ta-filter="published" aria-pressed="${taFilter==='published'}">With published records</button></div><label for="ta-search">Find a capability<input id="ta-search" type="search" maxlength="100" value="${esc(taSearch)}" placeholder="Try uptake, growth, recovery…"></label><button class="ta-search-button" type="submit">Search →</button></form><div id="ta-results">${taCategoryResults()}</div><aside class="ta-field-note"><span>START HERE</span><div><h2>From uptake to recovery.<br>A distinction worth keeping.</h2><p>The first documented examples come from algae and phosphorus. Uptake is observed; recovery into a useful material remains an open goal.</p><a href="#trait-categories/nutrient-capture/phosphate-uptake">Explore phosphate uptake <span aria-hidden="true"><span class="ta-link-arrow" aria-hidden="true"></span></span></a></div><div class="ta-note-index" aria-hidden="true">P<span>PHOSPHORUS</span></div></aside>`);
}
function taCategoryResults(){
 const query=taSearch.trim().toLowerCase();
 const categories=taCategories.filter(c=>{
  const traits=taTraits.filter(t=>t.category===c.id);
  return (taFilter!=='published'||traits.some(t=>taRecords(t).length))&&(!query||[c.name,c.verb,c.description,...traits.flatMap(t=>[t.name,t.summary])].join(' ').toLowerCase().includes(query));
 });
 return `<p class="ta-result-count" role="status" aria-live="polite">${categories.length} ${categories.length===1?'category':'categories'} · authored browsing taxonomy</p><div class="ta-category-grid">${categories.map(c=>{
  const traits=taTraits.filter(t=>t.category===c.id),documented=traits.filter(t=>taRecords(t).length).length;
  const status=documented?`${documented} ${documented===1?'trait':'traits'} with published observations`:traits.some(t=>t.role==='documented')?'Source records unavailable':traits.some(t=>t.role==='goal')?'Open goals · evidence needed':'Proposed category · no records';
  return `<a class="ta-category ta-${c.color}" href="#trait-categories/${c.id}"><div class="ta-swatch"><span class="ta-index">${c.number} / ${c.verb}</span>${taArt(c)}<span class="ta-arrow" aria-hidden="true"><span class="ta-link-arrow" aria-hidden="true"></span></span></div><div class="ta-category-caption"><h2>${c.name}</h2><p>${c.description}</p><span class="ta-card-status">${status}</span></div></a>`;
 }).join('')}</div>${categories.length?'':'<div class="ta-empty"><h2>No matching categories.</h2><p>Try a broader capability or clear the filters.</p><button type="button" id="ta-clear">Clear filters</button></div>'}`;
}
function taBreadcrumb(category,trait){return `<nav class="ta-breadcrumb" aria-label="Trait category path"><a href="#trait-categories">Trait Categories</a><span aria-hidden="true">/</span>${trait?`<a href="#trait-categories/${category.id}">${category.name}</a><span aria-hidden="true">/</span><span aria-current="page">${trait.name}</span>`:`<span aria-current="page">${category.name}</span>`}</nav>`;}
function taCategoryView(category){
 const traits=taTraits.filter(t=>t.category===category.id);
 return taChrome(`${taBreadcrumb(category)}<header class="ta-family-header ta-${category.color}"><div><span class="ta-eyebrow">CATEGORY ${category.number} / ${category.verb}</span><h1>${category.name}</h1><p>${category.description}</p></div>${taArt(category)}</header>${taLegend()}<p class="ta-result-count">${traits.length} ${traits.length===1?'trait card':'trait cards'} · inspect the role on each card</p><div class="ta-trait-grid">${traits.map((t,i)=>`<a class="ta-trait-card ta-${category.color}" href="${taHref(t)}"><span class="ta-card-status">${taStatus(t)}</span><span class="ta-trait-number">${category.number}.${i+1}</span><h2>${t.name}</h2><p>${t.summary}</p><span class="ta-trait-link">${taRecords(t).length?'View evidence & conditions':'Explore the open question'} <span class="ta-link-arrow" aria-hidden="true"></span></span></a>`).join('')}</div>${typeof tlCategoryPanel==='function'?tlCategoryPanel(category.id):''}<p class="ta-annotation">These are browsing labels. A source-linked trait is not a validated transfer capability or an approved intervention.</p>`);
}
const taValue=value=>value===null||value===undefined?'Unknown':esc(value);
function taEvidence(trait){
 const entries=taRecords(trait);
 if(!entries.length)return `<section class="ta-detail-section"><span class="ta-eyebrow">EVIDENCE STATUS</span><h2>${trait.role==='documented'?'Source records unavailable':'Evidence still to be established'}</h2><p>${trait.role==='documented'?'The required record and source bindings are missing or inconsistent. Observations are withheld.':'No documented examples are admitted for this card. It is an authored question, not an observed capability in this application.'}</p></section>`;
 const sources=[...new Map(entries.map(e=>[e.source.id,e.source])).values()];
 return `<section class="ta-detail-section"><span class="ta-eyebrow">DOCUMENTED EXAMPLES / EXISTING PUBLIC RECORDS</span><h2>Algae, in their source context.</h2><p><a class="ta-organism-link" href="#research-story"><i>Chlamydomonas reinhardtii</i></a> · observations retain the lines and conditions reported in each study.</p>${entries.length<trait.records.length?'<p class="ta-annotation">Some expected records are unavailable. Only resolved record and source pairs are shown.</p>':''}${sources.map(source=>{
  const rows=entries.filter(e=>e.source.id===source.id).map(e=>e.record),quant=rows.filter(r=>r.value_state==='reported_mean'),qual=rows.filter(r=>r.value_state==='qualitative');
  return `<article class="ta-source-block"><div class="ta-source-heading"><h3>${esc(source.authors)} · ${esc(source.year)}</h3><a href="${esc(taSourceUrl(source.url))}" target="_blank" rel="noopener noreferrer">Read source <span class="ta-link-arrow" aria-hidden="true"></span></a></div><p class="ta-source-title">${esc(source.title)}</p>${quant.length?`<div class="table-wrap"><table class="ta-table"><caption>Published summaries · mean ± SE · ${esc(quant[0].unit)} · source control UVM4</caption><thead><tr><th scope="col">Source line</th><th scope="col">Mean ± SE</th><th scope="col">n / independent unit</th></tr></thead><tbody>${quant.map(r=>`<tr><th scope="row">${esc(r.subject)}${r.subject==='UVM4'?' <small>control</small>':''}</th><td>${taValue(r.value)} ± ${taValue(r.uncertainty?.value)} ${esc(r.uncertainty?.kind||'uncertainty unknown')}</td><td>${taValue(r.uncertainty?.n)} / ${esc(r.uncertainty?.independent_unit||'Unknown')}</td></tr>`).join('')}</tbody></table></div><p class="ta-record-basis">${esc(quant[0].measurement_basis)}</p>`:''}${qual.map(r=>`<p class="ta-card-status">Qualitative observation · numeric value not admitted</p><blockquote>${esc(r.statement)}</blockquote><p>${esc(r.measurement_basis)}</p><p class="ta-record-basis">Source strains: ${esc((r.subjects||[]).join(', '))}</p>`).join('')}<details><summary>Conditions, record IDs & limitations</summary>${rows.map(r=>`<div class="ta-exact-record"><strong>${esc(r.id)}</strong><p>${esc(r.background||r.organism)}</p><p>${esc(r.locator)}</p><p>${esc(r.claim_limit)}</p></div>`).join('')}<p>${esc(source.admission)}</p></details><p class="ta-source-id">${esc(source.id)} · ${esc(source.license)} · existing admitted source</p></article>`;
 }).join('')}</section>`;
}
function taTraitView(category,trait){
 const documented=taRecords(trait).length>0;
 return taChrome(`${taBreadcrumb(category,trait)}<header class="ta-detail-header ta-${category.color}"><div><span class="ta-card-status">${taStatus(trait)}</span><h1>${trait.name}</h1><p>${trait.summary}</p></div><div class="ta-detail-art">${taArt(category)}<small>Abstract illustration</small></div></header><div class="ta-detail-grid"><div><section class="ta-detail-section"><span class="ta-eyebrow">THE CAPABILITY</span><h2>What does it describe?</h2><p>${trait.definition}</p><div class="ta-context"><span>CONTEXT TO KEEP IN VIEW</span><p>${trait.context}</p><small>Conceptual relationship · no simulation or measured flow</small></div></section>${taEvidence(trait)}</div><aside class="ta-detail-aside"><span class="ta-eyebrow">CLAIM BOUNDARY</span><h2>What remains open?</h2><p>${trait.boundary}</p><hr><span class="ta-eyebrow">A QUESTION TO CARRY FORWARD</span><p>${trait.question}</p>${documented?'<a class="ta-action" href="#research-story">Open the linked evidence workspace <span class="ta-link-arrow" aria-hidden="true"></span></a><a class="ta-action ta-secondary-action" href="#journey">See evidence → Muse → local audit <span class="ta-link-arrow" aria-hidden="true"></span></a>':trait.role==='goal'?'<a class="ta-action" href="#journey">Return to the phosphorus study <span class="ta-link-arrow" aria-hidden="true"></span></a>':'<p class="ta-annotation">Future collection: sources and organism examples must be reviewed before adding evidence.</p>'}<p class="ta-annotation">This is an authored guide. It is not new Muse output. The default showcase uses a synthetic Muse replay.</p></aside></div>${trait.related.length?`<section class="ta-related"><span class="ta-eyebrow">KEEP DISTINCT, EXPLORE TOGETHER</span><div>${trait.related.map(id=>{const t=taTrait(id);return `<a href="${taHref(t)}"><span>${t.name}</span><small>${taStatus(t)}</small><b aria-hidden="true"><span class="ta-link-arrow" aria-hidden="true"></span></b></a>`;}).join('')}</div></section>`:''}<p class="ta-annotation">Organisms are linked examples within a trait. No measured cross-organism transfer is established here.</p>`);
}
function traitCategoryView(){
 const route=taRoute();
 if(route.level==='categories')return taCategoriesView();
 if(route.level==='category')return taCategoryView(route.category);
 if(route.level==='trait')return taTraitView(route.category,route.trait);
 return taChrome('<section class="ta-empty"><h1>That trait page is unavailable.</h1><p>The category or trait is not in this curated index.</p><a href="#trait-categories">Return to Trait Categories →</a></section>');
}
function traitCategoryLayout(active){document.body.classList.toggle('trait-atlas-mode',active);}
function bindTraitCategory(){
 const update=()=>{const host=document.getElementById('ta-results');if(host)host.innerHTML=taCategoryResults();document.getElementById('ta-clear')?.addEventListener('click',()=>{taFilter='all';taSearch='';render();document.getElementById('ta-search')?.focus();});};
 document.querySelectorAll('[data-ta-filter]').forEach(button=>button.addEventListener('click',()=>{taFilter=button.dataset.taFilter;document.querySelectorAll('[data-ta-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.taFilter===taFilter)));update();}));
 document.getElementById('ta-search')?.addEventListener('input',event=>{taSearch=event.target.value.slice(0,100);update();});
 document.getElementById('ta-filter-form')?.addEventListener('submit',event=>{event.preventDefault();taSearch=document.getElementById('ta-search').value.slice(0,100);update();});
 update();
}
