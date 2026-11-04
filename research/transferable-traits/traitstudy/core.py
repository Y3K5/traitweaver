"""Source-bound records and append-only review in SQLite, using only stdlib.

Structural checks establish consistency, never source entailment or biology.
There is deliberately no HTTP client, credential handling, or provider execution.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    raw = value if isinstance(value, bytes) else canonical(value).encode()
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 20000, name + ' must be nonempty text')
    return value


def fields(obj, expected, name):
    require(isinstance(obj, dict) and set(obj) == set(expected.split()), name + ' has missing or extra fields')


def link(value):
    parsed = urlsplit(value)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password,
            'Source URL must be HTTPS without credentials')
    require(not parsed.query and not parsed.fragment, 'Use a canonical source URL; put source locations in locator')


def source_key(source):
    ids = source['identifiers']
    if ids.get('doi'):
        doi = ids['doi'].strip().lower()
        doi = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', doi)
        require(re.fullmatch(r'10\.\d{4,9}/\S+', doi), 'Invalid DOI')
        return 'doi:' + doi
    if ids.get('pmid'):
        require(re.fullmatch(r'\d+', str(ids['pmid'])), 'Invalid PMID')
        return 'pmid:' + str(ids['pmid'])
    return 'url:' + source['url'].rstrip('/')


SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, work_key TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 role TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS source_work ON sources(work_key);
CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(
 id TEXT PRIMARY KEY, identity_key TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 trait TEXT NOT NULL, donor_id TEXT NOT NULL REFERENCES entities(id),
 recipient_id TEXT NOT NULL REFERENCES entities(id), study_key TEXT NOT NULL,
 scope TEXT NOT NULL, evidence_type TEXT NOT NULL, synthetic INTEGER NOT NULL,
 data TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS observation_identity ON observations(identity_key);
CREATE INDEX IF NOT EXISTS observation_trait ON observations(trait);
CREATE TABLE IF NOT EXISTS observation_components(
 observation_id TEXT REFERENCES observations(id), component_id TEXT REFERENCES entities(id),
 PRIMARY KEY(observation_id,component_id));
CREATE TABLE IF NOT EXISTS citations(
 observation_id TEXT REFERENCES observations(id), source_id TEXT REFERENCES sources(id),
 locator TEXT NOT NULL, claim TEXT NOT NULL,
 PRIMARY KEY(observation_id,source_id,locator,claim));
CREATE TABLE IF NOT EXISTS dependencies(
 observation_id TEXT REFERENCES observations(id), dependency_key TEXT NOT NULL,
 status TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(observation_id,dependency_key));
CREATE TABLE IF NOT EXISTS category_assignments(
 observation_id TEXT REFERENCES observations(id), scheme TEXT NOT NULL, category TEXT NOT NULL,
 provenance TEXT NOT NULL, PRIMARY KEY(observation_id,scheme,category));
CREATE TABLE IF NOT EXISTS groups_(id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS group_members(
 group_id TEXT REFERENCES groups_(id), observation_id TEXT REFERENCES observations(id),
 PRIMARY KEY(group_id,observation_id));
CREATE TABLE IF NOT EXISTS reviews(
 id INTEGER PRIMARY KEY AUTOINCREMENT, observation_id TEXT REFERENCES observations(id),
 record_sha256 TEXT NOT NULL, reviewer TEXT NOT NULL, decision TEXT NOT NULL,
 note TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, input_sha256 TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL, available_at REAL NOT NULL DEFAULT 0,
 lease_until REAL, lease_token TEXT, checkpoint TEXT, error_code TEXT);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id),
 state TEXT NOT NULL, details TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budgets(
 id TEXT PRIMARY KEY, ceiling_micro INTEGER NOT NULL, max_calls INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reservations(
 id TEXT PRIMARY KEY, budget_id TEXT REFERENCES budgets(id), amount_micro INTEGER NOT NULL,
 state TEXT NOT NULL, actual_micro INTEGER, details TEXT NOT NULL);
'''


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')

    def close(self):
        self.db.close()

    @contextmanager
    def atomic(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def add_source(self, s):
        fields(s, 'title url identifiers role retrieved_utc access license snapshot_sha256 content origin', 'source')
        text(s['title'], 'title'); text(s['retrieved_utc'], 'retrieved_utc'); link(s['url'])
        require(s['role'] in ('primary_study', 'reference_annotation', 'synthetic_fixture'), 'Invalid source role')
        require(s['origin'] in ('human_admitted', 'synthetic_fixture'), 'Unknown source origin')
        require((s['role'] == 'synthetic_fixture') == (s['origin'] == 'synthetic_fixture'), 'Mixed synthetic source provenance')
        require(isinstance(s['identifiers'], dict) and set(s['identifiers']) <= {'doi', 'pmid', 'pmcid', 'accession', 'version'}, 'Invalid identifiers')
        require(s['access'] in ('open_access', 'metadata_only', 'licensed_local', 'synthetic'), 'Invalid access')
        require((s['access'] == 'synthetic') == (s['role'] == 'synthetic_fixture'), 'Invalid synthetic access')
        if s['content'] is not None:
            text(s['content'], 'content')
            require(s['access'] != 'metadata_only' and bool(s['license']), 'Text needs lawful access and license note')
            require(s['snapshot_sha256'] == digest(s['content'].encode()), 'Source snapshot hash mismatch')
        else:
            require(s['snapshot_sha256'] is None, 'Absent snapshot cannot have a hash')
        key, sha = source_key(s), digest(s)
        sid = 'src_' + sha
        with self.atomic():
            self.db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?)',
                            (sid, key, sha, s['role'], canonical(s), utc()))
        return sid

    def source(self, sid):
        r = self.db.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
        require(r is not None, 'Source is not admitted')
        return json.loads(r['data'])

    def _entity(self, kind, data):
        if kind == 'organism':
            fields(data, 'name taxonomy_id strain context', 'organism')
            text(data['name'], 'organism name')
        else:
            fields(data, 'name kind accession version gene protein identity_status', 'component')
            text(data['name'], 'component name')
            require(data['kind'] in ('gene', 'protein', 'pathway', 'unknown'), 'Component kind')
            require(data['identity_status'] in ('source_reported', 'reference_only', 'unresolved', 'synthetic'), 'Component identity')
        eid = kind + '_' + digest(data)
        self.db.execute('INSERT OR IGNORE INTO entities VALUES(?,?,?)', (eid, kind, canonical(data)))
        return eid

    def add_observation(self, o):
        fields(o, 'trait donor recipient components study_key condition_key evidence_type endpoint dependencies uncertainty negative_results transfer_method stability citations category_assignments provenance', 'observation')
        for k in ('trait', 'study_key', 'condition_key'):
            text(o[k], k)
        fields(o['provenance'], 'origin workbook_ref model_run', 'provenance')
        origin = o['provenance']['origin']
        require(origin in ('human_curated', 'model_candidate', 'synthetic_fixture'), 'Invalid origin')
        synthetic = origin == 'synthetic_fixture'
        require(o['evidence_type'] in ('measured', 'negative', 'mixed', 'qualitative', 'unknown'), 'Invalid evidence type')
        e = o['endpoint']
        fields(e, 'name scope value units uncertainty n control timepoint interpretation_limit', 'endpoint')
        text(e['name'], 'endpoint name'); text(e['interpretation_limit'], 'interpretation limit')
        require(e['scope'] in ('extracted_enzyme', 'intact_cell', 'whole_organism', 'material', 'unknown'), 'Invalid endpoint scope')
        require(e['value'] is None or (type(e['value']) in (int, float) and math.isfinite(e['value'])), 'Invalid endpoint value')
        require(e['value'] is None or bool(e['units']), 'Numeric values require units')
        require(e['n'] is None or (type(e['n']) is int and e['n'] > 0), 'n must be positive or null')
        for k in ('components', 'citations', 'dependencies', 'uncertainty', 'category_assignments'):
            require(isinstance(o[k], list), k + ' must be a list')
        require(bool(o['components']) and bool(o['citations']) and bool(o['uncertainty']), 'Components, citations and uncertainty required')
        require(o['negative_results'] is None or isinstance(o['negative_results'], list), 'Negative results must be null or a list')
        require(o['evidence_type'] != 'negative' or bool(o['negative_results']), 'Negative evidence requires reported negative result')
        for c in o['citations']:
            fields(c, 'source_id locator supports', 'citation')
            text(c['locator'], 'citation locator'); text(c['supports'], 'citation supports')
            source = self.source(c['source_id'])
            require((source['role'] == 'synthetic_fixture') == synthetic, 'Mixed synthetic and real evidence')
        primary = [self.source(c['source_id']) for c in o['citations']
                   if self.source(c['source_id'])['role'] in ('primary_study', 'synthetic_fixture')]
        require(primary, 'Transfer observation needs a primary study; an annotation alone is insufficient')
        for d in o['dependencies']:
            fields(d, 'name status statement citations', 'dependency')
            text(d['name'], 'dependency name')
            require(d['status'] in ('reported', 'unknown', 'hypothesis'), 'Dependency status')
            require(isinstance(d['citations'], list), 'Dependency citations')
            require(d['status'] != 'reported' or bool(d['citations']), 'Reported dependency requires citation')
            require(all(x in o['citations'] for x in d['citations']), 'Dependency cites outside observation')
        for a in o['category_assignments']:
            fields(a, 'scheme category provenance', 'category')
            require(a['scheme'] in ('workbook_human_v1', 'app_capabilities_v1', 'muse_proposed_v1', 'synthetic_test_v1'), 'Category scheme')
            text(a['category'], 'category'); text(a['provenance'], 'category provenance')
            require(not synthetic or a['scheme'] == 'synthetic_test_v1', 'Synthetic categories cannot populate real schemes')
        sha = digest(o)
        oid = 'obs_' + sha
        # Semantic identity includes exact primary work, donor, recipient, component,
        # condition and endpoint; changed claims become revisions, never overwrites.
        identity = digest([sorted(source_key(s) for s in primary), o['donor'], o['recipient'],
                           sorted(digest(c) for c in o['components']), o['condition_key'], e['name'], e['scope']])
        with self.atomic():
            donor = self._entity('organism', o['donor']); recipient = self._entity('organism', o['recipient'])
            components = [self._entity('component', c) for c in o['components']]
            self.db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                            (oid, identity, sha, o['trait'], donor, recipient, o['study_key'], e['scope'],
                             o['evidence_type'], int(synthetic), canonical(o), utc()))
            for cid in components:
                self.db.execute('INSERT OR IGNORE INTO observation_components VALUES(?,?)', (oid, cid))
            for c in o['citations']:
                self.db.execute('INSERT OR IGNORE INTO citations VALUES(?,?,?,?)',
                                (oid, c['source_id'], c['locator'], c['supports']))
            for d in o['dependencies']:
                self.db.execute('INSERT OR IGNORE INTO dependencies VALUES(?,?,?,?)', (oid, digest(d), d['status'], canonical(d)))
            for a in o['category_assignments']:
                self.db.execute('INSERT OR IGNORE INTO category_assignments VALUES(?,?,?,?)',
                                (oid, a['scheme'], a['category'], a['provenance']))
        return oid

    def observation(self, oid):
        row = self.db.execute('SELECT data FROM observations WHERE id=?', (oid,)).fetchone()
        require(row is not None, 'Unknown observation')
        return json.loads(row['data'])

    def review(self, oid, expected_sha256, reviewer, decision, note):
        require(decision in ('source_checked', 'needs_correction', 'rejected'), 'Invalid review decision')
        text(reviewer, 'reviewer'); text(note, 'review note')
        with self.atomic():
            o = self.observation(oid)
            require(digest(o) == expected_sha256, 'Review is stale')
            require(o['provenance']['origin'] != 'synthetic_fixture' or decision != 'source_checked',
                    'Synthetic evidence cannot receive scientific source-check approval')
            self.db.execute('INSERT INTO reviews(observation_id,record_sha256,reviewer,decision,note,created) VALUES(?,?,?,?,?,?)',
                            (oid, expected_sha256, reviewer, decision, note, utc()))

    def add_group(self, g):
        fields(g, 'name kind members study_key recipient condition_key demonstration uncertainty provenance', 'group')
        require(g['kind'] in ('demonstrated_stack', 'proposed_pairing'), 'Group kind')
        require(isinstance(g['members'], list) and len(set(g['members'])) >= 2, 'Group needs two distinct observations')
        members = [self.observation(x) for x in g['members']]
        synthetic = all(o['provenance']['origin'] == 'synthetic_fixture' for o in members)
        require(synthetic or all(o['provenance']['origin'] != 'synthetic_fixture' for o in members), 'Mixed synthetic group')
        require(g['provenance'] == ('synthetic_fixture' if synthetic else 'human_authored'), 'Group provenance')
        require(bool(g['uncertainty']), 'Group uncertainty required')
        if g['kind'] == 'demonstrated_stack':
            require(all(o['study_key'] == g['study_key'] and o['recipient'] == g['recipient'] and
                        o['condition_key'] == g['condition_key'] for o in members), 'Stack must share study, recipient and condition')
            d = g['demonstration']
            fields(d, 'source_id locator supports', 'stack demonstration')
            text(d['locator'], 'demonstration locator'); text(d['supports'], 'joint endpoint evidence')
            source = self.source(d['source_id'])
            require(source['role'] == ('synthetic_fixture' if synthetic else 'primary_study'), 'Primary stack evidence required')
            require(all(d['source_id'] in [c['source_id'] for c in o['citations']] for o in members), 'Stack citation must support every member')
        else:
            require(g['demonstration'] is None, 'Proposed group cannot claim demonstration')
        gid = 'group_' + digest(g)
        with self.atomic():
            self.db.execute('INSERT OR IGNORE INTO groups_ VALUES(?,?,?)', (gid, g['kind'], canonical(g)))
            for oid in g['members']:
                self.db.execute('INSERT OR IGNORE INTO group_members VALUES(?,?)', (gid, oid))
        return gid

    def export(self, query=''):
        # Literal, parameter-bound search: '%' and '_' are not wildcard instructions.
        query = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        rows = self.db.execute("SELECT * FROM observations WHERE data LIKE ? ESCAPE '\\' ORDER BY trait,id", ('%'+query+'%',)).fetchall()
        observations = []
        for r in rows:
            reviews = [dict(x) for x in self.db.execute('SELECT * FROM reviews WHERE observation_id=? ORDER BY id', (r['id'],))]
            observations.append({'id': r['id'], 'sha256': r['sha256'], 'identity_key': r['identity_key'],
                                 'record': json.loads(r['data']), 'review_status': reviews[-1]['decision'] if reviews else 'unreviewed', 'reviews': reviews})
        return {'schema': 'traitweaver.cloud-study.v1', 'mode': 'offline',
                'biological_validation': 'not_established', 'model_calls': 0,
                'observations': observations,
                'sources': [{'id': r['id'], 'sha256': r['sha256'], 'record': json.loads(r['data'])}
                            for r in self.db.execute('SELECT * FROM sources ORDER BY id')],
                'groups': [{'id': r['id'], 'record': json.loads(r['data'])} for r in self.db.execute('SELECT * FROM groups_ ORDER BY id')],
                'queue': [dict(r) for r in self.db.execute('SELECT id,kind,state,attempts,checkpoint,error_code FROM jobs ORDER BY id')]}
