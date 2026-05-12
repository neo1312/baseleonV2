# Inventory Architecture (Deprecated: Product.stock)

## ⚠️ BREAKING CHANGE: Product.stock Field Removed

As of migration `im/0054_remove_product_stock_field.py`, the `Product.stock` field has been **completely removed** from the database.

## Current Architecture: InventoryUnit as Single Source of Truth

### Key Rules
1. **InventoryUnit is the ONLY source of truth for inventory**
2. **Product.stock_ready_to_sale property** calculates available inventory by counting InventoryUnit records
3. **All stock queries** must use the `stock_ready_to_sale` property
4. **Never use deprecated Product.stock field** - it no longer exists in the database

### How It Works

```python
# Correct way to get available stock:
product = Product.objects.get(id=1)
available = product.stock_ready_to_sale  # ✅ Uses InventoryUnit ready_to_sale count

# WRONG - Product.stock no longer exists:
available = product.stock  # ❌ AttributeError - field removed
```

### Stock Tracking

**Creating inventory (e.g., purchase order received):**
```python
# When receiving a purchase order, create InventoryUnit records:
for i in range(quantity):
    InventoryUnit.objects.create(
        product=product,
        purchase_order=po,
        status='ready_to_sale',
        purchase_cost=cost,
        received_date=timezone.now(),
    )
# Now product.stock_ready_to_sale will automatically increase
```

**Selling (e.g., creating a sale):**
```python
# When creating a sale, InventoryUnit signal handlers automatically:
# 1. Find ready_to_sale units
# 2. Mark them as status='sold'
# 3. stock_ready_to_sale count decreases automatically

saleItem.objects.create(
    product=product,
    sale=sale,
    quantity=5,
    # ... other fields
)
# InventoryUnit signals handle marking units as sold
```

**Stock adjustments:**
```python
# Don't modify Product.stock (it doesn't exist!)
# Instead, manage InventoryUnit records:

# Mark units as damaged/adjustment:
units = InventoryUnit.objects.filter(product=product, status='ready_to_sale')[:5]
units.update(status='adjustment')
# stock_ready_to_sale decreases by 5

# Return units from a devolución:
for i in range(quantity):
    InventoryUnit.objects.create(
        product=product,
        devolve_from_sale=sale,
        status='ready_to_sale',
        # ... other fields
    )
# stock_ready_to_sale increases
```

### Querying Products with Available Stock

```python
# WRONG: Using removed stock field
products = Product.objects.filter(stock__gt=0)  # ❌ FieldError

# CORRECT: Filter then check stock_ready_to_sale in Python
products = Product.objects.all()
products_with_stock = [p for p in products if p.stock_ready_to_sale > 0]
products_with_stock.sort(key=lambda p: p.stock_ready_to_sale, reverse=True)
```

### Why This Change?

The old system had:
- **Product.stock**: A simple integer field (stale, manual updates)
- **InventoryUnit**: Detailed tracking of individual units (accurate, auto-updated)

These two systems could get out of sync, causing incorrect inventory displays and overselling.

**Solution**: Remove Product.stock, use ONLY InventoryUnit counting.

### Migration Notes

```
Before (deprecated):
- Product.stock = 6 (incorrect)
- InventoryUnit with status='ready_to_sale' = 2 (correct)
- POS showed 6 (WRONG!)

After (current):
- Product.stock = REMOVED (doesn't exist)
- InventoryUnit with status='ready_to_sale' = 2 (correct)
- POS shows 2 (CORRECT!)
```

### Files Using New System

✅ **POS System** (`pos/views.py`):
- Uses `stock_ready_to_sale` for all inventory queries
- Filters products by availability correctly

✅ **Purchase Orders** (`scm/views/purchase/po_views.py`):
- Creates InventoryUnit records when receiving goods
- No longer updates Product.stock

✅ **Tests** (`im/tests.py`):
- Create InventoryUnit objects in test fixtures
- Query using `stock_ready_to_sale` property

✅ **Management Commands** (`crm/management/commands/*_new.py`):
- Updated to use `stock_ready_to_sale`

⚠️ **Deprecated** (`statModul/views.py`):
- `update_stock()` endpoint now returns 400 error
- Use InventoryUnit API instead

### Testing the New System

```bash
# Old commands (don't exist):
python manage.py test_quantity_update      # ❌ Uses removed stock field
python manage.py test_stock_discount       # ❌ Uses removed stock field

# New commands:
python manage.py test_quantity_update_new  # ✅ Uses stock_ready_to_sale
python manage.py test_stock_discount_new   # ✅ Uses stock_ready_to_sale
```

### InventoryUnit Statuses

| Status | Meaning | Counted in stock_ready_to_sale |
|--------|---------|--------------------------------|
| `ready_to_sale` | Available for sale | ✅ Yes |
| `sold` | Part of a completed sale | ❌ No |
| `returned` | Returned from customer | ❌ No (should be marked ready_to_sale again) |
| `damaged` | Damaged/unusable | ❌ No |
| `adjustment` | Inventory adjustment | ❌ No |

### Common Mistakes to Avoid

```python
# ❌ WRONG: These will fail
product.stock = 10  # Field doesn't exist
product.stock += 5  # Field doesn't exist
Product.objects.filter(stock__gt=0)  # FieldError

# ✅ CORRECT: Use stock_ready_to_sale
product.stock_ready_to_sale  # Read-only property
Product.objects.all()  # Get products, then check stock_ready_to_sale in Python
```

## Future Improvements

1. **Database-level filtering**: Consider indexing InventoryUnit for faster queries
2. **Caching**: Cache stock_ready_to_sale counts for high-traffic endpoints
3. **Bulk operations**: Optimize batch InventoryUnit creation for large imports
4. **Real-time sync**: Implement WebSocket updates for multi-terminal POS systems
