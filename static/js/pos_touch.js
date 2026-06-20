/**
 * TOUCH-OPTIMIZED POS - Client-side Logic
 * For 10" tablet (1280x800) touch screen
 * Reuses all backend endpoints from the main POS
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

// Broadcast channel for customer display
let posChannel = null;
try {
  posChannel = new BroadcastChannel('pos-display');
} catch(e) {}
function broadcastToDisplay(msg) {
  if (posChannel) posChannel.postMessage(msg);
}

// --- SESSION SYNC (same as desktop POS, reuses same endpoints) ---
function syncCartToSession(extra) {
  const payload = {
    cart: cart,
    saleType: saleType,
    clientId: clientId,
    clientName: clientName,
    clientWallet: clientWallet,
    saleStarted: saleStarted,
    ...(extra || {}),
  };
  return fetch('/pos/cart/save/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }).then(r => {
    if (!r.ok) console.error('Cart sync failed:', r.status);
    return r;
  }).catch(err => console.error('Cart sync error:', err));
}

function syncCheckoutState(state) {
  fetch('/pos/checkout/save/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(state),
  }).catch(err => console.error('Checkout sync error:', err));
}

function clearCheckoutState() {
  fetch('/pos/checkout/clear/', {method: 'POST'})
    .catch(err => console.error('Checkout clear error:', err));
}

// --- DOM REFS ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// --- CARD EVENT HANDLERS ---
function attachCardHandlers(card) {
  const addBtn = card.querySelector('.card-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const qtyInput = card.querySelector('.card-qty');
      const qty = parseInt(qtyInput?.value) || 1;
      addToCart(card.dataset.productId, qty, card);
    });
  }

  card.addEventListener('click', (e) => {
    if (e.target.closest('.card-qty-row') || e.target.closest('.card-badge')) return;
    addToCart(card.dataset.productId, 1, card);
  });
}

// --- INIT ---
document.addEventListener('DOMContentLoaded', function() {
  sessionKey = DISPLAY_SESSION_KEY;
  updateCartDisplay();

  // Attach handlers to server-rendered cards
  $$('.product-card').forEach(attachCardHandlers);

  // Search
  const searchInput = $('#search-input');
  searchInput.addEventListener('input', handleSearchInput);
  searchInput.addEventListener('keypress', handleSearchKeypress);
  $('#search-clear').addEventListener('click', clearSearch);

  // Mayoreo toggle
  $('#toggleMayoreoBtn').addEventListener('click', toggleMayoreo);
  applyMayoreoVisibility();
});

// --- SEARCH ---
let searchTimer = null;

function handleSearchInput(e) {
  if (searchTimer) clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2) {
    searchTimer = setTimeout(() => {
      if (q.length === 0) reloadProducts();
    }, 200);
    return;
  }
  searchTimer = setTimeout(() => searchProducts(q), 150);
}

function handleSearchKeypress(e) {
  if (e.key === 'Enter') {
    const q = e.target.value.trim();
    if (q.length < 2) return;
    if (searchTimer) clearTimeout(searchTimer);
    searchProducts(q);
  }
}

function clearSearch() {
  $('#search-input').value = '';
  reloadProducts();
  $('#search-input').focus();
}

function searchProducts(query) {
  fetch(`/pos/search/?q=${encodeURIComponent(query)}`)
    .then(r => r.json())
    .then(products => renderProductGrid(products))
    .catch(err => console.error('Search error:', err));
}

function reloadProducts() {
  fetch('/pos/')
    .then(r => r.text())
    .then(html => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const rows = doc.querySelectorAll('tbody tr');
      const products = [];
      rows.forEach(row => {
        const td = (i) => row.cells[i]?.textContent.trim() || '';
        products.push({
          id: row.dataset.productId,
          barcode: td(0),
          compose_name: td(1).replace(/GRANEL.*/, '').trim(),
          stock: parseInt(td(2)) || 0,
          price: parseFloat(td(3).replace('$', '')) || 0,
          price_mayoreo: parseFloat(td(4).replace('$', '')) || 0,
          Granel_Item: row.classList.contains('row-granel'),
          price_granel: row.dataset.priceGranel,
          minimo: row.dataset.minimo,
        });
      });
      renderProductGrid(products);
    })
    .catch(err => console.error('Reload error:', err));
}

