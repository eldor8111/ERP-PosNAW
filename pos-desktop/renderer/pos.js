// ═══════════════════════════════════════════════
// ERPPos Desktop POS — Renderer Logic (Fixed)
// ═══════════════════════════════════════════════
// Support both Electron and Chrome browser
// Electron'da oyna boshqaruvi preload.js orqali (window.posWin); brauzerda yo'q — bu normal.

// XSS himoyasi: innerHTML ga qo'yiladigan barcha server qiymatlari esc() dan o'tadi
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));
// Mahsulot rasmi manzili: /static/... bo'lsa apiUrl qo'shiladi, keyin safeUrl dan o'tadi
const prodImgSrc = (u) => {
  const v = String(u ?? '');
  return safeUrl(v.startsWith('/static') ? (CFG.apiUrl + v) : v);
};
// Rasm manzili: faqat https://, http://(lokal server), data:image/ yoki nisbiy yo'l; aks holda ''
const safeUrl = (u) => {
  const v = String(u ?? '').trim();
  if (!v) return '';
  if (/^data:image\/(png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$/i.test(v)) return esc(v);
  if (/^https?:\/\/[^\s"'<>]+$/i.test(v)) return esc(v);
  if (/^\/(?!\/)[^\s"'<>]*$/.test(v)) return esc(v);
  return '';
};

const PRODUCTION_API = 'https://savdo.e-code.uz';

// ─── Config ───────────────────────────────────
const savedApiUrl = localStorage.getItem('pos_apiUrl');
// If saved URL is localhost, ignore it and use production
const defaultApiUrl = (savedApiUrl && !savedApiUrl.includes('localhost') && !savedApiUrl.includes('127.0.0.1'))
  ? savedApiUrl : PRODUCTION_API;

let CFG = {
  apiUrl: defaultApiUrl,
  autoPrint: localStorage.getItem('pos_autoPrint') === '1',
  unknownProd: localStorage.getItem('pos_unknownProd') === '1',
  // T3.10: fiskal (Hippo) — yoqilsa POST /sales/ va smena yopishda X-Hippo-Factory-Id yuboriladi
  fiscal: localStorage.getItem('pos_fiskalSend') === '1',
  fiskalId: localStorage.getItem('pos_fiskalId') || '',
  discount: localStorage.getItem('pos_discount') !== '0',
  credit: localStorage.getItem('pos_credit') === '1',
  requireCustomer: localStorage.getItem('pos_requireCustomer') === '1',
  printer: localStorage.getItem('pos_printer') || '',
  paperSize: localStorage.getItem('pos_paperSize') || '80mm',
  cassaName: localStorage.getItem('pos_cassaName') || 'Kassa #1',
};

let API_TOKEN = localStorage.getItem('pos_token') || '';
let REFRESH_TOKEN = localStorage.getItem('pos_refresh') || '';
let AUTH_HEADERS = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_TOKEN}` };
// Ko'p korxonali login: select-company uchun vaqtinchalik token
let TEMP_LOGIN_TOKEN = '';
let _refreshPromise = null;

// ─── State ────────────────────────────────────
let allProducts = [];
let categories = [];
let customers = [];
let warehouses = [];
// T1.17: POS qoldig'i tanlangan ombor (filial) bo'yicha; sotuv ham shu ombordan yechiladi
let posWarehouses = [];
let posWarehouseId = localStorage.getItem('pos_warehouseId') || '';
let posCtxLoaded = false;
let suppliers = [];
let favorites = JSON.parse(localStorage.getItem('pos_favorites') || '[]');
// T3.18: to'lov tizimlari (terminallar) serverdan o'qiladi (GET /payment-terminals/mine); localStorage ishlatilmaydi
let paySystems = [];
try { localStorage.removeItem('pos_paySystems'); } catch (e) { /* eski brauzer keshini tozalash */ }
let settingsToggles = { autoPrint: CFG.autoPrint, unknownProd: CFG.unknownProd, fiscal: CFG.fiscal, discount: CFG.discount, credit: CFG.credit, requireCustomer: CFG.requireCustomer };
let cart = [];
let payMethod = 'cash';
let activeSmena = null;
let selectedReturnSale = null;
let kirimItems = [];
let currentUserName = '';
let companyData = null;
let currentUser = null;
// Sotuv uchun Idempotency-Key: bir xil payload qayta yuborilsa (timeout'dan keyin) bir xil kalit
let _saleKey = { sig: '', key: '' };
// Kirim ro'yxatini ko'ra oladigan rollar (GET /inventory/movements kassirga yopiq)
const KIRIM_ROLES = ['super_admin', 'admin', 'director', 'manager', 'warehouse', 'accountant'];

// ─── Init ─────────────────────────────────────
async function init() {
  startClock();
  applySettings();
  renderFavorites();
  renderPaySystems();

  // Check login first
  if (!API_TOKEN) {
    openLoginModal();
  } else {
    loadAllData();
  }
}

function startClock() {
  const el = document.getElementById('tbClock');
  function tick() { el.textContent = new Date().toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }); }
  tick(); setInterval(tick, 1000);
}

// ─── API Helper ───────────────────────────────
function setTokens(access, refresh) {
  API_TOKEN = access || '';
  if (API_TOKEN) localStorage.setItem('pos_token', API_TOKEN); else localStorage.removeItem('pos_token');
  if (refresh !== undefined) {
    REFRESH_TOKEN = refresh || '';
    if (REFRESH_TOKEN) localStorage.setItem('pos_refresh', REFRESH_TOKEN); else localStorage.removeItem('pos_refresh');
  }
  AUTH_HEADERS = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_TOKEN}` };
}

function apiBase() {
  return (document.getElementById('settApiUrl')?.value || CFG.apiUrl).replace(/\/$/, '');
}

// 401 da refresh_token bilan yangi token olish (bir vaqtda bitta so'rov). Muvaffaqiyatsiz bo'lsa false.
async function tryRefreshToken() {
  if (!REFRESH_TOKEN) return false;
  if (!_refreshPromise) {
    _refreshPromise = (async () => {
      try {
        const res = await fetch(apiBase() + '/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: REFRESH_TOKEN }),
        });
        if (!res.ok) return false;
        const d = await res.json();
        if (!d.access_token) return false;
        setTokens(d.access_token, d.refresh_token || REFRESH_TOKEN);
        return true;
      } catch (_) { return false; }
      finally { setTimeout(() => { _refreshPromise = null; }, 0); }
    })();
  }
  return _refreshPromise;
}

// Fiskal sarlavha: faqat POST /sales/ va smena yopishda, toggle yoqilgan va Factory ID kiritilgan bo'lsa
// (frontend/src/api/axios.js dagi Hippo mantig'iga mos)
function fiscalHeaders(path, method) {
  if (String(method || 'GET').toUpperCase() !== 'POST') return {};
  if (!CFG.fiscal || !CFG.fiskalId) return {};
  const p = String(path).split('?')[0];
  const isSale = p === '/sales/' || p === '/sales';
  const isShiftClose = p === '/shifts/close' || /^\/shifts\/\d+\/close$/.test(p);
  return (isSale || isShiftClose) ? { 'X-Hippo-Factory-Id': String(CFG.fiskalId) } : {};
}

async function api(path, opts = {}, _retried = false) {
  const url = apiBase() + '/api' + path;
  try {
    const res = await fetch(url, {
      ...opts,
      headers: { ...AUTH_HEADERS, ...fiscalHeaders(path, opts.method), ...(opts.headers || {}) },
    });
    if (res.status === 401) {
      if (!_retried && await tryRefreshToken()) return api(path, opts, true);
      setTokens('', '');
      openLoginModal();
      throw new Error('Sessiya tugadi. Qaytadan kiring.');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Server xatosi' }));
      const d = err.detail;
      throw new Error(typeof d === 'string' ? d : (Array.isArray(d) ? d.map(x => x.msg || '').filter(Boolean).join('; ') : '') || res.statusText);
    }
    return res.status === 204 ? null : res.json();
  } catch (e) {
    if (e.name === 'TypeError') throw new Error("Serverga ulanib bo'lmadi. Backend ishlaydimi?");
    throw e;
  }
}

// ─── Login ────────────────────────────────────
function openLoginModal() {
  document.getElementById('loginModal').classList.add('show');
  document.getElementById('loginOverlay').classList.add('show');
  document.getElementById('loginUsername').value = '';
  document.getElementById('loginPassword').value = '';
  document.getElementById('loginError').textContent = '';
  setTimeout(() => document.getElementById('loginUsername').focus(), 100);
}

function closeLoginModal() {
  document.getElementById('loginModal').classList.remove('show');
  document.getElementById('loginOverlay').classList.remove('show');
}

async function doLogin() {
  const rawPhone = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errEl = document.getElementById('loginError');
  const btn = document.getElementById('loginBtn');

  if (!rawPhone || !password) { errEl.textContent = 'Telefon va parol kiriting'; return; }

  // Auto-prepend +998 if not already present
  let phone = rawPhone;
  if (!phone.startsWith('+')) {
    phone = '+998' + phone.replace(/^998/, '');
  }

  btn.disabled = true;
  btn.textContent = 'Kirilmoqda...';
  errEl.textContent = '';

  try {
    const base = CFG.apiUrl.replace(/\/$/, '');

    let res;
    try {
      res = await fetch(base + '/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password }),
      });
    } catch (networkErr) {
      throw new Error(`❌ Serverga ulanib bo'lmadi!\nServer: ${base}\n(Backend ishlab turganmi?)`);
    }

    if (!res.ok) {
      let detail = 'Telefon yoki parol noto\'g\'ri';
      try {
        const err = await res.json();
        detail = err.detail || detail;
      } catch (_) {}
      if (res.status === 401) detail = 'Telefon yoki parol noto\'g\'ri';
      if (res.status === 404) detail = 'Server topilmadi';
      if (res.status >= 500) detail = 'Server ichki xatosi';
      throw new Error(detail);
    }

    const data = await res.json();
    // Ko'p korxonali foydalanuvchi: access_token yo'q — avval korxonani tanlash kerak
    if (data.needs_company_selection) {
      TEMP_LOGIN_TOKEN = data.temp_token || '';
      showCompanyChoices(data.companies || []);
      return;
    }
    finishLogin(data);
  } catch (e) {
    errEl.style.whiteSpace = 'pre-line';
    errEl.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Kirish';
  }
}

