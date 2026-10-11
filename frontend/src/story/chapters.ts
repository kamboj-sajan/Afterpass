/**
 * The story's five chapters (brief §13.1) as data: how long each lasts and what it does to the
 * map, and when. Chapters 1, 3, 4 and 5 show published data. Chapter 2's embers are an
 * illustration, because the hour a field was lit is not known; the caption says so.
 */

import { useExplorer, type LayerId } from '@/lib/store'
import { istMs } from '@/lib/time'
import type { SeasonData, SmokeRunSummary, Village } from '@/lib/types'

export type ChapterId = 'pass' | 'after' | 'scars' | 'missed' | 'smoke'

/** What the chapters need to know about the published data. */
export interface StoryContext {
  /** The week the story is told in, and its day with the most official detections. */
  week: string
  day: string
  districts: string[]
  /** A camera position that shows all the mapped districts. */
  overview: { longitude: number; latitude: number; zoom: number }
  /** The village with the most uncounted burning that has before and after images. */
  village: Village | null
  /** The smoke run with the most smoke over Delhi. */
  run: SmokeRunSummary | null
  /** Without motion the chapters set a still scene and do not play the clock. */
  reduced: boolean
}

export interface Cue {
  /** Seconds into the chapter. */
  at: number
  run: (context: StoryContext) => void
}

export interface Chapter {
  id: ChapterId
  seconds: number
  cues: Cue[]
}

const DELHI_VIEW = { longitude: 77.1, latitude: 28.63, zoom: 9.2, pitch: 55, bearing: -15 }

function layers(on: LayerId[]): void {
  const all: LayerId[] = ['official', 'burns', 'scars', 'smoke', 'delhi', 'districts']
  useExplorer
    .getState()
    .setLayers(Object.fromEntries(all.map((id) => [id, on.includes(id)])) as Record<LayerId, boolean>)
}

export const CHAPTERS: Chapter[] = [
  {
    // "Every afternoon around 1:30, NASA's satellites scan Punjab."
    id: 'pass',
    seconds: 16,
    cues: [
      {
        at: 0,
        run: (c) => {
          const explorer = useExplorer.getState()
          explorer.openImagery(null)
          explorer.setStoryEmbers(null)
          explorer.setDistricts(c.districts)
          explorer.setWeek(c.week)
          explorer.setScope('week')
          layers(['official', 'districts'])
          explorer.flyTo({ ...c.overview, pitch: 45, bearing: -12 })
          // Still: the day's detections after the pass. Moving: an hour before it, then play.
          explorer.setClock(istMs(c.day, c.reduced ? 15 : 12.5))
          explorer.setSpeed(1)
          if (!c.reduced) explorer.setPlaying(true)
        },
      },
      { at: 9, run: () => useExplorer.getState().setPlaying(false) },
    ],
  },
  {
    // "But most large fires now start after 3 PM." Embers are an illustration.
    id: 'after',
    seconds: 22,
    cues: [
      {
        at: 0,
        run: (c) => {
          const explorer = useExplorer.getState()
          layers(['official', 'districts'])
          explorer.setStoryEmbers(c.day)
          explorer.setClock(istMs(c.day, c.reduced ? 19 : 15))
          explorer.setSpeed(0.25)
          if (!c.reduced) explorer.setPlaying(true)
        },
      },
      { at: 16.5, run: () => useExplorer.getState().setPlaying(false) },
    ],
  },
  {
    // "The scars stay." The top village's before and after images, wiped automatically.
    id: 'scars',
    seconds: 26,
    cues: [
      {
        at: 0,
        run: (c) => {
          const explorer = useExplorer.getState()
          explorer.setPlaying(false)
          explorer.setStoryEmbers(null)
          explorer.setSpeed(1)
          layers(['scars', 'districts'])
          if (c.village === null) return
          explorer.highlightVillage(c.village.id)
          explorer.flyTo({ longitude: c.village.lon, latitude: c.village.lat, zoom: 12.6, pitch: 30, bearing: 0 })
        },
      },
      {
        at: 4,
        run: (c) => {
          if (c.village === null) return
          useExplorer.getState().setImageryWipe(c.reduced ? 50 : 88)
          useExplorer.getState().openImagery(c.village.id)
        },
      },
    ],
  },
  {
    // "Here's what the official count missed." Columns rise and the season's numbers count up.
    id: 'missed',
    seconds: 22,
    cues: [
      {
        at: 0,
        run: (c) => {
          const explorer = useExplorer.getState()
          explorer.setImageryWipe(null)
          explorer.openImagery(null)
          explorer.highlightVillage(null)
          layers(['official', 'burns', 'districts'])
          explorer.flyTo({ ...c.overview, pitch: 52, bearing: -15 })
          explorer.raiseColumns()
        },
      },
      { at: 3, run: () => useExplorer.getState().setScope('season') },
    ],
  },
  {
    // "And here's where the smoke goes." Trails to Delhi, Delhi's columns, the outlook card.
    id: 'smoke',
    seconds: 30,
    cues: [
      {
        at: 0,
        run: (c) => {
          const explorer = useExplorer.getState()
          explorer.setScope('week')
          if (c.run === null) return
          explorer.setSpeed(1)
          explorer.playSmoke(c.run.run_id, c.reduced ? 27 : 6)
          if (c.reduced) explorer.setPlaying(false)
          layers(['smoke', 'delhi', 'districts'])
          explorer.flyTo({ longitude: 76.25, latitude: 29.55, zoom: 7.4, pitch: 45, bearing: -12 })
        },
      },
      { at: 13, run: () => useExplorer.getState().flyTo(DELHI_VIEW) },
      { at: 27, run: () => useExplorer.getState().setPlaying(false) },
    ],
  },
]

