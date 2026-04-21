/* ============================================================== */
/* WORLD-CLASS UI — progress bar, celebration, glow, value flash   */
/* ============================================================== */

function createProgressBar() {
    let bar = document.getElementById('progressBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'progressBar';
        bar.className = 'progress-bar';
        document.body.prepend(bar);
    }
    return bar;
}

function showProgress(pct) {
    const bar = createProgressBar();
    bar.classList.add('active');
    bar.classList.remove('done');
    bar.style.width = `${Math.min(pct, 98)}%`;
}

function completeProgress() {
    const bar = createProgressBar();
    bar.classList.add('done');
    bar.style.width = '100%';
    setTimeout(() => { bar.classList.remove('active', 'done'); bar.style.width = '0%'; }, 800);
}

function celebrate() {
    if (prefersReducedMotion) return;
    const container = document.createElement('div');
    container.className = 'celebration-container';
    document.body.appendChild(container);

    const colors = ['#5eb6f5', '#f4a625', '#4ade80', '#ef6f7d', '#a78bfa', '#fff'];
    for (let i = 0; i < 40; i++) {
        const p = document.createElement('div');
        p.className = 'celebration-particle';
        p.style.left = `${Math.random() * 100}%`;
        p.style.top = `-${Math.random() * 10 + 5}%`;
        p.style.background = colors[Math.floor(Math.random() * colors.length)];
        p.style.width = `${Math.random() * 6 + 3}px`;
        p.style.height = p.style.width;
        p.style.animationDelay = `${Math.random() * 0.5}s`;
        p.style.animationDuration = `${1.2 + Math.random() * 1}s`;
        container.appendChild(p);
    }
    setTimeout(() => container.remove(), 2500);
}

function setupCardGlowTracking(root) {
    if (prefersReducedMotion) return;
    const cards = root.querySelectorAll('.allocation-card, .metric-card, .stress-card');
    cards.forEach(card => {
        if (card.dataset.glowReady) return;
        card.dataset.glowReady = '1';
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            card.style.setProperty('--glow-x', `${e.clientX - rect.left}px`);
            card.style.setProperty('--glow-y', `${e.clientY - rect.top}px`);
        });
    });
}

function flashValueChange(element, newVal, oldVal) {
    if (!element || prefersReducedMotion) return;
    element.classList.remove('value-flash-up', 'value-flash-down', 'value-flash');
    void element.offsetWidth;
    if (newVal > oldVal) element.classList.add('value-flash-up');
    else if (newVal < oldVal) element.classList.add('value-flash-down');
    else element.classList.add('value-flash');
}

function staggerCards(container) {
    if (prefersReducedMotion || !container) return;
    const cards = container.children;
    for (let i = 0; i < cards.length; i++) {
        // Don't add stagger to reveal-target elements — they have their own entrance animation
        if (cards[i].classList.contains('reveal-target')) {
            cards[i].style.transitionDelay = `${i * 60}ms`;
        } else {
            cards[i].classList.add('stagger-enter');
            cards[i].style.animationDelay = `${i * 60}ms`;
        }
    }
}

let portfolioChart = null;
let comparisonChart = null;
let drawdownChart = null;
let rollingSharpeChart = null;
let opsTrendChart = null;
let allocationDonutChart = null;
let sectorDonutChart = null;
let monteCarloChart = null;
let benchmarkPayload = null;
let activeBenchmarkPeriod = null;
let revealObserver = null;
let autoRefreshTimer = null;
let marketTapeTimer = null;
let opsMonitorTimer = null;
let isAutoRefreshing = false;
let latestPortfolioSnapshot = null;
let latestPortfolioPayload = null;

const previousTapePrices = new Map();

const AUTO_REFRESH_INTERVAL_MS = 10000;
const MARKET_TAPE_INTERVAL_MS = 15000;
const OPS_MONITOR_INTERVAL_MS = 15000;

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const formatCurrency = (value) =>
    `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const formatPercent = (value) =>
    `${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

const formatNumber = (value, digits = 2) =>
    Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const formatMaybePercent = (value) =>
    value === null || value === undefined || !Number.isFinite(Number(value)) ? 'N/A' : formatPercent(value);

const formatMaybeNumber = (value, digits = 2) =>
    value === null || value === undefined || !Number.isFinite(Number(value))
        ? 'N/A'
        : formatNumber(value, digits);

document.addEventListener('DOMContentLoaded', () => {
    setupStrategySelection();
    setupScenarioPresets();
    setupDemoModeToggle();
    setupFormSubmission();
    setupExportActions();
    setupRevealObserver();
    setupTiltEffects(document);
    revealStaticTargets();
    setupCursorGlow();
    setupKeyboardShortcuts();
    setupResultsTabs();
    setupMobileFormToggle();
    setupAmountValidation();
    setupThemeToggle();
    setupShareButton();
    setupSavedPortfolios();
    setupCompareTab();
    setupOnboardingTour();
    setupRiskProfile();
    autoLoadFromShareLink();
    refreshMarketTape();
    startMarketTape();
    refreshOpsMonitor();
    startOpsMonitorPolling();

    window.addEventListener('beforeunload', () => {
        stopAutoRefresh();
        stopMarketTape();
        stopOpsMonitorPolling();
    });
});

function setupCursorGlow() {
    const glow = document.getElementById('cursorGlow');
    if (!glow || prefersReducedMotion) {
        return;
    }

    window.addEventListener('mousemove', (event) => {
        document.body.style.setProperty('--mx', `${event.clientX}px`);
        document.body.style.setProperty('--my', `${event.clientY}px`);
        glow.style.opacity = '1';
        glow.style.transform = `translate(${event.clientX - 120}px, ${event.clientY - 120}px)`;
    });

    window.addEventListener('mouseleave', () => {
        glow.style.opacity = '0';
    });
}

function setupRevealObserver() {
    if (prefersReducedMotion) {
        return;
    }

    revealObserver = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('reveal-visible');
                    revealObserver.unobserve(entry.target);
                }
            });
        },
        {
            threshold: 0.14,
            rootMargin: '0px 0px -8% 0px'
        }
    );
}

function observeRevealElement(element) {
    if (!element || !element.classList.contains('reveal-target')) {
        return;
    }

    if (prefersReducedMotion) {
        element.classList.add('reveal-visible');
        return;
    }

    if (!revealObserver) {
        element.classList.add('reveal-visible');
        return;
    }

    revealObserver.observe(element);
}

function revealStaticTargets() {
    const targets = Array.from(document.querySelectorAll('.reveal-target'));
    targets.forEach((target, index) => {
        target.style.transitionDelay = `${Math.min(index * 32, 320)}ms`;
        observeRevealElement(target);
    });
}

