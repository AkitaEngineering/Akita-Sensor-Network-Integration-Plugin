# Akita Sensor Network Integration Plugin (ASNIP)

ASNIP integrates sensor readings with Meshtastic: it periodically broadcasts
local sensor values on a private port and logs both local and remote sensor
messages to a JSON file. This repository contains the plugin implementation
and test helpers used during development.

**Organization:** Akita Engineering
**License:** GPLv3 (see `LICENSE`)

---

## Quick Start

1. Install dependencies into your Python environment:

```bash
pip install -r requirements.txt
```

2. Make the plugin available to Meshtastic. During development you can run
   the plugin code directly from `src/` (see tests for examples).

3. Configure sensors via `sensors.json` (see `docs/README.md` for schema).

4. Run the plugin inside Meshtastic or use the test harness to exercise
   functionality locally.

---

## Installation

- System deployment: copy `src/asnip/asnip.py` to Meshtastic's plugin
  directory (e.g. `~/.meshtastic/plugins/`).
- Development: import `asnip.asnip` from the `src/` folder (tests already
  do this by adding `src/` to `sys.path`).

Install only the runtime dependencies you need; the BME280 driver is
optional unless you use bme280 sensor types.

```bash
pip install meshtastic
pip install adafruit-circuitpython-bme280  # optional
```

---

## Configuration

ASNIP reads configuration from `sensors.json`. The search order is:

1. `ASNIP_CONFIG` environment variable
2. `./sensors.json` (current working directory)
3. `sensors.json` located next to the plugin file

If missing, a reasonable default config will be created for you.

See `docs/README.md` for a full configuration schema and examples.

---

## Sensor Types

- `simulated_temperature` / `simulated_humidity` — simulated values for testing
- `random_value` — integer between `min_val` and `max_val`
- `static_value` — returns a fixed value configured in `params`
- `custom_script` — runs an external script (use caution)
- `bme280_temperature` / `bme280_humidity` / `bme280_pressure` — hardware
  sensor values (requires BME280 library and hardware)

Security note: `custom_script` uses shell execution. Ensure `sensors.json`
is protected from untrusted writers.

---

## Development & Tests

Run tests with `pytest` from the repository root. The test suite includes
examples for importing the plugin from `src/` and exercising the main
behaviors.

```bash
python -m pytest -q
```

---

## Contributing

Contributions are welcome. Please open issues or PRs; include tests for
behavioral changes. If you change licensing or add new dependencies include
justification in the PR description.

---

## Files of Interest

- `src/asnip/asnip.py` — plugin implementation
- `sensors.json` — example/default configuration
- `tests/` — unit tests used during development
- `docs/` — additional documentation

---

If you want, I can add a GitHub Actions workflow to run tests on push/PR.
