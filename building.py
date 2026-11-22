"""Grounded house construction and finite resource nodes for Arthur v1.8.

This module never moves Arthur, generates inventory, or calls an AI service.
The runtime follows choose_next() hints with its normal collision-aware mover,
then calls harvest()/handle_action() at the actual location. Call
 tick_resources(state, dt) and step_work(state, dt) once per simulation tick.
All returned events describe completed state changes and can feed the journal
and mind. The entire durable state lives in state.house and state.resources.
"""
from __future__ import annotations

import copy
import math
from world import BUILD_PLOT, SITES

MATERIALS = ('wood', 'stone', 'flowers', 'berries')
BACKPACK_CAPACITY = 24
WORK_RADIUS = .6
GATHER_RADIUS = .8
ORIENTATION_SECONDS = 8.
HARVEST_COOLDOWN = 2.
PHASES = (
    {'id':'foundation', 'label':'Foundation', 'duration':9., 'cost':{'wood':2,'stone':6}},
    {'id':'frame', 'label':'Timber frame', 'duration':12., 'cost':{'wood':8,'stone':2}},
    {'id':'roof', 'label':'Roof', 'duration':10., 'cost':{'wood':6,'flowers':2}},
    {'id':'finish', 'label':'Finishing touches', 'duration':8., 'cost':{'wood':2,'stone':2,'flowers':4}},
)
PHASE_IDS = tuple(p['id'] for p in PHASES)
STYLES = (
    {'id':'woodland','label':'Woodland cabin','description':'Warm timber, a moss-green roof and a simple stone base.',
     'palette':{'wall':'#a77d58','roof':'#637b60','trim':'#dbc19b','stone':'#92958b'}},
    {'id':'stone_cottage','label':'Stone cottage','description':'Pale stone cladding, slate blue roofing and dark timber trim.',
     'palette':{'wall':'#b3b3a1','roof':'#647887','trim':'#78644c','stone':'#979c94'}},
    {'id':'meadow_cottage','label':'Meadow cottage','description':'Light timber, a warm clay roof and flowering window boxes.',
     'palette':{'wall':'#d3bd94','roof':'#ab765c','trim':'#f0dcae','stone':'#a2a194'}},
)
STYLE_IDS = tuple(style['id'] for style in STYLES)
REQUIRED = {item:sum(phase['cost'].get(item,0) for phase in PHASES) for item in MATERIALS}
# A harvest is a small batch. Supplies are finite and regenerate in elapsed
# simulation time; repeated API calls cannot skip the cooldown or fill a bag.
RESOURCE_SPECS = {
    'grove': {'wood':{'capacity':18,'batch':2,'regen_per_second':1/12},
              'berries':{'capacity':12,'batch':2,'regen_per_second':1/10}},
    'forest': {'wood':{'capacity':12,'batch':2,'regen_per_second':1/16}},
    'hill': {'stone':{'capacity':12,'batch':2,'regen_per_second':1/18}},
    'pond': {'stone':{'capacity':6,'batch':1,'regen_per_second':1/22}},
    'meadow': {'flowers':{'capacity':12,'batch':2,'regen_per_second':1/16}},
}


class BuildError(ValueError):
    def __init__(self,message,status=409):
        super().__init__(message)
        self.status=status
        self.code=status


def _number(value,default=0.):
    if isinstance(value,bool):return float(default)
    try:result=float(value)
    except (TypeError,ValueError,OverflowError):return float(default)
    return result if math.isfinite(result) else float(default)


def _count(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)):return 0
    return max(0,int(value)) if math.isfinite(value) else 0


def _dt(value):
    # The server already caps suspended time. Retain that bound here so passing
    # a large delta to a work function can never finish a house instantly.
    return max(0.,min(.25,_number(value)))


def _inventory(state):
    if not isinstance(state.get('inventory'),dict):state['inventory']={}
    inventory=state['inventory']
    for item in MATERIALS:inventory[item]=_count(inventory.get(item,0))
    return inventory


