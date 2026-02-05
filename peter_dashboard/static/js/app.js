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

  handleMessage(data) {
    const { type, payload } = data;
    State.set({ lastUpdate: new Date().toISOString() });

    // Call registered handlers
    if (this.handlers[type]) {
      this.handlers[type].forEach(handler => handler(payload));
    }

    // Handle common message types
    switch (type) {
      case 'status':
        State.set({ services: payload.services });
        break;
      case 'job_complete':
      case 'job_start':
        this.refreshJobs();
        break;
      case 'error_alert':
        Toast.error('Error', payload.message || 'An error occurred');
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
                ${columns.map(col => `
                  <th class="${col.sortable ? 'sortable' : ''}"
                      ${col.sortable ? `onclick="DataTable.sort('${tableId}', '${col.key}')"` : ''}
                      style="${col.width ? `width: ${col.width}` : ''}">
                    ${col.label}
                    ${col.sortable ? `<span class="sort-icon">${Icons.sort}</span>` : ''}
                  </th>
                `).join('')}
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
    console.log('Sort by:', key);
    // Implementation would sort the data and re-render
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
 * Jobs View - Schedule monitor with data table
 */
const JobsView = {
  title: 'Jobs',
  jobs: [],

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Scheduled Jobs</h2>
            <p class="text-secondary">Monitor and manage scheduled tasks</p>
          </div>
          <button class="btn btn-primary" onclick="JobsView.refresh()">
            ${Icons.refresh} Refresh
          </button>
        </div>

        <div id="jobs-table">
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
      this.renderTable();
    } catch (error) {
      console.error('Failed to load jobs:', error);
      document.getElementById('jobs-table').innerHTML = `
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

  renderTable() {
    const filter = State.get('jobFilter');
    const search = State.get('searchQuery');

    let filteredJobs = this.jobs;

    // Apply status filter
    if (filter && filter !== 'all') {
      filteredJobs = filteredJobs.filter(j => j.status === filter);
    }

    // Apply search filter
    if (search) {
      filteredJobs = filteredJobs.filter(j =>
        (j.name || j.id || '').toLowerCase().includes(search) ||
        (j.skill || '').toLowerCase().includes(search)
      );
    }

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
      { key: 'success_rate_24h', label: 'Success Rate', sortable: true,
        render: (val) => val !== undefined ? `${val}%` : '-' },
      { key: 'enabled', label: 'Enabled', width: '80px',
        render: (val) => `
          <button class="btn btn-sm btn-ghost" onclick="JobsView.toggleJob(event)">
            ${val !== false ? Icons.toggleOn : Icons.toggleOff}
          </button>
        ` },
    ];

    const tableHtml = Components.dataTable({
      id: 'jobs-data-table',
      columns,
      data: filteredJobs,
      onRowClick: 'JobsView.selectJob',
    });

    document.getElementById('jobs-table').innerHTML = tableHtml;
  },

  selectJob(index) {
    const job = this.jobs[index];
    if (!job) return;

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
 */
const ServicesView = {
  title: 'Services',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>System Services</h2>
            <p class="text-secondary">Monitor and control system services</p>
          </div>
          <div class="flex gap-sm">
            <button class="btn btn-secondary" onclick="ServicesView.refresh()">
              ${Icons.refresh} Refresh
            </button>
            <button class="btn btn-primary" onclick="ServicesView.restartAll()">
              ${Icons.refreshCw} Restart All
            </button>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-md" id="services-list">
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
      const status = await API.get('/api/status');
      this.renderServices(status.services, status.tmux_sessions);
    } catch (error) {
      console.error('Failed to load services:', error);
      Toast.error('Error', 'Failed to load service status');
    }
  },

  renderServices(services, tmuxSessions) {
    const serviceInfo = {
      hadley_api: { name: 'Hadley API', icon: Icons.server, port: 8100, managed: 'NSSM' },
      discord_bot: { name: 'Discord Bot', icon: Icons.messageCircle, managed: 'NSSM' },
      claude_mem: { name: 'Claude Memory', icon: Icons.brain, port: 37777, managed: 'Systemd' },
      peterbot_session: { name: 'Peterbot Session', icon: Icons.terminal, managed: 'tmux' },
      hadley_bricks: { name: 'Hadley Bricks', icon: Icons.box, port: 3000, managed: 'NSSM' },
    };

    const html = Object.entries(services).map(([key, svc]) => {
      const info = serviceInfo[key] || { name: key, icon: Icons.server };
      const details = [];

      if (info.port) details.push({ label: 'Port', value: info.port });
      if (svc.pid) details.push({ label: 'PID', value: svc.pid });
      if (svc.latency_ms) details.push({ label: 'Latency', value: `${svc.latency_ms}ms` });
      if (info.managed) details.push({ label: 'Managed by', value: info.managed });
      if (svc.attached !== undefined) details.push({ label: 'Attached', value: svc.attached ? 'Yes' : 'No' });

      return `
        <div class="service-card">
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
          <div class="service-card-actions">
            <button class="btn btn-sm btn-secondary" onclick="ServicesView.restart('${key}')">
              ${Icons.refreshCw} Restart
            </button>
            <button class="btn btn-sm btn-danger" onclick="ServicesView.stop('${key}')">
              ${Icons.square} Stop
            </button>
          </div>
        </div>
      `;
    }).join('');

    document.getElementById('services-list').innerHTML = html;
  },

  async restart(service) {
    try {
      await API.post(`/api/restart/${service}`);
      Toast.success('Restarting', `${Format.serviceName(service)} is restarting`);
      setTimeout(() => this.loadData(), 2000);
    } catch (error) {
      Toast.error('Error', `Failed to restart: ${error.message}`);
    }
  },

  async stop(service) {
    if (!confirm(`Are you sure you want to stop ${Format.serviceName(service)}?`)) return;

    try {
      await API.post(`/api/stop/${service}`);
      Toast.success('Stopped', `${Format.serviceName(service)} has been stopped`);
      setTimeout(() => this.loadData(), 1000);
    } catch (error) {
      Toast.error('Error', `Failed to stop: ${error.message}`);
    }
  },

  async restartAll() {
    if (!confirm('Are you sure you want to restart all services?')) return;

    try {
      await API.post('/api/restart-all');
      Toast.success('Restarting', 'All services are restarting');
      setTimeout(() => this.loadData(), 3000);
    } catch (error) {
      Toast.error('Error', `Failed to restart: ${error.message}`);
    }
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Service status updated');
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
      const skill = await API.get(`/api/skill/${skillName}`);

      const content = `
        <h3 class="mb-md">${skillName}</h3>
        <div class="code-block">${Utils.escapeHtml(skill.content || 'No content available')}</div>
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
              <input type="text" placeholder="Search logs..."
                     oninput="LogsView.search(this.value)">
            </div>
            <div class="data-table-filters">
              <select class="form-select" onchange="LogsView.filterSource(this.value)">
                <option value="all">All Sources</option>
                <option value="bot">Bot</option>
                <option value="api">API</option>
                <option value="scheduler">Scheduler</option>
              </select>
              <select class="form-select" onchange="LogsView.filterLevel(this.value)">
                <option value="all">All Levels</option>
                <option value="debug">Debug</option>
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="error">Error</option>
              </select>
            </div>
          </div>
          <div class="card-body p-0" id="logs-container" style="max-height: 600px; overflow-y: auto;">
            ${Components.skeleton('text', 10)}
          </div>
        </div>
      </div>
    `;

    await this.loadData();
  },

  async loadData() {
    try {
      const data = await API.get('/api/logs/bot?lines=100');
      // Parse log lines into structured data
      this.logs = this.parseLogs(data.content || data.logs || '');
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

  parseLogs(content) {
    if (typeof content !== 'string') return [];

    return content.split('\n')
      .filter(line => line.trim())
      .map(line => {
        // Try to parse structured log format
        const match = line.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[(\w+)\]\s+\[(\w+)\]\s+(.*)$/);
        if (match) {
          return {
            timestamp: match[1],
            level: match[2].toLowerCase(),
            source: match[3].toLowerCase(),
            message: match[4]
          };
        }
        return {
          timestamp: new Date().toISOString(),
          level: 'info',
          source: 'unknown',
          message: line
        };
      });
  },

  renderLogs(logs) {
    const container = document.getElementById('logs-container');

    if (!logs.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">${Icons.fileText}</div>
          <div class="empty-state-title">No logs</div>
        </div>
      `;
      return;
    }

    container.innerHTML = logs.map(log => Components.logEntry(log)).join('');
  },

  search(query) {
    const filtered = this.logs.filter(log =>
      log.message.toLowerCase().includes(query.toLowerCase())
    );
    this.renderLogs(filtered);
  },

  filterSource(source) {
    const filtered = source === 'all'
      ? this.logs
      : this.logs.filter(log => log.source === source);
    this.renderLogs(filtered);
  },

  filterLevel(level) {
    const filtered = level === 'all'
      ? this.logs
      : this.logs.filter(log => log.level === level);
    this.renderLogs(filtered);
  },

  async refresh() {
    await this.loadData();
    Toast.info('Refreshed', 'Logs updated');
  },
};


