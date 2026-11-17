"""Regression tests: real FastAPI/SQLite, fully mocked external providers."""
import asyncio
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

import database
import main

REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
    for name, value in {
        'ACTIVE_PLAYER_CACHE': None, 'HERO_CATALOG_CACHE': {}, 'HERO_STATS_CACHE': {},
        'HERO_STATS_FETCHED_AT': None, 'HERO_STATS_FETCHED_MONOTONIC': 0,
        'LAST_SYNC_ATTEMPT': float('-inf'), 'META_CACHE': {},
        'SYNC_LOCK': asyncio.Lock(), 'CATALOG_LOCK': asyncio.Lock(),
        'RECOMMENDATION_REFRESH_LOCK': asyncio.Lock(), 'LAST_META_REFRESH_ATTEMPT': float('-inf'),
    }.items():
        monkeypatch.setattr(main, name, value)
    monkeypatch.delenv('STRATZ_TOKEN', raising=False)
    monkeypatch.delenv('OPENDOTA_API_KEY', raising=False)
    monkeypatch.delenv('CURRENT_META_FILE', raising=False)
    monkeypatch.delenv('REQUIRE_CURRENT_PATCH_META', raising=False)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(main, 'CURRENT_PATCH_INFO', {'patch_number':'test-current', 'patch_timestamp':(now-timedelta(days=14)).timestamp(), 'verified_at':now.isoformat()})
    monkeypatch.setattr(main, 'LAST_PATCH_REFRESH', time.monotonic())
    def forbidden(request):
        raise AssertionError(f"Unexpected network request: {request.url.path}")
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(forbidden), **kwargs))
    yield
    engine.dispose()


def run(coroutine):
    return asyncio.run(coroutine)


def match(i, hero=1):
    return {'match_id': i, 'hero_id': hero, 'is_win': i % 2 == 0, 'start_time': 1700000000+i,
            'position': 1, 'kills': 5, 'deaths': 2, 'assists': 3, 'gpm': 500, 'xpm': 600, 'duration': 1800}


def provider_data(account_id=123):
    return {
        'source': 'OpenDota', 'player_name': f'Player {account_id}', 'rank': 80,
        'total_wins': 15, 'total_losses': 5,
        'history': [match(i) for i in range(1, 42)], 'recent': [match(i) for i in range(22,42)],
        'player_heroes': [{'hero_id':1,'games':20,'win':15},{'hero_id':8,'games':10,'win':6}],
        'catalog': main.catalog_from_items([{'id':1,'localized_name':'Anti-Mage'},{'id':8,'localized_name':'Juggernaut'}]),
        'hero_stats_scope': {'kind':'provider_aggregate','matches':30,'provider':'OpenDota'},
        'totals_scope':'provider_aggregate','warnings':[],
    }


def meta():
    now = datetime.now(timezone.utc)
    return {'source':'test meta','requested_rank_bracket':'DIVINE','rank_bracket':'DIVINE',
            'rank_fallback_applied':False,'position_data_exact':True,
            'patch':main.CURRENT_PATCH_INFO['patch_number'], 'patch_coverage_verified':True,
            'window_start':(now-timedelta(days=7)).isoformat(), 'window_end':now.isoformat(),
            'collected_at':datetime.now(timezone.utc).isoformat(), 'warnings':[],
            'heroes':{h:{'positions':{1:{'matches':1000,'wins':550,'winrate':55,'pick_rate':20}}} for h in (1,8,61,106)}}


def cache():
    data = provider_data()
    heroes = main.build_heroes(data['player_heroes'], data['catalog'])
    favorite, best = main.choose_profile_heroes(heroes)
    return {**data,'account_id':123,'heroes':heroes,'favorite_hero':favorite,'best_hero':best,
            'meta':meta(),'synced_at':datetime.now(timezone.utc).isoformat()}


def mock_sync(monkeypatch):
    fetch = AsyncMock(side_effect=lambda account_id: provider_data(account_id))
    monkeypatch.setattr(main, 'fetch_opendota', fetch)
    monkeypatch.setattr(main, 'fetch_current_meta', AsyncMock(return_value=meta()))
    return fetch


def test_sync_routes_restart_and_single_player_replacement(monkeypatch):
    fetch = mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        assert client.get('/player/overview').status_code == 409
        first = client.post(f'/sync/{main.STEAM_ID64_BASE+123}')
        assert first.status_code == 200
        assert first.json()['account_id'] == 123
        for route in ('overview','heroes','trends','winrate-history','yearly','matches','stats'):
            assert client.get(f'/player/{route}').status_code == 200
        assert client.get('/player/123/stats').status_code == 200
        assert client.get('/player/456/stats').status_code == 404
        first_page = client.get('/player/matches?limit=5').json()
        assert first_page['matches'][0]['hero_name'] == 'Anti-Mage'
        assert 'hero_image_url' in first_page['matches'][0]
        assert client.get('/player/stats').json()['recent_matches'] == first_page['matches']
        overview_recent = client.get('/player/stats?recent_limit=20').json()['recent_matches']
        assert len(overview_recent) == 20
        assert overview_recent == client.get('/player/matches?limit=20').json()['matches']
        assert client.get('/player/stats?recent_limit=21').status_code == 422
        assert client.get('/player/matches?limit=5&offset=5').json()['has_more']
        assert client.get('/player/matches?offset=100').json()['matches'] == []
        assert client.get('/player/winrate-history').json()['group_count'] == 3
        assert client.post('/sync/123').json()['cached'] is True
        assert fetch.await_count == 1
        assert client.post('/sync/456').status_code == 429
        main.LAST_SYNC_ATTEMPT = float('-inf')
        assert client.post('/sync/456').status_code == 200
        assert client.get('/player/overview').json()['account_id'] == 456
        with database.SessionLocal() as db:
            assert [row.account_id for row in db.query(database.User).all()] == [456]
            assert db.query(database.ActiveSnapshot).count() == 1
    main.ACTIVE_PLAYER_CACHE = None
    with TestClient(main.app) as client:
        assert client.get('/player/overview').json()['account_id'] == 456
        result = client.get('/player/trends').json()
        assert [h['hero_id'] for h in result['recommendations']] == [1, 8]


def test_manual_positions_override_provider_recommendations():
    result = main.build_recommendations(cache(), 10)
    assert [h['hero_id'] for h in result['recommendations']] == [1, 8]
    assert 1 not in main.curated_positions(61)
    assert 1 not in main.curated_positions(106)
    assert main.curated_positions(145) == [1,2]


def test_unknown_attributes_do_not_earn_points():
    row = main.build_recommendations(cache(), 10)['recommendations'][0]
    assert 'same_primary_attribute' not in row['score_breakdown']
    assert 'same_attack_type' not in row['score_breakdown']


@pytest.mark.parametrize('lane,hero_id,expected', [(3,86,4),(3,2,3),(4,86,None),(1,5,5),(1,8,1),(3,14,None)])
def test_lane_estimates_are_not_position_numbers(lane,hero_id,expected):
    assert main.match_position({'lane_role':lane,'gpm':None},{'hero_id':hero_id}) == expected


def test_unknown_hero_does_not_default_to_mid():
    assert main.estimated_positions({'hero_id':9999,'roles':['Nuker']}) == []
    c = cache()
    c['heroes'] = main.build_heroes([{'hero_id':9999,'games':1,'win':1}],{})
    c['recent'] = [match(1,9999) | {'position':None}]
    result = main.build_recommendations(c,10)
    assert result['analysis']['focus_hero']['position'] is None
    assert result['recommendations'] == []


def test_position_override_and_validation(monkeypatch):
    mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        client.post('/sync/123')
        result=client.get('/player/trends?position=2').json()
        assert result['analysis']['focus_hero']['position'] == 2
        assert result['analysis']['focus_hero']['position_is_estimated'] is False
        for url in ['/player/trends?position=6','/player/trends?limit=11','/player/matches?limit=21','/sync/0']:
            response=client.post(url) if '/sync/' in url else client.get(url)
            assert response.status_code == 422


