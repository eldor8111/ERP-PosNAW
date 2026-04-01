// ═══════════════════════════════════════════════
// ERPPos Desktop POS — Renderer Logic (Fixed)
// ═══════════════════════════════════════════════
// Support both Electron and Chrome browser
let ipcRenderer = null;
try {
  if (typeof require !== 'undefined') {
    ipcRenderer = require('electron').ipcRenderer;
  }
} catch(e) { /* running in browser — that's fine */ }

// ─── Config ───────────────────────────────────
let CFG = {
  apiUrl: localStorage.getItem('pos_apiUrl') || 'http://localhost:8000',
  autoPrint: localStorage.getItem('pos_autoPrint') === '1',
  unknownProd: localStorage.getItem('pos_unknownProd') === '1',
  fiscal: false,
  discount: localStorage.getItem('pos_discount') !== '0',
  credit: localStorage.getItem('pos_credit') === '1',
  requireCustomer: localStorage.getItem('pos_requireCustomer') === '1',
  printer: localStorage.getItem('pos_printer') || '',
  paperSize: localStorage.getItem('pos_paperSize') || '80mm',
  cassaName: localStorage.getItem('pos_cassaName') || 'Kassa #1',
};

let API_TOKEN = localStorage.getItem('pos_token') || '';
let AUTH_HEADERS = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_TOKEN}` };

// ─── State ────────────────────────────────────
let allProducts = [];
let categories = [];
let customers = [];
let warehouses = [];
let suppliers = [];
let favorites = JSON.parse(localStorage.getItem('pos_favorites') || '[]');
let paySystems = JSON.parse(localStorage.getItem('pos_paySystems') || '[]');
let settingsToggles = { autoPrint: CFG.autoPrint, unknownProd: CFG.unknownProd, fiscal: CFG.fiscal, discount: CFG.discount, credit: CFG.credit, requireCustomer: CFG.requireCustomer };
let cart = [];
let payMethod = 'cash';
let activeSmena = null;
let selectedReturnSale = null;
let kirimItems = [];
let currentUserName = '';
let companyData = null;

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
async function api(path, opts = {}) {
  const base = (document.getElementById('settApiUrl')?.value || CFG.apiUrl).replace(/\/$/, '');
  const url = base + '/api' + path;
  try {
    const res = await fetch(url, {
      ...opts,
      headers: { ...AUTH_HEADERS, ...(opts.headers || {}) },
    });
    if (res.status === 401) {
      localStorage.removeItem('pos_token');
      API_TOKEN = '';
      openLoginModal();
      throw new Error('Sessiya tugadi. Qaytadan kiring.');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Server xatosi' }));
      throw new Error(err.detail || res.statusText);
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
  const phone = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errEl = document.getElementById('loginError');
  const btn = document.getElementById('loginBtn');

  if (!phone || !password) { errEl.textContent = 'Telefon va parol kiriting'; return; }

  btn.disabled = true;
  btn.textContent = 'Kirilmoqda...';
  errEl.textContent = '';

  try {
    const base = (document.getElementById('settApiUrl')?.value || CFG.apiUrl).replace(/\/$/, '');

    const res = await fetch(base + '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Noto\'g\'ri telefon yoki parol' }));
      throw new Error(err.detail || 'Noto\'g\'ri telefon yoki parol');
    }

    const data = await res.json();
    API_TOKEN = data.access_token;
    localStorage.setItem('pos_token', API_TOKEN);
    AUTH_HEADERS = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_TOKEN}` };

    closeLoginModal();
    toast('✅ Muvaffaqiyatli kirildi!', 'ok');
    loadAllData();
  } catch (e) {
    errEl.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Kirish';
  }
}

function handleLoginKeydown(e) {
  if (e.key === 'Enter') doLogin();
}

function doLogout() {
  localStorage.removeItem('pos_token');
  API_TOKEN = '';
  AUTH_HEADERS = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' };
  activeSmena = null;
  cart = [];
  openLoginModal();
  closeDotMenu();
}

