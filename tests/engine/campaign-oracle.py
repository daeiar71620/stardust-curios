"""Streaming synthetic, public-observation-driven mixed v9 campaign oracle.

Only the supplied Python source is read. There are no saves, databases, network
requests, imported games, post-start state patches, or fixture files. Policies
receive public observations only; hidden values are used solely by the oracle
to execute/validate and by the harness to compare complete results.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
parser.add_argument('--summary-only', action='store_true')
args = parser.parse_args()
source = Path(args.engine).resolve()
sys.path.insert(0, str(source.parent))
spec = importlib.util.spec_from_file_location('campaign_oracle_engine', source)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def emit(value):
    if not args.summary_only or value['type'] == 'summary':
        print(json.dumps(value, ensure_ascii=False, separators=(',', ':')), flush=True)


coverage = Counter()
successes = Counter()
failures = Counter()
event_ids = set()
campaigns = []
sequence = 0


def read_probes(state, public):
    """Compact descriptors; results reference the independently produced view."""
    probes = [{'command': c, 'args': []} for c in ('status', 'market', 'codex', 'visitors')]
    for location in ('inventory', 'collection'):
        if public[location]:
            probes.append({'command': 'inspect', 'args': [public[location][0]['id'].lower()]})
    if public['crates']:
        crate_id = public['crates'][0]['id']
        probes.append({'command': 'inspect', 'args': [crate_id],
                       'error': f'未找到物品 {crate_id}。盲箱需先 open 才能查看内容。'})
    pending = public['negotiation']
    if pending:
        item_id = pending['item_id']
        for price in sorted({pending['counter_offer'], pending['counter_offer'] + 1,
                             pending['original_price'] - 1, pending['original_price']}):
            probe = {'command': 'preview-offer', 'args': [item_id.lower(), str(price)]}
            try:
                final = engine._final_price(state['negotiation'], str(price))
                probe['preview'] = dict(engine._offer_forecast(state, state['negotiation'], final), suggested=False)
            except engine.GameError as exc:
                probe['error'] = str(exc)
            probes.append(probe)
    return probes


class Campaign:
    def __init__(self, seed, endowed, variant, until):
        self.label = f'{"endowed" if endowed else "fresh"}-seed-{seed}-policy-{variant}'
        self.variant = variant
        self.endowed = endowed
        self.until = until
        self.negotiations = 0
        self.steps = 0
        self.daily_collections = 0
        self.state = engine.new_state(seed)
        self.state['revision'] = 1
        # Explicit initial synthetic financing, not an asserted reachable new game.
        # Every later change, item and random draw comes from an actual command.
        if endowed:
            self.state['credits'] = 12000
        engine._validate_state(self.state)
        public = self.observe()
        emit({'type': 'start', 'label': self.label, 'seed': str(seed), 'endowed': endowed,
              'initial': self.state, 'observation': public, 'reads': read_probes(self.state, public)})

    def observe(self):
        return engine.observation(self.state)

    def step(self, command, *argv, tag=None):
        global sequence
        before = self.state
        candidate = copy.deepcopy(before)
        try:
            engine.apply_command(candidate, command, list(argv))
            candidate['revision'] += 1
            engine._validate_state(candidate)
            self.state = candidate
            error = None
            successes[command] += 1
        except engine.GameError as exc:
            error = str(exc)
            failures[command] += 1
        public = self.observe()
        self.steps += 1
        sequence += 1
        event_ids.add(public['daily_event']['id'])
        if tag:
            coverage[tag + ('/error' if error else '/success')] += 1
        if error is None and command == 'sell':
            coverage['sale/named' if len(argv) == 2 else 'sale/walkin'] += 1
            coverage['initial/' + str(public['last_roll']['outcome'])] += 1
        if error is None and command == 'offer':
            coverage['final/' + str(public['last_roll']['outcome'])] += 1
        if error is None and command == 'repair':
            coverage['repair/failure' if '失手' in public['last_event']['text'] else 'repair/success'] += 1
        if error is None and command == 'endday':
            if before['negotiation']:
                coverage['endday/closes-pending'] += 1
            if public['phase'] == 'week_summary':
                coverage['first-week/' + public['campaign']['first_week_result']] += 1
            if public['phase'] == 'lost':
                coverage['lost'] += 1
        if len(public['log']) == 60:
            coverage['retention/log60'] += 1
        if len(public['roll_history']) == 60:
            coverage['retention/roll60'] += 1
        emit({'type': 'step', 'index': self.steps, 'sequence': sequence,
              'command': command, 'args': list(argv), 'tag': tag, 'error': error,
              'state': self.state, 'observation': public, 'reads': read_probes(self.state, public)})
        return error is None

    def repair(self, item_id):
        if self.step('repair', item_id.lower(), tag='repair/first-attempt'):
            self.step('repair', item_id, tag='repair/same-day-retry')

    def resolve(self):
        public = self.observe()
        pending = public['negotiation']
        if not pending:
            return False
        self.negotiations += 1
        item_id = pending['item_id']
        self.step('price', item_id, '99', tag='pending/price-lock')
        self.step('repair', item_id, tag='pending/repair-lock')
        self.step('collect', item_id, tag='pending/collect-lock')
        self.step('replace-collection', item_id, tag='pending/replacement-lock')
        self.step('offer', item_id, str(pending['counter_offer']), tag='offer/counter-boundary')
        self.step('offer', item_id, str(pending['original_price']), tag='offer/initial-boundary')
        choice = (self.negotiations + self.variant) % 5
        # The self-financed policy accepts binding quotes to remain viable.
        if not self.endowed:
            choice = 0
        if choice == 4:
            self.step('endday', tag='pending/automatic-close')
            self.step('accept', item_id, tag='pending/expired-quote')
            return True
        if choice == 0:
            self.step('accept', item_id, tag='pending/accept')
        elif choice == 1:
            self.step('decline', item_id, tag='pending/decline')
        else:
            low, high = pending['counter_offer'] + 1, pending['original_price'] - 1
            if low <= high and public['energy'] > 0:
                self.step('offer', item_id, str(low if choice == 2 else high), tag='pending/final-offer')
            else:
                self.step('accept', item_id, tag='pending/no-final-space')
        self.step('accept', item_id, tag='pending/closed-quote')
        self.step('sell', item_id, tag='sale/no-reroll-after-resolution')
        return False

    def sell(self, item_id):
        public = self.observe()
        item = next((i for i in public['inventory'] if i['id'] == item_id), None)
        if item is None:
            return False
        options = [o for o in item['sale_options'] if o['available']]
        if not options:
            return False
        # Only public preferences, condition requirements and caps inform choice.
        options.sort(key=lambda o: (not o['preference_match'], not o['condition_met'],
                                    o['customer_id'] is None if self.variant % 2 else o['customer_id'] is not None,
                                    -o['max_counter_ask']))
        option = options[0]
        price = max(2, option['max_counter_ask'] if self.endowed else round(min(item['public_reference'] * .84, option['max_counter_ask'])))
        if self.endowed and (public['day'] + self.variant) % 11 == 0:
            price = 9999
        self.step('price', item_id.lower(), str(price), tag='sale/public-price')
        argv = [item_id.lower()] + ([option['customer_id'].upper()] if option['customer_id'] else [])
        if not self.step('sell', *argv, tag='sale/initial'):
            return False
        self.step('sell', *argv, tag='sale/immediate-no-reroll')
        if self.observe()['negotiation']:
            return self.resolve()
        # Changing a surviving price is permitted, but must never grant another roll.
        if any(i['id'] == item_id for i in self.observe()['inventory']):
            self.step('price', item_id, str(max(1, price - 1)), tag='sale/change-failed-price')
            self.step('sell', *argv, tag='sale/no-reroll-after-price')
        return False

    def manage_inventory(self):
        public = self.observe()
        for original in list(public['inventory']):
            public = self.observe()
            item = next((i for i in public['inventory'] if i['id'] == original['id']), None)
            if item is None or public['phase'] != 'active' or public['energy'] < 1:
                continue
            replacement = item['collection_replacement']
            if replacement and replacement['available']:
                self.step('collect', item['id'], tag='collection/duplicate-rejected')
                self.step('replace-collection', item['id'].lower(), tag='collection/better-replacement')
                self.step('replace-collection', replacement['cabinet_item_id'], tag='collection/worse-replacement')
            elif (self.daily_collections < 1 and not replacement and self.endowed
                  and (item['condition'] >= 60 or public['day'] % 3 == 0)):
                if item['condition'] < 85 and item['repair']['available'] and public['energy'] >= 4:
                    self.repair(item['id'])
                self.step('collect', item['id'].lower(), tag='collection/collect')
                self.daily_collections += 1

    def day(self):
        public = self.observe()
        day = public['day']
        self.daily_collections = 0
        self.step('continue', tag='continue/active-rejected')
        self.step('buy', 'missing', tag='buy/unknown-supplier')
        # At most one permanent investment per day, selected from public costs.
        upgrades = public['upgrade_details']
        upgrades = upgrades[self.variant % 3:] + upgrades[:self.variant % 3]
        affordable = next((u for u in upgrades if u['next_cost'] is not None and
                           public['credits'] >= u['next_cost'] + (800 if self.endowed else 300)), None)
        if affordable and public['energy'] >= 6:
            self.step('upgrade', affordable['id'], tag='upgrade/' + affordable['id'])
        public = self.observe()
        candidates = [i for i in public['collection'] if i['repair']['available'] and i['condition'] < 90]
        if candidates and (self.variant + day) % 2 == 0:
            self.repair(candidates[0]['id'])
        self.manage_inventory()
        # Open every carried box in order; sealed cargo is never policy input.
        for crate in list(self.observe()['crates']):
            if self.observe()['energy'] >= 1:
                self.step('open', crate['id'].lower(), tag='crate/carried-open')
        for purchase in range(3 if self.endowed else 2):
            public = self.observe()
            if public['energy'] < 3 or len(public['inventory']) + len(public['crates']) >= public['capacity']:
                break
            candidates = [s for s in public['suppliers'] if s['stock'] > 0 and
                          public['credits'] >= s['cost'] + public['operating_cost'] * (2 if self.endowed else 1)]
            candidates.sort(key=lambda s: (s['id'] != ('curated' if self.endowed and (day + purchase + self.variant) % 2 else 'salvage')))
            if not candidates:
                break
            self.step('buy', candidates[0]['id'], tag='buy/' + candidates[0]['id'])
            crate = self.observe()['crates'][-1]
            # Deliberately carry a committed unopened box into a later day.
            if purchase == 2 and (day + self.variant) % 5 == 0:
                coverage['crate/carried-overnight'] += 1
                break
            self.step('open', crate['id'].lower(), tag='crate/new-open')
            self.step('open', crate['id'], tag='crate/reopen-rejected')
            self.manage_inventory()
        public = self.observe()
        for item in sorted(public['inventory'], key=lambda i: (i['sale_attempted_today'], -i['public_reference'])):
            if self.observe()['energy'] < 1:
                break
            if self.sell(item['id']):
                return
        public = self.observe()
        # Use leftover energy to exercise repairs on genuine opened shelf items.
        candidates = [i for i in public['inventory'] if i['repair']['available'] and i['condition'] < 80]
        if candidates and self.endowed and public['energy'] >= 2:
            self.repair(candidates[0]['id'])
        public = self.observe()
        if public['inventory']:
            self.step('price', public['inventory'][0]['id'], '01', tag='price/noncanonical-rejected')
        self.step('endday', tag='day/close')

    def run(self):
        while True:
            public = self.observe()
            if public['phase'] == 'lost':
                for command, argv in [('buy', ['salvage']), ('endday', []), ('continue', [])]:
                    self.step(command, *argv, tag='lost/rejected')
                break
            if public['phase'] == 'week_summary':
                for command, argv in [('buy', ['salvage']), ('endday', []), ('repair', ['I001']), ('sell', ['I001'])]:
                    self.step(command, *argv, tag='first-week/pause-rejected')
                self.step('continue', tag='continue/explicit')
                self.step('continue', tag='continue/repeated-rejected')
                continue
            if public['day'] > self.until:
                break
            self.day()
        public = self.observe()
        info = {'type': 'end', 'label': self.label, 'steps': self.steps,
                'endowed': self.endowed, 'final_day': public['day'], 'phase': public['phase'],
                'first_week_result': public['campaign']['first_week_result'],
                'opened': public['stats']['crates_opened'], 'sales': public['stats']['sales_count'],
                'collection': len(public['collection']), 'rolls': public['last_roll']['id'] if public['last_roll'] else None,
                'milestones': [m['id'] for m in public['campaign']['completed_milestones']]}
        campaigns.append(info)
        emit(info)


# Fresh natural-start runs exercise financing and missed first-week outcomes;
# bankruptcy is handled if reached but is not required by this fixed matrix.
# Clearly labelled
# initially endowed runs guarantee long-lived mixed trajectories and facilities.
for seed in [0, 1, 2, 7, 19, 42, 123, 2026]:
    Campaign(seed, False, seed % 4, 14).run()
for variant, seed in enumerate([0, 1, 2, 3, 7, 11, 19, 42, 123, 4321, 2**53 - 1, 2**128 + 17]):
    Campaign(seed, True, variant % 4, 35 if variant < 4 else 21).run()

emit({'type': 'summary', 'case_count': len(campaigns), 'action_count': sequence,
      'engine_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
      'successes': dict(sorted(successes.items())), 'failures': dict(sorted(failures.items())),
      'coverage': dict(sorted(coverage.items())), 'events': sorted(event_ids), 'campaigns': campaigns})
