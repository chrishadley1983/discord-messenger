---
name: kids-pets
description: Check the kids' virtual pets (Tamagotchi) on the dashboard — Max's and Emmie's
trigger:
  - "how are the pets"
  - "how's max's pet"
  - "how's emmie's pet"
  - "are the pets ok"
  - "do the pets need feeding"
  - "pet status"
scheduled: false
conversational: true
---

# Kids' Pets (Tamagotchi)

## Purpose

Max and Emmie each have a virtual pet on the kitchen dashboard. This lets Peter
answer "how's my pet doing?" and flag if one needs attention. Base
`http://172.19.64.1:8100`.

## Endpoint

`GET /ihd/pets` → `{pets: {max, emmie}, sleeping, timestamp}`. Each pet (when it
exists) has `name`, `species`, `stage` (baby→…), and stats `hunger`,
`happiness`, `cleanliness` (0–100), plus `poopCount`.

## Interpretation

- Stats are 0–100; **higher is better**. Below ~30 on any stat = needs care
  (feed if hunger low, play/pet if happiness low, clean if cleanliness low or poops > 0).
- `sleeping: true` (roughly 8pm–7am) — pets can't be interacted with; say they're asleep.
- A pet may be `null` if that child hasn't created one yet — say so, don't invent stats.

## Response style

Kid-friendly and warm (Max/Emmie may be the ones asking): "Max's dragon Sparky is
happy (85) but a bit hungry (25) — give him a feed!" / "Both pets are asleep until 7am 😴".
Keep it short and encouraging.
