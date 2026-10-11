"""Dashboard page (HTML/CSS/JS served at /). One self-contained file, no external assets."""
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect width='24' height='24' rx='6' fill='%234f46e5'/%3E%3Cpath d='M13 3L5.5 13.5h5.5l-1 7.5 7.5-10.5H12z' fill='%23fff'/%3E%3C/svg%3E">
<title>Autopost</title>
<style>
:root{--bg:#0b0e14;--side:#090c12;--card:#0f1319;--card2:#131822;--line:#1c2128;--line2:#262c36;--ink:#eef0f6;--mute:#8b93a7;--mute2:#6c7488;
--acc:#3f3efb;--acc2:#633efa;--accsoft:#232785;--ok:#79cb9d;--okbg:#0b2f23;--okd:#2fd07f;--err:#ff6b6b;--errbg:#3a141b;--sch:#7aa7ff;--schbg:#10264f;--part:#f5b83d;--partbg:#35290c;
--ig:#e640d6;--yt:#ff4d4d;--tt:#22d3ee;--li:#3b72f6;--r:12px;color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 Inter,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased;overflow-x:hidden}
button,input{font:inherit;color:inherit}
button{cursor:pointer;background:none;border:0;padding:0}
button:disabled,[aria-disabled=true]{cursor:not-allowed}
:focus-visible{outline:2px solid #8c8bff;outline-offset:2px;border-radius:6px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.app{display:grid;grid-template-columns:208px minmax(0,1fr);min-height:100vh}
/* sidebar */
aside{background:var(--side);border-right:1px solid var(--line2);position:sticky;top:0;height:100vh;display:flex;flex-direction:column;padding:16px 13px 44px;min-width:0}
.brand{display:flex;align-items:center;gap:10px;padding:0 0 0 7px;height:30px;margin-bottom:24px;font-size:20px;font-weight:700;letter-spacing:-.2px}
.brand svg{color:#6a4bff;fill:#6a4bff;stroke:#6a4bff;stroke-width:1}
nav{display:flex;flex-direction:column;gap:5px}
.nv{text-decoration:none;display:flex;align-items:center;gap:14px;height:40px;padding:0 13px;border-radius:9px;color:#c4c9d8;font-size:15px;text-align:left;width:100%}
.nv svg{flex:none;color:#aab1c4}
.nv[aria-current=page]{background:linear-gradient(90deg,#2b2fa6,#212580);color:#fff;font-weight:600;box-shadow:inset 0 0 0 1px rgba(120,120,255,.15)}
.nv[aria-current=page] svg{color:#fff}
.nv[aria-disabled=true]:hover{background:rgba(255,255,255,.03)}
.promo{margin-top:auto;border:1px solid var(--line2);background:#10161d;border-radius:12px;padding:14px 14px 14px}
.promo .ph{display:flex;align-items:center;gap:10px;font-weight:600;font-size:14px}
.promo .ph svg{color:#8b5cf6;fill:#8b5cf6}
.promo p{margin:6px 0 14px;font-size:12.5px;line-height:1.45;color:var(--mute);padding-left:0}
.cta{display:block;width:100%;height:38px;border-radius:8px;background:var(--acc);color:#fff;font-weight:600;font-size:14px;opacity:.95}
.cta:disabled{opacity:.9}
/* main */
main{padding:13px 18px 28px 22px;min-width:0;display:flex;flex-direction:column;gap:15px}
.top{display:flex;align-items:center;gap:14px;height:40px}
.search{position:relative;flex:1 1 614px;max-width:614px;min-width:0}
.search>svg{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:#9aa2b6;pointer-events:none}
.search input{width:100%;height:38px;border-radius:10px;border:1px solid var(--line2);background:#141921;padding:0 64px 0 52px;color:var(--ink);outline-offset:2px}
.search input::placeholder{color:#8a92a6}
.kbd{position:absolute;right:12px;top:50%;transform:translateY(-50%);font-size:11px;color:#8f98ad;background:#1d232d;border:1px solid #2b323d;border-radius:6px;padding:2px 7px;pointer-events:none;letter-spacing:.3px}
.tr{display:flex;align-items:center;gap:13px;margin-left:auto;flex:none}
.btn{display:inline-flex;align-items:center;gap:9px;height:36px;padding:0 14px;border-radius:9px;border:1px solid var(--line2);background:#0f151a;color:#e6e9f2;font-size:14px;white-space:nowrap;position:relative}
.btn:hover{background:#151c23}
.btn svg{color:#c5cad8;flex:none}
.btn.pri{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600;padding:0 13px;gap:8px}
.btn.pri svg{color:#fff}.btn.pri:hover{background:#4d4cff}
.btn .bdg{background:var(--acc);color:#fff;border-radius:999px;font-size:10.5px;min-width:16px;height:16px;line-height:16px;text-align:center;padding:0 4px}
.ib{width:36px;padding:0;justify-content:center}
.ib[aria-busy=true] svg{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#6a4bff,#d946ef);display:grid;place-items:center;font-weight:700;font-size:14px;color:#fff;flex:none;box-shadow:0 0 0 2px #1c2230}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:13px 16px 14px;min-width:0;position:relative}
.ch{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px;min-height:34px}
.ct{margin:0;font-size:17px;font-weight:600;letter-spacing:-.1px}
.ct.s{font-size:16px}
.mute{color:var(--mute)}.small{font-size:12px}
/* kpis */
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}
.kpi{display:flex;gap:14px;align-items:flex-start;padding:12px 14px;height:103px}
.kic{width:48px;height:48px;border-radius:10px;display:grid;place-items:center;flex:none;margin-top:2px}
.kic.a{background:#112149;color:#6b8cff;box-shadow:inset 0 0 0 1px #1d3a82}
.kic.b{background:#0d2a21;color:#34d399;box-shadow:inset 0 0 0 1px #14503b}
.kic.c{background:#0f2046;color:#5b9cff;box-shadow:inset 0 0 0 1px #1a3a7d}
.kic.d{background:#32181f;color:#ff6b6b;box-shadow:inset 0 0 0 1px #5a2630}
.kic.e{background:#1c1a2f;color:#a78bfa;box-shadow:inset 0 0 0 1px #3a3366}
.kb{min-width:0;flex:1}
.kl{font-size:14.5px;color:#cfd4e3;margin-top:1px}
.kv{display:flex;align-items:baseline;gap:17px;margin-top:1px}
.kn{font-size:25px;font-weight:700;line-height:1.25;letter-spacing:-.3px}
.dl{font-size:13.5px;font-weight:500;color:#34d399;white-space:nowrap}
.dl.neg{color:var(--err)}.dl.na{color:var(--mute2)}
.ks{font-size:13.5px;color:var(--mute);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ks.bad{color:var(--err)}
/* grids */
.g2{display:grid;grid-template-columns:779fr 494fr;gap:14px}
.g3{display:grid;grid-template-columns:520fr 378fr 361fr;gap:14px;margin-top:0}
.sel{display:inline-flex;align-items:center;gap:10px;height:30px;padding:0 12px;border:1px solid var(--line2);border-radius:8px;font-size:13px;background:#0e1319}
.sel svg{color:#b8bfd0}
#banner:empty{display:none}
#chart{position:relative}
#chart svg{display:block;width:100%;overflow:visible}
.lg{display:flex;gap:26px;margin-top:10px;padding-left:8px;flex-wrap:wrap;font-size:13.5px;color:#d6dae6}
.lg span{display:inline-flex;align-items:center;gap:9px}
.lg i{width:10px;height:10px;border-radius:50%;display:inline-block}
.tip{position:absolute;pointer-events:none;background:#161b26;border:1px solid #2c3342;border-radius:9px;padding:8px 11px;font-size:12.5px;min-width:150px;box-shadow:0 8px 24px rgba(0,0,0,.5);z-index:5}
.tip b{display:block;margin-bottom:4px;font-weight:600}
.tip div{display:flex;align-items:center;gap:7px;justify-content:space-between}
.tip div span{display:inline-flex;align-items:center;gap:7px;color:#c8cde0}
.tip i{width:8px;height:8px;border-radius:50%;display:inline-block}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:140px;color:var(--mute);text-align:center;padding:12px;font-size:13.5px}
.empty svg{opacity:.7}
/* logos */
.logo{display:inline-grid;place-items:center;flex:none;border-radius:9px;overflow:hidden}
.logo svg{width:100%;height:100%;display:block}
.logo.instagram{background:linear-gradient(45deg,#f9a03f,#e1306c 52%,#7a38c9)}
.logo.instagram.bare{background:none}
.logo.youtube{background:#ff1f1f}
.logo.tiktok{background:#050507;box-shadow:inset 0 0 0 1px #2b2f38}
.logo.linkedin{background:#1060d0}
.logo.facebook{background:#1877f2}
/* settings */
#setView{display:none}
main.sett>:not(#setView){display:none}
main.sett #setView{display:block}
.acv-h{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin:6px 0 16px;flex-wrap:wrap}
.acv-h h1{font-size:24px;font-weight:600;margin:0 0 4px}.acv-h p{margin:0;color:var(--mute);font-size:14px}
.acv{padding:4px 18px}
.acr{display:flex;align-items:center;gap:14px;padding:14px 0;border-top:1px solid #171c23}
.acr:first-child{border-top:0}
.acr .ai{flex:1;min-width:0}.acr .ai b{display:block;font-size:15.5px;font-weight:600}
.acr .ai span{display:block;font-size:13px;color:var(--mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.acr .ai span.bad{color:#ff8a8a;white-space:normal}
.acb{font-size:12.5px;padding:3px 10px;border-radius:999px;background:#1a212b;color:#c3c9d8;white-space:nowrap}
.acb.good{background:#0f2a1e;color:#4ade9b}.acb.wait{background:#2a2410;color:#f3c969}
.acr .btn[disabled]{opacity:.5;cursor:default}
/* platform perf */
.pp{display:flex;flex-direction:column}
.ppc .ch{margin-bottom:0;min-height:30px}
.pr{display:grid;grid-template-columns:36px 125px minmax(110px,1fr) 104px;align-items:center;gap:0 12px;height:55.5px;border-top:1px solid #171c23}
.pr:first-child{border-top:0}
.pr .nm{font-size:14px;font-weight:500}.pr .po{font-size:13px;color:var(--mute)}
.pr .vw{display:flex;align-items:baseline;gap:14px;justify-content:flex-end;white-space:nowrap}
.pr .vw b{font-size:17px;font-weight:600}
.pr .rs2{grid-column:3/5;text-align:right;min-width:0;display:flex;flex-direction:column;align-items:flex-end}.pr .rs2 b{font-size:17px;font-weight:600;line-height:1.1}.pr .rs2 span{font-size:11.5px;color:var(--mute);max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pr .rs{font-size:11.5px;color:var(--mute);line-height:1.25;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.pr svg.sp{width:100%;height:28px;display:block}
/* demographics */
.tabs{display:inline-flex;background:#0b1017;border:1px solid var(--line);border-radius:9px;padding:3px;gap:2px}
.tabs button{height:30px;padding:0 15px;border-radius:7px;font-size:13.5px;color:#aeb5c8;border:1px solid transparent}
.tabs button[aria-selected=true]{background:#1f2a6c;color:#fff;border-color:#2f3ba5}
.tabs.seg{display:flex;width:100%;background:#151b23;padding:0;border-radius:8px;overflow:hidden}
.tabs.seg button{flex:1;border-radius:0;height:32px;font-size:12.5px;padding:0 4px}
.tabs.seg button[aria-selected=true]{background:var(--acc);border-color:transparent;color:#fff}
.aud{display:flex;gap:18px;align-items:flex-start;margin-top:6px}
.map{flex:0 0 245px;max-width:50%;margin-top:4px}
.map svg{width:100%;height:auto;display:block}
.al{flex:1;max-width:480px;min-width:0;display:flex;flex-direction:column;gap:4px;padding-top:2px}
.ar{display:grid;grid-template-columns:minmax(60px,1fr) 70px 36px;gap:0 10px;align-items:center;height:21px;font-size:14px;color:#dfe3ee}
.ar .tk{height:6px;border-radius:99px;background:#191f26;overflow:hidden}
.ar .tk i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#633efa,#8b6cff)}
.ar .pc{text-align:right;font-variant-numeric:tabular-nums}
.ar .an{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.aud.nomap .ar{grid-template-columns:minmax(70px,150px) 1fr 44px}
.aud.nomap .tk{height:8px}
/* top content */
.lnk{color:#7b86ff;font-size:13.5px}.lnk:hover{text-decoration:underline}
.tc{display:flex;flex-direction:column}
.tcr{display:flex;align-items:center;gap:13px;padding:6px 0;border-top:1px solid #171c23}
.tcr:first-child{border-top:0;padding-top:2px}
.th{width:56px;height:52px;border-radius:7px;overflow:hidden;flex:none;background:#1a2030;display:grid;place-items:center;position:relative}
.th img{width:100%;height:100%;object-fit:cover;display:block}
.th.ph{background:linear-gradient(135deg,#2b2f66,#14182e)}
.tt{min-width:0;flex:1}
.tt b{display:block;font-size:14.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tt span{font-size:13px;color:var(--mute)}
.medal{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-weight:700;font-size:13px;color:#1b1206;flex:none;margin-right:10px}
.m1{background:radial-gradient(circle at 35% 30%,#ffd978,#e09a1a);box-shadow:0 0 0 3px rgba(240,170,30,.2)}
.m2{background:radial-gradient(circle at 35% 30%,#f3f5fb,#a9b1c6);box-shadow:0 0 0 3px rgba(190,198,220,.18);color:#262c3a}
.m3{background:radial-gradient(circle at 35% 30%,#f0a56a,#c8632a);box-shadow:0 0 0 3px rgba(220,120,60,.2);color:#2b1406}
/* heatmap */
.hm{display:flex;gap:8px;margin-top:12px}
.hd{display:flex;flex-direction:column;gap:2px;font-size:11.5px;color:#aab1c4;width:30px;flex:none}.hd span{height:15px;line-height:15px}
.hg{flex:1;min-width:0}
.cells{display:grid;grid-template-columns:repeat(24,minmax(0,1fr));gap:2px}
.cells i{display:block;height:15px;border-radius:2px;background:#191d30;cursor:pointer;transition:transform .08s}
.cells i:hover,.cells i.on{outline:2px solid #fff;outline-offset:-1px;transform:scale(1.15);position:relative;z-index:2}
.hg{position:relative}
.bs{margin-top:2px;font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hx{position:relative;height:18px;margin-top:6px;font-size:11.5px;color:#c0c6d6}
.hx span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}
/* table card */
.tbl{padding:0}
.tabbar{display:flex;align-items:center;gap:0;border-bottom:1px solid var(--line);padding:0 16px;min-height:50px;flex-wrap:wrap}
.tabbar .ts{display:flex;gap:0;flex:1;min-width:0;overflow-x:auto}
.tab{display:inline-flex;align-items:center;gap:9px;height:50px;padding:0 20px;font-size:14px;color:#c3c9d8;position:relative;white-space:nowrap}
.tab[aria-selected=true]{color:#fff;font-weight:500}
.tab[aria-selected=true]::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:3px;background:var(--acc);border-radius:2px 2px 0 0}
.tab .pill{background:#1a212b;border-radius:999px;font-size:12px;min-width:28px;text-align:center;padding:2px 8px;color:#d4d9e6}
.tabbar .tx{display:flex;align-items:center;gap:12px;margin-left:auto;padding:6px 0}
.vt{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.vt button{width:38px;height:34px;display:grid;place-items:center;color:#aab1c4}
.vt button[aria-pressed=true]{background:#222735;color:#fff}
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;table-layout:fixed;min-width:1280px}
th{font-weight:400;color:#c9cedc;font-size:13px;text-align:center;height:44px;padding:0 6px;white-space:nowrap;border-bottom:1px solid var(--line)}
th.l,td.l{text-align:left}
th button{display:inline-flex;align-items:center;gap:5px;color:inherit;height:100%}
th button:hover{color:#fff}
td{height:50px;padding:0 6px;text-align:center;border-top:1px solid #181d24;font-size:13.5px;color:#e4e7f0;white-space:nowrap;font-variant-numeric:tabular-nums}
tbody tr:first-child td{border-top:0}
tbody tr:hover td{background:#121720}
tbody tr[aria-selected=true] td{background:#141a2e}
.cb{appearance:none;-webkit-appearance:none;width:17px;height:17px;border:1.5px solid #6d7488;border-radius:4px;background:transparent;display:inline-block;vertical-align:middle;margin:0;cursor:pointer;position:relative}
.cb:checked{background:var(--acc);border-color:var(--acc)}
.cb:checked::after{content:"";position:absolute;left:4px;top:1px;width:4px;height:8px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.cb:indeterminate{background:var(--acc);border-color:var(--acc)}
.cb:indeterminate::after{content:"";position:absolute;left:3px;top:6.5px;width:8px;height:2px;background:#fff}
.pc1{display:flex;align-items:center;gap:12px;min-width:0}
.pc1 .th{width:48px;height:40px;border-radius:6px}
.pt{min-width:0;text-align:left}
.pt b{display:block;font-weight:500;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pt span{font-size:12px;color:var(--mute)}
.st{display:inline-block;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:500}
.st.published{background:var(--okbg);color:var(--ok)}
.st.scheduled{background:var(--schbg);color:var(--sch)}
.st.queued,.st.partial{background:var(--partbg);color:var(--part)}
.st.failed,.st.invalid{background:var(--errbg);color:var(--err)}
.dt{line-height:1.25;font-size:13px}.dt span{display:block;color:#aeb5c6}
.fl{margin-right:7px;font-size:15px;vertical-align:-1px}
.act{width:34px;height:34px;border-radius:8px;display:inline-grid;place-items:center;color:#d8dcea}
.act:hover{background:#1b2130}
.more{display:flex;justify-content:center;padding:12px;border-top:1px solid #181d24}
.gridv{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;padding:16px}
.gc{background:#121720;border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.gc .th{width:100%;height:120px;border-radius:0}
.gc .gb{padding:10px 12px;display:flex;flex-direction:column;gap:6px}
.gc .gb b{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gc .gr{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12.5px;color:var(--mute)}
.selc{font-size:13px;color:#b9c0f5}
/* popovers & dialog */
.pop{position:fixed;z-index:50;background:#141922;border:1px solid #2a3140;border-radius:10px;padding:6px;min-width:170px;box-shadow:0 12px 32px rgba(0,0,0,.55)}
.mi{display:flex;align-items:center;gap:10px;width:100%;padding:8px 10px;border-radius:7px;font-size:13.5px;text-align:left;color:#e2e6f1;text-decoration:none;white-space:nowrap}
.mi:hover,.mi:focus-visible{background:#1d2431}
.mi .ck{width:14px;color:#8c8bff;flex:none}
.mh{font-size:11px;letter-spacing:.6px;text-transform:uppercase;color:var(--mute2);padding:6px 10px 2px}
.mi label{display:flex;align-items:center;gap:10px;width:100%;cursor:pointer}
.back{position:fixed;inset:0;background:rgba(3,5,10,.66);z-index:80;display:grid;place-items:center;padding:16px}
.dlg{background:#111620;border:1px solid #2a3140;border-radius:14px;padding:20px 22px;max-width:460px;width:100%;box-shadow:0 24px 60px rgba(0,0,0,.6)}
.dlg h3{margin:0 0 10px;font-size:17px}
.dlg p{margin:0 0 10px;color:#c5cadb;line-height:1.5}
.dlg code{background:#1c2230;border:1px solid #2a3140;border-radius:6px;padding:1px 6px;font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;color:#d7dcff;word-break:break-word}
.dlg .ft{display:flex;justify-content:flex-end;margin-top:14px}
.toast{position:fixed;right:20px;bottom:20px;z-index:90;background:#161c28;border:1px solid #2c3446;border-left:3px solid #6a6dff;padding:10px 14px;border-radius:9px;font-size:13.5px;max-width:min(380px,calc(100vw - 40px));box-shadow:0 10px 30px rgba(0,0,0,.5)}
.toast.bad{border-left-color:var(--err)}.toast.good{border-left-color:var(--okd)}
.banner{display:flex;align-items:center;gap:12px;background:var(--errbg);border:1px solid #6a2430;color:#ffc9c9;border-radius:10px;padding:10px 14px;font-size:13.5px}
.banner button{margin-left:auto;border:1px solid #7a3340;border-radius:7px;padding:4px 12px;color:#fff}
.skel{border-radius:8px;background:linear-gradient(90deg,#141a23 25%,#1b2230 50%,#141a23 75%);background-size:200% 100%;animation:sh 1.3s linear infinite}
@keyframes sh{to{background-position:-200% 0}}
@media(prefers-reduced-motion:reduce){.skel,.ib[aria-busy=true] svg{animation:none}}
/* responsive */
@media(max-width:1199px){
 .app{grid-template-columns:64px minmax(0,1fr)}
 aside{padding:14px 9px}
 .brand{justify-content:center;padding:0}.brand span,.nv span,.promo p,.promo .ph span{display:none}
 .nv{justify-content:center;padding:0}
 .promo{padding:10px 6px;border:0;background:none}.promo .ph{justify-content:center}.cta{font-size:0;height:36px;position:relative}
 .cta::after{content:"+";font-size:20px}
 .kpis{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
 .g2,.g3{grid-template-columns:minmax(0,1fr)}
 .search{flex:1 1 200px}
}
@media(max-width:700px){
 .app{grid-template-columns:minmax(0,1fr);grid-template-rows:auto 1fr}
 aside{position:static;height:auto;flex-direction:row;align-items:center;padding:8px 10px;overflow-x:auto;gap:6px;border-right:0;border-bottom:1px solid var(--line2)}
 .brand{margin:0;flex:none}
 nav{flex-direction:row;flex:none}.nv{width:40px;flex:none}
 .promo{display:none}
 main{padding:12px 12px 24px}
 .top{flex-wrap:wrap;height:auto}
 .search{flex:1 1 100%;max-width:none}
 .tr{margin-left:0;flex-wrap:wrap;width:100%;gap:8px}
 .tr .avatar{margin-left:auto}
 .kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
 .kpi{height:auto;min-height:103px;gap:10px;padding:12px}.ks{white-space:normal}.kic{width:40px;height:40px}
 .aud{flex-direction:column}.map{flex:none;max-width:none;width:100%}.al{width:100%}
 .pr{grid-template-columns:34px minmax(70px,1fr) auto;height:auto;min-height:56px;padding:6px 0}.pr .spc{display:none}
 .tabbar{padding:0 8px}.tabbar .tx{width:100%;justify-content:space-between}
 .ch{flex-wrap:wrap}
}
</style></head><body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><linearGradient id="igg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#f9a03f"/><stop offset=".5" stop-color="#e1306c"/><stop offset="1" stop-color="#7a38c9"/></linearGradient></defs></svg>
<div class="app">
<aside aria-label="Sidebar">
 <div class="brand"><span data-ico="bolt" data-sz="26"></span><span>Autopost</span></div>
 <nav aria-label="Main">
  <a class="nv" id="nav-dash" href="#" aria-current="page"><span data-ico="home" data-sz="20"></span><span>Dashboard</span></a>
  <button class="nv" id="nav-set" type="button" data-ico-l="settings"><span>Settings</span></button>
 </nav>
</aside>
<main id="main">
 <div class="top">
  <div class="search"><span data-ico="search" data-sz="18"></span>
   <input id="q" type="search" placeholder="Search posts, captions, hashtags..." aria-label="Search posts by title" autocomplete="off" spellcheck="false">
   <span class="kbd" aria-hidden="true">&#8984; K</span></div>
  <div class="tr">
   <button class="btn" id="rangeBtn" type="button" aria-haspopup="menu" aria-expanded="false"><span data-ico="calendar" data-sz="17"></span><span id="rangeLbl">Last 30 days</span><span data-ico="chev" data-sz="16"></span></button>
   <button class="btn" id="filterBtn" type="button" aria-haspopup="menu" aria-expanded="false"><span data-ico="filter" data-sz="17"></span><span>Filter</span><span class="bdg" id="filterBdg" hidden></span></button>
   <button class="btn pri" id="createBtn" type="button" aria-haspopup="menu" aria-expanded="false"><span data-ico="plus" data-sz="17"></span><span>Create Post</span><span data-ico="chev" data-sz="15"></span></button>
   <button class="btn ib" id="syncBtn" type="button" title="Sync analytics" aria-label="Sync analytics"><span data-ico="refresh" data-sz="17"></span></button>
   <div class="avatar" id="avatar" role="img" aria-label="Account">?</div>
  </div>
 </div>
 <div id="banner"></div>
 <section class="kpis" id="kpis" aria-label="Key metrics"></section>
 <section class="g2">
  <div class="card" id="perfCard" aria-labelledby="perfT"><div class="ch"><h2 class="ct" id="perfT">Performance Overview</h2><span id="perfSel"></span></div><div id="chart"></div><div class="lg" id="legend"></div></div>
  <div class="card ppc" aria-labelledby="ppT"><div class="ch"><h2 class="ct s" id="ppT">Platform Performance</h2><span id="ppSel"></span></div><div class="pp" id="pp"></div></div>
 </section>
 <section class="g3">
  <div class="card" aria-labelledby="audT"><div class="ch"><h2 class="ct" id="audT">Audience Demographics</h2><div class="tabs" id="audTabs" role="tablist" aria-label="Demographic"></div></div><div id="aud"></div></div>
  <div class="card" aria-labelledby="tcT"><div class="ch"><h2 class="ct s" id="tcT">Top Performing Content</h2><button class="lnk" id="viewAll" type="button">View all</button></div><div class="tc" id="tc"></div></div>
  <div class="card" aria-labelledby="btT"><div class="ch"><h2 class="ct s" id="btT">Best Posting Times</h2></div><div class="tabs seg" id="btTabs" role="tablist" aria-label="Platform"></div><div id="bt"></div></div>
 </section>
 <section class="card tbl" id="tableCard" aria-label="Posts">
  <div class="tabbar"><div class="ts" id="tabs" role="tablist" aria-label="Post status"></div>
   <div class="tx"><span class="selc" id="selc" aria-live="polite"></span>
    <button class="btn" id="exportBtn" type="button"><span data-ico="download" data-sz="17"></span><span>Export</span></button>
    <div class="vt" role="group" aria-label="View"><button type="button" id="vTable" aria-pressed="true" aria-label="Table view" title="Table view"><span data-ico="grid" data-sz="18"></span></button><button type="button" id="vGrid" aria-pressed="false" aria-label="Grid view" title="Grid view"><span data-ico="list" data-sz="18"></span></button></div></div></div>
  <div id="tbody"></div>
 </section>
<section id="setView" aria-labelledby="setT">
  <div class="acv-h"><div><h1 id="setT">Settings</h1><p>Connect the platforms Autopost publishes to. Each login opens in your browser.</p></div>
   <button class="btn pri" id="acctAll" type="button" hidden>Connect all</button></div>
  <div class="card acv" id="acctList" aria-live="polite"></div>
 </section>
</main></div>
<div id="live" class="sr" role="status" aria-live="polite"></div>
<script>
"use strict";
var NS="http://www.w3.org/2000/svg";
function $(s){return document.querySelector(s)}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function sv(t,a,k){var e=document.createElementNS(NS,t);for(var n in a)e.setAttribute(n,a[n]);if(k)for(var i=0;i<k.length;i++)e.append(k[i]);return e}
var ICONS={
bolt:["M13 2L4 14h7l-1 8 9-12h-7z"],
home:["M3 11l9-8 9 8","M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"],
content:["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z","M10 9l5 3-5 3z"],
calendar:["M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z","M16 2v4","M8 2v4","M3 10h18"],
analytics:["M3 3v18h18","M7 15l4-4 3 3 6-7"],
sparkle:["M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z","M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z"],
image:["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z","M3 16l5-5 5 5","M13 14l3-3 5 5","M8.5 7.5h.01"],
users:["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z","M23 21v-2a4 4 0 0 0-3-3.9","M16 3.1a4 4 0 0 1 0 7.8"],
settings:["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z","M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"],
search:["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z","M21 21l-4.3-4.3"],
chev:["M6 9l6 6 6-6"],
filter:["M4 6h16","M7 12h10","M10 18h4"],
plus:["M12 5v14","M5 12h14"],
download:["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4","M7 10l5 5 5-5","M12 15V3"],
grid:["M4 4h16v16H4z","M4 12h16","M12 4v16"],
list:["M8 6h13","M8 12h13","M8 18h13","M3.5 6h.01","M3.5 12h.01","M3.5 18h.01"],
refresh:["M23 4v6h-6","M1 20v-6h6","M3.5 9a9 9 0 0 1 14.9-3.4L23 10","M1 14l4.6 4.4A9 9 0 0 0 20.5 15"],
kposts:["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z","M12 8h.01","M12 11.5V17"],
kpub:["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z","M8 12.2l2.8 2.8L16 9.5"],
ksch:["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z","M12 7v5l3.2 2"],
kfail:["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z","M9 9l6 6","M15 9l-6 6"],
kview:["M6 20v-6","M12 20V9","M18 20V4"],
up:["M12 19V5","M5 12l7-7 7 7"],
down:["M12 5v14","M19 12l-7 7-7-7"],
dots:["M5 12h.01","M12 12h.01","M19 12h.01"],
ext:["M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6","M15 3h6v6","M10 14L21 3"],
copy:["M9 9h11v11H9z","M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"],
check:["M5 12.5l4.5 4.5L19 7.5"],
chart:["M3 3v18h18","M7 15l4-4 3 3 6-7"],
updown:["M8 9l4-4 4 4","M16 15l-4 4-4-4"]};
function ico(n,sz,fill){var s=sv("svg",{viewBox:"0 0 24 24",width:sz||18,height:sz||18,fill:fill?"currentColor":"none",stroke:"currentColor","stroke-width":"1.8","stroke-linecap":"round","stroke-linejoin":"round","aria-hidden":"true",focusable:"false"});var a=ICONS[n]||[];for(var i=0;i<a.length;i++)s.append(sv("path",{d:a[i]}));return s}
var PN={instagram:"Instagram",youtube:"YouTube",tiktok:"TikTok",linkedin:"LinkedIn",facebook:"Facebook"};
var PCOL={instagram:"#e640d6",youtube:"#ff4d4d",tiktok:"#22d3ee",linkedin:"#3b72f6",facebook:"#1877f2"};
var PORD=["instagram","youtube","tiktok","linkedin","facebook"];
function pname(p){return PN[p]||(p?String(p).charAt(0).toUpperCase()+String(p).slice(1):"")}
function logo(p,size,bare){
 var k=PN[p]?p:"x",w=el("span","logo "+k+(bare&&k==="instagram"?" bare":""));var s=size||28;
 w.style.width=s+"px";w.style.height=s+"px";if(s<=24)w.style.borderRadius="6px";
 w.setAttribute("role","img");w.setAttribute("aria-label",pname(p));
 var g=sv("svg",{viewBox:"0 0 24 24","aria-hidden":"true"});
 var W="#fff";
 if(k==="instagram"){var c=bare?"url(#igg)":W;
  g.append(sv("rect",{x:"3.6",y:"3.6",width:"16.8",height:"16.8",rx:"5",fill:"none",stroke:c,"stroke-width":"2"}),sv("circle",{cx:"12",cy:"12",r:"3.9",fill:"none",stroke:c,"stroke-width":"2"}),sv("circle",{cx:"17.1",cy:"6.9",r:"1.2",fill:c}))}
 else if(k==="youtube"){g.append(sv("path",{d:"M9.6 8.2v7.6l6.6-3.8z",fill:W}))}
 else if(k==="tiktok"){var d="M16.6 5.8A4.3 4.3 0 0 1 15.5 3h-3.1v12.4a2.6 2.6 0 1 1-2.6-2.6c.27 0 .53.04.77.12V9.7a5.7 5.7 0 1 0 4.93 5.7V9.1a7.4 7.4 0 0 0 4.3 1.4V7.4a4.3 4.3 0 0 1-3.2-1.6z";
  g.append(sv("path",{d:d,fill:"#25f4ee",transform:"translate(-.7 -.5)"}),sv("path",{d:d,fill:"#fe2c55",transform:"translate(.7 .5)"}),sv("path",{d:d,fill:W}))}
 else if(k==="linkedin"){g.append(sv("path",{d:"M6.9 9.2H3.6V20h3.3zM5.25 4a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 0 0 0-3.8zM20.4 13.6c0-3.2-1.7-4.7-4-4.7-1.8 0-2.6 1-3.1 1.7V9.2H10V20h3.3v-6c0-1.6.3-3.1 2.3-3.1s2 1.8 2 3.2V20h3.3z",fill:W,transform:"translate(2 0) scale(.84) translate(.7 1.5)"}))}
 else if(k==="facebook"){g.append(sv("path",{d:"M13.4 21v-7.6h2.6l.4-3h-3V8.5c0-.9.3-1.5 1.5-1.5h1.6V4.3c-.3 0-1.2-.1-2.3-.1-2.3 0-3.8 1.4-3.8 3.9v2.3H7.8v3h2.6V21z",fill:W}))}
 else{g.append(sv("circle",{cx:"12",cy:"12",r:"5",fill:W}))}
 w.append(g);return w}
/* number helpers */
function trimZ(x,d){return x.toFixed(d).replace(/\.0+$/,"")}
function fmt(n){if(n==null||typeof n!=="number"||!isFinite(n))return"—";var a=Math.abs(n);
 if(a>=999500)return trimZ(n/1e6,a>=1e7?0:1)+"M";if(a>=1e3)return trimZ(n/1e3,a>=1e4?0:1)+"K";return String(Math.round(n))}
function fmtFull(n){return n==null?"—":Math.round(n).toLocaleString("en-US")}
function axisFmt(v){if(v===0)return"0";if(v>=1e6)return trimZ(v/1e6,1)+"M";if(v>=1e3)return trimZ(v/1e3,1)+"K";return String(v)}
function pct1(n){return n==null||!isFinite(n)?"—":n.toFixed(1)+"%"}
function pctInt(n){return n==null||!isFinite(n)?"—":(Math.round(n*10)/10)+"%"}
function dateOf(s){if(!s)return null;var d=new Date(s);return isNaN(d.getTime())?null:d}
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function dLong(d){return d.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})}
function dTime(d){return d.toLocaleTimeString("en-US",{hour:"numeric",minute:"2-digit"})}
function isoShort(s){var m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s||"");return m?MON[+m[2]-1]+" "+(+m[3]):String(s||"")}
function isoLong(s){var m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s||"");return m?MON[+m[2]-1]+" "+(+m[3])+", "+m[1]:String(s||"")}
function safeUrl(u){return typeof u==="string"&&/^https?:\/\//i.test(u)?u:null}
function safeThumb(u){return typeof u==="string"&&(/^https:\/\//i.test(u)||/^\/thumb\/[A-Za-z0-9._~-]+$/.test(u))?u:null}
function skel(h){var s=el("div","skel");s.style.height=h+"px";s.setAttribute("aria-hidden","true");return s}
/* state */
var S={data:null,range:30,q:"",plats:{},stats:{},tab:"all",sort:{k:"views",d:-1},sortSet:false,view:"table",sel:{},shown:25,aud:"country",bt:"instagram",err:null,syncing:false,fetchedAt:0};
var STATS=["published","scheduled","queued","partial","failed"];
/* popovers */
var openM=null;
function closeM(back){if(!openM)return;var m=openM;openM=null;m.pop.remove();m.btn.setAttribute("aria-expanded","false");if(back)m.btn.focus()}
function openPop(btn,build,left){var same=openM&&openM.btn===btn;closeM();if(same)return;
 var pop=el("div","pop");pop.setAttribute("role","menu");build(pop);document.body.append(pop);
 var r=btn.getBoundingClientRect(),w=pop.offsetWidth,x=left?r.left:r.right-w;x=Math.max(8,Math.min(x,innerWidth-w-8));
 pop.style.left=x+"px";pop.style.top=Math.min(r.bottom+6,innerHeight-pop.offsetHeight-8)+"px";
 btn.setAttribute("aria-expanded","true");openM={btn:btn,pop:pop};var f=pop.querySelector("button,input,a");if(f)f.focus()}
function mi(label,fn,checked){var b=el("button","mi");b.type="button";b.setAttribute("role","menuitem");
 var c=el("span","ck");if(checked)c.append(ico("check",14));b.append(c,el("span",null,label));b.addEventListener("click",function(){closeM(true);fn()});return b}
document.addEventListener("click",function(e){if(openM&&!openM.pop.contains(e.target)&&!openM.btn.contains(e.target))closeM()});
window.addEventListener("resize",function(){closeM()});
window.addEventListener("scroll",function(e){if(openM&&!openM.pop.contains(e.target))closeM()},true);
document.addEventListener("keydown",function(e){
 if(e.key==="Escape"){if(openM)closeM(true);else if(dlgEl)closeDlg()}
 if((e.metaKey||e.ctrlKey)&&(e.key==="k"||e.key==="K")){e.preventDefault();var q=$("#q");q.focus();q.select()}
 if(openM&&(e.key==="ArrowDown"||e.key==="ArrowUp")){var it=[].slice.call(openM.pop.querySelectorAll("button,input,a"));var i=it.indexOf(document.activeElement);if(i>-1||e.key==="ArrowDown"){e.preventDefault();it[(i+(e.key==="ArrowDown"?1:-1)+it.length)%it.length].focus()}}});
/* toast + dialog */
var toastT=0;
function toast(msg,kind){var old=$(".toast");if(old)old.remove();var t=el("div","toast"+(kind?" "+kind:""),msg);t.setAttribute("role",kind==="bad"?"alert":"status");document.body.append(t);clearTimeout(toastT);toastT=setTimeout(function(){t.remove()},5000)}
var dlgEl=null,dlgPrev=null;
function closeDlg(){if(!dlgEl)return;dlgEl.remove();dlgEl=null;if(dlgPrev&&dlgPrev.focus)dlgPrev.focus()}
function showDlg(title,nodes){dlgPrev=document.activeElement;var b=el("div","back"),d=el("div","dlg");d.setAttribute("role","dialog");d.setAttribute("aria-modal","true");d.setAttribute("aria-labelledby","dlgT");
 var h=el("h3",null,title);h.id="dlgT";d.append(h);for(var i=0;i<nodes.length;i++)d.append(nodes[i]);
 var f=el("div","ft"),ok=el("button","btn pri","Got it");ok.type="button";ok.addEventListener("click",closeDlg);f.append(ok);d.append(f);b.append(d);
 b.addEventListener("mousedown",function(e){if(e.target===b)closeDlg()});
 d.addEventListener("keydown",function(e){if(e.key==="Tab"){e.preventDefault();ok.focus()}});
 document.body.append(b);dlgEl=b;ok.focus()}
/* data */
var seq=0;
function load(){var my=++seq;
 return fetch("/api/dashboard?range="+S.range,{headers:{Accept:"application/json"},cache:"no-store"}).then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(function(d){
  if(my!==seq)return;if(!d||typeof d!=="object")throw new Error("Unexpected response");S.data=d;S.err=null;S.fetchedAt=Date.now();
  if(d.range_days&&[7,30,90].indexOf(d.range_days)>-1)S.range=d.range_days},function(e){if(my!==seq)return;S.err=String(e&&e.message||e)}).then(function(){if(my===seq)renderAll()},function(e){S.err=String(e&&e.message||e);renderAll()})}
function renderAll(){renderBanner();renderTop();renderKpis();renderChart();renderPP();renderAud();renderTC();renderBT();renderTable()}
function renderBanner(){var b=$("#banner");b.replaceChildren();if(!S.err)return;var d=el("div","banner");d.setAttribute("role","alert");
 d.append(el("span",null,"Could not load dashboard data ("+S.err+")."+(S.data?" Showing the last loaded data.":"")));var r=el("button",null,"Retry");r.type="button";r.addEventListener("click",load);d.append(r);b.append(d)}
function renderTop(){$("#rangeLbl").textContent="Last "+S.range+" days";
 var n=Object.keys(S.plats).length+Object.keys(S.stats).length,bd=$("#filterBdg");bd.hidden=!n;bd.textContent=n;
 var nm=S.data&&S.data.account&&S.data.account.name,a=$("#avatar");var ini="?";
 if(nm){var w=String(nm).trim().split(/\s+/).filter(Boolean);if(w.length)ini=(w[0].charAt(0)+(w.length>1?w[w.length-1].charAt(0):"")).toUpperCase()}
 a.textContent=ini;a.setAttribute("aria-label","Account: "+(nm||"unknown"));
 var sa=S.data&&S.data.analytics_synced_at,d=dateOf(sa);$("#syncBtn").title=d?"Sync analytics (last synced "+dLong(d)+" "+dTime(d)+")":"Sync analytics";}
/* KPIs */
function delta(p){var s=el("span","dl");if(p==null||!isFinite(p)){s.classList.add("na");s.textContent="—";s.setAttribute("aria-label","no change data");return s}
 var neg=p<0;if(neg)s.classList.add("neg");s.append(ico(neg?"down":"up",13),document.createTextNode(" "+Math.round(Math.abs(p))+"%"));s.setAttribute("aria-label",(neg?"down ":"up ")+Math.round(Math.abs(p))+" percent");return s}
function renderKpis(){var box=$("#kpis");box.replaceChildren();var d=S.data;
 var defs=[["Total Posts","a","kposts","total_posts"],["Published","b","kpub","published"],["Scheduled","c","ksch","scheduled"],["Failed","d","kfail","failed"],["Total Views","e","kview","total_views"]];
 for(var i=0;i<defs.length;i++){var df=defs[i],c=el("div","card kpi"),ic=el("div","kic "+df[1]);ic.append(ico(df[2],24));
  var b=el("div","kb");c.append(ic,b);box.append(c);
  if(!d){b.append(skel(18),skel(30));b.firstChild.style.width="70%";b.firstChild.style.marginBottom="8px";continue}
  var k=(d.kpis||{})[df[3]]||{};b.append(el("div","kl",df[0]));
  var v=el("div","kv"),n=el("div","kn",df[3]==="total_views"?fmt(k.value):(k.value==null?"—":fmtFull(k.value)));v.append(n);
  var sub=el("div","ks");
  if(df[3]==="scheduled"||df[3]==="failed"){var na=el("span","dl na","—");na.setAttribute("aria-hidden","true");v.append(na)}else v.append(delta(k.delta_pct));
  if(df[3]==="scheduled")sub.textContent="in queue";
  else if(df[3]==="failed"){if(k.value>0){sub.textContent=k.value+" need attention";sub.classList.add("bad")}else sub.textContent="no issues"}
  else if(df[3]==="total_views"&&k.value==null&&!d.analytics_synced_at)sub.textContent="Sync to see views";
  else sub.textContent="vs previous "+S.range+" days";
  b.append(v,sub)}}
/* dropdown chip "Views" */
function viewsSel(host){host.replaceChildren();var b=el("button","sel");b.type="button";b.setAttribute("aria-haspopup","menu");b.setAttribute("aria-expanded","false");b.append(el("span",null,"Views"),ico("chev",15));
 b.addEventListener("click",function(){openPop(b,function(p){p.append(mi("Views",function(){},true))})});host.append(b)}
/* chart */
function nice(mx){if(mx<=0)return 1;var raw=mx/4,m=Math.pow(10,Math.floor(Math.log10(raw))),c=[1,2,2.5,5,10];for(var i=0;i<c.length;i++)if(c[i]*m>=raw)return c[i]*m;return 10*m}
function smooth(pts,lo,hi){var d="M"+pts[0][0].toFixed(1)+" "+pts[0][1].toFixed(1);
 for(var i=0;i<pts.length-1;i++){var p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||p2;
  var c1y=Math.max(lo,Math.min(hi,p1[1]+(p2[1]-p0[1])/6)),c2y=Math.max(lo,Math.min(hi,p2[1]-(p3[1]-p1[1])/6));
  d+="C"+(p1[0]+(p2[0]-p0[0])/6).toFixed(1)+" "+c1y.toFixed(1)+" "+(p2[0]-(p3[0]-p1[0])/6).toFixed(1)+" "+c2y.toFixed(1)+" "+p2[0].toFixed(1)+" "+p2[1].toFixed(1)}
 return d}
var lastW=0;
function renderChart(){var box=$("#chart"),lg=$("#legend");box.replaceChildren();lg.replaceChildren();viewsSel($("#perfSel"));
 var d=S.data;if(!d){box.append(skel(190));return}
 var ov=d.overview||{},dates=ov.dates||[],ser=(ov.series||[]).filter(function(s){return PN[s.platform]&&s.views&&s.views.length>1&&s.views.some(function(v){return v>0})});
 if(dates.length<2||!ser.length){var e=el("div","empty");e.append(ico("chart",30),el("div",null,"No analytics yet — click Sync analytics"));var bt=el("button","btn","Sync analytics");bt.type="button";bt.addEventListener("click",doSync);e.append(bt);box.append(e);return}
 var W=Math.max(280,box.clientWidth||700),H=165,L=40,R=10,T=8,B=26,pw=W-L-R,ph=H-T-B,n=dates.length,mx=0;
 ser.forEach(function(s){s.views.forEach(function(v){if(v>mx)mx=v})});var step=nice(mx),ym=step*4;
 var X=function(i){return L+pw*i/(n-1)},Y=function(v){return T+ph-ph*Math.min(v,ym)/ym};
 var svg=sv("svg",{viewBox:"0 0 "+W+" "+H,height:H,role:"img","aria-label":"Daily views by platform, "+isoLong(dates[0])+" to "+isoLong(dates[n-1])});
 var defs=sv("defs",{});ser.forEach(function(s){var g=sv("linearGradient",{id:"ag-"+s.platform,x1:"0",y1:"0",x2:"0",y2:"1"},[sv("stop",{offset:"0","stop-color":PCOL[s.platform],"stop-opacity":".30"}),sv("stop",{offset:"1","stop-color":PCOL[s.platform],"stop-opacity":"0"})]);defs.append(g)});svg.append(defs);
 for(var i=0;i<=4;i++){var y=Y(step*i);svg.append(sv("line",{x1:L,x2:W-R,y1:y,y2:y,stroke:"#1d2430","stroke-width":1}));var t=sv("text",{x:L-10,y:y+4,"text-anchor":"end","font-size":"12",fill:"#aeb5c6"});t.textContent=axisFmt(step*i);svg.append(t)}
 var gs=n<=10?1:n<=35?5:n<=70?10:15;gs=Math.max(gs,Math.ceil(n*64/pw));var idx=[];for(var j=0;j<n;j+=gs)idx.push(j);if(n-1-idx[idx.length-1]>=gs*0.6)idx.push(n-1);else if(idx[idx.length-1]!==n-1&&n>10)idx[idx.length-1]=n-1;
 idx.forEach(function(k){svg.append(sv("line",{x1:X(k),x2:X(k),y1:T,y2:T+ph,stroke:"#171d27","stroke-width":1}));var t=sv("text",{x:Math.min(W-14,Math.max(L-4,X(k))),y:H-6,"text-anchor":"middle","font-size":"12",fill:"#aeb5c6"});t.textContent=isoShort(dates[k]);svg.append(t)});
 var lines=[];
 ser.forEach(function(s){var pts=s.views.slice(0,n).map(function(v,i){return[X(i),Y(v||0)]});if(pts.length<2)return;var dd=smooth(pts,T,T+ph);
  svg.append(sv("path",{d:dd+"L"+pts[pts.length-1][0].toFixed(1)+" "+(T+ph)+"L"+pts[0][0].toFixed(1)+" "+(T+ph)+"Z",fill:"url(#ag-"+s.platform+")",stroke:"none"}));
  lines.push(sv("path",{d:dd,fill:"none",stroke:PCOL[s.platform],"stroke-width":"2","stroke-linecap":"round","stroke-linejoin":"round"}))});
 lines.forEach(function(l){svg.append(l)});
 var vl=sv("line",{y1:T,y2:T+ph,stroke:"#5a6378","stroke-width":1,"stroke-dasharray":"3 3",visibility:"hidden"}),dots=ser.map(function(s){return sv("circle",{r:4,fill:PCOL[s.platform],stroke:"#0f1319","stroke-width":2,visibility:"hidden"})});
 svg.append(vl);dots.forEach(function(c){svg.append(c)});
 var hit=sv("rect",{x:L,y:T,width:pw,height:ph,fill:"transparent"});svg.append(hit);box.append(svg);
 var tip=el("div","tip");tip.hidden=true;box.append(tip);
 function show(ev){var r=svg.getBoundingClientRect(),sx=W/r.width,px=(ev.clientX-r.left)*sx,i=Math.max(0,Math.min(n-1,Math.round((px-L)/pw*(n-1))));
  vl.setAttribute("x1",X(i));vl.setAttribute("x2",X(i));vl.setAttribute("visibility","visible");
  tip.replaceChildren();var b=el("b",null,isoLong(dates[i]));tip.append(b);
  ser.forEach(function(s,k){var v=s.views[i];dots[k].setAttribute("cx",X(i));dots[k].setAttribute("cy",Y(v||0));dots[k].setAttribute("visibility","visible");
   var row=el("div"),nm=el("span"),dt=el("i");dt.style.background=PCOL[s.platform];nm.append(dt,document.createTextNode(pname(s.platform)));row.append(nm,el("b",null,fmtFull(v)));row.lastChild.style.margin="0";tip.append(row)});
  tip.hidden=false;var tw=tip.offsetWidth,lx=X(i)/sx+(X(i)/W>.6?-tw-14:14);tip.style.left=Math.max(0,lx)+"px";tip.style.top="0px"}
 function hide(){vl.setAttribute("visibility","hidden");dots.forEach(function(c){c.setAttribute("visibility","hidden")});tip.hidden=true}
 hit.addEventListener("pointermove",show);hit.addEventListener("pointerdown",show);hit.addEventListener("pointerleave",hide);
 ser.forEach(function(s){var i=el("span");var dot=el("i");dot.style.background=PCOL[s.platform];i.append(dot,document.createTextNode(pname(s.platform)));lg.append(i)});
 lastW=box.clientWidth}
if(window.ResizeObserver){var rf=0;new ResizeObserver(function(){var b=$("#chart");if(!b||!S.data||Math.abs(b.clientWidth-lastW)<2)return;cancelAnimationFrame(rf);rf=requestAnimationFrame(renderChart)}).observe($("#perfCard"))}
/* platform performance */
function spark(vals,col){var s=sv("svg",{viewBox:"0 0 100 28",preserveAspectRatio:"none",class:"sp","aria-hidden":"true"});var n=vals.length;if(!n)return s;var mx=Math.max.apply(null,vals.concat([1])),w=100/n;
 vals.forEach(function(v,i){var h=Math.max(2,28*(v||0)/mx);s.append(sv("rect",{x:(i*w+w*.15).toFixed(2),y:(28-h).toFixed(2),width:(w*.7).toFixed(2),height:h.toFixed(2),rx:"0.6",fill:col}))});return s}
function renderPP(){var box=$("#pp");box.replaceChildren();viewsSel($("#ppSel"));var d=S.data;
 if(!d){for(var i=0;i<4;i++){var s=skel(40);s.style.margin="8px 0";box.append(s)}return}
 var byp={};(d.platforms||[]).forEach(function(p){byp[p.platform]=p});
 PORD.forEach(function(k){var p=byp[k]||{platform:k,posts:0,views:null,delta_pct:null,spark:[],status:"unavailable",reason:"No data"};
  var ok=p.status==="ok",r=el("div","pr");if(!ok&&p.reason)r.title=p.reason;
  var nm=el("div");nm.append(el("div","nm",pname(k)),el("div","po",(p.posts||0)+" post"+(p.posts===1?"":"s")));
  var vw=el("div","vw");vw.append(el("b",null,ok?fmt(p.views):"—"));if(ok&&p.delta_pct!=null){var dl=delta(p.delta_pct);dl.style.fontSize="12.5px";vw.append(dl)}
  if(ok){var sp=el("div","spc");if(p.spark&&p.spark.length)sp.append(spark(p.spark,PCOL[k]));r.append(logo(k,36),nm,vw,sp)}
  else{var rs=el("div","rs2");rs.append(el("b",null,"\u2014"),el("span",null,p.reason||"Unavailable"));r.append(logo(k,36),nm,rs)}
  box.append(r)})}
/* audience / map */
var LAND=[[[16,22],[24,32]],[[12,32],[54,60]],[[3,24],[25,31],[40,71]],[[2,24],[26,29],[31,33],[37,71]],[[3,25],[34,36],[37,71]],[[10,25],[35,36],[38,69]],[[11,25],[34,66]],[[11,24],[34,65]],[[11,22],[34,36],[38,64]],[[12,21],[34,37],[41,60],[62,63]],[[12,21],[33,60]],[[13,16],[20,21],[32,60]],[[15,18],[20,21],[32,47],[54,58],[60,61]],[[17,19],[21,22],[32,46],[50,52],[55,57],[60,61]],[[19,24],[33,46],[51,52],[56,57],[60,61]],[[20,26],[34,45],[55,57],[58,59],[64,66]],[[20,26],[38,44],[56,59],[60,61],[62,66]],[[20,29],[38,44],[57,59],[63,66]],[[20,29],[38,44],[58,61]],[[21,28],[38,46],[61,66]],[[22,28],[38,43],[45,46],[59,66]],[[22,26],[39,42],[59,66]],[[22,26],[39,42],[59,66]],[[22,24],[40,41],[59,65]],[[22,23],[65,65],[70,71]],[[21,23],[69,70]],[[21,22]],[[21,22]]];
var CR=[["US",2,4,2,7],["IS",3,3,31,33],["GL",0,4,24,33],["CA",0,6,2,25],["US",7,9,11,22],["US",10,10,17,21],["MX",10,10,12,16],["MX",11,12,13,18],["BR",15,17,22,29],["BR",18,21,23,29],["CO",14,17,19,21],["AR",22,27,21,24],
["GB",4,6,34,36],["ES",8,9,34,36],["FR",6,8,35,37],["DE",5,6,37,39],["IT",8,9,38,39],["TR",8,9,41,45],["RU",0,5,42,71],["RU",6,7,47,56],["KZ",6,8,45,53],["EG",10,11,40,43],["NG",13,14,36,38],["ZA",20,23,39,42],["KE",14,16,43,44],["SA",11,12,44,47],["PK",10,11,48,50],["AF",9,9,48,50],["IR",9,10,45,47],["IQ",10,10,44,45],["BD",11,11,53,54],["IN",10,14,50,54],["CN",6,11,54,61],["JP",7,10,62,64],["ID",15,18,55,61],["TH",12,14,55,57],["PH",12,14,60,61],["AU",19,24,59,66],["NZ",24,25,69,71]];
function cc(r,c){for(var i=0;i<CR.length;i++){var x=CR[i];if(r>=x[1]&&r<=x[2]&&c>=x[3]&&c<=x[4])return x[0]}return null}
function worldMap(list){var cw=3.6,ch=5.2,m={},mx=0;(list||[]).forEach(function(c){if(c.code&&typeof c.pct==="number"){m[String(c.code).toUpperCase()]=c.pct;if(c.pct>mx)mx=c.pct}});
 var s=sv("svg",{viewBox:"0 0 "+(72*cw)+" "+(28*ch),role:"img","aria-label":"World map shaded by audience share"});
 s.append(sv("defs",{},[sv("filter",{id:"goo",x:"-5%",y:"-5%",width:"110%",height:"110%"},[sv("feGaussianBlur",{stdDeviation:"1.1"}),sv("feColorMatrix",{values:"1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 16 -7"})])]));var gp=sv("g",{filter:"url(#goo)"});s.append(gp);
 LAND.forEach(function(rows,r){rows.forEach(function(rg){for(var c=rg[0];c<=rg[1];c++){var code=cc(r,c),v=code&&m[code],fill="#353b84";
  if(v!=null){var t=Math.max(.25,v/mx);fill=mixc([92,80,220],[190,172,255],t)}
  gp.append(sv("rect",{x:(c*cw).toFixed(2),y:(r*ch).toFixed(2),width:(cw*1.02).toFixed(2),height:(ch*1.02).toFixed(2),fill:fill}))}})});return s}
function mixc(a,b,t){return"rgb("+[0,1,2].map(function(i){return Math.round(a[i]+(b[i]-a[i])*t)}).join(",")+")"}
function renderAud(){var tb=$("#audTabs");tb.replaceChildren();var box=$("#aud");box.replaceChildren();
 [["country","Country"],["age","Age"],["gender","Gender"]].forEach(function(t){var b=el("button",null,t[1]);b.type="button";b.setAttribute("role","tab");b.setAttribute("aria-selected",String(S.aud===t[0]));b.tabIndex=S.aud===t[0]?0:-1;
  b.addEventListener("click",function(){S.aud=t[0];renderAud()});tb.append(b)});
 tabKeys(tb);
 var d=S.data;if(!d){box.append(skel(150));return}
 var a=d.audience,list=a&&a[S.aud];
 if(!a||!list||!list.length){var e=el("div","empty");e.append(ico("users",28),el("div",null,a?"No "+S.aud+" breakdown available":"No audience data yet — sync analytics to see it"));box.append(e);return}
 var w=el("div","aud"+(S.aud==="country"?"":" nomap"));
 if(S.aud==="country"){var m=el("div","map");m.append(worldMap(list));w.append(m)}
 var l=el("div","al");var mx=Math.max.apply(null,list.map(function(x){return x.pct||0}).concat([1]));
 list.forEach(function(x){var r=el("div","ar"),tk=el("div","tk"),f=el("i");f.style.width=Math.max(2,Math.min(100,(x.pct||0)/mx*100))+"%";tk.append(f);
  r.append(el("span","an",x.name==null?"—":String(x.name)),tk,el("span","pc",pctInt(x.pct)));l.append(r)});
 w.append(l);box.append(w)}
function tabKeys(tb){tb.onkeydown=function(e){if(e.key!=="ArrowRight"&&e.key!=="ArrowLeft")return;var t=[].slice.call(tb.querySelectorAll("[role=tab]")),i=t.indexOf(document.activeElement);if(i<0)return;e.preventDefault();var n=t[(i+(e.key==="ArrowRight"?1:-1)+t.length)%t.length];n.focus();n.click();var nn=tb.querySelectorAll("[role=tab]")[t.indexOf(n)];if(nn)nn.focus()}}
/* thumbs */
function thumb(r,cls){var w=el("div","th"+(cls?" "+cls:"")),u=safeThumb(r.thumbnail);
 function ph(){w.replaceChildren();w.classList.add("ph");w.append(logo(r.platform,26))}
 if(u){var im=new Image();im.alt="";im.loading="lazy";im.decoding="async";im.referrerPolicy="no-referrer";im.addEventListener("error",ph);im.src=u;w.append(im)}else ph();return w}
/* top content */
function renderTC(){var box=$("#tc");box.replaceChildren();var d=S.data;if(!d){for(var i=0;i<3;i++){var s=skel(52);s.style.marginBottom="10px";box.append(s)}return}
 var t=(d.top_content||[]).slice(0,3);if(!t.length){var e=el("div","empty");e.append(ico("chart",28),el("div",null,"No ranked posts yet"));box.append(e);return}
 t.forEach(function(r,i){var row=el("div","tcr"),tt=el("div","tt"),u=safeUrl(r.url),ti=u?el("a",null,r.title||"Untitled"):el("span");
  var b=el("b");if(u){ti.href=u;ti.target="_blank";ti.rel="noopener noreferrer";ti.style.color="inherit";ti.style.textDecoration="none";b.append(ti)}else b.textContent=r.title||"Untitled";b.title=r.title||"";
  tt.append(b,el("span",null,pname(r.platform)+" · "+fmt(r.views)+" views"));
  var rk=r.rank||i+1,m=el("div","medal m"+Math.min(3,rk),String(rk));m.setAttribute("aria-label","Rank "+rk);
  row.append(thumb(r),tt,m);box.append(row)})}
/* best times */
function renderBT(){var tb=$("#btTabs");tb.replaceChildren();var box=$("#bt");box.replaceChildren();
 PORD.forEach(function(p){var b=el("button",null,pname(p));b.type="button";b.setAttribute("role","tab");b.setAttribute("aria-selected",String(S.bt===p));b.tabIndex=S.bt===p?0:-1;b.addEventListener("click",function(){S.bt=p;renderBT()});tb.append(b)});tabKeys(tb);
 var d=S.data;if(!d){box.append(skel(130));return}
 var x=(d.best_times||{})[S.bt]||{},g=x.grid;
 if(!g||!g.length){var e=el("div","empty");e.append(ico("calendar",28),el("div",null,x.basis||"Not enough posts to find the best times yet"));box.append(e);return}
 var days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],wrap=el("div","hm"),hd=el("div","hd");days.forEach(function(n){hd.append(el("span",null,n))});
 var hg=el("div","hg"),cells=el("div","cells");cells.setAttribute("role","img");cells.setAttribute("aria-label","Best posting times heatmap for "+pname(S.bt)+", weekday by hour");
 var mxv=0;g.forEach(function(r){(r||[]).forEach(function(v){if(typeof v==="number"&&v>mxv)mxv=v})});
 for(var r=0;r<7;r++)for(var h=0;h<24;h++){var v=g[r]&&g[r][h],c=el("i");
  if(typeof v==="number"&&mxv>0){var t=Math.max(0,Math.min(1,v/mxv));c.style.background=mixc([38,40,128],[150,125,255],Math.pow(t,.9));c.dataset.tip=Math.round(t*100)+"% of peak · "+fmt(v)}else c.dataset.tip="No data";
  c.dataset.tl=days[r]+" "+hourL(h);cells.append(c)}
 var ctip=el("div","tip");ctip.hidden=true;var pin=null;
 function showT(c){var cr=c.getBoundingClientRect(),gr=cells.getBoundingClientRect();ctip.replaceChildren(el("b",null,c.dataset.tl),el("span",null,c.dataset.tip));ctip.style.minWidth="0";ctip.style.whiteSpace="nowrap";ctip.hidden=false;
  var tw=ctip.offsetWidth,lx=cr.left-gr.left+cr.width/2-tw/2;ctip.style.left=Math.max(0,Math.min(gr.width-tw,lx))+"px";ctip.style.top=(cr.top-gr.top-ctip.offsetHeight-6)+"px"}
 function cellOf(e){var c=e.target;return c&&c.tagName==="I"&&c.parentNode===cells?c:null}
 cells.addEventListener("mouseover",function(e){var c=cellOf(e);if(c&&!pin)showT(c)});
 cells.addEventListener("mouseleave",function(){if(!pin)ctip.hidden=true});
 cells.addEventListener("click",function(e){var c=cellOf(e);if(!c)return;if(pin){pin.classList.remove("on")}if(pin===c){pin=null;ctip.hidden=true;return}pin=c;c.classList.add("on");showT(c)});
 document.addEventListener("click",function(e){if(pin&&!cells.contains(e.target)){pin.classList.remove("on");pin=null;ctip.hidden=true}});
 var hx=el("div","hx");[[0,"12AM"],[6,"6AM"],[12,"12PM"],[18,"6PM"],[23,"12AM"]].forEach(function(a){var s=el("span",null,a[1]);s.style.left=((a[0]+.5)/24*100)+"%";hx.append(s)});
 hg.append(cells,hx,ctip);wrap.append(hd,hg);box.append(wrap);var bs=el("div","mute small bs",x.basis||"");bs.title=x.basis||"";box.append(bs)}
function hourL(h){return(h%12||12)+(h<12?"AM":"PM")}
/* table */
function whenOf(r){return dateOf(r.published_at)||dateOf(r.scheduled_at)}
function key(r){return r.platform+"|"+r.id}
function tabMatch(r){var t=S.tab;if(t==="all")return true;if(t==="published")return r.status==="published";if(t==="scheduled")return r.status==="scheduled"||r.status==="queued";if(t==="failed")return r.status==="failed"||r.status==="invalid";return true}
function filtered(){var d=S.data;if(!d)return[];var q=S.q.trim().toLowerCase(),pk=Object.keys(S.plats),sk=Object.keys(S.stats);
 var rows=(d.rows||[]).filter(function(r){return tabMatch(r)&&(!pk.length||S.plats[r.platform])&&(!sk.length||S.stats[r.status])&&(!q||String(r.title||"").toLowerCase().indexOf(q)>-1)});
 var k=S.sort.k,dir=S.sort.d;
 var val=function(r){switch(k){case"post":return String(r.title||"").toLowerCase();case"platform":return pname(r.platform).toLowerCase();case"status":return r.status;case"when":var w=whenOf(r);return w?w.getTime():null;case"eng":return r.eng_rate;default:return r[k]}};
 return rows.map(function(r,i){return[r,i]}).sort(function(A,B){var a=val(A[0]),b=val(B[0]);if(a==null&&b==null)return A[1]-B[1];if(a==null)return 1;if(b==null)return-1;return(a<b?-1:a>b?1:0)*dir||A[1]-B[1]}).map(function(x){return x[0]})}
function renderTabs(){var tb=$("#tabs");tb.replaceChildren();var c=(S.data&&S.data.tab_counts)||{};
 [["all","All Posts"],["published","Published"],["scheduled","Scheduled"],["failed","Failed"]].forEach(function(t){var b=el("button","tab");b.type="button";b.setAttribute("role","tab");b.setAttribute("aria-selected",String(S.tab===t[0]));b.tabIndex=S.tab===t[0]?0:-1;
  b.append(el("span",null,t[1]),el("span","pill",c[t[0]]==null?"—":String(c[t[0]])));b.addEventListener("click",function(){S.tab=t[0];S.shown=25;renderTable()});tb.append(b)});tabKeys(tb)}
function statusBadge(s){var l={published:"Published",scheduled:"Scheduled",queued:"Queued",partial:"Partial",failed:"Failed",invalid:"Invalid"};var b=el("span","st "+(l[s]?s:"queued"),l[s]||String(s||"Unknown"));return b}
function actions(r){var b=el("button","act");b.type="button";b.setAttribute("aria-haspopup","menu");b.setAttribute("aria-expanded","false");b.setAttribute("aria-label","Actions for "+(r.title||"post"));var dg=ico("dots",20);dg.setAttribute("stroke-width","3.2");b.append(dg);
 b.addEventListener("click",function(){openPop(b,function(p){var u=safeUrl(r.url);
  if(u){var a=el("a","mi");a.href=u;a.target="_blank";a.rel="noopener noreferrer";a.setAttribute("role","menuitem");a.append(ico("ext",15),el("span",null,"Open post"));a.addEventListener("click",function(){closeM()});p.append(a);
   p.append(mi("Copy link",function(){copyText(u)},false));p.lastChild.firstChild.replaceChildren(ico("copy",15))}
  else{var n=el("div","mh",r.error?"Error: "+r.error:"No link yet");n.style.textTransform="none";n.style.letterSpacing="0";n.style.maxWidth="260px";n.style.whiteSpace="normal";p.append(n)}})});return b}
function copyText(t){var done=function(){toast("Link copied","good")},fail=function(){toast("Could not copy the link","bad")};
 if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(t).then(done,fail);else{try{var i=el("textarea");i.value=t;i.style.position="fixed";i.style.opacity="0";document.body.append(i);i.select();var ok=document.execCommand("copy");i.remove();ok?done():fail()}catch(e){fail()}}}
function renderTable(){renderTabs();var box=$("#tbody");box.replaceChildren();var vt=$("#vTable"),vg=$("#vGrid");vt.setAttribute("aria-pressed",String(S.view==="table"));vg.setAttribute("aria-pressed",String(S.view==="grid"));
 var d=S.data;if(!d){var s=skel(220);s.style.margin="16px";box.append(s);$("#selc").textContent="";return}
 var rows=filtered(),vis=rows.slice(0,S.shown),nsel=Object.keys(S.sel).length;
 var sc=$("#selc");sc.textContent=nsel?nsel+" selected":"";
 if(!rows.length){var e=el("div","empty");e.append(ico("content",28),el("div",null,(d.rows||[]).length?"No posts match your filters":"No posts yet — add a post folder to posts/inbox and run python -m autopost run-inbox"));box.append(e);return}
 if(S.view==="grid"){var g=el("div","gridv");vis.forEach(function(r){var c=el("div","gc"),t=thumb(r),b=el("div","gb"),ti=el("b",null,r.title||"Untitled");ti.title=r.title||"";
   var row=el("div","gr"),left=el("span"),w=whenOf(r);left.textContent=fmt(r.views)+" views";row.append(logo(r.platform,22,true),left,statusBadge(r.status));
   var ck=el("input","cb");ck.type="checkbox";ck.checked=!!S.sel[key(r)];ck.setAttribute("aria-label","Select "+(r.title||"post"));ck.addEventListener("change",function(){ck.checked?S.sel[key(r)]=1:delete S.sel[key(r)];sc.textContent=Object.keys(S.sel).length?Object.keys(S.sel).length+" selected":""});
   var top=el("div","gr");top.append(ck,el("span",null,w?dLong(w):"—"),actions(r));b.append(ti,row,top);c.append(t,b);g.append(c)});box.append(g)}
 else{var wrap=el("div","tw"),tb=el("table"),cg=el("colgroup");[40,0,92,112,122,76,76,92,76,92,76].forEach(function(w){var c=el("col");if(w)c.style.width=w+"px";cg.append(c)});tb.append(cg);
  tb.setAttribute("aria-label","Posts");
  var th=el("thead"),tr=el("tr"),allc=el("input","cb"),allk=vis.every(function(r){return S.sel[key(r)]});allc.type="checkbox";allc.checked=allk&&vis.length>0;allc.indeterminate=!allc.checked&&vis.some(function(r){return S.sel[key(r)]});allc.setAttribute("aria-label","Select all shown posts");
  allc.addEventListener("change",function(){vis.forEach(function(r){allc.checked?S.sel[key(r)]=1:delete S.sel[key(r)]});renderTable()});
  var h0=el("th");h0.append(allc);tr.append(h0);
  [["post","Post","l"],["platform","Platform"],["status","Status"],["when","Published At"],["views","Views"],["likes","Likes"],["comments","Comments"],["shares","Shares"],["eng","Eng. Rate"]].forEach(function(c){
   var h=el("th",c[2]);var on=S.sortSet&&S.sort.k===c[0];h.setAttribute("aria-sort",on?(S.sort.d>0?"ascending":"descending"):"none");
   var b=el("button",null);b.type="button";b.append(el("span",null,c[1]));
   if(on)b.append(ico(S.sort.d>0?"up":"down",12));else if(c[0]==="status")b.append(ico("updown",13));
   b.addEventListener("click",function(){S.sortSet=true;if(S.sort.k===c[0])S.sort.d*=-1;else S.sort={k:c[0],d:(c[0]==="post"||c[0]==="platform"||c[0]==="status")?1:-1};renderTable()});h.append(b);tr.append(h)});
  var ha=el("th",null,"Actions");tr.append(ha);th.append(tr);tb.append(th);
  var bd=el("tbody");
  vis.forEach(function(r){var k=key(r),tr=el("tr");tr.setAttribute("aria-selected",String(!!S.sel[k]));
   var c0=el("td"),ck=el("input","cb");ck.type="checkbox";ck.checked=!!S.sel[k];ck.setAttribute("aria-label","Select "+(r.title||"post"));ck.addEventListener("change",function(){ck.checked?S.sel[k]=1:delete S.sel[k];renderTable()});c0.append(ck);tr.append(c0);
   var cp=el("td","l"),pc=el("div","pc1"),pt=el("div","pt"),ti=el("b",null,r.title||"Untitled");ti.title=r.title||"";pt.append(ti,el("span",null,r.type||""));pc.append(thumb(r),pt);cp.append(pc);tr.append(cp);
   var cl=el("td");cl.setAttribute("aria-label",pname(r.platform));cl.append(logo(r.platform,22,true));tr.append(cl);
   var cs=el("td");cs.append(statusBadge(r.status));if(r.error)cs.title=r.error;tr.append(cs);
   var w=whenOf(r),cw=el("td","l");cw.style.textAlign="left";
   if(w){var dt=el("div","dt",dLong(w));dt.append(el("span",null,(r.published_at?"":"Scheduled · ")+dTime(w)));cw.append(dt)}else cw.textContent="—";tr.append(cw);
   [r.views,r.likes,r.comments,r.shares].forEach(function(v){tr.append(el("td",null,fmt(v)))});
   tr.append(el("td",null,pct1(r.eng_rate)));
   var ca=el("td");ca.append(actions(r));tr.append(ca);bd.append(tr)});
  tb.append(bd);wrap.append(tb);box.append(wrap)}
 if(rows.length>vis.length){var m=el("div","more"),mb=el("button","btn","Show more ("+(rows.length-vis.length)+" remaining)");mb.type="button";mb.addEventListener("click",function(){S.shown+=25;renderTable()});m.append(mb);box.append(m)}}
/* export */
function csvCell(v){var s=v==null?"":String(v);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return/[",\n\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s}
function exportCsv(){var rows=filtered();if(!rows.length){toast("Nothing to export","bad");return}
 var head=["Title","Type","Platform","Status","Published At","Views","Likes","Comments","Shares","Engagement Rate %","URL"],out=[head.map(csvCell).join(",")];
 rows.forEach(function(r){var w=whenOf(r);out.push([r.title,r.type,pname(r.platform),r.status,w?w.toISOString():"",r.views,r.likes,r.comments,r.shares,r.eng_rate==null?"":r.eng_rate.toFixed(2),safeUrl(r.url)||""].map(csvCell).join(","))});
 var blob=new Blob(["﻿"+out.join("\r\n")+"\r\n"],{type:"text/csv;charset=utf-8"}),u=URL.createObjectURL(blob),a=el("a");a.href=u;a.download="autopost-posts-"+new Date().toISOString().slice(0,10)+".csv";document.body.append(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u)},4000);toast("Exported "+rows.length+" row"+(rows.length===1?"":"s"),"good")}
/* sync */
function doSync(){var b=$("#syncBtn");if(S.syncing)return;S.syncing=true;b.setAttribute("aria-busy","true");b.disabled=true;$("#live").textContent="Syncing analytics";
 fetch("/api/analytics/sync",{method:"POST"}).then(function(r){return r.json().catch(function(){return null}).then(function(j){return{ok:r.ok,j:j,s:r.status}})}).then(function(x){
  if(x.ok&&x.j&&x.j.ok){var p=x.j.platforms||{},parts=PORD.filter(function(k){return p[k]}).map(function(k){return pname(k)+": "+p[k]});var allbad=parts.length&&PORD.every(function(k){return!p[k]||p[k]!=="ok"});toast("Analytics synced"+(parts.length?" — "+parts.join(", "):""),allbad?"bad":"good")}
  else toast("Sync failed: "+((x.j&&x.j.error)||"HTTP "+x.s),"bad")},function(e){toast("Sync failed: "+(e&&e.message||e),"bad")}).then(function(){S.syncing=false;b.removeAttribute("aria-busy");b.disabled=false;return load()})}
/* wiring */
document.querySelectorAll("[data-ico]").forEach(function(h){h.replaceWith(ico(h.getAttribute("data-ico"),+h.getAttribute("data-sz")||18,h.getAttribute("data-fill")))});
document.querySelectorAll("[data-ico-l]").forEach(function(b){b.prepend(ico(b.getAttribute("data-ico-l"),20))});
/* settings view: connect platforms */
var A={rows:null,login:null,err:null,pending:null,queue:[],timer:0};
function setView(v){$("#main").classList.toggle("sett",v);
 var d=$("#nav-dash"),a=$("#nav-set");if(v){d.removeAttribute("aria-current");a.setAttribute("aria-current","page")}else{a.removeAttribute("aria-current");d.setAttribute("aria-current","page")}
 clearTimeout(A.timer);if(v)loadAcct();window.scrollTo({top:0})}
function loadAcct(){return fetch("/api/accounts",{headers:{Accept:"application/json"},cache:"no-store"}).then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(function(j){
  A.rows=j.accounts||[];A.login=j.login||null;A.err=null},function(e){A.err=String(e&&e.message||e)}).then(function(){renderAcct();trackLogin()})}
function trackLogin(){var l=A.login;if(!A.pending||!l||l.platform!==A.pending)return;
 if(l.state==="running"){clearTimeout(A.timer);A.timer=setTimeout(loadAcct,1500);return}
 var name=pname(l.platform);A.pending=null;
 if(l.state==="ok"){toast(name+": "+(l.message||"Connected"),"good");nextQueued()}else{A.queue=[];toast(name+" login failed: "+(l.message||"unknown error"),"bad");renderAcct()}}
function connect(name){A.pending=name;
 fetch("/api/accounts/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({platform:name})}).then(function(r){return r.json().catch(function(){return null}).then(function(j){return{ok:r.ok,j:j,s:r.status}})}).then(function(x){
  if(x.ok&&x.j&&x.j.ok){A.login=x.j.login;renderAcct();clearTimeout(A.timer);A.timer=setTimeout(loadAcct,1500)}
  else{A.pending=null;A.queue=[];toast("Could not start login: "+((x.j&&x.j.error)||"HTTP "+x.s),"bad")}},function(e){A.pending=null;A.queue=[];toast("Could not start login: "+(e&&e.message||e),"bad")})}
function cancelLogin(){A.pending=null;A.queue=[];clearTimeout(A.timer);
 fetch("/api/accounts/cancel",{method:"POST"}).then(function(){toast("Login cancelled")},function(){}).then(loadAcct)}
function nextQueued(){var n=A.queue.shift();if(n)connect(n);else loadAcct()}
function renderAcct(){var box=$("#acctList"),all=$("#acctAll");box.replaceChildren();
 if(A.err){var b=el("div","banner");b.setAttribute("role","alert");b.append(el("span",null,"Could not load platforms ("+A.err+")."));var rt=el("button",null,"Retry");rt.type="button";rt.addEventListener("click",loadAcct);b.append(rt);box.append(b);all.hidden=true;return}
 if(!A.rows){box.append(el("p","mu","Checking platforms…"));all.hidden=true;return}
 var running=!!(A.login&&A.login.state==="running");
 A.rows.forEach(function(r){var row=el("div","acr"),inf=el("div","ai"),busy=running&&A.login.platform===r.platform;
  inf.append(el("b",null,r.label));
  var sub=el("span",r.connected||busy?null:"bad",busy?(A.login.message||"Waiting for approval…"):(r.connected?r.detail:(r.error||"Not connected")));if(!r.connected&&!busy)sub.title=r.error||"";inf.append(sub);
  var bd=el("span","acb"+(busy?" wait":(r.connected?" good":"")),busy?"Waiting…":(r.connected?"Connected":"Not connected"));
  var bt=el("button","btn"+(r.connected||busy?"":" pri"),busy?"Cancel":(r.connected?"Reconnect":"Connect"));bt.type="button";bt.disabled=running&&!busy;bt.setAttribute("aria-label",(busy?"Cancel login for ":(r.connected?"Reconnect ":"Connect "))+r.label);
  bt.addEventListener("click",function(){A.queue=[];if(busy)cancelLogin();else connect(r.platform)});
  row.append(logo(r.platform,36),inf,bd,bt);box.append(row)});
 var todo=A.rows.filter(function(r){return!r.connected}).map(function(r){return r.platform});
 all.hidden=todo.length<2;all.disabled=running;all.textContent="Connect all ("+todo.length+")";all.onclick=function(){A.queue=todo.slice(1);connect(todo[0])}}
$("#nav-set").addEventListener("click",function(){setView(true)});
document.querySelectorAll("[aria-disabled=true]").forEach(function(b){b.addEventListener("click",function(e){e.preventDefault();toast("Coming soon")})});
$("#nav-dash").addEventListener("click",function(e){e.preventDefault();setView(false)});
$("#q").addEventListener("input",function(e){S.q=e.target.value;S.shown=25;renderTable()});
$("#q").addEventListener("keydown",function(e){if(e.key==="Escape"&&e.target.value){e.target.value="";S.q="";renderTable()}});
$("#rangeBtn").addEventListener("click",function(e){openPop(e.currentTarget,function(p){[7,30,90].forEach(function(n){p.append(mi("Last "+n+" days",function(){if(S.range!==n){S.range=n;renderTop();load()}},S.range===n))})})});
$("#filterBtn").addEventListener("click",function(e){openPop(e.currentTarget,function(p){
 function sect(t,items,store){p.append(el("div","mh",t));items.forEach(function(it){var l=el("label","mi"),c=el("input","cb");c.type="checkbox";c.checked=!!store[it[0]];c.addEventListener("change",function(){c.checked?store[it[0]]=1:delete store[it[0]];S.shown=25;renderTop();renderTable()});l.append(c,el("span",null,it[1]));p.append(l)})}
 sect("Platform",PORD.map(function(k){return[k,pname(k)]}),S.plats);sect("Status",STATS.map(function(k){return[k,k.charAt(0).toUpperCase()+k.slice(1)]}),S.stats);
 var cl=el("button","mi","Clear filters");cl.type="button";cl.style.marginTop="4px";cl.style.color="#9aa4ff";cl.addEventListener("click",function(){S.plats={};S.stats={};S.shown=25;closeM(true);renderTop();renderTable()});p.append(cl)},true)});
$("#createBtn").addEventListener("click",function(e){openPop(e.currentTarget,function(p){p.append(mi("New post folder…",function(){var a=el("p"),c=el("code","","python -m autopost run-inbox");
 a.append(document.createTextNode("Autopost publishes from folders. Put a folder containing your video and a "),el("code",null,"post.json"),document.createTextNode(" file in "),el("code",null,"posts/inbox"),document.createTextNode(", then run:"));
 var b=el("p");b.append(c);showDlg("New post folder",[a,b])},false))})});
$("#syncBtn").addEventListener("click",doSync);
$("#exportBtn").addEventListener("click",exportCsv);
$("#vTable").addEventListener("click",function(){S.view="table";renderTable()});$("#vGrid").addEventListener("click",function(){S.view="grid";renderTable()});
$("#viewAll").addEventListener("click",function(){S.tab="all";S.sort={k:"views",d:-1};S.sortSet=true;S.view="table";S.shown=25;renderTable();$("#tableCard").scrollIntoView({behavior:"smooth",block:"start"})});
setInterval(function(){if(document.visibilityState==="visible")load()},30000);
document.addEventListener("visibilitychange",function(){if(document.visibilityState==="visible"&&Date.now()-S.fetchedAt>30000)load()});
renderAll();load();
</script></body></html>
"""
