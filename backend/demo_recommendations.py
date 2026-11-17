"""Offline synthetic demonstration. No API requests; figures are not live Dota meta."""
import json
from datetime import datetime, timedelta, timezone
import main


def demo():
    now = datetime.now(timezone.utc)
    # Isolated fictional patch context: never use this demo as a live snapshot.
    main.CURRENT_PATCH_INFO = {'patch_number':'SYNTHETIC-DEMO',
        'patch_timestamp':(now-timedelta(days=14)).timestamp(), 'verified_at':now.isoformat()}
    # Fictional inputs to make score changes reproducible and inspectable.
    definitions = {
        10: ('Morphling', 300, 180, 54, 1, ['Carry', 'Escape'], 3),
        109: ('Terrorblade', 200, 130, 53, 1, ['Carry', 'Pusher'], 3),
        8: ('Juggernaut', 80, 48, 52, 1, ['Carry', 'Pusher'], 1),
        4: ('Bloodseeker', 10000, 9000, 47, 1, ['Carry', 'Nuker'], 1),
        32: ('Riki', 10000, 9000, 46, 1, ['Carry', 'Escape'], 1),
        48: ('Luna', 0, 0, 54, 1, ['Carry', 'Pusher', 'Nuker'], 1),
        70: ('Ursa', 3, 2, 52, 1, ['Carry'], 1),
        86: ('Rubick', 8, 4, 53, 4, ['Support', 'Disabler', 'Nuker'], 3),
        5: ('Crystal Maiden', 30, 15, 52, 4, ['Support', 'Disabler', 'Nuker'], 1),
        27: ('Shadow Shaman', 0, 0, 54, 4, ['Support', 'Disabler', 'Pusher'], 1),
        26: ('Lion', 0, 0, 51, 4, ['Support', 'Disabler', 'Nuker'], 1),
    }
    catalog = main.catalog_from_items([
        {'id':h,'localized_name':v[0],'roles':v[5],'complexity':v[6]}
        for h,v in definitions.items()
    ])
    heroes = main.build_heroes([
        {'hero_id':h,'games':v[1],'win':v[2]} for h,v in definitions.items()
    ],catalog)
    recent = [{'match_id':i+1,'hero_id':10,'is_win':i<14,'position':1,
               'start_time':int((now-timedelta(days=i+1)).timestamp())}
              for i in range(20)]
    cache = {'heroes':heroes,'history':recent,'recent':recent,'meta':{
        'source':'SYNTHETIC example, not live meta', 'position_data_exact':True,
        'rank_bracket':'DIVINE','requested_rank_bracket':'DIVINE',
        'rank_fallback_applied':False,'patch':'SYNTHETIC-DEMO','patch_coverage_verified':True,
        'window_start':(now-timedelta(days=7)).isoformat(),'window_end':now.isoformat(),
        'collected_at':now.isoformat(),'heroes':{
            h:{'positions':{v[4]:{'matches':50000,'winrate':v[3],'pick_rate':10}}}
            for h,v in definitions.items()
        }}}
    results = {str(pos): main.build_recommendations(cache,5,pos) for pos in (1,4)}
    return {'notice':'Synthetic regression demonstration; no live player/meta data or win-rate validation.',
            'scoring_version':main.SCORING_VERSION,'scenarios':results}


if __name__ == '__main__':
    print(json.dumps(demo(),indent=2,allow_nan=False))
