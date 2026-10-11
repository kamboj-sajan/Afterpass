# AfterPass: method and limits

AfterPass finds fields that burned but have no matching official fire detection, and models
where the smoke from that burning goes. This document explains how, and what the results can
and cannot tell you. Results for a season are in `validation/{season}.json` and in the
published data files; this document describes the method, which does not change between runs.

Each section below is also what the "Ask AfterPass" assistant quotes when asked about the method.

## How burn scars are detected {#detection}

A burned field stays black for days. AfterPass looks for that char in Sentinel-2 images
(20 m pixels, a pass every 2 to 5 days at about 11:00 IST) instead of looking for flames.

For every clear image of a district, each cropland pixel is tested:

- It must look like char now: a low Normalized Burn Ratio (NBR below 0.0), a high
  Mid-Infrared Burn Index (MIRBI above 1.6), and dark in the near infrared (below 0.20).
  Harvested straw and tilled soil are bright there; char is not.
- Its NBR must have dropped by more than 0.10 since the last clear look at that pixel,
  which must be within 20 days. This separates a new burn from land that was always dark.
- It must not have been flagged before. A scar keeps the date of the image that first showed it.

Cloud, cloud shadow near cloud, water and snow are masked out. Only cropland is tested
(ESA WorldCover). Flagged pixels are cleaned up, joined into patches, and patches under
0.5 hectares are dropped. Each remaining patch is one burn scar with an area in hectares.

A scar is dated by a window: it burned after the last clear image that showed the field
unburned and before the image that first showed the scar.

## Why official counts miss fires {#why_official_counts_miss_fires}

Official farm-fire counts come from satellites that detect active flames: VIIRS and MODIS,
published by NASA FIRMS. These satellites pass over Punjab at about 13:30 IST and again after
midnight. A fire is counted only if it is burning during a pass.

Stubble fires are short. A field lit at 16:00 is out long before the night pass, so it never
becomes a detection. The published histogram of detection times shows this: almost every
official detection falls between 12:00 and 16:00 IST.

An iFOREST study using geostationary satellite data, which looks every 15 minutes, found that
most large farm fires in Punjab in 2024 and 2025 started after 3 PM
([coverage in The Tribune](https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report)).
The burn scar is still there the next morning, which is why AfterPass looks for scars.

## How scars are matched with official detections {#matching}

A burn scar is "in official counts" when a FIRMS detection lies close to it in both space and
time:

- within 375 m of the scar for VIIRS, or within 1 km for MODIS (the size of one pixel of each
  sensor), and
- dated from one day before the scar's window opens to one day after the scar was first seen.

A scar with no such detection is "not in official counts". The comparison is made in hectares
of burned field. FIRMS counts fire pixels, not fields, so counts of the two cannot be compared
directly.

"Not in official counts" describes the satellites' timing. It says nothing about any farmer's
intent.

## How the smoke model works {#smoke}

The smoke outlook is a simple transport model. It is not a chemistry model and it never gives
a PM2.5 value.

- Each burn scar releases smoke between 15:00 and 19:00 IST on the days it could have burned.
- The smoke is carried by the wind at 100 m (hourly, on a 0.25° grid, from Open-Meteo),
  spreads sideways as it travels, and fades with a time constant of 36 hours.
- Over Delhi, the model adds up the smoke above each area every hour and divides by the
  depth of the air's mixing layer. A shallow layer at night means the same smoke counts for
  more.
- The result is the Smoke Arrival Index, from 0 to 100. A value of 100 is the 95th percentile
  of the 2025 season. Levels: Low 0 to 24, Moderate 25 to 49, High 50 to 74, Very high 75 to 100.

The index covers only smoke from the districts AfterPass has mapped. Traffic, industry, dust,
fireworks and smoke from other districts are not in it.

## How the results are checked {#validation}

Three checks, each with its own weakness:

- **Calibration against official detections.** Pixels next to confident VIIRS detections
  should be flagged, and clearly unburned cropland should not be. The detections are weak
  labels: a VIIRS pixel is 375 m wide, so many pixels near a detection did not burn. The share
  flagged therefore understates how many real burns are found. Thresholds come from one
  district and one season.
- **Visual check.** A random sample of 100 scars and 100 cropland points is labelled by eye
  from before and after images, in mixed order. The share of sampled scars confirmed as
  burned is the precision. It was done for the 2025 season by one person, so it carries that
  person's judgement, and a scar's outline has its own shape, so the labeller can tell scars
  from random points. Items marked unsure are left out, which narrows the sample. The random
  points show whether burning is being missed: too few of them are burned to give a miss
  rate, only an indication. The figures are in the validation file.
- **Smoke against observed PM2.5.** The daily Delhi-wide index is compared with PM2.5 from
  CPCB and DPCC monitors (via OpenAQ). The two share a driver, the mixing layer, so part of any
  agreement is weather. A correlation shows the two move together; it does not show how much
  PM2.5 the smoke adds.

## Limitations {#limitations}

- Clouds and haze leave gaps in the images.
- Sentinel-2 returns every 2 to 5 days. A field tilled under before the next clear image is
  missed. Burned area is therefore a lower bound.
- The hour a field was lit is unknown. A scar is dated by the image that first showed it.
- Fields under 0.5 hectares are missed.
- Villages are the nearest named place within 3 km of a scar, not administrative boundaries.
- The smoke index is relative, covers only the mapped districts, and is not a health forecast.
- Results exist only for the districts and seasons that have been processed.

## How the results should be used {#ethics}

AfterPass is for directing help: crop-residue machines, awareness work and support to the
villages where burning goes uncounted. It is not for fines.

- Results are shown for villages and districts. There is no farmer-level data.
- "Not in official counts" is the wording. A burn the satellites missed was not concealed by
  anyone.
- The smoke outlook warns Delhi residents; for health decisions people should use official
  AQI (CPCB's SAMEER app).

## Data sources {#data_sources}

- Sentinel-2 L2A imagery: contains modified Copernicus Sentinel data 2025-2026.
- Fire detections: NASA FIRMS, from LANCE, part of NASA's Earth Science Data and Information
  System (ESDIS).
- Cropland mask: © ESA WorldCover project 2021, contains modified Copernicus Sentinel data.
- Winds and mixing height: weather data by Open-Meteo.com (CC BY 4.0).
- Places: © OpenStreetMap contributors, Overture Maps Foundation.
- District boundaries: geoBoundaries (CC BY 4.0).
- PM2.5 observations: CPCB and DPCC monitors, via OpenAQ.
