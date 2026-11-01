"""Separate source-bound molecular reasoning model. No network or laboratory tools."""
from copy import deepcopy
import math

from traitweaver import public_algae, study
from traitweaver.study_store import screen_export

LIMIT='Research interpretation only. Public reference identity and published associations do not prove protein necessity, sufficiency, combination effects or transfer. No guide, edit site, construct or laboratory protocol is generated.'
CHECKS={'trait_evidence_audit':'Trait → protein evidence audit','combination_coverage':'Protein-combination coverage audit','transfer_coverage':'Species / context transfer review'}
FOCI={'trait':'trait_evidence_audit','combinations':'combination_coverage','transfer':'transfer_coverage'}
COMBINATIONS={'regulation_storage':['regulation','storage'],'regulation_recovery':['regulation','recovery'],'regulation_storage_recovery':['regulation','storage','recovery']}
RECIPIENTS={'unselected':{'label':'Recipient not selected','organism':None,'strain':None,'assembly':None,'context_kind':'unqualified'},
            'reference_cc503':{'label':'C. reinhardtii · CC-503 reference','organism':'Chlamydomonas reinhardtii','strain':'CC-503 cw92 mt+','assembly':'GCF_000002595.2','context_kind':'same_reference'},
            'study_uvm4':{'label':'C. reinhardtii · UVM4 study context','organism':'Chlamydomonas reinhardtii','strain':'UVM4','assembly':None,'context_kind':'same_species_different_context'}}


def catalog():
    literature=study.bundle()
    try:reference=public_algae.catalog()
    except (ValueError,OSError):reference=None
    claims={
      'C_PSR1_PATH':{'role':'published_summary','source_id':'S_PSR1_2023','locator':'Table 1; admitted growth and phosphate-uptake summaries','statement':'The PSR1 overexpression path has published source-bound summaries in UVM4 and three lines; this is not a necessity or recovery claim.'},
      'C_ENDPOINTS':{'role':'admitted_bundle_coverage','source_id':None,'source_ids':['S_PSR1_2023','S_OVERPLUS_2024'],'locator':'data/algae-public.v1.json / evidence','statement':'The admitted endpoint records keep uptake, cellular phosphorus and recovered product distinct; missing admission is not proof of absence in all literature.'},
      'C_COMBINATION_GAP':{'role':'curation_gap','source_id':None,'locator':'This catalog / candidates and combination evidence','statement':'Only one candidate is admitted. No pair experiment, required protein set, synergy, antagonism or stoichiometry is admitted.'},
      'C_RECIPIENT_GAP':{'role':'curation_gap','source_id':None,'locator':'This catalog / recipients','statement':'No cross-species recipient, orthology result, compatible expression/localization/partners or transfer outcome is qualified.'},
      'C_STRAIN_CONTEXT':{'role':'source_context','source_id':'S_PSR1_2023','locator':'Table 1 UVM4 source context; reference source/strain when available','statement':'The study UVM4 context is not automatically sequence-equivalent to the CC-503 reference.'}}
    if reference:
        for key,c in [('C_REFERENCE_IDENTITY',reference['claims'][0]),('C_REFERENCE_SEQUENCE',reference['claims'][2])]:
            claims[key]={'role':c['kind'],'source_id':'PSR1_REFERENCE_FILES','locator':c['locator'],'statement':c['statement'],'files':c['files']}
    return {'schema_version':'traitweaver.intelligence_catalog.v1','literature':literature,'reference':reference,
            'source_digests':{'literature':study.digest(literature),'reference':None if reference is None else study.digest(reference)},
            'reference_status':'available' if reference else 'unavailable_source_validation','claims':claims,
            'candidates':[{'id':'P_PSR1_REFERENCE','label':'PSR1-associated research candidate','role':'publication_associated_candidate',
                           'protein_id':public_algae.PROTEIN if reference else None,'transcript_id':public_algae.TRANSCRIPT if reference else None,
                           'gene_id':public_algae.GENE if reference else None,'necessity':None,'sufficiency':None,'causal_recovery_effect':None,
                           'citations':['C_PSR1_PATH']+(['C_REFERENCE_IDENTITY'] if reference else [])}],
            'recipients':deepcopy(RECIPIENTS),'combination_templates':deepcopy(COMBINATIONS),'checks':deepcopy(CHECKS),'limit':LIMIT}


