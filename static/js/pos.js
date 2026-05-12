/**
 * MINIMALIST POS SYSTEM - Client-side Logic
 * Focus: Fast, distraction-free cashier experience
 * Workflow: Nueva Venta (select type+client) → Add items → Checkout
 */

// Global state
let cart = {}; // {product_id: {id, barcode, name, qty, price, tipo}}
let saleType = null;
let clientId = null;
let clientName = null;
let clientWallet = 0;
let saleStarted = false; // Flag to block adding products before sale setup
const TAX_RATE = 0; // NO TAXES

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    updateCartDisplay();
    document.getElementById('search-input').addEventListener('keypress', handleSearchKeypress);
    document.getElementById('sale-type-select').addEventListener('change', updateSaleTypeDisplay);
    
    // Disable search initially
    disableSearch();
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
function handleSearchKeypress(e) {
    if (!saleStarted) {
        alert('⚠️ Please create a sale first (click ⚙️)');
        openSettings();
        return;
    }
    
    if (e.key === 'Enter') {
        const query = e.target.value.trim();
        if (query.length < 2) return;
        
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
                row.innerHTML = `
                    <td class="barcode">${p.barcode}</td>
                    <td class="name">${p.name}</td>
                    <td class="stock">${p.stock}</td>
                    <td class="price-regular">$${parseFloat(p.price).toFixed(2)}</td>
                    <td class="price-mayoreo">$${parseFloat(p.price_mayoreo).toFixed(2)}</td>
                    <td class="price-granel">${p.price_granel ? '$' + parseFloat(p.price_granel).toFixed(2) : '-'}</td>
                    <td class="minimo">${p.minimo}</td>
                    <td class="action">
                        <input type="number" class="qty-input" value="1" min="1" style="width: 50px;">
                        <button class="btn-add" onclick="addToCart(this)">+</button>
                    </td>
                `;
                tbody.appendChild(row);
            });
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
            
            updateCartDisplay();
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
    
    Object.values(cart).forEach(item => {
        const itemTotal = item.qty * item.price;
        totalItems += item.qty;
        totalAmount += itemTotal;
        
        const div = document.createElement('div');
        div.className = 'cart-item';
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
    }
}

// REMOVE FROM CART
function removeFromCart(productId) {
    delete cart[productId];
    updateCartDisplay();
}

// CLEAR CART
function clearCart() {
    if (Object.keys(cart).length === 0) return;
    if (confirm('Clear entire cart?')) {
        cart = {};
        updateCartDisplay();
    }
}

// SETTINGS
function openSettings() {
    document.getElementById('settings-modal').classList.add('show');
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
    enableSearch();
    updateSaleTypeDisplay();
    document.getElementById('client-display').textContent = `Client: ${clientName}`;
    
    closeSettings();
}

function updateSaleTypeDisplay() {
    document.getElementById('sale-type-display').textContent = `Sale: ${saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo'}`;
}

// CHECKOUT - WITH BACKEND STOCK VALIDATION
function proceedCheckout() {
    if (Object.keys(cart).length === 0) {
        alert('⚠️ Cart is empty!');
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
    
    // Setup payment method listeners
    setupPaymentMethodListeners();
    
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
}

function calculateChange() {
    const cashInput = document.getElementById('cash-amount-input');
    const cashAmount = parseFloat(cashInput.value) || 0;
    const changeDisplay = document.getElementById('change-display');
    const changeAmount = document.getElementById('change-amount');
    
    const change = cashAmount - window.currentTotal;
    
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
}

function closeCheckout() {
    document.getElementById('checkout-modal').classList.remove('show');
}

function confirmCheckout() {
    const paymentMethod = document.querySelector('input[name="payment"]:checked').value;
    const notes = document.getElementById('notes').value;
    
    // Calculate total
    let totalAmount = 0;
    Object.values(cart).forEach(item => {
        totalAmount += item.qty * item.price;
    });
    
    // Validate cash payment
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
    
    // Check for wallet discount
    let walletDiscount = 0;
    let finalTotal = totalAmount;
    
    if (clientId && clientWallet > 0) {
        walletDiscount = Math.min(clientWallet, totalAmount);
        
        // Ask user to accept wallet discount
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
    
    // Submit to server
    fetch('/pos/complete-sale/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(saleData),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            // Calculate change for cash payments
            let cashChange = 0;
            if (paymentMethod === 'cash') {
                const cashAmount = parseFloat(document.getElementById('cash-amount-input').value);
                cashChange = cashAmount - finalTotal;
            }
            
            let msg = `✅ Sale completed!\nSale ID: ${data.sale_id}\nTotal: $${data.total}`;
            if (walletDiscount > 0) {
                msg += `\n💰 Wallet Discount: $${walletDiscount.toFixed(2)}`;
            }
            if (paymentMethod === 'cash') {
                msg += `\n\n💵 Cash Received: $${document.getElementById('cash-amount-input').value}`;
                msg += `\n🔄 Change: $${cashChange.toFixed(2)}`;
            }
            alert(msg);
            
            // Reset sale
            cart = {};
            saleStarted = false;
            saleType = null;
            clientId = null;
            clientName = null;
            clientWallet = 0;
            
            updateCartDisplay();
            disableSearch();
            closeCheckout();
            document.getElementById('notes').value = '';
            document.getElementById('sale-type-display').textContent = 'Sale: -';
            document.getElementById('client-display').textContent = 'Client: -';
        } else {
            alert(`❌ Error: ${data.error}`);
        }
    })
    .catch(err => {
        console.error('Checkout error:', err);
        alert('❌ Failed to complete sale');
    });
}

// KEYBOARD SHORTCUTS
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        clearCart();
    }
});
