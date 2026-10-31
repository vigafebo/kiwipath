"""Travel regressions. Run: python3 -m unittest discover -s tests -v

Requires Python Playwright and Chromium. All remote services are stubbed;
these tests never authenticate or change shared Supabase data.
"""
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

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
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.errors = []
        self.route_requests = []
        self.routing_failure = False
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        source = (ROOT / "index.html").read_text()
        hooks = '''window.__travel = {
          reset(trip) { data={...initial(),trips:[trip],events:[]}; page="trips";
            activeTripId=trip.id; document.querySelector('#authScreen').style.display='none';
            document.querySelector('#kiwiApp').style.visibility='visible'; render(); },
          state:()=>data, open:()=>addTripItinerary(data.trips[0].id),
          points:tripMovementPoints, flight:tripFlightPath
        };'''
        source = source.replace("supabaseClient.auth.getSession().then", hooks + "\nsupabaseClient.auth.getSession().then")
        sdk = "window.supabase={createClient:()=>({auth:{getSession:()=>Promise.resolve({data:{session:null}}),onAuthStateChange:()=>{}}})};"
        leaflet = '''window.__map={markers:[],lines:[]};
        window.L={map:()=>({setView(){},fitBounds(){},invalidateSize(){},remove(){}}),
          tileLayer:()=>({addTo(){}}),latLngBounds:x=>x,
          circleMarker:(ll)=>{__map.markers.push(ll);return {addTo(){return this},bindPopup(){}}},
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
            elif "brouter.de/brouter?" in url:
                params = parse_qs(urlparse(url).query)
                self.route_requests.append(params)
                if self.routing_failure:
                    request.fulfill(status=503, body="Unavailable")
                else:
                    ends = [[float(x) for x in pair.split(",")] for pair in params["lonlats"][0].split("|")]
                    coords = [ends[0], [(ends[0][0]+ends[1][0])/2, (ends[0][1]+ends[1][1])/2+0.1], ends[1]]
                    request.fulfill(body=json.dumps({"features":[{"geometry":{"type":"LineString","coordinates":coords}}]}), content_type="application/json")
            elif "nominatim.openstreetmap.org" in url:
                request.fulfill(body=json.dumps([dict(name="Barcelona", lat="41.3874", lon="2.1686", address={"country":"España"})]), content_type="application/json")
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
        self.page.locator("#f-addTransport").select_option("yes")
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
