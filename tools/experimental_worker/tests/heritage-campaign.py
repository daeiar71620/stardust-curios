"""Streaming genuine-command native-v8 -> official migration -> v9 campaigns.

Synthetic _legacy_v8.new_state only. Initial test financing is disclosed. After
that, every item, date, quality improvement, trade, and RNG advance comes from
an official command. Decisions use public observations, never hidden values.
No GameStore, real saves, network, or payload fixture files are used.
"""
import argparse
import copy
import hashlib
import importlib
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
spec = importlib.util.spec_from_file_location('heritage_campaign_engine', source)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
old = importlib.import_module('_legacy_v8')
coverage, successes, failures = Counter(), Counter(), Counter()
campaigns = []


def emit(record):
    if not args.summary_only or record['type'] == 'summary':
        print(json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(',', ':')), flush=True)


def norm(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


class Campaign:
    def __init__(self, seed, trigger, variant):
        self.label = f'v8-{trigger}-seed-{seed}'
        self.trigger, self.variant = trigger, variant
        self.state = old.new_state(seed)
        self.state.update(revision=1, credits=20000)  # Disclosed initial synthetic financing only.
        self.module = old
        self.old_steps, self.steps, self.pending_count = 0, 0, 0
        self.migrated = False
        self.source_day = None
        old._validate_state(self.state)

    def observe(self):
        return self.module.observation(self.state)

    def maybe_migrate(self):
        if self.migrated:
            return
        public = self.observe()
        ready = (self.trigger == 'pending' and public['negotiation'] is not None
                 or self.trigger == 'day8' and public['day'] >= 8
                 or self.trigger == 'retained' and self.state['roll_seq'] >= 65)
        if not ready:
            return
        before = norm(self.state)
        self.state = engine.migrate_v8(json.dumps(before, ensure_ascii=False).encode())
        engine._validate_state(self.state)
        self.module, self.migrated = engine, True
        self.source_day = self.state['day']
        for key in ['day', 'phase', 'revision', 'credits', 'energy', 'reputation', 'inventory', 'collection',
                    'crates', 'upgrades', 'stats', 'first_week_result', 'milestones', 'rng', 'roll_seq', 'roll_history']:
            assert norm(self.state[key]) == before[key], ('migration changed', key)
        assert old._public_collection_progress(before) == engine._public_collection_progress(self.state)
        assert old._public_campaign(before) == engine._public_campaign(self.state)
        if self.state['negotiation']:
            assert self.state['negotiation']['origin_rules_version'] == 6
            assert self.state['negotiation']['rules_version'] == 9
            coverage['migration/pending6'] += 1
        coverage['migration/' + self.trigger] += 1
        emit({'type': 'start', 'label': self.label, 'source': before, 'initial': self.state,
              'old_commands': self.old_steps, 'observation': self.observe()})

    def step(self, command, *argv, tag=None):
        before = self.state
        candidate = copy.deepcopy(before)
        try:
            self.module.apply_command(candidate, command, list(argv))
            candidate['revision'] += 1
            self.module._validate_state(candidate)
            self.state = candidate
            error = None
        except self.module.GameError as exc:
            error = str(exc)
        if self.migrated:
            self.steps += 1
            (successes if error is None else failures)[command] += 1
            if tag:
                coverage[tag + ('/success' if error is None else '/error')] += 1
            if error is None:
                if command in ['sell', 'offer']:
                    row = self.state['roll_history'][-1]
                    coverage[command + '/' + row['outcome']] += 1
                    if command == 'offer' and before['negotiation']['origin_rules_version'] == 6:
                        coverage['cross-boundary/final9'] += 1
                if command == 'endday' and before['negotiation']:
                    coverage['pending/expiry'] += 1
                if len(self.state['roll_history']) == 60:
                    coverage['retention/60'] += 1
                if self.state['roll_history'] and all(row['rules_version'] == 9 for row in self.state['roll_history']):
                    coverage['retention/old-evicted'] += 1
            emit({'type': 'step', 'label': self.label, 'index': self.steps, 'command': command,
                  'args': list(argv), 'tag': tag, 'error': error, 'state': self.state, 'observation': self.observe()})
        else:
            self.old_steps += 1
            self.maybe_migrate()
        return error is None

    def resolve(self):
        pending = self.observe()['negotiation']
        if pending is None:
            return False
        self.pending_count += 1
        item_id = pending['item_id']
        self.step('repair', item_id, tag='pending/repair-lock')
        self.step('price', item_id, '99', tag='pending/price-lock')
        self.step('offer', item_id, str(pending['counter_offer']), tag='pending/low-bound')
        self.step('offer', item_id, str(pending['original_price']), tag='pending/high-bound')
        mode = (self.pending_count + self.variant) % 5
        # The exact migration-crossing pending trade exercises a final9 whenever
        # a genuine available gap exists; remaining campaigns cover all closures.
        if pending['origin_rules_version'] == 6 and self.migrated and self.trigger == 'pending':
            mode = self.variant % 4
        if mode == 4:
            self.step('endday', tag='pending/close-day')
            self.step('accept', item_id, tag='pending/expired-accept')
            return True
        if mode in [0, 1] and pending['final_offer_bounds']['available'] and self.observe()['energy']:
            self.step('offer', item_id, str(pending['final_offer_bounds']['min'] if mode == 0 else pending['final_offer_bounds']['max']), tag='pending/final')
        elif mode == 3:
            self.step('decline', item_id, tag='pending/decline')
        else:
            self.step('accept', item_id, tag='pending/accept')
        self.step('accept', item_id, tag='pending/already-closed')
        return False

    def day(self):
        if self.resolve():
            return
        public = self.observe()
        self.step('continue', tag='active/continue')
        upgrades = public['upgrade_details']
        option = next((u for u in upgrades if u['next_cost'] is not None and public['credits'] > u['next_cost'] + 5000), None)
        if option and public['energy'] >= 8:
            self.step('upgrade', option['id'], tag='management/upgrade')
        collected_today = False
        for purchase in range(3):
            public = self.observe()
            if public['energy'] < 3 or len(public['inventory']) + len(public['crates']) >= public['capacity']:
                break
            supplier = next((s for s in public['suppliers'] if s['stock'] and public['credits'] > s['cost'] + 200), None)
            if not supplier:
                break
            self.step('buy', supplier['id'], tag='crate/buy')
            crate = self.observe()['crates'][-1]
            self.step('open', crate['id'], tag='crate/open')
            item = self.observe()['inventory'][-1]
            replacement = item['collection_replacement']
            if replacement and replacement['available'] and self.observe()['energy'] >= 2:
                self.step('replace-collection', item['id'], tag='quality/replacement')
            elif not replacement and not collected_today and public['day'] % 3 == 0 and self.observe()['energy'] >= 3:
                if item['repair']['available'] and item['condition'] < 75 and self.observe()['energy'] >= 5:
                    self.step('repair', item['id'], tag='quality/precollect-repair')
                self.step('collect', item['id'], tag='quality/collect')
                collected_today = True
        public = self.observe()
        for item in list(public['inventory']):
            public = self.observe()
            if public['energy'] < 1:
                break
            item = next((i for i in public['inventory'] if i['id'] == item['id']), None)
            if item is None:
                continue
            options = [option for option in item['sale_options'] if option['available']]
            options.sort(key=lambda o: (not o['condition_met'], not o['preference_match'], o['customer_id'] is None))
            if not options:
                continue
            option = options[0]
            price = max(2, option['max_counter_ask'])
            self.step('price', item['id'], str(price), tag='sale/price')
            argv = [item['id']] + ([option['customer_id']] if option['customer_id'] else [])
            self.step('sell', *argv, tag='sale/named' if option['customer_id'] else 'sale/walkin')
            self.step('sell', *argv, tag='sale/no-reroll')
            if self.resolve():
                return
        public = self.observe()
        repairs = [item for item in public['collection'] if item['repair']['available']]
        if repairs and public['energy'] >= 2:
            self.step('repair', repairs[0]['id'], tag='quality/cabinet-repair')
        self.step('endday', tag='day/close')

    def run(self):
        while self.state['day'] <= 120:
            public = self.observe()
            if public['phase'] == 'lost':
                break
            if public['phase'] == 'week_summary':
                self.step('endday', tag='summary/no-advance')
                self.step('continue', tag='summary/continue')
                continue
            if self.migrated and public['day'] > self.source_day + (35 if self.trigger == 'retained' else 18):
                break
            self.day()
        assert self.migrated, (self.label, 'migration trigger not reached')
        assert self.steps > 100, (self.label, 'insufficient post-migration run')
        assert self.state['phase'] != 'lost', (self.label, 'test financing unexpectedly exhausted')
        info = {'type': 'end', 'label': self.label, 'old_commands': self.old_steps, 'steps': self.steps,
                'source_day': self.source_day, 'day': self.state['day'], 'roll_seq': self.state['roll_seq'],
                'collection': len(self.state['collection']), 'milestones': len(self.state['milestones'])}
        campaigns.append(info)
        emit(info)


for variant, seed in enumerate([0, 1, 7, 19]):
    Campaign(seed, 'pending', variant).run()
for variant, seed in enumerate([2, 42]):
    Campaign(seed, 'day8', variant).run()
for variant, seed in enumerate([7, 19]):
    Campaign(seed, 'retained', variant).run()
emit({'type': 'summary', 'case_count': len(campaigns), 'action_count': sum(c['steps'] for c in campaigns),
      'old_action_count': sum(c['old_commands'] for c in campaigns), 'campaigns': campaigns,
      'coverage': dict(sorted(coverage.items())), 'successes': dict(sorted(successes.items())),
      'failures': dict(sorted(failures.items())), 'engine_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
      'legacy_v8_sha256': hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest()})