// --- RENDER PRODUCT GRID ---
function renderProductGrid(products) {
  const grid = $('#products-grid');
  grid.innerHTML = '';

  if (!products || products.length === 0) {
    grid.innerHTML = '<div class="no-results"><div style="font-size:48px;margin-bottom:12px;">🔍</div>No products found</div>';
    return;
  }

  // Update count
  $('#product-count').textContent = products.length;

  products.forEach(p => {
    const card = document.createElement('div');
    card.className = 'product-card' + (p.Granel_Item ? ' granel' : '');
    card.dataset.productId = p.id;
    card.dataset.priceRegular = p.price || 0;
    card.dataset.priceMayoreo = p.price_mayoreo || 0;
    card.dataset.priceGranel = p.price_granel || '';
    card.dataset.minimo = p.minimo || '';

    const stockClass = p.stock <= 0 ? 'out' : p.stock < 5 ? 'low' : '';
    const mayoreoDisplay = document.body.dataset.mayoreo === 'true' ? '' : 'display:none;';

    card.innerHTML = `
      ${p.Granel_Item ? '<span class="card-badge">GRANEL</span>' : ''}
      <div class="card-name">${p.compose_name || p.name}</div>
      <div class="card-details">
        <span class="card-price">$${(parseFloat(p.price) || 0).toFixed(2)}</span>
        <span class="card-price-mayoreo col-mayoreo" style="${mayoreoDisplay}">May: $${(parseFloat(p.price_mayoreo) || 0).toFixed(2)}</span>
        <span class="card-stock ${stockClass}">${p.stock > 0 ? p.stock + ' pz' : 'Agotado'}</span>
      </div>
      <div class="card-actions">
        <div class="card-qty-row">
          <input type="number" class="card-qty" value="1" min="1" inputmode="numeric" pattern="[0-9]*">
          <button class="card-add-btn" data-pid="${p.id}">+</button>
        </div>
      </div>
    `;

    attachCardHandlers(card);
    grid.appendChild(card);
  });

  applyMayoreoVisibility();
}