// ─── Load Data ────────────────────────────────
async function loadAllData() {
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
    loadCurrentUser(),
  ]);
}

async function loadProducts() {
  try {
    const data = await api('/products/?limit=200');
    allProducts = Array.isArray(data) ? data : (data?.items || []);
    renderSaleGrid(allProducts);
    renderProductsTable(allProducts);
    populateCatFilter();
    toast('Mahsulotlar yuklandi ✓', 'ok');
  } catch (e) {
    document.getElementById('saleGrid').innerHTML = `<div class="empty-state">⚠️ ${e.message}</div>`;
    toast(e.message, 'err');
  }
}

async function loadCategories() {
  try {
    const data = await api('/categories/all');
    categories = Array.isArray(data) ? data : [];
  } catch (e) { categories = []; }
}

async function loadCustomers() {
  try {
    const data = await api('/customers/?limit=200');
    customers = Array.isArray(data) ? data : (data?.items || []);
    const sel = document.getElementById('saleCustomer');
    if (sel) {
      sel.innerHTML = '<option value="">👤 Mijoz (ixtiyoriy)</option>'
        + customers.map(c => `<option value="${c.id}">${c.name}${c.phone ? ' | ' + c.phone : ''}</option>`).join('');
    }
  } catch (e) { customers = []; }
}

async function loadWarehouses() {
  try {
    const data = await api('/inventory/warehouses');
    warehouses = Array.isArray(data) ? data : [];
    const sel = document.getElementById('kirimWarehouse');
    if (sel) sel.innerHTML = '<option value="">— Tanlang —</option>'
      + warehouses.map(w => `<option value="${w.id}">${w.name}</option>`).join('');
  } catch (e) { warehouses = []; }
}

async function loadSuppliers() {
  try {
    const data = await api('/suppliers/?limit=100');
    suppliers = Array.isArray(data) ? data : (data?.items || []);
    const sel = document.getElementById('kirimSupplier');
    if (sel) sel.innerHTML = '<option value="">— Tanlang —</option>'
      + suppliers.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
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
      currentUserName = user.name || user.username || user.phone || 'Kassir';
    }
  } catch (e) {
    console.log('User info load error:', e.message);
  }
}

async function loadCompanyInfo() {
  try {
    // Kompaniya va filial ma'lumotlarini olish
    const user = await api('/auth/me');
    if (user && user.company_id) {
      const company = await api(`/companies/${user.company_id}`);
      companyData = company;

      // Kompaniya ma'lumotlarini ko'rsatish
      const companyInfoEl = document.getElementById('companyInfo');
      const companyNameEl = document.getElementById('companyName');
      const companyCodeEl = document.getElementById('companyCode');
      const companyBalanceEl = document.getElementById('companyBalance');

      if (companyInfoEl && company) {
        companyInfoEl.style.display = 'flex';
        companyNameEl.textContent = company.name || 'Korxona';
        companyCodeEl.textContent = company.code || company.tin || '-';

        // Balansni olish
        if (user.branch_id) {
          try {
            const branch = await api(`/branches/${user.branch_id}`);
            if (branch && branch.balance !== undefined) {
              companyBalanceEl.textContent = fmt(branch.balance) + ' so\'m';
              companyBalanceEl.style.color = branch.balance >= 0 ? 'var(--green)' : 'var(--red)';
            }
          } catch (e) {
            companyBalanceEl.textContent = '0 so\'m';
          }
        } else {
          companyBalanceEl.textContent = '0 so\'m';
        }
      }
    }
  } catch (e) {
    console.log('Company info load error:', e.message);
  }
}

// ─── Tab Switch ───────────────────────────────
function switchTab(tab) {
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
  if (ipcRenderer) ipcRenderer.send('win-' + cmd);
  else if (cmd === 'close' && confirm('Dasturdan chiqishni istaysizmi?')) window.close();
}

