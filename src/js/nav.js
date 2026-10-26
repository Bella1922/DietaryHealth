/**
 * nav.js — DietaryHealth
 * Handles auth guard + logout only.
 * Nav HTML is hardcoded in each page — no injection needed.
 *
 * Auth-exempt pages set:  <script>window.DH_NO_AUTH = true;</script>
 * before this script.
 */
(function () {
  'use strict';

  // Read session user
  var user = null;
  try {
    var raw = localStorage.getItem('dh_user');
    if (raw) user = JSON.parse(raw);
  } catch (e) {}

  // Auth guard
  if (!window.DH_NO_AUTH && !user) {
    window.location.replace('login.html');
    return;
  }

  // Fill in the user's name in nav if a #nav-username span exists
  if (user) {
    var nameEl = document.getElementById('nav-username');
    if (nameEl) {
      nameEl.textContent = user.firstName || user.username || '';
    }
  }

  // Global logout
  window.dhLogout = function () {
    try { localStorage.removeItem('dh_user'); } catch (e) {}
    window.location.href = '../pages/login.html';
  };

})();
