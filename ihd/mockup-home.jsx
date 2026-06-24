import { useState, useEffect } from "react";

/* ── DATA ─────────────────────────────────────────────────────────────────── */

const PC = { Chris:'#c47f0a', Abby:'#c8304c', Max:'#2060b8', Emmie:'#7040b8', Family:'#1e8a50' };

const TODAY_EVENTS = [
  { t:'08:45', title:'School run', who:'Family' },
  { t:'09:30', title:'Grocery delivery', who:'Abby' },
  { t:'15:30', title:'Football training', who:'Max' },
  { t:'17:00', title:'Dance class', who:'Emmie' },
  { t:'19:00', title:'5K easy run', who:'Chris' },
];

const CAL = {
  Mon:[{t:'08:45',title:'School run',who:'Family'},{t:'09:00',title:'WFH all day',who:'Abby'}],
  Tue:[{t:'08:45',title:'School run',who:'Family'},{t:'09:30',title:'Grocery delivery',who:'Abby'},{t:'15:30',title:'Football training',who:'Max'},{t:'17:00',title:'Dance class',who:'Emmie'},{t:'19:00',title:'5K easy run',who:'Chris'}],
  Wed:[{t:'07:00',title:'8K tempo run',who:'Chris'},{t:'08:45',title:'School run',who:'Family'},{t:'17:00',title:'Dance class',who:'Emmie'}],
  Thu:[{t:'08:45',title:'School run',who:'Family'},{t:'10:00',title:'GainAI client call',who:'Chris'}],
  Fri:[{t:'08:45',title:'School run',who:'Family'},{t:'18:00',title:'Family pizza night 🍕',who:'Family'}],
  Sat:[{t:'10:00',title:'Hadley Bricks packing',who:'Chris'},{t:'14:00',title:'Family bike ride 🚴',who:'Family'}],
  Sun:[{t:'08:00',title:'16K long run',who:'Chris'},{t:'13:00',title:'Sunday roast 🥩',who:'Family'}],
};

const MEALS = [
  { day:'Mon', meal:'Pasta Bolognese',     e:'🍝', done:true  },
  { day:'Tue', meal:'Chicken Tikka Masala', e:'🍛', tonight:true },
  { day:'Wed', meal:'Fish & Chips',         e:'🐟' },
  { day:'Thu', meal:'Veggie Stir Fry',      e:'🥦' },
  { day:'Fri', meal:'Homemade Pizza',       e:'🍕' },
  { day:'Sat', meal:'BBQ Chicken',          e:'🍗' },
  { day:'Sun', meal:'Sunday Roast',         e:'🥩' },
];

const INITIAL_TASKS = [
  { text:'Book Shinkansen (Kyoto→Tokyo, Apr 14)', urgent:true,  done:false },
  { text:'Chase Japan travel insurance',          urgent:true,  done:false },
  { text:'Renew car insurance (due 20 Mar)',       urgent:true,  done:false },
  { text:'Phase 8d running spec review',          urgent:false, done:false },
  { text:'Peterbot voice spec — Kokoro TTS test', urgent:false, done:false },
];

const RUNNING_WEEK = [
  { d:'M',  label:'Rest',     km:null, color:null },
  { d:'Tu', label:'5K easy',  km:5,    color:'#72c98e' },
  { d:'W',  label:'8K tempo', km:8,    color:'#f0a830' },
  { d:'Th', label:'Rest',     km:null, color:null },
  { d:'F',  label:'10K',      km:10,   color:'#72c98e' },
  { d:'Sa', label:'Rest',     km:null, color:null },
  { d:'Su', label:'16K long', km:16,   color:'#e87890' },
];

/* ── STYLES ───────────────────────────────────────────────────────────────── */

