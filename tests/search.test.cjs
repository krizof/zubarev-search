const {test}=require('node:test');
const assert=require('node:assert/strict');
const S=require('../search.js');
const catalog=require('../catalog.json');
const index=S.makeIndex(catalog.items);
test('punctuation survives query parsing for decimals and plus',()=>{
  assert.equal(S.parse('комедия 90-е 7.5+').minKP,7.5);
  assert.equal(S.parse('комедия 90-е 7.5+').decade,1990);
  assert.equal(S.parse('комедия 90-е 7.5+').genre,'комедия');
});
test('typos, keyboard layout, transliteration and English titles',()=>{
  for(const q of ['интерстелар','byntbcntkkfh','interstellar']){
    assert.ok(S.search(index,q).some(r=>r.post.meta.title==='Интерстеллар (2014)'),q);
  }
  assert.ok(S.search(index,'vfnhbwf').some(r=>r.post.meta.title==='Матрица (1999)'));
  assert.ok(S.search(index,'spider man').some(r=>r.post.meta.title.includes('Человек-паук')));
});
test('year, decade, rating and genre are strict, missing values excluded',()=>{
  const results=S.search(index,'комедия 90-е 7+');
  assert.ok(results.length);
  assert.ok(results.every(({post:p})=>p.meta.year>=1990&&p.meta.year<=1999&&p.meta.kp>=7&&p.categories.includes('Комедия')));
  assert.ok(S.search(index,'мстители 2012').every(r=>r.post.meta.year===2012));
  assert.ok(S.search(index,'7.5+').every(r=>r.post.meta.kp>=7.5));
});
test('all words must match and sequel number is retained',()=>{
  assert.equal(S.search(index,'zzzzqqqq').length,0);
  const results=S.search(index,'форсаж 9');
  assert.ok(results.length);
  assert.ok(results.every(r=>S.normalize(r.post.meta.title).includes('9')));
});
test('availability is shared across tabs and saved ids',()=>{
  const hidden=S.search(index,'',{status:'unavailable'});
  assert.equal(hidden.length,catalog.stats.unavailable);
  assert.ok(S.search(index,'',{status:'available'}).every(r=>r.post.status==='available'));
  assert.equal(S.search(index,'',{ids:new Set([1700])}).length,1);
  assert.equal(S.search(index,'',{ids:new Set()}).length,0);
});
test('unknown KP cannot pass filter and exact year does not include neighbours',()=>{
  const items=[{id:1,meta:{title:'Фильм',kp:null,year:null},categories:[],text:'',status:'available'},{id:2,meta:{title:'Фильм',kp:8,year:2001},categories:[],text:'',status:'available'}];
  assert.equal(S.search(S.makeIndex(items),'8+').length,1);
  assert.equal(S.search(S.makeIndex(items),'2000').length,0);
});
test('top includes explicit ranges only when lower end qualifies',()=>{
  assert.ok(S.search(index,'',{top:true}).every(({post:p})=>p.meta.score>=8||(p.meta.score_range&&p.meta.score_range[0]>=8)));
});
