/* Arthur: the original painted head and chest, with a ground-contact limb rig.
 * The atlas has uneven cell bounds; source regions below intentionally exclude
 * neighboring glows. No animation phase is advanced without actual travel.
 */
const TAU = Math.PI * 2;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const mix = (a, b, t) => a + (b - a) * t;
const smooth = t => t * t * (3 - 2 * t);
const ellipse = (c,x,y,rx,ry,color,rot=0) => { c.fillStyle=color; c.beginPath(); c.ellipse(x,y,Math.max(.01,rx),Math.max(.01,ry),rot,0,TAU); c.fill(); };
function rod(c, a, b, width, dim=false) {
  c.lineCap='round'; c.strokeStyle=dim?'#3a4250':'#3d4652'; c.lineWidth=width+2;
  c.beginPath(); c.moveTo(a.x,a.y); c.lineTo(b.x,b.y); c.stroke();
  const g=c.createLinearGradient(a.x-3,a.y,b.x+4,b.y);
  g.addColorStop(0,dim?'#687882':'#9ba9af'); g.addColorStop(.45,dim?'#a7b0b1':'#cbd5d1'); g.addColorStop(1,dim?'#5a6478':'#778497');
  c.strokeStyle=g; c.lineWidth=width; c.stroke();
}
function joint(c,x,y,r,dim=false){
  ellipse(c,x,y,r+1,r+1,'#343d4e');
  const g=c.createRadialGradient(x-r*.35,y-r*.4,.1,x,y,r);
  g.addColorStop(0,dim?'#8588b8':'#b2addc');g.addColorStop(.45,dim?'#5c6796':'#707bb4');g.addColorStop(1,'#3c456e');
  ellipse(c,x,y,r,r,g);ellipse(c,x-r*.35,y-r*.35,r*.25,r*.18,'#c3cadc');
}
function knee(hip,ankle,bend,scale){
  const l1=15.5*scale,l2=16.5*scale,dx=ankle.x-hip.x,dy=ankle.y-hip.y;
  const d=clamp(Math.hypot(dx,dy),.001,l1+l2-.01),nx=dx/Math.max(.001,Math.hypot(dx,dy)),ny=dy/Math.max(.001,Math.hypot(dx,dy));
  const a=(l1*l1-l2*l2+d*d)/(2*d),h=Math.sqrt(Math.max(0,l1*l1-a*a));
  return {x:hip.x+nx*a-ny*h*bend,y:hip.y+ny*a+nx*h*bend};
}
const HEADS={
  down:{row:0,cx:74.5,cy:81,rx:18,ry:16,stem:[75,68,72,56,78,47,88,57],tip:[88.5,58],eyes:[[69,80,3.7,6],[80.5,80,3.7,6]],chest:[65,96,20,26]},
  left:{row:1,cx:64.5,cy:70,rx:18,ry:17,stem:[61,57,59,43,71,36,80,48],tip:[80,49],eyes:[[54,70,3.6,6]],chest:[57,86,15,25]},
  right:{row:2,cx:75,cy:73,rx:17,ry:17,stem:[75,60,79,45,62,43,59,55],tip:[59.5,55],eyes:[[83,73,3.6,6]],chest:[68,88,15,25]},
  up:{row:3,cx:76.5,cy:68,rx:18,ry:17,stem:[76,55,80,44,69,39,65,49],tip:[65,50],eyes:[],chest:[67,85,20,27]},
};

