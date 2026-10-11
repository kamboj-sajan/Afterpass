# What burns after the satellite passes

*Draft for AWS Builder Center.*

Every autumn, Delhi's air gets worse as paddy stubble burns in Punjab and Haryana, and every
day the news reports a number: how many farm fires the satellites counted. That number comes
from NASA's polar-orbiting satellites, which cross Punjab at about 1:30 PM. A fire is counted
only if it is burning at that moment.

An iFOREST study using geostationary data, which looks every 15 minutes, found that most large
farm fires in Punjab in 2024 and 2025 started after 3 PM. Those fires are out long before the
next pass. AfterPass, built for the WeMakeDevs × AWS *Environmental Hacks*, asks a different
question: not "what was burning at 1:30?", but "what has burned?"

## The idea: look for the scar, not the flame

A burned paddy field turns black and stays black for days. Sentinel-2 photographs Punjab
every two to five days at about 11 AM, in bands where char looks nothing like straw or soil.
So AfterPass:

1. **Finds burn scars.** For each clear Sentinel-2 image, a cropland pixel is flagged when it
   looks like char (low Normalized Burn Ratio, high mid-infrared burn index, dark in the near
   infrared) and its burn ratio dropped sharply since the last clear look. Flagged pixels
   become field-sized scars of half a hectare or more.
2. **Matches them with official detections.** A scar is "in official counts" if a FIRMS
   detection lies within one sensor pixel of it (375 m for VIIRS, 1 km for MODIS), at the
   right time. Otherwise it is "not in official counts".
3. **Follows the smoke.** Each scar releases model smoke between 3 and 7 PM on the days it
   could have burned. The smoke rides the 100 m wind from Open-Meteo to Delhi, where a Smoke
   Arrival Index scores each neighbourhood hour by hour for the next 48 hours.
4. **Answers questions in English and Hindi.** An assistant built with Strands Agents answers
   only from the published data and moves the map to show what it is talking about.

## Results: the 2025 season in three districts

For Sangrur, Bathinda and Firozpur, 1 October to 30 November 2025:

- **423,996 hectares burned**, and **303,189 hectares (71.5%) had no matching official
  detection.**
- Of 4,377 official detections, **4,330 (98.9%) were made between noon and 4 PM**, around the
  afternoon pass. Our own data shows the blind spot.
- The village at the top of the "send help here first" list, Chaunda in Sangrur, had 850.6
  hectares of burning not in official counts.
- Over 59 days, the daily Delhi-wide smoke index and PM2.5 from 40 CPCB and DPCC monitors had a
  Pearson correlation of 0.56 (Spearman 0.63).

### Honest limits

- **Burned area is a lower bound.** Clouds leave gaps; a field tilled under before the next
  clear image is missed; so are fields under half a hectare.
- **We don't know when a field was lit**, only between which two images it burned.
- **Calibration against FIRMS is a weak check.** A VIIRS pixel is 375 m wide, so many pixels
  next to a detection never burned, and the measured recall (32%) understates what we find.
  The real test is a visual check of 200 random samples, labelled by one person: 74 of the 85
  scars that could be judged were burned (87%, 95% interval 78% to 93%), and 15 were left out
  as unsure. Of 49 random cropland points that could be judged, 10 looked newly burned and
  none had been flagged on that date, which is too few to give a miss rate.
- **The smoke correlation is partly weather.** A shallow night-time mixing layer raises both
  the index and PM2.5, so the correlation shows the two move together, not how much PM2.5 the
  stubble smoke adds. The index is relative and is never shown as µg/m³.

## The stack

Everything is on AWS, in the Sydney region:

- **AWS Open Data** for the heavy inputs: Sentinel-2 L2A cloud-optimized GeoTIFFs (through
  Element 84's Earth Search), ESA WorldCover for the cropland mask, and Overture Maps for
  village and Delhi locality names (queried with DuckDB straight from S3).
- **Lambda and Step Functions** for the daily pipeline: fetch FIRMS, find scenes, detect burns
  per district in a Map state, match and aggregate, then smoke and imagery in parallel,
  publish, and alert. **EventBridge Scheduler** runs it at 7:12 PM IST, after FIRMS has
  processed the afternoon pass, with a smoke-only refresh at 7:12 AM.
- **S3 and CloudFront** serve the published JSON and imagery to the app.
- **Amazon Bedrock**, through **Strands Agents**, runs the assistant on a Lambda Function URL,
  with a DynamoDB rate limit.
- **SNS** emails Delhi smoke alerts by zone; **Amazon Location Service** draws the basemap with
  India's political view; **Amplify Hosting** serves the React app.

The frontend is React with deck.gl on MapLibre: extruded H3 columns for burned area, FIRMS
detections as cyan points, smoke as animated trails, and a react-globe.gl hero.

## What fought back

- **Region and model access.** The plan was `us-west-2`, next to the Sentinel-2 data, with
  Claude on Bedrock. The account could create resources only in Sydney and had no Claude
  quota. The data still streams from `us-west-2`, and the assistant runs on
  `openai.gpt-oss-120b` through Bedrock's OpenAI-compatible endpoint. Switching to Claude is a
  one-line setting once quota exists.
- **Getting the pipeline's image into AWS.** Pushing the container image to ECR from a home
  connection kept failing, so the build moved into CodeBuild, where it takes about a minute.
  The first run then stopped at once: the Lambda Python base image has no `libexpat`, which
  the raster library loads. The image build now imports every pipeline module, so a missing
  library fails the build and not a run.
- **Grounding an open model.** Every answer is checked mechanically: each number in it must
  appear in that turn's tool results. All 10 scripted questions, five in Hindi, passed.
- **Reading COGs reliably.** Long runs of HTTP range reads occasionally came back truncated.
  Reads are aligned to the files' internal blocks, run in parallel, and retried.
- **IST is UTC+5:30.** Days in India start at half past the UTC hour, which broke an
  assumption that model hours start on UTC hours.
- **Thousands of smoke trails in a browser.** Unix-second timestamps lose precision in the GPU's
  32-bit floats, so trail times are stored relative to each run. Trails are capped at 15,000,
  with a point every two hours, to keep each 48-hour run near 4 MB.
- **Not overstating anything.** The hardest rule was the one about numbers: everything on
  screen and in the assistant's answers comes from a pipeline output file, with its
  `generated_at`.

## Try it

- App: https://main.dx6zgy1knro1d.amplifyapp.com
- Method and limits: `docs/METHOD.md` in the repository.

AfterPass shows villages and districts, never individual farmers. Its purpose is to send
crop-residue machines and awareness work to where uncounted burning concentrates, and to give
Delhi a warning before the smoke arrives.
