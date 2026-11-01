"""Bounded molecular planning and synthetic coordinate arithmetic; no retrieval."""
from copy import deepcopy
import hashlib
from pathlib import Path

from traitweaver import protein_card, study
from traitweaver.study_store import screen_export

FIXTURE = study.APP_ROOT / 'data/molecular-demo.v1.json'
FIXTURE_HASH = '9811577f4b980c42f8f3314ea78a394b5a847542cfe03beddb0307fb0f282371'
LIMIT = 'Molecular planning only. Synthetic coordinate consistency is not biological evidence, a sequence-verified translation or an executable CRISPR design. No guide, edit site or laboratory protocol is generated.'
GOALS = {
    'increase_expression': ('Expression increase', 'CRISPR activation concept', 'Assess transcript and protein abundance alongside the study endpoint.'),
    'decrease_expression': ('Expression decrease', 'CRISPR interference concept', 'Assess transcript and protein reduction alongside the study endpoint.'),
    'loss_of_function': ('Loss-of-function question', 'Gene disruption concept', 'Review evidence for loss of function and effects on other isoforms.'),
    'isoform_comparison': ('Isoform comparison', 'Transcript evidence review', 'Compare isoform support and protein consequences before choosing an intervention.'),
}
STAGES = ['question', 'identity', 'transcripts', 'concept', 'measurements', 'review']