@pytest.mark.parametrize('value',[None,'false',{},[],2])
def test_unknown_outcomes_are_excluded(value):
    assert main.normalize_stratz_match({'id':1,'players':[{'heroId':1,'isVictory':value}]}) is None
    assert main.normalize_opendota_match({'match_id':1,'player_slot':0,'radiant_win':value}) is None


def test_invalid_player_slot_is_excluded():
    assert main.player_won({'radiant_win':True,'player_slot':'invalid'}) is None
    assert main.player_won({'radiant_win':True,'player_slot':128}) is False


def test_wilson_and_profile_heroes():
    assert main.wilson_score(1,1) < main.wilson_score(60,100)
    heroes=main.build_heroes([{'hero_id':1,'games':100,'win':60},{'hero_id':8,'games':1,'win':1}],{})
    favorite,best=main.choose_profile_heroes(heroes)
    assert favorite['hero_id'] == best['hero_id'] == 1


def test_history_sorted_before_limit_deduplicated_and_grouped():
    rows=[match(i) for i in range(1,1101)]
    rows += [match(1100),{'match_id':2000,'is_win':None}]
    groups=main.build_match_group_chart(rows)
    assert len(groups) == 50 and all(g['matches']==20 for g in groups)
    assert sum(g['wins'] for g in groups) == 500
    assert [m['match_id'] for m in main.bounded_matches(rows,2)] == [1100,1099]
    assert [g['matches'] for g in main.build_match_group_chart([match(i) for i in range(1,42)])] == [1,20,20]


def test_missing_metrics_remain_unknown():
    c=cache()
    c['recent']=[match(1), {'match_id':2,'is_win':False,'gpm':None}]
    overview=main.overview_payload(c)
    assert overview['recent_gpm'] == 500
    assert overview['recent_kda_matches'] == 1
    serialized=main.serialize_match(c['recent'][1])
    assert serialized['kills'] is None and serialized['duration'] is None


def test_all_ranks_include_immortal_but_immortal_request_uses_divine(monkeypatch):
    monkeypatch.setattr(main,'HERO_STATS_CACHE',{1:{'1_pick':100,'1_win':50,'7_pick':40,'7_win':20,'8_pick':100,'8_win':90}})
    all_meta=main.build_opendota_meta(0,[{'hero_id':1}])
    assert all_meta['heroes'][1]['positions'][1]['matches'] == 240
    divine=main.build_opendota_meta(80,[{'hero_id':1}])
    assert divine['rank_bracket']=='DIVINE' and divine['rank_fallback_applied']
    assert divine['heroes'][1]['positions'][1]['matches']==40


def test_catalog_refresh_and_real_timestamp(monkeypatch):
    items=[{'id':1,'localized_name':'Anti-Mage','1_pick':100,'1_win':50}]
    fetch=AsyncMock(return_value=items)
    monkeypatch.setattr(main,'get_json',fetch)
    monkeypatch.setattr(main,'request_json',AsyncMock(return_value={'result':{'data':{'heroes':[]}}}))
    async def scenario():
        await main.fetch_hero_catalog(None)
        original=main.HERO_STATS_FETCHED_AT
        await main.fetch_hero_catalog(None)
        assert fetch.await_count == 1
        assert main.build_opendota_meta(10,[{'hero_id':1}])['collected_at']==original
        main.HERO_STATS_FETCHED_MONOTONIC -= main.CATALOG_TTL_SECONDS+1
        await main.fetch_hero_catalog(None)
        assert fetch.await_count == 2
        main.HERO_STATS_FETCHED_MONOTONIC -= main.CATALOG_TTL_SECONDS+1
        fetch.side_effect=main.ProviderError('offline')
        last=main.HERO_STATS_FETCHED_AT
        await main.fetch_hero_catalog(None)
        assert main.HERO_STATS_FETCHED_AT == last
        assert main.build_opendota_meta(10,[{'hero_id':1}])['stale']
        main.HERO_STATS_FETCHED_MONOTONIC -= main.MAX_STALE_SECONDS+1
        result=await main.fetch_hero_catalog(None)
        assert len(result)==len(main.HERO_POSITION_PROFILES)
        assert main.HERO_STATS_CACHE=={} and main.HERO_STATS_FETCHED_AT is None
    run(scenario())


def test_meta_cache_refresh_and_stale_fallback(monkeypatch):
    monkeypatch.setenv('STRATZ_TOKEN','test')
    fetch=AsyncMock(return_value=meta())
    monkeypatch.setattr(main,'fetch_stratz_meta',fetch)
    async def scenario():
        await main.fetch_current_meta(80,[])
        await main.fetch_current_meta(80,[])
        assert fetch.await_count==1
        saved=main.META_CACHE[80][1]
        main.META_CACHE[80]=(time.monotonic()-main.META_TTL_SECONDS-1,saved)
        fetch.side_effect=main.ProviderError('offline')
        result=await main.fetch_current_meta(80,[])
        assert result['stale'] and result['collected_at']==saved['collected_at']
    run(scenario())


def test_stored_meta_does_not_stay_fresh_forever(monkeypatch):
    c=cache()
    c['meta']['collected_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    monkeypatch.setattr(main,'ACTIVE_PLAYER_CACHE',c)
    result=main.active_cache()
    assert result['meta']['stale'] and result['meta']['heroes']=={}
    assert c['meta']['heroes']  # Reading must not mutate stored state.


def test_opendota_partial_failure_and_shapes(monkeypatch):
    good={'match_id':1,'hero_id':1,'player_slot':0,'radiant_win':True,'start_time':1700000000}
    async def get(client,path,params=None):
        if path.endswith('/matches'): return [None,good]
        if path.endswith('/recentMatches'): return {'wrong':'shape'}
        if path.endswith('/heroes'): return [None]
        raise main.ProviderError('offline')
    monkeypatch.setattr(main,'get_json',get)
    monkeypatch.setattr(main,'fetch_hero_catalog',AsyncMock(return_value={}))
    data=run(main.fetch_opendota(123))
    assert len(data['history'])==len(data['recent'])==1
    assert data['total_wins']==1 and data['total_losses']==0
    assert data['hero_stats_scope']['kind']=='sampled_history'
    assert data['totals_scope']=='sampled_history' and data['warnings']


def test_opendota_bounds_matches_and_details(monkeypatch):
    async def get(client,path,params=None):
        if path.endswith('/matches') or path.endswith('/recentMatches'):
            return [{'match_id':i,'hero_id':1,'player_slot':0,'radiant_win':True,'start_time':1700000000+i} for i in range(1,1101)]
        if path.endswith('/heroes'):return [{'hero_id':1,'games':5000,'win':2500}]
        if path.endswith('/wl'):return {'win':2500,'lose':2500}
        return {'profile':{'personaname':'Name'},'rank_tier':80}
    monkeypatch.setattr(main,'get_json',get)
    monkeypatch.setattr(main,'fetch_hero_catalog',AsyncMock(return_value={}))
    data=run(main.fetch_opendota(123))
    assert len(data['history'])==1000 and len(data['recent'])==20
    assert data['hero_stats_scope']['kind']=='provider_aggregate'
    assert data['history'][0]['match_id']==1100


def test_stratz_bounded_pagination_and_unknown_results(monkeypatch):
    monkeypatch.setenv('STRATZ_TOKEN','test')
    queries=[]
    async def gql(client,query):
        queries.append(query)
        offset=0 if len(queries)==1 else (len(queries)-1)*100
        rows=[{'id':i+1,'startDateTime':1700000000+i,'players':[{'heroId':1,'isVictory':None if i==0 else True}]} for i in range(offset,offset+100)]
        return {'player':{'history':rows,'recent':rows[:20],'matchCount':5000,'winCount':3000,'steamAccount':{'seasonRank':80}}}
    monkeypatch.setattr(main,'graphql',gql)
    monkeypatch.setattr(main,'fetch_hero_catalog',AsyncMock(return_value={}))
    data=run(main.fetch_stratz(123))
    assert len(queries)==10 and 'skip: 900' in queries[-1]
    assert len(data['history'])==999 and len(data['recent'])==19
    assert data['player_heroes'][0]['games']==999
    assert data['hero_stats_scope']['matches']==999 and data['total_wins']==3000


def test_stratz_repeated_page_stops(monkeypatch):
    monkeypatch.setenv('STRATZ_TOKEN','test')
    rows=[{'id':i,'players':[{'heroId':1,'isVictory':True}]} for i in range(1,101)]
    gql=AsyncMock(return_value={'player':{'history':rows,'recent':[]}})
    monkeypatch.setattr(main,'graphql',gql)
    monkeypatch.setattr(main,'fetch_hero_catalog',AsyncMock(return_value={}))
    data=run(main.fetch_stratz(123))
    assert gql.await_count==2 and len(data['history'])==100
    assert any('repeated' in x for x in data['warnings'])


def test_retry_and_invalid_json():
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,headers={'Retry-After':'0'}) if len(calls)==1 else httpx.Response(200,json={'ok':True})
    async def scenario():
        async with REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler)) as client:
            assert await main.request_json(client,'GET','https://example.test') == {'ok':True}
        async with REAL_ASYNC_CLIENT(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='oops'))) as client:
            with pytest.raises(main.ProviderError):
                await main.request_json(client,'GET','https://example.test')
    run(scenario())
    assert len(calls)==2


