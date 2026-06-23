/**
 * TOUCH-OPTIMIZED POS - Camera Scanner + Cart
 * For 9" tablet - continuous barcode scanning
 */

// --- STATE ---
let cart = {};
let saleType = 'menudeo';
let clientId = null;
let clientName = null;
let clientWallet = 0;
let saleStarted = false;
let sessionKey = '';
let lastAddedId = null;
let currentDespieceConfig = null;
let qrScanner = null;
let isScanning = false;
let lastScannedCode = '';
let lastScannedTime = 0;
let scanDebounceMs = 1500;
let pendingScanProduct = null;
let lookupMode = false;
let cameraOn = true;

// --- DOM REFS ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// --- CSRF ---
function getCSRFToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.getAttribute('content');
  const cookies = document.cookie.split(';');
  for (let c of cookies) {
    if (c.trim().startsWith('csrftoken=')) return c.trim().substring('csrftoken='.length);
  }
  return '';
}

// --- SESSION SYNC ---
function syncCartToSession(extra) {
  const payload = {
    cart, saleType, clientId, clientName, clientWallet, saleStarted,
    ...(extra || {}),
  };
  return fetch('/pos/cart/save/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }).then(r => { if (!r.ok) console.error('Cart sync fail:', r.status); return r; })
    .catch(err => console.error('Cart sync error:', err));
}

function syncCheckoutState(state) {
  fetch('/pos/checkout/save/', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(state),
  }).catch(() => {});
}

function clearCheckoutState() {
  fetch('/pos/checkout/clear/', {method: 'POST'}).catch(() => {});
}

// --- BROADCAST ---
let posChannel = null;
try { posChannel = new BroadcastChannel('pos-display'); } catch(e) {}
function broadcastToDisplay(msg) { if (posChannel) posChannel.postMessage(msg); }

// ==================== SCANNER ====================
function initScanner() {
  if (!window.Html5Qrcode) {
    setTimeout(initScanner, 500);
    return;
  }
  if (qrScanner) {
    try { qrScanner.stop(); } catch(e) {}
  }
  qrScanner = new Html5Qrcode('scanner-viewfinder');
  qrScanner.start(
    { facingMode: 'environment' },
    {
      fps: 12,
      qrbox: { width: 260, height: 70 },
      formatsToSupport: [
        Html5QrcodeSupportedFormats.EAN_13,
        Html5QrcodeSupportedFormats.EAN_8,
        Html5QrcodeSupportedFormats.UPC_A,
        Html5QrcodeSupportedFormats.UPC_E,
        Html5QrcodeSupportedFormats.CODE_128,
        Html5QrcodeSupportedFormats.CODE_39,
        Html5QrcodeSupportedFormats.CODE_93,
        Html5QrcodeSupportedFormats.ITF,
      ],
    },
    onScanSuccess,
    () => {}
  ).then(() => { isScanning = true; })
   .catch(err => console.error('Scanner start error:', err));
}

function toggleCamera() {
  const btn = $('#cam-toggle');
  const camOverlay = $('#cam-off-overlay');
  if (cameraOn) {
    cameraOn = false;
    if (qrScanner) { try { qrScanner.stop(); isScanning = false; } catch(e) {} }
    btn.innerHTML = '📷';
    btn.classList.add('off');
    if (camOverlay) camOverlay.style.display = 'flex';
  } else {
    cameraOn = true;
    if (camOverlay) camOverlay.style.display = 'none';
    btn.innerHTML = '📷';
    btn.classList.remove('off');
    initScanner();
  }
}

function onScanSuccess(decodedText) {
  const now = Date.now();
  if (decodedText === lastScannedCode && now - lastScannedTime < scanDebounceMs) return;
  lastScannedCode = decodedText;
  lastScannedTime = now;
  navigator.vibrate && navigator.vibrate(50);
  flashViewfinder();
  lookupBarcode(decodedText);
}

