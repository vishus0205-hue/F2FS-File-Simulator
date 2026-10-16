/**
 * F2FS Flash Storage Simulator - Interactive Web Application
 * In-browser Flash Device & Filesystem Engine with Chart.js Benchmarks
 */

// --- 1. Flash Simulation Constants & Engine ---
const NUM_SEGMENTS = 8;
const PAGES_PER_SEGMENT = 16;
const TOTAL_PAGES = NUM_SEGMENTS * PAGES_PER_SEGMENT; // 128 pages
const DEFAULT_BLOCKS = 90; // ~70% initial utilization

class WebFlashDevice {
  constructor(numSegments = NUM_SEGMENTS, pagesPerSegment = PAGES_PER_SEGMENT) {
    this.numSegments = numSegments;
    this.pagesPerSegment = pagesPerSegment;
    this.totalPages = numSegments * pagesPerSegment;
    this.reset();
  }

  reset() {
    this.segments = [];
    for (let s = 0; s < this.numSegments; s++) {
      const pages = [];
      const basePpa = s * this.pagesPerSegment;
      for (let p = 0; p < this.pagesPerSegment; p++) {
        pages.push({
          ppa: basePpa + p,
          state: 'FREE', // 'FREE' | 'VALID' | 'INVALID'
          data: null,
          lba: null
        });
      }
      this.segments.push({
        segmentId: s,
        eraseCount: 0,
        pages: pages
      });
    }
  }

  getPage(ppa) {
    const segId = Math.floor(ppa / this.pagesPerSegment);
    const offset = ppa % this.pagesPerSegment;
    return this.segments[segId].pages[offset];
  }

  writePage(ppa, data, lba) {
    const page = this.getPage(ppa);
    if (page.state !== 'FREE') {
      throw new Error(`Write violation: PPA ${ppa} is not FREE.`);
    }
    page.state = 'VALID';
    page.data = data;
    page.lba = lba;
  }

  invalidatePage(ppa) {
    const page = this.getPage(ppa);
    if (page.state === 'FREE') {
      throw new Error(`Cannot invalidate a FREE page at PPA ${ppa}.`);
    }
    page.state = 'INVALID';
  }

  eraseSegment(segId) {
    const seg = this.segments[segId];
    seg.eraseCount++;
    for (const page of seg.pages) {
      page.state = 'FREE';
      page.data = null;
      page.lba = null;
    }
  }

  getValidCount(segId) {
    return this.segments[segId].pages.filter(p => p.state === 'VALID').length;
  }

  getInvalidCount(segId) {
    return this.segments[segId].pages.filter(p => p.state === 'INVALID').length;
  }

  getFreeCount(segId) {
    return this.segments[segId].pages.filter(p => p.state === 'FREE').length;
  }

  getTotalErases() {
    return this.segments.reduce((acc, s) => acc + s.eraseCount, 0);
  }

  getTotalInvalid() {
    return this.segments.reduce((acc, s) => acc + this.getInvalidCount(s.segmentId), 0);
  }
}

// In-Place Update Simulation
class WebInPlaceFS {
  constructor(flash) {
    this.flash = flash;
    this.name = 'In-Place Baseline';
    this.resetMetrics();
  }

  resetMetrics() {
    this.logicalWrites = 0;
    this.physicalWrites = 0;
    this.segmentErases = 0;
    this.gcRuns = 0;
    this.gcCopied = 0;
    this.isMeasuring = false;
  }

