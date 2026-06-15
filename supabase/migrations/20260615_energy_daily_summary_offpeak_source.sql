-- Audit fields on energy_daily_summary so a dispatch-verified off-peak split is
-- distinguishable from a clock-only one (and from a day where the Octopus
-- dispatch fetch was unavailable and may be silently misclassified).
-- Applied to project modjoikyuhqzouxvieua on 2026-06-15.
ALTER TABLE public.energy_daily_summary
    ADD COLUMN IF NOT EXISTS dispatch_kwh   numeric DEFAULT 0,
    ADD COLUMN IF NOT EXISTS offpeak_source text;

COMMENT ON COLUMN public.energy_daily_summary.dispatch_kwh IS
    'kWh attributed to off-peak via an Octopus dispatch slot (outside the fixed clock window).';
COMMENT ON COLUMN public.energy_daily_summary.offpeak_source IS
    'How the off-peak split was derived: dispatch | clock | clock-fallback (dispatch data unavailable).';