function setupTiltEffects(root = document) {
    if (prefersReducedMotion) {
        return;
    }

    const tiltNodes = root.querySelectorAll('[data-tilt]');
    tiltNodes.forEach((node) => {
        if (node.dataset.tiltReady === '1') {
            return;
        }

        node.dataset.tiltReady = '1';
        node.addEventListener('mousemove', (event) => {
            const rect = node.getBoundingClientRect();
            const px = (event.clientX - rect.left) / rect.width - 0.5;
            const py = (event.clientY - rect.top) / rect.height - 0.5;
            const rotateY = px * 7;
            const rotateX = -py * 7;
            node.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(0)`;
        });

        node.addEventListener('mouseleave', () => {
            node.style.transform = '';
        });
    });
}

function setLoadingState(enabled) {
    document.body.classList.toggle('is-loading', enabled);
    if (enabled) {
        renderAllocationSkeletons();
    }
}

function renderAllocationSkeletons(count = 6) {
    const grid = document.getElementById('allocationsGrid');
    if (!grid) {
        return;
    }

    grid.innerHTML = '';
    for (let i = 0; i < count; i += 1) {
        const card = document.createElement('article');
        card.className = 'allocation-card skeleton-card';
        card.innerHTML = `
            <div class="skeleton-line w-40"></div>
            <div class="skeleton-line w-80"></div>
            <div class="skeleton-grid">
                <div class="skeleton-line w-60"></div>
                <div class="skeleton-line w-50"></div>
                <div class="skeleton-line w-70"></div>
                <div class="skeleton-line w-55"></div>
            </div>
        `;
        grid.appendChild(card);
    }
}

function parseNumberFromText(text) {
    const sanitized = String(text).replace(/[^0-9.-]/g, '');
    const parsed = Number(sanitized);
    return Number.isFinite(parsed) ? parsed : 0;
}

function animateValue(element, targetValue, formatter, duration = 860) {
    if (!element) {
        return;
    }
    if (!Number.isFinite(Number(targetValue))) {
        element.textContent = 'N/A';
        return;
    }

    const target = Number(targetValue);
    const start = Number.isFinite(Number(element.dataset.value))
        ? Number(element.dataset.value)
        : parseNumberFromText(element.textContent);

    if (prefersReducedMotion) {
        element.textContent = formatter(target);
        element.dataset.value = String(target);
        return;
    }

    const startTime = performance.now();
    const delta = target - start;

    const step = (now) => {
        const progress = Math.min(1, (now - startTime) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + delta * eased;
        element.textContent = formatter(current);

        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            element.dataset.value = String(target);
        }
    };

    requestAnimationFrame(step);
}

function clearActivePresets() {
    document.querySelectorAll('.preset-btn').forEach((button) => button.classList.remove('active'));
}

function applyStrategiesToUI(strategies = []) {
    document.querySelectorAll('.strategy-card').forEach((card) => {
        const selected = strategies.includes(card.dataset.strategy);
        card.classList.toggle('selected', selected);
        const checkbox = card.querySelector('input[type="checkbox"]');
        checkbox.checked = selected;
    });
}

function setupScenarioPresets() {
    const presets = {
        conservative: {
            amount: 12000,
            strategies: ['Index Investing', 'Quality Investing']
        },
        balanced: {
            amount: 10000,
            strategies: ['Ethical Investing', 'Index Investing']
        },
        aggressive: {
            amount: 10000,
            strategies: ['Growth Investing', 'Value Investing']
        }
    };

    document.querySelectorAll('.preset-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const presetKey = button.dataset.preset;
            const preset = presets[presetKey];
            if (!preset) {
                return;
            }

            document.getElementById('investmentAmount').value = preset.amount;
            applyStrategiesToUI(preset.strategies);
            clearActivePresets();
            button.classList.add('active');
            hideError();
        });
    });
}

function setupDemoModeToggle() {
    const toggle = document.getElementById('demoModeToggle');
    const statusNode = document.getElementById('demoModeStatus');
    if (!toggle || !statusNode) {
        return;
    }

    const setToggleState = (enabled) => {
        toggle.checked = Boolean(enabled);
        statusNode.textContent = enabled ? 'Enabled' : 'Disabled';
    };

    toggle.addEventListener('change', async () => {
        try {
            const response = await fetch('/demo-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: toggle.checked })
            });
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.error || 'Unable to update demo mode');
            }
            setToggleState(payload.demo_mode_enabled);
            refreshMarketTape();
            refreshOpsMonitor();
        } catch (error) {
            showError(error.message);
            toggle.checked = !toggle.checked;
        }
    });

    fetch('/demo-mode')
        .then((response) => response.json())
        .then((payload) => setToggleState(payload.demo_mode_enabled))
        .catch(() => {
            /* no-op */
        });
}

function startOpsMonitorPolling() {
    stopOpsMonitorPolling();
    opsMonitorTimer = setInterval(refreshOpsMonitor, OPS_MONITOR_INTERVAL_MS);
}

function stopOpsMonitorPolling() {
    if (opsMonitorTimer) {
        clearInterval(opsMonitorTimer);
        opsMonitorTimer = null;
    }
}

async function refreshOpsMonitor() {
    try {
        const response = await fetch('/ops-monitor');
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || 'Ops monitor unavailable');
        }
        displayOpsMonitoring(payload);
    } catch (error) {
        const summary = document.getElementById('opsSummary');
        if (summary) {
            summary.textContent = `Monitoring unavailable: ${error.message}`;
        }
    }
}

function setupStrategySelection() {
    const strategyCards = document.querySelectorAll('.strategy-card');
    const toggleCard = (card) => {
        clearActivePresets();
        const checkbox = card.querySelector('input[type="checkbox"]');
        const selectedCount = document.querySelectorAll('.strategy-card.selected').length;

        if (!card.classList.contains('selected') && selectedCount >= 2) {
            showError('You can select a maximum of 2 investment strategies.');
            return;
        }

        card.classList.toggle('selected');
        const nowSelected = card.classList.contains('selected');
        if (checkbox) checkbox.checked = nowSelected;
        card.setAttribute('aria-checked', nowSelected ? 'true' : 'false');
        hideError();
    };

    strategyCards.forEach((card) => {
        card.addEventListener('click', () => toggleCard(card));
        card.addEventListener('keydown', (event) => {
            if (event.key === ' ' || event.key === 'Enter') {
                event.preventDefault();
                toggleCard(card);
            }
        });
    });
}

function setupFormSubmission() {
    const form = document.getElementById('portfolioForm');
    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const amount = parseFloat(document.getElementById('investmentAmount').value);
        const selectedStrategies = Array.from(document.querySelectorAll('.strategy-card.selected')).map(
            (card) => card.dataset.strategy
        );

        if (amount < 5000) {
            showError('Minimum investment amount is $5,000.');
            return;
        }

        if (selectedStrategies.length === 0 || selectedStrategies.length > 2) {
            showError('Please select 1 or 2 investment strategies.');
            return;
        }

        hideError();
        stopAutoRefresh();
        setLoadingState(true);
        showProgress(15);

        const button = document.getElementById('generateBtn');
        const originalLabel = button.textContent;
        button.textContent = 'Model Running...';
        button.classList.add('loading');
        button.disabled = true;

        try {
            showProgress(35);
            const body = {
                amount,
                strategies: selectedStrategies,
            };
            const profilePayload = collectRiskProfilePayload();
            if (profilePayload) {
                body.risk_profile = profilePayload;
            }
            showProgress(50);
            const response = await fetch('/generate-portfolio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            showProgress(85);
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.error || 'Failed to generate portfolio.');
            }

            showProgress(95);
            displayResults(payload, { silent: false });
            completeProgress();
            celebrate();
        } catch (error) {
            showError(error.message);
            completeProgress();
        } finally {
            button.textContent = originalLabel;
            button.classList.remove('loading');
            button.disabled = false;
            setLoadingState(false);
        }
    });
}

function setMetaLineValue(node, value) {
    if (!node) return;
    const valueSpan = node.querySelector('span:last-child');
    if (valueSpan) {
        valueSpan.textContent = value;
    } else {
        node.textContent = value;
    }
}

function setRefreshStatus(message, isError = false) {
    const statusNode = document.getElementById('refreshStatus');
    if (!statusNode) {
        return;
    }
    setMetaLineValue(statusNode, message);
    statusNode.classList.toggle('status-error', isError);
    pulseLiveIndicator(isError);
}

function pulseLiveIndicator(isError = false) {
    const node = document.getElementById('liveIndicator');
    if (!node) return;
    node.classList.toggle('live-error', isError);
    node.classList.remove('live-pulse');
    // Re-trigger the animation
    void node.offsetWidth;
    node.classList.add('live-pulse');
}

function buildRefreshPayload() {
    if (!latestPortfolioSnapshot) {
        return null;
    }

    const sanitizeAllocation = (allocation) => ({
        ticker: allocation.ticker,
        name: allocation.name,
        strategy: allocation.strategy,
        asset_type: allocation.asset_type,
        rationale: allocation.rationale,
        conviction: allocation.conviction,
        annualized_volatility: allocation.annualized_volatility,
        weight: allocation.weight,
        weight_pct: allocation.weight_pct,
        shares: allocation.shares,
        price: allocation.price,
        cost: allocation.cost,
        current_price: allocation.current_price,
        current_value: allocation.current_value,
        quote_source: allocation.quote_source,
        quote_is_stale: allocation.quote_is_stale
    });

    return {
        portfolio_id: latestPortfolioSnapshot.portfolio_id,
        investment_amount: latestPortfolioSnapshot.investment_amount,
        strategies: latestPortfolioSnapshot.strategies,
        allocation_method: latestPortfolioSnapshot.allocation_method,
        cash_remainder: latestPortfolioSnapshot.cash_remainder,
        total_allocated: latestPortfolioSnapshot.total_allocated,
        allocations: (latestPortfolioSnapshot.allocations || []).map(sanitizeAllocation)
    };
}

function buildCsvExportPayload(portfolio) {
    if (!portfolio) {
        return null;
    }

    return {
        investment_amount: portfolio.investment_amount || 0,
        total_value: portfolio.total_value || 0,
        cash_remainder: portfolio.cash_remainder || 0,
        strategies: portfolio.strategies || [],
        allocations: portfolio.allocations || []
    };
}

function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}

function startAutoRefresh() {
    stopAutoRefresh();

    if (!latestPortfolioSnapshot || !latestPortfolioSnapshot.allocations?.length) {
        setRefreshStatus('Auto-refresh: idle');
        return;
    }

    setRefreshStatus(`Auto-refresh every 10s · Last update ${new Date().toLocaleTimeString()}`);
    autoRefreshTimer = setInterval(refreshPortfolioLive, AUTO_REFRESH_INTERVAL_MS);
}

async function refreshPortfolioLive() {
    if (isAutoRefreshing) {
        return;
    }

    const payload = buildRefreshPayload();
    if (!payload) {
        return;
    }

    isAutoRefreshing = true;
    try {
        const response = await fetch('/refresh-portfolio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const refreshed = await response.json();
        if (!response.ok) {
            throw new Error(refreshed.error || 'Live refresh failed');
        }

        displayResults(refreshed, { silent: true, fromAutoRefresh: true });
        setRefreshStatus(`Auto-refresh every 10s · Last update ${new Date().toLocaleTimeString()}`);
    } catch (error) {
        setRefreshStatus(`Auto-refresh error: ${error.message}`, true);
    } finally {
        isAutoRefreshing = false;
    }
}

function startMarketTape() {
    stopMarketTape();
    marketTapeTimer = setInterval(refreshMarketTape, MARKET_TAPE_INTERVAL_MS);
}

function stopMarketTape() {
    if (marketTapeTimer) {
        clearInterval(marketTapeTimer);
        marketTapeTimer = null;
    }
}

function topHoldingSymbolsForTape() {
    const allocations = latestPortfolioSnapshot?.allocations || [];
    if (!allocations.length) {
        return [];
    }

    return [...allocations]
        .sort((a, b) => (b.current_value || b.cost || 0) - (a.current_value || a.cost || 0))
        .slice(0, 2)
        .map((allocation) => allocation.ticker);
}

async function refreshMarketTape() {
    try {
        const response = await fetch('/market-ticker', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ holdings: topHoldingSymbolsForTape() })
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || 'Failed to load market tape');
        }

        renderMarketTape(payload.entries || []);
    } catch (error) {
        const track = document.getElementById('ribbonTrack');
        if (track && !track.dataset.loaded) {
            track.innerHTML = '<span>Live tape unavailable</span>';
        }
    }
}

function tapePriceFormat(symbol, price) {
    if (symbol === '^TNX' || symbol === '^VIX' || symbol === 'DX-Y.NYB') {
        return formatNumber(price, 2);
    }
    return formatNumber(price, 2);
}

function renderMarketTape(entries) {
    const track = document.getElementById('ribbonTrack');
    if (!track || entries.length === 0) {
        return;
    }

    const createTokenText = (entry) => {
        const change = Number(entry.change_pct);
        const hasChange = Number.isFinite(change);
        const signedChange = hasChange ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : 'N/A';
        return `${entry.label} ${tapePriceFormat(entry.symbol, entry.price)} ${signedChange}`;
    };

    const buildTokenClass = (entry) => {
        const change = Number(entry.change_pct);
        if (!Number.isFinite(change)) {
            return 'tape-neutral';
        }
        return change >= 0 ? 'tape-up' : 'tape-down';
    };

    const fragment = document.createDocumentFragment();
    const renderPasses = 2;

    for (let pass = 0; pass < renderPasses; pass += 1) {
        entries.forEach((entry) => {
            const span = document.createElement('span');
            const baseClass = buildTokenClass(entry);
            span.classList.add(baseClass);
            span.textContent = createTokenText(entry);

            const previous = previousTapePrices.get(entry.symbol);
            if (previous !== undefined && Number(entry.price) !== previous) {
                span.classList.add(Number(entry.price) > previous ? 'flash-up' : 'flash-down');
            }

            fragment.appendChild(span);
        });
    }

    track.innerHTML = '';
    track.appendChild(fragment);
    track.dataset.loaded = '1';

    entries.forEach((entry) => {
        previousTapePrices.set(entry.symbol, Number(entry.price));
    });
}

function displayResults(portfolio, options = {}) {
    const { silent = false, fromAutoRefresh = false } = options;
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.style.display = 'block';

    animateValue(document.getElementById('portfolioValue'), portfolio.total_value || 0, formatCurrency, 1500);

    const headerEl = document.querySelector('.results-header.gradient-border');
    if (headerEl && !silent) {
        headerEl.classList.add('gradient-active');
        setTimeout(() => headerEl.classList.remove('gradient-active'), 3000);
    }

    document.getElementById('selectedStrategies').textContent = (portfolio.strategies || []).join(' + ');
    document.getElementById('allocationMethod').textContent = portfolio.allocation_method || 'N/A';

    renderHeaderMeta(portfolio);
    displayMetrics(portfolio.metrics || {});
    displayAllocations(portfolio.allocations || []);
    displayTrendChart(portfolio.trend_data || { dates: [], values: [] });
    displayComparisonTrendChart(portfolio.comparison_trend || {});
    displayBenchmarkComparison(portfolio.benchmark_comparison || {});
    displayBacktests(portfolio.backtest_analysis || {});
    displayExplainability(portfolio.explainability || {});
    displayMicrostructureRisk(portfolio.microstructure_risk || {});
    displayRebalancing(portfolio.rebalancing_recommendations || {});
    displayDataQuality(portfolio.data_quality || {}, portfolio.analysis_quality_warnings || []);
    displayAllocationDonut(portfolio.allocations || []);
    displaySectorExposure(portfolio.sector_exposure || {});
    displayCorrelationMatrix(portfolio.correlation_matrix || {});
    displayMonteCarlo(portfolio.monte_carlo || {});
    displayNarrative(portfolio.narrative || {});
    displayActionPlan(portfolio.action_plan || {});
    displayStressTests(portfolio.microstructure_risk || {});
    displayRiskProfilePill(portfolio.risk_profile || null);
    setupGoalTracker(portfolio.monte_carlo || {}, portfolio.total_value || 0);
    setupTweakWorkbench(portfolio.tweak_workbench || {}, portfolio.total_value || 0);
    displayOpsMonitoring(portfolio.ops_monitor || {});

    latestPortfolioSnapshot = {
        portfolio_id: portfolio.portfolio_id,
        investment_amount: portfolio.investment_amount,
        strategies: portfolio.strategies || [],
        allocation_method: portfolio.allocation_method,
        cash_remainder: portfolio.cash_remainder || 0,
        total_allocated: portfolio.total_allocated || 0,
        allocations: (portfolio.allocations || []).map((allocation) => ({ ...allocation }))
    };

    latestPortfolioPayload = JSON.parse(JSON.stringify(portfolio));

    setupTiltEffects(resultsSection);
    setupCardGlowTracking(resultsSection);

    const prevValue = latestPortfolioSnapshot?.total_value || 0;
    const newValue = portfolio.total_value || 0;
    if (fromAutoRefresh && prevValue !== newValue) {
        flashValueChange(document.getElementById('portfolioValue'), newValue, prevValue);
    }

    if (!silent) {
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (!fromAutoRefresh) {
        startAutoRefresh();
        refreshMarketTape();
    }
}

function renderHeaderMeta(portfolio) {
    const lastUpdateNode = document.getElementById('lastUpdatedLine');
    const sourceLineNode = document.getElementById('sourceBadgeLine');

    if (lastUpdateNode) {
        const value = portfolio.last_updated ? new Date(portfolio.last_updated).toLocaleString() : new Date().toLocaleString();
        setMetaLineValue(lastUpdateNode, value);
    }

    if (sourceLineNode) {
        const quality = portfolio.data_quality || {};
        const sources = new Set();
        (portfolio.allocations || []).forEach((allocation) => {
            if (allocation.quote_source) {
                sources.add(allocation.quote_source);
            }
        });

        const sourceLabel = sources.size ? Array.from(sources).join(', ') : 'N/A';
        const demoLabel = (portfolio.demo_mode_enabled || quality.demo_mode_enabled) ? 'DEMO ON' : 'DEMO OFF';
        setMetaLineValue(
            sourceLineNode,
            `${sourceLabel} · ${quality.market_status || 'UNKNOWN'} · Rel ${(quality.average_reliability || 0).toFixed(2)} · ${demoLabel}`
        );
    }
}

function displayMetrics(metrics) {
    animateValue(document.getElementById('metricInvested'), metrics.invested_capital || 0, formatCurrency);
    animateValue(document.getElementById('metricCash'), metrics.cash_remainder || 0, formatCurrency);

    const pnlElement = document.getElementById('metricPnL');
    const pnlValue = metrics.unrealized_pnl || 0;
    animateValue(pnlElement, pnlValue, formatCurrency);
    pnlElement.classList.toggle('metric-positive', pnlValue >= 0);
    pnlElement.classList.toggle('metric-negative', pnlValue < 0);

    const returnElement = document.getElementById('metricReturn');
    const returnValue = metrics.unrealized_return_pct || 0;
    animateValue(returnElement, returnValue, formatPercent);
    returnElement.classList.toggle('metric-positive', returnValue >= 0);
    returnElement.classList.toggle('metric-negative', returnValue < 0);

    animateValue(
        document.getElementById('metricDiversification'),
        metrics.diversification_score || 0,
        (value) => Number(value).toFixed(2)
    );

    const largestTicker = metrics.largest_position_ticker || '-';
    const largestWeight = formatPercent(metrics.largest_position_weight_pct || 0);
    document.getElementById('metricLargest').textContent = `${largestTicker} (${largestWeight})`;

    const metricsGrid = document.getElementById('metricsGrid');
    if (metricsGrid) {
        staggerCards(metricsGrid);
        setupCardGlowTracking(metricsGrid);
    }
}

function displayAllocations(allocations) {
    const grid = document.getElementById('allocationsGrid');
    grid.innerHTML = '';

    allocations.forEach((allocation, index) => {
        const card = document.createElement('article');
        card.className = 'allocation-card reveal-target';
        card.setAttribute('data-tilt', '');
        card.style.transitionDelay = `${Math.min(index * 44, 360)}ms`;
        card.style.position = 'relative';
        card.style.overflow = 'hidden';

        const currentPrice = allocation.current_price || allocation.price;
        const currentValue = allocation.current_value || allocation.cost;
        const volatilityPct = (allocation.annualized_volatility || 0) * 100;
        const positionReturnPct = Number(allocation.position_return_pct || 0);
        const attrClass = positionReturnPct > 0.05 ? 'attribution-pos' : (positionReturnPct < -0.05 ? 'attribution-neg' : 'attribution-flat');
        const attrSign = positionReturnPct >= 0 ? '+' : '';

        const newsItems = Array.isArray(allocation.news) ? allocation.news : [];
        const newsHtml = newsItems.length
            ? `
                <div class="holding-news">
                    <div class="holding-news-title">Recent news</div>
                    ${newsItems.map((item) => {
                        const safeTitle = (item.title || '').replace(/</g, '&lt;');
                        const source = (item.publisher || '').replace(/</g, '&lt;');
                        const url = item.url ? item.url.replace(/"/g, '&quot;') : '';
                        const link = url
                            ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${safeTitle}<span class="news-source"> · ${source}</span></a>`
                            : `<a class="news-no-link">${safeTitle}<span class="news-source"> · ${source}</span></a>`;
                        return link;
                    }).join('')}
                </div>
            `
            : '';

        card.innerHTML = `
            <canvas class="sparkline-bg" width="200" height="80" style="position: absolute; bottom: 0; left: 0; width: 100%; height: 60%; z-index: 0; pointer-events: none; opacity: 0.6;"></canvas>
            <span class="attribution-chip ${attrClass}" title="Position return since allocation">${attrSign}${positionReturnPct.toFixed(2)}%</span>
            <div class="stock-header">
                <div>
                    <div class="stock-ticker">_</div>
                    <div class="stock-name">_</div>
                </div>
                <span class="asset-badge">${allocation.asset_type || 'Stock'}</span>
            </div>
            <p class="stock-rationale">${allocation.rationale || ''}</p>
            <div class="stock-details">
                <div class="detail-item">
                    <div class="detail-label">Strategy</div>
                    <div class="detail-value">${allocation.strategy || '-'}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Weight</div>
                    <div class="detail-value">${formatPercent(allocation.weight_pct || 0)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Shares</div>
                    <div class="detail-value">${Number(allocation.shares).toFixed(4)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Price</div>
                    <div class="detail-value">${formatCurrency(currentPrice)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Conviction</div>
                    <div class="detail-value">${Number(allocation.conviction || 0).toFixed(2)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Volatility</div>
                    <div class="detail-value">${formatPercent(volatilityPct)}</div>
                </div>
            </div>
            <div class="weight-bar"><div class="weight-bar-fill" style="width: ${Math.min(allocation.weight_pct || 0, 100)}%"></div></div>
            ${newsHtml}
        `;

        // Decrypt text effect for ticker and name
        const tickerNode = card.querySelector('.stock-ticker');
        const nameNode = card.querySelector('.stock-name');
        decryptText(tickerNode, allocation.ticker, 600 + index * 100);
        decryptText(nameNode, allocation.name, 900 + index * 100);
        
        // Draw sparkline
        const sparkCanvas = card.querySelector('.sparkline-bg');
        if (sparkCanvas) {
            drawSparkline(sparkCanvas, volatilityPct);
        }

        grid.appendChild(card);
        observeRevealElement(card);
    });

    staggerCards(grid);
    setupCardGlowTracking(grid);
}

function displayTrendChart(trendData) {
    const canvas = document.getElementById('portfolioChart');
    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext('2d');
    if (portfolioChart) {
        portfolioChart.destroy();
    }

    const gradient = ctx.createLinearGradient(0, 0, 0, 280);
    gradient.addColorStop(0, 'rgba(45, 199, 232, 0.36)');
    gradient.addColorStop(0.5, 'rgba(91, 137, 255, 0.22)');
    gradient.addColorStop(1, 'rgba(244, 166, 37, 0.08)');

    portfolioChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: trendData.dates || [],
            datasets: [
                {
                    label: 'Portfolio Value',
                    data: trendData.values || [],
                    borderColor: '#58cbff',
                    backgroundColor: gradient,
                    fill: true,
                    borderWidth: 3,
                    tension: 0.35,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    pointBackgroundColor: '#08121c',
                    pointBorderColor: '#80d8ff',
                    pointBorderWidth: 2
                }
            ]
        },
        options: {
            maintainAspectRatio: true,
            responsive: true,
            animation: {
                duration: prefersReducedMotion ? 0 : 900,
                easing: 'easeOutQuart'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0b1420',
                    titleColor: '#ebf6ff',
                    bodyColor: '#ebf6ff',
                    borderColor: '#2d3e54',
                    borderWidth: 1,
                    displayColors: false,
                    callbacks: {
                        label: (context) => formatCurrency(context.parsed.y)
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        color: '#8ea9c3',
                        callback: (value) => `$${Number(value).toLocaleString('en-US')}`
                    },
                    grid: { color: 'rgba(143, 169, 195, 0.14)' }
                },
                x: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.07)' }
                }
            }
        }
    });
}

