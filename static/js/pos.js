/**
 * MINIMALIST POS SYSTEM - Client-side Logic
 * Focus: Fast, distraction-free cashier experience
 * Workflow: Nueva Venta (select type+client) → Add items → Checkout
 */

// Global state
let cart = {}; // {product_id: {id, barcode, name, qty, price, tipo}}
let currentMode = 'sale'; // 'sale' | 'devolucion' | 'cotizacion'
let returnSaleData = null;
let returnMode = null; // null | 'ticket' | 'noticket'

// Broadcast channel to notify customer display (if same browser)
try {
    var posChannel = new BroadcastChannel('pos-display');
} catch(e) {
    var posChannel = null;
}
function broadcastToDisplay(msg) {
    if (posChannel) posChannel.postMessage(msg);
}
let saleType = 'menudeo';
let clientId = null;
let clientName = null;
let clientWallet = 0;
let saleStarted = false; // Flag to block adding products before sale setup
const TAX_RATE = 0; // NO TAXES
let cashInputDebounceTimer = null; // For debouncing cash input validation
let searchDebounceTimer = null; // For debouncing live search input
let currentDespieceConfig = null; // For despiece modal

// Sync cart to server session (for customer display)
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
        if (!r.ok) console.error('Cart sync failed:', r.status, r.statusText);
        return r;
    }).catch(err => console.error('Cart sync error:', err));
}

// Sync checkout state to server session (for customer display)
function syncCheckoutState(state) {
    console.log('syncCheckoutState', state);
    fetch('/pos/checkout/save/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(state),
    }).then(r => {
        if (!r.ok) console.error('checkout/save status:', r.status);
    }).catch(err => console.error('Checkout state sync error:', err));
}

function clearCheckoutState() {
    fetch('/pos/checkout/clear/', {
        method: 'POST',
    }).catch(err => console.error('Checkout state clear error:', err));
}

// CSRF TOKEN
function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const cookies = document.cookie.split(';');
    for (let c of cookies) {
        if (c.trim().startsWith('csrftoken=')) return c.trim().substring('csrftoken='.length);
    }
    return '';
}

// DESPIECE MODAL
function openDespieceModal(btn) {
    const row = btn.closest('tr');
    currentDespieceConfig = {
        configId: row.dataset.despieceConfigId,
        sourceName: row.dataset.despieceSourceName,
        sourceStock: parseInt(row.dataset.despieceSourceStock) || 0,
        unitsPer: parseFloat(row.dataset.despieceUnitsPer) || 1,
    };
    if (!currentDespieceConfig.configId) { alert('No despiece config'); return; }
    document.getElementById('despiece-source-name').textContent = currentDespieceConfig.sourceName;
    document.getElementById('despiece-source-stock').textContent = currentDespieceConfig.sourceStock + ' pz';
    document.getElementById('despiece-qty').value = 1;
    updateDespiecePreview();
    document.getElementById('despiece-modal').classList.add('show');
}

function closeDespieceModal() {
    document.getElementById('despiece-modal').classList.remove('show');
    currentDespieceConfig = null;
}

function despieceQtyDelta(delta) {
    const input = document.getElementById('despiece-qty');
    let val = parseInt(input.value) + delta;
    val = Math.max(1, Math.min(val, currentDespieceConfig?.sourceStock || 999));
    input.value = val;
    updateDespiecePreview();
}

function updateDespiecePreview() {
    const qty = parseInt(document.getElementById('despiece-qty').value) || 0;
    const dest = qty * (currentDespieceConfig?.unitsPer || 1);
    document.getElementById('despiece-dest-qty').textContent = dest;
}

function confirmDespiece() {
    const qty = parseInt(document.getElementById('despiece-qty').value) || 0;
    if (qty <= 0) { alert('Enter a valid quantity'); return; }
    if (qty > currentDespieceConfig.sourceStock) {
        alert('Only ' + currentDespieceConfig.sourceStock + ' available'); return;
    }

    const url = '/im/product/despiece/' + currentDespieceConfig.configId + '/process/';
    const formData = new FormData();
    formData.append('source_quantity', qty);
    formData.append('csrfmiddlewaretoken', getCSRFToken());

    var xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.onload = function() {
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e) {}
        if (xhr.status >= 200 && xhr.status < 300 && data && data.success) {
            alert('✅ Despiece: ' + data.source_quantity + ' → ' + data.destination_quantity + ' units created');
            closeDespieceModal();
            location.reload();
        } else {
            alert('❌ URL=' + url + ' Status=' + xhr.status + ' Body=' + xhr.responseText.substring(0,200));
        }
    };
    xhr.onerror = function() {
        alert('❌ Network error URL=' + url);
    };
    xhr.send(formData);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    updateCartDisplay();
    document.getElementById('search-input').addEventListener('input', handleSearchInput);
    document.getElementById('search-input').addEventListener('keypress', handleSearchKeypress);
    document.getElementById('sale-type-select').addEventListener('change', updateSaleTypeDisplay);
    document.getElementById('toggleMayoreoBtn').addEventListener('click', toggleMayoreoColumn);
    applyMayoreoVisibility();

    // Init mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            setMode(this.dataset.mode);
        });
    });

    // Enable search immediately (browse products without starting a sale)
    enableSearch();
});

