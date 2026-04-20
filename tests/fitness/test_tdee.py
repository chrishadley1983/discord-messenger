"""Unit tests for TDEE / Mifflin-St Jeor calculation."""

import pytest

from domains.fitness.tdee import (
    mifflin_st_jeor_bmr,
    activity_factor_from_steps,
    compute_tdee,
    weeks_to_target,
)


class TestBMR:
    def test_male_bmr_reference_value(self):
        # 93kg, 178cm, 42yo male (Chris's actual height):
        # 10*93 + 6.25*178 - 5*42 + 5 = 930 + 1112.5 - 210 + 5 = 1837.5 → 1838
        bmr = mifflin_st_jeor_bmr(93, 178, 42, "male")
        assert bmr == 1838

    def test_female_bmr_lower_than_male(self):
        male = mifflin_st_jeor_bmr(70, 170, 40, "male")
        female = mifflin_st_jeor_bmr(70, 170, 40, "female")
        assert female < male
        assert male - female == 166   # fixed offset per Mifflin-St Jeor

    def test_weight_is_dominant_driver(self):
        lean = mifflin_st_jeor_bmr(80, 180, 40)
        heavy = mifflin_st_jeor_bmr(100, 180, 40)
        assert heavy > lean
        assert heavy - lean == 200   # 10 * 20kg delta

    def test_bmr_drops_as_weight_drops(self):
        """Adaptation check: losing weight reduces BMR by ~10 kcal per kg."""
        start = mifflin_st_jeor_bmr(94, 178, 42, "male")
        mid = mifflin_st_jeor_bmr(89, 178, 42, "male")
        end = mifflin_st_jeor_bmr(84, 178, 42, "male")
        assert start - mid == 50   # 5kg loss
        assert mid - end == 50     # another 5kg


class TestActivityFactor:
    @pytest.mark.parametrize("steps,expected", [
        (3000, 1.2),
        (6000, 1.375),
        (10000, 1.5),
        (14000, 1.6),
        (20000, 1.75),
    ])
    def test_step_bucket_mapping(self, steps, expected):
        assert activity_factor_from_steps(steps) == expected

    def test_boundary_behaviour(self):
        assert activity_factor_from_steps(4999) == 1.2
        assert activity_factor_from_steps(5000) == 1.375
        assert activity_factor_from_steps(7999) == 1.375
        assert activity_factor_from_steps(8000) == 1.5
        assert activity_factor_from_steps(11999) == 1.5
        assert activity_factor_from_steps(12000) == 1.6
        assert activity_factor_from_steps(15999) == 1.6
        assert activity_factor_from_steps(16000) == 1.75


class TestComputeTdee:
    def test_chris_starting_values(self):
        # 94kg, 178cm, 42yo, 15k avg steps — what Chris's programme starts at
        r = compute_tdee(94, 178, 42, avg_steps=15000)
        # 10*94 + 6.25*178 - 5*42 + 5 = 940 + 1112.5 - 210 + 5 = 1847.5 → 1848
        assert r.bmr == 1848
        assert r.activity_factor == 1.6
        assert r.tdee == round(r.bmr * 1.6)
        assert r.target_calories == r.tdee - 550
        # 1.67 * 94 = 156.98 → rounded to nearest 5 = 155
        assert r.target_protein_g == 155

    def test_deficit_override(self):
        r = compute_tdee(90, 180, 40, avg_steps=12000, deficit_kcal=400)
        assert r.deficit_kcal == 400
        assert r.target_calories == r.tdee - 400

    def test_protein_is_rounded_to_5g(self):
        r = compute_tdee(93.7, 178, 42, avg_steps=15000)
        assert r.target_protein_g % 5 == 0

    def test_protein_ratio_override(self):
        # Explicit higher ratio for muscle-retention research protocol
        r = compute_tdee(90, 178, 42, avg_steps=15000, protein_g_per_kg=1.8)
        # 1.8 * 90 = 162 → rounded to nearest 5 = 160
        assert r.target_protein_g == 160

    def test_targets_drop_as_weight_drops(self):
        """Adaptation check: losing weight drops calorie target because
        BMR (and therefore TDEE) fall with bodyweight."""
        start = compute_tdee(94, 178, 42, avg_steps=15000)
        after_5kg = compute_tdee(89, 178, 42, avg_steps=15000)
        after_10kg = compute_tdee(84, 178, 42, avg_steps=15000)
        # BMR drops 50 kcal per 5kg; at 1.6 factor that's 80 TDEE kcal
        assert start.tdee - after_5kg.tdee == 80
        assert after_5kg.tdee - after_10kg.tdee == 80
        # Target calories follow TDEE down
        assert start.target_calories > after_5kg.target_calories > after_10kg.target_calories
        # Protein target also drops (because it's per-kg)
        assert start.target_protein_g > after_10kg.target_protein_g


class TestWeeksToTarget:
    def test_10kg_at_default_rate(self):
        # 10kg at 0.77 kg/wk ≈ 13 weeks
        weeks = weeks_to_target(94, 84, weekly_loss_kg=0.77)
        assert weeks == 13

    def test_target_already_hit(self):
        assert weeks_to_target(80, 84) == 0

    def test_custom_rate(self):
        weeks = weeks_to_target(100, 90, weekly_loss_kg=0.5)
        assert weeks == 20
