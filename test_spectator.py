import copy
import json
from pathlib import Path
import time
import unittest
from spectator import Spectator

class CanvasProbe:
    def __init__(self): self.calls=[]
    def delete(self,*a): self.calls=[]
    def winfo_width(self): return 1364
    def winfo_height(self): return 1024
    def __getattr__(self,name):
        if name.startswith('create_'):
            return lambda *a,**kw:self.calls.append((name,a,kw))
        raise AttributeError(name)

class SpectatorTests(unittest.TestCase):
    def setUp(self):
        self.app=Spectator.__new__(Spectator)
        self.app.canvas=CanvasProbe()
        self.app.obs={'credits':260,'day':1,'total_days':7,'energy':12,'max_energy':12,
            'reputation':0,'goal':{'credits':650,'collection':2},'inventory':[],
            'crates':[],'collection':[],'phase':'active','log':[],
            'last_event':{'seq':1,'type':'start','title':'开门','text':'欢迎'},'demand':{}}
        self.app.error=None;self.app.inventory_page=0
        self.app.started=time.monotonic();self.app.event_at=time.monotonic()
        self.words=[]
        self.app.text=lambda x,y,text,*a,**kw:self.words.append(str(text))
    def test_fresh_screen(self):
        self.app.render()
        self.assertIn('星际旧货铺',self.words)
        self.assertTrue(len(self.app.canvas.calls)>20)
    def test_reveal_all_art_types_and_rarities(self):
        for kind in ['tool','artifact','bot','plant','signal']:
            for rarity in ['common','rare','legendary']:
                item={'id':'I001','name':'测试物品','kind':kind,'rarity':rarity,
                    'color':'#7aeecc','condition':71,'value_estimate':[30,50],'price':None}
                self.app.obs['inventory']=[item]
                self.app.obs['last_event']={'seq':2,'type':'reveal','title':'发现','text':'已开启','item':item}
                for elapsed in [0,1.2,5]:
                    self.app.event_at=time.monotonic()-elapsed
                    self.app.render()
                self.assertIn('测试物品',self.words)
    def test_inventory_paging(self):
        self.app.obs['inventory']=[{'id':f'I{i:03}','name':f'货物{i}','kind':'bot','rarity':'rare','condition':50,'value_estimate':[20,40]} for i in range(10)]
        self.app.inventory_page=3
        self.app.render()
        self.assertIn('货物9',self.words)
        self.assertNotIn('货物0',self.words)
    def test_end_phase_and_missing_state(self):
        for phase in ['won','lost']:
            self.app.obs['phase']=phase;self.app.render()
        self.app.obs=None;self.app.render()
        self.assertIn('等候店长开门…',self.words)

if __name__=='__main__':unittest.main()