def ensure_state(state):
    """Add durable building fields without touching older collections or history."""
    if not isinstance(state,dict):raise BuildError('World state must be an object.',400)
    if not isinstance(state.get('house'),dict):state['house']={}
    house=state['house']
    defaults={'version':1,'aspiration':'Build a home of my own','status':'planned',
              'style':'woodland','phase_index':0,'phase_elapsed':0.,'phase_paid':False,
              'paid_phases':[],'completed_phases':[],'stockpile':{},'spent':{},
              'orientation_elapsed':0.,'started_day':None,'completed_day':None,
              'event_seq':0,'working':False}
    for key,value in defaults.items():house.setdefault(key,copy.deepcopy(value))
    if house['style'] not in STYLE_IDS:house['style']='woodland'
    if house['status'] not in ('planned','active','paused','complete'):house['status']='planned'
    for group in ('stockpile','spent'):
        if not isinstance(house[group],dict):house[group]={}
        for item in MATERIALS:house[group][item]=_count(house[group].get(item,0))
    _inventory(state)
    house['orientation_elapsed']=max(0.,min(ORIENTATION_SECONDS,_number(house['orientation_elapsed'])))
    house['event_seq']=_count(house['event_seq'])
    claimed=house['completed_phases'] if isinstance(house['completed_phases'],list) else []
    completed=[];used={item:0 for item in MATERIALS}
    # Require an ordered completion ledger backed by materials actually spent.
    for phase in PHASES:
        if len(claimed)<=len(completed) or claimed[len(completed)]!=phase['id']:break
        trial={item:used[item]+phase['cost'].get(item,0) for item in MATERIALS}
        if any(house['spent'][item]<trial[item] for item in MATERIALS):break
        used=trial;completed.append(phase['id'])
    house['completed_phases']=completed
    house['phase_index']=len(completed)
    paid=house['paid_phases'] if isinstance(house['paid_phases'],list) else []
    house['paid_phases']=completed[:]
    if len(completed)==len(PHASES):
        house.update(status='complete',phase_elapsed=0.,phase_paid=False,working=False)
    else:
        phase=PHASES[len(completed)]
        has_payment=(phase['id'] in paid or house['phase_paid'] is True) and all(
            house['spent'][item]>=used[item]+phase['cost'].get(item,0) for item in MATERIALS)
        house['phase_paid']=has_payment
        if has_payment:house['paid_phases'].append(phase['id'])
        house['phase_elapsed']=max(0.,min(phase['duration'],_number(house['phase_elapsed']))) if has_payment else 0.
        if house['status']=='complete':house['status']='active' if completed or has_payment else 'planned'
    return house


def _resources(state):
    if not isinstance(state.get('resources'),dict):state['resources']={}
    resources=state['resources'];resources['version']=1
    if not isinstance(resources.get('nodes'),dict):resources['nodes']={}
    for place,spec in RESOURCE_SPECS.items():
        if not isinstance(resources['nodes'].get(place),dict):resources['nodes'][place]={}
        node=resources['nodes'][place]
        if not isinstance(node.get('stock'),dict):node['stock']={}
        for item,info in spec.items():
            node['stock'][item]=max(0.,min(info['capacity'],_number(node['stock'].get(item),info['capacity'])))
        node['cooldown']=max(0.,min(HARVEST_COOLDOWN,_number(node.get('cooldown'))))
    return resources


def _event(state,kind,message,place='homesite',details=None,salience=.65):
    house=ensure_state(state)
    house['event_seq']+=1
    return {'id':f"building:{house['event_seq']}",'type':kind,'source':'building',
            'message':message,'place':place,'details':details or {},'salience':salience}


def at_site(state,place='homesite',radius=WORK_RADIUS):
    point=SITES.get(place)
    if point is None:return False
    x=_number(state.get('x'),math.inf);y=_number(state.get('y'),math.inf)
    return math.isfinite(x) and math.isfinite(y) and math.hypot(x-point[0],y-point[1])<=radius


