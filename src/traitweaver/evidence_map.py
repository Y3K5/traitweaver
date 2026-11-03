"""Read-only graph of an already admitted intelligence catalog.

This projection neither admits sources nor runs checks. It is rebuilt from the
unchanged catalog on reopen; graph navigation is never a saved study action.
"""
from copy import deepcopy

from traitweaver import study


def project(bundle, endpoint):
    literature = bundle['literature']
    nodes, edges = [], []

    def node(identifier, kind, title, role, record):
        nodes.append({'id': identifier, 'kind': kind, 'label': title,
                      'role': role, 'record': deepcopy(record)})

    def edge(origin, target, relation, role, provenance):
        edges.append({'from': origin, 'to': target, 'relation': relation,
                      'role': role, 'provenance': deepcopy(provenance)})

    sources = {s['id']: s for s in literature['sources']}
    for s in sources.values():
        node(s['id'], 'source', s['title'], 'published_source', s)

    endpoints = list(dict.fromkeys([*study.ENDPOINTS,
                                   *(e['endpoint'] for e in literature['evidence'])]))
    if endpoint not in study.ENDPOINTS:
        raise ValueError('Unregistered review endpoint')
    for name in endpoints:
        rows = [e for e in literature['evidence'] if e['endpoint'] == name]
        endpoint_id = 'endpoint:' + name
        node(endpoint_id, 'endpoint', name.replace('_', ' '), 'research_endpoint', {
            'endpoint': name, 'observation_count': len(rows),
            'numeric_record_count': sum(type(e['value']) in (int, float) for e in rows),
            'scope': 'Admitted catalog only; no literature-wide absence claim.'})
        if not rows:
            gap_id = 'gap:' + name
            gap = {'endpoint': name, 'value': None, 'admitted_record_count': 0,
                   'statement': 'No observation for this endpoint is admitted. '
                                'Zero records is not a measured zero effect.',
                   'locator': 'intelligence catalog / literature / evidence',
                   'source_digests': bundle['source_digests']}
            node(gap_id, 'gap', 'Missing endpoint evidence', 'curation_gap', gap)
            edge(endpoint_id, gap_id, 'missing_admitted_evidence', 'curation_gap', gap)
        for e in rows:
            if e['source_id'] not in sources:
                raise ValueError('Observation source is unavailable')
            subject = e.get('subject') or ', '.join(e.get('subjects', []))
            node(e['id'], 'observation', subject or e['id'], e['role'], e)
            trace = {'source_id': e['source_id'], 'record_id': e['id'],
                     'locator': e['locator'], 'claim_limit': e['claim_limit']}
            edge(endpoint_id, e['id'], 'documented_by_observation', e['role'], trace)
            edge(e['id'], e['source_id'], 'reported_in', e['role'], trace)

    reference = bundle['reference']
    for candidate in bundle['candidates']:
        node(candidate['id'], 'candidate', candidate['label'], candidate['role'], candidate)
        for claim_id in candidate['citations']:
            claim = bundle['claims'][claim_id]
            if claim.get('source_id') in sources:
                edge(candidate['id'], claim['source_id'], 'publication_association',
                     claim['role'], {'claim_id': claim_id, **claim})
        gap = {'necessity': candidate['necessity'], 'sufficiency': candidate['sufficiency'],
               'causal_recovery_effect': candidate['causal_recovery_effect'],
               'reference_status': bundle['reference_status'],
               'statement': 'Necessity, sufficiency and causal recovery remain unknown. '
                            'UVM4 study lines are not sequence-qualified by a CC-503 reference.',
               'locator': 'intelligence catalog / candidates; C_STRAIN_CONTEXT'}
        gap_id = 'gap:' + candidate['id']
        node(gap_id, 'gap', 'Candidate qualification gaps', 'curation_gap', gap)
        edge(candidate['id'], gap_id, 'has_unresolved_qualification', 'curation_gap', gap)

    if reference:
        records = {s['file']: s for s in reference['sources']['sources']}
        for filename, s in records.items():
            node('reference-source:' + filename, 'reference_source', s['title'], s['role'], s)
        # The association is gene-level only. No edge asserts a UVM4 sequence or
        # protein match, a necessary mechanism, or a recovered-product outcome.
        identity = next(c for c in reference['claims'] if c['id'] == 'identity')
        context = next(c for c in reference['claims'] if c['id'] == 'context')
        sequence = next(c for c in reference['claims'] if c['id'] == 'sequence')
        publication = reference['sources']['publication_identity']
        node('reference:context', 'reference_context', reference['strain'], 'reference_context',
             {'organism': reference['organism'], 'strain': reference['strain'], 'claim': context})
        for filename in context['files']:
            edge('reference:context', 'reference-source:' + filename, 'context_documented_in',
                 context['kind'], {'claim': context, 'source': records[filename]})
        for c in bundle['candidates']:
            for field, kind in [('gene_id', 'gene'), ('transcript_id', 'transcript'), ('protein_id', 'protein')]:
                if not c[field]:
                    raise ValueError('Qualified reference identity is unavailable')
                identifier = 'reference:' + c[field]
                node(identifier, kind, c[field], 'reference_annotation', {
                    'organism': reference['organism'], 'strain': reference['strain'],
                    'record_status': reference['record_status'],
                    'identity': identity, 'context': context})
                edge(identifier, 'reference:context', 'reference_context', context['kind'], context)
                for filename in identity['files']:
                    if filename not in records:
                        raise ValueError('Reference identity source is unavailable')
                    edge(identifier, 'reference-source:' + filename, 'annotated_in',
                         identity['kind'], {'claim': identity, 'source': records[filename]})
            edge(c['id'], 'reference:' + c['gene_id'], 'gene_level_identity_association',
                 'identity_association', publication)
            edge('reference:' + c['transcript_id'], 'reference:' + c['gene_id'],
                 'annotated_at', identity['kind'], identity)
            edge('reference:' + c['protein_id'], 'reference:' + c['transcript_id'],
                 'reference_translation_of', identity['kind'], identity)
            edge('reference:' + c['protein_id'], 'reference-source:uniprot_Q9S807.fasta',
                 'offline_sequence_agreement', sequence['kind'], sequence)

    return {'projection_version': 'traitweaver.intelligence_evidence_map.v1',
            'catalog_sha256': study.digest(bundle), 'source_digests': deepcopy(bundle['source_digests']),
            'scope_endpoint': endpoint, 'nodes': nodes, 'edges': edges,
            'limit': 'Read-only source projection. Edges express the stated evidence role; '
                     'they do not establish causality, transfer or biological validation.'}
