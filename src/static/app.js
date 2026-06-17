/*
 * Copyright IBM Corp. 2024 - 2026
 * SPDX-License-Identifier: Apache-2.0
 */

// static/app.js
// Server-side DataTables UI with:
// - Pretty JSON toggle
// - Drag resizers (left/right + events/payload)
// - Policy selection (checkboxes, select-all per page, Export Selected, Deploy Selected)
// - Deploy cache (frontend-only via localStorage) that overrides Deployed → Yes styling,
//   persists across sessions, and can be cleared from the UI.
// - Temporal Grouping (related-events) vs Temporal Patterns (hierarchy view)
// - Auto-update mechanism that clears client-side caches when new data is loaded

// Logout button visibility is now controlled server-side based on ENABLE_AUTH setting
// No client-side logic needed!

// ------- Deploy Configuration Parameters -------
/**
 * Maximum number of policy IDs to include in a single deploy request.
 * Smaller batches process faster but create more network overhead.
 * @type {number}
 * @default 50
 */
const DEPLOY_BATCH_SIZE = 50;

// ---- Update watcher (poll /api/last_update) ----
let __lastSeenVersion = +(localStorage.getItem('last_seen_version') || 0);
let __updateBannerVisible = false;
let __updatePollTimer = null;
const LS_AUTO_REFRESH = 'auto_refresh_enabled';
const DEFAULT_WATCH_INTERVAL_MS = 15000;
let __updateReq = null;  // track inflight poll
/**
 * Maximum number of concurrent deploy requests.
 * Balances throughput against server load and browser resources.
 * @type {number}
 * @default 3
 */
const DEPLOY_MAX_INFLIGHT = 3;
/**
 * Number of policies to process concurrently on the backend per batch.
 * Higher values increase server-side parallelism but may impact stability.
 * @type {number}
 * @default 8
 */
const DEPLOY_CONCURRENCY_PER_BATCH = 8;

/**
 * Client-side timeout for each deploy request in milliseconds.
 * Prevents UI from hanging indefinitely on network issues.
 * @type {number}
 * @default 120000 (2 minutes)
 */
const DEPLOY_REQUEST_TIMEOUT_MS = 120000;
// Selection state reset gate for the next refresh
/**
 * Flag to prevent selection restoration after table refresh
 * @type {boolean}
 */
var __suppressRestoreSelection = false;

/**
 * Maximum number of policies that can be selected for deployment at once.
 * Prevents excessive server load and potential timeouts.
 * @type {number}
 * @default 20
 */
const MAX_DEPLOY_SELECTION = 20;

/**
 * Tracks whether the user has been notified about exceeding selection limit
 * @type {boolean}
 */
let __overCapNotified = false;

var policyTable, eventsTable, selectedPolicyId = null;
var __columnWidths__ = {};
var __policiesFirstLoadHandled = false;

// Define the common JSON fields we expect to find in the Details column
var jsonFields = [
  { field: 'Tally', displayName: 'Tally' },
  { field: 'X733EventType', displayName: 'X733 Event Type' },
  { field: 'TaskList', displayName: 'Task List' },
  { field: 'deletedat', displayName: 'Deleted At' },
  { field: 'NmosCauseType', displayName: 'Nmos Cause Type' },
  { field: 'AlertKey', displayName: 'Alert Key' },
  { field: 'AlertGroup', displayName: 'Alert Group' },
  { field: 'Web-Monitor', displayName: 'Web Monitor' },
  { field: 'Grade', displayName: 'Grade' },
  { field: 'FirstOccurrence', displayName: 'First Occurrence' },
  { field: 'ProcessReq', displayName: 'Process Req' },
  { field: 'lastmodified', displayName: 'Last Modified' },
  { field: 'Class', displayName: 'Class' },
  { field: 'ExpireTime', displayName: 'Expire Time' },
  { field: 'Acknowledged', displayName: 'Acknowledged' },
  { field: 'OwnerUID', displayName: 'Owner UID' },
  { field: 'OwnerGID', displayName: 'Owner GID' },
  { field: 'X733ProbableCause', displayName: 'X733 Probable Cause' },
  { field: 'originalseverity', displayName: 'Original Severity' },
  { field: 'Severity', displayName: 'Severity' },
  { field: 'NmosObjInst', displayName: 'Nmos Obj Inst' },
  { field: 'Flash', displayName: 'Flash' },
  { field: 'SuppressEscl', displayName: 'Suppress Escl' },
  { field: 'Serial', displayName: 'Serial' },
  { field: 'StateChange', displayName: 'State Change' },
  { field: 'Poll', displayName: 'Poll' },
  { field: 'eventid', displayName: 'Event ID' },
  { field: 'group', displayName: 'Group' },
  { field: 'Agent', displayName: 'Agent' },
  { field: 'timestamp', displayName: 'Timestamp' },
  { field: 'hostname', displayName: 'Hostname' },
  { field: 'ip_address', displayName: 'IP Address' },
  { field: 'status', displayName: 'Status' },
  { field: 'value', displayName: 'Value' },
  { field: 'threshold', displayName: 'Threshold' },
  { field: 'message', displayName: 'Message' },
  { field: 'source', displayName: 'Source' },
  { field: 'target', displayName: 'Target' },
  { field: 'duration', displayName: 'Duration' },
  { field: 'count', displayName: 'Count' }
];

// Selection state
var selectedPolicies = new Set();
var selectedPolicyStates = new Map(); // id -> deployed? (bool)

// Payload state
var payloadRaw = null, payloadPretty = null, payloadSuffix = "";

// Layout splits
var LEFT_SPLIT = +localStorage.getItem('leftSplit') || (5 / 13);
var RIGHT_SPLIT = +localStorage.getItem('rightSplit') || 0.25;
var MAIN_RESIZER_THICKNESS = 8;
var RESIZER_THICKNESS = 8;

// ---- Deploy cache (frontend-only) ----
const LS_DEPLOY_CACHE_KEY = 'deploy_cache_ids';
var overrideDeployed = new Set(); // IDs known deployed by client (from cache or recent success)

function autoRefreshEnabled() {
  try { return localStorage.getItem(LS_AUTO_REFRESH) === '1'; } catch (_) { return false; }
}
function setAutoRefreshEnabled(on) {
  try { localStorage.setItem(LS_AUTO_REFRESH, on ? '1' : '0'); } catch (_){}
  $('#auto-refresh').prop('checked', !!on);
}

// Set auto refresh to be enabled by default
try {
  if (localStorage.getItem(LS_AUTO_REFRESH) === null) {
    localStorage.setItem(LS_AUTO_REFRESH, '1');
  }
} catch (_){}

function ensureAutoRefreshToggle() {
  if ($('#auto-refresh-wrap').length) return;
  const $form = $('#registry-form'); if (!$form.length) return;

  const html = `
    <div id="auto-refresh-wrap" class="form-check form-switch ms-2" title="Automatically refresh tables when new data is available">
      <input class="form-check-input" type="checkbox" id="auto-refresh">
      <label class="form-check-label" for="auto-refresh">Auto refresh</label>
    </div>`;
  // place it near the group selector / search bar
  ($form.find('#events-search-wrap').length ? $(html).insertBefore('#events-search-wrap') : $form.append(html));

  // initialize from storage
  setAutoRefreshEnabled(autoRefreshEnabled());

  $(document).off('change.autoRefresh').on('change.autoRefresh', '#auto-refresh', function () {
    setAutoRefreshEnabled(this.checked);
    showNotification(this.checked ? 'Auto refresh enabled' : 'Auto refresh disabled', 'info', 2000);
  });
}
function renderUpdateBanner(onRefreshClick) {
  if (__updateBannerVisible) return;
  __updateBannerVisible = true;

  const $banner = $(`
    <div class="update-notification" id="update-banner">
      <div class="update-message">
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i>
        <span>New data is available.</span>
      </div>
      <div style="margin-left:12px; display:flex; gap:8px;">
        <button id="update-refresh" class="btn btn-sm btn-primary" type="button">Refresh</button>
        <button id="update-dismiss" class="btn btn-sm btn-outline-secondary" type="button">Dismiss</button>
      </div>
    </div>
  `).appendTo('body');

  $('#update-refresh').on('click', function(){
    // Clear caches silently before calling the provided refresh function
    clearDeployCacheSilently().then(() => {
      if (typeof onRefreshClick === 'function') onRefreshClick();
      hideUpdateBanner();
    });
  });
  $('#update-dismiss').on('click', hideUpdateBanner);
}

function hideUpdateBanner() {
  if (!__updateBannerVisible) return;
  __updateBannerVisible = false;
  $('#update-banner').remove();
}
function pickVersion(d) {
  if (!d || typeof d !== 'object') return 0;
  // Prefer server-provided version (mtime or computed)
  let v = Number(d.version || 0);
  if (!v && d.last_update_iso) {
    const t = Date.parse(d.last_update_iso);
    if (!isNaN(t)) v = Math.max(v, Math.floor(t / 1000));
  }
  if (!v && d.last_update) {                  // if server kept your original key
    const t = Date.parse(d.last_update);
    if (!isNaN(t)) v = Math.max(v, Math.floor(t / 1000));
  }
  if (!v && d.update_count != null) {
    v = Math.max(v, Number(d.update_count) || 0);
  }
  return v || 0;
}


function startUpdateWatcher(intervalMs = 306000) {
  if (__updatePollTimer) clearInterval(__updatePollTimer);

  const check = () => {
    if (__updateReq) return;  // don't overlap polls
    __updateReq = fetch('/api/last_update', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const ver = pickVersion(d);
        if (ver && ver > __lastSeenVersion) {
          if (autoRefreshEnabled()) {
            // Clear caches silently first, then refresh data
            clearDeployCacheSilently().then(() => {
              softRefreshData();
              markUpdateSeen(ver);
              showNotification('Data updated • tables refreshed', 'success', 2500);
            });
          } else {
            renderUpdateBanner(() => {
              softRefreshData();
              markUpdateSeen(ver);
            });
          }
        }
      })
      .catch(() => {})
      .finally(() => { __updateReq = null; });
  };

  check();
  __updatePollTimer = setInterval(check, intervalMs);
}


function markUpdateSeen(version) {
  __lastSeenVersion = Number(version) || 0;
  try { localStorage.setItem('last_seen_version', String(__lastSeenVersion)); } catch(e){}
}

/**
 * Silently clears both client and server deploy caches without prompts or alerts
 * Used during auto-updates and manual refreshes
 */
function clearDeployCacheSilently() {
  // Clear client-side cache immediately
  overrideDeployed.clear();
  updateClearCacheButton();
  
  // Clear server-side cache
  return fetch('/api/deploy_cache', { method: 'DELETE' })
    .then(() => {
      // Ensure client cache is cleared again after server response
      overrideDeployed.clear();
      updateClearCacheButton();
      return true;
    })
    .catch(() => {
      // Even if server cache clear fails, ensure client cache is cleared
      overrideDeployed.clear();
      updateClearCacheButton();
      return false;
    });
}

