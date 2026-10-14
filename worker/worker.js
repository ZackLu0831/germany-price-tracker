// Cloudflare Worker: authenticated GitHub product management. No scraping here.
const encoder=new TextEncoder(), decoder=new TextDecoder();
const reply=(obj,status=200,headers={})=>new Response(JSON.stringify(obj),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store',...headers}});
const toB64=bytes=>btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
const b64url=bytes=>toB64(bytes).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const fromB64url=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
const cookie=(name,value,age)=>`${name}=${value}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${age}`;
const cookies=req=>Object.fromEntries((req.headers.get('cookie')||'').split(';').map(s=>s.trim().split(/=(.*)/s).slice(0,2)).filter(a=>a.length===2));
function redirect(url,cs=[]){const h=new Headers({'location':url,'cache-control':'no-store'});for(const c of cs)h.append('set-cookie',c);return new Response(null,{status:302,headers:h})}
async function aesKey(secret){return crypto.subtle.importKey('raw',await crypto.subtle.digest('SHA-256',encoder.encode(secret)),{name:'AES-GCM'},false,['encrypt','decrypt'])}
async function seal(value,secret){const iv=crypto.getRandomValues(new Uint8Array(12));const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv},await aesKey(secret),encoder.encode(JSON.stringify(value)));return b64url(iv)+'.'+b64url(new Uint8Array(ciphertext))}
async function unseal(value,secret){try{const [a,b]=value.split('.');return JSON.parse(decoder.decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:fromB64url(a)},await aesKey(secret),fromB64url(b))))}catch{return null}}
function validate(products){
 if(!Array.isArray(products)||products.length>100)throw Error('最多100件商品');
 const ids=new Set(),hosts={mediamarkt:'mediamarkt.de',amazon:'amazon.de',otto:'otto.de'};
 for(const p of products){
  if(!p||typeof p.id!=='string'||!(/^[a-zA-Z0-9_-]{1,90}$/).test(p.id)||ids.has(p.id))throw Error('商品ID无效或重复');ids.add(p.id);
  if(typeof p.name!=='string'||!p.name.trim()||p.name.length>160)throw Error('商品名称无效');
  if(p.enabled!==undefined&&typeof p.enabled!=='boolean')throw Error('enabled必须为布尔值');
  if(p.target_price!=null&&(!Number.isFinite(p.target_price)||p.target_price<0))throw Error('目标价格无效');
  if(!p.links||typeof p.links!=='object'||Array.isArray(p.links))throw Error('商品链接格式无效');
  for(const [shop,link] of Object.entries(p.links)){
   if(!(shop in hosts))throw Error('不支持的平台 '+shop);
   if(!link)continue;
   if(typeof link!=='string'||link.length>2000)throw Error('链接无效');
   let url;try{url=new URL(link)}catch{throw Error('链接格式无效')}
   const host=hosts[shop];if(url.protocol!=='https:'||!(url.hostname===host||url.hostname.endsWith('.'+host)))throw Error(shop+' 的链接域名不正确');
  }
 }
}
async function github(env,method,products,sha){
 const url=`https://api.github.com/repos/${encodeURIComponent(env.GITHUB_OWNER)}/${encodeURIComponent(env.GITHUB_REPO)}/contents/products.json`;
 const headers={'authorization':`Bearer ${env.GITHUB_REPO_TOKEN}`,'accept':'application/vnd.github+json','x-github-api-version':'2022-11-28','user-agent':'germany-price-tracker-v2'};
 if(method==='PUT')headers['content-type']='application/json';
 // IMPORTANT: GitHub Contents API needs STANDARD Base64, not base64url.
 const body=method==='PUT'?JSON.stringify({message:'Update monitored products via admin',content:toB64(encoder.encode(JSON.stringify(products,null,2)+'\n')),sha}):undefined;
 const res=await fetch(url,{method,headers,body});const data=await res.json().catch(()=>({}));
 if(!res.ok){const e=Error(data.message||`GitHub API HTTP ${res.status}`);e.status=res.status;throw e}
 return data;
}
function cors(req,env,response){const origin=req.headers.get('origin');if(origin===env.PAGES_ORIGIN){const h=new Headers(response.headers);h.set('access-control-allow-origin',origin);h.set('access-control-allow-credentials','true');h.set('vary','Origin');return new Response(response.body,{status:response.status,headers:h})}return response}
export default {async fetch(req,env){const u=new URL(req.url),path=u.pathname;
 try{
  if(['GITHUB_OWNER','GITHUB_REPO','GITHUB_REPO_TOKEN','GITHUB_CLIENT_ID','GITHUB_CLIENT_SECRET','ALLOWED_GITHUB_LOGIN','SESSION_SECRET','PAGES_ORIGIN'].some(k=>!env[k]))return reply({error:'Worker environment incomplete'},503);
  if(path==='/admin.html'&&req.method==='GET'){
   const target=new URL('admin.html',env.PAGES_ORIGIN+'/').href;
   const r=await fetch(target,{headers:{'cache-control':'no-cache'}});
   return new Response(r.body,{status:r.status,headers:{'content-type':'text/html; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}});
  }
  if(path==='/auth/login'){
   const state=b64url(crypto.getRandomValues(new Uint8Array(24)));
   const callback=new URL('/auth/callback',u.origin).href;
   const url=new URL('https://github.com/login/oauth/authorize');
   url.searchParams.set('client_id',env.GITHUB_CLIENT_ID);url.searchParams.set('redirect_uri',callback);url.searchParams.set('scope','read:user');url.searchParams.set('state',state);
   return redirect(url.href,[cookie('oauth_state',state,600)]);
  }
  if(path==='/auth/callback'){
   const c=cookies(req),state=u.searchParams.get('state');
   if(!state||state!==c.oauth_state)return reply({error:'OAuth state mismatch'},403);
   const r=await fetch('https://github.com/login/oauth/access_token',{method:'POST',headers:{accept:'application/json','content-type':'application/json','user-agent':'germany-price-tracker-v2'},body:JSON.stringify({client_id:env.GITHUB_CLIENT_ID,client_secret:env.GITHUB_CLIENT_SECRET,code:u.searchParams.get('code'),redirect_uri:new URL('/auth/callback',u.origin).href})});
   const token=(await r.json()).access_token;if(!token)return reply({error:'GitHub OAuth failed'},401);
   const ur=await fetch('https://api.github.com/user',{headers:{authorization:`Bearer ${token}`,'user-agent':'germany-price-tracker-v2','accept':'application/vnd.github+json'}});
   const profile=await ur.json();if(!ur.ok||String(profile.login||'').toLowerCase()!==env.ALLOWED_GITHUB_LOGIN.toLowerCase())return reply({error:'GitHub user not authorized'},403);
   const csrf=b64url(crypto.getRandomValues(new Uint8Array(24)));
   const session=await seal({login:profile.login,csrf,exp:Date.now()+7*86400000},env.SESSION_SECRET);
   return redirect(new URL('/admin.html',u.origin).href,[cookie('oauth_state','',0),cookie('pt_session',session,604800)]);
  }
  if(path==='/auth/logout')return redirect(new URL('/admin.html',u.origin).href,[cookie('pt_session','',0)]);
  const origin=req.headers.get('origin');if(origin&&origin!==u.origin&&origin!==env.PAGES_ORIGIN)return reply({error:'Origin rejected'},403);
  if(req.method==='OPTIONS')return cors(req,env,new Response(null,{status:204,headers:{'access-control-allow-methods':'GET,PUT,OPTIONS','access-control-allow-headers':'content-type,x-csrf-token'}}));
  const session=await unseal(cookies(req).pt_session||'',env.SESSION_SECRET);
  if(!session||session.exp<Date.now()||session.login.toLowerCase()!==env.ALLOWED_GITHUB_LOGIN.toLowerCase())return cors(req,env,reply({error:'not_authenticated'},401));
  if(path==='/api/me'&&req.method==='GET')return cors(req,env,reply({login:session.login,csrf:session.csrf}));
  if(path==='/api/products'&&req.method==='GET'){
   const data=await github(env,'GET');
   const bytes=Uint8Array.from(atob(data.content.replace(/\s/g,'')),c=>c.charCodeAt(0));
   return cors(req,env,reply({products:JSON.parse(decoder.decode(bytes)),sha:data.sha}));
  }
  if(path==='/api/products'&&req.method==='PUT'){
   if(req.headers.get('x-csrf-token')!==session.csrf)return cors(req,env,reply({error:'CSRF token mismatch'},403));
   const raw=await req.text();if(raw.length>350000)return cors(req,env,reply({error:'Payload too large'},413));
   const data=JSON.parse(raw);validate(data.products);
   if(!/^[a-f0-9]{40}$/.test(data.sha||''))throw Error('Missing version SHA');
   await github(env,'PUT',data.products,data.sha);
   return cors(req,env,reply({ok:true}));
  }
  return cors(req,env,reply({error:'Not found'},404));
 }catch(e){return cors(req,env,reply({error:e.message||'Server error'},e.status===409||e.status===422?409:e.status===401?401:400))}
}};