export class ArthurRenderer {
  constructor(image){this.image=image;this.motion=null;this.metrics={};}
  reset(){this.motion=null;}
  _update(actor,tile,now){
    const center={x:(actor.x+.5)*tile,y:(actor.y+.5)*tile+tile*.12};
    let m=this.motion;
    if(!m || Math.hypot(center.x-m.center.x,center.y-m.center.y)>tile*3 || now-m.now>1000){
      m=this.motion={center,now,phase:0,heading:actor.heading??Math.PI/2,facing:actor.facing||'down',oldFacing:actor.facing||'down',turnAt:now,walk:0,lastDistance:actor.distance,
        feet:[-1,1].map(side=>({x:center.x+side*tile*.12,y:center.y,side,lift:0,swing:false,phase:side===-1?0:.5,start:null,end:null}))};
      return m;
    }
    const dt=clamp((now-m.now)/1000,.001,.1),dx=center.x-m.center.x,dy=center.y-m.center.y,ds=Math.hypot(dx,dy);
    const moving=ds>.005 && (actor.moving!==false || (actor.speed||0)>.04);
    const v=Math.hypot(actor.vx||0,actor.vy||0);
    let hx=v>.02?actor.vx/v:Math.cos(actor.heading??m.heading),hy=v>.02?actor.vy/v:Math.sin(actor.heading??m.heading);
    if(ds>.08){hx=dx/ds;hy=dy/ds;}
    const angle=Math.atan2(hy,hx),delta=Math.atan2(Math.sin(angle-m.heading),Math.cos(angle-m.heading));
    if(moving)m.heading+=delta*Math.min(1,dt*10);
    hx=Math.cos(m.heading);hy=Math.sin(m.heading);
    const stride=tile*(.44-.10*Math.abs(hy)),cycle=stride*2,duty=.55;
    const oldPhase=m.phase;
    if(moving)m.phase+=ds/cycle;
    if(moving)m.idleSince=null;
    else if(m.idleSince==null){m.idleSince=now;for(const foot of m.feet)foot.settle=null;}
    m.walk=mix(m.walk,moving?1:0,Math.min(1,dt*9));
    const face=actor.facing || (Math.abs(hx)>Math.abs(hy)?(hx>0?'right':'left'):(hy>0?'down':'up'));
    if(face!==m.facing){m.oldFacing=m.facing;m.facing=face;m.turnAt=now;}
    const lateral={x:Math.abs(hy)>.4?1:.25,y:Math.abs(hy)>.4?0:.28};
    for(let i=0;i<2;i++){
      const foot=m.feet[i],phase=((m.phase+i*.5)%1+1)%1,prev=((oldPhase+i*.5)%1+1)%1;
      const neutral={x:center.x+foot.side*tile*.12*lateral.x,y:center.y+foot.side*tile*.12*lateral.y};
      if(!moving){
        // A brief final step brings the feet under the hips. Planted feet never slide.
        if(!foot.settle && (foot.swing || Math.hypot(foot.x-neutral.x,foot.y-neutral.y)>tile*.025)){
          foot.settle={start:{x:foot.x,y:foot.y,lift:foot.lift},end:neutral,at:now+i*80};
        }
        if(foot.settle){
          const u=clamp((now-foot.settle.at)/180,0,1),q=smooth(u),s=foot.settle;
          foot.x=mix(s.start.x,s.end.x,q);foot.y=mix(s.start.y,s.end.y,q);
          foot.lift=s.start.lift*(1-q)+Math.sin(Math.PI*u)*2.8*tile/40;
          foot.swing=u<1;if(u>=1){foot.lift=0;foot.swing=false;}
        }else{foot.lift=0;foot.swing=false;}
      }else{
        foot.settle=null;
        if(phase>=duty && (!foot.swing || prev<duty)){
          foot.swing=true;foot.start={x:foot.x,y:foot.y};
          const lead=cycle*(1-duty)+stride*duty;
          foot.end={x:neutral.x+hx*lead,y:neutral.y+hy*lead};
        }
        if(foot.swing && phase<duty){
          if(foot.end){foot.x=foot.end.x;foot.y=foot.end.y;}foot.lift=0;foot.swing=false;
        }
        if(foot.swing){
          const u=clamp((phase-duty)/(1-duty),0,1),q=smooth(u);
          // Re-target only the airborne foot when the route turns.
          const end={x:neutral.x+hx*stride*duty,y:neutral.y+hy*stride*duty};
          if(Math.abs(delta)>.2){foot.end.x=mix(foot.end.x,end.x,dt*4);foot.end.y=mix(foot.end.y,end.y,dt*4);}
          foot.x=mix(foot.start.x,foot.end.x,q);foot.y=mix(foot.start.y,foot.end.y,q);
          foot.lift=Math.sin(Math.PI*u)*(4.2+1.2*Math.abs(hx))*tile/40;
        }else{
          foot.lift=0; // The world anchor is deliberately unchanged throughout stance.
        }
        if(Math.hypot(foot.x-neutral.x,foot.y-neutral.y)>tile*.9){foot.x=neutral.x;foot.y=neutral.y;foot.swing=false;foot.lift=0;}
      }
      foot.phase=phase;
    }
    m.center=center;m.now=now;m.lastDistance=actor.distance;
    this.metrics={phase:m.phase,speed:actor.speed||0,feet:m.feet.map(f=>({x:f.x,y:f.y,lift:f.lift,planted:!f.swing})),moving};
    return m;
  }
  _head(c,face,x,y,scale,now,tilt){
    const h=HEADS[face],ry=h.row*144;
    c.save();c.translate(x,y);c.rotate(tilt);c.scale(scale,scale);c.translate(-h.cx,-h.cy);
    // Union of the head silhouette and curved antenna: omit the clipped neighbor's halo.
    c.save();c.beginPath();c.ellipse(h.cx,h.cy,h.rx,h.ry,0,0,TAU);c.rect(h.cx-5,h.cy+10,10,9);
    c.moveTo(h.tip[0]+5,h.tip[1]);c.arc(h.tip[0],h.tip[1],5,0,TAU);c.clip();
    c.drawImage(this.image,0,ry,96,144,0,0,96,144);c.restore();
    // A separate curved antenna trace keeps the thin metal visible without an asset halo.
    c.strokeStyle='#596370';c.lineWidth=2.6;c.lineCap='round';c.beginPath();c.moveTo(...h.stem.slice(0,2));c.bezierCurveTo(...h.stem.slice(2));c.stroke();
    c.strokeStyle='#c0c8be';c.lineWidth=1;c.stroke();
    const pulse=.85+.15*Math.sin(now*.0024);ellipse(c,h.tip[0],h.tip[1],3.2,3.2,`rgba(255,225,100,${pulse})`);ellipse(c,h.tip[0]-.7,h.tip[1]-.7,1.4,1.4,'#fff4bc');
    const blinkPhase=(now+1100)%5200;
    if(blinkPhase>5050 && blinkPhase<5180){
      for(const [ex,ey,rx,eyr] of h.eyes){ellipse(c,ex,ey,rx+.7,eyr+.6,'#85877c');c.strokeStyle='#363b3c';c.lineWidth=1.1;c.beginPath();c.moveTo(ex-rx,ey+1);c.quadraticCurveTo(ex,ey+2,ex+rx,ey+1);c.stroke();}
    }
    c.restore();
  }
  draw(c,actor,camera,tile=40,now=performance.now()){
    if(!Number.isFinite(actor.x)||!Number.isFinite(actor.y))return;
    const m=this._update(actor,tile,now),scale=tile/40;
    const px=m.center.x-camera.x*tile,py=m.center.y-camera.y*tile;
    const phase=m.phase*TAU,hx=Math.cos(m.heading),hy=Math.sin(m.heading),sideView=Math.abs(hx)>.64;
    const bodyBob=-Math.cos(phase*2)*.65*m.walk*scale;
    const bodySway=Math.sin(phase)*.55*m.walk*scale;
    const body={x:px+bodySway,y:py+bodyBob};
    const face=(now-m.turnAt<65)?m.oldFacing:m.facing;
    c.save();
    ellipse(c,px,py+2*scale,14*scale,4*scale,'rgba(15,31,25,.25)');
    const footDraws=m.feet.map((f,i)=>({f,i,ankle:{x:f.x-camera.x*tile,y:f.y-camera.y*tile-f.lift},hip:{x:body.x+(sideView?2:5.2)*f.side*scale,y:body.y-30*scale+(sideView?f.side*1.1*scale:0)}}));
    footDraws.sort((a,b)=>a.ankle.y-b.ankle.y);
    for(const {f,ankle,hip,i} of footDraws){
      const dim=(sideView && (hx>0?i===0:i===1)),bend=hx>0?-1:1;
      // Front/back knee flexion points into depth, so its side-to-side projection is small.
      // Solving the same flat IK as the side view would produce a bow-legged squat.
      const k=sideView?knee(hip,ankle,bend,scale):{x:mix(hip.x,ankle.x,.5)+f.side*1.1*scale,y:mix(hip.y,ankle.y,.52)-f.lift*.12};
      ellipse(c,ankle.x, f.y-camera.y*tile+2*scale,5.5*scale,1.7*scale,'rgba(14,29,25,.12)');
      rod(c,hip,k,3.3*scale,dim);rod(c,k,ankle,3*scale,dim);joint(c,k.x,k.y,2.8*scale,dim);joint(c,hip.x,hip.y,2.8*scale,dim);
      const heel=f.swing?Math.sin((f.phase-.55)/.45*Math.PI)*.12:0;
      ellipse(c,ankle.x+(sideView?hx*1.8*scale:0),ankle.y,sideView?6.2*scale:4.6*scale,2.6*scale,dim?'#637180':'#9ca7ab',heel*hx);
      ellipse(c,ankle.x+(sideView?hx*1.5*scale:0)-1*scale,ankle.y-.9*scale,sideView?3.6*scale:2.7*scale,.65*scale,'#d2d7d2',heel*hx);
    }
    const arms=[];
    for(const side of [-1,1]){
      const swing=Math.sin(phase+(side<0?0:Math.PI))*m.walk;
      const shoulder={x:body.x+(sideView?4:9)*side*scale,y:body.y-45*scale+(sideView?side*1.2*scale:0)};
      const elbow={x:shoulder.x+side*1.6*scale-hx*swing*4.5*scale,y:shoulder.y+8.8*scale-hy*swing*2.7*scale};
      const hand={x:elbow.x-hx*swing*3*scale+side*.3*scale,y:elbow.y+9.3*scale};
      arms.push({side,shoulder,elbow,hand,dim:sideView&&(hx>0?side<0:side>0)});
    }
    const arm=a=>{rod(c,a.shoulder,a.elbow,2.7*scale,a.dim);rod(c,a.elbow,a.hand,2.4*scale,a.dim);joint(c,a.shoulder.x,a.shoulder.y,3.1*scale,a.dim);joint(c,a.elbow.x,a.elbow.y,2.5*scale,a.dim);ellipse(c,a.hand.x,a.hand.y,2.9*scale,3.4*scale,a.dim?'#6c7b8a':'#c0c8c7');};
    arms.filter(a=>a.dim).forEach(arm);
    // Torso and neck keep the exact chest texture from the approved book-derived sprite.
    rod(c,{x:body.x,y:body.y-49*scale},{x:body.x,y:body.y-53*scale},4.4*scale);
    const torsoWidth=(sideView?12:17)*scale,tx=body.x-torsoWidth/2,ty=body.y-48*scale;
    const metal=c.createLinearGradient(tx,ty,tx+torsoWidth,ty);metal.addColorStop(0,'#697780');metal.addColorStop(.45,'#bcc8c7');metal.addColorStop(1,'#768293');
    ellipse(c,body.x,body.y-38*scale,torsoWidth/2,11*scale,'#414956');ellipse(c,body.x,body.y-38*scale,torsoWidth/2-1*scale,10*scale,metal);
    if(this.image?.complete && this.image.naturalWidth){const h=HEADS[face],[sx,sy,sw,sh]=h.chest;c.drawImage(this.image,sx,sy+h.row*144,sw,sh,tx,ty,torsoWidth,23*scale);}
    arms.filter(a=>!a.dim).forEach(arm);
    const tilt=Math.sin(phase)*.015*m.walk+Math.sin(now*.0007)*.012*(1-m.walk);
    if(this.image?.complete && this.image.naturalWidth)this._head(c,face,body.x,body.y-61*scale,scale*.91,now,tilt);
    else{
      ellipse(c,body.x,body.y-61*scale,15*scale,14*scale,'#b6c1c2');
      for(const side of [-1,1])ellipse(c,body.x+side*5*scale,body.y-60*scale,3*scale,5*scale,'#f8d86f');
      rod(c,{x:body.x,y:body.y-74*scale},{x:body.x+6*scale,y:body.y-80*scale},1.5*scale);ellipse(c,body.x+6*scale,body.y-80*scale,2.7*scale,2.7*scale,'#ffe181');
    }
    c.restore();
  }
}

