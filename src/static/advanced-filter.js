/*
 * Copyright IBM Corp. 2024 - 2026
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Advanced Filter Module
 * Provides UI and logic for building complex filter queries
 */

// Global state for advanced filters
const AdvancedFilter = {
    conditions: [],
    logic: 'AND',
    isActive: false,
    activeFilterJSON: null,  // Store the active filter JSON globally
    timestampRangeHint: null,
    calendarState: {
        openForConditionId: null,
        viewYear: null,
        viewMonth: null
    },
    
    // Available columns and their data types
    columns: {
        'severity': { type: 'number', label: 'Severity' },
        'payload_resource': { type: 'string', label: 'Resource' },
        'summary': { type: 'string', label: 'Summary' },
        'payload_type': { type: 'number', label: 'Type' },
        'event_id': { type: 'string', label: 'Event ID' },
        'payload_details': { type: 'string', label: 'Details' },
        'timestamp': { type: 'timestamp', label: 'Timestamp' }
    },
    
    // Operators by data type
    operators: {
        number: [
            { value: '=', label: 'Equals (=)' },
            { value: '!=', label: 'Not Equals (≠)' },
            { value: '>', label: 'Greater Than (>)' },
            { value: '>=', label: 'Greater or Equal (≥)' },
            { value: '<', label: 'Less Than (<)' },
            { value: '<=', label: 'Less or Equal (≤)' }
        ],
        string: [
            { value: '=', label: 'Equals' },
            { value: '!=', label: 'Not Equals' },
            { value: 'contains', label: 'Contains' },
            { value: '!contains', label: 'Does Not Contain' },
            { value: 'starts', label: 'Starts With' },
            { value: 'ends', label: 'Ends With' }
        ],
        timestamp: [
            { value: '=', label: 'Equals' },
            { value: '!=', label: 'Not Equals' },
            { value: '>', label: 'After (>)' },
            { value: '>=', label: 'On or After (≥)' },
            { value: '<', label: 'Before (<)' },
            { value: '<=', label: 'On or Before (≤)' },
            { value: 'contains', label: 'Contains' }
        ]
    },
    
    /**
     * Initialize the advanced filter module
     */
    init: function() {
        console.log('[AdvancedFilter] Initializing...');
        this.createModal();
        this.attachEventListeners();
        this.loadTimestampRangeHint();
        console.log('[AdvancedFilter] Initialized successfully');
    },
    
    /**
     * Create the modal HTML structure
     */
    createModal: function() {
        const modalHTML = `
            <div id="advanced-filter-modal" class="advanced-filter-modal">
                <div class="advanced-filter-content">
                    <div class="advanced-filter-header">
                        <h2>🔍 Advanced Filter Builder</h2>
                        <button class="advanced-filter-close" id="close-advanced-filter">&times;</button>
                    </div>
                    <div class="advanced-filter-body">
                        <button class="add-condition-btn" id="add-condition-btn">+ Add Condition</button>
                        <div id="filter-conditions-container"></div>
                        <div class="filter-logic-selector" id="logic-selector-container" style="display: none;">
                            <label>Combine conditions with:</label>
                            <select id="filter-logic-select">
                                <option value="AND">AND (all must match)</option>
                                <option value="OR">OR (any can match)</option>
                            </select>
                        </div>
                        <div class="filter-summary">
                            <div id="timestamp-range-hint" class="filter-summary-text" style="margin-bottom: 10px; font-size: 12px; color: #525252; display: none;"></div>
                            <div class="filter-summary-title">Filter Preview <button id="refresh-preview-btn" style="font-size: 12px; padding: 2px 8px; margin-left: 8px;">🔄 Refresh</button></div>
                            <div class="filter-summary-text" id="filter-summary-text">
                                <span class="filter-summary-empty">No conditions added yet</span>
                            </div>
                        </div>
                    </div>
                    <div class="advanced-filter-footer">
                        <button class="clear-filters-btn" id="clear-filters-btn">Clear All</button>
                        <div style="display: flex; gap: 12px;">
                            <button class="cancel-btn" id="cancel-filter-btn">Cancel</button>
                            <button class="apply-filter-btn" id="apply-filter-btn">Apply Filter</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        console.log('[AdvancedFilter] Modal created');
    },
    
    /**
     * Attach event listeners to buttons and modal
     */
    attachEventListeners: function() {
        // Open modal button (will be added to the page)
        document.addEventListener('click', (e) => {
            console.log('[AdvancedFilter] Click detected on:', e.target.id, e.target.className);
            if (e.target.id === 'open-advanced-filter' || e.target.closest('#open-advanced-filter')) {
                console.log('[AdvancedFilter] Opening modal from button click');
                e.preventDefault();
                e.stopPropagation();
                
                // Check if button is disabled (Patterns mode)
                const btn = document.getElementById('open-advanced-filter');
                if (btn && btn.disabled) {
                    console.log('[AdvancedFilter] Button is disabled, not opening modal');
                    return;
                }
                
                this.openModal();
            }
            // Handle badge click - but not the X button
            if (e.target.id === 'filter-active-badge') {
                console.log('[AdvancedFilter] Opening modal from badge click');
                e.preventDefault();
                e.stopPropagation();
                this.openModal();
            }
            // Handle X button click on badge - clear filter
            if (e.target.id === 'clear-filter-badge-x') {
                console.log('[AdvancedFilter] Clearing filter from badge X button');
                e.preventDefault();
                e.stopPropagation();
                this.clearActiveFilter();
            }
        });
        
        // Close modal
        document.getElementById('close-advanced-filter').addEventListener('click', () => this.closeModal());
        document.getElementById('cancel-filter-btn').addEventListener('click', () => this.closeModal());
        
        // Click outside modal to close
        document.getElementById('advanced-filter-modal').addEventListener('click', (e) => {
            if (e.target.id === 'advanced-filter-modal') {
                this.closeCalendar();
                this.closeModal();
            }
        });

        document.addEventListener('click', (e) => {
            const calendar = document.querySelector('.custom-date-picker');
            if (!calendar || !this.calendarState.openForConditionId) {
                return;
            }

            if (e.target.closest('.custom-date-picker') ||
                e.target.closest('.date-picker-btn') ||
                e.target.closest('.condition-value')) {
                return;
            }

            this.closeCalendar();
        });
        
        // Add condition
        document.getElementById('add-condition-btn').addEventListener('click', () => this.addCondition());
        
        // Clear all
        document.getElementById('clear-filters-btn').addEventListener('click', () => this.clearAll());
        
        // Apply filter
        document.getElementById('apply-filter-btn').addEventListener('click', () => this.applyFilter());
        
        // Logic selector
        document.getElementById('filter-logic-select').addEventListener('change', (e) => {
            this.logic = e.target.value;
            this.updateSummary();
        });
        
        // Refresh preview button
        document.getElementById('refresh-preview-btn').addEventListener('click', (e) => {
            e.preventDefault();
            console.log('[AdvancedFilter] Manual refresh triggered');
            this.updateSummary();
        });
        
        console.log('[AdvancedFilter] Event listeners attached');
    },

    /**
     * Load timestamp range hint from runtime config
     */
    loadTimestampRangeHint: function() {
        try {
            const config = (typeof window !== 'undefined' && window.APP_CONFIG) ? window.APP_CONFIG : {};
            const hint = config && config.timestampRangeHint ? config.timestampRangeHint : null;
            this.timestampRangeHint = hint;
            this.renderTimestampRangeHint();
            console.log('[AdvancedFilter] Timestamp range hint loaded:', hint);
        } catch (err) {
            console.warn('[AdvancedFilter] Failed to load timestamp range hint:', err);
            this.timestampRangeHint = null;
            this.renderTimestampRangeHint();
        }
    },

    /**
     * Render timestamp range hint in the modal
     */
    renderTimestampRangeHint: function() {
        const hintEl = document.getElementById('timestamp-range-hint');
        if (!hintEl) {
            return;
        }

        const hint = this.timestampRangeHint;
        if (!hint || (!hint.min && !hint.max)) {
            hintEl.style.display = 'none';
            hintEl.textContent = '';
            return;
        }

        const minText = hint.min || 'unknown';
        const maxText = hint.max || 'unknown';
        hintEl.textContent = `Available timestamp range: ${minText} → ${maxText}`;
        hintEl.style.display = 'block';
    },
    
    /**
     * Open the filter modal
     */
    openModal: function() {
        console.log('[AdvancedFilter] Opening modal');
        document.getElementById('advanced-filter-modal').classList.add('show');
        
        // If no conditions, add one by default
        if (this.conditions.length === 0) {
            this.addCondition();
        }
    },
    
    /**
     * Close the filter modal
     */
    closeModal: function() {
        console.log('[AdvancedFilter] Closing modal');
        this.closeCalendar();
        document.getElementById('advanced-filter-modal').classList.remove('show');
    },
    
    /**
     * Add a new filter condition
     */
    addCondition: function() {
        const conditionId = 'condition-' + Date.now();
        const condition = {
            id: conditionId,
            column: 'severity',
            operator: '>',
            value: ''
        };
        
        this.conditions.push(condition);
        this.renderConditions();
        this.updateSummary();
        
        console.log('[AdvancedFilter] Added condition:', condition);
    },
    
    /**
     * Remove a condition
     */
    removeCondition: function(conditionId) {
        this.conditions = this.conditions.filter(c => c.id !== conditionId);
        this.renderConditions();
        this.updateSummary();
        
        console.log('[AdvancedFilter] Removed condition:', conditionId);
    },
    
    /**
     * Render all conditions
     */
    renderConditions: function() {
        const container = document.getElementById('filter-conditions-container');
        container.innerHTML = '';
        
        this.conditions.forEach((condition, index) => {
            const conditionHTML = this.createConditionHTML(condition, index);
            container.insertAdjacentHTML('beforeend', conditionHTML);
        });
        
        // Show/hide logic selector based on number of conditions
        const logicSelector = document.getElementById('logic-selector-container');
        logicSelector.style.display = this.conditions.length > 1 ? 'flex' : 'none';
        
        // Attach event listeners to new elements
        this.attachConditionListeners();
    },
    
    /**
     * Create HTML for a single condition
     */
    createConditionHTML: function(condition, index) {
        const columnType = this.columns[condition.column].type;
        const operators = this.operators[columnType];
        
        // Determine input type and placeholder based on column type
        let inputType = 'text';
        let placeholder = 'Enter value...';
        let inputStep = '';
        
        if (columnType === 'number') {
            inputType = 'number';
            placeholder = 'Enter number...';
        } else if (columnType === 'timestamp') {
            // Use text input with date format hint for better compatibility
            inputType = 'text';
            placeholder = 'YYYY-MM-DD HH:MM or YYYY-MM-DD';
        }
        
        return `
            <div class="filter-condition" data-condition-id="${condition.id}">
                <div class="filter-condition-field">
                    <label>Column</label>
                    <select class="condition-column" data-condition-id="${condition.id}">
                        ${Object.entries(this.columns).map(([key, col]) =>
                            `<option value="${key}" ${condition.column === key ? 'selected' : ''}>${col.label}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="filter-condition-field">
                    <label>Operator</label>
                    <select class="condition-operator" data-condition-id="${condition.id}">
                        ${operators.map(op =>
                            `<option value="${op.value}" ${condition.operator === op.value ? 'selected' : ''}>${op.label}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="filter-condition-field" style="${columnType === 'timestamp' ? 'flex: 2;' : ''}">
                    <label>Value</label>
                    <div class="timestamp-input-wrap" style="display: flex; gap: 4px; align-items: stretch; position: relative;">
                        <input type="${inputType}"
                               class="condition-value ${columnType === 'timestamp' ? 'condition-value-timestamp' : ''}"
                               data-condition-id="${condition.id}"
                               value="${columnType === 'timestamp' ? this.formatTimestampForDisplay(condition.value) : (condition.value || '')}"
                               placeholder="${placeholder}"
                               ${columnType === 'timestamp' ? 'readonly' : ''}
                               style="flex: 1; min-width: 0;">
                        ${columnType === 'timestamp' ? `
                            <button type="button"
                                    class="date-picker-btn"
                                    data-condition-id="${condition.id}"
                                    style="padding: 8px 12px; background: #0f62fe; color: white; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap; font-size: 14px;"
                                    title="Pick a date">
                                📅 Pick Date
                            </button>
                            ${this.createCalendarHTML(condition.id, condition.value)}
                        ` : ''}
                    </div>
                </div>
                <button class="remove-condition-btn" data-condition-id="${condition.id}">Remove</button>
            </div>
        `;
    },
    
    /**
     * Format stored timestamp value for display
     */
    formatTimestampForDisplay: function(value) {
        if (!value) {
            return '';
        }
        const text = String(value).trim();
        const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
        return match ? match[1] : text;
    },

    /**
     * Normalize date value back to filter timestamp format
     */
    normalizeTimestampValue: function(value) {
        if (!value) {
            return '';
        }
        return `${value} 00:00:00`;
    },

    /**
     * Parse timestamp value into year/month/day parts
     */
    parseTimestampParts: function(value) {
        const fallback = new Date();
        const text = this.formatTimestampForDisplay(value);
        const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (match) {
            return {
                year: parseInt(match[1], 10),
                month: parseInt(match[2], 10) - 1,
                day: parseInt(match[3], 10)
            };
        }
        return {
            year: fallback.getFullYear(),
            month: fallback.getMonth(),
            day: fallback.getDate()
        };
    },

    /**
     * Create custom calendar HTML for timestamp fields
     */
    createCalendarHTML: function(conditionId, value) {
        const isOpen = this.calendarState.openForConditionId === conditionId;
        const selected = this.parseTimestampParts(value);
        const viewYear = isOpen && this.calendarState.viewYear !== null ? this.calendarState.viewYear : selected.year;
        const viewMonth = isOpen && this.calendarState.viewMonth !== null ? this.calendarState.viewMonth : selected.month;
        const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                            'August', 'September', 'October', 'November', 'December'];
        const weekdayNames = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
        const firstDay = new Date(viewYear, viewMonth, 1).getDay();
        const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
        const prevMonthDays = new Date(viewYear, viewMonth, 0).getDate();
        const minYear = this.timestampRangeHint && this.timestampRangeHint.min ? this.parseTimestampParts(this.timestampRangeHint.min).year : viewYear - 5;
        const maxYear = this.timestampRangeHint && this.timestampRangeHint.max ? this.parseTimestampParts(this.timestampRangeHint.max).year : viewYear + 5;

        let daysHtml = '';
        for (let i = 0; i < firstDay; i++) {
            const dayNum = prevMonthDays - firstDay + i + 1;
            daysHtml += `<button type="button" class="calendar-day other-month" disabled>${dayNum}</button>`;
        }

        for (let day = 1; day <= daysInMonth; day++) {
            const isSelected = selected.year === viewYear && selected.month === viewMonth && selected.day === day;
            daysHtml += `
                <button type="button"
                        class="calendar-day ${isSelected ? 'selected' : ''}"
                        data-condition-id="${conditionId}"
                        data-day="${day}">
                    ${day}
                </button>
            `;
        }

        while ((firstDay + daysInMonth + (daysHtml.match(/calendar-day/g) || []).length - daysInMonth) % 7 !== 0) {
            const trailingCount = 42 - (firstDay + daysInMonth);
            if (trailingCount <= 0) {
                break;
            }
            const currentButtons = (daysHtml.match(/calendar-day/g) || []).length;
            if (currentButtons >= 42) {
                break;
            }
            const nextDay = currentButtons - (firstDay + daysInMonth) + 1;
            daysHtml += `<button type="button" class="calendar-day other-month" disabled>${nextDay}</button>`;
        }

        return `
            <div class="custom-date-picker ${isOpen ? 'show' : ''}" data-condition-id="${conditionId}">
                <div class="calendar-header">
                    <button type="button" class="calendar-nav-btn" data-condition-id="${conditionId}" data-direction="-1">◀</button>
                    <div class="calendar-month-year">
                        <select class="calendar-month-select" data-condition-id="${conditionId}">
                            ${monthNames.map((name, index) => `<option value="${index}" ${index === viewMonth ? 'selected' : ''}>${name}</option>`).join('')}
                        </select>
                        <select class="calendar-year-select" data-condition-id="${conditionId}">
                            ${Array.from({ length: Math.max(1, maxYear - minYear + 1) }, (_, i) => minYear + i)
                                .map(year => `<option value="${year}" ${year === viewYear ? 'selected' : ''}>${year}</option>`).join('')}
                        </select>
                    </div>
                    <button type="button" class="calendar-nav-btn" data-condition-id="${conditionId}" data-direction="1">▶</button>
                </div>
                <div class="calendar-weekdays">
                    ${weekdayNames.map(name => `<span>${name}</span>`).join('')}
                </div>
                <div class="calendar-grid">
                    ${daysHtml}
                </div>
                <div class="calendar-footer">
                    <button type="button" class="calendar-action-btn" data-action="today" data-condition-id="${conditionId}">Today</button>
                    <button type="button" class="calendar-action-btn" data-action="clear" data-condition-id="${conditionId}">Clear</button>
                </div>
            </div>
        `;
    },

    closeCalendar: function() {
        if (!this.calendarState.openForConditionId) {
            return;
        }
        this.calendarState.openForConditionId = null;
        this.calendarState.viewYear = null;
        this.calendarState.viewMonth = null;
        this.renderConditions();
    },

    openCalendar: function(conditionId) {
        const condition = this.conditions.find(c => c.id === conditionId);
        const parts = this.parseTimestampParts(condition ? condition.value : '');
        this.calendarState.openForConditionId = conditionId;
        this.calendarState.viewYear = parts.year;
        this.calendarState.viewMonth = parts.month;
        this.renderConditions();
    },

    updateCalendarView: function(conditionId, year, month) {
        this.calendarState.openForConditionId = conditionId;
        this.calendarState.viewYear = year;
        this.calendarState.viewMonth = month;
        this.renderConditions();
    },

    selectCalendarDate: function(conditionId, year, month, day) {
        const condition = this.conditions.find(c => c.id === conditionId);
        const input = document.querySelector(`.condition-value[data-condition-id="${conditionId}"]`);
        if (!condition) {
            return;
        }

        const dateValue = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const normalized = this.normalizeTimestampValue(dateValue);
        condition.value = normalized;
        if (input) {
            input.value = dateValue;
        }
        this.closeCalendar();
        this.updateSummary();
    },

    /**
     * Attach event listeners to condition elements
     */
    attachConditionListeners: function() {
        // Column change
        document.querySelectorAll('.condition-column').forEach(select => {
            select.addEventListener('change', (e) => {
                const conditionId = e.target.dataset.conditionId;
                const condition = this.conditions.find(c => c.id === conditionId);
                if (condition) {
                    const oldColumn = condition.column;
                    condition.column = e.target.value;
                    // Reset operator to first available for new column type
                    const columnType = this.columns[condition.column].type;
                    condition.operator = this.operators[columnType][0].value;
                    // Only reset value if changing between incompatible types
                    // Keep value if user already entered something
                    if (!condition.value) {
                        condition.value = '';
                    }
                    console.log(`[AdvancedFilter] Column changed from ${oldColumn} to ${condition.column}, value: "${condition.value}"`);
                    this.renderConditions();
                    this.updateSummary();
                }
            });
        });
        
        // Operator change
        document.querySelectorAll('.condition-operator').forEach(select => {
            select.addEventListener('change', (e) => {
                const conditionId = e.target.dataset.conditionId;
                const condition = this.conditions.find(c => c.id === conditionId);
                if (condition) {
                    condition.operator = e.target.value;
                    this.updateSummary();
                }
            });
        });
        
        // Value change
        document.querySelectorAll('.condition-value').forEach(input => {
            const updateValue = (e) => {
                const conditionId = e.target.dataset.conditionId;
                const condition = this.conditions.find(c => c.id === conditionId);
                if (!condition) {
                    return;
                }

                const columnType = this.columns[condition.column].type;
                const newValue = columnType === 'timestamp'
                    ? this.normalizeTimestampValue(e.target.value)
                    : e.target.value;

                condition.value = newValue;
                console.log(`[AdvancedFilter] Value updated for ${conditionId}: "${newValue}"`);
                this.updateSummary();
            };

            if (input.classList.contains('condition-value-timestamp')) {
                input.addEventListener('click', (e) => {
                    const conditionId = e.target.dataset.conditionId;
                    if (this.calendarState.openForConditionId === conditionId) {
                        this.closeCalendar();
                    } else {
                        this.openCalendar(conditionId);
                    }
                });
                return;
            }
            
            input.addEventListener('input', updateValue);
            input.addEventListener('change', updateValue);
        });
        
        // Remove button
        document.querySelectorAll('.remove-condition-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const conditionId = e.target.dataset.conditionId;
                this.removeCondition(conditionId);
            });
        });
        
        // Date picker button - toggles custom in-modal calendar
        document.querySelectorAll('.date-picker-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const conditionId = e.currentTarget.dataset.conditionId;
                if (this.calendarState.openForConditionId === conditionId) {
                    this.closeCalendar();
                } else {
                    this.openCalendar(conditionId);
                }
            });
        });

        document.querySelectorAll('.calendar-nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const conditionId = e.currentTarget.dataset.conditionId;
                const direction = parseInt(e.currentTarget.dataset.direction, 10);
                let year = this.calendarState.viewYear;
                let month = this.calendarState.viewMonth + direction;
                if (month < 0) {
                    month = 11;
                    year -= 1;
                } else if (month > 11) {
                    month = 0;
                    year += 1;
                }
                this.updateCalendarView(conditionId, year, month);
            });
        });

        document.querySelectorAll('.calendar-month-select').forEach(select => {
            select.addEventListener('change', (e) => {
                const conditionId = e.target.dataset.conditionId;
                this.updateCalendarView(conditionId, this.calendarState.viewYear, parseInt(e.target.value, 10));
            });
        });

        document.querySelectorAll('.calendar-year-select').forEach(select => {
            select.addEventListener('change', (e) => {
                const conditionId = e.target.dataset.conditionId;
                this.updateCalendarView(conditionId, parseInt(e.target.value, 10), this.calendarState.viewMonth);
            });
        });

        document.querySelectorAll('.calendar-day[data-day]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const conditionId = e.currentTarget.dataset.conditionId;
                const day = parseInt(e.currentTarget.dataset.day, 10);
                this.selectCalendarDate(conditionId, this.calendarState.viewYear, this.calendarState.viewMonth, day);
            });
        });

        document.querySelectorAll('.calendar-action-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const conditionId = e.currentTarget.dataset.conditionId;
                const action = e.currentTarget.dataset.action;
                if (action === 'today') {
                    const now = new Date();
                    this.selectCalendarDate(conditionId, now.getFullYear(), now.getMonth(), now.getDate());
                } else if (action === 'clear') {
                    const condition = this.conditions.find(c => c.id === conditionId);
                    if (condition) {
                        condition.value = '';
                    }
                    this.closeCalendar();
                    this.updateSummary();
                }
            });
        });
    },
    
    /**
     * Update the filter summary display
     */
    updateSummary: function() {
        const summaryEl = document.getElementById('filter-summary-text');
        
        if (this.conditions.length === 0) {
            summaryEl.innerHTML = '<span class="filter-summary-empty">No conditions added yet</span>';
            return;
        }
        
        // Sync values from DOM before displaying summary
        document.querySelectorAll('.condition-value').forEach(input => {
            const conditionId = input.dataset.conditionId;
            const condition = this.conditions.find(c => c.id === conditionId);
            if (!condition || !input.value) {
                return;
            }

            if (this.columns[condition.column].type === 'timestamp') {
                condition.value = this.normalizeTimestampValue(input.value);
            } else {
                condition.value = input.value;
            }
        });
        
        const parts = this.conditions.map(c => {
            const columnLabel = this.columns[c.column].label;
            const operatorLabel = this.getOperatorLabel(c.column, c.operator);
            let value = c.value || '(empty)';
            
            // For timestamp, just show the value as-is without timezone conversion
            // The value is already in the format the user entered (YYYY-MM-DD HH:MM:SS)
            
            return `${columnLabel} ${operatorLabel} '${value}'`;
        });
        
        summaryEl.textContent = parts.join(` ${this.logic} `);
    },
    
    /**
     * Get operator label for display
     */
    getOperatorLabel: function(column, operatorValue) {
        const columnType = this.columns[column].type;
        const operator = this.operators[columnType].find(op => op.value === operatorValue);
        return operator ? operator.label : operatorValue;
    },
    
    /**
     * Clear all conditions
     */
    clearAll: function() {
        console.log('[AdvancedFilter] Clearing all conditions');
        this.conditions = [];
        this.logic = 'AND';
        document.getElementById('filter-logic-select').value = 'AND';
        this.renderConditions();
        this.updateSummary();
    },
    
    /**
     * Apply the filter
     */
    applyFilter: function() {
        console.log('[AdvancedFilter] Applying filter');
        
        // IMPORTANT: Sync values from DOM inputs before validation
        document.querySelectorAll('.condition-value').forEach(input => {
            const conditionId = input.dataset.conditionId;
            const condition = this.conditions.find(c => c.id === conditionId);
            if (!condition) {
                return;
            }

            const syncedValue = this.columns[condition.column].type === 'timestamp'
                ? this.normalizeTimestampValue(input.value)
                : input.value;

            console.log(`[AdvancedFilter] DEBUG - Input element:`, {
                conditionId: conditionId,
                type: input.type,
                value: input.value,
                innerHTML: input.outerHTML.substring(0, 200)
            });

            condition.value = syncedValue;
            console.log(`[AdvancedFilter] Synced value for ${conditionId}: "${syncedValue}"`);
        });
        
        console.log('[AdvancedFilter] Current conditions after sync:', JSON.stringify(this.conditions, null, 2));
        
        // Check if no conditions - warn and ask to continue
        if (this.conditions.length === 0) {
            const proceed = confirm('No filter conditions are defined. This will clear any active filter and show all data.\n\nDo you want to continue?');
            if (!proceed) {
                return;
            }
            // User confirmed - clear the active filter
            this.clearActiveFilter();
            this.closeModal();
            return;
        }
        
        // Validate conditions - check for empty or whitespace-only values
        const invalidConditions = this.conditions.filter(c => !c.value || c.value.trim() === '');
        if (invalidConditions.length > 0) {
            console.log('[AdvancedFilter] Invalid conditions found:', invalidConditions);
            alert('Please fill in all condition values before applying the filter.');
            return;
        }
        
        // Build filter object
        const filterObj = {
            conditions: this.conditions.map(c => ({
                column: c.column,
                operator: c.operator,
                value: c.value
            })),
            logic: this.logic
        };
        
        console.log('[AdvancedFilter] Filter object:', filterObj);
        
        // Set active state
        this.isActive = true;
        
        // Store filter JSON globally so both tables can access it
        const filterJSON = JSON.stringify(filterObj);
        this.activeFilterJSON = filterJSON;
        console.log('[AdvancedFilter] Filter stored globally:', filterJSON);
        
        // Update badge
        this.updateBadge();
        
        // Close modal
        this.closeModal();
        
        // Clear global search box to avoid confusion with advanced filter
        const globalSearchBox = document.getElementById('events-global-search');
        if (globalSearchBox) {
            globalSearchBox.value = '';
            console.log('[AdvancedFilter] Cleared global search box');
        }
        
        // Clear policy selection to show all events with filter
        // This mimics the global search behavior
        if (typeof selectedPolicyId !== 'undefined') {
            selectedPolicyId = null;
            if (typeof $ !== 'undefined') {
                $('#selected-policy').text('None');
                $('#policy-table tbody tr').removeClass('selected-row');
            }
        }
        
        // Store filter in eventsTable settings if it exists
        if (typeof eventsTable !== 'undefined' && eventsTable) {
            eventsTable.settings()[0].advancedFilter = filterJSON;
            console.log('[AdvancedFilter] Filter also stored in eventsTable settings');
        }
        
        // Reload policyTable to find policies with matching events
        // This is the key - just like global search, we reload the policy table
        if (typeof policyTable !== 'undefined' && policyTable) {
            console.log('[AdvancedFilter] Reloading policyTable to find matching policies');
            policyTable.ajax.reload(null, true);
        }
        
        // Initialize or reload events table
        if (typeof eventsTable !== 'undefined' && eventsTable) {
            console.log('[AdvancedFilter] Reloading eventsTable');
            eventsTable.ajax.reload(null, false);
        } else if (typeof initEvents === 'function') {
            console.log('[AdvancedFilter] Initializing eventsTable');
            initEvents();
        }
    },
    
    /**
     * Clear the active filter
     */
    clearActiveFilter: function() {
        console.log('[AdvancedFilter] Clearing active filter');
        this.isActive = false;
        this.activeFilterJSON = null;
        this.clearAll();
        this.updateBadge();
        
        // Clear filter from DataTables
        if (typeof eventsTable !== 'undefined' && eventsTable) {
            delete eventsTable.settings()[0].advancedFilter;
            eventsTable.ajax.reload();
            console.log('[AdvancedFilter] eventsTable reloaded without filter');
        }
        
        // Reload policyTable to show all policies again
        if (typeof policyTable !== 'undefined' && policyTable) {
            policyTable.ajax.reload(null, true);
            console.log('[AdvancedFilter] policyTable reloaded without filter');
        }
    },
    
    /**
     * Update the active filter badge
     */
    updateBadge: function() {
        let badge = document.getElementById('filter-active-badge');
        
        if (this.isActive && this.conditions.length > 0) {
            if (!badge) {
                // Create badge next to the global search box
                const searchWrap = document.querySelector('#events-search-wrap');
                if (searchWrap) {
                    const badgeHTML = `
                        <span id="filter-active-badge" class="filter-active-badge" title="Click to edit filter">
                            Filtered (${this.conditions.length} condition${this.conditions.length > 1 ? 's' : ''})
                            <span id="clear-filter-badge-x" style="margin-left: 8px; padding: 4px 8px; cursor: pointer; font-size: 16px; font-weight: bold; border-radius: 3px; display: inline-block; line-height: 1;" title="Clear filter">✕</span>
                        </span>
                    `;
                    searchWrap.insertAdjacentHTML('beforeend', badgeHTML);
                }
            } else {
                // Update badge
                badge.innerHTML = `
                    Filtered (${this.conditions.length} condition${this.conditions.length > 1 ? 's' : ''})
                    <span id="clear-filter-badge-x" style="margin-left: 8px; padding: 4px 8px; cursor: pointer; font-size: 16px; font-weight: bold; border-radius: 3px; display: inline-block; line-height: 1;" title="Clear filter">✕</span>
                `;
            }
        } else {
            // Remove badge
            if (badge) {
                badge.remove();
            }
        }
    }
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AdvancedFilter.init());
} else {
    AdvancedFilter.init();
}

