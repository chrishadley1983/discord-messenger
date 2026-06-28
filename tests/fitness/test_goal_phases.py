"""Unit tests for the goal/phase model on the fitness programme.

Covers: BMI helper, phase resolution (fat-loss vs muscle-build), the BMI
auto-switch, legacy backward-compatibility (no goal_config), and that
compute_current_targets honours the resolved phase's protein mode.
"""

from domains.fitness.service import (
    bmi, resolve_goal, compute_current_targets, default_goal_config,
)
from domains.fitness.tdee import DEFAULT_PROTEIN_G_PER_KG


GOAL_CONFIG = {
    "current_phase": "fat_loss",
    "auto_switch": {"metric": "bmi", "below": 25.0, "to_phase": "muscle_build"},
    "phases": {
        "fat_loss": {
            "label": "Fat loss first",
            "focus": "Weight loss is the priority.",
            "protein": {"mode": "fixed", "g": 125},
            "protein_note": "125 g floor.",
            "rule": "Hit ~125 g protein and stay under calories.",
        },
        "muscle_build": {
            "label": "Build muscle",
            "focus": "Build lean mass.",
            "protein": {"mode": "adaptive", "g_per_kg": 2.0},
            "protein_note": "~2.0 g/kg.",
            "rule": "Hit protein (~2.0 g/kg).",
        },
    },
}


def _programme(**over):
    """A minimal active-programme dict matching Chris's reset cut."""
    p = {
        "id": "p1",
        "protein_g_per_kg": 2.0,
        "deficit_kcal": 840,
        "daily_protein_g": 125,
        "daily_calorie_target": 2050,
        "daily_steps_target": 15000,
        # deep-copy the goal_config so per-test mutations don't leak
        "goal_config": {
            **GOAL_CONFIG,
            "phases": {k: {**v, "protein": dict(v["protein"])}
                       for k, v in GOAL_CONFIG["phases"].items()},
        },
    }
    p.update(over)
    return p


class TestBmi:
    def test_healthy_threshold_weight(self):
        # 178cm: BMI 25 lands at ~79.2kg.
        assert round(bmi(79.21, 178), 1) == 25.0

    def test_overweight_now(self):
        assert bmi(91, 178) > 25


class TestResolveGoal:
    def test_fat_loss_active_above_threshold(self):
        g = resolve_goal(_programme(), 91.0)   # BMI ~28.7
        assert g["current_phase"] == "fat_loss"
        assert g["effective_phase"] == "fat_loss"
        assert g["transitioned"] is False
        assert g["phase"]["protein"] == {"mode": "fixed", "g": 125}

    def test_switches_to_muscle_build_below_bmi(self):
        g = resolve_goal(_programme(), 78.0)   # BMI ~24.6 < 25
        assert g["current_phase"] == "fat_loss"
        assert g["effective_phase"] == "muscle_build"
        assert g["transitioned"] is True
        assert g["phase"]["protein"]["mode"] == "adaptive"
        assert g["phase"]["protein"]["g_per_kg"] == 2.0

    def test_no_switch_once_in_muscle_build(self):
        p = _programme()
        p["goal_config"]["current_phase"] = "muscle_build"
        g = resolve_goal(p, 91.0)
        assert g["effective_phase"] == "muscle_build"
        assert g["transitioned"] is False

    def test_no_weight_no_switch(self):
        g = resolve_goal(_programme(), None)
        assert g["effective_phase"] == "fat_loss"
        assert g["bmi"] is None

    def test_legacy_no_goal_config_is_adaptive(self):
        g = resolve_goal(_programme(goal_config=None), 91.0)
        assert g["config"] is None
        assert g["phase"]["protein"]["mode"] == "adaptive"
        # backfilled from the programme's protein_g_per_kg column
        assert g["phase"]["protein"]["g_per_kg"] == 2.0

    def test_adaptive_phase_backfills_gkg_from_column(self):
        p = _programme()
        del p["goal_config"]["phases"]["muscle_build"]["protein"]["g_per_kg"]
        p["goal_config"]["current_phase"] = "muscle_build"
        g = resolve_goal(p, 91.0)
        assert g["phase"]["protein"]["g_per_kg"] == 2.0


class TestComputeCurrentTargetsHonoursPhase:
    def test_fixed_phase_pins_protein(self):
        r = compute_current_targets(_programme(), 91.0, 15000)
        assert r.target_protein_g == 125          # fixed, NOT 2.0*91=182

    def test_muscle_phase_scales_protein(self):
        p = _programme()
        p["goal_config"]["current_phase"] = "muscle_build"
        r = compute_current_targets(p, 79.0, 15000)
        assert r.target_protein_g == 160          # 2.0*79=158 → nearest 5

    def test_auto_switch_applies_in_targets(self):
        # Stored phase is fat_loss but BMI is below threshold → adaptive.
        r = compute_current_targets(_programme(), 78.0, 15000)
        assert r.target_protein_g == 155          # 2.0*78=156 → nearest 5

    def test_explicit_factor_override_still_wins(self):
        # Callers can still force a multiplier (back-compat).
        r = compute_current_targets(_programme(), 91.0, 15000, protein_g_per_kg=1.8)
        assert r.target_protein_g == 165          # 1.8*91=163.8 → nearest 5

    def test_calories_unaffected_by_phase(self):
        # Protein phase must not change the calorie deficit behaviour.
        fixed = compute_current_targets(_programme(), 91.0, 15000)
        p = _programme()
        p["goal_config"]["current_phase"] = "muscle_build"
        adaptive = compute_current_targets(p, 91.0, 15000)
        assert fixed.target_calories == adaptive.target_calories


class TestDefaultGoalConfig:
    def test_floor_derived_from_start_weight(self):
        # 1.4 g/kg of 90.1kg = 126.14 → nearest 5 = 125
        cfg = default_goal_config(90.1)
        assert cfg["current_phase"] == "fat_loss"
        assert cfg["phases"]["fat_loss"]["protein"] == {"mode": "fixed", "g": 125}
        assert cfg["auto_switch"] == {"metric": "bmi", "below": 25.0, "to_phase": "muscle_build"}
        assert cfg["phases"]["muscle_build"]["protein"]["mode"] == "adaptive"

    def test_floor_scales_with_weight(self):
        assert default_goal_config(100)["phases"]["fat_loss"]["protein"]["g"] == 140
        assert default_goal_config(80)["phases"]["fat_loss"]["protein"]["g"] == 110

    def test_seeded_programme_resolves_fat_loss_fixed(self):
        prog = {
            "protein_g_per_kg": DEFAULT_PROTEIN_G_PER_KG, "daily_protein_g": 125,
            "deficit_kcal": 550, "daily_steps_target": 15000,
            "goal_config": default_goal_config(90.1),
        }
        g = resolve_goal(prog, 90.0)            # BMI ~28.4 > 25
        assert g["effective_phase"] == "fat_loss"
        r = compute_current_targets(prog, 90.0, 15000)
        assert r.target_protein_g == 125        # flat floor, not weight-scaled
