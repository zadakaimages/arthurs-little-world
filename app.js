import {Landscape} from './landscape.js';
import {ArthurRenderer,CreatureRenderer} from './character.js';
import {SnapshotBuffer,FrameClock} from './motion.js';

const $=id=>document.getElementById(id);
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const title=value=>String(value??'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const fmt=m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(Math.floor(m%60)).padStart(2,'0')}`;
const labels={home:'Home',meadow:'Meadow',pond:'Lake shore',forest:'Forest',hill:'Ridge',grove:'Grove',town:'Village',market:'Market',beach:'Beach',homesite:'House plot'};
const siteColors={home:'#b49a78',meadow:'#a3b877',pond:'#7da8ac',forest:'#547b60',hill:'#b5b084',grove:'#7f9764',town:'#bd9b78',market:'#b69b7a',beach:'#d0b78b',homesite:'#b6ab7d'};
const colors={Mossbit:'#84a06b',Emberoo:'#ca946d',Puddlepip:'#77a6ae',Thornlet:'#aa8fa6',Moonmote:'#9eabc6',Pebblin:'#9e9f8c'};
const canvas=$('world'),ctx=canvas.getContext('2d',{alpha:false});
const mapCanvas=$('fullmap'),mapCtx=mapCanvas.getContext('2d');
const buffer=new SnapshotBuffer(),frameClock=new FrameClock(30),T=40;
const arthurImage=new Image();
const camera={x:9.5,y:8.5};
let landscape=null,arthur=null,creatures=null,world=null,latest=null,visual=null;
let zoom=1,following=true,cameraReady=false,connected=false,busy=false;
let raf=0,pollTimer=0,polling=false,booting=false,initialized=false,lastUI=0,lastGood=0,lastMap=0;
let frameCount=0,fpsStart=0,fps=0,paintTime=0,maxPaintTime=0;
let viewerId='v'+Math.random().toString(36).slice(2),ownerToken='';
let chatSubmitting=false,chatSubmission=null,chatDeliveryError='',ownerUnlocking=false,accessRevision=0;
try{viewerId=sessionStorage.getItem('arthurViewerId')||viewerId;sessionStorage.setItem('arthurViewerId',viewerId);ownerToken=sessionStorage.getItem('arthurOwnerToken')||'';}catch{}

function setText(id,value){const el=$(id),s=String(value??'');if(el.textContent!==s)el.textContent=s;}
function setHTML(id,value){const el=$(id);if(el.dataset.lastHTML!==value){el.innerHTML=value;el.dataset.lastHTML=value;return true;}return false;}
function error(message){setText('error',message);}
function connection(ok,reason=''){
  connected=ok;$('status').className='status '+(ok?'online':'offline');
  setText('status',ok?'World is live':'Reconnecting');
  const overlay=$('connection');overlay.hidden=ok;overlay.classList.toggle('soft',!!latest);
  if(!ok){
    setText('connectionTitle',latest?'Connection paused · retrying':'Arthur’s world is waiting');
    setText('connectionHelp',reason||'Run python3 server.py in the game folder, then open http://localhost:8765.');
    $('retry').hidden=false;
  }
  if(latest)renderChat(latest.state);
  updatePermissions();
}
function updatePermissions(){
  const owner=!!latest?.owner_mode&&connected&&!busy;
  const thinking=latest?.state.chat_status?.status==='thinking'||chatSubmitting||!!chatSubmission?.awaiting;
  for(const button of document.querySelectorAll('#destinations button'))button.disabled=!owner;
  $('arthurPause').disabled=!owner;
  $('chatInput').disabled=!owner||thinking;$('chatSend').disabled=!owner||thinking;
  for(const button of document.querySelectorAll('#chatPrompts button'))button.disabled=!owner||thinking;
  $('chatRetry').disabled=!owner||thinking;
  const market=world?.sites.market;
  const near=!!market&&!!latest&&Math.hypot(latest.state.x-market[0],latest.state.y-market[1])<=3;
  for(const button of document.querySelectorAll('#shop button'))button.disabled=!owner||!near||(latest?.state.coins??0)<Number(button.dataset.price);
  setText('shopHelp',!latest?.owner_mode?'Viewers can watch Arthur’s travels. The owner can buy resources.':near?'Arthur is at the market. Choose a resource to buy.':'Arthur needs to visit the market before buying resources.');
  const house=latest?.state.construction;
  $('houseStart').disabled=!owner||!house||house.status!=='planned';
  $('housePause').disabled=!owner||house?.status!=='active';
  $('houseResume').disabled=!owner||house?.status!=='paused';
  $('houseDeposit').disabled=!owner||!house?.can_deposit||house?.status==='complete';
  $('houseStyle').disabled=!owner||!house?.can_change_style;
  $('houseVisit').disabled=!owner||!world?.sites.homesite;
  $('ownerUnlock').disabled=ownerUnlocking||!connected;
  $('ownerLock').disabled=ownerUnlocking;
}
function makeControls(){
  $('destinations').replaceChildren();
  $('stats').replaceChildren();
  for(const site of ['home','meadow','forest','pond','hill','beach','grove','town','market','homesite']){
    if(!world.sites[site])continue;
    const button=document.createElement('button');button.type='button';button.dataset.site=site;
    const dot=document.createElement('i');dot.style.setProperty('--dot',siteColors[site]);dot.setAttribute('aria-hidden','true');
    button.append(dot,document.createTextNode(labels[site]));button.disabled=true;
    button.addEventListener('click',()=>act('/api/suggest',{goal:site}));$('destinations').append(button);
  }
  $('shop').replaceChildren();
  const shop=latest?.shop||{wood:5,stone:7,flowers:3,berries:4};
  for(const [item,priceInfo] of Object.entries(shop)){
    const price=typeof priceInfo==='number'?priceInfo:priceInfo.price;
    const button=document.createElement('button');button.type='button';button.dataset.price=price;button.disabled=true;
    const name=document.createElement('b');name.textContent=title(item);
    const amount=document.createElement('span');amount.textContent=`${price} coins`;
    button.append(name,amount);button.addEventListener('click',()=>act('/api/buy',{item}));$('shop').append(button);
  }
  for(const [key,label,color] of [['energy','Energy','#a7b87d'],['hunger','Hunger','#d3b782'],['curiosity','Curiosity','#9caaa9'],['mood','Mood','#b4b28c']]){
    const stat=document.createElement('div');stat.className='stat';
    stat.innerHTML=`<div class="stat-label"><span>${label}</span><b id="stat-${key}">—</b></div><div class="bar"><i id="bar-${key}" style="--bar:${color};width:0%"></i></div>`;
    $('stats').append(stat);
  }
}
async function jsonFetch(path,options={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
  try{
    const response=await fetch(path,{cache:'no-store',...options,headers:{...(ownerToken?{'X-Arthur-Owner':ownerToken}:{}),...(options.headers||{})},signal:controller.signal});
    const data=await response.json();if(!response.ok)throw new Error(data.error||`Request failed (${response.status})`);return data;
  }finally{clearTimeout(timer);}
}
async function fetchState(){
  const before=performance.now(),accessAtStart=accessRevision;
  const data=await jsonFetch('/api/state',{headers:{'X-Arthur-Viewer':viewerId}});
  const now=performance.now();
  if(accessAtStart!==accessRevision)return null;
  if(!data.state||!Number.isFinite(data.state.x)||!Number.isFinite(data.state.y))throw new Error('The server returned an invalid world state.');
  const restarted=buffer.runId!==null&&buffer.runId!==data.run_id;
  if(buffer.push(data,now,now-before)){
    latest=data;
    if(restarted||now-lastGood>1500){cameraReady=false;arthur?.reset();}
  }
  lastGood=now;if(!connected)connection(true);
  if(now-lastUI>450){renderUI();lastUI=now;}
  return data;
}
async function poll(){
  if(polling||document.hidden||!world)return;
  polling=true;const started=performance.now();
  try{await fetchState();}catch{connection(false);}
  finally{polling=false;clearTimeout(pollTimer);if(!document.hidden)pollTimer=setTimeout(poll,Math.max(40,(connected?200:1200)-(performance.now()-started)));}
}
async function boot(){
  if(booting)return;booting=true;
  try{
    const [worldData]=await Promise.all([
      jsonFetch('/api/world'),
      new Promise(resolve=>{
        if(arthurImage.complete&&arthurImage.naturalWidth)return resolve();
        const timer=setTimeout(resolve,3500);
        const ready=()=>{clearTimeout(timer);resolve();};
        arthurImage.onload=ready;arthurImage.onerror=ready;arthurImage.src='/arthur_sprites.png';
      })
    ]);
    world=worldData.world||worldData;
    if(!Array.isArray(world.tiles))throw new Error('World map is unavailable.');
    landscape=new Landscape(world,{tileSize:T});
    arthur=new ArthurRenderer(arthurImage);creatures=new CreatureRenderer();
    await fetchState();makeControls();renderUI();resize();initialized=true;
    if(!raf)raf=requestAnimationFrame(loop);clearTimeout(pollTimer);pollTimer=setTimeout(poll,200);
  }catch(e){
    connection(false,location.protocol==='file:'?'Start the included Python server and open http://localhost:8765 in your browser.':e.message);
    if(!document.hidden){clearTimeout(pollTimer);pollTimer=setTimeout(boot,1200);}
  }
  finally{booting=false;}
}
function renderUI(){
  if(!latest)return;
  const s=latest.state,owner=latest.owner_mode;
  setText('clock',`Day ${s.day} · ${fmt(s.minute)}`);
  setText('viewers',`${latest.viewer_count??1} watching`);
  setText('accessLabel',owner?'Your world':'Spectator');
  setText('arthurPause',s.paused?'Continue Arthur':'Pause Arthur');$('arthurPause').setAttribute('aria-pressed',String(!!s.paused));
  setText('modeNote',owner?'Arthur chooses his own adventures. You can suggest the next one.':'You’re watching Arthur’s shared world.');
  setText('destinationHelp',owner?'Arthur will walk there, then continue his own adventures.':'This is a spectator view. The local owner can suggest destinations.');
  setText('thought',`“${s.thought||'There is always something new to notice.'}”`);
  setText('goal',s.last_action||title(s.goal));
  setText('moodTag',s.mood>75?'Feeling content':s.mood>45?'Taking it all in':'A quiet moment');
  setText('motionLabel',s.moving?`On his way to ${labels[s.goal]?.toLowerCase()||title(s.goal)}`:s.last_action||'Taking in the world');
  let nearest='home',distance=Infinity;
  for(const [name,p] of Object.entries(world.sites)){const d=Math.hypot(s.x-p[0],s.y-p[1]);if(d<distance){distance=d;nearest=name;}}
  const regions={home:'Home & sanctuary',forest:'Whispering Woods',hill:'Sunlit Ridge',pond:'Glasswater Lake',beach:'Glasswater shore',town:'Alder Village',market:'Alder Village',grove:'Bramble Grove',meadow:'Wildflower Meadow',homesite:'Arthur’s house plot'};
  setText('place',regions[nearest]);
  for(const key of ['energy','hunger','curiosity','mood']){
    if(!$('stat-'+key))continue;const value=clamp(Number(s[key])||0,0,100);setText('stat-'+key,Math.round(value));$('bar-'+key).style.width=value+'%';
  }
  for(const b of document.querySelectorAll('#destinations button')){b.classList.toggle('selected',s.goal===b.dataset.site);b.setAttribute('aria-pressed',String(s.goal===b.dataset.site));}
  const plan=(s.plans||[]).find(p=>p.id===s.active_plan&&p.status==='active');
  const aspiration=(s.aspirations||[]).find(a=>a.name===s.active_aspiration);
  setText('project',plan?`${plan.title} · ${Math.min(plan.index+1,plan.steps.length)}/${plan.steps.length} · ${plan.steps[plan.index]||'Finishing up'}`:aspiration?`${aspiration.name} · ${aspiration.progress}/${aspiration.required}`:'Following his curiosity');
  const companions=s.companions||[];
  setText('collectionCount',`${companions.length} ${companions.length===1?'friend':'friends'}`);
  setText('sanctuary',companions.length>1?`${companions.length-1} friends at the sanctuary · one adventuring with Arthur.`:companions.length?'One friend exploring alongside Arthur.':'New friends will find a home in the sanctuary.');
  const card=(name,detail,color)=>`<div class="creature-card"><div class="creature-icon" style="--creature:${color}" aria-hidden="true"></div><div><b>${escapeHTML(name)}</b><small>${detail}</small></div></div>`;
  setHTML('collection',companions.length?companions.map(c=>card(c.nickname||c.species,`${escapeHTML(c.form||c.species)} · Level ${Number(c.level)||1}<br>Friendship ${Math.round(c.friendship??c.bond??0)} · XP ${Number(c.xp)||0}`,colors[c.species]||'#9faaa1')).join(''):'<p class="empty">He hasn’t befriended a creature yet. There are little lives all around him.</p>');
  setHTML('encyclopedia',(latest.encyclopedia||[]).map(e=>card(e.seen?e.species:'Unknown creature',`${e.owned?'Befriended':e.seen?'Seen':'Undiscovered'} · ${escapeHTML(e.seen?e.habitat:'Unknown habitat')}${e.evolution?'<br>→ '+escapeHTML(e.evolution):''}`,e.seen?colors[e.species]||'#8e9e86':'#bdc5b4')).join(''));
  setText('inventory',Object.entries(s.inventory||{}).map(([k,v])=>`${title(k)} ${v}`).join(' · ')||'Nothing collected yet');
  setText('wallet',`${s.coins??0} coins`);
  renderChat(s);renderMind(s);renderHouse(s);renderOwnerAccess();
  setHTML('journal',(latest.journal||[]).slice(0,30).map(e=>`<div class="entry"><time>DAY ${Number(e.day)} · ${fmt(e.minute)}</time>${escapeHTML(e.event)}</div>`).join('')||'<p class="empty">His first adventures are just beginning.</p>');
  setText('preferences',Object.entries(owner?s.visits||{}:{}).sort((a,b)=>b[1]-a[1]).filter(([,v])=>v>0).map(([k,v])=>`${labels[k]||title(k)} · ${v} visits`).join(' / ')||'Still finding his favorites');
  setText('traits',Object.entries(owner?s.traits||{}:{}).map(([k,v])=>`${title(k)} ${Math.round(v)}`).join(' · '));
  setText('reflection',owner?s.reflection||'Still getting to know his world.':'');
  setText('discoveries',(owner?s.discoveries||[]:[]).join(' · ')||'His discoveries will appear here.');
  setText('structures',(owner?s.structures||[]:[]).map(b=>title(b.kind)).join(' · ')||'Nothing built yet.');
  $('memoryDetails').hidden=!owner;
  setHTML('memories',(owner?latest.memories||[]:[]).slice(0,6).map(m=>`<div class="entry"><time>DAY ${Number(m.day)}</time>${escapeHTML(m.summary)}</div>`).join('')||'<p class="empty">A lifetime of memories ahead.</p>');
  updatePermissions();
}
async function act(path,body,{errorId='error'}={}){
  if(!connected||!latest?.owner_mode||busy)return false;
  busy=true;setText(errorId,'');updatePermissions();
  try{await jsonFetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});await fetchState();renderUI();return true;}
  catch(e){setText(errorId,e.message);return false;}
  finally{busy=false;updatePermissions();}
}