/**
 * Files View - Configuration file browser
 */
const FilesView = {
  title: 'Files',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Configuration Files</h2>
            <p class="text-secondary">View and edit configuration files</p>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-md">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Files</h3>
            </div>
            <div class="card-body p-0" id="file-list">
              ${Components.skeleton('text', 8)}
            </div>
          </div>

          <div class="col-span-3 card">
            <div class="card-header">
              <h3 class="card-title" id="file-name">Select a file</h3>
              <div class="flex gap-sm">
                <button class="btn btn-sm btn-secondary" id="btn-save" disabled onclick="FilesView.save()">
                  ${Icons.save} Save
                </button>
              </div>
            </div>
            <div class="card-body">
              <div id="file-content" class="code-block" style="min-height: 400px;">
                Select a file from the list to view its contents.
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    await this.loadFiles();
  },

  async loadFiles() {
    try {
      const data = await API.get('/api/files');
      const files = data.files || data || [];
      this.renderFileList(files);
    } catch (error) {
      console.error('Failed to load files:', error);
      document.getElementById('file-list').innerHTML = `
        <div class="p-md text-muted">Failed to load files</div>
      `;
    }
  },

  renderFileList(files) {
    // Group files by type
    const windowsFiles = files.filter(f => f.type === 'windows' || !f.type);
    const wslFiles = files.filter(f => f.type === 'wsl');

    const html = `
      <div class="p-sm">
        <div class="text-xs font-semibold text-muted mb-sm">WINDOWS FILES</div>
        ${windowsFiles.map(f => `
          <div class="sidebar-item" onclick="FilesView.loadFile('${f.name}', '${f.type || 'windows'}')">
            <span class="sidebar-item-icon">${Icons.file}</span>
            <span class="sidebar-item-label">${f.name}</span>
          </div>
        `).join('')}

        ${wslFiles.length ? `
          <div class="text-xs font-semibold text-muted mt-md mb-sm">WSL FILES</div>
          ${wslFiles.map(f => `
            <div class="sidebar-item" onclick="FilesView.loadFile('${f.name}', 'wsl')">
              <span class="sidebar-item-icon">${Icons.file}</span>
              <span class="sidebar-item-label">${f.name}</span>
            </div>
          `).join('')}
        ` : ''}
      </div>
    `;

    document.getElementById('file-list').innerHTML = html;
  },

  async loadFile(name, type) {
    try {
      const data = await API.get(`/api/file/${type}/${encodeURIComponent(name)}`);
      document.getElementById('file-name').textContent = name;
      document.getElementById('file-content').textContent = data.content || 'Empty file';
      document.getElementById('btn-save').disabled = false;
      this.currentFile = { name, type };
    } catch (error) {
      Toast.error('Error', `Failed to load file: ${error.message}`);
    }
  },

  async save() {
    if (!this.currentFile) return;
    Toast.info('Info', 'Save functionality coming soon');
  },
};


