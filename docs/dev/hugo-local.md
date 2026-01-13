# Repo-lokales Hugo (Wissen)

Diese Repo-Installation nutzt eine gepinnte Hugo-Extended-Version, die lokal in `wissen/tools/hugo/<os>-<arch>/` installiert wird (kein Binary im Git-Repo).

## Nutzung

```bash
./wissen/tools/hugo/hugo version
./wissen/tools/hugo/hugo -s wissen --minify
```

## Version ändern

1. `wissen/tools/hugo/VERSION` anpassen (ohne führendes `v`).
2. Beim nächsten Aufruf lädt `install.sh` die passende Hugo-Extended-Binary und prüft die SHA256-Checksumme.

## Hinweise

- Die Binary wird nach `wissen/tools/hugo/<os>-<arch>/` gelegt und **nicht** committed.
- Die Installation ist deterministisch über `VERSION` + Checksum-Verification.