def initial_scope():
    return {'target_endpoint':'recovered_product_phosphorus','minimum_growth_ratio':None,'recipient':'unselected','combination':'regulation_storage_recovery'}


def validate_scope(value):
    study.fields(value,('target_endpoint','minimum_growth_ratio','recipient','combination'))
    if any(not isinstance(value[k],str) for k in ('target_endpoint','recipient','combination')):raise ValueError('Scope choices must be registered text identifiers')
    if value['target_endpoint'] not in study.ENDPOINTS or value['recipient'] not in RECIPIENTS or value['combination'] not in COMBINATIONS:raise ValueError('Unavailable endpoint, recipient context or combination template')
    x=value['minimum_growth_ratio']
    if x is not None and (type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=100):raise ValueError('Growth margin must be unknown or a finite nonnegative ratio up to 100')
    return deepcopy(value)


def context(current):
    return {'study_id':current['state']['study_id'],'study_revision_hash':current['hash']}


def initial():
    return {'scope':initial_scope(),'context':None,'cycles':[]}


def required_citations(check,bundle):
    base={'trait_evidence_audit':['C_PSR1_PATH','C_ENDPOINTS'],
          'combination_coverage':['C_PSR1_PATH','C_COMBINATION_GAP'],
          'transfer_coverage':['C_STRAIN_CONTEXT','C_RECIPIENT_GAP']}[check]
    return base+(['C_REFERENCE_IDENTITY'] if bundle['reference'] else [])


