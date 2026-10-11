/** Loaders for the published data files. Responses are cached for the page's lifetime. */

import { useEffect, useState } from 'react'
import { DATA_BASE_URL } from './config'
import type {
  DistrictCollection,
  FirmsPoint,
  H3Row,
  ImageryIndexItem,
  ImageryMeta,
  Items,
  Latest,
  DelhiSai,
  ScarCollection,
  SeasonData,
  SmokeIndex,
  SmokeLocality,
  SmokeRun,
  SmokeRunSummary,
  Summary,
  TripsFile,
  Validation,
  Village,
} from './types'

export class DataError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'DataError'
    this.status = status
  }
}

export function dataUrl(path: string): string {
  return `${DATA_BASE_URL}/${path}`
}

const cache = new Map<string, Promise<unknown>>()

function getJson<T>(path: string): Promise<T> {
  let pending = cache.get(path)
  if (!pending) {
    pending = fetch(dataUrl(path)).then(
      (response) => {
        if (!response.ok) throw new DataError(`${path}: HTTP ${response.status}`, response.status)
        return response.json() as Promise<unknown>
      },
      () => {
        throw new DataError(`${path}: network error`, null)
      },
    )
    // A failed request should be retried on the next call, not remembered.
    pending.catch(() => cache.delete(path))
    cache.set(path, pending)
  }
  return pending as Promise<T>
}

export function districtSlug(name: string): string {
  return name.toLowerCase().replaceAll(' ', '_')
}

async function loadSeason(season: number): Promise<SeasonData> {
  const base = `seasons/${season}`
  const [latest, summary, districts, cells, firms, villages, imagery] = await Promise.all([
    getJson<Latest>('latest.json'),
    getJson<Summary>(`${base}/summary.json`),
    getJson<DistrictCollection>(`${base}/districts.geojson`),
    getJson<Items<H3Row>>(`${base}/burns_h3_r8.json`),
    getJson<Items<FirmsPoint>>(`${base}/firms_points.json`),
    getJson<Items<Village>>(`${base}/villages.json`),
    // Written by `afterpass imagery`; until that has run, no village has crops.
    getJson<Items<ImageryIndexItem>>('imagery/index.json').catch((error: unknown) => {
      if (error instanceof DataError && error.status === 404) return { items: [] }
      throw error
    }),
  ])
  return {
    latest,
    summary,
    districts,
    cells,
    firms,
    villages,
    // Crops are prepared per season; a village's crops from another season are not this season's.
    imagery: new Set(
      imagery.items.filter((item) => item.post_date.startsWith(String(season))).map((item) => item.village_id),
    ),
  }
}

export type Loadable<T> = { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error'; error: DataError }

function useLoad<T>(key: string | null, load: () => Promise<T>): Loadable<T> | null {
  const [result, setResult] = useState<{
    key: string
    value: Loadable<T>
  } | null>(null)
  useEffect(() => {
    if (key === null) return
    let cancelled = false
    load().then(
      (data) => {
        if (!cancelled) setResult({ key, value: { status: 'ready', data } })
      },
      (error: unknown) => {
        const wrapped = error instanceof DataError ? error : new DataError(String(error), null)
        if (!cancelled) setResult({ key, value: { status: 'error', error: wrapped } })
      },
    )
    return () => {
      cancelled = true
    }
    // `load` is rebuilt every render; `key` identifies what it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  if (key === null) return null
  return result !== null && result.key === key ? result.value : { status: 'loading' }
}

export function useSeasonData(season: number): Loadable<SeasonData> {
  return (
    useLoad(`season:${season}`, () => loadSeason(season)) ?? {
      status: 'loading',
    }
  )
}

/** Scar polygons for one week in each given district. Districts with no file that week are skipped. */
export function useScars(season: number, districts: string[], week: string | null, enabled: boolean): ScarCollection[] {
  const key = enabled && week !== null ? `scars:${season}:${week}:${districts.join(',')}` : null
  const result = useLoad(key, async () => {
    const files = await Promise.all(
      districts.map((name) =>
        getJson<ScarCollection>(`seasons/${season}/scars/${districtSlug(name)}/${week}.geojson`).catch(
          (error: unknown) => {
            if (error instanceof DataError && error.status === 404) return null
            throw error
          },
        ),
      ),
    )
    return files.filter((file): file is ScarCollection => file !== null)
  })
  return result?.status === 'ready' ? result.data : []
}

/**
 * Imagery metadata for a village, or `missing` when no crops were prepared for it.
 * `prepared` comes from the imagery index, so villages without crops are never requested.
 */
export function useImagery(villageId: string | null, prepared: boolean): Loadable<ImageryMeta | 'missing'> | null {
  return useLoad(
    villageId === null ? null : `imagery:${villageId}:${prepared}`,
    (): Promise<ImageryMeta | 'missing'> =>
      prepared ? getJson<ImageryMeta>(`imagery/${villageId}/meta.json`) : Promise.resolve('missing' as const),
  )
}

/** `smoke/index.json`, or null until `afterpass smoke` has run. */
export function useSmokeIndex(): SmokeIndex | null {
  const result = useLoad('smoke:index', () =>
    getJson<SmokeIndex>('smoke/index.json').catch((error: unknown) => {
      if (error instanceof DataError && error.status === 404) return null
      throw error
    }),
  )
  return result?.status === 'ready' ? result.data : null
}

function loadSmokeRun(summary: SmokeRunSummary): Promise<SmokeRun> {
  const base = `smoke/${summary.run_id}`
  return Promise.all([
    getJson<TripsFile>(`${base}/trips.json`),
    getJson<DelhiSai>(`${base}/delhi_sai_h3r7.json`),
    getJson<Items<SmokeLocality>>(`${base}/localities.json`),
  ]).then(([trips, sai, localities]) => ({ summary, trips, sai, localities: localities.items }))
}

/** One run's trails, Delhi index and localities. The previous run stays on screen while the next loads. */
export function useSmokeRun(summary: SmokeRunSummary | null): SmokeRun | null {
  const [run, setRun] = useState<SmokeRun | null>(null)
  const runId = summary?.run_id ?? null
  useEffect(() => {
    if (summary === null) return
    let cancelled = false
    loadSmokeRun(summary).then(
      (loaded) => {
        if (!cancelled) setRun(loaded)
      },
      // A run that fails to load leaves the previous one on screen; the index lists only published runs.
      () => undefined,
    )
    return () => {
      cancelled = true
    }
    // `summary` is a new object whenever the index reloads; the run id identifies it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])
  return summary === null ? null : run
}

/** Start downloading a run before the clock reaches it, so playback does not stall. */
export function prefetchSmokeRun(summary: SmokeRunSummary): void {
  void loadSmokeRun(summary).catch(() => undefined)
}

/** What the Method page shows: the season summary and the validation report. */
export function useMethodData(season: number): Loadable<{ summary: Summary; validation: Validation }> {
  return (
    useLoad(`method:${season}`, async () => {
      const [summary, validation] = await Promise.all([
        getJson<Summary>(`seasons/${season}/summary.json`),
        getJson<Validation>(`validation/${season}.json`),
      ])
      return { summary, validation }
    }) ?? { status: 'loading' }
  )
}