// --- BEEP SOUNDS (Web Audio API, no files needed) ---
let audioCtx = null;
function initAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume();
}
function playBeep(freq, durationMs, type) {
  try {
    initAudio();
    if (!audioCtx) return;
    if (audioCtx.state === 'suspended') audioCtx.resume();
    if (audioCtx.state === 'suspended') return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type || 'sine';
    osc.frequency.value = freq;
    const t = audioCtx.currentTime;
    gain.gain.setValueAtTime(0.3, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + Math.max(durationMs / 1000, 0.01));
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(t);
    osc.stop(t + durationMs / 1000);
  } catch(e) { /* audio not available */ }
}

function flashViewfinder() {
  const el = $('#scanner-viewfinder');
  el.style.outline = '3px solid #2e7d32';
  el.style.outlineOffset = '-3px';
  setTimeout(() => { el.style.outline = 'none'; }, 200);
}

function lookupBarcode(code) {
  fetch('/pos/scan/?q=' + encodeURIComponent(code))
    .then(r => r.json().catch(() => null))
    .then(data => {
      if (!data || data.error) {
        playBeep(300, 300, 'square');
        showNotFound(code);
        return;
      }
      playBeep(880, 120, 'sine');
      if (saleStarted && !lookupMode) {
        openQtyModal(data);
      } else {
        showProductInfo(data);
      }
    })
    .catch(() => showNotFound(code));
}

// --- LOOKUP MODE TOGGLE ---
function toggleLookupMode() {
  lookupMode = !lookupMode;
  const btn = $('#lookup-toggle');
  if (lookupMode) {
    btn.classList.add('active');
    btn.innerHTML = '🔍 Lookup ON';
    showToast('Lookup mode: scans show info only', 'info');
  } else {
    btn.classList.remove('active');
    btn.innerHTML = '🔍 Lookup';
    showToast('Sale mode: scan to add to cart', 'info');
  }
}

// --- INFO PANEL (IDLE MODE) ---
function showProductInfo(p) {
  const info = $('#product-info');
  const nf = $('#scan-notfound');
  nf.style.display = 'none';
  info.style.display = 'block';
  $('#pi-name').textContent = p.compose_name || p.name;
  const price = parseFloat(p.price) || 0;
  const mayoreo = parseFloat(p.price_mayoreo) || 0;
  let priceHtml = '$' + price.toFixed(2);
  if (mayoreo > 0) priceHtml += ' <span class="pi-mayoreo">May: $' + mayoreo.toFixed(2) + '</span>';
  $('#pi-price').innerHTML = priceHtml;
  let details = [];
  if (p.Granel_Item) details.push('📦 Granel');
  if (p.despiece_config_id) details.push('📦→ Despiece: ' + (p.despiece_source_name || ''));
  if (p.granel) details.push('⚖️ Venta por peso');
  $('#pi-details').textContent = details.join(' · ');
  let stockText = p.stock > 0 ? p.stock + ' pz' : 'Agotado';
  let stockClass = p.stock > 0 ? '' : ' out';
  if (p.stock <= 0 && p.despiece_config_id && p.despiece_source_stock > 0) {
    stockText += ' · src: ' + p.despiece_source_stock;
  }
  $('#pi-stock').textContent = stockText;
  $('#pi-stock').className = 'pi-stock' + stockClass;
  $('#idle-msg').style.display = 'none';
}

function showNotFound(code) {
  $('#product-info').style.display = 'none';
  const nf = $('#scan-notfound');
  nf.style.display = 'block';
  nf.querySelector('.nf-sub').textContent = 'Código: ' + code + ' — ingrésalo manualmente';
  $('#manual-barcode').value = code;
  $('#idle-msg').style.display = 'none';
}

// ==================== QTY MODAL ====================
let qtyNumpadValue = '1';

function initQtyNumpad() {
  const numpad = $('#qm-numpad');
  if (!numpad) return;
  numpad.querySelectorAll('.numpad-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.value;
      if (val === 'clear') { qtyNumpadValue = '1'; }
      else if (val === 'backspace') { qtyNumpadValue = qtyNumpadValue.length > 1 ? qtyNumpadValue.slice(0, -1) : '1'; }
      else { 
        const newVal = qtyNumpadValue === '1' ? val : qtyNumpadValue + val;
        qtyNumpadValue = newVal.replace(/^0+/, '') || '1';
      }
      $('#qm-display').textContent = qtyNumpadValue;
    });
  });
}