// Login muvaffaqiyatli: tokenlar saqlanadi, modal yopiladi, ma'lumotlar yuklanadi
function finishLogin(data) {
  if (!data || !data.access_token) throw new Error('Server token qaytarmadi. Qaytadan urinib ko\'ring.');
  TEMP_LOGIN_TOKEN = '';
  setTokens(data.access_token, data.refresh_token || '');
  posCtxLoaded = false; posWarehouses = [];
  closeCompanyModal();
  closeLoginModal();
  toast('✅ Muvaffaqiyatli kirildi!', 'ok');
  loadAllData();
}

// Korxona tanlash modali (nomlar textContent bilan — XSS xavfsiz)
function showCompanyChoices(companies) {
  const list = document.getElementById('companyChoiceList');
  const errEl = document.getElementById('companyChoiceError');
  if (errEl) errEl.textContent = '';
  list.replaceChildren();
  companies.forEach(c => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-outline';
    btn.style.cssText = 'width:100%;text-align:left;padding:12px 14px;margin-bottom:8px';
    btn.textContent = c.company_name || ("Korxona #" + c.company_id);
    btn.addEventListener('click', () => selectCompany(c.company_id));
    list.appendChild(btn);
  });
  closeLoginModal();
  document.getElementById('companyModal').classList.add('show');
  document.getElementById('loginOverlay').classList.add('show');
}

function closeCompanyModal() {
  document.getElementById('companyModal')?.classList.remove('show');
}

function cancelCompanyChoice() {
  TEMP_LOGIN_TOKEN = '';
  closeCompanyModal();
  openLoginModal();
}

async function selectCompany(companyId) {
  const errEl = document.getElementById('companyChoiceError');
  if (errEl) errEl.textContent = '';
  try {
    const res = await fetch(apiBase() + '/api/auth/select-company', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ temp_token: TEMP_LOGIN_TOKEN, company_id: Number(companyId) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((typeof err.detail === 'string' && err.detail) || "Korxonani tanlab bo'lmadi");
    }
    finishLogin(await res.json());
  } catch (e) {
    if (errEl) errEl.textContent = e.name === 'TypeError' ? "Serverga ulanib bo'lmadi" : e.message;
  }
}

function handleLoginKeydown(e) {
  if (e.key === 'Enter') doLogin();
}

function doLogout() {
  setTokens('', '');
  TEMP_LOGIN_TOKEN = '';
  // Keyingi kirgan korxona uchun eski chek shabloni qolmasin
  try { localStorage.removeItem('erp_receipt_settings'); } catch (_) {}
  currentUser = null; companyData = null;
  activeSmena = null;
  cart = [];
  posCtxLoaded = false; posWarehouseId = ''; posWarehouses = [];
  openLoginModal();
  closeDotMenu();
}

// ─── Load Data ────────────────────────────────
async function loadAllData() {
  // Rol va korxona/filial ma'lumoti boshqa yuklashlar (Kirim, korxona nomi, shablon) uchun kerak
  await loadCurrentUser();
  await Promise.allSettled([
    loadProducts(),
    loadCategories(),
    loadCustomers(),
    loadWarehouses(),
    loadSuppliers(),
    checkSmena(),
    checkApiStatus(),
    loadKirimList(),
    loadKassaStats(),
    loadCompanyInfo(),
    loadReceiptTemplates(),
    loadPaySystems(),
  ]);
}

// Filial default ombori va sotiladigan omborlar (eski serverda endpoint yo'q — jim o'tkaziladi)
async function loadPosContext() {
  try {
    const ctx = await api('/products/pos-context');
    posWarehouses = Array.isArray(ctx?.warehouses) ? ctx.warehouses : [];
    const ok = posWarehouses.some(w => String(w.id) === String(posWarehouseId));
    if (!ok) {
      posWarehouseId = ctx?.default_warehouse_id ? String(ctx.default_warehouse_id)
        : (posWarehouses.length === 1 ? String(posWarehouses[0].id) : '');
    }
    posCtxLoaded = true;
  } catch (e) { posWarehouses = []; posWarehouseId = ''; }
  renderPosWarehouseSelect();
}

function setPosWarehouse(id) {
  posWarehouseId = String(id || '');
  try { localStorage.setItem('pos_warehouseId', posWarehouseId); } catch (_) {}
  cart = []; renderCart();
  renderPosWarehouseSelect();
  loadProducts();
}

// Ombor tanlagich: sotuv paneli (T1.17) va sozlamalardagi settWarehouse bitta manbadan to'ldiriladi.
// Bitta ombor bo'lsa avto-tanlanadi va tanlagich ko'rinmaydi; bir nechta bo'lsa tanlash majburiy.
function renderPosWarehouseSelect() {
  const fill = (sel) => {
    sel.replaceChildren();
    if (!posWarehouseId) {
      const ph = document.createElement('option');
      ph.value = ''; ph.textContent = '— Omborni tanlang —';
      sel.appendChild(ph);
    }
    posWarehouses.forEach(w => {
      const o = document.createElement('option');
      o.value = String(w.id); o.textContent = w.name;
      sel.appendChild(o);
    });
    sel.value = posWarehouseId;
  };
  let sel = document.getElementById('saleWarehouseSel');
  if (posWarehouses.length <= 1) { if (sel) sel.remove(); }
  else {
    if (!sel) {
      const inp = document.getElementById('saleSearchInput');
      if (inp && inp.parentNode) {
        sel = document.createElement('select');
        sel.id = 'saleWarehouseSel';
        sel.className = 'fsel-sm';
        sel.onchange = () => setPosWarehouse(sel.value);
        inp.parentNode.insertBefore(sel, inp.nextSibling);
      }
    }
    if (sel) fill(sel);
  }
  const row = document.getElementById('settWarehouseRow');
  const ss = document.getElementById('settWarehouse');
  if (row) row.style.display = posWarehouses.length > 1 ? '' : 'none';
  if (ss && posWarehouses.length > 1) {
    fill(ss);
    ss.onchange = () => setPosWarehouse(ss.value);
  }
}

function attachSellSources(list, pool) {
  list.forEach(p => {
    if (p.product_type === 'sell' && p.conversion) {
      const src = pool.find(x => String(x.id) === String(p.conversion.source_product_id));
      p._sourceStock = src ? Number(src.stock_quantity || 0) : null;
      p._conversionRatio = Number(p.conversion.ratio || 1);
      p._sourceProductId = p.conversion.source_product_id;
    }
  });
}

async function loadProducts() {
  try {
    if (!posCtxLoaded) await loadPosContext();
    // pos-list tezroq va product_type qaytaradi; qoldiq tanlangan ombor bo'yicha
    const data = await api('/products/pos-list?limit=500'
      + (posWarehouseId ? '&warehouse_id=' + encodeURIComponent(posWarehouseId) : ''));
    const raw = Array.isArray(data) ? data : (data?.items || []);
    // sell tipli mahsulotlar uchun manba qoldiqlarini biriktirish
    attachSellSources(raw, raw);
    allProducts = raw;
    renderSaleGrid(allProducts);
    renderProductsTable(allProducts);
    populateCatFilter();
    toast('Mahsulotlar yuklandi ✓', 'ok');
  } catch (e) {
    // fallback: oddiy endpoint
    try {
      const data2 = await api('/products/?limit=200');
      allProducts = Array.isArray(data2) ? data2 : (data2?.items || []);
      renderSaleGrid(allProducts);
      renderProductsTable(allProducts);
      populateCatFilter();
      toast('Mahsulotlar yuklandi ✓', 'ok');
    } catch (e2) {
      document.getElementById('saleGrid').innerHTML = `<div class="empty-state">⚠️ ${esc(e2.message)}</div>`;
      toast(e2.message, 'err');
    }
  }
}

async function loadCategories() {
  try {
    const data = await api('/categories/all');
    categories = Array.isArray(data) ? data : [];
  } catch (e) { categories = []; }
}

// Mijoz tanlash: <input list> + <datalist>; GET /customers?search=&limit=20, 300 ms debounce.
// Variantlar textContent bilan yoziladi (XSS xavfsiz). Tanlangan mijoz id si yashirin #saleCustomer da.
let _custTimer = null;
let _custByLabel = new Map();

function customerLabel(c) {
  return (c.name || ('#' + c.id)) + (c.phone ? ' | ' + c.phone : '');
}

function renderCustomerOptions() {
  const dl = document.getElementById('saleCustomerList');
  if (!dl) return;
  dl.replaceChildren();
  _custByLabel = new Map();
  customers.forEach(c => {
    let label = customerLabel(c);
    if (_custByLabel.has(label)) label += ' #' + c.id;   // bir xil nom+telefon bo'lsa farqlash
    _custByLabel.set(label, c.id);
    const o = document.createElement('option');
    o.value = label;
    dl.appendChild(o);
  });
}

async function loadCustomers(q = '') {
  try {
    const data = await api('/customers?limit=20&search=' + encodeURIComponent(q || ''));
    customers = Array.isArray(data) ? data : (data?.items || []);
    renderCustomerOptions();
  } catch (e) {
    // T3.8: oflayn/xato — oxirgi yuklangan ro'yxat saqlanadi (klientda qidiriladi), bo'shatilmaydi
    renderCustomerOptions();
  }
}