// "Soft" refresh without full page reload
function softRefreshData() {
  // Clear both client and server caches silently
  clearDeployCacheSilently();

  fetch('/api/last_update', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(d => markUpdateSeen(pickVersion(d)))
    .catch(()=>{});

  if (window.policyTable) policyTable.ajax.reload(null, false);
  if (isPatternsMode()) {
    if (window.selectedPolicyId) loadPatternDetailsForPolicy(selectedPolicyId);
  } else {
    if (window.eventsTable) eventsTable.ajax.reload(null, true);
    else ensureEventsTable();
  }
}


// ---- Simple notification system ----
function showNotification(message, type = 'info', duration = 3000, actionButton = null) {
  $('#notification-container').remove();
  const $container = $('<div id="notification-container"></div>').appendTo('body');
  
  let notificationHtml = '<div class="notification notification-' + type + '">' +
    '<span class="notification-message">' + message + '</span>';
  
  // Add action button if provided
  if (actionButton && actionButton.text && actionButton.callback) {
    notificationHtml += '<button class="notification-action btn btn-sm btn-' +
      (actionButton.style || 'light') + ' ms-2">' + actionButton.text + '</button>';
  }
  
  notificationHtml += '</div>';
  const $notification = $(notificationHtml).appendTo($container);
  
  // Attach action button callback if provided
  if (actionButton && actionButton.callback) {
    $notification.find('.notification-action').on('click', function(e) {
      e.preventDefault();
      actionButton.callback();
      // Don't auto-dismiss if callback is triggered
      if (actionButton.keepOpen !== true) {
        $notification.removeClass('show');
        setTimeout(() => $notification.remove(), 300);
      }
    });
  }
  
  setTimeout(() => $notification.addClass('show'), 10);
  if (duration > 0) {
    setTimeout(() => {
      $notification.removeClass('show');
      setTimeout(() => $notification.remove(), 300);
    }, duration);
  }
  return $notification;
}

function clearDeployCache() {
  overrideDeployed.clear();
  try { localStorage.removeItem(LS_DEPLOY_CACHE_KEY); } catch (e) { }
  if (policyTable) policyTable.ajax.reload(null, false);
  updateClearCacheButton();
}

function updateClearCacheButton() {
  const hasCache = overrideDeployed.size > 0;
  const $btn = $('#clear-deploy-cache');
  if ($btn.length === 0) return;
  $btn.find('.cache-badge').text(overrideDeployed.size || 0);
  $btn
    .prop('disabled', !hasCache)
    .toggleClass('btn-outline-secondary', !hasCache)
    .toggleClass('btn-warning', hasCache)
    .attr('title', hasCache
      ? 'Clear cached deployed policy IDs (UI overrides)'
      : 'No cached deployed IDs');
}

// ---- Injected styles ----
function ensureDeployedStyles() {
  // (kept for symmetry; your deployed styles are controlled via CSS)
}

// --- neutral, high-contrast tree styles for Pattern Hierarchy (match left table look) ---
// --- neutral, table-default background; black text; bold nodes + IF lines ---
(function ensurePatternTreeStyles(){
  const id = 'pattern-tree-styles';
  const css = `
  /* keep DataTables background as-is (no overrides) */
  #events-table td.tree-cell { padding:10px 12px !important; vertical-align: top; }

  .ptree { font-size:13.5px; line-height:1.45; color:#000; }
  .ptree ul { list-style:none; margin:6px 0 0 0; padding-left:18px; border-left:1px dashed #b8bfc7; }
  .ptree li { margin:0; padding:6px 0 0 12px; position:relative; }
  .ptree .node { display:inline-flex; gap:8px; align-items:baseline; }

  /* plain black text */
  .ptree .meta { color:#000; }

  /* nodes (“Condition set”, “Group …”, “Conditions”, “Actions”, “value/if”) */
  .ptree .badge{
    display:inline-block; padding:2px 8px; border-radius:9999px;
    font-size:11.5px; font-weight:700; line-height:1;
    background:transparent; border:1px solid #c7c9cc; color:#000;
  }

  /* make ONLY the IF lines’ text bold black */
  .ptree .badge.if + .meta { font-weight:700; color:#000; }

  .ptree .caret { cursor:pointer; user-select:none; font-weight:800; margin-right:6px; color:#000; }
  .ptree .collapsed > ul { display:none; }
  `;
  $('#'+id).remove();
  $('<style/>',{ id, text: css }).appendTo(document.head || document.body);
})();

// Add styles for notification action buttons
(function ensureNotificationActionStyles(){
  const id = 'notification-action-styles';
  const css = `
  .notification {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  
  .notification-action {
    white-space: nowrap;
    margin-left: 12px;
    font-size: 0.85rem;
    padding: 2px 8px;
  }
  
  #notification-container {
    z-index: 9999;
    max-width: 90%;
    width: 500px;
  }
  
  .notification-info {
    background-color: rgba(13, 202, 240, 0.2);
    border-left: 4px solid #0dcaf0;
  }
  
  .notification-success {
    background-color: rgba(25, 135, 84, 0.2);
    border-left: 4px solid #198754;
  }
  
  .notification-warning {
    background-color: rgba(255, 193, 7, 0.2);
    border-left: 4px solid #ffc107;
  }
  
  .notification-error {
    background-color: rgba(220, 53, 69, 0.2);
    border-left: 4px solid #dc3545;
  }
  `;
  $('#'+id).remove();
  $('<style/>',{ id, text: css }).appendTo(document.head || document.body);
})();

// Add styles for progress bars
(function ensureProgressBarStyles(){
  const id = 'progress-bar-styles';
  const css = `
  .loading-progress-bar {
    height: 4px;
    background-color: #e9ecef;
    border-radius: 2px;
    margin-top: 4px;
    overflow: hidden;
  }
  
  .loading-progress-bar .progress {
    height: 100%;
    background-color: #0dcaf0;
    width: 0%;
    transition: width 0.3s ease;
  }
  
  .loading-status {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    margin-top: 2px;
  }
  `;
  $('#'+id).remove();
  $('<style/>',{ id, text: css }).appendTo(document.head || document.body);
})();

// Add styles for loading indicators
(function ensureLoadingStyles(){
  const id = 'loading-indicator-styles';
  const css = `
  #policies-loading-info,
  #events-loading-info {
    position: relative;
    margin-bottom: 8px;
    font-size: 0.85rem;
    border-left: 3px solid #0dcaf0;
    background-color: rgba(13, 202, 240, 0.1);
    transition: opacity 0.3s ease;
    padding: 8px 12px;
    border-radius: 4px;
  }
  
  #policies-loading-info .bi-info-circle,
  #events-loading-info .bi-info-circle {
    margin-right: 4px;
    color: #0dcaf0;
  }
  
  .loaded-count, .total-count {
    font-weight: bold;
  }
  
  .load-more-btn {
    transition: all 0.2s ease;
  }
  
  .load-more-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
  }
  
  .loading-progress-bar {
    height: 6px;
    background-color: rgba(233, 236, 239, 0.5);
    border-radius: 3px;
    margin: 6px 0;
    overflow: hidden;
  }
  
  .loading-progress-bar .progress {
    height: 100%;
    background-color: #0dcaf0;
    width: 0%;
    transition: width 0.5s ease;
    border-radius: 3px;
  }
  
  .loading-status {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: #6c757d;
  }
  `;
  $('#'+id).remove();
  $('<style/>',{ id, text: css }).appendTo(document.head || document.body);
})();


$(function () {
  ensureDeployedStyles();
  installGlobalSearchHandler();

  fetch('/api/deploy_cache')
    .then(r => r.json())
    .then(d => {
      const ids = (d && Array.isArray(d.ids)) ? d.ids : [];
      overrideDeployed = new Set(ids.map(String));
    })
    .catch(() => { overrideDeployed = new Set(); })
    .finally(() => {
      ensurePrettySwitch();
      ensurePolicyButtons();
      ensureGroupSelector();
      ensureAutoRefreshToggle();
      updateActionButtons();
      updateClearCacheButton();
      installRightResizer();
      initPolicies();
      setupResizeButtons();
      applyDefaultColumns();
      installMainResizer();
      applyLeftRightWidths();
      $('.container-fluid .row.mt-3').addClass('two-pane-nowrap');
    });

  // Auto-select 1st policy (when no global search), else load global events table
  $('#policy-table').on('xhr.dt', function () {
    if (__policiesFirstLoadHandled) return;
    __policiesFirstLoadHandled = true;
    const term = ($('#events-global-search').val() || '').trim();
    if (!term) {
      const first = policyTable.row(0).data();
      if (first && first.policy_id) {
        selectedPolicyId = first.policy_id;
        $('#selected-policy').text(selectedPolicyId);
        $('#policy-table tbody tr:eq(0)').addClass('selected-row');
        if (!isPatternsMode()) ensureEventsTable();
      }
    } else {
      selectedPolicyId = null;
      $('#selected-policy').text('None');
      if (!eventsTable) ensureEventsTable(); else eventsTable.ajax.reload(null, true);
    }
    requestAnimationFrame(layoutHeights);
  });

  // Pretty toggle
  $(document).on('change', '#pretty-json', renderPayload);

  // Resize
  let raf;
  $(window).on('resize', function () {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(layoutHeights);
  });
  
  // Add keyboard shortcut (Alt+M) to toggle between modes
  $(document).on('keydown', function(e) {
    // Alt+M to toggle between modes
    if (e.altKey && e.key === 'm') {
      const $selector = $('#group-selector');
      if ($selector.length) {
        const currentValue = $selector.val();
        const newValue = currentValue === 'related-events' ?
          'analytics.temporal-patterns' : 'related-events';
        
        $selector.val(newValue).trigger('change');
        
        // Update Advanced Filter button state based on mode
        const $advancedFilterBtn = $('#open-advanced-filter');
        if ($advancedFilterBtn.length) {
          const inPatternsMode = newValue === 'analytics.temporal-patterns';
          if (inPatternsMode) {
            $advancedFilterBtn
              .prop('disabled', true)
              .removeClass('btn-primary')
              .addClass('btn-secondary')
              .attr('title', 'Advanced Filter is only available for Temporal Grouping (event data)');
          } else {
            $advancedFilterBtn
              .prop('disabled', false)
              .removeClass('btn-secondary')
              .addClass('btn-primary')
              .attr('title', 'Open advanced filter builder');
          }
        }
        
        showNotification(
          `Switched to ${newValue === 'related-events' ? 'Temporal Grouping' : 'Temporal Patterns'} mode`,
          'info',
          2000
        );
      }
    }
  });

  // Export
  $(document).on('click', '#export-selected-policies', function () {
    if (selectedPolicies.size === 0) { alert('No policies selected.'); return; }
    const arr = Array.from(selectedPolicies).sort();
    const blob = new Blob([arr.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'selected_policies_' + new Date().toISOString().replace(/[:.]/g, '-') + '.txt';
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
  });

  // Clear Deploy Cache (server-side file)
  $(document).on('click', '#clear-deploy-cache', function () {
    if (!confirm('This will clear the server cache file used to override Deployed=Yes.\n\nProceed?')) return;
    
    // Use our shared function for the core functionality
    clearDeployCacheSilently()
      .then(success => {
        if (policyTable) policyTable.ajax.reload(null, false);
        alert('Server deploy cache cleared.\n\nReload policies_export.csv to reflect upstream truth.');
      })
      .catch(() => alert('Failed to clear server cache'));
  });

  // Deploy flow
  $(document).on('click', '#deploy-selected-policies', async function () {
    refreshSelectedStatesFromVisiblePage();

    if (selectedPolicies.size === 0) {
      alert('No policies selected.\n\nSelect at least one UNDEPLOYED policy to deploy.');
      return;
    }
    const n = selectedPolicies.size || 0;
    if (n > MAX_DEPLOY_SELECTION) {
      alert(`You selected ${n} policies.\n\nMax per deploy is ${MAX_DEPLOY_SELECTION}.\nPlease reduce your selection and try again.`);
      return;
    }

    const all = Array.from(selectedPolicies);
    const deployed = [], undeployed = [], unknown = [];
    all.forEach(id => {
      if (!selectedPolicyStates.has(id)) unknown.push(id);
      else if (selectedPolicyStates.get(id)) deployed.push(id);
      else undeployed.push(id);
    });

    if (undeployed.length === 0) {
      let msg = 'All selected policies are already deployed.\n\nUncheck these:\n' +
        (deployed.length ? '\n' + deployed.join('\n') : '\n— none —');
      if (unknown.length) msg += '\n\nStatus unknown (off-page):\n' + unknown.join('\n');
      alert(msg);
      return;
    }

    if (deployed.length) {
      alert('These policies are already deployed and will be skipped:\n\n' +
        deployed.join('\n') +
        (unknown.length ? '\n\nStatus unknown (off-page):\n' + unknown.join('\n') : ''));
    }

    const baseUrl = ($('#registry-url').val() || '').trim();
    const user = ($('#registry-username').val() || '').trim();
    const pass = $('#registry-password').val() || '';

    if (!baseUrl) { alert('Registry URL is required.'); return; }
    if (!user && !pass) {
      if (!confirm('No username/password provided.\n\nProceed without authentication?')) return;
    }

    const $btn = $('#deploy-selected-policies').prop('disabled', true).text('Deploying…');

    try {
      const results = await deployPoliciesBatched(undeployed, { url: baseUrl, user, pass });

      if (results.urls) {
        console.group('Deploy request URLs');
        Object.entries(results.urls).forEach(([id, url]) => console.log(id, '→', url));
        console.groupEnd();
      }

      results.ok.forEach(id => {
        id = String(id);
        overrideDeployed.add(id);
        selectedPolicyStates.set(id, true);
        selectedPolicies.delete(id);
      });

      fetch('/api/deploy_cache', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: results.ok })
      }).catch(() => { });

      updateClearCacheButton();
      updateActionButtons();

      clearAllSelectionsUI();
      __suppressRestoreSelection = true;

      if (policyTable) {
        policyTable.ajax.reload(function () {
          restoreSelectionAfterRefresh();
        }, false);
      }

      const okCount = results.ok.length;
      const failCount = results.fail.length;
      if (okCount > 0 && failCount === 0) {
        showNotification(`Successfully deployed ${okCount} policies`, 'success', 5000);
      } else if (okCount > 0 && failCount > 0) {
        showNotification(`Deployed ${okCount} policies, ${failCount} failed`, 'warning', 5000);
      } else if (okCount === 0 && failCount > 0) {
        showNotification(`Failed to deploy ${failCount} policies`, 'error', 5000);
      }

      let msg = 'Deploy completed.\n\n' +
        'Succeeded: ' + okCount + '\n' +
        'Failed:    ' + failCount;

      if (failCount) {
        const list = results.fail.slice(0, 25).map(e =>
          `${e.id} [${e.status}]${e.error ? ' - ' + e.error : ''}`
        ).join('\n');
        msg += '\n\nFailures (up to 25):\n' + list;
      }

      msg += '\n\nNext steps:\n' +
        '1) Reload policies_export.csv so the upstream data reflects new states.\n' +
        '2) After reloading, clear the local deploy cache (click "Clear Deploy Cache") to avoid stale UI overrides.';

      alert(msg);
    } catch (e) {
      console.error(e);
      showNotification('Deploy failed: ' + (e && e.message ? e.message : e), 'error', 5000);
      alert('Deploy failed: ' + (e && e.message ? e.message : e));
    } finally {
      $btn.prop('disabled', false).text('Deploy Selected');
    }
  });

  // Persist registry fields + add global event search input
  (function ensureRegistryFields() {
    $('#registry-url').val(localStorage.getItem('registry_url') || '');
    $('#registry-username').val(localStorage.getItem('registry_user') || '');
    $('#registry-password').val(localStorage.getItem('registry_pass') || '');
    $(document).on('input change', '#registry-url', function () { localStorage.setItem('registry_url', this.value.trim()); });
    $(document).on('input change', '#registry-username', function () { localStorage.setItem('registry_user', this.value.trim()); });
    $(document).on('input change', '#registry-password', function () { localStorage.setItem('registry_pass', this.value); });

    if ($('#events-global-search').length === 0) {
      const $form = $('#registry-form');
      if ($form.length) {
        // Check if we're in Patterns mode
        const inPatternsMode = isPatternsMode();
        const buttonDisabled = inPatternsMode ? 'disabled' : '';
        const buttonClass = inPatternsMode ? 'btn-secondary' : 'btn-primary';
        const buttonTitle = inPatternsMode ?
          'Advanced Filter is only available for Temporal Grouping (event data)' :
          'Open advanced filter builder';
        
        const html =
          '<div id="events-search-wrap" style="margin-left:auto; display:flex; gap:8px; align-items:center;">' +
          '<input type="text" id="events-global-search" ' +
          'class="form-control form-control-sm" ' +
          'placeholder="Search all events…" style="width:360px">' +
          `<button id="open-advanced-filter" class="btn btn-sm ${buttonClass}" title="${buttonTitle}" style="white-space:nowrap;" ${buttonDisabled}>` +
          '<i class="bi bi-funnel"></i> Advanced Filter' +
          '</button>' +
          '</div>';
        $form.append(html);
      }
    }
  })();


fetch('/api/last_update', { cache: 'no-store' })
  .then(r => r.ok ? r.json() : null)
  .then(d => {
    const ver = pickVersion(d);
    if (ver) markUpdateSeen(ver);
  })
  .finally(() => startUpdateWatcher(15000));


});