function disableSearch() {
    const searchInput = document.getElementById('search-input');
    searchInput.disabled = true;
    searchInput.placeholder = 'Click ⚙️ to start a new sale...';
    searchInput.style.opacity = '0.5';
}

function enableSearch() {
    const searchInput = document.getElementById('search-input');
    searchInput.disabled = false;
    searchInput.placeholder = 'Search by product name or barcode...';
    searchInput.style.opacity = '1';
    searchInput.focus();
}

// SEARCH & PRODUCT MANAGEMENT
function handleSearchInput(e) {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    const query = e.target.value.trim();
    if (query.length < 2) {
        searchDebounceTimer = setTimeout(() => {
            if (query.length === 0) reloadInventory();
        }, 200);
        return;
    }
    searchDebounceTimer = setTimeout(() => searchProducts(query), 150);
}

function handleSearchKeypress(e) {
    if (e.key === 'Enter') {
        const query = e.target.value.trim();
        if (query.length < 2) return;
        if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
        searchProducts(query);
        e.target.value = '';
    }
}

function searchProducts(query) {
    fetch(`/pos/search/?q=${encodeURIComponent(query)}`)
        .then(r => r.json())
        .then(products => {
            // Update table with search results
            const tbody = document.getElementById('products-tbody');
            tbody.innerHTML = '';
            
            products.forEach(p => {
                const row = document.createElement('tr');
                row.dataset.productId = p.id;
                row.dataset.priceGranel = p.price_granel || '';
                row.dataset.minimo = p.minimo || '';
                row.dataset.despieceConfigId = p.despiece_config_id || '';
                row.dataset.despieceSourceName = p.despiece_source_name || '';
                row.dataset.despieceSourceStock = p.despiece_source_stock || '';
                row.dataset.despieceUnitsPer = p.despiece_units_per || '';
                if (p.Granel_Item) row.classList.add('row-granel');
                if (p.stock <= 0 && p.despiece_config_id) row.classList.add('zero-despiece');
                const hasDespiece = p.despiece_config_id ? true : false;
                let stockDisplay = p.stock;
                if (p.stock <= 0 && hasDespiece && p.despiece_source_stock > 0) {
                    stockDisplay = '0 · src: ' + p.despiece_source_stock;
                }
                row.innerHTML = `
                    <td class="barcode">${p.barcode}</td>
                    <td class="name">${p.compose_name || p.name}${p.Granel_Item ? ' <span class="badge-granel">GRANEL</span>' : ''}</td>
                    <td class="stock">${stockDisplay}</td>
                    <td class="price-regular">$${parseFloat(p.price).toFixed(2)}</td>
                    <td class="price-mayoreo col-mayoreo">$${parseFloat(p.price_mayoreo).toFixed(2)}</td>
                    <td class="action">
                        <input type="number" class="qty-input" value="1" min="1" style="width: 50px;">
                        <button class="btn-add" onclick="addToCart(this)">+</button>
                        ${hasDespiece ? '<button class="despiece-btn" onclick="openDespieceModal(this)" title="Despiece: ' + p.despiece_source_name + '">📦→</button>' : ''}
                    </td>
                `;
                tbody.appendChild(row);
            });
            // Re-apply mayoreo column visibility after search
            applyMayoreoVisibility();
        })
        .catch(err => console.error('Search error:', err));
}