function computeDrawdown(values = []) {
    let runningMax = -Infinity;
    return values.map((value) => {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return null;
        }
        if (numericValue > runningMax) {
            runningMax = numericValue;
        }
        if (runningMax <= 0) {
            return 0;
        }
        return ((numericValue / runningMax) - 1) * 100;
    });
}

function computeRollingSharpe(values = [], windowSize = 10) {
    if (!values || values.length < 3) {
        return values.map(() => null);
    }

    const returns = [];
    for (let i = 1; i < values.length; i += 1) {
        const prev = Number(values[i - 1]);
        const curr = Number(values[i]);
        if (!Number.isFinite(prev) || !Number.isFinite(curr) || prev === 0) {
            returns.push(null);
            continue;
        }
        returns.push((curr - prev) / prev);
    }

    const sharpeSeries = [null];
    for (let i = 0; i < returns.length; i += 1) {
        const windowStart = Math.max(0, i - windowSize + 1);
        const windowReturns = returns.slice(windowStart, i + 1).filter((item) => Number.isFinite(item));

        if (windowReturns.length < 3) {
            sharpeSeries.push(null);
            continue;
        }

        const mean = windowReturns.reduce((acc, value) => acc + value, 0) / windowReturns.length;
        const variance =
            windowReturns.reduce((acc, value) => acc + (value - mean) ** 2, 0) / (windowReturns.length - 1);
        const std = Math.sqrt(Math.max(variance, 0));

        if (std === 0) {
            sharpeSeries.push(null);
            continue;
        }

        sharpeSeries.push((mean / std) * Math.sqrt(252));
    }

    return sharpeSeries;
}