function openQtyModal(product) {
  pendingScanProduct = product;
  qtyNumpadValue = '1';
  $('#qty-modal-title').textContent = 'Cantidad para:';
  $('#qm-product').textContent = product.compose_name || product.name;
  $('#qm-display').textContent = '1';
  $('#qty-modal').classList.add('show');
}

function closeQtyModal() {
  $('#qty-modal').classList.remove('show');
  pendingScanProduct = null;
}

function confirmQtyModal() {
  const qty = parseInt($('#qm-display').textContent) || 1;
  if (pendingScanProduct) {
    addScannedToCart(pendingScanProduct, qty);
  }
  closeQtyModal();
}

// ==================== ADD SCANNED TO CART ====================
function addScannedToCart(product, qty) {
  if (!saleStarted) { showToast('Start a sale first', 'warning'); return; }
  if (qty > product.stock && !product.Granel_Item && !product.despiece_config_id) {
    showToast('Only ' + product.stock + ' in stock', 'error');
    return;
  }
  const price = saleType === 'mayoreo' ? (parseFloat(product.price_mayoreo) || 0) : (parseFloat(product.price) || 0);
  const pid = String(product.id);
  if (cart[pid]) {
    cart[pid].qty += qty;
  } else {
    cart[pid] = {
      id: pid,
      barcode: product.barcode || '',
      name: (product.compose_name || product.name).replace('GRANEL', '').trim(),
      qty: qty,
      price: price,
      tipo: saleType,
      addedAt: Date.now(),
    };
  }
  lastAddedId = pid;
  renderCartRows();
  updateBottomTotals();
  syncCartToSession();
  showToast('✓ ' + (product.compose_name || product.name) + ' x' + qty, 'success');
}

// ==================== CART ROWS ====================
function renderCartRows() {
  const container = $('#cart-rows');
  const keys = Object.keys(cart);
  if (keys.length === 0) {
    container.innerHTML = '<div class="cr-empty">🛒 Carrito vacío</div>';
    $('#cart-rows-count').textContent = '0 items';
    return;
  }
  let totalItems = 0;
  const entries = Object.values(cart).sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));
  container.innerHTML = '';
  entries.forEach(item => {
    totalItems += item.qty;
    const div = document.createElement('div');
    div.className = 'cr-item' + (item.id === lastAddedId ? ' highlight' : '');
    div.dataset.pid = item.id;
    const lineTotal = (item.qty * item.price).toFixed(2);
    div.innerHTML =
      '<div class="cr-name">' + item.name + '</div>' +
      '<div class="cr-controls">' +
        '<button class="cr-qty-btn" data-delta="-1">−</button>' +
        '<span class="cr-qty-val">' + item.qty + '</span>' +
        '<button class="cr-qty-btn" data-delta="1">+</button>' +
      '</div>' +
      '<div class="cr-price">$' + lineTotal + '</div>' +
      '<button class="cr-remove">✕</button>';
    div.querySelector('.cr-remove').addEventListener('click', () => removeFromCart(item.id));
    div.querySelectorAll('.cr-qty-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const delta = parseInt(btn.dataset.delta);
        updateQty(item.id, delta);
      });
    });
    container.appendChild(div);
  });
  $('#cart-rows-count').textContent = totalItems + ' items';
}

function updateBottomTotals() {
  let total = 0;
  Object.values(cart).forEach(item => { total += item.qty * item.price; });
  $('#bt-total').textContent = '$' + total.toFixed(2);
}

function updateQty(pid, delta) {
  if (!cart[pid]) return;
  cart[pid].qty += delta;
  if (cart[pid].qty <= 0) {
    delete cart[pid];
  }
  renderCartRows();
  updateBottomTotals();
  syncCartToSession();
}

function removeFromCart(pid) {
  delete cart[pid];
  if (lastAddedId === pid) lastAddedId = null;
  renderCartRows();
  updateBottomTotals();
  syncCartToSession();
}

