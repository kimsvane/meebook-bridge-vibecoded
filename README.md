# Meebook Bridge (HA app repository)

Home Assistant app-repository med ét add-on:

- [`meebook_bridge/`](meebook_bridge/) – kører en Playwright-browser i en
  container, logger ind på Meebook via Unilogin/MitID og eksponerer elevdata
  (elevplan, lektier, fravær) som JSON/REST til Home Assistant-sensorer.
- [`mac/`](mac/) – samme bridge kørende direkte på en Mac (uden HA).

## Installation

Supervisor → Tilføjelsesbutik → ⋮ → Repositories →
`https://github.com/kimsvane/meebook-bridge-vibecoded`

Se [`meebook_bridge/README.md`](meebook_bridge/README.md) for login og sensor-opsætning.