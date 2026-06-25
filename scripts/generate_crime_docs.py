import os
import shutil
import base64

def enc(p):
    with open(p, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

brain_dir = r"C:\Users\HP\.gemini\antigravity-ide\brain\a2950f48-ee1d-46b5-b80d-3dbe558d9318"
workspace_dir = r"c:\Users\HP\.gemini\antigravity-ide\scratch\crime-intel-platform"

# Target directories
docs_dir = os.path.join(workspace_dir, "docs")
images_dir = os.path.join(docs_dir, "images")

os.makedirs(images_dir, exist_ok=True)

# Image mapping
image_mapping = {
    'logo': ('media__1782323355445.png', 'gpcssi_logo.png'),
    'dashboard': ('crime_dashboard_1782333079505.png', 'crime_dashboard.png'),
    'simulation': ('crime_simulation_1782333142322.png', 'crime_simulation.png'),
    'graph_error': ('crime_graph_error_1782333186472.png', 'crime_graph_error.png'),
    'osint': ('crime_osint_1782333635926.png', 'crime_osint.png'),
    'crypto_trace': ('crime_crypto_trace_1782333677149.png', 'crime_crypto_trace.png'),
    'readiness': ('crime_readiness_1782333541726.png', 'crime_readiness.png'),
    'legal_elements': ('crime_legal_elements_1782333434145.png', 'crime_legal_elements.png'),
    'copilot': ('crime_copilot_1782333607377.png', 'crime_copilot.png'),
    'deception': ('crime_deception_1782333782615.png', 'crime_deception.png'),
}

# Encode base64 & copy files
base64_data = {}
for key, (src_name, dest_name) in image_mapping.items():
    src_path = os.path.join(brain_dir, src_name)
    dest_path = os.path.join(images_dir, dest_name)
    
    if os.path.exists(src_path):
        # Base64 encode
        base64_data[key] = enc(src_path)
        # Copy file
        shutil.copy2(src_path, dest_path)
        print(f"Processed {key}: copied and base64 encoded successfully.")
    else:
        print(f"Warning: {src_path} not found.")
        base64_data[key] = ""

# Define the HTML template (normal string)
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crime Intelligence Platform — Technical Project Report</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
  --bg: #090b10;
  --surface: #0e121a;
  --surface2: #141a27;
  --border: #232d3f;
  --border-focus: #3b4e6d;
  --accent: #00bcd4; /* Vibrant Cyan */
  --accent-rgb: 0, 188, 212;
  --accent2: #4caf50; /* Green */
  --accent3: #ff5722; /* Red-Orange */
  --accent4: #9c27b0; /* Purple */
  --gold: #ffd700;
  --text: #f0f4f8;
  --muted: #8b9bb4;
  --dark-red: #ff3333;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Outfit', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  scroll-behavior: smooth;
}

/* ===== NAVIGATION BAR ===== */
.navbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 70px;
  background: rgba(14, 18, 26, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  z-index: 100;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-brand img {
  height: 40px;
  filter: drop-shadow(0 0 10px rgba(0, 188, 212, 0.4));
}

.nav-brand-title {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 1px;
  background: linear-gradient(135deg, #00bcd4 0%, #00e5ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-transform: uppercase;
}

.nav-links {
  display: flex;
  gap: 24px;
}

.nav-link {
  color: var(--muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: color 0.2s, text-shadow 0.2s;
  padding: 8px 12px;
  border-radius: 6px;
}

.nav-link:hover, .nav-link.active {
  color: var(--accent);
  text-shadow: 0 0 8px rgba(0, 188, 212, 0.4);
}

/* ===== COVER PAGE ===== */
.cover {
  min-height: 100vh;
  background: radial-gradient(circle at 50% 30%, #0b1a30 0%, #090b10 70%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 40px 60px 40px;
  position: relative;
  overflow: hidden;
  page-break-after: always;
}

.cover::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: 
    radial-gradient(circle at 10% 10%, rgba(0,188,212,0.08) 0%, transparent 40%),
    radial-gradient(circle at 90% 80%, rgba(156,39,176,0.06) 0%, transparent 40%);
  pointer-events: none;
}

.cover-org {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
  animation: fadeInDown 1s ease-out;
}

.cover-org img {
  width: 150px;
  height: 150px;
  object-fit: contain;
  filter: drop-shadow(0 0 25px rgba(0, 188, 212, 0.3));
}

.cover-org-name {
  text-align: center;
}

.cover-org-name .police {
  font-size: 22px;
  font-weight: 800;
  color: #ff3333;
  letter-spacing: 2px;
  text-transform: uppercase;
  text-shadow: 0 0 10px rgba(255, 51, 51, 0.3);
}

.cover-org-name .tagline {
  font-size: 14px;
  color: var(--muted);
  font-weight: 500;
  margin-top: 4px;
  letter-spacing: 1px;
}

.cover-divider {
  width: 250px;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  margin: 20px 0;
}

.cover-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(0, 188, 212, 0.1);
  border: 1px solid rgba(0, 188, 212, 0.3);
  border-radius: 20px;
  padding: 6px 18px;
  font-size: 12px;
  color: var(--accent);
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 24px;
}

.cover-title {
  font-size: 54px;
  font-weight: 900;
  text-align: center;
  background: linear-gradient(135deg, #ffffff 30%, #a2e8f5 70%, #00bcd4 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.1;
  letter-spacing: -1px;
  margin-bottom: 12px;
}

.cover-subtitle {
  font-size: 18px;
  color: var(--muted);
  text-align: center;
  font-weight: 400;
  max-width: 750px;
  margin-bottom: 40px;
  line-height: 1.5;
}

.cover-version-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 48px;
}

.cover-pill {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--muted);
}

.cover-pill span {
  color: var(--accent);
  font-weight: 600;
}

.cover-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  width: 100%;
  max-width: 800px;
  margin-bottom: 40px;
}

