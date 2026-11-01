"""Frozen public PSR1-associated reference annotation; offline derivation only.

Exact accessions, forward strand and standard genetic code are deliberately
bounded here. This is not an importer, target designer or database client.
"""
from copy import deepcopy
import hashlib
import re

from traitweaver import study
from traitweaver.study_store import screen_export

ROOT = study.APP_ROOT / 'data/public-algae/psr1-reference'
REQUIREMENTS_PIN = 'f35d305ded2aaccba921147c4c958d95d7563dc8e32d1312e04f72cb6a810248'
MANIFEST_PIN = '07060e0d0456daa36574552232ad1180dfb4efec4f7b93306c2d89adc4fe98e9'
CATALOG_PIN = '836c407af55da476d8b042df822249ccb9e83090b839366dd059f8a3a21e2e28'
LIMIT = ('Public reference annotation and offline sequence reconciliation only. '
         'No experimental splice support, intervention result or strain equivalence is established. '
         'No guide, edit site, construct or laboratory protocol is generated.')
PROTEIN = 'XP_001700553.1'
TRANSCRIPT = 'XM_001700501.2'
GENE = 'GeneID:5726104'


def _raw(name, pin):
    if name not in {'SOURCE_MANIFEST.json','reference.v2.json','evidence-needed/REQUIREMENTS.json','refseq_XP_001700553.1.gb',
                    'refseq_XM_001700501.2.gb','reference_gene_region.gb','assembly_report.txt','uniprot_Q9S807.fasta'}:
        raise ValueError('Unknown public reference file')
    path=ROOT/name
    if ROOT.is_symlink() or any(p.is_symlink() for p in (path.parent, ROOT.parent, ROOT.parent.parent)) or path.is_symlink() or not path.is_file() or path.stat().st_size>131072:
        raise ValueError('Public source missing, unsafe or oversized')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Pinned public source changed; no retrieval fallback')
    return raw


def manifest():
    return study.decode(_raw('SOURCE_MANIFEST.json',MANIFEST_PIN))


def source_file(name):
    """Closed allowlist; returned bytes are rechecked at every local read."""
    rows={s['file']:s for s in manifest()['sources']}
    if name not in rows:raise ValueError('Unknown public source file')
    return _raw(name,rows[name]['sha256'])


def _sequence(text):
    parts=text.split('\nORIGIN')
    if len(parts)!=2 or parts[1].count('//')!=1:raise ValueError('Unsupported GenBank sequence')
    return ''.join(re.findall('[A-Za-z]+',parts[1].split('//')[0])).upper()


def _feature(text,kind,qualifier):
    rows=re.findall(r'^     (\S+)\s+([^\n]+)\n(.*?)(?=^     \S|^ORIGIN)',text,re.M|re.S)
    hits=[(location,body) for key,location,body in rows if key==kind and qualifier in body]
    if len(hits)!=1:raise ValueError('Missing or ambiguous exact reference feature')
    return hits[0]


def _intervals(location):
    # Fail closed on partial/complement/remote coordinates in this one forward locus.
    if not re.fullmatch(r'(\d+\.\.\d+|join\(\d+\.\.\d+(?:,\d+\.\.\d+)+\))',location):
        raise ValueError('Unsupported reference coordinate expression')
    rows=[[int(a)-1,int(b)] for a,b in re.findall(r'(\d+)\.\.(\d+)',location)]
    if any(a<0 or a>=b for a,b in rows) or any(a[1]>b[0] for a,b in zip(rows,rows[1:])):
        raise ValueError('Invalid reference intervals')
    return rows


def _translate(dna):
    # NCBI standard table 1; ambiguity and internal stops are rejected.
    bases='TCAG'
    aa='FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG'
    table={a+b+c:v for (a,b,c),v in zip(((a,b,c) for a in bases for b in bases for c in bases),aa)}
    if len(dna)%3 or re.search('[^ACGT]',dna):raise ValueError('Unresolved reference translation')
    peptide=''.join(table[dna[i:i+3]] for i in range(0,len(dna),3))
    if not peptide.endswith('*') or '*' in peptide[:-1]:raise ValueError('Reference stop codon mismatch')
    return peptide[:-1]


