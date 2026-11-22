// Snapshots share one delayed clock. A network packet never restarts a tween.
const lerp=(a,b,t)=>a+(b-a)*t;
const numeric=(v,fallback=0)=>Number.isFinite(v)?v:fallback;
function angle(a,b,t){return a+Math.atan2(Math.sin(b-a),Math.cos(b-a))*t;}
export function interpolateActor(a,b,t){
  if(!a)return {...b};if(!b)return {...a};
  const out={...b};
  for(const k of ['x','y','vx','vy','speed','distance','sanctuary_x','sanctuary_y']){
    if(Number.isFinite(a[k])&&Number.isFinite(b[k]))out[k]=lerp(a[k],b[k],t);
  }
  out.heading=angle(numeric(a.heading),numeric(b.heading),t);
  const dx=numeric(b.x)-numeric(a.x),dy=numeric(b.y)-numeric(a.y);
  out.moving=Math.hypot(dx,dy)>.001&&numeric(out.speed)>.015;
  out.facing=t<.5?a.facing:b.facing;
  return out;
}
function entityKey(entity,index){return String(entity.id??entity.uid??`${entity.species}-${index}`);}
function interpolateList(a=[],b=[],t){
  const previous=new Map(a.map((e,i)=>[entityKey(e,i),e]));
  return b.map((e,i)=>interpolateActor(previous.get(entityKey(e,i)),e,t));
}
export class SnapshotBuffer{
  constructor({delay=280,capacity=20}={}){this.delay=delay;this.capacity=capacity;this.retiredRuns=new Set();this.reset();}
  reset(){this.frames=[];this.offset=null;this.runId=null;this.lastReceive=-Infinity;this.latestSequence=-1;}
  push(payload,receivedAt,rtt=0){
    const serverTime=numeric(payload.snapshot_ms,Date.now());
    if(this.retiredRuns.has(payload.run_id))return false;
    const restarted=this.runId!==null&&payload.run_id!==this.runId;
    const stale=receivedAt-this.lastReceive>1500;
    if(restarted){
      this.retiredRuns.add(this.runId);
      if(this.retiredRuns.size>8)this.retiredRuns.delete(this.retiredRuns.values().next().value);
      this.reset();
    }else if(payload.seq!==undefined&&payload.seq<=this.latestSequence)return false;
    else if(stale){this.frames=[];this.offset=null;}
    this.runId=payload.run_id;this.latestSequence=payload.seq??this.latestSequence+1;
    const estimate=receivedAt-serverTime-Math.min(Math.max(rtt,0)/2,150);
    if(this.offset===null)this.offset=estimate;
    else this.offset+=Math.max(-2,Math.min(2,(estimate-this.offset)*.04));
    this.lastReceive=receivedAt;
    this.frames.push({time:serverTime,state:payload.state});
    if(this.frames.length>this.capacity)this.frames.shift();
    return true;
  }
  sample(now){
    if(!this.frames.length)return null;
    const target=now-this.offset-this.delay;
    let left=this.frames[0],right=left;
    for(let i=1;i<this.frames.length;i++){
      right=this.frames[i];if(right.time>=target)break;left=right;
    }
    const range=right.time-left.time;
    const t=range>0?Math.max(0,Math.min(1,(target-left.time)/range)):1;
    const state=interpolateActor(left.state,right.state,t);
    state.wild_creatures=interpolateList(left.state.wild_creatures,right.state.wild_creatures,t);
    state.companions=interpolateList(left.state.companions,right.state.companions,t);
    if(target>right.time+40||target<left.time){
      state.speed=0;state.moving=false;
      for(const e of [...state.wild_creatures,...state.companions]){e.speed=0;e.moving=false;}
    }
    return state;
  }
}
export class FrameClock{
  constructor(fps=30){this.interval=1000/fps;this.reset();}
  reset(){this.schedule=null;this.previous=null;}
  tick(now){
    if(this.schedule===null){this.schedule=now;this.previous=now;return 1/30;}
    const elapsed=now-this.schedule;
    if(elapsed+.05<this.interval)return null;
    this.schedule+=Math.max(1,Math.floor((elapsed+.05)/this.interval))*this.interval;
    const dt=Math.min(.1,(now-this.previous)/1000);this.previous=now;return dt;
  }
}