function displayComparisonTrendChart(comparisonTrend) {
    const dates = comparisonTrend.dates || [];
    const portfolioValues = comparisonTrend.portfolio || [];
    const sp500Values = comparisonTrend.sp500 || [];
    const sixtyFortyValues = comparisonTrend.sixty_forty || [];

    const comparisonCanvas = document.getElementById('comparisonChart');
    const drawdownCanvas = document.getElementById('drawdownChart');
    const rollingCanvas = document.getElementById('rollingSharpeChart');
    if (!comparisonCanvas || !drawdownCanvas || !rollingCanvas) {
        return;
    }

    if (comparisonChart) {
        comparisonChart.destroy();
    }
    if (drawdownChart) {
        drawdownChart.destroy();
    }
    if (rollingSharpeChart) {
        rollingSharpeChart.destroy();
    }

    comparisonChart = new Chart(comparisonCanvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: 'Portfolio',
                    data: portfolioValues,
                    borderColor: '#58cbff',
                    borderWidth: 2.8,
                    pointRadius: 0,
                    tension: 0.24
                },
                {
                    label: 'S&P 500 (SPY)',
                    data: sp500Values,
                    borderColor: '#31cd76',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.24
                },
                {
                    label: '60/40 (SPY/AGG)',
                    data: sixtyFortyValues,
                    borderColor: '#f4a625',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.24
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    labels: { color: '#d4e7fa' }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.dataset.label}: ${formatCurrency(context.parsed.y)}`
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        color: '#8ea9c3',
                        callback: (value) => `$${Number(value).toLocaleString('en-US')}`
                    },
                    grid: { color: 'rgba(143, 169, 195, 0.12)' }
                },
                x: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.05)' }
                }
            }
        }
    });

    const drawdownValues = computeDrawdown(portfolioValues);
    drawdownChart = new Chart(drawdownCanvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: 'Drawdown %',
                    data: drawdownValues,
                    borderColor: '#ff7b86',
                    backgroundColor: 'rgba(246, 111, 114, 0.16)',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.25
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    ticks: {
                        color: '#8ea9c3',
                        callback: (value) => `${Number(value).toFixed(1)}%`
                    },
                    grid: { color: 'rgba(143, 169, 195, 0.1)' }
                },
                x: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.04)' }
                }
            }
        }
    });

    const rollingSharpeValues = computeRollingSharpe(portfolioValues, 10);
    rollingSharpeChart = new Chart(rollingCanvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: 'Rolling Sharpe',
                    data: rollingSharpeValues,
                    borderColor: '#9d9cff',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.25
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.1)' }
                },
                x: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.04)' }
                }
            }
        }
    });
}

function displayBenchmarkComparison(benchmarkComparison) {
    benchmarkPayload = benchmarkComparison || {};
    const tabsContainer = document.getElementById('benchmarkPeriodTabs');
    const tableBody = document.getElementById('benchmarkTableBody');
    tabsContainer.innerHTML = '';
    tableBody.innerHTML = '';

    const periods = Object.keys(benchmarkPayload.periods || {});
    if (periods.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="7">No benchmark data available.</td></tr>';
        return;
    }

    if (!activeBenchmarkPeriod || !periods.includes(activeBenchmarkPeriod)) {
        if (benchmarkPayload.default_period && periods.includes(benchmarkPayload.default_period)) {
            activeBenchmarkPeriod = benchmarkPayload.default_period;
        } else {
            activeBenchmarkPeriod = periods[0];
        }
    }

    periods.forEach((period, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `period-tab ${period === activeBenchmarkPeriod ? 'active' : ''}`;
        button.textContent = period;
        button.style.transitionDelay = `${index * 30}ms`;
        button.addEventListener('click', () => {
            activeBenchmarkPeriod = period;
            displayBenchmarkComparison(benchmarkPayload);
        });
        tabsContainer.appendChild(button);
    });

    const selected = benchmarkPayload.periods[activeBenchmarkPeriod];
    if (!selected || selected.status !== 'ok' || !selected.rows || selected.rows.length === 0) {
        tableBody.innerHTML =
            '<tr><td colspan="7">Insufficient historical data for this horizon.</td></tr>';
        return;
    }

    selected.rows.forEach((row, index) => {
        const tr = document.createElement('tr');
        tr.className = 'reveal-target';
        tr.style.transitionDelay = `${Math.min(index * 36, 240)}ms`;
        tr.innerHTML = `
            <td>${row.label}</td>
            <td>${formatMaybePercent(row.annual_return_pct)}</td>
            <td>${formatMaybePercent(row.annual_volatility_pct)}</td>
            <td>${formatMaybeNumber(row.sharpe)}</td>
            <td>${formatMaybePercent(row.max_drawdown_pct)}</td>
            <td>${formatMaybePercent(row.alpha_pct)}</td>
            <td>${formatMaybeNumber(row.beta)}</td>
        `;
        tableBody.appendChild(tr);
        observeRevealElement(tr);
    });
}

function displayBacktests(backtestAnalysis) {
    const configText = document.getElementById('backtestConfigText');
    const grid = document.getElementById('backtestGrid');
    grid.innerHTML = '';

    const config = backtestAnalysis.configuration || {};
    const transactionCost = config.transaction_cost_bps ?? 0;
    const rebalanceFreq = config.rebalance_frequency || 'N/A';
    configText.textContent =
        `Assumptions: ${transactionCost} bps transaction cost, ${rebalanceFreq} rebalancing.`;

    const periods = backtestAnalysis.periods || [];
    if (periods.length === 0) {
        grid.innerHTML = '<p class="panel-subtitle">No backtest periods available.</p>';
        return;
    }

    periods.forEach((period, index) => {
        const card = document.createElement('article');
        card.className = 'backtest-card reveal-target';
        card.setAttribute('data-tilt', '');
        card.style.transitionDelay = `${Math.min(index * 50, 260)}ms`;

        if (period.status && period.status !== 'ok') {
            card.innerHTML = `
                <h3>${period.period}</h3>
                <p class="panel-subtitle">${period.reason || 'Insufficient data.'}</p>
            `;
            grid.appendChild(card);
            observeRevealElement(card);
            return;
        }

        card.innerHTML = `
            <h3>${period.period}</h3>
            <div class="backtest-metrics">
                <p><span>Return:</span> ${formatPercent(period.portfolio_total_return_pct || 0)}</p>
                <p><span>Sharpe:</span> ${formatNumber(period.portfolio_sharpe || 0)}</p>
                <p><span>Drawdown:</span> ${formatPercent(period.portfolio_max_drawdown_pct || 0)}</p>
                <p><span>Turnover:</span> ${formatPercent(period.turnover_pct || 0)}</p>
                <p><span>Txn Cost:</span> ${formatPercent(period.transaction_cost_paid_pct || 0)}</p>
                <p><span>Rebalances:</span> ${period.rebalance_count || 0}</p>
            </div>
        `;
        grid.appendChild(card);
        observeRevealElement(card);
    });
}

function displayExplainability(explainability) {
    const riskProfileLine = document.getElementById('riskProfileLine');
    const summaryLine = document.getElementById('explainabilitySummary');
    const methodologyLine = document.getElementById('methodologyLine');
    const driversList = document.getElementById('explainabilityDrivers');

    riskProfileLine.textContent = `Risk Profile: ${explainability.risk_profile || 'N/A'}`;
    summaryLine.textContent = explainability.summary || 'Explainability summary unavailable.';
    methodologyLine.textContent = explainability.methodology || '';

    driversList.innerHTML = '';
    const drivers = explainability.top_drivers || [];
    if (!drivers.length) {
        driversList.innerHTML = '<li>No position drivers available.</li>';
        return;
    }

    drivers.forEach((driver) => {
        const li = document.createElement('li');
        li.textContent = driver;
        driversList.appendChild(li);
    });
}

function displayMicrostructureRisk(payload) {
    const grid = document.getElementById('riskControlGrid');
    const summary = document.getElementById('riskControlSummary');
    const breachList = document.getElementById('riskBreachList');
    if (!grid || !summary || !breachList) {
        return;
    }

    grid.innerHTML = '';
    breachList.innerHTML = '';

    const execution = payload.execution_summary || {};
    const varCvar = payload.var_cvar || {};
    const stressTests = payload.stress_tests || {};
    const worstStressPct = stressTests.worst_case_pct;

    const cards = [
        { label: 'Expected Cost', value: formatCurrency(execution.expected_total_cost || 0) },
        { label: 'Expected Cost (bps)', value: formatNumber(execution.expected_total_cost_bps || 0, 2) },
        { label: 'Largest Execution Cost', value: formatCurrency(execution.largest_execution_cost || 0) },
        { label: 'Daily VaR', value: formatMaybePercent(varCvar.daily_var_pct) },
        { label: 'Daily CVaR', value: formatMaybePercent(varCvar.daily_cvar_pct) },
        { label: 'Ann. Volatility', value: formatMaybePercent(varCvar.annualized_volatility_pct) },
        { label: 'Worst Stress', value: formatMaybePercent(worstStressPct) }
    ];

    cards.forEach((card, index) => {
        const node = document.createElement('article');
        node.className = 'quality-card reveal-target';
        node.setAttribute('data-tilt', '');
        node.style.transitionDelay = `${Math.min(index * 36, 200)}ms`;
        node.innerHTML = `
            <h3>${card.label}</h3>
            <p>${card.value}</p>
        `;
        grid.appendChild(node);
        observeRevealElement(node);
    });

    const breaches = payload.limit_breaches || [];
    const stressRows = stressTests.scenarios || [];
    if (!breaches.length && !stressRows.length) {
        summary.textContent = 'Risk limits within configured thresholds.';
        breachList.innerHTML = '<li>No active limit breaches.</li>';
        return;
    }

    const summaryParts = [];
    if (breaches.length) {
        summaryParts.push(`${breaches.length} risk limit breach(es) detected`);
    } else {
        summaryParts.push('No hard limit breach detected');
    }

    if (stressRows.length) {
        summaryParts.push(
            stressTests.warning_triggered
                ? 'stress warning threshold breached'
                : 'stress scenarios within threshold'
        );
    }

    summary.textContent = `${summaryParts.join(' · ')}.`;

    breaches.forEach((breach) => {
        const li = document.createElement('li');
        li.textContent = `[${breach.severity?.toUpperCase() || 'INFO'}] ${breach.message}`;
        breachList.appendChild(li);
    });

    stressRows.forEach((scenario) => {
        const li = document.createElement('li');
        li.textContent =
            `[STRESS] ${scenario.name}: ${formatPercent(scenario.pnl_pct || 0)} (${formatCurrency(
                scenario.pnl_dollars || 0
            )}) · Worst ${scenario.worst_position_ticker}`;
        breachList.appendChild(li);
    });
}

function displayRebalancing(rebalancing) {
    const summary = document.getElementById('rebalanceSummary');
    const list = document.getElementById('rebalanceList');
    list.innerHTML = '';

    summary.textContent = rebalancing.summary || 'Rebalance analysis unavailable.';
    const recommendations = rebalancing.recommendations || [];

    if (recommendations.length === 0) {
        list.innerHTML = '<p class="panel-subtitle">No trades required at this time.</p>';
        return;
    }

    recommendations.forEach((item, index) => {
        const row = document.createElement('div');
        row.className = `rebalance-item reveal-target ${item.action === 'BUY' ? 'buy' : 'sell'}`;
        row.setAttribute('data-tilt', '');
        row.style.transitionDelay = `${Math.min(index * 42, 220)}ms`;
        row.innerHTML = `
            <p class="rebalance-title">${item.action} ${item.ticker}</p>
            <p>Drift: ${formatPercent(item.drift_pct)}</p>
            <p>Target ${formatPercent(item.target_weight_pct)} vs Current ${formatPercent(item.current_weight_pct)}</p>
            <p>Trade Value: ${formatCurrency(item.trade_value)}</p>
            <p>Shares Delta: ${formatNumber(item.shares_delta, 4)}</p>
        `;
        list.appendChild(row);
        observeRevealElement(row);
    });
}

function displayDataQuality(dataQuality, qualityWarnings) {
    const grid = document.getElementById('qualityGrid');
    const warnings = document.getElementById('qualityWarnings');
    grid.innerHTML = '';

    const cards = [
        { label: 'Market Status', value: dataQuality.market_status || 'UNKNOWN' },
        { label: 'Quotes Received', value: dataQuality.quotes_received ?? 0 },
        { label: 'Stale Quotes', value: dataQuality.stale_count ?? 0 },
        { label: 'Fallback Quotes', value: dataQuality.fallback_count ?? 0 },
        {
            label: 'Avg Reliability',
            value: formatNumber((dataQuality.average_reliability || 0) * 100, 1) + '%'
        }
    ];

    cards.forEach((card, index) => {
        const node = document.createElement('article');
        node.className = 'quality-card reveal-target';
        node.setAttribute('data-tilt', '');
        node.style.transitionDelay = `${Math.min(index * 36, 180)}ms`;
        node.innerHTML = `
            <h3>${card.label}</h3>
            <p>${card.value}</p>
        `;
        grid.appendChild(node);
        observeRevealElement(node);
    });

    const warningItems = [];
    const staleTickers = dataQuality.stale_tickers || [];
    const fallbackTickers = dataQuality.fallback_tickers || [];

    if (staleTickers.length > 0) {
        warningItems.push(`Stale: ${staleTickers.join(', ')}`);
    }
    if (fallbackTickers.length > 0) {
        warningItems.push(`Fallback source: ${fallbackTickers.join(', ')}`);
    }
    if ((qualityWarnings || []).length > 0) {
        warningItems.push(...qualityWarnings.slice(0, 4));
    }

    warnings.textContent = warningItems.length > 0 ? warningItems.join(' | ') : 'All data quality checks passed.';
}

function displayOpsMonitoring(opsMonitor) {
    const grid = document.getElementById('opsGrid');
    const summary = document.getElementById('opsSummary');
    const errorsNode = document.getElementById('opsErrors');
    const alertsNode = document.getElementById('opsAlerts');
    const trendCanvas = document.getElementById('opsTrendChart');

    if (!grid || !summary || !errorsNode || !alertsNode || !trendCanvas) {
        return;
    }

    grid.innerHTML = '';
    errorsNode.innerHTML = '';
    alertsNode.innerHTML = '';

    const counters = opsMonitor.counters || {};
    const cards = [
        { label: 'Quote Requests', value: counters.quote_requests ?? 0 },
        { label: 'Quote Failures', value: counters.quote_failures ?? 0 },
        { label: 'Failure Rate', value: formatPercent(opsMonitor.failure_rate_pct || 0) },
        { label: 'Fallback Quotes', value: counters.fallback_quotes ?? 0 },
        { label: 'Stale Quotes', value: counters.stale_quotes ?? 0 },
        { label: 'Demo Quotes', value: counters.demo_quotes_served ?? 0 },
        { label: 'Demo Mode', value: opsMonitor.demo_mode_enabled ? 'ENABLED' : 'DISABLED' }
    ];

    cards.forEach((card, index) => {
        const node = document.createElement('article');
        node.className = 'quality-card reveal-target';
        node.setAttribute('data-tilt', '');
        node.style.transitionDelay = `${Math.min(index * 34, 180)}ms`;
        node.innerHTML = `
            <h3>${card.label}</h3>
            <p>${card.value}</p>
        `;
        grid.appendChild(node);
        observeRevealElement(node);
    });

    summary.textContent = opsMonitor.summary || 'Monitoring summary unavailable.';

    const activeAlerts = opsMonitor.alerts?.active || [];
    if (!activeAlerts.length) {
        alertsNode.innerHTML = '<li>No active alerts.</li>';
    } else {
        activeAlerts.forEach((alert) => {
            const li = document.createElement('li');
            li.textContent = `[${(alert.severity || 'info').toUpperCase()}] ${alert.message}`;
            alertsNode.appendChild(li);
        });
    }

    const recentErrors = opsMonitor.recent_errors || [];
    if (!recentErrors.length) {
        errorsNode.innerHTML = '<li>No recent backend errors captured.</li>';
    } else {
        recentErrors.forEach((message) => {
            const li = document.createElement('li');
            li.textContent = message;
            errorsNode.appendChild(li);
        });
    }

    const trend = opsMonitor.trend || {};
    const labels = trend.labels || [];
    const fallbackCounts = trend.fallback_counts || [];
    const errorCounts = trend.error_counts || [];

    if (opsTrendChart) {
        opsTrendChart.destroy();
    }

    opsTrendChart = new Chart(trendCanvas.getContext('2d'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Fallback Events',
                    data: fallbackCounts,
                    borderColor: '#f4a625',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.28
                },
                {
                    label: 'Error Events',
                    data: errorCounts,
                    borderColor: '#f66f72',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.28
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#d1e5fa' } }
            },
            scales: {
                y: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.10)' }
                },
                x: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.05)' }
                }
            }
        }
    });
}

function setupExportActions() {
    const csvButton = document.getElementById('exportCsvBtn');
    const pdfButton = document.getElementById('exportPdfBtn');

    csvButton?.addEventListener('click', async () => {
        if (!latestPortfolioPayload) {
            showError('Generate a portfolio before exporting.');
            return;
        }
        const exportPayload = buildCsvExportPayload(latestPortfolioPayload);

        try {
            const response = await fetch('/export-csv', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(exportPayload)
            });

            if (!response.ok) {
                const payload = await response.json();
                throw new Error(payload.error || 'CSV export failed');
            }

            const blob = await response.blob();
            const downloadUrl = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = downloadUrl;
            anchor.download = `portfolio-report-${Date.now()}.csv`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(downloadUrl);
        } catch (error) {
            showError(error.message);
        }
    });

    pdfButton?.addEventListener('click', () => {
        if (!latestPortfolioPayload) {
            showError('Generate a portfolio before exporting.');
            return;
        }

        const popup = window.open('', '_blank', 'width=1020,height=760');
        if (!popup) {
            showError('Popup blocked. Please allow popups to export PDF.');
            return;
        }

        popup.document.write(buildPrintableReportHtml(latestPortfolioPayload));
        popup.document.close();

        setTimeout(() => {
            popup.focus();
            popup.print();
        }, 480);
    });
}

function buildPrintableReportHtml(portfolio) {
    const allocations = portfolio.allocations || [];
    const rows = allocations
        .map(
            (allocation) => `
                <tr>
                    <td>${allocation.ticker || ''}</td>
                    <td>${allocation.name || ''}</td>
                    <td>${allocation.strategy || ''}</td>
                    <td>${formatPercent(allocation.weight_pct || 0)}</td>
                    <td>${Number(allocation.shares || 0).toFixed(4)}</td>
                    <td>${formatCurrency(allocation.current_value || allocation.cost || 0)}</td>
                </tr>
            `
        )
        .join('');

    return `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>Portfolio Report</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 24px; color: #1b2836; }
                h1 { margin-bottom: 8px; }
                .meta { margin-bottom: 4px; }
                table { border-collapse: collapse; width: 100%; margin-top: 16px; }
                th, td { border: 1px solid #d6dce2; padding: 8px; text-align: left; }
                th { background: #f3f7fb; }
            </style>
        </head>
        <body>
            <h1>Quantum Portfolio Lab Report</h1>
            <p class="meta"><strong>Generated:</strong> ${new Date().toLocaleString()}</p>
            <p class="meta"><strong>Strategies:</strong> ${(portfolio.strategies || []).join(' + ')}</p>
            <p class="meta"><strong>Investment Amount:</strong> ${formatCurrency(portfolio.investment_amount || 0)}</p>
            <p class="meta"><strong>Current Total Value:</strong> ${formatCurrency(portfolio.total_value || 0)}</p>
            <p class="meta"><strong>Allocation Method:</strong> ${portfolio.allocation_method || 'N/A'}</p>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Name</th>
                        <th>Strategy</th>
                        <th>Weight</th>
                        <th>Shares</th>
                        <th>Current Value</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </body>
        </html>
    `;
}

function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

function hideError() {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.style.display = 'none';
}

// ---------------------------------------------------------------
// Allocation Donut Chart
// ---------------------------------------------------------------

const CHART_PALETTE = [
    '#58cbff', '#f4a625', '#31cd76', '#9d9cff', '#ff7b86',
    '#5b89ff', '#e88c30', '#44dba8', '#c084fc', '#fb923c',
    '#38bdf8', '#a3e635', '#818cf8', '#f472b6', '#22d3ee',
];

function displayAllocationDonut(allocations) {
    const canvas = document.getElementById('allocationDonutChart');
    if (!canvas) return;
    if (allocationDonutChart) allocationDonutChart.destroy();

    const labels = allocations.map(a => a.ticker);
    const data = allocations.map(a => Number(a.weight_pct || 0));

    allocationDonutChart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: CHART_PALETTE.slice(0, labels.length),
                borderColor: '#0a1623',
                borderWidth: 2,
                hoverOffset: 8,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '55%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#d1e5fa', font: { size: 11 }, padding: 10 }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.label}: ${formatPercent(ctx.parsed)}`
                    }
                }
            }
        }
    });
}

