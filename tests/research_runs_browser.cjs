'use strict';
// Synthetic fixtures, loopback only; no provider calls or credentials.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {chromium}=require(process.env.TRAITWEAVER_PLAYWRIGHT||'playwright');
const out=process.env.TRAITWEAVER_QA_OUTPUT;
if(!out||!path.isAbsolute(out)||fs.existsSync(out))throw Error('Fresh external output directory required');
fs.mkdirSync(out,{recursive:true});
const records=path.join(out,'records');
cp.execFileSync('python3',['-B','-c',`import sys;sys.path[:0]=['src','tests'];from traitweaver.research_homes import Session;from test_research_runs import prepare,fixture;s=Session(sys.argv[1]);p=prepare(s);s.act(fixture(p,True),s.fingerprint());s.act(fixture(p),s.fingerprint())`,records],{cwd:process.cwd()});
let server,browser,base,checks=0;const errors=[],external=[];
const check=(v,msg)=>{assert.ok(v,msg);checks++;};
async function start(){server=cp.spawn('python3',['-B','run_workspace.py','--demo','--port','0','--research-dir',records],{cwd:process.cwd(),stdio:['ignore','pipe','pipe']});let log='';base=await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('Startup timeout '+log)),20000);server.stdout.on('data',d=>{log+=d;const m=log.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(t);resolve(m[0]);}});server.stderr.on('data',d=>log+=d);server.on('exit',c=>{clearTimeout(t);reject(Error('Server exit '+c));});});}
async function stop(){if(server&&server.exitCode===null)await new Promise(r=>{server.once('exit',r);server.kill('SIGINT');});}
(async()=>{try{
 await start();browser=await chromium.launch({headless:true,...(process.env.TRAITWEAVER_CHROMIUM?{executablePath:process.env.TRAITWEAVER_CHROMIUM}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1080},acceptDownloads:true});
 await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname==='127.0.0.1')return route.continue();external.push(u.origin);return route.abort();});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 const go=async tail=>{await page.goto(base+'/#trait-library/'+tail);await page.locator('.rh-app').waitFor();};
 const state=()=>page.evaluate(()=>fetch('/api/state',{headers:{'X-Traitweaver-Client':'workspace'}}).then(r=>r.json()));
 await go('runs');const initial=await state(),runs=initial.research_homes.saved_runs,ok=runs.find(r=>r.outcome==='completed'),bad=runs.find(r=>r.outcome==='failed');
 check(await page.locator('.rh-run-card').count()===2,'both attempts visible');
 check((await page.locator('.rh-content').innerText()).includes('Synthetic test receipt'),'synthetic provenance visible');
 await page.locator('[name=facet]').selectOption('failed');check(await page.locator('.rh-run-card').count()===1,'filter failed');
 await page.locator('[name=facet]').selectOption('all');await page.screenshot({path:path.join(out,'replies.png'),fullPage:true});
 await go('runs/'+ok.run_id);check(await page.locator('#rr-sources .rh-source-card').count()===2,'exact source records');
 check((await page.locator('#rr-gaps').innerText()).includes('Synthetic gap'),'suggestion retained');
 check((await page.locator('#rr-plan').innerText()).includes('NOT LAB-READY'),'plan limit visible');
 check((await page.locator('#rr-cost').innerText()).includes('$0.00021'),'token cost displayed');
 check((await page.locator('.rh-content').innerText()).includes('Attempt failed')||(await page.locator('.rh-content').innerText()).includes('HTTP 401'),'failure still visible beside success');
 await page.getByText('Exact request bytes and fingerprint',{exact:true}).click();check((await page.locator('#rr-context').innerText()).includes(ok.request_sha256),'exact request hash visible');
 await page.getByRole('button',{name:'Record a separate human decision',exact:true}).click();
 await page.locator('#rh-review-dialog [name=reviewer]').fill('Synthetic browser reviewer');await page.locator('#rh-review-dialog [name=reason]').fill('Synthetic planning review; evidence still needed.');
 await page.getByRole('button',{name:'Save separate decision',exact:true}).click();await page.waitForFunction(()=>snapshot.research_homes.history.length===5);
 check((await state()).research_homes.history.at(-1).event.target_hash===ok.record_hash,'review bound to reply');
 await page.screenshot({path:path.join(out,'reply-detail.png'),fullPage:true});
 await go('runs/'+bad.run_id);check((await page.locator('#rr-cost').innerText()).includes('Unknown'),'failed cost unknown');check((await page.locator('#rr-gaps').innerText()).includes('no model answer')||(await page.locator('#rr-gaps').innerText()).includes('No answer'),'no fabricated answer');
 await go('muse');check((await page.locator('.rh-content').innerText()).includes('Research replies are saved'),'context desk links replies');await page.locator('.rh-saved-packet>summary').click();check((await page.locator('.rh-packet').textContent()).includes('Used in a saved attempt'),'preparation snapshot qualified');
 await go('how');check((await page.locator('.rh-content').innerText()).includes('Many traits. One clear research question.'),'human map');check((await page.locator('.rh-content').innerText()).includes('website cannot dispatch requests to this chat'),'chat connection not falsely claimed');await page.screenshot({path:path.join(out,'human-map.png'),fullPage:true});
 await go('review');await page.locator('#rh-export-ack').check();const waitDownload=page.waitForEvent('download');await page.locator('#rh-export').click();const d=await waitDownload;const exported=path.join(out,'synthetic-export.json');await d.saveAs(exported);const saved=JSON.parse(fs.readFileSync(exported));check(saved.history.length===5,'both attempts and review exported');
 await page.locator('#rh-import').setInputFiles(exported);await page.waitForFunction(()=>snapshot.research_homes.read_only);await go('runs/'+ok.run_id);check(await page.locator('[data-rh-review]').count()===0,'reopen read-only');
 check(JSON.stringify((await state()).current)===JSON.stringify(initial.current),'original phosphorus demo preserved');
 await page.setViewportSize({width:390,height:844});for(const route of ['runs','runs/'+ok.run_id,'how']){await go(route);check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile width '+route);}await page.screenshot({path:path.join(out,'human-map-mobile.png'),fullPage:true});
 await stop();await start();await go('runs');const restarted=await state();assert.deepEqual(restarted.research_homes.history,saved.history);checks++;check(restarted.research_homes.saved_runs.length===2,'both attempts persisted');check(restarted.research_homes.new_provider_calls===0,'workspace made no provider calls');
 check(errors.length===0,'no page errors');check(external.length===0,'no external requests');
 fs.writeFileSync(path.join(out,'BROWSER_CHECKS.json'),JSON.stringify({status:'passed',checks,errors,externalRequests:external,restartVerified:true,scope:'Synthetic local review; no provider calls or scientific validation'},null,2));console.log(JSON.stringify({status:'passed',checks,output:out}));
 }catch(e){fs.writeFileSync(path.join(out,'BROWSER_FAILURE.json'),JSON.stringify({error:e.message,checks,errors,external},null,2));throw e;}finally{if(browser)await browser.close();await stop();}})().catch(e=>{console.error(e);process.exitCode=1});