function clearCart() {
  if (Object.keys(cart).length === 0) return;
  showConfirm('Clear entire cart?', () => {
    cart = {};
    lastAddedId = null;
    renderCartRows();
    updateBottomTotals();
    syncCartToSession();
  });
}

// ==================== SETTINGS (New Sale) ====================
function openSettings() {
  $('#settings-modal').classList.add('show');
  $('#sale-type-select').value = saleType;
}

function closeSettings() {
  $('#settings-modal').classList.remove('show');
}

function saveSettings() {
  saleType = $('#sale-type-select').value;
  const sel = $('#client-select');
  clientId = sel.value || null;
  const opt = sel.options[sel.selectedIndex];
  clientName = opt ? opt.text : 'General';
  clientWallet = parseFloat(opt?.dataset?.wallet) || 0;
  if (!saleType) { showToast('Select a sale type', 'warning'); return; }
  saleStarted = true;
  updateSaleTypeDisplay();
  closeSettings();
  syncCartToSession();
  broadcastToDisplay('sale_started');
  // Show cart rows and bottom bar
  $('#cart-rows-wrap').style.display = 'flex';
  $('#bottom-bar').style.display = 'flex';
  $('#idle-msg').style.display = 'none';
  // Clear info panel for fresh start
  $('#product-info').style.display = 'none';
  $('#scan-notfound').style.display = 'none';
  renderCartRows();
  updateBottomTotals();
}

function updateSaleTypeDisplay() {
  $('#sale-type-display').textContent = saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo';
  $('#client-display').textContent = clientName || 'General';
}

// --- MANUAL INPUT + LIVE SUGGESTIONS ---
let suggestDebounce = null;
let suggestIndex = -1;

function initManualInput() {
  const input = $('#manual-barcode');
  const btn = $('#manual-lookup');
  const wrap = input.closest('.manual-wrap');

  btn.addEventListener('click', () => {
    const code = input.value.trim();
    if (code) { clearSuggestions(); lookupBarcode(code); }
  });
  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      const sel = wrap && wrap.querySelector('.sg-item.active');
      if (sel) { selectSuggestion(sel.dataset); return; }
      const code = input.value.trim();
      if (code) { clearSuggestions(); lookupBarcode(code); }
    }
  });
  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (q.length < 2) { clearSuggestions(); return; }
    clearTimeout(suggestDebounce);
    suggestDebounce = setTimeout(() => fetchSuggestions(q), 200);
  });
  input.addEventListener('blur', () => setTimeout(clearSuggestions, 250));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); moveSuggestion(1); }
    if (e.key === 'ArrowUp') { e.preventDefault(); moveSuggestion(-1); }
    if (e.key === 'Escape') { clearSuggestions(); }
  });
}

function fetchSuggestions(q) {
  fetch('/pos/search/?q=' + encodeURIComponent(q))
    .then(r => r.json())
    .then(items => {
      if (!items || !items.length) { clearSuggestions(); return; }
      renderSuggestions(items.slice(0, 8));
    })
    .catch(() => clearSuggestions());
}

function renderSuggestions(items) {
  const wrap = $('#manual-barcode').closest('.manual-wrap');
  if (!wrap) return;
  let existing = wrap.querySelector('.sg-dropdown');
  if (!existing) {
    existing = document.createElement('div');
    existing.className = 'sg-dropdown';
    wrap.appendChild(existing);
  }
  existing.innerHTML = '';
  items.forEach((p, i) => {
    const div = document.createElement('div');
    div.className = 'sg-item' + (i === 0 ? ' active' : '');
    div.dataset.id = p.id;
    div.dataset.barcode = p.barcode || '';
    div.dataset.clave = p.clave || '';
    div.dataset.name = p.compose_name || p.name;
    div.dataset.price = p.price || 0;
    div.dataset.price_mayoreo = p.price_mayoreo || 0;
    div.dataset.stock = p.stock || 0;
    div.dataset.granel = p.granel || false;
    div.dataset.Granel_Item = p.Granel_Item || false;
    div.dataset.despiece_config_id = p.despiece_config_id || '';
    div.dataset.despiece_source_name = p.despiece_source_name || '';
    div.dataset.despiece_source_id = p.despiece_source_id || '';
    div.dataset.despiece_source_stock = p.despiece_source_stock || 0;
    div.dataset.despiece_units_per = p.despiece_units_per || 0;
    div.innerHTML =
      '<span class="sg-name">' + (p.compose_name || p.name) + '</span>' +
      '<span class="sg-meta">' +
        (p.clave ? '<span class="sg-clave">' + p.clave + '</span>' : '') +
        '<span class="sg-price">$' + (parseFloat(p.price) || 0).toFixed(2) + '</span>' +
        '<span class="sg-stock">' + (p.stock > 0 ? p.stock + ' pz' : 'Agotado') + '</span>' +
      '</span>';
    div.addEventListener('mousedown', (e) => { e.preventDefault(); selectSuggestion(div.dataset); });
    div.addEventListener('touchstart', (e) => { e.preventDefault(); selectSuggestion(div.dataset); });
    existing.appendChild(div);
  });
  suggestIndex = 0;
}

