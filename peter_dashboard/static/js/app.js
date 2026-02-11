/**
 * Peter Dashboard - Main Application
 *
 * A lightweight SPA framework for the Peter Dashboard.
 *
 * Structure:
 * 1. State Management
 * 2. API Client
 * 3. WebSocket Manager
 * 4. Router
 * 5. Components
 * 6. Views
 * 7. Utilities
 * 8. Initialization
 */

// =============================================================================
// 1. STATE MANAGEMENT
// =============================================================================

/**
 * Simple reactive state management with event-based updates.
 */
const State = {
  _data: {
    // System status
    services: {},
    jobs: [],
    skills: [],

    // UI state
    sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true',
    currentRoute: '/',
    selectedItem: null,
    detailPanelOpen: false,

    // Connection state
    wsConnected: false,
    lastUpdate: null,

    // Filters
    jobFilter: 'all',
    logLevel: 'all',
    searchQuery: '',

    // Sorting
    sortKey: null,
    sortDirection: 'asc',

    // Pagination
    currentPage: 1,
    pageSize: 25,
  },

  get(key) {
    return this._data[key];
  },

  set(updates) {
    const changedKeys = [];
    for (const [key, value] of Object.entries(updates)) {
      if (this._data[key] !== value) {
        this._data[key] = value;
        changedKeys.push(key);
      }
    }
    if (changedKeys.length > 0) {
      document.dispatchEvent(new CustomEvent('stateChange', {
        detail: { changes: changedKeys, state: this._data }
      }));
    }
  },

  subscribe(callback) {
    document.addEventListener('stateChange', (e) => callback(e.detail));
  },
};


// =============================================================================
// UTILITIES (moved before first use)
// =============================================================================

/**
 * General utilities
 */
const Utils = {
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  throttle(func, limit) {
    let inThrottle;
    return function(...args) {
      if (!inThrottle) {
        func.apply(this, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  },

  renderMarkdown(content) {
    let html = Utils.escapeHtml(content);
    html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>').replace(/^## (.*)$/gm, '<h2>$1</h2>').replace(/^# (.*)$/gm, '<h1>$1</h1>');
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\*([^*]+)\*/g, '<em>$1</em>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    html = html.replace(/^\s*[-*+]\s+(.*)$/gm, '<li>$1</li>').replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    html = html.replace(/\n\n/g, '</p><p>'); html = '<p>' + html + '</p>';
    return html;
  },

  formatRelativeTime(isoTimestamp) {
    if (!isoTimestamp) return 'Never';
    const date = new Date(isoTimestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  },
};


// =============================================================================
// 2. API CLIENT
// =============================================================================

/**
 * API client with timeout, retry, and error handling.
 */
const API = {
  baseUrl: '',
  timeout: 10000,

  async request(path, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error = new Error(`API Error: ${response.status} ${response.statusText}`);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error('Request timeout');
      }
      throw error;
    }
  },

  get(path) {
    return this.request(path, { method: 'GET' });
  },

  post(path, data) {
    return this.request(path, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  put(path, data) {
    return this.request(path, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  delete(path) {
    return this.request(path, { method: 'DELETE' });
  },
};


// =============================================================================
// 3. WEBSOCKET MANAGER
// =============================================================================

/**
 * WebSocket manager with automatic reconnection and message handling.
 */
const WebSocketManager = {
  ws: null,
  reconnectAttempts: 0,
  maxReconnectAttempts: 5,
  reconnectDelay: 1000,
  handlers: {},

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        State.set({ wsConnected: true });
        Toast.success('Connected', 'Real-time updates enabled');
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleMessage(data);
        } catch (error) {
          console.error('[WS] Parse error:', error);
        }
      };

      this.ws.onclose = (event) => {
        console.log('[WS] Disconnected:', event.code, event.reason);
        State.set({ wsConnected: false });
        this.scheduleReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error);
      };
    } catch (error) {
      console.error('[WS] Connection failed:', error);
      this.scheduleReconnect();
    }
  },

  handleMessage(msg) {
    const { type, payload, data } = msg;
    const content = payload || data || {};  // Support both payload and data
    State.set({ lastUpdate: new Date().toISOString() });

    // Call registered handlers
    if (this.handlers[type]) {
      this.handlers[type].forEach(handler => handler(content));
    }

    // Handle common message types
    switch (type) {
      case 'status':
        if (content.services) {
          State.set({ services: content.services });
        }
        break;
      case 'job_complete':
      case 'job_start':
        this.refreshJobs();
        break;
      case 'error_alert':
        Toast.error('Error', content.message || 'An error occurred');
        break;
    }
  },

  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      Toast.error('Connection Lost', 'Unable to connect to server. Please refresh the page.');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);

    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    setTimeout(() => this.connect(), delay);
  },

  send(type, payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, payload }));
    }
  },

  on(type, handler) {
    if (!this.handlers[type]) {
      this.handlers[type] = [];
    }
    this.handlers[type].push(handler);
  },

  off(type, handler) {
    if (this.handlers[type]) {
      this.handlers[type] = this.handlers[type].filter(h => h !== handler);
    }
  },

  async refreshJobs() {
    try {
      const data = await API.get('/api/jobs');
      if (data && data.jobs) {
        State.set({ jobs: data.jobs });
      }
    } catch (error) {
      console.error('Failed to refresh jobs:', error);
    }
  },
};


// =============================================================================
// 4. ROUTER
// =============================================================================

/**
 * Simple hash-based router for SPA navigation.
 */
const Router = {
  routes: {},
  currentView: null,

  register(path, view) {
    this.routes[path] = view;
  },

  navigate(path) {
    window.location.hash = path;
  },

  getCurrentPath() {
    return window.location.hash.slice(1) || '/';
  },

  handleRoute() {
    const path = this.getCurrentPath();
    const view = this.routes[path] || this.routes['/'];

    if (view) {
      State.set({ currentRoute: path, detailPanelOpen: false, selectedItem: null });

      // Update active state in sidebar
      document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.toggle('active', item.dataset.route === path);
      });

      // Render view
      const content = document.getElementById('main-content');
      if (content && typeof view.render === 'function') {
        content.innerHTML = '';
        view.render(content);

        // Update header title
        const headerTitle = document.querySelector('.header-title');
        if (headerTitle && view.title) {
          headerTitle.textContent = view.title;
        }

        this.currentView = view;
      }
    }
  },

  init() {
    window.addEventListener('hashchange', () => this.handleRoute());
    this.handleRoute();
  },
};


// =============================================================================
// 5. COMPONENTS
// =============================================================================

/**
 * Reusable UI components
 */
const Components = {
  /**
   * Create a stats card element
   */
  statsCard({ icon, value, label, trend, variant = 'info' }) {
    const trendClass = trend > 0 ? 'positive' : trend < 0 ? 'negative' : 'neutral';
    const trendIcon = trend > 0 ? Icons.trendUp : trend < 0 ? Icons.trendDown : '';
    const trendText = trend !== undefined ? `${trend > 0 ? '+' : ''}${trend}%` : '';

    return `
      <div class="stats-card">
        <div class="stats-card-icon ${variant}">${icon}</div>
        <div class="stats-card-content">
          <div class="stats-card-value">${value}</div>
          <div class="stats-card-label">${label}</div>
          ${trend !== undefined ? `
            <div class="stats-card-trend ${trendClass}">
              ${trendIcon} ${trendText}
            </div>
          ` : ''}
        </div>
      </div>
    `;
  },

  /**
   * Create a status badge element
   */
  statusBadge(status) {
    const statusMap = {
      up: 'running',
      down: 'error',
      running: 'running',
      paused: 'paused',
      error: 'error',
      idle: 'idle',
      pending: 'pending',
      healthy: 'running',
      degraded: 'paused',
    };
    const badgeClass = statusMap[status?.toLowerCase()] || 'idle';
    const label = status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown';
    return `<span class="status-badge ${badgeClass}">${label}</span>`;
  },

  /**
   * Create a service card element
   */
  serviceCard({ name, status, details = [], actions = [] }) {
    return `
      <div class="service-card">
        <div class="service-card-header">
          <span class="service-card-name">${name}</span>
          ${this.statusBadge(status)}
        </div>
        <div class="service-card-details">
          ${details.map(d => `
            <div class="service-card-detail">
              <span class="text-muted">${d.label}:</span>
              <span>${d.value}</span>
            </div>
          `).join('')}
        </div>
        ${actions.length ? `
          <div class="service-card-actions">
            ${actions.map(a => `
              <button class="btn btn-sm ${a.variant || 'btn-secondary'}"
                      onclick="${a.onclick}"
                      ${a.disabled ? 'disabled' : ''}>
                ${a.label}
              </button>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  },

  /**
   * Create a data table element
   */
  dataTable({ id, columns, data, searchable = true, paginated = true, onRowClick }) {
    const tableId = id || `table-${Date.now()}`;

    return `
      <div class="data-table-container" id="${tableId}">
        ${searchable ? `
          <div class="data-table-header">
            <div class="data-table-search">
              <span class="data-table-search-icon">${Icons.search}</span>
              <input type="text" placeholder="Search..."
                     oninput="DataTable.search('${tableId}', this.value)">
            </div>
            <div class="data-table-filters">
              <select class="form-select" onchange="DataTable.filter('${tableId}', this.value)">
                <option value="all">All Status</option>
                <option value="running">Running</option>
                <option value="idle">Idle</option>
                <option value="paused">Paused</option>
                <option value="error">Error</option>
              </select>
            </div>
          </div>
        ` : ''}
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                ${columns.map(col => {
                  const sortKey = State.get('sortKey');
                  const sortDir = State.get('sortDirection');
                  const isActive = col.sortable && sortKey === col.key;
                  const arrow = isActive ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '';
                  return `
                  <th class="${col.sortable ? 'sortable' : ''} ${isActive ? 'sort-active' : ''}"
                      ${col.sortable ? `onclick="DataTable.sort('${tableId}', '${col.key}')"` : ''}
                      style="${col.width ? `width: ${col.width}` : ''}; ${col.sortable ? 'cursor: pointer; user-select: none;' : ''}">
                    ${col.label}${arrow}
                    ${col.sortable && !isActive ? `<span class="sort-icon">${Icons.sort}</span>` : ''}
                  </th>`;
                }).join('')}
              </tr>
            </thead>
            <tbody>
              ${data.length ? data.map((row, idx) => `
                <tr class="${onRowClick ? 'clickable' : ''}"
                    ${onRowClick ? `onclick="${onRowClick}(${idx})"` : ''}
                    data-index="${idx}">
                  ${columns.map(col => `
                    <td>${col.render ? col.render(row[col.key], row) : (row[col.key] ?? '-')}</td>
                  `).join('')}
                </tr>
              `).join('') : `
                <tr>
                  <td colspan="${columns.length}">
                    <div class="empty-state">
                      <div class="empty-state-icon">${Icons.inbox}</div>
                      <div class="empty-state-title">No data</div>
                      <div class="empty-state-description">No items to display</div>
                    </div>
                  </td>
                </tr>
              `}
            </tbody>
          </table>
        </div>
        ${paginated && data.length > 0 ? `
          <div class="data-table-footer">
            <div class="data-table-info">
              Showing ${Math.min(data.length, State.get('pageSize'))} of ${data.length} items
            </div>
            <div class="data-table-pagination">
              <button onclick="DataTable.prevPage('${tableId}')">${Icons.chevronLeft}</button>
              <button class="active">1</button>
              <button onclick="DataTable.nextPage('${tableId}')">${Icons.chevronRight}</button>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  },

  /**
   * Create a loading skeleton
   */
  skeleton(type = 'text', count = 3) {
    if (type === 'card') {
      return `<div class="stats-card skeleton" style="height: 100px;"></div>`;
    }
    if (type === 'table') {
      return `
        <div class="data-table-container">
          ${Array(count).fill().map(() => `
            <div class="skeleton skeleton-text" style="margin: 16px;"></div>
          `).join('')}
        </div>
      `;
    }
    return Array(count).fill().map(() => `
      <div class="skeleton skeleton-text"></div>
    `).join('');
  },

  /**
   * Create tabs component
   */
  tabs({ id, tabs, activeTab = 0 }) {
    return `
      <div class="tabs" id="${id}">
        <div class="tab-list">
          ${tabs.map((tab, idx) => `
            <button class="tab ${idx === activeTab ? 'active' : ''}"
                    onclick="Tabs.switch('${id}', ${idx})">
              ${tab.label}
              ${tab.badge ? `<span class="tab-badge">${tab.badge}</span>` : ''}
            </button>
          `).join('')}
        </div>
        ${tabs.map((tab, idx) => `
          <div class="tab-panel ${idx === activeTab ? 'active' : ''}" id="${id}-panel-${idx}">
            ${tab.content || ''}
          </div>
        `).join('')}
      </div>
    `;
  },

  /**
   * Create a log entry
   */
  logEntry({ timestamp, level, source, message }) {
    return `
      <div class="log-entry">
        <span class="log-timestamp">${Format.time(timestamp)}</span>
        <span class="log-level ${level}">[${level.toUpperCase()}]</span>
        <span class="log-source">[${source}]</span>
        <span class="log-message">${Utils.escapeHtml(message)}</span>
      </div>
    `;
  },
};


/**
 * DataTable helper functions
 */
const DataTable = {
  search(tableId, query) {
    State.set({ searchQuery: query.toLowerCase() });
    // Re-render current view with filtered data
    if (Router.currentView && Router.currentView.refresh) {
      Router.currentView.refresh();
    }
  },

  filter(tableId, value) {
    State.set({ jobFilter: value });
    if (Router.currentView && Router.currentView.refresh) {
      Router.currentView.refresh();
    }
  },

  sort(tableId, key) {
    const currentKey = State.get('sortKey');
    const currentDir = State.get('sortDirection');
    // Toggle direction if same key, otherwise default to ascending
    const direction = (currentKey === key && currentDir === 'asc') ? 'desc' : 'asc';
    State.set({ sortKey: key, sortDirection: direction });
    if (Router.currentView && Router.currentView.refresh) {
      Router.currentView.refresh();
    }
  },

  applySorting(data) {
    const key = State.get('sortKey');
    const dir = State.get('sortDirection');
    if (!key) return data;

    return [...data].sort((a, b) => {
      let aVal = a[key];
      let bVal = b[key];

      // Handle nulls/undefined — push to bottom
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      // Numeric comparison for known numeric fields
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return dir === 'asc' ? aVal - bVal : bVal - aVal;
      }

      // String comparison (case-insensitive)
      aVal = String(aVal).toLowerCase();
      bVal = String(bVal).toLowerCase();
      if (aVal < bVal) return dir === 'asc' ? -1 : 1;
      if (aVal > bVal) return dir === 'asc' ? 1 : -1;
      return 0;
    });
  },

  prevPage(tableId) {
    const current = State.get('currentPage');
    if (current > 1) {
      State.set({ currentPage: current - 1 });
    }
  },

  nextPage(tableId) {
    State.set({ currentPage: State.get('currentPage') + 1 });
  },
};


/**
 * Tabs helper functions
 */
const Tabs = {
  switch(tabsId, index) {
    const tabs = document.getElementById(tabsId);
    if (!tabs) return;

    // Update tab buttons
    tabs.querySelectorAll('.tab').forEach((tab, idx) => {
      tab.classList.toggle('active', idx === index);
    });

    // Update tab panels
    tabs.querySelectorAll('.tab-panel').forEach((panel, idx) => {
      panel.classList.toggle('active', idx === index);
    });
  },
};


/**
 * Toast notification system
 */
const Toast = {
  container: null,

  init() {
    this.container = document.createElement('div');
    this.container.className = 'toast-container';
    document.body.appendChild(this.container);
  },

  show(type, title, message, duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${Icons[type] || Icons.info}</span>
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close" onclick="this.parentElement.remove()">
        ${Icons.x}
      </button>
    `;

    this.container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
      }, duration);
    }
  },

  success(title, message) { this.show('success', title, message); },
  error(title, message) { this.show('error', title, message, 8000); },
  warning(title, message) { this.show('warning', title, message); },
  info(title, message) { this.show('info', title, message); },
};


/**
 * Modal system
 */
const Modal = {
  backdrop: null,
  container: null,

  init() {
    this.backdrop = document.createElement('div');
    this.backdrop.className = 'modal-backdrop';
    this.backdrop.onclick = () => this.close();
    document.body.appendChild(this.backdrop);
  },

  open({ title, content, footer, size = 'md' }) {
    // Remove any existing modal
    const existing = document.querySelector('.modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = `modal modal-${size}`;
    modal.innerHTML = `
      <div class="modal-header">
        <h3 class="modal-title">${title}</h3>
        <button class="modal-close" onclick="Modal.close()">${Icons.x}</button>
      </div>
      <div class="modal-body">${content}</div>
      ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
    `;
    modal.onclick = (e) => e.stopPropagation();

    document.body.appendChild(modal);
    this.backdrop.classList.add('open');

    // Trigger animation
    requestAnimationFrame(() => {
      modal.classList.add('open');
    });
  },

  close() {
    const modal = document.querySelector('.modal');
    if (modal) {
      modal.classList.remove('open');
      this.backdrop.classList.remove('open');
      setTimeout(() => modal.remove(), 200);
    }
  },
};


/**
 * Detail Panel
 */
const DetailPanel = {
  open(content) {
    const panel = document.getElementById('detail-panel');
    const panelContent = document.getElementById('detail-panel-content');

    if (panel && panelContent) {
      panelContent.innerHTML = content;
      panel.classList.add('open');
      State.set({ detailPanelOpen: true });
    }
  },

  close() {
    const panel = document.getElementById('detail-panel');
    if (panel) {
      panel.classList.remove('open');
      State.set({ detailPanelOpen: false, selectedItem: null });
    }
  },

  update(content) {
    const panelContent = document.getElementById('detail-panel-content');
    if (panelContent) {
      panelContent.innerHTML = content;
    }
  },
};


// =============================================================================
// ICONS (moved before views that use them)
// =============================================================================

/**
 * Icon definitions (inline SVGs for performance)
 */
const Icons = {
  // Navigation
  home: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
  list: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
  server: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
  book: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',
  code: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
  fileText: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
  folder: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>',
  brain: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2A2.5 2.5 0 0112 4.5v15a2.5 2.5 0 01-4.96.44 2.5 2.5 0 01-2.96-3.08 3 3 0 01-.34-5.58 2.5 2.5 0 011.32-4.24A2.5 2.5 0 019.5 2z"/><path d="M14.5 2A2.5 2.5 0 0012 4.5v15a2.5 2.5 0 004.96.44 2.5 2.5 0 002.96-3.08 3 3 0 00.34-5.58 2.5 2.5 0 00-1.32-4.24A2.5 2.5 0 0014.5 2z"/></svg>',
  settings: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
  bell: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>',

  // Actions
  refresh: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
  refreshCw: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>',
  play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
  square: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
  save: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  x: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  menu: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
  chevronLeft: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>',
  chevronRight: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>',
  panelLeft: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>',
  panelRight: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="15" y1="3" x2="15" y2="21"/></svg>',

  // Status
  activity: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  checkCircle: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  alertCircle: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  clock: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  trendUp: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
  trendDown: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>',

  // UI
  sort: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 3 18 9"/><polyline points="6 15 12 21 18 15"/></svg>',
  inbox: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>',
  file: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
  terminal: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
  box: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
  messageCircle: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>',
  zap: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  star: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  plus: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  toggleOn: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="1" y="6" width="22" height="12" rx="6" fill="#22c55e"/><circle cx="17" cy="12" r="4" fill="white"/></svg>',
  toggleOff: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="1" y="6" width="22" height="12" rx="6" fill="#94a3b8"/><circle cx="7" cy="12" r="4" fill="white"/></svg>',

  // Toast types
  success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0d9488" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
};


// =============================================================================
// 6. VIEWS
// =============================================================================

/**
 * Dashboard View - Overview and quick stats
 */
const DashboardView = {
  title: 'Dashboard',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="grid grid-cols-4 gap-md mb-lg" id="stats-cards">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        <div class="grid grid-cols-3 gap-md mb-lg" id="services-grid">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        <div class="card mb-lg">
          <div class="card-header">
            <h3 class="card-title">Recent Activity</h3>
            <button class="btn btn-sm btn-secondary" onclick="DashboardView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
          <div class="card-body" id="recent-activity">
            ${Components.skeleton('table', 5)}
          </div>
        </div>

        <div class="grid grid-cols-2 gap-md">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Upcoming Jobs</h3>
            </div>
            <div class="card-body" id="upcoming-jobs">
              ${Components.skeleton('text', 5)}
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Recent Errors</h3>
            </div>
            <div class="card-body" id="recent-errors">
              ${Components.skeleton('text', 3)}
            </div>
          </div>
        </div>
      </div>
    `;

    await this.loadData();
  },

  async loadData() {
    try {
      // Load system status
      const status = await API.get('/api/status');
      this.renderStats(status);
      this.renderServices(status.services);

      // Load jobs for activity
      try {
        const jobsData = await API.get('/api/jobs');
        if (jobsData && jobsData.jobs) {
          State.set({ jobs: jobsData.jobs });
          this.renderActivity(jobsData.jobs);
          this.renderUpcoming(jobsData.jobs);
        }
      } catch (error) {
        console.log('Jobs API not available:', error);
        document.getElementById('recent-activity').innerHTML = '<p class="text-muted p-md">Job data not available</p>';
        document.getElementById('upcoming-jobs').innerHTML = '<p class="text-muted">Job data not available</p>';
      }

      // Render recent errors placeholder
      document.getElementById('recent-errors').innerHTML = `
        <div class="text-muted text-center p-md">No recent errors</div>
      `;

    } catch (error) {
      console.error('Failed to load dashboard data:', error);
      Toast.error('Error', 'Failed to load dashboard data');
    }
  },

  renderStats(status) {
    const services = status.services || {};
    const runningServices = Object.values(services).filter(s => s.status === 'up').length;
    const totalServices = Object.keys(services).length;

    const statsHtml = `
      ${Components.statsCard({
        icon: Icons.activity,
        value: `${runningServices}/${totalServices}`,
        label: 'Services Running',
        variant: runningServices === totalServices ? 'success' : 'warning'
      })}
      ${Components.statsCard({
        icon: Icons.checkCircle,
        value: '95.6%',
        label: 'Success Rate (24h)',
        trend: 2.3,
        variant: 'success'
      })}
      ${Components.statsCard({
        icon: Icons.alertCircle,
        value: '0',
        label: 'Errors Today',
        variant: 'info'
      })}
      ${Components.statsCard({
        icon: Icons.clock,
        value: '99.9%',
        label: 'Uptime',
        variant: 'info'
      })}
    `;

    document.getElementById('stats-cards').innerHTML = statsHtml;
  },

  renderServices(services) {
    const serviceCards = Object.entries(services).map(([key, svc]) => {
      const details = [];
      if (svc.port) details.push({ label: 'Port', value: svc.port });
      if (svc.pid) details.push({ label: 'PID', value: svc.pid });
      if (svc.latency_ms) details.push({ label: 'Latency', value: `${svc.latency_ms}ms` });
      if (svc.last_restart) details.push({ label: 'Last Restart', value: Utils.formatRelativeTime(svc.last_restart) });

      return Components.serviceCard({
        name: Format.serviceName(key),
        status: svc.status,
        details,
        actions: [
          { label: 'Restart', onclick: `App.restartService('${key}')` },
        ]
      });
    }).join('');

    document.getElementById('services-grid').innerHTML = serviceCards;
  },

  renderActivity(jobs) {
    // Show recent runs (mock data for now since we don't have actual run history)
    const recentRuns = jobs.slice(0, 5).map(job => ({
      time: job.last_run || new Date().toISOString(),
      name: job.name || job.id,
      status: job.last_success !== false ? 'running' : 'error',
      duration: job.last_duration_ms ? `${Math.round(job.last_duration_ms / 1000)}s` : '-'
    }));

    const html = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Job</th>
            <th>Status</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          ${recentRuns.map(run => `
            <tr>
              <td>${Format.time(run.time)}</td>
              <td>${run.name}</td>
              <td>${Components.statusBadge(run.status === 'running' ? 'running' : 'error')}</td>
              <td>${run.duration}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;

    document.getElementById('recent-activity').innerHTML = html;
  },

  renderUpcoming(jobs) {
    const upcoming = jobs
      .filter(j => j.next_run && j.enabled !== false)
      .sort((a, b) => new Date(a.next_run) - new Date(b.next_run))
      .slice(0, 5);

    const html = upcoming.length ? upcoming.map(job => `
      <div class="flex justify-between items-center py-sm border-b">
        <span>${job.name || job.id}</span>
        <span class="text-muted text-sm">${Format.relativeTime(job.next_run)}</span>
      </div>
    `).join('') : '<p class="text-muted">No upcoming jobs</p>';

    document.getElementById('upcoming-jobs').innerHTML = html;
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Dashboard data updated');
  }
};