function customerSearchInput(v) {
  const hid = document.getElementById('saleCustomer');
  // Ro'yxatdan aniq variant tanlangan bo'lsa id biriktiriladi, aks holda tanlov bekor
  const id = _custByLabel.get(v);
  hid.value = id ? String(id) : '';
  onCustomerChange();
  if (id) return;
  clearTimeout(_custTimer);
  _custTimer = setTimeout(() => loadCustomers(v.trim()), 300);
}

function clearCustomer() {
  const hid = document.getElementById('saleCustomer');
  const inp = document.getElementById('saleCustomerSearch');
  if (hid) hid.value = '';
  if (inp) inp.value = '';
  onCustomerChange();
}

async function loadWarehouses() {
  try {
    const data = await api('/inventory/warehouses');
    warehouses = Array.isArray(data) ? data : [];
    const sel = document.getElementById('kirimWarehouse');
    if (sel) sel.innerHTML = '<option value="">— Tanlang —</option>'
      + warehouses.map(w => `<option value="${esc(w.id)}">${esc(w.name)}</option>`).join('');
  } catch (e) { warehouses = []; }
}

async function loadSuppliers() {
  try {
    const data = await api('/suppliers/?limit=100');
    suppliers = Array.isArray(data) ? data : (data?.items || []);
    const sel = document.getElementById('kirimSupplier');
    if (sel) sel.innerHTML = '<option value="">— Tanlang —</option>'
      + suppliers.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
  } catch (e) { suppliers = []; }
}

async function checkApiStatus() {
  const el = document.getElementById('apiStatus');
  if (!el) return;
  try {
    await api('/health');
    el.textContent = '✅ Ulangan';
    el.style.color = 'var(--green)';
  } catch {
    try {
      await api('/products/?limit=1');
      el.textContent = '✅ Ulangan';
      el.style.color = 'var(--green)';
    } catch (e) {
      el.textContent = '❌ Ulanmagan';
      el.style.color = 'var(--red)';
    }
  }
}

async function loadCurrentUser() {
  try {
    const user = await api('/auth/me');
    if (user) {
      currentUser = user;
      currentUserName = user.name || user.username || user.phone || 'Kassir';
      applyRoleVisibility();
    }
  } catch (e) {
    console.log('User info load error:', e.message);
  }
}

// Kirim ro'yxati kassirga yopiq (GET /inventory/movements) — kassir roli uchun Kirim tabi yashiriladi
function canSeeKirim() {
  return !!currentUser && KIRIM_ROLES.includes(String(currentUser.role || ''));
}

function applyRoleVisibility() {
  const show = canSeeKirim();
  document.querySelectorAll('[data-tab="kirim"]').forEach(el => { el.style.display = show ? '' : 'none'; });
  const view = document.getElementById('view-kirim');
  if (view && !show) view.classList.remove('active');
}

// Sarlavha: "Korxona · Filial · Kassa". Korxona GET /billing/my-company, filial GET /branches/{id}
// (GET /companies/{id} yo'q; BranchOut da balans yo'q). Nomlar textContent bilan yoziladi.
async function loadCompanyInfo() {
  try {
    const user = currentUser || await api('/auth/me');
    if (!user || !user.company_id) return;
    let company = null;
    let branch = null;
    try { company = await api('/billing/my-company'); } catch (e) { console.log('Company info load error:', e.message); }
    if (user.branch_id) {
      try { branch = await api(`/branches/${user.branch_id}`); } catch (e) { console.log('Branch info load error:', e.message); }
    }
    companyData = { ...(company || {}), branch };
    renderCompanyHeader();
  } catch (e) {
    console.log('Company info load error:', e.message);
  }
}

function renderCompanyHeader() {
  const companyInfoEl = document.getElementById('companyInfo');
  const companyNameEl = document.getElementById('companyName');
  const companyCodeEl = document.getElementById('companyCode');
  if (!companyInfoEl || !companyData || !companyData.name) return;
  companyInfoEl.style.display = 'flex';
  const parts = [companyData.name];
  if (companyData.branch && companyData.branch.name) parts.push(companyData.branch.name);
  parts.push(CFG.cassaName);
  companyNameEl.textContent = parts.join(' · ');
  companyCodeEl.textContent = companyData.org_code || '-';
}

// Chek shabloni: GET /companies/me/receipt_templates -> localStorage.erp_receipt_settings
// ({r58, r80, nak, _company_id}); showReceipt shu kalitdan o'qiydi.
async function loadReceiptTemplates() {
  try {
    const data = await api('/companies/me/receipt_templates');
    const tpl = (data && data.receipt_templates) || {};
    const stored = { ...tpl, _company_id: currentUser ? currentUser.company_id : null };
    localStorage.setItem('erp_receipt_settings', JSON.stringify(stored));
  } catch (e) {
    console.log('Receipt template load error:', e.message);
  }
}

// ─── Tab Switch ───────────────────────────────
function switchTab(tab) {
  if (tab === 'kirim' && !canSeeKirim()) { switchTab('sale'); return; }
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const v = document.getElementById('view-' + tab);
  if (v) v.classList.add('active');
  if (tab === 'kassa') loadKassaStats();
  if (tab === 'kirim') loadKirimList();
  if (tab === 'settings') applySettings();
}

// ─── 3-Dot Menu ───────────────────────────────
function toggleDotMenu() {
  document.getElementById('dotDropdown').classList.toggle('show');
}
function closeDotMenu() {
  document.getElementById('dotDropdown').classList.remove('show');
}
document.addEventListener('click', e => {
  if (!document.getElementById('dotMenuWrap')?.contains(e.target)) closeDotMenu();
});

// ─── Window Controls ──────────────────────────
function winCtrl(cmd) {
  if (window.posWin) window.posWin.send(cmd);
  else if (cmd === 'close' && confirm('Dasturdan chiqishni istaysizmi?')) window.close();
}

// ─── SALE: Product Grid ───────────────────────
function populateCatFilter() {
  const sel = document.getElementById('saleCatFilter');
  const catSet = [...new Set(allProducts.map(p => p.category_name || p.cat_name || '').filter(Boolean))];
  sel.innerHTML = '<option value="">Barcha kategoriyalar</option>'
    + catSet.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
}

function saleSearch(q) {
  applySaleFilter(q);
  scheduleServerSearch(q);
}

function applySaleFilter(q) {
  const catFilter = document.getElementById('saleCatFilter').value;
  let list = allProducts;
  if (catFilter) list = list.filter(p => (p.category_name || p.cat_name || '') === catFilter);
  if (q) {
    const lq = q.toLowerCase();
    list = list.filter(p => p.name.toLowerCase().includes(lq) || (p.barcode || '').includes(q) || (p.sku || '').includes(lq));
  }
  renderSaleGrid(list);
}

// Ro'yxat 500 ta bilan cheklangan: qidiruv serverga ham o'tadi (300 ms debounce),
// topilgan mahsulotlar allProducts ga qo'shiladi (tanlangan ombor qoldig'i bilan).
let _prodSearchTimer = null;
function scheduleServerSearch(q) {
  clearTimeout(_prodSearchTimer);
  const term = (q || '').trim();
  if (term.length < 2) return;
  _prodSearchTimer = setTimeout(async () => {
    try {
      const data = await api('/products/pos-list?limit=50&search=' + encodeURIComponent(term)
        + (posWarehouseId ? '&warehouse_id=' + encodeURIComponent(posWarehouseId) : ''));
      const found = Array.isArray(data) ? data : (data?.items || []);
      const have = new Set(allProducts.map(p => String(p.id)));
      const fresh = found.filter(p => !have.has(String(p.id)));
      if (!fresh.length) return;
      attachSellSources(fresh, allProducts.concat(fresh));
      allProducts = allProducts.concat(fresh);
      // foydalanuvchi shu orada boshqa narsa yozgan bo'lsa, eskirgan natijani chizmaymiz
      const cur = document.getElementById('saleSearchInput')?.value.trim();
      if (cur === term) applySaleFilter(term);
    } catch (_) { /* qidiruv xatosi sotuvni to'xtatmaydi */ }
  }, 300);
}

// Lokal ro'yxatda yo'q shtrix-kod/SKU/PLU: GET /products/barcode/{code}; topilsa allProducts ga qo'shiladi
async function lookupBarcodeOnServer(code) {
  try {
    const p = await api('/products/barcode/' + encodeURIComponent(code));
    if (!p || p.id == null) return null;
    const known = allProducts.find(x => String(x.id) === String(p.id));
    if (known) return known;
    // Tanlangan ombor qoldig'ini aniqlash uchun pos-list dan nomi bo'yicha ham so'raymiz
    let item = p;
    try {
      const d = await api('/products/pos-list?limit=20&search=' + encodeURIComponent(p.name || code)
        + (posWarehouseId ? '&warehouse_id=' + encodeURIComponent(posWarehouseId) : ''));
      const arr = Array.isArray(d) ? d : (d?.items || []);
      item = arr.find(x => String(x.id) === String(p.id)) || p;
    } catch (_) { /* ProductOut ning o'zi ishlatiladi */ }
    attachSellSources([item], allProducts.concat([item]));
    allProducts = allProducts.concat([item]);
    return item;
  } catch (_) { return null; }
}

