// Exercises the generated view logic with a minimal DOM, not a browser layout test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8');
const raw=html.match(/<script id="study-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
class Node {constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.textContent='';this.handlers={};}
 append(n){this.children.push(n);}replaceChildren(...nodes){this.children=nodes;}addEventListener(event,fn){this.handlers[event]=fn;}}
const nodes=new Map();for(const id of ['study-data','search','scope','order','cards','count','stats','trails','groups','queue','reset'])nodes.set(id,new Node());
nodes.get('study-data').textContent=raw;nodes.get('order').value='trait';
const context={document:{getElementById:id=>nodes.get(id),createElement:tag=>new Node(tag)}};
vm.createContext(context);vm.runInContext(script,context,{timeout:1000});
assert.equal(nodes.get('cards').children.length,6);
assert.equal(nodes.get('trails').children.length,6);
assert.equal(nodes.get('groups').children.length,2);
assert.equal(nodes.get('queue').children.length,6);
nodes.get('scope').value='extracted_enzyme';nodes.get('scope').handlers.input();
assert.equal(nodes.get('cards').children.length,1);
assert.match(nodes.get('count').textContent,/1 synthetic/);
nodes.get('search').value='no matching trait';nodes.get('search').handlers.input();
assert.equal(nodes.get('cards').children.length,0);
nodes.get('reset').handlers.click();assert.equal(nodes.get('cards').children.length,6);
nodes.get('order').value='scope';nodes.get('order').handlers.input();
assert.equal(nodes.get('cards').children[0].children.find(n=>n.tag==='h3').textContent,'Synthetic extracted enzyme');
nodes.get('search').value='recipient R';nodes.get('search').handlers.input();assert.equal(nodes.get('cards').children.length,6);
assert.equal(nodes.get('groups').children.filter(n=>n.className==='dashed').length,1);
assert.equal((html.match(/https:\/\/[^"' <]+/g)||[]).some(x=>x.includes('cdn')),false);
console.log('12 offline UI assertions passed; no browser layout or visual claim.');