function moveSuggestion(dir) {
  const wrap = $('#manual-barcode').closest('.manual-wrap');
  if (!wrap) return;
  const items = wrap.querySelectorAll('.sg-item');
  if (!items.length) return;
  items.forEach(el => el.classList.remove('active'));
  suggestIndex = Math.max(0, Math.min(suggestIndex + dir, items.length - 1));
  items[suggestIndex].classList.add('active');
}

function selectSuggestion(data) {
  clearSuggestions();
  // Convert data-* attributes to a product object like the scan response
  const product = {
    id: parseInt(data.id),
    barcode: data.barcode,
    clave: data.clave,
    name: data.name,
    compose_name: data.name,
    price: parseFloat(data.price),
    price_mayoreo: parseFloat(data.price_mayoreo),
    stock: parseInt(data.stock),
    granel: data.granel === 'true',
    Granel_Item: data.Granel_Item === 'true',
    despiece_config_id: data.despiece_config_id ? parseInt(data.despiece_config_id) : null,
    despiece_source_name: data.despiece_source_name || null,
    despiece_source_id: data.despiece_source_id ? parseInt(data.despiece_source_id) : null,
    despiece_source_stock: data.despiece_source_stock ? parseInt(data.despiece_source_stock) : null,
    despiece_units_per: parseFloat(data.despiece_units_per) || null,
  };
  if (saleStarted && !lookupMode) {
    openQtyModal(product);
  } else {
    showProductInfo(product);
  }
  $('#manual-barcode').value = '';
}

function clearSuggestions() {
  const wrap = $('#manual-barcode').closest('.manual-wrap');
  if (wrap) {
    const dd = wrap.querySelector('.sg-dropdown');
    if (dd) dd.remove();
  }
  suggestIndex = -1;
}

// ==================== CHECKOUT ====================
function proceedCheckout() {
  if (Object.keys(cart).length === 0) { showToast('Cart is empty', 'warning'); return; }
  const items = Object.values(cart).map(item => ({ product_id: item.id, quantity: item.qty }));
  showLoading(true);
  fetch('/pos/validate-stock/', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({items}),
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (!data.success) {
      const failures = data.items.filter(i => !i.valid);
      let msg = 'Stock issues:\n';
      failures.forEach(f => { msg += '• ' + f.product_name + ': ' + f.message + '\n'; });
      showToast(msg, 'error');
      return;
    }
    openCheckoutModal();
  })
  .catch(() => { showLoading(false); showToast('Failed to validate stock', 'error'); });
}

function openCheckoutModal() {
  $('#checkout-modal').classList.add('show');
  let totalAmount = 0;
  Object.values(cart).forEach(item => { totalAmount += item.qty * item.price; });
  $('#chk-total').textContent = '$' + totalAmount.toFixed(2);
  window.currentTotal = totalAmount;
  $$('.payment-method-btn').forEach(btn => {
    btn.addEventListener('click', () => selectPaymentMethod(btn.dataset.method));
  });
  selectPaymentMethod('cash');
  setupNumpad('cash-numpad', 'cash-amount-display', (val) => {
    const cashAmount = parseFloat(val) || 0;
    const change = cashAmount - window.currentTotal;
    const cd = $('#change-display');
    if (cashAmount > 0) {
      cd.style.display = 'block';
      cd.className = 'change-display ' + (change < 0 ? 'negative' : 'positive');
      cd.textContent = change < 0 ? 'Need $' + Math.abs(change).toFixed(2) + ' more' : 'Change: $' + change.toFixed(2);
    } else { cd.style.display = 'none'; }
    syncCheckoutState({ active: true, payment_method: window.selectedPayment || 'cash', total: window.currentTotal, cash_received: cashAmount, change: change > 0 ? change : 0 });
  });
  $('#cash-amount-display').textContent = '$0.00';
  $('#change-display').style.display = 'none';
}

