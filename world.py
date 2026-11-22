"""Shared terrain and collision map for Arthur's Little World.

Integer coordinates denote tile centers. Art and navigation consume the same map.
"""
import math
from collections import deque

W, H = 44, 34
HOME = (21, 16)
SANCTUARY = (24, 19)
SITES = {'pond': (29,12), 'meadow': (14,13), 'grove': (35,23),
         'hill': (19,6), 'home': HOME, 'town': (7,26), 'market': (9,27),
         'forest': (7,9), 'beach': (35,15), 'homesite': (16,22)}
BUILD_PLOT = {'id':'arthur_house','x':15,'y':19,'w':3,'h':3,
              'work_point':[16,22],'door':[16,21],
              'name':"Arthur’s future home",'shelter':list(HOME)}

# Points below are in drawing coordinates (tile corners, with centers at n + .5).
ROADS = [
    {'points': [[21.5,16.5],[18.5,16.5],[16.5,15.5],[14.5,13.5]], 'width':1.35},
    {'points': [[14.5,13.5],[12.5,12.5],[10.5,10.5],[7.5,9.5]], 'width':1.1},
    {'points': [[18.5,16.5],[18.5,12.5],[19.5,9.5],[19.5,6.5]], 'width':1.2},
    {'points': [[21.5,16.5],[24.5,15.5],[27.5,13.5],[29.5,12.5]], 'width':1.35},
    {'points': [[27.5,13.5],[29.5,15.5],[32.5,15.5],[35.5,15.5]], 'width':1.25},
    {'points': [[14.5,13.5],[12.5,17.5],[10.5,20.5],[7.5,23.5],[7.5,26.5]], 'width':1.5},
    {'points': [[7.5,26.5],[9.5,27.5],[12.5,27.5]], 'width':1.7},
    {'points': [[24.5,15.5],[24.5,17.5],[24.5,19.5]], 'width':1.05},
    {'points': [[28.5,21.5],[31.5,22.5],[35.5,23.5]], 'width':1.25},
    {'points': [[28.5,21.5],[29.5,17.5],[29.5,15.5]], 'width':1.2},
    {'points': [[35.5,23.5],[39.5,23.5],[42.5,23.5]], 'width':1.3},
    {'points': [[18.5,16.5],[18.5,19.5],[18.5,22.5],[16.5,22.5]], 'width':1.1},
]
LAKE = []
for i in range(48):
    a = i * math.tau / 48
    wobble = 1 + .055*math.sin(a*3+.6) + .035*math.cos(a*5)
    LAKE.append([33.7 + math.cos(a)*4.5*wobble,
                 8.6 + math.sin(a)*4.25*wobble])
RIVER = [[37.0,11.5],[38.5,14.5],[39.3,17.5],[40.2,20.5],
         [39.6,23.5],[40.0,26.5],[41.5,29.5],[42,34.5]]
BUILDINGS = [
    {'kind':'home','x':20,'y':13,'w':3,'h':3,'roof':'#6b7970','name':"Arthur’s shelter"},
    {'kind':'house','x':3,'y':23,'w':3,'h':2,'roof':'#ab785a','name':'Village house'},
    {'kind':'market','x':9,'y':24,'w':3,'h':3,'roof':'#9a6255','name':'Meadow market'},
    {'kind':'house','x':2,'y':28,'w':3,'h':2,'roof':'#687c88','name':'Village house'},
    {'kind':'workshop','x':12,'y':29,'w':3,'h':2,'roof':'#8c7967','name':'Workshop'},
]


def _smooth_points(points,steps=10):
    """Sample the same quadratic curves used by the renderer for collision."""
    sampled=[points[0]]
    start=points[0]
    for i in range(1,len(points)):
        control=points[i] if i<len(points)-1 else points[-2]
        end=[(points[i][0]+points[i+1][0])/2,(points[i][1]+points[i+1][1])/2] if i<len(points)-1 else points[-1]
        for k in range(1,steps+1):
            t=k/steps;s=1-t
            sampled.append([s*s*start[0]+2*s*t*control[0]+t*t*end[0],
                            s*s*start[1]+2*s*t*control[1]+t*t*end[1]])
        start=end
    return sampled


