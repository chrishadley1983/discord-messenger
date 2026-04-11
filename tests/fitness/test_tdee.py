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
        # 93kg, 183cm, 42yo male:
        # 10*93 + 6.25*183 - 5*42 + 5 = 930 + 1143.75 - 210 + 5 = 1868.75 → 1869
        bmr = mifflin_st_jeor_bmr(93, 183, 42, "male")
        assert bmr == 1869

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


class TestActivityFactor:
    @pytest.mark.parametrize("steps,expected", [
        (3000, 1.2),
        (6000, 1.375),
        (10000, 1.55),
        (14000, 1.725),
        (20000, 1.9),
    ])
    def test_step_bucket_mapping(self, steps, expected):
        assert activity_factor_from_steps(steps) == expected

    def test_boundary_behaviour(self):
        assert activity_factor_from_steps(4999) == 1.2
        assert activity_factor_from_steps(5000) == 1.375
        assert activity_factor_from_steps(7999) == 1.375
        assert activity_factor_from_steps(8000) == 1.55


class TestComputeTdee:
    def test_chris_starting_values(self):
        # 94kg, 183cm, 42yo, 10k avg steps
        r = compute_tdee(94, 183, 42, avg_steps=10000)
        assert r.bmr == 1879  # 10*94 + 6.25*183 - 5*42 + 5 = 1878.75 → 1879
        assert r.activity_factor == 1.55
        assert r.tdee == round(r.bmr * 1.55)
        assert r.target_calories == r.tdee - 550
        # 1.8 * 94 = 169.2, rounded to nearest 5 = 170
        assert r.target_protein_g == 170

    def test_deficit_override(self):
        r = compute_tdee(90, 180, 40, avg_steps=12000, deficit_kcal=400)
        assert r.deficit_kcal == 400
        assert r.target_calories == r.tdee - 400

    def test_protein_is_rounded_to_5g(self):
        r = compute_tdee(93.7, 183, 42, avg_steps=10000)
        assert r.target_protein_g % 5 == 0


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
