// ═══════════════════════════════════════════════════════════
// TGTG Viz — shared utilities and data promise
//
// Loaded by the tgtg_init() shortcode after D3 and TopoJSON.
// Provides global functions: tip(), moveTip(), hideTip(), counter()
// Provides global promise: window.tgtgDataPromise
//
// Data files expected at: /tgtg_history.geojson and /cities.json
// Copy those to your Zola project's static/ directory.
// ═══════════════════════════════════════════════════════════

// ── Rerender registry — viz shortcodes push init functions here ──
window.tgtgRerenderFns = [];

// ── Tooltip ──
const TIP = document.getElementById('tooltip');
function tip(html, ev) {
  TIP.innerHTML = html;
  TIP.style.display = 'block';
  moveTip(ev);
}
function moveTip(ev) {
  const x = ev.clientX + 16, y = ev.clientY - 12;
  TIP.style.left = Math.min(x, window.innerWidth - 260) + 'px';
  TIP.style.top  = Math.min(y, window.innerHeight - 120) + 'px';
}
function hideTip() { TIP.style.display = 'none'; }

// ── Animated counter ──
function counter(id, target, dur = 1400, suffix = '') {
  const el = document.getElementById(id);
  if (!el) return;
  const t0 = Date.now();
  const f = () => {
    const p = Math.min((Date.now() - t0) / dur, 1);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(e * target) + suffix;
    if (p < 1) requestAnimationFrame(f);
  };
  requestAnimationFrame(f);
}

