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