/* -------------------- Policies -------------------- */

function ensureEventsModeUI() {
  rebuildEventsTheadForEventsMode();
  $('#events-container .card-header h2').text('Event Details');
  $('#payload-container .card-header h3').text('Event Payload');
  $('#toggle-details').show();
  showPayloadPane(true);
  if (policyTable) policyTable.columns([2, 3]).visible(true, false);
}

function rebuildEventsTheadForEventsMode() {
  if ($.fn.DataTable.isDataTable('#events-table')) {
    $('#events-table').DataTable().clear().destroy();
  }
  $('#events-table thead')
    .empty()
    .append(
      '<tr>' +
      '<th>Event ID</th>' +
      '<th>Severity</th>' +
      '<th>Resource</th>' +
      '<th>Summary</th>' +
      '<th class="details-col">Details</th>' +
      '<th class="type-details-col">Type</th>' +
      '</tr>'
    );
  $('#events-table tbody').empty();
}

function getTopConditions(parsed) {
  const csRoot = parsed && (parsed.condition_set || parsed) || {};
  return (csRoot.trigger && csRoot.trigger.conditions) || csRoot.conditions || null;
}

// Extract one row per *group* under topConditions.value[*]
function extractGroups(parsed) {
  const top = getTopConditions(parsed);
  const topOp = (top && top.operator) || '';
  const arr = (top && Array.isArray(top.value)) ? top.value : [];

  const groups = arr.map((g, idx) => {
    const op = (g && g.operator) || topOp || '';
    const leaves = (g && Array.isArray(g.value)) ? g.value : [];
    const resVals = [];
    if (g && Array.isArray(g.actions)) {
      g.actions.forEach(a => {
        const p = a && a.parameters;
        const rv = p && p.resourceValues;
        if (Array.isArray(rv)) rv.forEach(v => resVals.push(String(v)));
        else if (rv != null) resVals.push(String(rv));
      });
    }
    return { idx, op, leaves, resVals, group: g };
  });

  return { top, topOp, groups };
}

function summarizeList(arr, max = 3) {
  if (!arr || arr.length === 0) return '—';
  const head = arr.slice(0, max).join(', ');
  return arr.length > max ? `${head} … +${arr.length - max}` : head;
}

function summarizeCondition(c) {
  try {
    if (c && c.field && c.operator) {
      if (Array.isArray(c.allOf)) {
        return `${c.field} ${c.operator} ALL_OF(${c.allOf.join(', ')})`;
      }
      const v = (c.value !== undefined) ? c.value : (c.anyOf || c.allOf || '');
      return `${c.field} ${c.operator} ${Array.isArray(v) ? v.join(', ') : String(v)}`.trim();
    }
    if (c && c.operator && Array.isArray(c.value)) {
      return `(${c.operator}) ${c.value.length} sub-conditions`;
    }
  } catch (_) { }
  return JSON.stringify(c);
}

function summarizeGroup(g) {
  const conds = g.leaves || [];
  if (conds.length === 0) return '—';
  const joiner = ` ${g.op || '&&'} `;
  return conds.map(summarizeCondition).join(joiner);
}

function ensurePatternsModeUI() {
  $('#events-table tbody').off('.eventsMode').off('.patternsMode');
  $('#events-container .card-header h2').text('Pattern Details');
  $('#toggle-details').hide();

  if ($.fn.DataTable.isDataTable('#events-table')) {
    $('#events-table').DataTable().clear().destroy();
  }
  $('#events-table thead')
    .empty()
    .append('<tr><th>Pattern Hierarchy</th></tr>');

  $('#events-table tbody')
    .empty()
    .append('<tr><td class="text-muted" style="padding:12px 8px;">Select a policy on the left to load its conditions.</td></tr>');

  showPayloadPane(false);
  if (policyTable) policyTable.columns([2, 3]).visible(false, false);
  requestAnimationFrame(layoutHeights);
}

function showPayloadPane(show) {
  const $pc = $('#payload-container');
  const $rr = $('#right-resizer');
  if (!$pc.length) return;
  if (show) { $pc.show(); $rr.show(); }
  else { $pc.hide(); $rr.hide(); }
}

function initPolicies() {
  // Ensure extra headers exist BEFORE DataTable init
  const $theadRow = $('#policy-table thead tr');
  if ($theadRow.length) {
    const $ths = $theadRow.children('th');
    let $selectTh = $theadRow.find('th.select-col');
    if ($selectTh.length === 0) {
      $selectTh = $ths.length ? $ths.last().addClass('text-center select-col').empty()
        : $('<th class="text-center select-col"></th>').appendTo($theadRow);
    }
    if ($theadRow.find('th.enabled-col').length === 0) {
      $('<th class="text-center enabled-col">Deployed</th>').insertBefore($selectTh);
    }
  }

  policyTable = $('#policy-table').DataTable({
    serverSide: true,
    processing: true,
    ajax: {
      url: '/api/policies_ss',
      type: 'GET',
      data: function (d) {
        const term = ($('#events-global-search').val() || '').trim();
        if (term) d.global_search = term; else delete d.global_search;
        d.group_id = currentGroup();
        
        // Add advanced filter if active (check global AdvancedFilter object)
        if (typeof AdvancedFilter !== 'undefined' && AdvancedFilter.activeFilterJSON) {
          d.advancedFilter = AdvancedFilter.activeFilterJSON;
          console.log('[PolicyTable] Adding advancedFilter to request:', AdvancedFilter.activeFilterJSON);
        }
      },
      dataSrc: function(json) {
        // Use the helper function to update loading progress with metadata
        const info = {
          recordsTotal: json.recordsTotal || 0,
          end: json.data ? json.data.length : 0,
          metadata: json.metadata || {}
        };
        updateLoadingProgress('policies', info);
        
        // Show enhanced notification for very large datasets with improved options
        if (json.recordsTotal > 10000 && !sessionStorage.getItem('large_dataset_notified')) {
          const pageLength = policyTable ? policyTable.page.len() : 25;
          const initialLoad = Math.min(pageLength * 2, 100);
          
          showNotification(
            `<strong>Large dataset detected:</strong> ${json.recordsTotal.toLocaleString()} policies total.<br>` +
            `Currently showing ${initialLoad} records to maintain performance.`,
            'warning',
            8000, // Auto-dismiss after 8 seconds
            {
              text: 'Load More',
              style: 'primary',
              callback: function() {
                // Increase page size incrementally with a larger jump
                const newPageSize = Math.min(policyTable.page.len() * 3, 500);
                policyTable.page.len(newPageSize).draw();
                
                // Update the loading info with the new page size
                updateLoadingProgress('policies', {
                  recordsTotal: json.recordsTotal,
                  end: newPageSize,
                  metadata: json.metadata || {}
                }, true);
                
                // Show a notification with keyboard shortcut hint
                showNotification(
                  `Now showing ${newPageSize} policies per page. Use Alt+M to toggle view modes.`,
                  'success',
                  5000,
                  {
                    text: 'Load All',
                    style: 'outline-primary',
                    callback: function() {
                      if (json.recordsTotal > 5000) {
                        if (confirm(`Loading all ${json.recordsTotal.toLocaleString()} policies may affect performance. Continue?`)) {
                          policyTable.page.len(json.recordsTotal).draw();
                        }
                      } else {
                        policyTable.page.len(json.recordsTotal).draw();
                      }
                    }
                  }
                );
              }
            }
          );
          sessionStorage.setItem('large_dataset_notified', 'true');
        }
        
        return json.data;
      }
    },
    columns: [
      { data: 'policy_id' },
      { data: 'ranking_score' },
      { data: 'event_count' },
      { data: 'event_occurrences' },
      {
        data: null,
        className: 'text-center align-middle',
        render: function (_d, type, row) {
          const id = row && row.policy_id ? String(row.policy_id) : '';
          let val = resolveDeployedFlagFromRow(row);
          if (overrideDeployed.has(id)) val = true;
          if (type === 'sort') return val ? 1 : 0;
          const cls = val ? 'deployed-yes' : 'deployed-no';
          const txt = val ? 'Yes' : 'No';
          return '<span class="' + cls + '">' + txt + '</span>';
        }
      },
      {
        data: null, orderable: false, searchable: false, className: 'text-center align-middle',
        render: function (_d, type, row) {
          if (type !== 'display') return '';
          const id = row && row.policy_id ? String(row.policy_id) : '';
          const safe = encodeURIComponent(id);
          const selectable = isRowSelectable(row);
          if (!selectable && id) selectedPolicies.delete(id);
          const checked = selectable && id && selectedPolicies.has(id) ? ' checked' : '';
          const disabled = selectable ? '' : ' disabled title="Already deployed"';
          return '<input type="checkbox" class="form-check-input policy-select" data-id="' + safe + '"' + checked + disabled + '>';
        }
      }
    ],
    order: [[1, 'desc']],
    pageLength: 25,
    lengthMenu: [[10, 25, 50, 100, 200, 500, 1000], [10, 25, 50, 100, 200, 500, 1000]],
    autoWidth: true,
    responsive: false,
    deferRender: true,
    searchDelay: 400,
    dom: 'lrtip',
    language: { search: 'Search policies:' },
    scrollY: '100px',
    scrollCollapse: true,
    scrollX: true,
    columnDefs: [
      { targets: 4, width: 90 },
      { targets: 5, width: 60 }
    ],
    createdRow: function (row, data) {
      const id = data && data.policy_id ? String(data.policy_id) : '';
      if (id !== '') selectedPolicyStates.set(id, resolveDeployedFlagFromRow(data));
    }
  });

  ensurePolicySearchBox();
  ensureSelectAllInScrollHead();

  policyTable.on('draw.dt', function () {
    const nodes = policyTable.rows({ page: 'current' }).nodes();
    $(nodes).each(function () {
      const row = policyTable.row(this).data();
      const id = row && row.policy_id ? String(row.policy_id) : '';
      const $cb = $(this).find('input.policy-select');
      const selectable = isRowSelectable(row);
      $cb.prop('disabled', !selectable).attr('title', selectable ? '' : 'Already deployed');
      $cb.prop('checked', selectable && id && selectedPolicies.has(id));
    });

    purgeUnselectableFromSelection();
    ensureSelectAllInScrollHead();
    updateSelectAllState();
    updateActionButtons();
    ensurePolicySearchBox();
    
    // Update loading info on each draw using the helper function
    updateLoadingProgress('policies', policyTable.page.info());
    
    requestAnimationFrame(layoutHeights);
  });

  hookResizing($('#policy-table'), 'policy-table', policyTable);
  setDefaultWidths($('#policy-table'), 'policy-table', { 0: 310, 2: 70, 3: 40, 4: 80, 5: 40 });

  // Select-all (page)
  $(document)
    .off('change.policySelectAll')
    .on('change.policySelectAll', '#policy-container .dataTables_scrollHead #policy-select-all', function () {
      const checked = this.checked;
      this.indeterminate = false;

      const data = getCurrentPageData();
      data.forEach(row => {
        const id = row && row.policy_id ? String(row.policy_id) : '';
        if (!id) return;

        if (!isRowSelectable(row)) {
          selectedPolicies.delete(id);
          return;
        }
        const deployed = resolveDeployedFlagFromRow(row);
        if (checked) {
          selectedPolicies.add(id);
          selectedPolicyStates.set(id, deployed);
        } else {
          selectedPolicies.delete(id);
          selectedPolicyStates.delete(id);
        }
      });

      const nodes = policyTable.rows({ page: 'current' }).nodes();
      $(nodes).find('input.policy-select:not([disabled])').prop('checked', checked);
      purgeUnselectableFromSelection();
      updateSelectAllState();
      updateActionButtons();
    });

  // Individual checkbox
  $('#policy-table tbody').off('change', 'input.policy-select')
    .on('change', 'input.policy-select', function (e) {
      e.stopPropagation();
      const id = decodeURIComponent($(this).attr('data-id') || '');
      if (!id) return;

      const row = policyTable.row($(this).closest('tr')).data() || null;
      const deployed = resolveDeployedFlagFromRow(row);

      if (this.checked) {
        selectedPolicies.add(id);
        selectedPolicyStates.set(id, deployed);
      } else {
        selectedPolicies.delete(id);
        selectedPolicyStates.delete(id);
      }
      updateSelectAllState();
      updateActionButtons();
    });

  // Row click
  $('#policy-table tbody').off('click', 'tr').on('click', 'tr', function (e) {
    if ($(e.target).is('input, label, .policy-select')) return;
    const row = policyTable.row(this).data(); if (!row) return;

    selectedPolicyId = row.policy_id;
    $('#selected-policy').text(selectedPolicyId);
    $('#policy-table tbody tr').removeClass('selected-row');
    $(this).addClass('selected-row');

    if (isPatternsMode()) {
      loadPatternDetailsForPolicy(selectedPolicyId);
      return;
    }

    // Show a notification when clicking a policy during global search
    const globalSearchActive = ($('#events-global-search').val() || '').trim() !== '';
    if (globalSearchActive) {
      showNotification(
        `Showing events for selected policy: ${selectedPolicyId}`,
        'info',
        3000
      );
    }

    // Update the events panel title with the selected policy ID
    $('#events-container .card-header h2').text(`Event Details: ${selectedPolicyId}`);
    
    // Only initialize or reload events table if not in patterns mode
    if (!eventsTable) {
      initEvents();
    } else if (eventsTable.ajax) {
      eventsTable.ajax.reload(null, true);
    }
    payloadRaw = payloadPretty = null; payloadSuffix = "";
    $('#payload-json').text('Select an event to view payload');
    requestAnimationFrame(layoutHeights);
  });

  if (isPatternsMode()) ensurePatternsModeUI();
  else ensureEventsModeUI();
}