// ─── SALE: Product Grid ───────────────────────
function populateCatFilter() {
  const sel = document.getElementById('saleCatFilter');
  const catSet = [...new Set(allProducts.map(p => p.category_name || p.cat_name || '').filter(Boolean))];
  sel.innerHTML = '<option value="">Barcha kategoriyalar</option>'
    + catSet.map(c => `<option value="${c}">${c}</option>`).join('');
}

function saleSearch(q) {
  const catFilter = document.getElementById('saleCatFilter').value;
  let list = allProducts;
  if (catFilter) list = list.filter(p => (p.category_name || p.cat_name || '') === catFilter);
  if (q) {
    const lq = q.toLowerCase();
    list = list.filter(p => p.name.toLowerCase().includes(lq) || (p.barcode || '').includes(q) || (p.sku || '').includes(lq));
  }
  renderSaleGrid(list);
}

function saleBarcodeKey(e) {
  if (e.key === 'Enter') {
    const q = e.target.value.trim();
    if (!q) return;
    const p = allProducts.find(x => x.barcode === q || x.sku === q);
    if (p) { addToCartById(p.id); e.target.value = ''; renderSaleGrid(allProducts); }
    else saleSearch(q);
  }
}

function renderSaleGrid(list) {
  const el = document.getElementById('saleGrid');
  if (!list.length) { el.innerHTML = '<div class="empty-state">Mahsulot topilmadi</div>'; return; }
  el.innerHTML = list.map(p => {
    const img = p.image_url
      ? `<img src="${p.image_url.startsWith('/static') ? (CFG.apiUrl + p.image_url) : p.image_url}" alt="">`
      : `<span style="font-size:28px">📦</span>`;
    const qty = Number(p.stock_quantity || 0);
    const outOfStock = qty <= 0;
    const colorCls = qty <= 0 ? 'style="color:var(--red)"' : qty <= (p.min_stock || 5) ? 'style="color:var(--amber)"' : '';
    return `<div class="prod-card${outOfStock ? ' out-of-stock' : ''}" data-prod-id="${p.id}" onclick="addToCartById(${p.id})">
      <div class="prod-card-img">${img}</div>
      <div class="prod-card-name">${p.name}</div>
      <div class="prod-card-price">${fmt(p.sale_price)} so'm</div>
      <div class="prod-card-stock" ${colorCls}>Qoldiq: ${fmt(qty)} ${p.unit || 'dona'}</div>
    </div>`;
  }).join('');
}

// ─── CART ─────────────────────────────────────
function addToCartById(id) {
  const prod = allProducts.find(p => p.id === id);
  if (!prod) return;
  addToCart(prod);
}

function addToCart(prod) {
  const existing = cart.find(x => x.id === prod.id);
  if (existing) existing.qty++;
  else cart.push({ ...prod, qty: 1 });
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
        <div class="ci-name">${item.name}</div>
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
  const sel = document.getElementById('saleCustomer');
  const hasCustomer = !!sel.value;
  sel.style.color = hasCustomer ? 'var(--ink)' : (CFG.requireCustomer ? 'var(--red)' : 'var(--ink3)');
  sel.style.borderColor = (!hasCustomer && CFG.requireCustomer) ? 'var(--red)' : '';
}