def test_graphql_invalid_shape_is_provider_error(monkeypatch):
    monkeypatch.setenv('STRATZ_TOKEN','test')
    monkeypatch.setattr(main,'request_json',AsyncMock(return_value=[]))
    with pytest.raises(main.ProviderError):
        run(main.graphql(None,'query {}'))


def test_fallback_route_and_failed_sync_preserve_existing(monkeypatch):
    mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        client.post('/sync/123')
        main.LAST_SYNC_ATTEMPT=float('-inf')
        monkeypatch.setattr(main,'fetch_opendota',AsyncMock(side_effect=main.ProviderError('offline')))
        data=provider_data(456) | {'source':'STRATZ'}
        monkeypatch.setattr(main,'fetch_stratz',AsyncMock(return_value=data))
        assert client.post('/sync/456').json()['source']=='STRATZ'
        main.LAST_SYNC_ATTEMPT=float('-inf')
        monkeypatch.setattr(main,'fetch_stratz',AsyncMock(side_effect=main.ProviderError('offline')))
        assert client.post('/sync/789').status_code==502
        assert client.get('/player/overview').json()['account_id']==456
        assert database.load_active_player()['account_id']==456


def test_save_failure_retains_memory_and_db(monkeypatch):
    mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        client.post('/sync/123')
        main.LAST_SYNC_ATTEMPT=float('-inf')
        def fail(cache):raise RuntimeError('simulated disk failure')
        monkeypatch.setattr(main,'save_active_player',fail)
        assert client.post('/sync/456').status_code==500
        assert client.get('/player/overview').json()['account_id']==123
        assert database.load_active_player()['account_id']==123


def test_db_transaction_rolls_back_after_summary_delete():
    database.init_db()
    c=cache()
    database.save_active_player(c)
    def fail(session,*args):raise RuntimeError('simulated flush failure')
    event.listen(database.SessionLocal,'before_flush',fail)
    try:
        with pytest.raises(RuntimeError):
            database.save_active_player(c | {'account_id':456})
    finally:
        event.remove(database.SessionLocal,'before_flush',fail)
    with database.SessionLocal() as db:
        assert [u.account_id for u in db.query(database.User).all()]==[123]
    assert database.load_active_player()['account_id']==123


def test_legacy_migration_and_concurrent_startup():
    with database.engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (account_id INTEGER PRIMARY KEY, persona_name VARCHAR, rank_tier INTEGER, total_wins INTEGER, total_losses INTEGER)'))
        connection.execute(text("INSERT INTO users VALUES (123,'Existing',80,10,5)"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _:database.init_db(),range(3)))
    assert 'best_hero_score' in {c['name'] for c in inspect(database.engine).get_columns('users')}
    with database.SessionLocal() as db:
        assert db.get(database.User,123).persona_name=='Existing'


def test_snapshot_bound_is_enforced():
    database.init_db()
    c=cache()
    c['history']=[match(i) for i in range(1,1002)]
    with pytest.raises(ValueError):database.save_active_player(c)


def test_busy_sync_is_rejected(monkeypatch):
    async def scenario():
        async with main.SYNC_LOCK:
            with pytest.raises(main.HTTPException) as error:
                await main.sync_player(123)
            assert error.value.status_code==409
    run(scenario())


def test_real_provider_adapter_through_fastapi_http_mock(monkeypatch):
    requests=[]
    monkeypatch.setenv('OPENDOTA_API_KEY','test-key')
    def handler(request):
        requests.append(request)
        path=request.url.path
        if path.endswith('/herolist'):
            return httpx.Response(200,json={'result':{'data':{'heroes':[{'id':8,'complexity':2}]}}})
        assert request.url.params['api_key']=='test-key'
        if path.endswith('/heroStats'):
            return httpx.Response(200,json=[{'id':h,'localized_name':name,'primary_attr':'agi','attack_type':'Melee','roles':['Carry'],'7_pick':1000,'7_win':550} for h,name in [(1,'Anti-Mage'),(8,'Juggernaut')]])
        if path.endswith('/matches') or path.endswith('/recentMatches'):
            return httpx.Response(200,json=[{'match_id':i,'hero_id':1,'player_slot':0,'radiant_win':True,'start_time':1700000000+i,'lane_role':1,'kills':5,'deaths':2,'assists':3,'gold_per_min':500,'xp_per_min':600,'duration':1800} for i in range(1,22)])
        if path.endswith('/heroes'):
            return httpx.Response(200,json=[{'hero_id':1,'games':100,'win':60},{'hero_id':8,'games':50,'win':30}])
        if path.endswith('/wl'):return httpx.Response(200,json={'win':90,'lose':60})
        if path.endswith('/players/123'):return httpx.Response(200,json={'profile':{'personaname':'Actual adapter test'},'rank_tier':80})
        raise AssertionError(path)
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler),**kwargs))
    with TestClient(main.app) as client:
        response=client.post('/sync/123')
        assert response.status_code==200, response.text
        assert response.json()['detailed_matches_cached']==20
        assert response.json()['meta_rank_bracket']=='DIVINE'
        result=client.get('/player/trends').json()
        assert result['meta']['position_data_exact'] is False
        assert result['recommendations'] == result['worth_learning'] == []
        assert result['excluded_by_reason']['current_patch_unverified'] == 1
        assert result['analysis']['focus_hero']['position']==1
        assert client.get('/player/overview').json()['recent_kda']==4
    assert len(requests)==7


def test_stratz_meta_parsing_handles_out_of_position_stats(monkeypatch):
    monkeypatch.setenv('STRATZ_TOKEN','test')
    monkeypatch.setattr(main,'graphql',AsyncMock(return_value={'heroStats':{
        'p1':[{'heroId':61,'matchCount':1000,'winCount':600},{'heroId':8,'matchCount':1000,'winCount':550}],
        'p2':[],'p3':[],'p4':[],'p5':[],
    }}))
    actual=run(main.fetch_stratz_meta(80))
    c=cache() | {'meta':actual}
    # A weekly endpoint without a verified underlying window cannot establish current-patch meta.
    assert main.build_recommendations(c,10)['recommendations']==[]
    c['meta'] = {**meta(), **actual, **{k:meta()[k] for k in ('patch','patch_coverage_verified','window_start','window_end')}}
    assert [h['hero_id'] for h in main.build_recommendations(c,10)['recommendations']]==[8]
    assert actual['rank_bracket']=='DIVINE'


