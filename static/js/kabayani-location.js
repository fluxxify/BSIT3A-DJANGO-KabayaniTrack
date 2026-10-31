/*
 * Shared location helper for the OFW portal.
 *
 * Browsers on laptops often fail to get a GPS fix indoors ("Timeout expired").
 * This helper tries a strict GPS fix first, then a relaxed network fix, and
 * finally falls back to an approximate location based on the public IP so the
 * emergency pages still show useful safe places.
 */
(function (global) {
  'use strict';

  var GPS_ATTEMPTS = [
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
  ];

  var FAST_ATTEMPTS = [
    { enableHighAccuracy: false, timeout: 9000, maximumAge: 120000 }
  ];

  function toNumber(value) {
    var number = parseFloat(value);
    return isFinite(number) ? number : null;
  }

  function ipProviders() {
    return [
      {
        url: 'https://ipwho.is/',
        parse: function (data) {
          if (!data || data.success === false) return null;
          return {
            lat: toNumber(data.latitude),
            lng: toNumber(data.longitude),
            city: data.city || '',
            region: data.region || '',
            country: data.country || ''
          };
        }
      },
      {
        url: 'https://ipapi.co/json/',
        parse: function (data) {
          if (!data || data.error) return null;
          return {
            lat: toNumber(data.latitude),
            lng: toNumber(data.longitude),
            city: data.city || '',
            region: data.region || '',
            country: data.country_name || ''
          };
        }
      }
    ];
  }

  function ipLocate() {
    var providers = ipProviders();
    var index = 0;

    return new Promise(function (resolve, reject) {
      function next() {
        if (index >= providers.length) {
          reject(new Error('IP location failed'));
          return;
        }
        var provider = providers[index++];
        fetch(provider.url, {
          headers: { Accept: 'application/json' },
          cache: 'no-store'
        })
          .then(function (response) { return response.json(); })
          .then(function (data) {
            var place = provider.parse(data);
            if (place && place.lat !== null && place.lng !== null) {
              place.source = 'ip';
              place.accuracy = 3000;
              resolve(place);
            } else {
              next();
            }
          })
          .catch(next);
      }
      next();
    });
  }

  function browserPosition(options) {
    return new Promise(function (resolve, reject) {
      if (!navigator.geolocation) {
        reject({ code: 0, message: 'This browser does not support location.' });
        return;
      }
      navigator.geolocation.getCurrentPosition(
        function (position) {
          resolve({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            accuracy: position.coords.accuracy || 0,
            source: 'gps'
          });
        },
        function (error) {
          reject({ code: error.code, message: error.message });
        },
        options
      );
    });
  }

  /**
   * Resolve the current position.
   *
   * @param {{fast?: boolean}} [options] fast skips the strict GPS attempt.
   * @returns {Promise<{lat:number,lng:number,accuracy:number,source:string}>}
   */
  function getPosition(options) {
    options = options || {};

    if (global.isSecureContext === false) {
      return Promise.reject({
        code: -1,
        message: 'Location needs HTTPS or localhost. Open the live site or http://127.0.0.1:8000.'
      });
    }

    var attempts = options.fast ? FAST_ATTEMPTS : GPS_ATTEMPTS;
    var lastError = null;

    function tryAttempt(index) {
      if (index >= attempts.length) {
        return ipLocate().catch(function () {
          throw lastError || { code: 3, message: 'Unable to get your location.' };
        });
      }
      return browserPosition(attempts[index]).catch(function (error) {
        lastError = error;
        // Permission denied (1) and insecure context (-1) will not improve
        // with another attempt or an IP lookup.
        if (error && (error.code === 1 || error.code === -1)) throw error;
        return tryAttempt(index + 1);
      });
    }

    return tryAttempt(0);
  }

  function isInAppBrowser() {
    var ua = navigator.userAgent || '';
    return /FBAN|FBAV|FB_IAB|FBIOS|Instagram|Line\/|Twitter|Snapchat|MicroMessenger|; wv\)/i.test(ua);
  }

  function externalBrowserUrl() {
    var url = window.location.href;
    if (/Android/i.test(navigator.userAgent || '') && /^https?:/i.test(url)) {
      var withoutScheme = url.replace(/^https?:\/\//, '');
      return 'intent://' + withoutScheme +
        '#Intent;scheme=https;package=com.android.chrome;' +
        'S.browser_fallback_url=' + encodeURIComponent(url) + ';end';
    }
    return url;
  }

  function legacyCopy(text) {
    try {
      var field = document.createElement('textarea');
      field.value = text;
      field.setAttribute('readonly', 'readonly');
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.appendChild(field);
      field.select();
      var copied = document.execCommand('copy');
      document.body.removeChild(field);
      return copied;
    } catch (error) {
      return false;
    }
  }

  function copyCurrentLink() {
    var url = window.location.href;
    if (navigator.clipboard && window.isSecureContext !== false) {
      return navigator.clipboard.writeText(url)
        .then(function () { return true; })
        .catch(function () { return legacyCopy(url); });
    }
    return Promise.resolve(legacyCopy(url));
  }

  /**
   * Build an "you are in an in-app browser" help box, or null when not needed.
   * In-app browsers (Messenger, Facebook, Instagram) block geolocation and
   * there is no web API to override that, so guide the user to a real browser.
   */
  function inAppHelpBox() {
    if (!isInAppBrowser()) return null;

    var android = /Android/i.test(navigator.userAgent || '');
    var box = document.createElement('div');
    box.className = 'kabayani-inapp-help';
    box.setAttribute('role', 'note');

    var head = document.createElement('div');
    head.className = 'kbi-head';
    head.innerHTML =
      '<i class="fas fa-triangle-exclamation kbi-icon" aria-hidden="true"></i>' +
      '<div class="kbi-copy">' +
      '<div class="kbi-title">Open this page in Chrome or Safari</div>' +
      '<div class="kbi-text">Messenger and Facebook block location access. ' +
      'Use a real browser to share your live location.</div>' +
      '</div>';
    box.appendChild(head);

    var actions = document.createElement('div');
    actions.className = 'kbi-actions';

    if (android) {
      var open = document.createElement('a');
      open.className = 'btn btn-sm btn-primary';
      open.href = externalBrowserUrl();
      open.innerHTML = '<i class="fas fa-up-right-from-square me-1"></i>Open in Chrome';
      actions.appendChild(open);
    }

    var copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'btn btn-sm btn-outline-secondary';
    copy.innerHTML = '<i class="fas fa-copy me-1"></i>Copy link';
    copy.addEventListener('click', function () {
      copyCurrentLink().then(function (ok) {
        copy.innerHTML = ok
          ? '<i class="fas fa-check me-1"></i>Link copied'
          : '<i class="fas fa-xmark me-1"></i>Copy failed';
      });
    });
    actions.appendChild(copy);
    box.appendChild(actions);

    if (!android) {
      var hint = document.createElement('div');
      hint.className = 'kbi-hint';
      hint.textContent = 'On iPhone: tap ••• at the top, then "Open in Safari".';
      box.appendChild(hint);
    }

    return box;
  }

  function permissionState() {
    if (!navigator.permissions || !navigator.permissions.query) {
      return Promise.resolve('unknown');
    }
    return navigator.permissions
      .query({ name: 'geolocation' })
      .then(function (status) { return status.state; })
      .catch(function () { return 'unknown'; });
  }

  function describeError(error, usedApproximate) {
    if (usedApproximate) {
      return 'Using an approximate location from your internet connection.';
    }
    if (!error) return 'Unable to get your location. Please try again.';
    if (error.code === 1) {
      if (isInAppBrowser()) {
        return 'Location is blocked because this page was opened inside another app ' +
          '(Facebook, Messenger, Instagram, etc.). Copy the link and open it in Chrome or Safari, then try again.';
      }
      return 'Location permission is blocked for this site. Tap the lock or information ' +
        'icon next to the web address, choose Permissions, set Location to Allow, then ' +
        'reload this page and tap the button again.';
    }
    if (error.code === 2) {
      return 'Location unavailable. Turn on your device location / GPS and try again.';
    }
    if (error.code === 3) {
      return 'Location timed out. Turn on your device location / GPS and try again.';
    }
    if (error.code === -1) {
      return error.message;
    }
    return error.message || 'Unable to get your location.';
  }

  function formatDistance(km) {
    if (km < 1) return Math.max(10, Math.round(km * 1000 / 10) * 10) + ' m';
    if (km < 10) return km.toFixed(1) + ' km';
    return Math.round(km) + ' km';
  }

  global.KabayaniLocation = {
    getPosition: getPosition,
    getApproximate: ipLocate,
    describeError: describeError,
    permissionState: permissionState,
    isInAppBrowser: isInAppBrowser,
    externalBrowserUrl: externalBrowserUrl,
    copyCurrentLink: copyCurrentLink,
    inAppHelpBox: inAppHelpBox,
    formatDistance: formatDistance
  };
})(window);
