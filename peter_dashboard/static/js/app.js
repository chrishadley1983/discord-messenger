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
 * Enhanced with detail panel, tmux viewer, health history, and control actions
 */
const ServicesView = {
  title: 'Services',

  // State
  services: {},
  tmuxSessions: [],
  selectedService: null,
  healthHistory: {},  // { serviceKey: [{ timestamp, status }] }
  screenRefreshInterval: null,
  autoRefreshInterval: null,

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

    // Load data and start auto-refresh
    await this.loadData();
    this.startAutoRefresh();
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
      const status = await API.get('/api/status');
      this.services = status.services || {};
      this.tmuxSessions = status.tmux_sessions || [];

      // Record health history
      this.recordHealthHistory();

      this.renderServices();

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

  recordHealthHistory() {
    const now = Date.now();
    Object.entries(this.services).forEach(([key, svc]) => {
      if (!this.healthHistory[key]) {
        this.healthHistory[key] = [];
      }

      const status = svc.status === 'up' || svc.status === 'running' ? 'healthy' : 'unhealthy';
      this.healthHistory[key].push({ timestamp: now, status });

      // Keep only last 24 hours (assuming 30s intervals = 2880 records max)
      // But for display we only show last ~24 blocks
      if (this.healthHistory[key].length > 2880) {
        this.healthHistory[key] = this.healthHistory[key].slice(-2880);
      }
    });
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

    if (!info || !info.port) {
      container.innerHTML = '<div class="text-muted">No health endpoint configured</div>';
      return;
    }

    // Display recent health status
    const history = this.healthHistory[serviceKey] || [];
    const recentChecks = history.slice(-10).reverse();

    if (recentChecks.length === 0) {
      container.innerHTML = '<div class="text-muted">No health check history available</div>';
      return;
    }

    container.innerHTML = `
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
    Modal.close();

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
