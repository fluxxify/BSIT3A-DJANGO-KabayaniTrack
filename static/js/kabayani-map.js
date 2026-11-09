/*
 * Shared Leaflet helpers for KabayaniTrack maps.
 *
 * - Esri World Street Map for zoom levels up to 16 (its reliable native
 *   coverage). Deeper zooms use OpenStreetMap instead, so the map never shows
 *   Esri's "Map data not yet available" placeholder tile.
 * - Theme-aware colours: the active Tabler primary colour is read from CSS
 *   variables, and markers can subscribe to live theme changes.
 */
(function () {
  if (window.KabayaniMap) { return; }

  var ESRI_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}';
  var ESRI_ATTRIBUTION = 'Tiles &copy; <a href="https://www.esri.com/">Esri</a>';
  var OSM_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  var OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

  // Esri World Street Map has no street detail beyond this level in many
  // rural areas (including Kabankalan), where it returns a placeholder tile.
  var ESRI_MAX_NATIVE_ZOOM = 16;

  function cssColor(name, fallback) {
    var value = '';
    try {
      value = window.getComputedStyle(document.documentElement)
        .getPropertyValue(name);
    } catch (err) {
      value = '';
    }
    value = String(value || '').trim();
    return value || fallback;
  }

  function primaryColor() {
    return cssColor('--tblr-primary', '#6366f1');
  }

  function dangerColor() {
    return cssColor('--tblr-danger', '#d63939');
  }

  function successColor() {
    return cssColor('--tblr-success', '#2fb344');
  }

  /*
   * Call `callback` whenever the Tabler theme attributes change. Returns the
   * observer so callers can keep a reference if needed.
   */
  function onThemeChange(callback) {
    if (typeof callback !== 'function' || !window.MutationObserver) {
      return null;
    }
    var observer = new MutationObserver(function () { callback(); });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-bs-theme', 'data-bs-theme-primary']
    });
    return observer;
  }

  /*
   * Add a hybrid Esri/OSM base layer to a map.
   *
   * Esri is used up to ESRI_MAX_NATIVE_ZOOM. From the next level upwards an
   * OSM layer takes over. If Esri ever fails, both are replaced by OSM.
   */
  function addBaseLayer(map, options) {
    options = options || {};
    var maxZoom = options.maxZoom || 19;
    var esri = L.tileLayer(ESRI_URL, {
      maxZoom: ESRI_MAX_NATIVE_ZOOM,
      attribution: ESRI_ATTRIBUTION
    });
    var osm = L.tileLayer(OSM_URL, {
      minZoom: ESRI_MAX_NATIVE_ZOOM + 1,
      maxZoom: maxZoom,
      attribution: OSM_ATTRIBUTION
    });
    var switched = false;

    esri.on('tileerror', function () {
      if (switched) { return; }
      switched = true;
      if (map.hasLayer(esri)) { map.removeLayer(esri); }
      if (map.hasLayer(osm)) { map.removeLayer(osm); }
      L.tileLayer(OSM_URL, {
        maxZoom: maxZoom,
        attribution: OSM_ATTRIBUTION
      }).addTo(map);
    });

    esri.addTo(map);
    osm.addTo(map);
    return { esri: esri, osm: osm };
  }

  window.KabayaniMap = {
    ESRI_MAX_NATIVE_ZOOM: ESRI_MAX_NATIVE_ZOOM,
    addBaseLayer: addBaseLayer,
    cssColor: cssColor,
    primaryColor: primaryColor,
    dangerColor: dangerColor,
    successColor: successColor,
    onThemeChange: onThemeChange
  };
})();
