
const API_BASE_URL = "http://127.0.0.1:8000";
const RED_HEX = "#FF0000";
const GREEN_HEX = "#008000";

let currentSession = { officerId: "", totalVerified: 0, approvals: 0, rejections: 0 };
let resultsChart = null;
let riskGauge = null;

document.addEventListener("DOMContentLoaded", () => {
    // Reset form safely
    document.getElementById("login-form")?.reset();
    
    setupEventListeners();
    generateFormFields();
    
    // Initialize charts only if library is loaded
    if (typeof Chart !== 'undefined') {
        initChart();
        initRiskGauge();
    }
    
    // Default starting view
    switchTab("prediction");
});

/* -------------------- FIELD MAPPINGS -------------------- */
const FIELD_MAPPINGS = {
    "external_risk_estimate_c": "Risk Score",
    "net_fraction_revolving_burden": "Revolving Burden %",
    "average_m_in_file": "History Length (M)",
    "num_inq_last_6m": "Recent Inquiries",
    "percent_trades_never_delq": "Clean History %",
    "num_satisfactory_trades": "Healthy Accounts",
    "m_since_oldest_trade": "Oldest Account (M)",
    "m_since_recent_trade": "Newest Account (M)",
    "num_total_trades": "Total Credit Lines",
    "max_delq_ever": "Delinquency Rating",
    "m_since_recent_delq": "Months Since Delq",
    "num_trades_open_in_last_12m": "New Accounts (12M)",
    "percent_install_trades": "Installment Mix %",
    "net_fraction_install_burden": "Installment Burden",
    "num_revolving_trades_w_balance": "Active Balances",
    "percent_trades_w_balance": "Utilization Spread %",
    "num_bank2_natl_trades_w_high_utilization": "High Util Trades",
    "num_trades_60_ever2_derog_pub_rec": "60D Derogatory",
    "num_trades_90_ever2_derog_pub_rec": "90D Derogatory",
    "max_delq_2_public_rec_last_12m": "Max Delq (12M)",
    "m_since_recent_inq_excl7d": "Recent Inquiry (M)",
    "num_inq_last_6m_excl_7days": "Inquiries (Excl 7d)",
    "num_install_trades_w_balance": "Installment Balances"
};

/* -------------------- EVENT LISTENERS -------------------- */
function setupEventListeners() {
    const loginForm = document.getElementById("login-form");
    if (loginForm) loginForm.addEventListener("submit", handleLogin);

    // Password Toggle Logic
    const toggleBtn = document.getElementById('togglePassword');
    const passwordInput = document.getElementById('password');
    if (toggleBtn && passwordInput) {
        toggleBtn.addEventListener('click', function() {
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            this.textContent = type === 'password' ? '👁️' : '🙈';
        });
    }

    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", e => switchTab(e.currentTarget.dataset.tab));
    });

    document.getElementById("btn-search")?.addEventListener("click", handleSearch);
    document.getElementById("btn-predict")?.addEventListener("click", handlePrediction);

    document.getElementById("btn-global-reset")?.addEventListener("click", () => {
        document.getElementById("app-id-search").value = "";
        document.querySelectorAll("#financial-form input").forEach(i => i.value = 0);
        resetDecisionUI();
        
        const icon = document.querySelector(".refresh-icon");
        if (icon) {
            icon.style.transition = "transform 0.6s ease";
            icon.style.transform = "rotate(-360deg)";
            setTimeout(() => {
                icon.style.transition = "none";
                icon.style.transform = "rotate(0deg)";
            }, 600);
        }
    });
}

/* -------------------- LOGIN LOGIC -------------------- */
function handleLogin(e) {
    if (e) e.preventDefault();
    const idField = document.getElementById("employeeId");
    const passField = document.getElementById("password");
    const id = idField.value.trim();
    const pass = passField.value.trim();

    if (id === "admin2026" && pass === "year2026") {
        currentSession.officerId = id;
        document.getElementById("officer-id-display").textContent = id;
        document.getElementById("login-overlay").classList.add("hidden");
        document.getElementById("app-container").classList.remove("hidden");
        idField.value = "";
        passField.value = "";
        switchTab("prediction");
    } else {
        const errorMsg = document.getElementById("login-error");
        if (errorMsg) errorMsg.textContent = "Access Denied: Invalid Credentials";
    }
}

/* -------------------- PREDICTION UI -------------------- */
function updateDecisionUI(result) {
    const statusText = document.getElementById("gauge-status-text");
    const recBox = document.getElementById("recommendation-box");
    const recText = document.getElementById("recommendation-text");
    const summary = document.getElementById("decision-summary");

    const isApproved = result.prediction === 0;
    const prob = result.probability;

    if (riskGauge) {
        riskGauge.data.datasets[0].data = [prob, 100 - prob];
        riskGauge.data.datasets[0].backgroundColor = isApproved ? [GREEN_HEX, "#1a1a1a"] : [RED_HEX, "#1a1a1a"];
        riskGauge.update();
    }

    const statusWord = isApproved ? "APPROVED" : "REJECTED";
    statusText.style.color = isApproved ? GREEN_HEX : RED_HEX;

   
    statusText.innerHTML = `
          <span style="font-size: 1.5rem; display: block; font-weight: bold;">${prob.toFixed(1)}%</span>
          <span style="letter-spacing: 2px; font-weight: 600;">${statusWord}</span>
    `;


    recBox.style.display = "block";
    recBox.style.borderLeftColor = isApproved ? GREEN_HEX : RED_HEX;
    recText.textContent = isApproved ? "CREDIT SECURE: Proceed with standard issuance." : "HIGH RISK: Manual review or rejection advised.";
    summary.innerHTML = `Subject exhibits ${isApproved ? 'stable' : 'volatile'} credit patterns with a risk factor of ${prob.toFixed(1)}%. Primary impact: ${result.primary_factor || 'External Risk Index'}.`;
}



