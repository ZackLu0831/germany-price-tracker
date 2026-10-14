const $=id=>document.getElementById(id);
const names={mediamarkt:'MediaMarkt',amazon:'Amazon.de',otto:'OTTO.de'};
const colors={mediamarkt:'#ff6a83',amazon:'#ffc04f',otto:'#67a8ff'};
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const euro=n=>Number.isFinite(n)?new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(n):'—';
let products=[],latest={results:[]},history=[],days=7,chart=null;
const ADMIN_URL='https://germany-price-tracker.zachlu0831.workers.dev/admin.html';
$('admin').href=ADMIN_URL;
async function get(file){const r=await fetch('data/'+file+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(file+': HTTP '+r.status);return r.json()}
async function load(){try{
 const [p,l,h]=await Promise.all([get('products.json'),get('latest.json'),get('history.json')]);
 products=p;latest=l;history=h;
 const old=$('product').value;$('product').innerHTML=products.map(p=>`<option value="${safe(p.id)}">${safe(p.name)}</option>`).join('');
 if(products.some(p=>p.id===old))$('product').value=old;
 $('updated').textContent=latest.generated_at?'最近采集：'+new Date(latest.generated_at).toLocaleString('zh-CN'):'尚未采集';
 draw();
}catch(e){$('overview').innerHTML=`<p class="bad">读取数据失败：${safe(e.message)}。请检查 GitHub Pages 和 Actions。</p>`}}
function draw(){const p=products.find(p=>p.id===$('product').value);if(!p){$('overview').innerHTML='<p class="muted">暂无商品。请在管理后台添加商品。</p>';return}
 const results=(latest.results||[]).filter(x=>x.product_id===p.id);
 $('overview').innerHTML=Object.keys(names).map(shop=>{
 const r=results.find(x=>x.shop===shop),link=p.links?.[shop],good=r?.status==='ok';
 const price=good?euro(r.price):'—';
 const status=!link?'未配置链接':!r?'尚未采集':good?'抓取成功':'抓取失败：'+(r.error||'未知错误');
 const a=link?`<a href="${safe(link)}" target="_blank" rel="noopener noreferrer">商家商品页 ↗</a>`:'未配置链接';
 const target=p.target_price!=null&&good?`<p class="small ${r.price<=p.target_price?'ok':'muted'}">目标 ${euro(p.target_price)} · ${r.price<=p.target_price?'已达到':'尚未达到'}</p>`:'';
 return `<div class="card"><div class="muted">${names[shop]}</div><strong>${price}</strong><div class="status ${good?'ok':link?'bad':'muted'}">${safe(status)}</div><div class="small">${a}</div>${target}</div>`
 }).join('');
 const rows=results.map(r=>`<tr><td>${safe(r.time)}</td><td>${names[r.shop]||safe(r.shop)}</td><td class="${r.status==='ok'?'ok':'bad'}">${r.status==='ok'?'成功':'失败'}</td><td>${euro(r.price)}</td><td>${safe(r.error||r.method||'')}</td></tr>`).join('');
 $('rows').innerHTML=rows||'<tr><td colspan="5">此商品尚无采集记录</td></tr>';
 $('summary').textContent=`本次任务：${latest.attempted??0} 个链接，成功 ${latest.succeeded??0} 个，失败 ${(latest.attempted??0)-(latest.succeeded??0)} 个。`;
 plot(p.id);
}
function plot(id){const min=Date.now()-days*86400000;
 const datasets=Object.keys(names).map(shop=>({label:names[shop],data:history.filter(x=>x.product_id===id&&x.shop===shop&&Date.parse(x.time)>=min&&Number.isFinite(x.price)).map(x=>({x:Date.parse(x.time),y:x.price})).sort((a,b)=>a.x-b.x),borderColor:colors[shop],backgroundColor:colors[shop],tension:.2,pointRadius:2,spanGaps:false}));
 const any=datasets.some(d=>d.data.length);$('empty').textContent=any?'':'所选时间范围内没有成功采集的价格数据。';
 if(chart){chart.destroy();chart=null}
 if(typeof Chart==='undefined'){$('empty').textContent+=' 图表库未加载，请检查网络。';return}
 chart=new Chart($('chart'),{type:'line',data:{datasets},options:{responsive:true,maintainAspectRatio:false,parsing:false,plugins:{legend:{labels:{color:'#d7e4f7'}}},scales:{x:{type:'linear',min,max:Date.now(),ticks:{color:'#9fb0ca',callback:value=>new Date(value).toLocaleDateString('de-DE')},grid:{color:'#27364e'}},y:{ticks:{color:'#9fb0ca',callback:v=>'€'+v},grid:{color:'#27364e'}}}}});
}
$('product').onchange=draw;$('refresh').onclick=load;
document.querySelectorAll('[data-days]').forEach(b=>b.onclick=()=>{days=+b.dataset.days;document.querySelectorAll('[data-days]').forEach(x=>x.classList.toggle('active',x===b));draw()});load();