// ─── PROCESS SALE ─────────────────────────────
async function processSale() {
  if (!cart.length) { toast('Savat bo\'sh', 'warn'); return; }

  // Check mandatory customer
  const customerId = document.getElementById('saleCustomer').value;
  if (CFG.requireCustomer && !customerId) {
    toast('⚠️ Mijoz tanlanmagan! Sozlamalarda "Mijoz tanlanmasa sotmasin" yoqilgan.', 'err');
    document.getElementById('saleCustomer').focus();
    return;
  }
  const total = getTotal();
  const subTotal = cart.reduce((s, x) => s + x.sale_price * x.qty, 0);
  const discountPct = parseFloat(document.getElementById('discountInp').value) || 0;
  const discountAmount = Math.round(subTotal * discountPct / 100);
  const paid = parseFloat(document.getElementById('payAmountInp').value) || total;
  if (payMethod === 'cash' && paid < total) { toast('To\'lov yetarli emas', 'err'); return; }

  const payBtn = document.getElementById('payBtn');
  payBtn.disabled = true;
  try {
    // customerId already read above

    // Payload must match SaleCreate schema exactly
    const payload = {
      items: cart.map(p => ({
        product_id: p.id,
        quantity: p.qty,
        unit_price: p.sale_price,   // required field name in schema
        discount: 0,
      })),
      payment_type: payMethod,      // 'cash' | 'card' | 'credit'
      paid_amount: paid,            // required Decimal
      discount_amount: discountAmount,
      note: '',
    };
    const cartSnapshot = [...cart];
    const result = await api('/sales/', { method: 'POST', body: JSON.stringify(payload) });
    toast('✅ Sotuv muvaffaqiyatli saqlandi!', 'ok');
    showReceipt(result || payload, total, paid, cartSnapshot);

    // Reset cart and form
    cart = [];
    document.getElementById('discountInp').value = '';
    document.getElementById('payAmountInp').value = '';
    document.getElementById('saleCustomer').value = '';
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
  const cfg = receiptSettings.r58 || receiptSettings.r80 || {};
  const company = cfg.company || CFG.cassaName || 'ERPPos';
  const address = cfg.address || '';
  const phone = cfg.phone || '';
  const inn = cfg.inn || '';
  const header = cfg.header || '';
  const footer = cfg.footer || 'Xarid uchun rahmat!';
  const showCashier = cfg.show_cashier !== false;
  const showDate = cfg.show_date !== false;
  const logo = cfg.logo || '';
  const logoSize = cfg.logo_size || 40;

  let html = '';

  // Logo
  if (logo) {
    html += `<div class="receipt-center"><img src="${logo}" alt="Logo" style="max-width:120px;height:${logoSize}px;object-fit:contain;margin:0 auto 8px"></div>`;
  }

  // Company Info
  if (company) {
    html += `<div class="receipt-center" style="font-weight:800;font-size:14px">${company}</div>`;
  }
  if (address) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666">${address}</div>`;
  }
  if (phone) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666">Tel: ${phone}</div>`;
  }
  if (inn) {
    html += `<div class="receipt-center" style="font-size:10px;color:#999">STIR: ${inn}</div>`;
  }
  if (header) {
    html += `<div class="receipt-center" style="font-size:11px;color:#666;font-style:italic;margin-top:4px">${header}</div>`;
  }

  html += `<hr class="receipt-sep">`;

  // Date/Time and Receipt Number
  if (showDate) {
    html += `<div class="receipt-row"><span>Sana:</span><span>${now.toLocaleDateString('uz-UZ')}</span></div>`;
    html += `<div class="receipt-row"><span>Vaqt:</span><span>${now.toLocaleTimeString('uz-UZ')}</span></div>`;
  }
  html += `<div class="receipt-row"><span>Chek #:</span><span>${sale.id || sale.number || Math.floor(Math.random() * 9000 + 1000)}</span></div>`;

  html += `<hr class="receipt-sep">`;

  // Items
  items.forEach(item => {
    const name = item.name || item.product_name || '-';
    const qty = item.qty || item.quantity || 1;
    const price = item.sale_price || item.unit_price || item.price || 0;
    html += `<div class="receipt-row"><span>${name}</span><span>${qty}×${fmt(price)}</span></div>`;
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
    html += `<div class="receipt-center" style="font-size:10px;color:#999;margin-top:4px">Kassir: ${currentUserName}</div>`;
  }

  html += `<hr class="receipt-sep">`;

  // Footer
  if (footer) {
    html += `<div class="receipt-center" style="font-size:10px;color:#999">${footer}</div>`;
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
      const safeS = encodeURIComponent(JSON.stringify(s));
      return `
      <div class="kirim-row" onclick="selectReturnSaleEncoded('${safeS}')">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:700">#${s.id} — ${s.number || ''} — ${s.cashier_name || 'Kassir'}</div>
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
  // Try to load full sale items if list view doesn't have them
  if (!sale.items || !sale.items.length) {
    api('/sales/' + sale.id).then(full => {
      selectedReturnSale = full;
      _renderReturnItems(full.items || []);
    }).catch(() => _renderReturnItems([]));
  } else {
    _renderReturnItems(sale.items);
  }
}

function _renderReturnItems(items) {
  document.getElementById('returnItemsList').innerHTML = items.length
    ? items.map((item, i) => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-size:13px;font-weight:600">${item.product_name || item.name || '#' + item.product_id}</div>
          <div style="font-size:11px;color:var(--ink3)">${item.quantity} dona × ${fmt(item.unit_price || item.price)} so'm</div>
        </div>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600">
          <input type="checkbox" data-idx="${i}" style="accent-color:var(--blue)" checked> Qaytarish
        </label>
      </div>`).join('')
    : '<div class="empty-state">Mahsulotlar topilmadi</div>';
  document.getElementById('processReturnBtn').disabled = !items.length;
  toast('Sotuv tanlandi. Qaytariladigan mahsulotlarni belgilang.', 'info');
}

