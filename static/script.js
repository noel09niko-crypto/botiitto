document.addEventListener('DOMContentLoaded', () => {
    const activeList = document.getElementById('activeScenariosList');
    const favoritesList = document.getElementById('favoriteScenariosList');
    const statusMessage = document.getElementById('statusMessage');
    
    // Filters & Sorting
    const filterSectorBtn = document.getElementById('filterSector');
    const filterRiskBtn = document.getElementById('filterRisk');
    const sortBtn = document.getElementById('sortBtn');
    
    // Global Data State
    let allActiveScenarios = [];
    let allFavoriteScenarios = [];
    let currentSortOrder = 'desc'; // desc = highest confidence first
    let availableSectors = new Set();

    // Modal Elements
    const modal = document.getElementById('folderModal');
    const closeBtn = document.querySelector('.close-btn');
    const modalFavBtn = document.getElementById('modalFavBtn');

    let currentModalScenarioId = null;

    fetchScenarios();
    setInterval(fetchScenarios, 5 * 60 * 1000);

    async function fetchScenarios() {
        try {
            const response = await fetch('/api/scenarios');
            const data = await response.json();

            if (data.success) {
                statusMessage.textContent = `Viimeksi päivitetty: ${data.timestamp} | AI-Moottori Aktiivinen`;
                allActiveScenarios = data.active;
                allFavoriteScenarios = data.favorites;
                
                // Extract sectors dynamically for the dropdown
                availableSectors.clear();
                [...allActiveScenarios, ...allFavoriteScenarios].forEach(s => {
                    if(s.sector) availableSectors.add(s.sector);
                });
                updateSectorDropdown();
                
                applyFiltersAndRender();
            } else {
                statusMessage.textContent = "Virhe markkinadatan haussa.";
            }
        } catch (error) {
            console.error("Error fetching scenarios:", error);
            statusMessage.textContent = "Yhteysvirhe palvelimeen.";
        }
    }

    function updateSectorDropdown() {
        const currentVal = filterSectorBtn.value;
        filterSectorBtn.innerHTML = '<option value="ALL">Kaikki toimialat</option>';
        [...availableSectors].sort().forEach(sector => {
            const opt = document.createElement('option');
            opt.value = sector;
            opt.textContent = sector;
            filterSectorBtn.appendChild(opt);
        });
        filterSectorBtn.value = currentVal; // preserve selection
    }

    // Event Listeners for Filters
    filterSectorBtn.addEventListener('change', applyFiltersAndRender);
    filterRiskBtn.addEventListener('change', applyFiltersAndRender);
    sortBtn.addEventListener('click', () => {
        currentSortOrder = currentSortOrder === 'desc' ? 'asc' : 'desc';
        sortBtn.textContent = currentSortOrder === 'desc' ? 'Lajittele: Luottamus % (Ylinensin)' : 'Lajittele: Luottamus % (Alin ensin)';
        applyFiltersAndRender();
    });

    function applyFiltersAndRender() {
        const selSector = filterSectorBtn.value;
        const selRisk = filterRiskBtn.value;

        let filteredActive = allActiveScenarios.filter(s => {
            if (selSector !== 'ALL' && s.sector !== selSector) return false;
            if (selRisk !== 'ALL' && s.risk_level !== selRisk) return false;
            return true;
        });

        let filteredFavs = allFavoriteScenarios.filter(s => {
            if (selSector !== 'ALL' && s.sector !== selSector) return false;
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
        activeList.innerHTML = '';
        favoritesList.innerHTML = '';

        if (active.length === 0) {
            activeList.innerHTML = '<p style="color:var(--text-secondary); padding:20px;">Ei skenaarioita saatavilla. AI hakee uusia...</p>';
        } else {
            active.forEach(item => {
                try {
                    activeList.appendChild(createFolderElement(item, false));
                } catch(e) {
                    console.error("Error rendering card:", e, item);
                }
            });
        }

        if (favorites.length === 0) {
            favoritesList.innerHTML = '<p style="color:var(--text-secondary); padding:20px;">Ei seurattavia skenaarioita.</p>';
        } else {
            favorites.forEach(item => {
                try {
                    favoritesList.appendChild(createFolderElement(item, true));
                } catch(e) {
                    console.error("Error rendering fav card:", e, item);
                }
            });
        }
    }

    function extractPrimaryTicker(tickersStr) {
        if (!tickersStr) return "YLEINEN";
        return tickersStr.split(',')[0].trim() || "YLEINEN";
    }
    
    // Extractor just for the raw ticker code (e.g. AAPL) to query yfinance
    function extractRawTickerSymbol(primaryTickerStr) {
        return primaryTickerStr.split(' ')[0].trim();
    }

    function getRecClass(rec) {
        if (!rec) return 'rec-tarkkaile';
        const r = rec.toLowerCase();
        if (r.includes('osta')) return 'rec-osta';
        if (r.includes('vältä') || r.includes('myy') || r.includes('short')) return 'rec-valta';
        return 'rec-tarkkaile';
    }

    function extractCompanyName(titleStr) {
        if (!titleStr) return 'Tuntematon yhtiö';
        // If format is 'COMPANY: idea', return just the company part
        const colonIdx = titleStr.indexOf(':');
        if (colonIdx > 0 && colonIdx < 60) {
            return titleStr.substring(0, colonIdx).trim();
        }
        // If the title starts with a long word in caps (AI put name first), use it
        // Otherwise truncate to 50 chars max
        return titleStr.length > 50 ? titleStr.substring(0, 50).trim() + '…' : titleStr;
    }

    function getWorldHint(item) {
        const src = item.global_context || item.summary || '';
        if (!src || src === 'N/A') return '';
        const firstSentence = src.split(/[.!?]/)[0].trim() + '.';
        // Detect hallucination: if any word repeats 3+ times, reject and try fallback
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
        
        // Border color based on recommendation
        let borderClass = 'rec-watch-border';
        if (recClass === 'rec-osta') borderClass = 'rec-buy-border';
        if (recClass === 'rec-valta') borderClass = 'rec-sell-border';

        div.className = `folder-card ${isFav ? 'tracked-style' : borderClass}`;
        
        const dateStr = new Date(item.created_at).toLocaleString('fi-FI', { month: 'short', day: 'numeric' });
        const primaryTicker = extractPrimaryTicker(item.tickers);
        const conf = item.confidence ? `${item.confidence}%` : '?';
        const companyName = extractCompanyName(item.title);
        const worldHint = getWorldHint(item);

        // Simple rec label: just OSTA or MYY
        let recLabel = 'OSTA';
        if (rec.toLowerCase().includes('myy') || rec.toLowerCase().includes('vältä') || rec.toLowerCase().includes('short')) {
            recLabel = 'MYY';
        }

        div.innerHTML = `
            <div class="card-top-row">
                <div class="folder-title">${companyName}</div>
                <button class="track-btn-small ${isFav ? 'active' : ''}" data-id="${item.id}">
                    ${isFav ? '★ Seurannassa' : '+ Seuraa'}
                </button>
            </div>
            ${worldHint ? `<div class="card-world-hint">${worldHint}</div>` : ''}
            <div class="folder-meta">
                <span class="primary-ticker">${primaryTicker}</span>
                <span class="rec-tag ${recClass}">${recLabel}</span>
                <span class="conf-tag">Luottamus ${conf}</span>
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
            
            // Helper functions to safely parse data
            const primaryTicker = extractPrimaryTicker(item.tickers);
            const primaryTickerRaw = extractRawTickerSymbol(primaryTicker);
            
            // Show modal and reset scrolling
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';

            // Setup base modal texts
            document.getElementById('modalTitle').textContent = item.title;
            document.getElementById('modalPrimaryTicker').textContent = primaryTickerRaw;
            
            let recommendation = (item.recommendation || 'Tarkkaile').toUpperCase();
            const recEl = document.getElementById('modalRecommendation');
            recEl.textContent = recommendation;
            recEl.className = 'tag tag-border'; // Reset
            
            if (recommendation.includes('OSTA')) {
                recEl.classList.add('tag-success');
            } else if (recommendation.includes('MYY')) {
                recEl.classList.add('tag-danger');
            } else {
                recEl.classList.add('tag-secondary');
            }
            
            document.getElementById('modalRiskLevel').textContent = `Riski: ${item.risk_level || 'Tuntematon'}`;
            document.getElementById('modalConfidence').textContent = `Luottamus: ${item.confidence || '?'}%`;
            document.getElementById('modalSector').textContent = item.sector || 'Yleinen';
            
            // Tarinalliset kentät
            document.getElementById('modalSummary').textContent = item.summary;
            document.getElementById('modalGlobalContext').textContent = item.global_context || 'Ei lisätietoja maailman tilanteesta.';
            document.getElementById('modalReasoning').textContent = item.reasoning;
            document.getElementById('modalMetricsExp').textContent = item.metrics_explanation || 'Numerot selitetään seuraavassa päivityksessä.';
            document.getElementById('modalTimeHorizon').textContent = item.time_horizon || 'Horisontti puuttuu.';
            document.getElementById('modalCompanyHistory').textContent = item.company_history || 'Yhtiön historiaa ei saatavilla.';
            
            // Clear and reset live data fields
            resetStockDetailsFields();

            // Populate Supporting News
            const newsContainer = document.getElementById('modalNewsContainer');
            if (newsContainer) {
                newsContainer.innerHTML = '<p class="text-muted small">Ladataan uutisia...</p>';
                // (Optional: Load news if needed, but the worker now puts story parts in separate fields)
            }

            // Load extra stock info from YFinance via our API
            if (primaryTickerRaw && primaryTickerRaw !== 'N/A') {
                document.getElementById('liveDataLoading').style.display = 'inline';
                try {
                    const req = await fetch(`/api/stock_info/${primaryTickerRaw}`);
                    const res = await req.json();
                    if(res.success && res.data) {
                        const d = res.data;
                        document.getElementById('stockPrice').textContent = `$${d.price}`;
                        const sign = d.changePercent >= 0 ? '+' : '';
                        document.getElementById('stockChange').textContent = `${sign}${d.changePercent}%`;
                        document.getElementById('stockChange').className = `stat-value ${d.changePercent >= 0 ? 'val-pos' : 'val-neg'}`;
                        document.getElementById('stockPE').textContent = d.pe;
                        document.getElementById('stockPB').textContent = d.pb;
                        document.getElementById('stockEV').textContent = d.ev_ebitda;
                        document.getElementById('stockEPSG').textContent = d.eps_growth;
                        document.getElementById('stockRevG').textContent = d.rev_growth;
                        document.getElementById('stockMargin').textContent = d.net_margin;
                        document.getElementById('stockROE').textContent = d.roe;
                        document.getElementById('stockFCF').textContent = d.fcf;
                        document.getElementById('stockDE').textContent = d.debt_equity;
                        document.getElementById('stockDiv').textContent = d.div_yield;
                        document.getElementById('stockHigh').textContent = `$${d.high52}`;
                        document.getElementById('stockLow').textContent = `$${d.low52}`;
                        document.getElementById('stockRSI').textContent = d.rsi;
                        document.getElementById('stockBeta').textContent = d.beta;
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
            alert("Virhe avattaessa tietoja. Yritä uudelleen.");
        }
    }

    function resetStockDetailsFields() {
        const fields = ['stockPrice', 'stockChange', 'stockPE', 'stockPB', 'stockEV', 'stockEPSG', 'stockRevG', 'stockMargin', 'stockROE', 'stockFCF', 'stockDE', 'stockDiv', 'stockHigh', 'stockLow', 'stockRSI', 'stockBeta', 'stockCap'];
        fields.forEach(f => {
            const el = document.getElementById(f);
            if (el) el.textContent = '--';
        });
    }

    function extractPrimaryTicker(tickersStr) {
        if (!tickersStr) return 'N/A';
        const parts = tickersStr.split(',').map(s => s.trim());
        return parts[0] || 'N/A';
    }

    function extractRawTickerSymbol(fullTicker) {
        if (!fullTicker || fullTicker === 'N/A') return 'N/A';
        const match = fullTicker.match(/\$([A-Z.0-9]+)/);
        if (match) return match[1];
        return fullTicker.replace(/[^A-Z]/g, ''); // Fallback to uppercase letters only
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
        modalFavBtn.textContent = modalFavBtn.classList.contains('active') ? 'Poista Seurannasta' : 'Lisää Seurantaan';
        try {
            const resp = await fetch(`/api/favorite/${currentModalScenarioId}`, { method: 'POST' });
            if (resp.ok) fetchScenarios();
        } catch (err) {
            console.error("Favorite toggle error:", err);
        }
    });
});
