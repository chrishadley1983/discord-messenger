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
  _authKey: document.querySelector('meta[name="api-key"]')?.content || '',

  async request(path, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const headers = { 'Content-Type': 'application/json', ...options.headers };
      if (this._authKey) headers['x-api-key'] = this._authKey;

      const response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
        headers,
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

      // Cleanup previous view (e.g. stop live tail timers)
      if (this.currentView && typeof this.currentView.destroy === 'function') {
        this.currentView.destroy();
      }

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
      success: 'running',
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
  _backdropHandler: null,

  open(content) {
    const panel = document.getElementById('detail-panel');
    const panelContent = document.getElementById('detail-panel-content');

    if (panel && panelContent) {
      panelContent.innerHTML = content;
      panel.classList.add('open');
      State.set({ detailPanelOpen: true });

      // Click outside to close (delayed to avoid immediate trigger)
      if (this._backdropHandler) document.removeEventListener('mousedown', this._backdropHandler);
      setTimeout(() => {
        this._backdropHandler = (e) => {
          if (!panel.contains(e.target)) {
            this.close();
          }
        };
        document.addEventListener('mousedown', this._backdropHandler);
      }, 100);
    }
  },

  close() {
    const panel = document.getElementById('detail-panel');
    if (panel) {
      panel.classList.remove('open');
      State.set({ detailPanelOpen: false, selectedItem: null });
    }
    if (this._backdropHandler) {
      document.removeEventListener('mousedown', this._backdropHandler);
      this._backdropHandler = null;
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
 * Dashboard View - Dense overview with live data
 */
const DashboardView = {
  title: 'Dashboard',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="dash-services" id="dash-services">
          <div class="dash-svc-pill skeleton" style="width:120px;height:28px"></div>
          <div class="dash-svc-pill skeleton" style="width:120px;height:28px"></div>
          <div class="dash-svc-pill skeleton" style="width:120px;height:28px"></div>
        </div>

        <div class="dash-stats" id="dash-stats">
          <div class="dash-stat skeleton" style="height:48px"></div>
          <div class="dash-stat skeleton" style="height:48px"></div>
          <div class="dash-stat skeleton" style="height:48px"></div>
          <div class="dash-stat skeleton" style="height:48px"></div>
        </div>

        <div class="dash-activity" id="dash-activity">
          <div class="dash-activity-header">
            <span class="dash-activity-title">Recent Activity</span>
            <button class="btn btn-sm btn-ghost" onclick="DashboardView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
          <div id="dash-activity-body">
            ${Components.skeleton('table', 5)}
          </div>
        </div>

        <div class="dash-bottom" id="dash-bottom">
          <div class="dash-panel">
            <div class="dash-panel-header">Upcoming Jobs</div>
            <div class="dash-panel-body" id="dash-upcoming">
              ${Components.skeleton('text', 4)}
            </div>
          </div>
          <div class="dash-panel" id="dash-errors-panel">
            <div class="dash-panel-header">Recent Errors</div>
            <div class="dash-panel-body" id="dash-errors">
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
      // Fire all API calls in parallel
      const [status, jobsData, statsData, execData] = await Promise.all([
        API.get('/api/status').catch(() => null),
        API.get('/api/jobs').catch(() => null),
        API.get('/api/job-stats').catch(() => null),
        API.get('/api/jobs/executions?limit=15').catch(() => null),
      ]);

      if (status) {
        this.renderServices(status.services || {});
      }

      this.renderStats(status, statsData);

      if (jobsData && jobsData.jobs) {
        State.set({ jobs: jobsData.jobs });
        this.renderUpcoming(jobsData.jobs);
      }

      if (execData && execData.executions) {
        this.renderActivity(execData.executions);
      } else if (jobsData && jobsData.jobs) {
        this.renderActivityFromJobs(jobsData.jobs);
      }

      this.renderErrors(statsData);

    } catch (error) {
      console.error('Failed to load dashboard data:', error);
      Toast.error('Error', 'Failed to load dashboard data');
    }
  },

  renderServices(services) {
    const html = Object.entries(services).map(([key, svc]) => {
      const latency = svc.latency_ms ? `<span class="dash-svc-latency">${Math.round(svc.latency_ms)}ms</span>` : '';
      const port = svc.port ? `<span class="dash-svc-port">:${svc.port}</span>` : '';
      return `
        <div class="dash-svc-pill" title="${Format.serviceName(key)}${svc.last_restart ? ' — restarted ' + Utils.formatRelativeTime(svc.last_restart) : ''}">
          <span class="dash-svc-dot ${svc.status}"></span>
          <span>${Format.serviceName(key)}</span>${port} ${latency}
        </div>
      `;
    }).join('');

    document.getElementById('dash-services').innerHTML = html;
  },

  renderStats(status, statsData) {
    const services = status ? status.services || {} : {};
    const running = Object.values(services).filter(s => s.status === 'up').length;
    const total = Object.keys(services).length;

    const successRate = statsData ? statsData.success_rate_24h : '-';
    const errors = statsData ? statsData.errors_24h : '-';
    const avgDuration = statsData && statsData.avg_duration_ms
      ? (statsData.avg_duration_ms / 1000).toFixed(1) + 's'
      : '-';

    const svcVariant = running === total ? 'success' : 'warning';
    const errVariant = (errors === 0 || errors === '-') ? 'info' : 'error';
    const rateVariant = (successRate >= 95) ? 'success' : (successRate >= 80) ? 'warning' : 'error';

    const html = `
      <div class="dash-stat">
        <div class="dash-stat-icon ${svcVariant}">${Icons.activity}</div>
        <div>
          <div class="dash-stat-value">${running}/${total}</div>
          <div class="dash-stat-label">Services</div>
        </div>
      </div>
      <div class="dash-stat">
        <div class="dash-stat-icon ${rateVariant}">${Icons.checkCircle}</div>
        <div>
          <div class="dash-stat-value">${successRate}%</div>
          <div class="dash-stat-label">Success (24h)</div>
        </div>
      </div>
      <div class="dash-stat">
        <div class="dash-stat-icon ${errVariant}">${Icons.alertCircle}</div>
        <div>
          <div class="dash-stat-value">${errors}</div>
          <div class="dash-stat-label">Errors (24h)</div>
        </div>
      </div>
      <div class="dash-stat">
        <div class="dash-stat-icon info">${Icons.clock}</div>
        <div>
          <div class="dash-stat-value">${avgDuration}</div>
          <div class="dash-stat-label">Avg Duration</div>
        </div>
      </div>
    `;

    document.getElementById('dash-stats').innerHTML = html;
  },

  renderActivity(executions) {
    const rows = executions.slice(0, 12).map(exec => {
      const duration = exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(1)}s` : '-';
      const statusBadge = Components.statusBadge(exec.status);
      const jobName = (exec.job_id || '').replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return `
        <tr>
          <td style="white-space:nowrap">${Format.time(exec.started_at)}</td>
          <td>${Utils.escapeHtml(jobName)}</td>
          <td>${statusBadge}</td>
          <td style="font-family:var(--font-mono);font-size:var(--text-xs)">${duration}</td>
        </tr>
      `;
    }).join('');

    document.getElementById('dash-activity-body').innerHTML = `
      <table class="dash-table">
        <thead>
          <tr>
            <th style="width:80px">Time</th>
            <th>Job</th>
            <th style="width:80px">Status</th>
            <th style="width:70px">Duration</th>
          </tr>
        </thead>
        <tbody>${rows || '<tr><td colspan="4" class="dash-empty">No recent executions</td></tr>'}</tbody>
      </table>
    `;
  },

  renderActivityFromJobs(jobs) {
    const recentJobs = jobs
      .filter(j => j.last_run)
      .sort((a, b) => new Date(b.last_run) - new Date(a.last_run))
      .slice(0, 10);

    const rows = recentJobs.map(job => {
      const duration = job.last_duration_ms ? `${(job.last_duration_ms / 1000).toFixed(1)}s` : '-';
      const status = job.last_success !== false ? 'running' : 'error';
      return `
        <tr>
          <td style="white-space:nowrap">${Format.time(job.last_run)}</td>
          <td>${Utils.escapeHtml(job.name || job.id)}</td>
          <td>${Components.statusBadge(status)}</td>
          <td style="font-family:var(--font-mono);font-size:var(--text-xs)">${duration}</td>
        </tr>
      `;
    }).join('');

    document.getElementById('dash-activity-body').innerHTML = `
      <table class="dash-table">
        <thead>
          <tr>
            <th style="width:80px">Time</th>
            <th>Job</th>
            <th style="width:80px">Status</th>
            <th style="width:70px">Duration</th>
          </tr>
        </thead>
        <tbody>${rows || '<tr><td colspan="4" class="dash-empty">No recent activity</td></tr>'}</tbody>
      </table>
    `;
  },

  renderUpcoming(jobs) {
    const upcoming = jobs
      .filter(j => j.next_run && j.enabled !== false)
      .sort((a, b) => new Date(a.next_run) - new Date(b.next_run))
      .slice(0, 8);

    const html = upcoming.length
      ? upcoming.map(job => `
          <div class="dash-upcoming-item">
            <span>${Utils.escapeHtml(job.name || job.id)}</span>
            <span class="dash-upcoming-time">${Format.relativeTime(job.next_run)}</span>
          </div>
        `).join('')
      : '<div class="dash-empty">No upcoming jobs</div>';

    document.getElementById('dash-upcoming').innerHTML = html;
  },

  renderErrors(statsData) {
    const failures = statsData && statsData.recent_failures ? statsData.recent_failures : [];
    const panel = document.getElementById('dash-errors-panel');

    if (!failures.length) {
      // Hide errors panel entirely, make upcoming full width
      if (panel) panel.style.display = 'none';
      const bottom = document.getElementById('dash-bottom');
      if (bottom) bottom.style.gridTemplateColumns = '1fr';
      return;
    }

    const html = failures.slice(0, 5).map(f => {
      const jobName = (f.job_id || '').replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return `
        <div class="dash-error-item">
          <div class="dash-error-job">${Utils.escapeHtml(jobName)}</div>
          ${f.error ? `<div class="dash-error-msg" title="${Utils.escapeHtml(f.error)}">${Utils.escapeHtml(f.error)}</div>` : ''}
          <div class="dash-error-time">${Format.relativeTime(f.timestamp)}</div>
        </div>
      `;
    }).join('');

    document.getElementById('dash-errors').innerHTML = html;
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
    second_brain: {
      name: 'Second Brain',
      icon: Icons.brain,
      managed: 'Supabase',
      description: 'Unified memory — Supabase + pgvector',
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
      { key: 'second_brain', name: 'Second Brain', icon: Icons.brain },
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
  filtered: [],
  // Current filter state
  _sourceFilter: 'all',
  _typeFilter: 'all',
  _projectFilter: 'all',
  _categoryFilter: 'all',
  _searchQuery: '',

  // Source display names and CSS class suffixes
  _sourceLabels: {
    'peterbot': 'Peterbot',
    'global-skill': 'Global Skill',
    'project-command': 'Project Command',
    'global-command': 'Global Command',
  },

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Skills Directory</h2>
            <p class="text-secondary">Browse skills and commands from all sources</p>
          </div>
          <div class="data-table-search">
            <span class="data-table-search-icon">${Icons.search}</span>
            <input type="text" placeholder="Search skills..."
                   id="skills-search-input"
                   oninput="SkillsView.onSearch(this.value)">
          </div>
        </div>

        <div id="skills-stats-bar" class="stats-bar"></div>

        <div class="filter-bar" id="skills-filter-bar">
          <select class="form-select" id="skills-filter-source" onchange="SkillsView.onFilterChange()">
            <option value="all">All Sources</option>
            <option value="peterbot">Peterbot</option>
            <option value="global-skill">Global Skills</option>
            <option value="project-command">Project Commands</option>
            <option value="global-command">Global Commands</option>
          </select>
          <select class="form-select" id="skills-filter-type" onchange="SkillsView.onFilterChange()">
            <option value="all">All Types</option>
            <option value="scheduled">Scheduled</option>
            <option value="triggered">Triggered</option>
            <option value="conversational">Conversational</option>
            <option value="command">Command</option>
          </select>
          <select class="form-select" id="skills-filter-project" onchange="SkillsView.onFilterChange()">
            <option value="all">All Projects</option>
          </select>
          <select class="form-select" id="skills-filter-category" onchange="SkillsView.onFilterChange()">
            <option value="all">All Categories</option>
          </select>
        </div>

        <div class="grid grid-cols-4 gap-md" id="skills-grid">
          ${Components.skeleton('card')}
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
      const data = await API.get('/api/skills/directory');
      this.skills = data.skills || [];
      State.set({ skills: this.skills });
      this._populateFilterDropdowns();
      this.applyFilters();
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

  _populateFilterDropdowns() {
    // Populate project dropdown from data
    const projects = [...new Set(
      this.skills
        .filter(s => s.shared_with && s.shared_with.length > 0)
        .flatMap(s => s.shared_with)
    )].sort();
    const projSelect = document.getElementById('skills-filter-project');
    if (projSelect) {
      projSelect.innerHTML = '<option value="all">All Projects</option>' +
        projects.map(p => `<option value="${p}">${p}</option>`).join('');
    }

    // Populate category dropdown from data
    const categories = [...new Set(
      this.skills
        .filter(s => s.category)
        .map(s => s.category)
    )].sort();
    const catSelect = document.getElementById('skills-filter-category');
    if (catSelect) {
      catSelect.innerHTML = '<option value="all">All Categories</option>' +
        categories.map(c => `<option value="${c}">${c}</option>`).join('');
    }
  },

  onSearch(query) {
    this._searchQuery = query;
    this.applyFilters();
  },

  onFilterChange() {
    this._sourceFilter = document.getElementById('skills-filter-source')?.value || 'all';
    this._typeFilter = document.getElementById('skills-filter-type')?.value || 'all';
    this._projectFilter = document.getElementById('skills-filter-project')?.value || 'all';
    this._categoryFilter = document.getElementById('skills-filter-category')?.value || 'all';

    // Disable/enable contextual filters (F11, F12)
    const projSelect = document.getElementById('skills-filter-project');
    const catSelect = document.getElementById('skills-filter-category');
    if (projSelect) {
      const showProject = this._sourceFilter === 'all' || this._sourceFilter === 'project-command';
      projSelect.disabled = !showProject;
      if (!showProject) { projSelect.value = 'all'; this._projectFilter = 'all'; }
    }
    if (catSelect) {
      const showCategory = this._sourceFilter === 'all' || this._sourceFilter === 'peterbot';
      catSelect.disabled = !showCategory;
      if (!showCategory) { catSelect.value = 'all'; this._categoryFilter = 'all'; }
    }

    this.applyFilters();
  },

  applyFilters() {
    const q = this._searchQuery.toLowerCase();
    this.filtered = this.skills.filter(s => {
      // Source filter (F9)
      if (this._sourceFilter !== 'all' && s.source !== this._sourceFilter) return false;

      // Type filter (F10) — match if type equals OR if skill has the property
      if (this._typeFilter !== 'all') {
        if (this._typeFilter === 'scheduled' && !s.scheduled) return false;
        if (this._typeFilter === 'triggered' && (!s.triggers || s.triggers.length === 0)) return false;
        if (this._typeFilter === 'conversational' && !s.conversational) return false;
        if (this._typeFilter === 'command' && s.type !== 'command') return false;
      }

      // Project filter (F11) — match if project equals OR project is in shared_with
      if (this._projectFilter !== 'all') {
        const inShared = s.shared_with && s.shared_with.includes(this._projectFilter);
        const isProject = s.project === this._projectFilter;
        if (!inShared && !isProject) return false;
      }

      // Category filter (F12)
      if (this._categoryFilter !== 'all' && s.category !== this._categoryFilter) return false;

      // Search (F13)
      if (q) {
        const name = (s.name || '').toLowerCase();
        const desc = (s.description || '').toLowerCase();
        const triggers = (s.triggers || []).join(' ').toLowerCase();
        if (!name.includes(q) && !desc.includes(q) && !triggers.includes(q)) return false;
      }

      return true;
    });

    this.renderStatsBar();
    this.renderSkills(this.filtered);
  },

  renderStatsBar() {
    const bar = document.getElementById('skills-stats-bar');
    if (!bar) return;

    const total = this.skills.length;
    const shown = this.filtered.length;
    const isFiltered = shown !== total;

    const bySrc = {};
    for (const s of this.filtered) {
      bySrc[s.source] = (bySrc[s.source] || 0) + 1;
    }

    const countText = isFiltered ? `${shown} of ${total} skills` : `${total} skills`;
    const chips = Object.entries(this._sourceLabels)
      .filter(([key]) => bySrc[key])
      .map(([key, label]) => `<span class="stats-chip stats-chip-${key}">${bySrc[key]} ${label}</span>`)
      .join('<span class="stats-bar-sep">|</span>');

    bar.innerHTML = `<span class="stats-bar-total">${countText}</span><span class="stats-bar-sep">&mdash;</span>${chips}`;
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

    const html = skills.map(skill => {
      const name = skill.name || 'unknown';
      const desc = skill.description || 'No description';
      const sourceLabel = this._sourceLabels[skill.source] || skill.source;
      const sourceCls = `skill-badge-source-${skill.source}`;
      const hasTriggers = skill.triggers && skill.triggers.length > 0;
      const runsOnCls = skill.runs_on === 'wsl' ? 'skill-runs-on-wsl' : 'skill-runs-on-win';
      const runsOnLabel = skill.runs_on === 'wsl' ? 'WSL' : 'Win';

      // Project badge (F15)
      let projectBadge = '';
      if (skill.project_count > 1) {
        projectBadge = `<span class="skill-badge skill-badge-project">${skill.project_count} projects</span>`;
      } else if (skill.project_count === 1 && skill.shared_with && skill.shared_with.length === 1) {
        projectBadge = `<span class="skill-badge skill-badge-project">${skill.shared_with[0]}</span>`;
      }

      // Escape single quotes in ID for onclick
      const safeId = (skill.id || '').replace(/'/g, "\\'");

      return `
        <div class="skill-card" onclick="SkillsView.select('${safeId}')">
          <div class="skill-card-header">
            <div class="skill-card-name">${name}</div>
            <span class="skill-runs-on ${runsOnCls}">${runsOnLabel}</span>
          </div>
          <div class="skill-card-desc">${desc}</div>
          <div class="skill-card-badges">
            <span class="skill-badge ${sourceCls}">${sourceLabel}</span>
            ${skill.scheduled ? `<span class="skill-badge skill-badge-scheduled">${Icons.clock} Scheduled</span>` : ''}
            ${hasTriggers ? `<span class="skill-badge skill-badge-trigger">${Icons.messageCircle} Triggers</span>` : ''}
            ${skill.conversational ? `<span class="skill-badge skill-badge-conversational">${Icons.messageCircle} Chat</span>` : ''}
            ${projectBadge}
          </div>
        </div>
      `;
    }).join('');

    document.getElementById('skills-grid').innerHTML = html;
  },

  filter(query) {
    // Legacy compat — redirect to new search
    this._searchQuery = query;
    this.applyFilters();
  },

  async select(skillId) {
    try {
      const response = await API.get(`/api/skills/directory/${encodeURIComponent(skillId)}`);

      if (!response.exists) {
        Toast.error('Error', 'Skill not found');
        return;
      }

      // Find skill metadata from the loaded list
      const skillMeta = this.skills.find(s => s.id === skillId) || {};
      const hasTriggers = skillMeta.triggers && skillMeta.triggers.length > 0;
      const sourceLabel = this._sourceLabels[skillMeta.source] || skillMeta.source || '';
      const sourceCls = `skill-badge-source-${skillMeta.source || 'peterbot'}`;

      // Strip frontmatter from content for cleaner display
      let markdown = response.content || '';
      markdown = markdown.replace(/^---[\s\S]*?---\s*/, '');

      // Shared projects chips (F19)
      let sharedHtml = '';
      if (skillMeta.shared_with && skillMeta.shared_with.length > 0) {
        sharedHtml = `
          <div class="skill-detail-row">
            <span class="skill-detail-label">Projects</span>
            <span class="skill-detail-value">${skillMeta.shared_with.map(p => `<span class="skill-project-chip">${p}</span>`).join('')}</span>
          </div>
        `;
      }

      // Last modified
      let modifiedHtml = '';
      if (response.last_modified || skillMeta.last_modified) {
        const dt = response.last_modified || skillMeta.last_modified;
        const formatted = new Date(dt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        modifiedHtml = `
          <div class="skill-detail-row">
            <span class="skill-detail-label">Modified</span>
            <span class="skill-detail-value">${formatted}</span>
          </div>
        `;
      }

      const runsOnCls = (skillMeta.runs_on === 'wsl') ? 'skill-runs-on-wsl' : 'skill-runs-on-win';
      const runsOnLabel = (skillMeta.runs_on === 'wsl') ? 'WSL' : 'Windows';

      const content = `
        <div class="skill-detail-header">
          <div class="skill-detail-title">${response.name || skillMeta.name || skillId}</div>
          <div class="skill-detail-desc">${skillMeta.description || ''}</div>
          <div class="skill-detail-meta">
            <span class="skill-badge ${sourceCls}">${sourceLabel}</span>
            ${skillMeta.scheduled ? `<span class="skill-badge skill-badge-scheduled">${Icons.clock} Scheduled</span>` : ''}
            ${hasTriggers ? `<span class="skill-badge skill-badge-trigger">${Icons.messageCircle} Triggers</span>` : ''}
            ${skillMeta.conversational ? `<span class="skill-badge skill-badge-conversational">${Icons.messageCircle} Chat</span>` : ''}
          </div>
          ${hasTriggers ? `
            <div class="skill-detail-triggers">
              <div class="skill-detail-triggers-label">Trigger phrases</div>
              <div>${skillMeta.triggers.map(t => `<span class="skill-trigger-chip">${t}</span>`).join('')}</div>
            </div>
          ` : ''}
        </div>
        <div style="padding: var(--spacing-md) var(--spacing-lg);">
          <div class="skill-detail-row">
            <span class="skill-detail-label">Source</span>
            <span class="skill-detail-value"><span class="skill-badge ${sourceCls}">${sourceLabel}</span></span>
          </div>
          <div class="skill-detail-row">
            <span class="skill-detail-label">Runs on</span>
            <span class="skill-detail-value"><span class="skill-runs-on ${runsOnCls}">${runsOnLabel}</span></span>
          </div>
          ${sharedHtml}
          <div class="skill-detail-row">
            <span class="skill-detail-label">Path</span>
            <span class="skill-detail-value skill-detail-path">${response.path || skillMeta.path || ''}</span>
          </div>
          ${modifiedHtml}
          ${skillMeta.category ? `
            <div class="skill-detail-row">
              <span class="skill-detail-label">Category</span>
              <span class="skill-detail-value">${skillMeta.category}</span>
            </div>
          ` : ''}
        </div>
        <div style="padding: 0 var(--spacing-lg) var(--spacing-lg);">
          <div class="markdown-preview">${Utils.renderMarkdown(markdown)}</div>
        </div>
      `;

      DetailPanel.open(content);
    } catch (error) {
      Toast.error('Error', `Failed to load skill: ${error.message}`);
    }
  },
};


/**
 * Logs View - Datadog-inspired observability log viewer (F1-F10)
 */
const LogsView = {
  title: 'Logs',
  logs: [],
  allLogs: [],
  sources: [],
  facets: { sources: [], levels: [], top_patterns: [] },
  histogram: [],

  // Filter state
  activeSources: new Set(),
  activeLevels: new Set(),
  currentSearch: '',
  parsedQuery: { qualifiers: {}, freeText: '' },

  // UI state
  groupEnabled: true,
  hideNoise: true,
  liveTail: false,
  _liveTailInterval: null,
  _lastTimestamp: null,
  _userScrolledUp: false,
  _activeView: 'All',

  // Saved views (F8)
  savedViews: [
    { name: 'All', icon: '', filters: {} },
    { name: 'Errors Only', icon: '', filters: { level: 'ERROR,CRITICAL' } },
    { name: 'Warnings+', icon: '', filters: { level: 'WARNING,ERROR,CRITICAL' } },
    { name: 'Startup', icon: '', filters: { search: 'Starting logging in connected to Gateway' } },
    { name: 'Scheduler', icon: '', filters: { search: 'scheduler job cron', source: 'discord_bot' } },
    { name: 'HTTP Requests', icon: '', filters: { source: 'hadley_api' } },
    { name: 'No Health Checks', icon: '', filters: { excludeNoise: true } },
  ],

  async render(container) {
    // Load saved preferences from localStorage
    const savedHideNoise = localStorage.getItem('peter_logs_hide_noise');
    if (savedHideNoise !== null) this.hideNoise = savedHideNoise !== 'false';
    const savedGroup = localStorage.getItem('peter_logs_group');
    if (savedGroup !== null) this.groupEnabled = savedGroup !== 'false';

    container.innerHTML = `
      <div class="animate-fade-in logs-page">
        <!-- Saved View Pills (F8) -->
        <div class="saved-view-pills" id="logs-saved-views"></div>

        <!-- Toolbar -->
        <div class="logs-toolbar">
          <div class="logs-toolbar-left">
            <div class="logs-search-container">
              <span class="data-table-search-icon">${Icons.search}</span>
              <input type="text" class="logs-search-input" placeholder="Search... (source:x level:y text)"
                     id="logs-search-input" oninput="LogsView.onSearchInput(this.value)"
                     onkeydown="LogsView.onSearchKeydown(event)">
            </div>
            <div class="query-chips" id="logs-query-chips"></div>
          </div>
          <div class="logs-toolbar-right">
            <button class="btn btn-sm ${this.groupEnabled ? 'btn-primary' : 'btn-secondary'}"
                    onclick="LogsView.toggleGroup()" id="logs-group-btn"
                    title="Group similar consecutive entries">
              Group
            </button>
            <button class="btn btn-sm ${this.hideNoise ? 'btn-primary' : 'btn-secondary'}"
                    onclick="LogsView.toggleNoise()" id="logs-noise-btn"
                    title="Hide known noise patterns">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
              Hide Noise
            </button>
            <button class="btn btn-sm ${this.liveTail ? 'btn-accent' : 'btn-secondary'}"
                    onclick="LogsView.toggleLiveTail()" id="logs-live-btn"
                    title="Auto-refresh logs every 2 seconds">
              <span class="live-indicator ${this.liveTail ? 'active' : ''}" id="logs-live-dot"></span>
              Live Tail
            </button>
            <button class="btn btn-sm btn-secondary" onclick="LogsView.refresh()">
              ${Icons.refresh}
            </button>
          </div>
        </div>

        <!-- Log Volume Timeline (F1) -->
        <div class="logs-timeline card" id="logs-timeline">
          <svg id="logs-timeline-svg" width="100%" height="80"></svg>
        </div>

        <!-- Main layout: facet sidebar + log list -->
        <div class="logs-layout">
          <!-- Faceted Sidebar (F3) -->
          <aside class="logs-facets card" id="logs-facets">
            <div class="facet-section" id="facet-sources">
              <div class="facet-section-header" onclick="LogsView.toggleFacetSection('sources')">
                <span>Sources</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div class="facet-section-body" id="facet-sources-body"></div>
            </div>
            <div class="facet-section" id="facet-levels">
              <div class="facet-section-header" onclick="LogsView.toggleFacetSection('levels')">
                <span>Levels</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div class="facet-section-body" id="facet-levels-body"></div>
            </div>
            <div class="facet-section" id="facet-patterns">
              <div class="facet-section-header" onclick="LogsView.toggleFacetSection('patterns')">
                <span>Top Patterns</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div class="facet-section-body" id="facet-patterns-body"></div>
            </div>
          </aside>

          <!-- Log entries -->
          <div class="logs-main">
            <div class="logs-count-bar" id="logs-count-bar"></div>
            <div class="card logs-list-card">
              <div class="logs-list" id="logs-container">
                ${Components.skeleton('text', 10)}
              </div>
            </div>
            <!-- Jump to live pill (F5) -->
            <div class="logs-jump-pill" id="logs-jump-pill" onclick="LogsView.jumpToLive()" style="display:none;">
              Jump to live
            </div>
          </div>
        </div>
      </div>
    `;

    this.renderSavedViews();
    // Scroll detection for live tail
    const logsContainer = document.getElementById('logs-container');
    if (logsContainer) {
      logsContainer.addEventListener('scroll', () => {
        const el = logsContainer;
        this._userScrolledUp = (el.scrollHeight - el.scrollTop - el.clientHeight) > 50;
        const pill = document.getElementById('logs-jump-pill');
        if (pill) pill.style.display = (this.liveTail && this._userScrolledUp) ? 'block' : 'none';
      });
    }

    await Promise.all([this.loadSources(), this.loadHistogram(), this.loadFacets(), this.loadData()]);
  },

  // =========================================================================
  // Data loading
  // =========================================================================

  async loadSources() {
    try {
      const data = await API.get('/api/logs/sources');
      this.sources = data.sources || [];
    } catch (error) {
      console.error('Failed to load log sources:', error);
    }
  },

  _buildParams() {
    const params = new URLSearchParams();
    params.set('limit', '200');
    params.set('group', this.groupEnabled ? 'true' : 'false');
    params.set('suppress_noise', 'true');

    // Source from facets or query
    const sources = this.parsedQuery.qualifiers.source
      ? [this.parsedQuery.qualifiers.source]
      : (this.activeSources.size > 0 ? [...this.activeSources] : []);
    if (sources.length === 1) params.set('source', sources[0]);

    // Level from facets or query
    const levels = this.parsedQuery.qualifiers.level
      ? [this.parsedQuery.qualifiers.level.toUpperCase()]
      : (this.activeLevels.size > 0 ? [...this.activeLevels] : []);
    if (levels.length > 0) params.set('level', levels.join(','));

    // Search text
    const search = this.parsedQuery.freeText || '';
    if (search) params.set('search', search);

    // Time range from qualifiers
    if (this.parsedQuery.qualifiers.since) params.set('since', this.parsedQuery.qualifiers.since);
    if (this.parsedQuery.qualifiers.until) params.set('until', this.parsedQuery.qualifiers.until);

    return params;
  },

  async loadData() {
    try {
      const params = this._buildParams();
      console.log('[LogsView] loadData URL:', `/api/logs/unified?${params.toString()}`);
      const data = await API.get(`/api/logs/unified?${params.toString()}`);
      console.log('[LogsView] Got', (data.logs || []).length, 'entries');
      this.allLogs = data.logs || [];
      this.logs = this.allLogs;
      if (this.logs.length > 0 && this.logs[0].timestamp) {
        this._lastTimestamp = this.logs[0].timestamp;
      }
      this.renderLogs(this.logs);
      this.updateCountBar(data.total);
    } catch (error) {
      console.error('Failed to load logs:', error);
      const container = document.getElementById('logs-container');
      if (container) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-title">Failed to load logs</div>
            <p class="text-secondary">${error.message}</p>
          </div>
        `;
      }
    }
  },

  async loadHistogram() {
    try {
      const params = new URLSearchParams({ hours: '6', buckets: '60' });
      if (this.activeSources.size === 1) params.set('source', [...this.activeSources][0]);
      const data = await API.get(`/api/logs/histogram?${params.toString()}`);
      this.histogram = data.histogram || [];
      this.renderTimeline();
    } catch (error) {
      console.error('Failed to load histogram:', error);
    }
  },

  async loadFacets() {
    try {
      const params = new URLSearchParams({ hours: '6' });
      const data = await API.get(`/api/logs/facets?${params.toString()}`);
      this.facets = data;
      this.renderFacets();
    } catch (error) {
      console.error('Failed to load facets:', error);
    }
  },

  // =========================================================================
  // Timeline (F1) - D3 stacked bar chart
  // =========================================================================

  renderTimeline() {
    const svg = document.getElementById('logs-timeline-svg');
    if (!svg || !this.histogram.length) return;

    const container = document.getElementById('logs-timeline');
    const width = container.clientWidth - 24;
    const height = 70;
    const margin = { top: 5, right: 10, bottom: 18, left: 10 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    svg.innerHTML = '';
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const data = this.histogram;
    const barW = Math.max(2, Math.floor(innerW / data.length) - 1);

    const maxTotal = Math.max(1, ...data.map(d =>
      d.counts.DEBUG + d.counts.INFO + d.counts.WARNING + d.counts.ERROR
    ));

    const colors = {
      DEBUG: 'var(--text-muted)',
      INFO: 'var(--accent)',
      WARNING: 'var(--status-paused)',
      ERROR: 'var(--status-error)',
    };
    const order = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];

    let barsHtml = '';
    data.forEach((bucket, i) => {
      const x = margin.left + i * (barW + 1);
      let y = innerH + margin.top;

      order.forEach(level => {
        const count = bucket.counts[level];
        if (count === 0) return;
        const h = Math.max(1, (count / maxTotal) * innerH);
        y -= h;
        barsHtml += `<rect x="${x}" y="${y}" width="${barW}" height="${h}"
          fill="${colors[level]}" rx="1" opacity="0.85"
          class="timeline-bar"
          onmouseover="LogsView.showTimelineTip(event, ${i})"
          onmouseout="LogsView.hideTimelineTip()"
          onclick="LogsView.clickTimelineBucket(${i})" />`;
      });
    });

    let labelsHtml = '';
    const step = Math.max(1, Math.floor(data.length / 6));
    for (let i = 0; i < data.length; i += step) {
      const ts = new Date(data[i].timestamp);
      const label = ts.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      const x = margin.left + i * (barW + 1) + barW / 2;
      labelsHtml += `<text x="${x}" y="${height - 2}" text-anchor="middle"
        fill="var(--text-muted)" font-size="10" font-family="var(--font-sans)">${label}</text>`;
    }

    svg.innerHTML = barsHtml + labelsHtml +
      `<g id="timeline-tooltip" style="display:none">
        <rect rx="4" fill="var(--bg-sidebar)" opacity="0.95" id="tt-bg"/>
        <text fill="var(--text-inverse)" font-size="11" font-family="var(--font-sans)" id="tt-text"/>
      </g>`;
  },

  showTimelineTip(event, bucketIdx) {
    const bucket = this.histogram[bucketIdx];
    if (!bucket) return;
    const ts = new Date(bucket.timestamp);
    const label = ts.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    const total = bucket.counts.DEBUG + bucket.counts.INFO + bucket.counts.WARNING + bucket.counts.ERROR;
    const tip = `${label} - ${total} logs (E:${bucket.counts.ERROR} W:${bucket.counts.WARNING} I:${bucket.counts.INFO})`;

    const svg = document.getElementById('logs-timeline-svg');
    const tooltip = document.getElementById('timeline-tooltip');
    const ttBg = document.getElementById('tt-bg');
    const ttText = document.getElementById('tt-text');
    if (!tooltip || !ttBg || !ttText) return;

    const rect = svg.getBoundingClientRect();
    const x = Math.min(Math.max(event.clientX - rect.left, 60), rect.width - 160);

    ttText.textContent = tip;
    ttText.setAttribute('x', x + 8);
    ttText.setAttribute('y', 14);
    ttBg.setAttribute('x', x);
    ttBg.setAttribute('y', 1);
    ttBg.setAttribute('width', tip.length * 6.5 + 16);
    ttBg.setAttribute('height', 20);
    tooltip.style.display = '';
  },

  hideTimelineTip() {
    const tooltip = document.getElementById('timeline-tooltip');
    if (tooltip) tooltip.style.display = 'none';
  },

  clickTimelineBucket(idx) {
    const bucket = this.histogram[idx];
    if (!bucket) return;
    const bucketSeconds = this.histogram.length > 1
      ? (new Date(this.histogram[1].timestamp) - new Date(this.histogram[0].timestamp)) / 1000
      : 360;
    const start = new Date(bucket.timestamp);
    const end = new Date(start.getTime() + bucketSeconds * 1000);
    this.addChip('since', start.toISOString());
    this.addChip('until', end.toISOString());
    this.applyFilters();
  },

  // =========================================================================
  // Facets Sidebar (F3)
  // =========================================================================

  renderFacets() {
    const sourcesBody = document.getElementById('facet-sources-body');
    if (sourcesBody && this.facets.sources) {
      sourcesBody.innerHTML = this.facets.sources.map(s => {
        const active = this.activeSources.has(s.name);
        return `<div class="facet-item ${active ? 'active' : ''}"
                     onclick="LogsView.toggleFacet('source', '${s.name}')">
          <span class="facet-item-name">${Utils.escapeHtml(s.display_name || s.name)}</span>
          <span class="facet-item-count">${s.count}</span>
        </div>`;
      }).join('');
    }

    const levelsBody = document.getElementById('facet-levels-body');
    if (levelsBody && this.facets.levels) {
      const levelColors = { ERROR: 'var(--status-error)', WARNING: 'var(--status-paused)', INFO: 'var(--accent)', DEBUG: 'var(--text-muted)' };
      levelsBody.innerHTML = this.facets.levels.map(l => {
        const active = this.activeLevels.has(l.name);
        const color = levelColors[l.name] || 'var(--text-muted)';
        return `<div class="facet-item ${active ? 'active' : ''}"
                     onclick="LogsView.toggleFacet('level', '${l.name}')">
          <span class="facet-level-dot" style="background:${color}"></span>
          <span class="facet-item-name">${l.name}</span>
          <span class="facet-item-count">${l.count}</span>
        </div>`;
      }).join('');
    }

    const patternsBody = document.getElementById('facet-patterns-body');
    if (patternsBody && this.facets.top_patterns) {
      patternsBody.innerHTML = this.facets.top_patterns.slice(0, 8).map(p => {
        const short = (p.pattern || '').slice(0, 50);
        return `<div class="facet-item facet-pattern"
                     onclick="LogsView.onSearchInput('${Utils.escapeHtml(p.sample.slice(0, 40).replace(/'/g, ''))}')"
                     title="${Utils.escapeHtml(p.sample)}">
          <span class="facet-item-name">${Utils.escapeHtml(short)}</span>
          <span class="facet-item-count">${p.count}</span>
        </div>`;
      }).join('');
    }
  },

  toggleFacetSection(section) {
    const body = document.getElementById(`facet-${section}-body`);
    if (body) body.classList.toggle('collapsed');
  },

  toggleFacet(type, value) {
    const set = type === 'source' ? this.activeSources : this.activeLevels;
    if (set.has(value)) {
      set.delete(value);
    } else {
      set.add(value);
    }
    this.applyFilters();
  },

  // =========================================================================
  // Search / Query Chips (F7)
  // =========================================================================

  _parseQuery(raw) {
    const qualifiers = {};
    const remainder = raw.replace(/(\w+):(\S+)/g, (match, key, val) => {
      qualifiers[key.toLowerCase()] = val;
      return '';
    }).trim();
    return { qualifiers, freeText: remainder };
  },

  onSearchInput(value) {
    const input = document.getElementById('logs-search-input');
    if (input && input.value !== value) input.value = value;
    this.currentSearch = value;
    this.parsedQuery = this._parseQuery(value);
    this.renderChips();
    clearTimeout(this._searchTimeout);
    this._searchTimeout = setTimeout(() => this.applyFilters(), 300);
  },

  onSearchKeydown(event) {
    if (event.key === 'Enter') {
      clearTimeout(this._searchTimeout);
      this.applyFilters();
    }
  },

  addChip(key, value) {
    this.parsedQuery.qualifiers[key] = value;
    this._rebuildSearchFromQuery();
    this.renderChips();
  },

  removeChip(key) {
    delete this.parsedQuery.qualifiers[key];
    if (key === 'source') this.activeSources.clear();
    if (key === 'level') this.activeLevels.clear();
    this._rebuildSearchFromQuery();
    this.renderChips();
    this.applyFilters();
  },

  _rebuildSearchFromQuery() {
    const parts = [];
    for (const [k, v] of Object.entries(this.parsedQuery.qualifiers)) {
      parts.push(`${k}:${v}`);
    }
    if (this.parsedQuery.freeText) parts.push(this.parsedQuery.freeText);
    const input = document.getElementById('logs-search-input');
    if (input) input.value = parts.join(' ');
    this.currentSearch = parts.join(' ');
  },

  renderChips() {
    const container = document.getElementById('logs-query-chips');
    if (!container) return;
    const quals = this.parsedQuery.qualifiers;
    if (Object.keys(quals).length === 0) {
      container.innerHTML = '';
      return;
    }
    container.innerHTML = Object.entries(quals).map(([k, v]) => {
      const displayVal = (k === 'since' || k === 'until')
        ? new Date(v).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
        : v;
      return `<span class="query-chip">
        ${k}:${Utils.escapeHtml(displayVal)}
        <span class="query-chip-remove" onclick="LogsView.removeChip('${k}')">&times;</span>
      </span>`;
    }).join('');
  },

  // =========================================================================
  // Saved Views (F8)
  // =========================================================================

  renderSavedViews() {
    const container = document.getElementById('logs-saved-views');
    if (!container) return;
    container.innerHTML = this.savedViews.map(v => {
      const active = this._activeView === v.name;
      return `<button class="saved-view-pill ${active ? 'active' : ''}"
                      onclick="LogsView.applySavedView('${v.name}')">
        ${v.name}
      </button>`;
    }).join('');
  },

  applySavedView(name) {
    const view = this.savedViews.find(v => v.name === name);
    if (!view) return;
    this._activeView = name;

    // Reset filters
    this.activeSources.clear();
    this.activeLevels.clear();
    this.parsedQuery = { qualifiers: {}, freeText: '' };

    const f = view.filters;
    if (f.source) {
      this.activeSources.add(f.source);
      this.parsedQuery.qualifiers.source = f.source;
    }
    if (f.level) {
      this.parsedQuery.qualifiers.level = f.level;
    }
    if (f.search) {
      this.parsedQuery.freeText = f.search;
    }
    if (f.excludeNoise) {
      this.hideNoise = true;
      this._updateNoiseBtn();
    }

    this._rebuildSearchFromQuery();
    this.renderChips();
    this.renderSavedViews();
    this.applyFilters();
  },

  // =========================================================================
  // Filter application
  // =========================================================================

  applyFilters() {
    this.loadData();
    this.loadFacets();
  },

  // =========================================================================
  // Log Rendering (F2, F4, F9, F10)
  // =========================================================================

  updateCountBar(total) {
    const bar = document.getElementById('logs-count-bar');
    if (!bar) return;
    const noiseCount = this.logs.filter(l => l.noise).length;
    const liveLabel = this.liveTail
      ? ' <span class="live-indicator active"></span> <span style="color:var(--status-running)">live</span>'
      : '';
    bar.innerHTML = `Showing ${this.logs.length} logs${liveLabel}` +
      (this.hideNoise && noiseCount > 0 ? ` <span class="log-noise-indicator">${noiseCount} noise lines hidden</span>` : '');
  },

  renderLogs(logs) {
    const container = document.getElementById('logs-container');
    if (!container) return;

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

    let html = '';
    let hiddenNoiseCount = 0;

    for (const log of logs) {
      if (this.hideNoise && log.noise) {
        hiddenNoiseCount++;
        continue;
      }

      // Flush hidden noise indicator
      if (hiddenNoiseCount > 0) {
        html += `<div class="log-noise-bar" onclick="this.classList.toggle('expanded')">
          ${hiddenNoiseCount} noise line${hiddenNoiseCount > 1 ? 's' : ''} hidden
        </div>`;
        hiddenNoiseCount = 0;
      }

      html += this.renderLogEntry(log);
    }

    // Final noise indicator
    if (hiddenNoiseCount > 0) {
      html += `<div class="log-noise-bar">${hiddenNoiseCount} noise line${hiddenNoiseCount > 1 ? 's' : ''} hidden</div>`;
    }

    container.innerHTML = html;
  },

  renderLogEntry(log) {
    const level = (log.level || 'INFO').toUpperCase();
    const levelLower = level.toLowerCase();
    const source = log.source || 'unknown';
    const message = log.message || '';
    const timestamp = log.timestamp ? Format.datetime(log.timestamp) : '';
    const hasTraceback = log.extra_lines && log.extra_lines.length > 0;
    const isGrouped = (log.group_count || 1) > 1;
    const entryId = log.id;
    const noiseClass = log.noise ? ' log-entry-noise' : '';

    let tracebackHtml = '';
    if (hasTraceback) {
      const frameCount = log.traceback_frames || 0;
      tracebackHtml = `
        <div class="log-traceback-toggle" onclick="event.stopPropagation(); this.nextElementSibling.classList.toggle('expanded'); this.classList.toggle('open')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
          <span class="log-traceback-badge">${frameCount} frame${frameCount !== 1 ? 's' : ''}</span>
        </div>
        <div class="log-traceback">${log.extra_lines.map(l => Utils.escapeHtml(l)).join('\n')}</div>
      `;
    }

    let groupHtml = '';
    if (isGrouped) {
      groupHtml = `<span class="log-group-count" onclick="event.stopPropagation(); LogsView.expandGroup('${entryId}')"
                         title="Click to expand">&times;${log.group_count}</span>`;
    }

    let statusClass = '';
    if (log.metadata && log.metadata.status) {
      const s = log.metadata.status;
      if (s >= 200 && s < 300) statusClass = 'http-2xx';
      else if (s >= 400 && s < 500) statusClass = 'http-4xx';
      else if (s >= 500) statusClass = 'http-5xx';
    }

    return `
      <div class="log-entry level-${levelLower}${isGrouped ? ' log-entry-grouped' : ''}${noiseClass}"
           data-id="${entryId}" onclick="LogsView.openDetail(this)" data-log="${btoa(JSON.stringify(log))}">
        <span class="log-timestamp">${timestamp}</span>
        <span class="log-level-badge level-${levelLower}">${level}</span>
        <span class="log-source-badge">${source}</span>
        <span class="log-message ${statusClass}">${Utils.escapeHtml(message)}</span>
        ${groupHtml}
        ${tracebackHtml}
      </div>
    `;
  },

  expandGroup(entryId) {
    const log = this.logs.find(l => l.id === entryId);
    if (!log || !log.group_entries) return;

    const el = document.querySelector(`.log-entry[data-id="${entryId}"]`);
    if (!el) return;

    if (el.classList.contains('group-expanded')) {
      el.classList.remove('group-expanded');
      el.querySelectorAll('.log-group-expanded-entry').forEach(e => e.remove());
      return;
    }

    el.classList.add('group-expanded');
    const entries = log.group_entries;
    let expandHtml = '';
    for (const e of entries) {
      const ts = e.timestamp ? Format.time(e.timestamp) : '';
      expandHtml += `<div class="log-group-expanded-entry">
        <span class="log-timestamp">${ts}</span>
        <span class="log-message">${Utils.escapeHtml(e.message || '')}</span>
      </div>`;
    }
    el.insertAdjacentHTML('beforeend', expandHtml);
  },

  // =========================================================================
  // Detail Panel (F6)
  // =========================================================================

  openDetail(el) {
    if (event.target.closest('.log-traceback-toggle, .log-group-count, .log-traceback')) return;

    let log;
    try {
      log = JSON.parse(atob(el.dataset.log));
    } catch { return; }

    const level = (log.level || 'INFO').toUpperCase();
    const levelLower = level.toLowerCase();
    const ts = log.timestamp ? new Date(log.timestamp).toLocaleString('en-GB') : '-';

    let metaHtml = '';
    if (log.metadata && Object.keys(log.metadata).length > 0) {
      metaHtml = `<table class="log-detail-meta">
        ${Object.entries(log.metadata).map(([k, v]) => {
          let valClass = '';
          if (k === 'status') {
            if (v >= 200 && v < 300) valClass = 'http-2xx';
            else if (v >= 400 && v < 500) valClass = 'http-4xx';
            else if (v >= 500) valClass = 'http-5xx';
          }
          return `<tr><td class="log-detail-meta-key">${Utils.escapeHtml(k)}</td>
                      <td class="${valClass}">${Utils.escapeHtml(String(v))}</td></tr>`;
        }).join('')}
      </table>`;
    }

    let tracebackHtml = '';
    if (log.extra_lines && log.extra_lines.length) {
      tracebackHtml = `
        <div class="log-detail-section">
          <div class="log-detail-section-title">Traceback (${log.traceback_frames || 0} frames)</div>
          <pre class="log-traceback expanded">${log.extra_lines.map(l => {
            return Utils.escapeHtml(l).replace(
              /File &quot;([^&]+)&quot;, line (\d+)/g,
              '<span class="tb-file">File "$1", line $2</span>'
            );
          }).join('\n')}</pre>
        </div>
      `;
    }

    const content = `
      <div class="log-detail-header">
        <span class="log-level-badge level-${levelLower}">${level}</span>
        <span class="log-detail-timestamp">${ts}</span>
        <span class="log-source-badge">${log.source || 'unknown'}</span>
      </div>
      <div class="log-detail-section">
        <div class="log-detail-section-title">Message</div>
        <pre class="log-detail-message">${Utils.escapeHtml(log.message || '')}</pre>
      </div>
      ${metaHtml ? `<div class="log-detail-section"><div class="log-detail-section-title">Metadata</div>${metaHtml}</div>` : ''}
      ${tracebackHtml}
      ${log.noise ? '<div class="log-detail-noise-flag">This entry matches a noise pattern</div>' : ''}
      <div class="log-detail-section">
        <button class="btn btn-sm btn-secondary" onclick="LogsView.loadContext('${log.source}', '${log.timestamp}')">
          Show surrounding logs
        </button>
      </div>
      <div id="log-detail-context"></div>
    `;

    DetailPanel.open(content);
  },

  async loadContext(source, timestamp) {
    try {
      const data = await API.get(`/api/logs/context?source=${encodeURIComponent(source)}&timestamp=${encodeURIComponent(timestamp)}&lines=5`);
      const contextEl = document.getElementById('log-detail-context');
      if (!contextEl) return;

      const renderCtx = (entries) => {
        if (!entries || !entries.length) return '';
        return entries.map(e => {
          const ts = e.timestamp ? Format.time(e.timestamp) : '';
          const lvl = (e.level || 'INFO').toLowerCase();
          return `<div class="log-entry level-${lvl}" style="font-size:11px; padding:2px 8px;">
            <span class="log-timestamp">${ts}</span>
            <span class="log-level-badge level-${lvl}" style="font-size:9px">${(e.level || 'INFO').toUpperCase()}</span>
            <span class="log-message">${Utils.escapeHtml(e.message || '')}</span>
          </div>`;
        }).join('');
      };

      contextEl.innerHTML = `
        <div class="log-detail-section">
          <div class="log-detail-section-title">Surrounding Logs</div>
          <div class="log-detail-context-list">
            ${renderCtx(data.before)}
            <div class="log-detail-context-target">--- target entry ---</div>
            ${renderCtx(data.after)}
          </div>
        </div>
      `;
    } catch (error) {
      console.error('Failed to load context:', error);
    }
  },

  // =========================================================================
  // Live Tail (F5)
  // =========================================================================

  toggleLiveTail() {
    this.liveTail = !this.liveTail;
    const btn = document.getElementById('logs-live-btn');
    const dot = document.getElementById('logs-live-dot');
    if (btn) btn.className = `btn btn-sm ${this.liveTail ? 'btn-accent' : 'btn-secondary'}`;
    if (dot) dot.className = `live-indicator ${this.liveTail ? 'active' : ''}`;

    if (this.liveTail) {
      this._startLiveTail();
    } else {
      this._stopLiveTail();
    }
    this.updateCountBar(this.logs.length);
  },

  _startLiveTail() {
    this._stopLiveTail();
    this._liveTailInterval = setInterval(() => this._pollNewLogs(), 2000);
  },

  _stopLiveTail() {
    if (this._liveTailInterval) {
      clearInterval(this._liveTailInterval);
      this._liveTailInterval = null;
    }
  },

  async _pollNewLogs() {
    if (!this.liveTail) return;
    if (document.hidden) return;

    try {
      const params = this._buildParams();
      if (this._lastTimestamp) {
        params.set('since', this._lastTimestamp);
      }
      params.set('limit', '50');

      const data = await API.get(`/api/logs/unified?${params.toString()}`);
      const newLogs = data.logs || [];

      if (newLogs.length > 0) {
        this._lastTimestamp = newLogs[0].timestamp;
        this.allLogs = [...newLogs, ...this.allLogs].slice(0, 500);
        this.logs = this.allLogs;
        this.renderLogs(this.logs);
        this.updateCountBar(this.logs.length);

        // Flash new entries
        const container = document.getElementById('logs-container');
        if (container) {
          const entries = container.querySelectorAll('.log-entry');
          for (let i = 0; i < Math.min(newLogs.length, entries.length); i++) {
            entries[i].classList.add('log-entry-flash');
          }
        }

        if (!this._userScrolledUp && container) {
          container.scrollTop = 0;
        }
      }
    } catch (error) {
      console.error('Live tail poll failed:', error);
    }
  },

  jumpToLive() {
    const container = document.getElementById('logs-container');
    if (container) {
      container.scrollTop = 0;
      this._userScrolledUp = false;
    }
    const pill = document.getElementById('logs-jump-pill');
    if (pill) pill.style.display = 'none';
  },

  // =========================================================================
  // Toggle buttons
  // =========================================================================

  toggleGroup() {
    this.groupEnabled = !this.groupEnabled;
    localStorage.setItem('peter_logs_group', this.groupEnabled);
    const btn = document.getElementById('logs-group-btn');
    if (btn) btn.className = `btn btn-sm ${this.groupEnabled ? 'btn-primary' : 'btn-secondary'}`;
    this.loadData();
  },

  toggleNoise() {
    this.hideNoise = !this.hideNoise;
    localStorage.setItem('peter_logs_hide_noise', this.hideNoise);
    this._updateNoiseBtn();
    this.renderLogs(this.logs);
    this.updateCountBar(this.logs.length);
  },

  _updateNoiseBtn() {
    const btn = document.getElementById('logs-noise-btn');
    if (btn) btn.className = `btn btn-sm ${this.hideNoise ? 'btn-primary' : 'btn-secondary'}`;
  },

  async refresh() {
    const container = document.getElementById('logs-container');
    if (container) container.innerHTML = Components.skeleton('text', 10);
    await Promise.all([this.loadData(), this.loadHistogram(), this.loadFacets()]);
    Toast.info('Refreshed', 'Logs updated');
  },

  // Cleanup on view change
  destroy() {
    this._stopLiveTail();
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
 * Knowledge View — Unified Second Brain browse + Mind Map visualizations
 */
const KnowledgeView = {
  title: 'Knowledge',

  // Second Brain browse state
  brainOffset: 0,
  brainLimit: 30,
  brainTotal: 0,
  brainContentType: '',
  brainTopic: '',
  brainSearchMode: false,
  _activeTab: 0,
  _searchTimeout: null,

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="kb-header-row">
          <div>
            <h2>Knowledge</h2>
            <p class="text-secondary">Browse, search, and visualize your knowledge base</p>
          </div>
          <div class="kb-header-controls">
            <div class="mm-source-toggle" id="kb-source-toggle">
              <button class="mm-source-btn active" data-source="both">Both</button>
              <button class="mm-source-btn" data-source="brain">Second Brain</button>
              <button class="mm-source-btn" data-source="memory">Memories</button>
            </div>
            <button class="btn btn-secondary" onclick="KnowledgeView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
        </div>

        <div class="kb-search-row">
          <div class="data-table-search">
            <span class="data-table-search-icon">${Icons.search}</span>
            <input type="text" placeholder="Search knowledge..."
                   id="kb-search" onkeyup="if(event.key==='Enter')KnowledgeView.handleSearch(this.value)">
          </div>
        </div>

        <div class="mind-map-stats" id="mm-stats"></div>

        <div class="kb-tabs">
          ${Components.tabs({
            id: 'kb-tabs',
            tabs: [
              { label: 'Browse', badge: '', content: this.renderBrowseTab() },
              { label: 'Knowledge Graph', content: '<div id="mm-graph" class="mm-graph-container"><div class="mm-loading">Loading graph...</div></div>' },
              { label: 'Radar', content: '<div id="mm-radar" class="mm-chart-container"><div class="mm-loading">Loading radar...</div></div>' },
              { label: 'Timeline', content: '<div id="mm-activity" class="mm-chart-container"><div class="mm-loading">Loading activity...</div></div>' },
              { label: 'Decay', content: '<div id="mm-decay" class="mm-chart-container"><div class="mm-loading">Loading decay data...</div></div>' },
              { label: 'Health', content: '<div id="mm-health" class="mm-health-container"><div class="mm-loading">Loading health data...</div></div>' },
            ]
          })}
        </div>

        <div id="mm-detail-panel" class="mm-detail-panel" style="display:none"></div>
      </div>
    `;

    this._wireTabSwitching();
    this._wireSourceToggle();
    await this.loadData();
  },

  renderBrowseTab() {
    return `
      <div class="kb-filter-row">
        <div class="data-table-search" style="max-width: 300px; flex: 1;">
          <span class="data-table-search-icon">${Icons.search}</span>
          <input type="text" placeholder="Semantic search..."
                 id="brain-search" onkeyup="if(event.key==='Enter')KnowledgeView.searchBrain(this.value)">
        </div>
        <select id="brain-filter-type" onchange="KnowledgeView.filterBrain()" class="kb-filter-select">
          <option value="">All types</option>
          <option value="article">Article</option>
          <option value="recipe">Recipe</option>
          <option value="reference">Reference</option>
          <option value="conversation">Conversation</option>
          <option value="note">Note</option>
          <option value="tutorial">Tutorial</option>
          <option value="news">News</option>
        </select>
        <select id="brain-filter-topic" onchange="KnowledgeView.filterBrain()" class="kb-filter-select">
          <option value="">All topics</option>
        </select>
      </div>
      <div id="brain-results">
        <div class="flex justify-center py-lg"><div class="spinner"></div></div>
      </div>
      <div id="brain-pagination" style="display: flex; justify-content: center; gap: 12px; padding: 16px 0;"></div>
    `;
  },

  _wireTabSwitching() {
    const origSwitch = Tabs.switch.bind(Tabs);
    document.querySelectorAll('#kb-tabs .tab').forEach((btn, idx) => {
      btn.onclick = () => {
        origSwitch('kb-tabs', idx);
        this._activeTab = idx;
        if (idx > 0 && typeof MindMapView !== 'undefined') {
          MindMapView.setActiveTab(idx - 1);
        }
      };
    });
  },

  _wireSourceToggle() {
    document.querySelectorAll('#kb-source-toggle .mm-source-btn').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('#kb-source-toggle .mm-source-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (typeof MindMapView !== 'undefined') {
          MindMapView.setSource(btn.dataset.source);
        }
      };
    });
  },

  handleSearch(query) {
    if (this._activeTab === 0) {
      this.searchBrain(query);
    } else if (typeof MindMapView !== 'undefined') {
      MindMapView._handleSearch(query);
    }
  },

  async loadData() {
    this.loadBrainItems();
    this.loadBrainTopics();
    if (typeof MindMapView !== 'undefined') {
      MindMapView.init();
    }
  },

  updateBadge(tabIndex, count) {
    const tabs = document.querySelectorAll('#kb-tabs .tab');
    if (tabs[tabIndex]) {
      const badge = tabs[tabIndex].querySelector('.tab-badge');
      if (badge) { badge.textContent = count; }
      else { tabs[tabIndex].insertAdjacentHTML('beforeend', `<span class="tab-badge">${count}</span>`); }
    }
  },

  // --- Second Brain browse/search (preserved from MemoryView) ---

  async searchBrain(query) {
    if (!query.trim()) {
      this.brainSearchMode = false;
      this.brainOffset = 0;
      this.loadBrainItems();
      return;
    }
    this.brainSearchMode = true;
    const container = document.getElementById('brain-results');
    const pagination = document.getElementById('brain-pagination');
    container.innerHTML = '<div class="flex justify-center py-lg"><div class="spinner"></div></div>';
    if (pagination) pagination.innerHTML = '';
    try {
      const results = await API.get(`/api/search/second-brain?query=${encodeURIComponent(query)}&limit=20`);
      if (!results.success || !results.items || !results.items.length) {
        container.innerHTML = '<p class="text-muted">No results found</p>';
        return;
      }
      container.innerHTML = `
        <div style="margin-bottom: 8px;">
          <a href="#" onclick="event.preventDefault(); document.getElementById('brain-search').value=''; KnowledgeView.searchBrain('');" style="font-size: 13px; color: var(--primary);">&larr; Back to browse</a>
          <span class="text-muted text-sm" style="margin-left: 8px;">${results.items.length} semantic match${results.items.length !== 1 ? 'es' : ''}</span>
        </div>
        ${results.items.map(item => this._renderBrainCard(item, true)).join('')}
      `;
    } catch (error) { Toast.error('Error', `Search failed: ${error.message}`); }
  },

  async loadBrainItems() {
    const container = document.getElementById('brain-results');
    if (!container) return;
    try {
      let url = `/api/search/second-brain/list?limit=${this.brainLimit}&offset=${this.brainOffset}`;
      if (this.brainContentType) url += `&content_type=${encodeURIComponent(this.brainContentType)}`;
      if (this.brainTopic) url += `&topic=${encodeURIComponent(this.brainTopic)}`;
      const data = await API.get(url);
      if (!data.success) throw new Error(data.error || 'Unknown error');
      this.brainTotal = data.total || 0;
      this.updateBadge(0, this.brainTotal);
      this.renderBrainItems(data.items || []);
      this.renderBrainPagination();
    } catch (error) {
      console.error('Error loading brain items:', error);
      container.innerHTML = `<p class="text-error">Failed to load: ${error.message}</p>`;
    }
  },

  async loadBrainTopics() {
    try {
      const data = await API.get('/api/search/second-brain/stats');
      if (!data.success || !data.topics) return;
      const select = document.getElementById('brain-filter-topic');
      if (!select) return;
      const current = select.value;
      select.innerHTML = '<option value="">All topics</option>' +
        data.topics.map(t => `<option value="${Utils.escapeHtml(t.topic)}"${t.topic === current ? ' selected' : ''}>${Utils.escapeHtml(t.topic)} (${t.count})</option>`).join('');
    } catch (e) { console.error('Failed to load brain topics:', e); }
  },

  filterBrain() {
    this.brainContentType = document.getElementById('brain-filter-type')?.value || '';
    this.brainTopic = document.getElementById('brain-filter-topic')?.value || '';
    this.brainOffset = 0;
    this.brainSearchMode = false;
    this.loadBrainItems();
  },

  renderBrainItems(items) {
    const container = document.getElementById('brain-results');
    if (!container) return;
    if (!items.length) { container.innerHTML = '<p class="text-muted">No items found</p>'; return; }
    container.innerHTML = items.map(item => this._renderBrainCard(item, false)).join('');
  },

  _renderBrainCard(item, isSearch) {
    const typeColors = { article: '#3b82f6', recipe: '#f59e0b', reference: '#8b5cf6', conversation: '#10b981', note: '#6b7280', tutorial: '#ec4899', news: '#ef4444' };
    const typeBg = typeColors[item.content_type] || '#6b7280';
    const similarity = isSearch && item.similarity ? `<span style="font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">${(item.similarity * 100).toFixed(0)}% match</span>` : '';
    const captureLabel = item.capture_type ? `<span style="font-size: 10px; color: var(--text-muted);">${item.capture_type}</span>` : '';
    const topics = (item.topics || []).slice(0, 4).map(t =>
      `<span style="display: inline-block; font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 1px 6px; border-radius: 10px;">${Utils.escapeHtml(t)}</span>`
    ).join(' ');

    return `
      <div style="background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            ${item.content_type ? `<span style="font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; background: ${typeBg}; color: white; text-transform: uppercase;">${item.content_type}</span>` : ''}
            ${captureLabel}
            ${similarity}
          </div>
          <span style="font-size: 12px; color: var(--text-muted); white-space: nowrap;">${Format.datetime(item.created_at)}</span>
        </div>
        <div style="font-weight: 500; margin-bottom: 4px;">${Utils.escapeHtml(item.title || 'Untitled')}</div>
        ${item.summary ? `<div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${Utils.escapeHtml(item.summary)}</div>` : ''}
        ${isSearch && item.excerpts && item.excerpts.length ? `<div style="font-size: 12px; color: var(--text-muted); border-left: 2px solid var(--border); padding-left: 8px; margin-bottom: 6px;">${Utils.escapeHtml(item.excerpts[0])}</div>` : ''}
        ${topics ? `<div style="display: flex; gap: 4px; flex-wrap: wrap;">${topics}</div>` : ''}
      </div>
    `;
  },

  renderBrainPagination() {
    const container = document.getElementById('brain-pagination');
    if (!container) return;
    if (this.brainSearchMode || this.brainTotal <= this.brainLimit) { container.innerHTML = ''; return; }
    const page = Math.floor(this.brainOffset / this.brainLimit) + 1;
    const totalPages = Math.ceil(this.brainTotal / this.brainLimit);
    container.innerHTML = `
      <button class="btn btn-secondary btn-sm" onclick="KnowledgeView.brainPage(-1)" ${page <= 1 ? 'disabled' : ''} style="padding: 4px 12px; font-size: 13px;">&larr; Prev</button>
      <span class="text-sm text-muted" style="line-height: 32px;">Page ${page} of ${totalPages} (${this.brainTotal} items)</span>
      <button class="btn btn-secondary btn-sm" onclick="KnowledgeView.brainPage(1)" ${page >= totalPages ? 'disabled' : ''} style="padding: 4px 12px; font-size: 13px;">Next &rarr;</button>
    `;
  },

  brainPage(direction) {
    this.brainOffset = Math.max(0, this.brainOffset + direction * this.brainLimit);
    this.loadBrainItems();
  },

  async refresh() {
    Toast.info('Refreshing', 'Loading knowledge...');
    if (typeof MindMapView !== 'undefined') {
      MindMapView.refresh();
    }
    this.brainOffset = 0;
    this.brainSearchMode = false;
    await Promise.all([this.loadBrainItems(), this.loadBrainTopics()]);
    Toast.success('Done', 'Knowledge refreshed');
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
      second_brain: 'Second Brain',
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
  _showAllSkills: false,
  _filterSkill: '',
  _filterChannel: '',
  _filterModel: '',
  _searchText: '',

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

        <div class="card mb-lg" id="costs-trend-card">
          <div class="card-header">
            <h3 class="card-title">Cost Trend</h3>
          </div>
          <div class="cost-trend-chart" id="costs-trend-chart">
            ${Components.skeleton('text', 4)}
          </div>
        </div>

        <div class="grid grid-cols-2 gap-md mb-lg">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Cost by Skill</h3>
            </div>
            <div class="card-body" id="costs-by-skill" style="padding: 0;">
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
            <span class="text-sm text-muted" id="costs-log-count"></span>
          </div>
          <div class="costs-filter-bar" id="costs-filter-bar">
            <div class="costs-search-container">
              <span class="data-table-search-icon">${Icons.search}</span>
              <input type="text" class="costs-search-input" placeholder="Search skills, channels..."
                     id="costs-search-input" oninput="CostsView.onSearchInput(this.value)">
            </div>
            <select class="form-input" style="width: auto; height: 32px; font-size: var(--text-sm); padding: 4px 8px;" id="costs-filter-skill">
              <option value="">All Skills</option>
            </select>
            <select class="form-input" style="width: auto; height: 32px; font-size: var(--text-sm); padding: 4px 8px;" id="costs-filter-model">
              <option value="">All Models</option>
            </select>
          </div>
          <div id="costs-table" style="max-height: 600px; overflow-y: auto;">
            ${Components.skeleton('table', 10)}
          </div>
        </div>
      </div>
    `;

    document.getElementById('costs-days-filter').addEventListener('change', (e) => {
      this._days = parseInt(e.target.value);
      this.refresh();
    });

    document.getElementById('costs-filter-skill').addEventListener('change', (e) => {
      this._filterSkill = e.target.value;
      this.renderTable(this._data?.entries || []);
    });

    document.getElementById('costs-filter-model').addEventListener('change', (e) => {
      this._filterModel = e.target.value;
      this.renderTable(this._data?.entries || []);
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
      this.renderTrendChart(data.summary.by_day || {});
      this.renderBySkill(data.summary.by_skill || []);
      this.renderByModel(data.summary.by_model || {});
      this.populateFilters(data);
      this.renderTable(data.entries || []);
    } catch (error) {
      console.error('Failed to load cost data:', error);
      Toast.error('Error', 'Failed to load cost data');
    }
  },

  _resolveChannel(raw) {
    if (!raw) return '-';
    const idMatch = raw.match(/(\d{17,20})/);
    if (idMatch && this._channelMap && this._channelMap[idMatch[1]]) {
      return this._channelMap[idMatch[1]];
    }
    return raw.replace('Channel ', '#').replace(/^#peter-/, '').replace(/^#/, '');
  },

  _extractSkill(source) {
    if (!source) return '-';
    return source.startsWith('scheduled:') ? source.replace('scheduled:', '') : source;
  },

  _costSeverity(gbp) {
    if (gbp > 0.20) return 'high';
    if (gbp >= 0.05) return 'medium';
    return 'low';
  },

  renderStats(summary) {
    const el = document.getElementById('costs-stats');
    if (!el) return;

    const pace = summary.daily_budget_pace || {};
    const pct = summary.percentiles || {};
    const src = summary.by_source_type || {};
    const numDays = Object.keys(summary.by_day || {}).length || 1;
    const dailyAvg = (summary.total_gbp || 0) / numDays;

    const paceColor = pace.projected_daily_gbp > dailyAvg ? 'error' : 'success';
    const paceValue = pace.today_gbp !== undefined ? '\u00A3' + pace.today_gbp.toFixed(2) : '-';
    const paceSubtitle = pace.projected_daily_gbp !== undefined
      ? `Pace: \u00A3${pace.projected_daily_gbp.toFixed(2)}/day`
      : '';

    el.innerHTML = `
      <div class="stats-card">
        <div class="stats-card-icon info">${Icons.activity}</div>
        <div class="stats-card-content">
          <div class="stats-card-value">\u00A3${(summary.total_gbp || 0).toFixed(2)}</div>
          <div class="stats-card-label">Total Cost (GBP)</div>
          <div class="stats-card-subtitle">Avg \u00A3${dailyAvg.toFixed(2)}/day</div>
        </div>
      </div>
      <div class="stats-card">
        <div class="stats-card-icon success">${Icons.checkCircle}</div>
        <div class="stats-card-content">
          <div class="stats-card-value">${summary.total_calls || 0}</div>
          <div class="stats-card-label">Total Calls</div>
          <div class="stats-card-subtitle">${src.scheduled?.calls || 0} sched / ${src.conversation?.calls || 0} conv</div>
        </div>
      </div>
      <div class="stats-card">
        <div class="stats-card-icon info">${Icons.clock}</div>
        <div class="stats-card-content">
          <div class="stats-card-value">${summary.avg_duration_ms ? (summary.avg_duration_ms / 1000).toFixed(1) + 's' : '-'}</div>
          <div class="stats-card-label">Avg Duration</div>
          <div class="stats-card-subtitle">p90: ${pct.p90_duration_ms ? (pct.p90_duration_ms / 1000).toFixed(1) + 's' : '-'}</div>
        </div>
      </div>
      <div class="stats-card">
        <div class="stats-card-icon ${paceColor}">${Icons.zap}</div>
        <div class="stats-card-content">
          <div class="stats-card-value">${paceValue}</div>
          <div class="stats-card-label">Today's Spend</div>
          <div class="stats-card-subtitle" style="color: var(--status-${paceColor === 'error' ? 'error' : 'running'});">${paceSubtitle}</div>
        </div>
      </div>
    `;
  },

  renderTrendChart(byDay) {
    const el = document.getElementById('costs-trend-chart');
    if (!el) return;

    const days = Object.entries(byDay);
    if (days.length < 2) {
      el.innerHTML = '<p class="text-muted text-center p-md">Not enough data for chart</p>';
      return;
    }

    el.innerHTML = '';

    const margin = { top: 12, right: 20, bottom: 30, left: 50 };
    const width = el.clientWidth - margin.left - margin.right;
    const height = 180 - margin.top - margin.bottom;

    const svg = d3.select(el)
      .append('svg')
      .attr('width', width + margin.left + margin.right)
      .attr('height', height + margin.top + margin.bottom)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    const data = days.map(([day, d]) => ({
      date: new Date(day + 'T00:00:00'),
      scheduled: d.scheduled_gbp || 0,
      conversation: d.conversation_gbp || 0,
      total: d.cost_gbp || 0
    }));

    const x = d3.scaleTime()
      .domain(d3.extent(data, d => d.date))
      .range([0, width]);

    const maxY = d3.max(data, d => d.total) || 1;
    const y = d3.scaleLinear()
      .domain([0, maxY * 1.1])
      .range([height, 0]);

    // Grid lines
    svg.append('g')
      .attr('class', 'grid')
      .call(d3.axisLeft(y).ticks(4).tickSize(-width).tickFormat(''));

    // Stacked areas
    const stack = d3.stack()
      .keys(['scheduled', 'conversation'])
      .order(d3.stackOrderNone)
      .offset(d3.stackOffsetNone);

    const series = stack(data);

    const area = d3.area()
      .x(d => x(d.data.date))
      .y0(d => y(d[0]))
      .y1(d => y(d[1]))
      .curve(d3.curveMonotoneX);

    const colors = ['#0d9488', '#3b82f6']; // teal for scheduled, blue for conversation

    svg.selectAll('.area')
      .data(series)
      .join('path')
      .attr('class', 'area')
      .attr('d', area)
      .attr('fill', (d, i) => colors[i])
      .attr('fill-opacity', 0.3)
      .attr('stroke', (d, i) => colors[i])
      .attr('stroke-width', 1.5);

    // X axis
    const tickCount = data.length > 14 ? 7 : data.length;
    svg.append('g')
      .attr('class', 'axis')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x).ticks(tickCount).tickFormat(d3.timeFormat('%-d %b')));

    // Y axis
    svg.append('g')
      .attr('class', 'axis')
      .call(d3.axisLeft(y).ticks(4).tickFormat(d => '\u00A3' + d.toFixed(2)));

    // Tooltip hover
    const tooltip = d3.select(el)
      .append('div')
      .attr('class', 'cost-trend-tooltip')
      .style('opacity', 0);

    const bisect = d3.bisector(d => d.date).left;

    const hoverRect = svg.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', 'none')
      .attr('pointer-events', 'all');

    const hoverLine = svg.append('line')
      .attr('stroke', 'var(--text-muted)')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '4,4')
      .style('opacity', 0);

    hoverRect.on('mousemove', function(event) {
      const [mx] = d3.pointer(event);
      const x0 = x.invert(mx);
      const i = Math.min(bisect(data, x0, 1), data.length - 1);
      const d = data[i];
      if (!d) return;

      hoverLine
        .attr('x1', x(d.date)).attr('x2', x(d.date))
        .attr('y1', 0).attr('y2', height)
        .style('opacity', 1);

      tooltip
        .style('opacity', 1)
        .html(`<strong>${d3.timeFormat('%-d %b')(d.date)}</strong><br>
               Scheduled: \u00A3${d.scheduled.toFixed(3)}<br>
               Conversation: \u00A3${d.conversation.toFixed(3)}<br>
               Total: \u00A3${d.total.toFixed(3)}`)
        .style('left', (x(d.date) + margin.left + 10) + 'px')
        .style('top', '10px');
    }).on('mouseleave', function() {
      hoverLine.style('opacity', 0);
      tooltip.style('opacity', 0);
    });

    // Legend
    const legend = d3.select(el)
      .append('div')
      .style('display', 'flex')
      .style('gap', '16px')
      .style('justify-content', 'center')
      .style('margin-top', '4px');

    [{ label: 'Scheduled', color: colors[0] }, { label: 'Conversation', color: colors[1] }].forEach(item => {
      legend.append('span')
        .style('font-size', '11px')
        .style('color', 'var(--text-secondary)')
        .style('display', 'flex')
        .style('align-items', 'center')
        .style('gap', '4px')
        .html(`<span style="width:12px;height:3px;background:${item.color};border-radius:2px;display:inline-block;"></span>${item.label}`);
    });
  },

  renderBySkill(bySkill) {
    const el = document.getElementById('costs-by-skill');
    if (!el) return;

    if (!bySkill || bySkill.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No data</p>';
      return;
    }

    const maxCost = bySkill[0]?.cost_gbp || 1;
    const displayLimit = this._showAllSkills ? bySkill.length : 10;
    const displayed = bySkill.slice(0, displayLimit);

    const rows = displayed.map(s => {
      const barWidth = Math.max(2, (s.cost_gbp / maxCost) * 60);
      const severity = this._costSeverity(s.avg_cost_gbp);
      const barClass = severity === 'high' ? 'high' : severity === 'medium' ? 'medium' : '';
      return `
        <tr>
          <td>
            <span class="cost-bar ${barClass}" style="width: ${barWidth}px;"></span>
            <span class="font-medium text-sm">${Utils.escapeHtml(s.name)}</span>
          </td>
          <td class="text-right text-sm">${s.calls}</td>
          <td class="text-right font-mono text-sm">\u00A3${s.avg_cost_gbp.toFixed(3)}</td>
          <td class="text-right font-mono text-sm font-semibold">\u00A3${s.cost_gbp.toFixed(2)}</td>
        </tr>
      `;
    }).join('');

    let showAllHtml = '';
    if (bySkill.length > 10) {
      const label = this._showAllSkills ? 'Show top 10' : `Show all ${bySkill.length}`;
      showAllHtml = `<div class="costs-show-all"><button onclick="CostsView.toggleShowAllSkills()">${label}</button></div>`;
    }

    el.innerHTML = `
      <div style="padding: var(--spacing-lg);">
        <table class="table">
          <thead>
            <tr>
              <th>Skill</th>
              <th class="text-right">Calls</th>
              <th class="text-right">Avg Cost</th>
              <th class="text-right">Total GBP</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${showAllHtml}
    `;
  },

  toggleShowAllSkills() {
    this._showAllSkills = !this._showAllSkills;
    if (this._data) {
      this.renderBySkill(this._data.summary.by_skill || []);
    }
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

  populateFilters(data) {
    // Populate skill filter
    const skillSelect = document.getElementById('costs-filter-skill');
    if (skillSelect && data.summary.by_skill) {
      const skills = data.summary.by_skill.map(s => s.name).sort();
      skillSelect.innerHTML = '<option value="">All Skills</option>' +
        skills.map(s => `<option value="${Utils.escapeHtml(s)}">${Utils.escapeHtml(s)}</option>`).join('');
    }

    // Populate model filter
    const modelSelect = document.getElementById('costs-filter-model');
    if (modelSelect && data.summary.by_model) {
      const models = Object.keys(data.summary.by_model).sort();
      modelSelect.innerHTML = '<option value="">All Models</option>' +
        models.map(m => {
          const short = m.replace('claude-', '').replace(/-\d{8}$/, '');
          return `<option value="${Utils.escapeHtml(m)}">${Utils.escapeHtml(short)}</option>`;
        }).join('');
    }
  },

  onSearchInput(value) {
    this._searchText = value.toLowerCase();
    this.renderTable(this._data?.entries || []);
  },

  _getFilteredEntries(entries) {
    return entries.filter(e => {
      if (this._filterSkill) {
        const skill = this._extractSkill(e.source);
        if (skill !== this._filterSkill) return false;
      }
      if (this._filterModel && e.model !== this._filterModel) return false;
      if (this._searchText) {
        const searchable = [
          this._extractSkill(e.source),
          this._resolveChannel(e.channel),
          e.model || '',
          e.message || '',
          ...(e.tools_used || [])
        ].join(' ').toLowerCase();
        if (!searchable.includes(this._searchText)) return false;
      }
      return true;
    });
  },

  renderTable(entries) {
    const el = document.getElementById('costs-table');
    if (!el) return;

    const filtered = this._getFilteredEntries(entries);
    const countEl = document.getElementById('costs-log-count');
    if (countEl) {
      countEl.textContent = filtered.length === entries.length
        ? `${entries.length} calls`
        : `${filtered.length} of ${entries.length} calls`;
    }

    if (filtered.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No cost data recorded yet</p>';
      return;
    }

    const rows = filtered.map((e, idx) => {
      const time = Format.datetime(e.timestamp);
      const skill = this._extractSkill(e.source);
      const isScheduled = (e.source || '').startsWith('scheduled');
      const channel = this._resolveChannel(e.channel);
      const model = (e.model || 'unknown').replace('claude-', '').replace(/-\d{8,}$/, '');
      const duration = e.duration_ms ? (e.duration_ms / 1000).toFixed(1) + 's' : '-';
      const tools = [...new Set(e.tools_used || [])];
      const toolStr = tools.length > 0
        ? tools.slice(0, 3).join(', ') + (tools.length > 3 ? ` +${tools.length - 3}` : '')
        : '-';
      const costGbp = e.cost_gbp || 0;
      const severity = this._costSeverity(costGbp);

      return `
        <div class="cost-entry cost-${severity}" onclick="CostsView.openDetail(${idx})" data-idx="${idx}">
          <span class="cost-entry-time">${time}</span>
          <span class="cost-entry-skill">${isScheduled ? '<span class="status status-pending" style="font-size:10px;padding:1px 5px;">sched</span> ' : ''}${Utils.escapeHtml(skill)}</span>
          <span class="cost-entry-channel">${Utils.escapeHtml(channel)}</span>
          <span class="cost-entry-model">${Utils.escapeHtml(model)}</span>
          <span class="cost-entry-cost">\u00A3${costGbp.toFixed(3)}</span>
          <span class="cost-entry-duration">${duration}</span>
          <span class="cost-entry-tools">${Utils.escapeHtml(toolStr)}</span>
        </div>
      `;
    }).join('');

    el.innerHTML = rows;
  },

  openDetail(idx) {
    const entries = this._getFilteredEntries(this._data?.entries || []);
    const e = entries[idx];
    if (!e) return;

    const skill = this._extractSkill(e.source);
    const channel = this._resolveChannel(e.channel);
    const model = (e.model || 'unknown').replace('claude-', '').replace(/-\d{8,}$/, '');
    const tools = [...new Set(e.tools_used || [])];
    const severity = this._costSeverity(e.cost_gbp || 0);
    const severityLabel = severity === 'high' ? 'High Cost' : severity === 'medium' ? 'Medium Cost' : 'Low Cost';
    const severityColor = severity === 'high' ? 'var(--status-error)' : severity === 'medium' ? 'var(--status-paused)' : 'var(--status-running)';

    const content = `
      <div style="margin-bottom: var(--spacing-md);">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
          <span style="font-size: var(--text-lg); font-weight: var(--font-semibold);">${Utils.escapeHtml(skill)}</span>
          <span class="status-badge" style="background: ${severity === 'high' ? 'var(--status-error-bg)' : severity === 'medium' ? 'var(--status-paused-bg)' : 'var(--status-running-bg)'}; color: ${severityColor}; font-size: 10px; padding: 2px 8px; border-radius: 999px;">${severityLabel}</span>
        </div>
        <div style="font-size: var(--text-xs); color: var(--text-muted);">${Format.datetime(e.timestamp)}</div>
      </div>

      <div class="cost-detail-grid">
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Cost (GBP)</div>
          <div class="cost-detail-item-value">\u00A3${(e.cost_gbp || 0).toFixed(4)}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Cost (USD)</div>
          <div class="cost-detail-item-value">$${(e.cost_usd || 0).toFixed(4)}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Duration</div>
          <div class="cost-detail-item-value">${e.duration_ms ? (e.duration_ms / 1000).toFixed(1) + 's' : '-'}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Turns</div>
          <div class="cost-detail-item-value">${e.num_turns || '-'}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Model</div>
          <div class="cost-detail-item-value">${Utils.escapeHtml(model)}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Channel</div>
          <div class="cost-detail-item-value">${Utils.escapeHtml(channel)}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Source</div>
          <div class="cost-detail-item-value">${Utils.escapeHtml(e.source || '-')}</div>
        </div>
        <div class="cost-detail-item">
          <div class="cost-detail-item-label">Response Chars</div>
          <div class="cost-detail-item-value">${e.response_chars != null ? e.response_chars.toLocaleString() : '-'}</div>
        </div>
      </div>

      ${tools.length > 0 ? `
        <div style="margin-bottom: var(--spacing-sm);">
          <div style="font-size: var(--text-xs); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Tools Used</div>
          <div class="cost-detail-tools">
            ${tools.map(t => `<span class="cost-detail-tool-chip">${Utils.escapeHtml(t)}</span>`).join('')}
          </div>
        </div>
      ` : ''}

      ${e.message ? `
        <div>
          <div style="font-size: var(--text-xs); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Message</div>
          <div class="cost-detail-message">${Utils.escapeHtml(e.message)}</div>
        </div>
      ` : ''}
    `;

    DetailPanel.open(content);
  },
};


// =============================================================================
// TASKS VIEW — List + Kanban with Quick Actions
// =============================================================================

const TasksView = {
  title: 'Tasks',
  HADLEY_API: '/api/hadley/proxy',
  _tasks: [],
  _counts: {},
  _categories: [],
  _activeList: localStorage.getItem('tasks_activeList') || 'personal_todo',
  _viewMode: localStorage.getItem('tasks_viewMode') || 'list',
  _collapsedStatuses: new Set(JSON.parse(localStorage.getItem('tasks_collapsed') || '["done","cancelled"]')),
  _selectedIndex: -1,
  _dragTaskId: null,
  _quickMenuTaskId: null,

  LIST_TYPES: [
    { key: 'personal_todo', label: 'Todos', icon: Icons.checkCircle },
    { key: 'peter_queue', label: 'Peter Queue', icon: Icons.zap },
    { key: 'idea', label: 'Ideas', icon: Icons.star },
    { key: 'research', label: 'Research', icon: Icons.search },
  ],

  COLUMNS: {
    personal_todo: ['inbox', 'scheduled', 'in_progress', 'done'],
    peter_queue:   ['queued', 'heartbeat_scheduled', 'in_heartbeat', 'in_progress', 'review', 'done'],
    idea:          ['inbox', 'scheduled', 'review', 'done'],
    research:      ['queued', 'in_progress', 'findings_ready', 'done'],
  },

  COLUMN_CONFIG: {
    inbox:               { label: 'Inbox',          color: '#6B7280', accent: '#E5E7EB' },
    scheduled:           { label: 'Scheduled',      color: '#2563EB', accent: '#BFDBFE' },
    queued:              { label: 'Queued',          color: '#7C3AED', accent: '#DDD6FE' },
    heartbeat_scheduled: { label: 'HB Scheduled',   color: '#D97706', accent: '#FDE68A' },
    in_heartbeat:        { label: 'In Heartbeat',   color: '#EA580C', accent: '#FED7AA' },
    in_progress:         { label: 'In Progress',    color: '#059669', accent: '#A7F3D0' },
    review:              { label: 'Review',          color: '#7C3AED', accent: '#DDD6FE' },
    findings_ready:      { label: 'Findings Ready', color: '#059669', accent: '#A7F3D0' },
    done:                { label: 'Done',            color: '#16A34A', accent: '#BBF7D0' },
    cancelled:           { label: 'Cancelled',       color: '#9CA3AF', accent: '#E5E7EB' },
  },

  PRIORITY_CONFIG: {
    critical: { label: 'Critical', color: '#DC2626', bg: '#FEE2E2' },
    high:     { label: 'High',     color: '#EA580C', bg: '#FFF7ED' },
    medium:   { label: 'Medium',   color: '#2563EB', bg: '#EFF6FF' },
    low:      { label: 'Low',      color: '#6B7280', bg: '#F3F4F6' },
    someday:  { label: 'Someday',  color: '#9CA3AF', bg: '#F9FAFB' },
  },

  _persistState() {
    localStorage.setItem('tasks_activeList', this._activeList);
    localStorage.setItem('tasks_viewMode', this._viewMode);
    localStorage.setItem('tasks_collapsed', JSON.stringify([...this._collapsedStatuses]));
  },

  _hasOverdue(listKey) {
    // Check from loaded tasks only if this is the active list
    if (listKey !== this._activeList) return false;
    const now = new Date();
    return this._tasks.some(t =>
      t.due_date && t.status !== 'done' && t.status !== 'cancelled' && new Date(t.due_date) < now
    );
  },

  async render(container) {
    const listTabs = this.LIST_TYPES.map(lt => `
      <button class="kb-list-tab ${lt.key === this._activeList ? 'kb-list-tab-active' : ''}"
              onclick="TasksView.switchList('${lt.key}')"
              data-list="${lt.key}">
        ${lt.icon}
        <span class="kb-list-tab-label">${lt.label}</span>
        <span class="kb-tab-count" id="tab-count-${lt.key}"></span>
        <span class="kb-tab-overdue" id="tab-overdue-${lt.key}"></span>
      </button>
    `).join('');

    container.innerHTML = `
      <div class="animate-fade-in kb-page">
        <div class="kb-toolbar">
          <div class="kb-toolbar-left">
            <div class="kb-list-tabs">${listTabs}</div>
          </div>
          <div class="kb-toolbar-right">
            <div class="kb-search-wrap">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input type="text" id="kb-search" placeholder="Search..." onkeyup="TasksView.applyFilters()">
            </div>
            <select id="kb-filter-priority" class="kb-filter-select" onchange="TasksView.applyFilters()">
              <option value="">All Priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="someday">Someday</option>
            </select>
            <select id="kb-filter-category" class="kb-filter-select" onchange="TasksView.applyFilters()">
              <option value="">All Categories</option>
            </select>
            <div class="kb-view-toggle">
              <button class="kb-view-btn ${this._viewMode === 'list' ? 'kb-view-btn-active' : ''}"
                      onclick="TasksView.setViewMode('list')" title="List view">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
                  <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
                </svg>
              </button>
              <button class="kb-view-btn ${this._viewMode === 'kanban' ? 'kb-view-btn-active' : ''}"
                      onclick="TasksView.setViewMode('kanban')" title="Board view">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="3" width="5" height="18" rx="1"/><rect x="10" y="3" width="5" height="12" rx="1"/><rect x="17" y="3" width="5" height="15" rx="1"/>
                </svg>
              </button>
            </div>
            <button class="btn btn-primary btn-sm" onclick="TasksView.showCreateModal()">
              ${Icons.plus} New
            </button>
          </div>
        </div>

        <div id="kb-content" class="kb-content">
          ${Components.skeleton('table', 5)}
        </div>
      </div>
    `;
    this._bindKeyboard();
    await this.loadData();
  },

  async loadData(retries = 2) {
    try {
      const [countsResp, tasksResp, catsResp] = await Promise.all([
        fetch(`${this.HADLEY_API}/ptasks/counts`),
        fetch(`${this.HADLEY_API}/ptasks/list/${this._activeList}?include_done=true`),
        fetch(`${this.HADLEY_API}/ptasks/categories`),
      ]);

      if (!countsResp.ok || !tasksResp.ok) {
        if (retries > 0) {
          console.warn(`Tasks API returned ${countsResp.status}/${tasksResp.status}, retrying...`);
          await new Promise(r => setTimeout(r, 800));
          return this.loadData(retries - 1);
        }
        throw new Error(`API error: counts=${countsResp.status} tasks=${tasksResp.status}`);
      }

      this._counts = (await countsResp.json()).counts || {};
      this._tasks = (await tasksResp.json()).tasks || [];
      this._categories = catsResp.ok ? ((await catsResp.json()).categories || []) : this._categories;

      this._updateTabCounts();
      this._populateCategoryFilter();
      this._renderContent();
    } catch (error) {
      console.error('Failed to load tasks:', error);
      Toast.error('Error', 'Failed to load tasks');
    }
  },

  _updateTabCounts() {
    for (const lt of this.LIST_TYPES) {
      const el = document.getElementById(`tab-count-${lt.key}`);
      if (el) {
        const count = this._counts[lt.key] || 0;
        el.textContent = count > 0 ? count : '';
      }
      const od = document.getElementById(`tab-overdue-${lt.key}`);
      if (od) od.style.display = this._hasOverdue(lt.key) ? 'inline-block' : 'none';
    }
  },

  _populateCategoryFilter() {
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

  applyFilters() { this._renderContent(); },

  setViewMode(mode) {
    this._viewMode = mode;
    this._persistState();
    document.querySelectorAll('.kb-view-btn').forEach(btn => btn.classList.remove('kb-view-btn-active'));
    document.querySelector(`.kb-view-btn[title="${mode === 'list' ? 'List view' : 'Board view'}"]`)?.classList.add('kb-view-btn-active');
    this._renderContent();
  },

  _renderContent() {
    if (this._viewMode === 'kanban') {
      this._renderKanban();
    } else {
      this._renderList();
    }
  },

  // ===========================================================================
  // LIST VIEW
  // ===========================================================================
  _renderList() {
    const content = document.getElementById('kb-content');
    if (!content) return;

    const columns = this.COLUMNS[this._activeList] || [];
    const filtered = this._getFilteredTasks();
    const byStatus = {};
    for (const task of filtered) {
      byStatus[task.status] = byStatus[task.status] || [];
      byStatus[task.status].push(task);
    }

    let rowIndex = 0;
    const groups = columns.map(status => {
      const col = this.COLUMN_CONFIG[status] || { label: status, color: '#6B7280' };
      const tasks = byStatus[status] || [];
      const isCollapsed = this._collapsedStatuses.has(status);
      const rows = isCollapsed ? '' : tasks.map(t => this._renderListRow(t, rowIndex++)).join('');

      return `
        <div class="kb-list-group" data-status="${status}"
             ondragover="TasksView.onListDragOver(event)"
             ondragenter="TasksView.onListDragEnter(event, '${status}')"
             ondragleave="TasksView.onListDragLeave(event)"
             ondrop="TasksView.onListDrop(event, '${status}')">
          <div class="kb-list-group-header" onclick="TasksView.toggleGroup('${status}')" style="--group-color: ${col.color};">
            <div class="kb-list-group-left">
              <svg class="kb-list-chevron ${isCollapsed ? '' : 'kb-list-chevron-open'}" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
              <span class="kb-list-group-dot" style="background: ${col.color};"></span>
              <span class="kb-list-group-title">${col.label}</span>
              <span class="kb-list-group-count">${tasks.length}</span>
            </div>
          </div>
          <div class="kb-list-group-body ${isCollapsed ? 'kb-list-group-collapsed' : ''}">
            ${rows || (tasks.length === 0 ? '<div class="kb-list-empty">No tasks</div>' : '')}
          </div>
        </div>
      `;
    }).join('');

    content.innerHTML = `<div class="kb-list-view">${groups}</div>`;
  },

  _renderListRow(task, index) {
    const prio = this.PRIORITY_CONFIG[task.priority] || this.PRIORITY_CONFIG.medium;
    const isDone = task.status === 'done' || task.status === 'cancelled';
    const isSelected = index === this._selectedIndex;

    const dueStr = task.due_date
      ? new Date(task.due_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      : '';
    const isOverdue = task.due_date && !isDone && new Date(task.due_date) < new Date();

    const catBadges = (task.categories || []).map(slug => {
      const cat = this._categories.find(c => c.slug === slug);
      if (!cat) return '';
      return `<span class="kb-cat-badge" style="background: ${cat.color}22; color: ${cat.color};">${Utils.escapeHtml(cat.name)}</span>`;
    }).join('');

    const effortLabel = task.estimated_effort ? `<span class="kb-effort">${Utils.escapeHtml(task.estimated_effort)}</span>` : '';

    return `
      <div class="kb-list-row ${isDone ? 'kb-list-row-done' : ''} ${isSelected ? 'kb-list-row-selected' : ''}"
           data-task-id="${task.id}" data-row-index="${index}"
           draggable="true"
           ondragstart="TasksView.onListRowDragStart(event, '${task.id}')"
           ondragend="TasksView.onListRowDragEnd(event)">
        <button class="kb-checkbox ${isDone ? 'kb-checkbox-checked' : ''}"
                onclick="event.stopPropagation(); TasksView.toggleComplete('${task.id}')"
                style="--check-color: ${prio.color};"
                title="${isDone ? 'Reopen' : 'Complete'}">
          ${isDone ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>' : ''}
        </button>
        <div class="kb-list-row-priority" style="background: ${prio.color};" title="${prio.label}"></div>
        <div class="kb-list-row-main" onclick="TasksView.showEditModal('${task.id}')">
          <div class="kb-list-row-title-line">
            <span class="kb-list-row-title ${isDone ? 'kb-title-done' : ''}">${Utils.escapeHtml(task.title)}</span>
            ${task.created_by === 'peter' ? '<span class="kb-peter-badge" title="Created by Peter">P</span>' : ''}
          </div>
          ${task.description ? `<div class="kb-list-row-desc">${Utils.escapeHtml(task.description).substring(0, 100)}${task.description.length > 100 ? '...' : ''}</div>` : ''}
        </div>
        <div class="kb-list-row-meta">
          <span class="kb-prio-chip" style="background: ${prio.bg}; color: ${prio.color};">${prio.label}</span>
          ${catBadges}
        </div>
        <div class="kb-list-row-end">
          ${dueStr ? `<span class="kb-due ${isOverdue ? 'kb-overdue' : ''}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> ${dueStr}</span>` : ''}
          ${effortLabel}
        </div>
        <button class="kb-quick-menu-btn" onclick="event.stopPropagation(); TasksView.showQuickMenu(event, '${task.id}')" title="Actions">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
          </svg>
        </button>
      </div>
    `;
  },

  toggleGroup(status) {
    if (this._collapsedStatuses.has(status)) {
      this._collapsedStatuses.delete(status);
    } else {
      this._collapsedStatuses.add(status);
    }
    this._persistState();
    this._renderContent();
  },

  // ===========================================================================
  // LIST VIEW — Drag and Drop between status groups
  // ===========================================================================
  onListRowDragStart(e, taskId) {
    this._dragTaskId = taskId;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', taskId);
    e.target.classList.add('kb-list-row-dragging');
  },

  onListRowDragEnd(e) {
    this._dragTaskId = null;
    e.target.classList.remove('kb-list-row-dragging');
    document.querySelectorAll('.kb-list-group-drop-target').forEach(el => el.classList.remove('kb-list-group-drop-target'));
  },

  onListDragOver(e) {
    if (!this._dragTaskId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  },

  onListDragEnter(e, targetStatus) {
    if (!this._dragTaskId) return;
    e.preventDefault();
    const task = this._tasks.find(t => t.id === this._dragTaskId);
    if (task && task.status === targetStatus) return;
    const group = e.target.closest('.kb-list-group');
    if (group) group.classList.add('kb-list-group-drop-target');
  },

  onListDragLeave(e) {
    const group = e.target.closest('.kb-list-group');
    if (group && !group.contains(e.relatedTarget)) {
      group.classList.remove('kb-list-group-drop-target');
    }
  },

  async onListDrop(e, targetStatus) {
    e.preventDefault();
    const group = e.target.closest('.kb-list-group');
    if (group) group.classList.remove('kb-list-group-drop-target');
    if (!this._dragTaskId) return;
    const task = this._tasks.find(t => t.id === this._dragTaskId);
    if (!task || task.status === targetStatus) return;
    await this.quickSetStatus(this._dragTaskId, targetStatus);
  },

  // ===========================================================================
  // KANBAN VIEW
  // ===========================================================================
  _renderKanban() {
    const content = document.getElementById('kb-content');
    if (!content) return;

    const columns = this.COLUMNS[this._activeList] || [];
    const filtered = this._getFilteredTasks();
    const byStatus = {};
    for (const task of filtered) {
      byStatus[task.status] = byStatus[task.status] || [];
      byStatus[task.status].push(task);
    }

    content.innerHTML = `<div class="kb-board">${columns.map(status => {
      const col = this.COLUMN_CONFIG[status] || { label: status, color: '#6B7280' };
      const tasks = byStatus[status] || [];
      const isDoneCol = status === 'done' || status === 'cancelled';
      const isCollapsed = isDoneCol && this._collapsedStatuses.has(status);
      const showMax = 10;
      const visibleTasks = tasks.slice(0, showMax);
      const hiddenCount = tasks.length - showMax;

      return `
        <div class="kb-column ${isCollapsed ? 'kb-column-collapsed' : ''}" data-status="${status}"
             ondragover="TasksView.onDragOver(event)"
             ondragenter="TasksView.onDragEnter(event)"
             ondragleave="TasksView.onDragLeave(event)"
             ondrop="TasksView.onDrop(event, '${status}')">
          <div class="kb-column-header" style="border-top: 3px solid ${col.color};"
               ${isDoneCol ? `onclick="TasksView.toggleGroup('${status}')"` : ''}>
            <span class="kb-column-title">${col.label}</span>
            <span class="kb-column-count">${tasks.length}</span>
          </div>
          <div class="kb-column-body">
            ${visibleTasks.map(t => this._renderCard(t)).join('')}
            ${hiddenCount > 0 ? `<button class="kb-show-more" onclick="this.parentElement.innerHTML = TasksView._renderAllCards('${status}'); ">Show ${hiddenCount} more</button>` : ''}
          </div>
        </div>
      `;
    }).join('')}</div>`;
  },

  _renderAllCards(status) {
    const filtered = this._getFilteredTasks().filter(t => t.status === status);
    return filtered.map(t => this._renderCard(t)).join('');
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
           style="border-left: 3px solid ${prio.color};"
           ondragstart="TasksView.onDragStart(event, '${task.id}')"
           ondragend="TasksView.onDragEnd(event)">
        <div class="kb-card-top">
          <button class="kb-checkbox kb-checkbox-sm ${isDone ? 'kb-checkbox-checked' : ''}"
                  onclick="event.stopPropagation(); TasksView.toggleComplete('${task.id}')"
                  style="--check-color: ${prio.color};"
                  title="${isDone ? 'Reopen' : 'Complete'}">
            ${isDone ? '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>' : ''}
          </button>
          <div class="kb-card-title-wrap" onclick="TasksView.showEditModal('${task.id}')">
            <span class="kb-card-title ${isDone ? 'kb-title-done' : ''}">${Utils.escapeHtml(task.title)}</span>
          </div>
          <button class="kb-quick-menu-btn kb-quick-menu-btn-card" onclick="event.stopPropagation(); TasksView.showQuickMenu(event, '${task.id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
            </svg>
          </button>
        </div>
        ${task.description ? `<div class="kb-card-desc" onclick="TasksView.showEditModal('${task.id}')">${Utils.escapeHtml(task.description).substring(0, 80)}${task.description.length > 80 ? '...' : ''}</div>` : ''}
        <div class="kb-card-footer">
          <span class="kb-prio-chip kb-prio-chip-sm" style="background: ${prio.bg}; color: ${prio.color};">${prio.label}</span>
          ${catBadges}
          ${dueStr ? `<span class="kb-due ${isOverdue ? 'kb-overdue' : ''}">${dueStr}</span>` : ''}
          ${task.created_by === 'peter' ? '<span class="kb-peter-badge" title="Created by Peter">P</span>' : ''}
        </div>
      </div>
    `;
  },

  // ===========================================================================
  // QUICK ACTIONS MENU
  // ===========================================================================
  showQuickMenu(event, taskId) {
    event.preventDefault();
    this.closeQuickMenu();
    this._quickMenuTaskId = taskId;
    const task = this._tasks.find(t => t.id === taskId);
    if (!task) return;

    const isDone = task.status === 'done' || task.status === 'cancelled';
    const columns = this.COLUMNS[this._activeList] || [];
    const priorities = Object.entries(this.PRIORITY_CONFIG);

    const statusItems = columns.filter(s => s !== task.status).map(s => {
      const sc = this.COLUMN_CONFIG[s] || { label: s, color: '#6B7280' };
      return `<button class="kb-qm-item" onclick="TasksView.quickSetStatus('${taskId}', '${s}')">
        <span class="kb-qm-dot" style="background: ${sc.color};"></span> ${sc.label}
      </button>`;
    }).join('');

    const prioItems = priorities.filter(([k]) => k !== task.priority).map(([k, v]) =>
      `<button class="kb-qm-item" onclick="TasksView.quickSetPriority('${taskId}', '${k}')">
        <span class="kb-qm-dot" style="background: ${v.color};"></span> ${v.label}
      </button>`
    ).join('');

    const menu = document.createElement('div');
    menu.className = 'kb-quick-menu';
    menu.innerHTML = `
      <button class="kb-qm-item kb-qm-item-primary" onclick="TasksView.toggleComplete('${taskId}')">
        ${isDone ? '&#x21bb; Reopen' : '&#x2713; Complete'}
      </button>
      <div class="kb-qm-divider"></div>
      <div class="kb-qm-label">Move to</div>
      ${statusItems}
      <div class="kb-qm-divider"></div>
      <div class="kb-qm-label">Priority</div>
      ${prioItems}
      <div class="kb-qm-divider"></div>
      <div class="kb-qm-label">Reschedule</div>
      <button class="kb-qm-item" onclick="TasksView.quickReschedule('${taskId}', 'today')">Today</button>
      <button class="kb-qm-item" onclick="TasksView.quickReschedule('${taskId}', 'tomorrow')">Tomorrow</button>
      <button class="kb-qm-item" onclick="TasksView.quickReschedule('${taskId}', 'next_week')">Next week</button>
      <button class="kb-qm-item" onclick="TasksView.quickReschedule('${taskId}', 'clear')">Clear date</button>
      <div class="kb-qm-divider"></div>
      <button class="kb-qm-item kb-qm-item-danger" onclick="TasksView.deleteTask('${taskId}')">Delete</button>
    `;

    document.body.appendChild(menu);

    // Position near the button
    const rect = event.target.closest('button').getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
    let top = rect.bottom + 4;
    let left = rect.right - menuRect.width;
    if (left < 8) left = 8;
    if (top + menuRect.height > window.innerHeight - 8) top = rect.top - menuRect.height - 4;
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';

    // Close on click outside
    setTimeout(() => {
      document.addEventListener('click', TasksView._closeQuickMenuHandler);
    }, 0);
  },

  _closeQuickMenuHandler(e) {
    if (!e.target.closest('.kb-quick-menu')) TasksView.closeQuickMenu();
  },

  closeQuickMenu() {
    document.querySelectorAll('.kb-quick-menu').forEach(m => m.remove());
    document.removeEventListener('click', TasksView._closeQuickMenuHandler);
    this._quickMenuTaskId = null;
  },

  async toggleComplete(taskId) {
    this.closeQuickMenu();
    const task = this._tasks.find(t => t.id === taskId);
    if (!task) return;
    const isDone = task.status === 'done' || task.status === 'cancelled';
    const newStatus = isDone ? (this.COLUMNS[this._activeList]?.[0] || 'inbox') : 'done';
    try {
      const resp = await fetch(`${this.HADLEY_API}/ptasks/${taskId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus, actor: 'chris' })
      });
      if (!resp.ok) {
        const err = await resp.json();
        Toast.error('Error', err.detail || 'Status change failed');
        return;
      }
      await this.loadData();
    } catch (error) {
      Toast.error('Error', error.message);
    }
  },

  async quickSetStatus(taskId, newStatus) {
    this.closeQuickMenu();
    try {
      const resp = await fetch(`${this.HADLEY_API}/ptasks/${taskId}/status`, {
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
      Toast.error('Error', error.message);
    }
  },

  async quickSetPriority(taskId, priority) {
    this.closeQuickMenu();
    try {
      await fetch(`${this.HADLEY_API}/ptasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority })
      });
      await this.loadData();
    } catch (error) {
      Toast.error('Error', error.message);
    }
  },

  async quickReschedule(taskId, when) {
    this.closeQuickMenu();
    let dueDate = null;
    if (when === 'today') {
      dueDate = new Date().toISOString();
    } else if (when === 'tomorrow') {
      const d = new Date(); d.setDate(d.getDate() + 1);
      dueDate = d.toISOString();
    } else if (when === 'next_week') {
      const d = new Date(); d.setDate(d.getDate() + (8 - d.getDay()) % 7 || 7);
      dueDate = d.toISOString();
    }
    try {
      await fetch(`${this.HADLEY_API}/ptasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ due_date: dueDate })
      });
      await this.loadData();
    } catch (error) {
      Toast.error('Error', error.message);
    }
  },

  // ===========================================================================
  // DRAG AND DROP (kanban)
  // ===========================================================================
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

  onDragOver(e) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; },

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
    await this.quickSetStatus(this._dragTaskId, newStatus);
  },

  // ===========================================================================
  // LIST SWITCHING
  // ===========================================================================
  async switchList(listType) {
    this._activeList = listType;
    this._persistState();
    document.querySelectorAll('.kb-list-tab').forEach(btn => {
      btn.classList.toggle('kb-list-tab-active', btn.dataset.list === listType);
    });
    document.getElementById('kb-content').innerHTML = Components.skeleton('table', 5);
    await this.loadData();
  },

  // ===========================================================================
  // KEYBOARD SHORTCUTS
  // ===========================================================================
  _boundKeyHandler: null,

  _bindKeyboard() {
    if (this._boundKeyHandler) document.removeEventListener('keydown', this._boundKeyHandler);
    this._boundKeyHandler = (e) => this._handleKey(e);
    document.addEventListener('keydown', this._boundKeyHandler);
  },

  _handleKey(e) {
    // Don't intercept when in inputs/modals
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (document.querySelector('.modal.open, .modal-backdrop.open')) return;
    if (this._viewMode !== 'list') return;

    const rows = document.querySelectorAll('.kb-list-row');
    const maxIndex = rows.length - 1;

    switch (e.key) {
      case 'n':
        e.preventDefault();
        this.showCreateModal();
        break;
      case 'j':
      case 'ArrowDown':
        e.preventDefault();
        this._selectedIndex = Math.min(this._selectedIndex + 1, maxIndex);
        this._highlightSelected(rows);
        break;
      case 'k':
      case 'ArrowUp':
        e.preventDefault();
        this._selectedIndex = Math.max(this._selectedIndex - 1, 0);
        this._highlightSelected(rows);
        break;
      case 'x':
        e.preventDefault();
        if (this._selectedIndex >= 0 && rows[this._selectedIndex]) {
          const id = rows[this._selectedIndex].dataset.taskId;
          if (id) this.toggleComplete(id);
        }
        break;
      case 'Enter':
        e.preventDefault();
        if (this._selectedIndex >= 0 && rows[this._selectedIndex]) {
          const id = rows[this._selectedIndex].dataset.taskId;
          if (id) this.showEditModal(id);
        }
        break;
      case '1': case '2': case '3': case '4': case '5':
        e.preventDefault();
        if (this._selectedIndex >= 0 && rows[this._selectedIndex]) {
          const id = rows[this._selectedIndex].dataset.taskId;
          const prioKeys = ['critical', 'high', 'medium', 'low', 'someday'];
          if (id) this.quickSetPriority(id, prioKeys[parseInt(e.key) - 1]);
        }
        break;
      case 'Escape':
        this._selectedIndex = -1;
        this._highlightSelected(rows);
        break;
    }
  },

  _highlightSelected(rows) {
    rows.forEach((r, i) => r.classList.toggle('kb-list-row-selected', i === this._selectedIndex));
    if (this._selectedIndex >= 0 && rows[this._selectedIndex]) {
      rows[this._selectedIndex].scrollIntoView({ block: 'nearest' });
    }
  },

  // ===========================================================================
  // EDIT MODAL
  // ===========================================================================
  async showEditModal(taskId) {
    try {
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

    const catChecks = document.querySelectorAll('.kb-cat-check input[type="checkbox"]');
    const selectedCats = Array.from(catChecks).filter(cb => cb.checked).map(cb => cb.value);

    try {
      const updateBody = { title, description: description || null, priority };
      if (dueDate) updateBody.due_date = new Date(dueDate).toISOString();
      if (effort) updateBody.estimated_effort = effort;

      const oldTask = this._tasks.find(t => t.id === taskId);

      await fetch(`${this.HADLEY_API}/ptasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateBody)
      });

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
        this._persistState();
        document.querySelectorAll('.kb-list-tab').forEach(btn => {
          btn.classList.toggle('kb-list-tab-active', btn.dataset.list === listType);
        });
      }
      await this.loadData();
    } catch (error) {
      Toast.error('Error', `Failed to create task: ${error.message}`);
    }
  },

  async deleteTask(taskId) {
    if (!confirm('Delete this task? This cannot be undone.')) return;
    this.closeQuickMenu();
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
// 7b. GOALS / ACCOUNTABILITY VIEW
// =============================================================================

const GoalsView = {
  title: 'Goals',
  HADLEY_API: '/api/hadley/proxy',
  _data: null,

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex items-center justify-between mb-lg">
          <h2 style="margin:0; font-size:18px; font-weight:600;">Accountability Tracker</h2>
          <div class="flex items-center gap-sm">
            <button class="btn btn-sm btn-primary" onclick="GoalsView.showAddModal()">
              ${Icons.plus || '+'} Add Goal
            </button>
            <button class="btn btn-sm btn-secondary" onclick="GoalsView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
        </div>

        <div id="goals-grid" class="goals-grid">
          <div style="padding: 40px; text-align: center; color: var(--text-muted);">Loading goals...</div>
        </div>

        <div class="accountability-extras">
          <div class="mood-widget" id="mood-widget">
            <div style="padding: 20px; text-align: center; color: var(--text-muted);">Loading mood...</div>
          </div>
          <div class="journal-widget" id="journal-widget">
            <div style="padding: 20px; text-align: center; color: var(--text-muted);">Loading journal...</div>
          </div>
        </div>
      </div>
    `;
    await Promise.all([this.loadGoals(), this.loadMood(), this.loadJournal()]);
  },

  async loadGoals() {
    try {
      const data = await API.get(`${this.HADLEY_API}/accountability/goals`);
      this._data = data;
      this.renderGoals(data.goals || []);
    } catch (e) {
      document.getElementById('goals-grid').innerHTML = `
        <div style="padding: 40px; text-align: center; color: var(--text-danger);">
          Failed to load goals: ${e.message}
        </div>`;
    }
  },

  renderGoals(goals) {
    const grid = document.getElementById('goals-grid');
    if (!goals.length) {
      grid.innerHTML = `
        <div style="padding: 60px; text-align: center; color: var(--text-muted);">
          <div style="font-size: 48px; margin-bottom: 16px;">&#127919;</div>
          <div style="font-size: 16px; margin-bottom: 8px;">No goals yet</div>
          <div style="font-size: 13px;">Add your first goal to start tracking.</div>
        </div>`;
      return;
    }
    grid.innerHTML = goals.map(g => this.renderGoalCard(g)).join('');
    // Load heatmaps after cards render
    goals.forEach(g => this.loadHeatmap(g.id));
  },

  renderGoalCard(goal) {
    const c = goal.computed || {};
    const pct = c.pct || 0;
    const isHabit = goal.goal_type === 'habit';
    const direction = goal.direction || 'up';

    // Category badge colors
    const catColors = {
      fitness: '#3b82f6', health: '#10b981', finance: '#f59e0b',
      learning: '#8b5cf6', general: '#6b7280'
    };
    const catColor = catColors[goal.category] || catColors.general;

    // Category icons
    const catIcons = {
      fitness: '&#127939;', health: '&#9878;&#65039;', finance: '&#128176;',
      learning: '&#128218;', general: '&#127919;'
    };
    const catIcon = catIcons[goal.category] || catIcons.general;

    // Format current/target values
    const cur = this.formatValue(goal.current_value, goal.metric);
    const tgt = this.formatValue(goal.target_value, goal.metric);

    // Progress bar color
    const barColor = pct >= 100 ? '#10b981' : pct >= 70 ? '#3b82f6' : pct >= 40 ? '#f59e0b' : '#ef4444';

    // Trend indicator
    const trendIcon = c.trend === '\u2191' ? '\u2191' : c.trend === '\u2193' ? '\u2193' : '\u2192';
    const trendColor = (direction === 'up')
      ? (c.trend === '\u2191' ? '#10b981' : c.trend === '\u2193' ? '#ef4444' : '#6b7280')
      : (c.trend === '\u2193' ? '#10b981' : c.trend === '\u2191' ? '#ef4444' : '#6b7280');

    // Streak display
    let streakHtml = '';
    if (isHabit && c.current_streak > 0) {
      const fires = c.current_streak >= 100 ? '\uD83D\uDD25\uD83D\uDD25\uD83D\uDD25' : c.current_streak >= 30 ? '\uD83D\uDD25\uD83D\uDD25' : c.current_streak >= 3 ? '\uD83D\uDD25' : '';
      streakHtml = `<span class="goal-streak">${c.current_streak}d ${fires}</span>`;
    }

    // Hit rate for habits
    let hitRateHtml = '';
    if (isHabit && c.hit_rate_7) {
      hitRateHtml = `<span class="goal-hit-rate">${c.hit_rate_7.hits}/${c.hit_rate_7.days} this week</span>`;
    }

    // On-track for target goals
    let onTrackHtml = '';
    if (!isHabit && c.on_track !== null && c.on_track !== undefined) {
      const otColor = c.on_track >= 90 ? '#10b981' : c.on_track >= 70 ? '#f59e0b' : '#ef4444';
      onTrackHtml = `<span class="goal-on-track" style="color:${otColor}">On-track: ${c.on_track}%</span>`;
    }

    // Deadline countdown
    let deadlineHtml = '';
    if (goal.deadline) {
      const daysLeft = Math.ceil((new Date(goal.deadline) - new Date()) / 86400000);
      if (daysLeft > 0) {
        deadlineHtml = `<span class="goal-deadline">${daysLeft}d left</span>`;
      } else {
        deadlineHtml = `<span class="goal-deadline" style="color:#ef4444">Overdue</span>`;
      }
    }

    // Heatmap for last 30 days
    const heatmapHtml = this.renderHeatmap(goal);

    return `
      <div class="goal-card" data-goal-id="${goal.id}" onclick="GoalsView.showGoalDetail('${goal.id}')" style="cursor:pointer;">
        <div class="goal-card-header">
          <div class="goal-title-row">
            <span class="goal-icon">${catIcon}</span>
            <span class="goal-title">${Utils.escapeHtml(goal.title)}</span>
          </div>
          <span class="goal-category-badge" style="background:${catColor}20; color:${catColor};">${goal.category}</span>
        </div>

        <div class="goal-values">
          <span class="goal-current">${cur}</span>
          <span class="goal-separator">/</span>
          <span class="goal-target">${tgt}</span>
          <span class="goal-pct" style="color:${barColor};">${Math.round(pct)}%</span>
          <span class="goal-trend" style="color:${trendColor};">${trendIcon}</span>
        </div>

        <div class="goal-progress-bar">
          <div class="goal-progress-fill" style="width:${Math.min(pct, 100)}%; background:${barColor};"></div>
        </div>

        <div class="goal-meta">
          ${streakHtml}${hitRateHtml}${onTrackHtml}${deadlineHtml}
        </div>

        ${heatmapHtml}

        <div class="goal-card-actions">
          ${goal.metric === 'boolean'
            ? `<button class="btn btn-sm ${c.today_value === 1 ? 'btn-success' : 'btn-outline'}" onclick="event.stopPropagation(); GoalsView.toggleBoolean('${goal.id}', ${c.today_value === 1 ? 0 : 1})">
                ${c.today_value === 1 ? '&#10003; Done' : '&#9675; Mark Done'}
              </button>`
            : `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); GoalsView.showLogModal('${goal.id}', '${Utils.escapeHtml(goal.title).replace(/'/g, "\\\\'")}', '${goal.metric}')">
                Log Progress
              </button>`
          }
          <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); GoalsView.deleteGoal('${goal.id}', '${Utils.escapeHtml(goal.title).replace(/'/g, "\\\\'")}')">
            ${Icons.x}
          </button>
        </div>
      </div>
    `;
  },

  renderHeatmap(goal) {
    // We don't have per-day data in the summary endpoint, so show a placeholder
    // that gets populated when we fetch progress detail
    return `<div class="goal-heatmap" id="heatmap-${goal.id}" title="30-day activity"></div>`;
  },

  async loadHeatmap(goalId) {
    try {
      const data = await API.get(`${this.HADLEY_API}/accountability/goals/${goalId}/progress?days=30`);
      const el = document.getElementById(`heatmap-${goalId}`);
      if (!el || !data.progress) return;

      const today = new Date();
      const dayMap = {};
      for (const p of data.progress) {
        dayMap[p.date] = parseFloat(p.value);
      }

      let html = '';
      for (let i = 29; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const key = d.toISOString().slice(0, 10);
        const val = dayMap[key];
        const cls = val !== undefined ? (val > 0 ? 'heatmap-hit' : 'heatmap-miss') : 'heatmap-empty';
        html += `<div class="heatmap-cell ${cls}" title="${key}: ${val !== undefined ? val : 'no data'}"></div>`;
      }
      el.innerHTML = html;
    } catch (e) {
      // Silently fail — heatmap is non-critical
    }
  },

  formatValue(value, metric) {
    const v = parseFloat(value) || 0;
    switch (metric) {
      case 'steps': return v.toLocaleString('en-GB');
      case 'gbp': return '\u00a3' + v.toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      case 'kg': return v.toFixed(1) + 'kg';
      case 'ml': return v.toLocaleString('en-GB') + 'ml';
      case 'kcal': return v.toLocaleString('en-GB') + 'kcal';
      case 'boolean': return v >= 1 ? '&#10003;' : '&#10007;';
      default: return v.toLocaleString('en-GB');
    }
  },

  showAddModal() {
    Modal.open({
      title: 'Add Goal',
      content: `
        <div class="form-group">
          <label>Title</label>
          <input type="text" id="goal-title" class="form-input" placeholder="e.g. 10k steps daily">
        </div>
        <div class="form-group">
          <label>Type</label>
          <select id="goal-type" class="form-input" onchange="GoalsView.toggleHabitFields()">
            <option value="habit">Habit (recurring)</option>
            <option value="target">Target (one-off)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Category</label>
          <select id="goal-category" class="form-input">
            <option value="fitness">Fitness</option>
            <option value="health">Health</option>
            <option value="finance">Finance</option>
            <option value="learning">Learning</option>
            <option value="general">General</option>
          </select>
        </div>
        <div class="form-group">
          <label>Metric</label>
          <select id="goal-metric" class="form-input" onchange="GoalsView.onMetricChange()">
            <option value="steps">Steps</option>
            <option value="kcal">Calories (kcal)</option>
            <option value="ml">Millilitres (ml)</option>
            <option value="kg">Kilograms (kg)</option>
            <option value="gbp">Pounds (\u00a3)</option>
            <option value="count">Count</option>
            <option value="boolean">Yes/No (daily check-in)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Target Value</label>
          <input type="number" id="goal-target" class="form-input" placeholder="e.g. 10000" step="any">
        </div>
        <div class="form-group">
          <label>Starting Value</label>
          <input type="number" id="goal-start" class="form-input" placeholder="0" value="0" step="any">
        </div>
        <div class="form-group">
          <label>Direction</label>
          <select id="goal-direction" class="form-input">
            <option value="up">Up (higher is better)</option>
            <option value="down">Down (lower is better)</option>
          </select>
        </div>
        <div id="habit-fields">
          <div class="form-group">
            <label>Frequency</label>
            <select id="goal-frequency" class="form-input">
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
        </div>
        <div id="target-fields" style="display:none;">
          <div class="form-group">
            <label>Deadline</label>
            <input type="date" id="goal-deadline" class="form-input">
          </div>
        </div>
        <div class="form-group">
          <label>Auto-Source (optional)</label>
          <select id="goal-auto-source" class="form-input">
            <option value="">Manual only</option>
            <option value="garmin_steps">Garmin Steps</option>
            <option value="garmin_sleep">Garmin Sleep</option>
            <option value="nutrition_calories">Nutrition Calories</option>
            <option value="nutrition_water">Nutrition Water</option>
            <option value="nutrition_protein">Nutrition Protein</option>
            <option value="weight">Weight (Withings)</option>
          </select>
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
        <button class="btn btn-primary" onclick="GoalsView.saveGoal()" style="margin-left:8px;">Create</button>
      `,
    });
  },

  onMetricChange() {
    const metric = document.getElementById('goal-metric').value;
    const targetEl = document.getElementById('goal-target');
    const startEl = document.getElementById('goal-start');
    if (metric === 'boolean') {
      targetEl.value = '1';
      targetEl.disabled = true;
      startEl.value = '0';
      startEl.disabled = true;
    } else {
      targetEl.disabled = false;
      startEl.disabled = false;
    }
  },

  toggleHabitFields() {
    const type = document.getElementById('goal-type').value;
    document.getElementById('habit-fields').style.display = type === 'habit' ? '' : 'none';
    document.getElementById('target-fields').style.display = type === 'target' ? '' : 'none';
  },

  async saveGoal() {
    const title = document.getElementById('goal-title').value.trim();
    const goalType = document.getElementById('goal-type').value;
    const category = document.getElementById('goal-category').value;
    const metric = document.getElementById('goal-metric').value;
    const targetValue = parseFloat(document.getElementById('goal-target').value);
    const startValue = parseFloat(document.getElementById('goal-start').value) || 0;
    const direction = document.getElementById('goal-direction').value;
    const autoSource = document.getElementById('goal-auto-source').value || null;

    if (!title || !targetValue) {
      Toast.show('Title and target value are required', 'error');
      return;
    }

    const payload = {
      title, goal_type: goalType, category, metric,
      target_value: targetValue, start_value: startValue, direction,
      auto_source: autoSource,
    };

    if (goalType === 'habit') {
      payload.frequency = document.getElementById('goal-frequency').value;
    } else {
      const deadline = document.getElementById('goal-deadline').value;
      if (deadline) payload.deadline = deadline;
    }

    try {
      await API.post(`${this.HADLEY_API}/accountability/goals`, payload);
      Modal.close();
      Toast.show('Goal created', 'success');
      await this.loadGoals();
    } catch (e) {
      Toast.show('Failed to create goal: ' + e.message, 'error');
    }
  },

  showLogModal(goalId, title, metric) {
    Modal.open({
      title: `Log Progress: ${title}`,
      content: `
        <div class="form-group">
          <label>Value (${metric})</label>
          <input type="number" id="log-value" class="form-input" placeholder="Enter value" step="any" autofocus>
        </div>
        <div class="form-group">
          <label>Note (optional)</label>
          <input type="text" id="log-note" class="form-input" placeholder="e.g. PB today!">
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
        <button class="btn btn-primary" onclick="GoalsView.logProgress('${goalId}')" style="margin-left:8px;">Log</button>
      `,
    });
  },

  async logProgress(goalId) {
    const value = parseFloat(document.getElementById('log-value').value);
    const note = document.getElementById('log-note').value.trim() || null;

    if (isNaN(value)) {
      Toast.show('Enter a valid number', 'error');
      return;
    }

    try {
      await API.post(`${this.HADLEY_API}/accountability/goals/${goalId}/progress`, {
        value, source: 'manual', note,
      });
      Modal.close();
      Toast.show('Progress logged', 'success');
      await this.loadGoals();
    } catch (e) {
      Toast.show('Failed to log: ' + e.message, 'error');
    }
  },

  async deleteGoal(goalId, title) {
    if (!confirm(`Abandon goal "${title}"?`)) return;
    try {
      await API.delete(`${this.HADLEY_API}/accountability/goals/${goalId}`);
      Toast.show('Goal abandoned', 'success');
      await this.loadGoals();
    } catch (e) {
      Toast.show('Failed: ' + e.message, 'error');
    }
  },

  // ── Goal Detail Panel ───────────────────────────────────────────────

  async showGoalDetail(goalId) {
    try {
      const data = await API.get(`${this.HADLEY_API}/accountability/goals/${goalId}?days=31`);
      const goal = data;
      const progress = data.progress || [];
      const milestones = data.milestones || [];
      const c = goal.computed || {};

      const today = new Date();
      const last7 = progress.filter(p => (today - new Date(p.date)) / 86400000 < 7);
      const last31 = progress;

      const progressTableRows = (entries) => entries.map(p =>
        `<tr>
          <td>${p.date}</td>
          <td>${this.formatValue(p.value, goal.metric)}</td>
          <td style="color: ${(p.delta||0) >= 0 ? '#10b981' : '#ef4444'}">${p.delta != null ? (p.delta >= 0 ? '+' : '') + this.formatValue(Math.abs(p.delta), goal.metric) : '-'}</td>
          <td style="color: var(--text-muted); font-size:11px;">${p.source || ''}</td>
        </tr>`
      ).join('');

      const milestoneRows = milestones.map(m =>
        `<div class="goal-detail-milestone ${m.reached_at ? 'reached' : ''}">
          <span>${m.reached_at ? '&#9989;' : '&#9675;'}</span>
          <span>${Utils.escapeHtml(m.title)}</span>
          <span style="margin-left:auto; color:var(--text-muted);">${this.formatValue(m.target_value, goal.metric)}</span>
          ${m.reached_at ? `<span style="font-size:11px; color:var(--text-muted);">${m.reached_at.slice(0,10)}</span>` : ''}
        </div>`
      ).join('') || '<div style="color:var(--text-muted);">No milestones set</div>';

      // Summary stats
      const statsHtml = `
        <div class="goal-detail-stats">
          <div class="goal-detail-stat">
            <div class="goal-detail-stat-value">${this.formatValue(goal.current_value, goal.metric)}</div>
            <div class="goal-detail-stat-label">Current</div>
          </div>
          <div class="goal-detail-stat">
            <div class="goal-detail-stat-value">${this.formatValue(goal.target_value, goal.metric)}</div>
            <div class="goal-detail-stat-label">Target</div>
          </div>
          <div class="goal-detail-stat">
            <div class="goal-detail-stat-value">${Math.round(c.pct || 0)}%</div>
            <div class="goal-detail-stat-label">Progress</div>
          </div>
          ${c.on_track != null ? `<div class="goal-detail-stat">
            <div class="goal-detail-stat-value">${c.on_track}%</div>
            <div class="goal-detail-stat-label">On-track</div>
          </div>` : ''}
          ${c.current_streak ? `<div class="goal-detail-stat">
            <div class="goal-detail-stat-value">${c.current_streak}d</div>
            <div class="goal-detail-stat-label">Streak</div>
          </div>` : ''}
        </div>`;

      const content = `
        <div class="goal-detail">
          <div class="goal-detail-header">
            <h3 style="margin:0;">${Utils.escapeHtml(goal.title)}</h3>
            <span class="goal-category-badge" style="background:#3b82f620; color:#3b82f6;">${goal.category} &middot; ${goal.goal_type}</span>
          </div>
          ${statsHtml}
          ${goal.description ? `<p style="color:var(--text-secondary); font-size:13px;">${Utils.escapeHtml(goal.description)}</p>` : ''}

          <h4 style="margin: 16px 0 8px;">Last 7 Days</h4>
          <table class="goal-detail-table">
            <thead><tr><th>Date</th><th>Value</th><th>Change</th><th>Source</th></tr></thead>
            <tbody>${progressTableRows(last7) || '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No data</td></tr>'}</tbody>
          </table>

          <h4 style="margin: 16px 0 8px;">Last 31 Days</h4>
          <table class="goal-detail-table">
            <thead><tr><th>Date</th><th>Value</th><th>Change</th><th>Source</th></tr></thead>
            <tbody>${progressTableRows(last31) || '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No data</td></tr>'}</tbody>
          </table>

          <h4 style="margin: 16px 0 8px;">Milestones</h4>
          <div class="goal-detail-milestones">${milestoneRows}</div>
        </div>
      `;
      DetailPanel.open(content);
    } catch (e) {
      Toast.show('Failed to load goal detail: ' + e.message, 'error');
    }
  },

  // ── Boolean Habit Toggle ──────────────────────────────────────────

  async toggleBoolean(goalId, newValue) {
    try {
      await API.post(`${this.HADLEY_API}/accountability/goals/${goalId}/progress`, {
        value: newValue, source: 'manual',
      });
      Toast.show(newValue === 1 ? 'Done!' : 'Unmarked', 'success');
      await this.loadGoals();
    } catch (e) {
      Toast.show('Failed: ' + e.message, 'error');
    }
  },

  // ── Mood Widget ───────────────────────────────────────────────────

  async loadMood() {
    const el = document.getElementById('mood-widget');
    if (!el) return;
    try {
      const data = await API.get(`${this.HADLEY_API}/accountability/mood`);
      this.renderMoodWidget(el, data);
    } catch (e) {
      el.innerHTML = `<div class="widget-header">Mood</div><div style="padding:12px; color:var(--text-muted);">Could not load mood</div>`;
    }
  },

  renderMoodWidget(el, data) {
    const today = data.today;
    const todayScore = today ? today.score : null;
    const todayNote = today ? today.note || '' : '';
    const history = data.history_7 || [];
    const weekAvg = data.week_avg;
    const trend = data.trend;

    const trendIcon = trend === 'up' ? '&#8593;' : trend === 'down' ? '&#8595;' : '&#8594;';
    const trendColor = trend === 'up' ? '#10b981' : trend === 'down' ? '#ef4444' : '#6b7280';

    // Mood buttons (1-10)
    const buttons = Array.from({length: 10}, (_, i) => {
      const n = i + 1;
      const isActive = todayScore === n;
      const color = n <= 3 ? '#ef4444' : n <= 6 ? '#f59e0b' : '#10b981';
      return `<button class="mood-btn ${isActive ? 'active' : ''}" style="${isActive ? `background:${color}; color:white;` : ''}" onclick="GoalsView.logMood(${n})">${n}</button>`;
    }).join('');

    // 7-day dots
    const dots = history.slice(0, 7).reverse().map(h => {
      const s = h.score;
      const color = s <= 3 ? '#ef4444' : s <= 6 ? '#f59e0b' : '#10b981';
      return `<div class="mood-dot" style="background:${color};" title="${h.date}: ${s}/10${h.note ? ' — ' + h.note : ''}"></div>`;
    }).join('');

    el.innerHTML = `
      <div class="widget-header">Mood Today</div>
      <div class="mood-buttons">${buttons}</div>
      <div class="mood-note-row">
        <input type="text" id="mood-note" class="form-input" placeholder="Optional note..." value="${Utils.escapeHtml(todayNote)}" style="flex:1; font-size:12px;">
        <button class="btn btn-sm btn-secondary" onclick="GoalsView.saveMoodNote()" style="margin-left:6px;">Save</button>
      </div>
      <div class="mood-footer">
        <div class="mood-dots">${dots || '<span style="color:var(--text-muted); font-size:12px;">No data yet</span>'}</div>
        <div class="mood-avg">${weekAvg != null ? `Avg: ${weekAvg} <span style="color:${trendColor};">${trendIcon}</span>` : ''}</div>
      </div>
    `;
  },

  async logMood(score) {
    const noteEl = document.getElementById('mood-note');
    const note = noteEl ? noteEl.value.trim() : null;
    try {
      await API.post(`${this.HADLEY_API}/accountability/mood`, { score, note: note || null });
      Toast.show(`Mood: ${score}/10`, 'success');
      await this.loadMood();
    } catch (e) {
      Toast.show('Failed to log mood: ' + e.message, 'error');
    }
  },

  async saveMoodNote() {
    // Re-save today's mood with the updated note (need current score)
    try {
      const data = await API.get(`${this.HADLEY_API}/accountability/mood`);
      const score = data.today ? data.today.score : null;
      if (!score) { Toast.show('Log a mood score first', 'error'); return; }
      const note = document.getElementById('mood-note')?.value.trim() || null;
      await API.post(`${this.HADLEY_API}/accountability/mood`, { score, note });
      Toast.show('Note saved', 'success');
    } catch (e) {
      Toast.show('Failed: ' + e.message, 'error');
    }
  },

  // ── Journal Widget ────────────────────────────────────────────────

  async loadJournal() {
    const el = document.getElementById('journal-widget');
    if (!el) return;
    try {
      const [todayData, historyData] = await Promise.all([
        API.get(`${this.HADLEY_API}/accountability/journal`),
        API.get(`${this.HADLEY_API}/accountability/journal/history?days=7`),
      ]);
      this.renderJournalWidget(el, todayData.entry, historyData.history || []);
    } catch (e) {
      el.innerHTML = `<div class="widget-header">Journal</div><div style="padding:12px; color:var(--text-muted);">Could not load journal</div>`;
    }
  },

  renderJournalWidget(el, todayEntry, history) {
    const content = todayEntry ? todayEntry.content : '';
    const previousEntries = history.filter(h => h.date !== new Date().toISOString().slice(0, 10)).slice(0, 3);

    const prevHtml = previousEntries.length > 0
      ? `<details class="journal-previous">
           <summary style="cursor:pointer; font-size:12px; color:var(--text-muted); margin-top:8px;">Previous entries</summary>
           ${previousEntries.map(h => `
             <div class="journal-prev-entry">
               <div class="journal-prev-date">${h.date}</div>
               <div class="journal-prev-text">${Utils.escapeHtml(h.content)}</div>
             </div>`).join('')}
         </details>`
      : '';

    el.innerHTML = `
      <div class="widget-header">Journal</div>
      <textarea id="journal-content" class="form-input journal-textarea" placeholder="Thoughts for today...">${Utils.escapeHtml(content)}</textarea>
      <div style="display:flex; justify-content:flex-end; margin-top:6px;">
        <button class="btn btn-sm btn-primary" onclick="GoalsView.saveJournal()">Save</button>
      </div>
      ${prevHtml}
    `;
  },

  async saveJournal() {
    const content = document.getElementById('journal-content')?.value.trim();
    if (!content) { Toast.show('Write something first', 'error'); return; }
    try {
      await API.post(`${this.HADLEY_API}/accountability/journal`, { content });
      Toast.show('Journal saved', 'success');
    } catch (e) {
      Toast.show('Failed: ' + e.message, 'error');
    }
  },

  async refresh() {
    await Promise.all([this.loadGoals(), this.loadMood(), this.loadJournal()]);
    Toast.show('Refreshed', 'success');
  },
};


// =============================================================================
// 7c. SUBSCRIPTIONS VIEW
// =============================================================================

const SubscriptionsView = {
  title: 'Subscriptions',
  _data: null,
  _scope: 'all',
  _status: 'active',
  _category: 'all',
  _editingId: null,

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex items-center justify-between mb-lg">
          <div class="flex items-center gap-sm">
            <select id="subs-scope" class="form-input" style="width: auto;">
              <option value="all" selected>All Scopes</option>
              <option value="personal">Personal</option>
              <option value="business">Business</option>
            </select>
            <select id="subs-status" class="form-input" style="width: auto;">
              <option value="active" selected>Active</option>
              <option value="all">All Statuses</option>
              <option value="cancelled">Cancelled</option>
              <option value="paused">Paused</option>
            </select>
            <select id="subs-category" class="form-input" style="width: auto;">
              <option value="all" selected>All Categories</option>
            </select>
          </div>
          <div class="flex items-center gap-sm">
            <button class="btn btn-sm btn-primary" onclick="SubscriptionsView.showAddModal()">
              ${Icons.plus} Add
            </button>
            <button class="btn btn-sm btn-secondary" onclick="SubscriptionsView.refresh()">
              ${Icons.refresh} Refresh
            </button>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-md mb-lg" id="subs-stats">
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
          ${Components.skeleton('card')}
        </div>

        <div class="grid grid-cols-2 gap-md mb-lg">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">By Category</h3>
            </div>
            <div class="card-body" id="subs-by-category">
              ${Components.skeleton('table', 5)}
            </div>
          </div>
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">By Scope</h3>
            </div>
            <div class="card-body" id="subs-by-scope">
              ${Components.skeleton('table', 3)}
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">All Subscriptions</h3>
          </div>
          <div class="card-body" id="subs-table">
            ${Components.skeleton('table', 10)}
          </div>
        </div>
      </div>
    `;

    ['subs-scope', 'subs-status', 'subs-category'].forEach(id => {
      document.getElementById(id).addEventListener('change', () => this._applyFilters());
    });

    await this.loadData();
  },

  async _applyFilters() {
    this._scope = document.getElementById('subs-scope').value;
    this._status = document.getElementById('subs-status').value;
    this._category = document.getElementById('subs-category').value;
    await this.loadData();
  },

  async loadData() {
    try {
      const params = new URLSearchParams();
      if (this._scope !== 'all') params.set('scope', this._scope);
      if (this._status !== 'all') params.set('status', this._status);
      if (this._category !== 'all') params.set('category', this._category);

      const data = await API.get(`/api/subscriptions?${params}`);
      this._data = data;

      this.renderStats(data.summary);
      this.renderByCategory(data.summary.by_category || {});
      this.renderByScope(data.summary);
      this.renderTable(data.subscriptions || []);
      this._populateCategoryFilter(data.summary.by_category || {});
    } catch (error) {
      console.error('Failed to load subscriptions:', error);
      Toast.error('Error', 'Failed to load subscriptions');
    }
  },

  _populateCategoryFilter(byCategory) {
    const sel = document.getElementById('subs-category');
    if (!sel) return;
    const current = sel.value;
    const cats = Object.keys(byCategory).sort();
    sel.innerHTML = '<option value="all">All Categories</option>' +
      cats.map(c => `<option value="${Utils.escapeHtml(c)}" ${c === current ? 'selected' : ''}>${Utils.escapeHtml(c)}</option>`).join('');
  },

  renderStats(summary) {
    const el = document.getElementById('subs-stats');
    if (!el) return;

    el.innerHTML = `
      ${Components.statsCard({
        icon: Icons.activity,
        value: '\u00A3' + summary.total_monthly.toFixed(2),
        label: 'Total Monthly',
        variant: 'info'
      })}
      ${Components.statsCard({
        icon: Icons.checkCircle,
        value: summary.active_count,
        label: 'Active Subscriptions',
        variant: 'success'
      })}
      ${Components.statsCard({
        icon: Icons.clock,
        value: '\u00A3' + summary.personal_monthly.toFixed(2),
        label: 'Personal Monthly',
        variant: 'info'
      })}
      ${Components.statsCard({
        icon: Icons.zap,
        value: '\u00A3' + summary.business_monthly.toFixed(2),
        label: 'Business Monthly',
        variant: 'warning'
      })}
    `;
  },

  renderByCategory(byCategory) {
    const el = document.getElementById('subs-by-category');
    if (!el) return;

    const entries = Object.entries(byCategory).sort((a, b) => b[1].monthly - a[1].monthly);
    if (entries.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No data</p>';
      return;
    }

    const rows = entries.map(([cat, d]) => `
      <tr>
        <td>${Utils.escapeHtml(cat)}</td>
        <td class="text-right">${d.count}</td>
        <td class="text-right font-mono">\u00A3${d.monthly.toFixed(2)}</td>
        <td class="text-right font-mono text-muted">\u00A3${(d.monthly * 12).toFixed(2)}</td>
      </tr>
    `).join('');

    el.innerHTML = `
      <table class="table">
        <thead>
          <tr>
            <th>Category</th>
            <th class="text-right">Count</th>
            <th class="text-right">Monthly</th>
            <th class="text-right">Annual</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  renderByScope(summary) {
    const el = document.getElementById('subs-by-scope');
    if (!el) return;

    el.innerHTML = `
      <table class="table">
        <thead>
          <tr>
            <th>Scope</th>
            <th class="text-right">Monthly</th>
            <th class="text-right">Annual</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><span class="status status-running">Personal</span></td>
            <td class="text-right font-mono">\u00A3${summary.personal_monthly.toFixed(2)}</td>
            <td class="text-right font-mono text-muted">\u00A3${(summary.personal_monthly * 12).toFixed(2)}</td>
          </tr>
          <tr>
            <td><span class="status status-warning">Business</span></td>
            <td class="text-right font-mono">\u00A3${summary.business_monthly.toFixed(2)}</td>
            <td class="text-right font-mono text-muted">\u00A3${(summary.business_monthly * 12).toFixed(2)}</td>
          </tr>
          <tr style="font-weight: 600; border-top: 2px solid var(--border);">
            <td>Total</td>
            <td class="text-right font-mono">\u00A3${summary.total_monthly.toFixed(2)}</td>
            <td class="text-right font-mono">\u00A3${summary.total_annual.toFixed(2)}</td>
          </tr>
        </tbody>
      </table>
    `;
  },

  renderTable(subs) {
    const el = document.getElementById('subs-table');
    if (!el) return;

    if (subs.length === 0) {
      el.innerHTML = '<p class="text-muted text-center p-md">No subscriptions found</p>';
      return;
    }

    const rows = subs.map(s => {
      const scopeBadge = s.scope === 'business'
        ? '<span class="status status-warning">Biz</span>'
        : '<span class="status status-running">Personal</span>';
      const statusBadge = s.status === 'active'
        ? '<span class="status status-success">Active</span>'
        : s.status === 'cancelled'
          ? '<span class="status status-error">Cancelled</span>'
          : `<span class="status status-idle">${Utils.escapeHtml(s.status)}</span>`;

      const freq = s.frequency === 'fortnightly' ? '/2wk'
        : s.frequency === 'monthly' ? '/mo'
        : s.frequency === 'annual' ? '/yr'
        : s.frequency === 'termly' ? '/term'
        : s.frequency === 'quarterly' ? '/qtr'
        : s.frequency === 'weekly' ? '/wk'
        : '';

      return `
        <tr style="cursor: pointer;" onclick="SubscriptionsView.showDetail('${s.id}')">
          <td style="min-width: 160px;">
            <div style="font-weight: 500;">${Utils.escapeHtml(s.name)}</div>
            ${s.provider && s.provider !== s.name ? `<div class="text-sm text-muted">${Utils.escapeHtml(s.provider)}</div>` : ''}
          </td>
          <td>${scopeBadge}</td>
          <td class="text-sm" style="white-space: nowrap;">${Utils.escapeHtml(s.category || '-')}</td>
          <td class="text-right font-mono" style="white-space: nowrap;">\u00A3${parseFloat(s.amount).toFixed(2)}${freq}</td>
          <td class="text-right font-mono" style="white-space: nowrap;">\u00A3${s.monthly_cost.toFixed(2)}</td>
          <td class="text-right font-mono text-muted" style="white-space: nowrap;">\u00A3${s.annual_cost.toFixed(2)}</td>
          <td>${statusBadge}</td>
          <td class="text-right" style="white-space: nowrap;">
            <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); SubscriptionsView.editSub('${s.id}')" title="Edit">
              ${Icons.save}
            </button>
            <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); SubscriptionsView.deleteSub('${s.id}', '${Utils.escapeHtml(s.name)}')" title="Delete" style="margin-left: 4px;">
              ${Icons.x}
            </button>
          </td>
        </tr>
      `;
    }).join('');

    el.innerHTML = `
      <div style="overflow-x: auto;">
        <table class="table" style="table-layout: auto; width: 100%;">
          <thead>
            <tr>
              <th style="min-width: 160px;">Name</th>
              <th>Scope</th>
              <th>Category</th>
              <th class="text-right" style="white-space: nowrap;">Amount</th>
              <th class="text-right" style="white-space: nowrap;">Monthly</th>
              <th class="text-right" style="white-space: nowrap;">Annual</th>
              <th>Status</th>
              <th class="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  },

  async showDetail(id) {
    if (!this._data) return;
    const s = this._data.subscriptions.find(sub => sub.id === id);
    if (!s) return;

    const scopeBadge = s.scope === 'business'
      ? '<span class="status status-warning">Business</span>'
      : '<span class="status status-running">Personal</span>';
    const statusBadge = s.status === 'active'
      ? '<span class="status status-success">Active</span>'
      : s.status === 'cancelled'
        ? '<span class="status status-error">Cancelled</span>'
        : `<span class="status status-idle">${Utils.escapeHtml(s.status)}</span>`;

    const freq = {weekly:'Weekly',fortnightly:'Fortnightly',monthly:'Monthly',quarterly:'Quarterly',termly:'Per Term',annual:'Annual'}[s.frequency] || s.frequency;

    // Build detail rows
    const fields = [
      ['Provider', s.provider],
      ['Scope', scopeBadge],
      ['Category', s.category],
      ['Amount', `\u00A3${parseFloat(s.amount).toFixed(2)} ${freq}`],
      ['Monthly Equiv', `\u00A3${s.monthly_cost.toFixed(2)}`],
      ['Annual Equiv', `\u00A3${s.annual_cost.toFixed(2)}`],
      ['Status', statusBadge],
      ['Billing Day', s.billing_day ? `Day ${s.billing_day}` : null],
      ['Next Renewal', s.next_renewal_date],
      ['Start Date', s.start_date],
      ['End Date', s.end_date],
      ['Payment', s.payment_method],
      ['Bank Pattern', s.bank_description_pattern ? `<code>${Utils.escapeHtml(s.bank_description_pattern)}</code>` : null],
      ['Plan Tier', s.plan_tier],
      ['Auto Renew', s.auto_renew !== null ? (s.auto_renew ? 'Yes' : 'No') : null],
      ['URL', s.url ? `<a href="${Utils.escapeHtml(s.url)}" target="_blank" style="color: var(--primary);">${Utils.escapeHtml(s.url)}</a>` : null],
      ['Notes', s.notes],
    ].filter(([, v]) => v != null && v !== '');

    const detailRows = fields.map(([label, val]) => `
      <tr>
        <td class="text-muted text-sm" style="width: 120px; padding: 6px 8px; vertical-align: top;">${label}</td>
        <td style="padding: 6px 8px;">${val}</td>
      </tr>
    `).join('');

    // Show panel immediately with loading state for transactions
    DetailPanel.open(`
      <div style="padding: 16px;">
        <div class="flex items-center justify-between mb-md">
          <h3 style="margin: 0;">${Utils.escapeHtml(s.name)}</h3>
          <div class="flex items-center gap-sm">
            <button class="btn btn-sm btn-secondary" onclick="SubscriptionsView.editSub('${s.id}')">Edit</button>
            <button class="btn btn-sm btn-secondary" onclick="DetailPanel.close()">${Icons.x}</button>
          </div>
        </div>

        <table class="table" style="margin-bottom: 20px;">
          <tbody>${detailRows}</tbody>
        </table>

        <h4 style="margin: 0 0 8px 0;">Recent Transactions</h4>
        <div id="sub-detail-txns">
          ${Components.skeleton('table', 5)}
        </div>
      </div>
    `);

    // Fetch matching transactions
    try {
      const data = await API.get(`/api/subscriptions/${id}/transactions?limit=20`);
      const txnEl = document.getElementById('sub-detail-txns');
      if (!txnEl) return;

      if (!data.transactions || data.transactions.length === 0) {
        txnEl.innerHTML = `<p class="text-muted text-sm">${data.message || 'No matching transactions found'}</p>`;
        return;
      }

      const txnRows = data.transactions.map(t => `
        <tr>
          <td class="font-mono text-sm" style="white-space: nowrap;">${t.date}</td>
          <td class="text-sm" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${Utils.escapeHtml(t.description)}">${Utils.escapeHtml(t.description)}</td>
          <td class="text-right font-mono" style="white-space: nowrap; color: ${parseFloat(t.amount) < 0 ? 'var(--error)' : 'var(--success)'};">\u00A3${Math.abs(parseFloat(t.amount)).toFixed(2)}</td>
        </tr>
      `).join('');

      txnEl.innerHTML = `
        <table class="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th class="text-right">Amount</th>
            </tr>
          </thead>
          <tbody>${txnRows}</tbody>
        </table>
        <p class="text-muted text-sm" style="margin-top: 8px;">${data.match_count} matching transaction${data.match_count !== 1 ? 's' : ''} found</p>
      `;
    } catch (error) {
      const txnEl = document.getElementById('sub-detail-txns');
      if (txnEl) txnEl.innerHTML = '<p class="text-muted text-sm">Failed to load transactions</p>';
    }
  },

  showAddModal(existing = null) {
    const isEdit = !!existing;
    const s = existing || {};

    Modal.show(
      isEdit ? 'Edit Subscription' : 'Add Subscription',
      `<form id="sub-form" style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
        <div>
          <label class="form-label">Name *</label>
          <input class="form-input" name="name" value="${Utils.escapeHtml(s.name || '')}" required>
        </div>
        <div>
          <label class="form-label">Provider</label>
          <input class="form-input" name="provider" value="${Utils.escapeHtml(s.provider || '')}">
        </div>
        <div>
          <label class="form-label">Scope *</label>
          <select class="form-input" name="scope">
            <option value="personal" ${s.scope !== 'business' ? 'selected' : ''}>Personal</option>
            <option value="business" ${s.scope === 'business' ? 'selected' : ''}>Business</option>
          </select>
        </div>
        <div>
          <label class="form-label">Category</label>
          <input class="form-input" name="category" value="${Utils.escapeHtml(s.category || '')}" list="cat-suggestions">
          <datalist id="cat-suggestions">
            <option value="Entertainment">
            <option value="AI & Tech">
            <option value="TV & Internet">
            <option value="Utilities">
            <option value="Phone">
            <option value="Insurance">
            <option value="Kids Activities">
            <option value="Household">
            <option value="Shopping">
            <option value="Family">
            <option value="Fitness">
            <option value="Infrastructure">
            <option value="Platform Fees">
          </datalist>
        </div>
        <div>
          <label class="form-label">Amount *</label>
          <input class="form-input" name="amount" type="number" step="0.01" value="${s.amount || ''}" required>
        </div>
        <div>
          <label class="form-label">Frequency *</label>
          <select class="form-input" name="frequency">
            <option value="monthly" ${(!s.frequency || s.frequency === 'monthly') ? 'selected' : ''}>Monthly</option>
            <option value="annual" ${s.frequency === 'annual' ? 'selected' : ''}>Annual</option>
            <option value="weekly" ${s.frequency === 'weekly' ? 'selected' : ''}>Weekly</option>
            <option value="fortnightly" ${s.frequency === 'fortnightly' ? 'selected' : ''}>Fortnightly</option>
            <option value="quarterly" ${s.frequency === 'quarterly' ? 'selected' : ''}>Quarterly</option>
            <option value="termly" ${s.frequency === 'termly' ? 'selected' : ''}>Termly</option>
          </select>
        </div>
        <div>
          <label class="form-label">Billing Day</label>
          <input class="form-input" name="billing_day" type="number" min="1" max="31" value="${s.billing_day || ''}">
        </div>
        <div>
          <label class="form-label">Status</label>
          <select class="form-input" name="status">
            <option value="active" ${(!s.status || s.status === 'active') ? 'selected' : ''}>Active</option>
            <option value="paused" ${s.status === 'paused' ? 'selected' : ''}>Paused</option>
            <option value="cancelled" ${s.status === 'cancelled' ? 'selected' : ''}>Cancelled</option>
            <option value="trial" ${s.status === 'trial' ? 'selected' : ''}>Trial</option>
          </select>
        </div>
        <div>
          <label class="form-label">Payment Method</label>
          <input class="form-input" name="payment_method" value="${Utils.escapeHtml(s.payment_method || '')}">
        </div>
        <div>
          <label class="form-label">Bank Pattern</label>
          <input class="form-input" name="bank_description_pattern" value="${Utils.escapeHtml(s.bank_description_pattern || '')}" placeholder="e.g. PAYPAL *NETFLIX">
        </div>
        <div style="grid-column: 1 / -1;">
          <label class="form-label">Notes</label>
          <input class="form-input" name="notes" value="${Utils.escapeHtml(s.notes || '')}">
        </div>
      </form>
      <div style="margin-top: 16px; text-align: right;">
        <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
        <button class="btn btn-primary" onclick="SubscriptionsView.saveSub(${isEdit ? `'${s.id}'` : 'null'})" style="margin-left: 8px;">
          ${isEdit ? 'Update' : 'Create'}
        </button>
      </div>`
    );
  },

  async saveSub(id) {
    const form = document.getElementById('sub-form');
    if (!form) return;

    const data = {};
    new FormData(form).forEach((val, key) => {
      if (val !== '') {
        data[key] = key === 'amount' ? parseFloat(val)
          : key === 'billing_day' ? parseInt(val)
          : val;
      }
    });

    if (!data.name || !data.amount) {
      Toast.error('Error', 'Name and amount are required');
      return;
    }

    try {
      if (id) {
        await API.put(`/api/subscriptions/${id}`, data);
        Toast.success('Updated', `${data.name} updated`);
      } else {
        await API.post('/api/subscriptions', data);
        Toast.success('Created', `${data.name} added`);
      }
      Modal.close();
      await this.loadData();
    } catch (error) {
      Toast.error('Error', error.message || 'Failed to save');
    }
  },

  editSub(id) {
    if (!this._data) return;
    const sub = this._data.subscriptions.find(s => s.id === id);
    if (sub) this.showAddModal(sub);
  },

  async deleteSub(id, name) {
    if (!confirm(`Delete subscription "${name}"?`)) return;

    try {
      await API.delete(`/api/subscriptions/${id}`);
      Toast.success('Deleted', `${name} removed`);
      await this.loadData();
    } catch (error) {
      Toast.error('Error', error.message || 'Failed to delete');
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Subscriptions data updated');
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
    Router.register('/knowledge', KnowledgeView);
    // ApiExplorerView is defined in api-explorer.js which may load after this
    if (typeof ApiExplorerView !== 'undefined') {
      Router.register('/api-explorer', ApiExplorerView);
    }
    Router.register('/costs', CostsView);
    Router.register('/tasks', TasksView);
    Router.register('/meal-plan', MealPlanView);
    Router.register('/goals', GoalsView);
    Router.register('/subscriptions', SubscriptionsView);
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
        Router.navigate('/knowledge');
      } else if (shortcutBuffer === 'gc') {
        Router.navigate('/costs');
      } else if (shortcutBuffer === 'gp') {
        Router.navigate('/subscriptions');
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
window.KnowledgeView = KnowledgeView;
window.CostsView = CostsView;
window.MealPlanView = MealPlanView;
window.GoalsView = GoalsView;
window.SubscriptionsView = SubscriptionsView;
// ApiExplorerView is defined in api-explorer.js
window.SettingsView = SettingsView;
