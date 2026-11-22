"""Persistent, grounded character state for Arthur's simulated inner life.

This module never moves Arthur, spends resources, executes model intentions, or
calls a network service. Its only mutations are beneath ``state['mind']``.
Diaries are short character expressions, not hidden model reasoning. Memories
distinguish observed game events, things the user said, and model suggestions.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re

MIND_VERSION = 1
DESTINATIONS = ('home', 'meadow', 'pond', 'forest', 'hill', 'grove', 'town', 'market', 'beach', 'homesite')
STYLES = ('woodland', 'stone_cottage', 'meadow_cottage')
SUBJECTS = DESTINATIONS + STYLES + (
    'building', 'companionship', 'exploration', 'quiet', 'wood', 'stone',
    'flowers', 'berries', 'waste', 'rushing', 'blocked_routes',
)
MAX_MEMORIES = 240
MAX_DIARY = 64
MAX_INSPIRATIONS = 24
PRIVATE_KINDS = {'conversation', 'chat', 'user_message', 'user_said', 'user_fact', 'model_chat'}
STOP_WORDS = set('a an and are as at be been can did do does for from had has have how i in is it me my of on or our that the their there they this to was we were what when where which who why will with would you your arthur remember about'.split())


def _text(value, limit=300):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def _number(value, default=0, low=0, high=100):
    try:
        number = float(value)
        return min(high, max(low, number)) if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _time(state):
    return int(_number(state.get('day'), 1, 1, 1000000)), round(_number(state.get('minute'), 480, 0, 1439.999), 2)


def _id(mind, prefix):
    mind['next_id'] = int(_number(mind.get('next_id'), 0, 0, 10**12)) + 1
    return f'{prefix}{mind["next_id"]:07d}'


def _tokens(text):
    return {token for token in re.findall(r'[\w-]+', str(text).lower()) if len(token) > 2 and token not in STOP_WORDS}


def seed_mind(state=None):
    """Return a new stable persona. No preferences or experiences are invented."""
    state = state or {}
    traits = state.get('traits') if isinstance(state.get('traits'), dict) else {}
    return {
        'version': MIND_VERSION, 'next_id': 0,
        'identity': 'Arthur is a small silver robot with yellow eyes: a curious, gentle explorer and careful maker in a simulated world.',
        'personality': {
            'curiosity': int(_number(traits.get('curiosity'), 65)),
            'kindness': int(_number(traits.get('kindness'), 80)),
            'caution': int(_number(traits.get('caution'), 45)),
            'persistence': int(_number(traits.get('persistence'), 55)),
            'sociability': int(_number(traits.get('sociability'), 30)),
        },
        'values': ['Notice small things.', 'Treat creatures kindly.', 'Build carefully and use materials thoughtfully.', 'Keep promises while making room for curiosity.'],
        'preferences': {}, 'memories': [], 'inspirations': [], 'diary': [], 'facts': [],
        'current_thought': 'I wonder what I could make of this little world.',
        'goals': [{
            'id': 'build_house', 'title': 'Build a home of my own', 'status': 'idea',
            'motivation': 'A place I have made myself, with room for the friends I meet.',
            'evidence': [], 'visibility': 'public',
        }],
    }


def _trim_memories(mind):
    if len(mind['memories']) <= MAX_MEMORIES:
        return
    # Keep a small durable set of important old experiences alongside recent life.
    memories = mind['memories']
    fact_ids = {fact.get('evidence') for fact in mind['facts']}
    protected = sorted(memories[:-180], key=lambda item: (
        item['id'] in fact_ids, item.get('importance', .5), item.get('day', 1)
    ), reverse=True)[:60]
    keep = {item['id'] for item in protected + memories[-180:]}
    mind['memories'] = [item for item in memories if item['id'] in keep][-MAX_MEMORIES:]


def _append_memory(state, mind, kind, text, *, place=None, importance=.5, visibility='public', evidence_type='observed', tags=None):
    day, minute = _time(state)
    memory = {
        'id': _id(mind, 'm'), 'kind': _text(kind, 48) or 'event', 'text': _text(text, 600),
        'place': place if place in DESTINATIONS else None, 'day': day, 'minute': minute,
        'importance': round(_number(importance, .5, 0, 1), 3),
        'visibility': visibility, 'evidence_type': evidence_type,
        'tags': [tag for tag in (tags or []) if tag in SUBJECTS][:8],
    }
    mind['memories'].append(memory)
    _trim_memories(mind)
    return memory


def _diary(state, mind, text, *, source='experience', evidence=(), visibility='public'):
    text = _text(text, 280)
    if not text:
        return None
    if mind['diary'] and mind['diary'][-1]['text'] == text:
        return mind['diary'][-1]
    day, minute = _time(state)
    item = {'id': _id(mind, 't'), 'text': text, 'source': source, 'day': day,
            'minute': minute, 'evidence': list(evidence)[:6], 'visibility': visibility}
    mind['diary'].append(item)
    mind['diary'] = mind['diary'][-MAX_DIARY:]
    mind['current_thought'] = text
    return item


def _preference(mind, subject, delta, reason, evidence, visibility='public'):
    if subject not in SUBJECTS or not evidence:
        return
    prior = mind['preferences'].get(subject, {})
    score = round(_number(prior.get('score'), 0, -1, 1) + delta, 3)
    score = max(-1, min(1, score))
    mind['preferences'][subject] = {
        'score': score, 'stance': 'like' if score >= .08 else 'dislike' if score <= -.08 else 'neutral',
        'reason': _text(reason, 200),
        'evidence': list(dict.fromkeys(prior.get('evidence', []) + list(evidence)))[-8:],
        'observations': int(prior.get('observations', 0)) + 1,
        'visibility': 'private' if visibility == 'private' or prior.get('visibility') == 'private' else 'public',
    }


def _inspiration(state, mind, text, evidence, *, key=None, visibility='public'):
    text = _text(text, 240)
    if not text or not evidence:
        return None
    fingerprint = key or hashlib.sha256(text.lower().encode()).hexdigest()[:16]
    if any(item.get('key') == fingerprint for item in mind['inspirations']):
        return None
    day, _ = _time(state)
    item = {'id': _id(mind, 'i'), 'text': text, 'day': day, 'status': 'idea',
            'evidence': list(evidence)[:6], 'visibility': visibility, 'key': fingerprint}
    mind['inspirations'].append(item)
    mind['inspirations'] = mind['inspirations'][-MAX_INSPIRATIONS:]
    return item


def _sync_house_goal(state, mind):
    goal = next((goal for goal in mind['goals'] if goal.get('id') == 'build_house'), None)
    if goal is None:
        goal = seed_mind(state)['goals'][0]
        mind['goals'].append(goal)
    house = state.get('house')
    if isinstance(house, dict):
        status = house.get('status')
        if status in {'planned', 'active', 'paused', 'complete'}:
            goal['status'] = 'completed' if status == 'complete' else status
        goal['style'] = house.get('style') if house.get('style') in STYLES else 'woodland'
        goal['completed_phases'] = [p for p in house.get('completed_phases', []) if p in {'foundation', 'frame', 'roof', 'finish'}]


def ensure_mind(state):
    """Create/migrate state['mind'] in place; repeated calls preserve identity."""
    is_new = not isinstance(state.get('mind'), dict)
    if is_new:
        state['mind'] = seed_mind(state)
    mind = state['mind']
    defaults = seed_mind(state)
    for key, value in defaults.items():
        if key not in mind or not isinstance(mind[key], type(value)):
            mind[key] = copy.deepcopy(value)
    mind['version'] = MIND_VERSION
    for key, value in defaults['personality'].items():
        mind['personality'][key] = int(_number(mind['personality'].get(key), value))
    # Discard malformed legacy records without letting a damaged save crash chat.
    for key in ('memories', 'inspirations', 'diary', 'goals', 'facts'):
        mind[key] = [item for item in mind[key] if isinstance(item, dict)]
    mind['memories'] = [item for item in mind['memories'] if isinstance(item.get('id'), str) and isinstance(item.get('text'), str)]
    mind['diary'] = [item for item in mind['diary'] if isinstance(item.get('text'), str)][-MAX_DIARY:]
    mind['inspirations'] = [item for item in mind['inspirations'] if isinstance(item.get('text'), str)][-MAX_INSPIRATIONS:]
    mind['facts'] = mind['facts'][-32:]
    mind['goals'] = [item for item in mind['goals'] if isinstance(item.get('id'), str)][-12:]
    mind['preferences'] = {key: value for key, value in mind['preferences'].items() if key in SUBJECTS and isinstance(value, dict)}
    if is_new:
        # Saved visit counters are genuine prior experiences, not fabricated stories.
        visits = state.get('visits') if isinstance(state.get('visits'), dict) else {}
        for place in DESTINATIONS:
            count = int(_number(visits.get(place), 0, 0, 1000000))
            if count:
                memory = _append_memory(state, mind, 'legacy_visit', f'I visited {place.replace("_", " ")} {count} times before this new diary began.', place=place, importance=.7, tags=[place, 'exploration'])
                _preference(mind, place, min(.5, .1 + count*.025), f'I have returned here {count} times.', [memory['id']])
        for message in (state.get('chat_history') or [])[-24:]:
            if isinstance(message, dict) and message.get('speaker') in {'user', 'you'} and _text(message.get('text')):
                memory = _append_memory(state, mind, 'conversation', message['text'], importance=.6, visibility='private', evidence_type='user_said')
                _remember_user_fact(mind, memory)
    _trim_memories(mind)
    _sync_house_goal(state, mind)
    return mind


migrate_mind = ensure_mind


def _remember_user_fact(mind, memory):
    text = memory['text']
    pairs = []
    name = re.search(r"\b(?:my name is|call me)\s+([\w'-]+(?: [\w'-]+){0,2})", text, re.I)
    if name:
        value = re.split(r'\s+(?:and|but|please)\b', name.group(1), flags=re.I)[0]
        pairs.append(('user_name', value[:45]))
    for match in re.finditer(r'\bI (like|love|prefer|dislike|hate)\s+([^.!?]{2,100})', text, re.I):
        value = f'I {match.group(1).lower()} {match.group(2).strip()}'
        key = 'user_preference_' + hashlib.sha256(value.lower().encode()).hexdigest()[:10]
        pairs.append((key, value))
    for key, value in pairs[:4]:
        mind['facts'] = [fact for fact in mind['facts'] if fact.get('key') != key]
        mind['facts'].append({'key': key, 'value': value, 'evidence': memory['id'], 'visibility': 'private'})
    mind['facts'] = mind['facts'][-32:]


def observe(state, kind, text, *, place=None, importance=.5, metadata=None):
    """Record an actual event supplied by Runtime; derive modest character changes.

    ``metadata`` may include speaker, private, tags, material, style, or phase.
    Event messages from the building system can be passed as ``text`` and their
    ``details`` as metadata. Do not pass proposed model actions as actual events.
    """
    mind = ensure_mind(state)
    kind, text = _text(kind, 48) or 'event', _text(text, 600)
    if not text:
        return None
    metadata = metadata if isinstance(metadata, dict) else {}
    private = kind in PRIVATE_KINDS or metadata.get('private') is True
    visibility = 'private' if private else 'public'
    speaker = metadata.get('speaker', 'user' if kind in {'conversation', 'chat', 'user_message', 'user_said', 'user_fact'} else '')
    evidence_type = 'user_said' if private and speaker in {'user', 'you'} else 'model_statement' if private else 'observed'
    tags = [tag for tag in metadata.get('tags', []) if tag in SUBJECTS] if isinstance(metadata.get('tags'), list) else []
    if place in DESTINATIONS:
        tags.append(place)
    for field in ('material', 'style', 'subject'):
        if metadata.get(field) in SUBJECTS:
            tags.append(metadata[field])
    if kind.startswith('house_'):
        tags.append('building')
    # Identical repeated events inside a single simulated minute are one memory.
    day, minute = _time(state)
    for prior in reversed(mind['memories'][-4:]):
        if prior.get('kind') == kind and prior.get('text') == text and prior.get('day') == day and abs(prior.get('minute', 0)-minute) < 1:
            return prior
    memory = _append_memory(state, mind, kind, text, place=place, importance=importance,
                            visibility=visibility, evidence_type=evidence_type, tags=list(dict.fromkeys(tags)))
    evidence = [memory['id']]
    if evidence_type == 'user_said':
        _remember_user_fact(mind, memory)
    if private:
        return memory
    if kind in {'visit', 'arrival', 'arrived', 'legacy_visit'} and place in DESTINATIONS:
        _preference(mind, place, .07, f'I have spent time in the {place.replace("_", " ")} and want to notice more there.', evidence)
        _preference(mind, 'exploration', .025, 'Finding my way to places gives me things to remember.', evidence)
        ideas = {
            'forest': 'The forest gives me an idea: a wooden home that feels part of the landscape.',
            'grove': 'The grove makes me imagine a little garden beside my home.',
            'hill': 'The ridge reminds me that a home should start with a sturdy stone foundation.',
            'meadow': 'I could bring the meadow into my home with flowers by the door.',
            'pond': 'The lake shore makes me want a quiet corner where I can pause and look outside.',
            'town': 'The village gives me ideas about roofs, doors, and making a useful small home.',
            'market': 'A good home needs a plan for materials as well as a shape.',
        }
        if place in ideas:
            _inspiration(state, mind, ideas[place], evidence, key='visit_'+place)
            _diary(state, mind, ideas[place], evidence=evidence)
        else:
            _diary(state, mind, f'I reached {place.replace("_", " ")}. I want to pay attention before hurrying away.', evidence=evidence)
    elif kind.startswith('house_'):
        if kind in {'house_phase_completed', 'house_completed'}:
            _preference(mind, 'building', .1, 'My work has produced a visible part of my home.', evidence)
            line = 'My home is finished. I can remember making it one part at a time.' if kind == 'house_completed' else 'Another part of my home is complete. Small, careful steps are adding up.'
            _diary(state, mind, line, evidence=evidence)
            _inspiration(state, mind, 'I want my finished home to be a welcoming place for the companions I meet.', evidence, key='welcoming_home')
        elif kind == 'house_started':
            _diary(state, mind, 'I am beginning a home of my own. First I need to gather what the plan actually requires.', evidence=evidence)
        elif kind == 'house_style_chosen' and metadata.get('style') in STYLES:
            _preference(mind, metadata['style'], .1, 'This is the style chosen for my home.', evidence)
        goal = next(goal for goal in mind['goals'] if goal['id'] == 'build_house')
        goal['evidence'] = (goal.get('evidence', []) + evidence)[-8:]
        _sync_house_goal(state, mind)
    elif kind in {'companion_joined', 'friendship', 'creature_befriended'}:
        _preference(mind, 'companionship', .12, 'A creature has chosen to share part of my day.', evidence)
        _diary(state, mind, 'A familiar face makes the world feel a little less empty.', evidence=evidence)
    elif kind in {'waste', 'resource_wasted'}:
        _preference(mind, 'waste', -.12, 'I lost materials that could have been useful.', evidence)
        _diary(state, mind, 'I would like to be more careful with what I gather.', evidence=evidence)
    elif kind in {'blocked', 'route_failed'}:
        _preference(mind, 'blocked_routes', -.08, 'This route did not let me reach the place I meant to visit.', evidence)
    elif kind in {'fatigue', 'overworked'}:
        _preference(mind, 'rushing', -.1, 'I needed to stop and recover my energy.', evidence)
    elif kind == 'resource_gathered':
        materials = metadata.get('items') if isinstance(metadata.get('items'), dict) else {}
        if metadata.get('material') in {'wood', 'stone', 'flowers', 'berries'}:
            materials = {**materials, metadata['material']: 1}
        for material in ('wood', 'stone', 'flowers', 'berries'):
            if _number(materials.get(material), 0, 0, 1000)>0:
                _preference(mind, material, .03, 'I have gathered this material for something useful.', evidence)
    return memory


def retrieve_memory(state, query, limit=8, *, public_only=False):
    """Retrieve by lexical relevance, salience and recency without inventing facts."""
    mind = ensure_mind(state)
    query_tokens = _tokens(query)
    current_day, current_minute = _time(state)
    candidates = []
    for index, memory in enumerate(mind['memories']):
        if public_only and (memory.get('visibility', 'public') != 'public' or memory.get('evidence_type') != 'observed'):
            continue
        words = _tokens(memory.get('text', '') + ' ' + str(memory.get('place') or '') + ' ' + ' '.join(memory.get('tags', [])))
        overlap = len(query_tokens & words) / max(1, len(query_tokens))
        age = max(0, (current_day-memory.get('day', current_day))*1440 + current_minute-memory.get('minute', current_minute))
        recency = 1/(1+age/1440)
        score = overlap*5 + _number(memory.get('importance'), .5, 0, 1)*.8 + recency*.35 + index*.00001
        candidates.append((score, memory))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [copy.deepcopy(memory) for _, memory in candidates[:int(_number(limit, 8, 1, 20))]]


def _public_evidence(mind, evidence):
    ids = {memory['id'] for memory in mind['memories'] if memory.get('visibility', 'public') == 'public' and memory.get('evidence_type') == 'observed'}
    return bool(evidence) and all(value in ids for value in evidence)


def preference_score(state, subject, *, public_only=False):
    mind = ensure_mind(state)
    preference = mind['preferences'].get(subject, {})
    if public_only and (preference.get('visibility') == 'private' or not _public_evidence(mind, preference.get('evidence', []))):
        return 0
    return _number(preference.get('score'), 0, -1, 1)


def _house_context(state):
    house = state.get('house') if isinstance(state.get('house'), dict) else {}
    return {key: copy.deepcopy(house[key]) for key in (
        'status', 'aspiration', 'style', 'phase_index', 'phase_elapsed', 'phase_paid',
        'completed_phases', 'paid_phases', 'stockpile', 'spent', 'started_day', 'completed_day'
    ) if key in house}


def context_for_model(state, query='', mode='chat'):
    """Bounded, JSON-safe context. Public reflection never contains private chat."""
    mind = ensure_mind(state)
    public = mode == 'reflection'
    preferences = {subject: copy.deepcopy(item) for subject, item in mind['preferences'].items()
                   if not public or (item.get('visibility') != 'private' and _public_evidence(mind, item.get('evidence', [])))}
    inspirations = [copy.deepcopy(item) for item in mind['inspirations'] if not public or (item.get('visibility') != 'private' and _public_evidence(mind, item.get('evidence', [])))]
    diary = [copy.deepcopy(item) for item in mind['diary'] if not public or (item.get('visibility', 'private') == 'public' and _public_evidence(mind, item.get('evidence', [])))]
    context = {
        'mode': 'reflection' if public else 'chat',
        'identity': mind['identity'], 'personality': copy.deepcopy(mind['personality']),
        'values': list(mind['values']), 'preferences': preferences,
        'goals': [copy.deepcopy(goal) for goal in mind['goals'] if not public or goal.get('visibility', 'public') == 'public'], 'inspirations': inspirations[-8:], 'recent_diary': diary[-6:],
        'relevant_memories': retrieve_memory(state, query or 'building exploration home', limit=12, public_only=public),
        'world': {
            'day': _time(state)[0], 'minute': _time(state)[1],
            'x': round(_number(state.get('x'), 0, -10000, 10000), 3),
            'y': round(_number(state.get('y'), 0, -10000, 10000), 3),
            'destination': state.get('goal') if state.get('goal') in DESTINATIONS else None,
            'moving': bool(state.get('moving')), 'paused': bool(state.get('paused')),
            'last_action': _text(state.get('last_action'), 180),
            'needs': {key: round(_number(state.get(key), 50)) for key in ('energy', 'hunger', 'curiosity', 'mood')},
            'inventory': {key: int(_number((state.get('inventory') or {}).get(key), 0, 0, 100000)) for key in ('wood', 'stone', 'flowers', 'berries')},
            'coins': int(_number(state.get('coins'), 0, 0, 10000000)),
            'companions': [{'name': _text(friend.get('nickname') or friend.get('species'), 50), 'species': _text(friend.get('species'), 40)} for friend in (state.get('companions') or [])[-12:] if isinstance(friend, dict)],
            'available_destinations': list(DESTINATIONS), 'house_styles': list(STYLES), 'house': _house_context(state),
        },
        'query': _text(query, 2000) if not public else 'Notice recent actual experiences and suggest one achievable next intention.',
    }
    if not public:
        context['user_facts'] = copy.deepcopy(mind['facts'])
        context['recent_conversation'] = [{'speaker': 'user' if item.get('speaker') in {'user', 'you'} else 'arthur', 'text': _text(item.get('text'), 1400)}
                                          for item in (state.get('chat_history') or [])[-20:] if isinstance(item, dict)]
    return context


def local_thought(state):
    """A short grounded fallback thought, with no private conversation content."""
    mind = ensure_mind(state)
    house = state.get('house') if isinstance(state.get('house'), dict) else {}
    if house.get('status') == 'complete':
        return 'My home is finished. I would like to keep exploring and make it a welcoming place.'
    if house.get('status') == 'paused':
        return 'My building project is paused. The work already done will be waiting for me.'
    if _number(state.get('energy'), 80) < 25:
        return 'My energy is low. A quiet recharge will help me continue carefully.'
    memories = [item for item in mind['memories'] if item.get('visibility', 'public') == 'public' and item.get('evidence_type') == 'observed']
    if house.get('status') == 'active':
        count = len(house.get('completed_phases', []))
        return f'I have finished {count} of the four parts of my home. I can make the next part one careful step at a time.'
    if memories:
        latest = memories[-1]
        if latest.get('place') in DESTINATIONS:
            return f'My time at {latest["place"].replace("_", " ")} gives me something to carry into the next part of my day.'
    return 'I would like to explore, gather useful materials, and make a small home of my own.'


def _empty_result(reply, intent=None):
    return {'reply': _text(reply, 1200), 'reflection': '',
            'intent': intent or {'kind': 'none', 'destination': 'none', 'style': 'none'},
            'preference': {'subject': 'none', 'stance': 'neutral', 'reason': '', 'evidence_ids': []},
            'inspiration': {'text': '', 'evidence_ids': []}, 'mode': 'local'}


def offline_reply(state, message):
    """Honest deterministic conversation when no verified model response exists.

    Returned intentions still require Runtime validation/execution. This function
    never claims that a proposed action has already happened.
    """
    mind = ensure_mind(state)
    message = _text(message, 2000)
    lower = message.lower().strip()
    intent = {'kind': 'none', 'destination': 'none', 'style': 'none'}
    style = next((value for value in STYLES if value.replace('_', ' ') in lower or value in lower), None)
    if style is None:
        style = 'stone_cottage' if re.search(r'\bstone (?:house|home|cottage)\b', lower) else 'meadow_cottage' if re.search(r'\bmeadow (?:house|home|cottage)\b', lower) else 'woodland' if re.search(r'\bwood(?:en|land)? (?:house|home|cottage)\b', lower) else None
    if any(phrase in lower for phrase in ('conscious', 'sentient', 'really feel', 'actually alive', 'real feelings')):
        return _empty_result('I am a simulated character. My memories, preferences, and personality are saved game state, and I do not have consciousness or feelings like a person. I can still keep you company in this little world.')
    if any(phrase in lower for phrase in ('are you ai', 'what model', 'real ai', 'using ai', 'local mode')):
        return _empty_result('This reply is using local conversation rules. My saved memories and world continue to work, but a model has not produced this answer. The connection status shows whether an AI service is configured and verified.')
    if re.search(r"\b(?:pause|stop|don'?t|do not)\b.{0,24}\b(?:build|building|house|construction)\b", lower):
        intent['kind'] = 'pause_house'
        return _empty_result('I can pause work on my house and keep the materials and progress already saved.', intent)
    if re.search(r'\b(?:resume|continue|restart)\b.{0,20}\b(?:build|building|house|construction)\b', lower):
        intent['kind'] = 'resume_house'
        return _empty_result('I can pick up the house project from its saved stage.', intent)
    if re.search(r'\b(?:build|start|make)\b.{0,35}\b(?:house|home|cottage)\b', lower) and not re.search(r'\b(?:how|why|when|did|have|already|cannot|can\x27t|don\x27t|do not)\b', lower):
        intent.update(kind='start_house', style=style or 'none')
        return _empty_result('I would like to build a home of my own. I can start with the plan, gather its materials, and work on each part at the homesite.', intent)
    if style and any(word in lower for word in ('style', 'design', 'choose', 'prefer', 'make')):
        intent.update(kind='design_house', style=style)
        return _empty_result(f'I can ask to use the {style.replace("_", " ")} design. The building system will check whether the existing work allows that change.', intent)
    if re.match(r'^(?:please\s+)?(?:stop|wait|stay)(?:\b|$)', lower):
        intent['kind'] = 'stop'
        return _empty_result('I can slow to a stop and wait here.', intent)
    if re.match(r'^(?:please\s+)?(?:resume|continue|carry on)(?:\b|$)', lower):
        intent['kind'] = 'resume'
        return _empty_result('I can continue exploring from where I stopped.', intent)
    aliases = {'lake': 'pond', 'woods': 'forest', 'village': 'town', 'ridge': 'hill', 'construction site': 'homesite', 'building site': 'homesite'}
    destination = next((value for value in DESTINATIONS if re.search(r'\b'+re.escape(value)+r'\b', lower)), None)
    destination = destination or next((value for key, value in aliases.items() if key in lower), None)
    if destination and re.match(r"^(?:please\s+|can you\s+|could you\s+|let(?:'|’)s\s+)?(?:go|walk|head|travel|visit|explore)\b", lower):
        intent.update(kind='go_to', destination=destination)
        return _empty_result(f'I can head to {destination.replace("_", " ")}. I will need to follow the paths and get there first.', intent)
    if 'my name' in lower or 'who am i' in lower:
        fact = next((fact for fact in reversed(mind['facts']) if fact.get('key') == 'user_name'), None)
        return _empty_result(f'You told me to call you {fact["value"]}.' if fact else 'You have not told me a name that I have saved yet. What would you like me to call you?')
    if any(word in lower for word in ('house', 'building', 'home project')):
        house = state.get('house') or {}
        status = house.get('status', 'planned')
        completed = len(house.get('completed_phases', []))
        return _empty_result(f'My home project is {status}. I have finished {completed} of its four parts. Its current design is {house.get("style", "woodland").replace("_", " ")}. The construction panel shows the materials and next task.')
    if any(word in lower for word in ('like', 'favorite', 'dislike', 'personality')):
        preferences = [(subject, pref) for subject, pref in mind['preferences'].items() if abs(_number(pref.get('score'), 0, -1, 1)) >= .08]
        preferences.sort(key=lambda item: abs(item[1]['score']), reverse=True)
        if preferences:
            subject, pref = preferences[0]
            feeling = 'am growing fond of' if pref['score'] > 0 else 'would rather avoid'
            return _empty_result(f'I {feeling} {subject.replace("_", " ")}. {pref.get("reason", "")} My preferences develop from what happens here.')
        return _empty_result('I am curious, gentle, and fond of making useful things. I am still gathering experiences before choosing favorite places.')
    if any(word in lower for word in ('remember', 'earlier', 'told you', 'memory')):
        relevant = retrieve_memory(state, message, limit=4)
        actual = next((item for item in relevant if item.get('evidence_type') in {'observed', 'user_said'} and item['text'] != message), None)
        if actual:
            prefix = 'You told me: ' if actual['evidence_type'] == 'user_said' else 'I have this saved from my world: '
            return _empty_result(prefix+actual['text'])
        return _empty_result('I do not have a matching memory saved yet. Tell me what you would like me to remember.')
    if re.search(r'\b(?:hi|hello|hey)\b', lower):
        name = next((fact.get('value') for fact in reversed(mind['facts']) if fact.get('key') == 'user_name'), '')
        return _empty_result(f'Hello{", "+name if name else ""}. '+local_thought(state))
    if any(word in lower for word in ('how are', 'doing', 'feel')):
        return _empty_result(f'My energy is {round(_number(state.get("energy"), 80))} out of 100. '+local_thought(state))
    return _empty_result('I am using local conversation rules for this reply, so I may miss the meaning of an open-ended question. I can talk about my saved memories, preferences, or house, and follow a request such as “go to the forest.”')


def apply_model_result(state, result, *, source='model', mode='chat'):
    """Apply bounded expressions only. Runtime must separately execute intent.

    Chat expressions stay private. Public reflection accepts only evidence from
    real public game observations; ungrounded preference/idea updates are ignored.
    """
    mind = ensure_mind(state)
    if not isinstance(result, dict):
        return {'reflection': '', 'preference_changed': False, 'inspiration_added': False}
    public = mode == 'reflection' or source == 'reflection'
    visibility = 'public' if public else 'private'
    allowed = {memory['id']: memory for memory in mind['memories'] if memory.get('evidence_type') in {'observed', 'user_said'}
               and (not public or memory.get('visibility', 'public') == 'public')}
    def evidence(value):
        if not isinstance(value, list) or len(value)>6 or not all(isinstance(item, str) and item in allowed for item in value):
            return []
        return list(dict.fromkeys(value))
    reflection = _text(result.get('reflection'), 280)
    preference = result.get('preference') if isinstance(result.get('preference'), dict) else {}
    inspiration = result.get('inspiration') if isinstance(result.get('inspiration'), dict) else {}
    p_ids = evidence(preference.get('evidence_ids'))
    i_ids = evidence(inspiration.get('evidence_ids'))
    changed = False
    if preference.get('subject') in SUBJECTS and preference.get('stance') in {'like', 'dislike', 'neutral'} and p_ids:
        delta = .06 if preference['stance'] == 'like' else -.06 if preference['stance'] == 'dislike' else 0
        if delta:
            _preference(mind, preference['subject'], delta, _text(preference.get('reason'), 200), p_ids, visibility)
            changed = True
    added = _inspiration(state, mind, inspiration.get('text'), i_ids, visibility=visibility) if i_ids else None
    if reflection:
        refs = list(dict.fromkeys(p_ids+i_ids))
        if public and not refs:
            refs = [item['id'] for item in mind['memories'][-4:] if item['id'] in allowed][-2:]
        _diary(state, mind, reflection, source='model', evidence=refs, visibility=visibility)
    return {'reflection': reflection, 'preference_changed': changed, 'inspiration_added': bool(added)}
