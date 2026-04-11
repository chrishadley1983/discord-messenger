"""TDEE estimation using Mifflin-St Jeor BMR + activity factor.

For a male (hard-coded for Chris), BMR = 10*kg + 6.25*cm - 5*age + 5.
Activity factor is derived from recent average step count so it self-tunes:
    <5k   sedentary       1.2
    5-8k  light           1.375
    8-12k moderate        1.55
    12-16k active         1.725
    16k+  very active     1.9

We then apply a 500-600 kcal deficit for 0.5-0.7 kg/week loss.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TdeeResult:
    bmr: int                    # Mifflin-St Jeor BMR
    activity_factor: float      # multiplier from step average
    tdee: int                   # bmr * activity_factor
    target_calories: int        # tdee - deficit
    target_protein_g: int       # 1.8 * weight_kg (rounded to nearest 5)
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

    Self-tuning: don't need the user to self-rate their activity level.
    """
    if avg_steps < 5000:
        return 1.2
    if avg_steps < 8000:
        return 1.375
    if avg_steps < 12000:
        return 1.55
    if avg_steps < 16000:
        return 1.725
    return 1.9


def compute_tdee(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    avg_steps: float,
    sex: str = "male",
    deficit_kcal: int = 550,
) -> TdeeResult:
    """Full TDEE + targets calculation.

    Args:
        weight_kg: Current body weight.
        height_cm: Height in cm.
        age_years: Age in years.
        avg_steps: 7-day average daily step count (from Garmin).
        sex: 'male' or 'female'.
        deficit_kcal: Daily deficit (default 550 -> ~0.6 kg/week).

    Returns:
        TdeeResult with BMR, TDEE, target calories and protein.
    """
    bmr = mifflin_st_jeor_bmr(weight_kg, height_cm, age_years, sex)
    factor = activity_factor_from_steps(avg_steps)
    tdee = round(bmr * factor)
    target_cals = tdee - deficit_kcal
    # Protein: 1.8g/kg, round to nearest 5g
    protein = round((1.8 * weight_kg) / 5) * 5
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