// ADD TO CART - WITH BACKEND STOCK VALIDATION
function addToCart(btn) {
    if (!saleStarted) {
        alert('⚠️ Please create a sale first (click 📝 NUEVA VENTA)');
        openSettings();
        return;
    }
    
    const row = btn.closest('tr');
    const productId = row.dataset.productId;
    const qtyInput = row.querySelector('.qty-input');
    const quantity = parseInt(qtyInput.value) || 1;
    
    const barcode = row.querySelector('.barcode').textContent;
    const name = row.querySelector('.name').textContent;

    // For devolucion without ticket, skip stock check
    if (currentMode === 'devolucion' && returnMode === 'noticket') {
        const priceRegular = parseFloat(row.querySelector('.price-regular').textContent.replace('$', ''));
        const priceMayoreo = parseFloat(row.querySelector('.price-mayoreo').textContent.replace('$', ''));
        const price = saleType === 'mayoreo' ? priceMayoreo : priceRegular;
        if (cart[productId]) {
            cart[productId].qty += quantity;
        } else {
            cart[productId] = {
                id: productId,
                barcode: barcode,
                name: name,
                qty: quantity,
                price: price,
                tipo: saleType,
                is_return: true,
            };
        }
        cart[productId].addedAt = Date.now();
        updateCartDisplay();
        syncCartToSession();
        qtyInput.value = 1;
        return;
    }

    // FETCH CURRENT STOCK FROM BACKEND (single source of truth)
    fetch(`/pos/stock/?id=${productId}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                alert(`❌ Product not found!`);
                return;
            }
            
            const backendStock = data.stock;
            
            // Update table display with current stock
            row.querySelector('.stock').textContent = backendStock;
            
            // Check single add quantity
            if (quantity > backendStock) {
                alert(`⚠️ Cannot add ${quantity} units - only ${backendStock} in stock!`);
                return;
            }
            
            // Check total quantity in cart for this product won't exceed stock
            const currentQtyInCart = cart[productId] ? cart[productId].qty : 0;
            const totalQtyAfterAdd = currentQtyInCart + quantity;
            
            if (totalQtyAfterAdd > backendStock) {
                alert(`⚠️ You already have ${currentQtyInCart} in cart.\nOnly ${backendStock - currentQtyInCart} more available!\nCannot add ${quantity}.`);
                return;
            }
            
            // Get price based on sale type
            const priceRegular = parseFloat(row.querySelector('.price-regular').textContent.replace('$', ''));
            const priceMayoreo = parseFloat(row.querySelector('.price-mayoreo').textContent.replace('$', ''));
            const price = saleType === 'mayoreo' ? priceMayoreo : priceRegular;
            
        // Add to cart
        if (cart[productId]) {
            cart[productId].qty += quantity;
        } else {
            cart[productId] = {
                id: productId,
                barcode: barcode,
                name: name,
                qty: quantity,
                price: price,
                tipo: saleType,
            };
        }
        cart[productId].addedAt = Date.now();
            
            updateCartDisplay();
            syncCartToSession();
            qtyInput.value = 1;
        })
        .catch(err => {
            console.error('Stock check error:', err);
            alert('❌ Failed to verify stock');
        });
}

// UPDATE CART DISPLAY
function updateCartDisplay() {
    const itemsContainer = document.getElementById('cart-items');
    const cartCount = document.getElementById('cart-count');
    let totalItems = 0;
    let totalAmount = 0;
    
    if (Object.keys(cart).length === 0) {
        itemsContainer.innerHTML = '<div class="empty-cart">Empty</div>';
        cartCount.textContent = '0';
        document.getElementById('total-items').textContent = '0';
        document.getElementById('subtotal').textContent = '$0.00';
        document.getElementById('total').textContent = '$0.00';
        return;
    }
    
    itemsContainer.innerHTML = '';

    // Sort: last added first, then alphabetically by name
    const entries = Object.values(cart);
    const lastAdded = entries.reduce((a, b) => a.addedAt > b.addedAt ? a : b);
    const sorted = [
        lastAdded,
        ...entries.filter(e => e.id !== lastAdded.id).sort((a, b) => a.name.localeCompare(b.name)),
    ];

    // Track which is the last added (first in sorted array)
    const lastAddedId = sorted.length > 0 ? sorted[0].id : null;

    sorted.forEach(item => {
        const itemTotal = item.qty * item.price;
        totalItems += item.qty;
        totalAmount += itemTotal;
        
        const div = document.createElement('div');
        div.className = 'cart-item' + (item.id === lastAddedId ? ' cart-item-last' : '');
        div.innerHTML = `
            <div class="cart-item-header">
                <span class="cart-item-name">${item.name}</span>
                <button class="cart-item-remove" onclick="removeFromCart('${item.id}')">Remove</button>
            </div>
            <div class="cart-item-price">
                <span>$${item.price.toFixed(2)} × ${item.qty}</span>
                <strong>$${itemTotal.toFixed(2)}</strong>
            </div>
            <div class="cart-item-qty">
                <button class="qty-btn" onclick="updateQty('${item.id}', -1)">−</button>
                <span>${item.qty}</span>
                <button class="qty-btn" onclick="updateQty('${item.id}', 1)">+</button>
            </div>
        `;
        itemsContainer.appendChild(div);
    });
    
    cartCount.textContent = Object.keys(cart).length;
    document.getElementById('total-items').textContent = totalItems;
    document.getElementById('subtotal').textContent = '$' + totalAmount.toFixed(2);
    document.getElementById('total').textContent = '$' + totalAmount.toFixed(2);
}

// UPDATE ITEM QUANTITY
function updateQty(productId, delta) {
    if (cart[productId]) {
        cart[productId].qty += delta;
        if (cart[productId].qty <= 0) {
            delete cart[productId];
        }
        updateCartDisplay();
        syncCartToSession();
    }
}

// REMOVE FROM CART
function removeFromCart(productId) {
    delete cart[productId];
    updateCartDisplay();
    syncCartToSession();
}

// CLEAR CART
function clearCart() {
    if (Object.keys(cart).length === 0) return;
    if (confirm('Clear entire cart?')) {
        cart = {};
        updateCartDisplay();
        syncCartToSession();
    }
}

// SETTINGS
function openSettings() {
    document.getElementById('settings-modal').classList.add('show');
    
    // Sync dropdowns with current state
    document.getElementById('sale-type-select').value = saleType;
    
    // Default to "mostrador" client
    const clientSelect = document.getElementById('client-select');
    const options = clientSelect.querySelectorAll('option');
    options.forEach(opt => {
        if (opt.textContent.toLowerCase().includes('mostrador')) {
            clientSelect.value = opt.value;
        }
    });
}

function closeSettings() {
    document.getElementById('settings-modal').classList.remove('show');
}

function saveSettings() {
    saleType = document.getElementById('sale-type-select').value;
    clientId = document.getElementById('client-select').value || null;
    
    // Get client data
    const clientSelect = document.getElementById('client-select');
    const selectedOption = clientSelect.options[clientSelect.selectedIndex];
    clientName = selectedOption.text;
    clientWallet = parseFloat(selectedOption.dataset.wallet) || 0;
    
    if (!saleType) {
        alert('⚠️ Please select a sale type');
        return;
    }
    
    // Update display
    saleStarted = true;
    updateSaleTypeDisplay();
    document.getElementById('client-display').textContent = `Client: ${clientName}`;
    
    closeSettings();
    syncCartToSession();
    broadcastToDisplay('sale_started');
}

function updateSaleTypeDisplay() {
    document.getElementById('sale-type-display').textContent = `Sale: ${saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo'}`;
}

function toggleMayoreoColumn() {
    const table = document.getElementById('products-table');
    const isVisible = table.dataset.mayoreoVisible === 'true';
    table.dataset.mayoreoVisible = isVisible ? 'false' : 'true';
    applyMayoreoVisibility();
}

function applyMayoreoVisibility() {
    const table = document.getElementById('products-table');
    const isVisible = table.dataset.mayoreoVisible === 'true';
    table.querySelectorAll('.col-mayoreo').forEach(el => {
        el.style.display = isVisible ? 'table-cell' : 'none';
    });
}

// ==================== MODE SWITCHING ====================
function setMode(mode) {
    currentMode = mode;
    returnMode = null;
    returnSaleData = null;
    document.body.className = document.body.className.replace(/mode-\w+/g, '').trim() + ' mode-' + mode;
    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));

    const checkoutBtn = document.getElementById('pos-checkout-btn');
    if (mode === 'devolucion') {
        if (checkoutBtn) checkoutBtn.textContent = '🔄 DEVOLVER';
        showReturnChoice();
    } else if (mode === 'cotizacion') {
        if (checkoutBtn) checkoutBtn.textContent = '📄 COTIZAR';
        hideReturnChoice();
        hideReturnLookup();
    } else {
        if (checkoutBtn) checkoutBtn.textContent = '💳 COBRAR';
        hideReturnChoice();
        hideReturnLookup();
        returnSaleData = null;
    }
}

