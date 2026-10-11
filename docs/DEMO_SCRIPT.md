# Demo script (3:00)

A three-minute screen recording at 1920 × 1080. Every number said aloud is on screen at that
moment and comes from the published files, so check it against the app on recording day.

## Before recording

- Open the app in a fresh window at 1920 × 1080, zoom 100%, with notifications off.
- The Explorer link with `?demo=1` always opens on the same state: the season's biggest week,
  every district, the clock at noon on its first day. Use it for every Explorer shot.
- In the story, press **P** for presentation mode: controls hidden, captions enlarged.
- Open the Delhi screen on a replayed day with smoke, not on the live forecast, which is Low
  while nothing is burning: `/delhi?run=<run id>`. `smoke/index.json` lists the runs with
  their `delhi_mean_peak`. The day the assistant used in its transcript is `2025-11-06`.
- Ask the assistant the Hindi question once before recording, so the first answer is not slow.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00–0:15 | Hero (`/`). The satellite crosses Punjab at 13:30 IST; cyan dots blink; ember rings bloom after it has passed. | "Every afternoon at about 1:30, NASA's satellites count Punjab's farm fires. Most large fires are now lit after 3 PM. The satellites never see them." |
| 0:15–0:45 | Explorer (`/map?demo=1`). Point at the Ground Truth panel's detection-time histogram. | "This is our own data: of 4,377 official detections in the 2025 season, 4,330 fall between noon and 4 PM, right around the pass. iFOREST found most large fires start after 3. So we stopped looking for flames and started looking for what fire leaves behind: the burn scar." |
| 0:45–1:45 | **Play the story** with P on. Chapter 3 wipes a village before/after; chapter 4 raises the columns and counts up the KPIs. | "Sentinel-2 sees the black scar the next clear morning, whatever time the field burned. Across Sangrur, Bathinda and Firozpur we found 423,996 hectares burned in 2025. 71% of it, 303,189 hectares, has no matching official detection. The village at the top of the list, Chaunda in Sangrur, has 850.6 hectares not in official counts. That's where residue-management machines should go first." |
| 1:45–2:20 | Open **Ask AfterPass**. Tap the Hindi chip "संगरूर के किन गाँवों में…". The map flies to Sangrur and opens a village. Then the Delhi screen (`/delhi?run=…`), press play. | "Officials can ask in Hindi. The assistant answers only from our data, and moves the map to show it. And the smoke: we carry it on the 100-metre wind to Delhi, neighbourhood by neighbourhood, 48 hours ahead. It's a relative index, not PM2.5; for health, we point people to official AQI." |
| 2:20–2:45 | The architecture diagram from the README. | "It all runs on AWS: Sentinel-2, WorldCover and Overture from AWS Open Data; Lambda and Step Functions for the daily pipeline; S3 and CloudFront for the data; Bedrock through Strands Agents for the assistant; SNS for Delhi smoke alerts; Amazon Location for the maps, with India's political view." |
| 2:45–3:00 | Back to the Explorer, the village list "Send help here first". | "AfterPass isn't for fines. It shows villages, never farmers. It shows where the uncounted burning is, so help can get there first." |

## If something is off on the day

- **The assistant is slow or down:** skip the live question and show the Delhi screen. The
  transcript in `backend/agent/tests/transcript.md` shows the same questions answered.
- **The globe does not render** (WebGL off): the hero falls back to a still image. Say the
  same lines.
- **The numbers differ from this script:** say what the app shows. The script's numbers come
  from the 2025 replay published on 11 October 2026, as quoted in the assistant's transcript.
