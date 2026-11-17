"""Regression coverage for the user's current-pub and personal-readiness requirements."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import main
from recommendation_context import load_snapshot, temporal_evidence
from test_backend import isolated, cache, meta, recent_match


def morph_scenario(position=None, wins=0, games=3):
    c=cache()
    c['heroes']=main.build_heroes([{'hero_id':10,'games':games,'win':wins}], main.catalog_from_items([{'id':10,'complexity':3}]))
    c['meta']['heroes']={10:{'positions':{1:{'matches':5000,'wins':2900,'winrate':58}}}}
    c['history']=[recent_match(i,hero=10,position=position,win=i<wins) for i in range(3)]
    c['recent']=[]
    return c


@pytest.mark.parametrize('position',[None,1])
def test_zero_of_three_morphling_is_practice_first_but_can_be_worth_learning(position):
    result=main.build_recommendations(morph_scenario(position),10,1)
    assert not result['recommendations']
    row=result['worth_learning'][0]
    assert row['hero_id']==10 and row['next_game_readiness']=='practice_first'
    assert row['learning_assessment']['justified']
    assert 'evasive_damage' in row['learning_assessment']['capabilities']
    assert row['personal_evidence']['role_games']==(3 if position else 0)
    assert row['personal_evidence']['unknown_role_games']==(0 if position else 3)


def test_known_other_role_losses_are_not_relabelled_as_selected_role():
    result=main.build_recommendations(morph_scenario(2,games=100),10,1)
    row=result['recommendations'][0]
    assert row['personal_evidence']['role_games']==row['personal_evidence']['unknown_role_games']==0
    assert row['score_breakdown']['personal_performance']==row['score_breakdown']['unknown_role_readiness']==0


def test_unknown_role_losses_warn_without_claiming_role_winrate():
    c=morph_scenario(games=100)
    row=main.build_recommendations(c,10,1)['recommendations'][0]
    assert row['score_breakdown']['personal_performance']==0
    assert row['score_breakdown']['unknown_role_readiness']<0
    assert any('not role win-rate evidence' in s for s in row['reasons'])


def test_unknown_role_success_never_adds_personal_bonus():
    c=morph_scenario(wins=3,games=100)
    row=main.build_recommendations(c,10,1)['recommendations'][0]
    assert row['score_breakdown']['personal_performance']==row['score_breakdown']['unknown_role_readiness']==0


@pytest.mark.parametrize('failure',['mixed_patch','past_patch','future_window','old_window','missing_window','unverified','stale_patch_check','missing_patch_check','all_role','unknown_rank'])
def test_strict_current_meta_withholds_unverified_recommendations(monkeypatch,failure):
    c=cache(); now=datetime.now(timezone.utc)
    if failure=='mixed_patch': c['meta']['window_start']=(now-timedelta(days=20)).isoformat()
    elif failure=='past_patch': c['meta']['patch']='TI2023'
    elif failure=='future_window': c['meta']['window_end']=(now+timedelta(days=1)).isoformat()
    elif failure=='old_window':
        c['meta']['window_start']=(now-timedelta(days=10)).isoformat()
        c['meta']['window_end']=(now-timedelta(days=4)).isoformat()
    elif failure=='missing_window': c['meta'].pop('window_start')
    elif failure=='unverified': c['meta']['patch_coverage_verified']=False
    elif failure=='stale_patch_check': monkeypatch.setattr(main,'CURRENT_PATCH_INFO',main.CURRENT_PATCH_INFO|{'verified_at':(now-timedelta(days=2)).isoformat()})
    elif failure=='missing_patch_check': monkeypatch.setattr(main,'CURRENT_PATCH_INFO',{k:v for k,v in main.CURRENT_PATCH_INFO.items() if k!='verified_at'})
    elif failure=='all_role': c['meta']['position_data_exact']=False
    elif failure=='unknown_rank': c['meta']['rank_bracket']='ALL_RANKS'
    result=main.build_recommendations(c,10,1)
    assert result['recommendations']==result['worth_learning']==[]
    assert result['excluded_by_reason']['current_patch_unverified']==1


def test_explicit_legacy_mode_still_cannot_use_known_wrong_patch(monkeypatch):
    monkeypatch.setenv('REQUIRE_CURRENT_PATCH_META','false')
    c=cache(); c['meta']['patch']='TI2023'
    assert main.build_recommendations(c,10,1)['recommendations']==[]


def test_conditional_roles_require_target_rank_not_high_mmr_proxy():
    c=cache(); c['meta']['heroes']={7:{'positions':{2:{'matches':5000,'winrate':55}}}}
    c['meta']['rank_fallback_applied']=True
    result=main.build_recommendations(c,10,2)
    assert result['recommendations']==[]
    assert result['excluded_by_reason']['conditional_role_unverified']>0
    c['meta']['rank_fallback_applied']=False
    assert main.build_recommendations(c,10,2)['recommendations'][0]['hero_id']==7


def test_learning_requires_concrete_strategic_value():
    c=cache(); c['heroes']=main.build_heroes([], {})
    c['meta']['heroes']={95:{'positions':{1:{'matches':5000,'winrate':56}}}}
    # Troll has concrete disable and tower pressure capabilities, even without a pool anchor.
    row=main.build_recommendations(c,10,1)['worth_learning'][0]
    assert row['learning_assessment']['pool_gaps']


def test_snapshot_counts_determine_rate_and_rank_must_match(tmp_path):
    data=meta();data['heroes']={'8':{'positions':{'1':{'matches':1000,'wins':550,'winrate':99}}}}
    path=tmp_path/'meta.json';path.write_text(json.dumps(data))
    loaded=load_snapshot(path,'DIVINE',main.CURRENT_PATCH_INFO,datetime.now(timezone.utc))
    assert loaded['heroes'][8]['positions'][1]['winrate']==pytest.approx(55)
    with pytest.raises(ValueError,match='rank bracket'):load_snapshot(path,'ARCHON',main.CURRENT_PATCH_INFO,datetime.now(timezone.utc))


@pytest.mark.parametrize('counts',[(1,2),(0,0),(-1,0),(True,0),(100,False),(1.5,1)])
def test_snapshot_rejects_invalid_counts(tmp_path,counts):
    data=meta();data['heroes']={'8':{'positions':{'1':{'matches':counts[0],'wins':counts[1]}}}}
    path=tmp_path/'meta.json';path.write_text(json.dumps(data))
    with pytest.raises(ValueError):load_snapshot(path,'DIVINE',main.CURRENT_PATCH_INFO,datetime.now(timezone.utc))


def test_snapshot_provider_route_and_fallback_disclosure(monkeypatch,tmp_path):
    path=tmp_path/'meta.json';path.write_text(json.dumps(meta()))
    monkeypatch.setenv('CURRENT_META_FILE',str(path))
    result=asyncio.run(main.fetch_current_meta(80,[]))
    assert result['requested_rank_bracket']=='IMMORTAL' and result['rank_bracket']=='DIVINE'
    assert result['rank_fallback_applied']
    assert result['current_patch']==main.CURRENT_PATCH_INFO


def test_invalid_snapshot_fails_closed_with_visible_reason(monkeypatch,tmp_path):
    path=tmp_path/'meta.json';path.write_text(json.dumps(meta()))
    monkeypatch.setenv('CURRENT_META_FILE',str(path))
    result=asyncio.run(main.fetch_current_meta(40,[]))
    assert result['source']=='Invalid current-meta snapshot'
    assert result['heroes']=={}
    assert any('rank bracket' in warning for warning in result['warnings'])


def test_valve_patch_refresh_replaces_old_patch_and_rejects_old_snapshot(monkeypatch):
    monkeypatch.setattr(main,'LAST_PATCH_REFRESH',0)
    patch={'patch_number':'new-patch','patch_timestamp':datetime.now(timezone.utc).timestamp()}
    monkeypatch.setattr(main,'request_json',AsyncMock(return_value={'patches':[patch]}))
    c=cache()
    asyncio.run(main.refresh_current_patch())
    assert main.CURRENT_PATCH_INFO['patch_number']=='new-patch'
    assert not main.build_recommendations(c,10,1)['recommendations']


def test_full_roster_policy_and_source_coverage():
    policy=main.HERO_POLICY_AUDIT; heroes=policy['heroes']
    assert len(heroes)==127 and len({h['hero_id'] for h in heroes})==127
    assert set(main.HERO_POSITION_PROFILES)=={h['hero_id'] for h in heroes}
    for h in heroes:
        assert set(h['evidence_roles'])==set('12345')
        assert h['evidence_source'].startswith('https://dota2protracker.com/hero/')
        assert set(h['conditional_positions'])<=set(h['positions'])
        assert all(p in main.POSITION_NAMES for p in h['positions'])
    assert set(main.curated_positions(50))=={4,5}
    assert main.curated_positions(82)==[2] and main.curated_positions(135)==[3]
    assert not {4,5}&set(main.curated_positions(10))
    assert not {4,5}&set(main.curated_positions(109))
    assert main.curated_positions(73)==[1]


@pytest.mark.parametrize('position',[1,2,3,4,5])
def test_whole_roster_cannot_leak_disallowed_roles_in_either_track(position):
    c=cache(); c['heroes']=main.build_heroes([],{})
    c['meta']['heroes']={hid:{'positions':{p:{'matches':10000,'winrate':65} for p in range(1,6)}} for hid in main.HERO_POSITION_PROFILES}
    result=main.build_recommendations(c,127,position)
    for track in ('recommendations','worth_learning'):
        assert all(position in main.curated_positions(h['hero_id']) for h in result[track])
