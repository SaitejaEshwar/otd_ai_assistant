import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../src/voice.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {startVoice} = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
function harness({denied=false,pending=false,empty=false}={}) {
  const elements=new Map(); const timers=new Map(); let timerId=0, stopped=0, closed=0, uploads=0, acquire;
  const element=id=> {
    if (!elements.has(id)) elements.set(id,{value:'Existing draft',listeners:{},hidden:false,readOnly:false,disabled:false,textContent:'',addEventListener(name,fn){this.listeners[name]=fn},setAttribute(){},focus(){}});
    return elements.get(id);
  };
  const listeners={}; const track={stop(){stopped++},addEventListener(){}};
  const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
  const worklets=[];
  class Worklet { constructor(){this.port={};worklets.push(this)} connect(){return this} disconnect(){} }
  class Context {audioWorklet={addModule:async()=>{}};async resume(){} async close(){closed++} createMediaStreamSource(){return {connect(){}}} createGain(){return {gain:{value:1},connect(){return {connect(){}}}}} }
  globalThis.document={hidden:false,getElementById:element,addEventListener:(key,fn)=>listeners[key]=fn};
  globalThis.window={AudioWorkletNode:Worklet,setTimeout:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId},addEventListener:(key,fn)=>listeners[key]=fn};
  globalThis.clearTimeout=id=>timers.delete(id);
  globalThis.AudioContext=Context;globalThis.AudioWorkletNode=Worklet;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=> denied ? Promise.reject(new DOMException('Denied','NotAllowedError')) : pending ? new Promise(resolve=>acquire=resolve) : Promise.resolve(stream)}}});
  globalThis.fetch=async(url,options)=>{
    if(url.endsWith('/status')) return {json:async()=>({available:true})};
    uploads++; const bytes=await options.body.arrayBuffer();const view=new DataView(bytes);
    assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint16(22,true),1);
    return {ok:!empty,json:async()=>empty?{detail:'No speech detected'}:{text:'Call Sam'}};
  };
  const busy=startVoice(()=>false);
  return {element,worklets,timers,listeners,busy,resolve:()=>acquire(stream),stats:()=>({stopped,closed,uploads})};
}
test('permission denial returns to editable idle state',async()=>{
  const h=harness({denied:true});await h.element('talk').listeners.click();
  assert.match(h.element('voice-state').textContent,/permission denied/);assert.equal(h.busy(),false);assert.equal(h.stats().uploads,0);
});
test('cancel pending permission closes a late arriving stream',async()=>{
  const h=harness({pending:true});const opening=h.element('talk').listeners.click();h.element('cancel-voice').listeners.click();h.resolve();await opening;
  assert.equal(h.stats().stopped,1);assert.equal(h.busy(),false);assert.equal(h.stats().uploads,0);
});
for(const event of ['cancel','visibilitychange','pagehide']) test(`${event} discards audio and releases microphone`,async()=>{
  const h=harness();await h.element('talk').listeners.click();
  if(event==='cancel')h.element('cancel-voice').listeners.click();else {document.hidden=true;h.listeners[event]()}
  assert.deepEqual(h.stats(),{stopped:1,closed:1,uploads:0});assert.equal(h.busy(),false);assert.equal(h.element('draft').value,'Existing draft');
});
test('stop produces editable transcript without submitting a task',async()=>{
  const h=harness();await h.element('talk').listeners.click();h.worklets[0].port.onmessage({data:new Float32Array(16000).fill(.1)});await h.element('talk').listeners.click();
  assert.deepEqual(h.stats(),{stopped:1,closed:1,uploads:1});assert.equal(h.element('draft').value,'Existing draft Call Sam');assert.equal(h.element('draft').readOnly,false);assert.equal(h.busy(),false);
});
test('silence response preserves the existing draft',async()=>{
  const h=harness({empty:true});await h.element('talk').listeners.click();await h.element('talk').listeners.click();
  assert.equal(h.element('draft').value,'Existing draft');assert.match(h.element('voice-state').textContent,/No speech/);assert.equal(h.busy(),false);
});
test('30 second recording limit stops capture',async()=>{
  const h=harness();await h.element('talk').listeners.click();const limit=[...h.timers.values()].find(t=>t.ms===30000);assert.ok(limit);limit.fn();
  await new Promise(resolve=>setImmediate(resolve));assert.equal(h.stats().stopped,1);assert.equal(h.stats().uploads,1);
});
