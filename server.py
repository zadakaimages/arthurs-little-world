"""Arthur v1.8: a persistent character, asynchronous conversation and grounded building."""
import copy, hmac, json, math, os, random, re, signal, sqlite3, threading, time, uuid
from collections import deque
from functools import lru_cache
from urllib.parse import urlsplit
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from settings import load_settings, bounded_int
load_settings()
from locomotion import Mover, clear_at, nearest_clear, length
from world import W, H, HOME, SANCTUARY, SITES, walkable, public_world
import building
from ai_client import AIClient
from conversation import ConversationEngine
from mind import ensure_mind, observe, local_thought, offline_reply, apply_model_result, preference_score

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('ARTHUR_DB',str(ROOT/'arthur.sqlite3')))
HOST=os.environ.get('ARTHUR_HOST','127.0.0.1')
PORT=bounded_int('ARTHUR_PORT',8765,1,65535)
MODEL=os.environ.get('ARTHUR_MODEL','gpt-6.1-terra')
OWNER_TOKEN=os.environ.get('ARTHUR_OWNER_TOKEN','')
LOCK=threading.RLock()
VIEWERS={}
VIEWER_LOCK=threading.Lock()
VERSION="1.8"
SIM_HZ=20
HISTORY_REVISION=0
RUNTIME=None

# Original collectible species, inspired by classic monster-collecting RPGs.
SPECIES={
 'Mossbit':{'color':'#66b96b','accent':'#d5f17e','habitat':'meadow','rarity':0.40,'temperament':'gentle'},
 'Emberoo':{'color':'#ee8754','accent':'#ffdc73','habitat':'hill','rarity':0.23,'temperament':'bold'},
 'Puddlepip':{'color':'#5bb9d4','accent':'#b6edff','habitat':'pond','rarity':0.32,'temperament':'shy'},
 'Thornlet':{'color':'#9c7cbd','accent':'#e5b7f4','habitat':'grove','rarity':0.30,'temperament':'curious'},
 'Moonmote':{'color':'#c2c7e9','accent':'#fff2b0','habitat':'hill','rarity':0.08,'temperament':'elusive'},
 'Pebblin':{'color':'#a5a0a0','accent':'#d6d2c8','habitat':'grove','rarity':0.34,'temperament':'patient'},
}

# Evolution is earned through shared experiences, not random capture rolls.
EVOLUTIONS={
 'Mossbit':('Mossbloom',70),'Emberoo':('Emberhorn',85),
 'Puddlepip':('Ripplefin',70),'Thornlet':('Thornbloom',75),
 'Moonmote':('Lunaglow',95),'Pebblin':('Boulderkin',80),
}

def companion_tick(c,s):
    friends=s.get('companions',[])
    if not friends:return
    # Movement is handled continuously by Runtime; social milestones run at 0.5 Hz.
    friend=friends[s.get('active_companion',0)%len(friends)]
    friend.setdefault('xp',0)
    friend.setdefault('level',1)
    friend.setdefault('form',friend['species'])
    friend.setdefault('friendship',min(100,friend.get('bond',0)))
    friend.setdefault('last_xp_step',s['steps'])
    if s['steps']-friend['last_xp_step']>=9:
        friend['last_xp_step']=s['steps']
        friend['xp']+=8
        friend['friendship']=min(100,friend['friendship']+2)
        level=min(20,1+friend['xp']//45)
        if level>friend['level']:
            friend['level']=level
            record(c,s,friend['nickname']+' reached level '+str(level)+'!')
        next_form,threshold=EVOLUTIONS[friend['species']]
        if friend['form']==friend['species'] and friend['xp']>=threshold and friend['friendship']>=65:
            friend['form']=next_form
            friend['evolved_day']=s['day']
            record(c,s,friend['nickname']+' evolved into '+next_form+'!')
            remember(c,s,s['goal'],'My friend '+friend['nickname']+' evolved into '+next_form+'.',1.0)
            s['thought']='Wow! '+friend['nickname']+' became '+next_form+'!'

def creature_encyclopedia(s):
    owned={c['species'] for c in s.get('companions',[])}
    return [{'species':name,'habitat':spec['habitat'],
             'seen':name in s['seen_species'],'owned':name in owned,
             'evolution':EVOLUTIONS[name][0] if name in owned else None}
            for name,spec in SPECIES.items()]

def seed_wild():
    roster=[]
    for i,(name,spec) in enumerate(SPECIES.items()):
        sx,sy=SITES[spec['habitat']]
        x,y=sx+(i%3)*2-2,sy+(i%2)*2-1
        if not walkable(x,y):x,y=sx,sy
        roster.append({'id':i+1,'species':name,'x':x,'y':y,'habitat':spec['habitat'],'bond':0,'seen':False})
    return roster

def creature_tick(c,s):
    # Creatures are independent wildlife, not conversational AI agents.
    for creature in s['wild_creatures']:
        distance=math.hypot(s['x']-creature['x'],s['y']-creature['y'])
        if distance<=2:
            species=creature['species']
            if species not in s['seen_species']:
                s['seen_species'].append(species)
                record(c,s,'Arthur discovered a wild '+species+'!')
                remember(c,s,creature['habitat'],'I met a '+species+' in the '+creature['habitat']+'.',.85)
            creature['seen']=True
            if distance<=1 and s['steps']-s.get('last_encounter_step',-100)>12:
                s['last_encounter_step']=s['steps']
                creature['bond']=min(100,creature['bond']+random.randint(12,30))
                s['last_action']='Met '+species
                s['thought']='A '+species+' is nearby! I wonder if it wants to be my friend.'
                record(c,s,'Arthur approached '+species+' (trust '+str(creature['bond'])+'/100).')
                # Friendship-based collection, no combat. A creature may choose to join.
                if creature['bond']>=55 and random.random()<.40 and not any(f['species']==species for f in s['companions']):
                    s['companions'].append({'species':species,'met_day':s['day'],'nickname':species,'bond':creature['bond'],'friendship':creature['bond'],'xp':0,'level':1,'form':species,'x':s['x'],'y':s['y'],'last_xp_step':s['steps']})
                    record(c,s,species+' decided to join Arthur’s collection!')
                    remember(c,s,creature['habitat'],species+' became my companion.',1.0)
                    s['thought']='I made a new friend: '+species+'!'
                    observe(s,'companion_joined',species+' became my companion.',place=creature['habitat'],importance=1.)
                    creature['bond']=0
                    # The wild population stays in its habitat; no visible teleport.
                    creature['behavior']='resting'

def new_state():
    return {'x':21,'y':16,'day':1,'minute':480,'energy':85,'hunger':10,'curiosity':75,'mood':80,'goal':'meadow','target':list(SITES['meadow']),'thought':'I wonder what I will discover today.','steps':0,'preferences':{k:0 for k in SITES},'visits':{k:0 for k in SITES},'project':'Visit each landmark','last_action':'Woke up at home','traits':{'curiosity':65,'caution':45,'sociability':30,'persistence':55},'aspirations':[],'active_aspiration':None,'reflection':'I am just beginning to understand my little world.','milestones':[],'plans':[],'active_plan':None,'plan_history':[],'failed_attempts':0,'inventory':{'wood':0,'stone':0,'flowers':0,'berries':0},'structures':[],'discoveries':[],'craft_count':0,'activity_count':{},'last_craft_day':0,'wild_creatures':[],'companions':[],'seen_species':[],'last_encounter_step':-100,'creature_focus':False,'active_companion':0,'coins':25,'chat_history':[],'pending_request':None}

def connect(db_path=None):
    path=Path(db_path) if db_path is not None else DB
    path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path,timeout=15,check_same_thread=False)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY AUTOINCREMENT,day INTEGER,minute INTEGER,event TEXT,created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, place TEXT, summary TEXT, salience REAL, created_at TEXT)')
    return c