async function saleBarcodeKey(e) {
  if (e.key === 'Enter') {
    const input = e.target;
    const q = input.value.trim();
    if (!q) return;
    const p = allProducts.find(x => x.barcode === q || x.sku === q);
    if (p) { addToCartById(p.id, 1); input.value = ''; renderSaleGrid(allProducts); return; }
    // T3.12: tarozi shtrix-kodi 20|21|22 + 5 (PLU) + 5 (vazn, gramm) + 1; PLU = mahsulotning plu_code si
    if (/^\d{13}$/.test(q) && (q.startsWith('20') || q.startsWith('21') || q.startsWith('22'))) {
      const itemCode = q.substring(2, 7);
      const weightGram = parseInt(q.substring(7, 12), 10) || 0;
      const weightKg = weightGram / 1000;
      let scaleProduct = allProducts.find(x => x.plu_code != null && Number(x.plu_code) === Number(itemCode));
      if (!scaleProduct) scaleProduct = await lookupBarcodeOnServer(itemCode);
      if (scaleProduct) {
        addToCartById(scaleProduct.id, weightKg);
        input.value = ''; renderSaleGrid(allProducts);
      } else {
        toast('Tarozi mahsuloti topilmadi (Kodi: ' + itemCode + ')', 'err');
        input.value = '';
      }
      return;
    }
    // Lokal ro'yxatda yo'q (masalan 500 tadan keyingi tovar): serverdan qidiramiz
    const sp = await lookupBarcodeOnServer(q);
    if (sp) { addToCartById(sp.id, 1); input.value = ''; renderSaleGrid(allProducts); }
    else saleSearch(q);
  }
}

function _getSellableQty(p) {
  // sell tipli mahsulot uchun manba qoldig'idan hisoblangan qoldiq
  if (p.product_type === 'sell') {
    if (p._sourceStock != null && p._conversionRatio) {
      return p._sourceStock / p._conversionRatio;
    }
    return null; // ma'lum emas
  }
  return Number(p.stock_quantity || 0);
}

function renderSaleGrid(list) {
  const el = document.getElementById('saleGrid');
  if (!list.length) { el.innerHTML = '<div class="empty-state">Mahsulot topilmadi</div>'; return; }
  el.innerHTML = list.map(p => {
    const imgSrc = prodImgSrc(p.image_url);
    const img = imgSrc
      ? `<img src="${imgSrc}" alt="">`
      : `<span style="font-size:28px">📦</span>`;
    const isSell = p.product_type === 'sell';
    const sellQty = _getSellableQty(p);
    const qty = isSell ? (sellQty ?? 0) : Number(p.stock_quantity || 0);
    const outOfStock = qty <= 0;
    const colorCls = qty <= 0 ? 'style="color:var(--red)"' : qty <= (p.min_stock || 5) ? 'style="color:var(--amber)"' : '';
    let stockLabel;
    if (isSell) {
      if (sellQty == null) {
        stockLabel = '⭐ Tarkibiy';
      } else if (sellQty <= 0) {
        stockLabel = '❌ Xom-ashyo tugagan';
      } else {
        stockLabel = `🔄 ~${fmt(Math.floor(sellQty))} ${esc(p.unit || 'ta')} sotsa bo'ladi`;
      }
    } else {
      stockLabel = `Qoldiq: ${fmt(qty)} ${esc(p.unit || 'dona')}`;
    }
    return `<div class="prod-card${outOfStock ? ' out-of-stock' : ''}" data-prod-id="${esc(p.id)}" onclick="addToCartById(${Number(p.id)})">
      <div class="prod-card-img">${img}</div>
      <div class="prod-card-name">${esc(p.name)}${isSell ? ' <span style="font-size:9px;background:#6366f1;color:#fff;border-radius:4px;padding:1px 4px">Tark.</span>' : ''}</div>
      <div class="prod-card-price">${fmt(p.sale_price)} so'm</div>
      <div class="prod-card-stock" ${colorCls}>${stockLabel}</div>
    </div>`;
  }).join('');
}

// ─── CART ─────────────────────────────────────
function addToCartById(id, qtyToAdd = 1) {
  const prod = allProducts.find(p => p.id === id);
  if (!prod) return;
  addToCart(prod, qtyToAdd);
}

function addToCart(prod, qtyToAdd = 1) {
  const existing = cart.find(x => x.id === prod.id);
  if (existing) existing.qty += qtyToAdd;
  else cart.push({ ...prod, qty: qtyToAdd });
  renderCart();
  toast(prod.name + ' qo\'shildi', 'ok');
}

function removeFromCart(idx) { cart.splice(idx, 1); renderCart(); }

function changeQty(idx, delta) {
  cart[idx].qty = Math.max(1, cart[idx].qty + delta);
  renderCart();
}

function clearCart() { cart = []; renderCart(); }

function renderCart() {
  const itemsEl = document.getElementById('cartItems');
  const totalsEl = document.getElementById('cartTotals');
  const payEl = document.getElementById('paySection');

  if (!cart.length) {
    itemsEl.innerHTML = `<div class="cart-empty"><svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M3 3h2l.4 2M7 13h10l4-8H5.4"/><circle cx="9" cy="19" r="1"/><circle cx="20" cy="19" r="1"/></svg><span>Savat bo'sh</span></div>`;
    totalsEl.style.display = 'none';
    payEl.style.display = 'none';
    return;
  }
  itemsEl.innerHTML = cart.map((item, i) => `
    <div class="cart-item">
      <div class="ci-top">
        <div class="ci-name">${esc(item.name)}</div>
        <button class="ci-remove" onclick="removeFromCart(${i})">✕</button>
      </div>
      <div class="ci-bottom">
        <div class="qty-ctrl">
          <button class="qty-btn" onclick="changeQty(${i},-1)">−</button>
          <span class="qty-disp">${item.qty}</span>
          <button class="qty-btn" onclick="changeQty(${i},1)">+</button>
        </div>
        <span class="ci-price">${fmt(item.sale_price * item.qty)} so'm</span>
      </div>
    </div>`).join('');
  totalsEl.style.display = 'flex';
  payEl.style.display = 'flex';
  calcCart();
}

function calcCart() {
  const discount = parseFloat(document.getElementById('discountInp').value) || 0;
  const subTotal = cart.reduce((s, x) => s + x.sale_price * x.qty, 0);
  const total = Math.round(subTotal * (1 - discount / 100));
  const qtyTotal = cart.reduce((s, x) => s + x.qty, 0);
  document.getElementById('cartQtyTotal').textContent = qtyTotal + ' dona';
  document.getElementById('cartGrandTotal').textContent = fmt(total) + ' so\'m';
  calcChange();
}

function getTotal() {
  const discount = parseFloat(document.getElementById('discountInp').value) || 0;
  const subTotal = cart.reduce((s, x) => s + x.sale_price * x.qty, 0);
  return Math.round(subTotal * (1 - discount / 100));
}

function calcChange() {
  const paid = parseFloat(document.getElementById('payAmountInp').value) || 0;
  const total = getTotal();
  const changeEl = document.getElementById('changeRow');
  if (paid > 0 && payMethod === 'cash') {
    changeEl.style.display = 'flex';
    document.getElementById('changeVal').textContent = fmt(Math.max(0, paid - total)) + ' so\'m';
  } else {
    changeEl.style.display = 'none';
  }
}