// ---------------------------------------------------------------
// Sector Exposure Donut
// ---------------------------------------------------------------

function displaySectorExposure(payload) {
    const canvas = document.getElementById('sectorDonutChart');
    if (!canvas) return;
    if (sectorDonutChart) sectorDonutChart.destroy();

    const sectors = payload.sectors || [];
    const weights = payload.weights || [];
    if (!sectors.length) return;

    sectorDonutChart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: sectors,
            datasets: [{
                data: weights,
                backgroundColor: CHART_PALETTE.slice(0, sectors.length),
                borderColor: '#0a1623',
                borderWidth: 2,
                hoverOffset: 8,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '55%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#d1e5fa', font: { size: 11 }, padding: 10 }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.label}: ${formatPercent(ctx.parsed)}`
                    }
                }
            }
        }
    });
}

// ---------------------------------------------------------------
// Correlation Matrix Heatmap
// ---------------------------------------------------------------

function correlationColor(val) {
    // Red (negative) → transparent (zero) → Cyan (positive)
    const v = Math.max(-1, Math.min(1, val));
    if (v >= 0) {
        const alpha = (v * 0.85).toFixed(3);
        return `rgba(45, 199, 232, ${alpha})`;
    }
    const alpha = (Math.abs(v) * 0.85).toFixed(3);
    return `rgba(246, 111, 114, ${alpha})`;
}

function displayCorrelationMatrix(payload) {
    const wrap = document.getElementById('correlationHeatmap');
    const status = document.getElementById('correlationStatus');
    if (!wrap || !status) return;
    wrap.innerHTML = '';

    if (payload.status !== 'ok') {
        status.textContent = payload.status === 'insufficient_holdings'
            ? 'At least 2 holdings required for correlation.'
            : 'Insufficient historical data for correlation matrix.';
        return;
    }

    status.textContent = `Pairwise daily-return correlation (${payload.tickers.length} assets).`;
    const tickers = payload.tickers;
    const matrix = payload.matrix;

    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headerRow.appendChild(document.createElement('th'));
    tickers.forEach(t => {
        const th = document.createElement('th');
        th.textContent = t;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    matrix.forEach((row, i) => {
        const tr = document.createElement('tr');
        const labelTd = document.createElement('th');
        labelTd.textContent = tickers[i];
        tr.appendChild(labelTd);
        row.forEach(val => {
            const td = document.createElement('td');
            td.textContent = val.toFixed(2);
            td.style.background = correlationColor(val);
            td.style.color = Math.abs(val) > 0.5 ? '#0b1118' : '#d5e4f3';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
}

// ---------------------------------------------------------------
// Monte Carlo Fan Chart
// ---------------------------------------------------------------

function displayMonteCarlo(payload) {
    const canvas = document.getElementById('monteCarloChart');
    const statusEl = document.getElementById('monteCarloStatus');
    const statsGrid = document.getElementById('monteCarloStats');
    if (!canvas || !statusEl || !statsGrid) return;
    statsGrid.innerHTML = '';

    if (monteCarloChart) monteCarloChart.destroy();

    if (payload.status !== 'ok') {
        statusEl.textContent = 'Insufficient data for Monte Carlo simulation.';
        return;
    }

    statusEl.textContent =
        `${payload.simulations.toLocaleString()} simulations · ${payload.forecast_days} trading days · ` +
        `Daily μ=${payload.expected_return_daily_pct.toFixed(4)}% σ=${payload.volatility_daily_pct.toFixed(4)}%`;

    const labels = payload.sample_days.map(d => `Day ${d}`);
    const bands = payload.bands;

    const ctx = canvas.getContext('2d');

    monteCarloChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: '95th %ile',
                    data: bands.p95,
                    borderColor: 'rgba(45, 199, 232, 0.25)',
                    backgroundColor: 'rgba(45, 199, 232, 0.06)',
                    fill: '+4',
                    borderWidth: 1,
                    pointRadius: 0,
                    tension: 0.3,
                },
                {
                    label: '75th %ile',
                    data: bands.p75,
                    borderColor: 'rgba(45, 199, 232, 0.35)',
                    backgroundColor: 'rgba(45, 199, 232, 0.1)',
                    fill: '+2',
                    borderWidth: 1,
                    pointRadius: 0,
                    tension: 0.3,
                },
                {
                    label: 'Median',
                    data: bands.p50,
                    borderColor: '#f4a625',
                    borderWidth: 2.5,
                    pointRadius: 0,
                    tension: 0.3,
                },
                {
                    label: '25th %ile',
                    data: bands.p25,
                    borderColor: 'rgba(45, 199, 232, 0.35)',
                    backgroundColor: 'rgba(45, 199, 232, 0.1)',
                    fill: false,
                    borderWidth: 1,
                    pointRadius: 0,
                    tension: 0.3,
                },
                {
                    label: '5th %ile',
                    data: bands.p5,
                    borderColor: 'rgba(45, 199, 232, 0.25)',
                    fill: false,
                    borderWidth: 1,
                    pointRadius: 0,
                    tension: 0.3,
                },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#d1e5fa' } },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${formatCurrency(ctx.parsed.y)}`
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        color: '#8ea9c3',
                        callback: v => `$${Number(v).toLocaleString('en-US')}`
                    },
                    grid: { color: 'rgba(143, 169, 195, 0.12)' }
                },
                x: {
                    ticks: { color: '#8ea9c3' },
                    grid: { color: 'rgba(143, 169, 195, 0.05)' }
                }
            }
        }
    });

    // Terminal distribution stats
    const terminal = payload.terminal_distribution;
    const statCards = [
        { label: '5th %ile', value: formatCurrency(terminal.p5) },
        { label: '25th %ile', value: formatCurrency(terminal.p25) },
        { label: 'Median', value: formatCurrency(terminal.p50) },
        { label: '75th %ile', value: formatCurrency(terminal.p75) },
        { label: '95th %ile', value: formatCurrency(terminal.p95) },
    ];

    statCards.forEach((card, index) => {
        const node = document.createElement('article');
        node.className = 'quality-card reveal-target';
        node.setAttribute('data-tilt', '');
        node.style.transitionDelay = `${Math.min(index * 36, 200)}ms`;
        node.innerHTML = `<h3>${card.label}</h3><p>${card.value}</p>`;
        statsGrid.appendChild(node);
        observeRevealElement(node);
    });
}

// ---------------------------------------------------------------
// Keyboard Shortcuts
// ---------------------------------------------------------------

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (event) => {
        // Ctrl+Enter → Run Portfolio Model
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            const form = document.getElementById('portfolioForm');
            if (form) form.dispatchEvent(new Event('submit', { cancelable: true }));
            return;
        }

        // Ctrl+E → Export CSV
        if ((event.ctrlKey || event.metaKey) && event.key === 'e') {
            event.preventDefault();
            const csvBtn = document.getElementById('exportCsvBtn');
            if (csvBtn) csvBtn.click();
            return;
        }

        // Ctrl+R → Manual refresh
        if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
            event.preventDefault();
            refreshPortfolioLive();
            return;
        }

        // Number keys 1-5 → Toggle strategies (only when not in an input)
        if (event.key >= '1' && event.key <= '5' && !event.ctrlKey && !event.metaKey) {
            const activeTag = document.activeElement?.tagName;
            if (activeTag === 'INPUT' || activeTag === 'TEXTAREA') return;
            const cards = document.querySelectorAll('.strategy-card');
            const index = parseInt(event.key, 10) - 1;
            if (index < cards.length) {
                cards[index].click();
            }
        }
    });
}

function decryptText(element, finalString, duration = 800) {
    if (!element) return;
    if (prefersReducedMotion) {
        element.textContent = finalString;
        return;
    }
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
    const startTime = performance.now();
    
    const step = (now) => {
        const progress = Math.min(1, (now - startTime) / duration);
        if (progress < 1) {
            element.textContent = finalString.split('').map((char, index) => {
                if (char === ' ') return ' ';
                if (index < finalString.length * progress) {
                    return char;
                }
                return chars[Math.floor(Math.random() * chars.length)];
            }).join('');
            requestAnimationFrame(step);
        } else {
            element.textContent = finalString;
        }
    };
    requestAnimationFrame(step);
}

function drawSparkline(canvas, volatility) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const points = 20;
    const stepX = width / (points - 1);
    
    ctx.beginPath();
    let currentY = height / 2;
    ctx.moveTo(0, currentY);
    
    for (let i = 1; i < points; i++) {
        const noise = (Math.random() - 0.5) * (volatility || 15) * 1.5;
        currentY = Math.max(10, Math.min(height - 10, currentY + noise));
        // Force the last point to trend slightly upwards for aesthetics
        if (i > points - 5) currentY -= 2;
        ctx.lineTo(i * stepX, currentY);
    }
    
    ctx.strokeStyle = 'rgba(45, 199, 232, 0.15)';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    
    // Add gradient fill under sparkline
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, 'rgba(45, 199, 232, 0.08)');
    gradient.addColorStop(1, 'rgba(45, 199, 232, 0)');
    ctx.fillStyle = gradient;
    ctx.fill();
}

// ---------------------------------------------------------------
// Plain-English Narrative
// ---------------------------------------------------------------