async function processReturn() {
  if (!selectedReturnSale) { toast('Sotuv tanlanmagan', 'warn'); return; }
  const checks = document.querySelectorAll('#returnItemsList input[type=checkbox]:checked');
  const items = selectedReturnSale.items || [];
  const returnItems = [...checks].map(cb => items[parseInt(cb.dataset.idx)]).filter(Boolean);
  if (!returnItems.length) { toast('Qaytariladigan mahsulot tanlanmagan', 'warn'); return; }
  try {
    await api('/sales/' + selectedReturnSale.id + '/refund', {
      method: 'POST',
      body: JSON.stringify({
        items: returnItems.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
        reason: 'Qaytarish'
      })
    });
    toast('✅ Qaytarish muvaffaqiyatli amalga oshirildi', 'ok');
    selectedReturnSale = null;
    document.getElementById('returnItemsList').innerHTML = '<div class="empty-state">Sotuvni tanlang</div>';
    document.getElementById('returnSaleList').innerHTML = '<div class="empty-state">Sotuv raqamini kiriting</div>';
    document.getElementById('returnSearchInp').value = '';
    document.getElementById('processReturnBtn').disabled = true;
    await loadProducts();
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
  const list = allProducts.filter(p => p.name.toLowerCase().includes(q.toLowerCase()) || (p.sku || '').toLowerCase().includes(q.toLowerCase())).slice(0, 10);
  el.innerHTML = list.map(p => `
    <div class="prod-result-item" data-prod-id="${p.id}" onclick="addKirimItemById(${p.id})">
      <div><div class="pri-name">${p.name}</div><div class="pri-sku">${p.sku || ''}</div></div>
      <div class="pri-price">${fmt(p.cost_price)} so'm</div>
    </div>`).join('') || '<div class="empty-state" style="padding:16px">Topilmadi</div>';
}

function addKirimItemById(id) {
  const prod = allProducts.find(p => p.id === id);
  if (prod) addKirimItem(prod);
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
          <td style="font-size:13px;font-weight:600">${item.name}</td>
          <td class="r"><input type="number" min="1" value="${item.qty}" style="width:60px;padding:4px 6px;border:1.5px solid var(--border2);border-radius:var(--r-xs);font-family:var(--mono);text-align:center;outline:none" onchange="kirimQty(${i},this.value)"></td>
          <td class="r"><input type="number" min="0" value="${item.cost}" style="width:90px;padding:4px 6px;border:1.5px solid var(--border2);border-radius:var(--r-xs);font-family:var(--mono);text-align:right;outline:none" onchange="kirimCost(${i},this.value)"></td>
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
  try {
    // Try with type filter; fallback without if server doesn't support it yet
    let data;
    try {
      data = await api('/inventory/movements?type=in&limit=30');
    } catch {
      data = await api('/inventory/movements?limit=30');
    }
    const list = Array.isArray(data) ? data : (data?.items || []);
    if (!list.length) { el.innerHTML = '<div class="empty-state" style="padding:40px">Kirimlar topilmadi</div>'; return; }
    el.innerHTML = list.map(m => `
      <div class="kirim-row">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:700">${m.reference_type === 'purchase' ? 'Kirim #' + m.reference_id : (m.reason || 'Kirim')} — ${m.product_name || 'Mahsulot #' + m.product_id}</div>
          <div style="font-size:11px;color:var(--ink3)">${new Date(m.created_at || m.date).toLocaleDateString('uz-UZ')}</div>
        </div>
        <div style="text-align:right">
          <div style="font-family:var(--mono);font-weight:700;color:var(--green)">+${m.quantity} dona</div>
          <div style="font-size:11px;color:var(--ink3)">Qoldiq: ${m.qty_after || '—'}</div>
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state" style="padding:40px">⚠️ ${e.message}</div>`;
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
      <td><span style="font-family:var(--mono);font-size:11px">${p.sku || '-'}</span></td>
      <td style="font-weight:600">${p.name}</td>
      <td style="color:var(--ink3)">${p.category_name || '-'}</td>
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
    <div class="prod-result-item" onclick="addFavoriteById(${p.id})">
      <div><div class="pri-name">${p.name}</div><div class="pri-sku">${p.sku || ''}</div></div>
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
    const img = live.image_url
      ? `<img src="${live.image_url.startsWith('/static') ? (CFG.apiUrl + live.image_url) : live.image_url}" alt="">`
      : `<span style="font-size:28px">📦</span>`;
    const outOfStock = qty <= 0;
    const colorCls = qty <= 0 ? 'color:var(--red)' : qty <= (live.min_stock || 5) ? 'color:var(--amber)' : '';
    return `<div class="prod-card${outOfStock ? ' out-of-stock' : ''}" style="position:relative" onclick="addToCartById(${p.id});switchTab('sale')">
      <button onclick="event.stopPropagation();removeFavorite(${p.id})" title="Sevimlilardan o'chirish" style="position:absolute;top:6px;right:6px;background:rgba(255,255,255,0.9);border:none;border-radius:50%;width:22px;height:22px;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;z-index:2">✕</button>
      <div class="prod-card-img">${img}</div>
      <div class="prod-card-name">${live.name}</div>
      <div class="prod-card-price">${fmt(live.sale_price)} so'm</div>
      <div class="prod-card-stock" style="${colorCls}">Qoldiq: ${fmt(qty)} ${live.unit || 'dona'}</div>
    </div>`;
  }).join('');
}

// ─── KASSA STATS ──────────────────────────────
async function loadKassaStats() {
  try {
    // Load today's sales only
    const todayParam = '&date_today=true';
    const data = await api('/sales/?limit=100' + todayParam).catch(() => api('/sales/?limit=100'));
    const sales = Array.isArray(data) ? data : (data?.items || []);
    const naqdTotal = sales.filter(s => s.payment_type === 'cash').reduce((sum, s) => sum + Number(s.total_amount || 0), 0);
    const cardTotal = sales.filter(s => s.payment_type === 'card').reduce((sum, s) => sum + Number(s.total_amount || 0), 0);
    document.getElementById('kassaNaqdTotal').textContent = fmt(naqdTotal) + ' so\'m';
    document.getElementById('kassaCardTotal').textContent = fmt(cardTotal) + ' so\'m';
    document.getElementById('kassaSalesCount').textContent = sales.length + ' ta';
    document.getElementById('kassaReturnTotal').textContent = '0 so\'m';
    document.getElementById('kassaSalesTbody').innerHTML = sales.slice(0, 30).map(s => `
      <tr>
        <td>${new Date(s.created_at || s.date).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })}</td>
        <td>${s.cashier_name || '—'}</td>
        <td class="r" style="font-weight:700;font-family:var(--mono)">${fmt(s.total_amount || s.total)} so'm</td>
        <td><span class="badge ${s.payment_type === 'cash' ? 'badge-green' : 'badge-blue'}">${s.payment_type === 'cash' ? 'Naqd' : s.payment_type === 'card' ? 'Karta' : s.payment_type}</span></td>
        <td class="c"><button onclick="reprint(${s.id})" style="background:none;border:1.5px solid var(--border2);border-radius:var(--r-xs);padding:3px 8px;cursor:pointer;font-size:12px;color:var(--ink2)">🖨</button></td>
      </tr>`).join('') || '<tr><td colspan="5" class="empty-row">Bugun sotuv yo\'q</td></tr>';
  } catch (e) { console.log('Kassa stats error:', e.message); }
}

function reprint(id) { toast('Chek qayta chop etildi #' + id, 'info'); }

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
        <div style="font-size:13px;color:var(--ink2)">Kassir ID: ${activeSmena?.cashier_id || '—'}</div>
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
  CFG.discount = settingsToggles.discount;
  CFG.credit = settingsToggles.credit;
  CFG.requireCustomer = settingsToggles.requireCustomer;
  CFG.printer = document.getElementById('settPrinter')?.value || '';
  CFG.paperSize = document.getElementById('settPaperSize')?.value || '80mm';
  CFG.cassaName = document.getElementById('settCassaName')?.value || 'Kassa #1';
  CFG.apiUrl = document.getElementById('settApiUrl')?.value || 'http://localhost:8000';
  Object.entries(CFG).forEach(([k, v]) => localStorage.setItem('pos_' + k, typeof v === 'boolean' ? (v ? '1' : '0') : v));
  toast('✅ Sozlamalar saqlandi', 'ok');
  checkApiStatus();
}