def derive():
    """Reproduce the public-only catalog from five pinned primary record files."""
    from traitweaver import molecular
    m=manifest();texts={s['file']:source_file(s['file']).decode() for s in m['sources']}
    requirements=study.decode(_raw('evidence-needed/REQUIREMENTS.json',REQUIREMENTS_PIN))
    r=texts['refseq_XM_001700501.2.gb'];p=texts['refseq_XP_001700553.1.gb'];g=texts['reference_gene_region.gb'];assembly=texts['assembly_report.txt']
    for text,accession in ((r,TRANSCRIPT),(p,PROTEIN),(g,'NC_057015.1')):
        if re.search(r'^VERSION\s+'+re.escape(accession)+r'\b',text,re.M) is None:raise ValueError('Wrong versioned source')
        if 'CC-503 cw92 mt+' not in text:raise ValueError('Unresolved reference strain')
    if 'GCF_000002595.2' not in assembly or not any(line.split('\t')[2:7]==['12','Chromosome','CM008973.1','=','NC_057015.1'] for line in assembly.splitlines()):
        raise ValueError('Assembly chromosome identity mismatch')
    region=re.search(r'REGION:\s+(\d+)\.\.(\d+)',g)
    if region is None or region.groups()!=('724592','729993'):raise ValueError('Wrong extracted genomic region')
    offset=int(region[1])-1
    mrna_location,mrna_body=_feature(g,'mRNA','/transcript_id="'+TRANSCRIPT+'"')
    cds_location,cds_body=_feature(g,'CDS','/protein_id="'+PROTEIN+'"')
    rna_cds,rna_body=_feature(r,'CDS','/protein_id="'+PROTEIN+'"')
    gene_location,gene_body=_feature(g,'gene','/db_xref="GeneID:5726104"')
    for body in (mrna_body,cds_body,rna_body,gene_body):
        if '/locus_tag="CHLRE_12g495100v5"' not in body or '/db_xref="Phytozome:Cre12.g495100"' not in body:
            raise ValueError('Reference identity cross-reference mismatch')
    if '/codon_start=1' not in cds_body or '/codon_start=1' not in rna_body or 'accession '+TRANSCRIPT not in p:
        raise ValueError('Unresolved translation basis')
    genomic=_sequence(g);rna=_sequence(r);peptide=_sequence(p)
    uniprot=''.join(texts['uniprot_Q9S807.fasta'].splitlines()[1:]).upper()
    if not texts['uniprot_Q9S807.fasta'].startswith('>tr|Q9S807|'):raise ValueError('Expected unreviewed UniProt record')
    exons=_intervals(mrna_location);cds=_intervals(cds_location);rna_intervals=_intervals(rna_cds)
    spliced=''.join(genomic[a:b] for a,b in exons);coding=''.join(genomic[a:b] for a,b in cds)
    if spliced!=rna or rna_intervals!=[[767,3026]] or coding!=rna[767:3026]:raise ValueError('Genomic / transcript sequence disagreement')
    translated=_translate(coding)
    if translated!=peptide or uniprot!=peptide or (len(rna),len(genomic),len(peptide))!=(4772,5402,752):
        raise ValueError('Reference protein sequence disagreement')
    normalized=deepcopy(cds);normalized[-1][1]-=3  # Preserve annotated stop separately below.
    gene=_intervals(gene_location)[0]
    model={'coordinate_system':'0-based, half-open; chromosome NC_057015.1; transcript 5-prime order',
           'genes':[{'id':GENE,'label':'CHLRE_12g495100v5 / Cre12.g495100','assembly':'GCF_000002595.2','chromosome':'NC_057015.1','strand':'+','start':offset+gene[0],'end':offset+gene[1],'source_id':'reference_gene_region.gb'}],
           'exons':[],'transcripts':[{'id':TRANSCRIPT,'label':'One admitted reference transcript','gene_id':GENE,'exon_ids':[],'protein_id':PROTEIN}],
           'proteins':[{'id':PROTEIN,'label':'PSR1-associated reference; RefSeq product uncharacterized protein','length_aa':752}]}
    for i,(a,b) in enumerate(exons,1):
        spans=[[max(a,c),min(b,d)] for c,d in normalized if max(a,c)<min(b,d)]
        if len(spans)>1:raise ValueError('Unsupported coding feature')
        name='REF-exon-'+str(i);model['transcripts'][0]['exon_ids'].append(name)
        model['exons'].append({'id':name,'gene_id':GENE,'start':offset+a,'end':offset+b,'cds':None if not spans else [offset+v for v in spans[0]]})
    mapping=molecular.transcript_map(model,TRANSCRIPT)
    mapping['translation_status']='exact_offline_reference_sequence_reconciliation'
    mapping['limit']=LIMIT
    checks={'spliced_genomic_equals_refseq_transcript':spliced==rna,'translated_cds_equals_refseq_protein':translated==peptide,'unreviewed_uniprot_equals_refseq_protein':uniprot==peptide,
            'annotated_cds_length_nt':len(coding),'peptide_coding_length_nt':len(coding)-3,'terminal_stop_codon':coding[-3:],
            'stop_genomic_interval':[offset+cds[-1][1]-3,offset+cds[-1][1]],'stop_transcript_interval':[3023,3026],
            'annotated_cds_genomic_intervals':[[offset+a,offset+b] for a,b in cds],
            'sequence_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in {'genomic':genomic,'transcript':rna,'refseq_protein':peptide,'uniprot_protein':uniprot}.items()},
            'basis':'Standard genetic code 1, forward-strand joined CDS, codon_start=1; source CDS includes the terminal stop, peptide projection excludes it. Exact byte/sequence agreement is not experimental validation.'}
    claims=[{'id':'identity','statement':'XP_001700553.1 ↔ XM_001700501.2 ↔ GeneID:5726104 / CHLRE_12g495100v5 / Cre12.g495100.','files':['refseq_XP_001700553.1.gb','refseq_XM_001700501.2.gb','reference_gene_region.gb'],'locator':'DBSOURCE; gene/CDS/mRNA qualifiers; versioned accessions','kind':'reference_annotation'},
            {'id':'exons','statement':'One admitted forward-strand transcript has three annotated exons, 4772 transcript nt and a 752 aa reference protein.','files':['reference_gene_region.gb','refseq_XM_001700501.2.gb','refseq_XP_001700553.1.gb'],'locator':'mRNA join(1..1311,1549..2216,2610..5402); CDS joins; ORIGIN','kind':'annotation_and_offline_calculation'},
            {'id':'sequence','statement':'Spliced genomic sequence matches the transcript; translated CDS matches RefSeq protein; cached unreviewed Q9S807 has the same sequence.','files':['reference_gene_region.gb','refseq_XM_001700501.2.gb','refseq_XP_001700553.1.gb','uniprot_Q9S807.fasta'],'locator':'ORIGIN / FASTA; reproducible derive() checks and normalized sequence hashes','kind':'offline_sequence_reconciliation'},
            {'id':'context','statement':'Reference assembly v5.5 / GCF_000002595.2, chromosome NC_057015.1, strain CC-503 cw92 mt+. This does not establish equivalence to UVM4 study lines.','files':['assembly_report.txt','reference_gene_region.gb'],'locator':'Assembly header; chromosome 12 row; source strain qualifier','kind':'reference_context'}]
    result={'schema_version':'traitweaver.molecular_catalog.v2','case_id':'psr1-reference','role':'public_reference_annotation','title':'Public algae · PSR1-associated reference',
            'organism':'Chlamydomonas reinhardtii','strain':'CC-503 cw92 mt+','record_status':'RefSeq PROVISIONAL; product uncharacterized protein; UniProt Q9S807 unreviewed. Protein is conceptually translated, not experimental protein evidence.',
            'models':model,'transcript_maps':{TRANSCRIPT:mapping},'sources':m,'claims':claims,'checks':checks,'evidence_requirements':requirements,
            'goals':{k:{'label':v[0],'concept':v[1],'readout_question':v[2]} for k,v in molecular.GOALS.items()},
            'unknowns':['Alternative isoforms and splice-junction abundance are not admitted; one annotation is not proof of a single biological isoform.',
                        'Reference-strain identity is established for these files; UVM4 sequence, current assembly and exact paper construct equivalence remain unqualified.',
                        'PSR1 association is gene-level via the paper identifier; RefSeq retains an uncharacterized product label.',
                        'No guide specificity, suitable intervention, protein activity, causal effect or recovered-product phosphorus measurement is established.'],
            'limit':LIMIT}
    screen_export(result)
    return result


