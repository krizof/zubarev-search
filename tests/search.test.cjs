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
  assert.ok(S.search(index,'',{status:'available'}).every(r=>S.isAvailable(r.post)));
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

test('reported missing movies appear with the intended filters',()=>{
  for(const [q,ids] of [['Шрэк',[412,414,416,418]],['Мадагаскар',[360,362,364]],['Кунг-фу Панда',[77,79,82,394]],['Кот в сапогах',[244,245,247]]]){
    const found=new Set(S.search(index,q,{kind:'animation',genre:'Мультфильмы',status:'available'}).map(r=>r.post.id));
    for(const id of ids)assert.ok(found.has(id),q+' '+id);
  }
  assert.ok(S.search(index,'Прочь',{genre:'Ужасы',status:'available'}).some(r=>r.post.id===389));
  for(const q of ['Стажёр','Паддингтон','Притворись моей женой','Предложение','50 первых поцелуев','Знакомство с родителями','Знакомство с Факерами','Джо Блэк']){
    assert.ok(S.search(index,q,{status:'available'}).length,q);
  }
});

test('reserved movies are findable without pretending main posts are restored',()=>{
  for(const [id,target] of [[1000,53],[1634,56],[664,22],[873,3],[139,36]]){
    const p=catalog.items.find(p=>p.id===id);
    assert.equal(p.status,'blocked');
    assert.equal(S.recordLink(p),'https://t.me/rezervzub/'+target);
    assert.ok(S.search(index,p.meta.title,{status:'available'}).some(r=>r.post.id===id));
    assert.ok(!S.search(index,p.meta.title,{status:'unavailable'}).some(r=>r.post.id===id));
  }
  const bad={id:1,status:'blocked',reserve_url:'https://example.com/1',parts:0};
  assert.equal(S.recordLink(bad),null);
  assert.equal(S.isAvailable(bad),false);
  assert.equal(S.recordLink({id:1,status:'partial',parts:1,reserve_url:'https://t.me/rezervzub/3'}),'https://t.me/rezervzub/3');
});
