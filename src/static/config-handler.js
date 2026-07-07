//
// Copyright IBM Corp. 2024 - 2026
// SPDX-License-Identifier: Apache-2.0
//

/**
 * Configuration Handler
 * 
 * This script handles dynamic configuration loaded from /api/config endpoint.
 * It applies runtime settings like authentication visibility and session timeout.
 */

(function() {
    'use strict';
    
    // Wait for config to be loaded (from /api/config script tag)
    document.addEventListener('DOMContentLoaded', function() {
        const config = window.APP_CONFIG || {};
        
        // Handle logout button visibility based on authentication setting
        if (config.enableAuth) {
            const logoutContainer = document.getElementById('logout-container');
            if (logoutContainer) {
                logoutContainer.style.display = 'block';
            }
        }

        // Pre-fill registry URL / credentials from api_url_login.txt if present.
        // Only set fields that are currently empty so manual edits are never overwritten.
        if (config.registryUrl) {
            const urlField = document.getElementById('registry-url');
            if (urlField && !urlField.value) {
                urlField.value = config.registryUrl;
                // Persist to localStorage so app.js persistence logic picks it up too
                try { localStorage.setItem('registry_url', config.registryUrl); } catch(_) {}
            }
        }
        if (config.registryUsername) {
            const userField = document.getElementById('registry-username');
            if (userField && !userField.value) {
                userField.value = config.registryUsername;
                try { localStorage.setItem('registry_user', config.registryUsername); } catch(_) {}
            }
        }
        if (config.registryPassword) {
            const passField = document.getElementById('registry-password');
            if (passField && !passField.value) {
                passField.value = config.registryPassword;
                try { localStorage.setItem('registry_pass', config.registryPassword); } catch(_) {}
            }
        }

        // Log configuration (for debugging)
        if (config.debug) {
            console.log('App Configuration:', config);
        }
        
        // Store config globally for other scripts to use
        window.appConfig = config;
    });
})();

