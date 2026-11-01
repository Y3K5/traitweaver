"""Public-source research story, proposed measurement design and synthetic math.

No construct/guide design, laboratory protocol, provider or experimental run.
Original evidence, assistant and mapping contracts stay unchanged.
"""
from copy import deepcopy
import hashlib
import math

from traitweaver import study, study_store, public_algae, protein_card, assistant

FIXTURE=study.APP_ROOT/'data/research-story.v1.json'
PIN='7584cda0ae8b8e9eb74b362bda1d02c1dd01acbd80d2e30846c855680f90538b'
SCHEMA='traitweaver.research_story_package.v1'
STAGES=('evidence','identity','materials','fluorescence','phosphorus','reactor','plan')
SUBJECTS=('UVM4','8-27','8-42','8-2')
LIMIT='Published summaries and reference annotation; authored study-design proposals; optional clearly synthetic calculations. No linked laboratory run, engineered material, cassette/guide design or biological improvement is established.'


def fixture():
    if FIXTURE.is_symlink():raise ValueError('Unsafe research-story fixture')
    raw=FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError('Research-story fixture changed; no fallback')
    value=study.decode(raw);study_store.screen_export(value);return value


def _numbers(values):
    return all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in values)


def _portable_numbers(value):
    """JSON numbers have no float-vs-int type; preserve bool/null explicitly."""
    if type(value) is float and math.isfinite(value) and value.is_integer():return int(value)
    if isinstance(value,dict):return {k:_portable_numbers(v) for k,v in value.items()}
    if isinstance(value,list):return [_portable_numbers(v) for v in value]
    return value


def fluorescence(value):
    out={'role':'synthetic_calculation','inputs':deepcopy(value),'net_signal':None,'normalized_signal':None,
         'normalized_unit':'RFU / g dry_weight','interpretation':'Illustrative arithmetic only; not edit confirmation, expression validation, phosphorus performance or cross-instrument comparability.'}
    if value['signal_unit']!='RFU' or value['background_unit']!='RFU' or value['normalization_unit']!='g dry_weight':
        return dict(out,status='invalid',blocker='incompatible_units')
    values=[value[k] for k in ('signal','background','normalization_mass')]
    if any(v is None for v in values):return dict(out,status='unavailable',blocker='missing_input')
    if not _numbers(values):return dict(out,status='invalid',blocker='invalid_numeric_input')
    out['net_signal']=value['signal']-value['background']
    if value['normalization_mass']==0:return dict(out,status='inconclusive',blocker='zero_normalization_mass')
    out['normalized_signal']=out['net_signal']/value['normalization_mass']
    return dict(out,status='illustration_only',blocker='instrument_and_biological_qualification_missing')


def phosphorus(value):
    out={'role':'synthetic_calculation','inputs':deepcopy(value),'concentration_change_percent':None,
         'liquid_inventory_decrease_percent':None,'input_mass_mg_P':None,'final_liquid_mass_mg_P':None,
         'accounted_mass_mg_P':None,'unaccounted_mass_mg_P':None,'mass_closure_percent':None,
         'collected_product_fraction_percent':None,'microbe_effect':None,'plant_use':None,'chemical_transformation':None,
         'interpretation':'Disjoint compartment arithmetic only. Concentration decline, liquid inventory change and collected product are different quantities; no microbial causality, assimilation, speciation or plant-use benefit follows.'}
    if (value['basis'],value['concentration_unit'],value['volume_unit'],value['mass_unit'])!=('elemental_P','mg P/L','L','mg P'):
        return dict(out,status='invalid',blocker='incompatible_phosphorus_basis_or_units')
    if value['compartments_disjoint'] is not True:return dict(out,status='invalid',blocker='overlapping_or_unqualified_compartments')
    keys=('initial_concentration','initial_volume','final_concentration','final_volume','retained_biomass_P','collected_product_P','sample_outflow_P','other_input_P')
    vals=[value[k] for k in keys]
    if any(v is None for v in vals):return dict(out,status='unavailable',blocker='missing_mass_accounting_input')
    if not _numbers(vals):return dict(out,status='invalid',blocker='invalid_numeric_input')
    initial=value['initial_concentration']*value['initial_volume'];final=value['final_concentration']*value['final_volume']
    total=initial+value['other_input_P'];accounted=final+value['retained_biomass_P']+value['collected_product_P']+value['sample_outflow_P']
    out.update(input_mass_mg_P=total,final_liquid_mass_mg_P=final,accounted_mass_mg_P=accounted,unaccounted_mass_mg_P=total-accounted)
    if value['initial_concentration']!=0:out['concentration_change_percent']=100*(value['initial_concentration']-value['final_concentration'])/value['initial_concentration']
    if initial!=0:out['liquid_inventory_decrease_percent']=100*(initial-final)/initial
    if total!=0:out.update(mass_closure_percent=100*accounted/total,collected_product_fraction_percent=100*value['collected_product_P']/total)
    return dict(out,status='illustration_only',blocker='no_control_uncertainty_or_actual_run')


