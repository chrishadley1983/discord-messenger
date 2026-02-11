/**
 * Mind Map View — Peter's Knowledge Visualization
 *
 * 5 tabs: Force Graph, Knowledge Radar, Activity Timeline, Decay Analysis, Health Dashboard
 * Uses D3.js v7 for all visualizations.
 */

const MindMapView = {
  title: 'Mind Map',
  API: '/api/hadley/proxy/brain/graph',
  _data: null,
  _memories: null,
  _activity: null,
  _simulation: null,
  _activeTab: 0,

  // Domain color mapping
  DOMAIN_COLORS: {
    'Business': '#f59e0b',
    'Fitness': '#22c55e',
    'Family': '#3b82f6',
    'Tech': '#8b5cf6',
    'Finance': '#ef4444',
    'Food': '#f97316',
    'Health': '#14b8a6',
    'Personal': '#ec4899',
    'Travel': '#06b6d4',
    'Other': '#64748b',
  },

  // Topics that describe source/medium, not knowledge domain — filter from graph
  SOURCE_TOPICS: new Set([
    'email', 'calendar', 'calendar-event', 'bookmark', 'receipt', 'commit',
    'general', 'blog', 'article', 'newsletter', 'video', 'podcast',
    'youtube-channel', 'food-blog', 'recipe-blog', 'tutorial', 'review',
    'personal-log', 'news', 'streaming', 'tracking',
  ]),

  DOMAIN_KEYWORDS: {
    'Business': ['business', 'ecommerce', 'e-commerce', 'ebay', 'amazon', 'inventory', 'lego', 'bricklink', 'sales', 'orders', 'shipping', 'hadley-bricks', 'profit', 'revenue', 'listing', 'sourcing', 'supplier', 'purchase', 'purchases', 'retired-sets', 'minifigures', 'packaging', 'promotion', 'promotions', 'discount', 'brick-collecting', 'collecting', 'invoice', 'customer-service', 'deals', 'postal-supplies', 'lego-investing', 'shopping', 'storage', 'inventory-management'],
    'Fitness': ['fitness', 'training', 'running', 'marathon', 'exercise', 'workout', 'strength', 'garmin', 'vo2', 'pace', 'mileage', 'race', 'half-marathon', 'gym', 'cycling', 'indoor-cycling', 'hiking', 'walking', 'peloton', 'outdoor-activity', 'outdoor-adventure', 'stretching', 'mobility', 'long-run', 'marathon-training', 'recovery', 'rest', 'indoor-training', 'trail-running', 'mountain-trail', 'fitness-training', 'fitness-tracking', 'sports', 'cricket'],
    'Family': ['family', 'kids', 'parenting', 'school', 'children', 'wife', 'husband', 'home', 'house', 'garden', 'max', 'abby', 'family-trip', 'family-travel', 'birthday', 'family-meal-planner', 'home-improvement', 'diy'],
    'Tech': ['tech', 'programming', 'python', 'javascript', 'api', 'docker', 'linux', 'code', 'software', 'server', 'database', 'ai', 'claude', 'peterbot', 'supabase', 'discord', 'typescript', 'github', 'commit', 'development', 'web-development', 'code-quality', 'testing', 'code-review', 'tech-debt', 'tutorial'],
    'Finance': ['finance', 'budget', 'savings', 'investment', 'investing', 'tax', 'mortgage', 'money', 'bank', 'banking', 'pension', 'crypto', 'insurance', 'receipt', 'subscription', 'payment', 'self-employment', 'credit-card', 'early-retirement', 'financial-independence', 'retirement', 'personal-finance', 'hsbc', 'paypal', 'rewards', 'utilities'],
    'Food': ['food', 'recipe', 'recipes', 'cooking', 'meal', 'nutrition', 'diet', 'grocery', 'restaurant', 'calories', 'protein', 'dining', 'vegetarian', 'meal-prep', 'meal-deal', 'meal-delivery', 'home-cooking', 'food-blog', 'recipe-blog', 'soup', 'curry', 'side-dish', 'italian-cuisine', 'london-dining', 'restaurant-review', 'restaurant-reservation', 'coffee'],
    'Health': ['health', 'medical', 'doctor', 'sleep', 'weight', 'withings', 'blood-pressure', 'mental-health', 'wellness', 'health-tracking', 'medical-appointment', 'personal-care'],
    'Personal': ['personal', 'productivity', 'goals', 'habits', 'journal', 'learning', 'reading', 'books', 'hobbies', 'social', 'events', 'event-planning', 'event', 'key-date', 'lifestyle', 'simple-living', 'entertainment', 'new-year', 'new-years-eve', 'research', 'black-friday'],
    'Travel': ['travel', 'holiday', 'holiday-deals', 'flight', 'flight-deals', 'hotel', 'hotels', 'hotel-booking', 'hotel-stay', 'vacation', 'trip', 'accommodation', 'booking', 'hospitality', 'austria', 'japan-trip', 'airbnb', 'premier-inn', 'budget-travel', 'budget-accommodation', 'transportation', 'london', 'city-trip', 'city-centre', 'tourism', 'italy', 'italy-trip', 'switzerland', 'germany', 'uk-trip', 'tonbridge', 'train', 'reservation', 'car-service', 'vehicle-maintenance', 'automotive'],
  },

  getDomain(topic) {
    const t = topic.toLowerCase();
    for (const [domain, keywords] of Object.entries(this.DOMAIN_KEYWORDS)) {
      if (keywords.some(kw => t.includes(kw))) return domain;
    }
    return 'Other';
  },

  getDomainColor(topic) {
    return this.DOMAIN_COLORS[this.getDomain(topic)] || this.DOMAIN_COLORS['Other'];
  },

  // Filter topics by current source toggle (shared across all tabs)
  _filterTopicsBySource(topics) {
    const src = this._graphSource || 'both';
    return topics.filter(t => {
      if (this.SOURCE_TOPICS.has(t.topic)) return false;
      if (src === 'brain' && t._isMemory) return false;
      if (src === 'memory' && !t._isMemory) return false;
      return true;
    });
  },

  async render(container) {
    container.innerHTML = `
      <div class="animate-fade-in">
        <div class="flex justify-between items-center mb-lg">
          <div>
            <h2>Peter's Mind Map</h2>
            <p class="text-secondary">Knowledge topology, activity, and health</p>
          </div>
          <div class="flex gap-sm">
            <div class="mind-map-search-wrap">
              <input type="text" id="mm-search" class="input" placeholder="Search knowledge..." style="width: 240px">
            </div>
            <button class="btn btn-secondary" onclick="MindMapView.refresh()">Refresh</button>
          </div>
        </div>

        <div class="mind-map-stats" id="mm-stats"></div>

        <div class="mm-global-controls">
          <div class="mm-source-toggle" id="mm-global-source">
            <button class="mm-source-btn active" data-source="both">Both</button>
            <button class="mm-source-btn" data-source="brain">Second Brain</button>
            <button class="mm-source-btn" data-source="memory">Memories</button>
          </div>
        </div>

        ${Components.tabs({
          id: 'mm-tabs',
          tabs: [
            { label: 'Knowledge Graph', content: '<div id="mm-graph" class="mm-graph-container"><div class="mm-loading">Loading graph...</div></div>' },
            { label: 'Knowledge Radar', content: '<div id="mm-radar" class="mm-chart-container"><div class="mm-loading">Loading radar...</div></div>' },
            { label: 'Activity Timeline', content: '<div id="mm-activity" class="mm-chart-container"><div class="mm-loading">Loading activity...</div></div>' },
            { label: 'Decay Analysis', content: '<div id="mm-decay" class="mm-chart-container"><div class="mm-loading">Loading decay data...</div></div>' },
            { label: 'Health Dashboard', content: '<div id="mm-health" class="mm-health-container"><div class="mm-loading">Loading health data...</div></div>' },
          ]
        })}

        <div id="mm-detail-panel" class="mm-detail-panel" style="display:none"></div>
      </div>
    `;

    // Wire up tab switching to render the right chart
    const origSwitch = Tabs.switch.bind(Tabs);
    const mmTabSwitch = (id, idx) => {
      origSwitch(id, idx);
      if (id === 'mm-tabs') {
        this._activeTab = idx;
        this._renderActiveTab();
      }
    };
    // Patch tab buttons
    document.querySelectorAll('#mm-tabs .tab').forEach((btn, idx) => {
      btn.onclick = () => mmTabSwitch('mm-tabs', idx);
    });

    // Global source toggle
    this._graphSource = 'both';
    document.querySelectorAll('#mm-global-source .mm-source-btn').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('#mm-global-source .mm-source-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._graphSource = btn.dataset.source;
        this._renderActiveTab();
      };
    });

    // Search handler
    const searchInput = document.getElementById('mm-search');
    let searchTimeout;
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => this._handleSearch(searchInput.value), 300);
    });

    await this._loadData();
  },

  async _loadData() {
    try {
      const [graphResp, memResp] = await Promise.all([
        fetch(this.API),
        fetch('/api/memory/graph').catch(() => null),
      ]);
      if (!graphResp.ok) throw new Error(`HTTP ${graphResp.status}`);
      this._data = await graphResp.json();

      // Load peterbot memories and merge into graph
      if (memResp && memResp.ok) {
        const memData = await memResp.json();
        this._memories = memData.categories || [];
        this._memoryTotal = memData.total || 0;
        this._mergeMemoriesIntoGraph();
      }

      this._renderStats();
      this._renderActiveTab();
    } catch (e) {
      console.error('Mind map data load failed:', e);
      document.getElementById('mm-graph').innerHTML = `<div class="mm-error">Failed to load graph data: ${e.message}</div>`;
    }
  },

  _mergeMemoriesIntoGraph() {
    if (!this._memories || !this._data) return;

    // Build memory nodes from pre-aggregated categories (min 2 items)
    const memoryNodes = [];
    for (const cat of this._memories) {
      if (cat.count < 2) continue;
      const recentItems = (cat.items || []).filter(m => {
        if (!m.created_at) return false;
        return (Date.now() - new Date(m.created_at).getTime()) < 30 * 86400000;
      });
      memoryNodes.push({
        topic: cat.category,
        item_count: cat.count,
        recently_accessed: recentItems.length,
        added_last_week: (cat.items || []).filter(m => m.created_at && (Date.now() - new Date(m.created_at).getTime()) < 7 * 86400000).length,
        avg_decay: 1.0,
        avg_access_count: 0,
        last_accessed: cat.items?.[0]?.created_at || null,
        content_types: Object.keys(cat.types || {}),
        _isMemory: true,
        _memoryItems: cat.items || [],
      });
    }

    // Merge into topic_stats (avoid duplicates)
    const existingTopics = new Set(this._data.topic_stats.map(t => t.topic.toLowerCase()));
    for (const mn of memoryNodes) {
      if (!existingTopics.has(mn.topic.toLowerCase())) {
        this._data.topic_stats.push(mn);
      }
    }

    // Update overall stats
    if (this._data.overall) {
      this._data.overall.memory_count = this._memoryTotal;
      this._data.overall.memory_categories = memoryNodes.length;
    }
  },

  async refresh() {
    try {
      await fetch(`${this.API}/refresh`, { method: 'POST' });
    } catch (_) {}
    this._data = null;
    this._memories = null;
    this._activity = null;
    await this._loadData();
  },

  _renderStats() {
    const s = this._data?.overall;
    if (!s) return;
    document.getElementById('mm-stats').innerHTML = `
      <div class="mm-stat-cards">
        <div class="mm-stat-card">
          <div class="mm-stat-value">${(s.total_items || 0).toLocaleString()}</div>
          <div class="mm-stat-label">Knowledge Items</div>
        </div>
        <div class="mm-stat-card">
          <div class="mm-stat-value">${s.unique_topics || 0}</div>
          <div class="mm-stat-label">Unique Topics</div>
        </div>
        <div class="mm-stat-card">
          <div class="mm-stat-value">${s.accessed_30d || 0}</div>
          <div class="mm-stat-label">Accessed (30d)</div>
        </div>
        <div class="mm-stat-card">
          <div class="mm-stat-value">${s.avg_decay || 0}</div>
          <div class="mm-stat-label">Avg Decay Score</div>
        </div>
        <div class="mm-stat-card">
          <div class="mm-stat-value">${s.added_7d || 0}</div>
          <div class="mm-stat-label">Added (7d)</div>
        </div>
        ${s.memory_count ? `<div class="mm-stat-card">
          <div class="mm-stat-value">${s.memory_count}</div>
          <div class="mm-stat-label">Memories</div>
        </div>` : ''}
      </div>
    `;
  },

  _renderActiveTab() {
    if (!this._data) return;
    switch (this._activeTab) {
      case 0: this._renderGraph(); break;
      case 1: this._renderRadar(); break;
      case 2: this._renderActivityTimeline(); break;
      case 3: this._renderDecay(); break;
      case 4: this._renderHealth(); break;
    }
  },

  // ================================================================
  // TAB 1: Force-Directed Graph
  // ================================================================

  _renderGraph() {
    const container = document.getElementById('mm-graph');
    if (!container || !this._data) return;
    container.innerHTML = `
      <div class="mm-graph-controls">
        <label>Recency:
          <select id="mm-recency">
            <option value="0">Off</option>
            <option value="0.5">12 hours</option>
            <option value="1">24 hours</option>
            <option value="3">3 days</option>
            <option value="7" selected>7 days</option>
            <option value="14">14 days</option>
            <option value="30">30 days</option>
            <option value="90">90 days</option>
          </select>
        </label>
        <label>Min Items: <input type="range" id="mm-min-items" min="2" max="50" value="3"><span id="mm-min-items-val">3</span></label>
        <label>Min Edge Weight: <input type="range" id="mm-min-edge" min="5" max="50" value="5"><span id="mm-min-edge-val">5</span></label>
        <div class="mm-legend" id="mm-legend"></div>
      </div>
      <svg id="mm-graph-svg"></svg>
      <div id="mm-tooltip" class="mm-tooltip"></div>
    `;

    this._buildLegend();
    this._drawForceGraph(3, 5);

    // Filter controls
    const minItemsSlider = document.getElementById('mm-min-items');
    const minEdgeSlider = document.getElementById('mm-min-edge');
    minItemsSlider.oninput = () => {
      document.getElementById('mm-min-items-val').textContent = minItemsSlider.value;
      this._drawForceGraph(+minItemsSlider.value, +minEdgeSlider.value);
    };
    minEdgeSlider.oninput = () => {
      document.getElementById('mm-min-edge-val').textContent = minEdgeSlider.value;
      this._drawForceGraph(+minItemsSlider.value, +minEdgeSlider.value);
    };

    // Recency filter — highlight nodes accessed within window
    document.getElementById('mm-recency').onchange = (e) => {
      this._applyRecency(+e.target.value);
    };
    // Apply default recency on first render
    setTimeout(() => this._applyRecency(7), 500);
  },

  _applyRecency(days) {
    if (!days) {
      // Off — reset all nodes to normal
      d3.selectAll('.mm-node').each(function(d) {
        d3.select(this).select('circle, rect').attr('opacity', 0.85);
        d3.select(this).select('.mm-recency-ring').remove();
      });
      d3.selectAll('.mm-links line').attr('stroke-opacity', null);
      return;
    }

    const cutoff = Date.now() - days * 86400000;

    d3.selectAll('.mm-node').each(function(d) {
      const la = d.last_accessed ? new Date(d.last_accessed).getTime() : 0;
      // For memory nodes, use created_at of most recent item
      const memTime = d._isMemory && d._memoryItems?.[0]?.created_at
        ? new Date(d._memoryItems[0].created_at).getTime() : 0;
      const lastActive = Math.max(la, memTime);
      const isRecent = lastActive > cutoff;

      const shape = d3.select(this).select('circle, rect');
      shape.attr('opacity', isRecent ? 1 : 0.2);

      // Add/remove glow ring for recent nodes
      d3.select(this).select('.mm-recency-ring').remove();
      if (isRecent && !d._isMemory) {
        const r = +d3.select(this).select('circle').attr('r');
        if (r) {
          d3.select(this).insert('circle', ':first-child')
            .attr('class', 'mm-recency-ring')
            .attr('r', r + 5)
            .attr('fill', 'none')
            .attr('stroke', d.color)
            .attr('stroke-width', 3)
            .attr('opacity', 0.5)
            .attr('class', 'mm-recency-ring mm-pulse');
        }
      }
    });

    // Fade edges to non-recent nodes
    d3.selectAll('.mm-links line').each(function(d) {
      const sTime = d.source.last_accessed ? new Date(d.source.last_accessed).getTime() : 0;
      const tTime = d.target.last_accessed ? new Date(d.target.last_accessed).getTime() : 0;
      const bothRecent = sTime > cutoff && tTime > cutoff;
      d3.select(this).attr('stroke-opacity', bothRecent ? 0.6 : 0.05);
    });
  },

  _buildLegend() {
    const el = document.getElementById('mm-legend');
    if (!el) return;
    el.innerHTML = Object.entries(this.DOMAIN_COLORS).map(([name, color]) =>
      `<span class="mm-legend-item"><span class="mm-legend-dot" style="background:${color}"></span>${name}</span>`
    ).join('') +
    `<span class="mm-legend-item"><span class="mm-legend-dot mm-legend-dot-memory"></span>Memory</span>`;
  },

  _drawForceGraph(minItems, minEdge) {
    const svg = d3.select('#mm-graph-svg');
    if (svg.empty()) return;
    svg.selectAll('*').remove();

    if (this._simulation) {
      this._simulation.stop();
      this._simulation = null;
    }

    const topics = this._filterTopicsBySource(this._data.topic_stats)
      .filter(t => t.item_count >= minItems);
    const topicSet = new Set(topics.map(t => t.topic));
    const edges = this._data.topic_edges.filter(e =>
      e.co_count >= minEdge && topicSet.has(e.source) && topicSet.has(e.target)
    );

    // Build node/link arrays
    const nodeMap = {};
    const nodes = topics.map(t => {
      const n = { id: t.topic, ...t, domain: this.getDomain(t.topic), color: this.getDomainColor(t.topic) };
      nodeMap[t.topic] = n;
      return n;
    });
    const links = edges.map(e => ({ source: e.source, target: e.target, weight: e.co_count }));

    const rect = document.getElementById('mm-graph-svg').parentElement.getBoundingClientRect();
    const width = rect.width || 900;
    const height = 600;

    svg.attr('width', width).attr('height', height).attr('viewBox', `0 0 ${width} ${height}`);

    const radiusScale = d3.scaleSqrt()
      .domain(d3.extent(nodes, d => d.item_count))
      .range([6, 40]);

    const edgeScale = d3.scaleLinear()
      .domain(d3.extent(links, d => d.weight) || [1, 1])
      .range([0.3, 2]);

    const opacityScale = d3.scaleLinear()
      .domain(d3.extent(links, d => d.weight) || [1, 1])
      .range([0.15, 0.6]);

    // Simulation
    this._simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(d => Math.min(d.weight / 50, 0.5)))
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => radiusScale(d.item_count) + 4));

    // Zoom
    const g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.2, 5]).on('zoom', (event) => {
      g.attr('transform', event.transform);
    }));

    // Links
    const link = g.append('g').attr('class', 'mm-links')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#94a3b8')
      .attr('stroke-width', d => edgeScale(d.weight))
      .attr('stroke-opacity', d => opacityScale(d.weight));

    // Node groups
    const node = g.append('g').attr('class', 'mm-nodes')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('class', 'mm-node')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) this._simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on('end', (event, d) => {
          if (!event.active) this._simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    // Second Brain nodes: circles
    node.filter(d => !d._isMemory).append('circle')
      .attr('r', d => radiusScale(d.item_count))
      .attr('fill', d => d.color)
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.85);

    // Memory nodes: diamonds (rotated squares)
    node.filter(d => d._isMemory).append('rect')
      .attr('width', d => radiusScale(d.item_count) * 1.5)
      .attr('height', d => radiusScale(d.item_count) * 1.5)
      .attr('x', d => -radiusScale(d.item_count) * 0.75)
      .attr('y', d => -radiusScale(d.item_count) * 0.75)
      .attr('transform', 'rotate(45)')
      .attr('fill', d => d.color)
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .attr('opacity', 0.85)
      .attr('rx', 2);

    // Pulse for recently accessed
    node.filter(d => d.recently_accessed > 0)
      .append('circle')
      .attr('r', d => radiusScale(d.item_count) + 4)
      .attr('fill', 'none')
      .attr('stroke', d => d.color)
      .attr('stroke-width', 2)
      .attr('opacity', 0.4)
      .attr('class', 'mm-pulse');

    // Labels for larger nodes
    node.filter(d => d.item_count >= 10)
      .append('text')
      .text(d => d.topic.length > 14 ? d.topic.slice(0, 12) + '...' : d.topic)
      .attr('text-anchor', 'middle')
      .attr('dy', d => radiusScale(d.item_count) + 14)
      .attr('class', 'mm-node-label');

    // Tooltip
    const tooltip = d3.select('#mm-tooltip');
    node.on('mouseover', (event, d) => {
      tooltip.style('display', 'block')
        .html(`
          <strong>${d.topic}</strong><br>
          Source: ${d._isMemory ? 'Peterbot Memory' : 'Second Brain'}<br>
          ${d._isMemory ? 'Observations' : 'Items'}: ${d.item_count}<br>
          ${d._isMemory ? '' : `Accessed (30d): ${d.recently_accessed}<br>Avg Decay: ${d.avg_decay}<br>`}
          Domain: ${d.domain}
        `)
        .style('left', (event.pageX + 12) + 'px')
        .style('top', (event.pageY - 10) + 'px');
    })
    .on('mousemove', (event) => {
      tooltip.style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 10) + 'px');
    })
    .on('mouseout', () => tooltip.style('display', 'none'))
    .on('click', (event, d) => d._isMemory ? this._showMemoryDetail(d.topic) : this._showTopicDetail(d.topic));

    // Tick
    this._simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
  },

  async _showTopicDetail(topic) {
    const panel = document.getElementById('mm-detail-panel');
    panel.style.display = 'block';
    panel.innerHTML = `<div class="mm-loading">Loading ${topic}...</div>`;

    try {
      const resp = await fetch(`${this.API}/topic/${encodeURIComponent(topic)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const items = data.items || [];
      const count = data.total_count || items.length;
      panel.innerHTML = `
        <div class="mm-detail-header">
          <h3>${Utils.escapeHtml(topic)}</h3>
          <span class="text-secondary">${count} items</span>
          <button class="btn btn-sm" onclick="document.getElementById('mm-detail-panel').style.display='none'">Close</button>
        </div>
        <div class="mm-detail-items">
          ${items.length === 0 ? '<p class="text-secondary">No items found</p>' : items.map(item => `
            <div class="mm-detail-item">
              <div class="mm-detail-item-title">${Utils.escapeHtml(item.title || 'Untitled')}</div>
              <div class="mm-detail-item-meta">
                <span class="badge">${item.content_type || 'unknown'}</span>
                <span>Decay: ${item.decay_score ?? '-'}</span>
                <span>Accessed: ${item.access_count ?? 0}x</span>
                ${item.last_accessed_at ? `<span>Last: ${new Date(item.last_accessed_at).toLocaleDateString()}</span>` : ''}
              </div>
              ${item.summary ? `<div class="mm-detail-item-summary">${Utils.escapeHtml(item.summary.slice(0, 200))}${item.summary.length > 200 ? '...' : ''}</div>` : ''}
            </div>
          `).join('')}
        </div>
      `;
    } catch (e) {
      panel.innerHTML = `<div class="mm-error">Failed to load topic: ${e.message}</div>`;
    }
  },

  _showMemoryDetail(category) {
    const panel = document.getElementById('mm-detail-panel');
    panel.style.display = 'block';

    // Find the category in memory data, or look for matching node
    const catData = (this._memories || []).find(c => c.category === category);
    const items = catData?.items || [];

    // Also check if a graph node has _memoryItems
    if (items.length === 0) {
      const node = (this._data?.topic_stats || []).find(t => t.topic === category && t._isMemory);
      if (node?._memoryItems) items.push(...node._memoryItems);
    }

    panel.innerHTML = `
      <div class="mm-detail-header">
        <h3>${Utils.escapeHtml(category)}</h3>
        <span class="text-secondary">${items.length} memories</span>
        <button class="btn btn-sm" onclick="document.getElementById('mm-detail-panel').style.display='none'">Close</button>
      </div>
      <div class="mm-detail-items">
        ${items.length === 0 ? '<p class="text-secondary">No memories found</p>' : items.map(mem => `
          <div class="mm-detail-item">
            <div class="mm-detail-item-title">${Utils.escapeHtml(mem.title || 'Untitled')}</div>
            <div class="mm-detail-item-meta">
              <span class="badge" style="background:#8b5cf6;color:#fff">${mem.type || 'observation'}</span>
              ${mem.created_at ? `<span>Created: ${new Date(mem.created_at).toLocaleDateString()}</span>` : ''}
            </div>
            ${mem.narrative ? `<div class="mm-detail-item-summary">${Utils.escapeHtml(mem.narrative.slice(0, 200))}${mem.narrative.length > 200 ? '...' : ''}</div>` : ''}
          </div>
        `).join('')}
      </div>
    `;
  },

  async _handleSearch(query) {
    if (!query || query.length < 2) {
      // Reset highlighting
      d3.selectAll('.mm-node circle').attr('opacity', 0.85).attr('stroke', '#fff');
      d3.selectAll('.mm-node').classed('mm-highlighted', false);
      return;
    }

    try {
      const resp = await fetch(`${this.API}/search?query=${encodeURIComponent(query)}`);
      const data = await resp.json();
      const highlights = new Set(data.highlighted_topics || []);

      d3.selectAll('.mm-node').each(function(d) {
        const isHit = highlights.has(d.topic);
        d3.select(this).select('circle')
          .attr('opacity', isHit ? 1 : 0.2)
          .attr('stroke', isHit ? '#fff' : 'transparent')
          .attr('stroke-width', isHit ? 3 : 1);
        d3.select(this).classed('mm-highlighted', isHit);
      });
    } catch (e) {
      console.error('Search failed:', e);
    }
  },

  // ================================================================
  // TAB 2: Knowledge Radar
  // ================================================================

  _renderRadar() {
    const container = document.getElementById('mm-radar');
    if (!container || !this._data) return;

    const src = this._graphSource || 'both';
    const isMemoryOnly = src === 'memory';

    // For memory-only: show top memory categories directly as axes
    // For brain/both: aggregate by domain group
    let axes;
    let metrics;

    if (isMemoryOnly) {
      // Memory categories as direct axes (top 10)
      const memTopics = this._filterTopicsBySource(this._data.topic_stats)
        .sort((a, b) => b.item_count - a.item_count)
        .slice(0, 10);
      axes = memTopics.map(t => ({
        name: t.topic,
        item_count: t.item_count,
        access_count: t.recently_accessed || 0,
        topic_count: 1,
        avg_decay: t.avg_decay || 1,
      }));
      metrics = [
        { value: 'item_count', label: 'Observation Count' },
        { value: 'access_count', label: 'Recent (30d)' },
      ];
    } else {
      // Domain-based aggregation for Second Brain / Both
      const domains = {};
      const filteredTopics = this._filterTopicsBySource(this._data.topic_stats);
      for (const t of filteredTopics) {
        const d = this.getDomain(t.topic);
        if (!domains[d]) domains[d] = { name: d, item_count: 0, access_count: 0, topic_count: 0, avg_decay_sum: 0 };
        domains[d].item_count += t.item_count;
        domains[d].access_count += t.recently_accessed;
        domains[d].topic_count += 1;
        domains[d].avg_decay_sum += t.avg_decay * t.item_count;
      }
      axes = Object.values(domains)
        .filter(d => d.name !== 'Other')
        .map(d => ({
          ...d,
          avg_decay: d.item_count > 0 ? d.avg_decay_sum / d.item_count : 0,
        }));
      metrics = [
        { value: 'item_count', label: 'Item Count' },
        { value: 'access_count', label: 'Access (30d)' },
        { value: 'avg_decay', label: 'Avg Decay' },
        { value: 'topic_count', label: 'Topic Diversity' },
      ];
    }

    container.innerHTML = `
      <div class="mm-radar-controls">
        <label>Metric:
          <select id="mm-radar-metric">
            ${metrics.map((m, i) => `<option value="${m.value}"${i === 0 ? ' selected' : ''}>${m.label}</option>`).join('')}
          </select>
        </label>
      </div>
      <svg id="mm-radar-svg"></svg>
    `;

    const self = this;
    const drawRadar = (metric) => {
      const svg = d3.select('#mm-radar-svg');
      svg.selectAll('*').remove();

      const size = Math.min(container.clientWidth, 500);
      const cx = size / 2, cy = size / 2, maxR = size / 2 - 60;
      svg.attr('width', size).attr('height', size);

      const n = axes.length;
      if (n === 0) {
        svg.append('text').attr('x', size / 2).attr('y', size / 2)
          .attr('text-anchor', 'middle').attr('fill', '#94a3b8').text('No data for current filter');
        return;
      }

      const maxVal = d3.max(axes, d => d[metric]) || 1;
      const angleSlice = (Math.PI * 2) / n;

      // Grid circles
      const levels = 5;
      for (let i = 1; i <= levels; i++) {
        const r = (maxR / levels) * i;
        svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', r)
          .attr('fill', 'none').attr('stroke', '#e2e8f0').attr('stroke-dasharray', '3,3');
      }

      // Axes
      axes.forEach((d, i) => {
        const angle = angleSlice * i - Math.PI / 2;
        const x = cx + Math.cos(angle) * maxR;
        const y = cy + Math.sin(angle) * maxR;
        svg.append('line').attr('x1', cx).attr('y1', cy).attr('x2', x).attr('y2', y)
          .attr('stroke', '#cbd5e1').attr('stroke-width', 1);
        // Label
        const lx = cx + Math.cos(angle) * (maxR + 25);
        const ly = cy + Math.sin(angle) * (maxR + 25);
        const label = d.name.length > 16 ? d.name.slice(0, 14) + '..' : d.name;
        svg.append('text').attr('x', lx).attr('y', ly)
          .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
          .attr('class', 'mm-radar-label')
          .text(label);
      });

      // Polygon
      const points = axes.map((d, i) => {
        const angle = angleSlice * i - Math.PI / 2;
        const r = (d[metric] / maxVal) * maxR;
        return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r];
      });

      svg.append('polygon')
        .attr('points', points.map(p => p.join(',')).join(' '))
        .attr('fill', isMemoryOnly ? 'rgba(139, 92, 246, 0.2)' : 'rgba(13, 148, 136, 0.2)')
        .attr('stroke', isMemoryOnly ? '#8b5cf6' : '#0d9488')
        .attr('stroke-width', 2);

      // Dots
      points.forEach(([x, y], i) => {
        svg.append('circle').attr('cx', x).attr('cy', y).attr('r', 5)
          .attr('fill', self.DOMAIN_COLORS[axes[i].name] || (isMemoryOnly ? '#8b5cf6' : '#0d9488'));
      });
    };

    drawRadar(metrics[0].value);
    document.getElementById('mm-radar-metric').onchange = (e) => drawRadar(e.target.value);
  },

  // ================================================================
  // TAB 3: Activity Timeline (Heatmap)
  // ================================================================

  async _renderActivityTimeline() {
    const container = document.getElementById('mm-activity');
    if (!container) return;

    if (!this._activity) {
      try {
        const resp = await fetch(`${this.API}/activity`);
        this._activity = await resp.json();
      } catch (e) {
        container.innerHTML = `<div class="mm-error">Failed to load activity: ${e.message}</div>`;
        return;
      }
    }

    const cliData = this._activity.cli_activity || [];
    const knowledgeData = this._activity.knowledge_activity || [];

    // Merge into day map
    const dayMap = {};
    for (const entry of cliData) {
      dayMap[entry.date] = { calls: entry.calls, cost: entry.total_cost_usd || 0, accesses: 0 };
    }
    for (const entry of knowledgeData) {
      if (!dayMap[entry.date]) dayMap[entry.date] = { calls: 0, cost: 0, accesses: 0 };
      dayMap[entry.date].accesses = entry.accesses;
    }

    // Build 90-day grid
    const today = new Date();
    const days = [];
    for (let i = 89; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      days.push({ date: key, dayOfWeek: d.getDay(), ...(dayMap[key] || { calls: 0, cost: 0, accesses: 0 }) });
    }

    // Summary stats
    const totalCalls = days.reduce((s, d) => s + d.calls, 0);
    const totalAccesses = days.reduce((s, d) => s + d.accesses, 0);
    const activeDays = days.filter(d => d.calls > 0 || d.accesses > 0).length;
    const totalCost = days.reduce((s, d) => s + d.cost, 0);

    container.innerHTML = `
      <div class="mm-activity-summary">
        <div class="mm-stat-cards">
          <div class="mm-stat-card"><div class="mm-stat-value">${totalCalls}</div><div class="mm-stat-label">CLI Calls (90d)</div></div>
          <div class="mm-stat-card"><div class="mm-stat-value">${totalAccesses}</div><div class="mm-stat-label">KB Accesses (90d)</div></div>
          <div class="mm-stat-card"><div class="mm-stat-value">${activeDays}</div><div class="mm-stat-label">Active Days</div></div>
          <div class="mm-stat-card"><div class="mm-stat-value">$${totalCost.toFixed(2)}</div><div class="mm-stat-label">CLI Cost (90d)</div></div>
        </div>
      </div>
      <h4 style="margin: 16px 0 8px">Activity Heatmap <span class="text-secondary" style="font-weight:400;font-size:12px">Last 90 days</span></h4>
      <div class="mm-heatmap-wrap"><svg id="mm-heatmap-svg"></svg></div>
      <div id="mm-heatmap-legend" class="mm-heatmap-legend"></div>
      ${cliData.length > 0 ? `
        <h4 style="margin: 20px 0 8px">Daily Breakdown</h4>
        <div class="mm-activity-table-wrap">
          <table class="mm-activity-table">
            <thead><tr><th>Date</th><th>CLI Calls</th><th>KB Accesses</th><th>Cost</th></tr></thead>
            <tbody>
              ${[...days].reverse().filter(d => d.calls > 0 || d.accesses > 0).slice(0, 20).map(d => `
                <tr>
                  <td>${d.date}</td>
                  <td>${d.calls}</td>
                  <td>${d.accesses}</td>
                  <td>${d.cost > 0 ? '$' + d.cost.toFixed(2) : '-'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : '<p class="text-secondary" style="text-align:center;margin-top:16px">No CLI cost log data yet. Activity will appear here as Peter handles conversations.</p>'}
    `;

    // Draw heatmap
    const svg = d3.select('#mm-heatmap-svg');
    const containerWidth = container.clientWidth - 40;
    const weeks = Math.ceil(days.length / 7);
    const cellSize = Math.min(Math.floor((containerWidth - 50) / weeks) - 3, 28);
    const cellGap = 3;
    const w = weeks * (cellSize + cellGap) + 50;
    const h = 7 * (cellSize + cellGap) + 50;
    svg.attr('width', w).attr('height', h);

    const maxCalls = d3.max(days, d => d.calls + d.accesses) || 1;
    const colorScale = d3.scaleSequential(d3.interpolateGreens).domain([0, maxCalls]);

    const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    dayLabels.forEach((label, i) => {
      svg.append('text').attr('x', 30).attr('y', i * (cellSize + cellGap) + cellSize / 2 + 20)
        .attr('text-anchor', 'end').attr('dominant-baseline', 'central')
        .attr('class', 'mm-heatmap-day-label').text(label);
    });

    // Month labels at top
    let lastMonth = '';
    let weekIdx = 0;
    days.forEach((d, i) => {
      if (i > 0 && d.dayOfWeek === 0) weekIdx++;
      const month = d.date.slice(0, 7);
      if (d.dayOfWeek === 0 && month !== lastMonth) {
        const monthName = new Date(d.date).toLocaleString('en-GB', { month: 'short' });
        svg.append('text')
          .attr('x', 40 + weekIdx * (cellSize + cellGap))
          .attr('y', 10).attr('class', 'mm-heatmap-day-label').text(monthName);
        lastMonth = month;
      }
    });

    weekIdx = 0;
    const tooltip = d3.select('#mm-tooltip');
    days.forEach((d, i) => {
      const dow = d.dayOfWeek;
      if (i > 0 && dow === 0) weekIdx++;
      const total = d.calls + d.accesses;

      svg.append('rect')
        .attr('x', 40 + weekIdx * (cellSize + cellGap))
        .attr('y', 18 + dow * (cellSize + cellGap))
        .attr('width', cellSize)
        .attr('height', cellSize)
        .attr('rx', 3)
        .attr('fill', total > 0 ? colorScale(total) : '#f1f5f9')
        .attr('stroke', '#e2e8f0')
        .attr('stroke-width', 0.5)
        .style('cursor', 'pointer')
        .on('mouseover', (event) => {
          tooltip.style('display', 'block')
            .html(`<strong>${d.date}</strong><br>CLI Calls: ${d.calls}<br>KB Accesses: ${d.accesses}${d.cost > 0 ? '<br>Cost: $' + d.cost.toFixed(2) : ''}`)
            .style('left', (event.pageX + 12) + 'px')
            .style('top', (event.pageY - 10) + 'px');
        })
        .on('mouseout', () => tooltip.style('display', 'none'));
    });

    // Legend
    document.getElementById('mm-heatmap-legend').innerHTML = `
      <span class="text-secondary">Less</span>
      ${[0, 0.25, 0.5, 0.75, 1].map(v =>
        `<span class="mm-heatmap-swatch" style="background:${v === 0 ? '#f1f5f9' : colorScale(v * maxCalls)}"></span>`
      ).join('')}
      <span class="text-secondary">More</span>
    `;
  },

  // ================================================================
  // TAB 4: Decay Analysis
  // ================================================================

  _renderDecay() {
    const container = document.getElementById('mm-decay');
    if (!container || !this._data) return;

    container.innerHTML = `
      <div class="mm-decay-grid">
        <div class="mm-decay-chart-wrap">
          <h4>Decay Score vs Days Since Access</h4>
          <svg id="mm-decay-svg"></svg>
        </div>
        <div class="mm-decay-suggestions">
          <h4>Suggestions</h4>
          <div id="mm-decay-suggest"></div>
        </div>
      </div>
    `;

    const topics = this._filterTopicsBySource(this._data.topic_stats);
    const now = Date.now();
    const points = topics.map(t => ({
      topic: t.topic,
      decay: t.avg_decay,
      domain: this.getDomain(t.topic),
      color: this.getDomainColor(t.topic),
      items: t.item_count,
      isMemory: !!t._isMemory,
      daysSince: t.last_accessed ? Math.max(0, (now - new Date(t.last_accessed).getTime()) / 86400000) : 365,
    }));

    const svgEl = document.getElementById('mm-decay-svg');
    const w = svgEl.parentElement.clientWidth || 600;
    const h = 400;
    const margin = { top: 20, right: 30, bottom: 40, left: 50 };

    const svg = d3.select('#mm-decay-svg').attr('width', w).attr('height', h);

    const x = d3.scaleLinear().domain([0, d3.max(points, d => d.daysSince) || 365]).range([margin.left, w - margin.right]);
    const y = d3.scaleLinear().domain([0, d3.max(points, d => d.decay) || 1.5]).range([h - margin.bottom, margin.top]);
    const r = d3.scaleSqrt().domain(d3.extent(points, d => d.items)).range([3, 18]);

    // Axes
    svg.append('g').attr('transform', `translate(0,${h - margin.bottom})`).call(d3.axisBottom(x).ticks(8))
      .append('text').attr('x', w / 2).attr('y', 35).attr('fill', '#64748b').attr('text-anchor', 'middle').text('Days Since Last Access');
    svg.append('g').attr('transform', `translate(${margin.left},0)`).call(d3.axisLeft(y).ticks(6))
      .append('text').attr('transform', 'rotate(-90)').attr('x', -h / 2).attr('y', -35).attr('fill', '#64748b').attr('text-anchor', 'middle').text('Avg Decay Score');

    // Theoretical decay curve
    const curveData = d3.range(0, 365, 1).map(d => ({ x: d, y: Math.pow(0.5, d / 90) }));
    svg.append('path')
      .datum(curveData)
      .attr('fill', 'none')
      .attr('stroke', '#94a3b8')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '6,3')
      .attr('d', d3.line().x(d => x(d.x)).y(d => y(d.y)));

    // Points
    const tooltip = d3.select('#mm-tooltip');
    svg.selectAll('.mm-decay-point')
      .data(points)
      .join('circle')
      .attr('class', 'mm-decay-point')
      .attr('cx', d => x(d.daysSince))
      .attr('cy', d => y(d.decay))
      .attr('r', d => r(d.items))
      .attr('fill', d => d.color)
      .attr('opacity', 0.7)
      .attr('stroke', '#fff')
      .attr('stroke-width', 0.5)
      .on('mouseover', (event, d) => {
        tooltip.style('display', 'block')
          .html(`<strong>${d.topic}</strong><br>Decay: ${d.decay}<br>Days: ${Math.round(d.daysSince)}<br>Items: ${d.items}`)
          .style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 10) + 'px');
      })
      .on('mouseout', () => tooltip.style('display', 'none'))
      .on('click', (event, d) => d.isMemory ? this._showMemoryDetail(d.topic) : this._showTopicDetail(d.topic));

    // Suggestions: high-count low-access and low-decay (Second Brain only)
    const neglected = [...topics]
      .filter(t => t.item_count >= 10 && t.recently_accessed === 0)
      .sort((a, b) => b.item_count - a.item_count)
      .slice(0, 8);

    const thin = [...topics]
      .filter(t => t.item_count < 5)
      .sort((a, b) => b.recently_accessed - a.recently_accessed)
      .slice(0, 8);

    document.getElementById('mm-decay-suggest').innerHTML = `
      <div class="mm-suggest-section">
        <h5>Neglected (many items, no recent access)</h5>
        ${neglected.length === 0 ? '<p class="text-secondary">None found</p>' :
          neglected.map(t => `<div class="mm-suggest-item" onclick="MindMapView._showTopicDetail('${t.topic}')">
            <span class="mm-suggest-dot" style="background:${this.getDomainColor(t.topic)}"></span>
            <span>${t.topic}</span> <span class="text-secondary">(${t.item_count} items)</span>
          </div>`).join('')}
      </div>
      <div class="mm-suggest-section">
        <h5>Thin Coverage (few items, recently used)</h5>
        ${thin.length === 0 ? '<p class="text-secondary">None found</p>' :
          thin.map(t => `<div class="mm-suggest-item" onclick="MindMapView._showTopicDetail('${t.topic}')">
            <span class="mm-suggest-dot" style="background:${this.getDomainColor(t.topic)}"></span>
            <span>${t.topic}</span> <span class="text-secondary">(${t.item_count} items)</span>
          </div>`).join('')}
      </div>
    `;
  },

  // ================================================================
  // TAB 5: Health Dashboard
  // ================================================================

  _renderHealth() {
    const container = document.getElementById('mm-health');
    if (!container || !this._data) return;

    container.innerHTML = `
      <div class="mm-health-grid">
        <div class="mm-health-treemap-wrap">
          <h4>Topic Proportions</h4>
          <svg id="mm-treemap-svg"></svg>
        </div>
        <div class="mm-health-side">
          <div class="mm-health-donut-wrap">
            <h4>Content Types</h4>
            <svg id="mm-donut-svg"></svg>
          </div>
          <div class="mm-health-decay-wrap">
            <h4>Decay Distribution</h4>
            <div id="mm-decay-bars"></div>
          </div>
        </div>
      </div>
    `;

    this._drawTreemap();
    this._drawDonut();
    this._drawDecayBars();
  },

  _drawTreemap() {
    const topics = this._filterTopicsBySource(this._data.topic_stats).slice(0, 80);
    const svg = d3.select('#mm-treemap-svg');
    const el = document.getElementById('mm-treemap-svg');
    if (!el) return;
    const w = el.parentElement.clientWidth || 600;
    const h = 400;
    svg.attr('width', w).attr('height', h);

    // Build hierarchy grouped by domain
    const domainMap = {};
    for (const t of topics) {
      const d = this.getDomain(t.topic);
      if (!domainMap[d]) domainMap[d] = [];
      domainMap[d].push(t);
    }

    const root = d3.hierarchy({
      name: 'root',
      children: Object.entries(domainMap).map(([domain, items]) => ({
        name: domain,
        children: items.map(t => ({ name: t.topic, value: t.item_count, data: t })),
      })),
    }).sum(d => d.value || 0);

    d3.treemap().size([w, h]).padding(2).paddingOuter(4)(root);

    const tooltip = d3.select('#mm-tooltip');
    const leaves = root.leaves();

    svg.selectAll('rect')
      .data(leaves)
      .join('rect')
      .attr('x', d => d.x0).attr('y', d => d.y0)
      .attr('width', d => d.x1 - d.x0).attr('height', d => d.y1 - d.y0)
      .attr('fill', d => this.getDomainColor(d.data.name))
      .attr('opacity', 0.8)
      .attr('rx', 2)
      .on('mouseover', (event, d) => {
        tooltip.style('display', 'block')
          .html(`<strong>${d.data.name}</strong><br>Items: ${d.value}`)
          .style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 10) + 'px');
      })
      .on('mouseout', () => tooltip.style('display', 'none'))
      .on('click', (event, d) => d.data.data?._isMemory ? this._showMemoryDetail(d.data.name) : this._showTopicDetail(d.data.name));

    // Labels for cells large enough
    svg.selectAll('.mm-treemap-label')
      .data(leaves.filter(d => (d.x1 - d.x0) > 50 && (d.y1 - d.y0) > 18))
      .join('text')
      .attr('class', 'mm-treemap-label')
      .attr('x', d => d.x0 + 4).attr('y', d => d.y0 + 14)
      .text(d => {
        const maxLen = Math.floor((d.x1 - d.x0 - 8) / 7);
        return d.data.name.length > maxLen ? d.data.name.slice(0, maxLen - 1) + '..' : d.data.name;
      });
  },

  _drawDonut() {
    const svg = d3.select('#mm-donut-svg');
    const size = 200;
    svg.attr('width', size).attr('height', size);

    const data = this._data.content_types || [];
    if (data.length === 0) return;

    const pie = d3.pie().value(d => d.count).sort(null);
    const arc = d3.arc().innerRadius(50).outerRadius(90);
    const colors = d3.scaleOrdinal(d3.schemeTableau10);

    const g = svg.append('g').attr('transform', `translate(${size / 2},${size / 2})`);

    const tooltip = d3.select('#mm-tooltip');
    g.selectAll('path')
      .data(pie(data))
      .join('path')
      .attr('d', arc)
      .attr('fill', (d, i) => colors(i))
      .attr('stroke', '#fff')
      .attr('stroke-width', 1)
      .on('mouseover', (event, d) => {
        tooltip.style('display', 'block')
          .html(`<strong>${d.data.content_type}</strong><br>Count: ${d.data.count}`)
          .style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 10) + 'px');
      })
      .on('mouseout', () => tooltip.style('display', 'none'));

    // Center text
    const total = d3.sum(data, d => d.count);
    g.append('text').attr('text-anchor', 'middle').attr('dy', '-0.2em')
      .attr('class', 'mm-donut-total').text(total);
    g.append('text').attr('text-anchor', 'middle').attr('dy', '1em')
      .attr('class', 'mm-donut-label').text('items');
  },

  _drawDecayBars() {
    const container = document.getElementById('mm-decay-bars');
    if (!container) return;
    const decay = this._data.decay_distribution || {};
    const buckets = [
      { key: 'thriving', label: 'Thriving (0.8+)', color: '#22c55e' },
      { key: 'healthy', label: 'Healthy (0.5-0.8)', color: '#3b82f6' },
      { key: 'aging', label: 'Aging (0.3-0.5)', color: '#f59e0b' },
      { key: 'fading', label: 'Fading (0.1-0.3)', color: '#f97316' },
      { key: 'forgotten', label: 'Forgotten (<0.1)', color: '#ef4444' },
    ];
    const maxVal = d3.max(buckets, b => decay[b.key] || 0) || 1;

    container.innerHTML = buckets.map(b => {
      const val = decay[b.key] || 0;
      const pct = (val / maxVal) * 100;
      return `
        <div class="mm-decay-bar-row">
          <span class="mm-decay-bar-label">${b.label}</span>
          <div class="mm-decay-bar-track">
            <div class="mm-decay-bar-fill" style="width:${pct}%;background:${b.color}"></div>
          </div>
          <span class="mm-decay-bar-val">${val}</span>
        </div>
      `;
    }).join('');
  },
};

// Make globally available
window.MindMapView = MindMapView;

// Register with Router if it exists and route not already registered
if (typeof Router !== 'undefined' && Router.routes && !Router.routes['/mind-map']) {
  Router.register('/mind-map', MindMapView);
}