# Art and passability follow the same smooth watercourse and winding trails.
RIVER=_smooth_points(RIVER)
for road in ROADS:road['points']=_smooth_points(road['points'])


def _distance_segment(x,y,a,b):
    vx,vy=b[0]-a[0],b[1]-a[1]
    q=max(0,min(1,((x-a[0])*vx+(y-a[1])*vy)/(vx*vx+vy*vy or 1)))
    return math.hypot(x-a[0]-vx*q,y-a[1]-vy*q)


def _line_distance(x,y,points):
    return min(_distance_segment(x,y,a,b) for a,b in zip(points,points[1:]))


def _inside(x,y,poly):
    odd=False
    j=len(poly)-1
    for i,p in enumerate(poly):
        q=poly[j]
        if (p[1]>y)!=(q[1]>y) and x<(q[0]-p[0])*(y-p[1])/(q[1]-p[1])+p[0]: odd=not odd
        j=i
    return odd


def _noise(x,y):
    v=(x*374761393+y*668265263+1447)&0xffffffff
    v=((v^(v>>13))*1274126177)&0xffffffff
    return ((v^(v>>16))&0xffffffff)/4294967295


def _base(x,y):
    px,py=x+.5,y+.5
    if not (0<x<W-1 and 0<y<H-1):return 'edge'
    if 38<=x<=41 and y==23:return 'bridge'
    if _inside(px,py,LAKE) or _line_distance(px,py,RIVER)<.65:return 'water'
    if min(math.hypot(px-a,py-b) for a,b in LAKE)<1.0 or (30<=x<=37 and 12<=y<=16):return 'sand'
    if 2<=x<=15 and 22<=y<=31:return 'town'
    if ((px-19.5)/6)**2+((py-5.5)/4.8)**2<1:return 'hill'
    if x<12 and y<17:return 'forest'
    if x>29 and y>18:return 'grove'
    return 'grass'


TILES=[[_base(x,y) for x in range(W)] for y in range(H)]
BLOCKED=[[t in ('edge','water') for t in row] for row in TILES]
ROAD_CLEAR=set()
for y in range(1,H-1):
    for x in range(1,W-1):
        for road in ROADS:
            if _line_distance(x+.5,y+.5,road['points']) < road['width']*.5+.48:
                ROAD_CLEAR.add((x,y))
                if TILES[y][x] not in ('water','bridge'):
                    TILES[y][x]='path'; BLOCKED[y][x]=False

# Keep destinations and their approaches open. This also preserves v1.6 anchors.
for sx,sy in SITES.values():
    for y in range(sy-1,sy+2):
        for x in range(sx-1,sx+2):
            if 0<x<W-1 and 0<y<H-1 and TILES[y][x]!='water':
                ROAD_CLEAR.add((x,y)); BLOCKED[y][x]=False

# Sanctuary enclosure: collision fence and visible fence share exact tile footprints.
FENCES=[]
for y in range(17,23):
    for x in range(22,29):
        if x in (22,28) or y in (17,22):
            if (x,y) in ((24,17),(28,21)):continue
            FENCES.append({'x':x,'y':y,'axis':'horizontal' if y in (17,22) else 'vertical'})
            BLOCKED[y][x]=True
for y in range(18,22):
    for x in range(23,28):
        TILES[y][x]='sanctuary'; BLOCKED[y][x]=False;ROAD_CLEAR.add((x,y))
for b in BUILDINGS:
    for y in range(b['y'],b['y']+b['h']):
        for x in range(b['x'],b['x']+b['w']):
            TILES[y][x]='building';BLOCKED[y][x]=True

