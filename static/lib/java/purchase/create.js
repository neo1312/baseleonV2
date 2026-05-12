window.onload=function(){

const formDetalle=document.getElementById("formDetalle")
const formQuantity= document.getElementById('quantity')
const formselectCodigo = document.getElementById('codigo')
const formselectProduct= document.getElementById('selectProduct')
const formunitario= document.getElementById('unitario')
const formtotal= document.getElementById('total')
const cuerpoTabla=document.getElementById('cuerpoTabla')
const btnCart= document.getElementById("btnCart")
const inputDetalle = document.getElementsByClassName("detalle")
const totalFactura = document.getElementById("totalFactura")
const input = document.getElementById('buscador')
const autocomplete_result= document.getElementById('autocomplete-result')



//traer datos de producto.
btnCart.addEventListener("click",(e)=>{
    e.preventDefault();
    let valorBtn=input.value
    traerData(valorBtn)
    input.value=""

})

const traerData = (valorBtn)=>{
    let url = "/purchase/getdata"
    fetch(url,{
        method:'POST',
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken':csrftoken,
        },
        body:JSON.stringify({'id':valorBtn})
    })
        .then((response)=>{
            return response.json();
        })
        .then((data)=>{
            console.log('data',data)
            arrayData=data.datos
            formselectProduct.value=arrayData[1]
            formselectCodigo.value=arrayData[0]
            formunitario.value=arrayData[2]
            formQuantity.value= 1
        })
    
}

//resgistrar orderItems
btnAdd.addEventListener("click",(e)=>{
    e.preventDefault();
    let quantity= document.getElementById("quantity")
    let codigo= document.getElementById("codigo")
    codigo=codigo.value
    quantity=quantity.value
    registrarItem(codigo,quantity)
    formDetalle.reset()
})


const registrarItem= (codigo,quantity)=>{
    console.log('Adding item - Code:', codigo, 'Qty:', quantity);
    let url = "/purchase/itemview"
    fetch(url,{
        method:'POST',
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken':csrftoken,
        },
        body:JSON.stringify([codigo,quantity])
    })
        .then((response)=>{
            return response.json();
        })
        .then((data)=>{
            console.log('Response from server:', data)
            if (data.status === 'updated') {
                console.log('DUPLICATE DETECTED - Updating row instead of reloading');
                // Item quantity was updated - update UI without reload
                updateRowUI(data.item_id, data.quantity, data.total);
                console.log('Updated existing item:', data.item_id);
            } else if (data.status === 'created') {
                console.log('NEW ITEM - Reloading page to show new row');
                // New item created - reload to show new row
                setTimeout(() => { location.reload(); }, 500);
            } else {
                console.log('Unexpected response format - reloading page');
                // Old format response - reload page
                setTimeout(() => { location.reload(); }, 500);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error adding item');
        })
}

const updateRowUI = (itemId, quantity, total) => {
    // Find the row for this item and update it
    const row = document.querySelector(`tr[data-item-id="${itemId}"]`);
    if (row) {
        // Update quantity input
        const qtyInput = row.querySelector('.quantity-input');
        if (qtyInput) {
            qtyInput.value = quantity;
        }
        
        // Update total cell
        const totalCell = row.querySelector('.item-total');
        if (totalCell) {
            totalCell.innerHTML = '<strong>$' + parseFloat(total).toFixed(2) + '</strong>';
        }
        
        // Update cart total
        updateCartTotal();
        
        // Visual feedback
        row.style.backgroundColor = '#fff3cd';
        setTimeout(() => {
            row.style.backgroundColor = '';
        }, 500);
    }
};

// Quantity increment/decrement buttons
const setupQuantityButtons = () => {
    // Increase quantity buttons
    document.querySelectorAll('.btn-quantity-increase').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const itemId = btn.getAttribute('data-item-id');
            const input = document.querySelector(`.quantity-input[data-item-id="${itemId}"]`);
            const currentQty = parseInt(input.value) || 1;
            updateItemQuantity(itemId, currentQty + 1);
        });
    });

    // Decrease quantity buttons
    document.querySelectorAll('.btn-quantity-decrease').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const itemId = btn.getAttribute('data-item-id');
            const input = document.querySelector(`.quantity-input[data-item-id="${itemId}"]`);
            const currentQty = parseInt(input.value) || 1;
            if (currentQty > 1) {
                updateItemQuantity(itemId, currentQty - 1);
            }
        });
    });
};

const updateItemQuantity = (itemId, newQuantity) => {
    let url = "/purchase/updatequantity"
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({item_id: itemId, quantity: newQuantity})
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Update the input field
            const input = document.querySelector(`.quantity-input[data-item-id="${itemId}"]`);
            input.value = newQuantity;
            
            // Update the total for this item
            const cost = parseFloat(data.cost);
            const total = newQuantity * cost;
            const totalCell = document.querySelector(`.item-total[data-item-id="${itemId}"]`);
            totalCell.innerHTML = '<strong>$' + total.toFixed(2) + '</strong>';
            
            // Update cart total
            updateCartTotal();
        } else {
            alert(data.message || 'Error updating quantity');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error updating quantity');
    });
};

const updateCartTotal = () => {
    let total = 0;
    document.querySelectorAll('.item-total').forEach(cell => {
        const text = cell.textContent.replace(/[$,]/g, '');
        total += parseFloat(text) || 0;
    });
    
    const totalFacturaEl = document.getElementById('totalFactura');
    if (totalFacturaEl) {
        totalFacturaEl.value = total.toFixed(2);
    }
};

// Initialize quantity buttons when page loads
setupQuantityButtons();

}