  write(lba, data) {
    if (this.isMeasuring) this.logicalWrites++;

    const ppa = lba;
    const segId = Math.floor(ppa / this.flash.pagesPerSegment);
    const targetPage = this.flash.getPage(ppa);

    if (targetPage.state === 'FREE') {
      this.flash.writePage(ppa, data, lba);
      if (this.isMeasuring) this.physicalWrites++;
      logTerminal(`[WRITE] PPA ${ppa} (LBA ${lba}) cold write`, 'log-write');
    } else {
      // In-Place rewrite: read segment, update buffer, erase, rewrite valid pages
      const seg = this.flash.segments[segId];
      const buffer = [];
      for (const p of seg.pages) {
        if (p.state === 'VALID') {
          buffer.push({ ppa: p.ppa, data: p.data, lba: p.lba });
        }
      }
      // Update target
      const idx = buffer.findIndex(b => b.ppa === ppa);
      if (idx >= 0) buffer[idx].data = data;
      else buffer.push({ ppa, data, lba });

      this.flash.eraseSegment(segId);
      if (this.isMeasuring) this.segmentErases++;
      triggerSegmentEraseAnimation(segId);
      logTerminal(`[ERASE] Segment ${segId} erased for in-place update`, 'log-erase');

      for (const item of buffer) {
        this.flash.writePage(item.ppa, item.data, item.lba);
        if (this.isMeasuring) this.physicalWrites++;
      }
      logTerminal(`[REWRITE] Segment ${segId} rewrote ${buffer.length} valid pages`, 'log-write');
    }
  }
}

// Log-Structured (F2FS) Simulation
class WebLogStructuredFS {
  constructor(flash) {
    this.flash = flash;
    this.name = 'Log-Structured (F2FS)';
    this.l2p = new Map();
    this.p2l = new Map();
    this.activeSegId = null;
    this.activeOffset = 0;
    this.isGcInProgress = false;
    this.resetMetrics();
  }

  resetMetrics() {
    this.logicalWrites = 0;
    this.physicalWrites = 0;
    this.segmentErases = 0;
    this.gcRuns = 0;
    this.gcCopied = 0;
    this.isMeasuring = false;
  }

  getFreeSegmentIds() {
    const list = [];
    for (const seg of this.flash.segments) {
      if (this.flash.getFreeCount(seg.segmentId) === this.flash.pagesPerSegment) {
        list.push(seg.segmentId);
      }
    }
    return list;
  }

  selectVictimSegment() {
    let bestId = null;
    let minValid = this.flash.pagesPerSegment + 1;
    let maxInvalid = -1;

    for (const seg of this.flash.segments) {
      if (seg.segmentId === this.activeSegId) continue;
      if (this.flash.getFreeCount(seg.segmentId) === this.flash.pagesPerSegment) continue;
      if (this.flash.getInvalidCount(seg.segmentId) === 0) continue;

      const valid = this.flash.getValidCount(seg.segmentId);
      const invalid = this.flash.getInvalidCount(seg.segmentId);

      if (valid < minValid || (valid === minValid && invalid > maxInvalid)) {
        minValid = valid;
        maxInvalid = invalid;
        bestId = seg.segmentId;
      }
    }
    return bestId;
  }

  collect() {
    const victimId = this.selectVictimSegment();
    if (victimId === null) return 0;

    logTerminal(`[GC] Victim chosen: Segment ${victimId} (Valid: ${this.flash.getValidCount(victimId)}, Invalid: ${this.flash.getInvalidCount(victimId)})`, 'log-gc');
    const seg = this.flash.segments[victimId];
    const pagesToMigrate = seg.pages.filter(p => p.state === 'VALID').map(p => p.ppa);

    let pagesCopied = 0;
    for (const oldPpa of pagesToMigrate) {
      const page = this.flash.getPage(oldPpa);
      const lba = page.lba;
      if (this.l2p.get(lba) !== oldPpa) continue;

      const newPpa = this.allocatePage();
      this.flash.writePage(newPpa, page.data, lba);
      this.l2p.set(lba, newPpa);
      this.p2l.set(newPpa, lba);
      this.p2l.delete(oldPpa);
      pagesCopied++;

      if (this.isMeasuring) {
        this.physicalWrites++;
        this.gcCopied++;
      }
    }

    this.flash.eraseSegment(victimId);
    triggerSegmentEraseAnimation(victimId);
    logTerminal(`[ERASE] GC cleaned and erased Segment ${victimId} (Copied ${pagesCopied} pages)`, 'log-erase');

    if (this.isMeasuring) {
      this.segmentErases++;
      this.gcRuns++;
    }

    return pagesCopied;
  }