def save(c,s):
    c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',('state',json.dumps(s)))

def record(c,s,event):
    global HISTORY_REVISION
    HISTORY_REVISION+=1
    c.execute('INSERT INTO journal(day,minute,event,created_at) VALUES (?,?,?,?)',(s['day'],s['minute'],event,datetime.now(timezone.utc).isoformat()))
    c.execute('DELETE FROM journal WHERE id NOT IN (SELECT id FROM journal ORDER BY id DESC LIMIT 500)')

def load(c):
    row=c.execute("SELECT value FROM kv WHERE key='state'").fetchone()
    s=json.loads(row[0]) if row else new_state()
    for k,v in new_state().items():s.setdefault(k,v)
    for k,v in new_state()['inventory'].items():s['inventory'].setdefault(k,v)
    if not s['wild_creatures']:s['wild_creatures']=seed_wild()
    return s

def remember(c,s,place,summary,salience=0.5):
    global HISTORY_REVISION
    HISTORY_REVISION+=1
    c.execute('INSERT INTO memories(day,place,summary,salience,created_at) VALUES (?,?,?,?,?)',(s['day'],place,summary,salience,datetime.now(timezone.utc).isoformat()))
    c.execute('DELETE FROM memories WHERE id NOT IN (SELECT id FROM memories ORDER BY id DESC LIMIT 250)')
    observe(s,'experience',summary,place=place,importance=salience)

def memories(c,limit=12):
    return [{'day':d,'place':p,'summary':t,'salience':v} for d,p,t,v in c.execute('SELECT day,place,summary,salience FROM memories ORDER BY salience DESC,id DESC LIMIT ?', (limit,))]

def new_aspiration(s):
    # Long-horizon, measurable personal goals, based on Arthur's own experiences.
    places=['pond','meadow','grove','hill']
    ranked=sorted(places,key=lambda k:(s['preferences'].get(k,0)+s['visits'].get(k,0)*.25),reverse=True)
    favorite=ranked[0]
    options=[('Become a pond watcher','pond',3),('Study the meadow flowers','meadow',4),('Learn the grove trails','grove',4),('Watch the sunrise from the hill','hill',3)]
    eligible=[x for x in options if not any(a['name']==x[0] and a['completed'] for a in s['aspirations'])]
    if not eligible:return None
    weighted=sorted(eligible,key=lambda a:(a[1]!=favorite,random.random()))
    name,place,amount=weighted[0]
    a={'name':name,'place':place,'start_visits':s['visits'].get(place,0),'required':amount,'progress':0,'completed':False,'created_day':s['day']}
    s['aspirations'].append(a);s['active_aspiration']=name
    return a

def evolve(c,s,place):
    traits=s['traits']
    if place in ('meadow','hill'):traits['curiosity']=min(95,traits['curiosity']+.35)
    if place=='home':traits['caution']=min(95,traits['caution']+.2)
    if place=='grove':traits['persistence']=min(95,traits['persistence']+.25)
    a=next((a for a in s['aspirations'] if a['name']==s.get('active_aspiration') and not a['completed']),None)
    if a and a['place']==place:
        a['progress']=min(a['required'],s['visits'][place]-a['start_visits'])
        if a['progress']>=a['required']:
            a['completed']=True;s['active_aspiration']=None
            line='I finished my project: '+a['name']+'. I want to remember this.'
            s['reflection']=line;s['milestones'].append({'day':s['day'],'event':line})
            remember(c,s,place,line,1.0);record(c,s,line)
    if not s.get('active_aspiration'):
        a=new_aspiration(s)
        if a:record(c,s,'Arthur began a personal project: '+a['name']+'.')

# Open-ended *descriptions*, constrained to executable world actions.
# A plan is an ordered sequence of landmark visits, not arbitrary code.
PLAN_TEMPLATES=[
    ('Trace the quiet places', ['pond','hill','meadow']),
    ('Find my favorite peaceful corner', ['meadow','pond','home']),
    ('Prepare for a long walk', ['grove','home','hill']),
    ('Compare the view from two places', ['hill','pond','hill']),
    ('Explore and write down what I learned', ['grove','meadow','home']),
]

def propose_plan(s, title=None, steps=None, reason=None):
    valid={'pond','meadow','grove','hill','home'}
    if not isinstance(steps,list) or not 2<=len(steps)<=6 or any(not isinstance(x,str) or x not in valid for x in steps):return None
    title=str(title or 'Explore my little world').strip()[:90]
    if not title:return None
    plan={'id':max((p.get('id',0) for p in s['plans']),default=0)+1,'title':title,'steps':steps[:], 'index':0,'status':'active','reason':str(reason or 'I want to learn something new.')[:180], 'started_day':s['day'],'failures':0}
    s['plans'].append(plan);s['active_plan']=plan['id']
    s['plans']=s['plans'][-30:]
    return plan

def current_plan(s):
    return next((p for p in s['plans'] if p['id']==s.get('active_plan') and p['status']=='active'),None)

