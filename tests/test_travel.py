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
          inspectDay(day) { tripSelectedDays.set(data.trips[0].id,day);
            tripMapDays.set(data.trips[0].id,'all'); render(); },
          voucherStorage(fn) { supabaseClient.storage.from=fn;currentUser={id:'test-user'};
            isApplyingCloudData=true; },
          memories(trips,visits=[]) { data={...initial(),trips,memoryVisits:visits,events:[]};page='trips';
            activeTripId='';tripsView='history';tripMemoryYear='all';tripMemoryView='map';
            document.querySelector('#authScreen').style.display='none';
            document.querySelector('#kiwiApp').style.visibility='visible';render(); },
          refreshCloud:loadCloudData, redraw:render,
          memoryCities:tripMemoryCities, memoryEntries:tripMemoryTrips,
          worldCountries:()=>[...TRIP_WORLD_COUNTRIES], memoryMap:()=>tripMemoryMap,
          mapSession:()=>tripMapSession, state:()=>data, open:()=>addTripItinerary(data.trips[0].id),
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
            elif urlparse(url).path.startswith("/kiwipath/vendor/") or urlparse(url).path in ("/kiwipath/trip-guide.js","/kiwipath/memory-globe.js"):
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

    def test_real_leaflet_popup_survives_autopan_and_pending_route(self):
        self.page.add_script_tag(path=str(ROOT / "tests/fixtures/leaflet/leaflet.js"))
        self.page.add_style_tag(path=str(ROOT / "tests/fixtures/leaflet/leaflet.css"))
        for clustered in (False, True):
            with self.subTest(clustered=clustered):
                pending = []
                released = [False]
                def finish_route(route):
                    params=parse_qs(urlparse(route.request.url).query)
                    ends=[[float(x) for x in pair.split(",")] for pair in params["lonlats"][0].split("|")]
                    route.fulfill(body=json.dumps({"features":[{"properties":{"total-time":7200},
                        "geometry":{"type":"LineString","coordinates":[ends[0],[0,45],ends[1]]}}]}),
                        content_type="application/json")
                self.page.route("**/brouter?**", lambda route: finish_route(route) if released[0] else pending.append(route))
                items = [dict(id="edge", title="Edge stop", location="Barcelona",
                              date="2026-10-16", latitude="41.3874",
                              longitude="2.1686", transport="car")]
                if clustered:
                    items.append({**items[0], "id":"nearby", "title":"Nearby stop"})
                self.page.evaluate("trip=>{__travel.reset(trip);__travel.inspectDay('2026-10-15')}", {**TRIP, "itinerary":items})
                self.page.wait_for_function("__travel.mapSession()?.markers.has('edge')")
                self.page.wait_for_function("document.querySelector('#tripMapStatus').textContent.includes('Calculando')")
                self.page.evaluate("""()=>{
                  const session=__travel.mapSession(),map=session.map;
                  map.setView([41.3874,2.1686],13,{animate:false});
                  map.panBy([0,145],{animate:false});
                  window.__edgeMarker=session.markers.get('edge');
                  window.__autoPans=0;window.__mapMoves=0;
                  map.on('autopanstart',()=>window.__autoPans++);
                  map.on('moveend',()=>window.__mapMoves++);
                }""")
                self.page.locator("#tripMovementMap").scroll_into_view_if_needed()
                selector = ".trip-map-pin.is-cluster" if clustered else ".trip-map-pin"
                if clustered:
                    self.page.locator(selector).click()
                else:
                    self.page.locator(".leaflet-marker-icon[title='Edge stop']").click()
                self.page.wait_for_function("window.__autoPans>0 && window.__mapMoves>0")
                self.page.wait_for_function("!__travel.mapSession().map._panAnim?._inProgress")
                self.assertTrue(self.page.evaluate("__edgeMarker.isPopupOpen()"))
                self.assertTrue(self.page.evaluate("__travel.mapSession().focused"))
                self.assertEqual(self.page.locator(".trip-timeline-item.selected").count(), 0)
                self.assertEqual(self.page.locator("#trip-item-edge").count(), 0)
                center = self.page.evaluate("__travel.mapSession().map.getCenter()")
                self.assertTrue(pending)
                released[0] = True
                for route in pending:
                    finish_route(route)
                self.page.wait_for_function("document.querySelector('#tripMapStatus').textContent.includes('Traçados estimados')")
                self.assertEqual(center, self.page.evaluate("__travel.mapSession().map.getCenter()"))
                self.assertTrue(self.page.evaluate("__edgeMarker.isPopupOpen()"))
                self.page.get_by_role("button", name="Ver no roteiro").first.click()
                self.page.wait_for_selector("#trip-item-edge.selected")
                self.page.wait_for_function("document.querySelector('#tripMapStatus').textContent.includes('Traçados estimados')")
                self.page.wait_for_function("!__travel.mapSession().map._animatingZoom && !__travel.mapSession().map._panAnim?._inProgress")
                self.page.unroute("**/brouter?**")

    def test_real_leaflet_manual_navigation_survives_pending_route(self):
        self.page.add_script_tag(path=str(ROOT / "tests/fixtures/leaflet/leaflet.js"))
        self.page.add_style_tag(path=str(ROOT / "tests/fixtures/leaflet/leaflet.css"))
        for index, action in enumerate(("zoom", "drag")):
            with self.subTest(action=action):
                pending=[]
                self.page.route("**/brouter?**", lambda route: pending.append(route))
                trip={**TRIP, "itinerary":[dict(id="stop",title="Stop",date="2026-10-15",
                    latitude="41.3874",longitude=str(2.1686+index),transport="car")]}
                self.page.evaluate("trip=>__travel.reset(trip)",trip)
                self.page.wait_for_function("__travel.mapSession()?.markers.has('stop')")
                # Disable drag inertia so the reference view is the completed gesture.
                self.page.evaluate("__travel.mapSession().map.options.inertia=false")
                container=self.page.locator("#tripMovementMap")
                container.scroll_into_view_if_needed()
                if action=="zoom":
                    self.page.locator(".leaflet-control-zoom-in").click()
                else:
                    box=container.bounding_box()
                    x,y=box["x"]+box["width"]/2,box["y"]+box["height"]/2
                    self.page.mouse.move(x,y)
                    self.page.mouse.down()
                    self.page.mouse.move(x+100,y+60,steps=12)
                    self.page.mouse.up()
                # Leaflet starts button zoom on the next animation frame.
                self.page.wait_for_function("__travel.mapSession().focused===true")
                self.page.wait_for_function("!__travel.mapSession().map._animatingZoom && !__travel.mapSession().map._panAnim?._inProgress")
                self.assertTrue(self.page.evaluate("__travel.mapSession().focused"))
                view=self.page.evaluate("({center:__travel.mapSession().map.getCenter(),zoom:__travel.mapSession().map.getZoom()})")
                self.assertTrue(pending)
                for route in pending:
                    route.fulfill(body=json.dumps({"features":[{"properties":{"total-time":7200},
                        "geometry":{"type":"LineString","coordinates":[[-3.7038,40.4168],[0,50],[2.1686+index,41.3874]]}}]}),
                        content_type="application/json")
                self.page.wait_for_function("document.querySelector('#tripMapStatus').textContent.includes('Traçados estimados')")
                self.page.wait_for_function("!__travel.mapSession().map._animatingZoom && !__travel.mapSession().map._panAnim?._inProgress")
                self.assertEqual(view,self.page.evaluate("({center:__travel.mapSession().map.getCenter(),zoom:__travel.mapSession().map.getZoom()})"))
                self.page.unroute("**/brouter?**")

    def test_itinerary_more_options_keyboard_outside_and_mobile(self):
        trip={**TRIP,"itinerary":[dict(id="walk",title="Walk",location="Madrid",date="2026-10-15")]}
        self.page.evaluate("trip=>__travel.reset(trip)", trip)
        for width in (1280, 375, 320):
            self.page.set_viewport_size({"width":width,"height":850})
            summary=self.page.locator(".trip-more-options summary")
            self.assertFalse(self.page.get_by_role("button",name="Editar",exact=True).is_visible())
            self.assertFalse(self.page.get_by_role("button",name="Marcar feito",exact=True).is_visible())
            self.assertEqual(summary.inner_text(),"⋯")
            summary.focus()
            self.page.keyboard.press("Enter")
            self.assertTrue(self.page.get_by_role("button",name="Duplicar",exact=True).is_visible())
            self.page.keyboard.press("Escape")
            self.assertFalse(self.page.get_by_role("button",name="Duplicar",exact=True).is_visible())
            self.assertTrue(summary.evaluate("el=>el===document.activeElement"))
            summary.click()
            self.page.locator(".trip-day-group h3").first.click()
            self.assertEqual(self.page.locator(".trip-more-options[open]").count(),0)
            summary.click()
            bounds=self.page.locator(".trip-more-panel").bounding_box()
            self.assertGreaterEqual(bounds["x"],0)
            self.assertLessEqual(bounds["x"]+bounds["width"],width)
            self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth<=innerWidth"))
            self.page.keyboard.press("Escape")

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
        self.page.locator(".trip-more-options summary").click()
        self.page.get_by_role("button", name="Editar", exact=True).click()
        self.page.locator("#f-title").fill("Prado museum")
        self.page.locator("#itemForm button[type=submit]").click()
        state = self.page.evaluate("__travel.state()")
        self.assertEqual(len(state["trips"][0]["itinerary"]), 1)
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(state["events"][0]["title"], "Spain · Prado museum")
        self.page.locator(".trip-more-options summary").click()
        self.page.get_by_role("button", name="Duplicar", exact=True).click()
        self.page.locator("#f-date").select_option("2026-10-16")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertEqual(self.page.evaluate("__travel.state().events.length"), 2)
        self.page.locator(".trip-more-options summary").click()
        self.page.get_by_role("button", name="Mover dia", exact=True).click()
        self.page.locator("#f-date").select_option("2026-10-15")
        self.page.locator("#itemForm button[type=submit]").click()
        self.assertEqual(self.page.evaluate("__travel.state().events[1].date"), "2026-10-15")
        self.assertEqual(self.page.locator(".trip-itinerary").count(), 2)
        self.assertGreater(self.page.locator(".trip-item-warning").count(), 0)
        self.page.locator(".trip-itinerary").last.locator(".trip-more-options summary").click()
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
        self.page.locator(".trip-more-options summary").click()
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

    def test_reservation_uploads_pdf_and_preserves_voucher_on_failed_replacement(self):
        self.page.evaluate("""()=>{__travel.state().documents=[];window.__uploads=[];window.__uploadFailure=false;
          __travel.voucherStorage(bucket=>({
            upload:async(path,file,options)=>{__uploads.push({bucket,path,name:file.name,options});
              return {error:__uploadFailure?{message:'Upload failed'}:null}},
            createSignedUrl:async path=>({data:{signedUrl:'https://files.test/'+path}})
          }));
        }""")
        self.page.locator('[data-action="travel-add-reservation:test-trip"]').click()
        self.page.locator("#f-title").fill("Flight voucher")
        self.page.locator("#f-startDate").fill("2026-10-15")
        self.page.locator("#f-reservationPdf").set_input_files(ROOT / "tests/fixtures/voucher.pdf")
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.wait_for_selector("#modalBackdrop",state="detached")
        state=self.page.evaluate("__travel.state()")
        reservation=state["trips"][0]["reservations"][0]
        document=state["documents"][0]
        self.assertEqual(reservation["documentId"],document["id"])
        self.assertEqual(document["tripId"],TRIP["id"])
        self.assertEqual(document["fileName"],"voucher.pdf")
        self.assertEqual(self.page.evaluate("__uploads[0].bucket"),"kiwipath-documents")
        self.page.get_by_role("button",name="Abrir voucher",exact=True).click()
        self.assertIn(document["filePath"],self.page.locator(".pdf-preview-frame").get_attribute("src"))
        self.page.locator("#pdfCloseBtn").click()
        self.page.locator('[data-action^="travel-edit-reservation:"]').click()
        self.assertEqual(self.page.locator("#f-documentId").input_value(),document["id"])
        self.page.evaluate("window.__uploadFailure=true")
        self.page.locator("#f-reservationPdf").set_input_files(ROOT / "tests/fixtures/voucher.pdf")
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('Não foi possível enviar')")
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].reservations[0].documentId"),document["id"])
        self.assertEqual(self.page.evaluate("__travel.state().documents.length"),1)
        self.page.wait_for_function("!document.querySelector('#itemForm button[type=submit]').disabled")
        self.page.evaluate("window.__uploadFailure=false")
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.wait_for_selector("#modalBackdrop",state="detached")
        state=self.page.evaluate("__travel.state()")
        self.assertEqual(len(state["documents"]),2)
        self.assertNotEqual(state["trips"][0]["reservations"][0]["documentId"],document["id"])
        self.assertEqual(len(state["trips"][0]["reservations"]),1)
        self.page.locator('[data-action^="travel-edit-reservation:"]').click()
        self.page.locator("#f-documentId").select_option(document["id"])
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.wait_for_selector("#modalBackdrop",state="detached")
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].reservations[0].documentId"),document["id"])

    def test_reservation_pdf_rejects_invalid_file_and_requires_sign_in(self):
        self.page.evaluate("__travel.state().documents=[]")
        self.page.locator('[data-action="travel-add-reservation:test-trip"]').click()
        self.page.locator("#f-title").fill("Voucher")
        self.page.locator("#f-reservationPdf").set_input_files(
            {"name":"note.txt","mimeType":"text/plain","buffer":b"Not a PDF"})
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('Envie um arquivo PDF')")
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].reservations.length"),0)
        self.page.wait_for_function("!document.querySelector('#itemForm button[type=submit]').disabled")
        self.page.locator("#f-reservationPdf").set_input_files(ROOT / "tests/fixtures/voucher.pdf")
        self.page.locator("#itemForm button[type=submit]").click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('Entre na conta')")
        self.assertEqual(self.page.evaluate("__travel.state().documents.length"),0)

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
        self.page.locator(".trip-more-options summary").click()
        self.page.get_by_role("button", name="Remover", exact=True).click()
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary.length"), 1)
        self.page.get_by_role("button", name="Manter item", exact=True).click()
        self.assertEqual(self.page.locator(".trip-itinerary").count(), 1)
        self.page.locator(".trip-more-options summary").click()
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
        self.page.locator("#trip-item-0 summary").click()
        self.page.locator('[data-action="travel-status:test-trip:0:done"]').click()
        self.assertIn("Activity 1",self.page.locator(".trip-now h2").inner_text())
        self.page.locator("#trip-item-1 summary").click()
        self.page.locator('[data-action="travel-status:test-trip:1:skipped"]').click()
        self.assertIn("Activity 2",self.page.locator(".trip-now h2").inner_text())
        self.page.locator("#trip-item-0 summary").click()
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
        self.page.locator(".trip-itinerary summary").first.click()
        self.page.locator('[data-action^="travel-edit-itinerary:"]').first.click()
        self.assertEqual(self.page.locator("#modalTitle").inner_text(),"Editar reserva")

    def test_reorder_previews_route_changes_and_drag_order_persists(self):
        trip={**TRIP,"itinerary":[
            dict(id='a',title='Barcelona',kind='activity',date='2026-10-15',time='08:00',location='Barcelona',latitude='41.38',longitude='2.16'),
            dict(id='b',title='Paris',kind='travel',date='2026-10-15',time='10:00',location='Paris',latitude='48.85',longitude='2.35',transport='train',originSource='previous',origin='Barcelona',originLatitude='41.38',originLongitude='2.16'),
            dict(id='c',title='Lyon',kind='activity',date='2026-10-15',time='12:00',location='Lyon',latitude='45.76',longitude='4.83')]}
        self.page.evaluate("trip=>__travel.reset(trip)",trip)
        self.page.locator("#trip-item-c summary").click()
        self.page.get_by_role('button',name='Mover Lyon para cima',exact=True).click()
        self.assertIn('Lyon → Paris',self.page.locator('.trip-order-preview').inner_text())
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary[1].origin"),'Barcelona')
        self.page.locator('#cancelModal').click()
        self.page.locator("#trip-item-c summary").click()
        self.page.get_by_role('button',name='Mover Lyon para cima',exact=True).click()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate("__travel.sorted(__travel.state().trips[0]).map(x=>x.id)"),['a','c','b'])
        self.assertEqual(self.page.evaluate("__travel.state().trips[0].itinerary[1].origin"),'Lyon')
        self.page.locator("#trip-item-b summary").click()
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
        self.page.locator(".trip-more-options summary").click()
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
        self.page.locator("#trip-item-b summary").click()
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
        self.page.locator(".trip-more-options summary").click()
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

    def test_country_visit_details_sort_newest_first_and_undated_last(self):
        trips=[{**TRIP,'id':'older','name':'Older trip','status':'done','countryCode':'ie',
                'startDate':'2024-05-01','endDate':'2024-05-03'},
               {**TRIP,'id':'undated','name':'Without date','status':'done','countryCode':'ie',
                'startDate':'','endDate':''}]
        visits=[dict(id=key,name=key,countryCode='ie',date=date) for key,date in
                [('august','2025-08-17'),('june','2025-06-07'),('july','2025-07-26')]]
        self.page.evaluate('args=>__travel.memories(...args)',[trips,visits])
        for passport in (False, True):
            if passport:self.page.get_by_role('button',name='Passaporte',exact=True).click()
            self.page.locator('[data-action="memory-country:ie"]').first.click()
            self.assertEqual(self.page.locator('[data-memory-trip]').evaluate_all(
                'buttons=>buttons.map(b=>b.dataset.memoryTrip)'),
                ['quick-august','quick-july','quick-june','older','undated'])
            self.assertIn('01 de mai. de 2024',self.page.locator('#itemForm').inner_text())
            self.page.locator('#cancelModal').click()

    def test_memory_summary_combines_old_visits_and_trips_and_finance_style_tabs(self):
        trip={**TRIP,'status':'done','countryCode':'es','startDate':'2025-06-01','endDate':'2025-06-03'}
        visits=[dict(id='old',name='Barcelona',countryCode='es',date='2024-01-01'),
                dict(id='recent',name='Paris',countryCode='fr',date='2025-05-01')]
        self.page.evaluate('args=>__travel.memories(...args)',[[trip],visits])
        self.assertEqual(self.page.locator('.memory-stats .trip-history-stat').count(),3)
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'3')
        self.assertNotIn('Orçamentos',self.page.locator('.memory-stats').inner_text())
        self.assertNotIn('Visitas registradas',self.page.locator('.memory-stats').inner_text())
        self.page.locator('#memoryYear').select_option('2024')
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'1')
        self.page.locator('#memoryYear').select_option('2025')
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'2')
        buttons=self.page.locator('.memory-view-switch.finance-tabs button')
        self.assertEqual(buttons.count(),2)
        self.assertEqual(buttons.locator('svg[aria-hidden="true"]').count(),2)
        self.page.get_by_role('button',name='Passaporte',exact=True).click()
        self.assertEqual(self.page.get_by_role('button',name='Passaporte',exact=True).get_attribute('aria-pressed'),'true')
        self.assertTrue(self.page.get_by_role('button',name='Passaporte',exact=True).evaluate("el=>el.classList.contains('selected')"))
        self.page.set_viewport_size({'width':375,'height':850})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertGreaterEqual(buttons.first.bounding_box()['height'],52)
        self.page.get_by_role('button',name='Mapa e cidades',exact=True).click()
        self.page.wait_for_selector('.memory-globe-svg')
        self.assertEqual(self.page.evaluate('__travel.state().trips.length'),1)
        self.assertEqual(self.page.evaluate('__travel.state().memoryVisits.length'),2)

    def test_memories_year_filter_passport_and_global_world_percentage(self):
        trips=[{**TRIP,'id':'winter','name':'Winter','status':'done','countryCode':'es',
                'destination':'Madrid, España','startDate':'2024-12-30','endDate':'2025-01-02'},
               {**TRIP,'id':'paris','name':'Paris trip','status':'done','countryCode':'fr',
                'destination':'Paris, France','startDate':'2025-06-01','endDate':'2025-06-02',
                'latitude':'48.8566','longitude':'2.3522','visitedCountries':['hk']},
               {**TRIP,'id':'future','name':'Future','countryCode':'us','endDate':'2099-01-01'}]
        self.page.evaluate('trips=>__travel.memories(trips)',trips)
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'2')
        self.assertEqual(self.page.locator('#memoryCityCount').inner_text(),'2')
        self.assertEqual(self.page.locator('#memoryCountryCount').inner_text(),'3')
        self.assertEqual(self.page.evaluate('__travel.worldCountries().length'),195)
        self.assertEqual(self.page.locator('progress').get_attribute('value'),'2')
        percentage=self.page.locator('#memoryWorldPercent').inner_text()
        self.page.locator('#memoryYear').select_option('2024')
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'1')
        self.assertEqual(self.page.locator('#memoryCityCount').inner_text(),'1')
        self.assertEqual(self.page.locator('#memoryWorldPercent').inner_text(),percentage)
        self.page.get_by_role('button',name='Passaporte',exact=True).click()
        self.assertEqual(self.page.locator('.memory-stamp.is-visited').count(),1)
        self.page.locator('#memoryOnlyVisited').uncheck()
        self.page.locator('#memoryCountrySearch').fill('Japão')
        self.assertEqual(self.page.locator('.memory-stamp:visible').count(),1)
        self.assertIn('Ainda por conhecer',self.page.locator('.memory-stamp:visible').inner_text())
        self.page.locator('#memoryYear').select_option('2025')
        self.page.locator('[data-action="memory-country:fr"]').first.click()
        self.assertIn('Paris trip',self.page.locator('#itemForm').inner_text())
        self.page.locator('[data-memory-trip="paris"]').click()
        self.assertIn('Paris trip',self.page.locator('#pageContent').inner_text())
        self.assertEqual(self.page.locator('#memoryYear').count(),0)

    def test_memories_cities_deduplicate_and_do_not_count_attractions(self):
        trip={**TRIP,'status':'done','countryCode':'es','destination':'Madrid, España',
              'itinerary':[dict(id='museum',title='Museum',location='Museo del Prado, España',countryCode='es'),
                           dict(id='skip',city='Berlin',countryCode='de',status='skipped')],
              'visitedCities':[dict(id='one',name='MADRID',countryCode='es'),
                               dict(id='two',name='Barcelona',countryCode='es',latitude='',longitude='')]}
        visit=dict(id='quick',name='Madrid',location='Madrid, España',countryCode='es',
                   latitude='40.4168',longitude='-3.7038',date='2025-01-01')
        self.page.evaluate('args=>__travel.memories(...args)',[ [trip], [visit] ])
        cities=self.page.evaluate('__travel.memoryCities(__travel.memoryEntries())')
        self.assertEqual(len(cities),2)
        madrid=next(c for c in cities if c['name'].lower()=='madrid')
        self.assertEqual(len(madrid['trips']),2)
        self.assertEqual(madrid['firstVisit'],'2025-01-01')
        self.assertEqual(madrid['latitude'],40.4168)
        self.page.locator('#memoryCitySearch').fill('BARCELONA')
        self.assertEqual(self.page.locator('.memory-city:visible').count(),1)
        self.assertIn('Sem pin',self.page.locator('.memory-city:visible').inner_text())
        self.page.locator('#memoryCitySearch').fill('no match')
        self.assertTrue(self.page.locator('#memoryCityEmpty').is_visible())

    def test_quick_memory_visit_create_edit_delete_and_persist_without_trip(self):
        self.page.evaluate('__travel.memories([])')
        self.page.locator('[data-action="memory-quick-new"]').first.click()
        self.page.locator('#f-itineraryLocationSearch').fill('Barcelona')
        self.page.locator('[data-itinerary-location="0"]').click()
        self.page.locator('#f-visitDate').fill('2025-05-01')
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate('__travel.state().trips.length'),0)
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'1')
        self.assertEqual(self.page.locator('#memoryCityCount').inner_text(),'1')
        self.assertEqual(self.page.locator('#memoryCountryCount').inner_text(),'1')
        self.assertEqual(self.page.evaluate('__travel.state().events.length'),0)
        self.assertEqual(self.page.evaluate('__travel.state().reservations?.length||0'),0)
        self.page.get_by_role('button',name='Editar visita',exact=True).click()
        self.page.locator('#f-visitDate').fill('2024-06-02')
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.evaluate('__travel.state().memoryVisits[0].date'),'2024-06-02')
        self.page.reload()
        self.assertEqual(self.page.evaluate('__travel.state().memoryVisits[0].date'),'2024-06-02')
        self.page.evaluate('()=>__travel.memories([],__travel.state().memoryVisits)')
        self.page.locator('[data-action^="memory-quick-remove:"]').click()
        self.page.get_by_role('button',name='Manter visita',exact=True).click()
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'1')
        self.page.locator('[data-action^="memory-quick-remove:"]').click()
        self.page.get_by_role('button',name='Remover visita',exact=True).click()
        self.assertEqual(self.page.locator('#memoryTripCount').inner_text(),'0')
        self.assertEqual(self.page.locator('progress').get_attribute('value'),'0')

    def test_memory_globe_rotation_zoom_backside_pins_and_keyboard(self):
        visits=[dict(id='front',name='Paris',countryCode='fr',latitude='48.85',longitude='2.35',date='2025-01-01'),
                dict(id='back',name='Sydney',countryCode='au',latitude='-33.86',longitude='151.2',date='2025-01-01')]
        self.page.evaluate('visits=>__travel.memories([],visits)',visits)
        self.page.wait_for_selector('.memory-globe-svg')
        self.assertFalse(self.page.locator('[data-globe-city="sydney|au"]').is_visible())
        globe=self.page.locator('.memory-globe-svg')
        globe.scroll_into_view_if_needed()
        box=globe.bounding_box()
        x,y=box['x']+box['width']/2,box['y']+box['height']/2
        self.page.mouse.move(x,y)
        self.page.mouse.down()
        self.page.mouse.move(x+100,y+15,steps=12)
        self.page.mouse.up()
        self.assertNotEqual(self.page.evaluate('__travel.memoryMap().globe.getView().longitude'),0)
        self.assertEqual(self.page.locator('.memory-globe-popup').count(),0)
        globe.focus()
        before=self.page.evaluate('__travel.memoryMap().globe.getView()')
        self.page.keyboard.press('ArrowRight')
        self.assertNotEqual(before['longitude'],self.page.evaluate('__travel.memoryMap().globe.getView().longitude'))
        self.page.get_by_role('button',name='Aproximar globo',exact=True).click()
        self.assertGreater(self.page.evaluate('__travel.memoryMap().globe.getView().zoom'),1)
        self.page.locator('[data-action="memory-pin:sydney%7Cau"]').click()
        self.assertTrue(self.page.locator('[data-globe-city="sydney|au"]').is_visible())
        self.assertIn('Sydney',self.page.locator('.memory-globe-popup').inner_text())
        self.page.locator('.memory-globe-popup').get_by_role('button',name='Ver memórias').click()
        self.assertIn('Visita a Sydney',self.page.locator('#itemForm').inner_text())
        self.page.locator('#cancelModal').click()
        view=self.page.evaluate('__travel.memoryMap().globe.getView()')
        self.page.locator('#memoryCitySearch').fill('Paris')
        self.assertEqual(view,self.page.evaluate('__travel.memoryMap().globe.getView()'))
        globe.focus()
        self.page.keyboard.press('Home')
        self.assertEqual(self.page.evaluate('__travel.memoryMap().globe.getView().zoom'),1)

    def test_memory_cards_flags_hover_keyboard_and_nested_actions(self):
        visits=[dict(id='paris',name='Paris',countryCode='fr',latitude='48.85',longitude='2.35',date='2025-01-01')]
        self.page.evaluate('visits=>__travel.memories([],visits)',visits)
        card=self.page.locator('.memory-city')
        self.assertEqual(card.locator('.memory-country-label img').get_attribute('src'),
                         'https://flagcdn.com/w80/fr.png')
        self.assertIn('França',card.locator('.memory-country-label').inner_text())
        card.hover()
        self.page.wait_for_function("getComputedStyle(document.querySelector('.memory-city')).borderColor==='rgb(160, 188, 145)'")
        self.assertEqual(card.evaluate("el=>getComputedStyle(el).cursor"),'pointer')
        card.get_by_role('button',name='Ver memórias de Paris',exact=True).focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.locator('#modalTitle').inner_text(),'Paris')
        self.page.locator('#cancelModal').click()
        card.locator('.memory-country-label').click()
        self.assertEqual(self.page.locator('#modalTitle').inner_text(),'Paris')
        self.page.locator('#cancelModal').click()
        card.get_by_role('button',name='Ver pin',exact=True).click()
        self.assertEqual(self.page.locator('#modalBackdrop').count(),0)
        self.assertTrue(self.page.locator('.memory-globe-popup').is_visible())
        quick=self.page.locator('.memory-quick-list article')
        self.assertEqual(quick.locator('.memory-country-label img').get_attribute('src'),
                         'https://flagcdn.com/w80/fr.png')
        quick.get_by_role('button',name='Editar visita a Paris',exact=True).click()
        self.assertEqual(self.page.locator('#modalTitle').inner_text(),'Editar visita')
        self.page.locator('#cancelModal').click()
        quick.get_by_role('button',name='Remover',exact=True).click()
        self.assertTrue(self.page.get_by_role('button',name='Manter visita',exact=True).is_visible())
        self.page.get_by_role('button',name='Manter visita',exact=True).click()
        self.page.emulate_media(reduced_motion='reduce')
        card.hover()
        self.assertEqual(card.evaluate("el=>getComputedStyle(el).transitionDuration"),'0s')

    def test_memory_globe_deep_zoom_survives_background_cloud_poll_and_redraw(self):
        visits=[dict(id='city',name='Paris',countryCode='fr',latitude='48.85',longitude='2.35',date='2025-01-01')]
        self.page.evaluate('visits=>__travel.memories([],visits)',visits)
        globe=self.page.locator('.memory-globe-svg')
        globe.scroll_into_view_if_needed();globe.focus()
        for _ in range(20):self.page.keyboard.press('+')
        self.assertEqual(self.page.evaluate('__travel.memoryMap().globe.getView().zoom'),40)
        self.assertTrue(self.page.get_by_role('button',name='Aproximar globo',exact=True).is_disabled())
        self.page.keyboard.press('ArrowRight');self.page.keyboard.press('ArrowDown')
        view=self.page.evaluate('__travel.memoryMap().globe.getView()')
        self.page.evaluate('__travel.redraw()')
        self.page.wait_for_selector('.memory-globe-svg')
        self.assertEqual(view,self.page.evaluate('__travel.memoryMap().globe.getView()'))
        self.page.clock.install()
        self.page.evaluate("""()=>{
          window.__memoryPolls=0;
          __travel.api(()=>({select(){return this},eq(){return this},order(){return this},
            limit:async()=>{__memoryPolls++;return {data:[{id:'test-record',
              content:__travel.state(),updated_at:'2026-11-01T10:00:00Z'}]}}}));
        }""")
        self.page.clock.run_for(16000)
        self.page.wait_for_function('window.__memoryPolls>0 && __travel.memoryMap()!==null')
        self.assertEqual(view,self.page.evaluate('__travel.memoryMap().globe.getView()'))
        self.page.get_by_role('button',name='Passaporte',exact=True).click()
        self.page.get_by_role('button',name='Mapa e cidades',exact=True).click()
        self.page.wait_for_selector('.memory-globe-svg')
        self.assertEqual(view,self.page.evaluate('__travel.memoryMap().globe.getView()'))
        self.page.get_by_role('button',name='Ver mundo',exact=True).click()
        self.assertEqual(self.page.evaluate('__travel.memoryMap().globe.getView()'),
                         {'longitude':0,'latitude':20,'zoom':1})

    def test_memory_globe_touch_pinch_and_city_list_scroll_on_mobile(self):
        codes=['es','fr','gb','ie','pt','de','br','us','ar','cl','it','at','hu','cz','sk','ch','no','se','fi','au']
        visits=[dict(id=str(i),name='City '+str(i).zfill(2),countryCode=codes[i%len(codes)],latitude=str(30+i/10),
                     longitude=str(i),date='2025-01-01') for i in range(45)]
        self.page.set_viewport_size({'width':375,'height':850})
        self.page.evaluate('visits=>__travel.memories([],visits)',visits)
        grid=self.page.get_by_role('region',name='Lista de cidades visitadas, com rolagem',exact=True)
        self.assertLessEqual(grid.evaluate('el=>el.clientHeight'),360)
        self.assertGreater(grid.evaluate('el=>el.scrollHeight'),grid.evaluate('el=>el.clientHeight')*5)
        grid.evaluate('el=>el.scrollTop=el.scrollHeight')
        self.assertGreater(grid.evaluate('el=>el.scrollTop'),0)
        visits_list=self.page.get_by_role('region',name='Visitas registradas, com rolagem',exact=True)
        self.assertLessEqual(visits_list.evaluate('el=>el.clientHeight'),360)
        self.assertGreater(visits_list.evaluate('el=>el.scrollHeight'),visits_list.evaluate('el=>el.clientHeight')*3)
        self.assertTrue(self.page.get_by_role('heading',name='Visitas registradas',exact=True).is_visible())
        countries=self.page.get_by_role('region',name='Países visitados, com rolagem',exact=True)
        self.assertLessEqual(countries.evaluate('el=>el.clientHeight'),360)
        self.assertGreater(countries.evaluate('el=>el.scrollHeight'),countries.evaluate('el=>el.clientHeight'))
        countries.evaluate('el=>el.scrollTop=el.scrollHeight')
        self.assertGreater(countries.evaluate('el=>el.scrollTop'),0)
        self.page.locator('#memoryCitySearch').fill('City 44')
        self.assertEqual(self.page.locator('.memory-city:visible').count(),1)
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        globe=self.page.locator('.memory-globe-svg');globe.scroll_into_view_if_needed()
        box=globe.bounding_box();x,y=box['x']+box['width']/2,box['y']+box['height']/2
        cdp=self.context.new_cdp_session(self.page)
        cdp.send('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':2})
        def touches(kind,distance):
            cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[
                {'x':x-distance,'y':y,'id':1},{'x':x+distance,'y':y,'id':2}] if kind!='touchEnd' else []})
        touches('touchStart',25);touches('touchMove',65);touches('touchEnd',0)
        self.assertGreater(self.page.evaluate('__travel.memoryMap().globe.getView().zoom'),1)
        self.assertEqual(self.page.locator('.memory-globe-popup').count(),0)
        self.page.get_by_role('button',name='Passaporte',exact=True).click()
        self.assertIsNone(self.page.evaluate('__travel.memoryMap()'))
        cdp.detach()

    def test_memories_add_city_to_trip_and_globe_pins(self):
        self.page.evaluate('trip=>__travel.memories([trip])',{**TRIP,'status':'done','countryCode':'es'})
        self.page.get_by_role('button',name='Cidades visitadas',exact=True).click()
        self.page.locator('#f-itineraryLocationSearch').fill('Paris')
        self.page.locator('[data-itinerary-location="0"]').click()
        self.page.locator('#itemForm button[type=submit]').click()
        self.assertEqual(self.page.locator('#memoryCityCount').inner_text(),'2')
        self.assertEqual(self.page.locator('#memoryCountryCount').inner_text(),'2')
        self.page.wait_for_function('__travel.memoryMap()?.markers.size===2')
        self.page.locator('#tripMemoryMap').scroll_into_view_if_needed()
        self.page.locator('[data-globe-city="paris|fr"]').click()
        self.assertTrue(self.page.locator('.memory-globe-popup').is_visible())
        self.assertIn('Paris',self.page.locator('.memory-globe-popup').inner_text())
        self.page.get_by_role('button',name='Ver mundo',exact=True).click()
        self.assertEqual(self.page.evaluate('__travel.memoryMap().globe.getView().zoom'),1)
        self.page.set_viewport_size({'width':375,'height':850})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.get_by_role('button',name='Passaporte',exact=True).click()
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertIsNone(self.page.evaluate('__travel.memoryMap()'))

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
        self.page.locator(".trip-itinerary summary").click()
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
