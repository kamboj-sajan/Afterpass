/**
 * Scripted walkthrough of the Explorer and the Delhi screen in a headless browser.
 *
 * Records a video and screenshots into ../reports/, fails on any console error, and checks
 * that the season KPIs on screen equal the totals in summary.json (formatted en-IN). Software
 * WebGL here is far slower than a GPU: check the smoke frame rate in a browser with /map?fps=1.
 *
 * Needs both local servers: `make serve-data` and `make web`.
 * Usage: node scripts/walkthrough.mjs [appUrl] [dataUrl]
 */
import { mkdirSync, renameSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const appUrl = process.argv[2] ?? 'http://127.0.0.1:5173'
const dataUrl = process.argv[3] ?? 'http://127.0.0.1:8787'
const reports = resolve(dirname(fileURLToPath(import.meta.url)), '../../reports')
const videoDir = resolve(reports, '.walkthrough-video')
const size = { width: 1600, height: 900 }

const integer = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const percent = new Intl.NumberFormat('en-IN', { style: 'percent', maximumFractionDigits: 0 })

async function expectedSeasonKpis() {
  const latest = await (await fetch(`${dataUrl}/latest.json`)).json()
  const summary = await (await fetch(`${dataUrl}/seasons/${latest.season}/summary.json`)).json()
  const burned = summary.districts.reduce((total, d) => total + d.burned_ha, 0)
  const unrecorded = summary.districts.reduce((total, d) => total + d.unrecorded_ha, 0)
  const official = summary.districts.reduce((total, d) => total + d.firms.firms_count, 0)
  return [integer.format(official), integer.format(burned), percent.format(unrecorded / burned)]
}

const problems = []
mkdirSync(reports, { recursive: true })
rmSync(videoDir, { recursive: true, force: true })

const browser = await chromium.launch({
  // Software WebGL, so the map renders without a GPU.
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
})
const context = await browser.newContext({
  viewport: size,
  deviceScaleFactor: 1,
  recordVideo: { dir: videoDir, size },
})
const page = await context.newPage()
page.on('console', (message) => {
  if (message.type() === 'error') problems.push(`console: ${message.text()}`)
})
page.on('pageerror', (error) => problems.push(`page error: ${error.message}`))

const shot = (name) => page.screenshot({ path: resolve(reports, `explorer_${name}.png`) })
const pause = (ms) => page.waitForTimeout(ms)

await page.goto(`${appUrl}/map`)
await page.getByTestId('kpi-value').first().waitFor({ timeout: 60_000 })
await page.waitForFunction(() => document.querySelector('canvas.maplibregl-canvas') !== null)
await pause(9000) // basemap tiles, then the columns rise
await shot('1_overview')

// Season totals must match summary.json exactly.
await page.getByRole('radio', { name: 'Season', exact: true }).click()
await pause(1500)
const shown = await page.getByTestId('kpi-value').allInnerTexts()
const expected = await expectedSeasonKpis()
if (JSON.stringify(shown) !== JSON.stringify(expected)) {
  problems.push(`KPIs ${JSON.stringify(shown)} do not match summary.json ${JSON.stringify(expected)}`)
}
console.log('Season KPIs on screen:', shown.join(' | '), '| from summary.json:', expected.join(' | '))
await page.getByRole('radio', { name: 'This week', exact: true }).click()

// Change the week: the columns rise again.
await page.getByRole('slider', { name: 'Week', exact: true }).focus()
await page.keyboard.press('ArrowLeft')
await pause(2200)
await page.keyboard.press('ArrowRight')
await pause(2200)

// Top village: fly in to the scars and open its imagery.
await page.locator('ol button').first().click()
await pause(7000)
await shot('2_village_scars')

// Search with the command palette.
await page.keyboard.press('Escape')
await page.keyboard.press('Control+k')
await page.getByPlaceholder('Search districts, villages and Delhi localities…').fill('sangrur')
await pause(900)
await shot('3_search')
await page.keyboard.press('Enter')
await pause(4500)

// Play the week at 4x until a satellite pass sweeps the map.
await page.getByRole('radio', { name: '4×' }).click()
await page.getByRole('button', { name: 'Play the week' }).click()
await page.getByTestId('clock').filter({ hasText: '13:30' }).waitFor({ timeout: 60_000 })
await pause(700)
await shot('4_timeline_scan')
await pause(7000)

// Smoke: trails on the clock, Delhi columns, and a locality's 48-hour outlook found in Hindi.
const outlook = page.getByTestId('delhi-outlook')
if ((await outlook.count()) === 0) {
  problems.push('The Delhi smoke outlook is not shown. Has `make smoke` run?')
} else {
  await page.getByRole('radio', { name: '16×' }).click()
  await pause(6000)
  await shot('5_smoke')
  await page.getByRole('button', { name: 'Pause' }).click()
  await page.getByRole('textbox', { name: /Delhi locality/ }).fill('द्वार')
  const match = page.getByRole('listbox').getByRole('button').first()
  if ((await match.count()) > 0) await match.click()
  await pause(4000)
  const place = await page.getByTestId('smoke-locality').innerText()
  const peak = await page.getByTestId('smoke-peak').innerText()
  console.log(`Delhi outlook: ${place} | ${peak}`)
  await shot('6_delhi_outlook')
}

// Delhi screen: opens on the season's peak run; the city's figures are checked against its file.
await page.goto(`${appUrl}/delhi`)
const delhi = page.getByTestId('delhi-screen')
await delhi.waitFor({ timeout: 60_000 }).catch(() => undefined)
if ((await delhi.count()) === 0) {
  problems.push('The Delhi screen did not open. Has `make smoke` run?')
} else {
  await pause(3000)
  const index = await (await fetch(`${dataUrl}/smoke/index.json`)).json()
  const runs = index.runs.filter((run) => run.kind === 'replay').sort((a, b) => a.start - b.start)
  const peak = runs.reduce((best, run) => (run.delhi_mean_peak > best.delhi_mean_peak ? run : best))
  const sai = await (await fetch(`${dataUrl}/smoke/${peak.run_id}/delhi_sai_h3r7.json`)).json()
  const firstHour = Object.values(sai.cells).map((series) => series[0])
  const mean = Math.round(firstHour.reduce((total, value) => total + value, 0) / firstHour.length)
  const high = `${firstHour.filter((value) => value >= 50).length} of ${firstHour.length}`
  const shownMean = (await page.getByTestId('delhi-mean').innerText()).replace(/\s+/g, ' ')
  const shownHigh = await page.getByTestId('delhi-high').innerText()
  console.log(`Delhi screen (${peak.run_id}): ${shownMean} | ${shownHigh} | from the file: ${mean} | ${high}`)
  if (!shownMean.endsWith(`· ${mean}`)) problems.push(`Delhi average on screen (${shownMean}) is not ${mean}.`)
  if (shownHigh !== high) problems.push(`Areas at High or above on screen (${shownHigh}) is not ${high}.`)
  await page.getByRole('radio', { name: '4×' }).click()
  await page.getByRole('button', { name: 'Play the 48 hours' }).click()
  await pause(5000)
  await page.getByRole('button', { name: 'Pause' }).click()
  await shot('7_delhi_screen')
}

await context.close()
const video = await page.video().path()
renameSync(video, resolve(reports, 'explorer_walkthrough.webm'))
rmSync(videoDir, { recursive: true, force: true })
await browser.close()

if (problems.length > 0) {
  console.error(`\n${problems.length} problem(s):\n- ${[...new Set(problems)].join('\n- ')}`)
  process.exit(1)
}
console.log('Walkthrough passed. Video and screenshots are in reports/.')