def create_fallback_plan(s):
    favorite=max(('pond','meadow','grove','hill'),key=lambda k:s['preferences'].get(k,0))
    available=[p for p in PLAN_TEMPLATES if p[0] not in [q['title'] for q in s['plans'][-5:]]]
    if not available:available=PLAN_TEMPLATES
    title,steps=random.choice(available)
    if random.random()<.3:steps=[favorite]+[x for x in steps if x!=favorite]
    return propose_plan(s,title,steps,'My experiences have given me an idea.')

def progress_plan(c,s,place):
    p=current_plan(s)
    if not p:return
    expected=p['steps'][p['index']]
    if place!=expected:return
    p['index']+=1
    record(c,s,'Plan progress: '+p['title']+' ('+str(p['index'])+'/'+str(len(p['steps']))+').')
    if p['index']>=len(p['steps']):
        p['status']='completed';s['active_plan']=None
        summary='I completed my own plan: '+p['title']+'.'
        s['reflection']=summary;s['milestones'].append({'day':s['day'],'event':summary})
        remember(c,s,place,summary,1.0);record(c,s,summary)
        s['plan_history'].append({'day':s['day'],'title':p['title'],'outcome':'completed'})
        s['plan_history']=s['plan_history'][-40:]

def plan_failure(c,s,reason):
    p=current_plan(s)
    if not p:return
    p['failures']+=1;s['failed_attempts']+=1
    record(c,s,'Plan setback: '+reason+'; Arthur will reconsider.')
    if p['failures']>=3:
        p['status']='abandoned';s['active_plan']=None
        s['plan_history'].append({'day':s['day'],'title':p['title'],'outcome':'abandoned: '+reason})
        remember(c,s,s.get('goal','home'),'My plan '+p['title']+' did not work. '+reason,0.85)
    else:
        # Recovery step is explicit and safe; then retry the planned destination.
        s['goal']='home';s['target']=list(SITES['home']);s['thought']='That did not work. I will recharge and try again.'

def choose(s):
    if s['energy']<22:
        return 'home','My battery is running low. I should go home.'
    if s['hunger']>78:
        return 'grove','I feel hungry. I should find berries in the grove.'
    p=current_plan(s)
    if p:return p['steps'][p['index']], 'I am working on my plan: '+p['title']
    options=['pond','meadow','grove','hill','home']
    weights=[max(.2,3+s['preferences'].get(k,0)*.2+4*preference_score(s,k,public_only=True)+max(0,4-s['visits'].get(k,0))) for k in options]
    a=next((a for a in s['aspirations'] if a['name']==s.get('active_aspiration') and not a['completed']),None)
    if a:weights[options.index(a['place'])]+=8+s['traits']['persistence']/15
    if s['curiosity']<25:weights[-1]+=8
    # Arthur is increasingly drawn toward habitats of species he has not met.
    for cr in s.get('wild_creatures',[]):
        if cr['species'] not in s['seen_species'] and cr['habitat'] in options:
            weights[options.index(cr['habitat'])]+=5
    if sum(s['inventory'].values())>=7:weights[-1]+=18
    if sum(s['inventory'].values())<4:
        for k in ('grove','meadow','hill'):weights[options.index(k)]+=3
    dest=random.choices(options,weights=weights,k=1)[0]
    return dest,{'pond':'I want to listen to the water.','meadow':'Maybe there are flowers to discover.','grove':'I wonder what is growing in the grove.','hill':'The hill might have a nice view.','home':'I feel like spending time at home.'}[dest]


# Deterministic world resources. Every action is validated by the simulation.
RESOURCE_NODES={'grove':{'wood':2,'berries':2},'meadow':{'flowers':2},'hill':{'stone':2},'pond':{'stone':1}}
RECIPES={'flower_garden':{'wood':2,'flowers':3},'stone_marker':{'stone':3,'wood':1},'rest_bench':{'wood':5,'stone':2}}

def activity(c,s,kind,message,place=None):
    s['last_action']=message
    s['activity_count'][kind]=s['activity_count'].get(kind,0)+1
    record(c,s,message)
    if place and s['activity_count'][kind] in (1,5,12):remember(c,s,place,message,0.7)

def interact(c,s,place):
    if place in building.RESOURCE_SPECS:
        grounded_events(c,s,building.harvest(s,place))
    if place=='grove' and s['hunger']>30 and s['inventory']['berries']:
        s['inventory']['berries']-=1;s['hunger']=max(0,s['hunger']-35)
        activity(c,s,'eat','Arthur ate a berry from his backpack.',place)
    if place=='homesite':
        grounded_events(c,s,building.handle_action(s,'deposit'))
        if s['house']['status']=='complete':s['energy']=min(100,s['energy']+45)
    if place=='home' and s.get('house',{}).get('status')=='complete':
        choices=[(name,recipe) for name,recipe in RECIPES.items() if all(s['inventory'].get(k,0)>=v for k,v in recipe.items())]
        if choices and len(s['structures'])<12:
            name,recipe=sorted(choices,key=lambda q:(sum(q[1].values()),q[0]))[0]
            for item,n in recipe.items():s['inventory'][item]-=n
            location=[(19,18),(23,18),(18,16),(24,16),(20,20),(22,20),(17,19),(25,19),(18,21),(24,21),(20,13),(22,13)][len(s['structures'])]
            s['structures'].append({'kind':name,'x':location[0],'y':location[1],'day':s['day']});s['craft_count']+=1
            activity(c,s,'build',f'Arthur built a {name.replace("_"," ")} near his shelter.',place)
            remember(c,s,place,'I made a '+name.replace('_',' ')+' using materials I found.',.95)
    if place=='pond' and 'shimmering_water' not in s['discoveries']:
        s['discoveries'].append('shimmering_water')
        activity(c,s,'discover','Arthur discovered a strange shimmer in the pond.',place)
    if place=='hill' and s['day']>=2 and 'hilltop_stars' not in s['discoveries'] and (s['minute']>=1200 or s['minute']<360):
        s['discoveries'].append('hilltop_stars')
        activity(c,s,'discover','Arthur discovered how bright the stars look from the hill.',place)

