'use strict';
// Offline citation closure: no browser, network, provider calls or file writes.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../research/traitweaver-300-showcase');
const html=fs.readFileSync(root+'/LIBRARY.html','utf8');
const data=JSON.parse(fs.readFileSync(root+'/library.json','utf8'));
assert.deepEqual(JSON.parse(html.match(/<script id="library-data" type="application\/json">([\s\S]*?)<\/script>/)[1]),data);
const code=html.match(/function allSourceIds\([\s\S]*?\nfunction detail/)[0].replace(/\nfunction detail$/,'');
const ctx=vm.createContext({});vm.runInContext(code,ctx);
const refs=value=>Array.isArray(value)?value.flatMap(refs):value&&typeof value==='object'?Object.entries(value).flatMap(([key,val])=>key==='source_ids'?val:refs(val)):[];
let n=0;
for(const trait of data.traits){
 const groups=data.combinations.filter(g=>g.evidence_current!==false&&g.trait_ids.includes(trait.id));
 ctx.record=trait.record;ctx.groups=groups;
 const actual=Array.from(vm.runInContext('allSourceIds(record,groups)',ctx));
 const expected=[...new Set(refs([trait.record,...groups]))];
 assert.deepEqual(actual.slice().sort(),expected.sort(),'Complete citation closure: '+trait.id);
 assert.equal(actual.length,new Set(actual).size,'No duplicate sources');
 const exported=data.sources.filter(s=>actual.includes(s.id));
 assert.equal(exported.length,expected.length,'Every referenced source exports: '+trait.id);n++;
}
console.log(JSON.stringify({status:'passed',traits:n,checks:n*3+1}));