function showReturnChoice() {
    hideReturnChoice();
    hideReturnLookup();
    const cartSection = document.querySelector('.pos-cart-section');
    if (!cartSection) return;
    const div = document.createElement('div');
    div.id = 'return-choice';
    div.style.cssText = 'padding:16px;text-align:center;background:#fff5f5;border:1px solid #f5c6cb;border-radius:6px;margin-bottom:10px;';
    div.innerHTML =
        '<div style="font-size:15px;font-weight:700;color:#c0392b;margin-bottom:12px;">🔙 MODO DEVOLUCIÓN</div>' +
        '<div style="display:flex;gap:10px;justify-content:center;">' +
        '<button class="btn btn-danger" onclick="startReturnWithTicket()" style="padding:10px 20px;">🎫 Con Ticket</button>' +
        '<button class="btn btn-danger" onclick="startReturnWithoutTicket()" style="padding:10px 20px;">📦 Sin Ticket</button>' +
        '</div>' +
        '<div style="margin-top:8px;font-size:12px;color:#888;">Con ticket: busca venta original · Sin ticket: selecciona productos directamente</div>';
    const cartItems = document.querySelector('.cart-items');
    cartSection.insertBefore(div, cartItems || cartSection.lastChild);
}

function hideReturnChoice() {
    const el = document.getElementById('return-choice');
    if (el) el.remove();
}

