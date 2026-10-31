# PDF guide dependencies

These assets are served locally so PDF generation does not send trip contents to
an external conversion service. JavaScript distributions are unmodified.

- **pdf-lib 1.17.1** — MIT, https://github.com/Hopding/pdf-lib.
  `pdf-lib-LICENSE.md` is copied from the published package.
- **@pdf-lib/fontkit 1.1.1** — MIT, https://github.com/Hopding/fontkit.
  The package metadata and upstream README declare MIT. `fontkit-README.md`
  preserves the upstream documentation, attribution and license link. The npm
  package and upstream repository do not include a separate license file.
- **DejaVu Sans** — copied from the environment's `fonts-dejavu-core` package.
  See `DejaVu-LICENSE.txt` for the Bitstream Vera/DejaVu font notices.

The npm tarballs were checked against their registry-published SHA-512 integrity
before extracting the bundles. The font is embedded as a subset in generated PDFs.
