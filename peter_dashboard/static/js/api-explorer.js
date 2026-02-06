/**
 * API Explorer View - Interactive API documentation and testing
 *
 * Features:
 * - Categorized endpoint sidebar with counts
 * - Endpoint details with parameters table
 * - Try It Out for safe GET endpoints only
 * - cURL command generation and copy
 * - Search across all endpoints
 * - Favorites system with localStorage persistence
 */
const ApiExplorerView = {
  title: 'API Explorer',
  endpoints: [],
  openApiSpec: null,
  currentEndpoint: null,
  selectedCategory: null,
  searchQuery: '',
  favorites: JSON.parse(localStorage.getItem('apiExplorerFavorites') || '[]'),
  lastResponse: null,

  categoryMap: {
    '/gmail': { name: 'Gmail', icon: Icons.messageCircle, color: '#ea4335' },
    '/calendar': { name: 'Calendar', icon: Icons.clock, color: '#4285f4' },
    '/drive': { name: 'Drive', icon: Icons.folder, color: '#0f9d58' },
    '/tasks': { name: 'Tasks', icon: Icons.checkCircle, color: '#fbbc04' },
    '/contacts': { name: 'Contacts', icon: Icons.book, color: '#673ab7' },
    '/notion': { name: 'Notion', icon: Icons.book, color: '#000000' },
    '/nutrition': { name: 'Nutrition', icon: Icons.activity, color: '#4caf50' },
    '/weather': { name: 'Weather', icon: Icons.activity, color: '#03a9f4' },
    '/traffic': { name: 'Traffic', icon: Icons.activity, color: '#ff5722' },
    '/directions': { name: 'Directions', icon: Icons.activity, color: '#ff5722' },
    '/places': { name: 'Places', icon: Icons.activity, color: '#795548' },
    '/ev': { name: 'Electric Vehicle', icon: Icons.zap, color: '#00bcd4' },
    '/kia': { name: 'Kia Connect', icon: Icons.activity, color: '#05141f' },
    '/ring': { name: 'Ring', icon: Icons.bell, color: '#1c9ad6' },
    '/hb': { name: 'Hadley Bricks', icon: Icons.box, color: '#ff9800' },
    '/sheets': { name: 'Sheets', icon: Icons.fileText, color: '#0f9d58' },
    '/docs': { name: 'Docs', icon: Icons.fileText, color: '#4285f4' },
    '/whatsapp': { name: 'WhatsApp', icon: Icons.messageCircle, color: '#25d366' },
    '/reminders': { name: 'Reminders', icon: Icons.bell, color: '#9c27b0' },
    '/brain': { name: 'Second Brain', icon: Icons.brain, color: '#607d8b' },
    '/browser': { name: 'Browser', icon: Icons.terminal, color: '#3f51b5' },
    '/ptasks': { name: 'Peterbot Tasks', icon: Icons.list, color: '#e91e63' },
  },

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in api-explorer">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>API Explorer</h2>
            <p class="text-secondary">Browse, test, and explore Hadley API endpoints</p>
          </div>
          <div class="flex gap-sm items-center">
            <div class="data-table-search" style="width: 300px;">
              <span class="data-table-search-icon">${Icons.search}</span>
              <input type="text" id="api-search" placeholder="Search endpoints..." oninput="ApiExplorerView.handleSearch(this.value)">
            </div>
            <button class="btn btn-secondary" onclick="ApiExplorerView.refresh()">${Icons.refresh} Refresh</button>
          </div>
        </div>
        <div class="api-explorer-layout">
          <div class="card api-categories-panel">
            <div class="card-header"><h3 class="card-title">Categories</h3></div>
            <div class="card-body p-0" id="categories-list">${Components.skeleton('text', 10)}</div>
          </div>
          <div class="card api-endpoints-panel">
            <div class="card-header">
              <h3 class="card-title" id="endpoints-title">Endpoints</h3>
              <span class="text-muted text-sm" id="endpoints-count"></span>
            </div>
            <div class="card-body p-0" id="endpoints-list" style="max-height: calc(100vh - 300px); overflow-y: auto;">
              <div class="p-md text-muted text-center">Select a category to view endpoints</div>
            </div>
          </div>
          <div class="card api-detail-panel">
            <div class="card-header">
              <h3 class="card-title" id="detail-title">Select an endpoint</h3>
              <div class="flex gap-sm">
                <button class="btn btn-sm btn-ghost" id="btn-favorite" onclick="ApiExplorerView.toggleFavorite()" title="Toggle favorite">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                </button>
                <button class="btn btn-sm btn-secondary" id="btn-curl" disabled onclick="ApiExplorerView.copyCurl()" title="Copy cURL command">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> cURL
                </button>
              </div>
            </div>
            <div class="card-body" id="detail-content" style="max-height: calc(100vh - 300px); overflow-y: auto;">
              <div class="empty-state">
                <div class="empty-state-icon">${Icons.code}</div>
                <div class="empty-state-title">No endpoint selected</div>
                <div class="empty-state-description">Select an endpoint from the list to view its details and test it</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <style>
        .api-explorer-layout { display: grid; grid-template-columns: 200px 320px 1fr; gap: 16px; height: calc(100vh - 220px); }
        .api-categories-panel, .api-endpoints-panel, .api-detail-panel { display: flex; flex-direction: column; height: 100%; }
        .api-categories-panel .card-body, .api-endpoints-panel .card-body, .api-detail-panel .card-body { flex: 1; overflow-y: auto; }
        .api-category-item { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer; border-bottom: 1px solid var(--border-color); transition: background-color 0.15s; }
        .api-category-item:hover { background-color: var(--hover-bg); }
        .api-category-item.active { background-color: var(--primary-bg); border-left: 3px solid var(--primary); }
        .api-category-icon { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 4px; flex-shrink: 0; }
        .api-category-icon svg { width: 14px; height: 14px; }
        .api-category-name { flex: 1; font-size: 13px; font-weight: 500; }
        .api-category-count { font-size: 11px; color: var(--text-muted); background: var(--bg-secondary); padding: 2px 6px; border-radius: 10px; }
        .api-endpoint-item { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; cursor: pointer; border-bottom: 1px solid var(--border-color); transition: background-color 0.15s; }
        .api-endpoint-item:hover { background-color: var(--hover-bg); }
        .api-endpoint-item.active { background-color: var(--primary-bg); }
        .api-method-badge { font-size: 10px; font-weight: 700; font-family: monospace; padding: 3px 6px; border-radius: 4px; text-transform: uppercase; flex-shrink: 0; }
        .api-method-badge.get { background: #dcfce7; color: #166534; }
        .api-method-badge.post { background: #dbeafe; color: #1e40af; }
        .api-method-badge.put { background: #fef3c7; color: #92400e; }
        .api-method-badge.delete { background: #fee2e2; color: #991b1b; }
        .api-method-badge.patch { background: #f3e8ff; color: #6b21a8; }
        .api-endpoint-info { flex: 1; min-width: 0; }
        .api-endpoint-path { font-family: monospace; font-size: 12px; word-break: break-all; }
        .api-endpoint-summary { font-size: 11px; color: var(--text-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .api-endpoint-star { color: var(--text-muted); opacity: 0; transition: opacity 0.15s; cursor: pointer; }
        .api-endpoint-item:hover .api-endpoint-star, .api-endpoint-star.favorited { opacity: 1; }
        .api-endpoint-star.favorited { color: #f59e0b; }
        .api-detail-section { margin-bottom: 24px; }
        .api-detail-section h4 { font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
        .api-params-table { width: 100%; font-size: 13px; }
        .api-params-table th { text-align: left; padding: 8px 12px; background: var(--bg-secondary); font-weight: 500; border-bottom: 1px solid var(--border-color); }
        .api-params-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
        .api-param-name { font-family: monospace; font-weight: 500; }
        .api-param-required { color: #ef4444; font-size: 10px; margin-left: 4px; }
        .api-param-type { font-size: 11px; color: var(--text-muted); background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; display: inline-block; margin-top: 2px; }
        .api-params-table td .api-param-type + .api-param-type { margin-left: 4px; }
        .api-try-section { background: var(--bg-secondary); border-radius: 8px; padding: 16px; }
        .api-response-body pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
        .api-try-input-group { margin-bottom: 12px; }
        .api-try-input-group label { display: block; font-size: 12px; font-weight: 500; margin-bottom: 4px; }
        .api-try-input-group input { width: 100%; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 13px; background: var(--bg-primary); }
        .api-response-section { margin-top: 16px; }
        .api-response-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
        .api-response-status { display: flex; align-items: center; gap: 12px; }
        .api-response-status-code { font-weight: 600; padding: 4px 8px; border-radius: 4px; }
        .api-response-status-code.success { background: #dcfce7; color: #166534; }
        .api-response-status-code.error { background: #fee2e2; color: #991b1b; }
        .api-response-time { font-size: 12px; color: var(--text-muted); }
        .api-response-body { background: var(--bg-tertiary, var(--bg-secondary)); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12px; line-height: 1.5; max-height: 400px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
        .api-warning-box { background: #fef3c7; border: 1px solid #fcd34d; border-radius: 6px; padding: 12px; margin-bottom: 16px; display: flex; align-items: flex-start; gap: 8px; color: #92400e; font-size: 13px; }
        .api-warning-box svg { flex-shrink: 0; color: #f59e0b; }
        @media (max-width: 1200px) { .api-explorer-layout { grid-template-columns: 180px 1fr; grid-template-rows: auto 1fr; } .api-detail-panel { grid-column: span 2; } }
      </style>
    `;
    await this.loadEndpoints();
  },

  async loadEndpoints() {
    try {
      const response = await fetch('/api/hadley/proxy/openapi.json');
      if (!response.ok) throw new Error('Failed to fetch OpenAPI spec: ' + response.status);
      this.openApiSpec = await response.json();
      this.endpoints = this.parseOpenApiSpec(this.openApiSpec);
      this.renderCategories();
      if (this.favorites.length > 0) this.showFavorites();
    } catch (error) {
      console.error('Failed to load endpoints:', error);
      document.getElementById('categories-list').innerHTML = '<div class="p-md text-center"><div class="text-muted mb-sm">Failed to load API endpoints</div><div class="text-sm text-muted">' + Utils.escapeHtml(error.message) + '</div><button class="btn btn-sm btn-primary mt-md" onclick="ApiExplorerView.loadEndpoints()">Retry</button></div>';
    }
  },

  /**
   * Resolve a $ref reference in the OpenAPI spec
   */
  resolveRef(ref, spec) {
    if (!ref || !ref.startsWith('#/')) return null;
    const parts = ref.slice(2).split('/');
    let current = spec;
    for (const part of parts) {
      if (!current || typeof current !== 'object') return null;
      current = current[part];
    }
    return current;
  },

  /**
   * Recursively resolve all $ref in a schema
   */
  resolveSchema(schema, spec, visited) {
    visited = visited || new Set();
    if (!schema) return null;

    // Handle $ref
    if (schema.$ref) {
      if (visited.has(schema.$ref)) return { type: 'object', description: '(circular reference)' };
      visited.add(schema.$ref);
      const resolved = this.resolveRef(schema.$ref, spec);
      if (resolved) return this.resolveSchema(resolved, spec, visited);
      return { type: 'unknown', description: schema.$ref.split('/').pop() };
    }

    // Handle anyOf (nullable types in Pydantic)
    if (schema.anyOf) {
      const nonNull = schema.anyOf.find(s => s.type !== 'null');
      if (nonNull) {
        const resolved = this.resolveSchema(nonNull, spec, visited);
        return { ...resolved, nullable: true, title: schema.title, description: schema.description || resolved.description };
      }
    }

    // Resolve nested properties
    if (schema.type === 'object' && schema.properties) {
      const resolvedProps = {};
      for (const [key, value] of Object.entries(schema.properties)) {
        resolvedProps[key] = this.resolveSchema(value, spec, visited);
      }
      return { ...schema, properties: resolvedProps };
    }

    // Resolve array items
    if (schema.type === 'array' && schema.items) {
      return { ...schema, items: this.resolveSchema(schema.items, spec, visited) };
    }

    return schema;
  },

  parseOpenApiSpec(spec) {
    const endpoints = [];
    const paths = spec.paths || {};
    for (const [path, methods] of Object.entries(paths)) {
      for (const [method, details] of Object.entries(methods)) {
        if (['get', 'post', 'put', 'delete', 'patch'].includes(method)) {
          let category = 'Other';
          for (const [prefix, catInfo] of Object.entries(this.categoryMap)) {
            if (path.startsWith(prefix)) { category = catInfo.name; break; }
          }
          const parameters = (details.parameters || []).map(p => ({
            name: p.name, in: p.in, required: p.required || false,
            type: p.schema?.type || 'string', description: p.description || '',
            default: p.schema?.default, enum: p.schema?.enum,
          }));
          let requestBody = null;
          if (details.requestBody?.content?.['application/json']) {
            const rawSchema = details.requestBody.content['application/json'].schema;
            requestBody = this.resolveSchema(rawSchema, spec);
          }
          let responseSchema = null;
          if (details.responses?.['200']?.content?.['application/json']) {
            const rawSchema = details.responses['200'].content['application/json'].schema;
            responseSchema = this.resolveSchema(rawSchema, spec);
          }
          endpoints.push({ path, method: method.toUpperCase(), summary: details.summary || '', description: details.description || '', category, tags: details.tags || [], parameters, requestBody, responseSchema, operationId: details.operationId || '' });
        }
      }
    }
    return endpoints.sort((a, b) => a.path.localeCompare(b.path));
  },

  renderCategories() {
    const categoryCounts = {};
    this.endpoints.forEach(ep => { categoryCounts[ep.category] = (categoryCounts[ep.category] || 0) + 1; });
    const categories = Object.entries(this.categoryMap).map(([prefix, info]) => ({ prefix, ...info, count: categoryCounts[info.name] || 0 })).filter(c => c.count > 0).sort((a, b) => a.name.localeCompare(b.name));
    const otherCount = categoryCounts['Other'] || 0;
    if (otherCount > 0) categories.push({ prefix: '', name: 'Other', icon: Icons.server, color: '#6b7280', count: otherCount });
    const totalCount = this.endpoints.length;
    let html = '<div class="api-category-item ' + (!this.selectedCategory ? 'active' : '') + '" onclick="ApiExplorerView.selectCategory(null)"><div class="api-category-icon" style="background:#6b728015;color:#6b7280;">' + Icons.list + '</div><span class="api-category-name">All Endpoints</span><span class="api-category-count">' + totalCount + '</span></div>';
    if (this.favorites.length > 0) {
      html += '<div class="api-category-item ' + (this.selectedCategory === 'favorites' ? 'active' : '') + '" onclick="ApiExplorerView.showFavorites()"><div class="api-category-icon" style="background:#fef3c7;color:#f59e0b;"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div><span class="api-category-name">Favorites</span><span class="api-category-count">' + this.favorites.length + '</span></div>';
    }
    html += categories.map(cat => '<div class="api-category-item ' + (this.selectedCategory === cat.name ? 'active' : '') + '" onclick="ApiExplorerView.selectCategory(\'' + cat.name + '\')"><div class="api-category-icon" style="background:' + cat.color + '15;color:' + cat.color + ';">' + cat.icon + '</div><span class="api-category-name">' + cat.name + '</span><span class="api-category-count">' + cat.count + '</span></div>').join('');
    document.getElementById('categories-list').innerHTML = html;
    if (!this.selectedCategory) this.renderEndpointsList(this.endpoints);
  },

  selectCategory(category) {
    this.selectedCategory = category;
    this.renderCategories();
    let filtered = category ? this.endpoints.filter(ep => ep.category === category) : this.endpoints;
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase();
      filtered = filtered.filter(ep => ep.path.toLowerCase().includes(q) || ep.summary.toLowerCase().includes(q) || ep.description.toLowerCase().includes(q));
    }
    document.getElementById('endpoints-title').textContent = category || 'All Endpoints';
    this.renderEndpointsList(filtered);
  },

  showFavorites() {
    this.selectedCategory = 'favorites';
    this.renderCategories();
    const favorited = this.endpoints.filter(ep => this.favorites.includes(ep.method + ':' + ep.path));
    document.getElementById('endpoints-title').textContent = 'Favorites';
    this.renderEndpointsList(favorited);
  },

  renderEndpointsList(endpoints) {
    document.getElementById('endpoints-count').textContent = endpoints.length + ' endpoint' + (endpoints.length !== 1 ? 's' : '');
    if (endpoints.length === 0) {
      document.getElementById('endpoints-list').innerHTML = '<div class="empty-state p-lg"><div class="empty-state-icon">' + Icons.search + '</div><div class="empty-state-title">No endpoints found</div><div class="empty-state-description">Try adjusting your search or selecting a different category</div></div>';
      return;
    }
    const self = this;
    const html = endpoints.map(function(ep) {
      const isFav = self.favorites.includes(ep.method + ':' + ep.path);
      const isActive = self.currentEndpoint && self.currentEndpoint.method === ep.method && self.currentEndpoint.path === ep.path;
      const escapedPath = Utils.escapeHtml(ep.path).replace(/'/g, "\\'");
      return '<div class="api-endpoint-item ' + (isActive ? 'active' : '') + '" onclick="ApiExplorerView.selectEndpoint(\'' + ep.method + "', '" + escapedPath + '\')"><span class="api-method-badge ' + ep.method.toLowerCase() + '">' + ep.method + '</span><div class="api-endpoint-info"><div class="api-endpoint-path">' + Utils.escapeHtml(ep.path) + '</div>' + (ep.summary ? '<div class="api-endpoint-summary">' + Utils.escapeHtml(ep.summary) + '</div>' : '') + '</div><span class="api-endpoint-star ' + (isFav ? 'favorited' : '') + '" onclick="event.stopPropagation(); ApiExplorerView.toggleFavoriteEndpoint(\'' + ep.method + "', '" + escapedPath + '\')"><svg width="14" height="14" viewBox="0 0 24 24" fill="' + (isFav ? 'currentColor' : 'none') + '" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></span></div>';
    }).join('');
    document.getElementById('endpoints-list').innerHTML = html;
  },

  selectEndpoint(method, path) {
    const endpoint = this.endpoints.find(ep => ep.method === method && ep.path === path);
    if (!endpoint) return;
    this.currentEndpoint = endpoint;
    const isFav = this.favorites.includes(method + ':' + path);
    document.getElementById('detail-title').textContent = method + ' ' + path;
    document.getElementById('btn-curl').disabled = false;
    document.getElementById('btn-favorite').innerHTML = isFav ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>' : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
    this.renderEndpointDetail(endpoint);
    if (this.selectedCategory === 'favorites') this.showFavorites();
    else this.selectCategory(this.selectedCategory);
  },

  renderEndpointDetail(endpoint) {
    const { method, path, summary, description, parameters, requestBody, responseSchema } = endpoint;
    const isGet = method === 'GET';
    const queryParams = parameters.filter(p => p.in === 'query');
    const pathParams = parameters.filter(p => p.in === 'path');

    // Header section
    let html = '<div class="api-detail-section">' +
      '<div class="flex items-center gap-sm mb-sm">' +
      '<span class="api-method-badge ' + method.toLowerCase() + '">' + method + '</span>' +
      '<code class="font-mono text-sm">' + Utils.escapeHtml(path) + '</code></div>' +
      (summary ? '<p class="text-sm">' + Utils.escapeHtml(summary) + '</p>' : '') +
      (description && description !== summary ? '<p class="text-sm text-muted mt-sm">' + Utils.escapeHtml(description) + '</p>' : '') +
      '</div>';

    // Path parameters
    if (pathParams.length > 0) {
      html += '<div class="api-detail-section"><h4>Path Parameters</h4>' +
        '<table class="api-params-table"><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead><tbody>' +
        pathParams.map(function(p) {
          return '<tr><td><span class="api-param-name">' + Utils.escapeHtml(p.name) + '</span>' +
            '<span class="api-param-required">*required</span></td>' +
            '<td><span class="api-param-type">' + Utils.escapeHtml(p.type) + '</span></td>' +
            '<td>' + (p.description ? Utils.escapeHtml(p.description) : '<span class="text-muted">-</span>') + '</td></tr>';
        }).join('') +
        '</tbody></table></div>';
    }

    // Query parameters
    if (queryParams.length > 0) {
      html += '<div class="api-detail-section"><h4>Query Parameters</h4>' +
        '<table class="api-params-table"><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead><tbody>' +
        queryParams.map(function(p) {
          return '<tr><td><span class="api-param-name">' + Utils.escapeHtml(p.name) + '</span>' +
            (p.required ? '<span class="api-param-required">*required</span>' : '') + '</td>' +
            '<td><span class="api-param-type">' + Utils.escapeHtml(p.type) + '</span></td>' +
            '<td>' + (p.description ? Utils.escapeHtml(p.description) : '<span class="text-muted">-</span>') +
            (p.default !== undefined ? '<br><span class="text-muted text-sm">Default: ' + p.default + '</span>' : '') +
            (p.enum ? '<br><span class="api-param-type">' + p.enum.join(' | ') + '</span>' : '') + '</td></tr>';
        }).join('') +
        '</tbody></table></div>';
    }

    // Request Body Schema (POST/PUT/PATCH)
    if (requestBody && ['POST', 'PUT', 'PATCH'].includes(method)) {
      html += '<div class="api-detail-section"><h4>Request Body Schema</h4>';
      if (requestBody.properties) {
        html += this.formatSchemaAsTable(requestBody);
      } else {
        html += '<div class="api-response-body">' + this.formatSchema(requestBody) + '</div>';
      }
      html += '</div>';

      // Request Body Example
      const exampleBody = this.generateExampleJson(requestBody);
      if (exampleBody) {
        html += '<div class="api-detail-section"><h4>Example Request Body</h4>' +
          '<div class="api-response-body" style="position: relative;">' +
          '<button class="btn btn-sm btn-ghost" onclick="ApiExplorerView.copyExample(\'request\')" ' +
          'style="position: absolute; top: 8px; right: 8px;" title="Copy example">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
          '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg></button>' +
          '<pre id="example-request-body" style="margin:0;">' + Utils.escapeHtml(JSON.stringify(exampleBody, null, 2)) + '</pre></div></div>';
      }
    }

    // Response Schema
    if (responseSchema && Object.keys(responseSchema).length > 0) {
      html += '<div class="api-detail-section"><h4>Response Schema (200 OK)</h4>';
      if (responseSchema.properties) {
        html += this.formatSchemaAsTable(responseSchema);
      } else if (responseSchema.type === 'array' && responseSchema.items && responseSchema.items.properties) {
        html += '<div class="text-sm text-muted mb-sm">Array of:</div>' + this.formatSchemaAsTable(responseSchema.items);
      } else {
        html += '<div class="api-response-body">' + this.formatSchema(responseSchema) + '</div>';
      }
      html += '</div>';

      // Response Example
      const exampleResponse = this.generateExampleJson(responseSchema);
      if (exampleResponse) {
        html += '<div class="api-detail-section"><h4>Example Response</h4>' +
          '<div class="api-response-body" style="position: relative;">' +
          '<button class="btn btn-sm btn-ghost" onclick="ApiExplorerView.copyExample(\'response\')" ' +
          'style="position: absolute; top: 8px; right: 8px;" title="Copy example">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
          '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg></button>' +
          '<pre id="example-response-body" style="margin:0;">' + Utils.escapeHtml(JSON.stringify(exampleResponse, null, 2)) + '</pre></div></div>';
      }
    }

    // Try It Out section (GET only)
    if (isGet) {
      html += '<div class="api-detail-section"><h4>Try It Out</h4>' +
        '<div class="api-warning-box">' + Icons.alertCircle +
        '<div><strong>Safety Notice:</strong> This will make a real API request to the Hadley API. Only GET endpoints are available for testing. Results may include personal data.</div></div>' +
        '<div class="api-try-section">';

      if (queryParams.length > 0) {
        html += '<div class="mb-md"><div class="text-sm font-medium mb-sm">Query Parameters</div>' +
          queryParams.map(function(p) {
            // Generate a helpful placeholder/default value
            let placeholder = p.default !== undefined ? String(p.default) : (p.description || p.name);
            let defaultVal = '';
            if (p.default !== undefined) {
              defaultVal = String(p.default);
            } else if (p.enum && p.enum.length > 0) {
              defaultVal = p.enum[0];
            }
            return '<div class="api-try-input-group"><label>' + Utils.escapeHtml(p.name) +
              (p.required ? '<span class="text-error">*</span>' : '') +
              ' <span class="text-muted text-xs">(' + p.type + ')</span></label>' +
              '<input type="text" id="param-' + p.name + '" placeholder="' + Utils.escapeHtml(placeholder) + '"' +
              (defaultVal ? ' value="' + Utils.escapeHtml(defaultVal) + '"' : '') + '></div>';
          }).join('') + '</div>';
      }

      html += '<button class="btn btn-primary" onclick="ApiExplorerView.executeRequest()">' + Icons.play + ' Send Request</button>' +
        '<div id="api-response-container" class="api-response-section" style="display:none;">' +
        '<div class="api-response-header"><div class="api-response-status">' +
        '<span class="api-response-status-code" id="response-status"></span>' +
        '<span class="api-response-time" id="response-time"></span></div>' +
        '<button class="btn btn-sm btn-secondary" onclick="ApiExplorerView.copyResponse()">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
        '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> Copy</button></div>' +
        '<div class="api-response-body" id="response-body"></div></div></div></div>';
    } else {
      // Non-GET endpoint testing section
      html += '<div class="api-detail-section"><h4>Testing</h4>' +
        '<div class="api-warning-box">' + Icons.alertCircle +
        '<div><strong>Note:</strong> ' + method + ' requests cannot be tested in the browser for safety. Use the "Copy cURL" button to test with a terminal.</div></div></div>';
    }

    document.getElementById('detail-content').innerHTML = html;
  },

  /**
   * Copy example JSON to clipboard
   */
  copyExample(type) {
    const elementId = type === 'request' ? 'example-request-body' : 'example-response-body';
    const el = document.getElementById(elementId);
    if (el) {
      navigator.clipboard.writeText(el.textContent)
        .then(function() { Toast.success('Copied', 'Example copied to clipboard'); })
        .catch(function() { Toast.error('Error', 'Failed to copy'); });
    }
  },

  /**
   * Format schema as a readable table with field info
   */
  formatSchemaAsTable(schema) {
    if (!schema || !schema.properties) {
      return '<div class="text-muted">No schema available</div>';
    }

    const required = schema.required || [];
    const rows = Object.entries(schema.properties).map(([key, prop]) => {
      const isRequired = required.includes(key);
      const typeStr = this.getTypeString(prop);
      const desc = prop.description || prop.title || '';
      const nullable = prop.nullable ? ' <span class="text-muted">(optional)</span>' : '';
      const enumVals = prop.enum ? '<br><span class="api-param-type">' + prop.enum.join(' | ') + '</span>' : '';

      return '<tr>' +
        '<td><span class="api-param-name">' + Utils.escapeHtml(key) + '</span>' +
        (isRequired ? '<span class="api-param-required">*required</span>' : '') + '</td>' +
        '<td><span class="api-param-type">' + Utils.escapeHtml(typeStr) + '</span>' + nullable + enumVals + '</td>' +
        '<td>' + (desc ? Utils.escapeHtml(desc) : '<span class="text-muted">-</span>') + '</td>' +
        '</tr>';
    }).join('');

    return '<table class="api-params-table"><thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead><tbody>' + rows + '</tbody></table>';
  },

  /**
   * Get a human-readable type string from a schema property
   */
  getTypeString(prop) {
    if (!prop) return 'any';
    if (prop.type === 'array' && prop.items) {
      return this.getTypeString(prop.items) + '[]';
    }
    if (prop.type === 'object' && prop.additionalProperties) {
      return 'object';
    }
    let t = prop.type || 'any';
    if (prop.format) t += ' (' + prop.format + ')';
    return t;
  },

  /**
   * Generate example JSON from schema
   */
  generateExampleJson(schema) {
    if (!schema) return null;

    if (schema.type === 'object' && schema.properties) {
      const obj = {};
      const required = schema.required || [];
      for (const [key, value] of Object.entries(schema.properties)) {
        // Include required fields and a sampling of optional fields
        if (required.includes(key) || Object.keys(schema.properties).length <= 6) {
          obj[key] = this.generateSampleValue(value);
        }
      }
      return obj;
    }

    if (schema.type === 'array' && schema.items) {
      return [this.generateExampleJson(schema.items)];
    }

    return this.generateSampleValue(schema);
  },

  formatSchema(schema, indent) {
    indent = indent || 0;
    if (!schema) return 'null';
    const spaces = '  '.repeat(indent);
    if (schema.type === 'object' && schema.properties) {
      const self = this;
      const props = Object.entries(schema.properties).map(function([key, value]) {
        const required = (schema.required || []).includes(key) ? ' // required' : '';
        return spaces + '  "' + key + '": ' + self.formatSchema(value, indent + 1) + required;
      }).join(',\n');
      return '{\n' + props + '\n' + spaces + '}';
    }
    if (schema.type === 'array' && schema.items) return '[' + this.formatSchema(schema.items, indent) + ']';
    if (schema.type) {
      let t = schema.type;
      if (schema.format) t += ' (' + schema.format + ')';
      if (schema.enum) t += ' [' + schema.enum.join('|') + ']';
      return '<' + t + '>';
    }
    if (schema.$ref) return '<' + schema.$ref.split('/').pop() + '>';
    return JSON.stringify(schema);
  },

  async executeRequest() {
    if (!this.currentEndpoint || this.currentEndpoint.method !== 'GET') return;
    const { path, parameters } = this.currentEndpoint;
    const queryParams = parameters.filter(p => p.in === 'query');
    let url = '/api/hadley/proxy' + path;
    const params = new URLSearchParams();
    queryParams.forEach(function(p) { const inp = document.getElementById('param-' + p.name); if (inp && inp.value) params.append(p.name, inp.value); });
    const qs = params.toString();
    if (qs) url += '?' + qs;
    const container = document.getElementById('api-response-container');
    const statusEl = document.getElementById('response-status');
    const timeEl = document.getElementById('response-time');
    const bodyEl = document.getElementById('response-body');
    container.style.display = 'block';
    statusEl.textContent = 'Loading...';
    statusEl.className = 'api-response-status-code';
    timeEl.textContent = '';
    bodyEl.textContent = 'Sending request...';
    const start = performance.now();
    try {
      const response = await fetch(url);
      const dur = Math.round(performance.now() - start);
      const data = await response.json();
      statusEl.textContent = response.status + ' ' + response.statusText;
      statusEl.className = 'api-response-status-code ' + (response.ok ? 'success' : 'error');
      timeEl.textContent = dur + 'ms';
      bodyEl.textContent = JSON.stringify(data, null, 2);
      this.lastResponse = data;
    } catch (error) {
      const dur = Math.round(performance.now() - start);
      statusEl.textContent = 'Error';
      statusEl.className = 'api-response-status-code error';
      timeEl.textContent = dur + 'ms';
      bodyEl.textContent = 'Error: ' + error.message;
      this.lastResponse = null;
    }
  },

  copyResponse() {
    if (this.lastResponse) {
      navigator.clipboard.writeText(JSON.stringify(this.lastResponse, null, 2)).then(function() { Toast.success('Copied', 'Response copied to clipboard'); }).catch(function() { Toast.error('Error', 'Failed to copy response'); });
    }
  },

  copyCurl() {
    if (!this.currentEndpoint) return;
    const { method, path, parameters, requestBody } = this.currentEndpoint;
    const queryParams = parameters.filter(p => p.in === 'query');
    let url = '/api/hadley/proxy' + path;
    if (method === 'GET' && queryParams.length > 0) {
      const params = [];
      queryParams.forEach(function(p) {
        const inp = document.getElementById('param-' + p.name);
        if (inp && inp.value) params.push(encodeURIComponent(p.name) + '=' + encodeURIComponent(inp.value));
        else if (p.required) params.push(encodeURIComponent(p.name) + '=<' + p.type + '>');
      });
      if (params.length > 0) url += '?' + params.join('&');
    }
    let curl = 'curl -X ' + method + ' "' + url + '"';
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      curl += ' \\\n  -H "Content-Type: application/json"';
      if (requestBody) curl += " \\\n  -d '" + JSON.stringify(this.generateSampleBody(requestBody)) + "'";
    }
    navigator.clipboard.writeText(curl).then(function() { Toast.success('Copied', 'cURL command copied to clipboard'); }).catch(function() { Toast.error('Error', 'Failed to copy cURL command'); });
  },

  generateSampleBody(schema) {
    if (!schema) return {};
    if (schema.type === 'object' && schema.properties) {
      const obj = {};
      for (const [key, value] of Object.entries(schema.properties)) obj[key] = this.generateSampleValue(value);
      return obj;
    }
    return this.generateSampleValue(schema);
  },

  generateSampleValue(schema) {
    if (!schema) return null;
    if (schema.example !== undefined) return schema.example;
    if (schema.default !== undefined) return schema.default;
    if (schema.enum) return schema.enum[0];

    // Handle nullable types (anyOf with null)
    if (schema.anyOf) {
      const nonNull = schema.anyOf.find(s => s.type !== 'null');
      if (nonNull) return this.generateSampleValue(nonNull);
    }

    // Generate contextual example based on field name/title
    const fieldName = (schema.title || '').toLowerCase();
    const fieldDesc = (schema.description || '').toLowerCase();

    switch (schema.type) {
      case 'string':
        // Format-based examples
        if (schema.format === 'date') return '2026-02-05';
        if (schema.format === 'date-time') return '2026-02-05T10:00:00Z';
        if (schema.format === 'email') return 'user@example.com';
        if (schema.format === 'uri' || schema.format === 'url') return 'https://example.com';

        // Name-based examples for common fields
        if (fieldName.includes('title') || fieldName.includes('name')) return 'Example Title';
        if (fieldName.includes('description')) return 'A brief description';
        if (fieldName.includes('task') || fieldName.includes('message')) return 'Complete the task';
        if (fieldName.includes('id')) return 'abc123';
        if (fieldName.includes('email')) return 'user@example.com';
        if (fieldName.includes('url') || fieldName.includes('link')) return 'https://example.com';
        if (fieldName.includes('date')) return '2026-02-05';
        if (fieldName.includes('session')) return 'sess_12345';
        if (fieldName.includes('action')) return 'navigate';
        if (fieldName.includes('source')) return 'Vinted';
        if (fieldName.includes('reference')) return 'REF-001';
        if (fieldName.includes('method') || fieldName.includes('payment')) return 'PayPal';
        if (fieldName.includes('priority')) return 'high';

        return 'string';

      case 'integer':
        if (fieldName.includes('id') || fieldName.includes('user') || fieldName.includes('channel')) return 123456789;
        if (fieldName.includes('count') || fieldName.includes('limit')) return 10;
        if (fieldName.includes('page')) return 1;
        return 1;

      case 'number':
        if (fieldName.includes('cost') || fieldName.includes('price') || fieldName.includes('amount')) return 29.99;
        if (fieldName.includes('lat')) return 51.5074;
        if (fieldName.includes('lon') || fieldName.includes('lng')) return -0.1278;
        return 0;

      case 'boolean':
        return true;

      case 'array':
        if (schema.items) {
          // For tags/items arrays, return 2 sample items
          if (fieldName.includes('tag')) return ['tag1', 'tag2'];
          return [this.generateSampleValue(schema.items)];
        }
        return [];

      case 'object':
        if (schema.additionalProperties) {
          // Generic object with additionalProperties
          return { key: 'value' };
        }
        return this.generateSampleBody(schema);

      default:
        return null;
    }
  },

  toggleFavorite() {
    if (!this.currentEndpoint) return;
    this.toggleFavoriteEndpoint(this.currentEndpoint.method, this.currentEndpoint.path);
  },

  toggleFavoriteEndpoint(method, path) {
    const key = method + ':' + path;
    const idx = this.favorites.indexOf(key);
    if (idx === -1) { this.favorites.push(key); Toast.success('Favorited', 'Endpoint added to favorites'); }
    else { this.favorites.splice(idx, 1); Toast.info('Removed', 'Endpoint removed from favorites'); }
    localStorage.setItem('apiExplorerFavorites', JSON.stringify(this.favorites));
    this.renderCategories();
    if (this.selectedCategory === 'favorites') this.showFavorites();
    else this.selectCategory(this.selectedCategory);
    if (this.currentEndpoint && this.currentEndpoint.method === method && this.currentEndpoint.path === path) {
      const isFav = this.favorites.includes(key);
      document.getElementById('btn-favorite').innerHTML = isFav ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>' : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
    }
  },

  handleSearch(query) {
    this.searchQuery = query;
    if (!query) { this.selectCategory(this.selectedCategory); return; }
    const q = query.toLowerCase();
    const filtered = this.endpoints.filter(function(ep) {
      return ep.path.toLowerCase().includes(q) || ep.summary.toLowerCase().includes(q) || ep.description.toLowerCase().includes(q) || ep.category.toLowerCase().includes(q) || ep.method.toLowerCase().includes(q);
    });
    document.getElementById('endpoints-title').textContent = 'Search: "' + query + '"';
    this.renderEndpointsList(filtered);
    document.querySelectorAll('.api-category-item').forEach(function(item) { item.classList.remove('active'); });
  },

  async refresh() {
    this.currentEndpoint = null;
    this.searchQuery = '';
    document.getElementById('api-search').value = '';
    document.getElementById('detail-content').innerHTML = '<div class="empty-state"><div class="empty-state-icon">' + Icons.code + '</div><div class="empty-state-title">No endpoint selected</div><div class="empty-state-description">Select an endpoint from the list to view its details and test it</div></div>';
    await this.loadEndpoints();
    Toast.info('Refreshed', 'API endpoints reloaded');
  },
};

// Make globally available
window.ApiExplorerView = ApiExplorerView;

// Register with Router if it exists and route not already registered
if (typeof Router !== 'undefined' && Router.routes && !Router.routes['/api-explorer']) {
  Router.register('/api-explorer', ApiExplorerView);
}