function displayNarrative(narrative) {
    const panel = document.getElementById('narrativePanel');
    const headlineEl = document.getElementById('narrativeHeadline');
    const bulletsEl = document.getElementById('narrativeBullets');
    if (!panel || !headlineEl || !bulletsEl) return;

    const bullets = Array.isArray(narrative.bullets) ? narrative.bullets : [];
    if (!narrative.headline && bullets.length === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = '';
    headlineEl.textContent = narrative.headline || '';
    bulletsEl.innerHTML = '';
    bullets.forEach((text) => {
        const li = document.createElement('li');
        li.textContent = text;
        bulletsEl.appendChild(li);
    });
    observeRevealElement(panel);
}

// ---------------------------------------------------------------
// Goal Tracker — lognormal probability + Monte Carlo overlay
// ---------------------------------------------------------------

let goalTrackerState = { mu_daily: null, sigma_daily: null, current_value: 0 };

function normCdf(z) {
    // Abramowitz & Stegun 7.1.26 approximation of erf.
    const sign = z < 0 ? -1 : 1;
    const x = Math.abs(z) / Math.sqrt(2);
    const t = 1 / (1 + 0.3275911 * x);
    const a1 =  0.254829592;
    const a2 = -0.284496736;
    const a3 =  1.421413741;
    const a4 = -1.453152027;
    const a5 =  1.061405429;
    const erf = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return 0.5 * (1 + sign * erf);
}

function lognormalProbability(currentValue, targetValue, muDaily, sigmaDaily, days) {
    if (!Number.isFinite(currentValue) || currentValue <= 0) return null;
    if (!Number.isFinite(targetValue) || targetValue <= 0) return null;
    if (!Number.isFinite(muDaily) || !Number.isFinite(sigmaDaily) || sigmaDaily <= 0) return null;
    if (!Number.isFinite(days) || days <= 0) return null;

    const drift = (muDaily - 0.5 * sigmaDaily * sigmaDaily) * days;
    const stdev = sigmaDaily * Math.sqrt(days);
    const logRatio = Math.log(targetValue / currentValue);
    const z = (logRatio - drift) / stdev;
    const probReach = 1 - normCdf(z);

    const expectedValue = currentValue * Math.exp(drift + 0.5 * stdev * stdev);
    return {
        probability_pct: probReach * 100,
        expected_value: expectedValue,
        z_score: z,
    };
}

function setupGoalTracker(monteCarlo, currentValue) {
    const panel = document.getElementById('goalTrackerPanel');
    const form = document.getElementById('goalTrackerForm');
    const resultEl = document.getElementById('goalResult');
    if (!panel || !form || !resultEl) return;

    if (monteCarlo.status !== 'ok') {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = '';

    goalTrackerState = {
        mu_daily: (monteCarlo.expected_return_daily_pct || 0) / 100,
        sigma_daily: (monteCarlo.volatility_daily_pct || 0) / 100,
        current_value: currentValue || monteCarlo.current_value || 0,
    };

    const targetInput = document.getElementById('goalTargetValue');
    if (targetInput && !targetInput.value) {
        targetInput.value = Math.round((goalTrackerState.current_value || 10000) * 1.5);
    }
    const yearsInput = document.getElementById('goalTargetYears');
    if (yearsInput && !yearsInput.value) {
        yearsInput.value = '5';
    }

    form.onsubmit = (event) => {
        event.preventDefault();
        evaluateGoalTracker();
    };
    observeRevealElement(panel);
}

function evaluateGoalTracker() {
    const targetValue = parseFloat(document.getElementById('goalTargetValue').value);
    const targetYears = parseFloat(document.getElementById('goalTargetYears').value);
    const resultEl = document.getElementById('goalResult');
    const headlineEl = document.getElementById('goalProbHeadline');
    const detailEl = document.getElementById('goalProbDetail');
    const statsEl = document.getElementById('goalStats');
    if (!resultEl || !headlineEl || !detailEl || !statsEl) return;

    const days = Math.round(targetYears * 252);
    const result = lognormalProbability(
        goalTrackerState.current_value,
        targetValue,
        goalTrackerState.mu_daily,
        goalTrackerState.sigma_daily,
        days
    );

    resultEl.style.display = '';
    if (!result) {
        headlineEl.textContent = 'Insufficient data';
        detailEl.textContent = 'Run a portfolio first or check your inputs.';
        statsEl.innerHTML = '';
        return;
    }

    const prob = Math.max(0, Math.min(100, result.probability_pct));
    headlineEl.innerHTML = `${prob.toFixed(1)}% <span class="goal-prob-suffix">chance of reaching ${formatCurrency(targetValue)}</span>`;
    headlineEl.classList.toggle('goal-prob-good', prob >= 60);
    headlineEl.classList.toggle('goal-prob-mid', prob >= 30 && prob < 60);
    headlineEl.classList.toggle('goal-prob-low', prob < 30);

    const verdict = prob >= 70 ? 'Likely' : prob >= 40 ? 'Plausible' : prob >= 15 ? 'Stretch goal' : 'Unlikely without higher risk or more capital';
    detailEl.textContent = `${verdict} — based on the portfolio's historical drift and volatility, projected ${targetYears} years (${days} trading days) forward under a lognormal model.`;

    statsEl.innerHTML = '';
    [
        { label: 'Current value', value: formatCurrency(goalTrackerState.current_value) },
        { label: 'Target', value: formatCurrency(targetValue) },
        { label: 'Expected value', value: formatCurrency(result.expected_value) },
        { label: 'Horizon', value: `${targetYears} yrs` },
    ].forEach((item) => {
        const card = document.createElement('div');
        card.className = 'quality-card';
        card.innerHTML = `<h3>${item.label}</h3><p>${item.value}</p>`;
        statsEl.appendChild(card);
    });

    drawGoalLineOnMonteCarlo(targetValue);
}

function drawGoalLineOnMonteCarlo(targetValue) {
    if (!monteCarloChart || !Number.isFinite(targetValue)) return;
    const datasets = monteCarloChart.data.datasets;
    const len = (datasets[0] && datasets[0].data && datasets[0].data.length) || 0;
    if (!len) return;

    const goalData = new Array(len).fill(targetValue);
    const existingIdx = datasets.findIndex((ds) => ds.label === 'Goal');
    if (existingIdx >= 0) {
        datasets[existingIdx].data = goalData;
    } else {
        datasets.push({
            label: 'Goal',
            data: goalData,
            borderColor: '#f4a625',
            borderDash: [6, 4],
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            tension: 0,
        });
    }
    monteCarloChart.update();
}

// ---------------------------------------------------------------
// Tweak Workbench — live what-if weights with Sharpe/Vol/Return recompute
// ---------------------------------------------------------------

let tweakState = null;

function setupTweakWorkbench(workbench, currentValue) {
    const panel = document.getElementById('tweakWorkbenchPanel');
    const slidersEl = document.getElementById('tweakSliders');
    const statusEl = document.getElementById('tweakStatus');
    if (!panel || !slidersEl) return;

    if (workbench.status !== 'ok' || !Array.isArray(workbench.tickers) || workbench.tickers.length < 2) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = '';

    tweakState = {
        tickers: workbench.tickers.slice(),
        names: (workbench.names || workbench.tickers).slice(),
        muAnnual: (workbench.mu_annual_pct || []).map((v) => v / 100),
        sigmaAnnual: (workbench.sigma_annual_pct || []).map((v) => v / 100),
        corr: workbench.correlation_matrix || [],
        rf: (workbench.risk_free_rate_annual_pct || 0) / 100,
        initialWeights: (workbench.initial_weights || []).slice(),
        currentValue: currentValue || 0,
        currentWeights: (workbench.initial_weights || []).slice(),
        baselineMetrics: null,
    };

    if (statusEl) {
        statusEl.textContent =
            `Drag sliders to test "what-if" weights. Live recompute uses ${workbench.history_days || '~500'} days of returns.`;
    }

    renderTweakSliders();
    tweakState.baselineMetrics = computeTweakMetrics(tweakState.initialWeights);
    renderTweakMetrics(tweakState.initialWeights);

    const resetBtn = document.getElementById('tweakResetBtn');
    if (resetBtn) {
        resetBtn.onclick = () => {
            tweakState.currentWeights = tweakState.initialWeights.slice();
            renderTweakSliders();
            renderTweakMetrics(tweakState.currentWeights);
        };
    }
    const equalBtn = document.getElementById('tweakEqualizeBtn');
    if (equalBtn) {
        equalBtn.onclick = () => {
            const n = tweakState.tickers.length;
            tweakState.currentWeights = new Array(n).fill(1 / n);
            renderTweakSliders();
            renderTweakMetrics(tweakState.currentWeights);
        };
    }
    observeRevealElement(panel);
}

function renderTweakSliders() {
    const slidersEl = document.getElementById('tweakSliders');
    if (!slidersEl || !tweakState) return;
    slidersEl.innerHTML = '';

    const normalized = normalizeWeights(tweakState.currentWeights);

    tweakState.tickers.forEach((ticker, idx) => {
        const row = document.createElement('div');
        row.className = 'tweak-row';
        const weightPct = (normalized[idx] || 0) * 100;
        const rawValue = (tweakState.currentWeights[idx] || 0) * 100;

        row.innerHTML = `
            <div class="tweak-row-head">
                <span class="tweak-ticker">${ticker}</span>
                <span class="tweak-name">${tweakState.names[idx] || ''}</span>
                <span class="tweak-weight" data-idx="${idx}">${weightPct.toFixed(1)}%</span>
            </div>
            <input class="tweak-slider" type="range" min="0" max="60" step="0.5"
                   value="${rawValue.toFixed(2)}" data-idx="${idx}">
        `;
        slidersEl.appendChild(row);
    });

    slidersEl.querySelectorAll('input.tweak-slider').forEach((input) => {
        input.addEventListener('input', (event) => {
            const idx = parseInt(event.target.dataset.idx, 10);
            tweakState.currentWeights[idx] = parseFloat(event.target.value) / 100;
            const normalizedLive = normalizeWeights(tweakState.currentWeights);
            slidersEl.querySelectorAll('.tweak-weight').forEach((node) => {
                const i = parseInt(node.dataset.idx, 10);
                node.textContent = `${(normalizedLive[i] * 100).toFixed(1)}%`;
            });
            renderTweakMetrics(tweakState.currentWeights);
        });
    });
}

function normalizeWeights(weights) {
    const sum = weights.reduce((s, w) => s + (w > 0 ? w : 0), 0);
    if (sum <= 0) {
        const n = weights.length || 1;
        return new Array(n).fill(1 / n);
    }
    return weights.map((w) => (w > 0 ? w / sum : 0));
}

function computeTweakMetrics(weightsRaw) {
    const w = normalizeWeights(weightsRaw);
    const n = w.length;
    let portReturn = 0;
    for (let i = 0; i < n; i++) portReturn += w[i] * (tweakState.muAnnual[i] || 0);

    let portVar = 0;
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            const corr = (tweakState.corr[i] && tweakState.corr[i][j] !== undefined) ? tweakState.corr[i][j] : (i === j ? 1 : 0);
            const cov = corr * (tweakState.sigmaAnnual[i] || 0) * (tweakState.sigmaAnnual[j] || 0);
            portVar += w[i] * w[j] * cov;
        }
    }
    const portVol = portVar > 0 ? Math.sqrt(portVar) : 0;
    const sharpe = portVol > 0 ? (portReturn - tweakState.rf) / portVol : 0;
    const hhi = w.reduce((s, x) => s + x * x, 0);
    const effectiveN = hhi > 0 ? 1 / hhi : 0;

    return {
        portReturnPct: portReturn * 100,
        portVolPct: portVol * 100,
        sharpe,
        effectiveN,
        topWeightPct: Math.max(...w) * 100,
    };
}

function renderTweakMetrics(weightsRaw) {
    const metricsEl = document.getElementById('tweakMetrics');
    if (!metricsEl || !tweakState) return;
    const live = computeTweakMetrics(weightsRaw);
    const base = tweakState.baselineMetrics || live;

    const cards = [
        { label: 'Expected Return (annual)', value: `${live.portReturnPct.toFixed(2)}%`, delta: live.portReturnPct - base.portReturnPct, deltaSuffix: 'pp' },
        { label: 'Volatility (annual)', value: `${live.portVolPct.toFixed(2)}%`, delta: live.portVolPct - base.portVolPct, deltaSuffix: 'pp', invert: true },
        { label: 'Sharpe Ratio', value: live.sharpe.toFixed(2), delta: live.sharpe - base.sharpe, deltaSuffix: '' },
        { label: 'Effective # Holdings', value: live.effectiveN.toFixed(2), delta: live.effectiveN - base.effectiveN, deltaSuffix: '' },
        { label: 'Largest Weight', value: `${live.topWeightPct.toFixed(1)}%`, delta: live.topWeightPct - base.topWeightPct, deltaSuffix: 'pp', invert: true },
    ];

    metricsEl.innerHTML = '';
    cards.forEach((card) => {
        const node = document.createElement('div');
        node.className = 'tweak-metric-card';
        let deltaHtml = '';
        if (Math.abs(card.delta) > 1e-4) {
            const positive = card.invert ? card.delta < 0 : card.delta > 0;
            const sign = card.delta >= 0 ? '+' : '';
            deltaHtml = `<span class="tweak-delta ${positive ? 'tweak-delta-pos' : 'tweak-delta-neg'}">${sign}${card.delta.toFixed(2)}${card.deltaSuffix}</span>`;
        }
        node.innerHTML = `
            <div class="tweak-metric-label">${card.label}</div>
            <div class="tweak-metric-value">${card.value}${deltaHtml}</div>
        `;
        metricsEl.appendChild(node);
    });
}