// --- ADD TO CART ---
function addToCart(productId, quantity, cardElement) {
  if (!saleStarted) {
    showToast('Please start a sale first', 'warning');
    openSettings();
    return;
  }

  const stockEl = cardElement?.querySelector('.card-stock');

  fetch(`/pos/stock/?id=${productId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        showToast('Product not found', 'error');
        return;
      }

      const backendStock = data.stock;

      // Update displayed stock
      if (stockEl) stockEl.textContent = backendStock + ' pz';

      if (quantity > backendStock) {
        showToast(`Only ${backendStock} in stock!`, 'error');
        return;
      }

      const currentQty = cart[productId] ? cart[productId].qty : 0;
      if (currentQty + quantity > backendStock) {
        showToast(`Only ${backendStock - currentQty} more available`, 'error');
        return;
      }

      // Get price from data attributes (server-side authoritative values)
      const priceRegular = parseFloat(cardElement?.dataset?.priceRegular) || 0;
      const priceMayoreo = parseFloat(cardElement?.dataset?.priceMayoreo) || 0;
      const price = saleType === 'mayoreo' ? priceMayoreo : priceRegular;

      if (cart[productId]) {
        cart[productId].qty += quantity;
      } else {
        const nameEl = cardElement?.querySelector('.card-name');
        const barcode = data.barcode || '';
        cart[productId] = {
          id: productId,
          barcode: barcode,
          name: nameEl?.textContent?.replace('GRANEL', '').trim() || data.compose_name || data.name,
          qty: quantity,
          price: price,
          tipo: saleType,
        };
      }
      cart[productId].addedAt = Date.now();
      lastAddedId = productId;

      updateCartDisplay();
      syncCartToSession();

      if (cardElement) {
        const qtyInput = cardElement.querySelector('.card-qty');
        if (qtyInput) qtyInput.value = 1;
      }

      showToast('Added to cart', 'success');
    })
    .catch(err => {
      console.error('Stock check error:', err);
      showToast('Failed to verify stock', 'error');
    });
}

// --- UPDATE CART DISPLAY ---
function updateCartDisplay() {
  const container = $('#cart-items');
  const countEl = $('#cart-count');
  let totalItems = 0;
  let totalAmount = 0;

  if (Object.keys(cart).length === 0) {
    container.innerHTML = '<div class="empty-cart">🛒 Cart is empty</div>';
    countEl.textContent = '0';
    $('#total-items').textContent = '0';
    $('#subtotal').textContent = '$0.00';
    $('#total').textContent = '$0.00';
    return;
  }

  container.innerHTML = '';

  const entries = Object.values(cart);
  const sorted = [...entries].sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));

  sorted.forEach(item => {
    const itemTotal = item.qty * item.price;
    totalItems += item.qty;
    totalAmount += itemTotal;

    const div = document.createElement('div');
    div.className = 'cart-item' + (item.id === lastAddedId ? ' highlight' : '');

    div.innerHTML = `
      <div class="item-row-top">
        <span class="item-name">${item.name}</span>
        <button class="item-remove" data-pid="${item.id}">✕</button>
      </div>
      <div class="item-row-bottom">
        <div class="item-qty-controls">
          <button class="qty-btn" data-pid="${item.id}" data-delta="-1">−</button>
          <span class="item-qty-value">${item.qty}</span>
          <button class="qty-btn" data-pid="${item.id}" data-delta="1">+</button>
        </div>
        <div class="item-price">
          <span class="unit-price">$${item.price.toFixed(2)} c/u</span>
          <strong>$${itemTotal.toFixed(2)}</strong>
        </div>
      </div>
    `;

    // Quantity buttons
    div.querySelectorAll('.qty-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const pid = btn.dataset.pid;
        const delta = parseInt(btn.dataset.delta);
        updateQty(pid, delta);
      });
    });

    // Remove
    div.querySelector('.item-remove').addEventListener('click', (e) => {
      e.stopPropagation();
      removeFromCart(item.id);
    });

    // Swipe to delete
    let startX = 0;
    div.addEventListener('touchstart', (e) => {
      startX = e.touches[0].clientX;
    }, {passive: true});
    div.addEventListener('touchend', (e) => {
      const endX = e.changedTouches[0].clientX;
      if (startX - endX > 80) {
        removeFromCart(item.id);
      }
    }, {passive: true});

    container.appendChild(div);
  });

  countEl.textContent = Object.keys(cart).length;
  $('#total-items').textContent = totalItems;
  $('#subtotal').textContent = '$' + totalAmount.toFixed(2);
  $('#total').textContent = '$' + totalAmount.toFixed(2);
}

// --- CART OPERATIONS ---
function updateQty(productId, delta) {
  if (!cart[productId]) return;
  cart[productId].qty += delta;
  if (cart[productId].qty <= 0) {
    delete cart[productId];
  }
  updateCartDisplay();
  syncCartToSession();
}

function removeFromCart(productId) {
  delete cart[productId];
  if (lastAddedId === productId) lastAddedId = null;
  updateCartDisplay();
  syncCartToSession();
}

function clearCart() {
  if (Object.keys(cart).length === 0) return;
  showConfirm('Clear entire cart?', () => {
    cart = {};
    lastAddedId = null;
    updateCartDisplay();
    syncCartToSession();
  });
}

// --- SETTINGS (New Sale) ---
function openSettings() {
  $('#settings-modal').classList.add('show');
  $('#sale-type-select').value = saleType;

  // Default to "mostrador" client
  const sel = $('#client-select');
  const options = sel.querySelectorAll('option');
  for (const opt of options) {
    if (opt.textContent.toLowerCase().includes('mostrador')) {
      sel.value = opt.value;
      break;
    }
  }
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

  if (!saleType) {
    showToast('Select a sale type', 'warning');
    return;
  }

  saleStarted = true;
  updateSaleTypeDisplay();
  closeSettings();
  syncCartToSession();
  broadcastToDisplay('sale_started');
  $('#search-input').focus();
}

function updateSaleTypeDisplay() {
  $('#sale-type-display').textContent = saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo';
  $('#client-display').textContent = clientName || 'General';
}

function toggleMayoreo() {
  const visible = document.body.dataset.mayoreo === 'true';
  document.body.dataset.mayoreo = visible ? 'false' : 'true';
  applyMayoreoVisibility();
}

function applyMayoreoVisibility() {
  const visible = document.body.dataset.mayoreo === 'true';
  $$('.col-mayoreo').forEach(el => {
    el.style.display = visible ? '' : 'none';
  });
  // Update card prices when toggling
  if (visible) {
    $$('.product-card').forEach(card => {
      const regular = parseFloat(card.dataset.priceRegular) || 0;
      const mayoreo = parseFloat(card.dataset.priceMayoreo) || 0;
      const priceEl = card.querySelector('.card-price');
      if (priceEl) priceEl.textContent = '$' + mayoreo.toFixed(2);
    });
  } else {
    $$('.product-card').forEach(card => {
      const regular = parseFloat(card.dataset.priceRegular) || 0;
      const priceEl = card.querySelector('.card-price');
      if (priceEl) priceEl.textContent = '$' + regular.toFixed(2);
    });
  }
}

// --- CHECKOUT ---
function proceedCheckout() {
  if (Object.keys(cart).length === 0) {
    showToast('Cart is empty', 'warning');
    return;
  }

  const items = Object.values(cart).map(item => ({
    product_id: item.id,
    quantity: item.qty,
  }));

  showLoading(true);

  fetch('/pos/validate-stock/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({items: items}),
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (!data.success) {
      const failures = data.items.filter(i => !i.valid);
      let msg = 'Stock issues:\n';
      failures.forEach(f => { msg += `• ${f.product_name}: ${f.message}\n`; });
      showToast(msg, 'error');
      return;
    }
    openCheckoutModal();
  })
  .catch(err => {
    showLoading(false);
    showToast('Failed to validate stock', 'error');
  });
}

function openCheckoutModal() {
  $('#checkout-modal').classList.add('show');

  let totalItems = 0;
  let totalAmount = 0;
  Object.values(cart).forEach(item => {
    totalItems += item.qty;
    totalAmount += item.qty * item.price;
  });

  $('#chk-tipo').textContent = saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo';
  $('#chk-client').textContent = clientName || 'General';
  $('#chk-items').textContent = totalItems;
  $('#chk-total').textContent = '$' + totalAmount.toFixed(2);

  window.currentTotal = totalAmount;
  window.walletDiscount = 0;
  window.walletApplied = false;

  // Payment method selection
  $$('.payment-method-btn').forEach(btn => {
    btn.addEventListener('click', () => selectPaymentMethod(btn.dataset.method));
  });
  selectPaymentMethod('cash');

  // Numpad
  setupNumpad('cash-numpad', 'cash-amount-display', (val) => {
    const cashAmount = parseFloat(val) || 0;
    const change = cashAmount - window.currentTotal;
    const cd = $('#change-display');
    if (cashAmount > 0) {
      cd.style.display = 'block';
      if (change < 0) {
        cd.className = 'change-display negative';
        cd.textContent = `Need $${Math.abs(change).toFixed(2)} more`;
      } else {
        cd.className = 'change-display positive';
        cd.textContent = `Change: $${change.toFixed(2)}`;
      }
    } else {
      cd.style.display = 'none';
    }

    syncCheckoutState({
      active: true,
      payment_method: window.selectedPayment || 'cash',
      total: window.currentTotal,
      cash_received: cashAmount,
      change: change > 0 ? change : 0,
    });
  });

  // Reset cash display
  $('#cash-amount-display').textContent = '$0.00';
  $('#change-display').style.display = 'none';

  // Wallet
  updateWalletDisplay();

  // Notes
  $('#checkout-notes').value = '';
}

function closeCheckout() {
  $('#checkout-modal').classList.remove('show');
  clearCheckoutState();
}

function selectPaymentMethod(method) {
  window.selectedPayment = method;
  $$('.payment-method-btn').forEach(btn => {
    btn.classList.toggle('selected', btn.dataset.method === method);
  });

  const cashArea = $('#cash-payment-area');
  if (method === 'cash') {
    cashArea.style.display = 'block';
  } else {
    cashArea.style.display = 'none';
  }
}

function setupNumpad(numpadId, displayId, onValueChange) {
  const numpad = $(`#${numpadId}`);
  if (!numpad) return;

  // Remove old listeners by cloning
  const display = $(`#${displayId}`);
  let currentValue = '';

  numpad.querySelectorAll('.numpad-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.value;
      if (val === 'clear') {
        currentValue = '';
      } else if (val === 'backspace') {
        currentValue = currentValue.slice(0, -1);
      } else if (val === '.') {
        if (!currentValue.includes('.')) currentValue += '.';
      } else {
        currentValue += val;
      }

      const numVal = parseFloat(currentValue) || 0;
      display.textContent = numVal > 0 ? '$' + numVal.toFixed(2) : '$0.00';
      if (onValueChange) onValueChange(currentValue);
    });
  });
}