def test_corrupt_snapshot_startup_requests_resync():
    database.init_db()
    with database.SessionLocal.begin() as db:
        db.add(database.ActiveSnapshot(id=1,payload='not-json'))
    with TestClient(main.app) as client:
        assert client.get('/player/overview').status_code==409


def recommendation_scenario():
    c = cache()
    ids = (1, 10, 109, 8, 4, 32, 86, 5, 21)
    c['heroes'] = main.build_heroes([
        {'hero_id': h, 'games': 10000 if h in (4, 32, 10, 109) else 50,
         'win': 9000 if h in (4, 32, 10, 109) else 25} for h in ids
    ], {})
    rates = {10: 54, 109: 53, 8: 52, 4: 47, 32: 46, 86: 53, 5: 52, 21: 52}
    c['meta']['heroes'] = {
        h: {'positions': {p: {'matches': 50000, 'wins': int(500*wr), 'winrate': wr, 'pick_rate': 10}
                          for p in (1, 2, 3, 4, 5)}} for h, wr in rates.items()
    }
    return c


@pytest.mark.parametrize('position', [3, 4, 5])
def test_core_heroes_cannot_be_supports_or_offlaners_despite_extreme_experience(position):
    result = main.build_recommendations(recommendation_scenario(), 10, position)
    assert result['requested_position'] == result['target_position'] == position
    ids = {h['hero_id'] for h in result['recommendations']}
    assert not {10, 109, 8}.intersection(ids)
    if position == 4:
        assert 86 in ids
    assert all(position in main.curated_positions(h) for h in ids)


def test_weak_meta_is_not_rescued_by_ten_thousand_games():
    result = main.build_recommendations(recommendation_scenario(), 10, 1)
    assert {h['hero_id'] for h in result['recommendations']} == {10, 109, 8, 21}
    assert result['excluded_by_reason']['below_next_games_floor'] == 2
    assert len(result['recommendations']) < 10  # Do not fill remaining slots with weak picks.


def test_no_permanent_ban_when_bloodseeker_and_riki_meta_improves():
    c = recommendation_scenario()
    for h in (4, 32):
        c['meta']['heroes'][h]['positions'][1]['winrate'] = 55
    result = main.build_recommendations(c, 10, 1)
    assert {4,32}.issubset({h['hero_id'] for h in result['recommendations']})


def test_meta_leads_but_comfort_still_matters_for_close_candidates():
    c = recommendation_scenario()
    c['heroes'] = main.build_heroes([
        {'hero_id':1,'games':100,'win':50},
        {'hero_id':8,'games':0,'win':0},
        {'hero_id':32,'games':10000,'win':9000},
    ],{})
    c['meta']['heroes'] = {h: {'positions': {1: {'matches':50000,'winrate':wr}}} for h,wr in [(8,54),(32,49)]}
    assert main.build_recommendations(c,10,1)['recommendations'][0]['hero_id'] == 8
    c['meta']['heroes'][8]['positions'][1]['winrate'] = 52
    c['meta']['heroes'][32]['positions'][1]['winrate'] = 51
    assert main.build_recommendations(c,10,1)['recommendations'][0]['hero_id'] == 32


def test_high_absolute_match_count_does_not_rescue_a_fringe_role():
    c = recommendation_scenario()
    c['meta']['heroes'][21]['positions'] = {
        4:{'matches':10000,'winrate':65}, 2:{'matches':990000,'winrate':55},
    }
    result = main.build_recommendations(c,10,4)
    assert 21 not in {h['hero_id'] for h in result['recommendations']}
    assert result['excluded_by_reason']['rare_position'] == 1


def test_tiny_sample_and_invalid_meta_are_excluded():
    c = recommendation_scenario()
    c['meta']['heroes'][8]['positions'][1] = {'matches':10,'winrate':100}
    c['meta']['heroes'][10]['positions'][1]['winrate'] = float('nan')
    result = main.build_recommendations(c,10,1)
    assert not {8,10}.intersection({h['hero_id'] for h in result['recommendations']})
    assert result['excluded_by_reason']['insufficient_meta'] == 1
    assert result['excluded_by_reason']['invalid_meta'] == 1


def test_role_switch_does_not_apply_carry_similarity_to_supports():
    c = recommendation_scenario()
    c['heroes'][0]['roles'] = ['Carry']
    result = main.build_recommendations(c,10,4)
    assert all(4 in main.curated_positions(h) for h in result['analysis']['similarity_anchor_ids'])
    for hero in result['recommendations']:
        assert hero['score_context']['playstyle_similarity'] == 0
        assert 'same_primary_attribute' not in hero['score_breakdown']


def test_role_switch_selects_compatible_recent_focus_when_available():
    c = recommendation_scenario()
    c['recent'] += [match(999,86) | {'position':4}]
    c['recent'] = [c['recent'][-1]] + c['recent'][:-1]
    result = main.build_recommendations(c,10,4)
    assert result['analysis']['focus_hero']['hero_id'] == 86
    assert result['analysis']['similarity_applied'] is True


def test_position_parameter_mistakes_are_not_silently_ignored(monkeypatch):
    mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        client.post('/sync/123')
        for query in ('pos=4','role=4','position=1&position=4'):
            assert client.get('/player/trends?'+query).status_code == 422
        result = client.get('/player/trends?position=4').json()
        assert result['target_position'] == 4
        assert result['scoring_version'] == '3.2-current-pub-personal'


def test_expired_meta_refreshes_without_syncing_player_again(monkeypatch):
    fetch_player = mock_sync(monkeypatch)
    catalog = AsyncMock(return_value={})
    new_meta = AsyncMock(return_value=meta())
    with TestClient(main.app) as client:
        client.post('/sync/123')
        main.ACTIVE_PLAYER_CACHE['meta']['collected_at'] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        monkeypatch.setattr(main,'fetch_hero_catalog',catalog)
        monkeypatch.setattr(main,'fetch_current_meta',new_meta)
        assert client.get('/player/trends?position=1').status_code == 200
        assert client.get('/player/trends?position=1').status_code == 200
        assert catalog.await_count == new_meta.await_count == fetch_player.await_count == 1
        assert main.ACTIVE_PLAYER_CACHE['meta']['collected_at'] == new_meta.return_value['collected_at']


def test_failed_refresh_uses_backoff_and_does_not_call_stale_data_live(monkeypatch):
    c = cache()
    c['meta']['collected_at'] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    monkeypatch.setattr(main,'ACTIVE_PLAYER_CACHE',c)
    fetch = AsyncMock(return_value=c['meta'])
    monkeypatch.setattr(main,'fetch_current_meta',fetch)
    monkeypatch.setattr(main,'fetch_hero_catalog',AsyncMock(return_value={}))
    async def scenario():
        first = await main.recommendation_cache(c)
        second = await main.recommendation_cache(first)
        assert first['meta']['stale'] and second['meta']['stale']
        assert fetch.await_count == 1
    run(scenario())


def test_meta_refresh_does_not_overwrite_a_concurrently_switched_player(monkeypatch):
    c = cache()
    c['meta']['collected_at'] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    monkeypatch.setattr(main,'ACTIVE_PLAYER_CACHE',c)
    async def switch(_):
        main.ACTIVE_PLAYER_CACHE = cache() | {'account_id':456}
        return {}
    monkeypatch.setattr(main,'fetch_hero_catalog',switch)
    monkeypatch.setattr(main,'fetch_current_meta',AsyncMock(return_value=meta()))
    result = run(main.recommendation_cache(c))
    assert result['account_id'] == 123
    assert main.ACTIVE_PLAYER_CACHE['account_id'] == 456


