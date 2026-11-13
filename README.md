# kiwipath
Our journey to New Zealand — immigration, study, finances and dreams.

## Version

Current official version: **v1.1.0**. Version numbering began with v1.0.0. The app displays the version in its footer.

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
the trip are warnings. Items and reservations have departure/arrival IANA time
zones and a separate arrival date, supporting overnight and international travel.
Nonexistent DST times and arrivals before departure are rejected. Linked calendar
events are converted to Pacific/Auckland, preserving the calendar's existing
convention and showing the original local time as context. Legacy items without a
zone keep the previous Auckland default. Mark items done or skipped (and resume
them); the next-item card excludes completed/skipped items using each item's zone.

“Compartilhar guia PDF” generates a styled PDF locally with the daily itinerary,
reservations, checklist, and original PDF vouchers appended as pages. The font and
PDF libraries are served from this repository, with no third-party PDF conversion.
Unsupported or unavailable vouchers are reported instead of silently omitted.
The Web Share API opens the native file share sheet when supported and user
activation is still available. Otherwise a PDF preview provides a fresh Share
button (where supported) and a download fallback. Canceling the share sheet does
not trigger an unwanted download. The exported PDF can be read offline; maps and
subsequent edits are not included. Tests use real PDF generation and parsing,
with mocked remote services and native sharing. Python tests also require pypdf.

Map stop numbers are anchored inside Leaflet div icons. Nearby stops cluster at
54 screen pixels and regroup on zoom/pan; cluster popups list individual stops
and can zoom to the area. Permanent tooltips are not used for numbering.
Every itinerary removal requires confirmation, including unlinked items.

Daily order can be changed with desktop drag handles or up/down buttons, including
on mobile. A preview shows the new sequence, timing conflicts and changed automatic
origins before committing; fixed times and custom origins are preserved. Changes
to the schedule while a preview is open require a fresh preview. The order is
persisted per day and used in the itinerary, map and exported PDF.

New reservations can create connected itinerary items: a transfer for a flight or
transport booking, and check-in/out for a stay. Editing the reservation updates
those items and their calendar events using stable IDs. Edit connected items via
the reservation; duplicating one makes an independent activity. Deliberately
removed generated parts are not recreated on the next reservation edit. Removing
a reservation preserves its activities and finance history as independent records.

Saved places are kept separately from scheduled activities. Adding a saved place
to the itinerary copies its details without deleting the library entry. Day tabs
also filter the map; the map's own selector can show another day or the whole trip.
Filtered maps retain a departure context point when needed for a selected day's
route, and preserve global stop numbering. PDF guides include status, local time
zones, manual order and saved places.

## Device time zones

The app detects the device's IANA time zone with Intl and refreshes on focus,
visibility, zone changes and local day changes. Account and preferences shows a
live local clock and, outside Pacific/Auckland, the NZ reference clock. No location
permission or shared account-wide time-zone setting is required.

Calendar/dashboard events are projected into the viewer's zone without rewriting
stored dates/times. Existing events with no zone keep their original Auckland
meaning; date-only values (document expiry, holidays, finance dates) are not shifted
as if they were timestamps. New manual events record their zone explicitly. New
trip defaults use the device zone; location-specific trip/arrival zones remain
editable. Trip-derived calendar records retain their explicit canonical NZ zone,
and are then projected for each viewer. ICS exports retain UTC instants/duration.

New alerts default to the device zone and send scheduled_at as a UTC ISO instant
plus the selected timezone. Existing repeating alerts retain their origin zone
unless edited explicitly. Event reminders use absolute 24-hour/3-hour offsets;
document reminders use 09:00 in the device zone. These are client payload changes.
No SQL migrations, Edge Function sources or Supabase administrative connector are
available in this repository/session; server recurrence/cron implementations have
not been modified or verified live. Automated tests mock Supabase and assert the
UTC payloads, local projections and preservation of existing schedules.

## Countries in travel history

Completed-trip history aggregates countries from the trip's starting destination,
itinerary stops, both transfer endpoints and reservations. Each country is counted
once per trip; a country row reports the number of trips that visited it. Skipped
stops and unscheduled saved places are excluded. Search selections persist country
name/code on both endpoints and retain them through saved-place scheduling,
reservation-generated transfers and automatic-origin updates.

Legacy location labels are matched against localized country names (for example,
“Paris, France” or “Roma, Itália”). A city name alone is not enough to infer its
country. “Países visitados” on each history card allows explicit additions for
countries visited in transit or older locations without country metadata. These
additions supplement the automatically identified countries; countries crossed by
a route are not guessed from a straight line or flight path.

## Flight research and airport connections

When adding a flight reservation, enter the flight number (for example LA803) and
the local departure date. “Pesquisar voo” offers public FlightRadar24 and web-search
links. This is external research, **not automatic flight-data import**: the user
checks the source and fills airline, airports and local departure/arrival times.
No paid API, provider account, scraping proxy or provider key is used. FlightRadar24
opens the flight-number page; its date must be checked there. The web query includes
both the number and date. The booking reference is separate and is not sent.

Reservations and itinerary segments have a visitMode: transit, destination
or both. New flight/transport reservations default to transit. Connections stay
in the travel map, itinerary and calendar, but contribute no countries or cities
to the passport/memory globe. Destination mode includes only the arrival location;
both includes both endpoints. Connected itinerary items inherit the reservation's
choice. The itinerary's three-dot menu can toggle a segment between a connection
and a destination visit. Legacy entries with no choice preserve their prior
behavior until edited; explicitly registered cities/countries remain visits.

City names resolved from location searches are stored separately from airport or
street labels. Only visit-marked city metadata contributes city pins; airport labels
are not guessed to be cities. The trip's main destination and manually registered
cities remain included.

## Bilingual UI

All new UI must include Portuguese and English; see AGENTS.md. Static legacy
copy is centralised in translations.js. User-entered text is never translated.
Generated default records use defaultCopy metadata and translate only unchanged
default fields. Version 1.1.0 covers UI, validation, flight research, globe
accessibility and travel PDF copy.