  ensureActiveSegment() {
    if (this.activeSegId !== null && this.activeOffset < this.flash.pagesPerSegment) {
      return;
    }

    this.activeSegId = null;
    let freeSegs = this.getFreeSegmentIds();

    if (freeSegs.length <= 1 && !this.isGcInProgress) {
      if (freeSegs.length > 0) {
        this.activeSegId = freeSegs.shift();
        this.activeOffset = 0;
      }
      if (this.flash.getTotalInvalid() > 0) {
        this.isGcInProgress = true;
        try {
          this.collect();
        } finally {
          this.isGcInProgress = false;
        }
      }
    }

    if (this.activeSegId === null) {
      freeSegs = this.getFreeSegmentIds();
      if (freeSegs.length === 0) {
        if (!this.isGcInProgress && this.flash.getTotalInvalid() > 0) {
          this.isGcInProgress = true;
          try {
            this.collect();
          } finally {
            this.isGcInProgress = false;
          }
          freeSegs = this.getFreeSegmentIds();
        }
      }
      if (freeSegs.length === 0) {
        throw new Error("Flash storage completely full!");
      }
      this.activeSegId = freeSegs.shift();
      this.activeOffset = 0;
    }
  }

  allocatePage() {
    this.ensureActiveSegment();
    const ppa = this.activeSegId * this.flash.pagesPerSegment + this.activeOffset;
    this.activeOffset++;
    return ppa;
  }

  write(lba, data) {
    if (this.isMeasuring) this.logicalWrites++;

    const oldPpa = this.l2p.get(lba);
    if (oldPpa !== undefined) {
      this.flash.invalidatePage(oldPpa);
      logTerminal(`[INVALIDATE] PPA ${oldPpa} (LBA ${lba}) marked INVALID`, 'log-invalid');
    }

    const newPpa = this.allocatePage();
    this.flash.writePage(newPpa, data, lba);
    this.l2p.set(lba, newPpa);
    this.p2l.set(newPpa, lba);

    if (this.isMeasuring) this.physicalWrites++;
    logTerminal(`[APPEND] PPA ${newPpa} written (LBA ${lba})`, 'log-write');
    highlightPageWrite(newPpa);
  }
}

// --- 2. State & UI Binding ---
let flashDevice = new WebFlashDevice();
let logFS = new WebLogStructuredFS(flashDevice);
let inPlaceFS = new WebInPlaceFS(flashDevice);
let currentStrategy = 'log_structured'; // 'log_structured' | 'in_place'
let activeFS = logFS;

function runSimulationInit(numBlocks = DEFAULT_BLOCKS) {
  flashDevice.reset();
  logFS = new WebLogStructuredFS(flashDevice);
  inPlaceFS = new WebInPlaceFS(flashDevice);
  activeFS = currentStrategy === 'log_structured' ? logFS : inPlaceFS;

  // Cold populate up to numBlocks
  activeFS.isMeasuring = false;
  for (let lba = 0; lba < numBlocks; lba++) {
    activeFS.write(lba, `init_${lba}`);
  }
  activeFS.isMeasuring = true;

  logTerminal(`System initialized with ${numBlocks} active logical blocks. Ready for workload updates.`, 'log-gc');
  renderGrid();
  updateMetricsDisplay();
}

function initSimulation(numBlocks = DEFAULT_BLOCKS) {
  runSimulationInit(numBlocks);
}

function switchStrategy(strat) {
  currentStrategy = strat;
  document.querySelectorAll('.pill-switch-btn, .strategy-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.strategy === strat);
  });
  runSimulationInit(DEFAULT_BLOCKS);
}

// UI Grid Render
function renderGrid() {
  const container = document.getElementById('flashSegmentsGrid');
  if (!container) return;
  container.innerHTML = '';

  for (let s = 0; s < flashDevice.numSegments; s++) {
    const seg = flashDevice.segments[s];
    const isActive = (currentStrategy === 'log_structured' && logFS.activeSegId === s);

    const segBox = document.createElement('div');
    segBox.className = `clean-segment-card ${isActive ? 'active-head' : ''}`;
    segBox.id = `seg-${s}`;

    segBox.innerHTML = `
      <div class="segment-top">
        <span class="seg-name">
          Segment ${s}
          ${isActive ? '<span class="head-pill">Active Log</span>' : ''}
        </span>
        <span class="seg-erase-metric">Erases: ${seg.eraseCount}</span>
      </div>
      <div class="page-chip-grid" id="pages-seg-${s}"></div>
    `;

    const matrix = segBox.querySelector(`#pages-seg-${s}`);
    for (const page of seg.pages) {
      const pageEl = document.createElement('div');
      let stateClass = '';
      if (page.state === 'VALID') stateClass = 'valid';
      else if (page.state === 'INVALID') stateClass = 'invalid';

      pageEl.className = `page-chip ${stateClass}`;
      pageEl.id = `page-${page.ppa}`;
      pageEl.title = `PPA: ${page.ppa} | State: ${page.state} | LBA: ${page.lba !== null ? page.lba : 'None'}`;
      pageEl.textContent = page.lba !== null ? page.lba : '';
      matrix.appendChild(pageEl);
    }

    container.appendChild(segBox);
  }
}