def content():
    f=fixture();bundle=study.bundle();ref=public_algae.catalog();gfp=protein_card.build_card()
    summaries={}
    for metric in study.METRICS:
        contrasts=study._contrast_value(study.initial_state(),metric)
        if contrasts['status']!='completed':raise ValueError('Published summary contrast is not admitted')
        rows=[e for e in bundle['evidence'] if e['source_id']=='S_PSR1_2023' and e['metric']==metric]
        comparisons={r['subject']:r for r in contrasts['rows']}
        summaries[metric]={'unit':contrasts['unit'],'measurement_basis':contrasts['measurement_basis'],'source_id':'S_PSR1_2023',
            'rows':[{'record':e,'ratio_to_control':1 if e['subject']=='UVM4' else comparisons[e['subject']]['ratio_to_control'],
                     'difference_from_control':0 if e['subject']=='UVM4' else comparisons[e['subject']]['difference_from_control']} for e in rows],
            'limit':contrasts['uncertainty_limit']}
    mapping=ref['transcript_maps'][public_algae.TRANSCRIPT];hashes=ref['checks']['sequence_sha256']
    chain=[{'id':'REF_GENOME','form':'Genome reference / one extracted locus','identifier':'GCF_000002595.2 / NC_057015.1',
            'parent':None,'length':5402,'unit':'nt in extracted region','sequence_sha256':hashes['genomic'],'source':'reference_gene_region.gb',
            'role':'reference_annotation','limit':'Region hash only, not a whole-genome hash. The intended edited organism/genome has not been sequenced here.'},
           {'id':'REF_GENE','form':'Annotated gene','identifier':public_algae.GENE,'parent':'REF_GENOME',
            'source':'reference_gene_region.gb','role':'reference_annotation','limit':'CC-503 reference annotation; not a new edited-material record.'},
           {'id':'REF_RNA','form':'Reference transcript','identifier':public_algae.TRANSCRIPT,'parent':'REF_GENE',
            'length':mapping['transcript_length_nt'],'unit':'nt','exon_count':len(mapping['rows']), 'sequence_sha256':hashes['transcript'],
            'source':'refseq_XM_001700501.2.gb','role':'reference_annotation_and_sequence_reconciliation','limit':'One admitted reference transcript; no experimental expression or alternate isoform is established.'},
           {'id':'REF_PROTEIN','form':'Reference protein','identifier':public_algae.PROTEIN,'parent':'REF_RNA',
            'length':mapping['protein_length_aa'],'unit':'aa','sequence_sha256':hashes['refseq_protein'],
            'source':'refseq_XP_001700553.1.gb','role':'reference_annotation_and_sequence_reconciliation','limit':'PSR1-associated reference; RefSeq product is uncharacterized. Sequence agreement is not functional validation.'}]
    sources=bundle['sources']+ref['sources']['sources']+gfp['sources']
    allowed={s['id'] for s in sources}|{e['id'] for e in bundle['evidence']}|{'ENV_SCOPE','ENV_GAPS'}
    for card in f['plan']:
        if not set(card['sources'])<=allowed:raise ValueError('Unknown study-design citation')
    data={'role':'public_reference_and_proposed_design_with_separate_synthetic_examples',
        'objective':'Investigate phosphorus recovery while considering growth; preserve identity and measure each compartment separately.',
        'summaries':summaries,'public_observations':bundle['evidence'],
        'scope_records':assistant.get_case('ENV_ALGAE')['records'][-2:],
        'reference_chain':chain,'reference_context':ref['strain'],
        'reference_checks':{k:v for k,v in ref['checks'].items() if k in ('spliced_genomic_equals_refseq_transcript','translated_cds_equals_refseq_protein','unreviewed_uniprot_equals_refseq_protein')},
        'reference_limit':'CC-503 reference context is not qualified as equivalent to the UVM4 literature lines. Only one locus, one transcript and its protein are admitted; no edited or whole experimental genome is mapped.',
        'gfp_reference':{'card_id':gfp['card_id'],'accession':'P42212','length_aa':gfp['identity']['sequence_length'],
            'role':'separate_qualified_reference_only','relevance_link_to_algae':None,'reporter_construct_record':None,
            'limit':'No GFP/PSR1 fusion or inserted reporter is linked. A fluorescence plan is a proposal; the GFP card is not automatically study evidence.'},
        'planned_materials':f['planned_materials'],'study_design':f['plan'],'synthetic_inputs':f['synthetic_math'],
        'synthetic_calculations':{'fluorescence':fluorescence(f['synthetic_math']['fluorescence']),'phosphorus':phosphorus(f['synthetic_math']['phosphorus'])},
        'sources':sources,'actual_lab_run_id':None,'actual_edited_material_id':None,'decision_thresholds':None,
        'source_identity':{'algae_canonical_sha256':study.digest(bundle),'public_reference_pin':public_algae.CATALOG_PIN,'gfp_card_canonical_sha256':study.digest(gfp),'plan_fixture_sha256':PIN},'limit':LIMIT}
    data=_portable_numbers(data)
    study_store.screen_export(data);return data


