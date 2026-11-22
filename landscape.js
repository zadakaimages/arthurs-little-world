/* A cached, layered landscape. World geometry comes from the server, so art and
 * collision describe the same place. No downloaded textures or game assets. */
const TAU = Math.PI * 2;
const clamp = (v,a,b)=>Math.max(a,Math.min(b,v));
function rng(seed=7){let s=(seed>>>0)||1;return ()=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)/4294967296;};}
function makeCanvas(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c;}
function ellipse(c,x,y,rx,ry,color,angle=0){c.fillStyle=color;c.beginPath();c.ellipse(x,y,rx,ry,angle,0,TAU);c.fill();}
function poly(c,pts,fill,stroke=null,width=1){c.beginPath();pts.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.closePath();if(fill){c.fillStyle=fill;c.fill();}if(stroke){c.strokeStyle=stroke;c.lineWidth=width;c.stroke();}}
function line(c,pts,color,width){c.beginPath();pts.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.lineJoin='round';c.lineCap='round';c.strokeStyle=color;c.lineWidth=width;c.stroke();}
function gradientBlob(c,x,y,rx,ry,inner,outer){c.save();c.translate(x,y);c.scale(rx,ry);const g=c.createRadialGradient(0,0,0,0,0,1);g.addColorStop(0,inner);g.addColorStop(1,outer);ellipse(c,0,0,1,1,g);c.restore();}
function tint(hex,amount){const raw=parseInt(String(hex).replace('#',''),16);return `rgb(${clamp((raw>>16)+amount,0,255)},${clamp(((raw>>8)&255)+amount,0,255)},${clamp((raw&255)+amount,0,255)})`;}
const PALETTE={grass:'#6d9855',forest:'#527750',grove:'#628954',hill:'#9da56b',town:'#b3a783',path:'#c3ac7f',sand:'#d4c28f',water:'#3b8190',bridge:'#9e8056',building:'#a59678',sanctuary:'#7b9e60',edge:'#426345'};