def arrive(c,s,dest):
    """Apply one visit's effects only after physically reaching its destination."""
    s['visits'][dest]=s['visits'].get(dest,0)+1
    s['preferences'][dest]=min(20,s['preferences'].get(dest,0)+1)
    s['last_action']='Visited '+dest
    if dest=='home':s['energy']=min(100,s['energy']+62);s['hunger']=max(0,s['hunger']-14)
    if dest in ('town','market'):s['coins']=min(9999,s.get('coins',0)+2)
    if dest=='grove':s['hunger']=max(0,s['hunger']-20)
    if dest in ('pond','hill','meadow'):s['curiosity']=min(100,s['curiosity']+24);s['mood']=min(100,s['mood']+2)
    interact(c,s,dest)
    evolve(c,s,dest)
    progress_plan(c,s,dest)
    if s['house']['status'] in ('paused','complete') and not current_plan(s) and random.random()<.28:create_fallback_plan(s)
    if s['visits'][dest] in (1,3,8,16,32):
        remember(c,s,dest,'I visited the '+dest+' for the '+str(s['visits'][dest])+' time.',0.4 if s['visits'][dest]>1 else 0.8)
    record(c,s,{'town':'Arthur visited the town square.','market':'Arthur browsed the marketplace.','forest':'Arthur wandered through the old forest.','beach':'Arthur explored the sandy beach.','pond':'Arthur watched ripples on the pond.','meadow':'Arthur explored the meadow flowers.','grove':'Arthur found berries in the grove.','hill':'Arthur admired the view from the hill.','home':'Arthur returned to his shelter to recharge.','homesite':'Arthur reached the site of his new home.'}[dest])
    observe(s,'visit','I reached the '+dest+'.',place=dest,importance=.6)
    s['target']=None
    if s.get('pending_request')==dest:s['pending_request']=None

def viewer_count():
    now=time.monotonic()
    with VIEWER_LOCK:
        for k,t in list(VIEWERS.items()):
            if now-t>15:del VIEWERS[k]
        return len(VIEWERS)

SHOP={'wood':5,'stone':7,'flowers':3,'berries':4}

def direct_control(message):
    """Only unambiguous short commands bypass model latency."""
    if not isinstance(message,str):return False
    text=message.strip().lower().rstrip('.!')
    return bool(re.fullmatch(r'(?:please )?(?:stop(?: here)?|wait(?: here)?|stay(?: here)?|continue|resume|carry on)',text))


def token_owner(token, configured=None):
    expected=OWNER_TOKEN if configured is None else configured
    return isinstance(expected,str) and len(expected)>=24 and isinstance(token,str) and hmac.compare_digest(token.encode('utf-8'),expected.encode('utf-8'))


def grounded_events(connection,state,events):
    """Only committed simulation events enter public memory and the journal."""
    for event in events:
        message=event['message']
        state['last_action']=message
        record(connection,state,message)
        details=dict(event.get('details') or {})
        items=details.get('items',{})
        if len(items)==1:details['material']=next(iter(items))
        observe(state,event['type'],message,place=event.get('place'),importance=event.get('salience',.6),metadata=details)
        if event['type']=='house_completed':
            state['thought']='I made a home of my own, one careful step at a time.'
            state['milestones'].append({'day':state['day'],'event':message})
        elif event['type']=='house_started':
            state['thought']='I would like a home I have made myself. I need to gather the foundation materials first.'


def finite_number(value, default=0.):
    try:
        result=float(value)
        return result if math.isfinite(result) else float(default)
    except (ValueError,TypeError):
        return float(default)


def owner_allowed(bind_host, client_ip):
    """Retain the local-owner/public-read-only model of earlier releases."""
    return bind_host in ('127.0.0.1','::1','localhost') and client_ip in ('127.0.0.1','::1')


@lru_cache(maxsize=1)
def reachable_cells():
    """Exclude isolated pockets when restoring an older world's saved positions."""
    queue=deque([HOME]);seen={HOME}
    while queue:
        x,y=queue.popleft()
        for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)):
            point=x+dx,y+dy
            if point not in seen and walkable(*point):seen.add(point);queue.append(point)
    return frozenset(seen)


def restore_position(point):
    x=max(1.,min(W-2.,point[0]));y=max(1.,min(H-2.,point[1]))
    connected=reachable_cells()
    return nearest_clear((x,y),lambda gx,gy:(gx,gy) in connected)