function highlightPageWrite(ppa) {
  setTimeout(() => {
    const el = document.getElementById(`page-${ppa}`);
    if (el) {
      el.classList.add('write-pulse');
      setTimeout(() => el.classList.remove('write-pulse'), 300);
    }
  }, 10);
}

function triggerSegmentEraseAnimation(segId) {
  const segEl = document.getElementById(`seg-${segId}`);
  if (segEl) {
    segEl.classList.add('erasing');
    setTimeout(() => segEl.classList.remove('erasing'), 500);
  }
}

function logTerminal(msg, typeClass = '') {
  // Silent or console logging to remove unnecessary UI clutter for the user
  console.log(`[FlashSim] ${msg}`);
}

function updateMetricsDisplay() {
  const waf = activeFS.logicalWrites > 0 ? (activeFS.physicalWrites / activeFS.logicalWrites).toFixed(2) : '1.00';

  const mLog = document.getElementById('mLogicalWrites');
  const mPhy = document.getElementById('mPhysicalWrites');
  const mWaf = document.getElementById('mWaf');
  const mEra = document.getElementById('mErases');
  const mGcR = document.getElementById('mGcRuns');
  const mGcC = document.getElementById('mGcCopied');
  const heroWaf = document.getElementById('heroWaf');

  if (mLog) mLog.textContent = activeFS.logicalWrites;
  if (mPhy) mPhy.textContent = activeFS.physicalWrites;
  if (mWaf) mWaf.textContent = `${waf}x`;
  if (mEra) mEra.textContent = flashDevice.getTotalErases();
  if (mGcR) mGcR.textContent = activeFS.gcRuns;
  if (mGcC) mGcC.textContent = activeFS.gcCopied;

  if (heroWaf && currentStrategy === 'log_structured') {
    heroWaf.innerHTML = `${waf}<small style="font-size: 1rem;">x</small>`;
  }
}

// User Actions
function performSingleWrite(skewed = false) {
  try {
    let lba;
    if (!skewed) {
      lba = Math.floor(Math.random() * DEFAULT_BLOCKS);
    } else {
      // 80% to 20% hot blocks (hot blocks: 0 to 18)
      const hotCount = Math.floor(DEFAULT_BLOCKS * 0.2);
      if (Math.random() < 0.8) {
        lba = Math.floor(Math.random() * hotCount);
      } else {
        lba = hotCount + Math.floor(Math.random() * (DEFAULT_BLOCKS - hotCount));
      }
    }

    activeFS.write(lba, `update_${Date.now()}`);
    renderGrid();
    updateMetricsDisplay();
  } catch (e) {
    console.error("Simulation write error:", e);
  }
}

function performBatchWrites(count = 20) {
  try {
    for (let i = 0; i < count; i++) {
      let lba = Math.floor(Math.random() * DEFAULT_BLOCKS);
      activeFS.write(lba, `update_${Date.now()}_${i}`);
    }
    renderGrid();
    updateMetricsDisplay();
  } catch (e) {
    console.error("Batch write error:", e);
  }
}

function performManualGC() {
  try {
    if (currentStrategy !== 'log_structured') {
      alert("Garbage collection applies to the Log-Structured strategy.");
      return;
    }
    const copied = logFS.collect();
    renderGrid();
    updateMetricsDisplay();
    if (copied === 0) {
      logTerminal("No eligible segments with invalid pages found for GC.", "log-gc");
    }
  } catch (e) {
    console.error("GC error:", e);
  }
}

