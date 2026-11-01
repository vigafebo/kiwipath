/* Interactive SVG globe. Geographic projection: D3; Natural Earth geometry: world-atlas. */
(function(){
 'use strict';
 let nextId=0;
 const MIN_ZOOM=.75,MAX_ZOOM=40;
 window.createMemoryGlobe=function(container,cities,onSelect,initialView=null){
  const d3=window.d3,world=window.KiwiMemoryWorld,topo=window.topojson;
  if(!d3?.geoOrthographic||!world||!topo)throw new Error('Globe assets unavailable');
  const lifetime=new AbortController(),signal=lifetime.signal,ns='http://www.w3.org/2000/svg';
  const node=(tag,attrs={},parent=container)=>{
   const el=document.createElementNS(ns,tag);
   Object.entries(attrs).forEach(([key,value])=>el.setAttribute(key,value));
   parent.appendChild(el);return el;
  };
  container.replaceChildren();
  const helpId='memory-globe-help-'+(++nextId);
  const svg=node('svg',{class:'memory-globe-svg',tabindex:'0',role:'group','aria-label':'Globo interativo de cidades visitadas','aria-describedby':helpId});
  const defs=node('defs',{},svg),ocean=node('radialGradient',{id:helpId+'-ocean',cx:'35%',cy:'30%',r:'75%'},defs);
  node('stop',{offset:'0%','stop-color':'#d3e8e2'},ocean);
  node('stop',{offset:'100%','stop-color':'#8fbbb7'},ocean);
  const sphere=node('path',{class:'memory-globe-sphere',fill:'url(#'+helpId+'-ocean)'},svg);
  const grid=node('path',{class:'memory-globe-grid'},svg);
  const land=node('path',{class:'memory-globe-land'},svg);
  const borders=node('path',{class:'memory-globe-borders'},svg);
  const pins=node('g',{},svg),projection=d3.geoOrthographic().clipAngle(90),path=d3.geoPath(projection);
  const countries=topo.feature(world,world.objects.countries),mesh=topo.mesh(world,world.objects.countries,(a,b)=>a!==b),graticule=d3.geoGraticule10();
  const markers=new Map();
  cities.forEach(city=>{
   const pin=node('g',{'data-globe-city':city.key,class:'memory-globe-pin',role:'button',tabindex:'-1','aria-label':'Ver memórias de '+city.name},pins);
   node('circle',{r:'10',class:'memory-globe-pin-halo'},pin);
   node('circle',{r:'6',class:'memory-globe-pin-dot'},pin);
   const title=node('title',{},pin);title.textContent=city.name;
   pin.addEventListener('keydown',event=>{
    if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();select(city)}
   },{signal});
   pin.addEventListener('click',event=>{
    if(event.detail===0){event.stopPropagation();select(city)}
   },{signal});
   markers.set(city.key,pin);
  });
  const controls=document.createElement('div');controls.className='memory-globe-controls';
  controls.innerHTML='<button type="button" aria-label="Aproximar globo">+</button><button type="button" aria-label="Afastar globo">−</button>';
  container.appendChild(controls);
  controls.children[0].addEventListener('click',()=>zoomBy(1.25),{signal});
  controls.children[1].addEventListener('click',()=>zoomBy(1/1.25),{signal});
  const help=document.createElement('p');help.className='memory-globe-help';help.id=helpId;
  help.textContent='Arraste para girar · Use + e − ou dois dedos para aproximar · Setas do teclado para explorar';
  container.appendChild(help);
  const credit=document.createElement('small');credit.className='memory-globe-credit';credit.textContent='Geografia: Natural Earth';container.appendChild(credit);
  let longitude=Number.isFinite(initialView?.longitude)?initialView.longitude:0,
      latitude=Number.isFinite(initialView?.latitude)?Math.max(-90,Math.min(90,initialView.latitude)):20,
      zoom=Number.isFinite(initialView?.zoom)?Math.max(MIN_ZOOM,Math.min(MAX_ZOOM,initialView.zoom)):1,
      width=1,height=1,selected='',disposed=false;
  const pointers=new Map();
  let gesture=null,suppressClick=false;
  function draw(){
   if(disposed)return;
   projection.rotate([-longitude,-latitude,0]).translate([width/2,height/2]).scale(Math.min(width,height)*.41*zoom);
   sphere.setAttribute('d',path({type:'Sphere'}));
   grid.setAttribute('d',path(graticule));
   land.setAttribute('d',path(countries));
   borders.setAttribute('d',path(mesh));
   cities.forEach(city=>{
    const pin=markers.get(city.key),visible=d3.geoDistance([longitude,latitude],[city.longitude,city.latitude])<Math.PI/2-.015;
    pin.style.display=visible?'':'none';pin.setAttribute('tabindex',visible?'0':'-1');pin.setAttribute('aria-hidden',String(!visible));
    if(visible){const [x,y]=projection([city.longitude,city.latitude]);pin.setAttribute('transform','translate('+x+','+y+')')}
    pin.classList.toggle('is-selected',selected===city.key);
   });
   controls.children[0].disabled=zoom>=MAX_ZOOM;
   controls.children[1].disabled=zoom<=MIN_ZOOM;
  }
  function resize(){
   const rect=container.getBoundingClientRect();width=Math.max(1,rect.width);height=Math.max(1,rect.height);
   svg.setAttribute('viewBox','0 0 '+width+' '+height);draw();
  }
  function zoomBy(factor){zoom=Math.max(MIN_ZOOM,Math.min(MAX_ZOOM,zoom*factor));draw()}
  function select(city){selected=city.key;draw();onSelect(city)}
  function resetGesture(){
   const points=[...pointers.values()];
   gesture=points.length?{longitude,latitude,zoom,points:points.map(p=>({...p})),moved:false}:null;
  }
  svg.addEventListener('pointerdown',event=>{
   if(event.button!==0)return;
   if(!pointers.size)suppressClick=false;else suppressClick=true;
   svg.focus({preventScroll:true});pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});svg.setPointerCapture(event.pointerId);resetGesture();
   svg.classList.add('is-dragging');
  },{signal});
  svg.addEventListener('pointermove',event=>{
   if(!pointers.has(event.pointerId)||!gesture)return;
   pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
   const current=[...pointers.values()],first=current[0],start=gesture.points[0],dx=first.x-start.x,dy=first.y-start.y;
   if(Math.hypot(dx,dy)>4){gesture.moved=true;suppressClick=true}
   if(current.length===2&&gesture.points.length===2){
    const distance=points=>Math.hypot(points[1].x-points[0].x,points[1].y-points[0].y);
    zoom=Math.max(MIN_ZOOM,Math.min(MAX_ZOOM,gesture.zoom*distance(current)/Math.max(1,distance(gesture.points))));gesture.moved=true;
   }
   const sensitivity=160/Math.max(200,Math.min(width,height))/zoom;
   longitude=((gesture.longitude-dx*sensitivity+540)%360)-180;
   latitude=Math.max(-85,Math.min(85,gesture.latitude+dy*sensitivity));draw();
  },{signal});
  function endPointer(event,cancelled=false){
   if(!pointers.has(event.pointerId))return;
   const clicked=!cancelled&&pointers.size===1&&!gesture?.moved&&!suppressClick;
   const target=clicked?document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-globe-city]'):null;
   pointers.delete(event.pointerId);
   if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);
   resetGesture();
   if(!pointers.size)svg.classList.remove('is-dragging');
   if(target&&svg.contains(target)){const city=cities.find(c=>c.key===target.dataset.globeCity);if(city)select(city)}
  }
  svg.addEventListener('pointerup',event=>endPointer(event),{signal});
  svg.addEventListener('pointercancel',event=>endPointer(event,true),{signal});
  svg.addEventListener('wheel',event=>{
   if(document.activeElement!==svg&&!event.ctrlKey)return;
   event.preventDefault();zoomBy(Math.exp(-event.deltaY*.0015));
  },{signal,passive:false});
  svg.addEventListener('keydown',event=>{
   const step=12/zoom;
   if(event.key==='ArrowLeft')longitude-=step;
   else if(event.key==='ArrowRight')longitude+=step;
   else if(event.key==='ArrowUp')latitude=Math.min(85,latitude+step);
   else if(event.key==='ArrowDown')latitude=Math.max(-85,latitude-step);
   else if(event.key==='+'||event.key==='='){event.preventDefault();zoomBy(1.25);return}
   else if(event.key==='-'){event.preventDefault();zoomBy(1/1.25);return}
   else if(event.key==='Home'){event.preventDefault();reset();return}
   else return;
   event.preventDefault();longitude=((longitude+540)%360)-180;draw();
  },{signal});
  function reset(){longitude=0;latitude=20;zoom=1;selected='';draw()}
  const observer=new ResizeObserver(resize);observer.observe(container);resize();
  return {
   markers,
   getView:()=>({longitude,latitude,zoom}),
   reset,
   focusCity(city){longitude=city.longitude;latitude=city.latitude;zoom=2.2;select(city)},
   fitCities(){
    if(!cities.length)return;
    const center=d3.geoCentroid({type:'MultiPoint',coordinates:cities.map(c=>[c.longitude,c.latitude])});
    if(!center.every(Number.isFinite)){reset();return}
    longitude=center[0];latitude=center[1];
    const distance=Math.max(...cities.map(c=>d3.geoDistance(center,[c.longitude,c.latitude])));
    zoom=cities.length===1?2.2:Math.max(1,Math.min(3,.8/Math.sin(Math.min(Math.PI/2,Math.max(.2,distance)))));
    draw();
   },
   dispose(){disposed=true;lifetime.abort();observer.disconnect();pointers.clear();container.replaceChildren()}
  };
 };
})();