/**
 * Jobs View - Calendar + List with schedule parsing
 */
const JobsView = {
  title: 'Jobs',
  jobs: [],

  // Day mapping for schedule parsing
  DAY_MAP: {
    sun: 0, sunday: 0,
    mon: 1, monday: 1,
    tue: 2, tuesday: 2,
    wed: 3, wednesday: 3,
    thu: 4, thursday: 4,
    fri: 5, friday: 5,
    sat: 6, saturday: 6,
  },
  DAY_NAMES: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Scheduled Jobs</h2>
            <p class="text-secondary">Peter's automated routines</p>
          </div>
          <button class="btn btn-primary" onclick="JobsView.refresh()">
            ${Icons.refresh} Refresh
          </button>
        </div>
        <div id="jobs-content">
          ${Components.skeleton('table', 10)}
        </div>
      </div>
    `;
    await this.loadData();
  },

  async loadData() {
    try {
      const data = await API.get('/api/jobs');
      this.jobs = data.jobs || [];
      State.set({ jobs: this.jobs });
      this.renderTabs();
    } catch (error) {
      console.error('Failed to load jobs:', error);
      document.getElementById('jobs-content').innerHTML = `
        <div class="card">
          <div class="empty-state">
            <div class="empty-state-icon">${Icons.alertCircle}</div>
            <div class="empty-state-title">Failed to load jobs</div>
            <div class="empty-state-description">${error.message}</div>
            <button class="btn btn-primary mt-md" onclick="JobsView.loadData()">Retry</button>
          </div>
        </div>
      `;
    }
  },

  renderTabs() {
    const activeTab = State.get('jobsActiveTab') || 0;
    document.getElementById('jobs-content').innerHTML = Components.tabs({
      id: 'jobs-tabs',
      tabs: [
        { label: 'Calendar', content: this.buildCalendar() },
        { label: 'List', content: this.buildTable() },
        { label: 'History', content: this.buildHistoryPlaceholder() },
      ],
      activeTab,
    });

    // Override tab switch to persist state and lazy-load history
    const origSwitch = Tabs.switch.bind(Tabs);
    const tabBtns = document.querySelectorAll('#jobs-tabs .tab');
    tabBtns.forEach((btn, idx) => {
      btn.onclick = () => {
        State.set({ jobsActiveTab: idx });
        origSwitch('jobs-tabs', idx);
        if (idx === 2) this.loadHistory();
      };
    });

    // If History tab is active on load, fetch data
    if (activeTab === 2) this.loadHistory();
  },

  // ── Schedule parsing helpers ───────────────────────────────────────

  isIntervalJob(schedule) {
    if (!schedule) return false;
    return /^(hourly|half-hourly)/i.test(schedule.replace(/ UK$/, '').trim());
  },

  getIntervalLabel(schedule) {
    const clean = (schedule || '').replace(/ UK$/, '').trim();
    if (/^half-hourly/i.test(clean)) return 'Every 30 min';
    if (/^hourly/i.test(clean)) return 'Every hour';
    return clean;
  },

  isMonthlyJob(schedule) {
    if (!schedule) return false;
    return /^1st /i.test((schedule || '').replace(/ UK$/, '').trim());
  },

  /** Expand "Mon-Wed,Fri" into [1,2,3,5] */
  expandDaySpec(spec) {
    const parts = spec.toLowerCase().split(',');
    const days = new Set();
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed.includes('-')) {
        const [startStr, endStr] = trimmed.split('-');
        const start = this.DAY_MAP[startStr.trim()];
        const end = this.DAY_MAP[endStr.trim()];
        if (start != null && end != null) {
          for (let d = start; d !== (end + 1) % 7; d = (d + 1) % 7) {
            days.add(d);
            if (days.size > 7) break;
          }
          days.add(end);
        }
      } else if (this.DAY_MAP[trimmed] != null) {
        days.add(this.DAY_MAP[trimmed]);
      }
    }
    return [...days].sort((a, b) => a - b);
  },

  /** Get array of weekday numbers (0=Sun..6=Sat) a job runs on */
  getJobDays(schedule) {
    if (!schedule) return [0,1,2,3,4,5,6];
    const clean = schedule.replace(/ UK$/, '').trim();

    // Interval jobs go in the "Always Running" section
    if (this.isIntervalJob(schedule)) return [];

    // Monthly jobs — don't show in weekly grid
    if (/^1st /i.test(clean)) return [];

    // Try to match "DaySpec HH:MM" pattern
    const dayTimeMatch = clean.match(/^([a-zA-Z,\-]+)\s+\d/);
    if (dayTimeMatch) {
      return this.expandDaySpec(dayTimeMatch[1]);
    }

    // Simple time or multi-time (e.g. "07:00" or "09:02,11:02,13:02") → every day
    return [0,1,2,3,4,5,6];
  },

  /** Extract display time from schedule string */
  getJobTime(schedule) {
    if (!schedule) return '';
    const clean = schedule.replace(/ UK$/, '').trim();
    // Match first HH:MM pattern
    const m = clean.match(/(\d{1,2}:\d{2})/);
    return m ? m[1] : '';
  },

  /** Count how many distinct times a job runs per day */
  getJobTimes(schedule) {
    if (!schedule) return [];
    const clean = schedule.replace(/ UK$/, '').trim();
    // Remove leading day spec if present
    const withoutDays = clean.replace(/^[a-zA-Z,\-]+\s+/, '');
    const matches = withoutDays.match(/\d{1,2}:\d{2}/g);
    return matches || [];
  },

  // ── Calendar builders ──────────────────────────────────────────────

  buildCalendar() {
    const enabledJobs = this.jobs.filter(j => j.enabled !== false);

    const intervalJobs = enabledJobs.filter(j => this.isIntervalJob(j.schedule));
    const monthlyJobs = enabledJobs.filter(j => this.isMonthlyJob(j.schedule));
    const gridJobs = enabledJobs.filter(j =>
      !this.isIntervalJob(j.schedule) && !this.isMonthlyJob(j.schedule)
    );

    return `
      ${this.buildAlwaysRunning(intervalJobs)}
      ${this.buildWeeklyGrid(gridJobs)}
      ${this.buildNextUp(enabledJobs, monthlyJobs)}
    `;
  },

  buildAlwaysRunning(jobs) {
    if (!jobs.length) return '';
    return `
      <div class="calendar-section">
        <div class="calendar-section-title">Always Running</div>
        <div class="always-running">
          ${jobs.map(j => `
            <span class="always-running-pill" onclick="JobsView.openJobDetail('${j.id}')">
              ${Icons.refresh}
              ${j.name || j.id} &middot; ${this.getIntervalLabel(j.schedule)}
            </span>
          `).join('')}
        </div>
      </div>
    `;
  },

  buildWeeklyGrid(jobs) {
    const today = new Date().getDay(); // 0=Sun

    // Build per-day buckets
    const buckets = Array.from({ length: 7 }, () => []);
    for (const job of jobs) {
      const days = this.getJobDays(job.schedule);
      const time = this.getJobTime(job.schedule);
      for (const d of days) {
        buckets[d].push({ ...job, _time: time });
      }
    }

    // Sort each bucket by time
    for (const bucket of buckets) {
      bucket.sort((a, b) => (a._time || '').localeCompare(b._time || ''));
    }

    const columns = this.DAY_NAMES.map((name, idx) => {
      const isToday = idx === today;
      const cards = buckets[idx].map(j => `
        <div class="job-card" onclick="JobsView.openJobDetail('${j.id}')" title="${j.name || j.id}">
          <div class="job-card-name">${j.name || j.id}</div>
          <div class="job-card-time">${j._time || ''}</div>
        </div>
      `).join('');

      return `
        <div class="weekly-grid-day${isToday ? ' today' : ''}">
          <div class="weekly-grid-header">${name}</div>
          <div class="weekly-grid-jobs">${cards}</div>
        </div>
      `;
    }).join('');

    return `
      <div class="calendar-section">
        <div class="calendar-section-title">Weekly Schedule</div>
        <div class="weekly-grid">${columns}</div>
      </div>
    `;
  },

  buildNextUp(allJobs, monthlyJobs) {
    // Sort by next_run, take top 8
    const upcoming = allJobs
      .filter(j => j.next_run)
      .sort((a, b) => new Date(a.next_run) - new Date(b.next_run))
      .slice(0, 8);

    if (!upcoming.length) return '';

    const rows = upcoming.map(j => {
      const isMonthly = this.isMonthlyJob(j.schedule);
      const badge = isMonthly ? '<span class="job-badge-monthly">Monthly</span>' : '';
      return `
        <div class="next-up-item" onclick="JobsView.openJobDetail('${j.id}')">
          <span class="next-up-name">${j.name || j.id}${badge}</span>
          <span class="next-up-time">${Format.relativeTime(j.next_run)}</span>
        </div>
      `;
    }).join('');

    return `
      <div class="calendar-section">
        <div class="calendar-section-title">Next Up</div>
        <div class="next-up-list">${rows}</div>
      </div>
    `;
  },

  // ── List tab (existing table) ──────────────────────────────────────

  buildTable() {
    const filter = State.get('jobFilter');
    const search = State.get('searchQuery');

    let filteredJobs = this.jobs;

    if (filter && filter !== 'all') {
      filteredJobs = filteredJobs.filter(j => j.status === filter);
    }

    if (search) {
      filteredJobs = filteredJobs.filter(j =>
        (j.name || j.id || '').toLowerCase().includes(search) ||
        (j.skill || '').toLowerCase().includes(search)
      );
    }

    filteredJobs = DataTable.applySorting(filteredJobs);

    const columns = [
      { key: 'status', label: 'Status', width: '100px', sortable: true,
        render: (val) => Components.statusBadge(val || 'idle') },
      { key: 'name', label: 'Name', sortable: true,
        render: (val, row) => `<strong>${val || row.id}</strong>` },
      { key: 'skill', label: 'Skill', sortable: true },
      { key: 'schedule', label: 'Schedule', sortable: true },
      { key: 'channel', label: 'Channel', sortable: true },
      { key: 'last_run', label: 'Last Run', sortable: true,
        render: (val) => val ? Format.relativeTime(val) : '-' },
      { key: 'next_run', label: 'Next Run', sortable: true,
        render: (val) => val ? Format.relativeTime(val) : '-' },
      { key: 'success_rate_24h', label: 'Success Rate', sortable: true,
        render: (val) => val != null ? `${val}%` : '-' },
      { key: 'enabled', label: 'Enabled', width: '80px',
        render: (val) => `
          <button class="btn btn-sm btn-ghost" onclick="JobsView.toggleJob(event)">
            ${val !== false ? Icons.toggleOn : Icons.toggleOff}
          </button>
        ` },
    ];

    return Components.dataTable({
      id: 'jobs-data-table',
      columns,
      data: filteredJobs,
      onRowClick: 'JobsView.selectJob',
    });
  },

  // ── Detail panel + actions ─────────────────────────────────────────

  // ── History tab ──────────────────────────────────────────────────

  historyData: [],
  historyHours: 24,
  historyFilter: 'all',

  buildHistoryPlaceholder() {
    return `
      <div id="jobs-history-content">
        ${Components.skeleton('table', 8)}
      </div>
    `;
  },

  async loadHistory() {
    const container = document.getElementById('jobs-history-content');
    if (!container) return;

    container.innerHTML = Components.skeleton('table', 8);

    try {
      const params = new URLSearchParams({ hours: this.historyHours, limit: '200' });
      if (this.historyFilter && this.historyFilter !== 'all') {
        params.set('status', this.historyFilter);
      }
      const data = await API.get(`/api/jobs/executions?${params}`);
      this.historyData = data.executions || [];
      this.renderHistory();
    } catch (error) {
      console.error('Failed to load job history:', error);
      container.innerHTML = `
        <div class="card">
          <div class="empty-state">
            <div class="empty-state-icon">${Icons.alertCircle}</div>
            <div class="empty-state-title">Failed to load history</div>
            <div class="empty-state-description">${error.message}</div>
            <button class="btn btn-primary mt-md" onclick="JobsView.loadHistory()">Retry</button>
          </div>
        </div>
      `;
    }
  },

  renderHistory() {
    const container = document.getElementById('jobs-history-content');
    if (!container) return;

    // Build summary cards
    const total = this.historyData.length;
    const success = this.historyData.filter(e => e.status === 'success').length;
    const failed = this.historyData.filter(e => e.status === 'error').length;
    const running = this.historyData.filter(e => e.status === 'running').length;
    const successRate = total > 0 ? ((success / total) * 100).toFixed(1) : '0';
    const avgDuration = total > 0
      ? Math.round(this.historyData.filter(e => e.duration_ms).reduce((sum, e) => sum + e.duration_ms, 0) / Math.max(this.historyData.filter(e => e.duration_ms).length, 1))
      : 0;

    // Job name map from main jobs list
    const jobNameMap = {};
    for (const j of this.jobs) {
      jobNameMap[j.id] = j.name || j.id;
    }

    const formatDuration = (ms) => {
      if (!ms && ms !== 0) return '-';
      if (ms < 1000) return `${ms}ms`;
      if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
      return `${(ms / 60000).toFixed(1)}m`;
    };

    // Build filter/toolbar
    const toolbar = `
      <div class="flex justify-between items-center mb-md" style="flex-wrap: wrap; gap: 0.5rem;">
        <div class="flex gap-sm items-center" style="flex-wrap: wrap;">
          <select class="form-select" onchange="JobsView.historyHours = parseInt(this.value); JobsView.loadHistory();">
            <option value="6" ${this.historyHours === 6 ? 'selected' : ''}>Last 6 hours</option>
            <option value="24" ${this.historyHours === 24 ? 'selected' : ''}>Last 24 hours</option>
            <option value="72" ${this.historyHours === 72 ? 'selected' : ''}>Last 3 days</option>
            <option value="168" ${this.historyHours === 168 ? 'selected' : ''}>Last 7 days</option>
          </select>
          <select class="form-select" onchange="JobsView.historyFilter = this.value; JobsView.loadHistory();">
            <option value="all" ${this.historyFilter === 'all' ? 'selected' : ''}>All Status</option>
            <option value="success" ${this.historyFilter === 'success' ? 'selected' : ''}>Success</option>
            <option value="error" ${this.historyFilter === 'error' ? 'selected' : ''}>Error</option>
            <option value="running" ${this.historyFilter === 'running' ? 'selected' : ''}>Running</option>
          </select>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="JobsView.loadHistory()">
          ${Icons.refresh} Refresh
        </button>
      </div>
    `;

    // Stats row
    const stats = `
      <div class="grid grid-4 mb-md">
        <div class="card" style="padding: 0.75rem 1rem;">
          <div class="text-muted text-xs" style="margin-bottom:0.25rem">Total Runs</div>
          <div style="font-size:1.25rem; font-weight:700">${total}</div>
        </div>
        <div class="card" style="padding: 0.75rem 1rem;">
          <div class="text-muted text-xs" style="margin-bottom:0.25rem">Success Rate</div>
          <div style="font-size:1.25rem; font-weight:700; color: ${parseFloat(successRate) >= 90 ? 'var(--success)' : parseFloat(successRate) >= 50 ? 'var(--warning)' : 'var(--error)'}">${successRate}%</div>
        </div>
        <div class="card" style="padding: 0.75rem 1rem;">
          <div class="text-muted text-xs" style="margin-bottom:0.25rem">Failures</div>
          <div style="font-size:1.25rem; font-weight:700; color: ${failed > 0 ? 'var(--error)' : 'var(--text-primary)'}">${failed}</div>
        </div>
        <div class="card" style="padding: 0.75rem 1rem;">
          <div class="text-muted text-xs" style="margin-bottom:0.25rem">Avg Duration</div>
          <div style="font-size:1.25rem; font-weight:700">${formatDuration(avgDuration)}</div>
        </div>
      </div>
    `;

    // Build table rows
    const tableRows = this.historyData.map(e => {
      const jobName = jobNameMap[e.job_id] || e.job_id;
      const statusBadge = Components.statusBadge(e.status);
      const started = Format.datetime(e.started_at);
      const duration = formatDuration(e.duration_ms);
      const errorCell = e.error
        ? `<span class="text-error" title="${Utils.escapeHtml(e.error)}">${Utils.escapeHtml(e.error.substring(0, 50))}${e.error.length > 50 ? '...' : ''}</span>`
        : (e.output_preview ? `<span class="text-muted" title="${Utils.escapeHtml(e.output_preview)}">${Utils.escapeHtml(e.output_preview.substring(0, 50))}${e.output_preview.length > 50 ? '...' : ''}</span>` : '-');

      return `
        <tr class="clickable" onclick="JobsView.openJobDetail('${e.job_id}')">
          <td>${statusBadge}</td>
          <td><strong>${Utils.escapeHtml(jobName)}</strong></td>
          <td>${started}</td>
          <td>${duration}</td>
          <td>${errorCell}</td>
        </tr>
      `;
    }).join('');

    const table = `
      <div class="data-table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width:100px">Status</th>
              <th>Job</th>
              <th style="width:140px">Started</th>
              <th style="width:100px">Duration</th>
              <th>Output / Error</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows.length ? tableRows : `
              <tr>
                <td colspan="5" style="text-align:center; padding:2rem; color:var(--text-secondary)">
                  No executions found for this time period
                </td>
              </tr>
            `}
          </tbody>
        </table>
      </div>
    `;

    container.innerHTML = toolbar + stats + table;
  },

  // ── Detail panel + actions ─────────────────────────────────────────

  openJobDetail(jobId) {
    const job = this.jobs.find(j => j.id === jobId);
    if (!job) return;
    this.showJobPanel(job);
  },

  selectJob(index) {
    const job = this.jobs[index];
    if (!job) return;
    this.showJobPanel(job);
  },

  showJobPanel(job) {
    State.set({ selectedItem: job });

    const content = `
      <h3 class="mb-md">${job.name || job.id}</h3>
      <p class="text-secondary mb-lg">${job.description || 'No description'}</p>

      <div class="mb-lg">
        <div class="flex justify-between py-sm border-b">
          <span class="text-muted">Status</span>
          ${Components.statusBadge(job.status || 'idle')}
        </div>
        <div class="flex justify-between py-sm border-b">
          <span class="text-muted">Schedule</span>
          <span>${job.schedule || '-'}</span>
        </div>
        <div class="flex justify-between py-sm border-b">
          <span class="text-muted">Channel</span>
          <span>${job.channel || '-'}</span>
        </div>
        <div class="flex justify-between py-sm border-b">
          <span class="text-muted">Skill</span>
          <span>${job.skill || '-'}</span>
        </div>
        <div class="flex justify-between py-sm border-b">
          <span class="text-muted">Last Run</span>
          <span>${job.last_run ? Format.datetime(job.last_run) : 'Never'}</span>
        </div>
        <div class="flex justify-between py-sm border-b">
          <span class="text-muted">Next Run</span>
          <span>${job.next_run ? Format.datetime(job.next_run) : '-'}</span>
        </div>
      </div>

      <div class="flex gap-sm">
        <button class="btn btn-primary flex-1" onclick="JobsView.runNow('${job.id}')">
          ${Icons.play} Run Now
        </button>
        <button class="btn btn-secondary flex-1" onclick="JobsView.toggleEnabled('${job.id}')">
          ${job.enabled !== false ? 'Disable' : 'Enable'}
        </button>
      </div>
    `;

    DetailPanel.open(content);
  },

  toggleJob(event) {
    event.stopPropagation();
    // Toggle job enabled state
  },

  async runNow(jobId) {
    try {
      await API.post(`/api/jobs/${jobId}/run`);
      Toast.success('Job Started', `Running ${jobId}`);
    } catch (error) {
      Toast.error('Error', `Failed to run job: ${error.message}`);
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Jobs list updated');
  },
};


/**
 * Services View - Service monitoring and control
 * Enhanced with detail panel, tmux viewer, health history, and control actions
 */
const ServicesView = {
  title: 'Services',

  // State
  services: {},
  tmuxSessions: [],
  selectedService: null,
  healthHistory: {},  // { serviceKey: [{ timestamp, status }] }
  serverUptimes: {},  // { serviceKey: uptimePercentage } - from server
  serverHistoryLoaded: false,
  screenRefreshInterval: null,
  autoRefreshInterval: null,

  // LocalStorage key for health history persistence
  HEALTH_HISTORY_KEY: 'peter_dashboard_health_history',

  // Service configuration
  serviceInfo: {
    hadley_api: {
      name: 'Hadley API',
      icon: Icons.server,
      port: 8100,
      managed: 'NSSM',
      description: 'REST API for external services',
      healthEndpoint: '/health',
      isTmux: false,
    },
    discord_bot: {
      name: 'Discord Bot',
      icon: Icons.messageCircle,
      managed: 'NSSM',
      description: 'Main Discord bot process',
      isTmux: false,
    },
    hadley_bricks: {
      name: 'Hadley Bricks',
      icon: Icons.box,
      port: 3000,
      managed: 'NSSM',
      description: 'LEGO inventory management system',
      healthEndpoint: '/api/health',
      isTmux: false,
    },
    peterbot_session: {
      name: 'Peterbot Session',
      icon: Icons.terminal,
      managed: 'tmux',
      description: 'Claude Code tmux session for Peterbot',
      tmuxSession: 'claude-peterbot',
      isTmux: true,
    },
    claude_mem: {
      name: 'Memory Worker',
      icon: Icons.brain,
      port: 37777,
      managed: 'Systemd',
      description: 'Claude memory observation worker',
      healthEndpoint: '/health',
      isTmux: false,
    },
  },

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in services-view">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>System Services</h2>
            <p class="text-secondary">Monitor and control system services</p>
          </div>
          <div class="flex gap-sm">
            <button class="btn btn-secondary" onclick="ServicesView.refresh()">
              ${Icons.refresh} Refresh
            </button>
            <button class="btn btn-primary" onclick="ServicesView.confirmRestartAll()">
              ${Icons.refreshCw} Restart All
            </button>
          </div>
        </div>

        <div id="model-provider-card" class="mb-lg"></div>

        <div class="services-layout">
          <div class="services-grid-container">
            <div class="grid grid-cols-2 gap-md" id="services-list">
              ${Components.skeleton('card')}
              ${Components.skeleton('card')}
              ${Components.skeleton('card')}
              ${Components.skeleton('card')}
              ${Components.skeleton('card')}
            </div>
          </div>

          <div class="service-detail-panel" id="service-detail-panel">
            <div class="detail-panel-placeholder">
              <div class="empty-state">
                <div class="empty-state-icon">${Icons.server}</div>
                <div class="empty-state-title">Select a service</div>
                <div class="empty-state-description">Click on a service card to view details</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Add custom styles for services view
    this.injectStyles();

    // Load health history from localStorage first (for immediate display)
    this.loadHealthHistoryFromStorage();

    // Load data and start auto-refresh
    await this.loadData();
    this.startAutoRefresh();
  },

  loadHealthHistoryFromStorage() {
    try {
      const stored = localStorage.getItem(this.HEALTH_HISTORY_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        // Only use data that's less than 24 hours old
        const cutoff = Date.now() - (24 * 60 * 60 * 1000);
        this.healthHistory = {};
        Object.entries(data).forEach(([key, history]) => {
          this.healthHistory[key] = history.filter(h => h.timestamp > cutoff);
        });
        console.log('[ServicesView] Loaded health history from localStorage:',
          Object.keys(this.healthHistory).map(k => `${k}: ${this.healthHistory[k].length} records`).join(', '));
      }
    } catch (e) {
      console.warn('[ServicesView] Failed to load health history from storage:', e);
      this.healthHistory = {};
    }
  },

  saveHealthHistoryToStorage() {
    try {
      // Only save last 24 hours worth of data to avoid localStorage bloat
      const cutoff = Date.now() - (24 * 60 * 60 * 1000);
      const dataToSave = {};
      Object.entries(this.healthHistory).forEach(([key, history]) => {
        dataToSave[key] = history.filter(h => h.timestamp > cutoff);
      });
      localStorage.setItem(this.HEALTH_HISTORY_KEY, JSON.stringify(dataToSave));
    } catch (e) {
      console.warn('[ServicesView] Failed to save health history to storage:', e);
    }
  },

  injectStyles() {
    if (document.getElementById('services-view-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'services-view-styles';
    styles.textContent = `
      .services-layout {
        display: flex;
        gap: var(--spacing-lg);
        min-height: 600px;
      }

      .services-grid-container {
        flex: 1;
        min-width: 0;
      }

      .service-detail-panel {
        width: 420px;
        flex-shrink: 0;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        overflow: hidden;
        display: flex;
        flex-direction: column;
      }

      .detail-panel-placeholder {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--spacing-xl);
      }

      .service-card.selected {
        border-color: var(--accent);
        box-shadow: 0 0 0 2px var(--accent-light);
      }

      .service-card.clickable {
        cursor: pointer;
      }

      .service-card.clickable:hover {
        border-color: var(--accent);
      }

      /* Health History Bar */
      .health-history {
        display: flex;
        gap: 2px;
        margin-top: var(--spacing-sm);
        height: 8px;
        border-radius: var(--radius-sm);
        overflow: hidden;
        background: var(--bg-hover);
      }

      .health-block {
        flex: 1;
        min-width: 4px;
        transition: background-color var(--transition-fast);
      }

      .health-block.healthy {
        background-color: var(--status-running);
      }

      .health-block.unhealthy {
        background-color: var(--status-error);
      }

      .health-block.unknown {
        background-color: var(--status-idle);
      }

      .health-summary {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: var(--text-xs);
        color: var(--text-muted);
        margin-top: var(--spacing-xs);
      }

      /* Detail Panel Header */
      .detail-header {
        padding: var(--spacing-lg);
        border-bottom: 1px solid var(--border);
        background: var(--bg-hover);
      }

      .detail-header-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: var(--spacing-sm);
      }

      .detail-service-name {
        display: flex;
        align-items: center;
        gap: var(--spacing-sm);
      }

      .detail-service-name h3 {
        margin: 0;
        font-size: var(--text-lg);
      }

      .detail-description {
        font-size: var(--text-sm);
        color: var(--text-secondary);
        margin-top: var(--spacing-xs);
      }

      /* Detail Panel Content */
      .detail-content {
        flex: 1;
        overflow-y: auto;
        padding: var(--spacing-lg);
      }

      .detail-section {
        margin-bottom: var(--spacing-lg);
      }

      .detail-section-title {
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: var(--spacing-sm);
      }

      .detail-stats {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: var(--spacing-md);
      }

      .detail-stat {
        background: var(--bg-hover);
        padding: var(--spacing-md);
        border-radius: var(--radius-md);
      }

      .detail-stat-label {
        font-size: var(--text-xs);
        color: var(--text-muted);
        margin-bottom: var(--spacing-xs);
      }

      .detail-stat-value {
        font-size: var(--text-base);
        font-weight: var(--font-semibold);
      }

      /* Terminal Viewer */
      .terminal-viewer {
        background: #1a1a2e;
        color: #e0e0e0;
        font-family: var(--font-mono);
        font-size: 11px;
        line-height: 1.4;
        padding: var(--spacing-md);
        border-radius: var(--radius-md);
        max-height: 300px;
        overflow: auto;
        white-space: pre-wrap;
        word-wrap: break-word;
      }

      .terminal-viewer-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: var(--spacing-sm);
      }

      .terminal-viewer-controls {
        display: flex;
        gap: var(--spacing-sm);
        align-items: center;
      }

      .terminal-auto-refresh {
        display: flex;
        align-items: center;
        gap: var(--spacing-xs);
        font-size: var(--text-xs);
        color: var(--text-muted);
      }

      .terminal-auto-refresh input {
        margin: 0;
      }

      /* Send Command Input */
      .send-command-container {
        display: flex;
        gap: var(--spacing-sm);
        margin-top: var(--spacing-sm);
      }

      .send-command-container input {
        flex: 1;
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        font-family: var(--font-mono);
        font-size: var(--text-sm);
        background: var(--bg-input);
      }

      /* Detail Actions */
      .detail-actions {
        padding: var(--spacing-lg);
        border-top: 1px solid var(--border);
        display: flex;
        gap: var(--spacing-sm);
        flex-wrap: wrap;
      }

      /* Confirmation Modal Content */
      .confirm-content {
        text-align: center;
        padding: var(--spacing-md);
      }

      .confirm-icon {
        font-size: 48px;
        margin-bottom: var(--spacing-md);
        color: var(--status-paused);
      }

      .confirm-title {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        margin-bottom: var(--spacing-sm);
      }

      .confirm-message {
        color: var(--text-secondary);
        margin-bottom: var(--spacing-lg);
      }

      .confirm-buttons {
        display: flex;
        gap: var(--spacing-sm);
        justify-content: center;
      }

      /* Latency indicator */
      .latency-indicator {
        display: inline-flex;
        align-items: center;
        gap: var(--spacing-xs);
      }

      .latency-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }

      .latency-good { background-color: var(--status-running); }
      .latency-medium { background-color: var(--status-paused); }
      .latency-poor { background-color: var(--status-error); }

      @media (max-width: 1200px) {
        .services-layout {
          flex-direction: column;
        }

        .service-detail-panel {
          width: 100%;
        }
      }
    `;
    document.head.appendChild(styles);
  },

  startAutoRefresh() {
    // Refresh service status every 30 seconds
    this.autoRefreshInterval = setInterval(() => {
      this.loadData(true);  // silent refresh
    }, 30000);
  },

  stopAutoRefresh() {
    if (this.autoRefreshInterval) {
      clearInterval(this.autoRefreshInterval);
      this.autoRefreshInterval = null;
    }
    if (this.screenRefreshInterval) {
      clearInterval(this.screenRefreshInterval);
      this.screenRefreshInterval = null;
    }
  },

  async loadData(silent = false) {
    try {
      // Fetch current status
      const status = await API.get('/api/status');
      this.services = status.services || {};
      this.tmuxSessions = status.tmux_sessions || [];

      // Fetch server-side health history (includes accurate uptime calculations)
      // Do this on every refresh to get the latest server-tracked data
      try {
        const healthData = await API.get('/api/health-history');
        this.serverUptimes = healthData.uptimes || {};
        // Merge server history with client-side history for display
        if (healthData.history) {
          Object.entries(healthData.history).forEach(([key, serverHistory]) => {
            if (!this.healthHistory[key]) {
              this.healthHistory[key] = [];
            }
            // Merge server history with client history, avoiding duplicates
            const existingTimestamps = new Set(this.healthHistory[key].map(h => h.timestamp));
            const newEntries = serverHistory.filter(h => !existingTimestamps.has(h.timestamp));
            this.healthHistory[key] = [...this.healthHistory[key], ...newEntries]
              .sort((a, b) => a.timestamp - b.timestamp)
              .slice(-2880);  // Keep max 24 hours
          });
        }
        this.serverHistoryLoaded = true;
      } catch (historyError) {
        console.warn('Failed to load health history from server:', historyError);
        // Continue without server history - client-side tracking will still work
      }

      // Record current status to client-side history
      this.recordHealthHistory();

      this.renderServices();

      // Render model provider card (uses status.model_provider from /api/status)
      this.renderModelProviderCard(status.model_provider);

      // Update detail panel if a service is selected
      if (this.selectedService && this.services[this.selectedService]) {
        this.renderDetailPanel(this.selectedService);
      }
    } catch (error) {
      console.error('Failed to load services:', error);
      if (!silent) {
        Toast.error('Error', 'Failed to load service status');
      }
    }
  },

  renderModelProviderCard(providerStatus) {
    const container = document.getElementById('model-provider-card');
    if (!container) return;

    // Migrate legacy 'claude' → 'claude_cc'
    let provider = (providerStatus && providerStatus.active_provider) || 'claude_cc';
    if (provider === 'claude') provider = 'claude_cc';

    const reason = (providerStatus && providerStatus.reason) || 'default';
    const switchedAt = providerStatus && providerStatus.switched_at;
    const autoSwitch = providerStatus ? providerStatus.auto_switch_enabled !== false : true;
    const kimiRequests = (providerStatus && providerStatus.kimi_requests) || 0;
    const priority = (providerStatus && providerStatus.provider_priority) || ['claude_cc', 'claude_cc2', 'kimi'];

    const providerConfig = {
      'claude_cc':  { label: 'Claude (cc)',  icon: '🤖', badge: 'badge-success', color: 'var(--success)', bg: 'rgba(16, 185, 129, 0.1)', tier: 'Primary' },
      'claude_cc2': { label: 'Claude (cc2)', icon: '🤖', badge: 'badge-info',    color: 'var(--info)',    bg: 'rgba(59, 130, 246, 0.1)', tier: 'Secondary' },
      'kimi':       { label: 'Kimi 2.5',     icon: '⚠️', badge: 'badge-warning', color: 'var(--warning)', bg: 'rgba(245, 158, 11, 0.1)', tier: 'Fallback' },
    };
    const cfg = providerConfig[provider] || providerConfig['claude_cc'];
    const switchedTimeStr = switchedAt ? Utils.formatRelativeTime(switchedAt) : 'never';

    // Build status text
    let statusText = `${cfg.tier} provider · Switched ${switchedTimeStr}`;
    if (provider === 'kimi') {
      statusText = `Fallback mode (${reason}) · ${kimiRequests} Kimi requests · Switched ${switchedTimeStr}`;
    } else if (provider === 'claude_cc2') {
      statusText = `Secondary account (${reason}) · Switched ${switchedTimeStr}`;
    }

    // Build switch buttons for other providers
    const switchButtons = priority
      .filter(p => p !== provider)
      .map(p => {
        const pcfg = providerConfig[p] || {};
        return `<button class="btn btn-sm btn-secondary" onclick="ServicesView.confirmSwitchProvider('${p}')">${pcfg.label || p}</button>`;
      })
      .join(' ');

    container.innerHTML = `
      <div class="card" style="border-left: 4px solid ${cfg.color}; background: ${cfg.bg};">
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-md">
            <div>
              <div class="flex items-center gap-sm">
                <span style="font-size: 1.25rem;">${cfg.icon}</span>
                <strong style="font-size: 1.1rem;">Model Provider</strong>
                <span class="badge ${cfg.badge}" style="margin-left: 0.5rem;">
                  ${cfg.label}
                </span>
              </div>
              <div class="text-secondary text-sm" style="margin-top: 0.35rem;">
                ${statusText}
              </div>
            </div>
          </div>
          <div class="flex items-center gap-sm">
            <label class="flex items-center gap-xs text-sm" title="Auto-switch to next provider when credits exhausted" style="cursor: pointer;">
              <input type="checkbox" ${autoSwitch ? 'checked' : ''} onchange="ServicesView.toggleAutoSwitch(this.checked)">
              Auto-cascade
            </label>
            ${switchButtons}
          </div>
        </div>
      </div>
    `;
  },

  confirmSwitchProvider(targetProvider) {
    const labels = { 'claude_cc': 'Claude (cc)', 'claude_cc2': 'Claude (cc2)', 'kimi': 'Kimi 2.5' };
    const label = labels[targetProvider] || targetProvider;
    const warnings = {
      'claude_cc': 'Ensure primary Anthropic account has available credits.',
      'claude_cc2': 'Ensure secondary Anthropic account has available credits.',
      'kimi': 'Kimi is degraded mode — no MCP tools, no CLAUDE.md auto-load.',
    };
    const warning = warnings[targetProvider] || '';

    Modal.show(`
      <h3>Switch to ${label}?</h3>
      <p class="text-secondary mb-md">${warning}</p>
      <div class="flex gap-sm justify-end">
        <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
        <button class="btn btn-primary" onclick="ServicesView.switchProvider('${targetProvider}')">Switch</button>
      </div>
    `);
  },

  async switchProvider(targetProvider) {
    Modal.close();
    const labels = { 'claude_cc': 'Claude (cc)', 'claude_cc2': 'Claude (cc2)', 'kimi': 'Kimi 2.5' };
    try {
      const HADLEY_API = 'http://localhost:8100';
      const resp = await fetch(HADLEY_API + '/model/switch', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: targetProvider, reason: 'manual' }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      Toast.success('Provider Switched', `Now using ${labels[targetProvider] || targetProvider}`);
      await this.loadData();
    } catch (e) {
      Toast.error('Error', `Failed to switch provider: ${e.message}`);
    }
  },

  async toggleAutoSwitch(enabled) {
    try {
      const HADLEY_API = 'http://localhost:8100';
      const resp = await fetch(HADLEY_API + '/model/auto-switch', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      Toast.success('Auto-Switch', enabled ? 'Enabled' : 'Disabled');
    } catch (e) {
      Toast.error('Error', `Failed to toggle auto-switch: ${e.message}`);
    }
  },

  recordHealthHistory() {
    const now = Date.now();
    let hasChanges = false;

    Object.entries(this.services).forEach(([key, svc]) => {
      if (!this.healthHistory[key]) {
        this.healthHistory[key] = [];
      }

      const status = svc.status === 'up' || svc.status === 'running' ? 'healthy' : 'unhealthy';

      // Only record if there's no recent entry (within last 10 seconds) to avoid duplicates
      const lastEntry = this.healthHistory[key][this.healthHistory[key].length - 1];
      if (!lastEntry || (now - lastEntry.timestamp) > 10000) {
        this.healthHistory[key].push({ timestamp: now, status });
        hasChanges = true;
      }

      // Keep only last 24 hours (assuming 30s intervals = 2880 records max)
      if (this.healthHistory[key].length > 2880) {
        this.healthHistory[key] = this.healthHistory[key].slice(-2880);
      }
    });

    // Persist to localStorage after recording
    if (hasChanges) {
      this.saveHealthHistoryToStorage();
    }
  },

  getHealthBlocks(serviceKey) {
    const history = this.healthHistory[serviceKey] || [];
    const blockCount = 24;  // Show 24 blocks for 24h-ish representation

    if (history.length === 0) {
      return Array(blockCount).fill('unknown');
    }

    // If we have fewer records than blocks, pad with most recent status
    if (history.length < blockCount) {
      const lastStatus = history[history.length - 1]?.status || 'unknown';
      const padded = [...history];
      while (padded.length < blockCount) {
        padded.unshift({ status: 'unknown' });
      }
      return padded.slice(-blockCount).map(h => h.status);
    }

    // Sample evenly across history
    const step = Math.floor(history.length / blockCount);
    const blocks = [];
    for (let i = 0; i < blockCount; i++) {
      const idx = Math.min(i * step, history.length - 1);
      blocks.push(history[idx]?.status || 'unknown');
    }
    return blocks;
  },

  calculateUptime(serviceKey) {
    // Use server-side uptime if available (source of truth)
    // Server tracks all health checks persistently, even when dashboard is closed
    if (this.serverUptimes && this.serverUptimes[serviceKey] !== undefined) {
      return Math.round(this.serverUptimes[serviceKey]);
    }

    // Fall back to client-side calculation from localStorage-persisted history
    const history = this.healthHistory[serviceKey] || [];
    if (history.length === 0) return 100;

    const healthyCount = history.filter(h => h.status === 'healthy').length;
    return Math.round((healthyCount / history.length) * 100);
  },

  getLatencyClass(latency) {
    if (!latency) return 'unknown';
    if (latency < 100) return 'good';
    if (latency < 500) return 'medium';
    return 'poor';
  },

  renderServices() {
    const html = Object.entries(this.services).map(([key, svc]) => {
      const info = this.serviceInfo[key] || { name: key, icon: Icons.server };
      const details = [];
      const isSelected = this.selectedService === key;
      const uptime = this.calculateUptime(key);
      const healthBlocks = this.getHealthBlocks(key);

      if (info.port) details.push({ label: 'Port', value: info.port });
      if (svc.pid) details.push({ label: 'PID', value: svc.pid });
      if (svc.latency_ms) {
        const latencyClass = this.getLatencyClass(svc.latency_ms);
        details.push({
          label: 'Latency',
          value: `<span class="latency-indicator"><span class="latency-dot latency-${latencyClass}"></span>${svc.latency_ms}ms</span>`
        });
      }
      if (svc.last_restart) {
        details.push({ label: 'Last Restart', value: Utils.formatRelativeTime(svc.last_restart) });
      }
      if (info.managed) details.push({ label: 'Managed', value: info.managed });

      return `
        <div class="service-card clickable ${isSelected ? 'selected' : ''}"
             onclick="ServicesView.selectService('${key}')">
          <div class="service-card-header">
            <div class="flex items-center gap-sm">
              <span class="text-xl">${info.icon}</span>
              <span class="service-card-name">${info.name}</span>
            </div>
            ${Components.statusBadge(svc.status)}
          </div>
          <div class="service-card-details">
            ${details.map(d => `
              <div class="service-card-detail">
                <span class="text-muted">${d.label}:</span>
                <span>${d.value}</span>
              </div>
            `).join('')}
          </div>

          <div class="health-history" title="24h uptime: ${uptime}%">
            ${healthBlocks.map(status => `<div class="health-block ${status}"></div>`).join('')}
          </div>
          <div class="health-summary">
            <span>24h Health</span>
            <span class="${uptime >= 95 ? 'text-success' : uptime >= 80 ? 'text-warning' : 'text-error'}">${uptime}% uptime</span>
          </div>

          <div class="service-card-actions" onclick="event.stopPropagation()">
            <button class="btn btn-sm btn-secondary" onclick="ServicesView.confirmRestart('${key}')">
              ${Icons.refreshCw} Restart
            </button>
            <button class="btn btn-sm btn-danger" onclick="ServicesView.confirmStop('${key}')">
              ${Icons.square} Stop
            </button>
          </div>
        </div>
      `;
    }).join('');

    const servicesList = document.getElementById('services-list');
    if (servicesList) {
      servicesList.innerHTML = html;
    }
  },

  selectService(serviceKey) {
    this.selectedService = serviceKey;
    this.renderServices();  // Re-render to update selection state
    this.renderDetailPanel(serviceKey);
  },

  renderDetailPanel(serviceKey) {
    const svc = this.services[serviceKey];
    const info = this.serviceInfo[serviceKey] || { name: serviceKey, icon: Icons.server };
    const panel = document.getElementById('service-detail-panel');

    if (!panel || !svc) return;

    const uptime = this.calculateUptime(serviceKey);
    const isTmux = info.isTmux;

    panel.innerHTML = `
      <div class="detail-header">
        <div class="detail-header-top">
          <div class="detail-service-name">
            <span class="text-2xl">${info.icon}</span>
            <div>
              <h3>${info.name}</h3>
              <div class="detail-description">${info.description || ''}</div>
            </div>
          </div>
          ${Components.statusBadge(svc.status)}
        </div>
      </div>

      <div class="detail-content">
        <div class="detail-section">
          <div class="detail-section-title">Status Information</div>
          <div class="detail-stats">
            <div class="detail-stat">
              <div class="detail-stat-label">Status</div>
              <div class="detail-stat-value ${svc.status === 'up' ? 'text-success' : 'text-error'}">
                ${svc.status === 'up' || svc.status === 'running' ? 'Running' : 'Stopped'}
              </div>
            </div>
            <div class="detail-stat">
              <div class="detail-stat-label">Uptime (24h)</div>
              <div class="detail-stat-value ${uptime >= 95 ? 'text-success' : uptime >= 80 ? 'text-warning' : 'text-error'}">
                ${uptime}%
              </div>
            </div>
            ${svc.pid ? `
              <div class="detail-stat">
                <div class="detail-stat-label">Process ID</div>
                <div class="detail-stat-value">${svc.pid}</div>
              </div>
            ` : ''}
            ${info.port ? `
              <div class="detail-stat">
                <div class="detail-stat-label">Port</div>
                <div class="detail-stat-value">${info.port}</div>
              </div>
            ` : ''}
            ${svc.latency_ms ? `
              <div class="detail-stat">
                <div class="detail-stat-label">Latency</div>
                <div class="detail-stat-value">
                  <span class="latency-indicator">
                    <span class="latency-dot latency-${this.getLatencyClass(svc.latency_ms)}"></span>
                    ${svc.latency_ms}ms
                  </span>
                </div>
              </div>
            ` : ''}
            <div class="detail-stat">
              <div class="detail-stat-label">Managed By</div>
              <div class="detail-stat-value">${info.managed || 'Unknown'}</div>
            </div>
            ${svc.last_restart ? `
              <div class="detail-stat">
                <div class="detail-stat-label">Last Restart</div>
                <div class="detail-stat-value">${Utils.formatRelativeTime(svc.last_restart)}</div>
              </div>
            ` : ''}
            ${svc.attached !== undefined ? `
              <div class="detail-stat">
                <div class="detail-stat-label">Attached</div>
                <div class="detail-stat-value">${svc.attached ? 'Yes' : 'No'}</div>
              </div>
            ` : ''}
          </div>
        </div>

        ${isTmux ? `
          <div class="detail-section">
            <div class="terminal-viewer-header">
              <div class="detail-section-title">Terminal Output</div>
              <div class="terminal-viewer-controls">
                <label class="terminal-auto-refresh">
                  <input type="checkbox" id="screen-auto-refresh" checked onchange="ServicesView.toggleScreenAutoRefresh(this.checked)">
                  Auto-refresh (5s)
                </label>
                <button class="btn btn-sm btn-secondary" onclick="ServicesView.refreshScreen()">
                  ${Icons.refresh}
                </button>
                <button class="btn btn-sm btn-secondary" onclick="ServicesView.clearScreen()">
                  Clear
                </button>
              </div>
            </div>
            <div class="terminal-viewer" id="terminal-output">Loading...</div>
            <div class="send-command-container">
              <input type="text" id="terminal-command" placeholder="Type a command..."
                     onkeypress="if(event.key==='Enter')ServicesView.sendCommand()">
              <button class="btn btn-sm btn-primary" onclick="ServicesView.sendCommand()">
                Send
              </button>
            </div>
          </div>
        ` : `
          <div class="detail-section">
            <div class="detail-section-title">Health Checks</div>
            <div id="health-check-results">
              <div class="text-muted">Loading health check data...</div>
            </div>
          </div>
        `}
      </div>

      <div class="detail-actions">
        <button class="btn btn-secondary" onclick="ServicesView.confirmRestart('${serviceKey}')">
          ${Icons.refreshCw} Restart Service
        </button>
        <button class="btn btn-danger" onclick="ServicesView.confirmStop('${serviceKey}')">
          ${Icons.square} Stop Service
        </button>
        ${!isTmux && info.port ? `
          <button class="btn btn-secondary" onclick="ServicesView.viewLogs('${serviceKey}')">
            ${Icons.fileText} View Logs
          </button>
        ` : ''}
      </div>
    `;

    // Load terminal output for tmux sessions
    if (isTmux) {
      this.refreshScreen();
      this.startScreenAutoRefresh();
    } else {
      this.stopScreenAutoRefresh();
      this.loadHealthChecks(serviceKey);
    }
  },

  async loadHealthChecks(serviceKey) {
    const container = document.getElementById('health-check-results');
    if (!container) return;

    const info = this.serviceInfo[serviceKey];
    const svc = this.services[serviceKey];

    // Display recent health status from history
    const history = this.healthHistory[serviceKey] || [];
    const recentChecks = history.slice(-10).reverse();

    // Show health check method
    const checkMethod = info?.port ? 'HTTP Health Endpoint' : 'Process Monitoring';

    if (recentChecks.length === 0) {
      container.innerHTML = `
        <div class="text-muted mb-sm">Method: ${checkMethod}</div>
        <div class="text-muted">No health check history available yet</div>
      `;
      return;
    }

    container.innerHTML = `
      <div class="text-muted mb-sm">Method: ${checkMethod}</div>
      <div class="health-check-list">
        ${recentChecks.map((check, idx) => {
          const time = new Date(check.timestamp).toLocaleTimeString();
          return `
            <div class="service-card-detail">
              <span class="text-muted">${time}</span>
              <span class="${check.status === 'healthy' ? 'text-success' : 'text-error'}">
                ${check.status === 'healthy' ? 'Healthy' : 'Unhealthy'}
              </span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  },

  startScreenAutoRefresh() {
    this.stopScreenAutoRefresh();
    const checkbox = document.getElementById('screen-auto-refresh');
    if (checkbox && checkbox.checked) {
      this.screenRefreshInterval = setInterval(() => {
        this.refreshScreen();
      }, 5000);
    }
  },

  stopScreenAutoRefresh() {
    if (this.screenRefreshInterval) {
      clearInterval(this.screenRefreshInterval);
      this.screenRefreshInterval = null;
    }
  },

  toggleScreenAutoRefresh(enabled) {
    if (enabled) {
      this.startScreenAutoRefresh();
    } else {
      this.stopScreenAutoRefresh();
    }
  },

  async refreshScreen() {
    if (!this.selectedService) return;

    const info = this.serviceInfo[this.selectedService];
    if (!info || !info.tmuxSession) return;

    const terminal = document.getElementById('terminal-output');
    if (!terminal) return;

    try {
      const data = await API.get(`/api/screen/${info.tmuxSession}?lines=60`);
      if (data.content) {
        terminal.textContent = this.escapeTerminalContent(data.content);
        terminal.scrollTop = terminal.scrollHeight;
      } else if (data.error) {
        terminal.textContent = `Error: ${data.error}`;
      }
    } catch (error) {
      terminal.textContent = `Failed to load: ${error.message}`;
    }
  },

  escapeTerminalContent(content) {
    // Remove ANSI escape codes but keep the text structure
    return content
      .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')  // ANSI escape sequences
      .replace(/\x1b\].*?\x07/g, '')           // OSC sequences
      .replace(/\r/g, '');                      // Carriage returns
  },

  async sendCommand() {
    const input = document.getElementById('terminal-command');
    if (!input || !input.value.trim()) return;

    const command = input.value.trim();

    // Show confirmation for potentially dangerous commands
    const dangerousPatterns = ['/clear', 'exit', 'kill', 'rm ', 'shutdown'];
    const isDangerous = dangerousPatterns.some(p => command.toLowerCase().includes(p));

    if (isDangerous) {
      if (!confirm(`This command may be destructive. Are you sure you want to send:\n\n${command}`)) {
        return;
      }
    }

    const info = this.serviceInfo[this.selectedService];
    if (!info || !info.tmuxSession) return;

    try {
      await API.post(`/api/send/${info.tmuxSession}?text=${encodeURIComponent(command)}`);
      input.value = '';
      Toast.success('Sent', 'Command sent to session');

      // Refresh screen after a short delay
      setTimeout(() => this.refreshScreen(), 500);
    } catch (error) {
      Toast.error('Error', `Failed to send command: ${error.message}`);
    }
  },

  async clearScreen() {
    const info = this.serviceInfo[this.selectedService];
    if (!info || !info.tmuxSession) return;

    if (!confirm('Send /clear to the session? This will clear the Claude Code context.')) {
      return;
    }

    try {
      await API.post(`/api/send/${info.tmuxSession}?text=${encodeURIComponent('/clear')}`);
      Toast.success('Sent', 'Clear command sent');
      setTimeout(() => this.refreshScreen(), 1000);
    } catch (error) {
      Toast.error('Error', `Failed to clear: ${error.message}`);
    }
  },

  viewLogs(serviceKey) {
    // Navigate to logs view with service filter
    Router.navigate('/logs');
    // The logs view should pick up the service filter
    setTimeout(() => {
      const searchInput = document.querySelector('.data-table-search input');
      if (searchInput) {
        searchInput.value = this.serviceInfo[serviceKey]?.name || serviceKey;
        searchInput.dispatchEvent(new Event('input'));
      }
    }, 100);
  },

  confirmRestart(serviceKey) {
    const info = this.serviceInfo[serviceKey] || { name: serviceKey };

    Modal.open({
      title: 'Confirm Restart',
      content: `
        <div class="confirm-content">
          <div class="confirm-icon">${Icons.refreshCw}</div>
          <div class="confirm-title">Restart ${info.name}?</div>
          <div class="confirm-message">
            This will restart the service. It may take a few seconds to come back online.
          </div>
        </div>
      `,
      footer: `
        <div class="confirm-buttons">
          <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
          <button class="btn btn-primary" onclick="ServicesView.restart('${serviceKey}')">
            ${Icons.refreshCw} Restart
          </button>
        </div>
      `,
    });
  },

  confirmStop(serviceKey) {
    const info = this.serviceInfo[serviceKey] || { name: serviceKey };

    Modal.open({
      title: 'Confirm Stop',
      content: `
        <div class="confirm-content">
          <div class="confirm-icon" style="color: var(--status-error);">${Icons.alertCircle}</div>
          <div class="confirm-title">Stop ${info.name}?</div>
          <div class="confirm-message">
            This will stop the service. You will need to restart it manually.
          </div>
        </div>
      `,
      footer: `
        <div class="confirm-buttons">
          <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
          <button class="btn btn-danger" onclick="ServicesView.stop('${serviceKey}')">
            ${Icons.square} Stop
          </button>
        </div>
      `,
    });
  },

  confirmRestartAll() {
    Modal.open({
      title: 'Confirm Restart All',
      content: `
        <div class="confirm-content">
          <div class="confirm-icon" style="color: var(--status-paused);">${Icons.alertCircle}</div>
          <div class="confirm-title">Restart All Services?</div>
          <div class="confirm-message">
            This will restart all services simultaneously. The system may be temporarily unavailable.
          </div>
        </div>
      `,
      footer: `
        <div class="confirm-buttons">
          <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
          <button class="btn btn-primary" onclick="ServicesView.restartAll()">
            ${Icons.refreshCw} Restart All
          </button>
        </div>
      `,
    });
  },

  async restart(service) {
    Modal.close();

    try {
      await API.post(`/api/restart/${service}`);
      Toast.success('Restarting', `${this.serviceInfo[service]?.name || service} is restarting`);
      setTimeout(() => this.loadData(), 2000);
    } catch (error) {
      Toast.error('Error', `Failed to restart: ${error.message}`);
    }
  },

  async stop(service) {
    Modal.close();

    try {
      await API.post(`/api/stop/${service}`);
      Toast.success('Stopped', `${this.serviceInfo[service]?.name || service} has been stopped`);
      setTimeout(() => this.loadData(), 1000);
    } catch (error) {
      Toast.error('Error', `Failed to stop: ${error.message}`);
    }
  },

  async restartAll() {
    const services = [
      { key: 'hadley_api', name: 'Hadley API', icon: Icons.server },
      { key: 'discord_bot', name: 'Discord Bot', icon: Icons.messageCircle },
      { key: 'hadley_bricks', name: 'Hadley Bricks', icon: Icons.box },
      { key: 'peterbot_session', name: 'Peterbot Session', icon: Icons.terminal },
      { key: 'claude_mem', name: 'Memory Worker', icon: Icons.brain },
    ];

    // Replace modal content with progress view
    const modalBody = document.querySelector('.modal-body');
    const modalFooter = document.querySelector('.modal-footer');
    const modalTitle = document.querySelector('.modal-title');
    if (modalTitle) modalTitle.textContent = 'Restarting Services';
    if (modalFooter) modalFooter.innerHTML = '';

    modalBody.innerHTML = `
      <div class="restart-progress">
        ${services.map(svc => `
          <div class="restart-progress-row" id="restart-row-${svc.key}">
            <span class="restart-svc-icon">${svc.icon}</span>
            <span class="restart-svc-name">${svc.name}</span>
            <span class="restart-status restart-status-pending" id="restart-status-${svc.key}">
              ${Icons.clock}
            </span>
          </div>
        `).join('')}
      </div>
    `;

    let successCount = 0;
    let failCount = 0;

    for (const svc of services) {
      const statusEl = document.getElementById(`restart-status-${svc.key}`);
      const rowEl = document.getElementById(`restart-row-${svc.key}`);
      if (!statusEl || !rowEl) continue;

      // Set to active/spinning
      statusEl.className = 'restart-status restart-status-active';
      statusEl.innerHTML = '<div class="spinner spinner-sm"></div>';
      rowEl.classList.add('restart-row-active');

      try {
        await API.post(`/api/restart/${svc.key}`);
        statusEl.className = 'restart-status restart-status-success';
        statusEl.innerHTML = Icons.checkCircle;
        successCount++;
      } catch (error) {
        statusEl.className = 'restart-status restart-status-failed';
        statusEl.innerHTML = Icons.error;
        failCount++;
      }
      rowEl.classList.remove('restart-row-active');
    }

    // Show summary footer
    if (modalFooter) {
      const summaryClass = failCount === 0 ? 'text-success' : 'text-error';
      const summaryText = failCount === 0
        ? `All ${successCount} services restarted successfully`
        : `${successCount} succeeded, ${failCount} failed`;
      modalFooter.innerHTML = `
        <div class="restart-summary">
          <span class="${summaryClass}">${summaryText}</span>
          <button class="btn btn-primary" onclick="Modal.close(); ServicesView.loadData();">Done</button>
        </div>
      `;
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Service status updated');
  },

  // Cleanup when leaving the view
  destroy() {
    this.stopAutoRefresh();
    this.selectedService = null;
  },
};


/**
 * Skills View - Browse skills
 */
const SkillsView = {
  title: 'Skills',
  skills: [],

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Skills Browser</h2>
            <p class="text-secondary">Browse available skills and their configurations</p>
          </div>
          <div class="data-table-search">
            <span class="data-table-search-icon">${Icons.search}</span>
            <input type="text" placeholder="Search skills..."
                   oninput="SkillsView.filter(this.value)">
          </div>
        </div>

        <div class="grid grid-cols-3 gap-md" id="skills-grid">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>
      </div>
    `;

    await this.loadData();
  },

  async loadData() {
    try {
      const data = await API.get('/api/skills');
      this.skills = data.skills || data || [];
      State.set({ skills: this.skills });
      this.renderSkills(this.skills);
    } catch (error) {
      console.error('Failed to load skills:', error);
      document.getElementById('skills-grid').innerHTML = `
        <div class="col-span-full">
          <div class="empty-state">
            <div class="empty-state-icon">${Icons.alertCircle}</div>
            <div class="empty-state-title">Failed to load skills</div>
            <button class="btn btn-primary mt-md" onclick="SkillsView.loadData()">Retry</button>
          </div>
        </div>
      `;
    }
  },

  renderSkills(skills) {
    if (!skills.length) {
      document.getElementById('skills-grid').innerHTML = `
        <div class="col-span-full">
          <div class="empty-state">
            <div class="empty-state-icon">${Icons.inbox}</div>
            <div class="empty-state-title">No skills found</div>
          </div>
        </div>
      `;
      return;
    }

    const html = skills.map(skill => `
      <div class="card cursor-pointer" onclick="SkillsView.select('${skill.name || skill}')">
        <div class="card-body">
          <h4 class="mb-sm">${skill.name || skill}</h4>
          <p class="text-secondary text-sm mb-md">${skill.description || 'No description'}</p>
          <div class="flex gap-sm">
            ${skill.scheduled ? `<span class="status-badge idle">${Icons.clock} Scheduled</span>` : ''}
            ${skill.triggers ? `<span class="status-badge pending">${Icons.messageCircle} Triggers</span>` : ''}
          </div>
        </div>
      </div>
    `).join('');

    document.getElementById('skills-grid').innerHTML = html;
  },

  filter(query) {
    const filtered = this.skills.filter(s => {
      const name = (s.name || s).toLowerCase();
      const desc = (s.description || '').toLowerCase();
      return name.includes(query.toLowerCase()) || desc.includes(query.toLowerCase());
    });
    this.renderSkills(filtered);
  },

  async select(skillName) {
    try {
      const response = await API.get(`/api/skill/${skillName}`);

      // Handle API response: { exists: bool, content: string, error?: string }
      if (!response.exists) {
        Toast.error('Error', response.error || 'Skill not found');
        return;
      }

      const content = `
        <div class="markdown-preview">${Utils.renderMarkdown(response.content)}</div>
      `;

      DetailPanel.open(content);
    } catch (error) {
      Toast.error('Error', `Failed to load skill: ${error.message}`);
    }
  },
};


/**
 * Logs View - Unified log viewer
 */
const LogsView = {
  title: 'Logs',
  logs: [],
  allLogs: [],
  sources: [],
  currentSource: 'all',
  currentLevel: 'all',
  currentSearch: '',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>System Logs</h2>
            <p class="text-secondary">View logs from all services</p>
          </div>
          <button class="btn btn-secondary" onclick="LogsView.refresh()">
            ${Icons.refresh} Refresh
          </button>
        </div>

        <div class="card">
          <div class="data-table-header">
            <div class="data-table-search">
              <span class="data-table-search-icon">${Icons.search}</span>
              <input type="text" placeholder="Search logs..." id="logs-search-input"
                     oninput="LogsView.search(this.value)">
            </div>
            <div class="data-table-filters">
              <select class="form-select" id="logs-source-filter" onchange="LogsView.filterSource(this.value)">
                <option value="all">All Sources</option>
              </select>
              <select class="form-select" id="logs-level-filter" onchange="LogsView.filterLevel(this.value)">
                <option value="all">All Levels</option>
                <option value="DEBUG">Debug</option>
                <option value="INFO">Info</option>
                <option value="WARNING">Warning</option>
                <option value="ERROR">Error</option>
              </select>
            </div>
          </div>
          <div class="card-body p-0" id="logs-container" style="max-height: 600px; overflow-y: auto;">
            ${Components.skeleton('text', 10)}
          </div>
        </div>
      </div>
    `;

    await this.loadSources();
    await this.loadData();
  },

  async loadSources() {
    try {
      const data = await API.get('/api/logs/sources');
      this.sources = data.sources || [];
      const select = document.getElementById('logs-source-filter');
      if (select && this.sources.length > 0) {
        select.innerHTML = '<option value="all">All Sources</option>' +
          this.sources.map(s => `<option value="${s.name}">${s.display_name}</option>`).join('');
      }
    } catch (error) {
      console.error('Failed to load log sources:', error);
    }
  },

  async loadData() {
    try {
      // Build query params
      const params = new URLSearchParams();
      params.set('limit', '100');
      if (this.currentSource !== 'all') params.set('source', this.currentSource);
      if (this.currentLevel !== 'all') params.set('level', this.currentLevel);
      if (this.currentSearch) params.set('search', this.currentSearch);

      const data = await API.get(`/api/logs/unified?${params.toString()}`);
      // API returns { logs: [...], total: N, has_more: bool }
      this.allLogs = data.logs || [];
      this.logs = this.allLogs;
      this.renderLogs(this.logs);
    } catch (error) {
      console.error('Failed to load logs:', error);
      document.getElementById('logs-container').innerHTML = `
        <div class="empty-state">
          <div class="empty-state-title">Failed to load logs</div>
          <p class="text-secondary">${error.message}</p>
        </div>
      `;
    }
  },

  renderLogs(logs) {
    const container = document.getElementById('logs-container');

    if (!logs.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">${Icons.fileText}</div>
          <div class="empty-state-title">No logs found</div>
          <p class="text-secondary">Try adjusting your filters</p>
        </div>
      `;
      return;
    }

    container.innerHTML = logs.map(log => this.renderLogEntry(log)).join('');
  },

  renderLogEntry(log) {
    const level = (log.level || 'INFO').toLowerCase();
    const source = log.source || 'unknown';
    const message = log.message || '';
    const timestamp = log.timestamp ? Format.time(log.timestamp) : '';

    return `
      <div class="log-entry">
        <span class="log-timestamp">${timestamp}</span>
        <span class="log-level ${level}">[${(log.level || 'INFO').toUpperCase()}]</span>
        <span class="log-source">[${source}]</span>
        <span class="log-message">${Utils.escapeHtml(message)}</span>
      </div>
    `;
  },

  search(query) {
    this.currentSearch = query;
    // Debounce the API call
    clearTimeout(this._searchTimeout);
    this._searchTimeout = setTimeout(() => this.loadData(), 300);
  },

  filterSource(source) {
    this.currentSource = source;
    this.loadData();
  },

  filterLevel(level) {
    this.currentLevel = level;
    this.loadData();
  },

  async refresh() {
    document.getElementById('logs-container').innerHTML = Components.skeleton('text', 10);
    await this.loadData();
    Toast.info('Refreshed', 'Logs updated');
  },
};



