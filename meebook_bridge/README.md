# Meebook Bridge for Home Assistant

Kører en browser (Playwright) i en HA add-on-container, logger ind på Meebook
som forælder via Unilogin/MitID og fanger Meebooks REST-API-svar (elevplan,
lektier, fravær osv.). Dataene eksponeres som JSON på port **8600** til
Home Assistant REST-sensorer.

## Installation

### Via GitHub-repo

1. Supervisor → Tilføjelsesbutik → ⋮ → **Repositories** →
   `https://github.com/kimsvane/meebook-bridge-vibecoded`
2. Find **Meebook Bridge** → **Installer** (containeren bygges automatisk,
   kan tage et par minutter) → **Start**.

### Lokal add-on (uden GitHub)

1. Kopiér mappen `meebook_bridge/` til `/addons/meebook_bridge/` på HA'ens
   configuration (fx via Samba).
2. Supervisor → Tilføjelsesbutik → ⋮ → **Repositories** → tilføj `local`.
3. Find **Meebook Bridge** → **Installer** → **Start**.

> HACS er ikke nødvendigt – HACS er til integrationer. Add-ons installeres
> via Supervisor, lokalt eller fra et repo.

## Første login (indlejret, ingen VNC)

Den nødvendige manuelle Unilogin/MitID-godkendelse sker helt i
add-on'ets web-interface:

1. Åbn add-on'et fra assistentens sidepanel.
2. Klik **Login (indlejret browser)**. En headless browser i containeren
   åbner Meebook-login, og du ser siden live i web-UI'et som skærmbillede -
   klik og tast i sidepanelet, som var det din egen browser
   (skriv fx CPR/MitID-navn i feltet, klik i Unilogin-flowet).
3. Godkend i MitID-appen (husk også at klikke/bekræfte i UI'et hvis nødvendigt).
4. Når du har ramt dashboardet, gemmer add-on'en sessionen automatisk.
   Derefter fornyer den selv sessionen hvert `refresh_interval_minutes` og
   fanger dataene - ingen login nødvendig før næste sessionudløb.

Tip: Har du allerede logget ind med `mac/`-versionen, kan du kopiere dens
`profile/` og `cookies.json` ind på HA'ens
`/addons/meebook_bridge/data/` og springe login'et over.

## Home Assistant-sensorer

### Anbefalet: Custom integration (entuelt mod Z2M-stil)

Add-on'en installerer automatisk en **custom integration** i
`/config/custom_components/meebook_bridge/` ved opstart. Sådan aktiveres den:

1. **Genstart Home Assistant** (Indstillinger → System → Genstart) – ikke kun add-on'en –
   så HA læser den nye integration.
2. Indstillinger → Enheder & tjenester → **Tilføj integration** → søg efter
   **Meebook Bridge**.
3. Angiv værtsnavn/port (standard `hassio.local:8600`). Virker `hassio.local`
   ikke, så brug din HA's LAN-IP (fx `192.168.1.10`).
4. Integrationen opretter så **én sensor pr. fanget endpoint** (fx
   `sensor.meebook_annualplans_latest`, `sensor.meebook_notifications` osv.)
   under énheden **Meebook**. Værdien er en kort sammenfatning (fx
   "2A – Matematik"), og alle JSON-værdierne ligger som **attributter**
   – inkl. den rå JSON i attributten `json`.

Da der automatisk oprettes en sensor, hver gang add-on'en fanger et nyt
endpoint, kan du se alle tilgængelige felter direkte på enheden.

### Automatisk via MQTT-discovery

Installér **Mosquitto broker**-add-on'en én gang. Så opretter Meebook Bridge
automatisk disse sensorer i Home Assistant (ingen YAML nødvendig):

- `sensor.meebook_elev` – barnets navn
- `sensor.meebook_seneste_aarsplan` – seneste årsplan (fx "2A – Matematik")
- `sensor.meebook_antal_aarsplaner` – antal planer
- `sensor.meebook_aarsplaner` – antal planer i nuværende skoleår
- `sensor.meebook_skoleaar` – nuværende skoleår
- `sensor.meebook_seneste_besked` – seneste besked/notifikation
- `sensor.meebook_beskeder` – antal beskeder
- `sensor.meebook_ugeplan_events` – antal ugeplan-begivenheder
- `sensor.meebook_aarsplan_<id>` – aktiviteter pr. årsplan (detalje)

Sensor-værdierne opdateres ved hver refresh.

### Manuel med REST-sensorer

Bekræftede endpoints (med data): `/rest/related/students`, `/rest/annualplans/latest`,
`/rest/annualplans` (detaljer: `/rest/annualplans/<id>` med lektier/aktiviteter),
`/rest/notifications`, `/rest/weekplan/events`, `/rest/yearSpans`.

Tilføj i `configuration.yaml`. Bemærk: `localhost` virker ikke – HA core og
add-ons kører i hver sin container. Brug `http://<HA_IP>:8600/...` eller
`http://hassio.local:8600/...`.

```yaml
rest:
  - resource: "http://<HA_IP>:8600/data/rest/related/students"
    scan_interval: 3600
    sensor:
      - name: "Meebook elev"
        value_template: "{{ value_json['items'][0]['name'] }}"

  - resource: "http://<HA_IP>:8600/data/rest/annualplans/latest"
    scan_interval: 300
    sensor:
      - name: "Meebook - årsplaner"
        value_template: "{{ value_json['items'][0]['categories'] | join(', ') }}"

  - resource: "http://<HA_IP>:8600/data/rest/annualplans/<planID>"
    scan_interval: 300
    sensor:
      - name: "Meebook - plan (lektier/aktiviteter)"
        value_template: "{{ (value_json.activities | default([])) | length }} aktiviteter"

  - resource: "http://<HA_IP>:8600/data/rest/notifications"
    scan_interval: 300
    sensor:
      - name: "Meebook - seneste besked"
        value_template: "{{ value_json['items'][0]['data']['senderName'] }}"

  - resource: "http://<HA_IP>:8600/data/rest/weekplan/events"
    scan_interval: 300
    sensor:
      - name: "Meebook - ugeplan events"
        value_template: "{{ value_json['items'] | length }}"
```

Find plan-ID'et i `/rest/annualplans/latest`-svaret under **Se data (JSON)**.

## Indstillinger (Options)

| Option | Beskrivelse |
|---|---|
| `refresh_interval_minutes` | Hvor tit session fornyes/data hentes (min.) |
| `navigate_urls` | Sider browseren besøger for at udløse API-kald |
| `page_settle_ms` | Ventetid efter sideindlæsning før svar fanges |
| `headless_refresh` | Refresh kører uden skærm (anbefalet) |

## API

| Endpoint | Beskrivelse |
|---|---|
| `GET /health` | Status (session, sidste login, ids, endpoints) |
| `POST /login` | Starter indlejret MitID-login (se `/remote`) |
| `GET /remote` | Web-UI med live-skærmbillede + input-videresendelse |
| `GET /snapshot` | Seneste login-skærmbillede (JPEG) |
| `POST /input/click` · `/input/type` · `/input/key` · `/input/scroll` | Styr login-browseren |
| `POST /refresh` | Hent data nu |
| `GET /data` | Alle fangede REST-svar som JSON |
| `GET /data/rest/...` | Et enkelt fanget endpoint |

## Filer

- `config.yaml` / `Dockerfile` / `run.sh` / `app.py` / `requirements.txt` – selve add-on'et
- `repository.yaml` / `README.md` – repo-layoutet (add-on ligger i `meebook_bridge/`)
- `mac/` – samme bridge, kørbar direkte på en Mac (kræver ikke HA)