// ---------------------------------------------------------------
// Results Tabs — single source of truth for which panel is visible
// ---------------------------------------------------------------

function setupResultsTabs() {
    const nav = document.getElementById('resultsTabs');
    if (!nav) return;
    const tabs = nav.querySelectorAll('.results-tab');
    const panes = document.querySelectorAll('.tab-pane');

    tabs.forEach((tab) => {
        tab.addEventListener('click', () => activateTab(tab.dataset.tab));
        tab.addEventListener('keydown', (event) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            event.preventDefault();
            const list = Array.from(tabs);
            const idx = list.indexOf(tab);
            const next = event.key === 'ArrowRight'
                ? list[(idx + 1) % list.length]
                : list[(idx - 1 + list.length) % list.length];
            next.focus();
            activateTab(next.dataset.tab);
        });
    });

    function activateTab(name) {
        tabs.forEach((tab) => {
            const active = tab.dataset.tab === name;
            tab.classList.toggle('active', active);
            tab.setAttribute('aria-selected', active ? 'true' : 'false');
            tab.tabIndex = active ? 0 : -1;
        });
        panes.forEach((pane) => {
            const active = pane.dataset.tabPane === name;
            pane.classList.toggle('active', active);
            if (active) {
                pane.removeAttribute('hidden');
            } else {
                pane.setAttribute('hidden', '');
            }
        });
        // Force charts to relayout when their pane becomes visible.
        window.dispatchEvent(new Event('resize'));
    }
}

// ---------------------------------------------------------------
// Mobile form toggle (collapse the build form below ~900px)
// ---------------------------------------------------------------

function setupMobileFormToggle() {
    const button = document.getElementById('mobileFormToggle');
    const dock = document.getElementById('leftDock');
    if (!button || !dock) return;

    const collapse = () => {
        dock.classList.add('collapsed');
        button.setAttribute('aria-expanded', 'false');
        const text = button.querySelector('.mobile-form-toggle-text');
        if (text) text.textContent = 'Build';
    };
    const expand = () => {
        dock.classList.remove('collapsed');
        button.setAttribute('aria-expanded', 'true');
        const text = button.querySelector('.mobile-form-toggle-text');
        if (text) text.textContent = 'Hide';
    };

    button.addEventListener('click', () => {
        if (dock.classList.contains('collapsed')) {
            expand();
            dock.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            collapse();
        }
    });

    // Auto-collapse on mobile after a successful submit
    const form = document.getElementById('portfolioForm');
    if (form) {
        form.addEventListener('submit', () => {
            if (window.matchMedia('(max-width: 900px)').matches) {
                setTimeout(collapse, 600);
            }
        });
    }

    if (window.matchMedia('(max-width: 900px)').matches) {
        collapse();
    }
}

// ---------------------------------------------------------------
// Inline amount validation (instead of waiting for submit)
// ---------------------------------------------------------------

function setupAmountValidation() {
    const input = document.getElementById('investmentAmount');
    const helper = document.getElementById('amountHelper');
    const submit = document.getElementById('generateBtn');
    if (!input || !helper) return;

    const validate = () => {
        const raw = input.value.trim();
        if (raw === '') {
            helper.textContent = 'Minimum $5,000.';
            helper.classList.remove('amount-helper-error', 'amount-helper-ok');
            if (submit) submit.disabled = false;
            return;
        }
        const value = parseFloat(raw);
        if (!Number.isFinite(value)) {
            helper.textContent = 'Please enter a valid number.';
            helper.classList.add('amount-helper-error');
            helper.classList.remove('amount-helper-ok');
            if (submit) submit.disabled = true;
            return;
        }
        if (value < 5000) {
            const short = 5000 - value;
            helper.textContent = `${formatCurrency(short)} short of the $5,000 minimum.`;
            helper.classList.add('amount-helper-error');
            helper.classList.remove('amount-helper-ok');
            if (submit) submit.disabled = true;
            return;
        }
        helper.textContent = `Looks good — allocating ${formatCurrency(value)}.`;
        helper.classList.remove('amount-helper-error');
        helper.classList.add('amount-helper-ok');
        if (submit) submit.disabled = false;
    };

    input.addEventListener('input', validate);
    input.addEventListener('blur', validate);
}

// ---------------------------------------------------------------
// Theme toggle (dark/light) with localStorage persistence
// ---------------------------------------------------------------

function setupThemeToggle() {
    const button = document.getElementById('themeToggle');
    if (!button) return;

    const stored = localStorage.getItem('qpl-theme');
    const initial = stored === 'light' ? 'light' : 'dark';
    applyTheme(initial);

    button.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
        applyTheme(current);
        localStorage.setItem('qpl-theme', current);
    });
}

function applyTheme(mode) {
    if (mode === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
}

// ---------------------------------------------------------------
// Share + save link
// ---------------------------------------------------------------

function setupShareButton() {
    const button = document.getElementById('shareBtn');
    if (!button) return;
    button.addEventListener('click', async () => {
        if (!latestPortfolioPayload || !latestPortfolioPayload.portfolio_id) {
            showShareToast('Generate a portfolio first.');
            return;
        }
        const url = `${window.location.origin}${window.location.pathname}?p=${encodeURIComponent(latestPortfolioPayload.portfolio_id)}`;
        try {
            await navigator.clipboard.writeText(url);
            showShareToast('Share link copied to clipboard!');
        } catch (_) {
            window.prompt('Copy this link:', url);
        }
        // Refresh saved-portfolios list since this one is now persisted
        refreshSavedPortfolios();
    });
}

let shareToastTimer = null;
function showShareToast(message) {
    let toast = document.getElementById('shareToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'shareToast';
        toast.className = 'share-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('visible');
    if (shareToastTimer) clearTimeout(shareToastTimer);
    shareToastTimer = setTimeout(() => toast.classList.remove('visible'), 2400);
}

function autoLoadFromShareLink() {
    const url = new URL(window.location.href);
    const id = url.searchParams.get('p');
    if (!id) return;
    loadSavedPortfolioById(id, { silent: false });
}

async function loadSavedPortfolioById(portfolioId, options = {}) {
    const { silent = false } = options;
    if (!silent) setLoadingState(true);
    try {
        const response = await fetch(`/portfolio/${encodeURIComponent(portfolioId)}`);
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            showError(data.error || 'Could not load saved portfolio.');
            return;
        }
        const portfolio = await response.json();
        applyStrategiesToUI(portfolio.strategies || []);
        const amountInput = document.getElementById('investmentAmount');
        if (amountInput && portfolio.investment_amount) {
            amountInput.value = portfolio.investment_amount;
        }
        displayResults(portfolio);
        showShareToast('Loaded saved portfolio.');
    } catch (exc) {
        showError(`Could not load: ${exc.message}`);
    } finally {
        if (!silent) setLoadingState(false);
    }
}

// ---------------------------------------------------------------
// Saved portfolios sidebar
// ---------------------------------------------------------------

function setupSavedPortfolios() {
    refreshSavedPortfolios();
}

async function refreshSavedPortfolios() {
    const list = document.getElementById('savedList');
    if (!list) return;
    try {
        const response = await fetch('/saved-portfolios');
        if (!response.ok) {
            list.innerHTML = '<div class="saved-empty">Could not load saved portfolios.</div>';
            return;
        }
        const data = await response.json();
        const portfolios = (data.portfolios || []);
        if (!portfolios.length) {
            list.innerHTML = '<div class="saved-empty">No saved portfolios yet — generate one and click "Copy share link."</div>';
            return;
        }
        list.innerHTML = '';
        portfolios.forEach((p) => {
            const item = document.createElement('div');
            item.className = 'saved-item';
            const strategiesText = (p.strategies || []).join(' + ') || 'Custom';
            const valueText = p.last_total_value !== null && p.last_total_value !== undefined
                ? formatCurrency(p.last_total_value)
                : (p.investment_amount ? formatCurrency(p.investment_amount) : '—');
            const dateText = p.last_snapshot_date || p.created_date || '';
            item.innerHTML = `
                <div>
                    <div class="saved-item-name">${strategiesText}</div>
                    <div class="saved-item-meta">${valueText} · ${dateText} · ${p.ticker_count || 0} holdings</div>
                </div>
                <span aria-hidden="true">→</span>
            `;
            item.addEventListener('click', () => loadSavedPortfolioById(p.portfolio_id));
            list.appendChild(item);
        });
    } catch (exc) {
        list.innerHTML = '<div class="saved-empty">Error loading saved portfolios.</div>';
    }
}

// ---------------------------------------------------------------
// A/B Compare tab
// ---------------------------------------------------------------

function setupCompareTab() {
    const button = document.getElementById('compareRunBtn');
    if (!button) return;

    const selectA = document.getElementById('compareSelectA');
    const selectB = document.getElementById('compareSelectB');
    if (selectA && selectB && selectB.options.length > 1 && selectA.value === selectB.value) {
        selectB.value = selectB.options[1].value;
    }

    button.addEventListener('click', runCompare);
}

async function runCompare() {
    const selectA = document.getElementById('compareSelectA');
    const selectB = document.getElementById('compareSelectB');
    const resultsEl = document.getElementById('compareResults');
    const amountInput = document.getElementById('investmentAmount');
    if (!selectA || !selectB || !resultsEl) return;

    const strategyA = selectA.value;
    const strategyB = selectB.value;
    if (strategyA === strategyB) {
        resultsEl.innerHTML = '<div class="empty-state"><div class="empty-state-title">Pick two different strategies</div></div>';
        return;
    }
    const amountValue = parseFloat(amountInput && amountInput.value);
    const amount = Number.isFinite(amountValue) && amountValue >= 5000 ? amountValue : 5000;

    resultsEl.innerHTML = `
        <div class="skeleton-card"><div class="skeleton-block"></div><div class="skeleton-block"></div><div class="skeleton-block"></div></div>
        <div class="skeleton-card"><div class="skeleton-block"></div><div class="skeleton-block"></div><div class="skeleton-block"></div></div>
    `;

    try {
        const response = await fetch('/compare-strategies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount, strategy_a: strategyA, strategy_b: strategyB }),
        });
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            resultsEl.innerHTML = `<div class="empty-state"><div class="empty-state-title">Compare failed</div><div class="empty-state-detail">${errData.error || 'Unknown error'}</div></div>`;
            return;
        }
        const data = await response.json();
        renderCompareResults(data, resultsEl);
    } catch (exc) {
        resultsEl.innerHTML = `<div class="empty-state"><div class="empty-state-title">Compare failed</div><div class="empty-state-detail">${exc.message}</div></div>`;
    }
}

