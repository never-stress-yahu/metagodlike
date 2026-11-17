"""Transparent policy helpers. Constants are product defaults, not fitted weights."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

AUDIT_VERSION = '2026-10-01-current-pub-v4'
PERSONAL_UNKNOWN_ROLE_WEIGHT = 0.35

# Reviewed strategic capabilities; intentionally not generic attribute similarity.
# These are skill/pool descriptions, not measured counter-pick coefficients.
CAPABILITY_HEROES = {
    'reliable_disable': {2,3,5,7,8,13,14,16,18,19,20,23,25,26,27,28,29,30,33,37,41,42,49,51,52,53,59,60,64,65,66,69,71,73,75,77,78,79,80,81,82,83,84,86,87,88,89,92,95,96,97,100,101,103,104,105,107,108,111,112,114,119,120,121,123,128,129,131,135,136,137,145},
    'ally_save': {20,45,50,57,79,83,91,100,111,112,131,155},
    'initiation': {2,7,13,14,16,19,23,28,29,33,37,41,49,51,60,65,69,71,78,81,88,96,97,100,103,104,107,108,120,129,136,137},
    'tower_pressure': {6,8,12,18,20,27,33,35,43,44,46,48,49,52,53,56,61,66,73,77,80,81,89,92,94,95,109,113,138,145},
    'sustain': {8,30,36,37,45,50,54,57,58,64,66,73,85,91,99,102,108,110,111,112,135,155},
    'global_presence': {53,67,90,91,135},
    'micro_practice': {12,33,38,53,58,61,66,77,78,80,82,89,92,109,113},
    'evasive_damage': {1,10,12,13,17,32,39,44,56,63,93,106,113,114,126,145},
    'objective_damage': {6,8,18,42,44,46,48,54,59,61,70,73,77,80,81,82,89,94,95,109},
    'area_spell_damage': {5,7,11,13,19,22,23,25,29,30,31,33,34,36,37,39,40,43,45,52,64,65,74,76,84,85,97,98,100,101,105,106,107,110,119,120,121,126,128,137,138,145},
    'lane_pressure': {4,6,11,15,22,25,35,36,39,43,45,47,52,56,59,76,85,98,99,138},
}
CAPABILITY_DESCRIPTIONS = {
    'reliable_disable': 'catch enemies and create time for allied damage',
    'ally_save': 'protect allies who are caught or focused',
    'initiation': 'start fights and choose when the team commits',
    'tower_pressure': 'turn lane or fight advantages into tower pressure',
    'sustain': 'keep the team fighting through healing and durability',
    'global_presence': 'respond to fights and pressure distant parts of the map',
    'micro_practice': 'control multiple units while managing the main hero',
    'evasive_damage': 'deal damage while escaping and repositioning',
    'objective_damage': 'convert safe damage windows into Roshan or building objectives',
    'area_spell_damage': 'combine area spells and time damage around team control',
    'lane_pressure': 'pressure the lane opponent while securing farm',
}


def hero_learning_cost(complexity, games):
    """Difficulty points for a player learning a hero, reduced by prior games."""
    if complexity not in (1, 2, 3):
        return 0.0
    practiced = min(1.0, math.log1p(max(games, 0)) / math.log1p(100))
    return 0.75 * (complexity - 1) ** 2 * (1 - practiced)


def capabilities(hero_id):
    return {name for name, ids in CAPABILITY_HEROES.items() if hero_id in ids}


def learning_value(hero_id, anchors, similarity):
    own = capabilities(hero_id)
    pool = set().union(*(capabilities(h['hero_id']) for h in anchors)) if anchors else set()
    gaps = own - pool - {'micro_practice'}
    transferable = own & pool - {'micro_practice'}
    # A discovery explanation must identify a capability or a concrete shared skill.
    # Generic provider role-tag overlap alone does not qualify a learning suggestion.
    justified = bool(gaps or transferable)
    return {
        'justified': justified,
        'capabilities': sorted(own),
        'pool_gaps': sorted(gaps),
        'transferable_capabilities': sorted(transferable),
        'pool_gap_bonus': min(1.0, 0.25 * len(gaps)),
        'gap_explanations': [CAPABILITY_DESCRIPTIONS[k] for k in sorted(gaps)],
        'transfer_explanations': [CAPABILITY_DESCRIPTIONS[k] for k in sorted(transferable)],
        'basis': 'reviewed strategic capability taxonomy; not learned from outcomes',
    }


def parse_time(value):
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value) if math.isfinite(value) else None
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def temporal_evidence(meta, now, current_patch):
    start, end = parse_time(meta.get('window_start')), parse_time(meta.get('window_end'))
    patch_start = parse_time(current_patch.get('patch_timestamp'))
    patch = current_patch.get('patch_number')
    now_ts = now.timestamp()
    patch_checked = parse_time(current_patch.get('verified_at', current_patch.get('verified_date')))
    patch_fresh = patch_checked is not None and 0 <= now_ts-patch_checked <= 86400
    valid_window = start is not None and end is not None and 0 <= end-start <= 14*86400 and 0 <= now_ts-end <= 3*86400
    verified = bool(meta.get('patch_coverage_verified')) and bool(patch) and meta.get('patch') == patch and patch_start is not None and patch_fresh and valid_window and start >= patch_start
    wrong_patch = bool(meta.get('patch') and patch and meta['patch'] != patch)
    return {'verified': verified, 'wrong_patch': wrong_patch, 'patch': patch,
            'patch_started_at': patch_start, 'window_start': meta.get('window_start'),
            'window_end': meta.get('window_end'),
            'reason': None if verified else 'Underlying match window and current patch are not verified'}


def load_snapshot(path, rank_name, current_patch, now):
    """Validate an explicitly supplied rank/position cohort; never reuse high-MMR audits as pub meta."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('rank_bracket') != rank_name:
            raise ValueError('Current-meta snapshot must match the requested rank bracket')
        if not data.get('source') or not data.get('position_data_exact'):
            raise ValueError('Current-meta snapshot requires source and role-specific statistics')
        collected = parse_time(data.get('collected_at'))
        if collected is None or not 0 <= now.timestamp()-collected <= 86400:
            raise ValueError('Current-meta snapshot must be collected within the last 24 hours')
        if not temporal_evidence(data, now, current_patch)['verified']:
            raise ValueError('Current-meta snapshot must cover only the current patch and a recent match window')
        heroes = data.get('heroes')
        if not isinstance(heroes, dict):
            raise ValueError('Current-meta snapshot requires hero statistics')
        normalized = {}
        for hid, hero in heroes.items():
            if not isinstance(hero, dict) or not isinstance(hero.get('positions'), dict):
                raise ValueError('Invalid hero/position statistics')
            positions = {}
            for pos, row in hero['positions'].items():
                pos = int(pos)
                if pos not in (1,2,3,4,5) or not isinstance(row, dict):
                    raise ValueError('Invalid position statistics')
                count, wins = row.get('matches'), row.get('wins')
                if isinstance(count, bool) or isinstance(wins, bool) or not isinstance(count, int) or not isinstance(wins, int) or not 0 <= wins <= count or count <= 0:
                    raise ValueError('Invalid position sample counts')
                positions[pos] = {**row, 'winrate': wins/count*100}
            normalized[int(hid)] = {**hero, 'positions': positions}
        return {**data, 'heroes': normalized, 'current_patch': current_patch, 'stale': False, 'warnings': []}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid CURRENT_META_FILE: {exc}') from exc
