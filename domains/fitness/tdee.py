"""TDEE estimation using Mifflin-St Jeor BMR + activity factor.

For a male (hard-coded for Chris), BMR = 10*kg + 6.25*cm - 5*age + 5.
Activity factor is derived from recent average step count so it self-tunes:
    <5k    sedentary       1.2
    5-8k   light           1.375
    8-12k  moderate        1.5
    12-16k active          1.6
    16k+   very active     1.75

These multipliers were recalibrated from the original Mifflin-St Jeor labels
because the textbook 1.725/1.9 buckets assume manual-labour jobs or 6-7 days
of hard training. For a primarily-walking-driven active day (e.g. 15k steps
plus short bodyweight workouts) those classic buckets over-estimate TDEE by
~150-250 kcal. The bottom-up MET calc (BMR + walking METs + TEF + other NEAT)
clusters around the current 1.6 multiplier for 15k steps, so we match that.

We then apply a 500-600 kcal deficit for 0.5-0.7 kg/week loss.

The programme is weight-adaptive: `compute_tdee` takes CURRENT weight. As Chris
loses weight, BMR drops and the target_calories should be recomputed from the
latest trend weight (see `domains/fitness/service.py::compute_current_targets`).
"""

from __future__ import annotations

from dataclasses import dataclass

# Protein target in g per kg bodyweight. 1.67 is above the 1.6 g/kg research
# floor for muscle retention in a cut, while rounding to more achievable
# numbers (e.g. 150g at 90kg instead of 162g at 1.8 g/kg).
DEFAULT_PROTEIN_G_PER_KG = 1.67


@dataclass
class TdeeResult:
    bmr: int                    # Mifflin-St Jeor BMR
    activity_factor: float      # multiplier from step average
    tdee: int                   # bmr * activity_factor
    target_calories: int        # tdee - deficit
    target_protein_g: int       # protein_per_kg * weight_kg (rounded to nearest 5)
    deficit_kcal: int           # kcal below TDEE


def mifflin_st_jeor_bmr(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: str = "male",
) -> int:
    """Mifflin-St Jeor resting metabolic rate.

    Considered the most accurate population estimate for sedentary-to-active
    adults. Rounded to nearest integer.
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age_years
    if sex.lower() == "male":
        return round(base + 5)
    return round(base - 161)


def activity_factor_from_steps(avg_steps: float) -> float:
    """Map 7-day average step count to an activity multiplier.

    Recalibrated (vs textbook Mifflin labels) so that walking-heavy lifestyles
    aren't over-estimated. The 12-16k bucket is 1.6 (not 1.725) because the
    bottom-up MET calculation for 15k steps adds ~630 kcal above BMR, not the
    1,310 kcal that 1.725 implies.
    """
    if avg_steps < 5000:
        return 1.2
    if avg_steps < 8000:
        return 1.375
    if avg_steps < 12000:
        return 1.5
    if avg_steps < 16000:
        return 1.6
    return 1.75


def compute_tdee(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    avg_steps: float,
    sex: str = "male",
    deficit_kcal: int = 550,
    protein_g_per_kg: float = DEFAULT_PROTEIN_G_PER_KG,
) -> TdeeResult:
    """Full TDEE + targets calculation.

    Call this with CURRENT weight each time — BMR drops as weight drops, so
    the deficit shrinks if you eat at a fixed target. Re-running this weekly
    keeps the deficit genuine.

    Args:
        weight_kg: Current body weight.
        height_cm: Height in cm.
        age_years: Age in years.
        avg_steps: 7-day average daily step count (from Garmin).
        sex: 'male' or 'female'.
        deficit_kcal: Daily deficit (default 550 -> ~0.6 kg/week).
        protein_g_per_kg: Protein target per kg bodyweight (default 1.67).

    Returns:
        TdeeResult with BMR, TDEE, target calories and protein.
    """
    bmr = mifflin_st_jeor_bmr(weight_kg, height_cm, age_years, sex)
    factor = activity_factor_from_steps(avg_steps)
    tdee = round(bmr * factor)
    target_cals = tdee - deficit_kcal
    # Protein rounded to nearest 5g for easier tracking
    protein = round((protein_g_per_kg * weight_kg) / 5) * 5
    return TdeeResult(
        bmr=bmr,
        activity_factor=factor,
        tdee=tdee,
        target_calories=target_cals,
        target_protein_g=int(protein),
        deficit_kcal=deficit_kcal,
    )


def weeks_to_target(
    start_weight_kg: float,
    target_weight_kg: float,
    weekly_loss_kg: float = 0.77,
) -> int:
    """How many weeks to reach target at expected weekly loss rate.

    Default 0.77 kg/week = 10kg in 13 weeks (aggressive but realistic on
    a 550 kcal deficit with high protein and 12k+ steps).
    """
    if target_weight_kg >= start_weight_kg:
        return 0
    return int(round((start_weight_kg - target_weight_kg) / weekly_loss_kg))