def test_vite_origins_can_call_api_but_other_origins_cannot():
    with TestClient(main.app) as client:
        allowed = client.options('/sync/123', headers={
            'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'POST',
            'Access-Control-Request-Headers':'content-type',
        })
        assert allowed.status_code == 200
        assert allowed.headers['access-control-allow-origin'] == 'http://localhost:5173'
        assert 'POST' in allowed.headers['access-control-allow-methods']
        blocked = client.options('/sync/123', headers={
            'Origin':'http://evil.example',
            'Access-Control-Request-Method':'POST',
        })
        assert blocked.status_code == 400
        assert 'access-control-allow-origin' not in blocked.headers


def recent_match(i, hero=8, position=1, win=True, days=1):
    return {'match_id': 10000+i, 'hero_id': hero, 'position': position,
            'is_win': win, 'start_time': int((datetime.now(timezone.utc)-timedelta(days=days)).timestamp())}


def test_two_tracks_keep_familiar_best_and_offer_low_experience_alternatives():
    c = cache()
    result = main.build_recommendations(c, 10, 1)
    assert result['recommendations'] == result['recommended_for_next_games']
    assert result['recommended_for_next_games'][0]['hero_id'] == 1  # Do not exclude focus hero.
    assert {h['hero_id'] for h in result['worth_learning']} == {8}
    assert all(h['track'] == 'worth_learning' for h in result['worth_learning'])
    assert all(h['track'] == 'next_games' for h in result['recommended_for_next_games'])


def test_explicit_role_works_without_recent_focus_or_personal_history():
    c = cache(); c['recent'] = []; c['history'] = []
    c['heroes'] = main.build_heroes([], {})
    result = main.build_recommendations(c, 10, 1)
    assert result['analysis']['focus_hero'] is None
    assert result['recommended_for_next_games'] and result['worth_learning']
    assert main.build_recommendations(c, 10)['message'].startswith('Select position')


def test_lifetime_winrate_is_not_used_as_current_role_success():
    c = cache()
    before = main.build_recommendations(c, 10, 1)
    for h in c['heroes']:
        h['winrate'] = 100 if h['hero_id'] == 8 else 0
    after = main.build_recommendations(c, 10, 1)
    assert [(h['hero_id'], h['recommendation_score']) for h in before['recommendations']] == [
        (h['hero_id'], h['recommendation_score']) for h in after['recommendations']]


def test_off_role_wins_do_not_inflate_personal_performance():
    c = cache(); c['history'] = [recent_match(i, position=2) for i in range(10)]
    c['recent'] = []
    row = next(h for h in main.build_recommendations(c,10,1)['recommendations'] if h['hero_id']==8)
    assert row['personal_evidence']['role_games'] == 0
    assert row['score_breakdown']['personal_performance'] == 0


def test_recent_role_evidence_changes_ranking_and_is_deduplicated():
    c = cache(); c['history'] = [recent_match(i) for i in range(20)]
    c['recent'] = c['history'][-10:]
    result = main.build_recommendations(c,10,1)
    row = result['recommendations'][0]
    assert row['hero_id'] == 8
    assert row['personal_evidence']['role_games'] == 20
    assert 0 < row['score_context']['personal_weight'] < 1
    assert row['score_breakdown']['personal_performance'] > 0


def test_old_future_unknown_position_and_unknown_outcomes_do_not_affect_role_rate():
    c = cache(); c['recent'] = []
    c['history'] = [recent_match(1, days=91), recent_match(2, days=-1),
                    recent_match(3,position=None), recent_match(4,win=None)]
    row = next(h for h in main.build_recommendations(c,10,1)['recommendations'] if h['hero_id']==8)
    assert row['personal_evidence']['role_games'] == 0
    assert row['score_breakdown']['personal_performance'] == 0


def test_recent_results_outweigh_old_results_within_window():
    now = datetime.now(timezone.utc)
    c = cache(); c['recent'] = []
    c['history'] = [recent_match(1,win=True,days=1), recent_match(2,win=False,days=60)]
    ev = main.recent_role_evidence(c,1,now)[8]
    assert ev['weighted_wins'] / ev['weighted_games'] > 0.75


def test_sparse_success_is_shrunk_more_than_substantial_evidence():
    small = main.adjusted_personal_performance(4,5,0.53)
    large = main.adjusted_personal_performance(60,100,0.53)
    assert 0.53 < small < large < 0.60


def test_fallback_and_stale_meta_have_less_influence_and_visible_labels(monkeypatch):
    monkeypatch.setenv('REQUIRE_CURRENT_PATCH_META','false')
    c = cache()
    exact = main.build_recommendations(c,10,1)['recommendations'][0]
    c['meta']['position_data_exact'] = False
    fallback_result = main.build_recommendations(c,10,1)
    fallback = fallback_result['recommendations'][0]
    assert fallback['score_breakdown']['current_meta'] < exact['score_breakdown']['current_meta']
    assert fallback['meta_scope'] == 'rank_all_positions_proxy'
    assert fallback_result['meta']['patch_coverage_verified'] is True
    c['meta']['stale'] = True
    stale = main.build_recommendations(c,10,1)['recommendations'][0]
    assert stale['score_breakdown']['current_meta'] < fallback['score_breakdown']['current_meta']


def test_expired_meta_is_not_scored_even_in_direct_engine_call():
    c = cache()
    c['meta']['collected_at'] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    result = main.build_recommendations(c,10,1)
    assert result['recommendations'] == result['worth_learning'] == []
    assert result['message']


def test_weak_meta_needs_recent_role_evidence_not_lifetime_wins():
    c = recommendation_scenario()
    assert 4 not in {h['hero_id'] for h in main.build_recommendations(c,10,1)['recommendations']}
    c['history'] = [recent_match(i,hero=4,win=i<28) for i in range(40)]
    c['recent'] = []
    result = main.build_recommendations(c,10,1)
    assert 4 in {h['hero_id'] for h in result['recommendations']}
    assert 4 not in {h['hero_id'] for h in result['worth_learning']}


def test_both_tracks_enforce_role_policy_and_limit():
    c = recommendation_scenario()
    for h in c['heroes']: h['games'] = 0
    result = main.build_recommendations(c,2,4)
    for key in ('recommended_for_next_games','worth_learning'):
        assert 0 < len(result[key]) <= 2
        assert all(4 in main.curated_positions(h['hero_id']) for h in result[key])
        assert not {10,109}.intersection(h['hero_id'] for h in result[key])


def test_mastered_complex_hero_has_less_learning_cost():
    c = cache(); c['recent'] = []; c['history'] = []
    hero = next(h for h in c['heroes'] if h['hero_id']==8)
    hero['complexity'] = 3; hero['games'] = 0
    before_result = main.build_recommendations(c,10,1)
    assert 8 not in {h['hero_id'] for h in before_result['recommendations']}
    before = next(h for h in before_result['worth_learning'] if h['hero_id']==8)
    hero['games'] = 100
    after = next(h for h in main.build_recommendations(c,10,1)['recommendations'] if h['hero_id']==8)
    assert after['score_breakdown']['learning_cost'] > before['score_breakdown']['learning_cost']
    assert 8 not in {h['hero_id'] for h in main.build_recommendations(c,10,1)['worth_learning']}


def test_score_explanation_sums_and_json_contains_no_nan():
    result = main.build_recommendations(cache(),10,1)
    json.dumps(result, allow_nan=False)
    for key in ('recommended_for_next_games','worth_learning'):
        for hero in result[key]:
            assert sum(hero['score_breakdown'].values()) == pytest.approx(hero['recommendation_score'],abs=0.0003)
            assert hero['reasons']
    assert result['score_kind'] == 'ranking_utility_not_win_probability'