function renderCompareResults(data, container) {
    container.innerHTML = '';
    const results = data.results || [];
    if (results.length !== 2) return;

    // Choose winners on each metric (higher Sharpe, lower drawdown, higher MC median)
    const winner = (key, higherBetter = true) => {
        const a = results[0][key];
        const b = results[1][key];
        if (a === null || a === undefined || b === null || b === undefined) return -1;
        if (higherBetter) return a > b ? 0 : (b > a ? 1 : -1);
        return Math.abs(a) < Math.abs(b) ? 0 : (Math.abs(b) < Math.abs(a) ? 1 : -1);
    };
    const winSharpe = winner('backtest_1y_sharpe');
    const winReturn = winner('backtest_1y_return_pct');
    const winDrawdown = winner('backtest_1y_max_drawdown_pct', false);
    const winMedian = winner('monte_carlo_median_1y');

    results.forEach((row, idx) => {
        const card = document.createElement('div');
        card.className = 'compare-card';
        const isWinner = (winSharpe === idx) && (winSharpe !== -1);
        const tickersHtml = (row.tickers || []).map((t, i) => {
            const w = (row.weights_pct || [])[i];
            return `<span class="ticker-chip" title="${(w || 0).toFixed(1)}%">${t}</span>`;
        }).join('');
        const fmt = (val, suffix = '', digits = 2) =>
            (val === null || val === undefined || !Number.isFinite(Number(val)))
                ? '—'
                : `${Number(val).toFixed(digits)}${suffix}`;
        const star = (won) => won ? ' <span class="compare-winner-badge">best</span>' : '';

        card.innerHTML = `
            <div class="compare-card-head">
                <div class="compare-strategy-name">${row.strategy}</div>
                ${isWinner ? '<span class="compare-winner-badge">best Sharpe</span>' : ''}
            </div>
            <div class="compare-tickers">${tickersHtml}</div>
            <div class="compare-stats">
                <div>
                    <div class="compare-stat-label">1Y Return${star(winReturn === idx)}</div>
                    <div class="compare-stat-value">${fmt(row.backtest_1y_return_pct, '%')}</div>
                </div>
                <div>
                    <div class="compare-stat-label">1Y Sharpe${star(winSharpe === idx)}</div>
                    <div class="compare-stat-value">${fmt(row.backtest_1y_sharpe)}</div>
                </div>
                <div>
                    <div class="compare-stat-label">1Y Max DD${star(winDrawdown === idx)}</div>
                    <div class="compare-stat-value">${fmt(row.backtest_1y_max_drawdown_pct, '%')}</div>
                </div>
                <div>
                    <div class="compare-stat-label">MC Median (1Y)${star(winMedian === idx)}</div>
                    <div class="compare-stat-value">${fmt(row.monte_carlo_median_1y, '', 0)}</div>
                </div>
                <div>
                    <div class="compare-stat-label">5–95th MC Range</div>
                    <div class="compare-stat-value">${fmt(row.monte_carlo_p5_1y, '', 0)} – ${fmt(row.monte_carlo_p95_1y, '', 0)}</div>
                </div>
                <div>
                    <div class="compare-stat-label">Annual Vol</div>
                    <div class="compare-stat-value">${fmt(row.annualized_volatility_pct, '%')}</div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

// ---------------------------------------------------------------
// First-time onboarding tour
// ---------------------------------------------------------------

const TOUR_STEPS = [
    {
        target: '#investmentAmount',
        title: 'Step 1 — Pick an amount',
        body: 'Start with at least $5,000. The model needs enough capital to size positions properly.',
    },
    {
        target: '.strategies-grid',
        title: 'Step 2 — Choose a strategy',
        body: 'Each card shows the actual tickers it will buy. Pick one or two; combos let you blend tilts.',
    },
    {
        target: '#generateBtn',
        title: 'Step 3 — Build your portfolio',
        body: 'Hit "Run Portfolio Model" — we size positions by conviction divided by volatility, then attach live prices and analytics.',
    },
    {
        target: '#resultsTabs',
        title: 'Tabs',
        body: 'Results are organized into Overview, Performance, Risk, What-If, Compare, and Data. The What-If tab lets you drag sliders and test goals.',
    },
    {
        target: '#themeToggle',
        title: 'Light or dark',
        body: 'Click the moon/sun in the corner to switch themes anytime.',
    },
];

function setupOnboardingTour() {
    const seen = localStorage.getItem('qpl-tour-seen');
    if (seen) return;
    // Wait a beat so the page can settle.
    setTimeout(() => runTourStep(0), 700);
}

function runTourStep(stepIdx) {
    cleanupTour();
    if (stepIdx >= TOUR_STEPS.length) {
        localStorage.setItem('qpl-tour-seen', '1');
        return;
    }
    const step = TOUR_STEPS[stepIdx];
    const target = document.querySelector(step.target);
    if (!target) {
        runTourStep(stepIdx + 1);
        return;
    }
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('tour-target-highlight');

    const backdrop = document.createElement('div');
    backdrop.className = 'tour-backdrop';
    backdrop.id = 'tourBackdrop';
    document.body.appendChild(backdrop);

    const popover = document.createElement('div');
    popover.className = 'tour-step';
    popover.id = 'tourStep';
    popover.innerHTML = `
        <div class="tour-step-title">${step.title}</div>
        <div class="tour-step-body">${step.body}</div>
        <div class="tour-step-actions">
            <span class="tour-step-progress">${stepIdx + 1} / ${TOUR_STEPS.length}</span>
            <div class="tour-step-buttons">
                <button type="button" class="tour-skip">Skip</button>
                <button type="button" class="tour-next">${stepIdx === TOUR_STEPS.length - 1 ? 'Done' : 'Next'}</button>
            </div>
        </div>
    `;
    document.body.appendChild(popover);

    // Position popover near the target.
    const rect = target.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    const margin = 14;
    let top = rect.bottom + margin;
    let left = rect.left;
    if (top + popoverRect.height > window.innerHeight - margin) {
        top = Math.max(margin, rect.top - popoverRect.height - margin);
    }
    if (left + popoverRect.width > window.innerWidth - margin) {
        left = Math.max(margin, window.innerWidth - popoverRect.width - margin);
    }
    popover.style.top = `${Math.max(margin, top)}px`;
    popover.style.left = `${Math.max(margin, left)}px`;

    popover.querySelector('.tour-next').addEventListener('click', () => runTourStep(stepIdx + 1));
    popover.querySelector('.tour-skip').addEventListener('click', () => {
        cleanupTour();
        localStorage.setItem('qpl-tour-seen', '1');
    });
    backdrop.addEventListener('click', () => {
        cleanupTour();
        localStorage.setItem('qpl-tour-seen', '1');
    });
}

function cleanupTour() {
    document.querySelectorAll('.tour-target-highlight').forEach((el) => el.classList.remove('tour-target-highlight'));
    const popover = document.getElementById('tourStep');
    if (popover) popover.remove();
    const backdrop = document.getElementById('tourBackdrop');
    if (backdrop) backdrop.remove();
}

// ---------------------------------------------------------------
// Risk Profile (3 Qs) — questionnaire + label preview
// ---------------------------------------------------------------

function setupRiskProfile() {
    const ageEl = document.getElementById('riskAge');
    const horizonEl = document.getElementById('riskHorizon');
    const tolEl = document.getElementById('riskTolerance');
    const resultEl = document.getElementById('riskProfileResult');
    if (!ageEl || !horizonEl || !tolEl || !resultEl) return;

    // Pre-fill from localStorage
    const stored = JSON.parse(localStorage.getItem('qpl-risk-profile') || 'null');
    if (stored) {
        if (stored.age) ageEl.value = stored.age;
        if (stored.horizon_years) horizonEl.value = stored.horizon_years;
        if (stored.max_drawdown_tolerance_pct) tolEl.value = stored.max_drawdown_tolerance_pct;
    }

    const update = () => {
        const payload = collectRiskProfilePayload();
        if (!payload) {
            resultEl.textContent = '';
            resultEl.className = 'risk-profile-result';
            return;
        }
        const score = computeRiskScore(payload);
        const label = riskLabelForScore(score);
        const cashPct = Math.max(0, Math.min(12, (100 - score) / 100 * 12));
        resultEl.innerHTML = `Profile: <strong>${label}</strong> · score ${score.toFixed(0)}/100 · ~${cashPct.toFixed(1)}% cash buffer`;
        resultEl.className = `risk-profile-result risk-${label.toLowerCase()}`;
        localStorage.setItem('qpl-risk-profile', JSON.stringify(payload));
    };

    [ageEl, horizonEl, tolEl].forEach((el) => el.addEventListener('input', update));
    update();
}

function collectRiskProfilePayload() {
    const age = parseInt(document.getElementById('riskAge')?.value, 10);
    const horizon = parseInt(document.getElementById('riskHorizon')?.value, 10);
    const tol = parseFloat(document.getElementById('riskTolerance')?.value);
    if (!Number.isFinite(age) || !Number.isFinite(horizon) || !Number.isFinite(tol)) return null;
    if (age < 18 || age > 99 || horizon < 1 || horizon > 50 || tol < 5 || tol > 60) return null;
    return { age, horizon_years: horizon, max_drawdown_tolerance_pct: tol };
}

function computeRiskScore(profile) {
    const ageC = Math.max(0, Math.min(100, (80 - profile.age) / 62 * 100));
    const horC = Math.max(0, Math.min(100, profile.horizon_years / 30 * 100));
    const tolC = Math.max(0, Math.min(100, (profile.max_drawdown_tolerance_pct - 5) / 55 * 100));
    return ageC * 0.35 + horC * 0.30 + tolC * 0.35;
}

function riskLabelForScore(score) {
    if (score >= 75) return 'Aggressive';
    if (score >= 55) return 'Growth';
    if (score >= 35) return 'Balanced';
    return 'Conservative';
}

function displayRiskProfilePill(profile) {
    const indicator = document.getElementById('liveIndicator');
    if (!indicator) return;
    let pill = document.getElementById('riskProfilePill');
    if (!profile) {
        if (pill) pill.remove();
        return;
    }
    if (!pill) {
        pill = document.createElement('span');
        pill.id = 'riskProfilePill';
        pill.className = 'risk-profile-pill';
        indicator.parentElement.insertBefore(pill, indicator);
    }
    const label = profile.label || riskLabelForScore(profile.risk_score || 60);
    pill.textContent = `${label} · ${(profile.risk_score || 60).toFixed(0)}/100`;
    pill.className = `risk-profile-pill risk-${label.toLowerCase()}`;
}

// ---------------------------------------------------------------
// Action Plan card on Overview tab
// ---------------------------------------------------------------

function displayActionPlan(actionPlan) {
    const panel = document.getElementById('actionPlanPanel');
    const list = document.getElementById('actionPlanList');
    const summary = document.getElementById('actionPlanSummary');
    const hint = document.getElementById('actionPlanHint');
    if (!panel || !list) return;

    const orders = (actionPlan && actionPlan.orders) || [];
    if (!orders.length) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = '';
    summary.textContent = actionPlan.summary || `${orders.length} buys ready for next market open.`;
    hint.textContent = actionPlan.open_at_hint || '';

    list.innerHTML = '';
    orders.forEach((order, idx) => {
        const li = document.createElement('li');
        li.className = 'action-plan-item';
        const slippage = Number(order.estimated_execution_cost || 0);
        const slippageHtml = slippage > 0
            ? `<span class="action-plan-slippage">est. cost ${formatCurrency(slippage)}</span>`
            : '';
        li.innerHTML = `
            <span class="action-plan-step">${idx + 1}</span>
            <span class="action-plan-action">BUY</span>
            <span class="action-plan-shares">${Number(order.shares).toFixed(4)} sh</span>
            <span class="action-plan-ticker">${order.ticker}</span>
            <span class="action-plan-price">@ ≤ ${formatCurrency(order.limit_price || 0)}</span>
            <span class="action-plan-cost">≈ ${formatCurrency(order.estimated_cost)}</span>
            ${slippageHtml}
        `;
        list.appendChild(li);
    });

    if (Number(actionPlan.cash_to_hold) > 0.01) {
        const cashLi = document.createElement('li');
        cashLi.className = 'action-plan-item action-plan-cash';
        cashLi.innerHTML = `
            <span class="action-plan-step">${orders.length + 1}</span>
            <span class="action-plan-action">HOLD</span>
            <span class="action-plan-shares">cash</span>
            <span class="action-plan-ticker">USD</span>
            <span class="action-plan-price"></span>
            <span class="action-plan-cost">≈ ${formatCurrency(actionPlan.cash_to_hold)}</span>
        `;
        list.appendChild(cashLi);
    }
}

// ---------------------------------------------------------------
// Stress Test scenario grid on Risk tab
// ---------------------------------------------------------------

function displayStressTests(microRisk) {
    const grid = document.getElementById('stressGrid');
    const summary = document.getElementById('stressTestsSummary');
    if (!grid) return;
    grid.innerHTML = '';

    const stress = (microRisk && microRisk.stress_tests) || {};
    const scenarios = stress.scenarios || [];
    if (!scenarios.length) {
        grid.innerHTML = '<div class="empty-state"><div class="empty-state-title">No scenarios available</div><div class="empty-state-detail">Run a portfolio first.</div></div>';
        return;
    }

    const worst = stress.worst_case_pct;
    const triggered = stress.warning_triggered;
    if (summary) {
        summary.innerHTML = `Worst-case scenario: <strong class="${triggered ? 'metric-negative' : ''}">${(worst || 0).toFixed(2)}%</strong> ${triggered ? '· warning threshold breached' : ''}`;
    }

    scenarios.forEach((scenario) => {
        const card = document.createElement('div');
        const lossClass = scenario.pnl_pct <= -8 ? 'stress-bad' : scenario.pnl_pct <= -3 ? 'stress-mid' : 'stress-mild';
        card.className = `stress-card ${lossClass}`;
        card.innerHTML = `
            <div class="stress-head">
                <span class="stress-name">${scenario.label || scenario.name}</span>
                <span class="stress-kind">${scenario.kind || 'hypothetical'}</span>
            </div>
            <div class="stress-pnl">${scenario.pnl_pct.toFixed(2)}%</div>
            <div class="stress-pnl-dollars">${formatCurrency(scenario.pnl_dollars)}</div>
            <div class="stress-detail">
                <span>${scenario.horizon || 'Hypothetical'}</span>
            </div>
            <div class="stress-severity-bar"><div class="stress-severity-fill" style="width: ${Math.min(Math.abs(scenario.pnl_pct) * 2, 100)}%"></div></div>
            <div class="stress-worst">Worst position: <strong>${scenario.worst_position_ticker}</strong> ${formatCurrency(scenario.worst_position_pnl)}</div>
        `;
        grid.appendChild(card);
    });

    staggerCards(grid);
    setupCardGlowTracking(grid);
}
