/**
 * MINIMALIST POS SYSTEM - Client-side Logic
 * Focus: Fast, distraction-free cashier experience
 */

// Global state
let cart = {}; // {product_id: {id, barcode, name, qty, price, tipo}}
let saleType = 'menudeo';
let clientId = null;
let clientName = 'General';
const TAX_RATE = 0; // NO TAXES

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    updateCartDisplay();
    document.getElementById('search-input').addEventListener('keypress', handleSearchKeypress);
    document.getElementById('sale-type-select').addEventListener('change', updateSaleTypeDisplay);
});

// SEARCH & PRODUCT MANAGEMENT
function handleSearchKeypress(e) {
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

// ADD TO CART
function addToCart(btn) {
    const row = btn.closest('tr');
    const productId = row.dataset.productId;
    const qtyInput = row.querySelector('.qty-input');
    const quantity = parseInt(qtyInput.value) || 1;
    
    const barcode = row.querySelector('.barcode').textContent;
    const name = row.querySelector('.name').textContent;
    const stock = parseInt(row.querySelector('.stock').textContent);
    
    // Validate stock
    if (quantity > stock) {
        alert(`⚠️ Only ${stock} in stock!`);
        return;
    }
    
    // Get price based on sale type
    const priceRegular = parseFloat(row.querySelector('.price-regular').textContent.replace('$', ''));
    const priceMayoreo = parseFloat(row.querySelector('.price-mayoreo').textContent.replace('$', ''));
    const price = saleType === 'mayoreo' ? priceMayoreo : priceRegular;
    
    // Check if already in cart
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
    clientId = document.getElementById('client-select').value;
    clientName = document.getElementById('client-select').options[document.getElementById('client-select').selectedIndex].text;
    
    // Update display
    updateSaleTypeDisplay();
    document.getElementById('client-display').textContent = `Client: ${clientName}`;
    
    closeSettings();
}

function updateSaleTypeDisplay() {
    document.getElementById('sale-type-display').textContent = `Sale: ${saleType === 'mayoreo' ? 'Mayoreo' : 'Menudeo'}`;
}

// CHECKOUT
function proceedCheckout() {
    if (Object.keys(cart).length === 0) {
        alert('⚠️ Cart is empty!');
        return;
    }
    
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
}

function closeCheckout() {
    document.getElementById('checkout-modal').classList.remove('show');
}

function confirmCheckout() {
    const paymentMethod = document.querySelector('input[name="payment"]:checked').value;
    const notes = document.getElementById('notes').value;
    
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
            alert(`✅ Sale completed!\nSale ID: ${data.sale_id}\nTotal: ${data.total}`);
            cart = {};
            updateCartDisplay();
            closeCheckout();
            document.getElementById('notes').value = '';
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