function closeCheckout() {
  $('#checkout-modal').classList.remove('show');
  clearCheckoutState();
}

function selectPaymentMethod(method) {
  window.selectedPayment = method;
  $$('.payment-method-btn').forEach(btn => btn.classList.toggle('selected', btn.dataset.method === method));
  $('#cash-payment-area').style.display = method === 'cash' ? 'block' : 'none';
}

function setupNumpad(numpadId, displayId, onValueChange) {
  const numpad = $('#' + numpadId);
  if (!numpad) return;
  let currentValue = '';
  numpad.querySelectorAll('.numpad-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.value;
      if (val === 'clear') { currentValue = ''; }
      else if (val === 'backspace') { currentValue = currentValue.slice(0, -1); }
      else if (val === '.') { if (!currentValue.includes('.')) currentValue += '.'; }
      else { currentValue += val; }
      const numVal = parseFloat(currentValue) || 0;
      $('#' + displayId).textContent = numVal > 0 ? '$' + numVal.toFixed(2) : '$0.00';
      if (onValueChange) onValueChange(currentValue);
    });
  });
}

function confirmCheckout() {
  const paymentMethod = window.selectedPayment || 'cash';
  const totalAmount = window.currentTotal;
  if (paymentMethod === 'cash') {
    const cashText = $('#cash-amount-display').textContent.replace('$', '');
    const cashAmount = parseFloat(cashText) || 0;
    if (cashAmount <= 0) { showToast('Enter the cash amount received', 'warning'); return; }
    if (cashAmount < totalAmount) {
      showToast('Insufficient payment! Need $' + (totalAmount - cashAmount).toFixed(2) + ' more', 'error');
      return;
    }
  }
  const items = Object.values(cart).map(item => ({ product_id: item.id, quantity: item.qty, price: item.price }));
  const saleData = { items, tipo: saleType, payment_method: paymentMethod, client_id: clientId || null, total_amount: totalAmount };
  showLoading(true);
  fetch('/pos/complete-sale/', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(saleData),
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (data.success) {
      showToast('✅ Sale #' + data.sale_id + ' completed! $' + data.total, 'success');
      clearCheckoutState();
      syncCartToSession({ saleCompleted: { message: 'Gracias por su compra', timestamp: Date.now() / 1000 } })
        .then(() => { closeCheckout(); broadcastToDisplay('sale_completed'); setTimeout(() => location.reload(), 300); });
    } else { showToast('Error: ' + data.error, 'error'); }
  })
  .catch(() => { showLoading(false); showToast('Failed to complete sale', 'error'); });
}

// ==================== DESPIECE ====================
function openDespieceModal(dataset) {
  currentDespieceConfig = {
    configId: dataset.despieceConfigId,
    sourceName: dataset.despieceSourceName,
    sourceStock: parseInt(dataset.despieceSourceStock) || 0,
    unitsPer: parseFloat(dataset.despieceUnitsPer) || 1,
  };
  if (!currentDespieceConfig.configId) { showToast('No despiece config', 'error'); return; }
  $('#despiece-source-name').textContent = currentDespieceConfig.sourceName;
  $('#despiece-source-stock').textContent = currentDespieceConfig.sourceStock + ' pz';
  $('#despiece-qty').value = 1;
  updateDespiecePreview();
  $('#despiece-modal').classList.add('show');
}

function closeDespieceModal() {
  $('#despiece-modal').classList.remove('show');
  currentDespieceConfig = null;
}