function resolveDeployedFlagFromRow(row) {
  if (!row) return false;
  let val =
    ('deployed' in row) ? row.deployed :
    ('is_deployed' in row) ? row.is_deployed :
    (row.statedata && 'deployed' in row.statedata) ? row.statedata.deployed :
    (row.statedata && typeof row.statedata.state === 'string') ? row.statedata.state :
    (typeof row.Deployed !== 'undefined') ? row.Deployed : false;

  if (typeof val === 'string') {
    const s = val.trim().toLowerCase();
    return (s === 'true' || s === 'yes' || s === '1' || s === 'active' || s === 'deployed');
  }
  return !!val;
}

function purgeUnselectableFromSelection() {
  const data = getCurrentPageData();
  data.forEach(row => {
    const id = row && row.policy_id ? String(row.policy_id) : '';
    if (id && !isRowSelectable(row)) {
      selectedPolicies.delete(id);
      selectedPolicyStates.delete(id);
    }
  });
}

function updateSelectAllState() {
  var $selectAll = $('#policy-select-all');
  if ($selectAll.length === 0) return;

  const data = getCurrentPageData();
  const selectable = data.filter(isRowSelectable);
  const total = selectable.length;

  if (!total) {
    $selectAll.prop({ checked: false, indeterminate: false, disabled: true });
    return;
  }
  $selectAll.prop('disabled', false);

  let checkedCount = 0;
  selectable.forEach(row => {
    const id = row && row.policy_id ? String(row.policy_id) : '';
    if (id && selectedPolicies.has(id)) checkedCount++;
  });

  if (checkedCount === 0) $selectAll.prop({ checked: false, indeterminate: false });
  else if (checkedCount === total) $selectAll.prop({ checked: true, indeterminate: false });
  else $selectAll.prop({ checked: false, indeterminate: true });
}

function refreshSelectedStatesFromVisiblePage() {
  if (!policyTable) return;
  const nodes = policyTable.rows({ page: 'current' }).nodes();
  $(nodes).find('input.policy-select:checked').each(function () {
    const id = decodeURIComponent($(this).attr('data-id') || '');
    if (!id) return;
    const row = policyTable.row($(this).closest('tr')).data() || null;
    selectedPolicyStates.set(id, resolveDeployedFlagFromRow(row));
  });
}

/* -------------------- Events (related-events) -------------------- */

function resetEventsTable() {
  // kill any table and row listeners
  $('#events-table tbody').off('.eventsMode .patternsMode');
  unbindEventsSearch();

  if ($.fn.DataTable.isDataTable('#events-table')) {
    $('#events-table').DataTable().clear().destroy();
  }
  eventsTable = null;

  // keep body empty so DT can re-init cleanly
  $('#events-table tbody').empty();
}



function ensureEventsTable() {
  if (!eventsTable) {
    initEvents();
  } else if (eventsTable.ajax && typeof eventsTable.ajax.reload === 'function') {
    eventsTable.ajax.reload(null, true);
  } else {
    // If eventsTable exists but doesn't have ajax (e.g., it's a pattern table), recreate it
    if ($.fn.DataTable.isDataTable('#events-table')) {
      eventsTable.destroy();
    }
    eventsTable = null;
    initEvents();
  }
}

function initEvents() {
  // Never create the server-side Events table in Patterns mode
  if (isPatternsMode()) return;

  // Using the global jsonFields array defined at the top of the file

  // Create column definitions for the standard columns
  const standardColumns = [
    { data: 'event_id' },
    { data: 'severity' },
    {
      data: 'payload_resource',
      render: function (data) {
        const s = data || '';
        const m = s.match(/node-([^-]+)/);
        return m ? m[0] : s;
      }
    },
    { data: 'summary' },
    {
      data: 'payload_details',
      className: 'details-col'
    },
    {
      data: 'payload_type',
      className: 'type-details-col'
    }
  ];

  // Create column definitions for the JSON fields (initially hidden)
  const jsonFieldColumns = jsonFields.map(fieldObj => {
    return {
      data: null,
      name: fieldObj.field,
      title: fieldObj.displayName,
      className: 'json-field-col',
      visible: false, // Hidden by default
      render: function(data, type, row) {
        // Try to extract the field from the payload_details JSON
        try {
          let details = row.payload_details || '';
          let value = null;
          
          // Try to parse the JSON or extract the field directly
          if (typeof details === 'string') {
            // Look for the field in the string using regex
            const regex = new RegExp(`['"]${fieldObj.field}['"]\\s*:\\s*([^,}]+)`);
            const match = details.match(regex);
            
            if (match) {
              value = match[1].trim();
              // Clean up the value
              if (value.startsWith("'") && value.endsWith("'")) {
                value = value.substring(1, value.length - 1);
              } else if (value.startsWith('"') && value.endsWith('"')) {
                value = value.substring(1, value.length - 1);
              } else if (!isNaN(value)) {
                value = Number(value);
              }
            }
          }
          
          // Return appropriate format based on the type
          if (type === 'display') {
            if (value === null || value === undefined) return '';
            
            if (typeof value === 'boolean') {
              return value ?
                '<span class="badge bg-success">Yes</span>' :
                '<span class="badge bg-secondary">No</span>';
            } else if (typeof value === 'number') {
              return value.toLocaleString();
            } else if (typeof value === 'string') {
              if (value.length > 50) {
                return `<span title="${value.replace(/"/g, '"')}">${value.substring(0, 50)}...</span>`;
              }
              return value;
            }
            
            return String(value);
          }
          
          // For sorting/filtering
          return value !== null ? String(value) : '';
        } catch (e) {
          return '';
        }
      }
    };
  });

  // Combine standard and JSON field columns
  const allColumns = [...standardColumns, ...jsonFieldColumns];

  eventsTable = $('#events-table').DataTable({
    serverSide: true,
    processing: true,
    ajax: {
      url: '/api/events_ss',
      type: 'GET',
      data: function (d) {
        const term = ($('#events-global-search').val() || '').trim();
        // If a policy is explicitly selected, prioritize showing its events
        // even if there's a global search term active
        if (selectedPolicyId) {
          d.policy_id = selectedPolicyId;
          delete d.global_search;
          d.group_id = currentGroup();
        } else if (term) {
          d.global_search = term;
          delete d.policy_id;
        } else {
          d.policy_id = selectedPolicyId;
          delete d.global_search;
          d.group_id = currentGroup();
        }
        
        // Add advanced filter if active (check global AdvancedFilter object)
        if (typeof AdvancedFilter !== 'undefined' && AdvancedFilter.activeFilterJSON) {
          d.advancedFilter = AdvancedFilter.activeFilterJSON;
          console.log('[EventsTable] Adding advancedFilter to request:', AdvancedFilter.activeFilterJSON);
        }
      },
      dataSrc: function(json) {
        // Use the helper function to update loading progress with metadata
        const info = {
          recordsTotal: json.recordsTotal || 0,
          end: json.data ? json.data.length : 0,
          metadata: json.metadata || {}
        };
        updateLoadingProgress('events', info);
        
        // Process the data to extract JSON fields
        if (json.data && json.data.length > 0) {
          json.data.forEach(row => {
            // Pre-process the details to extract JSON fields if needed
            const details = row.payload_details || '';
            if (details && typeof details === 'string') {
              // This is just preparation - actual rendering happens in the column definitions
              try {
                // Any preprocessing can be done here if needed
              } catch (e) {
                console.warn('Error preprocessing JSON fields:', e);
              }
            }
          });
        }
        
        // Show enhanced notification for very large datasets with improved options
        if (json.recordsTotal > 10000 && !sessionStorage.getItem('large_events_notified')) {
          const pageLength = eventsTable ? eventsTable.page.len() : 25;
          const initialLoad = Math.min(pageLength * 2, 100);
          
          // Create a more informative notification with better action buttons
          showNotification(
            `<strong>Large event dataset detected:</strong> ${json.recordsTotal.toLocaleString()} events total.<br>` +
            `Currently showing ${initialLoad} events to maintain performance.`,
            'warning',
            8000, // Auto-dismiss after 8 seconds
            {
              text: 'Load More',
              style: 'primary',
              callback: function() {
                // Increase page size incrementally with a larger jump
                const newPageSize = Math.min(eventsTable.page.len() * 3, 500);
                eventsTable.page.len(newPageSize).draw();
                
                // Update the loading info with the new page size
                updateLoadingProgress('events', {
                  recordsTotal: json.recordsTotal,
                  end: newPageSize,
                  metadata: json.metadata || {}
                }, true);
                
                // Show a notification with a secondary action button
                showNotification(
                  `Loading ${newPageSize} events per page`,
                  'info',
                  5000,
                  {
                    text: 'Load All',
                    style: 'outline-primary',
                    callback: function() {
                      if (json.recordsTotal > 3000) {
                        if (confirm(`Loading all ${json.recordsTotal.toLocaleString()} events may affect performance. Continue?`)) {
                          eventsTable.page.len(json.recordsTotal).draw();
                        }
                      } else {
                        eventsTable.page.len(json.recordsTotal).draw();
                      }
                    }
                  }
                );
              }
            }
          );
          sessionStorage.setItem('large_events_notified', 'true');
        }
        
        return json.data;
      }
    },
    columns: allColumns,
    order: [[0, 'asc']],
    pageLength: 25,
    lengthMenu: [[10,25,50,100,200,500,1000],[10,25,50,100,200,500,1000]],
    autoWidth: false,
    responsive: false,
    deferRender: true,
    searchDelay: 400,
    scrollY: '100px',
    scrollCollapse: true,
    scrollX: true
  });

  // Global search listener — bind ONLY in Events mode
  let evDeb;
  $(document).off('input.globalEventsSearchInEvents')
    .on('input.globalEventsSearchInEvents', '#events-global-search', function () {
    if (isPatternsMode()) return;               // guard if switch happened
    clearTimeout(evDeb);
    evDeb = setTimeout(function () {
      if (isPatternsMode()) return;             // guard again inside
      const term = ($('#events-global-search').val() || '').trim();

      if (term) {
        selectedPolicyId = null;
        $('#selected-policy').text('None');
        $('#policy-table tbody tr').removeClass('selected-row');
      } else {
        __policiesFirstLoadHandled = false;
      }

      if (policyTable) policyTable.ajax.reload(null, true);
      if (eventsTable && eventsTable.ajax && typeof eventsTable.ajax.reload === 'function') {
        eventsTable.ajax.reload(null, true);
      }
    }, 250);
    });

  hookResizing($('#events-table'), 'events-table', eventsTable);
  setDefaultWidths($('#events-table'), 'events-table', { 0: 480, 3: 520, 4: 360 });

  // Hide details cols by default
  eventsTable.columns([4, 5]).visible(false, false);
  $('#toggle-details').text('Show Details');

  function stripDNones() {
    $('#events-table thead th.details-col, #events-container .dataTables_scrollHead thead th.details-col').removeClass('d-none');
    $('#events-table thead th.type-details-col, #events-container .dataTables_scrollHead thead th.type-details-col').removeClass('d-none');
    $('#events-table td.details-col, #events-table td.type-details-col').removeClass('d-none');
  }
  stripDNones();
  eventsTable.on('draw.dt', stripDNones);

  // Row click → payload fetch
  $('#events-table tbody').off('click.eventsMode').on('click.eventsMode', 'tr', function () {
    const dt = $.fn.DataTable.isDataTable('#events-table') ? $('#events-table').DataTable() : null;
    if (!dt) return;
    const row = dt.row(this).data(); if (!row) return;

    const eventId = row.event_id;
    $('#selected-event').text(eventId);
    $('#events-table tbody tr').removeClass('selected-row');
    $(this).addClass('selected-row');
    $('#payload-json').text('Loading payload…');

    fetchPayloadForEvent(eventId, function (raw, pretty, suffix) {
      payloadRaw = raw; payloadPretty = pretty; payloadSuffix = suffix || "";
      renderPayload(); requestAnimationFrame(layoutHeights);
    }, function (msg) {
      payloadRaw = payloadPretty = null; payloadSuffix = "";
      $('#payload-json').text(msg || 'No payload data available for this event');
      requestAnimationFrame(layoutHeights);
    });
    
    // Update loading info when viewing a specific event
    $('#events-loading-info').hide();
  });

  eventsTable.one('draw.dt', () => requestAnimationFrame(layoutHeights));
  
  // Update loading info on each draw using the helper function
  eventsTable.on('draw.dt', function() {
    // Check if eventsTable and page method exist before calling
    if (eventsTable && eventsTable.page && typeof eventsTable.page === 'function') {
      updateLoadingProgress('events', eventsTable.page.info());
    }
  });
}