def test_lightweight_opendota_history_preserves_provider_position():
    row = main.normalize_opendota_match({'match_id':123,'hero_id':86,'player_slot':0,
                                       'radiant_win':True,'position_est':4,'lane_role':3})
    assert row['position'] == 4
    assert row['position_source'] == 'provider estimate'
    assert row['lane_role'] == 3


def test_two_track_http_contract_survives_snapshot_restart(monkeypatch):
    mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        client.post('/sync/123')
    main.ACTIVE_PLAYER_CACHE = None
    with TestClient(main.app) as client:
        response = client.get('/player/trends?position=1&limit=1')
        assert response.status_code == 200
        body = response.json()
        assert body['recommendations'] == body['recommended_for_next_games']
        assert len(body['recommended_for_next_games']) == len(body['worth_learning']) == 1


def test_meepo_is_mid_only_in_both_recommendation_tracks():
    c = cache(); c['heroes'] = main.build_heroes([], {})
    c['meta']['heroes'] = {82:{'positions':{1:{'matches':10000,'winrate':60},
                                                   2:{'matches':10000,'winrate':60}}}}
    for key in ('recommendations','worth_learning'):
        assert main.build_recommendations(c,10,1)[key] == []
        assert [h['hero_id'] for h in main.build_recommendations(c,10,2)[key]] == [82]


def test_established_pl_has_no_beginner_penalty_and_beats_wk_in_reported_scenario(monkeypatch):
    monkeypatch.setenv('REQUIRE_CURRENT_PATCH_META','false')
    c = cache(); c['recent'] = []; c['history'] = [recent_match(1,hero=12,position=None)]
    c['heroes'] = main.build_heroes([{'hero_id':42,'games':242,'win':128},
                                   {'hero_id':12,'games':648,'win':336}],
        main.catalog_from_items([{'id':42,'complexity':1},{'id':12,'complexity':2}]))
    c['meta']['position_data_exact'] = False
    c['meta']['heroes'] = {42:{'positions':{1:{'matches':37050,'winrate':52.97}}},
                          12:{'positions':{1:{'matches':55133,'winrate':53.26}}}}
    rows = main.build_recommendations(c,10,1)['recommendations']
    assert [h['hero_id'] for h in rows] == [12,42]
    assert rows[0]['score_breakdown']['learning_cost'] == 0
    assert rows[0]['score_breakdown']['personal_performance'] == 0


@pytest.mark.parametrize('hero_id,position', [(50,2),(82,1),(135,1),(10,4),(109,5),(94,2)])
def test_pro_or_fringe_statistics_never_override_strict_pub_roles(hero_id, position):
    c = cache()
    c['meta']['heroes'] = {hero_id:{'positions':{position:{'matches':100000,'winrate':90}}}}
    result = main.build_recommendations(c,10,position)
    assert result['recommendations'] == result['worth_learning'] == []
    assert result['policy']['professional_role_overrides_allowed'] is False


def test_all_role_fallback_never_becomes_secondary_position_evidence(monkeypatch):
    monkeypatch.setattr(main,'HERO_STATS_CACHE',{42:{'4_pick':10000,'4_win':6000},
                                               86:{'4_pick':10000,'4_win':5500}})
    result = main.build_opendota_meta(40,[{'hero_id':42},{'hero_id':86}])
    assert set(result['heroes'][42]['positions']) == {1}
    assert set(result['heroes'][86]['positions']) == {4,5}
    # Cached v3.0 proxies may still duplicate rates: the engine checks them too.
    c = cache()
    c['meta'] = meta() | {'position_data_exact':False,
        'heroes':{42:{'positions':{3:{'matches':10000,'winrate':60}}}}}
    response = main.build_recommendations(c,10,3)
    assert response['recommendations'] == response['worth_learning'] == []
    assert response['excluded_by_reason']['current_patch_unverified'] == 1


def test_measured_secondary_role_is_allowed_only_within_strict_policy():
    c = cache()
    c['meta']['heroes'] = {42:{'positions':{1:{'matches':5000,'winrate':54},
                                          3:{'matches':5000,'winrate':54}}}}
    assert [h['hero_id'] for h in main.build_recommendations(c,10,3)['recommendations']] == [42]


def test_draft_availability_filters_both_tracks_without_mutating_cache():
    c = cache(); original = copy.deepcopy(c)
    result = main.build_recommendations(c,10,1,{1,8})
    assert result['recommendations'] == result['worth_learning'] == []
    assert result['draft']['unavailable_hero_ids'] == [1,8]
    assert result['excluded_by_reason']['draft_unavailable'] == 2
    assert c == original


def test_recent_role_pool_bonus_is_bounded_and_neutral_without_role_labels():
    c = cache(); c['recent'] = []
    c['history'] = [recent_match(i) for i in range(50)]
    row = next(h for h in main.build_recommendations(c,10,1)['recommendations'] if h['hero_id']==8)
    assert 0 < row['score_breakdown']['recent_role_pool'] < 0.75
    for m in c['history']: m['position'] = None
    row = next(h for h in main.build_recommendations(c,10,1)['recommendations'] if h['hero_id']==8)
    assert row['score_breakdown']['recent_role_pool'] == 0


def test_complete_position_endpoint_and_old_snapshot_use_current_policy(monkeypatch):
    c = cache()
    next(h for h in c['heroes'] if h['hero_id']==135)['positions'] = [3,1]
    with TestClient(main.app) as client:
        monkeypatch.setattr(main,'ACTIVE_PLAYER_CACHE',c)
        catalog = client.get('/heroes/positions').json()
        assert len(catalog['heroes']) == len(main.HERO_POSITION_PROFILES)
        assert {h['hero_id'] for h in catalog['heroes']} == set(main.HERO_POSITION_PROFILES)
        for payload in (catalog, client.get('/player/heroes').json()):
            dawn = next(h for h in payload['heroes'] if h['hero_id']==135)
            assert dawn['positions'] == dawn['fallback_positions'] == [3]
    assert next(h for h in c['heroes'] if h['hero_id']==135)['positions'] == [3,1]


def test_pub_rank_override_and_draft_validation_are_request_local(monkeypatch):
    mock_sync(monkeypatch)
    with TestClient(main.app) as client:
        client.post('/sync/123')
        original = copy.deepcopy(main.ACTIVE_PLAYER_CACHE)
        fetch = AsyncMock(return_value=meta() | {'rank_bracket':'ARCHON',
             'requested_rank_bracket':'ARCHON','rank_fallback_applied':False})
        monkeypatch.setattr(main,'fetch_current_meta',fetch)
        monkeypatch.setattr(main,'fetch_hero_catalog',AsyncMock(return_value={}))
        result = client.get('/player/trends?position=1&meta_rank=4&unavailable_hero_ids=1&unavailable_hero_ids=1').json()
        assert result['requested_meta_rank'] == 4 and result['meta']['rank_bracket'] == 'ARCHON'
        assert [h['hero_id'] for h in result['recommendations']] == [8]
        assert result['draft']['unavailable_hero_ids'] == [1]
        fetch.assert_awaited_once_with(40,main.ACTIVE_PLAYER_CACHE['heroes'])
        assert main.ACTIVE_PLAYER_CACHE == original
        for query in ('meta_rank=2','meta_rank=7','meta_rank=4&meta_rank=5',
                      'unavailable_hero_ids=-1','unavailable_hero_ids=99999',
                      'unavailable_hero_ids=bad'):
            assert client.get('/player/trends?position=1&'+query).status_code == 422
        assert fetch.await_count == 1