def validate_view(view):
    study.fields(view,('stage','subject','metric','examples','scientist'))
    if view['stage'] not in STAGES or view['subject'] not in SUBJECTS or view['metric'] not in study.METRICS or type(view['examples']) is not bool or type(view['scientist']) is not bool:
        raise ValueError('Unsupported story presentation; no arbitrary data importer')
    return deepcopy(view)


def package(view):
    value={'schema_version':SCHEMA,'view':validate_view(view),'content':content(),'limit':LIMIT}
    value['sha256']=study.digest(value);study_store.screen_export(value);return value


def validate_package(value):
    if not isinstance(value,dict) or study.canonical(value)!=study.canonical(package(value.get('view'))):
        raise ValueError('Changed/corrupt research story or unqualified source data')
    return deepcopy(value)


class Session:
    def __init__(self):
        self.data=content();self.settings={'stage':'evidence','subject':'8-27','metric':'phosphate_uptake','examples':False,'scientist':False};self.revision=0;self.reopened=False

    def current(self):
        value={'view':deepcopy(self.settings),'revision':self.revision,'content_sha256':study.digest(self.data),'reopened':self.reopened}
        value['hash']=study.digest(value);return value

    def view(self):return {'current':self.current(),'content':deepcopy(self.data),'sources_read_only':True,'live_enabled':False}

    def present(self,view):
        self.settings=validate_view(view);self.revision+=1

    def open(self,value):
        valid=validate_package(value);self.settings=valid['view'];self.data=valid['content'];self.reopened=True;self.revision+=1

    def export(self):return package(self.settings)

    def readable(self):
        value=self.export();lines=['Traitweaver — scientific research story',SCHEMA,LIMIT,
            'Read-only source projection and deterministic descriptive arithmetic. No registered tool, model or laboratory execution. Presentation: '+study.canonical(self.settings),
            'Actual edited material ID: null; actual laboratory run ID: null; decision thresholds: null.',
            'Published within-study summaries (original mean, SE, n, units and basis):',study.canonical(value['content']['summaries']),
            'Reference lineage, not physical material custody:',study.canonical(value['content']['reference_chain']),
            'Proposed material records — NOT instantiated:',study.canonical(value['content']['planned_materials']),
            'Proposed measurement design — approved laboratory SOPs and decisions still required:']
        for card in value['content']['study_design']:
            lines += [card['id']+' — '+card['title'],'Question: '+card['question'],'Comparison: '+card['comparison'],
                'Controls: '+ '; '.join(card['controls']),'Readouts: '+ '; '.join(card['readouts']),
                'Independent units: '+card['independent_units'],'Required before run: '+ '; '.join(card['required_before_run']),
                'Completion: '+card['completion_check'],'Sources: '+', '.join(card['sources'])]
        lines += ['SYNTHETIC mathematical illustration, NOT experimental observations:',study.canonical(value['content']['synthetic_calculations']),
                  'Exact accepted content and source identities:',study.canonical(value)]
        return '\n'.join(lines)+'\n'