function updateWalletDisplay() {
  const el = $('#wallet-info');
  if (clientId && clientWallet > 0) {
    el.style.display = 'flex';
    $('#wallet-amount-display').textContent = '$' + clientWallet.toFixed(2);
  } else {
    el.style.display = 'none';
  }
}

function applyWalletDiscount() {
  if (!clientId || clientWallet <= 0) return;

  const discount = Math.min(clientWallet, window.currentTotal);
  window.walletDiscount = discount;
  window.walletApplied = true;

  const finalTotal = window.currentTotal - discount;
  $('#chk-total').textContent = '$' + finalTotal.toFixed(2);
  $('#wallet-info').innerHTML = `
    <span>✅ Wallet applied</span>
    <span class="wallet-amount" style="color:var(--success);">-$${discount.toFixed(2)}</span>
  `;
}

function confirmCheckout() {
  const paymentMethod = window.selectedPayment || 'cash';
  const notes = $('#checkout-notes').value;
  let totalAmount = window.currentTotal;
  let walletDiscount = window.walletDiscount || 0;

  if (paymentMethod === 'cash') {
    const cashText = $('#cash-amount-display').textContent.replace('$', '');
    const cashAmount = parseFloat(cashText) || 0;

    if (cashAmount <= 0) {
      showToast('Enter the cash amount received', 'warning');
      return;
    }

    if (cashAmount < totalAmount - walletDiscount) {
      showToast(`Insufficient payment! Need $${(totalAmount - walletDiscount - cashAmount).toFixed(2)} more`, 'error');
      return;
    }
  }

  const finalTotal = totalAmount - walletDiscount;

  const items = Object.values(cart).map(item => ({
    product_id: item.id,
    quantity: item.qty,
    price: item.price,
  }));

  const saleData = {
    items: items,
    tipo: saleType,
    payment_method: paymentMethod,
    client_id: clientId || null,
    notes: notes,
    wallet_discount: walletDiscount,
    total_amount: finalTotal,
  };

  showLoading(true);

  fetch('/pos/complete-sale/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(saleData),
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (data.success) {
      const saleMsg = 'Gracias por su compra, vuelva pronto';

      // Show success
      showToast(`✅ Sale #${data.sale_id} completed! $${data.total}`, 'success');

      clearCheckoutState();

      syncCartToSession({
        saleCompleted: {
          message: saleMsg,
          timestamp: Date.now() / 1000,
        }
      }).then(() => {
        closeCheckout();
        broadcastToDisplay('sale_completed');
        setTimeout(() => location.reload(), 300);
      });
    } else {
      showToast(`Error: ${data.error}`, 'error');
    }
  })
  .catch(err => {
    showLoading(false);
    showToast('Failed to complete sale', 'error');
  });
}

