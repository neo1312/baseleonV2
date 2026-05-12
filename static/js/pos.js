// ===== POS SYSTEM JAVASCRIPT =====

const cart = {};  // {product_id: {name, price, quantity, total}}
const TAX_RATE = 0.16;

// Get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrftoken = getCookie('csrftoken');

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', function() {
    updateDateTime();
    setInterval(updateDateTime, 1000);
    
    setupSearchListener();
    setupKeyboardShortcuts();
});

function updateDateTime() {
    const now = new Date();
    const options = { 
        weekday: 'short', 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    document.getElementById('current-date-time').textContent = now.toLocaleDateString('en-US', options);
}

// ===== SEARCH FUNCTIONALITY =====
function setupSearchListener() {
    const searchInput = document.getElementById('search-input');
    let debounceTimer;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = this.value.trim();
        
        if (query.length < 1) {
            loadDefaultProducts();
            return;
        }
        
        debounceTimer = setTimeout(() => {
            searchProducts(query);
        }, 300);
    });
    
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            // Search is already done, just focus first product
            const firstBtn = document.querySelector('.product-add-btn');
            if (firstBtn) firstBtn.focus();
        }
    });
}

function searchProducts(query) {
    fetch(`/pos/search/?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(products => {
            renderProducts(products);
        })
        .catch(error => {
            console.error('Search error:', error);
            alert('Error searching products');
        });
}

function loadDefaultProducts() {
    location.reload();
}

function renderProducts(products) {
    const container = document.getElementById('products-container');
    
    if (products.length === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 20px; color: #999;">No products found</div>';
        return;
    }
    
    container.innerHTML = products.map(p => `
        <div class="product-card" data-product-id="${p.id}">
            <div class="product-image">
                <i class="fas fa-toolbox"></i>
            </div>
            <div class="product-info">
                <h5 class="product-name">${p.name}</h5>
                <small class="product-sku">Barcode: ${p.barcode}</small>
                <div class="product-stock">
                    <span class="badge ${p.stock > 10 ? 'bg-success' : p.stock > 0 ? 'bg-warning' : 'bg-danger'}">
                        ${p.stock} in stock
                    </span>
                </div>
            </div>
            <div class="product-price">
                <span class="price">$${parseFloat(p.price).toFixed(2)}</span>
            </div>
            <button class="btn btn-sm btn-danger product-add-btn" 
                    onclick="quickAdd(${p.id}, '${p.name.replace(/'/g, "\\'")}', ${p.price})">
                <i class="fas fa-plus"></i>
            </button>
        </div>
    `).join('');
}

// ===== CART MANAGEMENT =====
function quickAdd(productId, productName, price) {
    if (cart[productId]) {
        cart[productId].quantity += 1;
    } else {
        cart[productId] = {
            id: productId,
            name: productName,
            price: parseFloat(price),
            quantity: 1
        };
    }
    
    updateCart();
    
    // Visual feedback
    const btn = event.target.closest('.product-add-btn');
    btn.innerHTML = '<i class="fas fa-check"></i>';
    btn.classList.add('disabled');
    setTimeout(() => {
        btn.innerHTML = '<i class="fas fa-plus"></i>';
        btn.classList.remove('disabled');
    }, 500);
}

function updateCart() {
    const cartContainer = document.getElementById('cart-items');
    const items = Object.values(cart);
    
    if (items.length === 0) {
        cartContainer.innerHTML = `
            <div class="empty-cart">
                <i class="fas fa-shopping-cart"></i>
                <p>Your cart is empty</p>
                <small class="text-muted">Add items from the left panel to get started</small>
            </div>
        `;
        document.getElementById('checkout-btn').disabled = true;
        updateTotals();
        return;
    }
    
    document.getElementById('checkout-btn').disabled = false;
    
    cartContainer.innerHTML = items.map(item => `
        <div class="cart-item">
            <h6 class="cart-item-name">${item.name}</h6>
            <div class="cart-item-row">
                <div class="cart-item-qty">
                    <button class="btn btn-sm btn-outline-danger qty-btn" onclick="decrementQty(${item.id})">−</button>
                    <input type="number" class="qty-input" value="${item.quantity}" onchange="updateQty(${item.id}, this.value)" min="1">
                    <button class="btn btn-sm btn-outline-success qty-btn" onclick="incrementQty(${item.id})">+</button>
                </div>
                <span>$${item.price.toFixed(2)}</span>
                <span class="cart-item-total">$${(item.quantity * item.price).toFixed(2)}</span>
                <span class="cart-item-remove" onclick="removeFromCart(${item.id})">
                    <i class="fas fa-trash"></i>
                </span>
            </div>
        </div>
    `).join('');
    
    updateTotals();
}

function incrementQty(productId) {
    if (cart[productId]) {
        cart[productId].quantity += 1;
        updateCart();
    }
}

function decrementQty(productId) {
    if (cart[productId]) {
        if (cart[productId].quantity > 1) {
            cart[productId].quantity -= 1;
            updateCart();
        }
    }
}

function updateQty(productId, quantity) {
    quantity = parseInt(quantity) || 1;
    if (quantity < 1) quantity = 1;
    
    if (cart[productId]) {
        cart[productId].quantity = quantity;
        updateCart();
    }
}

function removeFromCart(productId) {
    delete cart[productId];
    updateCart();
}

function clearAll() {
    if (Object.keys(cart).length === 0) {
        alert('Cart is already empty');
        return;
    }
    
    if (confirm('Clear the entire cart?')) {
        Object.keys(cart).forEach(key => delete cart[key]);
        updateCart();
        document.getElementById('search-input').focus();
    }
}

function continueShopping() {
    document.getElementById('search-input').value = '';
    document.getElementById('search-input').focus();
}

// ===== TOTALS CALCULATION =====
function updateTotals() {
    const items = Object.values(cart);
    const itemCount = items.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = items.reduce((sum, item) => sum + (item.quantity * item.price), 0);
    const tax = subtotal * TAX_RATE;
    const total = subtotal + tax;
    
    document.getElementById('total-items').textContent = itemCount;
    document.getElementById('total-price').textContent = `$${total.toFixed(2)}`;
    document.getElementById('subtotal').textContent = `$${subtotal.toFixed(2)}`;
    document.getElementById('tax').textContent = `$${tax.toFixed(2)}`;
    document.getElementById('total-amount').textContent = `$${total.toFixed(2)}`;
}

// ===== CHECKOUT =====
function checkout() {
    const items = Object.values(cart);
    if (items.length === 0) {
        alert('Please add items to your cart first');
        return;
    }
    
    // Build receipt preview
    const subtotal = items.reduce((sum, item) => sum + (item.quantity * item.price), 0);
    const tax = subtotal * TAX_RATE;
    const total = subtotal + tax;
    
    const receiptHTML = `
        <div style="text-align: center; margin-bottom: 10px;">
            <strong>FERRETERÍA LEÓN</strong><br>
            Receipt Preview
        </div>
        <div style="border-top: 1px dashed #ccc; border-bottom: 1px dashed #ccc; margin: 10px 0; padding: 10px 0;">
            ${items.map(item => `
                <div class="receipt-item">
                    <span>${item.name} x${item.quantity}</span>
                    <span>$${(item.quantity * item.price).toFixed(2)}</span>
                </div>
            `).join('')}
        </div>
        <div class="receipt-total" style="margin-top: 10px;">
            <div class="receipt-item">
                <span>Subtotal:</span>
                <span>$${subtotal.toFixed(2)}</span>
            </div>
            <div class="receipt-item">
                <span>Tax (16%):</span>
                <span>$${tax.toFixed(2)}</span>
            </div>
            <div class="receipt-item" style="font-size: 1.1rem; border-top: 1px dashed #ccc; margin-top: 5px; padding-top: 5px;">
                <span>TOTAL:</span>
                <span>$${total.toFixed(2)}</span>
            </div>
        </div>
    `;
    
    document.getElementById('receipt-preview').innerHTML = receiptHTML;
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('checkoutModal'));
    modal.show();
}

function confirmCheckout() {
    const items = Object.values(cart);
    const paymentMethod = document.querySelector('input[name="payment"]:checked').value;
    
    const payload = {
        items: items.map(item => ({
            product_id: item.id,
            quantity: item.quantity,
            price: item.price
        })),
        payment_method: paymentMethod,
        client_id: null
    };
    
    // Disable button
    const btn = document.querySelector('.modal-footer .btn-danger');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    
    fetch('/pos/complete-sale/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        },
        body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('checkoutModal'));
            modal.hide();
            
            // Show success message
            alert(`✓ Sale Completed!\n\nSale ID: ${data.sale_id}\nTotal: ${data.total}`);
            
            // Clear cart
            Object.keys(cart).forEach(key => delete cart[key]);
            updateCart();
            
            // Reset
            document.getElementById('search-input').value = '';
            document.getElementById('search-input').focus();
            document.getElementById('payment_cash').checked = true;
        } else {
            alert(`❌ Error: ${data.error}`);
        }
        
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-check"></i> Confirm & Complete';
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Connection error. Please try again.');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-check"></i> Confirm & Complete';
    });
}

// ===== KEYBOARD SHORTCUTS =====
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // ESC - Clear cart
        if (e.key === 'Escape') {
            clearAll();
        }
        
        // Ctrl+Enter or Cmd+Enter - Checkout
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            if (!document.getElementById('checkout-btn').disabled) {
                checkout();
            }
        }
    });
}

// ===== PRINT RECEIPT =====
function printReceipt(saleId) {
    window.open(`/receipt/${saleId}/`, '_blank');
}