def _stationary(state):
    return not bool(state.get('moving')) and abs(_number(state.get('speed')))<=.05


def _phase(house):
    index=house['phase_index']
    return PHASES[index] if index<len(PHASES) else None


def _items_text(items):
    return ', '.join(f'{amount} {item}' for item,amount in items.items() if amount)


def handle_action(state,action,payload=None):
    """Validated owner/local actions. Returns only events from actual changes.

    start, pause, resume: {}. style: {style: STYLE_ID}. deposit: {} moves
    every available backpack resource, or {item: MATERIAL, amount: positive int}
    moves an exact quantity. A deposit requires Arthur standing at the plot.
    """
    house=ensure_state(state)
    if not isinstance(action,str) or action not in ('start','pause','resume','style','deposit'):
        raise BuildError('Unknown construction action.',400)
    if payload is None:payload={}
    if not isinstance(payload,dict):raise BuildError('Construction options must be an object.',400)
    allowed={'style'} if action=='style' else {'item','amount'} if action=='deposit' else set()
    if any(key not in allowed for key in payload):raise BuildError('Unsupported construction option.',400)
    if action=='style':
        style=payload.get('style')
        if not isinstance(style,str) or style not in STYLE_IDS:raise BuildError('Unknown house style.',400)
        if house['paid_phases'] or house['completed_phases']:
            raise BuildError('Choose the style before construction starts.')
        if style==house['style']:return []
        house['style']=style
        label=next(item['label'] for item in STYLES if item['id']==style)
        return [_event(state,'house_style_chosen',f'Arthur chose the {label.lower()} design.',details={'style':style})]
    if action in ('start','resume'):
        if house['status']=='complete':raise BuildError('Arthur’s house is already complete.')
        if house['status']=='active':return []
        first=house['started_day'] is None
        house['status']='active';house['orientation_elapsed']=ORIENTATION_SECONDS
        if first:house['started_day']=max(1,_count(state.get('day',1)))
        return [_event(state,'house_started' if first else 'house_resumed',
            'Arthur began a project to build a home of his own.' if first else 'Arthur resumed building his home.',
            details={'style':house['style'],'phase':PHASES[house['phase_index']]['id']},salience=.9)]
    if action=='pause':
        if house['status']=='complete':raise BuildError('Arthur’s house is already complete.')
        if house['status']=='paused':return []
        house['status']='paused';house['working']=False
        return [_event(state,'house_paused','Arthur paused his house project; his materials and progress are saved.')]
    if not at_site(state) or not _stationary(state):
        raise BuildError('Arthur must be standing at the house site to deposit materials.')
    inventory=_inventory(state)
    if 'item' in payload:
        item=payload['item']
        if not isinstance(item,str) or item not in MATERIALS:raise BuildError('Unknown construction material.',400)
        amount=payload.get('amount',inventory[item])
        if isinstance(amount,bool) or not isinstance(amount,int) or amount<=0:
            raise BuildError('Deposit amount must be a positive whole number.',400)
        if amount>inventory[item]:raise BuildError('Arthur is not carrying that many materials.')
        items={item:amount}
    else:
        if 'amount' in payload:raise BuildError('Choose a material for an exact deposit.',400)
        items={item:inventory[item] for item in MATERIALS if inventory[item]>0}
        if not items:return []
    for item,amount in items.items():
        inventory[item]-=amount;house['stockpile'][item]+=amount
    return [_event(state,'house_materials_deposited',f'Arthur stored {_items_text(items)} at his house site.',details={'items':items})]


def tick_resources(state,dt):
    """Regenerate a bounded supply using simulation time, never wall-clock saves."""
    dt=_dt(dt)
    resources=_resources(state)
    for place,node in resources['nodes'].items():
        if place not in RESOURCE_SPECS:continue
        node['cooldown']=max(0.,node['cooldown']-dt)
        for item,info in RESOURCE_SPECS[place].items():
            node['stock'][item]=min(float(info['capacity']),node['stock'][item]+info['regen_per_second']*dt)
    return []