@pytest.mark.parametrize("evidence", ["verified", "aggregate", "invalid_snapshot", "wrong_patch"])
def test_trends_can_use_disclosed_request_local_fallback(monkeypatch, evidence):
    player = cache()
    # The independent OpenDota aggregate has a strong Juggernaut row for each rank.
    monkeypatch.setattr(main, "HERO_STATS_CACHE", {8: {
        "7_pick": 2500, "7_win": 1500, "4_pick": 2000, "4_win": 1200,
    }})
    monkeypatch.setattr(main, "HERO_STATS_FETCHED_AT", datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr(main, "HERO_STATS_FETCHED_MONOTONIC", time.monotonic())
    refresh_catalog = AsyncMock(return_value={})
    monkeypatch.setattr(main, "fetch_hero_catalog", refresh_catalog)
    if evidence == "aggregate":
        player["meta"] = main.build_opendota_meta(player["rank"], player["heroes"])
    elif evidence == "invalid_snapshot":
        player["meta"] = {**player["meta"], "heroes": {}, "patch_coverage_verified": False}
    elif evidence == "wrong_patch":
        player["meta"]["patch"] = "old-patch"
    monkeypatch.setattr(main, "fetch_current_meta", AsyncMock(return_value=player["meta"]))
    original = copy.deepcopy(player)

    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "ACTIVE_PLAYER_CACHE", player)
        strict = client.get("/player/trends?position=1").json()
        response = client.get("/player/trends?position=1&allow_historical_meta=true")
        assert response.status_code == 200
        result = response.json()
        if evidence == "verified":
            assert result["meta"]["evidence_mode"] == "verified_current"
            assert result["recommendations"] == strict["recommendations"]
            refresh_catalog.assert_not_awaited()
        else:
            assert strict["meta"]["evidence_mode"] == "unavailable"
            assert strict["recommendations"] == strict["worth_learning"] == []
            assert result["meta"]["evidence_mode"] == "historical"
            assert result["meta"]["patch_coverage_verified"] is False
            assert result["meta"]["source"].startswith("OpenDota")
            assert [row["hero_id"] for row in result["recommendations"]] == [8]
            assert result["recommendations"][0]["meta_scope"] == "rank_all_positions_proxy"
            assert result["worth_learning"] == []
            preview = client.get("/player/trends?position=1&allow_historical_learning=true").json()
            assert preview["worth_learning_evidence_mode"] == "historical"
            assert [hero["hero_id"] for hero in preview["worth_learning"]] == [8]
            assert any("practice candidate" in reason for reason in preview["worth_learning"][0]["reasons"])

        if evidence == "invalid_snapshot":
            override = client.get("/player/trends?position=1&meta_rank=4&allow_historical_meta=true").json()
            assert override["meta"]["rank_bracket"] == "ARCHON"
            assert override["recommendations"][0]["meta_matches"] == 2000

        assert main.ACTIVE_PLAYER_CACHE == original
        for query in ("allow_historical_meta=maybe", "allow_historical_meta=true&allow_historical_meta=false"):
            assert client.get("/player/trends?position=1&" + query).status_code == 422


def test_match_details_compare_against_other_recent_matches_after_restart(monkeypatch):
    player_data = provider_data()
    player_data["recent"] = [
        {**match(3, hero=8), "kills": 10, "deaths": 0, "assists": 6, "gpm": 650, "xpm": None},
        {**match(2), "kills": 5, "deaths": 2, "assists": 3, "gpm": 500},
        {**match(1), "kills": 2, "deaths": 4, "assists": None, "gpm": None, "xpm": 400},
    ]
    monkeypatch.setattr(main, "fetch_opendota", AsyncMock(return_value=player_data))
    monkeypatch.setattr(main, "fetch_current_meta", AsyncMock(return_value=meta()))

    with TestClient(main.app) as client:
        assert client.get("/player/matches/3").status_code == 409
        assert client.post("/sync/123").status_code == 200

    with TestClient(main.app) as client:
        response = client.get("/player/matches/3")
        assert response.status_code == 200
        details = response.json()
        assert details["account_id"] == 123
        assert details["match"]["hero_name"] == "Juggernaut"
        assert details["match"]["is_win"] is False
        assert details["match"]["duration"] == "30:00"
        assert details["baseline_match_count"] == 2
        comparison = details["comparison"]
        assert comparison["kills"] == {"value": 10, "average": 3.5, "delta": 6.5, "sample_size": 2}
        assert comparison["deaths"] == {"value": 0, "average": 3, "delta": -3, "sample_size": 2}
        assert comparison["kda"] == {"value": 16, "average": 4, "delta": 12, "sample_size": 1}
        assert comparison["gpm"] == {"value": 650, "average": 500, "delta": 150, "sample_size": 1}
        assert comparison["xpm"] == {"value": None, "average": 500, "delta": None, "sample_size": 2}
        assert client.get("/player/matches/4").status_code == 404
        assert client.get("/player/matches/0").status_code == 422


def test_match_details_keep_values_when_no_baseline_is_available(monkeypatch):
    player = cache()
    player["recent"] = [match(1)]
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "ACTIVE_PLAYER_CACHE", player)
        details = client.get("/player/matches/1").json()
        assert details["baseline_match_count"] == 0
        assert details["comparison"]["kda"] == {"value": 4, "average": None, "delta": None, "sample_size": 0}

def test_match_lineups_use_account_side_and_return_only_hero_data(monkeypatch):
    players = [
        {"player_slot": 0, "hero_id": 1},
        {"player_slot": 128, "hero_id": 8, "account_id": 123},
        {"player_slot": 129, "hero_id": 1, "account_id": 456},
    ]
    fetch = AsyncMock(return_value={"players": players})
    monkeypatch.setattr(main, "get_json", fetch)
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "ACTIVE_PLAYER_CACHE", cache())
        assert client.get("/player/matches/1/lineups").status_code == 404
        fetch.assert_not_awaited()
        response = client.get("/player/matches/41/lineups")
        assert response.status_code == 200
        result = response.json()
        assert result["side"] == "Dire"
        assert [(hero["name"], hero["is_you"]) for hero in result["allies"]] == [
            ("Juggernaut", True), ("Anti-Mage", False),
        ]
        assert [hero["name"] for hero in result["enemies"]] == ["Anti-Mage"]
        assert all("account_id" not in hero for hero in result["allies"])
        players[1].pop("account_id")
        assert client.get("/player/matches/41/lineups").status_code == 404

def test_sequential_draft_lists_only_enemies_revealed_before_each_allied_pick():
    allies = [{"hero_id": i, "is_you": i == 3} for i in range(1, 6)]
    enemies = [{"hero_id": i, "is_you": False} for i in range(6, 11)]
    events = [{"order": 0, "is_pick": False, "hero_id": 20}]
    for index, (team, hero_id) in enumerate(zip([0, 1] * 5, [6, 1, 7, 2, 8, 3, 9, 4, 10, 5]), 1):
        events.append({"order": index, "is_pick": True, "team": team, "hero_id": hero_id})
    details = {"game_mode": 2, "picks_bans": events[::-1]}
    draft = main.match_draft(details, 1, allies, enemies)
    assert draft["last_pick_allied"] is True
    own_pick = next(pick for pick in draft["picks"] if pick["hero"]["is_you"])
    assert [hero["hero_id"] for hero in own_pick["enemies_revealed"]] == [6, 7, 8]
    assert own_pick["unavailable_hero_ids"] == [1, 2, 6, 7, 8, 20]
    assert main.match_draft({**details, "game_mode": 22}, 1, allies, enemies) is None
    assert main.match_draft({**details, "picks_bans": events[:-1]}, 1, allies, enemies) is None

def test_draft_ranking_prioritizes_matchups_and_does_not_rank_unavailable_heroes():
    heroes = [{"hero_id": i, "name": str(i)} for i in range(1, 5)]
    meta_rows = {i: {"positions": {2: {"matches": 1000, "winrate": 54}}} for i in range(1, 5)}
    enemies = [{"name": "Enemy A"}, {"name": "Enemy B"}]
    matchup_rows = [
        {1: (65, 100), 2: (62, 100), 3: (90, 100), 4: (19, 19)},
        {1: (62, 100), 2: (42, 100), 3: (90, 100), 4: (100, 100)},
    ]
    picks = main.rank_draft_picks(heroes, {1, 2, 4}, meta_rows, 2, True, enemies,
                                 matchup_rows, {2: (90, 100)})
    assert [pick["hero_id"] for pick in picks] == [1, 2]
    assert picks[0]["player_winrate"] is None
    assert picks[1]["player_winrate"] == 90
    assert picks[1]["score_breakdown"]["worst_matchup"] < 0

