(function () {
  'use strict';

  // ── Read session user ──────────────────────────────────────
  var user = null;
  try {
    var raw = localStorage.getItem('dh_user');
    if (raw) user = JSON.parse(raw);
  } catch (e) {}

  // Auth guard — redirect to login if no session on protected pages
  if (!window.DH_NO_AUTH && !user) {
    window.location.replace('login.html');
    return;
  }

  // Run after DOM is ready (script may be in <head>)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {

  // ── Helpers ────────────────────────────────────────────────
  function initials(u) {
    if (!u) return '?';
    var f = (u.firstName || '').trim();
    var l = (u.lastName  || '').trim();
    if (f && l) return (f[0] + l[0]).toUpperCase();
    if (f)      return f[0].toUpperCase();
    if (u.username) return u.username[0].toUpperCase();
    return '?';
  }

  function displayName(u) {
    if (!u) return '';
    return u.firstName ? u.firstName : (u.username || '');
  }

  // Which page are we on?
  var page = window.location.pathname.split('/').pop() || 'dashboard.html';

  function activeClass(name) {
    return page === name ? ' active' : '';
  }

  // ── Inject styles ──────────────────────────────────────────
  var style = document.createElement('style');
  style.textContent = [
    /* Nav end / avatar area */
    '.nav-end { margin-left: auto; display: flex; align-items: center; gap: 12px; position: relative; }',

    /* Avatar button — white circle on green nav */
    '.nav-avatar {',
    '  width: 34px; height: 34px; border-radius: 50%;',
    '  background: rgba(255,255,255,0.25); color: #fff;',
    '  border: 2px solid rgba(255,255,255,0.6);',
    '  font-size: 13px; font-weight: 600;',
    '  display: flex; align-items: center; justify-content: center;',
    '  cursor: pointer; user-select: none;',
    '  font-family: inherit;',
    '  transition: background .15s;',
    '  flex-shrink: 0;',
    '}',
    '.nav-avatar:hover { background: rgba(255,255,255,0.35); }',

    /* Dropdown panel */
    '.nav-dropdown {',
    '  display: none;',
    '  position: absolute;',
    '  top: calc(100% + 10px);',
    '  right: 0;',
    '  min-width: 210px;',
    '  background: var(--surface);',
    '  border: 1px solid var(--border);',
    '  border-radius: var(--radius);',
    '  box-shadow: var(--shadow-md);',
    '  padding: 8px 0;',
    '  z-index: 999;',
    '}',
    '.nav-dropdown.open { display: block; }',
    '.nav-dd-name  { font-weight: 600; font-size: 14px; padding: 8px 16px 2px; color: var(--fg); }',
    '.nav-dd-email { font-size: 12px; color: var(--fg-muted); padding: 0 16px 10px;',
    '                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
    '.nav-dd-divider { border: none; border-top: 1px solid var(--border); margin: 4px 0; }',
    '.nav-dd-item {',
    '  display: block; width: 100%;',
    '  padding: 9px 16px; font-size: 14px;',
    '  color: var(--fg); text-decoration: none;',
    '  background: none; border: none;',
    '  cursor: pointer; font-family: inherit; text-align: left;',
    '  transition: background .12s;',
    '}',
    '.nav-dd-item:hover { background: var(--chip-bg); text-decoration: none; }',
    '.nav-dd-logout { color: var(--danger) !important; }',

    /* Footer */
    '.dh-footer {',
    '  border-top: 1px solid var(--border);',
    '  padding: 18px max(20px, env(safe-area-inset-left, 0px));',
    '  background: var(--surface);',
    '}',
    '.dh-footer-inner {',
    '  max-width: 900px; margin: 0 auto;',
    '  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;',
    '  font-size: 13px; color: var(--fg-muted);',
    '}',
    '.dh-footer-brand { font-weight: 600; color: var(--accent); }',
    '.dh-footer-sep   { color: var(--border); }',
  ].join('\n');
  document.head.appendChild(style);

  // ── Build nav HTML ─────────────────────────────────────────
  var avatarLabel = user ? initials(user) : '';
  var userName    = user ? displayName(user) : '';
  var userEmail   = user ? (user.email || '') : '';

  var navEl = document.createElement('nav');
  navEl.className = 'nav';
  navEl.id = 'dh-nav';
  navEl.innerHTML =
    '<a class="nav-brand" href="dashboard.html">Dietary<span>Health</span></a>' +
    '<div class="nav-links">' +
      '<a class="nav-link' + activeClass('dashboard.html')     + '" href="dashboard.html">Dashboard</a>' +
      '<a class="nav-link' + activeClass('calendar.html')      + '" href="calendar.html">Calendar</a>' +
      (user
        ? '<a class="nav-link' + activeClass('questionnaire.html') + '" href="questionnaire.html">Profile</a>' +
          '<button class="nav-link nav-logout" onclick="dhLogout()">Log out</button>'
        : '') +
    '</div>' +
    '<div class="nav-end">' +
      (user
        ? '<button class="nav-avatar" id="dh-avatar" aria-haspopup="true" aria-expanded="false"' +
            ' title="' + userName + '">' + avatarLabel + '</button>' +
          '<div class="nav-dropdown" id="dh-dropdown">' +
            '<div class="nav-dd-name">'  + userName  + '</div>' +
            '<div class="nav-dd-email">' + userEmail + '</div>' +
            '<hr class="nav-dd-divider">' +
            '<a  class="nav-dd-item" href="questionnaire.html">Edit profile</a>' +
            '<button class="nav-dd-item nav-dd-logout" onclick="dhLogout()">Log out</button>' +
          '</div>'
        : '') +
    '</div>';

  // ── Build footer HTML ──────────────────────────────────────
  var year = new Date().getFullYear();
  var footerEl = document.createElement('footer');
  footerEl.className = 'dh-footer';
  footerEl.innerHTML =
    '<div class="dh-footer-inner">' +
      '<span class="dh-footer-brand">DietaryHealth</span>' +
      '<span class="dh-footer-sep">&middot;</span>' +
      '<span>&copy; ' + year + ' Emma Swan &amp; Rachel Thomas</span>' +
      '<span class="dh-footer-sep">&middot;</span>' +
      '<span>AI/Data Science class project</span>' +
    '</div>';

  // ── Insert into DOM ────────────────────────────────────────
  // Insert nav at the very top of body
  if (document.body.firstChild) {
    document.body.insertBefore(navEl, document.body.firstChild);
  } else {
    document.body.appendChild(navEl);
  }
  document.body.appendChild(footerEl);

  // Flex column so footer sits at the bottom
  document.body.style.cssText += '; display:flex; flex-direction:column; min-height:100vh;';

  // Make the main content area fill the remaining space
  // Works for .page, .page-narrow, .auth-wrap
  setTimeout(function () {
    var main = document.querySelector('.page, .page-narrow, .auth-wrap');
    if (main) main.style.flex = '1';
  }, 0);

  // ── Dropdown toggle ────────────────────────────────────────
  var avatar   = document.getElementById('dh-avatar');
  var dropdown = document.getElementById('dh-dropdown');

  if (avatar && dropdown) {
    avatar.addEventListener('click', function (e) {
      e.stopPropagation();
      var isOpen = dropdown.classList.toggle('open');
      avatar.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });

    document.addEventListener('click', function () {
      dropdown.classList.remove('open');
      if (avatar) avatar.setAttribute('aria-expanded', 'false');
    });

    // Close on Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        dropdown.classList.remove('open');
        avatar.setAttribute('aria-expanded', 'false');
      }
    });
  }

  } // end init()

  // ── Global logout (must be accessible before DOM loads) ────
  window.dhLogout = function () {
    try { localStorage.removeItem('dh_user'); } catch (e) {}
    window.location.href = 'login.html';
  };

})();