def harvest(state,place):
    """Harvest one finite batch only while standing at the actual resource node."""
    ensure_state(state)
    if not isinstance(place,str) or place not in RESOURCE_SPECS:raise BuildError('This place has no resource node.',400)
    if not at_site(state,place,GATHER_RADIUS) or not _stationary(state):
        raise BuildError('Arthur must be standing at the resource node to gather.')
    inventory=_inventory(state)
    node=_resources(state)['nodes'][place]
    if node['cooldown']>1e-8:return []
    free=max(0,BACKPACK_CAPACITY-sum(_count(value) for value in inventory.values()))
    gathered={}
    for item,info in RESOURCE_SPECS[place].items():
        amount=min(free,info['batch'],max(0,int(node['stock'][item]+1e-8)))
        if amount:
            inventory[item]+=amount;node['stock'][item]-=amount;free-=amount;gathered[item]=amount
    if not gathered:return []
    node['cooldown']=HARVEST_COOLDOWN
    return [_event(state,'resource_gathered',f'Arthur gathered {_items_text(gathered)} in the {place}.',place,{'items':gathered},.45)]


def step_work(state,dt):
    """Advance orientation or on-site construction; elapsed work survives saves."""
    house=ensure_state(state);house['working']=False
    dt=_dt(dt)
    if dt<=0 or state.get('paused') or house['status'] in ('paused','complete'):return []
    events=[]
    if house['status']=='planned':
        house['orientation_elapsed']=min(ORIENTATION_SECONDS,house['orientation_elapsed']+dt)
        if house['orientation_elapsed']+1e-8<ORIENTATION_SECONDS:return []
        events.extend(handle_action(state,'start'))
    if not at_site(state) or not _stationary(state):return events
    # Basic needs can interrupt work without consuming the next phase's stock.
    if _number(state.get('energy'),100)<12 or _number(state.get('hunger'))>92:return events
    phase=_phase(house)
    if phase is None:return events
    if not house['phase_paid']:
        if any(house['stockpile'][item]<amount for item,amount in phase['cost'].items()):return events
        for item,amount in phase['cost'].items():
            house['stockpile'][item]-=amount;house['spent'][item]+=amount
        house['phase_paid']=True;house['paid_phases'].append(phase['id'])
        events.append(_event(state,'house_phase_started',
            f"Arthur started the {phase['label'].lower()} using {_items_text(phase['cost'])}.",
            details={'phase':phase['id'],'materials':dict(phase['cost'])},salience=.8))
    house['working']=True
    house['phase_elapsed']=min(phase['duration'],house['phase_elapsed']+dt)
    if 'energy' in state:state['energy']=max(0.,_number(state['energy'])-.1*dt)
    if house['phase_elapsed']+1e-8>=phase['duration']:
        house['completed_phases'].append(phase['id']);house['phase_index']+=1
        house['phase_elapsed']=0.;house['phase_paid']=False;house['working']=False
        events.append(_event(state,'house_phase_completed',f"Arthur finished the {phase['label'].lower()} of his home.",
                             details={'phase':phase['id']},salience=.9))
        if house['phase_index']==len(PHASES):
            house['status']='complete';house['completed_day']=max(1,_count(state.get('day',1)))
            events.append(_event(state,'house_completed','Arthur finished building a home of his own.',
                                 details={'style':house['style'],'plot':BUILD_PLOT['id']},salience=1.))
    return events


