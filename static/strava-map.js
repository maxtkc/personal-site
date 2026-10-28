// Shared MapLibre helpers for the Strava route maps
(function () {
  const STYLES = {
    dark:  'https://tiles.openfreemap.org/styles/dark',
    light: 'https://tiles.openfreemap.org/styles/positron',
  };
  const BG = { dark: '#0a111c', light: '#dfe6ee' };

  // Sport types grouped into categories, each with a dark and light theme color
  const CATEGORIES = [
    { id: 'ride',  label: 'Ride',      dark: '#fb923c', light: '#c2410c',
      types: ['Ride', 'GravelRide', 'MountainBikeRide', 'EBikeRide', 'EMountainBikeRide', 'Velomobile', 'VirtualRide', 'Handcycle'] },
    { id: 'run',   label: 'Run',       dark: '#f472b6', light: '#be185d',
      types: ['Run', 'TrailRun', 'VirtualRun'] },
    { id: 'foot',  label: 'Hike/Walk', dark: '#4ade80', light: '#15803d',
      types: ['Hike', 'Walk'] },
    { id: 'snow',  label: 'Snow/Ice',  dark: '#a78bfa', light: '#6d28d9',
      types: ['AlpineSki', 'NordicSki', 'BackcountrySki', 'Snowboard', 'Snowshoe', 'IceSkate'] },
    { id: 'water', label: 'Water',     dark: '#38bdf8', light: '#0369a1',
      types: ['Sail', 'Windsurf', 'Kitesurf', 'Swim', 'Rowing', 'Canoeing', 'Kayaking', 'StandUpPaddling', 'Surfing'] },
    { id: 'other', label: 'Other',     dark: '#fbbf24', light: '#a16207', types: [] },
  ];
  const TYPE_TO_CAT = {};
  CATEGORIES.forEach(c => c.types.forEach(t => { TYPE_TO_CAT[t] = c.id; }));

  function categoryOf(sportType) {
    return TYPE_TO_CAT[sportType] || 'other';
  }

  function currentTheme() {
    const attr = document.documentElement.getAttribute('data-theme');
    if (attr === 'dark' || attr === 'light') return attr;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  // Line color expression keyed on the feature's `cat` property
  function colorExpr(theme) {
    const expr = ['match', ['get', 'cat']];
    CATEGORIES.forEach(c => expr.push(c.id, c[theme]));
    expr.push(CATEGORIES[CATEGORIES.length - 1][theme]);
    return expr;
  }

  // Halo drawn under route lines to separate them from the basemap
  function casingColor(theme) {
    return theme === 'dark' ? '#0b0f14' : '#ffffff';
  }

  function applyGlobe(map, theme) {
    map.setProjection({ type: 'globe' });
    map.setSky({
      'sky-color':     BG[theme],
      'horizon-color': theme === 'dark' ? '#1e293b' : '#ffffff',
      'fog-color':     BG[theme],
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0],
    });
  }

  // Create a themed globe map; onStyle(theme) runs after every style (re)load
  function createMap(container, opts, onStyle) {
    let theme = currentTheme();
    container.style.background = BG[theme];
    const map = new maplibregl.Map(Object.assign({
      container,
      style: STYLES[theme],
      attributionControl: { compact: true },
    }, opts));
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.scrollZoom.setWheelZoomRate(1 / 300);
    map.on('style.load', () => {
      applyGlobe(map, theme);
      onStyle(theme);
    });

    function onThemeChange() {
      const t = currentTheme();
      if (t === theme) return;
      theme = t;
      container.style.background = BG[theme];
      map.setStyle(STYLES[theme], { diff: false });
    }
    new MutationObserver(onThemeChange)
      .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', onThemeChange);
    return map;
  }

  function boundsOf(fc) {
    const b = new maplibregl.LngLatBounds();
    (fc.features || []).forEach(f => {
      const g = f.geometry;
      if (!g) return;
      const lines = g.type === 'MultiLineString' ? g.coordinates : [g.coordinates];
      lines.forEach(line => line.forEach(c => b.extend(c)));
    });
    return b;
  }

  window.StravaMap = { CATEGORIES, categoryOf, colorExpr, casingColor, createMap, boundsOf };
})();
