# Demo script (2:55)

A screen recording at 1920 × 1080 in ten shots. Record each shot as its own clip, retake any
that go wrong, and join them. Every number said aloud is on screen in that shot and comes from
the published files, so check it against the app on recording day.

App: https://main.dx6zgy1knro1d.amplifyapp.com

## Before recording

- Use a fresh browser window at 1920 × 1080, full screen, zoom 100%, bookmarks bar hidden,
  notifications off. Keep the app in English.
- `/map?demo=1` always opens the Explorer in the same state: the 2025 replay, its biggest
  week, every district. Use it for every Explorer shot.
- Ask the assistant the Hindi question once before recording, so the recorded answer is not
  slow. Cut the wait for the answer out of the clip.
- The whole story runs 116 seconds, which is too long for this video. Shots 3 and 4 use only
  its third and fourth chapters.
- Read at a steady pace. The lines total about 385 words for 175 seconds.

## Shots

### 1. Hook · 0:00–0:12 · the hero

- **Open** `/` and let the satellite cross Punjab once. Do not click.
- **Say:** "Every afternoon at about 1:30, NASA's satellites count Punjab's farm fires. But
  most large fires are now lit after 3 PM. The satellites never see them."

### 2. The evidence · 0:12–0:32 · the Explorer

- **Open** `/map?demo=1`. In the Ground truth panel (right), click **Season**. Move the
  pointer slowly along the chart "When official detections happen".
- **Say:** "This is our own data for the 2025 season in three Punjab districts. 4,377
  official detections, and almost all of them fall between noon and 4 PM, right around the
  pass. So we stopped looking for flames, and looked for what fire leaves behind: the burn
  scar."

### 3. The scar · 0:32–0:54 · story, chapter 3

- **Do:** on `/map?demo=1`, click **Story**, click **Next chapter** twice, then press **P**
  for presentation mode. The map flies to Kotha Guru and the before and after images wipe
  across. Start the clip when the images open.
- **Say:** "Sentinel-2 photographs these fields every few days. A burned field turns black
  and stays black, whatever hour it was lit. This is Kotha Guru in Bathinda, before and
  after. Every outline is a field that burned between these two images."

### 4. What was missed · 0:54–1:16 · story, chapter 4

- **Do:** nothing; the story moves on by itself. Columns rise and the numbers count up to the
  season. Press **Esc** when the fifth chapter starts.
- **Say:** "Across Sangrur, Bathinda and Firozpur we found 4 lakh 24 thousand hectares burned
  in 2025. 72% of it has no matching official detection. That is a lower bound: clouds and
  small fields are missed."

### 5. Is it right? · 1:16–1:23 · the Method page

- **Open** `/method` and scroll to "How the detection has been checked", with the "Visual
  check" paragraph in view.
- **Say:** "We checked a random sample of scars by eye. 87% were confirmed as burned."

### 6. Ask in Hindi · 1:23–1:45 · the assistant

- **Open** `/map?demo=1`. Click **Ask AfterPass**, then the Hindi suggestion that begins
  "संगरूर के किन गाँवों…". The answer appears and the map flies to Chaunda with its before and
  after images.
- **Say:** "Officials can ask in Hindi: which villages in Sangrur had the most burning
  missing from official counts? The assistant answers only from our published data, and it
  moves the map. Chaunda: 850.6 hectares not in official counts. That is where crop-residue
  machines should go first."

### 7. The smoke · 1:45–2:03 · the Delhi screen

- **Open** `/delhi?run=2025-11-06`. Press **play** at the bottom, with the speed on 4×. Let
  the smoke reach Delhi and the columns rise.
- **Say:** "Then we follow the smoke. It rides the 100-metre wind to Delhi, and every
  neighbourhood gets an hourly index for the next 48 hours. It is a relative index, not
  PM2.5, and residents can sign up for an email when their area reaches High."

### 8. How it is built · 2:03–2:33 · the README on GitHub

- **Open** https://github.com/kamboj-sajan/Afterpass#architecture with the diagram in view.
  Halfway through the line, scroll down to the "How AWS is used" table.
- **Say:** "The pipeline is Python; the app is React and deck.gl. It all runs on AWS.
  Sentinel-2, WorldCover and Overture come from AWS Open Data. A Step Functions pipeline of
  Lambda container functions runs every evening on EventBridge Scheduler: detect, match,
  forecast, publish. S3 and CloudFront serve the data, Amplify hosts the app, and Amazon
  Location draws the map. The assistant is Strands Agents on Bedrock, and SNS sends the smoke
  alerts."

### 9. What I learned · 2:33–2:45 · stay on the table

- **Say:** "What I learned: the account only allowed the Sydney region and had no Claude
  quota. So I moved everything, ran an open model, and made the app check every number the
  model says against the data."

### 10. Close · 2:45–2:55 · the Explorer

- **Open** `/map?demo=1`, click **Season**, with the list "Send help here first" in view.
- **Say:** "AfterPass is not for fines. It shows villages, never farmers. It shows where the
  uncounted burning is, so help can get there first."

## Uploading

Export at 1080p. The video must be three minutes or less. Upload it to YouTube as Public or
Unlisted, and give the submission form the video's own link, not the channel's.

## If something is off on the day

- **The assistant is slow or down:** drop shot 6 and let shot 7 run longer. The transcript in
  `backend/agent/tests/transcript.md` shows the same question answered.
- **The globe does not render** (WebGL off): the hero falls back to a still image. Say the
  same line.
- **The numbers differ from this script:** say what the app shows. The script's numbers come
  from the 2025 replay published on 11 October 2026.
- **You are over three minutes:** drop shot 9. The form lists learning as optional.
