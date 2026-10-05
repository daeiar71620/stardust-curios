#!/usr/bin/env python3
"""Native read-only spectator. It never imports the game engine or reads its save."""
import argparse
import json
import math
from pathlib import Path
import time
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

BG = '#080f24'
PANEL = '#111f3b'
INK = '#eaf4ff'
MUTED = '#8daccb'
CYAN = '#68e6ec'
GOLD = '#ffcd68'
RARITIES = {'common': ('普通', '#8fbed6'), 'rare': ('稀有', '#ad9cff'), 'legendary': ('传奇', '#ffd06d')}
KINDS = {'tool':'工具', 'artifact':'古物', 'bot':'机器人', 'plant':'植物', 'signal':'信号'}

class Spectator:
    def __init__(self, path, fullscreen=False):
        self.path = Path(path)
        self.root = tk.Tk()
        self.root.title('星际旧货铺 · AI 店长实时画面')
        self.fonts = {}
        self.text_images = {}
        self.root.configure(bg=BG)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        height = min(964, sh - 70)
        width = round(height * 0.70)
        self.root.geometry(f'{width}x{height}+{(sw-width)//2}+28')
        self.root.minsize(440, 650)
        self.root.attributes('-fullscreen', fullscreen)
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.root.bind('<F11>', lambda _ : self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen')))
        self.root.bind('<Escape>', lambda _ : self.root.attributes('-fullscreen', False))
        self.root.bind('<space>', self.toggle_inventory)
        self.root.bind('<Button-1>', self.toggle_inventory)
        self.root.bind('<Configure>', lambda _: self.render())
        self.obs = None
        self.last_mtime = None
        self.error = None
        self.last_seq = None
        self.event_at = time.monotonic()
        self.inventory_page = 0
        self.started = time.monotonic()
        self.tick()

    def toggle_inventory(self, _=None):
        self.inventory_page += 1
        self.render()

    def text(self, x, y, text, size=18, color=INK, bold=False, anchor='nw', width=None):
        # This desktop's Tk uses core X fonts. Render CJK with its installed
        # Noto font through Pillow, then show native PhotoImages on the canvas.
        pixels=max(9, round(size*self.s))
        key=(str(text),pixels,color,bold,round(width*self.s) if width else None)
        if key not in self.text_images:
            if (pixels,bold) not in self.fonts:
                name='NotoSansCJK-Bold.ttc' if bold else 'NotoSansCJK-Regular.ttc'
                self.fonts[pixels,bold]=ImageFont.truetype('/usr/share/fonts/opentype/noto/'+name,pixels,index=2)
            font=self.fonts[pixels,bold]
            lines=[]
            for paragraph in str(text).split('\n'):
                line=''
                for char in paragraph:
                    if width and font.getlength(line+char)>width*self.s and line:
                        lines.append(line);line=char
                    else:line+=char
                lines.append(line)
            line_h=round(pixels*1.34)
            iw=max(1,math.ceil(max(font.getlength(line) for line in lines))+4)
            ih=max(1,line_h*len(lines))
            im=Image.new('RGBA',(iw,ih),(0,0,0,0))
            draw=ImageDraw.Draw(im)
            for i,line in enumerate(lines):draw.text((1,i*line_h),line,font=font,fill=color,anchor='lt')
            if len(self.text_images)>500:self.text_images.clear()
            self.text_images[key]=ImageTk.PhotoImage(im,master=self.root)
        return self.canvas.create_image(self.ox+x*self.s,self.oy+y*self.s,image=self.text_images[key],anchor=anchor)

    def rect(self, x1, y1, x2, y2, fill=PANEL, outline='', width=1):
        return self.canvas.create_rectangle(self.ox+x1*self.s, self.oy+y1*self.s, self.ox+x2*self.s, self.oy+y2*self.s, fill=fill, outline=outline, width=width*self.s)

    def oval(self,x1,y1,x2,y2,fill,outline='',width=1):
        return self.canvas.create_oval(self.ox+x1*self.s,self.oy+y1*self.s,self.ox+x2*self.s,self.oy+y2*self.s,fill=fill,outline=outline,width=width*self.s)

    def line(self,*pts,fill=INK,width=1):
        out=[]
        for i, p in enumerate(pts): out.append((self.ox if i%2==0 else self.oy)+p*self.s)
        return self.canvas.create_line(*out,fill=fill,width=width*self.s)

    def poly(self, pts,fill,outline='',width=1):
        out=[]
        for i,p in enumerate(pts):out.append((self.ox if i%2==0 else self.oy)+p*self.s)
        return self.canvas.create_polygon(*out,fill=fill,outline=outline,width=width*self.s)

    def progress(self,x,y,w,value,goal,color=CYAN):
        self.rect(x,y,x+w,y+6,'#26334c')
        self.rect(x,y,x+w*min(1,max(0,value/max(1,goal))),y+6,color)

    def item_art(self,x,y,size,item=None,crate=False,anim=0):
        # Original vector artwork, scaled from a 100-unit icon.
        color = (item or {}).get('color', CYAN)
        if not isinstance(color,str) or not color.startswith('#'): color=CYAN
        kind = (item or {}).get('kind','artifact')
        def R(a,b,c,d,f,o='',w=1):self.rect(x+a*size,y+b*size,x+c*size,y+d*size,f,o,w*size)
        def O(a,b,c,d,f,o='',w=1):self.oval(x+a*size,y+b*size,x+c*size,y+d*size,f,o,w*size)
        def L(pts,f,w=1):self.line(*[x+v*size if i%2==0 else y+v*size for i,v in enumerate(pts)],fill=f,width=w*size)
        def P(pts,f,o='',w=1):self.poly([x+v*size if i%2==0 else y+v*size for i,v in enumerate(pts)],f,o,w*size)
        if crate:
            P([12,31,49,14,91,32,52,53], '#416480', '#92d6df',2)
            P([12,31,52,53,52,91,12,70], '#24455d', '#78bbc9',2)
            P([52,53,91,32,91,70,52,91], '#18354f', '#78bbc9',2)
            L([32,22,72,42,72,81],GOLD,5)
            L([12,51,52,73,91,51],'#486c84',2)
            self.text(x+31*size,y+42*size,'?',round(24*size),GOLD,True)
        elif kind == 'bot':
            L([50,18,50,6],color,4); O(45,1,55,11,GOLD)
            R(19,20,81,66,color,'#dffcff',2);R(26,31,74,51,'#13273c')
            O(34,36,43,45,CYAN);O(57,36,66,45,CYAN)
            R(28,68,72,84,'#6887a6');L([30,86,22,94],color,7);L([70,86,78,94],color,7)
            L([17,35,6,55,12,69],color,5);L([83,35,94,55,89,68],color,5)
        elif kind == 'plant':
            L([49,71,48,32], '#77bd94',4)
            O(16,19,50,44,color);O(48,9,81,35,'#70d9b0');O(48,39,81,62,color)
            P([25,65,77,65,68,93,34,93],'#cb907e','#ffe0b9',2)
            R(22,62,80,69,'#ebbd9a');O(28,26,35,31,'#c8ffdf')
        elif kind == 'tool':
            P([40,36,58,47,39,91,22,82], '#748eb7',color,2)
            P([36,9,55,5,46,23,61,31,77,16,83,39,66,53,43,44,30,26], color,'#dcf4ff',2)
            O(27,79,34,86,'#172b45')
        elif kind == 'signal':
            R(18,42,82,85,'#45698a',color,2);R(27,51,63,72,'#142c46')
            L([30,61,37,61,41,55,48,69,53,60,59,60],CYAN,2)
            O(67,56,76,65,GOLD);L([63,40,81,9],color,3)
            L([34,28,39,21,48,18,55,20],color,3)
            L([25,18,33,9,46,5,58,8],color,2)
        else:
            O(7,19,92,87,'#18253f',color,2)
            P([50,6,80,49,50,93,20,49],color,'#effdff',2)
            P([50,6,50,93,20,49],'#59719c')
            L([20,49,80,49],'#edf8ff',1)
            O(43,39,57,54,'#f5fcff')

    def scene(self,o):
        self.rect(22,236,638,505,'#101e38', '#294665')
        self.rect(32,246,628,476,'#09162d')
        t=time.monotonic()-self.started
        for i in range(45):
            x=40+(i*79%576);y=253+(i*47%168)
            radius=1+(i%3==0)
            self.oval(x,y,x+radius,y+radius,'#688cb4' if i%3 else '#b7d2e8')
        self.oval(453,261,547,355,'#304564')
        self.oval(466,263,527,321,'#465b77')
        self.line(431,330,566,289,fill='#7593a8',width=3)
        self.rect(32,448,628,488,'#1b3651')
        self.line(32,448,628,448,fill='#538199',width=2)
        self.poly([98,424,444,424,496,447,63,447],'#294a66','#6998b0')
        self.rect(107,448,445,476,'#18324b')
        self.line(118,455,433,455,fill='#416883',width=2)
        self.text(48,259,'ORBIT / 旧货回收舱',12,'#85a6bf')
        self.text(615,259,'LIVE',12,CYAN,True,anchor='ne')
        evt=o.get('last_event',{})
        elapsed=time.monotonic()-self.event_at
        item=evt.get('item')
        if not item and o.get('inventory'):item=o['inventory'][-1]
        reveal=evt.get('type')=='reveal' and elapsed<4.5
        opening=reveal and elapsed<0.9
        iscrate=opening or (not item and bool(o.get('crates')))
        if reveal:
            color=RARITIES.get((item or {}).get('rarity'),('普通',CYAN))[1]
            for i in range(14):
                a=i*math.tau/14+t*.45
                r=95+12*math.sin(t*2+i)
                cx=300+math.cos(a)*r;cy=365+math.sin(a)*r*.58
                self.line(cx,cy,cx+math.cos(a)*9,cy+math.sin(a)*9,fill=color,width=2)
        if item or iscrate:
            if item and not iscrate:
                rare,col=RARITIES.get(item.get('rarity'),RARITIES['common'])
                self.text(330,286,f'✦  {rare}发现  ✦',17,col,True,anchor='n')
            self.item_art(248,315+math.sin(t*2)*2,1.10,item,iscrate)
            label='正在开启货箱…' if opening else (item or {}).get('name','神秘货箱已入港')
            self.text(330,468,label,20,INK,True,anchor='center')
        else:
            self.item_art(226,312+math.sin(t*1.5)*2,1.18,crate=True)
            self.text(398,347,'下一箱\n会是什么？',24,INK,True,width=180)
            self.text(330,477,'从一间破飞船小店开始',17,MUTED,anchor='center')
        self.text(330,512,evt.get('title','小店开门了'),24,GOLD,True,anchor='n')
        self.text(330,548,evt.get('text','等待 AI 店长的第一笔进货'),16,INK,anchor='n',width=586)

    def render(self):
        if not hasattr(self,'canvas'):return
        c=self.canvas;c.delete('all')
        w,h=max(c.winfo_width(),440),max(c.winfo_height(),650)
        self.s=min(w/660,h/944);self.ox=(w-660*self.s)/2;self.oy=(h-944*self.s)/2
        o=self.obs
        self.rect(0,0,660,944,BG)
        if not o:
            self.text(330,365,'星际旧货铺',42,CYAN,True,anchor='center')
            self.text(330,435,self.error or '等候店长开门…',20,INK,anchor='center',width=590)
            return
        self.text(24,15,'星际旧货铺',34,INK,True)
        self.text(24,64,'盲箱进货  ·  修理估价  ·  好好经营',15,MUTED)
        self.text(635,24,f"第 {o.get('day',1)} / 7 天",23,CYAN,True,anchor='ne')
        self.rect(22,95,638,158,PANEL)
        self.text(38,102,'可用星币',14,MUTED)
        self.text(38,121,f"{o.get('credits',0):,}",28,GOLD,True)
        self.text(282,103,'体力',14,MUTED)
        self.text(282,126,f"{o.get('energy',0)} / {o.get('max_energy',0)}",21,INK,True)
        self.text(445,103,'店铺声望',14,MUTED)
        self.text(445,126,f"★ {o.get('reputation',0)}",21,CYAN,True)
        goal=o.get('goal',{});collection=len(o.get('collection',[]))
        self.text(24,172,f"七日目标  {o.get('credits',0)} / {goal.get('credits',650)} 星币",15,MUTED)
        self.text(638,172,f"珍藏 {collection} / {goal.get('collection',2)}",15,GOLD,anchor='ne')
        self.progress(24,203,408,o.get('credits',0),goal.get('credits',650))
        self.progress(454,203,184,collection,goal.get('collection',2),GOLD)
        demand=o.get('demand',{})
        self.text(24,216,f"今日行情 · {demand.get('label','平稳')} ",12,CYAN)
        self.scene(o)
        self.line(24,598,638,598,fill='#213952')
        self.text(24,610,'货架与珍藏',20,INK,True)
        inventory=o.get('inventory',[])
        self.text(638,615,f"货箱 {len(o.get('crates',[]))}  ·  藏品 {collection}",14,MUTED,anchor='ne')
        pages=max(1,math.ceil(len(inventory)/3));p=self.inventory_page%pages
        visible=inventory[p*3:p*3+3]
        if not visible:
            self.rect(24,649,636,725,PANEL)
            self.text(330,675,'货架还空着，先选一箱神秘货物',18,MUTED,anchor='n')
        for i,item in enumerate(visible):
            y=648+i*49
            self.rect(24,y,636,y+43,PANEL)
            rare,col=RARITIES.get(item.get('rarity'),RARITIES['common'])
            self.item_art(34,y+3,.34,item)
            self.text(81,y+3,item.get('name','未知物品'),18,INK,True)
            self.text(81,y+26,f"{item.get('id','')}  ·  {rare}  ·  完好 {item.get('condition',0)}%",10,col)
            est=item.get('value_estimate',[0,0]);price=item.get('price')
            self.text(622,y+7,f"标价 {price}" if price else f"估值 {est[0]}–{est[1]}",16,GOLD,anchor='ne')
        if pages>1:self.text(636,799,f'{p+1}/{pages}  点击翻页',10,MUTED,anchor='ne')
        self.line(24,808,638,808,fill='#213952')
        self.text(24,820,'店长日志',15,CYAN,True)
        logs=o.get('log',[])[-3:]
        for i,log in enumerate(reversed(logs)):
            msg=log.get('text','') if isinstance(log,dict) else str(log)
            if len(msg)>38:msg=msg[:37]+'…'
            self.text(24,848+i*23,msg,13,INK if i==0 else MUTED)
        self.text(24,926,'AI 店长实时操作  ·  纯虚拟星币',11,MUTED,anchor='sw')
        self.text(638,926,'F11 全屏',11,MUTED,anchor='se')
        if o.get('phase') in ('won','lost'):
            self.rect(50,300,610,473,'#16283f',GOLD,2)
            self.text(330,324,'小店毕业！' if o['phase']=='won' else '这趟旅程结束了',32,GOLD,True,anchor='n')
            self.text(330,383,f"结余 {o.get('credits',0)} 星币 · 珍藏 {collection} 件",22,INK,anchor='n')
            self.text(330,430,'每一件旧物，都有下一段旅程',17,MUTED,anchor='n')
        if self.error:self.text(330,934,'状态读取中：'+self.error,10,'#ffb3a9',anchor='s',width=600)

    def tick(self):
        try:
            mtime=self.path.stat().st_mtime_ns
            if mtime != self.last_mtime:
                data=json.loads(self.path.read_text())
                if not isinstance(data,dict) or 'credits' not in data:raise ValueError('等待有效游戏状态')
                seq=data.get('last_event',{}).get('seq',data.get('revision'))
                if seq!=self.last_seq:self.event_at=time.monotonic();self.last_seq=seq
                self.obs=data;self.last_mtime=mtime;self.error=None
        except (OSError,ValueError) as exc:self.error='等待游戏状态' if not self.obs else str(exc)[:60]
        self.render()
        self.root.after(80,self.tick)

    def run(self):self.root.mainloop()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='星际旧货铺：只读原生观战画面')
    parser.add_argument('--observation',default=str(Path(__file__).with_name('observation.json')))
    parser.add_argument('--fullscreen',action='store_true')
    a=parser.parse_args()
    Spectator(a.observation,a.fullscreen).run()
