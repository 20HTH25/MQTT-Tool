# macOS App Build

## 1) Build-Abhängigkeit installieren

```bash
pip install -r requirements-dev.txt
```

## 2) Eigenes Icon erstellen (optional)

Wenn du ein Bild (idealerweise 1024x1024) hast, erstelle daraus eine `.icns`:

```bash
./create_icns.sh "pfad/zu/deinem-icon.png" assets/app.icns
```

## 3) App bauen

```bash
./build_macos.sh
```

Danach liegt die App hier:

- `dist/MQTT-Tool.app`

## Hinweis

- Ohne `assets/app.icns` wird die App trotzdem gebaut, dann mit Standard-Icon.
- Du kannst auch ein anderes `.icns` direkt beim Build angeben:

```bash
./build_macos.sh "pfad/zu/deinem-icon.icns"
```

## 4) Komplettes Release mit einem Befehl

`release.sh` baut die App und legt alles in `release/` ab.

### Standard (nutzt vorhandenes `assets/app.icns`, falls vorhanden)

```bash
./release.sh
```

### Mit PNG als Icon-Quelle

```bash
./release.sh "pfad/zu/deinem-icon.png"
```

### Mit PNG und eigenem `.icns`-Zielpfad

```bash
./release.sh "pfad/zu/deinem-icon.png" "assets/app.icns"
```

Ergebnis:

- `release/MQTT-Tool.app`
- optional: Icon-Datei im `release/`-Ordner
- `release/README.txt`