// ─── PAY SYSTEMS ──────────────────────────────
function openAddPaySystem() { openModal('paySystemModal'); }
function savePaySystem() {
  const name = document.getElementById('psName').value;
  if (!name) { toast('Nomi kiriting', 'warn'); return; }
  paySystems.push({ name, type: document.getElementById('psType').value, terminal: document.getElementById('psTerminal').value, active: true });
  localStorage.setItem('pos_paySystems', JSON.stringify(paySystems));
  renderPaySystems();
  closeModal('paySystemModal');
  toast('✅ To\'lov tizimi qo\'shildi', 'ok');
}

function renderPaySystems() {
  const el = document.getElementById('paySystemsTbody');
  if (!el) return;
  if (!paySystems.length) { el.innerHTML = '<tr><td colspan="5" class="empty-row">To\'lov tizimlari topilmadi</td></tr>'; return; }
  el.innerHTML = paySystems.map((p, i) => `
    <tr>
      <td style="font-weight:600">${p.name}</td>
      <td><span class="badge badge-blue">${p.type}</span></td>
      <td style="font-family:var(--mono);font-size:12px">${p.terminal || '—'}</td>
      <td class="c"><span class="badge badge-green">Faol</span></td>
      <td class="c"><button onclick="removePaySystem(${i})" style="color:var(--red);background:none;border:none;cursor:pointer;font-size:16px">✕</button></td>
    </tr>`).join('');
}

function removePaySystem(i) {
  paySystems.splice(i, 1);
  localStorage.setItem('pos_paySystems', JSON.stringify(paySystems));
  renderPaySystems();
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
