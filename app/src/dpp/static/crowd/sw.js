const CACHE='crowd-respondent-v1';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/static/css/output.css','/static/crowd/crowd.css','/static/crowd/respondent.js']))));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('message',event=>{
  if(event.data?.type==='CACHE_URL'&&typeof event.data.url==='string'){
    const url=new URL(event.data.url);
    if(url.origin===location.origin&&url.pathname.startsWith('/crowd/r/'))event.waitUntil(caches.open(CACHE).then(cache=>cache.add(url.href)));
  }
});
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==location.origin||url.pathname.startsWith('/crowd/api/'))return;
  event.respondWith(caches.match(request).then(cached=>{
    const network=fetch(request).then(response=>{if(response.ok&&response.type==='basic'){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy));}return response;});
    return cached||network.catch(()=>caches.match('/static/css/output.css'));
  }));
});