# Reserve the whole house from the blueprint onward: no actor can stand inside
# a future wall, and completion never changes collision beneath a visitor.
for y in range(BUILD_PLOT['y'],BUILD_PLOT['y']+BUILD_PLOT['h']):
    for x in range(BUILD_PLOT['x'],BUILD_PLOT['x']+BUILD_PLOT['w']):
        TILES[y][x]='build_plot';BLOCKED[y][x]=True

OBJECTS=[]
for y in range(1,H-1):
    for x in range(1,W-1):
        if BLOCKED[y][x] or (x,y) in ROAD_CLEAR:continue
        base=TILES[y][x]
        near_site=any(math.hypot(x-sx,y-sy)<2.2 for sx,sy in SITES.values())
        in_pen=22<=x<=28 and 17<=y<=22
        if near_site or in_pen:continue
        r=_noise(x,y)
        chance=.32 if base=='forest' else .19 if base=='grove' else .08 if base=='grass' else 0
        # Tree trunks occupy their source cell; crowns extend above for occlusion.
        if r<chance:
            kind='pine' if base=='forest' and _noise(x+44,y)<.25 else 'tree'
            OBJECTS.append({'kind':kind,'x':x,'y':y,'size':.82+_noise(x+80,y)*.4,'seed':int(r*1000000)})
            BLOCKED[y][x]=True
        elif base=='hill' and r<.18:
            OBJECTS.append({'kind':'rock','x':x,'y':y,'size':.65+r*2,'seed':int(r*1000000)})
            BLOCKED[y][x]=True
        elif base in ('grass','grove') and .45<r<.48:
            OBJECTS.append({'kind':'bush','x':x,'y':y,'size':1,'seed':int(r*1000000)})

# Water-edge reeds; they are decoration, not a second collision system.
for y in range(1,H-1):
    for x in range(1,W-1):
        if TILES[y][x] in ('sand','grass','grove') and any(TILES[y+dy][x+dx]=='water' for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))) and _noise(x+9,y)>.43:
            OBJECTS.append({'kind':'reeds','x':x,'y':y,'size':1,'seed':int(_noise(x,y)*100000)})


def terrain(x,y):
    if not isinstance(x,(int,float)) or not isinstance(y,(int,float)):return 'edge'
    if not math.isfinite(x) or not math.isfinite(y):return 'edge'
    x,y=int(math.floor(x+.5)),int(math.floor(y+.5))
    return TILES[y][x] if 0<=x<W and 0<=y<H else 'edge'


def walkable(x,y):
    if not isinstance(x,(int,float)) or not isinstance(y,(int,float)):return False
    if not math.isfinite(x) or not math.isfinite(y):return False
    x,y=int(math.floor(x+.5)),int(math.floor(y+.5))
    return 0<=x<W and 0<=y<H and not BLOCKED[y][x]


def public_world():
    return {'version':18,'width':W,'height':H,'tiles':TILES,'blocked':BLOCKED,
            'sites':SITES,'home':HOME,'sanctuary':SANCTUARY,'build_plot':BUILD_PLOT,
            'roads':ROADS,'lake':LAKE,'river':RIVER,'buildings':BUILDINGS,
            'objects':OBJECTS,'fences':FENCES,
            'regions':[{'name':'Whispering Woods','x':6,'y':4},
                       {'name':'Sunlit Ridge','x':19,'y':3},
                       {'name':'Glasswater Lake','x':34,'y':7},
                       {'name':'Wildflower Meadow','x':14,'y':19},
                       {'name':'Alder Village','x':7,'y':30},
                       {'name':'Bramble Grove','x':34,'y':28}]}


if __name__=='__main__':
    q=deque([HOME]);seen={HOME}
    while q:
        x,y=q.popleft()
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            v=x+dx,y+dy
            if v not in seen and walkable(*v):seen.add(v);q.append(v)
    for name,p in SITES.items():
        assert p in seen,(name,p,'unreachable')
    print('All landmarks connected;',len(seen),'walkable tiles;',len(OBJECTS),'objects')