/* -------------------- FORM GENERATION -------------------- */
function generateFormFields() {
    const container = document.getElementById("form-fields-container");
    if (!container) return;
    container.innerHTML = "";
    Object.entries(FIELD_MAPPINGS).forEach(([key, label]) => {
        const div = document.createElement("div");
        div.className = "form-group";
        div.innerHTML = `<label>${label}</label><input type="number" id="${key}" value="0" />`;
        container.appendChild(div);
    });
}

/* -------------------- SEARCH & PREDICT LOGIC -------------------- */
async function handleSearch() {
    const appId = document.getElementById("app-id-search").value.trim();
    if (!appId) return;
    try {
        const res = await fetch(`${API_BASE_URL}/application/${appId}`);
        if (!res.ok) throw new Error("ID not found");
        const dataArray = await res.json();
        const data = dataArray[0] || dataArray;
        document.querySelectorAll("#financial-form input").forEach(i => {
            i.value = data[i.id] ?? data[i.id.toUpperCase()] ?? 0;
        });
        resetDecisionUI();
    } catch (e) { alert(e.message); }
}

async function handlePrediction() {
    const payload = {};
    document.querySelectorAll("#financial-form input").forEach(i => {
        payload[i.id] = Number(i.value) || 0;
    });
    try {
        const res = await fetch(`${API_BASE_URL}/predict`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        updateDecisionUI(result);
        updateSessionStats(result);
    } catch { alert("Prediction error. Ensure Python server is active."); }
}

/* -------------------- CHARTS & TABS -------------------- */
function initRiskGauge() {
    const canvas = document.getElementById("riskGauge");
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (riskGauge) riskGauge.destroy();
    riskGauge = new Chart(ctx, {
        type: "doughnut",
        data: {
            datasets: [{
                data: [0, 100],
                backgroundColor: ["#D4AF37", "#1a1a1a"],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "85%",
            rotation: 270,
            circumference: 180,
            plugins: { legend: { display: false }, tooltip: { enabled: false } }
        }
    });
}

function initChart() {
    const canvas = document.getElementById("resultsChart");
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (resultsChart) resultsChart.destroy();
    resultsChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["Approved", "Rejected"],
            datasets: [{
                data: [0, 0],
                backgroundColor: [GREEN_HEX, RED_HEX],
                borderWidth: 0
            }]
        },
        options: {
            cutout: "70%",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false, position: 'bottom', labels: { color: '#ffffff', padding: 20 } }
            }
        }
    });
}

function resetDecisionUI() {
    if (!riskGauge) return;
    riskGauge.data.datasets[0].data = [0, 100];
    riskGauge.data.datasets[0].backgroundColor = ["#222", "#222"];
    riskGauge.update();
    document.getElementById("gauge-status-text").innerHTML = "READY";
    document.getElementById("gauge-status-text").style.color = "#a0a0a0";
    document.getElementById("recommendation-box").style.display = "none";
}

function updateSessionStats(result) {
    currentSession.totalVerified++;
    result.prediction === 0 ? currentSession.approvals++ : currentSession.rejections++;
}

function updateResultsUI() {
    // 1. Update the Big Number inside the donut hole
    const centerNumber = document.getElementById("chart-center-number");
    if (centerNumber) {
        centerNumber.textContent = currentSession.totalVerified;
    }

    // 2. Update the numbers in the legend (Approved/Rejected spans)
    const approvedLegend = document.getElementById("legend-approved");
    const rejectedLegend = document.getElementById("legend-rejected");
    
    if (approvedLegend) approvedLegend.textContent = currentSession.approvals;
    if (rejectedLegend) rejectedLegend.textContent = currentSession.rejections;

    // 3. Update the Chart.js visual data
    if (resultsChart) {
        resultsChart.data.datasets[0].data = [currentSession.approvals, currentSession.rejections];
        resultsChart.update();
    }
}

function switchTab(tab) {
    document.querySelectorAll(".tab-btn").forEach(b => 
        b.classList.toggle("active", b.dataset.tab === tab)
    );
    
    document.querySelectorAll(".tab-content").forEach(c => {
        if (c.id === `tab-${tab}`) {
            c.style.display = "flex"; // Fixes grid layout visibility
            c.classList.add("active");
        } else {
            c.style.display = "none";
            c.classList.remove("active");
        }
    });
    
    if (tab === "results" && resultsChart) {
        resultsChart.resize(); 
        updateResultsUI();
    }
}