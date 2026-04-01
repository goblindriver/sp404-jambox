#!/usr/bin/env python3
"""Generate novelty/fun sounds for SP-404 Bank B"""
import numpy as np, wave, os

SR = 44100
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
OUT = os.path.join(REPO_DIR, "_BANK_B_STAGING")
os.makedirs(OUT, exist_ok=True)

def save_wav(filename, data):
    data = np.clip(data, -1.0, 1.0)
    samples = (data * 32767).astype(np.int16)
    with wave.open(os.path.join(OUT, filename), 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(samples.tobytes())
    print(f"  {filename} ({len(data)/SR:.2f}s)")

def sine(freq, n): return np.sin(2*np.pi*freq*np.arange(n)/SR)
def saw(freq, n): return 2.0*(freq*np.arange(n)/SR % 1.0)-1.0
def square(freq, n): return np.sign(sine(freq, n))
def noise(n): return np.random.uniform(-1,1,n)
def norm(s, lv=0.95): mx=np.max(np.abs(s)); return s*(lv/mx) if mx>0 else s
def sat(s, a=2.0): return np.tanh(s*a)/np.tanh(a)

def lp(sig, cutoff):
    rc=1.0/(2*np.pi*cutoff); dt=1.0/SR; a=dt/(rc+dt)
    out=np.zeros_like(sig); out[0]=sig[0]
    for i in range(1,len(sig)): out[i]=out[i-1]+a*(sig[i]-out[i-1])
    return out

def adsr(n, a, d, s, r):
    env=np.zeros(n); a_s=int(a*SR); d_s=int(d*SR); r_s=int(r*SR)
    sus_s=max(0,n-a_s-d_s-r_s); p=0
    if a_s>0: env[p:p+a_s]=np.linspace(0,1,a_s); p+=a_s
    if d_s>0: env[p:p+d_s]=np.linspace(1,s,d_s); p+=d_s
    env[p:p+sus_s]=s; p+=sus_s
    if r_s>0 and p+r_s<=n: env[p:p+r_s]=np.linspace(s,0,r_s)
    return env

print("=== Bank B: Novelty Sounds ===")

# 1. AIR HORN
n=int(SR*1.5); t=np.arange(n)/SR
freq=np.full(n, 520.0); freq[:int(SR*0.05)]=np.linspace(400,520,int(SR*0.05))
phase=np.cumsum(freq/SR)
horn=sum(np.sin(2*np.pi*phase*(1+d/1000)) for d in [-3,-1,0,1,3])
horn+=sum(0.5*np.sin(2*np.pi*phase*2*(1+d/500)) for d in [-2,0,2])
horn*=adsr(n,0.01,0.1,0.9,0.3); horn=sat(horn,3.0); horn=lp(horn,3000)
save_wav("01_air_horn.wav", norm(horn))

# 2. RECORD SCRATCH
n=int(SR*0.8); t=np.arange(n)/SR
sf=np.concatenate([np.linspace(2000,200,int(SR*0.15)),np.linspace(200,3000,int(SR*0.1)),
    np.linspace(3000,100,int(SR*0.15)),np.linspace(100,1500,int(SR*0.1)),np.zeros(int(SR*0.3))])[:n]
sp=np.cumsum(sf/SR); scr=np.sin(2*np.pi*sp)*0.6+noise(n)*0.4
scr*=adsr(n,0.001,0.05,0.5,0.2); scr=lp(scr,4000)
crk=noise(n)*0.05; crk*=(np.random.random(n)>0.97).astype(float)*5
save_wav("02_record_scratch.wav", norm(scr+crk))

# 3. LASER ZAP
n=int(SR*0.6); t=np.arange(n)/SR
lf=3000*np.exp(-8*t); lph=np.cumsum(lf/SR)
las=np.sin(2*np.pi*lph)+0.3*np.sin(2*np.pi*lph*1.5)
las*=np.exp(-5*t)
save_wav("03_laser_zap.wav", norm(las))

# 4. ROBOT VOICE "YEAH"
n=int(SR*0.8); t=np.arange(n)/SR
car=saw(120,n)
f1=np.concatenate([np.linspace(300,600,n//3),np.linspace(600,700,n//3),np.linspace(700,800,n-2*(n//3))])
f2=np.concatenate([np.linspace(2200,1800,n//3),np.linspace(1800,1200,n//3),np.linspace(1200,1100,n-2*(n//3))])
voice=car*(np.sin(2*np.pi*f1*t[:,None] if False else np.array([np.sin(2*np.pi*f1[i]*t[i]) for i in range(n)]))+
    0.7*np.array([np.sin(2*np.pi*f2[i]*t[i]) for i in range(n)]))
voice*=adsr(n,0.02,0.1,0.7,0.2); voice=sat(voice,1.5)
save_wav("04_robot_yeah.wav", norm(voice))

# 5. SIREN WHOOP
n=int(SR*1.2); t=np.arange(n)/SR
sf=600+400*np.sin(2*np.pi*3*t); sp=np.cumsum(sf/SR)
sir=np.sin(2*np.pi*sp)+0.3*np.sin(2*np.pi*sp*2)
sir*=adsr(n,0.05,0.1,0.8,0.3)
save_wav("05_siren_whoop.wav", norm(sir))

# 6. 8-BIT COIN POWER-UP
n=int(SR*0.4); t=np.arange(n)/SR
coin=np.zeros(n); notes=[880,1047,1319,1568,2093]
nl=n//len(notes)
for i,f in enumerate(notes):
    s,e=i*nl,min((i+1)*nl,n); st=np.arange(e-s)/SR
    coin[s:e]=np.sign(sine(f,e-s))*0.7*np.exp(-8*st)
coin=np.round(coin*8)/8
save_wav("06_8bit_powerup.wav", norm(coin))

# 7. VINYL STOP
n=int(SR*1.5); t=np.arange(n)/SR
speed=np.exp(-3*t); vs=np.zeros(n)
for f in [220,277,330,440]:
    ph=np.cumsum(speed*f/SR); vs+=np.sin(2*np.pi*ph)
vs*=adsr(n,0.001,0.05,0.9,0.3); vs=lp(vs,2000); vs=sat(vs,2)
save_wav("07_vinyl_stop.wav", norm(vs))

# 8. TAPE REWIND
n=int(SR*1.0); t=np.arange(n)/SR
speed=np.exp(4*t); rn=noise(n)
rew=np.zeros(n)
for i in range(1,n): rew[i]=rn[i]-rn[i-1]
rew*=np.linspace(0.3,1.0,n)
wf=500*speed/speed[-1]*4; wp=np.cumsum(wf/SR)
rew+=0.3*np.sin(2*np.pi*wp)*np.linspace(0,1,n)
rew*=adsr(n,0.05,0.05,0.9,0.1)
save_wav("08_tape_rewind.wav", norm(rew))

# 9. ROBOT "OK"
n=int(SR*0.5); t=np.arange(n)/SR
car=saw(100,n)
f1=np.concatenate([np.full(n//2,400),np.full(n-n//2,300)])
f2=np.concatenate([np.full(n//2,800),np.full(n-n//2,2500)])
ok=np.array([car[i]*(np.sin(2*np.pi*f1[i]*t[i])+0.5*np.sin(2*np.pi*f2[i]*t[i])) for i in range(n)])
kb=noise(int(SR*0.05))*0.4*np.exp(-30*np.arange(int(SR*0.05))/SR)
ks=n//2; ok[ks:ks+len(kb)]+=kb
ok*=adsr(n,0.02,0.05,0.7,0.15); ok=sat(ok,1.5)
save_wav("09_robot_ok.wav", norm(ok))

# 10. DJ HORN STAB
n=int(SR*0.3); t=np.arange(n)/SR
stab=sum(saw(f,n) for f in [440,554,659,880])
stab*=adsr(n,0.005,0.05,0.6,0.1); stab=lp(stab,2500); stab=sat(stab,2.5)
save_wav("10_horn_stab.wav", norm(stab))

# 11. RISER BUILD-UP
n=int(SR*3.0); t=np.arange(n)/SR
rf=100*np.exp(3*t/t[-1]); rp=np.cumsum(rf/SR)
ris=np.sin(2*np.pi*rp)+0.5*noise(n)*np.linspace(0,1,n)
ris*=np.linspace(0.1,1.0,n)
pf=np.linspace(2,16,n); pulse=0.5+0.5*np.sin(2*np.pi*np.cumsum(pf/SR))
ris*=pulse
save_wav("11_riser_buildup.wav", norm(ris))

# 12. IMPACT DROP
n=int(SR*1.5); t=np.arange(n)/SR
df=200*np.exp(-5*t)+30; dp=np.cumsum(df/SR)
imp=np.sin(2*np.pi*dp)*np.exp(-2*t)
burst=noise(int(SR*0.05))*np.exp(-40*np.arange(int(SR*0.05))/SR)*2
imp[:len(burst)]+=burst; imp=sat(imp,3); imp*=adsr(n,0.001,0.1,0.5,0.5)
save_wav("12_impact_drop.wav", norm(imp))

print(f"\nDone! {len(os.listdir(OUT))} files ready")
