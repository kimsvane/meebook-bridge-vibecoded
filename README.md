<<<<<<< HEAD
# meebook-bridge-vibecoded
=======
# Meebook Bridge for Home Assistant

Kører en browser (Playwright) i en HA add-on-container, logger ind på Meebook
som forælder via Unilogin/MitID og fanger Meebooks REST-API-svar (elevplan,
lektier, fravær osv.). Dataene eksponeres som JSON på port **8600** til
Home Assistant REST-sensorer.

## Installation

### Lokal add-on (ingen GitHub/HACS nødvendig)

1. Kopiér hele denne mappe til din Home Assistant-installation under
   `/addons/meebook_bridge/` (fx via Samba/share).
2. Gå til **Indstillinger → Tilføjelsesprogrammer (Add-ons)** → **Tilføjelsesbutik**.
3. Klik de tre prikker øverst højre → **Repositories** → tilføj `local` og klik **Tilføj**.
4. Find **Meebook Bridge** i listen → **Installer** (containeren bygges automatisk,
   kan tage et par minutter) → **Start**.

### Via GitHub-repo (samme flow, bare online)

1. Gør repo-roden til dette add-on (mappen med denne `config.yaml`).
2. Supervisor → Butik → tre prikker → **Repositories** → tilføj repo-URL'en.
3. Installér og start.

> HACS er ikke nødvendigt – HACS er til integrationer. Add-ons installeres
> via Supervisor, lokalt eller fra et repo.

## Første login (Unilogin/MitID)

Bridgen skal logge ind én gang manuelt. Browseren kører i containeren på en
virtuel skærm, så du åbner den via VNC:

1. Forbind til VNC på HA'en: `vnc://<HA-IP>:5900` (fx via Screen Sharing-appen).
   Hvis du har sat `vnc_password`, tastes den.
2. Tryk **Login (ny MitID-godkendelse)** i add-on'ets web-interface (åbnes fra
   assistentens sidepanel), eller kør `POST /login`.
3. Udfør login-flowet (Unilogin → MitID → godkend i MitID-appen).
4. Derefter fornyer add-on'en selv sessionen hver `refresh_interval_minutes`
   og fanger dataene – ingen VNC nødvendig før næste sessionudløb.

Tip: Har du allerede logget ind med `mac/`-versionen, kan du kopiere dens
`profile/`- og `cookies.json` ind på HA'ens `/addons/meebook_bridge/data/`
og springe VNC-login over.

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
| `vnc_password` | Adgangskode til VNC-login (tom = ingen kode) |

## API

| Endpoint | Beskrivelse |
|---|---|
| `GET /health` | Status (session, sidste login, ids, endpoints) |
| `POST /login` | Starter manuel MitID-login (browser på VNC-skærmen) |
| `POST /refresh` | Hent data nu |
| `GET /data` | Alle fangede REST-svar som JSON |
| `GET /data/rest/...` | Et enkelt fanget endpoint |

## Filer

- `config.yaml` / `Dockerfile` / `run.sh` / `app.py` / `requirements.txt` – selve add-on'et
- `mac/` – samme bridge, kørbar direkte på en Mac (kræver ikke HA)
>>>>>>> 3ceab38 (Meebook Bridge: HA add-on med Playwright-session og REST-data)
