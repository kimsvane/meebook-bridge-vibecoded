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

Tilføj i `configuration.yaml` (erstat `HA_IP`):

```yaml
rest:
  - resource: "http://<HA_IP>:8600/data/rest/annualplans"
    scan_interval: 300
    sensor:
      - name: "Meebook årsplaner"
        value_template: "{{ value_json | tojson }}"

  - resource: "http://<HA_IP>:8600/data/rest/annualplans/<planID>"
    scan_interval: 300
    sensor:
      - name: "Meebook lektier"
        value_template: "{{ value_json.activities | tojson }}"
```

Find de relevante endpoints under **add-on'ets web-interface** (sidepanel):
alle fangede `/rest/...`-URL'er er listet med link, og `/health` viser
elev-ID og årsplan-ID automatisk.

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