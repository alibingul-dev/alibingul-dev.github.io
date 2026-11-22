/* Agent Resume service worker: network first, cached copy when offline. Same-origin GET only. */
var C='ar-v10';
var SHELL=['./','index.html','team.html','profile.html','policy.html','announcements.html','announcements.json','i18n.js','rep.js','social.js','posts.json','ads.json','manifest.webmanifest','icon-192.png','icon-512.png'];
self.addEventListener('install',function(e){e.waitUntil(caches.open(C).then(function(c){return Promise.all(SHELL.map(function(u){return c.add(u).catch(function(){});}));}).then(function(){return self.skipWaiting();}));});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.filter(function(k){return k!==C;}).map(function(k){return caches.delete(k);}));}).then(function(){return self.clients.claim();}));});
self.addEventListener('fetch',function(e){
  var r=e.request; if(r.method!=='GET') return;
  var u=new URL(r.url); if(u.origin!==location.origin) return;
  e.respondWith(fetch(r).then(function(res){ if(res&&res.ok&&res.type==='basic'){var cp=res.clone(); caches.open(C).then(function(c){c.put(r,cp);});} return res; })
    .catch(function(){return caches.match(r,{ignoreSearch:u.pathname.slice(-5)==='.html'}).then(function(m){return m||caches.match('index.html');});}));
});
self.addEventListener('notificationclick',function(e){e.notification.close(); var u=(e.notification.data&&e.notification.data.url)||'index.html';
  e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(function(cs){for(var i=0;i<cs.length;i++){if('focus' in cs[i]){cs[i].navigate(u); return cs[i].focus();}} return self.clients.openWindow(u);}));});