def audit(check,scope,bundle):
    """Pure validation arithmetic; no retrieval, provider dispatch or external tools."""
    validate_scope(scope)
    if check not in CHECKS:raise ValueError('Unregistered intelligence check')
    reference=bundle['reference'];mapping=reference['transcript_maps'][public_algae.TRANSCRIPT] if reference else None
    mapping_summary=None if mapping is None else {'protein_id':public_algae.PROTEIN,'transcript_id':public_algae.TRANSCRIPT,'gene_id':public_algae.GENE,
       'assembly':mapping['gene']['assembly'],'chromosome':mapping['gene']['chromosome'],'strain':reference['strain'],'length_aa':mapping['protein_length_aa'],
       'transcript_length_nt':mapping['transcript_length_nt'],'translation_status':mapping['translation_status'],'record_status':reference['record_status']}
    common=['Protein necessity and sufficiency are unestablished.','No recovered-product performance, executable intervention or biological winner is inferred.']
    if reference is None:common+=['Pinned reference files failed validation; exact protein/gene/transcript identity is unavailable. Published study records remain distinct.']
    if check=='trait_evidence_audit':
        rows=[deepcopy(e) for e in bundle['literature']['evidence'] if e['endpoint']==scope['target_endpoint']]
        numeric=[r for r in rows if type(r.get('value')) in (int,float)]
        outcome='supported' if scope['target_endpoint']=='phosphate_uptake' and numeric else ('inconclusive' if rows else 'unavailable')
        meaning='Published source-bound phosphate-uptake association; protein necessity and transfer remain unknown.' if outcome=='supported' else ('Descriptive source records do not establish a causal protein effect or acceptance against the chosen growth margin.' if rows else 'The selected endpoint has no admitted matching observations.')
        body={'candidate':deepcopy(bundle['candidates'][0]),'mapping':mapping_summary,'endpoint':scope['target_endpoint'],
              'matching_records':rows,'numeric_record_count':len(numeric),'growth_margin':scope['minimum_growth_ratio'],
              'necessity':None,'sufficiency':None,'causal_effect':None}
        growth=[e for e in bundle['literature']['evidence'] if e['source_id']=='S_PSR1_2023' and e['endpoint']=='growth']
        controls=[e for e in growth if e['subject']=='UVM4'];comparisons=[]
        if len(controls)==1 and type(controls[0]['value']) in (int,float) and controls[0]['value']>0:
            for e in growth:
                if e['subject']=='UVM4':continue
                ratio=e['value']/controls[0]['value']
                comparisons.append({'subject':e['subject'],'ratio_to_own_source_control':ratio,'meets_point_mean_margin':None if scope['minimum_growth_ratio'] is None else ratio>=scope['minimum_growth_ratio']})
        body['growth_constraint']={'source_control':'UVM4','point_mean_comparisons':comparisons,'margin':scope['minimum_growth_ratio'],
             'qualification':'Descriptive same-study mean ratios only. Reported growth summaries retain units, SE and sample counts in the public catalog; no significance or equivalence claim.'}
        if outcome=='supported' and comparisons and all(x['meets_point_mean_margin'] is False for x in comparisons):
            outcome='contradictory';meaning='The uptake association is present, but none of the admitted overexpression lines meets the selected growth margin on source point means. This is not a significance, equivalence or biological-failure claim.'
        blockers=common+(['CC-503 reference identity is not a sequence-qualified map of the UVM4 study lines.'] if reference else [])
        if not rows:blockers.insert(0,'No admitted measurement for '+scope['target_endpoint']+'.')
    elif check=='combination_coverage':
        roles=COMBINATIONS[scope['combination']]
        body={'template':scope['combination'],'roles':[{'role':r,'status':'candidate_association_only' if r=='regulation' else 'identity_unavailable',
              'candidate_ids':['P_PSR1_REFERENCE'] if r=='regulation' else [],'required_for_trait':None} for r in roles],
              'admitted_candidate_count':len(bundle['candidates']),'qualified_pair_count':0,'combination_effect':None,'synergy':None,'antagonism':None,'stoichiometry':None}
        outcome='unavailable';meaning='This is a role-based hypothesis template, not a qualified protein combination or a claim that every role requires a separate protein.'
        blockers=['At least two qualified distinct protein identities and a justified comparison are needed for a protein-pair review.','Storage/recovery protein identities and interaction evidence are not admitted.','Zero admitted pair records does not mean zero biological interaction.']+common
    else:
        recipient=RECIPIENTS[scope['recipient']]
        requirements=['recipient_reference','orthology','regulatory_context','localization','pathway_partners','expression','function','fitness','phenotype']
        body={'reference':mapping_summary,'recipient':deepcopy(recipient),'relationship':recipient['context_kind'],
              'requirements':[{'id':r,'status':'reference_identity_only' if r=='recipient_reference' and recipient['context_kind']=='same_reference' and reference else 'unavailable','value':None} for r in requirements],
              'transfer_success_probability':None,'phenotype_transfer':None}
        outcome='inconclusive' if recipient['context_kind']=='same_reference' and reference else 'unavailable'
        meaning='Same-reference identity check only; there is no transfer event or qualified phenotype effect.' if recipient['context_kind']=='same_reference' else 'Recipient context and function transfer remain unqualified. Same-species strain differences do not constitute demonstrated cross-species transfer.'
        blockers=['No cross-species recipient is admitted; public organism/reference evidence must be qualified before naming one.','Sequence agreement or orthology alone cannot establish expression, localization, partners, phenotype or fitness.']+common
        if scope['recipient']=='study_uvm4':blockers.insert(0,'UVM4 is a same-species study context with no admitted exact recipient assembly/sequence map.')
    return {'check':check,'outcome':outcome,'interpretation':meaning,'facts':body,'blockers':blockers,
            'citations':required_citations(check,bundle),'measurement_plan':measurement_plan(check,scope),'limit':LIMIT}


def measurement_plan(check,scope):
    return {'question':CHECKS[check]+' for '+scope['target_endpoint'],
      'comparison':'Define a named context and its own matched baseline; retain source controls and avoid unsupported cross-study rankings.',
      'controls':['Context-matched baseline','Qualified process and assay reference/background controls; suitability unresolved'],
      'readouts':['Exact reference identity and relevant transcript evidence','Candidate protein abundance and separately qualified function','Separate uptake, cellular phosphorus, recovered-product phosphorus and growth, with units and time bases'],
      'independent_units':'Define independent biological units and uncertainty; technical reads are not independent biological units.',
      'unresolved':['Additional candidate identities and mechanism evidence','Combination dependencies and interaction evidence','Recipient organism/reference and context compatibility','Assay qualification, replication and decision thresholds'],
      'execution':'Measurement questions only. No executable laboratory protocol.'}


