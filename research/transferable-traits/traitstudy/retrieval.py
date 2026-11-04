"""Reviewable retrieval plans, not a network client. Respect the enforced policy."""
from urllib.parse import urlencode, quote
from .core import require


def plan(query, allowed_hosts=()):
    require(isinstance(query, str) and 0 < len(query) <= 500, 'Bounded query required')
    specs = [
        ('pubmed', 'eutils.ncbi.nlm.nih.gov', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urlencode({'db':'pubmed','term':query,'retmode':'json','retmax':10}), 2),
        ('europe_pmc', 'www.ebi.ac.uk', 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':query,'format':'json','pageSize':10,'resultType':'core'}), 1),
        ('uniprot', 'rest.uniprot.org', 'https://rest.uniprot.org/uniprotkb/search?'+urlencode({'query':query,'format':'json','size':10}), 1),
    ]
    return [{'provider':p,'url':url,'host':host,'maximum_requests_per_second':rps,
             'network_status':'permitted_unexecuted' if host in allowed_hosts else 'blocked_by_current_policy',
             'executed':False,'retry_limit':2,'stop_on':[401,403, 'access_denied'],
             'notes':'Metadata first. Rights/primary-source review before text admission. No automatic provider fallback.'}
            for p,host,url,rps in specs]