/**
 * Files View - Enhanced Configuration File Browser
 * Features: File tree, syntax highlighting, editing, search, tabs, markdown preview
 */
const FilesView = {
  title: 'Files',
  files: [], skills: [], currentFile: null, openTabs: [], activeTabIndex: -1,
  isEditing: false, hasUnsavedChanges: false, originalContent: '',
  searchQuery: '', searchMatches: [], searchCurrentIndex: -1, fileCache: {},
  expandedFolders: { skills: false, logs: false }, maxDisplayLines: 1000, isPreviewMode: false,

  categories: {
    config: { files: ['CLAUDE.md', 'PETERBOT_SOUL.md', 'SCHEDULE.md', 'HEARTBEAT.md', 'USER.md', 'Bot Config'] },
    code: { files: ['Router', 'Parser'] }
  },

  async render(container) {
    this.setupBeforeUnloadWarning();
    container.innerHTML = `
      <div class="animate-fade-in files-view">
        <div class="flex justify-between items-center mb-md">
          <div><h2>File Manager</h2><p class="text-secondary">Browse, view, and edit configuration files</p></div>
          <button class="btn btn-secondary" onclick="FilesView.refresh()">${Icons.refresh} Refresh</button>
        </div>
        <div class="file-tabs-container mb-md" id="file-tabs" style="display: none;"><div class="file-tabs" id="file-tabs-list"></div></div>
        <div class="files-layout">
          <div class="file-tree-sidebar card">
            <div class="card-header"><h3 class="card-title">${Icons.folder} Files</h3></div>
            <div class="card-body p-0" id="file-tree">${Components.skeleton('text', 10)}</div>
          </div>
          <div class="file-content-area">
            <div class="file-info-bar card mb-md" id="file-info-bar" style="display: none;">
              <div class="card-body py-sm"><div class="flex justify-between items-center">
                <div class="flex items-center gap-md"><span class="file-info-path" id="file-info-path"></span><span class="file-info-meta text-muted text-sm" id="file-info-meta"></span></div>
                <div class="flex items-center gap-sm"><span class="file-info-type status-badge idle" id="file-info-type"></span></div>
              </div></div>
            </div>
            <div class="file-toolbar card mb-md" id="file-toolbar" style="display: none;">
              <div class="card-body py-sm"><div class="flex justify-between items-center">
                <div class="flex items-center gap-sm">
                  <button class="btn btn-sm btn-secondary" id="btn-edit" onclick="FilesView.toggleEdit()">${Icons.code} Edit</button>
                  <button class="btn btn-sm btn-secondary" id="btn-preview" onclick="FilesView.togglePreview()" style="display: none;">${Icons.fileText} Preview</button>
                  <span class="toolbar-divider"></span>
                  <button class="btn btn-sm btn-primary" id="btn-save" onclick="FilesView.save()" style="display: none;">${Icons.save} Save</button>
                  <button class="btn btn-sm btn-ghost" id="btn-cancel" onclick="FilesView.cancelEdit()" style="display: none;">Cancel</button>
                </div>
                <div class="flex items-center gap-sm">
                  <div class="file-search-box"><span class="file-search-icon">${Icons.search}</span>
                    <input type="text" id="file-search-input" placeholder="Search in file..." oninput="FilesView.searchInFile(this.value)" onkeydown="FilesView.handleSearchKeydown(event)">
                    <span class="file-search-nav" id="file-search-nav" style="display: none;"><span id="file-search-count">0/0</span>
                      <button class="btn btn-sm btn-ghost" onclick="FilesView.prevMatch()">${Icons.chevronLeft}</button>
                      <button class="btn btn-sm btn-ghost" onclick="FilesView.nextMatch()">${Icons.chevronRight}</button>
                    </span>
                  </div>
                </div>
              </div></div>
            </div>
            <div class="file-content-card card"><div class="card-body p-0">
              <div id="file-viewer-container" class="file-viewer-container">
                <div class="file-placeholder"><div class="empty-state"><div class="empty-state-icon">${Icons.fileText}</div><div class="empty-state-title">Select a file</div><div class="empty-state-description">Choose a file from the tree to view its contents</div></div></div>
              </div>
            </div></div>
          </div>
        </div>
      </div>`;
    await this.loadData();
  },

  async loadData() {
    try {
      const [filesData, skillsData] = await Promise.all([API.get('/api/files'), API.get('/api/skills').catch(() => ({ skills: [] }))]);
      this.files = filesData.files || filesData || [];
      this.skills = skillsData.skills || [];
      this.renderFileTree();
    } catch (error) {
      console.error('Failed to load files:', error);
      document.getElementById('file-tree').innerHTML = `<div class="p-md text-muted">Failed to load files. <button class="btn btn-sm btn-secondary" onclick="FilesView.loadData()">Retry</button></div>`;
    }
  },

  renderFileTree() {
    const windowsFiles = this.files.filter(f => f.type === 'windows' || !f.type);
    const wslFiles = this.files.filter(f => f.type === 'wsl');
    const configFiles = windowsFiles.filter(f => this.categories.config.files.includes(f.name));
    const codeFiles = windowsFiles.filter(f => this.categories.code.files.includes(f.name));
    document.getElementById('file-tree').innerHTML = `<div class="file-tree">
      <div class="file-tree-section"><div class="file-tree-header"><span class="file-tree-icon">${Icons.settings}</span><span class="file-tree-label">Config Files</span></div><div class="file-tree-items">${configFiles.map(f => this.renderFileItem(f)).join('')}</div></div>
      <div class="file-tree-section"><div class="file-tree-header"><span class="file-tree-icon">${Icons.code}</span><span class="file-tree-label">Code Files</span></div><div class="file-tree-items">${codeFiles.map(f => this.renderFileItem(f)).join('')}</div></div>
      <div class="file-tree-section"><div class="file-tree-header file-tree-folder" onclick="FilesView.toggleFolder('skills')"><span class="file-tree-expand ${this.expandedFolders.skills ? 'expanded' : ''}">${Icons.chevronRight}</span><span class="file-tree-icon">${Icons.folder}</span><span class="file-tree-label">Skills</span><span class="file-tree-badge">${this.skills.length}</span></div><div class="file-tree-items file-tree-folder-items ${this.expandedFolders.skills ? 'expanded' : ''}" id="skills-folder">${this.skills.map(s => `<div class="file-tree-item" onclick="FilesView.loadSkill('${s.name}')"><span class="file-tree-icon">${Icons.book}</span><span class="file-tree-label">${s.name}</span></div>`).join('')}</div></div>
      <div class="file-tree-section"><div class="file-tree-header"><span class="file-tree-icon">${Icons.terminal}</span><span class="file-tree-label">WSL Files</span></div><div class="file-tree-items">${wslFiles.map(f => this.renderFileItem(f)).join('')}</div></div>
      <div class="file-tree-section"><div class="file-tree-header file-tree-folder" onclick="FilesView.toggleFolder('logs')"><span class="file-tree-expand ${this.expandedFolders.logs ? 'expanded' : ''}">${Icons.chevronRight}</span><span class="file-tree-icon">${Icons.folder}</span><span class="file-tree-label">Logs</span></div><div class="file-tree-items file-tree-folder-items ${this.expandedFolders.logs ? 'expanded' : ''}" id="logs-folder"><div class="file-tree-item" onclick="FilesView.loadLog('bot')"><span class="file-tree-icon">${Icons.fileText}</span><span class="file-tree-label">discord_bot.log</span></div><div class="file-tree-item" onclick="FilesView.loadLog('raw_capture')"><span class="file-tree-icon">${Icons.fileText}</span><span class="file-tree-label">raw_capture.log</span></div></div></div>
    </div>`;
  },

  renderFileItem(file) {
    const icon = this.getFileIcon(file.name);
    const activeClass = this.currentFile && this.currentFile.name === file.name ? 'active' : '';
    return `<div class="file-tree-item ${activeClass}" onclick="FilesView.loadFile('${file.name}', '${file.type || 'windows'}')"><span class="file-tree-icon">${icon}</span><span class="file-tree-label">${file.name}</span></div>`;
  },

  getFileIcon(filename) {
    if (filename.endsWith('.md')) return Icons.fileText;
    if (filename.endsWith('.py')) return Icons.code;
    if (filename.endsWith('.json')) return Icons.code;
    if (filename.endsWith('.log')) return Icons.activity;
    return Icons.file;
  },

  getFileType(filename) {
    if (filename.endsWith('.md')) return 'markdown';
    if (filename.endsWith('.py')) return 'python';
    if (filename.endsWith('.json')) return 'json';
    if (filename.endsWith('.log')) return 'log';
    return 'text';
  },

  toggleFolder(folder) {
    this.expandedFolders[folder] = !this.expandedFolders[folder];
    const folderEl = document.getElementById(`${folder}-folder`);
    const expandIcon = folderEl?.parentElement?.querySelector('.file-tree-expand');
    if (folderEl) folderEl.classList.toggle('expanded', this.expandedFolders[folder]);
    if (expandIcon) expandIcon.classList.toggle('expanded', this.expandedFolders[folder]);
  },

  async loadFile(name, type) {
    if (this.hasUnsavedChanges && !confirm('You have unsaved changes. Discard them?')) return;
    try {
      const cacheKey = `${type}:${name}`;
      let data = this.fileCache[cacheKey];
      if (!data) { this.showLoading(); data = await API.get(`/api/file/${type}/${encodeURIComponent(name)}`); this.fileCache[cacheKey] = data; }
      const fileInfo = this.files.find(f => f.name === name && (f.type || 'windows') === type);
      this.currentFile = { name, type, content: data.content || '', path: fileInfo?.path || name, modified: fileInfo?.modified, size: data.size };
      this.originalContent = this.currentFile.content;
      this.hasUnsavedChanges = false; this.isEditing = false; this.isPreviewMode = false; this.searchMatches = []; this.searchCurrentIndex = -1;
      this.addTab(name, type); this.showFileInfo(); this.showToolbar(); this.renderFileContent();
    } catch (error) { Toast.error('Error', `Failed to load file: ${error.message}`); }
  },

  async loadSkill(skillName) {
    if (this.hasUnsavedChanges && !confirm('You have unsaved changes. Discard them?')) return;
    try {
      this.showLoading();
      const data = await API.get(`/api/skill/${encodeURIComponent(skillName)}`);
      this.currentFile = { name: `${skillName}/SKILL.md`, type: 'skill', content: data.content || '', path: `/home/chris_hadley/peterbot/.claude/skills/${skillName}/SKILL.md`, skillName };
      this.originalContent = this.currentFile.content; this.hasUnsavedChanges = false; this.isEditing = false; this.isPreviewMode = false;
      this.addTab(`${skillName}/SKILL.md`, 'skill'); this.showFileInfo(); this.showToolbar(); this.renderFileContent();
    } catch (error) { Toast.error('Error', `Failed to load skill: ${error.message}`); }
  },

  async loadLog(logType) {
    try {
      this.showLoading();
      let data = logType === 'bot' ? await API.get('/api/logs/bot') : await API.get('/api/captures');
      this.currentFile = { name: `${logType}.log`, type: 'log', content: data.content || data.logs || 'No log content available', path: logType === 'bot' ? 'logs/bot.log' : 'raw_capture.log', readOnly: true };
      this.originalContent = this.currentFile.content; this.hasUnsavedChanges = false; this.isEditing = false; this.isPreviewMode = false;
      this.addTab(`${logType}.log`, 'log'); this.showFileInfo(); this.showToolbar(); this.renderFileContent();
    } catch (error) { Toast.error('Error', `Failed to load log: ${error.message}`); }
  },

  showLoading() { document.getElementById('file-viewer-container').innerHTML = `<div class="file-loading"><div class="spinner"></div><span>Loading file...</span></div>`; },

  showFileInfo() {
    const infoBar = document.getElementById('file-info-bar');
    if (!this.currentFile) { infoBar.style.display = 'none'; return; }
    infoBar.style.display = 'block';
    document.getElementById('file-info-path').textContent = this.currentFile.path;
    const meta = [];
    if (this.currentFile.modified) meta.push(`Modified: ${Format.datetime(this.currentFile.modified)}`);
    if (this.currentFile.size) meta.push(`Size: ${Format.bytes(this.currentFile.size)}`);
    meta.push(`${this.currentFile.content.split('\n').length} lines`);
    document.getElementById('file-info-meta').textContent = meta.join(' | ');
    document.getElementById('file-info-type').textContent = this.getFileType(this.currentFile.name).toUpperCase();
  },

  showToolbar() {
    document.getElementById('file-toolbar').style.display = 'block';
    document.getElementById('btn-preview').style.display = this.currentFile.name.endsWith('.md') ? 'inline-flex' : 'none';
    document.getElementById('btn-edit').style.display = this.currentFile.readOnly ? 'none' : 'inline-flex';
  },

  renderFileContent() {
    const container = document.getElementById('file-viewer-container');
    const content = this.currentFile.content, fileType = this.getFileType(this.currentFile.name);
    const lines = content.split('\n'), displayLines = lines.slice(0, this.maxDisplayLines), hasMore = lines.length > this.maxDisplayLines;
    if (this.isEditing) {
      container.innerHTML = `<div class="file-editor-container"><textarea id="file-editor" class="file-editor" oninput="FilesView.onEditorChange()">${Utils.escapeHtml(content)}</textarea></div>${hasMore ? `<div class="file-truncated-warning">Note: File has ${lines.length} lines.</div>` : ''}`;
      document.getElementById('file-editor').focus();
    } else if (this.isPreviewMode && this.currentFile.name.endsWith('.md')) {
      container.innerHTML = `<div class="markdown-preview">${this.renderMarkdown(content)}</div>`;
    } else {
      const highlightedLines = displayLines.map((line, idx) => `<div class="file-line" data-line="${idx + 1}"><span class="file-line-number">${idx + 1}</span><span class="file-line-content">${this.highlightSyntax(line, fileType)}</span></div>`).join('');
      container.innerHTML = `<div class="file-viewer" id="file-viewer">${highlightedLines}</div>${hasMore ? `<div class="file-load-more"><button class="btn btn-secondary" onclick="FilesView.loadMoreLines()">Load more (${lines.length - this.maxDisplayLines} remaining)</button></div>` : ''}`;
    }
  },

  highlightSyntax(line, fileType) {
    let escaped = Utils.escapeHtml(line);
    if (fileType === 'markdown') {
      escaped = escaped.replace(/^(#{1,6})\s+(.*)$/, '<span class="syntax-header">$1 $2</span>');
      escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<span class="syntax-bold">**$1**</span>');
      escaped = escaped.replace(/`([^`]+)`/g, '<span class="syntax-code">`$1`</span>');
      escaped = escaped.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<span class="syntax-link">[$1]($2)</span>');
    } else if (fileType === 'python') {
      escaped = escaped.replace(/\b(def|class|import|from|if|elif|else|for|while|try|except|finally|with|as|return|yield|raise|pass|break|continue|and|or|not|in|is|None|True|False|self|async|await|lambda)\b/g, '<span class="syntax-keyword">$1</span>');
      escaped = escaped.replace(/(["'])(?:(?!\1)[^\\]|\\.)*\1/g, '<span class="syntax-string">$&</span>');
      escaped = escaped.replace(/(#.*)$/, '<span class="syntax-comment">$1</span>');
    } else if (fileType === 'json') {
      escaped = escaped.replace(/"([^"]+)":/g, '<span class="syntax-key">"$1"</span>:');
      escaped = escaped.replace(/:\s*"([^"]*)"(,?)/g, ': <span class="syntax-string">"$1"</span>$2');
      escaped = escaped.replace(/:\s*(true|false|null)(,?)/g, ': <span class="syntax-keyword">$1</span>$2');
    } else if (fileType === 'log') {
      escaped = escaped.replace(/^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})/g, '<span class="syntax-timestamp">$1</span>');
      escaped = escaped.replace(/\[(ERROR|WARN|WARNING)\]/gi, '<span class="syntax-error">[$1]</span>');
      escaped = escaped.replace(/\[(INFO)\]/gi, '<span class="syntax-info">[$1]</span>');
    }
    return escaped;
  },

  loadMoreLines() { this.maxDisplayLines += 1000; this.renderFileContent(); },

  addTab(name, type) {
    const existingIdx = this.openTabs.findIndex(t => t.name === name && t.type === type);
    if (existingIdx >= 0) this.activeTabIndex = existingIdx;
    else { this.openTabs.push({ name, type }); this.activeTabIndex = this.openTabs.length - 1; }
    this.renderTabs();
  },

  renderTabs() {
    const tabsContainer = document.getElementById('file-tabs'), tabsList = document.getElementById('file-tabs-list');
    if (this.openTabs.length === 0) { tabsContainer.style.display = 'none'; return; }
    tabsContainer.style.display = 'block';
    tabsList.innerHTML = this.openTabs.map((tab, idx) => {
      const isActive = idx === this.activeTabIndex, hasChanges = isActive && this.hasUnsavedChanges;
      return `<div class="file-tab ${isActive ? 'active' : ''} ${hasChanges ? 'unsaved' : ''}" onclick="FilesView.switchTab(${idx})"><span class="file-tab-icon">${this.getFileIcon(tab.name)}</span><span class="file-tab-name">${tab.name}${hasChanges ? ' *' : ''}</span><button class="file-tab-close" onclick="event.stopPropagation(); FilesView.closeTab(${idx})">${Icons.x}</button></div>`;
    }).join('');
  },

  switchTab(idx) {
    if (idx === this.activeTabIndex) return;
    const tab = this.openTabs[idx];
    if (tab.type === 'skill') this.loadSkill(tab.name.replace('/SKILL.md', ''));
    else if (tab.type === 'log') this.loadLog(tab.name.replace('.log', ''));
    else this.loadFile(tab.name, tab.type);
  },

  closeTab(idx) {
    if (idx === this.activeTabIndex && this.hasUnsavedChanges && !confirm('You have unsaved changes. Discard them?')) return;
    this.openTabs.splice(idx, 1);
    if (this.openTabs.length === 0) {
      this.currentFile = null; this.activeTabIndex = -1; this.hasUnsavedChanges = false;
      document.getElementById('file-info-bar').style.display = 'none';
      document.getElementById('file-toolbar').style.display = 'none';
      document.getElementById('file-viewer-container').innerHTML = `<div class="file-placeholder"><div class="empty-state"><div class="empty-state-icon">${Icons.fileText}</div><div class="empty-state-title">Select a file</div><div class="empty-state-description">Choose a file from the tree to view its contents</div></div></div>`;
    } else if (idx <= this.activeTabIndex) { this.activeTabIndex = Math.max(0, this.activeTabIndex - 1); this.switchTab(this.activeTabIndex); }
    this.renderTabs();
  },

  toggleEdit() {
    if (this.currentFile.readOnly) { Toast.warning('Read Only', 'This file cannot be edited'); return; }
    this.isEditing = !this.isEditing; this.isPreviewMode = false;
    const editBtn = document.getElementById('btn-edit'), saveBtn = document.getElementById('btn-save'), cancelBtn = document.getElementById('btn-cancel'), previewBtn = document.getElementById('btn-preview');
    if (this.isEditing) { editBtn.innerHTML = `${Icons.fileText} View`; saveBtn.style.display = 'inline-flex'; cancelBtn.style.display = 'inline-flex'; previewBtn.style.display = 'none'; }
    else { editBtn.innerHTML = `${Icons.code} Edit`; saveBtn.style.display = 'none'; cancelBtn.style.display = 'none'; previewBtn.style.display = this.currentFile.name.endsWith('.md') ? 'inline-flex' : 'none'; }
    this.renderFileContent();
  },

  onEditorChange() {
    const editor = document.getElementById('file-editor');
    if (editor) { this.currentFile.content = editor.value; this.hasUnsavedChanges = editor.value !== this.originalContent; this.renderTabs(); }
  },

  async save() {
    if (!this.currentFile || !this.hasUnsavedChanges) return;
    try {
      const { name, type, content } = this.currentFile;
      if (type === 'skill') { Toast.warning('Cannot Save', 'Skill files cannot be saved from here yet'); return; }
      await API.put(`/api/file/write/${type}/${encodeURIComponent(name)}?content=${encodeURIComponent(content)}`);
      this.originalContent = content; this.hasUnsavedChanges = false; delete this.fileCache[`${type}:${name}`];
      Toast.success('Saved', `${name} saved successfully`); this.renderTabs();
    } catch (error) { Toast.error('Save Failed', error.message); }
  },

  cancelEdit() {
    if (this.hasUnsavedChanges && !confirm('Discard unsaved changes?')) return;
    this.currentFile.content = this.originalContent; this.hasUnsavedChanges = false; this.isEditing = false;
    document.getElementById('btn-edit').innerHTML = `${Icons.code} Edit`;
    document.getElementById('btn-save').style.display = 'none';
    document.getElementById('btn-cancel').style.display = 'none';
    document.getElementById('btn-preview').style.display = this.currentFile.name.endsWith('.md') ? 'inline-flex' : 'none';
    this.renderFileContent(); this.renderTabs();
  },

  togglePreview() {
    this.isPreviewMode = !this.isPreviewMode;
    document.getElementById('btn-preview').innerHTML = this.isPreviewMode ? `${Icons.code} Code` : `${Icons.fileText} Preview`;
    this.renderFileContent();
  },

  renderMarkdown(content) {
    return Utils.renderMarkdown(content);
  },

  searchInFile(query) {
    this.searchQuery = query;
    const viewer = document.getElementById('file-viewer'), nav = document.getElementById('file-search-nav'), countEl = document.getElementById('file-search-count');
    if (!viewer || !query) { nav.style.display = 'none'; this.searchMatches = []; this.searchCurrentIndex = -1; if (this.currentFile && !this.isEditing) this.renderFileContent(); return; }
    this.searchMatches = [];
    const lines = viewer.querySelectorAll('.file-line'), regex = new RegExp(Utils.escapeRegex(query), 'gi');
    lines.forEach((line, idx) => { const content = line.querySelector('.file-line-content'), text = content.textContent; if (regex.test(text)) { this.searchMatches.push(idx); content.innerHTML = text.replace(regex, '<mark class="search-highlight">$&</mark>'); } regex.lastIndex = 0; });
    if (this.searchMatches.length > 0) { nav.style.display = 'flex'; this.searchCurrentIndex = 0; countEl.textContent = `1/${this.searchMatches.length}`; this.scrollToMatch(0); }
    else { nav.style.display = 'flex'; countEl.textContent = '0/0'; }
  },

  handleSearchKeydown(event) { if (event.key === 'Enter') { event.shiftKey ? this.prevMatch() : this.nextMatch(); } else if (event.key === 'Escape') { document.getElementById('file-search-input').value = ''; this.searchInFile(''); } },
  nextMatch() { if (this.searchMatches.length === 0) return; this.searchCurrentIndex = (this.searchCurrentIndex + 1) % this.searchMatches.length; document.getElementById('file-search-count').textContent = `${this.searchCurrentIndex + 1}/${this.searchMatches.length}`; this.scrollToMatch(this.searchCurrentIndex); },
  prevMatch() { if (this.searchMatches.length === 0) return; this.searchCurrentIndex = (this.searchCurrentIndex - 1 + this.searchMatches.length) % this.searchMatches.length; document.getElementById('file-search-count').textContent = `${this.searchCurrentIndex + 1}/${this.searchMatches.length}`; this.scrollToMatch(this.searchCurrentIndex); },
  scrollToMatch(idx) { const viewer = document.getElementById('file-viewer'), lines = viewer.querySelectorAll('.file-line'); lines.forEach(l => l.classList.remove('search-current')); const matchLine = lines[this.searchMatches[idx]]; if (matchLine) { matchLine.classList.add('search-current'); matchLine.scrollIntoView({ behavior: 'smooth', block: 'center' }); } },

  setupBeforeUnloadWarning() { window.addEventListener('beforeunload', (e) => { if (this.hasUnsavedChanges) { e.preventDefault(); e.returnValue = ''; } }); },

  async refresh() {
    this.fileCache = {};
    await this.loadData();
    if (this.currentFile) {
      const { name, type } = this.currentFile;
      if (type === 'skill') await this.loadSkill(name.replace('/SKILL.md', ''));
      else if (type === 'log') await this.loadLog(name.replace('.log', ''));
      else await this.loadFile(name, type);
    }
    Toast.info('Refreshed', 'File list updated');
  },
};

Utils.escapeRegex = function(string) { return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };


/**
 * Memory View - Memory browser and search
 */
const MemoryView = {
  title: 'Memory',
  peterbotObservations: [],
  claudeObservations: [],

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Memory Systems</h2>
            <p class="text-secondary">Browse and search memory observations</p>
          </div>
          <button class="btn btn-secondary" onclick="MemoryView.refresh()">
            ${Icons.refresh} Refresh
          </button>
        </div>

        ${Components.tabs({
          id: 'memory-tabs',
          tabs: [
            { label: 'Peterbot Memory', badge: '', content: this.renderPeterbotMemory() },
            { label: 'Claude Memory', badge: '', content: this.renderClaudeMemory() },
            { label: 'Second Brain', content: this.renderSecondBrain() },
          ]
        })}
      </div>
    `;

    await this.loadData();
  },

  renderPeterbotMemory() {
    return `
      <div class="mb-md">
        <div class="data-table-search" style="max-width: 400px;">
          <span class="data-table-search-icon">${Icons.search}</span>
          <input type="text" placeholder="Search peterbot memory..."
                 id="peter-memory-search" onkeyup="if(event.key==='Enter')MemoryView.searchPeter(this.value)">
        </div>
      </div>
      <div id="peter-memory-list">
        <div class="flex justify-center py-lg"><div class="spinner"></div></div>
      </div>
    `;
  },

  renderClaudeMemory() {
    return `
      <div class="mb-md">
        <div class="data-table-search" style="max-width: 400px;">
          <span class="data-table-search-icon">${Icons.search}</span>
          <input type="text" placeholder="Search claude memory..."
                 id="claude-memory-search" onkeyup="if(event.key==='Enter')MemoryView.searchClaude(this.value)">
        </div>
      </div>
      <div id="claude-memory-list">
        <div class="flex justify-center py-lg"><div class="spinner"></div></div>
      </div>
    `;
  },

  renderSecondBrain() {
    return `
      <div class="mb-md">
        <div class="data-table-search" style="max-width: 400px;">
          <span class="data-table-search-icon">${Icons.search}</span>
          <input type="text" placeholder="Search second brain..."
                 id="brain-search" onkeyup="if(event.key==='Enter')MemoryView.searchBrain(this.value)">
        </div>
      </div>
      <div id="brain-results">
        <p class="text-muted">Enter a search query to find content</p>
      </div>
    `;
  },

  async loadData() {
    this.loadPeterbotMemories();
    this.loadClaudeMemories();
  },

  async loadPeterbotMemories() {
    const container = document.getElementById('peter-memory-list');
    if (!container) return;
    try {
      const data = await API.get('/api/memory/peter?limit=50');
      this.peterbotObservations = data.observations || [];
      this.renderObservationList('peter-memory-list', this.peterbotObservations, 'peterbot');
      this.updateBadge(0, this.peterbotObservations.length);
    } catch (error) {
      console.error('Error loading peterbot memories:', error);
      container.innerHTML = `<p class="text-error">Failed to load: ${error.message}</p>`;
    }
  },

  async loadClaudeMemories() {
    const container = document.getElementById('claude-memory-list');
    if (!container) return;
    try {
      const data = await API.get('/api/memory/claude?limit=50');
      this.claudeObservations = data.observations || [];
      this.renderObservationList('claude-memory-list', this.claudeObservations, 'claude');
      this.updateBadge(1, this.claudeObservations.length);
    } catch (error) {
      console.error('Error loading claude memories:', error);
      container.innerHTML = `<p class="text-error">Failed to load: ${error.message}</p>`;
    }
  },

  updateBadge(tabIndex, count) {
    const tabs = document.querySelectorAll('#memory-tabs .tab');
    if (tabs[tabIndex]) {
      const badge = tabs[tabIndex].querySelector('.tab-badge');
      if (badge) { badge.textContent = count; }
      else { tabs[tabIndex].insertAdjacentHTML('beforeend', `<span class="tab-badge">${count}</span>`); }
    }
  },

  renderObservationList(containerId, observations, source) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!observations.length) { container.innerHTML = '<p class="text-muted">No observations found</p>'; return; }

    const sourceColors = { 'peterbot': { bg: 'var(--primary)', text: 'white', label: 'Peterbot' }, 'claude': { bg: 'var(--warning)', text: 'black', label: 'Claude' } };

    container.innerHTML = `
      <div class="memory-observations-list">
        ${observations.map(obs => {
          const sourceStyle = sourceColors[source] || sourceColors['claude'];
          const typeIcon = this.getTypeIcon(obs.type);
          return `
            <div class="memory-observation-item" onclick="MemoryView.showObservationDetail(${obs.id}, '${source}')">
              <div class="memory-obs-header">
                <div class="memory-obs-left">
                  <span class="memory-obs-id">#${obs.id}</span>
                  <span class="memory-obs-source" style="background: ${sourceStyle.bg}; color: ${sourceStyle.text};">${sourceStyle.label}</span>
                  <span class="memory-obs-type">${typeIcon} ${obs.type || 'observation'}</span>
                  ${obs.project && obs.project !== 'peterbot' ? `<span class="memory-obs-project">${obs.project}</span>` : ''}
                </div>
                <span class="memory-obs-time">${Format.datetime(obs.created_at)}</span>
              </div>
              <div class="memory-obs-title">${Utils.escapeHtml(obs.title || 'Untitled')}</div>
              ${obs.subtitle ? `<div class="memory-obs-subtitle">${Utils.escapeHtml(obs.subtitle)}</div>` : ''}
              ${obs.category ? `<span class="memory-obs-category">${obs.category}</span>` : ''}
            </div>`;
        }).join('')}
      </div>
      <style>
        .memory-observations-list { display: flex; flex-direction: column; gap: 8px; }
        .memory-observation-item { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; cursor: pointer; transition: all 0.2s ease; }
        .memory-observation-item:hover { border-color: var(--primary); transform: translateX(4px); }
        .memory-obs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
        .memory-obs-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .memory-obs-id { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); }
        .memory-obs-source { font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
        .memory-obs-type { font-size: 12px; color: var(--text-secondary); }
        .memory-obs-project { font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; }
        .memory-obs-time { font-size: 12px; color: var(--text-muted); }
        .memory-obs-title { font-weight: 500; margin-bottom: 4px; }
        .memory-obs-subtitle { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
        .memory-obs-category { display: inline-block; font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 8px; border-radius: 12px; margin-top: 4px; }
      </style>
    `;
  },

  getTypeIcon(type) {
    const icons = { 'observation': '[ ]', 'task': '[x]', 'decision': '[!]', 'learning': '[i]', 'preference': '[*]', 'context': '[-]', 'error': '[E]', 'success': '[S]' };
    return icons[type] || '[ ]';
  },

  showObservationDetail(id, source) {
    const observations = source === 'peterbot' ? this.peterbotObservations : this.claudeObservations;
    const obs = observations.find(o => o.id === id);
    if (!obs) return;

    const content = `
      <div class="mb-lg">
        <div class="flex items-center gap-sm mb-md">
          <span class="text-lg font-bold">#${obs.id}</span>
          <span class="status-badge ${source === 'peterbot' ? 'info' : 'warning'}">${source}</span>
          <span class="status-badge">${obs.type || 'observation'}</span>
        </div>
        <h3 class="mb-sm">${Utils.escapeHtml(obs.title || 'Untitled')}</h3>
        ${obs.subtitle ? `<p class="text-secondary mb-md">${Utils.escapeHtml(obs.subtitle)}</p>` : ''}
      </div>
      <div class="mb-md"><label class="text-sm text-muted">Created</label><p>${Format.datetime(obs.created_at)}</p></div>
      ${obs.project ? `<div class="mb-md"><label class="text-sm text-muted">Project</label><p>${obs.project}</p></div>` : ''}
      ${obs.category ? `<div class="mb-md"><label class="text-sm text-muted">Category</label><p>${obs.category}</p></div>` : ''}
      ${obs.narrative ? `<div class="mb-md"><label class="text-sm text-muted">Narrative</label><p>${Utils.escapeHtml(obs.narrative)}</p></div>` : ''}
      ${obs.facts && obs.facts !== '[]' ? `<div class="mb-md"><label class="text-sm text-muted">Facts</label><pre class="code-block" style="max-height: 200px; overflow-y: auto;">${Utils.escapeHtml(typeof obs.facts === 'string' ? obs.facts : JSON.stringify(obs.facts, null, 2))}</pre></div>` : ''}
      <div class="mb-md"><label class="text-sm text-muted">Status</label><p>${obs.is_active ? 'Active' : 'Inactive'}</p></div>
    `;
    DetailPanel.open(content);
  },

  async searchPeter(query) {
    if (!query.trim()) { this.renderObservationList('peter-memory-list', this.peterbotObservations, 'peterbot'); return; }
    try {
      const results = await API.get(`/api/search/memory?query=${encodeURIComponent(query)}`);
      if (results.observations) { this.renderObservationList('peter-memory-list', results.observations, 'peterbot'); }
      else if (results.results) { this.renderSearchResults('peter-memory-list', results.results); }
    } catch (error) { Toast.error('Error', `Search failed: ${error.message}`); }
  },

  async searchClaude(query) {
    if (!query.trim()) { this.renderObservationList('claude-memory-list', this.claudeObservations, 'claude'); return; }
    const filtered = this.claudeObservations.filter(obs =>
      (obs.title && obs.title.toLowerCase().includes(query.toLowerCase())) ||
      (obs.subtitle && obs.subtitle.toLowerCase().includes(query.toLowerCase())) ||
      (obs.narrative && obs.narrative.toLowerCase().includes(query.toLowerCase()))
    );
    this.renderObservationList('claude-memory-list', filtered, 'claude');
  },

  async searchBrain(query) {
    if (!query.trim()) return;
    try {
      const results = await API.get(`/api/search/second-brain?query=${encodeURIComponent(query)}`);
      this.renderSearchResults('brain-results', results.results || []);
    } catch (error) { Toast.error('Error', `Search failed: ${error.message}`); }
  },

  renderSearchResults(containerId, results) {
    const container = document.getElementById(containerId);
    if (!results.length) { container.innerHTML = '<p class="text-muted">No results found</p>'; return; }
    container.innerHTML = results.map(r => `
      <div class="card mb-sm">
        <div class="card-body">
          <div class="flex justify-between items-center mb-sm">
            <span class="text-xs text-muted">#${r.id || '-'}</span>
            <span class="text-xs text-muted">${Format.datetime(r.timestamp || r.created_at)}</span>
          </div>
          <p>${Utils.escapeHtml(r.content || r.text || r.title || '')}</p>
        </div>
      </div>
    `).join('');
  },

  async refresh() {
    Toast.info('Refreshing', 'Loading memories...');
    await this.loadData();
    Toast.success('Done', 'Memories refreshed');
  },
};


