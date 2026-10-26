/**
 * Flash messages (Django messages framework).
 *
 * Renders server-side messages inside a fixed stack and keeps them on screen
 * long enough to be read, close to how Facebook/Slack toasts behave:
 *   - success / info : auto-dismiss after 4s
 *   - warning        : auto-dismiss after 5s
 *   - error          : auto-dismiss after 6s
 *
 * Timers pause while the message is hovered or focused, so reading is never
 * interrupted. Extra messages can be pushed from page scripts at any time via
 * window.dhFlash(message, level).
 */
(function () {
  'use strict';

  var DEFAULT_TIMEOUTS = {
    success: 4000,
    info: 4000,
    warning: 5000,
    error: 6000
  };

  var STYLES = {
    success: { cls: 'alert-success', icon: 'fa-circle-check' },
    error: { cls: 'alert-danger', icon: 'fa-circle-xmark' },
    danger: { cls: 'alert-danger', icon: 'fa-circle-xmark' },
    warning: { cls: 'alert-warning', icon: 'fa-triangle-exclamation' },
    info: { cls: 'alert-info', icon: 'fa-circle-info' }
  };

  function dismiss(el) {
    if (!el || el.getAttribute('data-dh-flash-closing') === '1') {
      return;
    }
    el.setAttribute('data-dh-flash-closing', '1');
    el.classList.remove('show');
    window.setTimeout(function () {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
    }, 220);
  }

  function schedule(el) {
    var timeout = parseInt(el.getAttribute('data-dh-flash-timeout'), 10);
    if (isNaN(timeout) || timeout <= 0) {
      return;
    }

    var remaining = timeout;
    var startedAt = 0;
    var handle = null;

    function start() {
      startedAt = Date.now();
      handle = window.setTimeout(function () {
        handle = null;
        dismiss(el);
      }, remaining);
    }

    function pause() {
      if (!handle) {
        return;
      }
      window.clearTimeout(handle);
      handle = null;
      remaining -= Date.now() - startedAt;
      if (remaining < 0) {
        remaining = 0;
      }
    }

    function resume() {
      if (!handle && remaining > 0) {
        start();
      }
    }

    el.addEventListener('mouseenter', pause);
    el.addEventListener('mouseleave', resume);
    el.addEventListener('focusin', pause);
    el.addEventListener('focusout', resume);
    start();
  }

  function bind(el) {
    if (!el || el.getAttribute('data-dh-flash-ready') === '1') {
      return;
    }
    el.setAttribute('data-dh-flash-ready', '1');

    var close = el.querySelector('[data-dh-flash-close]');
    if (close) {
      close.addEventListener('click', function () {
        dismiss(el);
      });
    }
    schedule(el);
  }

  function stack() {
    var el = document.getElementById('dhFlashStack');
    if (!el) {
      el = document.createElement('div');
      el.id = 'dhFlashStack';
      el.className = 'dh-flash-stack';
      el.setAttribute('aria-live', 'polite');
      el.setAttribute('aria-atomic', 'false');
      document.body.appendChild(el);
    }
    return el;
  }

  function build(message, level) {
    var style = STYLES[level] || STYLES.info;
    var el = document.createElement('div');

    el.className = 'alert dh-flash alert-dismissible fade show ' + style.cls;
    el.setAttribute('role', (level === 'error' || level === 'danger') ? 'alert' : 'status');
    el.setAttribute('data-dh-flash', '');
    el.setAttribute('data-dh-flash-timeout', String(
      Object.prototype.hasOwnProperty.call(DEFAULT_TIMEOUTS, level) ? DEFAULT_TIMEOUTS[level] : DEFAULT_TIMEOUTS.info
    ));

    var icon = document.createElement('i');
    icon.className = 'fas dh-flash-icon ' + style.icon;
    icon.setAttribute('aria-hidden', 'true');

    var text = document.createElement('div');
    text.className = 'dh-flash-text';
    text.textContent = message;

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn-close';
    close.setAttribute('aria-label', 'Close');
    close.setAttribute('data-dh-flash-close', '');

    el.appendChild(icon);
    el.appendChild(text);
    el.appendChild(close);
    return el;
  }

  function init() {
    var nodes = document.querySelectorAll('[data-dh-flash]');
    for (var i = 0; i < nodes.length; i++) {
      bind(nodes[i]);
    }
  }

  window.dhFlash = function (message, level) {
    if (message === undefined || message === null || message === '') {
      return null;
    }
    var el = build(String(message), level || 'info');
    stack().appendChild(el);
    bind(el);
    return el;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
