-- Durable record of Octopus Intelligent Go EV charge dispatch slots.
-- completedDispatches age out of the Octopus API within ~1-2 days, so we
-- persist them here to audit the off-peak attribution and reclassify days.
-- Applied to project modjoikyuhqzouxvieua on 2026-06-15.
CREATE TABLE IF NOT EXISTS public.energy_dispatches (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    start_at    timestamptz NOT NULL UNIQUE,
    end_at      timestamptz NOT NULL,
    kwh         numeric DEFAULT 0,
    source      text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS energy_dispatches_start_idx
    ON public.energy_dispatches (start_at);

ALTER TABLE public.energy_dispatches ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.energy_dispatches IS
    'Octopus Intelligent Go EV charge dispatch slots (planned/completed). Ground truth for off-peak attribution of daytime smart-charging.';
