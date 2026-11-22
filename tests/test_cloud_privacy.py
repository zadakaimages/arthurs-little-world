"""Cloud owner access must protect the API as well as the visible panels."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import server


class CloudPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='arthur-privacy-')
        self.addCleanup(self.temporary.cleanup)
        self.runtime=server.Runtime(db_path=Path(self.temporary.name)/'world.sqlite3',enable_ai=False)
        self.addCleanup(self.runtime.close)

    def seed_private_fields(self):
        state=self.runtime.state
        state['reflection']='PRIVATE_REFLECTION_CANARY'
        state['project']='PRIVATE_PROJECT_CANARY'
        state['plans']=[{'id':1,'title':'PRIVATE_PLAN_CANARY','steps':['home','pond'],
                         'index':0,'status':'active','reason':'PRIVATE_REASON_CANARY'}]
        state['active_plan']=1
        state['plan_history']=[{'title':'PRIVATE_PLAN_HISTORY_CANARY'}]
        state['aspirations']=[{'name':'PRIVATE_ASPIRATION_CANARY'}]
        state['active_aspiration']='PRIVATE_ASPIRATION_CANARY'
        state['milestones']=[{'event':'PRIVATE_MILESTONE_CANARY'}]
        state['discoveries']=['PRIVATE_DISCOVERY_CANARY']
        state['preferences']['PRIVATE_PREFERENCE_CANARY']=1
        state['visits']['PRIVATE_VISIT_CANARY']=1
        state['traits']['PRIVATE_TRAIT_CANARY']=1
        state['activity_count']['PRIVATE_ACTIVITY_CANARY']=1
        state['structures']=[{'kind':'bench','x':19,'y':18,'note':'PRIVATE_STRUCTURE_NOTE_CANARY'}]
        server.remember(self.runtime.connection,state,'home','PRIVATE_MEMORY_CANARY',1.0)
        self.runtime.command('chat',{'message':'My name is PRIVATE_CHAT_CANARY',
                                    'request_id':'privacy-regression'})
        state['thought']='PRIVATE_SAVED_THOUGHT_CANARY'
        state['last_action']='PRIVATE_SAVED_ACTION_CANARY'
        self.runtime._publish()

    def test_spectator_redaction_does_not_erase_owner_state_or_visible_world(self):
        self.seed_private_fields()
        spectator=self.runtime.snapshot(False)
        owner=self.runtime.snapshot(True)
        self.assertNotIn('PRIVATE_',json.dumps(spectator))
        self.assertIn('PRIVATE_CHAT_CANARY',json.dumps(owner['state']['chat_history']))
        self.assertIn('PRIVATE_MEMORY_CANARY',json.dumps(owner['memories']))
        self.assertEqual(owner['state']['reflection'],'PRIVATE_REFLECTION_CANARY')
        self.assertEqual(owner['state']['plans'][0]['title'],'PRIVATE_PLAN_CANARY')
        self.assertEqual(owner['state']['thought'],'PRIVATE_SAVED_THOUGHT_CANARY')
        self.assertEqual(owner['state']['last_action'],'PRIVATE_SAVED_ACTION_CANARY')
        self.assertTrue(spectator['state']['thought'])
        self.assertTrue(spectator['state']['last_action'])
        self.assertEqual(spectator['state']['structures'],[{'kind':'bench','x':19,'y':18}])
        self.assertEqual(spectator['state']['construction'],owner['state']['construction'])
        self.assertEqual(spectator['state']['wild_creatures'],owner['state']['wild_creatures'])
        for key in ('x','y','day','minute','energy','inventory','coins'):
            self.assertEqual(spectator['state'][key],owner['state'][key])
        self.assertTrue(spectator['journal'])
        self.assertNotIn('PRIVATE_CHAT_CANARY',json.dumps(spectator['journal']))

    def test_http_owner_header_and_spectator_controls(self):
        token='test-only-owner-token-not-for-production'
        with patch.object(server,'HOST','0.0.0.0'),patch.object(server,'OWNER_TOKEN',token):
            class QuietHandler(server.Handler):
                def log_message(self,*args):
                    pass

            httpd=server.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
            httpd.runtime=self.runtime
            worker=threading.Thread(target=httpd.serve_forever,daemon=True)
            worker.start()
            base=f'http://127.0.0.1:{httpd.server_port}'

            def request(path,headers=None,data=None,method=None):
                req=urllib.request.Request(base+path,headers=headers or {},data=data,method=method)
                try:
                    response=urllib.request.urlopen(req,timeout=5)
                except urllib.error.HTTPError as error:
                    response=error
                with response:
                    return response.status,response.read()

            try:
                code,_=request('/api/chat',{'X-Arthur-Owner':token,'Content-Type':'application/json'},
                               b'{"message":"My name is PRIVATE_HTTP_CANARY","request_id":"http-privacy"}')
                self.assertEqual(code,200)
                for headers in ({},{'X-Arthur-Owner':'wrong'},
                                {'X-Forwarded-For':'127.0.0.1','X-Real-IP':'127.0.0.1'}):
                    code,body=request('/api/state',headers)
                    self.assertEqual(code,200)
                    self.assertFalse(json.loads(body)['owner_mode'])
                    self.assertNotIn(b'PRIVATE_HTTP_CANARY',body)
                    code,_=request('/api/suggest',headers,b'{"goal":"pond"}')
                    self.assertEqual(code,403)
                code,body=request('/api/state',{'X-Arthur-Owner':token})
                self.assertEqual(code,200)
                self.assertTrue(json.loads(body)['owner_mode'])
                self.assertIn(b'PRIVATE_HTTP_CANARY',body)
                code,_=request('/api/suggest',{'X-Arthur-Owner':token,'Origin':'https://untrusted.example'},
                               b'{"goal":"pond"}')
                self.assertEqual(code,403)
                code,_=request('/api/suggest',{'X-Arthur-Owner':token,'Origin':base},b'{"goal":"pond"}')
                self.assertEqual(code,200)
                for path in ('/server.py','/arthur.env','/arthur.sqlite3','/.git/config','/%2e%2e/server.py'):
                    for method in ('GET','HEAD'):
                        self.assertEqual(request(path,method=method)[0],404)
            finally:
                httpd.shutdown()
                worker.join(timeout=3)
                httpd.server_close()


if __name__=='__main__':
    unittest.main()
