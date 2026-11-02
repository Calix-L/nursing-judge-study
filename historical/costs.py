"""Conservative, offline list-price estimates from raw transport usage ledgers.

Bounds cover observed, valid, priced usage only, never unreported requests.
No account balance, discounts or free credits are inferred. Cache is part of
prompt_tokens and reasoning is already part of completion_tokens.
"""
from collections import Counter
from decimal import Decimal


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError('Token count must be a nonnegative integer')
    return value


def _usage(raw):
    if not isinstance(raw, dict):
        raise ValueError('Usage must be an object')
    prompt = _count(raw['prompt_tokens'])
    completion = _count(raw['completion_tokens'])
    total = _count(raw.get('total_tokens', prompt + completion))
    if total != prompt + completion:
        raise ValueError('Inconsistent total tokens')
    completion_details = raw.get('completion_tokens_details')
    if completion_details is not None:
        if not isinstance(completion_details, dict):
            raise ValueError('Invalid completion token details')
        if 'reasoning_tokens' in completion_details:
            if _count(completion_details['reasoning_tokens']) > completion:
                raise ValueError('Reasoning exceeds completion tokens')
    hits = []
    if 'prompt_cache_hit_tokens' in raw:
        hits.append(_count(raw['prompt_cache_hit_tokens']))
    details = raw.get('prompt_tokens_details')
    if details is not None:
        if not isinstance(details, dict):
            raise ValueError('Invalid prompt token details')
        if 'cached_tokens' in details:
            hits.append(_count(details['cached_tokens']))
    if 'prompt_cache_miss_tokens' in raw:
        hits.append(prompt - _count(raw['prompt_cache_miss_tokens']))
    if any(hit < 0 or hit > prompt for hit in hits) or len(set(hits)) > 1:
        raise ValueError('Contradictory cache counts')
    return prompt, completion, total, hits[0] if hits else (0 if prompt == 0 else None)


def _rate(prices, model, prompt):
    tiers = prices.get('models', {}).get(model, {}).get('tiers', [])
    for tier in tiers:
        if prompt >= tier.get('input_min', 0) and (
            tier.get('input_max_exclusive') is None or prompt < tier['input_max_exclusive']
        ):
            return tuple(Decimal(str(tier[key])) for key in ('input', 'cached_input', 'output'))
    return None


def _aggregate(entries, prices):
    counts = Counter()
    statuses = Counter()
    tokens = Counter()
    lower = upper = Decimal(0)
    for entry in entries:
        counts['events'] += 1
        status = entry.get('status', 'unknown')
        statuses[status] += 1
        if status == 'rate_limit_cooldown':
            counts['cooldown_events'] += 1
            continue
        counts['requests'] += 1
        failed = status != 'ok'
        counts['failed_requests' if failed else 'successful_requests'] += 1
        raw = entry.get('usage')
        if raw is None or raw == {}:
            counts['usage_missing'] += 1
            counts['possible_unreported_bill'] += int(failed)
            continue
        try:
            prompt, completion, total, cached = _usage(raw)
        except (ValueError, KeyError, TypeError):
            counts['usage_invalid'] += 1
            counts['possible_unreported_bill'] += int(failed)
            continue
        counts['usage_observed'] += 1
        tokens.update(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)
        if cached is None:
            counts['cache_unknown'] += 1
        else:
            counts['cache_observed'] += 1
            tokens['cached_tokens'] += cached
        rates = _rate(prices, entry.get('requested_model'), prompt)
        if rates is None:
            counts['price_unknown'] += 1
            continue
        counts['priced_requests'] += 1
        uncached_rate, cached_rate, output_rate = rates
        output_cost = completion * output_rate
        if cached is None:
            a, b = sorted((prompt * cached_rate, prompt * uncached_rate))
        else:
            a = b = (prompt - cached) * uncached_rate + cached * cached_rate
        lower += (a + output_cost) / 1_000_000
        upper += (b + output_cost) / 1_000_000
    fields = ('events', 'requests', 'cooldown_events', 'successful_requests', 'failed_requests',
              'usage_missing', 'usage_invalid', 'usage_observed', 'cache_unknown',
              'cache_observed', 'price_unknown', 'priced_requests', 'possible_unreported_bill')
    result = {key: counts[key] for key in fields}
    result['status_counts'] = dict(sorted(statuses.items()))
    result['complete_usage'] = counts['usage_observed'] == counts['requests']
    result['tokens'] = {key: tokens[key] if counts['usage_observed'] or not counts['requests'] else None
                        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    result['tokens']['cached_tokens'] = (tokens['cached_tokens'] if counts['cache_observed']
                                          or not counts['requests'] else None)
    result['token_scope'] = 'observed_valid_usage_only; cached_tokens is known-cache subtotal'
    has_cost = counts['priced_requests'] or not counts['requests']
    exact = result['complete_usage'] and not counts['price_unknown'] and not counts['cache_unknown']
    result['list_cost_cny'] = {
        'lower': float(lower) if has_cost else None,
        'upper': float(upper) if has_cost else None,
        'point': float(lower) if exact else None,
        'scope': 'observed_valid_priced_usage_only',
        'estimate_only': True,
    }
    return result


def summarize(entries, prices):
    """Return JSON-safe totals, separate role totals and requested-model totals.

    ``prices`` is the full versioned price artifact with a ``models`` mapping.
    Failed requests with valid usage are counted. Cooldown ledger events are
    local waits, not API requests. Missing/invalid usage remains unknown; token
    sums include only valid usage and costs include only known model prices.
    """
    entries = list(entries)
    result = {'schema_version': 1, 'currency': 'CNY', 'price_source_url': prices.get('source_url'),
              'price_verified_date': prices.get('verified_date'), 'total': _aggregate(entries, prices)}
    for field, destination in (('role', 'by_role'), ('requested_model', 'by_model')):
        keys = sorted({str(entry.get(field) or 'unknown') for entry in entries})
        result[destination] = {
            key: _aggregate([entry for entry in entries if str(entry.get(field) or 'unknown') == key], prices)
            for key in keys
        }
    return result
