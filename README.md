# kiwipath
Our journey to New Zealand — immigration, study, finances and dreams.

## Local development

Run `python3 -m http.server 8000 --bind 127.0.0.1 --directory /workspace`
and load `/kiwipath/` from that server. The PWA expects this base path.

## Travel maps

Surface routes use the public BRouter GeoJSON endpoint (`https://brouter.de/brouter`):
`rail` for trains, `car-vario` for cars/taxis/buses, and `shortest` for walking.
Routes are estimates from OpenStreetMap data, not booked train/bus services or schedules.
The routing provider receives only the segment coordinates and routing profile.
Flights use a local great-circle calculation, not actual airways or flight plans.
Short dotted segments indicate that a route could not be calculated or no transport
was selected. Failed requests time out after 20 seconds and can retry on the next
render; successful routes are cached in memory (up to 100). Network access to
`brouter.de` is required; map tiles and other existing services remain required.

Run regression tests with `python3 -m unittest discover -s tests -v`.
Tests require Python Playwright and `/usr/bin/chromium`; external services are
stubbed, so they never authenticate or modify shared data.

## Travel planning

The travel dashboard groups activities and transfers by day. Items can be edited,
duplicated, or moved while keeping their linked calendar event. Transfers store
explicit origin/destination coordinates; new activities no longer imply a route
from the preceding item. Existing itinerary items retain their previous map behavior.
Numbered stops link the map to the itinerary. Distance and duration are estimates
from the route response; unavailable routes remain clearly marked.

Reservations track check-in/out, confirmation, currency, manually entered exchange
rate, total/paid balance, and a voucher chosen from the trip's uploaded PDFs.
Posting a paid amount requires a finance account in the reservation's currency.
Reservations and linked payments are counted once in the budget. Finance expenses
in other currencies require manual conversion rates; missing conversions are
reported and excluded rather than summed as if they were in the budget currency.
Checklist items support owners and deadlines. Schedule conflicts and dates outside
the trip are warnings; an item's end time must be on the same day as its start.
Existing calendar times retain the application's calendar convention; check time
zones for international travel. The next-item card follows the device's local clock.

“Baixar guia offline” downloads a standalone HTML snapshot of the itinerary,
reservations, checklist and available PDFs. It can be opened without a connection;
it does not update itself and does not include offline maps. If a PDF cannot be
fetched, the guide and the app explicitly report that it was omitted. No change to
the authenticated app's offline startup or synchronization behavior is implied.