def test_ranked_all_pick_only_reveals_opponents_from_completed_rounds():
    allies = [{"hero_id": i, "is_you": i == 3} for i in range(1, 6)]
    enemies = [{"hero_id": i, "is_you": False} for i in range(6, 11)]
    order = [(0, 6), (1, 1), (0, 7), (1, 2), (0, 8), (1, 3),
             (1, 4), (0, 9), (1, 5), (0, 10)]
    events = [{"order": i, "is_pick": True, "team": team, "hero_id": hero}
              for i, (team, hero) in enumerate(order)]
    events.append({"order": 10, "is_pick": False, "hero_id": 20})
    details = {"game_mode": 22, "start_time": 1700000000, "picks_bans": events}
    draft = main.match_draft(details, 1, allies, enemies)
    assert draft["format"] == "all_pick"
    assert draft["last_pick_allied"] is None
    pick = next(row for row in draft["picks"] if row["hero"]["is_you"])
    assert pick["phase"] == 2
    assert [hero["hero_id"] for hero in pick["enemies_revealed"]] == [6, 7]
    assert pick["unavailable_hero_ids"] == [1, 2, 6, 7, 20]
    final_pick = next(row for row in draft["picks"] if row["hero"]["hero_id"] == 5)
    assert final_pick["phase"] == 3
    assert len(final_pick["enemies_revealed"]) == 4
    events[3], events[4] = {**events[4], "order": 3}, {**events[3], "order": 4}
    assert main.match_draft(details, 1, allies, enemies) is None

def test_outworld_devourer_has_lower_learning_cost_than_meepo():
    heroes = [
        {"hero_id": 76, "name": "Outworld Devourer", "complexity": 2},
        {"hero_id": 82, "name": "Meepo", "complexity": 3},
    ]
    stats = {hero["hero_id"]: {"positions": {2: {"matches": 1000, "winrate": 56}}} for hero in heroes}
    picks = main.rank_draft_picks(heroes, {76, 82}, stats, 2, True, [], [], {})
    assert [row["hero_id"] for row in picks] == [76, 82]
    assert [row["score_breakdown"]["learning_cost"] for row in picks] == [-0.75, -3.0]

    player = cache()
    player.update(heroes=main.build_heroes([], main.catalog_from_items([
        {"id": 76, "complexity": 2}, {"id": 82, "complexity": 3},
    ])), recent=[], history=[])
    player["meta"]["heroes"] = stats
    learning = main.build_recommendations(player, 10, 2)["worth_learning"]
    assert [row["hero_id"] for row in learning] == [76, 82]
    assert main.hero_learning_cost(3, 10) < main.hero_learning_cost(3, 0)
    assert main.hero_learning_cost(3, 100) == main.hero_learning_cost(None, 0) == 0

def test_dotabuff_crusader_sample_opens_measured_flex_roles_without_claiming_patch_coverage():
    from dotabuff_role_meta import COLLECTED_AT, MAX_AGE

    sample = main.load_role_sample("CRUSADER", main.HERO_POSITION_PROFILES, COLLECTED_AT)
    assert sample["position_data_exact"] is False
    assert len(sample["heroes"]) == 127
    assert sum(len(hero["positions"]) for hero in sample["heroes"].values()) == 284
    assert sample["heroes"][36]["positions"][2]["matches"] == 8508
    assert sample["heroes"][36]["positions"][2]["winrate"] == 50.65
    assert sample["heroes"][11]["positions"][1]["winrate"] == 43.35
    assert main.load_role_sample("ARCHON", main.HERO_POSITION_PROFILES, COLLECTED_AT) is None
    assert main.load_role_sample("CRUSADER", main.HERO_POSITION_PROFILES,
                                 COLLECTED_AT + MAX_AGE + timedelta(seconds=1)) is None

def test_starting_items_prefer_observed_role_and_keep_purchase_quantities(monkeypatch):
    monkeypatch.setattr(main, "ITEM_CATALOG_CACHE", None)
    monkeypatch.setattr(main, "STARTING_BUY_CACHE", {})
    catalog = {
        "branches": {"id": 16, "dname": "Iron Branch", "cost": 50},
        "tango": {"id": 44, "dname": "Tango", "cost": 90},
    }

    async def provider(client, path, params):
        if path == "/constants/items":
            return catalog
        if path == "/heroes/36/matches":
            return [{"match_id": i, "start_time": int(time.time())} for i in (123, 124)]
        position = 2 if path.endswith("/123") else 3
        return {"players": [{"hero_id": 36, "position_est": position, "purchase_log": [
            {"key": "branches", "time": -20},
            {"key": "branches", "time": -15},
            {"key": "tango", "time": 40},
        ]}]}

    monkeypatch.setattr(main, "get_json", provider)
    with TestClient(main.app) as client:
        response = client.get("/heroes/36/starting-items?position=2")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "selected_position"
        assert data["sample_size"] == 1
        assert data["bundles"][0]["gold"] == 100
        assert [(item["name"], item["quantity"]) for item in data["bundles"][0]["items"]] == [("Iron Branch", 2)]
        fallback = client.get("/heroes/36/starting-items?position=5").json()
        assert fallback["mode"] == "all_positions"
        assert fallback["bundles"][0]["observed_count"] == 2

def test_stage_inventories_consume_recipe_components_and_require_six_late_slots():
    catalog = {
        "ultimate_orb": {"item_id": 1, "cost": 2800, "created": False, "components": []},
        "skadi": {"item_id": 2, "cost": 5900, "created": True, "components": ["ultimate_orb"]},
        "orchid": {"item_id": 3, "cost": 3300, "created": True, "components": []},
        "bloodthorn": {"item_id": 4, "cost": 6800, "created": True, "components": ["orchid"]},
    }
    player = {"hero_id": 12, "position_est": 1, "purchase_log": [
        {"key": key, "time": time} for key, time in (
            ("ultimate_orb", 1200), ("skadi", 1550), ("orchid", 1700), ("bloodthorn", 2100),
        )
    ]}
    assert [item["item_id"] for item in main.mid_equipment(player, catalog)] == [2, 3]
    player["purchase_log"][-1]["time"] = 2099
    assert [item["item_id"] for item in main.mid_equipment(player, catalog)] == [4, 2]
    player.update({f"item_{slot}": 2 for slot in range(6)})
    match = {"match_id": 123, "players": [player], "duration": 3000}
    assert len(main.choose_game_inventory([match], 12, 1, catalog, late=True)["items"]) == 6
    assert main.choose_game_inventory([{**match, "duration": 2999}], 12, 1, catalog, late=True) is None
    player["item_5"] = 0
    assert main.choose_game_inventory([match], 12, 1, catalog, late=True) is None

def test_core_farm_summary_uses_only_known_core_roles_and_combines_match_time():
    result = main.core_farm_summary([
        {"position": 1, "duration": 1200, "last_hits": 100},
        {"position": 1, "duration": 2400, "last_hits": 380},
        {"position": 2, "duration": 1800, "last_hits": 180},
        {"position": 5, "duration": 1800, "last_hits": 25},
        {"position": None, "duration": 1800, "last_hits": 100},
    ])
    assert result["missing_data"] == 1
    carry, mid, offlane = result["roles"]
    assert (carry["matches"], carry["last_hits_per_match"], carry["last_hits_per_minute"]) == (2, 240, 8)
    assert mid["last_hits_per_minute"] == 6
    assert offlane["last_hits_per_minute"] is None