.cover-meta-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 24px;
}

.cover-meta-item .label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
  margin-bottom: 4px;
}

.cover-meta-item .value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.cover-github {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 20px;
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  font-family: 'JetBrains Mono', monospace;
  transition: border-color 0.2s, background 0.2s;
}

.cover-github:hover {
  border-color: var(--accent);
  background: rgba(0, 188, 212, 0.05);
}

.cover-confidential {
  position: absolute;
  top: 90px; right: 40px;
  background: rgba(255,51,51,0.15);
  border: 1px solid rgba(255,51,51,0.4);
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 11px;
  font-weight: 800;
  color: #ff3333;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}

/* ===== CONTENT LAYOUT ===== */
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 100px 40px 60px 40px;
  display: flex;
  gap: 40px;
}

.main-content {
  flex: 1;
}

.sidebar {
  width: 280px;
  position: sticky;
  top: 100px;
  height: fit-content;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.sidebar-menu {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-item a {
  color: var(--muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  display: block;
  padding: 8px 12px;
  border-radius: 6px;
  transition: all 0.2s;
}

.sidebar-item a:hover, .sidebar-item.active a {
  color: var(--accent);
  background: rgba(0, 188, 212, 0.05);
  padding-left: 16px;
}

/* ===== SECTIONS ===== */
.section-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 40px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
}

.section-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0; width: 4px; height: 100%;
  background: var(--accent);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.section-num {
  width: 38px;
  height: 38px;
  background: rgba(0, 188, 212, 0.1);
  border: 1px solid var(--accent);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 800;
  color: var(--accent);
}

.section-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--text);
}

.subsection-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: 32px 0 16px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.subsection-title::before {
  content: '';
  width: 3px; height: 18px;
  background: var(--accent);
  border-radius: 2px;
  display: inline-block;
}

p {
  margin-bottom: 16px;
  font-size: 15px;
  color: #c0ccdc;
  line-height: 1.7;
}

ul, ol {
  margin: 12px 0 20px 24px;
}

li {
  margin-bottom: 8px;
  font-size: 15px;
  color: #c0ccdc;
}

li::marker {
  color: var(--accent);
}

strong {
  color: var(--text);
}

/* ===== METRICS / STATS ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin: 24px 0;
}

.stat-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  transition: transform 0.2s, border-color 0.2s;
}

.stat-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent);
}

.stat-value {
  font-size: 32px;
  font-weight: 800;
  color: var(--accent);
  line-height: 1.2;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ===== INFO/ALERT CARDS ===== */
.alert {
  border-radius: 10px;
  padding: 16px 20px;
  margin: 20px 0;
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.alert-info {
  background: rgba(0, 188, 212, 0.06);
  border: 1px solid rgba(0, 188, 212, 0.2);
}

.alert-success {
  background: rgba(76, 175, 80, 0.06);
  border: 1px solid rgba(76, 175, 80, 0.2);
}

.alert-warning {
  background: rgba(255, 152, 0, 0.06);
  border: 1px solid rgba(255, 152, 0, 0.2);
}

.alert-danger {
  background: rgba(255, 51, 51, 0.06);
  border: 1px solid rgba(255, 51, 51, 0.2);
}

.alert-icon {
  font-size: 18px;
  margin-top: 1px;
}

.alert-text {
  font-size: 14px;
  line-height: 1.5;
  color: #c0ccdc;
}

/* ===== DATA TABLES ===== */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 24px 0;
  font-size: 14px;
}

th {
  padding: 12px 16px;
  text-align: left;
  background: var(--surface2);
  border-bottom: 2px solid var(--border);
  font-weight: 700;
  color: var(--text);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  color: #c0ccdc;
}

tr:hover td {
  background: rgba(255, 255, 255, 0.01);
  color: var(--text);
}

/* ===== CODE & ARCHITECTURE ===== */
.code-block {
  background: #06080c;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  margin: 16px 0;
  overflow-x: auto;
  color: #d1d5db;
}

