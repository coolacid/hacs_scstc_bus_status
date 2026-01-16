# SCSTC Bus Status

SCSTC Bus Status provides simple Home Assistant sensors for school bus
cancellations and bus notifications for Simcoe County schools.

Features
- Sensors for cancellation status and note for each group reported.
- Optional per-bus notifications when you add a `Bus` entry and provide a bus number.

Install (recommended)

- Install with HACS (preferred):

  [![Install via HACS](https://img.shields.io/badge/HACS-Install-brightgreen?logo=hacs)](https://github.com/your-github-username/scstc-bus-status)

  After adding the repository in HACS, go to HACS → Integrations → SCSTC Bus Status → Install.

Install (manual)

1. Copy the `custom_components/my_sensor/` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

Add the integration

- Go to Settings → Devices & Services → Add Integration and search for "SCSTC Bus Status".
- Choose the `type` you want: `Cancelation` (one only) or `Bus` (can add multiple). For `Bus`, you may provide a bus number.

Usage notes
- Cancellation sensors appear as `sensor.scstc_<...>` and provide `status` and `note` values for each reported key.
- Bus notifications are retrieved when you add one or more `Bus` entries (by bus number).

Support
- If you need help installing or configuring the integration, open an issue on the project repository.

