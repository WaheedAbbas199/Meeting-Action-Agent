"""Optional accessibility audit: npm i axe-core && AXE_JS=node_modules/axe-core/axe.min.js python e2e/axe_audit.py (run from backend/)."""
import os, sys, subprocess, tempfile, time, socket, httpx, json
from playwright.sync_api import sync_playwright
s=socket.socket(); s.bind(("127.0.0.1",0)); port=s.getsockname()[1]; s.close(); tmp=tempfile.mkdtemp()
env={**os.environ,"APP_ENV":"development","DATABASE_URL":f"sqlite:///{tmp}/d.db","JWT_SECRET":"x"*40,"EMAIL_PROVIDER":"mock","WHATSAPP_PROVIDER":"mock","RUN_WORKER":"false","LOG_JSON":"false"}
subprocess.run([sys.executable,"-m","app.seed"],env=env,check=True,capture_output=True)
pr=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--port",str(port),"--log-level","warning"],env=env)
url=f"http://127.0.0.1:{port}"
for _ in range(100):
    try:
        if httpx.get(url+"/api/health",timeout=1).status_code==200: break
    except Exception: time.sleep(.2)
r=httpx.post(url+"/api/auth/login",json={"email":"demo@example.com","password":"demo-password-123"}).json()
axe=open(os.environ.get("AXE_JS","node_modules/axe-core/axe.min.js")).read()
routes=["dashboard","meetings","meetings/1","tasks","risks","decisions","planner","memory","workload","followups","approvals","analytics","settings","settings?tab=team","settings?tab=integrations","settings?tab=contacts"]
bad={}
with sync_playwright() as p:
    b=p.chromium.launch()
    for theme in ("light","dark"):
        ctx=b.new_context(viewport={"width":1280,"height":900},bypass_csp=True); pg=ctx.new_page()
        pg.goto(url+"/#/login"); pg.evaluate("(a)=>{sessionStorage.setItem('maa.token',a.t);sessionStorage.setItem('maa.wid',a.w);localStorage.setItem('maa.theme',a.th)}",{"t":r["token"],"w":str(r["workspaces"][0]["id"]),"th":theme}); pg.reload()
        for route in routes:
            pg.goto(url+"/#/"+route); pg.wait_for_selector(".shell"); pg.wait_for_load_state("networkidle"); time.sleep(0.7)
            pg.add_script_tag(content=axe)
            res=pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})")
            for v in res["violations"]:
                key=(theme,route,v["id"],v["impact"]); bad[key]=[n["target"] for n in v["nodes"]][:3]
        ctx.close()
    b.close()
pr.terminate()
for k,v in bad.items(): print(k, v)
print("violations:",len(bad))