.code-keyword { color: #ff7b72; }
.code-class { color: #d2a8ff; }
.code-string { color: #a5d6ff; }
.code-comment { color: #8b949e; }
.code-num { color: #79c0ff; }

/* ===== MATHEMATICAL FORMULA ===== */
.math-box {
  background: linear-gradient(135deg, rgba(0, 188, 212, 0.05) 0%, rgba(156, 39, 176, 0.03) 100%);
  border: 1px solid rgba(0, 188, 212, 0.15);
  border-radius: 12px;
  padding: 24px;
  margin: 24px 0;
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px;
  color: var(--text);
  line-height: 1.8;
  position: relative;
}

.math-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 8px;
}

.math-expr {
  font-size: 18px;
  font-weight: 700;
  margin: 12px 0;
  color: #ffffff;
}

.math-legend {
  font-size: 13px;
  color: var(--muted);
  text-align: left;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 8px;
}

/* ===== INTEGRITY GRADE PILL ===== */
.grade-pill {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.grade-a { background: rgba(76, 175, 80, 0.15); border: 1px solid rgba(76, 175, 80, 0.3); color: #4caf50; }
.grade-b { background: rgba(0, 188, 212, 0.15); border: 1px solid rgba(0, 188, 212, 0.3); color: #00bcd4; }
.grade-c { background: rgba(255, 152, 0, 0.15); border: 1px solid rgba(255, 152, 0, 0.3); color: #ff9800; }
.grade-d { background: rgba(244, 67, 54, 0.15); border: 1px solid rgba(244, 67, 54, 0.3); color: #f44336; }

/* ===== SCREENSHOTS GALLERY ===== */
.screenshot-container {
  border-radius: 12px;
  border: 1px solid var(--border);
  overflow: hidden;
  background: #06080c;
  margin: 24px 0;
  box-shadow: 0 15px 30px rgba(0,0,0,0.5);
}

.screenshot-container img {
  width: 100%;
  display: block;
  transition: transform 0.3s;
}

.screenshot-container img:hover {
  transform: scale(1.01);
}

.screenshot-caption {
  background: var(--surface2);
  border-top: 1px solid var(--border);
  padding: 12px 20px;
  font-size: 13px;
  color: var(--muted);
  font-style: italic;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.screenshot-badge {
  background: rgba(0, 188, 212, 0.1);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

/* Animations */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1024px) {
  .container { flex-direction: column; }
  .sidebar { width: 100%; position: static; }
  .navbar { padding: 0 20px; }
  .cover-title { font-size: 38px; }
}

@media print {
  body { background: #ffffff; color: #000000; }
  .navbar, .sidebar { display: none; }
  .container { padding-top: 20px; }
  .section-card { border: none; padding: 20px 0; }
  .section-card::after { display: none; }
  .cover { min-height: 100vh; background: #ffffff; color: #000000; }
  .cover-title { -webkit-text-fill-color: initial; background: none; color: #000000; }
}
</style>
</head>
<body>

<!-- ===== NAVIGATION BAR ===== -->
<nav class="navbar">
  <div class="nav-brand">
    <img src="data:image/png;base64,__IMAGE_LOGO_BASE64__" alt="GPCSSI Logo" />
    <span class="nav-brand-title">Crime Intel Platform</span>
  </div>
  <div class="nav-links">
    <a href="#summary" class="nav-link">Summary</a>
    <a href="#architecture" class="nav-link">Architecture</a>
    <a href="#reasoning" class="nav-link">Reasoning</a>
    <a href="#legal" class="nav-link">Legal Layer</a>
    <a href="#screenshots" class="nav-link">UI Walkthrough</a>
    <a href="#verification" class="nav-link">Verification</a>
  </div>
</nav>

<!-- ===== COVER PAGE ===== -->
<div class="cover" id="summary">
  <div class="cover-confidential">⚠ Law Enforcement Sensitive</div>

  <div class="cover-org">
    <img src="data:image/png;base64,__IMAGE_LOGO_BASE64__" alt="GPCSSI 2024" />
    <div class="cover-org-name">
      <div class="police">Gurugram Cyber Police — GPCSSI 2024</div>
      <div class="tagline">Keeping Gurugram Cyber Safe</div>
    </div>
  </div>

  <div class="cover-divider"></div>

  <div class="cover-badge">📋 Technical Project Report &amp; PRD</div>

  <div class="cover-title">Crime Intelligence Platform</div>
  <div class="cover-subtitle">
    Integrated Case Management, Knowledge Graph Analytics, OSINT Scraping, Deception Assessment, and Procedural Compliance for Modern Forensic Investigation.
  </div>

  <div class="cover-version-row">
    <div class="cover-pill">Core API <span>v1.0.0</span></div>
    <div class="cover-pill">OSINT Service <span>v1.0.0</span></div>
    <div class="cover-pill">Deception Service <span>v0.1.0</span></div>
    <div class="cover-pill">Compliance Engine <span>BNSS/BSA 2023</span></div>
  </div>

  <div class="cover-meta-grid">
    <div class="cover-meta-item">
      <div class="label">Organization</div>
      <div class="value">Gurugram Cyber Police (GPCSSI 2024)</div>
    </div>
    <div class="cover-meta-item">
      <div class="label">Project Scope</div>
      <div class="value">Multi-Service Cyber Investigation Platform</div>
    </div>
    <div class="cover-meta-item">
      <div class="label">Deployment Target</div>
      <div class="value">Docker / Kubernetes / Air-gapped Command Centers</div>
    </div>
    <div class="cover-meta-item">
      <div class="label">Filing Status</div>
      <div class="value" style="color:var(--accent2)">Court Ready / Compliant</div>
    </div>
  </div>

  <a class="cover-github" href="https://github.com/hunny0025/Crime-Intel-Platform" target="_blank">
    🔗 github.com/hunny0025/Crime-Intel-Platform
  </a>
</div>

<!-- ===== CONTENT LAYOUT ===== -->
<div class="container">
  
  <!-- Sidebar Navigation -->
  <aside class="sidebar">
    <span class="sidebar-title">Sections</span>
    <ul class="sidebar-menu">
      <li class="sidebar-item active"><a href="#summary">0. Cover Page</a></li>
      <li class="sidebar-item"><a href="#intro">1. Executive Summary</a></li>
      <li class="sidebar-item"><a href="#architecture">2. System Architecture</a></li>
      <li class="sidebar-item"><a href="#reasoning">3. AIRE &amp; Probability</a></li>
      <li class="sidebar-item"><a href="#legal">4. Legal Layer (BNSS/BSA)</a></li>
      <li class="sidebar-item"><a href="#screenshots">5. UI Walkthrough (Screenshots)</a></li>
      <li class="sidebar-item"><a href="#verification">6. Verification &amp; Tests</a></li>
    </ul>
  </aside>

  <!-- Main Technical Report Content -->
  <main class="main-content">
    
    <!-- Section 1 -->
    <div class="section-card" id="intro">
      <div class="section-header">
        <div class="section-num">1</div>
        <div class="section-title">Executive Summary</div>
      </div>
      <p>
        The <strong>Crime Intelligence Platform</strong> is a state-of-the-art case management, network-analysis, and forensic reasoning tool developed during the <strong>GPCSSI 2024 Internship Program</strong> under the guidance of the <strong>Gurugram Cyber Police</strong>.
      </p>
      <p>
        Modern cybercrime investigations suffer from data fragmentation. Evidence resides across disjointed sources—CDR (Call Detail Records), GPS logs, CCTV footage, IPDR registries, and public OSINT data. In addition, new legislative guidelines (<strong>Bharatiya Nagarik Suraksha Sanhita 2023</strong> and <strong>Bharatiya Sakshya Adhiniyam 2023</strong>) introduce strict statutory timelines and digital evidence certification rules (specifically <strong>Section 65B</strong> electronic signatures).
      </p>
      <p>
        This platform solves these challenges by combining:
      </p>
      <ul>
        <li><strong>Evidence Plane &amp; Theory Plane separation:</strong> Guarantees that raw digital files are preserved immutably, and hypotheses can be generated and tested without corrupting source data.</li>
        <li><strong>Knowledge Graph Entity Extraction:</strong> Normalizes phone numbers, IMEI codes, IP addresses, and bank accounts into a unified Neo4j network mapping relationship structures.</li>
        <li><strong>Autonomous Reasoning (AIRE &amp; HPL):</strong> Auto-evaluates case hypotheses, checks for contradictions, and flags logical gaps.</li>
        <li><strong>Legal Procedural Engine:</strong> Computes automated filing checklists and generates Section 65B Electronic Certificates with cryptographic verification.</li>
      </ul>
    </div>

    <!-- Section 2 -->
    <div class="section-card" id="architecture">
      <div class="section-header">
        <div class="section-num">2</div>
        <div class="section-title">System Architecture</div>
      </div>
      <p>
        The platform utilizes a <strong>distributed microservices architecture</strong> configured through Docker Compose, ensuring physical separation between evidence processing, external scraping (OSINT), and resource-intensive AI models.
      </p>
      
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">Core API</div>
          <div class="stat-label">Port :8000</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">OSINT</div>
          <div class="stat-label">Port :8001</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">Deception</div>
          <div class="stat-label">Port :8002</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">Frontend</div>
          <div class="stat-label">Port :3002</div>
        </div>
      </div>

      <p>
        <strong>Core Microservices Details:</strong>
      </p>
      <ol>
        <li>
          <strong>Core API Service (<code>app/</code>, Port 8000):</strong> 
          Implements case management, MinIO S3 object ingestion, Kafka event workers, Neo4j graph mappings, causal simulation, and database persistence (PostgreSQL). It acts under an air-gapped security model.
        </li>
        <li>
          <strong>OSINT Service (<code>osint-service/</code>, Port 8001):</strong> 
          Handles internet egress. Resolves domain names, queries crt.sh SSL certificate logs, analyzes social networks, and traces multi-hop cryptocurrency transactions in blockchain networks. It NEVER reads raw evidence files directly; it only inserts findings into Neo4j with <code>classification_tag='public_osint'</code>.
        </li>
        <li>
          <strong>Deception Detection Service (<code>deception-detection-service/</code>, Port 8002):</strong> 
          Provides media deepfake classification (placeholder detector) and message stylometric analysis (using z-score sentence structure variance). This service is isolated so GPU dependencies don't bloat the core backend.
        </li>
      </ol>

      <div class="alert alert-info">
        <div class="alert-icon">💡</div>
        <div class="alert-text">
          <strong>Data Isolation Rule:</strong> The OSINT service has internet access enabled, while the Core API does not. This is critical for air-gapped lab operations, ensuring no sensitive evidence leaks onto the public web.
        </div>
      </div>
    </div>

    <!-- Section 3 -->
    <div class="section-card" id="reasoning">
      <div class="section-header">
        <div class="section-num">3</div>
        <div class="section-title">AIRE &amp; Probabilistic Engine</div>
      </div>
      <p>
        The <strong>Autonomous Investigation Reasoning Engine (AIRE)</strong> and the <strong>Probabilistic Engine</strong> calculate credibility levels across complex evidence chains.
      </p>

      <div class="subsection-title">Hypothesis Predicate Language (HPL)</div>
      <p>
        Hypotheses are declared in a formal, machine-executable grammar (HPL) powered by the Lark parser:
      </p>
      
      <div class="code-block">
<span class="code-keyword">PREDICATE</span>: Suspect[priya_suspect] COMMUNICATED_WITH Victim[rohit_victim]
  <span class="code-keyword">DURING</span> TimeInterval[2024-06-25T10:00:00Z, 2024-06-25T11:00:00Z, confidence:0.95]
  <span class="code-keyword">IMPLIES</span> [CallTowerPing(device_id: priya_phone, location_area: area_a)]
  <span class="code-keyword">FORBIDS</span> [GPSRecord(person: priya_suspect, location: location_delhi)]
      </div>

      <p>
        When a hypothesis is compiled, AIRE checks if the <strong>IMPLIES</strong> conditions match nodes in Neo4j (marked "found"). If a <strong>FORBIDS</strong> condition is satisfied (e.g. Priyas phone GPS is detected in Delhi during a Mumbai offense), AIRE flags a contradiction and triggers a confidence drop.
      </p>

      <div class="subsection-title">Timestamp Integrity &amp; Absence Likelihood Ratio</div>
      <p>
        Confidence values degrade over multiple inference hops:
      </p>
      
      <div class="math-box">
        <div class="math-title">Confidence Decay &amp; Absence Ratio Formula</div>
        <div class="math-expr">
          C_{chain} = C_{base} \times (D)^{hops} \quad | \quad ALR = \frac{1 - P(gen|guilty)}{1 - P(gen|innocent)}
        </div>
        <div class="math-legend">
          <div><strong>D (Decay Factor):</strong> Default 0.85 per inference hop.</div>
          <div><strong>ALR (Absence Likelihood Ratio):</strong> Measures weight of missing evidence.</div>
          <div><strong>ALR > 1.0:</strong> Absence suggests active evidence suppression.</div>
        </div>
      </div>
    </div>

    <!-- Section 4 -->
    <div class="section-card" id="legal">
      <div class="section-header">
        <div class="section-num">4</div>
        <div class="section-title">Legal Layer &amp; Court Readiness</div>
      </div>
      <p>
        The platform features built-in support for the new Indian Criminal Laws (Bharatiya Nagarik Suraksha Sanhita 2023 [BNSS] / Bharatiya Sakshya Adhiniyam 2023 [BSA]), which replaced CrPC and the Indian Evidence Act.
      </p>

      <div class="subsection-title">BSA 2023 Section 65B Electronic Certificates</div>
      <p>
        All digital evidence—such as phone screenshots, database dumps, or audio recordings—must carry a Section 65B certificate to be admissible. The platform enables investigators to draft and cryptographically submit these certificates. Once signed, the evidence is tagged <code>section_65b_certified = true</code> in Neo4j, satisfying court admissibility requirements.
      </p>

      <div class="subsection-title">Court Readiness Scoring (C_readiness)</div>
      <p>
        Overall chargesheet filing readiness is determined mathematically:
      </p>

      <div class="math-box">
        <div class="math-title">Court Readiness Formula</div>
        <div class="math-expr">
          C_{readiness} = \left(0.4 \times E_{coverage} + 0.4 \times Q_{evidence} + 0.2 \times P_{compliance}\right) \times (1 - B_{critical})
        </div>
        <div class="math-legend">
          <div><strong>E_coverage:</strong> Satisfied legal elements / total required elements.</div>
          <div><strong>Q_evidence:</strong> Quality score based on 65B certification cover.</div>
          <div><strong>P_compliance:</strong> Procedural timeline checkpoints met (e.g. filing windows).</div>
          <div><strong>B_critical:</strong> Binary indicator. 1 if a critical procedural blocker exists (forces score to 0).</div>
        </div>
      </div>

      <p>
        Based on the output score, the case is categorized into a tier:
      </p>
      <table>
        <thead>
          <tr>
            <th>Score Range</th>
            <th>Readiness Tier</th>
            <th>Filing Action Recommendation</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>0.80 - 1.00</td>
            <td><span class="grade-pill grade-a">Ready For Filing</span></td>
            <td>FILE immediately. Prosecution case is highly secure.</td>
          </tr>
          <tr>
            <td>0.60 - 0.79</td>
            <td><span class="grade-pill grade-b">Near Ready</span></td>
            <td>HOLD. Mitigate remaining defense risks first.</td>
          </tr>
          <tr>
            <td>0.40 - 0.59</td>
            <td><span class="grade-pill grade-c">Developing</span></td>
            <td>HOLD. Seek additional physical/digital corroboration.</td>
          </tr>
          <tr>
            <td>&lt; 0.40</td>
            <td><span class="grade-pill grade-d">Not Ready</span></td>
            <td>DROP. Evidence insufficient to satisfy indictment elements.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Section 5 -->
    <div class="section-card" id="screenshots">
      <div class="section-header">
        <div class="section-num">5</div>
        <div class="section-title">UI Walkthrough &amp; Screenshot Library</div>
      </div>
      <p>
        Below is a complete visual walkthrough of the Crime Intelligence Platform's user interface, captured on the active React frontend interface:
      </p>

      <div class="subsection-title">5.1 Case Workspace &amp; Dashboard</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_DASHBOARD_BASE64__" alt="Case Workspace Dashboard" />
        <div class="screenshot-caption">
          <span>Figure 1: Main Case Workspace showcasing case files, timeline, and cryptographic evidence hashes.</span>
          <span class="screenshot-badge">Workspace</span>
        </div>
      </div>

      <div class="subsection-title">5.2 OSINT Intelligence Hub</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_OSINT_BASE64__" alt="OSINT Intelligence Hub" />
        <div class="screenshot-caption">
          <span>Figure 2: OSINT Hub illustrating domain resolution, WHOIS logs, and social relationship expansion.</span>
          <span class="screenshot-badge">OSINT</span>
        </div>
      </div>

      <div class="subsection-title">5.3 OSINT Crypto wallet tracing</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_CRYPTO_TRACE_BASE64__" alt="OSINT Crypto Trace Tab" />
        <div class="screenshot-caption">
          <span>Figure 3: Cryptocurrency trace panel tracking transactions across multi-hop suspect wallet paths.</span>
          <span class="screenshot-badge">Crypto</span>
        </div>
      </div>

      <div class="subsection-title">5.4 Legal Element Matrix</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_LEGAL_ELEMENTS_BASE64__" alt="Legal Element Matrix" />
        <div class="screenshot-caption">
          <span>Figure 4: Legal elements mapping mapping evidence directly to statutory ingredients of offenses.</span>
          <span class="screenshot-badge">Legal</span>
        </div>
      </div>

      <div class="subsection-title">5.5 Court Readiness Dashboard</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_READINESS_BASE64__" alt="Court Readiness Dashboard" />
        <div class="screenshot-caption">
          <span>Figure 5: Readiness page displaying the overall chargesheet score (C_readiness), procedural milestones, and blockers.</span>
          <span class="screenshot-badge">Readiness</span>
        </div>
      </div>

      <div class="subsection-title">5.6 Investigation Copilot</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_COPILOT_BASE64__" alt="Investigation Copilot" />
        <div class="screenshot-caption">
          <span>Figure 6: Interactive investigator assistant generating evidence recommendations and drafting legal sections.</span>
          <span class="screenshot-badge">AI Copilot</span>
        </div>
      </div>

      <div class="subsection-title">5.7 Cognitive Deception Assessor</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_DECEPTION_BASE64__" alt="Cognitive Deception Assessor" />
        <div class="screenshot-caption">
          <span>Figure 7: Deception Detection view serving deepfake media analysis and stylometric text checks.</span>
          <span class="screenshot-badge">Deception</span>
        </div>
      </div>

      <div class="subsection-title">5.8 Crime Simulation Sandbox</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_SIMULATION_BASE64__" alt="Crime Simulation Page" />
        <div class="screenshot-caption">
          <span>Figure 8: Simulation page allowing investigators to execute what-if scenarios in the sandbox.</span>
          <span class="screenshot-badge">Simulator</span>
        </div>
      </div>

      <div class="subsection-title">5.9 Graph Service Connectivity &amp; Failure Mode</div>
      <div class="screenshot-container">
        <img src="data:image/png;base64,__IMAGE_GRAPH_ERROR_BASE64__" alt="Graph Error Screen" />
        <div class="screenshot-caption">
          <span>Figure 9: Failure mode handling gracefully rendering a warning when the graph database microservice is offline.</span>
          <span class="screenshot-badge">System Error</span>
        </div>
      </div>
    </div>

    <!-- Section 6 -->
    <div class="section-card" id="verification">
      <div class="section-header">
        <div class="section-num">6</div>
        <div class="section-title">Verification &amp; Test Suite</div>
      </div>
      <p>
        To verify backend correctness, the platform implements a complete integration test framework targeting all reasoning layers, database connectors, and mock service providers.
      </p>

      <div class="subsection-title">Running Tests</div>
      <p>
        Run the Python backend verification suite using pytest from the root folder:
      </p>
      <div class="code-block">
$ <span class="code-keyword">pytest</span> tests/ -v
      </div>

      <p>
        The tests verify:
      </p>
      <ul>
        <li><strong>HPL Grammar Verification:</strong> Assures correct parsing of strings into machine structures.</li>
        <li><strong>Absence Base Rates:</strong> Tests accurate calculations of the Absence Likelihood Ratio (ALR).</li>
        <li><strong>Causal Link Constraints:</strong> Confirms Neo4j only forms valid causal chains between events.</li>
        <li><strong>Chargesheet Score Logic:</strong> Proves overall readiness degrades to 0.0 when compliance alerts are present.</li>
        <li><strong>Section 65B Lifecycle:</strong> Validates certificate creation, draft rendering, and signing events.</li>
      </ul>
    </div>

  </main>
</div>

</body>
</html>
"""

# Apply base64 encoding to HTML content
html_content = HTML_TEMPLATE
for key, val in base64_data.items():
    html_content = html_content.replace(f"__IMAGE_{key.upper()}_BASE64__", val)

with open(os.path.join(docs_dir, "crime_intel_report.html"), "w", encoding="utf-8") as f:
    f.write(html_content)
print("crime_intel_report.html generated successfully.")

# Define the Markdown Technical Guide (normal string, no f prefix!)
MD_CONTENT = """# Technical Guide: Crime Intelligence Platform
## Case Management, Knowledge Graph, OSINT, and BNSS/BSA Legal Analytics
### Project Report | GPCSSI 2024 Internship Program | Gurugram Cyber Police

<div align="center">
  <img src="images/gpcssi_logo.png" width="160" alt="GPCSSI Logo" />
  <br/>
  <b>Gurugram Cyber Police — GPCSSI 2024</b>
  <br/>
  <i>Keeping Gurugram Cyber Safe</i>
  <br/>
  <b>Repository:</b> <a href="https://github.com/hunny0025/Crime-Intel-Platform">github.com/hunny0025/Crime-Intel-Platform</a>
</div>

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Forensic Logic & Probabilistic Engine](#3-forensic-logic--probabilistic-engine)
4. [HPL Hypothesis Predicate Grammar](#4-hpl-hypothesis-predicate-grammar)
5. [Legal Subsystem: BNSS 2023 / BSA 2023](#5-legal-subsystem-bnss-2023--bsa-2023)
6. [Interactive User Interface Library](#6-interactive-user-interface-library)
7. [Filing Readiness Classification](#7-filing-readiness-classification)
8. [Testing & Verification](#8-testing--verification)

---

## 1. Executive Summary

The **Crime Intelligence Platform** is a modern technical framework designed for the **Gurugram Cyber Police** as part of the GPCSSI 2024 internship. It consolidates scattered digital forensics feeds, runs cross-evidence correlation, tracks legal compliance, and helps prepare court-admissible electronic packages.

Key achievements include:
- Separating volatile investigator assumptions (Theory Plane) from immutable log entries (Evidence Plane).
- Constructing an automated, config-driven ingestion pipeline mapping data into Neo4j.
- Building compliance timers following the **Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023** deadlines.
- Developing digital certificate tools meeting the requirements of **Section 65B of the Bharatiya Sakshya Adhiniyam (BSA), 2023**.

---

## 2. System Architecture

The platform uses a distributed microservices design running in isolated Docker containers:

```
+------------------------------------------------------------+
|                  NEXT.JS FRONTEND UI (:3002)               |
+------------------------------------------------------------+
                              |
       +----------------------+----------------------+
       | (API calls)                                 | (API calls)
       v                                             v
+-----------------------------+               +-----------------------------+
|   CORE API SERVICE (:8000)  |               |  OSINT INTEL SERVICE (:8001)|
|  - Postgres Evidence dB     |               |  - Domain Lookup & WHOIS    |
|  - MinIO S3 Object Store    |               |  - Social Expansion Graph   |
|  - Kafka Normalizer Worker  |               |  - Crypto Chain Tracing     |
|  - Neo4j Graph DB           |               +-----------------------------+
|  - AIRE & Legal Engine      |                              |
+-----------------------------+                              | (Writes tag: public_osint)
       |                                                     v
       | (Inference Calls)                            +--------------+
       v                                              |  NEO4J GRAPH |
+-----------------------------+                       |   DATABASE   |
|   DECEPTION SERVICE (:8002) |                       |   (Shared)   |
|  - Stylometric Text Heuristic|                       +--------------+
|  - Deepfake Image Classifier|
+-----------------------------+
```

### Port Mappings and Network Boundaries
- **Core API (`:8000`):** Secure backend orchestrator. Completely air-gapped; has no external internet egress.
- **OSINT Service (`:8001`):** Enabled for internet access to query WHOIS records, SSL registers, and cryptocurrency logs.
- **Deception Service (`:8002`):** Processes stylometric message analysis and media deepfake evaluation.
- **Next.js UI (`:3002`):** Direct interface for investigators to manage cases.

---

## 3. Forensic Logic & Probabilistic Engine

The engine calculates confidence levels across multi-hop evidence pathways to help prosecutors evaluate case strength.

### 3.1 Inference Hop Decay
Evidence confidence decays as it moves further from direct observation:
$$C_{chain} = C_{base} \times (D)^{hops}$$
- **$C_{base}$**: Baseline confidence of the original node.
- **$D$ (Decay Factor):** Default `0.85`.
- **$hops$**: Number of inference hops (direct = 0, OSINT-derived starts at 1 due to public source indirection).

### 3.2 Absence Likelihood Ratio (ALR)
When expected evidence is missing, the system evaluates the probability of suppression:
$$ALR = \\frac{P(\\text{absent} \\mid \\text{guilty})}{P(\\text{absent} \\mid \\text{innocent})} = \\frac{1 - P(\\text{gen} \\mid \\text{guilty})}{1 - P(\\text{gen} \\mid \\text{innocent})}$$
- **ALR > 1.0:** The absence of evidence suggests deliberate deletion or tampering.
- **ALR < 1.0:** The absence is consistent with innocence.

---

## 4. HPL Hypothesis Predicate Grammar

Hypotheses are structured in a formal language (HPL) parsed using Earley parser trees:

```
predicate: "PREDICATE:" entity relationship entity during_clause? implies_clause? forbids_clause?
entity: ENTITY_TYPE "[" ENTITY_ID "]"
during_clause: "DURING" "TimeInterval" "[" TIMESTAMP "," TIMESTAMP "," "confidence:" NUMBER "]"
implies_clause: "IMPLIES" "[" evidence_list "]"
forbids_clause: "FORBIDS" "[" evidence_list "]"
```

Example HPL Statement:
```
PREDICATE: Person[suspect_a] COMMUNICATED_WITH Person[suspect_b]
  DURING TimeInterval[2024-06-25T14:00:00Z, 2024-06-25T15:30:00Z, confidence:0.9]
  IMPLIES [CommunicationRecord(sender: suspect_a, receiver: suspect_b)]
  FORBIDS [GPSRecord(person: suspect_a, location: location_out_of_state)]
```

---

## 5. Legal Subsystem: BNSS 2023 / BSA 2023

The system implements automated legal mapping to align with Indian digital evidence standards.

### 5.1 Court Readiness Score ($C_{readiness}$)
Case readiness is measured on a scale from 0.0 to 1.0:
$$C_{readiness} = \\left( 0.4 \\times E_{coverage} + 0.4 \\times Q_{evidence} + 0.2 \\times P_{compliance} \\right) \\times (1 - B_{critical})$$
- **$E_{coverage}$ (Element Coverage):** Percentage of statutory ingredients supported by evidence.
- **$Q_{evidence}$ (Evidence Quality):** Ratio of verified Section 65B certificates to total digital elements.
- **$P_{compliance}$ (Procedural Compliance):** Procedural tasks completed on time.
- **$B_{critical}$:** Binary flag. 1 if a critical procedural violation occurs (e.g. chargesheet deadline missed), dropping the score to 0.0.

### 5.2 Section 65B Certificate Workflows
To satisfy admissibility under the BSA 2023, the system:
1. Generates an automated Draft Certificate listing the device info, hash value, and operator details.
2. Accepts cryptographic signatures from the seizing officer.
3. Updates Neo4j, enabling the `section_65b_certified` flag and appending the hash to the case registry.

---

## 6. Interactive User Interface Library

Below are screenshots of the dashboard interface running on the Next.js React client (`http://localhost:3002/`):

### 6.1 Case Workspace & timeline
The Case Workspace acts as the primary cockpit, showing case statistics, timeline histories, and evidence file registries.
![Case Workspace](images/crime_dashboard.png)

### 6.2 OSINT Intelligence Hub
The OSINT view connects directly to the domain resolution page, showing WHOIS logs, social graph nodes, and public records.
![OSINT Hub](images/crime_osint.png)

### 6.3 Crypto Wallet Tracking Panel
This panel tracks transaction routes and visualizes wallet clusters across multiple transaction hops.
![Crypto Trace](images/crime_crypto_trace.png)

### 6.4 Legal Element Mapping Matrix
The Legal Matrix maps incoming evidence files directly to specific statutory offense elements.
![Legal Matrix](images/crime_legal_elements.png)

### 6.5 Court Readiness Dashboard
The Readiness Dashboard tracks overall chargesheet progress, compliance alerts, and filing timelines.
![Court Readiness](images/crime_readiness.png)

### 6.6 Investigation AI Copilot
The AI Copilot assists investigators by identifying missing elements, suggesting inquiries, and drafting charges.
![AI Copilot](images/crime_copilot.png)

### 6.7 Cognitive Deception Assessor
Serves as the UI for deepfake checks, showing video manipulation probability scores and message stylometry metrics.
![Deception Assessor](images/crime_deception.png)

### 6.8 Scenario Simulation Sandbox
The Simulation Sandbox allows investigators to test what-if scenarios (e.g., changing testimony) in a safe sandbox environment.
![Simulation Sandbox](images/crime_simulation.png)

### 6.9 Graph Service Connectivity Warning
When the Neo4j or OSINT backend is offline, the React UI gracefully displays a reconnection warning.
![Graph Offline](images/crime_graph_error.png)

---

## 7. Filing Readiness Classification

Based on the calculated readiness score, the platform provides automated guidance:

| Score | Tier | Recommendation |
|---|---|---|
| **&ge; 0.80** | **Ready For Filing** | Case is fully corroborated. Proceed to file chargesheet. |
| **0.60 - 0.79** | **Near Ready** | Gaps detected. Resolve pending compliance alerts. |
| **0.40 - 0.59** | **Developing** | Weak chain. Seek additional digital/witness corroboration. |
| **&lt; 0.40** | **Not Ready** | Drop case or perform major reinvestigation. |

---

## 8. Testing & Verification

Run the Python unit and integration test suite to verify all logic components:

```bash
pytest tests/ -v
```

The test suites verify:
- **`hpl/grammar.py`**: Parsing validity, implies/forbids conditions, and predicate mapping.
- **`probabilistic_engine.py`**: Confidence decay formulas, decay hops, and ALR boundary rates.
- **`legal/chargesheet_engine.py`**: Overall chargesheet calculations and blockers.
- **`deception-detection-service`**: Stylometric heuristics and placeholder detection.

---
**Gurugram Cyber Police — GPCSSI 2024**  
*Keeping Gurugram Cyber Safe*  
"""

with open(os.path.join(docs_dir, "crime_intel_guide.md"), "w", encoding="utf-8") as f:
    f.write(MD_CONTENT)
print("crime_intel_guide.md generated successfully.")
