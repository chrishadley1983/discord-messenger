"""Octopus Energy domain — live Home Mini telemetry + consumption sync.

Consolidated from hadley-bricks-inventory-management/scripts/energy in
Jun 2026. Modules:

- config: env-driven settings (meters, tariffs, device id, webhook)
- kraken: GraphQL client with cached JWT
- telemetry: 30s Home Mini poller -> energy_live + local log
- octopus_sync: daily half-hourly consumption/tariff sync (complete days only)
- weekly_digest / monthly_billing / chart: scheduled Discord outputs
- events: appliance event detection from live telemetry
- dispatches: Intelligent Go planned dispatch / EV attribution
- service: read-model helpers for the Hadley API endpoints
"""