// --- NUMERIC KEYPAD FOR QTY (used in settings/sale start) ---
let qtyKeypadCallback = null;

function openQtyKeypad(title, initialValue, callback) {
  qtyKeypadCallback = callback;
  $('#keypad-modal').classList.add('show');
  $('#keypad-title').textContent = title;
  $('#keypad-display').textContent = initialValue || '0';

  const numpad = $('#keypad-numpad');
  numpad.querySelectorAll('.numpad-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.value;
      const display = $('#keypad-display');
      let current = display.textContent;

      if (val === 'clear') {
        display.textContent = '0';
      } else if (val === 'backspace') {
        display.textContent = current.length > 1 ? current.slice(0, -1) : '0';
      } else {
        if (current === '0') {
          display.textContent = val;
        } else {
          display.textContent = current + val;
        }
      }
    });
  });

  $('#keypad-confirm').addEventListener('click', () => {
    const val = parseInt($('#keypad-display').textContent) || 1;
    if (qtyKeypadCallback) qtyKeypadCallback(Math.max(1, val));
    closeQtyKeypad();
  });

  $('#keypad-cancel').addEventListener('click', closeQtyKeypad);
}

function closeQtyKeypad() {
  $('#keypad-modal').classList.remove('show');
  qtyKeypadCallback = null;
}

