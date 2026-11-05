'use strict';
const traitLibraryViews = [['trait-library', 'Source-backed trait library']];
let tlPrepared = null;
const tlOwner = () => snapshot.trait_library;
const tlRole = role => ({documented_observation:'Documented observation', evidence_backed_inference:'Evidence-backed inference', untested_transfer_idea:'Untested transfer idea'}[role] || label(role));
const tlLink = t => '#trait-library/' + t.id;
function tlCategoryPanel(category) {
 const traits = tlOwner()?.catalog.traits.filter(t => !category || t.category === category) || [];
 if (!traits.length) return '';
 return `<section class="tl-section"><span class="ta-eyebrow">SOURCE-BACKED LIBRARY / HUMAN REVIEW PENDING</span><h2>Native systems, in context.</h2><p>Explore components and dependencies. A documented native function does not establish transfer to another organism.</p><div class="ta-trait-grid">${traits.map(t=>`<a class="ta-trait-card" href="${tlLink(t)}"><span class="ta-card-status">${esc(label(t.system_level))}</span><h3>${esc(t.name)}</h3><p><i>${esc(t.organism)}</i></p><span>Inspect sources & compare a recipient →</span></a>`).join('')}</div></section>`;
}
function tlSelection() {
 const parts=location.hash.slice(1).split('/'), bundle=tlOwner()?.catalog;
 if (!bundle || parts.length>3) return null;
 const trait=bundle.traits.find(t=>t.id===parts[1]);
 const recipient=bundle.recipients.find(r=>r.id===(parts[2]||'alga'));
 return trait&&recipient?{trait,recipient,comparison:tlOwner().comparisons.find(c=>c.trait_id===trait.id&&c.recipient_id===recipient.id)}:null;
}
function tlSources(ids) {
 return ids.map(id=>{const s=tlOwner()?.catalog.sources.find(x=>x.id===id),url=s&&taSourceUrl(s.url);return s&&url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(id)} ↗</a>`:'Source unavailable';}).join(' · ');
}
function tlDossier(t,r) {
 const d=t.dossier,p=d.study_plan,owner=tlOwner();
 return `<section class="tl-section" id="tl-dossier"><span class="ta-eyebrow">RESEARCH DOSSIER / ${esc(t.id)}</span><h2>Conflicts, caveats and missing evidence</h2><p>${esc(d.evidence_map)}</p>${d.conflicts_and_caveats.map(x=>`<article class="tl-warning"><h3>${esc(label(x.status))}</h3><p>${esc(x.text)}</p><p>${tlSources(x.source_ids)}</p><small>${esc(label(x.review_status))}</small></article>`).join('')}<h3>Information still needed</h3>${list(d.missing_information)}</section>
 <section class="tl-section" id="tl-study-plan"><span class="ta-eyebrow">DRAFT STUDY PLAN / NOT LAB-READY</span><h2>${esc(p.question)}</h2><p>${esc(p.authorship)}</p><p>Potential recipient: <i>${esc(r.organism)}</i>; actual stock and conditions remain unspecified.</p><h3>Candidate methods for reviewer selection</h3>${p.candidate_methods.map(x=>`<article><p><b>${esc(x.method)}</b></p><small>${esc(x.basis)}</small><p>${tlSources(x.source_ids)}</p></article>`).join('')}
 <div class="tl-context-grid"><article><h3>Proposed controls</h3>${list(p.controls)}</article><article><h3>Measurements to distinguish</h3>${list(p.measurements)}</article></div><h3>Design decisions before data collection</h3>${list(p.design_review)}<h3>Safety review</h3><p>${esc(p.safety_review)}</p><p class="tl-warning">Qualified reviewer sign-off: <b>pending</b>. ${esc(p.execution)}. This app cannot independently verify reviewer qualifications and never labels these plans lab-ready.</p>
 ${owner.read_only?'':`<details><summary>Record scoped human sign-off</summary><p>Record the reviewer’s own attestation and exact scope. This remains a planning record, not laboratory authorization. Prior sign-offs remain visible in history.</p><form id="tl-signoff"><div class="tl-context-grid"><label>Reviewer identifier<input name="reviewer" required maxlength="120"></label><label>Relevant qualification or role<input name="qualification" required maxlength="2000"></label></div><label>Specific organism and stock reviewed<input name="organism_stock" required maxlength="2000"></label><label>Specific methods and conditions reviewed<textarea name="methods_conditions" required maxlength="2000"></textarea></label><label>Review decision<select name="decision"><option value="changes_required">Changes required</option><option value="reviewed_for_further_planning">Reviewed for further planning</option></select></label><label>Reason and remaining limits<textarea name="reason" required maxlength="2000"></textarea></label><label class="tl-check"><input type="checkbox" name="attestation" required>The named qualified reviewer has verified this stated scope. This record does not authorize laboratory execution.</label><button class="button" type="submit">Save scoped sign-off record</button></form></details>`}</section>
 <section class="tl-section"><span class="ta-eyebrow">FUTURE TOOL INTEGRATION</span><h2>CRISPR research review</h2><p>${esc(d.crispr_future.purpose)}</p><div class="tl-context-grid"><article><h3>Required inputs</h3>${list(d.crispr_future.required_inputs)}</article><article><h3>Required records</h3>${list(d.crispr_future.required_outputs)}</article></div><p class="tl-warning"><b>Future, not connected.</b> ${esc(d.crispr_future.limit)}</p></section>`;
}
function tlHistory() {
 const owner=tlOwner();
 return `<section class="tl-section"><span class="ta-eyebrow">INSPECTABLE RECORD</span><h2>Sources → suggestions → checks → human decisions</h2><p>${owner.history.length} saved events · ${esc(label(owner.storage))}. ${owner.read_only?'Imported history is read-only.':'Earlier events are preserved.'} New Muse calls in this library: <b>0</b>.</p>${owner.history.length?owner.history.map(r=>{
  const e=r.event;
  return `<details class="tl-history"><summary>Revision ${r.revision} · ${esc(label(e.type))} · ${esc(e.trait_id)} → ${esc(e.recipient_id)}</summary><p>${esc(e.provenance||'Local human/software record')} · ${esc(r.saved_utc)}</p>${e.output?e.output.suggestions.map(s=>`<h3>Suggested review, not an action</h3><p>${esc(s.gap)}</p><p>${esc(s.proposed_check)}</p><p>Cites ${esc(s.claim_ids.join(', '))}. Validation checks shape and identifiers only.</p>`).join(''):''}${e.type==='review'?`<p><b>${esc(e.reviewer)}</b>: ${esc(label(e.decision))}</p><p>${esc(e.reason)}</p><p>This decision does not approve execution or establish transfer.</p>`:''}${e.type==='source_check'?'<p>Source IDs resolve in the pinned catalog. Scientific entailment and recipient compatibility were not tested.</p>':''}${e.type==='rejected_import'?'<p>Import rejected. Input hash retained; no scientific claim changed.</p>':''}<pre>${esc(pretty(r))}</pre></details>`;
 }).join(''):'<p>No model output, local check or reviewer decision is saved yet.</p>'}
 <p>${esc(owner.privacy.limit)}</p>${owner.privacy.findings.length?`<p class="tl-warning">Export blocked: ${owner.privacy.findings.map(f=>`revision ${f.revision}, ${esc(f.category)}`).join('; ')}. Nothing was removed.</p>`:''}
 <label class="tl-check"><input id="tl-export-reviewed" type="checkbox"> I reviewed all saved events above for private content before local export.</label>
 <div class="actions"><button type="button" id="tl-export" class="button">Export complete local review</button>${owner.read_only?'<button type="button" id="tl-return" class="button">Return to local history</button>':''}</div>
 <label for="tl-open">Reopen a library review, read-only</label><input id="tl-open" type="file" accept=".json,application/json"><p>Imports never run checks or call Muse. The existing local history is retained separately.</p></section>`;
}
function traitLibraryView() {
 if(typeof researchHomeRoute==='function' && researchHomeRoute())return researchHomeView();
 const owner=tlOwner();
 if (!owner) return taChrome(`<section class="ta-empty"><h1>Library unavailable</h1><p>${esc(snapshot.trait_library_error||'Source validation failed.')}</p></section>`);
 if (location.hash==='#trait-library') return taChrome(`<header class="ta-intro"><div><span class="ta-eyebrow">SIX CURATED SYSTEMS / FIRST LOCAL SLICE</span><h1>Source-backed traits<span>Start with what was observed.</span></h1></div><p>Native biology, dependencies and receiving-context questions. Scientific review pending.</p></header>${tlCategoryPanel()}${tlHistory()}`);
 const selected=tlSelection();
 if (!selected) return taChrome('<section class="ta-empty"><h1>Trait or recipient unavailable</h1><a href="#trait-library">Return to the library</a></section>');
 const {trait:t,recipient:r,comparison:c}=selected;
 const sourceIds=[...new Set([...t.claims,...t.components,...t.dependencies,...t.dossier.conflicts_and_caveats,t.dossier.study_plan].flatMap(row=>row.source_ids))];
 return taChrome(`<nav class="ta-breadcrumb" aria-label="Library path"><a href="#trait-categories">Trait Categories</a><span>/</span><a href="#trait-categories/${esc(t.category)}">${esc(taCategory(t.category)?.name||t.category)}</a><span>/</span><span aria-current="page">${esc(t.name)}</span></nav>
 <header class="tl-header"><span class="ta-eyebrow">${esc(label(t.system_level))} / CURATED NATIVE EVIDENCE</span><h1>${esc(t.name)}</h1><p>${esc(t.endpoint)}</p><div class="tl-warning"><b>Human scientific review pending.</b> ${esc(owner.limit)}</div></header>
 <section class="tl-section"><h2>The native system</h2><h3><i>${esc(t.organism)}</i></h3><p>${esc(t.context)}</p>${[...new Set(t.claims.map(x=>x.role))].map(role=>`<div class="tl-claim-group tl-${role}"><h3>${tlRole(role)}</h3>${t.claims.filter(x=>x.role===role).map(x=>`<article><p>${esc(x.text)}</p><small>${esc(x.id)} · ${esc(x.locator)}</small><p>${tlSources(x.source_ids)}</p></article>`).join('')}</div>`).join('')}</section>
 <section class="tl-section"><h2>Genes, proteins and their limits</h2><div class="table-wrap"><table><caption>Native associations; exact sequence/reference mappings remain unqualified in this library.</caption><thead><tr><th>Gene → protein</th><th>Supported role</th><th>Identity and evidence</th></tr></thead><tbody>${t.components.map(x=>`<tr><th>${esc(x.gene||'Gene unresolved')}<br><span>${esc(x.protein||'Protein unresolved')}</span></th><td>${esc(x.function)}</td><td>${esc(x.basis)}<br>Accession: ${esc(x.reference_accession||'Not qualified')}<br>${tlSources(x.source_ids)}</td></tr>`).join('')}</tbody></table></div></section>
 <section class="tl-section"><span class="ta-eyebrow">NATIVE SYSTEM → RECEIVING CONTEXT</span><h2>What would need investigation?</h2><label for="tl-recipient">Potential receiving organism</label><select id="tl-recipient">${owner.catalog.recipients.map(x=>`<option value="${esc(x.id)}" ${x.id===r.id?'selected':''}>${esc(x.organism)} · strain not selected</option>`).join('')}</select>
 <div class="tl-context-grid"><article><h3>Native evidence</h3><p><i>${esc(t.organism)}</i></p><p>${esc(t.context)}</p></article><article><h3>Potential recipient</h3><p><i>${esc(r.organism)}</i></p><p>${esc(r.context)}</p><p>${esc(label(c.relationship))}</p></article></div><p class="tl-warning">${esc(c.recipient_evidence)} Transfer: <b>untested</b>. Sufficiency: <b>unknown</b>. These rows identify investigation needs, not a proposed cassette.</p>
 <div class="table-wrap"><table><caption>Component and dependency gap map</caption><thead><tr><th>Native component / dependency</th><th>Recipient evidence</th><th>Next review question</th></tr></thead><tbody>${c.rows.map(x=>`<tr><th>${esc(x.native)}<small>${esc(label(x.kind))}</small>${tlSources(x.source_ids)}</th><td>Unknown</td><td>${esc(x.question)}</td></tr>`).join('')}</tbody></table></div><h3>Open questions</h3>${list(t.open_questions)}<h3>Safety and intended use</h3><p>${esc(t.safety)}</p></section>
 ${tlDossier(t,r)}<section class="tl-section"><h2>Inspect the sources</h2><p>Access depth is explicit. Abstract review is not full-text qualification; this starter library is not exhaustive.</p>${sourceIds.map(id=>{const s=owner.catalog.sources.find(x=>x.id===id);return `<details class="tl-history"><summary>${esc(s.title)}</summary><p>${tlSources([id])}</p><p>${esc(label(s.access))} · accessed ${esc(s.accessed)}</p><p>${esc(s.locator)}</p><p>${esc(s.limit)}</p></details>`;}).join('')}</section>
 <section class="tl-section"><h2>Muse as a research partner</h2><p>Proposed model: <b>muse-spark-1.3</b>. Prepare only; no provider calls or credential access. Imported output remains unauthenticated. Synthetic replay is authored test content.</p><div class="actions"><button type="button" id="tl-prepare" class="button">Inspect unsent research request</button>${owner.read_only?'':'<button type="button" id="tl-synthetic" class="button">Try labeled synthetic replay</button><button type="button" id="tl-check" class="button">Check local source bindings</button>'}</div><div id="tl-prepared"></div>${owner.read_only?'':`<details><summary>Import a saved, typed Muse suggestion</summary><p>Requires the exact prepared request hash, model and output.suggestions. Checks validate identifiers and shape, not source entailment or provider authenticity.</p><label for="tl-reply">Saved response wrapper JSON</label><textarea id="tl-reply" maxlength="65536" rows="5"></textarea><button type="button" id="tl-import-reply" class="button">Validate and retain output</button></details>`}</section>
 ${owner.read_only?'':`<section class="tl-section"><h2>Record a human decision</h2><p>Review the original sources and model suggestions independently. Saving a decision does not approve experiments or change the source evidence.</p><form id="tl-review"><div class="tl-context-grid"><label>Reviewer name or local identifier<input name="reviewer" required maxlength="120"></label><label>Decision<select name="decision"><option value="needs_evidence">Needs more evidence</option><option value="investigate_further">Investigate further</option><option value="decline">Decline this direction</option></select></label></div><label>Reason<textarea name="reason" required maxlength="2000" rows="3"></textarea></label><fieldset><legend>Claims reviewed (select at least one)</legend>${t.claims.map(x=>`<label class="tl-check"><input type="checkbox" name="claim" value="${esc(x.id)}">${esc(x.id)} · ${tlRole(x.role)}</label>`).join('')}</fieldset><label class="tl-check"><input name="safety" type="checkbox" required>I considered the safety note; this decision does not authorize biological execution.</label><button class="button" type="submit">Save separate review decision</button></form></section>`}${tlHistory()}`);
}
function bindTraitLibrary() {
 if(typeof researchHomeRoute==='function' && researchHomeRoute()){bindResearchHome();return;}
 const owner=tlOwner(); if(!owner)return;
 tlPrepared=null;
 document.querySelectorAll('.demo-badge').forEach(e=>{e.textContent='Library · local review';});
 document.getElementById('revision-label').textContent='Library · '+owner.history.length+' events';
 document.getElementById('study-identity').textContent='TRAIT LIBRARY';
 show('Separate local research review. The phosphorus demo remains unchanged. No provider calls.');
 const selection=tlSelection();
 const body=extra=>({library_hash:tlOwner().hash,...extra});
 const action=type=>({type,trait_id:selection.trait.id,recipient_id:selection.recipient.id});
 const act=value=>perform('/api/trait-library/act',body({action:value}),'Library record saved locally. No provider or biological execution.');
 document.getElementById('tl-recipient')?.addEventListener('change',e=>{location.hash=tlLink(selection.trait)+'/'+e.target.value;});
 document.getElementById('tl-check')?.addEventListener('click',()=>act(action('source_check')));
 document.getElementById('tl-synthetic')?.addEventListener('click',()=>act(action('synthetic_suggestions')));
 document.getElementById('tl-import-reply')?.addEventListener('click',()=>act({...action('import_suggestions'),reply:document.getElementById('tl-reply').value}));
 document.getElementById('tl-prepare')?.addEventListener('click',async()=>{try{
  const route=location.hash, fingerprint=tlOwner().hash;
  const p=await api('/api/trait-library/prepare',body({trait_id:selection.trait.id,recipient_id:selection.recipient.id}));
  if(location.hash!==route||tlOwner().hash!==fingerprint)return;
  tlPrepared=p;document.getElementById('tl-prepared').innerHTML=`<p><b>Not sent.</b> One proposed request, maximum $0.10 application allowance, 8192 output tokens, no retries. Pricing and account readiness require verification. This contract has no live adapter.</p>${detail('Exact public-only request and destination',p)}<button type="button" id="tl-download-request" class="button">Download unsent packet</button>`;
  document.getElementById('tl-download-request').onclick=()=>download('trait-library-muse-request.json',pretty(p)+'\n','application/json');
 }catch(e){show(e.message,true);}});
 document.getElementById('tl-review')?.addEventListener('submit',event=>{event.preventDefault();const f=new FormData(event.target);act({...action('review'),comparison_sha256:selection.comparison.comparison_sha256,reviewer:f.get('reviewer'),decision:f.get('decision'),reason:f.get('reason'),claim_ids:f.getAll('claim'),safety_acknowledged:f.get('safety')==='on'});});
 document.getElementById('tl-signoff')?.addEventListener('submit',event=>{event.preventDefault();const f=new FormData(event.target);const plan=owner.study_plans.find(p=>p.trait_id===selection.trait.id&&p.recipient_id===selection.recipient.id);act({...action('plan_signoff'),comparison_sha256:selection.comparison.comparison_sha256,plan_sha256:plan.plan_sha256,reviewer:f.get('reviewer'),qualification:f.get('qualification'),organism_stock:f.get('organism_stock'),methods_conditions:f.get('methods_conditions'),decision:f.get('decision'),reason:f.get('reason'),reviewer_attestation:f.get('attestation')==='on'});});
 document.getElementById('tl-export')?.addEventListener('click',async()=>{try{
  if(!document.getElementById('tl-export-reviewed').checked)throw Error('Review the entire saved history and acknowledge before local export.');
  const hash=tlOwner().hash;
  const response=await fetch('/api/trait-library/export.json',{headers:{'X-Traitweaver-Client':'workspace','X-Traitweaver-Privacy-Reviewed':hash}});
  if(!response.ok)throw Error((await response.json()).error);
  const p=await response.json();if(tlOwner().hash!==hash)throw Error('Review changed; inspect again before export.');
  download('trait-library-review.json',pretty(p)+'\n','application/json');show('Local review export requested; no sharing authorized.');
 }catch(e){show(e.message,true);}});
 document.getElementById('tl-open')?.addEventListener('change',async e=>{const f=e.target.files[0];if(!f)return;if(f.size>2097152){show('Package too large.',true);return;}await perform('/api/trait-library/open',body({package_json:await f.text()}),'Library review reopened read-only; nothing executed.');});
 document.getElementById('tl-return')?.addEventListener('click',()=>perform('/api/trait-library/local',body({}),'Original local library history restored.'));
}