/**
 * Memory View - Memory browser and search
 */
const MemoryView = {
  title: 'Memory',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Memory Systems</h2>
            <p class="text-secondary">Browse and search memory observations</p>
          </div>
        </div>

        ${Components.tabs({
          id: 'memory-tabs',
          tabs: [
            { label: 'Peterbot Memory', content: this.renderPeterbotMemory() },
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
          <input type="text" placeholder="Search memory..."
                 id="memory-search" onkeyup="if(event.key==='Enter')MemoryView.search(this.value)">
        </div>
      </div>
      <div id="memory-results">
        <p class="text-muted">Enter a search query to find memories</p>
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
    // Load recent memories
    try {
      const data = await API.get('/api/memory/recent');
      // Render recent observations
    } catch (error) {
      console.log('Memory API not available');
    }
  },

  async search(query) {
    if (!query.trim()) return;

    try {
      const results = await API.get(`/api/search/memory?q=${encodeURIComponent(query)}`);
      this.renderResults('memory-results', results.results || []);
    } catch (error) {
      Toast.error('Error', `Search failed: ${error.message}`);
    }
  },

  async searchBrain(query) {
    if (!query.trim()) return;

    try {
      const results = await API.get(`/api/search/second-brain?q=${encodeURIComponent(query)}`);
      this.renderResults('brain-results', results.results || []);
    } catch (error) {
      Toast.error('Error', `Search failed: ${error.message}`);
    }
  },

  renderResults(containerId, results) {
    const container = document.getElementById(containerId);
    if (!results.length) {
      container.innerHTML = '<p class="text-muted">No results found</p>';
      return;
    }

    container.innerHTML = results.map(r => `
      <div class="card mb-sm">
        <div class="card-body">
          <div class="flex justify-between items-center mb-sm">
            <span class="text-xs text-muted">#${r.id || '-'}</span>
            <span class="text-xs text-muted">${Format.datetime(r.timestamp || r.created_at)}</span>
          </div>
          <p>${Utils.escapeHtml(r.content || r.text || '')}</p>
        </div>
      </div>
    `).join('');
  },
};


/**
 * API Explorer View
 */
const ApiExplorerView = {
  title: 'API Explorer',

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>API Explorer</h2>
            <p class="text-secondary">Browse and test Hadley API endpoints</p>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-md">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">Endpoints</h3>
            </div>
            <div class="card-body p-0" id="endpoint-list" style="max-height: 600px; overflow-y: auto;">
              ${Components.skeleton('text', 15)}
            </div>
          </div>

          <div class="col-span-3 card">
            <div class="card-header">
              <h3 class="card-title" id="endpoint-title">Select an endpoint</h3>
              <button class="btn btn-primary" id="btn-try" disabled onclick="ApiExplorerView.tryEndpoint()">
                ${Icons.play} Try It
              </button>
            </div>
            <div class="card-body">
              <div id="endpoint-details">
                Select an endpoint from the list to view details.
              </div>
              <div id="endpoint-response" class="mt-lg hidden">
                <h4 class="mb-sm">Response</h4>
                <div class="code-block" id="response-content"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    await this.loadEndpoints();
  },

  async loadEndpoints() {
    try {
      const data = await API.get('/api/hadley/endpoints');
      this.endpoints = data.endpoints || data || [];
      this.renderEndpoints();
    } catch (error) {
      console.error('Failed to load endpoints:', error);
      document.getElementById('endpoint-list').innerHTML = `
        <div class="p-md text-muted">Failed to load endpoints</div>
      `;
    }
  },

  renderEndpoints() {
    // Group by category
    const grouped = {};
    this.endpoints.forEach(ep => {
      const category = ep.category || 'Other';
      if (!grouped[category]) grouped[category] = [];
      grouped[category].push(ep);
    });

    const html = Object.entries(grouped).map(([category, endpoints]) => `
      <div class="p-sm">
        <div class="text-xs font-semibold text-muted mb-sm">${category.toUpperCase()}</div>
        ${endpoints.map(ep => `
          <div class="sidebar-item" onclick="ApiExplorerView.selectEndpoint('${ep.method}', '${ep.path}')">
            <span class="text-xs font-mono ${ep.method === 'GET' ? 'text-success' : 'text-warning'}">${ep.method}</span>
            <span class="sidebar-item-label text-sm">${ep.path}</span>
          </div>
        `).join('')}
      </div>
    `).join('');

    document.getElementById('endpoint-list').innerHTML = html;
  },

  selectEndpoint(method, path) {
    this.currentEndpoint = { method, path };

    document.getElementById('endpoint-title').textContent = `${method} ${path}`;
    document.getElementById('btn-try').disabled = false;
    document.getElementById('endpoint-response').classList.add('hidden');

    document.getElementById('endpoint-details').innerHTML = `
      <div class="mb-md">
        <span class="status-badge ${method === 'GET' ? 'running' : 'paused'}">${method}</span>
        <span class="font-mono ml-sm">${path}</span>
      </div>
      <p class="text-muted">Click "Try It" to test this endpoint</p>
    `;
  },

  async tryEndpoint() {
    if (!this.currentEndpoint) return;

    const { method, path } = this.currentEndpoint;
    const responseDiv = document.getElementById('endpoint-response');
    const responseContent = document.getElementById('response-content');

    try {
      responseDiv.classList.remove('hidden');
      responseContent.textContent = 'Loading...';

      // Call through Hadley API
      const apiPath = path.startsWith('/') ? path : `/${path}`;
      const response = await fetch(`http://localhost:8100${apiPath}`, { method });
      const data = await response.json();

      responseContent.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      responseContent.textContent = `Error: ${error.message}`;
    }
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
};


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
  toggleOn: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="1" y="6" width="22" height="12" rx="6" fill="#22c55e"/><circle cx="17" cy="12" r="4" fill="white"/></svg>',
  toggleOff: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="1" y="6" width="22" height="12" rx="6" fill="#94a3b8"/><circle cx="7" cy="12" r="4" fill="white"/></svg>',

  // Toast types
  success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0d9488" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
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
    Router.register('/logs', LogsView);
    Router.register('/files', FilesView);
    Router.register('/memory', MemoryView);
    Router.register('/api-explorer', ApiExplorerView);
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
window.ApiExplorerView = ApiExplorerView;
window.SettingsView = SettingsView;