function startReturnWithTicket() {
    returnMode = 'ticket';
    hideReturnChoice();
    hideReturnLookup();
    showReturnLookup();
}

function startReturnWithoutTicket() {
    returnMode = 'noticket';
    hideReturnChoice();
    hideReturnLookup();
    alert('Selecciona productos a devolver desde la tabla de productos');
}


function showReturnLookup() {
    if (returnMode === 'noticket') return;
    const cartSection = document.querySelector('.pos-cart-section');
    if (!cartSection) return;
    let lookup = document.getElementById('return-lookup');
    if (lookup) { lookup.style.display = 'flex'; return; }
    const div = document.createElement('div');
    div.id = 'return-lookup';
    div.className = 'return-lookup';
    div.innerHTML = '<input type="text" id="return-ticket-input" placeholder="Ticket # original..." autocomplete="off">' +
        '<button onclick="lookupReturnSale()">🔍 Buscar</button>';
    const cartItems = document.querySelector('.cart-items');
    cartSection.insertBefore(div, cartItems || cartSection.lastChild);
}

function hideReturnLookup() {
    const el = document.getElementById('return-lookup');
    if (el) el.style.display = 'none';
    document.querySelectorAll('.return-item-row').forEach(el => el.remove());
    document.querySelectorAll('.return-add-btn-container').forEach(el => el.remove());
}

function lookupReturnSale() {
    const saleId = document.getElementById('return-ticket-input').value.trim();
    if (!saleId || isNaN(saleId)) { showToast('Enter a valid ticket number', 'warning'); return; }
    showLoading(true);
    fetch('/pos/get-sale-for-return/' + saleId + '/')
        .then(r => r.json())
        .then(data => {
            showLoading(false);
            if (data.error) { alert(data.error); return; }
            returnSaleData = data;
            showReturnItems(data);
        })
        .catch(() => { showLoading(false); alert('Sale not found'); });
}

function showReturnItems(data) {
    document.querySelectorAll('.return-item-row').forEach(el => el.remove());
    document.querySelectorAll('.return-add-btn-container').forEach(el => el.remove());
    const cartSection = document.querySelector('.pos-cart-section');
    data.items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'return-item-row';
        row.innerHTML = '<input type="checkbox" class="return-chk" data-sale-item-id="' + item.sale_item_id + '" checked>' +
            '<span style="flex:1;">' + item.name + '</span>' +
            '<span style="color:#888;font-size:11px;margin-right:4px;">SAT:' + (item.sat ? 'Sí' : 'No') + '</span>' +
            '<input type="number" class="return-qty" value="' + item.quantity + '" min="1" max="' + item.quantity + '" style="width:50px;">' +
            '<span style="margin-left:4px;">$' + item.price.toFixed(2) + '</span>';
        cartSection.appendChild(row);
    });
    const btnContainer = document.createElement('div');
    btnContainer.className = 'return-add-btn-container';
    btnContainer.style.cssText = 'padding:8px;text-align:center;';
    btnContainer.innerHTML = '<button class="btn btn-danger" onclick="addSelectedReturns()">➕ Agregar seleccionados a devolución</button>';
    cartSection.appendChild(btnContainer);
}