/**
 * Settings View
 */
const SettingsView = {
  title: 'Settings',

  render(container) {
    const darkMode = document.documentElement.getAttribute('data-theme') === 'dark';

    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="mb-lg">
          <h2>Settings</h2>
          <p class="text-secondary">Configure dashboard preferences</p>
        </div>

        <div class="card" style="max-width: 600px;">
          <div class="card-body">
            <h3 class="mb-lg">Appearance</h3>

            <div class="form-group">
              <label class="form-checkbox-group">
                <input type="checkbox" class="form-checkbox"
                       ${darkMode ? 'checked' : ''}
                       onchange="SettingsView.toggleDarkMode(this.checked)">
                <span>Dark Mode</span>
              </label>
              <p class="form-help">Enable dark color theme</p>
            </div>

            <div class="form-group">
              <label class="form-checkbox-group">
                <input type="checkbox" class="form-checkbox"
                       ${State.get('sidebarCollapsed') ? 'checked' : ''}
                       onchange="SettingsView.toggleSidebar(this.checked)">
                <span>Collapse Sidebar</span>
              </label>
              <p class="form-help">Start with sidebar collapsed</p>
            </div>

            <h3 class="mb-lg mt-xl">Notifications</h3>

            <div class="form-group">
              <label class="form-checkbox-group">
                <input type="checkbox" class="form-checkbox" checked disabled>
                <span>Show Error Alerts</span>
              </label>
              <p class="form-help">Display toast notifications for errors</p>
            </div>

            <h3 class="mb-lg mt-xl">Data</h3>

            <div class="form-group">
              <label class="form-label">Auto-refresh Interval</label>
              <select class="form-select" style="max-width: 200px;">
                <option value="5000">5 seconds</option>
                <option value="10000" selected>10 seconds</option>
                <option value="30000">30 seconds</option>
                <option value="60000">1 minute</option>
                <option value="0">Manual only</option>
              </select>
              <p class="form-help">How often to refresh dashboard data</p>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  toggleDarkMode(enabled) {
    document.documentElement.setAttribute('data-theme', enabled ? 'dark' : 'light');
    localStorage.setItem('theme', enabled ? 'dark' : 'light');
  },

  toggleSidebar(collapsed) {
    State.set({ sidebarCollapsed: collapsed });
    localStorage.setItem('sidebarCollapsed', collapsed);
    document.getElementById('sidebar').classList.toggle('collapsed', collapsed);
  },
};


/**
 * Parser View - Monitor parser system status, captures, feedback, and cycles
 */
const ParserView = {
  title: 'Parser',
  status: null,
  captures: [],
  feedback: [],
  cycles: [],
  activeTab: 'status',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Parser System</h2>
            <p class="text-secondary">Monitor and manage the self-improving parser</p>
          </div>
          <div class="flex gap-sm">
            <button class="btn btn-secondary" onclick="ParserView.runRegression()">
              ${Icons.play} Run Regression
            </button>
            <button class="btn btn-secondary" onclick="ParserView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
        </div>

        <!-- Status Cards -->
        <div class="grid grid-cols-4 gap-md mb-lg" id="parser-status-cards">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        <!-- Tabs -->
        <div class="tabs mb-lg">
          <button class="tab ${this.activeTab === 'status' ? 'active' : ''}" onclick="ParserView.switchTab('status')">Fixtures</button>
          <button class="tab ${this.activeTab === 'captures' ? 'active' : ''}" onclick="ParserView.switchTab('captures')">Captures</button>
          <button class="tab ${this.activeTab === 'feedback' ? 'active' : ''}" onclick="ParserView.switchTab('feedback')">Feedback</button>
          <button class="tab ${this.activeTab === 'cycles' ? 'active' : ''}" onclick="ParserView.switchTab('cycles')">Improvement Cycles</button>
        </div>

        <!-- Tab Content -->
        <div class="card" id="parser-tab-content">
          <div class="card-body">
            ${Components.skeleton('list')}
          </div>
        </div>
      </div>
    `;

    await this.loadData();
  },

  async loadData() {
    try {
      // Load all data in parallel
      const [statusRes, capturesRes, feedbackRes, cyclesRes] = await Promise.all([
        API.get('/api/parser/status'),
        API.get('/api/parser/captures'),
        API.get('/api/parser/feedback'),
        API.get('/api/parser/cycles')
      ]);

      this.status = statusRes;
      this.captures = capturesRes.captures || [];
      this.feedback = feedbackRes.feedback || [];
      this.cycles = cyclesRes.cycles || [];

      this.renderStatusCards();
      this.renderTabContent();
    } catch (error) {
      console.error('Failed to load parser data:', error);
      document.getElementById('parser-status-cards').innerHTML = `
        <div class="col-span-full">
          <div class="empty-state">
            <div class="empty-state-icon">${Icons.alertCircle}</div>
            <div class="empty-state-title">Failed to load parser status</div>
            <p class="text-secondary">${error.message}</p>
            <button class="btn btn-primary mt-md" onclick="ParserView.loadData()">Retry</button>
          </div>
        </div>
      `;
    }
  },

  renderStatusCards() {
    if (!this.status) return;

    const s = this.status;
    const cards = `
      <div class="stat-card">
        <div class="stat-card-icon" style="background: var(--success-bg); color: var(--success);">
          ${Icons.check}
        </div>
        <div class="stat-card-content">
          <div class="stat-card-value">${s.fixtures_loaded || 0}</div>
          <div class="stat-card-label">Fixtures Loaded</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-card-icon" style="background: var(--info-bg); color: var(--info);">
          ${Icons.messageCircle}
        </div>
        <div class="stat-card-content">
          <div class="stat-card-value">${s.captures_today || 0}</div>
          <div class="stat-card-label">Captures Today</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-card-icon" style="background: var(--warning-bg); color: var(--warning);">
          ${Icons.alertCircle}
        </div>
        <div class="stat-card-content">
          <div class="stat-card-value">${s.pending_feedback || 0}</div>
          <div class="stat-card-label">Pending Feedback</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-card-icon" style="background: var(--accent-bg); color: var(--accent);">
          ${Icons.activity}
        </div>
        <div class="stat-card-content">
          <div class="stat-card-value">${s.improvement_cycles || 0}</div>
          <div class="stat-card-label">Improvement Cycles</div>
        </div>
      </div>
    `;

    document.getElementById('parser-status-cards').innerHTML = cards;
  },

  switchTab(tab) {
    this.activeTab = tab;
    // Update tab buttons
    document.querySelectorAll('.tabs .tab').forEach(btn => {
      btn.classList.toggle('active', btn.textContent.toLowerCase().includes(tab));
    });
    this.renderTabContent();
  },

  renderTabContent() {
    const container = document.getElementById('parser-tab-content');
    let content = '';

    switch (this.activeTab) {
      case 'status':
        content = this.renderFixturesTab();
        break;
      case 'captures':
        content = this.renderCapturesTab();
        break;
      case 'feedback':
        content = this.renderFeedbackTab();
        break;
      case 'cycles':
        content = this.renderCyclesTab();
        break;
    }

    container.innerHTML = `<div class="card-body">${content}</div>`;
  },

  renderFixturesTab() {
    if (!this.status || !this.status.fixtures) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">${Icons.inbox}</div>
          <div class="empty-state-title">No fixtures loaded</div>
          <p class="text-secondary">Parser fixtures are not configured</p>
        </div>
      `;
    }

    const fixtures = this.status.fixtures;
    const rows = Object.entries(fixtures).map(([name, data]) => `
      <tr>
        <td><code>${Utils.escapeHtml(name)}</code></td>
        <td>${data.count || 0} examples</td>
        <td>${data.last_updated ? Format.relativeTime(data.last_updated) : '-'}</td>
        <td>
          <span class="status-badge ${data.healthy ? 'success' : 'warning'}">
            ${data.healthy ? 'Healthy' : 'Needs Review'}
          </span>
        </td>
      </tr>
    `).join('');

    return `
      <table class="data-table">
        <thead>
          <tr>
            <th>Fixture</th>
            <th>Examples</th>
            <th>Last Updated</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows || '<tr><td colspan="4" class="text-center text-muted">No fixtures found</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderCapturesTab() {
    if (!this.captures.length) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">${Icons.messageCircle}</div>
          <div class="empty-state-title">No recent captures</div>
          <p class="text-secondary">Parser captures will appear here as messages are processed</p>
        </div>
      `;
    }

    const rows = this.captures.map(c => `
      <tr class="cursor-pointer" onclick="ParserView.showCapture('${c.id}')">
        <td><code class="text-sm">${Utils.escapeHtml(c.id?.substring(0, 8) || '-')}...</code></td>
        <td>${Utils.escapeHtml(c.intent || 'unknown')}</td>
        <td class="text-truncate" style="max-width: 300px;">${Utils.escapeHtml(c.input?.substring(0, 50) || '-')}...</td>
        <td>${Format.relativeTime(c.timestamp)}</td>
        <td>
          <span class="status-badge ${c.success ? 'success' : 'error'}">
            ${c.success ? 'Success' : 'Failed'}
          </span>
        </td>
      </tr>
    `).join('');

    return `
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Intent</th>
            <th>Input</th>
            <th>Time</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;
  },

  renderFeedbackTab() {
    if (!this.feedback.length) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">${Icons.check}</div>
          <div class="empty-state-title">No pending feedback</div>
          <p class="text-secondary">All feedback items have been resolved</p>
        </div>
      `;
    }

    const rows = this.feedback.map(f => `
      <tr>
        <td><code class="text-sm">${Utils.escapeHtml(f.id?.substring(0, 8) || '-')}...</code></td>
        <td>${Utils.escapeHtml(f.type || 'unknown')}</td>
        <td class="text-truncate" style="max-width: 300px;">${Utils.escapeHtml(f.message?.substring(0, 50) || '-')}...</td>
        <td>${Format.relativeTime(f.created_at)}</td>
        <td>
          <button class="btn btn-sm btn-secondary" onclick="ParserView.resolveFeedback('${f.id}')">
            Resolve
          </button>
        </td>
      </tr>
    `).join('');

    return `
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Type</th>
            <th>Message</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;
  },

  renderCyclesTab() {
    if (!this.cycles.length) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">${Icons.activity}</div>
          <div class="empty-state-title">No improvement cycles</div>
          <p class="text-secondary">Parser improvement cycles will appear here as the system learns</p>
        </div>
      `;
    }

    const rows = this.cycles.map(c => `
      <tr>
        <td><code class="text-sm">${c.version || '-'}</code></td>
        <td>${c.changes_count || 0} changes</td>
        <td>${Format.datetime(c.started_at)}</td>
        <td>
          <span class="status-badge ${c.status === 'completed' ? 'success' : c.status === 'failed' ? 'error' : 'pending'}">
            ${c.status || 'unknown'}
          </span>
        </td>
        <td>
          ${c.regression_passed !== undefined ? (c.regression_passed ?
            `<span class="text-success">${Icons.check} Passed</span>` :
            `<span class="text-error">${Icons.x} Failed</span>`) : '-'}
        </td>
      </tr>
    `).join('');

    return `
      <table class="data-table">
        <thead>
          <tr>
            <th>Version</th>
            <th>Changes</th>
            <th>Started</th>
            <th>Status</th>
            <th>Regression</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;
  },

  showCapture(captureId) {
    const capture = this.captures.find(c => c.id === captureId);
    if (!capture) return;

    const content = `
      <h4 class="mb-md">Capture Details</h4>
      <div class="mb-md">
        <label class="text-sm text-muted">ID</label>
        <p><code>${Utils.escapeHtml(capture.id)}</code></p>
      </div>
      <div class="mb-md">
        <label class="text-sm text-muted">Intent</label>
        <p>${Utils.escapeHtml(capture.intent || 'unknown')}</p>
      </div>
      <div class="mb-md">
        <label class="text-sm text-muted">Input</label>
        <pre class="code-block">${Utils.escapeHtml(capture.input || '')}</pre>
      </div>
      <div class="mb-md">
        <label class="text-sm text-muted">Output</label>
        <pre class="code-block">${Utils.escapeHtml(JSON.stringify(capture.output, null, 2) || '')}</pre>
      </div>
      <div class="mb-md">
        <label class="text-sm text-muted">Timestamp</label>
        <p>${Format.datetime(capture.timestamp)}</p>
      </div>
    `;

    DetailPanel.open(content);
  },

  async runRegression() {
    try {
      Toast.info('Running', 'Starting regression tests...');
      const result = await API.post('/api/parser/run-regression');
      if (result.success) {
        Toast.success('Complete', 'Regression tests completed');
        await this.loadData();
      } else {
        Toast.error('Failed', result.error || 'Regression tests failed');
      }
    } catch (error) {
      Toast.error('Error', `Failed to run regression: ${error.message}`);
    }
  },

  async resolveFeedback(feedbackId) {
    try {
      await API.post(`/api/parser/feedback/${feedbackId}/resolve`);
      Toast.success('Resolved', 'Feedback item marked as resolved');
      await this.loadData();
    } catch (error) {
      Toast.error('Error', `Failed to resolve feedback: ${error.message}`);
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Parser data updated');
  },
};


// =============================================================================
// 7. UTILITIES
// =============================================================================

/**
 * Formatting utilities
 */
const Format = {
  time(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  },

  datetime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit'
    });
  },

  relativeTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = date - now;
    const absDiff = Math.abs(diff);

    const minutes = Math.floor(absDiff / 60000);
    const hours = Math.floor(absDiff / 3600000);
    const days = Math.floor(absDiff / 86400000);

    if (diff < 0) {
      // Past
      if (minutes < 1) return 'Just now';
      if (minutes < 60) return `${minutes}m ago`;
      if (hours < 24) return `${hours}h ago`;
      return `${days}d ago`;
    } else {
      // Future
      if (minutes < 60) return `in ${minutes}m`;
      if (hours < 24) return `in ${hours}h`;
      return `in ${days}d`;
    }
  },

  serviceName(key) {
    const names = {
      hadley_api: 'Hadley API',
      discord_bot: 'Discord Bot',
      claude_mem: 'Claude Memory',
      peterbot_session: 'Peterbot Session',
      hadley_bricks: 'Hadley Bricks',
    };
    return names[key] || key;
  },

  bytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  },
};


/**
 * Costs View - CLI cost tracking and analysis
 */
const CostsView = {
  title: 'CLI Costs',
  _data: null,
  _days: 7,

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex items-center justify-between mb-lg">
          <div class="flex items-center gap-sm">
            <select id="costs-days-filter" class="form-input" style="width: auto;">
              <option value="1">Last 24h</option>
              <option value="7" selected>Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="0">All time</option>
            </select>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="CostsView.refresh()">
            ${Icons.refresh} Refresh
          </button>
        </div>

        <div class="grid grid-cols-4 gap-md mb-lg" id="costs-stats">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        <div class="grid grid-cols-2 gap-md mb-lg">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Cost by Day</h3>
            </div>
            <div class="card-body" id="costs-by-day">
              ${Components.skeleton('table', 5)}
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Cost by Model</h3>
            </div>
            <div class="card-body" id="costs-by-model">
              ${Components.skeleton('table', 3)}
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Call Log</h3>
          </div>
          <div class="card-body" id="costs-table">
            ${Components.skeleton('table', 10)}
          </div>
        </div>
      </div>
    `;

    document.getElementById('costs-days-filter').addEventListener('change', (e) => {
      this._days = parseInt(e.target.value);
      this.refresh();
    });

    await this.loadData();
  },

  async refresh() {
    await this.loadData();
  },

  async loadData() {
    try {
      const data = await API.get(`/api/costs?days=${this._days}`);
      this._data = data;
      this._channelMap = data.channel_map || {};
      this.renderStats(data.summary);
      this.renderByDay(data.summary.by_day || {});
      this.renderByModel(data.summary.by_model || {});
      this.renderTable(data.entries || []);
    } catch (error) {
      console.error('Failed to load cost data:', error);
      Toast.error('Error', 'Failed to load cost data');
    }
  },

  _resolveChannel(raw) {
    // "Channel 1465294449038069912" → "food-log" or "#api-costs" → "api-costs"
    if (!raw) return '-';
    const idMatch = raw.match(/(\d{17,20})/);
    if (idMatch && this._channelMap && this._channelMap[idMatch[1]]) {
      return this._channelMap[idMatch[1]];
    }
    return raw.replace('Channel ', '#').replace(/^#peter-/, '').replace(/^#/, '');
  },

  renderStats(summary) {
    const el = document.getElementById('costs-stats');
    if (!el) return;

    el.innerHTML = `
      ${Components.statsCard({
        icon: Icons.activity,
        value: '\u00A3' + (summary.total_gbp || 0).toFixed(2),
        label: 'Total Cost (GBP)',
        variant: 'info'
      })}
      ${Components.statsCard({
        icon: Icons.checkCircle,
        value: summary.total_calls || 0,
        label: 'Total Calls',
        variant: 'success'
      })}
      ${Components.statsCard({
        icon: Icons.clock,
        value: summary.avg_duration_ms ? (summary.avg_duration_ms / 1000).toFixed(1) + 's' : '-',
        label: 'Avg Duration',
        variant: 'info'
      })}
      ${Components.statsCard({
        icon: Icons.alertCircle,
        value: '$' + (summary.total_usd || 0).toFixed(2),
        label: 'Total Cost (USD)',
        variant: 'warning'
      })}
    `;
  },

  renderByDay(byDay) {
    const el = document.getElementById('costs-by-day');
    if (!el) return;

    const days = Object.entries(byDay);
    if (days.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No data</p>';
      return;
    }

    const rows = days.map(([day, d]) => `
      <tr>
        <td class="font-mono text-sm">${day}</td>
        <td class="text-right">${d.calls}</td>
        <td class="text-right font-mono">\u00A3${d.cost_gbp.toFixed(2)}</td>
        <td class="text-right font-mono text-muted">$${d.cost_usd.toFixed(2)}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      <table class="table">
        <thead>
          <tr>
            <th>Date</th>
            <th class="text-right">Calls</th>
            <th class="text-right">GBP</th>
            <th class="text-right">USD</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  renderByModel(byModel) {
    const el = document.getElementById('costs-by-model');
    if (!el) return;

    const models = Object.entries(byModel);
    if (models.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No data</p>';
      return;
    }

    const rows = models.map(([model, d]) => {
      const shortModel = model.replace('claude-', '').replace(/-\d{8}$/, '');
      return `
        <tr>
          <td><span class="status status-running">${Utils.escapeHtml(shortModel)}</span></td>
          <td class="text-right">${d.calls}</td>
          <td class="text-right font-mono">\u00A3${d.cost_gbp.toFixed(2)}</td>
          <td class="text-right font-mono text-muted">$${d.cost_usd.toFixed(2)}</td>
        </tr>
      `;
    }).join('');

    el.innerHTML = `
      <table class="table">
        <thead>
          <tr>
            <th>Model</th>
            <th class="text-right">Calls</th>
            <th class="text-right">GBP</th>
            <th class="text-right">USD</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  renderTable(entries) {
    const el = document.getElementById('costs-table');
    if (!el) return;

    if (entries.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No cost data recorded yet</p>';
      return;
    }

    const rows = entries.map(e => {
      const time = Format.datetime(e.timestamp);
      const source = e.source || '-';
      // Shorten "scheduled:balance-monitor" → "sched:balance"
      const sourceShort = source.startsWith('scheduled:')
        ? source.replace('scheduled:', 'sched:').replace('-monitor', '')
        : source;
      const sourceClass = source === 'conversation' ? 'status-running' : 'status-pending';
      const channel = this._resolveChannel(e.channel);
      const model = (e.model || 'unknown').replace('claude-', '').replace(/-\d{8,}$/, '');
      const duration = e.duration_ms ? (e.duration_ms / 1000).toFixed(1) + 's' : '-';
      const tools = (e.tools_used || []);
      const uniqueTools = [...new Set(tools)];
      const toolStr = uniqueTools.length > 0
        ? uniqueTools.slice(0, 3).join(', ') + (uniqueTools.length > 3 ? ` +${uniqueTools.length - 3}` : '')
        : '-';
      const msg = Utils.escapeHtml((e.message || '').substring(0, 40));
      const costUsd = (e.cost_usd || 0);
      const costGbp = (e.cost_gbp || 0);
      const costClass = costUsd === 0 ? 'text-muted' : costUsd > 0.20 ? 'text-warning' : '';

      return `
        <tr>
          <td class="text-sm text-muted" style="white-space: nowrap;">${time}</td>
          <td class="text-sm"><span class="status ${sourceClass}">${Utils.escapeHtml(sourceShort)}</span></td>
          <td class="text-sm">${Utils.escapeHtml(channel)}</td>
          <td class="text-sm font-mono">${Utils.escapeHtml(model)}</td>
          <td class="text-right font-mono ${costClass}" style="padding-right: 12px;">\u00A3${costGbp.toFixed(3)}</td>
          <td class="text-right text-sm text-muted" style="padding-left: 12px;">${duration}</td>
          <td class="text-sm text-muted">${toolStr}</td>
          <td class="text-sm text-muted" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${Utils.escapeHtml(e.message || '')}">${msg}</td>
        </tr>
      `;
    }).join('');

    el.innerHTML = `
      <div style="overflow-x: auto;">
        <table class="table" style="table-layout: auto; width: 100%;">
          <thead>
            <tr>
              <th style="white-space: nowrap;">Time</th>
              <th>Source</th>
              <th>Channel</th>
              <th>Model</th>
              <th class="text-right" style="padding-right: 12px;">Cost</th>
              <th class="text-right" style="padding-left: 12px;">Duration</th>
              <th>Tools</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  },
};


// =============================================================================
// TASKS VIEW — Kanban Board
// =============================================================================

const TasksView = {
  title: 'Tasks',
  HADLEY_API: '/api/hadley/proxy',
  _tasks: [],
  _counts: {},
  _categories: [],
  _activeList: 'personal_todo',
  _dragTaskId: null,

  LIST_TYPES: [
    { key: 'personal_todo', label: 'Todos', icon: Icons.checkCircle },
    { key: 'peter_queue', label: 'Peter Queue', icon: Icons.zap },
    { key: 'idea', label: 'Ideas', icon: Icons.star },
    { key: 'research', label: 'Research', icon: Icons.search },
  ],

  // Columns shown per list type (order = left to right)
  COLUMNS: {
    personal_todo: ['inbox', 'scheduled', 'in_progress', 'done'],
    peter_queue:   ['queued', 'heartbeat_scheduled', 'in_heartbeat', 'in_progress', 'review', 'done'],
    idea:          ['inbox', 'scheduled', 'review', 'done'],
    research:      ['queued', 'in_progress', 'findings_ready', 'done'],
  },

  COLUMN_CONFIG: {
    inbox:               { label: 'Inbox',        color: '#6B7280', accent: '#E5E7EB' },
    scheduled:           { label: 'Scheduled',    color: '#2563EB', accent: '#BFDBFE' },
    queued:              { label: 'Queued',        color: '#7C3AED', accent: '#DDD6FE' },
    heartbeat_scheduled: { label: 'HB Scheduled',  color: '#D97706', accent: '#FDE68A' },
    in_heartbeat:        { label: 'In Heartbeat',  color: '#EA580C', accent: '#FED7AA' },
    in_progress:         { label: 'In Progress',   color: '#059669', accent: '#A7F3D0' },
    review:              { label: 'Review',        color: '#7C3AED', accent: '#DDD6FE' },
    findings_ready:      { label: 'Findings Ready', color: '#059669', accent: '#A7F3D0' },
    done:                { label: 'Done',          color: '#16A34A', accent: '#BBF7D0' },
    cancelled:           { label: 'Cancelled',     color: '#9CA3AF', accent: '#E5E7EB' },
  },

  PRIORITY_CONFIG: {
    critical: { label: 'Critical', color: '#DC2626', bg: '#FEE2E2' },
    high:     { label: 'High',     color: '#EA580C', bg: '#FFF7ED' },
    medium:   { label: 'Medium',   color: '#2563EB', bg: '#EFF6FF' },
    low:      { label: 'Low',      color: '#6B7280', bg: '#F3F4F6' },
    someday:  { label: 'Someday',  color: '#9CA3AF', bg: '#F9FAFB' },
  },

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Tasks</h2>
            <p class="text-secondary" id="tasks-subtitle">To-dos, ideas, research & Peter's work queue</p>
          </div>
          <div class="flex gap-sm">
            <button class="btn btn-primary" onclick="TasksView.showCreateModal()">
              ${Icons.plus} New Task
            </button>
            <button class="btn btn-ghost" onclick="TasksView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-md mb-lg" id="tasks-stats">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        <div class="flex gap-sm mb-md" id="tasks-tab-bar">
          ${this.LIST_TYPES.map(lt => `
            <button class="btn ${lt.key === this._activeList ? 'btn-primary' : 'btn-secondary'}"
                    onclick="TasksView.switchList('${lt.key}')"
                    data-list="${lt.key}">
              ${lt.icon} ${lt.label}
              <span class="kb-tab-count" id="tab-count-${lt.key}"></span>
            </button>
          `).join('')}
        </div>

        <div class="kb-filter-bar" id="kb-filters">
          <input type="text" id="kb-search" placeholder="Search tasks..." onkeyup="TasksView.applyFilters()">
          <select id="kb-filter-priority" onchange="TasksView.applyFilters()">
            <option value="">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="someday">Someday</option>
          </select>
          <select id="kb-filter-category" onchange="TasksView.applyFilters()">
            <option value="">All Categories</option>
          </select>
        </div>

        <div id="kanban-board" class="kb-board">
          ${Components.skeleton('table', 5)}
        </div>
      </div>
    `;
    await this.loadData();
  },

  async loadData() {
    try {
      const [countsResp, tasksResp, catsResp] = await Promise.all([
        fetch(`${this.HADLEY_API}/ptasks/counts`),
        fetch(`${this.HADLEY_API}/ptasks/list/${this._activeList}?include_done=true`),
        fetch(`${this.HADLEY_API}/ptasks/categories`),
      ]);

      this._counts = (await countsResp.json()).counts || {};
      this._tasks = (await tasksResp.json()).tasks || [];
      this._categories = (await catsResp.json()).categories || [];

      this.renderStats();
      this.populateCategoryFilter();
      this.renderBoard();
    } catch (error) {
      console.error('Failed to load tasks:', error);
      Toast.error('Error', 'Failed to load tasks');
    }
  },

  renderStats() {
    const c = this._counts;
    const total = (c.personal_todo || 0) + (c.peter_queue || 0) + (c.idea || 0) + (c.research || 0);
    const container = document.getElementById('tasks-stats');
    if (!container) return;

    container.innerHTML = `
      ${Components.statsCard({ icon: Icons.checkCircle, value: c.personal_todo || 0, label: 'Todos', variant: 'info' })}
      ${Components.statsCard({ icon: Icons.zap, value: c.peter_queue || 0, label: 'Peter Queue', variant: 'warning' })}
      ${Components.statsCard({ icon: Icons.star, value: c.idea || 0, label: 'Ideas', variant: 'success' })}
      ${Components.statsCard({ icon: Icons.search, value: c.research || 0, label: 'Research', variant: 'info' })}
    `;

    // Update tab counts
    for (const lt of this.LIST_TYPES) {
      const el = document.getElementById(`tab-count-${lt.key}`);
      if (el) el.textContent = c[lt.key] || '';
    }

    document.getElementById('tasks-subtitle').textContent = `${total} active tasks across all lists`;
  },

  populateCategoryFilter() {
    const sel = document.getElementById('kb-filter-category');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">All Categories</option>' +
      this._categories.map(c => `<option value="${c.slug}" ${c.slug === current ? 'selected' : ''}>${Utils.escapeHtml(c.name)}</option>`).join('');
  },

  _getFilteredTasks() {
    const search = (document.getElementById('kb-search')?.value || '').toLowerCase();
    const priority = document.getElementById('kb-filter-priority')?.value || '';
    const category = document.getElementById('kb-filter-category')?.value || '';
    return this._tasks.filter(task => {
      if (search && !task.title.toLowerCase().includes(search) && !(task.description || '').toLowerCase().includes(search)) return false;
      if (priority && task.priority !== priority) return false;
      if (category && !(task.categories || []).includes(category)) return false;
      return true;
    });
  },

  applyFilters() {
    this.renderBoard();
  },

  renderBoard() {
    const board = document.getElementById('kanban-board');
    if (!board) return;

    const columns = this.COLUMNS[this._activeList] || [];
    const filtered = this._getFilteredTasks();

    // Group tasks by status
    const byStatus = {};
    for (const task of filtered) {
      byStatus[task.status] = byStatus[task.status] || [];
      byStatus[task.status].push(task);
    }

    board.innerHTML = columns.map(status => {
      const col = this.COLUMN_CONFIG[status] || { label: status, color: '#6B7280', accent: '#E5E7EB' };
      const tasks = byStatus[status] || [];

      return `
        <div class="kb-column" data-status="${status}"
             ondragover="TasksView.onDragOver(event)"
             ondragenter="TasksView.onDragEnter(event)"
             ondragleave="TasksView.onDragLeave(event)"
             ondrop="TasksView.onDrop(event, '${status}')">
          <div class="kb-column-header" style="border-top: 3px solid ${col.color};">
            <span class="kb-column-title">${col.label}</span>
            <span class="kb-column-count">${tasks.length}</span>
          </div>
          <div class="kb-column-body">
            ${tasks.map(t => this._renderCard(t)).join('')}
          </div>
        </div>
      `;
    }).join('');
  },

  _renderCard(task) {
    const prio = this.PRIORITY_CONFIG[task.priority] || this.PRIORITY_CONFIG.medium;
    const isDone = task.status === 'done' || task.status === 'cancelled';

    const dueStr = task.due_date
      ? new Date(task.due_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      : '';
    const isOverdue = task.due_date && !isDone && new Date(task.due_date) < new Date();

    const catBadges = (task.categories || []).map(slug => {
      const cat = this._categories.find(c => c.slug === slug);
      if (!cat) return '';
      return `<span class="kb-cat-badge" style="background: ${cat.color}22; color: ${cat.color};">${Utils.escapeHtml(cat.name)}</span>`;
    }).join('');

    return `
      <div class="kb-card ${isDone ? 'kb-card-done' : ''}"
           draggable="true"
           data-task-id="${task.id}"
           ondragstart="TasksView.onDragStart(event, '${task.id}')"
           ondragend="TasksView.onDragEnd(event)"
           onclick="TasksView.showEditModal('${task.id}')">
        <div class="kb-card-title ${isDone ? 'kb-title-done' : ''}">${Utils.escapeHtml(task.title)}</div>
        ${task.description ? `<div class="kb-card-desc">${Utils.escapeHtml(task.description).substring(0, 80)}${task.description.length > 80 ? '...' : ''}</div>` : ''}
        <div class="kb-card-footer">
          <span class="kb-prio-dot" style="background: ${prio.color};" title="${prio.label}"></span>
          ${catBadges}
          ${dueStr ? `<span class="kb-due ${isOverdue ? 'kb-overdue' : ''}">${dueStr}</span>` : ''}
          ${task.created_by === 'peter' ? '<span class="kb-peter-badge" title="Created by Peter">P</span>' : ''}
        </div>
      </div>
    `;
  },

  // ---- Drag and Drop ----
  onDragStart(e, taskId) {
    this._dragTaskId = taskId;
    e.dataTransfer.effectAllowed = 'move';
    e.target.classList.add('kb-card-dragging');
  },

  onDragEnd(e) {
    this._dragTaskId = null;
    e.target.classList.remove('kb-card-dragging');
    document.querySelectorAll('.kb-column-over').forEach(el => el.classList.remove('kb-column-over'));
  },

  onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  },

  onDragEnter(e) {
    e.preventDefault();
    const col = e.target.closest('.kb-column');
    if (col) col.classList.add('kb-column-over');
  },

  onDragLeave(e) {
    const col = e.target.closest('.kb-column');
    if (col && !col.contains(e.relatedTarget)) col.classList.remove('kb-column-over');
  },

  async onDrop(e, newStatus) {
    e.preventDefault();
    const col = e.target.closest('.kb-column');
    if (col) col.classList.remove('kb-column-over');

    if (!this._dragTaskId) return;
    const task = this._tasks.find(t => t.id === this._dragTaskId);
    if (!task || task.status === newStatus) return;

    try {
      const resp = await fetch(`${this.HADLEY_API}/ptasks/${this._dragTaskId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus, actor: 'chris' })
      });
      if (!resp.ok) {
        const err = await resp.json();
        Toast.error('Invalid move', err.detail || 'Status transition not allowed');
        return;
      }
      await this.loadData();
    } catch (error) {
      Toast.error('Error', `Failed to move task: ${error.message}`);
    }
  },

  // ---- List switching ----
  async switchList(listType) {
    this._activeList = listType;
    document.querySelectorAll('#tasks-tab-bar button[data-list]').forEach(btn => {
      btn.classList.toggle('btn-primary', btn.dataset.list === listType);
      btn.classList.toggle('btn-secondary', btn.dataset.list !== listType);
    });
    document.getElementById('kanban-board').innerHTML = Components.skeleton('table', 5);
    await this.loadData();
  },

  // ---- Edit Modal (full editing with activity timeline) ----
  async showEditModal(taskId) {
    try {
      // Fetch task detail and history in parallel
      const [taskResp, histResp] = await Promise.all([
        fetch(`${this.HADLEY_API}/ptasks/${taskId}`),
        fetch(`${this.HADLEY_API}/ptasks/${taskId}/history`),
      ]);
      const task = await taskResp.json();
      const histData = await histResp.json();
      const history = histData.history || [];

      const prioOpts = Object.entries(this.PRIORITY_CONFIG).map(([k, v]) =>
        `<option value="${k}" ${task.priority === k ? 'selected' : ''}>${v.label}</option>`
      ).join('');

      const statusOpts = (this.COLUMNS[this._activeList] || []).map(s => {
        const sc = this.COLUMN_CONFIG[s] || { label: s };
        return `<option value="${s}" ${task.status === s ? 'selected' : ''}>${sc.label}</option>`;
      }).join('');

      const allCats = this._categories;
      const taskCatSlugs = task.categories || [];
      const catCheckboxes = allCats.map(cat => `
        <label class="kb-cat-check" style="--cat-color: ${cat.color};">
          <input type="checkbox" value="${cat.slug}" ${taskCatSlugs.includes(cat.slug) ? 'checked' : ''}>
          <span class="kb-cat-check-label" style="background: ${cat.color}22; color: ${cat.color}; border: 1px solid ${cat.color}40;">${Utils.escapeHtml(cat.name)}</span>
        </label>
      `).join('');

      const comments = (task.comments_list || []).map(c => `
        <div class="kb-comment">
          <div class="kb-comment-meta">
            <strong>${Utils.escapeHtml(c.author)}</strong> &middot; ${new Date(c.created_at).toLocaleString('en-GB')}
            ${c.is_system_message ? '<span style="color: #7C3AED; font-size: 10px;">(system)</span>' : ''}
          </div>
          <div class="kb-comment-text">${Utils.escapeHtml(c.content)}</div>
        </div>
      `).join('') || '<p class="text-muted" style="font-size: 12px;">No comments yet</p>';

      // Activity timeline from task_history
      const timeline = history.map(h => {
        const time = new Date(h.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
        let desc = h.action;
        if (h.action === 'status_changed') {
          const oldLabel = (this.COLUMN_CONFIG[h.old_value] || {}).label || h.old_value;
          const newLabel = (this.COLUMN_CONFIG[h.new_value] || {}).label || h.new_value;
          desc = `${oldLabel} &rarr; ${newLabel}`;
        } else if (h.action === 'created') {
          desc = 'Task created';
        }
        const actor = h.actor || '';
        const isPeter = actor === 'peter';
        return `<div class="kb-timeline-item">
          <div class="kb-timeline-dot" style="background: ${isPeter ? '#7C3AED' : '#2563EB'};"></div>
          <div class="kb-timeline-content">
            <span class="kb-timeline-desc">${desc}</span>
            <span class="kb-timeline-meta">${actor} &middot; ${time}</span>
          </div>
        </div>`;
      }).join('') || '<p class="text-muted" style="font-size: 12px;">No activity recorded</p>';

      const dueVal = task.due_date ? task.due_date.split('T')[0] : '';

      Modal.open({
        title: 'Edit Task',
        size: 'lg',
        content: `
          <div class="kb-edit-form">
            <div class="kb-edit-row">
              <label class="form-label">Title</label>
              <input type="text" id="edit-task-title" class="form-input" value="${Utils.escapeHtml(task.title)}">
            </div>
            <div class="kb-edit-row">
              <label class="form-label">Description</label>
              <textarea id="edit-task-desc" class="form-input" rows="3">${Utils.escapeHtml(task.description || '')}</textarea>
            </div>
            <div class="kb-edit-row-grid">
              <div>
                <label class="form-label">Status</label>
                <select id="edit-task-status" class="form-input">${statusOpts}</select>
              </div>
              <div>
                <label class="form-label">Priority</label>
                <select id="edit-task-priority" class="form-input">${prioOpts}</select>
              </div>
              <div>
                <label class="form-label">Due Date</label>
                <input type="date" id="edit-task-due" class="form-input" value="${dueVal}">
              </div>
              <div>
                <label class="form-label">Effort</label>
                <input type="text" id="edit-task-effort" class="form-input" value="${Utils.escapeHtml(task.estimated_effort || '')}" placeholder="e.g. 2h, half_day">
              </div>
            </div>
            <div class="kb-edit-row">
              <label class="form-label">Categories</label>
              <div class="kb-cat-list">${catCheckboxes || '<span class="text-muted" style="font-size: 12px;">No categories defined</span>'}</div>
            </div>
            <div class="kb-edit-row" style="margin-top: 8px;">
              <label class="form-label">Comments</label>
              <div class="kb-comments-box">${comments}</div>
              <div class="kb-comment-add">
                <input type="text" id="edit-task-comment" class="form-input" placeholder="Add a comment...">
                <button class="btn btn-secondary btn-sm" onclick="TasksView.addComment('${task.id}')">Send</button>
              </div>
            </div>
            <div class="kb-edit-row" style="margin-top: 8px;">
              <label class="form-label">Activity</label>
              <div class="kb-timeline">${timeline}</div>
            </div>
            <div class="kb-edit-meta">
              Created by <strong>${task.created_by || 'unknown'}</strong>
              &middot; ${new Date(task.created_at).toLocaleString('en-GB')}
            </div>
          </div>
        `,
        footer: `
          <button class="btn btn-ghost" style="color: #DC2626; margin-right: auto;" onclick="TasksView.deleteTask('${task.id}')">Delete</button>
          <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
          <button class="btn btn-primary" onclick="TasksView.saveTask('${task.id}')">Save</button>
        `
      });
    } catch (error) {
      Toast.error('Error', `Failed to load task: ${error.message}`);
    }
  },

  async saveTask(taskId) {
    const title = document.getElementById('edit-task-title')?.value?.trim();
    const description = document.getElementById('edit-task-desc')?.value?.trim();
    const status = document.getElementById('edit-task-status')?.value;
    const priority = document.getElementById('edit-task-priority')?.value;
    const dueDate = document.getElementById('edit-task-due')?.value;
    const effort = document.getElementById('edit-task-effort')?.value?.trim();

    if (!title) { Toast.error('Error', 'Title is required'); return; }

    // Collect selected categories
    const catChecks = document.querySelectorAll('.kb-cat-check input[type="checkbox"]');
    const selectedCats = Array.from(catChecks).filter(cb => cb.checked).map(cb => cb.value);

    try {
      // Update task fields
      const updateBody = { title, description: description || null, priority };
      if (dueDate) updateBody.due_date = new Date(dueDate).toISOString();
      if (effort) updateBody.estimated_effort = effort;

      const oldTask = this._tasks.find(t => t.id === taskId);

      await fetch(`${this.HADLEY_API}/ptasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateBody)
      });

      // Update status if changed
      if (oldTask && oldTask.status !== status) {
        const statusResp = await fetch(`${this.HADLEY_API}/ptasks/${taskId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status, actor: 'chris' })
        });
        if (!statusResp.ok) {
          const err = await statusResp.json();
          Toast.error('Status change failed', err.detail || 'Invalid transition');
        }
      }

      // Update categories
      await fetch(`${this.HADLEY_API}/ptasks/${taskId}/categories`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(selectedCats)
      });

      Modal.close();
      Toast.success('Saved', 'Task updated');
      await this.loadData();
    } catch (error) {
      Toast.error('Error', `Failed to save: ${error.message}`);
    }
  },

  async addComment(taskId) {
    const input = document.getElementById('edit-task-comment');
    if (!input || !input.value.trim()) return;

    try {
      await fetch(`${this.HADLEY_API}/ptasks/${taskId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: input.value.trim(), author: 'chris' })
      });
      input.value = '';
      Toast.success('Comment added', '');
      // Refresh the comment list in-place
      this.showEditModal(taskId);
    } catch (error) {
      Toast.error('Error', `Failed to add comment: ${error.message}`);
    }
  },

  // ---- Create Modal ----
  showCreateModal() {
    const listOpts = this.LIST_TYPES.map(lt =>
      `<option value="${lt.key}" ${lt.key === this._activeList ? 'selected' : ''}>${lt.label}</option>`
    ).join('');

    const prioOpts = Object.entries(this.PRIORITY_CONFIG).map(([k, v]) =>
      `<option value="${k}" ${k === 'medium' ? 'selected' : ''}>${v.label}</option>`
    ).join('');

    const catCheckboxes = this._categories.map(cat => `
      <label class="kb-cat-check" style="--cat-color: ${cat.color};">
        <input type="checkbox" value="${cat.slug}">
        <span class="kb-cat-check-label" style="background: ${cat.color}22; color: ${cat.color}; border: 1px solid ${cat.color}40;">${Utils.escapeHtml(cat.name)}</span>
      </label>
    `).join('');

    Modal.open({
      title: 'New Task',
      content: `
        <div class="kb-edit-form">
          <div class="kb-edit-row">
            <label class="form-label">Title</label>
            <input type="text" id="new-task-title" class="form-input" placeholder="What needs doing?">
          </div>
          <div class="kb-edit-row">
            <label class="form-label">Description</label>
            <textarea id="new-task-desc" class="form-input" rows="2" placeholder="Optional details..."></textarea>
          </div>
          <div class="kb-edit-row-grid">
            <div>
              <label class="form-label">List</label>
              <select id="new-task-list" class="form-input">${listOpts}</select>
            </div>
            <div>
              <label class="form-label">Priority</label>
              <select id="new-task-priority" class="form-input">${prioOpts}</select>
            </div>
          </div>
          ${catCheckboxes ? `
            <div class="kb-edit-row">
              <label class="form-label">Categories</label>
              <div class="kb-cat-list">${catCheckboxes}</div>
            </div>
          ` : ''}
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
        <button class="btn btn-primary" onclick="TasksView.createTask()">Create</button>
      `
    });
  },

  async createTask() {
    const title = document.getElementById('new-task-title')?.value?.trim();
    const desc = document.getElementById('new-task-desc')?.value?.trim();
    const listType = document.getElementById('new-task-list')?.value;
    const priority = document.getElementById('new-task-priority')?.value;

    if (!title) { Toast.error('Error', 'Title is required'); return; }

    const catChecks = document.querySelectorAll('.kb-cat-check input[type="checkbox"]');
    const selectedCats = Array.from(catChecks).filter(cb => cb.checked).map(cb => cb.value);

    Modal.close();

    try {
      await fetch(`${this.HADLEY_API}/ptasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          list_type: listType,
          title,
          description: desc || null,
          priority,
          created_by: 'chris',
          category_slugs: selectedCats.length > 0 ? selectedCats : null,
        })
      });
      Toast.success('Created', `Task "${title}" created`);
      if (listType !== this._activeList) {
        this._activeList = listType;
        document.querySelectorAll('#tasks-tab-bar button[data-list]').forEach(btn => {
          btn.classList.toggle('btn-primary', btn.dataset.list === listType);
          btn.classList.toggle('btn-secondary', btn.dataset.list !== listType);
        });
      }
      await this.loadData();
    } catch (error) {
      Toast.error('Error', `Failed to create task: ${error.message}`);
    }
  },

  async deleteTask(taskId) {
    if (!confirm('Delete this task? This cannot be undone.')) return;
    Modal.close();

    try {
      await fetch(`${this.HADLEY_API}/ptasks/${taskId}`, { method: 'DELETE' });
      Toast.success('Deleted', 'Task deleted');
      await this.loadData();
    } catch (error) {
      Toast.error('Error', `Failed to delete task: ${error.message}`);
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Tasks updated');
  },
};


// =============================================================================
// MEAL PLAN VIEW
// =============================================================================

const MealPlanView = {
  title: 'Meal Plan',
  _plan: null,
  _shoppingList: null,
  HADLEY_API: '/api/hadley/proxy',
  DAY_NAMES: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
  DAY_SHORT: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Meal Plan</h2>
            <p class="text-secondary" id="meal-plan-subtitle">Weekly meal planner</p>
          </div>
          <div class="flex gap-sm">
            <button class="btn btn-secondary" onclick="MealPlanView.importFromSheets()">
              ${Icons.refreshCw} Import from Sheets
            </button>
            <button class="btn btn-secondary" onclick="MealPlanView.exportMealPlanPDF()">
              ${Icons.file} Export PDF
            </button>
            <button class="btn btn-ghost" onclick="MealPlanView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-md mb-lg" id="meal-plan-stats">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        ${Components.tabs({
          id: 'meal-plan-tabs',
          tabs: [
            { label: 'Week View', badge: '' },
            { label: 'Shopping List', badge: '' },
            { label: 'Import', badge: '' }
          ],
          activeTab: 0
        })}
      </div>
    `;

    // Override tab panel content
    document.getElementById('meal-plan-tabs-panel-0').innerHTML = `<div id="meal-week-view">${Components.skeleton('table', 7)}</div>`;
    document.getElementById('meal-plan-tabs-panel-1').innerHTML = `<div id="meal-shopping-list">${Components.skeleton('table', 5)}</div>`;
    document.getElementById('meal-plan-tabs-panel-2').innerHTML = `<div id="meal-import-panel">${this._renderImportPanel()}</div>`;

    await this.loadData();
  },

  async loadData() {
    try {
      const resp = await fetch(`${this.HADLEY_API}/meal-plan/current`);
      const data = await resp.json();
      this._plan = data.plan;
      this.renderStats();
      this.renderWeekView();
      this.renderShoppingList();
    } catch (error) {
      console.error('Failed to load meal plan:', error);
      Toast.error('Error', 'Failed to load meal plan');
      this.renderEmpty();
    }
  },

  renderStats() {
    const plan = this._plan;
    const container = document.getElementById('meal-plan-stats');
    if (!container) return;

    if (!plan) {
      container.innerHTML = `
        ${Components.statsCard({ icon: Icons.alertCircle, value: 'None', label: 'Current Plan', variant: 'warning' })}
        ${Components.statsCard({ icon: Icons.clock, value: '-', label: 'Week Starting', variant: 'info' })}
        ${Components.statsCard({ icon: Icons.list, value: '0', label: 'Meals Planned', variant: 'info' })}
        ${Components.statsCard({ icon: Icons.box, value: '0', label: 'Ingredients', variant: 'info' })}
      `;
      document.getElementById('meal-plan-subtitle').textContent = 'No plan imported yet — import from Google Sheets to get started';
      return;
    }

    const items = plan.items || [];
    const ingredients = plan.ingredients || [];
    const days = new Set(items.map(i => i.date)).size;
    const goustoCount = items.filter(i => i.source_tag === 'gousto').length;
    const weekDate = new Date(plan.week_start + 'T00:00:00');
    const weekStr = weekDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

    container.innerHTML = `
      ${Components.statsCard({ icon: Icons.checkCircle, value: `w/c ${weekStr}`, label: 'Current Week', variant: 'success' })}
      ${Components.statsCard({ icon: Icons.list, value: items.length, label: `Meals (${days} days)`, variant: 'info' })}
      ${Components.statsCard({ icon: Icons.box, value: ingredients.length, label: 'Ingredients', variant: 'info' })}
      ${Components.statsCard({ icon: Icons.zap, value: goustoCount, label: 'Gousto Meals', variant: 'info' })}
    `;

    document.getElementById('meal-plan-subtitle').textContent = `Week commencing ${weekDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })} — source: ${plan.source || 'manual'}`;
  },

  renderWeekView() {
    const container = document.getElementById('meal-week-view');
    if (!container) return;

    if (!this._plan || !this._plan.items || this._plan.items.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding: 48px 0;">
          <div class="empty-state-icon">${Icons.inbox}</div>
          <div class="empty-state-title">No Meal Plan</div>
          <div class="empty-state-description">Import your meal plan from Google Sheets to see it here.</div>
          <button class="btn btn-primary" style="margin-top: 16px;" onclick="MealPlanView.importFromSheets()">
            ${Icons.refreshCw} Import from Sheets
          </button>
        </div>
      `;
      return;
    }

    // Group items by date
    const byDate = {};
    for (const item of this._plan.items) {
      if (!byDate[item.date]) byDate[item.date] = [];
      byDate[item.date].push(item);
    }

    // Sort dates
    const dates = Object.keys(byDate).sort();
    const today = new Date().toISOString().split('T')[0];

    let html = '<div class="meal-week-grid">';
    for (const date of dates) {
      const d = new Date(date + 'T00:00:00');
      const dayName = d.toLocaleDateString('en-GB', { weekday: 'long' });
      const dateStr = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
      const isToday = date === today;
      const meals = byDate[date].sort((a, b) => a.meal_slot - b.meal_slot);

      html += `
        <div class="meal-day-card ${isToday ? 'meal-day-today' : ''}">
          <div class="meal-day-header">
            <span class="meal-day-name">${dayName}</span>
            <span class="meal-day-date">${dateStr}</span>
            ${isToday ? '<span class="status-badge running" style="font-size: 10px; padding: 2px 6px;">Today</span>' : ''}
          </div>
          <div class="meal-day-body">
            ${meals.map(m => this._renderMealSlot(m)).join('')}
          </div>
        </div>
      `;
    }
    html += '</div>';

    container.innerHTML = html;
  },

  _renderMealSlot(meal) {
    const sourceTag = meal.source_tag;
    let tagBadge = '';
    if (sourceTag === 'gousto') {
      tagBadge = '<span class="meal-tag meal-tag-gousto">Gousto</span>';
    } else if (sourceTag === 'chris_out') {
      tagBadge = '<span class="meal-tag meal-tag-out">Out</span>';
    }

    const adults = meal.adults_meal || '';
    const kids = meal.kids_meal || '';
    const sameAsBoth = adults && kids && adults.toLowerCase() === kids.toLowerCase();

    let content;
    if (sameAsBoth) {
      content = `<div class="meal-slot-item"><span class="meal-slot-who">Everyone</span> ${Utils.escapeHtml(adults)}</div>`;
    } else {
      content = '';
      if (adults) {
        content += `<div class="meal-slot-item"><span class="meal-slot-who">Adults</span> ${Utils.escapeHtml(adults)}</div>`;
      }
      if (kids) {
        content += `<div class="meal-slot-item"><span class="meal-slot-who">Kids</span> ${Utils.escapeHtml(kids)}</div>`;
      }
    }

    return `
      <div class="meal-slot">
        <div class="meal-slot-header">
          <span class="meal-slot-label">Meal ${meal.meal_slot}</span>
          ${tagBadge}
        </div>
        ${content}
        ${meal.recipe_url ? `<a href="${meal.recipe_url}" target="_blank" class="meal-recipe-link">${Icons.file} Recipe</a>` : ''}
      </div>
    `;
  },

  renderShoppingList() {
    const container = document.getElementById('meal-shopping-list');
    if (!container) return;

    if (!this._plan) {
      container.innerHTML = `
        <div class="empty-state" style="padding: 48px 0;">
          <div class="empty-state-icon">${Icons.inbox}</div>
          <div class="empty-state-title">No Shopping List</div>
          <div class="empty-state-description">Import a meal plan first, then shopping list ingredients will appear here.</div>
        </div>
      `;
      return;
    }

    const ingredients = this._plan.ingredients || [];
    if (ingredients.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="padding: 48px 0;">
          <div class="empty-state-icon">${Icons.inbox}</div>
          <div class="empty-state-title">No Ingredients</div>
          <div class="empty-state-description">No ingredients found in this plan. Make sure the Google Sheet has an ingredients tab.</div>
        </div>
      `;
      return;
    }

    // Group by category
    const byCategory = {};
    for (const ing of ingredients) {
      const cat = ing.category || 'Other';
      if (!byCategory[cat]) byCategory[cat] = [];
      byCategory[cat].push(ing);
    }

    const categories = Object.keys(byCategory).sort();
    let html = `
      <div class="flex justify-between items-center" style="margin-bottom: 16px;">
        <div>
          <strong>${ingredients.length}</strong> items across <strong>${categories.length}</strong> categories
        </div>
        <button class="btn btn-primary" onclick="MealPlanView.generateShoppingPDF()">
          ${Icons.file} Generate PDF
        </button>
      </div>
      <div class="meal-ingredients-grid">
    `;

    for (const cat of categories) {
      const items = byCategory[cat];
      html += `
        <div class="meal-ingredient-category">
          <div class="meal-ingredient-cat-header">${Utils.escapeHtml(cat)} <span class="text-muted">(${items.length})</span></div>
          <ul class="meal-ingredient-list">
            ${items.map(item => {
              const qty = item.quantity ? ` <span class="text-muted">(${Utils.escapeHtml(item.quantity)})</span>` : '';
              const recipe = item.for_recipe ? ` <span class="meal-ingredient-recipe">${Utils.escapeHtml(item.for_recipe)}</span>` : '';
              return `<li class="meal-ingredient-item">${Utils.escapeHtml(item.item)}${qty}${recipe}</li>`;
            }).join('')}
          </ul>
        </div>
      `;
    }

    html += '</div>';
    container.innerHTML = html;
  },

  _renderImportPanel() {
    return `
      <div class="grid grid-cols-3 gap-md" style="padding: 8px 0;">
        <div class="card">
          <div class="card-body" style="text-align: center; padding: 24px;">
            <div style="font-size: 32px; margin-bottom: 12px;">${Icons.box}</div>
            <h4 style="margin-bottom: 8px;">Google Sheets</h4>
            <p class="text-secondary text-sm" style="margin-bottom: 16px;">Import meal plan and ingredients from Chris's Google Sheet.</p>
            <button class="btn btn-primary" onclick="MealPlanView.importFromSheets()">
              ${Icons.refreshCw} Import
            </button>
          </div>
        </div>
        <div class="card">
          <div class="card-body" style="text-align: center; padding: 24px;">
            <div style="font-size: 32px; margin-bottom: 12px;">${Icons.zap}</div>
            <h4 style="margin-bottom: 8px;">Gousto Emails</h4>
            <p class="text-secondary text-sm" style="margin-bottom: 16px;">Search Gmail for Gousto recipe box confirmations.</p>
            <button class="btn btn-secondary" onclick="MealPlanView.importGousto()">
              ${Icons.search} Search Emails
            </button>
          </div>
        </div>
        <div class="card">
          <div class="card-body" style="text-align: center; padding: 24px;">
            <div style="font-size: 32px; margin-bottom: 12px;">${Icons.file}</div>
            <h4 style="margin-bottom: 8px;">CSV Import</h4>
            <p class="text-secondary text-sm" style="margin-bottom: 16px;">Paste CSV data to import meals and ingredients.</p>
            <button class="btn btn-secondary" onclick="MealPlanView.showCSVModal()">
              ${Icons.file} Paste CSV
            </button>
          </div>
        </div>
      </div>
      <div id="import-results" style="margin-top: 16px;"></div>
    `;
  },

  renderEmpty() {
    const statsEl = document.getElementById('meal-plan-stats');
    if (statsEl) {
      statsEl.innerHTML = `
        ${Components.statsCard({ icon: Icons.alertCircle, value: 'Error', label: 'Failed to load', variant: 'warning' })}
        ${Components.statsCard({ icon: Icons.clock, value: '-', label: 'Week Starting', variant: 'info' })}
        ${Components.statsCard({ icon: Icons.list, value: '-', label: 'Meals', variant: 'info' })}
        ${Components.statsCard({ icon: Icons.box, value: '-', label: 'Ingredients', variant: 'info' })}
      `;
    }
  },

  async importFromSheets() {
    Toast.info('Importing', 'Importing meal plan from Google Sheets...');
    try {
      const resp = await fetch(`${this.HADLEY_API}/meal-plan/import/sheets`, { method: 'POST' });
      const data = await resp.json();

      if (data.status === 'imported') {
        Toast.success('Imported', `${data.items_count} meals, ${data.ingredients_count} ingredients imported`);
        await this.loadData();

        const resultsEl = document.getElementById('import-results');
        if (resultsEl) {
          resultsEl.innerHTML = `
            <div class="card" style="border-left: 3px solid var(--status-running);">
              <div class="card-body">
                <strong>Import Successful</strong>
                <p class="text-secondary text-sm" style="margin-top: 4px;">
                  Week: ${data.week_start} | ${data.items_count} meals | ${data.ingredients_count} ingredients<br>
                  Tabs found: ${data.tabs_found.meal_plan || 'none'} (meals), ${data.tabs_found.ingredients || 'none'} (ingredients)
                </p>
              </div>
            </div>
          `;
        }
      } else {
        Toast.error('Import Failed', data.detail || 'Unknown error');
      }
    } catch (error) {
      Toast.error('Error', `Import failed: ${error.message}`);
    }
  },

  async importGousto() {
    Toast.info('Searching', 'Searching Gmail for Gousto emails...');
    try {
      const resp = await fetch(`${this.HADLEY_API}/meal-plan/import/gousto`, { method: 'POST' });
      const data = await resp.json();

      const resultsEl = document.getElementById('import-results');
      if (!resultsEl) return;

      if (data.status === 'no_emails') {
        Toast.info('No Emails', 'No recent Gousto emails found');
        resultsEl.innerHTML = `
          <div class="card" style="border-left: 3px solid var(--status-paused);">
            <div class="card-body">
              <strong>No Gousto Emails Found</strong>
              <p class="text-secondary text-sm" style="margin-top: 4px;">No Gousto emails found in the last 14 days.</p>
            </div>
          </div>
        `;
      } else {
        Toast.success('Found', `${data.recipes_found.length} recipes found in ${data.emails_checked} emails`);
        resultsEl.innerHTML = `
          <div class="card" style="border-left: 3px solid var(--status-running);">
            <div class="card-body">
              <strong>Gousto Recipes Found</strong>
              <p class="text-secondary text-sm" style="margin-top: 8px;">
                ${data.recipes_found.map(r => `<span class="meal-tag meal-tag-gousto" style="margin: 2px;">${Utils.escapeHtml(r)}</span>`).join('')}
              </p>
              ${data.matched.length > 0 ? `
                <p class="text-sm" style="margin-top: 8px; color: var(--status-running);">
                  Matched ${data.matched.length} to current plan
                </p>
              ` : ''}
              ${data.unmatched.length > 0 ? `
                <p class="text-sm" style="margin-top: 4px; color: var(--status-paused);">
                  ${data.unmatched.length} unmatched recipes
                </p>
              ` : ''}
            </div>
          </div>
        `;
      }
    } catch (error) {
      Toast.error('Error', `Gousto search failed: ${error.message}`);
    }
  },

  showCSVModal() {
    Modal.open({
      title: 'Import from CSV',
      content: `
        <div style="margin-bottom: 12px;">
          <label class="form-label">Meal Plan CSV</label>
          <textarea id="csv-meals-input" class="form-input" rows="8"
            placeholder="Date,Day,Adults,Kids&#10;07/02,Sat,Chicken stir-fry,Fish fingers&#10;08/02,Sun,Roast dinner,Roast dinner"
            style="font-family: var(--font-mono); font-size: 12px;"></textarea>
        </div>
        <div>
          <label class="form-label">Ingredients CSV (optional)</label>
          <textarea id="csv-ingredients-input" class="form-input" rows="5"
            placeholder="Category,Item,Quantity,Recipe&#10;Meat & Fish,Chicken breast,500g,Chicken stir-fry"
            style="font-family: var(--font-mono); font-size: 12px;"></textarea>
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
        <button class="btn btn-primary" onclick="MealPlanView.importCSV()">Import</button>
      `
    });
  },

  async importCSV() {
    const csvData = document.getElementById('csv-meals-input')?.value;
    const ingredientsCsv = document.getElementById('csv-ingredients-input')?.value;

    if (!csvData || !csvData.trim()) {
      Toast.error('Error', 'Please enter meal plan CSV data');
      return;
    }

    Modal.close();
    Toast.info('Importing', 'Processing CSV data...');

    try {
      const body = { csv_data: csvData };
      if (ingredientsCsv && ingredientsCsv.trim()) {
        body.ingredients_csv = ingredientsCsv;
      }

      const resp = await fetch(`${this.HADLEY_API}/meal-plan/import/csv`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await resp.json();

      if (data.status === 'imported') {
        Toast.success('Imported', `${data.items_count} meals imported from CSV`);
        await this.loadData();
      } else {
        Toast.error('Import Failed', data.detail || 'CSV parsing error');
      }
    } catch (error) {
      Toast.error('Error', `CSV import failed: ${error.message}`);
    }
  },

  async generateShoppingPDF() {
    if (!this._plan) {
      Toast.error('Error', 'No meal plan loaded');
      return;
    }

    Toast.info('Generating', 'Creating shopping list PDF...');

    try {
      const resp = await fetch(`${this.HADLEY_API}/meal-plan/shopping-list/generate?plan_id=${this._plan.id}`, {
        method: 'POST'
      });
      const data = await resp.json();

      if (data.status === 'created') {
        Toast.success('PDF Created', `${data.filename} saved to Google Drive`);
      } else {
        Toast.error('Error', data.detail || 'PDF generation failed');
      }
    } catch (error) {
      Toast.error('Error', `PDF generation failed: ${error.message}`);
    }
  },

  async exportMealPlanPDF() {
    if (!this._plan) {
      Toast.error('Error', 'No meal plan loaded');
      return;
    }

    Toast.info('Generating', 'Creating meal plan PDF...');

    try {
      const resp = await fetch(`${this.HADLEY_API}/meal-plan/export-pdf?plan_id=${this._plan.id}`, {
        method: 'POST'
      });
      const data = await resp.json();

      if (data.status === 'created') {
        Toast.success('PDF Created', `${data.filename} saved to Google Drive`);
      } else {
        Toast.error('Error', data.detail || 'PDF generation failed');
      }
    } catch (error) {
      Toast.error('Error', `PDF generation failed: ${error.message}`);
    }
  },

  async deletePlan() {
    if (!this._plan) return;

    if (!confirm('Delete this meal plan? This cannot be undone.')) return;

    try {
      await fetch(`${this.HADLEY_API}/meal-plan/${this._plan.id}`, { method: 'DELETE' });
      Toast.success('Deleted', 'Meal plan deleted');
      this._plan = null;
      this.renderStats();
      this.renderWeekView();
      this.renderShoppingList();
    } catch (error) {
      Toast.error('Error', `Delete failed: ${error.message}`);
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Meal plan data updated');
  }
};


// =============================================================================
// 8. INITIALIZATION
// =============================================================================

/**
 * Main Application Controller
 */
const App = {
  init() {
    // Initialize components
    Toast.init();
    Modal.init();

    // Register routes
    Router.register('/', DashboardView);
    Router.register('/jobs', JobsView);
    Router.register('/services', ServicesView);
    Router.register('/skills', SkillsView);
    Router.register('/parser', ParserView);
    Router.register('/logs', LogsView);
    Router.register('/files', FilesView);
    Router.register('/memory', MemoryView);
    // ApiExplorerView is defined in api-explorer.js which may load after this
    if (typeof ApiExplorerView !== 'undefined') {
      Router.register('/api-explorer', ApiExplorerView);
    }
    // MindMapView is defined in mind-map.js which may load after this
    if (typeof MindMapView !== 'undefined') {
      Router.register('/mind-map', MindMapView);
    }
    Router.register('/costs', CostsView);
    Router.register('/tasks', TasksView);
    Router.register('/meal-plan', MealPlanView);
    Router.register('/settings', SettingsView);

    // Initialize router
    Router.init();

    // Connect WebSocket
    WebSocketManager.connect();

    // Setup sidebar toggle
    this.setupSidebar();

    // Setup keyboard shortcuts
    this.setupKeyboardShortcuts();

    // Load saved preferences
    this.loadPreferences();

    console.log('Peter Dashboard initialized');
  },

  setupSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');

    if (toggleBtn) {
      toggleBtn.onclick = () => {
        const collapsed = sidebar.classList.toggle('collapsed');
        State.set({ sidebarCollapsed: collapsed });
        localStorage.setItem('sidebarCollapsed', collapsed);
      };
    }

    // Mobile menu toggle
    const mobileToggle = document.getElementById('mobile-menu-toggle');
    if (mobileToggle) {
      mobileToggle.onclick = () => {
        sidebar.classList.toggle('open');
      };
    }

    // Restore collapsed state
    if (State.get('sidebarCollapsed')) {
      sidebar.classList.add('collapsed');
    }
  },

  setupKeyboardShortcuts() {
    let shortcutBuffer = '';
    let shortcutTimeout;

    document.addEventListener('keydown', (e) => {
      // Ignore if typing in input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
      }

      // Single key shortcuts
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        const searchInput = document.querySelector('.data-table-search input');
        if (searchInput) searchInput.focus();
        return;
      }

      if (e.key === 'Escape') {
        DetailPanel.close();
        Modal.close();
        return;
      }

      if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
        if (Router.currentView && Router.currentView.refresh) {
          Router.currentView.refresh();
        }
        return;
      }

      // Two-key shortcuts (g + key)
      clearTimeout(shortcutTimeout);
      shortcutBuffer += e.key;

      if (shortcutBuffer === 'gd') {
        Router.navigate('/');
      } else if (shortcutBuffer === 'gj') {
        Router.navigate('/jobs');
      } else if (shortcutBuffer === 'gs') {
        Router.navigate('/services');
      } else if (shortcutBuffer === 'gl') {
        Router.navigate('/logs');
      } else if (shortcutBuffer === 'gk') {
        Router.navigate('/skills');
      } else if (shortcutBuffer === 'gf') {
        Router.navigate('/files');
      } else if (shortcutBuffer === 'gm') {
        Router.navigate('/memory');
      } else if (shortcutBuffer === 'gc') {
        Router.navigate('/costs');
      }

      shortcutTimeout = setTimeout(() => {
        shortcutBuffer = '';
      }, 500);
    });
  },

  loadPreferences() {
    // Load theme preference
    const theme = localStorage.getItem('theme');
    if (theme) {
      document.documentElement.setAttribute('data-theme', theme);
    }
  },

  async restartService(service) {
    try {
      await API.post(`/api/restart/${service}`);
      Toast.success('Restarting', `${Format.serviceName(service)} is restarting`);
    } catch (error) {
      Toast.error('Error', `Failed to restart: ${error.message}`);
    }
  },
};


// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

// Make globals available for onclick handlers
window.App = App;
window.Router = Router;
window.State = State;
window.Components = Components;
window.Toast = Toast;
window.Modal = Modal;
window.DetailPanel = DetailPanel;
window.DataTable = DataTable;
window.Tabs = Tabs;
window.Format = Format;
window.Utils = Utils;
window.Icons = Icons;

// View globals
window.DashboardView = DashboardView;
window.JobsView = JobsView;
window.ServicesView = ServicesView;
window.SkillsView = SkillsView;
window.LogsView = LogsView;
window.FilesView = FilesView;
window.MemoryView = MemoryView;
window.CostsView = CostsView;
window.MealPlanView = MealPlanView;
// ApiExplorerView is defined in api-explorer.js
window.SettingsView = SettingsView;
