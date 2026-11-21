"""Contoso Bikes catalog and stores: a verbatim copy of the data in episode 1 (generate_export.py, lines 20-72),
so the live till events sell the same products in the same stores as the star schema of episodes 1-16."""

CATALOG = {
    "Bikes": {
        "Road Bikes": [
            ("BK-R-100", "Road 100", "Red", 899.00, 540.00),
            ("BK-R-200", "Road 200", "Black", 1299.00, 760.00),
            ("BK-R-300", "Road 300 Carbon", "White", 2499.00, 1390.00),
        ],
        "Mountain Bikes": [
            ("BK-M-100", "Trail 100", "Green", 749.00, 455.00),
            ("BK-M-200", "Trail 200", "Black", 1149.00, 690.00),
            ("BK-M-300", "Enduro 300", "Orange", 2199.00, 1240.00),
        ],
        "City Bikes": [
            ("BK-C-100", "Urban 100", "Blue", 499.00, 300.00),
            ("BK-C-200", "Urban 200 E-Assist", "Grey", 1799.00, 1080.00),
        ],
    },
    "Accessories": {
        "Helmets": [
            ("AC-H-010", "Helmet Sport", "Red", 59.90, 22.00),
            ("AC-H-020", "Helmet Commuter", "Black", 79.90, 31.00),
        ],
        "Lights": [
            ("AC-L-010", "Front Light 400", "Black", 34.90, 12.50),
            ("AC-L-020", "Rear Light Radar", "Black", 129.00, 61.00),
        ],
        "Locks": [
            ("AC-K-010", "U-Lock", "Yellow", 44.90, 17.00),
            ("AC-K-020", "Folding Lock", "Black", 89.90, 38.00),
        ],
        "Bottles": [
            ("AC-B-010", "Bottle 750 ml", "Blue", 9.90, 2.80),
        ],
    },
    "Clothing": {
        "Jerseys": [
            ("CL-J-010", "Jersey Classic", "Blue", 49.90, 18.00),
            ("CL-J-020", "Jersey Aero", "White", 89.90, 35.00),
        ],
        "Gloves": [
            ("CL-G-010", "Gloves Summer", "Black", 24.90, 8.00),
            ("CL-G-020", "Gloves Winter", "Black", 39.90, 14.50),
        ],
    },
}

STORES = [
    ("Contoso Lisboa", "Portugal", "Store"),
    ("Contoso Porto", "Portugal", "Store"),
    ("Contoso Madrid", "Spain", "Store"),
    ("Contoso Paris", "France", "Store"),
    ("Contoso Online", "Portugal", "Online"),
]
