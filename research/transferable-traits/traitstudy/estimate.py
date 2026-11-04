"""Transparent planning arithmetic. Estimates do not authorize spending."""
from decimal import Decimal

PRICES={'input_usd_per_million':'1.25','output_usd_per_million':'4.25',
        'web_query_usd':'0.0025','checked':'2026-11-04',
        'source':'https://dev.meta.ai/docs/pricing-rate-limits', 'mode':'Standard'}


def estimate(cases, calls_per_case=2, input_tokens=20000, output_tokens=8000,
             web_queries_per_case=2, overhead_fraction='0.30'):
    values=(cases,calls_per_case,input_tokens,output_tokens,web_queries_per_case)
    if any(type(n) is not int or n<0 for n in values):raise ValueError('Nonnegative integer counts required')
    overhead=Decimal(overhead_fraction)
    if not overhead.is_finite() or not 0<=overhead<=1:raise ValueError('Overhead must be 0–1')
    calls=cases*calls_per_case
    model=(Decimal(calls*input_tokens)*Decimal(PRICES['input_usd_per_million'])+
           Decimal(calls*output_tokens)*Decimal(PRICES['output_usd_per_million']))/1000000
    search=Decimal(cases*web_queries_per_case)*Decimal(PRICES['web_query_usd'])
    return {'candidate_cases':cases,'model_calls':calls,'input_tokens':calls*input_tokens,
            'output_tokens_including_reasoning':calls*output_tokens,
            'paid_web_queries':cases*web_queries_per_case,'model_usd':str(model),
            'web_search_usd':str(search),'subtotal_usd':str(model+search),
            'with_overhead_usd':str((model+search)*(1+overhead)),
            'validated_unique_traits':None,'pricing':PRICES,
            'excluded':'Hosting, storage, taxes, human review, paid publisher access; no cache discount assumed'}


if __name__=='__main__':
    import json
    print(json.dumps([estimate(n) for n in (6,50,500,750,1000)],indent=2))