function addSelectedReturns() {
    const checkboxes = document.querySelectorAll('.return-chk:checked');
    if (checkboxes.length === 0) { alert('Select items to return'); return; }
    checkboxes.forEach(chk => {
        const saleItemId = chk.dataset.saleItemId;
        const row = chk.closest('.return-item-row');
        const qtyInput = row.querySelector('.return-qty');
        const qty = parseInt(qtyInput.value) || 1;
        const item = returnSaleData.items.find(i => i.sale_item_id == saleItemId);
        if (!item) return;
        const pid = item.product_id;
        if (cart[pid]) {
            cart[pid].qty += qty;
        } else {
            cart[pid] = { id: pid, qty: qty, price: item.price, name: item.name, is_return: true, sale_item_id: saleItemId, sat: item.sat };
        }
    });
    alert(checkboxes.length + ' item(s) added to return');
    renderCart();
    hideReturnLookup();
}

function showToast(msg) {
    // Simple fallback for normal POS (no toast system)
    console.log(msg);
}

function showLoading(v) {
    const el = document.getElementById('loading-overlay');
    if (el) el.style.display = v ? 'flex' : 'none';
}

// Helper to check if we're in a non-sale mode
function isNonSaleMode() {
    return currentMode === 'devolucion' || currentMode === 'cotizacion';
}

// CHECKOUT - WITH BACKEND STOCK VALIDATION
function proceedCheckout() {
    if (Object.keys(cart).length === 0) {
        alert('⚠️ Cart is empty!');
        return;
    }

    // Skip stock validation for devolucion and cotizacion
    if (isNonSaleMode()) {
        proceedCheckoutModal();
        return;
    }

    // Prepare items for validation
    const cartItems = Object.values(cart).map(item => ({
        product_id: item.id,
        quantity: item.qty,
    }));
    
    // VALIDATE ALL ITEMS AGAINST CURRENT BACKEND STOCK
    fetch('/pos/validate-stock/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({items: cartItems}),
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) {
            // Show which items have stock issues
            const failures = data.items.filter(item => !item.valid);
            let msg = '❌ Stock validation failed:\n\n';
            failures.forEach(item => {
                msg += `• ${item.product_name}: ${item.message}\n`;
            });
            alert(msg);
            return;
        }
        
        // All items valid - proceed to checkout
        proceedCheckoutModal();
    })
    .catch(err => {
        console.error('Stock validation error:', err);
        alert('❌ Failed to validate stock');
    });
}

function proceedCheckoutModal() {
    console.log('proceedCheckoutModal called');
    // Open checkout modal
    document.getElementById('checkout-modal').classList.add('show');

    // Update checkout summary
    document.getElementById('checkout-tipo').textContent = saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo';
    document.getElementById('checkout-client').textContent = clientName;

    let totalItems = 0;
    let totalAmount = 0;
    Object.values(cart).forEach(item => {
        totalItems += item.qty;
        totalAmount += item.qty * item.price;
    });

    document.getElementById('checkout-items').textContent = totalItems;
    document.getElementById('checkout-total').textContent = '$' + totalAmount.toFixed(2);

    // Store total for cash payment calculation
    window.currentTotal = totalAmount;

    // Show/hide payment section based on mode
    const paymentGroup = document.querySelector('.checkout-group');
    if (paymentGroup) {
        paymentGroup.style.display = isNonSaleMode() ? 'none' : 'block';
    }

    if (isNonSaleMode()) {
        const confirmBtn = document.getElementById('checkout-confirm-btn');
        if (confirmBtn) {
            confirmBtn.textContent = currentMode === 'devolucion' ? '🔄 CONFIRMAR DEVOLUCIÓN' : '📄 GENERAR COTIZACIÓN';
        }
        return;
    }

    // Reset confirm button for sale mode
    const confirmBtn = document.getElementById('checkout-confirm-btn');
    if (confirmBtn) confirmBtn.textContent = '💳 COBRAR';

    // Setup payment method listeners
    setupPaymentMethodListeners();

    // Sync checkout state for customer display
    syncCheckoutState({
        active: true,
        payment_method: 'cash',
        total: totalAmount,
        cash_received: 0,
        change: 0,
    });

    // Reset cash amount input
    const cashAmountInput = document.getElementById('cash-amount-input');
    if (cashAmountInput) {
        cashAmountInput.value = '';
        cashAmountInput.focus();
    }
}

