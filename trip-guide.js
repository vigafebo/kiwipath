/* KiwiPath PDF guide. Dependencies and Unicode font are served from this site. */
(() => {
 'use strict';
 const base=new URL('./',document.currentScript?.src||document.baseURI);
 let dependencies,fontBytes;
 function script(file,ready){
  if(ready())return Promise.resolve();
  return new Promise((resolve,reject)=>{
   const node=document.createElement('script');node.src=new URL(file,base).href;
   node.onload=()=>ready()?resolve():reject(new Error('Biblioteca PDF indisponível.'));
   node.onerror=()=>{node.remove();reject(new Error('Não foi possível carregar o gerador de PDF.'))};document.head.appendChild(node);
  });
 }
 async function load(){
  if(!dependencies)dependencies=Promise.all([
   script('vendor/pdf-lib-1.17.1.min.js',()=>!!window.PDFLib),
   script('vendor/fontkit-1.1.1.min.js',()=>!!window.fontkit)
  ]).catch(error=>{dependencies=null;throw error});
  await dependencies;
  if(!fontBytes)fontBytes=fetch(new URL('vendor/DejaVuSans.ttf',base)).then(response=>{if(!response.ok)throw new Error('Fonte do PDF indisponível.');return response.arrayBuffer()}).catch(error=>{fontBytes=null;throw error});
  return fontBytes;
 }
 async function create({trip,documents=[],loadDocument,formatDate,formatMoney,transportLabel}){
  const bytes=await load(),{PDFDocument,rgb}=window.PDFLib,pdf=await PDFDocument.create();pdf.registerFontkit(window.fontkit);
  const font=await pdf.embedFont(bytes,{subset:true}),supported=new Set(font.getCharacterSet());
  const clean=value=>Array.from(String(value??'').replace(/\t/g,'  ')).map(c=>c==='\n'||supported.has(c.codePointAt(0))?c:'?').join('');
  const colors={forest:rgb(.09,.24,.19),muted:rgb(.36,.44,.39),sage:rgb(.91,.95,.88),cream:rgb(.985,.981,.956),line:rgb(.85,.9,.82),white:rgb(1,1,1)};
  const width=595.28,height=841.89,margin=44,content=width-margin*2,guidePages=[];let page,y;
  const wrap=(value,size,maxWidth=content)=>{
   const lines=[];
   for(const paragraph of clean(value).split('\n')){
    let line='';
    for(const character of paragraph){
     if(line&&font.widthOfTextAtSize(line+character,size)>maxWidth){
      const space=line.lastIndexOf(' ');
      if(space>line.length/2){lines.push(line.slice(0,space));line=line.slice(space+1)+character}else{lines.push(line);line=character}
     }else line+=character;
    }
    lines.push(line);
   }
   return lines;
  };
  function newPage(){
   page=pdf.addPage([width,height]);guidePages.push(page);y=height-74;
   page.drawRectangle({x:0,y:0,width,height,color:colors.cream});
   page.drawText('KIWIPATH',{x:margin,y:height-35,size:10,font,color:colors.forest});
   page.drawText('GUIA DE VIAGEM',{x:width-margin-100,y:height-35,size:8,font,color:colors.muted});
   page.drawLine({start:{x:margin,y:height-47},end:{x:width-margin,y:height-47},thickness:.7,color:colors.line});
  }
  function space(required){if(y-required<56)newPage()}
  function paragraph(value,{size=10,color=colors.forest,indent=0,gap=5}={}){
   for(const line of wrap(value,size,content-indent)){
    space(size*1.5);page.drawText(line,{x:margin+indent,y,size,font,color});y-=size*1.5;
   }y-=gap;
  }
  function section(title){space(56);y-=10;page.drawRectangle({x:margin,y:y-10,width:content,height:30,color:colors.sage});page.drawText(clean(title),{x:margin+12,y,size:12,font,color:colors.forest});y-=33}
  function separator(){space(12);page.drawLine({start:{x:margin,y},end:{x:width-margin,y},thickness:.5,color:colors.line});y-=16}
  const date=value=>value?formatDate(value):'Data a definir';
  newPage();
  const titleLines=wrap(trip.name||'Nossa viagem',26).slice(0,5),heroHeight=95+titleLines.length*33;
  page.drawRectangle({x:margin-12,y:y-heroHeight,width:content+24,height:heroHeight+12,color:colors.forest});
  let titleY=y-27;
  titleLines.forEach(line=>{page.drawText(line,{x:margin+8,y:titleY,size:26,font,color:colors.white});titleY-=33});
  const destinationLines=wrap(trip.destination||'Destino a definir',11,content-20).slice(0,2);
  destinationLines.forEach(line=>{page.drawText(line,{x:margin+8,y:titleY-7,size:11,font,color:colors.white});titleY-=16});
  page.drawText(clean(date(trip.startDate)+' → '+date(trip.endDate)),{x:margin+8,y:y-heroHeight+19,size:10,font,color:colors.white});
  y-=heroHeight+30;
  paragraph('Seu roteiro, reservas e documentos em um só lugar.',{size:12});
  paragraph('Preparado em '+new Date().toLocaleDateString('pt-BR')+'. Cópia para consulta offline; mapas e alterações posteriores precisam de conexão.',{size:8,color:colors.muted,gap:12});
  const itinerary=(trip.itinerary||[]).slice().sort((a,b)=>((a.date||'9999')+(a.time||'')).localeCompare((b.date||'9999')+(b.time||'')));
  section('Roteiro dia a dia');
  if(!itinerary.length)paragraph('Roteiro ainda não definido.',{color:colors.muted});
  let lastDay;
  itinerary.forEach((item,index)=>{
   if(item.date!==lastDay||index===0){space(64);paragraph(date(item.date),{size:11,gap:10});lastDay=item.date}
   space(55);page.drawCircle({x:margin+10,y:y-1,size:10,color:colors.forest});
   const number=String(index+1);page.drawText(number,{x:margin+10-font.widthOfTextAtSize(number,8)/2,y:y-4,size:8,font,color:colors.white});
   paragraph(item.title||'Atividade',{size:12,indent:29});
   paragraph((item.time||'Horário livre')+(item.endTime?' – '+item.endTime:'')+(item.transport?' · '+transportLabel(item.transport):''),{size:9,color:colors.muted,indent:29});
   if(item.origin||item.location)paragraph((item.origin?item.origin+' → ':'')+(item.location||''),{size:10,indent:29});
   if(item.note)paragraph(item.note,{size:9,color:colors.muted,indent:29});separator();
  });
  section('Reservas e passagens');
  if(!(trip.reservations||[]).length)paragraph('Nenhuma reserva cadastrada.',{color:colors.muted});
  for(const reservation of trip.reservations||[]){
   space(65);paragraph(reservation.title,{size:12});
   paragraph(date(reservation.startDate)+(reservation.time?' · '+reservation.time:'')+(reservation.endDate?' → '+date(reservation.endDate)+(reservation.endTime?' · '+reservation.endTime:''):''),{size:9,color:colors.muted});
   if(reservation.provider||reservation.reference)paragraph([reservation.provider,reservation.reference?'Confirmação: '+reservation.reference:''].filter(Boolean).join(' · '));
   if(reservation.location)paragraph(reservation.location);
   paragraph('Total: '+formatMoney(reservation.cost||0,reservation.currency||trip.currency)+'  ·  Pago: '+formatMoney(reservation.paidAmount||0,reservation.currency||trip.currency)+'  ·  Pendente: '+formatMoney(Math.max(0,(reservation.cost||0)-(reservation.paidAmount||0)),reservation.currency||trip.currency),{size:9});
   if(reservation.note)paragraph(reservation.note,{size:9,color:colors.muted});separator();
  }
  section('Checklist de preparação');
  if(!(trip.checklist||[]).length)paragraph('Nenhum item de preparação cadastrado.',{color:colors.muted});
  for(const item of trip.checklist||[]){
   space(44);page.drawRectangle({x:margin,y:y-2,width:9,height:9,borderColor:colors.muted,borderWidth:.8,color:item.done?colors.forest:colors.white});
   paragraph(item.title,{indent:20,size:10});paragraph((item.done?'Concluído':'Pendente')+' · '+(item.owner==='vitor'?'Vitor':item.owner==='zack'?'Zack':'Vitor & Zack')+(item.due?' · Prazo: '+date(item.due):''),{indent:20,size:8,color:colors.muted});
  }
  const attachments=[],missing=[];
  for(const document of documents){
   if(!document.filePath)continue;
   try{
    const attachment=await PDFDocument.load(await loadDocument(document));
    const copied=await pdf.copyPages(attachment,attachment.getPageIndices());
    if(!copied.length)throw new Error('PDF sem páginas');attachments.push({document,pages:copied});
   }catch(error){missing.push(document.title||'Comprovante')}
  }
  section('Documentos e comprovantes');
  if(!documents.length)paragraph('Nenhum documento cadastrado.',{color:colors.muted});
  for(const document of documents){
   paragraph(document.title,{size:11});
   paragraph((document.expiryDate?'Validade: '+date(document.expiryDate)+' · ':'')+(attachments.some(a=>a.document.id===document.id)?'PDF incluído nas páginas seguintes.':document.filePath?'Não incluído: indisponível ou formato inválido.':'Sem arquivo PDF.'),{size:8,color:colors.muted});
  }
  if(missing.length)paragraph('Não foi possível incluir: '+missing.join(', ')+'.',{size:9});
  for(const attachment of attachments){
   newPage();section(attachment.document.title||'Comprovante');paragraph('Comprovante original nas páginas seguintes.',{color:colors.muted});
   attachment.pages.forEach(copied=>pdf.addPage(copied));
  }
  const all=pdf.getPages();
  guidePages.forEach(sheet=>{
   const number=all.indexOf(sheet)+1;
   sheet.drawLine({start:{x:margin,y:39},end:{x:width-margin,y:39},thickness:.5,color:colors.line});
   sheet.drawText('KiwiPath · '+number+' / '+all.length,{x:margin,y:25,size:8,font,color:colors.muted});
  });
  pdf.setTitle(clean((trip.name||'Viagem')+' · Guia de viagem'));pdf.setAuthor('KiwiPath');pdf.setSubject('Roteiro e comprovantes de viagem');pdf.setLanguage('pt-BR');
  return {bytes:await pdf.save(),missing};
 }
 window.KiwiTripGuide={create};
})();