def catalog():
    saved=study.decode(_raw('reference.v2.json',CATALOG_PIN));derived=derive()
    if study.canonical(saved)!=study.canonical(derived):raise ValueError('Public reference derivation differs from admitted catalog')
    return saved


def initial_selection():
    return {'protein_id':PROTEIN,'transcript_id':None,'comparison_id':None,'goal':'increase_expression'}


def validate_selection(selection,bundle):
    from traitweaver import molecular
    study.fields(selection,('protein_id','transcript_id','comparison_id','goal'))
    if selection['protein_id']!=PROTEIN or selection['transcript_id'] not in (None,TRANSCRIPT) or selection['comparison_id'] is not None or selection['goal'] not in molecular.GOALS:
        raise ValueError('Unavailable public protein, transcript, comparison or objective')
    return deepcopy(selection)


def assess(selection,bundle):
    from traitweaver import molecular
    validate_selection(selection,bundle);goal=molecular.GOALS[selection['goal']]
    mapping=bundle['transcript_maps'].get(selection['transcript_id'])
    blockers=list(bundle['unknowns'])
    if mapping is None:blockers.insert(0,'Inspect and explicitly select the admitted reference transcript before recording a mapped identity.')
    return {'mapping_status':'explicit_public_reference_mapping' if mapping else 'selection_required','candidate_transcripts':[TRANSCRIPT],
            'mapping':deepcopy(mapping),'comparison':None,'synthetic':False,'planning_only':True,'biological_target_ready':False,'blockers':blockers,
            'concept':{'label':goal[1],'purpose':goal[2],'not_generated':['guide sequences','edit sites','constructs','laboratory protocol']},
            'measurement_plan':measurement_plan(selection),'limit':LIMIT}


def measurement_plan(selection):
    from traitweaver import molecular
    return {'question':molecular.GOALS[selection['goal']][0]+' for the PSR1-associated locus in a qualified algae context',
            'comparison':'A specified study strain and condition versus its own matched baseline; no CC-503-to-UVM4 performance comparison.',
            'controls':['Same strain, nutrient context and time basis','Researcher-qualified process control and baseline for any later intervention','Assay-specific reference and background controls; suitability unresolved'],
            'readouts':['Identity and reference-version concordance for the intended strain','Transcript identity and splice-junction support; alternative transcript abundance remains unknown','Protein abundance and separately qualified activity','Phosphate uptake, cellular phosphorus, recovered-product phosphorus and growth as separate measurements with units and time bases'],
            'independent_units':'Define independent biological units, replication and uncertainty; technical reads are not independent units.',
            'unresolved':['Which strain/reference and condition the question concerns','Whether the annotated transcript and other isoforms occur in that context','Whether protein abundance or activity mediates the endpoint','Assay qualification, suitable controls, decision thresholds and uncertainty'],
            'execution':'Questions and evidence requirements only. No executable laboratory procedure.'}