function despieceQtyDelta(delta) {
  const input = $('#despiece-qty');
  let val = parseInt(input.value) + delta;
  val = Math.max(1, Math.min(val, currentDespieceConfig?.sourceStock || 999));
  input.value = val;
  updateDespiecePreview();
}

function updateDespiecePreview() {
  const qty = parseInt($('#despiece-qty').value) || 0;
  const dest = qty * (currentDespieceConfig?.unitsPer || 1);
  $('#despiece-dest-qty').textContent = dest;
}

function confirmDespiece() {
  const qty = parseInt($('#despiece-qty').value) || 0;
  if (qty <= 0) { showToast('Enter a valid quantity', 'warning'); return; }
  if (qty > currentDespieceConfig.sourceStock) { showToast('Only ' + currentDespieceConfig.sourceStock + ' available', 'error'); return; }
  showLoading(true);
  const url = '/im/product/despiece/' + currentDespieceConfig.configId + '/process/';
  const fd = new FormData();
  fd.append('source_quantity', qty);
  fd.append('csrfmiddlewaretoken', getCSRFToken());
  var xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  xhr.onload = function() {
    showLoading(false);
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) {}
    if (xhr.status >= 200 && xhr.status < 300 && data && data.success) {
      showToast('✅ Despiece: ' + data.source_quantity + ' → ' + data.destination_quantity + ' units created', 'success');
      closeDespieceModal();
      showToast('Reloading...', 'info');
      setTimeout(() => location.reload(), 500);
    } else { showToast('❌ ' + ((data && data.error) || 'Despiece failed'), 'error'); }
  };
  xhr.onerror = function() { showLoading(false); showToast('❌ Network error', 'error'); };
  xhr.send(fd);
}

// ==================== CUSTOMER DISPLAY ====================
function openDisplayLink() {
  const baseUrl = window.location.origin + '/pos/customer-display/?sk=' + encodeURIComponent(sessionKey);
  $('#display-url').value = baseUrl + '&activate=1';
  try { posChannel?.postMessage('sale_started'); } catch(e) {}
  window.open(baseUrl + '&activate=1', 'customer-display', 'width=800,height=600');
  $('#display-modal').classList.add('show');
}

function closeDisplayLink() { $('#display-modal').classList.remove('show'); }

function copyDisplayLink() {
  const input = $('#display-url');
  input.select(); input.setSelectionRange(0, 99999);
  navigator.clipboard.writeText(input.value).catch(() => {});
  showToast('Link copied', 'success');
}

// ==================== TOAST ====================
function showToast(message, type) {
  const container = $('#toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast toast-' + (type || 'info');
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(100%)'; setTimeout(() => toast.remove(), 300); }, 2500);
}

// ==================== CONFIRM ====================
function showConfirm(message, onConfirm) {
  $('#confirm-modal').classList.add('show');
  $('#confirm-message').textContent = message;
  $('#confirm-yes').onclick = () => { $('#confirm-modal').classList.remove('show'); if (onConfirm) onConfirm(); };
  $('#confirm-no').onclick = () => { $('#confirm-modal').classList.remove('show'); };
}

// ==================== LOADING ====================
function showLoading(show) { $('#loading-overlay').style.display = show ? 'flex' : 'none'; }

// ==================== KEYBOARD ====================
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if ($('#qty-modal.show')) { closeQtyModal(); return; }
    if ($('#despiece-modal.show')) { closeDespieceModal(); return; }
    if ($('#checkout-modal.show')) { closeCheckout(); return; }
    if ($('#settings-modal.show')) { closeSettings(); return; }
    if ($('#display-modal.show')) { closeDisplayLink(); return; }
    if ($('#confirm-modal.show')) { $('#confirm-modal').classList.remove('show'); return; }
    clearCart();
  }
});

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', function() {
  sessionKey = DISPLAY_SESSION_KEY;
  initManualInput();
  initScanner();
  initQtyNumpad();
  // Init audio context on first user tap (Chrome requires user gesture)
  document.addEventListener('click', initAudio, { once: true });
  document.addEventListener('touchstart', initAudio, { once: true });
  // Show idle message
  $('#idle-msg').style.display = 'flex';
});
