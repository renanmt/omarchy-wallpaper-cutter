const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/../Geometry.js', 'utf8').replace('.pragma library', ''), context);
const m = (name,x,y,width=100,height=100) => ({name,x,y,width,height});
let f = context.frames([m('a',0,0),m('b',100,0),m('c',200,0)],20,{});
assert.deepEqual(Array.from(f,x=>x.x),[0,120,240]);
f=context.frames([m('a',0,0),m('b',0,100),m('c',0,200)],12,{});
assert.deepEqual(Array.from(f,x=>x.y),[0,112,224]);
f=context.frames([m('a',-100,-20),m('b',0,0),m('c',100,-20)],30,{c:{x:4,y:-6}});
assert.deepEqual(Array.from(f,x=>x.x),[-100,30,164]);
assert.equal(f[2].y,-26);
f=context.frames([m('a',0,0),m('b',100,100)],50,{});
assert.equal(f[1].x,100); // A corner is not a seam.
f=context.frames([m('a',0,0),m('b',130,0)],50,{});
assert.equal(f[1].x,130); // Existing desktop gaps stay intact.
console.log('5 geometry scenarios passed');