// ═══════════════════════════════════════════════════════════
// SHARED DATA PROMISE — resolves with { pts, storeMap, worldData, getCountry, getCity }
// All viz shortcodes await this instead of fetching independently.
// ═══════════════════════════════════════════════════════════
window.tgtgDataPromise = (async () => {
  const [gj, worldData, citiesRaw] = await Promise.all([
    d3.json('/tgtg_history.geojson'),
    d3.json('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json').catch(() => null),
    d3.json('/cities.json').catch(() => null),
  ]);

  const pts = gj.features
    .filter(f => f.geometry.type === 'Point')
    .map(f => ({
      lon:  f.geometry.coordinates[0],
      lat:  f.geometry.coordinates[1],
      name: f.properties.name,
      logo: f.properties.logo || null,
      time: new Date(f.properties.time),
    }))
    .sort((a, b) => a.time - b.time);

  pts.forEach(p => {
    p.year    = p.time.getUTCFullYear();
    p.month   = d3.utcMonth(p.time);
    p.dateStr = d3.utcFormat('%Y-%m-%d')(p.time);
  });

  const storeMap = d3.rollup(pts, v => v.length, d => d.name);

  // ── Country / city detection ──
  const ISO_NAMES = {
    4:'Afghanistan',8:'Albania',12:'Algeria',24:'Angola',32:'Argentina',
    36:'Australia',40:'Austria',56:'Belgium',68:'Bolivia',76:'Brazil',
    100:'Bulgaria',116:'Cambodia',120:'Cameroon',124:'Canada',144:'Sri Lanka',
    152:'Chile',156:'China',170:'Colombia',188:'Costa Rica',191:'Croatia',
    192:'Cuba',196:'Cyprus',203:'Czechia',208:'Denmark',218:'Ecuador',
    818:'Egypt',231:'Ethiopia',246:'Finland',250:'France',276:'Germany',
    288:'Ghana',300:'Greece',320:'Guatemala',332:'Haiti',340:'Honduras',
    348:'Hungary',356:'India',360:'Indonesia',364:'Iran',368:'Iraq',
    372:'Ireland',376:'Israel',380:'Italy',388:'Jamaica',392:'Japan',
    400:'Jordan',398:'Kazakhstan',404:'Kenya',408:'North Korea',410:'South Korea',
    422:'Lebanon',434:'Libya',484:'Mexico',504:'Morocco',508:'Mozambique',
    524:'Nepal',528:'Netherlands',554:'New Zealand',566:'Nigeria',578:'Norway',
    586:'Pakistan',604:'Peru',608:'Philippines',616:'Poland',620:'Portugal',
    642:'Romania',643:'Russia',682:'Saudi Arabia',686:'Senegal',694:'Sierra Leone',
    705:'Slovenia',706:'Somalia',710:'South Africa',724:'Spain',752:'Sweden',
    756:'Switzerland',764:'Thailand',788:'Tunisia',792:'Turkey',800:'Uganda',
    804:'Ukraine',784:'UAE',826:'United Kingdom',840:'United States',
    858:'Uruguay',862:'Venezuela',704:'Vietnam',887:'Yemen',894:'Zambia',
    716:'Zimbabwe',703:'Slovakia',688:'Serbia',499:'Montenegro',
    807:'North Macedonia',70:'Bosnia & Herzegovina',
  };

  const countryFeatures = worldData
    ? topojson.feature(worldData, worldData.objects.countries).features
    : null;

  function getCountry(lon, lat) {
    if (!countryFeatures) return 'Unknown';
    for (const f of countryFeatures) {
      if (d3.geoContains(f, [lon, lat])) {
        return ISO_NAMES[+f.id] || `Region ${f.id}`;
      }
    }
    return 'Unknown';
  }

  const _cityCache = new Map();
  function getCity(lon, lat) {
    const key = `${lon},${lat}`;
    if (_cityCache.has(key)) return _cityCache.get(key);
    if (!citiesRaw) {
      const rLon = Math.round(lon / 0.4) * 0.4;
      const rLat = Math.round(lat / 0.4) * 0.4;
      return `${rLat.toFixed(1)},${rLon.toFixed(1)}`;
    }
    let best = null, bestDist = Infinity;
    for (const [clat, clon, name, iso2] of citiesRaw) {
      const dlat = lat - clat, dlon = lon - clon;
      const d = dlat * dlat + dlon * dlon;
      if (d < bestDist) { bestDist = d; best = `${name}, ${iso2}`; }
    }
    _cityCache.set(key, best);
    return best;
  }

  // ── Hero counters (no-ops if hero shortcode not present) ──
  const yearMin = d3.min(pts, d => d.year);
  const yearMax = d3.max(pts, d => d.year);

  function updateHeroCounters(p, sm) {
    const yMin = d3.min(p, d => d.year);
    const yMax = d3.max(p, d => d.year);
    const heroRescues = document.getElementById('hero-rescues');
    if (heroRescues) heroRescues.textContent = p.length;
    const heroYears = document.getElementById('hero-years');
    if (heroYears) heroYears.textContent = Math.floor(d3.max(pts, d => d.year) - d3.min(pts, d => d.year));
    counter('sn-pickups',   p.length);
    counter('sn-stores',    sm.size);
    counter('sn-years',     yMax - yMin, 800);
    counter('sn-countries', new Set(p.map(d => getCountry(d.lon, d.lat))).size);
    counter('sn-cities',    new Set(p.map(d => getCity(d.lon, d.lat))).size);
  }

  updateHeroCounters(pts, storeMap);

  // ── setData — upload shortcode calls this to replace data and re-render all vizzes ──
  window.tgtgSetData = function(rawPts) {
    const newPts = rawPts.slice().sort((a, b) => a.time - b.time);
    newPts.forEach(p => {
      p.year    = p.time.getUTCFullYear();
      p.month   = d3.utcMonth(p.time);
      p.dateStr = d3.utcFormat('%Y-%m-%d')(p.time);
    });
    const newStoreMap = d3.rollup(newPts, v => v.length, d => d.name);
    updateHeroCounters(newPts, newStoreMap);
    window.tgtgRerenderFns.forEach(fn => fn({ pts: newPts, storeMap: newStoreMap, worldData, getCountry, getCity }));
  };

  return { pts, storeMap, worldData, getCountry, getCity };
})();

// ── Fade-in on scroll (runs after full page is parsed) ──
document.addEventListener('DOMContentLoaded', () => {
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
  }, { threshold: 0.12 });
  document.querySelectorAll('.fadein').forEach(el => io.observe(el));
});