class Runtime:
    """One shared authoritative world; rendering and network latency cannot change its pace.

    Only this runtime mutates state, under its lock. A 20 Hz loop integrates motion;
    0.5 Hz behavior decisions, 1.25-second saves and optional background AI are separate.
    GET handlers only read the latest immutable published snapshot.
    """
    def __init__(self, db_path=None, enable_ai=None, ai_client=None):
        self.lock=threading.RLock()
        self.connection=connect(db_path)
        existed=self.connection.execute("SELECT 1 FROM kv WHERE key='state'").fetchone()
        self.state=load(self.connection)
        self.run_id=uuid.uuid4().hex
        self.seq=0
        self.last_tick_at=time.monotonic()
        self.elapsed=0.
        self.brain_elapsed=0.
        self.save_elapsed=0.
        self.reflection_elapsed=0.
        self.dwell=0.
        self.closed=False
        self.history_revision=-1
        self.journal=[]
        self.recall=[]
        self.command_revision=0
        self.ai_idea=None
        self.entities={}
        self._migrate()
        client=ai_client or AIClient(api_key=os.environ.get('OPENAI_API_KEY'),model=MODEL)
        self.ai_configured=bool(client.status().get('configured'))
        self.enable_ai=self.ai_configured if enable_ai is None else bool(enable_ai and self.ai_configured)
        self.conversation=ConversationEngine(self.state,client=client,enabled=self.enable_ai,
            autonomy=os.environ.get('ARTHUR_AI_AUTONOMY','1').lower() not in ('0','false','off'),
            interval=bounded_int('ARTHUR_THINK_INTERVAL',180,30,3600),
            limit=bounded_int('ARTHUR_MAX_AI_CALLS_PER_HOUR',40,1,240))
        if not existed:record(self.connection,self.state,'Arthur woke up in his little world.')
        s=self.state
        self.mover=Mover(s['x'],s['y'],walkable,heading=s['heading'],distance=s['distance'])
        self._sync_entities()
        if not s.get('paused') and s.get('target') and s.get('goal') in SITES:
            self._start_goal(s['goal'],s['thought'])
        else:
            self.dwell=1.
        save(self.connection,s)
        self.connection.commit()
        self._publish()

    def _migrate(self):
        s=self.state
        # Nested defaults keep v1.6 inventories, projects, creatures and memories intact.
        default=new_state()
        for section in ('inventory','traits','preferences','visits'):
            if not isinstance(s.get(section),dict):s[section]=copy.deepcopy(default[section])
            for key,value in default[section].items():s[section].setdefault(key,value)
        for key in ('plans','companions','wild_creatures','seen_species','aspirations','structures','discoveries','chat_history','milestones','plan_history'):
            if not isinstance(s.get(key),list):s[key]=copy.deepcopy(default[key])
        x=finite_number(s.get('x'),HOME[0]);y=finite_number(s.get('y'),HOME[1])
        x,y=restore_position((x,y))
        s['x'],s['y']=x,y
        s['distance']=max(0.,finite_number(s.get('distance')),finite_number(s.get('steps')))
        s['steps']=max(0,int(finite_number(s.get('steps'),0)))
        s['heading']=finite_number(s.get('heading'),math.pi/2)
        s.update(schema_version=18,vx=0.,vy=0.,speed=0.,moving=False)
        s['paused']=bool(s.get('paused',False))
        if s['paused']:s['target']=None
        s['day']=max(1,int(finite_number(s.get('day'),1)))
        s['minute']=finite_number(s.get('minute'),480)%1440
        for key in ('energy','hunger','curiosity','mood'):s[key]=max(0.,min(100.,finite_number(s.get(key),default[key])))
        if s.get('goal') not in SITES:s['goal']='home';s['target']=None
        if s.get('target') is not None:s['target']=list(SITES[s['goal']])
        building.ensure_state(s)
        mind=ensure_mind(s)
        if not mind.get('legacy_memories_imported'):
            rows=self.connection.execute('SELECT day,place,summary,salience FROM memories ORDER BY id DESC LIMIT 80').fetchall()
            for day,place,summary,salience in reversed(rows):
                observe(s,'legacy_memory',f'From day {day}: {summary}',place=place,importance=salience)
            mind['legacy_memories_imported']=True
        if not s['wild_creatures']:s['wild_creatures']=seed_wild()
        for i,cr in enumerate(s['wild_creatures']):
            cr.setdefault('id',i+1)
            cr.setdefault('habitat',SPECIES.get(cr.get('species'),SPECIES['Mossbit'])['habitat'])
            cr.setdefault('bond',0);cr.setdefault('seen',False)
        for i,friend in enumerate(s['companions']):
            friend.setdefault('id','companion-'+str(i+1))
            friend.setdefault('nickname',friend['species'])
            friend.setdefault('form',friend['species'])
            friend.setdefault('xp',0);friend.setdefault('level',1)
            friend.setdefault('friendship',friend.get('bond',55))
            friend.setdefault('last_xp_step',s['steps'])
            if i!=s.get('active_companion',0)%max(1,len(s['companions'])) and 'sanctuary_x' in friend:
                friend['x']=friend['sanctuary_x'];friend['y']=friend['sanctuary_y']

    def _sync_entities(self):
        s=self.state
        for group in ('wild_creatures','companions'):
            for i,entity in enumerate(s[group]):
                entity.setdefault('id',i+1 if group=='wild_creatures' else 'companion-'+str(i+1))
                key=(group,str(entity['id']))
                if key in self.entities:continue
                fallback=SITES.get(entity.get('habitat'),(s['x'],s['y']))
                x,y=restore_position((finite_number(entity.get('x'),fallback[0]),finite_number(entity.get('y'),fallback[1])))
                cruise={'Mossbit':.6,'Emberoo':1.12,'Puddlepip':.66,'Thornlet':.84,'Moonmote':.52,'Pebblin':.4}.get(entity.get('species'),.6)
                if group=='companions':cruise=1.8
                mover=Mover(x,y,walkable,cruise=cruise,acceleration=2.4,braking=3.,heading=finite_number(entity.get('heading'),math.pi/2),distance=max(0.,finite_number(entity.get('distance'))))
                self.entities[key]=mover
                entity.update(mover.fields())
                if group=='companions' and i!=s.get('active_companion',0)%len(s[group]):
                    entity['sanctuary_x'],entity['sanctuary_y']=x,y
                entity.setdefault('behavior','resting')

    def _start_goal(self, goal, thought=None):
        s=self.state
        if goal not in SITES:return False
        if not self.mover.active and length((self.mover.x,self.mover.y),SITES[goal])<.04:
            s.update(goal=goal,target=None,paused=False,pending_request=None)
            s['last_action']='Already at '+goal
            if thought:s['thought']='I am already at the '+goal+'.'
            self.dwell=1.8
            return True
        if not self.mover.set_target(SITES[goal]):
            plan_failure(self.connection,s,'I could not find a path to my destination')
            observe(s,'route_failed','I could not find a clear route to '+goal+'.',place=goal,importance=.65)
            s['target']=None
            self.dwell=2.
            return False
        s['goal']=goal;s['target']=list(SITES[goal]);s['paused']=False
        if thought:s['thought']=thought
        s['last_action']='Walking to '+goal
        self.dwell=0.
        return True

    def _building_task(self,hint):
        s=self.state;goal=hint['goal'];action=hint['action']
        s['thought']=hint['reason']
        if length((s['x'],s['y']),SITES[goal])>.15:
            if action=='recharge' and s['energy']<22:
                observe(s,'fatigue','I needed to stop and recharge before continuing my work.',place=goal,importance=.7)
            self._start_goal(goal,hint['reason'])
            return
        # A resource patch or a construction stage can require several actions
        # at one location. Do them in place rather than inventing another trip.
        s['target']=None
        if action in ('gather','eat'):
            grounded_events(self.connection,s,building.harvest(s,goal))
            if s['hunger']>30 and s['inventory']['berries']:
                s['inventory']['berries']-=1;s['hunger']=max(0,s['hunger']-35)
                activity(self.connection,s,'eat','Arthur ate a berry from his backpack.',goal)
            self.dwell=1.
        elif action=='deposit':
            grounded_events(self.connection,s,building.handle_action(s,'deposit'))
            self.dwell=.25
        elif action=='recharge':
            s['energy']=min(100,s['energy']+10);s['last_action']='Recharging at the shelter'
            self.dwell=1.
        else:
            s['last_action']='Working on my home' if action=='work' else 'Waiting for materials to regrow'
            self.dwell=.5

    def _choose_next(self):
        s=self.state
        hint=building.choose_next(s)
        if hint:
            self._building_task(hint)
            return
        if s['energy']<22 and s['house']['status']=='complete':
            goal,thought='homesite','I can recharge at the home I built.'
        elif self.ai_idea and not current_plan(s) and s['energy']>=22 and s['hunger']<=78:
            goal,thought=self.ai_idea;self.ai_idea=None
        else:
            self.ai_idea=None
            goal,thought=choose(s)
        if length((s['x'],s['y']),SITES[goal])<.1:
            if goal in ('home','homesite') and s['energy']<22:
                s['energy']=min(100,s['energy']+10);self.dwell=1.
                s['last_action']='Recharging at my home' if goal=='homesite' else 'Recharging at the shelter'
                return
            alternatives=[p for p in ('meadow','pond','grove','hill','home') if length((s['x'],s['y']),SITES[p])>1]
            goal=random.choice(alternatives)
            thought='I am ready to explore the '+goal+'.'
        if s['energy']<22:
            observe(s,'fatigue','I needed a recharge after exploring.',place=goal,importance=.7)
        self._start_goal(goal,thought)

    def _wildlife_decisions(self):
        s=self.state
        self._sync_entities()
        for creature in s['wild_creatures']:
            mover=self.entities[('wild_creatures',str(creature['id']))]
            if mover.active:continue
            creature['behavior']={'Mossbit':'grazing','Emberoo':'looking around','Puddlepip':'watching the water','Thornlet':'foraging','Moonmote':'drifting','Pebblin':'resting'}.get(creature['species'],'resting')
            if random.random()>.42:continue
            sx,sy=SITES.get(creature['habitat'],HOME)
            candidates=[]
            if creature['species']=='Puddlepip' and length((mover.x,mover.y),(s['x'],s['y']))<2:
                dx=mover.x-s['x'];dy=mover.y-s['y'];norm=max(.01,math.hypot(dx,dy))
                candidates.append((round(mover.x+dx/norm*1.5),round(mover.y+dy/norm*1.5)))
                creature['behavior']='shyly retreating'
            else:creature['behavior']='exploring'
            candidates.extend((round(mover.x)+random.randint(-2,2),round(mover.y)+random.randint(-2,2)) for _ in range(5))
            for point in candidates:
                if abs(point[0]-sx)<=5 and abs(point[1]-sy)<=5 and length((mover.x,mover.y),point)>.25 and clear_at(*point,walkable) and mover.set_target(point):break
        friends=s['companions']
        for i,friend in enumerate(friends):
            mover=self.entities[('companions',str(friend['id']))]
            active=i==s.get('active_companion',0)%len(friends)
            if active:
                friend['behavior']='following Arthur'
                gap=length((mover.x,mover.y),(s['x'],s['y']))
                if gap>1.3:
                    target=(s['x']-.8*math.cos(self.mover.heading),s['y']-.8*math.sin(self.mover.heading))
                    if not clear_at(*target,walkable):target=(s['x'],s['y'])
                    mover.set_target(target)
                elif not self.mover.active and gap<1.2:mover.stop()
            else:
                friend['behavior']='resting at the sanctuary'
                if not mover.active and (length((mover.x,mover.y),SANCTUARY)>3 or random.random()<.3):
                    target=(random.randint(23,27),random.randint(18,21))
                    if clear_at(*target,walkable):mover.set_target(target)

    def _brain(self):
        s=self.state
        if s['house']['status'] in ('paused','complete') and not current_plan(s) and (not s['plans'] or random.random()<.02):
            plan=create_fallback_plan(s)
            if plan:record(self.connection,s,'Arthur made a plan: '+plan['title'])
        creature_tick(self.connection,s)
        companion_tick(self.connection,s)
        self._wildlife_decisions()

    def _execute_intent(self,result,*,source='chat',revision=None):
        intent=result.get('intent') if isinstance(result,dict) else None
        if not isinstance(intent,dict):return ''
        kind=intent.get('kind','none');s=self.state
        if kind=='none':return ''
        if revision is not None and revision!=self.command_revision:
            return 'The world received a newer instruction while I was replying, so that newer instruction takes priority.'
        background=source=='reflection'
        if background and (s.get('paused') or s.get('pending_request')):return ''
        if background and kind not in ('go_to','start_house','design_house'):return ''
        if kind=='go_to':
            goal=intent.get('destination')
            if not isinstance(goal,str) or goal not in SITES:return 'That destination does not exist in this world.'
            if background:
                if s['house']['status'] in ('planned','active'):return ''
                self.ai_idea=(goal,'I would like to spend some time at '+goal+'.')
                return ''
            self.command_revision+=1;s['pending_request']=goal
            ok=self._start_goal(goal,'I am going to the '+goal+'.')
            return ('Walking to '+goal+'.' if self.mover.active else 'I am already at '+goal+'.') if ok else 'I could not find a safe route there.'
        if kind=='stop' and not background:
            self.command_revision+=1;s['paused']=True;s['target']=None;s['pending_request']=None
            self.mover.brake_to_stop();s.update(self.mover.fields())
            s['last_action']='Slowing to a stop' if self.mover.active else 'Standing still'
            return 'Pausing here. Say “continue” when you want me to carry on.'
        if kind=='resume' and not background:
            self.command_revision+=1;s['paused']=False
            self._choose_next()
            return 'Continuing from here.'
        build_actions={'start_house':'start','pause_house':'pause','resume_house':'resume','design_house':'style'}
        if kind in build_actions:
            if background and kind=='start_house' and s['house']['status']!='planned':return ''
            action=build_actions[kind]
            style=intent.get('style','none')
            try:
                if action=='style':
                    events=building.handle_action(s,'style',{'style':style})
                else:
                    # A combined start + design is validated before changing the project.
                    events=[]
                    if action=='start' and style!='none':events+=building.handle_action(s,'style',{'style':style})
                    events+=building.handle_action(s,action)
                grounded_events(self.connection,s,events)
            except building.BuildError as error:return str(error)
            if not background:
                self.command_revision+=1
                if action in ('start','resume'):
                    s['paused']=False;s['pending_request']=None;self._choose_next()
                elif action=='pause':
                    self.dwell=max(self.dwell,1.)
            return events[-1]['message'] if events else 'That house setting is already in place.'
        return 'That action is not available in this world.'

    def _poll_ai(self):
        for completion in self.conversation.poll(self.state,self.command_revision):
            mode=completion['mode']
            if mode=='error':continue
            result=completion['result']
            apply_model_result(self.state,result,source='reflection' if mode=='reflection' else 'model',mode=mode)
            note=self._execute_intent(result,source=mode,revision=completion['revision'])
            if mode=='chat':
                self.conversation.finish(self.state,completion['entry'],result,note)
            elif result.get('reflection'):
                self.state['thought']=str(result['reflection'])[:280]

    def step(self, dt):
        """Advance measured elapsed seconds; ignore offline time after suspension."""
        with self.lock:
            if self.closed:return
            dt=max(0.,min(.25,finite_number(dt)))
            if dt<=0:return
            s=self.state
            self.elapsed+=dt;self.seq+=1
            self.brain_elapsed+=dt;self.save_elapsed+=dt;self.reflection_elapsed+=dt
            s['minute']+=2.*dt
            if s['minute']>=1440:
                s['minute']-=1440;s['day']+=1;record(self.connection,s,'A new day begins.')
            building.tick_resources(s,dt)
            s['hunger']=min(100.,s['hunger']+.3*dt)
            s['curiosity']=max(0.,s['curiosity']-.06*dt)
            if self.mover.active:
                arrived=self.mover.update(dt)
                s['energy']=max(0.,s['energy']-.225*dt)
                s.update(self.mover.fields())
                s['steps']=int(self.mover.distance)
                if arrived:
                    if s.get('paused'):
                        s['last_action']='Standing still'
                    else:
                        arrive(self.connection,s,s['goal'])
                        self.dwell=1.8 if s['goal']!='home' else 3.
            else:
                self.dwell=max(0.,self.dwell-dt)
                if self.dwell<=0 and not s.get('paused'):self._choose_next()
                s.update(self.mover.fields())
            grounded_events(self.connection,s,building.step_work(s,dt))
            for group in ('wild_creatures','companions'):
                for i,entity in enumerate(s[group]):
                    mover=self.entities.get((group,str(entity.get('id'))))
                    if mover is None:continue
                    mover.update(dt)
                    entity.update(mover.fields())
                    if group=='companions' and i!=s.get('active_companion',0)%len(s[group]):
                        entity['sanctuary_x'],entity['sanctuary_y']=mover.x,mover.y
            if self.brain_elapsed>=2.:
                self.brain_elapsed%=2.
                self._brain()
            if self.reflection_elapsed>=60.:
                self.reflection_elapsed%=60.
                s['reflection']=local_thought(s)
                s['mind']['current_thought']=s['reflection']
                if not s.get('paused'):s['thought']=s['reflection']
            self._poll_ai()
            if self.save_elapsed>=1.25:
                self.save_elapsed%=1.25
                save(self.connection,s);self.connection.commit()
            self._publish()
            self.last_tick_at=time.monotonic()

    def _publish(self):
        if self.history_revision!=HISTORY_REVISION:
            rows=self.connection.execute('SELECT day,minute,event FROM journal ORDER BY id DESC LIMIT 40').fetchall()
            self.journal=[{'day':d,'minute':int(m),'event':e} for d,m,e in rows]
            self.recall=memories(self.connection,12)
            self.history_revision=HISTORY_REVISION
        ensure_mind(self.state)
        stamp=round(time.time()*1000)
        meta={'snapshot_ms':stamp,'seq':self.seq,'run_id':self.run_id,'epoch':self.run_id,'sim_hz':SIM_HZ,'version':VERSION,'ai_configured':self.ai_configured}
        s=copy.deepcopy(self.state)
        s.pop('chat_requests',None);s.pop('ai_usage',None)
        s['construction']=building.public_house(s)
        self._snapshot={'state':s,'journal':self.journal,'memories':self.recall,
            'ai':self.conversation.status(self.state),'ai_enabled':self.enable_ai,
            'server_time':stamp/1000,'species':SPECIES,
            'encyclopedia':creature_encyclopedia(s),'sanctuary':list(SANCTUARY),'shop':SHOP,
            'sites':SITES,'metadata':meta,**meta}

    def snapshot(self, owner_mode=False):
        with self.lock:
            snapshot=copy.deepcopy(self._snapshot)
            if not owner_mode:
                # Enforce the private panels at the API boundary, not only in
                # the browser. Legacy saves may contain personal text here too.
                state=snapshot['state']
                # Saved free-form thoughts/actions have no visibility marker.
                # Derive the spectator summary from bounded world facts instead
                # of trusting old saves or private conversation-derived text.
                state['thought']=local_thought(state)
                if state.get('paused'):
                    state['last_action']='Slowing to a stop' if state.get('moving') else 'Standing still'
                elif state.get('construction',{}).get('working'):
                    state['last_action']='Working on the house'
                elif state.get('goal') in SITES:
                    state['last_action']=('Walking to ' if state.get('moving') else 'Visiting ')+state['goal']
                else:
                    state['last_action']='Exploring the world'
                for key in ('chat_history','plans','plan_history','aspirations',
                            'milestones','discoveries'):
                    state[key]=[]
                for key in ('preferences','visits','traits','activity_count'):
                    state[key]={}
                for key in ('reflection','project'):
                    state[key]=''
                for key in ('mind','active_plan','active_aspiration'):
                    state[key]=None
                state['chat_status']={'status':'spectator','mode':self.conversation.mode}
                snapshot['memories']=[]
                # The journal contains committed world events, not chat text.
                # Keep it, movement, creatures, and visible construction public.
                # Only the renderer's fields are needed for crafted objects.
                state['structures']=[{key:item[key] for key in ('kind','x','y') if key in item}
                                     for item in state.get('structures',[]) if isinstance(item,dict)]
            snapshot.update(viewer_count=viewer_count(),owner_mode=bool(owner_mode))
            return snapshot

    def command(self, kind, data):
        with self.lock:
            s=self.state
            if not isinstance(data,dict):return 400,{'error':'JSON object required'}
            code=200
            if kind=='chat':
                if 'retry' in data and not isinstance(data['retry'],bool):return 400,{'error':'Retry must be true or false.'}
                message=data.get('message')
                code,result,immediate=self.conversation.submit(s,message,data.get('request_id'),
                    retry=data.get('retry',False),revision=self.command_revision,force_local=direct_control(message))
                if code>=400:return code,result
                if immediate is not None:
                    apply_model_result(s,immediate,source='local',mode='chat')
                    note=self._execute_intent(immediate,source='chat',revision=self.command_revision)
                    self.conversation.finish_local(s,result['request_id'],immediate,note)
                    result.update(reply=immediate['reply'],action_note=note)
            elif kind=='build':
                action=data.get('action')
                try:
                    events=building.handle_action(s,action,{key:value for key,value in data.items() if key!='action'})
                except building.BuildError as error:return error.status,{'error':str(error)}
                self.command_revision+=1
                grounded_events(self.connection,s,events)
                if action in ('start','resume'):
                    s['paused']=False;s['pending_request']=None;self._choose_next()
                result={'ok':True,'construction':building.public_house(s),
                        'message':events[-1]['message'] if events else 'That house setting is already in place.'}
            elif kind=='suggest':
                goal=data.get('goal')
                if not isinstance(goal,str) or goal not in SITES:return 400,{'error':'Unknown location'}
                self.command_revision+=1
                s['pending_request']=goal
                if not self._start_goal(goal,'I am going to the '+goal+'.'):
                    return 409,{'error':'Arthur cannot currently reach that location'}
                record(self.connection,s,'Arthur received a suggestion to visit '+goal+'.')
                result={'ok':True}
            elif kind=='buy':
                item=data.get('item')
                if not isinstance(item,str) or item not in SHOP:return 400,{'error':'Unknown item'}
                amount=SHOP[item]
                if length((s['x'],s['y']),SITES['market'])>3:return 409,{'error':'Arthur must be at the market to shop'}
                if s.get('coins',0)<amount:return 409,{'error':'Not enough coins'}
                if sum(s['inventory'].values())>=24:return 409,{'error':'Arthur’s backpack is full'}
                s['coins']-=amount;s['inventory'][item]=s['inventory'].get(item,0)+1
                self.command_revision+=1
                text='Arthur purchased '+item+' for '+str(amount)+' coins.'
                record(self.connection,s,text)
                observe(s,'purchase',text,place='market',importance=.5,metadata={'material':item})
                result={'ok':True}
            else:return 404,{'error':'Not found'}
            save(self.connection,s);self.connection.commit()
            self._publish()
            return code,result

    def run(self, stop_event):
        previous=time.monotonic()
        next_tick=previous+1./SIM_HZ
        while not stop_event.wait(max(0.,next_tick-time.monotonic())):
            now=time.monotonic()
            self.step(now-previous)
            previous=now
            next_tick+=1./SIM_HZ
            if next_tick<now-.1:next_tick=now+1./SIM_HZ

    def close(self):
        with self.lock:
            if self.closed:return
            save(self.connection,self.state);self.connection.commit();self.connection.close()
            self.closed=True
        self.conversation.close()