// --- CUSTOMER DISPLAY ---
function openDisplayLink() {
  const baseUrl = window.location.origin + '/pos/customer-display/?sk=' + encodeURIComponent(sessionKey);
  const activateUrl = baseUrl + '&activate=1';
  $('#display-url').value = activateUrl;

  try {
    posChannel?.postMessage('sale_started');
  } catch(e) {}

  window.open(activateUrl, 'customer-display', 'width=800,height=600');
  $('#display-modal').classList.add('show');
}

function closeDisplayLink() {
  $('#display-modal').classList.remove('show');
}

function copyDisplayLink() {
  const input = $('#display-url');
  input.select();
  input.setSelectionRange(0, 99999);
  navigator.clipboard.writeText(input.value).catch(() => {});
  showToast('Link copied', 'success');
}

// --- TOAST NOTIFICATIONS ---
function showToast(message, type) {
  const container = $('#toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast toast-' + (type || 'info');
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// --- CONFIRM DIALOG ---
function showConfirm(message, onConfirm) {
  $('#confirm-modal').classList.add('show');
  $('#confirm-message').textContent = message;
  $('#confirm-yes').onclick = () => {
    $('#confirm-modal').classList.remove('show');
    if (onConfirm) onConfirm();
  };
  $('#confirm-no').onclick = () => {
    $('#confirm-modal').classList.remove('show');
  };
}

// --- LOADING ---
function showLoading(show) {
  $('#loading-overlay').style.display = show ? 'flex' : 'none';
}



// --- KEYBOARD SHORTCUTS ---
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if ($('#checkout-modal.show')) { closeCheckout(); return; }
    if ($('#settings-modal.show')) { closeSettings(); return; }
    if ($('#display-modal.show')) { closeDisplayLink(); return; }
    if ($('#keypad-modal.show')) { closeQtyKeypad(); return; }
    if ($('#confirm-modal.show')) { $('#confirm-modal').classList.remove('show'); return; }
    clearCart();
  }
});
