/**
 * TOUCH-OPTIMIZED POS - Split layout: Left products + Right cart + Bottom keyboard
 * For 10" tablet - fast, two-tap add to cart
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
let scannerConnected = true;
let scannerPollTimer = null;
let currentMode = 'sale'; // 'sale' | 'devolucion' | 'cotizacion'

// Return state
let returnSaleData = null;
let returnMode = null; // null | 'ticket' | 'noticket'

// New state for keyboard + selection
let searchQuery = '';
let selectedProductId = null;
let selectedProductData = null;
let keyboardMode = 'search'; // 'search' | 'quantity'
let qtyValue = '1';
let keyboardVisible = true;
let searchDebounce = null;
let lastKbKeyTime = 0;

// Barcode scanner debounce
let lastScannedCode = '';
let lastScannedTime = 0;
let scanDebounceMs = 1500;

// Barcode detection buffer (USB wedge scanner)
let barcodeBuf = '';
let barcodeBufTimer = 0;

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

// ==================== BEEP SOUNDS ====================
let beepOkUrl = null;
let beepFailUrl = null;
let beepReady = false;

function initBeeps() {
  if (beepReady) return;
  beepReady = true;
  beepOkUrl = createBeepWav(880, 0.12, 'sine');
  beepFailUrl = createBeepWav(300, 0.3, 'square');
}

function createBeepWav(freq, durationSec, type) {
  try {
    const sr = 44100;
    const numSamples = Math.floor(sr * durationSec);
    const buf = new ArrayBuffer(44 + numSamples * 2);
    const v = new DataView(buf);
    function w(str, off) { for (let i = 0; i < str.length; i++) v.setUint8(off + i, str.charCodeAt(i)); }
    w('RIFF', 0); v.setUint32(4, 36 + numSamples * 2, true);
    w('WAVE', 8); w('fmt ', 12); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    w('data', 36); v.setUint32(40, numSamples * 2, true);
    for (let i = 0; i < numSamples; i++) {
      const t = i / sr;
      const envelope = Math.max(0, 1 - t / durationSec);
      let sample;
      if (type === 'square') {
        sample = Math.sin(2 * Math.PI * freq * t) >= 0 ? 0.5 : -0.5;
      } else {
        sample = Math.sin(2 * Math.PI * freq * t) * 0.5;
      }
      v.setInt16(44 + i * 2, sample * envelope * 32767, true);
    }
    const blob = new Blob([buf], { type: 'audio/wav' });
    return URL.createObjectURL(blob);
  } catch(e) { return null; }
}

function playBeep(type) {
  try {
    initBeeps();
    const url = type === 'fail' ? beepFailUrl : beepOkUrl;
    if (!url) return;
    const a = new Audio(url);
    a.volume = 0.6;
    a.play().catch(function() {});
  } catch(e) {}
}

// ==================== KEYBOARD HANDLING ====================
function initKeyboard() {
  // Setup custom keyboard button clicks
  $$('.kb-key').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      const key = this.dataset.key;
      handleKeyPress(key);
    });
    // Use touchstart for lower latency
    btn.addEventListener('touchstart', function(e) {
      e.preventDefault();
      const key = this.dataset.key;
      handleKeyPress(key);
    }, { passive: false });
  });

  // Physical keyboard / USB wedge scanner support
  document.addEventListener('keydown', function(e) {
    // Ignore if modal is open
    if ($('.touch-modal.show')) {
      if (e.key === 'Escape') handleGlobalEscape();
      return;
    }
    // Printable character
    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      handleKeyPress(e.key.toLowerCase());
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      handleKeyPress('enter');
      return;
    }
    if (e.key === 'Backspace') {
      e.preventDefault();
      handleKeyPress('backspace');
      return;
    }
    if (e.key === 'Escape') {
      handleGlobalEscape();
      return;
    }
  });
}

function handleKeyPress(key) {
  const now = Date.now();

  // Devolucion mode: keyboard types ticket #, not product search
  if (currentMode === 'devolucion') {
    if (returnMode === 'ticket' && !returnSaleData) {
      if (key === 'enter') {
        lookupReturnSale();
        return;
      }
      if (key === 'backspace') {
        const input = $('#return-ticket-input');
        if (input) {
          input.value = input.value.slice(0, -1);
          input.focus();
        }
        return;
      }
      if (key === 'clear') {
        const input = $('#return-ticket-input');
        if (input) { input.value = ''; input.focus(); }
        return;
      }
      if (key.length === 1) {
        const input = $('#return-ticket-input');
        if (input) {
          input.value += key;
          input.focus();
        }
        return;
      }
      return;
    }
    // Noticket mode or already loaded: fall through to normal search
  }

  // Space always goes to search, never barcode buffer
  if (key === ' ') {
    if (keyboardMode === 'search') handleSearchKey(key);
    else handleQuantityKey(key);
    return;
  }

  // Barcode detection: rapid keystrokes (USB wedge scanner)
  if (key.length === 1 && barcodeBufTimer > 0 && now - barcodeBufTimer < 100) {
    barcodeBuf += key;
    barcodeBufTimer = now;
    return;
  }
  if (key === 'enter' && barcodeBuf.length >= 5) {
    const code = barcodeBuf;
    barcodeBuf = '';
    barcodeBufTimer = 0;
    clearSearch();
    lookupBarcode(code);
    return;
  }

  // Start tracking a potential barcode scan
  if (key.length === 1 && now - lastKbKeyTime > 200) {
    barcodeBuf = key;
    barcodeBufTimer = now;
  } else {
    barcodeBuf = '';
    barcodeBufTimer = 0;
  }

  // Physical keyboard rate limiting (for USB wedge scanners)
  if (now - lastKbKeyTime < 20) return;
  lastKbKeyTime = now;

  if (keyboardMode === 'search') {
    handleSearchKey(key);
  } else {
    handleQuantityKey(key);
  }
}

function handleSearchKey(key) {
  if (key === 'backspace') {
    searchQuery = searchQuery.slice(0, -1);
    updateSearchInput();
    if (searchQuery.length >= 2) {
      debouncedSearch(searchQuery);
    } else {
      clearSearchResults();
    }
    return;
  }
  if (key === 'clear') {
    clearSearch();
    return;
  }
  if (key === 'enter') {
    if (searchQuery.length >= 1) {
      fetchSearchResults(searchQuery);
    }
    return;
  }
  // Append character (lowercase already)
  searchQuery += key;
  updateSearchInput();
  if (searchQuery.length >= 2) {
    debouncedSearch(searchQuery);
  }
}

function handleQuantityKey(key) {
  if (key === 'backspace') {
    qtyValue = qtyValue.length > 1 ? qtyValue.slice(0, -1) : '1';
    updateQtyDisplay();
    return;
  }
  if (key === 'clear') {
    qtyValue = '1';
    updateQtyDisplay();
    return;
  }
  if (key === 'enter') {
    addSelectedToCart();
    return;
  }
  // Only allow digits
  if (key >= '0' && key <= '9') {
    const newVal = qtyValue === '1' ? key : qtyValue + key;
    qtyValue = newVal.replace(/^0+/, '') || '1';
    updateQtyDisplay();
  }
}

function updateSearchInput() {
  const input = $('#search-input');
  input.value = searchQuery;
  const clearBtn = $('#search-clear');
  clearBtn.style.display = searchQuery.length > 0 ? 'flex' : 'none';
}

function updateQtyDisplay() {
  $('#kb-qty-value').textContent = qtyValue;
  // Update selected product qty display in list
  const selItem = $('.pl-item.selected .pl-item-qty-value');
  if (selItem) selItem.textContent = qtyValue;
}

function debouncedSearch(q) {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => fetchSearchResults(q), 150);
}

function setKeyboardMode(mode) {
  keyboardMode = mode;
  updateKeyboardUI();
}

function updateKeyboardUI() {
  const label = $('#kb-mode-label');
  const qtyDisplay = $('#kb-qty-display');
  if (keyboardMode === 'quantity') {
    label.textContent = '✏️ Cantidad para: ' + (selectedProductData?.compose_name || selectedProductData?.name || '');
    label.className = 'kb-mode-label qty-mode';
    qtyDisplay.style.display = 'inline-flex';
    $('#kb-qty-value').textContent = qtyValue;
  } else {
    label.textContent = searchQuery ? '🔍 ' + searchQuery : '🔍 Buscar producto...';
    label.className = 'kb-mode-label search-mode';
    qtyDisplay.style.display = 'none';
  }
}

// ==================== KEYBOARD TOGGLE ====================
function toggleKeyboard() {
  keyboardVisible = !keyboardVisible;
  const panel = $('#bottom-panel');
  const toggle = $('#kb-toggle');
  if (keyboardVisible) {
    panel.classList.remove('keyboard-hidden');
    toggle.textContent = '🔽';
  } else {
    panel.classList.add('keyboard-hidden');
    toggle.textContent = '🔼';
  }
}

// ==================== SEARCH & PRODUCTS LIST ====================
function initSearch() {
  const clearBtn = $('#search-clear');
  clearBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    clearSearch();
  });
  // Tapping the search bar clears product selection and goes back to search mode
  const searchBar = $('#search-bar');
  searchBar.addEventListener('click', function(e) {
    if (e.target.closest('.search-bar-clear')) return;
    if (selectedProductId) {
      clearSelection();
    }
  });
}

function fetchSearchResults(q) {
  fetch('/pos/search/?q=' + encodeURIComponent(q))
    .then(r => r.json())
    .then(items => {
      if (!items || !items.length) {
        renderNoResults();
        return;
      }
      renderSearchResults(items);
    })
    .catch(() => renderNoResults());
}

function renderSearchResults(items) {
  const container = $('#products-list');
  const idle = $('#pl-idle');
  if (idle) idle.style.display = 'none';
  container.innerHTML = '';
  items.forEach(p => {
    const div = document.createElement('div');
    div.className = 'pl-item' + (p.Granel_Item ? ' granel' : '');
    div.dataset.id = p.id;
    div.dataset.barcode = p.barcode || '';
    div.dataset.name = p.compose_name || p.name;
    div.dataset.price = p.price || 0;
    div.dataset.price_mayoreo = p.price_mayoreo || 0;
    div.dataset.stock = p.stock || 0;
    div.dataset.granel = p.Granel_Item || false;
    div.dataset.despiece_config_id = p.despiece_config_id || '';
    div.dataset.despiece_source_name = p.despiece_source_name || '';
    div.dataset.despiece_source_id = p.despiece_source_id || '';
    div.dataset.despiece_source_stock = p.despiece_source_stock || 0;
    div.dataset.despiece_units_per = p.despiece_units_per || 0;

    const price = parseFloat(p.price) || 0;
    const mayoreo = parseFloat(p.price_mayoreo) || 0;
    const isSelected = String(p.id) === selectedProductId;

    let qtyHtml = '';
    if (isSelected) {
      qtyHtml = '<div class="pl-item-qty-wrap"><span class="qty-icon">✏️</span><span class="qty-value pl-item-qty-value">' + qtyValue + '</span></div>';
    }

    const despieceBtn = p.despiece_config_id
      ? '<button class="pl-item-despiece" data-despiece=\'' + JSON.stringify({
          configId: p.despiece_config_id,
          sourceName: p.despiece_source_name,
          sourceStock: p.despiece_source_stock,
          unitsPer: p.despiece_units_per,
        }) + '\'>📦→</button>'
      : '';

    const granelTag = p.Granel_Item ? '<span class="pl-item-meta-badge granel">📦 Granel</span>' : '';

    div.innerHTML =
      '<div class="pl-item-info">' +
        '<div class="pl-item-name">' + (p.compose_name || p.name) + '</div>' +
        '<div class="pl-item-meta">' +
          (p.clave ? '<span class="pl-item-clave">' + p.clave + '</span>' : '') +
          granelTag +
          (mayoreo > 0 && mayoreo !== price ? '<span class="pl-item-mayoreo">May: $' + mayoreo.toFixed(2) + '</span>' : '') +
          '<span class="pl-item-stock' + (p.stock <= 0 ? ' out' : '') + '">' +
            (p.stock > 0 ? p.stock + ' pz' : 'Agotado') +
          '</span>' +
        '</div>' +
      '</div>' +
      despieceBtn +
      '<div class="pl-item-price">$' + price.toFixed(2) + '</div>' +
      qtyHtml;

    // Despiece button handler
    const dpBtn = div.querySelector('.pl-item-despiece');
    if (dpBtn) {
      dpBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        const config = JSON.parse(this.dataset.despiece);
        openDespieceModal(config);
      });
    }

    if (isSelected) div.classList.add('selected');

    div.addEventListener('click', function() {
      const productData = {
        id: parseInt(this.dataset.id),
        barcode: this.dataset.barcode,
        name: this.dataset.name,
        compose_name: this.dataset.name,
        price: parseFloat(this.dataset.price),
        price_mayoreo: parseFloat(this.dataset.price_mayoreo),
        stock: parseInt(this.dataset.stock),
        granel: this.dataset.granel === 'true',
        Granel_Item: this.dataset.granel === 'true',
        despiece_config_id: this.dataset.despiece_config_id || null,
        despiece_source_name: this.dataset.despiece_source_name || null,
        despiece_source_id: this.dataset.despiece_source_id || null,
        despiece_source_stock: this.dataset.despiece_source_stock || null,
        despiece_units_per: this.dataset.despiece_units_per || null,
      };
      selectProduct(productData);
    });

    container.appendChild(div);
  });
}

function renderNoResults() {
  const container = $('#products-list');
  container.innerHTML =
    '<div class="pl-idle">' +
      '<div class="pl-idle-icon" style="font-size:36px;">🔍</div>' +
      '<div>Sin resultados para "<strong>' + searchQuery + '</strong>"</div>' +
      '<div class="pl-idle-sub">Prueba con otro nombre o código</div>' +
    '</div>';
}

function clearSearchResults() {
  const container = $('#products-list');
  const idle = $('#pl-idle');
  if (searchQuery.length > 0) {
    container.innerHTML =
      '<div class="pl-idle">' +
        '<div class="pl-idle-icon" style="font-size:36px;">🔍</div>' +
        '<div>Escribe al menos 2 caracteres</div>' +
      '</div>';
  } else {
    if (idle) idle.style.display = 'flex';
    container.innerHTML = '';
    if (idle) container.appendChild(idle);
  }
}

function clearSearch() {
  searchQuery = '';
  selectedProductId = null;
  selectedProductData = null;
  qtyValue = '1';
  setKeyboardMode('search');
  updateSearchInput();
  clearSearchResults();
}

// ==================== PRODUCT SELECTION (double-tap to add) ====================
function selectProduct(productData) {
  const pid = String(productData.id);

  if (selectedProductId === pid) {
    // Double-tap on same product → add to cart
    addSelectedToCart();
    return;
  }

  // Single tap → select this product, switch to quantity mode
  selectedProductId = pid;
  selectedProductData = productData;
  qtyValue = '1';

  setKeyboardMode('quantity');
  updateProductHighlight();
  updateQtyDisplay();
}

function autoStartSale() {
  if (saleStarted) return;
  saleType = 'menudeo';
  clientId = null;
  clientName = 'General';
  clientWallet = 0;
  activateSale();
}

function activateSale() {
  saleStarted = true;
  updateSaleTypeDisplay();
  syncCartToSession();
  broadcastToDisplay('sale_started');
  renderCart();
}

function addSelectedToCart() {
  if (!selectedProductData) return;
  if (!saleStarted) autoStartSale();
  const qty = parseInt(qtyValue) || 1;
  addScannedToCart(selectedProductData, qty);
  clearSelection();
  playBeep('ok');
}

function clearSelection() {
  selectedProductId = null;
  selectedProductData = null;
  qtyValue = '1';
  setKeyboardMode('search');
  updateProductHighlight();
}

function updateProductHighlight() {
  const items = $$('.pl-item');
  items.forEach(el => {
    const pid = String(el.dataset.id);
    const isSelected = pid === selectedProductId;
    el.classList.toggle('selected', isSelected);
    // Update qty display in item
    let qtyWrap = el.querySelector('.pl-item-qty-wrap');
    if (isSelected) {
      if (!qtyWrap) {
        qtyWrap = document.createElement('div');
        qtyWrap.className = 'pl-item-qty-wrap';
        qtyWrap.innerHTML = '<span class="qty-icon">✏️</span><span class="qty-value pl-item-qty-value">' + qtyValue + '</span>';
        el.appendChild(qtyWrap);
      }
    } else {
      if (qtyWrap) qtyWrap.remove();
    }
  });
}

// ==================== SCANNER LOOKUP ====================
function lookupBarcode(code) {
  // Debounce duplicate scans
  const now = Date.now();
  if (code === lastScannedCode && now - lastScannedTime < scanDebounceMs) return;
  lastScannedCode = code;
  lastScannedTime = now;

  fetch('/pos/scan/?q=' + encodeURIComponent(code))
    .then(r => r.json().catch(() => null))
    .then(data => {
      if (!data || data.error) {
        playBeep('fail');
        showToast('Código no encontrado: ' + code, 'error');
        return;
      }
      playBeep('ok');
      navigator.vibrate && navigator.vibrate(30);

      if (saleStarted) {
        // Scanner: auto-add to cart with qty 1 (fast path)
        addScannedToCart(data, 1);
        showToast('✓ ' + code, 'success');
      } else {
        // No sale: just show info in search area
        searchQuery = code;
        updateSearchInput();
        fetchSearchResults(searchQuery);
      }
    })
    .catch(() => showToast('Error al buscar código', 'error'));
}

// ==================== ADD TO CART ====================
function addScannedToCart(product, qty) {
  if (!saleStarted) { showToast('Start a sale first', 'warning'); return; }
  // Stock check (skip for granel/despiece, skip for returns)
  if (currentMode !== 'devolucion' && qty > product.stock && !product.Granel_Item && !product.despiece_config_id) {
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
      is_return: currentMode === 'devolucion',
    };
  }
  lastAddedId = pid;
  renderCart();
  syncCartToSession();
}

// ==================== CART RENDER ====================
function renderCart() {
  const container = $('#cart-items');
  const keys = Object.keys(cart);

  // Update count
  let totalItems = 0;
  Object.values(cart).forEach(item => { totalItems += item.qty; });
  $('#cart-count').textContent = totalItems;

  // Show/hide sections
  if (keys.length === 0) {
    container.innerHTML = '<div class="empty-cart">🛒 Carrito vacío</div>';
    $('#cart-totals').style.display = 'none';
    $('#cart-actions').style.display = 'none';
    return;
  }

  $('#cart-totals').style.display = 'block';
  $('#cart-actions').style.display = 'flex';

  const entries = Object.values(cart).sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));
  container.innerHTML = '';

  entries.forEach(item => {
    const div = document.createElement('div');
    div.className = 'cart-item' + (item.id === lastAddedId ? ' highlight' : '') + (item.is_return ? ' return-item' : '');
    div.dataset.pid = item.id;
    const lineTotal = (item.qty * item.price).toFixed(2);
    const label = item.is_return ? '<span style="color:#c0392b;font-size:10px;font-weight:700;margin-right:4px;">DEVOLUCIÓN</span>' : '';

    div.innerHTML =
      '<div class="item-row-top">' +
        '<div class="item-name">' + label + item.name + '</div>' +
        '<button class="item-remove">✕</button>' +
      '</div>' +
      '<div class="item-row-bottom">' +
        '<div class="item-qty-controls">' +
          '<button class="qty-btn" data-delta="-1">−</button>' +
          '<span class="item-qty-value">' + item.qty + '</span>' +
          '<button class="qty-btn" data-delta="1">+</button>' +
        '</div>' +
        '<div class="item-price">$' + lineTotal + '</div>' +
      '</div>';

    div.querySelector('.item-remove').addEventListener('click', function(e) {
      e.stopPropagation();
      removeFromCart(item.id);
    });
    div.querySelectorAll('.qty-btn').forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        const delta = parseInt(this.dataset.delta);
        updateCartQty(item.id, delta);
      });
    });

    container.appendChild(div);
  });

  updateCartTotal();
}

function updateCartTotal() {
  let total = 0;
  Object.values(cart).forEach(item => { total += item.qty * item.price; });
  $('#cart-total-amount').textContent = '$' + total.toFixed(2);
}

function updateCartQty(pid, delta) {
  if (!cart[pid]) return;
  cart[pid].qty += delta;
  if (cart[pid].qty <= 0) {
    delete cart[pid];
  }
  renderCart();
  syncCartToSession();
}

function removeFromCart(pid) {
  delete cart[pid];
  if (lastAddedId === pid) lastAddedId = null;
  renderCart();
  syncCartToSession();
}

function clearCart() {
  if (Object.keys(cart).length === 0) return;
  showConfirm('Clear entire cart?', () => {
    cart = {};
    lastAddedId = null;
    renderCart();
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
  closeSettings();
  activateSale();
}

function updateSaleTypeDisplay() {
  $('#sale-type-display').textContent = saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo';
  $('#client-display').textContent = clientName || 'General';
}

// ==================== MODE SWITCHING ====================
function setMode(mode) {
  currentMode = mode;
  returnMode = null;
  returnSaleData = null;
  document.body.className = document.body.className.replace(/mode-\w+/g, '').trim() + ' mode-' + mode;
  $$('.mode-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));

  // Clear product search
  clearSearch();
  searchQuery = '';
  updateSearchInput();

  const checkoutBtn = $('#checkout-btn');
  if (mode === 'devolucion') {
    if (checkoutBtn) checkoutBtn.textContent = '🔄 DEVOLVER';
    showReturnChoice();
  } else if (mode === 'cotizacion') {
    if (checkoutBtn) checkoutBtn.textContent = '📄 COTIZAR';
    hideReturnLookup();
    hideReturnChoice();
    enableProductSearch();
  } else {
    if (checkoutBtn) checkoutBtn.textContent = '💳 COBRAR';
    hideReturnLookup();
    hideReturnChoice();
    enableProductSearch();
    returnSaleData = null;
  }
}

function showReturnChoice() {
  hideReturnLookup();
  hideReturnChoice();
  const pl = $('#products-list');
  if (!pl) return;
  const div = document.createElement('div');
  div.id = 'return-choice';
  div.style.cssText = 'padding:20px;text-align:center;';
  div.innerHTML =
    '<div style="font-size:16px;font-weight:700;color:#c0392b;margin-bottom:16px;">🔙 MODO DEVOLUCIÓN</div>' +
    '<div style="display:flex;gap:12px;justify-content:center;">' +
    '<button class="modal-btn primary" onclick="startReturnWithTicket()" style="background:#c0392b;font-size:16px;padding:14px 28px;">🎫 Con Ticket</button>' +
    '<button class="modal-btn primary" onclick="startReturnWithoutTicket()" style="background:#c0392b;font-size:16px;padding:14px 28px;">📦 Sin Ticket</button>' +
    '</div>' +
    '<div style="margin-top:10px;font-size:13px;color:#888;">Con ticket: busca la venta original · Sin ticket: selecciona productos directamente</div>';
  pl.parentNode.insertBefore(div, pl);
  const idle = $('#pl-idle');
  if (idle) idle.style.display = 'none';
  clearSearchResults();
}

function hideReturnChoice() {
  const el = $('#return-choice');
  if (el) el.remove();
}

function startReturnWithTicket() {
  returnMode = 'ticket';
  hideReturnChoice();
  showReturnLookup();
}

function startReturnWithoutTicket() {
  returnMode = 'noticket';
  hideReturnChoice();
  hideReturnLookup();
  enableProductSearch();
  showToast('Selecciona productos a devolver', 'info');
}

function enableProductSearch() {
  const idle = $('#pl-idle');
  if (idle) idle.style.display = 'flex';
  hideReturnModeMessage();
  hideReturnChoice();
  hideReturnLookup();
  const inp = $('#search-input');
  if (inp) inp.focus();
}

function showReturnLookup() {
  const cartContainer = $('#cart-items');
  if (!cartContainer) return;
  if ($('#return-lookup')) {
    const inp = $('#return-ticket-input');
    if (inp) inp.focus();
    return;
  }
  const div = document.createElement('div');
  div.id = 'return-lookup';
  div.className = 'return-lookup';
  div.innerHTML = '<input type="text" id="return-ticket-input" placeholder="Ticket # original..." autocomplete="off">' +
    '<button onclick="lookupReturnSale()">🔍 Buscar</button>';
  cartContainer.parentNode.insertBefore(div, cartContainer);

  // Show message in products area
  showReturnModeMessage();

  // Focus the input
  setTimeout(() => {
    const inp = $('#return-ticket-input');
    if (inp) inp.focus();
  }, 100);
}

function showReturnModeMessage() {
  const pl = $('#products-list');
  if (!pl) return;
  const existing = $('#return-mode-msg');
  if (existing) return;
  const msg = document.createElement('div');
  msg.id = 'return-mode-msg';
  msg.style.cssText = 'padding:20px;text-align:center;color:#c0392b;font-size:18px;font-weight:700;';
  msg.textContent = '🔙 MODO DEVOLUCIÓN — Ingresa el # de ticket para buscar la venta original';
  pl.parentNode.insertBefore(msg, pl);
  const idle = $('#pl-idle');
  if (idle) idle.style.display = 'none';
  clearSearchResults();
}

function hideReturnModeMessage() {
  const msg = $('#return-mode-msg');
  if (msg) msg.remove();
}

function hideReturnLookup() {
  const el = $('#return-lookup');
  if (el) el.remove();
  const items = $$('.return-item-row');
  items.forEach(el => el.remove());
  const addBtn = $$('.return-add-btn-container');
  addBtn.forEach(el => el.remove());
  hideReturnModeMessage();
  const idle = $('#pl-idle');
  if (idle) idle.style.display = 'flex';
}

function lookupReturnSale() {
  const saleId = $('#return-ticket-input').value.trim();
  if (!saleId || isNaN(saleId)) { showToast('Enter a valid ticket number', 'warning'); return; }
  showLoading(true);
  fetch('/pos/get-sale-for-return/' + saleId + '/')
    .then(r => r.json())
    .then(data => {
      showLoading(false);
      if (data.error) { showToast(data.error, 'error'); return; }
      returnSaleData = data;
      $('#return-mode-msg').textContent = '✅ Venta #' + data.sale_id + ' cargada — Selecciona productos a devolver';
      showReturnItems(data);
    })
    .catch(() => { showLoading(false); showToast('Sale not found', 'error'); });
}

function showReturnItems(data) {
  // Remove old rows
  $$('.return-item-row').forEach(el => el.remove());
  const cartContainer = $('#cart-items');
  data.items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'return-item-row';
    row.innerHTML = '<input type="checkbox" class="return-chk" data-sale-item-id="' + item.sale_item_id + '" checked>' +
      '<span style="flex:1;">' + item.name + '</span>' +
      '<span style="color:#888;font-size:11px;margin-right:4px;">SAT:' + (item.sat ? 'Sí' : 'No') + '</span>' +
      '<input type="number" class="return-qty" value="' + item.quantity + '" min="1" max="' + item.quantity + '" style="width:50px;">' +
      '<span style="margin-left:4px;">$' + item.price.toFixed(2) + '</span>';
    cartContainer.appendChild(row);
  });
  // Add "Add selected to return" button
  const btn = document.createElement('div');
  btn.style = 'padding:8px;text-align:center;';
  btn.innerHTML = '<button class="modal-btn primary" onclick="addSelectedReturns()" style="background:#c0392b;">➕ Agregar seleccionados a devolución</button>';
  cartContainer.appendChild(btn);
}

function addSelectedReturns() {
  const checkboxes = $$('.return-chk:checked');
  if (checkboxes.length === 0) { showToast('Select items to return', 'warning'); return; }
  checkboxes.forEach(chk => {
    const saleItemId = chk.dataset.saleItemId;
    const row = chk.closest('.return-item-row');
    const qtyInput = row.querySelector('.return-qty');
    const qty = parseInt(qtyInput.value) || 1;
    const item = returnSaleData.items.find(i => i.sale_item_id == saleItemId);
    if (!item) return;
    // Add to cart as return item
    const pid = item.product_id;
    if (cart[pid]) {
      cart[pid].qty += qty;
    } else {
      cart[pid] = { id: pid, qty: qty, price: item.price, name: item.name, is_return: true, sale_item_id: saleItemId, sat: item.sat };
    }
  });
  showToast(checkboxes.length + ' item(s) added to return', 'success');
  renderCart();
  hideReturnLookup();
}

// ==================== CHECKOUT ====================
function proceedCheckout() {
  if (Object.keys(cart).length === 0) { showToast('Cart is empty', 'warning'); return; }
  // Skip stock validation for devolucion and cotizacion
  if (currentMode !== 'sale') {
    openCheckoutModal();
    return;
  }
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
  const titles = { sale: '💳 Cobrar', devolucion: '🔄 Devolución', cotizacion: '📄 Cotización' };
  const titleEl = $('#chk-mode-title');
  if (titleEl) titleEl.textContent = titles[currentMode] || '💳 Cobrar';
  $('#chk-total').textContent = '$' + totalAmount.toFixed(2);
  window.currentTotal = totalAmount;

  // Show/hide payment section based on mode
  const pmSection = $('.pm-section');
  if (pmSection) pmSection.style.display = (currentMode === 'sale') ? 'block' : 'none';
  const cashArea = $('#cash-payment-area');
  if (cashArea) cashArea.style.display = 'none';

  if (currentMode !== 'sale') {
    // Hide payment methods, show confirm button with mode label
    $$('.payment-methods').forEach(el => el.style.display = 'none');
    const confirmBtn = $('.modal-actions .primary');
    if (currentMode === 'devolucion') confirmBtn.textContent = '🔄 Devolver';
    else if (currentMode === 'cotizacion') confirmBtn.textContent = '📄 Cotizar';
    else confirmBtn.textContent = '💳 Cobrar';
    return;
  }

  $$('.payment-methods').forEach(el => el.style.display = '');
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
  const totalAmount = window.currentTotal;

  if (currentMode === 'sale') {
    const paymentMethod = window.selectedPayment || 'cash';
    if (paymentMethod === 'cash') {
      const cashText = $('#cash-amount-display').textContent.replace('$', '');
      const cashAmount = parseFloat(cashText) || 0;
      if (cashAmount <= 0) { showToast('Enter the cash amount received', 'warning'); return; }
      if (cashAmount < totalAmount) {
        showToast('Insufficient payment! Need $' + (totalAmount - cashAmount).toFixed(2) + ' more', 'error');
        return;
      }
    }
  }

  const items = Object.values(cart).map(item => ({
    product_id: item.id,
    quantity: item.qty,
    price: item.price,
    sale_item_id: item.sale_item_id || null,
    sat: item.sat || false,
  }));

  const saleData = {
    items,
    tipo: saleType,
    client_id: clientId || null,
    total_amount: totalAmount,
    mode: currentMode,
  };

  if (currentMode === 'sale') {
    saleData.payment_method = window.selectedPayment || 'cash';
  }
  if (currentMode === 'devolucion' && returnSaleData) {
    saleData.original_sale_id = returnSaleData.sale_id;
  }

  showLoading(true);
  fetch('/pos/complete-sale/', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(saleData),
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (data.success) {
      const labels = { sale: 'Sale', devolucion: 'Devolución', cotizacion: 'Cotización' };
      const label = labels[currentMode] || 'Sale';
      showToast('✅ ' + label + ' #' + data.sale_id + ' completed! $' + data.total, 'success');
      window.lastSaleId = data.sale_id;
      $('#print-sale-info').textContent = label + ' #' + data.sale_id + ' — Total: $' + data.total.toFixed(2);
      $('#print-modal').classList.add('show');
    } else { showToast('Error: ' + data.error, 'error'); }
  })
  .catch(() => { showLoading(false); showToast('Failed to complete ' + currentMode, 'error'); });
}

function finishSale() {
  clearCheckoutState();
  syncCartToSession({ saleCompleted: { message: 'Gracias por su compra', timestamp: Date.now() / 1000 } })
    .then(() => { closeCheckout(); broadcastToDisplay('sale_completed'); setTimeout(() => location.reload(), 300); });
}

function doPrintTicket() {
  $('#print-modal').classList.remove('show');
  showToast('🖶 Printing ticket...', 'success');
  const ticketTypeMap = { sale: 'sale', devolucion: 'devolution', cotizacion: 'quote' };
  const ticketType = ticketTypeMap[currentMode] || 'sale';
  fetch('/pos/queue-print/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sale_id: window.lastSaleId, ticket_type: ticketType})
  }).finally(() => finishSale());
}

function skipPrint() {
  $('#print-modal').classList.remove('show');
  finishSale();
}

// ==================== DESPIECE ====================
function openDespieceModal(config) {
  currentDespieceConfig = {
    configId: config.configId || config.despieceConfigId,
    sourceName: config.sourceName || config.despieceSourceName || '',
    sourceStock: parseInt(config.sourceStock || config.despieceSourceStock) || 0,
    unitsPer: parseFloat(config.unitsPer || config.despieceUnitsPer) || 1,
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

// ==================== GLOBAL ESCAPE ====================
function handleGlobalEscape() {
  if ($('#print-modal.show')) { $('#print-modal').classList.remove('show'); return; }
  if ($('#confirm-modal.show')) { $('#confirm-modal').classList.remove('show'); return; }
  if ($('#despiece-modal.show')) { closeDespieceModal(); return; }
  if ($('#checkout-modal.show')) { closeCheckout(); return; }
  if ($('#settings-modal.show')) { closeSettings(); return; }
  if ($('#display-modal.show')) { closeDisplayLink(); return; }
  if (selectedProductId) { clearSelection(); return; }
  if (searchQuery) { clearSearch(); return; }
}

// ==================== SCANNER POLLING ====================
function initScannerPoll() {
  if (!scannerConnected) return;
  if (scannerPollTimer) clearInterval(scannerPollTimer);
  scannerPollTimer = setInterval(function() {
    fetch('/pos/scanner-poll/')
      .then(r => r.json())
      .then(data => {
        if (data && data.barcode) {
          lookupBarcode(data.barcode);
        }
      })
      .catch(function() {});
  }, 1000);
}

function toggleScannerConnection() {
  scannerConnected = !scannerConnected;
  const btn = $('#scanner-toggle');
  if (scannerConnected) {
    btn.innerHTML = '🔗';
    btn.style.opacity = '1';
    initScannerPoll();
  } else {
    btn.innerHTML = '🔌';
    btn.style.opacity = '0.5';
    if (scannerPollTimer) {
      clearInterval(scannerPollTimer);
      scannerPollTimer = null;
    }
  }
}

// ==================== FULLSCREEN ====================
function toggleFullscreen() {
  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    const el = document.documentElement;
    if (el.requestFullscreen) {
      el.requestFullscreen();
    } else if (el.webkitRequestFullscreen) {
      el.webkitRequestFullscreen();
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    }
  }
}

document.addEventListener('fullscreenchange', updateFullscreenIcon);
document.addEventListener('webkitfullscreenchange', updateFullscreenIcon);
function updateFullscreenIcon() {
  const btn = $('#fullscreen-btn');
  if (!btn) return;
  btn.textContent = !!(document.fullscreenElement || document.webkitFullscreenElement) ? '⛶' : '⛶';
}

// ==================== MAYOREO TOGGLE ====================
function initMayoreoButton() {
  const btn = $('#toggleMayoreoBtn');
  if (!btn) return;

  function syncMayoreo() {
    btn.textContent = saleType === 'mayoreo' ? '💰 Menudeo' : '💰 Mayoreo';
  }
  function toggleMayoreo() {
    saleType = saleType === 'mayoreo' ? 'menudeo' : 'mayoreo';
    if (saleStarted) updateSaleTypeDisplay();
    syncMayoreo();
    syncCartToSession();
    showToast('Modo: ' + (saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo'), 'info');
  }
  btn.addEventListener('click', toggleMayoreo);
}

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', function() {
  sessionKey = DISPLAY_SESSION_KEY;

  // Init keyboard
  initKeyboard();

  // Init search
  initSearch();

  // Init scanner polling
  initScannerPoll();

  // Init mayoreo toggle button
  initMayoreoButton();

  // Init mode buttons
  $$('.mode-btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      setMode(this.dataset.mode);
    });
  });

  // Init audio on user interaction
  document.addEventListener('click', initBeeps);
  document.addEventListener('touchstart', initBeeps);

  // Show idle state
  const idle = $('#pl-idle');
  if (idle) idle.style.display = 'flex';

  // Cart always visible, render empty state
  renderCart();

  // Enter fullscreen by default
  const el = document.documentElement;
  if (el.requestFullscreen) {
    el.requestFullscreen();
  } else if (el.webkitRequestFullscreen) {
    el.webkitRequestFullscreen();
  }
});
