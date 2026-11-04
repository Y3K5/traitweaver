"""Durable work leases and conservative accounting. No automatic paid retries."""
import json
import time
import uuid
from .core import canonical, digest, require, utc


class Queue:
    def __init__(self, store):
        self.store, self.db = store, store.db

    def event(self, jid, state, details):
        self.db.execute('INSERT INTO events(job_id,state,details,created) VALUES(?,?,?,?)',
                        (jid, state, canonical(details), utc()))

    def enqueue(self, kind, payload, max_attempts=3):
        require(kind in ('offline_extract', 'source_retrieval', 'human_review', 'model_request'), 'Unknown job kind')
        require(type(max_attempts) is int and 1 <= max_attempts <= 3, 'At most three local attempts')
        require(kind != 'model_request' or max_attempts == 1, 'Paid requests cannot automatically retry')
        sha = digest(payload); jid = 'job_' + digest([kind, sha])
        with self.store.atomic():
            cursor = self.db.execute('INSERT OR IGNORE INTO jobs(id,kind,input_sha256,payload,state,max_attempts) VALUES(?,?,?,?,?,?)',
                                    (jid, kind, sha, canonical(payload), 'pending', max_attempts))
            if cursor.rowcount:
                self.event(jid, 'pending', {'input_sha256': sha})
        return jid

    def claim(self, now=None, lease_seconds=60):
        now = time.time() if now is None else now
        require(0 < lease_seconds <= 300, 'Lease must be bounded')
        with self.store.atomic():
            # Any expired model request is uncertain, even if the crash happened
            # before send. An operator must reconcile it; never infer no charge.
            expired = self.db.execute("SELECT * FROM jobs WHERE state='running' AND lease_until<=?", (now,)).fetchall()
            for r in expired:
                state = 'uncertain' if r['kind'] == 'model_request' else ('failed' if r['attempts'] >= r['max_attempts'] else 'pending')
                self.db.execute('UPDATE jobs SET state=?,lease_token=NULL,lease_until=NULL,error_code=? WHERE id=?',
                                (state, 'lease_expired', r['id']))
                self.event(r['id'], state, {'reason': 'lease_expired'})
            row = self.db.execute("SELECT * FROM jobs WHERE state='pending' AND available_at<=? AND attempts<max_attempts ORDER BY rowid LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            self.db.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_until=?,lease_token=? WHERE id=?",
                            (now+lease_seconds, token, row['id']))
            self.event(row['id'], 'running', {'attempt': row['attempts']+1})
            return {**dict(row), 'state': 'running', 'attempts': row['attempts']+1,
                    'payload': json.loads(row['payload']), 'lease_token': token, 'lease_until': now+lease_seconds}

    def finish(self, job, state, checkpoint=None, error_code=None, now=None):
        require(state in ('done', 'needs_review', 'blocked', 'failed', 'uncertain', 'pending'), 'Invalid completion state')
        require(error_code is None or error_code in ('access_denied', 'rate_limited', 'invalid_evidence', 'transport_unknown', 'local_failure'), 'Only sanitized errors are persisted')
        now = time.time() if now is None else now
        with self.store.atomic():
            row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone()
            require(row and row['state'] == 'running' and row['lease_token'] == job['lease_token'] and row['lease_until'] > now, 'Expired or superseded worker lease')
            if state == 'pending':
                require(row['kind'] != 'model_request' and row['attempts'] < row['max_attempts'], 'Automatic retry forbidden or exhausted')
                require(error_code in ('rate_limited', 'local_failure'), 'Access/evidence failures cannot retry automatically')
            require(error_code != 'access_denied' or state == 'blocked', 'Access denial must block')
            due = now + min(300, 2**row['attempts']) if state == 'pending' else now
            self.db.execute('UPDATE jobs SET state=?,checkpoint=?,error_code=?,available_at=?,lease_until=NULL,lease_token=NULL WHERE id=?',
                            (state, canonical(checkpoint), error_code, due, row['id']))
            self.event(row['id'], state, {'checkpoint_sha256': digest(checkpoint), 'error_code': error_code})


class Ledger:
    """Application reservations only; NOT a provider/account hard billing cap.

Integer microdollars avoid rounding down. Every attempted request keeps a slot.
Partial/missing usage or an uncertain outcome retains its entire reservation.
"""
    def __init__(self, store, name, ceiling_micro, max_calls):
        require(type(ceiling_micro) is int and ceiling_micro > 0 and type(max_calls) is int and max_calls > 0, 'Positive bounded budget required')
        self.store, self.db, self.name = store, store.db, name
        with store.atomic():
            row = self.db.execute('SELECT * FROM budgets WHERE id=?', (name,)).fetchone()
            require(row is None or (row['ceiling_micro'] == ceiling_micro and row['max_calls'] == max_calls), 'Budget cannot be silently enlarged')
            self.db.execute('INSERT OR IGNORE INTO budgets VALUES(?,?,?)', (name, ceiling_micro, max_calls))

    def reserve(self, request_hash, upper_cost_micro):
        require(type(upper_cost_micro) is int and upper_cost_micro > 0, 'Positive reservation required')
        with self.store.atomic():
            b = self.db.execute('SELECT * FROM budgets WHERE id=?', (self.name,)).fetchone()
            rows = self.db.execute('SELECT * FROM reservations WHERE budget_id=?', (self.name,)).fetchall()
            require(not any(r['state'] in ('uncertain', 'overrun') for r in rows), 'Unsettled or overrun usage stops the batch')
            require(not self.db.execute('SELECT 1 FROM reservations WHERE id=?', (request_hash,)).fetchone(), 'Request already reserved; reconcile instead of resending')
            used = sum(r['actual_micro'] if r['state'] == 'settled' else r['amount_micro'] for r in rows)
            require(len(rows) < b['max_calls'] and used+upper_cost_micro <= b['ceiling_micro'], 'Budget or request ceiling reached')
            self.db.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',
                            (request_hash, self.name, upper_cost_micro, 'reserved', None, '{}'))

    def settle(self, request_hash, input_tokens, output_tokens, tool_queries=0):
        counts = (input_tokens, output_tokens, tool_queries)
        valid = all(type(n) is int and n >= 0 for n in counts)
        with self.store.atomic():
            r = self.db.execute('SELECT * FROM reservations WHERE id=? AND budget_id=?', (request_hash, self.name)).fetchone()
            require(r is not None and r['state'] == 'reserved', 'No open reservation')
            # Current planning prices, including all billed output/reasoning tokens.
            cost = ((input_tokens*125 + output_tokens*425 + tool_queries*250000 + 99)//100) if valid else None
            state = 'uncertain' if cost is None else ('overrun' if cost > r['amount_micro'] else 'settled')
            self.db.execute('UPDATE reservations SET state=?,actual_micro=?,details=? WHERE id=?',
                            (state, cost, canonical({'input_tokens': input_tokens, 'output_tokens': output_tokens,
                                                    'tool_queries': tool_queries, 'pricing_date': '2026-11-04'}), request_hash))
        return state