const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,200;9..144,500&family=Figtree:wght@300;400;500;600;700&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #f5f2eb; --s1: #ffffff; --s2: #f0ece2; --bd: #e0d9cc;
    --a: #c47f0a; --ag: rgba(196,127,10,.08); --ad: #c47f0a;
    --tx: #1a1710; --mid: #7a7060; --dim: #bbb0a0;
    --green: #2a9e5c; --blue: #2e78d0; --rose: #d44868; --pur: #7c52c8;
  }
  html, body, #root { width:100%; height:100%; overflow:hidden; background:var(--bg); color:var(--tx); font-family:'Figtree',sans-serif; }
  .serif { font-family:'Fraunces',serif; font-weight:200; }
  .card { background:var(--s1); border:1px solid var(--bd); border-radius:16px; padding:16px 18px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  .tap  { cursor:pointer; transition:transform .1s, background .15s; }
  .tap:active { transform:scale(.98); background:var(--s2); }
  .page { animation:fi .2s ease both; height:100%; }
  @keyframes fi { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
  .nb { flex:1; display:flex; flex-direction:column; align-items:center; gap:3px; padding:10px 8px 12px; border:none; background:transparent; color:var(--dim); cursor:pointer; font-family:'Figtree',sans-serif; font-size:11px; font-weight:500; border-top:2px solid transparent; transition:color .2s, border-color .2s; }
  .nb.on { color:var(--a); border-top-color:var(--a); }
  .nb:active { opacity:.7; }
  ::-webkit-scrollbar { width:3px; }
  ::-webkit-scrollbar-thumb { background:var(--bd); border-radius:3px; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }
  @keyframes glow  { 0%,100%{box-shadow:0 0 6px var(--green)} 50%{box-shadow:0 0 14px var(--green)} }
`;

/* ── HELPERS ──────────────────────────────────────────────────────────────── */

const japanDays = () => Math.ceil((new Date('2026-04-03') - new Date()) / 864e5);

function Pill({ who }) {
  const c = PC[who] || '#888';
  return <span style={{display:'inline-block',padding:'2px 8px',borderRadius:20,fontSize:10,fontWeight:700,letterSpacing:'0.05em',textTransform:'uppercase',background:c+'22',color:c,border:`1px solid ${c}44`}}>{who}</span>;
}

function H({ children }) {
  return <div style={{fontSize:10,fontWeight:700,letterSpacing:'0.12em',textTransform:'uppercase',color:'var(--mid)',marginBottom:10}}>{children}</div>;
}

/* ── HOME PAGE ────────────────────────────────────────────────────────────── */

function HomePage() {
  const now = new Date();
  const mins = now.getHours() * 60 + now.getMinutes();
  const days = japanDays();

  return (
    <div className="page" style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gridTemplateRows:'1fr 1fr',gap:12,padding:'12px 0 0'}}>

      {/* Events — spans 2 rows */}
      <div className="card" style={{gridRow:'span 2',display:'flex',flexDirection:'column'}}>
        <H>Today's Events</H>
        <div style={{flex:1,overflowY:'auto',display:'flex',flexDirection:'column',gap:10}}>
          {TODAY_EVENTS.map((ev,i) => {
            const [h,m] = ev.t.split(':').map(Number);
            const past = (h*60+m) < mins;
            return (
              <div key={i} style={{display:'flex',gap:10,alignItems:'flex-start',opacity:past?.4:1}}>
                <div style={{fontSize:13,fontWeight:600,color:'var(--mid)',minWidth:36,paddingTop:1,textDecoration:past?'line-through':'none'}}>{ev.t}</div>
                <div>
                  <div style={{fontSize:14,fontWeight:500,marginBottom:4}}>{ev.title}</div>
                  <Pill who={ev.who}/>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Dinner */}
      <div className="card" style={{display:'flex',flexDirection:'column',gap:8}}>
        <H>Tonight's Dinner</H>
        <div style={{display:'flex',alignItems:'center',gap:14,flex:1}}>
          <span style={{fontSize:42}}>🍛</span>
          <div>
            <div style={{fontSize:17,fontWeight:700}}>Chicken Tikka Masala</div>
            <div style={{fontSize:12,color:'var(--mid)',marginTop:4}}>Prep 20 min · Cook 30 min · Serves 4</div>
            <div style={{fontSize:11,color:'var(--a)',marginTop:6,fontWeight:600}}>⚡ Marinate chicken from 5pm</div>
          </div>
        </div>
      </div>

      {/* Japan countdown */}
      <div className="card" style={{background:'var(--s1)',borderColor:'var(--ad)',display:'flex',flexDirection:'column',justifyContent:'space-between'}}>
        <H>Japan Trip</H>
        <div style={{display:'flex',alignItems:'baseline',gap:8}}>
          <span className="serif" style={{fontSize:58,color:'var(--a)',lineHeight:1}}>{days}</span>
          <span style={{fontSize:14,color:'var(--mid)'}}>days to go</span>
        </div>
        <div>
          <div style={{fontSize:12,fontWeight:500}}>✈️  Departs 3 April 2026</div>
          <div style={{fontSize:11,color:'var(--mid)',marginTop:2}}>Tokyo · Osaka · Kyoto · Tokyo</div>
          <div style={{marginTop:8,display:'inline-block',fontSize:11,fontWeight:700,color:'var(--rose)',background:'rgba(232,120,144,.12)',padding:'3px 10px',borderRadius:8}}>⚠️ Shinkansen not booked!</div>
        </div>
      </div>

      {/* Sensor */}
      <div className="card">
        <H>Kitchen Sensor</H>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
          {[{l:'Temp',v:'19.4',u:'°C',c:'var(--a)'},{l:'Humidity',v:'58',u:'%',c:'var(--blue)'}].map(s=>(
            <div key={s.l} style={{textAlign:'center',padding:'10px 8px',background:'var(--s2)',borderRadius:10}}>
              <div style={{fontSize:24,fontWeight:700,color:s.c,fontFamily:"'Fraunces',serif",fontWeight:200}}>{s.v}<span style={{fontSize:13}}>{s.u}</span></div>
              <div style={{fontSize:10,color:'var(--mid)',marginTop:2,textTransform:'uppercase',letterSpacing:'0.08em'}}>{s.l}</div>
            </div>
          ))}
        </div>
        <div style={{marginTop:10,display:'flex',alignItems:'center',gap:6}}>
          <div style={{width:8,height:8,borderRadius:'50%',background:'var(--green)',animation:'glow 2s ease-in-out infinite'}}/>
          <span style={{fontSize:11,color:'var(--mid)'}}>Sonoff plug online · LQI 232</span>
        </div>
      </div>

      {/* Hadley quick stats */}
      <div className="card">
        <H>Hadley Bricks — Today</H>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10,marginBottom:10}}>
          {[{l:'Orders',v:'7',c:'var(--green)'},{l:'Revenue',v:'£142.50',c:'var(--a)'}].map(s=>(
            <div key={s.l} style={{textAlign:'center',padding:'10px 8px',background:'var(--s2)',borderRadius:10}}>
              <div style={{fontSize:20,fontWeight:700,color:s.c}}>{s.v}</div>
              <div style={{fontSize:10,color:'var(--mid)',marginTop:2,textTransform:'uppercase',letterSpacing:'0.08em'}}>{s.l}</div>
            </div>
          ))}
        </div>
        <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
          {[{n:'eBay',v:4},{n:'Amazon',v:2},{n:'BrickLink',v:1}].map(p=>(
            <span key={p.n} style={{fontSize:11,color:'var(--mid)',background:'var(--s2)',padding:'2px 8px',borderRadius:8}}>{p.n} {p.v}</span>
          ))}
          <span style={{fontSize:11,color:'var(--rose)',background:'rgba(232,120,144,.1)',padding:'2px 8px',borderRadius:8}}>2 offers pending</span>
        </div>
      </div>

    </div>
  );
}

/* ── CALENDAR PAGE ────────────────────────────────────────────────────────── */

function CalendarPage() {
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const dates = [9,10,11,12,13,14,15];
  const todayAbbr = new Date().toLocaleDateString('en-GB',{weekday:'short'});

  return (
    <div className="page" style={{padding:'12px 0 0'}}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:8,height:'100%'}}>
        {days.map((day,i)=>{
          const isToday = todayAbbr.startsWith(day.slice(0,3));
          const events = CAL[day]||[];
          return (
            <div key={day} className="card" style={{display:'flex',flexDirection:'column',gap:6,borderColor:isToday?'var(--a)':'var(--bd)',background:isToday?`linear-gradient(180deg,var(--s1),var(--ag))`:'var(--s1)'}}>
              <div style={{textAlign:'center',paddingBottom:4,borderBottom:'1px solid var(--bd)'}}>
                <div style={{fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:isToday?'var(--a)':'var(--mid)',fontWeight:700}}>{day}</div>
                <div className="serif" style={{fontSize:28,color:isToday?'var(--a)':'var(--tx)',lineHeight:1.2}}>{dates[i]}</div>
              </div>
              <div style={{flex:1,overflowY:'auto',display:'flex',flexDirection:'column',gap:5}}>
                {events.map((ev,j)=>(
                  <div key={j} style={{padding:'4px 7px',borderRadius:7,background:PC[ev.who]+'18',borderLeft:`2px solid ${PC[ev.who]}`}}>
                    <div style={{fontSize:10,fontWeight:600,color:PC[ev.who]}}>{ev.t}</div>
                    <div style={{fontSize:11,color:'var(--tx)',lineHeight:1.3}}>{ev.title}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── MEALS PAGE ───────────────────────────────────────────────────────────── */

function MealsPage() {
  return (
    <div className="page" style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:12,padding:'12px 0 0'}}>

      <div className="card" style={{display:'flex',flexDirection:'column'}}>
        <H>This Week's Meals</H>
        <div style={{flex:1,display:'flex',flexDirection:'column',gap:8,overflowY:'auto'}}>
          {MEALS.map((m,i)=>(
            <div key={i} style={{display:'flex',alignItems:'center',gap:12,padding:'10px 14px',borderRadius:10,background:m.tonight?'var(--ag)':m.done?'transparent':'var(--s2)',border:m.tonight?'1px solid var(--ad)':'1px solid transparent',opacity:m.done?.45:1}}>
              <span style={{fontSize:26,minWidth:32,textAlign:'center'}}>{m.e}</span>
              <div style={{flex:1}}>
                <div style={{fontSize:14,fontWeight:m.tonight?700:500,color:m.tonight?'var(--a)':'var(--tx)'}}>{m.meal}</div>
                <div style={{fontSize:11,color:'var(--mid)'}}>{m.day}</div>
              </div>
              {m.tonight && <span style={{fontSize:11,fontWeight:700,color:'var(--a)',background:'var(--ag)',padding:'3px 10px',borderRadius:12,border:'1px solid var(--ad)'}}>TONIGHT</span>}
              {m.done && <span style={{fontSize:18,color:'var(--green)'}}>✓</span>}
            </div>
          ))}
        </div>
      </div>

      <div style={{display:'flex',flexDirection:'column',gap:12}}>
        <div className="card" style={{background:'var(--s2)',borderColor:'var(--ad)',flex:1}}>
          <H>Tonight's Recipe</H>
          <div style={{fontSize:42,marginBottom:10}}>🍛</div>
          <div style={{fontSize:18,fontWeight:700,marginBottom:4}}>Chicken Tikka Masala</div>
          <div style={{display:'flex',flexDirection:'column',gap:6,marginTop:12}}>
            {[{i:'⏱️',t:'Prep: 20 min'},{i:'🔥',t:'Cook: 30 min'},{i:'👨‍👩‍👧‍👦',t:'Serves: 4'}].map(r=>(
              <div key={r.t} style={{display:'flex',gap:8,fontSize:13,color:'var(--mid)'}}><span>{r.i}</span><span>{r.t}</span></div>
            ))}
          </div>
          <div style={{marginTop:14,padding:'10px 12px',background:'rgba(240,168,48,.08)',borderRadius:10,border:'1px solid var(--ad)'}}>
            <div style={{fontSize:10,fontWeight:700,color:'var(--a)',marginBottom:4,letterSpacing:'0.1em'}}>PREP NOTE</div>
            <div style={{fontSize:12}}>Marinate chicken from 5pm for best results</div>
          </div>
        </div>

        <div className="card">
          <H>Week Summary</H>
          {[{l:'Planned',v:'7/7',c:'var(--green)'},{l:'Sourced',v:'5/7',c:'var(--a)'},{l:'Leftovers',v:'Mon night',c:'var(--mid)'}].map(r=>(
            <div key={r.l} style={{display:'flex',justifyContent:'space-between',fontSize:12,padding:'6px 0',borderBottom:'1px solid var(--bd)'}}>
              <span style={{color:'var(--mid)'}}>{r.l}</span>
              <span style={{color:r.c,fontWeight:600}}>{r.v}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

/* ── CONTROL PAGE ─────────────────────────────────────────────────────────── */

function ControlPage() {
  const [plug, setPlug] = useState(true);
  return (
    <div className="page" style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gridTemplateRows:'1fr 1fr',gap:12,padding:'12px 0 0'}}>

      {/* Smart plug — full height */}
      <div className="card tap" onClick={()=>setPlug(p=>!p)} style={{gridRow:'span 2',display:'flex',flexDirection:'column',justifyContent:'space-between',borderColor:plug?'var(--green)':'var(--bd)',background:plug?'linear-gradient(180deg,var(--s1),rgba(42,158,92,.05))':'var(--s1)',cursor:'pointer'}}>
        <H>Smart Plug</H>
        <div style={{textAlign:'center',padding:'24px 0'}}>
          <div style={{width:88,height:88,borderRadius:'50%',margin:'0 auto 16px',display:'flex',alignItems:'center',justifyContent:'center',background:plug?'rgba(114,201,142,.15)':'var(--s2)',border:`3px solid ${plug?'var(--green)':'var(--dim)'}`,fontSize:36,boxShadow:plug?'0 0 28px rgba(114,201,142,.25)':'none',transition:'all 0.3s'}}>⚡</div>
          <div style={{fontSize:26,fontWeight:700,color:plug?'var(--green)':'var(--dim)',transition:'color 0.3s'}}>{plug?'ON':'OFF'}</div>
          <div style={{fontSize:12,color:'var(--mid)',marginTop:4}}>Sonoff S60ZBTPG</div>
        </div>
        <div style={{textAlign:'center',fontSize:12,color:'var(--mid)',paddingBottom:8}}>{plug?'🔌 Drawing power':'💤 Standby'}</div>
      </div>

      {/* BME280 */}
      <div className="card" style={{display:'flex',flexDirection:'column',gap:8}}>
        <H>BME280 Sensor</H>
        {[{l:'Temperature',v:'19.4°C',c:'var(--a)',i:'🌡️'},{l:'Humidity',v:'58%',c:'var(--blue)',i:'💧'},{l:'Pressure',v:'1013 hPa',c:'var(--mid)',i:'🌀'}].map(s=>(
          <div key={s.l} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 10px',background:'var(--s2)',borderRadius:10}}>
            <span style={{fontSize:20}}>{s.i}</span>
            <div style={{flex:1}}>
              <div style={{fontSize:10,color:'var(--mid)'}}>{s.l}</div>
              <div style={{fontSize:16,fontWeight:700,color:s.c}}>{s.v}</div>
            </div>
          </div>
        ))}
      </div>

      {/* BH1750 */}
      <div className="card" style={{display:'flex',flexDirection:'column',gap:10}}>
        <H>BH1750 Light Sensor</H>
        <div style={{padding:'14px',background:'var(--s2)',borderRadius:10,textAlign:'center'}}>
          <div style={{fontSize:30,fontWeight:200,fontFamily:"'Fraunces',serif",color:'var(--a)'}}>420 <span style={{fontSize:14}}>lux</span></div>
          <div style={{fontSize:11,color:'var(--mid)',marginTop:2}}>Bright indoor</div>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:8,fontSize:12,color:'var(--mid)'}}>
          <span style={{whiteSpace:'nowrap'}}>Brightness</span>
          <div style={{flex:1,height:5,background:'var(--bd)',borderRadius:5}}><div style={{width:'80%',height:'100%',background:'var(--a)',borderRadius:5}}/></div>
          <span style={{color:'var(--a)',fontWeight:600}}>80%</span>
        </div>
      </div>

      {/* PIR */}
      <div className="card">
        <H>PIR Motion Sensor</H>
        <div style={{display:'flex',flexDirection:'column',gap:6}}>
          {[{l:'HC-SR501 · GPIO17',s:'Not yet wired',ok:false},{l:'Screen wake/sleep',s:'Pending PIR',ok:false}].map((r,i)=>(
            <div key={i} style={{display:'flex',alignItems:'center',gap:10,padding:'8px',background:'var(--s2)',borderRadius:8}}>
              <div style={{width:8,height:8,borderRadius:'50%',background:'var(--dim)',flexShrink:0}}/>
              <div>
                <div style={{fontSize:11,color:'var(--dim)',fontWeight:500}}>{r.s}</div>
                <div style={{fontSize:10,color:'var(--dim)'}}>{r.l}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Zigbee */}
      <div className="card">
        <H>Zigbee Network</H>
        <div style={{display:'flex',flexDirection:'column',gap:6}}>
          <div style={{padding:'8px',background:'var(--s2)',borderRadius:8,display:'flex',alignItems:'center',gap:8}}>
            <div style={{width:8,height:8,borderRadius:'50%',background:'var(--green)',animation:'glow 2s ease-in-out infinite',flexShrink:0}}/>
            <div style={{flex:1}}>
              <div style={{fontSize:12,fontWeight:500}}>Sonoff S60ZBTPG</div>
              <div style={{fontSize:10,color:'var(--mid)'}}>Router · LQI 232 · /dev/ttyUSB0</div>
            </div>
          </div>
          {['Candeo PIR (hallway)','Candeo door contact'].map(d=>(
            <div key={d} style={{padding:'8px',background:'var(--s2)',borderRadius:8,display:'flex',alignItems:'center',gap:8,opacity:.4}}>
              <div style={{width:8,height:8,borderRadius:'50%',background:'var(--dim)',flexShrink:0}}/>
              <div style={{fontSize:11,color:'var(--dim)',fontStyle:'italic'}}>{d} — planned</div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

/* ── CHRIS PAGE ───────────────────────────────────────────────────────────── */

function ChrisPage() {
  const [tasks, setTasks] = useState(INITIAL_TASKS);
  const toggle = i => setTasks(ts => ts.map((t,j)=>j===i?{...t,done:!t.done}:t));

  return (
    <div className="page" style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gridTemplateRows:'1fr 1fr',gap:12,padding:'12px 0 0'}}>

      {/* Tasks — spans 2 rows */}
      <div className="card" style={{gridRow:'span 2',display:'flex',flexDirection:'column'}}>
        <H>Peter — Tasks</H>
        <div style={{flex:1,overflowY:'auto',display:'flex',flexDirection:'column',gap:8}}>
          {tasks.map((t,i)=>(
            <div key={i} className="tap" onClick={()=>toggle(i)} style={{display:'flex',alignItems:'flex-start',gap:10,padding:'10px 12px',borderRadius:10,background:'var(--s2)',opacity:t.done?.4:1,borderLeft:t.urgent&&!t.done?'3px solid var(--rose)':'3px solid transparent'}}>
              <div style={{width:20,height:20,borderRadius:6,flexShrink:0,marginTop:1,border:t.done?'none':`2px solid ${t.urgent?'var(--rose)':'var(--bd)'}`,background:t.done?'var(--green)':'transparent',display:'flex',alignItems:'center',justifyContent:'center',color:'var(--bg)',fontSize:12,fontWeight:700}}>{t.done&&'✓'}</div>
              <div style={{flex:1}}>
                <div style={{fontSize:13,fontWeight:500,textDecoration:t.done?'line-through':'none'}}>{t.text}</div>
                {t.urgent&&!t.done&&<span style={{fontSize:10,color:'var(--rose)',fontWeight:700,marginTop:3,display:'block'}}>URGENT</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Hadley stats */}
      <div className="card">
        <H>Hadley Bricks — Today</H>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:10}}>
          {[{l:'Orders',v:'7',c:'var(--green)'},{l:'Revenue',v:'£142',c:'var(--a)'},{l:'Wk orders',v:'34',c:'var(--blue)'},{l:'Wk revenue',v:'£687',c:'var(--a)'}].map(s=>(
            <div key={s.l} style={{textAlign:'center',padding:'10px 8px',background:'var(--s2)',borderRadius:10}}>
              <div style={{fontSize:20,fontWeight:700,color:s.c}}>{s.v}</div>
              <div style={{fontSize:10,color:'var(--mid)',marginTop:2}}>{s.l}</div>
            </div>
          ))}
        </div>
        <div style={{display:'flex',gap:6}}>
          <span style={{fontSize:11,color:'var(--rose)',background:'rgba(232,120,144,.1)',padding:'2px 8px',borderRadius:8}}>2 offers</span>
          <span style={{fontSize:11,color:'var(--a)',background:'var(--ag)',padding:'2px 8px',borderRadius:8}}>1 low stock</span>
        </div>
      </div>

      {/* Running */}
      <div className="card">
        <H>Running — This Week</H>
        <div style={{display:'flex',gap:4,justifyContent:'space-between',marginBottom:12}}>
          {RUNNING_WEEK.map((r,i)=>(
            <div key={i} style={{flex:1,textAlign:'center'}}>
              <div style={{padding:'6px 2px',borderRadius:8,marginBottom:4,background:r.km?r.color+'22':'var(--s2)',border:`1px solid ${r.km?r.color+'44':'transparent'}`}}>
                <div style={{fontSize:11,fontWeight:700,color:r.km?r.color:'var(--dim)'}}>{r.d}</div>
                {r.km&&<div style={{fontSize:10,color:r.color,fontWeight:600,marginTop:2}}>{r.km}K</div>}
              </div>
              {!r.km&&<div style={{fontSize:9,color:'var(--dim)'}}>—</div>}
            </div>
          ))}
        </div>
        <div style={{borderTop:'1px solid var(--bd)',paddingTop:8,display:'flex',flexDirection:'column',gap:4}}>
          {[{l:'Weekly target',v:'39K',c:'var(--a)'},{l:'Next race',v:'Amsterdam Oct 2026',c:'var(--mid)'}].map(r=>(
            <div key={r.l} style={{display:'flex',justifyContent:'space-between',fontSize:12}}>
              <span style={{color:'var(--mid)'}}>{r.l}</span>
              <span style={{color:r.c,fontWeight:600}}>{r.v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hadley platforms */}
      <div className="card">
        <H>Platform Breakdown</H>
        <div style={{display:'flex',flexDirection:'column',gap:7}}>
          {[{n:'eBay',o:4,r:89.50,c:'#e07820'},{n:'Amazon',o:2,r:41.00,c:'#f0a830'},{n:'BrickLink',o:1,r:12.00,c:'#6ea8f0'},{n:'Brick Owl',o:0,r:0,c:'#72c98e'}].map(p=>(
            <div key={p.n} style={{display:'flex',alignItems:'center',gap:8}}>
              <div style={{width:3,height:28,borderRadius:2,background:p.c,flexShrink:0}}/>
              <div style={{flex:1,fontSize:13,fontWeight:500}}>{p.n}</div>
              <div style={{fontSize:12,color:'var(--mid)'}}>{p.o} orders</div>
              <div style={{fontSize:13,fontWeight:700,color:p.o>0?'var(--a)':'var(--dim)',minWidth:52,textAlign:'right'}}>£{p.r.toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Peterbot status */}
      <div className="card">
        <H>Peterbot Build</H>
        <div style={{display:'flex',flexDirection:'column',gap:4}}>
          {[
            {l:'Ph 8a–8c (Calendar/Finance/Home)',v:'✓ Done',c:'var(--green)'},
            {l:'Ph 8d — Running',v:'◐ Spec ready',c:'var(--a)'},
            {l:'Ph 8e–8g',v:'○ Pending',c:'var(--dim)'},
            {l:'Voice (Kokoro TTS)',v:'◐ Designed',c:'var(--a)'},
            {l:'Memory / 2nd Brain',v:'✓ Active',c:'var(--green)'},
          ].map(s=>(
            <div key={s.l} style={{display:'flex',justifyContent:'space-between',fontSize:11,padding:'5px 0',borderBottom:'1px solid var(--bd)'}}>
              <span style={{color:'var(--mid)'}}>{s.l}</span>
              <span style={{color:s.c,fontWeight:600,marginLeft:8,whiteSpace:'nowrap'}}>{s.v}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

/* ── MAIN DASHBOARD ───────────────────────────────────────────────────────── */

const NAV = [
  {id:'home',     icon:'🏠', label:'Home'},
  {id:'calendar', icon:'📅', label:'Calendar'},
  {id:'meals',    icon:'🍽', label:'Meals'},
  {id:'control',  icon:'💡', label:'Control'},
  {id:'chris',    icon:'📊', label:'Chris'},
];

export default function Dashboard() {
  const [now, setNow] = useState(new Date());
  const [page, setPage] = useState('home');

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const H2 = now.getHours().toString().padStart(2,'0');
  const M2 = now.getMinutes().toString().padStart(2,'0');
  const S2 = now.getSeconds().toString().padStart(2,'0');
  const dayStr  = now.toLocaleDateString('en-GB',{weekday:'long'});
  const dateStr = now.toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'});

  return (
    <>
      <style>{STYLES}</style>
      <div style={{width:'100vw',height:'100vh',display:'flex',flexDirection:'column',overflow:'hidden'}}>

        {/* Header */}
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'12px 24px 10px',borderBottom:'1px solid var(--bd)',background:'var(--s1)',flexShrink:0}}>
          {/* Clock */}
          <div style={{display:'flex',alignItems:'baseline',gap:6}}>
            <span className="serif" style={{fontSize:54,lineHeight:1,letterSpacing:'-0.01em'}}>
              {H2}<span style={{opacity:.4,animation:'blink 1s step-end infinite'}}>:</span>{M2}
            </span>
            <span style={{fontSize:16,color:'var(--mid)',fontWeight:300,marginLeft:4}}>{S2}</span>
          </div>
          {/* Date */}
          <div style={{textAlign:'center'}}>
            <div style={{fontSize:16,fontWeight:600}}>{dayStr}</div>
            <div style={{fontSize:12,color:'var(--mid)',marginTop:2}}>{dateStr}</div>
          </div>
          {/* Weather */}
          <div style={{display:'flex',alignItems:'center',gap:10}}>
            <span style={{fontSize:30}}>⛅</span>
            <div>
              <div style={{display:'flex',alignItems:'baseline',gap:4}}>
                <span className="serif" style={{fontSize:38,lineHeight:1}}>11°</span>
                <span style={{fontSize:13,color:'var(--mid)'}}>C</span>
              </div>
              <div style={{fontSize:11,color:'var(--mid)',marginTop:1}}>Tonbridge · Feels 8° · 20% rain</div>
            </div>
          </div>
        </div>

        {/* Page content */}
        <div style={{flex:1,overflow:'hidden',padding:'0 20px'}}>
          {page==='home'     && <HomePage/>}
          {page==='calendar' && <CalendarPage/>}
          {page==='meals'    && <MealsPage/>}
          {page==='control'  && <ControlPage/>}
          {page==='chris'    && <ChrisPage/>}
        </div>

        {/* Bottom nav */}
        <div style={{display:'flex',borderTop:'1px solid var(--bd)',background:'var(--s1)',flexShrink:0}}>
          {NAV.map(n=>(
            <button key={n.id} className={`nb${page===n.id?' on':''}`} onClick={()=>setPage(n.id)}>
              <span style={{fontSize:20}}>{n.icon}</span>
              <span>{n.label}</span>
            </button>
          ))}
        </div>

      </div>
    </>
  );
}