/** The cues of a chapter that fall due as its clock moves from `before` to `after` seconds. */
export function dueCues(chapter: Chapter, before: number, after: number): Cue[] {
  return chapter.cues.filter((cue) => (before < 0 ? cue.at <= after : cue.at > before && cue.at <= after))
}

/** The day of a week with the most official detections in the chosen districts. */
function busiestDay(data: SeasonData, dates: string[], districts: string[]): string {
  const counts = new Map<string, number>(dates.map((date) => [date, 0]))
  for (const point of data.firms.items) {
    const date = point.ist.slice(0, 10)
    if (counts.has(date) && districts.includes(point.district)) counts.set(date, (counts.get(date) ?? 0) + 1)
  }
  return [...counts.entries()].reduce((best, entry) => (entry[1] > best[1] ? entry : best))[0]
}

/** Works out what the story will show from the published data. */
export function storyContext(
  data: SeasonData,
  week: string,
  dates: string[],
  runs: SmokeRunSummary[],
  reduced: boolean,
): StoryContext {
  const districts = data.summary.districts.map((d) => d.district)
  const boxes = data.districts.features.map((feature) => {
    const ring =
      feature.geometry.type === 'Polygon' ? feature.geometry.coordinates[0] : feature.geometry.coordinates[0][0]
    const lons = ring.map((point) => point[0])
    const lats = ring.map((point) => point[1])
    return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)]
  })
  const west = Math.min(...boxes.map((b) => b[0]))
  const south = Math.min(...boxes.map((b) => b[1]))
  const east = Math.max(...boxes.map((b) => b[2]))
  const north = Math.max(...boxes.map((b) => b[3]))
  const replay = runs.filter((run) => run.kind === 'replay')
  return {
    week,
    day: busiestDay(data, dates, districts),
    districts,
    overview: { longitude: (west + east) / 2, latitude: (south + north) / 2, zoom: 8.2 },
    village: data.villages.items.find((village) => data.imagery.has(village.id)) ?? null,
    run: replay.reduce<SmokeRunSummary | null>(
      (best, run) => (best === null || run.delhi_mean_peak > best.delhi_mean_peak ? run : best),
      null,
    ),
    reduced,
  }
}