STATIC_FILES={'index.html','app.js','motion.js','landscape.js','character.js','styles.css','arthur_sprites.png'}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)

    @property
    def runtime(self):
        return getattr(self.server,'runtime',None) or RUNTIME

    def is_owner(self):
        return owner_allowed(HOST,self.client_address[0]) or token_owner(self.headers.get('X-Arthur-Owner',''))

    def reply(self,code,data):
        payload=json.dumps(data,allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        try:self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/healthz':
            runtime=self.runtime
            worker=getattr(self.server,'simulation_thread',None)
            # Avoid the simulation lock: a stalled loop must fail health checks.
            healthy=bool(runtime is not None and not runtime.closed and worker is not None
                         and worker.is_alive() and time.monotonic()-runtime.last_tick_at<10.)
            return self.reply(200 if healthy else 503,{'status':'ok' if healthy else 'unhealthy'})
        if path=='/api/state':
            viewer=self.headers.get('X-Arthur-Viewer','')[:64]
            if viewer and all(ch.isalnum() or ch in '-_' for ch in viewer):
                with VIEWER_LOCK:VIEWERS[viewer]=time.monotonic()
            return self.reply(200,self.runtime.snapshot(self.is_owner()))
        if path=='/api/world':return self.reply(200,public_world())
        if path=='/':path='/index.html'
        if path.startswith('/') and path[1:] in STATIC_FILES:
            self.path=path
            return super().do_GET()
        return self.reply(404,{'error':'Not found'})

    def do_HEAD(self):
        # SimpleHTTPRequestHandler otherwise exposes arbitrary file metadata.
        path=urlsplit(self.path).path
        if path=='/':path='/index.html'
        if path.startswith('/') and path[1:] in STATIC_FILES:
            self.path=path
            return super().do_HEAD()
        self.send_error(404,'Not found')

    def do_POST(self):
        path=urlsplit(self.path).path
        if path not in ('/api/suggest','/api/chat','/api/buy','/api/build'):return self.reply(404,{'error':'Not found'})
        if not self.is_owner():return self.reply(403,{'error':'Spectator mode is read-only. Use Owner access to unlock your controls.'})
        # A local owner action must originate from this page, not a third-party site.
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
            return self.reply(403,{'error':'Owner actions must come from Arthur’s page'})
        try:n=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.reply(400,{'error':'Invalid request length'})
        if not 1<=n<=16000:return self.reply(400,{'error':'Invalid request length'})
        try:data=json.loads(self.rfile.read(n))
        except (ValueError,UnicodeDecodeError):return self.reply(400,{'error':'Invalid JSON'})
        code,payload=self.runtime.command(path.rsplit('/',1)[-1],data)
        return self.reply(code,payload)

    def log_message(self,format,*args):
        if not self.path.startswith('/api/state'):super().log_message(format,*args)


def main():
    global RUNTIME
    httpd=ThreadingHTTPServer((HOST,PORT),Handler)
    RUNTIME=Runtime()
    httpd.runtime=RUNTIME
    stop=threading.Event()
    worker=threading.Thread(target=RUNTIME.run,args=(stop,),name='arthur-world',daemon=True)
    httpd.simulation_thread=worker
    worker.start()
    def shutdown(signum=None,frame=None):
        stop.set()
        threading.Thread(target=httpd.shutdown,daemon=True).start()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,shutdown)
    print(f'Arthur v{VERSION} running at http://{HOST}:{PORT} | save: {DB} | AI configured: {RUNTIME.ai_configured}',flush=True)
    try:httpd.serve_forever(poll_interval=.2)
    finally:
        stop.set();worker.join(timeout=3)
        RUNTIME.close();httpd.server_close()


if __name__=='__main__':main()