function selectPayMethod(m) {
  payMethod = m;
  document.querySelectorAll('.pay-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('pm-' + m)?.classList.add('active');
  const dueWrap = document.getElementById('debtDueWrap');
  if (dueWrap) dueWrap.style.display = m === 'debt' ? '' : 'none';
  calcChange();
}

// ─── FILL TOTAL ────────────────────────────────
function fillTotal() {
  const total = getTotal();
  document.getElementById('payAmountInp').value = total;
  calcChange();
}

// ─── CUSTOMER CHANGE ──────────────────────────
function onCustomerChange() {
  const inp = document.getElementById('saleCustomerSearch');
  if (!inp) return;
  const hasCustomer = !!document.getElementById('saleCustomer').value;
  inp.style.color = hasCustomer ? 'var(--ink)' : (CFG.requireCustomer ? 'var(--red)' : 'var(--ink3)');
  inp.style.borderColor = (!hasCustomer && CFG.requireCustomer) ? 'var(--red)' : '';
}

// ─── PROCESS SALE ─────────────────────────────
function newSaleKey() {
  try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (_) {}
  return 'pos-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
}

// Bir xil sotuv (payload) qayta yuborilsa (timeout'dan keyin) xuddi shu kalit; savat o'zgarsa yangi kalit
function saleKeyFor(payload) {
  const sig = JSON.stringify(payload);
  if (_saleKey.sig !== sig) _saleKey = { sig, key: newSaleKey() };
  return _saleKey.key;
}

async function processSale() {
  if (!cart.length) { toast('Savat bo\'sh', 'warn'); return; }

  // Check mandatory customer
  const customerId = document.getElementById('saleCustomer').value;
  if (CFG.requireCustomer && !customerId) {
    toast('⚠️ Mijoz tanlanmagan! Sozlamalarda "Mijoz tanlanmasa sotmasin" yoqilgan.', 'err');
    document.getElementById('saleCustomerSearch')?.focus();
    return;
  }
  // Nasiya mijozsiz bo'lmaydi (server ham 400 beradi) — so'rov yuborilmaydi
  if (payMethod === 'debt' && !customerId) {
    toast('Nasiya uchun mijoz tanlang', 'err');
    document.getElementById('saleCustomerSearch')?.focus();
    return;
  }
  // Bir nechta ombor bo'lsa, qoldiq va sotuv bitta ombor bo'yicha bo'lishi uchun tanlash majburiy
  if (posWarehouses.length > 1 && !posWarehouseId) {
    toast('Avval omborni tanlang', 'warn');
    return;
  }
  const total = getTotal();
  const subTotal = cart.reduce((s, x) => s + x.sale_price * x.qty, 0);
  const discountPct = parseFloat(document.getElementById('discountInp').value) || 0;
  const discountAmount = Math.round(subTotal * discountPct / 100);
  // Nasiyada kiritilmagan summa 0 (qoldiq qarzga yoziladi); naqd/kartada bo'sh summa = jami
  const enteredPaid = parseFloat(document.getElementById('payAmountInp').value);
  const paid = payMethod === 'debt' ? (enteredPaid || 0) : (enteredPaid || total);
  if (payMethod === 'cash' && paid < total) { toast('To\'lov yetarli emas', 'err'); return; }
  if (payMethod === 'debt' && paid >= total) { toast('Nasiya uchun qabul qilingan summa jami summadan kam bo\'lishi kerak', 'err'); return; }
  const dueDate = document.getElementById('debtDueInp')?.value || '';

  const payBtn = document.getElementById('payBtn');
  payBtn.disabled = true;
  try {
    // Payload must match SaleCreate schema exactly
    const payload = {
      items: cart.map(p => ({
        product_id: p.id,
        quantity: p.qty,
        // T3.19: unit_price faqat kassir narxni qo'lda o'zgartirgan bo'lsa yuboriladi; aks holda server
        // narxni hal qiladi (mijozning individual narxi > narx turi > sotuv narxi) va mijoz chegirmasini qo'llaydi
        ...(p.price_manual ? { unit_price: p.sale_price, price_manual: true } : {}),
        discount: 0,
      })),
      payment_type: payMethod,      // 'cash' | 'card' | 'debt'
      paid_amount: paid,            // required Decimal
      discount_amount: discountAmount,
      note: '',
      customer_id: customerId ? Number(customerId) : null,
      ...(payMethod === 'debt' && dueDate ? { debt_due_date: dueDate } : {}),
      ...(posWarehouseId ? { warehouse_id: Number(posWarehouseId) } : {}),
    };
    const cartSnapshot = [...cart];
    const result = await api('/sales/', {
      method: 'POST',
      headers: { 'Idempotency-Key': saleKeyFor(payload) },
      body: JSON.stringify(payload),
    });
    _saleKey = { sig: '', key: '' };
    toast('✅ Sotuv muvaffaqiyatli saqlandi!', 'ok');
    showReceipt(result || payload, total, paid, cartSnapshot);

    // Reset cart and form
    cart = [];
    document.getElementById('discountInp').value = '';
    document.getElementById('payAmountInp').value = '';
    const dueInp = document.getElementById('debtDueInp');
    if (dueInp) dueInp.value = '';
    clearCustomer();
    renderCart();
    await loadProducts();
    loadKassaStats();
  } catch (e) {
    toast(e.message, 'err');
  } finally {
    payBtn.disabled = false;
  }
}

// ─── RECEIPT ──────────────────────────────────
function showReceipt(sale, total, paid, cartItems) {
  const now = new Date();
  const change = Math.max(0, paid - total);
  const items = cartItems || cart;

  // Load receipt template settings from localStorage
  let receiptSettings = {};
  try {
    const stored = localStorage.getItem('erp_receipt_settings');
    if (stored) {
      receiptSettings = JSON.parse(stored);
    }
  } catch (e) {
    console.warn('Failed to load receipt settings:', e);
  }

  // Use template settings or defaults
  const cfg = (CFG.paperSize === '58mm' ? receiptSettings.r58 : CFG.paperSize === 'A4' ? receiptSettings.nak : receiptSettings.r80)
    || receiptSettings.r80 || receiptSettings.r58 || {};
  const branchInfo = (companyData && companyData.branch) || {};
  const company = cfg.company || sale.company_name || (companyData && companyData.name) || CFG.cassaName || 'ERPPos';
  // T3.7: sotuv filialining rekvizitlari (server javobi) birinchi o'rinda; shablon/joriy filial — zaxira
  const address = sale.branch_address || cfg.address || branchInfo.address || '';
  const phone = sale.branch_phone || cfg.phone || branchInfo.phone || '';
  const saleBranchName = sale.branch_name || '';
  const inn = cfg.inn || '';
  const header = cfg.header || '';
  const footer = cfg.footer || 'Xarid uchun rahmat!';
  const showCashier = cfg.show_cashier !== false;
  const showDate = cfg.show_date !== false;
  const logo = cfg.logo || '';
  const logoSize = Number(cfg.logo_size) || 40;

  let html = '';

  // Logo
  if (logo) {
    html += `<div class="receipt-center"><img src="${safeUrl(logo)}" alt="Logo" style="max-width:120px;height:${logoSize}px;object-fit:contain;margin:0 auto 8px"></div>`;
  }

  // Company Info
  if (company) {
    html += `<div class="receipt-center" style="font-weight:800;font-size:14px">${esc(company)}</div>`;
  }
  if (saleBranchName) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666">Filial: ${esc(saleBranchName)}</div>`;
  }
  if (address) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666">${esc(address)}</div>`;
  }
  if (phone) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666">Tel: ${esc(phone)}</div>`;
  }
  if (inn) {
    html += `<div class="receipt-center" style="font-size:10px;color:#999">STIR: ${esc(inn)}</div>`;
  }
  if (header) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666;font-style:italic;margin-top:4px">${esc(header)}</div>`;
  }

  html += `<hr class="receipt-sep">`;

  // Date/Time and Receipt Number
  if (showDate) {
    html += `<div class="receipt-row"><span>Sana:</span><span>${now.toLocaleDateString('uz-UZ')}</span></div>`;
    html += `<div class="receipt-row"><span>Vaqt:</span><span>${now.toLocaleTimeString('uz-UZ')}</span></div>`;
  }
  html += `<div class="receipt-row"><span>Chek #:</span><span>${esc(sale.number || '-')}</span></div>`;

  html += `<hr class="receipt-sep">`;

  // Items
  items.forEach(item => {
    const name = item.name || item.product_name || '-';
    const qty = item.qty || item.quantity || 1;
    const price = item.sale_price || item.unit_price || item.price || 0;
    html += `<div class="receipt-row"><span>${esc(name)}</span><span>${esc(qty)}×${fmt(price)}</span></div>`;
  });

  html += `<hr class="receipt-sep">`;

  // Totals
  html += `<div class="receipt-row" style="font-weight:700"><span>JAMI:</span><span>${fmt(total)} so'm</span></div>`;
  if (paid > 0) {
    html += `<div class="receipt-row"><span>To'lov:</span><span>${fmt(paid)} so'm</span></div>`;
  }
  if (change > 0) {
    html += `<div class="receipt-row"><span>Qaytim:</span><span>${fmt(change)} so'm</span></div>`;
  }

  // Cashier
  if (showCashier && currentUserName) {
    html += `<div class="receipt-center" style="font-size:10px;color:#999;margin-top:4px">Kassir: ${esc(currentUserName)}</div>`;
  }

  html += `<hr class="receipt-sep">`;

  // Footer
  if (footer) {
    html += `<div class="receipt-center" style="font-size:10px;color:#999">${esc(footer)}</div>`;
  }

  document.getElementById('receiptContent').innerHTML = html;
  openModal('receiptModal');
  if (CFG.autoPrint) setTimeout(printReceipt, 500);
}

function printReceipt() {
  window.print();
  toast('Printer ga yuborildi', 'info');
}