def integer(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError('Invalid molecular coordinate or count')
    return value


def _validate_models(value):
    study.fields(value, ('schema_version','fixture_kind','coordinate_system','organism','source','genes','exons','transcripts','proteins'))
    if value['schema_version'] != 'traitweaver.molecular_models.v1' or value['fixture_kind'] != 'synthetic_coordinate_model':
        raise ValueError('Only the declared synthetic molecular model is supported')
    study.fields(value['source'], ('id','title','role','origin','limitations'))
    if value['source']['role'] != 'software_fixture':
        raise ValueError('Synthetic models cannot be promoted to published observations')
    for key in ('coordinate_system','organism'):
        study.text(value[key])
    for text in value['source'].values():study.text(text)
    def index(key):
        rows=value[key]
        if not isinstance(rows,list) or not 1 <= len(rows) <= 32:raise ValueError('Unsupported molecular collection')
        result={}
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in result:
                raise ValueError('Missing or duplicate molecular identity')
            study.text(row['id'],100);result[row['id']]=row
        return result
    genes=index('genes');exons=index('exons');proteins=index('proteins');transcripts=index('transcripts')
    for g in genes.values():
        study.fields(g, ('id','label','assembly','chromosome','strand','start','end','source_id'))
        if g['strand'] not in ('+','-') or integer(g['start'])>=integer(g['end']) or g['source_id']!=value['source']['id']:
            raise ValueError('Invalid gene context')
        for key in ('id','label','assembly','chromosome'):study.text(g[key],200)
    for e in exons.values():
        study.fields(e, ('id','gene_id','start','end','cds'))
        if e['gene_id'] not in genes:raise ValueError('Unresolved exon gene identity')
        g=genes[e['gene_id']]
        if not g['start']<=integer(e['start'])<integer(e['end'])<=g['end']:raise ValueError('Exon outside its gene context')
        if e['cds'] is not None:
            if not isinstance(e['cds'],list) or len(e['cds'])!=2:raise ValueError('Invalid coding interval')
            a,b=map(integer,e['cds'])
            if not e['start']<=a<b<=e['end']:raise ValueError('Coding interval outside exon')
    for p in proteins.values():
        study.fields(p, ('id','label','length_aa'));study.text(p['label'],200)
        if integer(p['length_aa'])==0:raise ValueError('Empty declared protein')
    for t in transcripts.values():
        study.fields(t, ('id','label','gene_id','exon_ids','protein_id'));study.text(t['label'],200)
        if t['gene_id'] not in genes or not isinstance(t['exon_ids'],list) or not t['exon_ids'] or len(set(t['exon_ids']))!=len(t['exon_ids']):
            raise ValueError('Invalid transcript identity or exon membership')
        if any(e not in exons or exons[e]['gene_id']!=t['gene_id'] for e in t['exon_ids']):raise ValueError('Transcript crosses gene contexts')
        rows=[exons[e] for e in t['exon_ids']];g=genes[t['gene_id']]
        ordered=sorted(rows,key=lambda e:e['start'],reverse=g['strand']=='-')
        if rows!=ordered:raise ValueError('Exons must be in transcript 5-prime order for the declared strand')
        genomic=sorted(rows,key=lambda e:e['start'])
        if any(a['end']>b['start'] for a,b in zip(genomic,genomic[1:])):raise ValueError('Overlapping transcript exons')
        cursor=0;coding_spans=[]
        for e in rows:
            if e['cds'] is not None:
                a,b=e['cds'];offset=a-e['start'] if g['strand']=='+' else e['end']-b
                coding_spans.append([cursor+offset,cursor+offset+b-a])
            cursor+=e['end']-e['start']
        if any(a[1]!=b[0] for a,b in zip(coding_spans,coding_spans[1:])):
            raise ValueError('This bounded model requires a contiguous coding interval in transcript space')
        coding=sum(b-a for a,b in coding_spans)
        if t['protein_id'] is not None:
            if t['protein_id'] not in proteins or coding%3 or coding//3!=proteins[t['protein_id']]['length_aa']:
                raise ValueError('Declared synthetic protein does not match coding-length model')
    screen_export(value)
    return deepcopy(value)


def validate_models(value):
    try:return _validate_models(value)
    except (KeyError,TypeError,AttributeError,IndexError,RecursionError):
        raise ValueError('Malformed synthetic molecular model') from None


def models():
    if FIXTURE.is_symlink() or not FIXTURE.is_file() or FIXTURE.stat().st_size>131072:raise ValueError('Molecular fixture is missing, unsafe or oversized')
    raw=FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FIXTURE_HASH:raise ValueError('Pinned molecular fixture changed; no lookup fallback')
    return validate_models(study.decode(raw))


def transcript_map(model, transcript_id):
    t=next(t for t in model['transcripts'] if t['id']==transcript_id)
    g=next(g for g in model['genes'] if g['id']==t['gene_id'])
    exons={e['id']:e for e in model['exons']};cursor=coding=0;rows=[]
    for name in t['exon_ids']:
        e=exons[name];length=e['end']-e['start'];cds=e['cds']
        size=cds[1]-cds[0] if cds is not None else 0
        offset=None if cds is None else (cds[0]-e['start'] if g['strand']=='+' else e['end']-cds[1])
        rows.append({'exon_id':name,'genomic_interval':[e['start'],e['end']], 'transcript_interval':[cursor,cursor+length],
                     'transcript_coding_interval':None if cds is None else [cursor+offset,cursor+offset+size],
                     'coding_interval':None if cds is None else [coding,coding+size],
                     'phase_at_coding_start':None if cds is None else coding%3,
                     'protein_interval':None})
        cursor+=length;coding+=size
    mapped=t['protein_id'] is not None and coding%3==0
    if mapped:
        for row in rows:
            if row['coding_interval'] is not None:
                a,b=row['coding_interval'];row['protein_interval']=[a//3,(b+2)//3]
    return {'transcript':deepcopy(t),'gene':deepcopy(g),'rows':rows,'transcript_length_nt':cursor,
            'coding_length_nt':coding,'coding_remainder':coding%3,'protein_length_aa':coding//3 if mapped else None,
            'translation_status':'synthetic_length_model_only' if mapped else 'unresolved_coding_model',
            'coordinate_system':model['coordinate_system'],'limit':LIMIT}


def catalog():
    model=models();card=protein_card.build_card();identity=card['identity']
    public={'id':identity['uniprot_accession'],'label':identity['protein_name']+' · qualified public reference',
            'length_aa':identity['sequence_length'],'gene_label':identity['gene_label'],'organism':identity['organism'],
            'source_snapshot_sha256':deepcopy(protein_card.PINS),'attribution':deepcopy(card['attribution']),
            'source_id':'S_UNIPROT_P42212','locator':'accession.json /accession and /gene',
            'gene_id':None,'transcript_ids':[],'assembly':None,'role':'public_reference_metadata',
            'limit':'GFP is a supplied gene label, not an admitted versioned gene/transcript/genome mapping. No algae relevance is asserted.'}
    return {'schema_version':'traitweaver.molecular_catalog.v1','synthetic_fixture_sha256':FIXTURE_HASH,'synthetic_models':model,'public_reference':public,
            'transcript_maps':{t['id']:transcript_map(model,t['id']) for t in model['transcripts']},
            'goals':{k:{'label':v[0],'concept':v[1],'readout_question':v[2]} for k,v in GOALS.items()},
            'limit':LIMIT}


def initial_selection():
    return {'protein_id':'DEMO-P-A.1','transcript_id':None,'comparison_id':None,'goal':'increase_expression'}


def _validate_selection(selection, bundle):
    study.fields(selection, ('protein_id','transcript_id','comparison_id','goal'))
    if selection['goal'] not in GOALS:raise ValueError('Unknown planning objective')
    proteins={p['id'] for p in bundle['synthetic_models']['proteins']}|{bundle['public_reference']['id']}
    if selection['protein_id'] not in proteins:raise ValueError('Unknown protein identity')
    maps=bundle['transcript_maps'];t=selection['transcript_id'];other=selection['comparison_id']
    if t is not None and (t not in maps or maps[t]['transcript']['protein_id']!=selection['protein_id']):
        raise ValueError('Transcript is incompatible with the selected protein')
    if other is not None and (t is None or other==t or other not in maps or maps[other]['gene']['id']!=maps[t]['gene']['id']):
        raise ValueError('Comparison requires distinct transcripts from the same versioned gene context')
    return deepcopy(selection)


def validate_selection(selection, bundle):
    try:
        if bundle.get('schema_version')=='traitweaver.molecular_catalog.v2':
            from traitweaver import public_algae
            return public_algae.validate_selection(selection,bundle)
        return _validate_selection(selection,bundle)
    except (KeyError,TypeError,AttributeError,IndexError,RecursionError):
        raise ValueError('Malformed molecular selection') from None


def assess(selection, bundle):
    if bundle.get('schema_version')=='traitweaver.molecular_catalog.v2':
        from traitweaver import public_algae
        return public_algae.assess(selection,bundle)
    validate_selection(selection,bundle)
    candidates=[t['id'] for t in bundle['synthetic_models']['transcripts'] if t['protein_id']==selection['protein_id']]
    chosen=selection['transcript_id'];mapping=bundle['transcript_maps'].get(chosen)
    synthetic=selection['protein_id']!=bundle['public_reference']['id']
    blockers=[]
    if not candidates:blockers+=['No versioned gene identity, transcript identity or genome assembly is admitted for this public protein.']
    elif chosen is None:blockers+=['Choose a transcript explicitly; protein-to-transcript identity may be one-to-many.']
    if synthetic:blockers+=['Synthetic identifiers and coordinates cannot qualify a real biological target.']
    blockers+=['No sequence-backed target or off-target evidence is admitted.', 'No intervention result or recovery performance is established.']
    comparison=None
    if selection['comparison_id'] is not None:
        other=bundle['transcript_maps'][selection['comparison_id']]
        a=mapping['transcript']['exon_ids'];b=other['transcript']['exon_ids']
        comparison={'primary':chosen,'comparison':selection['comparison_id'],'shared_exons':[x for x in a if x in b],
                    'primary_only':[x for x in a if x not in b],'comparison_only':[x for x in b if x not in a],
                    'transcript_delta_nt':other['transcript_length_nt']-mapping['transcript_length_nt'],
                    'coding_delta_nt':other['coding_length_nt']-mapping['coding_length_nt'],
                    'comparison_coding_remainder':other['coding_remainder'],
                    'protein_length_difference_aa':None if other['protein_length_aa'] is None else other['protein_length_aa']-mapping['protein_length_aa'],
                    'interpretation':'Coordinate-only synthetic comparison; no splice event, translation or functional effect has been experimentally observed.'}
    goal=GOALS[selection['goal']]
    return {'mapping_status':'explicit_synthetic_mapping' if mapping else ('selection_required' if candidates else 'unavailable'),
            'candidate_transcripts':candidates,'mapping':mapping,'comparison':comparison,'synthetic':synthetic,
            'planning_only':True,'biological_target_ready':False,'blockers':blockers,
            'concept':{'label':goal[1],'purpose':goal[2], 'not_generated':['guide sequences','edit sites','constructs','laboratory protocol']},
            'measurement_plan':{'question':goal[0]+' in the selected context',
                'comparison':'Selected candidate versus context-matched source controls; unresolved for real biology.',
                'controls':['Matched baseline context','Appropriate intervention-process control to be decided by a researcher','Isoform-aware reference measurements'],
                'readouts':['Transcript / isoform support','Protein abundance or qualified activity','Study endpoint and growth, kept distinct'],
                'independent_units':'Define independent biological units and replication; repeated reads are not independent biological units.',
                'unresolved':['Exact real gene/transcript/assembly identity','Relevance to the study question','Control suitability and endpoint thresholds','Uncertainty, independent units and assay qualification'],
                'execution':'Measurement questions only; no executable biological procedure.'},'limit':LIMIT}


def context(current):
    return {'study_id':current['state']['study_id'],'study_revision_hash':current['hash'],
            'target_endpoint':current['state']['brief']['target_endpoint']}
