# Proteus – karbantartás

Minden, ami a Proteus kiadásához, beállításához és frissítéséhez kell.

## Beállítások egy helyen: `branding.py`

| Beállítás | Mit csinál |
|---|---|
| `UPDATE_REPO` | ebből a GitHub repóból frissül a telepített Proteus (Releases) |
| `SKINS_REPO` | innen szinkronizálja a skin könyvtárat (lásd lent) |
| `GITHUB_URL`, `DISCORD_URL`, `DONATE_URL` | linkek a beállítások panelen és a hibaüzenetekben; üres = rejtve |

Módosítás után:

```bash
python scripts/apply_branding.py
```

Ez beírja az értékeket a League kliensben futó JS pluginokba és a
telepítőbe. A build magától is lefuttatja, a CI pedig szól, ha elmaradt.

## Kinézet

- **Ikonok:** `assets/icon.png` és `assets/icon.ico` (exe, telepítő),
  `assets/tray_ready.png` / `tray_starting.png` (tálca: kész / indul),
  `assets/golden_proteus.png` (gomb a League kliens oldalsávjában: csak a
  formája számít, a színét a kliens adja). Forrás SVG-k és nagy változatok:
  `assets/proteus/`.
- **A kliensben megjelenő panelek** (beállítások, chroma kerék, party
  mode…): `Pengu Loader/plugins/PROTEUS-*/index.js`, a stílusok CSS-ként
  ezekben a fájlokban vannak.
- **Szövegek, fordítások:** `Pengu Loader/plugins/PROTEUS-I18n/locales/`
  (a kulcs az angol szöveg, az érték a fordítás).

## Új verzió kiadása

A buildet a GitHub csinálja Windows gépen (`.github/workflows/release.yml`).

1. Írd át a verziószámot **mindkét** helyen ugyanarra, pl. `1.5.5`:
   - `config.py` → `APP_VERSION = "1.5.5"`
   - `installer.iss` → `#define MyAppVersion "1.5.5"` és `MyAppVersionInfo "1.5.5.0"`
2. Push (vagy szólj Claude-nak).
3. Kb. 3 perc múlva a **Releases** oldalon megjelenik:
   - `Proteus_Setup_1.5.5.exe` – új telepítéshez
   - `update_package_1.5.5.zip` – ezt tölti le a már telepített Proteus

A build az **Actions** fülön (Release) követhető, és kézzel is indítható
(Run workflow). Ha a verziószám nem változott, csak buildel, release nem lesz.

## Party mode szerver

A party mode egy Cloudflare Workeren (ingyenes csomag) keresztül köti
össze a játékosokat. A kódja a `relay-worker/` mappában van, és a
Cloudflare minden olyan pushnál magától újraépíti, ami ezt a mappát
érinti.

Beállítás (egyszer kell, már kész):

1. Cloudflare → **Workers & Pages** → **Create application** → a
   `lildmate/claude` repó bekötése. Ebből lett a `claude` nevű worker (a név
   egyezzen a `relay-worker/wrangler.toml` `name` sorával).
2. A worker → **Settings** → **Build** → **Root directory**: `relay-worker`,
   **Include paths**: `relay-worker/**`.
3. A szerver címe: `wss://claude.<alnév>.workers.dev`. Böngészőben a
   `https://` változat `{"status":"ok",…}` választ ad, ha fut.
4. GitHub → **Settings** → **Secrets and variables** → **Actions** →
   `RELAY_URL` titok = a szerver címe. A Release build ebből teszi bele a
   programba; nélküle party mode nélkül buildel.

## Skin könyvtár

A skin fájlok a `SKINS_REPO` repóból jönnek (jelenleg
`Alban1911/LeagueSkins`). Ezt a repót nem mi tartjuk karban: a League
patchek után ott frissülnek a skinek, és a Proteus minden induláskor
magától letölti a változásokat.

## Átvett javítások

A Proteus a Rose kódjából indult (MIT licenc). Ha ott javítanak valamit,
ami nekünk is kell (pl. egy LoL patch után), azt kézzel lehet átvenni:

```bash
git remote add upstream https://github.com/Alban1911/Rose
```

```bash
git fetch upstream
```

Utána a szükséges commitokat egyenként kell átemelni és a Proteus neveihez
igazítani (`PROTEUS-*` pluginok, Proteus szövegek). Ezt Claude meg tudja
csinálni, ha szólsz.

## Ami szándékosan Rose maradt

- **Az adatmappa** `%LOCALAPPDATA%\Rose`: a Pengu Loader előre lefordított
  `core.dll`-je (forrása nincs meg) fixen innen olvassa a `config.ini`-t,
  más néven a kliensben nem jelennének meg a menük. Ezért a Proteus és a
  Rose nem futhat egy gépen egyszerre.
- **A `LICENSE` fájl** eredeti copyright sora: az MIT licenc feltétele,
  hogy a másolatokban megmaradjon.

A régi `ROSE-*` pluginmappákat (régebbi Proteus vagy az eredeti Rose) a
Proteus induláskor és a telepítő is törli, különben minden panel kétszer
jelenne meg.

## Build saját gépen (nem kötelező)

Windows 10/11, Python 3.11+, Visual Studio Build Tools (.NET desktop +
.NET Framework 4.7.2, MSVC C++20), Inno Setup 6. Utána:

```powershell
python -m pip install -r requirements.txt
```

```powershell
python scripts/build_all.py
```

```powershell
python scripts/create_update_package.py
```

A kész fájlok az `installer/` mappában lesznek.