// Global window exposure for inline onclick handlers
window.performSingleWrite = performSingleWrite;
window.performBatchWrites = performBatchWrites;
window.performManualGC = performManualGC;
window.initSimulation = runSimulationInit;
window.switchStrategy = switchStrategy;

// --- 3. Interactive Benchmark Charts (Chart.js with SVG fallback) ---
let chartExp1, chartExp2;

function renderSvgChartsFallback() {
  const box1 = document.getElementById('chartStrategy')?.parentElement;
  if (box1 && !chartExp1) {
    box1.innerHTML = `
      <div style="width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; padding: 1rem 2rem; position: relative;">
        <div style="display: flex; justify-content: space-around; align-items: flex-end; height: 180px; border-bottom: 2px solid #E4E7EC; padding-bottom: 8px;">
          <div style="display: flex; flex-direction: column; align-items: center; width: 80px;">
            <span style="font-size: 0.85rem; font-weight: 700; color: #F04438; margin-bottom: 4px;">63.34x</span>
            <div style="width: 50px; height: 155px; background: #F04438; border-radius: 6px 6px 0 0;"></div>
            <span style="font-size: 0.8rem; font-weight: 600; color: #101828; margin-top: 8px; text-align: center;">In-Place</span>
          </div>
          <div style="display: flex; flex-direction: column; align-items: center; width: 80px;">
            <span style="font-size: 0.85rem; font-weight: 700; color: #12B76A; margin-bottom: 4px;">1.74x</span>
            <div style="width: 50px; height: 16px; background: #12B76A; border-radius: 6px 6px 0 0;"></div>
            <span style="font-size: 0.8rem; font-weight: 600; color: #101828; margin-top: 8px; text-align: center;">F2FS</span>
          </div>
        </div>
      </div>
    `;
  }

  const box2 = document.getElementById('chartUtilization')?.parentElement;
  if (box2 && !chartExp2) {
    box2.innerHTML = `
      <div style="width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 1rem;">
        <svg viewBox="0 0 400 200" style="width: 100%; height: 100%; max-height: 200px;">
          <defs>
            <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#FF5A1F" stop-opacity="0.25"/>
              <stop offset="100%" stop-color="#FF5A1F" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
          <line x1="40" y1="160" x2="380" y2="160" stroke="#E4E7EC" stroke-width="1.5" />
          <line x1="40" y1="110" x2="380" y2="110" stroke="#F2F4F7" stroke-width="1" stroke-dasharray="4" />
          <line x1="40" y1="60" x2="380" y2="60" stroke="#F2F4F7" stroke-width="1" stroke-dasharray="4" />
          <path d="M 60 152 Q 160 148 240 136 T 360 30 L 360 160 L 60 160 Z" fill="url(#curveGrad)"/>
          <path d="M 60 152 Q 160 148 240 136 T 360 30" fill="none" stroke="#FF5A1F" stroke-width="3"/>
          <circle cx="60" cy="152" r="5" fill="#FF5A1F" stroke="#FFF" stroke-width="2"/>
          <text x="60" y="142" font-size="11" font-weight="700" fill="#344054" text-anchor="middle">1.06x</text>
          <text x="60" y="180" font-size="11" font-weight="600" fill="#667085" text-anchor="middle">40%</text>
          <circle cx="160" cy="148" r="5" fill="#FF5A1F" stroke="#FFF" stroke-width="2"/>
          <text x="160" y="138" font-size="11" font-weight="700" fill="#344054" text-anchor="middle">1.36x</text>
          <text x="160" y="180" font-size="11" font-weight="600" fill="#667085" text-anchor="middle">60%</text>
          <circle cx="260" cy="136" r="5" fill="#FF5A1F" stroke="#FFF" stroke-width="2"/>
          <text x="260" y="126" font-size="11" font-weight="700" fill="#344054" text-anchor="middle">2.66x</text>
          <text x="260" y="180" font-size="11" font-weight="600" fill="#667085" text-anchor="middle">80%</text>
          <circle cx="360" cy="30" r="5" fill="#FF5A1F" stroke="#FFF" stroke-width="2"/>
          <text x="360" y="20" font-size="11" font-weight="700" fill="#FF5A1F" text-anchor="middle">18.74x</text>
          <text x="360" y="180" font-size="11" font-weight="600" fill="#667085" text-anchor="middle">95%</text>
        </svg>
      </div>
    `;
  }
}