function installGlobalSearchHandler() {
  let evDeb;
  $(document)
    .off('input.globalEventsSearch')
    .off('input.globalEventsSearchInEvents'); // make sure the events-mode one isn’t lingering

  $(document).on('input.globalEventsSearch', '#events-global-search', function () {
    clearTimeout(evDeb);
    evDeb = setTimeout(function () {
      const term = ($('#events-global-search').val() || '').trim();

      if (term) {
        selectedPolicyId = null;
        $('#selected-policy').text('None');
        $('#policy-table tbody tr').removeClass('selected-row');
      } else {
        __policiesFirstLoadHandled = false;
      }

      if (policyTable) policyTable.ajax.reload(null, true);

      if (isPatternsMode()) {
        // Do not hit /api/events_ss in Patterns mode.
        if (!selectedPolicyId && $.fn.DataTable.isDataTable('#events-table')) {
          $('#events-table').DataTable().clear().draw();
          $('#events-table tbody').empty().append(
            '<tr><td class="text-muted" style="padding:12px 8px;">' +
            'Select a policy on the left to load its conditions.' +
            '</td></tr>'
          );
        }
        return;
      }

      if (!eventsTable) initEvents();
      else if (eventsTable.ajax && typeof eventsTable.ajax.reload === 'function') {
        eventsTable.ajax.reload(null, true);
      }
    }, 250);
  });
}


function unbindEventsSearch() {
  $(document).off('input.globalEventsSearchInEvents');
}


/* -------------------- Layout + resizers -------------------- */

function getDtFooterHeight($wrap) {
  let h = 0, $info = $wrap.find('.dataTables_info:visible'); if ($info.length) h += $info.outerHeight(true) || 0;
  let $pag = $wrap.find('.dataTables_paginate:visible'); if ($pag.length) h += $pag.outerHeight(true) || 0;
  return h;
}

function layoutHeights() {
  // Left
  const $polBody = $('#policy-container .dataTables_scrollBody');
  if ($polBody.length) {
    const $wrap = $polBody.closest('.dataTables_wrapper');
    const top = $polBody.offset().top - $(window).scrollTop();
    const avail = Math.max(160, window.innerHeight - top - getDtFooterHeight($wrap) - 12);
    setScrollY(policyTable, avail);
  }

  // Right
  const $evtBody = $('#events-container .card:first .dataTables_scrollBody');
  if ($evtBody.length) {
    if ($('#payload-container:visible').length) {
      const metrics = measureRightColumn();
      const eventsTarget = metrics.totalAvailClamped - metrics.payloadTarget;
      setScrollY(eventsTable, eventsTarget);
      $('#right-resizer').css({ height: RESIZER_THICKNESS + 'px' });

      const $payloadCard = $('#payload-container .card');
      const headerH = $('#payload-container .card-header').outerHeight(true) || 48;
      const chrome = $payloadCard.length ? ($payloadCard.outerHeight(true) - $payloadCard.height()) : 0;
      const preH = Math.max(80, metrics.payloadTarget - headerH - chrome - 8);
      $('#payload-json').css({ height: preH + 'px' });
    } else {
      const $wrap = $evtBody.closest('.dataTables_wrapper');
      const top = $evtBody.offset().top - $(window).scrollTop();
      const avail = Math.max(160, window.innerHeight - top - getDtFooterHeight($wrap) - 12);
      setScrollY(eventsTable, avail);
    }
  }
}

function setScrollY(dt, px) {
  if (!dt) return;
  const s = dt.settings()[0];
  s.oScroll.sY = px + 'px';
  $(dt.table().container()).find('div.dataTables_scrollBody').css({ height: px + 'px', maxHeight: px + 'px' });
  dt.columns.adjust();
}

/* ---- Pretty JSON ---- */

