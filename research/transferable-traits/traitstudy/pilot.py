"""Authored synthetic test fixtures; no biological observations are asserted."""
from copy import deepcopy
from .core import digest

TARGETS = [
    ('TW004', 'GFP', 'Single reporter; distinguish reference identity from measured expression'),
    ('TW009', 'Firefly light', 'Check substrate and host dependencies'),
    ('TW002', 'Fungal glow', 'Check multi-component pathway and host context'),
    ('TW037', 'PETase', 'Separate extracted-enzyme activity from intact-organism function'),
    ('TW020', 'Golden Rice', 'Separate pathway evidence, tissue endpoint and downstream health claims'),
    ('TW044', 'Cellulose-to-ethanol yeast', 'Check jointly measured functions and substrate boundaries'),
]


def trail_plan():
    return [{'workbook_id':i,'topic':n,'review_question':q,'status':'blocked_workbook_not_materialized',
             'source':'parent-provided target list; workbook row not inspected', 'observation':None,
             'scientific_review':'pending'} for i,n,q in TARGETS]


def synthetic_fixtures(store):
    content = ('SYNTHETIC SOFTWARE FIXTURE. Invented entity labels and test-only endpoints. '
               'Panel A: two signals measured jointly in fictional recipient R. '
               'Panel B: extracted enzyme measurement does not establish intact organism function. '
               'Panel C: unknown and measured zero are distinct. No biological result.')
    sid = store.add_source({'title':'Synthetic software fixture, not a paper',
        'url':'https://example.invalid/traitstudy/synthetic-fixture', 'identifiers':{},
        'role':'synthetic_fixture','retrieved_utc':'2026-11-04T00:00:00+00:00',
        'access':'synthetic','license':'Original synthetic fixture; MIT',
        'snapshot_sha256':digest(content.encode()),'content':content,'origin':'synthetic_fixture'})
    fixtures=[]
    labels=['Synthetic reporter','Synthetic substrate-dependent light','Synthetic pathway light',
            'Synthetic extracted enzyme','Synthetic material endpoint','Synthetic joint processing']
    for index, label in enumerate(labels):
        scope=['intact_cell','whole_organism','whole_organism','extracted_enzyme','material','intact_cell'][index]
        citation={'source_id':sid,'locator':'Synthetic fixture / panel '+('A' if index<2 else 'B' if index==3 else 'C'),
                  'supports':'Test-only endpoint; no biological evidence'}
        record={'trait':label,
            'donor':{'name':'Fictional donor D','taxonomy_id':None,'strain':None,'context':'synthetic'},
            'recipient':{'name':'Fictional recipient R','taxonomy_id':None,'strain':None,'context':'synthetic'},
            'components':[{'name':'Fictional component '+str(index+1),'kind':'protein','accession':None,
                           'version':None,'gene':None,'protein':None,'identity_status':'synthetic'}],
            'study_key':'synthetic_study','condition_key':'synthetic_condition',
            'evidence_type':'negative' if index==4 else 'qualitative',
            'endpoint':{'name':'Test endpoint '+str(index+1),'scope':scope,'value':0 if index==4 else None,
                        'units':'arbitrary test units' if index==4 else None,'uncertainty':None,'n':None,
                        'control':None,'timepoint':None,'interpretation_limit':'Synthetic only; no extrapolation beyond this assay scope.'},
            'dependencies':[{'name':'Host compatibility','status':'unknown','statement':'Not established','citations':[]}],
            'uncertainty':['Synthetic fixture only','Source entailment has not been assessed'],
            'negative_results':['Synthetic measured zero; not a biological result'] if index==4 else None,
            'transfer_method':None,'stability':None,'citations':[citation],
            'category_assignments':[{'scheme':'synthetic_test_v1','category':'Test group '+str(index//2+1),'provenance':'authored_fixture'}],
            'provenance':{'origin':'synthetic_fixture','workbook_ref':None,'model_run':None}}
        fixtures.append(record)
    return fixtures


def groups(store, ids):
    first=store.observation(ids[0])
    common={'members':ids[:2], 'study_key':first['study_key'],'recipient':first['recipient'],
            'condition_key':first['condition_key'],'uncertainty':['Synthetic validation fixture, not biology'],
            'provenance':'synthetic_fixture'}
    stack={**common,'name':'Synthetic co-measured stack','kind':'demonstrated_stack',
           'demonstration':{**first['citations'][0], 'supports':'Synthetic panel A reports both fictional signals together'}}
    store.add_group(stack)
    proposed={**common,'name':'Synthetic untested pairing','kind':'proposed_pairing','members':ids[2:4],
              'demonstration':None,'study_key':None,'condition_key':None,'recipient':None}
    store.add_group(proposed)