function initCharts() {
  if (typeof Chart === 'undefined') {
    console.warn("Chart.js library is not available, using high-res SVG fallback.");
    renderSvgChartsFallback();
    return;
  }

  // Chart 1: Strategy Comparison
  const ctx1 = document.getElementById('chartStrategy');
  if (ctx1) {
    try {
      chartExp1 = new Chart(ctx1, {
        type: 'bar',
        data: {
          labels: ['In-Place Baseline', 'Log-Structured (F2FS)'],
          datasets: [{
            label: 'Write Amplification Factor (WAF)',
            data: [63.34, 1.74],
            backgroundColor: ['#F04438', '#12B76A'],
            borderRadius: 8,
            barPercentage: 0.45
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `WAF: ${ctx.raw}x (Lower is better)`
              }
            }
          },
          scales: {
            y: {
              grid: { color: 'rgba(0, 0, 0, 0.05)' },
              ticks: { color: '#667085', font: { family: 'Plus Jakarta Sans', weight: '600' } },
              title: { display: true, text: 'WAF (Physical / Logical)', color: '#475467' }
            },
            x: {
              grid: { display: false },
              ticks: { color: '#101828', font: { weight: 'bold' } }
            }
          }
        }
      });
    } catch (e) {
      console.warn("Chart 1 error:", e);
      renderSvgChartsFallback();
    }
  }

  // Chart 2: Utilization Curve
  const ctx2 = document.getElementById('chartUtilization');
  if (ctx2) {
    try {
      chartExp2 = new Chart(ctx2, {
        type: 'line',
        data: {
          labels: ['40%', '60%', '80%', '95%'],
          datasets: [{
            label: 'Log-Structured WAF',
            data: [1.06, 1.36, 2.66, 18.74],
            borderColor: '#FF5A1F',
            backgroundColor: 'rgba(255, 90, 31, 0.08)',
            fill: true,
            tension: 0.35,
            pointBackgroundColor: '#FF5A1F',
            pointBorderColor: '#FFFFFF',
            pointBorderWidth: 2,
            pointRadius: 6,
            pointHoverRadius: 8
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `WAF at ${ctx.label} capacity: ${ctx.raw}x`
              }
            }
          },
          scales: {
            y: {
              grid: { color: 'rgba(0, 0, 0, 0.05)' },
              ticks: { color: '#667085', font: { family: 'Plus Jakarta Sans', weight: '600' } },
              title: { display: true, text: 'Write Amplification (WAF)', color: '#475467' }
            },
            x: {
              grid: { display: false },
              ticks: { color: '#101828', font: { weight: 'bold' } },
              title: { display: true, text: 'Storage Utilization', color: '#475467' }
            }
          }
        }
      });
    } catch (e) {
      console.warn("Chart 2 error:", e);
      renderSvgChartsFallback();
    }
  }
}

// --- DOM Ready Hook ---
document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize simulation engine & render grid FIRST
  try {
    runSimulationInit(DEFAULT_BLOCKS);
  } catch (e) {
    console.error("Simulation initialization error:", e);
  }

  // 2. Attach button events
  document.getElementById('btnWriteRandom')?.addEventListener('click', () => performSingleWrite(false));
  document.getElementById('btnWriteHot')?.addEventListener('click', () => performSingleWrite(true));
  document.getElementById('btnBatchWrites')?.addEventListener('click', () => performBatchWrites(20));
  document.getElementById('btnRunGc')?.addEventListener('click', performManualGC);
  document.getElementById('btnResetSim')?.addEventListener('click', () => runSimulationInit(DEFAULT_BLOCKS));

  // Strategy buttons
  document.querySelectorAll('.pill-switch-btn, .strategy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => switchStrategy(e.target.dataset.strategy));
  });

  // 3. Initialize charts with safety guard and SVG fallback
  try {
    initCharts();
  } catch (e) {
    console.warn("Charts initialization error:", e);
    renderSvgChartsFallback();
  }
});
