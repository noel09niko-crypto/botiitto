document.addEventListener('DOMContentLoaded', () => {
    const topTenList = document.getElementById('topTenList');
    const othersList = document.getElementById('othersList');
    const favoritesList = document.getElementById('favoritesList');
    const statusMessage = document.getElementById('statusMessage');
    
    const filterRiskBtn = document.getElementById('filterRisk');
    const sortBtn = document.getElementById('sortBtn');
    
    // Global Data State
    let allActiveScenarios = [];
    let allFavoriteScenarios = [];
    let currentSortOrder = 'desc'; // desc = highest confidence first

    // Modal Elements
    const modal = document.getElementById('folderModal');
    const closeBtn = document.querySelector('.close-btn');
    const modalFavBtn = document.getElementById('modalFavBtn');

    // Search Elements
    const searchInput = document.getElementById('searchInput');
    const refreshBtn = document.getElementById('refreshBtn');
    let currentModalScenarioId = null;

    fetchScenarios();
    // Faster refresh during debugging/initial setup
    setInterval(fetchScenarios, 60 * 1000); 

    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            refreshBtn.classList.add('rotating');
            fetchScenarios().then(() => {
                setTimeout(() => refreshBtn.classList.remove('rotating'), 500);
            });
        });
    }

    // Manual Search Handler
    async function handleSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        // UI Loading State
        searchBtn.disabled = true;
        const originalText = searchBtn.innerHTML;
        searchBtn.innerHTML = '<span class="loading-spinner"></span> Luodaan analyysia...';
        statusMessage.textContent = `Tutkitaan yhtiötä '${query}'... Tämä voi kestää 15-30 sekuntia.`;

        try {
            const response = await fetch('/api/search_and_analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            const data = await response.json();

            if (data.success) {
                searchInput.value = '';
                statusMessage.textContent = `Analyysi valmis: ${data.ticker}. Lisätty seurantaan.`;
                await fetchScenarios(); // Refresh lists
            } else {
                alert("Haku epäonnistui: " + data.error);
                statusMessage.textContent = "Haku epäonnistui.";
            }
        } catch (error) {
            console.error("Search error:", error);
            alert("Yhteysvirhe haun aikana.");
        } finally {
            searchBtn.disabled = false;
            searchBtn.innerHTML = originalText;
        }
    }

    searchBtn.addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });

    async function fetchScenarios() {
        try {
            const response = await fetch('/api/scenarios');
            const data = await response.json();

            if (data.success) {
                statusMessage.textContent = `Viimeksi päivitetty: ${data.timestamp} | AI-Moottori Aktiivinen`;
                allActiveScenarios = data.active;
                allFavoriteScenarios = data.favorites;
                applyFiltersAndRender();
            } else {
                statusMessage.textContent = "Virhe markkinadatan haussa.";
            }
        } catch (error) {
            console.error("Error fetching scenarios:", error);
            statusMessage.textContent = "Yhteysvirhe palvelimeen.";
        }
    }

    // Event Listeners for Filters
    filterRiskBtn.addEventListener('change', applyFiltersAndRender);
    sortBtn.addEventListener('click', () => {
        currentSortOrder = currentSortOrder === 'desc' ? 'asc' : 'desc';
        sortBtn.textContent = currentSortOrder === 'desc' ? 'Lajittele: Luottamus %' : 'Lajittele: Luottamus % (Nouseva)';
        applyFiltersAndRender();
    });

    function applyFiltersAndRender() {
        const selRisk = filterRiskBtn.value;

        let filteredActive = allActiveScenarios.filter(s => {
            if (selRisk !== 'ALL' && s.risk_level !== selRisk) return false;
            return true;
        });

        let filteredFavs = allFavoriteScenarios.filter(s => {
            if (selRisk !== 'ALL' && s.risk_level !== selRisk) return false;
            return true;
        });

        // Sorting by Confidence
        const confSort = (a, b) => {
            let confA = a.confidence || 0;
            let confB = b.confidence || 0;
            return currentSortOrder === 'desc' ? confB - confA : confA - confB;
        };

        filteredActive.sort(confSort);
        filteredFavs.sort(confSort);

        renderLists(filteredActive, filteredFavs);
    }

    function renderLists(active, favorites) {
        topTenList.innerHTML = '';
        othersList.innerHTML = '';
        favoritesList.innerHTML = '';

        // Scoring for Top 10
        const getRankScore = (item) => {
            let score = item.confidence || 0;
            const risk = (item.risk_level || '').toLowerCase();
            const rec = (item.recommendation || '').toLowerCase();

            // Strategy 1.1: PINNED (Huippu) analysts get massive priority
            if (item.is_pinned) score += 1000; 

            if (risk === 'matala') score += 5; // Value/Stability bonus
            if (rec.includes('core')) score += 10; // Strong conviction bonus
            if (rec.includes('speculative')) score += 5; // Growth potential
            return score;
        };

        const sortedByRank = [...active].sort((a, b) => getRankScore(b) - getRankScore(a));
        const topFive = sortedByRank.slice(0, 5);
        const others = sortedByRank.slice(5);

        // 1. Top 5
        if (topFive.length === 0) {
            topTenList.innerHTML = '<p class="empty-msg">Analyysejä tulossa...</p>';
        } else {
            topFive.forEach(item => {
                topTenList.appendChild(createFolderElement(item, false));
            });
        }

        // 2. Others
        if (others.length === 0) {
            othersList.innerHTML = '<p class="empty-msg">Ei muita kohteita.</p>';
        } else {
            others.forEach(item => {
                othersList.appendChild(createFolderElement(item, false));
            });
        }

        // 3. Favorites
        if (favorites.length === 0) {
            favoritesList.innerHTML = '<p class="empty-msg">Ei suosikkeja.</p>';
        } else {
            favorites.forEach(item => {
                favoritesList.appendChild(createFolderElement(item, true));
            });
        }
    }

    function extractPrimaryTicker(tickersStr) {
        if (!tickersStr) return "YLEINEN";
        return tickersStr.split(',')[0].trim() || "YLEINEN";
    }

    function extractRawTickerSymbol(primaryTickerStr) {
        if (!primaryTickerStr || primaryTickerStr === 'N/A') return 'N/A';
        const match = primaryTickerStr.match(/\$([A-Z.0-9]+)/);
        if (match) return match[1];
        return primaryTickerStr.split(' ')[0].trim().replace(/[^A-Z]/g, '');
    }

    function getRecClass(rec) {
        if (!rec) return 'rec-tarkkaile';
        const r = rec.toLowerCase();
        if (r.includes('osta')) return 'rec-osta';
        if (r.includes('vältä') || r.includes('myy') || r.includes('short')) return 'rec-valta';
        return 'rec-tarkkaile';
    }

    function extractCompanyName(item) {
        const titleStr = item.title;
        const tickersStr = item.tickers || '';
        
        if (!titleStr) return tickersStr || 'Tuntematon yhtiö';
        const colonIdx = titleStr.indexOf(':');
        if (colonIdx > 0 && colonIdx < 60) return titleStr.substring(0, colonIdx).trim();
        if (titleStr.length > 30 && tickersStr) return tickersStr.split(',')[0].trim();
        return titleStr.length > 50 ? titleStr.substring(0, 50).trim() + '…' : titleStr;
    }

    function getWorldHint(item) {
        const src = item.global_context || item.summary || '';
        if (!src || src === 'N/A') return '';
        const firstSentence = src.split(/[.!?]/)[0].trim() + '.';
        const words = firstSentence.toLowerCase().split(/\s+/).filter(w => w.length > 3);
        const wordCount = {};
        for (const w of words) { wordCount[w] = (wordCount[w] || 0) + 1; }
        const isGarbage = Object.values(wordCount).some(c => c >= 3) || firstSentence.length < 15;
        if (isGarbage) {
            const fallback = (item.summary || '').split(/[.!?]/)[0].trim() + '.';
            return fallback.length > 200 ? fallback.substring(0, 200) + '…' : fallback;
        }
        return firstSentence.length > 200 ? firstSentence.substring(0, 200) + '…' : firstSentence;
    }

    function createFolderElement(item, isFav) {
        const div = document.createElement('div');
        const rec = item.recommendation || 'Tarkkaile';
        const recClass = getRecClass(rec);
        
        let borderClass = 'rec-watch-border';
        if (recClass === 'rec-osta') borderClass = 'rec-buy-border';
        if (recClass === 'rec-valta') borderClass = 'rec-sell-border';

        const priceChange = item.price_change_24h || 0;
        let recLabel = 'OSTA';
        let finalRecClass = recClass;
        let finalBorderClass = borderClass;

        if (priceChange < 0) {
            recLabel = 'MYY';
            finalRecClass = 'rec-valta';
            finalBorderClass = 'rec-sell-border';
        } else if (rec.toLowerCase().includes('myy') || rec.toLowerCase().includes('vältä') || rec.toLowerCase().includes('short')) {
            recLabel = 'MYY';
            finalRecClass = 'rec-valta';
            finalBorderClass = 'rec-sell-border';
        } else {
            // Kaikki muut (osta, tarkkaile, odota jne.) ovat nyt "OSTA" keltaisella pohjalla
            recLabel = 'OSTA';
            finalRecClass = 'rec-osta';
            finalBorderClass = 'rec-buy-border';
        }

        div.className = `folder-card ${isFav ? 'tracked-style' : finalBorderClass}`;

        const dateStr = new Date(item.created_at).toLocaleString('fi-FI', { month: 'short', day: 'numeric' });
        const updateTime = new Date(item.created_at).toLocaleTimeString('fi-FI', { hour: '2-digit', minute: '2-digit' });
        const updatedTag = item.is_updated ? `<div class="updated-badge">🔄 PÄIVITETTY ${updateTime}</div>` : '';
        const primaryTicker = extractPrimaryTicker(item.tickers);
        const conf = item.confidence ? `${item.confidence}%` : '?';
        const companyName = extractCompanyName(item);
        const worldHint = getWorldHint(item);

        const isStrong = (item.confidence || 0) >= 90;

        let confClass = 'conf-low';
        const numConf = item.confidence || 0;
        if (numConf >= 90) confClass = 'conf-high-glow';
        else if (numConf >= 85) confClass = 'conf-high';
        else if (numConf >= 70) confClass = 'conf-med';

        div.innerHTML = `
            ${isStrong ? '<div class="strong-recommendation-badge">✨ Vahva suositus</div>' : ''}
            ${updatedTag}
            <div class="card-top-row">
                <div class="folder-title">${companyName}</div>
                <button class="track-btn-small ${isFav ? 'active' : ''}" data-id="${item.id}">
                    ${isFav ? '★ SUOSIKKI' : '+ SUOSIKKEIHIN'}
                </button>
            </div>
            ${worldHint ? `<div class="card-world-hint">${worldHint}</div>` : ''}
            <div class="folder-meta">
                <span class="primary-ticker">${primaryTicker}</span>
                <span class="rec-tag ${finalRecClass}">${recLabel}</span>
                <span class="conf-tag ${confClass}">Luottamus ${conf}</span>
                <span class="date-meta">${dateStr}</span>
            </div>
        `;

        div.addEventListener('click', (e) => {
            if(e.target.closest('.track-btn-small')) return; 
            openModal(item);
        });

        const favBtn = div.querySelector('.track-btn-small');
        favBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await toggleFavorite(item.id);
        });

        return div;
    }

    async function toggleFavorite(id) {
        try {
            await fetch(`/api/favorite/${id}`, { method: 'POST' });
            fetchScenarios();
        } catch (error) {
            console.error("Failed to track:", error);
        }
    }

    async function openModal(item) {
        try {
            currentModalScenarioId = item.id;
            const primaryTicker = extractPrimaryTicker(item.tickers);
            const primaryTickerRaw = extractRawTickerSymbol(primaryTicker);
            
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';

            document.getElementById('modalTitle').textContent = item.title;
            document.getElementById('modalPrimaryTicker').textContent = primaryTickerRaw;
            
            if (item.is_favorite) {
                modalFavBtn.classList.add('active');
                modalFavBtn.textContent = 'Poista Suosikeista';
            } else {
                modalFavBtn.classList.remove('active');
                modalFavBtn.textContent = 'Lisää Suosikkeihin';
            }

            let recommendation = (item.recommendation || 'Tarkkaile').toUpperCase();
            const recEl = document.getElementById('modalRecommendation');
            recEl.textContent = recommendation;
            recEl.className = 'tag tag-border'; 
            
            if (recommendation.includes('OSTA')) recEl.classList.add('tag-success');
            else if (recommendation.includes('MYY') || recommendation.includes('VÄLTÄ')) recEl.classList.add('tag-danger');
            else recEl.classList.add('tag-secondary');
            
            document.getElementById('modalRiskLevel').textContent = `Riski: ${item.risk_level || 'Tuntematon'}`;
            document.getElementById('modalConfidence').textContent = `Luottamus: ${item.confidence || '?'}%`;
            document.getElementById('modalSector').textContent = item.sector || 'Yleinen';
            
            document.getElementById('modalSummary').textContent = item.summary || 'Yhteenveto valmistuu...';
            document.getElementById('modalGlobalContext').textContent = item.global_context || 'Maailmanmarkkinoiden tilanne analysoitavana.';
            document.getElementById('modalReasoning').textContent = item.reasoning || 'Analyysi nousuajureista valmistuu.';
            document.getElementById('modalMetricsExp').textContent = item.metrics_explanation || 'Tunnuslukujen tarkempi analyysi päivittyy pian.';
            document.getElementById('modalTimeHorizon').textContent = item.time_horizon || 'Ostohorisontti tarkentuu pian.';
            document.getElementById('modalCompanyHistory').textContent = item.company_history || 'Yhtiön tarina päivittyy pian.';

            // Dynaamiset otsikot
            document.getElementById('headerSummary').textContent = item.summary_title || 'Pikakuvaus yhtiöstä';
            document.getElementById('headerGlobalContext').textContent = item.global_title || 'Mitä maailmalla tapahtuu?';
            document.getElementById('headerReasoning').textContent = item.reasoning_title || 'Analyysi ja perustelut';
            document.getElementById('headerMetricsExp').textContent = item.metrics_title || 'Yhtiön numerot sanallistettuna';
            document.getElementById('headerTimeHorizon').textContent = item.horizon_title || 'Ostohorisontti ja seuranta';
            document.getElementById('headerCompanyHistory').textContent = item.history_title || 'Yhtiön tarina ja tausta';
            
            resetStockDetailsFields();

            if (primaryTickerRaw && primaryTickerRaw !== 'N/A') {
                document.getElementById('liveDataLoading').style.display = 'inline';
                try {
                    const req = await fetch(`/api/stock_info/${primaryTickerRaw}`);
                    const res = await req.json();
                    if(res.success && res.data) {
                        const d = res.data;
                        const fmt = (el, val) => {
                            const e = document.getElementById(el);
                            if (!e) return;
                            if (val === 'N/A' || val === null || val === undefined) e.textContent = '—';
                            else e.textContent = val;
                        };
                        document.getElementById('stockPrice').textContent = `$${d.price}`;
                        const sign = d.changePercent >= 0 ? '+' : '';
                        document.getElementById('stockChange').textContent = `${sign}${d.changePercent}%`;
                        document.getElementById('stockChange').className = `stat-value ${d.changePercent >= 0 ? 'val-pos' : 'val-neg'}`;
                        fmt('stockPE', d.pe);
                        fmt('stockPB', d.pb);
                        fmt('stockEV', d.ev_ebitda);
                        fmt('stockEPSG', d.eps_growth);
                        fmt('stockRevG', d.rev_growth);
                        fmt('stockMargin', d.net_margin);
                        fmt('stockROE', d.roe);
                        fmt('stockFCF', d.fcf);
                        fmt('stockDE', d.debt_equity);
                        fmt('stockDiv', d.div_yield);
                        document.getElementById('stockHigh').textContent = `$${d.high52}`;
                        document.getElementById('stockLow').textContent = `$${d.low52}`;
                        fmt('stockRSI', d.rsi);
                        fmt('stockBeta', d.beta);
                        document.getElementById('stockCap').textContent = d.marketCap;
                    }
                } catch (err) {
                    console.error("Live data error:", err);
                } finally {
                    document.getElementById('liveDataLoading').style.display = 'none';
                }
            }
        } catch (error) {
            console.error("Modal Error:", error);
        }
    }

    function resetStockDetailsFields() {
        ['stockPrice', 'stockChange', 'stockPE', 'stockPB', 'stockEV', 'stockEPSG', 'stockRevG', 'stockMargin', 'stockROE', 'stockFCF', 'stockDE', 'stockDiv', 'stockHigh', 'stockLow', 'stockRSI', 'stockBeta', 'stockCap'].forEach(f => {
            const el = document.getElementById(f);
            if (el) el.textContent = '--';
        });
    }

    closeBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    });

    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = 'auto';
        }
    });

    modalFavBtn.addEventListener('click', async () => {
        if (!currentModalScenarioId) return;
        modalFavBtn.classList.toggle('active');
        const isActive = modalFavBtn.classList.contains('active');
        modalFavBtn.textContent = isActive ? 'Poista Suosikeista' : 'Lisää Suosikkeihin';
        await fetch(`/api/favorite/${currentModalScenarioId}`, { method: 'POST' });
        fetchScenarios();
    });
});
