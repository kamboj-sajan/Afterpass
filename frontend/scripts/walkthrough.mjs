/**
 * Scripted walkthrough of the whole app in a headless browser: hero, Explorer, Delhi screen,
 * Ask AfterPass, the story, the Method page and the phone layout.
 *
 * Records a video and screenshots into ../reports/, fails on any console error, and checks
 * that the season KPIs on screen equal the totals in summary.json (formatted en-IN). Software
 * WebGL here is far slower than a GPU: check the smoke frame rate in a browser with /map?fps=1.
 *
 * Needs both local servers: `make serve-data` and `make web`.
 * The Ask AfterPass step also needs `make agent`; without it that step is skipped and says so.
 * Usage: node scripts/walkthrough.mjs [appUrl] [dataUrl] [agentUrl]
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

// Hero: the globe, then the dive into the map.
await page.goto(`${appUrl}/`)
await page.getByTestId('hero').waitFor({ timeout: 60_000 })
await pause(12_000) // the globe loads, settles over North India and runs one pass
await shot('0_hero')
await page.getByRole('button', { name: 'Explore the map' }).click()
await page.waitForURL('**/map', { timeout: 30_000 })
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

// Ask AfterPass: one question through the real agent, if it is running (`make agent`).
const agentUrl = process.argv[4] ?? 'http://127.0.0.1:8788'
const agentUp = await fetch(`${agentUrl}/ask`, { method: 'OPTIONS' }).then(
  () => true,
  () => false,
)
if (!agentUp) {
  console.log('Ask AfterPass: SKIPPED, the agent is not running (start it with `make agent`).')
} else {
  await page.goto(`${appUrl}/map`)
  await page.getByTestId('ask-button').click({ timeout: 60_000 })
  await page.getByRole('button', { name: /^संगरूर के किन गाँवों/ }).click()
  await page.getByTestId('chat-answer').waitFor({ timeout: 90_000 })
  await pause(4000)
  const season = (await (await fetch(`${dataUrl}/latest.json`)).json()).season
  const villages = (await (await fetch(`${dataUrl}/seasons/${season}/villages.json`)).json()).items
  const top = villages
    .filter((village) => village.district === 'Sangrur')
    .reduce((best, village) => (village.unrecorded_ha > best.unrecorded_ha ? village : best))
  const answer = await page.getByTestId('chat-answer').innerText()
  console.log(`Ask AfterPass: top Sangrur village in the file is ${top.name}, ${top.unrecorded_ha} ha`)
  if (!answer.includes(top.name)) problems.push(`The agent's answer does not name ${top.name}.`)
  if (!answer.includes(String(top.unrecorded_ha))) {
    problems.push(`The agent's answer does not give ${top.unrecorded_ha} ha for ${top.name}.`)
  }
  await shot('8_ask_afterpass')
}

// The story, in demo mode: five chapters, in order, then the Explorer as it was.
await page.goto(`${appUrl}/map?demo=1&story=1`)
await page.getByTestId('story').waitFor({ timeout: 60_000 })
const captions = []
const storyStarted = Date.now()
let presented = false
// About two minutes on a GPU. Software WebGL draws a frame or two a second, and the story's
// clock never jumps more than a quarter second per frame, so here it takes several times longer.
while ((await page.getByTestId('story').count()) > 0 && Date.now() - storyStarted < 720_000) {
  const caption = await page
    .getByTestId('story-caption')
    .innerText({ timeout: 2000 })
    .catch(() => null)
  if (caption !== null && captions.at(-1) !== caption) {
    captions.push(caption)
    await pause(5000)
    await shot(`9_story_${captions.length}`)
    if (captions.length === 2 && !presented) {
      // Presentation mode: controls hidden, caption enlarged.
      presented = true
      await page.keyboard.press('p')
      await pause(1200)
      await shot('9_story_presentation')
      await page.keyboard.press('p')
    }
  }
  await pause(500)
}
console.log(`Story: ${captions.length} chapters in ${Math.round((Date.now() - storyStarted) / 1000)} s`)
for (const caption of captions) console.log(`  - ${caption}`)
if (captions.length !== 5) problems.push(`The story showed ${captions.length} chapters, not 5.`)
if ((await page.getByTestId('story').count()) > 0) problems.push('The story did not end by itself.')

// Method page: its numbers against the published files.
await page.goto(`${appUrl}/method`)
await page.getByTestId('method-pm25').waitFor({ timeout: 60_000 })
await pause(1500)
{
  const season = (await (await fetch(`${dataUrl}/latest.json`)).json()).season
  const summary = await (await fetch(`${dataUrl}/seasons/${season}/summary.json`)).json()
  const validation = await (await fetch(`${dataUrl}/validation/${season}.json`)).json()
  const hours = summary.firms.by_ist_hour
  const total = hours.reduce((sum, count) => sum + count, 0)
  const midday = hours.slice(12, 16).reduce((sum, count) => sum + count, 0)
  const text = await page.getByTestId('method-screen').innerText()
  const expectedText = [
    integer.format(total),
    percent.format(midday / total),
    integer.format(validation.samples.confident_viirs_detections),
    percent.format(validation.metrics.recall_on_firms_positives),
    validation.pm25.pearson.r.toFixed(2),
    validation.pm25.spearman.rho.toFixed(2),
    `${validation.pm25.stations} CPCB`,
  ]
  const missing = expectedText.filter((value) => !text.includes(value))
  console.log(
    `Method page: ${expectedText.length - missing.length} of ${expectedText.length} published figures found on screen`,
  )
  if (missing.length > 0) problems.push(`Method page does not show: ${missing.join(', ')}`)
  await shot('10_method')
}

await context.close()
const video = await page.video().path()
renameSync(video, resolve(reports, 'full_walkthrough.webm'))

// Phone size: the bottom-sheet layout, with nothing wider than the screen.
{
  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  })
  const small = await phone.newPage()
  small.on('pageerror', (error) => problems.push(`phone page error: ${error.message}`))
  for (const [path, name] of [
    ['/map', '11_phone_map'],
    ['/delhi', '12_phone_delhi'],
  ]) {
    await small.goto(`${appUrl}${path}`)
    await small.getByTestId('phone-sheet').waitFor({ timeout: 60_000 })
    await small.waitForTimeout(6000)
    const overflow = await small.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    if (overflow > 0) problems.push(`Phone ${path} is ${overflow}px wider than the screen.`)
    await small.screenshot({ path: resolve(reports, `explorer_${name}.png`) })
  }
  console.log('Phone layout: bottom sheet shown on /map and /delhi')
  await phone.close()
}
rmSync(videoDir, { recursive: true, force: true })
await browser.close()

if (problems.length > 0) {
  console.error(`\n${problems.length} problem(s):\n- ${[...new Set(problems)].join('\n- ')}`)
  process.exit(1)
}
console.log('Walkthrough passed. Video (full_walkthrough.webm) and screenshots are in reports/.')