def active(state):
    return state['cycles'][-1] if state['cycles'] and state['cycles'][-1]['applicability']=='current' else None


def run_check(check,scope,bundle,cycle_id):
    return result(check,scope,bundle,cycle_id)


def result(check,scope,bundle,cycle_id):
    data={'schema_version':'traitweaver.intelligence_result.v1','cycle_id':cycle_id,'catalog_sha256':study.digest(bundle),'scope_sha256':study.digest(scope),'status':'completed',**audit(check,scope,bundle)}
    data['id']=study.digest(data);return data


def failure_result(check,scope,bundle,cycle_id):
    data={'schema_version':'traitweaver.intelligence_result.v1','cycle_id':cycle_id,'catalog_sha256':study.digest(bundle),'scope_sha256':study.digest(scope),
          'status':'failed','check':check,'outcome':'failed','interpretation':'The local check failed. No biological result was produced.',
          'facts':{},'blockers':['Inspect local software state before deliberately choosing a later action.'],
          'citations':required_citations(check,bundle),'measurement_plan':measurement_plan(check,scope),'limit':LIMIT}
    data['id']=study.digest(data);return data


def transition(previous,action,bundle,recorded_result=None,validating_history=False):
    from traitweaver import intelligence_muse
    study.fields(action,('type','payload'));out=deepcopy(previous);p=action['payload']
    if action['type']=='revise':
        study.fields(p,('scope','context'));scope=validate_scope(p['scope']);ctx=p['context'];study.fields(ctx,('study_id','study_revision_hash'))
        study.text(ctx['study_id'],100)
        if not isinstance(ctx['study_revision_hash'],str) or len(ctx['study_revision_hash'])!=64 or any(c not in 'abcdef0123456789' for c in ctx['study_revision_hash']):raise ValueError('Invalid owning study context')
        if scope!=out['scope'] or ctx!=out['context']:
            for c in out['cycles']:c['applicability']='needs_reassessment'
        out['scope']=scope;out['context']=deepcopy(ctx)
    elif action['type']=='accept':
        intelligence_muse.validate_accept(out,p,bundle,allow_historical_order=validating_history)
        if p['phase']=='selection':
            check=p['proposal']['check'];cycle_id='I'+str(len(out['cycles'])+1)
            out['cycles'].append({'id':cycle_id,'scope':deepcopy(out['scope']),'context':deepcopy(out['context']),'applicability':'current',
              'decision':{'check':check,'arguments':deepcopy(out['scope']),'purpose':intelligence_muse.RATIONALES[check],
                 'deferred_alternatives':[x for x in CHECKS if x!=check],'conditional_next_steps':{'supported':'Review association and context limits before any new claim.','contradictory':'Review the point-mean constraint conflict and uncertainty; do not declare biological failure.','unavailable':'Review named evidence requirements.','inconclusive':'Resolve context and measurement decisions.','failed':'Inspect the safe failure and deliberately choose a later action.'},
                 'accepted_reply':deepcopy(p)},'result':None,'assessment':None})
        else:
            c=active(out);c['assessment']={'outcome':c['result']['outcome'],'next_action':'researcher_review_measurement_plan','result_id':c['result']['id'],
               'interpretation':c['result']['interpretation'],'measurement_plan':deepcopy(c['result']['measurement_plan']),'accepted_reply':deepcopy(p),'limit':LIMIT}
    elif action['type']=='run':
        study.fields(p,());c=active(out)
        if c is None or c['result'] is not None or c['assessment'] is not None:raise ValueError('One current unexecuted decision is required')
        if recorded_result is None:
            try:actual=run_check(c['decision']['check'],c['scope'],bundle,c['id'])
            except Exception:actual=failure_result(c['decision']['check'],c['scope'],bundle,c['id'])
        else:
            expected=(failure_result if recorded_result.get('status')=='failed' else result)(c['decision']['check'],c['scope'],bundle,c['id'])
            if study.canonical(recorded_result)!=study.canonical(expected):raise ValueError('Recorded intelligence result differs from source-bound validation')
            actual=deepcopy(recorded_result)
        c['result']=actual
    else:raise ValueError('Unregistered intelligence action')
    screen_export(out);return out