function setupPaymentMethodListeners() {
    const paymentRadios = document.querySelectorAll('input[name="payment"]');
    paymentRadios.forEach(radio => {
        radio.addEventListener('change', toggleCashInput);
    });
    
    // Show/hide cash input based on current selection
    const selectedPayment = document.querySelector('input[name="payment"]:checked').value;
    if (selectedPayment === 'cash') {
        showCashInput();
    } else {
        hideCashInput();
    }
}

function showCashInput() {
    let cashSection = document.getElementById('cash-payment-section');
    
    // Create cash input section if it doesn't exist
    if (!cashSection) {
        const paymentGroup = document.querySelector('.checkout-group');
        cashSection = document.createElement('div');
        cashSection.id = 'cash-payment-section';
        cashSection.className = 'checkout-group cash-payment-section';
        cashSection.innerHTML = `
            <label>Amount Received (Cash):</label>
            <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                <input type="number" id="cash-amount-input" class="form-control" placeholder="Enter cash amount" step="0.01" min="0">
            </div>
            <div id="change-display" style="display: none; padding: 10px; background: #f0f0f0; border-radius: 4px;">
                <strong>Change: $<span id="change-amount">0.00</span></strong>
            </div>
        `;
        paymentGroup.parentNode.insertBefore(cashSection, paymentGroup.nextSibling);
    }
    
    cashSection.style.display = 'block';
    
    // Add listener to cash amount input
    const cashInput = document.getElementById('cash-amount-input');
    cashInput.addEventListener('input', calculateChange);
    cashInput.focus();
}

function hideCashInput() {
    const cashSection = document.getElementById('cash-payment-section');
    if (cashSection) {
        cashSection.style.display = 'none';
    }
}

function toggleCashInput(e) {
    if (e.target.value === 'cash') {
        showCashInput();
    } else {
        hideCashInput();
    }
    syncCheckoutState({
        active: true,
        payment_method: e.target.value,
        total: window.currentTotal || 0,
        cash_received: parseFloat(document.getElementById('cash-amount-input')?.value) || 0,
        change: 0,
    });
}

function calculateChange() {
    // Debounce the validation - only show warnings after user stops typing for 500ms
    if (cashInputDebounceTimer) {
        clearTimeout(cashInputDebounceTimer);
    }
    
    const cashInput = document.getElementById('cash-amount-input');
    const changeDisplay = document.getElementById('change-display');
    
    // Always show the display area, but delay the validation message
    cashInputDebounceTimer = setTimeout(() => {
        const cashAmount = parseFloat(cashInput.value) || 0;
        const changeAmount = document.getElementById('change-amount');
        
        const change = cashAmount - window.currentTotal;
        
        syncCheckoutState({
            active: true,
            payment_method: 'cash',
            total: window.currentTotal || 0,
            cash_received: cashAmount,
            change: cashAmount > 0 && change >= 0 ? change : 0,
        });
        
        if (cashAmount > 0) {
            changeDisplay.style.display = 'block';
            if (change < 0) {
                changeAmount.textContent = '0.00';
                changeAmount.style.color = 'red';
                changeDisplay.innerHTML = `<strong style="color: red;">Insufficient payment! Need $${Math.abs(change).toFixed(2)} more</strong>`;
            } else {
                changeAmount.textContent = change.toFixed(2);
                changeAmount.style.color = 'green';
                changeDisplay.innerHTML = `<strong style="color: green;">Change: $<span id="change-amount">${change.toFixed(2)}</span></strong>`;
            }
        } else {
            changeDisplay.style.display = 'none';
        }
    }, 500); // Wait 500ms after user stops typing before showing validation
}

function closeCheckout() {
    document.getElementById('checkout-modal').classList.remove('show');
    clearCheckoutState();
    if (cashInputDebounceTimer) {
        clearTimeout(cashInputDebounceTimer);
        cashInputDebounceTimer = null;
    }
}

