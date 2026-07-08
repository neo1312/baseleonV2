"""Dashboard utilities for role-based feature access"""
from crm.decorators import _canonical_roles


ROLE_FEATURES = {
    'Admin': {
        'label': 'Admin Dashboard',
        'icon': 'fas fa-user-shield',
        'color': '#DC143C',
        'cards': [
            {
                'category': 'Point of Sale',
                'items': [
                    {'title': 'POS System', 'description': 'Fast checkout & sales', 'icon': '💳', 'url': '/pos/', 'color': '#DC143C'},
                    {'title': 'POS Touch', 'description': 'Touch-optimized for tablets 10"', 'icon': '📱', 'url': '/pos/touch/', 'color': '#FF4500'},
                    {'title': 'Customer Display', 'description': 'Customer-facing ticket', 'icon': '🖥️', 'url': '/pos/customer-display/', 'color': '#FF8C00'},
                    {'title': 'Cierre de Caja', 'description': 'Arqueo y sesiones de caja', 'icon': '💰', 'url': '/cash-register/', 'color': '#FF8C00'},
                ]
            },
            {
                'category': 'Sales',
                'items': [
                    {'title': 'Ventas', 'description': 'Crear nueva venta', 'icon': '🛒', 'url': '/sale/new', 'color': '#DC143C'},
                    {'title': 'Cotizaciones', 'description': 'Crear cotización', 'icon': '📋', 'url': '/quote/new', 'color': '#B8221C'},
                    {'title': 'Devoluciones', 'description': 'Procesar devoluciones', 'icon': '↩️', 'url': '/devolution/new', 'color': '#8B1414'},
                ]
            },
            {
                'category': 'Inventory',
                'items': [
                    {'title': 'Productos', 'description': 'Gestionar productos', 'icon': '📦', 'url': '/im/product/list', 'color': '#D84E4E'},
                    {'title': 'Importar Productos', 'description': 'Importar productos desde CSV', 'icon': '📤', 'url': '/im/product/import-csv/', 'color': '#28A745'},
                    {'title': 'Categorías', 'description': 'Gestionar categorías', 'icon': '🏷️', 'url': '/category/list', 'color': '#CA1B31'},
                    {'title': 'Clientes', 'description': 'Gestionar clientes', 'icon': '👥', 'url': '/client/list', 'color': '#C41C38'},
                    {'title': 'Proveedores', 'description': 'Gestionar proveedores', 'icon': '🚚', 'url': '/provider/list', 'color': '#8B0000'},
                    {'title': 'Despiece', 'description': 'Convertir producto unitario a partes', 'icon': '🔄', 'url': '/im/product/despiece/', 'color': '#28A745'},
                    {'title': 'Grupos', 'description': 'Gestionar grupos de productos equivalentes', 'icon': '📁', 'url': '/im/group/list', 'color': '#6F42C1'},
                    {'title': 'Consultar Productos', 'description': 'Buscar por nombre, clave o código', 'icon': '🔍', 'url': '/wholesale/', 'color': '#228B22'},
                ],
            },
            {
                'category': 'Purchasing',
                'items': [
                    {'title': 'Orden Instantánea', 'description': 'Pedido completo en 1 clic', 'icon': '⚡', 'url': '/po/instant-full/', 'color': '#28A745'},
                    {'title': 'Compras / Manual', 'description': 'Agregar productos manualmente', 'icon': '🛍️', 'url': '/purchase/new', 'color': '#A61E2C'},
                    {'title': 'Órdenes de Compra', 'description': 'Crear órdenes', 'icon': '📄', 'url': '/po/create/', 'color': '#8B3A3A'},
                    {'title': 'CSV Upload', 'description': 'Subir CSV para orden', 'icon': '📄', 'url': '/po/upload-csv/', 'color': '#9B4D4D'},
                    {'title': 'Órdenes Colocadas', 'description': 'Ver órdenes', 'icon': '📋', 'url': '/po/placed/', 'color': '#704040'},
                ]
            },
            {
                'category': 'Audits & Reports',
                'items': [
                    {'title': 'Auditoría de Inventario', 'description': 'Realizar auditoría', 'icon': '🔍', 'url': '/im/audit/', 'color': '#4169E1'},
                    {'title': 'Reportes de Auditoría', 'description': 'Ver análisis', 'icon': '📊', 'url': '/im/audit/reports/', 'color': '#1E90FF'},
                    {'title': 'My Reports', 'description': 'Dashboard con gráficas', 'icon': '📊', 'url': '/report/my-reports/', 'color': '#6F42C1'},
                    {'title': 'Reporte Diario', 'description': 'Ganancia diaria', 'icon': '💰', 'url': '/report/daily/', 'color': '#0047AB'},
                    {'title': 'Alarmas', 'description': 'Monitorear márgenes y alertas', 'icon': '🔔', 'url': '/im/alarms/', 'color': '#FF8C00'},
                ]
            },
            {
                'category': 'Admin',
                'items': [
                    {'title': 'Parámetros de Pronóstico', 'description': 'Configurar sistema', 'icon': '⚙️', 'url': '/admin/im/forecastconfiguration/', 'color': '#4A4A4A'},
                    {'title': 'Gestión de Usuarios', 'description': 'Admin panel', 'icon': '👑', 'url': '/admin/', 'color': '#333333'},
                ]
            },
        ]
    },
    'Manager': {
        'label': 'Manager Dashboard',
        'icon': 'fas fa-chart-line',
        'color': '#1E90FF',
        'cards': [
            {
                'category': 'Reports',
                'items': [
                    {'title': 'Reportes de Auditoría', 'description': 'Ver análisis de inventario', 'icon': '📊', 'url': '/im/audit/reports/', 'color': '#1E90FF'},
                    {'title': 'My Reports', 'description': 'Dashboard con gráficas', 'icon': '📊', 'url': '/report/my-reports/', 'color': '#6F42C1'},
                    {'title': 'Reporte Diario', 'description': 'Ganancia del día', 'icon': '💰', 'url': '/report/daily/', 'color': '#0047AB'},
                    {'title': 'Reportes de Ventas', 'description': 'Análisis de ventas', 'icon': '📈', 'url': '/report/sale', 'color': '#4169E1'},
                    {'title': 'Alarmas', 'description': 'Monitorear márgenes y alertas', 'icon': '🔔', 'url': '/im/alarms/', 'color': '#FF8C00'},
                ]
            },
            {
                'category': 'View Data',
                'items': [
                    {'title': 'Productos', 'description': 'Ver todos los productos', 'icon': '📦', 'url': '/im/product/list', 'color': '#D84E4E'},
                    {'title': 'Importar Productos', 'description': 'Importar productos desde CSV', 'icon': '📤', 'url': '/im/product/import-csv/', 'color': '#28A745'},
                    {'title': 'Clientes', 'description': 'Ver clientes', 'icon': '👥', 'url': '/client/list', 'color': '#C41C38'},
                    {'title': 'Proveedores', 'description': 'Ver proveedores', 'icon': '🚚', 'url': '/provider/list', 'color': '#8B0000'},
                    {'title': 'Despiece', 'description': 'Convertir producto unitario a partes', 'icon': '🔄', 'url': '/im/product/despiece/', 'color': '#28A745'},
                    {'title': 'Consultar Productos', 'description': 'Buscar por nombre, clave o código', 'icon': '🔍', 'url': '/wholesale/', 'color': '#228B22'},
                ]
            },
            {
                'category': 'Audits',
                'items': [
                    {'title': 'Auditoría de Inventario', 'description': 'Ver auditorías', 'icon': '🔍', 'url': '/im/audit/', 'color': '#4169E1'},
                ]
            },
        ]
    },
    'Cashier': {
        'label': 'Cashier Dashboard',
        'icon': 'fas fa-cash-register',
        'color': '#FF8C00',
        'cards': [
            {
                'category': 'Point of Sale',
                'items': [
                    {'title': 'POS System', 'description': 'Fast & easy checkout', 'icon': '💳', 'url': '/pos/', 'color': '#DC143C'},
                    {'title': 'POS Touch', 'description': 'Touch-optimized for tablets 10"', 'icon': '📱', 'url': '/pos/touch/', 'color': '#FF4500'},
                    {'title': 'Customer Display', 'description': 'Customer-facing ticket', 'icon': '🖥️', 'url': '/pos/customer-display/', 'color': '#FF8C00'},
                    {'title': 'Cierre de Caja', 'description': 'Abrir y realizar arqueo', 'icon': '💰', 'url': '/cash-register/', 'color': '#FF8C00'},
                ]
            },
        ]
    },
    'Cajero': {
        'label': 'Cajero Dashboard',
        'icon': 'fas fa-cash-register',
        'color': '#FF8C00',
        'cards': [
            {
                'category': 'Point of Sale',
                'items': [
                    {'title': 'POS System', 'description': 'Fast & easy checkout', 'icon': '💳', 'url': '/pos/', 'color': '#DC143C'},
                    {'title': 'POS Touch', 'description': 'Touch-optimized for tablets 10"', 'icon': '📱', 'url': '/pos/touch/', 'color': '#FF4500'},
                    {'title': 'Customer Display', 'description': 'Customer-facing ticket', 'icon': '🖥️', 'url': '/pos/customer-display/', 'color': '#FF8C00'},
                    {'title': 'Cierre de Caja', 'description': 'Abrir y realizar arqueo', 'icon': '💰', 'url': '/cash-register/', 'color': '#FF8C00'},
                ]
            },
        ]
    },
    'Auditor': {
        'label': 'Auditor Dashboard',
        'icon': 'fas fa-search',
        'color': '#4169E1',
        'cards': [
            {
                'category': 'Audits',
                'items': [
                    {'title': 'Nueva Auditoría', 'description': 'Iniciar auditoría', 'icon': '🔍', 'url': '/im/audit/', 'color': '#4169E1'},
                    {'title': 'Reportes', 'description': 'Ver resultados', 'icon': '📊', 'url': '/im/audit/reports/', 'color': '#1E90FF'},
                ]
            },
            {
                'category': 'Reference',
                'items': [
                    {'title': 'Productos', 'description': 'Ver inventario', 'icon': '📦', 'url': '/im/product/list', 'color': '#D84E4E'},
                    {'title': 'Consultar Productos', 'description': 'Buscar por nombre, clave o código', 'icon': '🔍', 'url': '/wholesale/', 'color': '#228B22'},
                ]
            },
        ]
    },
    'Buyer': {
        'label': 'Buyer Dashboard',
        'icon': 'fas fa-shopping-bag',
        'color': '#228B22',
        'cards': [
            {
                'category': 'Purchasing',
                'items': [
                    {'title': 'Orden Instantánea', 'description': 'Pedido completo en 1 clic', 'icon': '⚡', 'url': '/po/instant-full/', 'color': '#28A745'},
                    {'title': 'Nueva Compra / Manual', 'description': 'Registrar compra manual', 'icon': '🛍️', 'url': '/purchase/new', 'color': '#A61E2C'},
                    {'title': 'Nueva Orden', 'description': 'Crear orden de compra', 'icon': '📄', 'url': '/po/create/', 'color': '#8B3A3A'},
                    {'title': 'CSV Upload', 'description': 'Subir CSV para orden', 'icon': '📄', 'url': '/po/upload-csv/', 'color': '#9B4D4D'},
                    {'title': 'Mis Órdenes', 'description': 'Ver órdenes', 'icon': '📋', 'url': '/po/placed/', 'color': '#704040'},
                ]
            },
            {
                'category': 'Reference',
                'items': [
                    {'title': 'Productos', 'description': 'Ver catálogo', 'icon': '📦', 'url': '/im/product/list', 'color': '#D84E4E'},
                    {'title': 'Importar Productos', 'description': 'Importar productos desde CSV', 'icon': '📤', 'url': '/im/product/import-csv/', 'color': '#28A745'},
                    {'title': 'Proveedores', 'description': 'Ver proveedores', 'icon': '🚚', 'url': '/provider/list', 'color': '#8B0000'},
                    {'title': 'Consultar Productos', 'description': 'Buscar por nombre, clave o código', 'icon': '🔍', 'url': '/wholesale/', 'color': '#228B22'},
                ]
            },
        ]
    },
    'WholesaleBuyer': {
        'label': 'Wholesale Buyer',
        'icon': 'fas fa-store-alt',
        'color': '#228B22',
        'cards': [
            {
                'category': 'Products',
                'items': [
                    {'title': 'Consultar Productos', 'description': 'Buscar productos por nombre, clave o código', 'icon': '🔍', 'url': '/wholesale/', 'color': '#228B22'},
                ]
            },
        ]
    },
}


