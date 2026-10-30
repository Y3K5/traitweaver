"""One qualified, pinned GFP snapshot -> versioned card and local static viewer.

Standard library only. No server, retrieval, inference, credentials or fallback.
Saved reports must match the exact qualified v1 card, not arbitrary study data.
"""
import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

APP_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = APP_ROOT / 'data/gfp'
SCHEMA_PATH = APP_ROOT / 'schemas/protein-card.v1.schema.json'
TEMPLATE = Path(__file__).with_name('protein_card.html')
SCHEMA = 'traitweaver.protein_card.v1'
PINS = {
    'accession.json': '3e7b6b6539e3a604aa9a824a58a4e8b84bca4788c346ac6bdcc695a4864fcc35',
    'atlas-record.json': 'ef80ac9c0490014786868476916fb5614894be8872d5d8c0b5e292fb2bf7933a',
    'QUALIFICATION.json': 'd5d91fc33412f8517940e106e1b69801aa210fdf16f0200e3e8b9437321cdf61',
}
MAX_REPORT_BYTES = 256 * 1024


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def _json(raw):
    def invalid(_):
        raise ValueError('Nonfinite JSON value')
    try:
        return json.loads(raw, object_pairs_hook=_strict_object, parse_constant=invalid)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON report') from exc


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _load_inputs():
    records = {}
    for name, expected in PINS.items():
        path = FIXTURE_ROOT / name
        if path.is_symlink():
            raise ValueError('Qualified fixture must not be a symlink')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Qualified fixture bytes changed; no fallback is permitted')
        records[name] = _json(raw)
    return records


def _assemble(records):
    accession, atlas, qualified = (records[name] for name in PINS)
    if accession['sequence'] != atlas['sequence']:
        raise ValueError('Qualified protein identities do not match')
    return {
        'schema_version': SCHEMA,
        'card_id': 'GFP_P42212_ATLAS_F4AB4243',
        'identity': {
            'protein_name': accession['protein_name'], 'organism': accession['organism'],
            'gene_label': accession['gene'], 'uniprot_accession': accession['accession'],
            'atlas_accession': atlas['accession'], 'atlas_source': atlas['source'],
            'atlas_protein_hash_md5': atlas['protein_hash'], 'atlas_header': atlas['header'],
            'sequence_length': atlas['sequence_length'], 'sequence': atlas['sequence'],
            'sequence_sha256': qualified['identity']['sequence_sha256'], 'sequence_version': None,
        },
        'database_annotations': [{
            'id': 'DB_GFP_FUNCTION', 'role': 'database_annotation',
            'source_id': 'S_UNIPROT_P42212', 'locator': '/function',
            'value_state': 'reported', 'value': accession['function'],
            'claim_limit': 'Imported database annotation; independent assay and evidence-code verification not supplied here.',
        }],
        'model_predictions': [{
            'id': 'SAE_' + str(feature['feature_index']), 'role': 'model_prediction',
            'source_id': 'S_ATLAS_GFP', 'locator': '/sae_features/' + str(index),
            'value_state': 'reported', **deepcopy(feature),
            'claim_limit': 'Stored SAE activation and generic feature label; not experimentally demonstrated GFP function or a probability.',
        } for index, feature in enumerate(atlas['sae_features'])],
        'coordinate_convention': 'Original zero-based residue coordinates; interval-end convention not specified in qualification. No coordinate conversion applied.',
        'normalization': {'normalize_features': True, 'topk_features_requested': 3,
                          'limit': 'Three requested ranked features, not all active features. Original supplied normalized scores are retained.'},
        'unavailable': {key: atlas[key] for key in
                        ('pdb', 'ptm', 'mean_plddt', 'residues_plddt', 'cluster_rep_protein_hash')}
                        | {'model_version': None, 'generation_date': None},
        'experimental_evidence': [],
        'experimental_evidence_limit': 'No assay records or experimental evidence codes supplied in this snapshot; no assertion that the literature contains none.',
        'sources': [{
            'id': source_id, 'provider': provider, 'source_identifiers': identifiers,
            'snapshot': name, 'snapshot_sha256': PINS[name], **deepcopy(request),
        } for source_id, provider, identifiers, name, request in [
            ('S_UNIPROT_P42212', 'Biohub public UniProtKB resolver', ['P42212'],
             'accession.json', qualified['requests'][0]),
            ('S_ATLAS_GFP', 'Biohub ESM Atlas; UniParc source',
             [atlas['accession'], atlas['protein_hash']], 'atlas-record.json', qualified['requests'][1]),
        ]],
        'attribution': deepcopy(qualified['license_provenance']),
        'provenance': {'qualification_date': qualified['qualification_date'],
                       'qualification_snapshot': 'QUALIFICATION.json',
                       'qualification_sha256': PINS['QUALIFICATION.json'],
                       'folded_on_demand': atlas['folded_on_demand'],
                       'fold_on_miss': False,
                       'activation_data': deepcopy(qualified['activation_arrays']),
                       'activation_data_limit': 'Full sparse arrays remain in the unchanged qualified source snapshot; this brief contains their dimensions and entry counts only.'},
        'claim_limits': [qualified['decision']['limits'],
                         'This card is a reference snapshot, not a study, biological comparison, validated mechanism or experimental result.',
                         'Unavailable values remain null. No 3D structure or confidence estimate is generated.',
                         'Dataset/source license statements are retained by component; the API supplies no individual-record license declaration.'],
    }


