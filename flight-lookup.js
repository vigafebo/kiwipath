/* Free external flight research. These links do not import or verify flight data. */
(function(){
 'use strict';
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const normalize=value=>String(value||'').toUpperCase().replace(/[\s-]/g,'');
 function fields(old={}){
  return '<section id="tripFlightLookup" class="field full trip-flight-lookup" aria-label="Pesquisar voo"><strong>Pesquisar voo</strong><p>Use o número do voo, não o código da reserva. Consulte a data nas fontes públicas. Companhia, horários e aeroportos devem ser conferidos e preenchidos abaixo.</p><div class="trip-flight-grid"><div class="field"><label for="f-flightDate">Data do voo na origem</label><input type="date" id="f-flightDate" name="flightDate" value="'+escape(old.startDate||'')+'"></div><div class="field"><label for="f-flightNumber">Número do voo</label><input type="text" id="f-flightNumber" name="flightNumber" maxlength="9" placeholder="Ex.: LA803" autocomplete="off" autocapitalize="characters" spellcheck="false" value="'+escape(old.flightNumber||'')+'"></div></div><button type="button" class="trip-add" id="tripFlightSearch">Pesquisar voo</button><p id="tripFlightStatus" class="file-hint" role="status" aria-live="polite"></p><div id="tripFlightResults" class="trip-flight-links" hidden></div></section>';
 }
 function setup(root){
  const q=selector=>root.querySelector(selector),panel=q('#tripFlightLookup'),code=q('#f-flightNumber'),date=q('#f-flightDate'),results=q('#tripFlightResults'),status=q('#tripFlightStatus');
  const clear=()=>{results.replaceChildren();results.hidden=true;status.textContent=''};
  const update=()=>{panel.hidden=q('#f-type').value!=='flight';clear()};
  q('#f-type').addEventListener('change',update);update();
  code.addEventListener('input',clear);date.addEventListener('input',clear);
  date.addEventListener('change',()=>{if(q('#f-type').value==='flight')q('#f-startDate').value=date.value});
  q('#f-startDate').addEventListener('input',()=>{date.value=q('#f-startDate').value;clear()});
  q('#tripFlightSearch').addEventListener('click',()=>{
   clear();const number=normalize(code.value),day=date.value;code.value=number;
   if(!/^(?=.*[A-Z])[A-Z0-9]{2,3}\d{1,4}[A-Z]?$/.test(number)||!day||!date.checkValidity()){
    status.textContent='Informe a data e um número de voo válido, como LA803.';return;
   }
   const query=number+' '+day+' voo horários origem destino companhia';
   for(const [label,url] of [
    ['Abrir no FlightRadar24','https://www.flightradar24.com/data/flights/'+encodeURIComponent(number.toLowerCase())],
    ['Pesquisar na web','https://www.google.com/search?q='+encodeURIComponent(query)]
   ]){
    const link=document.createElement('a');link.className='trip-add';link.textContent=label;link.href=url;link.target='_blank';link.rel='noopener noreferrer';results.appendChild(link);
   }
   results.hidden=false;
   status.textContent='Pesquisa para '+number+' em '+day+'. No FlightRadar24, confira a data na página. Os dados não são importados automaticamente.';
  });
 }
 window.KiwiFlightLookup={fields,setup};
})();
