'use strict';
// Records the real local presentation using an installed browser; no uploads.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {chromium}=require(process.env.TRAITWEAVER_PLAYWRIGHT||'playwright');
const out=process.env.TRAITWEAVER_QA_OUTPUT;
if(!out||!path.isAbsolute(out)||fs.existsSync(out))throw Error('Choose a fresh external absolute recording directory');
fs.mkdirSync(out,{recursive:true});
let server,browser;const errors=[],external=[],writes=[],visits=[];
(async()=>{try{
 server=cp.spawn('python3',['-B','run_workspace.py','--demo','--port','0','--research-dir',path.join(out,'records')],{stdio:['ignore','pipe','pipe']});
 let log='';const base=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(log||'Server timeout')),20000);server.stdout.on('data',d=>{log+=d;const m=log.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timer);resolve(m[0]);}});server.stderr.on('data',d=>log+=d);server.on('exit',c=>{clearTimeout(timer);reject(Error('Server exit '+c+': '+log));});});
 browser=await chromium.launch({headless:true,executablePath:process.env.TRAITWEAVER_CHROMIUM});
 const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,recordVideo:{dir:out,size:{width:1920,height:1080}}});
 await context.route('**/*',route=>{const r=route.request();if(new URL(r.url()).hostname!=='127.0.0.1'){external.push(r.url());return route.abort();}if(r.method()!=='GET')writes.push(r.url());return route.continue();});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));const video=page.video(),recordingOpened=Date.now();
 await page.goto(base+'/#demo/possibility');await page.locator('[data-scene=possibility]').waitFor();await page.evaluate(()=>document.fonts.ready);
 const initial=await page.evaluate(()=>({study:snapshot.current.hash,research:snapshot.research_homes.hash,library:snapshot.trait_library.current?.hash}));
 const scenes=await page.evaluate(()=>siteScenes.map(s=>({id:s.id,seconds:s.seconds})));
 // Check the actual recording viewport before starting the timed capture.
 for(const s of scenes){await page.evaluate(id=>location.hash='#demo/'+id,s.id);await page.locator('[data-scene='+s.id+']').waitFor();const fits=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&document.querySelector('.sw-demo-footnote').getBoundingClientRect().bottom<=innerHeight);if(!fits){await page.screenshot({path:path.join(out,'overflow-'+s.id+'.png'),fullPage:true});throw Error('Scene does not fit recording viewport: '+s.id);}}
 await page.evaluate(()=>location.hash='#demo/possibility');await page.locator('[data-scene=possibility]').waitFor();
 const start=Date.now();await page.getByRole('button',{name:'Play tour',exact:true}).click();await page.mouse.move(1880,1060);
 for(const s of scenes){await page.locator('[data-scene='+s.id+']').waitFor({timeout:35000});visits.push({id:s.id,elapsedSeconds:(Date.now()-start)/1000});console.log(JSON.stringify({scene:s.id,elapsedSeconds:visits.at(-1).elapsedSeconds}));await page.screenshot({path:path.join(out,s.id+'.png')});if(s.id==='horizon')await page.waitForFunction(()=>!sitePlaying,{},{timeout:25000});}
 const end=Date.now(),final=await page.evaluate(()=>({study:snapshot.current.hash,research:snapshot.research_homes.hash,library:snapshot.trait_library.current?.hash}));
 if(JSON.stringify(initial)!==JSON.stringify(final)||errors.length||external.length||writes.length)throw Error('Recording boundary check failed');
 await context.close();const raw=await video.path();
 const receipt={status:'recorded',silent:true,viewport:{width:1920,height:1080},rawFile:path.basename(raw),approximateTrimStartSeconds:(start-recordingOpened)/1000,durationSeconds:(end-start)/1000,visits,errors,externalRequests:external,writes,sourceOwnersUnchanged:true,provenance:'Actual local browser recording. Synthetic model replies and saved software result. No new Muse call or biological experiment.'};
 fs.writeFileSync(path.join(out,'RECORDING.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({status:'recorded',output:out}));
}catch(e){fs.writeFileSync(path.join(out,'FAILURE.json'),JSON.stringify({error:e.message,errors,external,writes,visits},null,2));console.error(e);process.exitCode=1;}finally{if(browser)await browser.close();if(server&&server.exitCode===null)server.kill('SIGINT');}})();