def validate_card(card):
    """Validate the singleton v1 JSON Schema const contract, including JSON types.

    This release accepts exactly one qualified snapshot. Changing its scientific
    content, fields or roles requires a separately reviewed schema/snapshot.
    """
    if not isinstance(card, dict) or card.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported protein-card schema version')
    schema = _json(SCHEMA_PATH.read_bytes())
    if _canonical(card) != _canonical(schema['const']):
        raise ValueError('Report differs from the qualified GFP snapshot; altered or incomplete reports cannot be displayed')
    return None


def build_card():
    card = _assemble(_load_inputs())
    validate_card(card)
    return card


def open_report(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Saved report must not be a symlink')
    with path.open('rb') as handle:
        raw = handle.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Saved report exceeds the supported size')
    card = _json(raw)
    validate_card(card)
    return card


def readable(card):
    validate_card(card)
    identity = card['identity']
    lines = ['Traitweaver — offline GFP protein card', 'Schema: ' + SCHEMA, '', 'GFP identity']
    for label, key in [('Protein', 'protein_name'), ('Organism', 'organism'), ('Gene label (database)', 'gene_label'),
                       ('UniProtKB', 'uniprot_accession'), ('Atlas accession', 'atlas_accession'),
                       ('Atlas source', 'atlas_source'), ('Atlas sequence MD5', 'atlas_protein_hash_md5'),
                       ('Original Atlas header', 'atlas_header'), ('Sequence length', 'sequence_length'),
                       ('Sequence SHA-256', 'sequence_sha256')]:
        lines.append(label + ': ' + str(identity[key]))
    lines += ['Sequence version: Unavailable (null)', 'Original sequence:', identity['sequence'], '', 'Database annotation']
    for annotation in card['database_annotations']:
        lines += ['Role: ' + annotation['role'], annotation['value'],
                  'Source: ' + annotation['source_id'] + ' · ' + annotation['locator'], annotation['claim_limit'], '']
    lines += ['Three supplied SAE features — model predictions', card['coordinate_convention']]
    for feature in card['model_predictions']:
        lines += ['', str(feature['feature_index']) + ' — ' + feature['label'],
                  'Role: ' + feature['role'], 'Original score: ' + str(feature['value']), feature['description']]
        for region in feature['residue_regions']:
            lines.append('Original coordinates: start ' + str(region['start']) + '; end ' + str(region['end'])
                         + '; peak residue ' + str(region['peak_residue']) + '; mean activation ' + str(region['mean_activation']))
        lines += ['Source: ' + feature['source_id'] + ' · ' + feature['locator'], feature['claim_limit']]
    lines += ['', 'Unavailable in saved record']
    for key in card['unavailable']:
        lines.append(key + ': Unavailable (null)')
    lines += ['', 'Experimental evidence', card['experimental_evidence_limit'], '', 'Sources and identifiers']
    for source in card['sources']:
        lines += ['', source['id'] + ' — ' + source['provider'], 'Identifiers: ' + ', '.join(source['source_identifiers']),
                  'Original retrieval: ' + source['http_date'], source['url'],
                  'Saved snapshot: ' + source['snapshot'], 'Snapshot SHA-256: ' + source['snapshot_sha256']]
    lines += ['', 'Component attribution and licenses']
    for label, key in [('Biohub-generated Atlas data', 'atlas_generated_data'), ('Sequences / All Data collections', 'sequences_and_all_data_collections'),
                       ('Upstream UniParc', 'upstream_uniparc'), ('License source', 'source'), ('Attribution limits', 'scope_limit')]:
        lines.append(label + ': ' + card['attribution'][key])
    lines += ['', 'Score normalization', json.dumps(card['normalization'], ensure_ascii=False),
              '', 'Saved-record provenance', json.dumps(card['provenance'], ensure_ascii=False), '', 'Claim limits']
    lines.extend('- ' + limit for limit in card['claim_limits'])
    return '\n'.join(lines) + '\n'


def render_html(card, saved=False):
    validate_card(card)
    payload = json.dumps(card, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    template = TEMPLATE.read_text(encoding='utf-8')
    text_payload = json.dumps(readable(card), ensure_ascii=False).replace('<', '\\u003c')
    document = template.replace('/*CARD_DATA*/', payload).replace('/*SAVED_MODE*/', 'true' if saved else 'false').replace('/*READABLE_TEXT*/', text_payload)
    script = document.split('<script>', 1)[1].split('</script>', 1)[0]
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return document.replace('@@SCRIPT_HASH@@', script_hash)


def export_bundle(card, destination, saved=False):
    validate_card(card)
    payloads = {'protein-card.json': json.dumps(card, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                'protein-card.txt': readable(card), 'index.html': render_html(card, saved)}
    target = Path(destination)
    resolved = target.resolve()
    if resolved == APP_ROOT or APP_ROOT in resolved.parents:
        raise ValueError('Choose a fresh output directory outside the application tree')
    if target.is_symlink() or target.exists():
        raise ValueError('Output directory exists; nothing was overwritten')
    target.mkdir()
    written = []
    try:
        for name, content in payloads.items():
            path = target / name
            with path.open('x', encoding='utf-8') as handle:
                written.append(path)
                handle.write(content)
    except OSError:
        for path in written:
            path.unlink()
        target.rmdir()
        raise
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open the qualified offline GFP protein card. No server or network.')
    parser.add_argument('--output-dir', type=Path, help='Fresh directory outside the app; parent must exist')
    parser.add_argument('--report', type=Path, help='Display an explicitly selected saved protein-card JSON; does not restore a study')
    args = parser.parse_args(argv)
    try:
        card = open_report(args.report) if args.report else build_card()
        output = args.output_dir
        if output is None:
            output = Path(tempfile.mkdtemp(prefix='traitweaver-gfp-')) / 'card'
        target = export_bundle(card, output, saved=args.report is not None)
        print('Open this local page: ' + (target / 'index.html').resolve().as_uri())
        print('Saved protein-card.json and protein-card.txt alongside it.')
        print('Viewing a saved report; no study restored.' if args.report else 'Using the pinned qualified GFP fixture only.')
    except OSError:
        parser.exit(1, 'Could not read the selected local files or write the fresh output directory.\n')
    except (ValueError, TypeError) as exc:
        parser.exit(1, 'Protein card stopped: ' + str(exc) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