function confirmCheckout() {
    // Cancel any pending debounced checkout sync before completing
    if (cashInputDebounceTimer) {
        clearTimeout(cashInputDebounceTimer);
        cashInputDebounceTimer = null;
    }
    const totalAmount = window.currentTotal || 0;

    // For sale mode: validate payment
    if (currentMode === 'sale') {
        const paymentMethod = document.querySelector('input[name="payment"]:checked').value;
        const notes = document.getElementById('notes').value;
        window._paymentMethod = paymentMethod;
        window._notes = notes;

        if (paymentMethod === 'cash') {
            const cashInput = document.getElementById('cash-amount-input');
            const cashAmount = parseFloat(cashInput.value) || 0;
            if (cashAmount <= 0) {
                alert('⚠️ Please enter the cash amount received');
                return;
            }
            if (cashAmount < totalAmount) {
                alert(`⚠️ Insufficient payment!\nTotal: $${totalAmount.toFixed(2)}\nReceived: $${cashAmount.toFixed(2)}\nNeed: $${(totalAmount - cashAmount).toFixed(2)} more`);
                return;
            }
        }
    }

    // Check for wallet discount (sale only)
    let walletDiscount = 0;
    let finalTotal = totalAmount;
    if (currentMode === 'sale' && clientId && clientWallet > 0) {
        walletDiscount = Math.min(clientWallet, totalAmount);
        const useWallet = confirm(
            `Client has $${clientWallet.toFixed(2)} in wallet.\n\n` +
            `Apply $${walletDiscount.toFixed(2)} discount?\n\n` +
            `Original: $${totalAmount.toFixed(2)}\n` +
            `With Wallet: $${(totalAmount - walletDiscount).toFixed(2)}`
        );
        if (!useWallet) {
            walletDiscount = 0;
            finalTotal = totalAmount;
        } else {
            finalTotal = totalAmount - walletDiscount;
        }
    }

    // Prepare sale data
    const items = Object.values(cart).map(item => ({
        product_id: item.id,
        quantity: item.qty,
        price: item.price,
        sale_item_id: item.sale_item_id || null,
        sat: item.sat || false,
    }));

    const saleData = {
        items: items,
        tipo: saleType,
        client_id: clientId || null,
        mode: currentMode,
        total_amount: finalTotal,
    };

    if (currentMode === 'sale') {
        saleData.payment_method = window._paymentMethod || 'cash';
        saleData.notes = window._notes || '';
        saleData.wallet_discount = walletDiscount;
    }
    if (currentMode === 'devolucion' && returnSaleData) {
        saleData.original_sale_id = returnSaleData.sale_id;
    }

    // Submit to server
    fetch('/pos/complete-sale/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(saleData),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const labels = { sale: 'Sale', devolucion: 'Devolución', cotizacion: 'Cotización' };
            const label = labels[currentMode] || 'Sale';

            // Queue print job for all modes
            const ticketTypeMap = { sale: 'sale', devolucion: 'devolution', cotizacion: 'quote' };
            fetch('/pos/queue-print/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sale_id: data.sale_id, ticket_type: ticketTypeMap[currentMode] || 'sale'})
            });

            let msg = `✅ ${label} #${data.sale_id} completed!\nTotal: $${data.total}`;
            if (currentMode === 'sale') {
                if (walletDiscount > 0) {
                    msg += `\n💰 Wallet Discount: $${walletDiscount.toFixed(2)}`;
                }
                if (window._paymentMethod === 'cash') {
                    const cashAmount = parseFloat(document.getElementById('cash-amount-input')?.value) || 0;
                    msg += `\n\n💵 Cash Received: $${cashAmount.toFixed(2)}`;
                    msg += `\n🔄 Change: $${(cashAmount - finalTotal).toFixed(2)}`;
                }
            }
            alert(msg);

            clearCheckoutState();

            const saleMsg = currentMode === 'devolucion' ? 'Devolución procesada' :
                currentMode === 'cotizacion' ? 'Cotización generada' :
                'Gracias por su compra, vuelva pronto';

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
            alert('❌ Error: ' + data.error);
        }
    })
    .catch(err => {
        console.error('Error completing:', err);
        alert('❌ Failed to complete: ' + err.message);
    });
}

// Reload product inventory from server
function reloadInventory() {
    fetch('/pos/')
        .then(r => r.text())
        .then(html => {
            // Parse the response to extract products data
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const productRows = doc.querySelectorAll('tbody tr');
            
            // Update current product table
            const tbody = document.querySelector('tbody');
            tbody.innerHTML = '';
            
            productRows.forEach(row => {
                tbody.appendChild(row.cloneNode(true));
            });
            
            console.log('✅ Inventory reloaded from server');
        })
        .catch(err => console.error('Error reloading inventory:', err));
}

// KEYBOARD SHORTCUTS
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (document.getElementById('despiece-modal').classList.contains('show')) { closeDespieceModal(); return; }
        if (document.getElementById('checkout-modal').classList.contains('show')) { closeCheckout(); return; }
        if (document.getElementById('settings-modal').classList.contains('show')) { closeSettings(); return; }
        clearCart();
    }
});