export class Landscape {
  constructor(world,{tileSize=40}={}){
    this.world=world;this.tileSize=tileSize;this.width=world.width;this.height=world.height;
    this._random=rng(84017);this.sprites=new Map();this.waterPoints=[];this.grassPoints=[];
    this.ground=makeCanvas(world.width*tileSize,world.height*tileSize);
    this._buildGround();this._buildObjects();
  }
  tile(x,y){return this.world.tiles[Math.floor(y)]?.[Math.floor(x)]||'edge';}
  _scale(points){return points.map(p=>[p[0]*this.tileSize,p[1]*this.tileSize]);}
  _buildGround(){
    const c=this.ground.getContext('2d'),T=this.tileSize,W=this.ground.width,H=this.ground.height,r=this._random;
    c.fillStyle='#789b59';c.fillRect(0,0,W,H);
    // Broad, irregular color fields give terrain volume without showing tile edges.
    gradientBlob(c,7*T,10*T,13*T,15*T,'#385b46','rgba(61,91,60,0)');
    gradientBlob(c,36*T,26*T,12*T,11*T,'#527d4b','rgba(75,111,61,0)');
    gradientBlob(c,16*T,19*T,13*T,10*T,'#98ad69','rgba(129,159,81,0)');
    gradientBlob(c,20*T,5*T,9*T,6*T,'#c5bd89','rgba(154,161,100,0)');
    gradientBlob(c,9*T,29*T,10*T,9*T,'#a5ae7b','rgba(154,161,100,0)');
    for(let i=0;i<13000;i++){
      const x=r()*W,y=r()*H,a=.025+r()*.075;
      ellipse(c,x,y,2+r()*11,1+r()*4,r()<.5?`rgba(33,66,37,${a})`:`rgba(212,224,147,${a})`,r()*.6);
    }
    // Hill contours: broad beds of weathered rock, overgrown at the top.
    const ridge=[ [14,4.8],[15.6,3.2],[18.3,2.6],[21.1,2.8],[23.7,4.0],[25,5.5],[23.9,7],[21.8,7.6],[18.8,7.8],[16,6.9] ];
    const ridgePix=this._scale(ridge);
    c.save();c.shadowColor='rgba(31,43,31,.24)';c.shadowBlur=12;c.shadowOffsetY=8;
    poly(c,ridgePix,'#8c9070');c.restore();
    poly(c,ridgePix.map(([x,y])=>[x,y-7]),'#b4b38a');
    line(c,this._scale([[15.1,5.8],[16.9,6.6],[19.6,7.1],[22.1,6.8],[23.9,6]]),'#7e8668',5);
    line(c,this._scale([[15.5,5.6],[17,6.3],[19.7,6.8],[22,6.5],[23.6,5.8]]),'rgba(225,217,165,.6)',2);
    gradientBlob(c,20*T,4.5*T,5*T,2.5*T,'#b6bd86','rgba(152,166,101,0)');
    // Watercourse is drawn with the exact shape used to build the collision map.
    const lake=this._scale(this.world.lake),river=this._scale(this.world.river);
    line(c,river,'#416851',T*2.1);line(c,river,'#a8ad78',T*1.85);line(c,river,'#d1c391',T*1.53);
    poly(c,lake,'#d0c092','#50714f',T*2.1);poly(c,lake,'#d7c794','#d7c794',T*1.7);
    line(c,river,'#3f8b91',T*1.3);line(c,river,'#447f85',T*.78);
    const g=c.createLinearGradient(28*T,3*T,38*T,13*T);g.addColorStop(0,'#386e7e');g.addColorStop(.5,'#518e95');g.addColorStop(1,'#65a59c');
    poly(c,lake,g,'#96c0aa',3);
    // A broad sandy beach blends into the meadow, with reed and grass margins.
    gradientBlob(c,34.8*T,14*T,4*T,2.8*T,'#d6c696','rgba(200,190,131,0)');
    // Repaint the lake above the beach blend to retain clean shoreline.
    poly(c,lake,g,'#a8c8af',1.5);
    c.save();poly(c,lake);c.clip();
    gradientBlob(c,33.8*T,7*T,5*T,4*T,'rgba(22,63,88,.48)','rgba(38,98,112,0)');
    for(let i=0;i<90;i++){const x=(29+r()*10)*T,y=(4+r()*10)*T;ellipse(c,x,y,5+r()*23,.45,'rgba(215,238,215,.14)');}
    c.restore();
    // Village square and connecting trails are continuous strokes, not tile blocks.
    const square=this._scale([[5,24.5],[8.4,23.8],[12.4,26],[13.2,28.3],[10.2,29.2],[5.6,28.1]]);
    poly(c,square,'#b2aa8b');
    // Paint each layer across the entire network before the next layer. At
    // junctions this produces one continuous trail, without overlapping caps.
    c.lineCap='round';c.lineJoin='round';
    for(const layer of [{color:'rgba(50,74,41,.13)',extra:.28,mul:1},{color:'#b5a17a',extra:.08,mul:1},{color:'#c5b186',extra:0,mul:1}]){
      for(const road of this.world.roads){
        line(c,this._scale(road.points),layer.color,(road.width*layer.mul+layer.extra)*T);
      }
    }
    // Sparse small stones, fallen leaves, grass and meadow flowers.
    for(let i=0;i<12000;i++){
      const x=r()*W,y=r()*H,t=this.tile(x/T,y/T);
      if(['water','edge','building','bridge'].includes(t))continue;
      if(t==='path'||t==='town'||t==='sand'){
        if(r()<.35){ellipse(c,x,y,1+r()*2.8,.6+r(),r()<.5?'rgba(93,82,62,.19)':'rgba(237,219,177,.6)',r());}
      }else{
        const len=2+r()*4;
        line(c,[[x-1,y+len],[x,y],[x+1.4,y+len*.7]],r()<.5?'rgba(40,78,41,.25)':'rgba(168,193,102,.42)',.7);
        if(t==='grass'&&r()<.035){
          line(c,[[x,y+4],[x+1,y]],'#6d8c4f',.8);
          ellipse(c,x+1,y,1.8,1.4,r()<.5?'#e3cca0':'#d8b6bc');
        }
      }
    }
    // Sanctuary ground and feeding patches.
    const penG=c.createLinearGradient(23*T,18*T,27*T,22*T);penG.addColorStop(0,'#8eae6f');penG.addColorStop(1,'#74955a');
    c.fillStyle=penG;c.fillRect(23*T,18*T,5*T,4*T);
    for(let i=0;i<280;i++){const x=(23+r()*5)*T,y=(18+r()*4)*T;ellipse(c,x,y,1.5+r()*4,.7,'rgba(39,77,38,.12)');}
    ellipse(c,26.4*T,20.3*T,15,8,'#9d8e62');ellipse(c,26.4*T,20.3*T,12,6,'#78a7a4');
    ellipse(c,23.6*T,20.7*T,12,7,'#b9a365');
    // Cast shadows live on the ground cache so they never occlude characters.
    c.save();
    for(const o of this.world.objects){
      const px=(o.x+.5)*T,py=(o.y+.7)*T;
      if(o.kind==='tree'||o.kind==='pine'){
        ellipse(c,px+T*.38,py+T*.3,T*.65*o.size,T*.34*o.size,'rgba(28,52,38,.18)',.35);
        ellipse(c,px+T*.2,py+T*.13,T*.4,T*.2,'rgba(27,49,33,.13)',.35);
      }else if(o.kind==='rock')ellipse(c,px+7,py+3,T*.34,T*.13,'rgba(40,53,40,.22)');
    }
    for(const b of this.world.buildings){const x=b.x*T,y=b.y*T,w=b.w*T,h=b.h*T;poly(c,[[x,y+h],[x+w,y+h],[x+w+24,y+h+18],[x+12,y+h+18]],'rgba(39,46,35,.23)');}
    if(this.world.build_plot){
      const p=this.world.build_plot,x=p.x*T,y=p.y*T,w=p.w*T,h=p.h*T;
      poly(c,[[x-4,y+5],[x+w-3,y-3],[x+w+5,y+h-4],[x+2,y+h+3]],'#a69d75');
      for(let i=0;i<170;i++){const px=x+r()*w,py=y+r()*h;ellipse(c,px,py,1+r()*2,.7,r()<.5?'rgba(88,80,56,.18)':'rgba(223,208,163,.25)');}
    }
    c.restore();
    for(let i=0;i<160;i++){const x=r()*W,y=r()*H;if(this.tile(x/T,y/T)==='water')this.waterPoints.push({x,y,seed:r()*TAU,width:8+r()*18});}
    for(let i=0;i<110;i++){const x=r()*W,y=r()*H;if(['grass','grove','forest'].includes(this.tile(x/T,y/T)))this.grassPoints.push({x,y,seed:r()*TAU});}
    this._buildMapCache();
  }
  _buildObjects(){
    const T=this.tileSize;
    this.objects=this.world.objects.map(o=>({...o,depth:o.y+.72,worldX:o.x+.5,worldY:o.y+.72}));
    this.objects.push(...this.world.buildings.map(b=>({...b,kind:'building',depth:b.y+b.h+.03,worldX:b.x+b.w/2,worldY:b.y+b.h})));
    this.objects.push(...this.world.fences.map(f=>({...f,kind:'fence',depth:f.y+.73,worldX:f.x+.5,worldY:f.y+.72})));
    this.objects.push({kind:'sign',x:25,y:16,worldX:25.3,worldY:16.8,depth:16.8,label:'SANCTUARY'});
    this.objects.push({kind:'sign',x:6,y:25,worldX:6.5,worldY:25.9,depth:25.9,label:'ALDER VILLAGE'});
    this.objects.push({kind:'well',x:6,y:26,worldX:6.3,worldY:26.8,depth:26.8});
    this.objects.push({kind:'bridge',x:39,y:23,worldX:40,worldY:24,depth:23});
    for(const o of this.objects){
      if(['tree','pine','rock','bush','reeds'].includes(o.kind))this._sprite(o);
    }
  }
  _sprite(o){
    const key=o.kind+':'+(o.seed%6),T=this.tileSize;if(this.sprites.has(key))return this.sprites.get(key);
    const tree=o.kind==='tree'||o.kind==='pine',w=tree?T*3:T*1.5,h=tree?T*3.4:T*1.6;
    const im=makeCanvas(Math.ceil(w),Math.ceil(h)),c=im.getContext('2d'),r=rng(o.seed+71),cx=w/2,base=h-6;
    if(tree){
      // Flaring roots, lit bark and fine branches support a full, irregular canopy.
      poly(c,[[cx-5,base],[cx-3,base-T*1.3],[cx+2,base-T*1.7],[cx+5,base-T*.4],[cx+10,base+1],[cx+3,base-1]],'#665340');
      line(c,[[cx,base-2],[cx-1,base-T*.9],[cx+2,base-T*1.7]],'#a18960',2);
      line(c,[[cx-1,base-T*.6],[cx-16,base-T*1.2]],'#685741',3);
      line(c,[[cx+1,base-T*.8],[cx+19,base-T*1.6]],'#685741',3);
      if(o.kind==='pine'){
        for(let i=0;i<5;i++){
          const y=base-T*(.75+i*.35),half=T*(.7-i*.09);
          poly(c,[[cx-half,y],[cx-T*.14,y-T*.58],[cx,y-T*.78],[cx+half*.9,y-3],[cx+half*.55,y+6],[cx-half*.5,y+7]],i%2?'#3b654b':'#315b43');
          line(c,[[cx-half*.75,y-3],[cx,y-T*.63],[cx+half*.5,y-8]],'#628063',1.5);
        }
      }else{
        const cy=base-T*1.65,clusters=[];
        for(let i=0;i<16;i++){const a=r()*TAU,rr=Math.sqrt(r());clusters.push([cx+Math.cos(a)*T*.72*rr,cy+Math.sin(a)*T*.56*rr,T*(.3+r()*.28)]);}
        for(const [x,y,radius] of clusters){
          const g=c.createRadialGradient(x-radius*.35,y-radius*.45,1,x,y,radius);g.addColorStop(0,'#739460');g.addColorStop(.45,'#527c4b');g.addColorStop(1,'#2c563d');ellipse(c,x,y,radius,radius*.88,g);
        }
        for(let i=0;i<260;i++){
          const a=r()*TAU,rr=Math.sqrt(r()),x=cx+Math.cos(a)*T*.93*rr,y=cy+Math.sin(a)*T*.72*rr;
          const color=(x-cx+y-cy)<-T*.25?'rgba(164,186,105,.34)':'rgba(44,85,49,.24)';
          ellipse(c,x,y,1.3+r()*3,.7+r()*1.7,color,r()*TAU);
        }
      }
    }else if(o.kind==='rock'){
      const pts=[[cx-17,base-3],[cx-19,base-17],[cx-9,base-29],[cx+9,base-31],[cx+21,base-14],[cx+16,base-2]];
      poly(c,pts,'#858c83','#616b65',1);
      poly(c,[[cx-19,base-17],[cx-9,base-29],[cx+9,base-31],[cx+2,base-14],[cx-8,base-12]],'#b3b4a1');
      poly(c,[[cx+2,base-14],[cx+9,base-31],[cx+21,base-14],[cx+16,base-2]],'#737e77');
      line(c,[[cx-9,base-29],[cx-5,base-21],[cx+2,base-14],[cx-1,base-5]],'#6e7870',1);
      ellipse(c,cx-8,base-4,8,3,'#6f8d60');
    }else if(o.kind==='bush'){
      for(let i=0;i<7;i++){const x=cx+(r()-.5)*T*.6,y=base-6-r()*T*.45,rr=7+r()*6;const g=c.createLinearGradient(x,y-rr,x,y+rr);g.addColorStop(0,'#95a96b');g.addColorStop(1,'#426743');ellipse(c,x,y,rr,rr*.7,g);}
      for(let i=0;i<5;i++)ellipse(c,cx+(r()-.5)*18,base-12-r()*14,1.7,1.5,'#b87864');
    }else if(o.kind==='reeds'){
      for(let i=0;i<12;i++){const x=cx+(r()-.5)*T*.6,top=base-(.2+r()*.55)*T;line(c,[[x,base],[x+(r()-.5)*8,top]],'#637b4d',1);if(i%3===0)line(c,[[x,top],[x-.4,top-5]],'#876e49',2.4);}
    }
    const value={image:im,anchorX:w/2,anchorY:base};this.sprites.set(key,value);return value;
  }
  drawGround(c,camera,vw,vh,timeMs,state){
    const T=this.tileSize,px=camera.x*T,py=camera.y*T;
    c.fillStyle='#405e42';c.fillRect(0,0,vw,vh);
    const sx=clamp(px,0,this.ground.width),sy=clamp(py,0,this.ground.height),sw=Math.min(vw,this.ground.width-sx),sh=Math.min(vh,this.ground.height-sy);
    if(sw>0&&sh>0)c.drawImage(this.ground,sx,sy,sw,sh,sx-px,sy-py,sw,sh);
    // Tiny ripples and reed movement are the only animated ground details.
    const seconds=timeMs*.001;c.save();
    for(const p of this.waterPoints){const x=p.x-px,y=p.y-py;if(x<-30||y<-5||x>vw+30||y>vh+5)continue;const phase=(seconds*.32+p.seed)%TAU,alpha=.08+.11*(.5+.5*Math.sin(phase));c.strokeStyle=`rgba(212,234,215,${alpha})`;c.lineWidth=.8;c.beginPath();c.ellipse(x+Math.sin(seconds*.2+p.seed)*3,y,p.width*(.75+Math.sin(phase)*.12),1.3,0,0,Math.PI);c.stroke();}
    for(const p of this.grassPoints){const x=p.x-px,y=p.y-py;if(x<0||y<0||x>vw||y>vh)continue;const sway=Math.sin(seconds*1.3+p.seed)*1.8;line(c,[[x,y+5],[x+sway,y-2]],'rgba(65,95,43,.28)',1);}
    c.restore();
  }
  objectsForDepth(camera,vw,vh,timeMs,state={}){
    const T=this.tileSize,items=[],offsetX=camera.x*T,offsetY=camera.y*T;
    const drawObject=o=>{
      const x=o.worldX*T-offsetX,y=o.worldY*T-offsetY;
      return {depth:o.depth,draw:c=>this._drawObject(c,o,x,y,timeMs)};
    };
    for(const o of this.objects){const x=o.worldX*T-offsetX,y=o.worldY*T-offsetY;if(x<-T*3||x>vw+T*3||y<-T||y>vh+T*4)continue;items.push(drawObject(o));}
    for(const b of state.structures||[]){
      if(!Number.isFinite(b.x)||!Number.isFinite(b.y))continue;
      const p=this.world.build_plot;if(p&&b.x>=p.x&&b.x<p.x+p.w&&b.y>=p.y&&b.y<p.y+p.h)continue;
      const o={kind:'crafted',buildKind:b.kind,worldX:b.x+.5,worldY:b.y+.7,depth:b.y+.7};items.push(drawObject(o));
    }
    if(this.world.build_plot){const p=this.world.build_plot;items.push(drawObject({...p,kind:'construction',house:state.construction||{},worldX:p.x+p.w/2,worldY:p.y+p.h,depth:p.y+p.h+.03}));}
    return items;
  }
  _drawObject(c,o,x,y,timeMs){
    const T=this.tileSize;
    c.save();
    if(['tree','pine','rock','bush','reeds'].includes(o.kind)){
      const s=this._sprite(o),size=o.size||1;
      c.translate(x,y);if(['tree','pine','reeds'].includes(o.kind))c.rotate(Math.sin(timeMs*.0006+(o.seed%13))*.008);
      c.drawImage(s.image,-s.anchorX*size,-s.anchorY*size,s.image.width*size,s.image.height*size);
    }else if(o.kind==='building')this._drawBuilding(c,o,x,y);
    else if(o.kind==='construction')this._drawConstruction(c,o,x,y,timeMs);
    else if(o.kind==='fence'){
      const v=o.axis==='vertical';
      if(v){line(c,[[x,y-T*.43],[x,y+T*.43]],'#7a6344',5);line(c,[[x-1,y-T*.43-8],[x-1,y+T*.43-8]],'#ad946a',3);}
      else{line(c,[[x-T*.45,y-6],[x+T*.45,y-6]],'#927951',4);line(c,[[x-T*.45,y-13],[x+T*.45,y-13]],'#b39d74',3);}
      c.fillStyle='#a18a61';c.fillRect(x-3,y-23,6,26);poly(c,[[x-3,y-23],[x,y-27],[x+3,y-23]],'#c6b085');line(c,[[x-2,y-21],[x-2,y]],'#d1bb90',1);
    }else if(o.kind==='sign'){
      c.fillStyle='#796143';c.fillRect(x-2,y-30,4,32);c.fillStyle='#9d8053';c.fillRect(x-24,y-31,48,15);c.strokeStyle='#d8bd84';c.lineWidth=1;c.strokeRect(x-23,y-30,46,13);c.fillStyle='#f2e0b8';c.font='600 6px system-ui';c.textAlign='center';c.fillText(o.label,x,y-21);c.textAlign='left';
    }else if(o.kind==='well'){
      ellipse(c,x,y-5,16,9,'#7d8273');ellipse(c,x,y-8,13,7,'#bab9a1');ellipse(c,x,y-9,9,4,'#335c63');line(c,[[x-13,y],[x-13,y-35]],'#795e3f',3);line(c,[[x+13,y],[x+13,y-35]],'#795e3f',3);poly(c,[[x-22,y-34],[x,y-47],[x+22,y-34]],'#9d7156');line(c,[[x,y-34],[x,y-13]],'#9a8b68',1);
    }else if(o.kind==='bridge'){
      c.save();c.translate(x,y);
      poly(c,[[-T*1.95,-T*.1],[T*1.95,-T*.1],[T*1.95,-T*.92],[-T*1.95,-T*.92]],'#8d7653');
      for(let i=-7;i<=7;i++){const xx=i*T*.25;line(c,[[xx,-T*.12],[xx,-T*.89]],i%2?'#b59b6e':'#a88c61',T*.2);}
      line(c,[[-T*1.94,-T*.18],[T*1.94,-T*.18]],'#d1bb8b',2);line(c,[[-T*1.94,-T*.84],[T*1.94,-T*.84]],'#d1bb8b',2);c.restore();
    }else if(o.kind==='crafted'){
      if(o.buildKind==='flower_garden'){
        poly(c,[[x-17,y],[x+17,y],[x+17,y-18],[x-17,y-18]],'#7d694b','#b09565',2);
        for(let i=0;i<6;i++){const xx=x-12+i*5;line(c,[[xx,y-3],[xx,y-15-(i%2)*4]],'#6c8e54',1);ellipse(c,xx,y-16-(i%2)*4,3,2.7,i%2?'#dab6be':'#ead69c');}
      }else if(o.buildKind==='rest_bench'){
        line(c,[[x-14,y],[x-14,y-15]],'#72553c',3);line(c,[[x+14,y],[x+14,y-15]],'#72553c',3);poly(c,[[x-20,y-15],[x+20,y-15],[x+20,y-23],[x-20,y-23]],'#b19766','#7d6543',1);line(c,[[x-19,y-30],[x+19,y-30]],'#a98b5a',7);
      }else{
        poly(c,[[x-9,y],[x+9,y],[x+11,y-18],[x+4,y-26],[x-8,y-22]],'#8f988a','#687266',1);line(c,[[x-5,y-16],[x+5,y-16]],'#d3d7b7',2);
      }
    }
    c.restore();
  }
  _drawBuilding(c,o,x,y){
    const T=this.tileSize,w=o.w*T,h=o.h*T,left=x-w/2,top=y-h;
    const home=o.kind==='home'||o.name?.includes('Arthur'),market=o.name?.includes('market');
    const finish=o.finish??1,palette=o.palette;
    // Foundation, plaster/wood facade, pitched roof with a lit roof plane.
    c.fillStyle='#746e58';c.fillRect(left-3,y-10,w+6,12);
    const wall=c.createLinearGradient(left,top,left,y);wall.addColorStop(0,palette?tint(palette.wall,16):home?'#c3bca0':'#d0c2a2');wall.addColorStop(1,palette?palette.wall:home?'#a69c7f':'#b0a58c');
    c.fillStyle=wall;c.fillRect(left,top+T*.55,w,h-T*.55);
    c.fillStyle='#81795f';c.fillRect(left+w-9,top+T*.55,9,h-T*.55);
    for(let yy=top+T*.8;yy<y-12;yy+=9)line(c,[[left+3,yy],[left+w-10,yy]],'rgba(101,87,59,.14)',1);
    const roofBase=top+T*.75,roofPeak=top-T*.65;
    poly(c,[[left-T*.2,roofBase],[left+w/2,roofPeak],[left+w+T*.2,roofBase]],o.roof||'#7c8069','#5e6251',2);
    poly(c,[[left-T*.2,roofBase],[left+w/2,roofPeak],[left+w*.52,roofBase]],palette?tint(palette.roof,20):home?'#829483':'#b58b6a');
    for(let i=1;i<7;i++){const yy=roofPeak+(roofBase-roofPeak)*i/7,spread=(w/2+T*.2)*i/7;line(c,[[x-spread,yy],[x+spread,yy]],'rgba(46,53,42,.19)',1.2);}
    line(c,[[left-T*.2,roofBase],[left+w+T*.2,roofBase]],'#5b6050',4);
    // Door, windows and awning are aligned to a visible approach on the shared map.
    const doorX=market?left+T*.45:x;
    c.fillStyle='#665b45';c.fillRect(doorX-10,y-35,20,35);
    if(finish>=.2){c.fillStyle=palette?.trim||'#7c6b4c';c.fillRect(doorX-8,y-33,16,31);ellipse(c,doorX+5,y-15,1.2,1.2,'#e2c777');}
    for(const wx of [left+T*.48,left+w-T*.48]){
      if(Math.abs(wx-doorX)<T*.5)continue;
      c.fillStyle='#7b7761';c.fillRect(wx-10,y-45,20,24);
      if(finish>=.45){c.fillStyle='#c8d8c3';c.fillRect(wx-8,y-43,16,20);line(c,[[wx,y-42],[wx,y-23]],'#8a846b',2);line(c,[[wx-8,y-33],[wx+8,y-33]],'#8a846b',2);}
      if(finish>=.8){c.fillStyle='#796c50';c.fillRect(wx-12,y-22,24,4);ellipse(c,wx-5,y-20,4,3,'#658654');ellipse(c,wx+4,y-20,4,3,'#a0b16b');if(o.style==='meadow_cottage'){ellipse(c,wx-5,y-23,2,2,'#d6a1ab');ellipse(c,wx+4,y-23,2,2,'#ebd390');}}
    }
    const chimneyX=left+w*.76;if(finish>=.7){c.fillStyle='#8a8673';c.fillRect(chimneyX,roofPeak+8,12,29);c.fillStyle='#b3ad95';c.fillRect(chimneyX-1,roofPeak+6,14,5);}
    if(market){
      const ay=y-40,ax=left-3,aw=w+6;poly(c,[[ax,ay],[ax+aw,ay],[ax+aw+6,ay+17],[ax-6,ay+17]],'#c6b68d','#947b54',1);
      for(let i=0;i<8;i++){const xx=ax+i*aw/8;c.fillStyle=i%2?'#e1d4b0':'#6f8d7d';c.fillRect(xx,ay,aw/8,17);}
      c.fillStyle='#9e7e52';c.fillRect(left+T*.9,y-15,T*1.8,12);
      for(let i=0;i<6;i++)ellipse(c,left+T+.28*T*i,y-16,3,3,i%2?'#9caf62':'#c18964');
      c.fillStyle='#e8d8ad';c.font='bold 9px system-ui';c.textAlign='center';c.fillText('MARKET',x,roofBase-10);c.textAlign='left';
    }else if(home&&finish>=.9){
      c.fillStyle='#88734b';c.fillRect(doorX-16,y-42,32,8);c.fillStyle='#e4d1a6';c.font='6px system-ui';c.textAlign='center';c.fillText('ARTHUR',doorX,y-36);c.textAlign='left';
    }
  }
  _drawConstruction(c,o,x,y,timeMs){
    const T=this.tileSize,w=o.w*T,h=o.h*T,left=x-w/2,top=y-h,house=o.house||{};
    const index=house.status==='complete'?4:clamp(Number(house.phase_index)||0,0,4),progress=clamp(Number(house.progress)||0,0,1);
    const palette=(house.styles||[]).find(s=>s.id===house.style)?.palette||({woodland:{wall:'#a77d58',roof:'#637b60',trim:'#dbc19b',stone:'#92958b'},stone_cottage:{wall:'#b3b3a1',roof:'#647887',trim:'#78644c',stone:'#979c94'},meadow_cottage:{wall:'#d3bd94',roof:'#ab765c',trim:'#f0dcae',stone:'#a2a194'}}[house.style]||{wall:'#a77d58',roof:'#637b60',trim:'#dbc19b',stone:'#92958b'});
    if(index>=3){
      poly(c,[[left,y],[left+w,y],[left+w+19,y+13],[left+8,y+13]],'rgba(39,46,35,.22)');
      this._drawBuilding(c,{...o,name:"Arthur's house",kind:'home',roof:palette.roof,palette,style:house.style,finish:index===4?1:progress},x,y);
      if(index===4)return;
    }else{
      // String lines and corner pegs make the reserved plot visible from day one.
      const corners=[[left+3,top+9],[left+w-3,top+9],[left+w-3,y-4],[left+3,y-4]];
      line(c,[...corners,corners[0]],'rgba(233,217,163,.85)',1);
      for(const [px,py] of corners){line(c,[[px,py+3],[px,py-10]],'#8a704d',3);ellipse(c,px,py-10,2.5,1.5,'#c2a97d');}
      const foundation=index>0?1:(house.phase_paid?progress:0);
      if(foundation>0){
        c.save();c.beginPath();c.rect(left,top,w,h*foundation);c.clip();
        poly(c,[[left+2,top+12],[left+w-2,top+12],[left+w-2,y-3],[left+2,y-3]],'#a7a68f');
        for(let row=0;row<3;row++)for(let i=0;i<7;i++){
          const bx=left+i*w/7+(row%2)*5,by=y-4-row*7;c.fillStyle=row%2?palette.stone:tint(palette.stone,12);c.fillRect(bx,by-6,w/7-1,6);
        }
        c.restore();
      }
      if(index>=1){
        const f=index>1?1:progress,roofBase=top+T*.75,roofPeak=top-T*.65;
        const posts=[left+7,left+w-7,left+w*.33,left+w*.67];
        for(let i=0;i<posts.length;i++)if(f>i*.14){line(c,[[posts[i],y-9],[posts[i],roofBase]],'#8b6846',5);line(c,[[posts[i]-1,y-9],[posts[i]-1,roofBase]],'#c5a374',1.5);}
        if(f>.35){line(c,[[left+3,roofBase],[left+w-3,roofBase]],'#a48155',5);line(c,[[left+6,y-25],[left+w-6,y-25]],'#98764e',3);}
        if(f>.55){line(c,[[left+6,y-10],[left+w*.33,roofBase]],'#b18b5c',3);line(c,[[left+w-6,y-10],[left+w*.67,roofBase]],'#b18b5c',3);}
        if(f>.72){line(c,[[left-T*.18,roofBase],[x,roofPeak],[left+w+T*.18,roofBase]],'#aa8556',4);line(c,[[x,roofPeak],[x,roofBase]],'#b59667',3);}
        if(index===2){
          const wall=c.createLinearGradient(left,roofBase,left,y);wall.addColorStop(0,tint(palette.wall,16));wall.addColorStop(1,palette.wall);c.fillStyle=wall;c.fillRect(left,roofBase,w,y-roofBase-7);
          for(let yy=roofBase+6;yy<y-10;yy+=9)line(c,[[left+2,yy],[left+w-2,yy]],'rgba(87,69,44,.2)',1);
          c.fillStyle='#665b45';c.fillRect(x-10,y-35,20,31);c.fillRect(left+10,y-45,18,22);c.fillRect(left+w-28,y-45,18,22);
          c.save();c.beginPath();c.rect(left-T*.25,roofPeak-3,(w+T*.5)*progress,roofBase-roofPeak+8);c.clip();
          poly(c,[[left-T*.2,roofBase],[x,roofPeak],[left+w+T*.2,roofBase]],palette.roof,'#56634e',2);
          poly(c,[[left-T*.2,roofBase],[x,roofPeak],[x,roofBase]],tint(palette.roof,20));
          for(let i=1;i<7;i++){const yy=roofPeak+(roofBase-roofPeak)*i/7,spread=(w/2+T*.2)*i/7;line(c,[[x-spread,yy],[x+spread,yy]],'rgba(39,49,38,.25)',1.1);}
          c.restore();
        }
      }
    }
    // Supplies sit inside the reserved footprint, clear of Arthur's approach.
    const stock=house.stockpile||{},logs=Math.min(4,Math.ceil((stock.wood||0)/3)),stones=Math.min(4,Math.ceil((stock.stone||0)/3));
    for(let i=0;i<logs;i++){const ly=y-8-i*4;line(c,[[left+6,ly],[left+24,ly]],'#846343',5);ellipse(c,left+24,ly,2.7,2.4,'#c1a478');}
    for(let i=0;i<stones;i++)ellipse(c,left+w-11-(i%2)*7,y-5-Math.floor(i/2)*5,5,3,palette.stone);
    if(house.working){
      const beat=Math.sin(timeMs*.01);c.save();c.translate(x+T*.6,y-20);c.rotate(-.5+Math.max(0,beat)*.85);line(c,[[0,0],[0,-12]],'#a78353',2.5);line(c,[[-5,-12],[5,-12]],'#8d958c',4);c.restore();
      for(let i=0;i<3;i++){const p=(timeMs*.0015+i*.33)%1;ellipse(c,x+T*.55+i*3,y-5-p*9,1.4,1.2,`rgba(229,212,166,${(1-p)*.35})`);}
    }
  }
  drawAtmosphere(c,camera,vw,vh,timeMs,state={}){
    const minute=Number.isFinite(state.minute)?state.minute:600,h=minute/60;
    let night=0;if(h>=19)night=clamp((h-19)/2,0,1);else if(h<6)night=1;else if(h<8)night=1-(h-6)/2;
    c.save();
    if(night>0){c.fillStyle=`rgba(20,35,61,${night*.38})`;c.fillRect(0,0,vw,vh);}
    if((h>6&&h<9)||(h>17&&h<20)){const warmth=1-Math.min(1,Math.abs(h-(h<12?7.5:18.5))/1.5);c.fillStyle=`rgba(238,177,92,${warmth*.08})`;c.fillRect(0,0,vw,vh);}
    const vignette=c.createRadialGradient(vw*.5,vh*.42,Math.min(vw,vh)*.22,vw*.5,vh*.45,Math.max(vw,vh)*.73);vignette.addColorStop(0,'rgba(17,36,25,0)');vignette.addColorStop(1,'rgba(17,36,25,.17)');c.fillStyle=vignette;c.fillRect(0,0,vw,vh);
    // Light, slow cloud shade adds depth without hiding the world.
    if(night<.5){const drift=Math.sin(timeMs*.000025)*vw*.3;const cg=c.createLinearGradient(-vw*.2+drift,0,vw*.8+drift,vh);cg.addColorStop(0,'rgba(51,67,58,0)');cg.addColorStop(.48,'rgba(51,67,58,.045)');cg.addColorStop(.7,'rgba(51,67,58,0)');c.fillStyle=cg;c.fillRect(0,0,vw,vh);}
    c.restore();
  }
  _buildMapCache(){
    const m=makeCanvas(660,510),c=m.getContext('2d');
    c.drawImage(this.ground,0,0,m.width,m.height);
    const sx=m.width/this.width,sy=m.height/this.height;
    for(const o of this.world.objects){if(!['tree','pine'].includes(o.kind))continue;ellipse(c,(o.x+.5)*sx,(o.y+.5)*sy,3,3.8,'rgba(37,74,44,.65)');}
    for(const b of this.world.buildings){c.fillStyle=b.roof;c.fillRect(b.x*sx,b.y*sy,b.w*sx,b.h*sy);}
    this.mapCache=m;
  }
  drawMap(c,state={}){
    const W=c.canvas.width,H=c.canvas.height;c.clearRect(0,0,W,H);c.drawImage(this.mapCache,0,0,W,H);
    const sx=W/this.width,sy=H/this.height;c.save();c.font=`600 ${Math.max(9,W/60)}px system-ui`;c.textBaseline='middle';
    const labels={home:'Shelter',pond:'Lake shore',forest:'Woods',meadow:'Meadow',hill:'Ridge',grove:'Grove',town:'Village',market:'Market',beach:'Beach',homesite:state.construction?.status==='complete'?"Arthur's house":'House plot'};
    if(this.world.build_plot){const p=this.world.build_plot,h=state.construction||{};c.fillStyle=h.status==='complete'?'#6b7f5d':h.phase_index>=2?'#a28a67':'#c3b08b';c.fillRect(p.x*sx,p.y*sy,p.w*sx,p.h*sy);c.strokeStyle='#677450';c.lineWidth=1;c.strokeRect(p.x*sx,p.y*sy,p.w*sx,p.h*sy);}
    for(const [name,p] of Object.entries(this.world.sites)){
      const x=(p[0]+.5)*sx,y=(p[1]+.5)*sy,txt=labels[name]||name,w=c.measureText(txt).width;
      const offset=name==='town'?-14:12;ellipse(c,x,y,3,3,'#f4df9f');c.fillStyle='rgba(29,48,38,.81)';c.fillRect(x-w/2-5,y+offset-7,w+10,14);c.fillStyle='#f4ecd8';c.textAlign='center';c.fillText(txt,x,y+offset);
    }
    for(const cr of state.wild_creatures||[]){ellipse(c,(cr.x+.5)*sx,(cr.y+.5)*sy,1.7,1.7,'#d9c7a4');}
    if(Number.isFinite(state.x)&&Number.isFinite(state.y)){const x=(state.x+.5)*sx,y=(state.y+.5)*sy;ellipse(c,x,y,6,6,'rgba(255,234,150,.24)');ellipse(c,x,y,3.5,3.5,'#ffe28b');c.strokeStyle='#675630';c.lineWidth=1;c.beginPath();c.arc(x,y,3.5,0,TAU);c.stroke();}
    c.restore();
  }
}
