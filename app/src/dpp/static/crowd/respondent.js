(() => {
  const app = document.querySelector('#app');
  if (!app || app.dataset.collectable !== 'true') return;
  const token = app.dataset.token;
  const preview = app.dataset.preview === 'true';
  const questions = [...document.querySelectorAll('.question')];
  const welcome = document.querySelector('#welcome'), survey = document.querySelector('#survey'), thanks = document.querySelector('#thanks');
  let index = 0, locationFix = null, recording = null, recordedChunks = [], voiceAnswer = new Set();
  const dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open('crowd-responses-v1', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('pending', { keyPath: 'client_id' });
    req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
  });
  const requestLocation = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Dieses Gerät unterstützt keine Standortbestimmung.'));
    navigator.geolocation.getCurrentPosition(pos => {
      if (pos.coords.accuracy > 100) return reject(new Error('Der Standort ist noch zu ungenau. Bitte versuche es erneut.'));
      locationFix = { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy_m: pos.coords.accuracy, at: Date.now() };
      resolve(locationFix);
    }, () => reject(new Error('Bitte erlaube den Standortzugriff, um teilzunehmen.')), { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  });
  const setError = message => { document.querySelector('#welcome-error').textContent = message || ''; };
  const updatePending = async () => {
    try { const db = await dbPromise, tx = db.transaction('pending'), req = tx.objectStore('pending').count(); req.onsuccess = () => { const target=document.querySelector('#sync-count'); if(target) target.textContent=req.result ? `${req.result} Antwort(en) warten auf Übertragung.` : ''; const thanksText=document.querySelector('#thanks-sync'); if(thanksText) thanksText.textContent=req.result ? 'Die Antwort wird übertragen, sobald eine Verbindung besteht.' : ''; }; } catch (_) {}
  };
  async function syncPending() {
    try { const db=await dbPromise, tx=db.transaction('pending','readonly'), req=tx.objectStore('pending').getAll(); req.onsuccess=async()=>{ for(const item of req.result){ try{const response=await fetch(`/crowd/api/r/${token}/responses`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)}); if(response.ok || response.status===410){const del=db.transaction('pending','readwrite');del.objectStore('pending').delete(item.client_id);} }catch(_){break;} } updatePending(); }; } catch (_) {}
  }
  const uuid = () => crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return(c==='x'?r:(r&3|8)).toString(16)});
  const answerFor = question => {
    if(question.dataset.type==='text') return question.querySelector('textarea').value.trim();
    const selected=[...question.querySelectorAll('input:checked')].map(el=>el.value);
    return question.dataset.type==='single_choice' ? (selected[0]||'') : selected;
  };
  function showQuestion() { questions.forEach((q,i)=>q.classList.toggle('active',i===index));document.querySelector('#progress').textContent=`${index+1} von ${questions.length}`;document.querySelector('#back').disabled=index===0;document.querySelector('#next').textContent=index===questions.length-1?'Antwort senden':'Weiter';document.querySelector('#question-error').textContent=''; }
  document.querySelector('#start').addEventListener('click', async () => {
    try { if(document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen().catch(()=>{}); if(!preview) await requestLocation(); welcome.hidden=true;survey.hidden=false;showQuestion();if(!preview)syncPending(); }
    catch(error){setError(error.message);document.querySelector('#gps-retry').hidden=false;}
  });
  document.querySelector('#gps-retry').addEventListener('click',async()=>{try{await requestLocation();setError('Standort verfügbar. Tippe auf Start.');document.querySelector('#gps-retry').hidden=true;}catch(error){setError(error.message);}});
  document.querySelector('#back').addEventListener('click',()=>{if(index>0){index--;showQuestion();}});
  document.querySelector('#next').addEventListener('click',async()=>{
    const q=questions[index], answer=answerFor(q), missing=Array.isArray(answer)?answer.length===0:!answer;
    if(q.dataset.required==='true'&&missing){document.querySelector('#question-error').textContent='Bitte beantworte diese Pflichtfrage.';return;}
    if(index<questions.length-1){index++;showQuestion();return;}
    if(preview){survey.hidden=true;thanks.hidden=false;setTimeout(()=>{questions.forEach(question=>{question.querySelectorAll('textarea').forEach(el=>el.value='');question.querySelectorAll('input').forEach(el=>el.checked=false);});index=0;thanks.hidden=true;welcome.hidden=false;showQuestion();},5000);return;}
    document.querySelector('#next').disabled=true;document.querySelector('#question-error').textContent='Standort wird geprüft …';
    try {
      try { await requestLocation(); }
      catch(error) { if(!locationFix || Date.now()-locationFix.at>300000) throw error; }
      const answers={};questions.forEach(question=>{const val=answerFor(question);if(val && (!Array.isArray(val)||val.length))answers[question.dataset.questionId]={text:question.dataset.type==='text'?val:undefined,options:Array.isArray(val)?val:(question.dataset.type==='single_choice'?[val]:[]),via_voice:voiceAnswer.has(question.dataset.questionId)};});
      // The API expects text values directly for text questions and option IDs for choices.
      questions.forEach(question=>{if(question.dataset.type==='text'&&answers[question.dataset.questionId])answers[question.dataset.questionId]={text:answerFor(question),via_voice:voiceAnswer.has(question.dataset.questionId)};else if(question.dataset.type!=='text'&&answers[question.dataset.questionId])answers[question.dataset.questionId]=Array.isArray(answerFor(question))?answerFor(question):answerFor(question);});
      const payload={client_id:uuid(),captured_at:new Date().toISOString(),latitude:locationFix.latitude,longitude:locationFix.longitude,accuracy_m:locationFix.accuracy_m,answers};
      const db=await dbPromise,tx=db.transaction('pending','readwrite');tx.objectStore('pending').put(payload);await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
      survey.hidden=true;thanks.hidden=false;updatePending();await syncPending();
      setTimeout(()=>{questions.forEach(question=>{question.querySelectorAll('textarea').forEach(el=>el.value='');question.querySelectorAll('input').forEach(el=>el.checked=false);});voiceAnswer.clear();index=0;thanks.hidden=true;welcome.hidden=false;document.querySelector('#next').disabled=false;locationFix=null;setError('');updatePending();},5000);
    } catch(error){document.querySelector('#question-error').textContent=error.message;document.querySelector('#next').disabled=false;}
  });
  document.querySelectorAll('[data-mic]').forEach(button=>button.addEventListener('click',async()=>{
    const fieldset=button.closest('.question'), textarea=fieldset.querySelector('textarea'), status=fieldset.querySelector('[data-mic-status]');
    if(recording){recording.stop();button.textContent='🎙 Antwort einsprechen';return;}
    try {const stream=await navigator.mediaDevices.getUserMedia({audio:true});const mime=MediaRecorder.isTypeSupported('audio/webm;codecs=opus')?'audio/webm;codecs=opus':undefined;recording=new MediaRecorder(stream,mime?{mimeType:mime}:{});recordedChunks=[];recording.ondataavailable=e=>{if(e.data.size)recordedChunks.push(e.data);};recording.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());const blob=new Blob(recordedChunks,{type:recording.mimeType||'audio/webm'});recording=null;if(blob.size>5*1024*1024){status.textContent='Aufnahme ist zu groß.';return;}status.textContent='Transkription läuft …';try{const contentType=blob.type.split(';')[0]||'audio/webm';const response=await fetch(`/crowd/api/r/${token}/transcribe`,{method:'POST',headers:{'Content-Type':contentType},body:blob});if(!response.ok)throw new Error();const result=await response.json();textarea.value=((textarea.value?textarea.value+' ':'')+result.text).slice(0,500);voiceAnswer.add(fieldset.dataset.questionId);status.textContent='Text eingefügt – bitte prüfen.';}catch(_){status.textContent='Transkription nicht möglich. Du kannst tippen.';}};recording.start();button.textContent='Aufnahme beenden';status.textContent='Aufnahme läuft (max. 60 Sekunden)';setTimeout(()=>{if(recording&&recording.state==='recording')recording.stop();},60000);}
    catch(_){status.textContent='Mikrofonzugriff nicht verfügbar.';}
  }));
  const setMicAvailability=()=>document.querySelectorAll('[data-mic]').forEach(button=>{button.disabled=!navigator.onLine;button.setAttribute('aria-disabled',String(!navigator.onLine));});
  setMicAvailability();window.addEventListener('online',setMicAvailability);window.addEventListener('offline',setMicAvailability);
  window.addEventListener('online',syncPending);document.addEventListener('visibilitychange',()=>{if(!document.hidden)syncPending();});
  if(!preview){if('serviceWorker' in navigator)navigator.serviceWorker.register('/crowd/r/sw.js',{scope:'/crowd/r/'}).then(()=>navigator.serviceWorker.ready).then(registration=>registration.active?.postMessage({type:'CACHE_URL',url:location.href})).catch(()=>{});syncPending();updatePending();}
})();