// ─── RETURN / QAYTARISH ───────────────────────
async function searchReturns(q) {
  if (!q) { document.getElementById('returnSaleList').innerHTML = '<div class="empty-state">Sotuv raqamini kiriting</div>'; return; }
  try {
    const data = await api(`/sales/?search=${encodeURIComponent(q)}&limit=10`);
    const list = Array.isArray(data) ? data : (data?.items || []);
    if (!list.length) { document.getElementById('returnSaleList').innerHTML = '<div class="empty-state">Sotuv topilmadi</div>'; return; }
    document.getElementById('returnSaleList').innerHTML = list.map(s => {
      // encodeURIComponent `'` ni kodlamaydi — onclick='...' dan chiqib ketmasin
      const safeS = encodeURIComponent(JSON.stringify(s)).replace(/'/g, '%27');
      return `
      <div class="kirim-row" onclick="selectReturnSaleEncoded('${safeS}')">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:700">#${esc(s.id)} — ${esc(s.number || '')} — ${esc(s.cashier_name || 'Kassir')}</div>
          <div style="font-size:11px;color:var(--ink3)">${new Date(s.created_at || s.date).toLocaleDateString('uz-UZ')} · ${fmt(s.total_amount || s.total)} so'm</div>
        </div>
        <span class="badge badge-blue">Tanlash →</span>
      </div>`;
    }).join('');
  } catch (e) { toast(e.message, 'err'); }
}

function selectReturnSaleEncoded(encoded) {
  selectReturnSale(JSON.parse(decodeURIComponent(encoded)));
}

function selectReturnSale(sale) {
  selectedReturnSale = sale;
  // Qatorlarda `id` va `returned_quantity` bo'lishi uchun har doim to'liq SaleOut olinadi
  api('/sales/' + sale.id).then(full => {
    selectedReturnSale = full;
    _renderReturnItems(full.items || []);
  }).catch(e => { toast(e.message, 'err'); _renderReturnItems([]); });
}

function _returnRemaining(item) {
  return Math.max(0, Number(item.quantity || 0) - Number(item.returned_quantity || 0));
}

function _renderReturnItems(items) {
  document.getElementById('returnItemsList').innerHTML = items.length
    ? items.map((item, i) => {
      const left = _returnRemaining(item);
      const done = Number(item.returned_quantity || 0);
      return `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);${left <= 0 ? 'opacity:.5' : ''}">
        <div>
          <div style="font-size:13px;font-weight:600">${esc(item.product_name || item.name || '#' + item.product_id)}</div>
          <div style="font-size:11px;color:var(--ink3)">${esc(item.quantity)} dona × ${fmt(item.unit_price || item.price)} so'm${done > 0 ? ' · qaytarilgan: ' + esc(done) : ''}</div>
        </div>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600">
          Qaytarish
          <input type="number" class="ret-qty" data-idx="${i}" min="0" max="${esc(left)}" step="any" value="${esc(left)}" ${left <= 0 ? 'disabled' : ''}
            style="width:70px;padding:4px 6px;border:1.5px solid var(--border2);border-radius:var(--r-xs);font-family:var(--mono);text-align:center;outline:none">
        </label>
      </div>`;
    }).join('')
    : '<div class="empty-state">Mahsulotlar topilmadi</div>';
  document.getElementById('processReturnBtn').disabled = !items.some(it => _returnRemaining(it) > 0);
  toast('Sotuv tanlandi. Qaytariladigan miqdorni kiriting.', 'info');
}

async function processReturn() {
  if (!selectedReturnSale) { toast('Sotuv tanlanmagan', 'warn'); return; }
  const items = selectedReturnSale.items || [];
  const returnItems = [];
  for (const inp of document.querySelectorAll('#returnItemsList input.ret-qty:not(:disabled)')) {
    const item = items[parseInt(inp.dataset.idx)];
    const qty = parseFloat(inp.value) || 0;
    if (!item || qty <= 0) continue;
    if (qty > _returnRemaining(item) + 1e-9) {
      toast('Qaytariladigan miqdor qolgan miqdordan oshmasligi kerak', 'err');
      return;
    }
    returnItems.push({ sale_item_id: item.id, quantity: qty });
  }
  if (!returnItems.length) { toast('Qaytariladigan mahsulot tanlanmagan', 'warn'); return; }
  // Pul asl sotuv to'lov turida qaytariladi (nasiya sotuv qarzdan, boshqa aralash turlar naqd)
  const origType = selectedReturnSale.payment_type;
  const payment_type = ['cash', 'card', 'debt'].includes(origType) ? origType : 'cash';
  try {
    await api('/sales/' + selectedReturnSale.id + '/return-items', {
      method: 'POST',
      body: JSON.stringify({ items: returnItems, payment_type, note: 'Qaytarish' }),
    });
    toast('✅ Qaytarish muvaffaqiyatli amalga oshirildi', 'ok');
    selectedReturnSale = null;
    document.getElementById('returnItemsList').innerHTML = '<div class="empty-state">Sotuvni tanlang</div>';
    document.getElementById('returnSaleList').innerHTML = '<div class="empty-state">Sotuv raqamini kiriting</div>';
    document.getElementById('returnSearchInp').value = '';
    document.getElementById('processReturnBtn').disabled = true;
    await loadProducts();
    loadKassaStats();
  } catch (e) { toast(e.message, 'err'); }
}

// ─── KIRIM ────────────────────────────────────
function openKirimForm() {
  kirimItems = [];
  document.getElementById('kirimDate').value = new Date().toISOString().split('T')[0];
  document.getElementById('kirimDocNum').value = 'INV-' + Math.floor(Math.random() * 9000 + 1000);
  document.getElementById('kirimProdSearch').value = '';
  document.getElementById('kirimProdResults').innerHTML = '';
  document.getElementById('kirimNote').value = '';
  renderKirimItems();
  openModal('kirimModal');
}

function kirimSearchProd(q) {
  const el = document.getElementById('kirimProdResults');
  if (!q) { el.innerHTML = ''; return; }
  // sell tipli (tarkibiy) mahsulotlarni kirimdan chiqarib tashlash
  const list = allProducts
    .filter(p => p.product_type !== 'sell')
    .filter(p => p.name.toLowerCase().includes(q.toLowerCase()) || (p.sku || '').toLowerCase().includes(q.toLowerCase()))
    .slice(0, 10);
  el.innerHTML = list.map(p => `
    <div class="prod-result-item" data-prod-id="${esc(p.id)}" onclick="addKirimItemById(${Number(p.id)})">
      <div><div class="pri-name">${esc(p.name)}</div><div class="pri-sku">${esc(p.sku || '')}</div></div>
      <div class="pri-price">${fmt(p.cost_price)} so'm</div>
    </div>`).join('') || '<div class="empty-state" style="padding:16px">Topilmadi</div>';
}

function addKirimItemById(id) {
  const prod = allProducts.find(p => p.id === id);
  if (!prod) return;
  if (prod.product_type === 'sell') {
    toast('⚠️ Tarkibiy mahsulotga kirim qilib bo\'lmaydi!', 'err');
    return;
  }
  addKirimItem(prod);
}

function addKirimItem(prod) {
  const existing = kirimItems.find(x => x.id === prod.id);
  if (existing) existing.qty++;
  else kirimItems.push({ ...prod, qty: 1, cost: prod.cost_price });
  renderKirimItems();
  document.getElementById('kirimProdSearch').value = '';
  document.getElementById('kirimProdResults').innerHTML = '';
}

function renderKirimItems() {
  const el = document.getElementById('kirimItems');
  if (!kirimItems.length) { el.innerHTML = '<div class="empty-state" style="padding:20px">Mahsulot qo\'shilmagan</div>'; return; }
  el.innerHTML = `<table class="pos-table">
    <thead><tr><th>Mahsulot</th><th class="r">Miqdor</th><th class="r">Narx</th><th class="c">O'chirish</th></tr></thead>
    <tbody>
      ${kirimItems.map((item, i) => `
        <tr>
          <td style="font-size:13px;font-weight:600">${esc(item.name)}</td>
          <td class="r"><input type="number" min="1" value="${esc(item.qty)}" style="width:60px;padding:4px 6px;border:1.5px solid var(--border2);border-radius:var(--r-xs);font-family:var(--mono);text-align:center;outline:none" onchange="kirimQty(${i},this.value)"></td>
          <td class="r"><input type="number" min="0" value="${esc(item.cost)}" style="width:90px;padding:4px 6px;border:1.5px solid var(--border2);border-radius:var(--r-xs);font-family:var(--mono);text-align:right;outline:none" onchange="kirimCost(${i},this.value)"></td>
          <td class="c"><button onclick="removeKirimItem(${i})" style="background:none;border:none;cursor:pointer;color:var(--red);font-size:16px">✕</button></td>
        </tr>`).join('')}
    </tbody>
  </table>`;
}

function kirimQty(i, v) { kirimItems[i].qty = Math.max(1, parseInt(v) || 1); }
function kirimCost(i, v) { kirimItems[i].cost = parseFloat(v) || 0; }
function removeKirimItem(i) { kirimItems.splice(i, 1); renderKirimItems(); }

async function saveKirim() {
  if (!kirimItems.length) { toast('Mahsulot qo\'shilmagan', 'warn'); return; }
  const whId = document.getElementById('kirimWarehouse').value;
  if (!whId) { toast('Omborni tanlang', 'warn'); return; }
  const supId = document.getElementById('kirimSupplier').value;
  try {
    const payload = {
      supplier_id: supId ? parseInt(supId) : null,
      warehouse_id: parseInt(whId),
      document_number: document.getElementById('kirimDocNum').value,
      note: document.getElementById('kirimNote').value,
      items: kirimItems.map(i => ({ product_id: i.id, quantity: i.qty, cost_price: i.cost })),
    };
    await api('/inventory/receive', { method: 'POST', body: JSON.stringify(payload) });
    toast('✅ Kirim muvaffaqiyatli saqlandi!', 'ok');
    closeModal('kirimModal');
    kirimItems = [];
    await Promise.all([loadProducts(), loadKirimList()]);
  } catch (e) { toast(e.message, 'err'); }
}

async function loadKirimList() {
  const el = document.getElementById('kirimList');
  if (!el) return;
  // Endpoint kassirga yopiq (403) — kassir rolida so'rov yuborilmaydi
  if (!canSeeKirim()) return;
  try {
    // MovementType katta harfda (IN); faqat xaridga bog'liq kirimlar (reference_type=purchase)
    const data = await api('/inventory/movements?type=IN&reference_type=purchase&limit=30');
    const list = Array.isArray(data) ? data : (data?.items || []);
    if (!list.length) { el.innerHTML = '<div class="empty-state" style="padding:40px">Kirimlar topilmadi</div>'; return; }
    el.innerHTML = list.map(m => `
      <div class="kirim-row">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:700">${esc(m.reference_type === 'purchase' ? 'Kirim #' + m.reference_id : (m.reason || 'Kirim'))} — ${esc(m.product_name || 'Mahsulot #' + m.product_id)}</div>
          <div style="font-size:11px;color:var(--ink3)">${new Date(m.created_at || m.date).toLocaleDateString('uz-UZ')}</div>
        </div>
        <div style="text-align:right">
          <div style="font-family:var(--mono);font-weight:700;color:var(--green)">+${esc(m.quantity)} dona</div>
          <div style="font-size:11px;color:var(--ink3)">Qoldiq: ${esc(m.qty_after || '—')}</div>
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state" style="padding:40px">⚠️ ${esc(e.message)}</div>`;
  }
}

// ─── PRODUCTS TABLE ───────────────────────────
function renderProductsTable(list) {
  const el = document.getElementById('productsTbody');
  if (!el) return;
  el.innerHTML = list.map(p => {
    const qty = Number(p.stock_quantity || 0);
    const cls = qty <= 0 ? 'badge badge-red' : qty <= (p.min_stock || 5) ? 'badge badge-amber' : 'badge badge-green';
    const label = qty <= 0 ? 'Tugagan' : qty <= (p.min_stock || 5) ? 'Kam' : 'Yetarli';
    return `<tr>
      <td><span style="font-family:var(--mono);font-size:11px">${esc(p.sku || '-')}</span></td>
      <td style="font-weight:600">${esc(p.name)}</td>
      <td style="color:var(--ink3)">${esc(p.category_name || '-')}</td>
      <td class="r">${fmt(p.cost_price)} so'm</td>
      <td class="r" style="font-weight:700;color:var(--blue)">${fmt(p.sale_price)} so'm</td>
      <td class="r" style="font-weight:700;color:${qty <= 0 ? 'var(--red)' : qty <= 5 ? 'var(--amber)' : 'var(--ink)'}">${fmt(qty)}</td>
      <td class="c"><span class="${cls}">${label}</span></td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="empty-row">Mahsulotlar topilmadi</td></tr>';
}

function searchProducts(q) {
  if (!q) { renderProductsTable(allProducts); return; }
  const lq = q.toLowerCase();
  renderProductsTable(allProducts.filter(p => p.name.toLowerCase().includes(lq) || (p.sku || '').toLowerCase().includes(lq)));
}

// ─── FAVORITES ────────────────────────────────
function openAddFavorite() {
  document.getElementById('favSearchInp').value = '';
  document.getElementById('favSearchResults').innerHTML = '<div class="empty-state" style="padding:30px">Qidirish uchun mahsulot nomini yozing</div>';
  openModal('favModal');
}

function favSearch(q) {
  if (!q) { document.getElementById('favSearchResults').innerHTML = '<div class="empty-state" style="padding:30px">Qidirish uchun mahsulot nomini yozing</div>'; return; }
  const lq = q.toLowerCase();
  const list = allProducts.filter(p => p.name.toLowerCase().includes(lq) || (p.sku || '').includes(q)).slice(0, 15);
  document.getElementById('favSearchResults').innerHTML = list.map(p => `
    <div class="prod-result-item" onclick="addFavoriteById(${Number(p.id)})">
      <div><div class="pri-name">${esc(p.name)}</div><div class="pri-sku">${esc(p.sku || '')}</div></div>
      <div style="display:flex;align-items:center;gap:8px">
        <div class="pri-price">${fmt(p.sale_price)} so'm</div>
        <button style="background:var(--green);color:#fff;border:none;border-radius:var(--r-xs);padding:4px 10px;font-size:12px;cursor:pointer">Qo'shish</button>
      </div>
    </div>`).join('') || '<div class="empty-state" style="padding:20px">Topilmadi</div>';
}

function addFavoriteById(id) {
  const prod = allProducts.find(p => p.id === id);
  if (prod) addFavorite(prod);
}

function addFavorite(prod) {
  if (favorites.find(f => f.id === prod.id)) { toast('Allaqachon qo\'shilgan', 'warn'); return; }
  favorites.push(prod);
  localStorage.setItem('pos_favorites', JSON.stringify(favorites));
  renderFavorites();
  toast(prod.name + ' sevimlilar ga qo\'shildi ⭐', 'ok');
}

function removeFavorite(id) {
  favorites = favorites.filter(f => f.id !== id);
  localStorage.setItem('pos_favorites', JSON.stringify(favorites));
  renderFavorites();
}

function renderFavorites() {
  const el = document.getElementById('favGrid');
  if (!el) return;
  if (!favorites.length) {
    el.innerHTML = '<div class="empty-state" style="grid-column:1/-1;padding:50px;">Sevimlilar yo\'q. "+ Sevimli qo\'shish" tugmasini bosing.</div>';
    return;
  }
  el.innerHTML = favorites.map(p => {
    const live = allProducts.find(x => x.id === p.id) || p;
    const qty = Number(live.stock_quantity || 0);
    const imgSrc = prodImgSrc(live.image_url);
    const img = imgSrc
      ? `<img src="${imgSrc}" alt="">`
      : `<span style="font-size:28px">📦</span>`;
    const outOfStock = qty <= 0;
    const colorCls = qty <= 0 ? 'color:var(--red)' : qty <= (live.min_stock || 5) ? 'color:var(--amber)' : '';
    return `<div class="prod-card${outOfStock ? ' out-of-stock' : ''}" style="position:relative" onclick="addToCartById(${Number(p.id)});switchTab('sale')">
      <button onclick="event.stopPropagation();removeFavorite(${Number(p.id)})" title="Sevimlilardan o'chirish" style="position:absolute;top:6px;right:6px;background:rgba(255,255,255,0.9);border:none;border-radius:50%;width:22px;height:22px;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;z-index:2">✕</button>
      <div class="prod-card-img">${img}</div>
      <div class="prod-card-name">${esc(live.name)}</div>
      <div class="prod-card-price">${fmt(live.sale_price)} so'm</div>
      <div class="prod-card-stock" style="${colorCls}">Qoldiq: ${fmt(qty)} ${esc(live.unit || 'dona')}</div>
    </div>`;
  }).join('');
}

// ─── KASSA STATS ──────────────────────────────
// To'lov turlari: "Karta" jamiga kiradiganlari (balances kalitlari)
const CARD_PAY_TYPES = ['card', 'uzcard', 'humo', 'visa', 'click', 'payme', 'uzum', 'bank'];

function _sumUzs(map, types) {
  return types.reduce((acc, t) => acc + Number((map && map[t] && map[t].UZS) || 0), 0);
}

async function loadKassaStats() {
  try {
    // Jamlar joriy smenadan (qaytarishlar ayirilgan, 100 tadan ko'p sotuvda ham to'g'ri); smena yo'q bo'lsa nol
    let shift = null;
    try { shift = await api('/shifts/current'); } catch (_) { shift = null; }
    let naqdTotal = 0, cardTotal = 0, returnTotal = 0, salesCount = 0;
    if (shift && shift.id) {
      const bal = shift.balances || {};
      naqdTotal = _sumUzs(bal, ['cash']);
      cardTotal = _sumUzs(bal, CARD_PAY_TYPES);
      try {
        const z = await api('/shifts/' + shift.id + '/z-report');
        salesCount = Number(z?.sales?.count || 0);
        returnTotal = _sumUzs(z?.returns?.by_payment, Object.keys(z?.returns?.by_payment || {}));
      } catch (_) { /* z-hisobot ko'rinmasa — faqat jamlar */ }
    }
    document.getElementById('kassaNaqdTotal').textContent = fmt(naqdTotal) + ' so\'m';
    document.getElementById('kassaCardTotal').textContent = fmt(cardTotal) + ' so\'m';
    document.getElementById('kassaSalesCount').textContent = salesCount + ' ta';
    document.getElementById('kassaReturnTotal').textContent = fmt(returnTotal) + ' so\'m';

    // "Bugungi sotuvlar" jadvali (oxirgi 100 ta); jamlar bundan hisoblanmaydi
    const data = await api('/sales/?limit=100&date_today=true').catch(() => api('/sales/?limit=100'));
    const sales = Array.isArray(data) ? data : (data?.items || []);
    document.getElementById('kassaSalesTbody').innerHTML = sales.slice(0, 30).map(s => `
      <tr>
        <td>${new Date(s.created_at || s.date).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })}</td>
        <td>${esc(s.cashier_name || '—')}</td>
        <td class="r" style="font-weight:700;font-family:var(--mono)">${fmt(s.total_amount || s.total)} so'm</td>
        <td><span class="badge ${s.payment_type === 'cash' ? 'badge-green' : 'badge-blue'}">${s.payment_type === 'cash' ? 'Naqd' : s.payment_type === 'card' ? 'Karta' : s.payment_type === 'debt' ? 'Nasiya' : esc(s.payment_type)}</span></td>
        <td class="c"><button onclick="reprint(${Number(s.id)})" style="background:none;border:1.5px solid var(--border2);border-radius:var(--r-xs);padding:3px 8px;cursor:pointer;font-size:12px;color:var(--ink2)">🖨</button></td>
      </tr>`).join('') || '<tr><td colspan="5" class="empty-row">Bugun sotuv yo\'q</td></tr>';
  } catch (e) { console.log('Kassa stats error:', e.message); }
}

// Chekni qayta chop etish: GET /sales/{id} dan chek yig'ib showReceipt ga beriladi
async function reprint(id) {
  try {
    const sale = await api('/sales/' + Number(id));
    const items = (sale.items || []).map(it => ({
      name: it.product_name || it.name,
      qty: it.quantity,
      sale_price: it.unit_price,
    }));
    showReceipt(sale, Number(sale.total_amount || 0), Number(sale.paid_amount || 0), items);
  } catch (e) { toast(e.message, 'err'); }
}

// ─── SMENA ────────────────────────────────────
async function checkSmena() {
  try {
    const data = await api('/shifts/current');
    if (data && data.id) {
      activeSmena = data;
      document.getElementById('smDot').className = 'sm-dot open';
      document.getElementById('smenaLabel').textContent = 'Smena ochiq';
      document.getElementById('smenaBtn').textContent = '🔐 Smenani yopish';
    } else {
      activeSmena = null;
      document.getElementById('smDot').className = 'sm-dot';
      document.getElementById('smenaLabel').textContent = 'Smena yo\'q';
      document.getElementById('smenaBtn').textContent = '⟳ Smena ochish';
    }
  } catch (e) {
    activeSmena = null;
  }
}

function handleSmenaClick() {
  if (!activeSmena) openSmenaModal('open');
  else openSmenaModal('close');
}

function showSmenaInfo() {
  if (!activeSmena) { handleSmenaClick(); return; }
  openSmenaModal('info');
}

function openSmenaModal(mode) {
  const body = document.getElementById('smenaModalBody');
  const actions = document.getElementById('smenaModalActions');
  const title = document.getElementById('smenaModalTitle');
  if (mode === 'open') {
    title.textContent = '🔓 Smenani Ochish';
    body.innerHTML = `
      <div style="font-size:13px;color:var(--ink2)">Yangi smena ochish uchun tasdiqlang.</div>
      <div style="padding:12px;background:var(--blue-bg);border:1.5px solid var(--blue-border);border-radius:var(--r-sm)">
        <div style="font-size:12px;font-weight:600;color:var(--blue)">Smena ochiladi</div>
        <div style="font-size:13px;color:var(--ink2);margin-top:4px">${new Date().toLocaleDateString('uz-UZ')} ${new Date().toLocaleTimeString('uz-UZ')}</div>
      </div>
    `;
    actions.innerHTML = `
      <button class="btn-outline" onclick="closeModal('smenaModal')">Bekor</button>
      <button class="btn-blue" onclick="openSmena()">✓ Smenani Ochish</button>
    `;
  } else if (mode === 'close') {
    title.textContent = '🔐 Smenani Yopish';
    body.innerHTML = `
      <div style="font-size:13px;color:var(--ink2)">Smenani yopish uchun tasdiqlang.</div>
      <div style="padding:12px;background:var(--green-bg);border:1.5px solid var(--green-border);border-radius:var(--r-sm)">
        <div style="font-size:12px;font-weight:600;color:var(--green)">Joriy smena</div>
        <div style="font-size:13px;color:var(--ink2);margin-top:4px">Boshlangan: ${activeSmena?.opened_at ? new Date(activeSmena.opened_at).toLocaleTimeString('uz-UZ') : '—'}</div>
      </div>
    `;
    actions.innerHTML = `
      <button class="btn-outline" onclick="closeModal('smenaModal')">Bekor</button>
      <button class="btn-blue" style="background:var(--red);border-color:var(--red)" onclick="closeSmena()">✓ Smenani Yopish</button>
    `;
  } else if (mode === 'info') {
    title.textContent = 'ℹ️ Smena Ma\'lumoti';
    body.innerHTML = `
      <div style="padding:12px;background:var(--green-bg);border:1.5px solid var(--green-border);border-radius:var(--r-sm)">
        <div style="font-size:12px;font-weight:600;color:var(--green)">Smena OCHIQ</div>
        <div style="font-size:13px;color:var(--ink2);margin-top:4px">Boshlangan: ${activeSmena?.opened_at ? new Date(activeSmena.opened_at).toLocaleTimeString('uz-UZ') : '—'}</div>
        <div style="font-size:13px;color:var(--ink2)">Kassir ID: ${esc(activeSmena?.cashier_id || '—')}</div>
      </div>
    `;
    actions.innerHTML = `
      <button class="btn-outline" onclick="closeModal('smenaModal')">Yopish</button>
      <button class="btn-blue" style="background:var(--red);border-color:var(--red)" onclick="closeSmena()">🔐 Smenani yopish</button>
    `;
  }
  openModal('smenaModal');
}

async function openSmena() {
  try {
    const data = await api('/shifts/open', { method: 'POST', body: JSON.stringify({ note: '' }) });
    activeSmena = data;
    document.getElementById('smDot').className = 'sm-dot open';
    document.getElementById('smenaLabel').textContent = 'Smena ochiq';
    document.getElementById('smenaBtn').textContent = '🔐 Smenani yopish';
    toast('✅ Smena ochildi', 'ok');
    closeModal('smenaModal');
  } catch (e) {
    toast(e.message, 'err');
  }
}

async function closeSmena() {
  try {
    await api('/shifts/close', { method: 'POST', body: JSON.stringify({}) });
    activeSmena = null;
    document.getElementById('smDot').className = 'sm-dot';
    document.getElementById('smenaLabel').textContent = 'Smena yo\'q';
    document.getElementById('smenaBtn').textContent = '⟳ Smena ochish';
    toast('✅ Smena yopildi', 'ok');
    closeModal('smenaModal');
  } catch (e) { toast(e.message, 'err'); }
}

// ─── SETTINGS ─────────────────────────────────
function applySettings() {
  Object.entries(settingsToggles).forEach(([k, v]) => {
    const el = document.getElementById('tog-' + k);
    if (el) el.classList.toggle('on', v);
  });
  const ps = document.getElementById('settPrinter');
  if (ps) ps.value = CFG.printer;
  const pp = document.getElementById('settPaperSize');
  if (pp) pp.value = CFG.paperSize;
  const cn = document.getElementById('settCassaName');
  if (cn) cn.value = CFG.cassaName;
  const au = document.getElementById('settApiUrl');
  if (au) au.value = CFG.apiUrl;
  const fid = document.getElementById('settFactoryId');
  if (fid) fid.value = CFG.fiskalId;
  checkApiStatus();
}

function toggleSetting(key) {
  settingsToggles[key] = !settingsToggles[key];
  const el = document.getElementById('tog-' + key);
  if (el) el.classList.toggle('on', settingsToggles[key]);
}

function saveSettings() {
  CFG.autoPrint = settingsToggles.autoPrint;
  CFG.unknownProd = settingsToggles.unknownProd;
  // Fiskal: yoqilsa Hippo Factory ID majburiy (POST /sales/ va smena yopishda X-Hippo-Factory-Id ketadi)
  CFG.fiskalId = (document.getElementById('settFactoryId')?.value || '').trim();
  if (settingsToggles.fiscal && !CFG.fiskalId) {
    toast('Fiskalizatsiya uchun Hippo Factory ID kiriting (fiskal o\'chirib qo\'yildi)', 'warn');
    settingsToggles.fiscal = false;
    document.getElementById('tog-fiscal')?.classList.remove('on');
  }
  CFG.fiscal = settingsToggles.fiscal;
  CFG.discount = settingsToggles.discount;
  CFG.credit = settingsToggles.credit;
  CFG.requireCustomer = settingsToggles.requireCustomer;
  CFG.printer = document.getElementById('settPrinter')?.value || '';
  CFG.paperSize = document.getElementById('settPaperSize')?.value || '80mm';
  CFG.cassaName = document.getElementById('settCassaName')?.value || 'Kassa #1';
  CFG.apiUrl = document.getElementById('settApiUrl')?.value || 'http://localhost:8000';
  Object.entries(CFG).forEach(([k, v]) => {
    if (k === 'fiscal') return;   // pos_fiskalSend kaliti ostida saqlanadi
    localStorage.setItem('pos_' + k, typeof v === 'boolean' ? (v ? '1' : '0') : v);
  });
  localStorage.setItem('pos_fiskalSend', CFG.fiscal ? '1' : '0');
  renderCompanyHeader();
  toast('✅ Sozlamalar saqlandi', 'ok');
  checkApiStatus();
}

// ─── PAY SYSTEMS ──────────────────────────────
// T3.18: serverdagi (kassir filiali uchun) faol to'lov terminallari
const PAY_PROVIDERS = ['payme', 'click', 'uzum', 'uzcard', 'humo'];
function canManagePaySystems() {
  return !!currentUser && ['super_admin', 'admin', 'director'].includes(String(currentUser.role || ''));
}
async function loadPaySystems() {
  try {
    const rows = await api('/payment-terminals/mine');
    paySystems = (Array.isArray(rows) ? rows : []).map(r => ({
      id: r.id,
      name: r.label || r.merchant_id || ('#' + r.id),
      type: r.provider,
      terminal: r.terminal_id || r.merchant_id || '',
      active: r.is_active !== false,
    }));
  } catch (e) { paySystems = []; }
  renderPaySystems();
}
function openAddPaySystem() {
  if (!canManagePaySystems()) { toast('Terminal qo\'shish faqat admin/direktor uchun (ERP → Sozlamalar)', 'warn'); return; }
  openModal('paySystemModal');
}
async function savePaySystem() {
  const name = document.getElementById('psName').value;
  if (!name) { toast('Nomi kiriting', 'warn'); return; }
  const type = document.getElementById('psType').value;
  if (!PAY_PROVIDERS.includes(type)) { toast('Terminal faqat Payme/Click/Uzum/UzCard/Humo uchun', 'warn'); return; }
  try {
    await api('/payment-terminals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: type, label: name, terminal_id: document.getElementById('psTerminal').value || null }),
    });
  } catch (e) { toast(e.message || 'Xatolik', 'err'); return; }
  await loadPaySystems();
  closeModal('paySystemModal');
  toast('✅ To\'lov tizimi qo\'shildi', 'ok');
}

function renderPaySystems() {
  const el = document.getElementById('paySystemsTbody');
  if (!el) return;
  if (!paySystems.length) { el.innerHTML = '<tr><td colspan="5" class="empty-row">To\'lov tizimlari topilmadi</td></tr>'; return; }
  el.innerHTML = paySystems.map((p, i) => `
    <tr>
      <td style="font-weight:600">${esc(p.name)}</td>
      <td><span class="badge badge-blue">${esc(p.type)}</span></td>
      <td style="font-family:var(--mono);font-size:12px">${esc(p.terminal || '—')}</td>
      <td class="c"><span class="badge badge-green">Faol</span></td>
      <td class="c"><button onclick="removePaySystem(${i})" style="color:var(--red);background:none;border:none;cursor:pointer;font-size:16px">✕</button></td>
    </tr>`).join('');
}

async function removePaySystem(i) {
  const p = paySystems[i];
  if (!p) return;
  if (!canManagePaySystems()) { toast('Terminalni o\'chirish faqat admin/direktor uchun', 'warn'); return; }
  try { await api('/payment-terminals/' + p.id, { method: 'DELETE' }); }
  catch (e) { toast(e.message || 'Xatolik', 'err'); return; }
  await loadPaySystems();
}

// ─── MODAL HELPERS ────────────────────────────
function openModal(id) {
  document.getElementById('overlay').classList.add('show');
  document.getElementById(id).classList.add('show');
}
function closeModal(id) {
  document.getElementById('overlay').classList.remove('show');
  document.getElementById(id).classList.remove('show');
}
function closeOverlay() {
  document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
  document.getElementById('overlay').classList.remove('show');
}

// ─── TOAST ────────────────────────────────────
function toast(msg, type = 'ok') {
  const tz = document.getElementById('toastZone');
  const el = document.createElement('div');
  const cls = { ok: 'tok', err: 'terr', warn: 'twarn', info: 'tinfo' }[type] || 'tok';
  el.className = 'toast ' + cls;
  el.textContent = msg;
  tz.appendChild(el);
  setTimeout(() => { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 320); }, 3200);
}

// ─── FORMAT ───────────────────────────────────
function fmt(n) { return Math.round(n || 0).toLocaleString('ru-RU'); }

// ─── START ────────────────────────────────────
init();