function prettyFromAny(raw) {
  try { return JSON.stringify(JSON.parse(raw), null, 2); } catch (_) {
    try { return JSON.stringify(JSON.parse(raw.replace(/'/g, '"')), null, 2); } catch (e) { }
  }
  const s = String(raw); let out = '', depth = 0, inStr = false, q = null, esc = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (inStr) { out += ch; if (esc) { esc = false; continue; } if (ch === '\\') { esc = true; continue; } if (ch === q) { inStr = false; q = null; } continue; }
    if (ch === '"' || ch == "'") { inStr = true; q = ch; out += ch; continue; }
    if (ch === '{' || ch === '[') { out += ch + '\n' + ' '.repeat(++depth * 2); continue; }
    if (ch === '}' || ch === ']') { out += '\n' + ' '.repeat(--depth * 2) + ch; continue; }
    if (ch === ',') { out += ch + '\n' + ' '.repeat(depth * 2); continue; }
    out += ch; if (ch === ':') out += ' ';
  }
  return out;
}

function renderPayload() {
  if (payloadRaw == null && payloadPretty == null) { $('#payload-json').text('Select an event to view payload'); return; }
  const usePretty = $('#pretty-json').is(':checked');
  $('#payload-json').text((usePretty && payloadPretty ? payloadPretty : payloadRaw) + (payloadSuffix || ''));
}

/* ---- Fetch payload ---- */

function fetchPatternConfig(policyId, done, fail) {
  $.getJSON('/api/pattern_config/' + encodeURIComponent(policyId))
    .done(function (res) {
      let obj = res && (res.condition_set ?? res);
      let raw, pretty, parsed = null;
      if (typeof obj === 'string') {
        raw = obj;
        try { parsed = JSON.parse(obj); } catch (_) { parsed = null; }
        try { pretty = JSON.stringify(parsed ?? JSON.parse(obj), null, 2); }
        catch (_) { pretty = prettyFromAny(obj); }
      } else {
        parsed = obj;
        raw = JSON.stringify(obj);
        pretty = JSON.stringify(obj, null, 2);
      }
      done(raw, pretty, parsed);
    })
    .fail(function (xhr) { fail('Pattern config not available (err ' + (xhr && xhr.status) + ')'); });
}

function fetchPayloadForEvent(eventId, done, fail) {
  $.getJSON('/api/payload/' + encodeURIComponent(eventId))
    .done(function (res) {
      if (res && res.full_payload != null) {
        let raw, pretty;
        if (typeof res.full_payload === 'string') { raw = res.full_payload; pretty = prettyFromAny(raw); }
        else { raw = JSON.stringify(res.full_payload); pretty = JSON.stringify(res.full_payload, null, 2); }
        return done(raw, pretty, "");
      }
      fetchPreview(eventId, done, fail);
    })
    .fail(function () { fetchPreview(eventId, done, fail); });
}

function fetchPreview(eventId, done, fail) {
  $.getJSON('/api/payload_preview/' + encodeURIComponent(eventId))
    .done(function (res) {
      if (!res || typeof res.text !== 'string') return fail('No payload data available for this event');
      const raw = res.text, pretty = prettyFromAny(raw);
      const suffix = res.truncated ? '\n\n[Preview truncated] Download full payload via /api/payload_download/' + encodeURIComponent(eventId) : '';
      done(raw, pretty, suffix);
    })
    .fail(function (xhr) { fail('No payload data available for this event (err ' + (xhr && xhr.status) + ')'); });
}

/* -------------------- Pattern hierarchy table -------------------- */

function initPatternTable() {
  // (Re)build a single "Pattern Hierarchy" column header
  if ($.fn.DataTable.isDataTable('#events-table')) {
    $('#events-table').DataTable().clear().destroy();
  }
  $('#events-table thead').empty().append('<tr><th>Pattern Hierarchy</th></tr>');
  $('#events-table tbody').empty();

  eventsTable = $('#events-table').DataTable({
    data: [],                           // client-side data only
    columns: [{
      data: 'html',
      orderable: false,
      className: 'tree-cell',
      render: function (data) {
        return data || (
          '<div class="ptree"><div class="node">' +
          '<span class="meta">Select a policy on the left to load its conditions.</span>' +
          '</div></div>'
        );
      }
    }],
    paging: false,                      // Disable paging for pattern view (usually just 1 entry)
    lengthChange: false,                // Hide the "Show entries" dropdown
    searching: false,
    ordering: false,
    autoWidth: false,
    responsive: false,
    deferRender: true,
    scrollY: '100px',
    scrollCollapse: true,
    scrollX: true
  });

  hookResizing($('#events-table'), 'patterns-tree', eventsTable);
  setDefaultWidths($('#events-table'), 'patterns-tree', { 0: 900 });
  eventsTable.one('draw.dt', () => requestAnimationFrame(layoutHeights));
}


function loadPatternDetailsForPolicy(policyId) {
  $('#selected-event').text('—');
  if (!eventsTable || !$.fn.DataTable.isDataTable('#events-table')) initPatternTable();

  function buildTree(parsed) {
    const { groups } = extractGroups(parsed);

    function esc(x) {
      return String(x == null ? '' : x).replace(/[&<>"]/g, s => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'
      }[s]));
    }

    function condText(c){
      try{
        if (c && c.field && c.operator) {
          const v = (c.value !== undefined) ? c.value : (c.anyOf || c.allOf || '');
          const vv = Array.isArray(v) ? v.join(', ') : String(v);
          return `${c.field} ${c.operator} ${vv}`.trim();
        }
        if (c && c.operator && Array.isArray(c.value)) {
          return `(${c.operator}) ${c.value.length} sub-conditions`;
        }
      } catch(_){}
      return JSON.stringify(c);
    }

    // Header: no operator shown
    let html = `<div class="ptree">
      <div class="node">
        <span class="badge op">Condition set</span>
      </div>
      <ul>`;

    (groups || []).forEach((g, i) => {
      html += `<li class="branch">
        <div class="node">
          <span class="caret" aria-label="toggle">▾</span>
          <span class="badge op">Group ${i + 1}</span>
        </div>
        <ul>
          <li>
            <div class="node">
              <span class="badge cond">Conditions</span>
              <span class="meta">${g.leaves && g.leaves.length ? esc(g.leaves.length + ' item(s)') : '—'}</span>
            </div>
            <ul>`;

      (g.leaves || []).forEach(c => {
        html += `<li>
          <div class="node">
            <span class="badge kv if">if</span>
            <span class="meta" style="font-weight:700;">${esc(condText(c))}</span>
          </div>
        </li>`;
      });

      html += `</ul></li>
          <li>
            <div class="node">
              <span class="badge act">Actions</span>
              <span class="meta">Resource Values</span>
            </div>
            <ul>`;

      (g.resVals || []).forEach(v => {
        html += `<li>
          <div class="node">
            <span class="badge kv val">value</span>
            <span class="meta">${esc(v)}</span>
          </div>
        </li>`;
      });

      html += `</ul></li>
        </ul>
      </li>`;
    });

    html += `</ul></div>`;

    // caret toggle
    setTimeout(() => {
      $('#events-table').off('click.ptree').on('click.ptree', '.ptree .caret', function(){
        const li = $(this).closest('li');
        li.toggleClass('collapsed');
        $(this).text(li.hasClass('collapsed') ? '▸' : '▾');
      });
    }, 0);

    return html;
  }

  fetchPatternConfig(policyId, function (_raw, _pretty, parsed) {
    // Card header: no " — op: ..."
    $('#events-container .card-header h2').text('Pattern Details');

    const { groups } = extractGroups(parsed);
    const treeHtml = buildTree(parsed);

    if (groups && groups.length) {
      eventsTable.clear().rows.add([{ html: treeHtml }]).draw();
    } else {
      eventsTable.clear().rows.add([{
        html: `<div class="ptree">
                 <div class="node"><span class="meta">No groups found under trigger.conditions.value.</span></div>
               </div>`
      }]).draw();
    }

    requestAnimationFrame(layoutHeights);
  }, function (msg) {
    if (eventsTable) eventsTable.clear().rows.add([{
      html: `<div class="ptree">
               <div class="node"><span class="meta">${(msg || 'Pattern config not available for this policy')}</span></div>
             </div>`
    }]).draw();
    $('#selected-event').text('—');
    $('#payload-json').text('No condition set available for this policy');
    requestAnimationFrame(layoutHeights);
  });
}


/* ---- Buttons/toggles ---- */

function setupResizeButtons() {
  $('#expand-policies, #collapse-policies, #expand-events, #collapse-events').remove();
  $('#toggle-details').off('click').on('click', function () {
    if (!eventsTable) return;
    const show = !eventsTable.column(4).visible();
    eventsTable.columns([4, 5]).visible(show, false);
    eventsTable.columns.adjust().draw(false);
    refreshResizers($('#events-table'), 'events-table');
    $(this).text(show ? 'Hide Details' : 'Show Details');
    requestAnimationFrame(layoutHeights);
  });
  
  // Add click handler for Extract Data button
  $('#extract-data').off('click').on('click', function() {
    if (!eventsTable) return;
    
    // Check if we're in patterns mode
    if (isPatternsMode()) {
      showNotification('Data extraction is not available in Patterns mode. Please switch to Temporal Grouping mode.', 'warning', 5000);
      return;
    }
    
    // Show a loading notification
    const $notification = showNotification('Preparing data for export...', 'info', 0);
    
    setTimeout(() => {
      try {
        // Get all data from the table
        const allData = eventsTable.data().toArray();
        
        // Define the 6 basic columns to export
        const basicColumns = [
          { key: 'event_id', header: 'Event ID' },
          { key: 'severity', header: 'Severity' },
          { key: 'payload_resource', header: 'Resource' },
          { key: 'summary', header: 'Summary' },
          { key: 'payload_details', header: 'Details' },
          { key: 'payload_type', header: 'Type' }
        ];
        
        // Helper function to properly escape CSV values
        function escapeCsvValue(val) {
          if (val === null || val === undefined) return '';
          val = String(val);
          // Always quote if contains comma, quote, newline, or looks like JSON
          if (val.includes(',') || val.includes('"') || val.includes('\n') || val.includes('{') || val.includes('[')) {
            return '"' + val.replace(/"/g, '""') + '"';
          }
          return val;
        }
        
        // Prepare CSV content with basic columns only
        const headers = basicColumns.map(col => col.header);
        let csvContent = headers.join(',') + '\n';
        
        // Add data rows - only basic columns
        allData.forEach(function(row) {
          const values = basicColumns.map(col => escapeCsvValue(row[col.key]));
          csvContent += values.join(',') + '\n';
        });
        
        // Create download link
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const policyId = selectedPolicyId || 'all';
        
        link.href = url;
        link.setAttribute('download', `events_data_${policyId}_${timestamp}.csv`);
        document.body.appendChild(link);
        
        // Trigger download and clean up
        link.click();
        setTimeout(() => {
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
          $notification.remove();
          
          // Add animation effect to the button
          $('#extract-data').addClass('extract-success');
          setTimeout(() => {
            $('#extract-data').removeClass('extract-success');
          }, 1000);
          
          showNotification('Data exported successfully!', 'success', 3000);
        }, 100);
      } catch (error) {
        console.error('Error exporting data:', error);
        $notification.remove();
        showNotification('Error exporting data: ' + error.message, 'error', 5000);
      }
    }, 100); // Small delay to allow notification to show
  });
  
  // Add click handler for Extract Details button with improved toggle functionality
  $('#extract-details').off('click').on('click', function() {
    if (!eventsTable) return;
    
    // Use the global jsonFields array that's defined at the top of the file
    // Make sure we're accessing the global variable
    
    // Check if we're in patterns mode
    if (isPatternsMode()) {
      showNotification('JSON field expansion is not available in Patterns mode. Please switch to Temporal Grouping mode.', 'warning', 5000);
      return;
    }
    
    // Make sure jsonFields is defined
    if (typeof jsonFields === 'undefined') {
      console.error('jsonFields is not defined');
      showNotification('Error: JSON fields configuration is missing. Please refresh the page and try again.', 'error', 5000);
      return;
    }
    
    // Check if we're already in expanded view and need to reset
    if ($(this).data('expanded')) {
      // Reset to normal view - hide the JSON field columns
      const $notification = showNotification('Collapsing JSON fields...', 'info', 0);
      
      try {
        // Hide all JSON field columns
        eventsTable.columns('.json-field-col').visible(false);
        
        // Show the original Details and Type columns
        eventsTable.column('.details-col').visible(true);
        eventsTable.column('.type-details-col').visible(true);
        
        // Update the button text back to normal
        $('#extract-details').text('Expand JSON Fields').removeClass('btn-warning').addClass('btn-outline-primary');
        $(this).data('expanded', false);
        
        // Remove expanded class from table
        $('#events-table').removeClass('expanded-json-view');
        $('body').removeClass('json-fields-expanded');
        
        // Adjust the table layout
        eventsTable.columns.adjust().draw(false);
        
        $notification.remove();
        showNotification('JSON fields collapsed successfully', 'success', 3000);
        
        // Adjust layout
        requestAnimationFrame(layoutHeights);
      } catch (error) {
        console.error('Error collapsing JSON fields:', error);
        $notification.remove();
        showNotification('Error collapsing JSON fields: ' + error.message, 'error', 5000);
      }
      
      return;
    }
    
    // Show a loading notification for expanding view
    const $notification = showNotification('Expanding JSON fields...', 'info', 0);
    
    try {
      console.log('Starting JSON field expansion with jsonFields:', jsonFields);
      // Ensure jsonFields is defined and accessible
      if (!window.jsonFields && typeof jsonFields === 'undefined') {
        throw new Error('JSON fields definition not found');
      }
      
      // We need to rebuild the table to properly show the JSON field columns
      // First, destroy the current table
      if ($.fn.DataTable.isDataTable('#events-table')) {
        $('#events-table').DataTable().destroy();
      }
      
      // Get the current data
      const currentData = eventsTable.data().toArray();
      
      // Process the data to extract JSON fields
      currentData.forEach(row => {
        const details = row.payload_details || '';
        if (details && typeof details === 'string') {
          try {
            // Try to parse the JSON data
            let jsonData = {};
            
            // Handle both single and double quotes
            if (details.trim().startsWith('{')) {
              try {
                // Try standard JSON parse first
                jsonData = JSON.parse(details);
              } catch (e) {
                // If that fails, try replacing single quotes with double quotes
                try {
                  // Replace single quotes with double quotes, but handle escaped quotes properly
                  const fixedJson = details
                    .replace(/'/g, '"')
                    .replace(/\\"/g, '\\"');
                  jsonData = JSON.parse(fixedJson);
                } catch (e2) {
                  console.warn('Failed to parse JSON:', e2);
                }
              }
            }
            
            // Add the JSON field values to the row data
            // Use the global jsonFields array
            (window.jsonFields || jsonFields).forEach(fieldObj => {
              const field = fieldObj.field;
              const value = jsonData[field];
              if (value !== undefined) {
                row[field] = value;
              }
            });
          } catch (e) {
            console.warn('Error processing JSON fields:', e);
          }
        }
      });
      
      // Create column definitions for the standard columns
      const standardColumns = [
        { data: 'event_id', title: 'Event ID' },
        { data: 'severity', title: 'Severity' },
        {
          data: 'payload_resource',
          title: 'Resource',
          render: function (data) {
            const s = data || '';
            const m = s.match(/node-([^-]+)/);
            return m ? m[0] : s;
          }
        },
        { data: 'summary', title: 'Summary' },
        {
          data: 'payload_details',
          title: 'Details',
          className: 'details-col d-none',
          visible: false
        },
        {
          data: 'payload_type',
          title: 'Type',
          className: 'type-details-col d-none',
          visible: false
        }
      ];
      
      // Create column definitions for the JSON fields
      // Make sure we're using the global jsonFields array
      const jsonFieldColumns = (window.jsonFields || jsonFields).map(fieldObj => {
        return {
          data: fieldObj.field,
          title: fieldObj.displayName,
          name: fieldObj.field,
          className: 'json-field-col',
          visible: true, // Explicitly set to visible
          orderable: false, // Disable sorting on JSON field columns
          defaultContent: '', // Provide default content for empty cells
          render: function(data, type, row) {
            if (data === undefined || data === null) return '';
            
            if (type === 'display') {
              if (typeof data === 'boolean') {
                return data ?
                  '<span class="badge bg-success">Yes</span>' :
                  '<span class="badge bg-secondary">No</span>';
              } else if (typeof data === 'number') {
                return data.toLocaleString();
              } else if (typeof data === 'string') {
                if (data.length > 50) {
                  return `<span title="${data.replace(/"/g, '"')}">${data.substring(0, 50)}...</span>`;
                }
                return data;
              } else if (data === null) {
                return '<span class="badge bg-light text-dark">null</span>';
              } else if (Array.isArray(data)) {
                return `<span class="badge bg-info">[Array: ${data.length}]</span>`;
              } else if (typeof data === 'object') {
                return `<span class="badge bg-info">{Object}</span>`;
              }
              return String(data);
            }
            
            return data;
          }
        };
      });
      
      // Combine all columns
      const allColumns = [...standardColumns, ...jsonFieldColumns];
      
      // Rebuild the table header to match the new columns
      const $thead = $('#events-table thead');
      $thead.empty();
      const $headerRow = $('<tr></tr>');
      allColumns.forEach(col => {
        const $th = $('<th></th>').text(col.title);
        if (col.className) {
          $th.addClass(col.className);
        }
        // Apply visibility style if column is set to not visible
        if (col.visible === false) {
          $th.css('display', 'none');
        }
        $headerRow.append($th);
      });
      $thead.append($headerRow);
      
      // Reinitialize the table with all columns
      eventsTable = $('#events-table').DataTable({
        data: currentData,
        columns: allColumns,
        order: [[0, 'asc']],
        pageLength: 25,
        lengthMenu: [[10,25,50,100,200,500,1000],[10,25,50,100,200,500,1000]],
        autoWidth: false,
        responsive: false,
        deferRender: true,
        searchDelay: 400,
        scrollY: '100px',
        scrollCollapse: true,
        scrollX: true
      });
      
      // Add event listener for row clicks
      $('#events-table tbody').off('click.eventsMode').on('click.eventsMode', 'tr', function () {
        const dt = $.fn.DataTable.isDataTable('#events-table') ? $('#events-table').DataTable() : null;
        if (!dt) return;
        const row = dt.row(this).data(); if (!row) return;
      
        const eventId = row.event_id;
        $('#selected-event').text(eventId);
        $('#events-table tbody tr').removeClass('selected-row');
        $(this).addClass('selected-row');
        $('#payload-json').text('Loading payload…');
      
        fetchPayloadForEvent(eventId, function (raw, pretty, suffix) {
          payloadRaw = raw; payloadPretty = pretty; payloadSuffix = suffix || "";
          renderPayload(); requestAnimationFrame(layoutHeights);
        }, function (msg) {
          payloadRaw = payloadPretty = null; payloadSuffix = "";
          $('#payload-json').text(msg || 'No payload data available for this event');
          requestAnimationFrame(layoutHeights);
        });
      });
      
      // Hide the original Details and Type columns
      eventsTable.column('.details-col').visible(false, false);
      eventsTable.column('.type-details-col').visible(false, false);
      
      // Show all JSON field columns - force redraw to ensure they're visible
      eventsTable.columns('.json-field-col').visible(true, false);
      
      // Force a complete redraw of the table
      eventsTable.columns.adjust().draw(true);
      
      // Add classes for styling
      $('#events-table').addClass('expanded-json-view');
      $('body').addClass('json-fields-expanded');
      
      // Adjust the table layout
      eventsTable.columns.adjust().draw(false);
      
      // Update the button text to indicate we can go back to normal view
      $('#extract-details').text('Collapse JSON Fields').removeClass('btn-outline-primary').addClass('btn-warning');
      $(this).data('expanded', true);
      
      $notification.remove();
      showNotification('JSON fields expanded successfully!', 'success', 3000);
      
      // Adjust layout
      requestAnimationFrame(layoutHeights);
    } catch (error) {
      console.error('Error expanding JSON fields:', error);
      console.log('jsonFields availability:', {
        isDefined: typeof jsonFields !== 'undefined',
        isArray: typeof jsonFields !== 'undefined' && Array.isArray(jsonFields),
        length: typeof jsonFields !== 'undefined' && Array.isArray(jsonFields) ? jsonFields.length : 'N/A'
      });
      $notification.remove();
      showNotification('Error expanding JSON fields: ' + error.message, 'error', 5000);
    }
  });
}

function setDeployCapHint(show, count = 0) {
  let $hint = $('#deploy-cap-hint');
  if (!$hint.length) {
    $hint = $(
      '<br><div id="deploy-cap-hint" class="alert alert-danger mt-2 mb-0 py-1 px-2" ' +
      'role="alert" style="font-size:.85rem;"></div>'
    );
    $('#policy-container .card-header').after($hint);
  }
  if (show) { $hint.text(`You selected ${count} policies; max is ${MAX_DEPLOY_SELECTION}. Deselect some to proceed.`).show(); }
  else { $hint.hide(); }
}

function isRowSelectable(row) {
  const idOk = row && row.policy_id;
  const deployed = resolveDeployedFlagFromRow(row);
  const id = idOk ? String(row.policy_id) : '';
  const effectiveDeployed = overrideDeployed.has(id) ? true : deployed;
  return idOk && !effectiveDeployed;
}

function clearAllSelectionsUI() {
  selectedPolicies.clear();
  selectedPolicyStates.clear();
  if (policyTable) {
    const nodes = policyTable.rows({ page: 'current' }).nodes();
    $(nodes).find('input.policy-select').prop('checked', false);
    $(nodes).removeClass('selected-row');
  }
  const $selectAll = $('#policy-select-all');
  if ($selectAll.length) { $selectAll.prop({ checked: false, indeterminate: false }); }
  updateActionButtons();
}

function ensurePolicyButtons() {
  const $hdr = $('#policy-container .card-header'); if (!$hdr.length) return;
  $hdr.addClass('d-flex justify-content-between align-items-center');
  let $ctr = $hdr.find('.policy-header-tools');
  if (!$ctr.length) { $ctr = $('<div class="policy-header-tools d-flex align-items-center gap-2 ms-auto"></div>'); $hdr.append($ctr); }

  if ($('#clear-deploy-cache').length === 0) {
    $ctr.prepend(
      '<button id="clear-deploy-cache" class="btn btn-sm btn-outline-secondary me-2" ' +
      'title="No cached deployed IDs" disabled>' +
      '<i class="bi bi-trash"></i> Clear Deploy Cache ' +
      '<span class="cache-badge count-badge" aria-hidden="true">0</span></button>'
    );
  }
  if ($('#deploy-selected-policies').length === 0) {
    $ctr.prepend(
      '<button id="deploy-selected-policies" class="btn btn-sm btn-primary me-2" ' +
      'title="Deploy selected undeployed policies" aria-live="polite" aria-disabled="true" disabled>' +
      '<i class="bi bi-rocket-takeoff"></i> Deploy Selected ' +
      '<span class="count-badge" aria-hidden="true">0</span></button>'
    );
  }
  if ($('#export-selected-policies').length) {
    $ctr.append($('#export-selected-policies').detach()
      .addClass('btn btn-sm btn-success')
      .attr('title', 'Export selected Policy IDs')
      .html('<i class="bi bi-download"></i> Export Selected <span class="count-badge" aria-hidden="true">0</span>'));
  } else {
    $ctr.append(
      '<button id="export-selected-policies" class="btn btn-sm btn-success" title="Export selected Policy IDs">' +
      '<i class="bi bi-download"></i> Export Selected <span class="count-badge" aria-hidden="true">0</span></button>'
    );
  }
}

function updateActionButtons() {
  const n = selectedPolicies.size || 0;
  const $deploy = $('#deploy-selected-policies');
  const $export = $('#export-selected-policies');

  $deploy.find('.count-badge').text(n);
  $export.find('.count-badge').text(n);

  const overCap = n > MAX_DEPLOY_SELECTION;
  const disableDeploy = (n === 0) || overCap;

  if (overCap && !__overCapNotified) {
    showNotification(`You selected ${n} policies; max per deploy is ${MAX_DEPLOY_SELECTION}.`, 'warning', 5000);
    __overCapNotified = true;
  }
  if (!overCap && __overCapNotified) __overCapNotified = false;

  setDeployCapHint(overCap, n);

  $deploy.prop('disabled', disableDeploy).attr('aria-disabled', disableDeploy)
    .attr('title', overCap
      ? `You selected ${n} policies. Max per deploy is ${MAX_DEPLOY_SELECTION}.`
      : (n === 0 ? 'Select at least one undeployed policy' : 'Deploy selected undeployed policies'));

  $export.prop('disabled', n === 0).attr('aria-disabled', n === 0);
}

function ensurePolicySearchBox() {
  const $wrap = $('#policy-table_wrapper'); if (!$wrap.length) return;
  const $length = $wrap.find('.dataTables_length'); if (!$length.length) return;
  $length.addClass('d-inline-flex align-items-center flex-nowrap me-3 mb-2');
  if ($wrap.find('#policy-search').length) return;
  const $box = $('<label class="policy-length-search d-inline-flex align-items-center flex-nowrap mb-2 ms-1"><span class="me-2">Search</span><input type="text" id="policy-search" class="form-control form-control-sm" placeholder="policies…" style="width:240px;"></label>');
  $box.insertAfter($length);
  let deb;
  $(document).off('input.policySearch').on('input.policySearch', '#policy-search', function () {
    const val = this.value; clearTimeout(deb);
    deb = setTimeout(function () { if (policyTable) policyTable.search(val).draw(); }, 250);
  });
}

function applyDefaultColumns() {
  const allMd = Array.from({ length: 12 }, (_, i) => `col-md-${i + 1}`).join(' ');
  $('#policy-container').removeClass(`d-none ${allMd} col-md-5-13 col-md-8-13`).addClass('col-md-5-13');
  $('#events-container').removeClass(`d-none ${allMd} col-md-5-13 col-md-8-13`).addClass('col-md-8-13');
  LEFT_SPLIT = (5 / 13); localStorage.setItem('leftSplit', LEFT_SPLIT.toFixed(4));
  requestAnimationFrame(() => { applyLeftRightWidths(); layoutHeights(); });
}

function getCurrentPageData() {
  try {
    var json = policyTable ? policyTable.ajax.json() : null;
    if (json && Array.isArray(json.data)) return json.data;
  } catch (e) { }
  return policyTable ? policyTable.rows({ page: 'current' }).data().toArray() : [];
}

/* -------------------- Resizable columns helpers -------------------- */

function getTables($bodyTable) {
  const $wrap = $bodyTable.closest('.dataTables_wrapper');
  let $headTable = $wrap.find('.dataTables_scrollHead table');
  if ($headTable.length === 0) $headTable = $bodyTable;
  return { $head: $headTable, $body: $bodyTable };
}
function ensureColGroup($tbl) {
  let $cg = $tbl.children('colgroup'); if ($cg.length === 0) { $cg = $('<colgroup/>'); $tbl.prepend($cg); }
  const need = $tbl.find('thead th').length;
  const have = $cg.children('col').length;
  if (have < need) { for (let i = have; i < need; i++) $cg.append('<col>'); }
  else if (have > need) $cg.children('col').slice(need).remove();
}
function applyColumnWidthTable($tbl, i, px) {
  const $col = $tbl.children('colgroup').children('col').eq(i);
  const css = { width: px + 'px', minWidth: px + 'px', maxWidth: px + 'px' };
  $col.css(css);
  const selH = 'thead tr>*:nth-child(' + (i + 1) + ')', selB = 'tbody tr>*:nth-child(' + (i + 1) + ')';
  $tbl.find(selH + ',' + selB).css(css);
}
function applyColumnWidthBoth($head, $body, i, px) { applyColumnWidthTable($head, i, px); applyColumnWidthTable($body, i, px); }
function saveWidths($body, id) {
  const arr = $body.children('colgroup').children('col').map(function () {
    const w = this.style.width; if (w) return w;
    const r = this.getBoundingClientRect(); return r && r.width ? Math.round(r.width) + 'px' : '';
  }).get();
  __columnWidths__[id] = arr;
}
function reapplySavedWidthsBoth($head, $body, id) {
  const arr = __columnWidths__[id] || [];
  for (let i = 0; i < arr.length; i++) { const w = arr[i]; if (w) applyColumnWidthBoth($head, $body, i, parseInt(w, 10)); }
}
function installHandles($head, $body, id) {
  $head.find('thead th').each(function () {
    const $th = $(this);
    if ($th.find('.resize-handle').length === 0) $('<div class="resize-handle"/>').appendTo($th);
  });
  let startX, startW, colIdx, $th;
  $head.find('.resize-handle').off('mousedown.colres').on('mousedown.colres', function (e) {
    e.preventDefault(); e.stopPropagation();
    $th = $(this).closest('th'); colIdx = $th.index(); startX = e.pageX; startW = $th.outerWidth();
    $('body').addClass('column-resizing');
    $(document).on('mousemove.colres', function (e2) {
      const w = Math.max(60, Math.round(startW + (e2.pageX - startX)));
      applyColumnWidthBoth($head, $body, colIdx, w);
    });
    $(document).one('mouseup.colres', function (upE) {
      upE.stopPropagation();
      $('body').removeClass('column-resizing');
      $(document).off('.colres');
      saveWidths($body, id);
      try { $('#events-table').DataTable().columns.adjust().draw(false); } catch (_) { }
    });
  });
}
function hookResizing($body, id, dt) {
  const t = getTables($body); ensureColGroup(t.$head); ensureColGroup(t.$body);
  reapplySavedWidthsBoth(t.$head, t.$body, id); installHandles(t.$head, t.$body, id);
  dt.on('draw.dt.__colpersist__ column-visibility.dt.__colpersist__', function () {
    const t2 = getTables($body); ensureColGroup(t2.$head); ensureColGroup(t2.$body);
    reapplySavedWidthsBoth(t2.$head, t2.$body, id); installHandles(t2.$head, t2.$body, id);
  });
}
function setDefaultWidths($body, id, defaultsPx) {
  const t = getTables($body); ensureColGroup(t.$head); ensureColGroup(t.$body);
  const saved = __columnWidths__[id] || [];
  for (const k in defaultsPx) { const i = parseInt(k, 10); if (!saved[i]) applyColumnWidthBoth(t.$head, t.$body, i, defaultsPx[k]); }
  saveWidths(t.$body, id);
}
function refreshResizers($body, id) {
  const t = getTables($body); ensureColGroup(t.$head); ensureColGroup(t.$body);
  reapplySavedWidthsBoth(t.$head, t.$body, id); installHandles(t.$head, t.$body, id);
}

/* ---- Main & Right resizers ---- */

function installMainResizer() {
  if ($('#main-resizer').length) return;
  const $policy = $('#policy-container'), $events = $('#events-container'); if (!$policy.length || !$events.length) return;
  const $row = $policy.closest('.row');
  $policy.after('<div id="main-resizer" class="h-resizer" aria-label="Drag to resize"></div>');
  $('#main-resizer').on('mousedown', function (e) {
    e.preventDefault();
    const startX = e.pageX, rowRect = $row[0].getBoundingClientRect();
    const total = rowRect.width - MAIN_RESIZER_THICKNESS;
    const polRect = $policy[0].getBoundingClientRect();
    const startLeftPx = polRect.width;
    $('body').addClass('resizing-x');
    $(document).on('mousemove.mainsplit', function (ev) {
      let newLeftPx = startLeftPx + (ev.pageX - startX);
      const minLeft = Math.max(160, total * 0.18), maxLeft = Math.min(total * 0.82, total - 220);
      newLeftPx = Math.max(minLeft, Math.min(maxLeft, newLeftPx));
      LEFT_SPLIT = newLeftPx / total; localStorage.setItem('leftSplit', LEFT_SPLIT.toFixed(4));
      applyLeftRightWidths(); requestAnimationFrame(layoutHeights);
    });
    $(document).one('mouseup.mainsplit', function () { $('body').removeClass('resizing-x'); $(document).off('.mainsplit'); });
  });
}
function applyLeftRightWidths() {
  const left = clamp(LEFT_SPLIT, 0.18, 0.82), leftPct = Math.round(left * 10000) / 100, rightPct = Math.round((1 - left) * 10000) / 100;
  $('#policy-container').css({ flex: '0 0 ' + leftPct + '%', maxWidth: leftPct + '%' });
  $('#events-container').css({ flex: '0 0 ' + rightPct + '%', maxWidth: rightPct + '%' });
}
function installRightResizer() {
  if ($('#right-resizer').length) return;
  const $eventsCard = $('#events-container .card').first(), $payload = $('#payload-container');
  if (!$eventsCard.length || !$payload.length) return;
  $('<div id="right-resizer" class="v-resizer" aria-label="Drag to resize"></div>').insertAfter($eventsCard);
  $('#right-resizer').on('mousedown', function (e) {
    e.preventDefault(); const startY = e.pageY; const metrics = measureRightColumn(); const startPayload = metrics.payloadTarget;
    $('body').addClass('resizing-y');
    $(document).on('mousemove.rightsplit', function (ev) {
      let newPayload = startPayload - (ev.pageY - startY);
      newPayload = Math.max(metrics.minPayload, Math.min(metrics.maxPayload, newPayload));
      RIGHT_SPLIT = newPayload / metrics.totalAvailClamped; localStorage.setItem('rightSplit', RIGHT_SPLIT.toFixed(4));
      layoutHeights();
    });
    $(document).one('mouseup.rightsplit', function () { $('body').removeClass('resizing-y'); $(document).off('.rightsplit'); });
  });
}
function measureRightColumn() {
  const $evtBody = $('#events-container .card:first .dataTables_scrollBody');
  if (!$evtBody.length) return { totalAvailClamped: 0, payloadTarget: 0, minPayload: 0, maxPayload: 0 };
  const $evtWrap = $evtBody.closest('.dataTables_wrapper');
  const evtTop = $evtBody.offset().top - $(window).scrollTop();
  const totalAvail = Math.max(240, window.innerHeight - evtTop - getDtFooterHeight($evtWrap) - 12);
  const totalAvailClamped = Math.max(200, totalAvail - RESIZER_THICKNESS);
  const minPayload = 100, minEvents = 140, maxPayload = totalAvailClamped - minEvents;
  const payloadTarget = clamp(Math.round(totalAvailClamped * RIGHT_SPLIT), minPayload, maxPayload);
  return { totalAvailClamped, payloadTarget, minPayload, maxPayload };
}
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

/* ---- Helpers ---- */

function isPatternsMode() { return currentGroup() === 'analytics.temporal-patterns'; }

function restoreSelectionAfterRefresh() {
  if (__suppressRestoreSelection) return;
  if (!policyTable) return;
  purgeUnselectableFromSelection();
  const nodes = policyTable.rows({ page: 'current' }).nodes();
  $(nodes).each(function () {
    const row = policyTable.row(this).data();
    if (!row) return;
    const id = String(row.policy_id || '');
    if (isRowSelectable(row) && selectedPolicies.has(id)) {
      $(this).addClass('selected-row');
      $(this).find('input.policy-select').prop('checked', true);
    }
  });
}

/* ---- Deploy progress toast ---- */
let __deployToast = null;
function showDeployProgress(total) {
  if (__deployToast) __deployToast.remove();
  __deployToast = $(`
    <div id="deploy-progress" style="
      position:fixed; right:16px; top:16px; z-index:9999;
      background:#fff; color:#212529; padding:12px 14px; border-radius:8px;
      box-shadow:0 8px 22px rgba(0,0,0,.15); width:320px; font-size:14px;
      border: 1px solid #e0e0e0;">
      <div style="font-weight:600; margin-bottom:6px;">Deploying policies…</div>
      <div id="dp-line" style="opacity:.9; margin-bottom:8px;"></div>
      <div style="height:8px; background:#eee; border-radius:4px; overflow:hidden;">
        <div id="dp-bar" style="height:100%; width:0%; background:#0d6efd; transition:width .25s;"></div>
      </div>
    </div>
  `).appendTo('body');
  updateDeployProgress({ done: 0, fail: 0, inflight: 0, total });
}
function updateDeployProgress({ done, fail, inflight, total }) {
  if (!__deployToast) return;
  const pct = total ? Math.min(100, Math.round(((done + fail) / total) * 100)) : 0;
  __deployToast.find('#dp-bar').css('width', pct + '%');
  __deployToast.find('#dp-line').text(
    `Done: ${done}  •  Failed: ${fail}  •  In-flight: ${inflight}  •  Total: ${total}  (${pct}%)`
  );
}
function hideDeployProgress() {
  if (!__deployToast) return;
  __deployToast.fadeOut(200, function () { $(this).remove(); __deployToast = null; });
}
/**
 * Deploys policies in batches with controlled concurrency
 *
 * @param {string[]} ids - Array of policy IDs to deploy
 * @param {Object} cfg - Configuration object with url, user, pass properties
 * @returns {Promise<{ok: string[], fail: Array<{id: string, status: string, error: string}>}>}
 */
async function deployPoliciesBatched(ids, cfg) {
  if (!ids || !Array.isArray(ids) || ids.length === 0) {
    return { ok: [], fail: [] };
  }

  // Validate configuration
  if (!cfg || typeof cfg !== 'object' || !cfg.url) {
    throw new Error('Invalid deployment configuration');
  }

  // Split IDs into manageable chunks based on configured batch size
  const chunks = [];
  for (let i = 0; i < ids.length; i += DEPLOY_BATCH_SIZE) {
    chunks.push(ids.slice(i, i + DEPLOY_BATCH_SIZE));
  }

  let ok = [], fail = [];
  let next = 0, inflight = 0;

  showDeployProgress(ids.length);

  const runOne = async () => {
    const batch = chunks[next++];
    if (!batch) return;
    
    inflight++;
    updateDeployProgress({ done: ok.length, fail: fail.length, inflight, total: ids.length });
    
    try {
      const res = await deployPolicies(batch, cfg, DEPLOY_CONCURRENCY_PER_BATCH, DEPLOY_REQUEST_TIMEOUT_MS);
      
      // Ensure we always get arrays back, even if API returns unexpected format
      const okIds = Array.isArray(res.ok) ? res.ok.map(String) : [];
      const failResults = Array.isArray(res.fail) ? res.fail : [];
      
      ok = ok.concat(okIds);
      fail = fail.concat(failResults);
    } catch (e) {
      console.error('Batch deployment error:', e);
      // Mark all IDs in this batch as failed with the error message
      fail = fail.concat(batch.map(id => ({
        id: String(id),
        status: 'client',
        error: String(e).substring(0, 200) // Limit error message length
      })));
    } finally {
      inflight--;
      updateDeployProgress({ done: ok.length, fail: fail.length, inflight, total: ids.length });
      
      // Continue with next batch if available
      if (next < chunks.length) return runOne();
    }
  };

  // Create workers limited by DEPLOY_MAX_INFLIGHT configuration
  const workerCount = Math.min(DEPLOY_MAX_INFLIGHT, chunks.length);
  const workers = Array.from({ length: workerCount }, () => runOne());
  
  try {
    await Promise.all(workers);
  } catch (e) {
    console.error('Deployment process error:', e);
    // This catch is just for unexpected Promise.all failures
    // Individual batch errors are already handled in runOne
  }

  hideDeployProgress();
  return { ok, fail, urls: {} }; // Ensure consistent return structure
}

/* ---- Pretty switch ---- */

function ensurePrettySwitch() {
  if ($('#pretty-json').length === 0) {
    const $hdr = $('#payload-container .card-header');
    if ($hdr.length) {
      $hdr.addClass('d-flex justify-content-between align-items-center');
      $hdr.append('<div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="pretty-json"><label class="form-check-label" for="pretty-json">Pretty JSON</label></div>');
    }
  }
  $('#pretty-json').prop('checked', false);
}

function ensureSelectAllInScrollHead() {
  const $row = $('#policy-container .dataTables_scrollHead thead tr'); if (!$row.length) return;
  const $th = $row.children('th').last();
  if ($th.find('#policy-select-all').length === 0) {
    $th.addClass('text-center').html('<input type="checkbox" id="policy-select-all" class="form-check-input" title="Select all on this page">');
  }
}

function ensureGroupSelector() {
  if ($('#group-selector').length) return;
  const $form = $('#registry-form'); if (!$form.length) return;

  // Get current mode from URL parameter
  const urlParams = new URLSearchParams(window.location.search);
  const currentMode = urlParams.get('mode') || 'temporal';
  
  // Create tabs instead of dropdown - clicking navigates to new URL (page reload)
  const html = `
    <div class="btn-group" role="group" aria-label="View mode tabs" style="margin-left:8px;">
      <a href="?mode=temporal" class="btn btn-sm ${currentMode === 'temporal' ? 'btn-primary' : 'btn-outline-primary'}"
         title="Temporal Grouping view">
        Temporal Grouping
      </a>
      <a href="?mode=patterns" class="btn btn-sm ${currentMode === 'patterns' ? 'btn-primary' : 'btn-outline-primary'}"
         title="Temporal Patterns view">
        Temporal Patterns
      </a>
    </div>
    <span class="ms-2 text-muted" style="font-size:0.8rem;">Click tabs to switch views (page will reload)</span>`;
  
  $('#events-search-wrap').length ? $(html).insertBefore('#events-search-wrap') : $form.append(html);
  
  // Store current mode in a hidden element for easy access by other functions
  $('<input type="hidden" id="group-selector" />').val(currentMode === 'patterns' ? 'analytics.temporal-patterns' : 'related-events').appendTo($form);
}

function currentGroup() {
  // Read from URL parameter, fallback to temporal grouping
  const urlParams = new URLSearchParams(window.location.search);
  const mode = urlParams.get('mode') || 'temporal';
  return mode === 'patterns' ? 'analytics.temporal-patterns' : 'related-events';
}

/**
 * Updates the loading progress indicator for large datasets
 * @param {string} type - Either 'policies' or 'events'
 * @param {Object} info - DataTables info object with recordsTotal, end, etc.
 * @param {boolean} [forceShow] - Whether to show the indicator regardless of dataset size
 */
function updateLoadingProgress(type, info, forceShow) {
  // DISABLED: In memory-only mode, all data is already loaded at startup
  // No need for progressive loading UI
  return;
  
  // Lower thresholds to show loading info more often
  const threshold = type === 'policies' ? 300 : 75;
  const $info = $(`#${type}-loading-info`);
  
  if (!info) return;
  
  // Get metadata from the response if available
  const metadata = info.metadata || {};
  const isLargeDataset = metadata.isLargeDataset || (info.recordsTotal > threshold);
  const totalItems = metadata.totalPolicies || info.recordsTotal || 0;
  const loadedItems = metadata.loadedPolicies || info.end || 0;
  
  if (isLargeDataset || forceShow) {
    if ($info.length === 0) {
      // Create enhanced loading info with progress bar and improved UI
      const html = `
        <div id="${type}-loading-info" class="alert alert-info py-2 px-3 mb-2" role="alert">
          <div class="d-flex align-items-center">
            <i class="bi bi-info-circle me-2"></i>
            <div class="flex-grow-1">
              <div class="d-flex justify-content-between align-items-center mb-1">
                <div>
                  <strong>Large dataset detected:</strong>
                  <span class="loaded-count">${loadedItems.toLocaleString()}</span> of
                  <span class="total-count">${totalItems.toLocaleString()}</span> ${type}
                </div>
                <div class="badge bg-info text-white processing-mode">${metadata.processingMode || 'standard'}</div>
              </div>
              <div class="loading-progress-bar">
                <div class="progress"></div>
              </div>
              <div class="loading-status d-flex justify-content-between">
                <small class="status-text">Loading...</small>
                <small class="percentage">0%</small>
              </div>
            </div>
            <div class="ms-3">
              <div class="btn-group">
                <button class="btn btn-sm btn-primary load-more-btn" data-type="${type}" data-increment="2">
                  <i class="bi bi-plus-circle me-1"></i> Load More
                </button>
                <button class="btn btn-sm btn-outline-primary load-all-btn" data-type="${type}">
                  <i class="bi bi-arrow-down-circle me-1"></i> Load All
                </button>
              </div>
            </div>
          </div>
        </div>`;
      const $loadingInfo = $(html).insertBefore(`#${type}-table_wrapper`);
      
      // Add click handler for the Load More button
      $loadingInfo.find('.load-more-btn').on('click', function() {
        const dataType = $(this).data('type');
        const table = dataType === 'policies' ? policyTable : eventsTable;
        const increment = parseInt($(this).data('increment')) || 2;
        
        if (table) {
          // Increase page size incrementally
          const currentPageSize = table.page.len();
          const newPageSize = Math.min(currentPageSize * increment, 1000);
          table.page.len(newPageSize).draw();
          
          // Update the increment factor for next click
          $(this).data('increment', Math.min(increment + 1, 4));
          
          showNotification(
            `Loading ${newPageSize} ${dataType} per page`,
            'info',
            3000,
            {
              text: 'Cancel',
              style: 'secondary',
              callback: function() {
                // Reset to smaller page size
                table.page.len(Math.max(25, currentPageSize / 2)).draw();
                showNotification(`Reduced page size to improve performance`, 'success', 2000);
              }
            }
          );
        }
      });
      
      // Add click handler for Load All button
      $loadingInfo.find('.load-all-btn').on('click', function() {
        const dataType = $(this).data('type');
        const table = dataType === 'policies' ? policyTable : eventsTable;
        
        if (table) {
          // Show warning for very large datasets
          if (totalItems > 3000) {
            showNotification(
              `Loading all ${totalItems.toLocaleString()} items may affect performance`,
              'warning',
              0,
              {
                text: 'Continue Anyway',
                style: 'danger',
                callback: function() {
                  // Set a very large page size to effectively load all
                  table.page.len(totalItems).draw();
                  showNotification(`Loading all ${totalItems.toLocaleString()} ${dataType}...`, 'info', 3000);
                  $(this).closest('.notification').remove();
                },
                keepOpen: true
              }
            );
          } else {
            // For smaller datasets, load all directly
            table.page.len(totalItems).draw();
            showNotification(`Loading all ${totalItems.toLocaleString()} ${dataType}...`, 'info', 3000);
          }
        }
      });
    }
    
    // Update the progress information with formatted numbers
    $info.find('.total-count').text(totalItems.toLocaleString());
    $info.find('.loaded-count').text(loadedItems.toLocaleString());
    
    // Update processing mode badge if available
    if (metadata.processingMode) {
      $info.find('.processing-mode').text(metadata.processingMode);
    }
    
    // Calculate and update progress percentage
    const percentage = totalItems > 0 ? Math.min(100, Math.round((loadedItems / totalItems) * 100)) : 0;
    $info.find('.progress').css('width', `${percentage}%`);
    $info.find('.percentage').text(`${percentage}%`);
    
    // Update status text based on progress
    if (percentage === 100) {
      $info.find('.status-text').text('Completed');
      // Hide buttons when fully loaded
      $info.find('.btn-group').fadeOut();
      // Hide after a delay when fully loaded
      setTimeout(() => $info.fadeOut(), 3000);
    } else if (percentage > 90) {
      $info.find('.status-text').text('Almost complete...');
    } else if (percentage > 75) {
      $info.find('.status-text').text('Loading final items...');
    } else if (percentage > 50) {
      $info.find('.status-text').text('More than halfway...');
    } else if (percentage > 25) {
      $info.find('.status-text').text('Processing...');
    } else {
      $info.find('.status-text').text('Loading initial data...');
    }
    
    // Show or hide the buttons based on progress
    if (percentage < 100) {
      $info.find('.btn-group').show();
    }
    
    $info.show();
  } else {
    $info.hide();
  }
}

/* -------------------- Deploy proxy call -------------------- */

/**
 * Sends a batch of policy IDs to the backend for deployment
 *
 * @param {string[]} ids - Array of policy IDs to deploy in this batch
 * @param {Object} cfg - Configuration with url, user, pass properties
 * @param {number} concurrency - Number of policies to process concurrently on backend
 * @param {number} clientTimeoutMs - Client-side timeout in milliseconds
 * @returns {Promise<{ok: string[], fail: Array<{id: string, status: string, error: string}>, urls: Object}>}
 */
async function deployPolicies(ids, cfg, concurrency = DEPLOY_CONCURRENCY_PER_BATCH, clientTimeoutMs = DEPLOY_REQUEST_TIMEOUT_MS) {
  // Input validation
  if (!ids || !Array.isArray(ids) || ids.length === 0) {
    return { ok: [], fail: [], urls: {} };
  }
  
  if (!cfg || typeof cfg !== 'object' || !cfg.url) {
    return {
      ok: [],
      fail: ids.map(id => ({ id: String(id), status: 'error', error: 'Invalid configuration' })),
      urls: {}
    };
  }

  // Set up timeout with AbortController
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort(new DOMException('timeout', 'AbortError'));
  }, clientTimeoutMs);

  try {
    const res = await fetch('/api/deploy_policies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: cfg.url,
        username: cfg.user || '',
        password: cfg.pass || '',
        ids: ids,
        verify_tls: false,
        timeout: Math.ceil(clientTimeoutMs / 2000), // Server timeout in seconds (half of client timeout)
        concurrency
      }),
      signal: controller.signal
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error('Backend deploy call failed: ' + res.status + (text ? ' ' + text : ''));
    }
    
    const data = await res.json();
    
    // Ensure consistent return structure
    return {
      ok: Array.isArray(data.ok) ? data.ok : [],
      fail: Array.isArray(data.fail) ? data.fail : [],
      urls: data.urls || {}
    };
  } catch (err) {
    console.error('Deploy API error:', err);
    
    if (err && err.name === 'AbortError') {
      const timeoutSecs = Math.round(clientTimeoutMs / 1000);
      return {
        ok: [],
        fail: ids.map(id => ({
          id: String(id),
          status: 'timeout',
          error: `Deploy request timed out after ${timeoutSecs}s`
        })),
        urls: {}
      };
    }
    
    // Convert all other errors to a structured response
    return {
      ok: [],
      fail: ids.map(id => ({
        id: String(id),
        status: 'error',
        error: String(err).substring(0, 200)
      })),
      urls: {}
    };
  } finally {
    clearTimeout(timer);
  }
}