def choose_next(state):
    """Return an executable intent; the caller performs travel and actual actions."""
    house=ensure_state(state)
    if state.get('paused') or house['status']!='active':return None
    if _number(state.get('energy'),100)<22:
        return {'goal':'home','action':'recharge','reason':'I need to recharge at my shelter before building more.'}
    if _number(state.get('hunger'))>78:
        return {'goal':'grove','action':'eat','reason':'I need some berries before I carry on with my house.'}
    phase=_phase(house)
    if phase is None:return None
    inventory=_inventory(state)
    carrying=sum(_count(value) for value in inventory.values())
    available=sum(inventory[item] for item in MATERIALS)
    if available and (carrying>=BACKPACK_CAPACITY or (at_site(state) and _stationary(state))):
        return {'goal':'homesite','action':'deposit','reason':'I will store my materials at the house site to make room in my backpack.'}
    if house['phase_paid'] or all(house['stockpile'][item]>=amount for item,amount in phase['cost'].items()):
        return {'goal':'homesite','action':'work','reason':f"I am ready to work on the {phase['label'].lower()}."}
    missing={item:max(0,amount-house['stockpile'][item]-inventory[item]) for item,amount in phase['cost'].items()}
    if not any(missing.values()):
        return {'goal':'homesite','action':'deposit','reason':'I am carrying what I need for the next stage of my house.'}
    resources=_resources(state)
    # First prioritize missing construction supplies. A full bag always routes
    # home above, including a bag of berries unrelated to a phase's recipe.
    for item,needed in sorted(missing.items(),key=lambda pair:pair[1],reverse=True):
        if needed<=0:continue
        candidates=[]
        for place,spec in RESOURCE_SPECS.items():
            if item not in spec:continue
            node=resources['nodes'][place]
            if int(node['stock'][item]+1e-8)<1:continue
            px,py=SITES[place]
            distance=math.hypot(_number(state.get('x'),px)-px,_number(state.get('y'),py)-py)
            candidates.append((distance,place,node['cooldown']))
        if candidates:
            _,place,cooldown=min(candidates)
            return {'goal':place,'action':'gather','item':item,
                    'reason':f'I need {needed} more {item} for the '+phase['label'].lower()+'.',
                    'wait_seconds':cooldown}
    if available:
        return {'goal':'homesite','action':'deposit','reason':'I can store what I have while the resource patches recover.'}
    return {'goal':'homesite','action':'wait','reason':'The resource patches need time to recover. I will wait at my house site.'}


def public_house(state):
    """Stable UI projection. Progress always reflects paid, completed work."""
    house=ensure_state(state);phase=_phase(house)
    total_duration=sum(item['duration'] for item in PHASES)
    complete_duration=sum(PHASES[i]['duration'] for i in range(house['phase_index']))
    elapsed=house['phase_elapsed'] if phase else 0.
    cost=dict(phase['cost']) if phase else {}
    missing={item:max(0,cost.get(item,0)-house['stockpile'][item]) if not house['phase_paid'] else 0 for item in MATERIALS}
    hint=choose_next(state)
    if house['status']=='complete':task='complete';reason='My home is finished. I built it one stage at a time.'
    elif house['status']=='paused' or state.get('paused'):task='paused';reason='The house project is paused; materials and work are saved.'
    elif house['status']=='planned':task='orienting';reason='I would like to build a home of my own.'
    elif house.get('working'):task='working';reason=f"I am working on the {phase['label'].lower()}."
    else:task=(hint or {}).get('action','waiting');reason=(hint or {}).get('reason','I am considering my next building task.')
    inventory=_inventory(state)
    return {**copy.deepcopy(house),'plot_id':BUILD_PLOT['id'],'phase_id':phase['id'] if phase else 'complete',
            'phase_label':phase['label'] if phase else 'Home complete','phase_duration':phase['duration'] if phase else 0.,
            'elapsed':elapsed,'progress':elapsed/phase['duration'] if phase else 1.,
            'total_progress':(complete_duration+elapsed)/total_duration,
            'phase_cost':cost,'missing':missing,'required':dict(REQUIRED),
            'remaining_required':{item:max(0,REQUIRED[item]-house['spent'][item]-house['stockpile'][item]) for item in MATERIALS},
            'styles':copy.deepcopy(list(STYLES)),'at_site':at_site(state),
            'can_deposit':at_site(state) and _stationary(state) and any(inventory[item]>0 for item in MATERIALS),
            'can_change_style':not house['paid_phases'] and not house['completed_phases'],
            'current_task':task,'reason':reason,'next':hint}