MENU_STRUCTURE = {
    'Admin': [
        {'category': 'Categorías', 'icon': 'fas fa-tag', 'url': '/category/list', 'color': 'text-primary'},
        {'category': 'Consultar Productos', 'icon': 'fas fa-search', 'url': '/wholesale/', 'color': 'text-success'},
        {'divider': True},
        {'category': 'Productos', 'icon': 'fas fa-boxes', 'url': '/im/product/list', 'color': 'text-success'},
        {'category': 'Clientes', 'icon': 'fas fa-users', 'url': '/client/list', 'color': 'text-info'},
        {'category': 'Proveedores', 'icon': 'fas fa-truck', 'url': '/provider/list', 'color': 'text-warning'},
        {'divider': True},
        {'category': 'Compras', 'icon': 'fas fa-shopping-bag', 'url': '/purchase/new', 'color': 'text-danger'},
        {'category': 'Órdenes de Compra', 'icon': 'fas fa-file-invoice-dollar', 'url': '/po/create/', 'color': 'text-danger'},
        {'category': 'CSV Upload', 'icon': 'fas fa-upload', 'url': '/po/upload-csv/', 'color': 'text-danger'},
        {'category': 'Órdenes Colocadas', 'icon': 'fas fa-list', 'url': '/po/placed/', 'color': 'text-danger'},
        {'category': 'Ventas', 'icon': 'fas fa-shopping-cart', 'url': '/sale/new', 'color': 'text-primary'},
        {'category': 'Cotizaciones', 'icon': 'fas fa-quote-left', 'url': '/quote/new', 'color': 'text-info'},
        {'category': 'Devoluciones', 'icon': 'fas fa-undo', 'url': '/devolution/new', 'color': 'text-warning'},
        {'divider': True},
        {'category': 'Auditoría', 'icon': 'fas fa-magnifying-glass-chart', 'url': '/im/audit/', 'color': 'text-info'},
        {'category': 'Reportes de Auditoría', 'icon': 'fas fa-chart-line', 'url': '/im/audit/reports/', 'color': 'text-success'},
        {'category': 'My Reports', 'icon': 'fas fa-chart-pie', 'url': '/report/my-reports/', 'color': 'text-success'},
        {'category': 'Reporte Diario', 'icon': 'fas fa-chart-line', 'url': '/report/daily/', 'color': 'text-success'},
        {'category': 'Reportes de Ventas', 'icon': 'fas fa-chart-bar', 'url': '/report/sale', 'color': 'text-success'},
        {'category': 'Alarmas', 'icon': 'fas fa-bell', 'url': '/im/alarms/', 'color': 'text-warning'},
        {'category': 'Cierre de Caja', 'icon': 'fas fa-cash-register', 'url': '/cash-register/', 'color': 'text-warning'},
        {'divider': True},
        {'category': 'Parámetros de Pronóstico', 'icon': 'fas fa-sliders-h', 'url': '/admin/im/forecastconfiguration/', 'color': 'text-info'},
    ],
    'Manager': [
        {'category': 'Reportes de Auditoría', 'icon': 'fas fa-chart-line', 'url': '/im/audit/reports/', 'color': 'text-success'},
        {'category': 'My Reports', 'icon': 'fas fa-chart-pie', 'url': '/report/my-reports/', 'color': 'text-success'},
        {'category': 'Reporte Diario', 'icon': 'fas fa-chart-line', 'url': '/report/daily/', 'color': 'text-success'},
        {'category': 'Reportes de Ventas', 'icon': 'fas fa-chart-bar', 'url': '/report/sale', 'color': 'text-success'},
        {'category': 'Alarmas', 'icon': 'fas fa-bell', 'url': '/im/alarms/', 'color': 'text-warning'},
        {'category': 'Consultar Productos', 'icon': 'fas fa-search', 'url': '/wholesale/', 'color': 'text-success'},
        {'divider': True},
        {'category': 'Auditoría', 'icon': 'fas fa-magnifying-glass-chart', 'url': '/im/audit/', 'color': 'text-info'},
        {'divider': True},
        {'category': 'Productos', 'icon': 'fas fa-boxes', 'url': '/im/product/list', 'color': 'text-success'},
        {'category': 'Clientes', 'icon': 'fas fa-users', 'url': '/client/list', 'color': 'text-info'},
        {'category': 'Proveedores', 'icon': 'fas fa-truck', 'url': '/provider/list', 'color': 'text-warning'},
    ],
    'Cashier': [
        {'category': 'POS System', 'icon': 'fas fa-cash-register', 'url': '/pos/', 'color': 'text-primary'},
        {'category': 'POS Touch', 'icon': 'fas fa-mobile-alt', 'url': '/pos/touch/', 'color': 'text-info'},
        {'category': 'Customer Display', 'icon': 'fas fa-desktop', 'url': '/pos/customer-display/', 'color': 'text-success'},
        {'divider': True},
        {'category': 'Cierre de Caja', 'icon': 'fas fa-cash-register', 'url': '/cash-register/', 'color': 'text-warning'},
    ],
    'Cajero': [
        {'category': 'POS System', 'icon': 'fas fa-cash-register', 'url': '/pos/', 'color': 'text-primary'},
        {'category': 'POS Touch', 'icon': 'fas fa-mobile-alt', 'url': '/pos/touch/', 'color': 'text-info'},
        {'category': 'Customer Display', 'icon': 'fas fa-desktop', 'url': '/pos/customer-display/', 'color': 'text-success'},
        {'divider': True},
        {'category': 'Cierre de Caja', 'icon': 'fas fa-cash-register', 'url': '/cash-register/', 'color': 'text-warning'},
    ],
    'Auditor': [
        {'category': 'Auditoría', 'icon': 'fas fa-magnifying-glass-chart', 'url': '/im/audit/', 'color': 'text-info'},
        {'category': 'Reportes de Auditoría', 'icon': 'fas fa-chart-line', 'url': '/im/audit/reports/', 'color': 'text-success'},
        {'category': 'Consultar Productos', 'icon': 'fas fa-search', 'url': '/wholesale/', 'color': 'text-success'},
    ],
    'Buyer': [
        {'category': 'Compras', 'icon': 'fas fa-shopping-bag', 'url': '/purchase/new', 'color': 'text-danger'},
        {'category': 'Órdenes de Compra', 'icon': 'fas fa-file-invoice-dollar', 'url': '/po/create/', 'color': 'text-danger'},
        {'category': 'CSV Upload', 'icon': 'fas fa-upload', 'url': '/po/upload-csv/', 'color': 'text-danger'},
        {'category': 'Órdenes Colocadas', 'icon': 'fas fa-list', 'url': '/po/placed/', 'color': 'text-danger'},
        {'category': 'Consultar Productos', 'icon': 'fas fa-search', 'url': '/wholesale/', 'color': 'text-success'},
        {'divider': True},
        {'category': 'Productos', 'icon': 'fas fa-boxes', 'url': '/im/product/list', 'color': 'text-success'},
        {'category': 'Proveedores', 'icon': 'fas fa-truck', 'url': '/provider/list', 'color': 'text-warning'},
    ],
    'WholesaleBuyer': [
        {'category': 'Consultar Productos', 'icon': 'fas fa-search', 'url': '/wholesale/', 'color': 'text-success'},
    ],
}


def get_dashboard_for_user(user):
    """Get dashboard cards based on user role"""
    if not user.is_authenticated:
        return None
    
    user_roles = _canonical_roles(user.groups.values_list('name', flat=True))
    
    for role in user_roles:
        if role in ROLE_FEATURES:
            return ROLE_FEATURES[role]
    
    return ROLE_FEATURES.get('Admin')


def get_menu_for_user(user):
    """Get menu items based on user role"""
    if not user.is_authenticated:
        return None
    
    user_roles = _canonical_roles(user.groups.values_list('name', flat=True))
    
    for role in user_roles:
        if role in MENU_STRUCTURE:
            return MENU_STRUCTURE[role]
    
    return MENU_STRUCTURE.get('Admin')