const PALETTES={
  Mossbit:['#6b9970','#b6ca87','#384f3c'],Emberoo:['#c87548','#edbd76','#783b32'],Puddlepip:['#67a0b3','#b3d0c5','#335e72'],
  Thornlet:['#a180ab','#dcb7bd','#64516f'],Moonmote:['#b1b8d4','#efe8c4','#6b7298'],Pebblin:['#9b9e8e','#cecbb4','#59625b']
};
export class CreatureRenderer {
  draw(c,a,camera,tile=40,now=performance.now()){
    if(!Number.isFinite(a.x)||!Number.isFinite(a.y))return;
    const scale=tile/40,base=PALETTES[a.species]||PALETTES.Mossbit,evolved=a.form&&a.form!==a.species;
    const moving=a.moving??((a.speed||0)>.03),dir=(a.vx||0)<-.02?-1:(a.vx||0)>.02?1:(a.facing==='left'?-1:1);
    const t=now/1000,seed=typeof a.id==='number'?a.id:(a.species||'').length;
    const phase=(a.distance||0)*TAU/1.05,activity=a.behavior||a.activity||'',rest=/sleep|rest|nap/.test(activity);
    const bob=moving?Math.abs(Math.sin(phase))*1.2:Math.sin(t*1.8+seed)*.4;
    const x=(a.x+.5-camera.x)*tile,y=(a.y+.5-camera.y)*tile+tile*.12;
    c.save();c.translate(x,y);c.scale(scale*dir,scale);if(evolved)c.scale(1.13,1.13);
    ellipse(c,0,2,13,3.3,'rgba(16,35,27,.21)');
    const shade=(cx,cy,rx,ry,main=base[0])=>{const g=c.createRadialGradient(cx-rx*.3,cy-ry*.4,1,cx,cy,Math.max(rx,ry));g.addColorStop(0,base[1]);g.addColorStop(.45,main);g.addColorStop(1,base[2]);ellipse(c,cx,cy,rx,ry,g);};
    c.translate(0,-bob);const walk=moving?Math.sin(phase):0,blink=rest||((t+seed*.37)%5.1>4.96);
    const foot=(xx,yy,r=3)=>{ellipse(c,xx,yy,r,2,base[2]);ellipse(c,xx-.6,yy-.7,r*.6,.6,base[1]);};
    if(a.species==='Emberoo'){
      c.strokeStyle=base[2];c.lineWidth=5;c.lineCap='round';c.beginPath();c.moveTo(-8,-10);c.quadraticCurveTo(-20,-9,-18,-21+Math.sin(t*3)*2);c.stroke();
      shade(-18,-22+Math.sin(t*3)*2,3,6,'#d88c47');shade(0,-12,11,12);shade(1,-24,10,9);
      for(const s of [-1,1]){shade(s*6,-33,3,8);foot(s*6+walk*s*2,walk*s>0?-2:0,4);}
      shade(8,-22,5,3,base[1]);
    }else if(a.species==='Puddlepip'){
      c.strokeStyle=base[2];c.lineWidth=5;c.lineCap='round';c.beginPath();c.moveTo(-7,-9);c.quadraticCurveTo(-20,-8,-19,-16+Math.sin(t*4)*3);c.stroke();
      shade(0,-11,12,10);shade(4,-20,11,8);shade(13,-21,4,2,base[1]);
      for(const s of [-1,1]){shade(-3+s*8,-27,4,7);foot(s*7+walk*s*2,Math.min(0,walk*s)*2,5);}
    }else if(a.species==='Mossbit'){
      shade(0,-12,12,11);shade(1,-22,10,8);foot(-7+walk*2,-Math.max(0,walk)*2,4);foot(7-walk*2,Math.min(0,walk)*2,4);
      for(const s of [-1,1]){c.save();c.translate(s*6,-28);c.rotate(s*.2+Math.sin(t*1.8+seed)*.06);shade(0,-4,4,9,'#6e9b62');c.restore();}
      if(evolved){for(let i=0;i<5;i++)ellipse(c,Math.cos(i*TAU/5)*5,-36+Math.sin(i*TAU/5)*3,3,4,'#e3b5ae');ellipse(c,0,-36,2,2,'#f2d78f');}
    }else if(a.species==='Thornlet'){
      for(let i=0;i<7;i++){const angle=i*TAU/7+.1*Math.sin(t);shade(Math.cos(angle)*10,-19+Math.sin(angle)*10,5,7,base[1]);}
      shade(0,-15,11,12);shade(0,-22,9,7);foot(-6+walk*1.6,-Math.max(0,walk)*2,3);foot(6-walk*1.6,Math.min(0,walk)*2,3);
      if(evolved){shade(-13,-23,5,8,'#bd8fbe');shade(13,-23,5,8,'#bd8fbe');}
    }else if(a.species==='Moonmote'){
      c.translate(0,-3-Math.sin(t*2+seed)*2);
      for(const s of [-1,1]){c.save();c.translate(s*6,-18);c.rotate(s*(.3+Math.sin(t*5)*.16));shade(s*7,-3,10,6,base[1]);c.restore();}
      shade(0,-14,9,12);shade(0,-24,9,8);ellipse(c,0,-34,2.5,3,'#f3e6ae');foot(-4,-3,2);foot(4,-3,2);
      if(evolved){const g=c.createRadialGradient(0,-17,2,0,-17,23);g.addColorStop(0,'rgba(232,223,166,.12)');g.addColorStop(1,'rgba(232,223,166,0)');ellipse(c,0,-17,23,23,g);}
    }else{
      foot(-8+walk,-Math.max(0,walk),5);foot(8-walk,Math.min(0,walk),5);shade(0,-10,14,12);shade(-5,-23,8,7);shade(6,-25,8,8);shade(0,-18,10,8);
      c.strokeStyle='rgba(61,69,61,.5)';c.lineWidth=1;c.beginPath();c.moveTo(-10,-13);c.lineTo(-3,-15);c.lineTo(1,-9);c.moveTo(5,-27);c.lineTo(3,-20);c.stroke();
    }
    const ey=a.species==='Emberoo'?-25:a.species==='Puddlepip'?-22:a.species==='Pebblin'?-18:-23;
    for(const ex of [-3.5,4]){ellipse(c,ex,ey,2,blink?.55:2.5,'#273b37');if(!blink)ellipse(c,ex-.5,ey-.7,.65,.8,'#fff4df');}
    if(!rest){ellipse(c,1,ey+4,1.1,.65,base[2]);}
    if(rest){c.fillStyle='rgba(225,237,229,.7)';c.font='10px Georgia';c.fillText('z',10+Math.sin(t)*2,-37-(t%2)*3);}
    c.restore();
  }
}
