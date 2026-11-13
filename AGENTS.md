# KiwiPath development rules

## Languages (required for every change)

Every user-facing feature must work in Portuguese (`pt`) and English (`en`).
Include both languages in the same change, including navigation, forms, buttons,
empty states, validation/errors, notifications, accessibility labels, tooltips,
PDF/CSV exports and external helper modules. Use the existing `copy.pt/copy.en`
keys, explicit `pt ? Portuguese : English` pairs, or `KiwiI18n.text()` with an
entry in `translations.js`. Do not ship a new label with only one language.

Only static application copy may be passed to `KiwiI18n.text()`. User-entered
names, notes, addresses, titles and file names must remain exactly as entered.
Default sample records have `defaultCopy` metadata; translate a field only while
it still equals that default. Never translate stored identifiers or option values.

When changing UI, verify it in both languages, including mobile layouts, and
extend the language regression checks for the affected flow. Check matching keys
in `copy.pt` and `copy.en`. Reuse existing labels before adding catalog entries.

## Official releases

The official version is in `VERSION`, the README and the visible app footer.
Keep these in sync when releasing an update. Increment the service-worker cache
when shipping changed app assets. Public main publication is authorised by the
user for requested corrections in this project.