const preferenceNames={...labels,building:'Making things',companionship:'Company',exploration:'Exploring',quiet:'Quiet places',wood:'Working with wood',stone:'Working with stone',flowers:'Flowers',berries:'Berries',woodland:'Woodland homes',stone_cottage:'Stone cottages',meadow_cottage:'Meadow cottages',waste:'Wasting materials',rushing:'Being rushed',blocked_routes:'Blocked paths'};
const empty=text=>`<p class="empty">${escapeHTML(text)}</p>`;
const requestId=()=>globalThis.crypto?.randomUUID?.()||`message-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
function aiState(){
  const a=latest?.ai||{};
  return {...a,configured:a.configured??!!latest?.ai_configured,status:a.status||(latest?.ai_configured?'configured':'not_configured')};
}
function renderOwnerAccess(){
  const owner=!!latest?.owner_mode;
  $('ownerAccess').hidden=owner&&!ownerToken;
  setText('ownerAccessTitle',owner?'Owner access is unlocked':'Owner access');
  setText('ownerAccessHelp',owner?'Owner access is saved for this browser tab. Lock the controls before handing this device to someone else.':'Enter your private owner access code to open your conversations and controls.');
  $('ownerToken').hidden=owner;$('ownerUnlock').hidden=owner;$('ownerLock').hidden=!ownerToken;
}
function renderChat(s){
  const owner=!!latest.owner_mode,a=aiState(),status=s.chat_status||{status:'idle'};
  const history=owner?(s.chat_history||[]).slice(-40):[];
  if(!owner){chatSubmission=null;chatDeliveryError='';$('chatInput').value='';}
  if(owner&&!chatSubmitting){
    if(status.status==='thinking'&&status.request_id){
      if(!chatSubmission||chatSubmission.request_id===status.request_id){
        chatSubmission={...chatSubmission,request_id:status.request_id,message:status.message||chatSubmission?.message||'',job_id:status.job_id,accepted:true,awaiting:true};
        chatDeliveryError='';
      }
    }else if(status.status==='error'&&status.request_id){
      if(!chatSubmission||chatSubmission.request_id===status.request_id){
        chatSubmission={...chatSubmission,request_id:status.request_id,message:status.message||chatSubmission?.message||'',job_id:status.job_id,accepted:true,awaiting:false,failed:true};
      }
    }
    const completed=chatSubmission&&history.some(m=>m.speaker==='arthur'&&(m.request_id===chatSubmission.request_id||(m.job_id&&m.job_id===chatSubmission.job_id)));
    const finishedStatus=chatSubmission?.accepted&&status.status==='idle'&&(status.request_id===chatSubmission.request_id||(status.job_id&&status.job_id===chatSubmission.job_id));
    if(completed||finishedStatus){chatSubmission=null;chatDeliveryError='';}
  }
  const waiting=owner&&(chatSubmitting||status.status==='thinking'||!!chatSubmission?.awaiting);
  const err=owner&&!chatSubmitting?(chatDeliveryError||(status.status==='error'?status.error||'Arthur could not finish this reply. You can retry the message.':'')):'';
  const scrolled=$('chatLog').scrollHeight-$('chatLog').scrollTop-$('chatLog').clientHeight<45;
  let markup=history.map(m=>`<div class="chat-message ${m.speaker==='arthur'?'':'you'}"><strong>${m.speaker==='arthur'?'Arthur':'You'}${m.speaker==='arthur'?`<span class="message-source">${m.source==='model'?'AI reply':m.source==='local'?'Local reply':''}</span>`:''}</strong>${escapeHTML(m.text)}${m.speaker==='arthur'&&m.action_note?`<div class="chat-action-note">${escapeHTML(m.action_note)}</div>`:''}</div>`).join('');
  const alreadyVisible=chatSubmission&&history.some(m=>m.request_id===chatSubmission.request_id||(m.job_id&&m.job_id===chatSubmission.job_id));
  if(owner&&chatSubmission?.message&&!alreadyVisible&&(chatSubmitting||chatSubmission.accepted))markup+=`<div class="chat-message you pending"><strong>You</strong>${escapeHTML(chatSubmission.message)}</div>`;
  const changed=setHTML('chatLog',markup||empty(owner?'Ask him about a memory, a place he likes, or the home he wants to build.':'Conversations are private. Unlock owner access to talk with Arthur.'));
  if(changed&&scrolled)$('chatLog').scrollTop=$('chatLog').scrollHeight;
  $('chatActivity').hidden=!waiting;setText('chatActivityText',chatSubmitting?'Sending your message…':connected?'Arthur is replying…':'Your message is waiting. Reconnecting for his reply…');
  $('chatErrorBox').hidden=!err;setText('chatError',err);$('chatRetry').hidden=!owner||!chatSubmission;
  const failed=['error','unavailable'].includes(a.status),verified=a.verified===true&&!failed&&(a.healthy===true||['ready','healthy','thinking'].includes(a.status));
  const mode=!owner?'Private conversation':failed?'AI connection issue':!a.configured?'Local mode':verified?'AI conversation':'AI not verified';
  setText('chatMode',mode);$('chatMode').className='quiet-tag '+(failed?'mode-error':verified?'mode-ready':'');
  setText('aiNote',a.configured?(verified?'AI conversation':failed?'AI connection issue':'AI not verified'):'Local mode');
  setText('chatIntro',owner?'Share an idea, ask about his day, or help him dream up a home. His replies draw on his saved character and experiences.':'Arthur’s world is open to watch. His conversations and personal memories belong to the owner.');
  setText('chatNote',!owner?'Unlock owner access above to start a private conversation.':!a.configured?'Local replies are active. Connect AI conversation below for open-ended conversation.':failed?'Arthur’s world keeps running while the AI connection is unavailable.':verified?'Your conversations are remembered. You can also say “stop”, “go to the forest”, or ask about his house.':'An API key is configured. Your next message will verify the connection.');
  $('chatPrompts').hidden=!owner;
  $('aiSetup').hidden=!owner||verified;
  setText('aiSetupTitle',!a.configured?'Connect AI conversation':failed?'AI connection needs attention':'Check the AI connection');
  setText('aiSetupMessage',!a.configured?'AI conversation is not connected on this world’s host yet.':failed?(a.last_error||a.message||'The AI service could not complete the last request. Check the setup on the host computer, then retry your message.'):'The host has a key, but a successful AI reply has not been confirmed yet.');
  $('aiSetupInstructions').hidden=!!a.configured&&!failed;
}
function renderMind(s){
  const owner=!!latest.owner_mode,m=owner?s.mind:null;
  $('mindContent').hidden=!owner;
  setText('mindMode',owner?'Saved across visits':'Private');
  setText('mindSummary',!owner?'Arthur’s personal memories and outlook are private to the owner.':m?.identity||'Preferences and plans grow from his experiences and stay with him between visits.');
  if(!m){
    for(const id of ['mindValues','mindLikes','mindDislikes','mindGoals','mindInspirations','mindThoughts'])setHTML(id,owner?empty('His story is just beginning.'):'');
    return;
  }
  setHTML('mindValues',(m.values||[]).slice(0,5).map(v=>`<span>${escapeHTML(title(v))}</span>`).join(''));
  const preferences=Object.entries(m.preferences||{}).filter(([,v])=>v&&['like','dislike'].includes(v.stance)).sort((a,b)=>Math.abs(b[1].score||0)-Math.abs(a[1].score||0));
  for(const [id,stance,message] of [['mindLikes','like','His favorite things will emerge as he explores.'],['mindDislikes','dislike','He hasn’t formed any strong dislikes yet.']]){
    const entries=preferences.filter(([,v])=>v.stance===stance).slice(0,5);
    setHTML(id,entries.length?entries.map(([key,v])=>`<div class="preference"><strong>${escapeHTML(preferenceNames[key]||title(key))}</strong><p>${escapeHTML(v.reason||'')}</p></div>`).join(''):empty(message));
  }
  const goals=(m.goals||[]).filter(g=>g.status!=='completed').slice(0,3);
  setHTML('mindGoals',goals.length?goals.map(g=>`<div class="mind-item"><strong>${escapeHTML(g.title)}</strong><p>${escapeHTML(g.motivation||'')}</p><small>${escapeHTML(title(g.status||'idea'))}</small></div>`).join(''):empty('He’s making room for a new ambition.'));
  const inspirations=(m.inspirations||[]).slice(-3).reverse();
  setHTML('mindInspirations',inspirations.length?inspirations.map(i=>`<div class="mind-item"><p>${escapeHTML(i.text)}</p><small>Day ${Number(i.day)||1}</small></div>`).join(''):empty('A visit, a conversation, or a small discovery can spark an idea.'));
  const thoughts=(m.diary||[]).slice(-4).reverse();
  setHTML('mindThoughts',thoughts.length?thoughts.map(t=>`<div class="mind-thought"><p>“${escapeHTML(t.text)}”</p><time>DAY ${Number(t.day)||1}${Number.isFinite(t.minute)?' · '+fmt(t.minute):''}${t.source==='model'?' · AI reflection':''}</time></div>`).join(''):empty('His first reflections will appear here.'));
}
function renderHouse(s){
  const h=s.construction,owner=!!latest.owner_mode;
  if(!h){setText('houseTask','The house project is loading.');return;}
  const complete=h.status==='complete',stages=[['foundation','Foundation'],['frame','Frame'],['roof','Roof'],['finish','Finishing']];
  const progress=complete?1:clamp(Number(h.total_progress)||0,0,1),percent=Math.floor(progress*100);
  const statusLabel={planned:'Planning',active:'In progress',paused:'Paused',complete:'A home of his own'};
  setText('houseStatus',statusLabel[h.status]||title(h.status));
  setText('houseStory',complete?'Gathered, carried, and built a little at a time. A new place in Arthur’s story.':'Arthur gathers materials, carries them to his plot, and builds his home one stage at a time.');
  setHTML('houseSteps',stages.map(([id,label],i)=>`<li class="${complete||(h.completed_phases||[]).includes(id)||i<(h.phase_index||0)?'done':i===(h.phase_index||0)&&h.status!=='planned'?'current':''}">${label}</li>`).join(''));
  setText('housePhase',complete?'Home is finished':`${h.phase_label||'Planning'} · ${Math.floor(clamp(Number(h.progress)||0,0,1)*100)}% of this stage`);setText('housePercent',`${percent}% overall`);
  $('houseProgressBar').style.width=`${percent}%`;$('houseProgress').setAttribute('aria-valuenow',percent);$('houseProgress').setAttribute('aria-valuetext',`${percent}% of the house is complete`);
  setText('houseTask',h.reason||h.current_task||(h.status==='planned'?'Arthur is considering his first building project.':h.status==='paused'?'The project is paused. His materials and progress are saved.':'He’s making progress at his own pace.'));
  const required=h.required||{wood:18,stone:10,flowers:6},stock=h.stockpile||{},spent=h.spent||{};
  setHTML('houseMaterials',Object.entries(required).filter(([,n])=>n>0).map(([key,total])=>{
    const remaining=Math.max(0,Number(total)-(Number(spent[key])||0)),have=complete?Number(spent[key])||0:Number(stock[key])||0,need=complete?Number(total):remaining;
    return `<div class="material ${have>=need?'ready':''}"><strong>${escapeHTML(title(key))}</strong><b>${have} <span>/ ${need}</span></b><small>${complete?'Used in the house':`Stored · ${Number(s.inventory?.[key])||0} carried`}</small></div>`;
  }).join(''));
  const missing=Object.entries(h.missing||{}).filter(([,n])=>n>0).map(([k,n])=>`${n} ${k}`).join(', ');
  setText('houseMaterialsNote',complete?'These materials are now part of his home.':missing?`Still needed for this stage: ${missing}.`:'Materials for this stage are ready. Work progresses when Arthur is at the plot.');
  const styles=Array.isArray(h.styles)?h.styles:[];
  if(styles.length)setHTML('houseStyle',styles.map(style=>`<option value="${escapeHTML(style.id)}">${escapeHTML(style.label)}</option>`).join(''));
  $('houseStyle').value=h.style||'woodland';
  const selected=styles.find(style=>style.id===h.style);
  setText('houseStyleHelp',h.can_change_style?(selected?.description||'Choose the look before building begins.'):'The chosen style is now part of the house plan.');
  $('houseStart').hidden=h.status!=='planned';$('housePause').hidden=h.status!=='active';$('houseResume').hidden=h.status!=='paused';$('houseDeposit').hidden=complete;
  setText('houseHint',!owner?'Arthur builds autonomously. Owner access unlocks project controls.':complete?'The completed house and its story stay saved with this world.':h.can_deposit?'Arthur is at the plot with supplies. Store them now, or let him continue on his own.':h.status==='paused'?'Continue when you’re ready; the stored materials are safe.':'Arthur can gather and deliver supplies himself. To store carried materials, first visit the plot.');
}
async function sendChat(message,{retry=false,reuse=false}={}){
  if(!message||!connected||!latest?.owner_mode||chatSubmitting||latest.state.chat_status?.status==='thinking')return false;
  if(!reuse||!chatSubmission)chatSubmission={request_id:requestId(),message,accepted:false,awaiting:false};
  const submission=chatSubmission;chatSubmitting=true;chatDeliveryError='';renderChat(latest.state);updatePermissions();
  let accepted=false;
  try{
    const result=await jsonFetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:submission.message,request_id:submission.request_id,...(retry?{retry:true}:{})})});
    submission.accepted=true;submission.awaiting=result.status==='pending'||result.status==='thinking';submission.job_id=result.job_id||submission.job_id;submission.failed=false;
    accepted=true;if($('chatInput').value.trim()===message)$('chatInput').value='';
    try{await fetchState();}catch{connection(false);}
  }catch(e){
    submission.awaiting=false;
    chatDeliveryError=e.name==='AbortError'?'Delivery could not be confirmed. Retry to safely check this message.':e.message||'This message could not be delivered. Try again.';
  }finally{
    chatSubmitting=false;if(latest)renderChat(latest.state);updatePermissions();
    if(accepted&&!$('chatInput').disabled)$('chatInput').focus();
    $('chatLog').scrollTop=$('chatLog').scrollHeight;
  }
  return accepted;
}
$('chatForm').addEventListener('submit',async event=>{event.preventDefault();await sendChat($('chatInput').value.trim());});
$('chatInput').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chatForm').requestSubmit();}});
$('chatRetry').addEventListener('click',async()=>{if(chatSubmission)await sendChat(chatSubmission.message,{reuse:true,retry:!!chatSubmission.failed});});
for(const button of document.querySelectorAll('#chatPrompts button'))button.addEventListener('click',()=>{if(!button.disabled){$('chatInput').value=button.dataset.prompt;$('chatInput').focus();}});
for(const [id,action] of [['houseStart','start'],['housePause','pause'],['houseResume','resume'],['houseDeposit','deposit']])$(id).addEventListener('click',()=>act('/api/build',{action},{errorId:'houseError'}));
$('houseStyle').addEventListener('change',()=>act('/api/build',{action:'style',style:$('houseStyle').value},{errorId:'houseError'}));
$('houseVisit').addEventListener('click',()=>act('/api/suggest',{goal:'homesite'},{errorId:'houseError'}));
$('arthurPause').addEventListener('click',()=>act('/api/chat',{message:latest?.state.paused?'continue':'stop',request_id:requestId()}));
$('ownerAccessForm').addEventListener('submit',async event=>{
  event.preventDefault();if(ownerUnlocking)return;
  const candidate=$('ownerToken').value.trim();if(!candidate){setText('ownerAccessError','Enter your private owner access code.');return;}
  ownerUnlocking=true;setText('ownerAccessError','');ownerToken=candidate;accessRevision++;buffer.reset();updatePermissions();
  try{
    await fetchState();
    if(latest?.owner_mode){try{sessionStorage.setItem('arthurOwnerToken',ownerToken);}catch{}$('ownerToken').value='';$('ownerAccess').open=false;}
    else{ownerToken='';try{sessionStorage.removeItem('arthurOwnerToken');}catch{}setText('ownerAccessError','That access code was not accepted. Check your private owner access code.');}
    renderUI();
  }catch{ownerToken='';setText('ownerAccessError','Could not verify owner access. Check the connection and try again.');}
  finally{ownerUnlocking=false;updatePermissions();}
});
$('ownerLock').addEventListener('click',async()=>{
  accessRevision++;ownerToken='';chatSubmission=null;chatDeliveryError='';$('chatInput').value='';$('ownerToken').value='';
  try{sessionStorage.removeItem('arthurOwnerToken');}catch{}
  buffer.reset();visual=null;
  if(latest){latest={...latest,owner_mode:false,state:{...latest.state,mind:null,plans:[],reflection:'',chat_history:[],chat_status:{status:'spectator'}},memories:[]};renderUI();}
  try{await fetchState();renderUI();}catch{connection(false);}
});


function resize(){
  const rect=canvas.getBoundingClientRect(),compact=matchMedia('(max-width:540px)').matches;
  const width=clamp(Math.round(rect.width*1.2),520,1200),height=Math.round(width*(compact?.75:.625));
  if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;ctx.imageSmoothingEnabled=true;cameraReady=false;}
}
new ResizeObserver(resize).observe(canvas);
function cameraTarget(actor,vw,vh){return {x:clamp(actor.x+.5-vw/T/2,0,Math.max(0,world.width-vw/T)),y:clamp(actor.y+.5-vh/T*.55,0,Math.max(0,world.height-vh/T))};}
function render(now,dt){
  if(!landscape)return;
  visual=buffer.sample(now);if(!visual)return;
  const start=performance.now(),vw=canvas.width/zoom,vh=canvas.height/zoom;
  const target=cameraTarget(visual,vw,vh);
  if(!cameraReady){Object.assign(camera,target);cameraReady=true;}
  else if(following){const k=1-Math.exp(-dt*4.5);camera.x+=(target.x-camera.x)*k;camera.y+=(target.y-camera.y)*k;}
  ctx.setTransform(zoom,0,0,zoom,0,0);
  landscape.drawGround(ctx,camera,vw,vh,now,visual);
  const objects=landscape.objectsForDepth(camera,vw,vh,now,visual);
  const entities=[...(visual.wild_creatures||[]).map(c=>({...c,renderId:'wild-'+c.id})),...(visual.companions||[]).map((c,i)=>({...c,renderId:'friend-'+(c.id??i)}))];
  for(const entity of entities){
    if(!Number.isFinite(entity.x)||!Number.isFinite(entity.y))continue;
    if(entity.x<camera.x-2||entity.x>camera.x+vw/T+2||entity.y<camera.y-2||entity.y>camera.y+vh/T+3)continue;
    objects.push({depth:entity.y+.5,draw:c=>creatures.draw(c,entity,camera,T,now)});
  }
  objects.push({depth:visual.y+.5,draw:c=>arthur.draw(c,visual,camera,T,now)});
  objects.sort((a,b)=>a.depth-b.depth);for(const obj of objects)obj.draw(ctx);
  landscape.drawAtmosphere(ctx,camera,vw,vh,now,visual);
  ctx.setTransform(1,0,0,1,0,0);
  paintTime=performance.now()-start;maxPaintTime=Math.max(maxPaintTime,paintTime);
  if($('mapDialog').open&&now-lastMap>160){landscape.drawMap(mapCtx,visual);lastMap=now;}
}
function loop(now){
  raf=0;if(document.hidden)return;
  raf=requestAnimationFrame(loop);
  const dt=frameClock.tick(now);if(dt===null)return;
  render(now,dt);frameCount++;
  if(!fpsStart)fpsStart=now;
  if(now-fpsStart>=1000){fps=Math.round(frameCount*1000/(now-fpsStart));setText('fps',`${fps} FPS · live world`);frameCount=0;fpsStart=now;}
  if(connected&&lastGood&&now-lastGood>1800)connection(false);
}
function changeZoom(delta){zoom=clamp(zoom+delta,.8,1.6);cameraReady=false;following=true;setText('follow','Following');}
$('zoomOut').addEventListener('click',()=>changeZoom(-.2));$('zoomIn').addEventListener('click',()=>changeZoom(.2));
$('follow').addEventListener('click',()=>{following=true;setText('follow','Following');});
let drag=null;
canvas.style.touchAction='pan-y';
canvas.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'||!visual)return;drag={x:e.clientX,y:e.clientY,cx:camera.x,cy:camera.y};canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{
  if(!drag||!world)return;const scale=canvas.width/canvas.getBoundingClientRect().width;
  const dx=(e.clientX-drag.x)*scale/(zoom*T),dy=(e.clientY-drag.y)*scale/(zoom*T);
  if(Math.hypot(dx,dy)<.05)return;following=false;setText('follow','Follow Arthur');
  camera.x=clamp(drag.cx-dx,0,Math.max(0,world.width-canvas.width/(zoom*T)));
  camera.y=clamp(drag.cy-dy,0,Math.max(0,world.height-canvas.height/(zoom*T)));
});
canvas.addEventListener('pointerup',()=>{drag=null;});canvas.addEventListener('pointercancel',()=>{drag=null;});
$('mapToggle').addEventListener('click',()=>{if(!landscape)return;$('mapDialog').showModal();landscape.drawMap(mapCtx,visual||latest?.state||{});});
$('mapClose').addEventListener('click',()=>$('mapDialog').close());
$('mapDialog').addEventListener('click',e=>{if(e.target===$('mapDialog')){const r=$('mapDialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('mapDialog').close();}});
$('retry').addEventListener('click',()=>initialized?poll():boot());
document.addEventListener('visibilitychange',()=>{
  clearTimeout(pollTimer);if(raf)cancelAnimationFrame(raf);raf=0;frameClock.reset();fpsStart=0;frameCount=0;
  if(!document.hidden){buffer.reset();cameraReady=false;arthur?.reset();if(initialized){poll();raf=requestAnimationFrame(loop);}else boot();}
});
// Read-only diagnostics are useful for checking frame pacing and snapshot motion.
Object.defineProperty(window,'arthurDiagnostics',{get:()=>({version:'1.8',fps,paintMs:paintTime,maxPaintMs:maxPaintTime,buffered:buffer.frames.length,connected,rendered:visual?{x:visual.x,y:visual.y,speed:visual.speed,distance:visual.distance,moving:visual.moving}:null,server:latest?{seq:latest.seq,x:latest.state.x,y:latest.state.y}:null})});
boot();
