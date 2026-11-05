# Proteus – saját verzió

A **Proteus** a [Rose](https://github.com/Alban1911/Rose) saját példánya
(az upstream `db1f7e0` commitjából, 1.5.2-es verzió). Az eredeti MIT licences,
ezért szabadon módosítható és terjeszthető, csak a `LICENSE` fájlban lévő
eredeti copyright sornak maradnia kell.

## Mi lett átállítva

| Mi | Eredetiben | Itt |
|---|---|---|
| Frissítések forrása | `Alban1911/Rose` releases | `lildmate/claude` releases (`branding.py` → `UPDATE_REPO`) |
| Statisztika (analytics ping) | be, az ő szerverükre | **ki** (`branding.py` → `ANALYTICS_ENABLED`) |
| Linkek a beállítások panelen | az ő Discordjuk, Ko-Fi, GitHub | csak a te GitHubod (a többi üresen = rejtve) |
| Hibaüzenetek „segítség” linkje | az ő Discordjuk | a te Discordod, ha nincs, a GitHubod |
| Telepítő (`installer.iss`) URL | az ő repójuk | a te repód |
| Skin könyvtár | `Alban1911/LeagueSkins` | **ugyanaz** (lásd lent) |

Minden ilyen beállítás egy fájlban van: **`branding.py`**. Ha módosítod,
futtasd le:

```bash
python scripts/apply_branding.py
```

Ez beírja az értékeket a League kliensben futó JS pluginokba és a
telepítőbe. (A `scripts/build_all.py` buildeléskor magától is lefuttatja,
a CI pedig szól, ha elfelejtetted.)

## Kinézet testreszabása

- **Ikon:** `assets/icon.png` és `assets/icon.ico` (exe, telepítő), `assets/tray_ready.png` / `tray_starting.png` (tálca: kész / indul), `assets/golden_rose.png` (gomb a League kliens oldalsávjában, csak a formája számít, a színét a kliens adja). A forrás SVG-k és nagy változatok: `assets/proteus/`.
- **Képek, gombok:** `assets/` mappa.
- **A League kliensben megjelenő panelek** (beállítások, chroma kerék,
  party mode stb.): `Pengu Loader/plugins/ROSE-*/index.js`. A stílusok
  (színek, méretek) ezekben a fájlokban CSS-ként vannak, pl. a beállítások
  panelé a `ROSE-SettingsPanel/index.js` elején (`.settings-link` stb.).
- **Fordítások / szövegek:** `Pengu Loader/plugins/ROSE-I18n/`.
- **App neve: Proteus.** Minden látható helyen ez szerepel: tálca, ablakok,
  hibaüzenetek, a League kliensben megjelenő szövegek (mind a 21 nyelven),
  `Proteus.exe`, `Proteus_Setup_<verzió>.exe`, Program Files\Proteus, saját
  Windows-azonosító (AppId), így külön appként települ.
  Belül néhány dolog **szándékosan Rose maradt**:
  - az adatmappa `%LOCALAPPDATA%\Rose` – a Pengu Loader előre lefordított
    `core.dll`-je fixen ezt olvassa, átnevezve a kliensben nem jelenne meg;
  - a pluginmappák (`ROSE-*`) és a belső kódnevek (pl. `window.RoseI18n`);
  - a „csak egy példány futhat” azonosító, így a Proteus és az eredeti Rose
    nem fut egyszerre (ugyanazt az adatmappát használnák).
  Ha az eredeti Rose fel van telepítve, előbb azt távolítsd el.

## Új verzió kiadása (automatikus)

A telepített Proteus induláskor megnézi a `lildmate/claude` repó **legutolsó
release**-ét, és ha újabb, felajánlja a frissítést.

A buildelést a GitHub csinálja (`.github/workflows/release.yml`), Windows
gépen, neked nem kell semmit telepítened. Új verzió:

1. Írd át a verziószámot **mindkét** helyen ugyanarra, pl. `1.5.3`:
   - `config.py` → `APP_VERSION = "1.5.3"`
   - `installer.iss` → `#define MyAppVersion "1.5.3"` és `MyAppVersionInfo "1.5.3.0"`
2. Pushold fel (vagy szólj Claude-nak, hogy csinálja meg).
3. Kb. 10-20 perc múlva a repó **Releases** oldalán megjelenik:
   - `Proteus_Setup_1.5.3.exe` – új telepítéshez
   - `update_package_1.5.3.zip` – ezt tölti le a már telepített Proteus

A build állapota a repó **Actions** fülén látszik (Release). Kézzel is
indítható: Actions → Release → Run workflow. Ha a verziószám nem változott,
csak buildel, nem ad ki új release-t.

Az eredeti Rose frissítései innentől **nem jönnek automatikusan**. Ha
szeretnél átvenni valamit tőlük, azt kézzel kell behúzni az upstream
repóból (git-tel: `git remote add upstream https://github.com/Alban1911/Rose`).

## Amire figyelj

- **Skinek:** a skin fájlokat továbbra is az eredeti
  `Alban1911/LeagueSkins` repóból tölti le. Ezt minden League patch után
  frissíteni kell; ha sajátot akarsz, forkold és írd át a `SKINS_REPO`-t.
- **Party mode:** saját szerver kell hozzá, lásd lent.
- **Riot szabályok:** a skin changerek a Riot felhasználási feltételeibe
  ütköznek, a fiók tiltásának kockázata a sajátodnál is ugyanúgy fennáll.

## Party mode szerver beállítása

A party mode (a barátaid is látják a skinedet) egy kis szerveren
keresztül köti össze a játékosokat. Ez egy Cloudflare Worker, az ingyenes
csomag bőven elég hozzá. Mindent böngészőben kell csinálni, telepíteni
nem kell semmit.

1. **Cloudflare fiók:** regisztrálj a https://dash.cloudflare.com/sign-up
   oldalon (ingyenes, bankkártya nem kell).
2. **Workers bekapcsolása:** a bal menüben nyisd meg a
   **Compute (Workers)** → **Workers & Pages** oldalt egyszer. Ilyenkor kér
   egy alnevet (pl. `lildmate`), ebből lesz a szerver címe:
   `proteus-party-relay.lildmate.workers.dev`.
3. **Account ID:** ugyanott, a Workers & Pages oldal jobb oldalán (vagy a
   fiók főoldalán) van egy **Account ID**. Másold ki.
4. **API token:** jobb felül profil ikon → **My Profile** → **API Tokens**
   → **Create Token** → az **Edit Cloudflare Workers** sablonnál
   **Use template** → az Account Resources-nál válaszd a fiókodat, a Zone
   Resources-nál `All zones` → **Continue to summary** → **Create Token**.
   Másold ki a tokent (csak egyszer mutatja meg).
5. **Titkok a GitHubon:** a repóban **Settings** → **Secrets and
   variables** → **Actions** → **New repository secret**, kettőt:
   - `CLOUDFLARE_API_TOKEN` = a 4. lépés tokenje
   - `CLOUDFLARE_ACCOUNT_ID` = a 3. lépés Account ID-ja
6. **Szerver feltöltése:** **Actions** fül → **Party relay** → **Run
   workflow**. Egy perc múlva a futás összefoglalójában ott a szerver címe,
   pl. `wss://proteus-party-relay.lildmate.workers.dev`.
7. **Cím a programba:** újabb secret: `RELAY_URL` = a 6. lépés címe.
8. **Új verzió:** szólj Claude-nak (vagy emeld a verziószámot): a
   következő build már party mode-dal készül.

A barátaidnak is a Proteust kell használniuk, mert az eredeti Rose a saját
szerverére csatlakozik, így a kettő nem látja egymást.
