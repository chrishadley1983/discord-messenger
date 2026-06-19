-- Make the weight-adaptive target engine configurable per programme.
-- Previously the deficit (550 kcal) and protein factor (1.67 g/kg) were
-- hardcoded defaults in compute_tdee/compute_current_targets, so a deliberately
-- aggressive plan was silently "corrected" back to those values by the
-- dashboard/weekly-review drift + recalibrate machinery.
--
-- With these columns, compute_current_targets reads the programme's own deficit
-- and protein factor, so live targets match the plan AND still auto-adjust down
-- as BMR drops with weight loss.

ALTER TABLE fitness_programmes
  ADD COLUMN IF NOT EXISTS deficit_kcal integer NOT NULL DEFAULT 550,
  ADD COLUMN IF NOT EXISTS protein_g_per_kg numeric(4,2) NOT NULL DEFAULT 1.67;

COMMENT ON COLUMN fitness_programmes.deficit_kcal IS 'Daily kcal deficit below TDEE used by the weight-adaptive target engine (compute_current_targets). Lets a programme set a more/less aggressive deficit than the 550 default.';
COMMENT ON COLUMN fitness_programmes.protein_g_per_kg IS 'Protein target in g per kg bodyweight used by the target engine. Default 1.67; raise for stronger lean-mass preservation on an aggressive cut.';
