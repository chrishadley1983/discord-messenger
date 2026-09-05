"""Phase 2: Fitbod CSV parsing + Garmin activity matching (pure functions)."""
from domains.fitness import fitbod_import as fb
from domains.fitness import garmin_activities as ga


CSV = """Date,Exercise,Reps,Weight(kg),Duration(s),Distance(m),Incline,Resistance,isWarmup,Note,multiplier
2026-09-05 10:12:33 +0100,Lat Pulldown,10,20.0,0,0,0,0,true,,1
2026-09-05 10:14:33 +0100,Lat Pulldown,10,33.0,0,0,0,0,false,,1
2026-09-05 10:16:33 +0100,Lat Pulldown,10,33.0,0,0,0,0,false,,1
2026-09-05 10:18:33 +0100,Lat Pulldown,10,33.0,0,0,0,0,false,few in reserve,1
2026-09-05 10:25:00 +0100,Machine Chest Press,10,25.0,0,0,0,0,false,,1
2026-09-05 10:27:00 +0100,Machine Chest Press,6,25.0,0,0,0,0,false,failed 7,1
2026-09-05 10:40:00 +0100,Plank,0,0,45,0,0,0,false,,1
2026-09-08 18:00:00 +0100,Leg Press,10,80.0,0,0,0,0,false,,1
2026-09-08 18:05:00 +0100,Seated Leg Curl,12,30.0,0,0,0,0,false,,1
2026-09-08 18:10:00 +0100,Mystery Kettlebell Swing,15,16.0,0,0,0,0,false,,1
"""


class TestFitbodParse:
    def test_groups_by_day_and_maps_names(self):
        sessions = fb.parse_fitbod_csv(CSV)
        assert [s["session_date"] for s in sessions] == ["2026-09-05", "2026-09-08"]
        s1 = sessions[0]
        assert s1["session_type"] == "upper"
        slugs = [x["exercise_slug"] for x in s1["sets"]]
        assert slugs.count("lat-pulldown") == 3          # warm-up row dropped
        assert slugs.count("chest-press") == 2
        assert [x["set_no"] for x in s1["sets"] if x["exercise_slug"] == "lat-pulldown"] == [1, 2, 3]
        plank = next(x for x in s1["sets"] if x["exercise_slug"] == "plank")
        assert plank["hold_s"] == 45 and plank["reps"] is None
        assert s1["external_id"].startswith("fitbod:2026-09-05:")

    def test_lower_and_unknown_exercise(self):
        s2 = fb.parse_fitbod_csv(CSV)[1]
        assert s2["session_type"] == "lower"
        unknown = next(x for x in s2["sets"] if "kettlebell" in x["exercise_slug"])
        assert unknown["exercise_slug"] == "mystery-kettlebell-swing"
        assert unknown["category"] == "other"    # no hint matches "kettlebell swing"; it still lands in the lower session
        assert unknown["exercise_name"] == "Mystery Kettlebell Swing"

    def test_include_warmups_flag(self):
        s1 = fb.parse_fitbod_csv(CSV, include_warmups=True)[0]
        assert [x["exercise_slug"] for x in s1["sets"]].count("lat-pulldown") == 4

    def test_external_id_is_content_stable(self):
        a = fb.parse_fitbod_csv(CSV)[0]["external_id"]
        b = fb.parse_fitbod_csv(CSV)[0]["external_id"]
        assert a == b

    def test_empty(self):
        assert fb.parse_fitbod_csv("") == []

    def test_infer_mixed_is_full_body(self):
        assert fb.infer_session_type(["push", "legs"]) == "full_body"
        assert fb.infer_session_type(["core"]) == "full_body"
        assert fb.infer_session_type(["pull", "push"]) == "upper"


class TestGarminMatching:
    ACTS = [
        {"activity_id": "1", "date": "2026-09-05", "activity_type": "stair_climbing", "duration_s": 1200, "avg_hr": 150, "calories": 210},
        {"activity_id": "2", "date": "2026-09-05", "activity_type": "walking", "duration_s": 2100, "avg_hr": 105, "calories": 180},
        {"activity_id": "3", "date": "2026-09-05", "activity_type": "strength_training", "duration_s": 2400, "avg_hr": 110},
        {"activity_id": "4", "date": "2026-09-06", "activity_type": "indoor_cycling", "duration_s": 600},
    ]

    def test_match_prefers_exact_modality(self):
        c = {"session_date": "2026-09-05", "modality": "stairmaster", "duration_min": 20}
        assert ga.match_activity(c, self.ACTS, set())["activity_id"] == "1"

    def test_match_skips_used_and_other_days(self):
        c = {"session_date": "2026-09-05", "modality": "stairmaster", "duration_min": 20}
        assert ga.match_activity(c, self.ACTS, {"1"}) is None
        c2 = {"session_date": "2026-09-06", "modality": "bike", "duration_min": None}
        assert ga.match_activity(c2, self.ACTS, set())["activity_id"] == "4"

    def test_walk_and_treadmill_are_compatible(self):
        c = {"session_date": "2026-09-05", "modality": "treadmill", "duration_min": 35}
        assert ga.match_activity(c, self.ACTS, set())["activity_id"] == "2"

    def test_auto_cardio_row(self):
        r = ga.auto_cardio_row(self.ACTS[1], "prog")
        assert r["modality"] == "walk" and r["intensity"] == "easy" and r["duration_min"] == 35
        assert r["source"] == "garmin" and r["garmin_activity_id"] == "2"
        assert ga.auto_cardio_row(self.ACTS[0], None)["intensity"] == "hard"
        assert ga.auto_cardio_row(self.ACTS[2], None) is None          # strength isn't cardio
        assert ga.auto_cardio_row(self.ACTS[3], None) is None          # 10 min < minimum

    def test_modality_map(self):
        assert ga.modality_for("STAIR_CLIMBING") == "stairmaster"
        assert ga.modality_for("yoga") is None
