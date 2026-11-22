"""Bounded, asynchronous model jobs; persistence lives in the world's save.

This coordinator is called under Runtime's lock. Workers receive copied context,
never the live world. Only Runtime can validate and execute a proposed action.
"""
import copy
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from ai_client import AIClient, AIError
from mind import ensure_mind, observe, context_for_model, offline_reply


class ConversationEngine:
    def __init__(self,state,*,client=None,enabled=True,autonomy=True,interval=180,limit=40):
        self.client=client or AIClient()
        self.enabled=bool(enabled and self.client.status().get('configured'))
        self.autonomy=autonomy
        self.interval=max(30,float(interval));self.limit=max(1,int(limit))
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='arthur-mind') if self.enabled else None
        self.chat_job=None;self.reflection_job=None
        self.next_reflection=time.monotonic()+min(30,self.interval)
        self.closed=False
        state.setdefault('chat_history',[]);state.setdefault('chat_requests',[]);state.setdefault('ai_usage',[])
        state['chat_history']=state['chat_history'][-200:]
        state['chat_requests']=state['chat_requests'][-80:]
        for entry in state['chat_requests']:
            if entry.get('status')=='pending':
                entry['status']='error';entry['error']='The server restarted before this reply finished. You can retry it.'
        old=state.get('chat_status',{})
        if old.get('status')=='thinking':
            state['chat_status']={**old,'status':'error','error':'The server restarted before this reply finished. You can retry it.'}
        else:state.setdefault('chat_status',{'status':'idle','mode':self.mode,'error':None})
        ensure_mind(state)

    @property
    def mode(self):return 'model' if self.enabled else 'local'

    def _spend_slot(self,state,kind):
        now=time.time()
        state['ai_usage']=[u for u in state.get('ai_usage',[]) if isinstance(u,dict)
                           and isinstance(u.get('at'),(int,float)) and 0<=now-u['at']<3600]
        if len(state['ai_usage'])>=self.limit:return False
        state['ai_usage'].append({'at':now,'kind':kind})
        return True

    def status(self,state):
        data=dict(self.client.status())
        data['status']={'local_only':'not_configured','configured':'unverified','healthy':'ready','error':'error'}.get(data.get('state'),'unverified')
        if isinstance(data.get('last_error'),dict):data['last_error']=data['last_error'].get('message')
        if not self.enabled:
            data['status']='not_configured' if not data.get('configured') else 'disabled'
        elif self.chat_job or self.reflection_job:data['status']='thinking'
        now=time.time()
        data.update(mode=self.mode,autonomy=bool(self.autonomy and self.enabled),
                    calls_last_hour=sum(0<=now-u.get('at',0)<3600 for u in state.get('ai_usage',[])),
                    hourly_limit=self.limit,reflection_interval=self.interval)
        return data

    def _status_for(self,entry):
        return {'status':'thinking' if entry['status']=='pending' else ('error' if entry['status']=='error' else 'idle'),
                'job_id':entry['job_id'],'request_id':entry['request_id'],
                'message':entry['message'],'error':entry.get('error'),'mode':entry['mode']}

    def submit(self,state,message,request_id=None,*,retry=False,revision=0,force_local=False):
        """Return (HTTP code, public receipt, immediate local result or None)."""
        if not isinstance(message,str) or not message.strip() or len(message)>2000:
            return 400,{'error':'Send a message between 1 and 2,000 characters.'},None
        message=message.strip()
        if request_id is None:request_id=uuid.uuid4().hex
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):
            return 400,{'error':'Invalid conversation request ID.'},None
        prior=next((e for e in state['chat_requests'] if e.get('request_id')==request_id),None)
        if prior and prior['message']!=message:return 409,{'error':'This request ID belongs to another message.'},None
        if prior and not (retry and prior['status']=='error'):
            return (202 if prior['status']=='pending' else 200),{
                'ok':True,'job_id':prior['job_id'],'request_id':request_id,'status':prior['status'],
                'reply':prior.get('reply'),'error':prior.get('error'),'duplicate':True},None
        if self.chat_job and not force_local:return 409,{'error':'Arthur is finishing his previous reply. Please wait a moment.'},None
        use_model=self.enabled and not force_local
        if use_model and not self._spend_slot(state,'chat'):
            return 429,{'error':f'The configured limit of {self.limit} model requests per hour has been reached. Arthur’s local world keeps running.'},None
        if prior:
            entry=prior
            entry.update(job_id=uuid.uuid4().hex,status='pending',error=None,revision=revision,
                         mode='model' if use_model else 'local')
        else:
            entry={'request_id':request_id,'job_id':uuid.uuid4().hex,'message':message,
                   'status':'pending','mode':'model' if use_model else 'local','revision':revision,'error':None}
            state['chat_requests'].append(entry);state['chat_requests']=state['chat_requests'][-80:]
            state['chat_history'].append({'id':request_id+'-user','speaker':'you','text':message,
                                          'request_id':request_id,'job_id':entry['job_id'],
                                          'day':state['day'],'minute':state['minute'],'source':'user'})
            state['chat_history']=state['chat_history'][-200:]
            observe(state,'user_message',message,importance=.65,metadata={'speaker':'user','private':True})
        state['chat_status']=self._status_for(entry)
        receipt={'ok':True,'job_id':entry['job_id'],'request_id':request_id,
                 'status':'pending' if use_model else 'completed','mode':entry['mode'],'duplicate':False}
        if use_model:
            context=context_for_model(state,message,mode='chat')
            future=self.pool.submit(self.client.generate,copy.deepcopy(context),mode='chat')
            self.chat_job={'future':future,'entry':entry,'revision':revision,'submitted_at':time.monotonic()}
            return 202,receipt,None
        return 200,receipt,offline_reply(state,message)

    def finish_local(self,state,request_id,result,action_note=''):
        entry=next(e for e in state['chat_requests'] if e['request_id']==request_id)
        self.finish(state,entry,result,action_note)

    def finish(self,state,entry,result,action_note=''):
        reply=str(result.get('reply','')).strip()[:1400]
        if not reply:reply='I am still putting that idea into words.'
        entry.update(status='completed',reply=reply,error=None,action_note=action_note)
        state['chat_history'].append({'id':entry['job_id']+'-arthur','speaker':'arthur','text':reply,
            'request_id':entry['request_id'],'job_id':entry['job_id'],
            'source':entry['mode'],'day':state['day'],'minute':state['minute'],'action_note':action_note})
        state['chat_history']=state['chat_history'][-200:]
        state['chat_status']=self._status_for(entry)
        if self.chat_job and self.chat_job['entry'] is not entry:
            state['chat_status']=self._status_for(self.chat_job['entry'])

    def poll(self,state,revision):
        """Return finished immutable proposals; never execute world changes here."""
        completed=[]
        if self.chat_job and self.chat_job['future'].done():
            job=self.chat_job;self.chat_job=None;entry=job['entry']
            try:
                result=job['future'].result()
                completed.append({'mode':'chat','result':result,'entry':entry,'revision':job['revision']})
            except Exception as error:
                message=error.user_message if isinstance(error,AIError) else 'The conversation connection failed. You can retry this message.'
                entry.update(status='error',error=message)
                state['chat_status']=self._status_for(entry)
                completed.append({'mode':'error','error':message,'entry':entry})
        if self.reflection_job and self.reflection_job['future'].done():
            job=self.reflection_job;self.reflection_job=None
            try:
                result=job['future'].result()
                completed.append({'mode':'reflection','result':result,'revision':job['revision']})
            except Exception:
                # Connection status exposes the safe provider error; local thought continues.
                self.next_reflection=max(self.next_reflection,time.monotonic()+self.interval)
        now=time.monotonic()
        if self.enabled and self.autonomy and not self.closed and not self.chat_job and not self.reflection_job and now>=self.next_reflection:
            self.next_reflection=now+self.interval
            if self._spend_slot(state,'reflection'):
                context=context_for_model(state,mode='reflection')
                future=self.pool.submit(self.client.generate,copy.deepcopy(context),mode='reflection')
                self.reflection_job={'future':future,'revision':revision}
        return completed

    def close(self):
        self.closed=True
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
