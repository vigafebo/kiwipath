"""Travel regressions. Run: python3 -m unittest discover -s tests -v

Requires Python Playwright, pypdf and Chromium. All remote services are stubbed;
these tests never authenticate or change shared Supabase data.
"""
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
TRIP = dict(id="test-trip", name="Spain", destination="Madrid, España",
            latitude="40.4168", longitude="-3.7038", startDate="2026-10-15",
            endDate="2026-10-16", status="planning", owner="both",
            currency="EUR", itinerary=[], reservations=[], checklist=[], documentIds=[])


class TravelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(service_workers="block",timezone_id=getattr(self,"timezone_id","UTC"))
        self.page = self.context.new_page()
        self.errors = []
        self.route_requests = []
        self.routing_failure = False
        self.pdf_failure = False
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        source = (ROOT / "index.html").read_text()
        hooks = '''window.__travel = {
          reset(trip) { data={...initial(),trips:[trip],events:[]}; page="trips";
            activeTripId=trip.id; document.querySelector('#authScreen').style.display='none';
            document.querySelector('#kiwiApp').style.visibility='visible'; render(); },
          state:()=>data, open:()=>addTripItinerary(data.trips[0].id),
          points:tripMovementPoints, flight:tripFlightPath, countries:tripVisitedCountries, historyCountries:tripHistoryCountries, budget:tripBudgetSummary, warnings:tripItemWarnings, markerGroups:tripMapMarkerGroups, range:tripRange, sorted:tripSortedItinerary, exportEvent:downloadEventIcs, zone:()=>DEVICE_TIMEZONE, today:today,
          project:eventInDeviceZone, refreshZone:refreshDeviceTimeContext, eventIso:eventStartIso,
          event:editEvent, alert:editAlert, alerts:rows=>{customAlerts=rows}, alertDate:displayAlertDate,
          api:fn=>{supabaseClient.from=fn;currentUser={id:'test-user',email:'test@example.com'}}
        };'''
        source = source.replace("supabaseClient.auth.getSession().then", hooks + "\nsupabaseClient.auth.getSession().then")
        sdk = """window.supabase={createClient:()=>({auth:{
            getSession:()=>Promise.resolve({data:{session:null}}),onAuthStateChange:()=>{}},
            storage:{from:()=>({createSignedUrl:async path=>({data:{signedUrl:'https://files.test/'+path}})})}
        })};"""
        leaflet = '''window.__map={markers:[],lines:[],icons:[]};
        window.L={map:()=>({setView(){},fitBounds(){},invalidateSize(){},remove(){},on(){},
            latLngToLayerPoint:([lat,lon])=>({x:lon*1000,y:lat*1000}),
            layerPointToLatLng:({x,y})=>[y/1000,x/1000]}),
          tileLayer:()=>({addTo(){}}),latLngBounds:x=>x,divIcon:options=>options,
          marker:(ll,options)=>{__map.markers.push(ll);__map.icons.push(options.icon);
            return {addTo(){return this},bindPopup(){return this},on(){return this},openPopup(){return this},
              remove(){const index=__map.markers.indexOf(ll);if(index>=0)__map.markers.splice(index,1)}}},
          polyline:(ll,options)=>{const record={ll,options};__map.lines.push(record);
            return {addTo(){return this},setLatLngs(path){record.ll=path;return this},
              setStyle(style){Object.assign(record.options,style);return this}}}};'''

        def route(request):
            url = request.request.url
            if url == "http://kiwipath.test/kiwipath/":
                request.fulfill(body=source, content_type="text/html")
            elif "supabase-js" in url:
                request.fulfill(body=sdk, content_type="application/javascript")
            elif url.endswith("leaflet.js"):
                request.fulfill(body=leaflet, content_type="application/javascript")
            elif urlparse(url).path.startswith("/kiwipath/vendor/") or urlparse(url).path == "/kiwipath/trip-guide.js":
                local = ROOT / urlparse(url).path.removeprefix("/kiwipath/")
                request.fulfill(body=local.read_bytes(), content_type="font/ttf" if local.suffix==".ttf" else "application/javascript")
            elif "files.test/" in url:
                request.fulfill(body=b"invalid PDF" if self.pdf_failure else (ROOT / "tests/fixtures/voucher.pdf").read_bytes(), content_type="application/pdf")
            elif "brouter.de/brouter?" in url:
                params = parse_qs(urlparse(url).query)
                self.route_requests.append(params)
                if self.routing_failure:
                    request.fulfill(status=503, body="Unavailable")
                else:
                    ends = [[float(x) for x in pair.split(",")] for pair in params["lonlats"][0].split("|")]
                    coords = [ends[0], [(ends[0][0]+ends[1][0])/2, (ends[0][1]+ends[1][1])/2+0.1], ends[1]]
                    request.fulfill(body=json.dumps({"features":[{"properties":{"total-time":7200},"geometry":{"type":"LineString","coordinates":coords}}]}), content_type="application/json")
            elif "nominatim.openstreetmap.org" in url:
                query=parse_qs(urlparse(url).query).get('q',[''])[0]
                result=dict(name="Paris",lat="48.8566",lon="2.3522",address={"country":"France","country_code":"fr"}) if query=='Paris' else dict(name="Zürich",lat="47.3769",lon="8.5417",address={"country":"Schweiz","country_code":"ch"}) if query=='Zürich' else dict(name="Barcelona",lat="41.3874",lon="2.1686",address={"country":"España","country_code":"es"})
                request.fulfill(body=json.dumps([result]),content_type="application/json")
            else:
                request.fulfill(body="", content_type="text/css")
        self.page.route("**/*", route)
        self.page.goto("http://kiwipath.test/kiwipath/")
        self.page.evaluate("trip=>__travel.reset(trip)", TRIP)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.context.close()

    def test_map_connects_madrid_to_first_stop_and_ignores_empty_coordinates(self):
        trip = {**TRIP, "itinerary": [
            dict(title="Unselected", date="2026-10-15", latitude="", longitude=""),
            dict(title="Barcelona", location="Barcelona", date="2026-10-15", latitude="41.3874", longitude="2.1686", transport="train")]}
        self.page.evaluate("trip=>{__map.markers=[];__map.lines=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("__map.lines.length === 1")
        result = self.page.evaluate("__map")
        self.assertEqual(result["markers"], [[40.4168, -3.7038], [41.3874, 2.1686]])
        self.assertEqual(result["lines"][0]["options"]["color"], "#916eab")
        points = self.page.evaluate("__travel.points({itinerary:[{latitude:null,longitude:0},{latitude:'91',longitude:'0'},{latitude:'0',longitude:'0'}]})")
        self.assertEqual(len(points), 1)  # Real coordinates at zero remain valid.

    def test_save_after_cloud_replacement_keeps_item_event_and_location(self):
        self.page.evaluate("__travel.open()")
        self.page.locator("#f-title").fill("Ida")
        self.page.locator("#f-time").fill("10:30")
        self.page.locator("#f-itineraryLocationSearch").fill("Barcelona")
        self.page.locator("[data-itinerary-location='0']").click()
        self.page.locator("#f-kind").select_option("travel")
        self.page.locator("#f-transport").select_option("train")
        # A storage update follows the same state replacement as cloud refresh.
        self.page.evaluate("""() => window.dispatchEvent(new StorageEvent('storage', {
          key:'kiwipath.v1', newValue:JSON.stringify({...__travel.state(),
          trips:__travel.state().trips.map(t=>({...t,name:'Updated trip'}))})}))""")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertEqual(self.page.locator("#modalBackdrop").count(), 0)
        state = self.page.evaluate("JSON.parse(localStorage.getItem('kiwipath.v1'))")
        item = state["trips"][0]["itinerary"][0]
        self.assertEqual(item["title"], "Ida")
        self.assertEqual(item["latitude"], "41.3874")
        self.assertEqual(item["transport"], "train")
        self.assertEqual(state["events"][0]["title"], "Updated trip · Ida")
        self.page.reload()
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary.length"), 1)

    def test_search_enter_does_not_submit_and_free_text_can_save(self):
        self.page.evaluate("__travel.open()")
        self.page.locator("#f-title").fill("Walk")
        search = self.page.locator("#f-itineraryLocationSearch")
        search.fill("Park")
        search.press("Enter")
        self.assertEqual(self.page.locator("#modalBackdrop").count(), 1)
        self.page.locator("#f-toTimeline").select_option("no")
        self.page.locator("#itemForm button[type=submit]").click()
        state = self.page.evaluate("__travel.state()")
        self.assertEqual(state["trips"][0]["itinerary"][0]["location"], "Park")
        self.assertEqual(state["events"], [])

    def test_transport_profiles_legend_and_route_cache(self):
        for mode, profile in [("train", "rail"), ("car", "car-vario"), ("bus", "car-vario"),
                              ("taxi", "car-vario"), ("walk", "shortest")]:
            trip = {**TRIP, "itinerary": [dict(title="Stop", date="2026-10-15",
                    latitude="41.3874", longitude="2.1686", transport=mode)]}
            self.page.evaluate("trip=>{__map.lines=[];__travel.reset(trip)}", trip)
            self.page.wait_for_function("__map.lines.length===1 && __map.lines[0].ll.length===3")
            self.assertIsNone(self.page.evaluate("__map.lines[0].options.dashArray"))
            self.assertEqual(self.route_requests[-1]["profile"], [profile])
        # Bus/taxi share the road geometry rather than calling the service again.
        self.assertEqual(len(self.route_requests), 3)
        self.assertEqual(self.page.locator(".trip-map-legend span").all_text_contents(),
                         ["Caminhando", "Carro", "Ônibus", "Trem", "Avião", "Táxi"])

    def test_route_failure_retains_dotted_fallback_and_retries(self):
        self.routing_failure = True
        trip = {**TRIP, "itinerary": [dict(title="Stop", date="2026-10-15",
                latitude="41.3874", longitude="2.1686", transport="train")]}
        self.page.evaluate("trip=>{__map.lines=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("document.querySelector('#tripMapStatus').textContent.includes('sem rota disponível')")
        self.assertEqual(self.page.evaluate("__map.lines[0].ll.length"), 2)
        self.assertEqual(self.page.evaluate("__map.lines[0].options.dashArray"), "3 7")
        self.routing_failure = False
        self.page.evaluate("trip=>{__map.lines=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("__map.lines.length===1 && __map.lines[0].ll.length===3")
        self.assertEqual(len(self.route_requests), 2)

    def test_flights_curve_without_network_and_cross_date_line_safely(self):
        trip = {**TRIP, "itinerary": [dict(title="Paris", date="2026-10-15",
                latitude="48.8566", longitude="2.3522", transport="flight")]}
        self.page.evaluate("trip=>{__map.lines=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("__map.lines.length===1")
        line = self.page.evaluate("__map.lines[0]")
        self.assertEqual(len(line["ll"]), 65)
        self.assertEqual(line["options"]["dashArray"], "8 8")
        self.assertEqual(self.route_requests, [])
        path = self.page.evaluate("__travel.flight([35,170],[40,-170])")
        self.assertTrue(all(abs(b[1]-a[1]) < 180 for a, b in zip(path, path[1:])))
        self.assertAlmostEqual(path[-1][1], 190)

    def test_edit_duplicate_move_and_remove_keep_timeline_connected(self):
        self.page.evaluate("__travel.open()")
        self.page.locator("#f-title").fill("Museum")
        self.page.locator("#f-time").fill("10:00")
        self.page.locator("#f-endTime").fill("11:30")
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.get_by_role("button", name="Editar", exact=True).click()
        self.page.locator("#f-title").fill("Prado museum")
        self.page.locator("#itemForm button[type=submit]").click()
        state = self.page.evaluate("__travel.state()")
        self.assertEqual(len(state["trips"][0]["itinerary"]), 1)
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(state["events"][0]["title"], "Spain · Prado museum")
        self.page.get_by_role("button", name="Duplicar", exact=True).click()
        self.page.locator("#f-date").select_option("2026-10-16")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertEqual(self.page.evaluate("__travel.state().events.length"), 2)
        self.page.get_by_role("button", name="Mover dia", exact=True).click()
        self.page.locator("#f-date").select_option("2026-10-15")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertEqual(self.page.evaluate("__travel.state().events[1].date"), "2026-10-15")
        self.assertEqual(self.page.locator(".trip-itinerary").count(), 2)
        self.assertGreater(self.page.locator(".trip-item-warning").count(), 0)
        self.page.locator(".trip-itinerary").last.get_by_role("button", name="Remover", exact=True).click()
        self.page.get_by_role("button", name="Remover item", exact=True).click()
        self.assertEqual(self.page.evaluate("__travel.state().events.length"), 1)

    def test_explicit_origin_does_not_create_unrelated_segments(self):
        trip = {**TRIP, "itinerary": [
            dict(id="cafe", kind="activity", title="Cafe", date="2026-10-15", time="08:00", latitude="40", longitude="-3"),
            dict(id="train", kind="travel", title="Train", date="2026-10-15", time="10:00", latitude="41.3874", longitude="2.1686", transport="train", origin="Madrid station", originLatitude="40.4065", originLongitude="-3.6895")]}
        self.page.evaluate("trip=>{__map.lines=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("__map.lines.length===1 && __map.lines[0].ll.length===3")
        self.assertEqual(self.route_requests[0]["lonlats"], ["-3.6895,40.4065|2.1686,41.3874"])
        self.assertIn("2 h", self.page.locator('[data-route-for="train"]').inner_text())
        self.page.get_by_role("button", name="Mostrar Train no mapa").click()
        self.assertIn("selected", self.page.locator("#trip-item-train").get_attribute("class"))

    def test_legacy_event_is_adopted_without_duplicate(self):
        trip = {**TRIP, "itinerary":[dict(id="legacy", title="Museum", date="2026-10-15", time="10:00", location="Madrid", note="") ]}
        self.page.evaluate("trip=>__travel.reset(trip)", trip)
        self.page.evaluate("__travel.state().events=[{id:'old-event',tripId:'test-trip',title:'Spain · Museum',date:'2026-10-15',time:'10:00',location:'Madrid',note:''}]")
        self.page.get_by_role("button", name="Editar", exact=True).click()
        self.page.locator("#f-title").fill("Museum visit")
        self.page.locator("#itemForm button[type=submit]").click()
        state = self.page.evaluate("__travel.state()")
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(state["events"][0]["itineraryId"], "legacy")
        self.assertEqual(state["events"][0]["title"], "Spain · Museum visit")

    def test_reservation_payment_currency_and_edit_avoid_double_count(self):
        self.page.evaluate("__travel.state().accounts=[{id:'eur',name:'Euro',currency:'EUR',owner:'both'}]")
        self.page.locator('[data-action="travel-add-reservation:test-trip"]').click()
        self.page.locator("#f-title").fill("Hotel")
        self.page.locator("#f-type").select_option("stay")
        self.page.locator("#f-cost").fill("200,00")
        self.page.locator("#f-paidAmount").fill("80,00")
        self.page.locator("#f-startDate").fill("2026-10-15")
        self.page.locator("#f-endDate").fill("2026-10-16")
        self.page.locator("#f-accountId").select_option("eur")
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.locator('[data-action^="travel-edit-reservation:"]').click()
        self.page.locator("#f-paidAmount").fill("100,00")
        self.page.locator("#itemForm button[type=submit]").click()
        state = self.page.evaluate("__travel.state()")
        self.assertEqual(len(state["transactions"]), 1)
        self.assertEqual(state["transactions"][0]["amount"], 100)
        summary = self.page.evaluate("__travel.budget(__travel.state().trips[0])")
        self.assertEqual(summary["actual"], 100)
        self.assertEqual(summary["planned"], 200)
        self.assertIn("Pendente", self.page.locator(".trip-reservation").inner_text())

    def test_missing_conversion_not_silently_summed(self):
        self.page.evaluate("""() => {
            const state=__travel.state();state.accounts=[{id:'brl',currency:'BRL'}];
            state.transactions=[{type:'expense',tripId:'test-trip',accountId:'brl',amount:100}];
        }""")
        summary = self.page.evaluate("__travel.budget(__travel.state().trips[0])")
        self.assertEqual(summary["actual"], 0)
        self.assertEqual(summary["unconverted"], 1)
        self.page.evaluate("__travel.state().trips[0].exchangeRates={BRL:0.2}")
        self.assertEqual(self.page.evaluate("__travel.budget(__travel.state().trips[0]).actual"), 20)

    def test_checklist_owner_due_and_offline_guide(self):
        self.page.locator('[data-action="travel-add-check:test-trip"]').click()
        self.page.locator("#f-title").fill("Travel insurance")
        self.page.locator("#f-owner").select_option("zack")
        self.page.locator("#f-due").fill("2026-10-01")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertIn("Zack", self.page.locator(".trip-check").inner_text())
        self.assertIn("Prazo vencido", self.page.locator(".trip-check").inner_text())
        self.page.get_by_role("button", name="Compartilhar guia PDF").click()
        with self.page.expect_download() as download:
            self.page.get_by_role("button", name="Baixar PDF", exact=True).click()
        reader = PdfReader(download.value.path())
        contents = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Travel insurance", contents)
        self.assertIn("Madrid", contents)
        self.assertTrue(download.value.suggested_filename.endswith(".pdf"))
        self.page.get_by_role("button", name="Fechar", exact=True).click()
        self.page.get_by_role("button", name="Modo em viagem", exact=True).click()
        self.assertIn("trip-travel-mode", self.page.locator(".trip-dashboard").get_attribute("class"))

    def test_guide_includes_available_pdf_and_mobile_has_no_overflow(self):
        self.page.set_viewport_size({"width":390,"height":844})
        self.page.evaluate("__travel.state().documents=[{id:'voucher',tripId:'test-trip',title:'Train ticket',filePath:'shared/test.pdf',fileName:'ticket.pdf'}]")
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth"), 390)
        self.page.get_by_role("button", name="Compartilhar guia PDF").click()
        with self.page.expect_download() as download:
            self.page.get_by_role("button", name="Baixar PDF", exact=True).click()
        reader = PdfReader(download.value.path())
        self.assertEqual(len(reader.pages), 3)
        self.assertIn("TEST VOUCHER - TRAIN MADRID", reader.pages[-1].extract_text())
        self.page.get_by_role("button", name="Fechar", exact=True).click()
        self.page.locator('[data-action="travel-add-document:test-trip"]').click()
        self.assertEqual(self.page.locator("#f-tripId").input_value(), "test-trip")
        self.assertEqual(self.page.locator("#f-pdfFile").count(), 1)

    def test_time_warning_and_outside_dates_are_nonblocking(self):
        trip = {**TRIP, "itinerary":[dict(id="train",kind="travel",title="Train",
                date="2026-10-15",time="10:00",endTime="11:00",latitude="41.3874",longitude="2.1686",
                origin="Madrid",originLatitude="40.4168",originLongitude="-3.7038",transport="train")]}
        self.page.evaluate("trip=>{__map.lines=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("document.querySelector('[data-route-for]').textContent.includes('tempo reservado')")
        warnings = self.page.evaluate("__travel.warnings(__travel.state().trips[0],{id:'outside',date:'2026-11-01'})")
        self.assertIn("Fora das datas da viagem", warnings)
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary.length"), 1)

    def test_unlinked_itinerary_removal_requires_confirmation_and_can_cancel(self):
        trip = {**TRIP, "itinerary":[dict(id="walk",kind="activity",title="Walk",date="2026-10-15")]}
        self.page.evaluate("trip=>__travel.reset(trip)", trip)
        self.page.get_by_role("button", name="Remover", exact=True).click()
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary.length"), 1)
        self.page.get_by_role("button", name="Manter item", exact=True).click()
        self.assertEqual(self.page.locator(".trip-itinerary").count(), 1)
        self.page.get_by_role("button", name="Remover", exact=True).click()
        self.page.get_by_role("button", name="Remover item", exact=True).click()
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary.length"), 0)

    def test_nearby_map_numbers_are_grouped_and_icons_have_fixed_anchors(self):
        trip = {**TRIP, "itinerary":[
            dict(id="one",title="First",date="2026-10-15",latitude="40.4168",longitude="-3.7038"),
            dict(id="two",title="Second",date="2026-10-15",latitude="40.42",longitude="-3.70")]}
        self.page.evaluate("trip=>{__map.icons=[];__travel.reset(trip)}", trip)
        self.page.wait_for_function("__map.icons.some(icon=>icon.html.includes('2 locais'))")
        cluster = self.page.evaluate("__map.icons.find(icon=>icon.html.includes('2 locais'))")
        self.assertEqual(cluster["iconAnchor"], [33,16])
        self.assertEqual(cluster["iconSize"], [66,32])
        # Zooming in separates the stops; colocated points remain selectable together.
        counts = self.page.evaluate("""() => {
            const points=__travel.points(__travel.state().trips[0]);
            return [1000,100000].map(scale=>__travel.markerGroups(points,{
                latLngToLayerPoint:([lat,lon])=>({x:lon*scale,y:lat*scale})}).length);
        }""")
        self.assertEqual(counts, [1,2])

    def test_native_pdf_share_receives_real_pdf_file(self):
        self.page.evaluate("""() => {
          Object.defineProperty(navigator,'canShare',{configurable:true,value:({files})=>files[0].type==='application/pdf'});
          Object.defineProperty(navigator,'share',{configurable:true,value:async ({files})=>{
            window.__shared={name:files[0].name,type:files[0].type,header:await files[0].slice(0,5).text(),active:navigator.userActivation.isActive};
          }});
        }""")
        self.page.get_by_role("button", name="Compartilhar guia PDF").click()
        self.page.wait_for_function("window.__shared || document.querySelector('[data-pdf-share]')")
        if not self.page.evaluate("!!window.__shared"):
            self.page.get_by_role("button", name="Compartilhar PDF", exact=True).click()
        self.page.wait_for_function("window.__shared")
        shared = self.page.evaluate("window.__shared")
        self.assertEqual(shared["header"], "%PDF-")
        self.assertEqual(shared["type"], "application/pdf")
        self.assertTrue(shared["active"])

    def test_invalid_pdf_is_reported_and_share_cancellation_can_retry(self):
        self.pdf_failure = True
        self.page.evaluate("__travel.state().documents=[{id:'bad',tripId:'test-trip',title:'Unavailable voucher',filePath:'shared/bad.pdf'}]")
        self.page.evaluate("""() => {
          window.__shareCalls=0;
          Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>true});
          Object.defineProperty(navigator,'share',{configurable:true,value:async()=>{window.__shareCalls++;throw new DOMException('Canceled','AbortError')}});
        }""")
        self.page.get_by_role("button", name="Compartilhar guia PDF").click()
        self.page.get_by_role("dialog", name="Seu guia está pronto").wait_for()
        self.assertIn("Unavailable voucher", self.page.locator("#tripGuideBackdrop .trip-item-warning").inner_text())
        self.assertEqual(self.page.evaluate("__shareCalls"), 0)
        self.page.get_by_role("button", name="Compartilhar PDF", exact=True).click()
        self.assertEqual(self.page.evaluate("__shareCalls"), 1)
        self.assertEqual(self.page.get_by_role("button", name="Baixar PDF", exact=True).count(), 1)

    def test_pdf_paginates_long_unicode_itinerary(self):
        trip = {**TRIP, "name":"São Paulo e Москва", "itinerary":[
            dict(id=str(i),title="Passeio histórico número "+str(i),date="2026-10-15",location="Madrid, España",note="Informação de viagem e café. "*25)
            for i in range(18)]}
        self.page.evaluate("trip=>__travel.reset(trip)", trip)
        self.page.get_by_role("button", name="Compartilhar guia PDF").click()
        with self.page.expect_download() as download:
            self.page.get_by_role("button", name="Baixar PDF", exact=True).click()
        reader = PdfReader(download.value.path())
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertGreater(len(reader.pages), 3)
        self.assertIn("São Paulo e Москва", text)
        self.assertIn("histórico número 17", text)
        self.assertIn("Checklist de preparação", text)

    def test_activity_status_advances_next_pending_and_persists(self):
        self.page.clock.set_fixed_time("2026-10-15T07:00:00Z")
        trip = {**TRIP,"timeZone":"Europe/Madrid","itinerary":[
            dict(id=str(i),title="Activity "+str(i),kind="activity",date="2026-10-15",time=str(10+i)+":00",timeZone="Europe/Madrid") for i in range(3)]}
        self.page.evaluate("trip=>__travel.reset(trip)",trip)
        self.assertIn("Activity 0",self.page.locator(".trip-now h2").inner_text())
        self.page.locator('[data-action="travel-status:test-trip:0:done"]').click()
        self.assertIn("Activity 1",self.page.locator(".trip-now h2").inner_text())
        self.page.locator('[data-action="travel-status:test-trip:1:skipped"]').click()
        self.assertIn("Activity 2",self.page.locator(".trip-now h2").inner_text())
        self.page.locator('[data-action="travel-status:test-trip:0:pending"]').click()
        self.assertIn("Activity 0",self.page.locator(".trip-now h2").inner_text())
        self.page.reload()
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary[1].status"),"skipped")

    def test_overnight_timezones_convert_calendar_and_detect_overlap(self):
        self.page.evaluate("__travel.open()")
        self.page.locator("#f-title").fill("Overnight flight")
        self.page.locator("#f-time").fill("23:30")
        self.page.locator("#f-timeZone").fill("Europe/Madrid")
        self.page.locator("#f-endDate").fill("2026-10-16")
        self.page.locator("#f-endTime").fill("05:00")
        self.page.locator("#f-endTimeZone").fill("America/Sao_Paulo")
        self.page.locator("#itemForm button[type=submit]").click()
        state=self.page.evaluate("__travel.state()")
        self.assertEqual(state["events"][0]["date"],"2026-10-16")
        self.assertEqual(state["events"][0]["time"],"10:30")
        self.assertEqual(state["events"][0]["sourceTimeZone"],"Europe/Madrid")
        duration=self.page.evaluate("(()=>{const t=__travel.state().trips[0],r=__travel.range(t.itinerary[0],t);return (r.end-r.start)/3600000})()")
        self.assertEqual(duration,10.5)
        self.assertEqual(state['events'][0]['endAt'],'2026-10-16T08:00:00.000Z')
        with self.page.expect_download() as download:
            self.page.evaluate('__travel.exportEvent(__travel.state().events[0].id)')
        ics=Path(download.value.path()).read_text()
        self.assertIn('DTSTART:20261015T213000Z',ics)
        self.assertIn('DTEND:20261016T080000Z',ics)

        warning=self.page.evaluate("""() => {
          const t=__travel.state().trips[0];t.itinerary.push({id:'other',date:'2026-10-16',time:'09:00',timeZone:'Europe/Paris'});
          return __travel.warnings(t,t.itinerary[0]);
        }""")
        self.assertIn("Horário coincide com outro item",warning)

    def test_invalid_zone_and_nonexistent_dst_time_do_not_save(self):
        self.page.evaluate("trip=>__travel.reset({...trip,startDate:'2026-03-29',endDate:'2026-03-30'})",TRIP)
        self.page.evaluate("__travel.open()")
        self.page.locator("#f-title").fill("DST gap")
        self.page.locator("#f-time").fill("02:30")
        self.page.locator("#f-timeZone").fill("Invalid/Zone")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertIn("fuso válido",self.page.locator("#toast").inner_text())
        self.page.locator("#f-timeZone").fill("Europe/Madrid")
        self.page.locator("#f-endTimeZone").fill("Europe/Madrid")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertIn("não existe",self.page.locator("#toast").inner_text())
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary.length"),0)

    def test_reservation_generates_and_updates_connected_stay_items(self):
        self.page.locator('[data-action="travel-add-reservation:test-trip"]').click()
        self.page.locator("#f-title").fill("Madrid hotel")
        self.page.locator("#f-type").select_option("stay")
        self.page.locator("#f-startDate").fill("2026-10-15")
        self.page.locator("#f-time").fill("15:00")
        self.page.locator("#f-endDate").fill("2026-10-16")
        self.page.locator("#f-endTime").fill("11:00")
        self.page.locator("#f-timeZone").fill("Europe/Madrid")
        self.page.locator("#f-endTimeZone").fill("Europe/Madrid")
        self.page.locator("#itemForm button[type=submit]").click()
        state=self.page.evaluate("__travel.state()")
        self.assertEqual(len(state["trips"][0]["itinerary"]),2)
        self.assertEqual(len(state["events"]),2)
        ids=[item["id"] for item in state["trips"][0]["itinerary"]]
        self.page.locator('[data-action^="travel-edit-reservation:"]').click()
        self.page.locator("#f-time").fill("16:00")
        self.page.locator("#itemForm button[type=submit]").click()
        state=self.page.evaluate("__travel.state()")
        self.assertEqual([item["id"] for item in state["trips"][0]["itinerary"]],ids)
        self.assertEqual(state["trips"][0]["itinerary"][0]["time"],"16:00")
        self.assertEqual(len(state["events"]),2)
        self.assertEqual(state["transactions"],[])
        self.page.locator('[data-action^="travel-edit-itinerary:"]').first.click()
        self.assertEqual(self.page.locator("#modalTitle").inner_text(),"Editar reserva")

    def test_reorder_previews_route_changes_and_drag_order_persists(self):
        trip={**TRIP,"itinerary":[
            dict(id='a',title='Barcelona',kind='activity',date='2026-10-15',time='08:00',location='Barcelona',latitude='41.38',longitude='2.16'),
            dict(id='b',title='Paris',kind='travel',date='2026-10-15',time='10:00',location='Paris',latitude='48.85',longitude='2.35',transport='train',originSource='previous',origin='Barcelona',originLatitude='41.38',originLongitude='2.16'),
            dict(id='c',title='Lyon',kind='activity',date='2026-10-15',time='12:00',location='Lyon',latitude='45.76',longitude='4.83')]}
        self.page.evaluate("trip=>__travel.reset(trip)",trip)
        self.page.get_by_role('button',name='Mover Lyon para cima',exact=True).click()
        self.assertIn('Lyon → Paris',self.page.locator('.trip-order-preview').inner_text())
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary[1].origin"),'Barcelona')
        self.page.locator('#cancelModal').click()
        self.page.get_by_role('button',name='Mover Lyon para cima',exact=True).click()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate("__travel.sorted(__travel.state().trips[0]).map(x=>x.id)"),['a','c','b'])
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary[1].origin"),'Lyon')
        self.page.locator('[data-drag-itinerary="b"]').drag_to(self.page.locator('#trip-item-a'))
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate("__travel.sorted(__travel.state().trips[0]).map(x=>x.id)"),['b','a','c'])
        self.page.reload()
        self.assertEqual(self.page.evaluate("__travel.sorted(__travel.state().trips[0]).map(x=>x.id)"),['b','a','c'])

    def test_saved_place_can_be_scheduled_without_losing_the_library_entry(self):
        self.page.locator('[data-action="travel-place-new:test-trip"]').click()
        self.page.locator('#f-title').fill('Restaurant idea')
        self.page.locator('#f-category').select_option('Restaurante')
        self.page.locator('#f-itineraryLocationSearch').fill('Barcelona')
        self.page.locator('[data-itinerary-location="0"]').click()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].itinerary.length'),0)
        self.page.get_by_role('button',name='Adicionar ao roteiro',exact=True).click()
        self.assertEqual(self.page.locator('#f-title').input_value(),'Restaurant idea')
        self.page.locator('#f-date').select_option('2026-10-16')
        self.page.locator('#itemForm button[type=submit]').click()
        state=self.page.evaluate('__travel.state()')
        self.assertEqual(len(state['trips'][0]['savedPlaces']),1)
        self.assertEqual(state['trips'][0]['itinerary'][0]['date'],'2026-10-16')
        self.assertEqual(state['trips'][0]['itinerary'][0]['latitude'],'41.3874')
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth'),390)

    def test_map_day_filter_keeps_departure_context_and_can_show_all(self):
        trip={**TRIP,"itinerary":[
            dict(id='a',title='First day',date='2026-10-15',latitude='40.41',longitude='-3.7'),
            dict(id='b',title='Second day',date='2026-10-16',latitude='41.38',longitude='2.16',transport='train')]}
        self.page.evaluate("trip=>__travel.reset(trip)",trip)
        self.page.locator('[data-action="travel-day:test-trip:2026-10-16"]').click()
        self.page.wait_for_function("document.querySelector('#tripMapDayFilter').value==='2026-10-16'")
        points=self.page.evaluate("__travel.points(__travel.state().trips[0],'2026-10-16')")
        self.assertEqual(len(points),2)
        self.assertEqual(points[0]['latitude'],'40.41')
        self.assertFalse(points[0]['connect'])
        self.assertEqual(points[1]['itineraryId'],'b')
        self.page.get_by_role('button',name='Ver viagem inteira',exact=True).click()
        self.assertEqual(self.page.locator('#tripMapDayFilter').input_value(),'all')
        self.assertEqual(len(self.page.evaluate('__travel.points(__travel.state().trips[0])')),3)

    def test_flight_reservation_stays_linked_and_removed_parts_stay_removed(self):
        self.page.locator('[data-action="travel-add-reservation:test-trip"]').click()
        self.page.locator('#f-title').fill('Madrid to Paris')
        self.page.locator('#f-startDate').fill('2026-10-15')
        self.page.locator('#f-time').fill('10:00')
        self.page.locator('#f-timeZone').fill('Europe/Madrid')
        self.page.locator('#f-endDate').fill('2026-10-15')
        self.page.locator('#f-endTime').fill('12:00')
        self.page.locator('#f-endTimeZone').fill('Europe/Paris')
        self.page.locator('#itemForm button[type=submit]').click()
        state=self.page.evaluate('__travel.state()')
        item=state['trips'][0]['itinerary'][0]
        self.assertEqual(item['kind'],'travel')
        self.assertEqual(item['transport'],'flight')
        self.assertEqual(len(state['events']),1)
        self.page.locator('[data-action^="travel-remove-itinerary:"]').click()
        self.page.get_by_role('button',name='Remover item',exact=True).click()
        self.page.locator('[data-action^="travel-edit-reservation:"]').click()
        self.page.locator('#f-title').fill('Updated flight')
        self.page.locator('#itemForm button[type=submit]').click()
        state=self.page.evaluate('__travel.state()')
        self.assertEqual(state['trips'][0]['itinerary'],[])
        self.assertEqual(state['events'],[])

    def test_stale_order_preview_rejects_concurrent_time_change(self):
        trip={**TRIP,'itinerary':[
            dict(id='a',title='A',date='2026-10-15',time='10:00'),
            dict(id='b',title='B',date='2026-10-15',time='11:00')]}
        self.page.evaluate('trip=>__travel.reset(trip)',trip)
        self.page.get_by_role('button',name='Mover B para cima',exact=True).click()
        self.page.evaluate("__travel.state().trips[0].itinerary[0].time='09:00'")
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertIn('roteiro mudou',self.page.locator('#toast').inner_text())
        self.assertEqual(self.page.locator('#modalBackdrop').count(),1)
        self.assertEqual(self.page.evaluate('__travel.sorted(__travel.state().trips[0]).map(x=>x.id)'),['a','b'])

    def test_pdf_preserves_manual_order_status_zones_and_saved_places(self):
        trip={**TRIP,'itinerary':[
            dict(id='a',title='Morning museum',date='2026-10-15',time='10:00',timeZone='Europe/Madrid',sequence=1),
            dict(id='b',title='Evening walk',date='2026-10-15',time='19:00',timeZone='Europe/Madrid',sequence=0,status='done')],
            'savedPlaces':[dict(id='idea',title='Saved restaurant',location='Madrid')]}
        self.page.evaluate('trip=>__travel.reset(trip)',trip)
        self.page.get_by_role('button',name='Compartilhar guia PDF').click()
        with self.page.expect_download() as download:self.page.get_by_role('button',name='Baixar PDF',exact=True).click()
        text='\n'.join(page.extract_text() for page in PdfReader(download.value.path()).pages)
        self.assertLess(text.index('Evening walk'),text.index('Morning museum'))
        self.assertIn('Europe/Madrid',text)
        self.assertIn('Feito',text)
        self.assertIn('Saved restaurant',text)

    def test_moving_to_dst_gap_keeps_original_item_unchanged(self):
        trip={**TRIP,'startDate':'2026-03-28','endDate':'2026-03-30','itinerary':[
            dict(id='dst',title='Early activity',date='2026-03-28',time='02:30',timeZone='Europe/Madrid')]}
        self.page.evaluate('trip=>__travel.reset(trip)',trip)
        self.page.get_by_role('button',name='Mover dia',exact=True).click()
        self.page.locator('#f-date').select_option('2026-03-29')
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertIn('não existe',self.page.locator('#toast').inner_text())
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].itinerary[0].date'),'2026-03-28')

    def in_time_zone(self,zone):
        self.context.close();self.timezone_id=zone;self.setUp()

    def mock_database(self):
        self.page.evaluate("""() => {
          window.__writes=[];
          const query=table=>new Proxy({}, {get(target,key){
            if(key==='then')return resolve=>Promise.resolve({data:[],error:null}).then(resolve);
            if(key==='maybeSingle'||key==='single')return ()=>Promise.resolve({data:null,error:null});
            return (...args)=>{if(key==='insert'||key==='update'||key==='upsert')__writes.push({table,action:key,payload:args[0]});return query(table)};
          }});
          __travel.api(query);
        }""")

    def test_device_zone_clocks_and_local_day_differ_from_nz(self):
        self.in_time_zone('America/Sao_Paulo')
        self.page.clock.set_fixed_time('2030-01-01T01:00:00Z')
        self.page.locator('#profileMenuToggle').click()
        self.page.evaluate('__travel.refreshZone()')
        self.assertEqual(self.page.evaluate('__travel.zone()'),'America/Sao_Paulo')
        self.assertEqual(self.page.evaluate('__travel.today()'),'2029-12-31')
        self.assertIn('22:00:00',self.page.locator('#deviceLocalClock').inner_text())
        self.assertIn('14:00:00',self.page.locator('#deviceNzClock').inner_text())
        self.assertTrue(self.page.locator('#deviceNzClockRow').is_visible())
        self.assertEqual(self.page.locator('#deviceClockZone').inner_text(),'America/Sao_Paulo')
        self.assertLessEqual(self.page.locator('#profileMenu').bounding_box()['height'],760)

    def test_nz_device_hides_duplicate_clock(self):
        self.in_time_zone('Pacific/Auckland')
        self.page.locator('#profileMenuToggle').click()
        self.assertFalse(self.page.locator('#deviceNzClockRow').is_visible())
        self.assertEqual(self.page.evaluate('__travel.zone()'),'Pacific/Auckland')

    def test_legacy_event_is_projected_without_changing_instant_or_date_only_items(self):
        self.in_time_zone('America/Sao_Paulo')
        raw=dict(id='legacy',title='NZ morning',date='2030-01-02',time='09:00')
        projected=self.page.evaluate('event=>__travel.project(event)',raw)
        self.assertEqual(projected['date'],'2030-01-01')
        self.assertEqual(projected['time'],'17:00')
        self.assertEqual(self.page.evaluate('event=>__travel.eventIso(event)',raw),'2030-01-01T20:00:00.000Z')
        date_only=dict(id='date',title='Anniversary',date='2030-01-02')
        self.assertEqual(self.page.evaluate('event=>__travel.project(event)',date_only)['date'],'2030-01-02')
        self.page.evaluate('event=>{__travel.state().events=[event];__travel.event(event.id)}',raw)
        self.assertEqual(self.page.locator('#f-date').input_value(),'2030-01-01')
        self.assertEqual(self.page.locator('#f-time').input_value(),'17:00')
        self.assertEqual(self.page.evaluate('__travel.state().events[0].date'),'2030-01-02')
        self.page.locator('#cancelModal').click()
        self.page.locator('#navigation [data-page="timeline"]').click()
        self.assertIn('17:00',self.page.locator('.event-timebox').first.inner_text())
        self.assertEqual(self.page.evaluate('__travel.state().events[0].date'),'2030-01-02')


    def test_device_zone_changes_refresh_view_without_rewriting_event(self):
        self.in_time_zone('America/Sao_Paulo')
        self.page.evaluate("__travel.state().events=[{id:'legacy',date:'2030-01-02',time:'09:00'}]")
        original=self.page.evaluate('JSON.stringify(__travel.state().events)')
        self.page.evaluate("""() => {
          const native=Intl.DateTimeFormat.prototype.resolvedOptions;
          Intl.DateTimeFormat.prototype.resolvedOptions=function(){return {...native.call(this),timeZone:'Europe/Paris'}};
          __travel.refreshZone();
        }""")
        self.assertEqual(self.page.evaluate('__travel.zone()'),'Europe/Paris')
        self.assertEqual(self.page.evaluate('JSON.stringify(__travel.state().events)'),original)
        self.assertEqual(self.page.evaluate('__travel.project(__travel.state().events[0]).time'),'21:00')

    def test_new_event_sends_utc_reminders_for_device_zone(self):
        self.in_time_zone('America/Sao_Paulo')
        self.page.clock.set_fixed_time('2030-01-01T00:00:00Z');self.mock_database()
        self.page.evaluate('__travel.event()')
        self.page.locator('#f-title').fill('Local appointment')
        self.page.locator('#f-date').fill('2030-01-03')
        self.page.locator('#f-time').fill('09:00')
        self.page.locator('#itemForm button[type=submit]').click()
        self.page.wait_for_function('!document.querySelector("#modalBackdrop")')
        state=self.page.evaluate('__travel.state()')
        self.assertEqual(state['events'][-1]['timeZone'],'America/Sao_Paulo')
        reminders=self.page.evaluate("__writes.filter(x=>x.table==='kiwipath_custom_alerts'&&x.action==='insert').map(x=>x.payload)")
        self.assertEqual(len(reminders),2)
        self.assertEqual(reminders[0]['scheduled_at'],'2030-01-02T12:00:00.000Z')
        self.assertEqual(reminders[1]['scheduled_at'],'2030-01-03T09:00:00.000Z')
        self.assertTrue(all(row['timezone']=='America/Sao_Paulo' for row in reminders))
        self.assertEqual(self.page.evaluate('__travel.eventIso(__travel.state().events.at(-1))'),'2030-01-03T12:00:00.000Z')


    def test_custom_alert_uses_device_zone_and_preserves_existing_repeat_zone(self):
        self.in_time_zone('America/Sao_Paulo');self.mock_database()
        self.page.clock.set_fixed_time('2030-01-01T00:00:00Z')
        self.page.evaluate('__travel.alert()')
        self.assertEqual(self.page.locator('#f-timeZone').input_value(),'America/Sao_Paulo')
        self.page.locator('#f-title').fill('Local alert')
        self.page.locator('#f-scheduledAt').fill('2030-01-03T09:00')
        self.page.locator('#itemForm button[type=submit]').click()
        self.page.wait_for_function('!document.querySelector("#modalBackdrop")')
        payload=self.page.evaluate("__writes.find(x=>x.table==='kiwipath_custom_alerts'&&x.action==='insert').payload")
        self.assertEqual(payload['scheduled_at'],'2030-01-03T12:00:00.000Z')
        self.assertEqual(payload['timezone'],'America/Sao_Paulo')
        self.page.evaluate("""() => {
          __travel.alerts([{id:'repeat',title:'Existing repeat',recurrence:'daily',timezone:'Pacific/Auckland',scheduled_at:'2030-01-03T20:00:00Z',status:'pending'}]);
          __travel.alert('repeat');
        }""")
        self.assertEqual(self.page.locator('#f-timeZone').input_value(),'Pacific/Auckland')
        self.assertEqual(self.page.locator('#f-scheduledAt').input_value(),'2030-01-04T09:00')
        self.page.locator('#itemForm button[type=submit]').click()
        self.page.wait_for_function('!document.querySelector("#modalBackdrop")')
        repeat=self.page.evaluate("__writes.filter(x=>x.table==='kiwipath_custom_alerts'&&x.action==='update').at(-1).payload")
        self.assertEqual(repeat['scheduled_at'],'2030-01-03T20:00:00.000Z')
        self.assertEqual(repeat['timezone'],'Pacific/Auckland')


    def test_editing_alert_during_repeated_dst_hour_preserves_utc_instant(self):
        self.in_time_zone('Europe/Paris');self.mock_database()
        self.page.clock.set_fixed_time('2026-10-24T00:00:00Z')
        self.page.evaluate("""() => {
          __travel.alerts([{id:'repeat-hour',title:'First 02:30',recurrence:'once',timezone:'Europe/Paris',scheduled_at:'2026-10-25T00:30:00Z',status:'pending'}]);
          __travel.alert('repeat-hour');
        }""")
        self.assertEqual(self.page.locator('#f-scheduledAt').input_value(),'2026-10-25T02:30')
        self.page.locator('#f-title').fill('Title only changed')
        self.page.locator('#itemForm button[type=submit]').click()
        self.page.wait_for_function('!document.querySelector("#modalBackdrop")')
        payload=self.page.evaluate("__writes.filter(x=>x.table==='kiwipath_custom_alerts'&&x.action==='update').at(-1).payload")
        self.assertEqual(payload['scheduled_at'],'2026-10-25T00:30:00.000Z')

    def test_history_collects_all_trip_countries_once_and_excludes_saved_or_skipped(self):
        trip={**TRIP,'status':'done','country':'Espanha','countryCode':'ES','itinerary':[
            dict(id='fr',title='Paris',location='Paris, France',countryCode='fr'),
            dict(id='fr2',title='Lyon',location='Lyon, France',countryCode='FR'),
            dict(id='it',title='Rome',location='Roma, Italia',origin='Paris, France',transport='train'),
            dict(id='skipped',title='Berlin',location='Berlin, Germany',countryCode='de',status='skipped')],
            'savedPlaces':[dict(id='idea',title='Lisbon',countryCode='pt',location='Lisboa, Portugal')]}
        self.page.evaluate('trip=>__travel.reset(trip)',trip)
        codes=self.page.evaluate('__travel.countries(__travel.state().trips[0]).map(x=>x.code)')
        self.assertEqual(set(codes),{'es','fr','it'})
        self.page.locator('[data-action="travel-back"]').click()
        self.page.locator('[data-action="travel-history"]').click()
        self.assertEqual(self.page.locator('.trip-history-country').count(),3)
        self.assertEqual(self.page.locator('.trip-history-country-list .trip-chip').count(),3)
        self.assertIn('França',self.page.locator('.trip-history-country-list').inner_text())
        self.assertNotIn('Alemanha',self.page.locator('.trip-history-country-list').inner_text())
        counts=self.page.evaluate("__travel.historyCountries([__travel.state().trips[0],{countryCode:'fr',itinerary:[]}])")
        self.assertEqual(next(row['count'] for row in counts if row['code']=='fr'),2)
        self.assertEqual(next(row['count'] for row in counts if row['code']=='it'),1)

    def test_legacy_country_labels_and_reservation_origins_are_recognized(self):
        trip={**TRIP,'countryCode':'es','itinerary':[
            dict(id='pt',location='Lisboa, Portugal'),dict(id='fr',location='Paris, France'),
            dict(id='uk',location='London, United Kingdom'),dict(id='unknown',location='Paris')],
            'reservations':[dict(id='train',location='Roma, Itália',origin='Zürich, Schweiz') ]}
        countries=self.page.evaluate('trip=>__travel.countries(trip)',trip)
        self.assertEqual({country['code'] for country in countries},{'es','pt','fr','gb','it','ch'})
        self.assertEqual(self.page.evaluate("__travel.countries({destination:'Paris',itinerary:[]})"),[])

    def test_country_metadata_survives_search_saved_place_schedule_and_edit(self):
        self.page.locator('[data-action="travel-place-new:test-trip"]').click()
        self.page.locator('#f-title').fill('Barcelona visit')
        self.page.locator('#f-itineraryLocationSearch').fill('Barcelona')
        self.page.locator('[data-itinerary-location="0"]').click()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].savedPlaces[0].countryCode'),'es')
        self.page.get_by_role('button',name='Adicionar ao roteiro',exact=True).click()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].itinerary[0].countryCode'),'es')
        self.page.locator('[data-action^="travel-edit-itinerary:"]').click()
        self.page.locator('#f-title').fill('Updated visit')
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].itinerary[0].countryCode'),'es')

    def test_history_can_add_transit_country_without_itinerary_stop(self):
        trip={**TRIP,'status':'done','countryCode':'es','itinerary':[dict(id='fr',location='Paris, France')]}
        self.page.evaluate('trip=>__travel.reset(trip)',trip)
        self.page.locator('[data-action="travel-back"]').click()
        self.page.locator('[data-action="travel-history"]').click()
        self.page.get_by_role('button',name='Países visitados',exact=True).click()
        self.page.locator('#tripCountrySearch').fill('Suíça')
        self.page.locator('input[name="country_ch"]').check()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.locator('.trip-history-country').count(),3)
        self.assertIn('Suíça',self.page.locator('.trip-history-country-list').inner_text())
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].visitedCountries'),['ch'])
        self.page.reload()
        self.assertEqual(self.page.evaluate('__travel.state().trips[0].visitedCountries'),['ch'])

    def test_reservation_country_metadata_reaches_connected_transfer(self):
        self.page.locator('[data-action="travel-add-reservation:test-trip"]').click()
        self.page.locator('#f-title').fill('Zürich to Paris')
        self.page.locator('#f-originLocationSearch').fill('Zürich')
        self.page.locator('#tripOriginLocationResults [data-itinerary-location="0"]').click()
        self.page.locator('#f-itineraryLocationSearch').fill('Paris')
        self.page.locator('#tripItineraryLocationResults [data-itinerary-location="0"]').click()
        self.page.locator('#itemForm button[type=submit]').click()
        state=self.page.evaluate('__travel.state()')
        reservation=state['trips'][0]['reservations'][0]
        item=state['trips'][0]['itinerary'][0]
        self.assertEqual((reservation['originCountryCode'],reservation['countryCode']),('ch','fr'))
        self.assertEqual((item['originCountryCode'],item['countryCode']),('ch','fr'))
        self.assertEqual({row['code'] for row in self.page.evaluate('__travel.countries(__travel.state().trips[0])')},{'es','ch','fr'})

    def test_deleted_trip_does_not_report_a_successful_save(self):
        self.page.evaluate("__travel.open()")
        self.page.locator("#f-title").fill("Ida")
        self.page.evaluate("__travel.state().trips=[]")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertEqual(self.page.locator("#modalBackdrop").count(), 1)
        self.assertIn("removida", self.page.locator("#toast").inner_text())
        self.assertEqual(self.page.evaluate("__travel.state().events.length"), 0)


if __name__ == "__main__":
    unittest.main()
